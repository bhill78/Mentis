"""The shared contract of a Magnet's manual activation (`docs/magnets/M1-contract.md`, "Manual
activation"), held against its fixtures, `tests/fixtures/magnet-conformance/activation/`.

Nothing here runs an activation: the route and its private protocol are built by the packages that
consume these fixtures. What this holds:

- a door row marked `locked_against_python` is what Python's real door answers, over a real socket.
  The activate path has no command yet, so it is asked of its sibling on the same door, `.../conversation`;
- the small models below (`public_verdict`, `definition_verdict`, `classify`, `verify`, `page_verdict`)
  are the contract's rules written once more, to show the rows agree with the rules and with each other.
  They are not an implementation, and neither side may import them.
"""
from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import pathlib
import socket
import threading
from http.server import ThreadingHTTPServer

import pytest

import mentis.magnet as M
from mentis.conversation import anchors
from mentis.fluid import _checks as W
from mentis.magnet import schema as S
from mentis.web import _Handler, _State, fixture
from mentis.worker import CAPABILITY_HEADER

REPO = pathlib.Path(__file__).resolve().parent.parent
HERE = REPO / "tests" / "fixtures" / "magnet-conformance" / "activation"


def load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


BOUNDS = load("bounds.json")
REFUSALS = load("refusals.json")
DOOR = load("door.json")
BODIES = load("public_bodies.json")
DEFINITIONS = load("definitions.json")
ANSWERS = load("answers.json")
ARTIFACTS = load("artifacts.json")
RESULTS = load("results.json")
USEFUL = load("useful_sources.json")
REQUESTS = load("private_requests.json")
MAGNET = DEFINITIONS["magnet"]
AUTHOR = ANSWERS["holding"]["author"]
OP = ANSWERS["holding"]["op"]
NOBODY = REFUSALS["author-unknown"]["body"]["given"]
A_POST = REFUSALS["author-not-participant"]["body"]["author"]


def ids(rows):
    return [r["id"] for r in rows]


def filled(fill) -> bytes:
    text = fill["text"].encode("utf-8")
    return text + fill["byte"].encode("ascii") * (fill["total"] - len(text))


def nested(spec) -> bytes:
    return (spec["before"] + spec["open"] * spec["depth"] + spec["inside"] + spec["close"] * spec["depth"]
            + spec["after"]).encode("utf-8")


def holds_surrogate(value) -> bool:
    """With a stack of its own: `json.loads` keeps a depth that recursion here would not reach."""
    left = [value]
    while left:
        one = left.pop()
        if isinstance(one, str):
            if any(0xD800 <= ord(c) <= 0xDFFF for c in one):
                return True
        elif isinstance(one, list):
            left.extend(one)
        elif isinstance(one, dict):
            left.extend(one.keys())
            left.extend(one.values())
    return False


def nested_too_deep(raw: bytes) -> bool:
    """Asked of the text `json.loads` would read, before it does, so its recursion limit decides nothing."""
    try:
        text = raw.decode(json.detect_encoding(raw), "surrogatepass")
    except ValueError:
        return False
    depth, in_text, escaped = 0, False, False
    for c in text:
        if in_text:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_text = False
        elif c == '"':
            in_text = True
        elif c in "[{":
            depth += 1
            if depth > BOUNDS["public_body_nesting_most"]:
                return True
        elif c in "]}":
            depth = max(depth - 1, 0)
    return False


# -- the bounds ---------------------------------------------------------------------------------


def test_the_bounds_are_the_ones_the_code_already_holds_and_the_plan_names():
    assert BOUNDS["definition_most"] == W.MAX_BYTES == 256 * 1024
    assert BOUNDS["public_body_most"] == 64 * 1024
    assert BOUNDS["public_body_nesting_most"] == 64
    assert BOUNDS["private_answer_most"] == 1024 * 1024
    assert BOUNDS["artifact_most"] == 25 * 1024 * 1024
    assert BOUNDS["held_across_pair_most"] == 2 * BOUNDS["held_per_process_most"]
    assert (BOUNDS["preflight_seconds"], BOUNDS["commit_seconds"]) == (2, 5)
    # A definition's worst case across `raw` and `value`, and what that leaves for the envelope.
    assert 3 * BOUNDS["definition_most"] + 262144 == BOUNDS["private_answer_most"]


# -- the refusals' bytes ------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(REFUSALS))
def test_a_refusal_s_bytes_are_what_python_s_send_makes_of_its_body(name):
    row = REFUSALS[name]
    assert row["bytes"] == json.dumps(row["body"], default=str)
    assert row["bytes"].isascii()
    assert row["said_by"] in ("python", "rust", "both")
    assert row["status"] in (400, 404, 409, 413, 422, 502, 503)
    assert isinstance(row["body"]["error"], str) and row["body"]["error"]


@pytest.mark.parametrize("name", [n for n, r in REFUSALS.items() if "reason" in r["body"]])
def test_a_reasoned_refusal_says_one_thing_twice_and_names_the_magnet(name):
    body = REFUSALS[name]["body"]
    assert body["reason"]["message"] == body["error"]
    assert set(body["reason"]) == {"code", "message", "retryable"}
    assert body["magnet"] == MAGNET
    assert body["reason"]["retryable"] is (REFUSALS[name]["status"] == 503)


def test_the_two_413s_are_different_bytes():
    public = REFUSALS["public-body-too-large"]
    artifact = REFUSALS["artifact-too-large"]
    assert (public["status"], artifact["status"]) == (413, 413)
    assert public["bytes"] != artifact["bytes"]
    assert "reason" not in public["body"] and public["body"]["limit"] == BOUNDS["public_body_most"]
    assert artifact["body"]["reason"]["code"] == "artifact-too-large"


def test_no_useful_source_does_not_claim_every_source_was_unreadable():
    body = REFUSALS["no-readable-source"]["body"]
    assert body["reason"]["code"] == "no-readable-source"
    assert "no source produced a useful result" in body["error"]
    assert "gave no results" in body["error"]
    assert not body["error"].startswith("no source could be read")


def test_a_refusal_that_may_have_written_never_says_refused():
    unknown = REFUSALS["outcome-unknown"]["body"]
    assert "refused" not in unknown
    assert unknown["op"] == OP and unknown["kind"] == "OutcomeUnknown"
    assert "same operation key" in unknown["error"] and "second activation" in unknown["error"]


# -- the door, against Python's own ---------------------------------------------------------------


@pytest.fixture(scope="module")
def door(tmp_path_factory):
    """Python alone on a disposable fixture Brain, holding the Magnet the sibling route asks about."""
    root = tmp_path_factory.mktemp("activation-door") / "brain"
    fixture.build(str(root))
    path = root / "presentation" / "magnets" / f"{MAGNET}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFINITIONS["executable"][0]["definition"]), encoding="utf-8")
    state = _State(str(root))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), type("H", (_Handler,), {"state": state}))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    a_post = state.corpus.entries_of_kind("contribution")[0]["id"]
    yield {"port": httpd.server_address[1], "a_post": a_post, "state": state}
    httpd.shutdown()
    httpd.server_close()


def send(port, target, headers, body: bytes, method="POST") -> dict:
    """One request as written, on its own socket, and the whole answer as it came."""
    named = {name.strip().lower() for name, _ in headers}
    lines = [f"{method} {target} HTTP/1.1"]
    if "host" not in named:
        lines.append(f"Host: 127.0.0.1:{port}")
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


def row_body(row) -> bytes:
    if "body_fill" in row:
        return filled(row["body_fill"])
    return row["body_text"].encode("utf-8")


