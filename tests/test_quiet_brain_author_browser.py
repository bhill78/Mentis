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
from tests.conftest import owner_headers

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
    # THE BROWSER IS THE OWNER THROUGH THE SUITE'S ONE SESSION, not a login of
    # its own. A credential keeps 64 sessions and drops the oldest; a login per
    # browser test pushed the suite's own session out part-way through a full
    # run, and every later owner operation in every later file answered 401.
    page.context.set_extra_http_headers(owner_headers())
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
        # a reference somebody already has can still be given, and reads as words.
        # (2026-11-20, B2: it is an advanced option now, looked up and SHOWN
        # before it is added, so it takes a second Enter: one to look it up,
        # one to add what was shown. It was one Enter that added unseen.)
        ed.locator(".ba-need").click()
        ed.get_by_role("button", name="Advanced: paste a link or id").click()
        page.keyboard.type(note)
        page.keyboard.press("Enter")
        ed.locator("[data-paste-found]").wait_for(timeout=MS)
        assert "The deploy call was refused" in ed.locator("[data-paste-found]").inner_text()
        assert ed.locator(".ba-chip").count() == 0 and ed.get_by_text("1 chosen").count() == 0
        page.wait_for_function("() => document.activeElement?.hasAttribute('data-paste-add')")
        page.keyboard.press("Enter")
        ed.get_by_text("1 chosen").wait_for(timeout=MS)
        ed.locator("[data-finder-done]").click()
        ed.locator(".ba-chip").wait_for(timeout=MS)
        assert "The deploy call was refused" in ed.locator(".ba-chip").inner_text()
        assert not errors, errors
        browser.close()


def _basis_finder(page, modal, kind):
    ed = modal.locator(f"[data-author='{kind}']")
    if ed.locator(".ba-need").count():
        ed.locator(".ba-need").click()
    else:
        _add(modal, "basis")
    ed.locator("[data-finder]").wait_for(timeout=MS)
    return ed


