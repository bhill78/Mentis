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
import tempfile
import textwrap
import types

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "installer"))

import build_windows_installer as builder  # noqa: E402
import launcher  # noqa: E402
import updater  # noqa: E402


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
    for name in ("VERSION", "FILE_VERSION", "COMMIT", "STAGE", "CMD_FILE", "OUTFILE"):
        assert "${%s}" % name in text
    # never the name Mark IV's installer registers under, nor any Brain
    assert "\\Uninstall\\MentisServer" in text
    assert "brain" not in " ".join(line for line in text.splitlines()
                                   if line.lstrip().startswith(("RMDir", "Delete"))).lower()


def test_the_nsi_really_compiles_and_unpacks(tmp_path):
    """Its defines share one case-blind namespace with NSIS's own headers: /DCMD took
    LogicLib's ${Cmd}, and no reading of the script shows that."""
    try:
        nsis = builder.makensis(builder.load(REPO, "lock.json"),
                                pathlib.Path(tempfile.gettempdir()) / "mentis-installer-cache")
    except OSError as exc:
        pytest.skip(f"the pinned NSIS cannot be fetched: {exc}")
    stage = tmp_path / "work" / "stage"
    (stage / "app").mkdir(parents=True)
    (stage / "app" / "BUILD.json").write_text('{"version": "0.1.0", "commit": "%s"}' % ("0" * 40), "utf-8")
    exe = tmp_path / "out.exe"
    builder.pack(stage, REPO / "tools/installer/mentis.nsi", nsis, exe, fast=True)
    if sys.platform == "win32":      # /EXTRACT is all update asks of the exe; it touches nothing else
        got = subprocess.run(f'"{exe}" /S /EXTRACT="{tmp_path / "unpacked"}"', timeout=120)
        assert got.returncode == 0
        assert (tmp_path / "unpacked" / "app" / "BUILD.json").is_file()


# -- what update and rollback take from the tree ---------------------------------

def test_dropping_the_updater_from_the_payload_is_caught(tree):
    edit_manifest(tree, lambda m: m.update(payload=[r for r in m["payload"]
                                                    if not r["from"].endswith("updater.py")]))
    assert any("must carry tools/installer/updater.py" in p for p in builder.problems(tree))


@pytest.mark.parametrize("key", ["identity", "working", "health"])
def test_a_manifest_that_no_longer_says_how_to_check_is_caught(tree, key):
    edit_manifest(tree, lambda m: m.pop(key))
    assert any(f"`{key}`" in p for p in builder.problems(tree))


def test_a_health_url_the_server_does_not_answer_is_caught(tree):
    edit_manifest(tree, lambda m: m["health"].append("http://127.0.0.1:{port}/api/no-such"))
    assert any("/api/no-such" in p for p in builder.problems(tree))


@pytest.mark.parametrize("gone", ["mentis/migrate.py", "mentis/readonly.py", "mentis/brain/__main__.py"])
def test_the_commands_update_runs_going_away_is_caught(tree, gone):
    (tree / gone).unlink()
    assert any(gone in p for p in builder.problems(tree))


def test_the_ledger_read_going_away_is_caught(tree):
    path = tree / "mentis/spine/migrations.py"
    path.write_text(path.read_text("utf-8").replace("def status_of(", "def renamed("), "utf-8")
    assert any("status_of" in p for p in builder.problems(tree))


@pytest.mark.parametrize("gone", ["/EXTRACT=", "arrive", "/remove:d"])
def test_the_setup_exe_losing_a_way_in_is_caught(tree, gone):
    path = tree / "tools/installer/mentis.nsi"
    path.write_text(path.read_text("utf-8").replace(gone, "x"), "utf-8")
    assert any(gone in p for p in builder.problems(tree))


def test_mentis_cmd_runs_what_state_current_names():
    text = builder.MENTIS_CMD.decode()
    assert 'state\\current' in text and r'releases\%MENTIS_RELEASE%\app\launcher.py' in text
    assert "exit /b %errorlevel%" in text


# -- the launcher -----------------------------------------------------------------

