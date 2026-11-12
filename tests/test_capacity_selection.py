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


def _svc(tmp_path, backends, capacity=None, *, primed=True, **kw):
    """A service, and by default one that has read MARS's capacity once, as a
    server does at start: selection never waits for a read (WS-P)."""
    ex = CountingExecution(backends, capacity, **kw)
    svc = MentisService(str(tmp_path / "instances"), execution=ex)
    if primed and not kw.get("delay"):
        svc._capacity_read(threading.Event())
        ex.calls = 0
    return svc, ex


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
    # A NAMED MODEL WHOSE EVERY OFFERING RUNTIME IS EXHAUSTED runs there, said.
    argon = svc.execution_select(model="argon")
    assert argon.runtime == "antigravity" and argon.model == "argon"
    assert any("group Gemini at 100%" in d for d in argon.inputs["disclosed"])
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


def test_a_hold_naming_no_model_matches_every_model(tmp_path):
    svc, _ = _svc(tmp_path, [_backend("claude", ["opus"]), _backend("codex")])
    now = time.time()
    anymodel = {"until": now + 600, "why": "claude: rate_limited",
                "model": None, "since": now, "basis": "act-1"}
    assert svc.execution_usable("claude", model="opus",
                                holds={"claude": anymodel})
    assert svc.execution_usable("claude", holds={"claude": anymodel})
    # The named model is still run where it is offered, and that is said.
    sel = svc.execution_select(model="opus", holds={"claude": anymodel})
    assert sel.runtime == "claude" and sel.model == "opus"
    assert any("run as named" in d for d in sel.inputs["disclosed"])
    # A hold naming the model matches that model, and not another.
    onmodel = {**anymodel, "model": "opus"}
    sel = svc.execution_select(model="opus", holds={"claude": onmodel})
    assert sel.model == "opus" and sel.inputs["disclosed"]
    assert svc.execution_usable("claude", model="sonnet",
                                holds={"claude": onmodel}) is None


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


def _landed(svc, s=5):
    deadline = time.monotonic() + s
    while svc._capacity is None and time.monotonic() < deadline:
        time.sleep(0.01)
    return svc._capacity is not None


def test_the_judge_paths_never_ask_mars(tmp_path):
    svc, ex = _svc(tmp_path, TWO, {
        "claude": _report(_window("five_hour", 1.0, 3600, 18000))}, primed=False)
    assert svc.execution_usable("claude") is None, "nothing held yet: unknown"
    assert svc.capacity_view("claude")["state"] == "unknown"
    assert ex.calls == 0
    svc.execution_select()
    assert _landed(svc) and ex.calls == 1
    # What selection had read is held, and the judge uses it -- still no call.
    assert "exhausted" in svc.execution_usable("claude")
    assert svc.capacity_view("claude")["state"] == "exhausted"
    assert ex.calls == 1


def test_selection_never_waits_for_capacity_even_with_nothing_held(tmp_path):
    """WS-P: a server's first selection, before any capacity answer has landed, does not wait
    for MARS. The runtimes read as unknown, said so; the read goes on in the background."""
    svc, ex = _svc(tmp_path, TWO, {
        "claude": _report(_window("five_hour", 1.0, 3600, 18000))}, delay=30)
    t0 = time.monotonic()
    first = svc.execution_select()
    second = svc.execution_select()
    assert time.monotonic() - t0 < 1
    assert ex.calls == 1, "one read in flight, shared"
    assert "no capacity answer is held yet" in first.inputs["capacity"]["claude"]["why"]
    assert first.inputs["capacity"]["claude"]["state"] == "unknown"
    assert first.inputs["timing"]["capacity_ms"] < 500 and "total_ms" in first.inputs["timing"]
    assert {first.runtime, second.runtime} == {"claude", "codex"}
    ex.release.set()
    assert _landed(svc)
    # The late answer is kept and used, without asking again.
    assert svc.execution_select().runtime == "codex"
    assert "exhausted" in svc.execution_usable("claude")
    assert ex.calls == 1


