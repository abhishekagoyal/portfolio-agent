import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core.collateral_manager import (
    add_collateral, get_collateral, remove_collateral,
    update_collateral, get_collateral_summary, get_default_haircut
)

st.set_page_config(page_title="Collateral Manager", page_icon="🏦", layout="wide")
st.title("🏦 Collateral Manager")
st.caption("Track collateral inventory, haircuts, and available collateral value.")

ASSET_CLASSES  = ["CASH", "STK", "ETF", "BOND", "COMMODITY", "CRYPTO"]
CUSTODIANS     = ["IBKR", "DTC", "Euroclear", "Clearstream", "BNY Mellon", "JPMorgan", "Other"]
CURRENCIES     = ["USD", "EUR", "GBP", "JPY", "INR", "BTC", "ETH"]

BOND_SUB_TYPES = {
    "TREASURY_SHORT":  "US Treasury < 1yr",
    "TREASURY_MED":    "US Treasury 1-3yr",
    "TREASURY_LONG":   "US Treasury 3-7yr",
    "TREASURY_XLONG":  "US Treasury 7yr+",
    "IG_CORP":         "Investment Grade Corp",
    "HY_CORP":         "High Yield Corp",
}

tab1, tab2, tab3 = st.tabs(["📊 Summary", "📋 Inventory", "➕ Add Collateral"])

# ── TAB 1: SUMMARY ──────────────────────────────────────────────────────
with tab1:
    summary = get_collateral_summary()

    if summary["total_market_value"] == 0:
        st.info("No collateral recorded yet. Add collateral using the 'Add Collateral' tab.")
    else:
        # Top metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Market Value",
                      f"${summary['total_market_value']:,.2f}")
        with col2:
            st.metric("Total Collateral Value",
                      f"${summary['total_collateral_value']:,.2f}",
                      help="Market value after applying haircuts")
        with col3:
            haircut_amt = summary["total_market_value"] - summary["total_collateral_value"]
            st.metric("Total Haircut Amount",
                      f"${haircut_amt:,.2f}")
        with col4:
            st.metric("Avg Effective Haircut",
                      f"{summary['avg_haircut_pct']:.1f}%")

        st.markdown("---")

        # By asset class breakdown
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Collateral by Asset Class**")
            ac_data = []
            for ac, vals in summary["by_asset_class"].items():
                ac_data.append({
                    "Asset Class":        ac,
                    "Market Value ($)":   f"${vals['market_value']:,.2f}",
                    "Collateral Value ($)":f"${vals['collateral_value']:,.2f}",
                    "Haircut ($)":        f"${vals['market_value'] - vals['collateral_value']:,.2f}",
                    "Items":              vals["count"],
                })
            st.dataframe(pd.DataFrame(ac_data), use_container_width=True, hide_index=True)

        with col2:
            # Pie chart — collateral value by asset class
            pie_data = [
                {"Asset Class": ac, "Collateral Value": vals["collateral_value"]}
                for ac, vals in summary["by_asset_class"].items()
                if vals["collateral_value"] > 0
            ]
            if pie_data:
                fig = px.pie(
                    pd.DataFrame(pie_data),
                    values="Collateral Value",
                    names="Asset Class",
                    title="Collateral Value Distribution",
                    color_discrete_sequence=px.colors.qualitative.Set2
                )
                fig.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Market value vs collateral value bar chart
        bar_data = pd.DataFrame([
            {"Asset Class": ac, "Type": "Market Value",     "Value": vals["market_value"]}
            for ac, vals in summary["by_asset_class"].items()
        ] + [
            {"Asset Class": ac, "Type": "Collateral Value", "Value": vals["collateral_value"]}
            for ac, vals in summary["by_asset_class"].items()
        ])

        fig2 = px.bar(
            bar_data, x="Asset Class", y="Value", color="Type",
            barmode="group",
            title="Market Value vs Collateral Value by Asset Class",
            color_discrete_map={"Market Value": "#4C9BE8", "Collateral Value": "#2ECC71"}
        )
        st.plotly_chart(fig2, use_container_width=True)

