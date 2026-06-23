import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotly.express as px
import pandas as pd

from core.position_store import get_positions, get_portfolio_summary
from core.margin_call import get_margin_call_status
from core.collateral_manager import get_collateral_summary

st.set_page_config(page_title='Portfolio Overview', page_icon='📊', layout='wide')
st.title('📊 Portfolio Overview')

# ── MARGIN HEALTH ALERT BANNER ───────────────────────────────────────────
try:
    mc     = get_margin_call_status()
    alert  = mc["alert"]
    el     = mc["excess_liquidity"]
    mm     = mc["total_mm"]
    cv     = mc["collateral_value"]
    st.markdown(
        f'<div style="padding:12px 18px;border-radius:8px;background:{alert["color"]}22;'
        f'border-left:6px solid {alert["color"]};margin-bottom:16px;">'
        f'<span style="font-size:20px;">{alert["emoji"]}</span>&nbsp;&nbsp;'
        f'<span style="font-size:16px;font-weight:700;color:{alert["color"]};">{alert["label"]}</span>'
        f'&nbsp;&nbsp;<span style="color:#ccc;font-size:13px;">{alert["description"]}</span>'
        f'&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;'
        f'<span style="color:#aaa;font-size:12px;">Excess Liquidity</span>&nbsp;'
        f'<span style="color:{alert["color"]};font-size:14px;font-weight:600;">${el:,.2f}</span>'
        f'&nbsp;&nbsp;'
        f'<span style="color:#aaa;font-size:12px;">MM Used</span>&nbsp;'
        f'<span style="color:#fff;font-size:14px;font-weight:600;">${mm:,.2f}</span>'
        f'&nbsp;&nbsp;'
        f'<span style="color:#aaa;font-size:12px;">Collateral</span>&nbsp;'
        f'<span style="color:#fff;font-size:14px;font-weight:600;">${cv:,.2f}</span>'
        f'</div>',
        unsafe_allow_html=True
    )
except Exception as e:
    st.info(f"Margin monitor unavailable: {str(e)[:60]}")

# ── ACCOUNT SUMMARY ───────────────────────────────────────────────────────
st.subheader("Account Summary")
try:
    coll    = get_collateral_summary()
    port    = get_portfolio_summary()
    total_cv = coll["total_collateral_value"]
    total_im = port["total_initial_margin"]
    total_mm = port["total_maintenance_margin"]

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Total Collateral Value",  f"${total_cv:,.2f}",
              help="Post-haircut collateral from Collateral Manager")
    c2.metric("Total Notional Exposure", f"${port['total_notional']:,.2f}")
    c3.metric("Initial Margin Used",     f"${total_im:,.2f}")
    c4.metric("Available Buying Power",  f"${total_cv - total_im:,.2f}")
    c5.metric("Unrealized P&L",          f"${port['total_unrealized_pnl']:+,.2f}",
              delta=f"{'▲' if port['total_unrealized_pnl']>=0 else '▼'} ${abs(port['total_unrealized_pnl']):,.2f}",
              delta_color="normal" if port['total_unrealized_pnl']>=0 else "inverse")
except Exception as e:
    st.warning(f"Could not load account summary: {e}")

st.markdown("---")

# ── POSITIONS ─────────────────────────────────────────────────────────────
positions = get_positions("open")

if not positions:
    st.warning("No open positions. Add positions via Order Input.")
    st.stop()

st.subheader(f"Open Positions ({len(positions)})")

rows = []
for p in positions:
    pnl_pct = ((p['current_price'] - p['entry_price']) / p['entry_price'] * 100
               if p['entry_price'] > 0 else 0)
    if p['side'] == 'SHORT':
        pnl_pct = -pnl_pct
    rows.append({
        "Symbol":         p["symbol"],
        "Asset Class":    p["asset_class"],
        "Side":           p["side"],
        "Qty":            p["quantity"],
        "Entry ($)":      f"${p['entry_price']:,.4f}",
        "Current ($)":    f"${p['current_price']:,.4f}",
        "Notional ($)":   f"${p['notional_value']:,.2f}",
        "Unreal P&L ($)": f"${p['unrealized_pnl']:+,.2f}",
        "P&L %":          f"{pnl_pct:+.2f}%",
        "IM ($)":         f"${p['initial_margin']:,.2f}",
        "Method":         p.get("margin_method") or "—",
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.markdown("---")

# ── CHARTS ────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("Notional by Asset Class")
    by_ac = {}
    for p in positions:
        ac = p["asset_class"]
        by_ac[ac] = by_ac.get(ac, 0) + p["notional_value"]
    if by_ac:
        fig1 = px.pie(
            pd.DataFrame([{"Asset Class": k, "Notional": v} for k, v in by_ac.items()]),
            values="Notional", names="Asset Class",
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        fig1.update_traces(textposition="inside", textinfo="percent+label")
        fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#fff")
        st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.subheader("Unrealized P&L by Position")
    pnl_df = pd.DataFrame([{
        "Symbol": f"{p['symbol']} ({p['side']})",
        "P&L ($)": p["unrealized_pnl"]
    } for p in positions])
    if not pnl_df.empty:
        fig2 = px.bar(pnl_df, x="Symbol", y="P&L ($)",
                      color="P&L ($)", color_continuous_scale=["red","green"],
                      title="Unrealized P&L by Position ($)")
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#fff",
                           plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)

# ── MARGIN SUMMARY ────────────────────────────────────────────────────────
if get_portfolio_summary()["by_asset_class"]:
    st.markdown("---")
    st.subheader("Margin by Asset Class")
    summary = get_portfolio_summary()
    margin_rows = [{"Asset Class": ac,
                    "Positions": v["count"],
                    "Notional ($)": f"${v['notional']:,.2f}",
                    "IM ($)": f"${v['initial_margin']:,.2f}",
                    "Unreal P&L ($)": f"${v['pnl']:+,.2f}"}
                   for ac, v in summary["by_asset_class"].items()]
    st.dataframe(pd.DataFrame(margin_rows), use_container_width=True, hide_index=True)

st.caption(f"Data source: Sentinel position store (trading.db) | Refresh to see latest")