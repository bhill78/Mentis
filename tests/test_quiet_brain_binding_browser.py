"""A decision opened on one Brain is never recorded in another, in real Chrome (owner,
2026-11-20, "Needs You Safety").

Quiet Chat binds the page to the Brain the server serves when it opens, names that Brain on
every write (`X-Mentis-Brain`), and checks it after every reread of a decision form. The real
server refuses a write naming another Brain before anything is written. "Another Brain on the
same address" is simulated by answering the page's identity reads as another instance of the
same Brain (a copy restored in place shares the id, not the instance); the server itself is
the real one, and every refusal here is its own.

A disposable Brain (`tests/needs_you_kinds.py`) and the real HTTP server. Build
apps/fluid-web first; opt in with MENTIS_QUIET_BROWSER=1.
"""

from __future__ import annotations

import json
import re
import urllib.request

import pytest

from tests._loop import world  # noqa: F401
from tests.conftest import owner_headers
from tests.needs_you_kinds import build
from tests.test_quiet_needs_you_inspect_browser import Quiet, _choose, chrome, pytestmark  # noqa: F401

OTHER = "0123456789abcdef"
TYPED = "Keep it as written, walrus."


def as_other(route):
    """The identity a read names, as another instance of the same Brain."""
    r = route.fetch()
    body = r.json()
    if isinstance(body.get("brain"), dict):
        body["brain"]["instance"] = OTHER
    route.fulfill(response=r, json=body)


def recorded(world, op):
    req = urllib.request.Request(
        world["base"] + f"/api/operations?op={urllib.request.quote(op)}&author={world['who']['@brian']}",
        headers={"X-Mentis-Client": "1", **owner_headers()})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["recorded"]


