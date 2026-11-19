"""A server draining for a deployment starts no new run (owner decision, 2026-11-19).

`mentis.web.drain`: one flag and one count under one lock; `dispatch.dispatch` asks it
before anything is written; `POST /api/server/drain` (the owner's) sets and clears it and
answers with the flag and the dispatches held, read in the same moment.

What is tested: the invariant under a race of starts against the drain request; that a
start refused while draining writes no `execution-started`, is recorded as a failure before
start with the reason, and leaves the work open; that runs already going finish; that a
delegation refused this way is still one the next server start recovers, within its
existing bounds; the owner's authentication; the bound that ends a drain by itself, with no
thread; and what the reads report.
"""
from __future__ import annotations

import random
import threading
import time
import types
import urllib.error

import pytest

from mentis.web import dispatch as D
from mentis.web import drain
from mentis.web.dispatch import (DELEGATION_NOT_RECOVERED, DELEGATION_RECOVERED,
                                 RECOVERY_ATTEMPTS, pending_delegations,
                                 recover_delegations)
from tests._loop import (_coordinator, a_conversation, get, post, rt, say,  # noqa: F401
                         world)
from tests.test_owner_auth import PASSPHRASE, call, cookie_of, login
from tests.test_owner_auth import server  # noqa: F401


def _starts(cv, exp):
    return [a for a in cv.history(caused_by=exp) if a["act"] == "execution-started"]


def _refusals(cv, exp):
    return [a for a in cv.history(caused_by=exp) if a["act"] == "delivery-failed"
            and (a.get("detail") or {}).get("stage") == drain.STAGE]


def _asked(world, cid, work="draw the chart [[return]]", alias="@Drawer"):
    """The owner addresses an agent; the door's dispatch is captured, not run."""
    cv = world["cv"]
    who = cv.create_participant(alias, about="an agent")
    cv.join(who, cid, attributed_to=world["who"]["@brian"])
    world["sent"].clear()
    out = say(world, cid, f"{alias} {work}", action="ask-participant",
              dispatch=[{"participant": who, "work": work}])
    (kw,) = world["sent"]
    world["sent"].clear()
    return out["expectations"][0], kw


# -- the flag and the count, alone -----------------------------------------------------

def test_the_drain_ends_by_itself_at_its_bound_and_nothing_wakes_to_end_it():
    """THE BOUND: one owner-authorized call keeps a server draining for at most BOUND_S.
    It is evaluated when the flag is next read: no thread or timer exists to end it."""
    st = types.SimpleNamespace()
    threads = threading.active_count()
    got = drain.request(st, on=True, by="owner", reason="deploy r1", now=1000.0)
    assert got["draining"]["since"] == 1000.0 and got["held"] == 0
    assert got["draining"]["expires_at"] == 1000.0 + drain.BOUND_S == 1120.0
    assert threading.active_count() == threads, "a drain starts no thread"
    assert drain.admit(st, now=1119.9) is not None, "still draining just inside the bound"
    assert drain.read(st, now=1119.9)["draining"]["refused"] == 1
    assert drain.read(st, now=1120.0)["draining"] is None, "ended at the bound, by a read"
    assert drain.admit(st, now=1120.0) is None, "and a start is admitted again"
    assert drain.read(st, now=1120.0) == {"draining": None, "held": 1}
    drain.leave(st)


def test_a_call_cannot_ask_for_longer_than_the_bound_and_only_a_new_call_extends_it():
    st = types.SimpleNamespace()
    got = drain.request(st, on=True, by="owner", reason="r", seconds=99999, now=0.0)
    assert got["draining"]["expires_at"] == drain.BOUND_S
    short = types.SimpleNamespace()
    assert drain.request(short, on=True, by="owner", reason="r", seconds=5,
                         now=0.0)["draining"]["expires_at"] == 5.0
    # nothing but a new call moves the end: reads and refused starts do not
    assert drain.admit(st, now=100.0) is not None
    assert drain.read(st, now=110.0)["draining"]["expires_at"] == drain.BOUND_S
    again = drain.request(st, on=True, by="owner", reason="r", now=110.0)
    assert again["draining"]["since"] == 0.0, "the same drain, extended"
    assert again["draining"]["expires_at"] == 110.0 + drain.BOUND_S
    assert again["draining"]["extended"] == 1
    assert drain.read(st, now=110.0 + drain.BOUND_S)["draining"] is None