def test_a_failed_capacity_read_is_kept_too(tmp_path):
    svc, ex = _svc(tmp_path, TWO, fail=RuntimeError("MARS went away"), primed=False)
    svc.execution_select()
    assert _landed(svc)
    sel = svc.execution_select()
    assert "MARS went away" in sel.inputs["capacity"]["claude"]["why"]
    svc.execution_select()
    svc.capacity_observe("claude")
    assert ex.calls == 1, "a failure is cached like an answer"


# -- #1167: Antigravity's capacity recognised and used ------------------------

WEEK = 604800
HOUR = 3600
AGY = _backend("antigravity", ["gemini-flash", "opus", "argon"])
AGY_GROUPS = {"gemini-flash": "Gemini Models", "opus": "Claude and GPT models",
              "argon": "Gemini 4 Argon"}


def _antigravity(*, argon_used=0.054, beyond=200, flash_used=0.0):
    """`agy /usage` as read 2026-11-02 (#1177): two untouched groups whose
    resets are the call's time plus the window, stamped after the reading's
    `observedAt`, and Argon part used with its own reset 4d21h away."""
    at = float(int(time.time()))

    def window(label, used, seconds, reset, group):
        return {"label": label, "usedFraction": used, "windowSeconds": seconds,
                "resetsAt": at + reset, "group": group, "raw": {}}

    return {"observedAt": at, "plan": None, "notes": [], "modelGroups": AGY_GROUPS,
            "windows": [
                window("weekly", flash_used, WEEK, WEEK + beyond, "Gemini Models"),
                window("5h", 0.0, 18000, 18000 + beyond, "Gemini Models"),
                window("weekly", 0.0, WEEK, WEEK + beyond, "Claude and GPT models"),
                window("5h", 0.0, 18000, 18000 + beyond, "Claude and GPT models"),
                window("weekly", argon_used, WEEK, 4 * 86400 + 21 * HOUR,
                       "Gemini 4 Argon")]}


def _supplied(**agy):
    """The figures selection was reported on: Antigravity 95% left, Codex 52%
    left resetting in about 56h, Claude 13% left resetting in about 7h42m."""
    return ([_backend("claude"), _backend("codex"), AGY],
            {"claude": _report(_window("seven_day", 0.87, 7.7 * HOUR, WEEK)),
             "codex": _report(_window("secondary", 0.48, 56.4 * HOUR, WEEK)),
             "antigravity": _antigravity(**agy)})


def _plain(left, resets_in, label="weekly", seconds=WEEK):
    return _report(_window(label, 1.0 - left, resets_in, seconds))


def _picks(svc, n, **kw):
    return [svc.execution_select(**kw).runtime for _ in range(n)]


def _row(sel, runtime):
    return next(r for r in sel.inputs["ranking"] if r["runtime"] == runtime)


@pytest.mark.parametrize("beyond,state", [
    (0, "available"), (200, "available"), (299, "available"), (300, "available"),
    (301, "unknown"), (400, "unknown"),
    (2 * 365 * 86400, "unknown")])          # far beyond any lateness
@pytest.mark.parametrize("runtime,group", [
    ("claude", None), ("codex", None), ("antigravity", "Gemini Models")])
def test_a_reset_slightly_beyond_nominal_is_current_on_every_runtime(
        tmp_path, runtime, group, beyond, state):
    at = float(int(time.time()))
    svc, _ = _svc(tmp_path, [_backend(runtime)], {runtime: {
        "observedAt": at, "plan": None, "notes": [], "modelGroups": {},
        "windows": [{"label": "weekly", "usedFraction": 0.0, "windowSeconds": WEEK,
                     "resetsAt": at + WEEK + beyond, "group": group, "raw": {}}]}})
    v = svc.capacity_view(runtime, fresh=True)
    assert v["state"] == state, v["why"]
    assert v["budget_left"] == (1.0 if state == "available" else None)


def test_a_reset_in_milliseconds_is_still_not_believed(tmp_path):
    at = float(int(time.time()))
    svc, _ = _svc(tmp_path, [_backend("claude")], {"claude": {
        "observedAt": at, "plan": None, "notes": [], "modelGroups": {},
        "windows": [{"label": "weekly", "usedFraction": 0.0, "windowSeconds": WEEK,
                     "resetsAt": at * 1000, "group": None, "raw": {}}]}})
    assert svc.capacity_view("claude", fresh=True)["state"] == "unknown"


