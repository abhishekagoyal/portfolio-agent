"""
core/margin_call.py
Margin Call engine — calculates IM, MM, VM status and alert levels.
"""
from datetime import datetime
from core.position_store import get_positions, get_portfolio_summary
from core.collateral_manager import get_collateral_summary


# ── Alert thresholds (as % of collateral value) ──────────────────────────
THRESHOLDS = {
    "safe":        0.20,   # Excess liquidity > 20% collateral → green
    "watch":       0.10,   # 10-20% → yellow
    "warning":     0.05,   # 5-10%  → orange
    "margin_call": 0.00,   # 0-5%   → red
    # below 0% → breach (negative excess liquidity)
}


def get_alert_level(excess_liquidity: float, collateral_value: float) -> dict:
    """Return alert level, colour, label and description."""
    if collateral_value <= 0:
        return {"level": "unknown", "color": "#888", "emoji": "⚪",
                "label": "No Collateral", "description": "No collateral on file."}

    el_pct = excess_liquidity / collateral_value

    if excess_liquidity < 0:
        return {"level": "breach", "color": "#8B0000", "emoji": "❌",
                "label": "MARGIN BREACH",
                "description": "Maintenance margin exceeds collateral value. Immediate action required."}
    elif el_pct < THRESHOLDS["margin_call"] + 0.05:
        return {"level": "margin_call", "color": "#cc3300", "emoji": "🔴",
                "label": "MARGIN CALL",
                "description": "Excess liquidity below 5% of collateral. Deposit cash or close positions."}
    elif el_pct < THRESHOLDS["watch"]:
        return {"level": "warning", "color": "#FF6600", "emoji": "🟠",
                "label": "WARNING",
                "description": "Excess liquidity 5-10% of collateral. Monitor closely."}
    elif el_pct < THRESHOLDS["safe"]:
        return {"level": "watch", "color": "#F39C12", "emoji": "🟡",
                "label": "WATCH",
                "description": "Excess liquidity 10-20% of collateral. Approaching warning zone."}
    else:
        return {"level": "safe", "color": "#2ECC71", "emoji": "🟢",
                "label": "SAFE",
                "description": "Sufficient excess liquidity. Portfolio is well margined."}


def calculate_variation_margin(positions: list) -> dict:
    """
    Calculate daily variation margin (MTM P&L) per position.
    VM = (current_price - entry_price) × qty × multiplier × contract_size × direction
    For futures this is cash settled daily.
    """
    vm_positions = []
    total_vm     = 0.0

    for p in positions:
        if p["asset_class"] not in ("FUT", "CRYPTO"):
            continue

        entry   = p.get("entry_price", 0) or 0
        curr    = p.get("current_price", 0) or entry
        qty     = p.get("quantity", 0) or 0
        mult    = p.get("multiplier", 1) or 1
        cs      = p.get("contract_size", 1) or 1
        direction = 1 if p["side"] == "LONG" else -1

        price_change = curr - entry
        vm           = direction * qty * price_change * mult * cs
        total_vm    += vm

        vm_positions.append({
            "symbol":         p["symbol"],
            "asset_class":    p["asset_class"],
            "side":           p["side"],
            "quantity":       qty,
            "entry_price":    entry,
            "current_price":  curr,
            "price_change":   round(price_change, 4),
            "vm":             round(vm, 2),
            "vm_direction":   "credit" if vm >= 0 else "debit",
        })

    return {
        "positions":  vm_positions,
        "total_vm":   round(total_vm, 2),
        "net_direction": "credit" if total_vm >= 0 else "debit",
    }


