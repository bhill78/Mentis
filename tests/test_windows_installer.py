"""A build from main must stay installable on Windows.

The ordinary tests read the source tree (`problems`) and run the launcher against
small stand-ins; they fail when somebody adds an import the install does not carry,
drops a payload file, or changes what the server is started with. `-m installer`
really builds the installer and installs it (tools/prove_windows_installer.py);
minutes, a real install and network, so it is opted into. docs/windows-installer.md.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import types

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "installer"))

from mentis.spine import backup  # noqa: E402

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


@pytest.mark.parametrize("gone", ["/EXTRACT=", "arrive", "/remove:d", "/FULLBACKUP", "--backup-question"])
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
    (inst.app / "FILES.json").write_text(json.dumps({}), "utf-8")
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
        self.brain_args = []
        self.brain_fails = None
        self.backup_kind = None
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
        monkeypatch.setattr(updater, "_corpus_id_of", lambda brain: "corpus-id", raising=False)
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
        self.brain_args.append(args)
        ok = types.SimpleNamespace(returncode=0, stderr="", stdout="{}")
        if self.brain_fails and args[2:3] == (self.brain_fails[0],):
            return self.brain_fails[1](args)
        if "mentis.migrate" in args:
            self.facts.update(version=self.target_of(name), min_reader=self.min_reader_of(name))
        elif "backup" in args:
            kind = "portable" if "--portable" in args else "local-recovery"
            ok.stdout = json.dumps({"backup": str(self.root.parent / "backups" / "one"), "kind": kind})
            self.backup_kind = kind
        elif "verify-backup" in args:
            ok.stdout = json.dumps({"usable": True, "kind": self.backup_kind})
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
        if args[:1] in (("start",), ("open",)):
            try:
                launcher.start(there, there.state(), in_update="--in-update" in args)
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

    def update(self, **kw):
        """What the new release's own launcher does, once it is placed."""
        return updater.transact(self.at(NEW), self.a(**kw), NEW, kind="update", made=True)

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


# a repair: `state\\current` never names a release that is away -----------------------

REPAIR_KILLS = ["repair:verified", "repair:copied", "repair:set-aside", "repair:replacing", "repair:replaced"]


def _with_a_last_file(w, name):
    """Three files, so that the launch files can be whole and the last one not."""
    import hashlib
    home = w.inst.releases / name
    (home / "app/z.txt").write_text("the last file", "utf-8")
    files = json.loads((home / "app/FILES.json").read_text("utf-8"))
    files["app/z.txt"] = hashlib.sha256(b"the last file").hexdigest()
    (home / "app/FILES.json").write_text(json.dumps(files), "utf-8")


def _arriving_from(w, name, tmp_path, monkeypatch):
    good = tmp_path / "good" / name
    shutil.copytree(w.inst.releases / name, good)
    monkeypatch.setattr(launcher, "__file__", str(good / "app/launcher.py"))
    return good


def _arrive(w):
    return updater.arrive(w.inst, types.SimpleNamespace(root=str(w.root), plan=False, yes=True))


def route_over_itself(w, tmp_path, monkeypatch):
    _with_a_last_file(w, OLD)
    _arriving_from(w, OLD, tmp_path, monkeypatch)
    return OLD, lambda: _arrive(w)


def route_arriving_over_previous(w, tmp_path, monkeypatch):
    _with_a_last_file(w, NEW)
    w.inst.point(OLD, NEW)
    _arriving_from(w, NEW, tmp_path, monkeypatch)
    monkeypatch.setattr(updater, "_hand_over", lambda *a: (0, {}))
    return NEW, lambda: _arrive(w)


def route_staged_over_previous(w, tmp_path, monkeypatch):
    _with_a_last_file(w, NEW)
    w.inst.point(OLD, NEW)
    good = tmp_path / "good" / NEW
    shutil.copytree(w.inst.releases / NEW, good)
    monkeypatch.setattr(updater, "_unpack", fake_unpack(good))
    monkeypatch.setattr(updater, "_hand_over", lambda *a: (0, {}))
    a = w.a(package=str(_exists(tmp_path)), staged_here=False)
    return NEW, lambda: updater._stage_and_hand_over(w.inst, a)


def route_under_an_unfinished_update(w, tmp_path, monkeypatch):
    _with_a_last_file(w, OLD)
    w.kill_label = "state:APPROVED"
    with pytest.raises(Killed):
        w.update()
    _arriving_from(w, OLD, tmp_path, monkeypatch)
    return OLD, lambda: _arrive(w)


REPAIR_ROUTES = [route_over_itself, route_arriving_over_previous, route_staged_over_previous,
                 route_under_an_unfinished_update]


def _damage_it(w, name):
    home = w.inst.releases / name
    for rel in ("app/manifest.json", "app/z.txt"):
        (home / rel).write_text("damaged", "utf-8")
    return home


def _every_named_release_is_there(w, named):
    assert (w.inst.current(), w.inst.previous()) == named
    for name in named:
        if name:
            home = w.inst.releases / name
            assert home.is_dir()
            assert all((home / rel).is_file() for rel in json.loads((home / "app/FILES.json").read_text("utf-8")))


@pytest.mark.parametrize("route", REPAIR_ROUTES)
@pytest.mark.parametrize("label", REPAIR_KILLS)
def test_a_kill_in_a_repair_leaves_every_named_release_there_and_the_exe_finishes_it(
        world, tmp_path, monkeypatch, route, label):
    w = world()
    name, run = route(w, tmp_path, monkeypatch)
    home = _damage_it(w, name)
    named = (w.inst.current(), w.inst.previous())
    w.kill_label = label
    with pytest.raises(Killed):
        run()
    assert w.killed_at == label
    _every_named_release_is_there(w, named)
    copied = list(w.inst.releases.glob(name + ".damaged-*"))
    if label in REPAIR_KILLS[2:]:
        assert [d.name for d in copied if d.name.endswith(".partial")] == []
        assert (copied[0] / "app/manifest.json").read_text("utf-8") == "damaged"
    if label == "repair:replacing":
        assert (home / "app/z.txt").read_text("utf-8") == "damaged"
        assert (home / "app/manifest.json").read_text("utf-8") != "damaged"

    run()
    assert not updater._damage(home)
    assert not [d.name for d in w.inst.releases.iterdir() if d.name.endswith(".partial")]
    assert list(w.inst.releases.glob(name + ".damaged-*"))
    assert w.inst.current() == named[0]


def test_at_no_instant_of_a_repair_is_the_release_or_one_of_its_files_away(world, tmp_path, monkeypatch):
    w = world()
    name, run = route_over_itself(w, tmp_path, monkeypatch)
    home = _damage_it(w, name)
    files = json.loads((home / "app/FILES.json").read_text("utf-8"))
    looked = []

    def look(*_):
        looked.append(all((home / rel).is_file() for rel in files) and w.inst.current() == name)
    real = updater.os.replace

    def watching(a, b):
        look()
        real(a, b)
        look()

    def no_rename(*a):
        raise AssertionError(f"a release is not renamed: {a}")
    monkeypatch.setattr(updater.os, "replace", watching)
    monkeypatch.setattr(updater.os, "rename", no_rename)
    monkeypatch.setattr(updater, "_hook", look)
    run()
    assert len(looked) > 10 and all(looked) and not updater._damage(home)


def _final_replace_fails(monkeypatch, home):
    real = updater.os.replace

    def failing(a, b):
        if pathlib.Path(b) == home / "app/z.txt":
            raise PermissionError(13, "held by something else")
        real(a, b)
    monkeypatch.setattr(updater.os, "replace", failing)
    monkeypatch.setattr(updater.time, "sleep", lambda s: None)


@pytest.mark.parametrize("route", REPAIR_ROUTES)
def test_the_final_replace_failing_leaves_every_named_release_there(world, tmp_path, monkeypatch, route):
    w = world()
    name, run = route(w, tmp_path, monkeypatch)
    home = _damage_it(w, name)
    named = (w.inst.current(), w.inst.previous())
    with monkeypatch.context() as m:
        _final_replace_fails(m, home)
        with pytest.raises(updater.NotRepaired, match="(?s)1 of 2 damaged files replaced.*not whole.*again"):
            run()
    _every_named_release_is_there(w, named)
    assert launcher.verify_dir(home)["changed"] == ["app/z.txt"]
    assert not list(w.inst.releases.glob("*.partial"))
    run()
    assert not updater._damage(home)


