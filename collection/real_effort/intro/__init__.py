from otree.api import *

doc = """
Welcome page shown once at the start of each day's session: overall
instructions plus the participant's email. The email is stored as the
participant label so it links the same person's Day 1 and Day 2 data and
appears in every oTree data export.
"""


class C(BaseConstants):
    NAME_IN_URL = "intro"
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    email = models.StringField(label="Email address")


def email_error_message(player: Player, value):
    """Basic format check for the email field."""
    value = (value or "").strip()
    if "@" not in value or "." not in value.rsplit("@", 1)[-1]:
        return "Please enter a valid email address."


# PAGES


class Welcome(Page):
    form_model = "player"
    form_fields = ["email"]

    @staticmethod
    def vars_for_template(player: Player):
        name = player.session.config.get("name", "")
        if name.endswith("day2"):
            session_label = "This is the second of the two study sessions."
        elif name.endswith("day1"):
            session_label = "This is the first of two study sessions."
        else:
            session_label = ""
        return dict(session_label=session_label)

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        # The email links a participant's Day 1 and Day 2 records. Store it as
        # the participant label so it shows up in every oTree data export.
        player.participant.label = player.email.strip()


page_sequence = [Welcome]
