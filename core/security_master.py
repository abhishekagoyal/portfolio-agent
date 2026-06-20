import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS instruments (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol              TEXT NOT NULL,
            name                TEXT,
            asset_class         TEXT NOT NULL,
            exchange            TEXT,
            currency            TEXT DEFAULT 'USD',
            status              TEXT DEFAULT 'active',
            cme_product_code    TEXT,
            contract_size       REAL,
            tick_size           REAL,
            tick_value          REAL,
            expiry              TEXT,
            underlying_symbol   TEXT,
            strike              REAL,
            option_right        TEXT,
            multiplier          REAL,
            margin_method       TEXT,
            conid               INTEGER,
            created_at          TEXT,
            updated_at          TEXT,
            UNIQUE(symbol, asset_class, expiry, strike, option_right)
        )
    """)
    conn.commit()
    conn.close()

def add_instrument(data: dict) -> tuple[bool, str]:
    try:
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        conn.execute("""
            INSERT INTO instruments (
                symbol, name, asset_class, exchange, currency, status,
                cme_product_code, contract_size, tick_size, tick_value, expiry,
                underlying_symbol, strike, option_right, multiplier,
                margin_method, conid, created_at, updated_at
            ) VALUES (
                :symbol, :name, :asset_class, :exchange, :currency, :status,
                :cme_product_code, :contract_size, :tick_size, :tick_value, :expiry,
                :underlying_symbol, :strike, :option_right, :multiplier,
                :margin_method, :conid, :created_at, :updated_at
            )
        """, {
            "symbol":            data.get("symbol", "").upper(),
            "name":              data.get("name"),
            "asset_class":       data.get("asset_class"),
            "exchange":          data.get("exchange"),
            "currency":          data.get("currency", "USD"),
            "status":            data.get("status", "active"),
            "cme_product_code":  data.get("cme_product_code"),
            "contract_size":     data.get("contract_size"),
            "tick_size":         data.get("tick_size"),
            "tick_value":        data.get("tick_value"),
            "expiry":            data.get("expiry"),
            "underlying_symbol": data.get("underlying_symbol"),
            "strike":            data.get("strike"),
            "option_right":      data.get("option_right"),
            "multiplier":        data.get("multiplier"),
            "margin_method":     data.get("margin_method"),
            "conid":             data.get("conid"),
            "created_at":        now,
            "updated_at":        now,
        })
        conn.commit()
        conn.close()
        return True, f"Added {data.get('symbol', '').upper()} successfully."
    except sqlite3.IntegrityError:
        return False, f"{data.get('symbol', '').upper()} already exists in the security master."
    except Exception as e:
        return False, f"Error: {str(e)}"

def search_instruments(query: str = "", asset_class: str = "All") -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM instruments WHERE status = 'active'"
    params = []
    if query:
        sql += " AND (symbol LIKE ? OR name LIKE ?)"
        params += [f"%{query}%", f"%{query}%"]
    if asset_class and asset_class != "All":
        sql += " AND asset_class = ?"
        params.append(asset_class)
    sql += " ORDER BY asset_class, symbol"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_instrument(symbol: str, asset_class: str = None) -> dict | None:
    conn = get_connection()
    if asset_class:
        row = conn.execute(
            "SELECT * FROM instruments WHERE symbol = ? AND asset_class = ? AND status = 'active'",
            (symbol.upper(), asset_class)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM instruments WHERE symbol = ? AND status = 'active' LIMIT 1",
            (symbol.upper(),)
        ).fetchone()
    conn.close()
    return dict(row) if row else None

def update_instrument(id: int, data: dict) -> tuple[bool, str]:
    try:
        conn = get_connection()
        data["updated_at"] = datetime.utcnow().isoformat()
        fields = ", ".join(f"{k} = :{k}" for k in data if k != "id")
        data["id"] = id
        conn.execute(f"UPDATE instruments SET {fields} WHERE id = :id", data)
        conn.commit()
        conn.close()
        return True, "Updated successfully."
    except Exception as e:
        return False, str(e)

def deactivate_instrument(id: int) -> tuple[bool, str]:
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE instruments SET status = 'inactive', updated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), id)
        )
        conn.commit()
        conn.close()
        return True, "Instrument removed."
    except Exception as e:
        return False, str(e)

def get_all_asset_classes() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT asset_class FROM instruments WHERE status = 'active' ORDER BY asset_class"
    ).fetchall()
    conn.close()
    return [r["asset_class"] for r in rows]

def seed_default_instruments():
    defaults = [
        {"symbol": "AAPL", "name": "Apple Inc",                "asset_class": "STK",    "exchange": "NASDAQ", "margin_method": "REGT", "currency": "USD"},
        {"symbol": "MSFT", "name": "Microsoft Corp",            "asset_class": "STK",    "exchange": "NASDAQ", "margin_method": "REGT", "currency": "USD"},
        {"symbol": "SPY",  "name": "SPDR S&P 500 ETF",          "asset_class": "STK",    "exchange": "NYSE",   "margin_method": "REGT", "currency": "USD"},
        {"symbol": "QQQ",  "name": "Invesco QQQ Trust",         "asset_class": "STK",    "exchange": "NASDAQ", "margin_method": "REGT", "currency": "USD"},
        {"symbol": "ES",   "name": "E-mini S&P 500 Futures",    "asset_class": "FUT",    "exchange": "CME",    "margin_method": "SPAN", "currency": "USD", "cme_product_code": "ES",  "contract_size": 50,     "tick_size": 0.25,    "tick_value": 12.5},
        {"symbol": "NQ",   "name": "E-mini NASDAQ 100 Futures", "asset_class": "FUT",    "exchange": "CME",    "margin_method": "SPAN", "currency": "USD", "cme_product_code": "NQ",  "contract_size": 20,     "tick_size": 0.25,    "tick_value": 5.0},
        {"symbol": "GC",   "name": "Gold Futures",              "asset_class": "FUT",    "exchange": "COMEX",  "margin_method": "SPAN", "currency": "USD", "cme_product_code": "GC",  "contract_size": 100,    "tick_size": 0.10,    "tick_value": 10.0},
        {"symbol": "CL",   "name": "Crude Oil Futures",         "asset_class": "FUT",    "exchange": "NYMEX",  "margin_method": "SPAN", "currency": "USD", "cme_product_code": "CL",  "contract_size": 1000,   "tick_size": 0.01,    "tick_value": 10.0},
        {"symbol": "ZB",   "name": "US Treasury Bond Futures",  "asset_class": "FUT",    "exchange": "CBOT",   "margin_method": "SPAN", "currency": "USD", "cme_product_code": "ZB",  "contract_size": 100000, "tick_size": 0.03125, "tick_value": 31.25},
        {"symbol": "BTC",  "name": "Bitcoin",                   "asset_class": "CRYPTO", "exchange": "IBKR",   "margin_method": "IBKR", "currency": "USD"},
        {"symbol": "ETH",  "name": "Ethereum",                  "asset_class": "CRYPTO", "exchange": "IBKR",   "margin_method": "IBKR", "currency": "USD"},
    ]
    for inst in defaults:
        add_instrument(inst)

init_db()