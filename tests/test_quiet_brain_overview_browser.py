"""ABOUT THIS BRAIN, in a real browser.

The real built Quiet Chat (`/quiet2`) against a real HTTP server backed by a
disposable fixture Brain (`tests/_loop.py`'s `world`): no mock, no live Brain.
Reached the way a reader reaches it: the Brain button, then "About".

What is checked: it opens inside the Brain card (no new page), says a few
lines first with every number the server's own (`/api/brain/overview`), keeps
the detail folded until asked, tells counts from sizes and says what a
portable backup includes and leaves out, works from the keyboard, returns
focus, and fits a 390 px phone. Screenshots go to
`MENTIS_OVERVIEW_SHOTS` where that is set.

Build apps/fluid-web first, then opt in with MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import os
import re

import pytest

from mentis import artifacts

from tests._loop import world, post, get  # noqa: F401
from tests.conftest import owner_headers

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="build the UI (apps/fluid-web) and set MENTIS_QUIET_BROWSER=1",
)

ENGINE = "chrome"
MS = 15000
SHOTS = os.environ.get("MENTIS_OVERVIEW_SHOTS")
#: the Brain card itself (Sources draws a card of the same class)
CARD = '.q2-brain-card[aria-label="Brain"]'


@pytest.fixture
def filled(world):
    """A Brain with something of each sort to count."""
    me = world["who"]["@brian"]
    st = world["state"]
    conv = post(world, "/api/conversations", {"name": "Release check"})["conversation"]
    for words in ("Is TEST ready?", "It is."):
        post(world, f"/api/conversations/{conv}/turns", {"author": me, "text": words})
    rule = post(world, "/api/entries", {"kind": "rule", "body": {"text": "Deploy to TEST first."},
                                        "attributed_to": me, "establish": False})["entry"]
    post(world, f"/api/entries/{rule}/establish", {"attributed_to": me, "because": "the owner said so"})
    post(world, "/api/entries", {"kind": "rule", "body": {"text": "Ask before a restart."},
                                 "attributed_to": me, "establish": False})
    post(world, "/api/entries", {"kind": "note", "body": {"text": "The deploy was refused."},
                                 "attributed_to": me, "establish": False})
    data = b"the same bytes, attached twice " * 200
    for name in ("one.txt", "again.txt"):
        artifacts.hold(st.corpus, st.cv, data, act="artifact-submitted", actor=me,
                       source=f"submission:{me}", door="human-ingress", claimed_name=name)
    os.makedirs(os.path.join(world["root"], "derived"), exist_ok=True)
    with open(os.path.join(world["root"], "derived", "index.bin"), "wb") as fh:
        fh.write(b"x" * 5000)
    return {"conv": conv, "me": me}


def _page(playwright, width=1440, height=1000):
    browser = playwright.chromium.launch(channel=ENGINE, headless=True)
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return browser, page, errors


def _open(page, world, conversation=None):
    page.context.set_extra_http_headers(owner_headers())
    page.goto(world["base"] + "/quiet2" + (f"?c={conversation}" if conversation else ""))
    page.get_by_role("button", name="Brain", exact=True).wait_for(timeout=MS)


def _about(page):
    page.get_by_role("button", name="Brain", exact=True).click()
    page.get_by_role("button", name="About this Brain").click()
    page.locator("[data-brain-overview] [data-bo='holds']").wait_for(timeout=MS)
    return page.locator("[data-brain-overview]")


def _shot(page, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=os.path.join(SHOTS, name))


def _n(n):
    return f"{n:,}"


def test_the_overview_opens_in_the_brain_card_and_its_numbers_are_the_servers(world, filled):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, filled["conv"])
        address = page.url
        about = _about(page)
        api = get(world, "/api/brain/overview")
        c = api["counts"]

        # in the card, over nothing new: the same address, the same dialog
        assert page.url == address
        assert about.evaluate("el => !!el.closest('.q2-brain-card[role=dialog]')")
        assert page.locator(CARD + " > .q2-cl").is_hidden()

        holds = about.locator("[data-bo='holds']").inner_text()
        assert f"{_n(c['conversations']['total'])} conversation" in holds
        assert f"{_n(c['posts'])} post" in holds
        assert f"{_n(c['knowledge']['total'])} knowledge record" in holds
        assert f"{_n(c['governing']['total'])} governing record" in holds
        adopted = next(s["count"] for s in c["governing"]["standing"] if s["status"] == "adopted")
        assert adopted >= 1 and f"{_n(adopted)} in effect" in holds
        # one file, two references: the file is counted once and both are said
        assert c["files"]["references"] == c["files"]["unique"] + 1
        assert f"{_n(c['files']['unique'])} file" in holds
        assert f"referred to {_n(c['files']['references'])} times" in holds

        # counts and sizes are told apart, and no id is shown
        heads = about.locator("h3").all_inner_texts()
        assert any("counts of things" in h.lower() for h in heads) and any("sizes on disk" in h.lower() for h in heads)
        assert not re.search(r"\b(KB|MB|GB|bytes)\b", holds)
        disk = about.locator("[data-bo='disk']").inner_text()
        assert disk.startswith("Database ") and "Files " in disk and re.search(r"\b(KB|MB|GB|bytes)\b", disk)
        assert not re.search(r"\b(ent|adm|opr|col)-[0-9a-f]{6}", about.inner_text())

        # what moving it takes, with what that includes and leaves out, beside it
        move = about.locator("[data-bo='portable']").inner_text()
        assert "as a portable backup" in move and "Includes the database" in move and "Leaves out" in move
        assert "rebuilt or belongs to this computer" in move
        stored = next(x for x in api["portable"]["parts"] if x["part"] == "files")["count"]
        assert (f"all {_n(stored)} stored files, each once" in move) or ("the 1 stored file" in move)

        # DETAIL ON DEMAND: folded until asked for
        details = about.locator("details")
        assert details.count() == 5
        assert details.evaluate_all("els => els.every(d => !d.open)")
        assert not about.get_by_text("Attached by people").is_visible()
        about.locator("[data-bo-detail='files'] summary").click()
        assert about.get_by_text("Attached by people").is_visible()
        about.locator("[data-bo-detail='governing'] summary").click()
        gov = about.locator("[data-bo-detail='governing']").inner_text()
        for s in c["governing"]["standing"]:
            if s["count"]:
                assert str(s["count"]) in gov
        assert "Adopted" in gov and "in effect" in gov and "Rule" in gov
        about.locator("[data-bo-detail='left-out'] summary").click()
        left = about.locator("[data-bo-detail='left-out']").inner_text()
        assert "Search and status indexes (rebuilt)" in left and "python -m mentis.brain backup --portable" in left
        _shot(page, "overview-desktop.png")

        # measured, dated, and measured again only when asked
        seen: list[str] = []
        page.on("request", lambda r: seen.append(r.url) if "/api/brain/overview" in r.url else None)
        assert "Files on disk measured at" in about.locator("[data-bo='measured']").inner_text()
        about.locator("[data-bo-measure]").click()
        page.wait_for_function("() => !document.querySelector('[data-bo-measure]').disabled")
        assert seen and seen[-1].endswith("/api/brain/overview?measure=1")

        # back to the records as they were; nothing was written
        about.get_by_role("button", name="Back to the records").click()
        page.locator(CARD + " > .q2-cl").wait_for(state="visible", timeout=MS)
        assert page.locator("[data-brain-overview]").count() == 0
        assert not errors, errors
        browser.close()


def test_the_overview_works_from_the_keyboard_and_gives_focus_back(world, filled):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, filled["conv"])
        page.get_by_role("button", name="Brain", exact=True).click()
        page.locator(CARD + " input[type=search]").wait_for(timeout=MS)
        about_button = page.get_by_role("button", name="About this Brain")
        about_button.focus()
        page.keyboard.press("Enter")
        about = page.locator("[data-brain-overview]")
        about.locator("[data-bo='holds']").wait_for(timeout=MS)
        # focus is inside it, on the way back
        assert page.evaluate("document.activeElement.getAttribute('aria-label')") == "Back to the records"

        # Tab reaches each folded part; Enter opens it; focus is always visible
        reached = []
        for _ in range(12):
            page.keyboard.press("Tab")
            tag = page.evaluate("document.activeElement.tagName")
            inside = page.evaluate("!!document.activeElement.closest('.q2-brain-card')")
            assert inside, "Tab left the Brain card"
            if tag == "SUMMARY":
                reached.append(page.evaluate("document.activeElement.textContent"))
                assert page.evaluate(
                    "(() => { const s = getComputedStyle(document.activeElement); "
                    "return s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0 })()")
                if len(reached) == 1:
                    page.keyboard.press("Enter")
                    assert about.locator("[data-bo-detail='knowledge']").evaluate("d => d.open")
        assert reached[:5] == ["Knowledge by kind", "Governing records by standing", "Files, by how they arrived",
                               "On disk, part by part", "Not in a portable backup"]

        # Escape leaves the overview first (the card stays), then the card
        page.keyboard.press("Escape")
        page.locator(CARD + " > .q2-cl").wait_for(state="visible", timeout=MS)
        assert page.locator("[data-brain-overview]").count() == 0
        page.wait_for_function("() => document.activeElement?.getAttribute('aria-label') === 'About this Brain'")
        page.keyboard.press("Escape")
        page.locator(CARD).wait_for(state="hidden", timeout=MS)
        assert not errors, errors
        browser.close()


def test_the_overview_fits_a_phone(world, filled):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p, width=390, height=844)
        _open(page, world, filled["conv"])
        about = _about(page)
        for part in ("knowledge", "governing", "files", "disk", "left-out"):
            about.locator(f"[data-bo-detail='{part}'] summary").click()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        body = about.locator(".q2-bo-body")
        assert body.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        box = about.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390 + 1
        # everything is reachable by scrolling the sheet itself
        about.locator("[data-bo-measure]").scroll_into_view_if_needed()
        assert about.locator("[data-bo-measure]").is_visible()
        _shot(page, "overview-phone.png")
        about.get_by_role("button", name="Close").click()
        page.locator(CARD).wait_for(state="hidden", timeout=MS)
        assert not errors, errors
        browser.close()
