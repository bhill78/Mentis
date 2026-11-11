"""A keyed `delegate` cut at any write, then sent again: one delegation, never two.

Round 2 -- Z (`docs/modernization/CONTRACT.md`). A session's write carries an
`op_key` and is resent by the bridge's outbox when its answer was lost
(`mentis.outbox`); the server answers a repeated key with the first answer
(`mentis.opkeys`). `delegate` used to write its key AFTER the delegation, in a
transaction of its own, and its own writes (join, Turn, child request, the
`work-delegated` act) each committed alone -- so a process that died between
them left a delegation, or part of one, that the resend did not find, and the
resend delegated again.

Each case here runs the keyed delegation in a real process that dies by
`os._exit` at one boundary (`tests/_delegate_opkey_crash.py`), then reopens the
Brain in a new server, as a restarted Mentis would, and sends the same write
again -- directly, or through the outbox at the next session's start -- and
then once more.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer

import pytest

import mentis.opkeys as opkeys
import mentis.web as web
from mentis.outbox import pending_all
from mentis.session_identity import default_alias
from mentis.web import _Handler, _State, fixture
from mentis.worker import CAPABILITY_HEADER, SESSION_ROUTE
from tests import _delegate_opkey_crash as child
from tests.test_manual_session import _mcp, _post

CHILD = pathlib.Path(child.__file__)
RUNTIME, HOST = "codex", "CRASHHOST"
WORK = "Chart the quarterly numbers"


class Server:
    """One Mentis process over the Brain: its own state, grants and HTTP door."""

    def __init__(self, root, workdir, monkeypatch=None):
        self.st = _State(str(root), str(workdir))
        handler = type("H", (_Handler,), {"state": self.st})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.sent = []
        if monkeypatch is not None:
            monkeypatch.setattr(web, "dispatch_soon",
                                lambda st, **kw: self.sent.append(kw))

    def session(self, continues=None):
        status, grant = _post(self.url + SESSION_ROUTE,
                              {"corpus": self.st.path, "runtime": RUNTIME,
                               "host": HOST,
                               **({"continues": continues} if continues else {})},
                              {"X-Mentis-Client": "1"})
        assert status == 200, grant

        def op(op_name, **args):
            return _post(self.url + "/api/worker",
                         {"corpus": self.st.path, "op": op_name, "args": args},
                         {CAPABILITY_HEADER: grant["grant"]})
        return grant, op

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.st.corpus.close()


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """A Brain where a session recorded a request and summoned a helper."""
    where = tmp_path_factory.mktemp("delegate-crash")
    root = where / "corpus"
    fixture.build(str(root))
    server = Server(root, where)
    try:
        grant, op = server.session()
        _, opened = op("open_conversation", name="Numbers")
        _, request = op("record_request", conversation=opened["conversation"],
                        text="the quarterly report")
        _, helper = op("summon_participant", alias="Charter",
                       conversation=opened["conversation"],
                       under=request["expectation"])
        made = {"root": str(root), "execution": grant["execution"],
                "participant": grant["participant"],
                "conversation": opened["conversation"],
                "request": request["expectation"],
                "helper": helper["participant"]}
    finally:
        server.close()
    return made


@pytest.fixture()
def brain(base, tmp_path):
    root = tmp_path / "corpus"
    shutil.copytree(base["root"], root)
    return {**base, "root": str(root), "dir": tmp_path,
            "outbox": str(tmp_path / "outbox")}


def delegation(brain, key="deleg-1"):
    return {"participant": brain["helper"], "work": WORK,
            "conversation": brain["conversation"],
            "under": brain["request"], "op_key": key}


def crash(brain, boundary, args, *, outbox=False) -> None:
    """The delegation, in a process of its own that ends at `boundary`."""
    path = brain["dir"] / "body.json"
    path.write_text(json.dumps({
        "execution": brain["execution"], "participant": None,
        "runtime": RUNTIME, "host": HOST, "args": args,
        **({"outbox": brain["outbox"]} if outbox else {})}), encoding="utf-8")
    got = subprocess.run(
        [sys.executable, str(CHILD), brain["root"], str(brain["dir"]),
         boundary, str(path)],
        capture_output=True, text=True, timeout=120,
        cwd=CHILD.parent.parent,
        env={**os.environ, "PYTHONPATH": str(CHILD.parent.parent)})
    assert got.returncode == child.CRASHED, (
        f"never reached {boundary}: exit {got.returncode}\n{got.stdout}\n{got.stderr}")


def counted(cv, brain, key="deleg-1") -> dict:
    """Everything a delegation writes, counted: each must be there once."""
    ops = cv.corpus.operational
    work_turns = [t for t in cv.turns(brain["conversation"])
                  if WORK in json.dumps(t["entry"]["body"])]
    children = [a for a in ops(act="expectation-recorded")
                if a.get("caused_by") == brain["request"]]
    keys = [a for a in ops(act="operation-keyed")
            if (a.get("detail") or {}).get("op") == f"worker:delegate:{key}"]
    return {"turns": len(work_turns), "children": len(children),
            "delegations": len(ops(act="work-delegated")), "keys": len(keys)}


ONE = {"turns": 1, "children": 1, "delegations": 1, "keys": 1}


@pytest.mark.parametrize("boundary", child.EVERY)
def test_a_resend_after_a_crash_at_any_write_delegates_once(brain, boundary,
                                                          monkeypatch):
    args = delegation(brain)
    crash(brain, boundary, args)
    server = Server(brain["root"], brain["dir"], monkeypatch)
    try:
        cv = server.st.cv
        before = counted(cv, brain)
        if boundary != "committed":
            # NOTHING OF IT SURVIVED: the delegation and its key are one
            # transaction, so a crash anywhere before its COMMIT leaves none.
            assert before == {"turns": 0, "children": 0, "delegations": 0,
                              "keys": 0}, before
        _, op = server.session(continues=brain["execution"])
        status, first = op("delegate", **args)
        assert status == 200, first
        assert counted(cv, brain) == ONE
        status, again = op("delegate", **args)
        assert status == 200 and again["replayed"] is True, again
        assert again["expectation"] == first["expectation"]
        assert counted(cv, brain) == ONE
        # A delegation that was not durable is dispatched by the resend; the
        # replay of a durable one never dispatches again.
        assert len(server.sent) == (0 if boundary == "committed" else 1)
    finally:
        server.close()


@pytest.mark.parametrize("boundary", ("said", "delegated", "keying",
                                      "committing", "committed"))
def test_the_outbox_resends_a_crashed_delegation_once(brain, boundary,
                                                       monkeypatch):
    """The bridge kept the write, the server died under it, and the next
    session's start resends it from the outbox, as the gone session."""
    args = delegation(brain, key="outbox-1")
    crash(brain, boundary, args, outbox=True)
    alias = default_alias(RUNTIME, HOST)
    assert len(pending_all(alias, brain["outbox"])) == 1
    server = Server(brain["root"], brain["dir"], monkeypatch)
    try:
        world = {"st": server.st, "url": server.url, "outbox": brain["outbox"]}
        _mcp(world, RUNTIME, [("orient", {})], host=HOST)
        assert pending_all(alias, brain["outbox"]) == []
        assert counted(server.st.cv, brain, "outbox-1") == ONE
        # And a later start finds nothing to send.
        _mcp(world, RUNTIME, [("orient", {})], host=HOST)
        assert counted(server.st.cv, brain, "outbox-1") == ONE
    finally:
        server.close()


