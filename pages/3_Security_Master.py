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

# ── Seed defaults ONCE per session only ─────────────────────────────────
if "sm_seeded" not in st.session_state:
    seed_default_instruments()
    st.session_state.sm_seeded = True

ASSET_CLASSES = ["STK", "FUT", "OPT", "CRYPTO", "BOND", "SWAP"]
MARGIN_METHODS = ["REGT", "SPAN", "BLACK_SCHOLES", "IBKR", "ISDA_SIMM"]
EXCHANGES      = ["NYSE", "NASDAQ", "CME", "CBOT", "NYMEX", "COMEX", "CBOE", "IBKR", "OTHER"]

tab1, tab2, tab3 = st.tabs(["📋 View & Search", "➕ Add Instrument", "✏️ Edit Instrument"])

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
        df = pd.DataFrame(instruments)

        # Build display columns — always show base, add asset-specific where relevant
        base_cols = ["symbol", "name", "asset_class", "exchange", "currency", "margin_method", "conid"]
        fut_cols  = ["cme_product_code", "contract_size", "tick_size", "tick_value", "expiry"]
        opt_cols  = ["underlying_symbol", "strike", "option_right", "multiplier", "expiry"]

        show_cols = base_cols.copy()
        if asset_filter in ["FUT", "All"]:
            show_cols += [c for c in fut_cols if c not in show_cols]
        if asset_filter in ["OPT", "All"]:
            show_cols += [c for c in opt_cols if c not in show_cols and c not in fut_cols]

        show_cols = [c for c in show_cols if c in df.columns]

        rename_map = {
            "symbol": "Symbol", "name": "Name", "asset_class": "Asset Class",
            "exchange": "Exchange", "currency": "CCY", "margin_method": "Margin Method",
            "conid": "IBKR ConID", "cme_product_code": "CME Code",
            "contract_size": "Contract Size", "tick_size": "Tick Size",
            "tick_value": "Tick Value ($)", "expiry": "Expiry",
            "underlying_symbol": "Underlying", "strike": "Strike",
            "option_right": "C/P", "multiplier": "Multiplier"
        }

        df_display = df[show_cols + ["id"]].rename(columns=rename_map)

        # Replace None/NaN with blank for cleaner display
        df_display = df_display.fillna("")

        st.dataframe(df_display.drop(columns=["id"]), use_container_width=True)

        # Remove instrument
        st.markdown("---")
        st.markdown("**Remove Instrument**")
        remove_options = {
            f"{r['symbol']} — {r['name'] or ''} ({r['asset_class']})": r["id"]
            for r in instruments
        }
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

    # ── Pull existing symbols for the dropdown ──────────────────────────
    all_instruments = search_instruments("", "All")
    existing_symbols = sorted(set(i["symbol"] for i in all_instruments))

    st.markdown("**Option A — Select existing symbol to view/clone**")
    selected_existing = st.selectbox(
        "Pick from security master (to pre-fill or check details)",
        ["— new instrument —"] + existing_symbols,
        key="existing_pick"
    )

    # Pre-fill if an existing symbol is selected
    prefill = {}
    if selected_existing != "— new instrument —":
        match = next((i for i in all_instruments if i["symbol"] == selected_existing), None)
        if match:
            prefill = match
            st.info(f"Showing details for **{selected_existing}** — modify fields below to add a variant (e.g. different expiry), or pick a new symbol.")

    st.markdown("**Option B — Enter new instrument details**")

    col1, col2, col3 = st.columns(3)
    with col1:
        new_symbol = st.text_input("Symbol *",
            value=prefill.get("symbol", ""),
            placeholder="ES, AAPL, BTC...").upper()
    with col2:
        new_name = st.text_input("Name",
            value=prefill.get("name") or "",
            placeholder="E-mini S&P 500 Futures")
    with col3:
        ac_index = ASSET_CLASSES.index(prefill["asset_class"]) if prefill.get("asset_class") in ASSET_CLASSES else 0
        new_asset_class = st.selectbox("Asset Class *", ASSET_CLASSES, index=ac_index)

    col1, col2, col3 = st.columns(3)
    with col1:
        ex_index = EXCHANGES.index(prefill["exchange"]) if prefill.get("exchange") in EXCHANGES else 0
        new_exchange = st.selectbox("Exchange", EXCHANGES, index=ex_index)
    with col2:
        currencies = ["USD", "EUR", "GBP", "JPY", "INR"]
        cur_index = currencies.index(prefill["currency"]) if prefill.get("currency") in currencies else 0
        new_currency = st.selectbox("Currency", currencies, index=cur_index)
    with col3:
        default_mm = (
            "SPAN"          if new_asset_class == "FUT"    else
            "BLACK_SCHOLES" if new_asset_class == "OPT"    else
            "IBKR"          if new_asset_class == "CRYPTO" else
            "REGT"
        )
        mm_val = prefill.get("margin_method") or default_mm
        mm_index = MARGIN_METHODS.index(mm_val) if mm_val in MARGIN_METHODS else 0
        new_margin_method = st.selectbox("Margin Method", MARGIN_METHODS, index=mm_index)

    new_conid = st.number_input("IBKR ConID (optional)",
        min_value=0, value=int(prefill.get("conid") or 0), step=1)

    # Asset-class specific fields
    new_cme_code = new_contract_size = new_tick_size = new_tick_value = None
    new_expiry = new_underlying = new_strike = new_right = new_multiplier = None

    if new_asset_class == "FUT":
        st.markdown("**Futures Contract Specs**")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            new_cme_code = st.text_input("CME Product Code",
                value=prefill.get("cme_product_code") or "",
                placeholder="ES")
        with col2:
            new_contract_size = st.number_input("Contract Size",
                min_value=0.0,
                value=float(prefill.get("contract_size") or 0.0),
                step=1.0)
        with col3:
            new_tick_size = st.number_input("Tick Size",
                min_value=0.0,
                value=float(prefill.get("tick_size") or 0.0),
                format="%.4f")
        with col4:
            new_tick_value = st.number_input("Tick Value ($)",
                min_value=0.0,
                value=float(prefill.get("tick_value") or 0.0),
                step=0.01)
        with col5:
            new_expiry = st.text_input("Expiry (YYYYMMDD)",
                value=prefill.get("expiry") or "",
                placeholder="20250620")

    if new_asset_class == "OPT":
        st.markdown("**Options Contract Specs**")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            new_underlying = st.text_input("Underlying Symbol",
                value=prefill.get("underlying_symbol") or "",
                placeholder="SPY")
        with col2:
            new_strike = st.number_input("Strike Price",
                min_value=0.0,
                value=float(prefill.get("strike") or 0.0),
                step=0.5)
        with col3:
            rights = ["C", "P"]
            right_index = rights.index(prefill["option_right"]) if prefill.get("option_right") in rights else 0
            new_right = st.selectbox("Call / Put", rights, index=right_index)
        with col4:
            new_multiplier = st.number_input("Multiplier",
                min_value=0.0,
                value=float(prefill.get("multiplier") or 100.0),
                step=1.0)
        with col5:
            new_expiry = st.text_input("Expiry (YYYYMMDD)",
                value=prefill.get("expiry") or "",
                placeholder="20250620")

    st.markdown("")
    if st.button("➕ Add to Security Master", type="primary"):
        if not new_symbol or not new_asset_class:
            st.error("Symbol and Asset Class are required.")
        elif new_asset_class == "FUT" and not new_expiry:
            st.error("Expiry is required for futures.")
        elif new_asset_class == "OPT" and (not new_expiry or not new_strike):
            st.error("Expiry and Strike are required for options.")
        else:
            payload = {
                "symbol":            new_symbol,
                "name":              new_name or None,
                "asset_class":       new_asset_class,
                "exchange":          new_exchange,
                "currency":          new_currency,
                "margin_method":     new_margin_method,
                "conid":             int(new_conid) if new_conid else None,
                "cme_product_code":  new_cme_code or None,
                "contract_size":     new_contract_size or None,
                "tick_size":         new_tick_size or None,
                "tick_value":        new_tick_value or None,
                "expiry":            new_expiry or None,
                "underlying_symbol": new_underlying or None,
                "strike":            new_strike or None,
                "option_right":      new_right if new_asset_class == "OPT" else None,
                "multiplier":        new_multiplier or None,
            }
            ok, msg = add_instrument(payload)
            if ok:
                st.success(f"✅ {msg}")
                st.rerun()
            else:
                st.error(f"❌ {msg}")

