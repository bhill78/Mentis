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
    # and an ordinary reply to the asking post, which is what gives that post
    # its everyday "N replies" control: opening that thread draws the post --
    # and so every form on it -- A SECOND TIME, in the same page
    out["asking_post"] = request_turn
    out["reply"] = lambda: cv.say(cid, coach, [text("Looking at the candidate now.")],
                                  replies_to=request_turn)
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


class Caught:
    """ABOUT READS CAUGHT ON THE WAY OUT AND LET GO BY HAND, which is the only
    way TWO readings of the same question -- one per drawing of the one form --
    are on their way at the same moment, and are finished in a chosen order.

    Nothing about the read is otherwise touched: when one is let go it is
    answered exactly as the server would have answered it at that moment, by
    the wire as it stands then. Review finding R1 on B2 (ent-f863f84301fc)."""

    def __init__(self):
        self.on = False
        self.waiting: list = []
        self.reply = None                 # how the wire answers one, now

    def let_go(self, i):
        self.reply(self.waiting.pop(i))


def _pinned(context, w, wire=None, caught=None):
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
    # KEPT, NOT COPIED: a case that changes the material under a read already
    # on its way changes this very dict, and the answer is built when the read
    # is answered -- not when the route was set
    wire = {} if wire is None else wire
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

    def answered(route):
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

    def about(route):
        # caught, and answered later by this same wire, or answered now
        if caught is not None and caught.on:
            return caught.waiting.append(route)
        return answered(route)

    if caught is not None:
        caught.reply = answered
    context.route(DECISIONS, decisions)
    context.route(ABOUT, about)


