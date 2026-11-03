"""A Magnet's manual activation, Python's half (`docs/magnets/M1-contract.md`, "Manual activation").

One explicit `POST` materializes one bounded M1 page in the Magnet's own Conversation. The Rust front
owns the public door, the M1 read and the artifact's bytes. What is here is what Python owns: every word
about the body, the author, the key and the definition, verifying what comes back, and every record write.

  public     `POST /fluid/api/magnets/<id>/activate`, on Python's own door: every check on the body, and
             a valid one is `ProcessorUnavailable`. It never records an activation.
  preflight  `POST /private/magnets/<id>/activate/preflight`: the same checks, then the definition's exact
             bytes. Its only possible write is the idempotent lift.
  commit     `POST /private/magnets/<id>/activate/commit`: the artifact, verified whole, then one
             transaction holding the claim if it is new, the Admission, the record-only Turn with its
             `turn-said`, `magnet-extracted`, `produced` and the keyed result.

The two private paths exist only behind a boot secret (`mentis.web`). The secret proves who could read it
and nothing else, so nothing here takes a word of the artifact for what the record already knows.

Nothing runs here by itself: no queue, retry, schedule or runtime. `m1-page` is the first mode of `extract`,
not what `extract` means.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import threading

from mentis import artifacts
from mentis.conversation import anchors, posting, text as text_part
from mentis.fluid import _checks as W
from mentis.spine import held

from . import MAGNET_ID, SCHEMA_VERSION, Unreadable, checked, exists, unreadable_words
from . import _path
from . import schema

PROTOCOL = 1
ROUTE = "fluid-magnet-activate"
FORMAT = "mentis.magnet-extract"
MODE = "m1-page"
MAGNET_EXTRACTED = "magnet-extracted"
MEDIA_TYPE = "application/json"
DIGEST_HEADER = "X-Mentis-Artifact-SHA256"

PUBLIC_BODY_MOST = 64 * 1024
NESTING_MOST = 64
OP_MOST = 200
DEFINITION_MOST = W.MAX_BYTES
ANSWER_MOST = 1024 * 1024
ARTIFACT_MOST = held.MAX_BYTES
#: What a page's `kept` may cost in the answer. It says which facets weren't applied, of the few a
#: definition has, so this is far past a real one: without it, the record could be written and the
#: answer to it be too big to send.
KEPT_MOST = 64 * 1024

#: A length past any limit here. A body this long is refused, never read, so the number itself isn't used.
LENGTH_BEYOND = 2 ** 63 - 1

_PUBLIC_PATH = re.compile(r"/fluid/api/magnets/[^/]+/activate/*")
_PRIVATE_PATH = re.compile(r"/private/magnets/([^/]+)/activate/(preflight|commit)")

STATUSES = ("ok", "partial", "busy", "unavailable")
_ARTIFACT_FIELDS = ["format", "version", "mode", "magnet", "request", "definition", "operation", "page"]
#: Each result keeps these, whichever kind it is: what makes it traceable to where it was read.
_RESULT_KEEPS = {"kind", "version", "conversation", "author", "at"}

#: Python's one commit place, not a queue: a request overlapping its holder is Busy.
COMMIT_PLACE = threading.Lock()


# -- the words ------------------------------------------------------------------------------------
# Each is `refusals.json`'s, by its bytes.

def _reasoned(mid, code, words, *, retryable=False, kind=None) -> dict:
    return {"error": words, **({"kind": kind} if kind else {}), "refused": True, "magnet": mid,
            "reason": {"code": code, "message": words, "retryable": retryable}}


_CANNOT_RUN = {
    "schema-version-not-supported": "this Magnet definition is from a later schema than this build reads, so it is not run",
    "activation-not-supported": "this build activates a Magnet only by hand: its activation must be manual",
    "collection-not-supported": "this build collects only once per activation: its collection must be one-time",
    "synthesis-not-supported": "this build synthesizes nothing by itself: its synthesis must be manual",
    "notifications-not-supported": "this build sends no notifications: every notification must be off",
    "pipeline-not-supported": "this build runs one operation, extract, and nothing else",
    "extract-mode-not-supported": "this build's extract materializes one M1 page: its options may say only that mode",
    "ai-not-supported": "this build's extract uses no AI: its ai mode must be none",
    "output-not-supported": "this build's extract records the page: its outputs may say only records",
    "destination-not-supported": "this build's extract goes to the Magnet's own Conversation and nowhere else",
    "no-readable-source": "no source produced a useful result: none could be read, or what could be read gave no results. Nothing was recorded",
}


def _bad_request(words) -> dict:
    return {"error": words, "kind": "BadRequest"}


BODY_TOO_DEEP = _bad_request(f"the body is nested more than {NESTING_MOST} levels deep, so it was not read")
BODY_SURROGATE = _bad_request("the body holds text that cannot be encoded as UTF-8")
BODY_NOT_OBJECT = _bad_request("the body is a JSON object")
BODY_FIELDS = _bad_request("an activation's body is \"author\" and \"op\" and nothing else: what it reads "
                           "and records is the Magnet's own")
NOT_A_MAGNET_ID = _bad_request("that is not a Magnet id")
OP_MISSING = _bad_request("an activation needs an operation key, \"op\": a non-empty string of at most "
                          f"{OP_MOST} characters. It is what makes a retry the same activation")
PUBLIC_BODY_TOO_LARGE = {"error": "this request's body is over the 65,536 bytes an activation takes, so "
                                  "nothing was read or recorded",
                         "kind": "ContentTooLarge", "limit": PUBLIC_BODY_MOST}


def cannot_run(mid, code) -> dict:
    return _reasoned(mid, code, _CANNOT_RUN[code])


def no_definition(mid) -> dict:
    return {"error": schema.MISSING, "kind": "NotFound", "refused": True, "magnet": mid}


def _unreadable(words) -> dict:
    return {"error": words, "kind": "Unreadable"}


def definition_too_large(mid) -> dict:
    return _unreadable(f"the Magnet definition {mid} could not be read: it is over 262,144 bytes")


def definition_surrogate(mid) -> dict:
    return _unreadable(f"the Magnet definition {mid} could not be read: it holds text that cannot be "
                       "encoded as UTF-8")


def deleted(mid) -> dict:
    return _reasoned(mid, "magnet-deleted-during-activation",
                     "this Magnet was deleted during its activation, so nothing was recorded")


def busy(mid) -> dict:
    return _reasoned(mid, "busy", "another activation holds the one place, so nothing was recorded. Ask again",
                     retryable=True, kind="Busy")


def sources_busy(mid) -> dict:
    return _reasoned(mid, "sources-busy", "no source produced a useful result and at least one was busy, so "
                                          "nothing was recorded. Ask again", retryable=True, kind="Busy")


def artifact_too_large(mid) -> dict:
    return _reasoned(mid, "artifact-too-large", "this activation's page is over the 25 MiB an artifact may "
                                                "be, so nothing was recorded", kind="ContentTooLarge")


def processor_unavailable(mid) -> dict:
    return _reasoned(mid, "processor-unavailable", "this server has no processor for a Magnet's activation, "
                                                   "so nothing was read or recorded", retryable=True,
                     kind="ProcessorUnavailable")


def internal_protocol_error(mid) -> dict:
    words = ("this server's two halves disagree about this activation, and nothing was written. It is a "
             "defect to report, not a configuration to change")
    return {"error": words, "kind": "InternalProtocolError", "magnet": mid,
            "reason": {"code": "internal-protocol-error", "message": words, "retryable": False}}


class _Stop(Exception):
    """An answer that isn't a result, and who it can name. Raised inside a transaction, it writes nothing."""

    def __init__(self, status, body, author=None, op=None):
        super().__init__("stopped")
        self.status, self.body, self.author, self.op = status, body, author, op


