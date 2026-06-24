import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import math
from datetime import date

from core.position_store import get_positions, get_portfolio_summary
from core.var import calculate_parametric_var, calculate_historical_var
from core.scenarios import run_scenario, run_all_scenarios, get_scenario_names, get_scenario_shocks
from core.span import calculate_portfolio_margin, load_span_params, save_span_params

st.set_page_config(page_title="Risk Intelligence", page_icon="🧠", layout="wide")
st.title("🧠 Risk Intelligence")
st.caption("SPAN/Reg T Margin, VaR, Scenario Analysis, Greeks, Concentration Risk and Stress P&L.")

PREDEFINED_SCENARIOS_DESC = {
    '2008 Financial Crisis': 'Global financial crisis, Lehman collapse, credit freeze',
    'COVID Crash 2020':      'Pandemic onset, fastest 30% market decline in history',
    'Rate Shock 2022':       'Fed aggressive rate hikes, bond market selloff',
    'Crypto Winter 2022':    'FTX collapse, crypto contagion, digital asset selloff',
    'Tech Selloff':          'Nasdaq correction, growth stock rotation to value',
    'Oil Shock':             'Geopolitical supply disruption, crude +40%',
    'Gold Rally':            'Flight to safety, gold +20%, equities fall',
}

positions = get_positions("open")
summary   = get_portfolio_summary()

if not positions:
    st.warning("No open positions found. Add positions via Order Input first.")
    st.stop()

st.caption(f"Running analysis on **{len(positions)}** open position(s) | "
           f"Total Notional: **${summary['total_notional']:,.2f}** | "
           f"Unrealized P&L: **${summary['total_unrealized_pnl']:+,.2f}**")

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📐 SPAN & Reg T",
    "📉 VaR & ES",
    "🌪️ Scenario Analysis",
    "🔢 Greeks",
    "🎯 Concentration Risk",
    "💥 Stress P&L",
    "⚙️ SPAN Parameters",
])

# ── TAB 1: SPAN & REG T ──────────────────────────────────────────────────
with tab1:
    st.subheader("SPAN & Reg T Margin Calculator")
    st.caption("Calculates margin requirements using SPAN for futures and Reg T for equities.")

    if st.button("Calculate Margin", type="primary", key="span_btn"):
        with st.spinner("Calculating..."):
            results = calculate_portfolio_margin(positions)
            st.session_state.span_results = results

    if "span_results" in st.session_state:
        results = st.session_state.span_results

        st.markdown("### Total Margin Summary")
        c1, c2, c3 = st.columns(3)
        c1.metric("Futures Margin (SPAN)",    f"${results['net_futures_margin']:,.2f}")
        c2.metric("Equity Margin (Reg T)",    f"${results['net_equity_margin']:,.2f}")
        c3.metric("Total Margin Requirement", f"${results['total_margin_requirement']:,.2f}")

        if results["futures_positions"]:
            st.markdown("---")
            st.markdown("### Futures — SPAN Margin")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Scanning Risk", f"${results['total_scanning_risk']:,.2f}")
            c2.metric("Spread Credits",      f"${results['total_spread_credits']:,.2f}")
            c3.metric("Short Option Min",    f"${results['total_som']:,.2f}")
            c4.metric("Net Futures Margin",  f"${results['net_futures_margin']:,.2f}")

            if results["total_spread_credits"] > 0:
                st.success(f"Intercommodity spread credits saved "
                           f"${results['total_spread_credits']:,.2f} in margin")

            fut_df = pd.DataFrame(results["futures_positions"])
            if not fut_df.empty:
                disp_cols = ["symbol", "asset_class", "quantity", "price",
                             "position_value", "margin_type", "initial_margin",
                             "maintenance_margin", "scanning_risk", "som",
                             "margin", "calc_detail"]
                fut_df = fut_df[[c for c in disp_cols if c in fut_df.columns]]
                fut_df.columns = [c.replace("_"," ").title() for c in fut_df.columns]
                st.dataframe(fut_df, use_container_width=True, hide_index=True)

        if results["equity_positions"]:
            st.markdown("---")
            st.markdown("### Equities — Reg T Margin")
            c1, c2, c3 = st.columns(3)
            c1.metric("Initial Margin (50%)",      f"${results['total_reg_t_initial']:,.2f}")
            c2.metric("Maintenance Margin (25%)",  f"${results['total_reg_t_maintenance']:,.2f}")
            total_eq = sum(abs(p["position_value"]) for p in results["equity_positions"])
            c3.metric("Total Equity Value",         f"${total_eq:,.2f}")

            eq_df = pd.DataFrame(results["equity_positions"])
            if not eq_df.empty:
                eq_df = eq_df[["symbol", "asset_class", "quantity", "price",
                               "position_value", "margin_type",
                               "initial_margin", "maintenance_margin", "calculation"]]
                eq_df.columns = ["Symbol", "Asset Class", "Qty", "Price",
                                 "Position Value", "Margin Type",
                                 "Initial Margin", "Maint. Margin", "Calculation"]
                st.dataframe(eq_df, use_container_width=True, hide_index=True)

            st.info("Reg T: 50% initial, 25% maintenance per FINRA rules. Crypto: 100% cash.")

