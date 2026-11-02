"""Row P5's assertions: Fluid opened in headless Chromium, decided, not looked at.

    <fixtures>\\venv\\Scripts\\python.exe tools/r1/browser_check.py <url>

Passes only when, in one load of BRAIN-SEED's Fluid:

1. no uncaught page error fires;
2. no same-origin request fails, at the network, with a status of 400 or more, or as an asset
   answered with the index page, other than those listed exactly in `ALLOWED_FAILED`, which is
   empty. Python answers a missing file with `index.html` and 200, so status alone can't see one;
3. Fluid's own controls are visible by name (`SHELL_BUTTONS`, `SHELL_TEXT`), so a blank or
   wrong page can't pass;
4. the known Conversation is listed in the conversation menu with its post count and, once
   opened, its known post is rendered (`KNOWN_CONVERSATION`, `KNOWN_POSTS`, `KNOWN_POST`).

Console errors are reported and don't decide anything: a failed request or page error is
what decides.

Prints the report as JSON. Exit 0 when all pass, 1 when any fails, 2 when the browser can't
run at all. Row P fails on anything but 0: no browser is a failure, never a skip. The `--fault`
options break the check on purpose, to show that it fails.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse

SHELL_BUTTONS = ("New conversation", "Latest activity", "Search", "Notifications")
SHELL_TEXT = ("Daily Briefing", "Needs you")
KNOWN_CONVERSATION = "R1 known conversation"
KNOWN_POSTS = "3 posts"
KNOWN_POST = "R1 known post: the harbour light is lit at dusk."
#: Same-origin requests allowed to fail, exactly, as (method, path, status). None are.
ALLOWED_FAILED: tuple = ()
WAIT_MS = 15_000


def check(url: str, *, block: str | None = None, known_post: str = KNOWN_POST,
          throw: bool = False) -> dict:
    """`block`, `known_post` and `throw` are the deliberate faults."""
    from playwright.sync_api import TimeoutError as Timeout
    from playwright.sync_api import sync_playwright

    origin = urllib.parse.urlsplit(url).netloc
    page_errors: list[str] = []
    console_errors: list[str] = []
    failed: list[list] = []
    found: dict[str, bool] = {}

    def same_origin(request) -> bool:
        return urllib.parse.urlsplit(request.url).netloc == origin

    def path_of(request) -> str:
        return urllib.parse.urlsplit(request.url).path

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        version = browser.version
        page = browser.new_page()
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console",
                lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("requestfailed", lambda r: failed.append(
            [r.method, path_of(r), r.failure]) if same_origin(r) else None)

        def answered(r) -> None:
            if not same_origin(r.request):
                return
            path = path_of(r.request)
            if r.status >= 400:
                failed.append([r.request.method, path, r.status])
            elif path.startswith("/assets/") and "text/html" in r.headers.get("content-type", ""):
                failed.append([r.request.method, path, "the index page, for an asset"])

        page.on("response", answered)
        if block:
            page.route(lambda u: block in urllib.parse.urlsplit(u).path,
                       lambda route: route.abort())
        if throw:
            page.add_init_script("setTimeout(() => { throw new Error('r1 fault') }, 0)")

        def visible(name: str, locator) -> bool:
            try:
                locator.first.wait_for(state="visible", timeout=WAIT_MS)
                found[name] = True
            except Timeout:
                found[name] = False
            return found[name]

        page.goto(url, wait_until="load", timeout=WAIT_MS)
        for name in SHELL_BUTTONS:
            visible(f"button: {name}", page.get_by_role("button", name=name, exact=True))
        for words in SHELL_TEXT:
            visible(f"text: {words}", page.get_by_text(words, exact=True))
        menu = page.locator("button", has_text="▾").filter(has_text="Home")
        if visible("the conversation menu", menu):
            menu.first.click()
            row = page.get_by_text(KNOWN_CONVERSATION, exact=True)
            if visible(f"listed: {KNOWN_CONVERSATION}", row):
                visible(f"listed: {KNOWN_POSTS}",
                        page.get_by_text(KNOWN_POSTS, exact=False))
                row.first.click()
                visible(f"rendered: {known_post}", page.get_by_text(known_post, exact=True))
        try:
            page.wait_for_load_state("networkidle", timeout=WAIT_MS)
        except Timeout:
            pass
        browser.close()

    unexpected = [f for f in failed if tuple(f) not in ALLOWED_FAILED]
    checks = {
        "no_page_errors": not page_errors,
        "no_failed_same_origin_requests": not unexpected,
        "fluid_controls_and_known_item_visible":
            bool(found) and all(found.values())
            and len(found) == len(SHELL_BUTTONS) + len(SHELL_TEXT) + 4,
    }
    return {
        "url": url,
        "chromium": version,
        "passed": all(checks.values()),
        "checks": checks,
        "found": found,
        "page_errors": page_errors,
        "failed_requests": unexpected,
        "console_errors_reported": console_errors,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="row P5's check of Fluid in a browser")
    ap.add_argument("url")
    ap.add_argument("--fault-block", default=None,
                    help="abort same-origin requests whose path holds this")
    ap.add_argument("--fault-known-post", default=KNOWN_POST,
                    help="look for words the fixture doesn't hold")
    ap.add_argument("--fault-throw", action="store_true", help="throw from the page")
    a = ap.parse_args(argv)
    try:
        report = check(a.url, block=a.fault_block, known_post=a.fault_known_post,
                       throw=a.fault_throw)
    except Exception as exc:  # no browser is a failure of the row, never a skip
        print(json.dumps({"passed": False, "browser_failed": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(report, indent=1))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
