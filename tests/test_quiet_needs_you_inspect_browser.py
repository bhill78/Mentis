"""Needs You in Quiet Chat, in real Chrome: inspect before deciding.

The owner's requirement (2026-11-20): a request that asks for an
authority-bearing decision says what it is about in plain words, links the
actual post, record or finding, opens it in context, and brings the owner
back to the decision with what they had chosen and typed still there. What
cannot be opened says so. Nothing is shown in place of something else.

A disposable Brain with one open item of every kind (`tests/needs_you_kinds.py`)
and the real HTTP server. Build apps/fluid-web first; opt in with
MENTIS_QUIET_BROWSER=1.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import json
import urllib.request

from mentis.conversation import text
from tests._loop import world  # noqa: F401
from tests.conftest import owner_headers
from tests.needs_you_kinds import GONE, build

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

ID = re.compile(r"\b(?:ent|opr|adm)-[0-9a-f]{6,}\b")
RULE = "Strip dangling links before migrating a chart."
MEASURED = "Measured the old chart loader: 41,211 rows, three rejects."
WORDS = "Hold it until I have read the lesson."


@pytest.fixture()
def chrome():
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


class Quiet:
    """Quiet Chat on the fixture's conversation, as the owner, with Activity open on Needs you."""

    def __init__(self, browser, world, w, width=1440, height=1000):
        self.w = w
        self.context = browser.new_context(viewport={"width": width, "height": height})
        # the suite's one owner session (a login per test would evict it)
        self.context.set_extra_http_headers(owner_headers())
        self.page = self.context.new_page()
        self.errors: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(world["base"] + f"/?c={w['cid']}")
        self.page.wait_for_selector(".q2-gdock-pill", timeout=30000)
        self.open_needs()

    def open_needs(self):
        if not self.page.locator(".q2-gdock-panel").count():
            self.page.locator(".q2-gdock-btn[data-panel='activity']").click()
        self.page.wait_for_selector(".q2-ny-about[data-about]:not([data-about='unread'])", timeout=30000)

    def item(self, key):
        row = self.page.locator(f"[data-needs-item='{key}']")
        row.wait_for(timeout=20000)
        return row

    def answer_here(self, key):
        row = self.item(key)
        row.evaluate("el => el.scrollIntoView({block: 'start'})")
        if not row.locator(".q2-gdock-answer").count():
            row.locator(".q2-gdock-more").click()
        row.locator(".rb-dec-q").first.wait_for(timeout=20000)
        return row

    def back_to_decision(self):
        go = self.page.locator(".q2-gdock-return-go")
        go.wait_for(timeout=10000)
        go.click()
        self.page.wait_for_selector(".q2-gdock-panel [data-needs-item]", timeout=20000)
        self.page.locator(".q2-gdock-return").wait_for(state="detached", timeout=10000)

    def close(self):
        self.context.close()
        assert self.errors == []


def _choose(q, option, words):
    """Choose an option on one question and type; the form rereads every few seconds and may be
    drawn again in between, so it is done until it holds."""
    for _ in range(5):
        try:
            pick = q.locator(f"[data-option='{option}']")
            if pick.get_attribute("aria-checked") != "true":
                pick.click()
            box = q.locator("textarea.rb-dec-words")
            box.wait_for(timeout=3000)
            box.fill(words)
            if box.input_value() == words and pick.get_attribute("aria-checked") == "true":
                return
        except Exception:                                 # noqa: BLE001 -- drawn again
            continue
    raise AssertionError("the form never held the choice and the words")


def _held(q, option, words):
    q.locator("textarea.rb-dec-words").wait_for(timeout=20000)
    assert q.locator(f"[data-option='{option}']").get_attribute("aria-checked") == "true"
    assert q.locator("textarea.rb-dec-words").input_value() == words


def _focused(page, ref):
    page.wait_for_function(
        "id => document.activeElement && document.activeElement.dataset.refId === id", arg=ref, timeout=10000)


def _record_page(page, words):
    rec = page.locator("[data-brain-page='record']")
    rec.wait_for(timeout=20000)
    rec.get_by_text(words, exact=False).first.wait_for(timeout=20000)
    return rec


