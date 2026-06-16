import json
import math
import random

ASSET_VOLATILITY = {
    'equity':            0.20,
    'equity_futures':    0.18,
    'equity_options':    0.25,
    'commodity_futures': 0.22,
    'crypto':            0.65,
    'fixed_income':      0.06,
    'fx':                0.10
}

Z_SCORES = {'95': 1.645, '99': 2.326}

def get_asset_class(symbol: str) -> str:
    mapping = {
        'ES': 'equity_futures', 'NQ': 'equity_futures', 'YM': 'equity_futures',
        'CL': 'commodity_futures', 'GC': 'commodity_futures',
        'SI': 'commodity_futures', 'HO': 'commodity_futures',
        'ZN': 'fixed_income', 'ZB': 'fixed_income',
        'BTC': 'crypto', 'ETH': 'crypto'
    }
    return mapping.get(symbol.upper(), 'equity')

def calculate_parametric_var(positions: list) -> dict:
    results = []
    portfolio_variance = 0.0
    total_value = 0.0

    for pos in positions:
        symbol       = pos.get('symbol', '')
        quantity     = pos.get('quantity', 0)
        price        = pos.get('price', 0.0)
        asset_class  = get_asset_class(symbol)
        position_value = abs(quantity * price)
        daily_vol    = ASSET_VOLATILITY.get(asset_class, 0.20) / math.sqrt(252)
        annual_vol   = ASSET_VOLATILITY.get(asset_class, 0.20)

        var_95_1d  = position_value * daily_vol  * Z_SCORES['95']
        var_99_1d  = position_value * daily_vol  * Z_SCORES['99']
        var_95_10d = var_95_1d * math.sqrt(10)
        var_99_10d = var_99_1d * math.sqrt(10)

        results.append({
            'symbol':          symbol,
            'asset_class':     asset_class,
            'position_value':  round(position_value, 2),
            'annual_vol_pct':  round(annual_vol * 100, 2),
            'daily_vol_pct':   round(daily_vol * 100, 4),
            'z_score_95':      Z_SCORES['95'],
            'z_score_99':      Z_SCORES['99'],
            'var_95_1d':       round(var_95_1d, 2),
            'var_99_1d':       round(var_99_1d, 2),
            'var_95_10d':      round(var_95_10d, 2),
            'var_99_10d':      round(var_99_10d, 2),
            'calculation': {
                'formula':     'VaR = Position Value x Daily Vol x Z-Score',
                'daily_vol':   'Annual Vol (' + str(round(annual_vol*100,1)) + '%) / sqrt(252) = ' + str(round(daily_vol*100,4)) + '%',
                'var_95_1d':   str(round(position_value,2)) + ' x ' + str(round(daily_vol,6)) + ' x ' + str(Z_SCORES['95']) + ' = ' + str(round(var_95_1d,2)),
                'var_99_1d':   str(round(position_value,2)) + ' x ' + str(round(daily_vol,6)) + ' x ' + str(Z_SCORES['99']) + ' = ' + str(round(var_99_1d,2)),
                'var_10d':     '1-day VaR x sqrt(10) = ' + str(round(var_95_1d,2)) + ' x ' + str(round(math.sqrt(10),4)) + ' = ' + str(round(var_95_10d,2))
            }
        })
        portfolio_variance += (position_value * daily_vol) ** 2
        total_value += position_value

    portfolio_daily_vol = math.sqrt(portfolio_variance)
    port_var_95_1d  = portfolio_daily_vol * Z_SCORES['95']
    port_var_99_1d  = portfolio_daily_vol * Z_SCORES['99']
    port_var_95_10d = port_var_95_1d * math.sqrt(10)
    port_var_99_10d = port_var_99_1d * math.sqrt(10)

    return {
        'method':          'Parametric (Variance-Covariance)',
        'positions':       results,
        'portfolio': {
            'total_value':     round(total_value, 2),
            'portfolio_daily_vol': round(portfolio_daily_vol, 2),
            'var_95_1d':       round(port_var_95_1d, 2),
            'var_99_1d':       round(port_var_99_1d, 2),
            'var_95_10d':      round(port_var_95_10d, 2),
            'var_99_10d':      round(port_var_99_10d, 2),
            'calculation': {
                'step1': 'Portfolio Daily Vol = sqrt(sum of (position_value x daily_vol)^2) = ' + str(round(portfolio_daily_vol, 2)),
                'step2': 'VaR 95% 1D = ' + str(round(portfolio_daily_vol,2)) + ' x ' + str(Z_SCORES['95']) + ' = ' + str(round(port_var_95_1d,2)),
                'step3': 'VaR 99% 1D = ' + str(round(portfolio_daily_vol,2)) + ' x ' + str(Z_SCORES['99']) + ' = ' + str(round(port_var_99_1d,2)),
                'step4': 'VaR 95% 10D = ' + str(round(port_var_95_1d,2)) + ' x sqrt(10) = ' + str(round(port_var_95_10d,2))
            }
        }
    }

