"""Prove a built installer on this PC: real install, setup, open, restart, update,
rollback, every way an update can fail, a kill at every step, uninstall.

    python tools/prove_windows_installer.py <Mentis-Setup-...exe> --root DIR --port N
        [--commit SHA] [--new <newer exe> --new-commit SHA] [--evidence DIR] [--cache DIR]

The exe's `work-<commit12>\\` from the build must still be beside it: the broken and
migrating packages are that stage changed and packed again, under --root\\variants.
Without --new, the newer build is this one stamped with another commit.

Everything goes under `--root`, which must not exist yet: the install (in a folder
with a space in its name), a new Brain and a workspace. The installed commands run
with what a machine without Python, Node or Git gives them: a PATH of Windows alone,
and PYTHONHOME and PYTHONPATH set to nonsense they must ignore. That is not a clean
machine; docs/windows-installer.md says what only a clean machine can prove.

It refuses port 8760 and refuses to run where this user already has this installer's
uninstall entry, so it cannot replace an install or a server somebody uses. It touches
only --root, this installer's uninstall entry and its Start Menu folder, and removes
those two again. Mentis's Brain locks and the disposable Brain do the rest.

Prints one JSON object, every step with its result. Exit 0 all passed, 1 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import winreg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_windows_installer as builder  # noqa: E402
from build_windows_installer import scrubbed_env  # noqa: E402

KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MentisServer"
EDGE = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")


#: the second release's own migrations, for the proof: real ones, run by the real runner
MIGRATION_ADDITIVE = """
_PROOF_A = ("CREATE TABLE IF NOT EXISTS proof_additive (x INTEGER)",)
def _proof_a(ctx):
    ctx.execute(_PROOF_A[0])
PROOF_A = Migration(id="0002-proof-additive", from_version=1, to_version=2, kind="additive",
                    min_reader=1, statements=_PROOF_A, procedure="a table nobody reads",
                    apply=_proof_a)
"""
MIGRATION_BREAKING = """
_PROOF_B = ("CREATE TABLE IF NOT EXISTS proof_breaking (x INTEGER)",)
def _proof_b(ctx):
    ctx.execute(_PROOF_B[0])
PROOF_B = Migration(id="0003-proof-breaking", from_version=2, to_version=3, kind="breaking",
                    min_reader=3, statements=_PROOF_B, procedure="raises min_reader",
                    apply=_proof_b, requires_applied=("0002-proof-additive",))
"""
MIGRATION_BREAKING_2 = """
_PROOF_C = ("CREATE TABLE IF NOT EXISTS proof_breaking_2 (x INTEGER)",)
def _proof_c(ctx):
    ctx.execute(_PROOF_C[0])
PROOF_C = Migration(id="0004-proof-breaking", from_version=3, to_version=4, kind="breaking",
                    min_reader=4, statements=_PROOF_C, procedure="raises min_reader",
                    apply=_proof_c, requires_applied=("0002-proof-additive",))
