"""Row J's allowed messages, read from `restart_messages.json`, decided whole.

`decide` says which entries a message matches, and row J's test fails on none. The cases a test
names are those it can truly be in: a B-sent reply isn't allowed to read as case A, because that
message says nothing was done.

A `NotPermitted` message can say anything, so its words decide nothing. Entry `Refused` matches
only on `Refusals`, the evidence from that same call: what Python answered it, and what the record
gained meanwhile. With no evidence it matches nothing.
"""

from __future__ import annotations

import json
import pathlib
import re
import sqlite3

LIST = json.loads(pathlib.Path(__file__).with_name("restart_messages.json")
                  .read_text(encoding="utf-8"))

#: What a placeholder may hold. Nothing else in a message varies.
PLACEHOLDERS = {
    "{via}": r"https?://[^\s/]+(?::\d+)?/?",
    "{name}": r"'[a-z_]+'",
    "{record}": r"'[^']+'",
    "{urlopen_error}": r"<urlopen error [^>]*>",
}

#: What `_over` reads of a 403's body, in characters (`worker.py:6697` at b8e324c).
OVER_READS = 1200
#: Each row's own clock, by table. Row J's server runs one Brain on one machine.
STAMPED = {"entry": "recorded_at", "operational": "at", "delivery": "at"}
#: Added to each end of a call's window, in seconds. Python's `time.time` on Windows moves in steps
#: of up to 15.6 ms, so a call's own row can read early. Errs toward "that call wrote".
WINDOW_PAD_S = 0.05


def _pattern(template: str) -> re.Pattern:
    parts = re.split("(" + "|".join(re.escape(p) for p in PLACEHOLDERS) + ")", template)
    return re.compile("".join(PLACEHOLDERS.get(p, re.escape(p)) for p in parts), re.DOTALL)


def told_for(body: str) -> str:
    """The message the worker makes of a 403's body: `_over`, then `serve`'s catch-all."""
    detail = body[:OVER_READS]
    try:
        said = json.loads(detail).get("error") or detail
    except (ValueError, AttributeError):
        said = detail
    return f"NotPermitted: {said}"


class Refusals:
    """The front's `worker-refusals.jsonl` for one run, and that run's copy of the Brain.

    `vouch` is true only when an unused line would make exactly this message, and the record gained
    no row while that call was in hand. Each line vouches for one message, so one call per message,
    in the order the agent saw them. `failed` says why any was not vouched for. No log is no lines:
    a run that was refused nothing writes none, and a message then has nothing behind it.
    """

    def __init__(self, log: pathlib.Path, db: pathlib.Path):
        self.db = pathlib.Path(db)
        self.failed: list[str] = []
        log = pathlib.Path(log)
        self.lines = ([json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
                      if log.exists() else [])
        for line in self.lines:
            if set(line) != {"received_at", "answered_at", "body"}:
                raise ValueError(f"not a line of {log}: {sorted(line)}")

    def _rows_written(self, line: dict) -> int:
        conn = sqlite3.connect(f"file:{self.db.as_posix()}?mode=ro", uri=True)
        try:
            return sum(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {at} BETWEEN ? AND ?",
                                    (line["received_at"] - WINDOW_PAD_S,
                                     line["answered_at"] + WINDOW_PAD_S)).fetchone()[0]
                       for table, at in STAMPED.items())
        finally:
            conn.close()

    def vouch(self, message: str) -> bool:
        for at, line in enumerate(self.lines):
            if told_for(line["body"]) == message:
                del self.lines[at]
                written = self._rows_written(line)
                if written:
                    self.failed.append(f"{written} rows written while refusing: {message}")
                return not written
        self.failed.append(f"Python answered no such refusal: {message}")
        return False


def decide(message: str, cases=None, refusals: Refusals | None = None) -> list[str]:
    """The agent-tool-error entries, of `cases` or of all, this whole message matches.

    `Refused` needs `refusals`, and asks it once, which uses a line: call this once per message."""
    entries = LIST["agent_tool_errors"]
    return [case for case in (cases or entries)
            if (message.startswith("NotPermitted: ") and refusals is not None
                and refusals.vouch(message)
                if case == "Refused"
                else _pattern(entries[case]["message"]).fullmatch(message))]


def is_bridge_exit(stderr: str) -> bool:
    return bool(_pattern(LIST["bridge_exit"]["C"]["stderr"]).fullmatch(stderr.strip()))