def test_what_a_rule_is_based_on_is_chosen_by_title_and_recorded_by_the_same_id(world, conv, me_id, note):
    """B2 (owner, 2026-11-20). Choosing what a rule is based on never asks for
    an id: the finder lists records by their words, with their Kind and who
    recorded them, and what is recorded is the same reference as ever."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        sent = _sent(page)
        modal = _new(page, "Rule")
        ed = _basis_finder(page, modal, "rule")
        # no field asks for a reference: the only box is a search by words
        assert ed.locator("[data-finder] input").count() == 1
        assert "by any words" in ed.locator("[data-finder] input").get_attribute("placeholder")
        row = ed.get_by_role("option").filter(has_text="The deploy call was refused").first
        row.wait_for(timeout=MS)
        words = row.inner_text()
        assert "Note" in words and "recorded by @brian" in words
        assert not re.search(r"\b(ent|adm)-[0-9a-f]{6}", ed.locator("[data-finder]").inner_text())
        # the way to paste is there, and says what it is
        assert ed.get_by_role("button", name="Advanced: paste a link or id").count() == 1
        row.click()
        ed.locator("[data-finder-done]").click()
        chip = ed.locator(".ba-chip")
        assert "The deploy call was refused" in chip.inner_text() and note not in chip.inner_text()
        # the id is there for whoever wants it, as secondary detail
        assert note in chip.locator(".ba-chip-t").get_attribute("title")
        ed.locator("textarea").first.fill("Deploys go through the release path.")
        ed.locator("[data-part='basisReason'] textarea").fill("It is what the refusal shows.")
        _record(modal)
        made = _done(modal)
        cites = [b for path, b in sent if path == f"/api/entries/{made}/derive-from"]
        assert cites == [{"attributed_to": me_id, "from": [note], "because": "It is what the refusal shows."}]
        assert [b["ref"] for b in get(world, f"/api/ladder/items/{made}")["basis"]] == [note]
        assert not errors, errors
        browser.close()


def test_a_pasted_id_or_link_is_looked_up_and_shown_before_it_is_added(world, conv, me_id, note):
    """B2: pasting is the advanced option. A valid id or link says what it
    resolves to first; a name, an unknown id or a missing file is refused in
    plain words and adds nothing; what is recorded is the exact reference."""
    from playwright.sync_api import sync_playwright
    turn = post(world, f"/api/conversations/{conv}/turns", {"author": me_id, "text": "Is TEST ready for the release?"})["turn"]
    number = get(world, f"/api/ladder/resolve?ref={turn}")["where"]["number"]
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        sent = _sent(page)
        modal = _new(page, "Lesson")
        ed = _basis_finder(page, modal, "lesson")
        ed.locator("[data-paste-open]").click()
        box = ed.locator("[data-paste] input")
        # it says what it accepts, and that it is the advanced way
        said = ed.locator("[data-paste]").inner_text()
        assert "Paste a link or an id" in said and "ADVANCED" in said.upper()
        assert "A link copied from a record or a post" in said and "shown to you before it is added" in said
        assert box.evaluate("el => el === document.activeElement")

        def refused(text):
            box.fill(text)
            box.press("Enter")
            ed.locator("[data-paste-refused]").wait_for(timeout=MS)
            why = ed.locator("[data-paste-refused]").inner_text()
            assert ed.locator("[data-paste-found]").count() == 0
            assert ed.get_by_text("1 chosen").count() == 0 and ed.locator("[data-paste-add]").count() == 0
            return why

        # a name is not a reference: said plainly, with what to do instead
        assert refused("the deploy note") == ("That is not a link or an id from Mentis. Paste a link copied from a record "
                                              "or a post, or search by words above.")
        # an id that names nothing, and a file that is not there
        assert refused("ent-000000000000") == "Nothing in this Brain has that link or id. Nothing was added."
        assert refused("adm-000000000000") == "Nothing in this Brain has that link or id. Nothing was added."
        assert refused(world["base"] + f"/quiet2?c={conv}&at=999") == "Nothing in this Brain has that link or id. Nothing was added."

        # a valid id: shown first (title, kind, who recorded it), added second
        box.fill(note)
        ed.locator("[data-paste-look]").click()
        found = ed.locator("[data-paste-found]")
        found.wait_for(timeout=MS)
        words = found.inner_text()
        assert "This is:" in words and "The deploy call was refused" in words
        assert "Note" in words and "recorded by @brian" in words and note not in words
        assert ed.locator("[data-paste-refused]").count() == 0
        assert ed.get_by_text("1 chosen").count() == 0          # not added yet
        if os.environ.get("MENTIS_OVERVIEW_SHOTS"):
            page.screenshot(path=os.path.join(os.environ["MENTIS_OVERVIEW_SHOTS"], "paste-desktop.png"))
        # changing what was pasted takes back what was shown for it
        box.press("End")
        box.type("x")
        assert ed.locator("[data-paste-found]").count() == 0
        box.fill(note)
        box.press("Enter")
        found.wait_for(timeout=MS)
        page.wait_for_function("() => document.activeElement?.hasAttribute('data-paste-add')")
        page.keyboard.press("Enter")
        ed.get_by_text("1 chosen").wait_for(timeout=MS)
        assert ed.locator("[data-paste]").count() == 0

        # a post, by the link its own "Copy link" gives: resolved to the post
        ed.locator("[data-paste-open]").click()
        box.fill(world["base"] + f"/quiet2?c={conv}&at={number}")
        box.press("Enter")
        found.wait_for(timeout=MS)
        words = found.inner_text()
        assert "Is TEST ready for the release?" in words and "Post" in words and f"#{number} in Release check" in words
        ed.locator("[data-paste-add]").click()
        ed.get_by_text("2 chosen").wait_for(timeout=MS)
        # pasting the first one again does not add it twice
        ed.locator("[data-paste-open]").click()
        box.fill(world["base"] + f"/quiet2?record={note}")
        box.press("Enter")
        found.wait_for(timeout=MS)
        assert "Already chosen:" in found.inner_text()
        ed.locator("[data-paste-add]").click()
        assert ed.get_by_text("2 chosen").count() == 1

        ed.locator("[data-finder-done]").click()
        chips = ed.locator(".ba-chip")
        assert chips.count() == 2
        assert not re.search(r"\b(ent|adm)-[0-9a-f]{6}", " ".join(chips.all_inner_texts()))
        ed.locator("textarea").first.fill("A hosted run cannot restart its host.")
        _record(modal)
        made = _done(modal)
        create = next(b for path, b in sent if path == "/api/entries")
        assert create["basis"] == [note, turn]                 # exactly the ids, as before
        assert sorted(b["ref"] for b in get(world, f"/api/ladder/items/{made}")["basis"]) == sorted([note, turn])
        assert not errors, errors
        browser.close()


def test_the_paste_option_fits_a_phone_and_only_evidence_offers_it(world, conv, me_id, note):
    """B2: 390 px, and where the option is: the three Kinds that can rest on
    evidence (rule, decision, lesson). The other four have no reference to
    enter at all, by id or otherwise."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p, width=390, height=844)
        _open(page, world, conv)
        modal = _new(page, "Decision")
        ed = _basis_finder(page, modal, "decision")
        ed.locator("[data-paste-open]").click()
        box = ed.locator("[data-paste] input")
        box.fill(note)
        box.press("Enter")
        ed.locator("[data-paste-found]").wait_for(timeout=MS)
        assert _no_sideways(page)
        assert ed.locator("[data-paste]").evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        add = ed.locator("[data-paste-add]").bounding_box()
        assert add["x"] >= 0 and add["x"] + add["width"] <= 391
        shots = os.environ.get("MENTIS_OVERVIEW_SHOTS")
        if shots:
            page.screenshot(path=os.path.join(shots, "paste-phone.png"))
        # the question a decision settles is chosen by words only
        page.keyboard.press("Escape")
        _add(modal, "context")
        ed.locator("[data-finder]").wait_for(timeout=MS)
        assert ed.locator("[data-paste-open]").count() == 0
        assert not errors, errors
        browser.close()
    kinds = {k["kind"]: k for k in get(world, "/api/governance/authoring")["kinds"] if k.get("authoring")}
    assert {n for n, k in kinds.items() if k["authoring"]["basis"] or k.get("requires_basis")} == {"rule", "decision", "lesson"}
    assert not any((f or {}).get("input") == "refs" for k in kinds.values() for f in (k.get("form") or {}).values())


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


