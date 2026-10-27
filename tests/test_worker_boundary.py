"""The boundary a worker asks across, when it may not open the corpus at all.

WHAT IS BEING PROTECTED. A dispatched worker used to answer questions about
the record by opening the record. A sandboxed one cannot -- the spine is WAL
and SQLite writes beside a WAL database before it will read one -- and the
answer to that must not be to give the worker write access to the corpus.
So the worker sends the question instead, and the process that already owns
the corpus performs it.

The invariant these tests exist for: WORKER FILESYSTEM PERMISSIONS MUST NOT
DETERMINE CORPUS PERMISSIONS. Everything below is about the boundary being
narrow, being read-only, refusing a corpus it does not own, and failing out
loud rather than quietly reading from disk.
"""

from __future__ import annotations
import os

import io
import json
import threading
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer

import pytest

from mentis.execution import RunResult
from mentis.web import _Handler, _State, fixture
from mentis.worker import (CAPABILITY_HEADER, NoOwner, TOOLS, _parse,
                           _result, ask)


@pytest.fixture(scope="module")
def owner(tmp_path_factory):
    """A Mentis that owns a corpus and answers questions about it."""
    root = tmp_path_factory.mktemp("boundary") / "corpus"
    world = fixture.build(str(root))
    state = _State(str(root))
    handler = type("H", (_Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    # The grant an execution is dispatched with, minted the same way
    # `register` mints one.
    grant = state.agents.authority._grant("exec-under-test", state.path)
    yield {"base": f"http://127.0.0.1:{httpd.server_address[1]}",
           "path": str(root), "world": world, "state": state,
           "grant": grant}
    httpd.shutdown()


def over(owner, op, grant=..., corpus=None, **args):
    body = json.dumps({"corpus": corpus or owner["path"], "op": op,
                       "args": args})
    head = {"Content-Type": "application/json"}
    grant = owner["grant"] if grant is ... else grant
    if grant is not None:
        head[CAPABILITY_HEADER] = grant
    req = urllib.request.Request(
        owner["base"] + "/api/worker", method="POST",
        data=body.encode("utf-8"), headers=head)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def run(record, argv, via, capability=None):
    """The launcher's own entry point, with its JSON captured."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = ask(record, argv, via=via, capability=capability)
    return code, json.loads(buf.getvalue())


# -- the boundary answers, and answers the same thing -----------------------

def test_the_four_operations_cross_the_boundary(owner):
    assert over(owner, "orient")["corpus_id"]
    assert over(owner, "find", q="a")["matched"] >= 0
    assert "found" in over(owner, "find", q="a")
    assert over(owner, "history")["acts"] is not None


def test_the_answer_is_the_same_one_the_surface_gives(owner):
    """Same semantics, not merely a working wire.

    The far side must be the SAME `Surface` and the SAME `_result` the MCP
    server and the composer use. If this ever diverges, two implementations
    are deciding what exists and they will disagree.
    """
    from mentis.web import _surface
    direct = _result(_surface(owner["state"]), "orient", {})
    assert over(owner, "orient") == direct


def test_a_real_reference_resolves_across_it(owner):
    """A discriminating reference: content that is only in the record."""
    cv = owner["state"].cv
    cid = cv.all_conversations()[0]["id"]
    tid = cv.contributions(cid)[0]["id"]
    got = over(owner, "resolve", ref=tid)
    assert got["known"] is True
    assert got["conversation"] == cid
    assert got["number"] == cv.turn_number(tid)


# -- nothing but the reads ---------------------------------------------------

def test_the_boundary_exposes_exactly_the_reads(owner):
    # The source reads joined deliberately: the owner chose them as a default
    # agent capability (Bulk Source / Repository Onboarding, Turn 19), and
    # `search_sources` with Sources A ("Yes, A after B"). They write
    # nothing, which the test below holds them to.
    assert {t["name"] for t in TOOLS} == {"orient", "find", "resolve",
                                          "history", "kinds", "sources",
                                          "source_history", "source_links",
                                          "read_source", "search_sources",
                                          # the render check's dry run reads
                                          # nothing of the record and writes
                                          # nothing (Markdown Renderer Maturation)
                                          "check_rendering",
                                          # reads of what the owner's UI and a
                                          # dispatch brief already read
                                          # (agent access through the bridge)
                                          "governed", "owner_decisions",
                                          "capabilities", "brief"}
    for denied in ("say", "post", "write", "record_turn", "reply", ""):
        with pytest.raises(urllib.error.HTTPError):
            over(owner, denied)


def test_the_boundary_takes_no_path(owner):
    """An operation and its arguments, never a location.

    `_result` reads its arguments as references and text. There is no
    parameter through which a caller could name a file, so a worker cannot
    steer this at anything but the corpus the owner already holds.
    """
    got = over(owner, "resolve", ref=owner["path"])
    assert got["known"] is False


def test_it_refuses_a_corpus_it_does_not_own(owner):
    """Silently answering about a DIFFERENT record is the failure mode that
    `workers_read` exists to prevent, so it is refused rather than served."""
    body = json.dumps({"corpus": r"C:\somewhere\else", "op": "orient",
                       "args": {}})
    req = urllib.request.Request(
        owner["base"] + "/api/worker", method="POST",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json",
                 CAPABILITY_HEADER: owner["grant"]})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert "does not own that corpus" in exc.value.read().decode()


def test_writes_are_not_reachable_through_it(owner):
    """The route can express no act. Every write the server has lives behind
    a different path, and this one dispatches four names."""
    before = len(owner["state"].corpus.operational())
    for op in ("orient", "find", "resolve", "history", "kinds", "sources",
               "source_history", "source_links", "read_source",
               "search_sources", "check_rendering"):
        try:
            over(owner, op, ref="ent-000000000000", q="x")
        except urllib.error.HTTPError:
            pass
    assert len(owner["state"].corpus.operational()) == before


# -- the launcher's own path ------------------------------------------------

def test_the_launcher_asks_across_the_boundary(owner):
    code, got = run(owner["path"], ["orient"], via=owner["base"],
                    capability=owner["grant"])
    assert code == 0
    assert got["corpus_id"] == over(owner, "orient")["corpus_id"]


def test_one_grammar_for_both_wires(owner):
    """The command line is parsed in one place, so the two ways of reaching
    Mentis cannot drift into understanding different commands."""
    assert _parse(["resolve", "ent-abc"]) == ("resolve", {"ref": "ent-abc"})
    assert _parse(["find", "two", "words"]) == ("find", {"q": "two words"})


# -- and when nobody owns it ------------------------------------------------

def test_no_owner_fails_explicitly_and_reads_nothing(owner, monkeypatch):
    """THE FALLBACK THAT MUST NOT EXIST.

    With no Mentis listening, the honest answer is "I could not ask". The
    dangerous answer is the corpus on disk. This asserts the first and, by
    forbidding `Surface` entirely, that the second was not reached -- "could
    not ask" stays distinct from "unknown" and from "empty".
    """
    import mentis.worker as worker

    def forbidden(*a, **k):
        raise AssertionError("fell back to opening the corpus directly")

    monkeypatch.setattr(worker, "Surface", forbidden)
    # A port with nothing behind it, on the same loopback interface.
    code, got = run(owner["path"], ["orient"], via="http://127.0.0.1:9")
    assert code == 3
    assert got["error"] == "no Mentis owner for this record"
    assert "no Mentis is answering" in got["why_not"]
    assert got["asked"] == "orient"


def test_no_owner_is_not_an_empty_record(owner, monkeypatch):
    import mentis.worker as worker
    monkeypatch.setattr(worker, "Surface", lambda *a, **k: None)
    code, got = run(owner["path"], ["find", "anything"],
                    via="http://127.0.0.1:9")
    assert code == 3
    assert "found" not in got and "matched" not in got


def test_a_worker_with_no_owner_is_offered_no_capability(tmp_path):
    """A run is handed the Mentis server only when something can answer:
    with no record attached there is no grant and no server in its RunSpec."""
    from mentis.core.service import MentisService
    from mentis.execution import FakeExecution
    svc = MentisService(str(tmp_path / "instances"), execution=FakeExecution())
    assert svc.mcp_servers_for("any-run", str(tmp_path)) == ()


def test_the_owner_states_where_it_answers(tmp_path):
    """The address comes from the process that opened the corpus, not from
    anything the worker supplies."""
    root = tmp_path / "corpus"
    fixture.build(str(root))
    st = _State(str(root), answers_at="http://127.0.0.1:1234")
    assert st.agents._answers_at == "http://127.0.0.1:1234"
    assert st.agents._record == st.path


def test_no_owner_raises_its_own_exception(owner):
    from mentis.worker import _over
    with pytest.raises(NoOwner):
        _over("http://127.0.0.1:9", owner["path"], "orient", {})



# -- what the grant is, and what it is not ----------------------------------

def write_with(owner, path, payload, grant):
    """Attempt an ordinary write, presenting a worker grant."""
    req = urllib.request.Request(
        owner["base"] + path, method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 CAPABILITY_HEADER: grant})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    return exc.value


def test_the_grant_buys_nothing_on_any_write_route(owner):
    """THE ACCEPTANCE THIS EXISTS FOR.

    One grant, every write the server has. None of them may be reached with
    it -- not a Conversation, not a Topic, not a Turn, not a late addressing
    and not an expectation.
    """
    cid = owner["state"].cv.all_conversations()[0]["id"]
    attempts = [
        ("/api/conversations", {"name": "smuggled"}),
        (f"/api/conversations/{cid}/topics", {"name": "smuggled"}),
        (f"/api/conversations/{cid}/turns", {"text": "smuggled"}),
        (f"/api/conversations/{cid}/participants", {"alias": "@smuggled"}),
        (f"/api/conversations/{cid}/address", {"turn": "x"}),
        (f"/api/conversations/{cid}/expect", {"turn": "x"}),
    ]
    before = len(owner["state"].cv.all_conversations())
    for path, payload in attempts:
        err = write_with(owner, path, payload, owner["grant"])
        assert err.code == 403, path
        assert "nothing else" in err.read().decode()
    assert len(owner["state"].cv.all_conversations()) == before


def test_the_grant_buys_nothing_on_reads_either(owner):
    """Not "writes are special" -- the grant is good at one route.

    A list of routes to protect is a list somebody forgets to add to, so the
    rule is the other way round: everything refuses a grant except the one
    route that accepts one.
    """
    for path in ("/api/brain", "/api/participants", "/api/references?q=a",
                 "/api/activity", "/api/capacity"):
        req = urllib.request.Request(
            owner["base"] + path,
            headers={CAPABILITY_HEADER: owner["grant"]})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 403, path


def test_the_four_reads_need_a_grant(owner):
    """Reaching the port is not permission to ask through it."""
    for bad in (None, "", "not-a-grant", owner["grant"][:-1] + "x"):
        with pytest.raises(urllib.error.HTTPError) as exc:
            over(owner, "orient", grant=bad)
        assert exc.value.code == 403


def test_a_grant_is_scoped_to_one_corpus(owner, tmp_path):
    """Changing the scope is rejected, from either direction."""
    other = tmp_path / "elsewhere"
    fixture.build(str(other))
    # Asking this owner about a record it does not hold.
    with pytest.raises(urllib.error.HTTPError) as exc:
        over(owner, "orient", corpus=str(other))
    assert exc.value.code in (400, 403)
    # And a grant minted for that other record is not good here.
    foreign = owner["state"].agents.authority._grant("other-exec",
                                                       str(other))
    with pytest.raises(urllib.error.HTTPError) as exc:
        over(owner, "orient", grant=foreign)
    assert exc.value.code == 403


def test_another_execution_cannot_reuse_a_grant(owner):
    """Each execution asks with its own, and one ending does not end another.

    What is honestly established here is that grants are per-execution and
    separately revocable. It is NOT a proof of who is calling: presenting the
    grant is the whole claim, so a grant that leaked while its execution was
    live would work. Binding it to a caller would need something to identify
    callers with, which is the subsystem this is deliberately not.
    """
    f = owner["state"].agents.authority
    mine, theirs = owner["grant"], f._grant("another-exec", owner["path"])
    assert mine != theirs
    assert f.authorises(mine, owner["path"]) == "exec-under-test"
    assert f.authorises(theirs, owner["path"]) == "another-exec"
    # Ending one execution does not disturb the other.
    f._grants.pop(theirs)
    f._granted_to.pop("another-exec")
    assert f.authorises(theirs, owner["path"]) is None
    assert over(owner, "orient")["corpus_id"]


def test_a_grant_lives_as_long_as_its_execution(owner):
    """LIFETIME IS AN OBSERVED FACT, NOT A CLOCK.

    No expiry is chosen, because none could be chosen honestly: a resumed
    execution may legitimately be asking hours later, and Mark IV cannot
    observe when a detached worker stops. What it CAN observe is the
    instance being released, so that is the end the grant is bound to.
    """
    f = owner["state"].agents.authority
    token = f._grant("long-running", owner["path"])
    assert f.authorises(token, owner["path"]) == "long-running"
    # Many asks, across what would be many `perform` calls on a resume.
    for _ in range(5):
        assert f.authorises(token, owner["path"]) == "long-running"
    assert f.grant_of("long-running") == token
    f._grants.pop(token)
    f._granted_to.pop("long-running")
    assert f.authorises(token, owner["path"]) is None


def test_a_grant_lasts_exactly_as_long_as_the_run(tmp_path):
    """The tightest honest lifetime: the work it authorises.

    It used to be minted when an instance was registered and revoked
    only at release -- which release nothing performed -- so an instance
    kept dormant for reuse carried a usable worker capability with
    nothing running to use it. A run's own end needs no timeout.
    """
    seen = {}

    def watching(spec):
        # What the worker would actually be handed, mid-run.
        seen["capability"] = svc.authority.grant_of(spec.run_id)
        seen["authorises"] = svc.authority.authorises(seen["capability"],
                                                      str(tmp_path))
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn", text="done")

    svc, inst = _summoned(tmp_path, {"codex": watching})
    i1 = inst.instance_id

    # Nothing is authorised before there is work to authorise.
    assert svc.authority.grant_of(i1) is None
    svc.agents_perform(i1, "work")
    # It was usable inside the run...
    assert seen["capability"]
    assert seen["authorises"] == i1
    # ...and is not afterwards, with the instance still dormant and
    # perfectly reusable.
    assert svc.authority.grant_of(i1) is None


def _summoned(tmp_path, script, *, via=None, scope=None):
    """A service over `tmp_path` as the record, with a FakeExecution running
    `script`, and one instance summoned on codex (authorised as `scope`)."""
    from mentis.api.types import Address, Selection
    from mentis.core.service import MentisService
    from mentis.execution import FakeExecution
    svc = MentisService(str(tmp_path / "instances"),
                        execution=FakeExecution(script=script))
    svc.workers_read(str(tmp_path), answers_at=via)
    inst = svc.agents_summon(Address("Ada"), Selection("codex", None, None, ()),
                             workspace=str(tmp_path))
    if scope:
        svc.authority.authorise_for(inst.instance_id, {"scope": scope})
    return svc, inst
    assert f.authorises(seen["capability"], str(tmp_path)) is None
    assert f.known("i1") is not None


# -- one boundary for all four reads, whatever the transport -----------------

def _rpc(server_in, requests):
    """Drive the MCP server over its own stdio protocol and collect replies."""
    import io as _io
    import json as _json
    import sys as _sys
    from mentis import worker as W

    out = _io.StringIO()
    old_in, old_out = _sys.stdin, _sys.stdout
    _sys.stdin = _io.StringIO("\n".join(_json.dumps(r) for r in requests) + "\n")
    _sys.stdout = out
    try:
        W.serve(*server_in[0], **server_in[1])
    finally:
        _sys.stdin, _sys.stdout = old_in, old_out
    return [_json.loads(l) for l in out.getvalue().splitlines() if l.strip()]


def test_the_mcp_transport_asks_the_owner_and_opens_no_corpus(monkeypatch,
                                                              tmp_path):
    """THE ASYMMETRY THIS CLOSES. Two runtimes were served by an MCP server
    that constructed a `Surface` in the WORKER process -- opening corpus.db
    there -- while the Codex transport went through `/api/worker` under an
    invocation-scoped grant. Same four operations, two capability boundaries,
    and for two of them a worker's filesystem permissions decided corpus
    permissions. Proved here by making any corpus handle in this process fatal.
    """
    from mentis import worker as W

    def never(*a, **kw):
        raise AssertionError("the worker opened the corpus itself")

    monkeypatch.setattr(W, "Surface", never)
    asked = []

    def fake_over(via, record, name, args, capability=None):
        asked.append((via, record, name, args, capability))
        return {"ok": name}

    monkeypatch.setattr(W, "_over", fake_over)
    replies = _rpc(((str(tmp_path / "corpus"),),
                    {"via": "http://127.0.0.1:9", "capability": "cap-1"}),
                   [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "orient", "arguments": {}}}])
    assert replies[0]["result"]["content"][0]["text"].strip().startswith("{")
    assert len(asked) == 1
    via, record, name, args, cap = asked[0]
    assert (via, name, cap) == ("http://127.0.0.1:9", "orient", "cap-1")
    assert record == str(tmp_path / "corpus"), "the corpus asked about is named"


def test_all_reads_go_the_same_way_and_nothing_else_does(monkeypatch,
                                                             tmp_path):
    from mentis import worker as W
    monkeypatch.setattr(W, "Surface",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            AssertionError("opened the corpus")))
    seen = []
    monkeypatch.setattr(W, "_over",
                        lambda via, rec, name, args, cap=None: seen.append(name)
                        or {"ok": name})
    reqs = [{"jsonrpc": "2.0", "id": i, "method": "tools/call",
             "params": {"name": n, "arguments": {}}}
            for i, n in enumerate(W.READS)]
    _rpc(((str(tmp_path / "corpus"),),
          {"via": "http://127.0.0.1:9", "capability": "cap-1"}), reqs)
    assert seen == list(W.READS)

    # EVERY OPERATION LEAVES BY THE SAME DOOR, and none of them opens the
    # corpus. What changed when organising was added is the SIZE of the offered
    # set, never the boundary -- so what this test protects is that nothing on
    # it is served locally, whatever it is called.
    #
    # `return_artifact` is the one operation that READS SOMETHING ON THIS SIDE
    # first -- a file in the worker's own directory, never the corpus -- so it
    # is given a file to read. What leaves is still one question to the owner.
    seen.clear()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "made.txt").write_text("made here", encoding="utf-8")
    given = {"return_artifact": {"path": "made.txt"}}
    _rpc(((str(tmp_path / "corpus"),),
          {"via": "http://127.0.0.1:9", "capability": "cap-1"}),
         [{"jsonrpc": "2.0", "id": i, "method": "tools/call",
           "params": {"name": n, "arguments": given.get(n, {})}}
          for i, n in enumerate(W.ORGANISES + W.ASKS)])
    assert seen == list(W.ORGANISES + W.ASKS), (
        "an operation was answered somewhere other than at the owner"
    )

    # A RETURN WITH NOTHING TO READ IS REFUSED BEFORE IT CROSSES, on this side,
    # and still opens no corpus: the Surface above would have raised.
    seen.clear()
    refused = _rpc(((str(tmp_path / "corpus"),),
                    {"via": "http://127.0.0.1:9", "capability": "cap-1"}),
                   [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "return_artifact",
                                "arguments": {"path": "../outside.txt"}}}])
    assert seen == []
    assert refused[0]["result"]["isError"] is True
    assert "outside this worker's directory" in (
        refused[0]["result"]["content"][0]["text"])

    # WHAT IS OFFERED IS THIS RUN'S OWN SET, and a bounded run that was told
    # nothing gets the reads. FAILING CLOSED IS THE POINT: a missing or
    # unreadable scope must not be the permissive case.
    listed = _rpc(((str(tmp_path / "corpus"),), {"via": "http://x",
                                                 "capability": "c"}),
                  [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    assert sorted(t["name"] for t in listed[0]["result"]["tools"]) == sorted(
        W.READS)

    # Told what it may do, it offers exactly that -- no more, and no less.
    listed = _rpc(((str(tmp_path / "corpus"),),
                   {"via": "http://x", "capability": "c",
                    "permits": W.OPERATIONS}),
                  [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    assert sorted(t["name"] for t in listed[0]["result"]["tools"]) == sorted(
        W.OPERATIONS)

    # And a name nothing implements cannot conjure a tool by being permitted.
    listed = _rpc(((str(tmp_path / "corpus"),),
                   {"via": "http://x", "capability": "c",
                    "permits": ("orient", "establish", "write_anything")}),
                  [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    assert [t["name"] for t in listed[0]["result"]["tools"]] == ["orient"]

    # IN-PROCESS THERE IS NO GRANT, so no operation could ever be admitted and
    # only the reads are advertised. Offering one here would advertise a tool
    # that cannot work. The source reads are reads too: they are their own set
    # because a Scratch answer's holding them was decided apart (it now does,
    # opr-9fa00d2183a9), and this path is not a Scratch answer.
    # D2: a worker that holds the record itself refuses to start on a missing
    # Brain, so this in-process path is given a real one (made explicitly).
    from tests._brains import new_brain
    listed = _rpc(((new_brain(tmp_path / "corpus"),), {}),
                  [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    assert sorted(t["name"] for t in listed[0]["result"]["tools"]) == sorted(
        W.READS + W.SOURCE_READS)


def test_a_refusal_from_the_owner_is_reported_not_worked_around(monkeypatch,
                                                                tmp_path):
    """Wrong corpus, wrong scope, missing grant -- all the owner's answer, and
    NONE of them fall back to reading the record on disk."""
    from mentis import worker as W
    monkeypatch.setattr(W, "Surface",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            AssertionError("fell back to the corpus")))

    def refuse(*a, **kw):
        raise W.NoOwner("that grant is not for this corpus")

    monkeypatch.setattr(W, "_over", refuse)
    replies = _rpc(((str(tmp_path / "corpus"),),
                    {"via": "http://127.0.0.1:9", "capability": "wrong"}),
                   [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "orient", "arguments": {}}}])
    res = replies[0]["result"]
    assert res.get("isError") is True
    assert "not for this corpus" in res["content"][0]["text"]


def test_the_direct_path_remains_only_for_a_caller_that_holds_the_record(
        tmp_path):
    """Unbounded `serve` still exists for the CLI and tests. What matters is
    that a dispatched worker is never handed it -- see the adapter test below."""
    from mentis.web import fixture
    root = str(tmp_path / "corpus")
    fixture.build(root)
    replies = _rpc(((root,), {}),
                   [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "orient", "arguments": {}}}])
    assert "corpus_id" in replies[0]["result"]["content"][0]["text"]


def _spec_of_one_run(tmp_path, *, via="http://127.0.0.1:8123", scope=None):
    """The RunSpec one run is handed, and the grant it held while running."""
    seen = {}

    def capture(spec):
        seen["spec"] = spec
        seen["grant"] = svc.authority.grant_of(spec.run_id)
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn", text="done")

    svc, inst = _summoned(tmp_path, {"codex": capture}, via=via, scope=scope)
    svc.agents_perform(inst.instance_id, "work")
    return seen["spec"], seen["grant"]


def test_every_run_is_handed_the_bounded_boundary(tmp_path):
    """NO DIRECT-DISK WORKER PATH LEFT. A run's ONE MCP server, `mentis`,
    must carry `via` and the grant; a bare `serve(record)` is the asymmetry
    coming back. (Mark IV checked this per runtime adapter; there is now
    one place a run is handed it: the RunSpec given to MARS.)"""
    import sys
    via = "http://127.0.0.1:8123"
    spec, cap = _spec_of_one_run(tmp_path, via=via)
    assert [s["name"] for s in spec.mcp_servers] == ["mentis"]
    server = spec.mcp_servers[0]
    assert server["command"] == sys.executable
    assert server["args"][:2] == ["-I", "-c"]
    boot = server["args"][-1]
    assert via in boot, "the run's server does not name the owner"
    assert cap and cap in boot, "the run's server does not carry the grant"
    assert "via=None" not in boot, "the run's server serves unbounded"
    assert "capability=None" not in boot, "the run's server has no grant"


def test_the_bridge_offers_exactly_the_read_only_tools():
    """The server a run is handed offers exactly the read-only operations
    as its plain tools; everything else is an act the door admits by grant."""
    assert sorted(t["name"] for t in TOOLS) == ["brief", "capabilities",
                                                "check_rendering",
                                                "find", "governed", "history",
                                                "kinds", "orient",
                                                "owner_decisions",
                                                "read_source",
                                                "resolve", "search_sources",
                                                "source_history",
                                                "source_links", "sources"]


# -- authority comes from the dispatch, and visibility matches it -----------
#
# WHY THESE EXIST, AND IT IS NOT A HYPOTHETICAL. Organising operations were
# added for an execution carrying an unaddressed request, and the surface
# advertised them to EVERY bounded run on the reasoning that the door refuses
# what a run may not do. Measured in real use within five minutes: an ordinary
# specialist, explicitly addressed for a small piece of work, was shown
# `delegate`, `respond` and `summon_participant`; it correctly concluded the
# surface could not be the one its working note described, declined to call any
# tool at all, and said so. Its restraint was the only thing between the
# advertisement and a call. That is not a boundary.
#
# So there are two separate invariants below, and BOTH are load-bearing:
#   1. an ordinary worker cannot SEE an organising operation;
#   2. an ordinary worker cannot USE one if it asks anyway.
# Neither is allowed to be the reason the other is not needed.


def _granted(owner, scope, **authority):
    """Mint a grant EXACTLY AS `dispatch` DOES, for an execution of that scope.

    THIS HELPER USED TO HIDE A DEFECT, and that is worth saying here rather than
    quietly fixing. It built its "worker" grant WITH a participant -- which no
    ordinary dispatch actually produced, because `authorise_for` was called only
    for intake. So `request_decision` was advertised and pre-approved to every
    ordinary run and refused 100% of the time, and these tests could not see it
    because the fixture was more generous than production. A test that mints its
    own facts differently from the code under test proves nothing about the code.

    So this mirrors `dispatch`: scope comes from the caller and everything else
    is present for every run.
    """
    fnd = owner["state"].agents.authority
    iid = f"exec-{scope or 'none'}-{len(fnd._grants)}"
    cv = owner["state"].cv
    conversation = cv.all_conversations()[0]["id"]
    who = cv.participants(conversation)[0]
    fnd.authorise_for(iid, dict(
        {"conversation": conversation, "participant": who, "runtime": "claude"},
        **({"scope": scope} if scope else {}), **authority))
    return iid, fnd._grant(iid, owner["state"].path)


def test_an_ordinary_worker_is_not_shown_organising_operations(owner):
    """VISIBILITY MATCHES AUTHORITY, which is what the real finding was about.

    Handing work on is not organising: an ordinary worker is shown `delegate`,
    so it can involve the role its work needs instead of stranding the need.
    """
    from mentis.worker import ASKS, HANDS_OFF, ORGANISES, READS
    fnd = owner["state"].agents.authority
    iid, _ = _granted(owner, "worker")
    shown = set(fnd.permits_for(iid))
    assert set(READS) <= shown, "a worker cannot even read"
    assert set(ASKS) <= shown, (
        "a worker cannot say a decision is the owner's, so it would say it in "
        "prose instead"
    )
    assert set(HANDS_OFF) <= shown, "a worker cannot hand work on"
    for op in ORGANISES:
        if op not in HANDS_OFF:
            assert op not in shown, f"an ordinary worker is shown {op!r}"


def test_the_caretaker_execution_is_shown_exactly_its_own_operations(owner):
    from mentis.worker import (ASKS, DEEP_DIVE, HANDS_OFF,
                               INTERACTS, OPERATIONS, ORGANISES, READS,
                               RESUME_INTAKE, SOURCE_READS)
    fnd = owner["state"].agents.authority
    iid, _ = _granted(owner, "intake")
    shown = set(fnd.permits_for(iid))
    assert shown == set(OPERATIONS)
    assert set(ORGANISES) <= shown
    # And it is BOUNDED: no establishment, no arbitrary write, no actor.
    assert "establish" not in shown
    for banned in ("write", "record_act", "say_as", "set_actor",
                   "establish_material", "corpus_write"):
        assert banned not in shown, f"the organising set contains {banned!r}"
    # SOURCE_READS counted separately: they are not in `READS`, because a
    # Scratch answer's holding them was decided apart (opr-9fa00d2183a9). The
    # caretaker's set is unchanged in content.
    # `delegate` is HANDS_OFF, counted on its own: it is the capability every
    # run holds, no longer listed among the organising operations.
    # `resume_intake` is derived like `deep_dive`; it is admitted only with
    # `coordinate` (`_operate`), which this hand-made grant does not record.
    # (Mark IV's server-side web tools and `arm_deploy` are gone.)
    assert len(shown) == (len(READS) + len(SOURCE_READS) + len(ASKS)
                          + len(INTERACTS) + len(HANDS_OFF)
                          + len(ORGANISES)
                          + len((DEEP_DIVE, RESUME_INTAKE)))


def test_what_a_run_is_shown_is_what_reaches_its_runtime(tmp_path):
    """The declared set travels into the launch: the `permits` in the boot
    command of the run's `mentis` server are the ones its grant admits.

    Checked on the RunSpec handed to MARS rather than asserted of the
    plumbing, because the defect was exactly a mismatch between what one
    layer decided and what another advertised.
    """
    from mentis.worker import ORGANISES, permitted

    for scope in ("worker", "intake"):
        spec, _ = _spec_of_one_run(tmp_path / scope, scope=scope)
        args = spec.mcp_servers[0]["args"][-1]
        for op in permitted(scope):
            assert f"'{op}'" in args, (
                f"{scope}: {op} never reached the query surface")
        if scope == "worker":
            for op in ORGANISES:
                if op in permitted("worker"):
                    continue
                assert f"'{op}'" not in args, (
                    f"an ordinary worker's surface was told to offer {op!r}"
                )


def test_an_ordinary_worker_asking_anyway_is_refused_at_the_door(owner):
    """THE SECOND LOCK. Not seeing it must not be the only thing stopping it."""
    from mentis.worker import HANDS_OFF, ORGANISES
    _, grant = _granted(owner, "worker")
    for op in ORGANISES:
        if op in HANDS_OFF:
            continue
        with pytest.raises(urllib.error.HTTPError) as caught:
            over(owner, op, grant=grant, name="x", alias="x", participant="x",
                 work="x", kind="note", body={"text": "x"}, text="x",
                 question="x")
        assert caught.value.code == 403, f"{op} was not refused as a refusal"
        said = json.loads(caught.value.read())["error"]
        assert op in said and "scope" in said, (
            f"the refusal of {op!r} does not say what was needed: {said!r}"
        )


def test_a_delegated_specialist_never_inherits_organising_authority(owner):
    """Delegation hands over WORK, never the authority that arranged it.

    Authority comes from why an execution was dispatched, and a delegated
    execution was not dispatched to organise anything. It may still hand work
    on (`HANDS_OFF`) -- that is not organising -- and no depth counter exists.
    """
    from mentis.worker import HANDS_OFF, ORGANISES, permitted
    organising = set(ORGANISES) - set(HANDS_OFF)
    # However deep, a delegated run is dispatched as an ordinary worker.
    for _ in range(4):
        assert not (organising & set(permitted("worker")))
        assert set(HANDS_OFF) <= set(permitted("worker"))
    # And an unrecognised or absent scope fails closed rather than open.
    for scope in (None, "", "caretaker", "Intake", "INTAKE", "admin"):
        assert not (organising & set(permitted(scope))), (
            f"scope {scope!r} was treated as organising authority"
        )


def test_authority_does_not_survive_the_run_it_was_minted_for(owner):
    """A reused session must not carry the previous run's reason.

    Otherwise an ordinary worker would acquire organising authority simply by
    being summoned into a session that once carried an unaddressed request.
    """
    fnd = owner["state"].agents.authority
    iid, token = _granted(owner, "intake")
    # `summon_participant`, not `delegate`: handing work on is held by every
    # dispatched run, so it no longer tells organising authority apart.
    assert "summon_participant" in fnd.permits_for(iid)
    # What the end of a perform does (`MentisService.agents_perform`).
    fnd.revoke(iid)
    assert fnd.grant_for(token, owner["state"].path) is None
    assert "summon_participant" not in fnd.permits_for(iid), (
        "organising authority outlived the request it was granted for"
    )
