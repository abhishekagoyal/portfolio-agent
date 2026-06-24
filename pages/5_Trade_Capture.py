import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from core.security_master import search_instruments, get_instrument
from core.position_store import (
    add_position, get_positions, get_positions_by_instrument,
    get_portfolio_summary, update_position_margin,
    reduce_or_close_position, recalculate_portfolio_margins
)
from core.collateral_manager import get_collateral_summary
from core.span import calculate_portfolio_margin, load_span_params

st.set_page_config(page_title="Order Input", page_icon="🎯", layout="wide")
st.title("🎯 Order Input — Pre-Trade Margin Check")
st.caption("Select an instrument, enter order details, and check margin impact before trading.")


# ── Helper: convert position store format to span engine format ──────────
def positions_to_span_format(positions: list) -> list:
    """Convert position store records to the format span engine expects."""
    span_positions = []
    for p in positions:
        # side can be LONG/SHORT (manual) or BUY/SELL (order_input) — normalise both
        side = p.get("side", "LONG").upper()
        is_long = side in ("LONG", "BUY")
        span_positions.append({
            "symbol":          p["symbol"],
            "quantity":        p["quantity"] if is_long else -p["quantity"],
            "price":           p["current_price"] or p["entry_price"],
            "is_short_option": p.get("option_right") is not None and not is_long,
        })
    return span_positions


def net_positions(existing: list, new_symbol: str, new_qty_signed: float,
                  new_price: float) -> list:
    """
    Merge a new order into existing positions.
    new_qty_signed: positive = BUY, negative = SELL
    Returns combined list with quantities netted for same symbol.
    """
    combined = {p["symbol"]: dict(p) for p in existing}

    if new_symbol in combined:
        existing_qty = combined[new_symbol]["quantity"]
        combined[new_symbol]["quantity"] = existing_qty + new_qty_signed
        combined[new_symbol]["price"]    = new_price
        # Remove if flat
        if combined[new_symbol]["quantity"] == 0:
            del combined[new_symbol]
    else:
        combined[new_symbol] = {
            "symbol":          new_symbol,
            "quantity":        new_qty_signed,
            "price":           new_price,
            "is_short_option": False,
        }

    return list(combined.values())


