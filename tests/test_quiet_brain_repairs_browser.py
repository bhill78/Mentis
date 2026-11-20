"""THE MANAGE BRAIN FUNCTIONAL REPAIRS, in a real (headless) browser.

Quiet UI audit 2026-11-18 (release 20261118-638cf44), section 9 "Confirmed
functional defects". Each test replays the audit's own reproduction steps
against the real built Quiet Chat (`/quiet2`) and a real HTTP server over a
disposable fixture Brain. No live Brain, no MARS, no visible window.

SINCE THE BRAIN RECORD EDITOR (owner, 2026-11-18) the surfaces some of these
defects were found on are different ones: a record is made in the compact
modal and revised in the same editor on its page, and the conversation's
Instructions box no longer takes typing. Each repair is still checked, on the
surface that now carries it, with `test_quiet_brain_author_browser.py`'s
helpers ("author::" below is that file):

  - Defect 2 (a lesson is created from the interface with its basis in the
    create request): now author::test_a_lesson_needs_evidence_and_it_is_found_by_words,
    which replaced `test_a_lesson_is_created_with_its_basis_and_the_page_names_its_kind`
    here. Defect 1 (the page names the Kind being written): there is no Kind
    select to drift from the header any more; the modal is titled by the Kind
    it was opened for, and the leave question's wording is checked in
    `apps/fluid-web/tests/brain_repairs_unit.ts`.
  - Defect 5: a refusal goes when its cause is corrected -- in the editor
    (`test_a_refusal_goes_when_what_it_complained_about_is_corrected`, which
    replaced the step form's `..._about_reach_...`: the reach select and the
    steps are gone).
  - Defect 4: a saved revision lands on the new version with no question;
    an unsaved one is still asked about, and its Cancel asks once.
  - Review of repair 4: choosing another act asks before dropping typed
    words, between the revise editor, a Ladder form and the hosted forms
    (Place, Delete), which still come from `useRecordActs`.
  - Defect 3: the record's menu says its acts are loading, and offers Retry
    where the read failed.
  - Defect 6: an instruction being written is not dropped on Escape or an
    outside press. The box itself holds nothing typed now, so the check is
    on the modal it opens (it replaced
    `test_the_instructions_popover_keeps_a_typed_instruction`, whose last
    step asserted that the box established at once: removed by the approved
    design, see author::test_the_instructions_box_opens_the_same_editor_and_does_not_establish).

Build apps/fluid-web first (`npm ci && npm run build` under apps/fluid-web),
then opt in with MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import os
import re

import pytest

from tests._loop import world, post, get  # noqa: F401
from tests.test_quiet_brain_author_browser import (  # noqa: F401
    MS as APPEARS_MS, _add, _new, _open, _page as _author_page, _record, _revise, _sent, conv, me_id, note,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="build the UI (apps/fluid-web) and set MENTIS_QUIET_BROWSER=1",
)

LEAVE = ".q2-leave-veil"
REVISE = re.compile(r"^Revise…")
CHALLENGE = re.compile(r"^Challenge…")


def _page(playwright):
    return _author_page(playwright)


def _gone(locator):
    """What React takes down is taken down after it draws, not as the press returns."""
    locator.wait_for(state="detached", timeout=APPEARS_MS)


def _open_record(page, world, entry):
    _open(page, world)
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


# -- Defect 5 --------------------------------------------------------------------

def test_a_refusal_goes_when_what_it_complained_about_is_corrected(world, conv, me_id, note):
    """A refusal is about the draft as it was when Record was pressed: it is
    taken down as soon as the reader changes the draft, and nothing was sent."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            _open(page, world, conv)
            modal = _new(page, "Lesson")
            ed = modal.locator("[data-author='lesson']")
            alert = ed.get_by_role("alert")
            page.keyboard.type("Unmeasured changes failed twice.")
            sent = _sent(page)
            _record(modal)
            assert "has to be based on something already held" in alert.inner_text() and not sent
            # choosing what it is based on is the correction
            ed.locator(".ba-need").click()
            ed.get_by_role("option").filter(has_text="The deploy call was refused").first.click()
            _gone(alert)
            ed.locator("[data-finder-done]").click()
            assert alert.count() == 0 and not sent
            ed.locator("[data-cancel]").click()
            ed.locator("[data-discard]").click()
            page.keyboard.press("Escape")

            # a refusal about a placement goes as its reason is typed
            modal = _new(page, "Rule")
            ed = modal.locator("[data-author='rule']")
            alert = ed.get_by_role("alert")
            page.keyboard.type("Reach corrected.")
            _add(modal, "place")
            _record(modal)
            assert "Say why it belongs there." in alert.inner_text() and not sent
            ed.locator('[data-part="placeReason"]').fill("I")
            _gone(alert)
            assert not sent
            assert not errors, errors
        finally:
            browser.close()


