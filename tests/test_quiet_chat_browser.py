"""Quiet Chat against real Mentis HTTP routes on a disposable fixture Brain.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mentis.conversation import text
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
