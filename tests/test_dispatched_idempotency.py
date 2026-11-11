"""A dispatched run's writes have stable identities (round 4, C2).

The run's real Mentis bridge (`worker.serve` with the run's grant and execution, as
`core.service.mcp_servers_for` starts it) keys every write it sends: the agent's own
`op_key`; else the key of a kept, unanswered write with the same operation and arguments;
else, for a write that makes a record (`worker.CONTENT_KEYED`), a key derived from
(execution, operation, arguments); else a fresh one. It keeps each write until answered
and resends it before the run's next call (`outbox.MemoryOutbox`). The server records a
keyed write once (`mentis.opkeys`).

Each case dispatches a real run whose scripted agent drives that bridge over stdio,
through a door that can lose an answer (`tests/_dispatched_bridge.Cutting`): before the
server had it, after it committed and before the answer, or with a 503 after it.
"""
from __future__ import annotations

import json
import time

import pytest

import mentis.web as web
from mentis.execution import RunResult
from tests._dispatched_bridge import Bridge, Cutting
from tests._loop import a_conversation, say, world  # noqa: F401


def _children(cv, exp, words):
    kids = [a for a in cv.corpus.operational(act="expectation-recorded")
            if a.get("caused_by") == exp]
    return [a for a in kids
            if words in json.dumps(cv.corpus.read([a["turn"]])[0]["body"])]


def _keys(cv):
    return [a for a in cv.corpus.operational(act="operation-keyed")
            if (a.get("detail") or {}).get("op", "").startswith("worker:delegate:")]


@pytest.fixture()
def run_with(world, monkeypatch):
    """`run_with(agent)`: the owner asks @Ada for work; Ada's run is dispatched for real
    and its agent is `agent(bridge, door, helper)`, driving the run's own bridge through a
    `Cutting` door. Returns (request, what the agent kept, the door)."""
    from mentis.web import dispatch as D
    st, cv = world["state"], world["cv"]
    helper = cv.create_participant("@Helper", about="an agent")
    ada = cv.create_participant("@Ada", about="an agent")
    door = Cutting(world["base"])
    st.agents.workers_read(st.path, answers_at=door.url)
    monkeypatch.setattr(web, "dispatch_soon", lambda s, **kw: (
        D.dispatch(s, **kw) if kw.get("participant") == ada else None))

    def go(agent):
        kept = {}

        def perform(spec):
            bridge = Bridge(spec)
            try:
                kept["execution"] = spec.run_id
                kept.update(agent(bridge, door, helper) or {})
            finally:
                kept["stderr"] = bridge.close()
            now = time.time()
            return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                             stop_reason="end_turn", text="done", started_at=now,
                             finished_at=now)
        st.agents.execution.script = {"codex": perform}
        cid = a_conversation(world)
        out = say(world, cid, "split it", action="ask-participant",
                  dispatch=[{"participant": ada, "work": "split it",
                             "runtime": "codex"}])
        return out["expectations"][0], kept

    yield go
    door.close()


def test_the_same_delegate_sent_again_by_a_dispatched_run_is_one_child(world, run_with):
    """Exposure 1 of round 3 (B4), closed: the agent sends `delegate` again with no key
    -- as after a lost answer -- and it is the same delegation."""
    cv = world["cv"]

    def agent(bridge, door, helper):
        return {"calls": [bridge.call("delegate", participant=helper, work="part B")
                          for _ in range(2)]}
    exp, kept = run_with(agent)
    (e1, first), (e2, again) = kept["calls"]
    assert not e1 and not e2, kept
    assert again["replayed"] is True and again["expectation"] == first["expectation"]
    assert "op_key of your own" in again["replayed_why"]
    assert len(_children(cv, exp, "part B")) == 1
    assert len(cv.corpus.operational(act="work-delegated")) == 1
    assert len(_keys(cv)) == 1


def test_an_agent_that_means_a_second_one_says_so_with_its_own_key(world, run_with):
    cv = world["cv"]

    def agent(bridge, door, helper):
        return {"calls": [
            bridge.call("delegate", participant=helper, work="part C", op_key="c-1"),
            bridge.call("delegate", participant=helper, work="part C", op_key="c-2"),
            bridge.call("delegate", participant=helper, work="part C", op_key="c-1"),
            bridge.call("delegate", participant=helper, work="part D, the first"),
            bridge.call("delegate", participant=helper, work="part D, the second")]}
    exp, kept = run_with(agent)
    assert not any(e for e, _ in kept["calls"]), kept
    assert kept["calls"][2][1]["replayed"] is True
    # its own key is its own identity: no "same arguments" note is added to it
    assert "replayed_why" not in kept["calls"][2][1]
    assert len(_children(cv, exp, "part C")) == 2
    assert len(_children(cv, exp, "part D, the first")) == 1
    assert len(_children(cv, exp, "part D, the second")) == 1


@pytest.mark.parametrize("cut", ["drop-before", "drop-after", "503-after"])
def test_a_lost_answer_then_the_agent_sends_it_again_is_one_child(world, run_with, cut):
    """The answer is lost at the acknowledgement boundary -- before the server had the
    call, after it committed, or with a 503 after it -- and the agent sends the same call
    again: the bridge sends it under the kept write's key, and it is recorded once."""
    cv = world["cv"]

    def agent(bridge, door, helper):
        door.plan = [cut]
        lost = bridge.call("delegate", participant=helper, work="part E")
        again = bridge.call("delegate", participant=helper, work="part E")
        return {"lost": lost, "again": again}
    exp, kept = run_with(agent)
    err, text = kept["lost"]
    assert err and "KEPT BY THIS RUN'S MENTIS BRIDGE" in text, kept
    err, again = kept["again"]
    assert not err, kept
    if cut == "drop-before":
        # nothing was done the first time: this is the first delegation
        assert again.get("replayed") is None
    else:
        assert again["replayed"] is True, again
        assert "op_key of your own" in again["replayed_why"]
    assert len(_children(cv, exp, "part E")) == 1
    assert len(cv.corpus.operational(act="work-delegated")) == 1


