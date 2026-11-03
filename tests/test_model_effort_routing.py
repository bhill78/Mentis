"""Capability, model and effort-aware routing (owner request, Mentis Setup
Installation / Updates #1401, built to brief #1425).

Selection is exercised against a MARS catalogue carrying `routingModels` and
`effectiveDefaultModel`; everything else through the real posting, delegate and
dispatch paths on a fixture Brain, with only the runs scripted.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from mentis.api.errors import RuntimeNotPresent, Unsupported
from mentis.api.types import Address
from mentis.core import routing
from mentis.core.service import MentisService
from mentis.execution import FakeExecution, RunResult, RunSpec
from mentis.web import dispatch as D
from mentis.web.quota import quota_holds
from tests._loop import a_conversation, say, world  # noqa: F401

ALL = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]


def _claude():
    return {"id": "claude", "kind": "acp", "available": True, "reason": None,
            "models": ["haiku", "sonnet", "opus", "opus-alias", "default"],
            "efforts": ["low", "medium", "high", "xhigh", "max", "ultra"],
            "effectiveDefaultModel": "sonnet",
            "routingModels": [
                {"id": "haiku", "tier": "economy", "efforts": ["low", "medium"]},
                {"id": "sonnet", "tier": "coding",
                 "efforts": ["low", "medium", "high"]},
                {"id": "opus", "tier": "frontier",
                 "efforts": ["low", "medium", "high", "xhigh", "max", "ultra",
                             "default"]}],
            "supports": {"mcp": ["stdio"]}}


def _codex():
    return {"id": "codex", "kind": "acp", "available": True, "reason": None,
            "models": ["mini", "code", "max"],
            "efforts": ["minimal", "low", "medium", "high", "xhigh"],
            "effectiveDefaultModel": "code",
            "routingModels": [
                {"id": "mini", "tier": "economy", "efforts": ["minimal", "low"]},
                {"id": "code", "tier": "coding", "efforts": ["medium", "high"]},
                {"id": "max", "tier": "frontier", "efforts": ["xhigh"]}],
            "supports": {"mcp": ["stdio"]}}


def _plain(rid, models=(), efforts=()):
    """A backend with no per-model proof, as Antigravity, Gemini or Kimi."""
    return {"id": rid, "kind": "acp", "available": True, "reason": None,
            "models": list(models), "efforts": list(efforts),
            "supports": {"mcp": ["stdio"]}}


def _catalogue():
    return [_claude(), _codex(), _plain("antigravity", ["argon"], ["low"]),
            _plain("gemini", ["gem"])]


def _svc(tmp_path, backends=None, capacity=None):
    return MentisService(str(tmp_path / "instances"),
                         execution=FakeExecution(
                             _catalogue() if backends is None else backends,
                             capacity=capacity))


def _hold(model=None, until=600):
    now = time.time()
    return {"until": now + until, "why": "held", "model": model, "since": now,
            "basis": "act-1"}


def _holds(**by_runtime):
    return {rt: {**scopes[0], "scopes": scopes}
            for rt, scopes in by_runtime.items()}


# -- the tier ------------------------------------------------------------------

@pytest.mark.parametrize("word,tier", [
    ("mechanical", "economy"), ("bounded", "coding"), ("routine", "coding"),
    ("complex", "frontier"), ("architecture", "frontier"),
    ("debugging", "frontier")])
def test_an_explicit_difficulty_implies_its_tier(word, tier):
    assert routing.required_tier(difficulty=word) == (tier, ["difficulty"])


@pytest.mark.parametrize("word", ["ordinary", "default", "trivial", "hard", None])
def test_a_legacy_difficulty_alone_implies_nothing(word):
    assert routing.required_tier(difficulty=word) == (None, [])


def test_precedence_review_and_authority_over_workflow_and_advisory_over_difficulty():
    both = dict(difficulty="complex", workflow_tier="economy",
                advisory_tier="coding")
    # the stronger of Workflow and advisory wins, and difficulty does not
    assert routing.required_tier(**both) == ("coding", ["advisory"])
    assert routing.required_tier(difficulty="complex", workflow_tier="economy") \
        == ("economy", ["workflow_default"])
    assert routing.required_tier(difficulty="mechanical", advisory_tier="frontier",
                                 workflow_tier="frontier") \
        == ("frontier", ["workflow_default", "advisory"])
    # review and authority beat all of it
    assert routing.required_tier(**both, review=True) == ("frontier", ["review"])
    assert routing.required_tier(**both, authority_sensitive=True) \
        == ("frontier", ["authority_sensitive"])


def test_only_canonical_efforts_and_tagged_models_are_tuples():
    rows = routing.tuples_of({"routingModels": [
        {"id": "a", "tier": "frontier", "efforts": ["max", "ultra", "low", "default"]},
        {"id": "b", "tier": "frontier", "efforts": ["ultra", "default"]},
        {"id": "c", "tier": "mystery", "efforts": ["low"]},
        {"id": "", "tier": "coding", "efforts": ["low"]},
        "nonsense"]})
    assert rows == [{"model": "a", "tier": "frontier", "efforts": ["low", "max"]}]
    assert routing.EFFORT_ORDER == tuple(ALL)


# -- automatic selection -------------------------------------------------------

@pytest.mark.parametrize("tier,model,effort", [
    ("economy", "haiku", "low"), ("coding", "sonnet", "medium"),
    ("frontier", "opus", "high")])
def test_a_tier_selects_the_least_sufficient_tuple(tmp_path, tier, model, effort):
    svc = _svc(tmp_path, [_claude()])
    sel = svc.execution_select(tier=tier, tier_sources=("difficulty",))
    assert (sel.runtime, sel.model, sel.requested_effort) == ("claude", model, effort)
    route = sel.inputs["routing"]
    assert route["required_tier"] == tier and route["selected_tier"] == tier
    assert route["tier_sources"] == ["difficulty"]
    assert route["tier_unfulfilled"] is None
    assert sel.inputs["effective_model"] == model


def test_the_least_advertised_effort_at_or_above_the_target(tmp_path):
    sel = _svc(tmp_path, [_codex()]).execution_select(tier="frontier")
    assert (sel.model, sel.requested_effort) == ("max", "xhigh")


def test_the_lower_effort_wins_across_runtimes(tmp_path):
    # claude's opus at high, codex's max at xhigh: the same tier, less effort.
    sel = _svc(tmp_path).execution_select(tier="frontier")
    assert (sel.runtime, sel.model, sel.requested_effort) == ("claude", "opus", "high")


def test_explicit_only_values_are_never_chosen_automatically(tmp_path):
    only_odd = {**_plain("odd", ["x"]), "routingModels": [
        {"id": "x", "tier": "frontier", "efforts": ["ultra", "default"]}]}
    svc = _svc(tmp_path, [only_odd, _claude()])
    sel = svc.execution_select(tier="frontier")
    assert sel.runtime == "claude" and sel.requested_effort not in ("ultra", "default")
    for _ in range(3):
        assert svc.execution_select(tier="coding").model != "opus-alias"


def test_capability_filtering_comes_before_tuples(tmp_path):
    lacks = {**_claude(), "lacks": {"build_ui": "measured"}}
    can = {**_codex(), "capabilities": ["build_ui"]}
    sel = _svc(tmp_path, [lacks, can]).execution_select(
        tier="coding", requires=("build_ui",))
    assert sel.runtime == "codex" and sel.model == "code"
    assert sel.inputs["routing"]["considered"][0]["runtime"] == "codex"


def test_a_model_hold_falls_to_the_sibling_and_a_runtime_hold_to_another(tmp_path):
    svc = _svc(tmp_path)
    # sonnet held: the other runtime's coding tuple, before anything stronger
    sel = svc.execution_select(tier="coding", holds=_holds(claude=[_hold("sonnet")]))
    assert (sel.runtime, sel.model) == ("codex", "code")
    # the whole of claude held: codex
    sel = svc.execution_select(tier="economy", holds=_holds(claude=[_hold()]))
    assert sel.runtime == "codex"
    # every coding model held: escalates to what is adequate, never down
    sel = svc.execution_select(tier="coding", holds=_holds(
        claude=[_hold("sonnet")], codex=[_hold("code")]))
    assert routing.tier_rank(sel.inputs["routing"]["selected_tier"]) \
        >= routing.tier_rank("coding")
    assert sel.model in ("opus", "max")


def test_automatic_selection_with_nothing_adequate_is_refused_not_lowered(tmp_path):
    economy = {**_plain("cheap", ["a"]), "routingModels": [
        {"id": "a", "tier": "economy", "efforts": ["low", "high"]}]}
    with pytest.raises(Unsupported) as got:
        _svc(tmp_path, [economy, _plain("antigravity")]).execution_select(
            tier="frontier")
    words = str(got.value)
    assert "no adequate model and effort for tier frontier" in words
    assert "not lowered" in words and "antigravity" in words
    # and every adequate tuple held is the same refusal, saying which
    with pytest.raises(Unsupported, match="opus .*held"):
        _svc(tmp_path, [_claude()]).execution_select(
            tier="frontier", holds=_holds(claude=[_hold("opus")]))


def test_no_tuples_anywhere_is_the_legacy_path_said(tmp_path):
    svc = _svc(tmp_path, [_plain("antigravity"), _plain("kimi-k3")])
    sel = svc.execution_select(tier="frontier", tier_sources=("review",))
    assert sel.model is None and sel.requested_effort is None
    route = sel.inputs["routing"]
    assert route["tier_unfulfilled"] == "no_catalogue_metadata"
    assert route["required_tier"] == "frontier"


def test_tuples_only_on_a_named_only_runtime_do_not_activate_routing(tmp_path):
    gem = {**_plain("gemini", ["g"]), "routingModels": [
        {"id": "g", "tier": "frontier", "efforts": ["high"]}]}
    sel = _svc(tmp_path, [gem, _plain("antigravity")]).execution_select(tier="frontier")
    assert sel.runtime == "antigravity"
    assert sel.inputs["routing"]["tier_unfulfilled"] == "no_catalogue_metadata"


def test_no_tier_selects_as_it_always_did(tmp_path):
    sel = _svc(tmp_path).execution_select()
    assert sel.model is None and sel.requested_effort is None
    assert sel.inputs["routing"]["required_tier"] is None
    assert sel.inputs["routing"]["tier_unfulfilled"] is None


# -- fixed fields --------------------------------------------------------------

def test_a_tier_fills_only_inside_a_fixed_runtime(tmp_path):
    sel = _svc(tmp_path).execution_select(runtime="codex", tier="frontier")
    assert (sel.runtime, sel.model, sel.requested_effort) == ("codex", "max", "xhigh")


def test_a_fixed_runtime_with_nothing_adequate_runs_and_records_it(tmp_path):
    sel = _svc(tmp_path).execution_select(runtime="antigravity", tier="frontier")
    assert (sel.runtime, sel.model, sel.requested_effort) == ("antigravity", None, None)
    route = sel.inputs["routing"]
    assert route["tier_unfulfilled"] == "fixed_binding"
    assert "antigravity" in route["tier_unfulfilled_because"]
    assert sel.runtime == "antigravity", "a fixed field is never replaced"


def test_a_named_model_is_fixed_and_the_tier_fills_only_its_effort(tmp_path):
    sel = _svc(tmp_path).execution_select(model="opus", tier="coding")
    assert (sel.runtime, sel.model, sel.requested_effort) == ("claude", "opus", "medium")
    # an untagged alias is honoured exactly and the tier cannot be met on it
    sel = _svc(tmp_path).execution_select(model="opus-alias", tier="frontier")
    assert (sel.runtime, sel.model) == ("claude", "opus-alias")
    assert sel.requested_effort is None
    assert sel.inputs["routing"]["tier_unfulfilled"] == "fixed_binding"


def test_a_named_model_below_the_tier_stays_named(tmp_path):
    sel = _svc(tmp_path).execution_select(model="haiku", tier="frontier")
    assert sel.model == "haiku"
    assert sel.inputs["routing"]["tier_unfulfilled"] == "fixed_binding"


def test_a_named_model_nobody_offers_is_refused(tmp_path):
    with pytest.raises(Unsupported, match="refusing rather than running a different"):
        _svc(tmp_path).execution_select(model="nope")


def test_a_named_model_whose_offerers_are_all_held_runs_on_the_best_disclosed(tmp_path):
    second = {**_codex(), "models": ["sonnet"]}
    sel = _svc(tmp_path, [_claude(), second]).execution_select(
        model="sonnet", holds=_holds(claude=[_hold("sonnet")],
                                     codex=[_hold("sonnet")]))
    assert sel.model == "sonnet" and sel.runtime in ("claude", "codex")
    assert any("run as named" in d for d in sel.inputs["disclosed"])


def test_a_named_effort_alone_does_not_constrain_placement(tmp_path):
    # no tuple on either has `ultra`-adjacent support for antigravity: exact anyway
    sel = _svc(tmp_path, [_plain("antigravity", ["argon"], ["low"])]).execution_select(
        effort="max")
    assert (sel.runtime, sel.requested_effort) == ("antigravity", "max")
    assert sel.inputs["effort_support"] == "unadvertised"
    assert any("passed exactly as named" in d for d in sel.inputs["disclosed"])
    # nothing listed at all: unknown, and still exact
    sel = _svc(tmp_path, [_plain("kimi-k3")]).execution_select(effort="ultra")
    assert sel.requested_effort == "ultra" and sel.inputs["effort_support"] == "unknown"


def test_a_named_effort_with_a_tier_keeps_the_effort_and_fills_the_model(tmp_path):
    sel = _svc(tmp_path, [_claude()]).execution_select(effort="xhigh", tier="frontier")
    assert (sel.model, sel.requested_effort) == ("opus", "xhigh")
    assert sel.inputs["routing"]["tier_unfulfilled"] is None
    # below the target: kept, and said
    sel = _svc(tmp_path, [_claude()]).execution_select(effort="low", tier="frontier")
    assert (sel.model, sel.requested_effort) == ("opus", "low")
    assert sel.inputs["routing"]["tier_unfulfilled"] == "fixed_binding"
    # no compatible tuple: legacy placement, the effort exact, nothing replaced
    sel = _svc(tmp_path, [_claude()]).execution_select(effort="ultra", tier="frontier")
    assert (sel.model, sel.requested_effort) == (None, "ultra")
    assert sel.inputs["routing"]["tier_unfulfilled"] == "fixed_binding"


def test_a_named_runtime_runs_exactly_with_everything_disclosed(tmp_path):
    svc = _svc(tmp_path)
    sel = svc.execution_select(runtime="claude", model="retired", effort="turbo",
                               holds=_holds(claude=[_hold()]))
    assert (sel.runtime, sel.model, sel.requested_effort) == (
        "claude", "retired", "turbo")
    said = " | ".join(sel.inputs["disclosed"])
    assert "not in claude's catalogue" in said and "not substituted" in said
    assert "'turbo' is unadvertised" in said


def test_a_named_runtime_unavailable_or_lacking_is_still_refused(tmp_path):
    down = {**_claude(), "available": False, "reason": "signed out"}
    lacks = {**_codex(), "lacks": {"build_ui": "measured"}}
    svc = _svc(tmp_path, [down, lacks])
    with pytest.raises(RuntimeNotPresent, match="signed out"):
        svc.execution_select(runtime="claude", tier="frontier")
    with pytest.raises(Unsupported, match="can be given this work"):
        svc.execution_select(runtime="codex", requires=("build_ui",),
                             tier="frontier")


# -- review --------------------------------------------------------------------

def test_review_prefers_another_runtime_among_adequate_tuples(tmp_path):
    sel = _svc(tmp_path).execution_select(tier="frontier", avoid="claude")
    assert (sel.runtime, sel.model, sel.requested_effort) == ("codex", "max", "xhigh")
    assert "disclosed" not in sel.inputs


def test_review_uses_the_author_when_it_is_the_only_adequate_tuple(tmp_path):
    sel = _svc(tmp_path, [_claude(), _plain("antigravity")]).execution_select(
        tier="frontier", avoid="claude")
    assert (sel.runtime, sel.model) == ("claude", "opus")
    assert any("not independent by runtime" in d for d in sel.inputs["disclosed"])


def test_review_independence_never_refuses_where_a_held_other_leaves_the_author(tmp_path):
    sel = _svc(tmp_path).execution_select(tier="frontier", avoid="claude",
                                          holds=_holds(codex=[_hold("max")]))
    assert sel.runtime == "claude"
    assert any("not independent by runtime" in d for d in sel.inputs["disclosed"])


# -- holds and the model that would run ----------------------------------------

def test_a_hold_is_matched_by_runtime_and_exact_model():
    on = MentisService._hold_on
    now = time.time()
    model_hold = _holds(a=[_hold("x")])
    assert on("a", "x", model_hold, now) is not None
    assert on("a", "y", model_hold, now) is None
    assert on("b", "x", model_hold, now) is None
    wide = _holds(a=[_hold()])
    assert on("a", "x", wide, now) is not None and on("a", None, wide, now) is not None
    both = _holds(a=[_hold("x", 100), _hold("y", 900)])
    assert on("a", "y", both, now)["model"] == "y"
    assert on("a", "z", both, now) is None
    assert on("a", "x", _holds(a=[_hold("x", -1)]), now) is None


def test_an_unknown_default_is_read_conservatively_and_a_known_one_exactly():
    on = MentisService._hold_on
    now = time.time()
    held = _holds(a=[_hold("x")])
    assert on("a", None, held, now) is not None, "the hidden default may be x"
    assert on("a", None, held, now, default="y") is None
    assert on("a", None, held, now, default="x") is not None


def test_legacy_selection_treats_an_unknown_default_conservatively(tmp_path):
    unknown = _plain("a"), _plain("b")
    sel = _svc(tmp_path, list(unknown)).execution_select(
        holds=_holds(a=[_hold("some-model")]))
    assert sel.runtime == "b"
    # the known default not being the held model, it is free
    known = [{**_plain("a"), "effectiveDefaultModel": "other"}]
    sel = _svc(tmp_path, known).execution_select(holds=_holds(a=[_hold("some-model")]))
    assert sel.runtime == "a"


def test_a_named_runtime_with_no_model_runs_and_discloses_a_model_hold(tmp_path):
    sel = _svc(tmp_path, [_plain("a")]).execution_select(
        runtime="a", holds=_holds(a=[_hold("some-model")]))
    assert sel.runtime == "a" and sel.model is None
    assert any("not substituted" in d for d in sel.inputs["disclosed"])


def _failure(cv, start, runtime="codex", **evidence):
    return cv.record_act(actor="tester", act="delivery-failed", runtime=runtime,
                         caused_by=start, because="quota",
                         detail={"terminal": "failed", "runtime_evidence": {
                             "error_kind": "rate_limited", **evidence}})


def _start(cv, model=None, runtime="codex", effective=None):
    return cv.record_act(actor="tester", act="execution-started", runtime=runtime,
                         because="a run",
                         detail={"selected_model": model,
                                 **({"effective_model": effective}
                                    if effective else {})})


def _done(cv, start, runtime="codex"):
    return cv.record_act(actor="tester", act="result-returned", runtime=runtime,
                         caused_by=start, because="done",
                         detail={"terminal": "reported_done"})


def _scopes(cv, runtime="codex"):
    return {s["model"] for s in (quota_holds(cv).get(runtime) or {}).get("scopes", ())}


def _tick():
    time.sleep(0.02)


def test_a_failure_holds_the_model_its_start_recorded_or_else_the_runtime(world):
    cv = world["cv"]
    _failure(cv, _start(cv, "code"))
    assert _scopes(cv) == {"code"}
    assert quota_holds(cv)["codex"]["model"] == "code"
    _tick()
    _failure(cv, _start(cv, None, runtime="claude"), runtime="claude")
    assert _scopes(cv, "claude") == {None}
    # the default a run was recorded as using counts as known
    _tick()
    _failure(cv, _start(cv, None, runtime="kimi", effective="k2"), runtime="kimi")
    assert _scopes(cv, "kimi") == {"k2"}


def test_sibling_holds_stand_side_by_side(world):
    cv = world["cv"]
    _failure(cv, _start(cv, "code"))
    _tick()
    _failure(cv, _start(cv, "max"))
    _tick()
    _failure(cv, _start(cv, None))
    assert _scopes(cv) == {"code", "max", None}


def test_a_concrete_success_clears_its_model_and_the_runtime_not_a_sibling(world):
    cv = world["cv"]
    _failure(cv, _start(cv, "code"))
    _tick()
    _failure(cv, _start(cv, "max"))
    _tick()
    _failure(cv, _start(cv, None))
    _tick()
    _done(cv, _start(cv, "code"))
    assert _scopes(cv) == {"max"}


def test_an_unknown_success_clears_only_the_runtime_wide_hold(world):
    cv = world["cv"]
    _failure(cv, _start(cv, "code"))
    _tick()
    _failure(cv, _start(cv, None))
    _tick()
    _done(cv, _start(cv, None))
    assert _scopes(cv) == {"code"}


def test_a_success_before_the_failure_clears_nothing(world):
    cv = world["cv"]
    earlier = _start(cv, "code")
    _tick()
    _failure(cv, _start(cv, "code"))
    _tick()
    _done(cv, earlier)
    assert _scopes(cv) == {"code"}


def test_holds_expire_scope_by_scope(world):
    cv = world["cv"]
    far = time.time() + 7200
    failed = _failure(cv, _start(cv, "code"), resets_at=far)
    _tick()
    _failure(cv, _start(cv, "max"))
    at = cv._act(failed)["at"]
    assert _scopes(cv) == {"code", "max"}
    later = quota_holds(cv, now=at + 4000)["codex"]
    assert [s["model"] for s in later["scopes"]] == ["code"]
    assert quota_holds(cv, now=far + 1) == {}


# -- handles -------------------------------------------------------------------

def _summon(svc, selection, participant="p"):
    return svc.agents_summon(Address(name="a", context="c"), selection,
                             workspace=".", participant=participant)


def test_a_handle_is_reused_only_for_the_same_model_and_effort(tmp_path):
    svc = _svc(tmp_path)

    def again(**kw):
        inst = _summon(svc, svc.execution_select(runtime="claude", **kw))
        svc.agents_perform(inst.instance_id, "x", run=None)
        return inst.instance_id

    named = again(model="opus")
    assert again(model="opus") == named
    assert again() != named, "nothing named must not reuse a handle holding opus"
    assert again(model="opus", effort="high") != named
    # two unset values are equal, and the effective default is what would run
    unset = again()
    assert again() == unset
    assert again(model="sonnet") == unset, "sonnet is this runtime's default"
    assert again(tier="frontier") not in (named, unset)


def test_a_tier_chosen_tuple_does_not_reuse_a_lower_one(tmp_path):
    svc = _svc(tmp_path, [_claude()])
    low = _summon(svc, svc.execution_select(tier="economy"))
    svc.agents_perform(low.instance_id, "x", run=None)
    high = _summon(svc, svc.execution_select(tier="frontier"))
    assert high.instance_id != low.instance_id
    assert (high.requested_model, high.requested_effort) == ("opus", "high")


# -- MARS's structured option --------------------------------------------------

def _spec():
    return RunSpec(run_id="r", backend="claude", prompt="x", workspace=".")


def _option_error(option="model", offered=("a", "b")):
    from acp import RequestError
    return RequestError(-32603, "claude does not offer model 'x'", {"mars": {
        "kind": "backend_unavailable",
        **({"option": option} if option is not None else {}),
        **({"offered": list(offered)} if offered is not None else {})}})


def test_the_option_survives_the_failed_result_path():
    from mentis.execution.mars import MarsExecution
    res = MarsExecution._failed_result(_spec(), 0.0, _option_error("effort"))
    assert (res.option, res.offered) == ("effort", ["a", "b"])
    assert res.error_kind == "backend_unavailable"


def test_the_option_survives_a_refused_session_new():
    from mentis.execution.mars import MarsExecution

    class Conn:
        async def new_session(self, **kw):
            raise _option_error("model")

    ex = MarsExecution(["mars"])

    async def connected():
        return Conn()
    ex._ensure_connection = connected
    res = asyncio.run(ex._perform(_spec(), None, time.time()))
    assert res.started is False and res.error_kind == "backend_unavailable"
    assert (res.option, res.offered) == ("model", ["a", "b"])


@pytest.mark.parametrize("bad", ["Model", "models", "", 1, None, True])
def test_only_the_two_exact_options_count(bad):
    from mentis.execution.mars import MarsExecution
    res = MarsExecution._failed_result(_spec(), 0.0, _option_error(bad))
    assert res.option is None and res.offered is None


def test_a_configuration_failure_carries_no_option_whatever_it_says():
    from mentis.execution.mars import MarsExecution
    res = MarsExecution._failed_result(_spec(), 0.0, _option_error(None, ("a",)))
    assert res.option is None and res.offered is None


def test_option_and_offered_reach_the_evidence():
    from mentis.core.service import _outcome_of
    from mentis.api.types import Liveness, Instance, Observed
    inst = Instance(instance_id="i", address=Address(name="a"), participant="p",
                    runtime="claude", machine_id="m", session_ref=None,
                    requested_model="x", actual_model=Observed.unknown("n"),
                    requested_effort=None, actual_effort=Observed.unknown("n"),
                    liveness=Liveness.BUSY, started_at=0.0, workspace=".")
    res = RunResult(run_id="i", backend="claude", started=False,
                    error_kind="backend_unavailable", error="nope",
                    option="model", offered=["a"])
    outcome, _ = _outcome_of(inst, res)
    assert outcome.evidence["option"] == "model"
    assert outcome.evidence["offered"] == ["a"]
    plain, _ = _outcome_of(inst, RunResult(run_id="i", backend="claude",
                                           started=False, error_kind="backend_error"))
    assert "option" not in plain.evidence and "offered" not in plain.evidence


@pytest.mark.parametrize("evidence,sources,want", [
    ({"option": "model"}, {"model": "tier"}, "model_unavailable/catalogue_changed"),
    ({"option": "effort"}, {"effort": "tier"}, "effort_unavailable/catalogue_changed"),
    ({"option": "model"}, {"model": "named"}, None),
    ({"option": "effort"}, {"effort": "named"}, None),
    ({"option": "model"}, {"model": "runtime-default"}, None),
    ({"error": "does not offer model", "error_kind": "backend_unavailable"},
     {"model": "tier"}, None),
    ({}, {"model": "tier"}, None), (None, {"model": "tier"}, None),
])
def test_what_counts_as_the_catalogue_changing(evidence, sources, want):
    assert D.option_failure(evidence, sources) == want


# -- through the real paths ----------------------------------------------------

@pytest.fixture()
def real(world, monkeypatch):
    """Real posting, delegate and dispatch over the routing catalogue; each run
    answers `script(spec)` or else reports done. Grants are kept."""
    import mentis.web as web
    st = world["state"]
    svc = st.agents
    svc.execution._backends = _catalogue()
    grants, scripted = [], {}

    def perform(spec):
        grants.append(svc.authority.grant_for(svc.authority.grant_of(spec.run_id),
                                              st.path))
        if scripted.get("fn"):
            got = scripted["fn"](spec)
            if got is not None:
                return got
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done", started_at=now,
                         finished_at=now)

    svc.execution.script = {b["id"]: perform for b in _catalogue()}
    monkeypatch.setattr(web, "dispatch_soon", lambda s, **kw: D.dispatch(st, **kw))
    return {"grants": grants, "scripted": scripted, "ex": svc.execution}


def _post(world, cid, **spec):
    who = spec.pop("participant", world["who"]["@Ada"])
    reply = spec.pop("replies_to", None)
    got = say(world, cid, "do the work", action="ask-participant",
              **({"replies_to": reply} if reply else {}),
              dispatch=[{"participant": who, "work": "do the work", **spec}])
    assert "error" not in got, got
    return got


def _runs(cv, expectation):
    return [a for a in cv.history(caused_by=expectation)
            if a["act"] == "execution-started"]


def _latest(cv, expectation):
    got = _runs(cv, expectation)
    assert got, "the run did not start"
    return max(got, key=lambda a: a["at"])


def _reply_of(cv, expectation):
    """The Turn the latest run of this request returned on."""
    start = _latest(cv, expectation)["id"]
    return next(a["turn"] for a in cv.history(caused_by=start)
                if a["act"] == "result-returned")


def _delegate(world, grant, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "delegate", args, grant)


def _run(world, out):
    spec = out["dispatch"]
    return D.dispatch(world["state"], conversation=out["conversation"],
                      turn=spec.get("turn") or out["turn"],
                      participant=spec["participant"], work=spec["work"],
                      persona=spec.get("persona"), runtime=spec.get("runtime"),
                      model=spec.get("model"), effort=spec.get("effort"),
                      requires=spec.get("requires") or (),
                      expectation=out["expectation"])


@pytest.mark.parametrize("field,value,rest", [
    ("runtime", "claude", {"model": None, "effort": None}),
    ("model", "opus", {"runtime": None, "effort": None}),
    ("effort", "high", {"runtime": None, "model": None})])
def test_an_owner_post_binds_each_field_it_names(world, real, field, value, rest):
    cv = world["cv"]
    cid = a_conversation(world)
    got = _post(world, cid, **{field: value})
    exp = got["expectations"][0]
    said = cv._act(exp)["detail"]["constraints"]
    assert said["field_sources"] == {field: "named"}
    assert said["constraint_bases"] == {field: got["turn"]}
    started = _latest(cv, exp)["detail"]
    row = started["field_binding"][field]
    assert row["source"] == "named" and row["binding"] == "owner-bound_claimed"
    assert row["basis"] == got["turn"] and row["supplied_by"] == world["who"]["@brian"]
    assert started["field_sources"][field] == "named"
    for other in rest:
        assert started["field_binding"][other]["binding"] != "owner-bound_claimed"
    options = real["ex"].performed[-1].options
    if field != "runtime":
        assert options[field] == value


def test_a_post_by_somebody_else_is_carrier_bound(world, real):
    from tests._loop import post
    cv = world["cv"]
    cid = a_conversation(world)
    vera = world["who"]["@Vera"]
    cv.join(vera, cid)
    got = post(world, f"/api/conversations/{cid}/turns",
               {"author": vera, "text": "do it", "action": "ask-participant",
                "dispatch": [{"participant": world["who"]["@Ada"], "work": "do it",
                              "model": "opus"}]})
    assert "error" not in got, got
    row = _latest(cv, got["expectations"][0])["detail"]["field_binding"]["model"]
    assert row["binding"] == "carrier-bound" and row["basis"] == got["turn"]


def test_a_participant_default_stays_a_preference_though_the_post_has_a_basis(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    cv.declare_runtime_default(world["who"]["@Ada"], "codex", by=world["who"]["@brian"])
    got = _post(world, cid)
    exp = got["expectations"][0]
    said = cv._act(exp)["detail"]["constraints"]
    assert said["field_sources"] == {"runtime": "participant-default"}
    assert "runtime" not in (said.get("constraint_bases") or {})
    row = _latest(cv, exp)["detail"]["field_binding"]["runtime"]
    assert row["source"] == "participant-default" and row["binding"] == "preference"


def test_a_participant_default_with_nothing_adequate_yields_to_the_tier(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    cv.declare_runtime_default(world["who"]["@Ada"], "antigravity",
                               by=world["who"]["@brian"])
    got = _post(world, cid, difficulty="complex")
    started = _latest(cv, got["expectations"][0])
    assert started["runtime"] == "claude"
    assert started["detail"]["selected_model"] == "opus"
    assert started["detail"]["field_binding"]["runtime"]["source"] == "tier"
    # with no routing asked for, the default binds as it always did
    plain = _post(world, cid)
    assert _latest(cv, plain["expectations"][0])["runtime"] == "antigravity"


def test_a_participant_default_with_something_adequate_stays(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    cv.declare_runtime_default(world["who"]["@Ada"], "codex", by=world["who"]["@brian"])
    started = _latest(cv, _post(world, cid, difficulty="complex")["expectations"][0])
    assert started["runtime"] == "codex"
    assert started["detail"]["selected_model"] == "max"
    assert started["detail"]["selected_effort"] == "xhigh"


def test_every_dispatch_record_says_what_was_selected_and_why(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    d = _latest(cv, _post(world, cid, difficulty="mechanical")["expectations"][0])["detail"]
    assert (d["selected_runtime"], d["selected_model"], d["selected_effort"]) == (
        "claude", "haiku", "low")
    assert d["effective_model"] == "haiku"
    assert d["routing"]["required_tier"] == "economy"
    assert d["routing"]["tier_sources"] == ["difficulty"]
    assert d["routing"]["selected_tier"] == "economy"
    assert d["field_sources"] == {"runtime": "tier", "model": "tier", "effort": "tier"}
    assert d["field_binding"]["model"]["binding"] == "routed"
    assert "least sufficient" in d["selection_because"]
    assert real["ex"].performed[-1].options == {"model": "haiku", "effort": "low"}


def test_no_signal_passes_no_option_and_records_no_tier(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    d = _latest(cv, _post(world, cid)["expectations"][0])["detail"]
    assert real["ex"].performed[-1].options == {}
    assert d["selected_model"] is None and "routing" not in d
    assert d["field_binding"]["model"] == {"source": "runtime-default", "binding": None}
    assert d["field_binding"]["runtime"]["binding"] == "automatic"
    assert d["effective_model"] in ("sonnet", "code", None)


def test_ordinary_difficulty_records_no_tier(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    d = _latest(cv, _post(world, cid, difficulty="ordinary")["expectations"][0])["detail"]
    assert "routing" not in d and real["ex"].performed[-1].options == {}


def test_a_nothing_adequate_failure_is_recorded_before_anything_starts(world, real):
    cv = world["cv"]
    real["ex"]._backends = [{**_plain("cheap", ["a"]), "routingModels": [
        {"id": "a", "tier": "economy", "efforts": ["low"]}]}]
    cid = a_conversation(world)
    exp = _post(world, cid, authority_sensitive=True)["expectations"][0]
    assert not _runs(cv, exp) and not real["ex"].performed
    failed = [a for a in cv.history(caused_by=exp) if a["act"] == "delivery-failed"]
    assert len(failed) == 1
    assert "no adequate model and effort" in failed[0]["because"]
    assert failed[0]["detail"]["requested"]["routing"]["required_tier"] == "frontier"


def test_an_unknown_advisory_tier_or_non_boolean_is_refused_at_the_post(world, real):
    cid = a_conversation(world)
    for bad, word in (({"advisory_tier": "turbo"}, "advisory_tier"),
                      ({"authority_sensitive": "yes"}, "authority_sensitive")):
        got = say(world, cid, "do it", action="ask-participant",
                  dispatch=[{"participant": world["who"]["@Ada"], "work": "x", **bad}])
        assert word in got["error"]
    assert not real["ex"].performed


# -- delegation: provenance and advice -----------------------------------------

@pytest.fixture()
def carrying(world, real):
    """A real run of the steward, carrying an owner's request, and a child's
    grant one level further down."""
    cv = world["cv"]
    cid = a_conversation(world)
    asked = _post(world, cid, participant=world["steward"], coordinate=True)
    grant = real["grants"][-1]
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=world["who"]["@brian"])
    return {"cid": cid, "grant": grant, "bob": bob, "turn": asked["turn"],
            "parent": asked["expectations"][0]}


def test_a_carriers_named_field_is_carrier_bound(world, carrying):
    cv = world["cv"]
    out = _delegate(world, carrying["grant"], participant=carrying["bob"], work="x",
                    model="opus")
    said = cv._act(out["expectation"])["detail"]["constraints"]
    assert said["field_sources"] == {"model": "named"}
    _run(world, out)
    row = _latest(cv, out["expectation"])["detail"]["field_binding"]["model"]
    assert row["binding"] == "carrier-bound"
    assert row["supplied_by"] == cv.expectation_state(out["expectation"])["requested_by"]


def test_the_owners_basis_binds_only_the_field_it_is_cited_for(world, carrying):
    cv = world["cv"]
    owner = carrying["turn"]
    out = _delegate(world, carrying["grant"], participant=carrying["bob"], work="x",
                    runtime="claude", model="opus", constraint_basis=owner)
    _run(world, out)
    rows = _latest(cv, out["expectation"])["detail"]["field_binding"]
    assert rows["runtime"]["binding"] == "owner-bound_claimed"
    assert rows["runtime"]["basis"] == owner
    assert rows["model"]["binding"] == "carrier-bound", (
        "a carrier cannot make a model the owner's by citing the runtime's basis")


def test_a_model_only_owner_basis(world, carrying):
    cv = world["cv"]
    owner = carrying["turn"]
    out = _delegate(world, carrying["grant"], participant=carrying["bob"], work="x",
                    model="opus", effort="low", constraint_bases={"model": owner})
    _run(world, out)
    rows = _latest(cv, out["expectation"])["detail"]["field_binding"]
    assert rows["model"]["binding"] == "owner-bound_claimed"
    assert rows["effort"]["binding"] == "carrier-bound"


@pytest.mark.parametrize("bases,why", [
    ({"model": "ent-doesnotexist"}, "not a Turn"),
    ({"tier": "ent-x"}, "holds runtime, model and effort"),
    ({"effort": "ent-x"}, "does not name"),
    ("ent-x", "holds a Turn per field")])
def test_a_bad_field_basis_is_refused(world, carrying, bases, why):
    from mentis.worker import NotPermitted
    with pytest.raises(NotPermitted, match=why):
        _delegate(world, carrying["grant"], participant=carrying["bob"], work="x",
                  model="opus", constraint_bases=bases)


def test_a_nested_carrier_cannot_cite_a_remote_owner_and_retries_carrier_bound(
        world, carrying, real):
    from mentis.worker import NotPermitted
    cv = world["cv"]
    out = _delegate(world, carrying["grant"], participant=carrying["bob"], work="x")
    _run(world, out)
    nested = real["grants"][-1]
    assert nested["expectation"] == out["expectation"]
    carl = cv.create_participant("@Carl")
    cv.join(carl, carrying["cid"], attributed_to=world["who"]["@brian"])
    before = len(cv.history())
    with pytest.raises(NotPermitted, match="not a Turn by the person who asked"):
        _delegate(world, nested, participant=carl, work="y", model="opus",
                  constraint_bases={"model": carrying["turn"]})
    assert len(cv.history()) == before, "a refusal writes nothing"
    # refused rather than softened: the same delegation, without the claim
    again = _delegate(world, nested, participant=carl, work="y", model="opus")
    _run(world, again)
    row = _latest(cv, again["expectation"])["detail"]["field_binding"]["model"]
    assert row["binding"] == "carrier-bound" and "basis" not in row


def test_an_older_owner_request_with_no_sources_reads_carrier_bound(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    got = _post(world, cid, model="opus", runtime="claude")
    turn = got["turn"]
    said = {"runtime": "claude", "model": "opus", "supplied_by": world["who"]["@brian"],
            "basis": turn, "source": "named"}
    from types import SimpleNamespace
    rows = D.field_provenance(
        cv, said, {"runtime": "claude", "source": "named"}, model="opus", effort=None,
        selection=SimpleNamespace(runtime="claude", model="opus",
                                  requested_effort=None, inputs={}))
    assert rows["runtime"]["binding"] == "carrier-bound"
    assert rows["model"]["binding"] == "carrier-bound"
    assert rows["runtime"]["basis"] == turn, "and the basis is still there to read"


def test_advice_fills_only_what_nobody_named_and_is_recorded_as_advice(world, carrying):
    cv = world["cv"]
    out = _delegate(world, carrying["grant"], participant=carrying["bob"], work="x",
                    advisory_tier="frontier", difficulty="mechanical")
    routed = cv._act(out["expectation"])["detail"]["routing"]
    assert routed["required_tier"] == "frontier" and routed["tier_sources"] == ["advisory"]
    assert routed["advisory_tier"] == "frontier"
    assert routed["advisory_by"] == world["steward"]
    assert routed["difficulty"] == "mechanical"
    _run(world, out)
    d = _latest(cv, out["expectation"])["detail"]
    assert d["selected_model"] == "opus" and d["selected_effort"] == "high"
    assert d["field_binding"]["model"]["binding"] == "advisory"
    # named fields stand
    named = _delegate(world, carrying["grant"], participant=carrying["bob"], work="y",
                      advisory_tier="frontier", model="haiku")
    _run(world, named)
    d = _latest(cv, named["expectation"])["detail"]
    assert d["selected_model"] == "haiku"
    assert d["routing"]["tier_unfulfilled"] == "fixed_binding"


def test_delegate_refuses_unknown_routing_words(world, carrying):
    from mentis.worker import NotPermitted
    for bad, why in (({"advisory_tier": "turbo"}, "advisory_tier"),
                     ({"difficulty": "hard"}, "difficulty"),
                     ({"authority_sensitive": "yes"}, "authority_sensitive")):
        with pytest.raises(NotPermitted, match=why):
            _delegate(world, carrying["grant"], participant=carrying["bob"],
                      work="x", **bad)


def test_authority_sensitive_and_review_of_force_frontier_over_advice(world, carrying):
    cv = world["cv"]
    a = _delegate(world, carrying["grant"], participant=carrying["bob"], work="x",
                  authority_sensitive=True, advisory_tier="economy")
    assert cv._act(a["expectation"])["detail"]["routing"]["tier_sources"] == [
        "authority_sensitive"]
    _run(world, a)
    assert _latest(cv, a["expectation"])["detail"]["selected_effort"] == "high"
    r = _delegate(world, carrying["grant"], participant=carrying["bob"], work="y",
                  review_of=a["expectation"], advisory_tier="economy")
    routed = cv._act(r["expectation"])["detail"]["routing"]
    assert routed["required_tier"] == "frontier" and routed["tier_sources"] == ["review"]
    assert routed["review_of"] == a["expectation"]


def test_a_reviewer_persona_avoids_the_author_at_frontier(world, carrying):
    cv = world["cv"]
    reviewer = cv.define_persona("Reviewer", "Review the work.")
    a = _delegate(world, carrying["grant"], participant=carrying["bob"], work="x",
                  runtime="claude")
    _run(world, a)
    r = _delegate(world, carrying["grant"], participant=carrying["bob"], work="y",
                  review_of=a["expectation"], persona=reviewer)
    _run(world, r)
    started = _latest(cv, r["expectation"])
    assert started["runtime"] == "codex"
    assert started["detail"]["selected_model"] == "max"


# -- Workflow steps ------------------------------------------------------------

def _workflow(world, **row):
    return world["cv"].corpus.create_and_establish(
        kind="workflow",
        body={"name": "Change", "about": "changing", "text": "go",
              "activities": [{"key": "step", "what": "do it", **row}],
              "decisions": [], "done_when": "done", "requires": []},
        attributed_to=world["who"]["@brian"])


@pytest.mark.parametrize("row,field", [
    ({"default_tier": "turbo"}, "default_tier"),
    ({"authority_sensitive": "yes"}, "authority_sensitive")])
def test_workflow_activity_routing_fields_are_validated(world, row, field):
    from mentis.conversation import reference_refusal
    got = reference_refusal(
        world["cv"].corpus, "workflow",
        {"name": "x", "about": "y", "text": "z", "decisions": [], "requires": [],
         "done_when": "w", "activities": [{"key": "k", "what": "w", **row}]})
    assert got and field in got["error"], got


def test_valid_activity_routing_fields_pass_and_are_rendered(world):
    from mentis.conversation import reference_refusal
    cv = world["cv"]
    body = {"name": "x", "about": "y", "text": "z", "decisions": [], "requires": [],
            "done_when": "w", "activities": [
                {"key": "k", "what": "w", "default_tier": "frontier",
                 "authority_sensitive": True}]}
    assert reference_refusal(cv.corpus, "workflow", body) is None
    said = cv._said_activities("ent-x", body["activities"])
    assert "Default tier: frontier" in said and "Authority-sensitive" in said


def test_a_step_default_routes_its_work_and_advice_may_raise_it(world, real):
    cv = world["cv"]
    wf = _workflow(world, default_tier="coding")
    cid = a_conversation(world)
    asked = _post(world, cid, participant=world["steward"], governed=[wf])
    grant = real["grants"][-1]
    assert wf in grant["delivered"]
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=world["who"]["@brian"])
    assert asked
    out = _delegate(world, grant, participant=bob, work="x", activity=f"{wf}#step",
                    difficulty="complex")
    routed = cv._act(out["expectation"])["detail"]["routing"]
    assert routed["required_tier"] == "coding"
    assert routed["tier_sources"] == ["workflow_default"]
    assert routed["workflow_default_tier"] == "coding"
    _run(world, out)
    assert _latest(cv, out["expectation"])["detail"]["selected_model"] in ("sonnet", "code")
    up = _delegate(world, grant, participant=bob, work="y", activity=f"{wf}#step",
                   advisory_tier="frontier")
    assert cv._act(up["expectation"])["detail"]["routing"]["required_tier"] == "frontier"


def test_a_step_marked_authority_sensitive_is_frontier(world, real):
    cv = world["cv"]
    wf = _workflow(world, default_tier="economy", authority_sensitive=True)
    cid = a_conversation(world)
    _post(world, cid, participant=world["steward"], governed=[wf])
    grant = real["grants"][-1]
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=world["who"]["@brian"])
    out = _delegate(world, grant, participant=bob, work="x", activity=f"{wf}#step")
    routed = cv._act(out["expectation"])["detail"]["routing"]
    assert routed["required_tier"] == "frontier"
    assert routed["tier_sources"] == ["authority_sensitive"]


# -- another run of the same request, and work that continues it ----------------

def _again(world, cv, exp):
    """Another run of the same request, as resume and retry start one: naming
    neither a model nor an effort."""
    act = cv._act(exp)
    return D.dispatch(world["state"], conversation=act["conversation"],
                      turn=act["turn"], participant=act["about"][0],
                      work="resuming", expectation=exp, new_instance=True)


def test_the_same_request_again_keeps_its_named_model_and_effort(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    exp = _post(world, cid, model="opus", effort="xhigh")["expectations"][0]
    _again(world, cv, exp)
    assert len(_runs(cv, exp)) == 2
    assert real["ex"].performed[-1].options == {"model": "opus", "effort": "xhigh"}
    rows = _latest(cv, exp)["detail"]["field_binding"]
    assert rows["model"]["binding"] == "owner-bound_claimed"
    assert rows["effort"]["binding"] == "owner-bound_claimed"


def test_a_resume_dispatch_is_held_to_the_same_request_through_the_one_door(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    exp = _post(world, cid, model="opus", difficulty="mechanical")["expectations"][0]
    act = cv._act(exp)
    kw = dict(conversation=act["conversation"], turn=act["turn"],
              participant=act["about"][0], work="resume", expectation=exp)
    assert "model" not in kw
    D.dispatch(world["state"], **kw)
    assert real["ex"].performed[-1].options["model"] == "opus"


def test_the_same_request_again_keeps_its_tier(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    exp = _post(world, cid, difficulty="complex")["expectations"][0]
    _again(world, cv, exp)
    assert real["ex"].performed[-1].options == {"model": "opus", "effort": "high"}
    assert _latest(cv, exp)["detail"]["routing"]["difficulty"] == "complex"


def test_a_retired_named_model_fails_honestly_and_is_not_substituted(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    exp = _post(world, cid, runtime="claude", model="retired")["expectations"][0]
    assert real["ex"].performed[-1].options["model"] == "retired"
    real["scripted"]["fn"] = lambda spec: RunResult(
        run_id=spec.run_id, backend=spec.backend, started=False,
        error_kind="backend_unavailable", error="claude does not offer it",
        option="model", offered=["opus"])
    _again(world, cv, exp)
    assert real["ex"].performed[-1].options["model"] == "retired"
    failed = max((a for a in cv.history(act="delivery-failed")),
                 key=lambda a: a["at"])
    assert "failure_classification" not in failed["detail"]
    assert failed["detail"]["runtime_evidence"]["option"] == "model"


def test_a_retry_the_owner_chose_sends_what_the_latest_pick_up_asked(world, carrying,
                                                                     found, real):
    cv = world["cv"]
    out = _delegate(world, carrying["grant"], participant=carrying["bob"], work="take",
                    expectation=found, model="opus", effort="xhigh")
    assert out["picked_up"] is True
    asked = cv.record_act(actor=world["who"]["@Vera"], act="expectation-recorded",
                          conversation=carrying["cid"], turn=carrying["turn"],
                          about=[world["who"]["@brian"]], because="ended empty",
                          detail={"recovery": D.EMPTY_RUN_REVIEW, "retry_of": found,
                                  "carrier": carrying["bob"]})
    starts = D.retry_if_chosen(cv, {"expectation": asked, "option": 0},
                               by=world["who"]["@brian"], turn=carrying["turn"])
    assert [(s["model"], s["effort"]) for s in starts] == [("opus", "xhigh")]


def test_a_recorded_reassignment_moves_the_runtime_and_keeps_the_rest(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    exp = _post(world, cid, runtime="claude", model="opus", effort="high")["expectations"][0]
    # written by Mark IV's recovery and still read: nothing here writes it anew
    act = cv._act(exp)
    cv.record_act(actor=act["actor"], act=D.WORK_REASSIGNED,
                  conversation=act["conversation"], turn=act["turn"], caused_by=exp,
                  about=[exp], because="could not run there",
                  detail={"to_runtime": "codex"})
    time.sleep(0.02)
    _again(world, cv, exp)
    started = _latest(cv, exp)
    assert started["runtime"] == "codex"
    assert real["ex"].performed[-1].options == {"model": "opus", "effort": "high"}
    rows = started["detail"]["field_binding"]
    assert rows["runtime"]["binding"] == "reassigned-bound"
    assert rows["model"]["binding"] == "owner-bound_claimed", "untouched, and kept"


def test_a_continuation_inherits_the_runtime_only(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    first = _post(world, cid, runtime="claude", model="opus", effort="xhigh",
                  advisory_tier="frontier")
    exp = first["expectations"][0]
    first_handle = _latest(cv, exp)["execution"]
    next_ = _post(world, cid, replies_to=_reply_of(cv, exp))
    cont = next_["expectations"][0]
    assert cont != exp
    d = _latest(cv, cont)
    assert d["runtime"] == "claude", "the runtime carries on"
    assert real["ex"].performed[-1].options == {}, "the model and effort do not"
    assert d["detail"]["field_binding"]["runtime"]["binding"] == "continued-bound"
    assert d["detail"]["field_binding"]["model"]["binding"] is None
    assert "routing" not in d["detail"], "nor does the tier"
    assert d["execution"] != first_handle, (
        "a continuation naming no model must not reuse a handle holding the old one")


def test_a_continuation_selects_afresh_from_its_own_signals(world, real):
    cv = world["cv"]
    cid = a_conversation(world)
    first = _post(world, cid, runtime="codex", model="max", effort="xhigh")
    cont = _post(world, cid, replies_to=_reply_of(cv, first["expectations"][0]),
                 difficulty="mechanical")["expectations"][0]
    assert _latest(cv, cont)["runtime"] == "codex"
    assert real["ex"].performed[-1].options == {"model": "mini", "effort": "low"}


# -- picked-up discovered work -------------------------------------------------

@pytest.fixture()
def found(world, carrying):
    from mentis.web import _surface
    from mentis.worker import _operate
    from tests.gravity_choice import owner_chooses
    surface = _surface(world["state"])
    exp = _operate(surface, "record_discovered_work",
                   {"work": "found on the way", "because": "not this work"},
                   carrying["grant"])["expectation"]
    owner_chooses(surface, carrying["grant"], exp)
    return exp


def test_a_pick_up_stores_its_constraints_without_rewriting_the_request(
        world, carrying, found, real):
    cv = world["cv"]
    before = dict(cv._act(found)["detail"])
    out = _delegate(world, carrying["grant"], participant=carrying["bob"], work="take",
                    expectation=found, model="opus", effort="xhigh",
                    constraint_bases={"model": carrying["turn"]},
                    advisory_tier="frontier")
    assert out["picked_up"] is True
    assert cv._act(found)["detail"] == before, "the request is not rewritten"
    assign = [a for a in cv.history(caused_by=found)
              if a["act"] == "expectation-assigned"][-1]["detail"]
    assert assign["constraints"]["model"] == "opus"
    assert assign["constraints"]["field_sources"] == {"model": "named", "effort": "named"}
    assert assign["constraints"]["constraint_bases"] == {"model": carrying["turn"]}
    assert assign["routing"]["advisory_tier"] == "frontier"
    delegated = cv._act(out["delegation"])["detail"]
    assert delegated["constraints"]["effort"] == "xhigh"
    assert delegated["routing"]["advisory_tier"] == "frontier"
    # the first run, then the same request again, each as asked
    _run(world, out)
    assert real["ex"].performed[-1].options == {"model": "opus", "effort": "xhigh"}
    state = cv.expectation_state(found)
    D.dispatch(world["state"], conversation=state["conversation"],
               turn=state["turn"], participant=carrying["bob"], work="resume",
               expectation=found)
    assert real["ex"].performed[-1].options == {"model": "opus", "effort": "xhigh"}
    rows = _latest(cv, found)["detail"]["field_binding"]
    assert rows["model"]["binding"] == "owner-bound_claimed"
    assert rows["effort"]["binding"] == "carrier-bound"
    assert _latest(cv, found)["detail"]["routing"]["advisory_tier"] == "frontier"


def test_work_continuing_a_pick_up_inherits_neither_model_nor_effort(
        world, carrying, found, real):
    cv = world["cv"]
    out = _delegate(world, carrying["grant"], participant=carrying["bob"], work="take",
                    expectation=found, runtime="claude", model="opus", effort="xhigh")
    _run(world, out)
    assert real["ex"].performed[-1].options == {"model": "opus", "effort": "xhigh"}
    cont = _post(world, carrying["cid"], participant=carrying["bob"],
                 replies_to=_reply_of(cv, found))
    exp = cont["expectations"][0]
    assert exp != found
    assert _latest(cv, exp)["runtime"] == "claude"
    assert real["ex"].performed[-1].options == {}


# -- failure, evidence and no retry --------------------------------------------

def _rejected(option, offered=("a",)):
    def fn(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=False,
                         error_kind="backend_unavailable",
                         error=f"{spec.backend} does not offer {option}",
                         option=option, offered=list(offered),
                         started_at=now, finished_at=now)
    return fn


def _failed_act(cv, exp):
    start = _latest(cv, exp)["id"]
    got = [a for a in cv.history(caused_by=start) if a["act"] == "delivery-failed"]
    assert len(got) == 1
    return got[0]


@pytest.mark.parametrize("option,want", [
    ("model", "model_unavailable/catalogue_changed"),
    ("effort", "effort_unavailable/catalogue_changed")])
def test_an_automatically_selected_option_vanishing_is_the_catalogue_changing(
        world, real, option, want):
    cv = world["cv"]
    cid = a_conversation(world)
    real["scripted"]["fn"] = _rejected(option)
    exp = _post(world, cid, difficulty="complex")["expectations"][0]
    assert len(real["ex"].performed) == 1, "nothing is retried"
    act = _failed_act(cv, exp)
    assert act["detail"]["failure_classification"] == want
    ev = act["detail"]["runtime_evidence"]
    assert ev["option"] == option and ev["offered"] == ["a"]
    assert ev["error_kind"] == "backend_unavailable"
    assert quota_holds(cv) == {}, "it is not a quota hold"


@pytest.mark.parametrize("field,option,value", [("model", "model", "opus"),
                                                ("effort", "effort", "high")])
def test_a_named_option_failing_is_not_the_catalogue_changing(
        world, real, field, option, value):
    cv = world["cv"]
    cid = a_conversation(world)
    real["scripted"]["fn"] = _rejected(option)
    exp = _post(world, cid, **{field: value})["expectations"][0]
    act = _failed_act(cv, exp)
    assert "failure_classification" not in act["detail"]
    assert act["detail"]["runtime_evidence"]["option"] == option


def test_an_ordinary_configuration_failure_is_not_misclassified(world, real):
    cv = world["cv"]
    cid = a_conversation(world)

    def config(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=False,
                         error_kind="backend_unavailable",
                         error="backends.json: claude does not offer model 'x'",
                         started_at=now, finished_at=now)
    real["scripted"]["fn"] = config
    exp = _post(world, cid, difficulty="complex")["expectations"][0]
    act = _failed_act(cv, exp)
    assert "failure_classification" not in act["detail"]
    assert "option" not in act["detail"]["runtime_evidence"]


def test_a_failure_returns_evidence_and_escalation_is_a_new_authorized_execution(
        world, carrying, real):
    cv = world["cv"]
    calls = len(real["ex"].performed)
    real["scripted"]["fn"] = lambda spec: RunResult(
        run_id=spec.run_id, backend=spec.backend, started=True,
        error_kind="agent_error", error="could not finish")
    out = _delegate(world, carrying["grant"], participant=carrying["bob"], work="x",
                    difficulty="bounded")
    _run(world, out)
    assert len(real["ex"].performed) == calls + 1, "nothing retried it"
    act = _failed_act(cv, out["expectation"])
    assert act["detail"]["selected"]["model"] in ("sonnet", "code")
    assert act["detail"]["selected"]["effort"] == "medium"
    assert act["detail"]["routing"]["required_tier"] == "coding"
    assert act["detail"]["field_sources"]["model"] == "tier"
    assert act["detail"]["error"] == "agent_error: could not finish"
    # the coordinator reads that, and authorizes something stronger
    real["scripted"].clear()
    up = _delegate(world, carrying["grant"], participant=carrying["bob"],
                   work="x again", advisory_tier="frontier")
    _run(world, up)
    d = _latest(cv, up["expectation"])
    assert d["detail"]["selected_model"] == "opus"
    assert d["detail"]["field_binding"]["model"]["binding"] == "advisory"
    assert up["expectation"] != out["expectation"]


def test_a_quota_failure_on_a_tier_model_holds_it_and_routing_goes_to_a_sibling(
        world, real):
    cv = world["cv"]
    cid = a_conversation(world)

    def quota(spec):
        now = time.time()
        if spec.options.get("model") == "sonnet":
            return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                             error_kind="rate_limited", error="quota",
                             started_at=now, finished_at=now)
        return None
    real["scripted"]["fn"] = quota
    real["ex"]._backends = [_claude(), _plain("antigravity")]
    first = _post(world, cid, difficulty="bounded")["expectations"][0]
    assert real["ex"].performed[-1].options["model"] == "sonnet"
    assert _scopes(cv, "claude") == {"sonnet"}
    assert len(_runs(cv, first)) == 1
    # sonnet is held and its sibling at this tier or above takes the next
    second = _post(world, cid, difficulty="bounded")["expectations"][0]
    assert real["ex"].performed[-1].options["model"] == "opus"
    assert _scopes(cv, "claude") == {"sonnet"}, "opus succeeding clears no sibling"
    assert _latest(cv, second)["detail"]["effective_model"] == "opus"
