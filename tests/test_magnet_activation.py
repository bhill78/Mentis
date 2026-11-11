"""Python's half of a Magnet's manual activation (`mentis.magnet.activation`), on its real door and a
real record: `docs/magnets/M1-contract.md`, "Manual activation", held to the fixtures in
`tests/fixtures/magnet-conformance/activation/`. No Rust here: an artifact is what those fixtures hold."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import pathlib
import shutil
import os
import socket
import threading
from http.server import ThreadingHTTPServer

import pytest

import mentis.magnet as M
from mentis import artifacts
from mentis.core import context_cache
from mentis.conversation import anchors, posting
from mentis.fluid import _checks as W
from mentis.fluid import arrangements as A
from mentis.fluid import commands
from mentis.magnet import activation as X
from mentis.spine import held
from mentis.web import _Handler, _State, fixture

HERE = pathlib.Path(__file__).parent / "fixtures" / "magnet-conformance" / "activation"
SECRET = "s3cret"


def load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


REFUSALS, DOOR, BODIES = load("refusals.json"), load("door.json"), load("public_bodies.json")
DEFINITIONS, ANSWERS, ARTIFACTS = load("definitions.json"), load("answers.json"), load("artifacts.json")
RESULTS, USEFUL, REQUESTS = load("results.json"), load("useful_sources.json"), load("private_requests.json")
MAGNET = DEFINITIONS["magnet"]
AUTHOR, OP = ANSWERS["holding"]["author"], ANSWERS["holding"]["op"]
A_POST = REFUSALS["author-not-participant"]["body"]["author"]
PREFLIGHT = f"/private/magnets/{MAGNET}/activate/preflight"
COMMIT = f"/private/magnets/{MAGNET}/activate/commit"
JSON_HEADERS = [["X-Mentis-Client", "1"], ["Content-Type", "application/json"]]


def ids(rows):
    return [r["id"] for r in rows]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """One fixture Brain, copied for each test: what a test writes is that test's."""
    root = tmp_path_factory.mktemp("activation-seed") / "brain"
    fixture.build(str(root))
    return root


class World:
    def __init__(self, root):
        self.root = root
        self.state = _State(str(root))
        self.corpus, self.cv = self.state.corpus, self.state.cv
        self.who = self.corpus.entries_of_kind("participant")[0]["id"]
        self.other = self.corpus.entries_of_kind("participant")[1]["id"]
        self.a_post = self.corpus.entries_of_kind("contribution")[0]["id"]
        self.servers = []
        self.alone = self.serve(None)
        self.front = self.serve(SECRET)

    def serve(self, secret):
        attrs = {"state": self.state, "boot_secret": secret}
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), type("H", (_Handler,), attrs))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.servers.append(httpd)
        return httpd.server_address[1]

    def stop(self):
        for httpd in self.servers:
            httpd.shutdown()
            httpd.server_close()

    @property
    def definition_path(self):
        return pathlib.Path(self.root) / "presentation" / "magnets" / f"{MAGNET}.json"

    def define(self, raw: bytes | str | dict):
        if isinstance(raw, dict):
            raw = json.dumps(raw).encode()
        elif isinstance(raw, str):
            raw = raw.encode()
        self.definition_path.parent.mkdir(parents=True, exist_ok=True)
        self.definition_path.write_bytes(raw)


@pytest.fixture()
def world(built, tmp_path):
    root = tmp_path / "brain"
    shutil.copytree(built, root)
    w = World(root)
    yield w
    w.stop()


def send(port, target, headers, body: bytes, method="POST") -> dict:
    named = {name.strip().lower() for name, _ in headers}
    lines = [f"{method} {target} HTTP/1.1"]
    if "host" not in named:
        lines.append(f"Host: 127.0.0.1:{port}")
    if "authorization" not in named:     # the owner's session (tests/conftest.py)
        lines.append(f"Authorization: Bearer {os.environ['MENTIS_TEST_OWNER_TOKEN']}")
    if "content-length" not in named and "transfer-encoding" not in named and body:
        lines.append(f"Content-Length: {len(body)}")
    lines += [f"{name}: {value}" for name, value in headers]
    wire = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8") + body
    with socket.create_connection(("127.0.0.1", port), timeout=30) as sock:
        sock.sendall(wire)
        sock.shutdown(socket.SHUT_WR)
        got = b""
        while chunk := sock.recv(1 << 16):
            got += chunk
    head, _, rest = got.partition(b"\r\n\r\n")
    status_line, *header_lines = head.decode("latin-1").split("\r\n")
    answered = [line.split(": ", 1) for line in header_lines]
    return {"status": int(status_line.split(" ")[1]), "reason": status_line.split(" ", 2)[2],
            "content_type": next(v for k, v in answered if k.lower() == "content-type"),
            "closes": any(k.lower() == "connection" and v == "close" for k, v in answered),
            "body": rest}


def filled(fill) -> bytes:
    text = fill["text"].encode("utf-8")
    return text + fill["byte"].encode("ascii") * (fill["total"] - len(text))


def nested(spec) -> bytes:
    return (spec["before"] + spec["open"] * spec["depth"] + spec["inside"] + spec["close"] * spec["depth"]
            + spec["after"]).encode("utf-8")


def public_body(row) -> bytes:
    if "public_body_nest" in row:
        return nested(row["public_body_nest"])
    if "public_body_fill" in row:
        return filled(row["public_body_fill"])
    return base64.b64decode(row["public_body_base64"])


def preflight_wire(body: bytes, segment=MAGNET) -> bytes:
    return json.dumps({"protocol": 1, "magnet": segment,
                       "public_body_base64": base64.b64encode(body).decode()}).encode()


def private(world, target, body: bytes, *, secret=SECRET, headers=()) -> dict:
    sent = [["X-Mentis-Boot-Secret", secret], ["Content-Type", "application/json"], *headers]
    return send(world.front, target, sent, body)


def ask_preflight(world, body: bytes, segment=MAGNET) -> dict:
    got = private(world, f"/private/magnets/{segment}/activate/preflight", preflight_wire(body, segment))
    assert got["status"] == 200
    wire = got["body"]
    answer = json.loads(wire)
    assert json.dumps(answer, ensure_ascii=False).encode("utf-8") == wire
    assert len(wire) <= X.ANSWER_MOST
    return answer


def asked_body(world, op=OP, author=None) -> bytes:
    return json.dumps({"author": author or world.who, "op": op}).encode()


def artifact_of(world, name="complete", op=OP, author=None, change=None) -> bytes:
    """A fixture's artifact as this Brain's Participant asked for it, in the one serialization."""
    art = json.loads((HERE / ARTIFACTS["artifacts"][name]["file"]).read_bytes())
    art["request"]["author"] = author or world.who
    art["request"]["op"] = op
    if change:
        change(art)
    return json.dumps(art).encode("utf-8")


def define_from(world, raw: bytes):
    world.define(json.loads(raw)["definition"]["raw"].encode("utf-8"))


def ask_commit(world, raw: bytes, *, digest=None, segment=MAGNET, ctype="application/json") -> dict:
    sent = [["X-Mentis-Boot-Secret", SECRET], ["Content-Type", ctype],
            [X.DIGEST_HEADER, digest or hashlib.sha256(raw).hexdigest()]]
    got = send(world.front, f"/private/magnets/{segment}/activate/commit", sent, raw)
    assert got["status"] == 200, got
    wire = got["body"]
    answer = json.loads(wire)
    assert json.dumps(answer, ensure_ascii=False).encode("utf-8") == wire
    return answer


def committed(world, op=OP, name="complete") -> dict:
    raw = artifact_of(world, name, op=op)
    define_from(world, raw)
    answer = ask_commit(world, raw)
    assert answer["state"] == "committed", answer
    return answer


def act_of(world, act):
    return world.corpus.operational(act=act, limit=100000)


def record_size(world) -> int:
    """Every entry the record holds, which is what writes nothing has to leave alone."""
    import sqlite3
    db = sqlite3.connect(f"file:{pathlib.Path(world.root) / 'corpus.db'}?mode=ro", uri=True)
    try:
        return sum(db.execute(f"select count(*) from {table}").fetchone()[0] for table in ("entry", "operational"))
    finally:
        db.close()


# -- the words ------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, body", [
    ("body-too-deep", X.BODY_TOO_DEEP), ("body-surrogate", X.BODY_SURROGATE),
    ("body-not-object", X.BODY_NOT_OBJECT), ("body-fields", X.BODY_FIELDS),
    ("magnet-id", X.NOT_A_MAGNET_ID), ("op-missing", X.OP_MISSING),
    ("public-body-too-large", X.PUBLIC_BODY_TOO_LARGE), ("no-definition", X.no_definition(MAGNET)),
    ("definition-too-large", X.definition_too_large(MAGNET)),
    ("definition-surrogate", X.definition_surrogate(MAGNET)), ("magnet-deleted", X.deleted(MAGNET)),
    ("busy", X.busy(MAGNET)), ("sources-busy", X.sources_busy(MAGNET)),
    ("artifact-too-large", X.artifact_too_large(MAGNET)),
    ("processor-unavailable", X.processor_unavailable(MAGNET)),
    ("internal-protocol-error", X.internal_protocol_error(MAGNET)),
    *[(code, X.cannot_run(MAGNET, code)) for code in DEFINITIONS["order"]]])
