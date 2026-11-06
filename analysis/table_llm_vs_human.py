#!/usr/bin/env python3
"""Estimate the LLM-vs-human task-difficulty LPM (Tables tab:lm_llm_hum and
tab:avg_llm_hum, Appendix "Comparing LLM and Humans on Tasks").

Model (accuracy in percentage points, one row per agent x task):

    acc_{a,t} = b0 + Task'b + LLM*g + (Task x LLM)'d + e

    - LLM agents: per-model T0 (t0-control) accuracy, one value per (model, task).
    - Human agents: per-participant accuracy, one value per (participant, task),
      over every participant who attempted the task.
    - Reference task = Addition; LLM = 1 for models, 0 for humans.

tab:lm_llm_hum = the full coefficient table.
tab:avg_llm_hum = the per-task average marginal effect of LLM, i.e. the linear
combination (LLM + Task_t x LLM), tested with res.t_test.

Writes output/tables/tab_lm_llm_hum.csv and tab_avg_llm_hum.csv. Run from repo root:
    uv run python analysis/table_llm_vs_human.py
"""

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from common import GAME_LABELS, LLM_DB, TAB_DIR, connect_ro, load_human_trials

# Row order used in the paper tables (Addition is the reference / intercept).
TASK_ORDER = [
    "add_numbers",
    "counting_zeros",
    "string_entry",
    "sudoku_game",
    "task_decoding",
    "task_sequences",
    "task_summation",
    "task_transcription",
]


def llm_t0_accuracy():
    """Per-(model, game) T0 accuracy in percentage points (one row per agent x task)."""
    con = connect_ro(LLM_DB)
    df = pd.read_sql_query(
        "SELECT r.model, r.game, p.is_correct "
        "FROM puzzles p JOIN runs r ON p.run_id=r.id "
        "JOIN experiments e ON r.experiment_id=e.id "
        "WHERE r.status='completed' AND e.name='t0-control'",
        con,
    )
    con.close()
    df["is_correct"] = pd.to_numeric(df["is_correct"], errors="coerce").fillna(0)
    g = df.groupby(["model", "game"])["is_correct"].mean().reset_index()
    g["acc"] = g["is_correct"] * 100.0
    g["LLM"] = 1
    return g[["game", "acc", "LLM"]]


def human_accuracy():
    """Per-(participant, game) accuracy in percentage points."""
    hum = load_human_trials()
    pp = hum.groupby(["participant", "game"])["is_correct"].mean().reset_index()
    pp["acc"] = pp["is_correct"] * 100.0
    pp["LLM"] = 0
    return pp[["game", "acc", "LLM"]], hum["participant"].nunique()


def fit():
    llm = llm_t0_accuracy()
    hum, _ = human_accuracy()
    data = pd.concat([llm, hum], ignore_index=True)
    data["game"] = pd.Categorical(data["game"], categories=TASK_ORDER, ordered=True)
    return smf.ols("acc ~ C(game, Treatment('add_numbers')) * LLM", data=data).fit()


def marginal_effects(res):
    """Per-task average marginal effect of LLM = LLM + (Task_t x LLM)."""
    names = res.params.index
    rows = []
    for t in TASK_ORDER:
        c = pd.Series(0.0, index=names)
        c["LLM"] = 1.0
        if t != "add_numbers":
            inter = f"C(game, Treatment('add_numbers'))[T.{t}]:LLM"
            c[inter] = 1.0
        tt = res.t_test(c.values)
        rows.append(
            {
                "Task": GAME_LABELS[t],
                "Estimate": float(np.ravel(tt.effect)[0]),
                "SE": float(np.ravel(tt.sd)[0]),
                "Stat": float(np.ravel(tt.tvalue)[0]),
                "P": float(np.ravel(tt.pvalue)[0]),
            }
        )
    return pd.DataFrame(rows)


def _term_label(name):
    if name == "Intercept":
        return "Intercept"
    if name == "LLM":
        return "LLM"
    is_inter = name.endswith(":LLM")
    base = name[: -len(":LLM")] if is_inter else name
    for t in TASK_ORDER[1:]:
        if base.endswith(f"[T.{t}]"):
            lab = f"Task: {GAME_LABELS[t]}"
            return f"{lab} x LLM" if is_inter else lab
    return name


def coef_table(res):
    """Full coefficient table (tab:lm_llm_hum) in the paper's row order."""
    order = (
        ["Intercept"]
        + [f"C(game, Treatment('add_numbers'))[T.{t}]" for t in TASK_ORDER[1:]]
        + ["LLM"]
        + [f"C(game, Treatment('add_numbers'))[T.{t}]:LLM" for t in TASK_ORDER[1:]]
    )
    rows = []
    for nm in order:
        rows.append(
            {
                "Term": _term_label(nm),
                "Estimate": res.params[nm],
                "SE": res.bse[nm],
                "Stat": res.tvalues[nm],
                "P": res.pvalues[nm],
            }
        )
    return pd.DataFrame(rows)


def _print(table, label_col, width):
    for _, r in table.iterrows():
        print(
            f"  {r[label_col]:<{width}} {r['Estimate']:7.1f} {r['SE']:6.1f} "
            f"{r['Stat']:7.1f} {r['P']:8.3f}"
        )


def main():
    res = fit()
    _, n_hum = human_accuracy()
    print(f"humans={n_hum},  N obs={int(res.nobs)},  R^2={res.rsquared:.3f}")
    TAB_DIR.mkdir(parents=True, exist_ok=True)

    coef = coef_table(res)
    coef.to_csv(TAB_DIR / "tab_lm_llm_hum.csv", index=False)
    print("-- tab:lm_llm_hum  (full coefficients) --")
    _print(coef, "Term", 30)

    me = marginal_effects(res)
    me.to_csv(TAB_DIR / "tab_avg_llm_hum.csv", index=False)
    print("-- tab:avg_llm_hum  (per-task marginal effect of LLM) --")
    _print(me, "Task", 26)


if __name__ == "__main__":
    main()
