"""String entry task: type 9-character strings made of special characters.

Based on the real-effort task from Niederle & Vesterlund (2007) / Gill & Prowse
(2012). Characters are drawn from: / \\ ) ( _ < and space.
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEXT_FONT = Path(__file__).parent / "assets" / "FreeSansBold.otf"

CHARSET = r"/\)(_ <"
LENGTH = 9
TEXT_SIZE = 36
CHAR_SPACING = 32

INPUT_TYPE = "text"
INPUT_HINT = "type the characters shown above"


def generate_puzzle_fields(length: int = LENGTH, charset: str = CHARSET) -> dict:
    """Generate a random string of special characters."""
    text = "".join(random.choice(charset) for _ in range(length))
    return dict(text=text, solution=text)


def _normalize_spaces(s: str) -> str:
    """Treat space, underscore, and ␣ (open box) as equivalent."""
    return s.replace("\u2423", " ").replace("_", " ")


def _normalize_backslash(s: str) -> str:
    """Collapse escaped backslashes (\\\\) to single backslash (\\)."""
    return s.replace("\\\\", "\\")


def is_correct(response: str, puzzle) -> bool:
    """Match with lenient space and backslash handling.

    Spaces, underscores, and ␣ (U+2423 open box) are treated as equivalent,
    because the image renders spaces as ␣ and models frequently output _ or ␣
    instead of a literal space character.

    Double backslashes (\\\\) are collapsed to single backslash (\\),
    because models often escape backslashes in their output.
    """
    r = _normalize_backslash(_normalize_spaces(response))
    s = _normalize_backslash(_normalize_spaces(puzzle.solution))
    return r == s


def render_text(puzzle) -> str:
    """Return the string with spaces shown as [SPACE] for clarity."""
    return "".join("[SPACE]" if ch == " " else ch for ch in puzzle.text)


def render_image(puzzle) -> Image.Image:
    """Render the string as a clear, monospaced image.

    Each character is drawn in its own cell so that spaces are visible
    (rendered as a visible blank between vertical dividers).
    """
    text = puzzle.text
    n = len(text)

    try:
        font = ImageFont.truetype(str(TEXT_FONT), TEXT_SIZE)
    except OSError:
        font = ImageFont.load_default()

    cell_w = CHAR_SPACING + 8
    pad_x = 20
    pad_y = 16
    img_w = cell_w * n + pad_x * 2
    img_h = TEXT_SIZE + pad_y * 2 + 16

    image = Image.new("RGB", (img_w, img_h), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Draw each character in its own cell
    for i, ch in enumerate(text):
        cx = pad_x + i * cell_w + cell_w // 2
        cy = img_h // 2

        # Light cell background to show boundaries
        x0 = pad_x + i * cell_w + 1
        x1 = x0 + cell_w - 2
        y0 = pad_y
        y1 = img_h - pad_y
        draw.rectangle([x0, y0, x1, y1], fill=(245, 245, 245), outline=(200, 200, 200))

        # Draw the character (space rendered as ␣ symbol)
        if ch == " ":
            draw.text((cx, cy), "\u2423", font=font, fill=(150, 150, 150), anchor="mm")
        else:
            draw.text((cx, cy), ch, font=font, fill=(0, 0, 0), anchor="mm")

    return image
