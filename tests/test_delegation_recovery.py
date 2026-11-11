"""A delegation committed and never started (round 4, C2).

`delegate` commits the child request and its `work-delegated` act; the door dispatches
after the commit. A process that died between the two -- or before the dispatch recorded
the child's start -- left the delegation recorded and never started. Now the record says
so ("Delegated · not started"), and a server's start runs ONE bounded pass
(`dispatch.recover_delegations`) that starts each such delegation once, as it was
delegated, or resolves it, recorded, where the owner or the record says not to.

Part 1 kills a real process at each boundary after the commit (the harness
`tests/_delegate_opkey_crash.py`, as round 2 -- Z's tests do before it), reopens the
Brain in a new server and runs the pass. Part 2 tests each reason the pass does not
start one, the bound, provenance, authority and reconciliation in one process.
"""
from __future__ import annotations

import json
import time

import pytest

import mentis.web as web
from mentis.web import dispatch as D
from mentis.web.dispatch import (DELEGATION_NOT_RECOVERED, DELEGATION_RECOVERED,
                                 RECOVERY_ATTEMPTS, RECOVERY_WINDOW_S,
                                 recover_delegations)
from tests import _delegate_opkey_crash as child_proc
from tests.test_delegate_opkey_crash import (ONE, WORK, Server, base, brain,  # noqa: F401
                                             counted, crash, delegation)


def _child_of(cv, brain):
    kids = [a for a in cv.corpus.operational(act="expectation-recorded")
            if a.get("caused_by") == brain["request"]
            and WORK in json.dumps(cv.corpus.read([a["turn"]])[0]["body"])]
    assert len(kids) == 1, kids
    return kids[0]["id"]


def _starts(cv, exp):
    return [a for a in cv.history(caused_by=exp) if a["act"] == "execution-started"]


def _marks(cv, exp, act):
    return [a for a in cv.history(caused_by=exp) if a["act"] == act]


def _label(cv, exp):
    from mentis.operational.work import trunk_status
    return trunk_status(cv, exp)["state"]


def _real(st, **kw):
    """The pass's `start`, run as the real dispatch on this thread."""
    return D.dispatch(st, **kw)


# -- part 1: a real process killed at each boundary after the commit ------------------

@pytest.mark.parametrize("boundary", ("committed", "dispatching", "answered",
                                      "starting"))
def test_a_delegation_cut_before_its_child_started_is_started_once(brain, boundary,
                                                                   monkeypatch):
    """Committed (with its key), and the child's start never committed: the record shows
    it delegated and not started; the next server's start starts it once, as delegated;
    a resend of the key replays and starts nothing; a later start recovers nothing."""
    args = delegation(brain)
    crash(brain, boundary, args)
    server = Server(brain["root"], brain["dir"], monkeypatch)
    try:
        cv = server.st.cv
        assert counted(cv, brain) == ONE
        exp = _child_of(cv, brain)
        assert _starts(cv, exp) == []
        state = _label(cv, exp)
        assert state["value"] == "owed" and state["label"] == "Delegated · not started"
        assert state["pending_start"]["delegated"] is True

        done = recover_delegations(server.st, start=_real)
        assert [r["child"] for r in done["recovered"]] == [exp]
        assert done["not_recovered"] == []
        # ONCE, AS DELEGATED: the delegated Participant, on the child request, in its
        # Conversation, on the delegation's Turn, with the delegation's words
        starts = _starts(cv, exp)
        assert len(starts) == 1
        start = starts[0]
        assert start["actor"] == brain["helper"]
        assert start["conversation"] == brain["conversation"]
        delegated = cv.corpus.operational(act="work-delegated")
        assert len(delegated) == 1
        assert start["turn"] == delegated[0]["turn"]
        # PROVENANCE: the recovery names the delegation it recovers, who delegated, from
        # which execution, and the run's start says it was recovered
        (claim,) = _marks(cv, exp, DELEGATION_RECOVERED)
        assert claim["detail"]["delegation"] == delegated[0]["id"]
        assert claim["detail"]["delegating_execution"] == brain["execution"]
        assert claim["detail"]["attempt"] == 1
        assert set(claim["about"]) == {exp, delegated[0]["id"]}
        assert claim["id"] in (start.get("because") or "")

        # the resend of the key: the first answer, and nothing dispatched
        _, op = server.session(continues=brain["execution"])
        status, again = op("delegate", **args)
        assert status == 200 and again["replayed"] is True, again
        assert server.sent == []
        # a later start: nothing to recover, nothing resolved
        later = recover_delegations(server.st, start=_real)
        assert later["recovered"] == [] and later["not_recovered"] == []
        assert len(_starts(cv, exp)) == 1
        assert counted(cv, brain) == ONE
    finally:
        server.close()