class Fluid:
    """Fluid's conversation column on this conversation, as the owner. Fluid
    resolves no references for the decision form: it is exactly the host the
    seam was open in."""

    def __init__(self, browser, world, w, wire=None, width=1280, height=1000):  # noqa: F811
        self.w = w
        #: how the about read answers, read at the moment it answers: the
        #: material can change under a read already on its way by changing this
        self.wire = dict(wire or {})
        self.caught = Caught()
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
        _pinned(self.context, w, self.wire, self.caught)
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
        self.wire = dict(wire or {})
        _pinned(self.context, self.w, self.wire, self.caught)

    def catching(self, on=True):
        """From here, about reads are caught and not answered until they are
        let go of, one by one."""
        self.caught.on = on

    def waiting_for(self, n, ms=12000):
        """Wait until exactly `n` reads are caught and unanswered."""
        for _ in range(ms // 100):
            if len(self.caught.waiting) >= n:
                break
            self.page.wait_for_timeout(100)
        assert len(self.caught.waiting) == n, (
            f"{len(self.caught.waiting)} reads caught, expected {n}")

    def let_go(self, i=0):
        """One caught read is answered, as the wire answers it NOW."""
        self.caught.let_go(i)
        self.page.wait_for_timeout(900)

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


def test_an_unestablished_read_leaves_the_ways_out_reachable_on_a_narrow_screen(chrome, world):  # noqa: F811
    """AND THE SAME ON A NARROW SCREEN, BY KEYBOARD. Where an answer that
    established nothing withholds the choices, those choices are wording
    outside the radiogroup: no arrow reaches one, the two ways out are each one
    arrow away, the recorded wording is still read in full, and the form at
    380px has nothing to scroll sideways."""
    w = build(world)
    avail = w["required_material_available_question"]
    f = Fluid(chrome, world, w, wire={"hurt": {avail: "item_error"}}, width=380, height=900)
    try:
        card, asked = f.question(w["required_material_available"], avail)
        asked.locator("[data-clarify-needed='pending']").wait_for(timeout=40000)
        radios = asked.locator("[role='radio']")
        assert [r.get_attribute("data-option") for r in radios.all()] == ["own", "withdraw"]
        wording = asked.locator("[data-wording-only]")
        assert wording.locator("[role='radio'], button, input").count() == 0
        assert "Build this design" in wording.inner_text()

        asked.locator("[data-option='own']").focus()
        f.page.keyboard.press("ArrowDown")
        assert asked.locator("[data-option='own']").get_attribute("aria-checked") == "true"
        f.page.keyboard.press("ArrowDown")
        assert asked.locator("[data-option='withdraw']").get_attribute("aria-checked") == "true"
        f.page.keyboard.press("ArrowDown")
        assert asked.locator("[data-option='own']").get_attribute("aria-checked") == "true"
        assert asked.locator("[data-option='0'][aria-checked='true']").count() == 0
        f.page.wait_for_timeout(300)
        assert f.sent == [], f.sent
        assert world["cv"].expectation_state(avail)["response_present"] is False
        assert f.page.evaluate(
            "() => { const f = document.querySelector('.rb-form'); const d = document.scrollingElement;"
            " return [f.scrollWidth - f.clientWidth, d.scrollWidth - d.clientWidth] }") == [0, 0]
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


def _both_drawings(f, w, form, qid):
    """THE SAME QUESTION, DRAWN TWICE IN ONE PAGE, by the ordinary way there:
    an everyday reply gives the asking post its "N replies" control, and that
    control opens the post's own thread -- which draws the post, and so every
    form on it, a second time. Both drawings read for ONE set, which is what
    makes two readings of it supersede each other."""
    w["reply"]()
    chip = f.page.locator("[data-act=replies]").first
    chip.wait_for(timeout=60000)
    chip.click()
    post = f.page.locator(f".fx-conv-scroll [data-decision-form='{form}']").first
    thread = f.page.locator(f".fw-thread [data-decision-form='{form}']").first
    thread.wait_for(timeout=30000)
    for drawing in (post, thread):
        drawing.locator(f".rb-dec-q[data-question='{qid}'] [data-option='0'][role='radio']").first.wait_for(timeout=30000)
    return post, thread


def _said_in(drawing):
    return drawing.locator(".rb-form-failed").first.inner_text()


#: which of the two readings answers first. Both orders are driven: the one
#: that leaves the earlier reading holding only what was read before it began,
#: and the one that leaves it a LATER read's answer, which is an answer for it.
ORDERS = [("older first", [0, 0]), ("later first", [1, 0])]


@pytest.mark.parametrize("order,taking", ORDERS)
def test_two_drawings_reading_at_once_approve_nothing_read_before_either(chrome, world, order, taking):  # noqa: F811
    """REVIEW FINDING R1 ON B2 (ent-f863f84301fc), AT DECIDE. The form reads
    the material again before a recorded choice is sent -- but the SAME
    question is drawn in two places at once, the post and its own thread, and
    both drawings read for one set. Press Decide in both while the two reads
    are on their way, and the store keeps the later read's answer only: the
    earlier reading is left holding what was read BEFORE either of them began,
    which is the positive answer from before the material was deleted.

    That is not an answer for it, and nothing is sent on it. Nothing is
    claimed about the material by holding it either: what this page has not
    established, it does not describe."""
    w = build(world)
    avail = w["required_material_available_question"]
    form = w["required_material_available"]
    cv = world["cv"]
    f = Fluid(chrome, world, w)
    try:
        card, asked = f.question(form, avail)
        asked.locator("[data-option='0'][role='radio']").wait_for(timeout=30000)
        _pick(f, asked, "own")
        asked.locator("textarea").first.fill(WORDS)
        _pick(f, asked, "0")
        post, thread = _both_drawings(f, w, form, avail)
        reads = len(f.asked)

        # BOTH DRAWINGS READ AGAIN AT ONCE, and neither read has answered
        f.catching()
        post.locator(".rb-dec-foot .btn.primary").first.click()
        thread.locator(".rb-dec-foot .btn.primary").first.click()
        f.waiting_for(2)
        assert len(f.asked) == reads + 2, "one read per reading, and no more"
        assert f.sent == [], "and nothing is sent while they are on their way"

        # AND THE MATERIAL IS DELETED while both of them are in flight
        f.wire["hurt"] = {avail: "gone"}

        f.let_go(taking[0])
        assert f.sent == [], f.sent
        assert cv.expectation_state(avail)["response_present"] is False
        if order == "older first":
            # the superseded reading says what became of IT, and sends nothing
            said = _said_in(post)
            assert "not sent again" not in said.lower(), said
            assert "another reading of the same question" in said, said
            # and it claims NOTHING about the thing the question names
            assert "Nothing here says that thing is missing from this Brain" in said, said
            for word in ("holds nothing", "deleted", "erased"):
                assert word not in said, (word, said)
            # and nothing of the material is invented either way: this page has
            # read nothing newer than it had, and still draws what it read
            assert post.locator(f"[data-question='{avail}'] [data-option='0'][role='radio']").count() == 1

        f.let_go(taking[1])
        f.catching(False)
        assert f.sent == [], f.sent
        assert cv.expectation_state(avail)["response_present"] is False
        assert not cv.expectation_state(avail)["answer"], "nothing was recorded by either"

        # ONCE A READING'S OWN READ HAS ANSWERED, what it answered is what both
        # drawings are drawn against -- the deletion, said as the record's own
        for drawing in (post, thread):
            drawing.locator("[data-clarify-needed='record']").first.wait_for(timeout=30000)
            assert drawing.locator(f"[data-question='{avail}'] [data-option='0'][role='radio']").count() == 0
        q = post.locator(f".rb-dec-q[data-question='{avail}']").first
        assert "It was deleted" in _gaps(q)[0], _gaps(q)
        _nothing_sends(f, post)

        # AND NOTHING OF THE OWNER'S WAS LOST BY ANY OF IT
        _pick(f, q, "own")
        assert q.locator("textarea").first.input_value() == WORDS
    finally:
        f.close()


@pytest.mark.parametrize("order,taking", ORDERS)
def test_two_drawings_reading_at_once_send_nothing_again_on_what_was_read_before(chrome, world, order, taking):  # noqa: F811
    """THE SAME, AT THE RETRY SEAM. An attempted answer whose outcome is
    unknown goes again under the same key -- after the material is read for
    again. Two drawings of the question press Send again at the same moment,
    so one reading supersedes the other, and the superseded one must not send
    the attempt again on what was read before either began.

    Nothing is spent by holding it: no second request is made, the key, the
    words and the original attempt are untouched, and what is said says
    nothing about whether that attempt was recorded -- which is exactly what
    is not known."""
    w = build(world)
    avail = w["required_material_available_question"]
    form = w["required_material_available"]
    cv = world["cv"]
    f = Fluid(chrome, world, w)
    try:
        card, asked = f.question(form, avail)
        asked.locator("[data-option='0'][role='radio']").wait_for(timeout=30000)
        _pick(f, asked, "0")
        # THE ANSWER IS ATTEMPTED AND ITS OUTCOME IS NEVER KNOWN
        f.context.route("**/turns*", lambda route: route.abort()
                        if route.request.method == "POST" else route.continue_())
        card.locator(".rb-dec-foot .btn.primary").click()
        asked.locator("[data-resend]").wait_for(timeout=30000)
        attempts = len(f.sent)
        assert attempts == 1, f.sent

        w["reply"]()
        chip = f.page.locator("[data-act=replies]").first
        chip.wait_for(timeout=60000)
        chip.click()
        post = f.page.locator(f".fx-conv-scroll [data-decision-form='{form}']").first
        thread = f.page.locator(f".fw-thread [data-decision-form='{form}']").first
        thread.locator("[data-resend]").first.wait_for(timeout=30000)
        reads = len(f.asked)

        # BOTH DRAWINGS SEND AGAIN AT ONCE, and neither read has answered
        f.catching()
        post.locator("[data-resend]").first.click()
        thread.locator("[data-resend]").first.click()
        f.waiting_for(2)
        assert len(f.asked) == reads + 2, "one read per reading, and no more"
        assert len(f.sent) == attempts, "and nothing goes again while they are on their way"

        # AND THE MATERIAL IS DELETED while both of them are in flight
        f.wire["hurt"] = {avail: "gone"}

        f.let_go(taking[0])
        assert len(f.sent) == attempts, f.sent
        assert cv.expectation_state(avail)["response_present"] is False
        if order == "older first":
            landing = post.locator(".rb-dec-landing").first.inner_text()
            assert "not sent again just now" in landing, landing
            assert "another reading of the same question" in landing, landing
            # and it says nothing about what became of the attempt itself
            assert "It may or may not have been recorded" in landing, landing
            for word in ("holds nothing", "erased", "was deleted", "not recorded:"):
                assert word not in landing, (word, landing)

        f.let_go(taking[1])
        f.catching(False)
        assert len(f.sent) == attempts, "it was not sent again by either drawing"
        assert cv.expectation_state(avail)["response_present"] is False

        # ONCE A READING'S OWN READ HAS ANSWERED: held, said as F3 says it, and
        # the control is not offered again either -- the two reads still are
        for drawing in (post, thread):
            drawing.locator("[data-resend-held]").first.wait_for(timeout=30000)
            assert drawing.locator("[data-resend]").count() == 0
            assert "Check again" in drawing.inner_text()
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


# ---------------- F2: THE EXACT RECORD, OPENED FROM THE SHARED FORM ---------
# Combined review finding F2 (ent-b45998589533, report adm-44c2ee329473).
#
# The owner's requirement is that an authority-bearing question names a primary
# reference where the specific material can be INSPECTED. Quiet Chat's Needs
# you supplies the host capability that opens one; the same shared form drawn
# in Fluid supplied none, so a present, declared, resolved exact record printed
# "it cannot be opened from here; the asking post has it" and offered no
# control at all. Disclosing that is not providing it.
#
# Fluid now gives the form its own host (`fluid/present/decisionRefWords`): the
# exact id the question declared, opened by the record's own inspector in Peek
# (`brain:<entry>`), drawn OVER the workspace so the form is never unmounted.
# What is chosen and typed is therefore exactly as it was left, and closing
# returns focus to the control it was opened from.
#
# NOTHING IS INFERRED. The id opened is the declared one: never the asking
# post, never the first reference, never a title match. Where this page has no
# viewer to draw a record in, no opener is offered and the sentence stands.

#: what the record this Brain really holds says (`build`'s `held` post)
HELD_WORDS = "Candidate design: fixture v1."
#: the id the absent approval declares, which this Brain does not hold
ABSENT_ID = CORRECT["required_material_unavailable"]["expectation"]["presentation"]["primary"]["id"]


def _opener(card):
    """The one control on the question's Inspect row."""
    row = card.locator("[data-primary='ref']").first
    row.wait_for(timeout=30000)
    return row, row.locator("button[data-open-record]")


def test_the_declared_exact_record_is_opened_from_the_shared_form(chrome, world):  # noqa: F811
    """THE FINDING ITSELF. Fluid's conversation column draws the shared form;
    the Inspect row of an approval of one exact record this Brain holds carries
    a control that opens THAT id, and opening it reads the record itself."""
    w = build(world)
    f = Fluid(chrome, world, w)
    try:
        avail = w["required_material_available_question"]
        card, asked = f.question(w["required_material_available"], avail)
        asked.locator("[data-option='0'][role='radio']").wait_for(timeout=30000)
        row, opener = _opener(asked)
        assert opener.count() == 1, row.inner_text()
        # THE DECLARED ID, and not the post the question was asked on
        assert opener.get_attribute("data-open-record") == w["held"]
        assert opener.get_attribute("data-open-record") != w["asking_post"]
        assert "cannot be opened from here" not in row.inner_text()

        # a half-made answer, which opening the record may not touch
        pick = asked.locator("[data-option='0']")
        for _ in range(6):
            if pick.get_attribute("aria-checked") == "true":
                break
            pick.click()
            f.page.wait_for_timeout(250)
        asked.locator("textarea.rb-dec-words").fill("Read the design first.\nSecond line, kept.")

        opener.click()
        # the declared id is a post somebody wrote, so it is read as that post
        peek = f.page.locator(".pz-vpost")
        peek.wait_for(timeout=30000)
        peek.get_by_text(HELD_WORDS, exact=False).first.wait_for(timeout=30000)

        # AND COMING BACK FINDS THE FORM AS IT WAS LEFT
        f.page.locator("[data-act='close']").click()
        peek.wait_for(state="detached", timeout=20000)
        _, asked = f.question(w["required_material_available"], avail)
        assert asked.locator("[data-option='0']").get_attribute("aria-checked") == "true"
        assert asked.locator("textarea.rb-dec-words").input_value() == "Read the design first.\nSecond line, kept."
        # and it is still answerable: the return path is a real one
        card.locator(".rb-dec-foot .btn.primary").click()
        cv = world["cv"]
        for _ in range(80):
            if cv.expectation_state(avail)["answer"]:
                break
            f.page.wait_for_timeout(250)
        got = cv.expectation_state(avail)["answer"]
        assert got and (got["option"], got["label"]) == (0, "Build this design"), got
    finally:
        f.close()


def test_the_opener_never_stands_in_for_the_asking_post(chrome, world):  # noqa: F811
    """NOTHING IS SUBSTITUTED. The approval whose declared record this Brain
    does not hold still names that id and nothing else: the control carries the
    declared id, opening it reads that id -- not the asking post, which is a
    different record with different words -- and the choices stay withheld."""
    w = build(world)
    f = Fluid(chrome, world, w)
    try:
        qid = w["required_material_unavailable_question"]
        card, asked = f.question(w["required_material_unavailable"], qid)
        asked.locator("[data-clarify-needed='record']").wait_for(timeout=40000)
        row, opener = _opener(asked)
        assert opener.count() == 1, row.inner_text()
        assert opener.get_attribute("data-open-record") == ABSENT_ID
        assert opener.get_attribute("data-open-record") not in (w["asking_post"], w["held"])
        opener.click()
        # nothing answers for that id as a post, so it opens in the record's
        # own inspector -- as that id, and never as some other record
        peek = f.page.locator(".pz-vbrain")
        peek.wait_for(timeout=30000)
        f.page.wait_for_timeout(600)
        # the asking post's own words are not shown in place of it
        assert HELD_WORDS not in peek.inner_text()
        f.page.locator("[data-act='close']").click()
        peek.wait_for(state="detached", timeout=20000)
        # and the guard is exactly as it was: no choice of it is sent
        _, asked = f.question(w["required_material_unavailable"], qid)
        _nothing_sends(f, card)
        assert world["cv"].expectation_state(qid)["response_present"] is False
    finally:
        f.close()


def test_the_thread_sheets_drawing_of_the_same_form_opens_the_same_exact_record(chrome, world):  # noqa: F811
    """THE SAME FORM, A SECOND SHARED DRAWING. Opening the asking post's thread
    draws every form on it again in the same page; that drawing offers the same
    opener for the same declared id, and the draft both drawings share is kept
    through opening the record and coming back."""
    w = build(world)
    w["reply"]()
    f = Fluid(chrome, world, w)
    try:
        avail = w["required_material_available_question"]
        _, asked = f.question(w["required_material_available"], avail)
        asked.locator("[data-option='0'][role='radio']").wait_for(timeout=30000)
        asked.locator("[data-option='0']").click()
        asked.locator("textarea.rb-dec-words").fill("Kept across both drawings.")

        f.page.get_by_role("button", name="Reply to #1", exact=True).first.click()
        sheet = f.page.locator(".fw-thread-body [data-decision-form='"
                               + w["required_material_available"] + "']").last
        sheet.wait_for(timeout=20000)
        there = sheet.locator(f".rb-dec-q[data-question='{avail}'] [data-primary='ref'] button[data-open-record]")
        there.wait_for(timeout=30000)
        assert there.get_attribute("data-open-record") == w["held"]
        there.click()
        peek = f.page.locator(".pz-vpost")
        peek.wait_for(timeout=30000)
        peek.get_by_text(HELD_WORDS, exact=False).first.wait_for(timeout=30000)
        f.page.locator("[data-act='close']").click()
        peek.wait_for(state="detached", timeout=20000)
        held = f.page.locator(f"[data-decision-form='{w['required_material_available']}'] "
                              f".rb-dec-q[data-question='{avail}'] textarea.rb-dec-words").first
        assert held.input_value() == "Kept across both drawings."
        assert f.sent == [], f.sent
        assert world["cv"].expectation_state(avail)["response_present"] is False
    finally:
        f.close()


# ---------------------------------------------------------------------------
# AND WHAT IS OPENED CAN ACTUALLY BE READ (re-review finding F2-R1,
# ent-6347e9d7cabd, report adm-e1c8e43ae32c).
#
# The opener sends every supported NON-POST record, and every post whose lookup
# did not answer, to the record's own inspector -- and that inspector drew each
# declared field through `String(value)`. A field holding a structured value
# (a design with a purpose and a restriction; a contribution's list of content
# parts) therefore read `[object Object]`, so the one provided way to inspect
# the exact record a decision approves showed none of its words, while the
# entry read carried all of them. The requirement the form answers to is that
# the specific material can be inspected, so that is not cosmetic in this path.
#
# A field is now drawn as what it holds (`surfaces/entryValue`), and a post
# lookup that FAILED is kept apart from a lookup that answered and settled that
# the id is not a post (`fluid/present/decisionRefWords` `lookupExact`): the
# failure is tried once more, then said on the control, and the exact record is
# opened -- a fallback that is now genuinely readable.
#
# Nothing is substituted in either case: the id opened is the declared one, and
# the chosen option and the typed words are exactly as they were left.
#
# The Needs You zone and governance's asks supply the SAME provider
# (`FluidRefWords`) and the same inspector; the conversation column is the
# production host used here.

#: a structured design, as a dynamic Kind's one declared field holds it
DESIGN = {"purpose": "Build this isolated widget only.",
          "restriction": "Deployment is forbidden."}
#: what the ordinary post source this Brain holds actually says
POST_WORDS = "Exact candidate design: readable, build only."
#: the draft nothing here may lose
DRAFT = "Read the design first.\nSecond line, kept."


class Plain:
    """Fluid's conversation column on a conversation of this Brain, with
    NOTHING on the wire: the production host and the production reads."""

    def __init__(self, browser, world, w):  # noqa: F811
        self.context = browser.new_context(viewport={"width": 1280, "height": 1000})
        self.context.set_extra_http_headers(owner_headers())
        self.page = self.context.new_page()
        self.errors: list[str] = []
        self.sent: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("request", lambda r: self.sent.append(r.post_data or "")
                     if r.method == "POST" and "/turns" in r.url else None)
        # the asking post, which is the post Fluid's column draws the form on
        self.page.goto(world["base"] + "/fluid?c=" + w["cid"] + "&t=" + w["post"])

    def question(self, form):
        card = self.page.locator("[data-decision-form='" + form + "']").first
        card.wait_for(timeout=30000)
        card.evaluate("el => el.scrollIntoView({block: 'center'})")
        q = card.locator(".rb-dec-q").first
        q.wait_for(timeout=20000)
        return card, q

    def close(self):
        self.context.close()
        assert self.errors == []


def _strict_approval(world, cid, primary):  # noqa: F811
    """ONE STRICT `artifact_approval` OF ONE EXACT RECORD THIS BRAIN HOLDS,
    authored through the production door -- no replay, no weakened validator --
    on the asking run's own post, which is the post Fluid's column draws."""
    from mentis.worker import _operate
    from mentis.web import _surface
    from tests.decision_descriptors import question

    _coach, parent, grant = _coordinator(world, cid)
    post = world["cv"]._act(parent)["turn"]
    item = question("Build the exact candidate design?")
    item["presentation"]["type"] = "artifact_approval"
    item["presentation"]["primary"] = {"kind": "record", "id": primary,
                                       "label": "Exact candidate design"}
    item["presentation"].pop("primary_reason", None)
    made = _operate(_surface(world["state"]), "request_decision",
                    {"on": post, "because": item["because"], "questions": [item]}, grant)
    return {"cid": cid, "post": post, "form": made["form"],
            "qid": made["questions"][0]["expectation"], "source": primary}


def _drafted_here(q):
    """The first option chosen and two lines typed, which opening the exact
    record may not touch."""
    pick = q.locator("[role='radio'][data-option='0']")
    pick.wait_for(timeout=30000)
    for _ in range(6):
        if pick.get_attribute("aria-checked") == "true":
            break
        pick.click()
        q.page.wait_for_timeout(250)
    assert pick.get_attribute("aria-checked") == "true", q.inner_text()
    words = q.locator("textarea.rb-dec-words")
    words.wait_for(timeout=20000)
    words.fill(DRAFT)


def _kept_draft(q):
    assert q.locator("[data-option='0']").get_attribute("aria-checked") == "true"
    assert q.locator("textarea.rb-dec-words").input_value() == DRAFT


def test_a_structured_exact_record_is_readable_where_it_is_opened(chrome, world):  # noqa: F811
    """THE FINDING ITSELF. A valid record of an ordinary dynamic Kind whose one
    declared field holds a structured design: every part of it is on the screen,
    under the name the record gave it, and `[object Object]` appears nowhere.
    Nothing is sent by opening it, and the half-made answer comes back intact."""
    by = world["who"]["@brian"]
    corpus = world["cv"]._c
    corpus.define_kind("review-design", fields=["design"], attributed_to=by)
    exact = corpus.write(kind="review-design", body={"design": dict(DESIGN)}, attributed_to=by)
    cid = a_conversation(world, "Exact source: a structured record")
    w = _strict_approval(world, cid, exact)
    f = Plain(chrome, world, w)
    try:
        card, asked = f.question(w["form"])
        _drafted_here(asked)
        opener = asked.locator("button[data-open-record]")
        opener.wait_for(timeout=30000)
        assert opener.get_attribute("data-open-record") == exact
        opener.click()
        peek = f.page.locator(".pz-vbrain")
        peek.wait_for(timeout=30000)
        peek.locator(".ei-statement").wait_for(timeout=30000)
        said = peek.inner_text()
        assert "[object Object]" not in said, said
        for part in (DESIGN["purpose"], DESIGN["restriction"]):
            assert part in said, said
        # under the names the record gave them, in the order it holds them
        assert said.index(DESIGN["purpose"]) < said.index(DESIGN["restriction"]), said
        assert "purpose" in said.lower() and "restriction" in said.lower(), said
        # AND COMING BACK FINDS THE FORM AS IT WAS LEFT
        f.page.keyboard.press("Escape")
        peek.wait_for(state="detached", timeout=20000)
        _, asked = f.question(w["form"])
        _kept_draft(asked)
        assert f.sent == [], f.sent
        assert world["cv"].expectation_state(w["qid"])["response_present"] is False
        assert card.count() == 1
    finally:
        f.close()


def test_a_post_read_that_failed_is_said_and_the_exact_record_is_still_readable(chrome, world):  # noqa: F811
    """A FAILED LOOKUP IS NOT A DETERMINATION. The declared id IS an ordinary
    post; only its post read is made to fail, while its entry read stays
    healthy. The failure is said on the control, the exact record is opened as
    the record it is, and its own recorded words are readable there -- they were
    in the entry read the whole time. Nothing else is opened in its place."""
    cv = world["cv"]
    # THE DECLARED RECORD IS A POST, AND IT IS SOMEWHERE ELSE, so this page has
    # not already read it: clicking the opener really does make the post read
    # the finding is about. (A post the column already holds needs no read and
    # opens in full, which is the healthy case above.)
    elsewhere = a_conversation(world, "Exact source: where the post itself lives")
    away, _p, _g = _coordinator(world, elsewhere)
    source = cv.say(elsewhere, away, [text(POST_WORDS)])
    cv.say(elsewhere, away, [text("A different record; do not substitute it.")])
    cid = a_conversation(world, "Exact source: the post read failed")
    w = _strict_approval(world, cid, source)
    f = Plain(chrome, world, w)
    try:
        card, asked = f.question(w["form"])
        _drafted_here(asked)
        # ONLY the post lookup of THAT id fails; everything else is untouched
        def no_post(route):
            if source in route.request.url:
                return route.fulfill(status=500, content_type="application/json",
                                     body=json.dumps({"error": "the fixture server refused this post read"}))
            return route.continue_()
        f.context.route("**/fluid/api/posts?*", no_post)
        opener = asked.locator("button[data-open-record]")
        opener.wait_for(timeout=30000)
        assert opener.get_attribute("data-open-record") == source
        opener.click()
        peek = f.page.locator(".pz-vbrain")
        peek.wait_for(timeout=30000)
        peek.locator(".ei-statement").wait_for(timeout=30000)
        said = peek.inner_text()
        assert "[object Object]" not in said, said
        assert POST_WORDS in said, said
        assert "A different record; do not substitute it." not in said, said
        f.page.keyboard.press("Escape")
        peek.wait_for(state="detached", timeout=20000)
        _, asked = f.question(w["form"])
        # THE READ IS REPORTED, AND IT IS THE READ THAT IS REPORTED
        why = asked.locator("[data-open-record-read='post-failed']")
        why.wait_for(timeout=20000)
        told = why.inner_text()
        assert "post read failed" in told, told
        for word in ("deleted", "holds nothing", "not a post"):
            assert word not in told, told
        _kept_draft(asked)
        assert f.sent == [], f.sent
        assert world["cv"].expectation_state(w["qid"])["response_present"] is False
        assert card.count() == 1
    finally:
        f.close()
