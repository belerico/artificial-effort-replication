import time

from otree import settings
from otree.api import *

from config import get_game_config, payoff_summary, export_puzzle_rows

from . import task_transcription
from .image_utils import encode_image

doc = """
Transcribe distorted text from an image (image-based, single player).
"""


class C(BaseConstants):
    NAME_IN_URL = "task_transcription"
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1

    INSTRUCTION_TEMPLATE = __name__ + "/instructions.html"


class Subsession(BaseSubsession):
    pass


def creating_session(subsession: Subsession):
    session = subsession.session
    game_cfg = get_game_config("task_transcription")
    defaults = dict(
        retry_delay=1.0,
        puzzle_delay=1.0,
        attempts_per_puzzle=1,
        max_iterations=1,
        length=3,
        timeout=60,
        puzzle_timeout=0,
        incentive=False,
        incentive_text="You will earn a bonus of $0.10 for each correct answer.",
        bonus_per_correct=0.2,
        allow_skip=False,
    )
    # Merge into shared params — in a multi-app session oTree runs every app's
    # creating_session, so don't wipe params set by the other games.
    session.params = session.vars.get("params") or {}
    # session.config (editable per-session in the oTree admin) wins over the
    # YAML; the YAML still supplies per-game params absent from session.config.
    for param in defaults:
        session.params[param] = session.config.get(param, game_cfg.get(param, defaults[param]))
    reps = session.config.get("repetitions", game_cfg.get("repetitions"))
    if reps is not None:
        session.params["max_iterations"] = int(reps)


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    iteration = models.IntegerField(initial=0)
    num_trials = models.IntegerField(initial=0)
    num_correct = models.IntegerField(initial=0)
    num_failed = models.IntegerField(initial=0)


class Puzzle(ExtraModel):
    player = models.Link(Player)
    iteration = models.IntegerField(initial=0)
    attempts = models.IntegerField(initial=0)
    timestamp = models.FloatField(initial=0)
    text = models.LongStringField()
    solution = models.LongStringField()
    response = models.LongStringField()
    response_timestamp = models.FloatField()
    is_correct = models.BooleanField()


def gen_puzzle(player: Player) -> Puzzle:
    fields = task_transcription.generate_puzzle_fields(
        length=player.session.params["length"],
    )
    player.iteration += 1
    return Puzzle.create(
        player=player,
        iteration=player.iteration,
        timestamp=time.time(),
        **fields,
    )


def get_cur_puzzle(player: Player):
    puzzles = Puzzle.filter(player=player, iteration=player.iteration)
    if puzzles:
        [puzzle] = puzzles
        return puzzle


def enc_puzzle(puzzle: Puzzle):
    image = task_transcription.render_image(puzzle)
    return dict(image=encode_image(image))


def get_progress(player: Player):
    return dict(
        num_trials=player.num_trials,
        num_correct=player.num_correct,
        num_incorrect=player.num_failed,
        iteration=player.iteration,
    )


def custom_export(players):
    """One row per puzzle attempt — appears on the admin Data page."""
    yield from export_puzzle_rows(players, Puzzle)


