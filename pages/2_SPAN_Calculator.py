import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.span import calculate_portfolio_margin
from utils.s3 import load_positions, save_span_results

st.set_page_config(page_title='SPAN Calculator', page_icon='📐', layout='wide')
st.title('SPAN Margin Calculator')

if 'positions' not in st.session_state:
    st.session_state.positions = load_positions()

if not st.session_state.positions:
    st.warning('No positions found. Add positions in the Position Manager first.')
    st.stop()

st.subheader('Portfolio Positions')
for pos in st.session_state.positions:
    symbol = pos.get('symbol', '')
    qty = pos.get('quantity', 0)
    price = pos.get('price', 0.0)
    st.write('Symbol: ' + symbol + ' | Qty: ' + str(qty) + ' | Price: $' + str(price))

st.markdown('---')

if st.button('Calculate SPAN Margin', type='primary'):
    with st.spinner('Calculating...'):
        results = calculate_portfolio_margin(st.session_state.positions)
        st.session_state.span_results = results
        save_span_results(results)

    st.subheader('SPAN Results')

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric('Total Scanning Risk', '$' + str(results['total_scanning_risk']))
    with col2:
        st.metric('Spread Credits', '$' + str(results['total_spread_credits']))
    with col3:
        st.metric('Short Option Min', '$' + str(results['total_som']))
    with col4:
        st.metric('Net Margin Requirement', '$' + str(results['net_margin_requirement']))

    st.markdown('---')
    st.subheader('Position Breakdown')

    import pandas as pd
    df = pd.DataFrame(results['positions'])
    if not df.empty:
        df = df[['symbol', 'asset_class', 'quantity', 'price', 'position_value', 'scanning_risk', 'som', 'margin']]
        df.columns = ['Symbol', 'Asset Class', 'Qty', 'Price', 'Position Value', 'Scanning Risk', 'SOM', 'Margin']
        st.dataframe(df, use_container_width=True)

    st.markdown('---')
    st.subheader('Spread Credits Detail')
    if results['total_spread_credits'] > 0:
        st.success('Intercommodity spread credits saved $' + str(results['total_spread_credits']) + ' in margin')
    else:
        st.info('No spread credits applied. Add offsetting positions to reduce margin.')