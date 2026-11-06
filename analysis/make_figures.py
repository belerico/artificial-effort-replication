#!/usr/bin/env python3
"""Generate the 11 figures of the paper into output/figures/.

LLM data: data/results_llm.db (treatments T0-T4). Human data:
data/results_human.db (used by Figures fig:task_difficulty and fig:heatmap).
Run from repo root:
    uv run python analysis/make_figures.py
"""

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.ticker as mtick
import seaborn as sns

from common import FIG_DIR, GAME_LABELS, TREATMENT_ORDER, load_human_trials, load_llm_data
from table_llm_vs_human import TASK_ORDER, fit, marginal_effects

# ── Global font settings (uniform across all figures) ──
sns.set_theme(style="whitegrid", context="notebook", palette="colorblind")
FONT = {
    "title": 20,
    "label": 18,
    "tick": 15,
    "annot": 13,
    "legend": 14,
    "legend_title": 15,
    "bar_label": 13,
}
plt.rcParams.update(
    {
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "font.family": "serif",
        "font.size": FONT["tick"],
        "axes.titlesize": FONT["title"],
        "axes.labelsize": FONT["label"],
        "xtick.labelsize": FONT["tick"],
        "ytick.labelsize": FONT["tick"],
        "legend.fontsize": FONT["legend"],
        "legend.title_fontsize": FONT["legend_title"],
    }
)

OUT = FIG_DIR
OUT.mkdir(parents=True, exist_ok=True)

_, grouped_df = load_llm_data()


def _rename_games(obj):
    """Rename game columns/index using GAME_LABELS. Works on Series, DataFrame, or list."""
    if isinstance(obj, pd.DataFrame):
        return obj.rename(columns=GAME_LABELS, index=GAME_LABELS)
    elif isinstance(obj, pd.Series):
        return obj.rename(index=GAME_LABELS)
    elif isinstance(obj, list):
        return [GAME_LABELS.get(g, g) for g in obj]
    return obj


MODEL_COLORS = {
    # Anthropic (amber/brown — warm, saturated)
    "claude-haiku-4.5": "#F5D490",
    "claude-sonnet-3.7": "#E8B850",
    "claude-sonnet-4": "#D49C28",
    "claude-sonnet-4.5": "#C08418",
    "claude-sonnet-4.6": "#A06A10",
    "claude-opus-4.5": "#7A4E0C",
    "claude-opus-4.6": "#583608",
    # Google (blues — vivid spread)
    "gemini-2.5-flash-lite": "#B8D4F0",
    "gemini-3.1-flash-lite": "#88B8E8",
    "gemini-2.5-flash": "#5898D8",
    "gemini-3-flash": "#3078C0",
    "gemini-2.5-pro": "#1860A8",
    "gemini-3.1-pro": "#0A4080",
    # OpenAI — GPT series (greens) + O series (teal, distinct hue)
    "gpt-5.4-nano": "#B8E0BA",
    "gpt-5-mini": "#88C88E",
    "gpt-5.4-mini": "#5CB064",
    "gpt-5": "#389840",
    "gpt-5.1": "#207828",
    "gpt-5.2": "#106018",
    "gpt-5.4": "#084A10",
    "o4-mini": "#6CCEC4",
    "o4-mini-high": "#30A89C",
    "o3": "#108878",
}

