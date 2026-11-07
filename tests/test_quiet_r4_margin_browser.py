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


# -- 6. THE CORRECTION: what the independent review of 48bd62d found ---------
#
# Four of its five findings are here; the fifth -- Escape once the reader has
# clicked inside the viewer's sandboxed frame -- is in
# test_quiet_media_browser.py with the rest of the viewer. Every one was
# reproduced in both engines before it was fixed, so every case runs in both.

#: Two text parts, with the annotated passage in the SECOND one. An anchor's
#: passage is an offset into ONE part, and a layer given only the first part's
#: text has nowhere to place this one.
LATER_BEFORE = "The first text part fills several lines of context. " * 10
LATER_PASSAGE = "UNIQUE ANNOTATED LATER PASSAGE."


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("width", [1440, 390])
def test_an_anchored_comments_words_are_readable_in_its_margin_box(world, engine, width):
    """F1. The box said that one thing was attached and never what it said.
    A count is a promise of content, not content: the comment is words
    somebody wrote, and the margin is where the annotation is read."""
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation("Quiet annotation comment", about="A comment, read in the margin.")
    cv.join(owner, cid)
    words = "An annotated statement needs the qualification below."
    said = cv.say(cid, owner, [text(words)])
    anchor = create_anchor(cv, {
        "version": said, "type": "text-range", "part": 0, "start": 0,
        "end": len(words), "unit": "codepoint", "expected_excerpt": words}, by=owner)["anchor"]
    comment = "THE QUALIFICATION: this claim only holds for fixture data."
    cv.say(cid, owner, [{"type": "anchor", "ref": anchor}, text(comment)], replies_to=said)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE if width == 1440 else PHONE)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(world["base"] + f"/quiet#/c/{cid}")
            page.get_by_role("heading", name="Quiet annotation comment", exact=True).wait_for()
            post = page.locator(f"#qc-post-{said}")
            post.wait_for()
            post.locator(".qc-anno-mark").first.wait_for()
            post.locator(".qc-anno-mark").first.click()

            box = page.locator(".qc-margin .qc-box[data-kind='annotation']")
            box.wait_for()
            # THE WORDS ARE THERE WITH THE BOX, not after a read: the comment
            # is a post a few rows down the same stream, and the margin takes
            # its words from what that post draws. Asserted with no wait, as
            # the review's own case asserts it.
            assert comment in box.inner_text(), (
                "the margin shows a tally but not the comment's own words")
            # What it is on is still said, above the words.
            assert words in box.inner_text()
            # Who wrote it comes from the record's own read of that post.
            box.get_by_text("@brian", exact=True).wait_for()
            assert box.locator(".qc-box-comment").count() == 1
            shot(page, f"{engine}-{width}-annotation-comment.png", full=True)

            assert page.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"), (
                f"the comment's words gave the page a sideways scroll at {width}px")
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_an_annotation_on_a_later_text_part_is_level_with_its_passage(world, engine):
    """F2. Only the first text part reached the alignment, so an anchor on any
    later one had no span to be found in and its icon sat at the top of the
    body -- about 186px above the passage it is on."""
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation("Quiet later part", about="An anchor in the second text part.")
    cv.join(owner, cid)
    said = cv.say(cid, owner, [text(LATER_BEFORE), text(LATER_PASSAGE)])
    anchor = create_anchor(cv, {
        "version": said, "type": "text-range", "part": 1, "start": 0,
        "end": len(LATER_PASSAGE), "unit": "codepoint",
        "expected_excerpt": LATER_PASSAGE}, by=owner)["anchor"]
    react(cv, anchor, {"token": "\N{THUMBS UP SIGN}"}, by=owner)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(world["base"] + f"/quiet#/c/{cid}")
            page.get_by_role("heading", name="Quiet later part", exact=True).wait_for()
            post = page.locator(f"#qc-post-{said}")
            post.wait_for()
            post.locator(".qc-anno-mark").first.wait_for()
            # The passage is in the part that arrives second, and the layer
            # measures again when it does: let the mark settle.
            page.wait_for_timeout(200)

            # Every rectangle in ONE pass, so a redraw between two asks
            # cannot decide the case.
            places = page.evaluate(
                """([id, passage]) => {
                  const post = document.getElementById(id)
                  const m = post.querySelector('.qc-anno-mark').getBoundingClientRect()
                  const words = [...post.querySelectorAll('.qc-body p')]
                    .find((el) => el.textContent.trim() === passage)
                  const p = words.getBoundingClientRect()
                  const body = post.querySelector('.qc-body').getBoundingClientRect()
                  return {mark: [m.y, m.height], passage: [p.y, p.height], body: body.y}
                }""",
                [f"qc-post-{said}", LATER_PASSAGE])
            middle = places["mark"][0] + places["mark"][1] / 2
            top, height = places["passage"]
            assert top - 1 <= middle <= top + height + 1, (
                f"the mark's middle is at {middle}; its passage is drawn at "
                f"{top}..{top + height}")
            assert middle > places["body"] + 20, (
                "the mark sits at the top of the body rather than level with its passage")
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_put_away_annotation_comes_back_from_its_own_icon(world, carried, engine):
    """F3. `present` marked the box without taking it out of `away`, so the
    icon read as expanded while the margin stayed empty -- and there was no
    way back to that annotation for the rest of the tab's life."""
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            open_conversation(page, world, carried)
            mark = page.locator(f"#qc-post-{carried['said']} .qc-anno-mark").first
            mark.wait_for()
            mark.click()
            box = page.locator(".qc-margin .qc-box[data-kind='annotation']")
            box.wait_for()

            # PUT IT AWAY, and it goes.
            box.get_by_role("button", name="Put away Annotation", exact=True).click()
            page.wait_for_function(
                "() => document.querySelectorAll('.qc-margin .qc-box[data-kind=\\'annotation\\']').length === 0")

            # ASK FOR IT BY ITS OWN ICON -- closed, then opened again -- and it
            # is back: asking for a box is asking for it back.
            mark.click()
            mark.click()
            box.wait_for()
            assert mark.get_attribute("aria-expanded") == "true"
            assert PASSAGE in box.inner_text()
            assert errors == []
        finally:
            browser.close()


