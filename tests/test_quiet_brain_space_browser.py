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


# ── the camera, as a browser can actually see it ────────────────────────────
#
# Nothing publishes the camera to the DOM, and asserting on the renderer's
# source text is what review adm-425121b18a7f's A-2 was about. So the eye is
# observed where it has a visible consequence:
#
#   WHAT THE EYE ORBITS IS DRAWN IN THE MIDDLE. `layout.look` projects
#   `camera.eye.at` to exactly (width/2, height/2). Travelling to a choice
#   sets `eye.at` to that star's own place, so the chosen star -- drawn with
#   its accent glow and ring -- ARRIVES in the middle of the canvas. A middle
#   that stays dark while something is chosen is an eye that did not move:
#   the selection would be lit where it already was, off centre.
#
#   AND WHAT IS IN THE MIDDLE CAN BE CLICKED. The canvas hit-tests what it
#   drew (`under`, 9px), so clicking the exact middle must land on the thing
#   just chosen.
#
# Neither reads a number the fix writes; both are what a person would see.
# Both are asserted because the first alone is not decisive -- a choice that
# happens to be drawn near the middle, or a strand lit across it, can raise
# the light without the eye having moved; run against the unfixed renderer,
# the light check caught one surface and the click caught the other.

#: mean luminance of the middle of the canvas (0-255), premultiplied by alpha
#: -- the canvas is cleared, so where nothing is drawn it is 0.
MIDDLE_LIGHT = """
() => {
  const c = document.querySelector('.space-canvas')
  const g = c.getContext('2d')
  const dpr = c.width / c.clientWidth
  const R = Math.round(16 * dpr)
  const d = g.getImageData(Math.round(c.width / 2) - R, Math.round(c.height / 2) - R, R * 2, R * 2).data
  let sum = 0
  for (let i = 0; i < d.length; i += 4)
    sum += (d[i] * 0.2126 + d[i + 1] * 0.7152 + d[i + 2] * 0.0722) * (d[i + 3] / 255)
  return sum / (d.length / 4)
}
"""

#: What the middle measures on this fixture Brain with nothing chosen (the eye
#: orbiting the world origin): 0.07, there being nothing drawn there. With a
#: chosen star travelled to it measures 13 to 19. These two leave the whole
#: band between them as margin.
MIDDLE_DARK = 1.0
MIDDLE_HAS_THE_CHOICE = 5.0

#: One flight is 420ms ON THE PAGE'S OWN CLOCK (BrainSpace.tsx, MS: it is
#: timed with `performance.now()` and stepped by animation frames), and the eye
#: is only AT the choice once its last frame has been painted.
FLIGHT_PAGE_MS = 420
#: How long a poll waits before calling a flight that never happened a
#: failure. Nothing is waited on for this long when the eye does travel.
FLIGHT_MS = 10000

#: A FLIGHT HAS LANDED WHEN THE PAGE SAYS ITS TIME IS UP AND HAS PAINTED SINCE.
#: Asked of the page, not slept on here: a sleep measured from when this
#: process pressed the key says nothing about a page that rendered the choice
#: late or is being given few frames, and clicking the middle then lands on
#: whatever the eye is passing over. Started only after the page has shown the
#: choice (`_tab_chooses`), which is when the flight's own clock started; two
#: further frames, because the flight's last step and this are both frames.
LANDED = """
(ms) => new Promise((done) => {
  const from = performance.now()
  const tick = () => {
    if (performance.now() - from < ms) { requestAnimationFrame(tick); return }
    requestAnimationFrame(() => requestAnimationFrame(() => done(true)))
  }
  requestAnimationFrame(tick)
})
"""

#: EVERYTHING THE FIELD SAID ABOUT ITSELF, kept as it changed. Whether a flight
#: began is a fact about a moment that passes: polled for, it is missed by a
#: page whose frames are further apart than the flight is long.
WATCH = """
() => {
  const f = document.querySelector('.space-field')
  const seen = (window.__spaceSeen = [])
  new MutationObserver(() => seen.push([f.dataset.selected || '', f.dataset.moving]))
    .observe(f, { attributes: true, attributeFilter: ['data-moving', 'data-selected'] })
}
"""
FLEW_WITH_NOTHING_CHOSEN = """
() => (window.__spaceSeen || []).some(([selected, moving]) => selected === '' && moving === 'true')
"""


