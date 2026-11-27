"""A server draining for a deployment starts no new run (owner decision, 2026-11-19).

`mentis.web.drain`: one flag and one count under one lock; `dispatch.dispatch` asks it
before anything is written; `POST /api/server/drain` (the owner's) sets and clears it and
answers with the flag and the dispatches held, read in the same moment.

What is tested: the invariant under a race of starts against the drain request; that a
start refused while draining writes no `execution-started`, is recorded as a failure before
start with the reason, and leaves the work open; that runs already going finish; that
delegation recovery is exactly what it was (a delegation refused this way is NOT restarted);
that a resumption, a consent restart and a continuation each meet the drain and do not loop;
the stopping phase and its bound; that durations are measured on the monotonic clock; that
a drain has an identity and only a call naming it changes it; the owner's authentication;
the bound that ends a drain by itself, with no thread; and what the reads report.
"""
from __future__ import annotations

import json
import random
import threading
import time
import types
import urllib.error

import pytest

from mentis.web import dispatch as D
from mentis.web import drain
from mentis.web.dispatch import (DELEGATION_NOT_RECOVERED, DELEGATION_RECOVERED,
                                 pending_delegations, recover_delegations)
from tests._loop import (_coordinator, a_conversation, get, post, rt, say,  # noqa: F401
                         world)
