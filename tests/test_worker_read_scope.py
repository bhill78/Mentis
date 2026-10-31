"""An agent's read gets the same one-read scope a web GET already gets.

WHY. A web GET is answered inside `Conversations.reading()`, so a question asked
several times in one read -- a Conversation's Turns, a participant's deliveries
-- is computed once. An agent asks through `/api/worker`, a POST, and was
answered outside any scope, so the same `find` recomputed every Turn list it
touched. Measured on a copy of the real Brain: with five agents working, `find`
took 1.28 s at the median without the scope and 0.66 s with it.

What is asserted is what must not change, and the one thing that should:

  * THE READS, AND ONLY THE READS. `orient`, `resolve`, `history`, `find`,
    `kinds` are answered in a scope; the source reads and every act are not.
  * THE SAME ANSWERS, with the scope and without it.
  * NOTHING WRITTEN by a read, and nothing kept after it -- the scope is the
    request's, exactly as for GET.
  * THE WORK IS DONE ONCE, counted at the store rather than timed.
  * WRITES STAY VISIBLE under concurrency: a write landing while a read is in
    flight ends that read's answers, the next read sees it, and readers racing
    writers never see the record go backwards.
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
from mentis.web import _Handler, _State, _surface, fixture
from mentis.worker import CAPABILITY_HEADER, READS, _result, permitted


@pytest.fixture(scope="module")
def owner(tmp_path_factory):
    root = tmp_path_factory.mktemp("scope") / "corpus"
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


def over(owner, op, **args):
    req = urllib.request.Request(
        owner["base"] + "/api/worker", method="POST",
        data=json.dumps({"corpus": owner["path"], "op": op,
                         "args": args}).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 CAPABILITY_HEADER: owner["grant"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _a_turn(owner):
    w = owner["world"]
    return w["cv"].turns(w["design"])[0]["turn"]


def _calls(owner):
    """Every read, with arguments that make it do real work."""
    return [("orient", {}), ("resolve", {"ref": _a_turn(owner)}),
            ("history", {}), ("history", {"conversation":
                                          owner["world"]["design"]}),
            ("find", {"q": "a", "limit": 20}), ("kinds", {}),
            ("check_rendering", {"text": "```checklist version=1\n- [ ] a\n```"}),
            ("governed", {}), ("capabilities", {}),
            ("owner_decisions", {"conversation": owner["world"]["design"]}),
            ("brief", {"conversation": owner["world"]["design"]}),
            ("recall", {"work": "design a durable record"}),
            ("work_overview", {"conversation": owner["world"]["design"]})]


@pytest.fixture()
def seen_scope(monkeypatch):
    """Whether each `_result` ran inside an open reading scope."""
    seen = []
    real = worker._result

    def spy(surface, name, args, **kw):
        seen.append((name, getattr(surface.cv._scope, "frame", None)
                     is not None))
        return real(surface, name, args, **kw)
    monkeypatch.setattr(worker, "_result", spy)
    return seen


# -- which operations ---------------------------------------------------------

def test_every_read_is_answered_inside_a_scope(owner, seen_scope):
    for op, args in _calls(owner):
        over(owner, op, **args)
    assert {op for op, _ in seen_scope} == set(READS)
    assert all(scoped for _, scoped in seen_scope), seen_scope


def test_a_source_read_is_not_put_in_one(owner, seen_scope):
    over(owner, "sources")
    assert seen_scope == [("sources", False)]


def test_an_act_is_not_put_in_one(owner, monkeypatch):
    """Acts go to `_operate`, which writes; a scope must never span a write."""
    seen = []
    real = worker._operate

    def spy(surface, name, args, grant):
        seen.append(getattr(surface.cv._scope, "frame", None) is not None)
        return real(surface, name, args, grant)
    monkeypatch.setattr(worker, "_operate", spy)
    # This grant carries no request, so the act itself is refused -- after
    # `_operate` is entered, which is all this asks about.
    with pytest.raises(urllib.error.HTTPError):
        over(owner, "record_discovered_work", work="scope test finding")
    assert seen == [False]


def test_the_scope_ends_with_the_read(owner):
    """Nothing kept: the Surface is shared, its scope is not."""
    over(owner, "find", q="a")
    cv = _surface(owner["state"]).cv
    assert getattr(cv._scope, "frame", None) is None


# -- what the reads say -------------------------------------------------------

def test_the_answers_are_the_ones_an_unscoped_read_gives(owner):
    """`orient` reports what the caller may do from `surface.permits`, which
    the route sets from the grant on the one shared Surface. The direct read
    sets it the same way, so it compares with this grant's answer and not with
    whatever an earlier request left there."""
    state = owner["state"]
    surface = _surface(state)
    grant = state.agents.authority.grant_for(owner["grant"], state.path)
    for op, args in _calls(owner):
        assert getattr(surface.cv._scope, "frame", None) is None
        surface.permits = permitted(grant.get("scope"),
                                    grant.get("operations"))
        direct = json.loads(json.dumps(_result(surface, op, args),
                                       default=str))
        assert over(owner, op, **args) == direct, op


def test_a_read_writes_nothing(owner):
    store = owner["state"].corpus._store
    before = store.writes
    for op, args in _calls(owner):
        over(owner, op, **args)
    assert store.writes == before


def test_the_work_a_read_repeats_is_done_once(owner, monkeypatch):
    """Counted at the store. `find` over Turns in one Conversation asks for
    that Conversation's Turns once per hit; inside the scope, once."""
    w = owner["world"]
    for i in range(4):
        w["cv"].say(w["design"], w["who"]["@brian"],
                    [text(f"scopecount marker {i}")])
    store = owner["state"].corpus._store
    reads = []
    real = type(store)._entries

    def counted(self, *a, **kw):
        reads.append(1)
        return real(self, *a, **kw)
    monkeypatch.setattr(type(store), "_entries", counted)
    surface = _surface(owner["state"])
    plain = json.loads(json.dumps(
        _result(surface, "find", {"q": "scopecount", "limit": 20}),
        default=str))
    unscoped = len(reads)
    reads.clear()
    scoped = over(owner, "find", q="scopecount", limit=20)
    assert scoped == plain
    assert scoped["matched"] >= 4
    assert len(reads) < unscoped, (len(reads), unscoped)


