"""Unverified attempts and exploratory work on a catalogue shaped like the real
one (round 2 of the model-selection correction, workstream S; contract
section 4):

* demanding, noncritical work with NO established model available anywhere
  eligible runs an explicit discovered model as an UNVERIFIED ATTEMPT (the
  runtime's reported default first, else MARS's order; never refused,
  exhausted, held or tools-unsupported), recorded verdict `unknown`,
  `attempt: unverified` -- replacing interpretation I8 (the runtime default run
  in silence). Critical work keeps C1; named choices are never substituted.
* a newly discovered model nobody has rated is eligible for exploratory work,
  within `exploratory_allowed`'s limits.
* every candidate says why it was selected, excluded or deferred.
"""

from __future__ import annotations

import threading
import time

import pytest

from mentis import suitability as S
from mentis.api.errors import Unsupported
from mentis.core import requirements as R
from mentis.core.service import MentisService
from mentis.execution import FakeExecution
from tests._catalogue_world import (cat_carrying, cat_real,  # noqa: F401
                                    real_catalogue)
from tests._loop import world  # noqa: F401

LEGACY = [dict(s) for s in S.LEGACY_STANDING]
UI = ("build_ui", "drive_browser")
#: The legacy table's ids (owner #1401): established for what it says.
LEGACY_IDS = {s["pattern"] for s in LEGACY}


def _svc(tmp_path, backends):
    ex = FakeExecution(backends)
    svc = MentisService(str(tmp_path / "instances"), execution=ex)
    svc._capacity_read(threading.Event())
    return svc


def _select(svc, *, forced=(), standing=None, **said):
    kw = {k: said.pop(k) for k in ("runtime", "model", "effort", "requires",
                                   "holds") if k in said}
    req, _ = R.derive(**said)
    need = R.need(req, forced=forced)
    return svc.execution_select(need=need, requirements=req,
                                standing=LEGACY if standing is None else standing,
                                **kw)


def _cands(sel):
    return {(c["runtime"], c["model"]): c
            for c in sel.inputs["selection"]["candidates"]}


def _held(*pairs):
    """Quota holds on (runtime, model) pairs, as `quota_holds` reads them."""
    now = time.time()
    out: dict = {}
    for rt, mid in pairs:
        h = {"until": now + 3600, "why": f"{rt}: held after a quota failure",
             "model": mid, "since": now, "basis": "act-q"}
        out.setdefault(rt, {**h, "scopes": []})["scopes"].append(h)
    return out


#: Every established frontier model on the real catalogue, held.
FRONTIER_HELD = _held(("claude", "claude-opus-5"), ("claude", "claude-fable-5"),
                      ("codex", "gpt-6.1-sol"))


# -- the unverified attempt (replaces I8) --------------------------------------------

def test_demanding_ui_work_with_nothing_established_left_is_an_unverified_attempt(
        tmp_path):
    svc = _svc(tmp_path, real_catalogue())
    sel = _select(svc, solution="open", reasoning="deep", requires=UI,
                  holds=FRONTIER_HELD)
    # claude alone is confirmed for the UI capabilities; its own reported
    # default (`opus`, Opus 5.5) is sent EXPLICITLY at the floor
    assert (sel.runtime, sel.model, sel.requested_effort) == ("claude", "opus",
                                                              "high")
    assert sel.inputs["selection"]["attempt"] == "unverified"
    c = _cands(sel)
    picked = c[("claude", "opus")]
    assert picked["outcome"] == "selected" and picked["verdict"] == "unknown"
    assert picked["attempt"] == "unverified"
    assert "no model with established suitability" in picked["why"]
    assert "not established" in picked["why"]
    assert "runtime's own default model" in picked["why"]
    disclosed = " ".join(sel.inputs["disclosed"])
    assert "UNVERIFIED ATTEMPT" in disclosed and "not established" in disclosed
    assert "established and chosen" not in disclosed
    # the held established ones are excluded with the hold, never dropped
    assert c[("claude", "claude-opus-5")]["outcome"] == "excluded"
    assert "held" in c[("claude", "claude-opus-5")]["why"]
    # a model the legacy table speaks of at a lower level is not "unverified"
    assert c[("claude", "claude-sonnet-5")]["outcome"] != "selected"


