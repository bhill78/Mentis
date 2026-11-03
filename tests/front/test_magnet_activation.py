"""A Magnet's manual activation across the real seam: the real Rust front's artifact bytes, real Python's
checks and record, on a disposable copy of BRAIN-SEED. `docs/magnets/M1-contract.md`, "Manual activation".

Most of this asks the launcher's own front, which talks to Python directly. What needs an exact moment asks
a second real front through `Relay`, which sits between it and Python on the private port and stops, passes,
or loses one whole exchange. The relay carries bytes and changes none unless a row says so, so what Python
answers is what real Python said of what real Rust sent.

What can't be arranged here isn't faked: `docs/magnets/M1-contract.md`'s last moment before a commit's first
byte, a client leaving during the read, every source busy, a real 25 MiB page and a process dying inside the
transaction are held by the tests named in the report, on one side at a time.
"""

from __future__ import annotations

import base64
import collections
import concurrent.futures
import dataclasses
import hashlib
import json
import os
import pathlib
import shutil
import socket
import stat
import subprocess
import threading
import time

import pytest

from mentis.magnet.schema import INFORMATION_TYPES
from tests.front.pair import (CLIENT, SPARE_PORTS, Answer, Pair, advance, ask, exchange, post_json, request,
                              rows, session_grant)
from tools.r1 import common

PORT, STAGED_PORT, THIRD_PORT, DOOMED_PORT, ROLLED_BACK_PORT = list(SPARE_PORTS)[:5]
SIDE = common.REPO / "crates" / "mentis-rules" / "tests" / "support" / "python_side.py"
TABLE = common.REPO / "crates" / "mentis-server" / "route-table.default.json"
FIXTURES = common.REPO / "tests" / "fixtures" / "magnet-conformance" / "activation"
BIGGEST = ("SELECT l.link_to FROM entry l WHERE l.link_relation = 'in-conversation' "
           "GROUP BY l.link_to ORDER BY COUNT(*) DESC")
JSON_HEADERS = {**CLIENT, "Content-Type": "application/json"}
#: Longer than any exchange here takes, and only ever waited out by a test that has already failed.
PATIENCE = 60


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


REFUSALS, DOOR, BODIES = _load("refusals.json"), _load("door.json"), _load("public_bodies.json")
DEFINITIONS, RESULTS = _load("definitions.json"), _load("results.json")
MAGNET = DEFINITIONS["magnet"]
#: The Conversation the fixtures' definitions name, which this Brain doesn't hold.
FIXTURE_CONVERSATION = "ent-2865e11386f6"


def _ids(table):
    return [row["id"] for row in table]


# -- the relay ------------------------------------------------------------------------------------


class Gate:
    """Stops an exchange at one place until told. `reached` says it has got there."""

    def __init__(self):
        self.reached, self.go = threading.Event(), threading.Event()

    def __call__(self):
        self.reached.set()
        self.go.wait(PATIENCE)

    def arrived(self):
        assert self.reached.wait(PATIENCE), "that exchange never came"


@dataclasses.dataclass
class Plan:
    """What the relay does with the next exchange of a step. Left as it is, it carries it whole."""
    asked: object = None           # called once the front has sent it all, before Python hears of it
    to_python: bool = True         # False: Python never hears of it
    midway: object = None          # Python has the head and half the body while this is called
    answered: object = None        # called once Python has answered, before the front hears of it
    answer: object = None          # what the front is given of Python's bytes. None from it: nothing
    sent: object = None            # what Python is given of the front's body, its head as it came


@dataclasses.dataclass
class Heard:
    step: str
    magnet: str
    head: bytes
    body: bytes
    answer: bytes = b""


