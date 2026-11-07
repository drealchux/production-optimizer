"""Interactive least-cost salmon feed formulator.

    streamlit run app/streamlit_app.py
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from feedopt.data import (  # noqa: E402
    build_nutrient_matrix, list_profiles, load_inclusion_limits, load_price_table, load_raw_ingredients,
    load_requirements,
)
from feedopt.model import check_requirements, formulate  # noqa: E402
from feedopt.planning import shortfall_report  # noqa: E402
from feedopt.robust import coefficient_sd, formulate_chance  # noqa: E402
from feedopt.uncertainty import batch_pass_rate, compliance_table, load_variability, simulate_profiles  # noqa: E402

RELIABILITY_STEPS = [50, 80, 90, 95, 99, 99.5, 99.9]
N_SIM = 3000  # simulated batches for the live reliability check

st.set_page_config(page_title="Salmon Feed Optimizer", layout="wide")
st.title("Least-cost salmon feed formulator")
st.caption("Linear programming over sourced ingredient data (Feedipedia, FAO, World Bank), with an optional "
           "chance-constrained mode that holds each requirement in a chosen share of batches. "
           "Prices marked 'assumed' are illustrative. See data/SOURCES.md.")

raw = load_raw_ingredients()
nm = build_nutrient_matrix(raw)
variability = load_variability()
price_table = load_price_table()
limits = load_inclusion_limits()


@st.cache_data(show_spinner="Estimating ingredient variability...")
def cached_sd(profile: str, epa: float) -> pd.DataFrame:
    req = load_requirements(profile).copy()
    req.loc[req["nutrient"] == "epa_dha", "value"] = epa
    return coefficient_sd(raw, variability, req, n=5000)


@st.cache_data(show_spinner="Simulating batches...")
def cached_simulation(recipe_items: tuple, profile: str, epa: float):
    req = load_requirements(profile).copy()
    req.loc[req["nutrient"] == "epa_dha", "value"] = epa
    prof = simulate_profiles(pd.Series(dict(recipe_items)), raw, variability, n=N_SIM, seed=1)
    return batch_pass_rate(prof, req), compliance_table(prof, req)


with st.sidebar:
    profile = st.selectbox("Fish size profile", list_profiles(), index=0)
    req = load_requirements(profile).copy()

    st.subheader("Prices (USD/t)")
    prices = price_table["price_usd_per_t"].astype(float).copy()
    for ing in ["fish_oil", "fish_meal", "soy_protein_concentrate", "rapeseed_oil", "algal_oil", "wheat"]:
        tag = price_table.at[ing, "price_status"]
        prices[ing] = st.number_input(f"{ing.replace('_', ' ')} ({tag})", value=float(prices[ing]), step=50.0)

    st.subheader("Targets")
    epa = st.slider("Min EPA+DHA (% DM)", 0.5, 3.0,
                    float(req.loc[req["nutrient"] == "epa_dha", "value"].iloc[0]), 0.1)
    req.loc[req["nutrient"] == "epa_dha", "value"] = epa
    marine_max = st.slider("Max fish meal + fish oil (% of feed)", 0, 40, 40)

    st.subheader("Reliability")
    reliability = st.select_slider(
        "Share of batches meeting each requirement (%)", options=RELIABILITY_STEPS, value=50,
        help="50% is the plain least-cost recipe: it sits exactly on its limits, so any binding requirement "
             "is missed in about half of batches. Higher values add a safety margin sized from ingredient "
             "variability (chance constraints).")

    st.subheader("Availability")
    production = st.number_input("Production this month (t)", value=20000, step=1000)
    fo_stock = st.number_input("Fish oil available (t)", value=1000, step=50)

caps = {"fish_oil": min(100.0, fo_stock / production * 100)} if production else {}
groups = {"marine": (["fish_meal", "fish_oil"], marine_max)} if marine_max < 40 else None

lp = formulate(nm, prices, req, limits, availability_cap=caps, extra_max_groups=groups)
if not lp.feasible:
    st.error(f"No feasible recipe ({lp.status}). Loosen a target or raise availability.")
    st.stop()

if reliability > 50:
    with st.spinner("Solving the chance-constrained recipe..."):
        cc = formulate_chance(nm, prices, req, limits, cached_sd(profile, epa), reliability / 100,
                              availability_cap=caps, extra_max_groups=groups)
    if not cc.feasible:
        st.error(f"No recipe meets every requirement in {reliability}% of batches with these settings "
                 f"({cc.status}). Lower the reliability target or loosen a constraint.")
        st.stop()
    recipe, nutrients, cost = cc.recipe, cc.nutrients_dm, cc.cost_usd_per_t
else:
    recipe, nutrients, cost = lp.recipe, lp.nutrients_dm, lp.cost_usd_per_t

pass_all, compliance = cached_simulation(tuple(recipe[recipe > 0].round(6).items()), profile, epa)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Raw material cost", f"{cost:,.0f} USD/t",
          delta=f"+{cost - lp.cost_usd_per_t:,.0f} for reliability" if reliability > 50 else None,
          delta_color="inverse")
c2.metric("Batches meeting every requirement", f"{pass_all:.0f} %",
          help=f"Share of {N_SIM:,} simulated batches, with ingredient composition drawn from Feedipedia "
               "standard deviations, that meet all requirements at once.")
c3.metric("Marine ingredients", f"{recipe.reindex(['fish_meal', 'fish_oil']).fillna(0).sum():.1f} %")
c4.metric("EPA+DHA (average)", f"{nutrients['epa_dha']:.2f} % DM")

left, right = st.columns(2)
with left:
    st.subheader("Recipe (% as fed)")
    shown = pd.DataFrame({"this_recipe": recipe, "least_cost": lp.recipe}).fillna(0.0)
    shown = shown[(shown > 0.005).any(axis=1)].sort_values("this_recipe", ascending=False).round(2)
    st.bar_chart(shown["this_recipe"])
    st.dataframe(shown if reliability > 50 else shown[["this_recipe"]].rename(columns={"this_recipe": "pct_as_fed"}))
with right:
    st.subheader("Requirement check")
    check = check_requirements(nutrients, req)
    check["batches_failing_pct"] = compliance["pct_batches_failing"].round(1).to_numpy()
    st.caption("`actual` is the recipe's average. `batches_failing_pct` comes from the batch simulation.")
    st.dataframe(check, hide_index=True)
    if reliability > 50:
        st.info("Shadow prices and reduced costs come from the linear program, so they are shown only "
                "at 50% reliability.")
    else:
        st.subheader("Binding constraints (shadow prices)")
        st.caption("Extra USD per tonne of feed if the constraint tightens by one unit")
        if not lp.shadow_prices.empty:
            st.dataframe(lp.shadow_prices[["constraint", "usd_per_t_per_unit"]].round(2), hide_index=True)
        st.subheader("Price drop needed to enter the recipe")
        st.dataframe(lp.reduced_costs.round(0).rename("usd_per_t"))

st.subheader("Material requirements for this month")
stock = pd.Series({"fish_oil": float(fo_stock)})
need = (recipe / 100 * production).round(1)
st.dataframe(pd.DataFrame({"required_t": need[need > 0]}))
st.dataframe(shortfall_report(recipe, production, stock))
