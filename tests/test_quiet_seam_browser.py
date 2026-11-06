"""WHAT THE SEAM COMMIT PROMISED, as checks that can refuse it.

P0 splits one component and one stylesheet into ten packages' modules, makes
the reading column its own scroll container above 900px, and moves the
composer into a dock outside it. Three of those are claims a machine can test,
and one is a claim about everything NOT changing:

* THE PAGE STILL READS THE SAME. ``quiet_seam_baseline.json`` is the ARIA tree
  and the visible text of a fixture conversation, captured on the commit before
  the split (59749a8). The split page must equal it. That is "no visual
  regression" as something a machine can refuse rather than an opinion.
* THE COLUMN CONTINUES THROUGH THE HEADER. The header's centre cell and the
  stream share their left and right edges to within 1px, which is what one
  ``--qc-columns`` used by both rows is for.
* THE REGION THAT SCROLLS IS THE ONE EACH REGIME NAMES -- the stream above
  900px with the document still, the document at 900px and below with the
  stream still. This is the half of the scroll model that FAILS on 59749a8,
  and it is what makes a reset aimed at one of the two able to move anything.
* PAGING RETURNS THE READER TO THE TOP, in both regimes, from a verified
  nonzero position. Kept as a regression guard and reported as nothing more:
  it passes on 59749a8 as well, because a remounted page is briefly empty and
  the browser clamps the position for reasons of its own. See its docstring.
* THE RUN SHAPE ``api.ts`` DECLARES IS THE ONE THE HANDLER SENDS. The recorded
  response is committed; this suite asserts the recording still matches a live
  read, and ``apps/fluid-web/tests/quiet_seam_unit.mjs`` asserts the TypeScript
  declares exactly those keys. Either side drifting fails.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.

To RE-CAPTURE the baseline (only ever on the commit it is the baseline of),
set MENTIS_QUIET_SEAM_CAPTURE=1, and MENTIS_QUIET_SEAM_OUT to the tests
directory the files belong in.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import a_conversation, get, world  # noqa: F401

HERE = Path(__file__).parent
BASELINE = HERE / "quiet_seam_baseline.json"
RECORDED_RUN = HERE / "quiet_activity_run.json"
CAPTURE = os.environ.get("MENTIS_QUIET_SEAM_CAPTURE") == "1"
OUT = Path(os.environ.get("MENTIS_QUIET_SEAM_OUT") or HERE)

browser = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

WIDE = {"width": 1440, "height": 1000}
NARROW = {"width": 390, "height": 844}

#: WHATEVER ACTUALLY SCROLLED, discovered rather than named -- so the same
#: check runs against a build that has no stream at all, and fails there for
#: the real reason (the position was not reset) rather than for a missing id.
SCROLLER = """
  const scroller = () => {
    const stream = document.getElementById('qc-stream')
    const wide = window.matchMedia('(min-width: 901px)').matches
    if (wide && stream && stream.scrollHeight - stream.clientHeight > 1) return stream
    return document.scrollingElement
  }
