"""The 3D Brain hosted in Quiet Chat, against real Mentis HTTP routes.

The integration smoke for owner request ent-af6b8ce6355f: Part A's graph
session (quiet-brain-space-state) and Part B's Quiet host
(quiet-brain-space-host) merged and wired at the agreed seam
(adm-9f12e8153ca3 sections 1-3). What it is here to prove is the SEAM --
that the host is given Part A's real factory and reader, that the graph
therefore draws at all, and that placement does not cost a read or lose
what was being looked at. The full responsive/interaction matrix belongs
to the TEST-release verification, not here.

Disposable fixture Brain only (tests._loop.world): no live Brain, no
development server, no MARS. Build apps/fluid-web first and opt in with
MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import _written, world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

#: what SpaceHost says where Part A's module was never given to the host
#: (quiet2/space/provider.ts). Seeing it means the seam is not wired.
NOT_WIRED = "The 3D Brain is not part of this build yet."

#: the existing advance spacing of the one reader (useApi, 5000ms). A read in
#: a window this long is a legitimate advance; the point of the counts below
#: is that MOVING the graph reads nothing, not that nothing ever reads.
ADVANCE_S = 5.0


def _advances_possible(seconds: float) -> int:
    """How many durable advances the reader could honestly have made."""
    return int(seconds / ADVANCE_S) + 1


def _a_brain_worth_drawing(cv, owner):
    """Enough recorded things that /api/space returns a populated graph."""
    first = cv.open_conversation("Space browser: the busiest room",
                                 about="Where most of it was said.")
    second = cv.open_conversation("Space browser: the other room", about="Less here.")
    cv.join(owner, first)
    cv.join(owner, second)
    for n in range(24):
        cv.say(first, owner, [text(f"A thing said in the busiest room ({n}).")])
    for n in range(4):
        cv.say(second, owner, [text(f"A thing said elsewhere ({n}).")])
    return first, second


#: the first post of the busiest room, waited for as the page being up
OPENING = "A thing said in the busiest room (0)."


def _open_the_graph(page):
    """The real path: the Brain menu's own 3D Brain choice, no shortcut."""
    page.locator("button.brand-menu-open").click()
    row = page.locator('.brand-menu button[data-row="space"]')
    row.wait_for()
    assert row.get_attribute("aria-disabled") is None, "the Brain menu offers 3D Brain but refuses it"
    row.click()
    page.locator("section.space-surface").wait_for()


