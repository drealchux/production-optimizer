"""Load the raw data files and convert ingredient composition to an as-fed nutrient matrix.

Raw composition (data/raw/ingredients_raw.csv) follows Feedipedia conventions:
  dm             % as fed
  cp, fat, ash, fibre, starch   % of dry matter
  ge             MJ/kg dry matter
  p              g/kg dry matter
  amino acids    % of crude protein (aa_basis = pct_protein) or % as fed (pct_asfed)
  epa_dha_pct_fat  EPA+DHA as % of total fat

Everything the optimizer uses is converted to a per kg AS-FED basis, so a recipe
is simply a vector of as-fed inclusion fractions that sum to 1.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RAW_DIR = DATA_DIR / "raw"

AMINO_ACIDS = ["lys", "met", "thr", "trp", "arg", "his", "ile", "leu", "phe", "val"]


def load_raw_ingredients(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or RAW_DIR / "ingredients_raw.csv").set_index("ingredient")


def build_nutrient_matrix(raw: pd.DataFrame) -> pd.DataFrame:
    """Return one row per ingredient with nutrients per kg as fed.

    Columns:
      dm                    fraction (0 to 1)
      crude_protein, crude_lipid, ash, fibre, starch, phosphorus, epa_dha, AAs   % as fed
      digestible_protein    % as fed
      digestible_energy     MJ/kg as fed
    """
    dmf = raw["dm"] / 100.0
    out = pd.DataFrame(index=raw.index)
    out["category"] = raw["category"]
    out["dm"] = dmf
    out["crude_protein"] = raw["cp"] * dmf
    out["crude_lipid"] = raw["fat"] * dmf
    out["ash"] = raw["ash"] * dmf
    out["fibre"] = raw["fibre"] * dmf
    out["starch"] = raw["starch"] * dmf
    out["phosphorus"] = raw["p"] / 10.0 * dmf  # g/kg -> %
    out["epa_dha"] = out["crude_lipid"] * raw["epa_dha_pct_fat"] / 100.0
    out["digestible_protein"] = out["crude_protein"] * raw["adc_protein"]
    out["digestible_energy"] = raw["ge"] * dmf * raw["adc_energy"]
    for aa in AMINO_ACIDS:
        as_protein = raw[aa] * out["crude_protein"] / 100.0
        out[aa] = as_protein.where(raw["aa_basis"] == "pct_protein", raw[aa])
    return out


def load_prices(path: Path | None = None) -> pd.Series:
    df = pd.read_csv(path or RAW_DIR / "prices.csv").set_index("ingredient")
    return df["price_usd_per_t"].astype(float)


def load_price_table(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or RAW_DIR / "prices.csv").set_index("ingredient")


def load_requirements(profile: str = "grower_1_2kg", path: Path | None = None) -> pd.DataFrame:
    req = pd.read_csv(path or RAW_DIR / "requirements.csv")
    req = req[req["profile"] == profile]
    if req.empty:
        raise ValueError(f"Unknown requirement profile: {profile}")
    return req.reset_index(drop=True)


def list_profiles(path: Path | None = None) -> list[str]:
    return sorted(pd.read_csv(path or RAW_DIR / "requirements.csv")["profile"].unique())


def load_inclusion_limits(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or RAW_DIR / "inclusion_limits.csv").set_index("ingredient")


def load_price_history(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or RAW_DIR / "price_history.csv")


def load_benchmarks(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or RAW_DIR / "benchmarks.csv")


def load_all(profile: str = "grower_1_2kg"):
    """Convenience loader: (nutrient matrix, prices, requirements, limits)."""
    raw = load_raw_ingredients()
    return (
        build_nutrient_matrix(raw),
        load_prices(),
        load_requirements(profile),
        load_inclusion_limits(),
    )
