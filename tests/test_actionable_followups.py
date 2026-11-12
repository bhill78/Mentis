"""Record-shaped approval, continuation and detached reporting regressions."""
from __future__ import annotations

from mentis.operational import completion
from mentis.web import _surface
from mentis.worker import _operate
from tests._loop import _coordinator, a_conversation, world  # noqa: F401
from tests.test_decision_resume_parent import _answer, _form_of


def operate(world, grant, name, **args):
    return _operate(_surface(world["state"]), name, args, grant)


def test_approval_claim_keeps_request_pending_and_answer_resumes_named_artifact(world):
    cid = a_conversation(world)
    coach, parent, grant = _coordinator(world, cid)
    out = operate(world, grant, "respond", text="Candidate 4037e33 is ready.",
                  outcome={"result": "met", "approval": {"artifacts": ["commit 4037e33", "adm-review"]}})
    form = _form_of(world["cv"], parent)
    assert form["post"] == out["turn"]
    assert "4037e33" in form["questions"][0]["question"]
    assert out["reconciled"]["recorded"] == "pending"
    assert not world["cv"].expectation_state(parent)["satisfied_by"]
    _answer(world, form, "Approve")
    resumed = [x for x in world["sent"] if x["expectation"] == parent]
    assert len(resumed) == 1
    assert resumed[0]["participant"] == coach
    assert "4037e33" in resumed[0]["work"] and out["turn"] in resumed[0]["work"]


def test_final_block_approval_uses_same_decision_path(world):
    cid = a_conversation(world)
    coach, parent, _ = _coordinator(world, cid)
    turn = world["cv"].say(cid, coach, [{"type": "text", "text": "design"}])
    outcome, _ = completion.extract("Ready\n\n```outcome\nresult: met\napproval: commit abc123\n```" )
    claim = completion.claim(world["cv"], parent, outcome, actor=coach,
                             via="final-reply", reply_turn=turn)
    assert completion.reconcile(world["cv"], parent, claim)["recorded"] == "pending"
    assert "abc123" in _form_of(world["cv"], parent)["questions"][0]["question"]
