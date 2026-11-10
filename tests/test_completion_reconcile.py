"""WS-C: an agent's outcome CLAIM, and what reconciliation records of it.

Four facts, none implying another: a run ended, an outcome was claimed, the
objective was recorded met, and it was verified. These pin:

  * the ```outcome block ending a final reply is a claim, in any scope --
    a worker-scope run and a delegated child included -- taken out of the
    posted reply and rendered as one line;
  * a claim of met is recorded met only by `reconcile`'s four rules; an open
    decision, an unended child it waits on, a failure after the claim and a
    required review each keep it pending, with the reason;
  * partly / not-met are recorded as they stand and never become met;
  * reconciliation is idempotent; a parent is never met by its children;
  * a run ending with no block is "Ended · no outcome claimed", never met;
  * `regards` links from later records, and `later_findings`.
"""

from __future__ import annotations

import time

import pytest

from mentis.conversation import text as text_part
from mentis.execution import RunResult
from mentis.operational import completion as C
from tests._loop import a_conversation, say, world  # noqa: F401


# -- parsing --------------------------------------------------------------------

BLOCK = """Did the thing.

```outcome
summary: changed the parser
result: met   # met | partly | not-met
evidence:
- commit 1a2b3c4 on branch x
- tests: tests/test_y.py 12 passed
owner_note: kept
```
"""


def test_the_block_is_parsed_leniently_and_taken_out_of_the_text():
    claim, rest = C.extract(BLOCK)
    assert claim["result"] == "met"
    assert claim["summary"] == "changed the parser"
    assert claim["evidence"] == ["commit 1a2b3c4 on branch x",
                                 "tests: tests/test_y.py 12 passed"]
    assert claim["owner_note"] == "kept"           # unknown keys are kept
    assert rest == "Did the thing."
    line = C.render(claim)
    assert line.startswith("Outcome claimed: met — changed the parser")
    assert "commit 1a2b3c4" in line
    assert C.with_rendering(rest, claim) == "Did the thing.\n\n" + line


def test_results_are_normalised_and_a_block_without_one_is_no_claim():
    assert C.extract("```outcome\nresult: partial\n```")[0]["result"] == "partly"
    assert C.extract("```outcome\nresult: not met\n```")[0]["result"] == "not-met"
    assert C.extract("```outcome\nresult: done\nsummary: x\n```")[0]["evidence"] == []
    text = "```outcome\nsummary: no result here\n```"
    assert C.extract(text) == (None, text)
    assert C.extract("no block at all") == (None, "no block at all")


def test_the_closing_block_tells_every_run_how_to_claim():
    from mentis.web import dispatch as D
    closing = D._closing_block("do it", None)
    assert closing.startswith("# Before you return")
    assert "```outcome" in closing and "result: met | partly | not-met" in closing
    assert closing.rstrip().endswith(C.CLOSING_INSTRUCTION.rstrip())


# -- record fixtures -------------------------------------------------------------

def _work(world, cid=None, *, of=None, caused_by=None, detail=None):
    cv = world["cv"]
    cid = cid or a_conversation(world)
    owner = world["who"]["@brian"]
    turn = cv.say(cid, owner, [text_part("build it")])
    exp = cv.expect(turn, of=of or world["steward"], kind="result", by=owner,
                    caused_by=caused_by, detail=detail or {})
    return cid, exp


def _run(cv, exp, cid, who, *, execution="inst-1", end="result-returned",
         because=None):
    start = cv.record_act(actor=who, act="execution-started", conversation=cid,
                          execution=execution, runtime="codex", caused_by=exp)
    if end:
        cv.record_act(actor=who, act=end, conversation=cid,
                      execution=execution, runtime="codex", caused_by=start,
                      because=because, detail={"terminal": "reported_done"})
    return start


def _claim(cv, exp, cid, who, result="met", summary="did it",
           execution="inst-1"):
    return C.claim(cv, exp, {"result": result, "summary": summary,
                             "evidence": ["commit abc"]},
                   actor=who, execution=execution, runtime="codex",
                   via="reply", conversation=cid)


