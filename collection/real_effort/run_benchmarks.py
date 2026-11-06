#!/usr/bin/env python3
"""Run LLM benchmarks on puzzle games — calls OpenRouter directly (no botex/oTree).

Usage:
    uv run python run_benchmarks.py
    uv run python run_benchmarks.py --games add_numbers counting_zeros
    uv run python run_benchmarks.py --models openrouter/openai/gpt-4o-mini
    uv run python run_benchmarks.py --resume my_experiment
"""

import argparse
import asyncio
import csv
import importlib
import json
import os
import random
import re
import signal
import sqlite3
import sys
import time
import traceback
from base64 import b64encode
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from openai import APITimeoutError, AsyncOpenAI

from config import load_benchmark_config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPORT_DIR = SCRIPT_DIR / "reports"
RESULTS_DB = REPORT_DIR / "results_orig.db"
STATE_FILE = "experiment.json"

# Default benchmark config. Separate from config/otree_config.yaml (which the
# oTree apps read) so benchmark settings can diverge without affecting oTree.
DEFAULT_CONFIG = SCRIPT_DIR / "config" / "benchmark_config_llm.yaml"

DEFAULT_MODEL = "openrouter/google/gemini-3-flash-preview"

# Game name → puzzle module import path
GAME_MODULES = {
    "sudoku_game": "sudoku_game.sudoku_puzzle",
    "add_numbers": "add_numbers.task_addition",
    "counting_zeros": "counting_zeros.counting_zeros",
    "task_decoding": "task_decoding.task_decoding",
    "task_summation": "task_summation.task_summation",
    "task_transcription": "task_transcription.task_transcription",
    "task_sequences": None,  # CSV-based, no puzzle module
    "string_entry": "string_entry.string_entry",
}

ALL_GAMES = list(GAME_MODULES.keys())

_interrupted = False

# ---------------------------------------------------------------------------
# LLM prompts per game
# ---------------------------------------------------------------------------

# ── Treatment 0: No Human Bias & No Monetary Incentive ──
SYSTEM_PROMPT_CONTROL = (
    "You will be presented with a series of puzzles or tasks — these may involve images, text, "
    "or both. Your goal is to solve each task as accurately as possible.\n\n"
    "Instructions:\n"
    "- Read and examine the task carefully.\n"
    "- Follow the exact answer format specified in each task.\n"
    "- The answer must be formatted exactly as: Answer: <answer_format>"
)

# ── Treatment 1: No Human Bias & No Monetary Incentive ──
SYSTEM_PROMPT_EXPLICIT_NO_INCENTIVE = (
    "You will be presented with a series of puzzles or tasks — these may involve images, text, "
    "or both. Your goal is to solve each task as accurately as possible.\n\n"
    "There is no monetary compensation or bonus associated with your performance on these tasks.\n\n"
    "Instructions:\n"
    "- Read and examine the task carefully.\n"
    "- Follow the exact answer format specified in each task.\n"
    "- The answer must be formatted exactly as: Answer: <answer_format>"
)

# ── Treatment 2: No Human Bias & Monetary Incentive ──
SYSTEM_PROMPT_INCENTIVE = (
    "You will be presented with a series of puzzles or tasks — these may involve images, text, "
    "or both. Your goal is to solve each task as accurately as possible.\n\n"
    "You will be compensated for each correct answer: {incentive_text}\n\n"
    "Instructions:\n"
    "- Read and examine the task carefully.\n"
    "- Follow the exact answer format specified in each task.\n"
    "- The answer must be formatted exactly as: Answer: <answer_format>"
)

# ── Treatment 3: Human Bias & No Monetary Incentive ──
SYSTEM_PROMPT_HUMAN_EXPLICIT_NO_INCENTIVE = (
    "You are a human participant taking part in an academic research experiment on cognitive "
    "task performance.\n\n"
    "You will be presented with a series of puzzles or tasks — these may involve images, text, "
    "or both. Your goal is to solve each task as accurately as possible.\n\n"
    "There is no monetary compensation or bonus associated with your performance on these tasks.\n\n"
    "Instructions:\n"
    "- Read and examine the task carefully.\n"
    "- Follow the exact answer format specified in each task.\n"
    "- The answer must be formatted exactly as: Answer: <answer_format>"
)

# ── Treatment 4: Human Bias & Monetary Incentive ──
SYSTEM_PROMPT_HUMAN_INCENTIVE = (
    "You are a human participant taking part in an academic research experiment on cognitive "
    "task performance.\n\n"
    "You will be presented with a series of puzzles or tasks — these may involve images, text, "
    "or both. Your goal is to solve each task as accurately as possible.\n\n"
    "You will be compensated for each correct answer: {incentive_text}\n\n"
    "Instructions:\n"
    "- Read and examine the task carefully.\n"
    "- Follow the exact answer format specified in each task.\n"
    "- The answer must be formatted exactly as: Answer: <answer_format>"
)

GAME_PROMPTS = {
    "sudoku_game": (
        "Solve this 6×6 Sudoku puzzle. Each row, column, and 2×3 box must contain "
        "the numbers 1-6 exactly once. The image shows the grid with some cells empty.\n\n"
        "Return only the missing numbers in reading order (left to right, top to bottom), "
        "separated by spaces.\n\n"
        "Your answer must be formatted as — Answer: 3 1 5 2 4 6"
    ),
    "add_numbers": (
        "The image shows an addition problem. Calculate the sum of all the numbers shown. "
        "Return only the final numeric result.\n\n"
        "Your answer must be formatted as — Answer: 247"
    ),
    "counting_zeros": (
        "The image shows a paragraph of 0s and 1s. Count the total number of zeros. "
        "Return only the count.\n\n"
        "Your answer must be formatted as — Answer: 67"
    ),
    "task_decoding": (
        "The image shows a lookup table mapping digits (0-9) to letters, and a coded word "
        "(sequence of digits) below it. Decode the word by replacing each digit with its "
        "corresponding letter from the table. Return only the decoded word.\n\n"
        "Your answer must be formatted as — Answer: HELLO"
    ),
    "task_summation": (
        "The image shows a grid of decimal numbers. Find exactly two numbers from the grid "
        "that sum to {target_sum}. Return only the two numbers, space-separated.\n\n"
        "Your answer must be formatted as — Answer: 3.7 6.3"
    ),
    "task_transcription": (
        "The image shows distorted text (letters and/or digits). "
        "Transcribe exactly what you see. Return only the transcribed text.\n\n"
        "Your answer must be formatted as — Answer: A3BK7"
    ),
    "task_sequences": (
        "What is the next number in this sequence?\n{question}\n\n"
        "Return only the next number.\n\n"
        "Your answer must be formatted as — Answer: 42"
    ),
    "string_entry": (
        "The image shows a string of special characters drawn from: / \\ ) ( _ < and space. "
        "Spaces are shown as the ␣ (open box) symbol. "
        "Transcribe the exact string, including any spaces.\n\n"
        "Your answer must be formatted as — Answer: /\\) <(_<)"
    ),
}