def test_an_unverified_attempt_never_takes_a_refused_or_held_model(tmp_path):
    cat = real_catalogue()
    claude = next(b for b in cat if b["id"] == "claude")
    opus = next(m for m in claude["modelCatalogue"]["models"] if m["id"] == "opus")
    opus["status"] = "refused"
    svc = _svc(tmp_path, cat)
    holds = {**FRONTIER_HELD}
    holds["claude"]["scopes"].append({**holds["claude"]["scopes"][0],
                                      "model": "default"})
    sel = _select(svc, solution="open", reasoning="deep", requires=UI,
                  holds=holds)
    assert sel.runtime == "claude"
    assert sel.model not in ("opus", "default", "claude-opus-5", "claude-fable-5")
    assert sel.inputs["selection"]["attempt"] == "unverified"
    c = _cands(sel)
    assert c[("claude", "opus")]["outcome"] == "excluded"
    assert "refuse" in c[("claude", "opus")]["why"]
    # the first usable discovered model in MARS's order after them
    order = [m["id"] for m in claude["modelCatalogue"]["models"]]
    assert order.index(sel.model) == min(
        order.index(m) for m in ("claude-fable-5-2", "sonnet", "haiku", "fable")
        if m in order)


def test_with_nothing_standing_anywhere_the_default_is_sent_explicitly(tmp_path):
    """I8 replaced: a runtime nothing stands for, demanding work -- its reported
    default sent explicitly as an unverified attempt, not run in silence."""
    cat = [b for b in real_catalogue() if b["id"] == "codex"]
    svc = _svc(tmp_path, cat)
    sel = _select(svc, solution="open", reasoning="deep", standing=[])
    assert (sel.runtime, sel.model, sel.requested_effort) == ("codex",
                                                              "gpt-5.6-sol",
                                                              "high")
    assert sel.inputs["routing"]["tier_unfulfilled"] == "no_catalogue_metadata"
    assert sel.inputs["selection"]["attempt"] == "unverified"
    assert _cands(sel)[("codex", "gpt-5.6-sol")]["attempt"] == "unverified"
    # soft work keeps the runtime's own default, as before
    soft = _select(svc, standing=[])
    assert soft.model is None and "attempt" not in soft.inputs["selection"]


def test_antigravity_with_no_default_takes_the_first_usable_in_mars_order(
        tmp_path):
    cat = [b for b in real_catalogue() if b["id"] == "antigravity"]
    svc = _svc(tmp_path, cat)
    sel = _select(svc, solution="open", reasoning="deep")
    # effort is in the id: the first in MARS's order at or above `high`
    assert (sel.runtime, sel.model) == ("antigravity", "gemini-4-argon-high")
    assert sel.inputs["selection"]["attempt"] == "unverified"


@pytest.mark.parametrize("forced", [["review"], ["authority_sensitive"]])
def test_critical_work_is_never_an_unverified_attempt(tmp_path, forced):
    svc = _svc(tmp_path, real_catalogue())
    with pytest.raises(Unsupported, match="not run automatically"):
        _select(svc, forced=forced, requires=UI, holds=FRONTIER_HELD)
    named = _select(svc, forced=forced, requires=UI, holds=FRONTIER_HELD,
                    runtime="claude", model="opus")
    assert (named.runtime, named.model) == ("claude", "opus")


def test_named_choices_are_never_substituted_for_an_attempt(tmp_path):
    svc = _svc(tmp_path, real_catalogue())
    named = _select(svc, solution="open", reasoning="deep", requires=UI,
                    holds=FRONTIER_HELD, model="claude-opus-5", effort="max")
    assert (named.runtime, named.model, named.requested_effort) == \
        ("claude", "claude-opus-5", "max")
    assert "attempt" not in named.inputs["selection"]


def test_an_unverified_attempt_needs_confirmed_capabilities(tmp_path):
    """Only claude is confirmed for the UI capabilities; with every model it
    offers held, nothing is attempted on runtimes nobody confirmed."""
    svc = _svc(tmp_path, real_catalogue())
    claude = next(b for b in real_catalogue() if b["id"] == "claude")
    every = _held(*(("claude", m["id"])
                    for m in claude["modelCatalogue"]["models"]))
    with pytest.raises(Unsupported) as got:
        _select(svc, solution="open", reasoning="deep", requires=UI, holds=every)
    words = str(got.value)
    # antigravity and kimi were eligible but NOT CONFIRMED for the UI work
    assert "antigravity" in words and "kimi-discovery" in words
    assert "could be tried either" in words and "not confirmed" in words
    assert "not lowered" in words


