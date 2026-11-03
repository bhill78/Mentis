"""R4.1's routes on a backup-API copy of the real Brain, against Python itself.

One real Python and one real front share the copy. Between them is `routes_diff.Relay`: what it saw
go up is whether the front forwarded, and it can answer `/private/live` in Python's place, which is
the only way to hold a poll in flight, or to name a live row Python's copy doesn't hold.

The ids, names and open runs in these tests are the copy's own. Every comparison is the whole wire
answer, key order included.
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from mentis.conversation import closed_starts
from tests.front.pair import CLIENT, SPARE_PORTS, Answer, _template, exchange, post_json, request, rows
from tools.r1 import common
from tools.r4 import routes_diff

PY, RELAY, FRONT, WHOLE = SPARE_PORTS[0], SPARE_PORTS[1], SPARE_PORTS[2], SPARE_PORTS[3]
SECRET = "r41-routes"

LISTS = "/api/conversations"
#: What reads no live field, for "its durable siblings go on".
DURABLE = ("/fluid/api/latest?limit=3", "/fluid/api/participants?limit=3",
           "/fluid/api/needs-you/items", "/fluid/api/collections/stream?limit=3")


class Live:
    """What the relay answers `/private/live` with, in place of Python's route."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.schema, self.boot, self.generation = 1, "boot-a", 5
        self.fields = {"active_executions": [], "run_observations": {}}
        self.held = threading.Event()
        self.hold_after_one = False

    def __call__(self):
        while self.held.is_set():
            time.sleep(0.02)
        answer = json.dumps({"schema": self.schema, "boot_id": self.boot, "generation": self.generation,
                             "live_hash": "aaaaaaaaaaaa", "taken_at": time.time(),
                             "fields": {"live_now": [], "run_marks": [], **self.fields}}).encode()
        if self.hold_after_one:
            self.hold_after_one = False
            self.held.set()
        return answer


class World:
    def __init__(self, brain, relay, live):
        self.brain, self.relay, self.live = brain, relay, live

    def fetch(self, port, target) -> Answer:
        return Answer(exchange(port, request("GET", target, headers=CLIENT), wait=60))

    def python(self, target) -> Answer:
        return self.fetch(PY, target)

    def front(self, target) -> tuple[Answer, bool]:
        self.relay.take()
        got = self.fetch(FRONT, target)
        return got, target in self.relay.take()

    def pulse(self) -> dict:
        return self.fetch(FRONT, "/api/pulse").json

    def fresh(self, limit: float = 10.0) -> None:
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            if "live" not in self.pulse():
                return
            time.sleep(0.05)
        raise AssertionError(f"never fresh: {self.pulse()}")

    def until(self, state: str, limit: float = 15.0) -> None:
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            now = self.pulse().get("live", {}).get("state")
            if now == state:
                return
            time.sleep(0.05)
        raise AssertionError(f"never {state}: {self.pulse()}")

    def answered_same(self, target) -> Answer:
        ours, forwarded = self.front(target)
        theirs = self.python(target)
        assert not forwarded, f"{target} was forwarded"
        assert ours.comparable == theirs.comparable, target
        return ours

    def forwarded_same(self, target) -> Answer:
        theirs = self.python(target)
        ours, forwarded = self.front(target)
        assert forwarded, f"{target} was not forwarded"
        assert ours.comparable == theirs.comparable, target
        return ours

    def held_after_the_record_moved(self) -> None:
        """What is held was sampled before the record moved, and is still fresh: the next poll hangs
        while a real write lands. A write slower than a snapshot's two seconds is tried again."""
        for _ in range(5):
            self.live.held.clear()
            self.fresh()
            time.sleep(0.6)
            self.pulse()
            self.live.held.set()
            self.move_the_record()
            if "live" not in self.pulse():
                return
        raise AssertionError("a write never landed inside a snapshot's two seconds")

    def durable_siblings_answer(self) -> None:
        for target in DURABLE:
            self.answered_same(target)

    def move_the_record(self) -> None:
        """A real write, through Python: a Conversation, so a list changes too."""
        owner = rows(self.brain, "SELECT id FROM entry WHERE def_name='participant' AND "
                                 "json_extract(body,'$.about')='the owner' ORDER BY seq LIMIT 1")[0][0]
        got = post_json(PY, "/fluid/api/conversations", {"author": owner, "name": "R4.1 moved"}, CLIENT)
        assert got.status == 201, got


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    brain = tmp_path_factory.mktemp("r41") / "brain"
    routes_diff.copy_brain(common.master_dir(), brain)
    live = Live()
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("MENTIS")}
    env.update(MENTIS_BOOT_SECRET=SECRET, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    run = brain.parent / "run"
    run.mkdir()
    python = subprocess.Popen([sys.executable, "-m", "mentis.web", str(brain), "--host", "127.0.0.1",
                               "--port", str(PY), "--workspace", str(run / "ws"), "--mars",
                               routes_diff.NO_MARS],
                              cwd=common.REPO, env=env, stdout=open(run / "py.log", "ab"),
                              stderr=subprocess.STDOUT)
    relay = routes_diff.Relay(RELAY, PY, live=live)
    front = None
    try:
        routes_diff.wait_port(PY)
        words = _template()
        binary = pathlib.Path(words[0]).with_name("mentis-server.exe")
        front = subprocess.Popen([str(binary), str(brain), "--host", "127.0.0.1", "--port", str(FRONT),
                                  "--upstream", f"http://127.0.0.1:{RELAY}", "--dist", str(run)],
                                 env=env, stdout=open(run / "front.log", "ab"), stderr=subprocess.STDOUT)
        routes_diff.wait_port(FRONT)
        yield World(brain, relay, live)
    finally:
        relay.close()
        for process in (front, python):
            if process is not None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True,
                               check=False)
                process.wait(timeout=30)