def test_every_kind_says_what_it_is_about_in_words_never_ids(world, chrome):
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        said = page.locator(".q2-gdock-list").inner_text()
        assert not ID.findall(said), "no internal id is what the owner reads, anywhere in Needs you"

        adoption = q.item(w["adoption"]["ask"])
        assert adoption.locator(".q2-gdock-name").inner_text() == f"@Coach asks you to adopt this lesson: “{RULE}”"
        subject = adoption.locator("[data-role='subject']")
        assert subject.locator(".q2-ny-label").inner_text().lower() == "you are deciding on"
        link = subject.locator("button[data-ref-id]")
        assert link.get_attribute("data-ref-id") == w["rule"], "the link is the record's exact id"
        assert link.inner_text() == f"lesson “{RULE}”"
        assert w["rule"] in link.get_attribute("title"), "the id stays available, as secondary detail"
        evidence = adoption.locator("[data-role='evidence']")
        assert evidence.locator(".q2-ny-label").inner_text().lower() == "supporting material"
        assert evidence.locator("button[data-ref-id]").get_attribute("data-ref-id") == w["evidence"]
        assert "in Evidence room" in evidence.inner_text() and MEASURED in evidence.inner_text()
        assert not subject.locator(f"[data-ref-id='{w['evidence']}']").count(), "evidence is not drawn as the subject"

        findings = q.item(w["findings_decision"])
        assert findings.locator(".q2-gdock-name").inner_text() == "@Coach asks what should happen to the 2 things found along the way."
        named = findings.locator("[data-role='subject'] button[data-ref-id]")
        assert [named.nth(i).get_attribute("data-ref-id") for i in range(named.count())] == w["findings"]
        assert "Reconcile the base branch" in named.nth(0).inner_text()
        assert not findings.locator("[data-role='evidence']").count(), "no evidence is claimed where the record names none"

        perm = q.item(w["permission"])
        assert perm.locator(".q2-gdock-name").inner_text() == "@Coach asks permission to delete the old chart cache."
        op = perm.locator("[data-role='subject']")
        assert "Delete the old chart cache" in op.inner_text() and "Outside this task: it deletes files" in op.inner_text()
        op.locator("summary").click()
        assert "Remove-Item -Recurse C:\\charts\\cache" in op.locator("pre").inner_text(), "the exact command can be inspected"
        assert "@Coach's run" in perm.locator("[data-role='context']").inner_text()

        form = q.item(w["form"])
        assert form.locator(".q2-gdock-name").inner_text() == "@Coach asks you to decide 2 questions."
        assert "The record names no other item" in form.locator("[data-role='subject']").inner_text()
        assert form.locator("[data-role='referenced'] .q2-ny-label").inner_text().lower() == "also named in its words"

        wait = q.item(w["input"])
        assert "the form “cutover” in post #" in wait.locator("[data-role='subject']").inner_text()
        assert wait.locator("[data-role='subject'] button[data-ref-id]").get_attribute("data-ref-id") == w["set"], \
            "an input's subject is the exact set its Done is matched against"
        plain = q.item(w["plain"])
        assert "A reply to this request" in plain.locator("[data-role='subject']").inner_text()
        own = q.item(w["own"])
        assert own.locator("[data-role='subject'] button[data-ref-id]").get_attribute("data-ref-id") == w["twin"], \
            "the record with the same words is a different record, and each ask shows its own"
    finally:
        q.close()


