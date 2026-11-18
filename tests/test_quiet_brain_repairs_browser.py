"""THE MANAGE BRAIN FUNCTIONAL REPAIRS, in a real (headless) browser.

Quiet UI audit 2026-11-18 (release 20261118-638cf44), section 9 "Confirmed
functional defects". Each test replays the audit's own reproduction steps
against the real built Quiet Chat (`/quiet2`) and a real HTTP server over a
disposable fixture Brain -- the harness `test_quiet_governance_create_browser`
uses, with its helpers. No live Brain, no MARS, no visible window.

  - Defect 2 (with 1 and 5): a lesson is created from the interface, its
    basis carried by the create request; the page names the Kind being
    written; a refusal goes when its cause is corrected.
  - Defect 4: a saved revision lands on the new version with no question;
    an unsaved one is still asked about, and its Cancel asks once.
  - Defect 3: the record's menu says its acts are loading, and offers Retry
    where the read failed.
  - Defect 6: the conversation's Instructions popover does not drop a typed
    instruction on Escape or an outside press.

Build apps/fluid-web first (`npm ci && npm run build` under apps/fluid-web),
then opt in with MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import os
import re

import pytest

from tests._loop import world, post, get  # noqa: F401
from tests.test_quiet_governance_create_browser import (  # noqa: F401
    APPEARS_MS, _continue, _dialog, _field, _kind_select, _log_in_as_owner,
    _open_new, _open_quiet2, _page, _submit, basis_note, conv, me_id,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="build the UI (apps/fluid-web) and set MENTIS_QUIET_BROWSER=1",
)

LEAVE = ".q2-leave-veil"


def _gone(locator):
    """What React takes down is taken down after it draws, not as the press returns."""
    locator.wait_for(state="detached", timeout=APPEARS_MS)


def _open_record(page, world, entry):
    _log_in_as_owner(page, world)
    page.goto(world["base"] + "/quiet2?record=" + entry)
    page.locator(f'[data-record="{entry}"]').wait_for(timeout=APPEARS_MS)


def _menu(page):
    page.get_by_role("button", name="More on this record").click()
    menu = page.get_by_role("menu", name="More on this record")
    menu.wait_for(timeout=APPEARS_MS)
    return menu


def _proposed_rule(world, me_id, text="A rule the audit may revise."):
    return post(world, "/api/entries", {
        "kind": "rule", "body": {"text": text}, "attributed_to": me_id, "establish": False,
    })["entry"]


# -- Defects 2, 1, 5 -----------------------------------------------------------

def test_a_lesson_is_created_with_its_basis_and_the_page_names_its_kind(world, me_id, basis_note):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            sent = []
            page.on("request", lambda r: sent.append((r.method, r.url, r.post_data_json if r.method == "POST" else None)))
            _open_quiet2(page, world)
            _open_new(page, "Rule, decision or lesson")
            head = page.locator(".rv-author > .rv-kind")
            _kind_select(page).select_option("rule")
            assert head.inner_text().strip().lower() == "new · rule"          # Defect 1
            _kind_select(page).select_option("lesson")
            assert head.inner_text().strip().lower() == "new · lesson"

            # the field says it is required, and an empty one is refused here
            assert _dialog(page).get_by_text("references (required)").count() == 1
            assert _dialog(page).get_by_text("references (optional)").count() == 0
            _field(page, "text").fill("Unmeasured changes failed twice.")
            _continue(page)
            refusal = _dialog(page).locator(".r2-error")
            assert "Name at least one held reference" in refusal.inner_text()
            assert "step 1 of 3" in _dialog(page).inner_text().lower()
            assert not [s for s in sent if s[0] == "POST" and s[1].endswith("/api/entries")]

            # correcting what it complained about takes the refusal down (Defect 5)
            _field(page, "Supporting references").fill(basis_note)
            _gone(refusal)

            # the leave question names the Kind being written (Defect 1)
            page.locator("[data-brain-back]").click()
            assert "Leave this new lesson unfinished?" in page.locator(LEAVE).inner_text()
            page.locator(LEAVE).get_by_role("button", name="Stay").click()

            _continue(page)
            _continue(page)
            _submit(page)
            page.locator(".rv[data-record]").wait_for(timeout=APPEARS_MS)
            made = page.locator(".rv[data-record]").get_attribute("data-record")

            creates = [s[2] for s in sent if s[0] == "POST" and s[1].endswith("/api/entries")]
            assert len(creates) == 1, creates
            assert creates[0]["kind"] == "lesson" and creates[0]["basis"] == [basis_note], creates[0]
            assert creates[0]["establish"] is False
            assert not [s for s in sent if s[0] == "POST" and "/derive-from" in s[1]], "the basis must not be cited twice"

            got = get(world, "/api/entries/" + made)
            assert got["kind"] == "lesson" and got["stands"] is False
            cited = [x["link"]["to"] for x in world["cv"].corpus.links(frm=made)
                     if x["link"]["relation"] == "derived-from"]
            assert cited == [basis_note]
            assert not errors, errors
        finally:
            browser.close()


def test_a_refusal_about_reach_goes_when_the_reach_is_corrected(world, me_id):
    """Defect 5, the audit's own steps: place in a conversation, choose none,
    be refused, go back and choose "Only when named"."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            _open_quiet2(page, world)
            _open_new(page, "Rule, decision or lesson")
            _kind_select(page).select_option("rule")
            _field(page, "text").fill("Reach corrected.")
            _continue(page)
            _field(page, "Where it reaches").select_option("placed")
            _continue(page)
            _submit(page)
            refusal = _dialog(page).locator(".r2-error")
            assert "Choose a conversation." in refusal.inner_text()
            _dialog(page).get_by_role("button", name="Back", exact=True).click()
            _gone(refusal)      # moving between steps takes the refusal down
            _field(page, "Where it reaches").select_option("named")
            _continue(page)
            assert "Reaches only runs that name it." in _dialog(page).inner_text()
            assert refusal.count() == 0
            assert not errors, errors
        finally:
            browser.close()


