"""The Python half of the shared Magnet message-boundary contract check.

Revised contract adm-c5c73679ac1e sections 2-5, which accepts both BLOCKING findings
of contract review adm-41c083ce0dc9. The review asked for canonical
JSON/digest, concrete bounds and the covered definition fields to be defined
in the SHARED contract; this is the Python side of that definition.

`apps/fluid-web/tests/fixtures/magnet_boundary_vectors.json` is the published
artifact. The TypeScript implementation lives in
`apps/fluid-web/src/quiet2/magnets/contract.ts` and is checked against the same
file by `apps/fluid-web/tests/quiet_magnet_contract_unit.ts`. Here the rules
are applied through the standard library instead, so agreement between the two
is evidence about the rules and not two readings of one implementation.

WHAT THIS IS NOT: the server's managed route. A owns that (section 6). When A lands
the production canonicaliser, point `canonical` below at it and these vectors
become its conformance suite unchanged.
"""
import hashlib
import json
from pathlib import Path

import pytest

# THE WORLD THE DOOR ORACLE BELOW NEEDS: the same fixture Magnet, real grant
# and real `/api/worker` call the rest of Part A is checked with. Imported
# rather than rebuilt, so this file's claim about the door is the door's.
from tests.test_magnet_activation import (MAGNET, built, world,  # noqa: F401
                                          artifact_of, define_from, ask_commit)
from tests.test_magnet_scope import (magnet, exchange, granted,  # noqa: F401
                                     refused, elsewhere)
from tests.decision_descriptors import question

VECTORS = (Path(__file__).parents[1] / "apps" / "fluid-web" / "tests"
           / "fixtures" / "magnet_boundary_vectors.json")

#: section 3. Recursively sorted object keys by Unicode scalar order (which is what
#: Python's `sorted` on `str` gives), original array order, UTF-8, no BOM or
#: whitespace, literal Unicode, only the escaping JSON requires, and no
#: Unicode or newline normalisation. Numbers in this schema are integers.
CANONICAL_KWARGS = dict(sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, allow_nan=False)


class Refused(Exception):
    """Carries the contract's refusal reason, as `MANAGED_REFUSAL` names it."""

    def __init__(self, reason: str, words: str = ""):
        super().__init__(words or reason)
        self.reason = reason


def _integers_and_real_unicode(value) -> None:
    """Refuse what the schema does not hold, before anything is serialised."""
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return
    if isinstance(value, float):
        raise Refused("selector-schema", "this schema holds integers only")
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as e:        # a lone surrogate has no UTF-8
            raise Refused("invalid-unicode", str(e)) from e
        return
    if isinstance(value, list):
        for v in value:
            _integers_and_real_unicode(v)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise Refused("selector-schema", "object keys are strings")
            _integers_and_real_unicode(k)
            _integers_and_real_unicode(v)
        return
    raise Refused("selector-schema", "unsupported value %r" % (value,))


