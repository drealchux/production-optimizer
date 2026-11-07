"""Static charts (matplotlib) for the README and results folder."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Validated categorical order (fixed, never cycled)
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER = "#a3a29c"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"

LABELS = {
    "fish_meal": "Fish meal", "fish_oil": "Fish oil", "soy_protein_concentrate": "Soy protein conc.",
    "soybean_meal": "Soybean meal", "maize_gluten_meal": "Maize gluten", "wheat_gluten": "Wheat gluten",
    "pea_protein_concentrate": "Pea protein conc.", "faba_bean_dehulled": "Faba beans", "wheat": "Wheat",
    "rapeseed_oil": "Rapeseed oil", "algal_oil": "Algal oil", "monocalcium_phosphate": "MCP",
    "l_lysine_hcl": "Lysine", "dl_methionine": "Methionine", "premix": "Premix",
}
# Colour follows the ingredient, not its rank
COLOR_OF = {
    "fish_meal": PALETTE[0], "fish_oil": PALETTE[1], "soy_protein_concentrate": PALETTE[2],
    "rapeseed_oil": PALETTE[3], "maize_gluten_meal": PALETTE[4], "wheat": PALETTE[5],
    "algal_oil": PALETTE[6], "wheat_gluten": PALETTE[7],
}


def _style(ax, title, subtitle=None):
    fig = ax.figure
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, length=0, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=22)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=INK2)


def _fold(df: pd.DataFrame) -> pd.DataFrame:
    """Keep ingredients with a colour; fold the rest into Other."""
    keep = [c for c in df.columns if c in COLOR_OF]
    other = df[[c for c in df.columns if c not in COLOR_OF]].sum(axis=1)
    out = df[keep].copy()
    out["other"] = other
    return out


def recipe_bar(recipe: pd.Series, path: Path, title: str, subtitle: str):
    r = recipe[recipe > 0.05].sort_values()
    fig, ax = plt.subplots(figsize=(8, 4.8))
    colors = [COLOR_OF.get(i, OTHER) for i in r.index]
    ax.barh([LABELS.get(i, i) for i in r.index], r.values, color=colors, height=0.6, edgecolor=SURFACE, linewidth=2)
    for y, v in enumerate(r.values):
        ax.text(v + 0.4, y, f"{v:.1f}%", va="center", fontsize=9, color=INK)
    _style(ax, title, subtitle)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_xlabel("% of feed (as fed)", color=INK2, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def stacked_sweep(df: pd.DataFrame, xcol: str, path: Path, title: str, subtitle: str, xlabel: str):
    ing_cols = [c for c in df.columns if c in LABELS]
    folded = _fold(df[ing_cols])
    fig, ax = plt.subplots(figsize=(9, 5))
    x = df[xcol].values
    bottoms = 0
    cols = [c for c in folded.columns if c != "other"] + ["other"]
    ys = [folded[c].values for c in cols]
    colors = [COLOR_OF.get(c, OTHER) for c in cols]
    labels = [LABELS.get(c, "Other") for c in cols]
    ax.stackplot(x, ys, colors=colors, labels=labels, edgecolor=SURFACE, linewidth=1.5)
    _style(ax, title, subtitle)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel("% of feed", color=INK2, fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_xlim(x.min(), x.max())
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def line_chart(x, y, path: Path, title: str, subtitle: str, xlabel: str, ylabel: str, rotate=False):
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    ax.plot(x, y, color=PALETTE[0], linewidth=2, marker="o", markersize=6,
            markeredgecolor=SURFACE, markeredgewidth=2)
    for xi, yi in zip(list(x)[-1:], list(y)[-1:]):
        ax.annotate(f"{yi:,.0f}", (xi, yi), textcoords="offset points", xytext=(0, 8), ha="center",
                    fontsize=9, color=INK)
    _style(ax, title, subtitle)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    if rotate:
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def grouped_categories(table: pd.DataFrame, path: Path, title: str, subtitle: str):
    """table: index = category, columns = recipe names (max 3)."""
    fig, ax = plt.subplots(figsize=(9, 4.8))
    n = len(table.columns)
    width = 0.8 / n
    idx = range(len(table.index))
    for k, col in enumerate(table.columns):
        ax.bar([i + k * width - 0.4 + width / 2 for i in idx], table[col].values, width=width,
               color=PALETTE[k], label=col, edgecolor=SURFACE, linewidth=2)
    ax.set_xticks(list(idx))
    ax.set_xticklabels([c.replace("_", " ").capitalize() for c in table.index])
    _style(ax, title, subtitle)
    ax.set_ylabel("% of feed", color=INK2, fontsize=9)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def shadow_bar(shadow: pd.DataFrame, path: Path, title: str, subtitle: str):
    s = shadow.sort_values("usd_per_t_per_unit")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(s["constraint"], s["usd_per_t_per_unit"], color=PALETTE[0], height=0.6, edgecolor=SURFACE, linewidth=2)
    for y, v in enumerate(s["usd_per_t_per_unit"]):
        ax.text(v + 1, y, f"{v:.1f}", va="center", fontsize=9, color=INK)
    _style(ax, title, subtitle)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_xlabel("USD per tonne of feed, per 1 unit change in the constraint", color=INK2, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
