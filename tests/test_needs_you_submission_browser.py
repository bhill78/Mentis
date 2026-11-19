"""The decision form in real Chrome: slow answers, lost acknowledgments, refreshes, duplicates.

The incident (TEST, 2026-11-19, post #423): the owner answered a decision about findings in
their own words. The words were recorded; the decision, correctly, stayed open. The form said
"Sent ... the record has not shown it yet", and after a refresh, "Nothing sent yet".

What the form must do instead is in apps/fluid-web/src/experimental/decisionOutbox.ts. Here the
network between the page and a real server is interfered with: the server is the real one, so
"recorded once" is read from its record, not from the page.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest

from mentis.conversation import text
from mentis.operational import ask_about_findings, trunk_of
from tests._loop import _coordinator, a_conversation, world  # noqa: F401
from tests.conftest import owner_headers

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

TURNS = "**/api/conversations/*/turns"
READS = ("**/api/operations*", "**/fluid/api/decisions*")


def _offline(page, post):
    """The connection is gone: `post` says what happens to the answer being sent (it may still
    have reached the server), and nothing can be read back until `_online`."""
    page.route(TURNS, lambda route: post(route) if route.request.method == "POST" else route.continue_())
    for pattern in READS:
        page.route(pattern, lambda route: route.abort())


def _online(page):
    page.unroute(TURNS)
    for pattern in READS:
        page.unroute(pattern)


def _recorded_then_lost(route):
    route.fetch()                      # the server receives and records it
    route.abort()                      # and the answer never reaches the page
WORDS = "Pursue the base branch work; keep the rest."


def _world(world):
    """A conversation with an ordinary decision and a decision about findings, both asked of
    the owner (as tests/test_decision_continue_browser.py makes them)."""
    from mentis.web import _surface
    from mentis.worker import _operate
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = a_conversation(world, "Decisions")
    coach, parent, grant = _coordinator(world, cid)
    asked = cv.say(cid, coach, [text("Which branch should we keep?")])
    cv.expect(asked, of=owner, kind="decision", by=coach, because="which branch",
              detail={"options": [{"label": "Keep both"}, {"label": "Drop one"}]})
    found = [_operate(_surface(world["state"]), "record_discovered_work",
                      {"work": w, "because": "found on the way"}, grant)["expectation"]
             for w in ("Reconcile the base branch", "Rename the old flags")]
    brain = world["state"].brain
    offer = ask_about_findings(brain, found, conversation=cid, by=coach, owner=owner, caused_by=parent,
                               originating_turn=trunk_of(brain, parent)["originating_turn"],
                               question="Finished. What should happen to the 2 things found along the way?")
    return cid, offer["expectation"]


def _count(world, cid):
    req = urllib.request.Request(world["base"] + f"/api/conversations/{cid}", headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["turns_total"]


def _card(page, words):
    card = page.locator(".rb-form", has=page.get_by_text(words, exact=False)).filter(
        has=page.locator(".rb-dec-foot")).first
    card.wait_for(timeout=20000)
    return card


def _own_words(page, card_words, words=WORDS):
    """Choose "Your own words" on the card and type; a card rereads every few seconds and may be
    drawn again in between, so it is done until it holds."""
    for _ in range(5):
        card = _card(page, card_words)
        card.locator(".rb-dec-own").first.click()
        try:
            box = card.locator("textarea.rb-dec-words")
            box.wait_for(timeout=3000)
            box.fill(words)
            card.locator(".rb-form-status", has_text="One answer chosen").wait_for(timeout=3000)
            if box.input_value() == words:
                return card
        except Exception:                                 # noqa: BLE001 -- drawn again
            continue
    raise AssertionError("the card never held the owner's words")


def _press(card):
    card.locator(".rb-dec-foot .btn.primary").click()


class _Page:
    def __init__(self, world, cid, playwright):
        self.world, self.cid, self.p = world, cid, playwright

    def __enter__(self):
        self.browser = self.p.chromium.launch()
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        # the suite's one owner session (a login per test would evict it: the credential keeps 64)
        self.context.set_extra_http_headers(owner_headers())
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(self.world["base"] + f"/fluid?c={self.cid}")
        return self.page

    def __exit__(self, *exc):
        self.browser.close()
        if exc[0] is None:
            assert self.errors == []


@pytest.fixture()
def chrome():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        yield p


FINDINGS = "what to do with work found along the way"


def test_words_alone_on_a_decision_about_findings_say_recorded_and_still_open_through_a_refresh(world, chrome):
    """The incident, end to end."""
    cid, _ = _world(world)
    n = _count(world, cid)
    with _Page(world, cid, chrome) as page:
        card = _own_words(page, FINDINGS)
        # said BEFORE it is sent: words alone will not decide this
        assert "leave this decision open" in card.locator("[data-leaves-open]").inner_text()
        assert card.locator(".rb-dec-foot .btn.primary").inner_text() == "Reply, leaving it open"
        _press(card)
        said = _card(page, FINDINGS).locator("[data-reply-recorded]")
        said.wait_for(timeout=20000)
        number = said.get_attribute("data-reply-recorded")
        assert number and f"Your reply #{number} is recorded." in said.inner_text()
        assert "It did not decide this" in said.inner_text()
        whole = _card(page, FINDINGS).inner_text()
        assert "Nothing sent yet" not in whole and "Sent as" not in whole
        assert f"Your reply #{number} is recorded; this is still open" in whole
        assert _count(world, cid) == n + 1
        # the refresh: the same thing is said, from the record
        page.reload()
        again = _card(page, FINDINGS).locator("[data-reply-recorded]")
        again.wait_for(timeout=20000)
        assert again.get_attribute("data-reply-recorded") == number
        assert "Nothing sent yet" not in _card(page, FINDINGS).inner_text()
        # and the decision can still be made, by a choice, with the words added
        card = _card(page, FINDINGS)
        for _ in range(4):
            card.locator(".rb-dec-option", has_text="Keep all deferred").first.click()
            try:
                card.locator(".rb-form-status", has_text="One answer chosen").wait_for(timeout=3000)
                break
            except Exception:                             # noqa: BLE001
                card = _card(page, FINDINGS)
        _press(card)
        closed = page.locator(".rb-dec-closed.answered", has_text="Recorded").first
        closed.wait_for(timeout=20000)
        assert _count(world, cid) == n + 2
        # what the choice did is the server's account, said apart from "recorded"
        did = page.locator("[data-what-it-did]").first.inner_text()
        assert "0 to pursue, 2 kept deferred, 0 dismissed" in did and "Nothing was started." in did
        assert "No governed material changed" not in did and "Nothing else was recorded" not in did


def test_a_slow_answer_says_sending_and_then_recorded_never_sent(world, chrome):
    cid, _ = _world(world)
    n = _count(world, cid)
    with _Page(world, cid, chrome) as page:
        def slowly(route):
            page.wait_for_timeout(10000)
            route.continue_()
        page.route(TURNS, lambda route: slowly(route) if route.request.method == "POST" else route.continue_())
        card = _own_words(page, "Which branch", "Keep both, for now.")
        _press(card)
        state = _card(page, "Which branch").locator("[data-sent='sending']")
        state.wait_for(timeout=5000)
        assert "Sending your answer" in state.inner_text()
        assert _card(page, "Which branch").locator("textarea.rb-dec-words").input_value() == "Keep both, for now."
        # it is taking long: still Sending, and it says the words are kept; nothing claims success
        page.get_by_text("Still sending your answer").wait_for(timeout=12000)
        assert "kept on this device and cannot be recorded twice" in _card(page, "Which branch").inner_text()
        assert "Recorded as" not in _card(page, "Which branch").inner_text()
        page.locator(".rb-dec-closed.answered", has_text="Recorded").first.wait_for(timeout=30000)
        assert "Keep both, for now." in page.locator(".rb-dec-closed.answered").first.inner_text()
        assert _count(world, cid) == n + 1


def test_a_lost_acknowledgment_is_not_confirmed_then_found_recorded_without_a_second_post(world, chrome):
    cid, _ = _world(world)
    n = _count(world, cid)
    with _Page(world, cid, chrome) as page:
        card = _own_words(page, "Which branch", "Drop one of them.")
        _offline(page, _recorded_then_lost)
        _press(card)
        state = _card(page, "Which branch").locator("[data-sent='unknown']")
        state.wait_for(timeout=20000)
        told = state.inner_text()
        assert "Not confirmed" in told and "It may or may not have been recorded" in told
        assert "cannot record it twice" in told
        assert _card(page, "Which branch").locator("textarea.rb-dec-words").input_value() == "Drop one of them."
        assert _count(world, cid) == n + 1, "the server did record it"
        _online(page)
        # Send again: the same operation, so the first post is the answer
        _card(page, "Which branch").locator("[data-resend]").click()
        page.locator(".rb-dec-closed.answered", has_text="Recorded").first.wait_for(timeout=20000)
        assert _count(world, cid) == n + 1, "sent twice, recorded once"


def test_checking_asks_the_server_and_writes_nothing(world, chrome):
    cid, _ = _world(world)
    n = _count(world, cid)
    with _Page(world, cid, chrome) as page:
        card = _own_words(page, "Which branch", "Keep both.")
        _offline(page, _recorded_then_lost)
        _press(card)
        _card(page, "Which branch").locator("[data-sent='unknown']").wait_for(timeout=20000)
        _online(page)
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        _card(page, "Which branch").locator("[data-check]").click()
        page.locator(".rb-dec-closed.answered", has_text="Recorded").first.wait_for(timeout=20000)
        assert posts == [], "Check again is a read"
        assert _count(world, cid) == n + 1


def test_an_answer_that_never_reached_the_server_is_said_not_recorded_and_given_back(world, chrome):
    cid, _ = _world(world)
    n = _count(world, cid)
    with _Page(world, cid, chrome) as page:
        card = _own_words(page, "Which branch", "Keep bth.")
        _offline(page, lambda route: route.abort())
        _press(card)
        state = _card(page, "Which branch").locator("[data-sent='unknown']")
        state.wait_for(timeout=20000)
        assert "It may or may not have been recorded" in state.inner_text()
        assert _count(world, cid) == n
        _online(page)
        _card(page, "Which branch").locator("[data-check]").click()
        # asked, and said as what it is: not held NOW. That is not "it was not recorded".
        page.get_by_text("the server does not hold it. It may never have arrived").wait_for(timeout=20000)
        card = _card(page, "Which branch")
        assert "Not confirmed" in card.inner_text() and "Not recorded" not in card.inner_text()
        assert card.locator("textarea.rb-dec-words").input_value() == "Keep bth."
        assert _count(world, cid) == n
        # Change it first asks the SERVER to give the answer up; only then do the words come back
        gave_up = []
        page.on("request", lambda r: gave_up.append(r.url)
                if r.method == "POST" and "/api/operations/void" in r.url else None)
        card.locator("[data-take-back]").click()
        page.wait_for_function(
            "() => { const t = document.querySelector('textarea.rb-dec-words'); return t && !t.readOnly }",
            timeout=20000)
        box = _card(page, "Which branch").locator("textarea.rb-dec-words")
        assert len(gave_up) == 1
        assert box.input_value() == "Keep bth." and box.is_editable()
        box.fill("Keep both.")
        _press(_card(page, "Which branch"))
        closed = page.locator(".rb-dec-closed.answered", has_text="Recorded").first
        closed.wait_for(timeout=20000)
        assert "Keep both." in closed.inner_text()
        assert _count(world, cid) == n + 1


def test_a_refresh_while_it_is_being_sent_asks_what_happened_and_never_says_nothing_sent(world, chrome):
    cid, _ = _world(world)
    n = _count(world, cid)
    with _Page(world, cid, chrome) as page:
        def hang(route):
            if route.request.method != "POST":
                return route.continue_()
            route.fetch()                      # recorded by the server; the page never hears
        page.route(TURNS, hang)
        _press(_own_words(page, "Which branch", "Keep both, decided."))
        _card(page, "Which branch").locator("[data-sent='sending']").wait_for(timeout=5000)
        page.wait_for_timeout(1500)
        assert _count(world, cid) == n + 1
        page.unroute(TURNS)
        page.reload()
        closed = page.locator(".rb-dec-closed.answered", has_text="Recorded").first
        closed.wait_for(timeout=30000)
        assert "Keep both, decided." in closed.inner_text()
        assert _count(world, cid) == n + 1, "the refresh sent nothing again"


def test_a_refresh_before_the_server_ever_received_it_keeps_the_words_and_says_so(world, chrome):
    cid, _ = _world(world)
    n = _count(world, cid)
    with _Page(world, cid, chrome) as page:
        page.route(TURNS, lambda route: None if route.request.method == "POST" else route.continue_())
        _press(_own_words(page, "Which branch", "Words the server never saw."))
        _card(page, "Which branch").locator("[data-sent='sending']").wait_for(timeout=5000)
        # (the held request is not released: removing the route would let it through)
        page.reload()
        page.get_by_text("the server does not hold it").wait_for(timeout=30000)
        card = _card(page, "Which branch")
        assert card.locator("textarea.rb-dec-words").input_value() == "Words the server never saw."
        assert "Nothing sent yet" not in card.inner_text()
        assert _count(world, cid) == n


def test_pressing_decide_many_times_records_one_answer(world, chrome):
    cid, _ = _world(world)
    n = _count(world, cid)
    with _Page(world, cid, chrome) as page:
        seen = []
        page.on("request", lambda r: seen.append(r.url) if r.method == "POST" and "/turns" in r.url else None)
        card = _own_words(page, "Which branch", "Keep both.")
        button = card.locator(".rb-dec-foot .btn.primary")
        button.dblclick()
        page.keyboard.press("Enter")
        page.locator(".rb-dec-closed.answered", has_text="Recorded").first.wait_for(timeout=20000)
        assert len(seen) == 1 and _count(world, cid) == n + 1


def test_a_refusal_says_nothing_was_recorded_and_keeps_the_words(world, chrome):
    cid, _ = _world(world)
    n = _count(world, cid)
    with _Page(world, cid, chrome) as page:
        page.route(TURNS, lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"error": "this Conversation is in Trash; restore it to post here"}))
            if route.request.method == "POST" else route.continue_())
        _press(_own_words(page, "Which branch", "Keep both."))
        failed = _card(page, "Which branch").locator(".rb-form-failed")
        failed.wait_for(timeout=20000)
        assert "Not sent, and nothing was recorded: this Conversation is in Trash" in failed.inner_text()
        card = _card(page, "Which branch")
        assert card.locator("textarea.rb-dec-words").input_value() == "Keep both."
        assert card.locator("textarea.rb-dec-words").is_enabled()
        assert _count(world, cid) == n


def test_changing_an_unconfirmed_answer_that_had_landed_says_recorded_and_hands_nothing_back(world, chrome):
    """The danger "Change it first" must not create: the first answer DID land, the owner changes
    it, and both end up in the record."""
    cid, _ = _world(world)
    n = _count(world, cid)
    with _Page(world, cid, chrome) as page:
        card = _own_words(page, FINDINGS, "First words, which did land.")
        _offline(page, _recorded_then_lost)
        _press(card)
        _card(page, FINDINGS).locator("[data-sent='unknown']").wait_for(timeout=20000)
        assert _count(world, cid) == n + 1
        _online(page)
        _card(page, FINDINGS).locator("[data-take-back]").click()
        said = _card(page, FINDINGS).locator("[data-reply-recorded]")
        said.wait_for(timeout=20000)
        assert "is recorded" in said.inner_text()
        assert _count(world, cid) == n + 1, "nothing was handed back to send as a second answer"


def test_two_pages_about_different_questions_do_not_undo_each_other(world, chrome):
    cid, _ = _world(world)
    with _Page(world, cid, chrome) as page:
        other = page.context.new_page()
        other.goto(world["base"] + f"/fluid?c={cid}")
        # each page sends an answer the server never receives, about a different question
        for pg in (page, other):
            pg.route(TURNS, lambda route: None if route.request.method == "POST" else route.continue_())
        _press(_own_words(page, "Which branch", "From the first page."))
        _card(page, "Which branch").locator("[data-sent='sending']").wait_for(timeout=5000)
        _press(_own_words(other, FINDINGS, "From the second page."))
        _card(other, FINDINGS).locator("[data-sent='sending']").wait_for(timeout=5000)
        keys = page.evaluate("Object.keys(localStorage).filter((k) => k.startsWith('mentis.decisions.sent.'))")
        assert len(keys) == 2, keys
        # and each page shows the other's as being sent, so neither question can be answered twice
        _card(page, FINDINGS).locator("[data-sent='sending']").wait_for(timeout=10000)
        _card(other, "Which branch").locator("[data-sent='sending']").wait_for(timeout=10000)
        other.close()