def calculate_pretrade_margin_impact(
    symbol: str, asset_class: str, quantity: float,
    side: str, price: float,
    option_right: str = None,
    is_short_option: bool = False,
    existing_positions: list = None,
    inst: dict = None
) -> dict:
    """
    Calculate the MARGINAL margin impact of a new order against the existing portfolio.

    For futures: runs SPAN on combined portfolio (existing + new order netted),
    returns the difference vs current portfolio margin.

    For equities/crypto/bonds: calculates Reg T on the new order in isolation
    (netting doesn't apply under Reg T framework).
    """
    params = load_span_params()
    existing_positions = existing_positions or []
    position_value     = quantity * price

    # ── FUTURES — portfolio netting ──────────────────────────────────────
    if asset_class == "FUT":
        # Current portfolio margin
        current_span  = positions_to_span_format(existing_positions)
        current_result = calculate_portfolio_margin(current_span) if current_span else \
                         {"total_scanning_risk": 0, "total_spread_credits": 0,
                          "net_futures_margin": 0, "total_margin_requirement": 0}

        # Combined portfolio margin (existing + new order netted)
        signed_qty    = quantity if side == "BUY" else -quantity
        combined_span = net_positions(current_span, symbol, signed_qty, price)
        combined_result = calculate_portfolio_margin(combined_span)

        current_total  = current_result.get("net_futures_margin", 0)
        combined_total = combined_result.get("net_futures_margin", 0)
        margin_impact  = combined_total - current_total

        # Per-contract rate for display
        prod = params.get("product_margins", {}).get(symbol.upper(), {})
        is_long_side = side in ("BUY", "LONG")
        im_key = "long_initial"     if is_long_side else "short_initial"
        mm_key = "long_maintenance" if is_long_side else "short_maintenance"
        per_contract_im = prod.get(im_key) or prod.get("initial_margin", 0)
        per_contract_mm = prod.get(mm_key) or prod.get("maintenance_margin", 0)

        # Net position after trade
        existing_qty = sum(
            (p["quantity"] if p.get("side", "LONG").upper() in ("LONG", "BUY") else -p["quantity"])
            for p in existing_positions if p["symbol"] == symbol
        )
        net_qty = existing_qty + (quantity if side == "BUY" else -quantity)

        detail = (
            f"Existing portfolio SPAN: ${current_total:,.2f} | "
            f"Combined SPAN (net {net_qty:+.0f} {symbol}): ${combined_total:,.2f} | "
            f"Marginal impact: ${margin_impact:+,.2f}"
        )
        if combined_result.get("total_spread_credits", 0) > current_result.get("total_spread_credits", 0):
            new_credits = combined_result["total_spread_credits"] - current_result.get("total_spread_credits", 0)
            detail += f" (incl. ${new_credits:,.2f} new spread credits)"

        return {
            "initial_margin":      round(max(margin_impact, 0), 2),
            "maintenance_margin":  round(max(margin_impact * 0.91, 0), 2),
            "margin_impact":       round(margin_impact, 2),
            "method":              "SPAN (portfolio netted)",
            "calc_detail":         detail,
            "current_portfolio_margin":  round(current_total, 2),
            "combined_portfolio_margin": round(combined_total, 2),
            "per_contract_im":     per_contract_im,
            "per_contract_mm":     per_contract_mm,
            "net_qty_after":       net_qty,
        }

    # ── OPTIONS ──────────────────────────────────────────────────────────
    elif asset_class == "OPT":
        # Determine if this is an option on a futures product
        underlying_sym = (inst.get("underlying_symbol") or symbol).upper() if inst else symbol.upper()
        futures_opt_underlyings = params.get("futures_option_underlyings", [])
        is_futures_option = underlying_sym in futures_opt_underlyings

        if is_futures_option:
            # SPAN options margin from option_margins table
            opt_margins = params.get("option_margins", {}).get(underlying_sym, {})
            if is_short_option:
                im_rate = opt_margins.get("short_initial",
                          opt_margins.get("som_per_contract", 3000))
                mm_rate = opt_margins.get("short_maintenance", im_rate * 0.90)
                im      = quantity * im_rate
                mm      = quantity * mm_rate
                detail  = (f"SPAN short futures option on {underlying_sym}: "
                           f"{quantity:.0f} contracts × ${im_rate:,} = ${im:,.2f} IM | "
                           f"${mm_rate:,} = ${mm:,.2f} MM")
                method  = "SPAN (short futures option)"
            else:
                im     = abs(position_value)
                mm     = 0
                detail = (f"SPAN long futures option: 100% of premium "
                          f"${abs(position_value):,.2f} (max loss = premium paid)")
                method = "SPAN (long futures option)"
            return {"initial_margin": round(im, 2), "maintenance_margin": round(mm, 2),
                    "margin_impact": round(im, 2), "method": method,
                    "calc_detail": detail, "net_qty_after": None}
        else:
            # Equity option — use tastyware/margin-estimator (CBOE rules)
            from core.margin_estimator_integration import calculate_equity_option_margin
            strike      = float(inst.get("strike") or 0) if inst else 0
            expiry      = str(inst.get("expiry") or "") if inst else ""
            opt_right   = option_right or (inst.get("option_right") if inst else "C") or "C"
            # quantity: positive=long, negative=short
            signed_qty  = int(quantity) if not is_short_option else -int(quantity)
            result      = calculate_equity_option_margin(
                symbol           = symbol,
                underlying_price = price,   # use current price as underlying proxy
                option_right     = opt_right,
                strike           = strike or price,
                expiry           = expiry,
                quantity         = signed_qty,
                option_price     = price,   # option premium = entered price
                inst             = inst,
            )
            return {"initial_margin":     result["initial_margin"],
                    "maintenance_margin": result["maintenance_margin"],
                    "margin_impact":      result["initial_margin"],
                    "method":             result["method"],
                    "calc_detail":        result["calc_detail"],
                    "cash_margin":        result.get("cash_margin"),
                    "net_qty_after":      None}

    # ── CRYPTO ───────────────────────────────────────────────────────────
    elif asset_class == "CRYPTO":
        im     = abs(position_value)
        mm     = im
        detail = f"Crypto: 100% cash × ${abs(position_value):,.2f} = ${im:,.2f}"
        return {"initial_margin": round(im, 2), "maintenance_margin": round(mm, 2),
                "margin_impact": round(im, 2), "method": "Cash (100%)",
                "calc_detail": detail, "net_qty_after": None}

    # ── BONDS ─────────────────────────────────────────────────────────────
    elif asset_class == "BOND":
        im     = abs(position_value) * 0.10
        mm     = abs(position_value) * 0.05
        detail = f"Bond: 10% × ${abs(position_value):,.2f} = ${im:,.2f}"
        return {"initial_margin": round(im, 2), "maintenance_margin": round(mm, 2),
                "margin_impact": round(im, 2), "method": "Reg T (bond)",
                "calc_detail": detail, "net_qty_after": None}

    # ── EQUITIES (Reg T) ─────────────────────────────────────────────────
    else:
        reg_t  = params.get("reg_t", {})
        ir     = reg_t.get("initial", 0.50)
        mr     = reg_t.get("maintenance", 0.25)
        im     = abs(position_value) * ir
        mm     = abs(position_value) * mr
        detail = (f"Reg T: ${abs(position_value):,.2f} × {ir:.0%} = "
                  f"${im:,.2f} initial | × {mr:.0%} = ${mm:,.2f} maint.")
        return {"initial_margin": round(im, 2), "maintenance_margin": round(mm, 2),
                "margin_impact": round(im, 2), "method": "Reg T (equity)",
                "calc_detail": detail, "net_qty_after": None}


