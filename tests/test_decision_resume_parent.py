"""Answering a decision a child raised resumes its parent, once, and never past a sibling.

THE FAILURE THIS EXISTS FOR (Quiet Chat, 2026-11-06). A coordinator delegated a Reviewer and a
Builder. The Reviewer raised a decision and returned at 15:00; the coordinator was resumed at once,
with that question still open. The owner answered at 15:29, and the answer re-ran the Reviewer --
which had already returned -- while the Builder was still running: 13 minutes reviewing nothing.
When the Builder returned at 15:31 its return resumed nothing, because the re-run counted as
outstanding, and the result sat for 12 minutes.

What holds now, through the real delegate, request_decision, dispatch and posting:

  * a child's open decision is outstanding for its parent, so its return resumes nothing;
  * answering it when the child has returned resumes the parent, not the child -- and not while a
    sibling is still running;
  * the parent resumes exactly once, when nothing it waits on is outstanding, and the act says
    which decision closed and how it was answered;
  * an asker that is live when answered, or that returns to nobody, is resumed as before.
"""

from __future__ import annotations

import threading
import time

import pytest

from mentis.execution import RunResult
from mentis.web import dispatch as D
from tests._loop import _coordinator, a_conversation, grant_of_run, post, say, world  # noqa: F401
from tests._loop import script_every_backend
from tests.test_delegate_coordinate import _present

QUESTION = "Ship the candidate as it is, or wait for the corrected one?"
OPTIONS = [{"label": "Ship it", "consequence": "it goes out today"},
           {"label": "Wait", "consequence": "nothing ships until it is corrected"}]


@pytest.fixture()
def fake(world):
    """Runs complete as the test says, by the expectation they carry -- not by prompt text, which
    carries the siblings' work too: one in `ask` raises a decision form while running, one in
    `hold` waits on its gate until released, one in `fail` fails. Every other run returns."""
    from mentis.web import _surface
    from mentis.worker import _operate
    svc = world["state"].agents
    plan = {"ask": set(), "hold": {}, "fail": set()}

    def perform(spec):
        grant = grant_of_run(svc, spec, world["state"].path)
        if grant["expectation"] in plan["ask"]:
            _operate(_surface(world["state"]), "request_decision",
                     {"question": QUESTION, "options": OPTIONS,
                      "because": "only the owner can choose"}, grant)
        gate = plan["hold"].get(grant["expectation"])
        if gate is not None:
            gate.wait(timeout=120)
        now = time.time()
        if grant["expectation"] in plan["fail"]:
            return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                             error_kind="agent_error", error="the runtime exited 1",
                             started_at=now, finished_at=now)
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done: here is what I found",
                         started_at=now, finished_at=now)

    script_every_backend(svc, perform)
    return plan


def _child(world, grant, who, work):
    from mentis.web import _surface
    from mentis.worker import _operate
    out = _operate(_surface(world["state"]), "delegate",
                   {"participant": who, "work": work, "return_to_me": True}, grant)
    return out


def _run(world, out, who):
    return D.dispatch(world["state"], conversation=out["conversation"], turn=out["turn"],
                      participant=who, work=out["dispatch"]["work"],
                      expectation=out["expectation"])


def _resumes(cv, expectation):
    return [a for a in cv.history(caused_by=expectation) if a["act"] == "work-resumed"]


def _form_of(cv, asker):
    from mentis.conversation import DECISION_FORM
    forms = [a["id"] for a in cv.history(caused_by=asker) if a["act"] == DECISION_FORM]
    assert len(forms) == 1
    return cv.decision_form(forms[0])


def _answer(world, form, label="Wait"):
    q = form["questions"][0]
    i = [o["label"] for o in q["options"]].index(label)
    got = post(world, f"/api/conversations/{form['conversation']}/turns",
               {"author": world["who"]["@brian"], "text": label, "action": "record-only",
                "replies_to": form["post"], "addressed_to": [],
                "chose": {"expectation": q["expectation"], "option": i, "label": label}})
    assert "error" not in got, got
    return got