# ── TAB 2: VAR & ES ──────────────────────────────────────────────────────
with tab2:
    st.subheader("Value at Risk & Expected Shortfall")
    st.caption("Estimates potential portfolio loss at given confidence levels.")

    col1, col2 = st.columns(2)
    with col1:
        method = st.radio("Method", ["Parametric (Variance-Covariance)", "Historical Simulation", "Both"])
    with col2:
        simulations = st.slider("Simulations (Historical)", 500, 5000, 1000, 500)

    if st.button("Calculate VaR & ES", type="primary", key="var_btn"):
        if method in ["Parametric (Variance-Covariance)", "Both"]:
            with st.spinner("Running parametric VaR..."):
                st.session_state.p_var = calculate_parametric_var(positions)
        if method in ["Historical Simulation", "Both"]:
            with st.spinner(f"Running {simulations} simulations..."):
                st.session_state.h_var = calculate_historical_var(positions, simulations)

    if "p_var" in st.session_state and method in ["Parametric (Variance-Covariance)", "Both"]:
        p = st.session_state.p_var
        st.markdown("---")
        st.subheader("Parametric VaR")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("VaR 95% 1-Day",  f"${p['portfolio']['var_95_1d']:,.2f}")
        c2.metric("VaR 99% 1-Day",  f"${p['portfolio']['var_99_1d']:,.2f}")
        c3.metric("VaR 95% 10-Day", f"${p['portfolio']['var_95_10d']:,.2f}")
        c4.metric("VaR 99% 10-Day", f"${p['portfolio']['var_99_10d']:,.2f}")
        st.markdown("**Calculation Steps:**")
        for v in p['portfolio']['calculation'].values():
            st.write(f"— {v}")
        var_df = pd.DataFrame([{
            "Symbol": f"{r['symbol']} ({r['side']})",
            "VaR 95% 1D ($)": r['var_95_1d'],
            "VaR 99% 1D ($)": r['var_99_1d'],
        } for r in p['positions']])
        fig = px.bar(var_df, x="Symbol", y=["VaR 95% 1D ($)", "VaR 99% 1D ($)"],
                     barmode="group", title="VaR by Position",
                     color_discrete_map={"VaR 95% 1D ($)": "#4C9BE8", "VaR 99% 1D ($)": "#cc3300"})
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#fff", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("**Position-Level Breakdown:**")
        for pos_r in p['positions']:
            with st.expander(f"{pos_r['symbol']} ({pos_r['side']}) | VaR 95%: ${pos_r['var_95_1d']:,.2f}"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Position Value", f"${pos_r['position_value']:,.2f}")
                c2.metric("Annual Vol",     f"{pos_r['annual_vol_pct']:.1f}%")
                c3.metric("VaR 95% 1D",    f"${pos_r['var_95_1d']:,.2f}")
                c4.metric("VaR 99% 1D",    f"${pos_r['var_99_1d']:,.2f}")
                for v in pos_r['calculation'].values():
                    st.write(f"— {v}")

    if "h_var" in st.session_state and method in ["Historical Simulation", "Both"]:
        h = st.session_state.h_var
        st.markdown("---")
        st.subheader("Historical Simulation")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("VaR 95% 1-Day", f"${h['var_95_1d']:,.2f}")
        c2.metric("VaR 99% 1-Day", f"${h['var_99_1d']:,.2f}")
        c3.metric("ES 95%",        f"${h['es_95']:,.2f}")
        c4.metric("ES 99%",        f"${h['es_99']:,.2f}")
        st.markdown("**Calculation Steps:**")
        for v in h['calculation'].values():
            st.write(f"— {v}")
        dist_df = pd.DataFrame([{"Percentile": k.upper(), "Loss ($)": v}
                                 for k, v in h['loss_distribution'].items()])
        st.dataframe(dist_df, use_container_width=True, hide_index=True)
        worst_df = pd.DataFrame({"Scenario": range(1, 11), "Loss ($)": h['worst_10']})
        fig2 = px.bar(worst_df, x="Scenario", y="Loss ($)", title="10 Worst Simulated Losses",
                      color="Loss ($)", color_continuous_scale=["orange", "red"])
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#fff", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)

# ── TAB 3: SCENARIO ANALYSIS ─────────────────────────────────────────────
with tab3:
    st.subheader("Scenario Analysis")
    st.caption("Apply historical stress scenarios or custom shocks to the current portfolio.")

    mode = st.radio("Mode", ["Predefined Scenario", "Custom Shocks", "Run All Scenarios"])

    if mode == "Predefined Scenario":
        selected       = st.selectbox("Select Scenario", get_scenario_names())
        default_shocks = get_scenario_shocks(selected)
        st.markdown(f"*{PREDEFINED_SCENARIOS_DESC.get(selected, '')}*")
        st.markdown("**Adjust shocks if needed:**")
        custom_shocks = {}
        cols = st.columns(4)
        display_acs = ["STK", "FUT", "OPT", "CRYPTO", "BOND",
                       "equity", "equity_futures", "commodity_futures", "fixed_income", "crypto"]
        seen = set()
        display_list = [ac for ac in display_acs if ac not in seen and not seen.add(ac)]
        for i, ac in enumerate(display_list):
            with cols[i % 4]:
                default_val = int(default_shocks.get(ac, 0.0) * 100)
                val = st.slider(ac, -100, 100, default_val, 1, key=f"shock_{ac}")
                custom_shocks[ac] = val / 100.0
        if st.button("Run Scenario", type="primary", key="run_scen"):
            st.session_state.scenario_result = run_scenario(positions, selected, custom_shocks)

    elif mode == "Custom Shocks":
        st.markdown("**Set custom shock % per asset class:**")
        custom_shocks = {}
        cols = st.columns(4)
        for i, ac in enumerate(["STK", "FUT", "OPT", "CRYPTO", "BOND"]):
            with cols[i % 4]:
                val = st.slider(ac, -100, 100, 0, 1, key=f"custom_{ac}")
                custom_shocks[ac] = val / 100.0
        if st.button("Run Custom Scenario", type="primary", key="run_custom"):
            st.session_state.scenario_result = run_scenario(positions, "Custom", custom_shocks)

    elif mode == "Run All Scenarios":
        if st.button("Run All Scenarios", type="primary", key="run_all"):
            st.session_state.all_scenarios = run_all_scenarios(positions)
        if "all_scenarios" in st.session_state:
            st.subheader("Scenario Comparison")
            summary_rows = [{"Scenario": r["scenario_name"],
                             "Total P&L Impact": f"${r['total_pnl_impact']:+,.2f}",
                             "Worst Position": r["worst_position"],
                             "Best Position":  r["best_position"]}
                            for r in st.session_state.all_scenarios]
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
            fig_all = px.bar(
                pd.DataFrame([{"Scenario": r["scenario_name"],
                               "P&L Impact ($)": r["total_pnl_impact"]}
                              for r in st.session_state.all_scenarios]),
                x="Scenario", y="P&L Impact ($)",
                color="P&L Impact ($)", color_continuous_scale=["red", "yellow", "green"],
                title="P&L Impact by Scenario")
            fig_all.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#fff", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_all, use_container_width=True)

    if "scenario_result" in st.session_state and mode != "Run All Scenarios":
        r = st.session_state.scenario_result
        st.markdown("---")
        st.subheader(f"Results: {r['scenario_name']}")
        st.caption(r.get('description', ''))
        c1, c2, c3 = st.columns(3)
        c1.metric("Total P&L Impact", f"${r['total_pnl_impact']:+,.2f}")
        c2.metric("Worst Position",   r["worst_position"])
        c3.metric("Best Position",    r["best_position"])
        pos_df = pd.DataFrame(r["positions"])
        if not pos_df.empty:
            disp = pos_df[["symbol","side","asset_class","quantity",
                           "current_price","shock_pct","shocked_price",
                           "pnl_impact","calculation"]].copy()
            disp.columns = ["Symbol","Side","Asset Class","Qty",
                            "Current ($)","Shock %","Shocked ($)","P&L Impact ($)","Calculation"]
            st.dataframe(disp, use_container_width=True, hide_index=True)
        fig_s = px.bar(pos_df, x="symbol", y="pnl_impact",
                       color="pnl_impact", color_continuous_scale=["red","green"],
                       title=f"P&L Impact by Position — {r['scenario_name']}")
        fig_s.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#fff", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_s, use_container_width=True)

# ── TAB 4: GREEKS ────────────────────────────────────────────────────────
with tab4:
    st.subheader("Greeks Dashboard")
    st.caption("Delta-adjusted exposure for all positions. Full Greeks for options.")

    delta_rows = []
    total_dae  = 0
    for p in positions:
        ac        = p.get('asset_class', 'STK')
        side      = (p.get('side') or 'LONG').upper()
        direction = 1 if side in ('LONG','BUY') else -1
        price     = p.get('current_price') or p.get('price', 0) or 0
        qty       = p.get('quantity', 0)
        mult      = p.get('multiplier', 1) or 1
        cs        = p.get('contract_size', 1) or 1
        if ac == 'OPT':
            strike    = p.get('strike') or price
            right     = p.get('option_right', 'C')
            moneyness = price / strike if strike > 0 else 1
            delta     = min(max(0.3, moneyness * 0.5), 0.9) if right == 'C' else -min(max(0.3, moneyness * 0.5), 0.9)
            delta    *= direction
        else:
            delta = direction * 1.0
        notional = qty * price * mult * cs
        dae      = delta * notional
        total_dae += dae
        delta_rows.append({"Symbol": p["symbol"], "Asset Class": ac, "Side": side,
                           "Qty": qty, "Price ($)": f"${price:,.4f}",
                           "Delta": f"{delta:+.3f}", "Notional ($)": f"${notional:,.2f}",
                           "Delta-Adj Exposure ($)": f"${dae:+,.2f}"})
    st.dataframe(pd.DataFrame(delta_rows), use_container_width=True, hide_index=True)
    col1, col2 = st.columns(2)
    col1.metric("Net Delta-Adjusted Exposure", f"${total_dae:+,.2f}")
    col2.metric("Directional Bias", "LONG" if total_dae > 0 else "SHORT" if total_dae < 0 else "FLAT")

    opt_positions = [p for p in positions if p.get('asset_class') == 'OPT']
    if opt_positions:
        st.markdown("---")
        st.markdown("### Options Greeks")
        st.caption("Simplified Black-Scholes — assumes 30-day expiry, 20% IV. Indicative only.")
        greek_rows = []
        net_delta = net_gamma = net_vega = net_theta = 0
        for p in opt_positions:
            price  = p.get('current_price') or p.get('price', 0) or 0
            strike = p.get('strike') or price
            right  = p.get('option_right', 'C')
            side   = (p.get('side') or 'LONG').upper()
            qty    = p.get('quantity', 0)
            mult   = p.get('multiplier', 100) or 100
            direction = 1 if side in ('LONG','BUY') else -1
            T, iv, r_rate = 30/365, 0.20, 0.05
            try:
                from math import erf
                d1 = (math.log(price/strike) + (r_rate + 0.5*iv**2)*T) / (iv*math.sqrt(T))
                d2 = d1 - iv*math.sqrt(T)
                norm_cdf = lambda x: (1.0 + erf(x/math.sqrt(2)))/2.0
                norm_pdf = lambda x: math.exp(-0.5*x**2)/math.sqrt(2*math.pi)
                delta = norm_cdf(d1) if right=='C' else norm_cdf(d1)-1
                gamma = norm_pdf(d1)/(price*iv*math.sqrt(T))
                vega  = price*norm_pdf(d1)*math.sqrt(T)/100
                theta = (-(price*norm_pdf(d1)*iv)/(2*math.sqrt(T)) -
                         r_rate*strike*math.exp(-r_rate*T)*norm_cdf(d2 if right=='C' else -d2))/365
                pos_delta = direction*delta*qty*mult
                pos_gamma = direction*gamma*qty*mult
                pos_vega  = direction*vega*qty*mult
                pos_theta = direction*theta*qty*mult
                net_delta+=pos_delta; net_gamma+=pos_gamma; net_vega+=pos_vega; net_theta+=pos_theta
                greek_rows.append({"Symbol":p["symbol"],"Side":side,"Right":right,
                    "Strike":f"${strike:,.2f}","Qty":qty,
                    "Δ Delta":f"{pos_delta:+.4f}","Γ Gamma":f"{pos_gamma:+.6f}",
                    "ν Vega":f"${pos_vega:+,.2f}","Θ Theta":f"${pos_theta:+,.2f}/day"})
            except:
                greek_rows.append({"Symbol":p["symbol"],"Side":side,"Right":right,
                    "Strike":f"${strike:,.2f}","Qty":qty,
                    "Δ Delta":"N/A","Γ Gamma":"N/A","ν Vega":"N/A","Θ Theta":"N/A"})
        st.dataframe(pd.DataFrame(greek_rows), use_container_width=True, hide_index=True)
        g1,g2,g3,g4 = st.columns(4)
        g1.metric("Net Delta",f"{net_delta:+.4f}"); g2.metric("Net Gamma",f"{net_gamma:+.6f}")
        g3.metric("Net Vega",f"${net_vega:+,.2f}"); g4.metric("Net Theta",f"${net_theta:+,.2f}/day")
    else:
        st.info("No options positions. Greeks appear when OPT positions are added.")

# ── TAB 5: CONCENTRATION RISK ─────────────────────────────────────────────
with tab5:
    st.subheader("Concentration Risk")
    total_notional = summary["total_notional"] or 1
    ac_data = [{"Asset Class": ac, "Positions": v["count"],
                "Notional ($)": f"${v['notional']:,.2f}",
                "% of Portfolio": f"{v['notional']/total_notional*100:.1f}%",
                "Unrealized P&L": f"${v['pnl']:+,.2f}",
                "IM ($)": f"${v['initial_margin']:,.2f}"}
               for ac, v in summary["by_asset_class"].items()]
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**By Asset Class**")
        st.dataframe(pd.DataFrame(ac_data), use_container_width=True, hide_index=True)
    with col2:
        fig_ac = px.pie(
            pd.DataFrame([{"Asset Class": r["Asset Class"],
                           "Notional": summary["by_asset_class"][r["Asset Class"]]["notional"]}
                          for r in ac_data]),
            values="Notional", names="Asset Class", title="Notional by Asset Class",
            color_discrete_sequence=px.colors.qualitative.Set2)
        fig_ac.update_traces(textposition="inside", textinfo="percent+label")
        fig_ac.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#fff")
        st.plotly_chart(fig_ac, use_container_width=True)
    st.markdown("---")
    st.markdown("**By Symbol**")
    sym_data = {}
    for p in positions:
        sym = p["symbol"]
        if sym not in sym_data:
            sym_data[sym] = {"notional":0,"pnl":0,"count":0}
        sym_data[sym]["notional"] += p["notional_value"]
        sym_data[sym]["pnl"]      += p["unrealized_pnl"]
        sym_data[sym]["count"]    += 1
    sym_rows = sorted([
        {"Symbol":sym,"Positions":v["count"],
         "Notional ($)":f"${v['notional']:,.2f}",
         "% of Portfolio":f"{v['notional']/total_notional*100:.1f}%",
         "Unrealized P&L":f"${v['pnl']:+,.2f}",
         "Concentration":"⚠️ HIGH" if v['notional']/total_notional>0.30
                        else "🟡 MED" if v['notional']/total_notional>0.15 else "🟢 OK"}
        for sym,v in sym_data.items()],
        key=lambda x: float(x["Notional ($)"].replace("$","").replace(",","")), reverse=True)
    st.dataframe(pd.DataFrame(sym_rows), use_container_width=True, hide_index=True)
    st.markdown("---")
    st.markdown("**Long vs Short Exposure**")
    long_n  = sum(p["notional_value"] for p in positions if p["side"]=="LONG")
    short_n = sum(p["notional_value"] for p in positions if p["side"]=="SHORT")
    d1,d2,d3,d4 = st.columns(4)
    d1.metric("Long Notional",  f"${long_n:,.2f}")
    d2.metric("Short Notional", f"${short_n:,.2f}")
    d3.metric("Net Exposure",   f"${long_n-short_n:+,.2f}")
    d4.metric("L/S Ratio",      f"{long_n/short_n:.2f}x" if short_n>0 else "∞ (long only)")

# ── TAB 6: STRESS P&L ────────────────────────────────────────────────────
with tab6:
    st.subheader("Multi-Factor Stress P&L")
    col1,col2,col3 = st.columns(3)
    with col1:
        stk_shock   = st.slider("Equities (STK) %",  -80,80,-20,5,key="stress_stk")
        fut_shock   = st.slider("Futures (FUT) %",   -80,80,-10,5,key="stress_fut")
    with col2:
        crypto_shock= st.slider("Crypto %",          -90,90,-40,5,key="stress_crypto")
        bond_shock  = st.slider("Bonds (BOND) %",    -30,30,  5,1,key="stress_bond")
    with col3:
        opt_shock   = st.slider("Options (OPT) %",   -80,80,-30,5,key="stress_opt")
        vol_mult    = st.slider("Vol Multiplier (×)",  1,  5,  2,1,key="stress_vol",
                                help="Multiplies margin to simulate vol spike")

    if st.button("🔥 Run Stress Test", type="primary", key="stress_btn"):
        stress_shocks = {
            "STK":stk_shock/100,"FUT":fut_shock/100,"CRYPTO":crypto_shock/100,
            "BOND":bond_shock/100,"OPT":opt_shock/100,
            "equity":stk_shock/100,"equity_futures":fut_shock/100,
            "commodity_futures":fut_shock/100,"crypto":crypto_shock/100,
            "fixed_income":bond_shock/100,"equity_options":opt_shock/100,
        }
        stress_result = run_scenario(positions, "Stress Test", stress_shocks)
        from core.margin_call import get_margin_call_status
        mc = get_margin_call_status()
        stressed_im = mc["total_im"] * vol_mult
        stressed_mm = mc["total_mm"] * vol_mult
        pnl = stress_result["total_pnl_impact"]
        stressed_el = mc["collateral_value"] + pnl - stressed_mm
        st.markdown("---")
        st.subheader("Stress Test Results")
        r1,r2,r3,r4,r5 = st.columns(5)
        r1.metric("Stressed P&L",       f"${pnl:+,.2f}",
                  delta="Gain" if pnl>=0 else "Loss",
                  delta_color="normal" if pnl>=0 else "inverse")
        r2.metric("Current IM",         f"${mc['total_im']:,.2f}")
        r3.metric("Stressed IM (×vol)", f"${stressed_im:,.2f}")
        r4.metric("Collateral Value",   f"${mc['collateral_value']:,.2f}")
        r5.metric("Excess Liq (Stressed)", f"${stressed_el:,.2f}")
        if stressed_el < 0:
            st.error(f"🚨 MARGIN BREACH — shortfall ${abs(stressed_el):,.2f}")
        elif stressed_el < mc["collateral_value"]*0.05:
            st.warning(f"⚠️ Near margin call — excess liquidity ${stressed_el:,.2f}")
        else:
            st.success(f"✅ Portfolio survives stress — excess liquidity ${stressed_el:,.2f}")
        pos_df = pd.DataFrame(stress_result["positions"])
        if not pos_df.empty:
            disp = pos_df[["symbol","side","asset_class","shock_pct",
                           "current_price","shocked_price","pnl_impact"]].copy()
            disp.columns=["Symbol","Side","Asset Class","Shock %","Current ($)","Stressed ($)","P&L Impact ($)"]
            st.dataframe(disp, use_container_width=True, hide_index=True)
            fig_stress = px.bar(pos_df, x="symbol", y="pnl_impact",
                                color="pnl_impact", color_continuous_scale=["red","green"],
                                title="Stressed P&L by Position")
            fig_stress.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#fff", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_stress, use_container_width=True)

# ── TAB 7: SPAN PARAMETERS ───────────────────────────────────────────────
with tab7:
    st.subheader("⚙️ SPAN Margin Parameters")
    st.caption("Update margin rates when CME publishes performance bond changes.")

    params = load_span_params()
    meta   = params.get("_meta", {})
    col1, col2 = st.columns([3,1])
    with col1:
        st.info(f"Last updated: **{meta.get('last_updated','unknown')}** — {meta.get('source','')}")
    with col2:
        if st.button("🔄 Reload"):
            st.rerun()

    st.markdown("---")
    st.markdown("### Per-Product SPAN Margins ($/contract)")
    product_margins = params.get("product_margins", {})
    rate_rows = [{"Symbol":sym,"Name":prod.get("name",""),
                  "Exchange":prod.get("exchange",""),
                  "Asset Class":prod.get("asset_class",""),
                  "Initial ($)":prod.get("initial_margin",0),
                  "Maintenance ($)":prod.get("maintenance_margin",0)}
                 for sym, prod in product_margins.items()]
    st.dataframe(pd.DataFrame(rate_rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("### Update a Product Rate")
    col1,col2,col3 = st.columns(3)
    with col1:
        update_sym = st.selectbox("Product", list(product_margins.keys()), key="upd_sym")
    with col2:
        current_im = product_margins.get(update_sym,{}).get("initial_margin",0)
        new_im = st.number_input("New Initial Margin ($)", min_value=0, value=int(current_im), step=25, key="new_im")
    with col3:
        current_mm = product_margins.get(update_sym,{}).get("maintenance_margin",0)
        new_mm = st.number_input("New Maintenance Margin ($)", min_value=0, value=int(current_mm), step=25, key="new_mm")
    if st.button("💾 Update Rate", type="primary"):
        params["product_margins"][update_sym]["initial_margin"]    = new_im
        params["product_margins"][update_sym]["maintenance_margin"] = new_mm
        params["_meta"]["last_updated"] = str(date.today())
        params["_meta"]["source"]       = "Manual update via Sentinel UI"
        save_span_params(params)
        st.success(f"✅ Updated {update_sym}: Initial ${new_im:,} / Maintenance ${new_mm:,}")
        st.rerun()

    st.markdown("---")
    st.markdown("### Add New Product")
    col1,col2,col3,col4,col5 = st.columns(5)
    with col1: new_sym  = st.text_input("Symbol", placeholder="NG", key="new_sym").upper()
    with col2: new_name = st.text_input("Name", placeholder="Natural Gas", key="new_name")
    with col3: new_exch = st.selectbox("Exchange",["CME","CBOT","NYMEX","COMEX"], key="new_exch")
    with col4: new_ac   = st.selectbox("Asset Class",["equity_futures","commodity_futures","fixed_income","crypto","fx"], key="new_ac")
    with col5: new_ccy  = st.selectbox("Currency",["USD","EUR","GBP"], key="new_ccy")
    col1,col2 = st.columns(2)
    with col1: new_prod_im = st.number_input("Initial Margin ($)", min_value=0, value=5000, step=25, key="new_prod_im")
    with col2: new_prod_mm = st.number_input("Maintenance Margin ($)", min_value=0, value=4500, step=25, key="new_prod_mm")
    if st.button("➕ Add Product", key="add_prod"):
        if not new_sym:
            st.error("Symbol is required.")
        elif new_sym in product_margins:
            st.error(f"{new_sym} already exists — use Update Rate above.")
        else:
            params["product_margins"][new_sym] = {"name":new_name,"exchange":new_exch,
                "asset_class":new_ac,"initial_margin":new_prod_im,
                "maintenance_margin":new_prod_mm,"currency":new_ccy}
            params["asset_class_map"][new_sym] = new_ac
            params["_meta"]["last_updated"]    = str(date.today())
            params["_meta"]["source"]          = "Manual update via Sentinel UI"
            save_span_params(params)
            st.success(f"✅ Added {new_sym}")
            st.rerun()

    st.markdown("---")
    st.markdown("### Options Margins (SPAN — per contract)")
    st.caption("Short options on futures use per-contract SPAN margin. Long options pay 100% of premium.")
    opt_margins = params.get("option_margins", {})
    if opt_margins:
        opt_rows = [{"Underlying": sym,
                     "Name": v.get("name",""),
                     "Long IM ($)": "100% of premium",
                     "Short IM ($/contract)": f"${v.get('short_initial',0):,}",
                     "Short MM ($/contract)": f"${v.get('short_maintenance',0):,}",
                     "SOM ($/contract)": f"${v.get('som_per_contract',0):,}"}
                    for sym, v in opt_margins.items()]
        st.dataframe(pd.DataFrame(opt_rows), use_container_width=True, hide_index=True)

        st.markdown("**Update Options Margin Rate**")
        col1, col2, col3 = st.columns(3)
        with col1:
            upd_opt_sym = st.selectbox("Product", list(opt_margins.keys()), key="upd_opt_sym")
        with col2:
            cur_opt_im = opt_margins.get(upd_opt_sym, {}).get("short_initial", 0)
            new_opt_im = st.number_input("Short Initial ($/contract)", min_value=0,
                                          value=int(cur_opt_im), step=25, key="new_opt_im")
        with col3:
            cur_opt_mm = opt_margins.get(upd_opt_sym, {}).get("short_maintenance", 0)
            new_opt_mm = st.number_input("Short Maintenance ($/contract)", min_value=0,
                                          value=int(cur_opt_mm), step=25, key="new_opt_mm")
        if st.button("💾 Update Options Rate", type="primary", key="upd_opt_btn"):
            params["option_margins"][upd_opt_sym]["short_initial"]     = new_opt_im
            params["option_margins"][upd_opt_sym]["short_maintenance"]  = new_opt_mm
            params["option_margins"][upd_opt_sym]["som_per_contract"]   = new_opt_im
            params["_meta"]["last_updated"] = str(date.today())
            params["_meta"]["source"]       = "Manual update via Sentinel UI"
            save_span_params(params)
            st.success(f"✅ Updated {upd_opt_sym} options: Short IM ${new_opt_im:,} / MM ${new_opt_mm:,}")
            st.rerun()
    else:
        st.info("No option margins configured yet.")

    st.markdown("---")
    st.markdown("### Spread Credits")
    spread_rows = [{"Pair":pair,"Credit Rate":f"{rate:.0%}"}
                   for pair, rate in params.get("spread_credits",{}).items()]
    st.dataframe(pd.DataFrame(spread_rows), use_container_width=True, hide_index=True)

    st.markdown("### Reg T Rates")
    reg_t = params.get("reg_t",{})
    eq_opt = params.get("equity_option_margins", {})
    col1,col2,col3,col4 = st.columns(4)
    col1.metric("Equity Initial Margin",    f"{reg_t.get('initial',0.50):.0%}")
    col2.metric("Equity Maintenance Margin",f"{reg_t.get('maintenance',0.25):.0%}")
    col3.metric("Long Option",              "100% of premium")
    col4.metric("Short Naked Option",       f"{eq_opt.get('short_naked_initial',0.20):.0%} of notional")