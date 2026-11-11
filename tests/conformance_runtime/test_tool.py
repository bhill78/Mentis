"""tools/runtime_conformance.py and the rig it drives (integrator N2)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.conformance_runtime.rig import EndedBeforeLive, Rig

TOOL = Path(__file__).resolve().parents[2] / "tools" / "runtime_conformance.py"


def _tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location("runtime_conformance_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_tool_names_no_builders_paths_and_requires_its_root(monkeypatch):
    assert "r2-parity" not in TOOL.read_text(encoding="utf-8")
    tool = _tool()
    monkeypatch.delenv(tool.ROOT_ENV, raising=False)
    monkeypatch.delenv(tool.MARS_ENV, raising=False)
    with pytest.raises(SystemExit):
        tool.main(["--runtime", "claude", "--offline"])
    with pytest.raises(SystemExit):                       # live needs a MARS named
        tool.main(["--runtime", "claude", "--root", "x"])


def test_waiting_for_a_live_run_returns_at_once_when_it_already_ended():
    """A dispatch that already failed is said at once, not after the full wait."""
    ended = {"id": "s1"}

    class Stub:
        live = True
        runs = staticmethod(lambda exp: [ended])
        end_of = staticmethod(lambda start: {"act": "delivery-failed", "because": "refused"})
        failures = staticmethod(lambda exp: [])
    t0 = time.time()
    with pytest.raises(EndedBeforeLive) as got:
        Rig.wait_live(Stub(), "e", timeout=300)
    assert time.time() - t0 < 5 and "delivery-failed" in str(got.value)

    class NoRun(Stub):
        runs = staticmethod(lambda exp: [])
        failures = staticmethod(lambda exp: [{"act": "dispatch-failed", "because": "x"}])
    with pytest.raises(EndedBeforeLive):
        Rig.wait_live(NoRun(), "e", timeout=300)


def test_the_evidence_holds_each_runs_mcp_report(tmp_path, monkeypatch):
    tool = _tool()
    monkeypatch.delenv(tool.MARS_ENV, raising=False)
    tool.main(["--runtime", "claude", "--offline", "--root", str(tmp_path),
               "--scenarios", "failure"])
    out = json.loads(next((tmp_path / "evidence").glob("claude-*.json")).read_text())
    assert isinstance(out["runs"], list) and out["runs"]
    assert all("mcp" in r and "denied" in r for r in out["runs"])
