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

st.set_page_config(page_title="Salmon Feed Optimizer", layout="wide")
st.title("Least-cost salmon feed formulator")
st.caption("Linear programming over sourced ingredient data (Feedipedia, FAO, World Bank). "
           "Prices marked 'assumed' are illustrative. See data/SOURCES.md.")

nm = build_nutrient_matrix(load_raw_ingredients())
price_table = load_price_table()
limits = load_inclusion_limits()

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

    st.subheader("Availability")
    production = st.number_input("Production this month (t)", value=20000, step=1000)
    fo_stock = st.number_input("Fish oil available (t)", value=1000, step=50)

caps = {"fish_oil": min(100.0, fo_stock / production * 100)} if production else {}
groups = {"marine": (["fish_meal", "fish_oil"], marine_max)} if marine_max < 40 else None
res = formulate(nm, prices, req, limits, availability_cap=caps, extra_max_groups=groups)

if not res.feasible:
    st.error(f"No feasible recipe ({res.status}). Loosen a target or raise availability.")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Raw material cost", f"{res.cost_usd_per_t:,.0f} USD/t")
c2.metric("Marine ingredients", f"{res.recipe[['fish_meal', 'fish_oil']].sum():.1f} %")
c3.metric("EPA+DHA", f"{res.nutrients_dm['epa_dha']:.2f} % DM")

left, right = st.columns(2)
with left:
    st.subheader("Recipe (% as fed)")
    rec = res.recipe[res.recipe > 0.005].round(2)
    st.bar_chart(rec)
    st.dataframe(rec.rename("pct_as_fed"))
with right:
    st.subheader("Requirement check")
    st.dataframe(check_requirements(res.nutrients_dm, req), hide_index=True)
    st.subheader("Binding constraints (shadow prices)")
    st.caption("Extra USD per tonne of feed if the constraint tightens by one unit")
    if not res.shadow_prices.empty:
        st.dataframe(res.shadow_prices[["constraint", "usd_per_t_per_unit"]].round(2), hide_index=True)
    st.subheader("Price drop needed to enter the recipe")
    st.dataframe(res.reduced_costs.round(0).rename("usd_per_t"))

st.subheader("Material requirements for this month")
stock = pd.Series({"fish_oil": float(fo_stock)})
need = (res.recipe / 100 * production).round(1)
st.dataframe(pd.DataFrame({"required_t": need[need > 0]}))
st.dataframe(shortfall_report(res.recipe, production, stock))
