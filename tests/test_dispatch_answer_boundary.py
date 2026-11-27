"""Which characters of a fallback reply the run wrote, and which Mentis added.

A run that does not answer deliberately has its exit text written as the one
text part of a reply Turn, and where it made an outcome claim Mentis appends a
one-line rendering of that claim to it ("Claim by @X: ..."). The trailer is not
the answer and is not the run's words, but nothing on the record said where it
began, so a surface drawing the answer had to recognise its wording.

`said_span` and `appended` say it exactly. The agent's own narration before its
answer is NOT delimited here: only a deliberate answer draws that line, and a
run that used one never reaches this fallback.

WHERE IT IS READ. Recording the boundary is half of it: the surface that draws
an answer reads the FROZEN one, so `perspectives_work.finalize` carries both
fields into the answer package it freezes and onto its `answered` event
(independent review F1, `ent-c0eebf657ffb`). That half is checked in
`tests/test_magnet_perspectives.py::test_finalize_carries_the_reply_boundary_into_the_frozen_answer`,
and the client's use of the offsets in
`apps/fluid-web/tests/quiet_magnet_presentation_unit.ts`.
"""
import pytest

from mentis.operational import completion as C
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_dispatch_answer_ownership import _dispatch
from tests.test_headless_dispatch import synchronous  # noqa: F401


def _said(cv, exp):
    """The fallback reply Turn's `turn-said` act and its one text part."""
    act = next(a for a in cv.history(caused_by=exp) if a["act"] == "turn-said")
    turn = cv.corpus.read([act["turn"]])[0]
    parts = turn["body"]["parts"]
    assert len(parts) == 1 and parts[0]["type"] == "text"
    return act, parts[0]["text"]


ANSWER = "The collection's strongest theme is how observations become useful."


def test_the_span_mentis_appended_is_recorded_exactly(synchronous, monkeypatch):
    reported = (ANSWER + "\n```outcome\nresult: met\nsummary: answered it\n```")
    held, exp, start, end = _dispatch(synchronous, monkeypatch, reported=reported)
    cv = synchronous["cv"]
    act, whole = _said(cv, exp)
    d = act["detail"]

    # The reply does carry both: the run's answer and Mentis's trailer.
    assert ANSWER in whole and "Claim by" in whole

    # And the boundary between them is exact, not recognised by wording.
    span, appended = d["said_span"], d["appended"]
    assert span == {"part": 0, "start": 0, "end": appended[0]["start"]}
    assert appended[0]["part"] == 0 and appended[0]["what"] == "outcome-claim"
    assert appended[0]["end"] == len(whole)

    # Reading the recorded span gives the run's own words and nothing of
    # Mentis's -- which is the whole point of recording it.
    assert whole[span["start"]:span["end"]] == ANSWER
    assert "Claim by" not in whole[span["start"]:span["end"]]
    assert "Claim by" in whole[appended[0]["start"]:appended[0]["end"]]


def test_no_claim_means_nothing_was_appended_and_no_span_is_claimed(
        synchronous, monkeypatch):
    # Mentis added nothing, so it asserts no boundary. A reader sees the whole
    # text is the run's, because no `appended` says otherwise.
    held, exp, start, end = _dispatch(synchronous, monkeypatch, reported=ANSWER)
    cv = synchronous["cv"]
    act, whole = _said(cv, exp)
    assert whole == ANSWER
    assert "said_span" not in act["detail"] and "appended" not in act["detail"]
    # the fields the answer-ownership contract already promised are untouched
    assert act["detail"]["answers_request"] == exp


def test_a_reply_that_is_only_a_claim_puts_the_boundary_at_the_start(
        synchronous, monkeypatch):
    # The run reported nothing but its claim block, so Mentis's rendering is
    # the entire text and the run's own span is empty -- said, not guessed.
    reported = "```outcome\nresult: met\nsummary: said only this\n```"
    held, exp, start, end = _dispatch(synchronous, monkeypatch, reported=reported)
    cv = synchronous["cv"]
    act, whole = _said(cv, exp)
    span, appended = act["detail"]["said_span"], act["detail"]["appended"]
    assert span["end"] == 0 and appended[0]["start"] == 0
    assert whole[span["start"]:span["end"]] == ""
    assert appended[0]["end"] == len(whole) and whole.startswith("Claim by")


def test_a_deliberate_answer_records_no_boundary_and_writes_no_fallback(
        synchronous, monkeypatch):
    # The deliberate path owns the answer, so this boundary writes no Turn at
    # all and claims nothing about one.
    reported = "exit text\n```outcome\nresult: met\nsummary: exit claim\n```"
    held, exp, start, end = _dispatch(synchronous, monkeypatch,
                                      reported=reported, deliberate=True)
    cv = synchronous["cv"]
    acts = [a for a in cv.history(caused_by=exp) if a["act"] == "turn-said"]
    # only the deliberate answer's own act, which this boundary did not write
    assert [a["turn"] for a in acts] == [held["reply"]]
    assert "said_span" not in (acts[0]["detail"] or {})
    assert end["detail"]["response_owner"] == "respond"