def get_buying_power() -> dict:
    coll        = get_collateral_summary()
    port        = get_portfolio_summary()
    total_cv    = coll["total_collateral_value"]
    margin_used = port["total_initial_margin"]
    available   = total_cv - margin_used
    return {
        "total_collateral_value": total_cv,
        "margin_used":            margin_used,
        "available_buying_power": available,
        "utilisation_pct":        round(margin_used / total_cv * 100, 1) if total_cv > 0 else 0,
    }


# ── AUTO-RECALC MARGINS ON PAGE LOAD ────────────────────────────────────
# Always recalculate futures margins on load so buying power reflects
# true netted portfolio margin, not stale stored values
if "margins_recalculated" not in st.session_state:
    recalculate_portfolio_margins()
    st.session_state["margins_recalculated"] = True

# ── CURRENT BUYING POWER PANEL ───────────────────────────────────────────
st.subheader("💰 Current Buying Power")
bp = get_buying_power()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Collateral Value", f"${bp['total_collateral_value']:,.2f}",
              help="Post-haircut collateral from Collateral Manager")
with col2:
    st.metric("Margin Currently Used",  f"${bp['margin_used']:,.2f}",
              help="Sum of initial margin on all open positions")
with col3:
    st.metric("Available Buying Power", f"${bp['available_buying_power']:,.2f}")
with col4:
    st.metric("Margin Utilisation",     f"{bp['utilisation_pct']:.1f}%")

util      = min(bp["utilisation_pct"] / 100, 1.0)
bar_color = "#2ECC71" if util < 0.6 else ("#F39C12" if util < 0.85 else "#cc3300")
st.markdown(
    f'<div style="background:#2a2a2a;border-radius:6px;height:12px;margin:4px 0 16px 0;">'
    f'<div style="background:{bar_color};width:{util*100:.1f}%;'
    f'height:12px;border-radius:6px;"></div></div>',
    unsafe_allow_html=True
)

st.markdown("---")

# ── ORDER INPUT FORM ─────────────────────────────────────────────────────
st.subheader("📋 Order Details")

all_instruments = search_instruments("", "All")
inst_map = {
    f"{i['symbol']} — {i['name'] or ''} ({i['asset_class']})": i
    for i in all_instruments
}

col1, col2 = st.columns([3, 1])
with col1:
    selected_inst_label = st.selectbox(
        "Select Instrument from Security Master *",
        ["— select —"] + list(inst_map.keys()),
        key="order_inst"
    )
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("Not listed? Add it in Security Master first.")

if selected_inst_label == "— select —":
    st.info("Select an instrument above to begin.")
    # Show open positions even when no instrument selected
    st.markdown("---")
    st.subheader("📋 Current Open Positions")
    _positions = get_positions("open")
    if not _positions:
        st.info("No open positions yet.")
    else:
        _rows = []
        for p in _positions:
            _rows.append({
                "Symbol":          p["symbol"],
                "Asset Class":     p["asset_class"],
                "Side":            p["side"],
                "Qty":             p["quantity"],
                "Entry ($)":       f"${p['entry_price']:,.4f}",
                "Notional ($)":    f"${p['notional_value']:,.2f}",
                "Init Margin ($)": f"${p['initial_margin']:,.2f}",
                "Method":          p.get("margin_method") or "—",
                "Source":          p["source"],
            })
        st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
    st.stop()

