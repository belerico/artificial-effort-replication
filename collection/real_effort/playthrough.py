#!/usr/bin/env python3
"""
End-to-end playthrough of a real_effort oTree session, driven with Playwright.

Verifies the whole participant flow runs without getting stuck: the intro page
(email entry), every game's puzzles, and the Results / End pages, through to
the end of the session. Works against a local devserver or a deployed server.
This is the complete script whose core is Listing 1 of the paper (Appendix
"End-to-End Automation"); --llm is the mode shown there.

Answer modes (choose one):
  (default)  answer every puzzle with "1" (wrong) — a pure flow test.
  --solve    answer correctly: ask the server for each solution via the DEBUG
             'cheat' live-message. Devserver only (DEBUG on). Checks scoring.
  --llm      solve each puzzle with an LLM through OpenRouter: the bot reads the
             puzzle image off the page, sends it to the model, and types the
             model's answer. Needs OPENROUTER_API_KEY (.env or env). Costs API
             credits — each puzzle is one model call.

Options:
  --model NAME    LLM model for --llm mode (default: google/gemini-2.5-flash).
  --max-puzzles N stop after N puzzles (handy for a cheap --llm smoke test).

Requirements: `uv sync --group collection` at the repository root, and Google
Chrome (the browser is launched with Playwright's "chrome" channel; if Chrome
is not installed, `uv run playwright install chrome` installs it).

Usage (from collection/real_effort):
    uv run otree devserver                          # in another terminal
    uv run otree create_session real_effort_day1 1
    CODE=$(sqlite3 db.sqlite3 "SELECT code FROM otree_participant ORDER BY id DESC LIMIT 1")
    URL="http://localhost:8000/InitializeParticipant/$CODE"
    uv run python playthrough.py "$URL"
    uv run python playthrough.py "$URL" --solve
    uv run python playthrough.py "$URL" --llm --model google/gemini-2.5-flash

Exit code 0 = the flow completed with no errors; 1 = it got stuck or errored.
"""

import os
import re
import sys

from playwright.sync_api import sync_playwright

EMAIL = "playthrough-bot@example.com"
WRONG_ANSWER = "1"
DEFAULT_MODEL = "google/gemini-2.5-flash"
MAX_STEPS = 3000

# JS: true once the answer input exists and is non-empty (cheat has filled it).
_INPUT_FILLED = (
    "() => { const e = document.querySelector('#answer-inp');"
    " return !!e && e.value !== ''; }"
)


def make_llm_client():
    """OpenAI SDK client pointed at OpenRouter (used only for --llm mode)."""
    from openai import OpenAI

    try:
        from dotenv import load_dotenv

        load_dotenv()  # picks up the repo-root .env
    except ImportError:
        pass
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("error: OPENROUTER_API_KEY is not set (.env or environment)")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)


def llm_answer(client, model, page) -> str:
    """Ask an LLM to solve the puzzle currently shown on the page."""
    instructions = (page.text_content(".card") or "").strip()
    img = page.get_attribute("#captcha-img", "src") or ""
    prompt = (
        "You are a participant in an experiment, solving a puzzle.\n"
        f"Task instructions: {instructions}\n\n"
        "Study the puzzle and reply with ONLY the answer — no explanation, "
        "just the answer value, formatted exactly as the task asks."
    )
    content = [{"type": "text", "text": prompt}]
    if img.startswith("data:image"):
        content.append({"type": "image_url", "image_url": {"url": img}})
    else:  # text-only puzzle — include the visible puzzle text
        content[0]["text"] += "\n\n" + " ".join(
            (page.text_content(".task-wrapper") or "").split()
        )
    resp = client.chat.completions.create(
        model=model,
        max_tokens=800,
        messages=[{"role": "user", "content": content}],
    )
    out = (resp.choices[0].message.content or "").strip()
    low = out.lower()
    if "answer:" in low:  # tolerate "Answer: <x>" formatting
        out = out[low.rfind("answer:") + len("answer:") :].strip()
    return out.splitlines()[0].strip() if out else ""


