"""A run's permission answers and consent changes move the run, not its
Conversation (mentis/web/moved.py RUN_ONLY_ACTS; profiling 2026-10-29).

They were placed in the Conversation, so every open view of it reread each time
an agent's operation was answered. The run panel still learns of them through
the run's execution; any other act in the Conversation still moves it."""

from __future__ import annotations

from mentis.web.moved import moved
from tests._loop import a_conversation, say, world  # noqa: F401


def _since(world):
    return "%d.%d.%d" % world["cv"].corpus.advance()


def test_permission_answers_and_consent_move_only_the_run(world):
    cv = world["cv"]
    cid = a_conversation(world, "Moves")
    turn = say(world, cid, "work")["turn"]
    since = _since(world)
    for act in ("operation-answered", "consent-set"):
        cv.record_act(actor=world["steward"], act=act, conversation=cid, turn=turn,
                      execution="inst-moves", caused_by=None, detail={"answer": "allowed"})
    got = moved(cv.corpus, since)
    assert got["conversations"] == [] and got["executions"] == ["inst-moves"]
    assert got["loose"] is False


def test_any_other_act_still_moves_its_conversation(world):
    cv = world["cv"]
    cid = a_conversation(world, "Moves 2")
    turn = say(world, cid, "work")["turn"]
    since = _since(world)
    cv.record_act(actor=world["steward"], act="decision-answered", conversation=cid,
                  turn=turn, execution="inst-moves", caused_by=None, detail={})
    got = moved(cv.corpus, since)
    assert cid in got["conversations"]


def test_a_run_act_with_no_execution_is_not_placed_anywhere_certain(world):
    cv = world["cv"]
    cid = a_conversation(world, "Moves 3")
    since = _since(world)
    cv.record_act(actor=world["steward"], act="consent-set", conversation=cid,
                  execution=None, caused_by=None, detail={})
    assert moved(cv.corpus, since)["loose"] is True
