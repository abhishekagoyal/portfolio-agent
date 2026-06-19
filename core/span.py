import json
import os

def load_span_params():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'span_params.json')
    with open(config_path, 'r') as f:
        return json.load(f)

def get_asset_class(symbol: str, params: dict) -> str:
    return params['asset_class_map'].get(symbol.upper(), 'equity')

FUTURES_ASSET_CLASSES = ['equity_futures', 'commodity_futures', 'fixed_income', 'fx']
EQUITY_ASSET_CLASSES  = ['equity', 'equity_options', 'crypto']

REG_T_INITIAL     = 0.50
REG_T_MAINTENANCE = 0.25
CRYPTO_INITIAL    = 1.00

def calculate_reg_t_margin(symbol: str, position_value: float, asset_class: str) -> dict:
    abs_value = abs(position_value)
    if asset_class == 'crypto':
        initial     = abs_value * CRYPTO_INITIAL
        maintenance = abs_value * CRYPTO_INITIAL
        margin_type = 'Cash (100%)'
    else:
        initial     = abs_value * REG_T_INITIAL
        maintenance = abs_value * REG_T_MAINTENANCE
        margin_type = 'Reg T'
    return {
        'margin_type':       margin_type,
        'initial_margin':    round(initial, 2),
        'maintenance_margin': round(maintenance, 2),
        'margin':            round(initial, 2),
        'calculation':       'Reg T: ' + str(round(abs_value, 2)) + ' x ' + str(REG_T_INITIAL) + ' = ' + str(round(initial, 2))
    }

def calculate_scanning_risk(symbol: str, position_value: float, params: dict) -> float:
    asset_class = get_asset_class(symbol, params)
    scan_range  = params['scanning_ranges'].get(asset_class, 0.10)
    return abs(position_value) * scan_range

def calculate_spread_credit(symbol1: str, symbol2: str, margin1: float, margin2: float, params: dict) -> float:
    key1 = symbol1.upper() + '_' + symbol2.upper()
    key2 = symbol2.upper() + '_' + symbol1.upper()
    credit_rate = params['spread_credits'].get(key1) or params['spread_credits'].get(key2)
    if credit_rate:
        return min(margin1, margin2) * credit_rate
    return 0.0

def calculate_short_option_minimum(symbol: str, num_contracts: int, params: dict) -> float:
    asset_class = get_asset_class(symbol, params)
    som_rate    = params['short_option_minimum'].get(asset_class, 50)
    return num_contracts * som_rate

def calculate_portfolio_margin(positions: list) -> dict:
    params = load_span_params()

    results = {
        'futures_positions':  [],
        'equity_positions':   [],
        'total_scanning_risk':    0.0,
        'total_spread_credits':   0.0,
        'total_som':              0.0,
        'total_reg_t_initial':    0.0,
        'total_reg_t_maintenance': 0.0,
        'net_futures_margin':     0.0,
        'net_equity_margin':      0.0,
        'total_margin_requirement': 0.0
    }

    futures_margins = {}

    for pos in positions:
        symbol         = pos.get('symbol', '')
        quantity       = pos.get('quantity', 0)
        price          = pos.get('price', 0.0)
        is_short_opt   = pos.get('is_short_option', False)
        position_value = quantity * price
        asset_class    = get_asset_class(symbol, params)

        if asset_class in FUTURES_ASSET_CLASSES:
            scanning_risk = calculate_scanning_risk(symbol, position_value, params)
            som = calculate_short_option_minimum(symbol, abs(quantity), params) if is_short_opt else 0.0
            margin = max(scanning_risk, som)
            futures_margins[symbol] = margin
            results['total_scanning_risk'] += scanning_risk
            results['total_som'] += som
            results['futures_positions'].append({
                'symbol':         symbol,
                'asset_class':    asset_class,
                'quantity':       quantity,
                'price':          price,
                'position_value': round(position_value, 2),
                'margin_type':    'SPAN',
                'scanning_risk':  round(scanning_risk, 2),
                'som':            round(som, 2),
                'margin':         round(margin, 2)
            })
        else:
            reg_t = calculate_reg_t_margin(symbol, position_value, asset_class)
            results['total_reg_t_initial']     += reg_t['initial_margin']
            results['total_reg_t_maintenance'] += reg_t['maintenance_margin']
            results['equity_positions'].append({
                'symbol':              symbol,
                'asset_class':         asset_class,
                'quantity':            quantity,
                'price':               price,
                'position_value':      round(position_value, 2),
                'margin_type':         reg_t['margin_type'],
                'initial_margin':      reg_t['initial_margin'],
                'maintenance_margin':  reg_t['maintenance_margin'],
                'margin':              reg_t['initial_margin'],
                'calculation':         reg_t['calculation']
            })

    symbols = list(futures_margins.keys())
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            s1, s2 = symbols[i], symbols[j]
            credit = calculate_spread_credit(s1, s2, futures_margins[s1], futures_margins[s2], params)
            if credit > 0:
                results['total_spread_credits'] += credit

    results['total_scanning_risk']      = round(results['total_scanning_risk'], 2)
    results['total_spread_credits']     = round(results['total_spread_credits'], 2)
    results['total_som']                = round(results['total_som'], 2)
    results['total_reg_t_initial']      = round(results['total_reg_t_initial'], 2)
    results['total_reg_t_maintenance']  = round(results['total_reg_t_maintenance'], 2)
    results['net_futures_margin']       = round(results['total_scanning_risk'] - results['total_spread_credits'], 2)
    results['net_equity_margin']        = round(results['total_reg_t_initial'], 2)
    results['total_margin_requirement'] = round(results['net_futures_margin'] + results['net_equity_margin'], 2)

    return results
