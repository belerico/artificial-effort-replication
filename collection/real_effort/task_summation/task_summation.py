from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import random
import json

TEXT_FONT = Path(__file__).parent / "assets" / "FreeSerifBold.otf"

GRID_SIZE = 3
TARGET_SUM = 10.0
TEXT_SIZE = 32
TEXT_PADDING = TEXT_SIZE

INPUT_TYPE = "text"


def input_hint(target_sum=TARGET_SUM):
    ts = f"{target_sum:g}"
    return f"enter the two numbers that sum to {ts} (e.g. 3.7 6.3)"


def generate_puzzle_fields(grid_size=GRID_SIZE, target_sum=TARGET_SUM):
    """Create a grid where exactly two cells sum to *target_sum*.

    Numbers are decimals with one decimal place (0.1 to 9.9).
    The algorithm ensures no other pair in the grid sums to *target_sum*.
    """
    target_int = int(round(target_sum * 10))
    total_cells = grid_size * grid_size
    # Pick answer pair as integers (tenths: 1 .. target_int-1)
    a = random.randint(1, target_int - 1)
    b = target_int - a

    grid_ints = [a, b]

    # Build remaining cells ensuring no new pair sums to target_int
    candidates = list(range(1, target_int))
    random.shuffle(candidates)

    for c in candidates:
        if len(grid_ints) >= total_cells:
            break
        if (target_int - c) in grid_ints:
            continue
        grid_ints.append(c)

    random.shuffle(grid_ints)
    grid = [round(v / 10, 1) for v in grid_ints]

    sol = sorted([round(a / 10, 1), round(b / 10, 1)])
    return dict(
        text=json.dumps(grid),
        solution=json.dumps(sol),
    )


def is_correct(response, puzzle, target_sum=TARGET_SUM):
    try:
        grid = json.loads(puzzle.text)
        parts = response.strip().split()
        if len(parts) != 2:
            return False
        a, b = round(float(parts[0]), 1), round(float(parts[1]), 1)
        if abs(a + b - target_sum) > 0.05:
            return False
        # Check both numbers exist in the grid
        grid_copy = list(grid)
        try:
            grid_copy.remove(a)
            grid_copy.remove(b)
        except ValueError:
            return False
        return True
    except (ValueError, TypeError):
        return False


def render_text(puzzle):
    """Return the grid of decimals as plain text."""
    grid = json.loads(puzzle.text)
    grid_size = int(len(grid) ** 0.5)
    lines = []
    for r in range(grid_size):
        row = grid[r * grid_size : (r + 1) * grid_size]
        lines.append("  ".join(f"{v:.1f}" for v in row))
    return "\n".join(lines)


def render_image(puzzle):
    grid = json.loads(puzzle.text)
    grid_size = int(len(grid) ** 0.5)
    font = ImageFont.truetype(str(TEXT_FONT), TEXT_SIZE)

    cell = TEXT_SIZE + TEXT_PADDING * 2
    mid = cell * 0.5
    margin = 1  # prevent outer border from being clipped
    img_w = cell * grid_size + margin * 2
    img_h = cell * grid_size + margin * 2
    image = Image.new("RGB", (img_w, img_h), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    for idx, val in enumerate(grid):
        row = idx // grid_size
        col = idx % grid_size
        x = margin + col * cell
        y = margin + row * cell
        draw.rectangle([x, y, x + cell, y + cell], outline=(0, 0, 0))
        label = f"{val:.1f}"
        draw.text((x + mid, y + mid), label, font=font, fill=(0, 0, 0), anchor="mm")

    return image
