import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from core.margin_call import get_margin_call_status
from core.position_store import recalculate_portfolio_margins

st.set_page_config(page_title="Margin Monitor", page_icon="🚨", layout="wide")
st.title("🚨 Margin Monitor")
st.caption("Real-time Initial Margin, Maintenance Margin and Variation Margin dashboard.")

# Auto-recalc margins on load
if "mc_margins_recalculated" not in st.session_state:
    recalculate_portfolio_margins()
    st.session_state["mc_margins_recalculated"] = True

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 Refresh"):
        recalculate_portfolio_margins()
        st.rerun()

# ── FETCH STATUS ─────────────────────────────────────────────────────────
status = get_margin_call_status()
alert  = status["alert"]

# ── ALERT BANNER ─────────────────────────────────────────────────────────
st.markdown(
    f'<div style="padding:16px 20px;border-radius:8px;background:{alert["color"]}22;'
    f'border-left:6px solid {alert["color"]};margin-bottom:20px;">'
    f'<span style="font-size:24px;">{alert["emoji"]}</span>&nbsp;&nbsp;'
    f'<span style="font-size:20px;font-weight:700;color:{alert["color"]};">'
    f'{alert["label"]}</span>&nbsp;&nbsp;'
    f'<span style="color:#ccc;font-size:14px;">{alert["description"]}</span>'
    f'</div>',
    unsafe_allow_html=True
)

st.markdown("---")

# ── THREE MARGIN SECTIONS ─────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 IM Dashboard",
    "⚠️ MM & Margin Call",
    "💸 Variation Margin",
    "📋 Position Breakdown"
])

