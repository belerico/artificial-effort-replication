from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent / "otree_config.yaml"


def load_benchmark_config(config_path=None):
    """Load full YAML config. Returns {} if file doesn't exist."""
    path = Path(config_path) if config_path else _CONFIG_PATH
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def get_game_config(game_name, config_path=None):
    """Get per-game config dict from YAML.

    Merges global ``game_defaults`` with per-game overrides (per-game wins).
    Returns {} if neither section exists.
    """
    config = load_benchmark_config(config_path)
    defaults = config.get("game_defaults", {}) or {}
    games = config.get("games", {}) or {}
    per_game = games.get(game_name, {}) or {}
    return {**defaults, **per_game}


def payoff_summary(player):
    """Per-task figures for the Results page.

    ``bonus`` is what the participant would earn *if this task is the one
    drawn for payment* — num_correct x bonus_per_correct, in real-world
    currency. Only one task is ever paid and the draw happens at payment
    time, so this is computed for display only: it is NEVER written to
    ``player.payoff`` (doing so would make oTree sum it across every task
    into ``participant.payoff``).
    """
    from otree.api import cu

    params = getattr(player.session, "params", {}) or {}
    incentive = params.get("incentive") is True
    points = (
        player.num_correct * float(params.get("bonus_per_correct", 1.0))
        if incentive
        else 0
    )
    return dict(
        incentive=incentive,
        bonus=cu(points).to_real_world_currency(player.session),
    )


def export_puzzle_rows(players, puzzle_model, extra_fields=()):
    """Yield CSV rows (header first) for an app's per-puzzle ExtraModel.

    Used by each app's ``custom_export`` so the puzzle-level data — one row
    per puzzle attempt — is downloadable from the oTree admin Data page,
    matching the grain of the LLM benchmark's ``puzzles`` table.

    ``puzzle_model`` — the app's Puzzle/Question ExtraModel class.
    ``extra_fields`` — extra puzzle attributes to append (e.g. 'current_state').
    """
    header = [
        "session_code", "participant_code", "participant_label", "incentive",
        "num_correct", "num_failed", "num_trials",
        "iteration", "attempts", "text", "solution", "response",
        "is_correct", "timestamp", "response_timestamp", "response_time",
    ]
    yield header + list(extra_fields)
    for p in players:
        participant = p.participant
        session = p.session
        params = getattr(session, "params", None) or {}
        for puz in puzzle_model.filter(player=p):
            ts = puz.timestamp or 0
            rts = puz.response_timestamp or 0
            response_time = round(rts - ts, 3) if (ts and rts) else None
            row = [
                session.code, participant.code, participant.label,
                params.get("incentive"),
                p.num_correct, p.num_failed, p.num_trials,
                puz.iteration, puz.attempts, puz.text, puz.solution, puz.response,
                puz.is_correct, puz.timestamp, puz.response_timestamp, response_time,
            ]
            row += [getattr(puz, f, None) for f in extra_fields]
            yield row