inst        = inst_map[selected_inst_label]
symbol      = inst["symbol"]
asset_class = inst["asset_class"]
margin_method = inst.get("margin_method", "REGT")

with st.expander("📄 Instrument Details", expanded=False):
    dc1, dc2, dc3, dc4, dc5 = st.columns(5)
    dc1.metric("Symbol",        symbol)
    dc2.metric("Asset Class",   asset_class)
    dc3.metric("Exchange",      inst.get("exchange") or "—")
    dc4.metric("Margin Method", margin_method)
    dc5.metric("Currency",      inst.get("currency") or "USD")
    if asset_class == "FUT":
        dc1, dc2, dc3 = st.columns(3)
        dc1.metric("Contract Size", inst.get("contract_size") or "—")
        dc2.metric("Tick Size",     inst.get("tick_size") or "—")
        dc3.metric("Tick Value",    f"${inst.get('tick_value') or 0:,.2f}")

st.markdown("")
col1, col2, col3, col4 = st.columns(4)
with col1:
    order_side  = st.selectbox("Side", ["BUY", "SELL"], key="order_side")
with col2:
    order_qty   = st.number_input("Quantity", min_value=1, value=1,
                                  step=1, key="order_qty")
with col3:
    order_price = st.number_input("Price ($)", min_value=0.0, value=0.0,
                                  step=0.01, format="%.4f", key="order_price")
with col4:
    order_type  = st.selectbox("Order Type", ["MKT", "LMT"], key="order_type")

is_short_opt = False
option_right = None
order_expiry = inst.get("expiry") or ""
order_strike = inst.get("strike") or 0.0

if asset_class == "OPT":
    col1, col2, col3 = st.columns(3)
    with col1:
        option_right = st.selectbox("Call / Put",
                                    ["C", "P"],
                                    index=0 if inst.get("option_right") != "P" else 1,
                                    key="order_opt_right")
    with col2:
        order_strike = st.number_input("Strike ($)", min_value=0.0,
                                       value=float(inst.get("strike") or 0.0),
                                       step=0.5, key="order_strike")
    with col3:
        is_short_opt = st.checkbox("Short Option (selling)?", key="order_short_opt")

if asset_class in ["FUT", "OPT"]:
    order_expiry = st.text_input("Expiry (YYYYMMDD)",
                                 value=inst.get("expiry") or "",
                                 key="order_expiry")

st.markdown("")
check_col, _ = st.columns([1, 3])
with check_col:
    run_check = st.button("🔍 Run Pre-Trade Margin Check", type="primary", key="run_check")