# -- Defect 4, and Cancel on the revision ---------------------------------------

def test_a_saved_revision_lands_on_the_new_version_without_a_question(world, me_id):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            first = _proposed_rule(world, me_id)   # NOT standing: saving replaces the proposal
            _open_record(page, world, first)
            ed = _revise(page, first)
            sent = _sent(page)
            ed.locator("textarea").first.fill("A rule the audit revised.")
            ed.locator("[data-record]").click()
            page.locator(f'.rv[data-record]:not([data-record="{first}"])').wait_for(timeout=APPEARS_MS)
            page.wait_for_timeout(2500)   # the audit saw the question ~1.5 s after the save
            assert page.locator(LEAVE).count() == 0, "a saved revision must not be asked about"
            assert page.locator(".r2-create-guard").count() == 0 and page.locator("[data-revise]").count() == 0
            second = page.locator(".rv[data-record]").get_attribute("data-record")
            assert second != first
            assert sent[0][0] == f"/api/entries/{first}/edit" and len(sent) == 1
            assert "A rule the audit revised." in page.locator(".rv-words").inner_text()
            got = get(world, "/api/entries/" + second)
            assert got["body"]["text"] == "A rule the audit revised." and got["stands"] is False

            # A GENUINELY UNSAVED REVISION IS STILL PROTECTED, exactly as before.
            ed = _revise(page, second)
            box = ed.locator("textarea").first
            box.fill("Typed and not saved.")
            page.locator("[data-brain-back]").click()
            asked = page.locator(LEAVE)
            assert "Leave this revision unfinished?" in asked.inner_text()
            asked.get_by_role("button", name="Stay").click()
            assert box.input_value() == "Typed and not saved."

            # Its own Cancel asks once, and keeping keeps every word.
            ed.locator("[data-cancel]").click()
            assert "Discard what you wrote?" in ed.inner_text()
            ed.locator("[data-keep]").click()
            assert "Discard what you wrote?" not in ed.inner_text() and box.input_value() == "Typed and not saved."
            ed.locator("[data-cancel]").click()
            ed.locator("[data-discard]").click()
            assert page.locator("[data-revise]").count() == 0
            # discarded deliberately: nothing is asked again, and nothing waits unseen
            ed = _revise(page, second)
            assert ed.locator("textarea").first.input_value() == "A rule the audit revised."
            # nothing typed: Cancel closes at once
            ed.locator("[data-cancel]").click()
            assert page.locator("[data-revise]").count() == 0 and page.locator(LEAVE).count() == 0
            assert get(world, "/api/entries/" + second)["body"]["text"] == "A rule the audit revised."
            assert len(sent) == 1
            assert not errors, errors
        finally:
            browser.close()


