"""Quiet Chat round 4, track A: the composer's REUSED palettes, its ground,
and the participant filter that replaces the addressing dropdown.

What this file is about is that Quiet's composer now has the existing Mentis
composer's behaviour BY REUSING IT, not by having it rebuilt: typing `@`
addresses somebody, `#` refers to a topic or a post, `/` names an established
Workflow -- and each lands in the draft so that the POSTED BODY carries it
exactly as Fluid's own composer would send it. Each case therefore ends at the
record or at the request body, never at the chip on the screen.

Beside them: the composer is painted on the dock's own ground rather than a
second one of its own, and the participant filter reads at rest and opens out
on hover or keyboard focus.

Everything here runs against real Mentis HTTP routes on a disposable fixture
Brain, starts no agent and never opens a live Brain. Build apps/fluid-web
first and opt in with MENTIS_QUIET_BROWSER=1; it needs Playwright with its
Chromium and WebKit browsers.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

import pytest

from mentis.conversation import text
from mentis.execution import FakeExecution
from tests._loop import get, world  # noqa: F401

browser = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

WIDE = {"width": 1440, "height": 900}
NARROW = {"width": 390, "height": 844}
WEB = Path(__file__).resolve().parent.parent / "apps" / "fluid-web" / "src" / "quiet"

#: THE ADDRESSEE'S CHIP, which opens the shared runtime/model/effort cascade.
SETTINGS_TOGGLE = "Will be asked to work: open to choose runtime, model and effort"


def _shot(page, name):
    """Screenshots, where the caller asked for them as evidence."""
    destination = os.environ.get("MENTIS_R4A_EVIDENCE")
    if destination:
        path = Path(destination)
        path.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=path / name)


def _said(turn):
    """What a recorded Turn's parts say, as one string."""
    return " ".join(str(q.get("text") or "") for q in turn.get("parts") or [])