def test_a_window_in_its_last_seconds_is_still_judged(tmp_path):
    def view(*windows):
        svc, _ = _svc(tmp_path, [_backend("claude")],
                      {"claude": _report(*windows)})
        return svc.capacity_view("claude", fresh=True)

    four_minutes = 240
    assert view(_window("seven_day", 1.0, four_minutes, WEEK))["state"] == "exhausted"
    v = view(_window("five_hour", 1.0, four_minutes, 18000),
             _window("seven_day", 0.5, 86400, WEEK))
    assert v["state"] == "exhausted"
    v = view(_window("seven_day", 0.4, four_minutes, WEEK))
    assert v["state"] == "available"
    assert v["budget_left"] == pytest.approx(0.6)


def test_a_reset_gone_by_is_not_current(tmp_path):
    # Reported already past when it was read, and past since it was read.
    assert _svc(tmp_path, [_backend("claude")], {"claude": _report(
        _window("seven_day", 0.1, -5, WEEK))})[0].capacity_view(
            "claude", fresh=True)["state"] == "unknown"
    gone = _report(_window("seven_day", 0.1, -5, WEEK))
    gone["observedAt"] = time.time() - 60
    assert _svc(tmp_path, [_backend("claude")], {"claude": gone})[0].capacity_view(
        "claude", fresh=True)["state"] == "unknown"


def test_the_reported_antigravity_case_has_a_known_budget(tmp_path):
    """Before the correction, one second past the nominal week put the whole
    runtime in the unknown tier, whatever Argon's 95% said."""
    svc, _ = _svc(tmp_path, [AGY], {"antigravity": _antigravity()})
    v = svc.capacity_view("antigravity", fresh=True)
    assert v["state"] == "available"
    assert v["budget_left"] == pytest.approx(0.946)
    # A group's own run is judged on that group's own figures.
    argon = svc.capacity_view("antigravity", "argon")
    assert argon["budget_left"] == pytest.approx(0.946)
    assert argon["expires_at"] < v["expires_at"]
    assert svc.capacity_view("antigravity", "opus")["budget_left"] == 1.0


def test_antigravitys_exhausted_groups(tmp_path):
    svc, _ = _svc(tmp_path, [AGY], {"antigravity": _antigravity(argon_used=1.0)})
    v = svc.capacity_view("antigravity", fresh=True)
    assert v["state"] == "available", "the other two groups are untouched"
    assert v["budget_left"] == 1.0, "a full group is not what is left to use"
    assert "group Gemini 4 Argon exhausted, others not" in v["why"]
    assert svc.capacity_view("antigravity", "argon")["state"] == "exhausted"
    argon = svc.execution_select(model="argon")
    assert argon.model == "argon"
    assert any("group Gemini 4 Argon at 100%" in d
               for d in argon.inputs["disclosed"])
    assert svc.execution_select(model="opus").runtime == "antigravity"
    # Antigravity's lowest live group sets its budget: below the guard's line.
    low, _ = _svc(tmp_path, [AGY], {"antigravity": _antigravity(argon_used=0.55)})
    assert low.capacity_view("antigravity", fresh=True)["budget_left"] == \
        pytest.approx(0.45)


def test_the_supplied_figures_select_in_this_order(tmp_path):
    backends, capacity = _supplied()
    svc, _ = _svc(tmp_path, backends, capacity)
    assert _picks(svc, 9) == ["claude", "claude", "claude", "antigravity", "codex",
                              "claude", "claude", "antigravity", "codex"]