# -- Defect 4, and Cancel on a hosted form --------------------------------------

def test_a_saved_revision_lands_on_the_new_version_without_a_question(world, me_id):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            first = _proposed_rule(world, me_id)
            _open_record(page, world, first)
            _menu(page).get_by_role("menuitem", name=re.compile(r"^Revise…")).click()
            box = page.get_by_label("New text", exact=True)
            box.fill("A rule the audit revised.")
            page.locator(".r2-inline-form .r2-primary").click()
            page.locator(f'.rv[data-record]:not([data-record="{first}"])').wait_for(timeout=APPEARS_MS)
            page.wait_for_timeout(2500)   # the audit saw the question ~1.5 s after the save
            assert page.locator(LEAVE).count() == 0, "a saved revision must not be asked about"
            second = page.locator(".rv[data-record]").get_attribute("data-record")
            assert second != first
            assert "A rule the audit revised." in page.locator(".rv-words").inner_text()
            assert get(world, "/api/entries/" + second)["body"]["text"] == "A rule the audit revised."

            # A GENUINELY UNSAVED REVISION IS STILL PROTECTED, exactly as before.
            _menu(page).get_by_role("menuitem", name=re.compile(r"^Revise…")).click()
            box = page.get_by_label("New text", exact=True)
            box.fill("Typed and not saved.")
            page.locator("[data-brain-back]").click()
            asked = page.locator(LEAVE)
            assert "Leave this revision unfinished?" in asked.inner_text()
            asked.get_by_role("button", name="Stay").click()
            assert box.input_value() == "Typed and not saved."

            # Its own Cancel asks once, and Keep editing keeps every word.
            page.locator(".r2-inline-form").get_by_role("button", name="Cancel").click()
            guard = page.locator(".r2-create-guard")
            assert "Discard this revision?" in guard.inner_text()
            guard.get_by_role("button", name="Keep editing").click()
            assert guard.count() == 0 and box.input_value() == "Typed and not saved."
            page.locator(".r2-inline-form").get_by_role("button", name="Cancel").click()
            page.locator(".r2-create-guard").get_by_role("button", name="Discard changes").click()
            assert page.locator(".r2-inline-form").count() == 0
            # discarded deliberately: nothing is asked again, and nothing waits unseen
            _menu(page).get_by_role("menuitem", name=re.compile(r"^Revise…")).click()
            assert page.get_by_label("New text", exact=True).input_value() == "A rule the audit revised."
            # nothing typed: Cancel closes at once
            page.locator(".r2-inline-form").get_by_role("button", name="Cancel").click()
            assert page.locator(".r2-create-guard").count() == 0 and page.locator(".r2-inline-form").count() == 0
            assert get(world, "/api/entries/" + second)["body"]["text"] == "A rule the audit revised."
            assert not errors, errors
        finally:
            browser.close()


