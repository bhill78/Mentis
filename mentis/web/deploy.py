"""Arming a deploy of merged work: recorded here, performed outside.

THE OWNER'S STANDING RULE: merged means deployed. Work merged into main is
deployed to the day-to-day server as part of the same piece of work, without
asking, and if runs are going the deploy waits for them instead of asking.
A run cannot do that itself -- the server it would stop is the one it runs
inside -- so this ARMS it: checks the commit, records `deploy-armed`, writes
`<home>/restart-<sha12>/armed.json`, copies the supervisor out of the merged
commit beside it and starts it DETACHED from this server and from any job
it is in. The supervisor (`tools/deploy_supervisor.py`) waits until no run
is held, swaps, checks, rolls back on failure and writes `result.json`.

REFUSED, writing nothing, when: no repository is configured; the commit is
not one; it is not contained in `main`; the running server already
contains it (a downgrade); it predates the supervisor; or a deploy of it is
already armed -- which only its `armed.json` says. Whoever arms it is the owner, or a run whose
work the owner asked for and granted `coordinate` (`worker.arm_deploy`).
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import threading
import time

ARMED = "deploy-armed"
SUPERVISOR = "tools/deploy_supervisor.py"
_LOCK = threading.Lock()


class Refused(ValueError):
    pass


def home_of(st) -> pathlib.Path:
    """Where restart directories and releases live: `MENTIS_DEPLOY_HOME`, or
    the directory the Brain is in (the live Brain is `<Mark-IV>/brain`)."""
    said = os.environ.get("MENTIS_DEPLOY_HOME")
    return pathlib.Path(said) if said else pathlib.Path(st.path).parent


def port_of(st) -> int | None:
    port = (getattr(st, "answers_at", None) or "").rpartition(":")[2]
    port = port.strip("/")
    return int(port) if port.isdigit() else None


def _git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def clean_env() -> dict:
    e = {k: v for k, v in os.environ.items()
         if not (k.upper().startswith(("CLAUDE", "CODEX"))
                 or k.upper() == "PYTHONPATH")}
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def spawn_detached(cmd, cwd) -> int:
    """Start `cmd` so that nothing ending this server ends it: its own
    process group, no console, out of this process's job where the job
    allows that. Returns its pid."""
    kw = {}
    if os.name == "nt":
        flags = (0x00000008                      # DETACHED_PROCESS
                 | subprocess.CREATE_NEW_PROCESS_GROUP
                 | 0x01000000)                   # CREATE_BREAKAWAY_FROM_JOB
        kw["creationflags"] = flags
    else:
        kw["start_new_session"] = True
    # The child has its own handle once started; this one is closed here so
    # the server does not hold the file open for the supervisor's life.
    with open(pathlib.Path(cwd) / "supervisor.out", "ab") as out:
        try:
            p = subprocess.Popen(cmd, cwd=cwd, env=clean_env(), stdout=out,
                                 stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, close_fds=True,
                                 **kw)
        except OSError:
            if os.name != "nt":
                raise
            # A job that forbids breakaway refuses the whole start; detached
            # and in its own group is the most that job allows.
            kw["creationflags"] &= ~0x01000000
            p = subprocess.Popen(cmd, cwd=cwd, env=clean_env(), stdout=out,
                                 stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, close_fds=True,
                                 **kw)
    return p.pid


def running_commit() -> str | None:
    """The commit this server process started from, or None."""
    try:
        from mentis.web import identity
        return (identity._START.get("code") or {}).get("commit")
    except Exception:                                     # noqa: BLE001
        return None


def arm(st, commit, *, by, execution=None, runtime=None, caused_by=None,
        conversation=None, spawn=None, dry_run=False,
        written_by=None) -> dict:
    """Arm the supervised deploy of `commit`. Returns what was armed, or
    raises `Refused` with the reason and nothing written."""
    cv, repo = st.cv, getattr(st, "repository", None)
    commit = str(commit or "").strip()
    if not commit:
        raise Refused("name the merged commit to deploy")
    if not repo:
        raise Refused("this Mentis has no repository configured "
                      "(--repository), so there is no main to deploy from")
    got = _git(repo, "rev-parse", "--verify", "--quiet", commit + "^{commit}")
    sha = got.stdout.strip()
    if got.returncode or not sha:
        raise Refused(f"{commit!r} is not a commit of {repo}")
    if _git(repo, "merge-base", "--is-ancestor", sha, "main").returncode:
        raise Refused(f"{sha[:12]} is not contained in main: merged means "
                      "deployed, and this is not merged")
    # FORWARD ONLY. What this server runs must be contained in the commit
    # deployed, and not be it: anything else drops work. That includes a
    # feature tip merged into main AFTER the running commit, which is in
    # main and still not ahead of what runs (found by review). A running
    # commit this repository cannot place is refused too: forward cannot
    # be shown.
    running = running_commit()
    if not running:
        raise Refused("this server cannot say which commit it runs, so a "
                      "deploy cannot be shown to go forward")
    if running == sha:
        raise Refused(f"{sha[:12]} is what this server already runs")
    if _git(repo, "merge-base", "--is-ancestor", running, sha).returncode:
        raise Refused(f"what this server runs ({running[:12]}) is not "
                      f"contained in {sha[:12]}; deploying it would go "
                      "backwards or sideways and drop work")
    script = _git(repo, "show", f"{sha}:{SUPERVISOR}")
    if script.returncode:
        raise Refused(f"{sha[:12]} predates {SUPERVISOR}; it cannot be "
                      "deployed by a supervisor it does not carry")
    port = port_of(st)
    if not port:
        raise Refused("this server does not know which port it answers on")
    here = home_of(st) / f"restart-{sha[:12]}"
    with _LOCK:
        # ONLY `armed.json` MEANS ARMED: a folder made by hand, or one a
        # refused arming left, is not an arming.
        if (here / "armed.json").exists():
            raise Refused(f"a deploy of {sha[:12]} is already armed "
                          f"({here / 'armed.json'})")
        here.mkdir(parents=True, exist_ok=True)
        writable = list(getattr(st, "writable", ()) or ())
        cmd = [sys.executable, str(here / "supervise.py"),
               "--commit", sha, "--port", str(port), "--corpus", st.path,
               "--repository", repo, "--home", str(home_of(st))]
        for w in writable:
            cmd += ["--writable-root", w]
        if dry_run:
            cmd.append("--dry-run")
        armed = {"commit": sha, "port": port, "corpus": st.path,
                 "repository": repo, "writable": writable, "by": by,
                 "written_by": written_by, "running": running,
                 "armed_at": time.time(), "command": cmd}
        (here / "supervise.py").write_text(script.stdout, "utf-8")
        (here / "spawn-failed.json").unlink(missing_ok=True)
        (here / "armed.json").write_text(json.dumps(armed, indent=1),
                                         "utf-8")
        # A SUPERVISOR THAT NEVER STARTED IS NOT ARMED: `armed.json` goes,
        # so it neither blocks arming again nor reads as pending to another
        # supervisor; what happened is kept beside it.
        try:
            pid = (spawn or spawn_detached)(cmd, str(here))
        except Exception as exc:                          # noqa: BLE001
            (here / "armed.json").unlink(missing_ok=True)
            (here / "spawn-failed.json").write_text(json.dumps(
                {**armed, "error": repr(exc), "at": time.time()}, indent=1),
                "utf-8")
            raise Refused(f"the supervisor could not be started ({exc}); "
                          "nothing is armed")
        act = cv.record_act(
            actor=by, act=ARMED, conversation=conversation,
            execution=execution, runtime=runtime, caused_by=caused_by,
            because=f"merged into main; deployed to :{port} by a supervisor "
                    "once no run is held",
            detail={"commit": sha, "port": port, "dir": str(here),
                    "dry_run": bool(dry_run), "running": running,
                    "pid": pid,
                    "written_by": written_by or (
                        f"{runtime}/{(execution or '')[:8]}" if runtime
                        else None)})
        (here / "armed.json").write_text(json.dumps(
            {**armed, "act": act, "pid": pid}, indent=1), "utf-8")
    return {"ok": True, "armed": str(here), "act": act, "commit": sha,
            "port": port, "pid": pid,
            "note": (f"armed. The supervisor (pid {pid}) waits until "
                     f":{port} holds no run -- this one included -- then "
                     "swaps, checks and rolls back on failure. Its outcome "
                     f"is written to {here / 'result.json'}; until then the "
                     "deploy is NOT done.")}