def test_a_child_whose_start_committed_is_never_started_again(brain, monkeypatch):
    """Cut just after the child's `execution-started` committed: it started. The pass
    leaves it alone -- a second run of a child that already started is never made."""
    crash(brain, "started", delegation(brain))
    server = Server(brain["root"], brain["dir"], monkeypatch)
    try:
        cv = server.st.cv
        exp = _child_of(cv, brain)
        assert len(_starts(cv, exp)) == 1
        done = recover_delegations(server.st, start=_real)
        assert done["recovered"] == [] and done["not_recovered"] == []
        assert len(_starts(cv, exp)) == 1
        assert _marks(cv, exp, DELEGATION_RECOVERED) == []
    finally:
        server.close()


@pytest.mark.parametrize("boundary", ("said", "keying", "committing"))
def test_a_delegation_cut_before_its_commit_leaves_nothing_to_recover(brain, boundary,
                                                                      monkeypatch):
    """Before the COMMIT nothing survives (round 2 -- Z), so the pass creates nothing:
    it never makes work that was not recorded."""
    crash(brain, boundary, delegation(brain))
    server = Server(brain["root"], brain["dir"], monkeypatch)
    try:
        cv = server.st.cv
        done = recover_delegations(server.st, start=_real)
        assert done["recovered"] == [] and done["not_recovered"] == []
        assert cv.corpus.operational(act="execution-started") == [] or all(
            a.get("caused_by") != brain["request"]
            for a in cv.corpus.operational(act="execution-started"))
        assert counted(cv, brain)["children"] == 0
    finally:
        server.close()


def test_a_recovery_cut_as_it_starts_the_run_starts_it_once_later(brain, monkeypatch):
    """The pass itself is cut: its claim committed, and the process died before the run
    started. The next start claims it again (attempt 2) and starts it once; the one after
    finds it started."""
    crash(brain, "answered", delegation(brain))
    crash(brain, child_proc.RECOVERING, {})
    server = Server(brain["root"], brain["dir"], monkeypatch)
    try:
        cv = server.st.cv
        exp = _child_of(cv, brain)
        assert len(_marks(cv, exp, DELEGATION_RECOVERED)) == 1
        assert _starts(cv, exp) == []
        assert _label(cv, exp)["label"] == "Delegated · recovered, not started yet"
        done = recover_delegations(server.st, start=_real)
        assert [r["child"] for r in done["recovered"]] == [exp]
        claims = _marks(cv, exp, DELEGATION_RECOVERED)
        assert [c["detail"]["attempt"] for c in claims] == [1, 2]
        assert len(_starts(cv, exp)) == 1
        again = recover_delegations(server.st, start=_real)
        assert again["recovered"] == [] and again["not_recovered"] == []
        assert len(_starts(cv, exp)) == 1
    finally:
        server.close()


def test_a_recovery_cut_every_time_stops_at_its_bound(brain, monkeypatch):
    """Cut at every attempt, the pass claims a delegation at most RECOVERY_ATTEMPTS
    times, then resolves it, recorded, and never asks about it again."""
    crash(brain, "answered", delegation(brain))
    for _ in range(RECOVERY_ATTEMPTS):
        crash(brain, child_proc.RECOVERING, {})
    server = Server(brain["root"], brain["dir"], monkeypatch)
    try:
        cv = server.st.cv
        exp = _child_of(cv, brain)
        assert len(_marks(cv, exp, DELEGATION_RECOVERED)) == RECOVERY_ATTEMPTS
        done = recover_delegations(server.st, start=_real)
        assert done["recovered"] == []
        assert [r["reason"] for r in done["not_recovered"]] == ["attempts"]
        assert _starts(cv, exp) == []
        state = _label(cv, exp)
        assert state["value"] == "owed"
        assert state["label"].startswith("Delegated · not started · not recovered: ")
        later = recover_delegations(server.st, start=_real)
        assert later["recovered"] == [] and later["not_recovered"] == []
        assert len(_marks(cv, exp, DELEGATION_NOT_RECOVERED)) == 1
    finally:
        server.close()