def test_every_refusal_is_the_contract_s_bytes(name, body):
    assert json.dumps(body, default=str) == REFUSALS[name]["bytes"]


# -- the door, on its own path --------------------------------------------------------------------

EXPECTING = [r for r in DOOR["rows"] if "expect" in r]
REACHING = [r for r in DOOR["rows"] if "reaches" in r]


def row_body(row) -> bytes:
    return filled(row["body_fill"]) if "body_fill" in row else row["body_text"].encode("utf-8")


@pytest.mark.parametrize("row", EXPECTING, ids=ids(EXPECTING))
def test_a_door_row_is_what_the_activate_path_answers_on_python_alone(world, row):
    got = send(world.alone, DOOR["target"], row["headers"], row_body(row))
    expect = row["expect"]
    assert got["status"] == expect["status"]
    assert got["reason"] == expect["reason_phrase"]
    assert got["content_type"] == expect["content_type"]
    assert got["closes"] is expect["closes"]
    assert got["body"].decode("utf-8") == expect["body"]


@pytest.mark.parametrize("row", REACHING, ids=ids(REACHING))
def test_an_accepted_row_is_past_the_door_on_the_activate_path(world, row):
    """On to the body's checks: the row's author isn't in this Brain."""
    got = send(world.alone, DOOR["target"], row["headers"], row_body(row))
    assert got["status"] == 422 and json.loads(got["body"])["field"] == "author"


@pytest.mark.parametrize("length", ["9" * 4301, "0" * 5000 + "65537", str(2 ** 64)])
def test_a_body_past_the_limit_is_not_read(world, length, monkeypatch):
    read = []
    original = _Handler._read_body
    monkeypatch.setattr(_Handler, "_read_body", lambda self, n: (read.append(n), original(self, n))[1])
    got = send(world.alone, DOOR["target"], [*JSON_HEADERS, ["Content-Length", length]], b"")
    assert got["status"] == 413 and got["body"].decode() == REFUSALS["public-body-too-large"]["bytes"]
    assert read == []


def test_the_sibling_route_keeps_its_own_door_until_its_own_defect_is_taken_up(world):
    """Only this route's length is read by value: `ent-d613f231201d` is the rest of them."""
    sibling = DOOR["sibling_target"]
    got = send(world.alone, sibling, [*JSON_HEADERS, ["Content-Length", "9" * 4301]], b"")
    assert got["status"] == 500
    got = send(world.alone, DOOR["target"], [*JSON_HEADERS, ["Content-Length", "9" * 4301]], b"")
    assert got["status"] == 413


# -- the public body ------------------------------------------------------------------------------

def body_in_this_brain(world, raw: bytes) -> bytes:
    return raw.replace(A_POST.encode(), world.a_post.encode()).replace(AUTHOR.encode(), world.who.encode())


def words_in_this_brain(world, text: str) -> str:
    return text.replace(A_POST, world.a_post)


@pytest.mark.parametrize("row", BODIES["refused"], ids=ids(BODIES["refused"]))
def test_a_refused_body_on_python_alone_and_at_preflight(world, row):
    raw = body_in_this_brain(world, public_body(row))
    want = REFUSALS[row["refused"]]
    got = send(world.alone, DOOR["target"], [*JSON_HEADERS, ["Content-Length", str(len(raw))]], raw)
    assert got["status"] == want["status"]
    assert got["body"].decode() == words_in_this_brain(world, want["bytes"])
    before = record_size(world)
    answer = ask_preflight(world, raw)
    assert answer["state"] == "refused" and answer["status"] == want["status"]
    assert answer["body"] == json.loads(words_in_this_brain(world, want["bytes"]))
    assert answer["author"] == (world.who if row["author"] == AUTHOR else row["author"])
    assert answer["op"] == row["op"]
    assert record_size(world) == before


@pytest.mark.parametrize("row", BODIES["accepted"], ids=ids(BODIES["accepted"]))
def test_an_accepted_body_on_python_alone_is_no_processor_and_records_nothing(world, row):
    raw = body_in_this_brain(world, public_body(row))
    before = record_size(world)
    for target in BODIES["python_alone"]["paths"]:
        got = send(world.alone, target, [*JSON_HEADERS, ["Content-Length", str(len(raw))]], raw)
        assert got["status"] == 503 and got["body"].decode() == REFUSALS["processor-unavailable"]["bytes"]
    assert record_size(world) == before


def test_python_alone_refuses_a_forged_page_and_never_records(world):
    raw = json.dumps({"author": world.who, "op": OP, "page": {"sources": []}}).encode()
    for target in BODIES["python_alone"]["paths"]:
        got = send(world.alone, target, [*JSON_HEADERS, ["Content-Length", str(len(raw))]], raw)
        assert got["status"] == 400 and got["body"].decode() == REFUSALS["body-fields"]["bytes"]
    assert act_of(world, X.MAGNET_EXTRACTED) == []


def test_a_rolled_back_rule_behind_a_secret_answers_the_same_on_the_public_path(world):
    raw = asked_body(world)
    got = send(world.front, DOOR["target"], [*JSON_HEADERS, ["Content-Length", str(len(raw))]], raw)
    assert got["status"] == 503 and json.loads(got["body"])["kind"] == "ProcessorUnavailable"


@pytest.mark.parametrize("segment", ["mag-bad!", "mag-a%2fb", "mag-"])
def test_a_malformed_id_is_asked_of_the_raw_segment_whatever_the_body(world, segment):
    assert ask_preflight(world, b"{", segment) == {
        "protocol": 1, "state": "refused", "magnet": segment, "author": None, "op": None,
        "status": 400, "body": REFUSALS["magnet-id"]["body"]}
    got = send(world.alone, f"/fluid/api/magnets/{segment}/activate",
               [*JSON_HEADERS, ["Content-Length", "1"]], b"{")
    assert got["status"] == 400 and got["body"].decode() == REFUSALS["magnet-id"]["bytes"]


# -- the private paths ----------------------------------------------------------------------------

def test_the_private_paths_need_the_exact_secret(world):
    body = preflight_wire(asked_body(world))
    want = DOOR["private"]["private_port_without_secret"]
    for sent in ([], [["X-Mentis-Boot-Secret", "wrong"]]):
        for target in (PREFLIGHT, COMMIT):
            got = send(world.front, target, [["Content-Type", "application/json"], *sent], body)
            assert got["status"] == want["status"] and got["body"].decode() == want["body"]


def test_python_alone_has_neither_private_path_and_nothing_else_is_one(world):
    body = preflight_wire(asked_body(world))
    alone = DOOR["private"]["python_alone"]
    for target in (PREFLIGHT, COMMIT):
        got = send(world.alone, target, JSON_HEADERS, body)
        assert got["status"] == alone["status"] and got["body"].decode() == alone["body"]
        got = send(world.alone, target, [["X-Mentis-Boot-Secret", SECRET], *JSON_HEADERS], body)
        assert got["status"] == alone["status"]
    sent = [["X-Mentis-Boot-Secret", SECRET], ["Content-Type", "application/json"]]
    for target in (PREFLIGHT + "/", COMMIT + "/", f"/private/magnets/{MAGNET}/activate",
                   f"/private/magnets/{MAGNET}/activate/other"):
        assert send(world.front, target, sent, body)["status"] == 404, target
    assert send(world.front, PREFLIGHT, sent, b"", method="GET")["status"] == 404


@pytest.mark.parametrize("row", REQUESTS["preflight_refused"], ids=ids(REQUESTS["preflight_refused"]))
def test_a_preflight_request_that_is_not_one_is_a_protocol_error(world, row):
    got = private(world, PREFLIGHT, row["wire_text"].encode())
    answer = json.loads(got["body"])
    assert got["status"] == 200
    assert (answer["state"], answer["author"], answer["op"]) == ("internal-protocol-error", None, None)
    assert answer["status"] == 502 and answer["body"] == REFUSALS["internal-protocol-error"]["body"]


@pytest.mark.parametrize("row", REQUESTS["preflight_malformed_magnet"], ids=ids(REQUESTS["preflight_malformed_magnet"]))
def test_a_malformed_id_reaches_preflight_as_requested(world, row):
    got = private(world, row["path"], row["wire_text"].encode())
    answer = json.loads(got["body"])
    assert (answer["state"], answer["magnet"], answer["status"]) == ("refused", row["segment"], 400)
    assert answer["body"] == REFUSALS[row["answer"]]["body"]


def test_a_preflight_request_past_the_private_bound_is_not_read(world):
    sent = [["X-Mentis-Boot-Secret", SECRET], ["Content-Type", "application/json"],
            ["Content-Length", "9" * 5000]]
    got = send(world.front, PREFLIGHT, sent, b"")
    answer = json.loads(got["body"])
    assert answer["state"] == "internal-protocol-error" and got["closes"]


