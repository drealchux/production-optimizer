import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from feedopt.data import load_all, load_raw_ingredients, build_nutrient_matrix  # noqa: E402
from feedopt.model import check_requirements, evaluate_recipe, formulate  # noqa: E402
from feedopt.planning import availability_aware_formulation  # noqa: E402
from feedopt.scenarios import marine_cap, price_sweep  # noqa: E402


@pytest.fixture(scope="module")
def setup():
    return load_all("grower_1_2kg")


def test_unit_conversion_fish_meal():
    nm = build_nutrient_matrix(load_raw_ingredients())
    # 74.8 % DM protein at 92.2 % DM -> 68.97 % as fed
    assert nm.at["fish_meal", "crude_protein"] == pytest.approx(68.97, abs=0.01)
    # lysine 7.5 g/16 g N of protein
    assert nm.at["fish_meal", "lys"] == pytest.approx(68.97 * 0.075, abs=0.01)


def test_base_is_feasible_and_sums_to_100(setup):
    r = formulate(*setup)
    assert r.feasible
    assert r.recipe.sum() == pytest.approx(100, abs=1e-6)
    assert (r.recipe >= -1e-9).all()


def test_all_requirements_met(setup):
    nm, prices, req, limits = setup
    r = formulate(nm, prices, req, limits)
    assert check_requirements(r.nutrients_dm, req)["met"].all()


def test_inclusion_limits_respected(setup):
    nm, prices, req, limits = setup
    r = formulate(nm, prices, req, limits)
    for ing, lim in limits.iterrows():
        assert lim["min_pct"] - 1e-6 <= r.recipe.get(ing, 0) <= lim["max_pct"] + 1e-6


def test_evaluate_matches_objective(setup):
    nm, prices, req, limits = setup
    r = formulate(nm, prices, req, limits)
    cost, _ = evaluate_recipe(r.recipe, nm, prices)
    assert cost == pytest.approx(r.cost_usd_per_t, rel=1e-6)


def test_cost_never_falls_when_fish_oil_gets_dearer(setup):
    nm, prices, req, limits = setup
    sweep = price_sweep(nm, prices, req, limits, "fish_oil", [2000, 4000, 6000, 8000])
    assert sweep["cost_usd_per_t"].is_monotonic_increasing


def test_marine_cap_is_respected_and_costs_more(setup):
    nm, prices, req, limits = setup
    base = formulate(nm, prices, req, limits)
    capped = marine_cap(nm, prices, req, limits, max_marine_pct=8)
    assert capped.recipe[["fish_meal", "fish_oil"]].sum() <= 8 + 1e-6
    assert capped.cost_usd_per_t >= base.cost_usd_per_t - 1e-6


def test_availability_caps_respected(setup):
    nm, prices, req, limits = setup
    stock = pd.Series({"fish_oil": 100.0})
    r, caps = availability_aware_formulation(nm, prices, req, limits, 20_000, stock)
    assert r.recipe.get("fish_oil", 0) / 100 * 20_000 <= 100 + 1e-6


def test_impossible_requirement_is_infeasible(setup):
    nm, prices, req, limits = setup
    r2 = req.copy()
    r2.loc[r2["nutrient"] == "crude_protein", "value"] = 90
    assert not formulate(nm, prices, r2, limits).feasible
