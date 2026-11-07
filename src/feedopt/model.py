"""Least-cost salmon feed formulation as a linear program (PuLP + CBC).

Decision variables: x_i = as-fed inclusion of ingredient i (fraction of 1 kg feed).

Requirements are given on a DRY MATTER basis (as in the FAO tables), so a
requirement "nutrient >= r % DM" is written linearly as

    sum_i x_i * n_i  >=  r * sum_i x_i * dm_i

and the DP/DE ratio "DP/DE >= k g/MJ" as

    sum_i x_i * dp_i * 10  >=  k * sum_i x_i * de_i
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pulp

NUTRIENT_COLUMNS = {
    "crude_protein": "crude_protein",
    "crude_lipid": "crude_lipid",
    "ash": "ash",
    "fibre": "fibre",
    "starch": "starch",
    "phosphorus": "phosphorus",
    "epa_dha": "epa_dha",
    "digestible_energy": "digestible_energy",
    "lys": "lys", "met": "met", "thr": "thr", "trp": "trp", "arg": "arg",
    "his": "his", "ile": "ile", "leu": "leu", "phe": "phe", "val": "val",
}


@dataclass
class FormulationResult:
    status: str
    cost_usd_per_t: float | None
    recipe: pd.Series  # % as fed
    nutrients_dm: pd.Series  # nutrient profile on DM basis
    shadow_prices: pd.DataFrame  # binding constraints and their marginal cost
    reduced_costs: pd.Series  # USD/t price drop needed before an unused ingredient enters
    extra: dict = field(default_factory=dict)

    @property
    def feasible(self) -> bool:
        return self.status == "Optimal"


def _diet_profile(x: pd.Series, nm: pd.DataFrame) -> pd.Series:
    """Nutrient profile of a recipe (x as fractions) on a dry matter basis."""
    dm = float((x * nm["dm"]).sum())
    prof = {"dry_matter_pct_asfed": dm * 100}
    for name, col in NUTRIENT_COLUMNS.items():
        prof[name] = float((x * nm[col]).sum()) / dm
    dp = float((x * nm["digestible_protein"]).sum()) / dm
    prof["digestible_protein"] = dp
    prof["dp_de_ratio"] = dp * 10 / prof["digestible_energy"] if prof["digestible_energy"] else float("nan")
    return pd.Series(prof)


def formulate(
    nm: pd.DataFrame,
    prices: pd.Series,
    requirements: pd.DataFrame,
    limits: pd.DataFrame | None = None,
    availability_cap: dict[str, float] | None = None,
    extra_max_groups: dict[str, tuple[list[str], float]] | None = None,
    exclude: list[str] | None = None,
) -> FormulationResult:
    """Solve the least-cost formulation.

    availability_cap: {ingredient: max % as fed}, e.g. from stock on hand.
    extra_max_groups: {name: ([ingredients], max % as fed)}, e.g. marine ingredient cap.
    exclude: ingredients to remove entirely.
    """
    ingredients = [i for i in nm.index if i in prices.index and i not in (exclude or [])]
    prob = pulp.LpProblem("least_cost_salmon_feed", pulp.LpMinimize)
    x = {i: pulp.LpVariable(f"x_{i}", lowBound=0, upBound=1) for i in ingredients}

    prob += pulp.lpSum(prices[i] * x[i] for i in ingredients), "cost_usd_per_t"
    prob += pulp.lpSum(x.values()) == 1, "mix_sums_to_one"

    dm_expr = pulp.lpSum(nm.at[i, "dm"] * x[i] for i in ingredients)
    de_expr = pulp.lpSum(nm.at[i, "digestible_energy"] * x[i] for i in ingredients)

    named = {}
    for row in requirements.itertuples():
        nutrient, bound, value = row.nutrient, row.bound, float(row.value)
        cname = f"{nutrient}_{bound}"
        if nutrient == "dp_de_ratio":
            lhs = pulp.lpSum(nm.at[i, "digestible_protein"] * 10 * x[i] for i in ingredients)
            expr = lhs - value * de_expr
        else:
            col = NUTRIENT_COLUMNS[nutrient]
            expr = pulp.lpSum(nm.at[i, col] * x[i] for i in ingredients) - value * dm_expr
        prob += (expr >= 0) if bound == "min" else (expr <= 0), cname
        named[cname] = (nutrient, bound, value)

    if limits is not None:
        for ing, lim in limits.iterrows():
            if ing in x:
                if lim["min_pct"] > 0:
                    prob += x[ing] >= lim["min_pct"] / 100, f"limit_{ing}_min"
                prob += x[ing] <= lim["max_pct"] / 100, f"limit_{ing}_max"

    for ing, cap in (availability_cap or {}).items():
        if ing in x:
            prob += x[ing] <= cap / 100, f"stock_{ing}_max"

    for gname, (members, cap) in (extra_max_groups or {}).items():
        prob += pulp.lpSum(x[m] for m in members if m in x) <= cap / 100, f"group_{gname}_max"

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    status = pulp.LpStatus[prob.status]
    if status != "Optimal":
        empty = pd.Series(dtype=float)
        return FormulationResult(status, None, empty, empty, pd.DataFrame(), empty)

    xs = pd.Series({i: x[i].value() or 0.0 for i in ingredients})
    xs[xs.abs() < 1e-9] = 0.0
    diet_dm = float((xs * nm.loc[xs.index, "dm"]).sum())

    rows = []
    for cname, c in prob.constraints.items():
        pi = c.pi or 0.0
        if abs(pi) < 1e-7:
            continue
        if cname in named:
            nutrient, bound, value = named[cname]
            # d(cost)/d(requirement): constraint is sum x(n - r*dm) >= 0, so dRHS = dm per unit r
            scale = diet_dm if nutrient != "dp_de_ratio" else float((xs * nm.loc[xs.index, "digestible_energy"]).sum())
            rows.append({"constraint": cname, "nutrient": nutrient, "bound": bound, "requirement": value,
                         "usd_per_t_per_unit": abs(pi) * scale})
        elif cname != "mix_sums_to_one":
            rows.append({"constraint": cname, "nutrient": cname, "bound": "max" if cname.endswith("_max") else "min",
                         "requirement": None, "usd_per_t_per_unit": abs(pi) / 100})
    shadow = pd.DataFrame(rows).sort_values("usd_per_t_per_unit", ascending=False) if rows else pd.DataFrame()

    reduced = pd.Series({i: x[i].dj for i in ingredients if xs[i] == 0 and x[i].dj is not None})

    return FormulationResult(
        status=status,
        cost_usd_per_t=float(pulp.value(prob.objective)),
        recipe=(xs * 100).sort_values(ascending=False),
        nutrients_dm=_diet_profile(xs, nm.loc[xs.index]),
        shadow_prices=shadow,
        reduced_costs=reduced.sort_values(),
    )


def evaluate_recipe(recipe_pct: pd.Series, nm: pd.DataFrame, prices: pd.Series) -> tuple[float, pd.Series]:
    """Cost and DM nutrient profile of any given recipe (in % as fed)."""
    x = recipe_pct / 100
    return float((x * prices.reindex(x.index)).sum()), _diet_profile(x, nm.loc[x.index])


def check_requirements(profile: pd.Series, requirements: pd.DataFrame, tol: float = 1e-6) -> pd.DataFrame:
    """Compare a DM nutrient profile against requirements."""
    rows = []
    for r in requirements.itertuples():
        actual = float(profile[r.nutrient])
        ok = actual >= r.value - tol if r.bound == "min" else actual <= r.value + tol
        rows.append({"nutrient": r.nutrient, "bound": r.bound, "requirement": r.value,
                     "actual": round(actual, 3), "unit": r.unit, "met": ok})
    return pd.DataFrame(rows)