# ── TAB 3: EDIT INSTRUMENT ──────────────────────────────────────────────
with tab3:
    st.markdown("### Edit Existing Instrument")
    st.caption("Select an instrument and update any of its attributes.")

    all_insts = search_instruments("", "All")
    if not all_insts:
        st.info("No instruments in Security Master yet.")
    else:
        edit_options = {
            f"{i['symbol']} — {i['name'] or ''} ({i['asset_class']})": i
            for i in all_insts
        }
        selected_edit = st.selectbox("Select Instrument to Edit",
                                     list(edit_options.keys()), key="edit_sel")
        ei = edit_options[selected_edit]

        st.markdown("---")
        st.markdown(f"**Editing: {ei['symbol']} (ID: {ei['id']})**")

        col1, col2, col3 = st.columns(3)
        with col1:
            e_name = st.text_input("Name", value=ei.get("name") or "", key="e_name")
        with col2:
            e_exch = st.selectbox("Exchange", EXCHANGES,
                                  index=EXCHANGES.index(ei["exchange"]) if ei.get("exchange") in EXCHANGES else 0,
                                  key="e_exch")
        with col3:
            currencies = ["USD","EUR","GBP","JPY","INR"]
            e_ccy = st.selectbox("Currency", currencies,
                                 index=currencies.index(ei["currency"]) if ei.get("currency") in currencies else 0,
                                 key="e_ccy")

        col1, col2 = st.columns(2)
        with col1:
            e_mm = st.selectbox("Margin Method", MARGIN_METHODS,
                                index=MARGIN_METHODS.index(ei["margin_method"]) if ei.get("margin_method") in MARGIN_METHODS else 0,
                                key="e_mm")
        with col2:
            e_conid = st.number_input("IBKR ConID", min_value=0,
                                      value=int(ei.get("conid") or 0), step=1, key="e_conid")

        # Futures fields
        if ei.get("asset_class") == "FUT":
            st.markdown("**Futures Contract Specs**")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                e_cme = st.text_input("CME Code", value=ei.get("cme_product_code") or "", key="e_cme")
            with col2:
                e_cs = st.number_input("Contract Size", min_value=0.0,
                                       value=float(ei.get("contract_size") or 0), step=1.0, key="e_cs")
            with col3:
                e_ts = st.number_input("Tick Size", min_value=0.0,
                                       value=float(ei.get("tick_size") or 0), format="%.4f", key="e_ts")
            with col4:
                e_tv = st.number_input("Tick Value ($)", min_value=0.0,
                                       value=float(ei.get("tick_value") or 0), step=0.01, key="e_tv")
            with col5:
                e_exp = st.text_input("Expiry (YYYYMMDD)", value=ei.get("expiry") or "", key="e_exp")

        # Options fields
        if ei.get("asset_class") == "OPT":
            st.markdown("**Options Contract Specs**")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                e_und = st.text_input("Underlying", value=ei.get("underlying_symbol") or "", key="e_und")
            with col2:
                e_str = st.number_input("Strike ($)", min_value=0.0,
                                        value=float(ei.get("strike") or 0), step=0.5, key="e_str")
            with col3:
                rights = ["C", "P"]
                e_right = st.selectbox("C/P", rights,
                                       index=rights.index(ei["option_right"]) if ei.get("option_right") in rights else 0,
                                       key="e_right")
            with col4:
                e_mult = st.number_input("Multiplier", min_value=0.0,
                                         value=float(ei.get("multiplier") or 100), step=1.0, key="e_mult")
            with col5:
                e_exp = st.text_input("Expiry (YYYYMMDD)", value=ei.get("expiry") or "", key="e_exp_opt")

        st.markdown("")
        if st.button("💾 Save Changes", type="primary", key="save_edit"):
            updates = {
                "name":          e_name or None,
                "exchange":      e_exch,
                "currency":      e_ccy,
                "margin_method": e_mm,
                "conid":         int(e_conid) if e_conid else None,
            }
            if ei.get("asset_class") == "FUT":
                updates.update({
                    "cme_product_code": e_cme or None,
                    "contract_size":    e_cs or None,
                    "tick_size":        e_ts or None,
                    "tick_value":       e_tv or None,
                    "expiry":           e_exp or None,
                })
            if ei.get("asset_class") == "OPT":
                updates.update({
                    "underlying_symbol": e_und or None,
                    "strike":            e_str or None,
                    "option_right":      e_right,
                    "multiplier":        e_mult or None,
                    "expiry":            e_exp or None,
                })
            from core.security_master import update_instrument
            ok, msg = update_instrument(ei["id"], updates)
            if ok:
                st.success(f"✅ {msg}")
                st.rerun()
            else:
                st.error(f"❌ {msg}")