def canonical(value) -> str:
    _integers_and_real_unicode(value)
    return json.dumps(value, **CANONICAL_KWARGS)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def text_digest(text: str) -> str:
    """sections 3 and 4: the digest of EXACT authored text, its own UTF-8 bytes."""
    _integers_and_real_unicode(text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def vectors():
    assert VECTORS.exists(), "the published vectors are missing: %s" % VECTORS
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def test_published_bounds_are_the_contract(vectors):
    assert vectors["contract"] == "adm-c5c73679ac1e"
    assert vectors["bounds"] == {
        "managed_context_version": 1,
        "selector_max_bytes": 16 * 1024,
        "selector_max_references": 16,
        "hydrated_context_max_bytes": 64 * 1024,
        "identifier_max_chars": 128,
        "digest_hex_chars": 64,
        "managed_request_door": "/fluid/api/requests",
        # section 2 keeps the EXISTING gate refusal, not a renamed one.
        "retained_gate_code": "grounded-answers-blocked",
    }


def test_every_canonical_vector_reproduces(vectors):
    assert len(vectors["canonical"]) >= 9
    for v in vectors["canonical"]:
        assert canonical(v["value"]) == v["canonical"], v["name"]
        assert digest(v["value"]) == v["digest"], v["name"]
        assert len(v["digest"]) == 64 and v["digest"] == v["digest"].lower()


def test_keys_sort_by_unicode_scalar_not_utf16_code_unit():
    """The one place the two languages could silently diverge.

    JavaScript's default sort compares UTF-16 code units, which would put an
    astral-plane key BEFORE U+FFFD. Scalar order puts it after. Spelled out
    here so the expectation does not come from either implementation.
    """
    assert canonical({"a": 1, "\ufffd": 2, "\U0001f600": 3, "z": 4}) == (
        '{"a":1,"z":4,"\ufffd":2,"\U0001f600":3}')
    assert sorted(["\ufffd", "\U0001f600"]) == ["\ufffd", "\U0001f600"]


def test_only_required_escaping_and_no_normalisation():
    assert canonical({"s": "\u007f"}) == '{"s":"\u007f"}'      # DEL is literal
    assert canonical({"s": "\u0001"}) == '{"s":"\\u0001"}'
    assert canonical({"s": "\n\t\r"}) == '{"s":"\\n\\t\\r"}'
    assert canonical({"s": '"\\'}) == '{"s":"\\"\\\\"}'
    assert canonical("\u00e9") != canonical("e\u0301")
    assert canonical([3, 1, 2]) == "[3,1,2]"


def test_exact_authored_text_digests_untrimmed(vectors):
    for v in vectors["text_digests"]:
        assert text_digest(v["text"]) == v["digest"], v["name"]
    assert text_digest("") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    for pair in vectors["distinct_digests"]:
        assert text_digest(pair["left"]) != text_digest(pair["right"]), pair["why"]


#: section 3, and `mentis.conversation.versions.flow_text`, which is what the server
#: actually validates and reads the record back through: text parts and the
#: characters of inline references, in order.
AUTHORED_FLOW_PART_TYPES = ("text", "topic", "turn", "conversation",
                            "acquired", "object")


def flow_text(parts) -> str:
    return "".join(p.get("text") or "" for p in parts or ()
                   if p.get("type") in AUTHORED_FLOW_PART_TYPES)


def test_flow_text_mirrors_the_server_projection():
    """The TS mirror must cover exactly the server's reference part types.

    If `versions.py` ever gains or loses one, this fails and the shared
    contract gets updated rather than drifting.
    """
    from mentis.conversation import versions

    assert set(AUTHORED_FLOW_PART_TYPES) == {"text"} | set(versions._REFERENCE_PARTS)
    parts = [{"type": "text", "text": " a "},
             {"type": "topic", "ref": "ent-1", "text": "#b"},
             {"type": "file", "ref": "adm-1", "text": "ignored"}]
    assert flow_text(parts) == versions.flow_text(parts) == " a #b"


def test_published_flow_text_vectors_agree(vectors):
    for v in vectors["flow_text"]:
        assert (v["text"] == flow_text(v["parts"])) == v["agrees"], v["name"]


def test_a_chip_emitted_as_a_part_would_enter_authored_text(vectors):
    """B2/section 3: why a dropped chip may not become a content part.

    A chip becomes the same part types as a typed inline reference, so its
    generated label and separator are indistinguishable from characters the
    owner typed, and `flow_text` takes them as authored. The selected object's
    identity travels in the audited selector instead.
    """
    from mentis.conversation import versions

    case = next(v for v in vectors["flow_text"]
                if v["name"] == "chip-emitted-as-a-part-pollutes")
    polluted = versions.flow_text(case["parts"])
    assert polluted != case["text"] and "Collection batch 7" in polluted
    assert case["agrees"] is False


def test_refusal_reasons_and_their_statuses_are_the_existing_conventions(vectors):
    """section 4: 401/403 authentication/authority, 409 Brain/stale/edited/conflict,
    422 invalid schema or intent. Nothing new is invented."""
    published = {v["reason"] for v in vectors["selector_refusals"]}
    published |= {v["reason"] for v in vectors["canonical_refusals"]}
    assert published <= {
        "selector-schema", "duplicate-selection", "too-many-references",
        "identifier-too-long", "invalid-unicode", "selector-too-large",
    }
    # Each refusal vector really is refused by the canonical rules or by shape.
    for v in vectors["canonical_refusals"]:
        with pytest.raises(Refused) as got:
            canonical(v["value"])
        assert got.value.reason == v["reason"], v["name"]


def test_an_empty_object_is_not_the_empty_selection(vectors):
    """sections 2 and 3: missing and null mean ordinary empty with a server-made snapshot;
    `{}` is malformed and refuses before any domain write."""
    empty = next(v for v in vectors["canonical"]
                 if v["name"] == "empty-selector-v1")["value"]
    assert empty == {"version": 1, "mode": "ordinary",
                     "configuration_digest": empty["configuration_digest"],
                     "perspective": None, "references": []}
    assert empty["perspective"] is None and empty["references"] == []
    assert {} != empty
    assert any(v["name"] == "empty-object" for v in vectors["selector_refusals"])


def test_the_retained_content_gate_is_open_because_the_scope_is_enforced():
    """section 2, REVISED BY PART A, which is the condition section 2 named.

    The gate was shut on one condition: that configured-source read
    enforcement did not exist (owner correction `ent-d85254fe5e1b`). It does
    now -- `mentis.magnet.scope` at the one door -- so the gate is open, and
    this oracle holds the thing that actually matters instead: that the gate
    is open ONLY while the enforcement it waited on is in place. The refusal
    keeps its existing code rather than being renamed, so a build that shuts
    the gate again says the same words (`retained_gate_code` above).
    """
    from mentis.magnet import perspectives, scope

    assert perspectives.GROUNDED_ANSWERS_ENABLED is True
    assert perspectives.require_grounded() is None

    # THE ENFORCEMENT, NOT A PROMISE OF IT: the one door narrows what a
    # Magnet-scoped execution may call, and refuses each target outside that
    # Magnet's collection scope.
    from mentis.worker import _magnet_confined, permitted
    confined = scope.parsed(scope.scope_name("mag-oracle"))
    assert confined is not None and confined.magnet == "mag-oracle"
    may = set(permitted(scope.scope_name("mag-oracle"), ["respond"]))
    # ADMITTED BY THE TABLE, WHICH ON ITS OWN PROVES NOTHING about what the
    # door answers. This line used to be the whole claim, commented "it can
    # still answer the owner" -- and `respond` was 403 at the door for every
    # Magnet-scoped run, because `why_not` had no branch for it (A+B security
    # review, blocking finding 1, Turn `ent-77ca0fefb4fe`). The oracle that
    # holds the capability is `test_every_operation_the_table_admits_is_
    # reachable_at_the_real_door` below: it CALLS each one.
    assert "respond" in may
    for brain_wide in ("find", "recall", "governed", "work_overview", "brief",
                       "delegate", "owner_decisions"):
        assert brain_wide not in may, brain_wide
    # A synthesis execution holds no source read at all, so no authorization
    # can reach it (amendment adm-c38044ee5157 section 3).
    synthesis = set(permitted(scope.scope_name("mag-oracle", synthesis=True),
                              ["respond"]))
    assert not synthesis & set(scope.OUTSIDE_READS)
    assert set(scope.OUTSIDE_READS) <= set(
        permitted(scope.scope_name("mag-oracle"), ["respond"]))
    assert callable(_magnet_confined)

    # AND THE GATE'S WORDS ARE STILL THERE for a build that shuts it again.
    import contextlib
    with contextlib.ExitStack() as stack:
        stack.callback(setattr, perspectives, "GROUNDED_ANSWERS_ENABLED", True)
        perspectives.GROUNDED_ANSWERS_ENABLED = False
        with pytest.raises(perspectives.Refused) as got:
            perspectives.require_grounded()
    assert got.value.refusal["code"] == "grounded-answers-blocked"
    assert got.value.refusal["refused"] is True


#: The fail-closed tail's own words. An operation that reaches them was
#: admitted by `MAY_CALL` and decided by nothing, which is the defect.
FELL_THROUGH = "has no Magnet-scoped reading"

def _at_door(w, capability, op, args):
    """One call at the real `/api/worker` door, with the arguments as a dict.

    `test_magnet_scope.door` takes them as keywords, and a reaction's own
    `token` argument collides with the capability's there. Same request.
    """
    from mentis.worker import CAPABILITY_HEADER
    from tests.test_magnet_activation import send
    got = send(w.alone, "/api/worker",
               [["Content-Type", "application/json"],
                [CAPABILITY_HEADER, capability]],
               json.dumps({"corpus": w.state.path, "op": op,
                           "args": args}).encode("utf-8"), owner=False, half_close=False)
    return got["status"], json.loads(got["body"] or b"{}")


def _exchange_calls(version, anchor):
    """THE EIGHT WRITES `MAY_CALL` ADMITS, with the arguments a real run sends.

    `version` is a Turn of the Magnet's own Conversation and `anchor` an anchor
    in it, so the two that name a record name one inside the scope: what is
    being asked here is whether the gate lets them through, not whether it
    narrows (the narrowing is asserted separately, with a record that is
    outside).
    """
    return (
        ("respond", {"text": "what the collection actually held"}),
        ("record_discovered_work", {"work": "a source stopped updating"}),
        ("return_artifact", {"name": "note.txt", "media_type": "text/plain",
                             "bytes_b64": "aGVsbG8="}),
        ("request_decision",
         {"questions": [question("Which source should this Magnet keep?")]}),
        ("request_input", {"question": "which year?"}),
        ("answer", {"field": "year", "value": "2026"}),
        ("anchor", {"version": version, "type": "version"}),
        ("react", {"anchor": anchor, "token": "ack"}),
    )


def _anchored(w, turn) -> str:
    """An anchor on a Turn of the Magnet's own Conversation, written by the
    owner: what a run's `react` has to be able to name."""
    from mentis.conversation import anchors
    return anchors.create_anchor(w.cv, {"version": turn, "type": "version"},
                                 by=w.owner)["anchor"]


def test_every_operation_the_table_admits_is_reachable_at_the_real_door(magnet):
    """THE ORACLE THE WEAK ONE ABOVE SHOULD ALWAYS HAVE BEEN. It calls.

    `MAY_CALL` admitting an operation and the door serving it are two
    different facts, and for eight operations they disagreed: `why_not` had no
    branch for `respond`, `request_decision`, `request_input`, `answer`,
    `react`, `anchor`, `record_discovered_work` or `return_artifact`, so each
    fell through to the fail-closed tail and was 403. Nothing failed visibly,
    because dispatch's completion fallback still delivered an answer -- which
    is exactly why only a test that asks the door can hold this.

    Three things are asserted, at the real `/api/worker` door under a real
    grant minted by the real Authority:

      (i)   NO operation `MAY_CALL` admits reaches the fail-closed tail. Total
            over the table, so an operation added to `MAY_CALL` without a
            branch in `why_not` fails here rather than in production.
      (ii)  The writes an exchange needs are SERVED, not merely reached.
      (iii) The tail still refuses what the table does not admit, and the new
            branches still narrow: a record of another Conversation, named by
            one of those writes, is refused.
    """
    from mentis.magnet import scope as S
    w = magnet
    ex = exchange(w)
    scope_name = S.scope_name(MAGNET)
    _, token = granted(w, ex, scope=scope_name,
                       operations=list(S.MAY_CALL) + list(S.OUTSIDE_READS))

    # (i) TOTAL OVER THE AUTHORITY TABLE. The tail fires before any handler
    # check, so minimal arguments are enough to tell "decided" from "fell
    # through": a reached operation refuses for its own reasons or succeeds.
    fell = {}
    for op in S.MAY_CALL + S.OUTSIDE_READS:
        status, got = _at_door(w, token, op, {})
        words = str(got.get("error") or "")
        if FELL_THROUGH in words:
            fell[op] = (status, words[:120])
    assert not fell, f"admitted by MAY_CALL, decided by nothing: {fell}"

    # (ii) WITH THE ARGUMENTS A REAL RUN SENDS, each of the eight is still
    # decided by the operation and not by the gate. That they are SERVED is
    # the next test, which dispatches a run for real: this grant is minted
    # directly, so `respond` answers an execution identity check of its own
    # before it ever reaches the exchange.
    served = {}
    for op, args in _exchange_calls(ex["turn"], _anchored(w, ex["turn"])):
        status, got = _at_door(w, token, op, args)
        served[op] = (status, str(got.get("error") or "")[:200])
        assert FELL_THROUGH not in served[op][1], (op, served[op])
        assert "collection scope" not in served[op][1], (op, served[op])

    # (iii) THE TAIL IS STILL THERE for what the table does not admit, and the
    # new branches NARROW: a record of another Conversation, or an anchor that
    # cannot be read at all, is refused by the gate exactly as before.
    outside = elsewhere(w)
    for op, args in (("record_discovered_work",
                      {"work": "x", "regarding": [outside["post"]]}),
                     ("respond", {"text": "x", "results": [outside["post"]]}),
                     ("respond", {"text": "x",
                                  "parts": [{"type": "turn",
                                             "ref": outside["post"]}]}),
                     ("react", {"anchor": _anchored(w, outside["post"]),
                                "token": "ack"}),
                     ("react", {"anchor": "anc-nothing", "token": "ack"}),
                     ("anchor", {"version": outside["post"],
                                 "type": "version"})):
        status, got = _at_door(w, token, op, args)
        assert status == 403, (op, status, got)
        assert "collection scope" in refused(got), (op, got)
    for not_admitted in ("find", "recall", "delegate", "brief"):
        status, got = _at_door(w, token, not_admitted, {})
        assert status == 403, (not_admitted, status, got)


def test_a_real_dispatched_magnet_run_can_answer_and_ask_the_owner(magnet,
                                                                   monkeypatch):
    """SERVED, not merely reached: a real dispatched Magnet-scoped run, calling
    the door from inside itself under the grant dispatch minted for it.

    This is the half that cannot be faked by a table. The owner requires that
    a Magnet's agent can answer them, ask them, keep what it found and hand
    back a file; each of those was 403 before this correction, and the loss was
    invisible from outside because dispatch's completion fallback still posted
    a reply -- an answer that had lost `respond`'s rendering check and its
    decision form.
    """
    import time
    import mentis.web as web
    from mentis.execution import RunResult
    from mentis.web import dispatch as D
    w = magnet
    svc = w.state.agents
    seen = {}

    def ask(grant, op, **args):
        """The door's own entry points, in process: the HTTP route admits the
        token and then calls exactly these (`worker._api`)."""
        from mentis import worker
        from mentis.web import _surface
        surface = _surface(w.state)
        try:
            if op == "resolve":
                return 200, worker._result(surface, op, args, grant=grant,
                                           participant=grant.get("participant"))
            return 200, worker._operate(surface, op, args, grant)
        except worker.NotPermitted as exc:
            return 403, {"error": str(exc)}
        except Exception as exc:                              # noqa: BLE001
            return 500, {"error": f"{type(exc).__name__}: {exc}"}

    def perform(spec):
        grant = svc.authority.grant_for(svc.authority.grant_of(spec.run_id),
                                        w.state.path)
        seen["scope"] = grant["scope"]
        seen["read own batch"] = ask(grant, "read_artifact",
                                     ref=w.batch["ref"])
        turn = w.cv.asked_on(w.cv._act(grant["expectation"]))
        for op, args in _exchange_calls(turn, _anchored(w, turn)):
            seen[op] = ask(grant, op, **args)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         text="answered", stop_reason="end_turn",
                         started_at=now, finished_at=now,
                         timing={"prompt_sent": 1.0})

    for backend in svc.execution.backends():
        svc.execution.script = {**(svc.execution.script or {}),
                                backend["id"]: perform}
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: D.dispatch(w.state, **kw))
    ex = exchange(w)

    assert seen.get("scope") == "magnet:" + MAGNET, seen
    assert seen["read own batch"][0] == 200, seen["read own batch"]
    for op, _ in _exchange_calls(ex["turn"], "anc-x"):
        status, got = seen[op]
        words = str(got.get("error") or "")
        assert FELL_THROUGH not in words, (op, status, words[:200])
        assert "collection scope" not in words, (op, status, words[:200])
    # SERVED, for the ones whose own arguments are complete here. `request_
    # input` and `answer` name a block this exchange has none of, so they
    # answer for that reason -- which the loop above has already distinguished
    # from the gate answering for them.
    for op in ("respond", "record_discovered_work", "return_artifact",
               "request_decision", "anchor", "react"):
        assert seen[op][0] == 200, (op, seen[op])


def test_the_disclosure_no_longer_claims_the_boundary_is_missing():
    """The published disclosure is read by the client beside an answer. While
    the gate was shut it said grounded answers were blocked; saying that now
    would be false, and saying nothing about the boundary would be worse."""
    from mentis.magnet import perspectives

    words = perspectives.DISCLOSURE
    assert "blocked" not in words and "until" not in words
    assert "collection" in words and "refused at the door" in words
    assert "no authorization widens them" in words