MODEL_ABBREV = {
    # Anthropic
    "claude-sonnet-3.7": "CS3.7",
    "claude-haiku-4.5": "CH4.5",
    "claude-sonnet-4": "CS4",
    "claude-sonnet-4.5": "CS4.5",
    "claude-sonnet-4.6": "CS4.6",
    "claude-opus-4.5": "CO4.5",
    "claude-opus-4.6": "CO4.6",
    # Google
    "gemini-2.5-flash": "G2.5F",
    "gemini-2.5-flash-lite": "G2.5FL",
    "gemini-2.5-pro": "G2.5P",
    "gemini-3-flash": "G3F",
    "gemini-3.1-flash-lite": "G3.1FL",
    "gemini-3.1-pro": "G3.1P",
    # OpenAI
    "gpt-5": "GPT5",
    "gpt-5-mini": "GPT5m",
    "gpt-5.1": "GPT5.1",
    "gpt-5.2": "GPT5.2",
    "gpt-5.4": "GPT5.4",
    "gpt-5.4-mini": "GPT5.4m",
    "gpt-5.4-nano": "GPT5.4n",
    "o3": "O3",
    "o4-mini": "O4m",
    "o4-mini-high": "O4mH",
}


def _family_color(m):
    """Return the family color for a model short name."""
    if m.startswith("claude"):
        return "#C08418"
    elif m.startswith("gemini"):
        return "#3078C0"
    else:
        return "#389840"


def model_abbrev_legend(
    ax_or_fig, ncol=3, fontsize=10, use_family_colors=False, **kwargs
):
    """Add a legend mapping abbreviated labels to full model names with colored dots."""
    from matplotlib.lines import Line2D

    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=_family_color(m) if use_family_colors else MODEL_COLORS[m],
            markersize=8,
            label=f"{MODEL_ABBREV[m]} = {m}",
        )
        for m in sort_by_family(list(MODEL_ABBREV.keys()))
    ]
    return ax_or_fig.legend(handles=handles, ncol=ncol, fontsize=fontsize, **kwargs)


MODEL_RELEASE_TS = {
    "claude-sonnet-3.7": 1740422110,
    "claude-sonnet-4": 1747930371,
    "claude-haiku-4.5": 1760547638,
    "claude-sonnet-4.5": 1759161676,
    "claude-opus-4.5": 1764010580,
    "claude-opus-4.6": 1770219050,
    "claude-sonnet-4.6": 1771342990,
    "gemini-2.5-pro": 1750169544,
    "gemini-2.5-flash": 1750172488,
    "gemini-2.5-flash-lite": 1753200276,
    "gemini-3-flash": 1765987078,
    "gemini-3.1-flash-lite": 1772512673,
    "gemini-3.1-pro": 1771509627,
    "o3": 1744823457,
    "o4-mini": 1744820942,
    "o4-mini-high": 1744824212,
    "gpt-5-mini": 1754587407,
    "gpt-5": 1754587413,
    "gpt-5.1": 1763060305,
    "gpt-5.2": 1765389775,
    "gpt-5.4": 1772734352,
    "gpt-5.4-mini": 1773748178,
    "gpt-5.4-nano": 1773748187,
}


def sort_by_family(model_list):
    def _key(m):
        for prefix, order in [
            ("claude", 0),
            ("gemini", 1),
            ("gpt", 2),
            ("o3", 2),
            ("o4", 2),
        ]:
            if m.startswith(prefix):
                return (order, m)
        return (9, m)

    return sorted(model_list, key=_key)


# ── T0-only subset (used for the main-paper figures) ──
t0 = grouped_df[grouped_df["treatment"] == "T0: Control"]
avg_t0 = t0
# ── All treatments ──
avg = grouped_df

# ── Shared heatmap ordering and colormap ──
# Models grouped by family; tasks ordered by accuracy averaged over treatments.
avg_pivot = (
    avg.pivot_table(index="model_short", columns="game", values="accuracy") * 100
)
_mean_acc = avg_pivot.mean(axis=1)
_fam_key = lambda m: (
    0 if m.startswith("claude") else (1 if m.startswith("gemini") else 2)
)
model_order_h = sorted(_mean_acc.index, key=lambda m: (_fam_key(m), -_mean_acc[m]))
game_order_h = avg_pivot.mean(axis=0).sort_values(ascending=False).index.tolist()
# Accuracy heatmaps: pale yellow (low) -> teal -> dark blue (high)
_cmap_acc = "YlGnBu"


