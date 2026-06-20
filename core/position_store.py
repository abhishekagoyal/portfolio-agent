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

            -- identity
            symbol              TEXT NOT NULL,
            asset_class         TEXT NOT NULL,
            name                TEXT,

            -- trade details
            side                TEXT DEFAULT 'LONG',
            quantity            REAL NOT NULL,
            entry_price         REAL NOT NULL,
            current_price       REAL DEFAULT 0,

            -- futures / options specific
            expiry              TEXT,
            strike              REAL,
            option_right        TEXT,
            multiplier          REAL DEFAULT 1,
            contract_size       REAL DEFAULT 1,

            -- computed values (recalculated on price update)
            market_value        REAL DEFAULT 0,
            unrealized_pnl      REAL DEFAULT 0,
            notional_value      REAL DEFAULT 0,

            -- margin (populated by margin engine)
            margin_method       TEXT,
            initial_margin      REAL DEFAULT 0,
            maintenance_margin  REAL DEFAULT 0,

            -- source
            source              TEXT DEFAULT 'manual',
            account_id          TEXT,
            exchange            TEXT,
            currency            TEXT DEFAULT 'USD',

            -- status
            status              TEXT DEFAULT 'open',
            opened_at           TEXT,
            updated_at          TEXT
        )
    """)
    conn.commit()
    conn.close()

def _compute_fields(d: dict) -> dict:
    """Compute market_value, unrealized_pnl, notional_value from raw fields."""
    qty    = d.get("quantity", 0) or 0
    entry  = d.get("entry_price", 0) or 0
    curr   = d.get("current_price", 0) or entry
    mult   = d.get("multiplier", 1) or 1
    cs     = d.get("contract_size", 1) or 1
    side   = d.get("side", "LONG")

    notional      = abs(qty) * curr * mult * cs
    market_value  = notional if side == "LONG" else -notional
    direction     = 1 if side == "LONG" else -1
    unrealized    = direction * qty * (curr - entry) * mult * cs

    d["market_value"]   = round(market_value, 2)
    d["unrealized_pnl"] = round(unrealized, 2)
    d["notional_value"] = round(notional, 2)
    return d

def add_position(data: dict) -> tuple[bool, str]:
    try:
        data = _compute_fields(data)
        conn = get_connection()
        now  = datetime.utcnow().isoformat()
        conn.execute("""
            INSERT INTO positions (
                symbol, asset_class, name, side, quantity, entry_price, current_price,
                expiry, strike, option_right, multiplier, contract_size,
                market_value, unrealized_pnl, notional_value,
                margin_method, initial_margin, maintenance_margin,
                source, account_id, exchange, currency,
                status, opened_at, updated_at
            ) VALUES (
                :symbol, :asset_class, :name, :side, :quantity, :entry_price, :current_price,
                :expiry, :strike, :option_right, :multiplier, :contract_size,
                :market_value, :unrealized_pnl, :notional_value,
                :margin_method, :initial_margin, :maintenance_margin,
                :source, :account_id, :exchange, :currency,
                :status, :opened_at, :updated_at
            )
        """, {
            "symbol":             data.get("symbol", "").upper(),
            "asset_class":        data.get("asset_class", "STK"),
            "name":               data.get("name"),
            "side":               data.get("side", "LONG"),
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
        return True, f"Position added: {data.get('side','LONG')} {data.get('quantity')} {data.get('symbol','').upper()}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def get_positions(status: str = "open", asset_class: str = None) -> list[dict]:
    conn = get_connection()
    sql    = "SELECT * FROM positions WHERE status = ?"
    params = [status]
    if asset_class and asset_class != "All":
        sql += " AND asset_class = ?"
        params.append(asset_class)
    sql += " ORDER BY asset_class, symbol"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_position_price(id: int, current_price: float) -> tuple[bool, str]:
    """Update current price and recompute P&L fields."""
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

def update_position_margin(id: int, initial_margin: float, maintenance_margin: float) -> tuple[bool, str]:
    """Update margin fields after margin engine calculation."""
    try:
        conn = get_connection()
        conn.execute("""
            UPDATE positions SET
                initial_margin     = ?,
                maintenance_margin = ?,
                updated_at         = ?
            WHERE id = ?
        """, (initial_margin, maintenance_margin, datetime.utcnow().isoformat(), id))
        conn.commit()
        conn.close()
        return True, "Margin updated."
    except Exception as e:
        return False, str(e)

def close_position(id: int) -> tuple[bool, str]:
    """Soft close a position."""
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

def get_portfolio_summary() -> dict:
    """Aggregate across all open positions."""
    positions = get_positions("open")
    if not positions:
        return {
            "total_notional":         0,
            "total_market_value":     0,
            "total_unrealized_pnl":   0,
            "total_initial_margin":   0,
            "total_maintenance_margin": 0,
            "by_asset_class":         {},
            "positions":              [],
        }

    total_notional  = sum(p["notional_value"]      for p in positions)
    total_mv        = sum(p["market_value"]         for p in positions)
    total_pnl       = sum(p["unrealized_pnl"]       for p in positions)
    total_im        = sum(p["initial_margin"]       for p in positions)
    total_mm        = sum(p["maintenance_margin"]   for p in positions)

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