import streamlit as st

st.set_page_config(
    page_title='Portfolio Manager',
    page_icon='📊',
    layout='wide',
    initial_sidebar_state='expanded'
)

st.sidebar.title('📊 Portfolio Manager')
st.sidebar.markdown('---')

st.title('Welcome to Portfolio Manager')
st.markdown('''
Use the sidebar to navigate between modules:

- **Portfolio Overview** — P&L, positions summary
- **SPAN Calculator** — Margin requirements per position
- **Risk Intelligence** — AI-powered risk narratives
- **Position Manager** — Add, edit, manage positions
''')

st.info('👈 Select a page from the sidebar to get started.')
