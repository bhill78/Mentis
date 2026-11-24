"""Managed dispatch through the returned actual-send gate, on fixture Brains.

FakeExecution covers the complete request/service path. The real MarsExecution
cases use an ACP stand-in process, never live MARS or a real agent.
"""
import json
import sys
from pathlib import Path

import pytest

from mentis.conversation import versions
from mentis.execution import RunResult
from mentis.execution.mars import MarsExecution
from mentis.fluid import message_context as MC
from mentis.web import dispatch as D
from tests._loop import world, script_every_backend  # noqa: F401
from tests.test_agent_request_routing import a_magnet
from tests.test_magnet_message_boundary import request, send, routed


def asking(world, *, runtime="codex", persona=None):
    mid = a_magnet(world, sources=[])
    body = request(world, mid, action="ask-participant")
    body["dispatch"][0]["runtime"] = runtime
    if persona:
        body["dispatch"][0]["persona"] = persona
    status, answer = send(world, body)
    assert status == 200, answer
    return body, answer


def audit(world, answer):
    return world["cv"]._c.operational(act=MC.AUDIT, turn=answer["post"])


@pytest.mark.parametrize("change", ["edit", "delete", "revert", "stop", "grant", "widened-grant"])
def test_change_after_open_refuses_the_actual_managed_send(world, change):
    body, answer = asking(world)
    svc, cv = world["state"].agents, world["cv"]

    def before_send(spec):
        if change == "grant":
            svc.authority.revoke(spec.run_id)
        elif change == "widened-grant":
            authority = svc.authority.grant_for(svc.authority.grant_of(spec.run_id), world["state"].path)
            svc.authority.authorise_for(spec.run_id, {**authority, "scope": "organising", "operations": None})
        elif change == "stop":
            cv.record_act(actor=body["author"], act="work-parked", turn=answer["post"],
                          conversation=answer["home"], caused_by=answer["expectations"][0],
                          because="stop before actual send")
        elif change == "delete":
            versions.delete(cv, answer["post"], by=body["author"])
        else:
            versions.edit(cv, answer["post"], text="changed after session open", by=body["author"])
            if change == "revert":
                versions.edit(cv, answer["post"], text=body["text"], by=body["author"])

    svc.execution.before_send = before_send
    result = D.dispatch(world["state"], **world["sent"][0])
    assert result.get("ok") is False or result.get("terminal") == "cancelled", result
    assert svc.execution.sent == []
    states = [a["detail"]["state"] for a in audit(world, answer)]
    assert "refused" in states and "supplied" not in states and "reserved" not in states
    refused = [a for a in audit(world, answer) if a["detail"].get("phase") == "delivery"]
    assert len(refused) == 1
    assert refused[0]["execution"] and refused[0]["caused_by"] == answer["expectations"][0]
    if change == "grant":
        assert refused[0]["detail"]["grant"] is None
    else:
        assert refused[0]["detail"]["grant"]["instance"] == refused[0]["execution"]
        assert refused[0]["detail"]["grant"]["expectation"] == answer["expectations"][0]
    assert refused[0]["detail"]["refusal"]["code"] == {
        "edit": "authored-revision-changed", "delete": "authored-revision-changed",
        "revert": "authored-revision-changed", "stop": "owner-stopped",
        "grant": "authority-changed", "widened-grant": "authority-changed"}[change]
    if change in ("edit", "delete", "revert"):
        assert refused[0]["detail"]["refusal"]["expected_version"] == answer["post"]
        assert refused[0]["detail"]["refusal"]["observed_version"] != answer["post"]


@pytest.mark.parametrize("outcome, expected", [("ok", "supplied"), ("fail", "failed"), ("unknown", "unconfirmed")])
def test_delivery_reports_keep_reservation_identity_and_actual_grant(world, outcome, expected):
    body, answer = asking(world)
    seen = []

    def perform(spec):
        seen.append(spec)
        # Callback replay cannot manufacture another audit event.
        if outcome == "ok":
            return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                             stop_reason="end_turn", text="setup help")
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         error_kind="agent_error" if outcome == "fail" else None,
                         error="fixture send was not acknowledged")

    script_every_backend(world["state"].agents, perform)
    D.dispatch(world["state"], **world["sent"][0])
    rows = audit(world, answer)
    assert [a["detail"]["state"] for a in rows] == ["prepared", "reserved", "sent", expected]
    reserved, supplied = rows[1], rows[-1]
    detail = supplied["detail"]
    frozen = routed(world, answer)["managed_context"]
    assert detail["reservation"]["id"] == reserved["id"]
    assert detail["context_digest"] == frozen["context_digest"]
    assert detail["authored_version"] == answer["post"]
    assert detail["grant"] == reserved["detail"]["grant"]
    assert detail["grant"]["expectation"] == answer["expectations"][0]
    assert detail["grant"]["scope"] == "worker"
    assert detail["grant"]["run"] == detail["run"]
    assert detail["grant"]["instance"] == supplied["execution"]
    assert reserved["detail"]["prepared_payloads"]["full"] == MC.text_digest(seen[0].prompt)
    assert rows[2]["detail"]["acknowledged"] is None
    if expected == "supplied":
        assert detail["acknowledged"] == "prompt_result"
    else:
        assert detail["acknowledged"] is None
        assert not any(a["detail"]["state"] == "supplied" for a in rows)
    replay = {"state": expected, "run": seen[0].run_id, "send": 1,
              "reservation": detail["reservation"], "acknowledged": detail["acknowledged"],
              "sent_at": detail["sent_at"]}
    seen[0].on_delivery(replay)
    seen[0].on_delivery({**replay, "state": "sent", "acknowledged": None})
    assert len(audit(world, answer)) == len(rows)