def calculate_cure_options(shortfall: float, positions: list,
                           collateral_value: float) -> dict:
    """
    Given a margin shortfall, calculate:
    1. Cash to deposit to cure
    2. Which positions to close (largest margin consumers first)
    """
    # Option 1: cash deposit needed
    cash_needed = abs(shortfall)

    # Option 2: positions to close, sorted by margin contribution (highest first)
    fut_positions = sorted(
        [p for p in positions if p["asset_class"] == "FUT"],
        key=lambda x: x.get("initial_margin", 0),
        reverse=True
    )

    close_suggestions = []
    remaining_shortfall = abs(shortfall)
    for p in fut_positions:
        if remaining_shortfall <= 0:
            break
        margin_freed = p.get("maintenance_margin", 0)
        close_suggestions.append({
            "symbol":        p["symbol"],
            "side":          p["side"],
            "quantity":      p["quantity"],
            "margin_freed":  round(margin_freed, 2),
            "notional":      round(p.get("notional_value", 0), 2),
        })
        remaining_shortfall -= margin_freed

    return {
        "cash_to_deposit":    round(cash_needed, 2),
        "close_suggestions":  close_suggestions,
        "fully_cured_by_close": remaining_shortfall <= 0,
    }


def get_margin_call_status() -> dict:
    """
    Full margin call status report combining IM, MM, VM and alert level.
    This is the main function called by the UI.
    """
    coll      = get_collateral_summary()
    port      = get_portfolio_summary()
    positions = get_positions("open")

    collateral_value = coll["total_collateral_value"]
    total_im         = port["total_initial_margin"]
    total_mm         = port["total_maintenance_margin"]

    # IM metrics
    im_available     = collateral_value - total_im
    im_utilisation   = (total_im / collateral_value * 100) if collateral_value > 0 else 0

    # MM metrics (margin call is based on MM vs collateral)
    excess_liquidity = collateral_value - total_mm
    mm_utilisation   = (total_mm / collateral_value * 100) if collateral_value > 0 else 0
    mm_buffer        = excess_liquidity  # how much collateral can drop before margin call

    # MM buffer as % needed to reach each threshold
    watch_threshold    = collateral_value * THRESHOLDS["watch"]
    warning_threshold  = collateral_value * THRESHOLDS["warning"]
    call_threshold     = collateral_value * THRESHOLDS["margin_call"]

    # Alert level based on excess liquidity
    alert = get_alert_level(excess_liquidity, collateral_value)

    # Variation margin
    vm = calculate_variation_margin(positions)

    # Cure options (only relevant if in warning/call/breach)
    cure = None
    if alert["level"] in ("margin_call", "breach", "warning"):
        shortfall = max(0, total_mm - collateral_value)
        cure = calculate_cure_options(shortfall, positions, collateral_value)

    # Per-position margin breakdown
    position_breakdown = []
    for p in positions:
        im_pct = (p["initial_margin"] / total_im * 100) if total_im > 0 else 0
        mm_pct = (p["maintenance_margin"] / total_mm * 100) if total_mm > 0 else 0
        position_breakdown.append({
            "symbol":           p["symbol"],
            "asset_class":      p["asset_class"],
            "side":             p["side"],
            "quantity":         p["quantity"],
            "notional_value":   p["notional_value"],
            "initial_margin":   p["initial_margin"],
            "maintenance_margin": p["maintenance_margin"],
            "im_pct_of_total":  round(im_pct, 1),
            "mm_pct_of_total":  round(mm_pct, 1),
            "unrealized_pnl":   p["unrealized_pnl"],
        })

    return {
        "as_of":              datetime.utcnow().isoformat(),
        "alert":              alert,

        # Collateral
        "collateral_value":   round(collateral_value, 2),
        "collateral_breakdown": coll.get("by_asset_class", {}),

        # Initial Margin
        "total_im":           round(total_im, 2),
        "im_available":       round(im_available, 2),
        "im_utilisation_pct": round(im_utilisation, 1),

        # Maintenance Margin
        "total_mm":           round(total_mm, 2),
        "excess_liquidity":   round(excess_liquidity, 2),
        "mm_utilisation_pct": round(mm_utilisation, 1),
        "mm_buffer":          round(mm_buffer, 2),

        # Thresholds
        "watch_threshold":    round(watch_threshold, 2),
        "warning_threshold":  round(warning_threshold, 2),
        "call_threshold":     round(call_threshold, 2),

        # Variation Margin
        "variation_margin":   vm,

        # Positions
        "position_breakdown": position_breakdown,

        # Cure
        "cure":               cure,
    }