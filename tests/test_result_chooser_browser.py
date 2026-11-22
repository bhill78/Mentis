"""The result chooser, driven by keyboard alone in a narrow browser.

What this proves, and why it is a harness rather than the application: the
chooser is mounted into the conversation by the integrator's own patch
(`quiet2/Quiet2.tsx` has one editor for this round), so there is no place in
the running app to drive it from yet. `apps/fluid-web/tests/fixtures/
results-harness` mounts the real component over the frozen Magnet fixture
with a host that records what it was asked to open. No Brain, no Mentis
server, no MARS: a static directory and Chromium.

Build it first, from `apps/fluid-web`::

    npx vite build --config tests/fixtures/results-harness/vite.config.ts

then opt in with ``MENTIS_QUIET_BROWSER=1``. It needs Playwright and its
Chromium, which is the browser the owner reads this interface in.

The checks are the handoff's F1/F2 and V5 at a phone width:

  * a reader who never touches a pointer can open the chooser, walk it, and
    choose one of #88's exact files -- by its own reference, not by position;
  * when later review rounds fill the compact page, #88 is still reached
    through "All results", and the file chosen is still the exact one;
  * a result that cannot be opened stays on the list, says why in its own
    words, and choosing it does nothing;
  * at 360px nothing is clipped and the focused row shows a visible ring.
"""
from __future__ import annotations

import functools
import http.server
import os
import socket
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the chooser harness",
)

HARNESS = Path(__file__).parents[1] / "apps/fluid-web/dist/results-harness"

#: #88's three files, exactly as the navigation review named them.
GEN3 = ("adm-667a23eb07a8", "adm-a43714dc1b5b", "adm-cf3b99ac05cd")

#: The phone width the owner's checks use, and one step narrower than 390.
NARROW = {"width": 360, "height": 780}


@pytest.fixture(scope="module")
def harness() -> str:
    """The built harness, served from a loopback port of its own."""
    if not (HARNESS / "index.html").exists():
        pytest.skip(f"build the harness first: {HARNESS} has no index.html")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HARNESS))
    with socket.socket() as probe:  # a port nobody else is holding
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/index.html"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


FOCUSED = """() => {
  const el = document.activeElement
  if (!el) return null
  const cs = getComputedStyle(el)
  const box = el.getBoundingClientRect()
  return {
    role: el.getAttribute('role'),
    label: el.getAttribute('aria-label'),
    disabled: el.getAttribute('aria-disabled'),
    text: (el.textContent || '').replace(/\\s+/g, ' ').trim(),
    ring: cs.boxShadow + ' ' + cs.outline + ' ' + cs.outlineWidth,
    clipped: el.scrollWidth > el.clientWidth + 1 || box.right > window.innerWidth + 1,
    height: Math.round(box.height),
  }
}"""


def _tab_to(page, label_part: str, limit: int = 40) -> dict:
    """Tab until the focused control's label holds `label_part`."""
    for _ in range(limit):
        page.keyboard.press("Tab")
        got = page.evaluate(FOCUSED)
        if got and (got["label"] or "") and label_part in got["label"]:
            return got
    raise AssertionError(f"Tab never reached a control labelled with {label_part!r}")


def _arrow_to(page, needle: str, limit: int = 60) -> dict:
    """ArrowDown until the focused row's words hold `needle`."""
    got = page.evaluate(FOCUSED)
    if got and needle in (got["text"] or ""):
        return got
    for _ in range(limit):
        page.keyboard.press("ArrowDown")
        got = page.evaluate(FOCUSED)
        if got and needle in (got["text"] or ""):
            return got
    raise AssertionError(f"ArrowDown never reached a row holding {needle!r}")


@pytest.fixture
def page(harness):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport=NARROW)
            # The harness is static: no API, so no network idle to wait for.
            page.goto(harness, wait_until="load")
            page.wait_for_selector("[data-scenario='f1'] .q2r-entry")
            yield page
        finally:
            browser.close()


