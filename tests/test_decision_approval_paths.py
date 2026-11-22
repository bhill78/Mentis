"""Actual dispatch/respond/manual outcome paths, rollback, isolation and closure."""
import json
import threading
import time

import pytest

from mentis.operational import completion
from mentis.web import _surface
from mentis.worker import _operate
from tests._loop import _coordinator, a_conversation, grant_of_run, post, script_every_backend, world  # noqa: F401
from tests.decision_descriptors import question
from tests.test_decision_presentation import create_outcome, operate
from tests.test_run_consent import ws  # noqa: F401


@pytest.mark.parametrize("count", [1, 20])
def test_actual_dispatch_attaches_before_claim_and_records_refusal_or_append(world, count):
    from mentis.execution import RunResult
    from mentis.web import dispatch
    cv, st = world["cv"], world["state"]
    actor, parent, _ = _coordinator(world, a_conversation(world))
    made = {}

    def perform(spec):
        grant = grant_of_run(st.agents, spec, st.path)
        made.update(operate(world, grant, "request_decision", questions=[question(f"Chart {i}?") for i in range(count)]))
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         started_at=now, finished_at=now, stop_reason="end_turn",
                         text="Candidate ready\n\n```outcome\nresult: met\nsummary: Chart prepared\napproval: "
                         + json.dumps(create_outcome()["approval"]) + "\n```")

    script_every_backend(st.agents, perform)
    dispatch.dispatch(st, participant=actor, conversation=cv._act(parent)["conversation"],
                      turn=cv._act(parent)["turn"], expectation=parent, work="prepare chart")
    form = cv.decision_form(made["form"])
    assert form["post"] and not form["pending"]
    claim = completion.latest_claim(cv, parent)
    assert claim and claim["detail"]["summary"] == "Chart prepared"
    if count == 20:
        assert "approval" not in claim["detail"]
        assert claim["detail"]["outcome_unclaimed"]["problems"] == [{"path": "approval.questions", "code": "form_limit_20"}]
    else:
        assert claim["detail"]["approval"] == made["form"] and len(form["questions"]) == 2
    assert not cv.expectation_state(parent)["satisfied_by"]


def test_respond_overflow_returns_post_claim_and_diagnostic_without_new_form(world):
    cv = world["cv"]
    _, parent, grant = _coordinator(world, a_conversation(world))
    made = operate(world, grant, "request_decision", questions=[question(f"Chart {i}?") for i in range(20)])
    out = operate(world, grant, "respond", text="Candidate ready", outcome=create_outcome())
    assert out["turn"] and out["claim"] and out["outcome_unclaimed"]["kind"] == "bad-approval"
    assert out["reconciled"]["recorded"] == "pending"
    assert cv.decision_forms_on(out["turn"]) == [made["form"]]
    assert len(cv.decision_form(made["form"])["questions"]) == 20


def _checked_result(world, actor, parent, grant):
    return operate(world, grant, "respond", text="Prepared chart questions.")


@pytest.mark.parametrize("case", ["other_actor", "other_post", "ambiguous", "owner", "closed", "permission", "prose"])
def test_ineligible_existing_or_create_target_never_falls_back(world, case):
    from mentis.worker import _decision_form
    cv = world["cv"]
    actor, parent, grant = _coordinator(world, a_conversation(world))
    # Read the actual execution from a trusted result act, not grant shape.
    result = _checked_result(world, actor, parent, grant)
    execution = cv._act(result["said_act"])["execution"]
    options = {}
    actor_used = cv.create_participant("@Other") if case == "other_actor" else actor
    form_detail = {"permission": True} if case == "permission" else {"from_prose": True} if case == "prose" else None

    def make():
        return _decision_form(cv, {**question(), **options}, actor=actor_used, parent=parent,
                              here=cv._act(parent)["conversation"], wrote=None, execution=execution,
                              act=lambda kind, **kw: cv.record_act(actor=actor_used, act=kind, caused_by=parent, execution=execution, **kw),
                              where=lambda cid: cid, form_detail=form_detail)
    made = make()
    if case == "other_post":
        cv.attach_pending_forms(execution, cv._act(parent)["turn"], by=actor)
        approval = create_outcome()["approval"]
    elif case in ("permission", "prose"):
        approval = {"mode": "existing", "form": made["form"], "questions": [made["expectation"]]}
    else:
        approval = create_outcome()["approval"]
    if case == "ambiguous":
        # Internal fixture producer makes another ordinary pending form.
        form_detail = {"fixture": True}
        make()
        approval = create_outcome()["approval"]
    if case in ("owner", "closed"):
        if case == "owner":
            # Append-only fixture mismatch: an extra question expected of another participant.
            cv.expect(None, of=cv.create_participant("@NotOwner"), kind="decision", by=actor,
                      caused_by=parent, conversation=cv._act(parent)["conversation"],
                      detail={"form": made["form"], "index": 1, "question": "Wrong owner?", "requester": actor})
        else:
            cv.attach_pending_forms(execution, result["turn"], by=actor)
            q = cv.decision_form(made["form"])["questions"][0]
            post(world, f"/api/conversations/{cv._act(parent)['conversation']}/turns", {
                "author": world["who"]["@brian"], "text": "No longer needed", "action": "record-only",
                "replies_to": result["turn"], "chose": {"expectation": q["expectation"], "withdraw": True}})
    before = cv.decision_form(made["form"])
    claim = completion.claim(cv, parent, {"result": "met", "approval": approval}, actor=actor,
                             execution=execution, reply_turn=result["turn"], via="reply")
    assert "approval" not in cv._act(claim)["detail"]
    assert cv._act(claim)["detail"]["outcome_unclaimed"]["kind"] == "bad-approval"
    assert cv.decision_form(made["form"]) == before