#: THE REVIEW'S OWN SAMPLE (ent-65eecd7b255d, F3): an ordinary six-column
#: table, one row. It measured scrollWidth 496 against clientWidth 276 at
#: 1440, 496/218 at 901 and 496/258 at 390 -- the later columns were out of
#: view until the reader scrolled the box sideways, in both engines.
SIX_COLUMNS = (
    "```table version=1\n"
    "name,owner,state,start,end,notes\n"
    "Rollout,Vera,running,2026-11-01,2026-11-09,waiting on the second check\n"
    "```\n"
)

#: A table that GENUINELY CANNOT FIT: twelve columns whose cells are single
#: unbreakable tokens. There is no wrapping that makes this narrow, so it is
#: the exception the owner's sentence allows -- it still scrolls inside its
#: own box, and the whole of it is one press away through "Go to post".
UNFITTABLE = (
    "```table version=1\n"
    + ",".join(f"ccccccccccccccccc{i}" for i in range(12)) + "\n"
    + ",".join(f"vvvvvvvvvvvvvvvvv{i}" for i in range(12)) + "\n"
    "```\n"
)


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_carried_table_fits_its_box_and_only_an_unfittable_one_scrolls(world, engine):
    """THE CORRECTION TO F3 of the visual review (ent-65eecd7b255d).

    The owner's sentence is "margin content must adapt to the space available
    without unintended horizontal scrolling". margin.css chose the opposite on
    purpose -- the renderer's grid is `width: max-content` with `nowrap`
    cells, and the box let it scroll -- which was a reasonable fallback but
    makes the owner's rule the exception. Now the cells wrap and the grid
    takes the box's width, so the six-column sample has NO scroll range at
    all; only a table that cannot wrap keeps the fallback.
    """
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation("Quiet margin tables", about="A table carried beside its post.")
    cv.join(owner, cid)
    fits = cv.say(cid, owner, [text(SIX_COLUMNS)])
    cv.say(cid, owner, [text(UNFITTABLE)])

    # The four widths the owner's sentence is asked at. 1440 and 390 are the
    # two the correction names; 1100 and 901 are where the margin is at its
    # narrowest beside the stream, which is where the review measured 496/218.
    sizes = [WIDE, {"width": 1100, "height": 900}, {"width": 901, "height": 900}, PHONE]
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            for size in sizes:
                page = browser.new_page(viewport=size)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(world["base"] + f"/quiet#/c/{cid}")
                page.get_by_role("heading", name="Quiet margin tables", exact=True).wait_for()
                page.locator(f"#qc-post-{fits}").wait_for()
                show_carried(page)
                boxes = page.locator(".qc-margin .qc-box[data-kind='block']")
                boxes.first.wait_for()
                page.locator(".qc-margin .rb-table-scroll").first.wait_for()
                where = f"{engine} at {size['width']}px"

                # EVERY RECTANGLE IN ONE PASS, so a redraw between two asks
                # cannot decide the case. The two tables are told apart by
                # their own column count, not by their order in the margin.
                seen = page.evaluate("""() => {
                  const margin = document.querySelector('.qc-margin').getBoundingClientRect()
                  const read = (box) => {
                    const wrap = box.querySelector('.rb-table-scroll')
                    if (!wrap) return null
                    const r = wrap.getBoundingClientRect()
                    const b = box.getBoundingClientRect()
                    return {
                      columns: wrap.querySelectorAll('thead th').length,
                      scrollWidth: wrap.scrollWidth,
                      clientWidth: wrap.clientWidth,
                      box: [b.left, b.right],
                      heads: [...wrap.querySelectorAll('thead th')].map((th) => {
                        const h = th.getBoundingClientRect()
                        return [th.innerText.trim(), h.left, h.right]
                      }),
                    }
                  }
                  return {
                    margin: [margin.left, margin.right],
                    marginScroll: [
                      document.querySelector('.qc-margin').scrollWidth,
                      document.querySelector('.qc-margin').clientWidth],
                    page: [document.documentElement.scrollWidth,
                           document.documentElement.clientWidth],
                    tables: [...document.querySelectorAll(
                      ".qc-margin .qc-box[data-kind='block']")].map(read).filter(Boolean),
                  }
                }""")
                assert len(seen["tables"]) == 2, (f"both tables are carried, {where}: {seen}")
                fitting = [t for t in seen["tables"] if t["columns"] <= 7]
                wide = [t for t in seen["tables"] if t["columns"] > 7]
                assert len(fitting) == 1 and len(wide) == 1, seen["tables"]
                fitting, wide = fitting[0], wide[0]

                # THE SIX-COLUMN SAMPLE HAS NO HORIZONTAL SCROLL RANGE.
                assert fitting["scrollWidth"] <= fitting["clientWidth"] + 1, (
                    f"the six-column table still scrolls inside its box, {where}: "
                    f"scrollWidth {fitting['scrollWidth']} against clientWidth "
                    f"{fitting['clientWidth']}")
                # And every header cell is already inside the box's x-range,
                # so no column waits behind a sideways scroll.
                assert len(fitting["heads"]) >= 6, fitting["heads"]
                for name, left, right in fitting["heads"]:
                    assert left >= fitting["box"][0] - 1 and right <= fitting["box"][1] + 1, (
                        f"column {name!r} is outside the box at {where}: "
                        f"{left}..{right} against {fitting['box']}")
                # Legible: the words themselves are still drawn, wrapped.
                assert {n for n, _, _ in fitting["heads"]} >= {"name", "owner", "notes"}, (
                    fitting["heads"])

                # THE EXCEPTION: a table that cannot wrap keeps the fallback.
                # It scrolls INSIDE its own box and widens neither the margin
                # nor the page.
                assert wide["scrollWidth"] > wide["clientWidth"] + 1, (
                    f"the unfittable table has no scroll range, so its columns are "
                    f"cut off rather than reachable, {where}: {wide}")
                assert wide["box"][0] >= seen["margin"][0] - 1
                assert wide["box"][1] <= seen["margin"][1] + 1, (
                    f"the unfittable table widened its box past the margin, {where}")
                assert seen["marginScroll"][0] <= seen["marginScroll"][1] + 1, (
                    f"the unfittable table gave the margin a sideways scroll, {where}")
                assert seen["page"][0] <= seen["page"][1] + 1, (
                    f"the carried tables gave the page a sideways scroll, {where}")

                shot(page, f"{engine}-{size['width']}-margin-table.png")
                assert errors == []
                page.close()
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("width", [1440, 390])
def test_the_carried_reading_shows_its_boxes_beside_an_outstanding_decision(
        world, carried, engine, width):
    """F5, the seam. The request asks for the renderer's artifacts in the
    margin alongside media and the decision accordions; Carried and Activity
    were mutually exclusive readings, so a reader could have the boxes or the
    decision and never both."""
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    cv, owner, care = world["cv"], world["who"]["@brian"], world["steward"]
    question = "Which margin should the carried blocks sit in?"
    asked = cv.say(carried["conversation"], care, [text(question)])
    cv.expect(asked, of=owner, kind="decision", by=care, because="which margin",
              detail={"options": [{"label": "Keep it"}, {"label": "Change it"}]})

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE if width == 1440 else PHONE)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            open_conversation(page, world, carried)
            decisions = page.locator(".qc-margin .qc-decisions")

            # It is outstanding, and Activity shows it as it always has.
            page.get_by_role("button", name="Activity", exact=True).click()
            decisions.wait_for()
            assert decisions.count() == 1

            # AND SO DOES CARRIED, together with the boxes: one margin holding
            # both, the decision under them as Activity also puts it.
            show_carried(page)
            blocks = page.locator(".qc-margin .qc-box[data-kind='block']")
            blocks.first.wait_for()
            decisions.wait_for()
            assert blocks.count() >= 2
            assert decisions.count() == 1
            # The row says what it is: its own recorded reason, as Activity
            # draws it ("which margin" -- `because`, where the read of the
            # asking post has not named the question itself).
            assert "which margin" in decisions.inner_text()
            # Still the same control, answerable here: its options are its own.
            assert decisions.get_by_role("button", name="Keep it", exact=True).count() == 1
            assert decisions.bounding_box()["y"] >= blocks.last.bounding_box()["y"], (
                "the decision is under the boxes, not drawn over them"
            )
            shot(page, f"{engine}-{width}-carried-decisions.png", full=True)

            assert page.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"), (
                f"the boxes and the decision together gave the page a sideways scroll at {width}px")
            assert errors == []
        finally:
            browser.close()
