"""Chance-constrained least-cost formulation: meet each requirement in alpha% of batches.

The LP in model.py writes a dry matter requirement as

    sum_i x_i * a_i >= 0,     a_i = n_i - r * dm_i          (min bound)
                              a_i = r * dm_i - n_i          (max bound)
                              a_i = 10 * dp_i - k * de_i    (DP/DE ratio)

with every a_i at its average. Here a_i is random. Ingredient lots are
independent, so the blend's coefficient has mean mu'x and variance
sum_i sigma_i^2 x_i^2. Treating it as normal, P(a'x >= 0) >= alpha becomes

    mu'x - z_alpha * || diag(sigma) x ||_2  >=  0

which is a second-order cone constraint (convex for alpha >= 0.5). At
alpha = 0.5, z = 0 and the model is exactly the LP. sigma_i is estimated by
simulating each ingredient's composition with uncertainty.sample_raw, so the
unit conversion and dry matter effects are the same as everywhere else.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import cvxpy as cp
import numpy as np
import pandas as pd

from .data import build_nutrient_matrix
from .model import NUTRIENT_COLUMNS, _diet_profile, formulate
from .uncertainty import batch_pass_rate, compliance_table, sample_raw, simulate_profiles


def _coefficients(nm: pd.DataFrame, nutrient: str, bound: str, value: float) -> pd.Series:
    """Per-ingredient constraint coefficient a_i, oriented so that a'x >= 0 means 'met'."""
    if nutrient == "dp_de_ratio":
        a = nm["digestible_protein"] * 10 - value * nm["digestible_energy"]
    else:
        a = nm[NUTRIENT_COLUMNS[nutrient]] - value * nm["dm"]
    return a if bound == "min" else -a


def coefficient_sd(raw: pd.DataFrame, variability: pd.DataFrame, requirements: pd.DataFrame,
                   n: int = 20_000, seed: int = 0) -> pd.DataFrame:
    """Standard deviation of each constraint coefficient, rows = ingredient, cols = '<nutrient>_<bound>'."""
    sims = build_nutrient_matrix(sample_raw(raw, variability, n, seed))
    out = {}
    for r in requirements.itertuples():
        a = _coefficients(sims, r.nutrient, r.bound, float(r.value))
        out[f"{r.nutrient}_{r.bound}"] = a.groupby(level="ingredient").std()
    return pd.DataFrame(out).reindex(raw.index).fillna(0.0)


@dataclass
class ChanceResult:
    status: str
    alpha: float
    cost_usd_per_t: float | None
    recipe: pd.Series  # % as fed
    nutrients_dm: pd.Series

    @property
    def feasible(self) -> bool:
        return self.status == "optimal"


def formulate_chance(nm: pd.DataFrame, prices: pd.Series, requirements: pd.DataFrame,
                     limits: pd.DataFrame | None, sd: pd.DataFrame, alpha: float = 0.95) -> ChanceResult:
    """Least-cost recipe that meets every requirement individually with probability alpha."""
    if not 0.5 <= alpha < 1:
        raise ValueError("alpha must be in [0.5, 1)")
    z = NormalDist().inv_cdf(alpha)
    ings = [i for i in nm.index if i in prices.index]
    x = cp.Variable(len(ings), nonneg=True)
    cons = [cp.sum(x) == 1]
    for r in requirements.itertuples():
        mu = _coefficients(nm.loc[ings], r.nutrient, r.bound, float(r.value)).to_numpy()
        s = sd.loc[ings, f"{r.nutrient}_{r.bound}"].to_numpy()
        if z > 0 and s.any():
            cons.append(mu @ x - z * cp.norm(cp.multiply(s, x), 2) >= 0)
        else:
            cons.append(mu @ x >= 0)
    if limits is not None:
        for k, ing in enumerate(ings):
            if ing in limits.index:
                cons += [x[k] >= limits.at[ing, "min_pct"] / 100, x[k] <= limits.at[ing, "max_pct"] / 100]
    prob = cp.Problem(cp.Minimize(prices.loc[ings].to_numpy() @ x), cons)
    prob.solve(solver=cp.CLARABEL)
    if prob.status != "optimal":
        empty = pd.Series(dtype=float)
        return ChanceResult(prob.status, alpha, None, empty, empty)
    xs = pd.Series(np.clip(x.value, 0, None), index=ings)
    xs[xs < 1e-7] = 0.0
    xs /= xs.sum()
    return ChanceResult(prob.status, alpha, float(prices.loc[ings] @ xs),
                        (xs * 100).sort_values(ascending=False), _diet_profile(xs, nm.loc[ings]))


def fixed_margin_formulation(nm, prices, requirements, limits, raw, variability, base_recipe_pct,
                             alpha: float = 0.95, n: int = 10_000, seed: int = 0):
    """Common shortcut: simulate the LP recipe once, move each requirement inward by
    z_alpha standard deviations of that recipe, and re-run the LP."""
    z = NormalDist().inv_cdf(alpha)
    comp = compliance_table(simulate_profiles(base_recipe_pct, raw, variability, n, seed), requirements)
    shifted = requirements.copy()
    sign = np.where(shifted["bound"] == "min", 1.0, -1.0)
    shifted["value"] = shifted["value"] + sign * z * comp["sd"].to_numpy()
    return formulate(nm, prices, shifted, limits)


def validate(recipe_pct: pd.Series, raw, variability, requirements, n: int = 10_000, seed: int = 1) -> dict:
    """Simulated reliability of a recipe: share of batches meeting everything, and the weakest requirement."""
    prof = simulate_profiles(recipe_pct, raw, variability, n, seed)
    comp = compliance_table(prof, requirements)
    worst = comp.loc[comp["pct_batches_failing"].idxmax()]
    return {"all_requirements_pct": batch_pass_rate(prof, requirements),
            "weakest_requirement": f"{worst['nutrient']}_{worst['bound']}",
            "weakest_pass_pct": 100 - worst["pct_batches_failing"]}


def reliability_curve(nm, prices, requirements, limits, sd, raw, variability, alphas,
                      n_validate: int = 10_000) -> pd.DataFrame:
    """Cost and simulated reliability of the chance-constrained recipe at each alpha."""
    rows = []
    for a in alphas:
        res = formulate_chance(nm, prices, requirements, limits, sd, a)
        row = {"alpha_pct": 100 * a, "status": res.status, "cost_usd_per_t": res.cost_usd_per_t}
        if res.feasible:
            row |= validate(res.recipe, raw, variability, requirements, n_validate)
            row |= res.recipe.to_dict()
        rows.append(row)
    return pd.DataFrame(rows).fillna({c: 0.0 for c in nm.index})
