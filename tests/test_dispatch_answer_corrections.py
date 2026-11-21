"""F1/F2: real dispatched respond, collector outcome and decision placement.

No synthetic answer provenance or injected WorkOutcome: the service produces
the outcome from RunResult, and worker operations use dispatch's actual grant.
"""
import json

import pytest

from mentis.execution import RunResult
from mentis.operational import completion as C
from mentis.web import _surface
from mentis.worker import _operate
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.decision_descriptors import question
from tests.test_completion_reconcile import _met, _status, synchronous  # noqa: F401
from tests.test_outcome_malformed import _overview_item


VALID_EXIT = "All finished.\n\n```outcome\nresult: met\nsummary: exit claim\n```\n"


def _run(world, *, answer_kind="nonclaiming", exit_text=VALID_EXIT,
         terminal="end_turn", decisions=False):
    st, cv = world["state"], world["cv"]
    kept = {}

    def answer(spec):
        grant = st.agents.authority.grant_for(
            st.agents.authority.grant_of(spec.run_id), st.path)
        kept["grant"] = dict(grant)
        surface = _surface(st)

        def decision(words, **args):
            return _operate(surface, "request_decision", question(words, **args), grant)

        if decisions:
            kept["before"] = decision("Build the chart?")
        if answer_kind is not None:
            args = {"text": "Here is the answer."}
            if answer_kind == "claimed":
                args["outcome"] = {"result": "partly" if decisions else "met",
                                   "summary": "accepted answer"}
            elif answer_kind == "malformed":
                args["text"] += "\n```outcome\nresult: invalid\n```"
            kept["answer"] = _operate(surface, "respond", args, grant)
        if decisions:
            kept["after"] = decision("Build the legend?")
            # A later question explicitly placed elsewhere must never move.
            kept["placed"] = decision("Build the key?", on=cv._act(grant["expectation"])["turn"])
            kept["before_exit"] = {
                name: cv.decision_form(kept[name]["form"])["post"]
                for name in ("before", "after", "placed")}
        if terminal == "exception":
            raise RuntimeError("perform raised after answer and decision")
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason=terminal, text=exit_text)

    st.agents.execution.script = {"codex": answer}
    cid = a_conversation(world)
    out = say(world, cid, "do it", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "do it",
                         "runtime": "codex", "coordinate": True}])
    exp = out["expectations"][0]
    start = next(a for a in cv.history(caused_by=exp) if a["act"] == "execution-started")
    end = cv.run_end(start["id"])
    if answer_kind is not None:
        assert "answer" in kept, end["because"]
    if decisions:
        assert "before_exit" in kept, end
    return exp, end, kept


@pytest.mark.parametrize("answer_kind", ["nonclaiming", "claimed", "malformed"])
@pytest.mark.parametrize("terminal", ["end_turn", "failed", "cancelled"])
def test_exit_claim_is_evidence_only_and_explicitly_unapplied(
        synchronous, answer_kind, terminal):
    cv = synchronous["cv"]
    exp, end, kept = _run(synchronous, answer_kind=answer_kind, terminal=terminal)
    d = end["detail"]
    assert end["act"] == ("result-returned" if terminal == "end_turn" else "delivery-failed")
    assert d["response_owner"] == "respond"
    diagnostic = d["exit_outcome_unapplied"]
    assert diagnostic["kind"] == "respond-owned"
    assert diagnostic["result"] == "met" and diagnostic["summary"] == "exit claim"
    assert diagnostic["reply_turn"] == kept["answer"]["turn"]
    assert "not applied" in diagnostic["why"] and "evidence" in diagnostic["why"]
    assert d["collected_text"] == VALID_EXIT
    claims = C.claims_of(cv, exp)
    assert len(claims) == (1 if answer_kind == "claimed" else 0)
    if claims:
        assert claims[0]["detail"]["summary"] == "accepted answer"
    if answer_kind == "malformed":
        assert d["outcome_unclaimed"]["kind"] == "bad-result"
    state = _status(cv, exp)
    item = _overview_item(synchronous, exp)
    if terminal == "end_turn" and answer_kind != "claimed":
        assert state["label"] == "Ended · exit outcome not applied"
        assert diagnostic["why"] in state["why"]
        assert item["status_words"] == item["stage_words"] == state["label"]
        assert state["exit_outcome_unapplied"] == diagnostic
    if terminal != "end_turn":
        assert not _met(cv, exp)
        assert state["value"] in ("failed", "claim-pending")
    else:
        assert bool(_met(cv, exp)) == (answer_kind == "claimed")


@pytest.mark.parametrize("exit_text", ["done", "", "```outcome\nresult: invalid\n```"])
def test_exit_without_valid_claim_does_not_invent_an_unapplied_claim(synchronous, exit_text):
    exp, end, _ = _run(synchronous, exit_text=exit_text)
    assert "exit_outcome_unapplied" not in end["detail"]
    assert not C.claims_of(synchronous["cv"], exp)
    assert _status(synchronous["cv"], exp)["label"] == "Ended · no outcome claimed"


