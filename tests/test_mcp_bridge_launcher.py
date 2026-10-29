"""tools/mcp_bridge.py starts the bridge from the release the RUNNING server serves.

No release is named anywhere a CLI is registered: the launcher asks `/api/server` and
imports `mentis.worker` from `releases/<commit[:12]>`. Checked against a fake server
and a fake release whose `serve` records how it was called.
"""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / "tools" / "mcp_bridge.py"
COMMIT = "abcdef1234567890" + "0" * 24


@pytest.fixture
def fake_server():
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        payload: dict = {}

        def do_GET(self):
            seen.append((self.path, self.headers.get("X-Mentis-Client")))
            body = json.dumps(Handler.payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv, Handler, seen
    srv.shutdown()


def fake_release(home: Path, commit: str) -> Path:
    pkg = home / "releases" / commit[:12] / "mentis"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "worker.py").write_text(
        "import json, os, sys\n"
        "def serve(corpus, **kw):\n"
        "    print(json.dumps({'corpus': corpus, 'kw': kw, 'file': __file__}))\n"
    )
    return pkg.parent


def run(home: Path, server: str, session: str = "codex"):
    return subprocess.run(
        [sys.executable, "-I", str(LAUNCHER), "--session", session, "--server", server,
         "--home", str(home)],
        capture_output=True, text=True, timeout=60,
    )


def test_uses_the_running_servers_release(tmp_path, fake_server):
    srv, handler, seen = fake_server
    release = fake_release(tmp_path, COMMIT)
    handler.payload = {"code": {"commit": COMMIT}, "corpus": "C:/brain"}
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    out = run(tmp_path, url, "kimi")
    assert out.returncode == 0, out.stderr
    called = json.loads(out.stdout)
    assert Path(called["file"]).parent.parent == release
    assert called["corpus"] == "C:/brain"
    assert called["kw"] == {"via": url, "capability": None, "permits": None,
                            "scratch": None, "project": None, "session": "kimi"}
    assert seen == [("/api/server", "1")]
    assert COMMIT[:12] in out.stderr  # says which release, on stderr (stdout is MCP)


def test_installed_release_is_found_by_the_path_it_reports(tmp_path, fake_server):
    """An installed server (`releases/<semver>+<commit12>`) reports `release.path` and
    usually no checkout commit; the launcher uses that path (review finding)."""
    srv, handler, _ = fake_server
    root = tmp_path / "releases" / "1.4.0+abcdef123456"
    (root / "mentis").mkdir(parents=True)
    (root / "mentis" / "__init__.py").write_text("")
    (root / "mentis" / "worker.py").write_text(
        "import json\ndef serve(corpus, **kw):\n    print(json.dumps({'file': __file__}))\n")
    handler.payload = {"code": {"commit": None}, "corpus": "C:/brain",
                       "release": {"version": "1.4.0", "commit": COMMIT, "path": str(root)}}
    out = run(tmp_path, f"http://127.0.0.1:{srv.server_address[1]}")
    assert out.returncode == 0, out.stderr
    assert Path(json.loads(out.stdout)["file"]).parent.parent == root


def test_server_down_is_a_clear_failure(tmp_path):
    out = run(tmp_path, "http://127.0.0.1:1")
    assert out.returncode == 1 and out.stdout == ""
    assert "not answering" in out.stderr


def test_missing_release_is_a_clear_failure(tmp_path, fake_server):
    srv, handler, _ = fake_server
    handler.payload = {"code": {"commit": COMMIT}, "corpus": "C:/brain"}
    out = run(tmp_path, f"http://127.0.0.1:{srv.server_address[1]}")
    assert out.returncode == 1 and out.stdout == ""
    assert "holds no release" in out.stderr


def test_server_without_commit_is_refused(tmp_path, fake_server):
    srv, handler, _ = fake_server
    handler.payload = {"code": {}, "corpus": "C:/brain"}
    out = run(tmp_path, f"http://127.0.0.1:{srv.server_address[1]}")
    assert out.returncode == 1 and "did not say which release or commit" in out.stderr


def test_checkout_server_is_found_by_its_code_root(tmp_path, fake_server):
    """Headless Mentis running from a development checkout reports `code.root`;
    the bridge imports from exactly that checkout."""
    srv, handler, _ = fake_server
    root = tmp_path / "checkout"
    (root / "mentis").mkdir(parents=True)
    (root / "mentis" / "__init__.py").write_text("")
    (root / "mentis" / "worker.py").write_text(
        "import json\ndef serve(corpus, **kw):\n    print(json.dumps({'file': __file__}))\n")
    handler.payload = {"code": {"commit": COMMIT, "root": str(root)}, "corpus": "C:/brain",
                       "release": None}
    out = run(tmp_path, f"http://127.0.0.1:{srv.server_address[1]}")
    assert out.returncode == 0, out.stderr
    assert Path(json.loads(out.stdout)["file"]).parent.parent == root


def run_for(home: Path, server: str, brain: str):
    return subprocess.run(
        [sys.executable, "-I", str(LAUNCHER), "--session", "codex", "--server", server,
         "--home", str(home), "--brain", brain],
        capture_output=True, text=True, timeout=60,
    )


def test_refuses_a_server_holding_another_brain(tmp_path, fake_server):
    # THE SHADOWING DEFECT'S OTHER HALF. A session handed a bridge for a test
    # Brain must not end up talking to a different one -- production above all
    # -- however it was started. Named by id, a different id is refused before
    # `serve` is imported, so nothing reaches the other Brain at all.
    srv, handler, _ = fake_server
    fake_release(tmp_path, COMMIT)
    handler.payload = {"code": {"commit": COMMIT}, "corpus": "C:/live",
                       "corpus_id": "live-brain"}
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    out = run_for(tmp_path, url, "test-brain")
    assert out.returncode == 1 and out.stdout == ""
    assert "refusing to connect to a different Brain" in out.stderr
    assert "live-brain" in out.stderr


def test_connects_when_the_named_brain_is_held(tmp_path, fake_server):
    srv, handler, _ = fake_server
    fake_release(tmp_path, COMMIT)
    handler.payload = {"code": {"commit": COMMIT}, "corpus": "C:/test",
                       "corpus_id": "test-brain"}
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    by_id = run_for(tmp_path, url, "test-brain")
    assert by_id.returncode == 0, by_id.stderr
    by_path = run_for(tmp_path, url, "C:/test")
    assert by_path.returncode == 0, by_path.stderr


def test_an_unreported_id_is_refused_when_an_id_was_asked(tmp_path, fake_server):
    srv, handler, _ = fake_server
    fake_release(tmp_path, COMMIT)
    handler.payload = {"code": {"commit": COMMIT}, "corpus": "C:/old"}
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    out = run_for(tmp_path, url, "test-brain")
    assert out.returncode == 1
    assert "an unreported id" in out.stderr
