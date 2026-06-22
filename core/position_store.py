import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_positions_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_id       INTEGER,              -- FK to instruments.id in security master
            symbol              TEXT NOT NULL,
            asset_class         TEXT NOT NULL,
            name                TEXT,
            side                TEXT DEFAULT 'LONG',
            quantity            REAL NOT NULL,
            entry_price         REAL NOT NULL,
            current_price       REAL DEFAULT 0,
            expiry              TEXT,
            strike              REAL,
            option_right        TEXT,
            multiplier          REAL DEFAULT 1,
            contract_size       REAL DEFAULT 1,
            market_value        REAL DEFAULT 0,
            unrealized_pnl      REAL DEFAULT 0,
            notional_value      REAL DEFAULT 0,
            margin_method       TEXT,
            initial_margin      REAL DEFAULT 0,
            maintenance_margin  REAL DEFAULT 0,
            source              TEXT DEFAULT 'manual',
            account_id          TEXT,
            exchange            TEXT,
            currency            TEXT DEFAULT 'USD',
            status              TEXT DEFAULT 'open',
            opened_at           TEXT,
            updated_at          TEXT
        )
    """)
    # Add instrument_id column if upgrading existing db
    try:
        conn.execute("ALTER TABLE positions ADD COLUMN instrument_id INTEGER")
        conn.commit()
    except Exception:
        pass  # Column already exists
    conn.commit()
    conn.close()

def _normalise_side(side: str) -> str:
    """Normalise BUY→LONG, SELL→SHORT regardless of source."""
    s = (side or "LONG").upper()
    if s == "BUY":
        return "LONG"
    if s == "SELL":
        return "SHORT"
    return s

def _compute_fields(d: dict) -> dict:
    """Compute market_value, unrealized_pnl, notional_value from raw fields."""
    qty   = d.get("quantity", 0) or 0
    entry = d.get("entry_price", 0) or 0
    curr  = d.get("current_price", 0) or entry
    mult  = d.get("multiplier", 1) or 1
    cs    = d.get("contract_size", 1) or 1
    side  = _normalise_side(d.get("side", "LONG"))

    notional     = abs(qty) * curr * mult * cs
    market_value = notional if side == "LONG" else -notional
    direction    = 1 if side == "LONG" else -1
    unrealized   = direction * qty * (curr - entry) * mult * cs

    d["market_value"]   = round(market_value, 2)
    d["unrealized_pnl"] = round(unrealized, 2)
    d["notional_value"] = round(notional, 2)
    return d

def add_position(data: dict) -> tuple[bool, str]:
    try:
        data["side"] = _normalise_side(data.get("side", "LONG"))
        data = _compute_fields(data)
        conn = get_connection()
        now  = datetime.utcnow().isoformat()
        conn.execute("""
            INSERT INTO positions (
                instrument_id, symbol, asset_class, name, side,
                quantity, entry_price, current_price,
                expiry, strike, option_right, multiplier, contract_size,
                market_value, unrealized_pnl, notional_value,
                margin_method, initial_margin, maintenance_margin,
                source, account_id, exchange, currency,
                status, opened_at, updated_at
            ) VALUES (
                :instrument_id, :symbol, :asset_class, :name, :side,
                :quantity, :entry_price, :current_price,
                :expiry, :strike, :option_right, :multiplier, :contract_size,
                :market_value, :unrealized_pnl, :notional_value,
                :margin_method, :initial_margin, :maintenance_margin,
                :source, :account_id, :exchange, :currency,
                :status, :opened_at, :updated_at
            )
        """, {
            "instrument_id":      data.get("instrument_id"),
            "symbol":             data.get("symbol", "").upper(),
            "asset_class":        data.get("asset_class", "STK"),
            "name":               data.get("name"),
            "side":               data["side"],
            "quantity":           data.get("quantity", 0),
            "entry_price":        data.get("entry_price", 0),
            "current_price":      data.get("current_price", data.get("entry_price", 0)),
            "expiry":             data.get("expiry"),
            "strike":             data.get("strike"),
            "option_right":       data.get("option_right"),
            "multiplier":         data.get("multiplier", 1),
            "contract_size":      data.get("contract_size", 1),
            "market_value":       data.get("market_value", 0),
            "unrealized_pnl":     data.get("unrealized_pnl", 0),
            "notional_value":     data.get("notional_value", 0),
            "margin_method":      data.get("margin_method"),
            "initial_margin":     data.get("initial_margin", 0),
            "maintenance_margin": data.get("maintenance_margin", 0),
            "source":             data.get("source", "manual"),
            "account_id":         data.get("account_id"),
            "exchange":           data.get("exchange"),
            "currency":           data.get("currency", "USD"),
            "status":             "open",
            "opened_at":          now,
            "updated_at":         now,
        })
        conn.commit()
        conn.close()
        return True, f"Position added: {data['side']} {data.get('quantity')} {data.get('symbol','').upper()}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def get_positions(status: str = "open", asset_class: str = None) -> list[dict]:
    conn   = get_connection()
    sql    = "SELECT * FROM positions WHERE status = ?"
    params = [status]
    if asset_class and asset_class != "All":
        sql += " AND asset_class = ?"
        params.append(asset_class)
    sql += " ORDER BY asset_class, symbol"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_positions_by_instrument(instrument_id: int, status: str = "open") -> list[dict]:
    """Get all positions for a specific instrument_id (exact contract match)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM positions WHERE instrument_id=? AND status=? ORDER BY opened_at ASC",
        (instrument_id, status)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def reduce_or_close_position(instrument_id: int, reduce_qty: float,
                              symbol: str = None) -> tuple[bool, str, float]:
    """
    Reduce existing opposite position(s) for a given instrument_id by reduce_qty.
    Returns (success, message, remaining_qty) where remaining_qty > 0 means
    the order exceeded the existing position — caller opens remainder as new position.
    """
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM positions WHERE instrument_id=? AND status='open' ORDER BY opened_at ASC",
            (instrument_id,)
        ).fetchall()

        if not rows:
            conn.close()
            return False, f"No open position found for instrument_id={instrument_id}", reduce_qty

        remaining = reduce_qty
        for row in rows:
            p = dict(row)
            existing_qty = p["quantity"]

            if remaining >= existing_qty:
                conn.execute(
                    "UPDATE positions SET status='closed', updated_at=? WHERE id=?",
                    (datetime.utcnow().isoformat(), p["id"])
                )
                remaining -= existing_qty
            else:
                new_qty = existing_qty - remaining
                conn.execute(
                    "UPDATE positions SET quantity=?, updated_at=? WHERE id=?",
                    (new_qty, datetime.utcnow().isoformat(), p["id"])
                )
                remaining = 0
                break

        conn.commit()
        conn.close()
        label = symbol or f"instrument_id={instrument_id}"
        return True, f"Reduced {label} by {reduce_qty}", remaining

    except Exception as e:
        return False, str(e), 0