from tests.test_owner_auth import PASSPHRASE, call, cookie_of, login
from tests.test_owner_auth import server  # noqa: F401
from tests.test_decision_resume_parent import fake  # noqa: F401


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
    It is evaluated when the flag is next read: no thread or timer exists to end it. The
    clock that decides is the monotonic one (`mono`); `now` is only what is reported."""
    st = types.SimpleNamespace()
    threads = threading.active_count()
    got = drain.request(st, on=True, by="owner", reason="deploy r1", now=1000.0, mono=50.0)
    assert got["draining"]["since"] == 1000.0 and got["held"] == 0
    assert got["draining"]["expires_at"] == 1000.0 + drain.BOUND_S == 1120.0
    assert got["draining"]["lasts_s"] == drain.BOUND_S
    assert threading.active_count() == threads, "a drain starts no thread"
    assert drain.admit(st, mono=169.9) is not None, "still draining just inside the bound"
    assert drain.read(st, mono=169.9)["draining"]["refused"] == 1
    assert round(drain.read(st, mono=169.9)["draining"]["lasts_s"], 3) == 0.1
    assert drain.read(st, mono=170.0)["draining"] is None, "ended at the bound, by a read"
    assert drain.admit(st, mono=170.0) is None, "and a start is admitted again"
    assert drain.read(st, mono=170.0) == {"draining": None, "held": 1}
    drain.leave(st)


def test_a_wall_clock_set_forward_does_not_end_a_drain():
    """A clock correction is not time passing: a stopping drain must not run out, and admit a
    run, because the wall clock jumped."""
    st = types.SimpleNamespace()
    drain.request(st, on=True, by="owner", reason="r", stopping=True, seconds=306,
                  now=1000.0, mono=50.0)
    far = 1000.0 + 10 * 24 * 3600                      # the wall clock, ten days on
    met = drain.admit(st, now=far, mono=51.0)
    assert met is not None and met["phase"] == "stopping"
    assert drain.read(st, now=far, mono=355.9)["draining"] is not None
    assert drain.read(st, now=far, mono=356.0)["draining"] is None, "its 306 s, and no more"


def test_a_wall_clock_set_back_does_not_keep_a_server_draining():
    """Nor can a clock set back hold a server past its bound: it would refuse work for as
    long as the correction, with nothing to end it."""
    st = types.SimpleNamespace()
    drain.request(st, on=True, by="owner", reason="r", now=1000.0, mono=50.0)
    back = 1000.0 - 3600.0                             # the wall clock, an hour earlier
    assert drain.read(st, now=back, mono=169.9)["draining"] is not None
    assert drain.read(st, now=back, mono=170.0)["draining"] is None
    assert drain.admit(st, now=back, mono=170.0) is None
    drain.leave(st)



def test_a_call_cannot_ask_for_longer_than_the_bound_and_only_a_new_call_extends_it():
    st = types.SimpleNamespace()
    got = drain.request(st, on=True, by="owner", reason="r", seconds=99999, now=0.0, mono=0.0)
    assert got["draining"]["lasts_s"] == drain.BOUND_S == got["draining"]["expires_at"]
    short = types.SimpleNamespace()
    assert drain.request(short, on=True, by="owner", reason="r", seconds=5, now=0.0,
                         mono=0.0)["draining"]["lasts_s"] == 5.0
    # nothing but a new call moves the end: reads and refused starts do not
    assert drain.admit(st, mono=100.0) is not None
    assert drain.read(st, mono=110.0)["draining"]["lasts_s"] == drain.BOUND_S - 110.0
    again = drain.request(st, on=True, by="owner", reason="r", drain=got["drain"],
                          now=110.0, mono=110.0)
    assert again["ok"] is True and again["drain"] == got["drain"]
    assert again["draining"]["since"] == 0.0, "the same drain, extended"
    assert again["draining"]["lasts_s"] == drain.BOUND_S and again["draining"]["extended"] == 1
    assert drain.read(st, mono=110.0 + drain.BOUND_S)["draining"] is None



def test_clearing_says_what_the_drain_refused_and_a_cleared_server_admits(capsys):
    st = types.SimpleNamespace()
    mine = drain.request(st, on=True, by="owner", reason="deploy r1")["drain"]
    met = drain.admit(st)
    drain.note_refused(st, met, act="opr-1", expectation="exp-1", participant="p")
    got = drain.request(st, on=False, by="owner", drain=mine)
    assert got["ok"] is True and got["cleared"] is True
    assert got["draining"] is None and got["held"] == 0
    assert got["was"]["refused"] == 1
    assert got["was"]["refused_starts"] == [{"act": "opr-1", "expectation": "exp-1",
                                             "participant": "p"}]
    assert drain.admit(st) is None
    # AUDIT: each change is one line on the server's own log (stdout -> python.log)
    said = [json.loads(line[len("drain: "):]) for line in capsys.readouterr().out.splitlines()
            if line.startswith("drain: ")]
    assert [x["event"] for x in said] == ["set", "cleared"]
    assert said[0]["reason"] == "deploy r1" and said[0]["by"] == "owner"
    assert said[0]["drain"] == said[1]["drain"] == mine and said[1]["forced"] is False


# -- a drain has an identity -------------------------------------------------------------

def test_a_clear_that_does_not_name_the_drain_changes_nothing():
    st = types.SimpleNamespace()
    mine = drain.request(st, on=True, by="owner", reason="r", now=0.0, mono=0.0)["drain"]
    for named in (None, "some-other-drain", ""):
        got = drain.request(st, on=False, by="owner", drain=named, now=1.0, mono=1.0)
        assert got["ok"] is False and got["cleared"] is False and got["refused"], named
        assert got["draining"]["since"] == 0.0 and got["was"] is None, "answered with what stands"
    assert drain.admit(st, mono=1.0) is not None, "still draining"
    assert drain.request(st, on=False, by="owner", drain=mine, mono=2.0)["cleared"] is True
    # and with nothing standing a clear says so
    got = drain.request(st, on=False, by="owner", drain=mine, mono=3.0)
    assert got["ok"] is False and got["refused"] == "no drain is standing"


def test_a_late_clear_from_an_earlier_drain_does_not_end_a_newer_one_or_its_stopping_phase():
    """THE STALE REQUEST. A deployment gave up and sent its clear; the request was delayed.
    Meanwhile its drain ended and another deployment drained the server and began to stop
    it. The late clear arrives now: it names a drain that is gone, and changes nothing."""
    st = types.SimpleNamespace()
    first = drain.request(st, on=True, by="owner", reason="deploy A", mono=0.0)["drain"]
    assert drain.read(st, mono=drain.BOUND_S)["draining"] is None        # A's drain ran out
    second = drain.request(st, on=True, by="owner", reason="deploy B", mono=200.0)["drain"]
    assert second != first
    late = drain.request(st, on=False, by="owner", drain=first, mono=201.0)
    assert late["ok"] is False and late["cleared"] is False
    assert late["draining"]["reason"] == "deploy B"
    assert drain.request(st, on=True, by="owner", reason="deploy B", stopping=True, seconds=306,
                         drain=second, mono=202.0)["draining"]["phase"] == "stopping"
    for stale in (dict(drain=first), dict(drain=None), dict(drain=first, force=True),
                  dict(force=True)):
        got = drain.request(st, on=False, by="owner", mono=203.0, **stale)
        assert got["ok"] is False and got["cleared"] is False, stale
        assert got["draining"]["phase"] == "stopping"
    assert drain.admit(st, mono=204.0) is not None, "no run got in"
    # a late EXTENSION from the earlier drain does nothing either
    late = drain.request(st, on=True, by="owner", reason="deploy A", drain=first, mono=205.0)
    assert late["ok"] is False and "drain" not in late
    assert drain.read(st, mono=205.0)["draining"]["reason"] == "deploy B"
    # only the one who is stopping it clears it
    assert drain.request(st, on=False, by="owner", drain=second, mono=206.0)["cleared"] is True


def test_a_call_naming_a_drain_that_is_gone_sets_nothing():
    st = types.SimpleNamespace()
    gone = drain.request(st, on=True, by="owner", reason="r", mono=0.0)["drain"]
    for stopping in (False, True):
        got = drain.request(st, on=True, by="owner", reason="r", drain=gone, stopping=stopping,
                            mono=drain.BOUND_S + 1.0)
        assert got["ok"] is False and got["draining"] is None and "not standing" in got["refused"]
    assert drain.admit(st, mono=drain.BOUND_S + 2.0) is None
    drain.leave(st)


def test_a_second_drain_request_does_not_take_over_one_that_stands():
    st = types.SimpleNamespace()
    mine = drain.request(st, on=True, by="owner", reason="deploy A", mono=0.0)
    other = drain.request(st, on=True, by="owner", reason="deploy B", mono=100.0)
    assert other["ok"] is False and "drain" not in other, "it is not given the id"
    assert other["draining"]["reason"] == "deploy A"
    assert other["draining"]["lasts_s"] == drain.BOUND_S - 100.0, "and did not extend it"
    assert drain.request(st, on=True, by="owner", reason="deploy A", drain=mine["drain"],
                         mono=100.0)["draining"]["lasts_s"] == drain.BOUND_S


def test_the_owner_can_force_an_ordinary_drain_to_end_but_never_a_stopping_one(capsys):
    st = types.SimpleNamespace()
    drain.request(st, on=True, by="owner", reason="a deployment that hung", mono=0.0)
    got = drain.request(st, on=False, by="owner", force=True, mono=1.0)
    assert got["ok"] is True and got["cleared"] is True and got["draining"] is None
    assert got["was"]["reason"] == "a deployment that hung"
    said = [json.loads(line[len("drain: "):]) for line in capsys.readouterr().out.splitlines()
            if line.startswith("drain: ")]
    assert said[-1]["event"] == "cleared" and said[-1]["forced"] is True, "logged as forced"
    # the stopping phase: by then whoever holds the id is killing the server
    mine = drain.request(st, on=True, by="owner", reason="r", stopping=True, seconds=306,
                         mono=2.0)["drain"]
    got = drain.request(st, on=False, by="owner", force=True, mono=3.0)
    assert got["ok"] is False and got["cleared"] is False
    assert "cleared only by whoever is stopping it" in got["refused"]
    assert drain.admit(st, mono=4.0) is not None
    assert drain.read(st, mono=2.0 + 306.0)["draining"] is None, "its bound still ends it"
    assert mine


def test_the_id_of_a_drain_is_never_in_a_read_or_a_refused_start(world):
    st = world["state"]
    mine = post(world, "/api/server/drain", {"on": True, "reason": "deploy"})["drain"]
    assert st.drain["draining"]["id"] == mine
    met = drain.admit(st)
    for seen in (get(world, "/api/server"), get(world, "/api/working"), drain.read(st),
                 {k: v for k, v in met.items() if k != "_drain"}):
        assert mine not in json.dumps(seen, default=str)
    other = post(world, "/api/server/drain", {"on": True, "reason": "another"})
    assert other["ok"] is False and mine not in json.dumps(other)


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
        assert drain.request(st, on=False, by="owner", drain=answer["drain"])["draining"] is None
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
    quiet = post(world, "/api/server/drain", {"on": True, "reason": "deploying r2",
                                              "drain": answer["drain"]})
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
        assert seen["phase"] == "draining" and 0 < seen["lasts_s"] <= drain.BOUND_S
        assert "id" not in seen and answer["drain"] not in json.dumps(seen)
        assert seen["refused_starts"] == [{"act": failed["id"], "expectation": exp,
                                          "participant": kw["participant"]}]
    assert get(world, "/api/working")["dispatches_held"] == 0
    # CLEARED (a cancelled deployment): the same work is addressed again and runs
    unnamed = post(world, "/api/server/drain", {"on": False})
    assert unnamed["ok"] is False and unnamed["draining"] is not None, "a clear names its drain"
    cleared = post(world, "/api/server/drain", {"on": False, "drain": answer["drain"]})
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


def test_a_delegation_refused_while_draining_is_not_started_by_recovery(delegated, rt):
    """RECOVERY'S RULE IS UNCHANGED: it reads delegations with no run of the child started
    OR FAILED since. A start refused while draining is a failure before start like any
    other, so the next server start does not start it. The work is open, and continuing it
    is somebody's act."""
    st, cv, child = delegated["state"], delegated["cv"], delegated["child"]
    assert [p["child"] for p in pending_delegations(cv)] == [child], "before: never started"
    drain.request(st, on=True, by="owner", reason="deploying r2")
    out = D.dispatch(st, **delegated["door"])
    assert out["ok"] is False and _starts(cv, child) == []
    assert len(_refusals(cv, child)) == 1
    assert pending_delegations(cv) == [], "failed before start: not one recovery reads"
    st.drain = {"draining": None, "admitted": 0}        # the restart: never draining
    done = recover_delegations(st, start=_real)
    assert done["recovered"] == [] and done["not_recovered"] == []
    assert _starts(cv, child) == [] and rt["grants"] == []
    assert [a for a in cv.history(caused_by=child)
            if a["act"] in (DELEGATION_RECOVERED, DELEGATION_NOT_RECOVERED)] == []
    # OPEN, and addressed again it runs
    state = cv.expectation_state(child)
    assert not state.get("satisfied_by") and not state.get("withdrawn")
    assert D.dispatch(st, **delegated["door"])["ok"] is True
    assert len(_starts(cv, child)) == 1


