import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.express as px

from core.position_store import (
    add_position, get_positions, update_position_price,
    close_position, get_portfolio_summary
)
from core.security_master import search_instruments, get_instrument

st.set_page_config(page_title="Positions", page_icon="📈", layout="wide")
st.title("📈 Position Manager")
st.caption("Unified position store across all asset classes.")

ASSET_CLASSES = ["STK", "FUT", "OPT", "CRYPTO", "BOND"]
SIDES         = ["LONG", "SHORT"]
SOURCES       = ["manual", "ibkr", "webull"]

tab1, tab2, tab3 = st.tabs(["📊 Portfolio Summary", "📋 Open Positions", "➕ Add Position"])

# ── TAB 1: PORTFOLIO SUMMARY ─────────────────────────────────────────────
with tab1:
    summary = get_portfolio_summary()

    if summary["total_notional"] == 0:
        st.info("No open positions yet. Add positions using the 'Add Position' tab.")
    else:
        # Top metrics
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total Notional",       f"${summary['total_notional']:,.2f}")
        with col2:
            st.metric("Total Market Value",   f"${summary['total_market_value']:,.2f}")
        with col3:
            pnl = summary["total_unrealized_pnl"]
            st.metric("Unrealized P&L",       f"${pnl:,.2f}",
                      delta=f"{'▲' if pnl >= 0 else '▼'} ${abs(pnl):,.2f}",
                      delta_color="normal")
        with col4:
            st.metric("Initial Margin Used",  f"${summary['total_initial_margin']:,.2f}")
        with col5:
            st.metric("Maint. Margin Used",   f"${summary['total_maintenance_margin']:,.2f}")

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Exposure by Asset Class**")
            ac_rows = []
            for ac, vals in summary["by_asset_class"].items():
                ac_rows.append({
                    "Asset Class":    ac,
                    "Positions":      vals["count"],
                    "Notional ($)":   f"${vals['notional']:,.2f}",
                    "Unrealized P&L": f"${vals['pnl']:,.2f}",
                    "Initial Margin": f"${vals['initial_margin']:,.2f}",
                })
            st.dataframe(pd.DataFrame(ac_rows), use_container_width=True, hide_index=True)

        with col2:
            # Notional by asset class pie
            pie_data = [
                {"Asset Class": ac, "Notional": vals["notional"]}
                for ac, vals in summary["by_asset_class"].items()
                if vals["notional"] > 0
            ]
            if pie_data:
                fig = px.pie(pd.DataFrame(pie_data),
                             values="Notional", names="Asset Class",
                             title="Notional Exposure by Asset Class",
                             color_discrete_sequence=px.colors.qualitative.Set2)
                fig.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # P&L bar by position
        positions = summary["positions"]
        if positions:
            pnl_df = pd.DataFrame([{
                "Symbol":         p["symbol"],
                "Unrealized P&L": p["unrealized_pnl"],
                "Asset Class":    p["asset_class"],
            } for p in positions])
            fig2 = px.bar(pnl_df, x="Symbol", y="Unrealized P&L",
                          color="Unrealized P&L",
                          color_continuous_scale=["#cc3300", "#2ECC71"],
                          title="Unrealized P&L by Position")
            st.plotly_chart(fig2, use_container_width=True)