# Text-only prompts — used when --text-only is set.
# Replace "The image shows" with inline text references.
GAME_PROMPTS_TEXT = {
    "sudoku_game": (
        "Solve this 6×6 Sudoku puzzle. Each row, column, and 2×3 box must contain "
        "the numbers 1-6 exactly once. Dots (.) represent empty cells.\n\n"
        "Return only the missing numbers in reading order (left to right, top to bottom), "
        "separated by spaces.\n\n"
        "Your answer must be formatted as — Answer: 3 1 5 2 4 6\n\n"
        "Puzzle:\n{puzzle_text}"
    ),
    "add_numbers": (
        "Calculate the sum of all the numbers in the following addition problem. "
        "Return only the final numeric result.\n\n"
        "Your answer must be formatted as — Answer: 247\n\n"
        "{puzzle_text}"
    ),
    "counting_zeros": (
        "Below is a paragraph of 0s and 1s. Count the total number of zeros. "
        "Return only the count.\n\n"
        "Your answer must be formatted as — Answer: 67\n\n"
        "{puzzle_text}"
    ),
    "task_decoding": (
        "Below is a lookup table mapping digits (0-9) to letters, and a coded word "
        "(sequence of digits). Decode the word by replacing each digit with its "
        "corresponding letter from the table. Return only the decoded word.\n\n"
        "Your answer must be formatted as — Answer: HELLO\n\n"
        "{puzzle_text}"
    ),
    "task_summation": (
        "Below is a grid of decimal numbers. Find exactly two numbers from the grid "
        "that sum to {target_sum}. Return only the two numbers, space-separated.\n\n"
        "Your answer must be formatted as — Answer: 3.7 6.3\n\n"
        "{puzzle_text}"
    ),
    "task_transcription": (
        "Below is a string of characters (letters and/or digits). "
        "Transcribe exactly what you see. Return only the transcribed text.\n\n"
        "Your answer must be formatted as — Answer: A3BK7\n\n"
        "{puzzle_text}"
    ),
    "task_sequences": (
        "What is the next number in this sequence?\n{question}\n\n"
        "Return only the next number.\n\n"
        "Your answer must be formatted as — Answer: 42"
    ),
    "string_entry": (
        "Below is a string of special characters drawn from: / \\ ) ( _ < and space. "
        "Spaces are shown as [SPACE]. "
        "Transcribe the exact string, replacing [SPACE] with an actual space.\n\n"
        "Your answer must be formatted as — Answer: /\\) <(_<)\n\n"
        "{puzzle_text}"
    ),
}


# ---------------------------------------------------------------------------
# Puzzle module helpers
# ---------------------------------------------------------------------------


def _load_puzzle_module(game: str):
    """Import and return the puzzle module for a game."""
    mod_path = GAME_MODULES[game]
    if mod_path is None:
        return None
    return importlib.import_module(mod_path)


def _get_gen_params(game: str, game_cfg: dict) -> dict:
    """Map YAML game config to generate_puzzle_fields() kwargs."""
    if game == "sudoku_game":
        return {"difficulty": game_cfg.get("difficulty", 0.2)}
    elif game == "add_numbers":
        md = int(game_cfg.get("max_digits", 2))
        return {
            "num_addends": game_cfg.get("num_addends", 5),
            "min_num": 10 ** (md - 1) if md > 1 else 1,
            "max_num": 10**md - 1,
        }
    elif game == "counting_zeros":
        return {
            "rows": game_cfg.get("rows", 10),
            "cols": game_cfg.get("cols", 15),
            "min_zeros": game_cfg.get("min_zeros", 55),
            "max_zeros": game_cfg.get("max_zeros", 85),
        }
    elif game == "task_decoding":
        return {"word_length": game_cfg.get("word_length", 5)}
    elif game == "task_summation":
        return {
            "grid_size": game_cfg.get("grid_size", 3),
            "target_sum": game_cfg.get("target_sum", 10.0),
        }
    elif game == "task_transcription":
        return {"length": game_cfg.get("length", 3)}
    elif game == "task_sequences":
        return {}
    elif game == "string_entry":
        return {"length": game_cfg.get("length", 9)}
    else:
        raise ValueError(f"Unknown game: {game}")


def _get_prompt(
    game: str,
    game_cfg: dict,
    puzzle_text: str | None = None,
    text_only: bool = False,
) -> str:
    """Build the user prompt for a given game, filling in game-specific placeholders."""
    template = (GAME_PROMPTS_TEXT if text_only else GAME_PROMPTS)[game]
    fmt = {}
    if game == "task_summation":
        fmt["target_sum"] = game_cfg.get("target_sum", 10.0)
    elif game == "task_sequences":
        fmt["question"] = puzzle_text or ""
    if text_only:
        fmt["puzzle_text"] = puzzle_text or ""
    return template.format(**fmt) if fmt else template


def _image_to_base64(image) -> str:
    """Convert PIL Image to base64 string."""
    buf = BytesIO()
    image.save(buf, "PNG")
    return b64encode(buf.getvalue()).decode("ascii")


def _load_sequences() -> list[dict]:
    """Load task_sequences questions from CSV."""
    csv_path = SCRIPT_DIR / "task_sequences" / "sequences.csv"
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


_ANSWER_RE = re.compile(r"Answer:\s*(.+)", re.IGNORECASE)


def _extract_answer(raw: str) -> str:
    """Extract the answer from the model's response.

    Searches from the end of the response for the last 'Answer: <value>' line.
    Falls back to the raw response if no match is found.
    """
    # Search all matches, take the last one (closest to the end)
    matches = list(_ANSWER_RE.finditer(raw))
    if matches:
        return matches[-1].group(1).strip()
    return raw.strip()


def _validate_answer(
    game: str, response: str, puzzle: SimpleNamespace, game_cfg: dict, puzzle_mod
) -> bool:
    """Validate an answer using the game's is_correct function."""
    if game == "task_summation":
        return puzzle_mod.is_correct(
            response, puzzle, target_sum=game_cfg.get("target_sum", 10.0)
        )
    elif game == "task_sequences":
        try:
            return int(response) == int(puzzle.solution)
        except (ValueError, TypeError):
            return False
    else:
        return puzzle_mod.is_correct(response, puzzle)


# ---------------------------------------------------------------------------
# OpenRouter API
# ---------------------------------------------------------------------------


async def _async_openrouter_call(
    client: AsyncOpenAI,
    kwargs: dict,
    timeout: int | None,
) -> "ChatCompletion":
    """Make the API call, with optional hard wall-clock timeout.

    asyncio.wait_for cancels the coroutine on timeout, which cancels the
    underlying httpx request and closes the TCP connection.  OpenRouter sees
    the disconnect and stops generating (and charging).
    """
    coro = client.chat.completions.create(**kwargs)
    if timeout and timeout > 0:
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise APITimeoutError(request=None)
    return await coro