def _middle_light(page) -> float:
    return page.evaluate(MIDDLE_LIGHT)


def _the_flight_has_landed(page) -> None:
    page.evaluate(LANDED, FLIGHT_PAGE_MS)


def _flies_to_the_choice(page, before: float) -> float:
    """Wait for the chosen star to arrive in the middle, and say how bright it
    is once the flight has landed. Polled rather than slept on, so a flight
    that never happens fails with both numbers in it rather than after a
    sleep; then the rest of the flight is allowed to finish, because what is
    clicked next is what the eye has ARRIVED at, not passed over."""
    want = max(MIDDLE_HAS_THE_CHOICE, before + MIDDLE_HAS_THE_CHOICE)
    until = time.monotonic() + FLIGHT_MS / 1000
    light = _middle_light(page)
    while light < want and time.monotonic() < until:
        time.sleep(0.02)
        light = _middle_light(page)
    _the_flight_has_landed(page)
    return _middle_light(page)


def _the_middle_is_still(page) -> None:
    """Wait for the field to stop animating. With nothing chosen there is
    nothing else to animate, so this is the flight ending."""
    page.wait_for_function(
        "() => document.querySelector('.space-field').dataset.moving === 'false'",
        timeout=FLIGHT_MS,
    )


def _a_flight_is_under_way(page, what: str) -> None:
    """`data-moving` with nothing chosen can only be the eye travelling: the
    strand animation needs a selection, and nothing is playing. Read from
    what the field was SEEN to say (`WATCH`, started before letting go), not
    from what it says at the moment of asking."""
    try:
        page.wait_for_function(FLEW_WITH_NOTHING_CHOSEN, timeout=FLIGHT_MS)
    except Exception as nothing_moved:  # the field never animated at all
        raise AssertionError(
            f"{what}: the eye did not travel -- the field never began moving"
        ) from nothing_moved


def _clicking_the_middle_chooses(page):
    """What the canvas says is under the exact middle of the view. The pointer
    is then taken off the field: left where it clicked, it is HOVERING the
    middle, and the renderer names whatever comes under a hovering pointer --
    which paints a label into the very place `_middle_light` measures."""
    box = page.locator(".space-canvas").bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    chosen = page.locator(".space-field").get_attribute("data-selected")
    page.mouse.move(2, 2)
    return chosen


def _tab_chooses(page, after: str = ""):
    """Walk to the next thing with the keyboard, as a person would. Returns
    once the page shows the NEW choice (not the one before it), which is when
    its flight has begun."""
    field = page.locator(".space-field")
    field.focus()
    page.keyboard.press("Tab")
    page.wait_for_function(
        "(after) => { const f = document.querySelector('.space-field');"
        " return f && f.dataset.selected && f.dataset.selected !== after }",
        arg=after,
    )
    return field.get_attribute("data-selected")


def _a_dark_middle(page) -> float:
    """The Brain turned, if it must be, until nothing is drawn in the middle.

    WHERE A STAR IS DRAWN IS A HASH OF ITS ID (surfaces/space/layout.ts), and a
    fixture Brain's ids are new every run, so now and then one is drawn in the
    middle of the opening view. That is no fault and proves nothing either
    way; turning is the reader's own act, a flight leaves the bearing alone
    (BrainSpace.tsx, "The angle is left alone"), and the check that follows is
    unchanged: it still needs, and asserts, a dark middle to arrive in."""
    field = page.locator(".space-field")
    light = _middle_light(page)
    for _ in range(24):
        if light < MIDDLE_DARK:
            break
        field.focus()
        page.keyboard.press("ArrowLeft")
        page.evaluate(LANDED, 0)
        light = _middle_light(page)
    return light