def _refused_and_nothing_started(w, capsys, argv, *damaged):
    """`mentis.cmd <argv>` on a damaged release, nothing having been running."""
    got = launcher.main(argv, w.inst)
    said = capsys.readouterr()
    assert got != 0 and said.out == ""
    assert "nothing was started" in said.err and "setup exe" in said.err and "repairs them" in said.err
    assert f"Mentis-Setup-{w.inst.release.replace('+', '-')}.exe" in said.err
    for rel in damaged:
        assert rel in said.err
    assert w.inst.running() == [] and not w.inst.running_file.exists()
    assert not w.log.exists() and w.running_commit() is None
    return said.err


@windows_only
def test_after_the_final_replace_failed_start_refuses_and_the_exe_repairs_it(world, tmp_path, monkeypatch, capsys):
    w = world()
    name, run = route_over_itself(w, tmp_path, monkeypatch)
    home = _damage_it(w, name)
    a = types.SimpleNamespace(root=str(w.root), plan=False, yes=True, command="arrive")
    with monkeypatch.context() as m:
        _final_replace_fails(m, home)
        assert updater.command(w.inst, a) == 3
    said = capsys.readouterr().out
    assert "could not be repaired" in said and "app/z.txt" in said and "not whole" in said
    assert "could not be repaired" in (w.inst.logs / "update.log").read_text("utf-8")
    _refused_and_nothing_started(w, capsys, ["start"], "app/z.txt")
    assert updater.command(w.inst, a) == 0
    capsys.readouterr()
    assert launcher.main(["start"], w.inst) == 0
    assert w.running_commit() == "a"


@windows_only
@pytest.mark.parametrize("label", REPAIR_KILLS[:-1])
def test_after_a_kill_in_a_repair_start_refuses_and_the_exe_repairs_it(world, tmp_path, monkeypatch, capsys, label):
    w = world()
    name, run = route_over_itself(w, tmp_path, monkeypatch)
    _damage_it(w, name)
    w.kill_label = label
    with pytest.raises(Killed):
        run()
    capsys.readouterr()
    _refused_and_nothing_started(w, capsys, ["start"], "app/z.txt")
    run()
    assert launcher.main(["start"], w.inst) == 0
    assert w.running_commit() == "a"


@windows_only
def test_a_kill_after_the_last_replace_leaves_it_whole_and_start_works(world, tmp_path, monkeypatch):
    w = world()
    name, run = route_over_itself(w, tmp_path, monkeypatch)
    _damage_it(w, name)
    w.kill_label = "repair:replaced"
    with pytest.raises(Killed):
        run()
    assert launcher.main(["start"], w.inst) == 0
    assert w.running_commit() == "a"


# a damaged release is not started -----------------------------------------------------

def _start_routes(w, tmp_path, monkeypatch):
    fake_bootstrap(monkeypatch)
    monkeypatch.setattr("webbrowser.open", lambda url: pytest.fail("the browser was opened"))
    return {"start": ["start"], "open": ["open", "--no-browser"],
            "setup": ["setup", "--brain", w.brain, "--owner", "@o", "--port", str(w.port), "--no-browser"]}


@pytest.mark.parametrize("route", ["start", "open", "setup"])
@pytest.mark.parametrize("change", ["changed", "missing"])
def test_no_route_starts_a_damaged_release(world, tmp_path, monkeypatch, capsys, route, change):
    """Removing the guard fails this: each of these would then launch the server."""
    w = world()
    argv = _start_routes(w, tmp_path, monkeypatch)[route]
    target = w.inst.home / "app/manifest.json"
    if change == "changed":
        target.write_text("{}", "utf-8")
    else:
        target.unlink()
    said = _refused_and_nothing_started(w, capsys, argv, "app/manifest.json")
    assert f"{change}: app/manifest.json" in said


def test_setup_runs_no_code_of_a_damaged_release_on_a_brain(world, monkeypatch, capsys):
    w = world()
    calls = fake_bootstrap(monkeypatch)
    (w.inst.home / "app/manifest.json").write_text("{}", "utf-8")
    _refused_and_nothing_started(w, capsys, ["setup", "--brain", w.brain, "--owner", "@o", "--no-start"],
                                 "app/manifest.json")
    assert calls == []


def test_start_refuses_before_it_looks_at_anything_else(world, monkeypatch):
    """Its own imports may be what is damaged, and what it starts is not read yet."""
    w = world()
    (w.inst.home / "app/manifest.json").write_text("not even json", "utf-8")
    monkeypatch.setitem(sys.modules, "psutil", None)
    with pytest.raises(launcher.Refused, match="(?s)nothing was started.*changed: app/manifest.json"):
        launcher.start(w.inst, w.inst.state())


@pytest.mark.parametrize("content", ["not json", "[]"])
def test_a_file_list_that_cannot_be_read_is_damage_in_words(world, capsys, content):
    w = world()
    (w.inst.home / "app/FILES.json").write_text(content, "utf-8")
    said = _refused_and_nothing_started(w, capsys, ["start"])
    assert "could not be checked" in said


def test_a_list_of_damage_is_not_every_file_on_the_machine(world):
    w = world()
    files = {f"app/{i}.txt": "0" * 64 for i in range(50)}
    (w.inst.home / "app/FILES.json").write_text(json.dumps(files), "utf-8")
    with pytest.raises(launcher.Refused, match=r"app/19\.txt, and 30 more.*mentis\.cmd verify") as got:
        launcher.start(w.inst, w.inst.state())
    assert "app/20.txt" not in str(got.value)


@windows_only
def test_a_damaged_release_is_never_already_running_and_the_refusal_stops_nothing(world, capsys):
    w = world()
    launcher.start(w.inst, w.inst.state())
    before = w.inst.running_file.read_bytes()
    pids = [e["pid"] for e in w.inst.running()]
    (w.inst.home / "app/manifest.json").write_text("{}", "utf-8")
    assert launcher.main(["start"], w.inst) != 0
    said = capsys.readouterr()
    assert "already_running" not in said.out and "app/manifest.json" in said.err and "left running" in said.err
    assert w.inst.running_file.read_bytes() == before
    assert all(launcher._alive(e) for e in w.inst.running()) and pids == [e["pid"] for e in w.inst.running()]
    assert w.order() == ["backend up", "front up"]      # nothing more started, nothing stopped


@windows_only
def test_recovering_an_update_does_not_start_a_damaged_current_release_after_it(world, capsys):
    """The undo says it was not started again; `start` carrying on must not do it either."""
    w = world()
    w.kill_label = "state:STOPPED"
    with pytest.raises(Killed):
        w.update()
    (w.inst.home / "app/manifest.json").write_text("{}", "utf-8")
    capsys.readouterr()
    said = _refused_and_nothing_started(w, capsys, ["start"], "app/manifest.json")
    assert "the update did not happen" in said
    assert not (w.inst.state_dir / "update.journal.json").exists()


@windows_only
def test_a_recovery_that_hands_over_is_refused_by_the_release_it_hands_to(world, monkeypatch, capsys):
    """Finished forward, `current` is another release, whose own launcher takes the start."""
    w = world()
    w.kill_label = "state:SWITCHED"
    with pytest.raises(Killed):
        w.update()
    assert w.inst.current() == NEW
    (w.inst.releases / NEW / "app/manifest.json").write_text("{}", "utf-8")
    monkeypatch.setattr(updater, "_resume", lambda inst: (0, {"message": "it finished forward"}))
    monkeypatch.setattr(sys, "argv", ["launcher.py", "start"])
    capsys.readouterr()
    assert launcher.main(["start"], w.at(OLD)) == 1
    assert "app/manifest.json" in capsys.readouterr().err and w.at(NEW).running() == []


# -- recovery never reports success for a damaged release, or starts one ------------
#
# Every way out of `_recover` that can report success or start something. One row each:
# what the kill left, and how the damaged `to` release is met.

PAST_THE_SWITCH = ["after:C2", "state:SWITCHED", "started", "state:HEALTHY", "state:COMMITTED"]


