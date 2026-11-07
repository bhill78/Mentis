"""Returned work is acted on without waiting for unrelated runs, or for an open question.

THE DELAY THIS EXISTS FOR (Unified Fluid Space, 2026-11-07). A Caretaker had a review of package S
and a Builder on package R out at once. The review returned BLOCK at 09:36; the Caretaker was not
resumed until R returned at 10:25, so S's correction -- which later packages need -- waited 49
minutes for work it did not depend on.

What holds now, through the real delegate, request_decision, dispatch and posting:

  * a child delegated with `resume_on_return` resumes its carrier when it returns, while other
    children still run; the carrier is told which, and each resumes it again when it ends;
  * without it, the carrier still resumes once, when everything it needs back has returned;
  * two returns while one resumption is about to run give one run, and the second return is handed
    over when that run ends -- exactly once;
  * a question the carrier asked does not hold returned work: it is said to be open, and its
    answer resumes the carrier once more.
"""

from __future__ import annotations

import pytest

from mentis.web import dispatch as D
from tests._loop import _coordinator, a_conversation, world  # noqa: F401
from tests.test_decision_resume_parent import (OPTIONS, QUESTION, _answer, _form_of, _resumes,
                                               _run, _start_held, fake)  # noqa: F401
from tests.test_delegate_coordinate import _present


def _delegate(world, grant, who, work, **flags):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "delegate",
                    {"participant": who, "work": work, **flags}, grant)


def _ask(world, grant):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "request_decision",
                    {"question": QUESTION, "options": OPTIONS,
                     "because": "only the owner can choose"}, grant)


def _pair(world, **review_flags):
    """P coordinates; a review R (flagged as asked) and a Builder B both return to it."""
    cv = world["cv"]
    cid = a_conversation(world)
    _coach, parent, grant = _coordinator(world, cid)
    reviewer, builder = _present(world, cid, "@Reviewer"), _present(world, cid, "@Builder")
    r = _delegate(world, grant, reviewer, "review package S", **review_flags)
    b = _delegate(world, grant, builder, "build package R", return_to_me=True)
    return cv, parent, grant, (r, reviewer), (b, builder)


def _run_parent(world, parent):
    """P's resumed run, as dispatched."""
    spec = next(k for k in reversed(world["sent"]) if k["expectation"] == parent)
    world["sent"].remove(spec)
    D.dispatch(world["state"], **spec)


def test_a_child_flagged_to_resume_on_return_resumes_its_carrier_while_a_sibling_runs(world, fake):
    cv, parent, _, (r, reviewer), (b, builder) = _pair(world, resume_on_return=True)
    assert cv._act(r["expectation"])["detail"]["returns_to"]
    t, gate = _start_held(world, fake, b, builder)
    try:
        world["sent"].clear()
        _run(world, r, reviewer)
        resumed = _resumes(cv, parent)
        assert len(resumed) == 1
        detail = resumed[0]["detail"]
        assert detail["event"] == {"kind": "child-ended", "expectation": r["expectation"]}
        assert detail["alone"] == [r["expectation"]]
        assert detail["outstanding"] == [b["expectation"]]
        work = next(k for k in world["sent"] if k["expectation"] == parent)["work"]
        assert "still outstanding" in work and "not to be handed out again" in work
        # and the status says the review resumes it on its own
        from mentis.operational.work import conversation_work
        item = next(i for i in conversation_work(cv, cv._act(parent)["conversation"])["items"]
                    if i["expectation"] == parent)
        assert item["next"]["value"] == "Resumes when @Builder returns", item["next"]
        _run_parent(world, parent)
        assert len(_resumes(cv, parent)) == 1
    finally:
        gate.set()
        t.join(60)
    # B's return resumes P once more, and only once.
    resumed = _resumes(cv, parent)
    assert len(resumed) == 2
    assert resumed[-1]["detail"]["event"] == {"kind": "child-ended", "expectation": b["expectation"]}
    assert "outstanding" not in resumed[-1]["detail"]
    assert cv.claim_resumption(parent, event={"kind": "again"}) is None


def test_without_the_flag_the_carrier_still_waits_for_everything_it_needs_back(world, fake):
    cv, parent, _, (r, reviewer), (b, builder) = _pair(world, return_to_me=True)
    t, gate = _start_held(world, fake, b, builder)
    try:
        _run(world, r, reviewer)
        assert not _resumes(cv, parent)
        assert not cv._child_state(r["expectation"])["resume_on_return"]
    finally:
        gate.set()
        t.join(60)
    resumed = _resumes(cv, parent)
    assert len(resumed) == 1 and "outstanding" not in resumed[0]["detail"]
    assert cv.claim_resumption(parent, event={"kind": "again"}) is None


