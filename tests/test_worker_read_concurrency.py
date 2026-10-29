"""An agent's read-only call reads beside the writer, exactly as a GET does.

WHY. Agents' Mentis calls arrive as `POST /api/worker`. A POST read through the
single writer connection under the store's lock, so every agent read queued
behind every write and behind each other (profiled 2026-10-29: one answer took
over 60 s while a run was active). A GET already reads beside the writer (R1).

What is asserted:

  * A READ-ONLY OPERATION (`worker.READ_ONLY`) is answered while another
    thread holds an open write transaction, without waiting for it.
  * AN OPERATION NOT ON THE LIST reads as before: not beside the writer.
  * A LISTED OPERATION THAT TRIES TO WRITE is refused inside the scope and
    answered again from the start outside it -- even if it caught the
    refusal -- with the second answer the one returned.
  * THE SAME ANSWERS: a cached read taken beside an open transaction is not
    kept under a token that already counts that transaction's rows.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import mentis.worker as worker
from mentis.conversation import text
from mentis.spine.store import _reading_beside
from mentis.web import _Handler, _State, fixture
from mentis.worker import (CAPABILITY_HEADER, READ_ONLY, READS, SOURCE_READS,
                           permitted)


@pytest.fixture(scope="module")
def owner(tmp_path_factory):
    root = tmp_path_factory.mktemp("beside") / "corpus"
    world = fixture.build(str(root))
    state = _State(str(root))
    handler = type("H", (_Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    grant = state.agents.authority._grant("exec-under-test", state.path)
    yield {"base": f"http://127.0.0.1:{httpd.server_address[1]}",
           "path": str(root), "world": world, "state": state,
           "grant": grant}
    httpd.shutdown()


def over(owner, op, timeout=60, **args):
    req = urllib.request.Request(
        owner["base"] + "/api/worker", method="POST",
        data=json.dumps({"corpus": owner["path"], "op": op,
                         "args": args}).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 CAPABILITY_HEADER: owner["grant"]})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _calls(owner):
    w = owner["world"]
    turn = w["cv"].turns(w["design"])[0]["turn"]
    return [("orient", {}), ("resolve", {"ref": turn}), ("history", {}),
            ("find", {"q": "a", "limit": 20}), ("kinds", {}),
            ("check_rendering", {"text": "```checklist version=1\n- [ ] a\n```"}),
            ("governed", {}), ("capabilities", {}),
            ("owner_decisions", {"conversation": w["design"]}),
            ("brief", {"conversation": w["design"]}),
            ("recall", {"work": "design a durable record"}),
            ("work_overview", {"conversation": w["design"]}),
            ("sources", {})]


class _HeldWrite:
    """Another thread's write transaction, open until `release`. `append`, if
    given, is called with the server's `cv` inside it, and what it appends is
    not committed until then."""

    def __init__(self, owner, append=None):
        self.owner, self.append = owner, append
        self.opened, self.done = threading.Event(), threading.Event()
        self.released = threading.Event()
        self.written, self.error = None, None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        st = self.owner["state"]
        try:
            with st.corpus._store.write():
                if self.append:
                    self.written = self.append(st.cv)
                self.opened.set()
                self.released.wait(30)
        except Exception as exc:          # noqa: BLE001
            self.error = exc
        finally:
            self.opened.set()
            self.done.set()

    def __enter__(self):
        self.thread.start()
        assert self.opened.wait(10)
        assert self.error is None, self.error
        return self

    def __exit__(self, *exc):
        self.released.set()
        self.thread.join(30)
        assert self.error is None, self.error


def _same(answer):
    """An answer without what says WHEN or HOW it was read, not what."""
    return {k: v for k, v in answer.items()
            if k not in ("cache", "as_read_at")}


def _answered_within(fn, seconds):
    """`fn()`'s answer if it came within `seconds`, else None."""
    got = {}
    t = threading.Thread(target=lambda: got.setdefault("v", fn()), daemon=True)
    t.start()
    t.join(seconds)
    return got.get("v")


# -- which operations ---------------------------------------------------------

def test_the_list_is_reads_only():
    """Named one by one, every name a read the door answers by `_result`;
    `read_artifact`, which records a supply, is not among them."""
    assert len(set(READ_ONLY)) == len(READ_ONLY)
    assert set(READ_ONLY) <= set(READS + SOURCE_READS)
    assert "read_artifact" not in READ_ONLY
    assert not set(READ_ONLY) & {o for o in permitted("organising")
                                 if o not in READS + SOURCE_READS}