def _killed_then_damaged(w, label, *releases):
    launcher.start(w.inst, w.inst.state())
    w.kill_label = label
    with pytest.raises(Killed):
        w.update()
    for name in releases or (NEW,):
        (w.inst.releases / name / "app/manifest.json").write_text("{}", "utf-8")


def _no_success_recorded(w, outcome):
    archived = [json.loads(p.read_text("utf-8")) for p in (w.inst.state_dir / "updates").glob("upd-*.json")]
    assert [a["outcome"] for a in archived] == [outcome]
    assert not (w.inst.state_dir / "update.journal.json").exists()


@windows_only
@pytest.mark.parametrize("label", PAST_THE_SWITCH)
def test_resumed_past_the_switch_a_damaged_new_release_is_switched_back_from(world, label):
    """`_step_healthy`'s start, its `who` already serving branch, HEALTHY going straight on
    and COMMITTED: all one failure path. At COMMITTED only the archiving was left, and the
    journal says it is not over, so it is treated as what it is, a release not to be used."""
    w = world()
    _killed_then_damaged(w, label)
    code, doc = updater.recover(w.at(OLD))
    assert code == 3 and doc["reason"] == "rolled_back" and doc["previous_restored"] is True, doc
    assert "not whole" in doc["message"] and "Mentis is now" not in doc["message"]
    assert (w.inst.current(), w.running_commit()) == (OLD, "a")
    _no_success_recorded(w, updater.ROLLED_BACK)


@windows_only
@pytest.mark.parametrize("command", [["start"], ["open", "--no-browser"]])
@pytest.mark.parametrize("label", PAST_THE_SWITCH)
def test_start_and_open_past_the_switch_do_the_same_and_start_the_old_release(world, monkeypatch, capsys, label, command):
    """`mentis.cmd` runs the release `current` names, here the damaged one. It hands the
    resume to a whole one, and the start to whatever `current` then names."""
    w = world()
    _killed_then_damaged(w, label)
    monkeypatch.setattr(sys, "argv", ["launcher.py", *command])
    assert launcher.main(command, w.at(NEW)) == 0
    assert "not whole" in capsys.readouterr().err
    assert (w.inst.current(), w.running_commit()) == (OLD, "a")
    _no_success_recorded(w, updater.ROLLED_BACK)


@windows_only
@pytest.mark.parametrize("label", PAST_THE_SWITCH)
def test_past_a_breaking_migration_it_stops_and_asks(world, label):
    """The old release cannot read the Brain: the same failure path, needing attention."""
    w = world(new_target=2, new_min_reader=2)
    _killed_then_damaged(w, label)
    code, doc = updater.recover(w.at(OLD))
    assert code == 4 and doc["reason"] == "needs_attention", doc
    assert w.at(NEW).running() == []            # nothing is left answering on damaged files
    assert (w.inst.state_dir / "needs-attention.json").exists()
    assert w.inst.current() == NEW and w.facts["version"] == 2


@windows_only
@pytest.mark.parametrize("label", PAST_THE_SWITCH)
def test_with_both_releases_damaged_nothing_is_called_done(world, label):
    """Nothing whole to run a recovery from: `_resume` says so, `start` exits with it."""
    w = world()
    _killed_then_damaged(w, label, NEW, OLD)
    code, doc = updater._resume(w.at(NEW))
    assert code == 4 and doc["reason"] == "needs_attention" and "neither release" in doc["message"]
    assert (w.inst.state_dir / "update.journal.json").exists()
    assert updater.before_start(w.at(NEW)) == 4


@windows_only
@pytest.mark.parametrize("label", ["state:HEALTHY", "state:COMMITTED"])
def test_with_only_the_old_one_damaged_too_the_recovery_still_fails_in_words(world, label):
    """The recovery's own code is whole, the new release is not, the old one is not:
    `_switch_back` will not go back to it."""
    w = world()
    _killed_then_damaged(w, label, NEW, OLD)
    code, doc = updater.recover(w.at(NEW))
    assert code == 4 and doc["reason"] == "needs_attention" and "not switched back" in doc["message"]
    assert w.at(NEW).running() == []


@windows_only
def test_damaged_while_it_was_going_up_it_is_not_committed(world):
    """No kill: the check at the very end of an ordinary update, with its server up."""
    w = world()
    launcher.start(w.inst, w.inst.state())
    seen = w.hook

    def damaging(label):
        seen(label)
        if label == "state:HEALTHY":
            (w.inst.releases / NEW / "app/manifest.json").write_text("{}", "utf-8")
    updater._hook = damaging
    code, doc = w.update()
    assert code == 3 and doc["reason"] == "rolled_back" and "called done" in doc["message"]
    assert (w.inst.current(), w.running_commit()) == (OLD, "a")


@windows_only
def test_a_kill_before_the_switch_past_the_backup_then_damage_is_not_switched_to(world):
    """Forward from MIGRATED goes through the switch's own hash."""
    w = world()
    _killed_then_damaged(w, "state:MIGRATED")
    code, doc = updater.recover(w.at(OLD))
    assert code == 3 and doc["reason"] == "rolled_back" and "not whole" in doc["message"]
    assert (w.inst.current(), w.running_commit()) == (OLD, "a")


@windows_only
def test_a_kill_before_c1_then_damage_is_undone_without_trying_it(world):
    """`_abort`: the new release is not tried, whatever it holds."""
    w = world()
    _killed_then_damaged(w, "state:STOPPED")
    code, doc = updater.recover(w.at(OLD))
    assert code == 3 and doc["reason"] == "aborted" and w.running_commit() == "a"


@windows_only
@pytest.mark.parametrize("label", ["rollingback:stopped", "rollingback:pointed", "rollingback:started"])
def test_a_kill_while_switching_back_then_damage_to_where_it_goes_is_not_healthy(world, label):
    """ROLLING_BACK: `_switch_back` hashes first. A failure, not a restored release."""
    w = world(new_unhealthy=True)
    launcher.start(w.inst, w.inst.state())
    w.kill_label = label
    with pytest.raises(Killed):
        w.update()
    (w.inst.releases / OLD / "app/manifest.json").write_text("{}", "utf-8")
    code, doc = updater.recover(w.at(NEW))
    assert code == 4 and doc["reason"] == "needs_attention" and doc["previous_restored"] is False


@windows_only
def test_a_needs_attention_is_not_resolved_by_a_damaged_release_that_answers(world):
    """NEEDS_ATTENTION's `resolved`: running and healthy is not enough."""
    w = world(new_target=2, new_min_reader=2, new_unhealthy=True)
    launcher.start(w.inst, w.inst.state())
    assert w.update()[0] == 4
    launcher.start(w.at(NEW), w.at(NEW).state(), in_update=True)
    (w.inst.releases / NEW / "app/manifest.json").write_text(
        json.dumps({**json.loads((w.inst.releases / OLD / "app/manifest.json").read_text("utf-8")),
                    "health": []}), "utf-8")
    assert not updater._health(w.at(NEW), NEW)
    code, doc = updater.recover(w.at(NEW))
    assert code == 4 and doc["reason"] == "needs_attention"
    assert (w.inst.state_dir / "update.journal.json").exists()


@windows_only
def test_a_retry_from_attention_goes_through_the_same_checks(world):
    """`_retry_attention` with a release still damaged: it is not tried."""
    w = world(new_target=2, new_min_reader=2, new_unhealthy=True)
    launcher.start(w.inst, w.inst.state())
    assert w.update()[0] == 4
    (w.inst.releases / NEW / "app/manifest.json").write_text("{}", "utf-8")
    code, doc = updater.recover(w.at(NEW))
    assert code == 4 and w.at(NEW).running() == []
    assert (w.inst.state_dir / "update.journal.json").exists()


def test_nothing_unfinished_says_only_that(world):
    code, doc = updater.recover(w_ := world().at(OLD))
    assert code == 0 and doc["reason"] == "nothing_to_resume" and doc["running"] is None
    assert w_.running() == []


