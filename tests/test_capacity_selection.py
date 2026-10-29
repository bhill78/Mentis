"""Capacity and known quota failures in runtime selection (owner approval
2026-10-29; lifted from Mark IV `Foundation.capacity_view` / `_by_capacity`).

Automatic selection drops a runtime exhausted by its own report or held after
a quota failure, before review avoidance; a named runtime is kept and its
exhaustion disclosed; the judge paths never ask MARS; a slow or failing
capacity read never holds selection up.
"""

from __future__ import annotations

import threading
import time

import pytest

from mentis.api.errors import RuntimeNotPresent
from mentis.core import service as service_mod
from mentis.core.service import MentisService
from mentis.execution import FakeExecution


def _backend(rid, models=()):
    return {"id": rid, "kind": "acp", "available": True, "reason": None,
            "models": list(models), "efforts": [],
            "supports": {"mcp": ["stdio"]}}


def _window(label, used, resets_in, seconds, group=None):
    now = time.time()
    return {"label": label, "usedFraction": used, "windowSeconds": seconds,
            "resetsAt": now + resets_in, "group": group, "raw": {}}


def _report(*windows, groups=None, notes=()):
    return {"observedAt": time.time(), "plan": None, "notes": list(notes),
            "modelGroups": dict(groups or {}), "windows": list(windows)}


class CountingExecution(FakeExecution):
    """A FakeExecution whose `capacity()` is counted, and may be slow or fail."""

    def __init__(self, backends, capacity=None, *, delay=0.0, fail=None):
        super().__init__(backends, capacity=capacity)
        self.calls = 0
        self.delay = delay
        self.fail = fail
        self.release = threading.Event()

    def capacity(self):
        self.calls += 1
        if self.delay:
            self.release.wait(self.delay)
        if self.fail:
            raise self.fail
        return super().capacity()


def _svc(tmp_path, backends, capacity=None, **kw):
    ex = CountingExecution(backends, capacity, **kw)
    return MentisService(str(tmp_path / "instances"), execution=ex), ex


TWO = [_backend("claude"), _backend("codex")]


def test_exhausted_by_its_own_report_is_excluded(tmp_path):
    svc, _ = _svc(tmp_path, TWO, {
        "claude": _report(_window("five_hour", 1.0, 3600, 18000)),
        "codex": _report(_window("primary", 0.2, 3600, 18000))})
    sel = svc.execution_select()
    assert sel.runtime == "codex"
    assert "claude" in sel.excluded
    because = " · ".join(sel.because)
    assert "excluded as exhausted: ['claude']" in because
    assert "claude: exhausted by its own report (five_hour at 100%" in because
    # COMPACT VIEWS ONLY: never the reading.
    cap = sel.inputs["capacity"]
    assert set(cap) == {"claude", "codex"}
    assert all(set(v) == {"state", "why", "expires_at", "budget_left"}
               for v in cap.values())
    assert cap["claude"]["state"] == "exhausted"
    assert cap["claude"]["expires_at"] == pytest.approx(time.time() + 3600, abs=5)
    assert cap["codex"]["budget_left"] == pytest.approx(0.8)
    assert "capacity_gate" in sel.dimensions_used


def test_no_report_is_unknown_and_says_the_runtimes_own_note(tmp_path):
    svc, _ = _svc(tmp_path, TWO, {
        "claude": _report(notes=["gemini does not report capacity over ACP"])})
    view = svc.capacity_view("claude", fresh=True)
    assert view["state"] == "unknown"
    assert "does not report capacity over ACP" in view["why"]
    assert "not reported by MARS" in svc.capacity_view("codex")["why"]


def test_model_groups_judge_the_group_that_serves_the_model(tmp_path):
    agy = _backend("antigravity", ["argon", "opus"])
    groups = {"argon": "Gemini", "opus": "Claude and GPT"}
    svc, _ = _svc(tmp_path, [agy], {"antigravity": _report(
        _window("weekly", 1.0, 3600, 604800, "Gemini"),
        _window("weekly", 0.3, 7200, 604800, "Claude and GPT"),
        groups=groups)})
    assert svc.capacity_view("antigravity", "argon", fresh=True)["state"] == "exhausted"
    assert svc.capacity_view("antigravity", "opus")["state"] == "available"
    # No model placed: exhausted only if every group is.
    assert svc.capacity_view("antigravity")["state"] == "available"
    assert svc.execution_select(model="opus").runtime == "antigravity"
    with pytest.raises(RuntimeNotPresent, match="group Gemini at 100%"):
        svc.execution_select(model="argon")
    assert svc.execution_usable("antigravity", model="argon")
    assert svc.execution_usable("antigravity", model="opus") is None