# ── TAB 1: INITIAL MARGIN ────────────────────────────────────────────────
with tab1:
    st.subheader("Initial Margin (IM)")
    st.caption("Required to open and hold positions. Breach = cannot open new trades.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Collateral Value", f"${status['collateral_value']:,.2f}")
    c2.metric("IM Used",                f"${status['total_im']:,.2f}")
    c3.metric("IM Available",           f"${status['im_available']:,.2f}",
              delta=f"{status['im_available']:+,.2f}",
              delta_color="normal" if status['im_available'] >= 0 else "inverse")
    c4.metric("IM Utilisation",         f"{status['im_utilisation_pct']:.1f}%")

    # IM gauge
    fig_im = go.Figure(go.Indicator(
        mode  = "gauge+number+delta",
        value = status["im_utilisation_pct"],
        title = {"text": "IM Utilisation %"},
        delta = {"reference": 80, "increasing": {"color": "#cc3300"}},
        gauge = {
            "axis":  {"range": [0, 100]},
            "bar":   {"color": "#4C9BE8"},
            "steps": [
                {"range": [0,  60], "color": "#1a3a1a"},
                {"range": [60, 80], "color": "#3a3a1a"},
                {"range": [80, 90], "color": "#3a2a1a"},
                {"range": [90,100], "color": "#3a1a1a"},
            ],
            "threshold": {
                "line":  {"color": "#cc3300", "width": 4},
                "thickness": 0.75,
                "value": 90
            }
        }
    ))
    fig_im.update_layout(height=280, margin=dict(t=40, b=0, l=20, r=20),
                         paper_bgcolor="rgba(0,0,0,0)", font_color="#fff")
    st.plotly_chart(fig_im, use_container_width=True)

    # Collateral breakdown
    st.markdown("**Collateral by Asset Class**")
    coll_rows = []
    for ac, vals in status["collateral_breakdown"].items():
        coll_rows.append({
            "Asset Class":         ac,
            "Market Value ($)":    f"${vals['market_value']:,.2f}",
            "Collateral Value ($)": f"${vals['collateral_value']:,.2f}",
            "Items":               vals["count"],
        })
    if coll_rows:
        st.dataframe(pd.DataFrame(coll_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No collateral on file. Add collateral in the Collateral Manager.")

# ── TAB 2: MAINTENANCE MARGIN & MARGIN CALL ──────────────────────────────
with tab2:
    st.subheader("Maintenance Margin (MM) & Margin Call Status")
    st.caption("MM is the minimum to hold positions. Breach triggers a margin call.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Collateral Value",  f"${status['collateral_value']:,.2f}")
    c2.metric("MM Used",                 f"${status['total_mm']:,.2f}")
    el = status["excess_liquidity"]
    c3.metric("Excess Liquidity",        f"${el:,.2f}",
              delta=f"{el:+,.2f}",
              delta_color="normal" if el >= 0 else "inverse")
    c4.metric("MM Utilisation",          f"{status['mm_utilisation_pct']:.1f}%")

    st.markdown("---")

    # Threshold waterfall
    st.markdown("**Margin Call Buffer — Distance to Each Threshold**")
    cv = status["collateral_value"]
    mm = status["total_mm"]

    thresholds = [
        {"Level": "🟢 Safe (>20%)",     "Threshold ($)": f"${cv*0.20:,.2f}", "Buffer ($)": f"${el - cv*0.20:+,.2f}", "Status": "✅" if el >= cv*0.20 else "❌"},
        {"Level": "🟡 Watch (10-20%)",  "Threshold ($)": f"${cv*0.10:,.2f}", "Buffer ($)": f"${el - cv*0.10:+,.2f}", "Status": "✅" if el >= cv*0.10 else "❌"},
        {"Level": "🟠 Warning (5-10%)", "Threshold ($)": f"${cv*0.05:,.2f}", "Buffer ($)": f"${el - cv*0.05:+,.2f}", "Status": "✅" if el >= cv*0.05 else "❌"},
        {"Level": "🔴 Margin Call (<5%)","Threshold ($)": f"${cv*0.00:,.2f}", "Buffer ($)": f"${el:+,.2f}",          "Status": "✅" if el >= 0 else "❌"},
        {"Level": "❌ Breach (<0)",      "Threshold ($)": "$0.00",            "Buffer ($)": f"${el:+,.2f}",           "Status": "✅" if el >= 0 else "❌"},
    ]
    st.dataframe(pd.DataFrame(thresholds), use_container_width=True, hide_index=True)

    # MM gauge
    fig_mm = go.Figure(go.Indicator(
        mode  = "gauge+number+delta",
        value = status["mm_utilisation_pct"],
        title = {"text": "MM Utilisation %"},
        delta = {"reference": 95, "increasing": {"color": "#cc3300"}},
        gauge = {
            "axis":  {"range": [0, 100]},
            "bar":   {"color": "#F39C12"},
            "steps": [
                {"range": [0,  80], "color": "#1a3a1a"},
                {"range": [80, 90], "color": "#3a3a1a"},
                {"range": [90, 95], "color": "#3a2a1a"},
                {"range": [95,100], "color": "#3a1a1a"},
            ],
            "threshold": {
                "line":  {"color": "#cc3300", "width": 4},
                "thickness": 0.75,
                "value": 95
            }
        }
    ))
    fig_mm.update_layout(height=280, margin=dict(t=40, b=0, l=20, r=20),
                         paper_bgcolor="rgba(0,0,0,0)", font_color="#fff")
    st.plotly_chart(fig_mm, use_container_width=True)

    # Cure options
    if status["cure"]:
        st.markdown("---")
        st.markdown("### 💊 Cure Options")
        cure = status["cure"]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Option A — Deposit Cash**")
            st.metric("Cash Required to Cure", f"${cure['cash_to_deposit']:,.2f}")
            st.caption("Deposit this amount as collateral to restore excess liquidity above margin call threshold.")

        with col2:
            st.markdown("**Option B — Close Positions**")
            if cure["close_suggestions"]:
                close_df = pd.DataFrame(cure["close_suggestions"])
                close_df.columns = ["Symbol", "Side", "Qty", "Margin Freed ($)", "Notional ($)"]
                st.dataframe(close_df, use_container_width=True, hide_index=True)
                if cure["fully_cured_by_close"]:
                    st.success("✅ Closing these positions fully cures the margin call.")
                else:
                    st.warning("⚠️ Closing these positions partially cures — additional cash needed.")
            else:
                st.info("No futures positions to close.")

# ── TAB 3: VARIATION MARGIN ──────────────────────────────────────────────
with tab3:
    st.subheader("Variation Margin (VM)")
    st.caption("Daily MTM cash settlement on futures and crypto. Credits = cash in, Debits = cash out.")

    vm = status["variation_margin"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Net VM Today",
              f"${vm['total_vm']:,.2f}",
              delta=f"{'Credit ▲' if vm['total_vm'] >= 0 else 'Debit ▼'} ${abs(vm['total_vm']):,.2f}",
              delta_color="normal" if vm["total_vm"] >= 0 else "inverse")
    credits = sum(p["vm"] for p in vm["positions"] if p["vm"] >= 0)
    debits  = sum(p["vm"] for p in vm["positions"] if p["vm"] < 0)
    c2.metric("Total Credits", f"${credits:,.2f}")
    c3.metric("Total Debits",  f"${abs(debits):,.2f}")

    if vm["positions"]:
        st.markdown("---")
        st.markdown("**VM by Position**")
        vm_rows = []
        for p in vm["positions"]:
            vm_rows.append({
                "Symbol":        p["symbol"],
                "Side":          p["side"],
                "Qty":           p["quantity"],
                "Entry ($)":     f"${p['entry_price']:,.4f}",
                "Current ($)":   f"${p['current_price']:,.4f}",
                "Price Chg ($)": f"${p['price_change']:+,.4f}",
                "VM ($)":        f"${p['vm']:+,.2f}",
                "Direction":     p["vm_direction"].upper(),
            })
        st.dataframe(pd.DataFrame(vm_rows), use_container_width=True, hide_index=True)

        # VM bar chart
        fig_vm = px.bar(
            pd.DataFrame([{"Symbol": p["symbol"] + f" ({p['side']})", "VM ($)": p["vm"]}
                          for p in vm["positions"]]),
            x="Symbol", y="VM ($)",
            color="VM ($)",
            color_continuous_scale=["#cc3300", "#2ECC71"],
            title="Variation Margin by Position ($)"
        )
        fig_vm.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#fff",
                             plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_vm, use_container_width=True)
    else:
        st.info("No futures or crypto positions — variation margin only applies to futures and crypto.")

# ── TAB 4: POSITION BREAKDOWN ─────────────────────────────────────────────
with tab4:
    st.subheader("Position-Level Margin Breakdown")
    st.caption("Shows IM and MM per position and their % contribution to total portfolio margin.")

    breakdown = status["position_breakdown"]
    if not breakdown:
        st.info("No open positions.")
    else:
        rows = []
        for p in breakdown:
            rows.append({
                "Symbol":          p["symbol"],
                "Asset Class":     p["asset_class"],
                "Side":            p["side"],
                "Qty":             p["quantity"],
                "Notional ($)":    f"${p['notional_value']:,.2f}",
                "IM ($)":          f"${p['initial_margin']:,.2f}",
                "MM ($)":          f"${p['maintenance_margin']:,.2f}",
                "IM % of Total":   f"{p['im_pct_of_total']:.1f}%",
                "MM % of Total":   f"{p['mm_pct_of_total']:.1f}%",
                "Unrealized P&L":  f"${p['unrealized_pnl']:,.2f}",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("---")
        # IM contribution pie
        col1, col2 = st.columns(2)
        with col1:
            im_data = [{"Symbol": p["symbol"] + f"({p['side']})",
                        "IM": p["initial_margin"]}
                       for p in breakdown if p["initial_margin"] > 0]
            if im_data:
                fig_im_pie = px.pie(pd.DataFrame(im_data),
                                    values="IM", names="Symbol",
                                    title="IM Contribution by Position",
                                    color_discrete_sequence=px.colors.qualitative.Set2)
                fig_im_pie.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig_im_pie, use_container_width=True)

        with col2:
            mm_data = [{"Symbol": p["symbol"] + f"({p['side']})",
                        "MM": p["maintenance_margin"]}
                       for p in breakdown if p["maintenance_margin"] > 0]
            if mm_data:
                fig_mm_pie = px.pie(pd.DataFrame(mm_data),
                                    values="MM", names="Symbol",
                                    title="MM Contribution by Position",
                                    color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_mm_pie.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig_mm_pie, use_container_width=True)

st.markdown("---")
st.caption(f"Last calculated: {status['as_of']} UTC")