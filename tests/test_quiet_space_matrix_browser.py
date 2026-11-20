"""The responsive and navigation matrix the owner asked to be verified.

Owner request ent-af6b8ce6355f, §6 ("Responsive layout and performance") and
§8 ("Verification"), on the integrated candidate. The seam itself -- that the
host draws Part A's graph at all, that placement costs no read, and that a
choice moves the eye on both surfaces -- is already proved by
`test_quiet_brain_space_browser.py` and is NOT repeated here. What is here is
everything that was left to the release verification:

  the room            a wide column, a 220-300px narrow one, maximised, and
                      the whole window, with the floating controls reachable
                      and inside the COLUMN rather than the window
  resizing            the divider dragged by hand and stepped by key
  a second surface    a working surface beside the graph, each keeping what it
                      holds
  themes              light, the system's dark, and a chosen dark
  a phone             390px, where the graph has no column to open into
  the view            the camera and the filters through a move, a maximise and
                      a reading, measured as pixels and as the controls' own
                      state; the record's clock paused while parked
  reading             a record, an entry, a Turn and a Conversation opened from
                      the graph, the way back, and the browser's Back/Forward
  families            which reader each kind of node actually opens (§4)
  nothing written     every request the page made, and the record before and
                      after: same origin, no write, no agent dispatched

Disposable fixture Brain only (tests._loop.world): no live Brain, no
development server, no MARS. Build apps/fluid-web first and opt in with
MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

import pytest

from tests._loop import _written, world  # noqa: F401
from tests.test_quiet_brain_space_browser import (
    ADVANCE_S,
    NOT_WIRED,
    OPENING,
    _a_brain_worth_drawing,
    _advances_possible,
    _open_the_graph,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

DIST = Path(__file__).parents[1] / "apps/fluid-web/dist/index.html"

#: the least a working column may be dragged to (Quiet2.tsx MIN.s1)
COLUMN_MIN = 220
#: one flight of the eye, and a little for the frames around it
LANDED_S = 0.72


# ── what a browser can see of the view ──────────────────────────────────────
#
# THE CAMERA IS NOT PUBLISHED ANYWHERE, so held-camera equality is measured
# where it shows: the canvas is painted deterministically from the eye and the
# settled read, so the SAME eye at the SAME size paints the same pixels.
# Compared only at equal canvas sizes, and only with nothing chosen -- a
# selection animates its strands, and a moving picture proves nothing.

CANVAS_DIGEST = """
() => {
  const c = document.querySelector('.space-canvas')
  const g = c.getContext('2d')
  const d = g.getImageData(0, 0, c.width, c.height).data
  let h = 2166136261
  for (let i = 0; i < d.length; i += 16) {
    h ^= (d[i] + d[i + 1] * 3 + d[i + 2] * 7 + d[i + 3] * 11) & 0xffffffff
    h = (h * 16777619) >>> 0
  }
  return [c.width, c.height, h]
}
"""

LIT = """
() => {
  const c = document.querySelector('.space-canvas')
  const g = c.getContext('2d')
  const d = g.getImageData(0, 0, c.width, c.height).data
  let n = 0
  for (let i = 0; i < d.length; i += 16) if (d[i + 3] > 8) n++
  return n
}
"""


def _digest(page):
    """[canvas width, canvas height, a digest of its pixels]."""
    return page.evaluate(CANVAS_DIGEST)


def _drawn(page) -> int:
    return int(page.locator(".space-field").get_attribute("data-drawn") or 0)


def _still(page, timeout: int = 4000) -> None:
    """Wait until nothing in the field is animating, so pixels can be compared."""
    page.wait_for_function(
        "() => { const f = document.querySelector('.space-field');"
        " return f && f.dataset.moving === 'false' }",
        timeout=timeout,
    )


def _flight_lands(page) -> None:
    """Wait for a flight of the eye to BEGIN and then to end.

    Letting go of a choice is one render ahead of the flight it starts, so for
    a frame the field reports nothing moving while the eye has not set off
    yet: waiting only for stillness catches that gap and reads the canvas
    mid-flight. Not a product fault -- the flight does land -- but a pixel
    read in that window is meaningless."""
    page.wait_for_function(
        "() => document.querySelector('.space-field').dataset.moving === 'true'",
        timeout=2000,
    )
    _still(page)
    page.wait_for_timeout(120)


def _graph_is_up(page) -> None:
    page.locator("section.space-surface").wait_for()
    assert page.get_by_text(NOT_WIRED).count() == 0, "the host was not given Part A's module"
    page.locator(".space-field").wait_for()
    page.wait_for_function(
        "() => { const f = document.querySelector('.space-field');"
        " return f && f.dataset.drawn && f.dataset.drawn !== '0' }"
    )


def _session_of(page) -> str:
    return page.locator(".q2sp").get_attribute("data-space-session")


# ── every request the page made ─────────────────────────────────────────────


class Traffic:
    """What the page asked of the world, so what it did is checkable: that it
    read and never wrote, and that it never left this origin."""

    def __init__(self, page, base: str):
        self.base = base
        self.calls: list[tuple[str, str]] = []
        page.on("request", lambda r: self.calls.append((r.method, r.url)))

    def mark(self) -> int:
        return len(self.calls)

    def since(self, mark: int) -> list[tuple[str, str]]:
        return self.calls[mark:]

    def space_reads(self, mark: int = 0) -> list[str]:
        return [u for m, u in self.since(mark)
                if "/api/space" in u and "said" not in u]

    def writes(self, mark: int = 0) -> list[tuple[str, str]]:
        return [(m, u) for m, u in self.since(mark) if m not in ("GET", "HEAD")]

    def foreign(self, mark: int = 0) -> list[str]:
        return [u for _, u in self.since(mark)
                if not u.startswith(self.base) and not u.startswith("data:")
                and not u.startswith("blob:")]


def _read_nothing_else(traffic: Traffic, mark: int, since: float, what: str) -> None:
    """`what` cost no read of the graph beyond the advances the reader could
    honestly have made in that time (its existing 5000ms spacing)."""
    reads = traffic.space_reads(mark)
    allowed = _advances_possible(time.monotonic() - since)
    assert len(reads) <= allowed, f"{what} read /api/space again: {reads}"


def _wrote_nothing(traffic: Traffic, mark: int, what: str) -> None:
    assert traffic.writes(mark) == [], f"{what} wrote: {traffic.writes(mark)}"
    assert traffic.foreign(mark) == [], f"{what} left this origin: {traffic.foreign(mark)}"


# ── the Brain, as the graph read it ─────────────────────────────────────────


def _space(world) -> dict[str, dict]:
    """Every node `/api/space` returns, by id, with its kind, layer and the
    Conversation the record places it in."""
    req = urllib.request.Request(world["base"] + "/api/space",
                                 headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        read = json.loads(r.read())
    return {n["entry"]: n for n in read["nodes"]}


#: the kinds §4 sends to the read-only entry inspector whatever layer they sit
#: in (routing.ts SUBSTRATE, restated here as the expectation)
SUBSTRATE = {
    "anchor", "reaction", "observation", "deletion", "timer-mark", "marked-ready",
    "own-words", "interpretation", "interpretation-reply", "response-set", "answer",
    "source-material", "whole-brain",
}


def _reader_for(node: dict) -> str:
    """Which of Quiet Chat's existing readers §4 says this family is read by:
    'record' (Manage Brain's own), 'entry' (the read-only inspector), 'post'
    (the Turn in its Conversation) or 'conversation'."""
    if re.match(r"^adm-[0-9a-z]+$", node["entry"], re.I):
        return "entry"
    kind, layer = node["kind"], node["layer"]
    if kind in SUBSTRATE:
        return "entry"
    if kind == "conversation":
        return "conversation"
    if kind == "contribution":
        return "post" if node["conversation"] else "entry"
    if kind in ("topic", "participant"):
        return "entry"
    if layer in ("how", "that"):
        return "record"
    return "entry"


def _walk(page, steps: int) -> list[str]:
    """Walk the graph with the keyboard as a person would, and say what was
    chosen at each step. Tab leaves the canvas where there is nowhere left to
    go, so the field is focused again each time."""
    seen: list[str] = []
    field = page.locator(".space-field")
    for _ in range(steps):
        field.focus()
        page.keyboard.press("Tab")
        time.sleep(0.05)
        now = field.get_attribute("data-selected") or ""
        if not now or (seen and now == seen[-1]):
            break
        seen.append(now)
    return seen


# ── the page, as the tests open it ──────────────────────────────────────────


def _open_quiet(browser, world, conversation, *, width: int, height: int,
                arr: str | None = "three", theme: str | None = None,
                scheme: str = "light"):
    """Quiet Chat on this Brain, at this size, in this theme. `arr` is the
    existing address override for one load (prefs.ts); left out, the page
    restores what it saves, which on a fresh browser is one column."""
    page = browser.new_page(viewport={"width": width, "height": height},
                            color_scheme=scheme, reduced_motion="no-preference")
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    traffic = Traffic(page, world["base"])
    if theme:
        page.add_init_script(f"localStorage.setItem('mentis:theme', {json.dumps(theme)})")
    where = f"/quiet2?c={conversation}" + (f"&arr={arr}" if arr else "")
    page.goto(world["base"] + where)
    page.get_by_text(OPENING, exact=True).first.wait_for()
    return page, errors, traffic


def _fixture(world):
    assert DIST.exists(), "build apps/fluid-web first"
    cv, owner = world["cv"], world["who"]["@brian"]
    first, second = _a_brain_worth_drawing(cv, owner)
    return first, second


# ════════════════════════════════════════════════════════════════════════════
# 1. THE ROOM THE GRAPH IS GIVEN
# ════════════════════════════════════════════════════════════════════════════


def test_the_graph_takes_the_room_it_is_given(world):
    """§6: full-width workspace, wide and narrow columns, manual and keyboard
    resizing -- and the floating controls reachable inside the COLUMN, which
    is the thing `100vw` got wrong before."""
    playwright = pytest.importorskip("playwright.sync_api")
    first, _ = _fixture(world)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page, errors, traffic = _open_quiet(browser, world, first, width=1600, height=1000)
            before = _written(world)
            quiet = traffic.mark()

            _open_the_graph(page)
            _graph_is_up(page)
            session = _session_of(page)
            column = page.locator(".q2sp").bounding_box()
            canvas = page.locator(".space-canvas").bounding_box()
            # A WIDE COLUMN: the field fills its column, not the window.
            assert abs(canvas["width"] - column["width"]) <= 2, (canvas, column)
            assert canvas["width"] < 1600 * 0.6, "a column graph took the whole window"
            assert canvas["height"] > 400

            # -- the whole workspace: maximised, it has the window ------------
            after_open = traffic.mark()
            moved = time.monotonic()
            page.get_by_role("button", name="Maximise", exact=True).click()
            page.locator(".q2sp-max").wait_for()
            _graph_is_up(page)
            wide = page.locator(".space-canvas").bounding_box()
            assert wide["width"] > canvas["width"] * 1.6, (wide, canvas)
            assert wide["width"] > 1600 * 0.8, "maximised, the graph did not take the width"
            assert _session_of(page) == session, "maximising made a second graph"

            page.get_by_role("button", name="Restore", exact=True).click()
            page.locator(".q2sp-column").wait_for()
            _graph_is_up(page)
            assert page.locator(".space-canvas").bounding_box() == canvas
            _read_nothing_else(traffic, after_open, moved, "maximise and restore")

            # -- narrowed by hand, to a 220-300px column ---------------------
            sized = traffic.mark()
            dragged = time.monotonic()
            divider = page.locator(".q2-divider").first
            box = divider.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] + 230, box["y"] + box["height"] / 2, steps=12)
            page.mouse.up()
            page.wait_for_timeout(120)
            narrow = page.locator(".space-canvas").bounding_box()
            room = page.locator(".q2sp").bounding_box()
            assert 215 <= narrow["width"] <= 320, f"the column did not narrow: {narrow}"
            assert abs(narrow["width"] - room["width"]) <= 2
            assert _session_of(page) == session, "resizing made a second graph"
            assert _drawn(page) > 0, "the narrowed graph stopped drawing"

            # THE CONTROLS ARE REACHABLE, AND INSIDE THE COLUMN. The options
            # popover was sized with `100vw`; here the only room is the column.
            page.get_by_role("button", name="Options", exact=True).click()
            panel = page.locator(".space-options")
            panel.wait_for()
            pbox = panel.bounding_box()
            assert pbox["width"] <= room["width"] + 1, (pbox, room)
            assert pbox["x"] >= room["x"] - 1, (pbox, room)
            assert pbox["x"] + pbox["width"] <= room["x"] + room["width"] + 1, (pbox, room)
            # and every choice in it can actually be used
            for label in ("Show every connection", "Show turns", "Show what is copied from Sources"):
                box = panel.get_by_text(label, exact=False).first.bounding_box()
                assert box["x"] >= room["x"] - 1 and box["x"] + box["width"] <= room["x"] + room["width"] + 1, label
            page.get_by_role("button", name="Options", exact=True).click()
            head = page.locator(".space-head").bounding_box()
            foot = page.locator(".space-foot").bounding_box()
            for name, b in (("head", head), ("foot", foot)):
                assert b["x"] >= room["x"] - 1, (name, b, room)
                assert b["x"] + b["width"] <= room["x"] + room["width"] + 1, (name, b, room)

            # -- dragged past the minimum: the column stops, nothing collapses
            box = divider.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] + 600, box["y"] + box["height"] / 2, steps=12)
            page.mouse.up()
            page.wait_for_timeout(120)
            floored = page.locator(".space-canvas").bounding_box()
            assert floored["width"] >= COLUMN_MIN - 2, floored
            assert _drawn(page) > 0

            # -- stepped by key ---------------------------------------------
            was = page.locator(".space-canvas").bounding_box()["width"]
            divider.focus()
            for _ in range(3):
                page.keyboard.press("ArrowLeft")
            page.wait_for_timeout(120)
            keyed = page.locator(".space-canvas").bounding_box()["width"]
            assert keyed > was + 20, f"the keyboard did not resize the column: {was} -> {keyed}"
            assert _session_of(page) == session
            assert _drawn(page) > 0
            _read_nothing_else(traffic, sized, dragged, "resizing the column")

            _wrote_nothing(traffic, quiet, "placing and resizing the graph")
            assert _written(world) == before, "sizing the graph recorded something"
            assert world["sent"] == [], "a graph action dispatched an agent"
            assert errors == []
        finally:
            browser.close()


# ════════════════════════════════════════════════════════════════════════════
# 2. A SECOND WORKING SURFACE BESIDE IT
# ════════════════════════════════════════════════════════════════════════════


def test_a_second_working_surface_sits_beside_the_graph(world):
    """§6: "A second working surface beside the visualization". Neither takes
    the other's column, and moving the graph does not disturb it."""
    playwright = pytest.importorskip("playwright.sync_api")
    first, _ = _fixture(world)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page, errors, traffic = _open_quiet(browser, world, first, width=1600, height=1000)
            before = _written(world)
            quiet = traffic.mark()

            _open_the_graph(page)
            _graph_is_up(page)
            session = _session_of(page)
            graph_pane = page.locator(".q2-pane.q2-surface", has=page.locator(".q2sp"))
            assert graph_pane.count() == 1

            # a post opened in a working surface, through the existing action
            page.locator('.q2-conv [data-post] [aria-label="More actions"]').first.click()
            page.get_by_role("menuitem", name="Open this post in a working surface").click()
            other = page.locator(".q2-surface-view")
            other.first.wait_for()
            assert other.count() == 1, "the post did not open in a working surface"
            assert page.locator(".q2-pane.q2-surface").count() == 2, "there are not two surfaces"
            assert page.locator(".q2sp").count() == 1, "the graph was duplicated or lost"
            assert _session_of(page) == session, "the second surface rebuilt the graph"
            assert _drawn(page) > 0, "the graph stopped drawing beside another surface"

            # they are side by side, not one over the other
            g = page.locator(".q2sp").bounding_box()
            o = other.first.bounding_box()
            assert g["x"] + g["width"] <= o["x"] + 2 or o["x"] + o["width"] <= g["x"] + 2, (g, o)

            # the graph maximised and restored leaves the other surface as it was
            mark, moved = traffic.mark(), time.monotonic()
            page.get_by_role("button", name="Maximise", exact=True).click()
            page.locator(".q2sp-max").wait_for()
            page.get_by_role("button", name="Restore", exact=True).click()
            page.locator(".q2sp-column").wait_for()
            _graph_is_up(page)
            assert page.locator(".q2-surface-view").count() == 1, "the other surface was lost"
            assert page.locator(".q2-surface-view").first.bounding_box() == o
            assert _session_of(page) == session
            _read_nothing_else(traffic, mark, moved, "a round trip beside a second surface")

            _wrote_nothing(traffic, quiet, "opening a second surface")
            assert _written(world) == before
            assert world["sent"] == []
            assert errors == []
        finally:
            browser.close()


# ════════════════════════════════════════════════════════════════════════════
# 3. LIGHT AND DARK
# ════════════════════════════════════════════════════════════════════════════


def test_the_graph_is_drawn_in_every_theme(world):
    """§6: "Light and dark themes where supported". The canvas reads the same
    tokens as everything else, so a theme change must REPAINT it -- the defect
    this guards is a field left in the old theme's colours."""
    playwright = pytest.importorskip("playwright.sync_api")
    first, _ = _fixture(world)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # -- light, and the browser's own dark ---------------------------
            page, errors, traffic = _open_quiet(browser, world, first, width=1400, height=900,
                                                scheme="light")
            _open_the_graph(page)
            _graph_is_up(page)
            _still(page)
            light_ground = page.evaluate(
                "() => getComputedStyle(document.documentElement).getPropertyValue('--surface').trim()")
            light = _digest(page)
            lit = page.evaluate(LIT)

            mark, since = traffic.mark(), time.monotonic()
            page.emulate_media(color_scheme="dark")
            page.wait_for_timeout(250)
            _still(page)
            dark_ground = page.evaluate(
                "() => getComputedStyle(document.documentElement).getPropertyValue('--surface').trim()")
            dark = _digest(page)
            assert dark_ground != light_ground, "the page itself did not go dark"
            assert dark[:2] == light[:2], "the canvas was resized, so pixels cannot be compared"
            assert dark[2] != light[2], (
                f"the system theme changed ({light_ground} -> {dark_ground}) but the field "
                "was not repainted: it is still drawn in the other theme's colours")
            assert page.evaluate(LIT) > lit * 0.5, "the field went dark rather than being repainted"
            assert _drawn(page) > 0
            _read_nothing_else(traffic, mark, since, "changing the theme")
            _wrote_nothing(traffic, mark, "changing the theme")
            assert errors == []
            page.close()

            # -- a chosen dark, over a light browser (`mentis:theme`) --------
            page2, errors2, traffic2 = _open_quiet(browser, world, first, width=1400, height=900,
                                                   scheme="light", theme="dark")
            assert page2.evaluate("() => document.documentElement.getAttribute('data-theme')") == "dark"
            _open_the_graph(page2)
            _graph_is_up(page2)
            _still(page2)
            chosen = _digest(page2)
            assert chosen[:2] == light[:2]
            assert chosen[2] != light[2], "a chosen dark theme drew the light field"
            assert _drawn(page2) > 0
            assert page2.locator(".space-caption").first.inner_text() != ""
            assert errors2 == []
        finally:
            browser.close()


# ════════════════════════════════════════════════════════════════════════════
# 4. A PHONE
# ════════════════════════════════════════════════════════════════════════════


def test_a_phone_gets_the_whole_screen_and_a_way_back(world):
    """§6: "Phone-sized layout with an appropriate fallback". A phone has no
    working column to give (one column is what the page restores), so the
    existing fallback is the maximised graph over the conversation -- which
    must actually be usable and must give the conversation back."""
    playwright = pytest.importorskip("playwright.sync_api")
    first, _ = _fixture(world)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # no `arr`: what a phone restores, which on a fresh browser is one
            page, errors, traffic = _open_quiet(browser, world, first, width=390, height=844,
                                                arr=None)
            before = _written(world)
            quiet = traffic.mark()
            assert page.locator(".q2-pane.q2-surface").count() == 0, "a phone had working columns"

            _open_the_graph(page)
            _graph_is_up(page)
            assert page.locator(".q2sp-max").count() == 1, (
                "with no column to open into, the graph did not take the screen")
            canvas = page.locator(".space-canvas").bounding_box()
            # the maximised viewer keeps its existing margin (about 23px each
            # side at this width), so the field is most of the screen, not all
            assert canvas["width"] >= 390 * 0.85, f"the field was given almost no width: {canvas}"
            assert canvas["height"] >= 400, canvas
            assert _drawn(page) > 0, "nothing was drawn at phone size"

            # ITS CONTROLS FIT THE SCREEN rather than overflowing it
            room = page.locator(".q2sp").bounding_box()
            page.get_by_role("button", name="Options", exact=True).click()
            panel = page.locator(".space-options")
            panel.wait_for()
            pbox = panel.bounding_box()
            assert pbox["width"] <= 390 and pbox["x"] >= -1 and pbox["x"] + pbox["width"] <= 391, pbox
            page.get_by_role("button", name="Options", exact=True).click()
            for name in ("space-head", "space-foot", "space-tools"):
                b = page.locator("." + name).bounding_box()
                assert b["x"] >= -1 and b["x"] + b["width"] <= 391, (name, b)

            # choosing works by hand at this size, and the card can be read
            page.locator(".space-field").focus()
            page.keyboard.press("Tab")
            page.wait_for_function(
                "() => { const f = document.querySelector('.space-field');"
                " return f && f.dataset.selected }")
            time.sleep(LANDED_S)
            card = page.locator(".space-chosen")
            card.wait_for()
            cbox = card.bounding_box()
            assert cbox["x"] >= -1 and cbox["x"] + cbox["width"] <= 391, cbox
            assert card.get_by_role("button", name="Open", exact=False).count() >= 1

            # THE WAY BACK: closing the graph gives the conversation back
            page.get_by_role("button", name="Close viewer", exact=True).click()
            page.get_by_text(OPENING, exact=True).first.wait_for()
            assert page.locator(".space-field").count() == 0, "the graph stayed over the conversation"
            assert page.locator(".q2sp").count() == 0

            _wrote_nothing(traffic, quiet, "the graph on a phone")
            assert _written(world) == before
            assert world["sent"] == []
            assert errors == []
        finally:
            browser.close()


# ════════════════════════════════════════════════════════════════════════════
# 5. THE VIEW SURVIVES BEING MOVED AND BEING LEFT
# ════════════════════════════════════════════════════════════════════════════


def test_the_camera_filters_and_clock_survive_a_move_and_a_reading(world):
    """§4: "Preserve the graph's camera position, selection, and filters when
    moving between the visualization and record details", and the hidden
    playback policy (addendum §1). The camera is compared as PIXELS at an
    identical size, which is exact: the same eye paints the same field."""
    playwright = pytest.importorskip("playwright.sync_api")
    first, _ = _fixture(world)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page, errors, traffic = _open_quiet(browser, world, first, width=1600, height=1000)
            before = _written(world)
            quiet = traffic.mark()

            _open_the_graph(page)
            _graph_is_up(page)
            session = _session_of(page)
            _still(page)
            opening = _digest(page)

            # -- the view is made the reader's own: turned, travelled in -----
            field = page.locator(".space-field")
            field.focus()
            for _ in range(4):
                page.keyboard.press("ArrowLeft")
            page.keyboard.press("ArrowUp")
            page.keyboard.press("+")
            page.wait_for_timeout(150)
            _still(page)
            held = _digest(page)
            assert held[2] != opening[2], "turning and zooming did not change the view"

            # -- the filters are chosen --------------------------------------
            page.get_by_role("button", name="Options", exact=True).click()
            panel = page.locator(".space-options")
            panel.wait_for()
            every = panel.locator("input[type=checkbox]").nth(0)   # every connection
            turns = panel.locator("input[type=checkbox]").nth(1)   # show turns
            every.check()
            turns.uncheck()
            panel.locator("input[type=radio]").nth(1).check()      # colour by layer
            page.wait_for_timeout(120)

            # -- a thing chosen, to be preserved too -------------------------
            field.focus()
            page.keyboard.press("Tab")
            page.wait_for_function(
                "() => { const f = document.querySelector('.space-field');"
                " return f && f.dataset.selected }")
            chosen = field.get_attribute("data-selected")
            time.sleep(LANDED_S)

            # -- and the record's own clock, started and left running (the
            #    options panel is still the open one the filters were set in)
            page.locator(".space-options").wait_for()
            page.get_by_role("button", name="Watch how it was built", exact=False).click()
            page.locator(".space-when").wait_for()
            assert page.locator('.space-when button[aria-label="Pause"]').count() == 1, (
                "the record's clock did not start playing")
            page.wait_for_timeout(400)

            # ── READ WHAT WAS CHOSEN: the graph parks, the reader takes over ─
            mark, since = traffic.mark(), time.monotonic()
            field.focus()
            page.keyboard.press("Enter")
            back = page.get_by_role("button", name="Back to 3D Brain", exact=False)
            back.first.wait_for()
            assert page.locator(".space-field").count() == 0, "the graph was left over the reader"

            # THE CLOCK IS PAUSED WHILE NOBODY IS LOOKING, and does not catch up
            back.first.click()
            page.locator(".space-field").wait_for()
            _graph_is_up(page)
            assert _session_of(page) == session, "coming back built a new graph"
            assert page.locator(".space-field").get_attribute("data-selected") == chosen, (
                "the chosen thing was lost across a reading")
            assert page.locator('.space-when button[aria-label="Play"]').count() == 1, (
                "the record's clock was still playing, or playing again, after the return")
            was_at = page.locator(".space-when-said").inner_text()

            # THE FILTERS ARE THE ONES THAT WERE CHOSEN
            page.get_by_role("button", name="Options", exact=True).click()
            panel = page.locator(".space-options")
            panel.wait_for()
            assert panel.locator("input[type=checkbox]").nth(0).is_checked(), "'every connection' was lost"
            assert not panel.locator("input[type=checkbox]").nth(1).is_checked(), "'show turns' came back on"
            assert panel.locator("input[type=radio]").nth(1).is_checked(), "the palette was lost"
            page.get_by_role("button", name="Options", exact=True).click()
            _read_nothing_else(traffic, mark, since, "reading a chosen thing and coming back")

            # ── THE CAMERA, EXACTLY: let the choice go, then move the graph ──
            field = page.locator(".space-field")
            field.focus()
            page.keyboard.press("Escape")
            page.wait_for_function(
                "() => !document.querySelector('.space-field').dataset.selected")
            _flight_lands(page)
            parked_view = _digest(page)
            drawn_now = _drawn(page)

            mark, since = traffic.mark(), time.monotonic()
            page.get_by_role("button", name="Maximise", exact=True).click()
            page.locator(".q2sp-max").wait_for()
            _graph_is_up(page)
            _still(page)
            page.get_by_role("button", name="Restore", exact=True).click()
            page.locator(".q2sp-column").wait_for()
            _graph_is_up(page)
            _still(page)
            page.wait_for_timeout(200)
            moved_view = _digest(page)
            assert moved_view[:2] == parked_view[:2], "the canvas came back a different size"
            assert moved_view[2] == parked_view[2], (
                "the eye was not where it was left after a maximise and restore: the held "
                "camera was reset or re-framed")
            assert _drawn(page) == drawn_now, "moving the graph changed what is drawn"
            assert page.locator(".space-when-said").inner_text() == was_at, (
                "the record's clock moved on while the graph was being moved")
            _read_nothing_else(traffic, mark, since, "moving the graph")

            _wrote_nothing(traffic, quiet, "keeping the view through a move and a reading")
            assert _written(world) == before
            assert world["sent"] == []
            assert errors == []
        finally:
            browser.close()


# ════════════════════════════════════════════════════════════════════════════
# 6. READING FROM THE GRAPH, AND THE BROWSER'S OWN BACK
# ════════════════════════════════════════════════════════════════════════════


def test_the_browsers_back_and_forward_walk_the_graph_and_the_reader(world):
    """§4/§8: navigation between graph, Brain records and conversations, with
    the browser's own Back and Forward, and the same graph each time."""
    playwright = pytest.importorskip("playwright.sync_api")
    first, _ = _fixture(world)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page, errors, traffic = _open_quiet(browser, world, first, width=1600, height=1000)
            before = _written(world)
            quiet = traffic.mark()

            _open_the_graph(page)
            _graph_is_up(page)
            session = _session_of(page)
            field = page.locator(".space-field")
            field.focus()
            page.keyboard.press("Tab")
            page.wait_for_function(
                "() => { const f = document.querySelector('.space-field');"
                " return f && f.dataset.selected }")
            chosen = field.get_attribute("data-selected")
            time.sleep(LANDED_S)

            field.focus()
            page.keyboard.press("Enter")
            page.get_by_role("button", name="Back to 3D Brain", exact=False).first.wait_for()
            assert page.locator(".space-field").count() == 0

            # -- the browser's Back: the graph again, the same one -----------
            mark, since = traffic.mark(), time.monotonic()
            page.go_back()
            page.locator(".space-field").wait_for()
            _graph_is_up(page)
            assert _session_of(page) == session, "the browser's Back rebuilt the graph"
            assert page.locator(".space-field").get_attribute("data-selected") == chosen

            # -- and Forward: the reader again, still with its way back ------
            page.go_forward()
            page.get_by_role("button", name="Back to 3D Brain", exact=False).first.wait_for()
            assert page.locator(".space-field").count() == 0, "Forward left the graph drawn over it"

            # -- Back again, then out of the graph altogether ----------------
            page.go_back()
            page.locator(".space-field").wait_for()
            assert _session_of(page) == session
            _read_nothing_else(traffic, mark, since, "walking the browser's history")

            # the graph closed: the conversation, and no graph left behind
            page.get_by_role("button", name="Close viewer", exact=True).click()
            page.get_by_text(OPENING, exact=True).first.wait_for()
            assert page.locator(".q2sp").count() == 0
            # AND IT IS NOT RECREATED by an entry that named it
            page.go_back()
            page.wait_for_timeout(300)
            assert page.locator(".space-field").count() == 0, (
                "an old history entry brought a closed graph back to life")

            _wrote_nothing(traffic, quiet, "navigating from the graph")
            assert _written(world) == before
            assert world["sent"] == []
            assert errors == []
        finally:
            browser.close()


# ════════════════════════════════════════════════════════════════════════════
# 7. WHAT EACH FAMILY OF NODE OPENS
# ════════════════════════════════════════════════════════════════════════════


def test_each_family_of_node_opens_its_own_reader(world):
    """§4 of the addendum, in a browser: a chosen node is read by the reader
    its OWN family calls for -- Manage Brain's record presentation, the
    read-only entry inspector, the Turn in its Conversation, or the
    Conversation -- and the graph comes back from each.

    The families reached are the ones the keyboard walk actually visits in
    this Brain; which they were is asserted at the end, so a run that reached
    only one family fails rather than passing quietly."""
    playwright = pytest.importorskip("playwright.sync_api")
    first, _ = _fixture(world)
    nodes = _space(world)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page, errors, traffic = _open_quiet(browser, world, first, width=1600, height=1000)
            before = _written(world)
            quiet = traffic.mark()

            _open_the_graph(page)
            _graph_is_up(page)
            session = _session_of(page)

            walked = _walk(page, 18)
            assert walked, "the keyboard walked to nothing at all"
            # one representative of each family the walk reached
            picked: dict[str, str] = {}
            for entry in walked:
                node = nodes.get(entry)
                if not node:
                    continue
                picked.setdefault(_reader_for(node), entry)

            # the turns of each Conversation, so a post or a Conversation
            # target is recognised by what the conversation column shows
            turns_of: dict[str, list[str]] = {}
            for n in nodes.values():
                if n["kind"] == "contribution" and n["conversation"]:
                    turns_of.setdefault(n["conversation"], []).append(n["entry"])

            opened: dict[str, str] = {}
            for want, entry in sorted(picked.items()):
                # walk to it again from a clean field
                field = page.locator(".space-field")
                field.focus()
                page.keyboard.press("Escape")
                page.wait_for_timeout(80)
                for _ in range(len(walked) + 2):
                    field.focus()
                    page.keyboard.press("Tab")
                    page.wait_for_timeout(50)
                    if field.get_attribute("data-selected") == entry:
                        break
                assert field.get_attribute("data-selected") == entry, (
                    f"could not walk back to {entry}")
                time.sleep(LANDED_S)
                field.focus()
                page.keyboard.press("Enter")
                page.wait_for_timeout(600)

                node = nodes[entry]
                if want == "record":
                    page.locator('.q2-brain-main[data-brain-page="record"]').wait_for()
                    opened[want] = entry
                    assert page.locator("[data-brain-back]").inner_text().find("3D Brain") >= 0
                    page.locator("[data-brain-back]").click()
                elif want == "entry":
                    page.locator(f'[data-entry-inspect="{entry}"]').wait_for()
                    assert page.locator('.q2-brain-main[data-brain-page="entry"]').count() == 1
                    opened[want] = entry
                    assert page.locator("[data-brain-back]").inner_text().find("3D Brain") >= 0
                    page.locator("[data-brain-back]").click()
                elif want == "post":
                    page.locator(f'.q2-conv [data-post="{entry}"]').wait_for()
                    assert page.locator(".q2-brain-main").count() == 0, (
                        "a Turn was dressed as a Brain record")
                    opened[want] = entry
                    page.locator(".q2-space-return button").click()
                else:  # a Conversation
                    want_turns = turns_of.get(entry, [])
                    if want_turns:
                        page.wait_for_function(
                            "ids => ids.some((i) => document.querySelector"
                            "(`.q2-conv [data-post=\"${i}\"]`))",
                            arg=want_turns[:40], timeout=6000)
                    assert page.locator(".q2-brain-main").count() == 0, (
                        "a Conversation was dressed as a Brain record")
                    opened[want] = entry
                    page.locator(".q2-space-return button").click()

                page.locator(".space-field").wait_for()
                _graph_is_up(page)
                assert _session_of(page) == session, f"reading {want} rebuilt the graph"

            assert len(opened) >= 2, (
                f"the walk reached only {sorted(opened)}; nothing was proved about the rest")
            assert "conversation" in opened, (
                "the walk never reached a Conversation hub, which is where it starts")

            _wrote_nothing(traffic, quiet, "reading each family from the graph")
            assert _written(world) == before
            assert world["sent"] == []
            assert errors == []
            print("families opened from the graph:",
                  {k: (v, nodes[v]["kind"]) for k, v in opened.items()})
        finally:
            browser.close()


# ════════════════════════════════════════════════════════════════════════════
# 8. FLUID'S OWN 3D BRAIN IS STILL FLUID'S
# ════════════════════════════════════════════════════════════════════════════


def test_fluid_keeps_its_own_host_and_its_own_room(world):
    """§8: "No regression to Fluid's existing 3D Brain". That the route still
    draws and still travels is already proved; what is checked here is that
    Quiet Chat's host did not leak into it -- Open on Fluid's route is still
    Fluid's own float over the field, with none of Quiet Chat's frame -- and
    that the field still adapts to a narrow window."""
    playwright = pytest.importorskip("playwright.sync_api")
    _fixture(world)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1500, "height": 950},
                                    reduced_motion="no-preference")
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            traffic = Traffic(page, world["base"])

            page.goto(world["base"] + "/fluid#/brain/space")
            page.locator(".space-field").wait_for()
            page.wait_for_function(
                "() => { const f = document.querySelector('.space-field');"
                " return f && f.dataset.drawn && f.dataset.drawn !== '0' }")
            before = _written(world)
            mark = traffic.mark()
            assert page.locator(".q2sp").count() == 0, "Quiet Chat's host wrapped Fluid's route"
            assert page.locator(".q2-brain-main").count() == 0

            # the field has the whole place, as it always did
            canvas = page.locator(".space-canvas").bounding_box()
            assert canvas["width"] > 1500 * 0.8, canvas

            # OPEN IS STILL FLUID'S OWN: a float over the field, not a Quiet
            # reader, and the field stays drawn underneath it
            field = page.locator(".space-field")
            field.focus()
            page.keyboard.press("Tab")
            page.wait_for_function(
                "() => { const f = document.querySelector('.space-field');"
                " return f && f.dataset.selected }")
            time.sleep(LANDED_S)
            field.focus()
            page.keyboard.press("Enter")
            page.locator(".bz-float").first.wait_for()
            assert page.locator(".space-field").count() == 1, "Fluid's Open took the field away"
            assert page.locator(".q2-brain-main").count() == 0, (
                "Fluid's Open opened Quiet Chat's reader")

            # a narrow window: the options panel is bounded by the field
            page.set_viewport_size({"width": 420, "height": 820})
            page.wait_for_timeout(200)
            assert page.locator(".space-field").count() == 1
            surface = page.locator("section.space-surface").bounding_box()
            page.get_by_role("button", name="Options", exact=True).click()
            panel = page.locator(".space-options")
            panel.wait_for()
            pbox = panel.bounding_box()
            assert pbox["width"] <= surface["width"] + 1, (pbox, surface)
            assert pbox["x"] + pbox["width"] <= surface["x"] + surface["width"] + 1, (pbox, surface)

            _wrote_nothing(traffic, mark, "Fluid's own 3D Brain")
            assert _written(world) == before
            assert world["sent"] == []
            assert errors == []
        finally:
            browser.close()