@windows_only
@pytest.mark.parametrize("label", PAST_THE_SWITCH)
def test_a_whole_release_is_still_committed_by_a_resume_at_each_point(world, label):
    """What the check must not do: stop a good update finishing."""
    w = world()
    launcher.start(w.inst, w.inst.state())
    w.kill_label = label
    with pytest.raises(Killed):
        w.update()
    code, doc = updater.recover(w.at(NEW))
    assert code == 0 and doc["reason"] == "committed" and "Mentis is now" in doc["message"]
    assert (w.inst.current(), w.running_commit()) == (NEW, "b")


# -- the full backup ----------------------------------------------------------------

def _backup_calls(w):
    return [a[2:] for a in w.brain_args if a[2:3] == ("backup",)]


def _only_the_quick_one(w, code, doc):
    """Asserted first, so that what fails is the backup taken and nothing said about it."""
    assert _backup_calls(w) == [("backup", w.brain)]
    assert code == 0 and doc["full_backup"] is False and doc["backup_kind"] == "local-recovery" and doc["backup"]


@windows_only
def test_asked_for_an_update_takes_the_full_backup(world):
    w = world()
    code, doc = w.update(full_backup=True)
    assert code == 0 and _backup_calls(w)[0][-1] == "--portable"
    assert doc["full_backup"] is True and doc["backup_kind"] == "portable" and doc["backup"]
    assert "Full backup of the Brain, checked usable" in doc["message"]
    assert [a[2] for a in w.brain_args[:2]] == ["backup", "verify-backup"]
    archived = json.loads(next((w.inst.state_dir / "updates").glob("upd-*.json")).read_text("utf-8"))
    assert archived["full_backup"] is True and archived["backup_kind"] == "portable"


@windows_only
def test_no_flag_with_yes_takes_the_quick_one(world):
    w = world()
    a = launcher._parser().parse_args(["update", "--staged-here", "--yes", "--made"])
    code, doc = updater.transact(w.at(NEW), a, NEW, kind="update", made=True)
    _only_the_quick_one(w, code, doc)
    assert "Quick backup, which records stored files" in doc["message"]
    archived = json.loads(next((w.inst.state_dir / "updates").glob("upd-*.json")).read_text("utf-8"))
    assert archived["full_backup"] is False and archived["backup_kind"] == "local-recovery"


@windows_only
def test_no_flag_with_a_person_saying_yes_takes_the_quick_one(world, monkeypatch):
    w = world()
    monkeypatch.setattr(updater, "_confirmed", lambda a, question="Proceed?": True)
    a = launcher._parser().parse_args(["update", "--staged-here", "--made"])
    assert a.yes is False
    code, doc = updater.transact(w.at(NEW), a, NEW, kind="update", made=True)
    _only_the_quick_one(w, code, doc)


def test_the_old_flag_is_gone():
    with pytest.raises(SystemExit):
        launcher._parser().parse_args(["update", "x.exe", "--yes", "--no-full-backup"])
    with pytest.raises(SystemExit):
        launcher._parser().parse_args(["arrive", "--root", "x", "--no-full-backup"])


@windows_only
def test_a_rollback_takes_the_quick_one_whatever_the_update_chose(world):
    """The option is not on `rollback`, and the update's choice does not reach it."""
    w = world()
    assert w.update(full_backup=True)[0] == 0
    w.brain_args.clear()
    code, doc = w.rollback(NEW)
    assert code == 0 and _backup_calls(w) == [("backup", w.brain)]
    assert doc["full_backup"] is False and doc["backup_kind"] == "local-recovery"
    assert doc["message"] == f"Mentis is now {OLD}"     # as it always said
    with pytest.raises(SystemExit):
        launcher._parser().parse_args(["rollback", "--full-backup"])


@windows_only
@pytest.mark.parametrize("asked,kind", [(True, "portable"), (False, "local-recovery")])
def test_a_resumed_update_keeps_the_choice_and_takes_no_second_backup(world, asked, kind):
    w = world()
    launcher.start(w.inst, w.inst.state())
    w.kill_label = "state:SWITCHED"
    with pytest.raises(Killed):
        w.update(full_backup=asked)
    assert updater.journal(w.inst)["full_backup"] is asked
    w.brain_args.clear()
    code, doc = updater.recover(w.at(NEW))
    assert code == 0 and doc["backup_kind"] == kind and doc["full_backup"] is asked
    assert _backup_calls(w) == []


def _fills_up(w):
    def fail(args):
        part = pathlib.Path(w.brain).parent / "backups" / "corpus" / "x.partial"
        part.mkdir(parents=True)
        (part / "corpus.db").write_bytes(b"part of it")
        return types.SimpleNamespace(returncode=1, stdout="", stderr="OSError: [Errno 28] No space left on device")
    return fail


@windows_only
def test_a_backup_that_fails_is_a_failure_before_c1_and_the_old_server_comes_back(world):
    """A disk that fills, as the command reports it. Its unfinished copy goes, so that the
    old server has the room to come back; one from before this update stays."""
    w = world(new_target=2)
    launcher.start(w.inst, w.inst.state())
    older = pathlib.Path(w.brain).parent / "backups" / "corpus" / "older.partial"
    older.mkdir(parents=True)
    w.brain_fails = ("backup", _fills_up(w))
    code, doc = w.update(full_backup=True)
    assert code == 3 and doc["reason"] == "aborted" and doc["previous_restored"] is True
    assert "No space left" in doc["message"] and "was removed" in doc["message"]
    assert not older.with_name("x.partial").exists() and older.is_dir()
    assert w.inst.current() == OLD and w.running_commit() == "a"
    assert w.facts["version"] == 1 and not any("mentis.migrate" in a for a in w.brain_args)
    assert not (w.inst.releases / NEW).exists()     # this update staged it
    assert doc["backup"] is None and doc["backup_kind"] is None


@windows_only
def test_a_backup_the_check_refuses_stops_it_too_and_is_kept(world):
    w = world()
    launcher.start(w.inst, w.inst.state())
    w.brain_fails = ("verify-backup", lambda args: types.SimpleNamespace(
        returncode=1, stdout='{"usable": false}', stderr=""))
    code, doc = w.update(full_backup=True)
    assert code == 3 and doc["reason"] == "aborted" and "not usable" in doc["message"]
    assert w.inst.current() == OLD and w.running_commit() == "a"


@windows_only
def test_a_check_that_says_it_is_no_full_backup_stops_it(world):
    w = world()
    launcher.start(w.inst, w.inst.state())
    w.brain_fails = ("verify-backup", lambda args: types.SimpleNamespace(
        returncode=0, stdout='{"usable": true, "kind": "local-recovery"}', stderr=""))
    code, doc = w.update(full_backup=True)
    assert code == 3 and "is not one" in doc["message"] and w.inst.current() == OLD


@windows_only
def test_a_quick_backup_that_fails_leaves_its_partial_as_it_always_did(world):
    w = world()
    launcher.start(w.inst, w.inst.state())
    w.brain_fails = ("backup", _fills_up(w))
    code, doc = w.update()
    assert code == 3 and doc["reason"] == "aborted" and "was removed" not in doc["message"]
    assert list((pathlib.Path(w.brain).parent / "backups").glob("*/x.partial"))


@pytest.mark.parametrize("where", ["releases", "state", "."])
def test_backups_inside_the_install_are_refused_before_anything(world, where):
    w = world()
    w.inst.write(w.inst.state_file, {**w.inst.state(), "brain": str(w.inst.root / where / "brain")})
    with pytest.raises(launcher.Refused, match="inside this install") as got:
        w.update(full_backup=True)
    assert "without --full-backup" in str(got.value) and "without /FULLBACKUP" in str(got.value)
    assert w.inst.current() == OLD and not (w.inst.state_dir / "update.journal.json").exists()
    assert w.brain_args == []


@pytest.mark.skipif(sys.platform != "win32", reason="a junction is Windows's")
def test_backups_reached_through_a_junction_are_inside_too(world, tmp_path):
    w = world()
    inside = w.inst.root / "state" / "elsewhere"
    inside.mkdir(parents=True)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(tmp_path / "backups"), str(inside)], check=True,
                   capture_output=True)
    try:
        with pytest.raises(launcher.Refused, match="inside this install"):
            w.update(full_backup=True)
    finally:
        os.rmdir(tmp_path / "backups")
    assert w.brain_args == []


