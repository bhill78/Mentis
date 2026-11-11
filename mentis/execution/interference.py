"""WHO ENDED A RUNTIME: commands that terminate processes BY NAME, matched to a run that died.

DAY-TO-DAY incident 2026-11-11 (conversation ent-e05dcf622c97). A Builder stopped its own
Vite server with `taskkill //F //IM node.exe //T`; a retry of it with `Get-Process node |
Stop-Process -Force`. Every claude-agent-acp backend is a `node.exe`, so the runtimes of
other agents' runs died with it, and each was recorded only as "backend 'claude' exited
with code 1" (or -1). The carrier read that as infrastructure flakiness and dispatched the
same work again -- which did it again.

This module finds, for a run whose runtime exited (`backend_exited`), a RECORDED command
that terminates processes by an image name the run's runtime process has, run shortly
before the exit, by this run or another one. It reports what the record holds -- the
command, who ran it, when -- and names the coincidence for what it is: the command is
recorded, its effect on this process is not. It never infers anything from an exit alone,
and a command that stops processes by pid (`taskkill /PID`, `Stop-Process -Id`) is the
correct, owned way to stop something and is not a match.
"""

from __future__ import annotations

import fnmatch
import json
import re
from typing import Any

#: How far before the exit a command is looked for (seconds), and after (the observed
#: time of a call is when it was first seen; the kill lands a moment later).
BEFORE_S, AFTER_S = 30.0, 3.0

#: The process names each runtime's processes have on this machine (lower case, no
#: `.exe`). claude-agent-acp, codex-acp, gemini and kimi are started through node; the
#: local worker is Python. A runtime not listed matches nothing (nothing is assumed).
RUNTIME_IMAGES: dict[str, tuple[str, ...]] = {
    "claude": ("node", "claude"),
    "codex": ("node", "codex", "codex-acp"),
    "gemini": ("node", "gemini"),
    "kimi-k3": ("node", "kimi"),
    "antigravity": ("agy", "antigravity"),
    "local": ("python", "pythonw"),
}

_NAME = r"""["']?([\w.*\-]+(?:\s*,\s*[\w.*\-]+)*)["']?"""
#: taskkill /F /IM node.exe /IM python.exe (and //IM from a POSIX shell): every /IM of
#: each taskkill segment.
_TASKKILL = re.compile(r"taskkill\b[^|;&\n]*", re.I)
_IM = re.compile(r"(?:^|\s)[/-]{1,2}im\s+" + _NAME, re.I)
_PATTERNS = (
    # Stop-Process -Name node, spps -Name, kill -Name
    re.compile(r"\b(?:stop-process|spps|kill)\b[^|;\n]*?-name\s+" + _NAME, re.I),
    # Get-Process node ... | Stop-Process  /  | % { $_.Kill() }
    re.compile(r"\b(?:get-process|gps)\s+(?:-name\s+)?" + _NAME
               + r"[^\n;]*?\|\s*(?:stop-process|spps|kill\b|%\s*\{\s*\$_\.kill"
                 r"|foreach-object\s*\{\s*\$_\.kill)", re.I),
    # pkill node / killall node
    re.compile(r"\b(?:pkill|killall)\s+(?:-\S+\s+)*" + _NAME, re.I),
    # wmic process where name='node.exe' delete / call terminate
    re.compile(r"wmic\s+process\s+where\s+[\"(]*\s*name\s*=\s*'?([\w.*\-]+)'?"
               r"[^\n]*?(?:delete|terminate)", re.I),
    # Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Invoke-CimMethod -MethodName Terminate
    re.compile(r"win32_process[^\n|]*?name\s*=\s*'([\w.*\-]+)'[^\n]*?terminate", re.I),
)


def _norm(name: str) -> str:
    name = name.strip().strip("\"'").lower()
    return name[:-4] if name.endswith(".exe") else name


def killed_names(command: str) -> list[str]:
    """The process names `command` terminates by name (normalised), in order; [] if none."""
    if not isinstance(command, str) or not command:
        return []
    found = [m.group(1) for seg in _TASKKILL.finditer(command) for m in _IM.finditer(seg.group(0))]
    for pattern in _PATTERNS:
        found += [m.group(1) for m in pattern.finditer(command)]
    out: list[str] = []
    for got in found:
        for part in got.split(","):
            n = _norm(part)
            if n and n not in out:
                out.append(n)
    return out


