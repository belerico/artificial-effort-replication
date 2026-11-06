#!/usr/bin/env python3
"""Compute the numbers quoted in the text of the paper.

Each line shows where the number appears, what it is, the value computed from
the data and the value printed in the paper. LLM numbers use treatment T0
(control) unless stated otherwise. Writes output/numbers_in_text.txt. Run from
repo root:
    uv run python analysis/numbers_in_text.py
"""

import pandas as pd

from common import ROOT, HUMAN_DB, connect_ro, load_llm_data
from table_llm_vs_human import fit, marginal_effects

OUT = ROOT / "output" / "numbers_in_text.txt"
RATE = 0.25  # payment per correct trial used for the net gain (USD)

# Tiers named in Result 2 ("top-tier" vs "mid-tier"), per provider.
TOP_TIER = {
    "Anthropic": ["claude-opus-4.5", "claude-opus-4.6"],
    "Google": ["gemini-2.5-pro", "gemini-3.1-pro"],
    "OpenAI": ["gpt-5", "gpt-5.1", "gpt-5.2", "gpt-5.4"],
}
MID_TIER = {
    "Anthropic": ["claude-sonnet-3.7", "claude-sonnet-4", "claude-sonnet-4.5", "claude-sonnet-4.6"],
    "Google": ["gemini-2.5-flash", "gemini-3-flash"],
    "OpenAI": ["gpt-5-mini", "gpt-5.4-mini"],
}

lines = []


def section(title):
    lines.append(f"\n== {title} ==")


def show(what, value, paper):
    lines.append(f"  {what:<70} {value:>12}   paper: {paper}")


def pct(x):
    return f"{100 * x:.1f}%"


def human_sample():
    """Participants per study day and participant x task observations."""
    con = connect_ro(HUMAN_DB)
    runs = pd.read_sql_query(
        "SELECT e.day, r.participant_id FROM runs r JOIN experiments e ON e.id = r.experiment_id",
        con,
    )
    con.close()
    day1 = set(runs.loc[runs["day"] == 1, "participant_id"])
    day2 = set(runs.loc[runs["day"] == 2, "participant_id"])
    return day1, day2, len(runs)


