import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.portfolio import add_position
from utils.s3 import save_positions, load_positions
from utils.webull import get_account_list, get_account_positions, get_stock_quote

st.set_page_config(page_title="Position Manager", page_icon="📋", layout="wide")
st.title("Position Manager")

if "positions" not in st.session_state:
    st.session_state.positions = load_positions()
if "webull_raw" not in st.session_state:
    st.session_state.webull_raw = []

# ── SECTION 1: COMBINED PORTFOLIO ──────────────────────────────────────
st.subheader("Section 1 — Combined Portfolio")
if not st.session_state.positions:
    st.info("No positions yet. Add manually or sync from Webull below.")
else:
    col_refresh, col_clear = st.columns([1, 1])
    with col_refresh:
        if st.button("Refresh Live Prices"):
            with st.spinner("Fetching latest prices from Webull..."):
                updated = 0
                for i, pos in enumerate(st.session_state.positions):
                    live_price = get_stock_quote(pos.get("symbol", ""))
                    if live_price > 0:
                        st.session_state.positions[i]["price"] = live_price
                        updated += 1
                save_positions(st.session_state.positions)
                st.success("Updated prices for " + str(updated) + " positions!")
                st.rerun()
    with col_clear:
        if st.button("Clear All Positions"):
            st.session_state.positions = []
            save_positions([])
            st.rerun()

    st.markdown("")
    cols = st.columns([2, 1, 1, 1, 1, 1])
    cols[0].markdown("**Symbol**")
    cols[1].markdown("**Source**")
    cols[2].markdown("**Qty**")
    cols[3].markdown("**Entry $**")
    cols[4].markdown("**Price $**")
    cols[5].markdown("**Action**")
    for i, pos in enumerate(st.session_state.positions):
        col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 1, 1, 1, 1])
        with col1:
            st.write("**" + pos.get("symbol", "") + "**")
        with col2:
            st.write("Webull" if pos.get("source") == "webull" else "Manual")
        with col3:
            st.write(str(pos.get("quantity", 0)))
        with col4:
            st.write("$" + str(round(pos.get("entry_price", 0), 2)))
        with col5:
            new_price = st.number_input(
                "p", value=float(pos.get("price", 0)),
                key="cp_" + str(i) + "_" + pos.get("symbol", ""),
                step=0.01, label_visibility="collapsed"
            )
            if new_price != pos.get("price", 0):
                st.session_state.positions[i]["price"] = new_price
                save_positions(st.session_state.positions)
        with col6:
            if st.button("Remove", key="rm_" + str(i) + "_" + pos.get("symbol", "")):
                st.session_state.positions.pop(i)
                save_positions(st.session_state.positions)
                st.rerun()

st.markdown("---")

# ── SECTION 2: MANUAL POSITIONS ────────────────────────────────────────
st.subheader("Section 2 — Add Manual Position")
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    symbol = st.text_input("Symbol", placeholder="ES, BTC, GC...")
with col2:
    quantity = st.number_input("Quantity", value=1, step=1)
with col3:
    entry_price = st.number_input("Entry Price", value=0.0, step=0.01)
with col4:
    current_price = st.number_input("Current Price", value=0.0, step=0.01)
with col5:
    is_short_option = st.checkbox("Short Option?")

if st.button("Add Position", type="primary"):
    if symbol and entry_price > 0 and current_price > 0:
        new_pos = {
            "symbol":          symbol.upper(),
            "quantity":        quantity,
            "entry_price":     entry_price,
            "price":           current_price,
            "is_short_option": is_short_option,
            "source":          "manual"
        }
        st.session_state.positions = add_position(st.session_state.positions, new_pos)
        save_positions(st.session_state.positions)
        st.success("Added " + symbol.upper())
        st.rerun()
    else:
        st.error("Please fill in symbol, entry price and current price.")

manual_positions = [p for p in st.session_state.positions if p.get("source") == "manual"]
if manual_positions:
    st.markdown("**Current Manual Positions:**")
    for p in manual_positions:
        st.write("- " + p.get("symbol", "") + " | Qty: " + str(p.get("quantity")) + " | Entry: $" + str(round(p.get("entry_price", 0), 2)) + " | Price: $" + str(round(p.get("price", 0), 2)))

st.markdown("---")

# ── SECTION 3: WEBULL POSITIONS ────────────────────────────────────────
st.subheader("Section 3 — Webull Positions")

if st.button("Fetch from Webull", type="primary"):
    with st.spinner("Connecting to Webull..."):
        accounts = get_account_list()
        all_pos = []
        for acc in accounts:
            pos = get_account_positions(acc["account_id"])
            if pos:
                all_pos.extend(pos)
        seen = set()
        unique = []
        for p in all_pos:
            if p["symbol"] not in seen:
                seen.add(p["symbol"])
                unique.append(p)
        st.session_state.webull_raw = unique
        st.success("Fetched " + str(len(unique)) + " symbols from Webull!")