# -- the definition -------------------------------------------------------------------------------

@pytest.mark.parametrize("row", DEFINITIONS["executable"], ids=ids(DEFINITIONS["executable"]))
def test_what_can_run(world, row):
    world.define(row["definition"])
    answer = ask_preflight(world, asked_body(world))
    if row["answer"] == "ready":
        raw = world.definition_path.read_bytes()
        assert answer["state"] == "ready" and list(answer) == ["protocol", "state", "magnet", "request", "definition"]
        assert answer["request"] == {"author": world.who, "op": OP, "identity": RESULTS["identity"]}
        assert answer["definition"] == {"sha256": hashlib.sha256(raw).hexdigest(),
                                        "raw": raw.decode(), "value": row["value"]}
        assert json.dumps(answer["definition"]["value"]) == json.dumps(row["value"])
        return
    assert (answer["state"], answer["author"], answer["op"]) == ("refused", world.who, OP)
    assert json.dumps(answer["body"]) == REFUSALS[row["answer"]]["bytes"]
    assert answer["status"] == REFUSALS[row["answer"]]["status"]


def file_bytes(row) -> bytes | None:
    if "pad" in row:
        return filled(row["pad"])
    return base64.b64decode(row["file_base64"]) if "file_base64" in row else None


@pytest.mark.parametrize("row", DEFINITIONS["files"], ids=ids(DEFINITIONS["files"]))
def test_what_a_definition_file_answers_at_preflight(world, row):
    raw = file_bytes(row)
    if raw is not None:
        world.define(raw)
    answer = ask_preflight(world, asked_body(world))
    if row["answer"] == "ready":
        assert answer["state"] == "ready"
        assert answer["definition"]["raw"].encode("utf-8") == raw, "exact bytes, line endings and all"
        assert answer["definition"]["sha256"] == row["sha256"]
        assert world.definition_path.read_bytes() == raw, "nothing rewrites it"
    elif row["answer"] == "unreadable":
        assert (answer["state"], answer["status"]) == ("refused", 409)
        assert answer["body"]["kind"] == "Unreadable"
        assert answer["body"]["error"].startswith(row["error_starts"])
    else:
        assert answer["body"] == REFUSALS[row["answer"]]["body"], answer
        assert answer["status"] == REFUSALS[row["answer"]]["status"]


def test_an_unlifted_magnet_is_lifted_not_a_false_404_and_the_lifted_file_is_the_snapshot(world):
    plain = next(r for r in DEFINITIONS["executable"] if r["id"] == "plain")["value"]
    layout = A.check({"format": A.FORMAT, "version": 3,
                      "tree": {"type": "zone", "id": "stage", "show": "objects"},
                      "magnets": {MAGNET: plain}})
    W._atomic(pathlib.Path(world.root) / "presentation" / A.FOLDER / "ent-a.json",
              {"key": "ent-a", "layout": layout, "saved": 1.0, "ops": []})
    assert not world.definition_path.exists()
    answer = ask_preflight(world, asked_body(world))
    assert answer["state"] == "ready", answer
    assert answer["definition"]["raw"].encode("utf-8") == world.definition_path.read_bytes()


def test_a_replay_neither_lifts_nor_reads(world, monkeypatch):
    committed(world)
    world.definition_path.unlink()
    monkeypatch.setattr(A, "lift_all", lambda root: pytest.fail("a replay lifted"))
    monkeypatch.setattr(X, "_snapshot", lambda *a: pytest.fail("a replay read the definition"))
    assert ask_preflight(world, asked_body(world))["state"] == "replay"


def test_a_key_comes_before_anything_about_the_magnet(world):
    world.define(b"not a definition")
    anchors.keyed(world.cv, world.who, OP, {"route": "another"}, lambda: {"done": True})
    answer = ask_preflight(world, asked_body(world))
    assert (answer["state"], answer["status"]) == ("refused", 422)
    assert answer["body"]["error"] == REFUSALS["key-collision"]["body"]["error"]
    assert (answer["author"], answer["op"]) == (world.who, OP)


# -- the commit: spoiled artifacts ---------------------------------------------------------------

def spoil(world, row) -> tuple[bytes, str]:
    good = artifact_of(world)
    if "bytes_text" in row or "bytes_nest" in row:
        raw = row["bytes_text"].encode() if "bytes_text" in row else nested(row["bytes_nest"])
        return raw, hashlib.sha256(raw).hexdigest()
    if "header_sha256" in row:
        return good, row["header_sha256"]
    art = copy.deepcopy(json.loads(good))
    at = art
    for step in row["set"][:-1]:
        at = at[step]
    at[row["set"][-1]] = json.loads(row["to_json"]) if "to_json" in row else row["to"]
    raw = json.dumps(art).encode()
    return raw, hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("row", ARTIFACTS["verification"], ids=ids(ARTIFACTS["verification"]))
def test_a_spoiled_artifact_writes_nothing(world, row):
    define_from(world, artifact_of(world))
    before = record_size(world)
    blobs = held.blobs(str(world.root))
    raw, digest = spoil(world, row)
    answer = ask_commit(world, raw, digest=digest)
    assert answer["state"] == row["state"], answer
    assert answer["author"] == (world.who if row["author"] == AUTHOR else row["author"])
    assert answer["op"] == row["op"]
    if row["state"] == "refused":
        assert answer["body"] == REFUSALS[row["refused"]]["body"]
        assert answer["status"] == REFUSALS[row["refused"]]["status"]
    else:
        assert answer["status"] == 502 and answer["body"] == REFUSALS["internal-protocol-error"]["body"]
    assert record_size(world) == before
    assert held.blobs(str(world.root)) == blobs, "no bytes are held for what isn't recorded"


@pytest.mark.parametrize("name", ["complete", "partial-non-ascii", "linked-and-objects"])
def test_a_good_artifact_is_recorded_as_its_exact_bytes(world, name):
    raw = artifact_of(world, name)
    define_from(world, raw)
    answer = ask_commit(world, raw)
    assert answer["state"] == "committed", answer
    stored = answer["body"]["artifact"]
    assert stored["digest"] == hashlib.sha256(raw).hexdigest() and stored["size"] == len(raw)
    assert held.read(str(world.root), stored["digest"]) == raw


@pytest.mark.parametrize("spoiled, why", [
    (lambda raw: raw.decode().encode("utf-16"), "utf-16 isn't this format's encoding"),
    (lambda raw: raw[:-1] + b', "extra": NaN}', "a constant JSON doesn't have"),
    (lambda raw: b"\xef\xbb\xbf" + raw, "a byte-order mark"),
    (lambda raw: raw[:-1] + b', "extra": 1}', "a field the artifact doesn't have"),
])
def test_bytes_that_are_not_the_format_are_a_protocol_error(world, spoiled, why):
    raw = spoiled(artifact_of(world))
    assert ask_commit(world, raw)["state"] == "internal-protocol-error", why


def test_a_commit_must_be_declared_json(world):
    raw = artifact_of(world)
    define_from(world, raw)
    assert ask_commit(world, raw, ctype="text/plain")["state"] == "internal-protocol-error"
    assert act_of(world, X.MAGNET_EXTRACTED) == []


def test_what_could_not_be_answered_is_refused_before_the_write(world):
    """Past the bound, the record could be written and its answer be too big to send."""
    def huge(art):
        art["page"]["kept"] = [{"facet": "f" * 70000, "reason": "kept"}]
    raw = artifact_of(world, change=huge)
    define_from(world, raw)
    assert ask_commit(world, raw)["state"] == "internal-protocol-error"
    assert act_of(world, X.MAGNET_EXTRACTED) == []


@pytest.mark.parametrize("cursor", [
    "f1.-1.0.0", "f1.+1.0.0", "f1.1_0.0.0", "f1. 1.0.0", "f1.1 .0.0", "f1.\u0661.0.0", "f1.1.0.\uff11", "f1.01.0.0",
    "f1.1.0.0\n", "f1.1.0", "f1.1.0.0.0", "f2.1.0.0", "F1.1.0.0", "f1..0.0", "f1." + "1" * 21 + ".0.0", "",
])
def test_a_page_cursor_change_cursor_could_not_have_written_is_a_protocol_error(world, cursor):
    raw = artifact_of(world, change=lambda art: art["page"].__setitem__("cursor", cursor))
    define_from(world, raw)
    before = record_size(world)
    answer = ask_commit(world, raw)
    assert (answer["state"], answer["status"]) == ("internal-protocol-error", 502)
    assert record_size(world) == before


@pytest.mark.parametrize("cursor", ["f1.0.0.0", "f1.10.200.3000", "f1.18446744073709551615.0.1"])
def test_a_page_cursor_change_cursor_could_have_written_is_taken(world, cursor):
    raw = artifact_of(world, change=lambda art: art["page"].__setitem__("cursor", cursor))
    define_from(world, raw)
    assert ask_commit(world, raw)["state"] == "committed"


def test_the_shared_cursor_reader_takes_what_it_always_took():
    from mentis.fluid import read
    assert read.parse_change_cursor("f1.+1.1_0. 2") == (1, 10, 2)


