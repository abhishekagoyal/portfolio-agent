import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trading.db")

HAIRCUT_RULES = {
    "CASH":      {"USD": 0.0,   "NON_USD": 2.0},
    "STK":       {"default": 10.0},
    "ETF":       {"default": 10.0},
    "BOND":      {"TREASURY_SHORT": 0.5, "TREASURY_MED": 1.0, "TREASURY_LONG": 2.0,
                  "TREASURY_XLONG": 4.0, "IG_CORP": 8.0, "HY_CORP": 15.0, "default": 5.0},
    "COMMODITY": {"GOLD": 15.0, "SILVER": 15.0, "default": 25.0},
    "CRYPTO":    {"BTC": 35.0,  "ETH": 35.0,    "default": 50.0},
}

def get_default_haircut(asset_class: str, sub_type: str = None, symbol: str = None) -> float:
    rules = HAIRCUT_RULES.get(asset_class, {})
    if asset_class == "CASH":
        return rules.get(sub_type or "NON_USD", 2.0)
    if asset_class == "CRYPTO" and symbol:
        return rules.get(symbol.upper(), rules.get("default", 50.0))
    if asset_class == "COMMODITY" and symbol:
        return rules.get(symbol.upper(), rules.get("default", 25.0))
    if asset_class == "BOND" and sub_type:
        return rules.get(sub_type, rules.get("default", 5.0))
    return rules.get("default", 10.0)

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_collateral_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS collateral (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_class     TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            name            TEXT,
            sub_type        TEXT,
            quantity        REAL NOT NULL DEFAULT 0,
            market_price    REAL NOT NULL DEFAULT 0,
            currency        TEXT DEFAULT 'USD',
            haircut_pct     REAL NOT NULL DEFAULT 10.0,
            custodian       TEXT DEFAULT 'IBKR',
            source          TEXT DEFAULT 'manual',
            status          TEXT DEFAULT 'active',
            created_at      TEXT,
            updated_at      TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_collateral(data: dict) -> tuple[bool, str]:
    try:
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        conn.execute("""
            INSERT INTO collateral (
                asset_class, symbol, name, sub_type, quantity, market_price,
                currency, haircut_pct, custodian, source, status, created_at, updated_at
            ) VALUES (
                :asset_class, :symbol, :name, :sub_type, :quantity, :market_price,
                :currency, :haircut_pct, :custodian, :source, :status, :created_at, :updated_at
            )
        """, {
            "asset_class":  data.get("asset_class"),
            "symbol":       data.get("symbol", "").upper(),
            "name":         data.get("name"),
            "sub_type":     data.get("sub_type"),
            "quantity":     data.get("quantity", 0),
            "market_price": data.get("market_price", 0),
            "currency":     data.get("currency", "USD"),
            "haircut_pct":  data.get("haircut_pct", 10.0),
            "custodian":    data.get("custodian", "IBKR"),
            "source":       data.get("source", "manual"),
            "status":       "active",
            "created_at":   now,
            "updated_at":   now,
        })
        conn.commit()
        conn.close()
        return True, f"Added {data.get('symbol', '').upper()} to collateral."
    except Exception as e:
        return False, f"Error: {str(e)}"

def get_collateral() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM collateral WHERE status = 'active' ORDER BY asset_class, symbol"
    ).fetchall()
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        d["market_value"]     = round(d["quantity"] * d["market_price"], 2)
        d["collateral_value"] = round(d["market_value"] * (1 - d["haircut_pct"] / 100), 2)
        items.append(d)
    return items

def update_collateral_price(id: int, market_price: float) -> tuple[bool, str]:
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE collateral SET market_price = ?, updated_at = ? WHERE id = ?",
            (market_price, datetime.utcnow().isoformat(), id)
        )
        conn.commit()
        conn.close()
        return True, "Price updated."
    except Exception as e:
        return False, str(e)

def update_collateral(id: int, data: dict) -> tuple[bool, str]:
    try:
        conn = get_connection()
        data["updated_at"] = datetime.utcnow().isoformat()
        fields = ", ".join(f"{k} = :{k}" for k in data if k != "id")
        data["id"] = id
        conn.execute(f"UPDATE collateral SET {fields} WHERE id = :id", data)
        conn.commit()
        conn.close()
        return True, "Updated successfully."
    except Exception as e:
        return False, str(e)

def remove_collateral(id: int) -> tuple[bool, str]:
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE collateral SET status = 'inactive', updated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), id)
        )
        conn.commit()
        conn.close()
        return True, "Removed from collateral."
    except Exception as e:
        return False, str(e)

def get_collateral_summary() -> dict:
    items = get_collateral()
    if not items:
        return {"total_market_value": 0, "total_collateral_value": 0, "by_asset_class": {}, "items": []}
    total_mv = sum(i["market_value"]     for i in items)
    total_cv = sum(i["collateral_value"] for i in items)
    by_class = {}
    for i in items:
        ac = i["asset_class"]
        if ac not in by_class:
            by_class[ac] = {"market_value": 0, "collateral_value": 0, "count": 0}
        by_class[ac]["market_value"]     += i["market_value"]
        by_class[ac]["collateral_value"] += i["collateral_value"]
        by_class[ac]["count"]            += 1
    return {
        "total_market_value":     round(total_mv, 2),
        "total_collateral_value": round(total_cv, 2),
        "avg_haircut_pct":        round((1 - total_cv / total_mv) * 100, 2) if total_mv > 0 else 0,
        "by_asset_class":         by_class,
        "items":                  items,
    }

init_collateral_db()