def _fluid_get(world, path):
    """A read through Fluid's own door, which asks for the client header."""
    req = urllib.request.Request(world["base"] + path, headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _a_conversation(world, name="Quiet round four"):
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation(name, about="Where the palettes are used.")
    cv.join(owner, cid)
    cv.join(world["who"]["@Vera"], cid)
    for n in range(6):
        cv.say(cid, owner, [text(f"Something already said, number {n}.")])
    return cid


def _a_workflow(world, name="Round four check"):
    """One established Workflow, so `/` has something real to offer. Its
    `summary` -- the register's first declared string field -- is its name,
    which is what `workflowsOf` reads."""
    return world["state"].corpus.create_and_establish(
        kind="workflow",
        body={"name": name, "about": "a Workflow the slash palette can offer",
              "activities": [{"key": "do", "what": "Do it.", "done_when": "It is done."}]},
        attributed_to=world["who"]["@brian"])


def _open(world, page, conversation, name="Quiet round four"):
    page.goto(world["base"] + f"/quiet#/c/{conversation}")
    page.get_by_role("heading", name=name, exact=True).wait_for()
    page.locator(".qc-post").first.wait_for()
    return page.get_by_label("Continue the conversation")


def _pick(page, typed, row_text, where=".fc-prow"):
    """Type a trigger and take a row from the palette it opens.

    The palette is drawn in the frame's layer (`fluid/composer/Float.tsx`),
    which Quiet's composer mounts -- so these rows are the Mentis composer's
    own `.fc-prow` / `.fc-slash-item`, not markup written for Quiet."""
    field = page.get_by_label("Continue the conversation")
    field.click()
    field.fill(typed)
    row = page.locator(where).filter(has_text=row_text).first
    row.wait_for()
    row.click()
    return field


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_an_at_pick_addresses_the_participant_in_the_posted_body(world, engine):
    """`@` IS THE ADDRESSING NOW -- the native "Ask someone to work…" <select>
    is gone. A pick addresses them AND asks them to work (the palette's one
    selection for the ordinary thing), so the body carries `addressed_to` and
    a `dispatch` entry, and the record holds the addressee."""
    playwright = pytest.importorskip("playwright.sync_api")
    world["state"].agents.execution = FakeExecution([
        {"id": "claude", "kind": "acp", "available": True, "reason": None,
         "version": "fixture", "models": [{"id": "opus", "name": "Opus"}],
         "efforts": ["high", "low"], "supports": {"mcp": ["stdio"]}},
    ])
    vera = world["who"]["@Vera"]
    conversation = _a_conversation(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            field = _open(world, page, conversation)

            # ESCAPE DISMISSES AND THE CARET COMES BACK: the palette is an
            # offer layered over what is typed, never a mode.
            field.click()
            field.fill("Before anything else, @Ver")
            page.locator(".fc-palette").wait_for()
            page.keyboard.press("Escape")
            page.locator(".fc-palette").wait_for(state="detached")
            assert field.evaluate("el => el === document.activeElement")

            _pick(page, "Please look at this, @Ver", "@Vera")
            page.get_by_title(SETTINGS_TOGGLE).wait_for()
            # The token is written into the words, sigil included.
            assert "@Vera" in field.input_value(), field.input_value()
            _shot(page, f"r4a-at-palette-{engine}-{WIDE['width']}.png")

            with page.expect_request("**/fluid/api/posts") as sent:
                field.press("Control+Enter")
            body = sent.value.post_data_json
            assert body["addressed_to"] == [vera], body
            assert body["action"] == "ask-participant", body
            assert [d["participant"] for d in body["dispatch"]] == [vera], body
            page.wait_for_function("document.querySelector('#qc-compose')?.value === ''")
            assert not errors, errors
        finally:
            browser_.close()

    turns = get(world, f"/api/conversations/{conversation}?batch=2")["turns"]
    [posted] = [t for t in turns if "@Vera" in _said(t)]
    assert [a["participant"] for a in posted["addressees"]] == [vera], posted
    assert [s["participant"] for s in world["sent"]] == [vera], world["sent"]


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_hash_pick_attaches_the_topic_and_marks_the_words_that_name_it(world, engine):
    """`#` FILES THE POST UNDER THE TOPIC and marks the characters that name
    it -- two facts, which `bodyOf` sends as `topics` and as a `topic` part.
    Record only, so this case asks nothing of any runtime."""
    playwright = pytest.importorskip("playwright.sync_api")
    cv = world["cv"]
    conversation = _a_conversation(world)
    topic = cv.open_topic(conversation, "Thermal drift", about="The drift itself.")
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            field = _open(world, page, conversation)
            # A PHRASE, NOT ONE WORD: the trigger's query runs across the
            # single space inside a Topic's name (`composer/trigger.ts`).
            _pick(page, "Filed under #Thermal dri", "#Thermal drift")
            page.get_by_text("under #Thermal drift", exact=True).wait_for()
            assert "#Thermal drift" in field.input_value(), field.input_value()
            _shot(page, f"r4a-hash-chip-{engine}-{WIDE['width']}.png")

            page.get_by_label("Posting action").select_option("record-only")
            with page.expect_request("**/fluid/api/posts") as sent:
                page.get_by_role("button", name="Post ↑", exact=True).click()
            body = sent.value.post_data_json
            assert body["topics"] == [topic], body
            assert body["action"] == "record-only", body
            marked = [q for q in body["parts"] if q.get("type") == "topic"]
            assert marked == [{"type": "topic", "ref": topic, "text": "#Thermal drift"}], body["parts"]
            page.wait_for_function("document.querySelector('#qc-compose')?.value === ''")
            assert not errors, errors
        finally:
            browser_.close()

    turns = get(world, f"/api/conversations/{conversation}?batch=2")["turns"]
    [posted] = [t for t in turns if "Thermal drift" in _said(t)]
    assert cv.topics_of(posted["id"], conversation) == [topic]
    assert not world["sent"], "record only asks nobody and runs nothing"


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_slash_pick_selects_an_established_workflow(world, engine):
    """`/` OFFERS THE ESTABLISHED WORKFLOWS, and picking one names it for this
    request exactly as "Use…" names governed material: the `/…` token goes,
    `draft.use` holds it, and the body sends it as `governed`."""
    playwright = pytest.importorskip("playwright.sync_api")
    workflow = _a_workflow(world)
    conversation = _a_conversation(world)
    # The register is what the palette reads, so check the fixture is there
    # before blaming the interface for an empty palette.
    standing = _fluid_get(world, "/fluid/api/governed?state=standing&kind=workflow&limit=200")
    assert [r["summary"] for r in standing["groups"]["standing"]] == ["Round four check"], standing
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            field = _open(world, page, conversation)
            field.click()
            field.fill("/Round")
            row = page.locator(f'[data-workflow="{workflow}"]')
            # The Workflows are read once typing has paused (`useWorkflows`).
            row.wait_for(timeout=10_000)
            _shot(page, f"r4a-slash-palette-{engine}-{WIDE['width']}.png")
            row.click()
            page.get_by_text("uses Round four check", exact=True).wait_for()
            # The token is dropped from the words; the Workflow is the chip.
            assert field.input_value() == "", repr(field.input_value())

            field.fill("Do the thing, under that Workflow.")
            with page.expect_request("**/fluid/api/posts") as sent:
                field.press("Control+Enter")
            body = sent.value.post_data_json
            assert body["action"] == "ask-mentis", body
            assert body["governed"] == [workflow], body
            page.wait_for_function("document.querySelector('#qc-compose')?.value === ''")
            assert not errors, errors
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("size", [WIDE, NARROW])
def test_a_slash_pick_leaves_an_earlier_reference_marked_not_plain_text(world, engine, size):
    """DROPPING THE `/…` TOKEN MOVES THE MARKS WITH THE CHARACTERS.

    A mark is a claim about particular characters, by their offset. Removing
    the `/…` token moves everything after it to the left, so a `#` reference
    authored EARLIER IN THE LINE has to move too -- otherwise it is dropped,
    and what the writer marked goes out as plain prose while the Topic
    membership (a separate fact) survives, so nothing on the screen says
    anything was lost.

    The independent review of ddca038 found exactly that (its Turn
    ent-466df8486625, evidence adm-1f977fcfa4d1): Quiet removed the token
    without shifting the marks, where Fluid's own handler shifts them. Both are
    now the one rule, `choose.ts`'s `retexted`. This case is the reviewer's
    scenario, end to end, and it ends at the POST body because the chip and the
    words look identical either way."""
    playwright = pytest.importorskip("playwright.sync_api")
    cv = world["cv"]
    workflow = _a_workflow(world, "Independent review workflow")
    conversation = _a_conversation(world)
    topic = cv.open_topic(conversation, "Thermal drift", about="The drift itself.")
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=size)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            field = _open(world, page, conversation)

            # The `/…` token is typed FIRST and the reference authored after it,
            # so the token sits before the marked characters.
            _pick(page, "/Independent and #Thermal dri", "#Thermal drift")
            page.get_by_text("under #Thermal drift", exact=True).wait_for()
            assert field.input_value() == "/Independent and #Thermal drift ", repr(field.input_value())

            # Back into the token the writer left behind: whether a palette is
            # open is re-derived from (text, caret), so putting the caret inside
            # `/Independent` is all it takes to be offered the Workflow again.
            field.click()
            field.press("Control+Home")
            for _ in range(len("/Independent")):
                field.press("ArrowRight")
            row = page.locator(f'[data-workflow="{workflow}"]')
            # The Workflows are read once typing has paused (`useWorkflows`).
            row.wait_for(timeout=10_000)
            row.click()
            page.get_by_text("uses Independent review workflow", exact=True).wait_for()
            # The token is gone, and one space is kept where it sat.
            assert field.input_value() == "and #Thermal drift ", repr(field.input_value())
            _shot(page, f"r4a-slash-before-hash-{engine}-{size['width']}.png")

            page.get_by_label("Posting action").select_option("record-only")
            with page.expect_request("**/fluid/api/posts") as sent:
                field.press("Control+Enter")
            body = sent.value.post_data_json
            # BOTH FACTS, as Fluid would send them: membership, and the
            # authored reference as its own part carrying the Topic's identity
            # -- at its new offset, not left behind as prose.
            assert body["topics"] == [topic], body
            assert body["parts"] == [
                {"type": "text", "text": "and "},
                {"type": "topic", "ref": topic, "text": "#Thermal drift"},
            ], body["parts"]
            assert not any("#Thermal drift" in (q.get("text") or "")
                           for q in body["parts"] if q.get("type") == "text"), body["parts"]
            assert body["action"] == "record-only", body
            page.wait_for_function("document.querySelector('#qc-compose')?.value === ''")
            assert not errors, errors
        finally:
            browser_.close()

    # And the record holds the reference, not only the words.
    turns = get(world, f"/api/conversations/{conversation}?batch=2")["turns"]
    [posted] = [t for t in turns if "Thermal drift" in _said(t)]
    assert [q for q in posted["parts"] if q.get("type") == "topic"], posted["parts"]
    assert cv.topics_of(posted["id"], conversation) == [topic]


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("width", [390, 1440])
def test_the_composer_is_painted_on_the_docks_own_ground(world, engine, width):
    """ONE GROUND, NOT THREE. The composer sits on the dock, which paints the
    page (`--canvas`), so it is that colour -- not a `--wash-strong` panel
    inside it -- and its own controls do not add a third `--surface-sunken`
    ground on top of that. Measured in light and in chosen dark, because a
    token resolves differently in each."""
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport={"width": width, "height": 900})
            for theme in ("light", "dark"):
                page.add_init_script(
                    f"try {{ localStorage.setItem('mentis:theme', '{theme}') }} catch {{}}")
                field = _open(world, page, conversation)
                # Focused by keyboard, so the tool row is open; and the pointer
                # is moved away first, because the row opening moves the
                # controls up under a pointer left where the field was, and a
                # hovered control is painted on purpose.
                field.focus()
                page.get_by_label("Posting action").wait_for(state="visible")
                page.mouse.move(0, 0)
                ground = page.evaluate("""() => {
                  const paint = (el) => getComputedStyle(el).backgroundColor
                  const composer = document.querySelector('.qc-composer')
                  return {
                    composer: paint(composer),
                    dock: paint(document.querySelector('.qc-dock')),
                    action: paint(composer.querySelector('select[aria-label="Posting action"]')),
                    field: paint(composer.querySelector('#qc-compose')),
                  }
                }""")
                assert ground["composer"] == ground["dock"], (theme, ground)
                # Transparent, so whatever the composer stands on shows
                # through: no third ground inside the second.
                for inner in ("action", "field"):
                    assert ground[inner] == "rgba(0, 0, 0, 0)", (theme, inner, ground)
                _shot(page, f"r4a-ground-{theme}-{engine}-{width}.png")
        finally:
            browser_.close()