def test_a_result_on_a_source_that_answered_nothing_is_inconsistent(world):
    def busy_with_results(art):
        art["page"]["sources"][0]["status"] = "busy"
    raw = artifact_of(world, change=busy_with_results)
    define_from(world, raw)
    assert ask_commit(world, raw)["state"] == "internal-protocol-error"


@pytest.mark.parametrize("field", sorted(X._RESULT_KEEPS))
def test_a_result_that_lost_its_provenance_is_a_protocol_error(world, field):
    def lose(art):
        del art["page"]["sources"][0]["results"][0][field]
    raw = artifact_of(world, change=lose)
    define_from(world, raw)
    assert ask_commit(world, raw)["state"] == "internal-protocol-error"


@pytest.mark.parametrize("row", USEFUL, ids=ids(USEFUL))
def test_what_a_page_comes_to_at_commit(world, row):
    def shaped(art):
        one = art["page"]["sources"][0]
        result = one["results"][0]
        value = art["definition"]["value"]
        sources = [{"kind": "conversation", "conversation": f"ent-00000000000{i}"}
                   for i in range(len(row["sources"]))]
        said = json.loads(art["definition"]["raw"])
        said["sources"] = value["sources"] = sources
        art["definition"]["raw"] = json.dumps(said)
        art["definition"]["sha256"] = hashlib.sha256(art["definition"]["raw"].encode()).hexdigest()
        art["page"]["sources"] = [
            {"source": s, "key": f'conversation:{s["conversation"]}', "status": shape["status"],
             "reason": None, "summary": None,
             "results": [{**result, "conversation": s["conversation"], "id": f"ent-r{i}{n}"}
                         for n in range(shape["results"])],
             "next": None, "dates": one["dates"]}
            for i, (s, shape) in enumerate(zip(sources, row["sources"]))]
        art["page"]["kept"] = [{"facet": "phrases", "reason": "kept"}] * row["kept"]
    raw = artifact_of(world, change=shaped)
    define_from(world, raw)
    before = record_size(world)
    answer = ask_commit(world, raw)
    if row["decides"] in ("complete", "partial"):
        assert answer["state"] == "committed", answer
        assert answer["body"]["state"] == row["decides"]
    else:
        assert answer["state"] == "refused" and answer["body"] == REFUSALS[row["decides"]]["body"]
        assert record_size(world) == before


# -- the commit: what it records ------------------------------------------------------------------

def test_one_commit_records_the_whole_set(world):
    raw = artifact_of(world)
    define_from(world, raw)
    answer = ask_commit(world, raw)
    assert (answer["state"], answer["status"], answer["author"], answer["op"]) == ("committed", 201, world.who, OP)
    body = answer["body"]
    assert list(body) == [*RESULTS["complete"]["stored"], "replayed", "cursor"]
    assert body["replayed"] is False and body["cursor"].startswith("f1.")
    assert body["operation"] == RESULTS["complete"]["stored"]["operation"]
    assert body["page"] == RESULTS["complete"]["stored"]["page"]
    assert body["state"] == "complete" and body["conversation_created"] is True
    adm, post, cid = body["artifact"]["ref"], body["post"], body["conversation"]
    assert body["artifact"] == {"ref": adm, "digest": hashlib.sha256(raw).hexdigest(), "size": len(raw),
                                "media_type": "application/json"}
    # The Conversation, and the claim on it.
    assert commands._claimed(world.state, "magnet", MAGNET) == cid
    assert world.cv._is_kind(cid, "conversation")
    # The Turn, record-only, through `posting.post`, with its `turn-said`.
    said = [a for a in act_of(world, "turn-said") if a.get("turn") == post]
    assert len(said) == 1 and said[0]["detail"] == {"action": posting.RECORD_ONLY}
    assert said[0]["conversation"] == cid
    parts = world.corpus.read([post])[0]["body"]["parts"]
    assert [p["type"] for p in parts] == ["text", "file"]
    assert parts[1]["ref"] == adm and "cursor" not in parts[0]["text"]
    assert len(parts[0]["text"]) < 200, "the page isn't copied into its text"
    # The Admission, holding the exact bytes.
    described = artifacts.describe(world.corpus, adm)
    assert described["state"] == "held" and described["digest"] == body["artifact"]["digest"]
    # The act and what it made.
    made = act_of(world, X.MAGNET_EXTRACTED)
    assert len(made) == 1
    made = made[0]
    assert made["actor"] == world.who and made["conversation"] == cid and made["turn"] == post
    assert adm in made["about"]
    assert made["detail"]["magnet"] == MAGNET and made["detail"]["mode"] == "m1-page"
    assert made["detail"]["operation"] == {"index": 0, "name": None}
    assert made["detail"]["definition_sha256"] == json.loads(raw)["definition"]["sha256"]
    assert made["detail"]["page"] == {"cursor": body["page"]["cursor"], "state": "complete",
                                      "results": body["page"]["results"], "statuses": body["page"]["statuses"]}
    assert made["detail"]["artifact"] == {"ref": adm, "digest": body["artifact"]["digest"], "size": len(raw)}
    assert artifacts.producing_act(world.corpus, world.cv, adm)["id"] == made["id"]
    # Read back as any attached file is: while its Turn stands, in its Conversation.
    assert artifacts.in_conversation(world.corpus, world.cv, cid, adm)[0] is not None
    # The key.
    stored = anchors.prior_outcome(world.cv, world.who, OP, RESULTS["identity"])
    assert {k: v for k, v in stored.items() if k != "replayed"} == {
        k: v for k, v in body.items() if k not in ("replayed", "cursor")}
    # And after the commit, the file.
    assert json.loads(world.definition_path.read_text(encoding="utf-8"))["conversation"] == cid


def test_nothing_runs_from_a_record_only_turn(world, monkeypatch):
    import mentis.web as web
    monkeypatch.setattr(web, "dispatch_soon", lambda *a, **k: pytest.fail("something was dispatched"))
    body = committed(world)["body"]
    assert world.corpus.operational(act="expectation-recorded", conversation=body["conversation"], limit=1) == []


def test_a_replay_writes_nothing_and_answers_the_first_result_with_a_fresh_cursor(world):
    raw = artifact_of(world)
    define_from(world, raw)
    first = ask_commit(world, raw)["body"]
    before = record_size(world)
    # Through either phase, and after the Magnet changed or went.
    asked = ask_preflight(world, asked_body(world))
    world.define({**json.loads(json.loads(raw)["definition"]["raw"]), "presentation": {"renderer": "list"}})
    again = ask_commit(world, raw)
    world.definition_path.unlink()
    gone = ask_preflight(world, asked_body(world))
    for answer in (asked, again, gone):
        assert (answer["state"], answer["status"], answer["author"], answer["op"]) == ("replay", 200, world.who, OP)
        assert answer["body"]["replayed"] is True
        assert {k: v for k, v in answer["body"].items() if k not in ("replayed", "cursor")} == {
            k: v for k, v in first.items() if k not in ("replayed", "cursor")}
        # The first answer's bytes, but for the two fields that aren't stored (`results.json`).
        same = {**first, "replayed": True, "cursor": answer["body"]["cursor"]}
        assert json.dumps(answer["body"]) == json.dumps(same)
    assert record_size(world) == before
    assert not world.definition_path.exists(), "a replay doesn't correct or recreate anything"


def test_python_alone_answers_a_used_key_from_the_record_too(world):
    first = committed(world)["body"]
    raw = asked_body(world)
    got = send(world.alone, DOOR["target"], [*JSON_HEADERS, ["Content-Length", str(len(raw))]], raw)
    assert got["status"] == 200
    assert json.loads(got["body"])["post"] == first["post"]
    assert json.loads(got["body"])["replayed"] is True


def test_a_replay_keeps_the_frozen_page_and_a_new_top_level_cursor(world):
    first = committed(world)["body"]
    other = committed(world, op="activate-other")["body"]
    assert other["cursor"] != first["cursor"]
    replay = ask_preflight(world, asked_body(world))["body"]
    assert replay["page"]["cursor"] == first["page"]["cursor"]
    assert replay["cursor"] >= other["cursor"] > first["cursor"]


def test_a_key_used_for_another_request_at_commit(world):
    anchors.keyed(world.cv, world.who, OP, {"route": "another"}, lambda: {"done": True})
    before = record_size(world)
    raw = artifact_of(world)
    define_from(world, raw)
    blobs = held.blobs(str(world.root))
    answer = ask_commit(world, raw)
    assert (answer["state"], answer["status"], answer["author"], answer["op"]) == ("refused", 422, world.who, OP)
    assert answer["body"]["error"] == REFUSALS["key-collision"]["body"]["error"]
    assert list(answer["body"]) == list(REFUSALS["key-collision"]["body"])
    assert record_size(world) == before and held.blobs(str(world.root)) == blobs


def test_two_keys_two_turns_one_conversation_and_one_claim(world):
    first = committed(world)["body"]
    second = committed(world, op="activate-0002")["body"]
    assert first["conversation"] == second["conversation"]
    assert (first["conversation_created"], second["conversation_created"]) == (True, False)
    assert first["post"] != second["post"]
    assert len(act_of(world, commands.CONVERSATION_CLAIMED)) == 1


