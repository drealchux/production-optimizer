"""Raw material requirement planning.

Turns a recipe plus a production plan into ingredient tonnage, compares it with
stock and inbound deliveries, and re-formulates when something will run short.
This mirrors the 'make sure raw materials are available when needed' side of
the job: a recipe is only optimal if you can actually get the ingredients.
"""
from __future__ import annotations

import pandas as pd

from .model import formulate


def material_requirements(recipe_pct: pd.Series, production_t: float) -> pd.Series:
    """Tonnes of each ingredient needed to produce `production_t` tonnes of feed."""
    return (recipe_pct / 100 * production_t).round(1)


def shortfall_report(recipe_pct: pd.Series, production_t: float, stock_t: pd.Series,
                     inbound_t: pd.Series | None = None) -> pd.DataFrame:
    """Only ingredients present in the stock data are tracked (micro ingredients are assumed on hand)."""
    need = material_requirements(recipe_pct, production_t)
    avail = stock_t.reindex(need.index).fillna(0.0)
    if inbound_t is not None:
        avail = avail + inbound_t.reindex(need.index).fillna(0.0)
    df = pd.DataFrame({"required_t": need, "available_t": avail})
    df["balance_t"] = (df["available_t"] - df["required_t"]).round(1)
    df["status"] = df["balance_t"].apply(lambda b: "SHORT" if b < 0 else "ok")
    tracked = stock_t.index if inbound_t is None else stock_t.index.union(inbound_t.index)
    df = df[(df["required_t"] > 0) & df.index.isin(tracked)]
    return df.sort_values("balance_t")


def availability_aware_formulation(nm, prices, req, limits, production_t: float,
                                   stock_t: pd.Series, inbound_t: pd.Series | None = None,
                                   tracked: list[str] | None = None):
    """Re-optimize so no tracked ingredient exceeds what is physically available.

    tracked: ingredients whose availability is constrained (defaults to all with stock data).
    """
    avail = stock_t.copy()
    if inbound_t is not None:
        avail = avail.add(inbound_t, fill_value=0.0)
    tracked = tracked or list(avail.index)
    caps = {ing: min(100.0, float(avail[ing]) / production_t * 100) for ing in tracked}
    return formulate(nm, prices, req, limits, availability_cap=caps), caps
