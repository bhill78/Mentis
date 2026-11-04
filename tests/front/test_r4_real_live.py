"""R4.1's live routes from Python's real registries, on a backup-API copy: no scripted snapshot.

`tests/front/test_r4_routes.py` answers `/private/live` in Python's place, which is the only way to hold
a poll in flight. Here the poll goes through to the real route, and what it reads is what
`tools/r4/live_python.py` moved with `begin_execution` and `agents_open_run` in Python's own process. So
the row's "exact" is Python's answer against the front's, the whole wire answer, key order included.
"""
from __future__ import annotations

import json
import os
import pathlib
import socket
import sqlite3
import subprocess
import sys
import time

import pytest

from mentis.conversation import closed_starts
from tests.front.pair import CLIENT, SPARE_PORTS, Answer, _template, exchange, request, rows
from tools.r1 import common
from tools.r4 import routes_diff

PY, RELAY, FRONT, CONTROL = SPARE_PORTS[0], SPARE_PORTS[1], SPARE_PORTS[2], SPARE_PORTS[3]
SECRET = "r41-real-live"
LISTS = "/api/conversations"
ACTIVITY = "/fluid/api/conversations?activity=1&limit=24"
WORKERS_MOST = 750 * 1024  # `_LIVE_FIELDS_MOST`


class World:
    def __init__(self, brain, relay):
        self.brain, self.relay = brain, relay
        self.control = socket.create_connection(("127.0.0.1", CONTROL)).makefile("rwb")

    def do(self, **ask):
        self.control.write(json.dumps(ask).encode() + b"\n")
        self.control.flush()
        got = json.loads(self.control.readline())
        assert "error" not in got, got
        return got["ok"]

    def fetch(self, port, target) -> Answer:
        return Answer(exchange(port, request("GET", target, headers=CLIENT), wait=60))

    def front(self, target) -> tuple[Answer, bool]:
        self.relay.take()
        got = self.fetch(FRONT, target)
        return got, target in self.relay.take()

    def settled(self, limit: float = 10.0) -> None:
        """A poll sent after what the test just did has been held. Polling runs only while a pulse was
        asked for, and a poll up to two seconds old is still fresh, so ask first and wait a poll out."""
        self.fetch(FRONT, "/api/pulse")
        time.sleep(1.2)
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            if "live" not in self.fetch(FRONT, "/api/pulse").json:
                return
            time.sleep(0.05)
        raise AssertionError("never fresh")

    def exactly_python(self, target) -> Answer:
        ours, forwarded = self.front(target)
        theirs = self.fetch(PY, target)
        assert not forwarded, f"{target} was forwarded"
        assert ours.comparable == theirs.comparable, (
            target, routes_diff.first_difference(theirs.body, ours.body))
        return ours


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    brain = tmp_path_factory.mktemp("r41live") / "brain"
    routes_diff.copy_brain(common.master_dir(), brain)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("MENTIS")}
    env.update(MENTIS_BOOT_SECRET=SECRET, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    run = brain.parent / "run"
    run.mkdir()
    script = pathlib.Path(routes_diff.__file__).with_name("live_python.py")
    python = subprocess.Popen([sys.executable, str(script), str(brain), "--port", str(PY), "--control",
                               str(CONTROL), "--workspace", str(run / "ws")],
                              cwd=common.REPO, env=env, stdout=open(run / "py.log", "ab"),
                              stderr=subprocess.STDOUT)
    relay = routes_diff.Relay(RELAY, PY)
    front = None
    try:
        routes_diff.wait_port(PY)
        binary = pathlib.Path(_template()[0]).with_name("mentis-server.exe")
        front = subprocess.Popen([str(binary), str(brain), "--host", "127.0.0.1", "--port", str(FRONT),
                                  "--upstream", f"http://127.0.0.1:{RELAY}", "--dist", str(run)],
                                 env=env, stdout=open(run / "front.log", "ab"), stderr=subprocess.STDOUT)
        routes_diff.wait_port(FRONT)
        here = World(brain, relay)
        here.settled()
        yield here
    finally:
        relay.close()
        for process in (front, python):
            if process is not None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True,
                               check=False)
                process.wait(timeout=30)