def test_clearing_says_what_the_drain_refused_and_a_cleared_server_admits(capsys):
    st = types.SimpleNamespace()
    drain.request(st, on=True, by="owner", reason="deploy r1", now=10.0)
    met = drain.admit(st, now=11.0)
    drain.note_refused(st, met, act="opr-1", expectation="exp-1", participant="p")
    got = drain.request(st, on=False, by="owner", now=12.0)
    assert got["draining"] is None and got["held"] == 0
    assert got["was"]["refused"] == 1
    assert got["was"]["refused_starts"] == [{"act": "opr-1", "expectation": "exp-1",
                                             "participant": "p"}]
    assert drain.admit(st, now=12.0) is None
    # AUDIT: each change is one line on the server's own log (stdout -> python.log)
    said = [line for line in capsys.readouterr().out.splitlines() if line.startswith("drain: ")]
    assert ['"event": "set"' in said[0], '"event": "cleared"' in said[1]] == [True, True]
    assert '"reason": "deploy r1"' in said[0] and '"by": "owner"' in said[0]


# -- THE RACE: starts against the drain request ------------------------------------------

def test_no_start_passes_a_drain_and_none_admitted_is_missed_by_its_count(monkeypatch):
    """Many rounds of several threads starting dispatches while another asks for the
    drain. In every round, once the drain call has returned "draining, held = N":

      - exactly N dispatches are inside the start path (`_dispatch`), not one more, ever,
        until the drain is cleared: every other one was refused and wrote no start;
      - none that passed the check is missing from N;
      - when those N finish, held is 0 and the server is still draining.
    """
    lock = threading.Lock()
    rounds, starters = 150, 8
    answers = set()
    for n in range(rounds):
        st = types.SimpleNamespace(cv=None)
        gate = threading.Event()
        inside, refused, settled = [], [], [threading.Event() for _ in range(starters)]

        def fake_dispatch(st_, *, me, **kw):
            with lock:
                inside.append(me)               # where `execution-started` is written
            settled[me].set()
            gate.wait(10)
            return {"ok": True}

        def fake_refusal(cv, *, stage, requested, **kw):
            with lock:
                refused.append(stage)
            return "failed-act"
        monkeypatch.setattr(D, "_dispatch", fake_dispatch)
        monkeypatch.setattr(D, "_failed_before_start", fake_refusal)
        line_up = threading.Barrier(starters + 1)
        results = [None] * starters

        def start(i):
            line_up.wait(10)
            time.sleep(random.random() * 0.002)
            results[i] = D.dispatch(st, me=i)
            settled[i].set()
        threads = [threading.Thread(target=start, args=(i,), daemon=True)
                   for i in range(starters)]
        for t in threads:
            t.start()
        line_up.wait(10)
        time.sleep(random.random() * 0.002)
        answer = drain.request(st, on=True, by="owner", reason=f"round {n}")
        held = answer["held"]
        answers.add(held)
        assert answer["draining"] is not None
        for e in settled:
            assert e.wait(10)
        with lock:
            assert len(inside) == held, (n, "inside the start path", len(inside), "held", held)
            assert len(refused) == starters - held, (n, refused, held)
        assert drain.read(st)["held"] == held
        # a start arriving later is refused too, however long the drain has stood
        late = D.dispatch(st, me=99)
        assert late["ok"] is False and late["before_execution_started"] is True
        with lock:
            assert len(inside) == held
        gate.set()
        for t in threads:
            t.join(10)
        now = drain.read(st)
        assert now["held"] == 0 and now["draining"] is not None, n
        assert now["draining"]["refused"] == starters - held + 1
        assert sum(1 for r in results if r == {"ok": True}) == held
        assert drain.request(st, on=False, by="owner")["draining"] is None
        monkeypatch.setattr(D, "_dispatch", lambda st_, **kw: {"ok": "after"})
        assert D.dispatch(st, me=100) == {"ok": "after"}, "cleared: starts are admitted again"
        assert drain.read(st)["held"] == 0
    assert len(answers) > 2, f"the drain met the starts at one point only: {answers}"