def _met(cv, exp):
    return [a for a in cv._own_acts(exp) if a["act"] == "expectation-met"]


def _status(cv, exp):
    from mentis.operational.work import trunk_status
    return trunk_status(cv, exp)["state"]


# -- reconciliation ---------------------------------------------------------------

def test_a_claim_of_met_with_nothing_open_is_recorded_met_and_idempotent(world):
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who)
    claim = _claim(cv, exp, cid, who)
    out = C.reconcile(cv, exp, claim)
    assert out["recorded"] == "met" and out["reasons"] == []
    met = _met(cv, exp)
    assert len(met) == 1
    assert met[0]["detail"]["reconciled_from"] == claim
    assert met[0]["detail"]["claimed_by"] == "inst-1"
    # a second reconciliation writes nothing new
    before = len(cv.history(caused_by=exp))
    again = C.reconcile(cv, exp, claim)
    assert again["recorded"] == "met" and again.get("already")
    assert len(cv.history(caused_by=exp)) == before
    s = _status(cv, exp)
    assert s["value"] == "claimed-met"
    assert s["label"] == "Objective met · claimed by @Steward"


def test_an_open_decision_keeps_the_claim_pending_with_the_reason(world):
    cv, who = world["cv"], world["steward"]
    owner = world["who"]["@brian"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who)
    q = cv.say(cid, who, [text_part("which way?")])
    decision = cv.expect(q, of=owner, kind="decision", by=who, caused_by=exp)
    claim = _claim(cv, exp, cid, who)
    out = C.reconcile(cv, exp, claim)
    assert out["recorded"] == "pending"
    assert out["reasons"] == [f"decision {decision} is open"]
    assert not _met(cv, exp)
    pend = [a for a in cv._own_acts(exp) if a["act"] == C.OUTCOME_PENDING]
    assert len(pend) == 1 and pend[0]["detail"]["claim"] == claim
    # the same reasons again: nothing new
    C.reconcile(cv, exp, claim)
    assert len([a for a in cv._own_acts(exp)
                if a["act"] == C.OUTCOME_PENDING]) == 1
    s = _status(cv, exp)
    assert s["value"] == "claim-pending"
    assert s["label"] == f"Claimed met · pending: decision {decision} is open"


def test_a_run_that_has_not_ended_or_failed_after_the_claim_holds_it(world):
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who, end=None)
    claim = _claim(cv, exp, cid, who)
    assert C.reconcile(cv, exp, claim)["reasons"] == [
        "its run has not ended yet"]
    cid2, exp2 = _work(world)
    start = _run(cv, exp2, cid2, who, end=None)
    claim2 = _claim(cv, exp2, cid2, who)
    cv.record_act(actor=who, act="delivery-failed", conversation=cid2,
                  execution="inst-1", caused_by=start,
                  because="terminal 'failed', exit 1")
    assert C.reconcile(cv, exp2, claim2)["reasons"] == [
        "its run failed after the claim"]
    assert not _met(cv, exp) and not _met(cv, exp2)


def test_partly_and_not_met_are_recorded_as_they_stand_and_never_met(world):
    cv, who = world["cv"], world["steward"]
    for result, value, words in (("partly", "claimed-partly", "Partly done"),
                                 ("not-met", "claimed-not-met", "Not done")):
        cid, exp = _work(world)
        _run(cv, exp, cid, who)
        claim = _claim(cv, exp, cid, who, result=result, summary="half of it")
        out = C.reconcile(cv, exp, claim)
        assert out == {"recorded": result, "reasons": [], "notes": [],
                       "act": None}
        assert not _met(cv, exp)
        s = _status(cv, exp)
        assert s["value"] == value and s["label"] == f"{words} · half of it"


