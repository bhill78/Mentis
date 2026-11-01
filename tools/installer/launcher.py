"""The installed Mentis's one command: `mentis.cmd <command>`.

    mentis.cmd setup [--brain DIR] [--owner @alias] [--attach] [--port N]
                     [--workspace DIR] [--mars COMMAND] [--no-tour]
                     [--no-start] [--no-browser]
    mentis.cmd open [--no-browser]     start what is not running, open Fluid
    mentis.cmd start | stop | status | verify | version

It runs on the install's own Python, is copied to `app\\launcher.py`, and needs
nothing else on the machine. WHAT TO START IS NOT HERE: `app\\manifest.json`
(tools/installer/manifest.json) declares it. `launch` is started in order and
stopped in reverse, so one more process is one more row there.

SETUP is `python -m mentis.bootstrap`, the new-Brain setup, run once. On a folder
holding a Brain it needs `--attach`, and then runs `--check` first: a refusal
there changes nothing. The Brain and the workspace live outside the install, so
uninstalling leaves them.

STARTING IS NOT SUPERVISING. Nothing here watches, restarts or retries. A process
that does not answer is stopped and the failure said.

STOPPING is Ctrl-C, the server's own clean stop (`mentis.web.serve`), delivered
by a small helper attached to that process's console; only a process that has
not gone after STOP_WAIT_S is killed, and the answer says which it was.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

FIRST_PORT = 8780
PORT_SPAN = 100
READY_WAIT_S = 90
STOP_WAIT_S = 30
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

#: The helper that delivers Ctrl-C. Its own process, because leaving this
#: console to attach to another would take this command's output with it.
_CTRL_C = (
    "import ctypes,sys\n"
    "k=ctypes.windll.kernel32\n"
    "k.FreeConsole()\n"
    "ok=k.AttachConsole(int(sys.argv[1]))\n"
    "ok=ok and k.SetConsoleCtrlHandler(None,True)\n"
    "ok=ok and k.GenerateConsoleCtrlEvent(0,0)\n"
    "import time;time.sleep(0.5)\n"
    "sys.exit(0 if ok else 1)\n")


class Refused(Exception):
    """Said in words; nothing was changed by whatever refused."""


class Install:
    def __init__(self, root=None):
        self.root = pathlib.Path(root or pathlib.Path(__file__).resolve().parents[1])
        self.app = self.root / "app"
        self.state_dir = self.root / "state"
        self.state_file = self.state_dir / "install.json"
        self.running_file = self.state_dir / "running.json"
        self.logs = self.state_dir / "logs"
        self.python = str(self.root / "runtime" / "python.exe")

    def manifest(self) -> dict:
        return json.loads((self.app / "manifest.json").read_text("utf-8"))

    def build(self) -> dict:
        return json.loads((self.app / "BUILD.json").read_text("utf-8"))

    def state(self) -> dict | None:
        try:
            return json.loads(self.state_file.read_text("utf-8"))
        except FileNotFoundError:
            return None

    def running(self) -> list:
        try:
            return json.loads(self.running_file.read_text("utf-8"))
        except FileNotFoundError:
            return []

    def write(self, path: pathlib.Path, value) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".partial")
        part.write_text(json.dumps(value, indent=1), "utf-8")
        os.replace(part, path)

    def values(self, st: dict) -> dict:
        """What a manifest row may name."""
        ports = {k: str(int(st["port"]) + int(off))
                 for k, off in self.manifest()["ports"].items()}
        return {"python": self.python, "root": str(self.root), "brain": st["brain"],
                "workspace": st["workspace"], "mars": st["mars"], **ports}


# -- ports ----------------------------------------------------------------------

def port_free(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            return False
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_port(offsets) -> int:
    """The first port from FIRST_PORT whose whole declared set is free."""
    for port in range(FIRST_PORT, FIRST_PORT + PORT_SPAN):
        if all(port_free(port + int(off)) for off in offsets):
            return port
    raise Refused(f"no free port from {FIRST_PORT} to {FIRST_PORT + PORT_SPAN - 1}; "
                  "name one with --port")


# -- starting and stopping ------------------------------------------------------

def _alive(entry: dict):
    """The psutil process this entry started, or None. A pid alone could be
    somebody else's by now: the start time says it is still ours."""
    import psutil
    try:
        p = psutil.Process(entry["pid"])
        return p if abs(p.create_time() - entry["created"]) < 2 and p.is_running() else None
    except psutil.Error:
        return None


