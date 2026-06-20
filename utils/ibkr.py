import requests
import urllib3
import os
from dotenv import load_dotenv

urllib3.disable_warnings()
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

IBKR_BASE_URL = os.getenv("IBKR_BASE_URL", "https://localhost:5000/v1/api")
IBKR_ACCOUNT  = os.getenv("IBKR_ACCOUNT_ID", "U26593584")

def get_session():
    s = requests.Session()
    s.verify = False
    r1 = s.get(IBKR_BASE_URL + "/tickle")
    s.cookies.clear()
    for cookie in r1.cookies:
        s.cookies.set(cookie.name, cookie.value)
    s.post(IBKR_BASE_URL + "/iserver/auth/ssodh/init", json={"publish": True, "compete": True})
    return s

def get(endpoint, params=None):
    try:
        s = get_session()
        resp = s.get(IBKR_BASE_URL + endpoint, params=params)
        if resp.text:
            return resp.json()
        return {}
    except Exception as e:
        print("IBKR GET error:", str(e))
        return {}

def post(endpoint, body=None):
    try:
        s = get_session()
        resp = s.post(IBKR_BASE_URL + endpoint, json=body)
        if resp.text:
            return resp.json()
        return {}
    except Exception as e:
        print("IBKR POST error:", str(e))
        return {}

def get_conid(symbol: str) -> int:
    s = get_session()
    resp = s.get(IBKR_BASE_URL + "/iserver/secdef/search", params={"symbol": symbol, "name": False, "secType": "STK"})
    data = resp.json()
    if isinstance(data, list) and len(data) > 0:
        return int(data[0].get("conid"))
    return None

def get_account_summary() -> dict:
    # /portfolio/summary returns null values for paper accounts on CP Gateway —
    # use /portfolio/ledger instead which has the same data in a flat structure
    data = get("/portfolio/" + IBKR_ACCOUNT + "/ledger")
    usd = data.get("USD", data.get("BASE", {}))
    return {
        "availablefunds":     {"value": usd.get("availablefunds",    usd.get("settledcash")),        "currency": "USD"},
        "buyingpower":        {"value": usd.get("buyingpower",       usd.get("settledcash")),        "currency": "USD"},
        "netliquidation":     {"value": usd.get("netliquidationvalue"),                              "currency": "USD"},
        "totalcashvalue":     {"value": usd.get("cashbalance",       usd.get("settledcash")),        "currency": "USD"},
        "initmarginreq":      {"value": usd.get("initmarginreq",     0),                             "currency": "USD"},
        "maintmarginreq":     {"value": usd.get("maintmarginreq",    0),                             "currency": "USD"},
        "excessliquidity":    {"value": usd.get("excessliquidity",   usd.get("settledcash")),        "currency": "USD"},
        "grosspositionvalue": {"value": usd.get("stockmarketvalue",  0),                             "currency": "USD"},
    }

def get_margin_requirements() -> dict:
    summary = get_account_summary()
    return {
        "initial_margin":       summary.get("initmarginreq", {}).get("value"),
        "maintenance_margin":   summary.get("maintmarginreq", {}).get("value"),
        "buying_power":         summary.get("buyingpower", {}).get("value"),
        "available_funds":      summary.get("availablefunds", {}).get("value"),
        "excess_liquidity":     summary.get("excessliquidity", {}).get("value"),
        "net_liquidation":      summary.get("netliquidation", {}).get("value"),
        "gross_position_value": summary.get("grosspositionvalue", {}).get("value")
    }