def test_no_claim_is_ended_with_no_outcome_claimed_never_met(world):
    """The runtime ending normally never alone completes work."""
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who)
    assert C.reconcile_latest(cv, exp) is None
    assert not _met(cv, exp)
    s = _status(cv, exp)
    assert s["value"] == "returned"
    assert s["label"] == "Ended · no outcome claimed"


def _delegate(cv, parent, cid, by, to, *, waits=True):
    turn = cv.say(cid, by, [text_part("part of it")], addressed_to=[to])
    child = cv.expect(turn, of=to, kind="result", by=by, caused_by=parent,
                      detail={"returns_to": by if waits else None})
    cv.record_act(actor=by, act="work-delegated", conversation=cid, turn=turn,
                  caused_by=parent, about=[child],
                  detail={"participant": to, "return_expected": waits})
    return child


def test_a_parent_is_not_met_by_its_children_nor_a_child_by_its_parent(world):
    cv, who = world["cv"], world["steward"]
    ada = cv.create_participant("@Ada", about="an agent")
    cid, parent = _work(world)
    child = _delegate(cv, parent, cid, who, ada)
    _run(cv, child, cid, ada, execution="inst-c")
    c_claim = _claim(cv, child, cid, ada, execution="inst-c")
    assert C.reconcile(cv, child, c_claim)["recorded"] == "met"
    assert _met(cv, child) and not _met(cv, parent)
    assert _status(cv, parent)["value"] != "claimed-met"
    # and the other way: a parent's claim does not meet an unclaimed child
    other = _delegate(cv, parent, cid, who, ada, waits=False)
    _run(cv, other, cid, ada, execution="inst-o")
    _run(cv, parent, cid, who, execution="inst-p")
    p_claim = _claim(cv, parent, cid, who, execution="inst-p")
    out = C.reconcile(cv, parent, p_claim)
    assert out["recorded"] == "met"
    assert f"child {other} not met" in out["notes"]
    assert not _met(cv, other)
    # the unclaimed child went back to the work that handed it out
    assert _status(cv, other)["label"] == "Returned to @Steward"


def test_a_child_it_waits_on_and_has_not_ended_holds_the_parent(world):
    cv, who = world["cv"], world["steward"]
    ada = cv.create_participant("@Ada", about="an agent")
    cid, parent = _work(world)
    child = _delegate(cv, parent, cid, who, ada, waits=True)
    _run(cv, child, cid, ada, execution="inst-c", end=None)
    _run(cv, parent, cid, who, execution="inst-p")
    out = C.reconcile(cv, parent, _claim(cv, parent, cid, who,
                                         execution="inst-p"))
    assert out["recorded"] == "pending"
    assert out["reasons"] == [f"child {child} has not ended"]


def _review_workflow(world):
    cv = world["cv"]
    reviewer = cv.define_persona("Independent Reviewer", "Review the change.")
    return cv.corpus.create_and_establish(
        kind="workflow",
        body={"name": "Reviewed change", "about": "x", "text": "build, review",
              "activities": [
                  {"key": "implement", "what": "make the change",
                   "who": {"role": "a worker"}, "done_when": "committed"},
                  {"key": "review", "what": "review the change",
                   "who": {"persona": reviewer}, "done_when": "passed"}],
              "decisions": [], "done_when": "reviewed", "requires": []},
        attributed_to=world["who"]["@brian"]), reviewer


def test_a_workflow_requiring_review_holds_the_claim_until_a_pass(world):
    cv, who = world["cv"], world["steward"]
    wf, _ = _review_workflow(world)
    cid, exp = _work(world, detail={"governed": [wf]})
    assert C.review_required(cv, exp)
    _run(cv, exp, cid, who)
    claim = _claim(cv, exp, cid, who)
    assert C.reconcile(cv, exp, claim)["reasons"] == ["review required"]
    # a review delegated under it records a pass: the claim is reconciled
    rex = cv.create_participant("@Rex", about="a reviewer")
    review = _delegate(cv, exp, cid, who, rex, waits=False)
    cv.record_act(actor=rex, act="review-verdict", conversation=cid,
                  caused_by=review, about=[review],
                  detail={"verdict": "pass", "summary": "fine"})
    got = C.on_review_pass(cv, review)
    assert got and got[0]["recorded"] == "met"
    assert _met(cv, exp)[0]["detail"]["reconciled_from"] == claim
    s = _status(cv, exp)
    assert s["value"] == "verified" and s["label"] == "Verified · @Rex"


