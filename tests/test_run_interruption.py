"""Runs a stopped server left open are ended `interrupted` by the next one.

The execution is over; the work may remain open. `runs.interrupted_by_restart`
(a server's start) and `Conversations.interrupt_run` (the one write), and how
`/api/working` then shows them: not open, and kept among the ended with what
actually happened to them.
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from mentis.evidence import failure_class
from mentis.operational.runs import interrupted_by_restart, run_state
from tests._loop import a_conversation, say, world  # noqa: F401


def _get(world, path):
    req = urllib.request.Request(world["base"] + path, headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _request(world, conversation, of):
    """An owner request in the conversation. The fixture world arrives with
    runs of its own left open, so what was open before is ended first and
    each test starts from a record with none."""
    cv = world["cv"]
    interrupted_by_restart(cv)
    turn = say(world, conversation, "please do this")["turn"]
    return turn, cv.expect(turn, of=of, kind="result", by=world["who"]["@brian"])


def _start(world, conversation, who, instance, request=None, turn=None):
    return world["cv"].record_act(
        actor=who, act="execution-started", conversation=conversation,
        turn=turn, caused_by=request, execution=instance, runtime="fake",
        because="test run")


def _end(world, run, act, **kw):
    cv = world["cv"]
    start = cv._act(run)
    return cv.record_act(actor=start["actor"], act=act,
                         conversation=start["conversation"], turn=start.get("turn"),
                         execution=start["execution"], runtime="fake",
                         caused_by=run, **kw)


def test_a_restart_with_several_agents_running_ends_each_run_and_no_work(world):
    cv = world["cv"]
    care, owner = world["steward"], world["who"]["@brian"]
    a, b = a_conversation(world, "Here"), a_conversation(world, "Elsewhere")
    turn_a, req_a = _request(world, a, care)
    turn_b, req_b = _request(world, b, care)
    # a run that returned, and one somebody stopped: both over before the restart
    done = _start(world, a, care, "inst-done", req_a, turn_a)
    returned = _end(world, done, "result-returned", because="it reported")
    stopped = _start(world, a, care, "inst-stopped", req_a, turn_a)
    cancelled = _end(world, stopped, "delivery-failed",
                     because="terminal 'cancelled', exit None: stop reason 'cancelled'",
                     detail={"terminal": "cancelled"})
    # two agents mid-run when the server stopped, one of them with activity
    one = _start(world, a, care, "inst-1", req_a, turn_a)
    seen = cv.record_act(actor=care, act="operations-observed", conversation=a,
                         turn=turn_a, execution="inst-1", caused_by=one,
                         because="3 tool calls seen")
    two = _start(world, b, care, "inst-2", req_b, turn_b)
    before = len(cv.history())

    found = interrupted_by_restart(cv, server={"pid": 1})

    assert [f["run"] for f in found] == [one, two]
    assert [f["request"] for f in found] == [req_a, req_b]
    assert cv.open_runs() == []
    # only the two ends were written; nothing was rewritten or removed
    assert len(cv.history()) == before + 2
    assert cv._act(one)["act"] == "execution-started"
    assert seen in [x["id"] for x in cv.history(caused_by=one)]
    for f in found:
        end = cv.run_end(f["run"])
        assert end["id"] == f["act"] and end["act"] == "delivery-failed"
        assert end["actor"] == "mentis"
        assert end["detail"]["terminal"] == "interrupted"
        assert end["detail"]["observed_end"] is False and end["detail"]["result"] is None
        assert failure_class(end) == "interrupted"
        assert run_state(cv._act(f["run"]), end)["state"] == "interrupted"
    # the runs that had already ended keep the end they had
    assert cv.run_end(done)["id"] == returned
    assert cv.run_end(stopped)["id"] == cancelled
    # THE WORK STAYS OPEN: nothing claimed, nothing met, nobody answered
    for req in (req_a, req_b):
        state = cv.expectation_state(req)
        assert not state["satisfied_by"] and not state["withdrawn"]
        assert not state["live_execution"]
        assert not [x for x in cv.history(caused_by=req)
                    if x["act"] in ("outcome-claimed", "expectation-met")]
    assert cv._child_state(req_b)["state"] == "interrupted"
    # once: a second start finds nothing to end
    assert interrupted_by_restart(cv) == []
    assert len(cv.history()) == before + 2


def test_restart_records_exact_run_started_at_evidence_key(world):
    cv = world["cv"]
    interrupted_by_restart(cv)
    a = a_conversation(world, "Here")
    run = _start(world, a, world["steward"], "inst-evidence")
    started_at = cv._act(run)["at"]
    server = {"pid": 1234}

    found = interrupted_by_restart(cv, server=server)

    assert len(found) == 1 and found[0]["run"] == run
    # Read the durable act directly, rather than the helper's return value.
    end = cv.corpus.operational(id=found[0]["act"])[0]
    assert end["caused_by"] == run
    assert end["detail"]["terminal"] == "interrupted"
    evidence = end["detail"]["evidence"]
    assert set(evidence) == {"found_by", "server", "run_started_at", "why"}
    assert evidence["run_started_at"] == started_at
    assert evidence["found_by"] == "server-start"
    assert evidence["server"] == server


def test_working_shows_interrupted_runs_as_ended_not_as_possibly_running(world):
    cv, st = world["cv"], world["state"]
    care = world["steward"]
    a = a_conversation(world, "Here")
    turn, req = _request(world, a, care)
    gone = _start(world, a, care, "inst-gone", req, turn)
    assert [r["state"] for r in _get(world, "/api/working")["open"]
            if r["run"] == gone] == ["unknown"]

    interrupted_by_restart(cv)
    # a run started after the restart, held by this server, is untouched
    live = _start(world, a, care, "inst-live", req, turn)
    st.agents.agents_open_run("inst-live", live)

    got = _get(world, "/api/working")
    assert [r["run"] for r in got["open"]] == [live]
    row = next(r for r in got["ended"] if r["run"] == gone)
    assert row["state"] == "interrupted" and row["source"] == "recorded"
    assert "stays open" in row["words"] and row["expectation"] == req
    acts = {r["participant"]: r for r in _get(world, "/api/activity")["activity"]}
    assert [r["run"] for r in acts[care]["runs"]] == [live]


def test_a_run_this_process_holds_is_never_ended(world):
    cv = world["cv"]
    a = a_conversation(world, "Here")
    interrupted_by_restart(cv)
    held = _start(world, a, world["steward"], "inst-held")
    assert interrupted_by_restart(cv, held=[held]) == []
    assert cv.run_end(held) is None


def test_a_delegated_run_whose_parent_run_ended_is_ended_and_holds_its_parent(world):
    """The child's run was open when the server stopped; the parent's had
    already returned. The child's run ends interrupted, its request stays
    owed, and the parent work is not resumed by itself."""
    cv = world["cv"]
    care, owner = world["steward"], world["who"]["@brian"]
    a = a_conversation(world, "Here")
    turn, parent = _request(world, a, care)
    prun = _start(world, a, care, "inst-parent", parent, turn)
    child = cv.expect(turn, of=care, kind="result", by=care, caused_by=parent)
    cv.record_act(actor=care, act="work-delegated", conversation=a, turn=turn,
                  caused_by=parent, about=[child], because="handed on",
                  detail={"required": True})
    _end(world, prun, "result-returned", because="it reported; waiting on the child")
    crun = _start(world, a, care, "inst-child", child, turn)

    found = interrupted_by_restart(cv)

    assert [f["run"] for f in found] == [crun]
    assert cv._child_state(child)["state"] == "interrupted"
    assert not cv.expectation_state(child)["satisfied_by"]
    assert not cv.expectation_state(parent)["satisfied_by"]


def test_only_a_recorded_open_run_can_be_interrupted(world):
    cv = world["cv"]
    a = a_conversation(world, "Here")
    turn, req = _request(world, a, world["steward"])
    with pytest.raises(ValueError):
        cv.interrupt_run(req, why="not a run")
    run = _start(world, a, world["steward"], "inst-x", req, turn)
    ended = _end(world, run, "result-returned", because="it reported")
    assert cv.interrupt_run(run, why="too late") is None
    assert cv.run_end(run)["id"] == ended