"""
AT = "() => {" + SCROLLER + " return scroller().scrollTop }"
PUSH = ("() => {" + SCROLLER
        + " const el = scroller(); el.scrollTop = el.scrollHeight; return el.scrollTop }")


def _tidy(line: str) -> str:
    """The record's own ids and `ago`'s words are new on every run."""
    line = re.sub(r"\bent-[0-9a-f]+", "<id>", line)
    line = re.sub(r"\b\d+[mhd] ago\b", "<time>", line)
    return re.sub(r"\bjust now\b", "<time>", line).rstrip()


def _lines(raw: str) -> list[str]:
    return [_tidy(line) for line in raw.splitlines() if line.strip()]


#: THE VISIBLE WORDS, IN ORDER, read off the DOM rather than from innerText --
#: whose whitespace folding is the browser's own, and so would make two
#: engines disagree about a page neither of them had changed.
WORDS = """
() => {
  const out = []
  const walk = (node) => {
    for (const child of node.childNodes) {
      if (child.nodeType === 3) {
        const said = child.textContent.trim()
        if (said) out.push(said)
      } else if (child.nodeType === 1 && getComputedStyle(child).display !== 'none') {
        walk(child)
      }
    }
  }
  walk(document.querySelector('.qc'))
  return out
}
"""


def _seam(page) -> dict:
    """The page as a reader meets it: the ARIA tree, then the visible words."""
    return {
        "aria": _lines(page.locator(".qc").aria_snapshot()),
        "text": [_tidy(said) for said in page.evaluate(WORDS)],
    }


def _a_conversation_to_read(world):
    """A fixture conversation with the things a post can be, and nothing
    volatile: one topic, a filed post, a reply, and a deleted post."""
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation("Quiet seam", about="The page the baseline is of.")
    cv.join(owner, cid)
    topic = cv.open_topic(cid, "Reading", about="What the margin lists.")
    first = cv.say(cid, owner, [text("The first post, with a **word** in bold.")])
    cv.assign_topic(first, topic)
    for n in range(4):
        cv.say(cid, owner, [text(f"An ordinary post, number {n}.")])
    cv.say(cid, owner, [text("A reply to the first post.")], replies_to=first)
    return cid


def _open(world, page, conversation):
    page.goto(world["base"] + f"/quiet#/c/{conversation}")
    page.get_by_role("heading", name="Quiet seam", exact=True).wait_for()
    page.locator(".qc-post").first.wait_for()
    page.get_by_label("Continue the conversation").wait_for()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_split_page_reads_exactly_as_the_unsplit_one_did(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    conversation = _a_conversation_to_read(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            _open(world, page, conversation)
            got = _seam(page)
            assert errors == []
        finally:
            browser_.close()

    if CAPTURE:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "quiet_seam_baseline.json").write_text(
            json.dumps(got, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        pytest.skip("captured the baseline; nothing was asserted against it")

    want = json.loads(BASELINE.read_text(encoding="utf-8"))
    # Named apart so a failure says WHICH of the two drifted.
    assert got["aria"] == want["aria"], "the ARIA tree is not the one the baseline holds"
    assert got["text"] == want["text"], "the visible text is not the one the baseline holds"


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_reading_column_continues_through_the_header(world, engine):
    """ONE COLUMN TEMPLATE, USED BY BOTH ROWS. The header's centre cell is
    where A puts the conversation's title; if it does not sit over the stream,
    the title will not either, and no package can fix that from its own
    file."""
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation_to_read(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            _open(world, page, conversation)
            title = page.locator(".qc-cell-title").bounding_box()
            stream = page.locator("#qc-stream").bounding_box()
            assert title and stream, "the header's centre cell and the stream must both exist"
            assert abs(title["x"] - stream["x"]) <= 1, (
                f"left edges differ: header {title['x']}, stream {stream['x']}")
            assert abs((title["x"] + title["width"]) - (stream["x"] + stream["width"])) <= 1, (
                f"right edges differ: header {title}, stream {stream}")
            # The stream is the region that scrolls, not the page.
            assert page.evaluate(
                "() => document.documentElement.scrollHeight <= innerHeight + 1")
        finally:
            browser_.close()


#: Whether each candidate container has anything to scroll. The pair is the
#: whole point: "the reading column scrolls" is only true if the document
#: does NOT, and a reset aimed at the wrong one of the two moves nothing.
REGIONS = """
() => {
  const scrolls = (el) => !!el && el.scrollHeight - el.clientHeight > 1
  const stream = document.getElementById('qc-stream')
  return {
    stream_exists: !!stream,
    stream: scrolls(stream),
    document: scrolls(document.scrollingElement),
  }
}
"""


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_region_that_scrolls_is_the_one_each_regime_names(world, engine):
    """THE ASSERTION SHOWN FAILING ON 59749a8. Above 900px the reading column
    is its own scroll container and the document does not move; at 900px and
    below the document scrolls and the stream has nothing to scroll -- which
    is exactly why `Flow.move` cannot hard-code one of them. The stream
    element is in the DOM at both widths, so calling `scrollTo` on it narrow
    would succeed while moving nothing.

    On the commit before P0 there is no stream and the document scrolls at
    1440px, so the wide half of this is false there."""
    playwright = pytest.importorskip("playwright.sync_api")
    cv, owner = world["cv"], world["who"]["@brian"]
    conversation = a_conversation(world, "Quiet regimes")
    cv.join(owner, conversation)
    for n in range(48):
        cv.say(conversation, owner, [text(f"A post long enough to scroll past, number {n}.")])

    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            for viewport, wide in ((WIDE, True), (NARROW, False)):
                page = browser_.new_page(viewport=viewport)
                try:
                    page.goto(world["base"] + f"/quiet#/c/{conversation}")
                    page.get_by_role("heading", name="Quiet regimes", exact=True).wait_for()
                    page.locator(".qc-post").first.wait_for()
                    page.get_by_label("Continue the conversation").wait_for()
                    got = page.evaluate(REGIONS)
                    # The substantive half first, so a build that scrolls the
                    # wrong thing says so rather than saying a name is missing.
                    assert got["document"] is not wide, (
                        f"{viewport['width']}px: the document "
                        f"{'scrolls' if got['document'] else 'does not scroll'} "
                        f"where it should {'not' if wide else ''}: {got}")
                    assert got["stream_exists"], "the reading column has no stream to scroll"
                    assert got["stream"] is wide, f"{viewport['width']}px: {got}"
                    # The composer is reachable without reading to the end,
                    # in both regimes: in the dock above 900px, stuck to the
                    # viewport's lower edge below it.
                    page.evaluate(PUSH)
                    dock = page.locator(".qc-dock").bounding_box()
                    assert dock and dock["y"] < viewport["height"], (
                        f"{viewport['width']}px: the dock is off screen at {dock}")
                finally:
                    page.close()
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_paging_returns_the_reader_to_the_top_in_both_regimes(world, engine):
    """A REGRESSION GUARD, AND NOT EVIDENCE OF THE CHANGE -- said plainly,
    because the plan asked for this one to be shown failing on 59749a8 and it
    does not.

    Paging remounts the page, so the container is empty for an instant and the
    browser clamps the position to the new maximum; the reader therefore ends
    at the top whether or not anything reset them deliberately. Measured on
    59749a8: this passes there, at both viewports. What the deliberate reset
    is really needed for -- that it acts on the container which actually
    scrolled in this regime -- is asserted by the test above instead.

    Kept because the position IS pushed to a verified nonzero place first, so
    it still refuses a build where paging leaves the reader mid-conversation
    for any other reason."""
    playwright = pytest.importorskip("playwright.sync_api")
    cv, owner = world["cv"], world["who"]["@brian"]
    conversation = a_conversation(world, "Quiet paging")
    cv.join(owner, conversation)
    for n in range(48):
        cv.say(conversation, owner, [text(f"A post long enough to scroll past, number {n}.")])

    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            for viewport in (WIDE, NARROW):
                page = browser_.new_page(viewport=viewport)
                try:
                    page.goto(world["base"] + f"/quiet#/c/{conversation}")
                    page.get_by_role("heading", name="Quiet paging", exact=True).wait_for()
                    page.locator(".qc-post").first.wait_for()
                    pushed = page.evaluate(PUSH)
                    assert pushed and pushed > 0, (
                        f"{viewport['width']}px: nothing scrolled, so the reset proves nothing")
                    assert page.evaluate(AT) > 0
                    page.get_by_role("button", name="Older posts", exact=False).click()
                    page.get_by_role("button", name="Latest posts", exact=True).wait_for()
                    assert page.evaluate(AT) == 0, (
                        f"{viewport['width']}px: paging left the reader at "
                        f"{page.evaluate(AT)} instead of the top")
                finally:
                    page.close()
        finally:
            browser_.close()


def test_the_declared_run_shape_is_the_one_the_handler_sends(world):
    """`api.ts` under-declared /api/activity's run rows (ent-dffb798c7e65), so
    a reader of that file could not see what it was being sent. The recording
    committed beside this file is what the handler actually sends; the client's
    own suite asserts the TypeScript declares exactly these keys. A field added
    or dropped on either side fails here or there."""
    cv, st = world["cv"], world["state"]
    care = world["steward"]
    conversation = a_conversation(world, "Quiet run shape")
    run = cv.record_act(actor=care, act="execution-started", conversation=conversation,
                        execution="inst-quiet-seam", runtime="fake", because="shape check")
    st.agents.agents_open_run("inst-quiet-seam", run)

    rows = {r["participant"]: r for r in get(world, "/api/activity")["activity"]}
    runs = rows[care]["runs"]
    assert runs, "the fixture run did not reach /api/activity"
    keys = sorted(runs[0])

    if CAPTURE:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "quiet_activity_run.json").write_text(
            json.dumps({"keys": keys}, indent=1) + "\n", encoding="utf-8")
        pytest.skip("recorded the run shape; nothing was asserted against it")

    assert keys == json.loads(RECORDED_RUN.read_text(encoding="utf-8"))["keys"]
