import os
import hashlib
import hmac
import base64
import json
import uuid
import urllib.parse
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

APP_KEY    = os.getenv('WEBULL_APP_KEY', 'a88f2efed4dca02b9bc1a3cecbc35dba')
APP_SECRET = os.getenv('WEBULL_APP_SECRET', 'c2895b3526cc7c7588758351ddf425d6')
HOST       = 'us-openapi-alb.uat.webullbroker.com'
BASE_URL   = 'https://' + HOST

ASSET_CLASS_MAP = {
    'STK':    'equity',
    'OPT':    'equity_options',
    'FUT':    'commodity_futures',
    'CRYPTO': 'crypto',
    'ETF':    'equity',
}

def generate_signature(path, query_params, body_string, timestamp, nonce):
    signing_headers = {
        'x-app-key':             APP_KEY,
        'x-timestamp':           timestamp,
        'x-signature-algorithm': 'HMAC-SHA1',
        'x-signature-version':   '1.0',
        'x-signature-nonce':     nonce,
        'host':                  HOST,
    }
    all_params = {}
    all_params.update(query_params)
    all_params.update(signing_headers)
    str1 = '&'.join(f'{k}={all_params[k]}' for k in sorted(all_params.keys()))
    if body_string:
        str2 = hashlib.md5(body_string.encode('utf-8')).hexdigest().upper()
        str3 = f'{path}&{str1}&{str2}'
    else:
        str3 = f'{path}&{str1}'
    encoded = urllib.parse.quote(str3, safe='')
    key = f'{APP_SECRET}&'
    sig = base64.b64encode(
        hmac.new(key.encode('utf-8'), encoded.encode('utf-8'), hashlib.sha1).digest()
    ).decode('utf-8')
    return sig

def call_api(method, path, query_params=None, body=None):
    query_params = query_params or {}
    timestamp    = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    nonce        = uuid.uuid4().hex
    body_string  = json.dumps(body, separators=(',', ':')) if body else None
    signature    = generate_signature(path, query_params, body_string, timestamp, nonce)
    headers = {
        'x-app-key':             APP_KEY,
        'x-timestamp':           timestamp,
        'x-signature':           signature,
        'x-signature-algorithm': 'HMAC-SHA1',
        'x-signature-version':   '1.0',
        'x-signature-nonce':     nonce,
        'x-version':             'v2',
    }
    url = BASE_URL + path
    if method.upper() == 'GET':
        resp = requests.get(url, headers=headers, params=query_params)
    else:
        headers['Content-Type'] = 'application/json'
        resp = requests.post(url, headers=headers, data=body_string)
    return resp

def get_account_list():
    resp = call_api('GET', '/openapi/account/list')
    if resp.status_code == 200:
        return resp.json()
    return []

def get_account_positions(account_id: str) -> list:
    resp = call_api('GET', '/openapi/assets/positions', {'account_id': account_id})
    if resp.status_code == 200:
        data = resp.json()
        positions = []
        items = data if isinstance(data, list) else data.get('data', [])
        for item in items:
            symbol       = item.get('symbol', item.get('ticker', ''))
            qty          = float(item.get('position', item.get('qty', 0)))
            cost_price   = float(item.get('cost_price', item.get('average_cost', 0)))
            market_price = float(item.get('last_price', item.get('market_price', cost_price)))
            asset_type   = item.get('asset_type', item.get('security_type', 'STK'))
            asset_class  = ASSET_CLASS_MAP.get(asset_type, 'equity')
            positions.append({
                'symbol':          symbol,
                'quantity':        qty,
                'entry_price':     cost_price,
                'price':           market_price,
                'asset_class':     asset_class,
                'is_short_option': False,
                'source':          'webull'
            })
        return positions
    print('Positions error:', resp.status_code, resp.text)
    return []

def get_account_balance(account_id: str) -> dict:
    resp = call_api('GET', '/openapi/assets/balance', {'account_id': account_id})
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        return {
            'net_liquidation':    float(data.get('net_liquidation', data.get('netLiquidation', 0))),
            'cash':               float(data.get('cash', data.get('totalCash', 0))),
            'buying_power':       float(data.get('buying_power', data.get('buyingPower', 0))),
            'total_market_value': float(data.get('market_value', data.get('totalMarketValue', 0)))
        }
    print('Balance error:', resp.status_code, resp.text)
    return {}

def get_stock_quote(symbol: str) -> float:
    resp = call_api('GET', '/openapi/market-data/stock/snapshot', {'symbols': symbol, 'category': 'US_STOCK'})
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            return float(data[0].get('price', data[0].get('close', 0)))
        return float(data.get('price', 0))
    return 0.0

def get_multiple_quotes(symbols: list) -> dict:
    prices = {}
    for symbol in symbols:
        try:
            price = get_stock_quote(symbol)
            if price > 0:
                prices[symbol] = price
        except Exception as e:
            print('Quote error for ' + symbol + ': ' + str(e))
    return prices