LOCKED = [r for r in DOOR["rows"] if r["locked_against_python"]]


@pytest.mark.parametrize("row", LOCKED, ids=ids(LOCKED))
def test_a_door_row_is_what_python_s_real_door_answers(door, row):
    got = send(door["port"], DOOR["sibling_target"], row["headers"], row_body(row))
    expect = row["expect"]
    assert got["status"] == expect["status"]
    assert got["reason"] == expect["reason_phrase"]
    assert got["content_type"] == expect["content_type"]
    assert got["closes"] is expect["closes"]
    # The grant refusal alone names the path it was asked for.
    said = got["body"].decode("utf-8").replace(DOOR["sibling_target"], DOOR["target"])
    assert said == expect["body"]


def test_every_refusal_the_plan_names_has_a_door_row():
    named = set(ids(DOOR["rows"]))
    for needed in ("host-refused", "framing-chunked", "content-length-words", "content-length-minus",
                   "content-length-plus", "client-missing", "grant-without-client", "content-type-wrong",
                   "empty-body-exempt-wrong-type", "body-limit-65536-accepted", "body-limit-65537-refused",
                   "very-long-length-2-63", "very-long-length-2-64", "very-long-length-4301-digits",
                   "very-long-length-4301-digits-host-first", "long-zeros-empty", "long-zeros-small-body"):
        assert needed in named, needed


def test_the_grant_header_is_the_one_python_reads():
    assert DOOR["worker_header"] == CAPABILITY_HEADER


def test_a_length_python_cannot_read_is_refused_before_the_host_and_in_html():
    """`do_POST`'s JSON answers for a bad Content-Length are never reached: `parse_request` answers first."""
    rows = {r["id"]: r for r in DOOR["rows"]}
    for id_ in ("content-length-words", "content-length-minus", "content-length-plus",
                "content-length-plus-under-a-foreign-host"):
        assert rows[id_]["expect"]["status"] == 400
        assert rows[id_]["expect"]["content_type"] == "text/html;charset=utf-8"
        assert rows[id_]["head_refusal"] == "ContentLengthNotDigits"
        assert "Content-Length must be digits only" in rows[id_]["expect"]["body"]


def test_the_public_body_limit_is_exact_and_comes_after_the_door():
    rows = {r["id"]: r for r in DOOR["rows"]}
    assert len(row_body(rows["body-limit-65536-accepted"])) == 65536
    assert rows["body-limit-65536-accepted"]["reaches"] == "preflight"
    assert len(row_body(rows["body-limit-65537-refused"])) == 65537
    assert rows["body-limit-65537-refused"]["expect"]["body"] == REFUSALS["public-body-too-large"]["bytes"]
    assert rows["body-limit-65537-refused"]["expect"]["status"] == 413
    for id_, status in (("over-limit-door-first-client", 403), ("over-limit-door-first-grant", 403),
                        ("over-limit-door-first-type", 415)):
        assert len(row_body(rows[id_])) == 65537 and rows[id_]["expect"]["status"] == status


VERY_LONG = [r for r in DOOR["rows"] if r.get("very_long_length")]
LONG_ZEROS = [r for r in DOOR["rows"] if r.get("long_leading_zeros")]
PYTHON_TODAY = [r for r in DOOR["rows"] if "python_today" in r]
PUBLIC_BODY_MOST = 65536


def length_of(row) -> str:
    return next(value for name, value in row["headers"] if name == "Content-Length")


def over_the_limit(length: str) -> bool:
    """By value, from the digits themselves: `int()` raises past Python's integer-string digit limit,
    and how many digits were sent says nothing until the leading zeros are gone."""
    digits = length.lstrip("0")
    return len(digits) > len(str(PUBLIC_BODY_MOST)) or int(digits or 0) > PUBLIC_BODY_MOST


def test_a_very_long_length_is_only_over_the_limit_and_the_door_still_comes_first():
    answered = {r["id"]: r["expect"]["status"] for r in VERY_LONG}
    assert answered == {"very-long-length-2-63": 413, "very-long-length-2-64": 413,
                        "very-long-length-40-digits": 413, "very-long-length-leading-zeros": 413,
                        "very-long-length-host-first": 421, "very-long-length-framing-first": 501,
                        "very-long-length-client-first": 403, "very-long-length-grant-first": 403,
                        "very-long-length-type-first": 415,
                        "very-long-length-4300-digits": 413, "very-long-length-4301-digits": 413,
                        "very-long-length-4301-digits-host-first": 421,
                        "very-long-length-4301-digits-framing-first": 501,
                        "very-long-length-4301-digits-client-first": 403,
                        "very-long-length-4301-digits-grant-first": 403,
                        "very-long-length-4301-digits-type-first": 415,
                        "very-long-length-zeros-then-65537": 413}
    for row in VERY_LONG:
        assert length_of(row).isascii() and length_of(row).isdigit() and over_the_limit(length_of(row))
        assert "head_refusal" not in row and row["body_text"] == ""
        if row["expect"]["status"] == 413:
            assert row["expect"]["body"] == REFUSALS["public-body-too-large"]["bytes"]
    assert {length_of(r) for r in VERY_LONG} >= {str(2 ** 63), str(2 ** 64), str(10 ** 40), "9" * 4300, "9" * 4301}
    assert REFUSALS["public-body-too-large"]["said_by"] == "both"


def test_past_the_digit_limit_every_stage_of_the_door_still_answers_first():
    """Each stage's row at 2^63 has a row at 4,301 digits, and they answer the same."""
    rows = {r["id"]: r for r in VERY_LONG}
    for stage in ("host", "framing", "client", "grant", "type"):
        at_2_63, past = rows[f"very-long-length-{stage}-first"], rows[f"very-long-length-4301-digits-{stage}-first"]
        assert length_of(past) == "9" * 4301 and past["stage"] == at_2_63["stage"]
        assert past["expect"] == at_2_63["expect"]


# Each one's twin says the same thing under a short spelling of the same number.
LONG_ZEROS_TWINS = {"long-zeros-empty": "empty-body-zero-length",
                    "long-zeros-empty-exempt-wrong-type": "empty-body-exempt-wrong-type",
                    "long-zeros-small-body": "length-digits-accepted",
                    "long-zeros-65536-accepted": "body-limit-65536-accepted",
                    "long-zeros-host-first": "host-refused",
                    "long-zeros-framing-first": "framing-chunked",
                    "long-zeros-client-first": "client-missing",
                    "long-zeros-grant-first": "grant-without-client",
                    "long-zeros-type-first": "content-type-wrong"}


@pytest.mark.parametrize("row", LONG_ZEROS, ids=ids(LONG_ZEROS))
def test_long_leading_zeros_are_read_by_the_number_they_spell(row):
    """Past Python's digit limit too: 5,000 zeros are an empty body, not an oversized one."""
    twin = next(r for r in DOOR["rows"] if r["id"] == LONG_ZEROS_TWINS[row["id"]])
    length = length_of(row)
    assert len(length) >= 5000 and set(length[:5000]) == {"0"} and "head_refusal" not in row
    assert int(length.lstrip("0") or 0) == row["length_value"]
    assert len(row_body(row)) == row["length_value"] and not over_the_limit(length)
    assert (row["stage"], row.get("expect"), row.get("reaches")) == (twin["stage"], twin.get("expect"), twin.get("reaches"))