# ── TAB 2: INVENTORY ────────────────────────────────────────────────────
with tab2:
    items = get_collateral()

    if not items:
        st.info("No collateral recorded yet.")
    else:
        # Filter
        ac_filter = st.selectbox("Filter by asset class",
                                 ["All"] + ASSET_CLASSES, key="inv_filter")
        filtered = items if ac_filter == "All" else [i for i in items if i["asset_class"] == ac_filter]

        # Display table
        display_rows = []
        for i in filtered:
            display_rows.append({
                "ID":                i["id"],
                "Symbol":            i["symbol"],
                "Name":              i["name"] or "",
                "Asset Class":       i["asset_class"],
                "Sub Type":          i["sub_type"] or "",
                "Qty":               i["quantity"],
                "Price ($)":         f"${i['market_price']:,.4f}",
                "Market Value ($)":  f"${i['market_value']:,.2f}",
                "Haircut %":         f"{i['haircut_pct']:.1f}%",
                "Collateral Value":  f"${i['collateral_value']:,.2f}",
                "Currency":          i["currency"],
                "Custodian":         i["custodian"] or "",
            })

        df = pd.DataFrame(display_rows)
        st.dataframe(df.drop(columns=["ID"]), use_container_width=True, hide_index=True)

        st.markdown("---")
        col1, col2 = st.columns(2)

        # Update price
        with col1:
            st.markdown("**Update Market Price**")
            price_options = {f"{i['symbol']} ({i['asset_class']})": i for i in filtered}
            selected_price = st.selectbox("Select instrument", list(price_options.keys()), key="price_sel")
            new_price = st.number_input("New Market Price ($)",
                min_value=0.0,
                value=float(price_options[selected_price]["market_price"]),
                step=0.01, format="%.4f", key="new_price")
            if st.button("💾 Update Price"):
                from core.collateral_manager import update_collateral_price
                ok, msg = update_collateral_price(price_options[selected_price]["id"], new_price)
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

        # Remove
        with col2:
            st.markdown("**Remove Collateral**")
            remove_options = {f"{i['symbol']} — {i['name'] or ''} ({i['asset_class']})": i["id"] for i in filtered}
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

    col1, col2, col3 = st.columns(3)
    with col1:
        new_ac = st.selectbox("Asset Class *", ASSET_CLASSES, key="col_ac")
    with col2:
        new_symbol = st.text_input("Symbol *", placeholder="AAPL, BTC, GC...", key="col_sym").upper()
    with col3:
        new_name = st.text_input("Name", placeholder="Apple Inc", key="col_name")

    col1, col2, col3 = st.columns(3)
    with col1:
        new_qty = st.number_input("Quantity *", min_value=0.0, value=0.0, step=1.0, key="col_qty")
    with col2:
        new_price = st.number_input("Market Price ($) *", min_value=0.0, value=0.0,
                                    step=0.01, format="%.4f", key="col_price")
    with col3:
        new_currency = st.selectbox("Currency", CURRENCIES, key="col_ccy")

    # Sub-type for bond/crypto/commodity
    new_sub_type = None
    if new_ac == "BOND":
        st.markdown("**Bond Details**")
        sub_label = st.selectbox("Bond Type", list(BOND_SUB_TYPES.values()), key="col_bond_sub")
        new_sub_type = {v: k for k, v in BOND_SUB_TYPES.items()}[sub_label]
    elif new_ac == "CASH":
        new_sub_type = st.selectbox("Cash Currency Type", ["USD", "NON_USD"], key="col_cash_sub")

    # Auto-apply default haircut
    default_hc = get_default_haircut(new_ac, new_sub_type, new_symbol)

    col1, col2 = st.columns(2)
    with col1:
        new_haircut = st.number_input(
            "Haircut % (auto-filled, override if needed)",
            min_value=0.0, max_value=100.0,
            value=default_hc, step=0.5, format="%.1f", key="col_hc"
        )
    with col2:
        new_custodian = st.selectbox("Custodian", CUSTODIANS, key="col_cust")

    # Live preview
    if new_qty > 0 and new_price > 0:
        mv  = new_qty * new_price
        cv  = mv * (1 - new_haircut / 100)
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
            st.error("Symbol, Quantity and Market Price are required.")
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