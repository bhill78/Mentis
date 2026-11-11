"""Row J: what a front restart does to agent calls. 13, then 3 live. `R1-acceptance.md`, "J", and
`docs/rust-front-restart.md`, cases A to F.

Every message is judged whole by `decide`, against only the entries that case can truly be in. A
call is put in hand by holding SQLite's write lock on the run's copy from this process, so Python's
write waits inside its transaction for as long as the test likes.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import pathlib
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

import pytest

from tests.front import restart_messages
from tests.front.pair import (CLIENT, FRONT_503, PORT, REAL_MARS, Pair, ask, conversation_named, exchange, post_json, process_tree, request, rows,
                              session_grant, terminate, told, wait_gone)
from tests.front.restart_messages import Refusals
from tests.front.verifiers import assert_both_verify
from tools.r1 import common, door_recorder
from tools.r1 import ledger as ledger_tool

IN_HAND_S = 1.0
#: Where the launcher puts Python, by default, and so where J6's and J7's recorder carries to.
PRIVATE_PORT = PORT + 10000
#: `contracts/launcher.md`'s `DRAIN_LIMIT`, and how long past it a cut may be seen.
DRAIN_S = 35
CUT_SLACK_S = 5
#: J5's limit: the table is read each second.
TABLE_S = 2.0
#: Long enough for a reply to outrun every socket's buffer on the way to a client that holds back.
BIG_POST_CHARS = 30_000_000
#: Far more than any live turn should need. Whether it succeeds doesn't decide J6 or J7.
LIVE_RUN_LIMIT_S = 600
#: J10's run: `tests/fakes/mars_stdio_stand_in.py`, and the one backend it lists.
STAND_IN_SCRIPT = common.REPO / "tests" / "fakes" / "mars_stdio_stand_in.py"
STAND_IN = "j10-stand-in"


@pytest.fixture
def seed_copy(brain_seed, tmp_path):
    copy = tmp_path / "brain"
    shutil.copytree(brain_seed, copy)
    return copy


@pytest.fixture
def pair(seed_copy):
    with Pair(seed_copy) as running:
        yield running


@contextlib.contextmanager
def write_lock(brain):
    conn = sqlite3.connect(pathlib.Path(brain) / "corpus.db", isolation_level=None, timeout=30)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield
    finally:
        conn.execute("ROLLBACK")
        conn.close()


def in_thread(target, *args, **kw):
    result: dict = {}

    def run():
        result["value"] = target(*args, **kw)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, result


def call(pair, grant, tool, /, **args):
    return told(pair.url, pair.brain, tool, args, grant)


def conversations_named(brain, name: str) -> int:
    return rows(brain, "SELECT COUNT(*) FROM entry WHERE def_name='conversation' "
                       "AND json_extract(body,'$.name')=?", name)[0][0]


def owner_of(brain) -> str:
    return rows(brain, "SELECT id FROM entry WHERE def_name='participant' "
                       "AND json_extract(body,'$.alias')='@r1-owner'")[0][0]


def test_j1_a_planned_stop_finishes_what_it_has_and_cuts_at_the_limit(pair):
    python = pair.python_pid
    known = conversation_named(pair.brain, "R1 known conversation")

    # A slow read and a slow write: Python is suspended with both in its hands.
    pair.suspend_python()
    try:
        reading, read = in_thread(ask, pair.port, "GET", f"/api/conversations/{known}",
                                  headers=CLIENT, wait=60.0)
        writing, wrote = in_thread(post_json, pair.port, "/fluid/api/conversations",
                                   {"author": owner_of(pair.brain), "name": "J1 written"}, CLIENT,
                                   wait=60.0)
        time.sleep(IN_HAND_S)
        stopped_at = time.monotonic()
        assert pair.stop_front().status == 200
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", pair.port), timeout=2)
        assert pair.python_pid == python
    finally:
        pair.resume_python()
    reading.join(60)
    writing.join(60)
    assert read["value"].status == 200, read
    assert wrote["value"].status == 201, wrote
    assert conversations_named(pair.brain, "J1 written") == 1
    front = pair.front_pid
    assert wait_gone(front, DRAIN_S + CUT_SLACK_S), "the front didn't exit"
    gap_began = stopped_at

    pair.restart_front()
    print(f"\nJ1 gap: {time.monotonic() - gap_began:.2f} s, with the drain")
    assert pair.python_pid == python

    # A call past the limit: Python stays suspended, so nothing ever answers it.
    pair.suspend_python()
    try:
        cut, got = in_thread(lambda: exchange(pair.port, request("GET", "/api/server"), wait=120.0))
        time.sleep(IN_HAND_S)
        began = time.monotonic()
        assert pair.stop_front().status == 200
        cut.join(DRAIN_S + CUT_SLACK_S)
        took = time.monotonic() - began
    finally:
        pair.resume_python()
    assert got.get("value", b"x") == b"", "a cut call has no answer"
    assert DRAIN_S - 1 <= took <= DRAIN_S + CUT_SLACK_S, f"cut at {took:.1f} s"
    assert wait_gone(pair.front_pid)
    assert pair.python_pid == python


def test_j2_a_call_in_the_gap_is_told_nothing_was_done(pair):
    grant = session_grant(pair.port)["grant"]
    before = conversations_named(pair.brain, "J2 never")
    assert pair.stop_front().status == 200
    assert wait_gone(pair.front_pid, DRAIN_S + CUT_SLACK_S)
    answer, message = call(pair, grant, "open_conversation", name="J2 never")
    assert answer is None
    assert restart_messages.decide(message, ["A"]) == ["A"], message
    pair.restart_front()
    assert conversations_named(pair.brain, "J2 never") == before == 0, "Python saw no such call"


def rpc(stream_in, stream_out, method, params=None, rid=1):
    stream_in.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
                                "params": params or {}}) + "\n")
    stream_in.flush()
    return json.loads(stream_out.readline())


def test_j3_what_starts_in_the_gap(pair):
    grant = session_grant(pair.port)["grant"]
    permits = ("answer", "anchor")
    assert pair.stop_front().status == 200
    assert wait_gone(pair.front_pid, DRAIN_S + CUT_SLACK_S)

    bridge = subprocess.run(
        [sys.executable, str(common.REPO / "tools" / "mcp_bridge.py"), "--session", "claude",
         "--server", pair.url],
        capture_output=True, text=True, encoding="utf-8", timeout=60, stdin=subprocess.DEVNULL)
    assert bridge.returncode == restart_messages.LIST["bridge_exit"]["C"]["exit_code"], bridge
    assert bridge.stdout == "", bridge
    assert restart_messages.is_bridge_exit(bridge.stderr), bridge.stderr

    from mentis.worker import boot_command
    booted = subprocess.Popen(
        [sys.executable, "-I", "-c",
         boot_command(str(pair.brain), via=pair.url, capability=grant, permits=permits)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        encoding="utf-8")
    try:
        rpc(booted.stdin, booted.stdout, "initialize", {"protocolVersion": "2024-11-05",
                                                        "capabilities": {},
                                                        "clientInfo": {"name": "J3",
                                                                       "version": "1"}})
        listed = rpc(booted.stdin, booted.stdout, "tools/list", rid=2)["result"]["tools"]
        assert sorted(tool["name"] for tool in listed) == sorted(permits)
        assert booted.poll() is None, "a boot_command server stays up"
        called = rpc(booted.stdin, booted.stdout, "tools/call",
                     {"name": "anchor", "arguments": {"version": "ent-000000000000",
                                                      "type": "version"}}, rid=3)["result"]
        assert called["isError"] is True
        text = called["content"][0]["text"]
        assert restart_messages.decide(text, ["A"]) == ["A"], text
    finally:
        booted.kill()
        booted.wait(timeout=30)
    pair.restart_front()


def test_j4_a_reset_after_sending_says_the_result_is_unknown_and_python_goes_on(pair):
    grant = session_grant(pair.port)["grant"]
    with write_lock(pair.brain):
        thread, result = in_thread(call, pair, grant, "open_conversation", name="J4 written")
        time.sleep(IN_HAND_S)
        pair.kill_front()
        thread.join(30)
    answer, message = result["value"]
    assert answer is None
    assert restart_messages.decide(message, ["B-sent"]) == ["B-sent"], message
    deadline = time.monotonic() + 30
    while not conversations_named(pair.brain, "J4 written"):
        assert time.monotonic() < deadline, "Python didn't commit it"
        time.sleep(0.05)
    time.sleep(0.5)
    assert conversations_named(pair.brain, "J4 written") == 1


ROUTES_OWNED = {"format": 1, "routes": [
    {"id": "api", "method": "GET", "path": "/api/*", "owner": "python"},
    {"id": "fluid", "method": "GET", "path": "/fluid/api/*", "owner": "python"},
    {"id": "static", "method": "GET", "path": "*", "owner": "rust"}]}
ROUTES_BACK = {"format": 1, "routes": [
    {"id": "static", "method": "GET", "path": "*", "owner": "python"}]}


def answered_by_python_after(pair, changed: float, status: int) -> None:
    """A request begun within the limit of the change gets `status`. Judged from when each was
    sent, because with Python gone a forwarded one takes Windows about 2 s to find that out."""
    while True:
        sent = time.monotonic()
        if ask(pair.port, "GET", "/").status == status:
            return
        assert sent - changed <= TABLE_S, f"not {status} for a request sent within {TABLE_S} s"
        time.sleep(0.05)


def test_j5_a_route_goes_back_by_the_table_with_no_restart_within_two_seconds(seed_copy, tmp_path):
    """Who answered is seen by Python being gone: the front's own answer doesn't need it, and a
    forwarded one is 503. No other difference is allowed to show."""
    table = tmp_path / "routes.json"
    table.write_text(json.dumps(ROUTES_OWNED), encoding="utf-8")
    with Pair(seed_copy, route_table=table) as pair:
        front = pair.front_pid
        pair.kill_python()
        assert ask(pair.port, "GET", "/").status == 200, "owned"

        written = tmp_path / "routes.new"
        written.write_text(json.dumps(ROUTES_BACK), encoding="utf-8")
        os.replace(written, table)
        changed = time.monotonic()
        answered_by_python_after(pair, changed, 503)
        assert pair.front_pid == front

        written.write_text(json.dumps(ROUTES_OWNED), encoding="utf-8")
        os.replace(written, table)
        changed = time.monotonic()
        answered_by_python_after(pair, changed, 200)
        assert pair.front_pid == front


def big_reply_post(pair) -> str:
    """A post `resolve` answers whole, too big for any socket's buffers on the way."""
    known = conversation_named(pair.brain, "R1 known conversation")
    words = "the harbour light " * (BIG_POST_CHARS // 18)
    posted = post_json(pair.port, "/fluid/api/posts", {"conversation": known, "text": words,
                                                       "author": owner_of(pair.brain)}, CLIENT,
                       wait=120.0)
    assert posted.status == 200, posted
    return posted.json["post"]


def test_j8_killed_while_a_reply_s_body_arrives(pair):
    """The real `_over`, with a small receive buffer and its first read of the body held until the
    front is dead, so the head has come and the rest can't all have."""
    grant = session_grant(pair.port)["grant"]
    post = big_reply_post(pair)
    headed, killed = threading.Event(), threading.Event()
    original_begin = http.client.HTTPResponse.begin
    original_connect = http.client.HTTPConnection.connect
    worker: list[threading.Thread] = []

    def connect(self):
        if worker and threading.current_thread() is worker[0]:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.host, self.port))
            return
        original_connect(self)

    def begin(self):
        original_begin(self)
        if worker and threading.current_thread() is worker[0]:
            headed.set()
            assert killed.wait(30)

    http.client.HTTPConnection.connect = connect
    http.client.HTTPResponse.begin = begin
    try:
        def run():
            return call(pair, grant, "resolve", ref=post)

        result: dict = {}
        thread = threading.Thread(target=lambda: result.update(value=run()), daemon=True)
        worker.append(thread)
        thread.start()
        assert headed.wait(60), "the reply never came"
        pair.kill_front()
        killed.set()
        thread.join(60)
    finally:
        http.client.HTTPConnection.connect = original_connect
        http.client.HTTPResponse.begin = original_begin
    answer, message = result["value"]
    assert answer is None, "the whole reply fitted the buffers, so nothing was cut off"
    assert "IncompleteRead" not in message, message
    assert restart_messages.decide(message, ["B-reply"]) == ["B-reply"], message