def run(start_url, mode="flow", model=DEFAULT_MODEL, max_puzzles=0) -> bool:
    client = make_llm_client() if mode == "llm" else None
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(start_url, wait_until="load")
        puzzles = 0
        games: list[str] = []

        for step in range(MAX_STEPS):
            page.wait_for_timeout(300)

            # Intro page: fill the email once.
            email = page.query_selector("#id_email")
            if email and email.input_value() == "":
                email.fill(EMAIL)

            # Game page: answer one puzzle.
            if page.query_selector("#answer-inp") and page.query_selector(
                "#submit-btn"
            ):
                m = re.search(r"/p/[^/]+/([^/]+)/Game", page.url)
                game = m.group(1) if m else "?"
                if not games or games[-1] != game:
                    games.append(game)
                try:
                    if mode == "llm":
                        try:
                            ans = llm_answer(client, model, page)
                        except Exception as e:
                            print(f"  LLM call failed: {e}")
                            errors.append(f"llm error: {e}")
                            ans = ""
                        page.fill("#answer-inp", ans or "0", timeout=15000)
                        if page.input_value("#answer-inp").strip() == "":
                            page.fill("#answer-inp", "0")  # field rejected the answer
                    elif mode == "solve":
                        # DEBUG-only: server returns the solution, cheat() fills the input.
                        page.evaluate("liveSend({type: 'cheat'})")
                        page.wait_for_function(_INPUT_FILLED, timeout=8000)
                    else:
                        page.fill("#answer-inp", WRONG_ANSWER, timeout=15000)
                    page.click("#submit-btn", timeout=15000)
                except Exception as e:
                    print(f"!! STUCK on a puzzle in '{game}': {e}")
                    errors.append(f"stuck in {game}")
                    break
                puzzles += 1
                if max_puzzles and puzzles >= max_puzzles:
                    print(f"stopping after --max-puzzles {max_puzzles}")
                    break
                page.wait_for_timeout(1800)
                continue

            # Intro / Results / End page: click the next button.
            nxt = page.query_selector(".otree-btn-next")
            if nxt:
                nxt.click()
                page.wait_for_load_state("load")
                continue

            # Nothing actionable — may be mid-navigation; confirm before stopping.
            page.wait_for_timeout(1500)
            if page.query_selector("#answer-inp") or page.query_selector(
                ".otree-btn-next"
            ):
                continue
            final = " ".join((page.text_content("body") or "").split())[:100]
            print(f"reached the final page after {step} steps")
            print(f"final page: {final!r}")
            break
        else:
            print("!! MAX_STEPS reached — flow did not complete")
            errors.append("did not finish")

        label = {
            "flow": "flow (wrong answers)",
            "solve": "solve (cheat / correct answers)",
            "llm": f"llm via OpenRouter ({model})",
        }[mode]
        print(f"mode:             {label}")
        print(f"games played:     {games}")
        print(f"puzzles answered: {puzzles}")
        print(f"errors:           {errors if errors else 'none'}")
        browser.close()
        return not errors


if __name__ == "__main__":
    args = sys.argv[1:]
    url = None
    mode = "flow"
    model = DEFAULT_MODEL
    max_puzzles = 0
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--solve":
            mode = "solve"
        elif a == "--llm":
            mode = "llm"
        elif a == "--model":
            i += 1
            model = args[i]
        elif a == "--max-puzzles":
            i += 1
            max_puzzles = int(args[i])
        elif not a.startswith("--"):
            url = a
        i += 1
    if not url:
        sys.exit(
            "usage: python playthrough.py <participant URL> "
            "[--solve | --llm [--model M]] [--max-puzzles N]"
        )
    sys.exit(0 if run(url, mode=mode, model=model, max_puzzles=max_puzzles) else 1)