def test_two_servers_sending_one_key_at_once_delegate_once(brain, monkeypatch):
    """Two sends of one key in flight at once, each in a process of its own --
    which the in-process per-key lock cannot see. Both are past the first look
    for the key before either writes; one delegation results, and the other
    is answered with it."""
    # Two processes: two Brains opened on one file, and no lock shared.
    monkeypatch.setattr(opkeys, "_lock_for", lambda key: threading.Lock())
    sent = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: sent.append(kw))
    both = threading.Barrier(2, timeout=30)
    from mentis.web import dispatch as D
    real = D.review_readiness

    def readiness(*a, **kw):
        # REACHED BY EACH, AFTER THE FIRST LOOK AND BEFORE ANY WRITE.
        both.wait()
        return real(*a, **kw)
    monkeypatch.setattr(D, "review_readiness", readiness)
    one = Server(brain["root"], brain["dir"])
    two = Server(brain["root"], brain["dir"])
    try:
        _, op1 = one.session(continues=brain["execution"])
        _, op2 = two.session(continues=brain["execution"])
        args = delegation(brain, key="both-1")
        got = {}

        def send(name, op):
            got[name] = op("delegate", **args)
        threads = [threading.Thread(target=send, args=(n, o))
                   for n, o in (("one", op1), ("two", op2))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        assert {s for s, _ in got.values()} == {200}, got
        answers = sorted(got.values(), key=lambda g: bool(g[1].get("replayed")))
        assert answers[0][1].get("replayed") is None
        assert answers[1][1]["replayed"] is True
        assert answers[0][1]["expectation"] == answers[1][1]["expectation"]
        assert counted(one.st.cv, brain, "both-1") == ONE
        assert len(sent) == 1
    finally:
        one.close()
        two.close()


def test_without_an_op_key_each_send_is_a_delegation(brain, monkeypatch):
    """No key, no identity: a resend without one is a new request by
    definition, and is delegated again. The bridge always sends a key; a
    client that sends none has said each send is its own."""
    server = Server(brain["root"], brain["dir"], monkeypatch)
    try:
        _, op = server.session(continues=brain["execution"])
        args = {k: v for k, v in delegation(brain).items() if k != "op_key"}
        assert op("delegate", **args)[0] == 200
        assert op("delegate", **args)[0] == 200
        got = counted(server.st.cv, brain)
        assert (got["children"], got["delegations"], got["keys"]) == (2, 2, 0)
        assert len(server.sent) == 2
    finally:
        server.close()


# -- picking up discovered work: the same window, the same answer ----------------

from tests._loop import world, runs  # noqa: E402,F401
from tests.test_delegate_coordinate import (  # noqa: E402
    _discovered, _present, _run_of)


def test_a_pick_up_cut_before_its_key_is_answered_not_refused(world, runs,
                                                              monkeypatch):
    """Picking up discovered work wrote its claim in one transaction and its
    key in the next. Cut between them, the resend was refused as "already
    carried" -- by itself -- and never told what it had done. Now the claim
    and the key are one transaction: the cut leaves neither, the resend picks
    it up, and a further resend is answered with that."""
    from mentis.web import _surface
    from mentis.worker import _operate
    from tests.gravity_choice import owner_chooses
    cv = world["cv"]
    run = _run_of(world, runs, "gesture")
    grant = run["grant"]
    bob = _present(world, run["cid"], "@Bob")
    found = _discovered(world, grant)
    owner_chooses(_surface(world["state"]), grant, found)
    args = {"participant": bob, "work": "take it", "expectation": found,
            "op_key": "pick-1"}

    def send():
        surface = _surface(world["state"])
        return opkeys.keyed(world["state"].corpus, surface.cv,
                            participant=grant["participant"], op="delegate",
                            args=args,
                            run=lambda call: _operate(surface, "delegate",
                                                      call, grant),
                            execution=grant["instance"],
                            runtime=grant.get("runtime"))

    class Died(BaseException):
        """The process ending: nothing after it runs."""

    real = opkeys.remember

    def dies(*a, **kw):
        raise Died()
    monkeypatch.setattr(opkeys, "remember", dies)
    with pytest.raises(Died):
        send()
    monkeypatch.setattr(opkeys, "remember", real)
    assert cv.expectation_state(found)["unassigned"] is True
    first = send()
    assert first["picked_up"] is True and first["expectation"] == found
    again = send()
    assert again["replayed"] is True and again["expectation"] == found
    picks = [a for a in cv.corpus.operational(act="work-delegated")
             if found in (a.get("about") or ())]
    assert len(picks) == 1


def test_a_keyed_write_phase_without_done_commits_nothing():
    """Review (round 2 final): the docstring's promise is kept -- a keyed block that ends
    without `done` rolls back rather than committing writes with no key."""
    import contextlib
    from mentis import opkeys

    class _Corpus:
        def __init__(self):
            self.committed = self.rolled_back = 0

        @contextlib.contextmanager
        def atomic(self):
            try:
                yield
            except BaseException:
                self.rolled_back += 1
                raise
            self.committed += 1

    corpus = _Corpus()
    pending = opkeys._Pending(prior=lambda: None, record=lambda out: None)
    token = opkeys._pending.set(pending)
    try:
        with pytest.raises(RuntimeError):
            with opkeys.writing(corpus):
                pass
        assert (corpus.committed, corpus.rolled_back) == (0, 1)
    finally:
        opkeys._pending.reset(token)


# -- round 3 final (B4) measured this; round 4 (C2) closes it: a DISPATCHED run's delegations --

def test_a_dispatched_runs_delegate_sent_again_is_one_child(world, monkeypatch):
    """Round 3 (B4) measured the exposure here: a dispatched run's bridge added no
    `op_key`, so `delegate` sent twice without one made two children. Now the run's own
    bridge -- started from the MCP server the dispatch handed the run, as a runtime starts
    it -- keys it by (execution, operation, arguments): the same key twice is one child,
    and NO key twice is one child too (`worker.write_key`, `outbox.derived_key`)."""
    import time

    from mentis.execution import RunResult
    from mentis.web import dispatch as D
    from tests._dispatched_bridge import Bridge
    from tests._loop import a_conversation, say

    st, cv = world["state"], world["cv"]
    st.agents.workers_read(st.path, answers_at=world["base"])
    helper = cv.create_participant("@Helper", about="an agent")
    answers = []

    def perform(spec):
        bridge = Bridge(spec)
        try:
            for args in ({"participant": helper, "work": "part A", "op_key": "same"},
                         {"participant": helper, "work": "part A", "op_key": "same"},
                         {"participant": helper, "work": "part B"},
                         {"participant": helper, "work": "part B"}):
                answers.append(bridge.call("delegate", **args))
        finally:
            bridge.close()
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done", started_at=now,
                         finished_at=now)
    st.agents.execution.script = {"codex": perform}
    ada = cv.create_participant("@Ada", about="an agent")
    cid = a_conversation(world)
    monkeypatch.setattr(web, "dispatch_soon", lambda s, **kw: (
        D.dispatch(s, **kw) if kw.get("participant") == ada else None))
    out = say(world, cid, "split it", action="ask-participant",
              dispatch=[{"participant": ada, "work": "split it", "runtime": "codex"}])
    exp = out["expectations"][0]
    children = [a for a in cv.corpus.operational(act="expectation-recorded")
                if a.get("caused_by") == exp]
    works = [json.dumps(cv.corpus.read([a["turn"]])[0]["body"]) for a in children]
    assert len(answers) == 4 and not any(err for err, _ in answers), answers
    assert answers[1][1].get("replayed") is True
    assert answers[3][1].get("replayed") is True
    assert sum("part A" in w for w in works) == 1     # its own key: once
    assert sum("part B" in w for w in works) == 1     # no key: once (was twice)