SERVICE = textwrap.dedent("""\
    import http.server, json, pathlib, signal, sys
    port, name, brain, log = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
    build = json.loads(pathlib.Path(sys.argv[5]).read_text()) if len(sys.argv) > 5 else {}
    def say(what):
        with open(log, "a") as f:
            f.write(f"{name} {what}\\n")
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(404 if self.path.startswith("/bad") else 200); self.end_headers()
            body = {"corpus": brain, "release": build}
            busy = pathlib.Path(log + ".busy")
            if self.path == "/api/working" and busy.exists():
                body["open"] = [{"held_here": True, "state": busy.read_text()}]
            self.wfile.write(json.dumps(body).encode())
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
    inst = launcher.Install(root, "0+abc")
    inst.app.mkdir(parents=True)
    (inst.app / "BUILD.json").write_text(json.dumps({"commit": "abc", "version": "0"}), "utf-8")
    (root / "svc.py").write_text(SERVICE, "utf-8")
    inst.python = HOST_PYTHON
    return inst


HOST_PYTHON = getattr(sys, "_base_executable", sys.executable)


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
    (install.home / "a.txt").write_text("a", "utf-8")
    import hashlib
    good = hashlib.sha256(b"a").hexdigest()
    (install.app / "FILES.json").write_text(json.dumps({"a.txt": good}), "utf-8")
    assert launcher.verify(install)["ok"] is True
    (install.home / "a.txt").write_text("b", "utf-8")
    assert launcher.verify(install)["changed"] == ["a.txt"]
    (install.home / "a.txt").unlink()
    assert launcher.verify(install)["missing"] == ["a.txt"]


# -- update and rollback, with the two-process stand-in ---------------------------
#
# The real commands, the real journal, real processes on real ports, stopped by Ctrl-C:
# only the Brain's own commands (`_run_release`), the ledger and the running of another
# release's launcher are stood in for. tools/prove_windows_installer.py does it for real.

OLD, NEW = "0.1.0+" + "a" * 12, "0.1.0+" + "b" * 12


class Killed(BaseException):
    """What a kill leaves: no handler runs."""


class World:
    def __init__(self, tmp_path, monkeypatch, *, new_target=1, new_min_reader=1, new_unhealthy=False,
                 new_wont_start=False):
        self.root = tmp_path / "Mentis Test"
        self.log = tmp_path / "order.log"
        self.brain = str(tmp_path / "brain")
        self.port = free_port_pair()
        self.facts = {"exists": True, "version": 1, "min_reader": 1, "state": "open", "problems": [],
                      "legacy_open": False}
        self.brain_calls = []
        self.killed_at = None
        self.kill_label = None
        for name, commit, target, min_reader in ((OLD, "a" * 40, 1, 1), (NEW, "b" * 40, new_target, new_min_reader)):
            self.make_release(name, commit, target, min_reader,
                              unhealthy=name == NEW and new_unhealthy, wont_start=name == NEW and new_wont_start)
        self.inst = launcher.Install(self.root, OLD)
        self.inst.python = HOST_PYTHON
        self.inst.point(OLD, None)
        self.inst.write(self.inst.state_file, {"brain": self.brain, "owner": "@o", "port": self.port,
                                               "workspace": str(tmp_path / "w"), "mars": "m"})
        monkeypatch.setattr(updater, "_brain_facts", lambda brain: dict(self.facts))
        self.brain_open = False
        monkeypatch.setattr(updater, "_brain_is_open", lambda brain: self.brain_open)
        monkeypatch.setattr(updater, "_run_release", self.run_release)
        monkeypatch.setattr(updater, "_launch", self.launch)
        monkeypatch.setattr(updater, "_lock", lambda home: None)
        monkeypatch.setattr(updater, "_self_test", lambda home, build: None)
        monkeypatch.setattr(updater, "_hook", self.hook)

    def make_release(self, name, commit, target, min_reader, unhealthy=False, wont_start=False):
        import hashlib
        home = self.root / "releases" / name
        (home / "app").mkdir(parents=True)
        version, _ = name.split("+")
        (home / "app/BUILD.json").write_text(json.dumps(
            {"version": version, "commit": commit, "schema_target": target,
             "migrations": [f"{i:04}-m" for i in range(1, target + 1)], "min_reader_after": min_reader}), "utf-8")
        svc = (self.root / "svc.py")
        svc.write_text(SERVICE, "utf-8")
        def row_of(rname, port_name):
            command = ["{python}", "-I", "{root}/svc.py", "{%s}" % port_name, rname, "{brain}", str(self.log),
                       "{release}/app/BUILD.json"]
            if wont_start and rname == "front":
                command = ["{python}", "-I", "-c", "import sys; print('no such flag'); sys.exit(7)"]
            return {"name": rname, "command": command, "ready": "http://127.0.0.1:{%s}/" % port_name}
        man = {"ports": {"port": 0, "backend_port": 1},
               "launch": [row_of("backend", "backend_port"), row_of("front", "port")],
               "open": "http://127.0.0.1:{port}/", "identity": "http://127.0.0.1:{port}/api/server",
               "working": "http://127.0.0.1:{port}/api/working",
               "health": ["http://127.0.0.1:{port}/" + ("bad" if unhealthy else "fine")]}
        (home / "app/manifest.json").write_text(json.dumps(man), "utf-8")
        files = {f"app/{n}": hashlib.sha256((home / "app" / n).read_bytes()).hexdigest()
                 for n in ("BUILD.json", "manifest.json")}
        (home / "app/FILES.json").write_text(json.dumps(files), "utf-8")

    def hook(self, label):
        if label == self.kill_label:
            self.kill_label, self.killed_at = None, label
            raise Killed(label)

    def run_release(self, inst, name, *args, timeout=None):
        self.brain_calls.append((name, args[:3]))
        ok = types.SimpleNamespace(returncode=0, stderr="", stdout="{}")
        if "mentis.migrate" in args:
            self.facts.update(version=self.target_of(name), min_reader=self.min_reader_of(name))
        elif "backup" in args:
            ok.stdout = json.dumps({"backup": str(self.root.parent / "backups" / "one")})
        elif "verify" in args:
            ok.stdout = json.dumps({"ok": True, "problems": []})
        return ok

    def build_of(self, name):
        return json.loads((self.root / "releases" / name / "app/BUILD.json").read_text())

    def target_of(self, name):
        return self.build_of(name)["schema_target"]

    def min_reader_of(self, name):
        return self.build_of(name)["min_reader_after"]

    def launch(self, inst, name, *args):
        """Another release's launcher, in this process; its manifest is its own."""
        there = launcher.Install(self.root, name)
        there.python = HOST_PYTHON
        out = types.SimpleNamespace(returncode=0, stdout="{}", stderr="")
        if args[:1] == ("start",):
            try:
                launcher.start(there, there.state())
            except launcher.Refused as exc:
                out.returncode, out.stderr = 1, str(exc)
        elif args[:2] == ("update", "--resume"):
            out.returncode, doc = updater.recover(there)
            out.stdout = json.dumps({"outcome": updater.OUTCOME[out.returncode], **doc})
        else:
            raise AssertionError(args)
        return out

    def at(self, name):
        there = launcher.Install(self.root, name)
        there.python = HOST_PYTHON
        return there

    def a(self, **kw):
        base = dict(yes=True, drain_wait=None, resume=False, staged_here=True, plan_only=False, made=True,
                    package=None, command="update")
        return types.SimpleNamespace(**{**base, **kw})

    def update(self):
        """What the new release's own launcher does, once it is placed."""
        return updater.transact(self.at(NEW), self.a(), NEW, kind="update", made=True)

    def rollback(self, name):
        return updater._rollback(self.at(name), self.a(command="rollback"))

    def running_commit(self):
        who = updater._serving(self.at(self.inst.current()))
        return ((who or {}).get("release") or {}).get("commit", "")[:1] or None

    def order(self):
        return self.log.read_text().split("\n")[:-1] if self.log.exists() else []

    def stop(self):
        launcher.stop(self.inst)


@pytest.fixture
def world(tmp_path, monkeypatch):
    made = []

    def make(**kw):
        w = World(tmp_path, monkeypatch, **kw)
        made.append(w)
        return w
    yield make
    for w in made:
        w.stop()


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Ctrl-C by console is Windows's")


@windows_only
def test_update_stops_and_starts_in_the_declared_order_and_rollback_goes_back(world):
    w = world()
    launcher.start(w.inst, w.inst.state())
    code, doc = w.update()
    assert code == 0 and doc["running"] == NEW and w.running_commit() == "b"
    assert (w.inst.current(), w.inst.previous()) == (NEW, OLD)
    assert w.order() == ["backend up", "front up", "front clean", "backend clean", "backend up", "front up"]
    assert not (w.inst.state_dir / "update.journal.json").exists()
    assert list((w.inst.state_dir / "updates").glob("upd-*.json"))
    # the backup is taken before anything else touches the Brain, by the new release
    assert [c[1][2] for c in w.brain_calls[:2]] == ["backup", "verify-backup"]

    code, doc = w.rollback(NEW)
    assert code == 0 and doc["running"] == OLD and w.running_commit() == "a"
    assert (w.inst.current(), w.inst.previous()) == (OLD, NEW)
    assert w.order()[6:] == ["front clean", "backend clean", "backend up", "front up"]


@windows_only
def test_a_new_release_that_will_not_start_restores_the_old_one(world):
    w = world(new_wont_start=True)
    launcher.start(w.inst, w.inst.state())
    code, doc = w.update()
    assert code == 3 and doc["reason"] == "rolled_back" and doc["previous_restored"] is True
    assert "no such flag" in doc["message"] and "no records were lost" in doc["message"]
    assert doc["running"] == OLD and w.running_commit() == "a"
    assert (w.inst.current(), w.inst.previous()) == (OLD, None)
    assert (w.inst.releases / NEW).is_dir()     # kept, as Mark IV keeps it: not used


@windows_only
def test_a_failed_health_check_restores_the_old_one(world):
    w = world(new_unhealthy=True)
    launcher.start(w.inst, w.inst.state())
    code, doc = w.update()
    assert code == 3 and doc["reason"] == "rolled_back" and doc["previous_restored"] is True
    assert "/bad answered 404" in doc["message"]
    assert w.running_commit() == "a" and w.inst.current() == OLD


@windows_only
def test_a_server_not_running_before_is_not_left_hidden(world):
    """Mark IV starts the new release to check it, and leaves it running."""
    w = world()
    code, doc = w.update()
    assert code == 0 and w.running_commit() == "b"


def test_a_damaged_new_release_is_refused_before_the_server_is_touched(world):
    w = world()
    (w.inst.releases / NEW / "app/manifest.json").write_text("{}", "utf-8")
    with pytest.raises(launcher.Refused, match="not whole"):
        w.update()
    assert w.inst.current() == OLD and not (w.inst.state_dir / "update.journal.json").exists()
    assert w.brain_calls == []


@windows_only
def test_a_damaged_old_release_is_not_switched_back_to(world):
    w = world(new_unhealthy=True)
    launcher.start(w.inst, w.inst.state())
    (w.inst.releases / OLD / "app/manifest.json").write_text("{}", "utf-8")
    code, doc = w.update()
    assert code == 4 and w.running_commit() is None
    said = json.loads((w.inst.state_dir / "needs-attention.json").read_text())
    assert "damaged" in said["why"] and said["nothing_deleted"] is True


@windows_only
def test_an_old_release_too_damaged_to_say_what_it_reads_is_not_gone_back_to(world):
    w = world(new_unhealthy=True)
    launcher.start(w.inst, w.inst.state())
    (w.inst.releases / OLD / "app/BUILD.json").write_text("{}", "utf-8")
    code, doc = w.update()
    assert code == 4 and doc["reason"] == "needs_attention"


def test_rollback_needs_a_previous_release(world):
    w = world()
    with pytest.raises(launcher.Refused, match="no previous"):
        updater._rollback(w.inst, w.a())


@windows_only
def test_rollback_to_a_damaged_release_is_refused(world):
    w = world()
    assert w.update()[0] == 0
    (w.inst.releases / OLD / "app/BUILD.json").write_text("{}", "utf-8")
    with pytest.raises(launcher.Refused, match="damaged.*nothing was changed"):
        w.rollback(NEW)
    assert w.running_commit() == "b"


# the Brain ------------------------------------------------------------------------

@windows_only
def test_a_migration_is_run_by_the_new_release_after_its_backup(world):
    w = world(new_target=2)
    assert w.update()[0] == 0
    calls = [c[1] for c in w.brain_calls]
    assert calls.index(("-m", "mentis.brain", "backup")) < calls.index(("-m", "mentis.migrate", w.brain))
    assert (NEW, ("-m", "mentis.migrate", w.brain)) in w.brain_calls
    assert w.facts["version"] == 2


@windows_only
def test_rollback_over_an_additive_migration_goes_back(world):
    w = world(new_target=2, new_min_reader=1)
    assert w.update()[0] == 0
    code, doc = w.rollback(NEW)
    assert code == 0 and w.running_commit() == "a"
    assert w.facts["version"] == 2      # never migrated down, never restored


@windows_only
def test_rollback_over_a_breaking_migration_is_refused_in_true_words(world):
    w = world(new_target=2, new_min_reader=2)
    assert w.update()[0] == 0
    with pytest.raises(launcher.Refused, match="(?s)start old code on a Brain it cannot read.*nothing was changed"):
        w.rollback(NEW)
    assert w.running_commit() == "b" and w.inst.current() == NEW


@windows_only
def test_unhealthy_after_an_additive_migration_goes_back_on_the_migrated_brain(world):
    w = world(new_target=2, new_min_reader=1, new_unhealthy=True)
    launcher.start(w.inst, w.inst.state())
    code, doc = w.update()
    assert code == 3 and doc["reason"] == "rolled_back" and w.running_commit() == "a"
    assert w.facts["version"] == 2


@windows_only
def test_unhealthy_after_a_breaking_migration_stops_and_restores_nothing(world):
    w = world(new_target=2, new_min_reader=2, new_unhealthy=True)
    launcher.start(w.inst, w.inst.state())
    code, doc = w.update()
    assert code == 4 and doc["reason"] == "needs_attention"
    assert "cannot open the Brain" in doc["message"]
    assert w.running_commit() is None     # neither is left running
    said = json.loads((w.inst.state_dir / "needs-attention.json").read_text())
    assert said["nothing_deleted"] is True and "restore-plan" in said["restore_plan_command"]
    assert not [c for c in w.brain_calls if "restore" in c[1]]
    # start will not get round it, and a resume says it again
    assert updater.before_start(w.at(NEW)) == 4
    assert updater.recover(w.at(NEW))[0] == 4
    # somebody restores the backup: now the old release can read it, and it goes back
    w.facts.update(version=1, min_reader=1)
    code, doc = updater.recover(w.at(NEW))
    assert code == 3 and doc["reason"] == "rolled_back" and w.running_commit() == "a"
    assert not (w.inst.state_dir / "needs-attention.json").exists()


def test_a_brain_the_new_release_cannot_open_is_refused_before_anything(world):
    w = world(new_target=1)
    w.facts.update(version=3, min_reader=3)
    with pytest.raises(launcher.Refused, match="cannot open this Brain"):
        w.update()
    assert w.inst.current() == OLD and w.brain_calls == []


@pytest.mark.parametrize("facts,says", [
    ({"problems": ["a broken ledger"]}, "needs attention"),
    ({"legacy_open": True}, "older than the schema ledger"),
    ({"version": None, "state": "unadopted"}, "no schema ledger"),
    ({"exists": False, "version": None, "problems": ["no Brain there"]}, "no Brain at"),
])
def test_a_brain_in_trouble_is_refused_before_anything(world, facts, says):
    w = world()
    w.facts.update(facts)
    with pytest.raises(launcher.Refused, match=says):
        w.update()
    assert w.inst.current() == OLD and w.brain_calls == []


def test_can_read_is_the_open_gate():
    from mentis.spine import migrations
    assert updater.can_read(2, {"version": 2, "min_reader": 2, "problems": []})
    assert updater.can_read(2, {"version": 3, "min_reader": 2, "problems": []})
    assert not updater.can_read(2, {"version": 3, "min_reader": 3, "problems": []})
    assert not updater.can_read(2, {"version": 1, "min_reader": 1, "problems": []})
    assert not updater.can_read(2, {"version": 2, "min_reader": 1, "problems": ["x"]})
    # the same words as the gate it copies, which a change to the gate must revisit
    assert "version == t or (version > t and st.min_reader <= t)" in pathlib.Path(migrations.__file__).read_text("utf-8")


# a kill ---------------------------------------------------------------------------

KILLS = [("state:APPROVED", "a"), ("state:STOPPED", "a"), ("state:BACKED_UP", "a"), ("before:C1", "a"),
         ("after:C1", "a"), ("state:MIGRATED", "b"), ("before:C2", "b"), ("after:C2", "b"),
         ("state:SWITCHED", "b"), ("started", "b"), ("state:HEALTHY", "b"), ("state:COMMITTED", "b")]


@windows_only
@pytest.mark.parametrize("label,ends", KILLS)
def test_a_kill_at_each_step_leaves_a_usable_install_that_recovers(world, label, ends):
    w = world()
    launcher.start(w.inst, w.inst.state())
    w.kill_label = label
    with pytest.raises(Killed):
        w.update()
    # `state\current` always names a whole release, and the journal is what is left
    assert w.inst.current() in (OLD, NEW)
    assert not updater._damage(w.inst.releases / w.inst.current())
    assert (w.inst.state_dir / "update.journal.json").exists()

    code, doc = updater.recover(w.at(NEW))
    assert code in (0, 3), doc
    assert not (w.inst.state_dir / "update.journal.json").exists()
    assert w.running_commit() == ends, (label, doc)
    assert w.inst.current() == (NEW if ends == "b" else OLD)


@windows_only
def test_a_kill_past_a_real_migration_goes_forward_whatever_the_journal_says(world):
    w = world(new_target=2)
    launcher.start(w.inst, w.inst.state())
    w.kill_label = "after:C1"
    with pytest.raises(Killed):
        w.update()
    assert w.inst.current() == OLD and w.facts["version"] == 2      # migrated, not switched
    code, doc = updater.recover(w.at(NEW))
    assert code == 0 and w.inst.current() == NEW and w.running_commit() == "b"


@windows_only
@pytest.mark.parametrize("label", ["rollingback:stopped", "rollingback:pointed", "rollingback:started"])
def test_a_kill_while_switching_back_finishes_switching_back(world, label):
    w = world(new_unhealthy=True)
    launcher.start(w.inst, w.inst.state())
    w.kill_label = label
    with pytest.raises(Killed):
        w.update()
    code, doc = updater.recover(w.at(NEW))
    assert code == 3 and doc["reason"] == "rolled_back"
    assert w.running_commit() == "a" and w.inst.current() == OLD


@windows_only
def test_a_kill_in_a_rollback_recovers(world):
    w = world()
    assert w.update()[0] == 0
    w.kill_label = "state:STOPPED"
    with pytest.raises(Killed):
        w.rollback(NEW)
    code, doc = updater.recover(w.at(NEW))
    assert code == 3 and doc["reason"] == "aborted" and w.running_commit() == "b"
    assert (w.inst.releases / OLD).is_dir()     # a rollback never discards where it was going


@windows_only
def test_start_recovers_first(world):
    w = world()
    w.kill_label = "state:STOPPED"
    with pytest.raises(Killed):
        w.update()
    assert updater.before_start(w.at(OLD)) is None
    assert not (w.inst.state_dir / "update.journal.json").exists()


def test_a_journal_of_a_format_this_release_does_not_know_is_refused(world):
    w = world()
    updater._write(w.inst.state_dir / "update.journal.json", {"format": 99, "state": "x"})
    code, doc = updater._resume(w.inst)
    assert code == 2 and "format 99" in doc["message"]


def test_setup_will_not_run_over_an_unfinished_update(world):
    w = world()
    updater._write(w.inst.state_dir / "update.journal.json", {"format": 1, "state": "x"})
    with pytest.raises(launcher.Refused, match="update --resume"):
        launcher.setup(w.inst, setup_args(owner="@me"), False)


def test_a_second_update_at_once_is_refused(world):
    w = world()
    with updater._update_lock(w.inst):
        with pytest.raises(launcher.Refused, match="another update"):
            w.update()


# staging --------------------------------------------------------------------------

def fake_unpack(content):
    def unpack(package, into):
        shutil.copytree(content, into)
    return unpack


def test_a_package_that_is_not_a_setup_exe_is_refused_unrun(tmp_path):
    other = tmp_path / "other.exe"
    other.write_bytes(b"MZ not ours")
    with pytest.raises(launcher.Refused, match="not a Mentis setup"):
        updater._unpack(other, tmp_path / "into")
    assert not (tmp_path / "into").exists()


def test_a_package_its_sha256_disowns_is_refused_unrun(tmp_path):
    exe = tmp_path / "Mentis-Setup.exe"
    exe.write_bytes(b"MZ" + updater.SETUP_MARK)
    (tmp_path / "Mentis-Setup.exe.sha256").write_text("0" * 64 + "  x\n", "utf-8")
    with pytest.raises(launcher.Refused, match="is not what"):
        updater._unpack(exe, tmp_path / "into")


def test_a_changed_payload_never_reaches_the_releases(world, monkeypatch, tmp_path):
    w = world()
    bad = tmp_path / "bad"
    shutil.copytree(w.inst.releases / NEW, bad)
    (bad / "app/BUILD.json").write_text(json.dumps({"version": "0.1.0", "commit": "c" * 40}), "utf-8")
    monkeypatch.setattr(updater, "_unpack", fake_unpack(bad))
    a = w.a(package=str(_exists(tmp_path)), staged_here=False)
    with pytest.raises(launcher.Refused, match="was refused"):
        updater._stage_and_hand_over(w.inst, a)
    assert not list(w.inst.releases.glob(".incoming*")) and not (w.inst.releases / ("0.1.0+" + "c" * 12)).exists()
    assert w.inst.current() == OLD


def _exists(tmp_path):
    path = tmp_path / "pkg.exe"
    path.write_bytes(b"x")
    return path


def test_the_current_release_as_a_package_is_refused(world, monkeypatch, tmp_path):
    w = world()
    monkeypatch.setattr(updater, "_unpack", fake_unpack(w.inst.releases / OLD))
    with pytest.raises(launcher.Refused, match="already the current"):
        updater._stage_and_hand_over(w.inst, w.a(package=str(_exists(tmp_path)), staged_here=False))
    assert not list(w.inst.releases.glob(".incoming*"))


def test_a_kill_while_staging_leaves_only_what_the_next_update_clears(world, monkeypatch, tmp_path):
    w = world()
    (w.inst.releases / ".incoming-1").mkdir()
    (w.inst.releases / (NEW + ".partial")).mkdir()
    updater._clear_incoming(w.inst)
    assert sorted(d.name for d in w.inst.releases.iterdir()) == sorted([OLD, NEW])


def test_a_package_placed_and_refused_by_the_new_release_is_removed_by_the_old(world, tmp_path):
    w = world()
    assert updater._undo_staged(w.inst, NEW, True, 2, {"x": 1}) == (2, {"x": 1})
    assert not (w.inst.releases / NEW).exists()


def test_a_kept_previous_release_is_never_removed_by_a_refusal(world):
    w = world()
    w.inst.point(OLD, NEW)
    updater._undo_staged(w.inst, NEW, True, 2, {})
    assert (w.inst.releases / NEW).is_dir()


@windows_only
def test_a_commit_removes_no_release(world):
    w = world()
    (w.inst.releases / "0.0.1+cccccccccccc").mkdir()
    assert w.update()[0] == 0
    assert sorted(d.name for d in w.inst.releases.iterdir()) == sorted([OLD, NEW, "0.0.1+cccccccccccc"])


@windows_only
def test_a_switched_back_release_stays_as_the_words_say(world):
    w = world(new_unhealthy=True)
    launcher.start(w.inst, w.inst.state())
    code, doc = w.update()
    assert code == 3 and "is kept but not used" in doc["message"]
    assert updater._undo_staged(w.inst, NEW, True, code, doc) == (code, doc)
    assert (w.inst.releases / NEW).is_dir()


def test_a_damaged_copy_is_set_aside_never_deleted(world, tmp_path):
    w = world()
    good = tmp_path / "good"
    shutil.copytree(w.inst.releases / NEW, good)
    (w.inst.releases / NEW / "app/manifest.json").write_text("damaged", "utf-8")
    assert updater.place(w.inst, good, w.build_of(NEW), move=False) is True
    assert not updater._damage(w.inst.releases / NEW)
    aside = list(w.inst.releases.glob(NEW + ".damaged-*"))
    assert len(aside) == 1 and (aside[0] / "app/manifest.json").read_text("utf-8") == "damaged"


def test_a_damaged_copy_stays_when_the_new_one_does_not_verify(world, tmp_path):
    w = world()
    bad = tmp_path / "bad"
    shutil.copytree(w.inst.releases / NEW, bad)
    (bad / "app/manifest.json").write_text("changed", "utf-8")
    (w.inst.releases / NEW / "app/manifest.json").write_text("damaged", "utf-8")
    with pytest.raises(launcher.Refused):
        updater.place(w.inst, bad, w.build_of(NEW), move=False)
    assert (w.inst.releases / NEW / "app/manifest.json").read_text("utf-8") == "damaged"
    assert not list(w.inst.releases.glob(NEW + ".damaged-*"))


@windows_only
def test_running_work_holds_the_update_and_then_lets_it_go(world):
    import threading
    w = world()
    launcher.start(w.inst, w.inst.state())
    pids = [e["pid"] for e in w.inst.running()]
    busy = pathlib.Path(str(w.log) + ".busy")
    busy.write_text("running")
    a = w.a(drain_wait=1)
    code, doc = updater.transact(w.at(NEW), a, NEW, kind="update", made=False)
    assert code == 3 and doc["reason"] == "aborted" and "did not finish" in doc["message"]
    assert [e["pid"] for e in w.inst.running()] == pids and w.inst.current() == OLD and w.brain_calls == []
    # a run the runtime has ended holds nothing, as `runs.is_live` reads it
    threading.Timer(1, lambda: busy.write_text("runtime-ended")).start()
    code, doc = updater.transact(w.at(NEW), w.a(drain_wait=30), NEW, kind="update", made=False)
    assert code == 0 and w.running_commit() == "b"


@windows_only
def test_something_else_holding_the_brain_is_not_gone_past(world, monkeypatch):
    w = world()
    monkeypatch.setattr(updater, "OPEN_WAIT_S", 0.3)
    w.brain_open = True
    code, doc = w.update()
    assert code == 3 and doc["reason"] == "aborted" and "still has the Brain" in doc["message"]
    assert w.brain_calls == [] and w.inst.current() == OLD


@windows_only
def test_a_resume_while_the_brain_is_held_is_refused_and_keeps_everything(world, monkeypatch):
    monkeypatch.setattr(updater._await_openers, "__defaults__", (0.3,))
    w = world()
    w.kill_label = "state:BACKED_UP"
    with pytest.raises(Killed):
        w.update()
    w.brain_open = True
    code, doc = updater.recover(w.at(NEW))
    assert code == 2 and "still running" in doc["message"]
    assert (w.inst.state_dir / "update.journal.json").exists() and (w.inst.releases / NEW).is_dir()
    w.brain_open = False
    assert updater.recover(w.inst)[1]["reason"] == "aborted"


@windows_only
def test_a_resume_that_could_go_either_way_tries_the_new_release_first(world, monkeypatch):
    """Mark IV's order (N3): a repaired install finishes what the owner approved."""
    w = world(new_unhealthy=True)
    good = (w.inst.releases / OLD / "app/manifest.json").read_bytes()
    launcher.start(w.inst, w.inst.state())
    (w.inst.releases / OLD / "app/manifest.json").write_text("{}", "utf-8")
    assert w.update()[0] == 4
    (w.inst.releases / OLD / "app/manifest.json").write_bytes(good)
    monkeypatch.setattr(updater, "_drive", lambda inst, j, say: ("forward", j["state"]))
    assert updater.recover(w.at(NEW)) == ("forward", "SWITCHED")


@pytest.mark.parametrize("version,direction,major", [
    ("0.2.0", "upgrade", False), ("1.0.0", "upgrade", True), ("0.0.9", "downgrade", False),
    ("0.1.0", "same version, other commit", False)])
def test_the_plan_says_which_way_it_goes(world, version, direction, major):
    w = world()
    p = updater.plan(w.inst, {**w.build_of(NEW), "version": version})
    assert p["direction"] == direction and p["major"] is major and direction in updater.describe(p)
    assert ("BREAKING" in updater.describe(p)) is major


@pytest.mark.parametrize("answer,yes", [("y
", True), ("
", False), ("", False)])
def test_asking_leaves_stdout_to_the_one_answer(monkeypatch, capsys, answer, yes):
    """Windows says NUL is a terminal, so a program with no stdin gets here too."""
    import io
    stdin = io.StringIO(answer)
    stdin.isatty = lambda: True
    monkeypatch.setattr(sys, "stdin", stdin)
    assert updater._confirmed(types.SimpleNamespace(yes=False)) is yes
    said = capsys.readouterr()
    assert said.out == "" and "[y/N]" in said.err


def test_an_unexpected_failure_still_gives_one_answer(world, monkeypatch, capsys):
    w = world()
    def boom(inst):
        raise KeyError("x")
    monkeypatch.setattr(updater, "_resume", boom)
    assert updater.command(w.inst, w.a(resume=True, staged_here=False)) == 3
    said = json.loads(capsys.readouterr().out)
    assert said["outcome"] == "failed" and said["reason"] == "crashed" and "--resume" in said["message"]


def test_status_says_an_update_is_unfinished(world):
    w = world()
    w.kill_label = "state:APPROVED"
    with pytest.raises(Killed):
        w.update()
    said = updater.status(w.inst)["unfinished_update"]
    assert said["state"] == "APPROVED" and said["to"] == NEW


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
    """HEAD built, installed, set up, opened, restarted, updated, rolled back, broken
    every way and killed at every step, and uninstalled, under tmp_path. The newer
    build is HEAD stamped with another commit. Refuses to run if this user has an
    install already."""
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
                           encoding="utf-8", errors="replace", timeout=3600)
    assert prove.returncode == 0, prove.stdout[-4000:] + prove.stderr[-2000:]
    assert all(s["ok"] for s in json.loads(prove.stdout)["steps"])
