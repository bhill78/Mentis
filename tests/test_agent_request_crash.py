"""A process ending at any boundary of an agent request, and what comes after it.

The record and a workspace's or Magnet's file are two stores, so a request can be
cut between them. Each case here runs the request in a real process that dies by
`os._exit` at one boundary (`tests/_agent_request_crash.py`), then reads the disk
from a new process's state, retries, and reopens to check it stayed that way. Found
by review (`ent-c32aa128d5ef`): a manifest naming a Conversation the record lacked
stranded the workspace for good."""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time

import pytest

import mentis.magnet as M
import mentis.web as web
from mentis.execution import RunResult
from mentis.fluid import arrangements as A
from mentis.fluid import commands
from mentis.fluid import workspace_manifest as wm
from mentis.web import _State, dispatch as D, fixture
from tests import _agent_request_crash as child
from tests._loop import grant_of_run

CHILD = pathlib.Path(child.__file__)
TEXT = "Make a report from this"


# -- a Brain with somewhere to ask from ----------------------------------------

def _close(state) -> None:
    state.corpus.close()


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    root = tmp_path_factory.mktemp("request-crash") / "corpus"
    who = fixture.build(str(root))["who"]
    state = _State(str(root))
    magnet = commands.magnet_command(state, commands.MAGNET_CREATE, "home", {
        "seed": {"sources": [{"kind": "conversation", "conversation": "ent-src"}],
                 "selection": {}, "collection": {"mode": "one-time"},
                 "synthesis": {"mode": "manual"},
                 "notifications": {"newItems": False, "changes": False,
                                   "failures": False},
                 "presentation": {"renderer": "disc"}},
        "attach": {"zone": {"type": "zone", "show": "magnet", "name": "Board"},
                   "base": {"format": A.FORMAT, "version": 2,
                            "tree": {"type": "zone", "id": "stage",
                                     "show": "objects"}}}})
    assert magnet[0] == 200, magnet
    made = {"root": str(root), "author": who["@brian"],
            "agent": state.cv.create_participant("@Scribe"),
            "workspace": wm.create(str(root), {"name": "Evidence"})["id"],
            "magnet": magnet[1]["magnet"]["id"],
            "conversation": state.cv.open_conversation(
                "Somewhere", about="", attributed_to=who["@brian"])}
    _close(state)
    return made


@pytest.fixture()
def brain(base, tmp_path):
    root = tmp_path / "corpus"
    shutil.copytree(base["root"], root)
    return {**base, "root": str(root), "dir": tmp_path}


def request(brain, kind, text=TEXT, op="the-request", **more) -> dict:
    return {"from": {kind: brain[kind]}, "author": brain["author"], "text": text,
            "action": "ask-participant", "addressed_to": [brain["agent"]],
            "dispatch": [{"participant": brain["agent"], "work": text}],
            "op": op, **more}


def crash(brain, boundary, body) -> None:
    """The request, in a process of its own that ends at `boundary`."""
    path = brain["dir"] / "body.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    got = subprocess.run(
        [sys.executable, str(CHILD), brain["root"], boundary, str(path)],
        capture_output=True, text=True, timeout=120,
        cwd=CHILD.parent.parent,
        env={**os.environ, "PYTHONPATH": str(CHILD.parent.parent)})
    assert got.returncode == child.CRASHED, (
        f"never reached {boundary}: exit {got.returncode}\n{got.stdout}\n{got.stderr}")


class Process:
    """What a new server finds: the Brain reopened, and nothing else carried over.
    Its runs are real dispatches, on a scripted runtime."""

    def __init__(self, brain, monkeypatch):
        self.brain, self.state = brain, _State(brain["root"])
        self.grants, self.started = [], []
        svc = self.state.agents

        def perform(spec):
            self.grants.append(grant_of_run(svc, spec, self.state.path))
            now = time.time()
            return RunResult(run_id=spec.run_id, backend=spec.backend,
                             started=True, stop_reason="end_turn",
                             text="done: here is the chart",
                             started_at=now, finished_at=now)
        ex = svc.execution
        ex.script = {b["id"]: perform for b in ex.backends()}

        def starting(st, **kw):
            self.started.append(kw)
            D.dispatch(st, **kw)
        monkeypatch.setattr(web, "dispatch_soon", starting)

    def ask(self, body):
        return commands.agent_request(
            self.state, body,
            written_by=lambda: web._observed_writer(self.state, None))

    def conversations(self) -> set:
        return {c["id"] for c in self.state.cv.all_conversations()}

    def requests_in(self, cid) -> list:
        return [t["turn"] for t in self.state.cv.turns(cid)
                if TEXT in json.dumps(t["entry"]["body"])
                and t["entry"]["attributed_to"] == self.brain["author"]]

    def named_by_file(self, kind):
        if kind == "workspace":
            return wm.workspace(self.brain["root"], self.brain[kind])[
                "manifest"].get("conversation")
        if kind == "magnet":
            return M.read(self.brain["root"], self.brain[kind]).get("conversation")
        return None

    def close(self):
        _close(self.state)


