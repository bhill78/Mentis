"""Quiet Chat round 2, package C -- the composer -- against real Mentis HTTP
routes on a disposable fixture Brain.

What P0 already proved (the dock sits outside the scrolling region, at all)
is `test_quiet_seam_browser.py`'s; this file is what package C itself added:
the composer's box staying inside the viewport at both ends of a long
conversation, the textarea starting short and growing to a cap, the
runtime/model/effort cascade reachable for an `ask-participant` dispatch with
the chosen values reaching the server exactly as Fluid sends them, the
posting-action control saying in words what each way of sending does, and an
ordinary Ask Mentis post staying exactly what it was.

Round 4 removed the "Ask someone to work…" <select>: these cases now address
with `@` through the Mentis composer's own palette (`_ask`), and every claim
they make about the cascade and the dispatch is otherwise unchanged. What `@`,
`#` and `/` themselves do is `test_quiet_r4_composer_browser.py`'s.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
"""
from __future__ import annotations

import os

import pytest

from mentis.conversation import text
from mentis.execution import FakeExecution
from tests._loop import get, world  # noqa: F401

browser = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

WIDE = {"width": 1440, "height": 1000}

#: THE SAME DISCOVERY OF WHAT ACTUALLY SCROLLED test_quiet_seam_browser.py
#: uses -- duplicated rather than imported, so this file stands on its own.
SCROLLER = """
  const scroller = () => {
    const stream = document.getElementById('qc-stream')
    const wide = window.matchMedia('(min-width: 901px)').matches
    if (wide && stream && stream.scrollHeight - stream.clientHeight > 1) return stream
    return document.scrollingElement
  }
"""
TOP = "() => {" + SCROLLER + " const el = scroller(); el.scrollTop = 0; return el.scrollTop }"
PUSH = "() => {" + SCROLLER + " const el = scroller(); el.scrollTop = el.scrollHeight; return el.scrollTop }"


def _a_long_conversation(world, name="Quiet composer"):
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation(name, about="Room enough to scroll past.")
    cv.join(owner, cid)
    cv.join(world["who"]["@Vera"], cid)
    for n in range(48):
        cv.say(cid, owner, [text(f"A post long enough to scroll past, number {n}.")])
    return cid


def _open(world, page, conversation, name="Quiet composer"):
    page.goto(world["base"] + f"/quiet#/c/{conversation}")
    page.get_by_role("heading", name=name, exact=True).wait_for()
    page.locator(".qc-post").first.wait_for()
    page.get_by_label("Continue the conversation").wait_for()


#: THE ADDRESSEE'S CHIP, which opens the shared runtime/model/effort cascade.
SETTINGS_TOGGLE = "Will be asked to work: open to choose runtime, model and effort"