def test_the_same_key_twice_once_both_preflights_are_done_writes_once(world):
    raw = artifact_of(world)
    define_from(world, raw)
    assert ask_preflight(world, asked_body(world))["state"] == "ready"
    assert ask_preflight(world, asked_body(world))["state"] == "ready"
    assert ask_commit(world, raw)["state"] == "committed"
    assert ask_commit(world, raw)["state"] == "replay"
    assert len(act_of(world, X.MAGNET_EXTRACTED)) == 1


def test_a_definition_changed_after_preflight_keeps_what_it_ran_on(world):
    raw = artifact_of(world)
    define_from(world, raw)
    assert ask_preflight(world, asked_body(world))["state"] == "ready"
    captured = json.loads(raw)["definition"]
    world.define({**json.loads(captured["raw"]), "presentation": {"renderer": "list"}})
    body = ask_commit(world, raw)["body"]
    made = act_of(world, X.MAGNET_EXTRACTED)[0]
    assert made["detail"]["definition_sha256"] == captured["sha256"]
    held_art = json.loads(held.read(str(world.root), body["artifact"]["digest"]))
    assert held_art["definition"]["raw"] == captured["raw"]


@pytest.mark.parametrize("now", [b"not a definition", b'{"schema_version": 99}'])
def test_a_definition_no_longer_readable_after_preflight_still_exists(world, now):
    """Refused statuses at commit are the contract's: a 409 isn't one, and the artifact keeps its bytes."""
    raw = artifact_of(world)
    define_from(world, raw)
    world.define(now)
    answer = ask_commit(world, raw)
    assert answer["state"] == "committed", answer
    assert commands._claimed(world.state, "magnet", MAGNET) == answer["body"]["conversation"]
    assert world.definition_path.read_bytes() == now, "and it is left as it is"


def test_a_definition_deleted_after_preflight_writes_nothing_and_keeps_the_key(world):
    raw = artifact_of(world)
    define_from(world, raw)
    assert ask_preflight(world, asked_body(world))["state"] == "ready"
    world.definition_path.unlink()
    before, blobs = record_size(world), held.blobs(str(world.root))
    answer = ask_commit(world, raw)
    assert (answer["state"], answer["status"], answer["author"], answer["op"]) == ("refused", 422, world.who, OP)
    assert answer["body"] == REFUSALS["magnet-deleted"]["body"]
    assert record_size(world) == before and held.blobs(str(world.root)) == blobs
    define_from(world, raw)
    assert ask_commit(world, raw)["state"] == "committed", "no key was consumed"


def test_deleted_between_the_first_look_and_the_write_is_checked_again(world, monkeypatch):
    raw = artifact_of(world)
    define_from(world, raw)
    before = record_size(world)
    put = held.put

    def and_then_it_went(root, data):
        got = put(root, data)
        world.definition_path.unlink()
        return got
    monkeypatch.setattr(held, "put", and_then_it_went)
    answer = ask_commit(world, raw)
    assert answer["state"] == "refused" and answer["body"] == REFUSALS["magnet-deleted"]["body"]
    assert record_size(world) == before


def test_a_key_answered_between_the_first_look_and_the_write_is_a_replay(world, monkeypatch):
    raw = artifact_of(world)
    define_from(world, raw)
    first = ask_commit(world, artifact_of(world, op="activate-other"))
    assert first["state"] == "committed"
    real = X._keyed
    asked = []

    def key_is_taken_on_the_second_look(st, by, op, mid):
        asked.append(op)
        if len(asked) == 1:
            return real(st, by, op, mid)
        return {**first["body"], "replayed": True}
    monkeypatch.setattr(X, "_keyed", key_is_taken_on_the_second_look)
    before = record_size(world)
    answer = ask_commit(world, raw)
    assert answer["state"] == "replay" and answer["status"] == 200
    assert record_size(world) == before


# -- the one place --------------------------------------------------------------------------------

def test_a_commit_overlapping_the_place_is_busy_with_no_identity_and_unread(world, monkeypatch):
    raw = artifact_of(world)
    define_from(world, raw)
    read = []
    original = _Handler._read_body
    monkeypatch.setattr(_Handler, "_read_body", lambda self, n: (read.append(n), original(self, n))[1])
    assert X.COMMIT_PLACE.acquire(blocking=False)
    try:
        sent = [["X-Mentis-Boot-Secret", SECRET], ["Content-Type", "application/json"],
                [X.DIGEST_HEADER, hashlib.sha256(raw).hexdigest()]]
        got = send(world.front, COMMIT, sent, raw)
    finally:
        X.COMMIT_PLACE.release()
    answer = json.loads(got["body"])
    assert got["status"] == 200 and got["closes"], "its unread body can't be read as the next request"
    assert (answer["state"], answer["status"], answer["author"], answer["op"]) == ("refused", 503, None, None)
    assert answer["body"] == REFUSALS["busy"]["body"]
    assert read == [] and act_of(world, X.MAGNET_EXTRACTED) == []


def stalled(world, head_length, sent: bytes) -> bytes:
    """What a commit that declared `head_length` bytes and sent `sent`, keeping its connection open, is told."""
    head = (f"POST {COMMIT} HTTP/1.1\r\nHost: 127.0.0.1:{world.front}\r\nX-Mentis-Boot-Secret: {SECRET}\r\n"
            f"Content-Type: application/json\r\n{X.DIGEST_HEADER}: {'0' * 64}\r\n"
            f"Content-Length: {head_length}\r\n\r\n").encode()
    with socket.create_connection(("127.0.0.1", world.front), timeout=30) as sock:
        sock.sendall(head + sent)
        got = b""
        while chunk := sock.recv(1 << 16):
            got += chunk
    return got


def test_a_stalled_commit_body_gives_the_place_back_and_writes_nothing(world, monkeypatch):
    monkeypatch.setattr(X, "COMMIT_BODY_S", 0.4)
    define_from(world, artifact_of(world))
    before = record_size(world)
    got = stalled(world, 1000, b"x" * 10)
    head, _, body = got.partition(b"\r\n\r\n")
    assert b"200 OK" in head and b"Connection: close" in head
    answer = json.loads(body)
    assert (answer["state"], answer["status"], answer["author"], answer["op"]) == (
        "internal-protocol-error", 502, None, None)
    assert answer["body"] == REFUSALS["internal-protocol-error"]["body"]
    assert record_size(world) == before
    assert X.COMMIT_PLACE.acquire(blocking=False)
    X.COMMIT_PLACE.release()
    # And the next commit goes through.
    assert committed(world)["state"] == "committed"


def test_a_body_trickled_past_the_bound_is_cut_off_all_the_same(world, monkeypatch):
    monkeypatch.setattr(X, "COMMIT_BODY_S", 0.5)
    define_from(world, artifact_of(world))
    head = (f"POST {COMMIT} HTTP/1.1\r\nHost: 127.0.0.1:{world.front}\r\nX-Mentis-Boot-Secret: {SECRET}\r\n"
            f"Content-Type: application/json\r\n{X.DIGEST_HEADER}: {'0' * 64}\r\n"
            f"Content-Length: 100000\r\n\r\n").encode()
    stop = threading.Event()
    with socket.create_connection(("127.0.0.1", world.front), timeout=30) as sock:
        sock.sendall(head)

        def trickle():
            while not stop.wait(0.05):
                try:
                    sock.sendall(b"x")
                except OSError:
                    return
        sender = threading.Thread(target=trickle, daemon=True)
        sender.start()
        got = b""
        while b"\r\n\r\n" not in got or not got.rstrip().endswith(b"}"):
            chunk = sock.recv(1 << 16)
            if not chunk:
                break
            got += chunk
        stop.set()
        sender.join(5)
    assert json.loads(got.partition(b"\r\n\r\n")[2])["status"] == 502
    assert act_of(world, X.MAGNET_EXTRACTED) == []


def test_a_body_that_comes_in_pieces_in_time_is_read_whole(world):
    raw = artifact_of(world)
    define_from(world, raw)
    head = (f"POST {COMMIT} HTTP/1.1\r\nHost: 127.0.0.1:{world.front}\r\nX-Mentis-Boot-Secret: {SECRET}\r\n"
            f"Content-Type: application/json\r\n{X.DIGEST_HEADER}: {hashlib.sha256(raw).hexdigest()}\r\n"
            f"Content-Length: {len(raw)}\r\n\r\n").encode()
    with socket.create_connection(("127.0.0.1", world.front), timeout=30) as sock:
        sock.sendall(head)
        for at in range(0, len(raw), 512):
            sock.sendall(raw[at:at + 512])
        sock.shutdown(socket.SHUT_WR)
        got = b""
        while chunk := sock.recv(1 << 16):
            got += chunk
    assert json.loads(got.partition(b"\r\n\r\n")[2])["state"] == "committed"