def test_quiet_hosts_the_graph(world):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cv, owner = world["cv"], world["who"]["@brian"]
    first, _second = _a_brain_worth_drawing(cv, owner)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            reads: list[str] = []
            page.on("request", lambda r: reads.append(r.url)
                    if "/api/space" in r.url and "said" not in r.url else None)

            # `arr=three` (prefs.ts: an address override for this load only)
            # gives the page its two working columns, so the graph opens into
            # a column and has somewhere to be restored to. With one column it
            # opens maximised and the host offers no restore, which is the
            # existing placement rule, not this seam.
            page.goto(world["base"] + f"/quiet2?c={first}&arr=three")
            page.get_by_text(OPENING, exact=True).first.wait_for()

            # Everything from here is reading. Nothing the graph offers may
            # record anything (plan adm-41ecec0c74c0: "No action navigates to
            # another origin or creates/edits Brain records").
            before = _written(world)

            # -- the seam: the host draws Part A's graph, not its own apology --
            _open_the_graph(page)
            assert page.get_by_text(NOT_WIRED).count() == 0, (
                "the host was not given Part A's session module: provideSpaceSessions "
                "is not wired"
            )
            field = page.locator(".space-field")
            field.wait_for()
            assert page.locator(".space-canvas").count() == 1
            viewer = page.locator(".q2sp")
            session_id = viewer.get_attribute("data-space-session")
            assert session_id, "the host placed a graph with no session"

            # -- it actually read the Brain, and says what it is showing --
            caption = page.locator(".space-caption").first
            caption.wait_for()
            page.wait_for_function(
                "() => { const f = document.querySelector('.space-field');"
                " return f && f.dataset.drawn && f.dataset.drawn !== '0' }"
            )
            assert "thing" in caption.inner_text()
            after_first_read = len(reads)
            assert after_first_read >= 1, "the graph never read /api/space"

            # -- the keyboard chooses something, and the field reports it --
            field.focus()
            page.keyboard.press("Tab")
            page.wait_for_function(
                "() => { const f = document.querySelector('.space-field');"
                " return f && f.dataset.selected }"
            )
            chosen = field.get_attribute("data-selected")
            assert chosen, "Tab chose nothing to walk from"

            # -- a placement round trip: same session, same choice, no re-read.
            # Where it opened (a free column, or maximised when there is none)
            # is the host's existing placement rule, so the trip is taken from
            # wherever that was and back to it.
            trip_from = time.monotonic()
            was_max = page.locator(".q2sp-max").count() == 1
            here, there = ((".q2sp-max", ".q2sp-column") if was_max
                           else (".q2sp-column", ".q2sp-max"))
            out_label, back_label = ("Restore", "Maximise") if was_max else ("Maximise", "Restore")
            box_before = page.locator(".space-canvas").bounding_box()

            page.get_by_role("button", name=out_label, exact=True).click()
            page.locator(there).wait_for()
            page.locator(".space-field").wait_for()
            page.get_by_role("button", name=back_label, exact=True).click()
            page.locator(here).wait_for()
            page.locator(".space-field").wait_for()

            assert page.locator(".q2sp").get_attribute("data-space-session") == session_id, (
                "maximise/restore made a new session instead of moving the one graph"
            )
            assert page.locator(".space-field").get_attribute("data-selected") == chosen, (
                "the chosen thing was lost across a placement change"
            )
            # The reader keeps its existing 5000ms advance while the graph is
            # placed anywhere, so what is checked is that the trip itself cost
            # no read beyond the advances that window could hold -- in practice
            # none, the trip being far shorter than one spacing.
            during_trip = len(reads) - after_first_read
            allowed = _advances_possible(time.monotonic() - trip_from)
            assert during_trip <= allowed, (
                "moving the graph read /api/space again: the retained read or the "
                f"single reader is not in force (reads: {reads[after_first_read:]})"
            )
            assert all(r.endswith("/api/space") for r in reads), (
                f"placement changed the read's key or path: {reads}"
            )
            assert page.locator(".space-canvas").bounding_box() == box_before

            # -- opening what is chosen parks the graph and offers the way back --
            page.locator(".space-field").focus()
            page.keyboard.press("Enter")
            back = page.get_by_role("button", name="Back to 3D Brain", exact=False)
            back.first.wait_for()
            assert page.locator(".space-field").count() == 0, (
                "the graph was left drawn over what it was asked to show"
            )
            reads_while_parked = len(reads)
            return_from = time.monotonic()

            back.first.click()
            page.locator(".space-field").wait_for()
            assert page.locator(".q2sp").get_attribute("data-space-session") == session_id, (
                "coming back from a record built a new graph"
            )
            assert page.locator(".space-field").get_attribute("data-selected") == chosen
            assert len(reads) - reads_while_parked <= _advances_possible(
                time.monotonic() - return_from), (
                "returning to the graph read the whole Brain again "
                f"(reads: {reads[reads_while_parked:]})"
            )

            assert _written(world) == before, (
                "opening the graph, choosing, moving it and reading what was "
                "chosen recorded something in the Brain"
            )
            assert world["sent"] == [], "a graph action dispatched an agent"
            assert errors == []
        finally:
            browser.close()


def test_fluid_route_still_draws_without_a_session(world):
    """Part A changed the shared renderer, so Fluid's own `#/brain/space`
    is the regression that matters most: it passes no session and must keep
    its own local reader, defaults and behaviour (addendum section 1,
    "Without a session, Fluid retains its current local reader")."""
    playwright = pytest.importorskip("playwright.sync_api")
    cv, owner = world["cv"], world["who"]["@brian"]
    _a_brain_worth_drawing(cv, owner)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            reads: list[str] = []
            page.on("request", lambda r: reads.append(r.url)
                    if "/api/space" in r.url and "said" not in r.url else None)

            page.goto(world["base"] + "/fluid#/brain/space")
            page.locator(".space-field").wait_for()
            page.wait_for_function(
                "() => { const f = document.querySelector('.space-field');"
                " return f && f.dataset.drawn && f.dataset.drawn !== '0' }"
            )
            assert page.get_by_text(NOT_WIRED).count() == 0
            assert page.locator(".space-canvas").count() == 1
            assert "thing" in page.locator(".space-caption").first.inner_text()
            # Fluid is not hosted by Quiet Chat: no Quiet frame around it.
            assert page.locator(".q2sp").count() == 0
            assert reads, "Fluid's own reader never read /api/space"
            assert all(r.endswith("/api/space") for r in reads), reads
            assert errors == []
        finally:
            browser.close()
