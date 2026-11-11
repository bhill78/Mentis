"""Workflow independence (round 4, owner decision 6, 2026-11-11).

The owner: Mentis supports many user-defined Workflows with different purposes, complexity and
completion requirements; a Workflow defines the process and completion requirements of the work
USING it; testing, independent review, commits, merges, deployment and production verification
are not universal requirements; different work items in one project or conversation can use
different Workflows; an authorised Workflow change keeps the work's identity, history, evidence
and attribution; completion is reconciled against the actual applicable Workflow; no Workflow
grants authority; no Workflow is privileged because it is the current DAY-TO-DAY process.

Pinned here, on the record (`completion.reconcile`, `workflow_change`, `posting.owe`'s reads):

  1. two requests in ONE conversation, one under a one-step Workflow and one under a many-step
     Workflow with a review activity, each reconcile against their OWN Workflow;
  2. a request naming no Workflow is not made to pass a review, a test or a commit: its claim
     of met, with no evidence of any of them, is recorded met; nothing attaches a Workflow it
     did not choose (not another request's in the same conversation, not a shipped baseline
     Workflow in a new Brain);
  3. a Workflow change mid-work keeps the request id, the earlier record, who changed it, why
     and on what evidence, and from then on the claim is reconciled against the new Workflow;
  4. no Workflow widens authority: a request's grant and consent are the same whichever
     Workflow (or none) governs it, a Workflow change grants nothing, and a widening after a
     carrier's change is refused at dispatch.
"""

from __future__ import annotations

from mentis.conversation import text as text_part
from mentis.conversation import workflow_change as WC
from mentis.operational import completion as C
from tests._loop import a_conversation, world  # noqa: F401
from tests.test_completion_reconcile import _claim, _met, _review_of, _run, _work


def _workflow(world, name, activities, *, text="how the work goes"):
    return world["cv"].corpus.create_and_establish(
        kind="workflow",
        body={"name": name, "about": name, "text": text, "projects": [],
              "activities": activities, "decisions": [], "done_when": f"{name} done",
              "requires": []},
        attributed_to=world["who"]["@brian"])


def _trivial(world):
    """One step, nothing else: no test, no review, no commit."""
    return _workflow(world, "Quick answer", [
        {"key": "answer", "what": "answer the question", "who": {"role": "the carrier"},
         "done_when": "answered"}])


def _many_step(world):
    """Many steps, one of them an independent review."""
    reviewer = world["cv"].define_persona("Independent Reviewer", "Review the change.")
    steps = [("plan", "plan the parts"), ("implement", "make the change"),
             ("test", "run the targeted tests"), ("integrate", "integrate the parts"),
             ("commit", "commit the result"), ("deploy", "deploy it")]
    rows = [{"key": k, "what": w, "who": {"role": "a worker"}, "done_when": "done"}
            for k, w in steps]
    rows.insert(3, {"key": "review", "what": "review the change",
                    "who": {"persona": reviewer}, "done_when": "passed"})
    return _workflow(world, "Long software change", rows), reviewer


def _review_pass(world, cv, work, cid):
    """An independent review of `work`, by somebody other than its claimant, recording PASS."""
    rex = cv.create_participant("@Rex", about="a reviewer")
    review = _review_of(cv, work, cid, world["steward"], rex)
    _run(cv, review, cid, rex, execution="inst-rex")
    cv.record_act(actor=rex, act=C.REVIEW_VERDICT, conversation=cid, caused_by=review,
                  about=[review], detail={"verdict": "pass", "summary": "fine"})
    return C.on_review_pass(cv, review)