# ═══ Figure fig:task_difficulty — fig3_t0_task_difficulty.pdf ═══
# LLM bar: mean (± SE) over the 23 models of per-model T0 accuracy on each task.
_t0_gd = (
    avg_t0.groupby("game", observed=True)["accuracy"]
    .agg(["mean", "std", "count"])
    .sort_values("mean", ascending=True)
)
_t0_gd["se"] = _t0_gd["std"] / np.sqrt(_t0_gd["count"])
# Human bar: mean (± SE) over all participants of per-participant accuracy on each
# task (everyone who attempted it, not just the both-days intersection) —
# symmetric with the LLM (one accuracy value per agent per task).
_hum_trials = load_human_trials()
_hum_pg = _hum_trials.groupby(["participant", "game"])["is_correct"].mean().reset_index()
_hum_gd = _hum_pg.groupby("game")["is_correct"].agg(["mean", "std", "count"])
_hum_gd["se"] = _hum_gd["std"] / np.sqrt(_hum_gd["count"])

# Per-task LLM-vs-human difference p-values, from the same model as Table
# tab:avg_llm_hum (analysis/table_llm_vs_human.py).
_llm_hum_pval = dict(zip(TASK_ORDER, marginal_effects(fit())["P"]))


def _fmt_pval(p):
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


_game_order = _t0_gd.index.tolist()
_y = np.arange(len(_game_order))
_bh = 0.4
_llm_m, _llm_se = _t0_gd["mean"].values, _t0_gd["se"].values
_hum_m = _hum_gd["mean"].reindex(_game_order).values
_hum_se = _hum_gd["se"].reindex(_game_order).values

fig, ax = plt.subplots(figsize=(12, 7))
ax.barh(
    _y - _bh / 2,
    _hum_m,
    _bh,
    color="#DD8452",
    edgecolor="white",
    label="Human",
)
ax.barh(
    _y + _bh / 2,
    _llm_m,
    _bh,
    color="#4C72B0",
    edgecolor="white",
    label="LLM",
)
ax.set_yticks(_y)
ax.set_yticklabels([GAME_LABELS.get(g, g) for g in _game_order])
ax.set_xlim(0, 1.32)
ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))
ax.set_xticks(np.arange(0, 1.01, 0.2))  # cap axis at 100%; p-value column sits beyond
ax.set_xlabel("Accuracy")
ax.grid(axis="x", alpha=0.3)
ax.grid(axis="y", visible=False)  # no horizontal gridlines
_leg = ax.legend(
    fontsize=FONT["legend"],
    ncol=2,
    loc="upper center",
    bbox_to_anchor=(0.5, -0.16),
    framealpha=0.9,
)
for i in range(len(_game_order)):
    ax.text(
        _hum_m[i] + 0.01,
        i - _bh / 2,
        f"{_hum_m[i]:.1%}",
        va="center",
        fontsize=FONT["bar_label"] - 1,
    )
    ax.text(
        _llm_m[i] + 0.01,
        i + _bh / 2,
        f"{_llm_m[i]:.1%}",
        va="center",
        fontsize=FONT["bar_label"] - 1,
    )
    # LLM-vs-human difference p-value (Table tab:avg_llm_hum), right-aligned column
    ax.text(
        1.30,
        i,
        _fmt_pval(_llm_hum_pval[_game_order[i]]),
        va="center",
        ha="right",
        fontsize=FONT["bar_label"] - 1,
        color="#333333",
    )
fig.savefig(
    OUT / "fig3_t0_task_difficulty.pdf",
    bbox_extra_artists=[_leg],
    bbox_inches="tight",
)
plt.close(fig)
print("fig3_t0")

