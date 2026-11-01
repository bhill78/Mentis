"""Prove a built installer on this PC: real install, setup, open, restart, uninstall.

    python tools/prove_windows_installer.py <Mentis-Setup-...exe> --root DIR --port N
        [--commit SHA] [--evidence DIR]

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
from build_windows_installer import scrubbed_env  # noqa: E402

KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MentisServer"
EDGE = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")


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
    def __init__(self, installer, root, port, commit, evidence):
        self.installer = pathlib.Path(installer).resolve()
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

    def python(self, *args, timeout=60) -> str:
        r = subprocess.run([str(self.install / "runtime" / "python.exe"), "-I", "-X", "utf8", *args],
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
        status, body, _ = http(self.url + "/fluid/api/topics")
        names = re.findall(r'"name":\s*"([^"]+)"', body.decode("utf-8", "replace"))
        log = (self.install / "state" / "logs" / "server.log").read_text("utf-8", "replace")
        if "no Mentis baseline" in log or "intake does not resolve" in log:
            raise Failed("the server says the Brain has no baseline or intake")
        if not names:
            raise Failed(f"no topics from the welcome tour: {body[:300]}")
        return {"topics": names[:8], "log": log.splitlines()[0][:200]}

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
        p = subprocess.Popen([str(self.install / "runtime" / "python.exe"), "-I", "-X", "utf8",
                              str(self.install / "app" / "tools" / "mcp_bridge.py"),
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

    def do_uninstall(self):
        self.brain_hash = hashlib.sha256((self.brain / "corpus.db").read_bytes()).hexdigest()
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
        return "folder, uninstall entry, Start Menu folder gone; server stopped"

    def do_brain_kept(self):
        now = hashlib.sha256((self.brain / "corpus.db").read_bytes()).hexdigest()
        if not self.workspace.is_dir():
            raise Failed("the workspace is gone")
        return {"corpus_db": str(self.brain / "corpus.db"), "sha256": now[:16],
                "same_as_before_uninstall_start": now == self.brain_hash}

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
                             ("attach the same Brain, restart, open, status", self.do_attach_restart)):
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
    ap.add_argument("--evidence")
    a = ap.parse_args(argv)
    try:
        got = Proof(a.installer, a.root, a.port, a.commit, a.evidence).run()
    except Failed as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(got, indent=1))
    return 0 if got["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