def test_respond_with_an_outcome_is_a_claim_and_reconciled(world):
    """`respond` gains `outcome`; `fulfils: true` means met. Recorded met
    only through reconciliation, `reconciled_from` naming the claim."""
    from mentis.web import _surface
    from mentis.worker import _operate
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    grant = {"participant": who, "expectation": exp, "conversation": cid,
             "instance": "inst-r", "runtime": "codex", "scope": "intake",
             "organising": ["respond"]}
    out = _operate(_surface(world["state"]), "respond",
                   {"text": "half done",
                    "outcome": {"result": "partly", "summary": "half"}}, grant)
    assert out["fulfilled_by"] is None
    assert out["reconciled"]["recorded"] == "partly"
    assert cv._act(out["claim"])["detail"]["via"] == "respond"
    out = _operate(_surface(world["state"]), "respond",
                   {"text": "all done", "fulfils": True}, grant)
    assert out["reconciled"]["recorded"] == "met"
    met = cv._act(out["fulfilled_by"])
    assert met["detail"]["reconciled_from"] == out["claim"]


# -- dispatch: the reply block, in a worker-scope run and a delegated child -------

@pytest.fixture()
def synchronous(world, monkeypatch):
    import mentis.web as web
    from mentis.web import dispatch as D
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: D.dispatch(st, **kw))
    return world


def _answering(st, text, seen):
    def answer(spec):
        seen["grant"] = st.agents.authority.grant_for(
            st.agents.authority.grant_of(spec.run_id), st.path)
        seen["prompt"] = spec.prompt
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn", text=text,
                         started_at=now, finished_at=now)
    return answer


def test_a_worker_scope_run_claims_met_through_its_reply(synchronous):
    world = synchronous
    st, cv = world["state"], world["cv"]
    seen = {}
    st.agents.execution.script = {"codex": _answering(st, BLOCK, seen)}
    ada = cv.create_participant("@Ada", about="an agent")
    cid = a_conversation(world)
    out = say(world, cid, "please change the parser", action="ask-participant",
              dispatch=[{"participant": ada, "work": "change the parser",
                         "runtime": "codex"}])
    exp = out["expectations"][0]
    assert seen["grant"]["scope"] == "worker"
    assert "respond" not in (seen["grant"].get("permitted") or [])
    assert "```outcome" in seen["prompt"]          # told how to claim
    claims = C.claims_of(cv, exp)
    assert len(claims) == 1
    d = claims[0]["detail"]
    assert d["result"] == "met" and d["via"] == "reply"
    assert d["claimed_by"] == claims[0]["execution"]
    # the posted reply has the one-line rendering, not the block
    reply = cv.corpus.read([d["reply_turn"]])[0]
    text = " ".join(p.get("text") or "" for p in reply["body"]["parts"])
    assert "```outcome" not in text
    assert "Outcome claimed: met — changed the parser" in text
    met = _met(cv, exp)
    assert len(met) == 1 and met[0]["detail"]["reconciled_from"] == claims[0]["id"]
    assert _status(cv, exp)["value"] == "claimed-met"


def test_a_worker_run_with_no_block_ends_unclaimed(synchronous):
    world = synchronous
    st, cv = world["state"], world["cv"]
    st.agents.execution.script = {"codex": _answering(st, "Here it is.", {})}
    ada = cv.create_participant("@Ada", about="an agent")
    cid = a_conversation(world)
    out = say(world, cid, "summarise", action="ask-participant",
              dispatch=[{"participant": ada, "work": "summarise",
                         "runtime": "codex"}])
    exp = out["expectations"][0]
    assert not C.claims_of(cv, exp) and not _met(cv, exp)
    from mentis.operational.work_overview import overview
    items = [i for i in overview(cv, viewer=world["who"]["@brian"],
                                 runtime=None)["items"]
             if i["expectation"] == exp]
    assert items and items[0]["status_words"] == "Ended · no outcome claimed"
    assert items[0]["objective_met"] is False
    assert items[0]["claim"] is None
    assert items[0]["stage_words"].startswith("Ended")
    assert "Answered" not in items[0]["stage_words"]


