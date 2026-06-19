import QuantLib as ql
import math
from datetime import date

def calculate_option_price_and_greeks(
    option_type: str,
    spot_price: float,
    strike_price: float,
    expiry_days: int,
    risk_free_rate: float = 0.05,
    volatility: float = 0.20,
    dividend_yield: float = 0.0
) -> dict:
    today = ql.Date.todaysDate()
    ql.Settings.instance().evaluationDate = today
    expiry_date = today + expiry_days

    option_type_ql = ql.Option.Call if option_type.upper() == "CALL" else ql.Option.Put
    payoff = ql.PlainVanillaPayoff(option_type_ql, strike_price)
    exercise = ql.EuropeanExercise(expiry_date)
    option = ql.VanillaOption(payoff, exercise)

    spot_handle      = ql.QuoteHandle(ql.SimpleQuote(spot_price))
    rate_handle      = ql.YieldTermStructureHandle(ql.FlatForward(today, risk_free_rate, ql.Actual365Fixed()))
    div_handle       = ql.YieldTermStructureHandle(ql.FlatForward(today, dividend_yield, ql.Actual365Fixed()))
    vol_handle       = ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.NullCalendar(), volatility, ql.Actual365Fixed()))

    bsm_process = ql.BlackScholesMertonProcess(spot_handle, div_handle, rate_handle, vol_handle)
    option.setPricingEngine(ql.AnalyticEuropeanEngine(bsm_process))

    price = option.NPV()
    delta = option.delta()
    gamma = option.gamma()
    theta = option.theta() / 365
    vega  = option.vega() / 100
    rho   = option.rho() / 100

    t = expiry_days / 365.0
    intrinsic = max(spot_price - strike_price, 0) if option_type.upper() == "CALL" else max(strike_price - spot_price, 0)
    time_value = price - intrinsic
    moneyness  = "ATM" if abs(spot_price - strike_price) / strike_price < 0.02 else ("ITM" if intrinsic > 0 else "OTM")

    return {
        "option_type":    option_type.upper(),
        "spot_price":     round(spot_price, 2),
        "strike_price":   round(strike_price, 2),
        "expiry_days":    expiry_days,
        "volatility_pct": round(volatility * 100, 2),
        "risk_free_rate": round(risk_free_rate * 100, 2),
        "price":          round(price, 4),
        "intrinsic":      round(intrinsic, 4),
        "time_value":     round(time_value, 4),
        "moneyness":      moneyness,
        "greeks": {
            "delta": round(delta, 4),
            "gamma": round(gamma, 4),
            "theta": round(theta, 4),
            "vega":  round(vega, 4),
            "rho":   round(rho, 4)
        },
        "calculation": {
            "model":       "Black-Scholes-Merton",
            "spot":        str(spot_price),
            "strike":      str(strike_price),
            "T":           str(round(t, 4)) + " years (" + str(expiry_days) + " days)",
            "vol":         str(round(volatility * 100, 1)) + "%",
            "rate":        str(round(risk_free_rate * 100, 1)) + "%",
            "price":       "Option price = $" + str(round(price, 4)),
            "delta_interp": "Position moves $" + str(round(abs(delta), 4)) + " per  move in underlying",
            "gamma_interp": "Delta changes by " + str(round(gamma, 4)) + " per  move in underlying",
            "theta_interp": "Loses $" + str(round(abs(theta), 4)) + " per day from time decay",
            "vega_interp":  "Price changes $" + str(round(vega, 4)) + " per 1% change in vol"
        }
    }

def calculate_option_margin(
    option_type: str,
    position_type: str,
    spot_price: float,
    strike_price: float,
    expiry_days: int,
    num_contracts: int,
    contract_multiplier: int = 100,
    volatility: float = 0.20,
    risk_free_rate: float = 0.05
) -> dict:
    result = calculate_option_price_and_greeks(
        option_type, spot_price, strike_price, expiry_days, risk_free_rate, volatility
    )
    option_price   = result["price"]
    delta          = abs(result["greeks"]["delta"])
    contract_value = option_price * contract_multiplier * num_contracts
    underlying_value = spot_price * contract_multiplier * num_contracts

    if position_type.upper() == "LONG":
        margin = contract_value
        margin_type = "Long Option — Full Premium"
        calculation = "Long option: pay full premium = $" + str(round(option_price, 4)) + " x " + str(contract_multiplier) + " x " + str(num_contracts) + " = $" + str(round(margin, 2))
    else:
        naked_margin_method1 = (0.20 * underlying_value) - max(strike_price - spot_price, 0) * contract_multiplier * num_contracts + contract_value
        naked_margin_method2 = (0.10 * underlying_value) + contract_value
        naked_margin = max(naked_margin_method1, naked_margin_method2)
        margin = naked_margin
        margin_type = "Short Naked Option — CBOE Rule"
        calculation = "Short option margin = max(20% x underlying - OTM amount + premium, 10% x underlying + premium)"

    return {
        "symbol":             "OPTION",
        "option_type":        option_type.upper(),
        "position_type":      position_type.upper(),
        "spot_price":         spot_price,
        "strike_price":       strike_price,
        "expiry_days":        expiry_days,
        "num_contracts":      num_contracts,
        "contract_multiplier": contract_multiplier,
        "option_price":       round(option_price, 4),
        "contract_value":     round(contract_value, 2),
        "underlying_value":   round(underlying_value, 2),
        "margin":             round(margin, 2),
        "margin_type":        margin_type,
        "delta":              round(delta, 4),
        "delta_adjusted_exposure": round(delta * underlying_value, 2),
        "calculation":        calculation,
        "greeks":             result["greeks"]
    }

def calculate_portfolio_options_margin(options_positions: list) -> dict:
    results = []
    total_margin = 0.0
    total_delta_exposure = 0.0

    for pos in options_positions:
        result = calculate_option_margin(
            option_type         = pos.get("option_type", "CALL"),
            position_type       = pos.get("position_type", "LONG"),
            spot_price          = pos.get("spot_price", 100.0),
            strike_price        = pos.get("strike_price", 100.0),
            expiry_days         = pos.get("expiry_days", 30),
            num_contracts       = pos.get("num_contracts", 1),
            contract_multiplier = pos.get("contract_multiplier", 100),
            volatility          = pos.get("volatility", 0.20),
            risk_free_rate      = pos.get("risk_free_rate", 0.05)
        )
        result["symbol"] = pos.get("symbol", "OPTION")
        results.append(result)
        total_margin += result["margin"]
        total_delta_exposure += result["delta_adjusted_exposure"]

    return {
        "positions":             results,
        "total_options_margin":  round(total_margin, 2),
        "total_delta_exposure":  round(total_delta_exposure, 2),
        "num_positions":         len(results)
    }
