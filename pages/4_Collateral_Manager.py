import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.express as px

from core.collateral_manager import (
    add_collateral, get_collateral, remove_collateral,
    update_collateral, update_collateral_price,
    get_collateral_summary, get_default_haircut
)
from core.security_master import search_instruments

st.set_page_config(page_title="Collateral Manager", page_icon="🏦", layout="wide")
st.title("🏦 Collateral Manager")
st.caption("Track collateral inventory, haircuts, and available collateral value.")

ASSET_CLASSES  = ["CASH", "STK", "ETF", "BOND", "COMMODITY", "CRYPTO"]
CUSTODIANS     = ["IBKR", "DTC", "Euroclear", "Clearstream", "BNY Mellon", "JPMorgan", "Other"]
CURRENCIES     = ["USD", "EUR", "GBP", "JPY", "INR", "BTC", "ETH"]
BOND_SUB_TYPES = {
    "TREASURY_SHORT": "US Treasury < 1yr",
    "TREASURY_MED":   "US Treasury 1-3yr",
    "TREASURY_LONG":  "US Treasury 3-7yr",
    "TREASURY_XLONG": "US Treasury 7yr+",
    "IG_CORP":        "Investment Grade Corp",
    "HY_CORP":        "High Yield Corp",
}

# Map collateral asset class to security master asset class
AC_TO_SM_MAP = {
    "STK":       "STK",
    "ETF":       "STK",
    "BOND":      "BOND",
    "COMMODITY": "FUT",
    "CRYPTO":    "CRYPTO",
}

tab1, tab2, tab3 = st.tabs(["📊 Summary", "📋 Inventory", "➕ Add Collateral"])

# ── TAB 1: SUMMARY ──────────────────────────────────────────────────────
with tab1:
    summary = get_collateral_summary()

    if summary["total_market_value"] == 0:
        st.info("No collateral recorded yet. Add collateral using the 'Add Collateral' tab.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Market Value",     f"${summary['total_market_value']:,.2f}")
        with col2:
            st.metric("Total Collateral Value", f"${summary['total_collateral_value']:,.2f}",
                      help="Market value after applying haircuts")
        with col3:
            haircut_amt = summary["total_market_value"] - summary["total_collateral_value"]
            st.metric("Total Haircut Amount",   f"${haircut_amt:,.2f}")
        with col4:
            st.metric("Avg Effective Haircut",  f"{summary['avg_haircut_pct']:.1f}%")

        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Collateral by Asset Class**")
            ac_data = []
            for ac, vals in summary["by_asset_class"].items():
                ac_data.append({
                    "Asset Class":          ac,
                    "Market Value ($)":     f"${vals['market_value']:,.2f}",
                    "Collateral Value ($)": f"${vals['collateral_value']:,.2f}",
                    "Haircut ($)":          f"${vals['market_value'] - vals['collateral_value']:,.2f}",
                    "Items":                vals["count"],
                })
            st.dataframe(pd.DataFrame(ac_data), use_container_width=True, hide_index=True)
        with col2:
            pie_data = [{"Asset Class": ac, "Collateral Value": vals["collateral_value"]}
                        for ac, vals in summary["by_asset_class"].items()
                        if vals["collateral_value"] > 0]
            if pie_data:
                fig = px.pie(pd.DataFrame(pie_data), values="Collateral Value", names="Asset Class",
                             title="Collateral Value Distribution",
                             color_discrete_sequence=px.colors.qualitative.Set2)
                fig.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        bar_data = pd.DataFrame(
            [{"Asset Class": ac, "Type": "Market Value",     "Value": vals["market_value"]}
             for ac, vals in summary["by_asset_class"].items()] +
            [{"Asset Class": ac, "Type": "Collateral Value", "Value": vals["collateral_value"]}
             for ac, vals in summary["by_asset_class"].items()]
        )
        fig2 = px.bar(bar_data, x="Asset Class", y="Value", color="Type", barmode="group",
                      title="Market Value vs Collateral Value by Asset Class",
                      color_discrete_map={"Market Value": "#4C9BE8", "Collateral Value": "#2ECC71"})
        st.plotly_chart(fig2, use_container_width=True)