def test_the_limit_is_exact_behind_long_leading_zeros():
    rows = {r["id"]: r for r in DOOR["rows"]}
    assert len(row_body(rows["long-zeros-65536-accepted"])) == 65536
    assert rows["long-zeros-65536-accepted"]["reaches"] == "preflight"
    refused = rows["very-long-length-zeros-then-65537"]
    assert refused["length_value"] == 65537 and refused["expect"]["status"] == 413
    assert refused["expect"]["body"] == REFUSALS["public-body-too-large"]["bytes"]


@pytest.mark.parametrize("row", PYTHON_TODAY, ids=ids(PYTHON_TODAY))
def test_python_s_500_on_a_long_length_is_the_defect_package_c_fixes(door, row):
    """What Python's shared door does today, measured so nobody reads it as the contract: the row's `expect`
    or `reaches` is. Package C answers those on the activate path; these rows then lock against it."""
    assert not row["locked_against_python"]
    assert row["python_today"]["is_a_defect_fixed_by"] == "Package C"
    assert row["python_today"]["status"] != row.get("expect", {}).get("status")
    got = send(door["port"], DOOR["sibling_target"], row["headers"], row_body(row))
    assert got["status"] == row["python_today"]["status"]
    assert json.loads(got["body"])["kind"] == row["python_today"]["kind"]


ACCEPTED_TODAY = [r for r in DOOR["rows"] if r.get("reaches") and "python_today" not in r]


@pytest.mark.parametrize("row", ACCEPTED_TODAY, ids=ids(ACCEPTED_TODAY))
def test_an_accepted_row_is_past_python_s_door(door, row):
    """Not refused by the door: the sibling goes on to read the author, whom this Brain doesn't hold."""
    got = send(door["port"], DOOR["sibling_target"], row["headers"], row_body(row))
    assert got["status"] == 422 and json.loads(got["body"])["field"] == "author"


def test_python_alone_has_no_private_activation_paths(door):
    want = DOOR["private"]["python_alone"]
    for target in DOOR["private"]["public_port"]["targets"]:
        got = send(door["port"], target,
                   [["X-Mentis-Client", "1"], ["Content-Type", "application/json"], ["Content-Length", "2"]], b"{}")
        assert got["status"] == want["status"] and got["body"].decode() == want["body"]


def test_without_the_secret_the_private_port_says_what_it_says_today(door):
    state = door["state"]
    httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                type("H", (_Handler,), {"state": state, "boot_secret": "s3cret"}))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        got = send(httpd.server_address[1], "/private/live", [], b"", method="GET")
    finally:
        httpd.shutdown()
        httpd.server_close()
    want = DOOR["private"]["private_port_without_secret"]
    assert got["status"] == want["status"] and got["body"].decode() == want["body"]


# -- the public body ------------------------------------------------------------------------------

LOCKED_BODIES = [r for r in BODIES["refused"] if r["locked_against_python"]]


def public_body(row) -> bytes:
    if "public_body_nest" in row:
        return nested(row["public_body_nest"])
    if "public_body_fill" in row:
        return filled(row["public_body_fill"])
    return base64.b64decode(row["public_body_base64"])


@pytest.mark.parametrize("row", LOCKED_BODIES, ids=ids(LOCKED_BODIES))
def test_a_body_refusal_shared_with_python_is_in_its_words(door, row):
    raw = public_body(row).replace(A_POST.encode(), door["a_post"].encode())
    got = send(door["port"], DOOR["sibling_target"],
               [["X-Mentis-Client", "1"], ["Content-Type", "application/json"],
                ["Content-Length", str(len(raw))]], raw)
    want = REFUSALS[row["refused"]]
    assert got["status"] == want["status"]
    assert got["body"].decode().replace(door["a_post"], A_POST) == want["bytes"]


def public_verdict(raw: bytes) -> dict:
    """The body's checks after the Magnet id, in the contract's order. `refused` names a `refusals.json` row."""
    if nested_too_deep(raw):
        return {"refused": "body-too-deep", "author": None, "op": None}
    try:
        body = json.loads(raw or b"{}")
    except ValueError as exc:
        words = f"the body is not JSON: {exc}"
        refused = next(n for n, r in REFUSALS.items() if r["body"].get("error") == words)
        return {"refused": refused, "author": None, "op": None}
    if holds_surrogate(body):
        return {"refused": "body-surrogate", "author": None, "op": None}
    if not isinstance(body, dict):
        return {"refused": "body-not-object", "author": None, "op": None}
    if set(body) - {"author", "op"}:
        return {"refused": "body-fields", "author": None, "op": None}
    author = body.get("author")
    if not isinstance(author, str) or not author.strip():
        return {"refused": "author-missing", "author": None, "op": None}
    author = author.strip()
    if author == NOBODY:
        return {"refused": "author-unknown", "author": None, "op": None}
    if author == A_POST:
        return {"refused": "author-not-participant", "author": None, "op": None}
    op = body.get("op")
    if not isinstance(op, str) or not op.strip() or len(op) > BOUNDS["op_most"]:
        return {"refused": "op-missing", "author": author, "op": None}
    return {"refused": None, "author": author, "op": op}


@pytest.mark.parametrize("row", BODIES["refused"], ids=ids(BODIES["refused"]))
def test_a_refused_body_names_only_what_was_validated(row):
    raw = public_body(row)
    assert len(raw) <= BOUNDS["public_body_most"]
    got = public_verdict(raw)
    assert got == {"refused": row["refused"], "author": row["author"], "op": row["op"]}
    assert not holds_surrogate(REFUSALS[row["refused"]]["body"])


@pytest.mark.parametrize("row", BODIES["accepted"], ids=ids(BODIES["accepted"]))
def test_an_accepted_body_is_validated_and_keeps_its_bytes(row):
    raw = public_body(row)
    got = public_verdict(raw)
    assert got == {"refused": None, "author": row["author"], "op": row["op"]}
    assert len(raw) <= BOUNDS["public_body_most"]
    # What would be sent to preflight survives the transfer whole.
    assert base64.b64decode(base64.b64encode(raw), validate=True) == raw


@pytest.mark.parametrize("row", [r for r in BODIES["refused"] if r["refused"] == "body-surrogate"],
                         ids=ids([r for r in BODIES["refused"] if r["refused"] == "body-surrogate"]))
def test_why_a_surrogate_is_refused_first(row):
    """`json.loads` keeps a lone surrogate, and a private answer can't encode one, escaped or raw."""
    body = json.loads(public_body(row))
    with pytest.raises(UnicodeEncodeError):
        json.dumps(body, ensure_ascii=False).encode("utf-8")
    assert "\\ud800" not in REFUSALS["body-surrogate"]["bytes"]


def test_a_real_pair_of_surrogate_escapes_is_one_character_and_passes():
    row = next(r for r in BODIES["accepted"] if r["id"] == "op-escaped-pair")
    raw = base64.b64decode(row["public_body_base64"])
    assert b"\\ud83d\\ude00" in raw
    assert not holds_surrogate(json.loads(raw))


def test_the_walk_for_a_surrogate_keeps_its_own_stack():
    """Past Python's recursion limit: a recursive walk fails on what `json.loads` can give back."""
    deep, clean = "\ud800", "fine"
    for _ in range(100_000):
        deep, clean = [{"a": deep}], [{"a": clean}]
    assert holds_surrogate(deep) and not holds_surrogate(clean)
    assert holds_surrogate({"\ud800": 1})