# -- writes, while reads are in flight ---------------------------------------

def test_a_write_during_a_read_ends_its_answers_and_the_next_read_sees_it(
        owner, monkeypatch):
    """Another thread writes while a scoped `find` is part-way through. The
    rest of that read sees the write -- the memo it had already taken is
    dropped, by the scope's own rule -- and so does the next read.

    WRITTEN THROUGH THE SERVER'S OWN `cv`, which shares the Store, and so the
    write count, the scope reads. The fixture's `cv` opens a Store of its own
    whose writes this process's count never sees."""
    w = owner["world"]
    writer_cv = owner["state"].cv
    cv = _surface(owner["state"]).cv
    real = type(cv)._contributions
    seen = {"written": None}

    def mid_read(self, conversation):
        if seen["written"] is None and self is cv:
            seen["written"] = "pending"
            frame = cv._scope.frame
            assert frame is not None
            before = [e["id"] for e in cv.contributions(w["research"])]

            def write():
                seen["written"] = writer_cv.say(
                    w["research"], w["who"]["@brian"],
                    [text("midread marker")])
            t = threading.Thread(target=write)
            t.start()
            t.join()
            after = [e["id"] for e in cv.contributions(w["research"])]
            seen["same_scope"] = cv._scope.frame is frame
            seen["before"], seen["after"] = before, after
        return real(self, conversation)
    monkeypatch.setattr(type(cv), "_contributions", mid_read)
    # Answers are shared between reads of one unmoved record, so an earlier
    # test's would be reused and the read below would compute nothing: start
    # it with none kept, so it reads -- and meets the write -- for itself.
    cv._shared.update(memo={}, snapshots={}, writes=None)
    over(owner, "find", q="a", limit=50)
    monkeypatch.setattr(type(cv), "_contributions", real)
    assert seen["same_scope"]
    assert seen["written"] not in seen["before"]
    assert seen["written"] in seen["after"]
    found = over(owner, "find", q="midread", limit=10)
    assert seen["written"] in json.dumps(found)
    assert over(owner, "resolve", ref=seen["written"])


def test_readers_racing_writers_never_see_the_record_go_backwards(owner):
    """Six agents reading while three write, through the server's own `cv`.
    Each count is its own request and so its own scope: this shows that no
    answer outlives its read -- a reader's count of the marker only grows,
    nothing errors, and the end state is all of it. Clearing WITHIN one read
    is the test above."""
    w = owner["world"]
    convs = [w["design"], w["research"], w["tavern"]]
    per_writer, errors = 12, []
    done = threading.Event()
    counts: dict[int, list[int]] = {i: [] for i in range(6)}

    def writer(j):
        try:
            for i in range(per_writer):
                owner["state"].cv.say(convs[j], w["who"]["@brian"],
                                      [text(f"racemarker w{j} n{i}")])
        except Exception as exc:          # noqa: BLE001
            errors.append(f"writer {j}: {exc!r}")

    def reader(i):
        try:
            while not done.is_set():
                op = ("find", "history", "kinds", "orient")[len(counts[i]) % 4]
                if op == "find":
                    counts[i].append(over(owner, "find", q="racemarker",
                                          limit=100)["matched"])
                else:
                    over(owner, op)
                    counts[i].append(counts[i][-1] if counts[i] else 0)
        except Exception as exc:          # noqa: BLE001
            errors.append(f"reader {i}: {exc!r}")

    readers = [threading.Thread(target=reader, args=(i,)) for i in range(6)]
    writers = [threading.Thread(target=writer, args=(j,)) for j in range(3)]
    for t in readers + writers:
        t.start()
    for t in writers:
        t.join()
    done.set()
    for t in readers:
        t.join()
    assert errors == []
    for i, seq in counts.items():
        assert seq == sorted(seq), (i, seq)
    assert over(owner, "find", q="racemarker",
                limit=100)["matched"] == 3 * per_writer
