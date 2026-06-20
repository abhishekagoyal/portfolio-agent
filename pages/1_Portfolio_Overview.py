import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotly.express as px
import pandas as pd

from core.portfolio import calculate_portfolio_summary, calculate_pnl, get_position_weights
from utils.s3 import load_positions, load_span_results

st.set_page_config(page_title='Portfolio Overview', page_icon='📊', layout='wide')
st.title('Portfolio Overview')

if 'positions' not in st.session_state:
    st.session_state.positions = load_positions()
if 'span_results' not in st.session_state:
    st.session_state.span_results = load_span_results()

# ── IBKR Live Account Overview ───────────────────────────────────────────────
st.subheader('🏦 IBKR Account Overview (Live)')

@st.cache_data(ttl=60, show_spinner=False)
def fetch_ibkr_account():
    try:
        from utils.ibkr import get_margin_requirements
        return get_margin_requirements(), None
    except Exception as e:
        return None, str(e)

with st.spinner('Fetching live account data from IBKR...'):
    ibkr_data, ibkr_error = fetch_ibkr_account()

if ibkr_error:
    st.warning(f'IBKR gateway unavailable — showing cached portfolio data. ({ibkr_error})')
elif ibkr_data:
    def fmt(v, prefix='$'):
        if v is None:
            return 'N/A'
        try:
            return f'{prefix}{float(v):,.2f}'
        except:
            return str(v)

    net_liq    = ibkr_data.get('net_liquidation')
    buying_pwr = ibkr_data.get('buying_power')
    init_mrgn  = ibkr_data.get('initial_margin')  or 0
    maint_mrgn = ibkr_data.get('maintenance_margin') or 0
    excess_liq = ibkr_data.get('excess_liquidity')

    # Margin utilisation: initial margin as % of net liquidation
    try:
        util_pct = (float(init_mrgn) / float(net_liq) * 100) if net_liq and float(net_liq) > 0 else 0
        util_str = f'{util_pct:.1f}%'
        util_delta = '🟢 Low' if util_pct < 30 else ('🟡 Medium' if util_pct < 60 else '🔴 High')
    except:
        util_str = 'N/A'
        util_delta = ''

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric('Net Liquidation', fmt(net_liq))
    with col2:
        st.metric('Buying Power', fmt(buying_pwr))
    with col3:
        st.metric('Initial Margin Req', fmt(init_mrgn))
    with col4:
        st.metric('Maintenance Margin', fmt(maint_mrgn))
    with col5:
        st.metric('Margin Utilisation', util_str, delta=util_delta, delta_color='off')

    if excess_liq is not None:
        try:
            el = float(excess_liq)
            color = '#1a9e3f' if el > 0 else '#cc3300'
            st.markdown(
                f'<div style="padding:8px 12px;border-radius:6px;background:#1e1e1e;'
                f'border-left:4px solid {color};margin-top:8px;">'
                f'<span style="color:#aaa;font-size:13px;">Excess Liquidity</span>&nbsp;&nbsp;'
                f'<span style="color:{color};font-size:16px;font-weight:600;">${el:,.2f}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
        except:
            pass

    if st.button('🔄 Refresh Account Data'):
        st.cache_data.clear()
        st.rerun()

st.markdown('---')

# ── Portfolio Summary ────────────────────────────────────────────────────────
if not st.session_state.positions:
    st.warning('No positions found. Add positions in Position Manager first.')
    st.stop()

summary  = calculate_portfolio_summary(st.session_state.positions)
enriched = calculate_pnl(st.session_state.positions)
weighted = get_position_weights(st.session_state.positions)

st.subheader('Portfolio Summary')
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric('Total Market Value', '$' + '{:,.2f}'.format(summary['total_market_value']))
with col2:
    st.metric('Total P&L', '$' + '{:,.2f}'.format(summary['total_pnl']))
with col3:
    st.metric('Positions', summary['num_positions'])
with col4:
    st.metric('Winners', summary['winners'])
with col5:
    st.metric('Losers', summary['losers'])

if st.session_state.span_results:
    st.markdown('---')
    st.subheader('SPAN Margin Summary')
    col1, col2, col3 = st.columns(3)
    span = st.session_state.span_results
    with col1:
        st.metric('Net Margin Requirement', '$' + '{:,.2f}'.format(span.get('net_margin_requirement', 0)))
    with col2:
        st.metric('Spread Credits', '$' + '{:,.2f}'.format(span.get('total_spread_credits', 0)))
    with col3:
        total_val = summary['total_market_value']
        margin    = span.get('net_margin_requirement', 0)
        utilization = (margin / total_val * 100) if total_val > 0 else 0
        st.metric('SPAN Margin Utilization', '{:.1f}'.format(utilization) + '%')

st.markdown('---')
st.subheader('Position Details')
df = pd.DataFrame(enriched)
if not df.empty:
    display_cols  = ['symbol', 'quantity', 'entry_price', 'price', 'market_value', 'pnl', 'pnl_pct']
    df_display    = df[display_cols].copy()
    df_display.columns = ['Symbol', 'Qty', 'Entry Price', 'Current Price', 'Market Value', 'P&L', 'P&L %']
    st.dataframe(df_display, use_container_width=True)

st.markdown('---')
col1, col2 = st.columns(2)

with col1:
    st.subheader('Portfolio Weights')
    weights_df = pd.DataFrame(weighted)
    if not weights_df.empty and 'weight_pct' in weights_df.columns:
        fig = px.pie(weights_df, values='weight_pct', names='symbol', title='Position Weights (%)')
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader('P&L by Position')
    pnl_df = pd.DataFrame(enriched)
    if not pnl_df.empty:
        fig2 = px.bar(pnl_df, x='symbol', y='pnl', title='P&L by Position ($)',
                      color='pnl', color_continuous_scale=['red', 'green'])
        st.plotly_chart(fig2, use_container_width=True)

st.caption('Last updated: ' + summary['as_of'])