def still_open(world, ask):
    req = urllib.request.Request(world["base"] + "/fluid/api/needs-you/items", headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return any(ask in (i.get("asks") or []) or i.get("key") == ask for i in json.loads(r.read())["items"])


class OpenedOn(Quiet):
    """Quiet Chat as `Quiet` opens it, with `before(context)` done first: the page is opened on
    whatever Brain the routes then say."""

    def __init__(self, browser, world, w, before):
        self.w = w
        self.context = browser.new_context(viewport={"width": 1440, "height": 1000})
        self.context.set_extra_http_headers(owner_headers())
        before(self.context)
        self.page = self.context.new_page()
        self.errors: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(world["base"] + f"/?c={w['cid']}")
        self.page.wait_for_selector(".q2-gdock-pill", timeout=30000)
        self.open_needs()


def answers_sent(page):
    """Every answer the page posts: (its operation key, the Brain it named)."""
    out = []
    page.on("request", lambda r: out.append((json.loads(r.post_data or "{}").get("op"), r.headers.get("x-mentis-brain")))
            if r.method == "POST" and "/turns" in r.url else None)
    return out


def send(row):
    row.locator(".rb-dec-foot .btn.primary").first.click()


def test_a_form_opened_on_another_brain_is_refused_keeps_what_was_typed_and_reloads_to_this_one(world, chrome):
    """THE STALE FORM. The page was opened on a Brain the server no longer serves: the answer is
    refused by the server before anything is written, the page says the Brain changed and how
    to reach this one, and what was typed is still there to copy. After a reload the page is
    this Brain's, and the decision is answered there, once."""
    w = build(world)
    own = w["own"]

    def opened_on_other(ctx):
        ctx.route("**/fluid/api/needs-you/*", as_other)      # which Brain, Needs you, and each form

    q = OpenedOn(chrome, world, w, opened_on_other)
    page = q.page
    try:
        sent = answers_sent(page)
        row = q.answer_here(own)
        _choose(row.locator(f"[data-question='{own}']"), 0, TYPED)
        send(row)
        page.locator("[data-brain-moved]").wait_for(timeout=20000)
        assert len(sent) == 1 and sent[0][1] and sent[0][1].endswith("@" + OTHER), sent
        assert not recorded(world, sent[0][0]), "the server wrote nothing"
        assert still_open(world, own), "the decision is still open on this Brain"
        moved = page.locator("[data-brain-moved]").inner_text()
        assert "another Brain" in moved and "Reload for this Brain" in moved
        page.locator("[data-brain-changed]").wait_for(timeout=20000)
        row = q.item(own)
        assert not row.locator("[data-question]").count(), "the stale form is not offered again"
        assert row.locator("[data-unsent] textarea").input_value() == TYPED, "what was typed is still readable"
        assert "\\" not in moved and ":/" not in moved, "no folder is named"

        # a reload binds the page to the Brain the server serves
        q.context.unroute("**/fluid/api/needs-you/*")
        asked = []
        page.once("dialog", lambda d: (asked.append(d.type), d.accept()))
        page.locator("[data-brain-moved] button").click()
        page.wait_for_selector(".q2-gdock-pill", timeout=30000)
        assert asked == ["beforeunload"], "reloading with an answer typed and not sent asks first"
        q.open_needs()
        assert not page.locator("[data-brain-moved]").count() and not page.locator("[data-brain-changed]").count()
        row = q.answer_here(own)
        _choose(row.locator(f"[data-question='{own}']"), 0, TYPED)
        send(row)
        page.wait_for_function("ask => !document.querySelector(`[data-needs-item='${ask}'] .rb-dec-foot .btn.primary:not([disabled])`)",
                               arg=own, timeout=20000)
        page.wait_for_timeout(1500)
        good = [op for op, brain in sent[1:] if op]
        assert good and all(b and not b.endswith("@" + OTHER) for _, b in sent[1:]), sent
        assert sum(recorded(world, op) for op in {op for op, _ in sent if op}) == 1, "one answer recorded"
        assert not still_open(world, own)
    finally:
        q.close()


def test_a_form_reread_from_another_brain_is_not_shown(world, chrome):
    """A FORM ON SCREEN, AND THEN ANOTHER BRAIN. The form rereads while its question is open;
    each reread is checked against the page's Brain, so a reread from another is never drawn,
    and the page moves."""
    w = build(world)
    own = w["own"]
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        row = q.answer_here(own)
        row.locator(f"[data-question='{own}']").wait_for(timeout=20000)
        assert not page.locator("[data-brain-moved]").count()
        page.route("**/fluid/api/needs-you/decisions*", as_other)   # the next reread is another Brain's
        page.locator("[data-brain-moved]").wait_for(timeout=30000)
        row = q.item(own)
        row.locator("[data-question]").first.wait_for(state="detached", timeout=20000)
        assert page.locator("[data-brain-changed]").count()
    finally:
        q.close()


def test_two_tabs_on_two_brains_record_one_answer(world, chrome):
    """TWO TABS, DIFFERENT STATE: one still on the Brain it was opened on before the server
    changed, one reloaded onto the Brain served now. The second answers; the first cannot add a
    second answer, to either Brain."""
    w = build(world)
    own = w["own"]

    def opened_on_other(ctx):
        ctx.route("**/fluid/api/needs-you/*", as_other)      # which Brain, Needs you, and each form

    old = OpenedOn(chrome, world, w, opened_on_other)
    new = Quiet(chrome, world, w)
    try:
        sent_old, sent_new = answers_sent(old.page), answers_sent(new.page)
        row_old = old.answer_here(own)
        _choose(row_old.locator(f"[data-question='{own}']"), 1, "Rewrite it, from the old tab.")
        row_new = new.answer_here(own)
        _choose(row_new.locator(f"[data-question='{own}']"), 0, TYPED)
        send(row_new)
        new.page.wait_for_timeout(2500)
        assert [op for op, _ in sent_new if op] and recorded(world, sent_new[0][0]), "the current tab's answer is recorded"
        # the old tab either cannot send at all (the answer sent from the other tab locks every copy
        # of the form) or sends and is refused as another Brain's: either way nothing more is recorded
        old.page.wait_for_timeout(2500)
        button = row_old.locator(".rb-dec-foot .btn.primary")
        if button.count() and button.first.is_enabled():
            send(row_old)
            old.page.wait_for_timeout(2500)
        recorded_ops = {op for op, _ in sent_old + sent_new if op and recorded(world, op)}
        assert recorded_ops == {sent_new[0][0]}, (sent_old, sent_new)
        assert not still_open(world, own)
    finally:
        old.close()
        new.close()


def test_a_lost_acknowledgment_is_asked_about_never_sent_twice(world, chrome):
    """THE ANSWER LANDS, ITS ACKNOWLEDGMENT IS LOST. It named this Brain and was recorded; the
    page does not know. After a reload the page asks the server about it (a read) and never
    sends it again: one answer is recorded."""
    w = build(world)
    own = w["own"]
    q = Quiet(chrome, world, w)
    page = q.page
    try:
        sent = answers_sent(page)

        def lose_the_answer(route):
            route.fetch()                                    # the server records it ...
            route.abort()                                    # ... and the page never hears

        page.route("**/api/conversations/*/turns", lose_the_answer)
        row = q.answer_here(own)
        _choose(row.locator(f"[data-question='{own}']"), 0, TYPED)
        send(row)
        page.wait_for_timeout(2500)
        page.unroute("**/api/conversations/*/turns")
        assert len(sent) == 1 and sent[0][1], "the answer named the Brain"
        assert recorded(world, sent[0][0]), "it landed"
        page.reload()
        page.wait_for_selector(".q2-gdock-pill", timeout=30000)
        page.wait_for_timeout(3000)
        assert len(sent) == 1, "nothing was sent again"
        assert not still_open(world, own)
    finally:
        q.close()


def test_a_half_written_adoption_decision_is_never_lost_without_a_word(world, chrome):
    """DRAFT PROTECTION (owner, 2026-11-20): an adoption decision being written survives closing
    the record, Escape, collapsing the edited wording, another conversation and Back, and a
    decision the server refuses; leaving the page itself asks first."""
    w = build(world)
    key, rule = w["adoption"]["ask"], w["rule"]
    q = Quiet(chrome, world, w)
    page = q.page
    why = "It held on both migrations, narwhal."
    wording = "Strip dangling links before migrating any chart, narwhal."

    def open_record():
        q.open_needs()
        q.item(key).locator(f"[data-role='subject'] button[data-ref-id='{rule}']").click()
        rec = page.locator("[data-brain-page='record']")
        rec.get_by_role("button", name="Adopt", exact=True).wait_for(timeout=20000)
        return rec

    def kept(rec):
        assert rec.get_by_label("Why, kept with your decision").input_value() == why
        if not rec.get_by_label("Edited wording").count():
            rec.get_by_role("button", name="Edit wording first").click()
        assert rec.get_by_label("Edited wording").input_value() == wording

    try:
        rec = open_record()
        rec.get_by_label("Why, kept with your decision").fill(why)
        rec.get_by_role("button", name="Edit wording first").click()
        rec.get_by_label("Edited wording").fill(wording)
        # Cancel: collapsing the edited wording keeps it
        rec.get_by_role("button", name="Edit wording first").click()
        assert not rec.get_by_label("Edited wording").count()
        kept(rec)
        # closing the record, and coming back
        page.get_by_role("button", name=re.compile("Back to the conversation")).first.click()
        rec.wait_for(state="detached", timeout=20000)
        kept(open_record())
        # Escape, and coming back
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        if page.locator("[data-brain-page='record']").count():
            page.keyboard.press("Escape")
        kept(open_record())
        # the browser's Back, and Forward to it again
        page.go_back()
        page.wait_for_timeout(1000)
        page.go_forward()
        rec = page.locator("[data-brain-page='record']")
        rec.get_by_role("button", name="Adopt", exact=True).wait_for(timeout=20000)
        kept(rec)
        # a decision the server refuses keeps everything written
        page.route("**/api/entries/*/decline", lambda r: r.fulfill(status=500, json={"error": "the server could not record it"}))
        rec.get_by_role("button", name="Decline", exact=True).click()
        rec.locator(".rv-error").wait_for(timeout=20000)
        kept(rec)
        page.unroute("**/api/entries/*/decline")
        # leaving the page itself asks first
        asked = []
        page.once("dialog", lambda d: (asked.append(d.type), d.dismiss()))
        page.evaluate("() => { location.reload() }")             # declined: the page stays
        page.wait_for_timeout(1500)
        assert asked == ["beforeunload"], "a reload with a half-written decision asks first"
        kept(page.locator("[data-brain-page='record']"))
        assert still_open(world, key), "nothing was decided"
    finally:
        q.close()


def test_an_answer_kept_before_brains_were_named_is_shown_and_never_sent_again(world, chrome):
    """A KEPT ANSWER FROM BEFORE THIS CHANGE carries no Brain: which Brain it went to is not known.
    Quiet shows it with its words, never sends it again or withdraws it, lets the owner ask this
    Brain about it (a read) or forget the note, and the question can still be answered here."""
    w = build(world)
    own = w["own"]
    kept = {"ask": own, "op": f"decision:{own}:legacy", "conversation": w["cid"], "author": world["who"]["@brian"],
            "body": {"op": f"decision:{own}:legacy"}, "pick": {"kind": "own"}, "text": "An answer from the old page, puffin.",
            "label": None, "continued": False, "phase": "unknown", "at": 0, "turn": None, "number": None,
            "dispatched": None, "did": None, "why": "the page was reloaded before the server answered", "kept": True}

    def seeded(ctx):
        ctx.add_init_script(
            f"try {{ if (!sessionStorage.getItem('seeded')) {{ localStorage.setItem('mentis.decisions.sent.v2:{own}', "
            f"{json.dumps(json.dumps(kept))}); sessionStorage.setItem('seeded', '1') }} }} catch (e) {{}}")

    q = OpenedOn(chrome, world, w, seeded)
    page = q.page
    try:
        writes = []
        page.on("request", lambda r: writes.append(r.url) if r.method == "POST" else None)
        note = page.locator("[data-legacy-sent]")
        note.wait_for(timeout=20000)
        assert "puffin" in note.locator("textarea").input_value()
        assert "never" in note.inner_text() and "confirmed" in note.inner_text()
        note.get_by_role("button", name="Check").click()
        note.get_by_text("This Brain does not hold it").wait_for(timeout=20000)
        assert writes == [], "asking is a read: nothing was sent"
        row = q.answer_here(own)
        row.locator(f"[data-question='{own}']").wait_for(timeout=20000)     # still answerable here
        note.get_by_role("button", name="Forget it in this browser").click()
        note.wait_for(state="detached", timeout=10000)
        assert writes == [] and not recorded(world, kept["op"])
        assert "puffin" not in page.evaluate("JSON.stringify(Object.entries(localStorage))")
    finally:
        q.close()