@pytest.mark.parametrize("cut", ["drop-before", "drop-after"])
def test_a_lost_answer_is_resent_by_the_bridge_before_the_next_call(world, run_with, cut):
    """The agent does NOT send it again: its next call (a read) carries the kept write
    first. After that, sending it again anyway is still the same write."""
    cv = world["cv"]

    def agent(bridge, door, helper):
        door.plan = [cut]
        lost = bridge.call("delegate", participant=helper, work="part F")
        read = bridge.call("orient")
        again = bridge.call("delegate", participant=helper, work="part F")
        return {"lost": lost, "read": read, "again": again,
                "seen": list(door.seen)}
    exp, kept = run_with(agent)
    assert kept["lost"][0] and not kept["read"][0] and not kept["again"][0], kept
    ops = [op for _, op in kept["seen"]]
    # the delegate, then its resend before the read, then the read, then the repeat
    assert ops[:3] == ["delegate", "delegate", "orient"], kept["seen"]
    assert kept["again"][1]["replayed"] is True
    assert "mentis outbox: resent delegate" in kept["stderr"]
    assert len(_children(cv, exp, "part F")) == 1


def test_a_finding_and_a_turn_sent_again_are_recorded_once(world, run_with):
    """Not only `delegate`: every write that makes a record (`CONTENT_KEYED`)."""
    cv = world["cv"]

    def agent(bridge, door, helper):
        return {"calls": [bridge.call("record_discovered_work",
                                      work="the parser drops comments")
                          for _ in range(2)]}
    exp, kept = run_with(agent)
    assert not any(e for e, _ in kept["calls"]), kept
    assert kept["calls"][1][1]["replayed"] is True
    found = [a for a in cv.corpus.operational(act="work-discovered")]
    assert len(found) == 1


def test_which_key_a_write_is_given():
    """`worker.write_key`, the rule: the agent's key; else a kept write's; else derived
    for a write that makes a record in a dispatched run; else fresh. A write that may be
    repeated later to mean something new (claim/release, an answer, a verdict) is never
    keyed by its content."""
    from mentis.outbox import MemoryOutbox, derived_key
    from mentis.worker import CONTENT_KEYED, write_key
    box = MemoryOutbox("exec-1")
    a = {"participant": "ent-x", "work": "w"}
    got, how = write_key("delegate", {**a, "op_key": "mine"}, box, dispatched=True,
                         execution="exec-1")
    assert (got["op_key"], how) == ("mine", "agent")
    got, how = write_key("delegate", a, box, dispatched=True, execution="exec-1")
    assert how == "derived" and got["op_key"] == derived_key("exec-1", "delegate", a)
    # the same arguments in another order are the same write; another run's are not
    assert derived_key("exec-1", "delegate", dict(reversed(list(a.items())))) \
        == got["op_key"]
    assert derived_key("exec-2", "delegate", a) != got["op_key"]
    # a hand-started session's write is not keyed by content
    assert write_key("delegate", a, box, dispatched=False, execution="s")[1] == "fresh"
    for op in ("claim_resource", "release_resource", "answer", "record_verdict",
               "challenge", "withdraw_challenge", "timer", "react", "change_workflow",
               "return_artifact", "await_work"):
        assert op not in CONTENT_KEYED
        first, how = write_key(op, {"x": 1}, box, dispatched=True, execution="exec-1")
        assert how == "fresh"
        assert write_key(op, {"x": 1}, box, dispatched=True,
                         execution="exec-1")[0]["op_key"] != first["op_key"]
    # a kept, unanswered write is resent under its own key, whatever the op
    box.put("claim_resource", {"x": 1, "op_key": "kept-1"})
    got, how = write_key("claim_resource", {"x": 1}, box, dispatched=True,
                         execution="exec-1")
    assert (got["op_key"], how) == ("kept-1", "kept")
    box.ack("kept-1")
    assert write_key("claim_resource", {"x": 1}, box, dispatched=True,
                     execution="exec-1")[1] == "fresh"


def test_the_dispatched_outbox_is_bounded_like_the_sessions():
    """Held in memory only, kept until answered, given up after MAX_AGE_S."""
    from mentis import outbox
    box = outbox.MemoryOutbox("exec-1")
    box.put("delegate", {"op_key": "k1"})
    box.put("delegate", {"op_key": "k1"})
    assert [e["key"] for e in box.pending()] == ["k1"]
    box._puts["k1"]["at"] -= outbox.MAX_AGE_S + 1
    assert box.pending() == []


def test_each_run_on_a_reused_handle_gives_its_bridge_its_own_identity(world):
    """Round-4 review (critical): an instance handle is REUSED across runs (same
    instance_id, new MARS session, new grant per run), so the bridge's derived write keys
    must name the RUN. Two grants minted in turn on ONE handle give the bridge two
    different execution identities; within a run it is stable."""
    from mentis.core.service import run_identity
    st = world["state"]
    svc = st.agents
    inst = "inst-reused-handle"
    seen = []
    for _ in range(2):
        svc.authority._grant(inst, svc._record)
        args = svc.mcp_servers_for(inst, st.workspace)[0]["args"][-1]
        token = svc.authority.grant_of(inst)
        assert run_identity(inst, token) in args and token not in args.split("execution=")[-1]
        seen.append(run_identity(inst, token))
        svc.authority.revoke(inst)
    assert seen[0] != seen[1]
    assert run_identity(inst, "g") == run_identity(inst, "g")
