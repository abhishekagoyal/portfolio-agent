import math
import random

ASSET_VOLATILITY = {
    'equity':            0.20,
    'equity_futures':    0.18,
    'equity_options':    0.25,
    'commodity_futures': 0.22,
    'crypto':            0.65,
    'fixed_income':      0.06,
    'fx':                0.10,
    'STK':               0.20,
    'FUT':               0.18,
    'OPT':               0.25,
    'CRYPTO':            0.65,
    'BOND':              0.06,
}

Z_SCORES = {'95': 1.645, '99': 2.326}

SYMBOL_AC_MAP = {
    'ES': 'equity_futures', 'NQ': 'equity_futures', 'YM': 'equity_futures',
    'CL': 'commodity_futures', 'GC': 'commodity_futures',
    'SI': 'commodity_futures', 'HO': 'commodity_futures',
    'ZN': 'fixed_income',  'ZB': 'fixed_income',
    'BTC': 'crypto',       'ETH': 'crypto',
}

def get_asset_class(pos: dict) -> str:
    """Read asset_class from position dict (new store) or fall back to symbol map."""
    ac = pos.get('asset_class') or SYMBOL_AC_MAP.get(pos.get('symbol', '').upper(), 'equity')
    return ac

def get_position_value(pos: dict) -> float:
    """Signed position value — negative for SHORT."""
    qty   = pos.get('quantity', 0) or 0
    price = pos.get('current_price') or pos.get('price', 0) or 0
    mult  = pos.get('multiplier', 1) or 1
    cs    = pos.get('contract_size', 1) or 1
    side  = (pos.get('side') or 'LONG').upper()
    direction = 1 if side in ('LONG', 'BUY') else -1
    return direction * qty * price * mult * cs

def calculate_parametric_var(positions: list) -> dict:
    results            = []
    portfolio_variance = 0.0
    total_value        = 0.0

    for pos in positions:
        symbol         = pos.get('symbol', '')
        asset_class    = get_asset_class(pos)
        position_value = abs(get_position_value(pos))
        annual_vol     = ASSET_VOLATILITY.get(asset_class, 0.20)
        daily_vol      = annual_vol / math.sqrt(252)

        var_95_1d  = position_value * daily_vol * Z_SCORES['95']
        var_99_1d  = position_value * daily_vol * Z_SCORES['99']
        var_95_10d = var_95_1d  * math.sqrt(10)
        var_99_10d = var_99_1d  * math.sqrt(10)

        results.append({
            'symbol':         symbol,
            'asset_class':    asset_class,
            'side':           pos.get('side', 'LONG'),
            'position_value': round(position_value, 2),
            'annual_vol_pct': round(annual_vol * 100, 2),
            'daily_vol_pct':  round(daily_vol * 100, 4),
            'z_score_95':     Z_SCORES['95'],
            'z_score_99':     Z_SCORES['99'],
            'var_95_1d':      round(var_95_1d, 2),
            'var_99_1d':      round(var_99_1d, 2),
            'var_95_10d':     round(var_95_10d, 2),
            'var_99_10d':     round(var_99_10d, 2),
            'calculation': {
                'formula':  'VaR = |Position Value| × Daily Vol × Z-Score',
                'daily_vol': f'Annual Vol ({annual_vol*100:.1f}%) / sqrt(252) = {daily_vol*100:.4f}%',
                'var_95_1d': f'{position_value:,.2f} × {daily_vol:.6f} × {Z_SCORES["95"]} = {var_95_1d:,.2f}',
                'var_99_1d': f'{position_value:,.2f} × {daily_vol:.6f} × {Z_SCORES["99"]} = {var_99_1d:,.2f}',
                'var_10d':   f'1-day VaR × sqrt(10) = {var_95_1d:,.2f} × {math.sqrt(10):.4f} = {var_95_10d:,.2f}',
            }
        })
        portfolio_variance += (position_value * daily_vol) ** 2
        total_value        += position_value

    port_daily_vol  = math.sqrt(portfolio_variance)
    port_var_95_1d  = port_daily_vol * Z_SCORES['95']
    port_var_99_1d  = port_daily_vol * Z_SCORES['99']
    port_var_95_10d = port_var_95_1d * math.sqrt(10)
    port_var_99_10d = port_var_99_1d * math.sqrt(10)

    return {
        'method':    'Parametric (Variance-Covariance)',
        'positions': results,
        'portfolio': {
            'total_value':         round(total_value, 2),
            'portfolio_daily_vol': round(port_daily_vol, 2),
            'var_95_1d':           round(port_var_95_1d, 2),
            'var_99_1d':           round(port_var_99_1d, 2),
            'var_95_10d':          round(port_var_95_10d, 2),
            'var_99_10d':          round(port_var_99_10d, 2),
            'calculation': {
                'step1': f'Portfolio Daily Vol = sqrt(Σ(pos_value × daily_vol)²) = {port_daily_vol:,.2f}',
                'step2': f'VaR 95% 1D = {port_daily_vol:,.2f} × {Z_SCORES["95"]} = {port_var_95_1d:,.2f}',
                'step3': f'VaR 99% 1D = {port_daily_vol:,.2f} × {Z_SCORES["99"]} = {port_var_99_1d:,.2f}',
                'step4': f'VaR 95% 10D = {port_var_95_1d:,.2f} × sqrt(10) = {port_var_95_10d:,.2f}',
            }
        }
    }