@pytest.fixture()
def reopen(brain, monkeypatch):
    opened = []

    def again():
        for p in opened:
            p.close()
        opened.clear()
        opened.append(Process(brain, monkeypatch))
        return opened[-1]
    yield again
    for p in opened:
        p.close()


def _cases():
    for boundary in child.EVERY:
        yield "workspace", boundary
        yield "magnet", boundary
        if boundary not in child.OWN_ONLY:
            yield "conversation", boundary


# -- every boundary, for every origin that reaches it ---------------------------

@pytest.mark.parametrize("kind,boundary", list(_cases()))
def test_a_crash_here_strands_nothing_and_repeats_nothing(
        brain, reopen, kind, boundary):
    p = reopen()
    baseline = p.conversations()
    body = request(brain, kind)
    p.close()

    crash(brain, boundary, body)

    # WHAT THE DISK SAYS, BEFORE ANYTHING TOUCHES IT.
    p = reopen()
    committed = boundary not in child.IN_TRANSACTION
    created_by_crash = p.conversations() - baseline
    own = kind != "conversation"
    assert len(created_by_crash) == (1 if committed and own else 0)
    named = p.named_by_file(kind)
    assert not named or named in p.conversations(), \
        "a file never names a Conversation the record lacks"
    if committed and own:
        assert bool(named) == (boundary not in ("committed", "file-temp"))
    if boundary == "file-temp":
        assert wm.workspaces(brain["root"]) is not None, "its temporary is no workspace"

    # THE RETRY.
    status, got, _ = p.ask(body)
    assert status == 200, got
    cid = got["route"]["conversation"]
    assert got["replayed"] is committed
    assert got["route"]["created"] is (not committed and own)
    if kind == "conversation":
        assert cid == brain["conversation"]
    made = p.conversations() - baseline

    def holds(process):
        assert process.conversations() - baseline == made
        assert made == ({cid} if own else set()), "one Conversation, never two"
        assert len(process.requests_in(cid)) == 1, "one request, never two"
        assert process.named_by_file(kind) == (cid if own else None)
        expectation = got["expectations"][0]
        runs = [a for a in process.state.corpus.operational(caused_by=expectation)
                if a["act"] == "execution-started"]
        assert len(runs) == 1, "one run, whichever process started it"
        assert runs[0]["conversation"] == cid

    holds(p)
    ran_here = boundary not in child.RUNNING
    assert len(p.started) == (1 if ran_here else 0)
    if ran_here:
        assert p.grants[0]["conversation"] == cid, \
            "by the grant any request's run has, over where it went"

    # ASKED AGAIN, IN THE SAME PROCESS AND THEN IN ANOTHER.
    status, again, _ = p.ask(body)
    assert status == 200 and again["replayed"] and again["post"] == got["post"]
    holds(p)
    before = len(p.started)
    assert before == (1 if ran_here else 0)

    p = reopen()
    status, again, _ = p.ask(body)
    assert status == 200 and again["replayed"] and again["post"] == got["post"]
    assert again["route"]["conversation"] == cid
    assert not p.started
    holds(p)

    # AND THE NEXT REQUEST FINDS THE SAME PLACE.
    status, next_one, _ = p.ask(request(brain, kind, text="And another", op="next"))
    assert status == 200, next_one
    assert next_one["route"]["conversation"] == cid
    assert next_one["route"]["created"] is False
    assert next_one["post"] != got["post"]
    assert p.conversations() - baseline == made


# -- what else can come first ----------------------------------------------------

@pytest.mark.parametrize("kind", ["workspace", "magnet"])
@pytest.mark.parametrize("boundary", ["committed", "file-temp"])
def test_another_request_arriving_first_uses_the_claim_and_tells_the_file(
        brain, reopen, kind, boundary):
    p = reopen()
    baseline = p.conversations()
    body = request(brain, kind)
    p.close()
    crash(brain, boundary, body)

    p = reopen()
    someone = p.state.cv.create_participant("@Somebody")
    cid, = p.conversations() - baseline
    assert p.named_by_file(kind) is None
    status, other, _ = p.ask({**request(brain, kind, text="Another", op="other"),
                              "author": someone})
    assert status == 200, other
    assert other["route"] == {"rule": kind, "conversation": cid, "created": False}
    assert p.named_by_file(kind) == cid
    assert p.conversations() - baseline == {cid}

    # The cut request is still somebody's to retry, and still runs once.
    status, retried, _ = p.ask(body)
    assert status == 200 and retried["replayed"], retried
    assert retried["route"]["conversation"] == cid
    assert [s["expectation"] for s in p.started][-1] == retried["expectations"][0]
    assert len(p.requests_in(cid)) == 1


