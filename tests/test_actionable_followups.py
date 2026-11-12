"""Record-shaped approval, continuation and detached reporting regressions."""
from __future__ import annotations

from mentis.operational import completion
from mentis.web import _surface
from mentis.worker import _operate
from tests._loop import _coordinator, a_conversation, world  # noqa: F401
from tests.test_decision_resume_parent import _answer, _form_of


def operate(world, grant, name, **args):
    return _operate(_surface(world["state"]), name, args, grant)


def test_approval_claim_keeps_request_pending_and_answer_resumes_named_artifact(world):
    cid = a_conversation(world)
    coach, parent, grant = _coordinator(world, cid)
    out = operate(world, grant, "respond", text="Candidate 4037e33 is ready.",
                  outcome={"result": "met", "approval": {"artifacts": ["commit 4037e33", "adm-review"]}})
    form = _form_of(world["cv"], parent)
    assert form["post"] == out["turn"]
    assert "4037e33" in form["questions"][0]["question"]
    assert out["reconciled"]["recorded"] == "pending"
    assert not world["cv"].expectation_state(parent)["satisfied_by"]
    _answer(world, form, "Approve")
    resumed = [x for x in world["sent"] if x["expectation"] == parent]
    assert len(resumed) == 1
    assert resumed[0]["participant"] == coach
    assert "4037e33" in resumed[0]["work"] and out["turn"] in resumed[0]["work"]


def test_final_block_approval_uses_same_decision_path(world):
    cid = a_conversation(world)
    coach, parent, _ = _coordinator(world, cid)
    turn = world["cv"].say(cid, coach, [{"type": "text", "text": "design"}])
    outcome, _ = completion.extract("Ready\n\n```outcome\nresult: met\napproval: commit abc123\n```" )
    claim = completion.claim(world["cv"], parent, outcome, actor=coach,
                             via="final-reply", reply_turn=turn)
    assert completion.reconcile(world["cv"], parent, claim)["recorded"] == "pending"
    assert "abc123" in _form_of(world["cv"], parent)["questions"][0]["question"]


def arm(world, grant):
    post = operate(world, grant, "respond", text="Deployment armed; its helper will report.")["turn"]
    return operate(world, grant, "arm_detached", what="deploy commit 4037e33",
                   result_location="release/REPORT.md", arming_post=post, pid=1234), post


def partial(world, grant, **more):
    return operate(world, grant, "respond", text="Work remains.",
                   outcome={"result": "partly", "summary": "waiting", **more})


def work_item(world, parent):
    from mentis.operational.work_overview import detail
    return detail(world["cv"], parent, viewer=world["who"]["@brian"], runtime=None)


def test_partial_without_continuation_is_recorded_warned_and_visible(world):
    cid = a_conversation(world)
    _, parent, grant = _coordinator(world, cid)
    out = partial(world, grant)
    assert out["reconciled"]["recorded"] == "partly"
    assert out["reconciled"]["no_continuation"] is True
    assert "stopped: nothing will resume it" in out["note"]
    assert "arm_detached" in out["note"]
    assert world["cv"]._act(out["claim"])["detail"]["no_continuation"]
    item = work_item(world, parent)
    assert item["status_words"] == "stopped: nothing will resume it"
    assert item["group"] == "in_flight"


def test_partial_with_named_owner_wait_is_explicitly_manual(world):
    cid = a_conversation(world)
    _, _, grant = _coordinator(world, cid)
    out = partial(world, grant, owner_wait="owner supplies the missing design")
    assert not out["reconciled"]["no_continuation"]
    assert out["reconciled"]["continuation"]["sources"] == [
        {"kind": "owner-wait", "action": "owner supplies the missing design", "automatic": False}]


def test_partial_with_open_decision_has_continuation(world):
    cid = a_conversation(world)
    _, _, grant = _coordinator(world, cid)
    operate(world, grant, "request_decision", question="Approve commit abc123?")
    assert not partial(world, grant)["reconciled"]["no_continuation"]


def test_partial_with_awaited_child_has_continuation(world):
    from tests.test_delegate_coordinate import _present
    cid = a_conversation(world)
    _, _, grant = _coordinator(world, cid)
    child = _present(world, cid, "@Builder")
    operate(world, grant, "delegate", participant=child, work="build", resume_on_return=True)
    assert not partial(world, grant)["reconciled"]["no_continuation"]