def test_every_group_full_is_exhausted_with_no_model(tmp_path):
    agy = _backend("antigravity", ["argon", "opus"])
    svc, _ = _svc(tmp_path, [agy], {"antigravity": _report(
        _window("weekly", 1.0, 3600, 604800, "Gemini"),
        _window("weekly", 1.0, 7200, 604800, "Claude and GPT"),
        groups={"argon": "Gemini", "opus": "Claude and GPT"})})
    v = svc.capacity_view("antigravity", fresh=True)
    assert v["state"] == "exhausted"
    # Either group freeing makes it usable again: the sooner reset.
    assert v["expires_at"] == pytest.approx(time.time() + 3600, abs=5)


def test_a_hold_excludes_until_it_expires(tmp_path):
    svc, _ = _svc(tmp_path, TWO)
    now = time.time()
    hold = {"until": now + 600, "why": "claude: rate_limited at 16:22",
            "model": None, "since": now - 60, "basis": "act-1"}
    sel = svc.execution_select(holds={"claude": hold})
    assert sel.runtime == "codex" and "claude" in sel.excluded
    assert "claude: rate_limited at 16:22" in " · ".join(sel.because)
    assert sel.inputs["holds"] == {"claude": hold}
    assert sel.inputs["capacity"]["claude"]["expires_at"] == hold["until"]
    expired = {**hold, "until": now - 1}
    seen = {svc.execution_select(holds={"claude": expired}).runtime
            for _ in range(2)}
    assert "claude" in seen, "an expired hold excludes nothing"
    assert svc.execution_usable("claude", holds={"claude": hold}).startswith(
        "claude: rate_limited")
    assert svc.execution_usable("claude", holds={"claude": expired}) is None


def test_a_hold_naming_no_model_does_not_block_an_explicit_model(tmp_path):
    svc, _ = _svc(tmp_path, [_backend("claude", ["opus"]), _backend("codex")])
    now = time.time()
    anymodel = {"until": now + 600, "why": "claude: rate_limited",
                "model": None, "since": now, "basis": "act-1"}
    sel = svc.execution_select(model="opus", holds={"claude": anymodel})
    assert sel.runtime == "claude"
    assert svc.execution_usable("claude", model="opus",
                                holds={"claude": anymodel}) is None
    assert svc.execution_usable("claude", holds={"claude": anymodel})
    # A hold naming the model does block a run of that model.
    onmodel = {**anymodel, "model": "opus"}
    with pytest.raises(RuntimeNotPresent):
        svc.execution_select(model="opus", holds={"claude": onmodel})


def test_a_named_exhausted_runtime_is_kept_and_disclosed(tmp_path):
    svc, _ = _svc(tmp_path, TWO, {
        "claude": _report(_window("five_hour", 1.0, 3600, 18000))})
    sel = svc.execution_select(runtime="claude")
    assert sel.runtime == "claude"
    [said] = sel.inputs["disclosed"]
    assert "exhausted by its own report" in said and "not substituted" in said
    assert said in sel.because
    assert sel.inputs["capacity"] == {"claude": {
        k: sel.inputs["capacity"]["claude"][k]
        for k in ("state", "why", "expires_at", "budget_left")}}
    # Not exhausted: nothing disclosed.
    assert "disclosed" not in svc.execution_select(runtime="codex").inputs