def busiest(world) -> tuple[str, str]:
    conversation = rows(world.brain, "SELECT link_to FROM entry WHERE link_relation='in-conversation' "
                                     "GROUP BY link_to ORDER BY COUNT(*) DESC LIMIT 1")[0][0]
    participant = rows(world.brain, """SELECT id FROM entry WHERE def_name='participant' AND family='entry'
        AND link_relation IS NULL AND json_extract(body,'$.about')<>'the owner'
        AND json_extract(body,'$.alias') IS NOT NULL ORDER BY seq LIMIT 1""")[0][0]
    return conversation, participant


def an_open_run(world) -> dict:
    db = sqlite3.connect(f"file:{(world.brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        marks = [dict(r) for r in db.execute(
            "SELECT seq,id,act,execution,caused_by,actor,conversation,turn,at FROM operational WHERE act IN "
            "('execution-started','result-returned','delivery-failed','result-recovered') ORDER BY seq")]
    finally:
        db.close()
    done = closed_starts(marks, lambda a: a["seq"])
    still = [m for m in marks if m["act"] == "execution-started" and m["id"] not in done
             and m["actor"] and m["conversation"] and m["execution"]]
    assert still, "the copy holds no open run"
    return still[-1]


def targets(conversation) -> tuple[str, ...]:
    return (LISTS, f"/fluid/api/conversations?ids={conversation}", ACTIVITY)


def row_of(answer, conversation) -> dict:
    return next(r for r in answer.json["conversations"] if r["id"] == conversation)


def test_nothing_live_is_exactly_python(world):
    conversation, _ = busiest(world)
    for target in targets(conversation):
        world.exactly_python(target)


def test_real_executions_are_exactly_python_and_end_exactly(world):
    conversation, participant = busiest(world)
    first = world.do(do="begin", participant=participant, conversation=conversation, runtime="claude")
    second = world.do(do="begin", participant=participant, conversation=conversation, runtime="codex")
    try:
        world.settled()
        for target in targets(conversation):
            world.exactly_python(target)
        assert row_of(world.exactly_python(LISTS), conversation)["live_executions"] == 2
        row = row_of(world.exactly_python(f"/fluid/api/conversations?ids={conversation}"), conversation)
        assert row["working"] == 2 and [w["run"] for w in row["workers"]] == [None, None]
    finally:
        world.do(do="end", reference=first)
        world.do(do="end", reference=second)
    world.settled()
    for target in targets(conversation):
        world.exactly_python(target)
    assert row_of(world.exactly_python(LISTS), conversation)["live_executions"] == 0


def test_an_execution_nobody_placed_in_a_conversation_is_exactly_python(world):
    conversation, participant = busiest(world)
    begun = world.do(do="begin", participant=participant)
    try:
        world.settled()
        for target in targets(conversation):
            world.exactly_python(target)
    finally:
        world.do(do="end", reference=begun)
    world.settled()


def test_a_real_open_run_covers_its_participant_exactly(world):
    run = an_open_run(world)
    target = f"/fluid/api/conversations?ids={run['conversation']}"
    world.do(do="open_run", instance=run["execution"], run=run["id"])
    begun = world.do(do="begin", participant=run["actor"], conversation=run["conversation"])
    try:
        world.settled()
        answer = world.exactly_python(target)
        workers = row_of(answer, run["conversation"])["workers"]
        assert [w["run"] for w in workers] == [run["id"]], "one row: the run covers its execution"
        world.exactly_python(ACTIVITY)
        world.exactly_python(LISTS)
    finally:
        world.do(do="end", reference=begun)
        world.do(do="end_run", run=run["id"])
    world.settled()
    assert row_of(world.exactly_python(target), run["conversation"])["workers"] == []


def test_the_added_fields_keep_to_their_caps_at_a_long_lived_size(world):
    conversation, participant = busiest(world)
    world.do(do="retain", participant=participant, conversation=conversation, count=3600)
    begun = [world.do(do="begin", participant=participant, conversation=conversation) for _ in range(8)]
    runs = [f"opr-load{i:04d}" for i in range(64)]
    for i, run in enumerate(runs):
        world.do(do="open_run", instance=f"inst-{i}", run=run)
    try:
        measured = world.do(do="measure", times=300)
        print("\nadded fields:", measured)
        assert measured["p95_ms"] < 15, measured
        assert sum(measured["fields"].values()) < WORKERS_MOST, measured
        assert set(measured["fields"]) == {"active_executions", "run_observations"}
        world.settled()
        for target in targets(conversation):
            world.exactly_python(target)
    finally:
        for reference in begun:
            world.do(do="end", reference=reference)
        for run in runs:
            world.do(do="end_run", run=run)
    world.settled()