def _live(cv, expectation, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cv.expectation_state(expectation)["live_execution"]:
            return
        time.sleep(0.05)
    raise AssertionError(f"{expectation} never started")


def _team(world, fake):
    """P coordinates; it delegates a Reviewer R, who asks, and a Builder B, both returning to it."""
    cv = world["cv"]
    cid = a_conversation(world)
    _coach, parent, grant = _coordinator(world, cid)
    reviewer, builder = _present(world, cid, "@Reviewer"), _present(world, cid, "@Builder")
    r = _child(world, grant, reviewer, "review the candidate")
    b = _child(world, grant, builder, "build the candidate")
    fake["ask"].add(r["expectation"])
    return cv, parent, (r, reviewer), (b, builder)


def _start_held(world, fake, out, who):
    fake["hold"][out["expectation"]] = gate = threading.Event()
    t = threading.Thread(target=_run, args=(world, out, who))
    t.start()
    _live(world["cv"], out["expectation"])
    return t, gate


# -- (e) and (a), (b): the Quiet case ------------------------------------------------------------


def test_the_quiet_case_resumes_the_parent_once_after_the_sibling(world, fake):
    cv, parent, (r, reviewer), (b, builder) = _team(world, fake)
    t, gate = _start_held(world, fake, b, builder)

    # (e) R raises D and returns while B runs: D is the parent's outstanding too.
    _run(world, r, reviewer)
    form = _form_of(cv, r["expectation"])
    assert form["post"] and not form["closed"]
    waiting = cv.waiting_on(parent)
    d = form["questions"][0]["expectation"]
    assert d in waiting["outstanding"]
    entry = next(x for x in waiting["child_decisions"] if x["expectation"] == d)
    assert entry["kind"] == "child-decision" and entry["asked_by"] == r["expectation"]
    assert not entry["answered"]
    assert not _resumes(cv, parent)

    # (a) answering D while B runs resumes nothing: not R, which returned, and not P.
    world["sent"].clear()
    got = _answer(world, form)
    assert not got.get("resumed")
    assert not _resumes(cv, parent) and not _resumes(cv, r["expectation"])
    assert not world["sent"]
    assert cv.waiting_on(parent)["outstanding"] == [b["expectation"]]

    # (b) B returns: P resumes exactly once, and the act shows D answered.
    gate.set()
    t.join(60)
    resumed = _resumes(cv, parent)
    assert len(resumed) == 1
    detail = resumed[0]["detail"]
    assert detail["event"]["kind"] == "child-ended"
    assert detail["event"]["expectation"] == b["expectation"]
    said = next(x for x in detail["child_decisions"] if x["expectation"] == d)
    assert said["answered"] and said["answer"]["label"] == "Wait"
    assert detail["child_forms"] == [form["form"]]
    assert not _resumes(cv, r["expectation"])
    assert [k["expectation"] for k in world["sent"]] == [parent]


# -- (c): the sibling already returned ------------------------------------------------------------


def test_answering_after_every_sibling_returned_resumes_the_parent_once(world, fake):
    cv, parent, (r, reviewer), (b, builder) = _team(world, fake)
    _run(world, b, builder)
    # B alone returning resumed P (nothing else was outstanding then: R not yet started
    # reads as not-ended, so it did not).
    before = len(_resumes(cv, parent))
    _run(world, r, reviewer)
    form = _form_of(cv, r["expectation"])
    assert len(_resumes(cv, parent)) == before, "R's return resumed P with D still open"

    world["sent"].clear()
    got = _answer(world, form)
    resumed = _resumes(cv, parent)
    assert len(resumed) == before + 1 and got["resumed"] == [resumed[-1]["id"]]
    event = resumed[-1]["detail"]["event"]
    assert event["kind"] == "decision-form-closed" and event["form"] == form["form"]
    assert event["asked_by"] == r["expectation"] and event["resumes"] == "parent"
    assert event["question"] == form["questions"][0]["expectation"]
    assert not _resumes(cv, r["expectation"])
    assert [k["expectation"] for k in world["sent"]] == [parent]
    # and only once: the form is handed over, nothing new is left to resume for
    assert cv.claim_resumption(parent, event={"kind": "again"}) is None


def test_a_child_whose_latest_run_failed_is_not_treated_as_returned(world, fake):
    """Returned is the LATEST run's state: an earlier return does not count once a later run of
    the same request failed, so the answer goes to the asker as before."""
    cv, parent, (r, reviewer), (b, builder) = _team(world, fake)
    _run(world, b, builder)
    _run(world, r, reviewer)
    form = _form_of(cv, r["expectation"])
    fake["ask"].discard(r["expectation"])
    fake["fail"].add(r["expectation"])
    _run(world, r, reviewer)
    assert cv._child_state(r["expectation"])["state"] == "failed"
    world["sent"].clear()
    got = _answer(world, form)
    mine = _resumes(cv, r["expectation"])
    assert len(mine) == 1 and got["resumed"] == [mine[0]["id"]]
    assert mine[0]["detail"]["event"]["resumes"] == "asker"
    assert not [a for a in _resumes(cv, parent)
                if a["detail"]["event"]["kind"] == "decision-form-closed"]


# -- (d): askers that are not a returned child keep today's behaviour ----------------------------


def test_an_asker_that_returns_to_nobody_is_resumed_by_the_answer(world, fake):
    cv = world["cv"]
    cid = a_conversation(world)
    ada = world["who"]["@Ada"]
    say(world, cid, "@Ada review this", action="ask-participant",
        dispatch=[{"participant": ada, "work": "review this"}])
    kw = world["sent"][-1]
    asker = kw["expectation"]
    fake["ask"].add(asker)
    D.dispatch(world["state"], **kw)
    form = _form_of(cv, asker)
    assert not _resumes(cv, asker)
    world["sent"].clear()
    got = _answer(world, form)
    resumed = _resumes(cv, asker)
    assert len(resumed) == 1 and got["resumed"] == [resumed[0]["id"]]
    assert resumed[0]["detail"]["event"]["resumes"] == "asker"
    assert resumed[0]["detail"]["forms"] == [form["form"]]


def test_a_live_asker_is_resumed_on_the_answer_not_its_parent(world, fake):
    cv, parent, (r, reviewer), _ = _team(world, fake)
    t, gate = _start_held(world, fake, r, reviewer)
    from mentis.conversation import DECISION_FORM
    # Wait for the whole form -- its act AND its questions, written in one transaction -- then
    # put it on R's request (a live run's form is on no post until it ends), and wait for that.
    deadline, form = time.time() + 20, None
    while time.time() < deadline:
        acts = [a for a in cv.history(caused_by=r["expectation"]) if a["act"] == DECISION_FORM]
        form = cv.decision_form(acts[0]["id"]) if acts else None
        if form and form["questions"]:
            if not form["post"]:
                cv.attach_pending_forms(form["execution"], r["turn"], by=reviewer)
                form = cv.decision_form(form["form"])
            if form["post"]:
                break
        time.sleep(0.05)
    assert form and form["post"], "the live run's form never reached a post"
    fid = form["form"]
    got = _answer(world, form)
    # The asker is live, so nothing resumes yet -- and the parent is not taken instead.
    assert not got.get("resumed")
    assert not _resumes(cv, parent) and not _resumes(cv, r["expectation"])
    gate.set()
    t.join(60)
    # Its own run ending hands it the answer, as before.
    mine = _resumes(cv, r["expectation"])
    assert len(mine) == 1 and mine[0]["detail"]["forms"] == [fid]