def test_a_record_made_although_its_placement_failed_opens_without_a_question(world, conv, me_id):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Rule")
        ed = modal.locator("[data-author='rule']")
        page.keyboard.type("Say so before building.")
        _add(modal, "place")
        ed.locator('[data-part="placeReason"]').fill("It was asked here.")
        page.route("**/api/entries/*/place", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"error": "refused for the test"})))
        sent = _sent(page)
        _record(modal)
        ed.get_by_text("was not").wait_for(timeout=MS)
        # closing now would leave the placement undone: it asks, and says the record stays
        page.keyboard.press("Escape")
        assert "the rest did not complete. Close anyway?" in ed.inner_text()
        ed.locator("[data-keep]").click()
        assert page.locator("[data-author-modal]").count() == 1
        modal.locator("[data-open-made]").click()
        # straight to the record that was made: no question about a draft that is recorded
        page.locator("[data-record]").wait_for(timeout=MS)
        assert page.locator(".q2-leave").count() == 0 and page.locator("[data-author-modal]").count() == 0
        entry = page.locator("[data-record]").get_attribute("data-record")
        assert _stands(world, entry) is False
        assert [s[0] for s in sent].count("/api/entries") == 1
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


# -- 6. carried over from the creation page this editor replaced -----------------
#
# What `test_quiet_governance_create_browser.py` checked on the Quiet-hosted
# `R2Create` and that the new editor still has to do (that file's docstring
# maps each of its old tests to the one here).

