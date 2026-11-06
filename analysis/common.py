"""Paths, task labels and the human-data loader shared by the analysis scripts."""

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LLM_DB = ROOT / "data" / "results_llm.db"
HUMAN_DB = ROOT / "data" / "results_human.db"
FIG_DIR = ROOT / "output" / "figures"
TAB_DIR = ROOT / "output" / "tables"

GAME_LABELS = {
    "add_numbers": "Addition",
    "task_summation": "Pair Summation",
    "task_decoding": "Letter Decoding",
    "task_sequences": "Sequence Completion",
    "task_transcription": "Distorted Text",
    "string_entry": "String Entry",
    "counting_zeros": "Counting Zeros",
    "sudoku_game": "Sudoku",
}


def connect_ro(db):
    """Open an SQLite database read-only."""
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def load_human_trials():
    """Trial-level human data, one row per trial: participant, game, is_correct.

    Every participant who attempted a task is kept (both study days). A trial
    with no submitted answer (is_correct NULL) counts as incorrect.
    """
    con = connect_ro(HUMAN_DB)
    hum = pd.read_sql_query(
        "SELECT r.participant_id AS participant, r.game, p.is_correct "
        "FROM puzzles p JOIN runs r ON p.run_id = r.id",
        con,
    )
    con.close()
    hum["is_correct"] = hum["is_correct"].fillna(0).astype(int)
    return hum


# Experiment name -> (treatment label, persona, incentive)
TREATMENT_MAP = {
    "t0-control": ("T0: Control", "control", "none"),
    "t1-standard-no-incentive": ("T1: Std No Inc", "standard", "no"),
    "t2-standard-incentive": ("T2: Std Inc", "standard", "yes"),
    "t3-human-no-incentive": ("T3: Hum No Inc", "human", "no"),
    "t4-human-incentive": ("T4: Hum Inc", "human", "yes"),
}

TREATMENT_ORDER = [
    "T0: Control",
    "T1: Std No Inc",
    "T2: Std Inc",
    "T3: Hum No Inc",
    "T4: Hum Inc",
]

# USD per token (OpenRouter API, 23 March 2026; Table tab:LLMs).
PRICING = {
    "anthropic/claude-3.7-sonnet": {"input": 3e-6, "output": 15e-6},
    "anthropic/claude-haiku-4.5": {"input": 1e-6, "output": 5e-6},
    "anthropic/claude-opus-4.5": {"input": 5e-6, "output": 25e-6},
    "anthropic/claude-opus-4.6": {"input": 5e-6, "output": 25e-6},
    "anthropic/claude-sonnet-4": {"input": 3e-6, "output": 15e-6},
    "anthropic/claude-sonnet-4.5": {"input": 3e-6, "output": 15e-6},
    "anthropic/claude-sonnet-4.6": {"input": 3e-6, "output": 15e-6},
    "google/gemini-2.5-flash": {"input": 0.3e-6, "output": 2.5e-6},
    "google/gemini-2.5-pro": {"input": 1.25e-6, "output": 10e-6},
    "google/gemini-3-flash-preview": {"input": 0.5e-6, "output": 3e-6},
    "google/gemini-3.1-pro-preview": {"input": 2e-6, "output": 12e-6},
    "openai/gpt-5": {"input": 1.25e-6, "output": 10e-6},
    "openai/gpt-5-mini": {"input": 0.25e-6, "output": 2e-6},
    "openai/gpt-5.1": {"input": 1.25e-6, "output": 10e-6},
    "openai/gpt-5.2": {"input": 1.75e-6, "output": 14e-6},
    "openai/gpt-5.4": {"input": 2.5e-6, "output": 15e-6},
    "openai/o3": {"input": 2e-6, "output": 8e-6},
    "openai/o4-mini": {"input": 1.1e-6, "output": 4.4e-6},
    "openai/o4-mini-high": {"input": 1.1e-6, "output": 4.4e-6},
    "google/gemini-2.5-flash-lite": {"input": 0.1e-6, "output": 0.4e-6},
    "google/gemini-3.1-flash-lite-preview": {"input": 0.25e-6, "output": 1.5e-6},
    "openai/gpt-5.4-mini": {"input": 0.75e-6, "output": 4.5e-6},
    "openai/gpt-5.4-nano": {"input": 0.2e-6, "output": 1.25e-6},
}