# ── TAB 2: INVENTORY ────────────────────────────────────────────────────
with tab2:
    items = get_collateral()
    if not items:
        st.info("No collateral recorded yet.")
    else:
        ac_filter = st.selectbox("Filter by asset class", ["All"] + ASSET_CLASSES, key="inv_filter")
        filtered  = items if ac_filter == "All" else [i for i in items if i["asset_class"] == ac_filter]

        display_rows = []
        for i in filtered:
            display_rows.append({
                "ID":                 i["id"],
                "Symbol":             i["symbol"],
                "Name":               i["name"] or "",
                "Asset Class":        i["asset_class"],
                "Sub Type":           i["sub_type"] or "",
                "Qty":                i["quantity"],
                "Price ($)":          f"${i['market_price']:,.4f}",
                "Market Value ($)":   f"${i['market_value']:,.2f}",
                "Haircut %":          f"{i['haircut_pct']:.1f}%",
                "Collateral Value":   f"${i['collateral_value']:,.2f}",
                "Currency":           i["currency"],
                "Custodian":          i["custodian"] or "",
            })

        df = pd.DataFrame(display_rows)
        st.dataframe(df.drop(columns=["ID"]), use_container_width=True, hide_index=True)

        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Update Market Price**")
            price_options = {f"{i['symbol']} ({i['asset_class']})": i for i in filtered}
            selected_price = st.selectbox("Select instrument", list(price_options.keys()), key="price_sel")
            new_price = st.number_input("New Market Price ($)",
                min_value=0.0, value=float(price_options[selected_price]["market_price"]),
                step=0.01, format="%.4f", key="new_price")
            if st.button("💾 Update Price"):
                ok, msg = update_collateral_price(price_options[selected_price]["id"], new_price)
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")
        with col2:
            st.markdown("**Remove Collateral**")
            remove_options = {f"{i['symbol']} — {i['name'] or ''} ({i['asset_class']})": i["id"]
                              for i in filtered}
            selected_remove = st.selectbox("Select to remove", list(remove_options.keys()), key="remove_col")
            if st.button("🗑️ Remove Selected", type="secondary"):
                ok, msg = remove_collateral(remove_options[selected_remove])
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

