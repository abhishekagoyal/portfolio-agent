import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from core.security_master import search_instruments, get_instrument
from core.position_store import (
    add_position, get_positions, get_portfolio_summary, update_position_margin
)
from core.collateral_manager import get_collateral_summary
from core.span import calculate_portfolio_margin, load_span_params

st.set_page_config(page_title="Order Input", page_icon="🎯", layout="wide")
st.title("🎯 Order Input — Pre-Trade Margin Check")
st.caption("Select an instrument, enter order details, and check margin impact before trading.")

# ── Helper: margin engine ────────────────────────────────────────────────
def calculate_pretrade_margin(symbol: str, asset_class: str, quantity: float,
                               side: str, price: float,
                               option_right: str = None,
                               is_short_option: bool = False) -> dict:
    """
    Run pre-trade margin calculation based on asset class.
    Returns a dict with initial_margin, maintenance_margin, method, calc_detail.
    """
    params     = load_span_params()
    position_value = quantity * price

    # ── FUTURES ──────────────────────────────────────────────────────────
    if asset_class == "FUT":
        prod = params.get("product_margins", {}).get(symbol.upper())
        if prod:
            im   = prod["initial_margin"]     * quantity
            mm   = prod["maintenance_margin"] * quantity
            detail = (f"{quantity:.0f} contracts × "
                      f"${prod['initial_margin']:,} = ${im:,.2f} initial | "
                      f"${prod['maintenance_margin']:,} = ${mm:,.2f} maint.")
            method = "SPAN (per-contract)"
        else:
            ac_map  = params.get("asset_class_map", {})
            ac_key  = ac_map.get(symbol.upper(), "equity_futures")
            fallback = params.get("fallback_scanning_ranges", {}).get(ac_key, 0.08)
            im      = abs(position_value) * fallback
            mm      = im * 0.90
            detail  = f"${abs(position_value):,.2f} × {fallback:.0%} = ${im:,.2f} (fallback — add to SPAN params for exact rate)"
            method  = "SPAN (fallback %)"
        return {"initial_margin": round(im, 2), "maintenance_margin": round(mm, 2),
                "method": method, "calc_detail": detail}

    # ── OPTIONS ON FUTURES (SPAN SOM) ────────────────────────────────────
    elif asset_class == "OPT" and symbol.upper() in params.get("asset_class_map", {}):
        ac_key = params["asset_class_map"].get(symbol.upper(), "equity_futures")
        som_key = ac_key + "_options" if "options" not in ac_key else ac_key
        som_rate = params.get("short_option_minimum", {}).get(som_key, 50)
        if is_short_option:
            im   = quantity * som_rate
            mm   = im * 0.90
            detail = f"{quantity:.0f} contracts × ${som_rate} SOM = ${im:,.2f}"
            method = "SPAN (SOM)"
        else:
            # Long option — pay premium only
            im     = abs(position_value)
            mm     = im
            detail = f"Long option: 100% premium = ${im:,.2f}"
            method = "SPAN (long premium)"
        return {"initial_margin": round(im, 2), "maintenance_margin": round(mm, 2),
                "method": method, "calc_detail": detail}

    # ── EQUITY OPTIONS (Reg T options rules) ─────────────────────────────
    elif asset_class == "OPT":
        if not is_short_option:
            # Long option — 100% of premium
            im     = abs(position_value)
            mm     = im
            detail = f"Long option: 100% of premium ${abs(position_value):,.2f}"
            method = "Reg T (long option)"
        else:
            # Short naked option — 20% of underlying notional
            im     = abs(position_value) * 0.20
            mm     = abs(position_value) * 0.20
            detail = f"Short naked option: 20% × ${abs(position_value):,.2f} = ${im:,.2f}"
            method = "Reg T (short naked option)"
        return {"initial_margin": round(im, 2), "maintenance_margin": round(mm, 2),
                "method": method, "calc_detail": detail}

    # ── CRYPTO ───────────────────────────────────────────────────────────
    elif asset_class == "CRYPTO":
        im     = abs(position_value) * 1.00
        mm     = im
        detail = f"Crypto: 100% cash × ${abs(position_value):,.2f} = ${im:,.2f}"
        method = "Cash (100%)"
        return {"initial_margin": round(im, 2), "maintenance_margin": round(mm, 2),
                "method": method, "calc_detail": detail}

    # ── BONDS held as securities ──────────────────────────────────────────
    elif asset_class == "BOND":
        im     = abs(position_value) * 0.10
        mm     = abs(position_value) * 0.05
        detail = f"Bond: 10% × ${abs(position_value):,.2f} = ${im:,.2f}"
        method = "Reg T (bond)"
        return {"initial_margin": round(im, 2), "maintenance_margin": round(mm, 2),
                "method": method, "calc_detail": detail}

    # ── EQUITIES (Reg T) ─────────────────────────────────────────────────
    else:
        reg_t  = params.get("reg_t", {})
        ir     = reg_t.get("initial", 0.50)
        mr     = reg_t.get("maintenance", 0.25)
        im     = abs(position_value) * ir
        mm     = abs(position_value) * mr
        detail = f"Reg T: ${abs(position_value):,.2f} × {ir:.0%} = ${im:,.2f} initial | × {mr:.0%} = ${mm:,.2f} maint."
        method = "Reg T (equity)"
        return {"initial_margin": round(im, 2), "maintenance_margin": round(mm, 2),
                "method": method, "calc_detail": detail}


