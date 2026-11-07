"""TRACK B: reply indicators, the parent-post header, toned-down activity
bars, and avatars -- against real Mentis HTTP routes on a disposable fixture
Brain.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mentis import artifacts
from mentis.conversation import text
from tests._loop import world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

WIDE = {"width": 1440, "height": 900}

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
       b"\x00\x00\x05\x00\x01\r\n\x00\x00\x00\x00IEND\xaeB`\x82")

LONG_PARAGRAPH = (
    "A long root post with room enough to overflow three clamped lines in "
    "the parent header, so Show more has something real to disclose. " * 6
)


def _hold(world, data, name, media_type, conversation):
    held = artifacts.hold(
        world["state"].corpus, world["cv"], data, act="artifact-submitted",
        actor=world["who"]["@brian"], source=f"submission:{world['who']['@brian']}",
        door="human-ingress", conversation=conversation,
        claimed_name=name, claimed_media_type=media_type)
    return held["admission"]


def _a_thread(world):
    """A root (pictured author) with a long chain of replies (an author with
    neither a picture nor a declared runtime, for a plain initial), so there
    is a thread long enough to scroll, a reply whose answered-to author is
    known, and both an avatar img and initials to find."""
    cv = world["cv"]
    brian = world["who"]["@brian"]
    nadia = cv.create_participant("@Quietly", about="no picture, no declared runtime")
    conv = cv.open_conversation("Quiet replies", about="Where reply indicators are checked.")
    cv.join(brian, conv)
    cv.join(nadia, conv)
    admission = _hold(world, PNG, "brian.png", "image/png", conv)
    cv.set_avatar(brian, admission, by=brian)

    root = cv.say(conv, brian, [text(LONG_PARAGRAPH)])
    first_reply = cv.say(conv, nadia, [text("The first reply, answering the root directly.")],
                          replies_to=root)
    chain = [first_reply]
    for n in range(24):
        chain.append(cv.say(conv, brian if n % 2 else nadia,
                             [text(f"Reply {n} in a long chain, to make the thread scroll.")],
                             replies_to=chain[-1]))
    return conv, brian, nadia, root, first_reply, chain


def _a_conversation_with_topics(world):
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation("Quiet activity caps", about="Where the bar maxima are checked.")
    cv.join(owner, cid)
    quiet = cv.open_topic(cid, "Quiet topic", about="One post filed here.")
    busy = cv.open_topic(cid, "Busy topic", about="Many posts filed here.")
    cv.assign_topic(cv.say(cid, owner, [text("The one quiet post.")]), quiet)
    for n in range(12):
        cv.assign_topic(cv.say(cid, owner, [text(f"A busy post, number {n}.")]), busy)
    return cid, quiet, busy


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_reply_line_is_unmistakable_and_accented(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    conv, brian, nadia, root, first_reply, chain = _a_thread(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            page.goto(world["base"] + f"/quiet#/c/{conv}/turn/{first_reply}")
            page.get_by_role("heading", name="Thread", exact=False).wait_for()
            post = page.locator(f"#qc-post-{first_reply}")
            post.wait_for()

            line = post.locator(".qc-reply-line")
            line.wait_for()
            line_text = line.inner_text()
            assert "↳" in line_text, "the reply line carries the reply glyph"
            assert "replying to" in line_text, "the reply line names what it answers"
            assert "@brian" in line_text and "#" in line_text, (
                "the Thread view has every row loaded, so the reply line names "
                "who it answers as well as which post")

            reply_color = post.locator(".qc-reply-line a").evaluate(
                "(el) => getComputedStyle(el).color")
            body_color = post.locator(".qc-body").evaluate(
                "(el) => getComputedStyle(el).color")
            assert reply_color != body_color, (
                "the reply line's accent must differ from the body's own ink")

            # Back in the conversation's own flow, the root (with replies)
            # carries its own clearly clickable "N replies" control.
            page.goto(world["base"] + f"/quiet#/c/{conv}")
            page.get_by_role("heading", name="Quiet replies", exact=True).wait_for()
            root_post = page.locator(f"#qc-post-{root}")
            root_post.wait_for()
            control = root_post.locator(".qc-post-reply")
            control_text = control.inner_text()
            assert "↳" in control_text and "replies" in control_text
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_parent_header_stays_pinned_and_discloses_its_content(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conv, brian, nadia, root, first_reply, chain = _a_thread(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            page.goto(world["base"] + f"/quiet#/c/{conv}/turn/{root}")
            page.get_by_role("heading", name="Thread", exact=False).wait_for()
            header = page.locator(".qc-parent-header")
            header.wait_for()

            # The root is STILL drawn in full as the stream's first row --
            # ParentHeader is additive, a pinned condensed summary of it.
            assert page.locator(f"#qc-post-{root}").count() == 1

            toggle = header.locator(".qc-parent-toggle")
            toggle.wait_for()
            assert toggle.get_attribute("aria-expanded") == "false"
            collapsed_box = header.locator(".qc-parent-body").bounding_box()
            toggle.click()
            assert toggle.get_attribute("aria-expanded") == "true"
            expanded_box = header.locator(".qc-parent-body").bounding_box()
            assert expanded_box["height"] > collapsed_box["height"], (
                "Show more must disclose the rest of the parent's content")
            toggle.click()
            assert toggle.get_attribute("aria-expanded") == "false"

            # Pinned: scrolling a long thread keeps the header in view, near
            # the top of the viewport, rather than scrolling away with the
            # replies under it.
            before = header.bounding_box()["y"]
            page.locator(f"#qc-post-{chain[-1]}").scroll_into_view_if_needed()
            after = header.bounding_box()["y"]
            assert after <= before + 1, "the parent header must not scroll past its pinned position"
            assert after <= 40, f"the parent header should sit near the top once pinned, not at y={after}"
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_parent_header_hides_what_scrolls_under_it(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conv, brian, nadia, root, first_reply, chain = _a_thread(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            page.goto(world["base"] + f"/quiet#/c/{conv}/turn/{root}")
            page.get_by_role("heading", name="Thread", exact=False).wait_for()
            header = page.locator(".qc-parent-header")
            header.wait_for()

            # Scroll enough for the header to reach its pinned position (near
            # the top, same as test_parent_header_stays_pinned... checks)
            # before sampling anything -- only once it is actually stuck is
            # there a meaningful "underneath it" to compare.
            page.locator(f"#qc-post-{chain[5]}").scroll_into_view_if_needed()
            pinned_box = header.bounding_box()
            assert pinned_box["y"] <= 40, f"the header should be pinned near the top, not y={pinned_box['y']}"

            # A point in the header's own top-left padding, clear of the
            # avatar and the text that follows it (elementFromPoint there
            # already returns the header -- it is sticky and on top -- which
            # is why that alone cannot show whether its backdrop is opaque).
            sample_x = pinned_box["x"] + 6
            sample_y = pinned_box["y"] + 3

            def pixel_at(x, y):
                return page.screenshot(clip={"x": x, "y": y, "width": 1, "height": 1})

            before = pixel_at(sample_x, sample_y)

            # Scroll further: more replies pass under the still-pinned header.
            page.locator(f"#qc-post-{chain[-1]}").scroll_into_view_if_needed()
            after_box = header.bounding_box()
            assert abs(after_box["y"] - pinned_box["y"]) < 2, "the header must still be pinned at the same spot"
            after = pixel_at(sample_x, sample_y)

            assert before == after, (
                "the header's own background must be opaque: a point in its band "
                "must read the same before and after more posts scroll underneath it"
            )
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_avatars_show_a_picture_or_initials(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conv, brian, nadia, root, first_reply, chain = _a_thread(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            page.goto(world["base"] + f"/quiet#/c/{conv}/turn/{first_reply}")
            page.get_by_role("heading", name="Thread", exact=False).wait_for()

            pictured = page.locator(f"#qc-post-{root} header .avatar")
            pictured.wait_for()
            assert pictured.locator("img").count() == 1, "@brian is pictured: an avatar img"
            assert "/api/artifacts/" in pictured.locator("img").get_attribute("src")

            unpictured = page.locator(f"#qc-post-{first_reply} header .avatar")
            unpictured.wait_for()
            assert unpictured.locator("img").count() == 0, "@Nadia has no picture: no img"
            assert unpictured.get_attribute("data-initial") == "Q"
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_topic_and_conversation_activity_bars_have_a_sane_maximum(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conv, quiet, busy = _a_conversation_with_topics(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            page.goto(world["base"] + f"/quiet#/c/{conv}")
            page.get_by_role("heading", name="Quiet activity caps", exact=True).wait_for()
            page.locator(".qc-topic-bar").first.wait_for()

            topic_boxes = page.locator(".qc-topic-bar").evaluate_all(
                "els => els.map(e => e.getBoundingClientRect())")
            for box in topic_boxes:
                assert box["height"] > box["width"] > 0
                assert box["width"] <= 8, f"a topic mark's thickness must stay capped, got {box['width']}"
                assert box["height"] <= 46, f"a topic mark's length must stay capped, got {box['height']}"

            nav_boxes = page.locator(".qc-nav-mark-bar").evaluate_all(
                "els => els.map(e => e.getBoundingClientRect())")
            for box in nav_boxes:
                assert box["height"] <= 18, f"a conversation mark's bar must be toned down, got {box['height']}"
                assert box["width"] <= 8, f"a conversation mark's weight must stay capped, got {box['width']}"
        finally:
            browser.close()
