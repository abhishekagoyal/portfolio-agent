import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.portfolio import add_position, remove_position, update_position_price
from utils.s3 import save_positions, load_positions

st.set_page_config(page_title='Position Manager', page_icon='📋', layout='wide')
st.title('📋 Position Manager')

if 'positions' not in st.session_state:
    st.session_state.positions = load_positions()

st.subheader('Add New Position')
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    symbol = st.text_input('Symbol', placeholder='ES, BTC, GC...')
with col2:
    quantity = st.number_input('Quantity', value=1, step=1)
with col3:
    entry_price = st.number_input('Entry Price', value=0.0, step=0.01)
with col4:
    current_price = st.number_input('Current Price', value=0.0, step=0.01)
with col5:
    is_short_option = st.checkbox('Short Option?')

if st.button('Add Position', type='primary'):
    if symbol and entry_price > 0 and current_price > 0:
        new_pos = {
            'symbol': symbol.upper(),
            'quantity': quantity,
            'entry_price': entry_price,
            'price': current_price,
            'is_short_option': is_short_option
        }
        st.session_state.positions = add_position(st.session_state.positions, new_pos)
        save_positions(st.session_state.positions)
        st.success('Added ' + symbol.upper())
        st.rerun()
    else:
        st.error('Please fill in all fields.')

st.markdown('---')
st.subheader('Current Positions')

if not st.session_state.positions:
    st.info('No positions yet. Add one above.')
else:
    for pos in st.session_state.positions:
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
        with col1:
            st.write('**' + pos.get('symbol') + '**')
        with col2:
            st.write('Qty: ' + str(pos.get('quantity')))
        with col3:
            st.write('Entry: $' + str(round(pos.get('entry_price', 0), 2)))
        with col4:
            new_price = st.number_input(
                'Current Price',
                value=float(pos.get('price', 0)),
                key='price_' + pos.get('symbol'),
                step=0.01,
                label_visibility='collapsed'
            )
            if new_price != pos.get('price'):
                st.session_state.positions = update_position_price(
                    st.session_state.positions, pos.get('symbol'), new_price
                )
                save_positions(st.session_state.positions)
        with col5:
            if st.button('Remove', key='remove_' + pos.get('symbol')):
                st.session_state.positions = remove_position(
                    st.session_state.positions, pos.get('symbol')
                )
                save_positions(st.session_state.positions)
                st.rerun()

st.markdown('---')
if st.session_state.positions:
    if st.button('Save All to S3'):
        if save_positions(st.session_state.positions):
            st.success('Saved to S3!')
        else:
            st.error('S3 save failed. Check AWS credentials in .env')