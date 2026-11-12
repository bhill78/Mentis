"""Workstream R, second review round (review-R-verify.md, 2026-11-12).

  A  lineage (relation_ref) into another Conversation imports nothing: an
     outcome against that Conversation's posts is refused;
  B  a Conversation opened under the carried request, with work delegated
     into it, is the work's: the parent may cite, record against and ask on
     the child's result there;
  C  explicit lineage naming a RESULT post (continues / revises / verifies /
     implements, relation_ref=ent-...) lets a decision form go on it;
  D  the thread walk reads at most MOST_NODES records, per record read, and
     walks the causal chain before lineage, so wide lineage never pushes a
     causal ancestor's answer out of the thread.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mentis.conversation import text, threads
from tests._loop import _coordinator, a_conversation, world  # noqa: F401
from tests.test_reply_context import _answer


def _op(world, name, args, grant):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), name, args, grant)


def _grant_for(world, expectation, participant):
    from mentis.web.dispatch import authority_for
    cv = world["cv"]
    auth = world["state"].agents.authority
    got = authority_for(cv, expectation)
    iid = f"review-child-{expectation}"
    auth.authorise_for(iid, {"scope": got["scope"],
                             "operations": got["organising"],
                             "participant": participant,
                             "expectation": expectation,
                             "conversation": cv._act(expectation)["conversation"],
                             "runtime": "claude"})
    return auth.grant_for(auth._grant(iid, world["state"].path),
                          world["state"].path)


def _setup(world):
    actor, parent, grant = _coordinator(world, a_conversation(world))
    builder = world["cv"].create_participant("@Builder")
    return world["cv"], actor, parent, grant, builder


BODY = {"text": "Verified result", "result": "done", "attempted": True}


# -- C ---------------------------------------------------------------------------

@pytest.mark.parametrize("relation",
                         ["continues", "revises", "verifies", "implements"])
def test_c_lineage_naming_a_result_post_allows_a_form_on_it(world, relation):
    cv, actor, parent, grant, builder = _setup(world)
    first = _op(world, "delegate", {"participant": builder,
                                    "work": "Build candidate"}, grant)
    result = _answer(cv, grant["conversation"], builder, first["expectation"],
                     "Candidate commit 123", replies_to=first["turn"],
                     claim={"result": "met", "summary": "built"})
    second = _op(world, "delegate", {"participant": builder,
                                     "work": "Revise candidate",
                                     "relation": relation,
                                     "relation_ref": [result]}, grant)
    req = cv._act(second["expectation"])["detail"]["routing"]["requirements"]
    assert result in req["relation"]["ref"]
    out = _op(world, "request_decision",
              {"on": result, "question": "Approve change to this candidate?"},
              _grant_for(world, second["expectation"], builder))
    assert out["ok"]


# -- B ---------------------------------------------------------------------------

def _sub_conversation(world):
    cv, actor, parent, grant, builder = _setup(world)
    new = _op(world, "open_conversation", {"name": "Implementation subwork"},
              grant)["conversation"]
    child = _op(world, "delegate", {"participant": builder,
                                    "work": "Build candidate",
                                    "conversation": new}, grant)
    answer = _answer(cv, new, builder, child["expectation"], "Candidate built",
                     replies_to=child["turn"])
    return cv, parent, grant, new, child, answer


def test_b_the_parent_cites_its_child_s_result_in_a_sub_conversation(world):
    cv, parent, grant, new, child, answer = _sub_conversation(world)
    assert _op(world, "record_material", {
        "kind": "outcome", "body": BODY,
        "outcome_of": cv._act(parent)["turn"],
        "in_context": grant["conversation"], "basis": [answer]}, grant)["entry"]


def test_b_the_parent_records_in_the_sub_conversation(world):
    cv, parent, grant, new, child, answer = _sub_conversation(world)
    assert _op(world, "record_material", {
        "kind": "outcome", "body": BODY, "outcome_of": child["turn"],
        "in_context": new, "basis": [answer]}, grant)["entry"]


def test_b_the_parent_asks_on_its_child_s_result(world):
    cv, parent, grant, new, child, answer = _sub_conversation(world)
    assert _op(world, "request_decision",
               {"question": "Accept child delivery?", "on": answer},
               grant)["ok"]


# -- A ---------------------------------------------------------------------------

def test_a_lineage_into_another_conversation_imports_nothing(world):
    from mentis.worker import NotPermitted
    cv, actor, parent, grant, builder = _setup(world)
    other = a_conversation(world, "Unrelated work")
    alien = cv.say(other, world["who"]["@brian"],
                   [text("Unrelated owner request")])
    alien_exp = cv.expect(alien, of=builder, kind="result",
                          by=world["who"]["@brian"])
    alien_result = _answer(cv, other, builder, alien_exp, "Other work result",
                           replies_to=alien)
    child = _op(world, "delegate", {"participant": builder,
                                    "work": "Look at other work",
                                    "relation": "verifies",
                                    "relation_ref": [alien_exp]}, grant)
    child_grant = _grant_for(world, child["expectation"], builder)
    for args in ({"outcome_of": alien_result, "in_context": alien,
                  "basis": [alien_result]},
                 {"outcome_of": child["turn"], "in_context": other},
                 {"outcome_of": child["turn"],
                  "in_context": grant["conversation"],
                  "basis": [alien_result]}):
        with pytest.raises(NotPermitted):
            _op(world, "record_material",
                {"kind": "outcome", "body": BODY, **args}, child_grant)
    assert alien_result not in threads.thread_of(
        cv, child["expectation"])["posts"]


# -- D ---------------------------------------------------------------------------

def test_d_the_walk_reads_at_most_its_budget(monkeypatch):
    n = 5000
    acts = {"opr-root": {"id": "opr-root", "act": "expectation-recorded",
                         "turn": "ent-root", "detail": {"routing": {
                             "requirements": {"relation": {
                                 "value": "verifies",
                                 "ref": [f"opr-{i}" for i in range(n)]}}}}}}
    acts.update({f"opr-{i}": {"id": f"opr-{i}", "act": "expectation-recorded",
                              "turn": f"ent-{i}"} for i in range(n)})
    reads = []

    def read(ref):
        reads.append(ref)
        return acts.get(ref)
    cv = SimpleNamespace(_act=read, _children=lambda ref: [],
                         history=lambda **kw: [],
                         _c=SimpleNamespace(read=lambda refs: []))
    monkeypatch.setattr(threads, "reply_target_of", lambda *a: None)
    t = threads.thread_of(cv, "opr-root")
    assert len(reads) <= threads.MOST_NODES
    assert len(t["posts"]) <= threads.MOST_NODES


def test_d_a_real_wide_lineage_stays_within_the_budget(world):
    cv, actor, parent, grant, builder = _setup(world)
    refs = []
    for i in range(80):
        turn = cv.say(grant["conversation"], world["who"]["@brian"],
                      [text(f"Reference request {i}")])
        refs.append(cv.expect(turn, of=builder, kind="result",
                              by=world["who"]["@brian"]))
    child = _op(world, "delegate", {"participant": builder,
                                    "work": "Verify related requests",
                                    "relation": "verifies",
                                    "relation_ref": refs}, grant)
    t = threads.thread_of(cv, child["expectation"])
    assert len(t["posts"]) <= threads.MOST_NODES


def test_d_wide_lineage_keeps_the_causal_grandparent_s_answer(world):
    cv, actor, parent, grant, builder = _setup(world)
    root_result = _op(world, "respond",
                      {"text": "Overall plan ready for owner review"},
                      grant)["turn"]
    middle = _op(world, "delegate", {"participant": builder,
                                     "work": "Implement plan"}, grant)
    middle_grant = _grant_for(world, middle["expectation"], builder)
    verifier = cv.create_participant("@Verifier")
    refs = []
    for i in range(50):
        turn = cv.say(grant["conversation"], world["who"]["@brian"],
                      [text(f"Requirement {i}")])
        refs.append(cv.expect(turn, of=verifier, kind="result",
                              by=world["who"]["@brian"]))
    child = _op(world, "delegate", {"participant": verifier,
                                    "work": "Verify requirements against plan",
                                    "relation": "verifies",
                                    "relation_ref": refs}, middle_grant)
    out = _op(world, "request_decision", {
        "on": root_result,
        "question": "Approve the plan used to verify these requirements?"},
        _grant_for(world, child["expectation"], verifier))
    assert out["ok"]
