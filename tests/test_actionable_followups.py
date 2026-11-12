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


def test_partial_with_awaited_work_has_continuation(world):
    cid = a_conversation(world)
    _, awaited, _ = _coordinator(world, cid)
    _, _, grant = _coordinator(world, cid)
    operate(world, grant, "await_work", expectation=awaited)
    assert not partial(world, grant)["reconciled"]["no_continuation"]


def test_unresolved_followups_survive_active_date_filter(world):
    from mentis.operational.work_overview import overview
    cid = a_conversation(world)
    _, parent, grant = _coordinator(world, cid)
    partial(world, grant)
    _, deploying, deployment_grant = _coordinator(world, cid)
    arm(world, deployment_grant)
    result = overview(world["cv"], viewer=world["who"]["@brian"], runtime=None,
                      active_since="2100-01-01T00:00:00Z")
    items = [i for i in result["items"] if i["group"] == "in_flight"]
    assert {parent, deploying} <= {x["expectation"] for x in items}


def test_keyed_arm_never_records_token_and_replay_cannot_recover_it(world):
    from mentis.opkeys import keyed
    cid = a_conversation(world)
    coach, parent, grant = _coordinator(world, cid)
    promise = operate(world, grant, "respond", text="Helper will report")["turn"]
    args = {"op_key": "arm-once", "what": "deploy", "arming_post": promise,
            "result_location": "REPORT.md"}
    def call():
        return keyed(world["state"].corpus, world["cv"], participant=coach,
                     op="arm_detached", args=args,
                     run=lambda a: operate(world, grant, "arm_detached", **a))
    first, second = call(), call()
    assert second["operation"] == first["operation"]
    assert second["replayed"] and second["token_unavailable"]
    assert "report_token" not in second
    assert first["report_token"] not in str(world["cv"].history())
    assert len([a for a in world["cv"]._own_acts(parent) if a["act"] == "detached-armed"]) == 1


def test_report_route_uses_only_operation_token_and_refuses_worker_grants(world):
    import http.client
    import json
    import urllib.parse
    cid = a_conversation(world)
    _, _, grant = _coordinator(world, cid)
    armed, _ = arm(world, grant)
    server = urllib.parse.urlparse(world["base"])
    body = json.dumps({"token": armed["report_token"], "result": "failed", "summary": "build failed"})
    def request(headers):
        connection = http.client.HTTPConnection(server.hostname, server.port)
        connection.request("POST", armed["report_path"], body=body,
            headers={"Content-Type": "application/json", "X-Mentis-Client": "1", **headers})
        answer = connection.getresponse()
        status, payload = answer.status, json.loads(answer.read())
        connection.close()
        return status, payload
    assert request({"X-Mentis-Worker": "even-with-the-right-report-token"})[0] == 403
    status, payload = request({})  # deliberately no owner authentication
    assert status == 200, payload
    assert world["cv"]._act(payload["report"])["detail"]["result"] == "failed"


def test_report_during_live_run_is_handed_over_after_it_ends_and_holds_met(world):
    from mentis.web.dispatch import resume_if_ready
    cid = a_conversation(world)
    coach, parent, grant = _coordinator(world, cid)
    cv = world["cv"]
    start = cv.record_act(actor=coach, act="execution-started", conversation=cid,
                          caused_by=parent, execution=grant["instance"])
    armed, _ = arm(world, grant)
    claimed = operate(world, grant, "respond", text="deploy in progress",
                      outcome={"result": "met"})
    report = report_http(world, armed)
    assert not report["resumed"]
    cv.record_act(actor=coach, act="result-returned", conversation=cid,
                  caused_by=start, execution=grant["instance"])
    rec = completion.reconcile(cv, parent, claimed["claim"])
    assert rec["recorded"] == "pending"
    assert any("has not been handed" in r for r in rec["reasons"])
    assert len(resume_if_ready(world["state"], parent)) == 1
    assert not resume_if_ready(world["state"], parent)
    sent = next(x for x in world["sent"] if x["expectation"] == parent)
    assert report["report"] in sent["work"]