def test_injected_append_write_failure_rolls_back_all_questions_and_claim(world, monkeypatch):
    cv = world["cv"]
    actor, parent, grant = _coordinator(world, a_conversation(world))
    made = operate(world, grant, "request_decision", **question())
    result = _checked_result(world, actor, parent, grant)
    before = len(cv.history()), len(cv.corpus.all_entries())
    original = cv.expect
    calls = []

    def fail(*args, **kw):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("injected append failure")
        return original(*args, **kw)

    monkeypatch.setattr(cv, "expect", fail)
    with pytest.raises(RuntimeError, match="injected"):
        completion.claim(cv, parent, {"result": "met", "approval": {"mode": "create", "questions": [question(), question("Second?")]}},
                         actor=actor, execution=cv._act(result["said_act"])["execution"], reply_turn=result["turn"], via="reply")
    assert (len(cv.history()), len(cv.corpus.all_entries())) == before
    assert len(cv.decision_form(made["form"])["questions"]) == 1


@pytest.mark.parametrize("withdraw", [False, True])
def test_append_commits_before_last_answer_or_withdrawal_keeps_form_open(world, withdraw):
    cv = world["cv"]
    _, parent, grant = _coordinator(world, a_conversation(world))
    made = operate(world, grant, "request_decision", **question())
    out = operate(world, grant, "respond", text="Prepared", outcome=create_outcome())
    chose = {"expectation": made["expectation"]}
    chose.update({"withdraw": True} if withdraw else {"option": 1, "label": "Wait"})
    answer = post(world, f"/api/conversations/{cv._act(parent)['conversation']}/turns", {
        "author": world["who"]["@brian"], "text": "Wait for now", "action": "record-only",
        "replies_to": out["turn"], "chose": chose})
    assert "error" not in answer
    assert cv.decision_form(made["form"])["open"] == 1
    assert not [a for a in cv._children(parent) if a["act"] == "work-resumed"]


@pytest.mark.parametrize("label,expected", [("Allow once", "once"), ("Deny", "no")])
def test_real_permission_producer_retains_offer_to_runtime_mapping(world, ws, label, expected):
    from tests.test_run_consent import _policy_world, _shell, _answer_form
    cid, _, _, run, policy = _policy_world(world, ws)
    obs, got = {}, {}
    thread = threading.Thread(target=lambda: got.setdefault(
        "answer", policy(run, "inst-c", _shell(f"echo chart > {ws['other']}\\chart.txt"), obs)))
    thread.start()
    try:
        form = _answer_form(world, cid, obs, label)
    finally:
        thread.join(30)
    assert not thread.is_alive()
    assert got["answer"] == expected
    assert "presentation" not in form["questions"][0]
    assert form["questions"][0]["presentation_status"] == {"state": "legacy", "problems": []}
    assert [o["label"] for o in form["questions"][0]["options"]][0] == "Allow once"


def test_existing_binding_cannot_reach_another_request(world):
    cv = world["cv"]
    actor, parent, grant = _coordinator(world, a_conversation(world))
    made = operate(world, grant, "request_decision", **question())
    actor2, parent2, grant2 = _coordinator(world, a_conversation(world))
    out = operate(world, grant2, "respond", text="Another request", outcome={
        "result": "met", "approval": {"mode": "existing", "form": made["form"], "questions": [made["expectation"]]}})
    assert out["outcome_unclaimed"]["kind"] == "bad-approval"
    assert "not_ordinary_form_of_carried_request" in out["outcome_unclaimed"]["why"]
    assert cv.decision_form(made["form"])["pending"]


@pytest.mark.parametrize("withdraw", [False, True])
def test_append_racing_the_last_answer_or_withdrawal_has_one_commit_order(world, withdraw):
    from concurrent.futures import ThreadPoolExecutor
    cv = world["cv"]
    actor, parent, grant = _coordinator(world, a_conversation(world))
    made = operate(world, grant, "request_decision", **question())
    result = _checked_result(world, actor, parent, grant)
    execution = cv._act(result["said_act"])["execution"]
    gate = threading.Barrier(2, timeout=10)

    def append():
        gate.wait()
        return completion.claim(cv, parent, create_outcome(), actor=actor,
                                execution=execution, reply_turn=result["turn"], via="reply")

    def close():
        gate.wait()
        chose = {"expectation": made["expectation"]}
        chose.update({"withdraw": True} if withdraw else {"option": 1, "label": "Wait"})
        return post(world, f"/api/conversations/{cv._act(parent)['conversation']}/turns", {
            "author": world["who"]["@brian"], "text": "Wait for now", "action": "record-only",
            "replies_to": result["turn"], "chose": chose})

    with ThreadPoolExecutor(max_workers=2) as pool:
        claiming, closing = pool.submit(append), pool.submit(close)
        claim, answer = claiming.result(timeout=30), closing.result(timeout=30)
    assert "error" not in answer
    form = cv.decision_form(made["form"])
    detail = cv._act(claim)["detail"]
    resumed = [a for a in cv._children(parent) if a["act"] == "work-resumed"]
    if detail.get("approval"):
        assert len(form["questions"]) == 2 and form["open"] == 1 and not resumed
    else:
        assert detail["outcome_unclaimed"]["kind"] == "bad-approval"
        assert len(form["questions"]) == 1 and form["closed"] and len(resumed) == 1
    assert not cv.expectation_state(parent)["satisfied_by"]
