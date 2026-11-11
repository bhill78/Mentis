"""Unterminated or malformed outcome blocks (owner decision 9, 2026-11-11).

A valid final outcome block may report met, partly or not-met. An unterminated
or malformed one is NOT a claim: the agent's reply is kept exactly as written,
the outcome is reported unclaimed with why (on the act that ends the run, in the
work's state label and stage words), a normal runtime exit never implies one, and
nothing is repaired into a claim. Runtimes deliver replies differently -- ACP
`agent_message_chunk` streams (claude, codex, kimi), agy's text deltas or one
final message as MARS translates them, the local worker's whole messages -- so
each shape is assembled by the real client (`MarsExecution._session_update`) and
the assembled text is sent through the real dispatch.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from mentis.execution import RunResult, RunSpec
from mentis.operational import completion as C
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_completion_reconcile import _met, _status, _work, synchronous  # noqa: F401

VALID = "Did it.\n\n```outcome\nresult: met\nsummary: did it\nevidence:\n- tests 3 passed\n```\n"

MALFORMED = {
    "unterminated": "Did it.\n\n```outcome\nresult: met\nsummary: did it\n",
    "no-result": "Did it.\n\n```outcome\nsummary: did it\n```\n",
    "bad-result": "Did it.\n\n```outcome\nresult: probably\nsummary: did it\n```\n",
    "template-result": "Did it.\n\n```outcome\nresult: met | partly | not-met\n```\n",
    "two-results": "Did it.\n\n```outcome\nresult: met\nresult: not-met\n```\n",
    "not-last": "```outcome\nresult: met\nsummary: did it\n```\n\nOne more thing: tests fail.",
    "quoted-only": "Done.\n\n````markdown\n```outcome\nresult: met\n```\n````\n",
    "quote-line": "Done.\n\n> ```outcome\n> result: met\n> ```\n",
    # an outcome fence inside another code block: closed by the outer one's close
    "inside-code": "Done.\n\n```text\nlog\n```outcome\nresult: met\n```\n",
    "outer-unterminated": "Done.\n\n```text\nlog\n```outcome\nresult: met\n",
}
KIND = {"template-result": "bad-result", "quote-line": "quoted-only",
        "inside-code": "quoted-only",
        "outer-unterminated": "unterminated"}


# -- the parsing, case by case ------------------------------------------------------

@pytest.mark.parametrize("result", ["met", "partly", "not-met"])
def test_a_valid_final_block_is_a_claim_of_any_result(result):
    got = C.inspect(f"Text.\n```outcome\nresult: {result}\nsummary: s\n```")
    assert got["claim"]["result"] == result and got["unclaimed"] is None
    assert got["text"] == "Text."


@pytest.mark.parametrize("case", list(MALFORMED))
def test_a_malformed_block_is_unclaimed_kept_as_written_and_explained(case):
    text = MALFORMED[case]
    got = C.inspect(text)
    assert got["claim"] is None
    assert got["text"] == text                     # never cut, never repaired
    assert got["unclaimed"]["kind"] == KIND.get(case, case)
    assert got["unclaimed"]["why"].startswith(C.UNCLAIMED_WHY[got["unclaimed"]["kind"]])
    assert C.extract(text) == (None, text)


def test_no_block_at_all_claims_nothing_and_needs_no_explanation():
    got = C.inspect("All done, tests pass.")
    assert got == {"claim": None, "text": "All done, tests pass.", "unclaimed": None}


def test_of_two_blocks_the_one_ending_the_reply_is_the_claim():
    text = ("```outcome\nresult: met\n```\n\nOn reflection:\n\n"
            "```outcome\nresult: partly\nsummary: half\n```")
    got = C.inspect(text)
    assert got["claim"]["result"] == "partly"
    assert "result: met" in got["text"]          # the earlier one stays as text


def test_a_valid_block_then_an_unterminated_one_is_unclaimed():
    text = ("```outcome\nresult: met\n```\n\nWait:\n```outcome\nresult: not-met\n")
    got = C.inspect(text)
    assert got["claim"] is None and got["unclaimed"]["kind"] == "unterminated"


def test_the_same_result_said_twice_is_one_claim():
    got = C.inspect("```outcome\nresult: met\nresult: done\n```")
    assert got["claim"]["result"] == "met"


# -- through the real dispatch: a worker-scope run's final reply ------------------------

def _answering(text):
    def answer(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text=text, started_at=now,
                         finished_at=now)
    return answer


def _dispatch(world, text, runtime="codex"):
    st, cv = world["state"], world["cv"]
    st.agents.execution.script = {runtime: _answering(text)}
    ada = cv.create_participant(f"@Ada{len(cv.corpus.operational())}", about="an agent")
    cid = a_conversation(world)
    out = say(world, cid, "please do it", action="ask-participant",
              dispatch=[{"participant": ada, "work": "do it", "runtime": runtime}])
    exp = out["expectations"][0]
    start = [a for a in cv.history(caused_by=exp) if a["act"] == "execution-started"][-1]
    return exp, start, cv.run_end(start["id"])


def _reply_text(cv, end):
    reply = cv.corpus.read([end["turn"]])[0]
    return " ".join(p.get("text") or "" for p in reply["body"]["parts"])


def _overview_item(world, exp):
    from mentis.operational.work_overview import overview
    return next(i for i in overview(cv=world["cv"], viewer=world["who"]["@brian"],
                                    runtime=None)["items"] if i["expectation"] == exp)


@pytest.mark.parametrize("case", list(MALFORMED))
def test_a_run_ending_with_a_malformed_block_is_reported_unclaimed(synchronous, case):
    world = synchronous
    cv = world["cv"]
    exp, start, end = _dispatch(world, MALFORMED[case])
    assert end["act"] == "result-returned"
    assert not C.claims_of(cv, exp) and not _met(cv, exp)
    assert _reply_text(cv, end) == MALFORMED[case].strip() or \
        _reply_text(cv, end) == MALFORMED[case]          # the reply as written
    unc = end["detail"]["outcome_unclaimed"]
    assert unc["kind"] == KIND.get(case, case) and unc["why"]
    state = _status(cv, exp)
    assert state["value"] == "returned"
    # an outcome fence only QUOTED (documentation, an example) is no attempt at a claim:
    # plain "no outcome claimed", the reason still in `why` (round-3 final review)
    words = ("Ended · no outcome claimed" if unc["kind"] == "quoted-only"
             else "Ended · no outcome claimed · outcome block not valid")
    assert state["label"] == words
    assert unc["why"] in state["why"] and state["outcome_unclaimed"] == unc
    item = _overview_item(world, exp)
    assert item["status_words"] == state["label"]
    assert item["stage_words"] == words
    assert item["claim"] is None and item["objective_met"] is False


def test_a_normal_exit_with_no_block_is_unclaimed_and_never_inferred(synchronous):
    world = synchronous
    cv = world["cv"]
    exp, start, end = _dispatch(world, "All done; the tests pass.")
    assert end["act"] == "result-returned" and end["detail"]["terminal"] == "reported_done"
    assert "outcome_unclaimed" not in end["detail"]
    assert not C.claims_of(cv, exp) and not _met(cv, exp)
    assert _status(cv, exp)["label"] == "Ended · no outcome claimed"


def test_a_valid_block_is_still_claimed_through_dispatch(synchronous):
    world = synchronous
    cv = world["cv"]
    exp, start, end = _dispatch(world, VALID)
    assert "outcome_unclaimed" not in end["detail"]
    claims = C.claims_of(cv, exp)
    assert len(claims) == 1 and claims[0]["detail"]["result"] == "met"


# -- respond: the reply is posted as written and the caller told why ----------------

def test_respond_with_a_malformed_block_posts_it_as_written_and_says_why(synchronous):
    from mentis.web import _surface
    from mentis.worker import _operate
    world = synchronous
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    grant = {"participant": who, "expectation": exp, "conversation": cid,
             "instance": "inst-m", "runtime": "codex", "scope": "intake",
             "organising": ["respond"]}
    text = MALFORMED["unterminated"]
    out = _operate(_surface(world["state"]), "respond", {"text": text}, grant)
    assert "claim" not in out and out["outcome_unclaimed"]["kind"] == "unterminated"
    assert "claims no outcome" in out["note"]
    said = cv.corpus.read([out["turn"]])[0]["body"]["parts"][-1]["text"]
    assert said.strip() == text.strip()               # as written (trailing space aside)
    act = cv._act(out["said_act"])
    assert act["detail"]["outcome_unclaimed"]["kind"] == "unterminated"
    assert not C.claims_of(cv, exp) and not _met(cv, exp)


def test_a_run_that_answered_through_respond_carries_its_reason_to_the_end(synchronous):
    """A run responds with a malformed block and exits saying nothing more: the act
    that ends it says why nothing was claimed. (`respond` is an organising operation:
    the run's own grant is used with it added, as an intake carrier's grant has it.)"""
    from mentis.web import _surface
    from mentis.worker import _operate
    world = synchronous
    st, cv = world["state"], world["cv"]
    answered = {}

    def answer(spec):
        grant = dict(st.agents.authority.grant_for(st.agents.authority.grant_of(spec.run_id),
                                                   st.path))
        grant["organising"] = list(grant.get("organising") or []) + ["respond"]
        answered.update(_operate(_surface(st), "respond",
                                 {"text": MALFORMED["bad-result"]}, grant))
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="", started_at=now, finished_at=now)
    st.agents.execution.script = {"codex": answer}
    cid = a_conversation(world)
    out = say(world, cid, "do it", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "do it",
                         "runtime": "codex"}])
    exp = out["expectations"][0]
    start = [a for a in cv.history(caused_by=exp) if a["act"] == "execution-started"][-1]
    end = cv.run_end(start["id"])
    assert end["act"] == "result-returned", end.get("because")
    assert answered["outcome_unclaimed"]["kind"] == "bad-result", answered
    assert end["detail"]["response_owner"] == "respond"
    assert end["detail"]["outcome_unclaimed"]["kind"] == "bad-result"
    assert not C.claims_of(cv, exp) and not _met(cv, exp)
    assert _status(cv, exp)["label"].endswith("outcome block not valid")


# -- each runtime's reply shape, assembled by the real client --------------------------

def _chunks_claude(text):
    """ACP stream, small deltas that split the fence markers themselves."""
    return [text[i:i + 3] for i in range(0, len(text), 3)]


def _chunks_codex(text):
    """ACP stream, a delta per line."""
    return text.splitlines(keepends=True)


def _chunks_agy_deltas(text):
    """MARS's agy translation: one agent_message_chunk per `text_delta`."""
    return [text[i:i + 40] for i in range(0, len(text), 40)]


