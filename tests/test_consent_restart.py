"""Round 2 (O2): consent narrowing and automatic restart, requirement by requirement.

Program section 4. Each test names the requirement it pins; requirements
already pinned in `test_permission_compiled.py` are named in
docs/modernization/CONTRACT.md "Round 2 — A" with their tests.
"""

from __future__ import annotations

import pytest

from mentis.operational import consent as C
from mentis.web import compiled_runs
from mentis.web import permissions as P
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_permission_compiled import (_Agents, _halt_for_real, _halted_and_ended,
                                            _restart_asked, _tracked_run, _wait)


def test_the_replacement_starts_only_after_the_old_execution_ended(world, tmp_path, monkeypatch):
    """Requirement: the old execution is halted before replacement work
    proceeds; the replacement receives the new consent and a grant of its own."""
    cv, cid, exp, run, specs = _halt_for_real(world, tmp_path, monkeypatch)
    assert _wait(lambda: len(specs) >= 2)
    end = cv.run_end(run)
    restarted = [a for a in cv._c.operational(caused_by=exp) if a["act"] == compiled_runs.RESTARTED]
    starts = sorted((a for a in cv._c.operational(caused_by=exp)
                     if a["act"] == "execution-started"), key=lambda a: a["at"])
    assert len(starts) == 2 and starts[0]["id"] == run
    assert end["at"] <= restarted[0]["at"] <= starts[1]["at"]
    fresh = specs[1]
    assert fresh.run_id != specs[0].run_id and fresh.resume is None
    assert fresh.consent["mode"] == "deny"
    assert "Bash" not in fresh.consent["runtime_rules"]["allow"]


def test_the_replacement_is_composed_from_the_record_not_the_stale_session(world, monkeypatch):
    """Requirement: new owner instructions and Workflow changes are preserved.
    The restart passes the halted dispatch's own words, deadline, model and
    Persona, plus follow-ups shown to it, and NOTHING that carries governance:
    the replacement's Workflow, governance and consent are read from the
    record when it is dispatched, so a change made meanwhile is what it gets."""
    import mentis.web as web
    cv, run, repo, told = _tracked_run(world, {"mode": "all"})
    monkeypatch.setattr(cv, "_compiled_st", type("S", (), {"agents": _Agents()})(), raising=False)
    C.set_task(cv, run, owner=world["who"]["@brian"],
               consent={"mode": "deny", "workspaces": [repo]}, because="narrowed")
    assert P._audit_for(cv).flush()
    start = cv._act(run)
    cv.record_act(actor=world["steward"], act="delivery-failed", conversation=start["conversation"],
                  turn=start["turn"], execution="inst-t", runtime="claude", caused_by=run,
                  because="cancelled", detail={"terminal": "cancelled"})
    sent = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: sent.append(kw))
    dispatched = {"conversation": start["conversation"], "turn": start["turn"],
                  "participant": world["steward"], "expectation": start["caused_by"],
                  "work": "do it", "resumed_from": "opr-x", "triggered_at": 1.0,
                  "new_instance": True, "model": "m"}
    got = compiled_runs.restart_if_asked(world["state"], run, dispatched=dispatched)
    assert sent == [got]
    assert set(got) <= {"conversation", "turn", "participant", "expectation", "work",
                        "model", "because"}
    assert not {"resumed_from", "triggered_at", "new_instance"} & set(got)


def test_a_withdrawn_request_is_never_restarted(world, monkeypatch):
    """Requirement: explicit owner withdrawal is never overridden."""
    import mentis.web as web
    cv, run, exp = _halted_and_ended(world, monkeypatch)
    cv.record_act(actor=world["who"]["@brian"], act="expectation-met", caused_by=exp,
                  about=[exp], because="withdrawn by the owner", detail={"withdrawn": True})
    sent = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: sent.append(kw))
    assert compiled_runs.restart_if_asked(world["state"], run) is None
    assert sent == []


