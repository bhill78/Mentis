"""Models and capacity as MARS reports them (`_mars/backends`, `_mars/capacity`)."""

from __future__ import annotations

from mentis.core.service import MentisService
from mentis.execution import FakeExecution

CLAUDE = {"id": "claude", "kind": "acp", "available": True, "reason": None,
          "models": ["default", "opus", "sonnet"], "efforts": ["low", "high"],
          "modelNames": {"opus": "Opus 5.5", "sonnet": "Sonnet 5.5"},
          "modelsFrom": "the 'model' and 'effort' config option(s) claude offered on session/new",
          "supports": {"mcp": ["stdio"]}}
AGY = {"id": "antigravity", "kind": "cli", "available": True, "reason": None,
       "models": ["gemini-4-argon-low"], "efforts": [], "supports": {"mcp": ["stdio"]}}

CAPACITY = {
    "claude": {"backend": "claude", "source": "claude rate_limit_event", "observedAt": 100.0,
               "plan": "allowed", "modelGroups": {}, "notes": ["in-band"],
               "windows": [{"label": "five_hour", "usedFraction": 0.25, "windowSeconds": 18000,
                            "resetsAt": 4102444800, "group": None, "raw": {"utilization": 0.25}}]},
    "antigravity": {"backend": "antigravity", "source": "agy /usage", "observedAt": 50.0,
                    "plan": None, "notes": ["agy"],
                    "modelGroups": {"gemini-4-argon-low": "Gemini 4 Argon"},
                    "windows": [{"label": "weekly", "usedFraction": 1.0, "windowSeconds": 604800,
                                 "resetsAt": 4102444800, "group": "Gemini 4 Argon", "raw": {}}]},
}


def _service(tmp_path, capacity=None):
    return MentisService(str(tmp_path / "instances"),
                         execution=FakeExecution([CLAUDE, AGY], capacity=capacity))


def test_models_carry_display_names_and_where_they_came_from(tmp_path):
    models = {m.slug: m for m in _service(tmp_path).models_list("claude")}
    assert list(models) == ["default", "opus", "sonnet"]
    assert models["opus"].display_name == "Opus 5.5"
    assert models["default"].display_name is None
    assert models["opus"].efforts == ("low", "high")
    assert "config option" in models["opus"].details["catalogue"]


def test_capacity_is_read_from_mars(tmp_path):
    svc = _service(tmp_path, CAPACITY)
    claude = svc.capacity_observe("claude")
    assert claude.established and claude.observed_at == 100.0
    [w] = claude.windows
    assert (w.label, w.used_fraction, w.window_seconds, w.group) == ("five_hour", 0.25, 18000, None)
    assert claude.plan.value == "allowed"
    agy = svc.capacity_observe("antigravity")
    assert agy.windows[0].group == "Gemini 4 Argon"
    assert dict(agy.model_groups) == {"gemini-4-argon-low": "Gemini 4 Argon"}


def test_no_report_is_not_zero(tmp_path):
    reading = _service(tmp_path).capacity_observe("claude")
    assert not reading.established and reading.windows == ()
    assert "not reported" in reading.notes[0]


LOCAL_BACKEND = {"id": "local", "kind": "acp", "available": True, "reason": None,
                 "models": [], "efforts": [], "supports": {"mcp": ["stdio"]}}
LOCAL = {"backend": "local", "source": "local servers", "observedAt": 7.0, "plan": None,
         "modelGroups": {}, "windows": [],
         "notes": ["local resources measured now, not a subscription quota"],
         "local": {"runningTurns": 0,
                   "unavailable": {"throughput": "not reported"},
                   "servers": [{"name": "ollama", "url": "http://127.0.0.1:11434",
                                "reachable": True, "version": "0.40.11",
                                "loadedMemoryBytes": 1200, "loadedVramBytes": 900,
                                "models": [{"id": "qwen2.5:0.5b", "loaded": True,
                                            "memoryBytes": 1200, "vramBytes": 900,
                                            "contextLength": 32768, "contextLoaded": 4096}]},
                               {"name": "lmstudio", "url": "http://127.0.0.1:1234",
                                "reachable": False, "why": "not running"}]}}


def test_local_resources_travel_apart_from_quota(tmp_path):
    """Local model servers are resources, not a plan: they never become windows,
    and `/api/capacity` carries them as `local` without a `why_not`."""
    from mentis.web import _State, fixture, _routes
    svc = MentisService(str(tmp_path / "instances"),
                        execution=FakeExecution([LOCAL_BACKEND], capacity={"local": LOCAL}))
    r = svc.capacity_observe("local")
    assert r.windows == () and not r.established
    assert r.local["servers"][0]["models"][0]["vramBytes"] == 900
    root = tmp_path / "corpus"
    fixture.build(str(root))
    st = _State(str(root), str(tmp_path))
    st.agents.execution = FakeExecution([LOCAL_BACKEND], capacity={"local": LOCAL})
    got = _routes(st, "/api/capacity", {}, None, "GET")["capacity"]["local"]
    assert got["windows"] == [] and got["why_not"] is None
    assert got["local"]["servers"][1]["reachable"] is False
    assert got["local"]["unavailable"]["throughput"]
