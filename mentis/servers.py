"""Mentis servers on this machine, found by what they say they are.

A server is identified by its own `/api/server` answer -- process id, start
time and the code directory it imported -- AND by the operating system naming
the same process as the one listening on that port. Never by a command-line
pattern: one of those matched the live server and stopped it
(docs/evidence/process-match-killed-the-live-server.md). The port check
matters because whatever answers HTTP on a port may be a proxy for some
other server (`vite` dev with MENTIS_API set is exactly that).

Stopping re-asks the same port immediately before acting, and acts only if
the same process (pid AND start time, from the same code directory) still
answers AND still owns the port. Anything else is left alone and reported.
When the machine cannot be asked which ports are in use, the answer is
"unknown", never "none".

ONE WAY ON EVERY OS: the operating system is asked through psutil (ports,
processes, liveness, termination), replacing netstat, tasklist, taskkill and
ctypes, which were Windows-only or parsed localised text.

GRACEFUL FIRST, HARD AFTER. A server that wrote a shutdown token for this
start into `<brain>/.mentis.serve.json` is asked to stop through its
loopback shutdown endpoint (drain requests, close the store, checkpoint the
WAL, give up the Brain's locks). One that has no endpoint -- every release up
to a24c2f0 -- or does not finish in time is stopped hard: the server and its
descendants are terminated, as `taskkill /T /F` did. Either way "stopped"
is judged by the outcome (the process gone and the port free), never by
what a call returned.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

import psutil

# the endpoint, its token header and the file the token is written to; they
# live apart so the server imports without psutil
from mentis.serve_protocol import (  # noqa: F401
    SERVE_INFO, SHUTDOWN_HEADER, SHUTDOWN_PATH)

#: addresses a local server listens on: loopback, or every interface
_LOCAL = {"127.0.0.1", "0.0.0.0", "::1", "::"}


def listening() -> dict[int, int | None] | None:
    """Local TCP ports in LISTEN with the pid owning each, or None when the
    machine could not be asked (which callers must treat as unknown). A pid
    of None is a listener the OS would not name an owner for (another
    user's, on Linux): never taken to be a Mentis server we may stop."""
    try:
        conns = psutil.net_connections(kind="tcp")
    except psutil.AccessDenied:
        # macOS answers only root for the whole machine; this user's own
        # processes can still be asked one by one.
        return _listening_own()
    except Exception:                                     # noqa: BLE001
        return None
    ports: dict[int, int | None] = {}
    for c in conns:
        if (c.status == psutil.CONN_LISTEN and c.laddr
                and c.laddr.ip.split("%")[0] in _LOCAL):
            if ports.get(c.laddr.port) is None:
                ports[c.laddr.port] = c.pid
    return ports


def _listening_own() -> dict[int, int | None] | None:
    ports: dict[int, int | None] = {}
    try:
        for p in psutil.process_iter():
            try:
                for c in p.net_connections(kind="tcp"):
                    if (c.status == psutil.CONN_LISTEN and c.laddr
                            and c.laddr.ip.split("%")[0] in _LOCAL):
                        ports.setdefault(c.laddr.port, p.pid)
            except (psutil.AccessDenied, psutil.NoSuchProcess,
                    psutil.ZombieProcess):
                continue
    except Exception:                                     # noqa: BLE001
        return None
    return ports


def _pythons() -> set[int] | None:
    """Pids of Python processes -- the only ones that can be a Mentis server,
    so the only ports worth asking. None when it cannot be told."""
    try:
        pids = set()
        for p in psutil.process_iter(["name"]):
            name = (p.info.get("name") or "").lower()
            if name.startswith("python"):
                pids.add(p.pid)
        return pids
    except Exception:                                     # noqa: BLE001
        return None


def probe(port: int, timeout: float = 2.0) -> tuple[str, dict | None]:
    """("mentis", identity), ("other", None) for anything that answered and
    is not a Mentis server, or ("unknown", None) when nothing could be told
    (no answer in time, connection refused or reset)."""
    import urllib.error
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/server",
                                    timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as exc:
        # A 4xx answered as something else; a 5xx may be a Mentis server
        # failing, which is not the same as not being one.
        return ("other" if exc.code < 500 else "unknown"), None
    except Exception:                                     # noqa: BLE001
        return "unknown", None
    try:
        d = json.loads(body.decode("utf-8"))
        return "mentis", {"port": port, "pid": d["process"]["pid"],
                          "started_at": d["process"]["started_at"],
                          "code": d["code"]["repository"],
                          "commit": d["code"].get("commit"),
                          "ui": (d.get("ui") or {}).get("built_from"),
                          "corpus": d.get("corpus"),
                          # None from a repository and from releases made
                          # before RELEASE.json existed
                          "release": d.get("release")}
    except Exception:                                     # noqa: BLE001
        return "other", None


def identity(port: int, timeout: float = 2.0) -> dict | None:
    """What answers on this port, if it is a Mentis server; else None."""
    return probe(port, timeout)[1]


def _inside(path: str, root: str) -> bool:
    p = os.path.normcase(os.path.realpath(path))
    r = os.path.normcase(os.path.realpath(root))
    return p == r or p.startswith(r.rstrip("\\/") + os.sep)


def serving_from(root: str) -> list[dict] | None:
    """Every Mentis server whose imported code lives in `root`, or None when
    that cannot be established (ports unknown, or a Python listener that did
    not answer)."""
    ports = listening()
    if ports is None:
        return None
    pythons = _pythons()
    found = []
    for port, pid in sorted(ports.items()):
        if pid is None or (pythons is not None and pid not in pythons):
            continue
        what, who = probe(port)
        if what == "other":
            continue
        if what == "unknown":
            if pythons is not None:
                return None     # a Python listener that would not say what it is
            continue
        if who["pid"] == pid and who["code"] and _inside(who["code"], root):
            found.append(who)
    return found


def _alive(pid: int) -> bool:
    """Whether a process with this pid is still running. A zombie (exited,
    not yet reaped) is not running. Doubt -- the OS refusing to say -- never
    reads as "stopped"."""
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True
    except Exception:                                     # noqa: BLE001
        return psutil.pid_exists(pid)


def _process(who: dict) -> psutil.Process | None:
    """The OS's process for this identity, or None when the pid now names a
    different process: one created AFTER the server said it started cannot
    be it (pid reuse). psutil keeps that check on every later call too."""
    try:
        p = psutil.Process(who["pid"])
        created = p.create_time()
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return None
    started = who.get("started_at")
    if isinstance(started, (int, float)) and created > started + 2:
        return None
    return p


def _terminate(who: dict, grace_s: float = 5) -> str:
    """Stop this server and its descendants hard. Returns what was done, for
    a failure report; never decides the outcome.

    The descendants are listed first, because once the server is gone its
    children can no longer be found through it. Each is asked to terminate
    (SIGTERM on POSIX; on Windows terminate is already TerminateProcess),
    and whatever is still there after `grace_s` is killed. A descendant that
    refuses (the console host a CREATE_NO_WINDOW server owns may) is reported
    and does not decide whether the server stopped."""
    p = _process(who)
    if p is None:
        return f"pid {who['pid']} is no longer the server that answered"
    try:
        kids = p.children(recursive=True)
    except psutil.Error:
        kids = []
    said = []
    procs = [p, *kids]
    for q in procs:
        try:
            q.terminate()
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as exc:
            said.append(f"terminate pid {q.pid}: {type(exc).__name__}")
    _gone, left = psutil.wait_procs(procs, timeout=grace_s)
    for q in left:
        try:
            q.kill()
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as exc:
            said.append(f"kill pid {q.pid}: {type(exc).__name__}")
    if left:
        psutil.wait_procs(left, timeout=grace_s)
    return "; ".join(said)


def shutdown_token(who: dict) -> tuple[str | None, str | None]:
    """(token, None) when the Brain this server says it serves holds a
    shutdown token written by THIS process for THIS start; else (None, why).
    Releases up to a24c2f0 write no token: they are stopped hard."""
    corpus = who.get("corpus")
    if not corpus:
        return None, "the server does not say which Brain it serves"
    try:
        with open(os.path.join(corpus, SERVE_INFO), encoding="utf-8") as fh:
            info = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, f"no readable {SERVE_INFO} ({type(exc).__name__})"
    if info.get("pid") != who["pid"] or info.get("port") not in (
            None, who["port"]):
        return None, (f"{SERVE_INFO} names pid {info.get('pid')} on port "
                      f"{info.get('port')}, not this server")
    token = info.get("token")
    if not token:
        return None, "this server wrote no shutdown token (an older release)"
    return token, None


def request_shutdown(port: int, token: str, timeout: float = 10
                     ) -> tuple[int | None, str]:
    """POST the shutdown endpoint on 127.0.0.1:port. (HTTP status, what was
    said), or (None, why) when nothing answered."""
    import urllib.error
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{SHUTDOWN_PATH}", data=b"", method="POST",
        headers={SHUTDOWN_HEADER: token,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:                              # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def _gone(who: dict, wait_s: float) -> tuple[bool, bool, dict | None]:
    """Wait up to `wait_s` for the pid to end AND the port to be free.
    (alive, held, ports) as last seen."""
    deadline = time.time() + wait_s
    while True:
        alive = _alive(who["pid"])
        ports = listening()
        held = ports is None or who["port"] in ports
        if not alive and not held:
            return False, False, ports
        if time.time() >= deadline:
            return alive, held, ports
        time.sleep(0.25)


def stop_server(who: dict, wait_s: float = 30, *, graceful: bool = True,
                graceful_s: float = 90) -> dict:
    """Stop exactly this server and wait until it is gone.

    {"stopped": bool, "how": "graceful" | "hard" | None, "why": str | None,
     "graceful_why_not": str | None}. Graceful when the server has a token
    and finishes within `graceful_s`; otherwise hard, judged within `wait_s`.
    """
    now = identity(who["port"], timeout=5)
    ports = listening()
    out = {"stopped": False, "how": None, "why": None,
           "graceful_why_not": None}
    if not now or (now["pid"], now["started_at"], now["code"]) != (
            who["pid"], who["started_at"], who["code"]):
        out["why"] = (f":{who['port']} no longer answers as pid {who['pid']} "
                      f"started at {who['started_at']} from {who['code']}; "
                      "nothing stopped")
        return out
    if ports is None or ports.get(who["port"]) != who["pid"]:
        out["why"] = (f"pid {who['pid']} answers on :{who['port']} but the "
                      "system does not show it owning that port (a proxy?); "
                      "nothing stopped")
        return out
    if _process(who) is None:
        out["why"] = (f"pid {who['pid']} was created after the server on "
                      f":{who['port']} said it started; nothing stopped")
        return out
    if graceful:
        token, why = shutdown_token({**who, "corpus": now.get("corpus")
                                     or who.get("corpus")})
        if token:
            code, said = request_shutdown(who["port"], token)
            if code == 202:
                alive, held, _ = _gone(who, graceful_s)
                if not alive and not held:
                    out.update(stopped=True, how="graceful")
                    return out
                why = (f"accepted the shutdown but after {graceful_s:g}s "
                       f"{'is still running' if alive else 'still listens'}")
            else:
                why = (f"the shutdown endpoint answered {code}: {said[:200]}"
                       if code else f"the shutdown endpoint: {said}")
        out["graceful_why_not"] = why
    try:
        said = _terminate(who)
    except Exception as exc:                              # noqa: BLE001
        said = f"could not ask pid {who['pid']} to stop: {exc}"
    alive, held, ports = _gone(who, wait_s)
    if not alive and not held:
        time.sleep(1)           # let the process release its handles
        out.update(stopped=True, how="hard")
        return out
    left = [w for w, bad in ((f"pid {who['pid']} is still running", alive),
                             (f":{who['port']} still listens"
                              if ports is not None else
                              f"cannot tell whether :{who['port']} is free",
                              held)) if bad]
    out["why"] = (f"pid {who['pid']} was told to stop but after {wait_s:g}s "
                  f"{' and '.join(left)}" + (f"; {said}" if said else ""))
    return out


def stop(who: dict, wait_s: float = 30) -> str | None:
    """Stop exactly this server and wait until it is gone. None when it is;
    otherwise why not. Graceful where the server offers it, hard otherwise
    (`stop_server`)."""
    return stop_server(who, wait_s)["why"]