def _chunks_agy_final(text):
    """MARS's agy translation when agy streamed no text: one final chunk."""
    return [text]


def _chunks_local(text):
    """The local worker: whole messages (a MessageEvent, then the finish message)."""
    head, sep, tail = text.partition("\n\n")
    return [head + sep, tail] if sep else [text]


SHAPES = {"claude": _chunks_claude, "codex": _chunks_codex, "kimi-k3": _chunks_claude,
          "antigravity-deltas": _chunks_agy_deltas, "antigravity-final": _chunks_agy_final,
          "local": _chunks_local}


def _assembled(chunks) -> str:
    """The text `MarsExecution` assembles from MARS's session/update notifications."""
    from acp.schema import SessionNotification

    from mentis.execution.mars import MarsExecution, _RunState
    ex = MarsExecution(["mars-not-started", "stdio"])
    spec = RunSpec(run_id="r-shape", backend="x", prompt="p", workspace=".")
    state = _RunState(spec=spec, result=RunResult(run_id="r-shape", backend="x", started=True),
                      on_event=None)
    ex._states["s-shape"] = state

    async def feed():
        for c in chunks:
            n = SessionNotification.model_validate({
                "sessionId": "s-shape",
                "update": {"sessionUpdate": "agent_message_chunk",
                           "content": {"type": "text", "text": c}}})
            await ex._session_update("s-shape", n.update)
    asyncio.run(feed())
    return state.result.text