def test_a_form_opens_its_record_and_post_and_comes_back_to_the_half_made_answer(world, chrome):
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        first = w["form_questions"][0]
        row = q.answer_here(w["form"])
        question = row.locator(f"[data-question='{first}']")
        legend = question.locator(".rb-dec-question")
        assert not ID.findall(legend.inner_text()), "the question names things in words"
        assert f"lesson “{RULE}”" in legend.inner_text()
        _choose(question, 1, WORDS)

        # the record its question names: the actual record, on its own page
        legend.locator(f"button[data-ref-id='{w['rule']}']").click()
        rec = _record_page(page, RULE)
        rec.get_by_text("Adopt this lesson?").wait_for(timeout=20000)      # the record itself, with its standing
        go = page.locator(".q2-gdock-return-go")
        go.wait_for(timeout=10000)
        assert "what you chose and typed is still there" in go.get_attribute("aria-label")
        q.back_to_decision()
        _held(page.locator(f"[data-question='{first}']"), 1, WORDS)
        _focused(page, w["rule"])

        # a post it names, in another conversation: shown there
        q.item(w["form"]).locator(f"[data-role='referenced'] button[data-ref-id='{w['evidence']}']").click()
        page.locator("h1", has_text="Evidence room").wait_for(timeout=20000)
        page.locator(f".q2-conv [data-post='{w['evidence']}']").wait_for(timeout=20000)
        q.back_to_decision()
        _held(page.locator(f"[data-question='{first}']"), 1, WORDS)
        _focused(page, w["evidence"])
        # nothing was sent by looking
        assert "not sent yet" in page.locator(f"[data-needs-item='{w['form']}'] .rb-form-status").inner_text()
    finally:
        q.close()


def test_findings_keep_each_choice_while_a_finding_is_read(world, chrome):
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        key = w["findings_decision"]
        row = q.answer_here(key)
        question = row.locator(f"[data-question='{key}']")
        _choose(question, 3, "Only the base branch.")                    # "Decide each finding"
        each = question.locator(".rb-dec-finding")
        assert each.count() == 2
        each.nth(0).get_by_role("radio", name="Pursue").click()
        each.nth(1).get_by_role("radio", name="Dismiss").click()
        # the finding itself, by its exact reference, from inside the form
        read = each.nth(0).locator("button[data-ref-id]")
        assert read.get_attribute("data-ref-id") == w["findings"][0]
        assert read.inner_text().startswith("Read this finding")
        read.click()
        post = world["cv"]._act(w["findings"][0])["turn"]
        page.locator(f".q2-conv [data-post='{post}']").wait_for(timeout=20000)
        q.back_to_decision()
        question = page.locator(f"[data-question='{key}']")
        _held(question, 3, "Only the base branch.")
        each = question.locator(".rb-dec-finding")
        assert each.nth(0).get_by_role("radio", name="Pursue").get_attribute("aria-checked") == "true"
        assert each.nth(1).get_by_role("radio", name="Dismiss").get_attribute("aria-checked") == "true"
    finally:
        q.close()


def test_an_adoption_opens_the_record_and_its_evidence_and_keeps_both_answers(world, chrome):
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        key = w["adoption"]["ask"]
        row = q.answer_here(key)
        _choose(row.locator(f"[data-question='{key}']"), "own", "Not before the migration.")
        row.locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").click()
        rec = _record_page(page, RULE)
        # the decision on the record itself: half-written, then the owner looks elsewhere
        why = rec.get_by_label("Why, kept with your decision")
        why.fill("It held twice.")
        q.back_to_decision()
        _held(page.locator(f"[data-question='{key}']"), "own", "Not before the migration.")
        # its supporting material, a post in another conversation
        q.item(key).locator(f"[data-role='evidence'] button[data-ref-id='{w['evidence']}']").click()
        page.locator(f".q2-conv [data-post='{w['evidence']}']").wait_for(timeout=20000)
        q.back_to_decision()
        _held(page.locator(f"[data-question='{key}']"), "own", "Not before the migration.")
        # and the record again: the reason typed there was kept too
        q.item(key).locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").click()
        rec = _record_page(page, RULE)
        assert rec.get_by_label("Why, kept with your decision").input_value() == "It held twice."
    finally:
        q.close()


