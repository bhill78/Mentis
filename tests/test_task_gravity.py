"""Task Gravity values and ancestry, adapted to the headless build."""

import pytest

from mentis.operational import (ASK, UNRESTRICTED, discovery,
                                follow_up_label, follow_up_value)
from mentis.conversation import text
from tests.test_manual_session import world


@pytest.mark.parametrize("value,label", [
    (None, "Asks before pursuing side work"),
    ({"depth": 1}, "May pursue side work 1 generation deep"),
    ({"depth": 2}, "May pursue side work 2 generations deep"),
    (UNRESTRICTED, "May pursue side work freely"),
])
def test_gravity_values_have_the_contract_labels(value, label):
    assert follow_up_label(value) == label


@pytest.mark.parametrize("bad", ["always", {"depth": 0},
                                  {"depth": "2"}, {"depth": True}, 3])
def test_other_gravity_values_are_refused(bad):
    with pytest.raises(ValueError, match="follow_up is"):
        follow_up_value(bad)


def test_generation_is_computed_from_finding_lineage(world):
    cv = world["st"].cv
    actor = cv.find_participant("@ManualSession") or cv.create_participant(
        "@ManualSession")
    cid = cv.open_conversation("Gravity", attributed_to=world["owner"])
    turn = cv.say(cid, actor, [text("root")])
    root = cv.expect(turn, of=actor, kind="result", by=actor,
                     detail={"follow_up": {"depth": 2}})
    first_turn = cv.say(cid, actor, [text("first")])
    first = cv.expect(first_turn, of=None, kind="result", by=actor,
                      caused_by=root)
    cv.record_act(actor=actor, act="work-discovered", conversation=cid,
                  turn=first_turn, caused_by=root, about=[first])
    second_turn = cv.say(cid, actor, [text("second")])
    second = cv.expect(second_turn, of=None, kind="result", by=actor,
                       caused_by=first)
    cv.record_act(actor=actor, act="work-discovered", conversation=cid,
                  turn=second_turn, caused_by=first, about=[second])
    assert discovery(cv, root) == {"origin": root, "generation": 0}
    assert discovery(cv, first) == {"origin": root, "generation": 1}
    assert discovery(cv, second) == {"origin": root, "generation": 2}
    assert follow_up_value(None) == ASK
