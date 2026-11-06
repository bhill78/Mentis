"""Quiet Chat against real Mentis HTTP routes on a disposable fixture Brain.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from mentis.conversation import text, versions
from tests._loop import get, world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_quiet_chat_real_api(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cv, owner = world["cv"], world["who"]["@brian"]
    first = cv.open_conversation("Quiet browser: research", about="Room for a longer thought.")
    second = cv.open_conversation("Quiet browser: notebook", about="Another conversation.")
    cv.join(owner, first)
    cv.join(owner, second)
    topic = cv.open_topic(first, "Reading", about="The posts filed for close reading.")
    older = cv.say(first, owner, [text("An older post to find through history.")])
    for n in range(32):
        cv.say(first, owner, [text(f"History post {n}.")])
    long_post = cv.say(first, owner, [text(
        "## A long thought\n\n" + "A paragraph with room to breathe.\n\n" * 32
        + "The final line of the long post."
    )])
    cv.assign_topic(long_post, topic)
    replies = []
    for n in range(65):
        replies.append(cv.say(first, owner, [text(f"Thread reply {n}.")],
                              replies_to=replies[-1] if replies else long_post))
    cv.assign_topic(replies[40], topic)
    cv.say(second, owner, [text("Notes in the other conversation.")])

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(world["base"] + f"/quiet#/c/{first}")
            page.get_by_role("heading", name="Quiet browser: research", exact=True).wait_for()
            page.get_by_text("The final line of the long post.", exact=True).wait_for()
            assert page.locator(f"#qc-post-{long_post}").inner_text().count("A paragraph with room to breathe.") == 32

            # The static fallback mounts Quiet separately and leaves Fluid the default.
            assert page.locator(".qc").count() == 1
            assert page.locator(".fw-shell.fx").count() == 0
            original_url = page.url
            page.get_by_role("link", name="Skip to conversation", exact=True).focus()
            page.keyboard.press("Enter")
            assert page.url == original_url
            page.get_by_role("button", name="Older posts", exact=False).click()
            page.locator(f"#qc-post-{older}").wait_for()
            page.get_by_role("button", name="Latest posts", exact=True).click()
            page.locator(f"#qc-post-{long_post}").wait_for()

            page.get_by_role("link", name="# Reading", exact=True).first.click()
            page.locator(f"#qc-post-{replies[40]}").wait_for()
            assert page.locator(f"#qc-post-{replies[40]}").inner_text().find("Replying to") >= 0
            page.evaluate("scrollTo(0, 0)")
            page.screenshot(path=Path(world["root"]).parent / "quiet-desktop.png")
            page.get_by_role("link", name="All posts", exact=False).click()

            page.get_by_role("link", name="Open thread · 65 replies", exact=True).click()
            page.get_by_role("heading", name="Thread #34", exact=False).wait_for()
            assert page.locator(".qc-post").count() == 66
            page.get_by_label("Go to post in thread").select_option(replies[60])
            page.locator(f"#qc-post-{replies[60]}[data-selected]").wait_for()
            page.reload()
            page.locator(f"#qc-post-{replies[60]}[data-selected]").wait_for()
            page.get_by_role("link", name="Previous post", exact=False).click()
            page.locator(f"#qc-post-{replies[59]}[data-selected]").wait_for()
            page.go_back()
            page.locator(f"#qc-post-{replies[60]}[data-selected]").wait_for()

            # A reply addresses the explicitly selected nested reply, through the
            # real posting door. Direct pointer press while the textarea has focus.
            page.locator(f"#qc-post-{replies[40]}").get_by_role("link", name="Reply to this post").click()
            page.get_by_label("Posting action").select_option("record-only")
            page.get_by_label("Replying to", exact=False).fill("A browser reply to the selected nested post.")
            reply_attempts = []

            def refuse_reply(route):
                reply_attempts.append(route.request.post_data_json)
                route.fulfill(status=403, content_type="application/json", body='{"error":"Reply refused for this check."}')

            page.route("**/fluid/api/posts", refuse_reply)
            page.get_by_role("button", name="Post ↑", exact=True).click()
            page.get_by_role("alert").get_by_text("Reply refused", exact=False).wait_for()
            page.unroute("**/fluid/api/posts", refuse_reply)
            page.locator(f"#qc-post-{replies[41]}").get_by_role("link", name="Reply to this post").click()
            with page.expect_request("**/fluid/api/posts") as retry:
                page.get_by_role("button", name="Post ↑", exact=True).click()
            assert retry.value.post_data_json["op"] != reply_attempts[0]["op"]
            page.get_by_text("A browser reply to the selected nested post.", exact=True).wait_for()
            posted = cv.turns(first)[-1]["turn"]
            assert get(world, f"/api/turns/{posted}")["answering"] == replies[41]
            assert not world["sent"]

            # Drafts stay with their scope across conversation switching.
            page.get_by_role("link", name="Back to conversation", exact=False).click()
            page.get_by_label("Continue the conversation").fill("A retained draft.")
            page.locator(".qc-brand").click()
            page.get_by_role("navigation", name="Conversations", exact=True).get_by_role("link", name="Quiet browser: notebook", exact=False).click()
            page.get_by_text("Notes in the other conversation.", exact=True).wait_for()
            page.go_back()
            page.get_by_role("heading", name="Quiet browser: research", exact=True).wait_for()
            page.get_by_label("Continue the conversation").wait_for()
            assert page.get_by_label("Continue the conversation").input_value() == "A retained draft."
            page.get_by_label("Posting action").select_option("record-only")
            page.get_by_role("button", name="Post ↑", exact=True).click()
            page.get_by_text("A retained draft.", exact=True).wait_for()
            assert get(world, f"/api/turns/{cv.turns(first)[-1]['turn']}")["answering"] is None

            # A focused post preserves the selected topic in the record.
            page.get_by_role("link", name="# Reading", exact=True).first.click()
            page.locator(".qc-focus").get_by_text("# Reading", exact=True).wait_for()
            page.locator(f"#qc-post-{replies[40]}").wait_for()
            page.get_by_label("Continue the conversation").fill("A new filed message.")
            page.get_by_label("Posting action").select_option("record-only")
            # A refusal must leave the draft in place and must not retry itself.
            attempts = []

            def refuse(route):
                attempts.append(route.request.post_data_json)
                route.fulfill(status=403, content_type="application/json",
                              body='{"error":"Posting refused for this check."}')

            before = len(cv.turns(first))
            page.route("**/fluid/api/posts", refuse)
            page.get_by_role("button", name="Post ↑", exact=True).click()
            page.get_by_role("alert").get_by_text("Posting refused", exact=False).wait_for()
            assert page.get_by_label("Continue the conversation").input_value() == "A new filed message."
            assert len(attempts) == 1 and len(cv.turns(first)) == before
            page.unroute("**/fluid/api/posts", refuse)
            with page.expect_request("**/fluid/api/posts") as retry:
                page.get_by_role("button", name="Post ↑", exact=True).click()
            assert retry.value.post_data_json["op"] == attempts[0]["op"]
            page.get_by_text("A new filed message.", exact=True).wait_for()
            assert cv.topics_of(cv.turns(first)[-1]["turn"], first) == [topic]

            # The small-screen margin remains reachable without horizontal spill.
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.get_by_role("button", name="Brief", exact=True).click()
            page.get_by_text("Room for a longer thought.", exact=True).wait_for()
            page.get_by_role("button", name="Activity", exact=True).click()
            page.get_by_text("No active agents reported here.", exact=True).wait_for()
            page.evaluate("scrollTo(0, 0)")
            page.screenshot(path=Path(world["root"]).parent / "quiet-mobile.png")

            # A delayed successful response belongs to its original draft and
            # must not clear a newer draft written after leaving and returning.
            page.get_by_role("button", name="Topics", exact=True).click()
            page.get_by_role("link", name="All posts", exact=False).click()
            page.locator(".qc-focus").wait_for(state="detached")
            page.get_by_label("Continue the conversation").fill("The delayed original message.")
            page.get_by_label("Posting action").select_option("record-only")
            pending = []
            page.route("**/fluid/api/posts", lambda route: pending.append(route))
            with page.expect_request("**/fluid/api/posts"):
                page.get_by_role("button", name="Post ↑", exact=True).click()
            page.locator(".qc-brand").click()
            page.get_by_role("navigation", name="Conversations", exact=True).get_by_role("link", name="Quiet browser: notebook", exact=False).click()
            page.get_by_role("heading", name="Quiet browser: notebook", exact=True).wait_for()
            page.go_back()
            page.get_by_role("heading", name="Quiet browser: research", exact=True).wait_for()
            page.get_by_label("Continue the conversation").fill("The newer draft must survive.")
            with page.expect_response("**/fluid/api/posts"):
                pending[0].continue_()
            page.unroute("**/fluid/api/posts")
            page.get_by_text("The delayed original message.", exact=True).wait_for()
            assert page.get_by_label("Continue the conversation").input_value() == "The newer draft must survive."
            assert errors == []

            # Both original addresses still mount the original Fluid shell.
            for path in ("/", "/fluid"):
                fluid_page = browser.new_page()
                try:
                    fluid_page.goto(world["base"] + path)
                    fluid_page.locator(".fw-shell.fx").wait_for()
                    assert fluid_page.locator(".qc").count() == 0
                finally:
                    fluid_page.close()
        finally:
            browser.close()


# -- what the four parallel tracks' reviews found, asked of this build --------
#
# Three of the four track branches were blocked on findings in their own code.
# The equivalent paths here are different code, so each finding is asked of
# THIS build rather than argued from the track's: the contrast of the ink
# actually painted, a conversation switched mid-page, a thread whose root was
# deleted, one voice at a time from a reader, and a resubmission's settling
# key. Nothing here reads the track branches.

#: The contrast an element's own ink actually reaches over the layers painted
#: behind it -- the computed colours, composited, not the tokens' nominal
#: values. WCAG 2.x relative luminance.
CONTRAST = r"""
(selector) => {
  const el = document.querySelector(selector)
  if (!el) return null
  const nums = (c) => (String(c).match(/[\d.]+/g) || [0, 0, 0]).map(Number)
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }
  const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])
  const over = (top, under) => {
    const a = top.length > 3 ? top[3] : 1
    return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a))
  }
  const layers = []
  for (let n = el; n; n = n.parentElement) layers.push(nums(getComputedStyle(n).backgroundColor))
  let paper = [255, 255, 255]
  for (let i = layers.length - 1; i >= 0; i--) paper = over(layers[i], paper)
  const ink = over(nums(getComputedStyle(el).color), paper)
  const pair = [lum(ink), lum(paper)].sort((a, b) => b - a)
  return { ratio: (pair[0] + 0.05) / (pair[1] + 0.05), paper: lum(paper) }
}
"""

#: Every place Quiet Chat writes in a quieter ink than body text, plus the
#: body and the primary action. --type-meta is 13px, so AA's 4.5:1 for normal
#: text is the bar everywhere here; none of this is large text.
#:
#: A CHOSEN ROW AND AN ORDINARY ONE ARE NAMED APART. `aria-current` tints the
#: row with the accent wash, which lifts the ground under the quietest ink in
#: the interface, so the two grounds are different measurements -- and a bare
#: `nav a span` would measure whichever row the server happened to list first.
QUIET_INK = (
    ".qc-eyebrow", ".qc-post > header time", ".qc-post > header a",
    ".qc-post > footer", ".qc-fluid", ".qc-brand span", ".qc-body",
    ".qc-margin", ".qc-margin h2",
    ".qc-margin nav a[aria-current='page'] span",
    ".qc-margin nav a:not([aria-current='page']) span",
    ".qc-heading nav button[aria-expanded='true']",
    ".qc-composer > label", ".qc-compose-actions > span",
    ".qc-compose-actions button",
)
#: The same, inside the conversation popover, which floats on --surface-raised
#: -- the lightest ground in dark, and so the hardest one here.
POPOVER_INK = (
    ".qc-navigation h2",
    ".qc-navigation a[aria-current='page'] span",
    ".qc-navigation a[aria-current='page'] strong",
    ".qc-navigation a:not([aria-current='page']) span",
    ".qc-navigation a:not([aria-current='page']) strong",
)


def _reads_in(page, base, conversation, name):
    """Open a conversation with posts, the margin and the composer all drawn."""
    page.goto(base + f"/quiet#/c/{conversation}")
    page.get_by_role("heading", name=name, exact=True).wait_for()
    page.locator(".qc-post").first.wait_for()
    page.get_by_label("Continue the conversation").wait_for()


def _legible(page, selectors):
    """Each selector's ratio, having checked it is actually on the page."""
    out = {}
    for selector in selectors:
        got = page.evaluate(CONTRAST, selector)
        assert got is not None, f"{selector} is not on the page to measure"
        out[selector] = got
    return out


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_quiet_chat_reconciled_findings(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    base = world["base"]
    cv, owner = world["cv"], world["who"]["@brian"]
    first = cv.open_conversation("Quiet reconcile: research", about="The conversation under review.")
    second = cv.open_conversation("Quiet reconcile: notebook", about="A second conversation to switch to.")
    cv.join(owner, first)
    cv.join(owner, second)
    cv.open_topic(first, "Reading", about="Something for the margin to list.")
    oldest = cv.say(first, owner, [text("The oldest post, only on an older page.")])
    for n in range(40):
        cv.say(first, owner, [text(f"Filler post {n}.")])
    # A thread whose root is deleted: its replies must stay reachable.
    dead_root = cv.say(first, owner, [text("The root that is about to be deleted.")])
    kept = [cv.say(first, owner, [text(f"Surviving reply {n}.")], replies_to=dead_root)
            for n in range(3)]
    versions.delete(cv, dead_root, by=owner)
    cv.say(second, owner, [text("Only the notebook's own post.")])
    assert get(world, f"/api/conversations/{first}/thread/{dead_root}")["replies_total"] == 3

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            # 1. THE INK ACTUALLY PAINTED, in both themes and both ways dark
            # arrives: the system preference, and the owner's own choice, which
            # index.html applies as `data-theme` before the first paint.
            for scheme, chosen, dark in (("dark", None, True),
                                         ("light", "dark", True),
                                         ("light", None, False)):
                page = browser.new_page(viewport={"width": 1440, "height": 1000},
                                        color_scheme=scheme)
                try:
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(base + "/quiet")
                    if chosen:
                        page.evaluate("(t) => localStorage.setItem('mentis:theme', t)", chosen)
                        # index.html reads the choice before the first paint, so
                        # it only takes effect on a load, not on a hash move.
                        page.reload()
                    _reads_in(page, base, first, "Quiet reconcile: research")
                    assert page.evaluate("document.documentElement.dataset.theme || null") == chosen
                    measured = _legible(page, QUIET_INK)
                    page.locator(".qc-brand").click()
                    page.get_by_role("navigation", name="Conversations", exact=True).wait_for()
                    measured.update(_legible(page, POPOVER_INK))
                    # Dark really is dark, and light really is light: a ratio
                    # proves nothing if the theme never took effect.
                    for selector, got in measured.items():
                        assert (got["paper"] < 0.08) == dark, (
                            f"{scheme}/{chosen}: {selector} is on the wrong plane: {got}")
                        assert got["ratio"] >= 4.5, (
                            f"{scheme}/{chosen}: {selector} reaches only "
                            f"{got['ratio']:.2f}:1")
                    page.evaluate("scrollTo(0, 0)")
                    page.screenshot(path=Path(world["root"]).parent
                                    / f"quiet-{'dark' if dark else 'light'}-{chosen or scheme}.png")
                    assert errors == []
                finally:
                    page.close()

            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            # 2. A CONVERSATION SWITCHED WHILE AN OLDER PAGE IS STILL IN FLIGHT.
            # The late answer belongs to the conversation that asked for it and
            # must reach no other; two conversations' posts never stand together.
            page.goto(base + f"/quiet#/c/{first}")
            page.get_by_role("heading", name="Quiet reconcile: research", exact=True).wait_for()
            page.locator(".qc-post").first.wait_for()
            held = []
            page.route(re.compile(r"before="), lambda route: held.append(route))
            page.get_by_role("button", name="Older posts", exact=False).click()
            page.locator(".qc-brand").click()
            page.get_by_role("navigation", name="Conversations", exact=True).get_by_role(
                "link", name="Quiet reconcile: notebook", exact=False).click()
            page.get_by_text("Only the notebook's own post.", exact=True).wait_for()
            assert held, "the older-page read was never asked for"
            with page.expect_response(lambda r: "before=" in r.url):
                held[0].continue_()
            page.get_by_role("heading", name="Quiet reconcile: notebook", exact=True).wait_for()
            assert page.locator(".qc-post").count() == 1
            assert page.locator(f"#qc-post-{oldest}").count() == 0
            assert page.get_by_text("Filler post 0.", exact=True).count() == 0
            page.unroute(re.compile(r"before="))

            # 3. A DELETED THREAD ROOT STILL CARRIES ITS REPLIES. The post says
            # it was deleted and keeps the way into the thread it roots.
            page.goto(base + f"/quiet#/c/{first}")
            tomb = page.locator(f"#qc-post-{dead_root}")
            tomb.wait_for()
            assert "This post was deleted." in tomb.inner_text()
            assert "The root that is about to be deleted." not in tomb.inner_text()
            tomb.get_by_role("link", name="Open thread · 3 replies", exact=True).click()
            page.get_by_role("heading", name="Thread #", exact=False).wait_for()
            for n in range(len(kept)):
                page.get_by_text(f"Surviving reply {n}.", exact=True).wait_for()
            assert page.locator(".qc-post").count() == 1 + len(kept)
            assert page.get_by_label("Go to post in thread").locator("option").count() == 1 + len(kept)

            # 4. ONE VOICE AT A TIME FROM A READER. `useApi` keeps the last
            # failure's words until a read succeeds, so a retry in flight must
            # not say the record is being read and cannot be read at once.
            refuse_list = {"on": True}
            held_list = []

            def listing(route):
                if refuse_list["on"]:
                    route.fulfill(status=503, content_type="application/json",
                                  body='{"error":"The conversation list is unavailable for this check."}')
                else:
                    held_list.append(route)

            page.route(re.compile(r"/api/conversations$"), listing)
            page.goto(base + "/quiet")
            page.locator(".qc-welcome .qc-error").wait_for()
            refuse_list["on"] = False
            page.locator(".qc-welcome").get_by_role("button", name="Try again", exact=True).click()
            page.locator(".qc-welcome").get_by_text("Reading…", exact=True).wait_for()
            assert page.locator(".qc-welcome .qc-error").count() == 0
            assert held_list, "Try again never asked again"
            with page.expect_response(lambda r: r.url.endswith("/api/conversations")):
                held_list[0].continue_()
            page.locator(".qc-welcome").get_by_role(
                "link", name="Quiet reconcile: notebook", exact=False).wait_for()
            assert page.locator(".qc-welcome .qc-muted").count() == 0
            page.unroute(re.compile(r"/api/conversations$"), listing)

            # 5. THE SAME SUBMISSION ASKS WITH THE SAME SETTLING KEY. A first
            # attempt whose answer never arrived may have reached the record;
            # typing the words away and back is still that one submission, so
            # its key must not change and let the record hold it twice.
            page.goto(base + f"/quiet#/c/{first}")
            page.get_by_label("Continue the conversation").wait_for()
            page.get_by_label("Posting action").select_option("record-only")
            words = "A message whose first attempt was refused."
            page.get_by_label("Continue the conversation").fill(words)
            tries = []

            def refuse(route):
                tries.append(route.request.post_data_json)
                route.fulfill(status=503, content_type="application/json",
                              body='{"error":"Posting refused for this check."}')

            before = len(cv.turns(first))
            page.route("**/fluid/api/posts", refuse)
            # Waited on the RESPONSE, which exists only once `refuse` has run
            # and recorded the attempt. The refusal alert cannot be waited on
            # between attempts: the previous one is still on screen, so it
            # would match before this attempt had been made at all. Post ↑
            # reads Sending… while one is in flight, so each click waits for
            # the composer to be free of its own accord.
            with page.expect_response("**/fluid/api/posts"):
                page.get_by_role("button", name="Post ↑", exact=True).click()
            page.get_by_role("alert").get_by_text("Posting refused", exact=False).wait_for()
            page.get_by_label("Continue the conversation").fill(words + " Second thoughts.")
            page.get_by_label("Continue the conversation").fill(words)
            with page.expect_response("**/fluid/api/posts"):
                page.get_by_role("button", name="Post ↑", exact=True).click()
            assert len(tries) == 2
            assert tries[1]["op"] == tries[0]["op"], (
                "editing away and back made a second submission of one")
            # Different words are a different submission and say so.
            page.get_by_label("Continue the conversation").fill("Different words entirely.")
            with page.expect_response("**/fluid/api/posts"):
                page.get_by_role("button", name="Post ↑", exact=True).click()
            assert len(tries) == 3 and tries[2]["op"] != tries[0]["op"]
            assert page.get_by_label("Continue the conversation").input_value() == "Different words entirely."
            page.unroute("**/fluid/api/posts", refuse)
            assert len(cv.turns(first)) == before
            assert not world["sent"]
            assert errors == []
            page.close()
        finally:
            browser.close()
