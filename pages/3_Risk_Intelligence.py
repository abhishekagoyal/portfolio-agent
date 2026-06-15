import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import analyze_portfolio_risk, suggest_trades, ask_portfolio_question
from utils.s3 import load_positions, load_span_results

st.set_page_config(page_title='Risk Intelligence', page_icon='🤖', layout='wide')
st.title('🤖 Risk Intelligence')
st.caption('Powered by Claude AI')

if 'positions' not in st.session_state:
    st.session_state.positions = load_positions()
if 'span_results' not in st.session_state:
    st.session_state.span_results = load_span_results()

if not st.session_state.positions:
    st.warning('No positions found. Add positions in Position Manager first.')
    st.stop()

if not st.session_state.span_results:
    st.warning('No SPAN results found. Run the SPAN Calculator first.')
    st.stop()

tab1, tab2, tab3 = st.tabs(['Risk Narrative', 'Trade Suggestions', 'Ask a Question'])

with tab1:
    st.subheader('Portfolio Risk Narrative')
    if st.button('Generate Risk Analysis', type='primary', key='risk_btn'):
        with st.spinner('Claude is analyzing your portfolio...'):
            narrative = analyze_portfolio_risk(
                st.session_state.positions,
                st.session_state.span_results
            )
            st.session_state.risk_narrative = narrative
    if 'risk_narrative' in st.session_state:
        st.markdown(st.session_state.risk_narrative)

with tab2:
    st.subheader('Trade Suggestions')
    st.caption('Claude will suggest trades to optimize margin and risk/reward')
    if st.button('Generate Trade Ideas', type='primary', key='trade_btn'):
        with st.spinner('Claude is generating trade ideas...'):
            suggestions = suggest_trades(
                st.session_state.positions,
                st.session_state.span_results
            )
            st.session_state.trade_suggestions = suggestions
    if 'trade_suggestions' in st.session_state:
        st.markdown(st.session_state.trade_suggestions)

with tab3:
    st.subheader('Ask About Your Portfolio')
    question = st.text_input('Ask a question', placeholder='Which position has the highest margin requirement?')
    if st.button('Ask Claude', type='primary', key='ask_btn'):
        if question:
            with st.spinner('Thinking...'):
                answer = ask_portfolio_question(
                    st.session_state.positions,
                    st.session_state.span_results,
                    question
                )
                st.session_state.last_answer = answer
        else:
            st.error('Please enter a question.')
    if 'last_answer' in st.session_state:
        st.markdown(st.session_state.last_answer)