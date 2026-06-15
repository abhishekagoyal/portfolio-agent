import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from core.portfolio import calculate_portfolio_summary, calculate_pnl, get_position_weights
from utils.s3 import load_positions, load_span_results

st.set_page_config(page_title='Portfolio Overview', page_icon='📊', layout='wide')
st.title('📊 Portfolio Overview')

if 'positions' not in st.session_state:
    st.session_state.positions = load_positions()
if 'span_results' not in st.session_state:
    st.session_state.span_results = load_span_results()

if not st.session_state.positions:
    st.warning('No positions found. Add positions in Position Manager first.')
    st.stop()

summary = calculate_portfolio_summary(st.session_state.positions)
enriched = calculate_pnl(st.session_state.positions)
weighted = get_position_weights(st.session_state.positions)

st.subheader('Portfolio Summary')
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric('Total Market Value', f"")
with col2:
    st.metric('Total P&L', f"", delta=f"")
with col3:
    st.metric('Positions', summary['num_positions'])
with col4:
    st.metric('Winners', summary['winners'])
with col5:
    st.metric('Losers', summary['losers'])

if st.session_state.span_results:
    st.markdown('---')
    st.subheader('Margin Summary')
    col1, col2, col3 = st.columns(3)
    span = st.session_state.span_results
    with col1:
        st.metric('Net Margin Requirement', f"")
    with col2:
        st.metric('Spread Credits', f"")
    with col3:
        utilization = (span.get('net_margin_requirement', 0) / summary['total_market_value'] * 100) if summary['total_market_value'] else 0
        st.metric('Margin Utilization', f"{utilization:.1f}%")

st.markdown('---')
st.subheader('Position Details')
df = pd.DataFrame(enriched)
if not df.empty:
    display_cols = ['symbol', 'quantity', 'entry_price', 'price', 'market_value', 'pnl', 'pnl_pct']
    df_display = df[display_cols].copy()
    df_display.columns = ['Symbol', 'Qty', 'Entry Price', 'Current Price', 'Market Value', 'P&L', 'P&L %']
    st.dataframe(df_display, use_container_width=True)

st.markdown('---')
col1, col2 = st.columns(2)

with col1:
    st.subheader('Portfolio Weights')
    weights_df = pd.DataFrame(weighted)
    if not weights_df.empty and 'weight_pct' in weights_df.columns:
        fig = px.pie(
            weights_df,
            values='weight_pct',
            names='symbol',
            title='Position Weights (%)'
        )
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader('P&L by Position')
    pnl_df = pd.DataFrame(enriched)
    if not pnl_df.empty:
        fig2 = px.bar(
            pnl_df,
            x='symbol',
            y='pnl',
            title='P&L by Position ($)',
            color='pnl',
            color_continuous_scale=['red', 'green']
        )
        st.plotly_chart(fig2, use_container_width=True)

st.caption(f"Last updated: {summary['as_of']}")