def _the_eye_travels_to_what_is_chosen(page, where: str) -> None:
    """THE A-1 CHECK, in a browser: choosing brings the chosen thing into
    view, EVERY time and not only the first -- the defect was a gate read once
    at mount, so with a session bound (which is how both surfaces draw) no
    choice ever moved the eye -- and letting go flies back to the middle.

    `where` names the surface, so a failure says which one."""
    field = page.locator(".space-field")
    at_rest = _a_dark_middle(page)
    assert at_rest < MIDDLE_DARK, (
        f"{where}: the middle of the view is already lit ({at_rest:.2f}) with "
        "nothing chosen, so arriving there proves nothing"
    )

    first = _tab_chooses(page)
    assert first, f"{where}: Tab chose nothing to travel to"
    lit = _flies_to_the_choice(page, at_rest)
    assert lit >= MIDDLE_HAS_THE_CHOICE, (
        f"{where}: choosing {first} left the middle of the view dark "
        f"({at_rest:.2f} before, {lit:.2f} after): the eye did not travel to it"
    )
    assert _clicking_the_middle_chooses(page) == first, (
        f"{where}: {first} was chosen but is not what the middle of the view "
        "is pointing at"
    )

    # AND AGAIN, for the next choice: one flight is not the property. The
    # renderer that read its gate once could not fly for any choice; one that
    # consumed a revision and stopped watching could fly only for the first.
    second = _tab_chooses(page, after=first)
    assert second and second != first, f"{where}: Tab did not walk on from {first}"
    lit_again = _flies_to_the_choice(page, 0.0)
    assert lit_again >= MIDDLE_HAS_THE_CHOICE, (
        f"{where}: the eye travelled to the first choice but not to {second} "
        f"(middle {lit_again:.2f})"
    )
    assert _clicking_the_middle_chooses(page) == second, (
        f"{where}: {second} was chosen but is not what the middle of the view "
        "is pointing at"
    )

    # LETTING GO FLIES BACK to the middle of the Brain. With nothing chosen
    # the field animates for nothing else, so this is the flight itself.
    page.evaluate(WATCH)
    field.focus()
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('.space-field').dataset.selected")
    _a_flight_is_under_way(page, f"{where}: letting go of {second}")
    _the_middle_is_still(page)
    home = _middle_light(page)
    assert home < MIDDLE_DARK, (
        f"{where}: letting go left the view where the choice was "
        f"(middle {home:.2f}): the eye did not fly back"
    )


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


def test_choosing_moves_the_eye_in_the_hosted_graph(world):
    """Part A's camera correction (quiet-brain-space-state f707b00), in the
    integrated host: a choice brings the chosen thing into view, and letting
    go flies back. Read the block above `MIDDLE_LIGHT` for what is observed
    and why that is the camera rather than the highlight."""
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cv, owner = world["cv"], world["who"]["@brian"]
    first, _second = _a_brain_worth_drawing(cv, owner)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # THE FLIGHT IS ANIMATED, so this says which motion preference the
            # page is driven with: asked to reduce motion the eye arrives in
            # one step, which is correct behaviour and a different check.
            page = browser.new_page(viewport={"width": 1600, "height": 1000},
                                    reduced_motion="no-preference")
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            page.goto(world["base"] + f"/quiet2?c={first}&arr=three")
            page.get_by_text(OPENING, exact=True).first.wait_for()
            before = _written(world)

            _open_the_graph(page)
            page.locator(".space-field").wait_for()
            page.wait_for_function(
                "() => { const f = document.querySelector('.space-field');"
                " return f && f.dataset.drawn && f.dataset.drawn !== '0' }"
            )
            _the_middle_is_still(page)

            _the_eye_travels_to_what_is_chosen(page, "the graph hosted in Quiet Chat")

            assert _written(world) == before, "choosing and travelling recorded something"
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
            page = browser.new_page(viewport={"width": 1600, "height": 1000},
                                    reduced_motion="no-preference")
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

            # THE SAME CAMERA PROPERTY HERE, because Part A changed the shared
            # renderer and this route is the one that was already shipping.
            # The route passes no session of its own, but SpaceSurface makes
            # one for itself (SpaceSurface.tsx: "UNBOUND, THIS SURFACE IS ITS
            # OWN HOST"), so the renderer always draws against a session and
            # the A-1 gate was in force here too.
            _the_middle_is_still(page)
            _the_eye_travels_to_what_is_chosen(page, "Fluid's own #/brain/space")

            assert errors == []
        finally:
            browser.close()
