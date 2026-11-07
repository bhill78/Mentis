"""ROUND 4, TRACK C: the in-app viewer, the renderer's artifacts in a Quiet
post, their presentation in the margin, and annotations.

Five things, each of which was not true before this change:

  1. a file row and an html mockup OPEN IN THE PAGE. They were links to
     `/api/artifacts/<ref>`, so reading a note or looking at a mockup meant
     leaving the conversation. The download link is inside the viewer now.
  2. a checklist and a table an agent wrote RENDER as blocks. `parts.tsx`
     passed `untrusted` to the shared reader, which switches every renderable
     block off, so they arrived as fenced source.
  3. what a post carries is PRESENTED IN THE MARGIN, as small windows beside
     the stream -- and it is the SAME block: ticking the margin's copy of a
     checklist ticks the post's.
  4. no horizontal scrollbar at 1440, 900 or 390, with boxes in the margin.
  5. an annotation shows as an ICON IN THE POST'S GUTTER, level with the
     passage it is on, and opens as a margin box.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
Set QUIET_R4_EVIDENCE to a folder to keep the screenshots.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mentis import artifacts
from mentis.conversation import text
from mentis.conversation.anchors import create_anchor, react
from tests._loop import world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

WIDE = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}

MOCKUP = (b"<!doctype html><html><head><title>Margin mockup</title></head>"
          b"<body><h1>A margin mockup</h1><p>drawn in the page</p></body></html>")

BLOCKS = (
    "## What the run came to\n"
    "\n"
    "```checklist version=1\n"
    "- [ ] Read the record\n"
    "- [ ] Say what changed\n"
    "```\n"
    "\n"
    "```table version=1\n"
    "item,value\n"
    "Alpha,1\n"
    "Beta,2\n"
    "```\n"
    "\n"
    "The line after the blocks.\n"
)

PASSAGE = "The sentence repeats."
#: Long enough that the anchored passage is NOT on the post's first line, so
#: "level with its passage" is a real measurement and not true by default.
WORDS = ("Plan first, and keep the plan where the work can see it, because a plan "
         "nobody reads is not a plan at all, however carefully it was written. "
         f"{PASSAGE} Then the next step, and a little more after it.")


def hold(world, data, name, media_type, conversation):
    held = artifacts.hold(
        world["state"].corpus, world["cv"], data, act="artifact-submitted",
        actor=world["who"]["@brian"], source=f"submission:{world['who']['@brian']}",
        door="human-ingress", conversation=conversation,
        claimed_name=name, claimed_media_type=media_type)
    return held["admission"]


def shot(page, name, full=False):
    folder = os.environ.get("QUIET_R4_EVIDENCE")
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / name), full_page=full)


def built():
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()


@pytest.fixture
def carried(world):
    """One conversation holding, in order: a post with two marked blocks, a
    post with an html mockup and a notes file, and an annotated post."""
    cv, owner = world["cv"], world["who"]["@brian"]
    corpus = world["state"].corpus
    cid = cv.open_conversation("Quiet carried", about="What the posts carry.")
    cv.join(owner, cid)
    blocks = cv.say(cid, owner, [text(BLOCKS)])
    mockup = hold(world, MOCKUP, "mockup.html", "text/html", cid)
    notes = hold(world, b"a short note, read in the page", "notes.txt", "text/plain", cid)
    files = cv.say(cid, owner, [artifacts.part(mockup, corpus=corpus),
                                artifacts.part(notes, corpus=corpus)])
    said = cv.say(cid, owner, [text(WORDS)])
    start = WORDS.index(PASSAGE)
    anchor = create_anchor(cv, {
        "version": said, "type": "text-range", "part": 0, "start": start,
        "end": start + len(PASSAGE), "unit": "codepoint",
        "expected_excerpt": PASSAGE}, by=owner)["anchor"]
    react(cv, anchor, {"token": "👍"}, by=owner)
    return {"conversation": cid, "blocks": blocks, "files": files,
            "said": said, "mockup": mockup, "notes": notes, "anchor": anchor}


def open_conversation(page, world, carried):
    page.goto(world["base"] + f"/quiet#/c/{carried['conversation']}")
    page.get_by_role("heading", name="Quiet carried", exact=True).wait_for()
    page.locator(f"#qc-post-{carried['blocks']}").wait_for()


def show_carried(page):
    page.get_by_role("button", name="Carried", exact=True).click()
    page.locator(".qc-carried").wait_for()


# -- 1. the viewer ------------------------------------------------------------

@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("width", [1440, 390])
def test_a_file_and_an_html_mockup_open_in_the_page(world, carried, engine, width):
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE if width == 1440 else PHONE)
            errors, navigations = [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # The page itself, not the preview's own frame: a guarded srcdoc
            # frame navigates once when it is drawn, which is the point of it.
            page.on("framenavigated",
                    lambda f: navigations.append(f.url) if f.parent_frame is None else None)
            open_conversation(page, world, carried)
            post = page.locator(f"#qc-post-{carried['files']}")
            post.wait_for()
            was = page.url
            moves = len(navigations)

            # THE HTML MOCKUP: drawn in the one guarded frame, in the page.
            post.get_by_role("button", name="Open mockup.html", exact=True).click()
            dialog = page.get_by_role("dialog")
            dialog.wait_for()
            frame = dialog.locator("iframe.qc-viewer-frame")
            frame.wait_for()
            # The frame's permissions are the ones prose.tsx decides once, and
            # the document in it is the author's with the policy in front of
            # it. Read off the element: the frame has an opaque origin
            # (`sandbox=""`), so the page it is in cannot look inside it, which
            # is the point.
            assert frame.get_attribute("sandbox") == ""
            assert frame.get_attribute("referrerpolicy") == "no-referrer"
            srcdoc = frame.get_attribute("srcdoc")
            assert "A margin mockup" in srcdoc
            assert "Content-Security-Policy" in srcdoc and "default-src 'none'" in srcdoc
            assert '<base target="_blank">' in srcdoc
            download = dialog.get_by_role("link", name="Download mockup.html", exact=True)
            assert download.get_attribute("href") == f"/api/artifacts/{carried['mockup']}"
            shot(page, f"{engine}-{width}-viewer-html.png")

            # Previous / next step through everything the post carries, not
            # only its pictures, and Escape returns focus to the row.
            dialog.get_by_text("1 of 2", exact=True).wait_for()
            page.keyboard.press("ArrowRight")
            dialog.get_by_text("2 of 2", exact=True).wait_for()
            dialog.get_by_role("link", name="Download notes.txt", exact=True).wait_for()
            dialog.get_by_text("a short note, read in the page", exact=False).wait_for()
            shot(page, f"{engine}-{width}-viewer-file.png")
            page.keyboard.press("Escape")
            dialog.wait_for(state="detached")
            assert page.evaluate(
                "document.activeElement.getAttribute('data-qc-name')") == "mockup.html"

            # NOTHING NAVIGATED. The whole reading happened in the page.
            assert page.url == was
            assert len(navigations) == moves, navigations
            assert errors == []
        finally:
            browser.close()


# -- 2 and 3. the blocks, and the margin -------------------------------------

@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_marked_blocks_render_and_are_presented_in_the_margin(world, carried, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            open_conversation(page, world, carried)
            post = page.locator(f"#qc-post-{carried['blocks']}")

            # THE BLOCKS RENDER. A checklist is its items with their boxes; a
            # table is a grid. Neither is its fenced source any more.
            post.locator(".rb-card").first.wait_for()
            assert post.locator(".rb-card").count() >= 2
            post.locator(".rb-check input").first.wait_for()
            assert post.locator(".rb-check input").count() == 2
            post.locator(".rb-table-grid").first.wait_for()
            assert "Alpha" in post.locator(".rb-table-grid").inner_text()
            # The words around them still read, in place.
            assert "What the run came to" in post.inner_text()
            assert "The line after the blocks." in post.inner_text()
            # And nothing widened the column.
            assert page.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")

            # THE MARGIN PRESENTS THEM, each a small window that says which
            # post it came from and can be put away.
            show_carried(page)
            boxes = page.locator(".qc-margin .qc-box")
            boxes.first.wait_for()
            titles = [t.strip().lower() for t in page.locator(".qc-box-title").all_inner_texts()]
            assert "checklist" in titles and "table" in titles, titles
            assert page.locator(".qc-box[data-kind='media']").count() >= 1, (
                "the post's attachments are carried beside it too")
            shot(page, f"{engine}-1440-margin.png")

            # IT IS THE SAME BLOCK, not a copy: one key, one state.
            box = page.locator(".qc-box[data-kind='block']", has=page.locator(".rb-check")).first
            box.wait_for()
            box.locator(".rb-check input").first.check()
            assert post.locator(".rb-check input").first.is_checked(), (
                "the margin's checklist and the post's are one block")

            # PUT AWAY takes that box out of the margin and leaves the post alone.
            before = boxes.count()
            box.locator(".qc-box-away").click()
            page.wait_for_function(
                "(n) => document.querySelectorAll('.qc-margin .qc-box').length === n - 1",
                arg=before)
            assert post.locator(".rb-check input").count() == 2
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("width", [1440, 900, 390])
def test_the_margins_boxes_never_give_the_page_a_sideways_scroll(world, carried, engine, width):
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 844 if width == 390 else 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            open_conversation(page, world, carried)
            show_carried(page)
            page.locator(".qc-margin .qc-box").first.wait_for()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"), (
                f"the page scrolls sideways at {width}px")
            # No box reaches past the margin it is in, at any width. Every
            # rectangle is read in ONE pass in the browser: asking for them one
            # at a time lets a box be re-drawn between two asks.
            edges = page.evaluate("""() => {
              const margin = document.querySelector('.qc-margin').getBoundingClientRect()
              return {
                margin: [margin.left, margin.right],
                boxes: [...document.querySelectorAll('.qc-margin .qc-box')]
                  .map((el) => { const r = el.getBoundingClientRect(); return [r.left, r.right] }),
              }
            }""")
            assert edges["boxes"], "nothing is carried, so nothing was measured"
            for left, right in edges["boxes"]:
                assert left >= edges["margin"][0] - 1
                assert right <= edges["margin"][1] + 1, (
                    f"a box reaches past the margin at {width}px")
            if width == 390:
                # Below 900px the margin falls into the column, above the stream.
                margin = page.locator(".qc-margin").bounding_box()
                stream = page.locator("#qc-stream").bounding_box()
                assert margin["y"] < stream["y"]
                assert abs(margin["width"] - stream["width"]) <= 1
                shot(page, f"{engine}-390-margin.png", full=True)
            assert errors == []
        finally:
            browser.close()


# -- 5. annotations -----------------------------------------------------------

@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("width", [1440, 390])
def test_an_annotation_shows_in_the_gutter_and_opens_in_the_margin(world, carried, engine, width):
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE if width == 1440 else PHONE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            open_conversation(page, world, carried)
            post = page.locator(f"#qc-post-{carried['said']}")
            post.wait_for()

            # THE ICON IS IN THE POST'S GUTTER, and says what it is on.
            mark = post.locator(".qc-anno-mark")
            mark.first.wait_for()
            assert mark.count() == 1
            label = mark.first.get_attribute("aria-label")
            assert PASSAGE in label and "👍" in label, label

            # LEVEL WITH THE PASSAGE, not with the top of the post: its middle
            # is inside the line the anchored words are drawn on.
            body = post.locator(".qc-body")
            box = mark.first.bounding_box()
            words = body.bounding_box()
            assert box["x"] >= words["x"], "the mark is not in the words"
            middle = box["y"] + box["height"] / 2
            assert words["y"] <= middle <= words["y"] + words["height"] + 1
            assert middle > words["y"] + 20, (
                "the mark sits at the top of the body, not level with its passage "
                "(the passage is deliberately not on the first line)")
            shot(page, f"{engine}-{width}-annotation.png")

            # ACTIVATING IT OPENS THE ANNOTATION AS A MARGIN BOX.
            mark.first.click()
            annotation = page.locator(".qc-margin .qc-box[data-kind='annotation']")
            annotation.wait_for()
            assert page.get_by_role("heading", name="Carried", exact=True).count() == 1, (
                "collecting an annotation switches the margin to what is carried")
            assert PASSAGE in annotation.inner_text()
            assert "👍" in annotation.inner_text()
            assert mark.first.get_attribute("aria-expanded") == "true"
            shot(page, f"{engine}-{width}-annotation-box.png")
            assert page.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
            assert errors == []
        finally:
            browser.close()