@pytest.mark.parametrize("shape", list(SHAPES))
@pytest.mark.parametrize("case", ["unterminated", "bad-result", "not-last", "valid"])
def test_every_runtime_reply_shape_is_read_the_same(synchronous, shape, case):
    text = VALID if case == "valid" else MALFORMED[case]
    assembled = _assembled(SHAPES[shape](text))
    assert assembled == text
    world = synchronous
    cv = world["cv"]
    exp, start, end = _dispatch(world, assembled)
    if case == "valid":
        assert C.claims_of(cv, exp) and "outcome_unclaimed" not in end["detail"]
    else:
        assert not C.claims_of(cv, exp) and not _met(cv, exp)
        assert end["detail"]["outcome_unclaimed"]["kind"] == case
        assert _reply_text(cv, end) in (text, text.strip())


def test_a_valid_claim_through_respond_is_not_flagged_by_the_exit_text(synchronous):
    """Round-3 final review: the answer `respond` gave is the run's word on its outcome. A
    run that claims met through `respond` and then exits with a malformed block is not
    flagged 'outcome block not valid'."""
    from mentis.web import _surface
    from mentis.worker import _operate
    world = synchronous
    st, cv = world["state"], world["cv"]
    valid = "Done.\n\n```outcome\nresult: met\nsummary: did it\n```"

    def answer(spec):
        grant = dict(st.agents.authority.grant_for(st.agents.authority.grant_of(spec.run_id),
                                                   st.path))
        grant["organising"] = list(grant.get("organising") or []) + ["respond"]
        _operate(_surface(st), "respond", {"text": valid}, grant)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text=MALFORMED["unterminated"],
                         started_at=now, finished_at=now)
    st.agents.execution.script = {"codex": answer}
    cid = a_conversation(world)
    out = say(world, cid, "do it", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "do it",
                         "runtime": "codex"}])
    exp = out["expectations"][0]
    start = [a for a in cv.history(caused_by=exp) if a["act"] == "execution-started"][-1]
    end = cv.run_end(start["id"])
    assert not (end.get("detail") or {}).get("outcome_unclaimed"), end.get("detail")
    assert C.claims_of(cv, exp), "the respond claim stands"