if run_check:
    if order_price <= 0:
        st.error("❌ Please enter a valid price.")
    else:
        with st.spinner("Calculating margin impact..."):
            existing_positions = get_positions("open")
            margin = calculate_pretrade_margin_impact(
                symbol, asset_class, order_qty, order_side,
                order_price, option_right, is_short_opt,
                existing_positions, inst
            )
            bp_after  = bp["available_buying_power"] - margin["margin_impact"]
            bp_change = -margin["margin_impact"]
            remaining_pct = (bp_after / bp["total_collateral_value"] * 100
                             if bp["total_collateral_value"] > 0 else 0)
            margin_call = bp_after < 0
            warning     = (not margin_call and remaining_pct < 10
                           and bp["total_collateral_value"] > 0)

        st.markdown("---")
        st.subheader("📊 Pre-Trade Margin Analysis")

        if margin_call:
            st.error(f"🚨 MARGIN CALL — Insufficient buying power. "
                     f"Shortfall: ${abs(bp_after):,.2f}")
        elif warning:
            st.warning(f"⚠️ LOW BUYING POWER — Only {remaining_pct:.1f}% remaining after trade.")
        elif margin["margin_impact"] <= 0:
            st.success("✅ Trade REDUCES margin requirement — this is a risk-reducing trade.")
        else:
            st.success("✅ Trade approved — sufficient buying power available.")

        # Margin metrics
        st.markdown("#### Margin Requirement")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Marginal IM Impact",  f"${margin['margin_impact']:+,.2f}")
        m2.metric("Initial Margin (IM)", f"${margin['initial_margin']:,.2f}")
        m3.metric("Maint. Margin (MM)",  f"${margin['maintenance_margin']:,.2f}")
        if margin.get("cash_margin") is not None:
            m4.metric("Cash Account Req",f"${margin['cash_margin']:,.2f}",
                      help="Margin required in a cash (non-margin) account")
        else:
            m4.metric("Cash Account Req", "N/A")
        m5.metric("Method", margin["method"])
        st.caption(f"📐 {margin['calc_detail']}")

        # Portfolio margin waterfall for futures
        if asset_class == "FUT" and "current_portfolio_margin" in margin:
            st.markdown("#### Portfolio SPAN Waterfall")
            pw1, pw2, pw3, pw4 = st.columns(4)
            pw1.metric("Current Portfolio Margin",  f"${margin['current_portfolio_margin']:,.2f}")
            pw2.metric("Combined Portfolio Margin", f"${margin['combined_portfolio_margin']:,.2f}")
            pw3.metric("Marginal Impact",
                       f"${margin['margin_impact']:+,.2f}",
                       delta="Reducing" if margin["margin_impact"] <= 0 else "Adding margin",
                       delta_color="normal" if margin["margin_impact"] <= 0 else "inverse")
            if margin.get("net_qty_after") is not None:
                pw4.metric("Net Position After", f"{margin['net_qty_after']:+.0f} {symbol}")

        # Buying power waterfall
        st.markdown("#### Buying Power Impact")
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Collateral Value",    f"${bp['total_collateral_value']:,.2f}")
        b2.metric("Margin Already Used", f"${bp['margin_used']:,.2f}")
        b3.metric("This Trade Impact",   f"${margin['margin_impact']:+,.2f}")
        b4.metric("Buying Power After",  f"${bp_after:,.2f}",
                  delta=f"{bp_change:+,.2f}", delta_color="inverse")

        # IBKR validation for equities
        if asset_class == "STK":
            st.markdown("#### 🔗 IBKR Validation")
            with st.spinner("Checking against IBKR..."):
                try:
                    from utils.ibkr import whatif_order
                    ibkr_result = whatif_order(symbol, int(order_qty), "MKT",
                                               order_side, order_price)
                    if ibkr_result.get("error"):
                        st.warning(f"IBKR: {ibkr_result['error']}")
                    else:
                        ibkr_im  = ibkr_result.get("margin_impact") or 0
                        our_im   = margin["initial_margin"]
                        diff     = abs(our_im - ibkr_im)
                        diff_pct = (diff / ibkr_im * 100) if ibkr_im > 0 else 0
                        iv1, iv2, iv3, iv4 = st.columns(4)
                        iv1.metric("Our Reg T Calc",   f"${our_im:,.2f}")
                        iv2.metric("IBKR Margin",      f"${ibkr_im:,.2f}")
                        iv3.metric("Difference",       f"${diff:,.2f}")
                        iv4.metric("Variance %",       f"{diff_pct:.1f}%",
                                   delta="✅ Within 10%" if diff_pct <= 10 else "⚠️ >10%",
                                   delta_color="off")
                except Exception as e:
                    st.info(f"IBKR gateway offline — validation skipped. ({str(e)[:80]})")

        st.session_state["pretrade_result"] = {
            "symbol":       symbol,
            "asset_class":  asset_class,
            "side":         order_side,
            "quantity":     order_qty,
            "price":        order_price,
            "order_type":   order_type,
            "expiry":       order_expiry or None,
            "strike":       order_strike or None,
            "option_right": option_right,
            "is_short_opt": is_short_opt,
            "margin":       margin,
            "bp_after":     bp_after,
            "margin_call":  margin_call,
            "instrument":   inst,          # includes inst["id"] = security master id
        }