# ── TAB 2: OPEN POSITIONS ────────────────────────────────────────────────
with tab2:
    col1, col2 = st.columns([2, 1])
    with col1:
        ac_filter = st.selectbox("Filter by asset class", ["All"] + ASSET_CLASSES, key="pos_filter")
    with col2:
        show_closed = st.checkbox("Show closed positions", value=False)

    status   = "closed" if show_closed else "open"
    positions = get_positions(status, ac_filter if ac_filter != "All" else None)

    if not positions:
        st.info("No positions found.")
    else:
        display_rows = []
        for p in positions:
            pnl_pct = ((p["current_price"] - p["entry_price"]) / p["entry_price"] * 100
                       if p["entry_price"] > 0 else 0)
            if p["side"] == "SHORT":
                pnl_pct = -pnl_pct
            display_rows.append({
                "ID":              p["id"],
                "Symbol":          p["symbol"],
                "Asset Class":     p["asset_class"],
                "Side":            p["side"],
                "Qty":             p["quantity"],
                "Entry ($)":       f"${p['entry_price']:,.4f}",
                "Current ($)":     f"${p['current_price']:,.4f}",
                "Notional ($)":    f"${p['notional_value']:,.2f}",
                "Mkt Value ($)":   f"${p['market_value']:,.2f}",
                "Unreal P&L ($)":  f"${p['unrealized_pnl']:,.2f}",
                "P&L %":           f"{pnl_pct:.2f}%",
                "Init Margin ($)": f"${p['initial_margin']:,.2f}",
                "Source":          p["source"],
                "Expiry":          p["expiry"] or "",
            })

        df = pd.DataFrame(display_rows)
        st.dataframe(df.drop(columns=["ID"]), use_container_width=True, hide_index=True)

        if not show_closed:
            st.markdown("---")
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Update Current Price**")
                price_opts = {f"{p['symbol']} | {p['side']} {p['quantity']} ({p['asset_class']})": p
                              for p in positions}
                sel_price = st.selectbox("Select position", list(price_opts.keys()), key="upd_price_sel")
                new_px    = st.number_input("New Price ($)",
                    min_value=0.0,
                    value=float(price_opts[sel_price]["current_price"]),
                    step=0.01, format="%.4f", key="new_px")
                if st.button("💾 Update Price", key="upd_px_btn"):
                    ok, msg = update_position_price(price_opts[sel_price]["id"], new_px)
                    if ok:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")

            with col2:
                st.markdown("**Close Position**")
                close_opts = {f"{p['symbol']} | {p['side']} {p['quantity']} ({p['asset_class']})": p["id"]
                              for p in positions}
                sel_close = st.selectbox("Select position to close", list(close_opts.keys()), key="close_sel")
                if st.button("🔴 Close Position", type="secondary", key="close_btn"):
                    ok, msg = close_position(close_opts[sel_close])
                    if ok:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")

