"""A decision about work found along the way offers no "+ continue"; an ordinary one still does.

THE DUPLICATE THIS EXISTS FOR (Quiet Chat, 2026-11-08). The owner answered "Pursue" on a
found-along-the-way decision with "+ continue with @Caretaker". Pursue already started the
finding as its own work, and the continuation started a second request, for the same carrier,
carrying only the option's words.
"""

from __future__ import annotations

import os

import pytest

from mentis.conversation import text
from mentis.operational import ask_about_findings, trunk_of
from tests._loop import _coordinator, a_conversation, world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)


def _decisions(world):
    from mentis.web import _surface
    from mentis.worker import _operate
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = a_conversation(world, "Decisions")
    coach, parent, grant = _coordinator(world, cid)
    # an ordinary decision the carrier asked as its own Turn
    asked = cv.say(cid, coach, [text("Which branch should we keep?")])
    ordinary = cv.expect(asked, of=owner, kind="decision", by=coach, because="which branch",
                         detail={"options": [{"label": "Keep both"}, {"label": "Drop one"}]})
    # and work found along the way, offered when the work finished
    found = _operate(_surface(world["state"]), "record_discovered_work",
                     {"work": "Reconcile the base branch", "because": "found on the way"},
                     grant)["expectation"]
    brain = world["state"].brain
    offer = ask_about_findings(brain, [found], conversation=cid, by=coach, owner=owner,
                               caused_by=parent,
                               originating_turn=trunk_of(brain, parent)["originating_turn"],
                               question="Finished. Pursue, keep deferred or dismiss each.")
    return cid, ordinary, offer["expectation"], offer["turn"], asked


def _choose(card, label, chosen="One answer chosen"):
    """Pick `label` and wait until the card has drawn the choice. A card re-reads its asks
    every few seconds and may be drawn again in between, so the pick is made again until it
    holds."""
    for _ in range(4):
        card.locator(".rb-dec-option", has_text=label).first.click()
        try:
            card.locator(".rb-form-status", has_text=chosen).wait_for(timeout=3000)
            return
        except Exception:                                 # noqa: BLE001 -- drawn again
            continue
    raise AssertionError(f"the card never drew the choice {label!r}")


def _card(page, words):
    card = page.locator(".rb-form", has=page.get_by_text(words, exact=False)).filter(
        has=page.locator(".rb-dec-foot")).first
    card.wait_for(timeout=15000)
    return card


def test_continue_is_offered_only_where_answering_does_not_already_start_work(world):
    playwright = pytest.importorskip("playwright.sync_api")
    cid, ordinary, offered, offer_turn, asked_turn = _decisions(world)
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(world["base"] + f"/fluid?c={cid}")
            # each card is read only once it has drawn the choice: the footer's
            # status says so, and the buttons are drawn with it
            plain = _card(page, "Drop one")
            _choose(plain, "Drop one")
            assert plain.locator(".rb-dec-foot button").all_inner_texts() == [
                "Leave open", "Decide + continue with @Coach", "Decide"]
            found = _card(page, "Pursue: Reconcile the base branch")
            _choose(found, "Pursue: Reconcile the base branch")
            assert found.locator(".rb-dec-foot button").all_inner_texts() == ["Leave open", "Decide"]
            assert errors == []
        finally:
            browser.close()