def identity(mid) -> dict:
    return {"route": ROUTE, "magnet": mid}


# -- the door's length ----------------------------------------------------------------------------

def names_activation(path, *, private: bool) -> bool:
    """Whether a path is this door's, so its length is read by value. A private one only behind a secret:
    Python alone has no such path, which means what it always did."""
    return bool(_PUBLIC_PATH.fullmatch(path) or (private and _PRIVATE_PATH.fullmatch(path)))


def length_by_value(said) -> int:
    """The number a `Content-Length` of digits spells, however it was spelled. `parse_request` has already
    refused anything but digits. Never `int()` on the digits as sent: past 4,300 of them it raises, zeros or
    not, and that failure came before the door could answer anything."""
    digits = str(said or "0").lstrip("0")
    return LENGTH_BEYOND if len(digits) > 18 else int(digits or "0")


def private_step(path) -> tuple[str, str] | None:
    """(the raw Magnet segment, `preflight` or `commit`), or None. Any one segment: a malformed id is a
    refusal from the first check, never a 404."""
    found = _PRIVATE_PATH.fullmatch(path)
    return (found.group(1), found.group(2)) if found else None


# -- what can't be carried ------------------------------------------------------------------------

def holds_surrogate(value) -> bool:
    """With a stack of its own: `json.loads` gives back a depth that recursion here wouldn't reach."""
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
    """Asked of the text `json.loads` would read, before it does, so where it gives up decides nothing.
    What can't be decoded is `json.loads`'s to say."""
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
            if depth > NESTING_MOST:
                return True
        elif c in "]}":
            depth = max(depth - 1, 0)
    return False