def test_real_dispatches_racing_a_drain_write_a_start_only_when_they_were_counted(world, rt):
    """The same race through the real dispatch, on a real record: each start that was
    admitted is one `execution-started`; each that met the drain wrote none and is a
    failure before start. The runs that were going FINISH, with their results."""
    st, cv = world["state"], world["cv"]
    cid = a_conversation(world)
    gate = rt["gates"]["g"] = threading.Event()
    asked = [_asked(world, cid, work=f"draw chart {i} [[hold:g]]", alias=f"@Drawer{i}")
             for i in range(6)]
    results = {}

    def start(exp, kw):
        results[exp] = D.dispatch(st, **kw)
    threads = [threading.Thread(target=start, args=a, daemon=True) for a in asked]
    for t in threads[:3]:
        t.start()
    deadline = time.time() + 30
    while len(rt["grants"]) < 1 and time.time() < deadline:
        time.sleep(0.01)                           # at least one run is being performed
    for t in threads[3:]:
        t.start()
    answer = post(world, "/api/server/drain", {"on": True, "reason": "deploying r2"})
    held = answer["held"]
    assert 1 <= held <= 6 and answer["draining"]["reason"] == "deploying r2"
    while len(rt["grants"]) + len(results) < 6 and time.time() < deadline:
        time.sleep(0.01)
    assert len(rt["grants"]) + len(results) == 6, "every start is performing or was refused"
    started = [exp for exp, _ in asked if _starts(cv, exp)]
    refused = [exp for exp, _ in asked if _refusals(cv, exp)]
    assert len(started) == held and len(refused) == 6 - held
    assert not set(started) & set(refused)
    assert get(world, "/api/working")["dispatches_held"] == held
    assert sum(1 for r in get(world, "/api/working")["open"] if r.get("held_here")) == held
    # EXISTING RUNS FINISH NORMALLY: nothing was stopped, and each returns its result
    gate.set()
    for t in threads:
        t.join(30)
    for exp in started:
        assert results[exp]["ok"] is True, results[exp]
        assert len(_starts(cv, exp)) == 1
        assert [a["act"] for a in cv.history(caused_by=_starts(cv, exp)[0]["id"])
                if a["act"] in ("result-returned", "delivery-failed")] == ["result-returned"]
    for exp in refused:
        assert _starts(cv, exp) == [] and results[exp]["before_execution_started"] is True
    quiet = post(world, "/api/server/drain", {"on": True, "reason": "deploying r2"})
    assert quiet["held"] == 0 and quiet["draining"]["extended"] == 1
    assert quiet["draining"]["refused"] == 6 - held


# -- a start refused while draining ------------------------------------------------------

def test_a_start_while_draining_writes_no_start_says_why_and_the_work_stays_open(world, rt):
    st, cv = world["state"], world["cv"]
    cid = a_conversation(world)
    exp, kw = _asked(world, cid)
    assert get(world, "/api/working")["draining"] is None
    assert get(world, "/api/server")["draining"] is None
    answer = post(world, "/api/server/drain", {"on": True, "reason": "deploying r2"})
    assert answer["held"] == 0 and answer["bound_s"] == drain.BOUND_S
    before = len(cv.history())
    out = D.dispatch(st, **kw)
    assert out["ok"] is False and out["before_execution_started"] is True
    assert "draining for a deployment (deploying r2)" in out["why"]
    assert "the work stays open" in out["why"]
    # NO START, and exactly one act: the failure before start, on the request
    assert _starts(cv, exp) == [] and rt["grants"] == []
    assert len(cv.history()) == before + 1
    (failed,) = _refusals(cv, exp)
    assert failed["id"] == out["failed_act"]
    assert failed["detail"]["before_execution_started"] is True
    assert failed["because"].startswith("ServerDraining: no run was started")
    # THE WORK IS OPEN: not met, not withdrawn, still its carrier's
    state = cv.expectation_state(exp)
    assert not state.get("satisfied_by") and not state.get("withdrawn")
    assert cv.assigned_carrier(exp)["carrier"] == kw["participant"]
    assert D.withdrawal_of(cv, exp) is None
    # OBSERVABLE: both reads say it, with what it refused
    for path in ("/api/working", "/api/server"):
        seen = get(world, path)["draining"]
        assert seen["reason"] == "deploying r2" and seen["refused"] == 1
        assert seen["by"] and seen["expires_at"] == seen["since"] + drain.BOUND_S
        assert seen["refused_starts"] == [{"act": failed["id"], "expectation": exp,
                                          "participant": kw["participant"]}]
    assert get(world, "/api/working")["dispatches_held"] == 0
    # CLEARED (a cancelled deployment): the same work is addressed again and runs
    cleared = post(world, "/api/server/drain", {"on": False})
    assert cleared["draining"] is None and cleared["was"]["refused"] == 1
    assert get(world, "/api/working")["draining"] is None
    again = D.dispatch(st, **kw)
    assert again["ok"] is True, again
    assert len(_starts(cv, exp)) == 1 and len(rt["grants"]) == 1