def calculate_historical_var(positions: list, simulations: int = 1000) -> dict:
    random.seed(42)
    portfolio_losses = []

    for _ in range(simulations):
        sim_loss = 0.0
        for pos in positions:
            asset_class    = get_asset_class(pos)
            daily_vol      = ASSET_VOLATILITY.get(asset_class, 0.20) / math.sqrt(252)
            position_value = get_position_value(pos)   # signed — shorts benefit from falls
            u              = random.gauss(0, 1)
            daily_return   = daily_vol * u
            sim_loss      -= position_value * daily_return
        portfolio_losses.append(sim_loss)

    portfolio_losses.sort()
    n      = len(portfolio_losses)
    idx_95 = int(n * 0.95)
    idx_99 = int(n * 0.99)

    losses_95 = portfolio_losses[idx_95:]
    losses_99 = portfolio_losses[idx_99:]
    es_95 = sum(losses_95) / len(losses_95) if losses_95 else 0
    es_99 = sum(losses_99) / len(losses_99) if losses_99 else 0

    return {
        'method':      'Historical Simulation (Monte Carlo)',
        'simulations': simulations,
        'var_95_1d':   round(portfolio_losses[idx_95], 2),
        'var_99_1d':   round(portfolio_losses[idx_99], 2),
        'es_95':       round(es_95, 2),
        'es_99':       round(es_99, 2),
        'worst_10':    [round(x, 2) for x in portfolio_losses[-10:]],
        'calculation': {
            'step1': f'Simulated {simulations} daily P&L scenarios using asset class volatilities',
            'step2': 'Sorted all losses from worst to best',
            'step3': f'VaR 95% = loss at 95th percentile = {portfolio_losses[idx_95]:,.2f}',
            'step4': f'VaR 99% = loss at 99th percentile = {portfolio_losses[idx_99]:,.2f}',
            'step5': f'ES 95% = average of worst 5% losses = {es_95:,.2f}',
            'step6': f'ES 99% = average of worst 1% losses = {es_99:,.2f}',
        },
        'loss_distribution': {
            'p10': round(portfolio_losses[int(n*0.10)], 2),
            'p25': round(portfolio_losses[int(n*0.25)], 2),
            'p50': round(portfolio_losses[int(n*0.50)], 2),
            'p75': round(portfolio_losses[int(n*0.75)], 2),
            'p90': round(portfolio_losses[int(n*0.90)], 2),
            'p95': round(portfolio_losses[idx_95], 2),
            'p99': round(portfolio_losses[idx_99], 2),
        }
    }