@pytest.mark.skipif(sys.platform != "win32", reason="a junction is Windows's")
@pytest.mark.parametrize("target_there", [True, False], ids=["to a folder", "to nothing yet"])
def test_a_junction_at_the_corpus_folder_is_inside_too(world, tmp_path, target_there):
    """Where the backup is really written: `backups` is outside, and `backups\\<corpus id>`
    goes to a release folder. Resolving only `backups` said it was fine."""
    w = world()
    sink = w.inst.root / "releases" / "sink"
    if target_there:
        sink.mkdir()
    (tmp_path / "backups").mkdir()
    corpus = tmp_path / "backups" / "corpus-id"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(corpus), str(sink)], check=True, capture_output=True)
    try:
        with pytest.raises(launcher.Refused, match="inside this install") as got:
            w.update(full_backup=True)
    finally:
        os.rmdir(corpus)
    assert str(corpus) in str(got.value) and "without --full-backup" in str(got.value)
    assert w.inst.current() == OLD and not (w.inst.state_dir / "update.journal.json").exists()
    assert w.brain_args == []


@pytest.mark.parametrize("why", ["it has none", "it cannot be read"])
def test_a_corpus_id_the_brain_cannot_give_refuses_rather_than_passes(world, monkeypatch, why):
    w = world()
    def cannot(brain):
        raise (backup.BackupRefused("no corpus identity") if why == "it has none" else OSError("disk error"))
    monkeypatch.setattr(updater, "_corpus_id_of", cannot)
    with pytest.raises(launcher.Refused, match="cannot be told") as got:
        w.update(full_backup=True)
    assert "without --full-backup" in str(got.value)
    assert w.inst.current() == OLD and w.brain_args == []
    # not asked for, there is nothing to look for
    assert updater.plan(w.at(NEW), w.build_of(NEW), full_backup=False)["ok"]


def test_a_location_that_does_not_exist_yet_is_outside_and_passes(world, tmp_path):
    w = world()
    assert not (tmp_path / "backups").exists()
    assert updater.plan(w.at(NEW), w.build_of(NEW), full_backup=True)["ok"]


def test_the_corpus_id_is_the_one_the_backup_files_under(tmp_path):
    from tests.test_exchange_export import build
    root = tmp_path / "brain"
    build(root)["corpus"].close()
    made = backup.backup(str(root))
    assert pathlib.Path(made["backup"]).parent.name == updater._corpus_id_of(str(root))


def test_a_brain_that_cannot_say_its_corpus_id_is_not_made_up_or_made(tmp_path):
    gone = tmp_path / "gone"
    with pytest.raises(Exception):
        updater._corpus_id_of(str(gone))
    assert not gone.exists()
    empty = tmp_path / "empty"
    empty.mkdir()
    sqlite3.connect(empty / "corpus.db").close()
    with pytest.raises(backup.BackupRefused):
        updater._corpus_id_of(str(empty))


def test_not_asked_for_a_location_inside_the_install_is_as_it_always_was(world):
    w = world()
    st = w.inst.state()
    w.inst.write(w.inst.state_file, {**st, "brain": str(w.inst.root / "brain")})
    p = updater.plan(w.at(NEW), w.build_of(NEW), full_backup=False)
    assert not [x for x in p["problems"] if "inside this install" in x]
    assert not [x for x in updater.plan(w.at(NEW), w.build_of(NEW))["problems"] if "inside this install" in x]


def test_the_plan_says_which_backup_and_about_how_big(world, tmp_path):
    w = world()
    brain = pathlib.Path(w.brain)
    (brain / "artifacts" / "sha256" / "aa").mkdir(parents=True)
    (brain / "artifacts" / "sha256" / "aa" / "aa").write_bytes(b"x" * (3 << 20))
    (brain / "corpus.db").write_bytes(b"x" * (1 << 20))
    (brain / "derived").mkdir()
    (brain / "derived" / "not-carried").write_bytes(b"x" * (9 << 20))
    full = updater.plan(w.at(NEW), w.build_of(NEW), full_backup=True)
    assert full["backup"]["approx_bytes"] == 4 << 20
    assert "Full backup of the Brain first, as asked, about 4 MB" in updater.describe(full)
    assert str(tmp_path / "backups") in updater.describe(full)
    quick = updater.describe(updater.plan(w.at(NEW), w.build_of(NEW), full_backup=False))
    assert "Quick backup of the Brain first" in quick and "does not copy them" in quick
    assert "--full-backup" in quick and "comparable to the Brain's size" in quick
    assert "as you said" not in quick and "declin" not in quick
    unsaid = updater.describe(updater.plan(w.at(NEW), w.build_of(NEW)))
    assert "ull backup" not in unsaid and "back up the Brain" in unsaid


def _arrive_args(**kw):
    return types.SimpleNamespace(**{**dict(root=None, plan=False, backup_question=False, yes=True,
                                           full_backup=False), **kw})


def _arriving_exe(w, tmp_path, monkeypatch):
    here = tmp_path / "incoming" / "app"
    here.mkdir(parents=True)
    build = json.loads((w.inst.releases / NEW / "app/BUILD.json").read_text("utf-8"))
    (here / "BUILD.json").write_text(json.dumps(build), "utf-8")
    monkeypatch.setattr(updater.launcher, "__file__", str(here / "launcher.py"))


def test_the_wizard_asks_only_of_an_update(world, tmp_path, monkeypatch):
    w = world()
    _arriving_exe(w, tmp_path, monkeypatch)
    ask = lambda: updater.arrive(w.inst, _arrive_args(root=w.inst.root, backup_question=True))[1]["message"]  # noqa: E731
    said = ask()
    assert said.startswith("Also take a full backup of the Brain before updating?")
    assert "recommended" not in said.lower()
    assert "may need disk space comparable to the Brain's size, about 1 MB now" in said
    assert str(tmp_path / "backups") in said
    assert "No: only the quick backup" in said and "not the files" in said
    # a first install
    state = w.inst.state_file.read_text("utf-8")
    w.inst.state_file.unlink()
    assert ask() == ""
    w.inst.state_file.write_text(state, "utf-8")
    # the same build over itself
    w.inst.point(NEW, OLD)
    assert ask() == ""
    w.inst.point(OLD, None)
    # an update that did not finish
    updater._write(w.inst.state_dir / "update.journal.json", {"format": 1, "state": "STOPPED"})
    assert ask() == ""
    (w.inst.state_dir / "update.journal.json").unlink()
    # one that would refuse anyway
    w.facts["problems"] = ["no"]
    assert ask() == ""


def test_a_location_only_the_full_backup_cannot_use_is_said_before_go_ahead_and_not_asked_about(
        world, tmp_path, monkeypatch):
    """The update goes ahead with the quick one, so the wizard must neither offer what it
    cannot do nor say the update will refuse."""
    w = world()
    _arriving_exe(w, tmp_path, monkeypatch)
    monkeypatch.setattr(updater, "_corpus_id_of", lambda brain: (_ for _ in ()).throw(OSError("disk error")))
    said = updater.arrive(w.inst, _arrive_args(root=w.inst.root, plan=True))[1]["message"]
    assert "No full backup can be offered: where the full backup would go cannot be told" in said
    assert "This update takes the quick backup" in said
    assert updater.arrive(w.inst, _arrive_args(root=w.inst.root, backup_question=True))[1]["message"] == ""
    assert updater.plan(w.at(NEW), w.build_of(NEW))["ok"]
    # what the wizard then runs, which goes ahead
    _only_the_quick_one(w, *w.update())


def test_the_plan_says_nothing_of_it_when_the_full_backup_can_go_where_it_goes(world, tmp_path, monkeypatch):
    w = world()
    _arriving_exe(w, tmp_path, monkeypatch)
    said = updater.arrive(w.inst, _arrive_args(root=w.inst.root, plan=True))[1]["message"]
    assert "Update Mentis" in said and "No full backup" not in said