@pytest.fixture(autouse=True)
def calm(world):
    world.live.reset()
    world.relay.blocked = False
    world.fresh()
    yield
    world.live.reset()
    world.relay.blocked = False


#: `PythonGone`, whichever way a connection to a Python that isn't answering ends.
PYTHON_GONE = ("Python is not answering behind this front, so this request did not reach it and nothing was done.",
               "Python stopped with this request in hand, so the result is unknown. It may still have done it: "
               "check the record before repeating it.")


# -- what is held on the copy --------------------------------------------------------------------


def busiest(world) -> tuple[str, str, str]:
    """A Conversation with something in it, and a real participant and their alias."""
    conversation = rows(world.brain, "SELECT link_to FROM entry WHERE link_relation='in-conversation' "
                                     "GROUP BY link_to ORDER BY COUNT(*) DESC LIMIT 1")[0][0]
    participant, alias = rows(world.brain, """SELECT id, json_extract(body,'$.alias') FROM entry
        WHERE def_name='participant' AND family='entry' AND link_relation IS NULL
        AND json_extract(body,'$.about')<>'the owner' ORDER BY seq LIMIT 1""")[0]
    return conversation, participant, alias


def execution(conversation, participant) -> dict:
    return {"reference": "live-r41", "participant": participant, "conversation": conversation,
            "runtime": "claude", "persona": None, "for_expectation": None}


def an_open_run(world) -> dict | None:
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
             and m["actor"] and m["conversation"]]
    return still[-1] if still else None


def observation(run: dict) -> dict:
    return {"run": run["id"], "instance": run["execution"], "opened_at": run["at"],
            "performing_since": run["at"], "last_event": None, "ended_at": None, "stop": None,
            "outcome": None, "permission": None, "permissions": [], "activity": "Reading",
            "activity_at": run["at"], "running": True}


def with_row(body: bytes, conversation: str, change) -> bytes:
    doc = json.loads(body)
    assert json.dumps(doc).encode() == body, "Python's own answer is this dump, so a change to it is"
    for row in doc["conversations"]:
        if row["id"] == conversation:
            change(row)
    return json.dumps(doc).encode()