def get_buying_power() -> dict:
    """Collateral value - current margin used = available buying power."""
    coll    = get_collateral_summary()
    port    = get_portfolio_summary()
    total_cv  = coll["total_collateral_value"]
    margin_used = port["total_initial_margin"]
    available   = total_cv - margin_used
    return {
        "total_collateral_value": total_cv,
        "margin_used":            margin_used,
        "available_buying_power": available,
        "utilisation_pct":        round(margin_used / total_cv * 100, 1) if total_cv > 0 else 0,
    }


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
    color = "normal" if bp["available_buying_power"] > 0 else "inverse"
    st.metric("Available Buying Power", f"${bp['available_buying_power']:,.2f}")
with col4:
    st.metric("Margin Utilisation",     f"{bp['utilisation_pct']:.1f}%")

# Utilisation bar
util = min(bp["utilisation_pct"] / 100, 1.0)
bar_color = "#2ECC71" if util < 0.6 else ("#F39C12" if util < 0.85 else "#cc3300")
st.markdown(
    f'<div style="background:#2a2a2a;border-radius:6px;height:12px;margin:4px 0 16px 0;">'
    f'<div style="background:{bar_color};width:{util*100:.1f}%;height:12px;border-radius:6px;"></div>'
    f'</div>', unsafe_allow_html=True
)

st.markdown("---")

# ── ORDER INPUT FORM ─────────────────────────────────────────────────────
st.subheader("📋 Order Details")

# Instrument selection from Security Master
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
    st.stop()

inst = inst_map[selected_inst_label]
symbol      = inst["symbol"]
asset_class = inst["asset_class"]
margin_method = inst.get("margin_method", "REGT")

# Show instrument details
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
    order_qty   = st.number_input("Quantity",
                                  min_value=1, value=1, step=1, key="order_qty")
with col3:
    order_price = st.number_input("Price ($)",
                                  min_value=0.0, value=0.0,
                                  step=0.01, format="%.4f", key="order_price")
with col4:
    order_type  = st.selectbox("Order Type", ["MKT", "LMT"], key="order_type")

# Asset-class specific fields
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
        order_strike = st.number_input("Strike ($)",
                                       min_value=0.0,
                                       value=float(inst.get("strike") or 0.0),
                                       step=0.5, key="order_strike")
    with col3:
        is_short_opt = st.checkbox("Short Option (selling)?", key="order_short_opt")

if asset_class in ["FUT", "OPT"]:
    order_expiry = st.text_input("Expiry (YYYYMMDD)",
                                 value=inst.get("expiry") or "",
                                 key="order_expiry")

# ── PRE-TRADE CHECK BUTTON ───────────────────────────────────────────────
st.markdown("")
check_col, _ = st.columns([1, 3])
with check_col:
    run_check = st.button("🔍 Run Pre-Trade Margin Check", type="primary", key="run_check")

