"""THE COMPACT BRAIN RECORD EDITOR, in a real browser.

The real built Quiet Chat (`/quiet2`) against a real HTTP server backed by a
disposable fixture Brain (`tests/_loop.py`'s `world`): no mock form, no live
Brain, no MARS. Reached the way a reader reaches it -- the rail's Brain
button, its menu, a Kind by name; a conversation's Instructions; a record's
own menu.

What is checked is what the owner approved (2026-11-18):

  - a compact modal over the workspace, never at the composer, small at the
    start, growing only when asked;
  - all seven Kinds, each by name;
  - references chosen by their words (records, posts, files), never typed ids;
  - RECORDING WRITES A PROPOSAL, in the request and in the Brain, for every
    door; establishing is a separate act on the record;
  - the conversation's Instructions box opens the same editor and no longer
    establishes;
  - revising uses the same editor, shows what changes, and leaves a standing
    record standing;
  - typed work is never dropped without a question; keyboard, focus, Escape
    and a phone-width layout.

These replace the Quiet-hosted scenarios of `test_quiet_governance_create_
browser.py` (the creation page that no longer exists) one for one where the
behaviour still exists; see that file's note.

Build apps/fluid-web first, then opt in with MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import json
import os
import re

import pytest

from tests._loop import world, post, get  # noqa: F401
from tests.conftest import OWNER_PASSPHRASE

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="build the UI (apps/fluid-web) and set MENTIS_QUIET_BROWSER=1",
)

ENGINE = "chrome"
MS = 15000
SEVEN = ["Rule", "Decision", "Lesson", "Persona", "Workflow", "Discipline", "Conversation instruction"]


# -- fixture state ------------------------------------------------------------

@pytest.fixture
def me_id(world):
    rows = get(world, "/api/participants?limit=1")["participants"]
    assert rows
    return rows[0]["participant"]


@pytest.fixture
def conv(world):
    return post(world, "/api/conversations", {"name": "Release check"})["conversation"]


@pytest.fixture
def note(world, me_id):
    return post(world, "/api/entries", {
        "kind": "note", "body": {"text": "The deploy call was refused from inside the hosting run."},
        "attributed_to": me_id, "establish": False})["entry"]


def _page(playwright, width=1440, height=1000):
    browser = playwright.chromium.launch(channel=ENGINE)
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return browser, page, errors


def _open(page, world, conversation=None):
    r = page.request.post(world["base"] + "/api/owner/login",
                          headers={"X-Mentis-Client": "1", "Content-Type": "application/json"},
                          data=json.dumps({"passphrase": OWNER_PASSPHRASE}))
    assert r.ok, (r.status, r.text())
    page.goto(world["base"] + "/quiet2" + (f"?c={conversation}" if conversation else ""))
    page.get_by_role("button", name="Brain", exact=True).wait_for(timeout=MS)


def _new(page, label):
    """Brain button -> its menu -> a Kind by name: the real way in."""
    page.get_by_role("button", name="Brain", exact=True).click()
    page.get_by_role("button", name="Make, import, preview").click()
    page.get_by_role("menuitem", name=f"{label}…", exact=True).click()
    page.locator("[data-author-modal] [data-author]").wait_for(timeout=MS)
    return page.locator("[data-author-modal]")


def _sent(page):
    """Every write the page makes from now on, as (path, body)."""
    seen: list[tuple[str, dict]] = []

    def on(req):
        if req.method == "POST" and "/api/" in req.url and "/owner/" not in req.url:
            try:
                seen.append((re.sub(r"^https?://[^/]+", "", req.url), req.post_data_json or {}))
            except Exception:  # noqa: BLE001 - a body that is not JSON is not ours
                pass
    page.on("request", on)
    return seen


def _record(modal):
    modal.locator("[data-record]").click()


def _done(modal):
    modal.locator("[data-author-done]").wait_for(timeout=MS)
    return modal.locator("[data-author-done]").get_attribute("data-author-done")


def _stands(world, entry):
    return get(world, f"/api/entries/{entry}")["stands"]


def _add(modal, part):
    modal.locator("[data-add]").click()
    modal.locator(f'[data-add-part="{part}"]').click()


def _no_sideways(page):
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


# -- 1. the modal: where it is, and how little it starts with ------------------

def test_new_lists_the_seven_kinds_and_a_rule_is_recorded_from_one_field(world, conv, me_id):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        page.get_by_role("button", name="Brain", exact=True).click()
        page.get_by_role("button", name="Make, import, preview").click()
        page.get_by_role("menuitem", name="Rule…", exact=True).wait_for(timeout=MS)
        items = [t.rstrip("…") for t in page.get_by_role("menuitem").all_inner_texts()]
        assert items[:7] == SEVEN, items
        page.get_by_role("menuitem", name="Rule…", exact=True).click()
        modal = page.locator("[data-author-modal]")
        ed = modal.locator("[data-author='rule']")
        ed.wait_for(timeout=MS)
        # small at the start: one writing area, and nothing optional on screen
        assert ed.locator("textarea").count() == 1 and ed.locator("input, select").count() == 0
        assert ed.locator("button").all_inner_texts() == ["+ Add", "Cancel", "Record"]
        assert "proposal" in ed.inner_text().lower()
        assert ed.locator("textarea").evaluate("el => el === document.activeElement")
        # not at the composer: the modal is its own dialog over the page
        assert page.locator(".q2-dock [data-author]").count() == 0
        assert modal.get_by_role("dialog").get_attribute("aria-modal") == "true"
        sent = _sent(page)
        page.keyboard.type("Say before building when a run cannot deploy itself.")
        page.keyboard.press("Control+Enter")
        entry = _done(modal)
        path, body = sent[0]
        assert path == "/api/entries" and body["kind"] == "rule" and body["establish"] is False
        assert len(sent) == 1, sent
        assert _stands(world, entry) is False
        assert "It is a proposal" in modal.inner_text()
        # Done returns to Brain management as it was
        modal.locator("[data-done]").click()
        assert page.locator("[data-author-modal]").count() == 0
        assert page.get_by_role("dialog", name="Brain").is_visible()
        assert not errors, errors
        browser.close()


def test_open_the_record_after_recording_and_establish_is_a_separate_act(world, conv, me_id):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Rule")
        page.keyboard.type("Ask who runs the deploy step.")
        _record(modal)
        entry = _done(modal)
        modal.locator("[data-open-record]").click()
        rec = page.locator(f'[data-record="{entry}"]')
        rec.wait_for(timeout=MS)
        assert _stands(world, entry) is False
        # the owner's own, separate act: Establish, with a reason
        rec.get_by_role("button", name="More on this record").click()
        page.get_by_role("menuitem", name=re.compile("^Establish")).click()
        host = rec.locator(".rv-act-host")
        host.locator("textarea").first.fill("It was read the wrong way twice.")
        host.get_by_role("button", name="Establish now").click()
        page.wait_for_function("async (u) => (await (await fetch(u)).json()).stands === true",
                               arg=world["base"] + f"/api/entries/{entry}", timeout=MS)
        assert not errors, errors
        browser.close()


# -- 2. evidence: found by its words ------------------------------------------

def test_a_lesson_needs_evidence_and_it_is_found_by_words(world, conv, me_id, note):
    post(world, f"/api/conversations/{conv}/turns", {"author": me_id, "text": "Nobody told me the release could not deploy itself."})
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Lesson")
        ed = modal.locator("[data-author='lesson']")
        assert ed.locator("textarea").count() == 1
        assert ed.locator(".ba-need").inner_text().startswith("Choose what this is based on")
        page.keyboard.type("A run hosted by an environment cannot restart it.")
        sent = _sent(page)
        _record(modal)
        assert "has to be based on something already held" in ed.inner_text() and not sent
        assert ed.locator(".ba-need").evaluate("el => el === document.activeElement")
        page.keyboard.press("Enter")
        finder = ed.locator("[data-finder]")
        finder.wait_for(timeout=MS)
        # records, posts and files are all offered: nothing narrower than the server takes
        assert finder.get_by_role("tab").all_inner_texts() == ["Brain records", "Posts", "Files"]
        page.keyboard.type("deploy refused")
        row = finder.get_by_role("option").filter(has_text="The deploy call was refused")
        row.first.wait_for(timeout=MS)
        assert note not in finder.inner_text()  # words, never the reference
        page.keyboard.press("Enter")
        assert row.first.get_attribute("aria-selected") == "true"
        # a post, found by its words
        finder.get_by_role("tab", name="Posts").click()
        page.keyboard.type("could not deploy itself")
        post_row = finder.get_by_role("option").filter(has_text="Nobody told me")
        post_row.first.wait_for(timeout=MS)
        post_row.first.click()
        page.keyboard.press("Escape")
        assert ed.locator("[data-finder]").count() == 0
        assert ed.locator(".ba-chip").count() == 2
        assert modal.count() == 1  # Escape closed the finder, not the editor
        # a lesson recorded as a proposal is not asked how the evidence leads to it
        assert ed.locator('[data-part="basisReason"]').count() == 0
        _record(modal)
        entry = _done(modal)
        path, body = sent[0]
        assert path == "/api/entries" and body["establish"] is False
        assert note in body["basis"] and len(body["basis"]) == 2
        assert len(sent) == 1  # the basis rode on the create; nothing cited twice
        assert _stands(world, entry) is False
        assert not errors, errors
        browser.close()


def test_removing_the_last_evidence_of_a_lesson_brings_the_requirement_back(world, conv, me_id, note):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Lesson")
        ed = modal.locator("[data-author='lesson']")
        ed.locator(".ba-need").click()
        ed.get_by_role("option").filter(has_text="The deploy call was refused").first.click()
        ed.locator("[data-finder-done]").click()
        assert ed.locator(".ba-chip").count() == 1
        ed.locator(".ba-chip .ba-x").click()
        assert ed.locator(".ba-need").count() == 1 and ed.locator(".ba-chip").count() == 0
        # a reference somebody already has can still be given, and reads as words
        ed.locator(".ba-need").click()
        ed.get_by_role("button", name="Paste a reference").click()
        page.keyboard.type(note)
        page.keyboard.press("Enter")
        ed.get_by_text("1 chosen").wait_for(timeout=MS)
        ed.locator("[data-finder-done]").click()
        ed.locator(".ba-chip").wait_for(timeout=MS)
        assert "The deploy call was refused" in ed.locator(".ba-chip").inner_text()
        assert not errors, errors
        browser.close()


def test_a_rule_with_evidence_and_a_placement_is_three_acts_in_order_and_retries(world, conv, me_id, note):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Rule")
        ed = modal.locator("[data-author='rule']")
        page.keyboard.type("Say so before building.")
        _add(modal, "basis")
        ed.get_by_role("option").filter(has_text="The deploy call was refused").first.click()
        ed.locator("[data-finder-done]").click()
        _add(modal, "place")
        # the conversation the reader is in is offered first, never assumed
        assert "Release check" in ed.locator('[data-part="place"]').inner_text()
        assert "Whole Brain" not in ed.inner_text()
        sent = _sent(page)
        _record(modal)
        assert "Say how what you chose leads to this." in ed.inner_text() and not sent
        ed.locator('[data-part="basisReason"] textarea').fill("It is what happened.")
        _record(modal)
        assert "Say why it belongs there." in ed.inner_text() and not sent
        ed.locator('[data-part="placeReason"]').fill("It was asked here.")
        # the placement fails once: the record stays, and only the rest is tried again
        fails = {"n": 1}

        def once(route):
            if fails["n"]:
                fails["n"] -= 1
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"error": "refused for the test"}))
            else:
                route.continue_()
        page.route("**/api/entries/*/place", once)
        _record(modal)
        ed.get_by_text("was not").wait_for(timeout=MS)
        assert "It was recorded as a proposal" in ed.inner_text()
        assert [s[0].split("/")[-1] for s in sent] == ["entries", "derive-from", "place"]
        # what was sent is what a retry finishes: the draft is no longer for editing,
        # so the remaining act cannot be dropped or changed by touching it
        assert ed.locator(".ba-chip .ba-x").first.evaluate("el => !!el.closest('[inert]')")
        assert ed.locator("textarea").first.evaluate("el => !!el.closest('[inert]')")
        # and the record that WAS made can be opened as it is, as the message says
        assert modal.locator("[data-open-made]").is_visible()
        modal.locator("[data-record]").click()
        entry = _done(modal)
        paths = [s[0] for s in sent]
        assert paths.count("/api/entries") == 1 and paths[-1] == f"/api/entries/{entry}/place"
        assert paths.count(f"/api/entries/{entry}/derive-from") == 1
        assert sent[0][1]["establish"] is False and all("establish" not in s[0] for s in sent)
        got = get(world, f"/api/entries/{entry}")
        assert got["stands"] is False
        assert [x["where"] for x in got["governance_actions"]["placements"]] == [conv]
        assert not errors, errors
        browser.close()


# -- 3. the other Kinds --------------------------------------------------------

def test_a_persona_is_recorded_as_a_proposal(world, conv, me_id):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Persona")
        ed = modal.locator("[data-author='persona']")
        assert ed.locator("input[type=text], textarea").count() == 2
        sent = _sent(page)
        page.keyboard.type("Release Reviewer")
        _record(modal)
        assert "Say how the persona should behave." in ed.inner_text() and not sent
        page.keyboard.type("Reads the diff against its request before anything else.")
        _record(modal)
        entry = _done(modal)
        path, body = sent[0]
        assert path == "/api/personas" and body["propose"] is True and body["establish"] is False
        assert body["name"] == "Release Reviewer"
        assert _stands(world, entry) is False
        assert not errors, errors
        browser.close()


def test_a_decision_links_the_question_it_settles(world, conv, me_id):
    post(world, f"/api/conversations/{conv}/turns", {"author": me_id, "text": "Do releases go to TEST first?"})
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Decision")
        ed = modal.locator("[data-author='decision']")
        assert ed.locator("textarea").count() == 1
        assert "does not answer or close an open request" in ed.inner_text()
        ed.get_by_role("button", name="See an example").click()
        assert ed.locator(".ba-example").count() == 1
        ed.locator("textarea").first.fill("Releases go to TEST first, always.")
        _add(modal, "context")
        ed.locator("[data-finder] input").first.fill("TEST first")
        ed.get_by_role("option").filter(has_text="Do releases go to TEST first?").first.click()
        assert "Do releases go to TEST first?" in ed.locator(".ba-chip").inner_text()
        sent = _sent(page)
        _record(modal)
        entry = _done(modal)
        body = sent[0][1]
        assert body["kind"] == "decision" and body["establish"] is False
        assert [l["relation"] for l in body["links"]] == ["in-context"]
        assert _stands(world, entry) is False
        assert not errors, errors
        browser.close()


def test_the_instructions_box_opens_the_same_editor_and_does_not_establish(world, conv, me_id):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        page.get_by_role("button", name="Instructions").click()
        box = page.locator(f'[data-instructions="{conv}"]')
        box.wait_for(timeout=MS)
        assert box.locator("textarea, input").count() == 0  # nothing is typed here any more
        assert "Establish" not in box.inner_text()
        box.locator("[data-new-instruction]").click()
        modal = page.locator("[data-author-modal]")
        ed = modal.locator("[data-author='conversation-instruction']")
        ed.wait_for(timeout=MS)
        assert "Release check" in ed.locator('[data-part="conversation"]').inner_text()
        page.keyboard.type("Say what was verified before saying it is done.")
        sent = _sent(page)
        _record(modal)
        entry = _done(modal)
        path, body = sent[0]
        assert path == f"/api/conversations/{conv}/instructions" and body["establish"] is False
        assert _stands(world, entry) is False
        modal.locator("[data-done]").click()
        # it is listed where instructions are read, as a proposal
        page.get_by_role("button", name="Instructions").click()
        page.locator(f'[data-instructions="{conv}"]').get_by_text("Say what was verified").wait_for(timeout=MS)
        assert not errors, errors
        browser.close()


def test_an_instruction_started_with_no_conversation_asks_for_one(world, me_id):
    post(world, "/api/conversations", {"name": "Elsewhere"})
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world)
        modal = _new(page, "Conversation instruction")
        ed = modal.locator("[data-author='conversation-instruction']")
        ed.locator("textarea").first.fill("Keep answers short.")
        if ed.locator('.ba-need[data-part="conversation"]').count():
            sent = _sent(page)
            _record(modal)
            assert "Choose the conversation it is for." in ed.inner_text() and not sent
            ed.locator('.ba-need[data-part="conversation"]').click()
        else:  # opened inside a conversation: it can still be changed
            ed.locator('[data-part="conversation"]').click()
        ed.get_by_role("option").filter(has_text="Elsewhere").first.click()
        assert "Elsewhere" in ed.locator('[data-part="conversation"]').inner_text()
        assert not errors, errors
        browser.close()


def test_a_discipline_starts_small_and_its_advanced_parts_are_reachable(world, conv, me_id):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Discipline")
        ed = modal.locator("[data-author='discipline']")
        # two questions; none of the eight other parts is on screen
        assert ed.locator("input[type=text], textarea").count() == 2 and ed.locator("input[type=checkbox]").count() == 0
        ed.locator("input[type=text]").first.fill("Headless verification")
        ed.locator("textarea").first.fill("Drive the real page; never a mock.")
        modal.locator("[data-add]").click()
        offered = modal.locator("[data-add-part]").evaluate_all("els => els.map(e => e.dataset.addPart)")
        assert set(offered) >= {"about", "tools", "tool_use", "requires", "inputs", "outputs", "verification", "limits", "place"}
        modal.locator('[data-add-part="tools"]').click()
        page.keyboard.type("playwright")
        page.keyboard.press("Enter")
        page.keyboard.type("pytest")
        _add(modal, "requires")
        boxes = ed.locator('[data-part="requires"] input[type=checkbox]')
        boxes.first.wait_for(timeout=MS)
        cap = boxes.first.evaluate("el => el.parentElement.textContent")
        boxes.first.check()
        sent = _sent(page)
        _record(modal)
        entry = _done(modal)
        body = sent[0][1]
        assert body["establish"] is False
        assert body["body"]["tools"] == ["playwright", "pytest"] and body["body"]["requires"] == [cap]
        assert _stands(world, entry) is False
        assert not errors, errors
        browser.close()


def test_a_workflow_grows_one_activity_at_a_time(world, conv, me_id):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Workflow")
        ed = modal.locator("[data-author='workflow']")
        # a name and one activity; nothing else
        assert ed.locator("input[type=text], textarea").count() == 2
        ed.locator("input[type=text]").first.fill("Release to TEST")
        ed.locator("[data-act-open] textarea").fill("Build the release")
        for words in ("Verify it headlessly", "Ask the owner who deploys"):
            ed.locator("[data-act-add]").click()
            page.keyboard.type(words)
        assert ed.locator(".ba-act").count() == 3 and ed.locator("[data-act-open]").count() == 1
        # reorder with the keyboard and with the button; focus stays usable
        page.keyboard.press("Alt+ArrowUp")
        assert "Ask the owner" in ed.locator(".ba-act").nth(1).inner_text() + ed.locator(".ba-act").nth(1).locator("textarea").input_value()
        ed.locator('[data-act-move="down"]').click()
        assert ed.locator(".ba-act").nth(2).locator("textarea").input_value() == "Ask the owner who deploys"
        # remove, and take it back
        ed.locator("[data-act-remove]").click()
        assert ed.locator(".ba-act").count() == 2
        ed.get_by_role("button", name="Undo").click()
        assert ed.locator(".ba-act").count() == 3
        # details only when asked for; the rarely used settings one step further
        assert ed.locator("[data-act-who]").count() == 0
        ed.locator("[data-act-detail]").click()
        ed.locator("[data-act-who]").fill("the carrier")
        assert ed.get_by_label("activity default tier").count() == 0
        ed.locator("[data-act-more]").click()
        ed.get_by_label("activity default tier").select_option("frontier")
        ed.get_by_label("activity coordinates").check()
        # nothing reads as stages
        assert not re.search(r"\bstep\b|\bstage\b|→", ed.inner_text(), re.I)
        # an empty extra activity is named and opened
        ed.locator("[data-act-add]").click()
        sent = _sent(page)
        _record(modal)
        assert "Activity 4 is empty. Write it or remove it." in ed.inner_text() and not sent
        ed.locator("[data-act-remove]").click()
        _record(modal)
        entry = _done(modal)
        body = sent[0][1]
        acts = body["body"]["activities"]
        assert body["establish"] is False and [a["what"] for a in acts] == ["Build the release", "Verify it headlessly", "Ask the owner who deploys"]
        keys = [a["key"] for a in acts]
        assert len(set(keys)) == 3 and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,39}", k) for k in keys), keys
        last = acts[2]
        assert last["who"] == {"role": "the carrier"} and last["default_tier"] == "frontier" and last["coordinates"] is True
        assert _stands(world, entry) is False
        # the other workflow parts are all still reachable
        assert not errors, errors
        browser.close()


def test_a_workflow_is_not_offered_a_plain_placement_and_keeps_every_field(world, conv, me_id):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Workflow")
        modal.locator("[data-add]").click()
        offered = set(modal.locator("[data-add-part]").evaluate_all("els => els.map(e => e.dataset.addPart)"))
        assert offered == {"about", "projects", "text", "decisions", "done_when", "evidence", "interrupted", "carrier", "persona", "requires"}, offered
        assert not errors, errors
        browser.close()


# -- 4. unsaved work, keyboard, narrow -----------------------------------------

def test_typed_work_is_never_dropped_without_a_question(world, conv, me_id):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Rule")
        ed = modal.locator("[data-author='rule']")
        # nothing typed: Escape closes at once, and focus goes back where it came from
        page.keyboard.press("Escape")
        assert page.locator("[data-author-modal]").count() == 0
        assert page.get_by_role("dialog", name="Brain").is_visible()
        page.keyboard.press("Escape")  # the browser's own menu / card
        modal = _new(page, "Rule")
        ed = modal.locator("[data-author='rule']")
        page.keyboard.type("Half a rule")
        for n, leave in enumerate((lambda: page.keyboard.press("Escape"),
                                   lambda: ed.locator("[data-cancel]").click(),
                                   lambda: page.mouse.click(5, 5))):
            leave()
            assert "Discard what you wrote?" in ed.inner_text(), n
            assert ed.locator("[data-keep]").evaluate("el => el === document.activeElement"), (n, page.evaluate("document.activeElement.outerHTML.slice(0,120)"))
            page.keyboard.press("Escape")  # Escape on the question keeps the draft
            assert "Discard what you wrote?" not in ed.inner_text()
            assert ed.locator("textarea").input_value() == "Half a rule"
        # an optional part: Escape closes it first, and only then asks
        _add(modal, "about")
        page.keyboard.type("deploys")
        page.keyboard.press("Escape")
        assert "Discard what you wrote?" not in ed.inner_text()
        assert ed.locator('[data-sum="about"]').inner_text() == "deploys"
        # the + Add menu: Escape closes it and returns focus to it
        modal.locator("[data-add]").click()
        page.keyboard.press("Escape")
        assert modal.locator(".ba-menu").count() == 0 and modal.locator("[data-add]").evaluate("el => el === document.activeElement")
        # Tab stays inside the modal
        for _ in range(12):
            page.keyboard.press("Tab")
            assert page.evaluate("document.querySelector('.ba-modal').contains(document.activeElement)")
        # reload warns
        fired = page.evaluate("(() => { const e = new Event('beforeunload', {cancelable: true}); window.dispatchEvent(e); return e.defaultPrevented })()")
        assert fired is True
        ed.locator("[data-cancel]").click()
        ed.locator("[data-discard]").click()
        assert page.locator("[data-author-modal]").count() == 0
        assert not errors, errors
        browser.close()


def test_phone_width_is_a_sheet_with_no_sideways_scrolling(world, conv, me_id, note):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p, width=390, height=780)
        _open(page, world, conv)
        modal = _new(page, "Workflow")
        ed = modal.locator("[data-author='workflow']")
        box = modal.locator(".ba-modal").bounding_box()
        assert box["x"] <= 1 and box["width"] >= 388 and abs(box["y"] + box["height"] - 780) <= 2
        ed.locator("input[type=text]").first.fill("Release to TEST")
        ed.locator("[data-act-open] textarea").fill("Build the release")
        ed.locator("[data-act-detail]").click()
        ed.locator("[data-act-disc]").click()
        ed.locator("[data-finder]").wait_for(timeout=MS)
        assert _no_sideways(page)
        ed.locator("[data-finder-done]").click()
        modal.locator("[data-add]").click()
        assert _no_sideways(page)
        page.keyboard.press("Escape")
        rec = modal.locator("[data-record]")
        rec.scroll_into_view_if_needed()
        assert rec.is_visible()
        assert not errors, errors
        browser.close()


# -- 5. revising: the same editor ----------------------------------------------

def _open_record(page, world, entry):
    page.goto(world["base"] + f"/quiet2?record={entry}")
    page.locator(f'[data-record="{entry}"]').wait_for(timeout=MS)


def _revise(page, entry):
    rec = page.locator(f'[data-record="{entry}"]')
    rec.get_by_role("button", name="More on this record").click()
    page.get_by_role("menuitem", name=re.compile(r"^(Revise|Propose new version)")).click()
    ed = page.locator(f'[data-revise="{entry}"] [data-author]')
    ed.wait_for(timeout=MS)
    return ed


def test_revising_a_rule_in_effect_proposes_and_leaves_it_standing(world, conv, me_id):
    rule = post(world, "/api/entries", {"kind": "rule", "body": {"text": "Ask the owner who runs the deploy step.", "about": "deploys"},
                                        "attributed_to": me_id, "establish": True})["entry"]
    post(world, f"/api/entries/{rule}/place", {"attributed_to": me_id, "where": conv, "because": "asked here"})
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        _open_record(page, world, rule)
        ed = _revise(page, rule)
        # the same controls, filled with what it says now; what was set is on screen
        assert ed.locator("textarea").first.input_value() == "Ask the owner who runs the deploy step."
        assert ed.locator('[data-sum="about"]').inner_text() == "deploys"
        assert "The current one stays in effect" in ed.inner_text()
        assert ed.locator("textarea").first.evaluate("el => el === document.activeElement")
        sent = _sent(page)
        ed.locator("[data-record]").click()
        assert "Nothing has changed yet." in ed.inner_text() and not sent
        ed.locator("textarea").first.fill("Ask the owner who runs the deploy step, before building.")
        ed.locator("[data-diff]").click()
        assert ed.locator("[data-diff-shown] ins").inner_text().strip() == "step, before building."
        page.keyboard.press("Control+Enter")
        page.get_by_text("New version proposed").wait_for(timeout=MS)
        path, body = sent[0]
        assert path == f"/api/entries/{rule}/edit"
        assert body["body"] == {"text": "Ask the owner who runs the deploy step, before building."}  # only what changed
        got = get(world, f"/api/entries/{rule}")
        assert got["stands"] is True and got["body"]["text"] == "Ask the owner who runs the deploy step."
        assert [x["where"] for x in got["governance_actions"]["placements"]] == [conv]
        # establishing the proposal is its own, offered, separate act
        assert page.get_by_role("button", name="Establish proposal…").is_visible()
        assert not errors, errors
        browser.close()


def test_revising_a_placed_proposal_says_its_placement_carries_over(world, conv, me_id):
    rule = post(world, "/api/entries", {"kind": "rule", "body": {"text": "Say so first."}, "attributed_to": me_id, "establish": False})["entry"]
    post(world, f"/api/entries/{rule}/place", {"attributed_to": me_id, "where": conv, "because": "asked here"})
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        _open_record(page, world, rule)
        ed = _revise(page, rule)
        text = ed.inner_text()
        assert "Replaces this proposal" in text and "still a proposal" in text and "stays placed where this one is" in text
        assert not errors, errors
        browser.close()


def test_an_unsaved_revision_is_asked_about_and_escape_closes_inner_things_first(world, conv, me_id):
    rule = post(world, "/api/entries", {"kind": "rule", "body": {"text": "Say so first."}, "attributed_to": me_id, "establish": False})["entry"]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        _open_record(page, world, rule)
        ed = _revise(page, rule)
        ed.locator("[data-diff]").click()
        page.keyboard.press("Escape")  # closes what changes first
        assert ed.locator("[data-diff-shown]").count() == 0 and ed.count() == 1
        page.keyboard.press("Escape")  # nothing typed: the revision closes
        assert page.locator(f'[data-revise="{rule}"]').count() == 0
        ed = _revise(page, rule)
        ed.locator("textarea").first.fill("Say so first, in words.")
        page.keyboard.press("Escape")
        assert "Discard what you wrote?" in ed.inner_text()
        ed.locator("[data-keep]").click()
        # choosing another act asks the same question
        page.locator(f'[data-record="{rule}"]').get_by_role("button", name="More on this record").click()
        page.get_by_role("menuitem", name=re.compile("^Challenge")).click()
        q = page.get_by_role("alertdialog", name="Discard your changes?")
        q.wait_for(timeout=MS)
        q.get_by_role("button", name="Keep editing").click()
        assert ed.locator("textarea").first.input_value() == "Say so first, in words."
        # so does leaving the page
        page.locator("[data-brain-back]").click()
        page.locator(".q2-leave").wait_for(timeout=MS)
        page.locator(".q2-leave").get_by_role("button", name="Stay").click()
        assert ed.locator("textarea").first.input_value() == "Say so first, in words."
        assert not errors, errors
        browser.close()


def test_revising_a_workflow_keeps_its_activity_keys(world, conv, me_id):
    wf = post(world, "/api/entries", {"kind": "workflow", "attributed_to": me_id, "establish": False, "body": {
        "name": "Release to TEST", "about": "releases", "done_when": "TEST serves it",
        "activities": [{"key": "build", "what": "Build the release", "default_tier": "coding"},
                       {"key": "verify", "what": "Verify it", "who": {"role": "a reviewer"}}]}})["entry"]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        _open_record(page, world, wf)
        ed = _revise(page, wf)
        # the same sequence it was made in, and everything set before is on screen
        assert ed.locator(".ba-act").count() == 2 and ed.locator("[data-act-open]").count() == 1
        assert ed.locator('[data-sum="about"]').inner_text() == "releases"
        assert ed.locator('[data-sum="done_when"]').inner_text() == "TEST serves it"
        ed.locator("[data-act-open] textarea").fill("Build the release from a clean checkout")
        ed.locator("[data-act-add]").click()
        page.keyboard.type("Ask who deploys")
        sent = _sent(page)
        ed.locator("[data-record]").click()
        page.wait_for_function("() => !document.querySelector('[data-revise]')", timeout=MS)
        body = sent[0][1]["body"]
        assert list(body) == ["activities"]
        acts = body["activities"]
        assert [a["key"] for a in acts][:2] == ["build", "verify"] and acts[2]["key"] not in ("build", "verify", "")
        assert acts[0]["default_tier"] == "coding" and acts[1]["who"] == {"role": "a reviewer"}
        assert not errors, errors
        browser.close()


def test_revising_a_discipline_uses_rows_and_a_checklist(world, conv, me_id):
    caps = get(world, "/api/governance/authoring")["capabilities"]
    d = post(world, "/api/entries", {"kind": "discipline", "attributed_to": me_id, "establish": False, "body": {
        "name": "Headless verification", "text": "Drive the real page.", "tools": ["playwright", "pytest"], "requires": [caps[0]]}})["entry"]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        _open_record(page, world, d)
        ed = _revise(page, d)
        rows = ed.locator('[data-part="tools"] input')
        assert [rows.nth(i).input_value() for i in range(rows.count())] == ["playwright", "pytest"]
        assert ed.locator('[data-part="requires"] input:checked').count() == 1
        rows.nth(1).fill("pytest -q")
        sent = _sent(page)
        ed.locator("[data-record]").click()
        page.wait_for_function("() => !document.querySelector('[data-revise]')", timeout=MS)
        assert sent[0][1]["body"] == {"tools": ["playwright", "pytest -q"]}
        assert not errors, errors
        browser.close()


def test_revising_a_lesson_shows_its_evidence_and_can_change_it(world, conv, me_id, note):
    other = post(world, "/api/entries", {"kind": "note", "body": {"text": "It happened a second time on the TEST release."},
                                         "attributed_to": me_id, "establish": False})["entry"]
    lesson = post(world, "/api/entries", {"kind": "lesson", "body": {"text": "A hosted run cannot restart its host."},
                                          "attributed_to": me_id, "establish": False, "basis": [note]})["entry"]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        _open_record(page, world, lesson)
        ed = _revise(page, lesson)
        assert "The deploy call was refused" in ed.locator(".ba-chip").first.inner_text()
        ed.locator('button[data-part="basis"]').click()
        ed.locator("[data-finder] input").first.fill("second time")
        ed.get_by_role("option").filter(has_text="It happened a second time").first.click()
        ed.locator("[data-finder-done]").click()
        sent = _sent(page)
        # evidence added, wording unchanged: cited on the record as it is, with a reason
        ed.locator("[data-record]").click()
        assert "Say why this is being added." in ed.inner_text() and not sent
        page.keyboard.type("It happened again.")
        ed.locator("[data-record]").click()
        page.wait_for_function("() => !document.querySelector('[data-revise]')", timeout=MS)
        path, req = sent[0]
        assert path == f"/api/entries/{lesson}/derive-from" and req["from"] == [other] and req["because"] == "It happened again."
        # reworded: a new version, carrying the evidence it is given
        ed = _revise(page, lesson)
        ed.locator(".ba-chip").nth(1).wait_for(timeout=MS)
        ed.locator("textarea").first.fill("A hosted run can never restart its host.")
        ed.locator(".ba-chip .ba-x").first.click()
        ed.locator("[data-record]").click()
        page.wait_for_function("() => !document.querySelector('[data-revise]')", timeout=MS)
        path, req = sent[-1]
        assert path == f"/api/entries/{lesson}/edit" and len(req["basis"]) == 1 and req["body"] == {"text": "A hosted run can never restart its host."}
        assert not errors, errors
        browser.close()