# -- what the server starts by itself meets the drain too, and does not loop --------------

@pytest.fixture()
def soon(world, monkeypatch):
    """Once the test calls `soon.live()`: `dispatch_soon` run at once on this thread,
    counted, and stopped if it ever looked like a loop. Until then it is captured, as the
    `world` fixture does."""
    import mentis.web as web

    class Soon(list):
        on = False

        def live(self):
            self.on = True
            self.clear()
    calls = Soon()

    def now(st, **kw):
        if not calls.on:
            return world["sent"].append(kw)
        calls.append(kw)
        assert len(calls) < 12, "dispatches are being started in a loop"
        return D.dispatch(world["state"], **kw)
    monkeypatch.setattr(web, "dispatch_soon", now)
    return calls


def test_a_resumption_meets_the_drain_and_does_not_loop(world, soon, fake):
    """A child that was running when the drain began finishes; its ending resumes the work
    it was delegated under, and that resumption is a new start: refused, once. The refusal's
    own ending asks about resumption again and finds nothing new."""
    from tests.test_decision_resume_parent import _resumes, _start_held
    from tests.test_delegate_coordinate import _present
    from tests.test_resume_on_return import _delegate
    plan = fake
    st, cv = world["state"], world["cv"]
    cid = a_conversation(world)
    _coach, parent, grant = _coordinator(world, cid)
    builder = _present(world, cid, "@Builder")
    child = _delegate(world, grant, builder, "build package R", return_to_me=True)
    soon.live()
    t, gate = _start_held(world, plan, child, builder)
    answer = drain.request(st, on=True, by="owner", reason="deploying r2")
    assert answer["held"] == 1
    gate.set()
    t.join(30)
    assert not t.is_alive()
    # the child finished normally; the parent was resumed in the record, once, and its start
    # was refused, once
    assert len(_starts(cv, child["expectation"])) == 1
    assert len(_resumes(cv, parent)) == 1
    assert [k["expectation"] for k in soon] == [parent]
    # the coordinator fixture records its own ended run of the parent (`coord-...`,
    # tests/respond_grant.py); the drain must start no other
    def started():
        return [a for a in _starts(cv, parent) if not str(a.get("execution")).startswith("coord-")]
    assert started() == [] and len(_refusals(cv, parent)) == 1
    now = drain.read(st)
    assert now["held"] == 0 and now["draining"]["refused"] == 1
    # NOTHING RESTARTS IT: cleared, the server starts nothing by itself
    assert drain.request(st, on=False, by="owner", force=True)["cleared"] is True
    assert len(soon) == 1 and started() == []