def get_positions() -> list:
    data = get("/portfolio/" + IBKR_ACCOUNT + "/positions/0")
    if not isinstance(data, list):
        return []
    asset_class_map = {
        "STK": "equity", "OPT": "equity_options", "FUT": "equity_futures",
        "CRYPTO": "crypto", "BOND": "fixed_income", "FX": "fx"
    }
    positions = []
    for item in data:
        symbol       = item.get("ticker", item.get("contractDesc", ""))
        qty          = float(item.get("position", 0))
        avg_cost     = float(item.get("avgCost", 0))
        market_price = float(item.get("mktPrice", avg_cost))
        market_value = float(item.get("mktValue", qty * market_price))
        unrealized   = float(item.get("unrealizedPnl", 0))
        asset_class  = item.get("assetClass", "STK")
        positions.append({
            "symbol":        symbol,
            "quantity":      qty,
            "entry_price":   round(avg_cost, 2),
            "price":         round(market_price, 2),
            "market_value":  round(market_value, 2),
            "unrealized_pnl": round(unrealized, 2),
            "asset_class":   asset_class_map.get(asset_class, "equity"),
            "source":        "ibkr"
        })
    return positions

def get_stock_price(symbol: str) -> float:
    conid = get_conid(symbol)
    if not conid:
        return 0.0
    s = get_session()
    data = s.get(IBKR_BASE_URL + "/iserver/marketdata/snapshot",
                 params={"conids": str(conid), "fields": "31,84,86"}).json()
    if isinstance(data, list) and len(data) > 0:
        try:
            return float(data[0].get("31", 0))
        except:
            return 0.0
    return 0.0

def _clean_num(v):
    import re as _re
    if v is None:
        return None
    m = _re.search(r"-?[\d,]+\.?\d*", str(v))
    return float(m.group().replace(",", "")) if m else None

def whatif_order(symbol: str, quantity: int, order_type: str = "MKT", side: str = "BUY", price: float = 0.0) -> dict:
    # Self-contained session — proven pattern: fresh session per call
    s = requests.Session()
    s.verify = False
    r1 = s.get(IBKR_BASE_URL + "/tickle")
    s.cookies.clear()
    for c in r1.cookies:
        s.cookies.set(c.name, c.value)
    s.post(IBKR_BASE_URL + "/iserver/auth/ssodh/init", json={"publish": True, "compete": True})
    s.get(IBKR_BASE_URL + "/iserver/accounts")  # warm-up: order endpoints need this once per session

    conid_resp = s.get(IBKR_BASE_URL + "/iserver/secdef/search",
                       params={"symbol": symbol, "name": False, "secType": "STK"})
    conid_data = conid_resp.json()
    if not isinstance(conid_data, list) or not conid_data:
        return {"error": "Could not find contract ID for " + symbol}
    conid = int(conid_data[0]["conid"])  # CP returns conid as a quoted string; body needs int

    # Prime market data — first snapshot is usually empty, second call gets a price
    s.get(IBKR_BASE_URL + "/iserver/marketdata/snapshot", params={"conids": str(conid), "fields": "31,84,86"})
    s.get(IBKR_BASE_URL + "/iserver/marketdata/snapshot", params={"conids": str(conid), "fields": "31,84,86"})

    body = {"orders": [{"acctId": IBKR_ACCOUNT, "conid": conid,
                        "orderType": order_type, "side": side,
                        "quantity": quantity, "tif": "DAY"}]}
    if order_type == "LMT":
        body["orders"][0]["price"] = price

    resp = s.post(IBKR_BASE_URL + "/iserver/account/" + IBKR_ACCOUNT + "/orders/whatif", json=body)
    result = resp.json() if resp.text else {}

    init   = result.get("initial")     or {}
    maint  = result.get("maintenance") or {}
    amount = result.get("amount")      or {}
    equity = result.get("equity")      or {}

    return {
        "symbol":             symbol,
        "quantity":           quantity,
        "side":               side,
        "conid":              conid,
        "trade_amount":       _clean_num(amount.get("amount")),
        "commission":         _clean_num(amount.get("commission")),
        "current_funds":      _clean_num(equity.get("current")),
        "post_trade_funds":   _clean_num(equity.get("after")),
        "initial_margin":     _clean_num(init.get("after"))   if isinstance(init, dict) else None,
        "maintenance_margin": _clean_num(maint.get("after"))  if isinstance(maint, dict) else None,
        "margin_impact":      _clean_num(init.get("change"))  if isinstance(init, dict) else None,
        "warnings":           result.get("warn") or [],
    }