"""Candidate selection over MARS's `modelCatalogue` (docs/model-selection-contract.md
section 4), at `MentisService.execution_select` with fake catalogues and
capacity: suitability per candidate, unknowns never dropped (deferred, or
preferred for bounded exploratory work, D2), expiring capacity favouring a
stronger suitable model only on the contract's conditions (D3), model-scoped
quota windows, review independence, unknown effort support, aliases, explicit
owner choices never substituted, and availability changing under selection.
"""

from __future__ import annotations

import threading
import time

import pytest

from mentis import suitability as S
from mentis.api.errors import RuntimeNotPresent, Unsupported
from mentis.core import requirements as R
from mentis.core.service import MentisService
from mentis.execution import FakeExecution, RunResult
from tests._catalogue_world import (antigravity, backend, cat_carrying,  # noqa: F401
                                    cat_real, claude, codex, delegate,
                                    latest_start, model, run)
from tests._loop import world  # noqa: F401

LEGACY = [dict(s) for s in S.LEGACY_STANDING]


def owner(pattern, level, opened, *, runtimes=None, sid=None, insufficient=False):
    return {"id": sid or f"act-{pattern}", "pattern": pattern, "runtimes": runtimes,
            "reasoning_max": level, "open": opened, "insufficient": insufficient,
            "basis": "owner", "evidence": [], "proposed_by": None,
            "supersedes": None, "source": "owner"}


def _window(label, used, resets_in, seconds, group=None):
    now = time.time()
    return {"label": label, "usedFraction": used, "windowSeconds": seconds,
            "resetsAt": now + resets_in, "group": group, "raw": {}}


def _report(*windows, groups=None):
    return {"observedAt": time.time(), "plan": None, "notes": [],
            "modelGroups": dict(groups or {}), "windows": list(windows)}


def _svc(tmp_path, backends, capacity=None):
    ex = FakeExecution(backends, capacity=capacity)
    svc = MentisService(str(tmp_path / "instances"), execution=ex)
    svc._capacity_read(threading.Event())
    return svc, ex


def _select(svc, *, solution=None, reasoning=None, difficulty=None,
            exploratory=None, done_when=None, forced=(), standing=None, **kw):
    req, _ = R.derive(solution=solution, reasoning=reasoning,
                      difficulty=difficulty, exploratory=exploratory,
                      done_when=done_when)
    need = R.need(req, forced=forced)
    return svc.execution_select(need=need, requirements=req,
                                standing=LEGACY if standing is None else standing,
                                **kw)


def _cands(sel):
    return {(c["runtime"], c["model"]): c
            for c in sel.inputs["selection"]["candidates"]}


# -- suitability and the least sufficient --------------------------------------------

def test_open_work_gets_only_open_capable_standing(tmp_path):
    svc, _ = _svc(tmp_path, [claude()])
    sel = _select(svc, solution="open")
    assert (sel.runtime, sel.model, sel.requested_effort) == \
        ("claude", "claude-opus-5", "medium")
    c = _cands(sel)
    assert c[("claude", "claude-sonnet-5")]["verdict"] == "unknown"
    assert c[("claude", "claude-sonnet-5")]["outcome"] == "deferred"
    bounded = _select(svc, difficulty="bounded")
    assert (bounded.model, bounded.requested_effort) == ("claude-sonnet-5", "medium")


def test_light_work_takes_the_least_sufficient(tmp_path):
    svc, _ = _svc(tmp_path, [claude()])
    sel = _select(svc, solution="specified", reasoning="light")
    assert (sel.model, sel.requested_effort) == ("claude-haiku-4-5-20251001", "low")


def test_insufficient_by_owner_statement_is_excluded_with_the_statement(tmp_path):
    svc, _ = _svc(tmp_path, [claude()])
    st = LEGACY + [owner("claude-haiku-4-5-20251001", "light", False,
                         sid="act-veto", insufficient=True)]
    sel = _select(svc, solution="specified", reasoning="light", standing=st)
    assert sel.model == "claude-sonnet-5"
    c = _cands(sel)[("claude", "claude-haiku-4-5-20251001")]
    assert c["verdict"] == "insufficient" and c["outcome"] == "excluded"
    assert "act-veto" in c["why"]