def test_the_nesting_bound_is_exact_and_counts_only_what_the_parser_would_descend():
    most = BOUNDS["public_body_nesting_most"]
    assert not nested_too_deep(b"[" * most + b"]" * most)
    assert nested_too_deep(b"[" * (most + 1) + b"]" * (most + 1))
    assert not nested_too_deep(json.dumps({"op": "[" * (most + 1)}).encode())
    assert nested_too_deep(b'{"op": "\\\\", "x": ' + b"[" * most + b"]" * most + b"}")
    assert not nested_too_deep(b'{"op": "\\"' + b"[" * (most + 1) + b'"}')
    # Sibling depths cancel, and what json.loads can't decode is its to say.
    assert not nested_too_deep(b"[" + b"[]," * (most + 1) + b"[]]")
    assert not nested_too_deep(b"\xff" + b"[" * (most + 1))


def test_a_body_that_is_not_json_is_refused_in_python_s_words():
    rows = {r["id"]: r for r in BODIES["refused"]}
    for id_ in ("not-json-cut-short", "not-json-not-text"):
        refused = REFUSALS[rows[id_]["refused"]]
        assert refused["status"] == 400 and refused["said_by"] == "python"
        assert refused["body"]["error"].startswith("the body is not JSON: ")
        assert refused["body"]["kind"] == "BadRequest"
        assert rows[id_]["locked_against_python"]


def test_nesting_past_the_bound_has_one_answer_wherever_json_loads_would_give_up():
    rows = {r["id"]: r for r in BODIES["refused"]}
    for id_ in ("nesting-one-past-the-most", "nesting-one-past-under-a-field", "nesting-objects",
                "nesting-where-json-loads-gives-up", "nesting-never-closed-at-the-limit",
                "nesting-before-not-json", "nesting-before-a-surrogate"):
        assert rows[id_]["refused"] == "body-too-deep", id_
    assert REFUSALS["body-too-deep"]["status"] == 400 and REFUSALS["body-too-deep"]["said_by"] == "python"
    assert len(public_body(rows["nesting-never-closed-at-the-limit"])) == BOUNDS["public_body_most"]
    # Just inside it, the checks after it decide, and they can't be asked to read anything deeper.
    assert rows["nesting-at-the-most-reads"]["refused"] == "body-not-object"
    assert rows["nesting-at-the-most-under-a-field"]["refused"] == "body-fields"
    assert rows["surrogate-just-within-the-most"]["refused"] == "body-surrogate"


def test_magnet_ids_are_the_ones_the_schema_takes():
    for good in BODIES["magnet_ids"]["good"]:
        assert S.MAGNET_ID.fullmatch(good), good
    for bad in BODIES["magnet_ids"]["bad"]:
        assert not S.MAGNET_ID.fullmatch(bad), bad
    assert REFUSALS[BODIES["magnet_ids"]["refused"]]["status"] == 400


def test_python_alone_has_its_refusal_and_both_spellings():
    alone = BODIES["python_alone"]
    assert REFUSALS[alone["answer_valid_body"]]["status"] == 503
    assert REFUSALS[alone["answer_valid_body"]]["body"]["kind"] == "ProcessorUnavailable"
    assert alone["paths"] == [DOOR["target"], DOOR["target"] + "/"]


# -- the definition -------------------------------------------------------------------------------


def executable_verdict(definition) -> str:
    """`ready`, or the first refusal in the contract's order."""
    version = definition.get("schema_version", 1)
    if version > S.SCHEMA_VERSION:
        return "schema-version-not-supported"
    if (definition.get("activation") or {}).get("mode") != "manual":
        return "activation-not-supported"
    if definition["collection"]["mode"] != "one-time":
        return "collection-not-supported"
    if definition["synthesis"]["mode"] != "manual":
        return "synthesis-not-supported"
    if any(definition["notifications"].values()):
        return "notifications-not-supported"
    operations = (definition.get("processing") or {}).get("operations") or []
    if len(operations) != 1 or operations[0]["op"] != "extract":
        return "pipeline-not-supported"
    if (operations[0].get("options") or {}) not in ({}, {"mode": "m1-page"}):
        return "extract-mode-not-supported"
    if "ai" in definition and definition["ai"] != {"mode": "none"}:
        return "ai-not-supported"
    if "outputs" in definition and definition["outputs"] != ["records"]:
        return "output-not-supported"
    if "destinations" in definition and definition["destinations"] != [{"kind": "magnet-conversation"}]:
        return "destination-not-supported"
    if not any(s["kind"] == "conversation" for s in definition["sources"]):
        return "no-readable-source"
    return "ready"


def write_definition(root, raw: bytes):
    path = root / "presentation" / "magnets" / f"{MAGNET}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


@pytest.mark.parametrize("row", DEFINITIONS["executable"], ids=ids(DEFINITIONS["executable"]))
def test_the_executable_subset(tmp_path, row):
    definition = row["definition"]
    assert executable_verdict(definition) == row["answer"]
    assert row["answer"] == "ready" or row["answer"] in DEFINITIONS["order"]
    if row["answer"] == "schema-version-not-supported":
        with pytest.raises(S.Refused):
            S.magnet_config(definition)
        return
    # Everything else is a good definition this build can't run: it reads, whatever it says.
    write_definition(tmp_path, json.dumps(definition).encode())
    read = M.read(tmp_path, MAGNET)
    if row["answer"] == "ready":
        assert json.dumps(read) == json.dumps(row["value"]), "value is the read's, in its order"


def test_a_definition_refusal_is_one_kept_refusal_per_code():
    for code in DEFINITIONS["order"]:
        assert REFUSALS[code]["body"]["reason"]["code"] == code
        assert any(r["answer"] == code for r in DEFINITIONS["executable"]), code


def definition_verdict(root) -> tuple[str, str | None]:
    """Exact bytes first, then what `mentis.magnet.read` says, then what it doesn't ask."""
    path = root / "presentation" / "magnets" / f"{MAGNET}.json"
    if not path.exists():
        return "no-definition", None
    raw = path.read_bytes()
    if len(raw) > BOUNDS["definition_most"]:
        return "definition-too-large", None
    try:
        config = M.read(root, MAGNET)
    except M.Unreadable as exc:
        return "unreadable", str(exc)
    if holds_surrogate(config):
        return "definition-surrogate", None
    return "ready", None


@pytest.mark.parametrize("row", DEFINITIONS["files"], ids=ids(DEFINITIONS["files"]))
def test_what_a_definition_file_answers(tmp_path, row):
    raw = None
    if "pad" in row:
        raw = filled(row["pad"])
    elif "file_base64" in row:
        raw = base64.b64decode(row["file_base64"])
    if raw is not None:
        write_definition(tmp_path, raw)
    got, words = definition_verdict(tmp_path)
    if row["answer"] == "unreadable":
        assert got == "unreadable" and words.startswith(row["error_starts"])
    elif got == "unreadable":
        want = REFUSALS[row["answer"]]
        assert want["status"] == 409 and want["body"] == {"error": words, "kind": "Unreadable"}
    else:
        assert got == row["answer"]
    if "sha256" in row:
        assert len(raw) == row["size"]
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
    if row["answer"] == "ready":
        assert (tmp_path / "presentation" / "magnets" / f"{MAGNET}.json").read_bytes() == raw, "read rewrites nothing"


def test_why_the_definition_bound_is_asked_of_the_bytes(tmp_path):
    """`mentis.magnet.read` has no size check of its own: the row over the bound reads."""
    row = next(r for r in DEFINITIONS["files"] if r["id"] == "over-the-bound")
    raw = filled(row["pad"])
    assert len(raw) == BOUNDS["definition_most"] + 1
    write_definition(tmp_path, raw)
    assert M.read(tmp_path, MAGNET)["id"] == MAGNET