def test_a_consent_restart_meets_the_drain_and_is_not_tried_again(world, soon, monkeypatch):
    """A run halted because its consent was narrowed is restarted once, as a new start. While
    draining that start is refused; nothing asks again."""
    from mentis.operational import consent as C
    from mentis.web import compiled_runs
    from tests.test_permission_compiled import _Agents, _tracked_run
    st = world["state"]
    cv, run, repo, _told = _tracked_run(world, {"mode": "all"})
    monkeypatch.setattr(cv, "_compiled_st", type("S", (), {"agents": _Agents()})(),
                        raising=False)
    C.set_task(cv, run, owner=world["who"]["@brian"],
               consent={"mode": "deny", "workspaces": [repo]}, because="narrowed")
    begun = cv._act(run)
    exp = begun["caused_by"]
    cv.record_act(actor=world["steward"], act="result-returned",
                  conversation=begun["conversation"], turn=begun["turn"], execution="inst-t",
                  runtime="claude", caused_by=run, because="halted",
                  detail={"terminal": "cancelled"})
    drain.request(st, on=True, by="owner", reason="deploying r2")
    soon.live()
    assert compiled_runs.restart_if_asked(st, run)
    assert [k["expectation"] for k in soon] == [exp]
    assert len(_starts(cv, exp)) == 1, "only the halted run's own start: no new one"
    assert len(_refusals(cv, exp)) == 1
    assert compiled_runs.restart_if_asked(st, run) == compiled_runs.HELD
    assert len(soon) == 1 and drain.read(st)["draining"]["refused"] == 1