def test_two_items_in_one_conversation_reconcile_against_their_own_workflows(world):
    cv, who = world["cv"], world["steward"]
    quick = _trivial(world)
    long_, _ = _many_step(world)
    cid = a_conversation(world, "Two Workflows, one conversation")
    _, small = _work(world, cid, detail={"governed": [quick]})
    _, big = _work(world, cid, detail={"governed": [long_]})
    assert cv.governed_named(small) == [quick] and cv.governed_named(big) == [long_]
    assert not C.review_required(cv, small) and C.review_required(cv, big)

    _run(cv, small, cid, who, execution="run-small")
    _run(cv, big, cid, who, execution="run-big")
    got_small = C.reconcile(cv, small, _claim(cv, small, cid, who, execution="run-small"))
    got_big = C.reconcile(cv, big, _claim(cv, big, cid, who, execution="run-big"))
    # the trivial one is met on its own requirements; the long one waits on ITS review only
    assert got_small["recorded"] == "met" and _met(cv, small)
    assert got_big == {**got_big, "recorded": "pending", "reasons": ["review required"]}
    assert not _met(cv, big)
    # nothing the long Workflow names (tests, commit, deploy) is asked of either: only its
    # review activity, which is the one requirement Mentis reads from a Workflow
    got = _review_pass(world, cv, big, cid)
    assert got and got[0]["recorded"] == "met" and _met(cv, big)
    # the status reads each request's own Workflow, not the other's
    from mentis.operational.work import trunk_status
    names = lambda e: [w["name"] for w in trunk_status(cv, e)["workflow"]["value"] or ()]  # noqa: E731
    assert names(small) == ["Quick answer"] and names(big) == ["Long software change"]


def test_work_with_no_workflow_is_not_forced_into_review_test_or_commit(world):
    cv, who = world["cv"], world["steward"]
    long_, _ = _many_step(world)
    cid = a_conversation(world, "No Workflow beside one")
    _, governed = _work(world, cid, detail={"governed": [long_]})
    _, plain = _work(world, cid)                     # names nothing
    assert cv.governed_named(plain) == []            # another item's Workflow is not attached
    assert WC.history(cv, plain)["origin"] == "none"
    assert not C.review_required(cv, plain)
    _run(cv, plain, cid, who)
    claim = C.claim(cv, plain, {"result": "met", "summary": "answered", "evidence": []},
                    actor=who, execution="inst-1", runtime="codex", via="reply",
                    conversation=cid)
    got = C.reconcile(cv, plain, claim)
    assert got["recorded"] == "met" and got["reasons"] == []
    assert C.review_required(cv, governed)           # the other item is unaffected


def test_a_new_brain_attaches_no_workflow_to_work_that_names_none(tmp_path):
    """The shipped baseline Workflow is one option a new Brain can name; it is placed nowhere,
    so it reaches no work that did not choose it, and nothing requires a review of such work."""
    import mentis.api as api
    from mentis.bootstrap import baseline
    from mentis.conversation import SCOPED_TO
    c = api.create_corpus(str(tmp_path / "brain"))
    try:
        cv = api.brain(c).conversations
        out = baseline.install(c, "@owner")
        flow = out["items"]["software-change"]["entry"]
        assert "software-change" not in out.get("placements", {})
        assert not cv._links_now(SCOPED_TO, frm=flow)
        owner = cv.participants_named("@owner")[0]
        cid = cv.open_conversation("Somewhere", written_by=owner)
        turn = cv.say(cid, owner, [text_part("what time is it")])
        exp = cv.expect(turn, of=owner, kind="result", by=owner)
        assert cv.governed_named(exp) == []
        assert WC.history(cv, exp)["origin"] == "none"
        assert not C.review_required(cv, exp)
    finally:
        c.close()