# -- part 2: why a pass does not start one, its bound, authority, reconciliation ------

from tests._loop import _coordinator, a_conversation, say, world  # noqa: E402,F401


@pytest.fixture()
def held(world, monkeypatch):
    """A coordinator's run delegated part of its work; the commit happened and the
    dispatch never ran (the door's `dispatch_soon` is captured and dropped)."""
    from mentis.web import _surface
    from mentis.worker import _operate
    cv = world["cv"]
    cid = a_conversation(world)
    coach, parent, grant = _coordinator(world, cid)
    helper = cv.create_participant("@Helper", about="an agent")
    cv.join(helper, cid, attributed_to=world["who"]["@brian"])
    # the coordinating run's own start, as dispatch records it
    started = cv.record_act(actor=coach, act="execution-started", conversation=cid,
                            caused_by=parent, execution=grant["instance"],
                            runtime="claude")

    def delegate(work="draw the chart", **extra):
        out = _operate(_surface(world["state"]), "delegate",
                       {"participant": helper, "work": work, **extra}, grant)
        return out["expectation"], out["delegation"]
    exp, act = delegate()
    world["sent"].clear()
    return {**world, "cid": cid, "coach": coach, "parent": parent, "grant": grant,
            "helper": helper, "child": exp, "delegation": act, "run": started,
            "delegate": delegate, "owner": world["who"]["@brian"]}


def _sent(world):
    return lambda st, **kw: world["sent"].append(kw)


def test_the_pass_starts_what_the_door_would_have(held):
    cv = held["cv"]
    done = recover_delegations(held["state"], start=_sent(held))
    assert [r["child"] for r in done["recovered"]] == [held["child"]]
    (kw,) = held["sent"]
    act = cv._act(held["delegation"])
    assert kw["participant"] == held["helper"]
    assert kw["expectation"] == held["child"]
    assert kw["conversation"] == held["cid"] and kw["turn"] == act["turn"]
    assert kw["work"] == "draw the chart"
    assert "recovered by" in kw["because"] and held["delegation"] in kw["because"]


@pytest.mark.parametrize("reason", ["owner-stopped", "withdrawn", "met",
                                    "parent-closed", "owner-said-since",
                                    "reassigned"])
def test_the_owner_and_the_record_still_decide(held, reason):
    """A Stop asked on the delegating run, the child withdrawn or met, the parent met,
    a follow-up the delegating run never read, the child given to somebody else: the
    pass starts nothing, and says why in the record. Asked again, it says nothing new."""
    cv, owner = held["cv"], held["owner"]
    if reason == "owner-stopped":
        cv.record_act(actor=owner, act="execution-stop-asked", caused_by=held["run"],
                      execution=held["grant"]["instance"], because="stop")
    elif reason == "withdrawn":
        cv.record_act(actor=owner, act="expectation-met", caused_by=held["child"],
                      because="not needed", detail={"withdrawn": True})
    elif reason == "met":
        cv.record_act(actor=owner, act="expectation-met", caused_by=held["child"],
                      because="done by hand")
    elif reason == "parent-closed":
        cv.record_act(actor=owner, act="expectation-met", caused_by=held["parent"],
                      because="done")
    elif reason == "owner-said-since":
        later = say(held, held["cid"], "actually, do it in blue",
                    action="ask-participant",
                    dispatch=[{"participant": held["coach"], "work": "blue"}])
        got = cv.attach_follow_up(later["expectations"][0], held["parent"], by=owner)
        assert not got.get("error"), got
    elif reason == "reassigned":
        other = cv.create_participant("@Other", about="an agent")
        cv.assign(held["child"], other, by=owner, because="Other does charts")
    held["sent"].clear()
    done = recover_delegations(held["state"], start=_sent(held))
    assert done["recovered"] == [] and held["sent"] == []
    assert [r["reason"] for r in done["not_recovered"]] == [reason]
    (mark,) = _marks(cv, held["child"], DELEGATION_NOT_RECOVERED)
    assert mark["detail"]["delegation"] == held["delegation"]
    assert mark["detail"]["reason"] == reason
    again = recover_delegations(held["state"], start=_sent(held))
    assert again["recovered"] == [] and again["not_recovered"] == []
    assert held["sent"] == []