def test_choosing_another_act_asks_before_dropping_what_was_typed(world, me_id):
    """Review of repair 4: another act chosen from the record's menu takes the
    open form's place. Where that form holds typed words it asks first, the
    question its own Cancel asks -- in both directions (a hosted form left for
    a Ladder act, a Ladder form left for a hosted act)."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            entry = _proposed_rule(world, me_id)
            _open_record(page, world, entry)
            revise = re.compile(r"^Revise…")
            challenge = re.compile(r"^Challenge…")
            guard = page.locator(".r2-create-guard")
            hosted = page.locator(".r2-inline-form")
            ladder = page.get_by_role("group", name="Challenge this record")

            # nothing typed: another act takes its place at once, as before
            _menu(page).get_by_role("menuitem", name=revise).click()
            hosted.wait_for(timeout=APPEARS_MS)
            _menu(page).get_by_role("menuitem", name=challenge).click()
            ladder.wait_for(timeout=APPEARS_MS)
            assert guard.count() == 0 and hosted.count() == 0
            _menu(page).get_by_role("menuitem", name=revise).click()
            hosted.wait_for(timeout=APPEARS_MS)
            assert guard.count() == 0 and ladder.count() == 0

            # typed in Revise, Challenge chosen: asked; Keep editing keeps it all
            box = page.get_by_label("New text", exact=True)
            box.fill("Typed and not saved.")
            _menu(page).get_by_role("menuitem", name=challenge).click()
            guard.wait_for(timeout=APPEARS_MS)
            assert "Discard this revision?" in guard.inner_text()
            assert ladder.count() == 0, "the other act must not open before the answer"
            guard.get_by_role("button", name="Keep editing").click()
            _gone(guard)
            assert box.input_value() == "Typed and not saved." and ladder.count() == 0
            # and it is still said to be unfinished to whatever would leave the page
            page.locator("[data-brain-back]").click()
            assert "Leave this revision unfinished?" in page.locator(LEAVE).inner_text()
            page.locator(LEAVE).get_by_role("button", name="Stay").click()
            assert box.input_value() == "Typed and not saved."

            # another hosted act asks the same
            _menu(page).get_by_role("menuitem", name=re.compile(r"^Delete…")).click()
            guard.wait_for(timeout=APPEARS_MS)
            guard.get_by_role("button", name="Keep editing").click()
            _gone(guard)
            assert box.input_value() == "Typed and not saved."

            # Discard: the words go, and the chosen act opens
            _menu(page).get_by_role("menuitem", name=challenge).click()
            guard.get_by_role("button", name="Discard changes").click()
            ladder.wait_for(timeout=APPEARS_MS)
            assert hosted.count() == 0 and guard.count() == 0

            # THE OTHER DIRECTION: a typed challenge, and a hosted act chosen
            why = ladder.get_by_label("What is wrong with it")
            why.fill("It contradicts the decision.")
            _menu(page).get_by_role("menuitem", name=revise).click()
            guard.wait_for(timeout=APPEARS_MS)
            assert "Discard this challenge?" in guard.inner_text() and hosted.count() == 0
            guard.get_by_role("button", name="Keep editing").click()
            _gone(guard)
            assert why.input_value() == "It contradicts the decision." and hosted.count() == 0
            _menu(page).get_by_role("menuitem", name=revise).click()
            guard.get_by_role("button", name="Discard changes").click()
            hosted.wait_for(timeout=APPEARS_MS)
            assert ladder.count() == 0
            # what was discarded from the revision earlier does not come back
            assert page.get_by_label("New text", exact=True).input_value() == "A rule the audit may revise."
            # nothing was recorded by any of it, and nothing is held now
            page.locator("[data-brain-back]").click()
            assert page.locator(LEAVE).count() == 0
            assert get(world, "/api/entries/" + entry)["body"]["text"] == "A rule the audit may revise."
            assert not get(world, "/api/governance/disputes?entry=" + entry)["disputes"]
            assert not errors, errors
        finally:
            browser.close()


# -- Defect 3 ------------------------------------------------------------------

def test_the_record_menu_says_its_acts_are_loading_and_offers_retry(world, me_id):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            entry = _proposed_rule(world, me_id)
            read = re.compile(r"/api/entries/" + entry + r"(\?.*)?$")
            held, mode = [], {"hold": True}
            page.route(read, lambda route: held.append(route) if mode["hold"] and route.request.method == "GET" else route.continue_())
            _open_record(page, world, entry)
            menu = _menu(page)
            loading = menu.get_by_role("menuitem", name="More actions are loading…")
            assert loading.count() == 1 and loading.is_disabled()
            assert menu.get_by_role("menuitem", name=re.compile(r"^Revise…")).count() == 0
            # the acts that need no second read are there throughout
            assert menu.get_by_role("menuitem", name=re.compile(r"^Challenge…")).count() == 1
            page.keyboard.press("Escape")

            # the read fails: the menu says so, with Retry
            mode["hold"] = False
            for route in held:
                route.abort()
            menu = _menu(page)
            retry = menu.get_by_role("menuitem", name=re.compile(r"^More actions could not be read\. Retry"))
            retry.wait_for(timeout=APPEARS_MS)
            assert menu.get_by_role("menuitem", name="More actions are loading…").count() == 0
            retry.click()

            # and once it answers, the acts themselves take the line's place
            menu = _menu(page)
            menu.get_by_role("menuitem", name=re.compile(r"^Revise…")).wait_for(timeout=APPEARS_MS)
            assert menu.get_by_role("menuitem", name=re.compile(r"^More actions")).count() == 0
            assert not errors, errors
        finally:
            browser.close()


# -- Defect 6 ------------------------------------------------------------------

def test_the_instructions_popover_keeps_a_typed_instruction(world, conv, me_id):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            _log_in_as_owner(page, world)
            page.goto(world["base"] + "/quiet2?c=" + conv)
            tools = page.get_by_role("toolbar", name="conversation tools")
            tools.wait_for(timeout=APPEARS_MS)
            opener = tools.get_by_role("button", name="Instructions")
            popover = page.locator(".q2-instructions")
            box = popover.locator("textarea")

            # nothing typed: Escape closes at once, as it always did
            opener.click()
            box.wait_for(timeout=APPEARS_MS)
            page.keyboard.press("Escape")
            assert popover.count() == 0 and page.locator(LEAVE).count() == 0

            opener.click()
            box.fill("Answer in one paragraph.")
            page.keyboard.press("Escape")
            asked = page.locator(LEAVE)
            assert "Leave this new instruction unfinished?" in asked.inner_text()
            asked.get_by_role("button", name="Stay").click()
            assert asked.count() == 0 and box.input_value() == "Answer in one paragraph."

            # an outside press asks too
            page.locator(".q2-conv, .q2-stream").first.click(position={"x": 5, "y": 5}, force=True)
            assert "Leave this new instruction unfinished?" in page.locator(LEAVE).inner_text()
            page.locator(LEAVE).get_by_role("button", name="Stay").click()
            assert box.input_value() == "Answer in one paragraph."

            # and so does the header's own button; discarding is explicit
            opener.click()
            page.locator(LEAVE).get_by_role("button", name="Discard changes and switch").click()
            assert popover.count() == 0
            opener.click()
            assert box.input_value() == ""

            # what the popover does is unchanged: it establishes at once
            sent = {}
            page.on("request", lambda r: sent.update(body=r.post_data_json) if r.method == "POST" and r.url.endswith("/instructions") else None)
            box.fill("Answer in one paragraph.")
            popover.get_by_role("button", name="Establish instruction").click()
            popover.get_by_text("Instruction established for this conversation.").wait_for(timeout=APPEARS_MS)
            assert sent["body"]["establish"] is True
            page.keyboard.press("Escape")       # recorded: nothing is held
            assert popover.count() == 0 and page.locator(LEAVE).count() == 0
            assert not errors, errors
        finally:
            browser.close()