def test_every_listed_read_is_answered_beside_the_writer(owner, monkeypatch):
    seen = []
    real = worker._result

    def spy(surface, name, args, **kw):
        seen.append((name, _reading_beside()))
        return real(surface, name, args, **kw)
    monkeypatch.setattr(worker, "_result", spy)
    for op, args in _calls(owner):
        over(owner, op, **args)
    assert {n for n, _ in seen} == {op for op, _ in _calls(owner)}
    assert all(beside for _, beside in seen), seen


def test_an_operation_not_listed_reads_as_before(owner, monkeypatch):
    """`_operate` answers acts and writes: never beside the writer."""
    seen = []
    real = worker._operate

    def spy(surface, name, args, grant):
        seen.append(_reading_beside())
        return real(surface, name, args, grant)
    monkeypatch.setattr(worker, "_operate", spy)
    # this grant carries no request, so the act is refused -- after
    # `_operate` is entered, which is all this asks about
    with pytest.raises(urllib.error.HTTPError):
        over(owner, "record_discovered_work", work="beside test finding")
    assert seen == [False]


# -- not waiting --------------------------------------------------------------

def test_a_read_answers_while_another_thread_holds_a_write(owner):
    """The transaction holds the store's lock for its whole length; a read
    under that lock would wait for it. Every listed read answers anyway, with
    what it answers once the transaction has ended (nothing was appended)."""
    during = {}
    with _HeldWrite(owner) as held:
        for op, args in _calls(owner):
            got = _answered_within(lambda: over(owner, op, timeout=20, **args),
                                   15)
            assert got is not None, f"{op} waited for the open transaction"
            during[op] = got
        assert not held.done.is_set()
    for op, args in _calls(owner):
        assert _same(over(owner, op, **args)) == _same(during[op]), op


def test_a_listed_read_does_not_see_rows_not_yet_committed(owner):
    """And once they are, the next read does. `orient` is cached under a
    token over `participants`, which the Participant's append moves before
    its COMMIT: a value read beside the open transaction must not be kept
    under it, or the read after the commit is served the count without it."""
    w = owner["world"]
    before = over(owner, "orient")["participants"]
    with _HeldWrite(owner, append=lambda cv: cv.create_participant(
            "Heldwrite", about="appended inside a held transaction")) as held:
        got = _answered_within(lambda: over(owner, "orient", timeout=20), 15)
        assert got is not None, "orient waited for the open transaction"
        assert got["participants"] == before
        assert over(owner, "resolve", ref=held.written)["known"] is False
    assert over(owner, "orient")["participants"] == before + 1
    assert over(owner, "resolve", ref=held.written)["known"] is True
    # and a Turn appended the same way is found once it is committed
    with _HeldWrite(owner, append=lambda cv: cv.say(
            w["design"], w["who"]["@brian"],
            [text("held write marker")])) as held:
        assert held.written not in json.dumps(
            over(owner, "find", q="held write marker", limit=10))
    assert held.written in json.dumps(
        over(owner, "find", q="held write marker", limit=10))


# -- a listed read that writes ------------------------------------------------

@pytest.mark.parametrize("swallow", [False, True])
def test_a_listed_read_that_writes_is_answered_again_outside(
        owner, monkeypatch, swallow):
    """Refused before it takes the lock, then the whole call is answered
    again under the lock, and that answer is the one returned -- even when
    the read caught the refusal itself."""
    from mentis.spine.store import WriteWhileReadingBeside
    seen = []
    real = worker._result

    def writes(surface, name, args, **kw):
        seen.append(_reading_beside())
        try:
            with surface.corpus._store.write():
                pass
        except WriteWhileReadingBeside:
            if not swallow:
                raise
        out = real(surface, name, args, **kw)
        return {**out, "beside": _reading_beside()}
    monkeypatch.setattr(worker, "_result", writes)
    got = over(owner, "kinds")
    assert seen == [True, False]
    assert got["beside"] is False
    monkeypatch.setattr(worker, "_result", real)
    plain = over(owner, "kinds")
    got.pop("beside")
    assert _same(got) == _same(plain)
