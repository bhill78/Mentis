"""A session the owner started by hand reaches Mentis through the running server.

WHAT MUST HOLD, and is tested here against a real HTTP server and the real MCP
server started exactly as the machine-wide registration starts it:
  - the session asks for its own grant (`SESSION_ROUTE`) and every call goes
    through `/api/worker` under it -- nothing in the session opens the corpus;
  - it is shown, and admitted, exactly `permitted(SESSION_SCOPE)`: what a
    @Caretaker run is granted, less what only a carried request gives meaning
    to (`SESSION_CARRIED`);
  - it organises like @Caretaker: opens a Conversation and acts in it --
    Topics, summoning, delegating -- and nowhere it did not open;
  - what it proposes is a candidate that does not stand, recorded as the
    session Participant with that session's own execution and runtime;
  - two sessions are two executions, and neither is put in a Conversation;
  - nothing it holds can establish: no operation, and no owner route;
  - a server that forgot the grant (a restart) is asked again, unprompted.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from mentis.web import _Handler, _routes, _State, fixture
from mentis import web
from mentis.worker import (AUTHORITY, CAPABILITY_HEADER, SESSION_CARRIED,
                           SESSION_ACTS, SESSION_PARTICIPANT, SESSION_ROUTE,
                           SESSION_SCOPE, boot_command, permitted)


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "corpus"
    fixture.build(str(root))
    st = _State(str(root), str(tmp_path))
    handler = type("H", (_Handler,), {"state": st})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield {"st": st, "url": f"http://127.0.0.1:{httpd.server_address[1]}",
               "owner": st.cv.resolve_participant("@brian")}
    finally:
        httpd.shutdown()
        httpd.server_close()


def _post(url, body, headers):
    req = urllib.request.Request(url, method="POST",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as fh:
            return fh.status, json.loads(fh.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def _mcp(world, runtime, calls, *, between=None):
    """Run the registered MCP server over stdio. Returns responses by id."""
    boot = boot_command(world["st"].path, via=world["url"], session=runtime)
    proc = subprocess.Popen([sys.executable, "-I", "-c", boot],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True,
                            encoding="utf-8")
    out = {}

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        if "id" in msg:
            got = json.loads(proc.stdout.readline())
            out[got["id"]] = got

    send({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
    send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    for i, (name, args) in enumerate(calls, start=2):
        if between and i in between:
            between[i]()
        if callable(args):              # built from earlier answers
            args = args(out)
        send({"jsonrpc": "2.0", "id": i, "method": "tools/call",
              "params": {"name": name, "arguments": args}})
    proc.stdin.close()
    proc.wait(timeout=30)
    return out


def _text(resp):
    result = resp["result"]
    return result.get("isError"), json.loads(result["content"][0]["text"]) \
        if not result.get("isError") else result["content"][0]["text"]


def test_session_sees_and_may_do_what_caretaker_may(world):
    caretaker = set(permitted("organising", AUTHORITY))
    # (Mark IV also took away its server-side web tools, which are gone.)
    assert set(permitted(SESSION_SCOPE)) == (
        caretaker - set(SESSION_CARRIED)) | set(SESSION_ACTS)
    for op in ("summon_participant", "delegate", "open_conversation",
               "open_topic", "propose_material", "deep_dive", "orient"):
        assert op in permitted(SESSION_SCOPE)
    got = _mcp(world, "claude", [])
    names = {t["name"] for t in got[1]["result"]["tools"]}
    assert names == set(permitted(SESSION_SCOPE))
    assert "establish" not in names and "respond" not in names


def test_session_records_request_outcome_and_remaining_work(world):
    st, cv = world["st"], world["st"].cv
    got = _mcp(world, "codex", [
        ("open_conversation", {"name": "CLI work"}),
        ("record_request", lambda out: {
            "conversation": _text(out[2])[1]["conversation"],
            "text": "Reconnect CLI work to Mentis",
            "requester_note": "Owner asked for stage 2",
            "repository": "C:/Work/Mentis", "branch": "reconnect"}),
        ("work_overview", lambda out: {
            "conversation": _text(out[2])[1]["conversation"]}),
        ("record_outcome", lambda out: {
            "expectation": _text(out[3])[1]["expectation"],
            "outcome": "Added the reconnect operations", "result": "done",
            "references": [{"type": "branch", "ref": "reconnect"}],
            "runtimes": ["codex", "claude"],
            "remaining": [{"work": "Apply the Brain transition",
                           "branch": "main"}]}),
        ("work_overview", lambda out: {
            "conversation": _text(out[2])[1]["conversation"]}),
    ])
    _, request = _text(got[3])
    err, before = _text(got[4])
    assert not err and request["expectation"] in {
        i["expectation"] for i in before["items"]}
    err, outcome = _text(got[5])
    assert not err, outcome
    assert outcome["fulfilled_by"] and len(outcome["remaining"]) == 1
    remaining = outcome["remaining"][0]["expectation"]
    err, after = _text(got[6])
    assert not err and remaining in {i["expectation"] for i in after["items"]}
    assert request["expectation"] not in {
        i["expectation"] for i in after["items"]}
    state = cv.expectation_state(request["expectation"])
    assert state["satisfied_by"]
    acts = cv.history(execution=next(
        a["execution"] for a in cv.history(act="manual-session-request-recorded")
        if a["id"] == request["recorded"]))
    assert {a["runtime"] for a in acts if a["runtime"]} == {"codex"}
    assert cv._act(remaining)["caused_by"] == outcome["outcome_act"]


def test_another_session_continues_and_only_done_closes(world):
    # Work recorded by one session is finished by another: that continuation
    # is what recording it is for. Only `done` meets the expectation.
    _, first = _session(world)
    _, second = _session(world)
    _, opened = first("open_conversation", name="Partial work")
    _, request = first("record_request", conversation=opened["conversation"],
                       text="Try this")
    status, partial = first("record_outcome", expectation=request["expectation"],
                            outcome="Some work remains", result="partial",
                            remaining=["Finish the rest"])
    assert status == 200 and partial["fulfilled_by"] is None
    assert not world["st"].cv.expectation_state(
        request["expectation"])["satisfied_by"]
    rest = partial["remaining"][0]["expectation"]
    status, done = second("record_outcome", expectation=rest,
                          outcome="Finished the rest", result="done")
    assert status == 200 and done["fulfilled_by"], done
    status, done = second("record_outcome", expectation=request["expectation"],
                          outcome="Closed by the next session", result="done")
    assert status == 200 and done["fulfilled_by"], done


def test_outcome_refuses_a_request_no_session_recorded(world):
    _, first = _session(world)
    status, refused = first("record_outcome", expectation="opr-000000000000",
                            outcome="Nothing", result="done")
    assert status == 403, refused


def test_open_topic_schema_advertises_conversation():
    from mentis.worker import ACT_TOOLS
    tool = next(t for t in ACT_TOOLS if t["name"] == "open_topic")
    assert "conversation" in tool["inputSchema"]["properties"]


def test_reads_and_proposals_go_through_the_server(world):
    cv = world["st"].cv
    got = _mcp(world, "codex", [
        ("orient", {}),
        ("propose_material", {"kind": "rule",
                              "body": {"text": "Keep dev inside the root."}}),
    ])
    err, orient = _text(got[2])
    assert not err and orient["corpus_path"] == world["st"].path
    err, proposed = _text(got[3])
    assert not err, proposed
    eid = proposed["entry"]
    assert proposed["stands"] is False
    assert world["st"].corpus.stands(eid)["stands"] is False
    pid = cv.find_participant(SESSION_PARTICIPANT)
    entry = world["st"].corpus.read([eid])[0]
    assert entry["attributed_to"] == pid
    assert (entry.get("written_by") or "").startswith("codex/")
    acts = [a for a in cv.history(actor=pid)
            if a["act"] == "material-recorded" and eid in a.get("about", [])]
    assert len(acts) == 1
    act = acts[0]
    assert act["runtime"] == "codex"
    started = [a for a in cv.history(actor=pid)
               if a["act"] == "manual-session-started"]
    assert [a["execution"] for a in started] == [act["execution"]]
    assert entry.get("written_by") == f"codex/{act['execution'][:8]}"
    assert not act.get("conversation")


def test_each_session_is_its_own_execution(world):
    cv = world["st"].cv
    _mcp(world, "claude", [("orient", {})])
    _mcp(world, "antigravity", [("orient", {})])
    pid = cv.find_participant(SESSION_PARTICIPANT)
    started = [a for a in cv.history(actor=pid)
               if a["act"] == "manual-session-started"]
    assert len(started) == 2
    assert len({a["execution"] for a in started}) == 2
    assert {a["runtime"] for a in started} == {"claude", "antigravity"}
    ended = [a for a in cv.history(actor=pid)
             if a["act"] == "manual-session-ended"]
    assert {a["execution"] for a in ended} == {a["execution"] for a in started}
    # Given back at exit: nothing of either session is still admitted.
    assert not [g for g in world["st"].agents.authority._grants.values()
                if g.get("scope") == SESSION_SCOPE]


def test_a_session_cannot_establish(world):
    st, url = world["st"], world["url"]
    status, grant = _post(url + SESSION_ROUTE,
                          {"corpus": st.path, "runtime": "claude"},
                          {"X-Mentis-Client": "1"})
    assert status == 200 and grant["scope"] == SESSION_SCOPE
    status, proposed = _post(url + "/api/worker", {
        "corpus": st.path, "op": "propose_material",
        "args": {"kind": "rule", "body": {"text": "A candidate."}}},
        {CAPABILITY_HEADER: grant["grant"]})
    assert status == 200, proposed
    eid = proposed["entry"]
    # No establishing operation is admitted for the session ...
    for op in ("establish", "establish_material", "respond",
               "request_decision", "propose_revision"):
        status, said = _post(url + "/api/worker",
                             {"corpus": st.path, "op": op, "args": {}},
                             {CAPABILITY_HEADER: grant["grant"]})
        assert status == 403, (op, said)
    # ... and presenting its grant to the owner's establish route is refused.
    status, said = _post(url + f"/api/entries/{eid}/establish",
                         {"attributed_to": world["owner"], "because": "x"},
                         {CAPABILITY_HEADER: grant["grant"],
                          "X-Mentis-Client": "1"})
    assert status == 403
    assert st.corpus.stands(eid)["stands"] is False
    # The owner's own act still establishes it.
    got = _routes(st, f"/api/entries/{eid}/establish", {},
                  {"attributed_to": world["owner"], "because": "owner"},
                  "POST")
    assert "error" not in got, got
    assert st.corpus.stands(eid)["stands"] is True


def test_a_dispatched_grant_cannot_be_traded_for_a_session(world):
    st, url = world["st"], world["url"]
    token = "t-" + "d" * 20
    st.agents.authority._grants[token] = {
        "instance": "i", "corpus": st.path, "scope": "worker",
        "operations": None, "expectation": None, "conversation": None,
        "participant": None, "runtime": "claude"}
    status, _ = _post(url + SESSION_ROUTE,
                      {"corpus": st.path, "runtime": "claude"},
                      {CAPABILITY_HEADER: token, "X-Mentis-Client": "1"})
    assert status == 403


def test_unknown_runtime_and_missing_client_header_are_refused(world):
    st, url = world["st"], world["url"]
    # A runtime with no adapter is accepted only as a LABEL under the name
    # rule (tests/test_agent_access_reads.py); this is not one.
    status, _ = _post(url + SESSION_ROUTE,
                      {"corpus": st.path, "runtime": "none such!"},
                      {"X-Mentis-Client": "1"})
    assert status >= 400
    # http.client, because the suite's conftest adds CLIENT_HEADER to urllib.
    import http.client
    host, port = url[len("http://"):].split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=30)
    conn.request("POST", SESSION_ROUTE,
                 body=json.dumps({"corpus": st.path, "runtime": "claude"}),
                 headers={"Content-Type": "application/json"})
    assert conn.getresponse().status == 403
    conn.close()


def test_a_forgotten_grant_is_asked_for_again(world):
    grants = world["st"].agents.authority._grants

    def restart():
        for k in [k for k, g in grants.items()
                  if g.get("scope") == SESSION_SCOPE]:
            grants.pop(k)

    got = _mcp(world, "claude", [("orient", {}), ("orient", {})],
               between={3: restart})
    assert not got[2]["result"].get("isError")
    assert not got[3]["result"].get("isError"), got[3]


def _session(world):
    st, url = world["st"], world["url"]
    status, grant = _post(url + SESSION_ROUTE,
                          {"corpus": st.path, "runtime": "codex"},
                          {"X-Mentis-Client": "1"})
    assert status == 200

    def op(op_name, **args):
        return _post(url + "/api/worker",
                     {"corpus": st.path, "op": op_name, "args": args},
                     {CAPABILITY_HEADER: grant["grant"]})
    return grant, op


def test_a_session_organises_and_delegates_like_caretaker(world, monkeypatch):
    sent = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: sent.append(kw))
    st, cv = world["st"], world["st"].cv
    grant, op = _session(world)
    pid = grant["participant"]
    status, opened = op("open_conversation", name="Session work",
                        about="opened by a hand-started session")
    assert status == 200, opened
    cid = opened["conversation"]
    status, topic = op("open_topic", name="Plans", conversation=cid)
    assert status == 200 and topic["conversation"] == cid, topic
    status, summoned = op("summon_participant", alias="SessionHelper",
                          conversation=cid)
    assert status == 200, summoned
    helper = summoned["participant"]
    status, handed = op("delegate", participant=helper,
                        work="Summarise the plans.", conversation=cid)
    assert status == 200, handed
    state = cv.expectation_state(handed["expectation"])
    assert state["requested_by"] == pid
    assert handed["parent_expectation"] is None
    assert sent and sent[0]["participant"] == helper
    assert sent[0]["expectation"] == handed["expectation"]
    # Every act is this session's: its Participant, execution and runtime.
    for a in cv.history(execution=grant["execution"]):
        assert a["actor"] == pid and a["runtime"] == "codex"
    for kind in ("rule", "decision", "lesson"):
        # A lesson declares requires_basis (owner decision 1); the
        # Conversation the session works in is what it was drawn from.
        status, got = op("propose_material", kind=kind,
                         body={"text": f"A {kind} from a session."},
                         basis=[cid])
        assert status == 200 and got["stands"] is False, (kind, got)
        assert st.corpus.stands(got["entry"])["stands"] is False


def test_a_session_acts_only_where_it_opened(world, monkeypatch):
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    st, cv = world["st"], world["st"].cv
    other = cv.open_conversation("Somebody else's", attributed_to=world["owner"])
    helper = cv.resolve_participant("@Helper")
    _, op = _session(world)
    status, said = op("summon_participant", alias="X")
    assert status == 403 and "open_conversation" in said["error"]
    status, said = op("delegate", participant=helper, work="w",
                      conversation=other)
    assert status == 403, said
    status, said = op("open_topic", name="t", conversation=other)
    assert status == 403, said
    # A Conversation another session opened is not this one's either.
    _, op2 = _session(world)
    status, opened = op2("open_conversation", name="Theirs")
    status, said = op("delegate", participant=helper, work="w",
                      conversation=opened["conversation"])
    assert status == 403, said


def test_a_session_cannot_run_the_owner_or_itself(world, monkeypatch):
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    st, cv = world["st"], world["st"].cv
    owner = cv.create_participant("@owner-of-this-brain", about="the owner")
    grant, op = _session(world)
    _, opened = op("open_conversation", name="Mine")
    for who in (owner, grant["participant"]):
        status, said = op("delegate", participant=who, work="w",
                          conversation=opened["conversation"])
        assert status == 403, said


def test_a_restart_keeps_what_the_session_opened(world):
    """Renewal continues the same execution, so its Conversations stay its own."""
    st, cv = world["st"], world["st"].cv
    grants = st.agents.authority._grants

    def restart():
        for k in [k for k, g in grants.items()
                  if g.get("scope") == SESSION_SCOPE]:
            grants.pop(k)

    got = _mcp(world, "codex", [
        ("open_conversation", {"name": "Before the restart"}),
        ("orient", {}),
        ("open_topic", lambda out: {
            "name": "After the restart",
            "conversation": _text(out[2])[1]["conversation"]}),
    ], between={3: restart})
    err, opened = _text(got[2])
    assert not err, opened
    assert not got[3]["result"].get("isError"), got[3]       # renewed here
    err, topic = _text(got[4])
    assert not err, topic
    assert topic["conversation"] == opened["conversation"]
    pid = cv.find_participant(SESSION_PARTICIPANT)
    acts = cv.history(actor=pid)
    started = [a for a in acts if a["act"] == "manual-session-started"]
    renewed = [a for a in acts if a["act"] == "manual-session-renewed"]
    assert len(started) == 1 and len(renewed) == 1
    assert renewed[0]["execution"] == started[0]["execution"]
    assert renewed[0]["runtime"] == "codex"


def test_a_renewed_session_still_acts_in_its_own_conversation(world):
    st, url = world["st"], world["url"]
    grants = st.agents.authority._grants
    status, first = _post(url + SESSION_ROUTE,
                          {"corpus": st.path, "runtime": "claude"},
                          {"X-Mentis-Client": "1"})
    status, opened = _post(url + "/api/worker", {
        "corpus": st.path, "op": "open_conversation",
        "args": {"name": "Mine"}}, {CAPABILITY_HEADER: first["grant"]})
    assert status == 200, opened
    grants.clear()                                    # the server restarted
    status, again = _post(url + SESSION_ROUTE,
                          {"corpus": st.path, "runtime": "claude",
                           "continues": first["execution"]},
                          {"X-Mentis-Client": "1"})
    assert status == 200, again
    assert again["execution"] == first["execution"]
    for name, args in (("open_topic", {"name": "t"}),
                       ("summon_participant", {"alias": "Helper2"})):
        status, said = _post(url + "/api/worker", {
            "corpus": st.path, "op": name,
            "args": {**args, "conversation": opened["conversation"]}},
            {CAPABILITY_HEADER: again["grant"]})
        assert status == 200, (name, said)


def test_only_a_known_unended_unheld_session_may_be_continued(world):
    st, url = world["st"], world["url"]
    hdr = {"X-Mentis-Client": "1"}

    def ask(**body):
        return _post(url + SESSION_ROUTE,
                     {"corpus": st.path, "runtime": "claude", **body}, hdr)

    status, live = ask()
    # still held by a live grant
    assert ask(continues=live["execution"])[0] == 403
    # on another runtime than it started on
    st.agents.authority._grants.clear()
    status, _ = _post(url + SESSION_ROUTE,
                      {"corpus": st.path, "runtime": "codex",
                       "continues": live["execution"]}, hdr)
    assert status == 403
    # never started here
    assert ask(continues="00000000-0000-0000-0000-000000000000")[0] == 403
    # ended
    status, other = ask()
    _post(url + SESSION_ROUTE + "/end",
          {"corpus": st.path, "grant": other["grant"]}, hdr)
    assert ask(continues=other["execution"])[0] == 403
    # and the one that lost its grant may continue
    assert ask(continues=live["execution"])[0] == 200


def test_the_ended_act_records_the_runtime(world):
    st, cv = world["st"], world["st"].cv
    _mcp(world, "antigravity", [("orient", {})])
    pid = cv.find_participant(SESSION_PARTICIPANT)
    ended = [a for a in cv.history(actor=pid)
             if a["act"] == "manual-session-ended"]
    assert len(ended) == 1 and ended[0]["runtime"] == "antigravity"


def test_summoning_refuses_reserved_and_former_names(world, monkeypatch):
    """`summon_participant` is a door to new addressing, so a former alias is
    pointed at the current one, a runtime's name is refused, and a
    Participant still named like a runtime is refused until the owner renames
    it (tests/test_participant_rename.py)."""
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    st, cv = world["st"], world["st"].cv
    bob = cv.create_participant("@Bob")
    cv.rename_participant(bob, "@Robert", by=world["owner"])
    legacy = cv.corpus.create_and_establish(
        kind="participant", body={"alias": "@Codex", "about": ""},
        attributed_to="human")
    _, op = _session(world)
    status, opened = op("open_conversation", name="Summoning")
    cid = opened["conversation"]
    before = len(cv.all_participants())
    for alias, words in (("@Codex", "rename"), ("Bob", "@Robert"),
                         ("gemini", "runtime or model")):
        status, said = op("summon_participant", alias=alias, conversation=cid)
        assert status == 403 and words in said["error"], (alias, said)
    assert len(cv.all_participants()) == before
    assert legacy not in cv.participants(cid) and bob not in cv.participants(cid)
    status, said = op("summon_participant", alias="Robert", conversation=cid)
    assert status == 200 and said["participant"] == bob, said
