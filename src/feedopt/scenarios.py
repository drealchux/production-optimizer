"""Scenario analysis on top of the least-cost model.

Each function answers a question a raw material optimization team asks in practice.
"""
from __future__ import annotations

import pandas as pd

from .model import formulate

MARINE = ["fish_meal", "fish_oil"]


def price_sweep(nm, prices, req, limits, ingredient: str, price_points, **kw) -> pd.DataFrame:
    """'What happens to the recipe if the price of X moves?'"""
    rows = []
    for pp in price_points:
        p = prices.copy()
        p[ingredient] = pp
        r = formulate(nm, p, req, limits, **kw)
        row = {"price": pp, "status": r.status, "cost_usd_per_t": r.cost_usd_per_t}
        if r.feasible:
            row.update(r.recipe.to_dict())
        rows.append(row)
    return pd.DataFrame(rows).fillna(0.0)


def requirement_sweep(nm, prices, req, limits, nutrient: str, bound: str, values, **kw) -> pd.DataFrame:
    """'What does it cost to raise a nutrient target?' e.g. EPA+DHA from 1% to 2.5%."""
    rows = []
    for v in values:
        r2 = req.copy()
        mask = (r2["nutrient"] == nutrient) & (r2["bound"] == bound)
        r2.loc[mask, "value"] = v
        r = formulate(nm, prices, r2, limits, **kw)
        row = {"requirement": v, "status": r.status, "cost_usd_per_t": r.cost_usd_per_t}
        if r.feasible:
            row.update(r.recipe.to_dict())
        rows.append(row)
    return pd.DataFrame(rows).fillna(0.0)


def supply_shock(nm, prices, req, limits, ingredient: str, cap_pct: float, price_multiplier: float = 1.0):
    """'A delivery of X is late, we can only use cap_pct % and it is more expensive.'"""
    p = prices.copy()
    p[ingredient] = p[ingredient] * price_multiplier
    base = formulate(nm, prices, req, limits)
    shocked = formulate(nm, p, req, limits, availability_cap={ingredient: cap_pct})
    return base, shocked


def marine_cap(nm, prices, req, limits, max_marine_pct: float):
    """Sustainability scenario: limit fish meal + fish oil (forage fish dependency)."""
    return formulate(nm, prices, req, limits, extra_max_groups={"marine": (MARINE, max_marine_pct)})


def historical_cost(nm, prices, req, limits, history: pd.DataFrame) -> pd.DataFrame:
    """Re-optimize with each historical price period.

    Sourced series replace the base price directly; derived ingredients keep their
    premium ratio to the base commodity (SPC to soybean meal, maize gluten to maize,
    faba beans to wheat). Unsourced prices are held constant.
    """
    base = prices.copy()
    ratios = {
        "soy_protein_concentrate": ("soybean_meal", base["soy_protein_concentrate"] / 404),
        "maize_gluten_meal": ("maize", base["maize_gluten_meal"] / 212.7),
        "faba_bean_dehulled": ("wheat_us_srw", base["faba_bean_dehulled"] / 247.4),
    }
    rows = []
    for h in history.itertuples():
        p = base.copy()
        p["fish_meal"] = h.fish_meal
        p["soybean_meal"] = h.soybean_meal
        p["wheat"] = h.wheat_us_srw
        for ing, (col, ratio) in ratios.items():
            p[ing] = getattr(h, col) * ratio
        r = formulate(nm, p, req, limits)
        row = {"period": h.period, "period_type": h.period_type, "cost_usd_per_t": r.cost_usd_per_t}
        row.update(r.recipe.to_dict())
        rows.append(row)
    return pd.DataFrame(rows).fillna(0.0)


def category_summary(recipe: pd.Series, nm: pd.DataFrame) -> pd.Series:
    """Group a recipe (% as fed) into the categories used in Nofima's reporting."""
    cats = nm.loc[recipe.index, "category"]
    out = recipe.groupby(cats).sum()
    rename = {"marine": "marine", "plant_protein": "plant_protein", "vegetable_oil": "vegetable_oil",
              "carbohydrate": "carbohydrate", "micro": "micro", "novel": "novel"}
    return out.rename(index=rename)