@pytest.mark.parametrize("boundary", ["committed", "file-temp"])
def test_the_magnets_own_door_finds_what_a_cut_request_claimed(
        brain, reopen, boundary):
    p = reopen()
    baseline = p.conversations()
    body = request(brain, "magnet")
    p.close()
    crash(brain, boundary, body)

    p = reopen()
    cid, = p.conversations() - baseline
    status, got, _ = commands.magnet_definition_command(
        p.state, "magnet-conversation", brain["magnet"],
        {"author": brain["author"]},
        written_by=lambda: web._observed_writer(p.state, None))
    assert status == 200 and got == {"magnet": brain["magnet"], "created": False,
                                     "conversation": cid}
    assert p.named_by_file("magnet") == cid
    assert p.conversations() - baseline == {cid}


def _file_says(brain, kind, cid):
    """A copy that names something else: only a hand or a restore could leave this."""
    root = brain["root"]
    if kind == "workspace":
        wm.set_conversation(root, brain[kind], cid)
    else:
        M.write(root, brain[kind], {**M.read(root, brain[kind]), "conversation": cid})


@pytest.mark.parametrize("kind", ["workspace", "magnet"])
@pytest.mark.parametrize("boundary", ["committed", "file-temp", "file-replaced"])
def test_a_cut_request_finds_its_claim_though_the_file_names_another(
        brain, reopen, kind, boundary):
    p = reopen()
    baseline = p.conversations()
    body = request(brain, kind)
    p.close()
    crash(brain, boundary, body)

    p = reopen()
    cid, = p.conversations() - baseline
    _file_says(brain, kind, brain["conversation"])

    # A real Conversation, so the file cannot be told wrong by what it names.
    p = reopen()
    assert p.named_by_file(kind) == brain["conversation"]
    status, got, _ = p.ask(body)
    assert status == 200 and got["replayed"], got
    assert got["route"]["conversation"] == cid
    assert p.named_by_file(kind) == cid
    assert len(p.requests_in(cid)) == 1
    assert p.requests_in(brain["conversation"]) == []

    _file_says(brain, kind, brain["conversation"])
    p = reopen()
    status, next_one, _ = p.ask(request(brain, kind, text="And another", op="next"))
    assert status == 200, next_one
    assert next_one["route"] == {"rule": kind, "conversation": cid, "created": False}
    assert p.named_by_file(kind) == cid
    assert p.grants[-1]["conversation"] == cid
    assert p.conversations() - baseline == {cid}
    assert p.requests_in(brain["conversation"]) == []


def test_the_magnets_own_door_finds_its_claim_though_the_file_names_another(
        brain, reopen):
    p = reopen()
    baseline = p.conversations()
    body = request(brain, "magnet")
    p.close()
    crash(brain, "committed", body)

    p = reopen()
    cid, = p.conversations() - baseline
    _file_says(brain, "magnet", brain["conversation"])
    p = reopen()
    status, got, _ = commands.magnet_definition_command(
        p.state, "magnet-conversation", brain["magnet"],
        {"author": brain["author"]},
        written_by=lambda: web._observed_writer(p.state, None))
    assert status == 200 and got == {"magnet": brain["magnet"], "created": False,
                                     "conversation": cid}
    assert p.named_by_file("magnet") == cid
    assert p.conversations() - baseline == {cid}


def test_a_cut_retry_is_answered_though_the_workspace_was_deleted_since(
        brain, reopen):
    p = reopen()
    body = request(brain, "workspace")
    p.close()
    crash(brain, "before-start", body)

    p = reopen()
    wm.delete(brain["root"], brain["workspace"])
    status, got, _ = p.ask(body)
    assert status == 200 and got["replayed"], got
    assert len(p.started) == 1, "what it asked for still runs"
    status, fresh, _ = p.ask(request(brain, "workspace", op="after"))
    assert status == 410 and fresh["kind"] == "Gone"