def test_j9_python_killed_with_a_call_forwarded(pair):
    grant = session_grant(pair.port)["grant"]
    raw_body = json.dumps({"corpus": str(pair.brain), "op": "open_conversation",
                           "args": {"name": "J9 raw"}}).encode()
    with write_lock(pair.brain):
        through_worker, worker = in_thread(call, pair, grant, "open_conversation", name="J9 worker")
        direct, raw = in_thread(
            ask, pair.port, "POST", "/api/worker", body=raw_body, wait=30.0,
            headers={"Content-Type": "application/json", "X-Mentis-Worker": grant})
        time.sleep(IN_HAND_S)
        pair.kill_python()
        through_worker.join(30)
        direct.join(30)
    assert raw["value"].status == 503, raw
    assert raw["value"].json == {"error": FRONT_503["Python-reached"]}
    _, message = worker["value"]
    assert restart_messages.decide(message, ["Python-reached"]) == ["Python-reached"], message


def keyed_twice(pair, grant, tool, /, **args):
    """A keyed write, its reply lost to a reset, then sent again under the same key. What the
    second call answers, with the first having committed."""
    key = uuid.uuid4().hex
    with write_lock(pair.brain):
        thread, first = in_thread(call, pair, grant, tool, **args, op=key)
        time.sleep(IN_HAND_S)
        pair.kill_front()
        thread.join(30)
    assert first["value"][1] is not None, f"{tool}: the first call was answered"
    time.sleep(1.0)  # Python commits once the lock goes
    pair.restart_front()
    answer, message = call(pair, grant, tool, **args, op=key)
    assert message is None, f"{tool}: {message}"
    assert answer.get("replayed") is True, f"{tool}: {answer}"
    return answer