@pytest.fixture
def world_no_owner(tmp_path):
    """A real fixture Brain with no Participant at all, so `MeProvider`
    (`identity.tsx`) resolves `me` to null exactly as it would for an
    unadopted or freshly created Brain: the same server `world` uses, without
    `fixture.build`'s demo participants."""
    import threading
    from http.server import ThreadingHTTPServer

    import mentis.api as mapi
    from mentis.web import _Handler, _State
    root = tmp_path / "corpus_no_owner"
    mapi.create_corpus(str(root))
    state = _State(str(root))
    handler = type("H", (_Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield {"base": f"http://127.0.0.1:{httpd.server_address[1]}", "state": state}
    finally:
        httpd.shutdown()


def _creates(sent):
    return [s for s in sent if s[0] in ("/api/entries", "/api/personas") or s[0].endswith("/instructions")]


def test_what_is_recorded_is_attributed_to_the_resolved_participant(world, conv, me_id):
    """Read from the request itself, through two doors: who wrote it is the
    participant the page resolved, and the fields are the ones typed."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Discipline")
        ed = modal.locator("[data-author='discipline']")
        ed.locator("input[type=text]").first.fill("Attribution case")
        ed.locator("textarea").first.fill("Say who wrote it.")
        _add(modal, "about")
        page.keyboard.type("attribution")
        sent = _sent(page)
        _record(modal)
        entry = _done(modal)
        path, body = sent[0]
        assert path == "/api/entries" and body["kind"] == "discipline"
        assert body["attributed_to"] == me_id
        assert (body["body"]["name"], body["body"]["about"], body["body"]["text"]) == ("Attribution case", "attribution", "Say who wrote it.")
        assert get(world, f"/api/entries/{entry}")["body"]["name"] == "Attribution case"
        modal.locator("[data-done]").click()
        page.keyboard.press("Escape")
        modal = _new(page, "Persona")
        page.keyboard.type("Attributed persona")
        modal.locator("[data-author='persona']").locator("input[type=text], textarea").nth(1).fill("Answers briefly.")
        _record(modal)
        _done(modal)
        path, body = sent[-1]
        assert path == "/api/personas" and body["attributed_to"] == me_id
        assert not errors, errors
        browser.close()


def test_no_participant_blocks_the_write_before_any_post(world_no_owner):
    """A Brain with no Participant: nothing can be attributed, so Record is
    not available and nothing reaches the network, whichever way it is asked."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world_no_owner)
        modal = _new(page, "Discipline")
        ed = modal.locator("[data-author='discipline']")
        sent = _sent(page)
        ed.locator("input[type=text]").first.fill("No owner case")
        ed.locator("textarea").first.fill("Should not record.")
        assert modal.locator("[data-record]").is_disabled(), "no attributed owner must disable Record"
        page.keyboard.press("Control+Enter")  # the keyboard's way to Record is refused in words
        ed.get_by_text("An attributed owner is needed to record this.").wait_for(timeout=MS)
        page.wait_for_timeout(500)  # nothing fires on its own either
        assert not _creates(sent), sent
        assert modal.locator("[data-author-done]").count() == 0
        assert not errors, errors
        browser.close()


def test_a_failed_citation_is_retried_on_the_same_record_and_nothing_is_made_twice(world, conv, me_id, note):
    """The record is made, citing what it is based on fails once: it says what
    was and was not recorded, the draft is no longer for editing, no discard
    is offered for a record that exists, and trying again cites the SAME
    record -- one create, ever."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        fails = {"n": 1}

        def once(route):
            if fails["n"]:
                fails["n"] -= 1
                route.abort()
            else:
                route.continue_()
        page.route("**/api/entries/*/derive-from", once)
        _open(page, world, conv)
        modal = _new(page, "Rule")
        ed = modal.locator("[data-author='rule']")
        page.keyboard.type("Retry case.")
        _add(modal, "basis")
        ed.get_by_role("option").filter(has_text="The deploy call was refused").first.click()
        ed.locator("[data-finder-done]").click()
        ed.locator('[data-part="basisReason"] textarea').fill("It supports this.")
        sent = _sent(page)
        _record(modal)
        ed.get_by_text("It was recorded as a proposal, but what it is based on was not").wait_for(timeout=MS)
        assert [s[0].split("/")[-1] for s in sent] == ["entries", "derive-from"]
        assert sent[0][1]["establish"] is False
        first = sent[1][0].split("/")[3]
        assert re.fullmatch(r"ent-[0-9a-f]+", first), sent[1][0]
        # the record exists, as a proposal, with nothing cited yet
        assert _stands(world, first) is False
        assert not [x for x in world["cv"].corpus.links(frm=first) if x["link"]["relation"] == "derived-from"]
        # truthful about what remains; no discard for what is already in the Brain
        assert "The rest did not complete." in ed.inner_text()
        assert modal.locator("[data-record]").inner_text() == "Try the rest again"
        assert modal.locator("[data-cancel]").inner_text() == "Close" and modal.locator("[data-discard]").count() == 0
        assert ed.locator("textarea").first.evaluate("el => !!el.closest('[inert]')")
        assert ed.locator(".ba-chip .ba-x").first.evaluate("el => !!el.closest('[inert]')")
        _record(modal)
        entry = _done(modal)
        assert entry == first, "a retry must keep the identity the first attempt made"
        paths = [s[0] for s in sent]
        assert paths.count("/api/entries") == 1, "a retry must never create a second record"
        assert paths == ["/api/entries", f"/api/entries/{first}/derive-from", f"/api/entries/{first}/derive-from"]
        assert sent[2][1] == sent[1][1] and sent[2][1]["from"] == [note] and sent[2][1]["because"] == "It supports this."
        cited = [x["link"]["to"] for x in world["cv"].corpus.links(frm=first) if x["link"]["relation"] == "derived-from"]
        assert cited == [note]
        assert _stands(world, first) is False
        assert not errors, errors
        browser.close()


def test_while_recording_nothing_else_can_be_started(world, conv, me_id):
    """Busy: the ways out are not available, Escape and an outside press do
    nothing, and asking to record again sends nothing a second time."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        held = []
        page.route("**/api/entries", lambda route: held.append(route) if route.request.method == "POST" else route.continue_())
        _open(page, world, conv)
        modal = _new(page, "Rule")
        ed = modal.locator("[data-author='rule']")
        page.keyboard.type("While recording.")
        sent = _sent(page)
        _record(modal)
        for _ in range(50):
            if held:
                break
            page.wait_for_timeout(100)
        assert len(held) == 1
        assert modal.locator("[data-record]").inner_text() == "Recording…"
        assert modal.locator("[data-record]").is_disabled() and modal.locator("[data-cancel]").is_disabled()
        page.keyboard.press("Escape")
        page.mouse.click(5, 5)
        assert page.locator("[data-author-modal] [data-author]").count() == 1
        assert "Discard what you wrote?" not in ed.inner_text()
        ed.locator("textarea").first.focus()
        page.keyboard.press("Control+Enter")
        page.wait_for_timeout(700)
        assert len(held) == 1 and len(_creates(sent)) == 1, "busy must block a second submission"
        held[0].continue_()
        entry = _done(modal)
        assert len(_creates(sent)) == 1 and _stands(world, entry) is False
        assert len([e for e in world["cv"].corpus.entries_of_kind("rule")
                    if e["body"].get("text") == "While recording."]) == 1
        assert not errors, errors
        browser.close()


def test_the_discard_question_is_decided_once_from_the_keyboard(world, conv, me_id):
    """Escape with the primary action focused asks; Enter and Space on the
    focused "Keep writing" keep the draft (never a background Record, never a
    silent reset); Tab decides nothing; every value survives each time."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)
        modal = _new(page, "Rule")
        ed = modal.locator("[data-author='rule']")
        page.keyboard.type("Kept through keyboard leave.")
        _add(modal, "about")
        page.keyboard.type("keyboard-leave")
        page.keyboard.press("Escape")  # folds the part to its line
        _add(modal, "place")
        ed.locator('[data-part="placeReason"]').fill("It was asked here.")
        sent = _sent(page)

        def kept():
            assert "Discard what you wrote?" not in ed.inner_text()
            assert ed.locator("textarea").first.input_value() == "Kept through keyboard leave."
            assert ed.locator('[data-sum="about"]').inner_text() == "keyboard-leave"
            assert ed.locator('[data-part="placeReason"]').input_value() == "It was asked here."
            assert "Release check" in ed.locator('[data-part="place"]').inner_text()
            assert not sent, "keeping the draft must never send anything"

        for key in ("Enter", "Space"):
            modal.locator("[data-record]").focus()
            page.keyboard.press("Escape")
            assert "Discard what you wrote?" in ed.inner_text()
            assert ed.locator("[data-keep]").evaluate("el => el === document.activeElement")
            # the draft is not for editing while the question is up
            assert ed.locator("textarea").first.evaluate("el => !!el.closest('[inert]')")
            page.keyboard.press(key)
            kept()
        modal.locator("[data-record]").focus()
        page.keyboard.press("Escape")
        page.keyboard.press("Tab")
        assert "Discard what you wrote?" in ed.inner_text(), "Tab must not have decided anything"
        assert page.evaluate("document.querySelector('.ba-modal').contains(document.activeElement)")
        page.keyboard.press("Escape")  # Escape on the question keeps the draft
        kept()
        assert page.locator("[data-author-modal]").count() == 1
        assert not errors, errors
        browser.close()


def test_every_kind_and_structure_nobody_wrote_in_yet_is_a_draft_to_protect(world, conv, me_id):
    """The protection the creation page had: each Kind asks before dropping
    what was typed, and an activity or a list row that was added and not yet
    written is still something the reader made."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page, errors = _page(p)
        _open(page, world, conv)

        def asked_and_kept(ed):
            assert "Discard what you wrote?" in ed.inner_text()
            ed.locator("[data-keep]").click()
            assert "Discard what you wrote?" not in ed.inner_text()

        def discard(ed):
            ed.locator("[data-cancel]").click()
            ed.locator("[data-discard]").click()
            assert page.locator("[data-author-modal]").count() == 0
            page.keyboard.press("Escape")  # the browser's own menu / card

        for label in SEVEN:
            modal = _new(page, label)
            ed = modal.locator("[data-author]")
            first = ed.locator("input[type=text], textarea").first
            first.fill(f"Half-written {label}")
            page.keyboard.press("Escape")
            asked_and_kept(ed)
            assert first.input_value() == f"Half-written {label}", label
            discard(ed)

        # AN EMPTY ADDED ACTIVITY IS A DRAFT: nothing typed, still the reader's
        modal = _new(page, "Workflow")
        ed = modal.locator("[data-author='workflow']")
        ed.locator("[data-act-add]").click()
        assert ed.locator(".ba-act").count() == 2
        ed.locator("[data-cancel]").click()
        asked_and_kept(ed)
        assert ed.locator(".ba-act").count() == 2
        # a part-written activity, with its own participant, survives it too
        ed.locator("[data-act-open] textarea").fill("Part-written, not finished")
        ed.locator("[data-act-detail]").click()
        ed.locator("[data-act-more]").click()
        who = ed.get_by_label("activity participant")
        who.select_option(index=1)
        chosen = who.input_value()
        assert chosen
        ed.locator('[data-act-move="up"]').click()  # moved, it keeps everything
        assert ed.locator(".ba-act").first.locator("textarea").input_value() == "Part-written, not finished"
        ed.locator("[data-cancel]").click()
        asked_and_kept(ed)
        assert ed.locator("[data-act-open] textarea").input_value() == "Part-written, not finished"
        if ed.get_by_label("activity participant").count() == 0:
            if ed.locator("[data-act-who]").count() == 0:
                ed.locator("[data-act-detail]").click()
            ed.locator("[data-act-more]").click()
        assert ed.get_by_label("activity participant").input_value() == chosen
        discard(ed)

        # A LIST PART: opened and untouched it holds nothing; a row added is a draft
        modal = _new(page, "Discipline")
        ed = modal.locator("[data-author='discipline']")
        _add(modal, "tools")
        ed.locator("[data-cancel]").click()
        assert page.locator("[data-author-modal]").count() == 0  # nothing made: closes at once
        page.keyboard.press("Escape")
        modal = _new(page, "Discipline")
        ed = modal.locator("[data-author='discipline']")
        _add(modal, "tools")
        ed.locator('[data-part="tools"] button.ba-quiet').click()
        rows = ed.locator('[data-part="tools"] input')
        assert rows.count() == 2
        ed.locator("[data-cancel]").click()
        asked_and_kept(ed)
        assert rows.count() == 2, "the added row must still be there"
        rows.nth(0).fill("git")
        rows.nth(1).fill("pytest")
        ed.locator("[data-cancel]").click()
        asked_and_kept(ed)
        assert [rows.nth(i).input_value() for i in range(rows.count())] == ["git", "pytest"]
        assert not errors, errors
        browser.close()