def test_a_retry_with_the_key_for_another_request_is_refused(brain, reopen):
    p = reopen()
    body = request(brain, "workspace")
    p.close()
    crash(brain, "committed", body)

    p = reopen()
    baseline = p.conversations()
    for other in ({**body, "text": "Different"},
                  {**body, "from": {"magnet": brain["magnet"]}},
                  {**body, "destination": {"conversation": brain["conversation"]}}):
        status, got, _ = p.ask(other)
        assert status == 422 and got["refused"] is True, got
    assert p.conversations() == baseline and not p.started
    assert p.named_by_file("workspace") is None, "nothing was done by a refusal"


# -- what a retry must not start -------------------------------------------------

def test_a_retry_does_not_rerun_a_request_whose_start_failed(brain, reopen):
    p = reopen()
    body = request(brain, "workspace")
    p.close()
    crash(brain, "before-start", body)

    p = reopen()
    act = p.state.corpus.operational(act=commands.REQUEST_ROUTED)[0]
    expectation = act["detail"]["starts"][0]["expectation"]
    p.state.cv.record_act(
        actor=brain["agent"], act="delivery-failed", caused_by=expectation,
        conversation=act["conversation"], turn=act["turn"], because="no runtime",
        detail={"stage": "selection", "before_execution_started": True})
    status, got, _ = p.ask(body)
    assert status == 200 and got["replayed"] and not p.started, got


def test_a_request_handed_on_in_this_process_is_not_handed_on_again(
        brain, reopen, monkeypatch):
    p = reopen()
    sent = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: sent.append(kw))
    body = request(brain, "workspace")
    status, first, _ = p.ask(body)
    assert status == 200 and len(sent) == 1, first
    status, again, _ = p.ask(body)
    assert status == 200 and again["replayed"] and len(sent) == 1, \
        "its thread has not reached its start act yet, and may not be late"


def test_a_start_that_could_not_be_handed_on_is_a_retrys_to_make(
        brain, reopen, monkeypatch):
    p = reopen()
    sent = []

    def refusing(st, **kw):
        if not sent:
            sent.append(None)
            raise RuntimeError("can't start new thread")
        sent.append(kw)
    monkeypatch.setattr(web, "dispatch_soon", refusing)
    body = request(brain, "workspace")
    with pytest.raises(RuntimeError):
        p.ask(body)
    status, got, _ = p.ask(body)
    assert status == 200 and got["replayed"] and len(sent) == 2, got
    assert sent[1]["expectation"] == got["expectations"][0]


def test_a_retry_cannot_slip_between_the_commit_and_the_hand_on(
        brain, reopen, monkeypatch):
    """The record says nothing has started until the hand-on, so without the door's
    lock a retry arriving there would start it too."""
    p = reopen()
    sent = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: sent.append(kw))
    body = request(brain, "workspace")
    committed, retried = threading.Event(), threading.Event()
    real = commands._tell_the_file

    def holding(*a):
        committed.set()
        retried.wait(1)
        return real(*a)
    monkeypatch.setattr(commands, "_tell_the_file", holding)
    answers = []

    def retry():
        assert committed.wait(30)
        answers.append(p.ask(body))
        retried.set()
    threads = [threading.Thread(target=lambda: answers.append(p.ask(body))),
               threading.Thread(target=retry)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert [a[0] for a in answers] == [200, 200], answers
    assert len(sent) == 1


def test_many_at_once_with_one_key_are_one_request(brain, reopen, monkeypatch):
    p = reopen()
    baseline = p.conversations()
    sent = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: sent.append(kw))
    body = request(brain, "workspace")
    answers, gate = [], threading.Barrier(6)

    def one():
        gate.wait(5)
        answers.append(p.ask(body))
    threads = [threading.Thread(target=one) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert [a[0] for a in answers] == [200] * 6, answers
    assert len({a[1]["post"] for a in answers}) == 1
    assert sum(a[1]["route"]["created"] for a in answers) == 1
    assert len(p.conversations() - baseline) == 1 and len(sent) == 1


def test_what_a_crash_committed_is_still_only_a_post(brain, reopen):
    """The authority a retried start runs under is what the request recorded, and
    nothing here is a worker's."""
    p = reopen()
    body = request(brain, "workspace")
    p.close()
    crash(brain, "before-start", body)

    p = reopen()
    status, got, _ = p.ask(body)
    assert status == 200, got
    grant = p.grants[0]
    assert grant["conversation"] == got["route"]["conversation"]
    expectation = got["expectations"][0]
    assert p.state.cv.authority_of(expectation)["operations"] == grant["operations"]
    src = pathlib.Path(commands.__file__).read_text(encoding="utf-8")
    assert "mentis.execution" not in src and "subprocess" not in src