def test_what_cannot_be_opened_says_so_before_the_decision(world, chrome):
    w = build(world)
    cv, owner = world["cv"], world["who"]["@brian"]
    turn = cv.say(w["cid"], w["coach"], [text("Please decide on the old rule.")], addressed_to=[owner])
    lost = cv.expect(turn, of=owner, kind="decision", by=w["coach"], material=[GONE],
                     because="it is ready", detail={"options": [{"label": "Keep"}, {"label": "Drop"}]})
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        named = q.item(w["form"]).locator("[data-role='referenced']")
        deleted = named.locator(f"[data-ref-id='{w['removed']}']")
        assert deleted.evaluate("el => el.tagName") == "SPAN", "a deleted post is not a link"
        assert deleted.inner_text() == "a deleted post (#2 in Evidence room) — This post was deleted."
        missing = named.locator(f"[data-ref-id='{GONE}']")
        assert missing.evaluate("el => el.tagName") == "SPAN"
        assert missing.inner_text() == "something this Brain does not hold — This Brain holds nothing with this id."
        assert "A draft nobody should rely on" not in page.locator(".q2-gdock-list").inner_text(), "a deleted post's words are not shown"

        row = q.item(lost)
        gap = row.locator("[data-gap]")
        assert gap.inner_text() == ("Something this Brain does not hold is what you would be deciding on, "
                                    "and it cannot be opened: This Brain holds nothing with this id.")
        assert not row.locator("[data-role='subject'] button[data-ref-id]").count(), "nothing else is offered in its place"
        # said before the answer form, and deciding is still possible
        order = row.evaluate("el => [...el.querySelectorAll('[data-gap], .q2-gdock-more')].map(x => x.className)")
        assert order[0] == "q2-ny-gap" and order[-1] == "q2-gdock-more"
        row = q.answer_here(lost)
        assert row.locator(f"[data-question='{lost}'] [data-option='0']").is_enabled()
        assert row.locator("[data-gap]").is_visible(), "still said with the form open"
    finally:
        q.close()


def test_by_keyboard(world, chrome):
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        first = w["form_questions"][0]
        row = q.answer_here(w["form"])
        _choose(row.locator(f"[data-question='{first}']"), 0, WORDS)
        link = row.locator(f"[data-role='referenced'] button[data-ref-id='{w['rule']}']")
        # reached by Tab, and seen to hold focus
        link.focus()
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Tab")
        _focused(page, w["rule"])
        assert link.evaluate("el => getComputedStyle(el).outlineStyle") != "none", "focus is visible on a reference"
        page.keyboard.press("Enter")
        _record_page(page, RULE)
        # focus is on the way back, and Escape there returns
        page.wait_for_function("document.activeElement && document.activeElement.classList.contains('q2-gdock-return-go')", timeout=10000)
        page.keyboard.press("Escape")
        page.wait_for_selector(".q2-gdock-panel [data-needs-item]", timeout=20000)
        _held(page.locator(f"[data-question='{first}']"), 0, WORDS)
        _focused(page, w["rule"])
    finally:
        q.close()


def test_a_reload_starts_every_form_empty_and_says_nothing_was_sent(world, chrome):
    """STATED BEHAVIOUR, not an accident: a half-made answer is kept in memory for the page,
    so that looking at a reference and coming back finds it. It is never written to the
    browser's storage. After a reload of the tab the form is folded and empty, says nothing
    was sent, and the adoption decision on the record starts empty too (as it always did)."""
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        own, key = w["own"], w["adoption"]["ask"]
        _choose(q.answer_here(own).locator(f"[data-question='{own}']"), 0, "Keep it as written, zebra.")
        q.item(key).locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").click()
        rec = _record_page(page, RULE)
        rec.get_by_label("Why, kept with your decision").fill("It held twice, zebra.")
        q.back_to_decision()
        _held(page.locator(f"[data-question='{own}']"), 0, "Keep it as written, zebra.")     # in the tab: kept
        stored = page.evaluate("JSON.stringify([Object.entries(sessionStorage), Object.entries(localStorage)])")
        assert "zebra" not in stored, "no answer text is in the browser's storage"
        assert "mentis.draft" not in stored and "needs.unfolded" not in stored

        page.reload()
        page.wait_for_selector(".q2-gdock-pill", timeout=30000)
        q.open_needs()
        row = q.item(own)
        assert not row.locator(".q2-gdock-answer").count(), "the form is folded again"
        row = q.answer_here(own)
        question = row.locator(f"[data-question='{own}']")
        question.locator("[data-option='0']").wait_for(timeout=20000)
        assert question.locator("[data-option='0']").get_attribute("aria-checked") == "false", "nothing is chosen"
        assert not question.locator("textarea.rb-dec-words").count(), "nothing is typed"
        assert row.locator(".rb-form-status").inner_text() == "Nothing sent yet"
        assert not page.locator(".q2-gdock-return").count(), "and there is no decision to go back to"
        q.item(key).locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").click()
        rec = _record_page(page, RULE)
        rec.get_by_role("button", name="Adopt", exact=True).wait_for(timeout=20000)
        assert rec.get_by_label("Why, kept with your decision").input_value() == ""
    finally:
        q.close()