def test_a_continuation_meets_the_drain_and_does_not_loop(world, soon):
    """The owner replies in the thread and continues with the carrier: the Turn and its
    request are recorded, and the start is refused, once."""
    from tests._loop import _answer, _continue
    st, cv = world["state"], world["cv"]
    cid = a_conversation(world)
    exp, kw = _asked(world, cid)
    result = _answer(world, cid, kw["turn"], kw["participant"])
    drain.request(st, on=True, by="owner", reason="deploying r2")
    soon.live()
    out = _continue(world, cid, result, kw["participant"])
    (again,) = out["expectations"]
    assert [k["expectation"] for k in soon] == [again]
    assert _starts(cv, again) == [] and len(_refusals(cv, again)) == 1
    assert _starts(cv, exp) == [], "and the work it continues was not started either"
    assert drain.read(st)["draining"]["refused"] == 1


# -- the stopping phase ------------------------------------------------------------------


def test_stopping_is_refused_while_anything_is_held_and_changes_nothing():
    st = types.SimpleNamespace()
    assert drain.admit(st, mono=0.0) is None                       # one dispatch held
    got = drain.request(st, on=True, by="owner", reason="r", stopping=True, seconds=300, mono=1.0)
    assert got["ok"] is False and got["held"] == 1 and "1 dispatch(es) are held" in got["refused"]
    assert got["draining"] is None, "a refused call did not start a drain"
    # with an ordinary drain standing, a refused call neither extends it nor changes its phase
    mine = drain.request(st, on=True, by="owner", reason="r", now=2.0, mono=2.0)
    got = drain.request(st, on=True, by="owner", reason="r", stopping=True, seconds=300,
                        drain=mine["drain"], now=50.0, mono=50.0)
    assert got["ok"] is False and got["draining"]["phase"] == "draining"
    assert got["draining"]["lasts_s"] == drain.BOUND_S - 48.0 and got["draining"]["extended"] == 0
    drain.leave(st)
    got = drain.request(st, on=True, by="owner", reason="r", stopping=True, seconds=300,
                        drain=mine["drain"], now=60.0, mono=60.0)
    assert got["ok"] is True and got["held"] == 0 and got["at"] == 60.0
    assert got["draining"]["phase"] == "stopping" and got["draining"]["lasts_s"] == 300.0
    assert got["draining"]["since"] == 2.0 and got["drain"] == mine["drain"], "the same drain, now stopping"