def test_edit_after_reservation_preserves_accepted_supply_and_refuses_further_send(world):
    body, answer = asking(world)
    cv = world["cv"]

    def after_send(spec):
        versions.edit(cv, answer["post"], text="new words after handover", by=body["author"])
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="original accepted answer")

    script_every_backend(world["state"].agents, after_send)
    D.dispatch(world["state"], **world["sent"][0])
    supplied = audit(world, answer)[-1]
    assert supplied["detail"]["state"] == "supplied"
    assert supplied["detail"]["authored_version"] == answer["post"]
    assert cv._c.read([answer["post"]])[0]["body"]["parts"] == body["parts"]
    with pytest.raises(versions.Refused):
        MC.accepted(cv, answer["expectations"][0])
    before = len(world["state"].agents.execution.sent)
    result = D.dispatch(world["state"], **world["sent"][0])
    assert result["ok"] is False
    assert len(world["state"].agents.execution.sent) == before


@pytest.mark.parametrize("mode, edit, terminal", [("ok", True, "refused"), ("ok", False, "supplied"),
    ("quiet", False, "supplied"), ("ack-fail", False, "supplied"),
    ("refuse", False, "failed"), ("vanish", False, "unconfirmed")])
def test_real_acp_managed_dispatch_gate_and_delivery(world, tmp_path, monkeypatch, mode, edit, terminal):
    body, answer = asking(world, runtime="stand-in", persona=world["persona"])
    svc = world["state"].agents
    delivered = []
    record_delivery = world["cv"].record_delivery
    def record(*args, **kw):
        delivered.append((args, kw))
        return record_delivery(*args, **kw)
    monkeypatch.setattr(world["cv"], "record_delivery", record)
    stand_in = Path(__file__).with_name("fakes") / (
        "magnet_send_boundary_stand_in.py" if mode == "ack-fail" else "mars_send_boundary_stand_in.py")
    log = tmp_path / "managed-acp.jsonl"

    class Window(MarsExecution):
        def perform(self, spec, *args, **kw):
            original = spec.on_open
            def opened(applied):
                if original:
                    original(applied)
                if edit:
                    versions.edit(world["cv"], answer["post"], text="edit after real session open", by=body["author"])
            from dataclasses import replace
            return super().perform(replace(spec, on_open=opened), *args, **kw)

    execution = Window([sys.executable, str(stand_in), str(log), mode], startup_s=30)
    svc.execution = execution
    try:
        result = D.dispatch(world["state"], **world["sent"][0])
    finally:
        execution.close()
    assert log.exists(), result
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in events] == (["new"] if edit else ["new", "prompt"])
    rows = audit(world, answer)
    assert rows[-1]["detail"]["state"] == terminal
    assert bool(delivered) is (terminal == "supplied"), "session open alone is not governing-material delivery"
    if not edit:
        frozen = routed(world, answer)["managed_context"]
        assert MC.payload(frozen) in events[1]["text"]
        assert body["text"] in events[1]["text"]
    if terminal == "supplied":
        assert rows[-1]["detail"]["acknowledged"] == ("prompt_result" if mode == "quiet" else "session_update")
        assert rows[-1]["detail"]["acknowledged_at"] >= rows[-1]["detail"]["sent_at"]
        if mode == "ack-fail":
            assert result.get("ok") is False, result
    else:
        assert not any(row["detail"]["state"] == "supplied" for row in rows)


def test_reservation_record_failure_sends_nothing_and_keeps_no_reserved_audit(world, monkeypatch):
    _, answer = asking(world)
    record = MC.audit
    def cannot_reserve(cv, context, state, **kw):
        if state == "reserved":
            raise OSError("fixture reservation cannot be committed")
        return record(cv, context, state, **kw)
    monkeypatch.setattr(MC, "audit", cannot_reserve)
    result = D.dispatch(world["state"], **world["sent"][0])
    assert result.get("ok") is False or result.get("terminal") == "cancelled", result
    assert world["state"].agents.execution.sent == []
    assert [a["detail"]["state"] for a in audit(world, answer)] == ["prepared", "refused"]
    assert "could not be confirmed" in audit(world, answer)[-1]["because"]


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("edit_in_window", [False, True])
def test_continuation_reserves_the_same_context_and_checks_the_actual_send_window(world, native, edit_in_window):
    body, answer = asking(world)
    st, cv = world["state"], world["cv"]
    ex = st.agents.execution
    ex.resumes = native
    start = world["sent"][0]
    assert D.dispatch(st, **start)["ok"]
    first_sent = len(ex.sent)
    if edit_in_window:
        ex.before_send = lambda spec: versions.edit(cv, answer["post"],
            text="edited while continuation session opens", by=body["author"])
    resumed = cv.record_act(actor=body["author"], act="work-resumed",
        conversation=answer["home"], turn=answer["post"], caused_by=start["expectation"])
    result = D.dispatch(st, **{**start, "resumed_from": resumed, "work": "Continue this request."})
    assert result["ok"] is (not edit_in_window), result
    assert len(ex.sent) == first_sent + (not edit_in_window)
    rows = audit(world, answer)
    if edit_in_window:
        assert rows[-1]["detail"]["state"] == "refused"
        assert rows[-1]["detail"]["refusal"]["expected_version"] == answer["post"]
    else:
        last = rows[-1]["detail"]
        assert last["state"] == "supplied"
        assert MC.text_digest(ex.sent[-1]) in last["reservation"]["prepared_payloads"].values()
        assert last["context_digest"] == routed(world, answer)["managed_context"]["context_digest"]
        supplied = [a for a in rows if a["detail"]["state"] == "supplied"]
        assert len(supplied) == len({a["detail"]["run"] for a in supplied}) == 2