# ── SUBMIT ORDER ─────────────────────────────────────────────────────────
if "pretrade_result" in st.session_state:
    r = st.session_state["pretrade_result"]
    st.markdown("---")
    st.subheader("📤 Submit Order")

    if r["margin_call"]:
        st.error("🚨 Cannot submit — insufficient buying power.")
    else:
        col1, col2 = st.columns([1, 3])
        with col1:
            submit = st.button("✅ Confirm & Add to Portfolio",
                               type="primary", key="submit_order")
        with col2:
            st.caption(
                f"This will add {r['side']} {r['quantity']} {r['symbol']} "
                f"@ ${r['price']:,.4f} to your Position Store with "
                f"marginal margin impact ${r['margin']['margin_impact']:+,.2f}."
            )

        if submit:
            inst          = r["instrument"]
            instrument_id = inst.get("id")       # unique contract id from security master
            symbol        = r["symbol"]
            ac            = r["asset_class"]
            side          = r["side"]
            qty           = r["quantity"]
            opposite_side = "SHORT" if side == "LONG" else "LONG"

            # Netting: find existing opposite positions for EXACT same instrument_id
            # Different maturities = different instrument_id = no netting
            existing_opposite = []
            if instrument_id:
                from core.position_store import get_positions_by_instrument
                existing_by_id = get_positions_by_instrument(instrument_id)
                existing_opposite = [p for p in existing_by_id if p["side"] == opposite_side]

            if existing_opposite and ac == "FUT":
                # Same contract, opposite side — net it
                ok, msg, remainder = reduce_or_close_position(
                    instrument_id, qty, symbol
                )
                if ok:
                    if remainder > 0:
                        # Sold more than we held — open remainder as new opposite position
                        payload = {
                            "instrument_id":  instrument_id,
                            "symbol":         symbol,
                            "asset_class":    ac,
                            "name":           inst.get("name"),
                            "side":           side,
                            "quantity":       remainder,
                            "entry_price":    r["price"],
                            "current_price":  r["price"],
                            "expiry":         r["expiry"],
                            "multiplier":     inst.get("multiplier") or 1,
                            "contract_size":  inst.get("contract_size") or 1,
                            "margin_method":  r["margin"]["method"],
                            "initial_margin": 0,
                            "maintenance_margin": 0,
                            "source":         "order_input",
                            "exchange":       inst.get("exchange"),
                            "currency":       inst.get("currency", "USD"),
                        }
                        add_position(payload)
                        msg = (f"Closed existing {opposite_side} and opened "
                               f"{side} {remainder} {symbol}")
                    else:
                        msg = f"Reduced/closed existing {opposite_side} {symbol} position"
                    recalculate_portfolio_margins()
                    st.success(f"✅ {msg}")
                    st.balloons()
                    del st.session_state["pretrade_result"]
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")
            else:
                # New position (different contract or same side) — just add it
                payload = {
                    "instrument_id":      instrument_id,
                    "symbol":             symbol,
                    "asset_class":        ac,
                    "name":               inst.get("name"),
                    "side":               side,
                    "quantity":           qty,
                    "entry_price":        r["price"],
                    "current_price":      r["price"],
                    "expiry":             r["expiry"],
                    "strike":             r["strike"],
                    "option_right":       r["option_right"],
                    "multiplier":         inst.get("multiplier") or 1,
                    "contract_size":      inst.get("contract_size") or 1,
                    "margin_method":      r["margin"]["method"],
                    "initial_margin":     r["margin"]["initial_margin"],
                    "maintenance_margin": r["margin"]["maintenance_margin"],
                    "source":             "order_input",
                    "exchange":           inst.get("exchange"),
                    "currency":           inst.get("currency", "USD"),
                }
                ok, msg = add_position(payload)
                if ok:
                    # Always recalc futures margins — captures spread credits
                    if ac == "FUT":
                        recalculate_portfolio_margins()
                    st.success(f"✅ {msg}")
                    st.balloons()
                    del st.session_state["pretrade_result"]
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

# ── OPEN POSITIONS SUMMARY ───────────────────────────────────────────────
st.markdown("---")
st.subheader("📋 Current Open Positions")
positions = get_positions("open")
if not positions:
    st.info("No open positions yet.")
else:
    rows = []
    for p in positions:
        rows.append({
            "Symbol":          p["symbol"],
            "Asset Class":     p["asset_class"],
            "Side":            p["side"],
            "Qty":             p["quantity"],
            "Entry ($)":       f"${p['entry_price']:,.4f}",
            "Notional ($)":    f"${p['notional_value']:,.2f}",
            "Init Margin ($)": f"${p['initial_margin']:,.2f}",
            "Method":          p.get("margin_method") or "—",
            "Source":          p["source"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)