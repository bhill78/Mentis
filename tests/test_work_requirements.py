"""Work requirements as inputs (docs/model-selection-contract.md section 2):
`delegate` and the owner composer take solution / reasoning / relation /
relation_ref / exploratory / done_when, validated, refused in words a caller
can act on; a legacy `difficulty` still works with source `compat`; what is
stated is recorded as `routing.requirements` and decides the need selection
judges candidates by. D4: a revision of work that failed substantively is
reassessed, never escalated.

Through the real delegate, posting and dispatch paths over a MARS
`modelCatalogue` (tests/_catalogue_world.py)."""

from __future__ import annotations

import pytest

from mentis import evidence as E
from mentis.core import requirements as R
from mentis.worker import NotPermitted
from tests._catalogue_world import (cat_carrying, cat_real, delegate,  # noqa: F401
                                    latest_start, reply_of, routing_of, run)
from tests._loop import a_conversation, say, world  # noqa: F401

UI = ["build_ui", "drive_browser"]


# -- the vocabulary ---------------------------------------------------------------

@pytest.mark.parametrize("word,solution,reasoning", [
    ("mechanical", "specified", "light"), ("routine", "specified", "substantial"),
    ("complex", "open", "deep"), ("architecture", "open", "deep"),
    ("debugging", "open", "deep")])
def test_each_legacy_difficulty_word_reads_as_compat(word, solution, reasoning):
    req, warnings = R.derive(difficulty=word)
    assert req["solution"] == {"value": solution, "source": "compat", "from": []}
    assert req["reasoning"] == {"value": reasoning, "source": "compat", "from": []}
    assert req["scope"] == {"value": "unstated", "source": "default"}
    assert warnings == []
    tier = {"light": "economy", "substantial": "coding", "deep": "frontier"}[reasoning]
    assert R.tier_of(R.need(req)) == tier


def test_bounded_is_narrow_scope_not_a_known_answer():
    """Round 2 (owner, 2026-11-12): `bounded` is scope. It reads as scope
    narrow and reasoning substantial with the solution UNSTATED; its need is
    unchanged (substantial, not open), so no historical pick changes."""
    req, warnings = R.derive(difficulty="bounded")
    assert req["solution"] == {"value": "unstated", "source": "default",
                               "from": []}
    assert req["reasoning"] == {"value": "substantial", "source": "compat",
                                "from": []}
    assert req["scope"] == {"value": "narrow", "source": "compat"}
    assert warnings == []
    need = R.need(req)
    assert (need["level"], need["open"], need["soft"]) == ("substantial", False,
                                                           False)
    assert R.tier_of(need) == "coding"
    assert R.tier_sources(need) == ["difficulty"]
    old = R.from_routing({"difficulty": "bounded", "required_tier": "coding"})
    assert old["solution"]["value"] == "unstated"
    assert old["scope"] == {"value": "narrow", "source": "compat"}
    assert R.need(old) == need
    # stated scope is informational: never an input to the need
    for scope in ("narrow", "broad"):
        got, _ = R.derive(scope=scope, solution="open", reasoning="deep")
        assert got["scope"] == {"value": scope, "source": "stated"}
        assert (R.need(got)["level"], R.need(got)["open"]) == ("deep", True)
    with pytest.raises(R.Invalid, match="scope is one of"):
        R.derive(scope="small")


@pytest.mark.parametrize("word", ["ordinary", "default", None, "hard"])
def test_ordinary_and_absent_imply_nothing(word):
    req, _ = R.derive(difficulty=word)
    assert req["solution"]["value"] == "unstated"
    need = R.need(req)
    assert need["soft"] and need["level"] == "substantial" and not need["open"]


def test_a_legacy_word_still_yields_to_the_workflow_and_advisory_floors():
    # unchanged precedence: `routing.required_tier`
    req, _ = R.derive(difficulty="complex")
    need = R.need(req, floors=[("workflow_default", "economy")])
    assert (need["level"], need["open"]) == ("light", False)
    # a STATED requirement is only raised by a floor
    req, _ = R.derive(solution="open", reasoning="deep")
    need = R.need(req, floors=[("workflow_default", "economy")])
    assert (need["level"], need["open"]) == ("deep", True)


