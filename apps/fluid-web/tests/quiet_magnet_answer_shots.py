"""Part F's screenshots: the Summary tab and the Perspectives panel with a real
recorded answer, on this checkout's own dev server.

Headless Chromium over `quiet_magnet_answer_harness.tsx`. It photographs the
four states the owner will judge: the Summary led by the evolving summary with
what it was grounded in beside it, the same Summary with "What changed" opened
on the difference between the current answer and the one it superseded, the
Perspectives panel showing the answer standing now with its earlier answers
kept under it, and -- driven only here, because the product refuses it for a
synthesis -- the same answer with Part A's `explored_outside` true, so the
rendered distinction can be seen.

It asserts nothing about behaviour: the unit files do that. It fails loudly if
the page logs an error or the expected words are not on screen, so a screenshot
is never taken of a surface that did not render.
"""
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "part-f-shots"
BASE = "http://127.0.0.1:5459/tests/quiet_magnet_answer.html"


def serve():
    OUT.mkdir(exist_ok=True)
    log = (ROOT / "part-f-shots-vite.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        ["node", "node_modules/vite/bin/vite.js", "--config", "tests/quiet_magnet_answer_vite.mjs"],
        cwd=ROOT, stdout=log, stderr=log,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(120):
        try:
            urllib.request.urlopen(BASE, timeout=1).read()
            return proc
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit("the dev server did not come up")


def shoot(page, name, must):
    for words in must:
        page.wait_for_function(
            "(w) => document.body.innerText.includes(w)", arg=words, timeout=15000)
    page.screenshot(path=str(OUT / name), full_page=True)
    print(f"wrote {name}")


def main():
    proc = serve()
    problems = []
    try:
        with sync_playwright() as play:
            browser = play.chromium.launch()
            page = browser.new_page(viewport={"width": 900, "height": 1200})
            page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: problems.append(str(e)))

            page.goto(BASE)
            shoot(page, "01-summary-answer.png", [
                "This Magnet has gathered 4 records from 2 sources",
                "arrived in this collection",
                "GROUNDED IN THIS COLLECTION",
                "Answer again from this collection",
            ])

            # "What changed" opens itself once there is a difference to show,
            # so this opens every disclosure rather than pressing one (which
            # would shut it) and photographs the whole surface.
            page.evaluate("document.querySelectorAll('details').forEach((d) => { d.open = true })")
            shoot(page, "02-summary-what-changed.png", ["new statements", "Now says", "No longer says"])

            page.goto(BASE + "?tab=Perspectives")
            shoot(page, "03-perspectives-answer.png", [
                "What is the state of what this Magnet has gathered?",
                "GROUNDED IN THIS COLLECTION",
                "Earlier answers",
                "Discuss this in the Conversation",
            ])

            page.goto(BASE + "?outside=1")
            shoot(page, "04-summary-explored-outside.png", ["EXPLORED OUTSIDE THIS COLLECTION"])
            browser.close()
    finally:
        proc.terminate()
    if problems:
        print("PAGE PROBLEMS:", *problems, sep="\n  ")
        return 1
    print("no page errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