def hits_runtime(names: list[str], runtime: str | None) -> list[str]:
    """Which of `names` (wildcards allowed) name a process of `runtime`."""
    images = RUNTIME_IMAGES.get((runtime or "").lower(), ())
    return [n for n in names if any(fnmatch.fnmatch(i, n) for i in images)]


def _calls_of(detail: Any) -> list[dict]:
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except ValueError:
            return []
    calls = (detail or {}).get("calls") if isinstance(detail, dict) else None
    return [c for c in calls or () if isinstance(c, dict)]


def find(reader, *, execution: str | None, runtime: str | None, ended_at: float,
         own_calls=()) -> dict | None:
    """The recorded command most likely to have terminated this run's runtime, or None.

    `reader` answers `acts(where, args)` (the record). `own_calls` are this run's own
    tool calls (`RunResult.tool_calls`), read first: a run that killed its own runtime
    is the plainest case. The newest matching command in the window wins."""
    lo, hi = ended_at - BEFORE_S, ended_at + AFTER_S
    found: list[dict] = []

    def consider(call: dict, who: str | None, who_runtime: str | None, act: str | None,
                 actor: str | None = None) -> None:
        title = call.get("title") or ""
        at = call.get("first_at")
        if not isinstance(at, (int, float)) or not (lo <= at <= hi):
            return
        names = killed_names(title)
        hit = hits_runtime(names, runtime)
        if hit:
            found.append({"execution": who, "runtime": who_runtime, "act": act,
                          "actor": actor, "command": title[:300], "at": at, "names": hit,
                          "self": bool(who and who == execution)})

    for c in own_calls or ():
        if isinstance(c, dict):
            # A run's own calls carry no time (`RunResult.tool_calls`): they are its
            # last acts before it ended, so they are taken as at its end.
            call = dict(c)
            call["first_at"] = c.get("first_at") or ended_at
            consider(call, execution, runtime, None)
    try:
        rows = reader.acts("act IN ('operations-observed', 'operation-answered') AND at >= ?",
                           (lo,))
    except Exception:                                     # noqa: BLE001
        rows = []
    for r in rows:
        r = dict(r)
        if r.get("act") == "operations-observed":
            for call in _calls_of(r.get("detail")):
                consider(call, r.get("execution"), r.get("runtime"), r.get("id"), r.get("actor"))
        else:
            d = r.get("detail")
            try:
                d = json.loads(d) if isinstance(d, str) else (d or {})
            except ValueError:
                d = {}
            op = d.get("operation") if isinstance(d, dict) else None
            title = (op or {}).get("title") if isinstance(op, dict) else d.get("title") if isinstance(d, dict) else None
            if title:
                consider({"title": title, "first_at": r.get("at")}, r.get("execution"),
                         r.get("runtime"), r.get("id"), r.get("actor"))
    if not found:
        return None
    best = max(found, key=lambda f: (f["at"], f["self"]))
    best["seconds_before_exit"] = round(ended_at - best["at"], 1)
    best["attribution"] = ("a recorded command that terminates processes by a name this "
                           "runtime's process has, run shortly before it exited; the record "
                           "holds the command, not its effect on this process")
    return best


def words(found: dict, *, alias: str | None = None) -> str:
    """One sentence for the failure record (`because`), and what it means for a retry."""
    names = ", ".join(f"`{n}`" for n in found["names"])
    cmd = found["command"].replace("\n", " / ")
    if found["self"]:
        return (f"its runtime was terminated by its own command `{cmd}`, which stops every "
                f"{names} process by name ({found['seconds_before_exit']}s before the exit); "
                f"the same work given the same way would do it again -- it must stop only "
                f"the processes it started (by pid)")
    who = alias or found.get("execution") or "another run"
    return (f"its runtime was terminated by a command of another run ({who}): `{cmd}` "
            f"stops every {names} process by name ({found['seconds_before_exit']}s before "
            f"the exit); this work did not fail on its own")