def test_an_expired_drain_lets_work_start_again(world, rt):
    st, cv = world["state"], world["cv"]
    cid = a_conversation(world)
    exp, kw = _asked(world, cid)
    threads = threading.active_count()
    post(world, "/api/server/drain", {"on": True, "reason": "a deploy that died",
                                      "seconds": 0.3})
    assert D.dispatch(st, **kw)["ok"] is False and _starts(cv, exp) == []
    assert threading.active_count() <= threads + 1, "no timer was started for the bound"
    time.sleep(0.35)
    assert get(world, "/api/working")["draining"] is None
    assert D.dispatch(st, **kw)["ok"] is True
    assert len(_starts(cv, exp)) == 1


# -- a delegation refused while draining -------------------------------------------------

@pytest.fixture()
def delegated(world):
    """A coordinator's run delegated part of its work: the commit happened, and the
    door's dispatch of the child is run when the test says."""
    from mentis.web import _surface
    from mentis.worker import _operate
    cv = world["cv"]
    cid = a_conversation(world)
    coach, parent, grant = _coordinator(world, cid)
    helper = cv.create_participant("@Helper", about="an agent")
    cv.join(helper, cid, attributed_to=world["who"]["@brian"])
    cv.record_act(actor=coach, act="execution-started", conversation=cid,
                  caused_by=parent, execution=grant["instance"], runtime="claude")
    out = _operate(_surface(world["state"]), "delegate",
                   {"participant": helper, "work": "draw the chart [[return]]"}, grant)
    # the dispatch the door makes after the commit, read as recovery reads it
    kw = D._start_of(cv, cv._act(out["delegation"]), out["expectation"], "the door")
    kw["because"] = None
    world["sent"].clear()
    return {**world, "child": out["expectation"], "delegation": out["delegation"],
            "door": kw, "helper": helper}


def _real(st, **kw):
    return D.dispatch(st, **kw)


def test_a_delegation_refused_while_draining_is_started_by_the_next_server_start(
        delegated, rt):
    st, cv, child = delegated["state"], delegated["cv"], delegated["child"]
    drain.request(st, on=True, by="owner", reason="deploying r2")
    out = D.dispatch(st, **delegated["door"])
    assert out["ok"] is False and _starts(cv, child) == []
    assert len(_refusals(cv, child)) == 1
    # STILL A DELEGATION RECORDED AND NEVER STARTED, which is what recovery reads
    assert [p["child"] for p in pending_delegations(cv)] == [child]
    # THE RESTART: a server that has just started is never draining
    st.drain = {"draining": None, "admitted": 0}
    done = recover_delegations(st, start=_real)
    assert [r["child"] for r in done["recovered"]] == [child] and done["not_recovered"] == []
    (start,) = _starts(cv, child)
    assert start["actor"] == delegated["helper"]
    assert [c["detail"]["attempt"] for c in cv.history(caused_by=child)
            if c["act"] == DELEGATION_RECOVERED] == [1]
    later = recover_delegations(st, start=_real)
    assert later["recovered"] == [] and later["not_recovered"] == []
    assert len(_starts(cv, child)) == 1


def test_a_failure_before_start_of_any_other_kind_still_counts_as_started(delegated):
    """Only a drain's refusal leaves a delegation recoverable: recovery's reading of every
    other failure before start is unchanged."""
    cv, child = delegated["cv"], delegated["child"]
    D._failed_before_start(cv, participant=delegated["helper"],
                           conversation=delegated["door"]["conversation"],
                           turn=delegated["door"]["turn"], expectation=child,
                           stage="selection", exc=RuntimeError("no runtime"), requested={})
    assert pending_delegations(cv) == []


