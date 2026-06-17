import os

with open('utils/webull.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''def get_stock_quote(symbol: str) -> float:
    resp = call_api('GET', '/openapi/quote/v1/ticker/snapshot', {'symbol': symbol, 'exchange': 'US'})
    if resp.status_code == 200:
        data = resp.json()
        return float(data.get('last_price', data.get('close', 0)))
    return 0.0'''

new = '''def get_stock_quote(symbol: str) -> float:
    resp = call_api('GET', '/openapi/market-data/stock/snapshot', {'symbols': symbol, 'category': 'US_STOCK'})
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            return float(data[0].get('price', data[0].get('close', 0)))
        return float(data.get('price', 0))
    return 0.0

def get_multiple_quotes(symbols: list) -> dict:
    symbols_str = ','.join(symbols)
    resp = call_api('GET', '/openapi/market-data/stock/snapshot', {'symbols': symbols_str, 'category': 'US_STOCK'})
    prices = {}
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list):
            for item in data:
                sym = item.get('symbol', '')
                prices[sym] = float(item.get('price', item.get('close', 0)))
    return prices'''

content = content.replace(old, new)
with open('utils/webull.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