def test_a_normal_end_is_never_restarted(world, monkeypatch):
    """Requirement: no restart merely because a runtime ended normally (no
    narrowing was recorded for the run)."""
    import mentis.web as web
    cv, run, repo, told = _tracked_run(world, {"mode": "all"})
    start = cv._act(run)
    cv.record_act(actor=world["steward"], act="result-returned", conversation=start["conversation"],
                  turn=start["turn"], execution="inst-t", runtime="claude", caused_by=run,
                  because="done", detail={})
    sent = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: sent.append(kw))
    assert compiled_runs.restart_if_asked(world["state"], run) is None
    assert sent == [] and not _restart_asked(cv, run)


def _ended_child(world, act, detail, *, halted=False, stopped=False):
    cid = a_conversation(world, "States")
    turn = say(world, cid, "work")["turn"]
    cv = world["cv"]
    exp = cv.expect(turn, of=world["steward"], kind="result", by=world["who"]["@brian"])
    run = cv.record_act(actor=world["steward"], act="execution-started", conversation=cid,
                        turn=turn, execution="inst-s", runtime="claude", caused_by=exp,
                        because="t", detail={})
    if halted:
        cv.record_act(actor="mentis", act=compiled_runs.RESTART_ASKED, conversation=cid,
                      turn=turn, caused_by=run, because="narrowed",
                      detail={"reason": "consent-narrowed"})
    if stopped:
        cv.record_act(actor=world["who"]["@brian"], act=compiled_runs.STOP_ASKED,
                      conversation=cid, turn=turn, caused_by=run, because="stop")
    cv.record_act(actor=world["steward"], act=act, conversation=cid, turn=turn,
                  execution="inst-s", runtime="claude", caused_by=run, because="ended",
                  detail=detail)
    return cv._child_state(exp)["state"]


def test_interruption_cancellation_failure_and_completion_stay_distinct(world):
    """Requirement: interruption (halted for a consent change), cancellation
    (the owner's Stop), failure and an ordinary end are four states; none is
    completion -- a run's end is never a claim (WS-C)."""
    got = {
        "interrupted": _ended_child(world, "delivery-failed", {"terminal": "cancelled"},
                                    halted=True),
        "cancelled": _ended_child(world, "delivery-failed", {"terminal": "cancelled"},
                                  halted=True, stopped=True),
        "failed": _ended_child(world, "delivery-failed", {}),
        "returned": _ended_child(world, "result-returned", {}),
    }
    assert got == {"interrupted": "interrupted", "cancelled": "cancelled",
                   "failed": "failed", "returned": "returned"}


def test_unrestartable_work_says_its_actual_reason(world, monkeypatch):
    """Requirement: unrestartable work appears in Needs You with its actual
    reason -- the cap, or a restart that never started."""
    from mentis.operational.work import trunk_status
    cv, run, exp = _halted_and_ended(world, monkeypatch, cap=True)
    state = trunk_status(cv, exp)["state"]
    assert state["value"] == "consent-stopped" and "held at the limit" in state["why"]
    cv2, run2, exp2 = _halted_and_ended(world, monkeypatch, cap=False)
    state2 = trunk_status(cv2, exp2)["state"]
    assert state2["value"] == "consent-stopped" and "held at the limit" not in state2["why"]
    assert state2["why"]


@pytest.mark.parametrize("narrowing", [{"mode": "ask"}, {"mode": "task"}, {"mode": "deny"}])
def test_every_narrowing_from_approve_all_halts(world, monkeypatch, narrowing):
    """Requirement: narrowing takes effect against the active execution."""
    cv, run, repo, told = _tracked_run(world, {"mode": "all"})
    agents = _Agents()
    monkeypatch.setattr(cv, "_compiled_st", type("S", (), {"agents": agents})(), raising=False)
    C.set_task(cv, run, owner=world["who"]["@brian"],
               consent={**narrowing, "workspaces": [repo], "categories": ["read", "edit"]},
               because="narrowed")
    assert agents.tries == 1 and compiled_runs.halting(cv, run)
    assert P._audit_for(cv).flush() and _restart_asked(cv, run)
    compiled_runs.untrack(cv, run)
