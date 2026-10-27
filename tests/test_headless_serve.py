"""The headless server: its API only, and an honest answer without MARS."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from mentis.execution import RunSpec
from tests._loop import world  # noqa: F401


def test_without_a_build_no_interface_is_served(world, monkeypatch, tmp_path):
    from mentis.conversation import render_check
    monkeypatch.setattr(render_check, "DIST", tmp_path / "no-build")
    for path in ("/", "/index.html", "/fluid/anything"):
        try:
            urllib.request.urlopen(world["base"] + path)
            raise AssertionError(f"{path} was served")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
            assert "Fluid is not built" in json.loads(exc.read())["error"]


def test_fluid_is_served_from_its_build(world, monkeypatch, tmp_path):
    """One page: a built file is served as itself, any other address is
    Fluid's own page; nothing outside the build, and not the server's
    render-check bundle, is served."""
    from mentis.conversation import render_check
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Mentis</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "render-check.js").write_text("var MentisRenderCheck")
    (tmp_path / "secret.txt").write_text("outside")
    monkeypatch.setattr(render_check, "DIST", dist)
    get = lambda p: urllib.request.urlopen(world["base"] + p)  # noqa: E731
    with get("/assets/app.js") as r:
        assert r.read() == b"console.log(1)"
        assert "javascript" in r.headers["Content-Type"]
    for path in ("/", "/fluid", "/fluid/anything?c=x", "/render-check.js",
                 "/../secret.txt", "/%2e%2e/secret.txt"):
        with get(path) as r:
            assert b"<title>Mentis</title>" in r.read(), path


def test_the_identity_probe_says_what_the_mcp_bridge_reads(world):
    """`tools/mcp_bridge.py` reads `corpus`, `release` and `code.commit`."""
    req = urllib.request.Request(world["base"] + "/api/server")
    with urllib.request.urlopen(req) as r:
        info = json.loads(r.read())
    assert info["corpus"] == world["state"].path
    assert info["release"] is None
    assert "commit" in info["code"]
    assert "ui" not in info


def test_without_mars_no_agent_runs_and_it_says_why(monkeypatch):
    """`mentis.execution.mars` is imported by name, lazily; without it the
    server still serves, lists no runtime, and every run is refused as
    `backend_unavailable` with the reason."""
    from mentis.core import service
    from mentis.core.service import mars_execution
    # The suite gives every service a FakeExecution (conftest); this test is
    # about the production fallback itself.
    monkeypatch.setattr(service, "unavailable_execution", service._Unavailable)
    monkeypatch.setitem(sys.modules, "mentis.execution.mars", None)
    ex = mars_execution("mars stdio")
    assert ex.backends() == []
    res = ex.perform(RunSpec(run_id="r1", backend="claude", workspace=".",
                             prompt="x"))
    assert res.started is False
    assert res.error_kind == "backend_unavailable"
    assert "mentis.execution.mars" in res.error
    assert ex.running() == set()


def test_the_mars_command_defaults(monkeypatch):
    from mentis.web import mars_command
    monkeypatch.delenv("MENTIS_MARS_COMMAND", raising=False)
    assert mars_command(None) == "mars stdio"
    monkeypatch.setenv("MENTIS_MARS_COMMAND", "C:/mars/mars.exe stdio")
    assert mars_command(None) == "C:/mars/mars.exe stdio"
    assert mars_command("other stdio") == "other stdio"
