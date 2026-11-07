"""Batch-to-batch variability: how often does a fixed recipe actually meet spec?

The optimizer treats every ingredient as having exactly its average composition,
so it pushes binding requirements to their limit. Real ingredient lots vary.
This module draws random ingredient compositions, pushes them through the same
unit conversion the optimizer uses, and reports how often a recipe misses each
requirement.

Assumptions (stated in data/SOURCES.md):
  - each batch uses one lot of each ingredient, drawn independently;
  - each raw column (protein, ash, amino acids as % of protein, ...) is drawn
    independently from a normal distribution, clipped to its physical range;
  - columns with no row in ingredient_variability.csv are held at their average,
    as are digestibility coefficients.
Amino acids are stored as % of protein, so they move with protein automatically.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .data import RAW_DIR, build_nutrient_matrix
from .model import NUTRIENT_COLUMNS

PCT_COLUMNS_DM = ["cp", "fat", "ash", "fibre", "starch"]  # % of dry matter, capped at 100


def load_variability(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or RAW_DIR / "ingredient_variability.csv")


def sample_raw(raw: pd.DataFrame, variability: pd.DataFrame, n: int, seed: int = 0,
               ingredients: list[str] | None = None) -> pd.DataFrame:
    """Return n random draws of the raw composition table, indexed by (sim, ingredient)."""
    rng = np.random.default_rng(seed)
    base = raw.loc[ingredients] if ingredients is not None else raw
    stacked = pd.concat({s: base for s in range(n)}, names=["sim", "ingredient"])
    varied = [c for c in variability["column"].unique() if c in stacked.columns]
    stacked[varied] = stacked[varied].astype(float)
    for row in variability.itertuples():
        if row.ingredient not in base.index or row.sd <= 0:
            continue
        mask = stacked.index.get_level_values("ingredient") == row.ingredient
        mean = float(base.at[row.ingredient, row.column])
        draws = rng.normal(mean, float(row.sd), size=int(mask.sum()))
        upper = 100.0 if row.column in PCT_COLUMNS_DM + ["dm", "epa_dha_pct_fat"] else np.inf
        stacked.loc[mask, row.column] = np.clip(draws, 0.0, upper)
    return stacked


def simulate_profiles(recipe_pct: pd.Series, raw: pd.DataFrame, variability: pd.DataFrame,
                      n: int = 10_000, seed: int = 0) -> pd.DataFrame:
    """Dry matter nutrient profile of n simulated batches of one recipe (one row per batch)."""
    x = recipe_pct[recipe_pct > 0] / 100.0
    stacked = sample_raw(raw, variability, n, seed, ingredients=list(x.index))
    nm = build_nutrient_matrix(stacked)
    w = nm.index.get_level_values("ingredient").map(x).to_numpy()

    cols = list(dict.fromkeys(["dm", "digestible_protein", *NUTRIENT_COLUMNS.values()]))
    weighted = nm[cols].mul(w, axis=0).groupby(level="sim").sum()
    dm = weighted["dm"]
    prof = pd.DataFrame({"dry_matter_pct_asfed": dm * 100})
    for name, col in NUTRIENT_COLUMNS.items():
        prof[name] = weighted[col] / dm
    prof["digestible_protein"] = weighted["digestible_protein"] / dm
    prof["dp_de_ratio"] = prof["digestible_protein"] * 10 / prof["digestible_energy"]
    return prof


def compliance_table(profiles: pd.DataFrame, requirements: pd.DataFrame) -> pd.DataFrame:
    """Per requirement: spread of the simulated nutrient and the share of batches that miss it."""
    rows = []
    for r in requirements.itertuples():
        v = profiles[r.nutrient]
        miss = (v < r.value) if r.bound == "min" else (v > r.value)
        rows.append({
            "nutrient": r.nutrient, "bound": r.bound, "requirement": r.value, "unit": r.unit,
            "mean": v.mean(), "sd": v.std(), "p5": v.quantile(0.05), "p95": v.quantile(0.95),
            "pct_batches_failing": 100 * miss.mean(),
            # distance the average must sit from the limit so that 95% of batches meet it
            "margin_for_95pct": 1.645 * v.std(),
        })
    return pd.DataFrame(rows)


def variance_contribution(recipe_pct: pd.Series, raw: pd.DataFrame, variability: pd.DataFrame,
                          nutrients: list[str], n: int = 5_000, seed: int = 0) -> pd.DataFrame:
    """Share (%) of each nutrient's batch-to-batch variance caused by each ingredient.

    Varies one ingredient at a time and normalises the variances to sum to 100.
    Exact for nutrients linear in composition; a close approximation for the
    dry matter ratios used here.
    """
    used = [i for i in recipe_pct[recipe_pct > 0].index if i in set(variability["ingredient"])]
    var = {}
    for ing in used:
        prof = simulate_profiles(recipe_pct, raw, variability[variability["ingredient"] == ing], n, seed)
        var[ing] = prof[nutrients].var()
    table = pd.DataFrame(var).T  # rows: ingredient, cols: nutrient
    return 100 * table / table.sum()


def batch_pass_rate(profiles: pd.DataFrame, requirements: pd.DataFrame) -> float:
    """Share of batches (%) that meet every requirement at once."""
    ok = pd.Series(True, index=profiles.index)
    for r in requirements.itertuples():
        v = profiles[r.nutrient]
        ok &= (v >= r.value) if r.bound == "min" else (v <= r.value)
    return 100 * float(ok.mean())
