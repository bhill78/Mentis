"""Screenshots of the answer as it is read, over TEST's own frozen words.

Owner `ent-bce57ba67f38`. Headless Chromium over
`quiet_magnet_answer_read_harness.tsx`, whose fixture is the reply Turn the
running TEST candidate holds for the owner's astronomy Magnet. Four pictures:

  before-perspectives-as-recorded  the reading this build replaced, on the
                                   same words -- the preamble in the lead, the
                                   fused sentences, the raw citation tokens
  after-summary                    the Summary tab as it reads now
  after-perspectives               the Perspectives tab as it reads now
  after-summary-sources            the Sources list under the answer

It asserts nothing about behaviour: the unit files do that. It fails loudly if
the page logs an error, so a screenshot is never taken of a surface that did
not render.
"""
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "answer-read-shots"
BASE = "http://127.0.0.1:5471/tests/quiet_magnet_answer_read.html"


def serve():
    OUT.mkdir(exist_ok=True)
    log = (ROOT / "answer-read-shots-vite.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        ["node", "node_modules/vite/bin/vite.js", "--config",
         "tests/quiet_magnet_answer_read_vite.mjs"],
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


def main():
    proc = serve()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1040, "height": 1500},
                                    device_scale_factor=2)
            problems = []
            page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: problems.append(str(e)))

            def shot(name, url, press=None, wait=None):
                page.goto(url, wait_until="load")
                page.wait_for_timeout(700)
                if press:
                    page.click(press)
                    page.wait_for_timeout(500)
                if wait:
                    page.wait_for_selector(wait, timeout=10000)
                page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
                if problems:
                    raise SystemExit(f"{name}: the page logged {problems}")
                print("wrote", OUT / f"{name}.png")

            shot("before-perspectives-as-recorded", f"{BASE}?as=recorded")
            shot("after-summary", BASE)
            shot("after-perspectives", BASE, press="#shot-perspectives")

            # THE STANDING QUESTION SURVIVES A REFRESH OF ITS ANSWER. "Read
            # this question again" is `store.recheck()`, which re-reads and
            # writes nothing; the wording on screen must be the same wording
            # after it as before, and no POST may have been made.
            page.goto(BASE, wait_until="load")
            page.wait_for_timeout(700)
            page.click("#shot-perspectives")
            page.wait_for_timeout(400)
            posts = page.evaluate("""() => { window.__posts = []; const f = window.fetch;
                window.fetch = (i, o = {}) => { if ((o.method || 'GET') !== 'GET') window.__posts.push(String(i)); return f(i, o); };
                return true }""")
            asked = page.inner_text(".q2p-asked")
            # `Read this question again` is one of the presses that act on the
            # answer rather than read it, so it now lives behind
            # `About this answer ▾` (owner `ent-15a36a065eb8`: secondary
            # actions through progressive disclosure). Open the disclosure
            # first; the press, its guard and what it does are unchanged.
            page.click(".q2p-about > summary")
            page.wait_for_timeout(300)
            page.click("text=Read this question again")
            page.wait_for_timeout(1200)
            again = page.inner_text(".q2p-asked")
            wrote = page.evaluate("() => window.__posts")
            if asked != again:
                raise SystemExit(f"the standing question changed on refresh: {asked!r} -> {again!r}")
            if wrote:
                raise SystemExit(f"a refresh wrote: {wrote}")
            print("standing question unchanged on refresh:", repr(asked))
            print("writes during refresh:", wrote)
            page.screenshot(path=str(OUT / "after-perspectives-refreshed.png"), full_page=True)
            print("wrote", OUT / "after-perspectives-refreshed.png")
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=30)


if __name__ == "__main__":
    sys.exit(main())