def test_the_ranking_says_what_the_guard_did(tmp_path):
    backends, capacity = _supplied()
    svc, _ = _svc(tmp_path, backends, capacity)
    first = svc.execution_select()
    assert [r["runtime"] for r in first.inputs["ranking"]] == [
        "claude", "codex", "antigravity"], "unused per hour, descending"
    assert "capacity_expiry" in first.dimensions_used
    assert "anti_starvation_guard" not in first.dimensions_used
    assert "the largest share of its budget" in first.because[-2]
    agy = _row(first, "antigravity")
    assert agy["substantial"] is True and agy["overdue"] is False
    assert agy["missed_opportunities"] == 0 and agy["overdue_at"] == 3
    assert agy["overdue_distance"] == -3 and agy["guard_selected"] is False
    assert _row(first, "claude")["substantial"] is False
    _picks(svc, 2)
    guard = svc.execution_select()
    assert guard.runtime == "antigravity"
    assert "anti_starvation_guard" in guard.dimensions_used
    assert "capacity_expiry" not in guard.dimensions_used
    top = guard.inputs["ranking"][0]
    assert top["runtime"] == "antigravity" and top["guard_selected"] is True
    assert top["overdue"] is True and top["overdue_distance"] == 0
    assert top["normal_order"] == 2
    assert [r["runtime"] for r in guard.inputs["ranking"]] == [
        "antigravity", "codex", "claude"], "both overdue, then the normal order"
    because = " · ".join(guard.because)
    assert "runtime antigravity chosen: anti-starvation guard" in because
    assert "missed 3 automatic choices" in because
    assert "by pace alone it would have been claude" in because
    assert "the largest share of its budget" not in because
    assert "tied with ['codex']" in because


def test_expiry_stays_the_normal_order(tmp_path):
    svc, _ = _svc(tmp_path, [_backend("claude"), _backend("codex"), AGY], {
        "claude": _plain(0.79, 0.5 * HOUR),
        "codex": _plain(0.60, 100 * HOUR),
        "antigravity": _plain(0.95, 160 * HOUR)})
    assert _picks(svc, 3) == ["claude"] * 3, "the near reset wins until one is due"
    # Codex and Claude, as they were: sooner reset first at equal budget.
    two, _ = _svc(tmp_path, TWO, {"claude": _plain(0.3, 6 * 86400),
                                  "codex": _plain(0.3, HOUR)})
    assert _picks(two, 8) == ["codex"] * 8, "neither is substantial: no guard"


def test_equal_figures_keep_the_least_recently_selected_rule(tmp_path):
    svc, _ = _svc(tmp_path, TWO)
    sel = svc.execution_select()
    assert sel.runtime == "claude", "unknown, never selected: catalogue order"
    assert "least_recently_selected" in sel.dimensions_used
    assert svc.execution_select().runtime == "codex"


def test_the_guards_bound_follows_the_known_candidates(tmp_path):
    # Two known: at least two misses. An unknown candidate is not counted.
    svc, _ = _svc(tmp_path, [_backend("claude"), _backend("codex"), _backend("local")],
                  {"claude": _plain(0.9, HOUR), "codex": _plain(0.5, 6 * 86400)})
    sel = svc.execution_select()
    assert _row(sel, "codex")["overdue_at"] == 2
    assert _row(sel, "local")["tier"] == 1 and _row(sel, "local")["substantial"] is False
    assert _picks(svc, 2) == ["claude", "codex"], "chosen on its second miss"
    assert svc._guard_missed.get("local", 0) == 0, "only a known candidate misses"
    # Alone: nothing to miss.
    one, _ = _svc(tmp_path, [_backend("codex")], {"codex": _plain(0.9, HOUR)})
    assert _picks(one, 5) == ["codex"] * 5
    # Four known: four misses.
    four, _ = _svc(tmp_path, [_backend(n) for n in ("a", "b", "c", "d")], {
        "a": _plain(0.9, HOUR), "b": _plain(0.8, 50 * HOUR),
        "c": _plain(0.2, 60 * HOUR), "d": _plain(0.2, 70 * HOUR)})
    assert _picks(four, 5) == ["a", "a", "a", "a", "b"]


@pytest.mark.parametrize("left,guarded", [(0.5, True), (0.4999, False)])
def test_the_threshold_is_a_cliff_at_one_half(tmp_path, left, guarded):
    svc, _ = _svc(tmp_path, TWO, {"claude": _plain(0.9, HOUR),
                                  "codex": _plain(left, 100 * HOUR)})
    sels = [svc.execution_select() for _ in range(30)]
    got = sum(s.runtime == "codex" for s in sels)
    assert (got > 0) is guarded, got
    row = _row(sels[0], "codex")
    assert row["substantial"] is guarded
    assert row["budget_left"] == pytest.approx(left)
    # The exact figure is said: 49.99% does not read as a substantial 50%.
    assert f"{left:g} left is {'' if guarded else 'not '}substantial" in \
        " · ".join(sels[0].because)