def play_game(player: Player, msg: dict):
    session = player.session
    my_id = player.id_in_group
    params = session.params
    now = time.time()
    current = get_cur_puzzle(player)
    msg_type = msg["type"]

    # Auto-fail a stale puzzle if its per-puzzle timeout was exceeded — a safety
    # net for non-'timeout' messages. Explicit 'timeout' messages are handled by
    # the timeout branch below, which needs current.response to still be None.
    puzzle_timeout = params.get("puzzle_timeout", 0)
    if (
        puzzle_timeout > 0
        and current is not None
        and current.response is None
        and msg_type != "timeout"
    ):
        if now - current.timestamp >= puzzle_timeout:
            current.response = "TIMEOUT"
            current.is_correct = False
            current.response_timestamp = now
            current.attempts = params["attempts_per_puzzle"]
            player.num_failed += 1
            player.num_trials += 1

    if msg_type == "load":
        prog = get_progress(player)
        if current:
            return {my_id: dict(type="status", progress=prog, puzzle=enc_puzzle(current))}
        else:
            return {my_id: dict(type="status", progress=prog)}

    if msg_type == "cheat" and settings.DEBUG:
        return {my_id: dict(type="solution", solution=current.solution)}

    if msg_type == "timeout":
        if current is None or current.response is not None:
            return {my_id: dict(type="status", progress=get_progress(player))}
        current.response = "TIMEOUT"
        current.is_correct = False
        current.response_timestamp = now
        current.attempts = params["attempts_per_puzzle"]
        player.num_failed += 1
        player.num_trials += 1
        return {
            my_id: dict(
                type="feedback",
                is_correct=False,
                retries_left=0,
                progress=get_progress(player),
                timed_out=True,
            )
        }

    if msg_type == "skip":
        # Admin-only "Skip" — enabled per session via the allow_skip config flag.
        if not params.get("allow_skip", False) or current is None:
            return {my_id: dict(type="status", progress=get_progress(player))}
        if current.response is None:
            current.response = "SKIPPED"
            current.is_correct = False
            current.response_timestamp = now
            current.attempts = params["attempts_per_puzzle"]
            player.num_failed += 1
            player.num_trials += 1
        return {
            my_id: dict(
                type="feedback",
                is_correct=False,
                retries_left=0,
                progress=get_progress(player),
                timed_out=True,
            )
        }

    if msg_type == "next":
        if current is not None:
            if current.response is None:
                raise RuntimeError("trying to skip over unsolved puzzle")
            if now < current.timestamp + params["puzzle_delay"]:
                raise RuntimeError("retrying too fast")
            if current.iteration >= params["max_iterations"]:
                return {
                    my_id: dict(
                        type="status",
                        progress=get_progress(player),
                        iterations_left=0,
                    )
                }
        else:
            if player.iteration >= params["max_iterations"]:
                return {
                    my_id: dict(
                        type="status",
                        progress=get_progress(player),
                        iterations_left=0,
                    )
                }
        puzz = gen_puzzle(player)
        prog = get_progress(player)
        return {my_id: dict(type="puzzle", puzzle=enc_puzzle(puzz), progress=prog)}

    if msg_type == "answer":
        if current is None:
            raise RuntimeError("trying to answer no puzzle")

        # Reject stale answers (from before a puzzle timeout)
        msg_iter = msg.get("iteration")
        if msg_iter is not None and msg_iter != player.iteration:
            prog = get_progress(player)
            resp = dict(type="status", progress=prog)
            if current:
                resp["puzzle"] = enc_puzzle(current)
            return {my_id: resp}

        if current.response is not None:
            if current.attempts >= params["attempts_per_puzzle"]:
                raise RuntimeError("no more attempts allowed")
            if now < current.response_timestamp + params["retry_delay"]:
                raise RuntimeError("retrying too fast")

            player.num_trials -= 1
            if current.is_correct:
                player.num_correct -= 1
            else:
                player.num_failed -= 1

        answer = msg["answer"]

        if answer == "" or answer is None:
            raise ValueError("Answer is empty")

        current.response = answer
        current.is_correct = task_transcription.is_correct(answer, current)
        current.response_timestamp = now
        current.attempts += 1

        if current.is_correct:
            player.num_correct += 1
        else:
            player.num_failed += 1
        player.num_trials += 1

        tries_left = params["attempts_per_puzzle"] - current.attempts
        prog = get_progress(player)
        return {
            my_id: dict(
                type="feedback",
                is_correct=current.is_correct,
                retries_left=tries_left,
                progress=prog,
            )
        }

    raise RuntimeError("unrecognized message from client")


# PAGES


class Game(Page):
    @staticmethod
    def get_timeout_seconds(player: Player):
        return None  # no oTree page timeout — per-puzzle countdown handles timing

    live_method = play_game

    @staticmethod
    def js_vars(player: Player):
        return dict(params=player.session.params)

    @staticmethod
    def vars_for_template(player: Player):
        params = player.session.params
        return dict(
            DEBUG=settings.DEBUG,
            input_type=task_transcription.INPUT_TYPE,
            placeholder=task_transcription.INPUT_HINT,
            incentive_text=params["incentive_text"] if params["incentive"] else "",
        )


class Results(Page):
    @staticmethod
    def vars_for_template(player: Player):
        return payoff_summary(player)


class End(Page):
    @staticmethod
    def is_displayed(player: Player):
        max_iter = player.session.params.get("max_iterations", 1)
        return player.iteration >= max_iter

    @staticmethod
    def vars_for_template(player: Player):
        return dict(message="Thank you. You have completed all repetitions.")


page_sequence = [Game, Results, End]
