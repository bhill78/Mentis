"""C1a dispatch contract, using fixture Brains and synthetic C1b provenance.

The C1b writer is separately owned. These fixtures append its agreed answer
contract, then exercise real dispatch end processing, grants and reconciliation.
They do not claim to test the worker's single-answer transaction.
"""
from dataclasses import replace

import pytest

from mentis import artifacts
from mentis.api.types import WorkOutcome
from mentis.authority import Authority
from mentis.conversation import text
from mentis.execution import RunResult
from mentis.operational import completion as C
from mentis.web import dispatch as D
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_headless_dispatch import synchronous  # noqa: F401


def _answer(cv, grant, *, claim=None, malformed=False, run=None):
    request = cv._act(grant["expectation"])["turn"]
    reply = cv.say(grant["conversation"], grant["participant"], [text("Useful answer")],
                   replies_to=request)
    diagnostic = {"kind": "bad-result", "why": "invalid deliberate claim"}
    cv.record_act(actor=grant["participant"], act="turn-said", turn=reply,
                  conversation=grant["conversation"], execution=grant["instance"],
                  caused_by=grant["expectation"],
                  detail={"answers_request": grant["expectation"],
                          "answers_turn": request, "run": run or grant["run"],
                          **({"outcome_unclaimed": diagnostic} if malformed else {})})
    if claim:
        C.claim(cv, grant["expectation"], claim, actor=grant["participant"],
                execution=grant["instance"], runtime=grant["runtime"], via="respond",
                reply_turn=reply, conversation=grant["conversation"])
    return reply


def _dispatch(world, monkeypatch, *, reported, terminal="reported_done",
              deliberate=False, claim=None, malformed=False, raises=False):
    st, cv = world["state"], world["cv"]
    cid = a_conversation(world)
    held = {}
    perform = st.agents.agents_perform

    def agent(spec):
        grant = st.agents.authority.grant_for(st.agents.authority.grant_of(spec.run_id), st.path)
        held["grant"] = dict(grant)
        if deliberate:
            held["reply"] = _answer(cv, grant, claim=claim, malformed=malformed)
        cv.record_act(actor=grant["participant"], act=artifacts.RETURNED,
                      execution=spec.run_id, caused_by=grant["expectation"],
                      about=["adm-partial-output"])
        if raises:
            raise RuntimeError("perform raised after useful answer")
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="placeholder")

    def outcome(*args, **kwargs):
        got = perform(*args, **kwargs)
        # Test the declared WorkOutcome boundary, including the empty string
        # that the upstream service currently normalizes to None.
        return replace(got, reported=reported, terminal=terminal,
                       error=None if terminal == "reported_done" else "specific failure Ω",
                       notes=("full diagnostic note",),
                       timed_out=terminal == "stopped_at_deadline", exit_code=0 if
                       terminal == "reported_done" else -1)

    monkeypatch.setattr(st.agents, "agents_perform", outcome)
    st.agents.execution.script = {"codex": agent}
    out = say(world, cid, "build it", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "build it",
                         "runtime": "codex", "coordinate": deliberate}])
    exp = out["expectations"][0]
    start = next(a for a in cv.history(caused_by=exp) if a["act"] == "execution-started")
    return held, exp, start, cv.run_end(start["id"])


EXITS = ["", "plain exit", "```outcome\nresult: met\nsummary: exit claim\n```",
         "```outcome\nresult: not-met\nsummary: conflicting exit\n```",
         "```outcome\nresult: partly\napproval: {bad: approval}\n```",
         "```outcome\nresult: invalid\n```"]


@pytest.mark.parametrize("reported", EXITS)
@pytest.mark.parametrize("answer_kind", ["claimed", "nonclaiming", "malformed"])
def test_deliberate_answer_owns_exit_claims_and_attachments(
        synchronous, monkeypatch, reported, answer_kind):
    world = synchronous
    cv = world["cv"]
    attach = []
    original = cv.attach_pending_forms
    monkeypatch.setattr(cv, "attach_pending_forms",
                        lambda *a, **kw: (attach.append(a), original(*a, **kw))[1])
    claim = {"result": "partly", "summary": "deliberate result", "evidence": []}
    held, exp, start, end = _dispatch(
        world, monkeypatch, reported=reported, deliberate=True,
        claim=claim if answer_kind == "claimed" else None,
        malformed=answer_kind == "malformed")
    assert end["act"] == "result-returned", end
    d = end["detail"]
    assert d["response_owner"] == "respond" and d["reply_turn"] == held["reply"]
    assert end["turn"] == held["reply"]
    assert d["run"] == start["id"] and d["request"] == exp
    assert d["collected_text"] == reported and d["collected_text_chars"] == len(reported)
    assert not attach
    claims = C.claims_of(cv, exp)
    assert len(claims) == (1 if answer_kind == "claimed" else 0)
    if claims:
        assert claims[0]["detail"]["summary"] == "deliberate result"
    assert bool(d.get("outcome_unclaimed")) == (answer_kind == "malformed")
    acts = cv.history(execution=held["grant"]["instance"])
    assert len([a for a in acts if a["act"] == "turn-said"]) == 1
    assert not [a for a in acts if a["act"] in ("decision-asked", "form-attached")]


@pytest.mark.parametrize("terminal", ["reported_done", "failed", "cancelled",
                                      "stopped_at_deadline", "max_tokens"])