def test_most_missed_then_older_then_more_budget_then_pace_then_catalogue(tmp_path):
    def chosen(codex_missed=4, agy_missed=4, last=None, codex=0.6, agy=0.9,
               agy_reset=100 * HOUR):
        svc, _ = _svc(tmp_path, [_backend("claude"), _backend("codex"), AGY], {
            "claude": _plain(0.1, 2 * HOUR),
            "codex": _plain(codex, 100 * HOUR),
            "antigravity": _plain(agy, agy_reset)})
        svc._guard_missed.update(codex=codex_missed, antigravity=agy_missed)
        svc._last_selected.update(last or {})
        return svc.execution_select()

    assert chosen(codex_missed=5).runtime == "codex", "most missed"
    sel = chosen(last={"codex": 1, "antigravity": 2})
    assert sel.runtime == "codex", "older last selection"
    assert "least_recently_selected" in sel.dimensions_used
    sel = chosen()
    assert sel.runtime == "antigravity", "more budget left"
    assert "least_recently_selected" not in sel.dimensions_used
    assert chosen(codex=0.9, agy_reset=50 * HOUR).runtime == "antigravity", "pace"
    assert chosen(codex=0.9).inputs["ranking"][0]["runtime"] == "codex", "catalogue"


def test_the_guard_starts_again_after_a_restart(tmp_path):
    backends, capacity = _supplied()
    svc, _ = _svc(tmp_path, backends, capacity)
    assert _picks(svc, 2) == ["claude", "claude"]
    restarted, _ = _svc(tmp_path, backends, capacity)
    assert _picks(restarted, 5) == [
        "claude", "claude", "claude", "antigravity", "codex"], (
            "this process's history only: what was missed before is not kept")


@pytest.mark.parametrize("between", [0, 1, 3, 5])
@pytest.mark.parametrize("how", [{"prefer": "claude"}, {"runtime": "claude"}])
def test_continuity_and_named_traffic_change_nothing(tmp_path, between, how):
    """The review's table (#1193): one global counter let continuity turn the
    guard into the primary policy, and Claude's expiring 79% got 2 of 30."""
    svc, _ = _svc(tmp_path, [_backend("claude"), _backend("codex"), AGY], {
        "claude": _plain(0.79, 0.5 * HOUR),
        "codex": _plain(0.60, 100 * HOUR),
        "antigravity": _plain(0.95, 160 * HOUR)})
    got = []
    for _ in range(30):
        missed = dict(svc._guard_missed)
        for _ in range(between):
            svc.execution_select(**how)
        assert svc._guard_missed == missed
        got.append(svc.execution_select().runtime)
    assert (got.count("claude"), got.count("codex"), got.count("antigravity")) == (
        16, 7, 7)


def test_a_named_or_continued_runtime_keeps_what_it_missed(tmp_path):
    backends, capacity = _supplied()
    svc, _ = _svc(tmp_path, backends, capacity)
    _picks(svc, 3)
    assert svc._guard_missed["antigravity"] == 3
    assert svc.execution_select(runtime="antigravity").runtime == "antigravity"
    assert svc.execution_select(prefer="antigravity").runtime == "antigravity"
    assert svc._guard_missed["antigravity"] == 3, "not an automatic choice"
    assert "continuity" in svc.execution_select(prefer="codex").dimensions_used


