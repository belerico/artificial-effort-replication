from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import random

TEXT_FONT = Path(__file__).parent / "assets" / "FreeSerifBold.otf"

ROWS = 10
COLS = 15
TEXT_SIZE = 24
CHAR_SPACING = 28

INPUT_TYPE = "number"
INPUT_HINT = "count the zeros in the paragraph"


def generate_puzzle_fields(rows=ROWS, cols=COLS, min_zeros=55, max_zeros=85):
    """Create a paragraph of 1s and 0s with a random number of zeros."""
    total = rows * cols
    num_zeros = random.randint(min_zeros, max_zeros)
    chars = ["0"] * num_zeros + ["1"] * (total - num_zeros)
    random.shuffle(chars)

    row_list = []
    for r in range(rows):
        row = "".join(chars[r * cols : (r + 1) * cols])
        row_list.append(row)
    text = "\n".join(row_list)

    return dict(text=text, solution=str(num_zeros))


def is_correct(response, puzzle):
    return puzzle.solution == response


def render_text(puzzle):
    """Return the puzzle grid as plain text (rows of 0s and 1s)."""
    return puzzle.text


def render_image(puzzle):
    font = ImageFont.truetype(str(TEXT_FONT), TEXT_SIZE)
    lines = puzzle.text.split("\n")
    num_rows = len(lines)
    num_cols = len(lines[0]) if lines else COLS
    pad_x = 16
    pad_y = 12
    img_w = CHAR_SPACING * num_cols + pad_x * 2
    img_h = CHAR_SPACING * num_rows + pad_y * 2
    image = Image.new("RGB", (img_w, img_h), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    mid = CHAR_SPACING * 0.5
    for rownum, row in enumerate(puzzle.text.split("\n")):
        for colnum, char in enumerate(row):
            x = pad_x + colnum * CHAR_SPACING + mid
            y = pad_y + rownum * CHAR_SPACING + mid
            draw.text((x, y), char, font=font, fill=(0, 0, 0), anchor="mm")

    return image