def test_a_delegated_child_claims_through_its_reply(synchronous):
    from mentis.web import dispatch as D
    world = synchronous
    st, cv = world["state"], world["cv"]
    who = world["steward"]
    ada = cv.create_participant("@Ada", about="an agent")
    cid, parent = _work(world)
    cv.join(ada, cid, attributed_to=world["who"]["@brian"])
    child = _delegate(cv, parent, cid, who, ada)
    st.agents.execution.script = {"codex": _answering(
        st, "Part done.\n```outcome\nresult: met\nsummary: the part\n```", {})}
    turn = cv._act(child)["turn"]
    D.dispatch(st, conversation=cid, turn=turn, participant=ada,
               work="part of it", expectation=child, runtime="codex")
    claims = C.claims_of(cv, child)
    assert len(claims) == 1 and claims[0]["detail"]["result"] == "met"
    assert _met(cv, child)
    assert not _met(cv, parent)


# -- later findings ------------------------------------------------------------------

def test_regarding_links_are_neutral_and_listed_as_later_findings(world):
    from mentis.web import _surface
    from mentis.worker import NotPermitted, _operate
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who)
    claim = _claim(cv, exp, cid, who)
    C.reconcile(cv, exp, claim)
    cid2, other = _work(world, cid)
    grant = {"participant": who, "expectation": other, "conversation": cid,
             "instance": "inst-2", "runtime": "codex", "scope": "worker"}
    out = _operate(_surface(world["state"]), "record_discovered_work",
                   {"work": "the parser drops comments",
                    "regarding": [exp, claim]}, grant)
    assert len(out["regards"]) == 2
    links = cv.corpus.links(relation=C.REGARDS, frm=out["turn"])
    assert sorted(x["link"]["to"] for x in links) == sorted([exp, claim])
    found = C.later_findings(cv, exp)
    assert [f["id"] for f in found] == [out["turn"]]
    # nothing was reopened: the claim and its met stand as recorded
    assert _status(cv, exp)["value"] == "claimed-met"
    # a reference that is not an expectation, claim or Turn is refused, and
    # nothing is written
    before = len(cv.history(caused_by=other))
    with pytest.raises(NotPermitted):
        _operate(_surface(world["state"]), "record_discovered_work",
                 {"work": "x", "regarding": ["ent-nothing-here"]}, grant)
    assert len(cv.history(caused_by=other)) == before
    # the helper other contributions call
    turn = cv.say(cid, who, [text_part("a later note")])
    assert len(C.link_regarding(cv, turn, [exp], who)) == 1
    assert {f["id"] for f in C.later_findings(cv, exp)} == {out["turn"], turn}
    from mentis.operational.work_overview import overview
    items = [i for i in overview(cv, viewer=world["who"]["@brian"],
                                 runtime=None)["items"]
             if i["expectation"] == exp]
    assert {f["id"] for f in items[0]["later_findings"]} == {out["turn"], turn}
    assert items[0]["claim"]["recorded"] == "met"
    assert items[0]["status_words"] == "Objective met · claimed by @Steward"


def test_record_outcome_maps_to_a_claim(world):
    m = C.RECORD_OUTCOME_RESULTS
    assert (m["done"], m["partial"], m["abandoned"], m["blocked"],
            m["failed"]) == ("met", "partly", "not-met", "not-met", "not-met")