def test_everything_exhausted_is_refused_naming_the_soonest_expiry(tmp_path):
    svc, _ = _svc(tmp_path, TWO, {
        "claude": _report(_window("five_hour", 1.0, 7200, 18000))})
    now = time.time()
    cooldown = {"until": now + 3600, "why": "codex: rate_limited, no reset reported",
                "model": None, "since": now, "basis": "act-2"}
    with pytest.raises(RuntimeNotPresent) as got:
        svc.execution_select(holds={"codex": cooldown})
    words = str(got.value)
    assert "every eligible runtime is exhausted" in words
    assert "soonest back is codex" in words
    assert "60-minute cooldown" in words
    # The soonest resting on a reported reset says nothing of the cooldown.
    reported = {**cooldown, "until": now + 9000, "since": now - 10}
    with pytest.raises(RuntimeNotPresent) as got:
        svc.execution_select(holds={"codex": reported})
    assert "soonest back is claude" in str(got.value)
    assert "cooldown" not in str(got.value)


def test_exhaustion_is_applied_before_review_avoidance(tmp_path):
    svc, _ = _svc(tmp_path, TWO, {
        "claude": _report(_window("five_hour", 1.0, 3600, 18000))})
    sel = svc.execution_select(avoid="codex")
    assert sel.runtime == "codex", "the author's runtime is the only one left"
    assert "independence by runtime was not achievable" in " · ".join(sel.because)


def test_continuity_wins_only_among_the_unexhausted(tmp_path):
    svc, _ = _svc(tmp_path, [_backend("claude"), _backend("codex"),
                             _backend("local")], {
        "claude": _report(_window("five_hour", 1.0, 3600, 18000))})
    sel = svc.execution_select(prefer="claude")
    assert sel.runtime != "claude" and "continuity" not in sel.dimensions_used
    assert svc.execution_select(prefer="local").runtime == "local"


def test_ranking_prefers_budget_that_would_expire_unused(tmp_path):
    svc, _ = _svc(tmp_path, [_backend("claude"), _backend("codex"),
                             _backend("local")], {
        "claude": _report(_window("seven_day", 0.5, 6 * 86400, 604800)),
        "codex": _report(_window("secondary", 0.5, 3600, 604800))})
    svc._last_selected["codex"] = 99                  # rotation would avoid it
    sel = svc.execution_select()
    assert sel.runtime == "codex"
    assert [r["runtime"] for r in sel.inputs["ranking"]] == ["codex", "claude", "local"]
    assert "least_recently_selected" not in sel.dimensions_used


def test_the_judge_paths_never_ask_mars(tmp_path):
    svc, ex = _svc(tmp_path, TWO, {
        "claude": _report(_window("five_hour", 1.0, 3600, 18000))})
    assert svc.execution_usable("claude") is None, "nothing held yet: unknown"
    assert svc.capacity_view("claude")["state"] == "unknown"
    assert ex.calls == 0
    svc.execution_select()
    assert ex.calls == 1
    # What selection read is held, and the judge uses it -- still no call.
    assert "exhausted" in svc.execution_usable("claude")
    assert svc.capacity_view("claude")["state"] == "exhausted"
    assert ex.calls == 1


def test_a_slow_capacity_read_does_not_hold_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(service_mod, "CAPACITY_WAIT_S", 0.2)
    svc, ex = _svc(tmp_path, TWO, {
        "claude": _report(_window("five_hour", 1.0, 3600, 18000))}, delay=30)
    t0 = time.monotonic()
    first = svc.execution_select()
    second = svc.execution_select()
    assert time.monotonic() - t0 < 5
    assert ex.calls == 1, "one read in flight, shared"
    assert "did not arrive" in first.inputs["capacity"]["claude"]["why"]
    assert {first.runtime, second.runtime} == {"claude", "codex"}
    ex.release.set()
    deadline = time.monotonic() + 5
    while svc._capacity is None and time.monotonic() < deadline:
        time.sleep(0.01)
    # The late answer is kept and used, without asking again.
    assert svc.execution_select().runtime == "codex"
    assert "exhausted" in svc.execution_usable("claude")
    assert ex.calls == 1


def test_a_failed_capacity_read_is_kept_too(tmp_path):
    svc, ex = _svc(tmp_path, TWO, fail=RuntimeError("MARS went away"))
    sel = svc.execution_select()
    assert "MARS went away" in sel.inputs["capacity"]["claude"]["why"]
    svc.execution_select()
    svc.capacity_observe("claude")
    assert ex.calls == 1, "a failure is cached like an answer"