def test_at_390_wide(world, chrome):
    w = build(world)
    q = Quiet(chrome, world, w, width=390, height=844)
    page = q.page
    try:
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "the page does not scroll sideways"
        panel = page.locator(".q2-gdock-panel")
        box = panel.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390
        lst = page.locator(".q2-gdock-list")
        assert lst.evaluate("el => el.scrollWidth <= el.clientWidth + 1"), "nothing in Needs you is cut off sideways"
        key = w["adoption"]["ask"]
        row = q.answer_here(key)
        _choose(row.locator(f"[data-question='{key}']"), "own", "Not yet.")
        link = row.locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']")
        link.scroll_into_view_if_needed()
        lb = link.bounding_box()
        assert lb["x"] >= 0 and lb["x"] + lb["width"] <= 390
        link.click()
        _record_page(page, RULE)
        go = page.locator(".q2-gdock-return-go")
        go.wait_for(timeout=10000)
        gb = page.locator(".q2-gdock-return").bounding_box()
        assert gb["x"] >= 0 and gb["x"] + gb["width"] <= 390 and gb["y"] + gb["height"] <= 844, "the way back is on screen"
        q.back_to_decision()
        _held(page.locator(f"[data-question='{key}']"), "own", "Not yet.")
        assert lst.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        # a post, too, at this width
        q.item(key).locator(f"[data-role='evidence'] button[data-ref-id='{w['evidence']}']").click()
        page.locator(f"[data-post='{w['evidence']}']").first.wait_for(timeout=20000)
        q.back_to_decision()
        _held(page.locator(f"[data-question='{key}']"), "own", "Not yet.")
    finally:
        q.close()