# -- exploratory work with discovered models (D2), no ratings ---------------------

def test_a_newly_discovered_model_is_eligible_for_exploratory_work(tmp_path):
    svc = _svc(tmp_path, real_catalogue())
    sel = _select(svc, solution="specified", reasoning="substantial",
                  exploratory=True, done_when="the three focused tests pass")
    assert sel.inputs["selection"]["exploratory"] is True
    picked = next(c for c in sel.inputs["selection"]["candidates"]
                  if c["outcome"] == "selected")
    assert picked["verdict"] == "unknown" and picked["by"] is None, \
        "a model nobody rated, with no statement needed"
    assert picked["model"] not in LEGACY_IDS
    assert "exploratory" in picked["why"]
    # the legacy-established models are still recorded, deferred
    c = _cands(sel)
    assert c[("claude", "claude-sonnet-5")]["outcome"] == "deferred"


def test_exploratory_limits_remain(tmp_path):
    svc = _svc(tmp_path, real_catalogue())
    deep_open = _select(svc, solution="open", reasoning="deep", exploratory=True,
                        done_when="it renders")
    assert "exploratory" not in deep_open.inputs["selection"]
    assert deep_open.model in ("claude-opus-5", "claude-fable-5", "gpt-6.1-sol")
    for forced in (["review"], ["authority_sensitive"]):
        sel = _select(svc, forced=forced, solution="specified", reasoning="light",
                      exploratory=True, done_when="x")
        assert "exploratory" not in sel.inputs["selection"]
        picked = next(c for c in sel.inputs["selection"]["candidates"]
                      if c["outcome"] == "selected")
        assert picked["verdict"] == "established"


# -- every candidate explained -----------------------------------------------------

def test_every_candidate_says_why(tmp_path):
    svc = _svc(tmp_path, real_catalogue(local=True, gemini=True))
    sel = _select(svc, solution="specified", reasoning="substantial",
                  requires=("drive_browser",))
    cands = sel.inputs["selection"]["candidates"]
    assert all(c.get("outcome") in ("selected", "excluded", "deferred")
               and c.get("why") for c in cands)
    by = _cands(sel)
    # named-only (gemini), tools-unsupported (local tev1), the capability gate
    assert "named-only" in by[("gemini", None)]["why"]
    tev = by[("local", "tev1:0.8b")]
    assert tev["outcome"] == "excluded" and "cannot use tools" in tev["why"]
    assert by[("codex", None)]["outcome"] == "excluded"
    assert "capability gate" in by[("codex", None)]["why"]
    low = by[("antigravity", "gemini-4-argon-low")]
    assert low["outcome"] == "excluded" and "below the medium" in low["why"]
    new = by[("claude", "claude-fable-5-2")]
    assert new["outcome"] == "deferred" and "not established" in new["why"]
    # deferred established ones say why their runtime was passed over
    deferred = [c for c in cands if c["outcome"] == "deferred"
                and c.get("verdict") == "established"]
    assert all(c["why"].startswith("established;") for c in deferred)
    # and `because` carries the summary
    line = next(b for b in sel.because if b.startswith("candidates: selected"))
    assert "excluded" in line and "deferred" in line


# -- through the real delegate and dispatch paths ---------------------------------

def test_an_unverified_attempt_is_recorded_on_the_run(world, cat_real,
                                                      cat_carrying):
    from tests._catalogue_world import delegate, latest_start, run
    cv = world["cv"]
    cat_real["ex"]._backends = [b for b in real_catalogue()
                                if b["id"] == "antigravity"]
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="find out why the panel jumps", requires=[],
                   solution="open", reasoning="deep")
    run(world, out)
    start = latest_start(cv, out["expectation"])
    d = start["detail"]
    assert start["runtime"] == "antigravity"
    assert d["selected_model"] == "gemini-4-argon-high", "sent explicitly"
    assert d["selection"]["attempt"] == "unverified"
    picked = next(c for c in d["selection"]["candidates"]
                  if c["outcome"] == "selected")
    assert (picked["verdict"], picked["attempt"]) == ("unknown", "unverified")
    because = d["selection_because"]
    assert "UNVERIFIED ATTEMPT" in because
    assert "candidates: selected antigravity gemini-4-argon-high" in because