def calculate_historical_var(positions: list, simulations: int = 1000) -> dict:
    random.seed(42)
    portfolio_losses = []

    for _ in range(simulations):
        sim_loss = 0.0
        for pos in positions:
            symbol        = pos.get('symbol', '')
            quantity      = pos.get('quantity', 0)
            price         = pos.get('price', 0.0)
            asset_class   = get_asset_class(symbol)
            daily_vol     = ASSET_VOLATILITY.get(asset_class, 0.20) / math.sqrt(252)
            position_value = quantity * price
            u = random.gauss(0, 1)
            daily_return  = daily_vol * u
            sim_loss     -= position_value * daily_return
        portfolio_losses.append(sim_loss)

    portfolio_losses.sort()
    n = len(portfolio_losses)
    idx_95 = int(n * 0.95)
    idx_99 = int(n * 0.99)

    losses_above_95 = portfolio_losses[idx_95:]
    losses_above_99 = portfolio_losses[idx_99:]
    es_95 = sum(losses_above_95) / len(losses_above_95) if losses_above_95 else 0
    es_99 = sum(losses_above_99) / len(losses_above_99) if losses_above_99 else 0

    worst_10 = portfolio_losses[-10:]

    return {
        'method':       'Historical Simulation (Monte Carlo)',
        'simulations':  simulations,
        'var_95_1d':    round(portfolio_losses[idx_95], 2),
        'var_99_1d':    round(portfolio_losses[idx_99], 2),
        'es_95':        round(es_95, 2),
        'es_99':        round(es_99, 2),
        'worst_10':     [round(x, 2) for x in worst_10],
        'calculation': {
            'step1': 'Simulated ' + str(simulations) + ' daily P&L scenarios using asset class volatilities',
            'step2': 'Sorted all losses from worst to best',
            'step3': 'VaR 95% = loss at 950th percentile = ' + str(round(portfolio_losses[idx_95], 2)),
            'step4': 'VaR 99% = loss at 990th percentile = ' + str(round(portfolio_losses[idx_99], 2)),
            'step5': 'ES 95% = average of worst 50 losses = ' + str(round(es_95, 2)),
            'step6': 'ES 99% = average of worst 10 losses = ' + str(round(es_99, 2))
        },
        'loss_distribution': {
            'p10': round(portfolio_losses[int(n*0.10)], 2),
            'p25': round(portfolio_losses[int(n*0.25)], 2),
            'p50': round(portfolio_losses[int(n*0.50)], 2),
            'p75': round(portfolio_losses[int(n*0.75)], 2),
            'p90': round(portfolio_losses[int(n*0.90)], 2),
            'p95': round(portfolio_losses[idx_95], 2),
            'p99': round(portfolio_losses[idx_99], 2)
        }
    }