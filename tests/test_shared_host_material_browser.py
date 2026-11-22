"""THE SAME GUARD WHEREVER THE DECISION FORM IS DRAWN -- in real Chrome.

The seam review finding F2 (ent-4ca09a1119c8) left open, disclosed in the
correction's return (ent-3ebadb3452fb) and asked for by the owner
(ent-6f6d22b5c962: a decision missing essential information requires
clarification rather than displaying an ambiguous approval).

At 9c993a3b the choices of an `artifact_approval` whose one exact record is not
in the Brain were withheld only where the HOST resolved that id -- Quiet Chat's
Needs you. The same shared form (`experimental/types/decision.tsx`) drawn in
Fluid's conversation column, on a post, in the thread sheet, full screen and in
governance's asks resolved nothing, so nothing was claimed and Approve was still
a control. The form now reads it for itself, through the same server read
(`GET /fluid/api/needs-you/about?ids=`, `experimental/materialStanding.ts`).

What is checked here, in Fluid -- a host that resolves no references at all,
and the one the seam was open in:

  present / missing     a record this Brain holds keeps every control and is
                        answered by choosing; one it does not hold is wording
  delayed               while the read is on its way, nothing is offered and
                        NOTHING IS CLAIMED about the reference
  failed                the same, with what became of the read
  another Brain         the same, with the way back
  ordinary / permission every control, and no read made at all
  keyboard              the ways out are reachable; no recorded choice is

The two approvals are answered with Python 2f3c2210's own payload for them
(`correction_cases` in the fixture, with that server's own resolution of each
declared reference); the rest of the wire is this server's. Acceptance against
the actual pinned Python, with nothing replayed, is `f2_hosts_accept.py` run
from the pinned clone.

Build apps/fluid-web first; opt in with MENTIS_QUIET_BROWSER=1.
"""

from __future__ import annotations

import json
import os