def _setup_exe_arrives(w, monkeypatch, *flags):
    """The exe's own `arrive --root <here> --yes $4`, through the real parser, and what it
    hands over run as the new release would run it."""
    handed = []
    monkeypatch.setattr(updater, "_place_arriving", lambda inst, src, build: True)
    monkeypatch.setattr(updater, "_hand_over", lambda inst, name, made, args: (handed.append(args), (0, {}))[1])
    updater.arrive(w.inst, launcher._parser().parse_args(["arrive", "--root", str(w.inst.root), "--yes", *flags]))
    a = launcher._parser().parse_args(handed[0])
    assert a.staged_here
    return updater.transact(w.at(NEW), a, NEW, kind="update", made=a.made)


@windows_only
def test_slash_s_handing_over_through_arrive_takes_the_quick_one(world, tmp_path, monkeypatch):
    w = world()
    _arriving_exe(w, tmp_path, monkeypatch)
    _only_the_quick_one(w, *_setup_exe_arrives(w, monkeypatch))


@windows_only
def test_slash_fullbackup_handing_over_through_arrive_takes_the_full_one(world, tmp_path, monkeypatch):
    w = world()
    _arriving_exe(w, tmp_path, monkeypatch)
    code, doc = _setup_exe_arrives(w, monkeypatch, "--full-backup")
    assert code == 0 and doc["backup_kind"] == "portable" and _backup_calls(w)[0][-1] == "--portable"


def _nsi():
    return (REPO / "tools/installer/mentis.nsi").read_text("utf-8").replace("\r\n", "\n")


def test_slash_s_passes_arrive_nothing_unless_slash_fullbackup_says_so():
    """Everything that sets what `arrive` is told, in the order the exe runs it. /S goes
    straight from the first three to `arrive`."""
    text = _nsi()
    sets = re.findall(r'StrCpy \$4 "([^"]*)"', text)
    assert sets == ["", "--full-backup", "--full-backup"], sets
    silent = text[text.index('StrCpy $4 ""'):text.index("IfSilent arrive")]
    assert '${GetOptions} $R9 "/FULLBACKUP" $R7\n  IfErrors +2\n    StrCpy $4 "--full-backup"' in silent
    assert 'arrive --root "$INSTDIR" --yes $4' in text


def test_the_wizards_no_passes_arrive_nothing_and_is_the_default_button():
    """No jumps past the only line that asks for it; that line is reached by Yes alone."""
    text = _nsi()
    assert ('MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "$3" /SD IDNO IDNO arrive\n'
            '    StrCpy $4 "--full-backup"\n') in text
    assert text.index("Go ahead?") < text.index("--backup-question") < text.index('--yes $4')
    assert text.index("IfSilent arrive") < text.index("--backup-question")
    assert "NOFULLBACKUP" not in text and "no-full-backup" not in text


# -- a real older release on the far side of the hand-over --------------------------
#
# The tests above parse and run both sides of a hand-over with this commit's code, so they
# cannot see what an older release does with it. Here the far side is that commit's own
# code, from `git archive`: its launcher as a real process, its updater, its `mentis.brain
# backup` on a real Brain. This side is this commit's, unstubbed from the unpack on. Stood
# in: the exe the payload comes out of, the embeddable Python (the host's, by the release's
# own `_pth`), and the processes its manifest starts.

LAST_ON_MAIN = "1c55e9f"
#: never released: each took a full backup unless declined. (commit, holds unnamed files)
DEVELOPMENT_ONLY = (("4ba5497", False), ("724c52a", False), ("6163dae", True))


def _runtime_for_a_release(rt: pathlib.Path) -> None:
    rt.mkdir(parents=True)
    base = pathlib.Path(sys.base_prefix)
    for name in ("python.exe", "python3.dll", f"python{sys.version_info[0]}{sys.version_info[1]}.dll",
                 "vcruntime140.dll", "vcruntime140_1.dll"):
        shutil.copy2(base / name, rt / name)
    lines = [base / "Lib", base / "DLLs", base / "Lib/site-packages", pathlib.Path(sys.prefix) / "Lib/site-packages"]
    (rt / f"python{sys.version_info[0]}{sys.version_info[1]}._pth").write_text(
        "\n".join([*map(str, lines), r"..\app", "import site"]) + "\n", "utf-8")


@pytest.fixture(scope="module")
def stage_of(tmp_path_factory):
    """That commit, as the stage of a release: its payload, its own BUILD.json and FILES.json."""
    made = {}

    def make(commit):
        if commit in made:
            return made[commit]
        def git(*args, **kw):
            return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, **kw)
        if git("cat-file", "-e", f"{commit}^{{commit}}").returncode:
            pytest.skip(f"{commit} is not in this clone")
        here = tmp_path_factory.mktemp(f"older-{commit}")
        src, stage = here / "src", here / "stage"
        src.mkdir()
        tar = here / "src.tar"
        got = git("archive", "-o", str(tar), commit, "mentis", "tools/installer", "tools/mcp_bridge.py",
                  "tools/ladder_vocabulary.py")
        assert got.returncode == 0, got.stderr
        shutil.unpack_archive(tar, src, filter="data")
        man = json.loads((src / "tools/installer/manifest.json").read_text("utf-8"))
        man["payload"] = [row for row in man["payload"] if "built_by" not in row]
        builder.copy_payload(man, src, stage)
        World.make_release(types.SimpleNamespace(root=here / "fake", log=here / "order.log"),
                           "0.0.0+fake", "f" * 40, 1, 1)
        shutil.copy2(here / "fake/releases/0.0.0+fake/app/manifest.json", stage / "app/manifest.json")
        _runtime_for_a_release(stage / "runtime")
        full = git("rev-parse", commit, text=True).stdout.strip()
        builder.stamp(stage, {"version": "0.1.0", "commit": full})
        made[commit] = stage
        return stage
    return make


@pytest.fixture
def beside(tmp_path, monkeypatch, capsys):
    """An install on this commit's updater, serving nothing yet, with a real Brain holding a
    stored file the record names and one it does not. `.update(...)` is `mentis.cmd update`."""
    from tests.test_exchange_export import build
    from mentis.readonly import unlock
    from mentis.spine import held
    worlds = []

    def make(stage):
        facts = json.loads((stage / "app/BUILD.json").read_text("utf-8"))
        root, brain = tmp_path / "Mentis Test", tmp_path / "brain"
        # A BRAIN THE STAGED (OLDER) COMMIT CAN OPEN: at the schema it reads.
        # Since 0002-erasure (min_reader 2) a Brain made at this commit's
        # target is one no earlier release may open writable.
        from mentis.spine import migrations as _migrations
        every = _migrations.MIGRATIONS
        if facts.get("schema_target", 1) < _migrations.target():
            _migrations.MIGRATIONS = every[:facts["schema_target"]]
        try:
            built = build(brain)
            built["corpus"].close()
        finally:
            _migrations.MIGRATIONS = every
        (brain / "mentis-corpus.json").write_text(json.dumps({"corpus_version": 1, "corpus_id": "fixture"}), "utf-8")
        unnamed, _ = held.put(str(brain), b"attached to a draft and never sent")
        w = types.SimpleNamespace(root=root, log=stage.parent / "order.log", brain=brain, named=built["digest"],
                                  unnamed=unnamed, name=updater.name_of(facts), backups=tmp_path / "backups")
        World.make_release(w, OLD, "a" * 40, facts["schema_target"], facts["min_reader_after"])
        w.inst = launcher.Install(root, OLD)
        w.inst.python = HOST_PYTHON
        w.inst.point(OLD, None)
        w.inst.write(w.inst.state_file, {"brain": str(brain), "owner": "@o", "port": free_port_pair(),
                                         "workspace": str(tmp_path / "w"), "mars": "m"})
        monkeypatch.setattr(updater, "_unpack", fake_unpack(stage))

        def update(*flags):
            capsys.readouterr()
            package = _exists(tmp_path)
            code = updater.command(w.inst, launcher._parser().parse_args(["update", str(package), *flags]))
            said = capsys.readouterr()
            return code, json.loads(said.out), said.err
        w.update = update
        worlds.append(w)
        return w
    yield make
    for w in worlds:
        there = launcher.Install(w.root, w.inst.current())
        there.python = HOST_PYTHON
        launcher.stop(there)
        for home in (w.root / "releases").iterdir():
            unlock(home)