@pytest.mark.parametrize("args,words", [
    ({"solution": "known"}, "solution is one of"),
    ({"reasoning": "huge"}, "reasoning is one of"),
    ({"relation": "fixes"}, "relation is one of"),
    ({"relation_ref": ["x"]}, "state `relation` with it"),
    ({"relation": "implements"}, "give relation_ref"),
    ({"exploratory": True}, "give `done_when`"),
    ({"done_when": "tests pass"}, "only for exploratory work"),
    ({"exploratory": "yes", "done_when": "x"}, "true or false")])
def test_delegate_refuses_a_requirement_it_cannot_read(world, cat_carrying, args,
                                                      words):
    with pytest.raises(NotPermitted) as got:
        delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                 work="w", requires=[], **args)
    assert words in str(got.value)


def test_a_relation_ref_must_name_something_the_record_holds(world, cat_carrying):
    with pytest.raises(NotPermitted) as got:
        delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                 work="w", requires=[], relation="implements",
                 relation_ref=["ent-doesnotexist"])
    assert "names nothing this record holds" in str(got.value)


# -- the round-two composer downgrade (owner, 2026-11-11) ---------------------------

def test_small_but_open_design_work_is_never_economy_or_coding(world, cat_carrying):
    """Round 2 of the Quiet Chat composer mockups was delegated `bounded` ("one
    focused revision") and ran on the coding-tier model; the owner rejected it:
    it was an open interaction-design problem. Stated `solution: open`, only
    models whose standing covers open work are established."""
    cv = world["cv"]
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="one focused revision of the composer mockups",
                   requires=UI, solution="open")
    routed = routing_of(cv, out["expectation"])
    assert routed["requirements"]["solution"] == {"value": "open",
                                                  "source": "stated", "from": []}
    assert routed["required_tier"] == "frontier"
    run(world, out)
    start = latest_start(cv, out["expectation"])
    d = start["detail"]
    assert start["runtime"] == "claude"
    assert d["selected_model"] == "claude-opus-5"
    assert d["selected_effort"] == "medium", "unstated reasoning: the soft floor"
    cands = {(c["runtime"], c["model"]): c for c in d["selection"]["candidates"]}
    assert cands[("claude", "claude-opus-5")]["outcome"] == "selected"
    for weaker in ("claude-sonnet-5", "claude-haiku-4-5-20251001"):
        assert cands[("claude", weaker)]["verdict"] == "unknown"
        assert cands[("claude", weaker)]["outcome"] == "deferred"
    assert d["requirements"]["solution"]["value"] == "open"
    assert d["selection"]["need"]["open"] is True


def test_the_same_call_with_only_bounded_is_coding_with_source_compat(world,
                                                                    cat_carrying):
    cv = world["cv"]
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="one focused revision of the composer mockups",
                   requires=UI, difficulty="bounded")
    routed = routing_of(cv, out["expectation"])
    req = routed["requirements"]
    assert req["solution"] == {"value": "unstated", "source": "default",
                               "from": []}, "bounded is scope, not a known answer"
    assert req["scope"] == {"value": "narrow", "source": "compat"}
    assert req["reasoning"] == {"value": "substantial", "source": "compat",
                                "from": []}
    assert routed["required_tier"] == "coding"
    assert routed["tier_sources"] == ["difficulty"]
    assert routed["difficulty"] == "bounded", "the old field is still written"
    run(world, out)
    d = latest_start(cv, out["expectation"])["detail"]
    assert d["selected_model"] == "claude-sonnet-5"
    assert d["selected_effort"] == "medium"


def test_the_schema_says_solution_is_not_size():
    from mentis.worker import ALL_TOOLS
    spec = next(t for t in ALL_TOOLS if t["name"] == "delegate")["inputSchema"]
    props = spec["properties"]
    assert "A small change whose answer is not known is open" in \
        props["solution"]["description"]
    assert "NOT how big it is" in props["reasoning"]["description"]
    assert "LEGACY" in props["difficulty"]["description"]
    assert "never used to pick a model" in props["scope"]["description"]
    assert props["scope"]["enum"] == ["narrow", "broad"]
    for name in ("relation", "relation_ref", "exploratory", "done_when", "scope"):
        assert name in props