def call_openrouter(
    model: str,
    messages: list[dict],
    *,
    api_key: str,
    temperature: float | None = None,
    max_tokens: int = 2048,
    reasoning_effort: str | None = None,
    reasoning_max_tokens: int | None = None,
    top_p: float | None = None,
    timeout: int | None = None,
    provider: dict | None = None,
) -> tuple[str, str | None, dict, int | None]:
    """Call OpenRouter and return (answer_text, reasoning_content, token_usage_dict, reasoning_tokens).

    Raises APITimeoutError if the wall-clock timeout fires.
    Uses async client + asyncio.wait_for for a real wall-clock timeout that
    actually closes the connection (so OpenRouter stops generating/charging).
    """
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    kwargs = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if top_p is not None:
        kwargs["top_p"] = top_p

    # Build reasoning config: max_tokens (hard cap) takes priority over effort
    # (OpenRouter rejects both at once)
    #
    # Only OpenAI supports reasoning.effort natively.
    # All other providers (Anthropic, Google, Qwen, Kimi, Seed) need
    # reasoning.max_tokens — auto-convert effort → max_tokens for them.
    EFFORT_RATIO = {
        "none": 0.0,
        "minimal": 0.10,
        "low": 0.20,
        "medium": 0.50,
        "high": 0.80,
        "xhigh": 0.95,
    }
    # Providers that natively support reasoning.effort
    EFFORT_PROVIDERS = {"openai/"}

    reasoning_cfg = {}
    if reasoning_max_tokens is not None:
        reasoning_cfg["max_tokens"] = reasoning_max_tokens
    elif reasoning_effort:
        if reasoning_effort == "none":
            reasoning_cfg["enabled"] = False
        elif any(model.lower().startswith(p) for p in EFFORT_PROVIDERS):
            reasoning_cfg["effort"] = reasoning_effort
        else:
            # Convert effort to explicit max_tokens for all other providers
            ratio = EFFORT_RATIO.get(reasoning_effort, 0.50)
            reasoning_cfg["max_tokens"] = int(max_tokens * ratio)
    extra_body = {}
    if reasoning_cfg:
        extra_body["reasoning"] = reasoning_cfg
    if provider:
        extra_body["provider"] = provider
    if extra_body:
        kwargs["extra_body"] = extra_body

    print(
        f"    [API] model={model} max_tokens={max_tokens} reasoning={reasoning_cfg or 'none'}"
    )

    loop = asyncio.new_event_loop()
    try:
        response = loop.run_until_complete(
            _async_openrouter_call(client, kwargs, timeout)
        )
    finally:
        loop.run_until_complete(client.close())
        loop.close()

    msg = response.choices[0].message
    text = (msg.content or "").strip()

    # Reasoning content — OpenRouter returns it as message.reasoning (Chat API)
    # OpenAI SDK native models use message.reasoning_content (o1/o3)
    reasoning = getattr(msg, "reasoning", None) or getattr(
        msg, "reasoning_content", None
    )
    if isinstance(reasoning, str):
        reasoning = reasoning.strip() or None

    usage = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(response.usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(response.usage, "total_tokens", 0) or 0,
    }

    # Some providers report reasoning tokens in usage (e.g. completion_tokens_details)
    details = getattr(response.usage, "completion_tokens_details", None)
    reasoning_tokens = None
    if details:
        reasoning_tokens = getattr(details, "reasoning_tokens", None)

    return text, reasoning, usage, reasoning_tokens


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------