def ready_answer(raw: bytes, value) -> bytes:
    return json.dumps({"protocol": 1, "state": "ready", "magnet": MAGNET,
                       "request": {"author": AUTHOR, "op": "k" * BOUNDS["op_most"],
                                   "identity": RESULTS["identity"]},
                       "definition": {"sha256": hashlib.sha256(raw).hexdigest(),
                                      "raw": raw.decode("utf-8"), "value": value}},
                      ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize("pad", [" ", "\n", "\t"], ids=["spaces", "newlines", "tabs"])
def test_a_definition_at_the_bound_fits_a_private_answer(tmp_path, pad):
    plain = next(r for r in DEFINITIONS["executable"] if r["id"] == "plain")
    text = json.dumps(plain["definition"], indent=1).encode()
    raw = text + pad.encode() * (BOUNDS["definition_most"] - len(text))
    write_definition(tmp_path, raw)
    assert len(ready_answer(raw, M.read(tmp_path, MAGNET))) <= BOUNDS["private_answer_most"]


def test_the_most_a_definition_can_cost_is_three_times_itself():
    """What the bound's arithmetic rests on: a double quote costs 3 across `raw` and `value`."""
    quotes = '"' * 1000
    assert len(json.dumps(quotes, ensure_ascii=False)) - 2 == 2 * 1000
    written = json.dumps({"a": quotes}, ensure_ascii=False)
    as_raw = json.dumps(written, ensure_ascii=False)
    assert (len(as_raw) + len(written)) <= 3 * len(written) + 2
    # And `ensure_ascii=True` is what would break it: 2 bytes become 6, in both.
    two_byte = "é" * 1000
    assert len(json.dumps(two_byte, ensure_ascii=False).encode()) - 2 == 2 * 1000
    assert len(json.dumps(two_byte).encode()) - 2 == 6 * 1000


# -- a private answer -----------------------------------------------------------------------------


COMMON = ("protocol", "state", "magnet")
ENVELOPE = (*COMMON, "author", "op", "status", "body")


def wire_of(row) -> bytes:
    if "wire_text" in row:
        return row["wire_text"].encode("utf-8")
    source = next(r for r in ANSWERS["rows"] if r["phase"] == row["phase"] and r["id"] == (row.get("wire_pad") or row["wire_cut"])["of"])
    text = source["wire_text"].encode("utf-8")
    if "wire_cut" in row:
        return text[:row["wire_cut"]["keep"]]
    return text[:-1] + b" " * (row["wire_pad"]["total"] - len(text)) + b"}"


def _is_identity(value) -> bool:
    return value is None or isinstance(value, str)


def _is_count(value) -> bool:
    return type(value) is int and value >= 0


def _is_result(body) -> bool:
    """A `committed` or `replay` body: the contract's "The answer", all of it and nothing else."""
    if set(body) != {"magnet", "operation", "state", "conversation", "conversation_created", "post", "artifact",
                     "page", "replayed", "cursor"}:
        return False
    operation, artifact, page = body["operation"], body["artifact"], body["page"]
    if (not isinstance(operation, dict) or set(operation) != {"index", "op", "mode", "name"}
            or not _is_count(operation["index"]) or not isinstance(operation["op"], str)
            or not isinstance(operation["mode"], str) or not (operation["name"] is None or isinstance(operation["name"], str))):
        return False
    if (not isinstance(artifact, dict) or set(artifact) != {"ref", "digest", "size", "media_type"}
            or not all(isinstance(artifact[k], str) for k in ("ref", "digest", "media_type"))
            or not _is_count(artifact["size"])):
        return False
    if (not isinstance(page, dict) or set(page) != {"cursor", "sources", "results", "statuses", "kept"}
            or not isinstance(page["cursor"], str) or not _is_count(page["sources"]) or not _is_count(page["results"])):
        return False
    statuses, kept = page["statuses"], page["kept"]
    if (not isinstance(statuses, dict) or set(statuses) != {"ok", "partial", "busy", "unavailable"}
            or not all(_is_count(n) for n in statuses.values()) or not isinstance(kept, list)
            or not all(isinstance(k, dict) and set(k) == {"facet", "reason"}
                       and isinstance(k["facet"], str) and isinstance(k["reason"], str) for k in kept)):
        return False
    return (body["state"] in ("complete", "partial") and isinstance(body["conversation"], str)
            and type(body["conversation_created"]) is bool and isinstance(body["post"], str)
            and isinstance(body["cursor"], str))


def _shape(answer, phase, asked=MAGNET) -> str | None:
    """The state of a well-formed answer, or None. `asked` is the raw path segment Rust sent."""
    if not isinstance(answer, dict) or answer.get("protocol") != 1 or answer.get("magnet") != asked:
        return None
    state = answer.get("state")
    if state == "ready":
        if phase != "preflight" or set(answer) != {*COMMON, "request", "definition"}:
            return None
        request = answer["request"]
        definition = answer["definition"]
        if (not isinstance(request, dict) or set(request) != {"author", "op", "identity"}
                or not isinstance(request["author"], str) or not isinstance(request["op"], str)
                or request["identity"] != RESULTS["identity"]):
            return None
        if (not isinstance(definition, dict) or set(definition) != {"sha256", "raw", "value"}
                or hashlib.sha256(definition["raw"].encode()).hexdigest() != definition["sha256"]):
            return None
        return state
    if state not in ("refused", "internal-protocol-error", "committed", "replay"):
        return None
    if state == "committed" and phase != "commit":
        return None
    if set(answer) != set(ENVELOPE) or not _is_identity(answer["author"]) or not _is_identity(answer["op"]):
        return None
    body = answer["body"]
    if not isinstance(body, dict) or not isinstance(body.get("error", ""), str):
        return None
    if state == "refused":
        if answer["status"] not in ANSWERS["refused_statuses"][phase] or "error" not in body:
            return None
    elif state == "internal-protocol-error":
        if answer["status"] != 502 or "error" not in body:
            return None
    else:
        want_status, want_replayed = (201, False) if state == "committed" else (200, True)
        if (answer["status"] != want_status or body.get("replayed") is not want_replayed
                or body.get("magnet") != MAGNET or not _is_result(body)
                or answer["author"] is None or answer["op"] is None):
            return None
    return state


def classify(row) -> tuple[str | None, str]:
    """(the refusal or state that decides the public answer, what happens next)."""
    phase = row["phase"]
    interrupted = "outcome-unknown" if phase == "commit" else "preflight-interrupted"
    malformed = "outcome-unknown" if phase == "commit" else "internal-protocol-error"
    if "event" in row:
        return interrupted, "none"
    wire = wire_of(row)
    if len(wire) > BOUNDS["private_answer_most"] or row.get("http_status", 200) != 200:
        return malformed, "none"
    try:
        answer = json.loads(wire)
    except ValueError:
        return malformed, "none"
    state = _shape(answer, phase, row.get("asked", MAGNET))
    if state is None:
        return malformed, "none"
    if state == "ready":
        try:
            S.magnet_config(json.loads(answer["definition"]["raw"]))
        except (ValueError, S.Refused):
            return "internal-protocol-error", "none"  # stands for `MagnetDefinition::parse`
        return None, "retrieve"
    if phase == "commit" and any(answer[k] is not None and answer[k] != ANSWERS["holding"][k] for k in ("author", "op")):
        return "outcome-unknown", "none"
    if state == "refused":
        return next(n for n, r in REFUSALS.items() if r["body"] == answer["body"]), "none"
    if state == "internal-protocol-error":
        return "internal-protocol-error", "none"
    return state, "none"


@pytest.mark.parametrize("row", ANSWERS["rows"], ids=[f'{r["phase"]}-{r["id"]}' for r in ANSWERS["rows"]])
def test_what_each_private_answer_decides(row):
    assert classify(row) == (row["decides"], row["next"])


@pytest.mark.parametrize("name", ["preflight", "commit"])
def test_the_wire_limit_is_exact(name):
    rows = {r["id"]: r for r in ANSWERS["rows"] if r["phase"] == name}
    assert len(wire_of(rows["at-the-wire-limit"])) == BOUNDS["private_answer_most"]
    assert len(wire_of(rows["over-the-wire-limit"])) == BOUNDS["private_answer_most"] + 1


def test_private_answers_are_not_ascii_escaped():
    row = next(r for r in ANSWERS["rows"] if r["id"] == "ready-non-ascii-not-escaped")
    wire = wire_of(row)
    assert json.dumps(json.loads(wire), ensure_ascii=False).encode("utf-8") == wire
    assert "😀".encode() in wire and b"\\ud83d" not in wire.replace(b"\\\\ud83d", b"")


def test_a_refused_answer_that_decides_quotes_a_refusal_python_says_whole():
    seen = 0
    for row in ANSWERS["rows"]:
        if row["decides"] not in REFUSALS or row["decides"] in ("outcome-unknown", "internal-protocol-error"):
            continue
        if "wire_text" not in row:
            continue
        answer = json.loads(row["wire_text"])
        assert answer["state"] == "refused", row["id"]
        assert answer["body"] == REFUSALS[row["decides"]]["body"], row["id"]
        assert answer["status"] == REFUSALS[row["decides"]]["status"], row["id"]
        assert REFUSALS[row["decides"]]["said_by"] in ("python", "both"), row["id"]
        seen += 1
    assert seen >= 20


def test_the_answers_the_corrections_named_are_all_there():
    by_id = {(r["phase"], r["id"]): r for r in ANSWERS["rows"]}
    for key in [("preflight", "ready-with-public-status"),
                ("preflight", "refused-author-malformed-null-identity"),
                ("preflight", "refused-unknown-author-null-author"),
                ("preflight", "interrupted-truncated"), ("preflight", "interrupted-timeout"),
                ("preflight", "interrupted-reset"), ("preflight", "interrupted-disconnect"),
                ("preflight", "replay"), ("preflight", "refused-key-collision"),
                ("preflight", "ready-rust-rejects-what-python-approved"),
                ("preflight", "refused-body-not-json-cut-short"), ("preflight", "refused-body-not-json-not-text"),
                ("preflight", "refused-body-too-deep"),
                ("preflight", "refused-magnet-id-bad-character"), ("preflight", "refused-magnet-id-encoded-slash"),
                ("commit", "early-busy-null-identity"),
                ("commit", "ipe-artifact-unparsed-null-identity"),
                ("preflight", "replay-body-hollow"), ("commit", "committed-body-hollow"),
                ("commit", "replay-body-hollow"), ("commit", "committed-partial-named")]:
        assert key in by_id, key
    assert by_id["commit", "early-busy-null-identity"]["decides"] == "busy"
    assert by_id["preflight", "refused-unknown-author-null-author"]["decides"] == "author-unknown"
    assert by_id["preflight", "collision-state-is-gone"]["decides"] == "internal-protocol-error"
    assert by_id["preflight", "refused-key-collision"]["decides"] == "key-collision"


@pytest.mark.parametrize("id_, segment", [("refused-magnet-id-bad-character", "mag-bad!"),
                                          ("refused-magnet-id-encoded-slash", "mag-a%2fb")])
def test_a_malformed_magnet_id_is_a_400_that_names_the_segment_as_it_was_sent(id_, segment):
    row = next(r for r in ANSWERS["rows"] if r["phase"] == "preflight" and r["id"] == id_)
    answer = json.loads(row["wire_text"])
    assert not S.MAGNET_ID.fullmatch(segment)
    assert (answer["magnet"], answer["author"], answer["op"]) == (segment, None, None)
    assert (answer["state"], answer["status"]) == ("refused", 400)
    assert json.dumps(answer["body"]) == REFUSALS["magnet-id"]["bytes"]
    assert classify(row) == ("magnet-id", "none")
    # Asked about anything else, the same answer is the other half naming the wrong Magnet.
    assert classify({**row, "asked": MAGNET}) == ("internal-protocol-error", "none")


def test_every_commit_answer_decides_or_says_it_is_unknown_and_nothing_else():
    allowed = {"committed", "replay", "outcome-unknown", "internal-protocol-error"}
    for row in ANSWERS["rows"]:
        if row["phase"] == "commit":
            assert row["decides"] in allowed or REFUSALS[row["decides"]]["status"] in ANSWERS["refused_statuses"]["commit"], row["id"]


# -- the private requests -------------------------------------------------------------------------


def test_the_preflight_request_carries_the_body_losslessly():
    asked = json.loads(REQUESTS["preflight"]["wire_text"])
    assert set(asked) == {"protocol", "magnet", "public_body_base64"}
    assert asked["protocol"] == 1 and asked["magnet"] == MAGNET
    assert public_verdict(base64.b64decode(asked["public_body_base64"], validate=True)) == {
        "refused": None, "author": AUTHOR, "op": OP}


def preflight_request_is_good(wire: str, segment=MAGNET) -> bool:
    try:
        asked = json.loads(wire)
    except ValueError:
        return False
    if not isinstance(asked, dict) or set(asked) != {"protocol", "magnet", "public_body_base64"}:
        return False
    if asked["protocol"] != 1 or asked["magnet"] != segment:
        return False
    try:
        base64.b64decode(asked["public_body_base64"], validate=True)
    except (binascii.Error, ValueError):
        return False
    return True


@pytest.mark.parametrize("row", REQUESTS["preflight_refused"], ids=ids(REQUESTS["preflight_refused"]))
def test_a_preflight_request_that_is_not_one_is_a_protocol_error(row):
    assert not preflight_request_is_good(row["wire_text"])
    assert preflight_request_is_good(REQUESTS["preflight"]["wire_text"])
    assert REQUESTS["preflight_refused_answer"] == {"state": "internal-protocol-error", "author": None, "op": None}


@pytest.mark.parametrize("row", REQUESTS["preflight_malformed_magnet"], ids=ids(REQUESTS["preflight_malformed_magnet"]))
def test_a_malformed_magnet_id_reaches_preflight_undecoded(row):
    """A request of the right shape, so Python's first check answers it, and neither side routes it to a 404."""
    assert preflight_request_is_good(row["wire_text"], row["segment"])
    assert row["path"] == f'/private/magnets/{row["segment"]}/activate/preflight'
    assert not S.MAGNET_ID.fullmatch(row["segment"])
    assert REFUSALS[row["answer"]]["status"] == 400
    assert row["segment"] in BODIES["magnet_ids"]["bad"]


def test_the_private_paths_are_private_and_exact():
    assert REQUESTS["preflight"]["path"] == f"/private/magnets/{MAGNET}/activate/preflight"
    assert REQUESTS["commit"]["path"] == f"/private/magnets/{MAGNET}/activate/commit"
    assert DOOR["private"]["public_port"]["targets"] == [REQUESTS["preflight"]["path"], REQUESTS["commit"]["path"]]
    assert DOOR["private"]["public_port"]["body"] == '{"error": "no such semantic surface"}'


# -- the artifact ---------------------------------------------------------------------------------


def artifact_bytes(name) -> bytes:
    return (HERE / ARTIFACTS["artifacts"][name]["file"]).read_bytes()


TOP = ["format", "version", "mode", "magnet", "request", "definition", "operation", "page"]


@pytest.mark.parametrize("name", list(ARTIFACTS["artifacts"]))
def test_an_artifact_is_exact_bytes_with_a_digest_python_can_recompute(tmp_path, name):
    info = ARTIFACTS["artifacts"][name]
    raw = artifact_bytes(name)
    assert len(raw) == info["size"] and hashlib.sha256(raw).hexdigest() == info["sha256"]
    assert b"\r" not in raw and not raw.endswith(b"\n")
    art = json.loads(raw)
    # One serialization: `json.dumps`' default, which is what `Py::dumps` writes.
    assert json.dumps(art).encode("utf-8") == raw
    assert list(art) == TOP
    assert list(art["request"]) == ["author", "op", "identity"]
    assert list(art["definition"]) == ["sha256", "raw", "value"]
    assert list(art["operation"]) == ["index", "op", "mode", "name", "options"]
    definition_bytes = art["definition"]["raw"].encode("utf-8")
    assert hashlib.sha256(definition_bytes).hexdigest() == art["definition"]["sha256"] == info["definition_sha256"]
    # `value` is the checked read of `raw`, not a form of it the digest covers.
    write_definition(tmp_path, definition_bytes)
    assert json.dumps(M.read(tmp_path, MAGNET)) == json.dumps(art["definition"]["value"])
    assert executable_verdict(json.loads(definition_bytes)) == "ready"


def test_non_ascii_survives_the_artifact_and_is_escaped_there():
    raw = artifact_bytes("partial-non-ascii")
    assert raw.isascii()
    art = json.loads(raw)
    assert "😀" in art["definition"]["raw"]
    assert art["operation"]["name"] == "Lire le fil"
    assert art["operation"]["options"] == {"mode": "m1-page"}


def test_the_page_is_the_shape_the_read_answers():
    shared = json.loads((HERE.parent / "page_answer.json").read_text(encoding="utf-8"))
    shape = {r["kind"]: set(r) for r in shared["sources"][0]["results"]}
    assert set(shape) == {"post", "file"}
    for name in ARTIFACTS["artifacts"]:
        page = json.loads(artifact_bytes(name))["page"]
        assert set(page) == set(shared)
        for got in page["sources"]:
            assert set(got) == set(shared["sources"][0])
            for result in got["results"]:
                assert set(result) == shape[result["kind"]]


def test_a_page_may_hold_what_a_real_conversation_links_in_and_its_objects():
    """Two of the kinds the first artifacts didn't have, as `MagnetRead` reports them: `magnet.rs` names a
    result's own home, and the source only when it has none to name."""
    art = json.loads(artifact_bytes("linked-and-objects"))
    source = art["page"]["sources"][0]
    home = source["source"]["conversation"]
    results = source["results"]
    posts = [r for r in results if r["kind"] == "post"]
    assert {(r["via"], r["number"] is None) for r in posts} == {("home", False), ("linked", True)}
    assert [r["conversation"] for r in posts if r["via"] == "home"] == [home]
    assert {r["conversation"] == home for r in posts if r["via"] == "linked"} == {True, False}
    objects = [r for r in results if r["kind"] != "post"]
    assert all("via" not in r and r["value"]["home"] == r["conversation"] for r in objects)
    assert {r["conversation"] == home for r in objects} == {True, False}


@pytest.mark.parametrize("via, state", [("linked", "valid"), ("home", "internal-protocol-error")])
def test_only_a_post_read_from_its_home_has_its_conversation_asked_about(via, state):
    assert "result-other-conversation" not in ids(ARTIFACTS["verification"])
    changed = json.loads(artifact_bytes("linked-and-objects"))
    for result in changed["page"]["sources"][0]["results"]:
        if result.get("via") == via:
            result["conversation"] = "ent-000000000009"
    raw = json.dumps(changed).encode()
    assert verify(raw, hashlib.sha256(raw).hexdigest())["state"] == state


def page_verdict(sources, kept) -> tuple[str, int]:
    useful = sum(1 for s in sources if s["status"] in ("ok", "partial") and s["results"] > 0)
    if useful:
        whole = all(s["status"] == "ok" for s in sources) and not kept
        return ("complete" if whole else "partial"), useful
    if any(s["status"] == "busy" for s in sources):
        return "sources-busy", 0
    return "no-readable-source", 0


@pytest.mark.parametrize("row", USEFUL, ids=ids(USEFUL))
def test_what_a_page_comes_to(row):
    assert page_verdict(row["sources"], row["kept"]) == (row["decides"], row["useful"])


def verify(raw: bytes, header: str) -> dict:
    """Python's checks on a commit, in the contract's order, short of the record's."""
    ip = {"state": "internal-protocol-error"}
    if hashlib.sha256(raw).hexdigest() != header:
        return {**ip, "author": None, "op": None}
    try:
        art = json.loads(raw)
    except (ValueError, RecursionError):
        return {**ip, "author": None, "op": None}
    if holds_surrogate(art):
        return {**ip, "author": None, "op": None}
    if not isinstance(art, dict) or list(art) != TOP:
        return {**ip, "author": None, "op": None}
    if (art["format"], art["version"], art["mode"], art["magnet"]) != ("mentis.magnet-extract", 1, "m1-page", MAGNET):
        return {**ip, "author": None, "op": None}
    if art["request"]["author"] != AUTHOR:
        return {**ip, "author": None, "op": None}
    author = AUTHOR
    if not isinstance(art["request"]["op"], str) or not art["request"]["op"].strip():
        return {**ip, "author": author, "op": None}
    op = art["request"]["op"]
    bad = {**ip, "author": author, "op": op}
    if art["request"]["identity"] != RESULTS["identity"]:
        return bad
    definition = art["definition"]
    if hashlib.sha256(definition["raw"].encode()).hexdigest() != definition["sha256"]:
        return bad
    said = json.loads(definition["raw"])
    if executable_verdict(said) != "ready":
        return bad
    if M.wire(S.magnet_config(said)) != definition["value"]:
        return bad
    named = said["processing"]["operations"][0]
    if (art["operation"]["index"], art["operation"]["op"], art["operation"]["mode"]) != (0, "extract", "m1-page"):
        return bad
    if art["operation"]["name"] != named.get("name") or art["operation"]["options"] != (named.get("options") or {}):
        return bad
    page = art["page"]
    if page["magnet"] != MAGNET or page["mode"] != "page" or not isinstance(page["cursor"], str) or not isinstance(page["kept"], list):
        return bad
    configured = definition["value"]["sources"]
    if [s["source"] for s in page["sources"]] != configured:
        return bad
    counted = []
    for one in page["sources"]:
        if one["key"] != S.source_key(one["source"]) or one["summary"] is not None:
            return bad
        if one["status"] not in ("ok", "partial", "busy", "unavailable") or not isinstance(one["results"], list):
            return bad
        conversation = one["source"].get("conversation")
        if any(r.get("via") == "home" and r["conversation"] != conversation for r in one["results"]):
            return bad
        counted.append({"status": one["status"], "results": len(one["results"])})
    came_to, _ = page_verdict(counted, page["kept"])
    if came_to in ("sources-busy", "no-readable-source"):
        return {"state": "refused", "refused": came_to, "author": author, "op": op}
    return {"state": "valid", "came_to": came_to, "author": author, "op": op}


def spoiled(row) -> tuple[bytes, str]:
    good = artifact_bytes("complete")
    if "bytes_text" in row or "bytes_nest" in row:
        raw = row["bytes_text"].encode() if "bytes_text" in row else nested(row["bytes_nest"])
        return raw, hashlib.sha256(raw).hexdigest()
    if "header_sha256" in row:
        return good, row["header_sha256"]
    art = copy.deepcopy(json.loads(good))
    at = art
    for step in row["set"][:-1]:
        at = at[step]
    # A lone surrogate is written as JSON's text: not every reader of this file would take one.
    at[row["set"][-1]] = json.loads(row["to_json"]) if "to_json" in row else row["to"]
    raw = json.dumps(art).encode()
    return raw, hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("name, came_to", [("complete", "complete"), ("partial-non-ascii", "partial"),
                                           ("linked-and-objects", "complete")])
def test_a_good_artifact_passes_every_check(name, came_to):
    raw = artifact_bytes(name)
    got = verify(raw, ARTIFACTS["artifacts"][name]["sha256"])
    assert got == {"state": "valid", "came_to": came_to, "author": AUTHOR, "op": OP}


@pytest.mark.parametrize("row", ARTIFACTS["verification"], ids=ids(ARTIFACTS["verification"]))
def test_what_python_makes_of_a_spoiled_artifact(row):
    raw, header = spoiled(row)
    got = verify(raw, header)
    want = {"state": row["state"], "author": row["author"], "op": row["op"]}
    if "refused" in row:
        want["refused"] = row["refused"]
    assert got == want


SURROGATES = {"surrogate-in-author": ["request", "author"], "surrogate-in-op": ["request", "op"],
              "surrogate-in-definition-raw": ["definition", "raw"],
              "surrogate-in-operation-name": ["operation", "name"], "surrogate-in-page-kept": ["page", "kept"]}


@pytest.mark.parametrize("id_, path", list(SURROGATES.items()))
def test_a_surrogate_anywhere_in_an_artifact_is_refused_before_anything_can_be_named(id_, path):
    """Past this, Python would write the record and then fail to encode the answer to it."""
    row = next(r for r in ARTIFACTS["verification"] if r["id"] == id_)
    assert row["set"] == path
    assert (row["state"], row["author"], row["op"]) == ("internal-protocol-error", None, None)
    art = json.loads(spoiled(row)[0])
    assert holds_surrogate(art)
    with pytest.raises(UnicodeEncodeError):
        json.dumps(art, ensure_ascii=False).encode("utf-8")


# -- the result -----------------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["complete", "partial"])
def test_a_result_is_what_was_stored_with_the_two_fields_that_are_not(case):
    row = RESULTS[case]
    stored = row["stored"]
    assert "cursor" not in stored and "replayed" not in stored
    assert row["first"]["status"] == 201 and row["replay"]["status"] == 200
    # In this order: what `keyed` gives back, `replayed` added, then the record's cursor now.
    assert list(row["first"]["body"]) == [*stored, "replayed", "cursor"]
    assert row["first"]["body"] == {**stored, "replayed": False, "cursor": row["first"]["body"]["cursor"]}
    assert row["replay"]["body"] == {**stored, "replayed": True, "cursor": row["replay"]["body"]["cursor"]}
    assert row["first"]["bytes"] == json.dumps(row["first"]["body"])
    assert row["replay"]["bytes"] == json.dumps(row["replay"]["body"])
    assert row["replay"]["body"]["page"]["cursor"] == stored["page"]["cursor"] != row["replay"]["body"]["cursor"]


@pytest.mark.parametrize("case", ["complete", "partial"])
def test_a_result_agrees_with_its_artifact(case):
    row = RESULTS[case]
    stored = row["stored"]
    info = ARTIFACTS["artifacts"][row["artifact"]]
    assert stored["artifact"]["digest"] == info["sha256"]
    assert stored["artifact"]["size"] == info["size"]
    assert stored["artifact"]["media_type"] == "application/json"
    art = json.loads(artifact_bytes(row["artifact"]))
    page = art["page"]
    assert stored["page"]["cursor"] == page["cursor"]
    assert stored["page"]["sources"] == len(page["sources"])
    assert stored["page"]["results"] == sum(len(s["results"]) for s in page["sources"])
    assert stored["page"]["kept"] == page["kept"]
    counts = {"ok": 0, "partial": 0, "busy": 0, "unavailable": 0}
    for one in page["sources"]:
        counts[one["status"]] += 1
    assert stored["page"]["statuses"] == counts
    assert stored["operation"] == {k: art["operation"][k] for k in ("index", "op", "mode", "name")}
    assert stored["state"] == case


def test_the_keyed_identity_is_the_route_and_the_magnet_and_digests_as_keyed_does():
    assert RESULTS["identity"] == {"route": "fluid-magnet-activate", "magnet": MAGNET}
    assert anchors.digest(RESULTS["identity"]) == RESULTS["identity_digest"]


def test_the_collision_wording_is_the_keyed_door_s_own(door):
    state = door["state"]
    who = state.corpus.entries_of_kind("participant")[0]["id"]
    first = anchors.keyed(state.cv, who, OP, RESULTS["identity"], lambda: {"done": True})
    assert first == {"done": True}
    with pytest.raises(anchors.Refused) as refused:
        anchors.keyed(state.cv, who, OP, {**RESULTS["identity"], "magnet": "mag-another"}, lambda: {})
    said = refused.value.refusal
    assert said["error"] == REFUSALS["key-collision"]["body"]["error"]
    assert list(said) == ["error", "op", "first"]
    assert list(REFUSALS["key-collision"]["body"]) == [*said, "refused"]


# -- what the documents say ------------------------------------------------------------------------


def doc(*path) -> str:
    return (REPO.joinpath("docs", *path)).read_text(encoding="utf-8")


def test_the_launcher_no_longer_says_the_secret_grants_nothing_over_the_record():
    text = doc("rust", "contracts", "launcher.md")
    assert "grants no authority over the record" not in text
    assert "Its grant still decides its operations" not in text
    assert ("A holder of its secret can cause validated append-only Magnet-extract writes naming any "
            "existing Participant, and Python cannot verify that valid submitted page content came "
            "from an actual M1 retrieval.") in text
    assert ("The agent's grant still decides its ordinary public operations. Possession of the boot "
            "secret separately grants the narrowly bounded Magnet-extract write authority described "
            "above; it grants no other record operation.") in text
    # The reason the last row stays out of scope still stands for a process with this user's rights.
    assert "Holding the secret gets a process of this user nothing it doesn't already have." in text
    assert "It can present the secret, claim any peer, stop the front and forge Magnet-extract writes" in text


def test_the_documents_name_the_route_and_the_paths():
    contract = doc("magnets", "M1-contract.md")
    for needed in ("## Manual activation", "/fluid/api/magnets/<id>/activate",
                   "/private/magnets/<id>/activate/preflight", "/private/magnets/<id>/activate/commit",
                   "ensure_ascii=False", "OutcomeUnknown", "magnet-extracted",
                   "tests/fixtures/magnet-conformance/activation/"):
        assert needed in contract, needed
    assert "/fluid/api/magnets/<id>/activate" in doc("rust", "routes.md")
    assert "/fluid/api/magnets/{}/activate" in doc("rust", "contracts", "route-table.md")
    assert "/private/magnets/<id>/activate/preflight" in doc("rust", "contracts", "launcher.md")


def test_the_contract_says_what_the_corrections_pinned():
    contract = doc("magnets", "M1-contract.md")
    assert "00053" in contract and "00057" not in contract
    assert "very_long_length" in contract and "Package C" in contract
    assert "never by recursion" in contract
    assert 'A post read `via: "home"`' in contract
    assert "raw path segment" in contract


def test_m1_page_is_the_first_mode_not_what_extract_means():
    assert "the first mode of `extract`, not what `extract` means" in doc("magnets", "M1-contract.md")