# ── TAB 3: ADD COLLATERAL ───────────────────────────────────────────────
with tab3:
    st.markdown("### Add Collateral Position")

    # Step 1: Asset Class
    col1, col2 = st.columns(2)
    with col1:
        new_ac = st.selectbox("Asset Class *", ASSET_CLASSES, key="col_ac")
    with col2:
        new_custodian = st.selectbox("Custodian", CUSTODIANS, key="col_cust")

    # ── CASH — special handling ──────────────────────────────────────────
    if new_ac == "CASH":
        st.markdown("**Cash Details**")
        col1, col2, col3 = st.columns(3)
        with col1:
            new_currency = st.selectbox("Currency *", CURRENCIES, key="col_ccy_cash")
        with col2:
            new_qty = st.number_input("Amount *", min_value=0.0, value=0.0,
                                      step=1000.0, key="col_qty_cash",
                                      help="Amount in the selected currency")
        with col3:
            if new_currency == "USD":
                fx_rate = 1.0
                st.number_input("FX Rate to USD", value=1.0, disabled=True,
                                key="col_fx_disabled",
                                help="USD/USD = 1.0 (fixed)")
            else:
                fx_rate = st.number_input(
                    f"FX Rate ({new_currency}/USD) *",
                    min_value=0.0001, value=1.0, step=0.0001,
                    format="%.4f", key="col_fx_rate",
                    help=f"How many USD per 1 {new_currency}. E.g. EUR/USD = 1.08"
                )

        usd_value = new_qty * fx_rate
        new_sub_type = "USD" if new_currency == "USD" else "NON_USD"
        default_hc   = get_default_haircut("CASH", new_sub_type)
        hc_key       = f"col_hc_CASH_{new_currency}"
        if st.session_state.get("_last_hc_key") != hc_key:
            st.session_state["_last_hc_key"]    = hc_key
            st.session_state["_current_hc_val"] = default_hc
        new_haircut = st.number_input(
            f"Haircut % — default for {new_currency}: {default_hc:.1f}%",
            min_value=0.0, max_value=100.0,
            value=st.session_state["_current_hc_val"],
            step=0.5, format="%.1f", key=hc_key
        )
        st.session_state["_current_hc_val"] = new_haircut

        if new_qty > 0:
            cv = usd_value * (1 - new_haircut / 100)
            st.markdown("---")
            st.markdown("**Preview**")
            p1, p2, p3, p4, p5 = st.columns(5)
            p1.metric(f"Amount ({new_currency})", f"{new_qty:,.2f}")
            p2.metric("FX Rate",                  f"{fx_rate:.4f}")
            p3.metric("USD Value",                f"${usd_value:,.2f}")
            p4.metric("Haircut %",                f"{new_haircut:.1f}%")
            p5.metric("Collateral Value (USD)",   f"${cv:,.2f}")

        st.markdown("")
        if st.button("➕ Add Cash Collateral", type="primary", key="col_add_cash"):
            if new_qty <= 0:
                st.error("❌ Amount must be greater than 0.")
            else:
                payload = {
                    "asset_class":  "CASH",
                    "symbol":       new_currency,
                    "name":         f"Cash {new_currency}",
                    "sub_type":     new_sub_type,
                    "quantity":     new_qty,
                    "market_price": fx_rate,   # store FX rate as price → market_value = qty × fx = USD value
                    "currency":     new_currency,
                    "haircut_pct":  new_haircut,
                    "custodian":    new_custodian,
                    "source":       "manual",
                }
                ok, msg = add_collateral(payload)
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

    # ── NON-CASH ASSET CLASSES ───────────────────────────────────────────
    else:
        # Symbol dropdown from Security Master filtered by asset class
        sm_ac   = AC_TO_SM_MAP.get(new_ac, new_ac)
        sm_insts = search_instruments("", sm_ac)

        if sm_insts:
            inst_options = {"— enter manually —": None}
            inst_options.update({
                f"{i['symbol']} — {i['name'] or ''} ({i['asset_class']})": i
                for i in sm_insts
            })
            selected_inst = st.selectbox(
                f"Select from Security Master ({new_ac})",
                list(inst_options.keys()), key="col_sm_sel"
            )
            prefill = inst_options[selected_inst] or {}
        else:
            st.caption(f"No {new_ac} instruments in Security Master — enter manually below.")
            prefill = {}

        col1, col2, col3 = st.columns(3)
        with col1:
            new_symbol = st.text_input("Symbol *",
                value=prefill.get("symbol", ""),
                placeholder="AAPL, GC...", key="col_sym").upper()
        with col2:
            new_name = st.text_input("Name",
                value=prefill.get("name") or "",
                placeholder="Apple Inc", key="col_name")
        with col3:
            currencies = ["USD", "EUR", "GBP", "JPY", "INR"]
            ccy_index  = currencies.index(prefill["currency"]) if prefill.get("currency") in currencies else 0
            new_currency = st.selectbox("Currency", currencies, index=ccy_index, key="col_ccy")

        col1, col2 = st.columns(2)
        with col1:
            new_qty = st.number_input("Quantity *", min_value=0.0, value=0.0,
                                      step=1.0, key="col_qty")
        with col2:
            new_price = st.number_input("Market Price ($) *", min_value=0.0, value=0.0,
                                        step=0.01, format="%.4f", key="col_price")

        # Sub-type for bond
        new_sub_type = None
        if new_ac == "BOND":
            st.markdown("**Bond Details**")
            sub_label    = st.selectbox("Bond Type", list(BOND_SUB_TYPES.values()), key="col_bond_sub")
            new_sub_type = {v: k for k, v in BOND_SUB_TYPES.items()}[sub_label]

        # Haircut auto-fill
        hc_key     = f"col_hc_{new_ac}_{new_symbol}_{new_sub_type}"
        default_hc = get_default_haircut(new_ac, new_sub_type, new_symbol)
        if st.session_state.get("_last_hc_key") != hc_key:
            st.session_state["_last_hc_key"]    = hc_key
            st.session_state["_current_hc_val"] = default_hc

        new_haircut = st.number_input(
            f"Haircut % — default for {new_ac}: {default_hc:.1f}% (override if needed)",
            min_value=0.0, max_value=100.0,
            value=st.session_state["_current_hc_val"],
            step=0.5, format="%.1f", key=hc_key
        )
        st.session_state["_current_hc_val"] = new_haircut

        # Live preview
        if new_qty > 0 and new_price > 0:
            mv     = new_qty * new_price
            cv     = mv * (1 - new_haircut / 100)
            hc_amt = mv - cv
            st.markdown("---")
            st.markdown("**Preview**")
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Market Value",     f"${mv:,.2f}")
            p2.metric("Haircut Amount",   f"${hc_amt:,.2f}")
            p3.metric("Collateral Value", f"${cv:,.2f}")
            p4.metric("Haircut %",        f"{new_haircut:.1f}%")

        st.markdown("")
        if st.button("➕ Add to Collateral", type="primary", key="col_add"):
            if not new_symbol or new_qty <= 0 or new_price <= 0:
                st.error("❌ Symbol, Quantity and Market Price are required.")
            else:
                payload = {
                    "asset_class":  new_ac,
                    "symbol":       new_symbol,
                    "name":         new_name or None,
                    "sub_type":     new_sub_type,
                    "quantity":     new_qty,
                    "market_price": new_price,
                    "currency":     new_currency,
                    "haircut_pct":  new_haircut,
                    "custodian":    new_custodian,
                    "source":       "manual",
                }
                ok, msg = add_collateral(payload)
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")