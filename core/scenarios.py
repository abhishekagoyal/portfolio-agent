PREDEFINED_SCENARIOS = {
    '2008 Financial Crisis': {
        'description': 'Global financial crisis, Lehman collapse, credit freeze',
        'shocks': {
            'equity':            -0.45,
            'equity_futures':    -0.42,
            'equity_options':    -0.50,
            'commodity_futures': -0.35,
            'crypto':            -0.60,
            'fixed_income':       0.12,
            'fx':                -0.08
        }
    },
    'COVID Crash 2020': {
        'description': 'Pandemic onset, fastest 30% market decline in history',
        'shocks': {
            'equity':            -0.34,
            'equity_futures':    -0.32,
            'equity_options':    -0.40,
            'commodity_futures': -0.28,
            'crypto':            -0.50,
            'fixed_income':       0.08,
            'fx':                -0.05
        }
    },
    'Rate Shock 2022': {
        'description': 'Fed aggressive rate hikes, bond market selloff',
        'shocks': {
            'equity':            -0.25,
            'equity_futures':    -0.22,
            'equity_options':    -0.30,
            'commodity_futures':  0.15,
            'crypto':            -0.65,
            'fixed_income':      -0.18,
            'fx':                 0.08
        }
    },
    'Crypto Winter 2022': {
        'description': 'FTX collapse, crypto contagion, digital asset selloff',
        'shocks': {
            'equity':            -0.05,
            'equity_futures':    -0.04,
            'equity_options':    -0.08,
            'commodity_futures': -0.03,
            'crypto':            -0.75,
            'fixed_income':       0.02,
            'fx':                -0.02
        }
    },
    'Tech Selloff': {
        'description': 'Nasdaq correction, growth stock rotation to value',
        'shocks': {
            'equity':            -0.15,
            'equity_futures':    -0.20,
            'equity_options':    -0.25,
            'commodity_futures':  0.05,
            'crypto':            -0.30,
            'fixed_income':       0.04,
            'fx':                -0.02
        }
    }
}

ASSET_CLASS_MAP = {
    'ES': 'equity_futures', 'NQ': 'equity_futures', 'YM': 'equity_futures',
    'CL': 'commodity_futures', 'GC': 'commodity_futures',
    'SI': 'commodity_futures', 'HO': 'commodity_futures',
    'ZN': 'fixed_income', 'ZB': 'fixed_income',
    'BTC': 'crypto', 'ETH': 'crypto'
}

def get_asset_class(symbol: str) -> str:
    return ASSET_CLASS_MAP.get(symbol.upper(), 'equity')

def run_scenario(positions: list, scenario_name: str, custom_shocks: dict = None) -> dict:
    if custom_shocks:
        shocks = custom_shocks
        description = 'Custom scenario with user-defined shocks'
    else:
        scenario = PREDEFINED_SCENARIOS.get(scenario_name, {})
        shocks = scenario.get('shocks', {})
        description = scenario.get('description', '')

    position_results = []
    total_pnl_impact = 0.0

    for pos in positions:
        symbol        = pos.get('symbol', '')
        quantity      = pos.get('quantity', 0)
        price         = pos.get('price', 0.0)
        entry_price   = pos.get('entry_price', price)
        asset_class   = get_asset_class(symbol)
        shock_pct     = shocks.get(asset_class, 0.0)
        position_value = quantity * price
        shocked_price  = price * (1 + shock_pct)
        pnl_impact     = quantity * (shocked_price - price)

        position_results.append({
            'symbol':          symbol,
            'asset_class':     asset_class,
            'quantity':        quantity,
            'current_price':   price,
            'shock_pct':       round(shock_pct * 100, 1),
            'shocked_price':   round(shocked_price, 2),
            'position_value':  round(position_value, 2),
            'pnl_impact':      round(pnl_impact, 2),
            'calculation':     str(quantity) + ' x (' + str(round(shocked_price,2)) + ' - ' + str(price) + ') = ' + str(round(pnl_impact,2))
        })
        total_pnl_impact += pnl_impact

    return {
        'scenario_name':    scenario_name,
        'description':      description,
        'shocks_applied':   {k: str(round(v*100,1)) + '%' for k, v in shocks.items()},
        'positions':        position_results,
        'total_pnl_impact': round(total_pnl_impact, 2),
        'worst_position':   min(position_results, key=lambda x: x['pnl_impact'])['symbol'] if position_results else '',
        'best_position':    max(position_results, key=lambda x: x['pnl_impact'])['symbol'] if position_results else ''
    }

def run_all_scenarios(positions: list) -> list:
    results = []
    for name in PREDEFINED_SCENARIOS:
        results.append(run_scenario(positions, name))
    return results

def get_scenario_names() -> list:
    return list(PREDEFINED_SCENARIOS.keys())

def get_scenario_shocks(scenario_name: str) -> dict:
    scenario = PREDEFINED_SCENARIOS.get(scenario_name, {})
    return scenario.get('shocks', {})