class Relay:
    """A loopback server in `--upstream`'s place. Each private activation request comes on a connection of
    its own (`front/activate.rs`), and anything else is piped as it is."""

    def __init__(self, python_port: int):
        self.python_port = python_port
        self.plans = {"preflight": collections.deque(), "commit": collections.deque()}
        self.heard: list[Heard] = []
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def on(self, step: str, **plan) -> None:
        self.plans[step].append(Plan(**plan))

    def of(self, step: str) -> list[Heard]:
        return [one for one in self.heard if one.step == step]

    def close(self) -> None:
        self.listener.close()

    def _serve(self) -> None:
        while True:
            try:
                front, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(front,), daemon=True).start()

    def _one(self, front: socket.socket) -> None:
        with front:
            try:
                self._carry(front)
            except OSError:
                pass

    def _carry(self, front: socket.socket) -> None:
        got = b""
        while b"\r\n\r\n" not in got:
            more = front.recv(1 << 16)
            if not more:
                return
            got += more
        head, _, body = got.partition(b"\r\n\r\n")
        words = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ")
        parts = words[1].split("/") if len(words) > 1 else []
        if len(parts) != 6 or parts[1:3] != ["private", "magnets"] or parts[4] != "activate":
            return self._pipe(front, got)
        length = next(int(line.split(b":", 1)[1]) for line in head.split(b"\r\n")[1:]
                      if line.lower().startswith(b"content-length:"))
        while len(body) < length:
            more = front.recv(1 << 20)
            if not more:
                return
            body += more
        heard = Heard(parts[5], parts[3], head, body)
        self.heard.append(heard)
        plans = self.plans[heard.step]
        plan = plans.popleft() if plans else Plan()
        if plan.asked:
            plan.asked()
        if not plan.to_python:
            return
        if plan.sent:
            body = plan.sent(body)
        with socket.create_connection(("127.0.0.1", self.python_port), timeout=PATIENCE) as python:
            wire = head + b"\r\n\r\n"
            if plan.midway:
                python.sendall(wire + body[:length // 2])
                plan.midway()
                python.sendall(body[length // 2:])
            else:
                python.sendall(wire + body)
            while more := python.recv(1 << 20):
                heard.answer += more
        if plan.answered:
            plan.answered()
        given = plan.answer(heard.answer) if plan.answer else heard.answer
        if given:
            front.sendall(given)

    def _pipe(self, front: socket.socket, first: bytes) -> None:
        with socket.create_connection(("127.0.0.1", self.python_port), timeout=PATIENCE) as python:
            python.sendall(first)

            def back():
                try:
                    while more := python.recv(1 << 20):
                        front.sendall(more)
                except OSError:
                    pass
                finally:
                    try:
                        front.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass

            threading.Thread(target=back, daemon=True).start()
            while more := front.recv(1 << 20):
                python.sendall(more)
            python.shutdown(socket.SHUT_WR)


# -- the world ------------------------------------------------------------------------------------


@dataclasses.dataclass
class World:
    pair: Pair
    brain: pathlib.Path
    relay: Relay
    seed: pathlib.Path
    who: str
    other: str
    a_post: str
    biggest: list
    seed_digest: dict
    made: int = 0

    @property
    def port(self) -> int:
        return self.pair.port

    def mid(self) -> str:
        self.made += 1
        return f"mag-d{self.made:04d}"

    def op(self) -> str:
        self.made += 1
        return f"key-{self.made:04d}"

    def path(self, magnet: str) -> pathlib.Path:
        return self.brain / "presentation" / "magnets" / f"{magnet}.json"

    def write(self, magnet: str, what) -> bytes:
        raw = what if isinstance(what, bytes) else json.dumps(what).encode("utf-8")
        self.path(magnet).parent.mkdir(parents=True, exist_ok=True)
        self.path(magnet).write_bytes(raw)
        return raw

    def magnet(self, *sources, **more) -> str:
        """A definition that can run, on the Brain's biggest Conversation unless told."""
        mid = self.mid()
        self.write(mid, definition(mid, list(sources) or [self.biggest[0]], **more))
        return mid

    def activate(self, magnet: str, op: str | None = None, *, port: int | None = None,
                 author: str | None = None) -> Answer:
        return post_json(port or self.port, f"/fluid/api/magnets/{magnet}/activate",
                         {"author": author or self.who, "op": op or self.op()}, CLIENT)

    def held_bytes(self, digest: str) -> bytes:
        return (self.brain / "artifacts" / "sha256" / digest[:2] / digest).read_bytes()

    def acts(self, act: str, *, turn: str | None = None, conversation: str | None = None) -> list:
        found = rows(self.brain, "SELECT actor, conversation, turn, about, detail FROM operational "
                                 "WHERE act = ?", act)
        return [dict(actor=a, conversation=c, turn=t, about=json.loads(b), detail=json.loads(d))
                for a, c, t, b, d in found
                if (turn is None or t == turn) and (conversation is None or c == conversation)]

    def outcomes(self, op: str) -> list:
        return [one for one in self.acts("operation-keyed") if one["detail"]["op"] == op]

    def claims(self, magnet: str) -> list:
        return [one for one in self.acts("own-conversation-claimed")
                if magnet in json.dumps(one["detail"])]


def definition(mid: str, sources: list, **more) -> dict:
    return {"id": mid, "sources": [source if isinstance(source, dict) else
                                   {"kind": "conversation", "conversation": source}
                                   for source in sources],
            "selection": {"informationTypes": ["post"]}, "collection": {"mode": "one-time"},
            "synthesis": {"mode": "manual"},
            "notifications": {"newItems": False, "changes": False, "failures": False},
            "presentation": {"renderer": "disc"}, "activation": {"mode": "manual"},
            "processing": {"operations": [{"op": "extract"}]}, "schema_version": 1, **more}


def _of_kind(brain, kind: str) -> list[str]:
    """Each such entry, oldest first. A Kind's own definition has a `def-` id and isn't one."""
    return [r[0] for r in rows(brain, "SELECT id FROM entry WHERE def_name = ? AND id LIKE 'ent-%' "
                                      "ORDER BY seq", kind)]


@pytest.fixture(scope="module")
def w(brain_seed, tmp_path_factory):
    before = common.tree_digest(brain_seed)
    brain = tmp_path_factory.mktemp("activation") / "brain"
    shutil.copytree(brain_seed, brain)
    done = subprocess.run([str(common.venv_python()), str(SIDE), "change", str(brain)],
                          cwd=common.REPO, capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONPATH": str(common.REPO),
                               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    assert done.returncode == 0, done.stderr
    people = _of_kind(brain, "participant")
    biggest = [r[0] for r in rows(brain, BIGGEST)]
    a_post = _of_kind(brain, "contribution")[0]
    with Pair(brain, port=PORT) as pair:
        relay = Relay(pair.private_port)
        try:
            with pair.second_front("127.0.0.1", STAGED_PORT, upstream=relay.url):
                yield World(pair, brain, relay, brain_seed, people[0], people[1], a_post, biggest, before)
        finally:
            relay.close()
    assert common.tree_digest(brain_seed) == before, "the seed itself changed"


@pytest.fixture(autouse=True)
def nothing_left_planned(w):
    w.relay.heard.clear()
    yield
    assert not any(w.relay.plans.values()), "a plan nothing came for"


def later(what):
    """`what()` on its own thread, as a client that is waiting for its answer."""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    done = pool.submit(what)
    pool.shutdown(wait=False)
    return done


def leaving_client(port: int, magnet: str, author: str, op: str) -> socket.socket:
    """A client that has asked, and can go by closing what this returns."""
    body = json.dumps({"author": author, "op": op}).encode()
    sock = socket.create_connection(("127.0.0.1", port), timeout=PATIENCE)
    sock.sendall(request("POST", f"/fluid/api/magnets/{magnet}/activate", body=body, headers=JSON_HEADERS))
    return sock


def artifact_of(heard: Heard) -> dict:
    return json.loads(heard.body)


def without_the_moment(body: dict) -> dict:
    return {k: v for k, v in body.items() if k not in ("replayed", "cursor")}


def assert_same_but_the_moment(first: Answer, replay: Answer) -> None:
    """A replay is the first answer's bytes but for its last two fields (`results.json`)."""
    a, b = first.json, replay.json
    assert list(a) == list(b)
    assert a["replayed"] is False and b["replayed"] is True
    assert json.dumps(without_the_moment(a)) == json.dumps(without_the_moment(b))
    assert first.body[:first.body.rindex(b'"replayed"')] == replay.body[:replay.body.rindex(b'"replayed"')]


# -- real Rust bytes, accepted by Python's checks ---------------------------------------------------


def test_a_first_commit_is_real_rust_bytes_held_exactly_and_its_record_is_the_whole_set(w):
    mid = w.magnet()
    raw = w.path(mid).read_bytes()
    op = w.op()
    before = advance(w.brain)
    got = w.activate(mid, op, port=STAGED_PORT)
    assert got.status == 201, got
    body = got.json

    # What Rust sent is what Python holds, and the digest of both is what was said.
    [commit] = w.relay.of("commit")
    assert commit.answer.startswith(b"HTTP/1.")
    digest = hashlib.sha256(commit.body).hexdigest()
    assert body["artifact"] == {"ref": body["artifact"]["ref"], "digest": digest, "size": len(commit.body),
                                "media_type": "application/json"}
    assert f"X-Mentis-Artifact-SHA256: {digest}".encode() in commit.head
    assert w.held_bytes(digest) == commit.body

    # The artifact's own form: `json.dumps`'s default, members in the contract's order.
    art = artifact_of(commit)
    assert json.dumps(art).encode("utf-8") == commit.body
    assert list(art) == ["format", "version", "mode", "magnet", "request", "definition", "operation", "page"]
    assert art["request"] == {"author": w.who, "op": op, "identity": {"route": "fluid-magnet-activate",
                                                                      "magnet": mid}}
    # The definition's exact bytes, whose digest anybody can recompute.
    assert art["definition"]["raw"].encode("utf-8") == raw
    assert art["definition"]["sha256"] == hashlib.sha256(raw).hexdigest()
    # What `mentis.magnet.read` makes of it, which leaves the file's own `schema_version` behind.
    assert art["definition"]["value"] == {k: v for k, v in json.loads(raw).items() if k != "schema_version"}
    assert art["operation"] == {"index": 0, "op": "extract", "mode": "m1-page", "name": None, "options": {}}

    # The public answer.
    assert list(body) == [*RESULTS["complete"]["stored"], "replayed", "cursor"]
    assert body["state"] == "complete" and body["replayed"] is False
    assert body["conversation_created"] is True
    assert body["operation"] == {"index": 0, "op": "extract", "mode": "m1-page", "name": None}
    results = art["page"]["sources"][0]["results"]
    assert results and body["page"] == {"cursor": art["page"]["cursor"], "sources": 1, "results": len(results),
                                        "statuses": {"ok": 1, "partial": 0, "busy": 0, "unavailable": 0},
                                        "kept": []}
    assert advance(w.brain) > before

    # The record: Turn, Admission, `turn-said`, `magnet-extracted`, `produced`, the key, the claim.
    cid, post, adm = body["conversation"], body["post"], body["artifact"]["ref"]
    assert adm.startswith("adm-")
    [(kind, turn_body)] = rows(w.brain, "SELECT def_name, body FROM entry WHERE id = ?", post)
    assert kind == "contribution"
    parts = json.loads(turn_body)["parts"]
    assert [p["type"] for p in parts] == ["text", "file"]
    assert parts[1]["ref"] == adm and parts[1]["media_type"] == "application/json"
    assert len(parts[0]["text"]) < 200, "the page isn't copied into its text"
    [in_conversation] = rows(w.brain, "SELECT link_to FROM entry WHERE link_from = ? "
                                      "AND link_relation = 'in-conversation'", post)
    assert in_conversation[0] == cid
    [(admitted,)] = rows(w.brain, "SELECT body FROM entry WHERE id = ?", adm)
    admitted = json.loads(admitted)
    assert admitted["locator"] == f"sha256:{digest}" and admitted["source"] == f"magnet:{mid}"
    assert admitted["content"] == "held" and admitted["envelope"]["size"] == len(commit.body)
    [said] = w.acts("turn-said", turn=post)
    assert said["detail"] == {"action": "record-only"} and said["conversation"] == cid
    [made] = w.acts("magnet-extracted", turn=post)
    assert made["actor"] == w.who and made["conversation"] == cid and adm in made["about"]
    assert made["detail"] == {
        "magnet": mid, "mode": "m1-page", "operation": {"index": 0, "name": None},
        "definition_sha256": hashlib.sha256(raw).hexdigest(),
        "page": {"cursor": art["page"]["cursor"], "state": "complete", "results": len(results),
                 "statuses": body["page"]["statuses"]},
        "artifact": {"ref": adm, "digest": digest, "size": len(commit.body)}}
    links = rows(w.brain, "SELECT link_from FROM entry WHERE link_to = ? AND link_relation = 'produced'", adm)
    assert len(links) == 1
    [act_id] = rows(w.brain, "SELECT id FROM operational WHERE act = 'magnet-extracted' AND turn = ?", post)
    assert links[0][0] == act_id[0]
    [keyed] = w.outcomes(op)
    assert json.dumps(keyed["detail"]["result"], sort_keys=True) == json.dumps(without_the_moment(body),
                                                                               sort_keys=True)
    assert keyed["conversation"] == cid
    assert len(w.claims(mid)) == 1
    # After the commit, the file. Nothing starts from a record-only Turn.
    assert json.loads(w.path(mid).read_text(encoding="utf-8"))["conversation"] == cid
    assert w.acts("expectation-recorded", conversation=cid) == []


def test_a_replay_is_the_first_answers_bytes_and_writes_nothing(w):
    mid, op = w.magnet(), w.op()
    first = w.activate(mid, op)
    assert first.status == 201, first
    at = advance(w.brain)
    w.relay.heard.clear()
    replay = w.activate(mid, op, port=STAGED_PORT)
    assert replay.status == 200, replay
    assert_same_but_the_moment(first, replay)
    assert advance(w.brain) == at
    assert not w.relay.of("commit"), "a replay is decided at preflight, and nothing is read or committed"
    assert replay.json["page"]["cursor"] == first.json["page"]["cursor"]
    # A write elsewhere moves the top-level cursor and leaves the frozen page.
    assert w.activate(w.magnet()).status == 201
    again = w.activate(mid, op)
    assert again.json["cursor"] != first.json["cursor"]
    assert_same_but_the_moment(first, again)


def test_a_replay_answers_after_the_definition_changed_and_after_it_is_deleted(w):
    mid, op = w.magnet(), w.op()
    first = w.activate(mid, op)
    assert first.status == 201, first
    w.write(mid, definition(mid, [w.biggest[1]], activation={"mode": "scheduled", "schedule": "0 0 * * *"}))
    at = advance(w.brain)
    assert_same_but_the_moment(first, w.activate(mid, op))
    w.path(mid).unlink()
    assert_same_but_the_moment(first, w.activate(mid, op))
    assert advance(w.brain) == at


def test_a_key_used_for_another_magnet_is_refused_and_writes_nothing(w):
    used, other, op = w.magnet(), w.magnet(), w.op()
    assert w.activate(used, op).status == 201
    at = advance(w.brain)
    got = w.activate(other, op, port=STAGED_PORT)
    assert got.status == 422, got
    assert got.json["refused"] is True and op in got.body.decode()
    assert not w.relay.of("commit")
    assert advance(w.brain) == at
    # The key is the author's: another's same word is another activation.
    assert w.activate(other, op, author=w.other).status == 201


@pytest.mark.parametrize("selection", [
    {},
    {"informationTypes": list(INFORMATION_TYPES)},
    {"informationTypes": ["post", "file"], "dates": {"after": "2020-01-01", "before": "2099-01-01T12:00:00Z"},
     "phrases": ["x"]},
], ids=["none", "every-type", "dates-and-a-kept-facet"])
def test_every_conversation_in_the_brain_passes_python_s_page_checks(w, selection):
    """The seam the stand-in hid. Every Conversation of a Brain with edits, deletions, links and files, read
    by real Rust. A disagreement would be 502 at preflight or `OutcomeUnknown` after a 502 at commit."""
    every = _of_kind(w.brain, "conversation")
    assert every
    states = collections.Counter()
    for conversation in every:
        mid = w.magnet(conversation, selection=selection)
        got = w.activate(mid, port=STAGED_PORT)
        assert got.status in (201, 422), (conversation, got)
        if got.status == 422:
            assert got.json["reason"]["code"] == "no-readable-source", got
        states[got.json.get("state", "refused")] += 1
    assert states["complete"] + states["partial"] > 0, states
    assert "complete" not in states or "phrases" not in selection, states
    errors = [h for h in w.relay.of("commit") if b'"internal-protocol-error"' in h.answer]
    assert not errors, [h.answer[:400] for h in errors]
    # That the shapes the stand-in couldn't show were really here.
    seen = collections.Counter()
    for commit in w.relay.of("commit"):
        for source in artifact_of(commit)["page"]["sources"]:
            seen["status " + source["status"]] += 1
            seen["next"] += source["next"] is not None
            for result in source["results"]:
                seen["kind " + result["kind"]] += 1
                seen["via " + str(result.get("via"))] += 1
    assert seen["via home"] and seen["via linked"] and seen["next"], seen
    assert seen["kind post"] and sum(n for name, n in seen.items() if name.startswith("kind ")) > seen["kind post"], seen


def test_all_of_a_brain_s_sources_on_one_page_and_a_source_with_more_to_read(w):
    every = _of_kind(w.brain, "conversation")[:20]
    mid = w.magnet(*every, selection={})
    got = w.activate(mid, port=STAGED_PORT)
    assert got.status == 201, got
    page = artifact_of(w.relay.of("commit")[0])["page"]
    assert [s["source"]["conversation"] for s in page["sources"]] == every
    assert got.json["page"]["sources"] == len(every)
    assert got.json["page"]["results"] == sum(len(s["results"]) for s in page["sources"])


def test_text_rust_has_to_escape_survives_to_the_held_bytes(w):
    conversation = w.biggest[1]
    words = 'café σασ \U0001f9f2 "quoted" back\\slash   line\ttab \x7f'
    said = post_json(w.port, "/fluid/api/posts", {"conversation": conversation, "author": w.who,
                                                  "parts": [{"type": "text", "text": words}]}, CLIENT)
    assert said.status == 200, said
    # And a definition that isn't ASCII, with line endings of its own: the bytes are the bytes.
    mid = w.mid()
    text = json.dumps(definition(mid, [conversation], processing={"operations": [
        {"op": "extract", "name": "Léo \U0001f9f2"}]}), ensure_ascii=False, indent=1)
    raw = w.write(mid, text.replace("\n", "\r\n").encode("utf-8"))
    got = w.activate(mid, port=STAGED_PORT)
    assert got.status == 201, got
    [commit] = w.relay.of("commit")
    art = artifact_of(commit)
    assert commit.body.isascii() and json.dumps(art).encode() == commit.body
    assert art["definition"]["raw"].encode("utf-8") == raw
    assert art["definition"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert art["operation"]["name"] == "Léo \U0001f9f2"
    assert got.json["operation"]["name"] == "Léo \U0001f9f2"
    assert w.held_bytes(got.json["artifact"]["digest"]) == commit.body


def test_a_page_comes_to_partial_beside_an_unavailable_source_and_a_kept_facet(w):
    other = next(row for row in DEFINITIONS["executable"]
                 if row["id"] == "unsupported-source-beside-conversation")["definition"]["sources"][-1]
    assert other["kind"] != "conversation"
    mid = w.magnet(w.biggest[0], other)
    got = w.activate(mid, port=STAGED_PORT)
    assert got.status == 201, got
    assert got.json["state"] == "partial"
    assert got.json["page"]["statuses"] == {"ok": 1, "partial": 0, "busy": 0, "unavailable": 1}
    page = artifact_of(w.relay.of("commit")[0])["page"]
    assert page["sources"][1]["status"] == "unavailable" and page["sources"][1]["results"] == []

    kept = w.magnet(w.biggest[0], selection={"informationTypes": ["post"], "phrases": ["x"]})
    got = w.activate(kept)
    assert got.status == 201, got
    assert got.json["state"] == "partial" and [k["facet"] for k in got.json["page"]["kept"]] == ["phrases"]
    assert got.json["page"]["statuses"]["ok"] == 1


def test_every_kind_of_source_and_every_kept_facet_as_the_file_spells_them(w):
    """Rust reads the file's own bytes and Python checks them against what it made of them, so whatever one
    side could normalize, reorder or re-spell shows here as a 502."""
    mid = w.mid()
    made = definition(mid, [
        {"conversation": w.biggest[0], "kind": "conversation"},
        {"brain": "ent-000000000001", "kind": "brain"},
        {"kind": "connector", "connector": "ent-000000000002", "location": " café 🧲 "},
        {"kind": "web", "domain": "examplé.test"},
        {"kind": "web", "url": "https://example.test/a b?x=σ#\"q\"", "domain": "example.test"},
        {"kind": "other", "type": "note", "ref": "back" + chr(92) + "slash / \"quoted\""},
        {"kind": "agent-results", "runtime": "claude"},
        {"kind": "agent-results", "conversation": w.biggest[0]},
        {"kind": "file", "collection": "ent-000000000003", "path": chr(92).join(["C:", "a", "b é.txt"])},
        {"kind": "database", "table": "t", "collection": "ent-000000000004"},
    ], selection={
        "criteria": "  spaced é  ", "phrases": ["🧲", " x "], "topics": ["ent-000000000005"],
        "informationTypes": ["post"], "dates": {"after": "2020-01-01", "before": "2099-01-01T12:00:00+02:00"},
        "filters": {"whole": 1, "negative": -2, "half": 1.5, "big": 1e15, "tiny": 1e-7, "thousand": 1e3,
                    "zero": -0.0, "yes": True, "no": False, "words": "café", "none": ""}})
    raw = w.write(mid, json.dumps(made, ensure_ascii=False, indent="	").encode("utf-8"))
    got = w.activate(mid, port=STAGED_PORT)
    assert got.status == 201, got
    assert got.json["state"] == "partial"
    assert got.json["page"]["statuses"]["ok"] == 1 and got.json["page"]["statuses"]["unavailable"] >= 8
    assert {k["facet"] for k in got.json["page"]["kept"]} == {"criteria", "phrases", "topics", "filters"}
    art = artifact_of(w.relay.of("commit")[0])
    assert art["definition"]["raw"].encode("utf-8") == raw
    assert art["definition"]["value"]["selection"]["filters"]["tiny"] == 1e-7
    assert [s["source"] for s in art["page"]["sources"]] == made["sources"]


def test_a_conversation_the_record_doesn_t_hold_and_one_with_nothing_in_it_write_nothing(w):
    empty = post_json(w.port, f"/fluid/api/magnets/{w.magnet()}/conversation", {"author": w.who}, CLIENT)
    assert empty.status in (200, 201), empty
    empty_id = empty.json["conversation"]
    for sources in (["ent-000000000000"], [empty_id]):
        mid = w.magnet(*sources)
        at = advance(w.brain)
        got = w.activate(mid, port=STAGED_PORT)
        assert got.status == 422, got
        assert got.json["reason"]["code"] == "no-readable-source"
        assert got.json["reason"]["retryable"] is False
        assert got.json["magnet"] == mid
        assert not w.relay.of("commit"), "Rust answers it after the read, without committing"
        assert advance(w.brain) == at


# -- what can run, and what the definition says -------------------------------------------------------


@pytest.mark.parametrize("row", DEFINITIONS["executable"], ids=_ids(DEFINITIONS["executable"]))
def test_every_definition_row_on_the_real_pair(w, row):
    if row["answer"] != "ready":
        w.write(MAGNET, row["definition"])
        at = advance(w.brain)
        got = w.activate(MAGNET, port=STAGED_PORT)
        expect = REFUSALS[row["answer"]]
        assert got.status == expect["status"], got
        assert got.body.decode("utf-8") == expect["bytes"]
        assert not w.relay.of("commit") and advance(w.brain) == at
        return
    mid = w.mid()
    made = json.loads(json.dumps(row["definition"]).replace(MAGNET, mid)
                      .replace(FIXTURE_CONVERSATION, w.biggest[0]))
    raw = w.write(mid, made)
    got = w.activate(mid, port=STAGED_PORT)
    assert got.status == 201, got
    art = artifact_of(w.relay.of("commit")[0])
    assert art["definition"]["raw"].encode("utf-8") == raw
    named = made["processing"]["operations"][0]
    assert art["operation"]["name"] == named.get("name")
    assert art["operation"]["options"] == (named.get("options") or {})
    assert got.json["operation"]["name"] == named.get("name")


def _file_bytes(row) -> bytes | None:
    if "pad" in row:
        text = row["pad"]["text"].encode("utf-8")
        return text + row["pad"]["byte"].encode("ascii") * (row["pad"]["total"] - len(text))
    return base64.b64decode(row["file_base64"]) if "file_base64" in row else None


@pytest.mark.parametrize("row", DEFINITIONS["files"], ids=_ids(DEFINITIONS["files"]))
def test_every_definition_file_row_on_the_real_pair(w, row):
    raw = _file_bytes(row)
    w.path(MAGNET).unlink(missing_ok=True)
    if raw is not None:
        # Same length, so a row at the bound stays at it.
        raw = raw.replace(FIXTURE_CONVERSATION.encode(), w.biggest[0].encode())
        w.write(MAGNET, raw)
    at = advance(w.brain)
    got = w.activate(MAGNET, port=STAGED_PORT)
    if row["answer"] == "ready":
        assert got.status == 201, got
        art = artifact_of(w.relay.of("commit")[0])
        assert art["definition"]["raw"].encode("utf-8") == raw, "exact bytes, line endings and all"
        assert art["definition"]["sha256"] == hashlib.sha256(raw).hexdigest()
        return
    assert not w.relay.of("commit") and advance(w.brain) == at
    if row["answer"] == "unreadable":
        assert got.status == 409 and got.json["kind"] == "Unreadable", got
        assert got.json["error"].startswith(row["error_starts"])
    else:
        assert got.status == REFUSALS[row["answer"]]["status"], got
        assert got.json == REFUSALS[row["answer"]]["body"]


def test_a_definition_python_itself_wrote_runs(w):
    made = post_json(w.port, "/fluid/api/arrangements/home/magnets", {
        "seed": {"sources": [{"kind": "conversation", "conversation": w.biggest[0]}], "selection": {},
                 "collection": {"mode": "one-time"}, "synthesis": {"mode": "manual"},
                 "notifications": {"newItems": False, "changes": False, "failures": False},
                 "presentation": {"renderer": "disc"}, "activation": {"mode": "manual"},
                 "processing": {"operations": [{"op": "extract", "name": "Read it"}]}},
        "attach": {"zone": {"type": "zone", "show": "magnet", "name": "Board"},
                   "base": {"format": "mentis.fluid-arrangement", "version": 2,
                            "tree": {"type": "zone", "id": "s", "show": "objects"}}}}, headers=CLIENT)
    assert made.status == 200, made
    got = w.activate(made.json["magnet"]["id"])
    assert got.status == 201, got
    assert got.json["operation"]["name"] == "Read it"


# -- the door ---------------------------------------------------------------------------------------


def _send(port, target, headers, body: bytes) -> Answer:
    named = {name.strip().lower() for name, _ in headers}
    lines = [f"POST {target} HTTP/1.1"]
    if "host" not in named:
        lines.append(f"Host: 127.0.0.1:{port}")
    if "content-length" not in named and "transfer-encoding" not in named and body:
        lines.append(f"Content-Length: {len(body)}")
    lines += [f"{name}: {value}" for name, value in headers]
    return Answer(exchange(port, ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8") + body, wait=PATIENCE))


def _row_body(row) -> bytes:
    if "body_fill" in row:
        fill = row["body_fill"]
        text = fill["text"].encode("utf-8")
        return text + fill["byte"].encode("ascii") * (fill["total"] - len(text))
    return row["body_text"].encode("utf-8")


@pytest.mark.parametrize("row", DOOR["rows"], ids=_ids(DOOR["rows"]))
def test_every_door_row_on_the_real_pair(w, row):
    at = advance(w.brain)
    got = _send(STAGED_PORT, DOOR["target"], row["headers"], _row_body(row))
    if "expect" in row:
        expect = row["expect"]
        assert (got.status, got.status_line.split(" ", 2)[2]) == (expect["status"], expect["reason_phrase"]), got
        assert got.header("Content-Type") == expect["content_type"]
        assert (got.header("Connection") == "close") is expect["closes"]
        assert got.body.decode("utf-8") == expect["body"]
        if row["stage"] == "body":
            # An empty body is past the door, and it is Python's 400 that real Python said.
            assert [h.step for h in w.relay.heard] == ["preflight"]
            assert base64.b64decode(json.loads(w.relay.heard[0].body)["public_body_base64"]) == b""
        else:
            assert not w.relay.heard, "a refusal at the door reaches nothing"
    else:
        assert row["reaches"] == "preflight"
        assert [h.step for h in w.relay.heard] == ["preflight"], got
        said = json.loads(w.relay.heard[0].body)
        assert base64.b64decode(said["public_body_base64"]) == _row_body(row), "the exact body"
        # Its author isn't this Brain's, and real Python says so.
        assert got.status == 422 and got.json["field"] == "author", got
    assert advance(w.brain) == at


def _public_body(row) -> bytes:
    if "public_body_nest" in row:
        spec = row["public_body_nest"]
        return (spec["before"] + spec["open"] * spec["depth"] + spec["inside"] + spec["close"] * spec["depth"]
                + spec["after"]).encode("utf-8")
    if "public_body_fill" in row:
        fill = row["public_body_fill"]
        text = fill["text"].encode("utf-8")
        return text + fill["byte"].encode("ascii") * (fill["total"] - len(text))
    return base64.b64decode(row["public_body_base64"])


@pytest.mark.parametrize("row", BODIES["refused"], ids=_ids(BODIES["refused"]))
def test_every_refused_body_on_the_real_pair_is_python_s_words_and_reached_it_lossless(w, row):
    """The fixtures name one Participant and one post of their own: this Brain's stand in for them."""
    a_post = REFUSALS["author-not-participant"]["body"]["author"]
    author = _load("answers.json")["holding"]["author"]
    body = _public_body(row).replace(a_post.encode(), w.a_post.encode()).replace(author.encode(), w.who.encode())
    want = REFUSALS[row["refused"]]
    at = advance(w.brain)
    got = _send(STAGED_PORT, DOOR["target"], [("X-Mentis-Client", "1"), ("Content-Type", "application/json"),
                                              ("Content-Length", str(len(body)))], body)
    assert got.status == want["status"], got
    assert got.body.decode() == want["bytes"].replace(a_post, w.a_post)
    assert [h.step for h in w.relay.heard] == ["preflight"]
    assert base64.b64decode(json.loads(w.relay.heard[0].body)["public_body_base64"]) == body
    assert advance(w.brain) == at


def test_a_grant_cannot_reach_preflight_with_or_without_the_client_header(w):
    grant = session_grant(w.port)["grant"]
    mid = w.magnet()
    body = json.dumps({"author": w.who, "op": w.op()}).encode()
    at = advance(w.brain)
    for headers in ({"X-Mentis-Worker": grant, "Content-Type": "application/json"},
                    {"X-Mentis-Worker": grant, "Content-Type": "application/json", **CLIENT}):
        got = ask(STAGED_PORT, "POST", f"/fluid/api/magnets/{mid}/activate", body=body, headers=headers)
        assert got.status == 403, got
        assert got.json["asked_for"] == f"/fluid/api/magnets/{mid}/activate"
    assert not w.relay.heard, "no preflight, and nothing else"
    assert advance(w.brain) == at


@pytest.mark.parametrize("path", ["/private/magnets/{}/activate/commit", "/private/magnets/{}/activate/preflight",
                                  "/%70rivate/magnets/{}/activate/commit"])
def test_a_forged_private_request_on_the_public_port_goes_nowhere(w, path):
    mid = w.magnet()
    at = advance(w.brain)
    got = ask(STAGED_PORT, "POST", path.format(mid), body=b'{"page": {}}',
              headers={**JSON_HEADERS, "X-Mentis-Boot-Secret": w.pair.secret,
                       "X-Mentis-Artifact-SHA256": "0" * 64})
    assert got.status == 404 and got.json == {"error": "no such semantic surface"}, got
    assert not w.relay.heard
    assert advance(w.brain) == at


def test_forged_fields_and_a_trailing_slash_can_t_commit(w):
    mid = w.magnet()
    at = advance(w.brain)
    target = f"/fluid/api/magnets/{mid}/activate"
    for field in ("page", "artifact", "definition", "digest", "cursor", "sources", "types", "mode",
                  "destination", "operation"):
        for port_target in (target, target + "/"):
            forged = post_json(STAGED_PORT, port_target, {"author": w.who, "op": w.op(), field: {}}, CLIENT)
            assert forged.status == 400, forged
            assert forged.json["kind"] == "BadRequest"
    # The slash isn't this route: it goes to Python's public door, which has no processor.
    plain = post_json(STAGED_PORT, target + "/", {"author": w.who, "op": w.op()}, CLIENT)
    assert plain.status == 503, plain
    assert plain.json["reason"]["code"] == "processor-unavailable"
    assert not w.relay.of("commit")
    assert advance(w.brain) == at


def test_python_s_private_port_needs_the_exact_secret_and_checks_what_the_secret_holder_sends(w):
    private = w.pair.private_port
    mid, op = w.magnet(), w.op()
    assert w.activate(mid, op, port=STAGED_PORT).status == 201
    raw = w.relay.of("commit")[0].body
    digest = hashlib.sha256(raw).hexdigest()
    target = f"/private/magnets/{mid}/activate/commit"
    plain = {"Content-Type": "application/json", "X-Mentis-Artifact-SHA256": digest}
    at = advance(w.brain)
    assert ask(private, "POST", target, body=raw, headers=plain).status == 403
    assert ask(private, "POST", target, body=raw, headers={**plain, "X-Mentis-Boot-Secret": "no"}).status == 403

    def told(body, digest_of=None):
        got = ask(private, "POST", target, body=body,
                  headers={"Content-Type": "application/json", "X-Mentis-Boot-Secret": w.pair.secret,
                           "X-Mentis-Artifact-SHA256": digest_of or hashlib.sha256(body).hexdigest()})
        assert got.status == 200, got
        return got.json

    # Real Rust bytes with one thing changed, under a digest that matches or one that doesn't.
    fresh = artifact_of(w.relay.of("commit")[0])
    fresh["request"]["op"] = w.op()
    assert told(json.dumps(fresh).encode(), digest)["state"] == "internal-protocol-error"
    fresh["page"]["sources"][0]["results"][0].pop("author")
    assert told(json.dumps(fresh).encode())["state"] == "internal-protocol-error"
    assert advance(w.brain) == at
    # The artifact's cap, unread.
    over = ask(private, "POST", target, headers={"Content-Type": "application/json",
                                                 "X-Mentis-Boot-Secret": w.pair.secret,
                                                 "X-Mentis-Artifact-SHA256": digest,
                                                 "Content-Length": str(26_214_401)})
    assert over.status == 200 and over.json["status"] == 413, over
    assert json.dumps(over.json["body"]) == REFUSALS["artifact-too-large"]["bytes"].replace(MAGNET, mid)
    assert advance(w.brain) == at


def test_the_rule_rolled_back_is_python_s_answer_and_records_nothing(brain_seed, tmp_path):
    brain = tmp_path / "brain"
    shutil.copytree(brain_seed, brain)
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    [rule] = [r for r in table["routes"] if r["id"] == "magnet-activate"]
    rule["owner"] = "python"
    path = tmp_path / "rolled-back.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    who = _of_kind(brain, "participant")[0]
    conversation = rows(brain, BIGGEST)[0][0]
    (brain / "presentation" / "magnets").mkdir(parents=True, exist_ok=True)
    (brain / "presentation" / "magnets" / f"{MAGNET}.json").write_text(
        json.dumps(definition(MAGNET, [conversation])), encoding="utf-8")
    with Pair(brain, port=ROLLED_BACK_PORT, route_table=path) as pair:
        at = advance(brain)
        target = f"/fluid/api/magnets/{MAGNET}/activate"
        for spelled in (target, target + "/"):
            got = post_json(pair.port, spelled, {"author": who, "op": "a-key"}, CLIENT)
            assert got.status == 503, got
            assert got.body.decode() == REFUSALS["processor-unavailable"]["bytes"]
            forged = post_json(pair.port, spelled, {"author": who, "op": "a-key", "page": {}}, CLIENT)
            assert forged.status == 400, forged
        assert advance(brain) == at


# -- M1's GET, beside it ----------------------------------------------------------------------------


def test_a_get_says_the_same_bytes_as_the_artifact_s_page_and_stays_the_same(w):
    # Posts alone: a page asked for objects says how far it has read them, which grows between two reads.
    mid = w.magnet(w.biggest[0])
    target = f"/fluid/api/magnets/{mid}/read?mode=page"
    before = ask(w.port, "GET", target, headers=CLIENT)
    assert before.status == 200, before
    got = w.activate(mid, port=STAGED_PORT)
    assert got.status == 201, got
    page = artifact_of(w.relay.of("commit")[0])["page"]
    assert json.dumps(page).encode("utf-8") == before.body, "one read, whichever asked"
    after = ask(w.port, "GET", target, headers=CLIENT)
    assert after.status == 200, after
    assert after.json["cursor"] != before.json["cursor"]
    assert after.body.replace(after.json["cursor"].encode(), before.json["cursor"].encode()) == before.body,         "the commit changed nothing in it but where the record is"


# -- races ------------------------------------------------------------------------------------------


def _two_preflights_done(w, mid, op_a, op_b):
    """Two activations with their `ready` answers both written by Python and neither given to its front."""
    gate_a, gate_b = Gate(), Gate()
    w.relay.on("preflight", answered=gate_a)
    a = later(lambda: w.activate(mid, op_a, port=STAGED_PORT))
    gate_a.arrived()
    w.relay.on("preflight", answered=gate_b)
    b = later(lambda: w.activate(mid, op_b, port=STAGED_PORT))
    gate_b.arrived()
    return a, gate_a, b, gate_b


def test_the_same_key_twice_once_both_preflights_are_done_writes_once_and_replays(w):
    mid, op = w.magnet(), w.op()
    a, gate_a, b, gate_b = _two_preflights_done(w, mid, op, op)
    gate_a.go.set()
    first = a.result(PATIENCE)
    assert first.status == 201, first
    gate_b.go.set()
    second = b.result(PATIENCE)
    assert second.status == 200, second
    assert_same_but_the_moment(first, second)
    commits = w.relay.of("commit")
    assert len(commits) == 2, "both went on: Python's key inside its transaction is what wrote once"
    assert b'"state": "committed"' in commits[0].answer and b'"state": "replay"' in commits[1].answer
    assert len(w.outcomes(op)) == 1 and len(w.claims(mid)) == 1
    assert len(w.acts("magnet-extracted", turn=first.json["post"])) == 1


def test_different_keys_on_a_first_activation_make_two_turns_in_one_conversation(w):
    mid, op_a, op_b = w.magnet(), w.op(), w.op()
    a, gate_a, b, gate_b = _two_preflights_done(w, mid, op_a, op_b)
    gate_a.go.set()
    first = a.result(PATIENCE)
    gate_b.go.set()
    second = b.result(PATIENCE)
    assert (first.status, second.status) == (201, 201), (first, second)
    assert first.json["conversation"] == second.json["conversation"]
    assert first.json["conversation_created"] is True and second.json["conversation_created"] is False
    assert first.json["post"] != second.json["post"]
    assert len(w.claims(mid)) == 1


@pytest.mark.parametrize("same_key", [True, False], ids=["same-key", "different-keys"])
def test_two_fronts_commit_at_the_same_instant(w, same_key):
    """Real overlap at Python, which one front can't give: its own place lets only one through at a time.
    Both commits are released together, so either they overlap at Python's one place or they don't."""
    mid, op_a = w.magnet(), w.op()
    op_b = op_a if same_key else w.op()
    gate_a, gate_b = Gate(), Gate()
    with w.pair.second_front("127.0.0.1", THIRD_PORT, upstream=w.relay.url):
        w.relay.on("commit", asked=gate_a)
        a = later(lambda: w.activate(mid, op_a, port=STAGED_PORT))
        gate_a.arrived()
        w.relay.on("commit", asked=gate_b)
        b = later(lambda: w.activate(mid, op_b, port=THIRD_PORT))
        gate_b.arrived()
        gate_a.go.set()
        gate_b.go.set()
        answers = [a.result(PATIENCE), b.result(PATIENCE)]
    statuses = sorted(answer.status for answer in answers)
    assert 201 in statuses, answers
    wrote = [answer for answer in answers if answer.status == 201]
    if same_key:
        assert statuses in ([200, 201], [201, 503]), answers
        assert len(w.outcomes(op_a)) == 1
    else:
        assert statuses in ([201, 201], [201, 503]), answers
    for answer in answers:
        if answer.status == 503:
            assert answer.json["reason"]["code"] == "busy", answer
    assert len({answer.json["conversation"] for answer in wrote}) == 1
    assert len(w.claims(mid)) == 1
    assert len(w.acts("magnet-extracted", conversation=wrote[0].json["conversation"])) == len(wrote)


@pytest.mark.parametrize("same_key", [True, False], ids=["same-key", "different-keys"])
def test_many_clients_at_once_on_one_front(w, same_key):
    """Nothing staged: whatever the timing, every answer is one the contract has, and the record agrees."""
    mid = w.magnet()
    keys = [w.op()] * 6 if same_key else [w.op() for _ in range(6)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        answers = list(pool.map(lambda key: w.activate(mid, key), keys))
    for answer in answers:
        assert answer.status in (200, 201, 503), answer
        if answer.status == 503:
            assert answer.json["reason"]["code"] == "busy", answer
    wrote = [answer for answer in answers if answer.status == 201]
    assert wrote, answers
    assert len({answer.json["conversation"] for answer in wrote}) == 1
    assert len(w.claims(mid)) == 1
    conversation = wrote[0].json["conversation"]
    assert len(w.acts("magnet-extracted", conversation=conversation)) == len(wrote)
    if same_key:
        assert len(wrote) == 1 and len(w.outcomes(keys[0])) == 1
        assert w.activate(mid, keys[0]).status == 200


@pytest.mark.parametrize("same_key", [True, False], ids=["same-key", "different-key"])
def test_one_place_on_a_front_not_queued_and_held_through_the_commit_s_answer(w, same_key):
    mid, op = w.magnet(), w.op()
    gate = Gate()
    w.relay.on("commit", answered=gate)
    first = later(lambda: w.activate(mid, op, port=STAGED_PORT))
    gate.arrived()
    # Python has answered and the front hasn't heard: the place is still held.
    at = advance(w.brain)
    overlapping = w.activate(mid, op if same_key else w.op(), port=STAGED_PORT)
    if same_key:
        # The key is already answered, and a replay never waits on the place.
        assert overlapping.status == 200, overlapping
        assert overlapping.json["post"] == json.loads(_answer_body(w.relay.of("commit")[0]))["body"]["post"]
    else:
        assert overlapping.status == 503, overlapping
        assert overlapping.body.decode() == REFUSALS["busy"]["bytes"].replace(MAGNET, mid)
    assert len(w.relay.of("commit")) == 1 and advance(w.brain) == at
    gate.go.set()
    assert first.result(PATIENCE).status == 201
    assert w.activate(mid, w.op(), port=STAGED_PORT).status == 201, "the place went back"


def test_an_overlap_before_the_first_write_is_busy_not_a_replay(w):
    mid, op = w.magnet(), w.op()
    gate = Gate()
    w.relay.on("commit", asked=gate)
    first = later(lambda: w.activate(mid, op, port=STAGED_PORT))
    gate.arrived()
    overlapping = w.activate(mid, op, port=STAGED_PORT)
    assert overlapping.status == 503, overlapping
    assert overlapping.json["reason"]["code"] == "busy"
    assert len(w.relay.of("commit")) == 1
    gate.go.set()
    assert first.result(PATIENCE).status == 201


def _answer_body(heard: Heard) -> bytes:
    return heard.answer.partition(b"\r\n\r\n")[2]


def test_python_s_one_commit_place_answers_another_front_busy_and_nothing_is_written(w):
    mid = w.magnet()
    gate = Gate()
    w.relay.on("commit", midway=gate)
    holding = later(lambda: w.activate(mid, port=STAGED_PORT))
    gate.arrived()
    time.sleep(0.5)  # Python takes its place on the request's head, before reading any of the body
    at = advance(w.brain)
    other = w.magnet()
    overlapping = w.activate(other)
    assert overlapping.status == 503, overlapping
    assert overlapping.body.decode() == REFUSALS["busy"]["bytes"].replace(MAGNET, other)
    assert advance(w.brain) == at
    gate.go.set()
    assert holding.result(PATIENCE).status == 201
    assert w.activate(other).status == 201


def test_beside_the_conversation_route_one_claim_and_no_orphan(w):
    mid, op = w.magnet(), w.op()
    gate = Gate()
    w.relay.on("commit", asked=gate)
    activating = later(lambda: w.activate(mid, op, port=STAGED_PORT))
    gate.arrived()
    opened = post_json(w.port, f"/fluid/api/magnets/{mid}/conversation", {"author": w.other}, CLIENT)
    assert opened.status in (200, 201), opened
    gate.go.set()
    got = activating.result(PATIENCE)
    assert got.status == 201, got
    assert got.json["conversation"] == opened.json["conversation"]
    assert got.json["conversation_created"] is False
    assert len(w.claims(mid)) == 1


# -- a Magnet deleted, and a definition changed, during its activation ------------------------------


def test_a_magnet_deleted_during_its_activation_writes_nothing_and_keeps_the_key(w):
    mid, op = w.magnet(), w.op()
    gate = Gate()
    w.relay.on("commit", asked=gate)
    activating = later(lambda: w.activate(mid, op, port=STAGED_PORT))
    gate.arrived()
    deleted = post_json(w.port, f"/fluid/api/magnets/{mid}/delete", {}, CLIENT)
    assert deleted.status == 200, deleted
    assert not w.path(mid).exists()
    at = advance(w.brain)
    gate.go.set()
    got = activating.result(PATIENCE)
    assert got.status == 422, got
    assert got.body.decode() == REFUSALS["magnet-deleted"]["bytes"].replace(MAGNET, mid)
    assert advance(w.brain) == at and not w.outcomes(op)
    w.write(mid, definition(mid, [w.biggest[0]]))
    assert w.activate(mid, op).status == 201, "the key was never used"


def test_a_definition_changed_during_its_activation_keeps_the_bytes_it_ran_on(w):
    mid, op = w.magnet(), w.op()
    ran_on = w.path(mid).read_bytes()
    gate = Gate()
    w.relay.on("commit", asked=gate)
    activating = later(lambda: w.activate(mid, op, port=STAGED_PORT))
    gate.arrived()
    w.write(mid, definition(mid, [w.biggest[1]], activation={"mode": "scheduled", "schedule": "0 0 * * *"}))
    gate.go.set()
    got = activating.result(PATIENCE)
    assert got.status == 201, got
    held = json.loads(w.held_bytes(got.json["artifact"]["digest"]))
    assert held["definition"]["raw"].encode("utf-8") == ran_on


# -- what's lost ------------------------------------------------------------------------------------


@pytest.mark.parametrize("plan", [
    dict(to_python=False),
    dict(answer=lambda answer: None),
    dict(answer=lambda answer: answer[:len(answer) - 7]),
], ids=["no-answer-python-never-heard", "answer-lost", "answer-truncated"])
def test_an_interrupted_preflight_is_busy_and_neither_a_read_nor_a_commit_follows(w, plan):
    mid, op = w.magnet(), w.op()
    at = advance(w.brain)
    w.relay.on("preflight", **plan)
    got = w.activate(mid, op, port=STAGED_PORT)
    assert got.status == 503, got
    assert got.json["reason"]["code"] == "preflight-interrupted" and got.json["kind"] == "Busy"
    assert got.body.decode() == REFUSALS["preflight-interrupted"]["bytes"].replace(MAGNET, mid)
    assert [h.step for h in w.relay.heard] == ["preflight"]
    assert advance(w.brain) == at
    assert w.activate(mid, op, port=STAGED_PORT).status == 201, "the same key simply runs"


@pytest.mark.parametrize("given", [
    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}",
    b"HTTP/1.1 500 Oops\r\nContent-Length: 0\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nContent-Length: 1048577\r\n\r\n",
], ids=["not-its-shape", "another-status", "over-the-bound"])
def test_a_complete_preflight_answer_that_is_no_answer_is_502_and_nothing_follows(w, given):
    mid, op = w.magnet(), w.op()
    at = advance(w.brain)
    w.relay.on("preflight", answer=lambda answer: given)
    got = w.activate(mid, op, port=STAGED_PORT)
    assert got.status == 502, got
    assert got.body.decode() == REFUSALS["internal-protocol-error"]["bytes"].replace(MAGNET, mid)
    assert [h.step for h in w.relay.heard] == ["preflight"] and advance(w.brain) == at
    assert w.activate(mid, op, port=STAGED_PORT).status == 201


def test_python_refusing_rust_s_artifact_is_502_writes_nothing_and_leaves_the_key_free(w):
    mid, op = w.magnet(), w.op()
    at = advance(w.brain)
    # One byte, so its digest no longer holds. Nothing else about the request changes.
    w.relay.on("commit", sent=lambda body: body[:-1] + b" ")
    got = w.activate(mid, op, port=STAGED_PORT)
    assert got.status == 502, got
    assert got.body.decode() == REFUSALS["internal-protocol-error"]["bytes"].replace(MAGNET, mid)
    assert not w.outcomes(op) and advance(w.brain) == at
    assert w.activate(mid, op, port=STAGED_PORT).status == 201


def test_a_preflight_past_its_two_seconds_is_busy_and_nothing_follows(w):
    mid, op = w.magnet(), w.op()
    at = advance(w.brain)
    gate = Gate()
    w.relay.on("preflight", answered=gate)
    started = time.monotonic()
    got = w.activate(mid, op, port=STAGED_PORT)
    took = time.monotonic() - started
    gate.go.set()
    assert got.status == 503 and got.json["reason"]["code"] == "preflight-interrupted", got
    assert 1.8 <= took < 6, took
    time.sleep(0.2)
    assert [h.step for h in w.relay.heard] == ["preflight"]
    assert advance(w.brain) == at


@pytest.mark.parametrize("plan", [
    dict(answer=lambda answer: None),
    dict(answer=lambda answer: answer[:len(answer) // 2]),
    dict(answer=lambda answer: b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"),
    dict(answer=lambda answer: b"HTTP/1.1 500 Oops\r\nContent-Length: 0\r\n\r\n"),
], ids=["lost", "truncated", "malformed", "another-status"])
def test_a_lost_commit_answer_is_outcome_unknown_and_the_same_key_finds_the_result(w, plan):
    mid, op = w.magnet(), w.op()
    w.relay.on("commit", **plan)
    got = w.activate(mid, op, port=STAGED_PORT)
    assert got.status == 503, got
    assert got.json["kind"] == "OutcomeUnknown" and got.json["op"] == op and got.json["magnet"] == mid
    assert got.json["reason"] == {"code": "outcome-unknown", "message": got.json["error"], "retryable": True}
    [keyed] = w.outcomes(op)
    assert "same operation key" in got.json["error"], "it did commit, and the caller is told how to find out"
    at = advance(w.brain)
    w.relay.heard.clear()
    found = w.activate(mid, op, port=STAGED_PORT)
    assert found.status == 200, found
    assert found.json["post"] == keyed["detail"]["result"]["post"]
    assert not w.relay.of("commit") and advance(w.brain) == at
    assert len(w.outcomes(op)) == 1
    # A new key is another activation, as the words say.
    assert w.activate(mid, w.op(), port=STAGED_PORT).json["post"] != found.json["post"]


def test_a_commit_past_its_five_seconds_is_outcome_unknown_and_python_may_still_commit(w):
    mid, op = w.magnet(), w.op()
    gate = Gate()
    w.relay.on("commit", asked=gate)
    started = time.monotonic()
    got = w.activate(mid, op, port=STAGED_PORT)
    took = time.monotonic() - started
    assert got.status == 503 and got.json["kind"] == "OutcomeUnknown", got
    assert 4.8 <= took < 12, took
    assert not w.outcomes(op), "Python hasn't heard yet"
    # The place went back with the answer, and same-key retry runs while the old bytes are still on their way.
    retried = w.activate(mid, op, port=STAGED_PORT)
    assert retried.status == 201, retried
    gate.go.set()
    deadline = time.monotonic() + PATIENCE
    while len(w.relay.of("commit")) < 2 or not w.relay.of("commit")[0].answer:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert b'"state": "replay"' in w.relay.of("commit")[0].answer, "the late one found the key"
    assert len(w.outcomes(op)) == 1


def test_no_python_to_commit_to_is_outcome_unknown_and_nothing_was_recorded(w):
    mid, op = w.magnet(), w.op()
    w.relay.on("commit", to_python=False)
    got = w.activate(mid, op, port=STAGED_PORT)
    assert got.status == 503 and got.json["kind"] == "OutcomeUnknown", got
    assert not w.outcomes(op)
    assert w.activate(mid, op, port=STAGED_PORT).status == 201, "safely runs again"


def test_a_file_that_can_t_be_told_refuses_nothing_and_a_later_request_tells_it(w):
    mid, op = w.magnet(), w.op()
    path = w.path(mid)
    os.chmod(path, stat.S_IREAD)
    try:
        first = w.activate(mid, op)
        assert first.status == 201, first
        cid = first.json["conversation"]
        assert "conversation" not in json.loads(path.read_text(encoding="utf-8")), "it could not be told"
        assert [one for one in w.claims(mid)], "the claim stands"
        assert_same_but_the_moment(first, w.activate(mid, op))
    finally:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    second = w.activate(mid)
    assert second.status == 201, second
    assert second.json["conversation"] == cid and second.json["conversation_created"] is False
    assert json.loads(path.read_text(encoding="utf-8"))["conversation"] == cid


# -- a client leaving -------------------------------------------------------------------------------


def test_a_client_gone_during_preflight_writes_nothing_and_the_key_stays_free(w):
    mid, op = w.magnet(), w.op()
    at = advance(w.brain)
    gate = Gate()
    w.relay.on("preflight", answered=gate)
    client = leaving_client(STAGED_PORT, mid, w.who, op)
    gate.arrived()
    client.close()
    time.sleep(0.2)
    gate.go.set()
    # Long enough for the read and a commit that isn't going to come.
    time.sleep(1.5)
    assert not w.relay.of("commit"), "no commit follows a client that has gone"
    assert not w.outcomes(op) and advance(w.brain) == at
    assert w.activate(mid, op, port=STAGED_PORT).status == 201, "the place went back and the key is free"


def test_a_client_gone_once_the_commit_has_begun_may_still_commit_and_the_same_key_finds_it(w):
    mid, op = w.magnet(), w.op()
    gate = Gate()
    w.relay.on("commit", asked=gate)
    client = leaving_client(STAGED_PORT, mid, w.who, op)
    gate.arrived()
    client.close()
    gate.go.set()
    deadline = time.monotonic() + PATIENCE
    while not w.outcomes(op):
        assert time.monotonic() < deadline, "Python never heard the commit"
        time.sleep(0.02)
    [keyed] = w.outcomes(op)
    found = w.activate(mid, op, port=STAGED_PORT)
    assert found.status == 200, found
    assert found.json["post"] == keyed["detail"]["result"]["post"]


# -- real kills -------------------------------------------------------------------------------------


def test_python_killed_before_it_heard_the_commit_leaves_nothing_and_the_same_key_runs(w):
    mid, op = w.magnet(), w.op()
    gate = Gate()
    w.relay.on("commit", asked=gate)
    activating = later(lambda: w.activate(mid, op, port=STAGED_PORT))
    gate.arrived()
    w.pair.kill_python()
    gate.go.set()
    got = activating.result(PATIENCE)
    assert got.status == 503 and got.json["kind"] == "OutcomeUnknown", got
    w.pair.restart_python()
    assert not w.outcomes(op)
    assert w.activate(mid, op, port=STAGED_PORT).status == 201


def test_python_killed_after_its_answer_keeps_the_commit_and_the_same_key_finds_it(w):
    mid, op = w.magnet(), w.op()
    gate = Gate()
    w.relay.on("commit", answered=gate)
    activating = later(lambda: w.activate(mid, op, port=STAGED_PORT))
    gate.arrived()
    w.pair.kill_python()
    gate.go.set()
    first = activating.result(PATIENCE)
    assert first.status == 201, first
    w.pair.restart_python()
    assert_same_but_the_moment(first, w.activate(mid, op))
    assert len(w.outcomes(op)) == 1


def test_a_front_killed_mid_commit_leaves_the_key_to_answer_on_any_front(w):
    mid, op = w.magnet(), w.op()
    gate = Gate()
    with w.pair.second_front("127.0.0.1", DOOMED_PORT, upstream=w.relay.url) as doomed:
        w.relay.on("commit", asked=gate)
        client = leaving_client(DOOMED_PORT, mid, w.who, op)
        gate.arrived()
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(doomed.pid)], capture_output=True, check=False)
        doomed.wait(timeout=30)
        gate.go.set()
        deadline = time.monotonic() + PATIENCE
        while not w.outcomes(op):
            assert time.monotonic() < deadline, "Python never heard the commit"
            time.sleep(0.02)
        client.close()
    found = w.activate(mid, op)
    assert found.status == 200, found


def test_the_seed_itself_is_unchanged_by_all_of_it(w):
    """Run last: the Brain every test wrote to is a copy, and nothing here wrote to what it was copied from.
    The module's fixture asks again once the pair has stopped."""
    assert w.seed.resolve() != w.brain.resolve()
    assert common.tree_digest(w.seed) == w.seed_digest
    assert not (w.seed.parent / f"{w.seed.name}.run").exists()
