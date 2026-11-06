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
            page.get_by_label("Ask someone to work").wait_for()
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
            page = browser_.new_page(viewport=WIDE)
            _open(world, page, conversation)
            page.get_by_label("Continue the conversation").fill("Please take a look at this.")

            ask = page.get_by_label("Ask someone to work")
            ask.focus()
            ask.locator("option", has_text="Vera").wait_for(state="attached")
            ask.select_option(label="@Vera")

            page.get_by_title("Will be asked to work: open to choose runtime, model and effort").click()
            runtime_btn = page.get_by_role("button", name="claude", exact=True)
            runtime_btn.wait_for()
            runtime_btn.click()
            model_btn = page.get_by_role("button", name="Opus", exact=True)
            model_btn.wait_for()
            page.wait_for_timeout(200)
            model_btn.click()
            effort_btn = page.get_by_role("button", name="high", exact=True)
            effort_btn.wait_for()
            page.wait_for_timeout(200)
            effort_btn.click()

            page.get_by_role("button", name="Ask @Vera", exact=False).click()
            page.get_by_label("Ask someone to work").wait_for()
        finally:
            browser_.close()

    [sent] = [s for s in world["sent"] if s.get("participant") == vera]
    assert sent["runtime"] == "claude"
    assert sent["model"] == "opus"
    assert sent["effort"] == "high"