# -- newly listed models: never dropped ----------------------------------------------

def test_a_newly_listed_claude_or_codex_model_is_a_visible_deferred_unknown(tmp_path):
    cl = claude()
    cl["modelCatalogue"]["models"].append(model("claude-opus-6", ("low", "high")))
    cx = codex()
    cx["modelCatalogue"]["models"].append(model("gpt-7", ("medium",)))
    svc, _ = _svc(tmp_path, [cl, cx])
    sel = _select(svc, reasoning="substantial")
    c = _cands(sel)
    for key in (("claude", "claude-opus-6"), ("codex", "gpt-7")):
        assert c[key]["verdict"] == "unknown"
        assert c[key]["outcome"] == "deferred"
        assert "not established" in c[key]["why"]
    assert sel.model in ("claude-sonnet-5", "gpt-6.1-terra")


def test_with_nothing_established_anywhere_every_model_is_still_recorded(tmp_path):
    only_new = backend("claude", [model("claude-opus-6"), model("claude-sonnet-6")],
                       default="claude-sonnet-6")
    svc, _ = _svc(tmp_path, [only_new])
    sel = _select(svc, reasoning="substantial")
    assert sel.runtime == "claude" and sel.model is None, "the runtime's own default"
    assert sel.inputs["routing"]["tier_unfulfilled"] == "no_catalogue_metadata"
    c = _cands(sel)
    assert c[("claude", "claude-opus-6")]["outcome"] == "deferred"
    assert c[("claude", "claude-sonnet-6")]["outcome"] == "deferred"
    assert c[("claude", None)]["outcome"] == "selected"


def test_a_new_local_model_is_unknown_and_deferred(tmp_path):
    local = backend("local", [model("llama3.3:70b", None, locality="local")],
                    default="llama3.3:70b")
    svc, _ = _svc(tmp_path, [claude(), local])
    sel = _select(svc, solution="specified", reasoning="light")
    assert sel.runtime == "claude"
    c = _cands(sel)[("local", "llama3.3:70b")]
    assert c["verdict"] == "unknown" and c["outcome"] == "deferred"
    # the owner establishes it: it is then a candidate like any other
    st = LEGACY + [owner("llama3.3:*", "light", False, runtimes=["local"])]
    only_local = _select(svc, solution="specified", reasoning="light",
                         standing=st, runtime="local")
    assert only_local.model == "llama3.3:70b"
    assert _cands(only_local)[("local", "llama3.3:70b")]["by"] == "pattern"


def test_mars_tier_tags_are_not_read_where_there_is_a_catalogue(tmp_path):
    tagged = claude(routing_models=[{"id": "claude-opus-6", "tier": "frontier",
                                     "efforts": ["high"]}])
    tagged["modelCatalogue"]["models"].append(model("claude-opus-6", ("high",)))
    svc, _ = _svc(tmp_path, [tagged])
    sel = _select(svc, solution="open", reasoning="deep")
    assert sel.model == "claude-opus-5"
    assert _cands(sel)[("claude", "claude-opus-6")]["verdict"] == "unknown"


# -- D2: bounded exploratory work ------------------------------------------------------

def _explorable():
    cl = claude()
    cl["modelCatalogue"]["models"].append(model("claude-opus-6", ("low", "medium")))
    return cl


def test_exploratory_work_prefers_an_unknown_model(tmp_path):
    svc, _ = _svc(tmp_path, [_explorable()])
    sel = _select(svc, solution="specified", reasoning="substantial",
                  exploratory=True, done_when="the three tests pass")
    assert sel.model == "claude-opus-6" and sel.requested_effort == "medium"
    c = _cands(sel)[("claude", "claude-opus-6")]
    assert c["outcome"] == "selected" and "D2" in c["why"]
    assert sel.inputs["selection"]["exploratory"] is True


@pytest.mark.parametrize("forced", [["review"], ["authority_sensitive"]])
def test_exploratory_is_never_review_or_authority(tmp_path, forced):
    svc, _ = _svc(tmp_path, [_explorable()])
    sel = _select(svc, solution="specified", reasoning="light", exploratory=True,
                  done_when="x", forced=forced)
    assert sel.model == "claude-opus-5"
    assert any("not run on an unproven model" in b for b in sel.because)