# -- the public body ------------------------------------------------------------------------------

def _asked(st, segment, raw) -> tuple[str, str, dict | None]:
    """(who, the key, what the key already came to) of a public body, in the contract's order, or `_Stop`.
    Nothing about the Magnet is read or changed here."""
    from mentis.fluid import commands
    if not MAGNET_ID.fullmatch(segment):
        raise _Stop(400, NOT_A_MAGNET_ID)
    if nested_too_deep(raw):
        raise _Stop(400, BODY_TOO_DEEP)
    try:
        body = json.loads(raw or b"{}")
    except ValueError as exc:
        raise _Stop(400, _bad_request(f"the body is not JSON: {exc}")) from None
    if holds_surrogate(body):
        raise _Stop(400, BODY_SURROGATE)
    if not isinstance(body, dict):
        raise _Stop(400, BODY_NOT_OBJECT)
    if set(body) - {"author", "op"}:
        raise _Stop(400, BODY_FIELDS)
    by, bad = commands._author(st, body)
    if bad:
        raise _Stop(bad[0], bad[1])
    op = body.get("op")
    if not isinstance(op, str) or not op.strip() or len(op) > OP_MOST:
        raise _Stop(400, OP_MISSING, by)
    return by, op, _keyed(st, by, op, segment)


def _as_stored(prior) -> dict:
    """What the key came to, in the contract's order. The record keeps a mapping sorted, and a replay is
    the same bytes as the first answer but for its last two fields (`results.json`)."""
    page, artifact, operation = prior["page"], prior["artifact"], prior["operation"]
    return {"magnet": prior["magnet"],
            "operation": {k: operation[k] for k in ("index", "op", "mode", "name")},
            "state": prior["state"], "conversation": prior["conversation"],
            "conversation_created": prior["conversation_created"], "post": prior["post"],
            "artifact": {k: artifact[k] for k in ("ref", "digest", "size", "media_type")},
            "page": {"cursor": page["cursor"], "sources": page["sources"], "results": page["results"],
                     "statuses": {s: page["statuses"][s] for s in STATUSES},
                     "kept": [{"facet": k["facet"], "reason": k["reason"]} for k in page["kept"]]},
            "replayed": True}


def _keyed(st, by, op, mid) -> dict | None:
    """What this key came to, or None. A key used for another request is its 422."""
    try:
        prior = anchors.prior_outcome(st.cv, by, op, identity(mid))
    except anchors.Refused as refused:
        raise _Stop(422, {**refused.refusal, "refused": True}, by, op) from None
    return None if prior is None else _as_stored(prior)


def _cursor_now(st) -> str:
    from mentis.fluid import read as _read
    return _read.change_cursor(st.corpus.advance())


def public(st, segment, raw) -> tuple[int, dict]:
    """Python alone, or the front's rule rolled back: every check on the body, and a valid one is
    `ProcessorUnavailable`. A key already used is still answered from the record, which writes nothing."""
    try:
        _by, _op, prior = _asked(st, segment, raw)
    except _Stop as stop:
        return stop.status, stop.body
    if prior is not None:
        return 200, {**prior, "cursor": _cursor_now(st)}
    return 503, processor_unavailable(segment)


