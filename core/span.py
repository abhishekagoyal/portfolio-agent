import json
import os

def load_span_params():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'span_params.json')
    with open(config_path, 'r') as f:
        return json.load(f)

def get_asset_class(symbol: str, params: dict) -> str:
    return params['asset_class_map'].get(symbol.upper(), 'equity')

def calculate_scanning_risk(symbol: str, position_value: float, params: dict) -> float:
    asset_class = get_asset_class(symbol, params)
    scan_range = params['scanning_ranges'].get(asset_class, 0.10)
    return abs(position_value) * scan_range

def calculate_spread_credit(symbol1: str, symbol2: str, margin1: float, margin2: float, params: dict) -> float:
    key1 = f"{symbol1.upper()}_{symbol2.upper()}"
    key2 = f"{symbol2.upper()}_{symbol1.upper()}"
    credit_rate = params['spread_credits'].get(key1) or params['spread_credits'].get(key2)
    if credit_rate:
        smaller_margin = min(margin1, margin2)
        return smaller_margin * credit_rate
    return 0.0

def calculate_short_option_minimum(symbol: str, num_contracts: int, params: dict) -> float:
    asset_class = get_asset_class(symbol, params)
    som_rate = params['short_option_minimum'].get(asset_class, 50)
    return num_contracts * som_rate

def calculate_portfolio_margin(positions: list) -> dict:
    params = load_span_params()
    results = {
        'positions': [],
        'total_scanning_risk': 0.0,
        'total_spread_credits': 0.0,
        'total_som': 0.0,
        'net_margin_requirement': 0.0
    }

    position_margins = {}

    for pos in positions:
        symbol        = pos.get('symbol', '')
        quantity      = pos.get('quantity', 0)
        price         = pos.get('price', 0.0)
        is_short_opt  = pos.get('is_short_option', False)
        position_value = quantity * price

        scanning_risk = calculate_scanning_risk(symbol, position_value, params)
        som = calculate_short_option_minimum(symbol, abs(quantity), params) if is_short_opt else 0.0
        margin = max(scanning_risk, som)

        position_margins[symbol] = margin
        results['total_scanning_risk'] += scanning_risk
        results['total_som'] += som

        results['positions'].append({
            'symbol':        symbol,
            'quantity':      quantity,
            'price':         price,
            'position_value': position_value,
            'asset_class':   get_asset_class(symbol, params),
            'scanning_risk': round(scanning_risk, 2),
            'som':           round(som, 2),
            'margin':        round(margin, 2)
        })

    symbols = list(position_margins.keys())
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            s1, s2 = symbols[i], symbols[j]
            credit = calculate_spread_credit(
                s1, s2,
                position_margins[s1],
                position_margins[s2],
                params
            )
            if credit > 0:
                results['total_spread_credits'] += credit

    results['total_scanning_risk']  = round(results['total_scanning_risk'], 2)
    results['total_spread_credits'] = round(results['total_spread_credits'], 2)
    results['total_som']            = round(results['total_som'], 2)
    results['net_margin_requirement'] = round(
        results['total_scanning_risk'] - results['total_spread_credits'], 2
    )

    return results