# -- the participant filter ---------------------------------------------------
#
# WHY THIS CASE DOES NOT DRIVE THE MOUNTED COMPONENT. `src/quiet/filter/` is a
# DECLARED SEAM: the integrator mounts `WhoFilter`, by this round's own
# instruction, so nothing in the built bundle imports it yet and the browser
# has no mounted strip to hover. What CAN be checked in a browser now is the
# rule that decides at rest from expanded -- `filter.css`'s own -- over the
# component's own class structure, and that is what this does: the stylesheet
# is the real file, and every class the fixture uses is asserted to be one
# `WhoFilter.tsx` actually constructs, so the two cannot drift apart. The
# component's reading of who is active, the "+N" count, toggling and what the
# filter then hides (`filterTurns`) are exact in
# `apps/fluid-web/tests/quiet_composer_unit.mjs`.

#: One conversation's strip as WhoFilter renders it: @Vera is working (so she
#: is active), @brian and @Quill are not, so at rest there is "All", one face
#: and "+2". The faces are `Who show="avatar" size={20}`'s own markup, inline
#: style included, so the shot shows what a reader would see.
def _face(initial, colour, working=False):
    return (f'<span class="fwho fwho-avatar{" fwho-working" if working else ""}" role="img">'
            f'<span class="avatar{" fwho-live" if working else ""}" aria-hidden="true"'
            f' data-initial="{initial}" style="background: var(--who-{colour}); width: 20px;'
            f' height: 20px; font-size: 9px; line-height: 20px;"></span></span>')