def update_position_price(id: int, current_price: float) -> tuple[bool, str]:
    try:
        conn = get_connection()
        row  = conn.execute("SELECT * FROM positions WHERE id = ?", (id,)).fetchone()
        if not row:
            conn.close()
            return False, "Position not found."
        d = dict(row)
        d["current_price"] = current_price
        d = _compute_fields(d)
        conn.execute("""
            UPDATE positions SET
                current_price  = ?,
                market_value   = ?,
                unrealized_pnl = ?,
                notional_value = ?,
                updated_at     = ?
            WHERE id = ?
        """, (current_price, d["market_value"], d["unrealized_pnl"],
              d["notional_value"], datetime.utcnow().isoformat(), id))
        conn.commit()
        conn.close()
        return True, "Price updated."
    except Exception as e:
        return False, str(e)

def update_position_margin(id: int, initial_margin: float,
                           maintenance_margin: float) -> tuple[bool, str]:
    try:
        conn = get_connection()
        conn.execute("""
            UPDATE positions SET
                initial_margin     = ?,
                maintenance_margin = ?,
                updated_at         = ?
            WHERE id = ?
        """, (initial_margin, maintenance_margin,
              datetime.utcnow().isoformat(), id))
        conn.commit()
        conn.close()
        return True, "Margin updated."
    except Exception as e:
        return False, str(e)

def close_position(id: int) -> tuple[bool, str]:
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE positions SET status = 'closed', updated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), id)
        )
        conn.commit()
        conn.close()
        return True, "Position closed."
    except Exception as e:
        return False, str(e)

