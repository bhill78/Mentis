"""A build from main must stay installable on Windows.

The ordinary tests read the source tree (`problems`) and run the launcher against
small stand-ins; they fail when somebody adds an import the install does not carry,
drops a payload file, or changes what the server is started with. `-m installer`
really builds the installer and installs it (tools/prove_windows_installer.py);
minutes, a real install and network, so it is opted into. docs/windows-installer.md.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import socket
import subprocess
import sys
import textwrap
import types

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "installer"))

import build_windows_installer as builder  # noqa: E402
import launcher  # noqa: E402


@pytest.fixture
def tree(tmp_path):
    """A copy of what `problems` reads, to break."""
    for name in ("pyproject.toml", "tools/installer", "tools/mcp_bridge.py",
                 "tools/ladder_vocabulary.py", "mentis"):
        src, dst = REPO / name, tmp_path / name
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    (tmp_path / "apps/fluid-web").mkdir(parents=True)
    shutil.copy2(REPO / "apps/fluid-web/package.json", tmp_path / "apps/fluid-web/package.json")
    return tmp_path


def edit_manifest(tree, change):
    path = tree / "tools/installer/manifest.json"
    man = json.loads(path.read_text("utf-8"))
    change(man)
    path.write_text(json.dumps(man), "utf-8")


def test_this_tree_would_install():
    assert builder.problems(REPO) == []


def test_a_new_third_party_import_is_caught(tree):
    (tree / "mentis/new_thing.py").write_text("def f():\n    import yaml\n", "utf-8")
    assert any("imports yaml" in p for p in builder.problems(tree))


def test_a_module_the_embeddable_python_lacks_is_caught(tree):
    (tree / "mentis/new_thing.py").write_text("import tkinter\n", "utf-8")
    assert any("imports tkinter" in p for p in builder.problems(tree))


def test_an_import_of_an_uncarried_tool_is_caught(tree):
    (tree / "mentis/new_thing.py").write_text("from tools.work_model_diff import x\n", "utf-8")
    assert any("tools/work_model_diff.py" in p for p in builder.problems(tree))


def test_a_dependency_the_lock_does_not_have_is_caught(tree):
    path = tree / "pyproject.toml"
    path.write_text(path.read_text("utf-8").replace(
        '"tzdata==2026.5",', '"tzdata==2026.5",\n    "attrs==25.1.0",'), "utf-8")
    assert any("attrs" in p and "--relock" in p for p in builder.problems(tree))


def test_a_payload_row_with_no_source_is_caught(tree):
    edit_manifest(tree, lambda m: m["payload"].append({"from": "tools/gone.py", "to": "app/gone.py"}))
    assert any("tools/gone.py" in p for p in builder.problems(tree))


def test_a_payload_row_outside_app_is_caught(tree):
    edit_manifest(tree, lambda m: m["payload"].append({"from": "tools/mcp_bridge.py", "to": "../x.py"}))
    assert any("under app/" in p for p in builder.problems(tree))


def test_dropping_the_code_or_the_launcher_is_caught(tree):
    edit_manifest(tree, lambda m: m.update(payload=[r for r in m["payload"]
                                                    if r["from"] not in ("mentis",)]))
    assert any("must carry mentis" in p for p in builder.problems(tree))


def test_a_server_flag_mentis_web_does_not_take_is_caught(tree):
    edit_manifest(tree, lambda m: m["launch"][0]["command"].append("--no-such-flag"))
    assert any("--no-such-flag" in p for p in builder.problems(tree))


def test_a_launch_module_that_is_gone_is_caught(tree):
    def rename(man):
        cmd = man["launch"][0]["command"]
        cmd[cmd.index("mentis.web")] = "mentis.nowhere"
    edit_manifest(tree, rename)
    found = builder.problems(tree)
    assert any("mentis.nowhere" in p for p in found), found


def test_the_new_brain_setup_going_away_is_caught(tree):
    (tree / "mentis/bootstrap/__main__.py").unlink()
    assert any("mentis.bootstrap" in p for p in builder.problems(tree))


def test_an_unknown_placeholder_is_caught(tree):
    edit_manifest(tree, lambda m: m["launch"][0]["command"].append("{nope}"))
    assert any("{nope}" in p for p in builder.problems(tree))


def test_the_install_lays_out_what_the_server_looks_for():
    """Fluid at <root>/apps/fluid-web/dist beside mentis/ (render_check.DIST), and
    the module the launch row names importable from app\\ (the runtime's ._pth)."""
    man = json.loads((REPO / "tools/installer/manifest.json").read_text("utf-8"))
    tos = {r["to"] for r in man["payload"]}
    assert {"app/mentis", "app/apps/fluid-web/dist", "app/launcher.py", "app/manifest.json"} <= tos
    assert r"..\app" in builder.PTH_LINES


def test_the_server_log_is_written_as_it_happens():
    """Its warnings (no baseline, no MARS) go to stdout, here a file: buffered, the
    log stays empty until the server stops."""
    man = json.loads((REPO / "tools/installer/manifest.json").read_text("utf-8"))
    assert "-u" in man["launch"][0]["command"]


def test_the_lock_pins_every_project_by_hash():
    text = (REPO / "tools/installer/requirements.lock").read_text("utf-8")
    assert text.count("==") == text.count("--hash=sha256:") > 5


def test_the_nsi_is_given_what_it_uses():
    text = (REPO / "tools/installer/mentis.nsi").read_text("utf-8")
    for name in ("VERSION", "FILE_VERSION", "COMMIT", "STAGE", "OUTFILE"):
        assert "${%s}" % name in text
    # never the name Mark IV's installer registers under, nor any Brain
    assert "\\Uninstall\\MentisServer" in text
    assert "brain" not in " ".join(line for line in text.splitlines()
                                   if line.lstrip().startswith(("RMDir", "Delete"))).lower()


# -- the launcher -----------------------------------------------------------------

SERVICE = textwrap.dedent("""\
    import http.server, json, signal, sys
    port, name, brain, log = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
    def say(what):
        with open(log, "a") as f:
            f.write(f"{name} {what}\\n")
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({"corpus": brain}).encode())
        def log_message(self, *a): pass
    say("up")
    try:
        http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
    except KeyboardInterrupt:
        say("clean")
    """)


def free_port_pair() -> int:
    for port in range(19311, 19900, 2):
        if launcher.port_free(port) and launcher.port_free(port + 1):
            return port
    pytest.skip("no free ports")


@pytest.fixture
def install(tmp_path):
    root = tmp_path / "Mentis Test"
    (root / "app").mkdir(parents=True)
    (root / "app/BUILD.json").write_text(json.dumps({"commit": "abc", "version": "0"}), "utf-8")
    (root / "svc.py").write_text(SERVICE, "utf-8")
    inst = launcher.Install(root)
    inst.python = getattr(sys, "_base_executable", sys.executable)
    return inst


def row(name, port_name, log):
    return {"name": name,
            "command": ["{python}", "-I", "{root}/svc.py", "{%s}" % port_name, name, "{brain}", str(log)],
            "ready": "http://127.0.0.1:{%s}/" % port_name}


def manifest(inst, launch, ports):
    (inst.app / "manifest.json").write_text(json.dumps(
        {"ports": ports, "launch": launch, "open": "http://127.0.0.1:{port}/"}), "utf-8")


def state(tmp_path, port) -> dict:
    return {"brain": str(tmp_path / "b"), "port": port, "workspace": str(tmp_path / "w"),
            "mars": "mars stdio", "owner": "@o"}


@pytest.mark.skipif(sys.platform != "win32", reason="Ctrl-C by console is Windows's")
def test_one_more_launch_row_is_all_a_new_process_takes(install, tmp_path):
    """The migration's seam: the front is a row in `launch`, a port in `ports`.
    Started in order, stopped in reverse, by Ctrl-C."""
    log = tmp_path / "order.log"
    port = free_port_pair()
    manifest(install, [row("backend", "backend_port", log), row("front", "port", log)],
             {"port": 0, "backend_port": 1})
    st = state(tmp_path, port)
    got = launcher.start(install, st)
    assert got == {"started": ["backend", "front"], "already_running": False}
    assert launcher.start(install, st)["already_running"] is True
    assert not launcher.port_free(port) and not launcher.port_free(port + 1)
    done = launcher.stop(install)
    assert done == {"stopped": {"front": "clean", "backend": "clean"}}
    assert log.read_text().split("\n")[:4] == ["backend up", "front up", "front clean", "backend clean"]
    assert launcher.port_free(port) and install.running() == []


def test_a_process_that_will_not_start_says_why_and_leaves_nothing(install, tmp_path):
    log = tmp_path / "order.log"
    port = free_port_pair()
    bad = {"name": "bad", "command": ["{python}", "-I", "-c", "import sys; print('no such'); sys.exit(7)"],
           "ready": "http://127.0.0.1:{port}/"}
    manifest(install, [row("backend", "backend_port", log), bad], {"port": 0, "backend_port": 1})
    with pytest.raises(launcher.Refused, match="(?s)bad did not start.*7.*no such"):
        launcher.start(install, state(tmp_path, port))
    assert install.running() == []
    assert launcher.port_free(port + 1)


def test_another_brains_server_on_the_port_is_refused(install, tmp_path):
    log = tmp_path / "order.log"
    port = free_port_pair()
    other = row("server", "port", log)
    other["command"][5] = str(tmp_path / "another")
    manifest(install, [other], {"port": 0})
    with pytest.raises(launcher.Refused, match="another Brain"):
        launcher.start(install, state(tmp_path, port))
    assert install.running() == []


def test_a_port_in_use_is_refused_before_anything_starts(install, tmp_path):
    log = tmp_path / "order.log"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        manifest(install, [row("server", "port", log)], {"port": 0})
        with pytest.raises(launcher.Refused, match="in use"):
            launcher.start(install, state(tmp_path, s.getsockname()[1]))
    assert not log.exists()


def setup_args(**kw):
    base = dict(brain=None, owner=None, workspace=None, mars=None, port=None, attach=False,
                no_tour=False, no_start=True, no_browser=True)
    return types.SimpleNamespace(**{**base, **kw})


def fake_bootstrap(monkeypatch, *, check_fails=False):
    calls = []

    def run(inst, brain, owner, *more):
        calls.append((brain, owner, more))
        refused = check_fails and "--check" in more
        return types.SimpleNamespace(returncode=1 if refused else 0,
                                     stderr="bootstrap refused: no" if refused else "")
    monkeypatch.setattr(launcher, "_bootstrap", run)
    return calls


def test_setup_creates_through_bootstrap_and_remembers(install, tmp_path, monkeypatch):
    manifest(install, [], {"port": 0})
    calls = fake_bootstrap(monkeypatch)
    got = launcher.setup(install, setup_args(brain=str(tmp_path / "b"), owner="me", port=9001), False)
    assert got["created"] is True and got["owner"] == "@me"
    assert calls == [(str(tmp_path / "b"), "@me", ())]
    held = install.state()
    assert held["port"] == 9001 and held["mars"] == "mars stdio"
    assert held["workspace"] == str(tmp_path / "workspace")
    assert (tmp_path / "workspace").is_dir()


def test_setup_refuses_a_brain_inside_the_install(install, monkeypatch):
    manifest(install, [], {"port": 0})
    calls = fake_bootstrap(monkeypatch)
    with pytest.raises(launcher.Refused, match="inside the install"):
        launcher.setup(install, setup_args(brain=str(install.root / "brain"), owner="@me"), False)
    assert calls == [] and install.state() is None


def test_setup_needs_an_owner_when_nobody_can_be_asked(install, tmp_path, monkeypatch):
    manifest(install, [], {"port": 0})
    fake_bootstrap(monkeypatch)
    with pytest.raises(launcher.Refused, match="--owner"):
        launcher.setup(install, setup_args(brain=str(tmp_path / "b")), False)


def existing_brain(tmp_path):
    brain = tmp_path / "b"
    brain.mkdir()
    (brain / "corpus.db").write_bytes(b"")
    return brain


def test_an_existing_brain_needs_attach(install, tmp_path, monkeypatch):
    manifest(install, [], {"port": 0})
    calls = fake_bootstrap(monkeypatch)
    brain = existing_brain(tmp_path)
    with pytest.raises(launcher.Refused, match="--attach"):
        launcher.setup(install, setup_args(brain=str(brain), owner="@me"), False)
    assert calls == []


def test_attach_checks_first_and_a_refusal_writes_nothing(install, tmp_path, monkeypatch):
    manifest(install, [], {"port": 0})
    calls = fake_bootstrap(monkeypatch, check_fails=True)
    brain = existing_brain(tmp_path)
    with pytest.raises(launcher.Refused, match="(?s)nothing was changed.*bootstrap refused"):
        launcher.setup(install, setup_args(brain=str(brain), owner="@me", attach=True), False)
    assert [c[2] for c in calls] == [("--check",)]
    assert install.state() is None


def test_attach_runs_the_setup_after_its_check(install, tmp_path, monkeypatch):
    manifest(install, [], {"port": 0})
    calls = fake_bootstrap(monkeypatch)
    brain = existing_brain(tmp_path)
    got = launcher.setup(install, setup_args(brain=str(brain), owner="@me", attach=True, port=9002), False)
    assert got["created"] is False
    assert [c[2] for c in calls] == [("--check",), ()]


def test_a_person_is_asked(install, tmp_path, monkeypatch):
    manifest(install, [], {"port": 0})
    calls = fake_bootstrap(monkeypatch)
    answers = iter([str(tmp_path / "chosen"), "me"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    got = launcher.setup(install, setup_args(port=9003), True)
    assert got["brain"] == str(tmp_path / "chosen") and got["owner"] == "@me"
    assert calls[0][1] == "@me"


def test_the_first_free_port_never_reaches_day_to_day(monkeypatch):
    monkeypatch.setattr(launcher, "port_free", lambda p: p != launcher.FIRST_PORT)
    assert launcher.choose_port([0]) == launcher.FIRST_PORT + 1
    assert launcher.FIRST_PORT > 8760


def test_verify_finds_a_changed_or_missing_file(install):
    (install.root / "a.txt").write_text("a", "utf-8")
    import hashlib
    good = hashlib.sha256(b"a").hexdigest()
    (install.app / "FILES.json").write_text(json.dumps({"a.txt": good}), "utf-8")
    assert launcher.verify(install)["ok"] is True
    (install.root / "a.txt").write_text("b", "utf-8")
    assert launcher.verify(install)["changed"] == ["a.txt"]
    (install.root / "a.txt").unlink()
    assert launcher.verify(install)["missing"] == ["a.txt"]


# -- what an install says it is ---------------------------------------------------

def test_an_installed_server_says_which_build_it_is(tmp_path, monkeypatch):
    from mentis.web import identity
    monkeypatch.setattr(identity, "_INSTALLED", {"version": "1.2.3", "commit": "c" * 40})
    tree = identity._tree()
    assert tree["commit"] == "c" * 40 and tree["commit_why_not"] is None and tree["dirty"] is None
    assert identity._git("rev-parse", "HEAD")[0] is None
    info = identity._identity(workspace="w", corpus="b")
    assert info["release"] == {"version": "1.2.3", "commit": "c" * 40, "path": str(identity.REPO)}


def test_a_checkout_has_no_stamp():
    from mentis.web import identity
    assert not (identity.REPO / "BUILD.json").exists()
    assert identity._INSTALLED is None
    assert identity._identity(workspace="w", corpus="b")["release"] is None


def test_the_bridge_finds_an_installs_code(tmp_path, monkeypatch):
    """`release.path` is the bridge's first choice, and holds `mentis/worker.py`."""
    import mcp_bridge
    (tmp_path / "mentis").mkdir()
    (tmp_path / "mentis/worker.py").write_text("", "utf-8")
    body = json.dumps({"corpus": "b", "code": {"commit": "x", "root": "elsewhere"},
                       "release": {"path": str(tmp_path), "version": "1", "commit": "x"}}).encode()

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return body
    monkeypatch.setattr(mcp_bridge.urllib.request, "urlopen", lambda *a, **k: Answer())
    monkeypatch.setattr(mcp_bridge.json, "load", lambda r: json.loads(r.read()))
    assert mcp_bridge.running_release("http://x", "home") == (str(tmp_path), "b")


# -- the real thing ---------------------------------------------------------------

@pytest.mark.installer
@pytest.mark.skipif(sys.platform != "win32", reason="the Windows installer")
def test_a_build_from_this_commit_really_installs_and_uninstalls(tmp_path):
    """HEAD built, installed, set up, opened, restarted and uninstalled, under
    tmp_path. Refuses to run if this user has an install already."""
    out = subprocess.run([sys.executable, str(REPO / "tools/build_windows_installer.py"),
                          "--out", str(tmp_path / "out")], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=1500)
    assert out.returncode == 0, out.stderr[-3000:]
    built = json.loads(out.stdout)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    prove = subprocess.run([sys.executable, str(REPO / "tools/prove_windows_installer.py"),
                            built["installer"], "--root", str(tmp_path / "proof"), "--port", str(port),
                            "--commit", built["commit"]], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900)
    assert prove.returncode == 0, prove.stdout[-4000:] + prove.stderr[-2000:]
    assert all(s["ok"] for s in json.loads(prove.stdout)["steps"])