# -- relations ------------------------------------------------------------------

def test_implements_an_approved_artifact_takes_its_own_requirements(world,
                                                                   cat_carrying):
    cv = world["cv"]
    design = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                      work="design it", requires=[], solution="open",
                      reasoning="deep")
    run(world, design)
    # THE OWNER'S VERDICT ACCEPTING THE RESULT (round 2: only an owner approval
    # the record holds legitimises the lowering)
    decision = cv.record_act(actor=world["who"]["@brian"], act=E.RESULT_VERDICT,
                             about=[design["expectation"]],
                             caused_by=design["expectation"],
                             detail={"verdict": "accepted", "why": "approved"})
    build = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                     work="build the approved design", requires=[],
                     relation="implements", relation_ref=[decision],
                     solution="specified", reasoning="substantial",
                     references=[reply_of(cv, design["expectation"])])
    req = routing_of(cv, build["expectation"])["requirements"]
    approval = req["relation"].pop("approval")
    assert approval["ref"] == decision and approval["by"] == "owner_verdict"
    req["relation"].pop("detected", None)
    assert req["relation"] == {"value": "implements", "ref": [decision],
                               "source": "stated"}
    assert req["reasoning"] == {"value": "substantial", "source": "stated",
                                "from": []}, "never raised: it is not a continuation"
    assert not build.get("warnings") or not any("raised" in w
                                                for w in build["warnings"])
    run(world, build)
    assert latest_start(cv, build["expectation"])["detail"]["selected_model"] \
        in ("claude-sonnet-5", "gpt-6.1-terra"), "the least sufficient for its own"


def test_mechanical_work_runs_on_the_least_sufficient(world, cat_carrying):
    cv = world["cv"]
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="rename the field everywhere", requires=[],
                   solution="specified", reasoning="light")
    run(world, out)
    start = latest_start(cv, out["expectation"])
    d = start["detail"]
    assert (start["runtime"], d["selected_model"]) in {
        ("claude", "claude-haiku-4-5-20251001"), ("codex", "gpt-6-luna")}
    assert d["selected_effort"] == "low"


def test_browser_required_work_goes_where_the_capability_is(world, cat_carrying):
    cv = world["cv"]
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="check it in the browser", requires=["drive_browser"],
                   solution="specified", reasoning="light")
    run(world, out)
    start = latest_start(cv, out["expectation"])
    assert start["runtime"] == "claude", "codex lacks drive_browser"
    assert start["detail"]["selected_model"] == "claude-haiku-4-5-20251001"
    gated = [c for c in start["detail"]["selection"]["candidates"]
             if c["runtime"] == "codex"]
    assert gated and all(c["outcome"] == "excluded" for c in gated)
    assert "capability gate" in gated[0]["why"]


# -- D4 ---------------------------------------------------------------------------

def _rejected(world, cat_carrying, **args):
    cv = world["cv"]
    first = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                     work="revise the composer mockups", requires=UI,
                     difficulty="bounded", **args)
    run(world, first)
    cv.record_act(actor=world["who"]["@brian"], act=E.RESULT_VERDICT,
                  about=[first["expectation"]], caused_by=first["expectation"],
                  detail={"verdict": "rejected", "why": "an open design problem"})
    return first


def test_a_revision_of_substantively_failed_work_must_restate(world, cat_carrying):
    cv = world["cv"]
    first = _rejected(world, cat_carrying)
    with pytest.raises(NotPermitted) as got:
        delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                 work="try again", requires=UI, relation="revises",
                 relation_ref=[first["expectation"]])
    words = str(got.value)
    assert "failed substantively" in words and "D4" in words
    assert "claude-sonnet-5" in words and "medium" in words
    assert "'unstated'" in words and "'substantial'" in words
    assert "state `solution`" in words
    # only reasoning restated is not enough
    with pytest.raises(NotPermitted):
        delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                 work="try again", requires=UI, relation="revises",
                 relation_ref=[first["expectation"]], reasoning="deep")
    # both restated: recorded, and nothing escalated beyond what was stated
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="try again", requires=UI, relation="revises",
                   relation_ref=[first["expectation"]], solution="open",
                   reasoning="substantial")
    exp = cv._act(out["expectation"])["detail"]
    re = exp["reassessment"]
    assert re["restated"] == {"solution": "open", "reasoning": "substantial"}
    assert re["prior"][0]["expectation"] == first["expectation"]
    assert re["prior"][0]["model"] == "claude-sonnet-5"
    assert re["evidence"]
    deleg = cv._act(out["delegation"])["detail"]
    assert deleg["reassessment"] == re
    req = exp["routing"]["requirements"]
    assert req["reasoning"]["value"] == "substantial"
    assert req["solution"]["value"] == "open"
    run(world, out)
    assert latest_start(cv, out["expectation"])["detail"]["selected_model"] \
        == "claude-opus-5"