STRIP = f"""
<div class="qc-who" role="group" aria-label="Show posts by" data-working="1">
  <button type="button" class="qc-who-all" aria-pressed="true">All</button>
  <div class="qc-who-scroll">
    <button type="button" class="qc-who-chip qc-who-active" data-author="ent-vera"
      data-working="true" aria-pressed="true" aria-label="Vera, working now">
      {_face("V", 2, working=True)}</button>
    <button type="button" class="qc-who-chip" data-author="ent-brian"
      aria-pressed="true" aria-label="brian">{_face("B", 4)}</button>
    <button type="button" class="qc-who-chip" data-author="ent-quill"
      aria-pressed="true" aria-label="Quill">{_face("Q", 6)}</button>
  </div>
  <span class="qc-who-rest" aria-hidden="true">+2</span>
</div>
"""


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_filter_shows_who_is_active_at_rest_and_everyone_on_hover_or_focus(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    css = (WEB / "filter" / "filter.css").read_text(encoding="utf8")
    source = (WEB / "filter" / "WhoFilter.tsx").read_text(encoding="utf8")
    # THE FIXTURE IS TIED TO THE COMPONENT: every class below is one the
    # component builds, so this case cannot pass over markup Quiet no longer
    # renders. The strip's three classes plus the two the rule names.
    for name in ("qc-who", "qc-who-all", "qc-who-scroll", "qc-who-chip",
                 "qc-who-active", "qc-who-rest"):
        assert re.search(r"\b" + name + r"\b", source), f"WhoFilter.tsx builds no {name}"
    conversation = _a_conversation(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            _open(world, page, conversation)
            page.evaluate("""([css, html]) => {
              const style = document.createElement('style')
              style.textContent = css
              document.head.append(style)
              const slot = document.createElement('div')
              slot.innerHTML = html
              document.querySelector('.qc-heading').prepend(slot.firstElementChild)
            }""", [css, STRIP])
            strip = page.locator(".qc-who")
            chips = page.locator(".qc-who-chip")
            rest = page.locator(".qc-who-rest")

            # AT REST: only who is active (working now, or filtered by) plus
            # "+N" for everyone else.
            assert chips.count() == 3
            assert [chips.nth(i).is_visible() for i in range(3)] == [True, False, False]
            assert rest.is_visible()
            at_rest = strip.bounding_box()
            _shot(page, f"r4a-filter-rest-{engine}-{WIDE['width']}.png")

            # HOVER opens it out to everyone, and puts the "+N" away.
            strip.hover()
            page.wait_for_function(
                "document.querySelectorAll('.qc-who-chip')[2].getBoundingClientRect().width > 0")
            assert all(chips.nth(i).is_visible() for i in range(3))
            assert not rest.is_visible()
            opened = strip.bounding_box()
            assert opened["width"] >= at_rest["width"], (at_rest, opened)
            _shot(page, f"r4a-filter-open-{engine}-{WIDE['width']}.png")

            # AND SO DOES KEYBOARD FOCUS: hover alone would make everyone but
            # the active few unreachable without a pointer.
            page.mouse.move(0, 0)
            page.wait_for_function(
                "document.querySelectorAll('.qc-who-chip')[2].getBoundingClientRect().width === 0")
            page.locator(".qc-who-all").focus()
            page.wait_for_function(
                "document.querySelectorAll('.qc-who-chip')[2].getBoundingClientRect().width > 0")
            assert all(chips.nth(i).is_visible() for i in range(3))
            assert not rest.is_visible()
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium"])
@pytest.mark.parametrize("size", [WIDE, NARROW])
def test_the_composer_with_a_palette_open_and_the_filter_both_ways(world, engine, size):
    """THE EVIDENCE SHOT, and the one claim it has to carry at both sizes: the
    palette fits inside the window and the filter fits inside the column. The
    cases above are what the behaviour is judged by; this is what the owner
    looks at (MENTIS_R4A_EVIDENCE)."""
    playwright = pytest.importorskip("playwright.sync_api")
    css = (WEB / "filter" / "filter.css").read_text(encoding="utf8")
    conversation = _a_conversation(world)
    world["cv"].open_topic(conversation, "Thermal drift", about="The drift itself.")
    w = size["width"]
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=size)
            _open(world, page, conversation)
            page.evaluate("""([css, html]) => {
              const style = document.createElement('style')
              style.textContent = css
              document.head.append(style)
              const slot = document.createElement('div')
              slot.innerHTML = html
              document.querySelector('.qc-heading').prepend(slot.firstElementChild)
            }""", [css, STRIP])
            _shot(page, f"r4a-filter-at-rest-{engine}-{w}.png")
            page.locator(".qc-who").hover()
            page.wait_for_function(
                "document.querySelectorAll('.qc-who-chip')[2].getBoundingClientRect().width > 0")
            strip = page.locator(".qc-who").bounding_box()
            assert strip["x"] >= -1 and strip["x"] + strip["width"] <= w + 1, strip
            _shot(page, f"r4a-filter-expanded-{engine}-{w}.png")

            page.mouse.move(0, 0)
            _pick(page, "Filed under #Thermal dri", "#Thermal drift")
            page.get_by_text("under #Thermal drift", exact=True).wait_for()
            field = page.get_by_label("Continue the conversation")
            field.click()
            field.fill("Filed under #Thermal drift, and @Ver")
            page.locator(".fc-palette").wait_for()
            panel = page.locator(".fx-float.qc-float").bounding_box()
            assert panel["x"] >= -1 and panel["x"] + panel["width"] <= w + 1, panel
            assert panel["y"] >= -1 and panel["y"] + panel["height"] <= size["height"] + 1, panel
            _shot(page, f"r4a-composer-palette-{engine}-{w}.png")
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_filter_strip_fits_the_narrow_reading_column(world, engine):
    """Quiet is an app shell at every width: the strip scrolls sideways in one
    row rather than wrapping or pushing the column wider."""
    playwright = pytest.importorskip("playwright.sync_api")
    css = (WEB / "filter" / "filter.css").read_text(encoding="utf8")
    conversation = _a_conversation(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=NARROW)
            _open(world, page, conversation)
            page.evaluate("""([css, html]) => {
              const style = document.createElement('style')
              style.textContent = css
              document.head.append(style)
              const slot = document.createElement('div')
              slot.innerHTML = html
              document.querySelector('.qc-heading').prepend(slot.firstElementChild)
            }""", [css, STRIP])
            page.locator(".qc-who").hover()
            page.wait_for_function(
                "document.querySelectorAll('.qc-who-chip')[2].getBoundingClientRect().width > 0")
            fits = page.evaluate("""() => {
              const el = document.querySelector('.qc-who')
              const row = document.querySelector('.qc-who-scroll')
              return { one_row: row.clientHeight <= 32, inside: el.getBoundingClientRect().right,
                       page: document.documentElement.scrollWidth <= innerWidth }
            }""")
            assert fits["one_row"], fits
            assert fits["inside"] <= NARROW["width"] + 1, fits
            assert fits["page"], fits
            _shot(page, f"r4a-filter-narrow-{engine}-{NARROW['width']}.png")
        finally:
            browser_.close()