def test_partial_with_armed_operation_has_continuation_and_visible_no_report(world):
    cid = a_conversation(world)
    _, parent, grant = _coordinator(world, cid)
    armed, promise = arm(world, grant)
    assert not partial(world, grant)["reconciled"]["no_continuation"]
    item = work_item(world, parent)
    assert "armed " in item["status_words"] and "no report yet" in item["status_words"]
    assert item["detached"][0]["arming_post"] == promise
    assert armed["report_token"] not in str(world["cv"].history())


def report_http(world, armed, **more):
    from tests._loop import post
    return post(world, armed["report_path"], {
        "token": armed["report_token"], "result": "succeeded",
        "summary": "4037e33 deployed; smoke passed", "evidence": ["release/REPORT.md"], **more})


def test_report_after_restart_replies_and_resumes_originating_request_then_reconciles(world):
    import json
    import threading
    from http.server import ThreadingHTTPServer
    from mentis.web import _Handler, _State
    from mentis.web import dispatch as D
    from tests._loop import script_every_backend
    from mentis.execution import RunResult
    import time
    cid = a_conversation(world)
    coach, parent, grant = _coordinator(world, cid)
    armed, promise = arm(world, grant)
    partial(world, grant)
    # A newer request in the same conversation must not receive this result.
    _, newer, _ = _coordinator(world, cid)
    fresh = _State(world["root"])
    server = ThreadingHTTPServer(("127.0.0.1", 0), type("Restarted", (_Handler,), {"state": fresh}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    restarted = {**world, "base": f"http://127.0.0.1:{server.server_address[1]}"}
    try:
        report = report_http(restarted, armed)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
    assert report["expectation"] == parent
    assert fresh.cv._act(report["report"])["caused_by"] == parent
    replies = fresh.cv._replies_to(promise)
    assert report["turn"] in [x["link"]["from"] for x in replies]
    assert not fresh.cv.expectation_state(parent)["satisfied_by"]
    resumed = fresh.cv._act(report["resumed"])
    assert resumed["detail"]["event"] == {"kind": "detached-reported",
        "expectation": parent, "operation": armed["operation"],
        "report": report["report"], "arming_post": promise}
    dispatch = next(x for x in world["sent"] if x["expectation"] == parent)
    assert dispatch["participant"] == coach and "4037e33" in dispatch["work"]
    for ref in (parent, report["report"], promise, armed["operation"]):
        assert ref in dispatch["work"]
    assert newer not in dispatch["work"]
    def perform(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", started_at=now, finished_at=now,
                         text="Verified deploy result.\n\n```outcome\nresult: met\nsummary: deployed 4037e33\n```")
    script_every_backend(fresh.agents, perform)
    D.dispatch(fresh, **dispatch)
    assert fresh.cv.expectation_state(parent)["satisfied_by"]
    assert not fresh.cv.expectation_state(newer)["satisfied_by"]
    assert len([a for a in fresh.cv._own_acts(parent) if a["act"] == "work-resumed"]) == 1
    assert armed["report_token"] not in json.dumps(fresh.cv.history(), default=str)


def test_token_wrong_missing_arm_and_second_report_are_refused_without_writes(world):
    import urllib.error
    import pytest
    cid = a_conversation(world)
    _, _, grant = _coordinator(world, cid)
    armed, _ = arm(world, grant)
    for bad in ({**armed, "report_token": "wrong"},
                {**armed, "report_path": "/api/detached/opr-missing/report"}):
        before = len(world["cv"].history())
        with pytest.raises(urllib.error.HTTPError) as err:
            report_http(world, bad)
        assert err.value.code == 403
        assert len(world["cv"].history()) == before
    report_http(world, armed)
    before = len(world["cv"].history())
    with pytest.raises(urllib.error.HTTPError) as err:
        report_http(world, armed)
    assert err.value.code == 403
    assert len(world["cv"].history()) == before


def test_report_for_withdrawn_work_is_recorded_and_shown_without_resume(world):
    cid = a_conversation(world)
    _, parent, grant = _coordinator(world, cid)
    armed, _ = arm(world, grant)
    world["cv"].record_act(actor=world["who"]["@brian"], act="expectation-met",
        conversation=cid, caused_by=parent, about=[parent], detail={"withdrawn": True})
    report = report_http(world, armed)
    assert not report["resumed"]
    assert world["cv"]._act(report["report"])["detail"]["result"] == "succeeded"
    assert work_item(world, parent)["detached"][0]["report"]["id"] == report["report"]