def test_a_return_while_a_resumption_is_about_to_run_is_handed_over_once_after_it(world, fake):
    cv, parent, _, (r, reviewer), (b, builder) = _pair(world, resume_on_return=True)
    t, gate = _start_held(world, fake, b, builder)
    try:
        _run(world, r, reviewer)
        assert len(_resumes(cv, parent)) == 1            # R resumed P; its run has not started
    finally:
        gate.set()
        t.join(60)
    # B ended in that gap: no second run of P beside the one about to start.
    assert len(_resumes(cv, parent)) == 1
    _run_parent(world, parent)
    # P's run ends, and B's return -- which that run was not given -- resumes it once.
    resumed = _resumes(cv, parent)
    assert len(resumed) == 2
    assert [c["state"] for c in resumed[-1]["detail"]["required"]
            if c["expectation"] == b["expectation"]] == ["returned"]
    _run_parent(world, parent)
    assert len(_resumes(cv, parent)) == 2
    assert cv.claim_resumption(parent, event={"kind": "again"}) is None


def test_an_open_question_the_carrier_asked_does_not_hold_returned_work(world, fake):
    cv = world["cv"]
    cid = a_conversation(world)
    _coach, parent, grant = _coordinator(world, cid)
    builder = _present(world, cid, "@Builder")
    b = _delegate(world, grant, builder, "build package R", return_to_me=True)
    asked = _ask(world, grant)
    assert "error" not in asked, asked
    form = _form_of(cv, parent)
    assert not form["closed"]
    world["sent"].clear()
    _run(world, b, builder)
    resumed = _resumes(cv, parent)
    assert len(resumed) == 1
    detail = resumed[0]["detail"]
    assert detail["open_questions"] == [form["questions"][0]["expectation"]]
    assert "forms" not in detail or form["form"] not in detail["forms"]
    work = next(k for k in world["sent"] if k["expectation"] == parent)["work"]
    assert "do nothing that needs its answer" in work
    assert f"- decision form {form['form']}" in work and "still open" in work
    assert f"{QUESTION} ({form['questions'][0]['expectation']}): open" in work
    _run_parent(world, parent)
    assert len(_resumes(cv, parent)) == 1

    # The answer resumes P once more, with the form handed over.
    world["sent"].clear()
    got = _answer(world, cv.decision_form(form["form"]))
    resumed = _resumes(cv, parent)
    assert len(resumed) == 2 and got["resumed"] == [resumed[-1]["id"]]
    assert resumed[-1]["detail"]["forms"] == [form["form"]]
    assert "open_questions" not in resumed[-1]["detail"]
    assert cv.claim_resumption(parent, event={"kind": "again"}) is None


def test_an_open_question_with_a_child_still_running_waits_for_the_child(world, fake):
    """The question no longer holds anything; the running child still does."""
    cv = world["cv"]
    cid = a_conversation(world)
    _coach, parent, grant = _coordinator(world, cid)
    builder = _present(world, cid, "@Builder")
    b = _delegate(world, grant, builder, "build package R", return_to_me=True)
    _ask(world, grant)
    t, gate = _start_held(world, fake, b, builder)
    try:
        assert cv.claim_resumption(parent, event={"kind": "probe"}) is None
        assert not _resumes(cv, parent)
    finally:
        gate.set()
        t.join(60)
    assert len(_resumes(cv, parent)) == 1


@pytest.mark.parametrize("flag", [True, False])
def test_the_delegation_records_whether_it_resumes_alone(world, fake, flag):
    cv = world["cv"]
    cid = a_conversation(world)
    _coach, parent, grant = _coordinator(world, cid)
    builder = _present(world, cid, "@Builder")
    out = _delegate(world, grant, builder, "build package R", return_to_me=True,
                    resume_on_return=flag)
    detail = cv._act(out["expectation"])["detail"]
    assert bool(detail.get("resume_on_return")) is flag
    assert detail["returns_to"]
    delegated = cv._act(out["delegation"])["detail"]
    assert delegated["return_expected"] is True
    assert bool(delegated.get("resume_on_return")) is flag


def test_an_answer_while_a_resumption_is_about_to_run_is_handed_over_once_after_it(world, fake):
    cv = world["cv"]
    cid = a_conversation(world)
    _coach, parent, grant = _coordinator(world, cid)
    builder = _present(world, cid, "@Builder")
    b = _delegate(world, grant, builder, "build package R", return_to_me=True)
    _ask(world, grant)
    form = _form_of(cv, parent)
    _run(world, b, builder)
    assert len(_resumes(cv, parent)) == 1               # resumed; its run has not started
    got = _answer(world, cv.decision_form(form["form"]))
    assert not got.get("resumed") and len(_resumes(cv, parent)) == 1
    _run_parent(world, parent)
    # The run ends, and the answer -- which that run was not given -- resumes it once.
    resumed = _resumes(cv, parent)
    assert len(resumed) == 2 and resumed[-1]["detail"]["forms"] == [form["form"]]
    _run_parent(world, parent)
    assert len(_resumes(cv, parent)) == 2
    assert cv.claim_resumption(parent, event={"kind": "again"}) is None