def recalculate_portfolio_margins() -> None:
    """
    Recalculate and update margin for all open futures positions.
    Nets long/short positions in the same symbol before calculating SPAN,
    then distributes the net margin proportionally across individual position rows.
    """
    from core.span import calculate_portfolio_margin
    positions = get_positions("open")
    fut_positions = [p for p in positions if p["asset_class"] == "FUT"]
    if not fut_positions:
        return

    # Step 1: Net quantities per symbol across all open positions
    net_by_symbol = {}
    for p in fut_positions:
        sym = p["symbol"]
        is_long = p["side"] == "LONG"
        signed_qty = p["quantity"] if is_long else -p["quantity"]
        price = p["current_price"] or p["entry_price"]
        if sym not in net_by_symbol:
            net_by_symbol[sym] = {"net_qty": 0, "price": price}
        net_by_symbol[sym]["net_qty"] += signed_qty

    # Step 2: Build span positions from net quantities (exclude flat positions)
    span_positions = []
    for sym, data in net_by_symbol.items():
        if data["net_qty"] != 0:
            span_positions.append({
                "symbol":          sym,
                "quantity":        data["net_qty"],
                "price":           data["price"],
                "is_short_option": False,
            })

    # Step 3: Calculate SPAN on netted portfolio
    if span_positions:
        result = calculate_portfolio_margin(span_positions)
        total_scanning = result.get("total_scanning_risk", 0)
        total_net      = result.get("net_futures_margin", 0)
        credit_ratio   = (total_net / total_scanning) if total_scanning > 0 else 1.0

        # Build per-symbol net margin map
        symbol_margin = {}
        for fp in result.get("futures_positions", []):
            sym      = fp["symbol"]
            gross_im = fp.get("initial_margin", 0)
            net_im   = round(gross_im * credit_ratio, 2)
            symbol_margin[sym] = net_im
    else:
        # All positions net to flat — zero margin
        symbol_margin = {}

    # Step 4: Distribute net margin across individual position rows for each symbol
    # Group positions by symbol, split margin proportionally by quantity
    conn = get_connection()
    for sym in net_by_symbol:
        sym_positions = [p for p in fut_positions if p["symbol"] == sym]
        net_qty       = abs(net_by_symbol[sym]["net_qty"])
        total_qty     = sum(p["quantity"] for p in sym_positions)
        net_im_total  = symbol_margin.get(sym, 0)

        for p in sym_positions:
            if net_qty == 0:
                # Fully netted — zero margin on all rows
                row_im = 0.0
                row_mm = 0.0
            else:
                # Distribute proportionally by quantity contribution to net
                row_im = round(net_im_total * (p["quantity"] / total_qty), 2)
                row_mm = round(row_im * 0.91, 2)
            conn.execute(
                "UPDATE positions SET initial_margin=?, maintenance_margin=?, updated_at=? WHERE id=?",
                (row_im, row_mm, datetime.utcnow().isoformat(), p["id"])
            )
    conn.commit()
    conn.close()

def get_portfolio_summary() -> dict:
    positions = get_positions("open")
    if not positions:
        return {
            "total_notional":           0,
            "total_market_value":       0,
            "total_unrealized_pnl":     0,
            "total_initial_margin":     0,
            "total_maintenance_margin": 0,
            "by_asset_class":           {},
            "positions":                [],
        }

    total_notional = sum(p["notional_value"]    for p in positions)
    total_mv       = sum(p["market_value"]       for p in positions)
    total_pnl      = sum(p["unrealized_pnl"]     for p in positions)
    total_im       = sum(p["initial_margin"]     for p in positions)
    total_mm       = sum(p["maintenance_margin"] for p in positions)

    by_class = {}
    for p in positions:
        ac = p["asset_class"]
        if ac not in by_class:
            by_class[ac] = {"count": 0, "notional": 0, "pnl": 0, "initial_margin": 0}
        by_class[ac]["count"]          += 1
        by_class[ac]["notional"]       += p["notional_value"]
        by_class[ac]["pnl"]            += p["unrealized_pnl"]
        by_class[ac]["initial_margin"] += p["initial_margin"]

    return {
        "total_notional":           round(total_notional, 2),
        "total_market_value":       round(total_mv, 2),
        "total_unrealized_pnl":     round(total_pnl, 2),
        "total_initial_margin":     round(total_im, 2),
        "total_maintenance_margin": round(total_mm, 2),
        "by_asset_class":           by_class,
        "positions":                positions,
    }

init_positions_db()