def test_run_state_says_ended_not_completed():
    from mentis.operational.runs import run_state
    start = {"id": "opr-s", "execution": "i", "runtime": "codex", "at": 1.0}
    end = {"id": "opr-e", "act": "result-returned", "at": 2.0}
    rs = run_state(start, end, now=3.0)
    assert rs["state"] == "ended" and rs["words"].startswith("ended · ")


# -- re-reconciled when what held the claim clears, with no further run -------------

def test_answering_the_decision_reconciles_the_claim_it_held(world):
    cv, who = world["cv"], world["steward"]
    owner = world["who"]["@brian"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who)
    q = cv.say(cid, who, [text_part("left or right?")], addressed_to=[owner])
    decision = cv.expect(q, of=owner, kind="decision", by=who, caused_by=exp)
    claim = _claim(cv, exp, cid, who)
    assert C.reconcile(cv, exp, claim)["recorded"] == "pending"
    assert C.pending_claim(cv, exp)["id"] == claim
    out = say(world, cid, "left", replies_to=q, action="record-only")
    assert "error" not in out, out
    assert cv.expectation_state(decision)["response_present"]
    met = _met(cv, exp)
    assert len(met) == 1 and met[0]["detail"]["reconciled_from"] == claim
    assert C.pending_claim(cv, exp) is None
    # idempotent: clearing again writes nothing
    before = len(cv.history(caused_by=exp))
    assert C.reconcile_held_by(cv, decision) == []
    assert len(cv.history(caused_by=exp)) == before


def test_a_waited_on_child_ending_reconciles_the_parents_claim(synchronous):
    from mentis.web import dispatch as D
    world = synchronous
    st, cv, who = world["state"], world["cv"], world["steward"]
    ada = cv.create_participant("@Ada", about="an agent")
    cid, parent = _work(world)
    cv.join(ada, cid, attributed_to=world["who"]["@brian"])
    child = _delegate(cv, parent, cid, who, ada, waits=True)
    _run(cv, parent, cid, who, execution="inst-p")
    claim = _claim(cv, parent, cid, who, execution="inst-p")
    assert C.reconcile(cv, parent, claim)["reasons"] == [
        f"child {child} has not ended"]
    # the child's own run ends, with no claim of its own
    st.agents.execution.script = {"codex": _answering(st, "Part done.", {})}
    D.dispatch(st, conversation=cid, turn=cv._act(child)["turn"],
               participant=ada, work="part of it", expectation=child,
               runtime="codex")
    met = _met(cv, parent)
    assert len(met) == 1 and met[0]["detail"]["reconciled_from"] == claim
    assert f"child {child} not met" in met[0]["detail"]["notes"]
    assert not _met(cv, child)
    # recorded met, so its ending did not run the parent again
    assert not [a for a in cv.history(caused_by=parent)
                if a["act"] == "work-resumed"]


def test_a_child_ending_leaves_a_claim_alone_that_is_not_pending(world):
    cv, who = world["cv"], world["steward"]
    ada = cv.create_participant("@Ada", about="an agent")
    cid, parent = _work(world)
    child = _delegate(cv, parent, cid, who, ada, waits=True)
    _run(cv, parent, cid, who, execution="inst-p")
    _claim(cv, parent, cid, who, result="partly", execution="inst-p")
    assert C.reconcile_held_by(cv, child) == []
    assert not _met(cv, parent)


# -- a resumed continuation still ends with how to claim -----------------------------

from tests.test_execution_continuity import (  # noqa: E402,F401
    _resumed_with_a_follow_up, _sent_for, team)


def test_a_resumed_continuation_prompt_ends_with_the_outcome_instruction(
        world, team):
    from mentis.web import continuity
    got = _resumed_with_a_follow_up(world, team, resumes=True)
    sent = _sent_for(world, got["spec"])
    assert sent.startswith(continuity.RESUME_NOTICE)    # it was resumed
    assert sent == got["spec"].continuation
    assert sent.rstrip().endswith(C.CLOSING_INSTRUCTION.rstrip())
    assert "```outcome" in sent[sent.rfind("# Before you return"):]
