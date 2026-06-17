import os

with open('pages/4_Position_Manager.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "for pos in st.session_state.positions:",
    "for i, pos in enumerate(st.session_state.positions):"
)
content = content.replace(
    "key='price_' + str(pos.get('symbol')) + str(pos.get('id', ''))",
    "key='price_' + str(i) + '_' + str(pos.get('symbol'))"
)
content = content.replace(
    "key='remove_' + str(pos.get('symbol')) + str(pos.get('id', ''))",
    "key='remove_' + str(i) + '_' + str(pos.get('symbol'))"
)

with open('pages/4_Position_Manager.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