def test_report_cannot_override_stop_on_arming_run(world):
    cid = a_conversation(world)
    coach, parent, grant = _coordinator(world, cid)
    cv = world["cv"]
    start = cv.record_act(actor=coach, act="execution-started", conversation=cid,
                          caused_by=parent, execution=grant["instance"])
    armed, _ = arm(world, grant)
    cv.record_act(actor=world["who"]["@brian"], act="execution-stop-asked",
                  caused_by=start, execution=grant["instance"])
    cv.record_act(actor=coach, act="delivery-failed", caused_by=start,
                  execution=grant["instance"], detail={"terminal": "cancelled"})
    assert not report_http(world, armed)["resumed"]


def test_report_for_met_work_is_recorded_without_resuming(world):
    cid = a_conversation(world)
    _, parent, grant = _coordinator(world, cid)
    armed, _ = arm(world, grant)
    world["cv"].record_act(actor=world["who"]["@brian"], act="expectation-met",
                           caused_by=parent, about=[parent])
    result = report_http(world, armed)
    assert result["report"] and not result["resumed"]


def test_bad_verdict_does_not_spend_token(world):
    import urllib.error
    import pytest
    cid = a_conversation(world)
    _, _, grant = _coordinator(world, cid)
    armed, _ = arm(world, grant)
    with pytest.raises(urllib.error.HTTPError) as err:
        report_http(world, armed, result="made-up")
    assert err.value.code == 400
    assert report_http(world, armed, result="rolled_back")["ok"]


def test_cli_reports_once_with_token_file(world, tmp_path, capsys):
    from tools.report_detached import main
    cid = a_conversation(world)
    _, _, grant = _coordinator(world, cid)
    armed, _ = arm(world, grant)
    secret = tmp_path / "private-token.txt"
    secret.write_text(armed["report_token"], encoding="utf-8")
    args = ["--server", world["base"], "--operation", armed["operation"],
            "--token-file", str(secret), "--result", "unknown", "--summary", "verdict unavailable",
            "--evidence", "release/REPORT.md"]
    assert main(args) == 0
    assert main(args) == 1
    output = capsys.readouterr()
    assert armed["report_token"] not in output.out + output.err


def test_a_person_can_continue_after_stop_and_reconcile_the_durable_report(world):
    cid = a_conversation(world)
    coach, parent, grant = _coordinator(world, cid)
    cv = world["cv"]
    start = cv.record_act(actor=coach, act="execution-started", conversation=cid,
                          caused_by=parent, execution=grant["instance"])
    armed, _ = arm(world, grant)
    cv.record_act(actor=world["who"]["@brian"], act="execution-stop-asked", caused_by=start)
    cv.record_act(actor=coach, act="delivery-failed", caused_by=start,
                  execution=grant["instance"], detail={"terminal": "cancelled"})
    report = report_http(world, armed)
    assert not report["resumed"]
    later = cv.record_act(actor=coach, act="execution-started", conversation=cid,
                          caused_by=parent, execution="explicit-owner-continuation")
    claim = completion.claim(cv, parent, {"result": "met", "evidence": [report["report"]]},
                             actor=coach, execution="explicit-owner-continuation", via="reply")
    cv.record_act(actor=coach, act="result-returned", caused_by=later,
                  execution="explicit-owner-continuation")
    assert completion.reconcile(cv, parent, claim)["recorded"] == "met"


def test_concurrent_reports_spend_the_token_once(world):
    import concurrent.futures
    import urllib.error
    cid = a_conversation(world)
    _, parent, grant = _coordinator(world, cid)
    armed, promise = arm(world, grant)
    def send():
        try:
            return report_http(world, armed)["report"]
        except urllib.error.HTTPError as err:
            return err.code
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: send(), range(2)))
    assert len([x for x in results if x == 403]) == 1
    assert len([a for a in world["cv"]._own_acts(parent) if a["act"] == "detached-reported"]) == 1
    assert len(world["cv"]._replies_to(promise)) == 1
