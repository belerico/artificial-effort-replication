import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sudoku import Sudoku

TEXT_FONT = Path(__file__).parent / "assets" / "FreeSerifBold.otf"

GRID_SIZE = 6
BOX_ROWS = 2
BOX_COLS = 3

TEXT_SIZE = 36
CELL_SIZE = 60
THICK_LINE = 3
THIN_LINE = 1
MARGIN = 10

INPUT_TYPE = "text"
INPUT_HINT = "enter missing numbers in reading order, space-separated"


def generate_puzzle_fields(difficulty=0.2):
    """Create a new 6x6 Sudoku puzzle.

    Returns dict with:
        text: JSON string of the puzzle grid (None for blanks)
        solution: space-separated missing numbers in reading order
    """
    # py-sudoku's Sudoku(width, height): width = box columns, height = box rows.
    # Must match the box borders drawn by render_image() — 3 columns x 2 rows.
    puzzle = Sudoku(
        width=BOX_COLS, height=BOX_ROWS, seed=random.randint(0, 2**31 - 1)
    ).difficulty(difficulty)
    solution_obj = puzzle.solve()
    solution_board = solution_obj.board

    # puzzle.board has None for blanks
    puzzle_board = puzzle.board

    # Collect missing numbers in reading order (left-to-right, top-to-bottom)
    missing = []
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if puzzle_board[r][c] is None:
                missing.append(str(int(solution_board[r][c])))

    return dict(
        text=json.dumps(puzzle_board),
        solution=" ".join(missing),
    )


def is_correct(response, puzzle):
    """Check if the response matches the solution."""
    # Normalize whitespace
    response_normalized = " ".join(response.strip().split())
    return response_normalized == puzzle.solution


def render_text(puzzle):
    """Alias for render_grid_text — used by the text-only benchmark mode."""
    return render_grid_text(puzzle)


def render_grid_text(puzzle):
    """Render the puzzle grid as a text string for bots to read.

    Format:
        . 2 . | 4 . 6
        4 . 6 | . 2 .
        ------+------
        . 4 . | 6 . 2
        6 . 2 | . 4 .
        ------+------
        . 6 . | 2 . 4
        2 . 4 | . 6 .
    """
    board = json.loads(puzzle.text)
    lines = []
    for r in range(GRID_SIZE):
        cells = []
        for c in range(GRID_SIZE):
            val = board[r][c]
            cells.append(str(int(val)) if val is not None else ".")
            if c == BOX_COLS - 1 and c < GRID_SIZE - 1:
                cells.append("|")
        lines.append(" ".join(cells))
        if (r + 1) % BOX_ROWS == 0 and r < GRID_SIZE - 1:
            sep = "-" * (BOX_COLS * 2 - 1)
            lines.append("+".join([sep] * (GRID_SIZE // BOX_COLS)))
    return "\n".join(lines)


def render_image(puzzle):
    """Draw the 6x6 Sudoku grid as a PIL Image."""
    board = json.loads(puzzle.text)
    font = ImageFont.truetype(str(TEXT_FONT), TEXT_SIZE)

    grid_px = CELL_SIZE * GRID_SIZE + MARGIN * 2
    image = Image.new("RGB", (grid_px, grid_px), "white")
    draw = ImageDraw.Draw(image)

    # Draw cells and numbers
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            x = MARGIN + c * CELL_SIZE
            y = MARGIN + r * CELL_SIZE
            val = board[r][c]
            if val is not None:
                cx = x + CELL_SIZE / 2
                cy = y + CELL_SIZE / 2
                draw.text((cx, cy), str(int(val)), fill="black", font=font, anchor="mm")

    # Draw thin grid lines
    for i in range(GRID_SIZE + 1):
        x = MARGIN + i * CELL_SIZE
        draw.line(
            [(x, MARGIN), (x, MARGIN + GRID_SIZE * CELL_SIZE)], fill="black", width=THIN_LINE
        )
    for i in range(GRID_SIZE + 1):
        y = MARGIN + i * CELL_SIZE
        draw.line(
            [(MARGIN, y), (MARGIN + GRID_SIZE * CELL_SIZE, y)], fill="black", width=THIN_LINE
        )

    # Draw thick box borders
    for i in range(GRID_SIZE // BOX_COLS + 1):
        x = MARGIN + i * BOX_COLS * CELL_SIZE
        draw.line(
            [(x, MARGIN), (x, MARGIN + GRID_SIZE * CELL_SIZE)], fill="black", width=THICK_LINE
        )
    for i in range(GRID_SIZE // BOX_ROWS + 1):
        y = MARGIN + i * BOX_ROWS * CELL_SIZE
        draw.line(
            [(MARGIN, y), (MARGIN + GRID_SIZE * CELL_SIZE, y)], fill="black", width=THICK_LINE
        )

    return image
