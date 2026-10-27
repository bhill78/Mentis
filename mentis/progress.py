"""`--progress jsonl`: what install, update, start and stop say, one JSON line
per step, for a program to read (the desktop app's progress screen).

THE LINE (installer plan adm-06dbd34701bf, S4; frozen, a parallel Builder
reads it):

    {"step": "<id>", "state": "running" | "done" | "failed", "message": "..."}

One object per line on stdout, ASCII (`ensure_ascii`), flushed at once. A
step is announced `running` and then ends `done` or `failed`; a step that
needs no work may be reported `done` only. `message` is plain words for a
person. The final `--json` result, when asked for, is ONE more line on
stdout: a JSON object with no "step" key.

THE OUTCOME (shared interface I1/I2; the desktop app reads exactly this).
Every command's final `--json` result carries

    {"outcome": "ok" | "unhealthy" | "refused" | "failed" | "needs_attention",
     "reason": "<a short machine word>", "message": "<plain English>", ...}

and its exit status is the outcome's: 0 ok, 1 ONLY installed (or running)
but not healthy, 2 refused, 3 failed -- any unexpected exception included,
caught at the command's top level with the result still printed -- and 4
needs attention (an update stopped and needs a decision or a resume).
`outcome_doc` makes the three keys, `EXIT` maps an outcome to its status.

With `--progress jsonl` the words a person would read go to stderr, so stdout
carries JSON lines and nothing else. Without it nothing changes: the words go
to stdout as before and no progress line is written.

Stdlib only: the installer imports this from inside the package zip.
"""

from __future__ import annotations

import json
import sys

JSONL = "jsonl"
MODES = (JSONL,)
RUNNING, DONE, FAILED = "running", "done", "failed"

#: the outcomes of I2, and the exit status of each (I1)
OK, UNHEALTHY, REFUSED = "ok", "unhealthy", "refused"
FAILED_OUTCOME, NEEDS_ATTENTION = "failed", "needs_attention"
EXIT = {OK: 0, UNHEALTHY: 1, REFUSED: 2, FAILED_OUTCOME: 3,
        NEEDS_ATTENTION: 4}
OUTCOME_OF = {v: k for k, v in EXIT.items()}


def outcome_doc(outcome: str, reason: str, message: str, **more) -> dict:
    """The three keys every final result carries (I2), then `more`."""
    if outcome not in EXIT:
        raise ValueError(f"no outcome {outcome!r}")
    return {"outcome": outcome, "reason": str(reason), "message": str(message),
            **more}

_mode: str | None = None
#: the step announced `running` and not yet ended, for `fail`
_open: str | None = None
#: the step of the last line
_last: str | None = None


def configure(mode: str | None) -> None:
    """Set the mode for this process (None: off)."""
    global _mode, _open, _last
    if mode not in (None, *MODES):
        raise ValueError(f"--progress {mode!r}: the only mode is {JSONL}")
    _mode, _open, _last = mode, None, None


def last_step() -> str | None:
    """The step of the last line reported (None before any)."""
    return _last


def mode() -> str | None:
    return _mode


def on() -> bool:
    return _mode == JSONL


def argv() -> list:
    """The flag to hand a child process so it reports the same way."""
    return ["--progress", _mode] if _mode else []


def emit(step: str, state: str, message: str = "") -> None:
    """One progress line, when progress is on."""
    global _open, _last
    _open = step if state == RUNNING else (None if step == _open else _open)
    _last = step
    if _mode != JSONL:
        return
    line = json.dumps({"step": step, "state": state, "message": str(message)},
                      ensure_ascii=True)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def fail(message: str, step: str) -> None:
    """End the step still running as `failed` -- or, when none is, report
    `step` failed -- so a refusal or a failure always ends on a line."""
    emit(_open or step, FAILED, message)


def say(msg: str = "") -> None:
    """Words for a person: stdout, or stderr when stdout carries JSON lines."""
    print(msg, file=sys.stderr if on() else sys.stdout, flush=True)


def result(doc, *, indent=1) -> None:
    """The final `--json` result: one line when progress is on, as before
    otherwise."""
    if on():
        sys.stdout.write(json.dumps(doc, default=str, ensure_ascii=True) + "\n")
        sys.stdout.flush()
    else:
        print(json.dumps(doc, indent=indent, default=str))


def utf8_streams() -> None:
    """stdout and stderr as UTF-8 whatever the console or pipe would pick.
    A program started with `-I` ignores PYTHONIOENCODING, and a pipe on
    Windows otherwise gets the ANSI code page, which cannot write every
    path a profile may have. Only entry points call this."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            pass
