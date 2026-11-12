"""Workstream R, fourth review round (review-R-verify3.md, 2026-11-12).

  * a delegated child keeps its causal ancestors' context: the owner post a
    parent's request replies to, and a result its parent's lineage names;
  * placement reads are bounded by depth and the target, never by how many
    refs the lineage names (500 named posts, and 5,000 in a stand-in record).
"""

from __future__ import annotations

from types import SimpleNamespace

from mentis.conversation import text, threads
from tests._loop import say, world  # noqa: F401
from tests.test_reply_context import _answer
from tests.test_reply_context_review2 import _grant_for, _op, _setup


def test_a_child_may_place_on_a_result_its_parent_s_lineage_names(world):
    cv, actor, parent, grant, builder = _setup(world)
    owner = world["who"]["@brian"]
    prior = cv.say(grant["conversation"], owner, [text("Baseline candidate")])
    req = cv.expect(prior, of=builder, kind="result", by=owner)
    result = _answer(cv, grant["conversation"], builder, req,
                     "Baseline implementation", replies_to=prior)
    middle = _op(world, "delegate", {"participant": builder,
                                     "work": "Revise baseline",
                                     "relation": "revises",
                                     "relation_ref": [req]}, grant)
    reviewer = cv.create_participant("@SubReviewer")
    child = _op(world, "delegate", {
        "participant": reviewer,
        "work": "Review a component of the baseline revision"},
        _grant_for(world, middle["expectation"], builder))
    assert _op(world, "request_decision", {
        "on": result, "question": "Accept baseline component revision?"},
        _grant_for(world, child["expectation"], reviewer))["ok"]


def test_a_child_may_place_on_its_parent_s_owner_reply_target(world):
    cv, actor, parent, grant, builder = _setup(world)
    context = cv.say(grant["conversation"], world["who"]["@brian"],
                     [text("This is the design specification to verify")])
    follow = say(world, grant["conversation"], "Verify this specification",
                 replies_to=context, action="ask-participant",
                 dispatch=[{"participant": actor,
                            "work": "Verify this specification",
                            "coordinate": True}])
    child = _op(world, "delegate", {
        "participant": builder,
        "work": "Verify one section of the specification"},
        _grant_for(world, follow["expectations"][0], actor))
    assert _op(world, "request_decision", {
        "on": context, "question": "Accept this specification section?"},
        _grant_for(world, child["expectation"], builder))["ok"]


def test_placement_reads_do_not_grow_with_named_refs(monkeypatch):
    n = 5000
    refs = [f"ent-result-{i}" for i in range(n)]
    exp = {"id": "opr-root", "act": "expectation-recorded", "turn": "ent-root",
           "conversation": "ent-home", "detail": {"routing": {"requirements": {
               "relation": {"value": "verifies", "ref": refs}}}}}
    reads, histories = [], []

    def read(ref):
        reads.append(ref)
        if ref == "opr-root":
            return exp
        return {"id": ref, "act": "run-started", "caused_by": "opr-other"}

    def history(**kw):
        histories.append(kw)
        if str(kw.get("turn", "")).startswith("ent-result-"):
            return [{"id": "opr-return", "act": "result-returned",
                     "caused_by": "opr-run"}]
        return []
    cv = SimpleNamespace(_act=read, history=history, _children=lambda ref: [],
                         _is=lambda entry, kind: kind == "contribution",
                         _c=SimpleNamespace(read=lambda refs: [{"body": {}}],
                                            links=lambda **kw: []),
                         conversation_of=lambda ref: "ent-home")
    monkeypatch.setattr(threads, "reply_target_of", lambda *a: None)
    monkeypatch.setattr(threads, "conversation_allowed", lambda *a: True)
    assert threads.placement_refusal(cv, "opr-root", refs[-1]) is None
    assert len(reads) <= 4 * (threads.MOST_UP + 2)
    assert len(histories) <= 4 * (threads.MOST_UP + 2)


def test_a_real_placement_with_500_named_posts_reads_by_depth(
        world, monkeypatch):
    cv, actor, parent, grant, builder = _setup(world)
    refs = [cv.say(grant["conversation"], world["who"]["@brian"],
                   [text(f"Baseline component specification {i}")])
            for i in range(500)]
    child = _op(world, "delegate", {"participant": builder,
                                    "work": "Verify all baseline specs",
                                    "relation": "verifies",
                                    "relation_ref": refs}, grant)
    cg = _grant_for(world, child["expectation"], builder)
    original = type(cv).history
    histories = []

    def counted(self, **kw):
        histories.append(kw)
        return original(self, **kw)
    monkeypatch.setattr(type(cv), "history", counted)
    assert threads.placement_refusal(cv, child["expectation"], refs[-1],
                                     participant=builder) is None
    assert len(histories) <= 4 * (threads.MOST_UP + 2)
    histories.clear()
    assert _op(world, "request_decision", {
        "on": refs[-1], "question": "Accept the final specification?"},
        cg)["ok"]
    assert len(histories) <= 4 * (threads.MOST_UP + 2)