def dispatched_run(pair, told: pathlib.Path, text: str) -> tuple[str, str, tuple]:
    """`@r1-agent` asked for `text` as the composer asks it, through the stand-in for `mars stdio`:
    (the grant dispatch started it with, its Participant, its execution and the request it carries).
    The grant is read from the MCP server's command dispatch gave the session, as a runtime would be
    given it."""
    agent = rows(pair.brain, "SELECT id FROM entry WHERE def_name='participant' "
                             "AND json_extract(body,'$.alias')='@r1-agent'")[0][0]
    posted = post_json(pair.port, "/fluid/api/posts", {
        "conversation": conversation_named(pair.brain, "R1 known conversation"),
        "author": owner_of(pair.brain), "text": text, "action": "ask-participant",
        "addressed_to": [agent], "dispatch": [{"participant": agent, "runtime": STAND_IN}]}, CLIENT)
    assert posted.status == 200, posted
    assert posted.json["dispatched"] >= 1, posted
    deadline = time.monotonic() + 60
    while not (told.exists() and told.read_text(encoding="utf-8").strip()):
        assert time.monotonic() < deadline, f"no run began; see {pair.run_dir}"
        time.sleep(0.1)
    servers = json.loads(told.read_text(encoding="utf-8").splitlines()[0])
    mentis = next(server for server in servers if server["name"] == "mentis")
    return (re.search(r"capability='([^']+)'", mentis["args"][-1]).group(1), agent,
            rows(pair.brain, "SELECT execution, caused_by FROM operational "
                             "WHERE act = 'execution-started' ORDER BY seq DESC LIMIT 1")[0])