def _the_one_backup(w) -> pathlib.Path:
    found = [p.parent for p in w.backups.rglob("BACKUP.json")]
    assert len(found) == 1, found
    return found[0]


def _files_of(*folders) -> dict:
    import hashlib
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for top in folders for p in sorted(top.rglob("*")) if p.is_file()}


@windows_only
@pytest.mark.parametrize("flags", [("--yes",), ()], ids=["yes", "a-person-says-yes"])
def test_an_unflagged_hand_over_to_the_last_build_on_main_takes_its_quick_backup(
        stage_of, beside, monkeypatch, flags):
    from mentis.spine import held
    stage = stage_of(LAST_ON_MAIN)
    assert "full-backup" not in (stage / "app/launcher.py").read_text("utf-8")
    w = beside(stage)
    monkeypatch.setattr(updater, "_confirmed", lambda a, question="Proceed?": True)
    code, doc, _ = w.update(*flags)
    made = _the_one_backup(w)
    manifest_of = json.loads((made / "BACKUP.json").read_text("utf-8"))
    assert manifest_of["kind"] == "local-recovery" and not made.name.endswith("-portable")
    assert not held.path(made, w.named).exists() and not held.path(made, w.unnamed).exists()
    assert code == 0 and doc["outcome"] == "ok"
    assert "backup" not in doc and "full_backup" not in doc, "that commit's answer has neither"
    archived = json.loads(next((w.inst.state_dir / "updates").glob("upd-*.json")).read_text("utf-8"))
    assert archived["backup"] == str(made) and "full_backup" not in archived
    assert (w.inst.current(), w.inst.previous()) == (w.name, OLD)


@windows_only
@pytest.mark.parametrize("flags", [("--yes",), ()], ids=["yes", "plan-first"])
def test_the_full_backup_asked_of_the_last_build_on_main_is_refused_with_nothing_changed(
        stage_of, beside, flags):
    w = beside(stage_of(LAST_ON_MAIN))
    launcher.start(w.inst, w.inst.state())
    pids = [e["pid"] for e in w.inst.running()]
    before = _files_of(w.brain, w.inst.state_dir)
    code, doc, err = w.update(*flags, "--full-backup")
    assert code == 2 and doc["outcome"] == "refused"
    assert "unrecognized arguments: --full-backup" in err
    assert sorted(d.name for d in w.inst.releases.iterdir()) == [OLD]
    assert (w.inst.current(), w.inst.previous()) == (OLD, None)
    after = _files_of(w.brain, w.inst.state_dir)
    left = {pathlib.Path(p).relative_to(w.inst.state_dir).as_posix() for p in set(after) - set(before)}
    assert left == {"logs/update.log", "update.lock"}, "what any update that gets this far leaves"
    assert {p: after[p] for p in before} == before
    assert not w.backups.exists()
    assert [e["pid"] for e in w.inst.running()] == pids and updater._serving_name(w.inst) == OLD
    assert doc["message"] == (
        "the update ended with exit 2 and gave no result" if flags else
        f"{w.name} did not answer (exit 2). Nothing was changed.")
    assert doc["reason"] == ("crashed" if flags else "refused")


@windows_only
def test_the_last_build_on_mains_own_update_has_no_full_backup_flag(stage_of):
    stage = stage_of(LAST_ON_MAIN)
    got = subprocess.run([str(stage / "runtime/python.exe"), "-I", "-X", "utf8", str(stage / "app/launcher.py"),
                          "update", "x.exe", "--full-backup"], capture_output=True, text=True, cwd=stage.parent)
    assert got.returncode == 2 and "unrecognized arguments: --full-backup" in got.stderr


@windows_only
@pytest.mark.parametrize("commit,holds_unnamed", DEVELOPMENT_ONLY)
def test_an_unflagged_hand_over_to_a_development_commit_takes_a_full_backup(
        stage_of, beside, commit, holds_unnamed):
    """What docs/windows-installer.md says of them; and that the test above would see it."""
    from mentis.spine import held
    w = beside(stage_of(commit))
    code, doc, _ = w.update("--yes")
    made = _the_one_backup(w)
    assert json.loads((made / "BACKUP.json").read_text("utf-8"))["kind"] == "portable"
    assert made.name.endswith("-portable") and code == 0
    assert held.path(made, w.named).exists()
    assert held.path(made, w.unnamed).exists() is holds_unnamed


# -- a Brain is never restored by anything here -------------------------------------

RESTORING = ("restore", "--resume", "discard-quarantine")


def _nothing_restored(w):
    assert not [a for a in w.brain_args if set(a) & set(RESTORING)], w.brain_args
    assert not list(pathlib.Path(w.brain).parent.glob("*.quarantine-*"))


@windows_only
@pytest.mark.parametrize("how", ["switched back", "needs attention", "killed", "rollback"])
def test_a_failed_update_restores_no_brain_even_with_a_full_backup_there(world, how):
    breaking = how == "needs attention"
    w = world(new_target=2, new_min_reader=2 if breaking else 1, new_unhealthy=how != "rollback" and how != "killed")
    launcher.start(w.inst, w.inst.state())
    if how == "killed":
        w.kill_label = "state:HEALTHY"
        with pytest.raises(Killed):
            w.update(full_backup=True)
        (w.inst.releases / NEW / "app/manifest.json").write_text("{}", "utf-8")
        code, doc = updater.recover(w.at(OLD))
    elif how == "rollback":
        assert w.update(full_backup=True)[0] == 0
        code, doc = w.rollback(NEW)
    else:
        code, doc = w.update(full_backup=True)
    assert doc["backup_kind"] in ("portable", "local-recovery") and doc["backup"], doc
    assert [a for a in w.brain_args if "--portable" in a]
    assert w.facts["version"] == 2     # the migration stands: a restore would have undone it
    _nothing_restored(w)
    if how == "needs attention":
        assert code == 4
        said = json.loads((w.inst.state_dir / "needs-attention.json").read_text("utf-8"))
        assert said["backup"] == doc["backup"] and "restore-plan" in said["restore_plan_command"]
        assert "Nothing was restored" in said["what_to_do"][0]
        # and still not when it is asked again
        assert updater.recover(w.at(NEW))[0] == 4
        _nothing_restored(w)


def test_the_updater_has_no_way_to_restore_a_brain():
    """`restore-plan` is said to a person, in words. It is never a command this runs."""
    import ast
    tree = ast.parse((REPO / "tools/installer/updater.py").read_text("utf-8"))
    literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "restore" not in literals and "restore-plan" not in literals
    assert "discard-quarantine" not in literals
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "restore"]


def test_with_nothing_unfinished_a_damaged_updater_is_named_not_met(world, monkeypatch, capsys):
    w = world()
    (w.inst.home / "app/manifest.json").write_text("{}", "utf-8")
    monkeypatch.setitem(sys.modules, "updater", None)      # what importing a damaged one does
    _refused_and_nothing_started(w, capsys, ["start"], "app/manifest.json")


def test_with_an_update_unfinished_a_damaged_updater_is_named_not_met(world, monkeypatch, capsys):
    w = world()
    updater._write(w.inst.state_dir / "update.journal.json", {"format": 1, "state": "x"})
    (w.inst.home / "app/manifest.json").write_text("{}", "utf-8")
    monkeypatch.setitem(sys.modules, "updater", None)
    _refused_and_nothing_started(w, capsys, ["start"], "app/manifest.json")


def test_an_update_failing_for_another_reason_is_not_called_damage(world, monkeypatch):
    w = world()
    updater._write(w.inst.state_dir / "update.journal.json", {"format": 1, "state": "x"})
    def boom(inst):
        raise KeyError("a defect in the recovery")
    monkeypatch.setattr(updater, "before_start", boom)
    with pytest.raises(KeyError):
        launcher.main(["start"], w.inst)