# ═══ Figure fig:family_evolution — fig_accuracy_by_tier.pdf ═══
# Define tiers per family, ordered from highest to lowest tier
_TIERS = {
    "Anthropic": {
        "Opus": ["claude-opus-4.5", "claude-opus-4.6"],
        "Sonnet": [
            "claude-sonnet-3.7",
            "claude-sonnet-4",
            "claude-sonnet-4.5",
            "claude-sonnet-4.6",
        ],
        "Haiku": ["claude-haiku-4.5"],
    },
    "Google": {
        "Pro": ["gemini-2.5-pro", "gemini-3.1-pro"],
        "Flash": ["gemini-2.5-flash", "gemini-3-flash"],
        "Flash Lite": ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite"],
    },
    "OpenAI": {
        "GPT-5": ["gpt-5", "gpt-5.1", "gpt-5.2", "gpt-5.4"],
        "Mini": ["gpt-5-mini", "gpt-5.4-mini"],
        "Nano": ["gpt-5.4-nano"],
        "o-series": ["o3", "o4-mini", "o4-mini-high"],
    },
}

# Get T0 accuracy per model
_tier_acc = t0.groupby("model_short", observed=True)["accuracy"].mean()

# Sort models within each tier by release date (newest first)
for fam in _TIERS:
    for tier in _TIERS[fam]:
        _TIERS[fam][tier] = sorted(
            _TIERS[fam][tier],
            key=lambda m: MODEL_RELEASE_TS.get(m, 0),
            reverse=True,
        )

FAMILY_PLOT_COLORS = {
    "Anthropic": "#C08418",
    "Google": "#3078C0",
    "OpenAI": "#389840",
}

fig, axes = plt.subplots(1, 3, figsize=(20, 9), sharey=True)

for ax, (fam, tiers) in zip(axes, _TIERS.items()):
    fam_color = FAMILY_PLOT_COLORS[fam]
    positions = []
    labels = []
    colors = []
    values = []
    tier_boundaries = []
    tier_labels = []
    pos = 0

    for tier_name, models in tiers.items():
        tier_start = pos
        n = len(models)
        for i, m in enumerate(models):
            acc = _tier_acc.get(m, 0)
            # Fade older models, saturate newer ones (newest = index 0 = darkest)
            alpha = 1.0 - 0.6 * (i / max(n - 1, 1))
            positions.append(pos)
            labels.append(MODEL_ABBREV.get(m, m))
            values.append(acc)
            colors.append(alpha)
            pos += 1
        tier_mid = (tier_start + pos - 1) / 2
        tier_labels.append((tier_mid, tier_name))
        pos += 0.8  # gap between tiers
        tier_boundaries.append(pos - 0.4)

    bars = ax.bar(
        positions,
        values,
        color=[(*matplotlib.colors.to_rgb(fam_color), a) for a in colors],
        edgecolor="white",
        linewidth=0.8,
        width=0.7,
    )

    # Value labels on bars
    for p, v in zip(positions, values):
        ax.text(
            p,
            v + 0.01,
            f"{v:.1%}",
            ha="center",
            va="bottom",
            fontsize=FONT["bar_label"] - 2,
        )

    ax.set_xticks(positions)
    ax.set_xticklabels(
        [m for tier_models in tiers.values() for m in tier_models],
        rotation=90,
        ha="center",
        fontsize=FONT["tick"] - 3,
    )
    ax.set_ylim(0.45, 0.9)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_ylabel("Accuracy" if ax == axes[0] else "")
    ax.set_title(fam, fontsize=FONT["title"], color=fam_color, pad=15)
    ax.grid(axis="y", alpha=0.3)

    # Tier labels below x-axis labels
    for mid, tname in tier_labels:
        ax.text(
            mid,
            -0.38,
            tname,
            ha="center",
            va="top",
            fontsize=FONT["legend"],
            fontweight="bold",
            transform=ax.get_xaxis_transform(),
        )

    # Vertical separators between tiers
    for b in tier_boundaries[:-1]:
        ax.axvline(x=b, color="gray", linewidth=0.8, linestyle=":", alpha=0.5)

