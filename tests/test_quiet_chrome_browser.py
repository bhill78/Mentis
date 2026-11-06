"""Package A (header and conversation navigation) against real Mentis HTTP
routes on a disposable fixture Brain.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import get, world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_chrome_header_and_navigation(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cv, owner, nadia = world["cv"], world["who"]["@brian"], world["who"]["@Nadia"]

    # Four quiet fillers, oldest first; a heavily active conversation (many
    # turns, an open ask, a live execution); a freshly touched conversation
    # last, so it reads newest. A real sleep between each: `last_activity`
    # is a wall-clock timestamp, and this run's many rapid writes can
    # otherwise land in the same tick and tie on it.
    fillers = []
    for n in range(4):
        f = cv.open_conversation(f"Quiet chrome: filler {n}")
        cv.join(owner, f)
        cv.say(f, owner, [text(f"A filler post {n}.")])
        fillers.append(f)
        time.sleep(0.02)

    busy = cv.open_conversation("Quiet chrome: heavily active", about="Lots going on.")
    cv.join(owner, busy)
    cv.join(nadia, busy)
    for n in range(20):
        cv.say(busy, owner, [text(f"Busy post {n}.")])
    cv.say(busy, owner, [text("A question for Nadia.")], addressed_to=[nadia])
    cv.begin_execution(participant=nadia, conversation=busy)
    time.sleep(0.02)

    quiet = cv.open_conversation("Quiet chrome: barely touched", about="Not much here.")
    cv.join(owner, quiet)
    cv.say(quiet, owner, [text("One quiet post.")])

    # However many conversations the fixture Brain already holds, this is
    # now all of them -- the five shown, plus whatever "reveal more" adds.
    total = len(get(world, "/api/conversations")["conversations"])

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            refs_requests = []
            page.on("request", lambda r: refs_requests.append(r.url)
                    if "/api/references" in r.url else None)

            page.goto(world["base"] + f"/quiet#/c/{quiet}")
            page.get_by_role("heading", name="Quiet chrome: barely touched", exact=True).wait_for()

            # 1. THE LOGO IS NO LONGER A SECOND CONVERSATION PICKER (owner,
            # 2026-11-06 request: remove duplicate conversation selection
            # controls, which governs over the same-day decision this test
            # once checked). It is a plain link to /quiet; the margin nav
            # below is the sole conversation selector.
            assert page.get_by_role("navigation", name="Conversations", exact=True).count() == 0
            brand = page.locator(".qc-brand")
            assert brand.get_attribute("href") == "/quiet"
            assert brand.evaluate("el => el.tagName") == "A"

            # 1b. THE HEADER'S REMAINING SECONDARY OPTION (owner, 2026-11-06
            # feedback: condense header options into an accessible
            # hamburger-style menu at the top left) sits behind a disclosure
            # at the header's top left, beside the brand -- not inside it,
            # and Settings (top right) is untouched by this.
            menu_button = page.get_by_role("button", name="Menu", exact=True)
            menu_button.wait_for()
            menu_btn_box = menu_button.bounding_box()
            brand_box = brand.bounding_box()
            settings_box = page.get_by_role("button", name="Settings", exact=True).bounding_box()
            assert menu_btn_box["x"] <= brand_box["x"], "the menu button is not at the header's left"
            assert menu_btn_box["x"] < settings_box["x"], "the menu button is not left of Settings"
            assert menu_button.get_attribute("aria-expanded") == "false"
            fluid_link = page.get_by_role("link", name="Open Fluid ↗", exact=True)
            assert not fluid_link.is_visible(), "Open Fluid is visible before the menu opens"

            menu_button.click()
            assert menu_button.get_attribute("aria-expanded") == "true"
            assert fluid_link.is_visible()
            page.keyboard.press("Escape")
            assert menu_button.get_attribute("aria-expanded") == "false"
            assert not fluid_link.is_visible()
            # Reopen, then dismiss with an outside click.
            menu_button.click()
            assert menu_button.get_attribute("aria-expanded") == "true"
            page.mouse.click(10, 10)
            assert menu_button.get_attribute("aria-expanded") == "false"
            # Settings remains its own, separate disclosure at the top right.
            settings_button = page.get_by_role("button", name="Settings", exact=True)
            settings_button.click()
            assert settings_button.get_attribute("aria-expanded") == "true"
            page.keyboard.press("Escape")

            # 2. FIVE MOST RECENT, TEXT-FREE MARKS. Newest (quiet, just
            # posted) and the busy conversation are both among them; the
            # oldest filler is not, until "reveal more" is pressed.
            nav = page.get_by_role("navigation", name="Conversations by recency", exact=True)
            marks = nav.locator(".qc-nav-mark")
            assert marks.count() == 5
            for i in range(5):
                assert marks.nth(i).inner_text().strip() == ""
            quiet_mark = nav.get_by_role("link", name="Quiet chrome: barely touched", exact=True)
            busy_mark = nav.get_by_role("link", name="Quiet chrome: heavily active", exact=True)
            quiet_mark.wait_for()
            busy_mark.wait_for()
            assert nav.get_by_role("link", name="Quiet chrome: filler 0", exact=True).count() == 0

            # 3. THICKNESS READS ACTIVITY, and never falls as live work rises:
            # for a vertical mark, thickness is the box's actual painted
            # width (boundingClientRect, which includes any border), not
            # just the CSS `width` property -- a border could still inflate
            # the rendered box past its own content width. Measure both and
            # require them to agree, so a reintroduced border-based recency
            # accent would be caught here, not just in CSS content width.
            def painted_width(locator):
                css_w = float(locator.evaluate("el => getComputedStyle(el).width").replace("px", ""))
                rendered_w = locator.evaluate("el => el.getBoundingClientRect().width")
                assert rendered_w == pytest.approx(css_w, abs=0.5)
                return rendered_w

            busy_w = painted_width(busy_mark.locator(".qc-nav-mark-bar"))
            quiet_w = painted_width(quiet_mark.locator(".qc-nav-mark-bar"))
            assert busy_w > quiet_w

            # 4. RECENCY READS AS AN INNER ACCENT, not an added border: the
            # newest shown mark (quiet, first) and the oldest shown mark
            # (fifth) paint a different background, but neither mark's bar
            # has a border at all -- the accent can only be an inner layer,
            # never something that grows the box.
            for m in (marks.first, marks.last):
                bar = m.locator(".qc-nav-mark-bar")
                assert bar.evaluate("el => getComputedStyle(el).borderLeftWidth") == "0px"
            newest_bg = marks.first.locator(".qc-nav-mark-bar").evaluate("el => getComputedStyle(el).backgroundImage")
            oldest_bg = marks.last.locator(".qc-nav-mark-bar").evaluate("el => getComputedStyle(el).backgroundImage")
            assert newest_bg != oldest_bg

            # 5. THICKNESS STAYS ACTIVITY'S, EVEN AT THE STRONGEST RECENCY
            # ACCENT: quiet_mark is also marks.first -- the most recent mark
            # shown, so it carries the strongest recency accent of anyone on
            # screen. Its painted width must still equal its own low-activity
            # weight, not be inflated by that accent -- the exact inversion
            # finding 1 identified (a quiet mark reading thicker than it
            # should once recency leaks into total thickness).
            quiet_weight_px = float(quiet_mark.evaluate("el => getComputedStyle(el).getPropertyValue('--qc-mark-weight')").replace("px", ""))
            assert quiet_w == pytest.approx(quiet_weight_px, abs=0.5)
            assert quiet_w < busy_w

            # 6. HOVER REVEALS THE LABEL; it carries no text until then.
            quiet_mark.hover()
            page.wait_for_timeout(50)
            assert quiet_mark.inner_text().strip() == "Quiet chrome: barely touched"
            label = quiet_mark.locator(".qc-nav-mark-label")
            # Hit-testing at the far edge proves the label is painted outside
            # the scrolling nav cell, not merely laid out beyond its clip.
            assert label.evaluate("""el => {
                const r = el.getBoundingClientRect();
                return document.elementFromPoint(r.right - 2, r.top + r.height / 2) === el;
            }""")
            page.mouse.move(0, 0)
            page.set_viewport_size({"width": 800, "height": 1000})
            for i in range(5):
                assert marks.nth(i).inner_text().strip() == ""
            quiet_mark.focus()
            assert quiet_mark.locator(".qc-nav-mark-label").is_visible()
            quiet_mark.blur()
            page.set_viewport_size({"width": 1440, "height": 1000})

            # 6. THE ACTIVE MARK (this is quiet's own page) computes a
            # different emphasis from a neighbour that is not current --
            # the text-free design carries it on the bar's own colour
            # (TRACK 2), not a row background: the row itself stays
            # transparent at every mark, current or not.
            active_bar = quiet_mark.locator(".qc-nav-mark-bar").evaluate("el => getComputedStyle(el).backgroundColor")
            neighbour_bar = busy_mark.locator(".qc-nav-mark-bar").evaluate("el => getComputedStyle(el).backgroundColor")
            assert active_bar != neighbour_bar

            # 7. A REVEAL-MORE CONTROL SHOWS THE REST.
            more = nav.get_by_role("button", name="more", exact=False)
            more.wait_for()
            more.click()
            assert nav.locator(".qc-nav-mark").count() == total
            nav.get_by_role("link", name="Quiet chrome: filler 0", exact=True).wait_for()

            # 8. SEARCH FILTERS CLIENT-SIDE, OVER WHAT WAS ALREADY LOADED --
            # never by asking the server again.
            nav.get_by_role("button", name="Find a conversation", exact=True).click()
            field = nav.get_by_role("searchbox", name="Find a conversation", exact=True)
            field.fill("barely touched")
            assert nav.locator(".qc-nav-mark").count() == 1
            nav.get_by_role("link", name="Quiet chrome: barely touched", exact=True).wait_for()
            assert refs_requests == [], "conversation search must never ask /api/references"
            field.fill("")
            nav.get_by_role("button", name="Find a conversation", exact=True).click()

            # 9. TAB REACHES EVERY MARK: none opts out of the tab order, and
            # each carries an accessible name even though it shows no text.
            all_marks = nav.locator(".qc-nav-mark")
            assert all_marks.count() == total
            for i in range(total):
                mark = all_marks.nth(i)
                assert mark.evaluate("el => el.tabIndex") >= 0
                assert mark.get_attribute("aria-label")

            # 10. ENTER FOLLOWS A FOCUSED MARK.
            target = all_marks.last
            target_name = target.get_attribute("aria-label")
            target.focus()
            page.keyboard.press("Enter")
            page.get_by_role("heading", name=target_name, exact=True).wait_for()

            # 11. TYPOGRAPHY (plan §1): title, eyebrow and header controls
            # take three distinct steps -- title largest, controls no
            # larger than the eyebrow.
            title = page.locator(".qc-heading h1").evaluate("el => getComputedStyle(el).fontSize")
            eyebrow = page.locator(".qc-eyebrow").evaluate("el => getComputedStyle(el).fontSize")
            control = page.locator(".qc-fluid").evaluate("el => getComputedStyle(el).fontSize")
            assert len({title, eyebrow, control}) == 3
            assert float(title.replace("px", "")) > float(eyebrow.replace("px", ""))
            assert float(control.replace("px", "")) <= float(eyebrow.replace("px", ""))

            assert errors == []
        finally:
            browser.close()