@windows_only
def test_only_an_updates_own_restart_goes_past_the_guard(world, monkeypatch):
    """`_start` is the one caller of `--in-update`: undoing and switching back hash first,
    and decide what a damaged release means there, so their outcomes stay their own."""
    w = world()
    (w.inst.home / "app/z.txt").write_text("not in the list", "utf-8")
    (w.inst.home / "app/FILES.json").write_text(json.dumps({"app/z.txt": "0" * 64}), "utf-8")
    launched = []
    monkeypatch.setattr(updater, "_launch", lambda inst, name, *args: (
        launched.append((name, args)), types.SimpleNamespace(returncode=0, stdout="", stderr=""))[1])
    updater._start(w.inst, OLD)
    assert launched == [(OLD, ("start", "--in-update"))]
    assert launcher.main(["start", "--in-update"], w.inst) == 0
    assert w.running_commit() == "a"
    source = (REPO / "tools/installer/updater.py").read_text("utf-8")
    assert source.count('"--in-update"') == 1


def test_a_copy_that_cannot_be_made_refuses_with_nothing_replaced(world, tmp_path, monkeypatch):
    w = world()
    name, run = route_over_itself(w, tmp_path, monkeypatch)
    home = _damage_it(w, name)

    def full(src, dst):
        pathlib.Path(dst).mkdir()
        raise OSError(28, "no space left")
    monkeypatch.setattr(updater.shutil, "copytree", full)
    with pytest.raises(launcher.Refused, match="could not be copied aside.*Nothing was replaced"):
        run()
    assert (home / "app/manifest.json").read_text("utf-8") == "damaged"
    assert not list(w.inst.releases.glob(name + ".damaged-*"))


def test_a_repair_removes_what_the_build_did_not_put_there_and_the_copy_keeps_it(world, tmp_path, monkeypatch):
    w = world()
    name, run = route_over_itself(w, tmp_path, monkeypatch)
    home = _damage_it(w, name)
    (home / "app/stray").mkdir()
    (home / "app/stray/left.py").write_text("x", "utf-8")
    run()
    assert not (home / "app/stray").exists()
    assert (list(w.inst.releases.glob(name + ".damaged-*"))[0] / "app/stray/left.py").is_file()


def test_two_repairs_in_one_second_keep_two_copies(world, tmp_path, monkeypatch):
    w = world()
    name, run = route_over_itself(w, tmp_path, monkeypatch)
    monkeypatch.setattr(updater.time, "strftime", lambda *a: "NOW")
    for _ in range(2):
        _damage_it(w, name)
        run()
    assert len(list(w.inst.releases.glob(name + ".damaged-*"))) == 2


def test_a_whole_release_a_kill_left_unlocked_is_locked_again(world, tmp_path, monkeypatch):
    from mentis import readonly
    w = world()
    locked = []
    monkeypatch.setattr(updater, "_lock", locked.append)
    monkeypatch.setattr(readonly, "is_locked", lambda home: False)
    home = w.inst.releases / NEW
    assert updater.place(w.inst, home, w.build_of(NEW), move=False) is False
    assert locked == [home]
    monkeypatch.setattr(readonly, "is_locked", lambda home: True)
    assert updater.place(w.inst, home, w.build_of(NEW), move=False) is False
    assert locked == [home]


# what the proof may call proven -----------------------------------------------------

@pytest.fixture
def proof(tmp_path):
    pytest.importorskip("winreg")
    import prove_windows_installer as prover
    return prover, prover.Proof(tmp_path / "x.exe", tmp_path / "root", 19999, None, tmp_path / "evidence")


def test_a_changed_brain_fails_the_step_and_the_proof(proof):
    prover, p = proof
    p.brain.mkdir(parents=True)
    p.workspace.mkdir()
    (p.brain / "corpus.db").write_bytes(b"as it was")
    import hashlib
    p.brain_hash = hashlib.sha256(b"as it was").hexdigest()
    assert p.step("the Brain and workspace stay", p.do_brain_kept) is True
    assert p.verdict() == {"ok": True, "failed": [], "not_run": []}
    (p.brain / "corpus.db").write_bytes(b"changed on purpose")
    assert p.step("the Brain and workspace stay", p.do_brain_kept) is False
    assert "corpus.db changed" in p.steps[-1]["detail"]
    assert p.verdict() == {"ok": False, "failed": ["the Brain and workspace stay"], "not_run": []}


def test_no_edge_is_not_run_and_nothing_can_read_the_proof_as_proven(proof, monkeypatch):
    prover, p = proof
    monkeypatch.setattr(prover, "EDGE", ())
    assert p.step("a step that passed", lambda: "fine") is True
    assert p.step("Fluid draws in a real browser", p.do_browser) is True    # the rest still run
    entry = p.steps[-1]
    assert entry["ok"] is False and entry["not_run"] is True and "no Edge" in entry["detail"]
    assert p.verdict() == {"ok": False, "failed": [], "not_run": ["Fluid draws in a real browser"]}


def test_no_release_removed_means_every_release_the_proof_kept(proof):
    prover, p = proof
    import hashlib
    p.old_name, p.new_name = "0.1.0+" + "a" * 12, "0.1.0+" + "b" * 12
    p.aside_seen = {p.old_name + ".damaged-1"}
    variants = ["0.1.0+" + hashlib.sha1(v.encode()).hexdigest()[:12] for v in prover.KEPT_VARIANTS]
    all_of_them = [p.old_name, p.new_name, p.old_name + ".damaged-1", *variants]
    for name in all_of_them:
        (p.install / "releases" / name).mkdir(parents=True)
    assert p.do_releases_kept()["releases"] == sorted(all_of_them)
    for gone in (variants[0], p.new_name, p.old_name + ".damaged-1"):
        (p.install / "releases" / gone).rmdir()
        with pytest.raises(prover.Failed, match="gone"):
            p.do_releases_kept()
        (p.install / "releases" / gone).mkdir()


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


@pytest.mark.parametrize("answer,yes", [("y\n", True), ("\n", False), ("", False)])
def test_asking_leaves_stdout_to_the_one_answer(monkeypatch, capsys, answer, yes):
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO(answer))
    monkeypatch.setattr(launcher, "a_person_can_answer", lambda: True)
    assert updater._confirmed(types.SimpleNamespace(yes=False)) is yes
    said = capsys.readouterr()
    assert said.out == "" and "[y/N]" in said.err


@windows_only
def test_nul_is_nobody_at_a_console_and_a_program_is_not_asked():
    """Windows says NUL is a terminal: `start` failing under a program got `Press Enter`,
    then EOFError's traceback where the words of the failure belong."""
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import launcher; "
            "print(sys.stdin.isatty(), launcher.a_person_can_answer())")
    got = subprocess.run([sys.executable, "-c", code, str(REPO / "tools/installer")], stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=60)
    assert got.stdout.split() == ["True", "False"], got.stderr


@windows_only
@pytest.mark.parametrize("stdout", ["", "not json"], ids=["nothing", "not an answer"])
def test_a_resume_that_crashes_reports_no_success_and_a_start_still_refuses(world, monkeypatch, capsys, stdout):
    """`_resume`'s `crashed` answer: the release it hands the resume to dies with no result.
    Here `current` is damaged, so the whole old release is who is handed it."""
    w = world()
    _killed_then_damaged(w, "state:SWITCHED")
    assert w.inst.current() == NEW
    monkeypatch.setattr(updater, "_launch", lambda inst, name, *args: types.SimpleNamespace(
        returncode=70, stdout=stdout, stderr="it died\n"))
    code, doc = updater._resume(w.at(NEW))
    assert code == 3 and doc["reason"] == "crashed" and "exit 70" in doc["message"]
    # through the command that reports it, which says the same
    capsys.readouterr()
    assert updater.command(w.at(NEW), w.a(resume=True, staged_here=False)) == 3
    said = json.loads(capsys.readouterr().out)
    assert said["outcome"] == "failed" and said["reason"] == "crashed"
    # nothing says it went well: the journal stands and nothing was archived
    assert (w.inst.state_dir / "update.journal.json").exists()
    assert not list((w.inst.state_dir / "updates").glob("upd-*.json"))
    assert w.inst.current() == NEW
    # and the next start goes on past the crash to the launcher, which refuses the damage
    monkeypatch.setattr(sys, "argv", ["launcher.py", "start"])
    capsys.readouterr()
    assert launcher.main(["start"], w.at(NEW)) == 1
    assert "app/manifest.json" in capsys.readouterr().err
    assert w.at(NEW).running() == [] and w.at(OLD).running() == []
    assert (w.inst.state_dir / "update.journal.json").exists()


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