def test_a_start_after_the_ordinary_bound_is_still_refused_while_stopping():
    """What the stopping phase is for: the stop can take longer than BOUND_S, and a start
    reaching the server in that time must still be refused."""
    st = types.SimpleNamespace()
    mine = drain.request(st, on=True, by="owner", reason="r", mono=0.0)["drain"]
    drain.request(st, on=True, by="owner", reason="r", stopping=True, seconds=306.0,
                  drain=mine, mono=10.0)
    late = 10.0 + drain.BOUND_S + 30.0
    assert late > drain.BOUND_S and drain.admit(st, mono=late) is not None
    assert drain.read(st, mono=315.9)["draining"]["phase"] == "stopping"
    # an ordinary call during the phase neither shortens it nor leaves it
    got = drain.request(st, on=True, by="owner", reason="r", drain=mine, mono=20.0)["draining"]
    assert got["phase"] == "stopping" and got["lasts_s"] == 296.0
    # STILL A BOUND: a stop that never comes frees the server, with no thread to do it
    assert drain.read(st, mono=316.0)["draining"] is None
    assert drain.admit(st, mono=316.0) is None



def test_the_stopping_bound_is_capped_and_a_clear_by_its_holder_ends_the_phase():
    st = types.SimpleNamespace()
    got = drain.request(st, on=True, by="owner", reason="r", stopping=True, seconds=10**9, mono=0.0)
    assert got["draining"]["lasts_s"] == drain.STOPPING_BOUND_S == got["stopping_bound_s"]
    assert drain.request(st, on=True, by="owner", reason="r", stopping=True, drain=got["drain"],
                         mono=1.0)["draining"]["lasts_s"] == drain.STOPPING_BOUND_S
    cleared = drain.request(st, on=False, by="owner", drain=got["drain"], mono=2.0)
    assert cleared["cleared"] is True and cleared["was"]["phase"] == "stopping"
    assert drain.admit(st, mono=2.0) is None