# -- the definition -------------------------------------------------------------------------------

def _cannot_run_code(value) -> str | None:
    """The first of the contract's lines a checked definition fails, or None. Its later `schema_version`
    is asked before this, because the full check refuses one."""
    if (value.get("activation") or {}).get("mode") != "manual":
        return "activation-not-supported"
    if value["collection"]["mode"] != "one-time":
        return "collection-not-supported"
    if value["synthesis"]["mode"] != "manual":
        return "synthesis-not-supported"
    if any(value["notifications"].values()):
        return "notifications-not-supported"
    operations = (value.get("processing") or {}).get("operations") or []
    if len(operations) != 1 or operations[0]["op"] != "extract":
        return "pipeline-not-supported"
    if (operations[0].get("options") or {}) not in ({}, {"mode": MODE}):
        return "extract-mode-not-supported"
    if "ai" in value and value["ai"] != {"mode": "none"}:
        return "ai-not-supported"
    if "outputs" in value and value["outputs"] != ["records"]:
        return "output-not-supported"
    if "destinations" in value and value["destinations"] != [{"kind": "magnet-conversation"}]:
        return "destination-not-supported"
    if not any(s["kind"] == "conversation" for s in value["sources"]):
        return "no-readable-source"
    return None


def _is_later_schema(data) -> bool:
    version = data.get("schema_version") if isinstance(data, dict) else None
    return isinstance(version, int) and not isinstance(version, bool) and version > SCHEMA_VERSION


def _snapshot(st, mid, by, op) -> tuple[bytes, str, dict]:
    """(the definition's exact bytes, their text, what they read as), or `_Stop`. Under the definition
    lock, after the existing lift, so an otherwise good unlifted Magnet doesn't get a false 404. One read."""
    from mentis.fluid import arrangements
    root = st.corpus.root
    with W._lock(root):
        arrangements.lift_all(root)
        try:
            with open(_path(root, mid), "rb") as file:
                raw = file.read(DEFINITION_MOST + 1)
        except FileNotFoundError:
            raise _Stop(404, no_definition(mid), by, op) from None
        except OSError as exc:
            raise _Stop(409, _unreadable(unreadable_words(mid, exc)), by, op) from None
    if len(raw) > DEFINITION_MOST:
        raise _Stop(409, definition_too_large(mid), by, op)
    try:
        text = raw.decode("utf-8")
        data = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise _Stop(409, _unreadable(unreadable_words(mid, exc)), by, op) from None
    if holds_surrogate(data):
        raise _Stop(409, definition_surrogate(mid), by, op)
    if _is_later_schema(data):
        raise _Stop(422, cannot_run(mid, "schema-version-not-supported"), by, op)
    try:
        value = checked(mid, data)
    except Unreadable as exc:
        raise _Stop(409, _unreadable(str(exc)), by, op) from None
    code = _cannot_run_code(value)
    if code:
        raise _Stop(422, cannot_run(mid, code), by, op)
    return raw, text, value


# -- the private answers --------------------------------------------------------------------------

def _envelope(state, segment, author, op, status, body) -> dict:
    return {"protocol": PROTOCOL, "state": state, "magnet": segment, "author": author, "op": op,
            "status": status, "body": body}


def _refused(segment, stop: _Stop) -> dict:
    if stop.status == 502:
        return _envelope("internal-protocol-error", segment, stop.author, stop.op, 502, stop.body)
    return _envelope("refused", segment, stop.author, stop.op, stop.status, stop.body)


def refused(segment, status, body) -> dict:
    """An answer given before anything was read that could name who asked."""
    return _refused(segment, _Stop(status, body))


def _protocol_error(segment, author=None, op=None) -> _Stop:
    return _Stop(502, internal_protocol_error(segment), author, op)