def test_exploratory_is_never_deep_open_work(tmp_path):
    svc, _ = _svc(tmp_path, [_explorable()])
    sel = _select(svc, solution="open", reasoning="deep", exploratory=True,
                  done_when="x")
    assert sel.model == "claude-opus-5"
    assert any("deep reasoning on an open" in b for b in sel.because)


# -- D3: expiring capacity -------------------------------------------------------------

def _d3(tmp_path, agy_used=0.1, agy_resets=3600, agy_window=True):
    agy = antigravity()
    st = LEGACY + [owner("claude-opus-5-5-*", "deep", True,
                         runtimes=["antigravity"])]
    cap = {"claude": _report(_window("weekly", 0.5, 6 * 86400, 7 * 86400)),
           "antigravity": _report(
               *([_window("weekly", agy_used, agy_resets, 7 * 86400,
                          "Claude and GPT")] if agy_window else []),
               _window("weekly", 0.0, 6 * 86400, 7 * 86400, "Gemini"))}
    svc, _ = _svc(tmp_path, [claude(), agy], cap)
    return svc, st


def test_expiring_capacity_favours_a_stronger_suitable_model(tmp_path):
    svc, st = _d3(tmp_path)
    sel = _select(svc, solution="specified", reasoning="light", standing=st)
    assert (sel.runtime, sel.model) == ("antigravity", "claude-opus-5-5-high")
    assert sel.requested_effort is None, "the effort is in the id"
    assert "capacity_stronger" in sel.dimensions_used
    assert any("D3" in b for b in sel.because)


def test_not_when_the_stronger_pace_is_unknown(tmp_path):
    svc, st = _d3(tmp_path, agy_window=False)
    sel = _select(svc, solution="specified", reasoning="light", standing=st)
    assert sel.model == "claude-haiku-4-5-20251001"
    assert "capacity_stronger" not in sel.dimensions_used


def test_not_when_its_budget_is_below_the_guard(tmp_path):
    svc, st = _d3(tmp_path, agy_used=0.6)
    sel = _select(svc, solution="specified", reasoning="light", standing=st)
    assert sel.model == "claude-haiku-4-5-20251001"


def test_never_for_a_named_model(tmp_path):
    svc, st = _d3(tmp_path)
    sel = _select(svc, solution="specified", reasoning="light", standing=st,
                  model="claude-haiku-4-5-20251001")
    assert sel.model == "claude-haiku-4-5-20251001"


# -- model-scoped quota windows ---------------------------------------------------------

def test_a_models_own_window_judges_it_from_its_quota_group(tmp_path):
    agy = antigravity()
    st = [owner("gemini-4-argon-*", "deep", True, runtimes=["antigravity"]),
          owner("claude-opus-5-5-*", "deep", True, runtimes=["antigravity"])]
    cap = {"antigravity": _report(
        _window("weekly", 1.0, 3600, 7 * 86400, "Gemini"),
        _window("weekly", 0.2, 7200, 7 * 86400, "Claude and GPT"))}
    svc, _ = _svc(tmp_path, [agy], cap)
    sel = _select(svc, solution="specified", reasoning="light", standing=st)
    assert sel.model == "claude-opus-5-5-high"
    c = _cands(sel)
    assert c[("antigravity", "gemini-4-argon-low")]["outcome"] == "excluded"
    assert c[("antigravity", "gemini-4-argon-low")]["capacity"] == "exhausted"


# -- review independence ----------------------------------------------------------------

def test_review_avoids_the_authors_runtime(tmp_path):
    svc, _ = _svc(tmp_path, [claude(), codex()])
    sel = _select(svc, forced=["review"], avoid="claude")
    assert (sel.runtime, sel.model, sel.requested_effort) == \
        ("codex", "gpt-6.1-sol", "high")
    alone = _select(MentisService(str(tmp_path / "i2"),
                                  execution=FakeExecution([claude()])),
                    forced=["review"], avoid="claude")
    assert alone.runtime == "claude"
    assert any("not independent by runtime" in d
               for d in alone.inputs["disclosed"])