if st.session_state.webull_raw:
    existing_symbols = {p["symbol"]: i for i, p in enumerate(st.session_state.positions)}

    price_updated = 0
    for wp in st.session_state.webull_raw:
        sym = wp["symbol"]
        if sym in existing_symbols:
            idx = existing_symbols[sym]
            if st.session_state.positions[idx]["price"] != wp["price"]:
                st.session_state.positions[idx]["price"] = wp["price"]
                price_updated += 1
    if price_updated > 0:
        save_positions(st.session_state.positions)
        st.info("Updated prices for " + str(price_updated) + " existing positions.")

    new_positions = [wp for wp in st.session_state.webull_raw if wp["symbol"] not in existing_symbols]

    if not new_positions:
        st.success("All Webull positions already in portfolio. Prices updated.")
    else:
        st.markdown("**New positions to add (" + str(len(new_positions)) + "):**")
        cols = st.columns([2, 1, 1, 1])
        cols[0].markdown("**Symbol**")
        cols[1].markdown("**Live Price**")
        cols[2].markdown("**Entry Price**")
        cols[3].markdown("**Quantity**")

        to_add = []
        for pos in new_positions:
            symbol = pos.get("symbol", "")
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            with col1:
                st.write(symbol)
            with col2:
                st.write("$" + str(round(pos.get("price", 0), 2)))
            with col3:
                st.write("$" + str(round(pos.get("entry_price", 0), 2)))
            with col4:
                qty = st.number_input("qty", value=0, step=1, key="wqty_" + symbol, label_visibility="collapsed")
            if qty != 0:
                to_add.append({
                    "symbol":          symbol,
                    "quantity":        qty,
                    "entry_price":     pos.get("entry_price", 0),
                    "price":           pos.get("price", 0),
                    "asset_class":     pos.get("asset_class", "equity"),
                    "is_short_option": False,
                    "source":          "webull"
                })

        if st.button("Add Selected to Portfolio", type="primary"):
            if to_add:
                for p in to_add:
                    st.session_state.positions.append(p)
                save_positions(st.session_state.positions)
                st.success("Added " + str(len(to_add)) + " positions!")
                st.rerun()
            else:
                st.error("Set at least one quantity above.")

st.markdown("---")

# ── SECTION 4: PRE-TRADE MARGIN CHECKER (IBKR) ─────────────────────────
st.subheader("Section 4 — Pre-Trade Margin Checker")
st.caption("Uses IBKR paper account to calculate real margin impact before placing a trade.")

wi_col1, wi_col2, wi_col3, wi_col4 = st.columns(4)
with wi_col1:
    wi_symbol = st.text_input("Symbol", placeholder="AAPL, MSFT...", key="wi_symbol").upper()
with wi_col2:
    wi_quantity = st.number_input("Quantity", min_value=1, value=10, step=1, key="wi_qty")
with wi_col3:
    wi_side = st.selectbox("Side", ["BUY", "SELL"], key="wi_side")
with wi_col4:
    wi_order_type = st.selectbox("Order Type", ["MKT", "LMT"], key="wi_order_type")

wi_limit_price = 0.0
if wi_order_type == "LMT":
    wi_limit_price = st.number_input("Limit Price", min_value=0.01, value=100.0, step=0.01, key="wi_limit_price")

if st.button("🔍 Check Margin Impact", type="primary", key="wi_check"):
    if not wi_symbol:
        st.error("Please enter a symbol.")
    else:
        with st.spinner(f"Checking margin impact for {wi_side} {wi_quantity} {wi_symbol}..."):
            try:
                from utils.ibkr import whatif_order
                result = whatif_order(wi_symbol, wi_quantity, wi_order_type, wi_side, wi_limit_price)

                if result.get("error"):
                    st.error(f"IBKR error: {result['error']}")
                else:
                    st.success("Margin check complete!")

                    r1, r2, r3, r4, r5 = st.columns(5)
                    with r1:
                        st.metric("Trade Amount",
                                  f"${result['trade_amount']:,.2f}" if result.get("trade_amount") else "N/A")
                    with r2:
                        st.metric("Margin Impact",
                                  f"${result['margin_impact']:,.2f}" if result.get("margin_impact") else "N/A",
                                  help="Initial margin added by this trade")
                    with r3:
                        st.metric("Initial Margin (after)",
                                  f"${result['initial_margin']:,.2f}" if result.get("initial_margin") else "N/A")
                    with r4:
                        st.metric("Maintenance Margin (after)",
                                  f"${result['maintenance_margin']:,.2f}" if result.get("maintenance_margin") else "N/A")
                    with r5:
                        st.metric("Commission",
                                  f"${result['commission']:,.2f}" if result.get("commission") else "N/A")

                    # Buying power impact
                    cf  = result.get("current_funds")
                    ptf = result.get("post_trade_funds")
                    if cf is not None and ptf is not None:
                        bp_change = ptf - cf
                        color = "#cc3300" if bp_change < 0 else "#1a9e3f"
                        st.markdown(
                            f'<div style="padding:10px 14px;border-radius:6px;background:#1e1e1e;'
                            f'border-left:4px solid {color};margin-top:12px;">'
                            f'<span style="color:#aaa;font-size:13px;">Buying Power</span>&nbsp;&nbsp;'
                            f'<span style="color:#fff;font-size:15px;">${cf:,.2f}</span>'
                            f'<span style="color:#aaa;font-size:13px;"> → </span>'
                            f'<span style="color:{color};font-size:15px;font-weight:600;">${ptf:,.2f}</span>'
                            f'&nbsp;<span style="color:{color};font-size:13px;">({bp_change:+,.2f})</span>'
                            f'</div>',
                            unsafe_allow_html=True
                        )

                    if result.get("warnings"):
                        for w in result["warnings"]:
                            st.warning(w)

            except Exception as e:
                st.error(f"Could not connect to IBKR gateway: {str(e)}")
                st.info("Make sure the IBKR Client Portal Gateway is running on localhost:5000")