@pytest.mark.parametrize("deliberate", [False, True])
def test_every_terminal_retains_full_collector_and_answer_link(
        synchronous, monkeypatch, terminal, deliberate):
    world = synchronous
    reported = " \r\nBEGIN Ω\n" + "middle\t" * 4000 + "\nTAIL\r\n "
    held, exp, start, end = _dispatch(
        world, monkeypatch, reported=reported, terminal=terminal,
        deliberate=deliberate,
        claim={"result": "met", "summary": "useful answer", "evidence": []}
        if deliberate else None)
    d = end["detail"]
    assert d["collected_text"] == reported
    assert d["collected_text_chars"] == len(reported) > 20000
    assert d["collected_text_format"] == "work-outcome-reported-v1"
    assert d["notes"] == ["full diagnostic note"]
    assert d["returned_artifacts"] == ["adm-partial-output"]
    assert d["request"] == exp and d["request_turn"] == start["turn"]
    assert d["run"] == start["id"] and d["terminal"] == terminal
    assert d["timed_out"] == (terminal == "stopped_at_deadline")
    if terminal != "reported_done":
        assert end["act"] == "delivery-failed"
        assert d["error"] == "specific failure Ω" and d["exit_code"] == -1
        assert end["turn"] == start["turn"]
        assert d["reply_turn"] == (held["reply"] if deliberate else None)
        assert d["response_owner"] == ("respond" if deliberate else None)
        assert not world["cv"].expectation_state(exp)["satisfied_by"]
    else:
        assert end["act"] == "result-returned"
        assert d["response_owner"] == ("respond" if deliberate else "dispatch-completion")
        assert d["reply_turn"] == end["turn"]
        if deliberate:
            assert d["final_text"] == reported


def test_perform_exception_retains_known_answer_artifact_and_specific_error(synchronous, monkeypatch):
    held, exp, start, end = _dispatch(synchronous, monkeypatch, reported=None,
                                     deliberate=True, raises=True,
                                     claim={"result": "met", "summary": "answer"})
    d = end["detail"]
    assert end["act"] == "delivery-failed" and d["terminal"] == "failed"
    assert d["response_owner"] == "respond" and d["reply_turn"] == held["reply"]
    assert d["collected_text"] is None and d["collected_text_chars"] is None
    assert "perform raised after useful answer" in d["error"]
    assert d["returned_artifacts"] == ["adm-partial-output"]
    assert not synchronous["cv"].expectation_state(exp)["satisfied_by"]


def test_ordinary_aggregate_claim_stays_visible_and_retains_original(synchronous, monkeypatch):
    reported = " \nOrdinary aggregate\n```outcome\nresult: met\nsummary: built it\n```\n "
    held, exp, start, end = _dispatch(synchronous, monkeypatch, reported=reported)
    assert held["grant"]["scope"] == "worker"
    from mentis.worker import permitted
    assert "respond" not in permitted(held["grant"]["scope"], held["grant"]["operations"])
    d = end["detail"]
    assert d["response_owner"] == "dispatch-completion" and d["reply_turn"] == end["turn"]
    assert d["collected_text"] == reported
    parts = synchronous["cv"].corpus.read([end["turn"]])[0]["body"]["parts"]
    assert "Ordinary aggregate" in parts[0]["text"] and "Claim by" in parts[0]["text"]
    assert len(C.claims_of(synchronous["cv"], exp)) == 1


def test_identity_refresh_and_revoke_do_not_change_permissions():
    authority = Authority()
    basis = dict(scope="worker", operations=[], expectation="request", run="start-one")
    authority.authorise_for("execution", basis)
    token = authority._grant("execution", "corpus")
    before = authority.grant_for(token, "corpus")
    authority.authorise_for("execution", {**basis, "delivered": ["source"]})
    after = authority.grant_for(token, "corpus")
    assert after["run"] == before["run"] == "start-one"
    assert after["scope"] == before["scope"] == "worker"
    assert after["operations"] == before["operations"] == []
    assert after["delivered"] == ["source"]
    authority.revoke("execution")
    authority.authorise_for("execution", {**basis, "run": "start-two"})
    second = authority._grant("execution", "corpus")
    assert authority.grant_for(token, "corpus") is None
    assert authority.grant_for(second, "corpus")["run"] == "start-two"


def test_late_old_answer_and_artifact_do_not_belong_to_resumed_start(world):
    cv, who = world["cv"], world["steward"]
    cid = a_conversation(world)
    request = cv.say(cid, world["who"]["@brian"], [text("build it")])
    exp = cv.expect(request, of=who, kind="result", by=world["who"]["@brian"])
    grant = dict(instance="same-execution", participant=who, conversation=cid,
                 expectation=exp, runtime="codex")
    def start():
        return cv.record_act(actor=who, act="execution-started", turn=request,
                             conversation=cid, execution=grant["instance"], caused_by=exp)
    old = start()
    cv.record_act(actor=who, act=artifacts.RETURNED, execution=grant["instance"],
                  caused_by=exp, about=["adm-old"])
    new = start()
    _answer(cv, {**grant, "run": old})  # late old completion after new start
    lookup = dict(execution=grant["instance"], expectation=exp,
                  request_turn=request, since=new)
    assert D._already_answered(cv, **lookup) is None
    reply = _answer(cv, {**grant, "run": new})
    assert D._already_answered(cv, **lookup) == reply
    assert D._already_answered(cv, **{**lookup, "request_turn": "other"}) is None
    assert D._already_answered(cv, **{**lookup, "expectation": "other"}) is None
    outcome = WorkOutcome(instance_id=grant["instance"], terminal="reported_done",
                          reported="", exit_code=0)
    retained = D._retained_end(cv, execution=grant["instance"], started=new,
                               expectation=exp, request_turn=request,
                               outcome=outcome, answered=reply)
    assert retained["returned_artifacts"] == []
    assert retained["collected_text"] == "" and retained["collected_text_chars"] == 0
