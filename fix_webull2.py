import os

with open('utils/webull.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''def get_multiple_quotes(symbols: list) -> dict:
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

new = '''def get_multiple_quotes(symbols: list) -> dict:
    prices = {}
    for symbol in symbols:
        try:
            price = get_stock_quote(symbol)
            if price > 0:
                prices[symbol] = price
        except Exception as e:
            print('Quote error for ' + symbol + ': ' + str(e))
    return prices'''

content = content.replace(old, new)
with open('utils/webull.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
