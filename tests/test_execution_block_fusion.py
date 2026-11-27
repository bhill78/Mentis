"""Where one block of an agent's prose ends and the next begins.

`agent_message_chunk` carries both the token deltas of a block being streamed
and the start of a genuinely separate block, and only the second needs a
separator. Reply Turn ent-116c910c16c2 on TEST is what joining them blindly
produces: 5155 characters in which the agent's blocks meet with no character
between them ("...the exact retained sources.The collection combines...").

These drive `MarsExecution._session_update` itself, so they cover the real
accumulation and not a copy of it.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from mentis.execution import RunResult, RunSpec
from mentis.execution.mars import MarsExecution, _RunState


def _chunk(text: str, message: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(session_update="agent_message_chunk",
                           content=SimpleNamespace(type="text", text=text),
                           message_id=message)


def _tool(call_id: str = "c1", kind: str = "tool_call") -> SimpleNamespace:
    return SimpleNamespace(session_update=kind, tool_call_id=call_id,
                           title="Read", kind="read", status="pending",
                           locations=None, field_meta=None)


def _spec() -> RunSpec:
    return RunSpec(run_id="fusion", backend="claude", prompt="p", workspace=".")


def _said(updates: list[SimpleNamespace]) -> str:
    """The text one run accumulates from `updates`, through the real path."""
    mars = MarsExecution(["mars", "stdio"])
    state = _RunState(spec=_spec(),
                      result=RunResult(run_id="fusion", backend="claude", started=True),
                      on_event=None)
    mars._states["s"] = state

    async def drive() -> None:
        for update in updates:
            await mars._session_update("s", update)

    asyncio.run(drive())
    return state.result.text


# ---- the deltas of one streamed block are joined by nothing -----------------

def test_token_deltas_of_one_block_are_not_separated():
    # The shape that must not change: a model streams a word in pieces, and
    # they meet with no character between them because that is the word.
    assert _said([_chunk("Hel", "m1"), _chunk("lo", "m1"),
                  _chunk(" there", "m1")]) == "Hello there"


def test_deltas_with_no_message_id_and_no_tool_call_are_not_separated():
    # An agent that sends no messageId still streams deltas, and with no tool
    # call between them there is nothing to say a new block began.
    assert _said([_chunk("Hel"), _chunk("lo")]) == "Hello"


def test_prose_the_agent_spaced_itself_is_left_alone():
    # A block that ends with its own blank line is already separated: nothing
    # is added, so the agent's own spacing survives byte for byte.
    assert _said([_chunk("First.\n\n", "m1"), _chunk("Second.", "m2")]) \
        == "First.\n\nSecond."
    assert _said([_chunk("First.", "m1"), _chunk("\nSecond.", "m2")]) \
        == "First.\nSecond."


# ---- a genuinely new block is separated -------------------------------------

def test_a_new_message_starts_a_new_block():
    # The recorded symptom, in miniature: two messages whose text would
    # otherwise fuse at the sentence end.
    assert _said([_chunk("...the exact retained sources.", "m1"),
                  _chunk("The collection combines", "m2")]) \
        == "...the exact retained sources.\n\nThe collection combines"


def test_a_tool_call_starts_a_new_block_when_no_message_id_is_sent():
    # An agent that sends no messageId: the tool call it stopped to make is
    # what says the prose after it is a new block.
    assert _said([_chunk("I'll read the records."), _tool(),
                  _chunk("The collection combines")]) \
        == "I'll read the records.\n\nThe collection combines"


def test_an_update_to_a_call_already_made_does_not_break_a_block():
    # A `tool_call_update` can arrive while the agent is still writing, so it
    # must not be read as a block boundary: "Hel" + "lo" is still one word.
    assert _said([_chunk("Hel"), _tool(kind="tool_call_update"),
                  _chunk("lo")]) == "Hello"


def test_message_id_decides_when_the_agent_sends_one():
    # Where messageId is sent it is the whole answer, so a tool call inside
    # one message does not split that message's own prose.
    assert _said([_chunk("one sentence, ", "m1"), _tool(),
                  _chunk("continued", "m1")]) == "one sentence, continued"


def test_the_runs_first_text_is_never_prefixed():
    assert _said([_tool(), _chunk("First thing said.")]) == "First thing said."


# ---- the whole observed shape ----------------------------------------------

def test_the_recorded_reply_shape_is_separated_at_both_boundaries():
    # The reply had exactly two fusion points, each at a block boundary the
    # agent reached by stopping to call tools.
    text = _said([
        _chunk("I'll read the frozen question, then trace the briefing's "
               "claims to the exact retained sources.", "m1"),
        _tool("c1"),
        _chunk("The collection combines a few full NASA articles with many "
               "search-result rows.", "m2"),
        _tool("c2"),
        _chunk("The collection's strongest theme is how observations become "
               "more useful.", "m3"),
    ])
    assert text.count("\n\n") == 2
    assert "sources.\n\nThe collection combines" in text
    assert "rows.\n\nThe collection's strongest theme" in text
    # and nothing else moved
    assert not text.startswith("\n") and not text.endswith("\n")


def test_events_still_carry_each_chunk_as_sent():
    # The separator is in the accumulated text only. Each event still reports
    # exactly the characters that chunk carried, which readers of the live run
    # (the run feed) depend on.
    seen: list[str] = []
    mars = MarsExecution(["mars", "stdio"])
    state = _RunState(spec=_spec(),
                      result=RunResult(run_id="fusion", backend="claude", started=True),
                      on_event=lambda event: seen.append(event.data.get("text"))
                      if event.kind == "agent_message_chunk" else None,
                      on_permission=None)
    mars._states["s"] = state

    async def drive() -> None:
        for update in [_chunk("First.", "m1"), _chunk("Second.", "m2")]:
            await mars._session_update("s", update)

    asyncio.run(drive())
    assert seen == ["First.", "Second."]
    assert state.result.text == "First.\n\nSecond."