def _ask(page, alias="@Vera", before=""):
    """Ask somebody to work the way the composer offers it now.

    Round 4 removed the native "Ask someone to work…" <select>: addressing is
    `@`, through the Mentis composer's own palette (`fluid/composer/Palette`),
    so these cases type it as a reader does. The words typed before the `@` are
    the draft's; `@Vera` stays in them afterwards, because an addressee whose
    name is deleted from the sentence is no longer addressed by it.
    """
    field = page.get_by_label("Continue the conversation")
    field.click()
    field.fill((before + " " if before else "") + alias[:4])
    row = page.locator(".fc-prow").filter(has_text=alias).locator(".fc-pmain").first
    row.wait_for()
    row.click()
    page.get_by_title(SETTINGS_TOGGLE).wait_for()
    return field


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_composer_stays_inside_the_viewport_scrolled_to_top_and_to_bottom(world, engine):
    """§4: the dock sits outside the scrolling region (P0's), but the
    composer's own box must still fit inside the viewport wherever the
    reader has scrolled to -- at the very top of a long conversation and
    pushed all the way to the bottom."""
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_long_conversation(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            _open(world, page, conversation)
            for move, label in ((TOP, "top"), (PUSH, "bottom")):
                page.evaluate(move)
                box = page.locator(".qc-composer").bounding_box()
                assert box, f"the composer has no box, scrolled to the {label}"
                assert box["y"] >= -1, (
                    f"scrolled to the {label}: the composer's box starts above the "
                    f"viewport ({box})")
                assert box["y"] + box["height"] <= WIDE["height"] + 1, (
                    f"scrolled to the {label}: the composer's box ({box}) reaches "
                    f"past the viewport's {WIDE['height']}px")
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_composer_stays_inside_the_viewport_with_settings_open_and_the_textarea_at_cap(
        world, engine):
    """The dock's row is content-sized (`grid-template-rows: ... auto` in
    layout.css), so nothing stopped it rendering taller than the space
    `.qc-reading` actually had left: at 1440x800, with the settings panel
    open and a long draft growing the textarea to its 320px cap, the
    composer's box reached 902px -- past the 800px viewport. `.qc-dock`'s cap
    (layout.css) and `.qc-composer`'s matching one (composer.css) are what
    stop that now."""
    playwright = pytest.importorskip("playwright.sync_api")
    world["state"].agents.execution = FakeExecution([
        {"id": "claude", "kind": "acp", "available": True, "reason": None,
         "version": "test", "models": [{"id": "opus", "name": "Opus"}],
         "efforts": ["high", "low", "medium"], "supports": {"mcp": ["stdio"]}},
    ])
    conversation = _a_long_conversation(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport={"width": 1440, "height": 800})
            _open(world, page, conversation)
            field = _ask(page)
            page.get_by_title(SETTINGS_TOGGLE).click()
            page.get_by_text("will be asked to work", exact=True).wait_for()
            page.get_by_role("button", name="claude", exact=True).click()
            page.wait_for_timeout(200)
            page.get_by_role("button", name="Opus", exact=True).click()
            page.wait_for_timeout(200)
            page.get_by_role("button", name="high", exact=True).click()
            field.fill("@Vera\n" + "\n".join(
                f"Line {n} of a long draft that keeps going." for n in range(20)))
            page.wait_for_timeout(150)
            for move, label in ((TOP, "top"), (PUSH, "bottom")):
                page.evaluate(move)
                box = page.locator(".qc-composer").bounding_box()
                assert box, f"the composer has no box, scrolled to the {label}"
                assert box["y"] + box["height"] <= 801, (
                    f"scrolled to the {label}: the composer's box ({box}) reaches "
                    f"past the viewport's 800px")
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_textarea_starts_shorter_than_110px_and_grows_with_content_to_a_cap(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_long_conversation(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            _open(world, page, conversation)
            field = page.get_by_label("Continue the conversation")
            empty = field.bounding_box()["height"]
            assert empty < 110, f"the empty composer is {empty}px, not shorter than today's 110px"
            field.fill("\n".join(f"Line {n} of a longer message that keeps going." for n in range(14)))
            grown = field.bounding_box()["height"]
            assert grown > empty, (
                f"the composer did not grow with multi-line content ({empty}px -> {grown}px)")
            assert grown <= 330, f"the composer grew past its cap ({grown}px)"
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_posting_action_control_says_what_each_way_of_sending_does(world, engine):
    """Readable text, not a tooltip nobody opened: Ask Mentis deliberately
    carries no runtime (`ACTION_WHY['ask-mentis']`), asking someone asks only
    them, and record-only asks and runs nothing."""
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_long_conversation(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            _open(world, page, conversation)
            said = page.get_by_label("what each way of sending does").inner_text()
            assert "you pick no runtime" in said, said
            assert "Nobody else is asked" in said, said
            assert "nothing runs" in said, said
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_asking_mentis_with_no_dispatch_is_unchanged_field_for_field(world, engine):
    """Posting semantics unchanged: an ordinary Ask Mentis post, with nobody
    marked for work, is identical to what it always was."""
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_long_conversation(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            _open(world, page, conversation)
            page.get_by_label("Continue the conversation").fill("An ordinary Ask Mentis post.")
            page.get_by_role("button", name="Ask Mentis ↑", exact=True).click()
            # The posted draft is cleared, which is what says the post went in.
            page.wait_for_function("document.querySelector('#qc-compose')?.value === ''")
        finally:
            browser_.close()

    turns = get(world, f"/api/conversations/{conversation}?batch=1")["turns"]
    [last] = [t for t in turns
              if any(p.get("type") == "text" and p.get("text", "").strip() == "An ordinary Ask Mentis post."
                     for p in t["parts"])]
    # Nobody was addressed and nobody was marked for work -- the one thing
    # dispatchBody would have changed, had it been called here.
    assert last["addressees"] == []
    assert last["chose"] is None


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_asking_a_participant_carries_the_chosen_runtime_model_and_effort(world, engine, monkeypatch):
    """§4 + the owner's authorized item 3: the runtime -> model -> effort
    cascade (`composer/Settings.tsx`) is reachable for an `ask-participant`
    dispatch, and the chosen values arrive in `world["sent"]` exactly as
    Fluid's own composer would send them (`mentis/conversation/posting.py`'s
    `later.append(dict(..., runtime=..., model=..., effort=...))`)."""
    playwright = pytest.importorskip("playwright.sync_api")
    world["state"].agents.execution = FakeExecution([
        {"id": "claude", "kind": "acp", "available": True, "reason": None,
         "version": "test", "models": [{"id": "opus", "name": "Opus"}],
         "efforts": ["high", "low"], "supports": {"mcp": ["stdio"]}},
    ])
    vera = world["who"]["@Vera"]
    conversation = _a_long_conversation(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport={"width": 1440, "height": 800})
            _open(world, page, conversation)
            _ask(page, before="Please take a look at this.")

            page.get_by_title(SETTINGS_TOGGLE).click()
            runtime_btn = page.get_by_role("button", name="claude", exact=True)
            runtime_btn.wait_for()
            runtime_btn.click()
            model_btn = page.get_by_role("button", name="Opus", exact=True)
            model_btn.wait_for()
            page.wait_for_timeout(200)
            model_btn.click()
            for move in (TOP, PUSH):
                page.evaluate(move)
                box = page.locator(".qc-composer").bounding_box()
                assert box["y"] >= -1 and box["y"] + box["height"] <= 801, box
            page.get_by_label("Posting action").select_option("record-only")
            assert page.get_by_role("button", name="Post \u2191", exact=True).is_visible()
            page.get_by_label("Posting action").select_option("ask-mentis")
            effort_btn = page.get_by_role("button", name="high", exact=True)
            effort_btn.wait_for()
            page.wait_for_timeout(200)
            effort_btn.click()

            requests = []
            def drop_first(route):
                requests.append(route.request.post_data_json)
                if len(requests) == 1:
                    route.abort()
                else:
                    route.continue_()
            page.route("**/fluid/api/posts", drop_first)
            page.get_by_role("button", name="Ask @Vera", exact=False).click()
            page.get_by_role("alert").filter(has_text="Your draft is still here").wait_for()
            page.get_by_role("button", name="low", exact=True).click()
            page.get_by_role("button", name="Ask @Vera", exact=False).click()
            page.wait_for_function("document.querySelector('#qc-compose')?.value === ''")
            assert len(requests) == 2
            assert requests[0]["op"] != requests[1]["op"]
        finally:
            browser_.close()

    [sent] = [s for s in world["sent"] if s.get("participant") == vera]
    assert sent["runtime"] == "claude"
    assert sent["model"] == "opus"
    assert sent["effort"] == "low"