def test_recovery_into_a_drain_stays_inside_its_attempts(delegated, rt):
    """A recovered start that meets a drain again is not retried without end: recovery
    claims one delegation at most RECOVERY_ATTEMPTS times, then resolves it, recorded."""
    st, cv, child = delegated["state"], delegated["cv"], delegated["child"]
    for attempt in range(1, RECOVERY_ATTEMPTS + 1):
        st.drain = {"draining": None, "admitted": 0}            # a server start
        drain.request(st, on=True, by="owner", reason="another deployment")
        done = recover_delegations(st, start=_real)
        assert [r["child"] for r in done["recovered"]] == [child]
        assert _starts(cv, child) == [] and len(_refusals(cv, child)) == attempt
    st.drain = {"draining": None, "admitted": 0}
    done = recover_delegations(st, start=_real)
    assert done["recovered"] == []
    assert [r["reason"] for r in done["not_recovered"]] == ["attempts"]
    assert _starts(cv, child) == []
    assert len([a for a in cv.history(caused_by=child)
                if a["act"] == DELEGATION_NOT_RECOVERED]) == 1


# -- the owner's authority ---------------------------------------------------------------

def test_draining_is_the_owners_and_is_refused_to_everybody_else(server):
    """The route is behind the owner's authentication like every owner write: no session,
    a forged one, the boot secret and a worker grant are each refused, and the server is
    not draining afterwards."""
    from mentis.worker import CAPABILITY_HEADER
    port, st = server["port"], server["st"]
    server["cred"].set_passphrase(PASSPHRASE)
    body = {"on": True, "reason": "not the owner"}
    for extra in ({}, {"Authorization": "Bearer not-a-session"},
                  {"X-Mentis-Boot-Secret": "anything", "X-Mentis-Peer": "127.0.0.1"},
                  {"Cookie": f"{server['cred'].cookie_name()}=forged"}):
        got = call(port, "POST", "/api/server/drain", body, extra)
        assert got["status"] == 401 and got["json"]["kind"] == "OwnerAuthRequired", extra
    got = call(port, "POST", "/api/server/drain", body, {CAPABILITY_HEADER: "any-grant"})
    assert got["status"] == 403 and got["json"]["kind"] == "PermissionError"
    assert drain.read(st)["draining"] is None
    assert call(port, "GET", "/api/server")["json"]["draining"] is None
    # THE OWNER: a session from the passphrase, as a cookie or a bearer token
    cookie = {"Cookie": cookie_of(login(port))}
    got = call(port, "POST", "/api/server/drain", body, cookie)
    assert got["status"] == 200 and got["json"]["draining"]["reason"] == "not the owner"
    assert drain.read(st)["draining"] is not None
    # and clearing it is the owner's too
    assert call(port, "POST", "/api/server/drain", {"on": False})["status"] == 401
    assert drain.read(st)["draining"] is not None
    token = login(port, token=True)["json"]["token"]
    how = {"Authorization": f"Bearer {token}"}
    got = call(port, "POST", "/api/server/drain", {"on": False}, how)
    assert got["status"] == 200 and got["json"]["draining"] is None
    assert got["json"]["was"]["reason"] == "not the owner"


def test_a_trusted_local_installation_drains_without_a_session(server):
    from mentis import owner_auth
    server["cred"].trust_local(owner_auth.TRUSTED_LOCAL_ACCEPTANCE)
    got = call(server["port"], "POST", "/api/server/drain", {"on": True, "reason": "deploy"})
    assert got["status"] == 200 and got["json"]["held"] == 0
    assert drain.read(server["st"])["draining"]["reason"] == "deploy"


def test_a_drain_request_says_what_it_wants_or_is_refused(world):
    for body in ({}, {"on": "yes"}, {"on": True}, {"on": True, "reason": "  "},
                 {"on": True, "reason": "r", "seconds": 0},
                 {"on": True, "reason": "r", "seconds": "long"}):
        with pytest.raises(urllib.error.HTTPError) as refused:
            post(world, "/api/server/drain", body)
        assert refused.value.code == 400, body
    assert drain.read(world["state"])["draining"] is None
    with pytest.raises(urllib.error.HTTPError) as missing:
        get(world, "/api/server/drain")
    assert missing.value.code == 404, "there is no read here: the two reads report it"
