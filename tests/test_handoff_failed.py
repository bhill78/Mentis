"""A failed, unrecorded hand-off is visible unfinished work, not a stop."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mentis.conversation import text
from mentis.operational import completion
from mentis.operational import work_overview
from mentis.operational.work import (_as_detail, _failed_handoff_from_acts,
                                     trunk_status)
from tests._loop import a_conversation, world  # noqa: F401


EXECUTION = "magnet-carrier"
REAL_EXECUTION = "ccdfaccc-bb42-4c6f-802f-253094f6da17"
REMAINING = "re-review and integration remain unconfirmed"
AUDIT_EXPORT = Path(
    "C:/Users/bhill/AppData/Local/Temp/claude/30441dcd84dbe9f1/"
    "c602828a-e801-42fc-b682-7a9cf91b9163/scratchpad/audit/"
    "operational-by-execution.json")


def _request(world):
    cv = world["cv"]
    cid = a_conversation(world)
    owner, carrier = world["who"]["@brian"], world["steward"]
    turn = cv.say(cid, owner, [text("finish the integrated candidate")])
    request = cv.expect(turn, of=carrier, kind="result", by=owner)
    start = cv.record_act(actor=carrier, act="execution-started", conversation=cid,
                          execution=EXECUTION, runtime="codex", caused_by=request)
    return cv, cid, request, start, owner, carrier


def _authorize_delegate(cv, cid, start, carrier):
    return cv.record_act(
        actor=carrier, act="operation-answered", conversation=cid,
        execution=EXECUTION, runtime="codex", caused_by=start,
        because="allowed by grant: Use its Mentis tool delegate",
        detail={"answer": "allowed", "by": "grant", "operation": {
            "category": "mentis", "command": None, "cwd": None, "outside": [],
            "resources": [], "summary": "Use its Mentis tool delegate",
            "tool": "mcp__mentis__delegate", "tool_label": "delegate",
            "within": True}})


def _result_returned(cv, cid, start, carrier, *, failed_delegate):
    calls = [
        {"id": "exec-resolve", "kind": "execute", "locations": [],
         "name": "mcp__mentis__resolve", "status": "completed",
         "title": "mcp.mentis.resolve"},
    ]
    if failed_delegate:
        calls.append(
            {"id": "exec-edecaf6c-613a-4c35-99ea-f2b24b849ec6",
             "kind": "execute", "locations": [],
             "name": "mcp__mentis__delegate", "status": "failed",
             "title": "mcp.mentis.delegate"})
    return cv.record_act(
        actor=carrier, act="result-returned", conversation=cid,
        execution=EXECUTION, runtime="codex", caused_by=start,
        because="the run reported and this is what it said",
        detail={"terminal": "reported_done", "tool_calls": calls,
                "tool_calls_observable": True})


def _observed_failure(cv, cid, start, carrier, authorized):
    return cv.record_act(
        actor=carrier, act="operations-observed", conversation=cid,
        execution=EXECUTION, runtime="codex", caused_by=start,
        because="delegate tool call failed",
        detail={"batch": 1, "calls": [{
            "id": "tool-delegate", "first_at": cv._act(authorized)["at"] + 0.001,
            "kind": "tool",
            "name": "mcp__mentis__delegate", "title": "mcp.mentis.delegate",
            "status": "failed"}]})


def _claim(cv, cid, request, carrier, *, result="partly"):
    return completion.claim(
        cv, request, {"result": result, "summary": REMAINING, "evidence": []},
        actor=carrier, execution=EXECUTION, runtime="codex", via="reply",
        conversation=cid)


def _real_failed_sequence(world, *, result="partly"):
    cv, cid, request, start, owner, carrier = _request(world)
    _authorize_delegate(cv, cid, start, carrier)
    returned = _result_returned(cv, cid, start, carrier, failed_delegate=True)
    _claim(cv, cid, request, carrier, result=result)
    return cv, cid, request, start, owner, carrier, returned


def _status(cv, request):
    return trunk_status(cv, request, viewer=None,
                        runtime={"instances": {}, "runs": []})


@pytest.mark.parametrize("result", ["partly", "not-met"])
def test_returned_failed_delegate_with_remaining_work_is_visible_not_stopped(world, result):
    cv, cid, request, start, owner, carrier, returned = _real_failed_sequence(
        world, result=result)

    status = _status(cv, request)
    assert status["state"]["value"] == "handoff-failed"
    assert status["state"]["handoff"]["observed"] == returned
    assert REMAINING in status["state"]["label"]
    assert "same operation key" in status["next"]["value"]

    overview = work_overview.overview(
        cv, viewer=owner, runtime={"instances": {}, "runs": []}, conversation=cid)
    item = next(row for row in overview["items"] if row["expectation"] == request)
    assert item["state"] == "handoff-failed"
    assert item["stage"] == "blocked"
    assert REMAINING in item["status_words"]


def test_operations_observed_failed_delegate_is_also_visible(world):
    cv, cid, request, start, owner, carrier = _request(world)
    authorized = _authorize_delegate(cv, cid, start, carrier)
    observed = _observed_failure(cv, cid, start, carrier, authorized)
    _result_returned(cv, cid, start, carrier, failed_delegate=False)
    _claim(cv, cid, request, carrier)

    status = _status(cv, request)
    assert status["state"]["value"] == "handoff-failed"
    assert status["state"]["handoff"]["observed"] == observed


def test_a_recorded_recovery_clears_handoff_failed_through_the_existing_path(world):
    cv, cid, request, start, owner, carrier, _ = _real_failed_sequence(world)
    assert _status(cv, request)["state"]["value"] == "handoff-failed"

    worker = cv.create_participant("@Reviewer")
    turn = cv.say(cid, carrier, [text(REMAINING)], addressed_to=[worker])
    child = cv.expect(turn, of=worker, kind="result", by=carrier,
                      caused_by=request, detail={"returns_to": carrier})
    cv.record_act(actor=carrier, act="work-delegated", conversation=cid, turn=turn,
                  execution=EXECUTION, caused_by=request, about=[child],
                  detail={"participant": worker, "return_expected": True,
                          "op_key": "same-derived-key"})

    status = _status(cv, request)
    assert status["state"]["value"] != "handoff-failed"
    assert status["state"]["value"] == "claimed-partly"


def test_owner_stop_precedes_the_failed_handoff_state_and_starts_nothing(world):
    cv, cid, request, start, owner, carrier = _request(world)
    _authorize_delegate(cv, cid, start, carrier)
    _result_returned(cv, cid, start, carrier, failed_delegate=True)
    cv.record_act(actor=owner, act="work-parked", conversation=cid,
                  caused_by=request, about=[request], because="stop this work")
    _claim(cv, cid, request, carrier)

    assert _status(cv, request)["state"]["value"] == "stopped-no-continuation"
    overview = work_overview.overview(
        cv, viewer=owner, runtime={"instances": {}, "runs": []}, conversation=cid)
    item = next(row for row in overview["items"] if row["expectation"] == request)
    assert item["stage"] == "parked"
    assert "your decision" in item["stage_words"]
    assert not [a for a in cv._own_acts(request)
                if a["act"] in ("work-resumed", "work-delegated")]


def test_partial_without_a_failed_handoff_is_still_stopped_no_continuation(world):
    cv, cid, request, start, owner, carrier = _request(world)
    _result_returned(cv, cid, start, carrier, failed_delegate=False)
    _claim(cv, cid, request, carrier)
    assert _status(cv, request)["state"]["value"] == "stopped-no-continuation"


def test_successful_completion_is_unchanged(world):
    cv, cid, request, start, owner, carrier = _request(world)
    _authorize_delegate(cv, cid, start, carrier)
    _result_returned(cv, cid, start, carrier, failed_delegate=True)
    claim = completion.claim(
        cv, request, {"result": "met", "summary": "all work complete", "evidence": []},
        actor=carrier, execution=EXECUTION, runtime="codex", via="reply",
        conversation=cid)
    completion.reconcile(cv, request, claim)
    assert _status(cv, request)["state"]["value"] == "claimed-met"


@pytest.mark.skipif(not AUDIT_EXPORT.is_file(), reason="real Magnet audit export absent")
def test_real_magnet_export_derives_handoff_failed_read_only():
    acts = [act for act in json.loads(AUDIT_EXPORT.read_text(encoding="utf-8"))
            if act.get("execution") == REAL_EXECUTION]
    claim = max((act for act in acts if act.get("act") == "outcome-claimed"
                 and _as_detail(act.get("detail")).get("result") == "partly"),
                key=lambda act: act.get("at") or 0)

    failed = _failed_handoff_from_acts(_as_detail(claim["detail"]), acts)

    assert failed is not None
    assert failed["operation"] == "delegate"
    assert failed["execution"] == REAL_EXECUTION
    assert failed["observed"] == "opr-916bdd78c44a"
