"""A lost run's final message, found and read by the server that records it.

A `result-recovered` act (see `Conversation.recover_result`) says: this run
finished, Mentis did not see it end, and this is what the runtime wrote. The
server establishes that ITSELF. The caller supplies neither a path nor any
text -- only which run -- so nothing here can be steered at a file the caller
chose, and nothing here can confirm a guess about a file's contents.

WHERE THE EVIDENCE IS, COMPUTED RATHER THAN ACCEPTED. Every dispatched run works
in `<corpus>/scratch/<execution>` (`mentis.foundation.scratch`), and the Claude
runtime files that directory's sessions under one folder
(`claude.transcript_folder`). Only that folder is read, and only a session
file that records that exact directory as a working directory counts -- the
folder name alone is lossy.

WHICH RECORDS ARE THIS RUN'S. Execution ids are reused and one session file
holds several runs, so a file is never evidence as a whole. The run is the
window from its own `execution-started` to the next start on the same
execution (or, if there is none, to the end of the file). Inside that window
there must be exactly one prompt -- a user message that is not a tool result,
not a runtime-injected meta record, not a compaction summary, and not a turn
the runtime started itself -- and the run's last assistant message after it
must have ended its turn (`stop_reason: end_turn`). Its text blocks, in order,
are the result.

WHEN A RUN COUNTS AS STOPPED -- the owner's rule. A runtime that is still alive
can end a turn and then carry on (a background task finishing wakes it), so an
`end_turn` alone is not an ending. Two further things are required, both
observed here, now:
  * NO PROCESS on this machine names the run's execution id or session id in
    its command line. Every Claude run's Mentis tool worker is started with
    its scratch path, which contains the execution id; a resumed session's
    runtime names its session. If the process table cannot be read, that is
    refused -- "could not look" is not "nothing there".
  * THE SESSION HAS BEEN QUIET for `QUIET_S` (30 minutes): nothing written
    to its transcript, to anything under `<session>/` beside it (subagents,
    tool results), or to the runtime's temp output for the session
    (background tasks), and no record stamped, for that long. An agent that means to
    stay alive through a long wait has to keep showing activity; one that has
    shown none for this long is taken as stopped.

Anything short of all of that is refused, not recorded weaker.

WHAT IS CHECKED AND WHAT IS NOT. Checked here, now, and recorded under
`checked`: the file's path, hash and size, the session it names, the prompt
and final message inside the window, that the final message ended its turn,
how long the transcript has been quiet, and that no process names the run. NOT
established, and recorded as such: that the runtime exited cleanly rather than
being killed, and why Mentis lost the waiter -- the recoverer's `because`.

ONE RUNTIME. Only Claude's transcript is read. Any other runtime is refused
with the reason, rather than guessed at.
"""

from __future__ import annotations

import datetime as _dt
import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

from mentis.foundation import scratch
from mentis.foundation.runtimes import claude as _claude

SUPPORTED = ("claude",)

#: How long a run's transcript must have been silent before the run is taken
#: as stopped. The owner's figure: about thirty minutes, because some test
#: suites run for a long time without an agent writing anything.
QUIET_S = 30 * 60


def _epoch(stamp):
    """A transcript timestamp as epoch seconds. One with no zone is read as
    UTC, which is what the runtime writes (every observed stamp ends in Z)."""
    if not stamp:
        return None
    try:
        t = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return t.timestamp()


def _is_prompt(row) -> bool:
    """A user message that asked for work. Not a tool result, not a record the
    runtime injected (`isMeta`), not a side conversation, not the summary a
    compaction writes, and not a turn the runtime started ITSELF -- a
    background task finishing arrives as a `promptSource: system` turn with an
    `origin`, inside the same run."""
    if row.get("type") != "user" or row.get("isMeta") or row.get("isSidechain"):
        return False
    if row.get("isCompactSummary") or row.get("isVisibleInTranscriptOnly"):
        return False
    if row.get("promptSource") == "system" or row.get("origin"):
        return False
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if not isinstance(content, list) or not content:
        return False
    return all(isinstance(p, dict) and p.get("type") == "text" for p in content)