def _clean_model_name(s):
    """Uniform display names: claude-3.7-sonnet → claude-sonnet-3.7, remove -preview."""
    s = s.replace("claude-3.7-sonnet", "claude-sonnet-3.7")
    s = s.replace("-preview", "")
    return s


def load_llm_data():
    """LLM data for treatments T0-T4: trial-level df and run-level grouped_df.

    A timed-out trial (response TIMEOUT) is scored incorrect and charged the full
    budget: 120 s, 2,048 completion tokens, and the model x task average prompt.
    grouped_df has one row per (experiment, model, game): accuracy, tokens and
    cost_per_game (USD for the 20 trials of the run).
    """
    conn = connect_ro(LLM_DB)
    df = pd.read_sql_query(
        """
        SELECT e.name AS experiment, r.model, r.game,
               p.iteration, p.is_correct, p.response_time,
               p.prompt_tokens, p.completion_tokens, p.total_tokens, p.response
        FROM puzzles p JOIN runs r ON p.run_id = r.id JOIN experiments e ON r.experiment_id = e.id
        WHERE r.status = 'completed'
        ORDER BY e.name, r.model, r.game, p.iteration
    """,
        conn,
    )
    conn.close()

    # Drop experiments not in our map (e.g. ad-hoc test runs)
    df = df[df["experiment"].isin(TREATMENT_MAP)].copy()

    df["treatment"] = df["experiment"].map(lambda x: TREATMENT_MAP[x][0])
    df["persona"] = df["experiment"].map(lambda x: TREATMENT_MAP[x][1])
    df["incentive"] = df["experiment"].map(lambda x: TREATMENT_MAP[x][2])

    df["model_short"] = df["model"].str.rsplit("/", n=1).str[-1].map(_clean_model_name)
    df["is_correct"] = df["is_correct"].fillna(0).astype(int)
    df["timed_out"] = df["response"] == "TIMEOUT"
    df.loc[df["timed_out"], "response_time"] = 120
    df.loc[df["timed_out"], "completion_tokens"] = 2048
    # Impute prompt_tokens for timeouts using the average for that model+game
    _timeout_mask = df["timed_out"]
    if _timeout_mask.any():
        _avg_prompt = df[~_timeout_mask].groupby(["model", "game"])["prompt_tokens"].mean()
        for idx in df[_timeout_mask].index:
            key = (df.loc[idx, "model"], df.loc[idx, "game"])
            if key in _avg_prompt.index:
                df.loc[idx, "prompt_tokens"] = round(_avg_prompt[key])
        df.loc[_timeout_mask, "total_tokens"] = (
            df.loc[_timeout_mask, "prompt_tokens"]
            + df.loc[_timeout_mask, "completion_tokens"]
        )
    df["treatment"] = pd.Categorical(
        df["treatment"], categories=TREATMENT_ORDER, ordered=True
    )

    _zero = {"input": 0, "output": 0}
    df["cost_total"] = (
        df["model"].map(lambda m: PRICING.get(m, _zero)["input"]) * df["prompt_tokens"]
        + df["model"].map(lambda m: PRICING.get(m, _zero)["output"])
        * df["completion_tokens"]
    )

    grouped_df = (
        df.groupby(["experiment", "model", "game"], observed=True)
        .agg(
            accuracy=("is_correct", "mean"),
            total_completion_tokens=("completion_tokens", "sum"),
            total_tokens=("total_tokens", "sum"),
            total_time=("response_time", "sum"),
            cost_per_game=("cost_total", "sum"),
            n_puzzles=("is_correct", "count"),
        )
        .reset_index()
    )
    grouped_df["model_short"] = (
        grouped_df["model"].str.rsplit("/", n=1).str[-1].map(_clean_model_name)
    )
    grouped_df["treatment"] = grouped_df["experiment"].map(lambda x: TREATMENT_MAP[x][0])
    grouped_df["treatment"] = pd.Categorical(
        grouped_df["treatment"], categories=TREATMENT_ORDER, ordered=True
    )
    grouped_df["persona"] = grouped_df["experiment"].map(lambda x: TREATMENT_MAP[x][1])
    grouped_df["incentive"] = grouped_df["experiment"].map(lambda x: TREATMENT_MAP[x][2])
    return df, grouped_df
