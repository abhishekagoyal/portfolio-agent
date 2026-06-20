import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'span_params.json')

def load_span_params() -> dict:
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def save_span_params(params: dict):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(params, f, indent=2)

def get_asset_class(symbol: str, params: dict) -> str:
    return params['asset_class_map'].get(symbol.upper(), 'equity')

FUTURES_ASSET_CLASSES = ['equity_futures', 'commodity_futures', 'fixed_income', 'fx']
REG_T_INITIAL         = 0.50
REG_T_MAINTENANCE     = 0.25

def calculate_futures_margin(symbol: str, quantity: int, params: dict) -> dict:
    """
    Per-product SPAN margin — uses fixed dollar initial/maintenance from product_margins.
    Falls back to scanning range percentage for unknown products.
    """
    sym  = symbol.upper()
    prod = params.get('product_margins', {}).get(sym)

    if prod:
        # Official per-contract dollar margin
        contracts       = abs(quantity)
        initial         = prod['initial_margin']     * contracts
        maintenance     = prod['maintenance_margin'] * contracts
        method          = 'SPAN (per-contract)'
        calc_detail     = (f"{contracts} contracts × ${prod['initial_margin']:,} "
                           f"= ${initial:,.2f} initial / "
                           f"${prod['maintenance_margin']:,} = ${maintenance:,.2f} maint.")
    else:
        # Fallback — percentage of notional (old method)
        asset_class     = get_asset_class(sym, params)
        scan_range      = params['fallback_scanning_ranges'].get(asset_class, 0.10)
        initial         = 0   # notional not available here — caller must pass position_value
        maintenance     = 0
        method          = 'SPAN (fallback %)'
        calc_detail     = f"No per-product rate for {sym} — fallback to scanning range"

    return {
        'symbol':             sym,
        'method':             method,
        'initial_margin':     round(initial, 2),
        'maintenance_margin': round(maintenance, 2),
        'margin':             round(initial, 2),
        'calc_detail':        calc_detail,
        'per_contract_im':    prod['initial_margin']     if prod else None,
        'per_contract_mm':    prod['maintenance_margin'] if prod else None,
    }

def calculate_futures_margin_from_notional(symbol: str, position_value: float, params: dict) -> dict:
    """Fallback for unknown products — percentage of notional."""
    asset_class = get_asset_class(symbol.upper(), params)
    scan_range  = params['fallback_scanning_ranges'].get(asset_class, 0.10)
    initial     = abs(position_value) * scan_range
    maintenance = initial * 0.90
    return {
        'symbol':             symbol.upper(),
        'method':             'SPAN (fallback % of notional)',
        'initial_margin':     round(initial, 2),
        'maintenance_margin': round(maintenance, 2),
        'margin':             round(initial, 2),
        'calc_detail':        f"{abs(position_value):,.2f} × {scan_range:.0%} = {initial:,.2f}",
        'per_contract_im':    None,
        'per_contract_mm':    None,
    }

def calculate_reg_t_margin(symbol: str, position_value: float, asset_class: str,
                            params: dict = None) -> dict:
    """Reg T margin for equities — 50% initial, 25% maintenance."""
    reg_t       = (params or {}).get('reg_t', {})
    init_rate   = reg_t.get('initial',     REG_T_INITIAL)
    maint_rate  = reg_t.get('maintenance', REG_T_MAINTENANCE)
    abs_value   = abs(position_value)

    if asset_class == 'crypto':
        initial     = abs_value * 1.00
        maintenance = abs_value * 1.00
        margin_type = 'Cash (100%)'
        calc        = f"{abs_value:,.2f} × 100% = {initial:,.2f}"
    else:
        initial     = abs_value * init_rate
        maintenance = abs_value * maint_rate
        margin_type = 'Reg T'
        calc        = f"{abs_value:,.2f} × {init_rate:.0%} = {initial:,.2f}"

    return {
        'margin_type':        margin_type,
        'initial_margin':     round(initial, 2),
        'maintenance_margin': round(maintenance, 2),
        'margin':             round(initial, 2),
        'calculation':        calc,
    }

def calculate_spread_credit(symbol1: str, symbol2: str,
                             margin1: float, margin2: float, params: dict) -> float:
    key1 = symbol1.upper() + '_' + symbol2.upper()
    key2 = symbol2.upper() + '_' + symbol1.upper()
    rate = (params['spread_credits'].get(key1) or
            params['spread_credits'].get(key2))
    if rate:
        return min(margin1, margin2) * rate
    return 0.0