def main():
    _, g = load_llm_data()
    t0 = g[g["experiment"] == "t0-control"]
    acc_m = t0.groupby("model_short")["accuracy"].mean()  # per-model mean over tasks
    cost_m = t0.groupby("model_short")["cost_per_game"].mean()  # per-task cost C_m
    acc_task = t0.groupby("game")["accuracy"].mean()  # per-task mean over models
    acc_mt = t0.pivot_table(index="model_short", columns="game", values="accuracy")

    section("Sample sizes")
    show("LLMs tested", g["model_short"].nunique(), "23")
    show("tasks", g["game"].nunique(), "eight")
    show("trials per LLM run", int(g["n_puzzles"].median()), "20")

    section("Method, human benchmark (Experimental setup)")
    day1, day2, n_obs = human_sample()
    show("participants on Day 1", len(day1), "36")
    show("Day-1 participants who also attended Day 2", len(day1 & day2), "33")
    show("additional participants on Day 2", len(day2 - day1), "6")
    show("student-task observations", n_obs, "297")

    section("Result 1: Task difficulty (T0 accuracy, mean over the 23 LLMs)")
    paper_acc = {
        "add_numbers": "100%",
        "task_summation": "97.6%",
        "task_decoding": "94.1%",
        "task_sequences": "90.0%",
        "sudoku_game": "25.0%",
        "counting_zeros": "27.2%",
        "string_entry": "37.0%",
        "task_transcription": "77.4%",
    }
    for game, paper in paper_acc.items():
        show(f"LLM accuracy, {game}", pct(acc_task[game]), paper)
    me = marginal_effects(fit()).set_index("Task")
    paper_gap = {
        "Addition": "11.9 pp",
        "Sequence Completion": "15.3 pp",
        "Pair Summation": "7.6 pp, p=0.064",
        "Letter Decoding": "-1.5 pp, p=0.708",
        "Sudoku": "61 pp, p<0.001",
        "Counting Zeros": "60.6 pp, p<0.001",
        "String Entry": "55 pp, p<0.001",
        "Distorted Text": "16.5 pp, p<0.001",
    }
    for task, paper in paper_gap.items():
        r = me.loc[task]
        show(f"LLM - human, {task} (pp, p)", f"{r['Estimate']:.1f}, p={r['P']:.3f}", paper)

    section("Result 2: Performance across providers, tiers, and tasks")
    for m in ("claude-opus-4.5", "claude-opus-4.6", "gemini-3.1-pro", "gpt-5.4"):
        show(f"average accuracy, {m}", pct(acc_m[m]), "above 80%")
    for prov in TOP_TIER:
        gap = acc_m[TOP_TIER[prov]].max() - acc_m[MID_TIER[prov]].max()
        show(f"best top-tier - best mid-tier, {prov} (pp)", f"{100 * gap:.1f}", "between 4 and 14")
    for old, new, paper in (
        ("gemini-2.5-pro", "gemini-3.1-pro", "22"),
        ("gpt-5", "gpt-5.4", "21"),
        ("claude-sonnet-3.7", "claude-sonnet-4.5", "11"),
        ("claude-sonnet-4.5", "claude-sonnet-4.6", "slight regression"),
    ):
        show(f"{old} -> {new} (pp)", f"{100 * (acc_m[new] - acc_m[old]):+.1f}", paper)

    section("Result 3: Cost-accuracy trade-offs")
    for m in ("gpt-5.4", "gemini-3.1-pro"):
        show(f"accuracy and per-task cost C_m, {m}", f"{pct(acc_m[m])}, ${cost_m[m]:.3f}", "82.5%, < $0.25")
    show(
        "accuracy and per-task cost C_m, gemini-3.1-flash-lite",
        f"{pct(acc_m['gemini-3.1-flash-lite'])}, ${cost_m['gemini-3.1-flash-lite']:.3f}",
        "79%, $0.03",
    )
    for m in cost_m.sort_values().index[:5]:
        show(
            f"cheapest models: accuracy and C_m, {m}",
            f"{pct(acc_m[m])}, ${cost_m[m]:.3f}",
            "58-60% (Result 3); around 60%, C_m < $0.05 (Discussion)",
        )
    best = {}
    for game, paper in (
        ("counting_zeros", "Gemini 3.1 Pro, 85%"),
        ("sudoku_game", "GPT-5.2, 85%"),
        ("string_entry", "Gemini 3.1 Pro, 75%"),
    ):
        m = acc_mt[game].idxmax()
        best[game] = acc_mt[game].max()
        show(f"best model on {game}", f"{m}, {pct(best[game])}", paper)
    cherry = acc_mt.max(axis=0).mean()
    show("average accuracy, best model per task", pct(cherry), "93.1%")
    show("gain over the best single model (pp)", f"{100 * (cherry - acc_m.max()):.1f}", "11 pp")
    ng = t0.assign(net=t0["accuracy"] * t0["n_puzzles"] * RATE - t0["cost_per_game"])
    ng_m = ng.groupby("model_short")["net"].mean()
    show(f"lowest net gain G_m ({ng_m.idxmin()})", f"${ng_m.min():.2f}", "$2.66 (o3)")
    show(f"highest net gain G_m ({ng_m.idxmax()})", f"${ng_m.max():.2f}", "$3.92 (GPT-5.4)")

    section("Discussion and Conclusions")
    show(f"most expensive model C_m ({cost_m.idxmax()})", f"${cost_m.max():.3f}", "Claude Opus 4.5, below $0.40")

    section("Appendix: Verbal Monetary Incentives (mean over the 23 LLMs)")
    tr = g.groupby(["treatment", "model_short"], observed=True)["accuracy"].mean()
    tr = tr.groupby("treatment", observed=True).mean()
    for t, paper in zip(tr.index, ("68.5%", "68.1%", "68.6%", "68.6%", "68.6%")):
        show(f"accuracy, {t}", pct(tr[t]), paper)
    piv = g.pivot_table(index=["model_short", "game"], columns="experiment", values="accuracy")
    deltas = pd.concat(
        [
            piv["t2-standard-incentive"] - piv["t1-standard-no-incentive"],
            piv["t4-human-incentive"] - piv["t3-human-no-incentive"],
        ]
    )
    show("incentive deltas within +/-10 pp", pct((deltas.abs() <= 0.10 + 1e-9).mean()), "about 80%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines).lstrip() + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