def run_game(
    game: str,
    model: str,
    api_key: str,
    *,
    repetitions: int = 1,
    game_cfg: dict | None = None,
    temperature: float | None = None,
    max_tokens: int = 2048,
    reasoning_effort: str | None = None,
    reasoning_max_tokens: int | None = None,
    top_p: float | None = None,
    puzzle_timeout: int = 0,
    system_prompt: str = SYSTEM_PROMPT_EXPLICIT_NO_INCENTIVE,
    provider: dict | None = None,
    enforce_reasoning_budget: bool = False,
    reasoning_budget_tolerance: int = 16,
    text_only: bool = False,
) -> dict:
    """Run all repetitions of a game for one model. Returns run result dict."""
    game_cfg = game_cfg or {}
    puzzle_mod = _load_puzzle_module(game)
    gen_params = _get_gen_params(game, game_cfg)
    sequences = _load_sequences() if game == "task_sequences" else None
    used_sequences: set[str] = set()

    # Compute effective reasoning budget for enforcement checks
    EFFORT_RATIO = {
        "none": 0.0,
        "minimal": 0.10,
        "low": 0.20,
        "medium": 0.50,
        "high": 0.80,
        "xhigh": 0.95,
    }
    if reasoning_max_tokens is not None:
        reasoning_budget = reasoning_max_tokens
    elif reasoning_effort and reasoning_effort != "none":
        reasoning_budget = int(max_tokens * EFFORT_RATIO.get(reasoning_effort, 0.50))
    else:
        reasoning_budget = None  # no budget to enforce

    puzzles_data: list[dict] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_total_tokens = 0
    num_correct = 0
    num_failed = 0
    num_errors = 0
    num_budget_exceeded = 0
    error_sample = ""
    start_time = time.monotonic()

    model_short = model.rsplit("/", 1)[-1]

    for i in range(repetitions):
        if _interrupted:
            break

        # Generate puzzle
        if game == "task_sequences":
            available = [q for q in sequences if q["question"] not in used_sequences]
            if not available:
                available = sequences
            chosen = random.choice(available)
            used_sequences.add(chosen["question"])
            puzzle = SimpleNamespace(
                text=chosen["question"], solution=chosen["solution"]
            )
        else:
            fields = puzzle_mod.generate_puzzle_fields(**gen_params)
            puzzle = SimpleNamespace(**fields)

        # Build prompt and messages
        if game == "task_sequences":
            # Always text-only
            user_prompt = _get_prompt(game, game_cfg, puzzle_text=puzzle.text)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        elif text_only:
            # Text-only mode: inline the text representation
            text_repr = puzzle_mod.render_text(puzzle)
            user_prompt = _get_prompt(
                game, game_cfg, puzzle_text=text_repr, text_only=True
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        else:
            # Image-based: render and encode
            user_prompt = _get_prompt(game, game_cfg, puzzle_text=puzzle.text)
            image = puzzle_mod.render_image(puzzle)
            b64 = _image_to_base64(image)
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                },
            ]

        # Call API
        t0 = time.monotonic()
        answer = "TIMEOUT"
        reasoning = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        reasoning_tokens = None
        timed_out = False

        try:
            answer, reasoning, usage, reasoning_tokens = call_openrouter(
                model,
                messages,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
                reasoning_max_tokens=reasoning_max_tokens,
                top_p=top_p,
                timeout=puzzle_timeout if puzzle_timeout > 0 else None,
                provider=provider,
            )
        except APITimeoutError:
            timed_out = True
            print(
                f"    [{i + 1}/{repetitions}] {model_short}/{game}: "
                f"TIMEOUT ({puzzle_timeout}s)",
            )
        except Exception as e:
            answer = f"ERROR: {type(e).__name__}: {e}"
            num_errors += 1
            if not error_sample:
                error_sample = answer
            print(
                f"    [{i + 1}/{repetitions}] {model_short}/{game}: "
                f"API error: {answer}",
                file=sys.stderr,
            )

        elapsed = round(time.monotonic() - t0, 2)

        # Extract answer from "Answer: <value>" format, then validate
        if timed_out or answer.startswith("ERROR:"):
            correct = False
        else:
            answer = _extract_answer(answer)
            correct = _validate_answer(game, answer, puzzle, game_cfg, puzzle_mod)

        # Check reasoning budget
        budget_exceeded = False
        if (
            reasoning_budget is not None
            and reasoning_tokens is not None
            and reasoning_tokens > reasoning_budget + reasoning_budget_tolerance
        ):
            budget_exceeded = True
            num_budget_exceeded += 1
            over = reasoning_tokens - reasoning_budget
            print(
                f"    [{i + 1}/{repetitions}] {model_short}/{game}: "
                f"⚠ reasoning budget exceeded: {reasoning_tokens} > "
                f"{reasoning_budget} (+{over} tokens over)",
                file=sys.stderr,
            )
            if enforce_reasoning_budget:
                correct = False

        if correct:
            num_correct += 1
        else:
            num_failed += 1

        total_prompt_tokens += usage["prompt_tokens"]
        total_completion_tokens += usage["completion_tokens"]
        total_total_tokens += usage["total_tokens"]

        status_mark = "✓" if correct else ("⏱" if timed_out else "✗")
        if budget_exceeded:
            status_mark = "⚠" if not enforce_reasoning_budget else "✗⚠"
        r_str = f" r={reasoning_tokens}" if reasoning_tokens else ""
        tok_str = (
            f"tokens={usage['total_tokens']}"
            f" (p={usage['prompt_tokens']} c={usage['completion_tokens']}{r_str})"
            if usage["total_tokens"] > 0
            else "tokens=0"
        )
        print(
            f"    [{i + 1}/{repetitions}] {model_short}/{game}: "
            f"{status_mark} {elapsed}s  {tok_str}  "
            f"answer={answer!r:.60}  solution={puzzle.solution!r:.40}"
        )

        puzzles_data.append(
            {
                "iteration": i + 1,
                "solution": puzzle.solution,
                "response": answer if not timed_out else "TIMEOUT",
                "reasoning_content": reasoning,
                "reasoning_tokens": reasoning_tokens,
                "is_correct": correct,
                "budget_exceeded": budget_exceeded,
                "response_time": elapsed,
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "total_tokens": usage["total_tokens"],
            }
        )

    session_time = round(time.monotonic() - start_time, 2)

    if num_budget_exceeded:
        print(
            f"\n  ⚠ {model_short}/{game}: {num_budget_exceeded}/{num_correct + num_failed} "
            f"puzzles exceeded reasoning budget "
            f"(requested {reasoning_budget}, tolerance ±{reasoning_budget_tolerance})"
        )

    return {
        "puzzles": puzzles_data,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_total_tokens,
        "num_correct": num_correct,
        "num_failed": num_failed,
        "num_trials": num_correct + num_failed,
        "num_errors": num_errors,
        "num_budget_exceeded": num_budget_exceeded,
        "error_sample": error_sample,
        "session_time": session_time,
    }