def test_j10_a_keyed_write_repeated_after_a_reset_happens_once(seed_copy, tmp_path):
    told = tmp_path / "sessions.jsonl"
    stand_in = f'"{common.venv_python()}" "{STAND_IN_SCRIPT}" "{told}"'
    with Pair(seed_copy, mars=stand_in) as pair:
        grant = session_grant(pair.port)["grant"]
        owner = owner_of(pair.brain)
        conversation = call(pair, grant, "open_conversation", name="J10 here")[0]["conversation"]
        posted = call(pair, grant, "record_request", conversation=conversation, text="J10")
        assert posted[1] is None, posted
        post = posted[0]["turn"]

        def entries_of(kind: str) -> int:
            return rows(pair.brain, "SELECT COUNT(*) FROM entry WHERE def_name = ?", kind)[0][0]

        before = entries_of("anchor")
        made = keyed_twice(pair, grant, "anchor", version=post, type="version")
        assert entries_of("anchor") == before + 1, "anchor"
        anchor = made["anchor"]

        reacted = rows(pair.brain, "SELECT COUNT(*) FROM entry WHERE body LIKE '%J10-token%'")[0][0]
        keyed_twice(pair, grant, "react", anchor=anchor, token="J10-token")
        assert rows(pair.brain, "SELECT COUNT(*) FROM entry WHERE body LIKE '%J10-token%'")[0][0] \
            == reacted + 1, "react"

        keyed_twice(pair, grant, "deep_dive", anchor=anchor, why="J10 why", name="J10 dive")
        assert conversations_named(pair.brain, "J10 dive") == 1, "deep_dive"

        # The composer's own post, under its `op`, through the front.
        key = uuid.uuid4().hex
        words = "J10 composed post"
        body = {"conversation": conversation, "author": owner, "text": words, "op": key}
        with write_lock(pair.brain):
            thread, _ = in_thread(post_json, pair.port, "/fluid/api/posts", body, CLIENT, wait=30.0)
            time.sleep(IN_HAND_S)
            pair.kill_front()
            thread.join(30)
        time.sleep(1.0)
        pair.restart_front()
        again = post_json(pair.port, "/fluid/api/posts", body, CLIENT)
        assert again.status == 200, again
        assert again.json["replayed"] is True, again
        assert rows(pair.brain, "SELECT COUNT(*) FROM entry WHERE body LIKE ?",
                    f"%{words}%")[0][0] == 1, "post"

        # `answer` and `timer`, as the tools they are: `/api/worker`, under a grant dispatch made
        # for a run it started. Each sent by `_over`, with its `op`, across the reset. The run is
        # still going throughout, because Python and the stand-in don't notice the front go.
        form = post_json(pair.port, "/fluid/api/posts", {
            "conversation": conversation_named(pair.brain, "R1 known conversation"),
            "author": owner, "text": "J10 form\n\n```checklist version=1 name=list\n- [ ] item\n```"
                                     "\n\n```timer version=1 name=focus title=\"Focus\" box=25m "
                                     "break=5m\n```"}, CLIENT)
        assert form.status == 200, form
        form = form.json["post"]
        run_grant, agent, run = dispatched_run(pair, told, f"Mark {form}#focus and tick the list.")
        assert all(run), run

        keyed_twice(pair, run_grant, "answer", post=form, block="list", field="item", value=True)
        answers = rows(pair.brain, "SELECT attributed_to FROM entry WHERE "
                                   "body LIKE '%\"field\": \"item\"%' "
                                   "OR body LIKE '%\"field\":\"item\"%'")
        assert answers == [(agent,)], f"answer: {answers}"

        keyed_twice(pair, run_grant, "timer", post=form, block="focus", action="start")
        marks = rows(pair.brain, "SELECT actor, execution, caused_by FROM operational "
                                 "WHERE act = 'timer-marked'")
        assert marks == [(agent, *run)], f"timer: {marks}"