if run_check:
    if order_price <= 0:
        st.error("❌ Please enter a valid price.")
    else:
        with st.spinner("Calculating margin impact..."):
            # Our engine
            margin = calculate_pretrade_margin(
                symbol, asset_class, order_qty, order_side,
                order_price, option_right, is_short_opt
            )

            # Buying power impact
            bp_after  = bp["available_buying_power"] - margin["initial_margin"]
            bp_change = -margin["initial_margin"]
            remaining_pct = (bp_after / bp["total_collateral_value"] * 100
                             if bp["total_collateral_value"] > 0 else 0)

            # Margin call check
            margin_call = bp_after < 0
            warning     = (not margin_call and
                           remaining_pct < 10 and
                           bp["total_collateral_value"] > 0)

        st.markdown("---")
        st.subheader("📊 Pre-Trade Margin Analysis")

        # Status banner
        if margin_call:
            st.error("🚨 MARGIN CALL — Insufficient buying power for this trade. "
                     f"Shortfall: ${abs(bp_after):,.2f}")
        elif warning:
            st.warning(f"⚠️ LOW BUYING POWER — Only {remaining_pct:.1f}% of collateral "
                       "remaining after this trade.")
        else:
            st.success("✅ Trade approved — sufficient buying power available.")

        # Margin metrics
        st.markdown("#### Margin Requirement")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Initial Margin",      f"${margin['initial_margin']:,.2f}")
        m2.metric("Maintenance Margin",  f"${margin['maintenance_margin']:,.2f}")
        m3.metric("Margin Method",       margin["method"])
        m4.metric("Notional Value",      f"${order_qty * order_price:,.2f}")

        st.caption(f"📐 Calculation: {margin['calc_detail']}")

        # Buying power waterfall
        st.markdown("#### Buying Power Impact")
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Collateral Value",    f"${bp['total_collateral_value']:,.2f}")
        b2.metric("Margin Already Used", f"${bp['margin_used']:,.2f}")
        b3.metric("This Trade Margin",   f"${margin['initial_margin']:,.2f}")
        color = "normal" if bp_after >= 0 else "inverse"
        b4.metric("Buying Power After",  f"${bp_after:,.2f}",
                  delta=f"{bp_change:+,.2f}", delta_color="inverse")

        # IBKR validation (if gateway available)
        if asset_class == "STK":
            st.markdown("#### 🔗 IBKR Validation")
            with st.spinner("Checking against IBKR paper account..."):
                try:
                    from utils.ibkr import whatif_order
                    ibkr_side   = order_side
                    ibkr_result = whatif_order(symbol, int(order_qty), "MKT", ibkr_side, order_price)

                    if ibkr_result.get("error"):
                        st.warning(f"IBKR: {ibkr_result['error']}")
                    else:
                        ibkr_im  = ibkr_result.get("margin_impact") or 0
                        our_im   = margin["initial_margin"]
                        diff     = abs(our_im - ibkr_im)
                        diff_pct = (diff / ibkr_im * 100) if ibkr_im > 0 else 0

                        iv1, iv2, iv3, iv4 = st.columns(4)
                        iv1.metric("Our SPAN/RegT Calc",  f"${our_im:,.2f}")
                        iv2.metric("IBKR Margin Impact",  f"${ibkr_im:,.2f}")
                        iv3.metric("Difference",          f"${diff:,.2f}")
                        iv4.metric("Variance %",          f"{diff_pct:.1f}%",
                                   delta="✅ Within 10%" if diff_pct <= 10 else "⚠️ >10% variance",
                                   delta_color="off")

                        if diff_pct > 10:
                            st.warning(f"Our calc differs from IBKR by {diff_pct:.1f}% — "
                                       "consider updating SPAN params in the Risk Calculator.")
                        else:
                            st.success(f"✅ Our calculation matches IBKR within {diff_pct:.1f}%")
                except Exception as e:
                    st.info(f"IBKR gateway offline — validation skipped. ({str(e)[:80]})")

        # Store result in session for submit
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
            "instrument":   inst,
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
            st.caption(f"This will add {r['side']} {r['quantity']} {r['symbol']} "
                       f"@ ${r['price']:,.4f} to your Position Store with "
                       f"initial margin ${r['margin']['initial_margin']:,.2f}.")

        if submit:
            inst  = r["instrument"]
            payload = {
                "symbol":             r["symbol"],
                "asset_class":        r["asset_class"],
                "name":               inst.get("name"),
                "side":               r["side"],
                "quantity":           r["quantity"],
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