# -- unknown effort support -------------------------------------------------------------

def test_unknown_efforts_send_none_and_rank_after_verified(tmp_path):
    cl = backend("claude", [model("claude-sonnet-5", None)],
                 default="claude-sonnet-5")
    svc, _ = _svc(tmp_path, [cl, codex()])
    sel = _select(svc, difficulty="bounded")
    assert (sel.runtime, sel.model) == ("codex", "gpt-6.1-terra")
    c = _cands(sel)[("claude", "claude-sonnet-5")]
    assert c["effort_floor_unverified"] is True and c["outcome"] == "deferred"
    only = _select(MentisService(str(tmp_path / "i2"),
                                 execution=FakeExecution([cl])), difficulty="bounded")
    assert only.model == "claude-sonnet-5" and only.requested_effort is None
    assert only.inputs["routing"]["effort_floor_unverified"] is True
    assert any("effort_floor_unverified" in b for b in only.because)


# -- aliases ---------------------------------------------------------------------------

def test_an_alias_entry_is_not_double_counted_and_its_name_selects(tmp_path):
    svc, _ = _svc(tmp_path, [claude()])
    sel = _select(svc, solution="open", reasoning="deep")
    models = [c["model"] for c in sel.inputs["selection"]["candidates"]]
    assert models.count("claude-opus-5") == 1 and "opus" not in models
    named = _select(svc, solution="open", reasoning="deep", model="opus")
    assert (named.runtime, named.model) == ("claude", "opus"), "sent as named"
    c = _cands(named)[("claude", "opus")]
    assert c["verdict"] == "established" and c["outcome"] == "selected"


# -- explicit owner choice --------------------------------------------------------------

def test_a_named_model_runs_exactly_and_the_recommendation_is_said(tmp_path):
    svc, _ = _svc(tmp_path, [claude(), codex()])
    sel = _select(svc, solution="open", reasoning="deep",
                  model="claude-haiku-4-5-20251001")
    assert (sel.runtime, sel.model) == ("claude", "claude-haiku-4-5-20251001")
    rec = sel.inputs["selection"]["recommendation"]
    assert rec["differs"] == ["model"]
    assert rec["model"] in ("claude-opus-5", "gpt-6.1-sol")
    assert "not acted on" in rec["why"]


def test_a_named_model_nothing_offers_is_refused(tmp_path):
    svc, _ = _svc(tmp_path, [claude()])
    with pytest.raises(Unsupported) as got:
        _select(svc, reasoning="light", model="gpt-6.1-sol")
    assert "refusing rather than running a different model" in str(got.value)


def test_a_named_effort_is_sent_as_named(tmp_path):
    svc, _ = _svc(tmp_path, [claude()])
    sel = _select(svc, solution="open", reasoning="deep", runtime="claude",
                  effort="low")
    assert sel.requested_effort == "low"
    assert sel.inputs["routing"]["tier_unfulfilled"] == "fixed_binding"


def test_a_refused_model_is_excluded_automatically_and_disclosed_when_named(tmp_path):
    cl = claude()
    for m in cl["modelCatalogue"]["models"]:
        if m["id"] == "claude-opus-5":
            m["status"], m["statusWhy"] = "refused", "set_model: unknown model"
    svc, _ = _svc(tmp_path, [cl, codex()])
    auto = _select(svc, solution="open", reasoning="deep")
    assert (auto.runtime, auto.model) == ("codex", "gpt-6.1-sol")
    c = _cands(auto)[("claude", "claude-opus-5")]
    assert c["outcome"] == "excluded" and "refuse" in c["why"]
    named = _select(svc, solution="open", reasoning="deep", runtime="claude",
                    model="claude-opus-5")
    assert (named.runtime, named.model) == ("claude", "claude-opus-5")
    assert any("refuse model 'claude-opus-5'" in d and "not substituted" in d
               for d in named.inputs["disclosed"])


# -- availability changing during selection --------------------------------------------