def _post(world, path, payload):
    req = urllib.request.Request(world["base"] + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "X-Mentis-Client": "1"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_the_browsers_back_is_the_pages_history_and_never_reopens_needs_you(world, chrome):
    """No listener of the dock's answers a history move: a Back at once after opening a
    reference just goes back, a later unrelated move does nothing here, and the one way
    back to the decision stays until it is used."""
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        first = w["form_questions"][0]
        row = q.answer_here(w["form"])
        _choose(row.locator(f"[data-question='{first}']"), 0, WORDS)
        row.locator(f"[data-role='referenced'] button[data-ref-id='{w['rule']}']").click()
        page.locator("[data-brain-page='record']").wait_for(timeout=20000)
        page.go_back()                                    # at once: no wait of any kind
        page.locator("[data-brain-page='record']").wait_for(state="detached", timeout=20000)
        page.locator(".q2-gdock-return-go").wait_for(timeout=10000)
        assert not page.locator(".q2-gdock-panel").count(), "Back went back, and opened nothing"
        # an unrelated history move, later: this page's own entry, pushed and left
        page.evaluate("new Promise(r => { addEventListener('popstate', () => r(1), { once: true }); history.pushState(history.state, ''); history.back() })")
        assert not page.locator(".q2-gdock-panel").count(), "an unrelated Back does not reopen Needs you"
        assert page.locator(".q2-gdock-return-go").is_visible(), "the way back is still there"
        q.back_to_decision()
        _held(page.locator(f"[data-question='{first}']"), 0, WORDS)
        _focused(page, w["rule"])
    finally:
        q.close()


def test_an_input_opens_at_the_exact_form_of_two_on_one_post(world, chrome):
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        q.item(w["input"]).locator(f"[data-role='subject'] button[data-ref-id='{w['set']}']").click()
        page.locator(f".q2-conv [data-post='{w['input_post']}']").wait_for(timeout=20000)
        landed = page.locator("[data-landed]")
        landed.wait_for(timeout=20000)
        assert landed.count() == 1
        key = landed.get_attribute("data-block-key")
        assert key == f"q2:{w['input_post']}:0/@cutover:form", "the block its response set names, not the other form on the post"
        assert "When may it start?" in landed.inner_text() and "How is it rolled back?" not in landed.inner_text()
        assert page.locator(f"[data-block-key='q2:{w['input_post']}:0/@rollback:form']").count() >= 1, "the other form is on the same post"
        assert page.locator(".q2-gdock-return-go").inner_text().strip().endswith("Back to what needs you")
    finally:
        q.close()


def test_a_draft_is_dropped_when_its_question_is_answered_elsewhere_or_reads_otherwise(world, chrome):
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        own, first = w["own"], w["form_questions"][0]
        _choose(q.answer_here(own).locator(f"[data-question='{own}']"), 0, "Keep it as written.")
        _choose(q.answer_here(w["form"]).locator(f"[data-question='{first}']"), 1, WORDS)

        # ANSWERED ELSEWHERE (another tab, another client): the record closes the question
        got = _post(world, f"/api/conversations/{w['cid']}/turns", {
            "author": world["who"]["@brian"], "text": "Rewrite it", "replies_to": w["own_post"],
            "action": "record-only", "chose": {"expectation": own, "option": 1, "label": "Rewrite it"}})
        assert got.get("turn"), got
        closed = page.locator(f"[data-question='{own}'][data-state='answered']")
        if page.locator(f"[data-needs-item='{own}']").count():
            # the form says what the record says, and the owner's unsent draft is not left on it
            try:
                closed.wait_for(timeout=15000)
                assert not page.locator(f"[data-question='{own}'] textarea.rb-dec-words").count()
            except Exception:                              # noqa: BLE001 -- the item left the list first
                pass
        page.locator(".q2-gdock-close").click()
        page.locator(".q2-gdock-btn[data-panel='activity']").click()
        page.locator(f"[data-needs-item='{own}']").wait_for(state="detached", timeout=20000)
        _held(q.item(w["form"]).locator(f"[data-question='{first}']"), 1, WORDS)        # the other draft is untouched

        # THE QUESTION NOW READS OTHERWISE: the same ask, its options in another order
        page.locator(".q2-gdock-close").click()

        def reordered(route):
            got = route.fetch()
            body = got.json()
            for e in body.get("expectations") or []:
                if e.get("id") == first and e.get("options"):
                    e["options"] = list(reversed(e["options"]))
            route.fulfill(response=got, json=body)
        page.route("**/fluid/api/decisions*", reordered)
        page.locator(".q2-gdock-btn[data-panel='activity']").click()
        question = q.item(w["form"]).locator(f"[data-question='{first}']")
        question.locator("[data-option='0']", has_text="Hold the migration").wait_for(timeout=20000)
        page.wait_for_function(
            "id => { const q = document.querySelector(`[data-question='${id}']`); return q && !q.querySelector('textarea.rb-dec-words') }",
            arg=first, timeout=10000)
        assert question.locator("[data-option='1']").get_attribute("aria-checked") == "false", \
            "the choice made at that place is not applied to what is there now"
        assert question.locator("[data-option='0']").get_attribute("aria-checked") == "false", "nor moved to follow its label"
    finally:
        q.close()


def test_a_repeated_adoption_request_starts_empty(world, chrome):
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        key = w["adoption"]["ask"]
        q.item(key).locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").click()
        rec = _record_page(page, RULE)
        rec.get_by_label("Why, kept with your decision").fill("It held twice.")
        rec.get_by_role("button", name="Edit wording first").click()
        rec.get_by_label("Edited wording").fill("Strip dangling links FIRST.")
        # left and come back to, in the tab: kept
        page.get_by_role("button", name="Back to the conversation").first.click()
        page.locator("[data-brain-page='record']").wait_for(state="detached", timeout=20000)
        q.back_to_decision()
        q.item(key).locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").click()
        rec = _record_page(page, RULE)
        assert rec.get_by_label("Why, kept with your decision").input_value() == "It held twice."
        assert rec.get_by_label("Edited wording").input_value() == "Strip dangling links FIRST."
        page.get_by_role("button", name="Back to the conversation").first.click()
        page.locator("[data-brain-page='record']").wait_for(state="detached", timeout=20000)

        # THE REQUEST IS CLOSED ELSEWHERE AND THE SAME RECORD IS ASKED ABOUT AGAIN, no reload
        _post(world, f"/api/entries/{w['rule']}/decline", {
            "attributed_to": world["who"]["@brian"], "because": "not yet", "request": w["adoption"]["request"]})
        from mentis.web import _surface
        from mentis.worker import _operate
        again = _operate(_surface(world["state"]), "request_adoption",
                         {"entry": w["rule"], "because": "it held a third time"}, w["grant"])
        assert again["request"] != w["adoption"]["request"]
        if page.locator(".q2-gdock-panel").count():
            page.locator(".q2-gdock-close").click()
        page.locator(".q2-gdock-btn[data-panel='activity']").click()
        q.item(again["ask"]).locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").click()
        rec = _record_page(page, RULE)
        rec.get_by_role("button", name="Adopt", exact=True).wait_for(timeout=20000)
        assert rec.get_by_label("Why, kept with your decision").input_value() == "", "the earlier request's reason is not this one's"
        assert not rec.get_by_label("Edited wording").count(), "nor its edited wording"
    finally:
        q.close()


def test_details_that_could_not_be_read_are_said_and_nothing_older_is_shown(world, chrome):
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        key = w["adoption"]["ask"]
        assert q.item(key).locator("[data-role='subject'] button[data-ref-id]").count() == 1      # read once, shown
        page.locator(".q2-gdock-close").click()
        page.route("**/fluid/api/needs-you/about*", lambda route: route.abort())
        page.locator(".q2-gdock-btn[data-panel='activity']").click()
        row = q.item(key)
        gap = row.locator(".q2-ny-about[data-about='unread'] .q2-ny-gap")
        gap.wait_for(timeout=20000)
        assert "could not be read" in gap.inner_text()
        assert not row.locator("[data-role='subject']").count(), "what was read before is not shown as current"
        assert not row.locator("button[data-ref-id]").count()
        # the decision stays usable
        row.locator(".q2-gdock-more").click()
        row.locator(f"[data-question='{key}'] [data-option='own']").wait_for(timeout=20000)
        # and a later opening that can read shows the details again
        page.unroute("**/fluid/api/needs-you/about*")
        page.locator(".q2-gdock-close").click()
        page.locator(".q2-gdock-btn[data-panel='activity']").click()
        q.item(key).locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").wait_for(timeout=20000)
    finally:
        q.close()


def test_a_reread_of_the_list_shows_nothing_earlier_until_its_details_are_read(world, chrome):
    """THE SAME OPENING, THE LIST READ AGAIN (review-needs-you-4): what the earlier read said
    must not stay beside the decision while the new details are on their way. The list may now
    be another Brain's (a deployment or restore on the same address keeps the same ids), so the
    earlier subject could sit beside a decision it is not about. Here the record moves (a new
    request for the owner), the list is read again in the same opening, and the details read
    is held: the earlier subject is gone until it answers, the decision stays usable, and the
    details come back when it does."""
    w = build(world)
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        key = w["adoption"]["ask"]
        row = q.item(key)
        row.locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").wait_for(timeout=20000)
        held = []
        page.route("**/fluid/api/needs-you/about*", lambda route: held.append(route))
        # the record moves: one more request for the owner, so the list is read again
        cv, owner, coach = world["cv"], world["who"]["@brian"], w["coach"]
        asked = cv.say(w["cid"], coach, [text("One more question, to make the list move.")], addressed_to=[owner])
        more = cv.expect(asked, of=owner, kind="clarification", by=coach, because="the list must move")
        q.item(more)                                                   # the list was read again
        for _ in range(100):
            if held:
                break
            page.wait_for_timeout(100)
        assert held, "the details were read again when the list moved"
        row = q.item(key)
        assert not row.locator("[data-role='subject']").count(), "the earlier subject is gone while the new details are read"
        assert not row.locator("button[data-ref-id]").count()
        row.locator(".q2-ny-about[data-about='unread'] .q2-ny-reading").wait_for(timeout=10000)
        # the decision stays usable meanwhile
        row.locator(".q2-gdock-more").click()
        row.locator(f"[data-question='{key}'] [data-option='own']").wait_for(timeout=20000)
        # released: the details come back, read afresh
        page.unroute("**/fluid/api/needs-you/about*")           # releases the held reads
        q.item(key).locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").wait_for(timeout=20000)
    finally:
        q.close()