from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import _coordinator, a_conversation, world  # noqa: F401
from tests.conftest import owner_headers
from tests.test_needs_decision_presentation_browser import (
    BECAUSE, CORRECT, OPERATION, SCOPE_Q,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

ABOUT = "**/fluid/api/needs-you/about*"
DECISIONS = "**/fluid/api/decisions*"
APPROVALS = ("required_material_unavailable", "required_material_available")


@pytest.fixture()
def chrome():
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


def _conversation(world, name, mark):  # noqa: F811
    """A conversation Fluid draws, with the one helper each of these needs: a
    decision form on its own post, recorded through the trusted historical
    constructor as the suites beside this one record them."""
    from mentis.worker import _decision_form
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = a_conversation(world, name)
    coach, parent, _grant = _coordinator(world, cid)
    request_turn = cv._act(parent)["turn"]

    def act(kind, **kw):
        kw.setdefault("caused_by", parent)
        return cv.record_act(actor=coach, act=kind, execution=mark, runtime="claude", **kw)

    def form(_words, question, **kw):
        # ON THE REQUEST'S OWN POST, which is the place the constructor allows
        # and the post Fluid's column draws: every form here is answered there,
        # one card each, exactly as a run's questions arrive on it.
        return _decision_form(
            cv, {"because": question["because"], "questions": [question], "on": request_turn},
            actor=coach, parent=parent, here=cid, wrote=None, act=act, where=lambda c: c,
            execution=mark, **kw)

    return cid, cv, coach, request_turn, form, act


def _permission(cv, coach, cid, request_turn, parent_mark, form):
    """A system-produced permission form, whose authority is the operation it
    displays: it declares no approval of exact material and must keep every
    control it has."""
    run = cv.record_act(actor=coach, act="execution-started", conversation=cid, turn=request_turn,
                        execution=parent_mark, runtime="claude", because="fixture run")
    return form("The run waits for permission to read the fixture report.",
                {"question": "Allow reading the fixture build report?",
                 "because": "The run waits for permission to inspect the fixture report.",
                 "options": [{"label": "Allow once", "consequence": "Only this operation; the next one is asked again."},
                             {"label": "Deny", "consequence": "Refuse this operation; the agent is told."}]},
                form_detail={"permission": True, "run": run,
                             "tool": {"title": OPERATION["summary"], "kind": "execute"},
                             "operation": OPERATION})


def build(world):  # noqa: F811
    """One conversation holding, side by side: the approval of one exact record
    this Brain does NOT hold, the same approval naming one it does, an ordinary
    sufficient question, and a system-produced permission form."""
    cid, cv, coach, request_turn, form, _act = _conversation(world, "The same form, every host", "inst-f2seam")
    out = {"cid": cid}
    out["held"] = cv.say(cid, coach, [text("Candidate design: fixture v1.\n\nBuild only; no deployment.")])
    for name in APPROVALS:
        src = CORRECT[name]["expectation"]
        f = form("Decide the fixture candidate design.",
                 {k: src[k] for k in ("question", "because", "options")})
        out[name] = f["form"]
        out[name + "_question"] = f["questions"][0]["expectation"]
    enough = form("Which first-release scope?", {**SCOPE_Q[1], "because": BECAUSE})
    out["enough"] = enough["form"]
    out["permission"] = _permission(cv, coach, cid, request_turn, "inst-f2seam-perm", form)["form"]
    # a run raising ANOTHER question on this same post later, which is what
    # makes Fluid draw the post's forms again (`fluid/conversation/Decisions`)
    out["another"] = lambda: form("Which first-release scope?", {**SCOPE_Q[1], "because": BECAUSE})["form"]
    return out


#: the server's own per-item failure envelope, word for word as `about()`
#: writes it on an otherwise successful answer (`mentis/fluid/inspect.py`)
ITEM_ERROR = "what this request is about could not be read (RuntimeError)"


def _hurt(item, qid, how):
    """ONE QUESTION'S OWN ITEM OF AN ANSWER THAT SUCCEEDED, as it comes back
    when the server could not read that question, does not project what each
    question declares, or resolved something other than the declared id."""
    if not how:
        return item
    if how == "item_error":
        return {"id": qid, "error": ITEM_ERROR}
    if how == "no_projection":
        item.pop("question_references", None)
        return item
    primary = (item.get("question_references") or [{}])[0].get("primary") or {}
    if how == "no_resolution":
        primary.pop("availability", None)
    elif how == "other_id":
        primary.setdefault("availability", {})["id"] = "ent-someotherrecord"
    elif how == "gone":
        primary.get("availability", {}).update(
            state="deleted", available=False, opens=None,
            why="It was deleted; the record keeps that it was.")
    return item


def _pinned(context, w, wire=None):
    """Each approval answered as Python 2f3c2210 answered it, and -- on the
    about read -- that server's own resolution of the exact record each names,
    keyed by THIS Brain's expectation id. The available one is re-keyed to a
    post this Brain really holds, so what is replayed is the pinned server's
    shape and not its Brain's contents.

    THE AVAILABLE ONE DECLARES AND RESOLVES THE SAME ID. The pinned payload
    names that Brain's own post; both the question's declaration and the
    read's resolution of it are re-keyed to a post THIS Brain holds, so the
    control really is an exact record resolved as there -- not an id nothing
    resolved, which is a different case and is checked in the unit tests.

    `wire` is how the about read itself behaves: nothing (answer it), `hang`
    (never answer it, which is the read still on its way), `fail`, or
    `brain_for` -- another Brain named on the one read that asks for that
    question. Nothing else on the wire is touched.

    `hurt` is what ONE question's own item of an otherwise successful HTTP 200
    comes back as, by that question's id (review findings B1 and B2). Each is a
    shape the server itself produces or a server that does not project; none of
    them is an error status, and the rest of the answer is untouched:
      item_error      the API's own per-item failure envelope
                      (`mentis/fluid/inspect.py` about(): HTTP 200, `error`)
      no_projection   a server that projects no `question_references` at all,
                      which the Python bundled at this UI commit does not
      no_resolution   the question's declaration, named without `availability`
      other_id        a resolution of an id other than the declared one
      gone            the exact record, resolved as deleted: the material
                      changing after a read already said it was there"""
    wire = wire or {}
    status, refs = {}, {}
    for name in APPROVALS:
        qid = w.get(name + "_question")
        if not qid:
            continue
        src = json.loads(json.dumps(CORRECT[name]["expectation"]))
        declared = json.loads(json.dumps(CORRECT[name]["question_reference"]))
        declared["expectation"] = qid
        if name == "required_material_available":
            src["presentation"]["primary"]["id"] = w["held"]
            declared["presentation"]["primary"]["id"] = w["held"]
            declared["primary"]["id"] = w["held"]
            declared["primary"]["availability"]["id"] = w["held"]
            declared["primary"]["availability"]["post"] = w["held"]
        status[qid] = src
        refs[qid] = declared

    def put(d, key):
        src = status.get(key)
        if not src:
            return
        if "presentation" in src:
            d["presentation"] = src["presentation"]
        d["presentation_status"] = src["presentation_status"]

    def decisions(route):
        res = route.fetch()
        try:
            body = res.json()
        except Exception:                                   # noqa: BLE001
            return route.fulfill(response=res)
        for f in body.get("decision_forms") or ():
            for q in f.get("questions") or ():
                put(q, q.get("expectation"))
        for e in body.get("expectations") or ():
            put(e, e.get("id"))
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def about(route):
        if wire.get("hang"):
            return                                          # never answered: the read is on its way
        if wire.get("fail"):
            return route.fulfill(status=500, content_type="application/json",
                                 body=json.dumps({"error": "the fixture server refused this read"}))
        res = route.fetch()
        try:
            body = res.json()
        except Exception:                                   # noqa: BLE001
            return route.fulfill(response=res)
        items = []
        for item in body.get("about") or ():
            qid = item.get("id")
            declared = refs.get(qid)
            if declared:
                item["question_references"] = [json.loads(json.dumps(declared))]
            items.append(_hurt(item, qid, (wire.get("hurt") or {}).get(qid)))
        body["about"] = items
        for qid, brain in (wire.get("brain_for") or {}).items():
            if qid in route.request.url:
                body["brain"] = brain
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context.route(DECISIONS, decisions)
    context.route(ABOUT, about)


class Fluid:
    """Fluid's conversation column on this conversation, as the owner. Fluid
    resolves no references for the decision form: it is exactly the host the
    seam was open in."""

    def __init__(self, browser, world, w, wire=None, width=1280, height=1000):  # noqa: F811
        self.w = w
        self.asked: list[str] = []
        self.sent: list[str] = []
        self.context = browser.new_context(viewport={"width": width, "height": height})
        self.context.set_extra_http_headers(owner_headers())
        self.page = self.context.new_page()
        self.errors: list[str] = []
        self.answered: list[int] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("request", lambda r: self.asked.append(r.url)
                     if "/needs-you/about" in r.url else None)
        self.page.on("response", lambda r: self.answered.append(r.status)
                     if "/needs-you/about" in r.url else None)
        self.page.on("request", lambda r: self.sent.append(r.post_data or "")
                     if r.method == "POST" and "/turns" in r.url else None)
        self.at = world["base"] + f"/fluid?c={w['cid']}"
        _pinned(self.context, w, wire)
        self.page.goto(self.at)

    def rewire(self, wire=None):
        """The about read answers otherwise from now on, and the page is read
        again from the start: what the read says then is all that is read."""
        self.reroute(wire)
        self.page.goto(self.at)

    def reroute(self, wire=None):
        """THE MATERIAL CHANGES WHILE THE PAGE STAYS AS IT IS: the about read
        answers otherwise from now on, and NOTHING is reloaded, remounted or
        told. Whatever the page still shows is what it read before."""
        self.context.unroute(ABOUT)
        self.context.unroute(DECISIONS)
        _pinned(self.context, self.w, wire)

    def question(self, form, qid=None):
        card = self.page.locator(f"[data-decision-form='{form}']").first
        card.wait_for(timeout=30000)
        card.evaluate("el => el.scrollIntoView({block: 'center'})")
        q = card.locator(f".rb-dec-q[data-question='{qid}']" if qid else ".rb-dec-q").first
        q.wait_for(timeout=20000)
        return card, q

    def close(self):
        self.context.close()
        assert self.errors == []


def _gaps(q):
    return [x.inner_text() for x in q.locator("[data-dec-gap]").all()]


def text_of(world, turn):  # noqa: F811
    """What the recorded reply actually says, read back from the Brain."""
    from mentis.conversation.versions import flow_text
    post = (world["cv"].corpus.read([turn]) or [None])[0] or {}
    return flow_text(((post.get("body") or {}).get("parts")) or [])


def _nothing_sends(f, card):
    """No path records a choice: not the wording, not Decide, not a forced
    Decide, and "+ continue" is not offered at all."""
    wording = card.locator("[data-wording-only]").first
    assert wording.locator("[role='radio'], button, input").count() == 0
    wording.locator(".rb-dec-option").first.click()
    assert card.locator(".rb-dec-foot .btn.primary").is_disabled()
    assert card.locator(".rb-dec-foot button", has_text="+ continue").count() == 0
    card.locator(".rb-dec-foot .btn.primary").evaluate("el => { el.disabled = false; el.click() }")
    f.page.wait_for_timeout(400)
    assert f.sent == [], f.sent


def _claims_nothing(said):
    """The page said what became of its OWN read, and nothing whatever about
    the record the question names."""
    assert said and "the exact candidate design" in said[0], said
    assert "not established yet" in said[0], said
    assert "Nothing here says this Brain does or does not hold it" in said[0], said
    for word in ("holds nothing", "deleted", "permanently deleted", "missing"):
        assert word not in said[0], (word, said[0])


def test_a_required_exact_record_the_brain_does_not_hold_offers_no_affirmative(chrome, world):  # noqa: F811
    """THE FINDING ITSELF, in the host it was open in. Fluid's conversation
    column resolves no references; the form reads the declared record for
    itself, and an approval of material nobody can look at offers no choice.

    The control beside it -- the same question naming a record this Brain holds
    -- keeps every control it had and is still answered by choosing."""
    w = build(world)
    f = Fluid(chrome, world, w)
    try:
        qid = w["required_material_unavailable_question"]
        card, asked = f.question(w["required_material_unavailable"], qid)
        # the question itself records everything the contract asks of it
        assert asked.get_attribute("data-presentation") == "complete"
        note = asked.locator("[data-clarify-needed]")
        note.wait_for(timeout=30000)
        # and it is the RECORD'S own statement, not an unfinished read
        for _ in range(60):
            if note.get_attribute("data-clarify-needed") == "record":
                break
            f.page.wait_for_timeout(250)
        assert note.get_attribute("data-clarify-needed") == "record"
        said = _gaps(asked)
        assert said and "the exact candidate design" in said[0], said
        assert "This Brain holds nothing with this id." in said[0], said
        for g in said:
            assert "presentation." not in g, g
        assert asked.locator("[data-option='0'][role='radio']").count() == 0
        assert asked.locator("[data-wording-only]").get_attribute("data-wording-only") == "2"
        _nothing_sends(f, card)
        assert world["cv"].expectation_state(qid)["response_present"] is False
        # the ways out are untouched
        assert asked.locator("[data-option='own']").count() == 1
        assert "Withdraw with a clarification reason" in asked.inner_text()
        # and nothing was substituted for the id the question declared
        assert card.locator("[data-primary='ref']").count() == 1

        # THE CONTROL: the same approval, naming a record this Brain holds.
        avail = w["required_material_available_question"]
        other, enough = f.question(w["required_material_available"], avail)
        enough.locator("[data-option='0'][role='radio']").wait_for(timeout=30000)
        assert enough.locator("[data-clarify-needed]").count() == 0
        assert _gaps(enough) == [], _gaps(enough)
        for i, label in enumerate(("Build this design", "Revise first")):
            control = enough.locator(f"[data-option='{i}'][role='radio']")
            assert control.count() == 1 and control.is_enabled()
            assert label in control.inner_text()
        pick = enough.locator("[data-option='0']")
        for _ in range(6):
            if pick.get_attribute("aria-checked") == "true":
                break
            pick.click()
            f.page.wait_for_timeout(300)
        other.locator(".rb-dec-foot .btn.primary").click()
        cv = world["cv"]
        for _ in range(80):
            if cv.expectation_state(avail)["answer"]:
                break
            f.page.wait_for_timeout(250)
        answer = cv.expectation_state(avail)["answer"]
        assert answer, "an approval whose exact material is there is still answered by choosing"
        assert (answer["option"], answer["label"]) == (0, "Build this design"), answer
    finally:
        f.close()


@pytest.mark.parametrize("how,said", [
    ("item_error", "could not say how this question stands"),
    ("no_projection", "did not say which exact thing"),
    ("no_resolution", "without saying how it stands"),
    ("other_id", "a different record"),
])
def test_a_read_that_answered_without_establishing_this_question_is_not_an_answer(chrome, world, how, said):  # noqa: F811
    """REVIEW FINDING B1. An answer that ARRIVED is not an answer FOR a question
    it established nothing for. Each of these is a successful HTTP 200 whose own
    per-question content establishes nothing: the server's own per-item failure
    envelope, a server that projects no question references at all, a
    declaration named without its resolution, and a resolution of some other id.

    None of them may become an offered choice, and NONE OF THEM MAY BE SAID AS
    THE RECORD BEING MISSING: what is said is what became of the read.

    On the approval naming a record this Brain DOES hold, so that nothing but
    the read's own shortfall can be what withholds the choices."""
    w = build(world)
    avail = w["required_material_available_question"]
    f = Fluid(chrome, world, w, wire={"hurt": {avail: how}})
    try:
        card, asked = f.question(w["required_material_available"], avail)
        asked.locator("[data-clarify-needed='pending']").wait_for(timeout=40000)
        # the read ANSWERED, and answered 200: this is not a failed read
        assert f.answered and set(f.answered) == {200}, f.answered
        gaps = _gaps(asked)
        _claims_nothing(gaps)
        assert said in gaps[0], (said, gaps)
        assert asked.locator("[data-option='0'][role='radio']").count() == 0
        _nothing_sends(f, card)
        assert world["cv"].expectation_state(avail)["response_present"] is False
        # and the ways out are untouched
        assert asked.locator("[data-option='own']").count() == 1
        assert "Withdraw with a clarification reason" in asked.inner_text()
    finally:
        f.close()


WORDS = "I want to look at this myself before I approve anything.\n\nSecond paragraph, kept."


def _pick(f, q, which="0"):
    control = q.locator(f"[data-option='{which}']")
    for _ in range(8):
        if control.get_attribute("aria-checked") == "true":
            return control
        control.click()
        f.page.wait_for_timeout(250)
    raise AssertionError(f"could not choose {which}")


def test_material_deleted_after_the_read_is_not_approved_on_what_the_read_said_then(chrome, world):  # noqa: F811
    """REVIEW FINDING B2, AT THE SEAM THAT RECORDS SOMETHING. A read that said
    the exact material was there is not an answer about the material FOREVER:
    the thing may be deleted while the page sits open, and the page is told
    nothing. How it stands is read AGAIN at the moment a recorded choice would
    be sent, and a read that no longer establishes it sends nothing.

    Nothing is polled meanwhile, nothing is written by the re-read, and nothing
    the owner typed is lost by it."""
    w = build(world)
    avail = w["required_material_available_question"]
    cv = world["cv"]
    f = Fluid(chrome, world, w)
    try:
        card, asked = f.question(w["required_material_available"], avail)
        asked.locator("[data-option='0'][role='radio']").wait_for(timeout=30000)
        # the owner's own words, then a recorded choice: both are in hand
        _pick(f, asked, "own")
        asked.locator("textarea").first.fill(WORDS)
        _pick(f, asked, "0")
        reads = len(f.asked)

        # THE MATERIAL IS DELETED. Nothing whatever tells the page.
        f.reroute(wire={"hurt": {avail: "gone"}})
        f.page.wait_for_timeout(1200)
        assert len(f.asked) == reads, "nothing polls: no read is made until something asks for one"
        assert asked.locator("[data-option='0'][role='radio']").count() == 1, "and the page still shows what it read"

        # DECIDE READS IT AGAIN, AND SENDS NOTHING
        card.locator(".rb-dec-foot .btn.primary").click()
        asked.locator("[data-clarify-needed='record']").wait_for(timeout=30000)
        assert len(f.asked) > reads, "the material was read again at the moment of sending"
        assert f.sent == [], f.sent
        assert cv.expectation_state(avail)["response_present"] is False
        failed = asked.locator(".rb-form-failed")
        assert failed.count() == 1 and "not sent" in failed.inner_text().lower(), failed.inner_text()
        assert "It was deleted" in _gaps(asked)[0], _gaps(asked)
        assert asked.locator("[data-option='0'][role='radio']").count() == 0
        _nothing_sends(f, card)

        # AND NOTHING OF THE OWNER'S WAS LOST BY ANY OF IT
        _pick(f, asked, "own")
        assert asked.locator("textarea").first.input_value() == WORDS
    finally:
        f.close()


def test_a_form_drawn_again_reads_the_material_again_and_the_later_answer_is_its_own(chrome, world):  # noqa: F811
    """REVIEW FINDING B2, IN THE LIFECYCLE. What the form read is not kept past
    the drawing it was read for. A run raising another question on this post
    makes Fluid draw the post's forms again; the approval is read again and what
    the material changed to is what it is drawn against -- without a reload.

    AND A LATER ANSWER IS STILL AN ANSWER: the owner's own words close the
    question, recorded under the original expectation with no option and no
    label, because what was withheld was only the choice nobody could read."""
    w = build(world)
    avail = w["required_material_available_question"]
    cv = world["cv"]
    f = Fluid(chrome, world, w)
    try:
        card, asked = f.question(w["required_material_available"], avail)
        asked.locator("[data-option='0'][role='radio']").wait_for(timeout=30000)
        _pick(f, asked, "0")

        # the material is deleted, and then the post is drawn again
        f.reroute(wire={"hurt": {avail: "gone"}})
        raised = w["another"]()
        f.page.locator(f"[data-decision-form='{raised}']").wait_for(timeout=40000)

        card, asked = f.question(w["required_material_available"], avail)
        asked.locator("[data-clarify-needed='record']").wait_for(timeout=40000)
        assert "It was deleted" in _gaps(asked)[0], _gaps(asked)
        assert asked.locator("[data-option='0'][role='radio']").count() == 0
        _nothing_sends(f, card)
        assert cv.expectation_state(avail)["response_present"] is False

        # THE LATER ANSWER: the owner's own words still close it
        _pick(f, asked, "own")
        asked.locator("textarea").first.fill(WORDS)
        card.locator(".rb-dec-foot .btn.primary").click()
        for _ in range(80):
            if cv.expectation_state(avail)["answer"]:
                break
            f.page.wait_for_timeout(250)
        answer = cv.expectation_state(avail)["answer"]
        assert answer, "own words are never withheld by how the material stands"
        assert answer.get("option") is None and answer.get("label") is None, answer
        assert answer.get("words") is True, answer
        said = text_of(world, answer["reply"])
        assert WORDS.split("\n")[0] in said, said
    finally:
        f.close()


def test_an_attempted_choice_is_not_sent_again_on_a_read_that_no_longer_holds(chrome, world):  # noqa: F811
    """REVIEW FINDING B2, AT THE RETRY SEAM. An answer whose outcome is unknown
    goes again under the SAME key -- but a recorded choice is read for again
    first, exactly as Decide is. A read that no longer establishes the material
    holds it: no second request is made, the key is not spent, and the words
    and both reads stay exactly as they were."""
    w = build(world)
    avail = w["required_material_available_question"]
    cv = world["cv"]
    f = Fluid(chrome, world, w)
    try:
        card, asked = f.question(w["required_material_available"], avail)
        asked.locator("[data-option='0'][role='radio']").wait_for(timeout=30000)
        _pick(f, asked, "0")
        # THE ANSWER IS ATTEMPTED AND ITS OUTCOME IS NEVER KNOWN
        f.context.route("**/turns*", lambda route: route.abort()
                        if route.request.method == "POST" else route.continue_())
        card.locator(".rb-dec-foot .btn.primary").click()
        again = asked.locator("[data-resend]")
        again.wait_for(timeout=30000)
        attempts = len(f.sent)
        assert attempts == 1, f.sent

        # and THEN the material is deleted
        f.reroute(wire={"hurt": {avail: "gone"}})
        again.click()
        asked.locator("[data-resend-held]").wait_for(timeout=30000)
        f.page.wait_for_timeout(600)
        assert len(f.sent) == attempts, "it was not sent again"
        assert asked.locator("[data-resend]").count() == 0, "and it is not offered again either"
        assert cv.expectation_state(avail)["response_present"] is False
        assert "Check again" in asked.inner_text()
    finally:
        f.close()


def test_a_read_still_on_its_way_offers_nothing_yet_and_claims_nothing(chrome, world):  # noqa: F811
    """PENDING IS NOT AN ANSWER. While the form's own read of the exact material
    is on its way, no choice of either approval is offered -- and nothing
    whatever is said about either reference: not that it is there, and not that
    it is gone. When the read does answer, what it answered is the only thing
    read: the available one gains its controls, the absent one is said to be
    absent."""
    w = build(world)
    f = Fluid(chrome, world, w, wire={"hang": True})
    try:
        for which in APPROVALS:
            qid = w[which + "_question"]
            card, asked = f.question(w[which], qid)
            note = asked.locator("[data-clarify-needed='pending']")
            note.wait_for(timeout=30000)
            assert "not established here yet" in note.inner_text()
            assert "Nothing here says that thing is missing from this Brain" in note.inner_text()
            said = _gaps(asked)
            _claims_nothing(said)
            assert "still being read" in said[0], said
            assert asked.locator("[data-option='0'][role='radio']").count() == 0
            _nothing_sends(f, card)
            assert world["cv"].expectation_state(qid)["response_present"] is False
            # the ways out are offered meanwhile
            assert asked.locator("[data-option='own']").count() == 1
            assert "Withdraw with a clarification reason" in asked.inner_text()

        # AND WHEN IT ANSWERS, WHAT IT ANSWERED IS THE ONLY THING READ
        f.rewire()
        avail = w["required_material_available_question"]
        _, enough = f.question(w["required_material_available"], avail)
        enough.locator("[data-option='0'][role='radio']").wait_for(timeout=40000)
        assert enough.locator("[data-clarify-needed]").count() == 0
        assert _gaps(enough) == [], _gaps(enough)
        _, absent = f.question(w["required_material_unavailable"],
                               w["required_material_unavailable_question"])
        absent.locator("[data-clarify-needed='record']").wait_for(timeout=40000)
        assert "This Brain holds nothing with this id." in _gaps(absent)[0], _gaps(absent)
    finally:
        f.close()


def test_a_read_that_failed_says_what_became_of_it_and_claims_nothing(chrome, world):  # noqa: F811
    """A READ THAT DID NOT FINISH IS NOT AN ANSWER EITHER. The page says what
    became of its own read, in its own words, and says nothing at all about the
    record -- it never becomes "this Brain does not hold it"."""
    w = build(world)
    f = Fluid(chrome, world, w, wire={"fail": True})
    try:
        avail = w["required_material_available_question"]
        card, asked = f.question(w["required_material_available"], avail)
        asked.locator("[data-clarify-needed='pending']").wait_for(timeout=30000)
        said = _gaps(asked)
        _claims_nothing(said)
        assert "refused" in said[0] or "500" in said[0], said
        assert asked.locator("[data-option='0'][role='radio']").count() == 0
        _nothing_sends(f, card)
        assert world["cv"].expectation_state(avail)["response_present"] is False
        assert asked.locator("[data-option='own']").count() == 1
    finally:
        f.close()


def test_a_read_answered_for_another_brain_is_used_for_nothing(chrome, world):  # noqa: F811
    """ONE BRAIN. The reader is bound by its first answer; a later answer naming
    another Brain means the server now serves a different one, and then NOTHING
    it read is current -- not the later answer and not the earlier one. A form is
    never drawn against one Brain's resolution of another's id, and the way back
    is said."""
    w = build(world)
    other = {"corpus_id": "another-brain", "instance": "elsewhere"}
    f = Fluid(chrome, world, w, wire={"brain_for": {w["required_material_available_question"]: other}})
    try:
        for which in APPROVALS:
            card, asked = f.question(w[which], w[which + "_question"])
            note = asked.locator("[data-clarify-needed='pending']")
            note.wait_for(timeout=40000)
            said = _gaps(asked)
            _claims_nothing(said)
            assert "another Brain" in said[0] and "reload the page" in said[0], said
            assert asked.locator("[data-option='0'][role='radio']").count() == 0
            _nothing_sends(f, card)
            assert world["cv"].expectation_state(w[which + "_question"])["response_present"] is False
    finally:
        f.close()


def test_an_ordinary_decision_and_a_permission_keep_every_control_and_read_nothing(chrome, world):  # noqa: F811
    """NOTHING OPTIONAL AND NO ACTION REFERENCE IS READ AS REQUIRED. An ordinary
    choice between alternatives and a system-produced permission form declare no
    approval of one exact record, so the form reads nothing for them at all:
    every control they had, and no read made.

    On a conversation holding only those two, so the count is theirs."""
    cid, cv, coach, request_turn, form, _act = _conversation(world, "Nothing to read", "inst-f2plain")
    plain = form("Which first-release scope?", {**SCOPE_Q[1], "because": BECAUSE})
    perm = _permission(cv, coach, cid, request_turn, "inst-f2plain-perm", form)
    f = Fluid(chrome, world, {"cid": cid})
    try:
        _, ordinary = f.question(plain["form"])
        ordinary.locator("[data-option='0'][role='radio']").wait_for(timeout=30000)
        assert ordinary.locator("[data-clarify-needed]").count() == 0
        assert _gaps(ordinary) == [], _gaps(ordinary)
        # two recorded choices, the owner's own words, and the withdrawal
        assert ordinary.locator("[role='radio']").count() == 4

        _, allow = f.question(perm["form"])
        allow.locator("[data-option='0'][role='radio']").wait_for(timeout=30000)
        assert allow.locator("[data-clarify-needed]").count() == 0
        assert _gaps(allow) == [], _gaps(allow)
        assert "Allow once" in allow.locator("[data-option='0']").inner_text()
        assert allow.locator("[data-option='1'][role='radio']").count() == 1

        f.page.wait_for_timeout(1500)
        assert f.asked == [], f.asked
    finally:
        f.close()


def test_the_ways_out_are_reachable_by_keyboard_and_no_recorded_choice_is(chrome, world):  # noqa: F811
    """KEYBOARD, AND A NARROW SCREEN. Where the choices are wording they are
    outside the radiogroup: no key reaches them, the ways out are each one arrow
    away, and the recorded wording is read in full by anyone reading the page."""
    w = build(world)
    f = Fluid(chrome, world, w, width=380, height=900)
    try:
        qid = w["required_material_unavailable_question"]
        card, asked = f.question(w["required_material_unavailable"], qid)
        asked.locator("[data-clarify-needed='record']").wait_for(timeout=40000)
        radios = asked.locator("[role='radio']")
        assert radios.count() == 2, radios.all_inner_texts()
        assert [r.get_attribute("data-option") for r in radios.all()] == ["own", "withdraw"]
        wording = asked.locator("[data-wording-only]")
        assert wording.locator("[role='radio'], button, input").count() == 0
        assert "Build this design" in wording.inner_text()

        asked.locator("[data-option='own']").focus()
        # one tab stop, arrows move: the two ways out, and nothing else
        f.page.keyboard.press("ArrowDown")
        assert asked.locator("[data-option='own']").get_attribute("aria-checked") == "true"
        f.page.keyboard.press("ArrowDown")
        assert asked.locator("[data-option='withdraw']").get_attribute("aria-checked") == "true"
        f.page.keyboard.press("ArrowDown")
        assert asked.locator("[data-option='own']").get_attribute("aria-checked") == "true"
        f.page.keyboard.press("ArrowUp")
        assert asked.locator("[data-option='withdraw']").get_attribute("aria-checked") == "true"
        # no arrow ever lands on a recorded choice, and nothing was sent
        assert asked.locator("[data-option='0'][aria-checked='true']").count() == 0
        f.page.wait_for_timeout(300)
        assert f.sent == [], f.sent
        assert world["cv"].expectation_state(qid)["response_present"] is False
        assert f.page.evaluate(
            "() => { const f = document.querySelector('.rb-form'); const d = document.scrollingElement;"
            " return [f.scrollWidth - f.clientWidth, d.scrollWidth - d.clientWidth] }") == [0, 0]
    finally:
        f.close()