def test_the_same_values_may_be_restated(world, cat_carrying):
    cv = world["cv"]
    first = _rejected(world, cat_carrying)
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="try again", requires=UI, relation="revises",
                   relation_ref=[first["expectation"]], solution="specified",
                   reasoning="substantial")
    assert cv._act(out["expectation"])["detail"]["reassessment"]["restated"] \
        == {"solution": "specified", "reasoning": "substantial"}


def test_an_infrastructure_failure_triggers_no_reassessment(world, cat_carrying,
                                                            cat_real):
    from mentis.execution import RunResult
    cv = world["cv"]
    ex = cat_real["ex"]
    ex.script["claude"] = lambda spec: RunResult(
        run_id=spec.run_id, backend=spec.backend, started=False,
        error_kind="backend_unavailable", error="claude is not available")
    first = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                     work="revise it", requires=UI, difficulty="bounded")
    run(world, first)
    ex.script["claude"] = cat_real["perform"]
    rows = E.per_execution(cv, expectation=first["expectation"])
    assert rows and rows[-1]["failure_class"] == "infrastructure"
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="try again", requires=UI, relation="revises",
                   relation_ref=[first["expectation"]])
    detail = cv._act(out["expectation"])["detail"]
    assert "reassessment" not in detail
    req = detail["routing"]["requirements"]
    assert req["reasoning"] == {"value": "substantial", "source": "inherited",
                                "from": [first["expectation"]]}, \
        "inherited, never escalated"


def test_a_review_block_is_substantive_too(world, cat_carrying):
    cv = world["cv"]
    first = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                     work="revise it", requires=UI, difficulty="bounded")
    run(world, first)
    reviewer = cv.create_participant("@Rex")
    review = cv.record_act(actor="owner", act="expectation-recorded",
                           detail={"repository": {"review_of": first["expectation"]}})
    cv.record_act(actor=reviewer, act="review-verdict", about=[review],
                  caused_by=review, detail={"verdict": "block"})
    assert E.substantive_failure(cv, first["expectation"])
    with pytest.raises(NotPermitted):
        delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                 work="again", requires=UI, relation="revises",
                 relation_ref=[first["expectation"]])


# -- the owner composer -------------------------------------------------------------

def test_the_composer_takes_requirements_and_refuses_bad_ones(world, cat_real):
    cv = world["cv"]
    cid = a_conversation(world)
    bad = say(world, cid, "design it", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "design it",
                         "solution": "maybe"}])
    assert "solution is one of" in bad["error"]
    got = say(world, cid, "design it", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "design it",
                         "solution": "open", "reasoning": "deep"}])
    assert "error" not in got, got
    exp = got["expectations"][0]
    req = routing_of(cv, exp)["requirements"]
    assert req["solution"]["source"] == "stated"
    assert routing_of(cv, exp)["required_tier"] == "frontier"
    d = latest_start(cv, exp)["detail"]
    assert d["selected_model"] == "claude-opus-5" and d["selected_effort"] == "high"


def test_the_composer_with_only_a_difficulty_records_compat(world, cat_real):
    cv = world["cv"]
    cid = a_conversation(world)
    got = say(world, cid, "tidy it", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "tidy it",
                         "difficulty": "mechanical"}])
    exp = got["expectations"][0]
    routed = routing_of(cv, exp)
    assert routed["requirements"]["reasoning"] == {"value": "light",
                                                   "source": "compat", "from": []}
    assert routed["required_tier"] == "economy"