def test_keyboard_alone_chooses_an_exact_file_of_88(page):
    """F1: the compact chooser, walked and chosen without a pointer."""
    entry = _tab_to(page, "Results of Yellow Quiet Magnet")
    assert entry["height"] >= 28, f"the entry control is only {entry['height']}px high"
    page.keyboard.press("Enter")
    page.wait_for_selector(".q2r-chooser")

    first = page.evaluate(FOCUSED)
    assert first["role"] == "menuitem", f"opening it puts focus on a row, not {first['role']!r}"

    row = _arrow_to(page, "g3a-yellow-puck.png")
    assert row["disabled"] is None, "a held file is offered, not disabled"
    assert not row["clipped"], "the row is clipped at 360px"
    assert row["ring"].strip() not in ("none none 0px", ""), "the focused row shows no visible ring"
    page.keyboard.press("Enter")

    chosen = page.evaluate("() => window.__chosen")
    assert [c["ref"] for c in chosen] == [GEN3[0]], f"the exact file was not chosen: {chosen}"
    assert chosen[0]["group"] == "grp-88", "and it came from #88's own group"
    # Choosing closes the chooser and gives focus back to the control. The
    # control takes it back on the next frame, so this waits for it rather
    # than reading the focus once and racing that frame.
    page.wait_for_selector(".q2r-chooser", state="detached")
    page.wait_for_function(
        "() => (document.activeElement?.getAttribute('aria-label') || '')"
        ".includes('Results of Yellow Quiet Magnet')")


def test_unavailable_result_stays_listed_and_does_nothing(page):
    """A purged return keeps its place, says why, and cannot be chosen."""
    _tab_to(page, "Results of Yellow Quiet Magnet")
    page.keyboard.press("Enter")
    page.wait_for_selector(".q2r-chooser")
    row = _arrow_to(page, "early-sketch.png")
    assert row["disabled"] == "true", "a purged result is marked as not openable"
    assert "purged" in row["text"], f"its reason is not in the row's own words: {row['text']!r}"
    page.keyboard.press("Enter")
    assert page.evaluate("() => window.__chosen.length") == 0, "a purged result must not be opened"
    assert page.is_visible(".q2r-chooser"), "and the chooser stays open"


def test_all_results_reaches_88_when_later_rounds_fill_the_page(page):
    """F2: the compact page is later review rounds; #88 is still reachable."""
    page.keyboard.press("Escape")
    entry = _tab_to(page, "Results of Yellow Quiet Magnet")
    # the second scenario's control: walk on until the F2 section's own entry
    while "q2r-entry" in page.evaluate("() => document.activeElement.className") and \
            not page.evaluate("() => !!document.activeElement.closest(\"[data-scenario='f2']\")"):
        page.keyboard.press("Tab")
    assert page.evaluate("() => !!document.activeElement.closest(\"[data-scenario='f2']\")"), entry
    page.keyboard.press("Enter")
    page.wait_for_selector("[data-scenario='f2'] .q2r-chooser")

    listed = page.inner_text("[data-scenario='f2'] .q2r-chooser")
    assert "g3a-yellow-puck.png" not in listed, "the fixture's first page should not hold #88"
    assert "8 of 13 result groups" in listed, f"the bound is not stated: {listed[:200]!r}"

    _arrow_to(page, "All results")
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.querySelector(\"[data-scenario='f2'] .q2r-chooser\").innerText.includes('g3a-yellow-puck.png')")

    row = _arrow_to(page, "gen3-comparison.html")
    assert not row["clipped"], "the older group's row is clipped at 360px"
    page.keyboard.press("Enter")
    chosen = page.evaluate("() => window.__chosen")
    assert [c["ref"] for c in chosen] == [GEN3[2]], f"the exact older file was not chosen: {chosen}"


def test_without_a_host_results_are_listed_and_not_offered(page):
    """A host with no opener lists everything and pretends nothing."""
    page.keyboard.press("Escape")
    while not page.evaluate("() => !!document.activeElement.closest(\"[data-scenario='nohost']\")"):
        page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    page.wait_for_selector("[data-scenario='nohost'] .q2r-chooser")
    listed = page.inner_text("[data-scenario='nohost'] .q2r-chooser")
    assert "opening them needs the conversation view" in listed
    assert "g3a-yellow-puck.png" in listed, "the results are still all listed"
    assert "All results:" not in listed, "no paging is offered that it cannot do"
    assert page.evaluate("() => window.__chosen.length") == 0