# Arrow annotation: darker = newer
from matplotlib.patches import FancyArrowPatch

fig.text(
    0.5,
    0.05,
    r"Darker $\rightarrow$ newer release within each tier",
    ha="center",
    fontsize=FONT["legend"],
    fontstyle="italic",
    color="gray",
)

fig.tight_layout()
fig.savefig(OUT / "fig_accuracy_by_tier.pdf", bbox_inches="tight")
plt.close(fig)
print("fig_accuracy_by_tier")

# ═══ Figure fig:heatmap — fig1_t0_accuracy_heatmap_human.pdf ═══
# T0 accuracy per model and task, plus a HUMAN row. Human accuracy on each task
# uses all participants who attempted that task: per-participant accuracy
# averaged over participants, symmetric with the per-model LLM rows.
_hh_pivot = (
    avg_t0.pivot_table(index="model_short", columns="game", values="accuracy") * 100
)
_hh_mean_acc = _hh_pivot.mean(axis=1)
_hh_model_order = sorted(
    _hh_mean_acc.index, key=lambda m: (_fam_key(m), -_hh_mean_acc[m])
)
_hh_game_order = _hh_pivot.mean(axis=0).sort_values(ascending=False).index.tolist()
_hh_pivot = _hh_pivot.loc[_hh_model_order, _hh_game_order]

_hum_all = load_human_trials()
_hum_pp = _hum_all.groupby(["participant", "game"])["is_correct"].mean().reset_index()
_hum_task = _hum_pp.groupby("game")["is_correct"].mean() * 100
_human_row = _hum_task.reindex(_hh_game_order)  # align to LLM column (game) order

_hh_pivot = _rename_games(_hh_pivot)
_human_row.index = [GAME_LABELS.get(g, g) for g in _hh_game_order]

_hh_pivot["Mean"] = _hh_pivot.mean(axis=1)
_llm_mean = _hh_pivot.mean(axis=0)
_human_full = _human_row.reindex(_hh_pivot.columns[:-1])
_human_full["Mean"] = _human_row.mean()
_human_label = "Human"
_hh_pivot.loc["Mean"] = _llm_mean
_hh_pivot.loc[_human_label] = _human_full
# Human as the first (top) row, then models by family, then the LLM Mean row
_hh_pivot = _hh_pivot.reindex([_human_label] + list(_hh_model_order) + ["Mean"])

fig, ax = plt.subplots(figsize=(15, 10.5))
sns.heatmap(
    _hh_pivot,
    annot=True,
    fmt=".1f",
    cmap=_cmap_acc,
    vmin=0,
    vmax=100,
    linewidths=0.3,
    linecolor="white",
    ax=ax,
    cbar_kws={"label": "Accuracy (%)", "shrink": 0.8},
    annot_kws={"size": FONT["annot"] - 2},
)
for lbl in ax.get_xticklabels():
    if lbl.get_text() == "Mean":
        lbl.set_weight("bold")
for lbl in ax.get_yticklabels():
    if lbl.get_text() in ("Mean", _human_label):
        lbl.set_weight("bold")
_models_hh = [m for m in _hh_pivot.index if m not in ("Mean", _human_label)]
_n_models_hh = len(_models_hh)
_prev_fam = None
for _i, _m in enumerate(_models_hh):
    _fam = 0 if _m.startswith("claude") else (1 if _m.startswith("gemini") else 2)
    if _prev_fam is not None and _fam != _prev_fam:
        ax.axhline(y=_i + 1, color="black", linewidth=1.5)  # +1: Human occupies row 0
    _prev_fam = _fam
ax.axhline(y=1, color="black", linewidth=1.5)  # Human | models
ax.axhline(y=_n_models_hh + 1, color="black", linewidth=1.5)  # models | Mean
ax.axvline(x=len(_hh_pivot.columns) - 1, color="black", linewidth=1.5)
ax.set_ylabel("")
ax.set_xlabel("")
fig.tight_layout()
fig.savefig(OUT / "fig1_t0_accuracy_heatmap_human.pdf", bbox_inches="tight")
plt.close(fig)
print("fig1_t0_human")