def wire(answer, segment) -> bytes:
    """A private answer's bytes, which never pass the limit and always encode: Rust reads either failure
    as a disagreement, so one is said here first."""
    try:
        data = json.dumps(answer, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        data = None
    if data is None or len(data) > ANSWER_MOST:
        data = json.dumps(_refused(segment, _protocol_error(segment, answer.get("author"),
                                                            answer.get("op"))),
                          ensure_ascii=False).encode("utf-8")
    return data


def _replay(st, segment, by, op, prior) -> dict:
    return _envelope("replay", segment, by, op, 200, {**prior, "cursor": _cursor_now(st)})


def _preflight_body(wire_text, segment) -> bytes:
    """The public body's exact bytes, from a request that is exactly one, or `_Stop`."""
    try:
        asked = json.loads(wire_text)
    except (ValueError, RecursionError):
        raise _protocol_error(segment) from None
    if (not isinstance(asked, dict) or set(asked) != {"protocol", "magnet", "public_body_base64"}
            or type(asked["protocol"]) is not int or asked["protocol"] != PROTOCOL
            or asked["magnet"] != segment or not isinstance(asked["public_body_base64"], str)):
        raise _protocol_error(segment)
    try:
        return base64.b64decode(asked["public_body_base64"], validate=True)
    except (binascii.Error, ValueError):
        raise _protocol_error(segment) from None


def preflight(st, segment, wire_text) -> dict:
    """What an activation may go on with: `ready`, or the replay or refusal that decides it. A key's answer
    comes before anything about the Magnet is read, and a replay reads none of it."""
    try:
        body = _preflight_body(wire_text, segment)
        by, op, prior = _asked(st, segment, body)
        if prior is not None:
            return _replay(st, segment, by, op, prior)
        raw, text, value = _snapshot(st, segment, by, op)
    except _Stop as stop:
        return _refused(segment, stop)
    return {"protocol": PROTOCOL, "state": "ready", "magnet": segment,
            "request": {"author": by, "op": op, "identity": identity(segment)},
            "definition": {"sha256": hashlib.sha256(raw).hexdigest(), "raw": text, "value": value}}


# -- the commit: verifying ------------------------------------------------------------------------

def _no_constant(said):
    raise ValueError(f"{said} is not JSON")


def _same(one, other) -> bool:
    """Equal as JSON says them. `==` would take `true` for `1`."""
    return json.dumps(one, sort_keys=True) == json.dumps(other, sort_keys=True)


def _exact(value, *fields) -> bool:
    return isinstance(value, dict) and list(value) == list(fields)


def _whole_int(value, wanted) -> bool:
    return type(value) is int and value == wanted


def _verified_page(segment, value, page, bad) -> tuple[str | None, dict]:
    """What a page's envelope comes to, or `bad`: (the page's state, or None with a useful-source refusal
    to come, and its summary)."""
    from mentis.fluid import read as _read
    if (not isinstance(page, dict) or page.get("magnet") != segment or page.get("mode") != "page"
            or not isinstance(page.get("cursor"), str) or not isinstance(page.get("kept"), list)
            or not isinstance(page.get("sources"), list)):
        raise bad
    try:
        _read.parse_change_cursor(page["cursor"])
    except _read.BadRequest:
        raise bad from None
    if not all(_exact(k, "facet", "reason") and isinstance(k["facet"], str) and isinstance(k["reason"], str)
               for k in page["kept"]):
        raise bad
    if len(json.dumps(page["kept"]).encode("utf-8")) > KEPT_MOST:
        raise bad
    configured = value["sources"]
    if len(page["sources"]) != len(configured):
        raise bad
    statuses = {s: 0 for s in STATUSES}
    results, useful = 0, 0
    for one, source in zip(page["sources"], configured):
        if not isinstance(one, dict) or not _same(one.get("source"), source):
            raise bad
        if one.get("key") != schema.source_key(source) or one.get("summary") is not None:
            raise bad
        status, got = one.get("status"), one.get("results")
        if status not in STATUSES or not isinstance(got, list):
            raise bad
        if status in ("busy", "unavailable") and got:
            raise bad
        for result in got:
            if not isinstance(result, dict) or not _RESULT_KEEPS <= set(result):
                raise bad
            if result.get("via") == "home" and result["conversation"] != source.get("conversation"):
                raise bad
        statuses[status] += 1
        results += len(got)
        useful += 1 if got else 0
    summary = {"cursor": page["cursor"], "sources": len(configured), "results": results,
               "statuses": statuses, "kept": page["kept"]}
    if not useful:
        return None, summary
    whole = statuses["ok"] == len(configured) and not page["kept"]
    return ("complete" if whole else "partial"), summary


def _verified(st, segment, raw, digest, ctype) -> dict:
    """Python's checks on a commit, 2 to 9 in the contract's order, or `_Stop`: what can be recorded."""
    from mentis.fluid import commands
    bad = _protocol_error(segment)
    if ctype != MEDIA_TYPE or hashlib.sha256(raw).hexdigest() != digest:
        raise bad
    try:
        art = json.loads(raw.decode("utf-8"), parse_constant=_no_constant)
    except (ValueError, RecursionError):
        raise bad from None
    if holds_surrogate(art):
        raise bad
    if not _exact(art, *_ARTIFACT_FIELDS):
        raise bad
    if (art["format"] != FORMAT or not _whole_int(art["version"], 1) or art["mode"] != MODE
            or art["magnet"] != segment or not MAGNET_ID.fullmatch(segment)):
        raise bad
    request = art["request"]
    if not _exact(request, "author", "op", "identity") or not isinstance(request["author"], str):
        raise bad
    by, refused = commands._author(st, {"author": request["author"]})
    if refused or by != request["author"]:
        raise bad
    op = request["op"]
    if not isinstance(op, str) or not op.strip() or len(op) > OP_MOST:
        raise _protocol_error(segment, by)
    bad = _protocol_error(segment, by, op)
    if not _same(request["identity"], identity(segment)):
        raise bad
    definition = art["definition"]
    if not _exact(definition, "sha256", "raw", "value") or not isinstance(definition["raw"], str):
        raise bad
    definition_bytes = definition["raw"].encode("utf-8")
    if (len(definition_bytes) > DEFINITION_MOST
            or hashlib.sha256(definition_bytes).hexdigest() != definition["sha256"]):
        raise bad
    try:
        value = checked(segment, json.loads(definition["raw"]))
    except (ValueError, RecursionError, Unreadable):
        raise bad from None
    if _cannot_run_code(value) or not _same(definition["value"], value):
        raise bad
    named = value["processing"]["operations"][0]
    operation = art["operation"]
    if (not _exact(operation, "index", "op", "mode", "name", "options")
            or not _whole_int(operation["index"], 0) or operation["op"] != "extract"
            or operation["mode"] != MODE or operation["name"] != named.get("name")
            or not _same(operation["options"], named.get("options") or {})):
        raise bad
    state, summary = _verified_page(segment, value, art["page"], bad)
    if state is None:
        if any(s.get("status") == "busy" for s in art["page"]["sources"]):
            raise _Stop(503, sources_busy(segment), by, op)
        raise _Stop(422, cannot_run(segment, "no-readable-source"), by, op)
    return {"by": by, "op": op, "state": state, "summary": summary, "value": value,
            "operation": {k: operation[k] for k in ("index", "op", "mode", "name")},
            "definition_sha256": definition["sha256"]}


# -- the commit: recording ------------------------------------------------------------------------

def _what_the_file_names(st, mid, captured) -> str | None:
    """The Conversation the definition names now, or, where it can't be read now, what the snapshot this
    activation ran on named. A definition changed since preflight doesn't invalidate the activation."""
    from . import read
    try:
        config = read(st.corpus.root, mid)
    except Unreadable:
        config = captured
    return (config or {}).get("conversation")


def _said(summary, state) -> str:
    results, sources = summary["results"], summary["sources"]
    return (f"Extracted one page from this Magnet ({state}): {results} result{'' if results == 1 else 's'} "
            f"from {sources} source{'' if sources == 1 else 's'}.")


def _record(st, mid, got, digest, size) -> dict:
    """Everything the record holds of this activation, as one, or nothing. Checks 10 and 11 are here,
    under the write lock, so two racing commits can't both miss the key, and a deletion that comes after
    the look is one that came after this activation."""
    from mentis.fluid import commands
    import mentis.web as _web
    corpus, cv = st.corpus, st.cv
    by, op = got["by"], got["op"]
    with corpus.atomic():
        prior = _keyed(st, by, op, mid)
        if prior is not None:
            return prior
        if not exists(corpus.root, mid):
            raise _Stop(422, deleted(mid), by, op)
        wrote = _web._observed_writer(st, None)
        try:
            cid, created = commands._own_from(st, by, "magnet", mid,
                                              _what_the_file_names(st, mid, got["value"]), None, wrote)
        except commands._Undone as undone:
            raise _Stop(undone.answer[0], undone.answer[1], by, op) from None
        adm = artifacts.admit_generated(corpus, digest, size, source=f"magnet:{mid}", door="magnet-extract",
                                        name=f"{mid}-extract.json", media_type=MEDIA_TYPE, actor=by,
                                        written_by=wrote)
        summary = got["summary"]
        out, _ = posting.post(cv, corpus, cid, {
            "author": by, "action": posting.RECORD_ONLY,
            "parts": [text_part(_said(summary, got["state"])),
                      {"type": "file", "ref": adm, "media_type": MEDIA_TYPE, "alt": f"{mid}-extract.json"}],
        }, agents=st.agents, written_by=lambda: wrote)
        if "error" in out:
            raise _Stop(422, {**out, "refused": True}, by, op)
        post = out["turn"]
        artifact = {"ref": adm, "digest": digest, "size": size, "media_type": MEDIA_TYPE}
        artifacts.record_generated(
            corpus, cv, adm, act=MAGNET_EXTRACTED, actor=by, conversation=cid, turn=post,
            because="its Magnet was activated by hand", written_by=wrote,
            detail={"magnet": mid, "mode": MODE, "operation": {"index": got["operation"]["index"],
                                                               "name": got["operation"]["name"]},
                    "definition_sha256": got["definition_sha256"],
                    "page": {"cursor": summary["cursor"], "state": got["state"],
                             "results": summary["results"], "statuses": summary["statuses"]},
                    "artifact": {k: artifact[k] for k in ("ref", "digest", "size")}})
        result = {"magnet": mid, "operation": got["operation"], "state": got["state"], "conversation": cid,
                  "conversation_created": created, "post": post, "artifact": artifact, "page": summary}
        anchors.record_outcome(cv, by, op, identity(mid), result, conversation=cid)
    return result


def commit(st, segment, raw, digest, ctype) -> dict:
    """A verified artifact, recorded once. Busy is the caller's, before the body is read: it holds
    `COMMIT_PLACE` across this. A failure no check foresaw isn't caught: the transaction ends writing
    nothing and the door's 500 is an outcome Rust can't vouch for, so the same key is what recovers it."""
    from mentis.fluid import commands
    from . import asking_for_conversation
    try:
        got = _verified(st, segment, raw, digest, ctype)
        by, op = got["by"], got["op"]
        # Asked first too, so a replay or a refusal doesn't hold bytes nothing will name.
        prior = _keyed(st, by, op, segment)
        if prior is not None:
            return _replay(st, segment, by, op, prior)
        if not exists(st.corpus.root, segment):
            raise _Stop(422, deleted(segment), by, op)
        digest, _fresh = held.put(st.corpus.root, raw)
        with asking_for_conversation(st.corpus.root, segment):
            recorded = _record(st, segment, got, digest, len(raw))
            if recorded.get("replayed"):
                return _replay(st, segment, by, op, recorded)
            # After the commit: a file that can't take it refuses nothing. The claim keeps answering, and
            # a later request tells it again.
            commands._tell_the_file(st, ("magnet", segment), recorded["conversation"])
    except _Stop as stop:
        return _refused(segment, stop)
    return _envelope("committed", segment, by, op, 201,
                     {**recorded, "replayed": False, "cursor": _cursor_now(st)})


__all__ = ["ANSWER_MOST", "ARTIFACT_MOST", "COMMIT_PLACE", "DIGEST_HEADER", "MAGNET_EXTRACTED",
           "PUBLIC_BODY_MOST", "PUBLIC_BODY_TOO_LARGE", "artifact_too_large", "busy", "commit",
           "internal_protocol_error", "length_by_value", "names_activation", "preflight", "private_step",
           "public", "refused", "wire"]