def test_a_workflow_change_mid_work_keeps_identity_history_and_attribution(world):
    cv, who = world["cv"], world["steward"]
    owner = world["who"]["@brian"]
    quick = _trivial(world)
    long_, _ = _many_step(world)
    cid = a_conversation(world, "Changed mid-work")
    _, exp = _work(world, cid, detail={"governed": [quick]})
    first = _run(cv, exp, cid, who, execution="run-1")
    before = {a["id"] for a in cv.history(caused_by=exp)}
    authority_before = cv.authority_of(exp)
    finding = cv.say(cid, owner, [text_part("finding: this is a real change, not a question")])

    change = WC.check(cv, exp, long_, because="the question turned into a change",
                      evidence=[finding], role=WC.OWNER)
    act = WC.record(cv, change, by=owner)

    # the same request, its earlier record intact, the change attributed and explained
    assert cv._act(exp)["act"] == "expectation-recorded"
    assert before <= {a["id"] for a in cv.history(caused_by=exp)}
    assert cv._act(first) is not None
    h = WC.history(cv, exp)
    assert [e["kind"] for e in h["history"]] == ["asked", "changed"]
    asked, changed = h["history"]
    assert [w["entry"] for w in asked["workflows"]] == [quick]
    assert changed["act"] == act and changed["by"] == owner and changed["role"] == WC.OWNER
    assert changed["because"] == "the question turned into a change"
    assert [e["ref"] for e in changed["evidence"]] == [finding]
    assert [w["entry"] for w in changed["from"]] == [quick]
    assert [w["entry"] for w in changed["to"]] == [long_]
    assert h["origin"] == "changed" and [w["entry"] for w in h["current"]] == [long_]
    # the change grants nothing, and says so
    d = cv._act(act)["detail"][WC.CHANGE]
    assert d["grants"].startswith("nothing")
    assert cv.authority_of(exp) == authority_before
    # from now on the claim is reconciled against the Workflow that applies now
    _run(cv, exp, cid, who, execution="run-2")
    got = C.reconcile(cv, exp, _claim(cv, exp, cid, who, execution="run-2"))
    assert got["recorded"] == "pending" and got["reasons"] == ["review required"]
    # and back again: the trivial Workflow asks no review, and the claim waiting is met
    WC.record(cv, WC.check(cv, exp, quick, because="it was a question after all",
                           evidence=[finding], role=WC.OWNER), by=owner)
    assert not C.review_required(cv, exp)
    assert [e["kind"] for e in WC.history(cv, exp)["history"]] == ["asked", "changed", "changed"]


def test_no_workflow_widens_authority(world):
    cv = world["cv"]
    owner = world["who"]["@brian"]
    quick = _trivial(world)
    long_, _ = _many_step(world)
    coordinating = _workflow(world, "Coordinated", [
        {"key": "pick-up", "what": "pick up discovered work", "who": {"role": "the carrier"},
         "done_when": "picked up", "coordinates": True, "authority_sensitive": True}])
    cid = a_conversation(world, "Authority")
    seen = []
    for governed in ([], [quick], [long_], [coordinating]):
        _, exp = _work(world, cid, detail={"governed": governed})
        seen.append((cv.authority_of(exp).get("operations") or [],
                     WC.authority_snapshot(cv, exp)))
    # the same (no) organising authority and the same consent, whichever Workflow governs
    assert all(s == seen[0] for s in seen), seen
    # a carrier's change records what the work could do; anything wider later is refused
    # unless the owner said so (`authority_widened`, read by dispatch before a run starts)
    _, exp = _work(world, cid, detail={"governed": [quick]})
    finding = cv.say(cid, owner, [text_part("finding: needs coordination")])
    WC.record(cv, WC.check(cv, exp, coordinating, because="it grew", evidence=[finding],
                           role=WC.CARRIER), by=world["steward"])
    assert WC.authority_widened(cv, exp) is None       # nothing wider than before
    assert WC.pending_carrier_change(cv, exp) is not None


def test_a_workflow_placed_where_work_runs_is_not_that_works_requirement(world):
    """An installation may place its usual Workflow on the whole Brain (DAY-TO-DAY places its
    Software change Workflow conditionally). Placed by reference, it is not the procedure or
    completion requirement of work that did not name it: no review is required of that work,
    the work status says it is placed, and "completes when" is not read from it. Work that
    names it gets all of it."""
    from mentis.operational.work import trunk_status
    from tests.test_workflow_change import _get
    cv, who = world["cv"], world["steward"]
    long_, _ = _many_step(world)
    cv.place(long_, whole_brain=True, by=world["who"]["@brian"], because="our usual process",
             delivery="conditional", when="changing software")
    cid = a_conversation(world, "Placed, not named")
    _, plain = _work(world, cid)
    _, named = _work(world, cid, detail={"governed": [long_]})
    assert cv.governed_named(plain) == [] and not C.review_required(cv, plain)
    assert C.review_required(cv, named)
    [placed] = trunk_status(cv, plain)["workflow"]["value"]
    assert placed["entry"] == long_ and placed.get("placed") is True
    [own] = trunk_status(cv, named)["workflow"]["value"]
    assert own["entry"] == long_ and "placed" not in own
    assert _get(world, f"/api/work/{plain}")["completes_when"] is None
    assert _get(world, f"/api/work/{named}")["completes_when"] == "Long software change done"
    _run(cv, plain, cid, who)
    assert C.reconcile(cv, plain, _claim(cv, plain, cid, who))["recorded"] == "met"