def test_a_runtime_gone_after_the_catalogue_read(tmp_path):
    svc, ex = _svc(tmp_path, [claude(), codex()])
    first = _select(svc, solution="open", reasoning="deep", runtime="claude")
    assert first.runtime == "claude"
    ex._backends = [claude(available=False), codex()]
    # A NAMED RUNTIME IS REFUSED, never substituted
    with pytest.raises(RuntimeNotPresent):
        _select(svc, solution="open", reasoning="deep", runtime="claude")
    # automatic selection judges again on what MARS now says
    again = _select(svc, solution="open", reasoning="deep")
    assert (again.runtime, again.model) == ("codex", "gpt-6.1-sol")
    c = _cands(again)[("claude", None)]
    assert c["outcome"] == "excluded" and "not available" in c["why"]


def test_a_run_whose_backend_went_away_fails_and_nothing_is_substituted(
        world, cat_carrying, cat_real):
    """Between selection and launch the backend became unavailable: as today,
    the run fails at MARS and is recorded, and the work is not moved to another
    runtime or model; a later run of it judges again."""
    from mentis import evidence as E
    cv = world["cv"]
    ex = cat_real["ex"]
    ex.script["claude"] = lambda spec: RunResult(
        run_id=spec.run_id, backend=spec.backend, started=False,
        error_kind="backend_unavailable", error="claude went away")
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="check it in the browser", requires=["drive_browser"],
                   solution="specified", reasoning="light")
    before = len(ex.performed)
    run(world, out)
    assert [s.backend for s in ex.performed[before:]] == ["claude"], \
        "one launch, on what was selected"
    failed = [a for a in cv.history(caused_by=latest_start(cv, out["expectation"])["id"])
              if a["act"] == "delivery-failed"]
    assert failed
    assert E.per_execution(cv, expectation=out["expectation"])[-1]["failure_class"] \
        == "infrastructure"
    # MARS now lists it unavailable: the next run of the same work is refused
    # (only claude can drive a browser), never placed on codex
    ex._backends = [claude(available=False), codex()]
    ex.script["claude"] = cat_real["perform"]
    got = run(world, out)
    assert got.get("ok") is False and got.get("before_execution_started")


# -- integrator review C1: critical work never on an unproven model automatically ----

def _agy_only(tmp_path):
    return _svc(tmp_path, [antigravity()])


@pytest.mark.parametrize("forced", [["review"], ["authority_sensitive"]])
def test_critical_work_with_only_unknown_models_is_refused_automatically(tmp_path,
                                                                        forced):
    svc, _ = _agy_only(tmp_path)
    with pytest.raises(Unsupported) as got:
        _select(svc, forced=forced)
    words = str(got.value)
    assert "not run automatically on a model whose suitability is not established" \
        in words
    assert "Name a runtime and model" in words
    # NAMED, it runs exactly as named
    named = _select(svc, forced=forced, runtime="antigravity",
                    model="claude-opus-5-5-high")
    assert (named.runtime, named.model) == ("antigravity", "claude-opus-5-5-high")
    by_model = _select(svc, forced=forced, model="gemini-4-argon-high")
    assert by_model.model == "gemini-4-argon-high"


def test_critical_work_refused_when_no_established_candidate_survives(tmp_path):
    # informed somewhere (a statement speaks of a model) but nothing established
    svc, _ = _agy_only(tmp_path)
    st = LEGACY + [owner("gemini-4-argon-*", "light", False,
                         runtimes=["antigravity"])]
    with pytest.raises(Unsupported, match="review work is not run automatically"):
        _select(svc, forced=["review"], standing=st)


def test_non_forced_deep_open_work_keeps_the_runtime_default(tmp_path):
    svc, _ = _agy_only(tmp_path)
    sel = _select(svc, solution="open", reasoning="deep")
    assert sel.runtime == "antigravity"
    assert sel.inputs["routing"]["tier_unfulfilled"] == "no_catalogue_metadata"


# -- integrator review C2: the soft/light fallback is an explicit candidate ------------

def _own(rid, *ids, default=None):
    return backend(rid, [model(i, ("low", "medium", "high")) for i in ids],
                   default=default)


