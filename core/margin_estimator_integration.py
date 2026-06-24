"""
core/margin_estimator_integration.py

Wraps the tastyware/margin-estimator library for equity options margin calculation.
Uses CBOE/CME rules via the library for:
  - Single equity option legs (long/short calls and puts)
  - Multi-leg strategies (spreads, straddles, iron condors)
  - Equity shares (for covered call margin)

For futures options — falls back to our SPAN SOM (library doesn't support futures yet).
For futures — uses our SPAN per-contract engine.
For equities (no options) — uses Reg T 50%/25%.
"""

from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from typing import Optional


def _parse_expiry(expiry_str: str) -> Optional[date]:
    """Parse YYYYMMDD string to date object."""
    if not expiry_str:
        return None
    try:
        return datetime.strptime(str(expiry_str), "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _get_etf_type(symbol: str, inst: dict = None):
    """
    Determine ETFType for broad/narrow/volatility based ETFs.
    Broad-based indices (SPY, QQQ, IWM, VTI etc.) get ETFType.BROAD.
    Sector ETFs get ETFType.NARROW.
    Volatility products get ETFType.VOLATILITY.
    Individual stocks get None.
    """
    try:
        from margin_estimator import ETFType
    except ImportError:
        return None

    sym = symbol.upper()

    # Broad-based index ETFs
    broad = {"SPY", "QQQ", "IWM", "VTI", "VOO", "DIA", "MDY", "IJR",
             "IVV", "GLD", "SLV", "TLT", "EEM", "EFA", "VEA", "VWO"}
    # Volatility products
    volatility = {"VXX", "UVXY", "SVXY", "VIXY"}
    # Sector/narrow ETFs
    narrow = {"XLF", "XLE", "XLK", "XLV", "XLI", "XLB", "XLU", "XLP",
              "XLY", "XLRE", "GDX", "GDXJ", "USO", "UNG", "ARKK"}

    if sym in volatility:
        return ETFType.VOLATILITY
    if sym in broad:
        return ETFType.BROAD
    if sym in narrow:
        return ETFType.NARROW
    return None  # individual stock


def calculate_equity_option_margin(
    symbol: str,
    underlying_price: float,
    option_right: str,         # "C" or "P"
    strike: float,
    expiry: str,               # "YYYYMMDD"
    quantity: int,             # positive = long, negative = short
    option_price: float,       # premium per share
    inst: dict = None,
) -> dict:
    """
    Calculate equity option margin using tastyware/margin-estimator (CBOE rules).

    Returns dict with:
      - initial_margin: margin account requirement
      - cash_margin: cash account requirement
      - maintenance_margin: same as initial for options
      - method: description string
      - calc_detail: human-readable calculation detail
    """
    try:
        from margin_estimator import ETFType, Option, OptionType, Underlying, calculate_margin

        expiry_date = _parse_expiry(expiry)
        if not expiry_date:
            expiry_date = date(2026, 12, 19)  # default fallback

        etf_type = _get_etf_type(symbol, inst)

        underlying = Underlying(
            price=Decimal(str(round(underlying_price, 4))),
            etf_type=etf_type
        )

        opt_type = OptionType.CALL if option_right == "C" else OptionType.PUT

        leg = Option(
            expiration=expiry_date,
            price=Decimal(str(round(option_price, 4))),
            quantity=quantity,   # positive=long, negative=short
            strike=Decimal(str(round(strike, 2))),
            type=opt_type,
        )

        result = calculate_margin([leg], underlying)

        im   = float(result.margin_requirement)
        cash = float(result.cash_requirement)

        side_label = "Long" if quantity > 0 else "Short"
        right_label = "Call" if option_right == "C" else "Put"
        etf_label   = f" ({etf_type.value})" if etf_type else " (equity)"

        detail = (
            f"CBOE {side_label} {right_label} on {symbol}{etf_label}: "
            f"{abs(quantity)} contract(s) × ${option_price:.2f} premium | "
            f"Strike ${strike:.2f} | Expiry {expiry_date} | "
            f"Margin account: ${im:,.2f} | Cash account: ${cash:,.2f}"
        )

        return {
            "initial_margin":     round(im, 2),
            "maintenance_margin": round(im, 2),   # options don't have separate MM
            "cash_margin":        round(cash, 2),
            "method":             f"CBOE ({'long' if quantity>0 else 'short'} {right_label.lower()})",
            "calc_detail":        detail,
            "library":            "margin-estimator (tastyware)",
        }

    except ImportError:
        # Library not installed — fall back to simple Reg T
        multiplier = inst.get("multiplier", 100) if inst else 100
        notional   = abs(quantity) * underlying_price * float(multiplier)
        if quantity > 0:
            im = abs(quantity) * option_price * float(multiplier)
            detail = f"Reg T fallback: Long option 100% of premium ${im:,.2f}"
        else:
            im = notional * 0.20
            detail = f"Reg T fallback: Short naked option 20% × ${notional:,.2f} = ${im:,.2f}"
        return {
            "initial_margin":     round(im, 2),
            "maintenance_margin": round(im, 2),
            "cash_margin":        round(im * 2, 2),
            "method":             "Reg T (fallback — install margin-estimator)",
            "calc_detail":        detail,
            "library":            "fallback",
        }

    except Exception as e:
        # Any other error — return error info
        return {
            "initial_margin":     0,
            "maintenance_margin": 0,
            "cash_margin":        0,
            "method":             "ERROR",
            "calc_detail":        f"margin-estimator error: {str(e)}",
            "library":            "error",
        }


def calculate_multi_leg_option_margin(
    symbol: str,
    underlying_price: float,
    legs: list[dict],
    inst: dict = None,
) -> dict:
    """
    Calculate margin for multi-leg option strategies (spreads, straddles, condors).

    legs: list of dicts with keys:
      - option_right: "C" or "P"
      - strike: float
      - expiry: "YYYYMMDD"
      - quantity: int (positive=long, negative=short)
      - option_price: float (premium per share)
    """
    try:
        from margin_estimator import ETFType, Option, OptionType, Underlying, calculate_margin

        etf_type   = _get_etf_type(symbol, inst)
        underlying = Underlying(
            price=Decimal(str(round(underlying_price, 4))),
            etf_type=etf_type
        )

        option_legs = []
        for leg in legs:
            expiry_date = _parse_expiry(leg.get("expiry", "")) or date(2026, 12, 19)
            opt_type    = OptionType.CALL if leg["option_right"] == "C" else OptionType.PUT
            option_legs.append(Option(
                expiration=expiry_date,
                price=Decimal(str(round(float(leg.get("option_price", 0)), 4))),
                quantity=int(leg["quantity"]),
                strike=Decimal(str(round(float(leg["strike"]), 2))),
                type=opt_type,
            ))

        result = calculate_margin(option_legs, underlying)
        im     = float(result.margin_requirement)
        cash   = float(result.cash_requirement)

        detail = (
            f"CBOE multi-leg {symbol}: {len(legs)} legs | "
            f"Margin: ${im:,.2f} | Cash: ${cash:,.2f}"
        )

        return {
            "initial_margin":     round(im, 2),
            "maintenance_margin": round(im, 2),
            "cash_margin":        round(cash, 2),
            "method":             f"CBOE multi-leg ({len(legs)} legs)",
            "calc_detail":        detail,
            "library":            "margin-estimator (tastyware)",
        }

    except Exception as e:
        return {
            "initial_margin":     0,
            "maintenance_margin": 0,
            "cash_margin":        0,
            "method":             "ERROR",
            "calc_detail":        f"multi-leg error: {str(e)}",
            "library":            "error",
        }