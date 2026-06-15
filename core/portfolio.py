from datetime import datetime

def calculate_pnl(positions: list) -> list:
    enriched = []
    for pos in positions:
        quantity    = pos.get('quantity', 0)
        entry_price = pos.get('entry_price', 0.0)
        current_price = pos.get('price', 0.0)
        pnl = (current_price - entry_price) * quantity
        pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price else 0.0

        enriched.append({
            **pos,
            'pnl':     round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
            'market_value': round(quantity * current_price, 2)
        })
    return enriched

def calculate_portfolio_summary(positions: list) -> dict:
    if not positions:
        return {
            'total_market_value': 0.0,
            'total_pnl':          0.0,
            'total_cost_basis':   0.0,
            'num_positions':      0,
            'winners':            0,
            'losers':             0,
            'as_of':              datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    enriched = calculate_pnl(positions)
    total_market_value = sum(p['market_value'] for p in enriched)
    total_cost_basis   = sum(p['quantity'] * p.get('entry_price', 0) for p in enriched)
    total_pnl          = sum(p['pnl'] for p in enriched)
    winners            = sum(1 for p in enriched if p['pnl'] > 0)
    losers             = sum(1 for p in enriched if p['pnl'] < 0)

    return {
        'total_market_value': round(total_market_value, 2),
        'total_pnl':          round(total_pnl, 2),
        'total_cost_basis':   round(total_cost_basis, 2),
        'num_positions':      len(enriched),
        'winners':            winners,
        'losers':             losers,
        'as_of':              datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def get_position_weights(positions: list) -> list:
    enriched = calculate_pnl(positions)
    total_value = sum(abs(p['market_value']) for p in enriched)
    if total_value == 0:
        return enriched
    for p in enriched:
        p['weight_pct'] = round(abs(p['market_value']) / total_value * 100, 2)
    return enriched

def add_position(positions: list, new_position: dict) -> list:
    new_position['id'] = len(positions) + 1
    new_position['added_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    positions.append(new_position)
    return positions

def remove_position(positions: list, symbol: str) -> list:
    return [p for p in positions if p.get('symbol', '').upper() != symbol.upper()]

def update_position_price(positions: list, symbol: str, new_price: float) -> list:
    for p in positions:
        if p.get('symbol', '').upper() == symbol.upper():
            p['price'] = new_price
    return positions