def doc_list(heading_row: str, text: str) -> set[str]:
    for line in text.splitlines():
        if line.startswith(heading_row):
            return set(re.findall(r"`([a-z_]+)`", line.split("|")[2]))
    raise AssertionError(f"{heading_row} isn't in the page")


def test_j11_the_page_s_agent_list_is_the_code_s():
    from mentis.worker import ALL_TOOLS, READ_ONLY
    page = (common.REPO / "docs" / "rust-front-restart.md").read_text(encoding="utf-8")
    keyed = doc_list("| **Key available: 5**", page)
    guarded = doc_list("| **No key, a guard read in source: 5**", page)
    unguarded = doc_list("| **No key, no guard read: 22**", page)
    tools = {tool["name"]: tool for tool in ALL_TOOLS}
    writes = set(tools) - set(READ_ONLY)
    assert keyed | guarded | unguarded == writes
    # 31: `attach_follow_up` (already a write, missing from the page) and WS-L's
    # `claim_resource` and `release_resource` (both guarded).
    # 32: and WS-I's `contribute`.
    assert len(writes) == 32
    assert not (keyed & guarded or keyed & unguarded or guarded & unguarded)
    assert {name for name in writes
            if "op" in tools[name].get("inputSchema", {}).get("properties", {})} == keyed
    assert not any("op" in tools[name]["inputSchema"].get("required", ()) for name in keyed)


