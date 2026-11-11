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
so a write kept here is recorded once however many times it is sent with its
key.

A DISPATCHED RUN'S BRIDGE (round 4, C2) keeps its writes by the same rules in
a `MemoryOutbox`: held by that bridge process alone, resent only before the
run's own next tool call, given up when the bridge ends. Nobody else may
resend them (the run's grant ends with the run), so nothing is kept on disk.
Its keys are made by `worker.serve` (`write_key`): the agent's own `op_key`;
else the key of a kept, unanswered write with the same operation and
arguments; else, for a write that makes a record (`worker.CONTENT_KEYED`), a
key derived from (execution, operation, arguments), so the agent sending the
same write again is the same write; else a fresh one.

THE FILES. One per SESSION (execution), never shared:
`%LOCALAPPDATA%/Mentis/outbox/<participant>/<execution>.jsonl`, one JSON
object per line, append-only: `{"t": "put", "key", "op", "args", "at"}` when a
write is about to be sent and `{"t": "ack", "key", "at"}` once it was answered.
What is pending is every put without an ack. Compacted when it has grown, and
deleted when nothing is pending. A session that has no execution yet (the
server never answered its grant) writes `unbound-<uuid>.jsonl`.

WHY PER SESSION (review finding): a resend runs under some session's grant,
and a write that acts in a place the ORIGINAL session opened is admitted only
under that session's execution. And two sessions sharing one participant must
not resend each other's writes while both are alive. So each session owns its
file, and holds `<execution>.live` locked by the OS for as long as its process
lives (released when it dies, however it dies). A new session resends another
session's entries only once it can take that lock -- the other is gone -- and
then, where the server lets it, as that session (`continues`), else under its
own grant, reporting every refusal to the agent.

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


def participant_dir(participant: str, directory: str | None = None) -> str:
    return os.path.join(directory or default_dir(), _slug(participant))


class Outbox:
    """One session's outbox file."""

    def __init__(self, participant: str, directory: str | None = None,
                 execution: str | None = None) -> None:
        self.participant = participant
        self.directory = participant_dir(participant, directory)
        self.execution = execution or f"unbound-{uuid.uuid4()}"
        self.path = os.path.join(self.directory, _slug(self.execution) + ".jsonl")
        self._lock_path = self.path + ".lock"
        self._live = None

    @property
    def bound(self) -> bool:
        return not self.execution.startswith("unbound-")

    # -- liveness: an OS lock held for the life of the process ---------------

    def hold(self) -> bool:
        """Mark this session alive until its process ends. False if another
        process holds it."""
        if self._live is not None:
            return True
        self._live = _try_lock(os.path.join(self.directory,
                                            _slug(self.execution) + ".live"))
        return self._live is not None

    def release(self) -> None:
        if self._live is not None:
            _unlock(self._live)
            self._live = None

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


def same_write(box, op: str, args: dict) -> dict | None:
    """The kept, unanswered write in `box` with this operation and these
    arguments (its `op_key` aside), or None. Sending it again is resending it,
    under its key."""
    if box is None:
        return None
    want = canonical({k: v for k, v in args.items() if k != "op_key"})
    for entry in box.pending():
        if entry.get("op") == op and canonical(
                {k: v for k, v in (entry.get("args") or {}).items()
                 if k != "op_key"}) == want:
            return entry
    return None


def canonical(args: dict) -> str:
    """One spelling of a call's arguments: keys sorted, compact."""
    return json.dumps(args, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), default=str)


def derived_key(execution: str, op: str, args: dict) -> str:
    """The key a dispatched run's write is given when the agent gave none:
    the same for the same (execution, operation, arguments), so an agent
    that sends a write again after a lost answer sends the same write."""
    import hashlib
    call = {k: v for k, v in args.items() if k != "op_key"}
    digest = hashlib.sha256("\x1f".join(
        (str(execution), op, canonical(call))).encode("utf-8")).hexdigest()
    return "run-" + digest[:40]


class MemoryOutbox:
    """A dispatched run's outbox: `Outbox`'s rules, held in its bridge's
    memory. Kept until answered; resent before the run's next tool call;
    given up after `MAX_AGE_S` or when the bridge process ends."""

    bound = True

    def __init__(self, execution: str | None = None) -> None:
        self.execution = execution or f"unbound-{uuid.uuid4()}"
        self._puts: dict[str, dict] = {}

    def hold(self) -> bool:
        return True

    def release(self) -> None:
        return None

    def put(self, op: str, args: dict) -> str:
        key = args["op_key"]
        self._puts.setdefault(key, {"t": "put", "key": key, "op": op,
                                    "args": args, "at": time.time()})
        return key

    def ack(self, key: str) -> None:
        self._puts.pop(key, None)

    def pending(self) -> list[dict]:
        now = time.time()
        for k in [k for k, p in self._puts.items()
                  if now - float(p["at"]) > MAX_AGE_S]:
            self._puts.pop(k, None)
        return list(self._puts.values())


def _try_lock(path: str):
    """An open handle holding an exclusive OS lock on `path`, or None if some
    other process holds it. The OS drops the lock when the process dies."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fh = open(path, "a+b")
    try:
        fh.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def _unlock(fh) -> None:
    try:
        fh.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    fh.close()
    try:
        os.remove(fh.name)
    except OSError:
        pass


def orphans(participant: str, directory: str | None,
            mine: str | None) -> list["Outbox"]:
    """Other sessions' outboxes, for this participant, that hold pending
    writes and whose session is gone (its liveness lock could be taken; the
    returned boxes HOLD it -- `release` each when done)."""
    where = participant_dir(participant, directory)
    try:
        names = sorted(os.listdir(where))
    except FileNotFoundError:
        return []
    out = []
    for name in names:
        if not name.endswith(".jsonl"):
            continue
        execution = name[:-len(".jsonl")]
        if execution == mine:
            continue
        box = Outbox(participant, directory, execution)
        if not box.pending():
            continue
        if not box.hold():
            continue                    # that session is alive: not ours
        out.append(box)
    return out


def pending_all(participant: str, directory: str | None = None) -> list[dict]:
    """Every pending write of every session of this participant."""
    where = participant_dir(participant, directory)
    try:
        names = os.listdir(where)
    except FileNotFoundError:
        return []
    return [p for n in sorted(names) if n.endswith(".jsonl")
            for p in Outbox(participant, directory, n[:-6]).pending()]
