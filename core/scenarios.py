PREDEFINED_SCENARIOS = {
    '2008 Financial Crisis': {
        'description': 'Global financial crisis, Lehman collapse, credit freeze',
        'shocks': {
            'equity': -0.45, 'equity_futures': -0.42, 'equity_options': -0.50,
            'commodity_futures': -0.35, 'crypto': -0.60, 'fixed_income': 0.12, 'fx': -0.08,
            'STK': -0.45, 'FUT': -0.42, 'OPT': -0.50, 'CRYPTO': -0.60, 'BOND': 0.12,
        }
    },
    'COVID Crash 2020': {
        'description': 'Pandemic onset, fastest 30% market decline in history',
        'shocks': {
            'equity': -0.34, 'equity_futures': -0.32, 'equity_options': -0.40,
            'commodity_futures': -0.28, 'crypto': -0.50, 'fixed_income': 0.08, 'fx': -0.05,
            'STK': -0.34, 'FUT': -0.32, 'OPT': -0.40, 'CRYPTO': -0.50, 'BOND': 0.08,
        }
    },
    'Rate Shock 2022': {
        'description': 'Fed aggressive rate hikes, bond market selloff',
        'shocks': {
            'equity': -0.25, 'equity_futures': -0.22, 'equity_options': -0.30,
            'commodity_futures': 0.15, 'crypto': -0.65, 'fixed_income': -0.18, 'fx': 0.08,
            'STK': -0.25, 'FUT': -0.22, 'OPT': -0.30, 'CRYPTO': -0.65, 'BOND': -0.18,
        }
    },
    'Crypto Winter 2022': {
        'description': 'FTX collapse, crypto contagion, digital asset selloff',
        'shocks': {
            'equity': -0.05, 'equity_futures': -0.04, 'equity_options': -0.08,
            'commodity_futures': -0.03, 'crypto': -0.75, 'fixed_income': 0.02, 'fx': -0.02,
            'STK': -0.05, 'FUT': -0.04, 'OPT': -0.08, 'CRYPTO': -0.75, 'BOND': 0.02,
        }
    },
    'Tech Selloff': {
        'description': 'Nasdaq correction, growth stock rotation to value',
        'shocks': {
            'equity': -0.15, 'equity_futures': -0.20, 'equity_options': -0.25,
            'commodity_futures': 0.05, 'crypto': -0.30, 'fixed_income': 0.04, 'fx': -0.02,
            'STK': -0.15, 'FUT': -0.20, 'OPT': -0.25, 'CRYPTO': -0.30, 'BOND': 0.04,
        }
    },
    'Oil Shock': {
        'description': 'Geopolitical supply disruption, crude +40%, energy inflation',
        'shocks': {
            'equity': -0.10, 'equity_futures': -0.08, 'equity_options': -0.12,
            'commodity_futures': 0.40, 'crypto': -0.15, 'fixed_income': -0.05, 'fx': 0.03,
            'STK': -0.10, 'FUT': 0.40, 'OPT': -0.12, 'CRYPTO': -0.15, 'BOND': -0.05,
        }
    },
    'Gold Rally': {
        'description': 'Flight to safety, gold +20%, equities fall',
        'shocks': {
            'equity': -0.12, 'equity_futures': -0.10, 'equity_options': -0.15,
            'commodity_futures': 0.20, 'crypto': -0.10, 'fixed_income': 0.05, 'fx': -0.03,
            'STK': -0.12, 'FUT': 0.20, 'OPT': -0.15, 'CRYPTO': -0.10, 'BOND': 0.05,
        }
    },
}

SYMBOL_AC_MAP = {
    'ES': 'equity_futures', 'NQ': 'equity_futures', 'YM': 'equity_futures',
    'CL': 'commodity_futures', 'GC': 'commodity_futures',
    'SI': 'commodity_futures', 'HO': 'commodity_futures',
    'ZN': 'fixed_income', 'ZB': 'fixed_income',
    'BTC': 'crypto', 'ETH': 'crypto',
}

def get_asset_class(pos: dict) -> str:
    return pos.get('asset_class') or SYMBOL_AC_MAP.get(pos.get('symbol','').upper(), 'equity')

def run_scenario(positions: list, scenario_name: str, custom_shocks: dict = None) -> dict:
    if custom_shocks:
        shocks      = custom_shocks
        description = 'Custom scenario with user-defined shocks'
    else:
        scenario    = PREDEFINED_SCENARIOS.get(scenario_name, {})
        shocks      = scenario.get('shocks', {})
        description = scenario.get('description', '')

    position_results = []
    total_pnl_impact = 0.0

    for pos in positions:
        symbol        = pos.get('symbol', '')
        quantity      = pos.get('quantity', 0)
        price         = pos.get('current_price') or pos.get('price', 0) or 0
        asset_class   = get_asset_class(pos)
        side          = (pos.get('side') or 'LONG').upper()
        direction     = 1 if side in ('LONG', 'BUY') else -1
        shock_pct     = shocks.get(asset_class, 0.0)
        mult          = pos.get('multiplier', 1) or 1
        cs            = pos.get('contract_size', 1) or 1

        shocked_price  = price * (1 + shock_pct)
        # For SHORT positions, a price drop is a gain
        pnl_impact     = direction * quantity * (shocked_price - price) * mult * cs
        position_value = quantity * price * mult * cs

        position_results.append({
            'symbol':         symbol,
            'asset_class':    asset_class,
            'side':           side,
            'quantity':       quantity,
            'current_price':  price,
            'shock_pct':      round(shock_pct * 100, 1),
            'shocked_price':  round(shocked_price, 4),
            'position_value': round(position_value, 2),
            'pnl_impact':     round(pnl_impact, 2),
            'calculation':    (f'{direction} × {quantity} × ({shocked_price:.4f} - {price:.4f})'
                               f' × {mult} × {cs} = {pnl_impact:,.2f}'),
        })
        total_pnl_impact += pnl_impact

    return {
        'scenario_name':    scenario_name,
        'description':      description,
        'shocks_applied':   {k: f'{v*100:.1f}%' for k, v in shocks.items()
                             if k in set(get_asset_class(p) for p in positions)},
        'positions':        position_results,
        'total_pnl_impact': round(total_pnl_impact, 2),
        'worst_position':   min(position_results, key=lambda x: x['pnl_impact'])['symbol'] if position_results else '',
        'best_position':    max(position_results, key=lambda x: x['pnl_impact'])['symbol'] if position_results else '',
    }

def run_all_scenarios(positions: list) -> list:
    return [run_scenario(positions, name) for name in PREDEFINED_SCENARIOS]

def get_scenario_names() -> list:
    return list(PREDEFINED_SCENARIOS.keys())

def get_scenario_shocks(scenario_name: str) -> dict:
    return PREDEFINED_SCENARIOS.get(scenario_name, {}).get('shocks', {})