def calculate_short_option_minimum(symbol: str, num_contracts: int, params: dict) -> float:
    asset_class = get_asset_class(symbol, params)
    som_key     = asset_class + '_options' if 'options' not in asset_class else asset_class
    som_rate    = params['short_option_minimum'].get(som_key, 50)
    return num_contracts * som_rate

def calculate_portfolio_margin(positions: list) -> dict:
    params = load_span_params()

    results = {
        'futures_positions':          [],
        'equity_positions':           [],
        'total_scanning_risk':        0.0,
        'total_spread_credits':       0.0,
        'total_som':                  0.0,
        'total_reg_t_initial':        0.0,
        'total_reg_t_maintenance':    0.0,
        'net_futures_margin':         0.0,
        'net_equity_margin':          0.0,
        'net_margin_requirement':     0.0,
        'total_margin_requirement':   0.0,
    }

    futures_margins = {}

    for pos in positions:
        symbol         = pos.get('symbol', '').upper()
        quantity       = pos.get('quantity', 0)
        price          = pos.get('price', 0.0)
        is_short_opt   = pos.get('is_short_option', False)
        position_value = quantity * price
        asset_class    = get_asset_class(symbol, params)

        if asset_class in FUTURES_ASSET_CLASSES:
            # Try per-product SPAN first
            prod = params.get('product_margins', {}).get(symbol)
            if prod:
                span = calculate_futures_margin(symbol, quantity, params)
            else:
                span = calculate_futures_margin_from_notional(symbol, position_value, params)

            som    = calculate_short_option_minimum(symbol, abs(quantity), params) if is_short_opt else 0.0
            margin = max(span['initial_margin'], som)

            futures_margins[symbol] = margin
            results['total_scanning_risk'] += span['initial_margin']
            results['total_som']           += som

            results['futures_positions'].append({
                'symbol':             symbol,
                'asset_class':        asset_class,
                'quantity':           quantity,
                'price':              price,
                'position_value':     round(position_value, 2),
                'margin_type':        span['method'],
                'initial_margin':     span['initial_margin'],
                'maintenance_margin': span['maintenance_margin'],
                'scanning_risk':      span['initial_margin'],
                'som':                round(som, 2),
                'margin':             round(margin, 2),
                'calc_detail':        span['calc_detail'],
                'per_contract_im':    span['per_contract_im'],
                'per_contract_mm':    span['per_contract_mm'],
            })

        else:
            # Equities, ETFs, bonds held as securities → Reg T
            reg_t = calculate_reg_t_margin(symbol, position_value, asset_class, params)
            results['total_reg_t_initial']     += reg_t['initial_margin']
            results['total_reg_t_maintenance'] += reg_t['maintenance_margin']

            results['equity_positions'].append({
                'symbol':             symbol,
                'asset_class':        asset_class,
                'quantity':           quantity,
                'price':              price,
                'position_value':     round(position_value, 2),
                'margin_type':        reg_t['margin_type'],
                'initial_margin':     reg_t['initial_margin'],
                'maintenance_margin': reg_t['maintenance_margin'],
                'margin':             reg_t['initial_margin'],
                'calculation':        reg_t['calculation'],
            })

    # Spread credits across futures pairs
    symbols = list(futures_margins.keys())
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            s1, s2 = symbols[i], symbols[j]
            credit  = calculate_spread_credit(s1, s2, futures_margins[s1], futures_margins[s2], params)
            if credit > 0:
                results['total_spread_credits'] += credit

    results['total_scanning_risk']     = round(results['total_scanning_risk'], 2)
    results['total_spread_credits']    = round(results['total_spread_credits'], 2)
    results['total_som']               = round(results['total_som'], 2)
    results['total_reg_t_initial']     = round(results['total_reg_t_initial'], 2)
    results['total_reg_t_maintenance'] = round(results['total_reg_t_maintenance'], 2)
    results['net_futures_margin']      = round(
        results['total_scanning_risk'] - results['total_spread_credits'], 2)
    results['net_equity_margin']       = round(results['total_reg_t_initial'], 2)
    results['net_margin_requirement']  = round(
        results['net_futures_margin'] + results['net_equity_margin'], 2)
    results['total_margin_requirement'] = results['net_margin_requirement']

    return results