import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from core.security_master import (
    search_instruments, add_instrument, update_instrument,
    deactivate_instrument, seed_default_instruments, get_all_asset_classes
)

st.set_page_config(page_title="Security Master", page_icon="🗂️", layout="wide")
st.title("🗂️ Security Master")
st.caption("Unified instrument database across all asset classes.")

# Seed defaults on first load
seed_default_instruments()

ASSET_CLASSES = ["STK", "FUT", "OPT", "CRYPTO", "BOND", "SWAP"]
MARGIN_METHODS = ["REGT", "SPAN", "BLACK_SCHOLES", "IBKR", "ISDA_SIMM"]
EXCHANGES = ["NYSE", "NASDAQ", "CME", "CBOT", "NYMEX", "COMEX", "CBOE", "IBKR", "OTHER"]

tab1, tab2 = st.tabs(["📋 View & Search", "➕ Add Instrument"])

# ── TAB 1: VIEW & SEARCH ────────────────────────────────────────────────
with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("🔍 Search by symbol or name", placeholder="AAPL, Gold, ES...")
    with col2:
        asset_filter = st.selectbox("Filter by asset class", ["All"] + ASSET_CLASSES)

    instruments = search_instruments(query, asset_filter)

    if not instruments:
        st.info("No instruments found. Add some using the 'Add Instrument' tab.")
    else:
        st.markdown(f"**{len(instruments)} instrument(s) found**")

        # Group by asset class for clean display
        df = pd.DataFrame(instruments)

        # Select display columns — show relevant ones, hide nulls
        base_cols = ["symbol", "name", "asset_class", "exchange", "currency", "margin_method", "conid"]
        fut_cols  = ["cme_product_code", "contract_size", "tick_size", "tick_value", "expiry"]
        opt_cols  = ["underlying_symbol", "strike", "option_right", "multiplier", "expiry"]

        # Always show base; conditionally show asset-specific cols
        show_cols = base_cols.copy()
        if asset_filter in ["FUT", "All"]:
            show_cols += [c for c in fut_cols if c not in show_cols]
        if asset_filter in ["OPT", "All"]:
            show_cols += [c for c in opt_cols if c not in show_cols and c not in fut_cols]

        # Only include columns that exist in df
        show_cols = [c for c in show_cols if c in df.columns]
        df_display = df[show_cols + ["id"]].copy()

        # Rename for display
        df_display = df_display.rename(columns={
            "symbol": "Symbol", "name": "Name", "asset_class": "Asset Class",
            "exchange": "Exchange", "currency": "CCY", "margin_method": "Margin Method",
            "conid": "IBKR ConID", "cme_product_code": "CME Code",
            "contract_size": "Contract Size", "tick_size": "Tick Size",
            "tick_value": "Tick Value ($)", "expiry": "Expiry",
            "underlying_symbol": "Underlying", "strike": "Strike",
            "option_right": "C/P", "multiplier": "Multiplier"
        })

        st.dataframe(df_display.drop(columns=["id"]), use_container_width=True)

        # Remove instrument
        st.markdown("---")
        st.markdown("**Remove Instrument**")
        remove_options = {f"{r['symbol']} — {r['name'] or ''} ({r['asset_class']})": r["id"] for r in instruments}
        selected_remove = st.selectbox("Select instrument to remove", list(remove_options.keys()), key="remove_sel")
        if st.button("🗑️ Remove Selected", type="secondary"):
            ok, msg = deactivate_instrument(remove_options[selected_remove])
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

# ── TAB 2: ADD INSTRUMENT ───────────────────────────────────────────────
with tab2:
    st.markdown("### Add New Instrument")

    col1, col2, col3 = st.columns(3)
    with col1:
        new_symbol = st.text_input("Symbol *", placeholder="ES, AAPL, BTC...").upper()
    with col2:
        new_name = st.text_input("Name", placeholder="E-mini S&P 500 Futures")
    with col3:
        new_asset_class = st.selectbox("Asset Class *", ASSET_CLASSES)

    col1, col2, col3 = st.columns(3)
    with col1:
        new_exchange = st.selectbox("Exchange", EXCHANGES)
    with col2:
        new_currency = st.selectbox("Currency", ["USD", "EUR", "GBP", "JPY", "INR"])
    with col3:
        new_margin_method = st.selectbox("Margin Method", MARGIN_METHODS,
            index=MARGIN_METHODS.index("SPAN" if new_asset_class == "FUT"
                  else "BLACK_SCHOLES" if new_asset_class == "OPT"
                  else "IBKR" if new_asset_class == "CRYPTO"
                  else "REGT"))

    new_conid = st.number_input("IBKR ConID (optional)", min_value=0, value=0, step=1)

    # Asset-class specific fields
    new_cme_code = new_contract_size = new_tick_size = new_tick_value = None
    new_expiry = new_underlying = new_strike = new_right = new_multiplier = None

    if new_asset_class == "FUT":
        st.markdown("**Futures Contract Specs**")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            new_cme_code = st.text_input("CME Product Code", placeholder="ES")
        with col2:
            new_contract_size = st.number_input("Contract Size", min_value=0.0, value=0.0, step=1.0)
        with col3:
            new_tick_size = st.number_input("Tick Size", min_value=0.0, value=0.0, format="%.4f")
        with col4:
            new_tick_value = st.number_input("Tick Value ($)", min_value=0.0, value=0.0, step=0.01)
        with col5:
            new_expiry = st.text_input("Expiry (YYYYMMDD)", placeholder="20250620")

    if new_asset_class == "OPT":
        st.markdown("**Options Contract Specs**")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            new_underlying = st.text_input("Underlying Symbol", placeholder="SPY")
        with col2:
            new_strike = st.number_input("Strike Price", min_value=0.0, value=0.0, step=0.5)
        with col3:
            new_right = st.selectbox("Call / Put", ["C", "P"])
        with col4:
            new_multiplier = st.number_input("Multiplier", min_value=0.0, value=100.0, step=1.0)
        with col5:
            new_expiry = st.text_input("Expiry (YYYYMMDD)", placeholder="20250620")

    st.markdown("")
    if st.button("➕ Add to Security Master", type="primary"):
        if not new_symbol or not new_asset_class:
            st.error("Symbol and Asset Class are required.")
        else:
            payload = {
                "symbol":           new_symbol,
                "name":             new_name,
                "asset_class":      new_asset_class,
                "exchange":         new_exchange,
                "currency":         new_currency,
                "margin_method":    new_margin_method,
                "conid":            int(new_conid) if new_conid else None,
                "cme_product_code": new_cme_code or None,
                "contract_size":    new_contract_size or None,
                "tick_size":        new_tick_size or None,
                "tick_value":       new_tick_value or None,
                "expiry":           new_expiry or None,
                "underlying_symbol":new_underlying or None,
                "strike":           new_strike or None,
                "option_right":     new_right if new_asset_class == "OPT" else None,
                "multiplier":       new_multiplier or None,
            }
            ok, msg = add_instrument(payload)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)