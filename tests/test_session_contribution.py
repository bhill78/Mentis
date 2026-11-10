"""WS-I: independent contribution, session identity, explainable refusals, durable
reporting (`docs/modernization/CONTRACT.md`).

Against a real HTTP server and, for the outbox, the real MCP server started as
the machine-wide registration starts it -- with its outbox in the test's own
temp folder, never `%LOCALAPPDATA%`.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mentis import web
from mentis.outbox import Outbox
from mentis.session_identity import default_alias
from mentis.worker import CAPABILITY_HEADER, SESSION_ROUTE
from tests.test_manual_session import _mcp, _post, _text, world  # noqa: F401


def _start(world, runtime="codex", **extra):
    st, url = world["st"], world["url"]
    status, grant = _post(url + SESSION_ROUTE,
                          {"corpus": st.path, "runtime": runtime, **extra},
                          {"X-Mentis-Client": "1"})
    assert status == 200, grant

    def op(op_name, **args):
        return _post(url + "/api/worker",
                     {"corpus": st.path, "op": op_name, "args": args},
                     {CAPABILITY_HEADER: grant["grant"]})
    return grant, op


def _acts(cv, act):
    return [a for a in cv.corpus.operational(act=act)]


# -- identity -----------------------------------------------------------------

def test_one_participant_per_runtime_and_host(world):
    cv = world["st"].cv
    a1, _ = _start(world, "claude", host="ALPHA")
    a2, _ = _start(world, "claude", host="ALPHA")
    b, _ = _start(world, "claude", host="BETA")
    c, _ = _start(world, "codex", host="ALPHA")
    assert a1["participant"] == a2["participant"]
    assert a1["execution"] != a2["execution"]          # each session its own run
    assert len({a1["participant"], b["participant"], c["participant"]}) == 3
    assert a1["alias"] == "@Claude-CLI-ALPHA" and b["alias"] == "@Claude-CLI-BETA"
    assert c["alias"] == "@Codex-CLI-ALPHA" and a1["host"] == "ALPHA"
    about = cv.corpus.read([a1["participant"]])[0]["body"]["about"]
    assert "independently launched CLI agent" in about
    started = [a for a in _acts(cv, "manual-session-started")
               if a["execution"] == b["execution"]]
    assert started[0]["detail"]["host"] == "BETA"


def test_a_named_participant_and_never_the_owner(world):
    named, _ = _start(world, "claude", host="ALPHA", participant="Cleanup-Agent")
    assert named["alias"] == "@Cleanup-Agent"
    again, _ = _start(world, "codex", host="BETA",
                      participant=named["participant"])
    assert again["participant"] == named["participant"]
    st, url = world["st"], world["url"]
    for who in (world["owner"], "@brian"):
        status, said = _post(url + SESSION_ROUTE,
                             {"corpus": st.path, "runtime": "claude",
                              "participant": who}, {"X-Mentis-Client": "1"})
        assert status >= 400 and "owner" in said["error"], said


def test_every_act_records_the_host(world):
    cv = world["st"].cv
    grant, op = _start(world, "claude", host="GAMMA")
    status, opened = op("open_conversation", name="Hosted")
    assert status == 200, opened
    for a in cv.history(execution=grant["execution"]):
        assert a["actor"] == grant["participant"]
        assert (a.get("detail") or {}).get("host") == "GAMMA", a


# -- authorized_by ------------------------------------------------------------

def test_authorized_by_is_stored_apart_from_the_actor(world):
    cv = world["st"].cv
    grant, op = _start(world, "claude", host="ALPHA")
    _, opened = op("open_conversation", name="Cleanup")
    said = {"source": "owner-in-chat", "note": "clean up the temp folders"}
    status, request = op("record_request", conversation=opened["conversation"],
                         text="Clean the temp folders", authorized_by=said)
    assert status == 200, request
    exp = cv._act(request["expectation"])
    assert exp["actor"] == grant["participant"]
    assert exp["detail"]["authorized_by"] == {**said, "request": None}
    words = cv.corpus.read([request["turn"]])[0]["body"]["parts"][0]["text"]
    assert ("Authorized by the owner in chat (clean up the temp folders); "
            f"executed by {grant['alias']}.") in words
    # Every act of that call carries it too, beside the host.
    recorded = cv._act(request["recorded"])
    assert recorded["detail"]["authorized_by"]["source"] == "owner-in-chat"
    assert recorded["detail"]["host"] == "ALPHA"
    # And any other write: a ladder record under the request defaults to it.
    status, got = op("record_material", kind="note", body={"text": "n"},
                     authorized_by={"source": "request",
                                    "request": request["expectation"]})
    assert status == 200, got
    act = cv._act(got["act"])
    assert act["detail"]["authorized_by"] == {
        "source": "request", "note": "", "request": request["expectation"]}


def test_a_malformed_authorization_is_a_validation_refusal(world):
    _, op = _start(world)
    status, said = op("record_material", kind="note", body={"text": "n"},
                      authorized_by={"source": "my manager"})
    assert status == 403
    assert said["refusal"]["boundary"] == "validation"


# -- the narrowed default ------------------------------------------------------

def test_coordination_needs_a_recorded_request(world, monkeypatch):
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    _, op = _start(world)
    for name, args in (("delegate", {"participant": world["owner"], "work": "w"}),
                       ("summon_participant", {"alias": "Helper"}),
                       ("attach_follow_up", {"work": "opr-000000000000"}),
                       ("change_workflow", {"expectation": "opr-000000000000",
                                            "workflow": "x"}),
                       ("resume_intake", {"expectation": "all"})):
        status, said = op(name, **args)
        assert status == 403, (name, said)
        refusal = said["refusal"]
        assert refusal["op"] == name and refusal["boundary"] == "coordination"
        assert any("record_request" in r and "under" in r
                   for r in refusal["recovery"]), refusal
        assert refusal["who"]
    # The contribution ops, reads and opening hold without one.
    status, _ = op("orient")
    assert status == 200
    status, opened = op("open_conversation", name="Mine")
    assert status == 200
    status, _ = op("record_material", kind="note", body={"text": "seen"})
    assert status == 200
    # Under a request it recorded, coordinating is admitted.
    _, request = op("record_request", conversation=opened["conversation"],
                    text="the work")
    status, summoned = op("summon_participant", alias="Helper",
                          conversation=opened["conversation"],
                          under=request["expectation"])
    assert status == 200, summoned


# -- contribute ----------------------------------------------------------------

def test_contribute_every_kind_into_one_contributions_conversation(world,
                                                                    monkeypatch):
    sent = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: sent.append(kw))
    st, cv = world["st"], world["st"].cv
    grant, op = _start(world, "claude", host="ALPHA")
    other, op2 = _start(world, "codex", host="BETA")
    out = {}
    for kind in ("finding", "problem", "observation", "proposed-work"):
        status, got = op("contribute", kind=kind, text=f"a {kind}",
                         evidence=["tests/test_x.py: 3 failed",
                                   "commit 1a2b3c4"])
        assert status == 200, (kind, got)
        assert got["stands"] is False and got["dispatched"] is False
        out[kind] = got
    status, theirs = op2("contribute", kind="observation", text="from codex")
    assert status == 200, theirs
    # ONE Contributions Conversation per Brain, whoever contributes.
    cids = {g["conversation"] for g in list(out.values()) + [theirs]}
    assert len(cids) == 1
    cid = cids.pop()
    assert cv.conversation_name(cid) == "Contributions"
    assert world["owner"] in cv.participants(cid)
    # Attributed, not standing; material only for finding and problem.
    for kind, got in out.items():
        turn = cv.corpus.read([got["turn"]])[0]
        assert turn["attributed_to"] == grant["participant"]
        act = cv._act(got["recorded"])
        assert act["actor"] == grant["participant"]
        assert act["detail"]["kind"] == kind and act["detail"]["stands"] is False
        if kind in ("finding", "problem"):
            entry = st.corpus.read([got["material"]])[0]
            assert entry["definition"]["name"] == kind
            assert st.corpus.stands(got["material"])["stands"] is False
        else:
            assert got["material"] is None
    # Proposed work: unassigned, owner-addressed, no parent, nothing dispatched.
    proposed = out["proposed-work"]["expectation"]
    exp = cv._act(proposed)
    assert exp["caused_by"] is None and exp["about"] == []
    assert cv.assigned_carrier(proposed)["carrier"] is None
    assert exp["detail"]["addressed_to"] == world["owner"]
    addressed = cv.addressees_of(out["proposed-work"]["turn"])["all"]
    assert addressed == [world["owner"]]
    assert sent == []
    # ... and the owner sees it in Work Overview as unassigned owner-addressed.
    status, overview = op("work_overview", conversation=cid)
    assert status == 200, overview
    item = next(i for i in overview["items"] if i["expectation"] == proposed)
    assert item["state"] == "unassigned"
    assert item["proposed_work"] is True
    assert item["addressed_to"] == world["owner"]
    assert item["proposed_by"] == grant["participant"]


def test_contribute_records_regarding_and_refuses_what_is_not_held(world):
    cv = world["st"].cv
    _, op = _start(world)
    _, opened = op("open_conversation", name="Mine")
    _, request = op("record_request", conversation=opened["conversation"],
                    text="the work")
    status, got = op("contribute", kind="finding", text="a later finding",
                     evidence=[request["turn"]],
                     regarding=[request["expectation"]])
    assert status == 200, got
    assert cv._act(got["recorded"])["detail"]["regarding"] == [
        request["expectation"]]
    status, said = op("contribute", kind="finding", text="x",
                      regarding=["opr-000000000000"])
    assert status == 403 and said["refusal"]["boundary"] == "validation"
    status, said = op("contribute", kind="rumour", text="x")
    assert status == 403 and said["refusal"]["boundary"] == "validation"


def test_the_incident_replayed(world):
    """2026-11-10: an owner-authorized cleanup session, no request recorded,
    finds a real defect. Recording it as discovered work is refused -- now
    saying what to do -- and `contribute` keeps it."""
    _, op = _start(world, "claude", host="ALPHA")
    status, said = op("record_discovered_work",
                      work="cleanup.ps1 deletes the live Brain's WAL")
    assert status == 403
    refusal = said["refusal"]
    assert refusal["op"] == "record_discovered_work"
    assert refusal["boundary"] == "lineage"
    assert any(r.startswith("contribute(") for r in refusal["recovery"])
    assert any("record_request" in r and "under=" in r
               for r in refusal["recovery"])
    assert "contribute(" in said["error"]           # the words say it too
    status, got = op("contribute", kind="problem",
                     text="cleanup.ps1 deletes the live Brain's WAL",
                     evidence=["tools/cleanup.ps1 line 40"],
                     authorized_by={"source": "owner-in-chat",
                                    "note": "owner asked for a temp cleanup"})
    assert status == 200 and got["material"], got


def test_a_refusal_is_rendered_by_the_bridge(world):
    got = _mcp(world, "claude", [("record_discovered_work", {"work": "x"})])
    result = got[2]["result"]
    assert result.get("isError")
    text = result["content"][0]["text"]
    assert text.startswith("NotPermitted:")
    assert "boundary: lineage" in text
    assert "recovery: contribute(" in text
    assert "who can lift it:" in text


# -- op_key --------------------------------------------------------------------

def test_the_same_op_key_twice_is_one_act(world):
    cv = world["st"].cv
    _, op = _start(world)
    first = op("contribute", kind="observation", text="once", op_key="k-1")
    second = op("contribute", kind="observation", text="once", op_key="k-1")
    assert first[0] == second[0] == 200
    assert second[1]["replayed"] is True
    assert {k: v for k, v in second[1].items() if k not in ("replayed", "op_key")
            } == first[1]
    assert len(_acts(cv, "contribution-recorded")) == 1
    # A new key is a new act; the same key for another write is refused.
    status, _ = op("contribute", kind="observation", text="once", op_key="k-2")
    assert status == 200 and len(_acts(cv, "contribution-recorded")) == 2
    status, said = op("contribute", kind="observation", text="other",
                      op_key="k-1")
    assert status == 403 and said["refusal"]["boundary"] == "validation"
    assert len(_acts(cv, "contribution-recorded")) == 2


def test_op_keys_are_per_participant(world):
    cv = world["st"].cv
    _, op = _start(world, "claude", host="ALPHA")
    _, op2 = _start(world, "codex", host="ALPHA")
    assert op("contribute", kind="observation", text="t", op_key="same")[0] == 200
    got = op2("contribute", kind="observation", text="t", op_key="same")
    assert got[0] == 200 and "replayed" not in got[1]
    assert len(_acts(cv, "contribution-recorded")) == 2


def test_a_replayed_delegation_dispatches_once(world, monkeypatch):
    sent = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: sent.append(kw))
    cv = world["st"].cv
    _, op = _start(world)
    _, opened = op("open_conversation", name="Mine")
    _, request = op("record_request", conversation=opened["conversation"],
                    text="the work")
    _, helper = op("summon_participant", alias="Helper",
                   conversation=opened["conversation"],
                   under=request["expectation"])
    args = {"participant": helper["participant"], "work": "do it",
            "under": request["expectation"], "op_key": "d-1"}
    a = op("delegate", **args)
    b = op("delegate", **args)
    assert a[0] == b[0] == 200, (a, b)
    assert b[1]["replayed"] is True
    assert b[1]["expectation"] == a[1]["expectation"]
    assert len(sent) == 1


# -- the outbox ----------------------------------------------------------------

class _LosingProxy:
    """Forwards to the server, and for the first `contribute` forwards it and
    then drops the connection without answering: the server committed, the
    client never heard."""

    def __init__(self, target):
        self.target, self.dropped, self.calls = target, 0, []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                try:
                    op = json.loads(body).get("op")
                except ValueError:
                    op = None
                outer.calls.append(op)
                req = urllib.request.Request(
                    outer.target + self.path, data=body, method="POST",
                    headers={k: v for k, v in self.headers.items()
                             if k.lower() not in ("host", "content-length")})
                try:
                    with urllib.request.urlopen(req, timeout=30) as fh:
                        status, data = fh.status, fh.read()
                except urllib.error.HTTPError as exc:
                    status, data = exc.code, exc.read()
                if op == "contribute" and outer.dropped == 0:
                    outer.dropped += 1
                    self.close_connection = True
                    return                      # nothing written back
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def test_a_lost_answer_is_resent_and_recorded_once(world):
    cv = world["st"].cv
    proxy = _LosingProxy(world["url"])
    try:
        got = _mcp({**world, "url": proxy.url}, "claude", [
            ("contribute", {"kind": "problem", "text": "lost on the wire"}),
            ("orient", {}),
        ])
    finally:
        proxy.close()
    lost = got[2]["result"]
    assert lost.get("isError")
    assert "KEPT IN THIS SESSION'S OUTBOX" in lost["content"][0]["text"]
    assert not got[3]["result"].get("isError")
    # Sent twice -- once lost, once resent before `orient` -- recorded once.
    assert proxy.calls.count("contribute") == 2
    acts = _acts(cv, "contribution-recorded")
    assert len(acts) == 1
    keyed = [a for a in _acts(cv, "operation-keyed")
             if a["detail"]["op"].startswith("worker:contribute:")]
    assert len(keyed) == 1
    assert Outbox(default_alias("claude"), world["outbox"]).pending() == []


def test_a_write_never_sent_is_sent_at_the_next_start(world):
    """The session crashed after keeping the write and before sending it."""
    cv = world["st"].cv
    box = Outbox(default_alias("codex"), world["outbox"])
    box.put("contribute", {"kind": "observation", "text": "kept, never sent",
                           "op_key": "crash-1"})
    assert len(box.pending()) == 1
    _mcp(world, "codex", [("orient", {})])
    acts = _acts(cv, "contribution-recorded")
    assert len(acts) == 1
    assert box.pending() == []
    # A later start finds nothing to send, and nothing is recorded twice.
    _mcp(world, "codex", [("orient", {})])
    assert len(_acts(cv, "contribution-recorded")) == 1


def test_the_bridge_gives_every_write_a_key(world):
    cv = world["st"].cv
    _mcp(world, "codex", [("contribute", {"kind": "observation", "text": "k"})])
    keyed = [a for a in _acts(cv, "operation-keyed")
             if a["detail"]["op"].startswith("worker:contribute:")]
    assert len(keyed) == 1
    assert Outbox(default_alias("codex"), world["outbox"]).pending() == []