def _answer(url: str, timeout: float = 3.0):
    req = urllib.request.Request(url, headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def _same_path(a, b) -> bool:
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def _wait_ready(proc, url: str, st: dict) -> None:
    end = time.monotonic() + READY_WAIT_S
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise Refused(f"it exited with status {proc.returncode}")
        try:
            status, body = _answer(url)
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
            continue
        if status == 200:
            try:
                corpus = json.loads(body).get("corpus")
            except ValueError:
                corpus = None
            if corpus and not _same_path(corpus, st["brain"]):
                raise Refused(f"{url} answers for another Brain, {corpus}")
            return
    raise Refused(f"{url} did not answer within {READY_WAIT_S} s")


def _tail(path: pathlib.Path, n: int = 25) -> str:
    try:
        return "\n".join(path.read_text("utf-8", "replace").splitlines()[-n:])
    except OSError:
        return "(no log)"


def start(inst: Install, st: dict) -> dict:
    import psutil
    if any(_alive(e) for e in inst.running()):
        return {"started": [], "already_running": True}
    man = inst.manifest()
    for name, off in man["ports"].items():
        port = int(st["port"]) + int(off)
        if not port_free(port):
            raise Refused(f"port {port} ({name}) is in use; `mentis.cmd stop`, or "
                          "run setup again with another --port")
    inst.logs.mkdir(parents=True, exist_ok=True)
    values = inst.values(st)
    # A parent that ignores Ctrl-C passes that on, and then the clean stop
    # could never reach what it starts.
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    started: list = []
    for row in man["launch"]:
        log = inst.logs / f"{row['name']}.log"
        command = [a.format_map(values) for a in row["command"]]
        with open(log, "ab") as out:
            proc = subprocess.Popen(command, cwd=inst.state_dir, env=env,
                                    stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        started.append({"name": row["name"], "pid": proc.pid,
                        "created": psutil.Process(proc.pid).create_time()})
        inst.write(inst.running_file, started)
        try:
            if row.get("ready"):
                _wait_ready(proc, row["ready"].format_map(values), st)
        except Refused as exc:
            stop(inst)
            raise Refused(f"{row['name']} did not start: {exc}\n{_tail(log)}") from None
    return {"started": [e["name"] for e in started], "already_running": False}


def _stop_one(inst: Install, entry: dict) -> str:
    """'gone', 'clean' or 'killed'. Refused if it outlives even the kill."""
    import psutil
    p = _alive(entry)
    if p is None:
        return "gone"
    subprocess.run([inst.python, "-I", "-c", _CTRL_C, str(entry["pid"])],
                   creationflags=NO_WINDOW, capture_output=True, timeout=30)
    try:
        p.wait(STOP_WAIT_S)
        return "clean"
    except psutil.TimeoutExpired:
        pass
    p.kill()
    try:
        p.wait(10)
    except psutil.TimeoutExpired:
        raise Refused(f"{entry['name']} (pid {entry['pid']}) would not stop") from None
    return "killed"


def stop(inst: Install) -> dict:
    how = {}
    for entry in reversed(inst.running()):
        how[entry["name"]] = _stop_one(inst, entry)
    inst.running_file.unlink(missing_ok=True)
    return {"stopped": how}


# -- setup ----------------------------------------------------------------------

def _ask(question: str, default: str) -> str:
    got = input(f"{question} [{default}]: ").strip()
    return got or default


def _inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    return path == root or root in path.parents


def _bootstrap(inst: Install, brain: str, owner: str, *more) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    return subprocess.run([inst.python, "-I", "-X", "utf8", "-m", "mentis.bootstrap",
                           brain, "--owner", owner, *more],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, cwd=inst.root)


def setup(inst: Install, a, interactive: bool) -> dict:
    if any(_alive(e) for e in inst.running()):
        raise Refused("Mentis is running from this install; `mentis.cmd stop` first")
    home = pathlib.Path.home() / "Mentis"
    held = inst.state() or {}
    brain = a.brain or held.get("brain")
    owner = a.owner or held.get("owner")
    if interactive:
        brain = _ask("Where should your Brain live? An existing Brain may be named",
                     str(brain or home / "brain"))
        owner = _ask("Your alias", owner or "@" + getpass.getuser())
    if not brain:
        brain = str(home / "brain")
    if not owner:
        raise Refused("setup needs --owner @your-alias")
    owner = owner if owner.startswith("@") else "@" + owner
    target = pathlib.Path(brain).expanduser().resolve()
    if _inside(target, inst.root.resolve()):
        raise Refused(f"{target} is inside the install, which uninstalling removes; "
                      "a Brain lives outside it")
    workspace = pathlib.Path(a.workspace or held.get("workspace")
                             or target.parent / "workspace").expanduser().resolve()
    offsets = inst.manifest()["ports"].values()
    port = a.port or held.get("port") or choose_port(offsets)
    more = ["--no-tour"] if a.no_tour else []
    exists = (target / "corpus.db").is_file()
    if exists:
        if not a.attach and not (interactive and _ask(
                f"{target} already holds a Brain. Use it? (yes/no)", "no").lower() in ("y", "yes")):
            raise Refused(f"{target} already holds a Brain; say --attach to use it")
        checked = _bootstrap(inst, str(target), owner, "--check", *more)
        if checked.returncode:
            raise Refused(f"this Brain cannot be attached as it stands, and nothing "
                          f"was changed:\n{checked.stderr.strip()}")
    done = _bootstrap(inst, str(target), owner, *more)
    if done.returncode:
        raise Refused(f"the new-Brain setup refused:\n{done.stderr.strip()}")
    workspace.mkdir(parents=True, exist_ok=True)
    st = {"brain": str(target), "owner": owner, "port": int(port),
          "workspace": str(workspace), "mars": a.mars or held.get("mars") or "mars stdio"}
    inst.write(inst.state_file, st)
    return {"brain": st["brain"], "created": not exists, "owner": owner,
            "port": st["port"], "workspace": st["workspace"], "mars": st["mars"]}


# -- the rest -------------------------------------------------------------------

def verify(inst: Install) -> dict:
    """Every file the build put here, against the hash it was built with."""
    files = json.loads((inst.app / "FILES.json").read_text("utf-8"))
    missing, changed = [], []
    for rel, want in files.items():
        p = inst.root / rel
        if not p.is_file():
            missing.append(rel)
        elif hashlib.sha256(p.read_bytes()).hexdigest() != want:
            changed.append(rel)
    return {"ok": not (missing or changed), "files": len(files),
            "missing": missing, "changed": changed}


def status(inst: Install) -> dict:
    st = inst.state()
    entries = [{"name": e["name"], "pid": e["pid"], "alive": _alive(e) is not None}
               for e in inst.running()]
    return {"build": inst.build(), "setup": st, "processes": entries,
            "url": (inst.manifest()["open"].format_map(inst.values(st)) if st else None)}


def do_open(inst: Install, a, interactive: bool) -> dict:
    if inst.state() is None:
        if not interactive:
            raise Refused("Mentis is not set up yet: `mentis.cmd setup --owner @you`")
        setup(inst, a, True)
    st = inst.state()
    out = start(inst, st)
    url = inst.manifest()["open"].format_map(inst.values(st))
    if not a.no_browser:
        import webbrowser
        webbrowser.open(url)
    return {**out, "url": url}


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mentis.cmd", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("setup", help="create or attach a Brain, then start and open")
    s.add_argument("--brain")
    s.add_argument("--owner")
    s.add_argument("--attach", action="store_true",
                   help="use the Brain already in that folder")
    s.add_argument("--port", type=int)
    s.add_argument("--workspace")
    s.add_argument("--mars", help="the command that starts MARS (default: mars stdio)")
    s.add_argument("--no-tour", action="store_true")
    s.add_argument("--no-start", action="store_true")
    s.add_argument("--no-browser", action="store_true")
    o = sub.add_parser("open", help="start what is not running and open Fluid")
    o.add_argument("--no-browser", action="store_true")
    for name in ("start", "stop", "status", "verify", "version"):
        sub.add_parser(name)
    return ap


def _empty_setup_args(a) -> None:
    """`open` falling through to setup has none of setup's flags."""
    for name in ("brain", "owner", "workspace", "mars", "port"):
        setattr(a, name, getattr(a, name, None))
    for name in ("attach", "no_tour"):
        setattr(a, name, getattr(a, name, False))


def main(argv=None, inst: Install | None = None) -> int:
    a = _parser().parse_args(argv)
    inst = inst or Install()
    # Named flags mean a script is driving; a person at a console is asked.
    interactive = (sys.stdin is not None and sys.stdin.isatty()
                   and not (getattr(a, "owner", None) or getattr(a, "brain", None)))
    _empty_setup_args(a)
    try:
        if a.command == "setup":
            out = setup(inst, a, interactive)
            if not a.no_start:
                out = {**out, **do_open(inst, a, False)}
        elif a.command == "open":
            out = do_open(inst, a, interactive)
        elif a.command == "start":
            st = inst.state()
            if st is None:
                raise Refused("Mentis is not set up yet: `mentis.cmd setup --owner @you`")
            out = start(inst, st)
        elif a.command == "stop":
            out = stop(inst)
        elif a.command == "status":
            out = status(inst)
        elif a.command == "verify":
            out = verify(inst)
            if not out["ok"]:
                print(json.dumps(out, indent=1))
                return 1
        else:
            out = inst.build()
    except (Refused, OSError) as exc:
        print(f"mentis: {exc}", file=sys.stderr)
        if interactive:
            input("Press Enter to close. ")
        return 1
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