def _texts(row) -> list[str]:
    content = (row.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    return [p.get("text", "") for p in content
            if isinstance(p, dict) and p.get("type") == "text"
            and p.get("text", "").strip()]


def _read(path):
    """(raw bytes, [(line number, parsed row)], [unparsed line numbers]).

    A torn line is what a killed writer leaves, and a later `--resume` of the
    same session appends after it -- so one can sit anywhere in a file. Whether
    it matters is decided by the caller: only one INSIDE the run being read
    does."""
    with open(path, "rb") as fh:
        raw = fh.read()
    # ON NEWLINE BYTES ONLY. `str.splitlines` also breaks on U+2028, U+2029
    # and other separators, which the runtime writes unescaped inside records,
    # so it tore valid records apart.
    lines = [ln.decode("utf-8", errors="replace").strip()
             for ln in raw.split(b"\n")]
    lines = [ln for ln in lines if ln]
    rows, bad = [], []
    for i, line in enumerate(lines):
        try:
            rows.append((i, json.loads(line)))
        except ValueError:
            # A BOOKKEEPING FRAGMENT IS TOLERATED ONLY AS THE FILE'S LAST LINE
            # AND ONLY IF NOTHING IS GLUED AFTER IT. A killed writer leaves one
            # with no newline; anything written later lands on the same line,
            # and a whole record hidden inside it must not be skipped.
            last = i == len(lines) - 1
            glued = line.count("{") > 1 or "}{" in line
            bad.append((i, _torn_type(line) if last and not glued else None))
    return raw, rows, bad


#: Record types that carry nothing a run SAID: the runtime's bookkeeping. A
#: torn line that still declares one of these cannot be the run's message.
BOOKKEEPING = frozenset({"cost-state", "last-prompt", "mode", "atis-latch",
                         "summary", "file-history-snapshot"})


def _torn_type(line):
    """The `type` a torn record still declares, if its start survived."""
    import re
    m = re.match(r'\s*\{\s*"type"\s*:\s*"([A-Za-z_-]+)"', line)
    return m.group(1) if m else None


def _default_processes() -> list[tuple[int, str]]:
    """(pid, command line) for every process this user can see. Raises if the
    process table cannot be read."""
    if sys.platform == "win32":
        # UTF-8 BOTH WAYS. Windows PowerShell 5.1 writes its console encoding,
        # which turns a typographic quote in somebody's command line into a
        # plain `"` AFTER ConvertTo-Json -- so the JSON broke whenever such a
        # process ran (measured 2026-10-08: an Antigravity run's prompt on its
        # argv), and with it every "is this run still alive?" answer.
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
             "Get-CimInstance Win32_Process | Select-Object ProcessId,"
             "CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, timeout=60, check=True).stdout
        rows = json.loads(out.decode("utf-8") or "[]")
        rows = rows if isinstance(rows, list) else [rows]
        return [(int(r["ProcessId"]), r.get("CommandLine") or "") for r in rows]
    out = subprocess.run(["ps", "-eo", "pid=,args="], capture_output=True,
                         text=True, timeout=60, check=True).stdout
    procs = []
    for line in out.splitlines():
        pid, _, args = line.strip().partition(" ")
        if pid.isdigit():
            procs.append((int(pid), args))
    return procs


class NoResult(ValueError):
    """The run left no finished result: no transcript of it, no reply to its
    prompt, or a last message that did not end its turn. Every other refusal
    is about what could not be established, not about what is not there."""


#: Replaced in tests. Everything else calls these through these names.
processes = _default_processes
clock = time.time


def _naming(needles) -> list[dict]:
    """Processes whose command line names any of `needles` (case-blind)."""
    try:
        procs = processes()
    except Exception as exc:                              # noqa: BLE001
        raise ValueError("the process table could not be read "
                         f"({type(exc).__name__}: {exc}), so whether this "
                         "run's runtime is still alive cannot be said") from exc
    wanted = [n.lower() for n in needles if n]
    me = os.getpid()
    return [{"pid": pid, "names": [n for n in wanted if n in cmd.lower()],
             "command": cmd}
            for pid, cmd in procs
            if pid != me and any(n in cmd.lower() for n in wanted)]


def final_message(record, *, execution, runtime, since, until=None,
                  now=None, require_quiet=True) -> dict:
    """This run's final message and the evidence it rests on.

    `since` is the run's own start (`at` of its `execution-started`), `until`
    the next start on the same execution, or None. Raises ValueError, with the
    reason, whenever the evidence does not establish exactly one answer, or
    does not establish that the run has stopped.
    """
    if runtime not in SUPPORTED:
        raise ValueError(f"recovery reads only {', '.join(SUPPORTED)} "
                         f"transcripts; this run was on {runtime!r}")
    now = clock() if now is None else now
    workspace = str(scratch.path_for(record, execution))
    folder = os.path.join(_claude._transcripts(),
                          _claude.transcript_folder(workspace))
    here = os.path.normcase(workspace)

    def ours(row):
        at = _epoch(row.get("timestamp"))
        return (at is not None and at > since
                and (until is None or at < until))

    found = []
    for path in sorted(glob.glob(os.path.join(folder, "*.jsonl"))):
        raw, numbered, bad = _read(path)
        rows = [r for _, r in numbered]
        # RECORDED FROM THIS RUN'S WORKSPACE, the same test `--resume`
        # eligibility applies. Not per record: a record's `cwd` follows the
        # run's shell, so a run that worked in the project records that
        # directory on the rest. A file that is not this workspace's is
        # skipped whatever state it is in.
        if not any(os.path.normcase(str(r.get("cwd") or "")) == here
                   for r in rows):
            continue
        inside = [(i, r) for i, r in numbered if ours(r)]
        if not inside:
            continue
        window = [r for _, r in inside]
        # A LINE THAT DOES NOT PARSE FROM THIS RUN'S FIRST RECORD UNTIL THE
        # NEXT RUN'S FIRST RECORD -- or the end of the file, if none -- could
        # be this run's own: most likely its LAST, torn by a kill, and then an
        # earlier message would be taken for its final one. So it refuses. One
        # before the run belongs to an earlier run and does not.
        first = inside[0][0]
        after = [i for i, r in numbered
                 if until is not None and i > first
                 and (_epoch(r.get("timestamp")) or 0) >= until]
        end = after[0] if after else None
        # A torn line that still says it is bookkeeping -- the usual thing a
        # kill leaves at the tail -- cannot be what the run said; one that
        # says it is a message, or says nothing, can.
        within = [i for i, kind in bad
                  if i > first and (end is None or i < end)
                  and kind not in BOOKKEEPING]
        if within:
            raise ValueError(f"{len(within)} records inside this run's part of "
                             "its transcript do not parse, so what it said "
                             "cannot be established")
        found.append((path, raw, rows, window, len(bad)))
    if not found:
        raise NoResult("no transcript of this run's workspace holds records "
                       "of this run's window")
    if len(found) > 1:
        raise ValueError(f"{len(found)} transcripts hold records of this run's "
                         "window, so which is this run's cannot be said")
    path, raw, rows, window, unparsed = found[0]
    prompts = [r for r in window if _is_prompt(r)]
    if len(prompts) != 1:
        raise ValueError(f"this run's window holds {len(prompts)} prompts, not "
                         "one, so which reply is this run's cannot be said")
    prompt = prompts[0]
    after = window[window.index(prompt) + 1:]
    replies = [r for r in after if r.get("type") == "assistant"
               and not r.get("isSidechain")]
    if not replies:
        raise NoResult("no assistant message follows this run's prompt")
    last = replies[-1]
    msg = last.get("message") or {}
    if msg.get("stop_reason") != "end_turn":
        raise NoResult("this run's last assistant message did not end its "
                       f"turn (stop_reason {msg.get('stop_reason')!r}); it "
                       "may still be running or may have been cut off")
    # ONE MESSAGE MAY SPAN SEVERAL RECORDS, one per content block. Separate
    # text blocks are kept apart, never run together.
    parts = [r for r in replies if (r.get("message") or {}).get("id")
             == msg.get("id")] if msg.get("id") else [last]
    said = "\n\n".join(t for r in parts for t in _texts(r)).strip()
    if not said:
        raise ValueError("this run's final message holds no text")
    sessions = {r.get("sessionId") for r in window if r.get("sessionId")}
    session = os.path.splitext(os.path.basename(path))[0]
    if sessions != {session}:
        raise ValueError(f"this run's transcript names sessions "
                         f"{sorted(sessions)}, not only {session}")

    # -- has it STOPPED? ---------------------------------------------------
    # ACTIVITY ANYWHERE IN THE SESSION COUNTS, not only in its main file: the
    # runtime writes subagents, tool output and task output under
    # `<session>/`, and a run whose main transcript is silent while a
    # background agent it started keeps writing has not stopped.
    stamps = [t for t in (_epoch(r.get("timestamp")) for r in rows)
              if t is not None]
    beside = []
    for top in (os.path.join(folder, session),
                # BACKGROUND TASK OUTPUT IS NOT UNDER THE SESSION FOLDER: the
                # runtime writes it to its temp directory, keyed the same way.
                os.path.join(tempfile.gettempdir(), "claude",
                             _claude.transcript_folder(workspace), session)):
        for root, _dirs, files in os.walk(top):
            for f in files:
                try:
                    beside.append(os.path.getmtime(os.path.join(root, f)))
                except OSError:
                    pass
    last_written = max([os.path.getmtime(path)] + stamps + beside)
    quiet = now - last_written
    # `require_quiet=False` ONLY WHERE STOPPING IS PROVEN ANOTHER WAY: the
    # wake check, for a run the machine has rebooted since (`mentis.wakecheck`).
    if require_quiet and quiet < QUIET_S:
        raise ValueError(f"this run's transcript was written {int(quiet)}s "
                         f"ago; a run is taken as stopped only after "
                         f"{QUIET_S // 60} minutes with no activity")
    # BY THE EXECUTION AND SESSION IDS, NOT A PATH. The run's Mentis tool
    # worker carries its scratch path, but `repr`-escaped (doubled backslashes
    # on Windows), so a path compared as written never matched it. Both ids
    # are UUIDs that appear however the path around them is spelled; a
    # resumed runtime names its session.
    alive = _naming([execution, session])
    if alive:
        raise ValueError(
            f"{len(alive)} process(es) on this machine still name this run's "
            "execution or session, so it has not stopped: "
            + "; ".join(f"pid {p['pid']} ({p['command'][:80]})"
                        for p in alive))

    return {
        "said": said,
        "session": session,
        "evidence": {
            "source": path,
            "checked": {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw),
                "unparsed_lines_tolerated": unparsed,
                "session": session,
                "workspace": workspace,
                "window": {"since": since, "until": until,
                           "records": len(window)},
                "prompt": {"uuid": prompt.get("uuid"),
                           "at": prompt.get("timestamp")},
                "final_message": {"id": msg.get("id"),
                                  "uuids": [r.get("uuid") for r in parts],
                                  "at": last.get("timestamp"),
                                  "stop_reason": msg.get("stop_reason")},
                "quiet_for_s": int(quiet),
                "quiet_includes": "the session file, its records' stamps, "
                                  "everything under <session>/ beside it, "
                                  "and the runtime's temp output for the "
                                  "session (background task output)",
                "quiet_required_s": QUIET_S,
                "processes_naming_run": 0,
                "checked_at": now,
                "checked_by": "the server that recorded this act",
            },
            "not_established": [
                "that the runtime exited cleanly rather than being killed: "
                "what is checked is that it ended its turn, has been silent "
                f"for {QUIET_S // 60}+ minutes, and no process names it",
                "processes this server cannot see the command line of -- "
                "another user's, or an elevated one -- are not checked",
                "background task output is looked for under THIS server's "
                "temp directory; a runtime writing elsewhere (another TEMP, "
                "CLAUDE_CODE_TMPDIR) is covered only by the process check",
                "why Mentis lost this run's waiter: that is the recoverer's "
                "account, in `because`"],
        },
    }
