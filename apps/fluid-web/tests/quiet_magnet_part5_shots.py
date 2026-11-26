"""Part 5's screenshots: information presented by what it represents.

Headless Chromium over `quiet_magnet_part5_harness.tsx`, on this checkout's own
dev server. It photographs the states the owner will judge:

  01-summary-synthesis.png  the Python synthesis as statements, each with the
                            collected records it was written from as presses,
                            and the dated material drawn as a table
  02-summary-briefing.png   an answer written as a document, drawn as prose by
                            `Prose`: heading, paragraphs, emphasis and a table
  03-summary-unanswered.png no answer recorded: the lead is what the material
                            NAMES, and no count is above the fold
  04-record-as-prose.png    one collected record opened: its headline a
                            heading, its address a link, its words prose
  05-summary-briefing-multi.png  the same document recorded across several
                            entries -- a paragraph cut off mid-sentence and
                            continued in the next, a table whose entries hold
                            one row, two rows, and a row with the sentence that
                            closes the table, an ordered list with one entry per
                            item and one entry that finishes an item and starts
                            the next -- each still naming only the record it
                            cites, and each citation naming WHICH RECORDED PART
                            it is and the row or item that part produced
                            (corrections for reviews `ent-19c3c55af28c`,
                            `ent-c0f9cca287b7` and `ent-7ca49dfd8393`)

It asserts nothing about behaviour -- `quiet_magnet_presentation_unit.ts` does
that. It fails loudly if the page logs an error or the expected words are not on
screen, so a screenshot is never taken of a surface that did not render.
"""
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "part-5-shots"
BASE = "http://127.0.0.1:5465/tests/quiet_magnet_part5.html"


def serve():
    OUT.mkdir(exist_ok=True)
    log = (ROOT / "part-5-shots-vite.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        ["node", "node_modules/vite/bin/vite.js", "--config", "tests/quiet_magnet_part5_vite.mjs"],
        cwd=ROOT, stdout=log, stderr=log,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print(f"dev server pid {proc.pid}")
    for _ in range(120):
        try:
            urllib.request.urlopen(BASE, timeout=1).read()
            return proc
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit("the dev server did not come up")


def main():
    proc = serve()
    problems = []
    try:
        with sync_playwright() as play:
            browser = play.chromium.launch()
            page = browser.new_page(viewport={"width": 900, "height": 1100})
            page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: problems.append(str(e)))

            for name, state, must in [
                ("01-summary-synthesis.png", "synthesis", [
                    "speaks mainly about Roman Space Telescope",
                    "Written from",
                    "What it holds, by date",
                ]),
                ("02-summary-briefing.png", "briefing", [
                    "What launched, and what was found",
                    "Artemis III shortlist narrowed",
                ]),
                ("03-summary-unanswered.png", "unanswered", [
                    "The collected material names",
                    "No answer is recorded for this collection yet",
                ]),
                ("04-record-as-prose.png", "inspect", [
                    "Roman Space Telescope passes its final thermal test",
                    "Open at example.org",
                ]),
                ("05-summary-briefing-multi.png", "briefing-multi", [
                    "What launched, and what was found",
                    "First lunar-Earth assist flown",
                    "Mars gravity assist refined for Europa Clipper",
                    # the two rows recorded in one entry, named as rows
                    "Rows ",
                    "Artemis III shortlist narrowed",
                    # the list item continued by a plain entry, read as one item
                    "cleared to ship to its launch site.",
                    # the occurrence each citation was recorded against, stated
                    # (correction for review `ent-7ca49dfd8393`): the recorded
                    # part, and the drawn rows or items it produced
                    "Part 1, Row 1",
                    "Part 2, Rows 2–3",
                    # the entry that finished one item and started the next, and
                    # the row recorded with the sentence that closes the table
                    "Items 1–2",
                    "Every row above is one collected record",
                ]),
            ]:
                page.goto(f"{BASE}?state={state}")
                for words in must:
                    page.wait_for_function(
                        "(w) => document.body.innerText.includes(w)", arg=words, timeout=15000)
                page.screenshot(path=str(OUT / name), full_page=True)
                print(f"wrote {name}")

            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=30)
    if problems:
        print("the page reported problems:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        raise SystemExit(1)
    print(f"screenshots in {OUT}")


if __name__ == "__main__":
    main()
