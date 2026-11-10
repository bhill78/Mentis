"""A hand-started session's outbox: a write whose answer was lost is sent again.

WS-I of `docs/modernization/CONTRACT.md`, durable reporting. The bridge (the MCP
server a CLI session talks to, `worker.serve` in session mode) gives every
write an operation key (`op_key`) and writes it here BEFORE sending it. When an
answer comes back -- a result, or a refusal, either of which is the server's
final word -- the entry is acknowledged. When none does -- the server was not
there, or stopped after the request was sent, or did not answer in time -- the
entry stays, and is sent again, with the same key, before the session's next
call and when the next session for this participant starts. The server answers
a repeated key with the first answer and does nothing twice (`mentis.opkeys`),
so a write lands exactly once however many times it is sent.

THE FILE. `%LOCALAPPDATA%\\Mentis\\outbox\\<participant>.jsonl`, one JSON object
per line, append-only: `{"t": "put", "key", "op", "args", "at"}` when a write is
about to be sent and `{"t": "ack", "key", "at"}` once it was answered. What is
pending is every put without an ack. The file is compacted -- rewritten to the
pending puts alone -- when it has grown, under a lock file, so two sessions of
one participant on one host can share it: each line is one small append, and
whichever session resends an entry first, the server keeps one act.

Never on the server: this is the client's record of what it has sent.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from typing import Iterator

#: Compact once the file holds this many lines.
COMPACT_AT = 200
#: An entry older than this is given up: sent again for a week, then dropped.
MAX_AGE_S = 7 * 24 * 3600
_LOCK_STALE_S = 10.0


def default_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Mentis", "outbox")


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or "session")).strip("._") \
        or "session"


def new_key() -> str:
    return str(uuid.uuid4())


class Outbox:
    """One participant's outbox file."""

    def __init__(self, participant: str, directory: str | None = None) -> None:
        self.directory = directory or default_dir()
        self.path = os.path.join(self.directory, _slug(participant) + ".jsonl")
        self._lock_path = self.path + ".lock"

    # -- the file ------------------------------------------------------------

    @contextmanager
    def _locked(self) -> Iterator[None]:
        os.makedirs(self.directory, exist_ok=True)
        deadline = time.monotonic() + 5.0
        while True:
            try:
                fd = os.open(self._lock_path,
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self._lock_path) \
                            > _LOCK_STALE_S:
                        os.remove(self._lock_path)
                        continue
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError(f"outbox {self.path} is locked")
                time.sleep(0.02)
        try:
            yield
        finally:
            try:
                os.remove(self._lock_path)
            except OSError:
                pass

    def _lines(self) -> list[dict]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                raw = fh.read().splitlines()
        except FileNotFoundError:
            return []
        out = []
        for line in raw:
            try:
                got = json.loads(line)
            except ValueError:
                continue                    # a torn last line: never sent
            if isinstance(got, dict) and got.get("key"):
                out.append(got)
        return out

    def _append(self, entry: dict) -> None:
        with self._locked():
            with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    # -- what callers use ----------------------------------------------------

    def put(self, op: str, args: dict) -> str:
        """Keep a write about to be sent. Its `op_key` is `args['op_key']`."""
        key = args["op_key"]
        self._append({"t": "put", "key": key, "op": op, "args": args,
                      "at": time.time()})
        return key

    def ack(self, key: str) -> None:
        """The server answered the write under `key`: it is no longer pending."""
        self._append({"t": "ack", "key": key, "at": time.time()})
        self._compact_if_large()

    def pending(self) -> list[dict]:
        """Every write kept and not answered, oldest first."""
        puts, acked = {}, set()
        for line in self._lines():
            if line.get("t") == "put" and line["key"] not in puts:
                puts[line["key"]] = line
            elif line.get("t") == "ack":
                acked.add(line["key"])
        now = time.time()
        return [p for k, p in puts.items() if k not in acked
                and now - float(p.get("at") or now) <= MAX_AGE_S]

    def _compact_if_large(self) -> None:
        try:
            with self._locked():
                lines = self._lines()
                pending = self._pending_of(lines)
                # Rewritten when nothing is pending (the file goes) or when
                # it has grown; otherwise left to grow by appends.
                if pending and len(lines) < COMPACT_AT:
                    return
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                    for p in pending:
                        fh.write(json.dumps(p, ensure_ascii=False) + "\n")
                os.replace(tmp, self.path)
                if not pending:
                    try:
                        os.remove(self.path)
                    except OSError:
                        pass
        except (TimeoutError, OSError):
            return

    @staticmethod
    def _pending_of(lines: list[dict]) -> list[dict]:
        puts, acked = {}, set()
        for line in lines:
            if line.get("t") == "put" and line["key"] not in puts:
                puts[line["key"]] = line
            elif line.get("t") == "ack":
                acked.add(line["key"])
        return [p for k, p in puts.items() if k not in acked]