# ---------------------------------------------------------------------------
# Results database (unchanged schema)
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResultsDB:
    """Persistent experiment results stored in SQLite.

    Every mutation is committed immediately so that data survives crashes.
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or RESULTS_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                config TEXT
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL REFERENCES experiments(id),
                model TEXT NOT NULL,
                game TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                session_code TEXT,
                started_at TEXT,
                completed_at TEXT,
                retries INTEGER DEFAULT 0,
                error TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                exit_code INTEGER,
                session_time REAL,
                num_correct INTEGER,
                num_failed INTEGER,
                num_trials INTEGER,
                data_missing INTEGER DEFAULT 0,
                is_text INTEGER DEFAULT 0,
                UNIQUE(experiment_id, model, game, is_text)
            );
            CREATE TABLE IF NOT EXISTS puzzles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES runs(id),
                iteration INTEGER,
                solution TEXT,
                response TEXT,
                reasoning_content TEXT,
                reasoning_tokens INTEGER,
                is_correct INTEGER,
                response_time REAL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER
            );
        """
        )
        self.conn.commit()
        self._migrate()

    def _migrate(self):
        """Add columns that may not exist in older DBs."""
        existing = {
            row[1] for row in self.conn.execute("PRAGMA table_info(puzzles)").fetchall()
        }
        migrations = {
            "prompt_tokens": "INTEGER",
            "completion_tokens": "INTEGER",
            "total_tokens": "INTEGER",
            "reasoning_content": "TEXT",
            "reasoning_tokens": "INTEGER",
        }
        for col, col_type in migrations.items():
            if col not in existing:
                self.conn.execute(f"ALTER TABLE puzzles ADD COLUMN {col} {col_type}")

        # Migrate runs table
        runs_existing = {
            row[1] for row in self.conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "is_text" not in runs_existing:
            self.conn.execute("ALTER TABLE runs ADD COLUMN is_text INTEGER DEFAULT 0")

        self.conn.commit()

    # -- experiment CRUD --

    def create_experiment(self, name: str, config: dict) -> int:
        self.conn.execute(
            "INSERT INTO experiments (name, created_at, status, config) VALUES (?, ?, 'running', ?)",
            (name, _now(), json.dumps(config, default=str)),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_experiment(self, name: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM experiments WHERE name = ?", (name,)
        ).fetchone()

    def finalize_experiment(self, experiment_id: int, status: str):
        completed_at = _now() if status != "running" else None
        self.conn.execute(
            "UPDATE experiments SET status = ?, completed_at = ? WHERE id = ?",
            (status, completed_at, experiment_id),
        )
        self.conn.commit()

    def reset_runs(self, experiment_id: int, from_status: str, to_status: str) -> int:
        cur = self.conn.execute(
            "UPDATE runs "
            "SET status = ?, started_at = NULL, completed_at = NULL "
            "WHERE experiment_id = ? AND status = ?",
            (to_status, experiment_id, from_status),
        )
        self.conn.commit()
        return cur.rowcount

    # -- runs CRUD --

    def create_runs(
        self, experiment_id: int, models: list[str], games: list[str], is_text: bool = False
    ):
        for model in models:
            for game in games:
                self.conn.execute(
                    "INSERT INTO runs (experiment_id, model, game, status, is_text) "
                    "VALUES (?, ?, ?, 'pending', ?)",
                    (experiment_id, model, game, int(is_text)),
                )
        self.conn.commit()

    def get_runs(self, experiment_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM runs WHERE experiment_id = ? ORDER BY id",
            (experiment_id,),
        ).fetchall()

    def get_pending_runs(self, experiment_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM runs WHERE experiment_id = ? AND status != 'completed' ORDER BY id",
            (experiment_id,),
        ).fetchall()

    def update_run(self, run_id: int, **kwargs):
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [run_id]
        self.conn.execute(f"UPDATE runs SET {sets} WHERE id = ?", vals)
        self.conn.commit()

    # -- puzzles --

    def save_puzzles(self, run_id: int, puzzles: list[dict]):
        self.conn.execute("DELETE FROM puzzles WHERE run_id = ?", (run_id,))
        for p in puzzles:
            is_correct = p.get("is_correct")
            self.conn.execute(
                "INSERT INTO puzzles "
                "(run_id, iteration, solution, response, reasoning_content, reasoning_tokens, "
                "is_correct, response_time, prompt_tokens, completion_tokens, total_tokens) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    p["iteration"],
                    p["solution"],
                    p["response"],
                    p.get("reasoning_content"),
                    p.get("reasoning_tokens"),
                    (1 if is_correct else 0) if is_correct is not None else None,
                    p["response_time"],
                    p.get("prompt_tokens"),
                    p.get("completion_tokens"),
                    p.get("total_tokens"),
                ),
            )
        self.conn.commit()

    def has_puzzles(self, run_id: int) -> bool:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM puzzles WHERE run_id = ?", (run_id,)
        ).fetchone()
        return row[0] > 0

    # -- reporting helpers --

    def get_completed_results(self, experiment_id: int) -> list[dict]:
        """Return results in the format expected by generate_report()."""
        runs = self.conn.execute(
            "SELECT * FROM runs WHERE experiment_id = ? AND status = 'completed' ORDER BY id",
            (experiment_id,),
        ).fetchall()
        results = []
        for run in runs:
            puzzles = self.conn.execute(
                "SELECT iteration, solution, response, reasoning_content, reasoning_tokens, "
                "is_correct, response_time, prompt_tokens, completion_tokens, total_tokens "
                "FROM puzzles WHERE run_id = ? ORDER BY iteration",
                (run["id"],),
            ).fetchall()
            results.append(
                {
                    "game": run["game"],
                    "model": run["model"],
                    "tokens": {
                        "prompt_tokens": run["prompt_tokens"] or 0,
                        "completion_tokens": run["completion_tokens"] or 0,
                        "total_tokens": run["total_tokens"] or 0,
                        "exit_code": run["exit_code"] or 0,
                    },
                    "puzzles": [
                        {
                            "iteration": p["iteration"],
                            "solution": p["solution"],
                            "response": p["response"],
                            "reasoning_content": p["reasoning_content"],
                            "reasoning_tokens": p["reasoning_tokens"],
                            "is_correct": (
                                bool(p["is_correct"])
                                if p["is_correct"] is not None
                                else None
                            ),
                            "response_time": p["response_time"],
                            "prompt_tokens": p["prompt_tokens"],
                            "completion_tokens": p["completion_tokens"],
                            "total_tokens": p["total_tokens"],
                        }
                        for p in puzzles
                    ],
                    "player_summary": (
                        {
                            "num_correct": run["num_correct"],
                            "num_failed": run["num_failed"],
                            "num_trials": run["num_trials"],
                        }
                        if run["num_correct"] is not None
                        else None
                    ),
                    "session_time": run["session_time"],
                }
            )
        return results

    def export_json(self, experiment_id: int, output_path: Path):
        """Export full experiment data as a JSON file."""
        exp = self.conn.execute(
            "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
        ).fetchone()
        results = self.get_completed_results(experiment_id)
        all_runs = self.get_runs(experiment_id)

        run_list = []
        for run in all_runs:
            matching = [
                r
                for r in results
                if r["model"] == run["model"] and r["game"] == run["game"]
            ]
            base = matching[0] if matching else {}
            run_list.append(
                {
                    "model": run["model"],
                    "game": run["game"],
                    "status": run["status"],
                    "started_at": run["started_at"],
                    "completed_at": run["completed_at"],
                    "retries": run["retries"],
                    "error": run["error"],
                    "tokens": base.get("tokens"),
                    "player_summary": base.get("player_summary"),
                    "session_time": base.get("session_time"),
                    "data_missing": bool(run["data_missing"]),
                    "puzzles": base.get("puzzles", []),
                }
            )

        n_completed = sum(1 for r in all_runs if r["status"] == "completed")
        n_failed = sum(1 for r in all_runs if r["status"] == "failed")
        n_missing = sum(1 for r in all_runs if r["data_missing"])

        data = {
            "name": exp["name"],
            "created_at": exp["created_at"],
            "completed_at": exp["completed_at"],
            "status": exp["status"],
            "config": json.loads(exp["config"]) if exp["config"] else {},
            "summary": {
                "total_runs": len(all_runs),
                "completed": n_completed,
                "failed": n_failed,
                "data_missing": n_missing,
            },
            "runs": run_list,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _escape_md(text: str) -> str:
    """Escape pipe characters for markdown tables."""
    return text.replace("|", "\\|").replace("\n", " ")


def generate_report(
    results: list[dict],
    models: list[str],
    run_config: dict,
    output_dir: Path | None = None,
):
    """Generate one markdown report per model."""
    output_dir = output_dir or REPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    config_lines = []
    for key in (
        "temperature",
        "max_tokens",
        "top_p",
        "reasoning_effort",
    ):
        val = run_config.get(key)
        if val is not None:
            config_lines.append(f"- **{key}**: `{val}`")

    game_configs = run_config.get("game_configs")
    all_model_configs = run_config.get("model_configs") or {}

    for model in models:
        model_short = model.rsplit("/", 1)[-1]
        model_results = [r for r in results if r["model"] == model]

        lines = []
        lines.append(f"# Benchmark Report — {model_short}")
        lines.append("")
        lines.append(f"- **Model**: `{model}`")
        lines.append(f"- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        lines.append("## Run Configuration")
        lines.append("")
        if config_lines:
            lines.extend(config_lines)
        else:
            lines.append("*Default settings (no overrides)*")

        mcfg = all_model_configs.get(model, {})
        if mcfg:
            lines.append("")
            lines.append("**Model-specific overrides:**")
            for k, v in mcfg.items():
                lines.append(f"- {k}: `{v}`")
        lines.append("")

        if game_configs:
            lines.append("### Game Config Overrides")
            lines.append("")
            for gname, gcfg in game_configs.items():
                params_str = ", ".join(f"{k}={v}" for k, v in gcfg.items())
                lines.append(f"- **{gname}**: {params_str}")
            lines.append("")

        # Summary table
        lines.append("## Summary")
        lines.append("")
        lines.append(
            "| Game | Prompt Tokens | Completion Tokens | Total Tokens "
            "| Correct | Incorrect | Avg Response Time (s) | Session Time (s) |"
        )
        lines.append(
            "|------|--------------|-------------------|-------------"
            "|---------|-----------|----------------------|------------------|"
        )

        sum_prompt = 0
        sum_completion = 0
        sum_total = 0

        for r in model_results:
            puzzles = r["puzzles"]
            player = r["player_summary"]
            correct = player["num_correct"] if player else "N/A"
            incorrect = player["num_failed"] if player else "N/A"
            times = [
                p["response_time"] for p in puzzles if p["response_time"] is not None
            ]
            avg_time = f"{sum(times) / len(times):.2f}" if times else "N/A"
            session_time = r["session_time"] if r["session_time"] is not None else "N/A"

            sum_prompt += r["tokens"]["prompt_tokens"]
            sum_completion += r["tokens"]["completion_tokens"]
            sum_total += r["tokens"]["total_tokens"]

            lines.append(
                f"| {r['game']} "
                f"| {r['tokens']['prompt_tokens']} "
                f"| {r['tokens']['completion_tokens']} "
                f"| {r['tokens']['total_tokens']} "
                f"| {correct} "
                f"| {incorrect} "
                f"| {avg_time} "
                f"| {session_time} |"
            )

        lines.append(
            f"| **TOTAL** "
            f"| **{sum_prompt}** "
            f"| **{sum_completion}** "
            f"| **{sum_total}** "
            f"| | | | |"
        )

        lines.append("")

        # Per-game detail tables
        for r in model_results:
            lines.append(f"## {r['game']}")
            lines.append("")

            if not r["puzzles"]:
                lines.append("*No puzzle data found.*")
                lines.append("")
                continue

            lines.append(
                "| Iteration | Solution | Response | Correct | Response Time (s) |"
            )
            lines.append(
                "|-----------|----------|----------|---------|-------------------|"
            )

            for p in r["puzzles"]:
                correct_str = {True: "Yes", False: "No", None: "N/A"}[p["is_correct"]]
                solution = _escape_md(str(p["solution"] or ""))
                response = _escape_md(str(p["response"] or ""))
                rt = p["response_time"] if p["response_time"] is not None else "N/A"
                lines.append(
                    f"| {p['iteration']} | {solution} | {response} "
                    f"| {correct_str} | {rt} |"
                )

            lines.append("")

        report = "\n".join(lines)
        safe_name = model.replace("/", "_")
        report_file = output_dir / f"{safe_name}.md"
        report_file.write_text(report)
        print(f"\nReport written to {report_file}")


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------


def _request_stop(signum, frame):
    """First Ctrl+C: graceful stop after current run. Second: force exit."""
    global _interrupted
    if _interrupted:
        print("\nForce exit.")
        sys.exit(1)
    _interrupted = True
    print("\n\nInterrupt received. Will stop after current run completes...")
    print("Press Ctrl+C again to force exit.\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    global _interrupted

    parser = argparse.ArgumentParser(
        description="Run LLM benchmarks on puzzle games (direct OpenRouter calls)."
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help=f"Path to YAML benchmark config file (default: {DEFAULT_CONFIG.name}).",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help=f"LLM models to benchmark (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--games",
        nargs="*",
        default=None,
        help='Games to benchmark (default: all). Use "all" to run all games.',
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature for the LLM.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Maximum number of tokens in the LLM response.",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=["xhigh", "high", "medium", "low", "minimal", "none"],
        default=None,
        help="OpenRouter reasoning effort level.",
    )
    parser.add_argument(
        "--reasoning-max-tokens",
        type=int,
        default=None,
        help="Hard cap on reasoning/thinking tokens (sent as reasoning.max_tokens).",
    )
    parser.add_argument(
        "--incentive",
        choices=["true", "false", "explicit_none"],
        default=None,
        help="Incentive mode: true (show compensation), false (silent), explicit_none (say no compensation).",
    )
    parser.add_argument(
        "--persona",
        choices=["standard", "human", "control"],
        default=None,
        help="Prompt persona: standard (default), human, or control.",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=None,
        help="Nucleus sampling parameter (0.0 - 1.0).",
    )
    parser.add_argument(
        "--resume",
        default=None,
        metavar="NAME",
        help="Resume an experiment by name (skips completed runs).",
    )
    parser.add_argument(
        "--experiment-name",
        default=None,
        help="Custom experiment name (default: UTC timestamp).",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="Directory for reports (default: reports/<experiment-name>/).",
    )
    parser.add_argument(
        "--run-delay",
        type=float,
        default=None,
        help="Seconds to wait between runs for rate-limit protection.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="Max retries per failed run (default: 1).",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=None,
        help="Number of repetitions per game (overrides YAML game_defaults.repetitions).",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        default=False,
        help="Send text descriptions instead of images for all games.",
    )
    # Keep for backward compat with run_parallel.sh (no-op now)
    parser.add_argument(
        "--no-reload", action="store_true", default=False, help=argparse.SUPPRESS
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _request_stop)

    # Load YAML config
    yaml_cfg = load_benchmark_config(args.config)

    # Merge: CLI > YAML > defaults
    models = args.models or yaml_cfg.get("models") or [DEFAULT_MODEL]
    temperature = (
        args.temperature
        if args.temperature is not None
        else yaml_cfg.get("temperature")
    )
    max_tokens = (
        args.max_tokens
        if args.max_tokens is not None
        else yaml_cfg.get("max_tokens", 2048)
    )
    top_p = args.top_p if args.top_p is not None else yaml_cfg.get("top_p")
    reasoning_effort = args.reasoning_effort or yaml_cfg.get("reasoning_effort")
    reasoning_max_tokens = (
        args.reasoning_max_tokens
        if args.reasoning_max_tokens is not None
        else yaml_cfg.get("reasoning_max_tokens")
    )
    run_delay = (
        args.run_delay if args.run_delay is not None else yaml_cfg.get("run_delay", 0)
    )
    max_retries = (
        args.max_retries
        if args.max_retries is not None
        else yaml_cfg.get("max_retries", 1)
    )
    retry_base_delay = yaml_cfg.get("retry_base_delay", 10)
    enforce_reasoning_budget = yaml_cfg.get("enforce_reasoning_budget", False)
    reasoning_budget_tolerance = int(yaml_cfg.get("reasoning_budget_tolerance", 16))
    provider = yaml_cfg.get("provider") or None

    model_configs = yaml_cfg.get("model_configs", {}) or {}

    # Game defaults
    game_defaults = yaml_cfg.get("game_defaults", {}) or {}
    repetitions = args.repetitions or int(game_defaults.get("repetitions", 1))
    puzzle_timeout = int(game_defaults.get("puzzle_timeout", 0))
    # Incentive mode: CLI > YAML (CLI uses strings, YAML uses bool/string)
    if args.incentive is not None:
        incentive = {"true": True, "false": False, "explicit_none": "explicit_none"}[
            args.incentive
        ]
    else:
        incentive = game_defaults.get("incentive", False)
    incentive_text = (
        game_defaults.get("incentive_text", "") if incentive is True else ""
    )

    # Persona: CLI > YAML > default ("standard")
    persona = args.persona or game_defaults.get("persona", "standard")

    if persona == "human":
        if incentive is True and incentive_text:
            system_prompt = SYSTEM_PROMPT_HUMAN_INCENTIVE.format(
                incentive_text=incentive_text
            )
        else:
            system_prompt = SYSTEM_PROMPT_HUMAN_EXPLICIT_NO_INCENTIVE
    elif persona == "control":
        system_prompt = SYSTEM_PROMPT_CONTROL
    else:
        if incentive is True and incentive_text:
            system_prompt = SYSTEM_PROMPT_INCENTIVE.format(
                incentive_text=incentive_text
            )
        else:
            system_prompt = SYSTEM_PROMPT_EXPLICIT_NO_INCENTIVE

    # Resolve games
    if args.games:
        if args.games == ["all"]:
            games = ALL_GAMES
        else:
            games = args.games
    elif "games" in yaml_cfg and yaml_cfg["games"] is not None:
        games = list(yaml_cfg["games"].keys())
    else:
        games = ALL_GAMES

    # Validate game names
    for game in games:
        if game not in GAME_MODULES:
            print(f"Unknown game: '{game}'. Available: {ALL_GAMES}", file=sys.stderr)
            sys.exit(1)

    # Per-game config overrides
    yaml_games = yaml_cfg.get("games", {}) or {}
    game_configs = {g: {**game_defaults, **(yaml_games.get(g) or {})} for g in games}

    run_config = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "reasoning_effort": reasoning_effort,
        "reasoning_max_tokens": reasoning_max_tokens,
        "game_configs": {
            g: yaml_games.get(g) or {} for g in games if yaml_games.get(g)
        },
        "model_configs": model_configs or None,
    }

    # Override game_defaults with the actual incentive value used (CLI may differ from YAML)
    game_defaults_actual = {
        **game_defaults,
        "incentive": incentive,
        "incentive_text": incentive_text,
        "persona": persona,
    }

    text_only = args.text_only

    full_config = {
        "models": models,
        "games": games,
        **run_config,
        "run_delay": run_delay,
        "max_retries": max_retries,
        "retry_base_delay": retry_base_delay,
        "game_defaults": game_defaults_actual,
        "text_only": text_only,
    }

    # ------------------------------------------------------------------
    # Open results DB and set up experiment
    # ------------------------------------------------------------------
    db = ResultsDB()

    if args.resume:
        exp_row = db.get_experiment(args.resume)
        if exp_row is None:
            print(
                f"ERROR: No experiment named '{args.resume}' in {RESULTS_DB}",
                file=sys.stderr,
            )
            db.close()
            sys.exit(1)
        exp_id = exp_row["id"]
        exp_name = exp_row["name"]
        stored_config = (
            json.loads(exp_row["config"]) if exp_row["config"] else full_config
        )
        stored_models = stored_config.get("models", models)
        stored_games = stored_config.get("games", games)

        if args.models:
            new_models = [m for m in args.models if m not in stored_models]
            if new_models:
                # Add new models to the experiment: create runs and update stored config
                run_games = stored_games
                db.create_runs(exp_id, new_models, run_games, is_text=text_only)
                stored_models.extend(new_models)
                stored_config["models"] = stored_models
                db.conn.execute(
                    "UPDATE experiments SET config = ? WHERE id = ?",
                    (json.dumps(stored_config), exp_id),
                )
                db.conn.commit()
                print(f"Added {len(new_models)} new model(s) to experiment: {new_models}")
            models = args.models
        else:
            models = stored_models

        if args.games:
            requested_games = ALL_GAMES if args.games == ["all"] else args.games
            new_games = [g for g in requested_games if g not in stored_games]
            if new_games:
                # Add new games to the experiment: create runs and update stored config
                run_models = stored_models
                db.create_runs(exp_id, run_models, new_games, is_text=text_only)
                stored_games.extend(new_games)
                stored_config["games"] = stored_games
                db.conn.execute(
                    "UPDATE experiments SET config = ? WHERE id = ?",
                    (json.dumps(stored_config), exp_id),
                )
                db.conn.commit()
                print(f"Added {len(new_games)} new game(s) to experiment: {new_games}")
            games = requested_games
        else:
            games = stored_games

        n_done = len(db.get_runs(exp_id)) - len(db.get_pending_runs(exp_id))
        n_total = len(db.get_runs(exp_id))
        print(f"Resuming experiment '{exp_name}' ({n_done}/{n_total} completed)")
    else:
        exp_name = args.experiment_name or datetime.now(timezone.utc).strftime(
            "%Y-%m-%d_%H%M%S"
        )
        if db.get_experiment(exp_name) is not None:
            print(
                f"ERROR: Experiment '{exp_name}' already exists. "
                f"Use --resume {exp_name} to continue it.",
                file=sys.stderr,
            )
            db.close()
            sys.exit(1)
        exp_id = db.create_experiment(exp_name, full_config)
        db.create_runs(exp_id, models, games, is_text=text_only)
        print(
            f"Created experiment '{exp_name}' ({len(models)} models x {len(games)} games)"
        )

    exp_dir = Path(args.report_dir) if args.report_dir else REPORT_DIR / exp_name
    exp_dir.mkdir(parents=True, exist_ok=True)

    if args.prepare_only:
        reset_count = db.reset_runs(exp_id, from_status="running", to_status="pending")
        if reset_count:
            print(f"Reset {reset_count} stale running runs to pending")

        pending = db.get_pending_runs(exp_id)
        if pending:
            db.finalize_experiment(exp_id, "running")

        print(
            f"Prepared experiment '{exp_name}' "
            f"({len(db.get_runs(exp_id)) - len(pending)}/{len(db.get_runs(exp_id))} completed)"
        )
        db.close()
        return

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr)
        db.close()
        sys.exit(1)

    # ------------------------------------------------------------------
    # Run games
    # ------------------------------------------------------------------
    exp_status = "failed"
    try:
        model_set = set(models)
        game_set = set(games)
        selected_runs = [
            run
            for run in db.get_runs(exp_id)
            if run["model"] in model_set and run["game"] in game_set
        ]
        pending = [
            run
            for run in db.get_pending_runs(exp_id)
            if run["model"] in model_set and run["game"] in game_set
        ]
        total = len(selected_runs)
        completed = total - len(pending)

        if total == 0:
            print(f"No runs matched the current selection for experiment '{exp_name}'")

        for seq, run_row in enumerate(pending):
            if _interrupted:
                break

            run_id = run_row["id"]
            game = run_row["game"]
            model = run_row["model"]
            model_short = model.rsplit("/", 1)[-1]
            success = False

            for attempt in range(max_retries + 1):
                if _interrupted:
                    break

                db.update_run(run_id, status="running", started_at=_now(), error=None)

                try:
                    # Merge per-model overrides
                    mcfg = model_configs.get(model, {})
                    m_temperature = mcfg.get("temperature", temperature)
                    m_max_tokens = mcfg.get("max_tokens", max_tokens)
                    m_top_p = mcfg.get("top_p", top_p)
                    m_reasoning_effort = mcfg.get("reasoning_effort", reasoning_effort)
                    m_reasoning_max_tokens = mcfg.get(
                        "reasoning_max_tokens", reasoning_max_tokens
                    )
                    m_provider = mcfg.get("provider", provider)

                    print(f"\n{'='*60}")
                    print(f"  {model_short} / {game}  (attempt {attempt + 1})")
                    print(f"{'='*60}")

                    gcfg = game_configs.get(game, {})
                    # Per-game max_tokens override (e.g. sudoku needs more)
                    g_max_tokens = gcfg.get("max_tokens", m_max_tokens)
                    gcfg = {k: v for k, v in gcfg.items() if k != "max_tokens"}

                    result = run_game(
                        game,
                        model,
                        api_key,
                        repetitions=repetitions,
                        game_cfg=gcfg,
                        temperature=m_temperature,
                        max_tokens=g_max_tokens,
                        reasoning_effort=m_reasoning_effort,
                        reasoning_max_tokens=m_reasoning_max_tokens,
                        top_p=m_top_p,
                        puzzle_timeout=puzzle_timeout,
                        system_prompt=system_prompt,
                        provider=m_provider,
                        enforce_reasoning_budget=enforce_reasoning_budget,
                        reasoning_budget_tolerance=reasoning_budget_tolerance,
                        text_only=text_only,
                    )

                    # If ALL puzzles were API errors, treat the run as failed
                    all_errored = (
                        result["num_errors"] > 0
                        and result["num_errors"] == result["num_trials"]
                    )

                    if all_errored:
                        error_msg = (
                            f"All {result['num_errors']} puzzles failed: "
                            f"{result['error_sample']}"
                        )
                        db.update_run(
                            run_id,
                            status="failed",
                            completed_at=_now(),
                            retries=attempt,
                            error=error_msg,
                            prompt_tokens=result["prompt_tokens"],
                            completion_tokens=result["completion_tokens"],
                            total_tokens=result["total_tokens"],
                            exit_code=1,
                            session_time=result["session_time"],
                            num_correct=result["num_correct"],
                            num_failed=result["num_failed"],
                            num_trials=result["num_trials"],
                        )
                        db.save_puzzles(run_id, result["puzzles"])
                        print(
                            f"\n  [{model_short} / {game}] ALL PUZZLES ERRORED: "
                            f"{result['error_sample'][:120]}"
                        )
                        # Don't retry if it's a model ID error (would fail again)
                        if "not a valid model" in result["error_sample"]:
                            break
                        # Otherwise let the retry loop handle it
                        continue

                    # Save results
                    db.update_run(
                        run_id,
                        status="completed",
                        completed_at=_now(),
                        retries=attempt,
                        prompt_tokens=result["prompt_tokens"],
                        completion_tokens=result["completion_tokens"],
                        total_tokens=result["total_tokens"],
                        exit_code=0,
                        session_time=result["session_time"],
                        num_correct=result["num_correct"],
                        num_failed=result["num_failed"],
                        num_trials=result["num_trials"],
                    )
                    db.save_puzzles(run_id, result["puzzles"])

                    completed += 1
                    success = True
                    print(
                        f"\n  [{completed}/{total}] {model_short} / {game}: "
                        f"DONE ({result['num_correct']}/{result['num_trials']} correct, "
                        f"{result['total_tokens']} tokens)"
                    )
                    break

                except Exception as e:
                    error_msg = f"{type(e).__name__}: {e}"
                    db.update_run(run_id, error=error_msg, retries=attempt)
                    print(f"\n  Exception: {error_msg}", file=sys.stderr)
                    traceback.print_exc()

                    if attempt < max_retries:
                        delay = retry_base_delay * (2**attempt)
                        print(f"  Retry {attempt + 1}/{max_retries} in {delay}s...")
                        time.sleep(delay)

            if not success and not _interrupted:
                db.update_run(run_id, status="failed", retries=max_retries)
                print(
                    f"\n  FAILED after {max_retries + 1} attempts: {model_short} / {game}"
                )

            # Rate-limit delay
            remaining = len(pending) - (seq + 1)
            if remaining > 0 and run_delay > 0 and not _interrupted:
                print(
                    f"  Waiting {run_delay}s before next run ({remaining} remaining)..."
                )
                time.sleep(run_delay)

        if _interrupted:
            exp_status = "interrupted"

    except Exception as exc:
        exp_status = "failed"
        print(f"\nFatal error: {exc}", file=sys.stderr)
        traceback.print_exc()

    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        all_runs = db.get_runs(exp_id)
        n_completed = sum(1 for r in all_runs if r["status"] == "completed")
        n_failed = sum(1 for r in all_runs if r["status"] == "failed")
        n_pending = sum(1 for r in all_runs if r["status"] in ("pending", "running"))
        tot_prompt = sum(r["prompt_tokens"] or 0 for r in all_runs)
        tot_completion = sum(r["completion_tokens"] or 0 for r in all_runs)
        tot_tokens = sum(r["total_tokens"] or 0 for r in all_runs)

        if exp_status != "interrupted":
            exp_status = "running" if n_pending else "completed"
        db.finalize_experiment(exp_id, exp_status)

        # Export JSON
        try:
            json_name = f"{exp_name}.json" if args.report_dir else STATE_FILE
            db.export_json(exp_id, exp_dir / json_name)
        except Exception as e:
            print(f"  WARNING: Could not export JSON: {e}", file=sys.stderr)

        # Generate markdown reports
        try:
            results = db.get_completed_results(exp_id)
            generate_report(results, models, run_config, exp_dir)
        except Exception as e:
            print(f"  WARNING: Could not generate reports: {e}", file=sys.stderr)

        # Final summary
        db.close()

        print(f"\nExperiment '{exp_name}' {exp_status}:")
        print(f"  {n_completed} completed, {n_failed} failed, {n_pending} pending")
        print(
            f"  Tokens: {tot_tokens} total "
            f"(prompt={tot_prompt}, completion={tot_completion})"
        )
        if n_pending:
            print(f"  Resume with: uv run python run_benchmarks.py --resume {exp_name}")
        print(f"  Results DB:  {RESULTS_DB}")
        print(f"  Reports:     {exp_dir}")

        signal.signal(signal.SIGINT, signal.SIG_DFL)


if __name__ == "__main__":
    main()