def test_j12_three_unkeyed_writes_sent_twice(pair):
    session = session_grant(pair.port)
    grant = session["grant"]

    one = call(pair, grant, "open_conversation", name="J12 repeated")
    two = call(pair, grant, "open_conversation", name="J12 repeated")
    assert one[1] is None and two[1] is None
    assert one[0]["conversation"] != two[0]["conversation"]
    assert conversations_named(pair.brain, "J12 repeated") == 2
    here = one[0]["conversation"]

    trunk = call(pair, grant, "record_request", conversation=here, text="J12 trunk",
                 follow_up={"depth": 1})[0]
    one = call(pair, grant, "record_discovered_work", under=trunk["expectation"], work="J12 finding")
    two = call(pair, grant, "record_discovered_work", under=trunk["expectation"], work="J12 finding")
    assert one[1] is None and two[1] is None
    assert one[0]["expectation"] != two[0]["expectation"]
    assert rows(pair.brain, "SELECT COUNT(*) FROM entry WHERE def_name='contribution' "
                            "AND body LIKE '%J12 finding%'")[0][0] == 2
    assert rows(pair.brain, "SELECT COUNT(*) FROM operational WHERE act='work-discovered' "
                            "AND conversation=?", here)[0][0] == 2

    picked = one[0]["expectation"]
    taken = call(pair, grant, "take_up", expectation=picked, under=trunk["expectation"])
    assert taken[1] is None and taken[0]["generation"] == 1, taken
    again = call(pair, grant, "take_up", expectation=picked, under=trunk["expectation"])
    assert again[1] == (f"NotPermitted: '{picked}' is already carried; "
                        "taking it up would take it from whoever has it"), again
    raw = post_json(pair.port, "/api/worker",
                    {"corpus": str(pair.brain), "op": "take_up",
                     "args": {"expectation": picked, "under": trunk["expectation"]}},
                    {"X-Mentis-Worker": grant})
    assert raw.status == 403
    assert raw.json == {"error": f"'{picked}' is already carried; "
                                 "taking it up would take it from whoever has it",
                        "kind": "PermissionError"}
    sys.path.insert(0, str(common.code_dir()))
    import mentis.api as api
    corpus = api.open_corpus(str(pair.brain), access="read")
    try:
        carrier = api.conversations(corpus).assigned_carrier(picked)["carrier"]
    finally:
        corpus.close()
    assert carrier == session["participant"]


def moved(before: str | None, after: str) -> str | None:
    """`moved` in `apps/fluid-web/src/fluid/identity/activity.ts`, which is what a reader is."""
    if before is None or before == after:
        return None
    was, now = before.split("/", 1), after.split("/", 1)
    if was[0] != now[0]:
        return "durable"
    return "live" if was[1] != now[1] else None


def test_j13_a_reader_polling_through_the_gap(pair):
    def pulse():
        got = ask(pair.port, "GET", "/api/pulse", headers=CLIENT, wait=5.0)
        assert got.status == 200, got
        return got.json

    def beat():
        return pulse()["token"]

    for _ in range(40):  # to fresh, the state a reader would be in before the gap
        answer = pulse()
        if "live" not in answer:  # the token and the check are one answer: this reader holds fresh
            token = answer["token"]
            break
        time.sleep(0.25)
    else:
        raise AssertionError("the pulse never reached fresh")

    assert pair.stop_front().status == 200
    assert wait_gone(pair.front_pid, DRAIN_S + CUT_SLACK_S)
    with pytest.raises(OSError):
        beat()
    pair.restart_front()

    rereads = 0
    first = beat()  # the first poll after the gap has an answer
    if moved(token, first):
        rereads += 1
    token = first
    for _ in range(20):  # readers beat on; what they reread for through to fresh is the count
        time.sleep(0.25)
        answer = beat()
        if moved(token, answer):
            rereads += 1
        token = answer
    # One going into `unavailable`, one coming out: "One reread per transition", and K15.
    assert rereads == 2, f"{rereads} rereads across the gap"
    assert token.split("/", 1)[1] != "unavailable", token


def test_j14_a_post_retried_across_the_gap_under_its_composer_s_op_is_one_post(pair):
    known = conversation_named(pair.brain, "R1 known conversation")
    words = f"J14 {uuid.uuid4().hex}"
    body = {"conversation": known, "author": owner_of(pair.brain), "text": words,
            "op": uuid.uuid4().hex}

    assert pair.stop_front().status == 200
    assert wait_gone(pair.front_pid, DRAIN_S + CUT_SLACK_S)
    with pytest.raises(OSError):
        exchange(pair.port, request("GET", "/"), wait=2.0)
    pair.restart_front()

    with write_lock(pair.brain):
        thread, _ = in_thread(post_json, pair.port, "/fluid/api/posts", body, CLIENT, wait=30.0)
        time.sleep(IN_HAND_S)
        pair.kill_front()
        thread.join(30)
    time.sleep(1.0)
    pair.restart_front()
    again = post_json(pair.port, "/fluid/api/posts", body, CLIENT)
    assert again.status == 200, again
    assert rows(pair.brain, "SELECT COUNT(*) FROM entry WHERE def_name='contribution' "
                            "AND body LIKE ?", f"%{words}%")[0][0] == 1