def test_the_window_bounds_what_the_pass_reads(held):
    """Delegations older than RECOVERY_WINDOW_S at the start are not read: nothing is
    started or written for them, and they stay shown as delegated and not started."""
    cv = held["cv"]
    done = recover_delegations(held["state"], start=_sent(held),
                               now=time.time() + RECOVERY_WINDOW_S + 60)
    assert done["recovered"] == [] and done["not_recovered"] == []
    assert held["sent"] == []
    assert _marks(cv, held["child"], DELEGATION_RECOVERED) == []
    assert _label(cv, held["child"])["label"] == "Delegated · not started"


def test_the_limit_bounds_how_many_one_pass_starts(held):
    """At most `limit` runs per pass; the rest are resolved, recorded, as over it."""
    cv = held["cv"]
    second, _ = held["delegate"]("label the axes")
    third, _ = held["delegate"]("write the caption")
    held["sent"].clear()
    done = recover_delegations(held["state"], start=_sent(held), limit=2)
    assert [r["child"] for r in done["recovered"]] == [held["child"], second]
    assert [(r["child"], r["reason"]) for r in done["not_recovered"]] == [
        (third, "limit")]
    assert len(held["sent"]) == 2
    assert _label(cv, third)["label"].startswith(
        "Delegated · not started · not recovered: more than")


def test_the_recovered_run_holds_the_grant_its_request_gives(held):
    """THE ORIGINAL AUTHORITY: what the recovered run may do is read from the child's
    request, exactly as for the run the door would have started."""
    st, cv = held["state"], held["cv"]
    seen = {}

    def perform(spec):
        seen["grant"] = st.agents.authority.grant_for(
            st.agents.authority.grant_of(spec.run_id), st.path)
        now = time.time()
        from mentis.execution import RunResult
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="here", started_at=now,
                         finished_at=now)
    from tests._loop import script_every_backend
    script_every_backend(st.agents, perform)
    recover_delegations(st, start=_real)
    g = seen["grant"]
    want = D.authority_for(cv, held["child"])
    assert g["expectation"] == held["child"]
    assert g["participant"] == held["helper"]
    assert g["scope"] == want["scope"]
    assert list(g.get("operations") or ()) == list(want["organising"] or ())
    # not the coordinator's: the child's request did not get `coordinate`
    assert "coordinate" not in (g.get("operations") or ())


def test_a_recovered_child_claims_for_itself_never_for_its_parent(held):
    """Reconciliation after an interrupted delegation: the recovered child's claim of
    met goes to the child; the parent stays owed by its own requirements."""
    st, cv = held["state"], held["cv"]
    from mentis.execution import RunResult
    from mentis.operational import completion as C
    from tests._loop import script_every_backend

    def perform(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn",
                         text="Chart drawn.\n```outcome\nresult: met\n"
                              "summary: the chart\n```",
                         started_at=now, finished_at=now)
    script_every_backend(st.agents, perform)
    recover_delegations(st, start=_real)
    claims = C.claims_of(cv, held["child"])
    assert len(claims) == 1 and claims[0]["detail"]["result"] == "met"
    assert cv.expectation_state(held["child"])["satisfied_by"]
    assert not cv.expectation_state(held["parent"])["satisfied_by"]
    assert C.claims_of(cv, held["parent"]) == []


def test_consent_is_the_records_when_the_recovered_run_starts(held):
    """The pass grants nothing: the consent the child's request reads
    (`consent.of_request`) is whatever the owner last set on the work, before or after
    the delegation, and the pass changes none of it."""
    from mentis.operational import consent as K
    cv = held["cv"]

    def owner_sets(mode):
        cv.record_act(actor=held["owner"], act=K.SET, caused_by=held["parent"],
                      because=mode, detail={"scope": "task", "consent": {
                          "mode": mode, "workspaces": [],
                          "categories": list(K.DEFAULT_CATEGORIES)}})
    owner_sets(K.TASK)
    assert K.of_request(cv, held["child"])["mode"] == K.TASK
    owner_sets(K.DENY)
    before = K.of_request(cv, held["child"])
    assert before["mode"] == K.DENY
    recover_delegations(held["state"], start=_sent(held))
    assert K.of_request(cv, held["child"])["mode"] == K.DENY