# -- parity --------------------------------------------------------------------------------------


def test_every_family_on_the_wire(world):
    """The differential's requests, sampled; `tools/r4/routes_diff.py run` asks more for a report."""
    db = sqlite3.connect(f"file:{(world.brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    corpus = routes_diff.Corpus(db, 4, world.python)
    answered = {}
    try:
        for family in routes_diff.EVERY:
            seen = set()
            for target in corpus.family(family):
                if target in seen:
                    continue
                seen.add(target)
                world.pulse()
                theirs = world.python(target)
                ours, forwarded = world.front(target)
                assert ours.comparable == theirs.comparable, target
                answered[family] = answered.get(family, 0) + (not forwarded)
    finally:
        db.close()
    # Each of these has a case Rust answers. A response set's state and its list are Python's.
    assert set(routes_diff.EVERY) - set(answered) <= {"response-sets", "response-set"}, answered


def test_a_fresh_empty_snapshot_answers_every_live_route_exactly(world):
    world.answered_same(LISTS)
    conversation, _, _ = busiest(world)
    world.answered_same(f"/fluid/api/conversations?ids={conversation}")
    world.answered_same("/fluid/api/conversations?activity=1&limit=24")


def test_a_fresh_execution_is_counted_exactly(world):
    conversation, participant, _ = busiest(world)
    world.live.fields["active_executions"] = [execution(conversation, participant)]
    world.fresh()
    time.sleep(0.7)
    ours, forwarded = world.front(LISTS)
    assert not forwarded
    wanted = with_row(world.python(LISTS).body, conversation,
                      lambda row: row.update(live_executions=1))
    assert ours.body == wanted


def test_a_fresh_execution_is_a_worker_exactly(world):
    conversation, participant, _ = busiest(world)
    alias = next(p["alias"] for p in world.python("/fluid/api/participants?limit=500").json["participants"]
                 if p["id"] == participant)
    world.live.fields["active_executions"] = [execution(conversation, participant)]
    world.fresh()
    time.sleep(0.7)
    target = f"/fluid/api/conversations?ids={conversation}"
    ours, forwarded = world.front(target)
    assert not forwarded
    worker = {"run": None, "participant": participant, "alias": alias.lstrip("@"), "turn": None,
              "since": None}
    wanted = with_row(world.python(target).body, conversation,
                      lambda row: row.update(working=1, workers=[worker]))
    assert ours.body == wanted


def test_a_held_open_run_is_a_worker_exactly(world):
    run = an_open_run(world)
    assert run, "the copy holds no open run to observe"
    world.live.fields["run_observations"] = {run["id"]: observation(run)}
    world.fresh()
    time.sleep(0.7)
    target = f"/fluid/api/conversations?ids={run['conversation']}"
    ours, forwarded = world.front(target)
    assert not forwarded
    alias = next(p["alias"] for p in world.python("/fluid/api/participants?limit=500").json["participants"]
                 if p["id"] == run["actor"])
    worker = {"run": run["id"], "participant": run["actor"], "alias": alias.lstrip("@"),
              "turn": run["turn"], "since": run["at"]}
    wanted = with_row(world.python(target).body, run["conversation"],
                      lambda row: row.update(working=1, workers=[worker]))
    assert ours.body == wanted


# -- what isn't fresh forwards -------------------------------------------------------------------


LIVE_ROUTES = (LISTS, "/fluid/api/conversations?activity=1&limit=7")


def test_stale_forwards_and_durable_siblings_answer(world):
    world.live.held.set()
    world.until("stale")
    for target in LIVE_ROUTES:
        world.forwarded_same(target)
    world.durable_siblings_answer()


def test_resume_after_idle_forwards_until_its_first_good_poll(world):
    # Polling ends 5 s after the last pulse asked, and its last good poll is then 2 s from stale.
    world.live.held.set()
    time.sleep(8.0)
    assert world.pulse()["live"]["state"] == "stale"
    for target in LIVE_ROUTES:
        world.forwarded_same(target)
    world.live.held.clear()
    world.fresh()
    world.answered_same(LISTS)


@pytest.mark.parametrize("change", ["boot", "generation", "schema"])
def test_a_discarded_snapshot_forwards_before_it_would_go_stale(world, change):
    live = world.live
    live.hold_after_one = True
    if change == "boot":
        live.boot = "boot-b"
    elif change == "generation":
        live.generation = 1
    else:
        live.schema = 99
    world.until("unavailable", limit=2.0)
    for target in LIVE_ROUTES:
        world.forwarded_same(target)
    world.durable_siblings_answer()
    live.schema = 1
    live.held.clear()
    world.fresh()
    world.answered_same(LISTS)


def test_a_missing_field_forwards_what_needs_it_and_nothing_else(world):
    conversation, _, _ = busiest(world)
    ids = f"/fluid/api/conversations?ids={conversation}"
    world.live.fields = {"active_executions": []}
    time.sleep(0.8)
    world.fresh()
    world.answered_same(LISTS)  # the count reads no run observations
    world.forwarded_same(ids)
    world.forwarded_same("/fluid/api/conversations?activity=1&limit=7")
    world.durable_siblings_answer()
    world.live.fields = {"run_observations": {}}
    time.sleep(0.8)
    world.fresh()
    world.forwarded_same(LISTS)
    world.forwarded_same(ids)
    world.durable_siblings_answer()


def test_python_unavailable_past_ten_seconds_then_a_good_poll_restores_exact_answers(world):
    world.live.held.set()
    world.relay.blocked = True
    world.until("unavailable", limit=15.0)
    for target in LIVE_ROUTES:
        got, _ = world.front(target)
        assert got.status == 503, got
        assert got.json["error"] in PYTHON_GONE, got
    for target in DURABLE:
        assert world.fetch(FRONT, target).status == 200, target
    world.relay.blocked = False
    world.live.held.clear()
    world.fresh()
    for target in LIVE_ROUTES:
        world.answered_same(target)


# -- coherence -----------------------------------------------------------------------------------


def test_an_end_landing_while_a_poll_is_in_flight_forwards(world):
    conversation, participant, _ = busiest(world)
    world.live.fields["active_executions"] = [execution(conversation, participant)]
    world.fresh()
    for target in (LISTS, f"/fluid/api/conversations?ids={conversation}"):
        world.held_after_the_record_moved()
        ours, forwarded = world.front(target)
        assert forwarded, target
        assert ours.comparable == world.python(target).comparable, target


def test_a_moved_record_whose_overlay_changes_nothing_does_not_forward(world):
    for target in (LISTS, "/fluid/api/conversations?activity=1&limit=7"):
        world.held_after_the_record_moved()
        world.answered_same(target)


def test_the_correcting_reread_after_the_end_window(world):
    conversation, participant, _ = busiest(world)
    live = world.live
    # The execution is live and the record says so: the count is the overlay's.
    live.fields["active_executions"] = [execution(conversation, participant)]
    world.fresh()
    time.sleep(0.7)
    ours, forwarded = world.front(LISTS)
    assert not forwarded
    assert next(r for r in ours.json["conversations"] if r["id"] == conversation)["live_executions"] == 1
    # `end_execution`, then the durable end, with a poll still older than it: forward, and be right.
    world.held_after_the_record_moved()
    ours = world.forwarded_same(LISTS)
    assert next(r for r in ours.json["conversations"] if r["id"] == conversation)["live_executions"] == 0
    # A poll after it already has the right count.
    live.fields["active_executions"] = []
    live.held.clear()
    world.fresh()
    time.sleep(0.7)
    world.answered_same(LISTS)


def test_nothing_was_written_by_reading(world):
    query = ("SELECT (SELECT MAX(seq) FROM entry), (SELECT MAX(seq) FROM operational),"
             " (SELECT MAX(seq) FROM delivery)")
    before = rows(world.brain, query)
    for target in (*LIVE_ROUTES, *DURABLE):
        world.fetch(FRONT, target)
    assert rows(world.brain, query) == before
