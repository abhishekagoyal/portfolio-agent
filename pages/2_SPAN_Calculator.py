import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.express as px

from core.span import calculate_portfolio_margin
from core.var import calculate_parametric_var, calculate_historical_var
from core.scenarios import run_scenario, run_all_scenarios, get_scenario_names, get_scenario_shocks
from utils.s3 import load_positions, save_span_results

st.set_page_config(page_title="Risk Calculator", page_icon="📐", layout="wide")
st.title("Risk Calculator")

if "positions" not in st.session_state:
    st.session_state.positions = load_positions()

if not st.session_state.positions:
    st.warning("No positions found. Add positions in Position Manager first.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["SPAN & Reg T Margin", "VaR & Expected Shortfall", "Scenario Analysis"])

with tab1:
    st.subheader("Portfolio Positions")
    for pos in st.session_state.positions:
        st.write("Symbol: " + pos.get("symbol", "") + " | Qty: " + str(pos.get("quantity", 0)) + " | Price: $" + str(pos.get("price", 0.0)))

    st.markdown("---")
    if st.button("Calculate Margin", type="primary"):
        with st.spinner("Calculating..."):
            results = calculate_portfolio_margin(st.session_state.positions)
            st.session_state.span_results = results
            save_span_results(results)

        st.subheader("Total Margin Summary")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Futures Margin (SPAN)", "$" + "{:,.2f}".format(results["net_futures_margin"]))
        with col2:
            st.metric("Equity Margin (Reg T)", "$" + "{:,.2f}".format(results["net_equity_margin"]))
        with col3:
            st.metric("Total Margin Requirement", "$" + "{:,.2f}".format(results["total_margin_requirement"]))

        if results["futures_positions"]:
            st.markdown("---")
            st.subheader("Futures Positions — SPAN Margin")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Scanning Risk", "$" + "{:,.2f}".format(results["total_scanning_risk"]))
            with col2:
                st.metric("Spread Credits", "$" + "{:,.2f}".format(results["total_spread_credits"]))
            with col3:
                st.metric("Short Option Min", "$" + "{:,.2f}".format(results["total_som"]))
            with col4:
                st.metric("Net Futures Margin", "$" + "{:,.2f}".format(results["net_futures_margin"]))

            fut_df = pd.DataFrame(results["futures_positions"])
            if not fut_df.empty:
                fut_df = fut_df[["symbol", "asset_class", "quantity", "price", "position_value", "scanning_risk", "som", "margin"]]
                fut_df.columns = ["Symbol", "Asset Class", "Qty", "Price", "Position Value", "Scanning Risk", "SOM", "SPAN Margin"]
                st.dataframe(fut_df, use_container_width=True)

            if results["total_spread_credits"] > 0:
                st.success("Intercommodity spread credits saved $" + "{:,.2f}".format(results["total_spread_credits"]) + " in margin")

        if results["equity_positions"]:
            st.markdown("---")
            st.subheader("Equity Positions — Reg T Margin")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Initial Margin (50%)", "$" + "{:,.2f}".format(results["total_reg_t_initial"]))
            with col2:
                st.metric("Total Maintenance Margin (25%)", "$" + "{:,.2f}".format(results["total_reg_t_maintenance"]))
            with col3:
                total_equity_value = sum(abs(p["position_value"]) for p in results["equity_positions"])
                st.metric("Total Equity Value", "$" + "{:,.2f}".format(total_equity_value))

            eq_df = pd.DataFrame(results["equity_positions"])
            if not eq_df.empty:
                eq_df = eq_df[["symbol", "asset_class", "quantity", "price", "position_value", "margin_type", "initial_margin", "maintenance_margin", "calculation"]]
                eq_df.columns = ["Symbol", "Asset Class", "Qty", "Price", "Position Value", "Margin Type", "Initial Margin", "Maintenance Margin", "Calculation"]
                st.dataframe(eq_df, use_container_width=True)

            st.info("Reg T: 50% initial margin, 25% maintenance margin per FINRA rules. Crypto requires 100% cash.")

with tab2:
    st.subheader("Value at Risk and Expected Shortfall")
    st.caption("Calculates potential portfolio loss at given confidence levels")
    col1, col2 = st.columns(2)
    with col1:
        method = st.radio("Select Method", ["Parametric (Variance-Covariance)", "Historical Simulation", "Both"])
    with col2:
        simulations = st.slider("Simulations (Historical only)", 500, 5000, 1000, 500)

    if st.button("Calculate VaR & ES", type="primary"):
        if method == "Parametric (Variance-Covariance)" or method == "Both":
            with st.spinner("Running parametric VaR..."):
                p_var = calculate_parametric_var(st.session_state.positions)
                st.session_state.p_var = p_var
        if method == "Historical Simulation" or method == "Both":
            with st.spinner("Running " + str(simulations) + " simulations..."):
                h_var = calculate_historical_var(st.session_state.positions, simulations)
                st.session_state.h_var = h_var

    if "p_var" in st.session_state and (method == "Parametric (Variance-Covariance)" or method == "Both"):
        p = st.session_state.p_var
        st.markdown("---")
        st.subheader("Parametric VaR Results")
        st.caption("Formula: VaR = Position Value x Daily Volatility x Z-Score")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("VaR 95% 1-Day", "$" + "{:,.2f}".format(p["portfolio"]["var_95_1d"]))
        with col2:
            st.metric("VaR 99% 1-Day", "$" + "{:,.2f}".format(p["portfolio"]["var_99_1d"]))
        with col3:
            st.metric("VaR 95% 10-Day", "$" + "{:,.2f}".format(p["portfolio"]["var_95_10d"]))
        with col4:
            st.metric("VaR 99% 10-Day", "$" + "{:,.2f}".format(p["portfolio"]["var_99_10d"]))
        st.markdown("**Portfolio Calculation Steps:**")
        for k, v in p["portfolio"]["calculation"].items():
            st.write("- " + v)
        st.markdown("**Position-Level Breakdown:**")
        for pos in p["positions"]:
            with st.expander(pos["symbol"] + " - " + pos["asset_class"] + " | VaR 95%: $" + str(pos["var_95_1d"])):
                st.write("Position Value: $" + "{:,.2f}".format(pos["position_value"]))
                st.write("Annual Volatility: " + str(pos["annual_vol_pct"]) + "%")
                st.write("Daily Volatility: " + str(pos["daily_vol_pct"]) + "%")
                st.write("Z-Score 95%: " + str(pos["z_score_95"]) + " | Z-Score 99%: " + str(pos["z_score_99"]))
                st.markdown("**Calculation Steps:**")
                for k, v in pos["calculation"].items():
                    st.write("- " + str(v))
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("VaR 95% 1D", "$" + str(pos["var_95_1d"]))
                with col2:
                    st.metric("VaR 99% 1D", "$" + str(pos["var_99_1d"]))
                with col3:
                    st.metric("VaR 95% 10D", "$" + str(pos["var_95_10d"]))
                with col4:
                    st.metric("VaR 99% 10D", "$" + str(pos["var_99_10d"]))

    if "h_var" in st.session_state and (method == "Historical Simulation" or method == "Both"):
        h = st.session_state.h_var
        st.markdown("---")
        st.subheader("Historical Simulation Results")
        st.caption("Monte Carlo simulation using asset class volatilities")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("VaR 95% 1-Day", "$" + "{:,.2f}".format(h["var_95_1d"]))
        with col2:
            st.metric("VaR 99% 1-Day", "$" + "{:,.2f}".format(h["var_99_1d"]))
        with col3:
            st.metric("ES 95%", "$" + "{:,.2f}".format(h["es_95"]))
        with col4:
            st.metric("ES 99%", "$" + "{:,.2f}".format(h["es_99"]))
        st.markdown("**Calculation Steps:**")
        for k, v in h["calculation"].items():
            st.write("- " + v)
        st.markdown("**Loss Distribution Percentiles:**")
        dist = h["loss_distribution"]
        dist_df = pd.DataFrame([
            {"Percentile": "P10", "Loss": dist["p10"]},
            {"Percentile": "P25", "Loss": dist["p25"]},
            {"Percentile": "P50", "Loss": dist["p50"]},
            {"Percentile": "P75", "Loss": dist["p75"]},
            {"Percentile": "P90", "Loss": dist["p90"]},
            {"Percentile": "P95 (VaR)", "Loss": dist["p95"]},
            {"Percentile": "P99 (VaR)", "Loss": dist["p99"]}
        ])
        st.dataframe(dist_df, use_container_width=True)
        st.markdown("**10 Worst Simulated Losses:**")
        worst_df = pd.DataFrame({"Scenario": list(range(1, 11)), "Loss ($)": h["worst_10"]})
        fig = px.bar(worst_df, x="Scenario", y="Loss ($)", title="10 Worst Simulated Portfolio Losses", color="Loss ($)", color_continuous_scale=["orange", "red"])
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("Scenario Analysis")
    st.caption("Apply historical stress scenarios or define custom shocks")
    scenario_mode = st.radio("Mode", ["Predefined Scenario", "Custom Shocks", "Run All Scenarios"])

    if scenario_mode == "Predefined Scenario":
        selected = st.selectbox("Select Scenario", get_scenario_names())
        default_shocks = get_scenario_shocks(selected)
        st.markdown("**Default shocks — adjust if needed:**")
        custom_shocks = {}
        cols = st.columns(4)
        asset_classes = ["equity", "equity_futures", "commodity_futures", "crypto", "fixed_income", "fx", "equity_options"]
        for i, ac in enumerate(asset_classes):
            with cols[i % 4]:
                default_val = int(default_shocks.get(ac, 0.0) * 100)
                val = st.slider(ac, -100, 100, default_val, 1, key="shock_" + ac)
                custom_shocks[ac] = val / 100.0
        if st.button("Run Scenario", type="primary"):
            with st.spinner("Running scenario..."):
                result = run_scenario(st.session_state.positions, selected, custom_shocks)
                st.session_state.scenario_result = result

    elif scenario_mode == "Custom Shocks":
        st.markdown("**Set custom shock % per asset class:**")
        custom_shocks = {}
        cols = st.columns(4)
        asset_classes = ["equity", "equity_futures", "commodity_futures", "crypto", "fixed_income", "fx", "equity_options"]
        for i, ac in enumerate(asset_classes):
            with cols[i % 4]:
                val = st.slider(ac, -100, 100, 0, 1, key="custom_" + ac)
                custom_shocks[ac] = val / 100.0
        if st.button("Run Custom Scenario", type="primary"):
            with st.spinner("Running custom scenario..."):
                result = run_scenario(st.session_state.positions, "Custom", custom_shocks)
                st.session_state.scenario_result = result

    elif scenario_mode == "Run All Scenarios":
        if st.button("Run All 5 Scenarios", type="primary"):
            with st.spinner("Running all scenarios..."):
                all_results = run_all_scenarios(st.session_state.positions)
                st.session_state.all_scenarios = all_results
        if "all_scenarios" in st.session_state:
            st.subheader("Scenario Comparison")
            summary_data = []
            for r in st.session_state.all_scenarios:
                summary_data.append({"Scenario": r["scenario_name"], "Total P&L Impact": r["total_pnl_impact"], "Worst Position": r["worst_position"], "Best Position": r["best_position"]})
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df, use_container_width=True)
            fig = px.bar(summary_df, x="Scenario", y="Total P&L Impact", title="P&L Impact by Scenario ($)", color="Total P&L Impact", color_continuous_scale=["red", "yellow", "green"])
            st.plotly_chart(fig, use_container_width=True)

    if "scenario_result" in st.session_state and scenario_mode != "Run All Scenarios":
        r = st.session_state.scenario_result
        st.markdown("---")
        st.subheader("Results: " + r["scenario_name"])
        st.caption(r["description"])
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total P&L Impact", "$" + "{:,.2f}".format(r["total_pnl_impact"]))
        with col2:
            st.metric("Worst Position", r["worst_position"])
        with col3:
            st.metric("Best Position", r["best_position"])
        st.markdown("**Position-Level Impact:**")
        pos_df = pd.DataFrame(r["positions"])
        if not pos_df.empty:
            display_cols = ["symbol", "asset_class", "quantity", "current_price", "shock_pct", "shocked_price", "pnl_impact", "calculation"]
            pos_df = pos_df[display_cols]
            pos_df.columns = ["Symbol", "Asset Class", "Qty", "Current Price", "Shock %", "Shocked Price", "P&L Impact", "Calculation"]
            st.dataframe(pos_df, use_container_width=True)
        fig = px.bar(pd.DataFrame(r["positions"]), x="symbol", y="pnl_impact", title="P&L Impact by Position ($)", color="pnl_impact", color_continuous_scale=["red", "green"])
        st.plotly_chart(fig, use_container_width=True)
