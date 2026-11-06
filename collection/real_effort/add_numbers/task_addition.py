import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEXT_FONT = Path(__file__).parent / "assets" / "FreeSerifBold.otf"
TEXT_SIZE = 40

INPUT_TYPE = "number"
INPUT_HINT = "enter the sum of the numbers"


def input_hint(num_addends=5):
    return f"enter the sum of the {num_addends} numbers"


def generate_puzzle_fields(num_addends=5, min_num=10, max_num=99):
    """Create a new addition puzzle: sum of `num_addends` random numbers."""
    numbers = [random.randint(min_num, max_num) for _ in range(num_addends)]
    return dict(text=json.dumps(numbers), solution=str(sum(numbers)))


def is_correct(response, puzzle):
    try:
        return int(response) == int(puzzle.solution)
    except (ValueError, TypeError):
        return False


def render_text(puzzle):
    """Return the addition expression as plain text."""
    numbers = json.loads(puzzle.text)
    return " + ".join(str(n) for n in numbers) + " = ___"


def render_image(puzzle):
    """Render a horizontal expression like '21 + 47 + 83 + 15 + 66 = ___'."""
    numbers = json.loads(puzzle.text)
    expression = " + ".join(str(n) for n in numbers) + " = ___"

    font = ImageFont.truetype(str(TEXT_FONT), TEXT_SIZE)
    bbox = font.getbbox(expression)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    padding = 20
    img_w = text_w + padding * 2
    img_h = text_h + padding * 2

    image = Image.new("RGB", (img_w, img_h), "white")
    draw = ImageDraw.Draw(image)
    draw.text((padding - bbox[0], padding - bbox[1]), expression, fill="black", font=font)

    return image
