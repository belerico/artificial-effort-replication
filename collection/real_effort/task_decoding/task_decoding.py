from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import random
import json

TEXT_FONT = Path(__file__).parent / "assets" / "FreeSerifBold.otf"

CHARSET = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
DIGITS = tuple("0123456789")
WORD_LENGTH = 5

INPUT_TYPE = "text"
INPUT_HINT = "enter text decoded from the number"


def generate_puzzle_fields(word_length=WORD_LENGTH):
    """Create new puzzle for a player"""

    chars = random.sample(CHARSET, len(DIGITS))
    digits = random.sample(DIGITS, len(DIGITS))

    lookup = dict(zip(digits, chars))

    coded_word = "".join(random.sample(DIGITS, word_length))
    solution = "".join(lookup[digit] for digit in coded_word)

    return dict(
        text=json.dumps(dict(rows=[chars, digits], coded_word=coded_word)),
        solution=solution,
    )


def is_correct(response, puzzle):
    return puzzle.solution.lower() == response.lower()


def render_text(puzzle):
    """Return the cipher table and coded word as plain text."""
    data = json.loads(puzzle.text)
    letters = data["rows"][0]
    digits = data["rows"][1]
    # Format as: A=0  B=1  C=2 ...
    pairs = [f"{l}={d}" for l, d in zip(letters, digits)]
    table = "  ".join(pairs)
    return f"Lookup table:\n{table}\n\nCoded word: {data['coded_word']}"


TEXT_SIZE = 32
TEXT_PADDING = TEXT_SIZE
CELL_DIM = TEXT_SIZE + TEXT_PADDING * 2
MID = CELL_DIM * 0.5


def render_image(puzzle):
    data = json.loads(puzzle.text)

    font = ImageFont.truetype(str(TEXT_FONT), TEXT_SIZE)
    img_w = CELL_DIM * len(DIGITS)
    # 4 because 2 rows + blank space + row for coded word
    img_h = CELL_DIM * 4
    image = Image.new("RGB", (img_w, img_h))
    draw = ImageDraw.Draw(image)

    for rownum, row in enumerate(data["rows"]):
        for colnum, char in enumerate(row):
            x = colnum * CELL_DIM
            y = rownum * CELL_DIM
            draw.rectangle([x, y, x + CELL_DIM, y + CELL_DIM])
            draw.text((x + MID, y + MID), char, font=font, anchor="mm")

    coded_word = data["coded_word"]
    bbox = draw.textbbox((0, 0), coded_word, font=font)
    w = bbox[2] - bbox[0]
    draw.text(
        ((img_w - w) / 2, image.height - MID),
        coded_word,
        font=font,
        anchor="mm",
    )

    return image
