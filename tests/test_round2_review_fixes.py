"""Regressions for the independent review of workstream S (round 2,
review-S.md) and the coordinator's C1 finding:

1. demanding work with nothing standing never falls through to an excluded
   model or the implicit runtime default;
2. a held default does not exhaust a runtime whose sibling is usable;
3. an `implements` with no owner approval is reassessed (D4);
4. lineage stays within the Conversation;
5. critical work is refused only where some runtime lists models to judge.
"""

from __future__ import annotations

import threading
import time

import pytest

from mentis import evidence as E
from mentis.api.errors import Unsupported
from mentis.core import requirements as R
from mentis.core.service import MentisService
from mentis.execution import FakeExecution
from mentis.worker import NotPermitted
from tests._catalogue_world import (backend, cat_carrying, cat_real,  # noqa: F401
                                    delegate, model, reply_of, routing_of, run)
from tests._loop import a_conversation, say, world  # noqa: F401


def _svc(tmp_path, backends):
    svc = MentisService(str(tmp_path / "instances"),
                        execution=FakeExecution(backends))
    svc._capacity_read(threading.Event())
    return svc


def _select(svc, *, forced=(), standing=(), **said):
    kw = {k: said.pop(k) for k in ("runtime", "model", "effort", "requires",
                                   "holds") if k in said}
    req, _ = R.derive(**said)
    return svc.execution_select(need=R.need(req, forced=forced),
                                requirements=req, standing=list(standing), **kw)


def _local(*models_, default):
    return backend("local", list(models_), default=default)


def _no_tools(mid):
    m = model(mid, None, locality="local")
    m["capabilities"] = {"tools": "unsupported"}
    return m


# -- 1. never an excluded model or the implicit default -------------------------------

@pytest.mark.parametrize("bad", ["refused", "tools", "floor"])
def test_an_excluded_default_with_nothing_usable_is_refused(tmp_path, bad):
    default = {"refused": model("m-def", ("low", "medium", "high"),
                                status="refused"),
               "tools": _no_tools("m-def"),
               "floor": model("m-def", ("low",))}[bad]
    svc = _svc(tmp_path, [_local(default, default="m-def")])
    with pytest.raises(Unsupported) as got:
        _select(svc, solution="open", reasoning="deep")
    words = str(got.value)
    assert "not run on an excluded model or an implicit runtime default" in words
    assert "local:" in words


@pytest.mark.parametrize("bad", ["refused", "tools", "floor"])
def test_an_excluded_default_yields_to_a_usable_sibling_explicitly(tmp_path, bad):
    default = {"refused": model("m-def", ("low", "medium", "high"),
                                status="refused"),
               "tools": _no_tools("m-def"),
               "floor": model("m-def", ("low",))}[bad]
    svc = _svc(tmp_path, [_local(default, model("m-ok", ("high",)),
                                 default="m-def")])
    sel = _select(svc, solution="open", reasoning="deep")
    assert (sel.runtime, sel.model, sel.requested_effort) == ("local", "m-ok",
                                                              "high")
    assert sel.inputs["selection"]["attempt"] == "unverified"
    assert sel.inputs["effective_model"] == "m-ok"


def test_unconfirmed_capabilities_are_refused_not_run_on_the_default(tmp_path):
    svc = _svc(tmp_path, [_local(model("m-def", ("high",)), default="m-def")])
    with pytest.raises(Unsupported, match="capabilities are not confirmed"):
        _select(svc, solution="open", reasoning="deep", requires=("build_ui",))


def test_a_named_runtime_with_only_excluded_models_is_refused(tmp_path):
    svc = _svc(tmp_path, [_local(_no_tools("m-def"), default="m-def")])
    with pytest.raises(Unsupported, match="Name the model too"):
        _select(svc, solution="open", reasoning="deep", runtime="local")
    named = _select(svc, solution="open", reasoning="deep", runtime="local",
                    model="m-def")
    assert named.model == "m-def", "named, it runs as named"


def test_a_backend_listing_no_model_keeps_its_default(tmp_path):
    bare = {"id": "bare", "kind": "acp", "available": True, "reason": None,
            "models": [], "efforts": [], "supports": {"mcp": ["stdio"]}}
    sel = _select(_svc(tmp_path, [bare]), solution="open", reasoning="deep")
    assert (sel.runtime, sel.model) == ("bare", None)


# -- 2. a held default does not exhaust its runtime -----------------------------------

def test_a_held_default_leaves_a_usable_sibling(tmp_path):
    now = time.time()
    hold = {"until": now + 3600, "why": "local: held", "model": "new-a",
            "since": now, "basis": "act-q"}
    svc = _svc(tmp_path, [_local(model("new-a", ("high",)),
                                 model("new-b", ("high",)), default="new-a")])
    sel = _select(svc, solution="open", reasoning="deep",
                  holds={"local": {**hold, "scopes": [hold]}})
    assert (sel.runtime, sel.model) == ("local", "new-b")
    assert sel.inputs["selection"]["attempt"] == "unverified"
    c = {(x["runtime"], x["model"]): x for x in sel.inputs["selection"]["candidates"]}
    assert c[("local", "new-a")]["outcome"] == "excluded"


# -- 3. an unapproved implements is reassessed ---------------------------------------