def test_j15_through_a_planned_restart_and_a_kill_under_writes(pair, tmp_path):
    grant = session_grant(pair.port)["grant"]
    ledger = ledger_tool.Ledger(tmp_path / "ledger.jsonl")
    writer = ledger_tool.Writer(ledger)
    stopping = threading.Event()
    refused: list[str] = []
    number = [0]

    def write():
        number[0] += 1

        def send():
            answer, message = call(pair, grant, "open_conversation", name=f"J15 {number[0]}")
            if message:
                raise ConnectionError(message)
            found = rows(pair.brain, "SELECT id, seq, hash FROM entry WHERE id = ?",
                         answer["conversation"])[0]
            return (found[0], "entry", found[1], found[2])

        writer.write(send)

    def load():
        while not stopping.is_set():
            try:
                write()
            except ConnectionError as said:
                refused.append(str(said))
                time.sleep(0.05)

    thread = threading.Thread(target=load, daemon=True)
    thread.start()
    time.sleep(2)
    assert pair.stop_front().status == 200
    assert wait_gone(pair.front_pid, DRAIN_S + CUT_SLACK_S)
    pair.restart_front()
    time.sleep(2)
    pair.kill_front()
    time.sleep(0.5)
    pair.restart_front()
    time.sleep(2)
    stopping.set()
    thread.join(60)
    ledger.close()

    rows_held = ledger_tool.read(tmp_path / "ledger.jsonl")
    assert len(rows_held) > 1
    conn = sqlite3.connect(f"file:{(pair.brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        assert ledger_tool.verify(tmp_path / "ledger.jsonl", conn) == []
    finally:
        conn.close()
    for said in refused:
        assert restart_messages.decide(said, ["A", "B-sending", "B-sent", "B-reply"]), said
    assert_both_verify(pair)


# -- Live: a real MARS and a logged-in runtime. No available runtime fails the row. ---------------


LIVE_RUNTIME = {"runtime": "claude", "model": "haiku"}
LIVE_MARS_ENV = {"MARS_BACKENDS_FILE": str(pathlib.Path(os.environ.get("LOCALAPPDATA", "."))
                                           / "mars" / "backends.json")}
#: A turn long enough to be in flight through a restart, calling its tools one at a time, and
#: naming no `return_artifact`: `R1-acceptance.md`'s known limits, "J". Only Mentis tools, since
#: anything else may wait on a permission nobody here answers.
LIVE_PROMPT = (
    "Using only your Mentis tools, one call at a time and never two together, do this: call kinds, "
    "then orient, then kinds, then orient, and go on so until you have made twelve calls. If a call "
    "fails, say what it said and go on with the next. Then say how many failed, in one line."
)


def live_run(pair) -> str:
    """Ask `@r1-agent` for a real turn, as the composer does. The run it became."""
    conversation = conversation_named(pair.brain, "R1 known conversation")
    agent = rows(pair.brain, "SELECT id FROM entry WHERE def_name='participant' "
                             "AND json_extract(body,'$.alias')='@r1-agent'")[0][0]
    posted = post_json(pair.port, "/fluid/api/posts", {
        "conversation": conversation, "author": owner_of(pair.brain), "text": LIVE_PROMPT,
        "action": "ask-participant", "addressed_to": [agent],
        "dispatch": [{"participant": agent, **LIVE_RUNTIME}]}, CLIENT)
    assert posted.status == 200, posted
    assert posted.json["dispatched"] >= 1, posted
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        found = rows(pair.brain, "SELECT id FROM operational WHERE act = 'execution-started' "
                                 "AND conversation = ? ORDER BY seq DESC LIMIT 1", conversation)
        if found:
            return found[0][0]
        time.sleep(0.25)
    raise AssertionError("no run began within 60 s: the row fails with no runtime")


def live_feed(pair, run: str) -> dict:
    got = ask(pair.port, "GET", f"/api/runs/{run}/feed?after=0", headers=CLIENT, wait=30.0)
    assert got.status == 200, got
    return got.json


def wait_for_run_end(pair, run: str) -> dict:
    deadline = time.monotonic() + LIVE_RUN_LIMIT_S
    while True:
        feed = live_feed(pair, run)
        if feed.get("ended_at") or not feed.get("running"):
            return feed
        assert time.monotonic() < deadline, "the run didn't end"
        time.sleep(2)


def said_by(output) -> str:
    """The words of a tool's result, however its runtime wrapped them."""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        return "".join(said_by(part) for part in output)
    if isinstance(output, dict):
        for key in ("text", "content", "message", "error"):
            if key in output:
                return said_by(output[key])
    return json.dumps(output)


def failed_mentis_messages(feed: dict) -> list[str]:
    """Each failed Mentis tool call in a run's feed, as the agent was told it."""
    return [said_by(event.get("raw_output")) for event in feed.get("events", ())
            if event.get("kind") == "tool" and event.get("status") == "failed"
            and "mentis" in str(event.get("title")).lower()]


def judge_live_run(pair, recorder, run: str, feed: dict, python: int) -> None:
    refusals = Refusals(recorder, pair.brain / "corpus.db")
    allowed = list(restart_messages.LIST["agent_tool_errors"])
    for message in failed_mentis_messages(feed):
        assert restart_messages.decide(message, allowed, refusals), (message, refusals.failed)
    assert pair.python_pid == python and process_tree(python), "a process was restarted"
    # Execution, grant and feed the same afterwards: this feed is still the run's own and the
    # server still answers for it through the new front.
    assert live_feed(pair, run)["run"] == run
    print(f"\nthe turn ended: {feed.get('outcome')}; "
          f"{len(failed_mentis_messages(feed))} failed Mentis calls")


@pytest.mark.live
def test_j6_a_real_run_through_a_planned_front_restart(seed_copy):
    """J6's outcome doesn't need the turn to succeed: `R1-acceptance.md`."""
    with door_recorder.DoorRecorder(PRIVATE_PORT) as recorder, \
            Pair(seed_copy, mars=REAL_MARS, upstream=recorder.url, env=LIVE_MARS_ENV) as pair:
        python = pair.python_pid
        run = live_run(pair)
        time.sleep(8)
        began = time.monotonic()
        assert pair.stop_front().status == 200
        assert wait_gone(pair.front_pid, DRAIN_S + CUT_SLACK_S)
        pair.restart_front(upstream=recorder.url)
        print(f"\nJ6 gap: {time.monotonic() - began:.2f} s")
        judge_live_run(pair, recorder, run, wait_for_run_end(pair, run), python)


@pytest.mark.live
def test_j7_a_real_run_through_a_front_kill(seed_copy):
    with door_recorder.DoorRecorder(PRIVATE_PORT) as recorder, \
            Pair(seed_copy, mars=REAL_MARS, upstream=recorder.url, env=LIVE_MARS_ENV) as pair:
        python = pair.python_pid
        run = live_run(pair)
        time.sleep(8)
        began = time.monotonic()
        terminate(pair.front_pid)
        pair.restart_front(upstream=recorder.url)
        print(f"\nJ7 gap: {time.monotonic() - began:.2f} s")
        judge_live_run(pair, recorder, run, wait_for_run_end(pair, run), python)


@pytest.mark.live
def test_j16_a_real_hand_started_session_whose_bridge_starts_in_the_gap(pair, tmp_path):
    assert pair.stop_front().status == 200
    assert wait_gone(pair.front_pid, DRAIN_S + CUT_SLACK_S)

    command = [sys.executable, str(common.REPO / "tools" / "mcp_bridge.py"), "--session", "claude",
               "--server", pair.url]
    alone = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=60,
                           stdin=subprocess.DEVNULL)
    assert alone.returncode == 1
    assert restart_messages.is_bridge_exit(alone.stderr), alone.stderr

    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"mcpServers": {"mentis": {
        "command": command[0], "args": command[1:]}}}), encoding="utf-8")
    claude = shutil.which("claude")
    assert claude, "no logged-in runtime, so the row fails"
    session = subprocess.run(
        [claude, "-p", "Reply with the single word ok.", "--model", "haiku", "--strict-mcp-config",
         "--mcp-config", str(config), "--output-format", "stream-json", "--verbose", "--max-turns",
         "1", "--tools", "Read"],
        capture_output=True, text=True, encoding="utf-8", timeout=300, stdin=subprocess.DEVNULL)
    init = next(json.loads(line) for line in session.stdout.splitlines()
                if '"subtype":"init"' in line.replace(" ", ""))
    assert {"name": "mentis", "status": "failed"}.items() <= next(
        server for server in init["mcp_servers"] if server["name"] == "mentis").items()
    assert "Read" in init["tools"]
    assert not any(tool.startswith("mcp__mentis__") for tool in init["tools"])
    print(f"\nthe session exited {session.returncode}")
    pair.restart_front()