def test_choosing_another_act_asks_before_dropping_what_was_typed(world, me_id):
    """Review of repair 4: another act chosen from the record's menu takes the
    open form's place. Where that form holds typed words it asks first, the
    one question -- from the revise editor to a Ladder act and to a hosted
    act, from a Ladder form to the revise editor, and between hosted forms."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            entry = _proposed_rule(world, me_id)
            _open_record(page, world, entry)
            guard = page.locator(".r2-create-guard")
            revising = page.locator(f'[data-revise="{entry}"]')
            hosted = page.locator(".r2-inline-form")
            ladder = page.get_by_role("group", name="Challenge this record")
            sent = _sent(page)

            # nothing typed: another act takes its place at once, as before
            _revise(page, entry)
            _menu(page).get_by_role("menuitem", name=CHALLENGE).click()
            ladder.wait_for(timeout=APPEARS_MS)
            assert guard.count() == 0 and revising.count() == 0
            ed = _revise(page, entry)
            assert guard.count() == 0 and ladder.count() == 0

            # typed in Revise, Challenge chosen: asked; Keep editing keeps it all
            box = ed.locator("textarea").first
            box.fill("Typed and not saved.")
            _menu(page).get_by_role("menuitem", name=CHALLENGE).click()
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

            # a hosted act (`useRecordActs`) chosen over it asks the same
            _menu(page).get_by_role("menuitem", name=re.compile(r"^Delete…")).click()
            guard.wait_for(timeout=APPEARS_MS)
            assert "Discard this revision?" in guard.inner_text() and hosted.count() == 0
            guard.get_by_role("button", name="Keep editing").click()
            _gone(guard)
            assert box.input_value() == "Typed and not saved."

            # Discard: the words go, and the chosen act opens
            _menu(page).get_by_role("menuitem", name=CHALLENGE).click()
            guard.get_by_role("button", name="Discard changes").click()
            ladder.wait_for(timeout=APPEARS_MS)
            assert revising.count() == 0 and guard.count() == 0

            # THE OTHER DIRECTION: a typed challenge, and Revise chosen
            why = ladder.get_by_label("What is wrong with it")
            why.fill("It contradicts the decision.")
            _menu(page).get_by_role("menuitem", name=REVISE).click()
            guard.wait_for(timeout=APPEARS_MS)
            assert "Discard this challenge?" in guard.inner_text() and revising.count() == 0
            guard.get_by_role("button", name="Keep editing").click()
            _gone(guard)
            assert why.input_value() == "It contradicts the decision." and revising.count() == 0
            _menu(page).get_by_role("menuitem", name=REVISE).click()
            guard.get_by_role("button", name="Discard changes").click()
            ed = page.locator(f'[data-revise="{entry}"] [data-author]')
            ed.wait_for(timeout=APPEARS_MS)
            assert ladder.count() == 0
            # what was discarded from the revision earlier does not come back
            assert ed.locator("textarea").first.input_value() == "A rule the audit may revise."

            # BETWEEN HOSTED FORMS, which are still `useRecordActs`' own: an
            # untouched revision gives way at once; a typed placement asks
            _menu(page).get_by_role("menuitem", name=re.compile(r"^Place…")).click()
            hosted.wait_for(timeout=APPEARS_MS)
            assert guard.count() == 0 and revising.count() == 0
            reason = hosted.get_by_label("Record reason", exact=True)
            reason.fill("It belongs here.")
            _menu(page).get_by_role("menuitem", name=re.compile(r"^Delete…")).click()
            guard.wait_for(timeout=APPEARS_MS)
            assert "Discard this placement?" in guard.inner_text()
            guard.get_by_role("button", name="Keep editing").click()
            _gone(guard)
            assert reason.input_value() == "It belongs here." and "Place this record" in hosted.inner_text()
            # a typed hosted form left for the revise editor asks too
            _menu(page).get_by_role("menuitem", name=REVISE).click()
            guard.wait_for(timeout=APPEARS_MS)
            assert "Discard this placement?" in guard.inner_text() and revising.count() == 0
            guard.get_by_role("button", name="Discard changes").click()
            ed.wait_for(timeout=APPEARS_MS)
            assert hosted.count() == 0 and guard.count() == 0

            # nothing was recorded by any of it, and nothing is held now
            page.locator("[data-brain-back]").click()
            assert page.locator(LEAVE).count() == 0
            assert not sent, sent
            got = get(world, "/api/entries/" + entry)
            assert got["body"]["text"] == "A rule the audit may revise."
            assert not got["governance_actions"]["placements"]
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
            assert menu.get_by_role("menuitem", name=REVISE).count() == 0
            # the acts that need no second read are there throughout
            assert menu.get_by_role("menuitem", name=CHALLENGE).count() == 1
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
            menu.get_by_role("menuitem", name=REVISE).wait_for(timeout=APPEARS_MS)
            assert menu.get_by_role("menuitem", name=re.compile(r"^More actions")).count() == 0
            assert not errors, errors
        finally:
            browser.close()


# -- Defect 6 ------------------------------------------------------------------

def test_an_instruction_being_written_from_the_box_is_asked_about_before_it_is_dropped(world, conv, me_id):
    """The conversation's Instructions box holds nothing typed any more, so it
    closes at once. The instruction is written in the modal the box opens,
    and THAT does not drop a half-written one on Escape, on an outside press
    or on Cancel; discarding is explicit, and nothing is recorded by any of it."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p)
        try:
            _open(page, world, conv)
            tools = page.get_by_role("toolbar", name="conversation tools")
            tools.wait_for(timeout=APPEARS_MS)
            opener = tools.get_by_role("button", name="Instructions")
            box = page.locator(f'[data-instructions="{conv}"]')
            modal = page.locator("[data-author-modal]")
            ed = modal.locator("[data-author='conversation-instruction']")
            sent = _sent(page)
            held_before = len(world["cv"].corpus.entries_of_kind("conversation-instruction"))

            # the box: nothing in it to lose, so Escape closes it at once
            opener.click()
            box.wait_for(timeout=APPEARS_MS)
            assert box.locator("textarea, input").count() == 0
            page.keyboard.press("Escape")
            _gone(box)
            assert page.locator(LEAVE).count() == 0 and modal.count() == 0

            # the editor it opens, untouched: Escape closes that at once too
            opener.click()
            box.locator("[data-new-instruction]").click()
            ed.wait_for(timeout=APPEARS_MS)
            page.keyboard.press("Escape")
            _gone(modal)
            assert page.locator(LEAVE).count() == 0

            # half-written: Escape asks, and keeping keeps every word
            if box.count() == 0:
                opener.click()
            box.locator("[data-new-instruction]").click()
            ed.wait_for(timeout=APPEARS_MS)
            words = ed.locator("textarea").first
            words.fill("Answer in one paragraph.")
            page.keyboard.press("Escape")
            assert "Discard what you wrote?" in ed.inner_text()
            ed.locator("[data-keep]").click()
            assert "Discard what you wrote?" not in ed.inner_text() and words.input_value() == "Answer in one paragraph."

            # an outside press asks too
            page.mouse.click(5, 5)
            assert "Discard what you wrote?" in ed.inner_text() and modal.count() == 1
            page.keyboard.press("Escape")   # Escape on the question keeps the draft
            assert words.input_value() == "Answer in one paragraph."

            # and so does its own Cancel; discarding is explicit
            ed.locator("[data-cancel]").click()
            assert "Discard what you wrote?" in ed.inner_text()
            ed.locator("[data-discard]").click()
            _gone(modal)
            assert page.locator(LEAVE).count() == 0
            if box.count() == 0:
                opener.click()
            box.locator("[data-new-instruction]").click()
            ed.wait_for(timeout=APPEARS_MS)
            assert ed.locator("textarea").first.input_value() == ""

            # nothing was written to the Brain by any of it
            assert not sent, sent
            assert len(world["cv"].corpus.entries_of_kind("conversation-instruction")) == held_before
            assert not errors, errors
        finally:
            browser.close()