def test_an_unapproved_implements_of_failed_work_must_restate(world, cat_carrying):
    cv = world["cv"]
    design = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                      work="design it", requires=[], solution="open",
                      reasoning="deep")
    run(world, design)
    result_turn = reply_of(cv, design["expectation"])
    cv.record_act(actor=world["who"]["@brian"], act=E.RESULT_VERDICT,
                  about=[design["expectation"]], caused_by=design["expectation"],
                  detail={"verdict": "rejected", "why": "wrong design"})
    with pytest.raises(NotPermitted) as got:
        delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                 work="build it", requires=[], relation="implements",
                 relation_ref=[result_turn])
    assert "names no owner approval" in str(got.value)
    assert "D4" in str(got.value)
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="build it", requires=[], relation="implements",
                   relation_ref=[result_turn], solution="open", reasoning="deep")
    assert cv._act(out["expectation"])["detail"]["reassessment"]["restated"] == \
        {"solution": "open", "reasoning": "deep"}


# -- 4. lineage stays within the Conversation -----------------------------------------

def test_a_reference_into_another_conversation_is_not_continued(world, cat_real,
                                                                cat_carrying):
    cv = world["cv"]
    other = a_conversation(world, "Elsewhere")
    got = say(world, other, "deep background work", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "think",
                         "solution": "open", "reasoning": "deep"}])
    elsewhere = got["turn"]
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="small change", requires=[], solution="specified",
                   reasoning="light", references=[elsewhere])
    req = routing_of(cv, out["expectation"])["requirements"]
    assert req["relation"]["value"] == "new"
    assert req["reasoning"] == {"value": "light", "source": "stated", "from": []}
    assert req["solution"]["value"] == "specified"
    # the same reference, within the Conversation, is continued
    here = say(world, cat_carrying["cid"], "deep work here",
               action="ask-participant",
               dispatch=[{"participant": world["steward"], "work": "think",
                          "solution": "open", "reasoning": "deep"}])["turn"]
    again = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                     work="small change", requires=[], references=[here])
    assert routing_of(cv, again["expectation"])["requirements"]["reasoning"][
        "value"] == "deep"


# -- 5. critical work with no model listed anywhere -----------------------------------

@pytest.mark.parametrize("forced", [["review"], ["authority_sensitive"]])
def test_critical_work_where_nothing_lists_a_model_runs_the_default(tmp_path,
                                                                   forced):
    bare = {"id": "bare", "kind": "acp", "available": True, "reason": None,
            "models": [], "efforts": [], "supports": {"mcp": ["stdio"]}}
    sel = _select(_svc(tmp_path, [bare]), forced=forced)
    assert (sel.runtime, sel.model) == ("bare", None)
    assert sel.inputs["routing"]["tier_unfulfilled"] == "no_catalogue_metadata"
    assert any("not applied" in b for b in sel.because)
    # listing models with nothing established: refused, as C1 decided
    svc = _svc(tmp_path / "two", [_local(model("m", ("high",)), default="m")])
    with pytest.raises(Unsupported, match="not run automatically"):
        _select(svc, forced=forced)


# -- 6. live check: every unknown pick for non-exploratory work is unverified --------

D2_WORDS = "preferred for exploratory work"


def _picked(sel):
    return next(c for c in sel.inputs["selection"]["candidates"]
                if c["outcome"] == "selected")


@pytest.mark.parametrize("runtime,said,expect", [
    ("antigravity", {"solution": "open", "reasoning": "deep"},
     "gemini-4-argon-high"),
    ("local", {"reasoning": "substantial"}, "qwen2.5:0.5b")])
def test_a_named_runtime_with_nothing_established_records_an_unverified_attempt(
        tmp_path, runtime, said, expect):
    """Live check 2026-11-12 (e2e/r2-selection.json): a named runtime with no
    established model for the need, beside runtimes that have one (legacy
    standing), selected its fallback with the exploratory (D2) words and no
    attempt. It is an unverified attempt, said so."""
    from mentis import suitability as S
    from tests._catalogue_world import real_catalogue
    svc = _svc(tmp_path, real_catalogue(local=True))
    sel = _select(svc, runtime=runtime, standing=[dict(s) for s in
                                                  S.LEGACY_STANDING], **said)
    assert (sel.runtime, sel.model) == (runtime, expect)
    picked = _picked(sel)
    assert picked["verdict"] == "unknown"
    assert picked["attempt"] == "unverified"
    assert sel.inputs["selection"]["attempt"] == "unverified"
    assert D2_WORDS not in picked["why"]
    assert picked["why"].startswith("unverified attempt: runtime "
                                    f"{runtime} was named and kept")
    assert "not established" in picked["why"]
    assert not any(D2_WORDS in b for b in sel.because)


@pytest.mark.parametrize("said", [{}, {"reasoning": "light"},
                                  {"solution": "open", "reasoning": "deep"}])
def test_no_unknown_pick_outside_exploratory_work_uses_the_d2_words(tmp_path,
                                                                  said):
    """Every path that can select a model whose suitability is not established
    -- the soft/light fallback, a runtime naming no default, the demanding
    unverified attempt -- records `attempt: unverified` and never D2's words."""
    from tests._catalogue_world import real_catalogue
    for i, cat in enumerate((
            [b for b in real_catalogue() if b["id"] == "antigravity"],
            [b for b in real_catalogue(local=True) if b["id"] == "local"],
            real_catalogue())):
        sel = _select(_svc(tmp_path / f"{i}", cat), **said)
        picked = _picked(sel)
        if picked.get("verdict") == "unknown":
            assert picked["attempt"] == "unverified", (i, picked)
            assert D2_WORDS not in picked["why"], (i, picked)
            assert sel.inputs["selection"]["attempt"] == "unverified"
    # and exploratory work keeps its own words, with no attempt label
    sel = _select(_svc(tmp_path / "x", real_catalogue()), reasoning="light",
                  exploratory=True, done_when="the tests pass")
    picked = _picked(sel)
    assert picked["verdict"] == "unknown" and D2_WORDS in picked["why"]
    assert "attempt" not in picked