def test_the_place_goes_back_whatever_became_of_the_commit(world, monkeypatch):
    raw = artifact_of(world)
    define_from(world, raw)
    monkeypatch.setattr(anchors, "record_outcome", lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    got = send(world.front, COMMIT, [["X-Mentis-Boot-Secret", SECRET], ["Content-Type", "application/json"],
                                     [X.DIGEST_HEADER, hashlib.sha256(raw).hexdigest()]], raw)
    assert got["status"] == 500
    assert X.COMMIT_PLACE.acquire(blocking=False)
    X.COMMIT_PLACE.release()


@pytest.mark.parametrize("length", [str(X.ARTIFACT_MOST + 1), "9" * 4301, "0" * 5000 + str(X.ARTIFACT_MOST + 1)])
def test_an_artifact_past_the_cap_is_refused_unread(world, length):
    define_from(world, artifact_of(world))
    got = send(world.front, COMMIT, [["X-Mentis-Boot-Secret", SECRET], ["Content-Type", "application/json"],
                                     ["Content-Length", length], [X.DIGEST_HEADER, "0" * 64]], b"")
    answer = json.loads(got["body"])
    assert (answer["state"], answer["status"], answer["author"], answer["op"]) == ("refused", 413, None, None)
    assert answer["body"] == REFUSALS["artifact-too-large"]["body"]
    assert got["closes"]


# -- what a failure leaves ------------------------------------------------------------------------

STEPS = {"the-claim": (commands, "_claim"),
         "the-admission": (artifacts, "admit_generated"), "the-turn": (posting, "post"),
         "the-act": (artifacts, "record_generated"), "the-key": (anchors, "record_outcome")}


@pytest.mark.parametrize("step", list(STEPS))
def test_a_failure_at_any_step_leaves_no_subset_of_the_set(world, monkeypatch, step):
    """Whichever fails, nothing is committed, the blob is inert, and the same key runs again."""
    raw = artifact_of(world)
    define_from(world, raw)
    before = record_size(world)
    module, name = STEPS[step]
    real = getattr(module, name)

    def failing(*a, **k):
        real(*a, **k)
        raise OSError("the machine went")
    monkeypatch.setattr(module, name, failing)
    got = send(world.front, COMMIT, [["X-Mentis-Boot-Secret", SECRET], ["Content-Type", "application/json"],
                                     [X.DIGEST_HEADER, hashlib.sha256(raw).hexdigest()]], raw)
    assert got["status"] == 500, "not a complete answer, so Rust says OutcomeUnknown"
    monkeypatch.undo()
    assert record_size(world) == before, "no proper subset"
    assert act_of(world, X.MAGNET_EXTRACTED) == [] and commands._claimed(world.state, "magnet", MAGNET) is None
    assert anchors.prior_outcome(world.cv, world.who, OP, RESULTS["identity"]) is None
    digest = hashlib.sha256(raw).hexdigest()
    assert held.has(str(world.root), digest), "held bytes may precede the transaction"
    assert digest in artifacts.discard_unnamed(world.corpus, older_than_s=1e9)["kept_younger"]
    assert ask_commit(world, raw)["state"] == "committed"


def name_in_the_file(world, raw) -> str:
    """A Magnet from before claims: its file names a Conversation the record holds, and nothing claims it."""
    named = world.cv.open_conversation("Mine", about="", attributed_to=world.who, written_by="t", provisional=False)
    world.cv.join(world.who, named, attributed_to=world.who, written_by="t")
    world.define({**json.loads(json.loads(raw)["definition"]["raw"]), "conversation": named})
    return named


@pytest.mark.parametrize("step", list(STEPS))
def test_a_failure_at_any_step_leaves_a_file_s_conversation_unclaimed(world, monkeypatch, step):
    raw = artifact_of(world)
    named = name_in_the_file(world, raw)
    before = record_size(world)
    module, name = STEPS[step]
    real = getattr(module, name)

    def failing(*a, **k):
        real(*a, **k)
        raise OSError("the machine went")
    monkeypatch.setattr(module, name, failing)
    got = send(world.front, COMMIT, [["X-Mentis-Boot-Secret", SECRET], ["Content-Type", "application/json"],
                                     [X.DIGEST_HEADER, hashlib.sha256(raw).hexdigest()]], raw)
    assert got["status"] == 500
    monkeypatch.undo()
    assert record_size(world) == before, "no proper subset"
    assert commands._claimed(world.state, "magnet", MAGNET) is None
    again = ask_commit(world, raw)
    assert again["state"] == "committed" and again["body"]["conversation"] == named
    assert commands._claimed(world.state, "magnet", MAGNET) == named


def test_a_turn_refused_inside_the_write_leaves_a_file_s_conversation_unclaimed(world, monkeypatch):
    raw = artifact_of(world)
    name_in_the_file(world, raw)
    before = record_size(world)
    monkeypatch.setattr(posting, "post", lambda *a, **k: ({"error": "not here"}, []))
    answer = ask_commit(world, raw)
    assert (answer["state"], answer["status"]) == ("refused", 422)
    assert record_size(world) == before and commands._claimed(world.state, "magnet", MAGNET) is None


def test_a_crash_after_the_bytes_and_before_the_record_names_nothing(world, monkeypatch):
    raw = artifact_of(world)
    define_from(world, raw)
    before = record_size(world)
    monkeypatch.setattr(X, "_record", lambda *a: (_ for _ in ()).throw(OSError("the machine went")))
    got = send(world.front, COMMIT, [["X-Mentis-Boot-Secret", SECRET], ["Content-Type", "application/json"],
                                     [X.DIGEST_HEADER, hashlib.sha256(raw).hexdigest()]], raw)
    assert got["status"] == 500
    assert record_size(world) == before
    assert artifacts.discard_unnamed(world.corpus, older_than_s=0)["removed"] == [hashlib.sha256(raw).hexdigest()]


# -- the Conversation, and the file that follows it -----------------------------------------------

def test_a_file_that_cannot_be_told_refuses_nothing_and_a_later_request_corrects_it(world, monkeypatch):
    raw = artifact_of(world)
    define_from(world, raw)
    told = []

    def full(root, mid, cid):
        told.append(cid)
        raise OSError("disk full")
    monkeypatch.setattr(M, "correct_conversation", full)
    first = ask_commit(world, raw)
    assert first["state"] == "committed" and told == [first["body"]["conversation"]]
    cid = first["body"]["conversation"]
    assert "conversation" not in json.loads(world.definition_path.read_text(encoding="utf-8"))
    # The claim and the answer stand, and a replay answers them, and tells nothing.
    told.clear()
    assert ask_commit(world, raw)["body"]["conversation"] == cid and told == []
    monkeypatch.undo()
    assert ask_preflight(world, asked_body(world))["state"] == "replay"
    assert "conversation" not in json.loads(world.definition_path.read_text(encoding="utf-8"))
    # A later request does.
    later = ask_commit(world, artifact_of(world, op="activate-later"))
    assert later["state"] == "committed" and later["body"]["conversation"] == cid
    assert json.loads(world.definition_path.read_text(encoding="utf-8"))["conversation"] == cid


def test_a_file_naming_another_conversation_is_corrected_from_the_claim(world):
    first = committed(world)["body"]
    other = world.cv.open_conversation("Other", about="", attributed_to=world.who, written_by="t", provisional=False)
    raw = artifact_of(world, op="activate-0002")
    world.define({**json.loads(json.loads(raw)["definition"]["raw"]), "conversation": other})
    second = ask_commit(world, raw)["body"]
    assert second["conversation"] == first["conversation"]
    assert json.loads(world.definition_path.read_text(encoding="utf-8"))["conversation"] == first["conversation"]


def test_a_magnet_from_before_claims_claims_the_conversation_its_file_names(world):
    """Used, nothing new opened, and claimed in the commit, for good: it survives the Magnet's going."""
    raw = artifact_of(world)
    named = name_in_the_file(world, raw)
    conversations = len(world.corpus.entries_of_kind("conversation"))
    body = ask_commit(world, raw)["body"]
    assert body["conversation"] == named and body["conversation_created"] is False
    assert commands._claimed(world.state, "magnet", MAGNET) == named
    claims = act_of(world, commands.CONVERSATION_CLAIMED)
    assert len(claims) == 1 and claims[0]["actor"] == world.who and claims[0]["conversation"] == named
    # Twice is once, and a later key adds no second claim.
    assert ask_commit(world, raw)["state"] == "replay"
    later = committed(world, op="activate-0002")["body"]
    assert later["conversation"] == named and len(act_of(world, commands.CONVERSATION_CLAIMED)) == 1
    # Removed and recreated, the file naming nothing: the same Conversation, and none opened.
    world.definition_path.unlink()
    again = committed(world, op="activate-0003")["body"]
    assert again["conversation"] == named and again["conversation_created"] is False
    assert len(world.corpus.entries_of_kind("conversation")) == conversations
    assert len(act_of(world, commands.CONVERSATION_CLAIMED)) == 1
    assert json.loads(world.definition_path.read_text(encoding="utf-8"))["conversation"] == named


def test_a_magnet_from_before_claims_comes_back_through_delete_and_create(world):
    raw = artifact_of(world)
    named = name_in_the_file(world, raw)
    assert ask_commit(world, raw)["body"]["conversation"] == named
    gone = send(world.alone, f"/fluid/api/magnets/{MAGNET}/delete", JSON_HEADERS, b"{}")
    assert gone["status"] == 200 and json.loads(gone["body"])["deleted"] is True
    assert not world.definition_path.exists()
    seed = {k: v for k, v in json.loads(json.loads(raw)["definition"]["raw"]).items()
            if k not in ("id", "schema_version", "conversation")}
    made = A.create_magnet(str(world.root), "ent-a", {"id": MAGNET, "seed": seed, "attach": {
        "zone": {"type": "zone", "show": "magnet", "name": "Board"},
        "base": {"format": A.FORMAT, "version": 3, "tree": {"type": "zone", "id": "stage", "show": "objects"}}}})
    assert made and not json.loads(world.definition_path.read_text(encoding="utf-8")).get("conversation")
    # By whichever door and whoever asks, the same one.
    route = f"/fluid/api/magnets/{MAGNET}/conversation"
    got = json.loads(send(world.alone, route, JSON_HEADERS, json.dumps({"author": world.other}).encode())["body"])
    assert got["conversation"] == named and got["created"] is False
    again = ask_commit(world, artifact_of(world, op="activate-0002"))["body"]
    assert again["conversation"] == named and again["conversation_created"] is False
    assert len(act_of(world, commands.CONVERSATION_CLAIMED)) == 1


def test_a_file_naming_what_is_no_conversation_opens_one_and_claims_that(world):
    raw = artifact_of(world)
    world.define({**json.loads(json.loads(raw)["definition"]["raw"]), "conversation": world.who})
    body = ask_commit(world, raw)["body"]
    assert body["conversation"] != world.who and body["conversation_created"] is True
    assert commands._claimed(world.state, "magnet", MAGNET) == body["conversation"]


def test_the_request_door_still_uses_a_file_s_conversation_without_claiming_it(world):
    """Only activation claims it: the other doors' answer stays as it is recorded."""
    named = world.cv.open_conversation("Mine", about="", attributed_to=world.who, written_by="t", provisional=False)
    assert commands._own_from(world.state, world.who, "magnet", MAGNET, named, None, "t") == (named, False)
    assert commands._claimed(world.state, "magnet", MAGNET) is None


def test_beside_the_conversation_route_one_claim_and_no_orphan(world):
    raw = artifact_of(world)
    define_from(world, raw)
    before = len(world.corpus.entries_of_kind("conversation"))
    route = f"/fluid/api/magnets/{MAGNET}/conversation"
    opened = send(world.alone, route, JSON_HEADERS, json.dumps({"author": world.other}).encode())
    assert opened["status"] in (200, 201)
    cid = json.loads(opened["body"])["conversation"]
    body = ask_commit(world, raw)["body"]
    assert body["conversation"] == cid and body["conversation_created"] is False
    again = json.loads(send(world.alone, route, JSON_HEADERS, json.dumps({"author": world.who}).encode())["body"])
    assert again["conversation"] == cid
    assert len(world.corpus.entries_of_kind("conversation")) == before + 1
    assert len(act_of(world, commands.CONVERSATION_CLAIMED)) == 1


def test_activation_first_then_the_conversation_route_answers_the_same(world):
    body = committed(world)["body"]
    route = f"/fluid/api/magnets/{MAGNET}/conversation"
    got = json.loads(send(world.alone, route, JSON_HEADERS, json.dumps({"author": world.other}).encode())["body"])
    assert got["conversation"] == body["conversation"] and got["created"] is False


def test_racing_the_conversation_route_makes_one_conversation(world):
    raw = artifact_of(world)
    define_from(world, raw)
    before = len(world.corpus.entries_of_kind("conversation"))
    route = f"/fluid/api/magnets/{MAGNET}/conversation"
    answers = {}

    def activate():
        answers["commit"] = ask_commit(world, raw)["body"]["conversation"]

    def open_it():
        answers["route"] = json.loads(send(world.alone, route, JSON_HEADERS,
                                           json.dumps({"author": world.other}).encode())["body"])["conversation"]
    threads = [threading.Thread(target=activate), threading.Thread(target=open_it)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert answers["commit"] == answers["route"]
    assert len(world.corpus.entries_of_kind("conversation")) == before + 1
    assert len(act_of(world, commands.CONVERSATION_CLAIMED)) == 1


# -- the key the Magnet Conversation route uses, on this door ------------------------------------------

MAGNET_KEY = f"magnet-conversation:{MAGNET}"


def recovered_by_its_key(world, op, first):
    """Every way back to `first` under the same key: it writes nothing and answers the same."""
    before = record_size(world)
    raw = artifact_of(world, op=op)
    answers = [ask_commit(world, raw), ask_preflight(world, asked_body(world, op=op))]
    for answer in answers:
        assert (answer["state"], answer["status"], answer["op"]) == ("replay", 200, op), answer
        assert answer["body"]["post"] == first["post"] and answer["body"]["replayed"] is True
        assert answer["body"]["conversation"] == first["conversation"]
    wire = asked_body(world, op=op)
    got = send(world.alone, DOOR["target"], [*JSON_HEADERS, ["Content-Length", str(len(wire))]], wire)
    assert got["status"] == 200 and json.loads(got["body"])["post"] == first["post"]
    assert json.loads(got["body"])["replayed"] is True
    assert record_size(world) == before
    assert len(act_of(world, X.MAGNET_EXTRACTED)) == 1


def public_before(world, op):
    wire = asked_body(world, op=op)
    got = send(world.alone, DOOR["target"], [*JSON_HEADERS, ["Content-Length", str(len(wire))]], wire)
    assert got["status"] == 503 and json.loads(got["body"])["kind"] == "ProcessorUnavailable"


def test_the_route_s_key_on_the_activation_that_opens_the_conversation(world):
    raw = artifact_of(world, op=MAGNET_KEY)
    define_from(world, raw)
    public_before(world, MAGNET_KEY)
    assert ask_preflight(world, asked_body(world, op=MAGNET_KEY))["state"] == "ready"
    answer = ask_commit(world, raw)
    assert answer["state"] == "committed" and answer["body"]["conversation_created"] is True
    # Two rows under one author and key, which is what the first retry used to refuse.
    assert len(world.corpus.operational(actor=world.who, act=anchors.KEYED,
                                        detail_is={"op": MAGNET_KEY}, limit=10)) == 2
    recovered_by_its_key(world, MAGNET_KEY, answer["body"])


def test_the_route_s_key_on_the_activation_of_a_conversation_the_route_opened(world):
    raw = artifact_of(world, op=MAGNET_KEY)
    define_from(world, raw)
    route = f"/fluid/api/magnets/{MAGNET}/conversation"
    opened = send(world.alone, route, JSON_HEADERS, json.dumps({"author": world.who}).encode())
    assert opened["status"] == 201
    cid = json.loads(opened["body"])["conversation"]
    public_before(world, MAGNET_KEY)
    assert ask_preflight(world, asked_body(world, op=MAGNET_KEY))["state"] == "ready"
    answer = ask_commit(world, raw)
    assert answer["state"] == "committed" and answer["body"]["conversation"] == cid
    assert answer["body"]["conversation_created"] is False
    recovered_by_its_key(world, MAGNET_KEY, answer["body"])


def test_the_route_s_key_on_the_activation_of_a_claimed_conversation_with_no_route_row(world):
    cid = committed(world, op="activate-first")["body"]["conversation"]
    raw = artifact_of(world, op=MAGNET_KEY)
    answer = ask_commit(world, raw)
    assert answer["state"] == "committed" and answer["body"]["conversation"] == cid
    before = len(act_of(world, X.MAGNET_EXTRACTED))
    again = ask_commit(world, raw)
    assert again["state"] == "replay" and again["body"]["post"] == answer["body"]["post"]
    assert len(act_of(world, X.MAGNET_EXTRACTED)) == before


def test_a_lost_answer_under_the_route_s_key_is_recovered_by_it(world, monkeypatch):
    raw = artifact_of(world, op=MAGNET_KEY)
    define_from(world, raw)
    # The commit stands and its answer never arrives: the failure comes after the record.
    monkeypatch.setattr(commands, "_tell_the_file", lambda *a: (_ for _ in ()).throw(ValueError("gone")))
    sent = [["X-Mentis-Boot-Secret", SECRET], ["Content-Type", "application/json"],
            [X.DIGEST_HEADER, hashlib.sha256(raw).hexdigest()]]
    assert send(world.front, COMMIT, sent, raw)["status"] == 500
    monkeypatch.undo()
    assert len(act_of(world, X.MAGNET_EXTRACTED)) == 1
    answer = ask_commit(world, raw)
    assert answer["state"] == "replay"
    recovered_by_its_key(world, MAGNET_KEY, answer["body"])


def test_a_commit_that_fails_under_the_route_s_key_runs_again_under_it(world, monkeypatch):
    raw = artifact_of(world, op=MAGNET_KEY)
    define_from(world, raw)
    before = record_size(world)
    monkeypatch.setattr(artifacts, "record_generated", lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    sent = [["X-Mentis-Boot-Secret", SECRET], ["Content-Type", "application/json"],
            [X.DIGEST_HEADER, hashlib.sha256(raw).hexdigest()]]
    assert send(world.front, COMMIT, sent, raw)["status"] == 500
    monkeypatch.undo()
    assert record_size(world) == before
    assert ask_commit(world, raw)["state"] == "committed"
    assert ask_commit(world, raw)["state"] == "replay"


def test_the_route_after_an_activation_under_its_key_answers_the_same_conversation(world):
    body = committed(world, op=MAGNET_KEY)["body"]
    route = f"/fluid/api/magnets/{MAGNET}/conversation"
    for who in (world.who, world.other):
        got = json.loads(send(world.alone, route, JSON_HEADERS, json.dumps({"author": who}).encode())["body"])
        assert got["conversation"] == body["conversation"] and got["created"] is False


def conversation_named(world, cid):
    return world.cv.conversation_name(cid)


def provisional_acts(world, cid):
    return [a for a in act_of(world, "conversation-provisionally-named") if a["conversation"] == cid]


def named_source(world, name):
    return world.cv.open_conversation(name, about="", attributed_to=world.who, written_by="t", provisional=False)


def test_an_activation_names_its_conversation_from_the_magnet(world):
    source = named_source(world, "Tidewater")
    raw = artifact_of(world, "complete")
    value = json.loads(json.loads(raw)["definition"]["raw"])
    world.define({**value, "sources": [{"kind": "conversation", "conversation": source}]})
    assert commands._magnet_conversation_name(world.state, MAGNET) == "Tidewater (Magnet)"
    world.define(value)
    body = ask_commit(world, raw)["body"]
    assert body["conversation_created"] is True
    assert not conversation_named(world, body["conversation"]).startswith("Unnamed")
    assert provisional_acts(world, body["conversation"]) == []


@pytest.mark.parametrize("who", ["route", "request"])
def test_each_other_door_names_it_by_the_same_rule_and_still_makes_one(world, who):
    source = named_source(world, "Tidewater")
    raw = artifact_of(world)
    value = json.loads(json.loads(raw)["definition"]["raw"])
    world.define({**value, "sources": [{"kind": "conversation", "conversation": source}]})
    if who == "route":
        route = f"/fluid/api/magnets/{MAGNET}/conversation"
        got = send(world.alone, route, JSON_HEADERS, json.dumps({"author": world.who}).encode())
        assert got["status"] == 201
        cid = json.loads(got["body"])["conversation"]
    else:
        with world.corpus.atomic():
            cid, created = commands._own_from(world.state, world.who, "magnet", MAGNET, None, None, "t")
        assert created is True
    assert conversation_named(world, cid) == "Tidewater (Magnet)"
    assert ask_commit(world, raw)["body"]["conversation"] == cid
    assert conversation_named(world, cid) == "Tidewater (Magnet)", "and is one claim, opened once"


def test_a_name_given_to_the_route_stands_and_a_bad_one_is_still_refused(world):
    raw = artifact_of(world)
    define_from(world, raw)
    route = f"/fluid/api/magnets/{MAGNET}/conversation"
    bad = send(world.alone, route, JSON_HEADERS, json.dumps({"author": world.who, "name": 7}).encode())
    assert bad["status"] == 400
    got = send(world.alone, route, JSON_HEADERS, json.dumps({"author": world.who, "name": "Mine"}).encode())
    assert conversation_named(world, json.loads(got["body"])["conversation"]) == "Mine"


def test_a_magnet_is_named_by_its_zone_then_its_operation_then_its_id(world):
    raw = artifact_of(world)
    value = {**json.loads(json.loads(raw)["definition"]["raw"]),
             "sources": [{"kind": "brain", "brain": "ent-a"}, {"kind": "web", "domain": "example.org"}]}
    name = lambda: commands._magnet_conversation_name(world.state, MAGNET)
    world.define({**value, "processing": {"operations": [{"op": "extract"}]}})
    assert name() == f"Magnet {MAGNET}"
    world.define({**value, "processing": {"operations": [{"op": "extract", "name": "Deployment check"}]}})
    assert name() == "Deployment check (Magnet)"
    A.create_magnet(str(world.root), "ent-a", {"id": MAGNET, "attach": {
        "zone": {"type": "zone", "show": "magnet", "name": "Board"},
        "base": {"format": A.FORMAT, "version": 3, "tree": {"type": "zone", "id": "stage", "show": "objects"}}}})
    assert name() == "Board (Magnet)"


def test_text_the_record_can_t_hold_never_becomes_a_name(world):
    raw = artifact_of(world)
    value = json.loads(json.loads(raw)["definition"]["raw"])
    world.define({**value, "sources": [{"kind": "brain", "brain": "ent-a"}],
                  "processing": {"operations": [{"op": "extract", "name": "\ud800"}]}})
    assert commands._magnet_conversation_name(world.state, MAGNET) == f"Magnet {MAGNET}"


def test_a_definition_that_can_t_be_read_is_still_named(world):
    world.define(b"not a definition")
    assert commands._magnet_conversation_name(world.state, MAGNET) == f"Magnet {MAGNET}"


def test_another_magnet_s_route_key_used_here_still_replays_when_that_route_records_it(world):
    other = "mag-another"
    key = f"magnet-conversation:{other}"
    first = committed(world, op=key)["body"]
    anchors.record_outcome(world.cv, world.who, key, commands._magnet_key_request(other),
                           {"conversation": first["conversation"]})
    assert ask_commit(world, artifact_of(world, op=key))["body"]["post"] == first["post"]


def test_the_key_of_any_other_request_is_still_a_collision_even_under_that_string(world):
    anchors.keyed(world.cv, world.who, MAGNET_KEY, {"route": "another"}, lambda: {"done": True})
    raw = artifact_of(world, op=MAGNET_KEY)
    define_from(world, raw)
    answer = ask_commit(world, raw)
    assert (answer["state"], answer["status"]) == ("refused", 422)
    assert answer["body"]["error"] == REFUSALS["key-collision"]["body"]["error"]


def test_only_this_door_skips_the_route_s_outcome(world):
    """Every other keyed door still reads that row as the collision it always was."""
    anchors.record_outcome(world.cv, world.who, MAGNET_KEY, commands._magnet_key_request(MAGNET), {"done": True})
    with pytest.raises(anchors.Refused):
        anchors.prior_outcome(world.cv, world.who, MAGNET_KEY, {"route": "another"})


def test_a_recreated_magnet_gets_its_old_conversation_back(world):
    first = committed(world)["body"]
    world.definition_path.unlink()
    second = committed(world, op="activate-0002")["body"]
    assert second["conversation"] == first["conversation"] and second["conversation_created"] is False


# -- what stays as it was --------------------------------------------------------------------------

def test_an_activation_in_a_conversation_it_has_moves_that_conversation_and_nothing_else(world):
    # Every record one commit writes, through the store's own hook. A first activation also claims its
    # Conversation, whose acts have their own classification, so this is the one after it.
    cid = committed(world)["body"]["conversation"]
    touched = []
    context_cache.revisions_for(world.corpus).add_listener(touched.append)
    assert committed(world, op="activate-0002")["body"]["conversation"] == cid
    assert touched and set().union(*touched) == {f"conversation:{cid}"}


def test_a_grant_cannot_reach_the_body_on_the_public_path(world):
    raw = asked_body(world)
    got = send(world.alone, DOOR["target"], [["X-Mentis-Worker", "any"], ["Content-Type", "application/json"],
                                             ["Content-Length", str(len(raw))]], raw)
    assert got["status"] == 403 and json.loads(got["body"])["asked_for"] == DOOR["target"]


def test_a_keep_alive_commit_answer_leaves_the_connection_usable(world):
    raw = artifact_of(world)
    define_from(world, raw)
    head = (f"POST {COMMIT} HTTP/1.1\r\nHost: 127.0.0.1:{world.front}\r\nX-Mentis-Boot-Secret: {SECRET}\r\n"
            f"Content-Type: application/json\r\n{X.DIGEST_HEADER}: {hashlib.sha256(raw).hexdigest()}\r\n"
            f"Content-Length: {len(raw)}\r\n\r\n").encode()
    with socket.create_connection(("127.0.0.1", world.front), timeout=30) as sock:
        sock.sendall(head + raw)
        got = b""
        while b"\r\n\r\n" not in got or len(got.partition(b"\r\n\r\n")[2]) < int(
                [ln for ln in got.split(b"\r\n") if ln.lower().startswith(b"content-length")][0].split(b":")[1]):
            got += sock.recv(1 << 16)
    assert b"HTTP/1.1 200" in got and b"Connection: close" not in got


def test_no_activation_runs_from_anywhere_else():
    """Nothing here starts one: the module is reached from the two doors and the private route only."""
    source = (pathlib.Path(X.__file__)).read_text(encoding="utf-8")
    for word in ("Thread(", "dispatch_soon", "schedule(", "subprocess", "time.sleep"):
        assert word not in source