def test_a_runtime_narrowed_away_does_not_age(tmp_path):
    """The review's worst case (#1195): picks a runtime was no candidate for
    counted against the others and starved the expiring one."""
    backends = [_backend("claude"), _backend("codex"), AGY,
                {**_backend("nomcp"), "supports": {"mcp": []}}]
    now = time.time()
    capacity = {"claude": _plain(0.13, 7.7 * HOUR),
                "codex": _plain(0.52, 56.4 * HOUR),
                "antigravity": _antigravity(),
                "nomcp": _plain(0.9, 100 * HOUR)}
    hold = {"until": now + 600, "why": "codex: rate_limited", "model": None,
            "since": now, "basis": "act-1"}
    narrowings = {
        "model": dict(model="opus"),
        "avoid": dict(avoid="codex"),
        "requires": dict(requires=["call_mentis_tools"]),
        "held": dict(holds={"codex": hold})}

    # Model: only Antigravity is a candidate, so nothing else misses anything.
    svc, _ = _svc(tmp_path, backends, capacity)
    assert _picks(svc, 6, **narrowings["model"]) == ["antigravity"] * 6
    assert svc._guard_missed == {"antigravity": 0}
    # Avoid and held: Codex was not a candidate.
    for kw in (narrowings["avoid"], narrowings["held"]):
        svc, _ = _svc(tmp_path, backends, capacity)
        sels = [svc.execution_select(**kw) for _ in range(6)]
        assert all(s.runtime != "codex" for s in sels)
        assert svc._guard_missed.get("codex", 0) == 0
    # Requires: the runtime that cannot take it was not a candidate.
    svc, _ = _svc(tmp_path, backends, capacity)
    for _ in range(6):
        assert svc.execution_select(**narrowings["requires"]).runtime != "nomcp"
    assert svc._guard_missed.get("nomcp", 0) == 0
    # With those mixed in, plain picks keep their order among themselves.
    plain = [b for b in backends if b["id"] != "nomcp"]
    svc, _ = _svc(tmp_path, plain, capacity)
    got = []
    for _ in range(9):
        svc.execution_select(model="opus")
        svc.execution_select(model="opus")
        got.append(svc.execution_select().runtime)
    assert got.count("claude") > got.count("antigravity"), got
    assert "codex" in got


def test_a_review_still_avoids_the_author_when_the_author_is_overdue(tmp_path):
    backends, capacity = _supplied()
    svc, _ = _svc(tmp_path, backends, capacity)
    _picks(svc, 3)
    assert svc._guard_missed["antigravity"] == 3
    sel = svc.execution_select(avoid="antigravity")
    assert sel.runtime != "antigravity"
    assert "antigravity" in sel.excluded
    assert "avoided so the review runs on a different runtime" in " · ".join(sel.because)
    assert svc._guard_missed["antigravity"] == 3, "not a candidate: not aged"
    assert "review_independence" in sel.dimensions_used


WITH_GEMINI = [_backend("gemini", ["flash"]), _backend("codex")]


def test_gemini_runs_when_named(tmp_path):
    svc, _ = _svc(tmp_path, WITH_GEMINI, {
        "gemini": _report(_window("daily", 1.0, HOUR, 86400))})
    sel = svc.execution_select(runtime="gemini")
    assert sel.runtime == "gemini", "named, not substituted"
    assert "not substituted" in sel.inputs["disclosed"][0]
    assert "named_only" not in sel.inputs and sel.excluded == ()
    assert svc._guard_missed == {}


def test_gemini_is_not_chosen_automatically(tmp_path):
    svc, _ = _svc(tmp_path, WITH_GEMINI, {
        "gemini": _plain(0.99, HOUR), "codex": _plain(0.1, 100 * HOUR)})
    sels = [svc.execution_select() for _ in range(6)]
    assert {s.runtime for s in sels} == {"codex"}, "whatever its capacity says"
    sel = sels[0]
    assert sel.inputs["named_only"] == ["gemini"] and "gemini" in sel.excluded
    assert "gemini" not in sel.inputs["capacity"]
    assert "gemini" not in sel.inputs["eligible"]
    assert "['gemini'] not considered: it runs only when named" in sel.because
    assert "gemini" not in svc._guard_missed


def test_gemini_alone_is_a_refusal_that_says_why(tmp_path):
    svc, _ = _svc(tmp_path, [_backend("gemini", ["flash"])])
    with pytest.raises(RuntimeNotPresent, match="runs only when named"):
        svc.execution_select()
    assert svc.execution_select(runtime="gemini").runtime == "gemini"
    # What eligibility left is gemini alone: a model only it offers.
    both, _ = _svc(tmp_path, WITH_GEMINI)
    with pytest.raises(RuntimeNotPresent, match="only \\['gemini'\\] could take"):
        both.execution_select(model="flash")
    assert both.execution_select(runtime="gemini", model="flash").runtime == "gemini"
    # ...or a requirement only it meets.
    lacking = {**_backend("codex"), "supports": {"mcp": []}}
    needs, _ = _svc(tmp_path, [_backend("gemini"), lacking])
    with pytest.raises(RuntimeNotPresent, match="runs only when named"):
        needs.execution_select(requires=["call_mentis_tools"])