# ═══ Figure fig:bubble — fig9_t0_bubble_chart.pdf ═══
_t0_ms = (
    avg_t0.groupby("model_short", observed=True)
    .agg(
        accuracy=("accuracy", "mean"),
        cost_per_game=("cost_per_game", "mean"),
        tokens_per_game=("total_tokens", "mean"),
    )
    .reset_index()
)
_t0_ms = _t0_ms.sort_values(
    "model_short", key=lambda s: s.map(lambda m: sort_by_family([m])[0])
)
fig, ax = plt.subplots(figsize=(16, 12))
_t0_ss = 1000 / _t0_ms["tokens_per_game"].max()
for _, row in _t0_ms.iterrows():
    ax.scatter(
        row["cost_per_game"],
        row["accuracy"],
        s=row["tokens_per_game"] * _t0_ss,
        color=MODEL_COLORS.get(row["model_short"], "#888"),
        alpha=0.95,
        edgecolors="white",
        linewidth=0.5,
        zorder=3,
    )
    bubble_s = row["tokens_per_game"] * _t0_ss
    radius_pt = np.sqrt(bubble_s) / 2
    ax.annotate(
        MODEL_ABBREV.get(row["model_short"], row["model_short"]),
        (row["cost_per_game"], row["accuracy"]),
        fontsize=14,
        ha="center",
        va="bottom",
        xytext=(0, radius_pt + 4),
        textcoords="offset points",
    )
# Pareto frontier
_t0_pareto = _t0_ms.sort_values("cost_per_game").copy()
_t0_front = []
_t0_best_acc = -1
for _, row in _t0_pareto.iterrows():
    if row["accuracy"] > _t0_best_acc:
        _t0_front.append(row)
        _t0_best_acc = row["accuracy"]
_t0_front = pd.DataFrame(_t0_front)
_t0_front_x = list(_t0_front["cost_per_game"].values)
_t0_front_y = list(_t0_front["accuracy"].values)
_t0_gemini_pro_cost = _t0_ms.loc[
    _t0_ms["model_short"] == "gemini-3.1-pro", "cost_per_game"
].values
if len(_t0_gemini_pro_cost):
    _t0_front_x.append(_t0_gemini_pro_cost[0])
    _t0_front_y.append(_t0_front_y[-1])
ax.plot(
    _t0_front_x,
    _t0_front_y,
    color="gray",
    linewidth=1.5,
    linestyle="--",
    alpha=0.6,
    zorder=2,
    label="Pareto frontier",
)

ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
ax.set_xlabel("Avg per-task cost ($)")
ax.set_ylabel("Accuracy")
ax.grid(alpha=0.3)
from matplotlib.lines import Line2D

_t0_token_handles = []
for t_val in [10000, 20000, 40000]:
    _t0_token_handles.append(
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="gray",
            alpha=0.4,
            markersize=np.sqrt(t_val * _t0_ss),
            label=f"{t_val // 1000}k",
        )
    )
leg_tokens = ax.legend(
    handles=_t0_token_handles,
    title="Tokens/task",
    ncol=1,
    fontsize=FONT["legend"],
    title_fontsize=FONT["legend_title"],
    loc="upper left",
    bbox_to_anchor=(1.01, 1.0),
    framealpha=0.9,
    borderpad=1.0,
    handletextpad=1.0,
    labelspacing=1.0,
)
ax.add_artist(leg_tokens)
leg_models = model_abbrev_legend(
    ax,
    ncol=4,
    fontsize=FONT["legend"],
    loc="upper center",
    bbox_to_anchor=(0.5, -0.09),
    framealpha=0.9,
)
fig.savefig(
    OUT / "fig9_t0_bubble_chart.pdf",
    bbox_extra_artists=[leg_tokens, leg_models],
    bbox_inches="tight",
)
plt.close(fig)
print("fig9_t0")