def test_no_respond_still_records_aggregate_exit_claim(synchronous):
    exp, end, _ = _run(synchronous, answer_kind=None)
    assert len(C.claims_of(synchronous["cv"], exp)) == 1
    assert _met(synchronous["cv"], exp)
    assert "exit_outcome_unapplied" not in end["detail"]


@pytest.mark.parametrize("result", ["partly", "not-met"])
def test_conflicting_exit_outcome_never_replaces_accepted_claim(synchronous, result):
    exp, end, _ = _run(synchronous, answer_kind="claimed",
                       exit_text=VALID_EXIT.replace("result: met", "result: " + result))
    claims = C.claims_of(synchronous["cv"], exp)
    assert len(claims) == 1 and claims[0]["detail"]["result"] == "met"
    assert end["detail"]["exit_outcome_unapplied"]["result"] == result


def test_exit_approval_is_only_evidence_and_cannot_create_a_decision(synchronous):
    approval = {"mode": "create", "questions": [question("Build the chart?")]}
    exit_text = VALID_EXIT.replace("summary: exit claim", "approval: " + json.dumps(approval))
    exp, end, kept = _run(synchronous, answer_kind="claimed", exit_text=exit_text)
    assert end["detail"]["exit_outcome_unapplied"]["kind"] == "respond-owned"
    acts = synchronous["cv"].history(execution=kept["grant"]["instance"])
    assert not [a for a in acts if a["act"] in ("decision-asked", "decision-form-asked",
                                                "decision-form-attached")]
    assert len(C.claims_of(synchronous["cv"], exp)) == 1


@pytest.mark.parametrize("answer_kind", ["nonclaiming", "claimed"])
@pytest.mark.parametrize("terminal", ["end_turn", "failed", "exception"])
def test_later_decision_attaches_once_to_answer_without_moving_existing_forms(
        synchronous, answer_kind, terminal):
    cv = synchronous["cv"]
    exp, end, kept = _run(synchronous, answer_kind=answer_kind,
                          terminal=terminal, decisions=True)
    reply = kept["answer"]["turn"]
    assert kept["before_exit"] == {"before": reply, "after": None,
                                    "placed": cv._act(exp)["turn"]}
    for name in ("before", "after"):
        assert cv.decision_form(kept[name]["form"])["post"] == reply
    assert cv.decision_form(kept["placed"]["form"])["post"] == cv._act(exp)["turn"]
    assert set(cv.decision_forms_on(reply)) == {kept[n]["form"] for n in ("before", "after")}
    acts = cv.history(execution=kept["grant"]["instance"])
    assert len([a for a in acts if a["act"] == "turn-said"]) == 1
    assert len([a for a in acts if a["act"] == "decision-form-attached"]) == 2
    assert len(C.claims_of(cv, exp)) == (1 if answer_kind == "claimed" else 0)
    assert not _met(cv, exp)  # genuine pending decisions still require the owner
    assert not cv.attach_pending_forms(kept["grant"]["instance"], reply, by=kept["grant"]["participant"])
    assert end["detail"]["reply_turn"] == reply
    assert "pending_forms_unattached" not in end["detail"]


@pytest.mark.parametrize("terminal", ["end_turn", "failed", "exception"])
def test_exit_attachment_failure_rolls_back_and_keeps_pending_decision_visible(
        synchronous, monkeypatch, terminal):
    cv = synchronous["cv"]
    from mentis.conversation import Conversations
    original = Conversations.attach_pending_forms

    def attach_then_fail(self, execution, reply, **kw):
        made = original(self, execution, reply, **kw)
        # Worker attached the first form. Fail only the dispatch attachment
        # of the form asked after respond, after its actual append.
        if made and len(self.decision_forms_on(reply)) == 2:
            raise RuntimeError("injected exit attachment failure")
        return made

    monkeypatch.setattr(Conversations, "attach_pending_forms", attach_then_fail)
    exp, end, kept = _run(synchronous, terminal=terminal, decisions=True)
    reply = kept["answer"]["turn"]
    assert end["act"] == ("result-returned" if terminal == "end_turn" else "delivery-failed")
    assert cv.decision_form(kept["after"]["form"])["post"] is None
    assert cv.decision_form(kept["after"]["form"])["open"] == 1
    assert cv.decision_forms_on(reply) == [kept["before"]["form"]]
    diagnostic = end["detail"]["pending_forms_unattached"]
    assert diagnostic["reply_turn"] == reply
    assert "injected exit attachment failure" in diagnostic["why"]
    assert not C.claims_of(cv, exp) and not _met(cv, exp)