def test_an_insufficient_default_is_not_run_by_the_fallback(tmp_path):
    svc, _ = _svc(tmp_path, [_own("local", "x-default", "x-other",
                                  default="x-default")])
    st = LEGACY + [owner("x-default", "light", False, sid="act-no",
                         insufficient=True)]
    sel = _select(svc, standing=st)
    assert (sel.runtime, sel.model, sel.requested_effort) == \
        ("local", "x-other", "medium")
    c = _cands(sel)
    assert c[("local", "x-default")]["outcome"] == "excluded"
    assert c[("local", "x-other")]["outcome"] == "selected"
    assert c[("local", "x-other")]["why"] == \
        "suitability not established (fallback for soft work)"
    assert any("fallback for soft work" in d for d in sel.inputs["disclosed"])


def test_a_held_default_yields_to_an_available_unknown_sibling(tmp_path):
    now = time.time()
    hold = {"until": now + 600, "why": "held", "model": "m-a", "since": now,
            "basis": "act-1"}
    svc, _ = _svc(tmp_path, [_own("local", "m-a", "m-b", "m-c", default="m-a")])
    st = LEGACY + [owner("m-c", "light", False, runtimes=["local"])]
    sel = _select(svc, standing=st,
                  holds={"local": {**hold, "scopes": [hold]}})
    assert sel.model == "m-b"
    assert _cands(sel)[("local", "m-a")]["outcome"] == "excluded"


def test_light_fallback_is_refused_when_no_unknown_can_take_it(tmp_path):
    svc, _ = _svc(tmp_path, [_own("local", "x-default", default="x-default")])
    st = LEGACY + [owner("x-default", "light", False, insufficient=True)]
    with pytest.raises(Unsupported, match="insufficient by the owner"):
        _select(svc, reasoning="light", standing=st)


def test_a_runtime_naming_no_default_gets_an_explicit_model(tmp_path):
    local = backend("local", [model("llama3.3:70b", None, locality="local"),
                              model("qwen3:32b", None, locality="local")])
    # nothing informed anywhere
    svc, _ = _svc(tmp_path, [local])
    sel = _select(svc, reasoning="light")
    assert (sel.runtime, sel.model, sel.requested_effort) == \
        ("local", "llama3.3:70b", None)
    assert any("names no default model" in d for d in sel.inputs["disclosed"])
    assert _cands(sel)[("local", "llama3.3:70b")]["outcome"] == "selected"
    # named, beside a runtime with established models
    svc2, _ = _svc(tmp_path / "two", [claude(), local])
    named = _select(svc2, reasoning="light", runtime="local")
    assert (named.runtime, named.model) == ("local", "llama3.3:70b")
    assert named.inputs["routing"]["tier_unfulfilled"] == "fixed_binding"
    # in the soft fallback too
    svc3, _ = _svc(tmp_path / "three",
                   [claude(available=True), local])
    soft = _select(svc3, reasoning="light", requires=())
    assert soft.runtime == "claude", "an established model is used first"


def test_a_named_runtime_with_a_standing_default_keeps_it(tmp_path):
    svc, _ = _svc(tmp_path, [claude(), _own("local", "m-a", "m-b", default="m-a")])
    sel = _select(svc, reasoning="light", runtime="local")
    assert (sel.runtime, sel.model) == ("local", None), "today's behaviour"


def test_a_model_reported_unable_to_use_tools_is_not_chosen_automatically(tmp_path):
    """Found live 2026-11-12: the local fallback picked Ollama's tev1:0.8b, which
    MARS reports `tools: unsupported`, and the run failed ("does not support
    chat"). Reported, not inferred: automatic selection passes it over; named,
    it still runs exactly as named."""
    no_tools = model("tev1:0.8b", None, locality="local")
    no_tools["capabilities"] = {"tools": "unsupported"}
    with_tools = model("qwen2.5:7b", None, locality="local")
    with_tools["capabilities"] = {"tools": "supported"}
    local = backend("local", [no_tools, with_tools])
    svc, _ = _svc(tmp_path, [local])
    sel = _select(svc, reasoning="light")
    assert (sel.runtime, sel.model) == ("local", "qwen2.5:7b")
    assert _cands(sel)[("local", "tev1:0.8b")]["outcome"] == "excluded"
    named = _select(svc, reasoning="light", runtime="local", model="tev1:0.8b")
    assert (named.runtime, named.model) == ("local", "tev1:0.8b")