"""
LIST_LINE = "MIGRATIONS: tuple[Migration, ...] = (ADOPT,)"

#: where a kill lands, and which release must be running afterwards
KILLS = (("stage:unpacked", "base"), ("stage:placed", "base"),
         ("state:APPROVED", "base"), ("state:STOPPED", "base"), ("state:BACKED_UP", "base"),
         ("before:C1", "base"), ("after:C1", "base"), ("state:MIGRATED", "target"),
         ("before:C2", "target"), ("after:C2", "target"), ("state:SWITCHED", "target"),
         ("started", "target"), ("state:HEALTHY", "target"), ("state:COMMITTED", "target"))


class Failed(Exception):
    pass


def uninstall_entry() -> dict | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            return {n: winreg.QueryValueEx(k, n)[0] for n in
                    ("InstallLocation", "DisplayVersion", "UninstallString")}
    except FileNotFoundError:
        return None


def http(url: str, timeout: float = 15.0):
    req = urllib.request.Request(url, headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(), r.headers.get("Content-Type", "")


def listener(port: int):
    import psutil
    for c in psutil.net_connections(kind="tcp"):
        if c.status == psutil.CONN_LISTEN and c.laddr.port == port:
            return c.pid
    return None


class Proof:
    def __init__(self, installer, root, port, commit, evidence, new=None, new_commit=None, cache=None):
        self.installer = pathlib.Path(installer).resolve()
        self.new, self.new_commit = (pathlib.Path(new).resolve() if new else None), new_commit
        self.cache = pathlib.Path(cache) if cache else pathlib.Path(os.environ.get("TEMP", ".")) / "mentis-installer-cache"
        self.variants: dict = {}
        self.root = pathlib.Path(root).resolve()
        self.port, self.commit = port, commit
        self.evidence = pathlib.Path(evidence).resolve() if evidence else self.root / "evidence"
        self.install = self.root / "Mentis Proof"
        self.brain = self.root / "brain"
        self.workspace = self.root / "workspace"
        self.url = f"http://127.0.0.1:{port}"
        self.steps: list = []
        env = scrubbed_env()
        # nothing the server writes may land in the real profile's AppData
        env.update(PYTHONHOME=r"C:\nope", PYTHONPATH=r"C:\nope",
                   LOCALAPPDATA=str(self.root / "localappdata"),
                   APPDATA=str(self.root / "appdata"))
        self.env = env

    def step(self, name, fn) -> bool:
        began = time.monotonic()
        try:
            detail, ok = fn(), True
        except Exception as exc:                            # noqa: BLE001
            detail, ok = f"{type(exc).__name__}: {exc}", False
        self.steps.append({"step": name, "ok": ok, "seconds": round(time.monotonic() - began, 1),
                           "detail": detail})
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {str(detail)[:300]}", file=sys.stderr, flush=True)
        return ok

    def mentis(self, *args, timeout=240) -> dict:
        r = subprocess.run([str(self.install / "mentis.cmd"), *args], env=self.env, text=True,
                           encoding="utf-8", errors="replace", capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, cwd=self.root)
        if r.returncode:
            raise Failed(f"mentis {args[0]} exited {r.returncode}: {(r.stderr or r.stdout)[-1500:]}")
        return json.loads(r.stdout)

    def ask(self, *args, env=None, timeout=900) -> tuple:
        """(exit, its JSON or None, its stderr), for what is meant to refuse."""
        r = subprocess.run([str(self.install / "mentis.cmd"), *args], env={**self.env, **(env or {})}, text=True,
                           encoding="utf-8", errors="replace", capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, cwd=self.root)
        try:
            doc = json.loads(r.stdout)
        except ValueError:
            doc = None
        return r.returncode, doc, r.stderr

    def named(self, which: str) -> str | None:
        try:
            return (self.install / "state" / which).read_text("utf-8").strip() or None
        except FileNotFoundError:
            return None

    def release_dir(self) -> pathlib.Path:
        return self.install / "releases" / self.named("current")

    def python(self, *args, timeout=60) -> str:
        r = subprocess.run([str(self.release_dir() / "runtime" / "python.exe"), "-I", "-X", "utf8", *args],
                           env=self.env, text=True, encoding="utf-8", errors="replace",
                           capture_output=True, timeout=timeout, cwd=self.root)
        if r.returncode:
            raise Failed(r.stderr[-1500:])
        return r.stdout.strip()

    # -- the steps ------------------------------------------------------------------

    def do_install(self):
        r = subprocess.run(f'"{self.installer}" /S /D={self.install}', env=self.env, timeout=300)
        if r.returncode:
            raise Failed(f"the installer exited {r.returncode}")
        entry = uninstall_entry()
        if not entry or os.path.normcase(entry["InstallLocation"]) != os.path.normcase(str(self.install)):
            raise Failed(f"uninstall entry is {entry}")
        got = self.mentis("verify")
        return {"uninstall_entry": entry, "files_verified": got["files"]}

    def do_no_tools(self):
        where = []
        for tool in ("python", "node", "git", "npm"):
            r = subprocess.run(["where.exe", tool], env=self.env, capture_output=True, text=True)
            if r.returncode == 0:
                where.append(r.stdout.strip())
        if where:
            raise Failed(f"found on the scrubbed PATH: {where}")
        return "python, node, git, npm are not on the PATH the install runs with"

    def do_setup(self):
        got = self.mentis("setup", "--brain", str(self.brain), "--owner", "@proof",
                          "--port", str(self.port), "--workspace", str(self.workspace),
                          "--no-browser")
        if not got.get("created") or got.get("started") != ["server"]:
            raise Failed(f"setup said {got}")
        return got

    def do_server(self):
        info = json.loads(http(self.url + "/api/server")[1])
        if os.path.normcase(info["corpus"]) != os.path.normcase(str(self.brain)):
            raise Failed(f"it serves {info['corpus']}")
        if self.commit and (info.get("release") or {}).get("commit") != self.commit:
            raise Failed(f"it runs {info.get('release')}, not {self.commit}")
        if self.commit and info["code"]["commit"] != self.commit:
            raise Failed(f"code.commit is {info['code']['commit']}")
        if not str(info["code"]["root"]).startswith(str(self.install)):
            raise Failed(f"it runs from {info['code']['root']}")
        return {"release": info["release"], "python": info["process"]["python"],
                "corpus_id": info["corpus_id"]}

    def do_brain(self):
        body = http(self.url + "/fluid/api/topics")[1].decode("utf-8", "replace")
        names = re.findall(r'"name":\s*"([^"]+)"', body)
        log = (self.install / "state" / "logs" / "server.log").read_text("utf-8", "replace")
        if "Mentis on http://127.0.0.1" not in log:
            raise Failed(f"the server's log does not say it started: {log[:400]!r}")
        if "no Mentis baseline" in log or "intake does not resolve" in log:
            raise Failed("the server says the Brain has no baseline or intake")
        if not names:
            raise Failed(f"no topics from the welcome tour: {body[:300]}")
        return {"topics": names[:8], "log": log.splitlines()[:3]}

    def do_fluid_files(self):
        got = []
        for path in ("/", "/fluid"):
            _, html, ctype = http(self.url + path)
            if "html" not in ctype or b"Fluid is not built" in html:
                raise Failed(f"{path}: {ctype} {html[:200]}")
        html = http(self.url + "/")[1].decode("utf-8")
        assets = re.findall(r'(?:src|href)="(/[^"]+)"', html)
        if not any(a.endswith(".js") for a in assets):
            raise Failed(f"index.html names no script: {html[:300]}")
        for asset in assets:
            status, body, _ = http(self.url + asset)
            got.append((asset, status, len(body)))
            if status != 200 or not body:
                raise Failed(f"{asset}: {status}")
        return got

    def do_browser(self):
        edge = next((e for e in EDGE if os.path.isfile(e)), None)
        if not edge:
            return "skipped: no Edge on this machine"
        self.evidence.mkdir(parents=True, exist_ok=True)
        shot = self.evidence / "fluid.png"
        base = [edge, "--headless=new", "--disable-gpu", f"--user-data-dir={self.root / 'edge'}",
                "--no-first-run", "--window-size=1400,900", "--virtual-time-budget=20000"]
        dom = subprocess.run([*base, "--dump-dom", self.url + "/"], capture_output=True, timeout=120,
                             encoding="utf-8", errors="replace")
        subprocess.run([*base, f"--screenshot={shot}", self.url + "/"], capture_output=True, timeout=120)
        out = dom.stdout or ""
        (self.evidence / "fluid.dom.html").write_text(out, "utf-8")
        visible = re.sub(r"<(script|style)\b.*?</\1>|<[^>]+>", " ", out, flags=re.S)
        words = len(visible.split())
        if words < 5:
            raise Failed(f"Fluid drew nothing in a browser: {out[:400]}")
        return {"visible_words": words, "text": " ".join(visible.split())[:160], "screenshot": str(shot)}

    def do_render_check(self):
        code = ("from mentis.conversation import render_check as r; import json;"
                "g=r.check('# x'); print(json.dumps([g.get('checked'), str(r.BUNDLE)]))")
        checked, bundle = json.loads(self.python("-B", "-c", code))
        if checked is not True or not bundle.startswith(str(self.install)):
            raise Failed(f"checked={checked} bundle={bundle}")
        return bundle

    def do_bridge(self):
        p = subprocess.Popen([str(self.release_dir() / "runtime" / "python.exe"), "-I", "-X", "utf8",
                              str(self.release_dir() / "app" / "tools" / "mcp_bridge.py"),
                              "--session", "claude", "--server", self.url],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env=self.env, text=True, encoding="utf-8", cwd=self.root)
        answers: list = []

        def reader():
            for line in p.stdout:
                answers.append(json.loads(line))
        threading.Thread(target=reader, daemon=True).start()
        try:
            for i, method in enumerate(("initialize", "tools/list")):
                p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i + 1, "method": method,
                                          "params": {}}) + "\n")
                p.stdin.flush()
            end = time.monotonic() + 60
            while len(answers) < 2 and time.monotonic() < end and p.poll() is None:
                time.sleep(0.2)
        finally:
            p.kill()
            err = p.communicate()[1]
        if len(answers) < 2:
            raise Failed(f"the bridge answered {answers}; stderr: {err[-800:]}")
        tools = answers[1]["result"]["tools"]
        if not tools:
            raise Failed("the bridge offers no tools")
        return {"tools_offered": len(tools), "stderr": err.strip().splitlines()[0][:160]}

    def do_stop(self):
        got = self.mentis("stop")
        if got["stopped"].get("server") != "clean":
            raise Failed(f"stop said {got}")
        if listener(self.port) is not None:
            raise Failed(f"port {self.port} is still held")
        log = (self.install / "state" / "logs" / "server.log").read_text("utf-8", "replace")
        if "Mentis stopped" not in log:
            raise Failed(f"the server went without its own clean stop: {log[-400:]!r}")
        if (self.brain / ".mentis.serve.json").exists():
            raise Failed("the server left its claim on the Brain")
        db = f"file:{(self.brain / 'corpus.db').as_posix()}?mode=ro"
        with sqlite3.connect(db, uri=True) as c:
            check = c.execute("PRAGMA integrity_check").fetchone()[0]
        c.close()
        if check != "ok":
            raise Failed(f"integrity_check: {check}")
        return {**got, "integrity_check": check, "wal_left": (self.brain / "corpus.db-wal").exists()}

    def do_attach_restart(self):
        before = hashlib.sha256((self.brain / "corpus.db").read_bytes()).hexdigest()
        got = self.mentis("setup", "--brain", str(self.brain), "--owner", "@proof", "--attach",
                          "--no-browser")
        if got.get("created") is not False or got.get("started") != ["server"]:
            raise Failed(f"attach said {got}")
        http(self.url + "/api/server")
        self.mentis("open", "--no-browser")
        status = self.mentis("status")
        if not all(p["alive"] for p in status["processes"]):
            raise Failed(f"status said {status}")
        self.mentis("stop")
        return {"attach": got, "corpus_before_attach": before[:16]}

    def do_install_again(self):
        """The same folder, with the server running: stopped, code replaced, setup kept."""
        self.mentis("start")
        r = subprocess.run(f'"{self.installer}" /S /D={self.install}', env=self.env, timeout=300)
        if r.returncode:
            raise Failed(f"the installer exited {r.returncode}")
        if listener(self.port) is not None:
            raise Failed("the server is still running on the code being replaced")
        files = self.mentis("verify")["files"]
        got = self.mentis("start")
        if got.get("started") != ["server"]:
            raise Failed(f"start said {got}")
        http(self.url + "/api/server")
        self.mentis("stop")
        return {"files_verified": files, "setup_kept": self.mentis("status")["setup"]["brain"]}

    def _unlock(self, home: pathlib.Path) -> None:
        self.python("-c", "import sys; from mentis import readonly; readonly.unlock(sys.argv[1])", str(home))

    def do_install_over_a_damaged_release(self):
        """The setup exe repairs its own release, and the damaged copy is kept."""
        home = self.release_dir()
        self._unlock(home)
        (home / "app" / "launcher.py").write_text("# damaged\n", "utf-8")
        r = subprocess.run(f'"{self.installer}" /S /D={self.install}', env=self.env, timeout=300)
        if r.returncode:
            raise Failed(f"the installer exited {r.returncode}")
        files = self.mentis("verify")["files"]
        aside = [d.name for d in (self.install / "releases").glob(f"{home.name}.damaged-*")]
        if len(aside) != 1:
            raise Failed(f"set aside: {aside}")
        if (self.install / "releases" / aside[0] / "app" / "launcher.py").read_text("utf-8") != "# damaged\n":
            raise Failed("the copy set aside is not the damaged one")
        return {"files_verified": files, "set_aside": aside}

    def do_second_location_refused(self):
        other = self.root / "second"
        r = subprocess.run(f'"{self.installer}" /S /D={other}', env=self.env, timeout=120)
        if r.returncode != 2 or other.exists():
            raise Failed(f"exit {r.returncode}, created {other.exists()}")
        if os.path.normcase(uninstall_entry()["InstallLocation"]) != os.path.normcase(str(self.install)):
            raise Failed(f"the entry moved: {uninstall_entry()}")
        return "exit 2, nothing created, the first install's entry unchanged"

    # -- update and rollback --------------------------------------------------------

    def _stage_of(self, exe: pathlib.Path, commit: str) -> tuple:
        work = exe.parent / f"work-{commit[:12]}"
        stage, nsi = work / "stage", work / "src" / "tools" / "installer" / "mentis.nsi"
        if not stage.is_dir() or not nsi.is_file():
            raise Failed(f"{work} is not here: the proof packs its variants from the build's stage")
        return stage, nsi

    def variant(self, name: str, change=None, tamper=None) -> pathlib.Path:
        """The newer build's stage, changed, stamped as another commit, packed again."""
        if name in self.variants:
            return self.variants[name]
        stage, nsi = self.base_stage
        out = self.root / "variants" / name
        copy = out / "stage"
        shutil.copytree(stage, copy)
        if change:
            change(copy)
            builder.compile_stage(copy)
        built = json.loads((copy / "app" / "BUILD.json").read_text("utf-8"))
        commit = hashlib.sha1(name.encode()).hexdigest()
        builder.stamp(copy, {k: built[k] for k in ("product", "version")} | {"commit": commit})
        if tamper:
            tamper(copy)
        nsis = builder.makensis(json.loads((nsi.parent / "lock.json").read_text("utf-8")), self.cache)
        exe = out / f"Mentis-Setup-{built['version']}-{commit[:12]}.exe"
        builder.pack(copy, nsi, nsis, exe, fast=True)
        shutil.rmtree(copy)
        self.variants[name] = exe
        return exe

    @staticmethod
    def _edit_manifest(stage: pathlib.Path, change) -> None:
        path = stage / "app" / "manifest.json"
        man = json.loads(path.read_text("utf-8"))
        change(man)
        path.write_text(json.dumps(man, indent=1), "utf-8")

    def _unhealthy(self, stage: pathlib.Path) -> None:
        self._edit_manifest(stage, lambda m: m["health"].append("http://127.0.0.1:{port}/api/no-such-path"))

    @staticmethod
    def _migrating(stage: pathlib.Path, *blocks) -> None:
        path = stage / "app" / "mentis" / "spine" / "migrations.py"
        text = path.read_text("utf-8")
        if LIST_LINE not in text:
            raise Failed("mentis.spine.migrations has no list line to add a migration after")
        names = {MIGRATION_ADDITIVE: "PROOF_A", MIGRATION_BREAKING: "PROOF_B", MIGRATION_BREAKING_2: "PROOF_C"}
        new = "".join(blocks) + "MIGRATIONS: tuple[Migration, ...] = (ADOPT, " + \
            ", ".join(names[b] for b in blocks) + ")"
        path.write_text(text.replace(LIST_LINE, new), "utf-8")

    def who(self) -> dict:
        info = json.loads(http(self.url + "/api/server")[1])
        return {"commit": (info.get("release") or {}).get("commit"), "corpus_id": info["corpus_id"],
                "root": info["code"]["root"], "pid": info["process"]["pid"]}

    def expect_running(self, commit: str, why: str = "") -> dict:
        got = self.who()
        if got["commit"] != commit:
            raise Failed(f"{why}: it runs {got['commit']}, not {commit}")
        if not str(got["root"]).startswith(str(self.install / "releases" / self.named("current"))):
            raise Failed(f"{why}: it runs from {got['root']}, not the current release")
        return got

    def no_journal(self, why: str) -> None:
        for name in ("update.journal.json", "needs-attention.json"):
            if (self.install / "state" / name).exists():
                raise Failed(f"{why}: {name} is still there")

    def records(self) -> int:
        db = f"file:{(self.brain / 'corpus.db').as_posix()}?mode=ro"
        with sqlite3.connect(db, uri=True) as c:
            got = c.execute("SELECT count(*) FROM entry").fetchone()[0]
        c.close()
        return got

    def ledger(self) -> int:
        db = f"file:{(self.brain / 'corpus.db').as_posix()}?mode=ro"
        with sqlite3.connect(db, uri=True) as c:
            got = c.execute("SELECT max(to_version) FROM schema_migration").fetchone()[0]
        c.close()
        return got

    def do_update(self):
        self.mentis("start")
        before, records = self.who(), self.records()
        code, doc, err = self.ask("update", str(self.new), "--yes")
        if code or (doc or {}).get("outcome") != "ok":
            raise Failed(f"exit {code}: {doc} {err[-1500:]}")
        got = self.expect_running(self.new_commit, "after update")
        if got["corpus_id"] != before["corpus_id"]:
            raise Failed(f"another Brain: {got['corpus_id']} not {before['corpus_id']}")
        if self.records() < records:
            raise Failed(f"records went from {records} to {self.records()}")
        if self.named("previous") != self.old_name or self.named("current") != self.new_name:
            raise Failed(f"current {self.named('current')} previous {self.named('previous')}")
        if not list((self.root / "backups").glob("*/*")):
            raise Failed("no backup was taken")
        self.no_journal("after update")
        if uninstall_entry()["DisplayVersion"] != self.new_name:
            raise Failed(f"the uninstall entry says {uninstall_entry()['DisplayVersion']}")
        return {"from": before["commit"], "to": got["commit"], "corpus_id": got["corpus_id"],
                "server_pid": [before["pid"], got["pid"]], "message": doc["message"],
                "records": [records, self.records()],
                "backups": len(list((self.root / "backups").glob("*/*")))}

    def do_rollback(self):
        before, records = self.who(), self.records()
        code, doc, err = self.ask("rollback", "--yes")
        if code:
            raise Failed(f"exit {code}: {doc} {err[-1500:]}")
        got = self.expect_running(self.commit, "after rollback")
        if got["corpus_id"] != before["corpus_id"]:
            raise Failed("another Brain after rollback")
        if self.records() < records:
            raise Failed(f"records went from {records} to {self.records()}")
        if self.named("previous") != self.new_name:
            raise Failed(f"previous is {self.named('previous')}")
        self.no_journal("after rollback")
        return {"to": got["commit"], "corpus_id": got["corpus_id"], "message": doc["message"]}

    def do_update_again(self):
        code, doc, err = self.ask("update", str(self.new), "--yes")
        if code:
            raise Failed(f"exit {code}: {doc} {err[-1500:]}")
        got = self.expect_running(self.new_commit, "after updating again")
        if "already" in err:
            raise Failed(err)
        return {"to": got["commit"], "message": doc["message"]}

    def do_setup_exe_updates(self):
        """Double-clicking the newer setup exe is the same transaction."""
        code, doc, err = self.ask("rollback", "--yes")
        if code:
            raise Failed(f"rollback exit {code}: {err[-800:]}")
        r = subprocess.run(f'"{self.new}" /S /D={self.install}', env=self.env, timeout=600)
        if r.returncode:
            raise Failed(f"the setup exe exited {r.returncode}: {self._log_tail()}")
        got = self.expect_running(self.new_commit, "after the setup exe")
        self.no_journal("after the setup exe")
        if (self.install / ".incoming").exists():
            raise Failed(".incoming was left behind")
        return {"to": got["commit"], "previous": self.named("previous")}

    def _log_tail(self) -> str:
        try:
            return (self.install / "state" / "logs" / "update.log").read_text("utf-8", "replace")[-800:]
        except OSError:
            return "(no update log)"

    def _refused(self, exe, why_has: str) -> dict:
        pid, cur = listener(self.port), self.named("current")
        code, doc, err = self.ask("update", str(exe), "--yes")
        if code != 2 or why_has not in (doc or {}).get("message", ""):
            raise Failed(f"exit {code}: {doc} {err[-800:]}")
        if listener(self.port) != pid or self.named("current") != cur:
            raise Failed("the running server or the current release changed")
        self.expect_running(self.new_commit, "after a refusal")
        left = [d.name for d in (self.install / "releases").iterdir() if d.name.startswith(".") or d.name.endswith(".partial")]
        if left or not (doc or {}).get("running"):
            raise Failed(f"left {left}; doc {doc}")
        self.no_journal("after a refusal")
        return {"exit": code, "message": doc["message"][:220], "running": doc["running"], "server_pid_unchanged": pid}

    def do_refuse_truncated(self):
        out = self.root / "variants" / "truncated"
        out.mkdir(parents=True, exist_ok=True)
        exe = out / "Mentis-Setup-truncated.exe"
        data = self.new.read_bytes()
        exe.write_bytes(data[:len(data) // 2])
        return self._refused(exe, "did not unpack")

    def do_refuse_not_setup(self):
        return self._refused(pathlib.Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "where.exe",
                             "not a Mentis setup exe")

    def do_refuse_wrong_hash_beside_it(self):
        out = self.root / "variants" / "wrong-sha"
        out.mkdir(parents=True, exist_ok=True)
        exe = out / self.new.name
        shutil.copy2(self.new, exe)
        (out / (exe.name + ".sha256")).write_text("0" * 64 + "  x\n", "utf-8")
        return self._refused(exe, "is not what")

    def do_refuse_tampered(self):
        def tamper(stage):
            (stage / "app" / "mentis" / "migrate.py").write_text("raise SystemExit(9)\n", "utf-8")
        return self._refused(self.variant("tampered", tamper=tamper), "was refused")

    def _did_not_take(self, exe, why_has: str) -> dict:
        code, doc, err = self.ask("update", str(exe), "--yes")
        if code != 3 or doc.get("reason") != "rolled_back" or not doc.get("previous_restored"):
            raise Failed(f"exit {code}: {doc} {err[-1500:]}")
        if why_has not in doc["message"]:
            raise Failed(f"the words do not say why: {doc['message']}")
        got = self.expect_running(self.new_commit, "after the failed update")
        if self.named("current") != self.new_name:
            raise Failed(f"current is {self.named('current')}")
        self.no_journal("after the failed update")
        kept = "+".join(pathlib.Path(exe).stem.rsplit("-", 2)[1:])
        if not (self.install / "releases" / kept).is_dir():
            raise Failed(f"the words say {kept} is kept, and it is gone")
        return {"exit": code, "running": doc["running"], "message": doc["message"][:300], "corpus_id": got["corpus_id"]}

    def do_wont_start_restored(self):
        def flag(stage):
            self._edit_manifest(stage, lambda m: m["launch"][0]["command"].append("--no-such-flag"))
        return self._did_not_take(self.variant("wont-start", flag), "did not start")

    def do_unhealthy_restored(self):
        return self._did_not_take(self.variant("unhealthy", self._unhealthy), "no-such-path")

    def do_damaged_previous(self):
        """Going back to a damaged release is refused; its package stages it again."""
        name = self.named("previous")
        home = self.install / "releases" / name
        if name != self.old_name:
            raise Failed(f"previous is {name}, not {self.old_name}")
        self._unlock(home)
        (home / "app" / "manifest.json").write_text("{}", "utf-8")
        pid = listener(self.port)
        code, doc, err = self.ask("rollback", "--yes")
        if code != 2 or "is damaged" not in doc["message"] or listener(self.port) != pid:
            raise Failed(f"rollback: exit {code} {doc}")
        code, doc, err = self.ask("update", str(self.installer), "--yes")
        if code:
            raise Failed(f"its own package: exit {code} {doc} {err[-1000:]}")
        self.expect_running(self.commit, "after staging it again")
        aside = [d.name for d in (self.install / "releases").glob(f"{name}.damaged-*")]
        if len(aside) != 2:         # the repair over itself, and this one
            raise Failed(f"set aside: {aside}")
        code, doc, err = self.ask("update", str(self.new), "--yes")
        if code:
            raise Failed(f"forward again: exit {code} {doc} {err[-1000:]}")
        self.expect_running(self.new_commit, "forward again")
        return {"set_aside": aside}

    def do_running_work_waited_for(self):
        """A release whose `working` says a run is open: the update waits, and is
        abandoned with the server left running; when the run ends, it goes."""
        import http.server
        said = {"open": [{"held_here": True, "state": "running"}], "why_not": None}

        class Working(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(said).encode())

            def log_message(self, *a):
                pass
        answering = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Working)
        threading.Thread(target=answering.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{answering.server_address[1]}/api/working"
            exe = self.variant("busy", lambda s: self._edit_manifest(s, lambda m: m.update(working=url)))
            commit = hashlib.sha1(b"busy").hexdigest()
            code, doc, err = self.ask("update", str(exe), "--yes")
            if code:
                raise Failed(f"to the busy release: exit {code} {doc} {err[-1000:]}")
            pid = listener(self.port)
            code, doc, err = self.ask("update", str(self.new), "--drain-wait", "3", "--yes")
            if code != 3 or doc["reason"] != "aborted" or "did not finish" not in doc["message"]:
                raise Failed(f"exit {code} {doc} {err[-1000:]}")
            if listener(self.port) != pid:
                raise Failed("the running server was touched")
            self.expect_running(commit, "after the update was abandoned")
            self.no_journal("after the update was abandoned")
            threading.Timer(5, lambda: said.update(open=[])).start()
            code, later, err = self.ask("update", str(self.new), "--drain-wait", "120", "--yes")
            if code or "waiting for 1 running piece" not in err:
                raise Failed(f"exit {code} {later} {err[-1000:]}")
            self.expect_running(self.new_commit, "after the work ended")
            return {"abandoned": doc["message"][:200], "then_waited_and_went": later["message"]}
        finally:
            answering.shutdown()

    def _holding_the_brain(self) -> subprocess.Popen:
        p = subprocess.Popen([str(self.release_dir() / "runtime" / "python.exe"), "-I", "-X", "utf8", "-c",
                              "import sys; from mentis.spine import brainlock\n"
                              "held = brainlock.shared(sys.argv[1])\nprint('held', flush=True)\nsys.stdin.read()",
                              str(self.brain)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=self.env,
                             text=True, cwd=self.root)
        if p.stdout.readline().strip() != "held":
            raise Failed("could not hold the Brain open")
        return p

    def do_brain_held_open(self):
        """Something that is not a server has the Brain: nothing is decided past it."""
        target = self.variant("second")
        version = self.ledger()
        self.mentis("stop")
        holder = self._holding_the_brain()
        try:
            code, doc, err = self.ask("update", str(target), "--yes")
        finally:
            holder.communicate("")
        if code != 3 or doc["reason"] != "aborted" or "still has the Brain" not in doc["message"]:
            raise Failed(f"at the stop: exit {code} {doc} {err[-800:]}")
        self.mentis("start")
        code, doc, err = self.ask("update", str(target), "--yes", env={"MENTIS_UPDATE_KILL_AT": "state:BACKED_UP"})
        if code == 0:
            raise Failed("the kill did not happen")
        holder = self._holding_the_brain()
        try:
            code, doc, err = self.ask("update", "--resume")
            if code != 2 or "still running" not in doc["message"]:
                raise Failed(f"resume while held: exit {code} {doc} {err[-800:]}")
            if not (self.install / "state" / "update.journal.json").exists():
                raise Failed("the journal went while the Brain was held")
        finally:
            holder.communicate("")
        code, doc, err = self.ask("update", "--resume")
        if code != 3 or doc["reason"] != "aborted":
            raise Failed(f"resume after: exit {code} {doc} {err[-800:]}")
        self.expect_running(self.new_commit, "after it let go")
        if self.ledger() != version:
            raise Failed(f"ledger {self.ledger()}")
        return {"at_the_stop": "aborted", "resume_while_held": "refused, journal kept", "then": doc["reason"]}

    def _recovered(self, label: str, how: str, want: str) -> dict:
        """After a kill: the install runs, the recovery finishes, the right release answers."""
        checked = self.ask("verify")
        if checked[0]:
            raise Failed(f"{label}: mentis.cmd verify exit {checked[0]}: {checked[1]} {checked[2][-400:]}")
        code, doc, err = (self.ask("update", "--resume") if how == "resume" else self.ask("start"))
        if code not in (0, 3):
            raise Failed(f"{label}: {how} exit {code}: {doc} {err[-800:]}")
        self.no_journal(label)
        self.expect_running(want, f"after a kill at {label}, then {how}")
        return {"at": label, "recovered_by": how, "exit": code, "running": want[:12]}

    def do_kill_at_each_step(self):
        target = self.variant("second")
        target_commit = hashlib.sha1(b"second").hexdigest()
        rows = []
        for i, (label, ends) in enumerate(KILLS):
            how = "resume" if i % 2 else "start"
            code, doc, err = self.ask("update", str(target), "--yes", env={"MENTIS_UPDATE_KILL_AT": label})
            if code == 0:
                raise Failed(f"the kill at {label} did not happen: {doc}")
            want = target_commit if ends == "target" else self.new_commit
            if label.startswith("stage:"):
                # the server was never touched, and nothing is unfinished
                self.expect_running(self.new_commit, f"after a kill at {label}")
                rows.append({"at": label, "server_untouched": True, "exit": code})
                continue
            rows.append(self._recovered(label, how, want))
            if ends == "target":
                back = self.ask("rollback", "--yes")
                if back[0]:
                    raise Failed(f"going back after {label}: {back[1]} {back[2][-600:]}")
        return rows

    def do_kill_in_rollback(self):
        """`second` is `previous` now, from the last step."""
        target_commit = hashlib.sha1(b"second").hexdigest()
        rows = []
        for label, want, how in (("state:STOPPED", self.new_commit, "resume"),
                                 ("after:C2", target_commit, "start")):
            code, doc, err = self.ask("rollback", "--yes", env={"MENTIS_UPDATE_KILL_AT": label})
            if code == 0:
                raise Failed(f"the kill at {label} did not happen")
            rows.append(self._recovered(label, how, want))
        back = self.ask("rollback", "--yes")
        if back[0]:
            raise Failed(f"{back[1]} {back[2][-600:]}")
        self.expect_running(self.new_commit, "back on the newer build")
        return rows

    def do_kill_while_switching_back(self):
        exe = self.variant("unhealthy", self._unhealthy)
        rows = []
        for i, label in enumerate(("rollingback:stopped", "rollingback:pointed", "rollingback:started")):
            code, doc, err = self.ask("update", str(exe), "--yes", env={"MENTIS_UPDATE_KILL_AT": label})
            if code == 0:
                raise Failed(f"the kill at {label} did not happen")
            rows.append(self._recovered(label, "start" if i % 2 else "resume", self.new_commit))
        return rows

    def do_kill_from_outside(self):
        """Not a hook: the whole process tree, killed when the journal says STOPPED."""
        import psutil
        target = self.variant("second")
        journal = self.install / "state" / "update.journal.json"
        p = subprocess.Popen([str(self.install / "mentis.cmd"), "update", str(target), "--yes"], env=self.env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, cwd=self.root)
        end = time.monotonic() + 300
        said = None
        while time.monotonic() < end and p.poll() is None:
            try:
                said = json.loads(journal.read_text("utf-8"))["state"]
            except (OSError, ValueError, KeyError):
                said = None
            if said == "STOPPED":
                break
            time.sleep(0.02)
        if said != "STOPPED":
            raise Failed(f"it never reached STOPPED (journal {said}, exit {p.poll()})")
        tree = psutil.Process(p.pid)
        for child in tree.children(recursive=True):
            child.kill()
        tree.kill()
        p.wait(30)
        return self._recovered("STOPPED, killed from outside", "start", self.new_commit)

    def do_migration_killed_past_c1(self):
        """Past C1 the ledger decides, whatever the journal says: forward, never back."""
        exe = self.variant("additive", lambda s: self._migrating(s, MIGRATION_ADDITIVE))
        commit = hashlib.sha1(b"additive").hexdigest()
        if self.ledger() != 1:
            raise Failed(f"the Brain is at {self.ledger()}")
        code, doc, err = self.ask("update", str(exe), "--yes", env={"MENTIS_UPDATE_KILL_AT": "after:C1"})
        if code == 0:
            raise Failed("the kill did not happen")
        version = self.ledger()
        got = self._recovered("after:C1, a real migration applied", "resume", commit)
        if version != 2 or self.ledger() != 2:
            raise Failed(f"ledger {version} then {self.ledger()}")
        return {**got, "ledger_after_kill": version}

    def do_rollback_after_additive_migration(self):
        code, doc, err = self.ask("rollback", "--yes")
        if code:
            raise Failed(f"exit {code}: {doc} {err[-800:]}")
        self.expect_running(self.new_commit, "the older code on the additive Brain")
        if self.ledger() != 2:
            raise Failed(f"ledger {self.ledger()}")
        return {"message": doc["message"], "ledger": self.ledger(), "older_code_reads_it": True}

    def do_breaking_migration_refuses_rollback(self):
        exe = self.variant("additive", lambda s: self._migrating(s, MIGRATION_ADDITIVE))
        code, doc, err = self.ask("update", str(exe), "--yes")
        if code:
            raise Failed(f"additive again, exit {code}: {doc} {err[-800:]}")
        if "Brain migrations: none" not in err:
            raise Failed(f"it would migrate again: {err[-600:]}")
        exe = self.variant("breaking", lambda s: self._migrating(s, MIGRATION_ADDITIVE, MIGRATION_BREAKING))
        code, doc, err = self.ask("update", str(exe), "--yes")
        if code:
            raise Failed(f"breaking, exit {code}: {doc} {err[-800:]}")
        if "BREAKING" not in err or "can no longer open" not in err:
            raise Failed(f"the plan did not say so: {err[-800:]}")
        commit = hashlib.sha1(b"breaking").hexdigest()
        self.expect_running(commit, "after the breaking migration")
        if self.ledger() != 3:
            raise Failed(f"ledger {self.ledger()}")
        pid = listener(self.port)
        # the previous release here reads schema 2, and the Brain needs 3
        code, doc, err = self.ask("rollback", "--yes")
        if code != 2 or "cannot read" not in doc["message"] or "nothing was changed" not in doc["message"]:
            raise Failed(f"rollback: exit {code} {doc}")
        if listener(self.port) != pid:
            raise Failed("the refusal touched the server")
        self.expect_running(commit, "after the refused rollback")
        older = self.ask("update", str(self.new), "--yes")
        if older[0] != 2 or "cannot open this Brain" not in older[1]["message"]:
            raise Failed(f"an older package: {older[0]} {older[1]}")
        self.expect_running(commit, "after the refused older package")
        return {"rollback_refused": doc["message"][:300], "older_package_refused": older[1]["message"][:220],
                "ledger": self.ledger(), "server_pid_unchanged": pid}

    def do_needs_attention_after_a_breaking_failure(self):
        """New code unhealthy, old code cannot read the Brain: it stops and says so.
        Nothing is restored until somebody does it, and `--resume` then goes back."""
        exe = self.variant("breaking-unhealthy", lambda s: (
            self._migrating(s, MIGRATION_ADDITIVE, MIGRATION_BREAKING, MIGRATION_BREAKING_2), self._unhealthy(s)))
        code, doc, err = self.ask("update", str(exe), "--yes")
        if code != 4 or doc["outcome"] != "needs_attention" or self.ledger() != 4:
            raise Failed(f"exit {code} ledger {self.ledger()}: {doc} {err[-800:]}")
        if listener(self.port) is not None:
            raise Failed("something still serves the Brain")
        said = json.loads((self.install / "state" / "needs-attention.json").read_text("utf-8"))
        if not said["nothing_deleted"] or not said["restore_plan_command"]:
            raise Failed(f"{said}")
        start = self.ask("start")
        again = self.ask("update", "--resume")
        if start[0] != 4 or again[0] != 4 or listener(self.port) is not None:
            raise Failed(f"start {start[0]} {start[1]}; resume {again[0]} {again[1]}")
        py = self.install / "releases" / said["releases"]["from"] / "runtime" / "python.exe"
        plan = subprocess.run([str(py), "-I", "-X", "utf8", "-m", "mentis.brain", "restore-plan",
                               str(self.brain), said["backup"]], env=self.env, text=True, encoding="utf-8",
                              capture_output=True, cwd=self.root)
        if plan.returncode:
            raise Failed(f"restore-plan: {plan.stderr[-800:]}")
        digest = json.loads(plan.stdout)["digest"]
        done = subprocess.run([str(py), "-I", "-X", "utf8", "-m", "mentis.brain", "restore",
                               str(self.brain), said["backup"], "--confirm", digest], env=self.env, text=True,
                              encoding="utf-8", capture_output=True, cwd=self.root)
        if done.returncode:
            raise Failed(f"restore: {done.stderr[-800:]}")
        if self.ledger() != 3:
            raise Failed(f"after the restore, ledger {self.ledger()}")
        code, doc, err = self.ask("update", "--resume")
        if code != 3 or doc["reason"] != "rolled_back" or not doc["previous_restored"]:
            raise Failed(f"resume after the restore: exit {code} {doc} {err[-800:]}")
        self.expect_running(hashlib.sha1(b"breaking").hexdigest(), "after the restore and resume")
        if self.ledger() != 3:
            raise Failed(f"trying the new release again moved the Brain to {self.ledger()}")
        self.no_journal("after the restore and resume")
        return {"said": said["why"][:300], "start_refused": start[0], "resume_refused": again[0],
                "after_restoring_by_hand": doc["message"][:220], "ledger": self.ledger()}

    def do_releases_kept(self):
        names = sorted(d.name for d in (self.install / "releases").iterdir())
        left = [n for n in names if n.startswith(".") or n.endswith(".partial")]
        if left:
            raise Failed(f"staging left {left}")
        if self.old_name not in names or not [n for n in names if ".damaged-" in n]:
            raise Failed(f"a release went: {names}")
        keep = sorted(n for n in (self.named("current"), self.named("previous")) if n)
        for name in keep:
            home = self.install / "releases" / name
            got = subprocess.run([str(home / "runtime" / "python.exe"), "-I", "-X", "utf8",
                                  str(home / "app" / "launcher.py"), "verify"], env=self.env, text=True,
                                 encoding="utf-8", capture_output=True, cwd=self.root)
            if got.returncode:
                raise Failed(f"{name} does not verify: {got.stdout[-400:]}")
        return {"releases": names, "current_and_previous_verify": keep}

    def do_uninstall(self):
        self.brain_hash = hashlib.sha256((self.brain / "corpus.db").read_bytes()).hexdigest()
        backups = list((self.root / "backups").glob("*/*"))
        self.mentis("start")                    # uninstall must stop what is running
        r = subprocess.run([str(self.install / "uninstall.exe"), "/S"], env=self.env, timeout=120)
        if r.returncode:
            raise Failed(f"uninstall.exe exited {r.returncode}")
        end = time.monotonic() + 120
        while time.monotonic() < end and (uninstall_entry() or self.install.exists()):
            time.sleep(0.5)
        left = sorted(str(p) for p in self.install.rglob("*")) if self.install.exists() else []
        if uninstall_entry() or self.install.exists():
            raise Failed(f"entry {uninstall_entry()}, left in the folder: {left[:15]}")
        if listener(self.port) is not None:
            raise Failed(f"port {self.port} is still held after uninstall")
        shortcuts = pathlib.Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Mentis"
        if shortcuts.exists():
            raise Failed(f"left {shortcuts}")
        gone = [str(b) for b in backups if not b.exists()]
        if gone:
            raise Failed(f"the Brain's backups went with the install: {gone[:3]}")
        return "folder, uninstall entry, Start Menu folder gone; server stopped"

    def do_brain_kept(self):
        now = hashlib.sha256((self.brain / "corpus.db").read_bytes()).hexdigest()
        if not self.workspace.is_dir():
            raise Failed("the workspace is gone")
        return {"corpus_db": str(self.brain / "corpus.db"), "sha256": now[:16],
                "same_as_before_uninstall_start": now == self.brain_hash}

    def do_uninstall_broken(self):
        """A mentis.cmd that cannot run must not keep an uninstall out."""
        r = subprocess.run(f'"{self.installer}" /S /D={self.install}', env=self.env, timeout=300)
        if r.returncode:
            raise Failed(f"the installer exited {r.returncode}")
        (self.install / "state" / "current").write_text("no-such-release\n", "utf-8")
        said = self.ask("status")
        if said[0] == 0 or "is not here" not in said[2]:
            raise Failed(f"mentis.cmd said {said}")
        r = subprocess.run([str(self.install / "uninstall.exe"), "/S"], env=self.env, timeout=120)
        if r.returncode:
            raise Failed(f"uninstall.exe exited {r.returncode}")
        end = time.monotonic() + 120
        while time.monotonic() < end and (uninstall_entry() or self.install.exists()):
            time.sleep(0.5)
        if uninstall_entry() or self.install.exists():
            raise Failed(f"entry {uninstall_entry()}, folder there: {self.install.exists()}")
        return {"mentis_cmd_said": said[2].strip()[:160]}

    def do_prepare(self):
        """The base stage to vary, and the newer build when none was given."""
        built = json.loads((self.release_dir() / "app" / "BUILD.json").read_text("utf-8"))
        self.commit = self.commit or built["commit"]
        self.old_name = f"{built['version']}+{built['commit'][:12]}"
        if self.new:
            self.base_stage = self._stage_of(self.new, self.new_commit)
        else:
            self.base_stage = self._stage_of(self.installer, built["commit"])
            self.new = self.variant("stamped-newer")
            self.new_commit = hashlib.sha1(b"stamped-newer").hexdigest()
        self.new_name = f"{built['version']}+{self.new_commit[:12]}"
        return {"old": self.old_name, "new": self.new_name, "new_exe": str(self.new),
                "variants_from": str(self.base_stage[0])}

    def run(self) -> dict:
        if self.port == 8760:
            raise Failed("port 8760 is the day-to-day server's; choose another")
        if self.root.exists() and any(self.root.iterdir()):
            raise Failed(f"{self.root} exists and is not empty; a proof starts empty")
        if uninstall_entry():
            raise Failed(f"this user has an install already, left alone: {uninstall_entry()}")
        if listener(self.port) is not None:
            raise Failed(f"port {self.port} is in use")
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in ("localappdata", "appdata"):
            (self.root / sub).mkdir()
        watched = listener(8760)
        installed = self.step("install silently, every file against its build hash", self.do_install)
        if installed:
            for name, fn in (("no python, node, git or npm on its PATH", self.do_no_tools),
                             ("setup creates a new Brain and starts", self.do_setup),
                             ("the server is this build, on this Brain", self.do_server),
                             ("the Brain holds the baseline and tour", self.do_brain),
                             ("Fluid's page and every asset are served", self.do_fluid_files),
                             ("Fluid draws in a real browser", self.do_browser),
                             ("the render check reads the built Fluid", self.do_render_check),
                             ("the MCP bridge attaches", self.do_bridge),
                             ("stop is clean, the Brain is sound", self.do_stop),
                             ("attach the same Brain, restart, open, status", self.do_attach_restart),
                             ("install again over itself, with the server running", self.do_install_again),
                             ("install over a damaged release: repaired, the copy kept", self.do_install_over_a_damaged_release),
                             ("a second install location is refused", self.do_second_location_refused),
                             ("the update's packages are ready", self.do_prepare),
                             ("update: the new commit, the same Brain", self.do_update),
                             ("rollback: the old commit, the same Brain", self.do_rollback),
                             ("update again", self.do_update_again),
                             ("the newer setup exe over the install is the same update", self.do_setup_exe_updates),
                             ("refused, old server answering: a truncated package", self.do_refuse_truncated),
                             ("refused, old server answering: not a setup exe", self.do_refuse_not_setup),
                             ("refused, old server answering: its .sha256 disagrees", self.do_refuse_wrong_hash_beside_it),
                             ("refused, old server answering: a changed payload", self.do_refuse_tampered),
                             ("the new server will not start: previous restored", self.do_wont_start_restored),
                             ("the health check fails: previous restored", self.do_unhealthy_restored),
                             ("a damaged previous release: refused, then its package stages it", self.do_damaged_previous),
                             ("running work: waited for, abandoned, then gone through", self.do_running_work_waited_for),
                             ("something else has the Brain open: never decided past it", self.do_brain_held_open),
                             ("a kill at every step of an update recovers", self.do_kill_at_each_step),
                             ("a kill in a rollback recovers", self.do_kill_in_rollback),
                             ("a kill while switching back recovers", self.do_kill_while_switching_back),
                             ("the whole process tree killed from outside recovers", self.do_kill_from_outside),
                             ("a kill just past a real migration goes forward", self.do_migration_killed_past_c1),
                             ("rollback over an additive migration: old code reads it", self.do_rollback_after_additive_migration),
                             ("a breaking migration: rollback refused in true words", self.do_breaking_migration_refuses_rollback),
                             ("unhealthy past a breaking migration: stops, restores nothing", self.do_needs_attention_after_a_breaking_failure),
                             ("no release was removed, the two in use verify", self.do_releases_kept)):
                if not self.step(name, fn):
                    break
        if self.install.exists():
            try:
                self.mentis("stop")
            except Exception:                               # noqa: BLE001
                pass
            uninstalled = self.step("uninstall silently, with the server running", self.do_uninstall)
            if uninstalled:
                self.step("the Brain and workspace stay", self.do_brain_kept)
                self.step("uninstall when mentis.cmd cannot run", self.do_uninstall_broken)
        return {"ok": all(s["ok"] for s in self.steps) and bool(self.steps),
                "installer": str(self.installer),
                "installer_sha256": hashlib.sha256(self.installer.read_bytes()).hexdigest(),
                "port": self.port, "root": str(self.root),
                "pid_on_8760_before_after": [watched, listener(8760)],
                "steps": self.steps}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("installer")
    ap.add_argument("--root", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--commit", help="the commit the install must say it is")
    ap.add_argument("--new", help="a newer build's exe, to update to")
    ap.add_argument("--new-commit", help="the commit that build must say it is")
    ap.add_argument("--evidence")
    ap.add_argument("--cache", help="where the builder keeps the pinned NSIS")
    a = ap.parse_args(argv)
    try:
        got = Proof(a.installer, a.root, a.port, a.commit, a.evidence, a.new, a.new_commit, a.cache).run()
    except Failed as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(got, indent=1))
    return 0 if got["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