def test_gemini_does_not_rescue_a_full_house(tmp_path):
    svc, _ = _svc(tmp_path, WITH_GEMINI, {
        "gemini": _plain(0.9, HOUR),
        "codex": _report(_window("primary", 1.0, HOUR, 18000))})
    with pytest.raises(RuntimeNotPresent, match="every eligible runtime is exhausted"):
        svc.execution_select()


def test_a_handle_on_gemini_is_not_continued_automatically(tmp_path):
    svc, _ = _svc(tmp_path, WITH_GEMINI)
    sel = svc.execution_select(prefer="gemini")
    assert sel.runtime == "codex" and "continuity" not in sel.dimensions_used
    assert ("the handle here runs on gemini, which runs only when named; "
            "not continued") in sel.because


def test_a_review_with_only_gemini_left_says_so(tmp_path):
    svc, _ = _svc(tmp_path, WITH_GEMINI)
    sel = svc.execution_select(avoid="codex")
    assert sel.runtime == "codex", "gemini is no way out of a self-review"
    because = " · ".join(sel.because)
    assert "['gemini'] run only when named" in because
    assert "independence by runtime was not achievable" in because
    # Reviewing gemini's own work goes elsewhere, and excludes it once.
    sel = svc.execution_select(avoid="gemini")
    assert sel.runtime == "codex" and sel.excluded.count("gemini") == 1
    assert "avoided so the review runs on a different runtime" in " · ".join(sel.because)


def test_a_default_does_not_yield_to_gemini(tmp_path):
    """A declared default gives way to what automatic selection would prefer,
    and automatic selection would not choose gemini."""
    gemini = {**_backend("gemini"), "capabilities": ["build_ui"]}
    svc, _ = _svc(tmp_path, [gemini, _backend("kimi-k3")])
    assert svc.execution_usable("kimi-k3", ["build_ui"]) is None
    assert svc.execution_usable("gemini", ["build_ui"]) is None, "it can be named"


def test_an_account_window_is_shared_and_a_group_window_serves_only_its_models(tmp_path):
    """Claude's `seven_day` (all models) beside its Fable-only `seven_day_fable`
    (model-selection integration, found live 2026-11-12): a model outside the
    Fable group is judged on the shared window, never on Fable's; a Fable model
    on both; a full shared window stops every model; a full Fable window stops
    only Fable models."""
    claude = _backend("claude", ["sonnet", "fable"])
    groups = {"fable": "fable"}
    svc, _ = _svc(tmp_path, [claude], {"claude": _report(
        _window("seven_day", 0.32, 3600 * 100, 604800),
        _window("seven_day_fable", 0.02, 3600 * 100, 604800, "fable"),
        groups=groups)})
    sonnet = svc.capacity_view("claude", "sonnet", fresh=True)
    assert sonnet["state"] == "available"
    assert sonnet["budget_left"] == pytest.approx(0.68)
    assert "seven_day_fable" not in sonnet["why"]
    fable = svc.capacity_view("claude", "fable")
    assert fable["budget_left"] == pytest.approx(0.68)  # the shared window binds too

    svc2, _ = _svc(tmp_path / "b", [claude], {"claude": _report(
        _window("seven_day", 0.5, 3600, 604800),
        _window("seven_day_fable", 1.0, 3600, 604800, "fable"),
        groups=groups)})
    assert svc2.capacity_view("claude", "fable", fresh=True)["state"] == "exhausted"
    assert svc2.capacity_view("claude", "sonnet")["state"] == "available"
    assert svc2.capacity_view("claude")["state"] == "available"

    svc3, _ = _svc(tmp_path / "c", [claude], {"claude": _report(
        _window("seven_day", 1.0, 3600, 604800),
        _window("seven_day_fable", 0.1, 3600, 604800, "fable"),
        groups=groups)})
    assert svc3.capacity_view("claude", "fable", fresh=True)["state"] == "exhausted"
    assert svc3.capacity_view("claude", "sonnet")["state"] == "exhausted"
    assert svc3.capacity_view("claude")["state"] == "exhausted"