# ═══ Figure fig:net_gain — fig_t0_net_gain_avg.pdf ═══
_t0_ng = avg_t0.copy()
_t0_ng["net_gain"] = (
    _t0_ng["accuracy"] * _t0_ng["n_puzzles"] * 0.25 - _t0_ng["cost_per_game"]
)
_t0_net_mean = _t0_ng.groupby("model_short", observed=True)["net_gain"].mean()
_t0_net_order = sorted(
    _t0_net_mean.index, key=lambda m: (_fam_key(m), -_t0_net_mean[m])
)
_t0_net_model = _t0_net_mean.reindex(_t0_net_order)

# Optimal participant
_t0_ng_per_game = _t0_ng.groupby(["model_short", "game"], observed=True)[
    "net_gain"
].mean()
_t0_best_per_game = _t0_ng_per_game.groupby("game").max()
_t0_smart_ng = _t0_best_per_game.mean()

labels = list(_t0_net_model.index) + ["Optimal participant"]
values = list(_t0_net_model.values) + [_t0_smart_ng]

fig, ax = plt.subplots(figsize=(10, 8))
y = np.arange(len(labels))
bar_colors = [MODEL_COLORS.get(m, "#888888") for m in _t0_net_model.index] + ["#E03030"]
ax.barh(y, values, color=bar_colors, edgecolor="white", linewidth=0.5)
ax.set_yticks(y)
ax.set_yticklabels(labels, fontsize=9)
for lbl in ax.get_yticklabels():
    if lbl.get_text() == "Optimal participant":
        lbl.set_weight("bold")
        lbl.set_color("#E03030")
ax.axvline(0, color="black", lw=0.8)
ax.set_xlabel("Net gain per task ($)")
ax.grid(axis="x", alpha=0.3)
for i, val in enumerate(values):
    offset = 0.05 if val >= 0 else -0.05
    ha = "left" if val >= 0 else "right"
    fw = "bold" if i >= len(values) - 1 else "normal"
    ax.text(
        val + offset, i, f"${val:.2f}", va="center", ha=ha, fontsize=8, fontweight=fw
    )
xmin, xmax = ax.get_xlim()
margin = (xmax - xmin) * 0.12
ax.set_xlim(xmin - margin, xmax + margin)
fig.tight_layout()
fig.savefig(OUT / "fig_t0_net_gain_avg.pdf", bbox_inches="tight")
plt.close(fig)
print("net_gain_t0")

# ═══ Figures fig:incentive_heatmaps_standard / _human — fig_appendix_incentive_heatmap_{standard,human}.pdf ═══
acc_pivot = grouped_df.pivot_table(
    index="model_short", columns=["treatment", "game"], values="accuracy"
)
# Shared colorbar normalisation across both files for visual comparability.
# Same YlGnBu palette as the accuracy heatmaps: light (negative) -> dark blue (positive).
norm = matplotlib.colors.Normalize(vmin=-30, vmax=30)
cmap = _cmap_acc