# ── TAB 3: ADD POSITION ──────────────────────────────────────────────────
with tab3:
    st.markdown("### Add New Position")

    # Pull instruments from security master for dropdown
    all_instruments = search_instruments("", "All")
    inst_map = {
        f"{i['symbol']} — {i['name'] or ''} ({i['asset_class']})": i
        for i in all_instruments
    }

    use_master = st.checkbox("Select from Security Master", value=True, key="use_master")

    prefill = {}
    if use_master and inst_map:
        selected_inst = st.selectbox("Select Instrument", list(inst_map.keys()), key="inst_sel")
        prefill = inst_map[selected_inst]
        st.info(f"Pre-filled from Security Master — adjust fields as needed.")

    col1, col2, col3 = st.columns(3)
    with col1:
        new_symbol = st.text_input("Symbol *",
            value=prefill.get("symbol", ""),
            key="pos_sym").upper()
    with col2:
        ac_list  = ASSET_CLASSES
        ac_index = ac_list.index(prefill["asset_class"]) if prefill.get("asset_class") in ac_list else 0
        new_ac   = st.selectbox("Asset Class *", ac_list, index=ac_index, key="pos_ac")
    with col3:
        new_side = st.selectbox("Side", SIDES, key="pos_side")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        new_qty = st.number_input("Quantity *", min_value=0.0, value=1.0, step=1.0, key="pos_qty")
    with col2:
        new_entry = st.number_input("Entry Price ($) *", min_value=0.0, value=0.0,
                                    step=0.01, format="%.4f", key="pos_entry")
    with col3:
        new_curr_px = st.number_input("Current Price ($)", min_value=0.0, value=0.0,
                                      step=0.01, format="%.4f", key="pos_curr")
    with col4:
        currencies = ["USD", "EUR", "GBP", "JPY", "INR"]
        new_ccy = st.selectbox("Currency", currencies, key="pos_ccy")

    # Asset-class specific
    new_expiry = new_strike = new_right = None
    new_mult   = float(prefill.get("multiplier") or 1)
    new_cs     = float(prefill.get("contract_size") or 1)

    if new_ac == "FUT":
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            new_expiry = st.text_input("Expiry (YYYYMMDD)",
                value=prefill.get("expiry") or "", key="pos_expiry")
        with col2:
            new_mult = st.number_input("Multiplier",
                min_value=0.0, value=new_mult, step=1.0, key="pos_mult")
        with col3:
            new_cs = st.number_input("Contract Size",
                min_value=0.0, value=new_cs, step=1.0, key="pos_cs")
        with col4:
            new_exchange = st.text_input("Exchange",
                value=prefill.get("exchange") or "", key="pos_exch")

    if new_ac == "OPT":
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            new_expiry = st.text_input("Expiry (YYYYMMDD)", key="pos_opt_expiry")
        with col2:
            new_strike = st.number_input("Strike ($)", min_value=0.0,
                value=float(prefill.get("strike") or 0.0), step=0.5, key="pos_strike")
        with col3:
            new_right = st.selectbox("Call / Put", ["C", "P"], key="pos_right")
        with col4:
            new_mult = st.number_input("Multiplier", min_value=0.0,
                value=float(prefill.get("multiplier") or 100.0), step=1.0, key="pos_opt_mult")

    col1, col2 = st.columns(2)
    with col1:
        new_source = st.selectbox("Source", SOURCES, key="pos_source")
    with col2:
        new_account = st.text_input("Account ID (optional)", key="pos_acct")

    # Live preview
    if new_qty > 0 and new_entry > 0:
        curr_px  = new_curr_px if new_curr_px > 0 else new_entry
        notional = new_qty * curr_px * new_mult * new_cs
        pnl_dir  = 1 if new_side == "LONG" else -1
        upnl     = pnl_dir * new_qty * (curr_px - new_entry) * new_mult * new_cs
        st.markdown("---")
        st.markdown("**Preview**")
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Notional Value",   f"${notional:,.2f}")
        p2.metric("Market Value",     f"${notional * pnl_dir:,.2f}")
        p3.metric("Unrealized P&L",   f"${upnl:,.2f}")
        p4.metric("Entry vs Current", f"${new_entry:,.4f} → ${curr_px:,.4f}")

    st.markdown("")
    if st.button("➕ Add Position", type="primary", key="pos_add"):
        if not new_symbol or new_qty <= 0 or new_entry <= 0:
            st.error("❌ Symbol, Quantity and Entry Price are required.")
        elif new_ac == "FUT" and not new_expiry:
            st.error("❌ Expiry is required for futures.")
        elif new_ac == "OPT" and (not new_expiry or not new_strike):
            st.error("❌ Expiry and Strike are required for options.")
        else:
            payload = {
                "symbol":        new_symbol,
                "asset_class":   new_ac,
                "name":          prefill.get("name"),
                "side":          new_side,
                "quantity":      new_qty,
                "entry_price":   new_entry,
                "current_price": new_curr_px if new_curr_px > 0 else new_entry,
                "expiry":        new_expiry,
                "strike":        new_strike,
                "option_right":  new_right,
                "multiplier":    new_mult,
                "contract_size": new_cs,
                "margin_method": prefill.get("margin_method"),
                "source":        new_source,
                "account_id":    new_account or None,
                "exchange":      prefill.get("exchange"),
                "currency":      new_ccy,
            }
            ok, msg = add_position(payload)
            if ok:
                st.success(f"✅ {msg}")
                st.rerun()
            else:
                st.error(f"❌ {msg}")