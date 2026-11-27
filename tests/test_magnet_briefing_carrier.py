"""The Summary briefing's actual send, end to end over fixture records.

What these check is the seam the authority/evidence review `ent-5acd177f3aa8`
found broken: the request the CLIENT actually composes for a frozen Perspective
ask (`apps/fluid-web/src/quiet2/magnets/perspectives.ts::perspectiveRequest`)
could not cross the one managed request door at all. It carried a generated
`dispatch[].work` override, which `mentis.fluid.message_context.gate` refuses
outright with `invalid-managed-intent` before any record or dispatch exists, so
the whole promised briefing flow returned 422 (review F2).

So the shape composed here is the corrected client's own shape, not a shape
invented for the test: the frozen question first (`bind` requires the asking
Turn to BEGIN with it), then what the run is told, as the message's own words;
one text part that is the exact projection of those words; every immutable
input as a real file part; and a dispatch spec carrying only `reach: "work"`
and `requires`. It is sent through the real door, bound, dispatched with
`FakeExecution`, finalized, and then asked for the FRESH DISPLAY RECEIPT the
Summary now obtains before it shows a frozen answer's words (review F4) --
because a display requirement that can never be satisfied would be no fix.

No MARS, model, live Brain or deployment is involved: fixture Brains and
`FakeExecution` only, exactly as `tests/test_magnet_perspectives.py` does.
"""
import uuid

import pytest

from mentis.fluid import commands
from mentis.fluid.inspect import brain_key
from mentis.magnet import perspectives as P
from tests.test_magnet_activation import world, built, MAGNET  # noqa: F401
from tests.test_magnet_perspectives import (  # noqa: F401
    inquiry, prepare, live, answer, cmd, qualify,
)

# What the client tells the run, in the message rather than as an override.
# The client's own wording is pinned by the UI test
# (`apps/fluid-web/tests/quiet_magnet_briefing_unit.ts`); what matters to this
# door is the shape: the frozen question, then more words.
INSTRUCTION = ("Use the attached frozen Perspective records, manifest and evidence. "
               "Read them with read_artifact. Reconstruct the inquiry by its Topic "
               "{perspective}, distinguish original support from interpretations and "
               "conflicting evidence, cite the exact versions/ranges, and answer the "
               "frozen question.")


def recipient(w):
    """Whoever the owner chooses to answer; created before anything is counted."""
    return w.cv.create_participant("@Briefing" + uuid.uuid4().hex[:6])


def carrier(w, prepared, agent, *, work=None, instruction=INSTRUCTION):
    """The request the corrected client composes, through the real door.

    `written_by` is what the server observes for a request presenting no grant,
    which is what `bind` requires of the owner's own asking Turn
    (`artifacts._written_by_execution`).
    """
    words = prepared["text"] + "\n\n" + instruction.format(perspective=prepared["perspective"])
    spec = {"participant": agent, "runtime": "codex", "reach": "work",
            "requires": ["call_mentis_tools"]}
    if work is not None:
        spec["work"] = work
    body = {"from": {"magnet": MAGNET}, "author": w.by,
            "text": words,
            "parts": [{"type": "text", "text": words}, *prepared["parts"]],
            "op": prepared["request_op"], "action": "ask-participant",
            "addressed_to": [agent], "topics": [prepared["perspective"]],
            "dispatch": [spec]}
    status, out, _ = commands.agent_request(
        w.state, body, written_by=lambda: "unattributed-local-request",
        brain=brain_key(w.corpus))
    return status, out, words


def test_the_client_carrier_crosses_the_one_door_and_becomes_a_frozen_answer(inquiry):
    w = inquiry
    p = prepare(w)
    agent = recipient(w)
    status, out, words = carrier(w, p, agent)
    assert status == 200, out
    assert words.startswith(p["text"]) and len(words) > len(p["text"])
    req = out["expectations"][0]
    # BOUND: the actual asking Turn, its original operation key, the frozen
    # question as its opening words and every immutable input as a real part.
    cmd(w, "bind", p["perspective"], intent=p["intent"], request=req)
    from mentis.web import dispatch as D
    result = D.dispatch(w.state, **w.sent[-1])
    assert result["ok"], result
    check = qualify(w, p)
    assert check["status"] == "qualified", check
    assert w.corpus.deliveries(participant=agent)
    frozen = cmd(w, "finalize", p["perspective"], intent=p["intent"],
                 execution=result["instance"], answer=result["reply"])
    assert frozen["answer"] and frozen["receipt"]["status"] == "qualified"
    event = frozen["event"]["data"]
    # WHAT THE SUMMARY READS THE ANSWER THROUGH: the frozen question it was
    # written for, the run that produced it, and the immutable package.
    assert event["intent"] == p["intent"]
    assert event["execution"] == result["instance"]
    assert event["manifest"] == p["manifest"]
    assert event["answer"]["ref"] and event["answer"]["digest"]
    # AND THE FRESH DISPLAY RECEIPT IT NOW TAKES BEFORE SHOWING THE WORDS.
    shown = cmd(w, "reconcile", p["perspective"], intent=p["intent"],
                purpose="display", execution=result["instance"])
    assert shown["status"] == "qualified", shown
    assert shown["declared_context"] == [], "a display declares nothing of its own"


def test_the_frozen_manifest_names_the_collection_the_answer_was_written_from(inquiry):
    """The Summary reads the answer's own collection out of this manifest.

    `finalize` records no collection on the answer event, which is how a
    briefing written from an earlier collection was shown as "rewritten from
    the collection shown" (review F6). The manifest is where it is recorded.
    """
    w = inquiry
    p = prepare(w)
    from mentis.magnet import perspectives_evidence as E
    from mentis.spine import held
    manifest = E.native(w.state, MAGNET, p["manifest"]["ref"],
                        held.read(w.root, p["manifest"]["digest"]), "manifest")
    assert [b["ref"] for b in manifest["batches"]] == [w.batch["ref"]]


def test_a_generated_work_override_is_still_refused_without_any_record(inquiry):
    """The refusal this correction stopped colliding with stays exactly as it is.

    Nothing here narrows the gate: a dispatch spec carrying `work` is still
    `invalid-managed-intent`, with no domain record and nothing dispatched.
    """
    w = inquiry
    p = prepare(w)
    agent = recipient(w)
    before = w.corpus.advance()
    status, out, _words = carrier(
        w, p, agent, work="Use the attached frozen Perspective records.")
    assert status == 422, out
    assert out["code"] == "invalid-managed-intent", out
    assert w.corpus.advance() == before
    assert w.sent == []


@pytest.mark.parametrize("instruction", ["", "   "])
def test_the_frozen_question_alone_still_binds(inquiry, instruction):
    """The guidance is additional words, never a condition of the send.

    `bind` requires the Turn to begin with the frozen question; a carrier that
    adds nothing after it is still exactly that Turn.
    """
    w = inquiry
    p = prepare(w)
    status, out, words = carrier(w, p, recipient(w), instruction=instruction)
    assert status == 200, out
    assert words.startswith(p["text"])
    cmd(w, "bind", p["perspective"], intent=p["intent"], request=out["expectations"][0])
    assert P.home(w.state, MAGNET)