def test_stopping_and_a_start_at_the_same_moment_are_one_or_the_other(monkeypatch):
    """Starts racing the stopping call: either it was granted and no start ever gets in, or
    something was already held and it was refused, leaving the server not draining at all."""
    lock = threading.Lock()
    granted = set()
    for n in range(150):
        st = types.SimpleNamespace(cv=None)
        gate, inside, refused = threading.Event(), [], []
        settled = [threading.Event() for _ in range(4)]

        def fake_dispatch(st_, *, me, **kw):
            with lock:
                inside.append(me)
            settled[me].set()
            gate.wait(10)
            return {"ok": True}
        monkeypatch.setattr(D, "_dispatch", fake_dispatch)
        monkeypatch.setattr(D, "_failed_before_start",
                            lambda cv, **kw: refused.append(1) or "failed-act")
        line_up = threading.Barrier(5)

        def start(i):
            line_up.wait(10)
            time.sleep(random.random() * 0.001)
            D.dispatch(st, me=i)
            settled[i].set()
        threads = [threading.Thread(target=start, args=(i,), daemon=True) for i in range(4)]
        for t in threads:
            t.start()
        line_up.wait(10)
        time.sleep(random.random() * 0.001)
        got = drain.request(st, on=True, by="owner", reason="r", stopping=True, seconds=195)
        granted.add(got["ok"])
        for e in settled:
            assert e.wait(10)
        if got["ok"]:
            assert got["held"] == 0 and inside == [] and len(refused) == 4, n
        else:
            assert got["held"] >= 1 and got["draining"] is None, n
            assert len(inside) == 4 and refused == [], (n, "not draining: every start ran")
        gate.set()
        for t in threads:
            t.join(10)
    assert granted == {True, False}, f"the race only ever went one way: {granted}"



def test_the_route_grants_the_stopping_phase_only_with_nothing_held(world):
    st = world["state"]
    assert drain.admit(st) is None
    got = post(world, "/api/server/drain", {"on": True, "reason": "deploy", "stopping": True,
                                            "seconds": 306})
    assert got["ok"] is False and got["held"] == 1 and "are held" in got["refused"]
    assert get(world, "/api/server")["draining"] is None
    drain.leave(st)
    got = post(world, "/api/server/drain", {"on": True, "reason": "deploy", "stopping": True,
                                            "seconds": 306})
    assert got["ok"] is True and got["draining"]["phase"] == "stopping"
    assert 305 < got["draining"]["lasts_s"] <= 306, "the duration the server states"
    assert get(world, "/api/working")["draining"]["phase"] == "stopping"
    for body in ({"on": False, "stopping": True}, {"on": True, "reason": "r", "stopping": "yes"},
                 {"on": True, "reason": "r", "force": True}, {"on": False, "force": "yes"},
                 {"on": False, "drain": 7}, {"on": False, "drain": ""}):
        with pytest.raises(urllib.error.HTTPError) as refused:
            post(world, "/api/server/drain", body)
        assert refused.value.code == 400, body
    # by the route too: not forced, not unnamed, only by its id
    for body in ({"on": False}, {"on": False, "force": True}, {"on": False, "drain": "another"}):
        assert post(world, "/api/server/drain", body)["ok"] is False, body
    assert get(world, "/api/server")["draining"]["phase"] == "stopping"
    cleared = post(world, "/api/server/drain", {"on": False, "drain": got["drain"]})
    assert cleared["cleared"] is True and cleared["was"]["phase"] == "stopping"


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
    # the id is not authority: without the owner's session it clears nothing
    named = {"on": False, "drain": got["json"]["drain"]}
    assert call(port, "POST", "/api/server/drain", named)["status"] == 401
    assert drain.read(st)["draining"] is not None
    got = call(port, "POST", "/api/server/drain", named, how)
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