for filename, title, t_high, t_low in [
    (
        "fig_appendix_incentive_heatmap_standard.pdf",
        "Standard Persona",
        "T2: Std Inc",
        "T1: Std No Inc",
    ),
    (
        "fig_appendix_incentive_heatmap_human.pdf",
        "Human Persona",
        "T4: Hum Inc",
        "T3: Hum No Inc",
    ),
]:
    fig, ax = plt.subplots(figsize=(15, 11))
    delta = (acc_pivot[t_high] - acc_pivot[t_low]) * 100
    # Order within families by this panel's mean incentive (highest at top)
    _panel_mean = delta.mean(axis=1)
    _panel_order = sorted(
        _panel_mean.index, key=lambda m: (_fam_key(m), -_panel_mean[m])
    )
    delta = delta.loc[
        _panel_order,
        [g for g in game_order_h if g in delta.columns],
    ]
    delta = _rename_games(delta)
    delta["Mean"] = delta.mean(axis=1)
    delta.loc["Mean"] = delta.mean(axis=0)
    sns.heatmap(
        delta,
        annot=True,
        fmt="+.1f",
        cmap=cmap,
        norm=norm,
        linewidths=0.5,
        ax=ax,
        cbar_kws={"label": "Δ Accuracy (pp)", "shrink": 0.8},
        annot_kws={"size": FONT["annot"] - 2},
    )
    for lbl in ax.get_xticklabels():
        if lbl.get_text() == "Mean":
            lbl.set_weight("bold")
    for lbl in ax.get_yticklabels():
        if lbl.get_text() == "Mean":
            lbl.set_weight("bold")
    # Family separators
    _models_inc = list(delta.index)
    _prev_fam = None
    for _i, _m in enumerate(_models_inc):
        if _m == "Mean":
            continue
        _fam = 0 if _m.startswith("claude") else (1 if _m.startswith("gemini") else 2)
        if _prev_fam is not None and _fam != _prev_fam:
            ax.axhline(y=_i, color="black", linewidth=1.5)
        _prev_fam = _fam
    ax.axhline(y=len(_models_inc) - 1, color="black", linewidth=1.5)
    ax.axvline(x=len(delta.columns) - 1, color="black", linewidth=1.5)
    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=90)
    fig.tight_layout()
    fig.savefig(OUT / filename, bbox_inches="tight")
    plt.close(fig)
print("fig5 (split)")

# ═══ Figures fig:heatmap_t1 ... fig:heatmap_t4 — fig_appendix_heatmap_t{1,2,3,4}.pdf ═══
for treatment in TREATMENT_ORDER[1:]:
    t_data = grouped_df[grouped_df["treatment"] == treatment]
    pivot = (
        t_data.pivot_table(index="model_short", columns="game", values="accuracy") * 100
    )
    _t_mean_acc = pivot.mean(axis=1)
    _t_model_order = sorted(
        _t_mean_acc.index, key=lambda m: (_fam_key(m), -_t_mean_acc[m])
    )
    pivot = pivot.loc[_t_model_order, game_order_h]
    pivot = _rename_games(pivot)
    pivot["Mean"] = pivot.mean(axis=1)
    pivot.loc["Mean"] = pivot.mean(axis=0)
    fig, ax = plt.subplots(figsize=(15, 10))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".1f",
        cmap=_cmap_acc,
        vmin=0,
        vmax=100,
        linewidths=0.3,
        linecolor="white",
        ax=ax,
        cbar_kws={"label": "Accuracy (%)", "shrink": 0.8},
        annot_kws={"size": FONT["annot"] - 2},
    )
    for lbl in ax.get_xticklabels():
        if lbl.get_text() == "Mean":
            lbl.set_weight("bold")
    for lbl in ax.get_yticklabels():
        if lbl.get_text() == "Mean":
            lbl.set_weight("bold")
    # Family separators
    _models_app = list(pivot.index)
    _prev_fam = None
    for _i, _m in enumerate(_models_app):
        if _m == "Mean":
            continue
        _fam = 0 if _m.startswith("claude") else (1 if _m.startswith("gemini") else 2)
        if _prev_fam is not None and _fam != _prev_fam:
            ax.axhline(y=_i, color="black", linewidth=1.5)
        _prev_fam = _fam
    ax.axhline(y=len(_models_app) - 1, color="black", linewidth=1.5)
    ax.axvline(x=len(pivot.columns) - 1, color="black", linewidth=1.5)
    ax.set_ylabel("")
    ax.set_xlabel("")
    fig.tight_layout()
    tag = treatment.split(":")[0].strip().lower()
    fig.savefig(OUT / f"fig_appendix_heatmap_{tag}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"appendix_{tag}")
