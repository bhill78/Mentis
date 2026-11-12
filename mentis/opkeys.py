"""One act per operation key: a worker write sent twice is done once.

WS-I of `docs/modernization/CONTRACT.md`, durable reporting. The worker client
never retries, and says "the result is unknown" when the answer was lost
(`worker._result_unknown`). A session's bridge now keeps what it sent in an
outbox and sends it again (`mentis.outbox`), so the server must recognise the
second sending: every write operation through `/api/worker` accepts `op_key`,
a key the client generated, and the first answer under (grant participant, op,
op_key) is the answer to every repeat. Nothing is written or dispatched again.

THE SAME ACT POSTING USES, FOUND BY AN INDEX. The outcome is kept as the
record's own `operation-keyed` act, named `worker:<op>:<op_key>` so a worker
key can never collide with an author's posting key, and carrying
`caused_by = opkey:<digest>` so it is found by an indexed equality (`find`). The same key with different arguments is
refused, as it is for posting: a new occurrence uses a new key.

WRITTEN WITH THE OPERATION, IN ONE TRANSACTION, ALWAYS -- so a crash leaves
neither the act nor its key, or both, and a resend after it either finds the
first answer or does the write for the first time. Most operations are run
whole inside the transaction that asks for the key and writes it.

`delegate` cannot be run whole inside one: before it writes, it asks the agent
service which runtimes are eligible, and that must not happen while holding
the write lock. So it is run in two parts. Its checks run outside, and its
writes go through `writing`, which opens the one transaction that asks for
the key AGAIN, makes every write of the delegation, and records the key
(round 2 -- Z: this used to be a second transaction after the delegation's
own, and a process that died between them -- or between the delegation's
own separately committed writes -- left a delegation the resend did not
find, and the resend delegated again). Two sends of one key in flight at
once, in one process or two, are both past the first look before either
writes: the look inside the transaction is taken under the store's write
lock (`BEGIN IMMEDIATE`), so the second finds the first's key, writes
nothing, and is answered with the first answer. A lock per key in this
process still holds a repeat until the first is answered, so the usual
resend does not even repeat the checks.

WHAT IS KEPT is the answer minus what the door does after it (`dispatch`,
`dispatches`): a repeat must not start a run again.

WHO SENDS KEYS (round 4, C2). Both bridges key every write they send
(`worker.write_key`): a hand-started session's with a fresh key per write, a
dispatched run's with a key derived from (execution, operation, arguments)
for a write that makes a record (`worker.CONTENT_KEYED`), so the agent
sending the same write again is the same write. Both keep a write until it is
answered and resend it under its key before their next call
(`mentis.outbox`).

WHAT THIS DOES NOT COVER (said so nothing overclaims it):
  * A write sent WITHOUT an `op_key` -- by a client that is not a bridge, or
    a dispatched run's write outside `CONTENT_KEYED` sent again by the agent
    after its answer was lost and given up -- has no identity to deduplicate
    by: each send is a new write.
  * A dispatched run's grant ends with the server process that minted it, so
    after a server restart its resend is refused, not replayed: nothing is
    written twice, and a write that did not commit before the crash is not
    made at all.
  * The door dispatches after `keyed` returns, and a replay never
    dispatches, so a delegation committed just before the process died is
    recorded and not started here. A server's start starts it, once, within
    a bound (`web.dispatch.recover_delegations`, round 4 C2).
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import threading
from typing import Any, Callable

#: Operations whose checks run outside the transaction and whose writes, with
#: their key, go through `writing` (see above).
OUTSIDE_TRANSACTION = ("delegate",)

#: What the door acts on after the operation, never replayed.
_NOT_REPLAYED = ("dispatch", "dispatches")

_locks: dict[tuple, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(key: tuple) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            if len(_locks) > 4096:
                # Unheld locks only; a held one is somebody's call in flight.
                for k in [k for k, v in _locks.items() if not v.locked()]:
                    _locks.pop(k, None)
            lock = _locks[key] = threading.Lock()
        return lock


def is_write(op: str) -> bool:
    """Whether `op` writes: not a read, and not one of the gated reads."""
    from mentis.worker import READ_ONLY, READS, SOURCE_READS, WORKSPACE_READ
    return op not in (set(READ_ONLY) | set(READS) | set(SOURCE_READS)
                      | {"read_artifact", WORKSPACE_READ})


def key_of(args: dict) -> str | None:
    """The `op_key` a call carried, checked; None for none."""
    key = args.get("op_key")
    if key is None or key == "":
        return None
    if not isinstance(key, str) or not key.strip() or len(key) > 160:
        from mentis.worker import NotPermitted
        raise NotPermitted(
            op=None, boundary="validation",
            why="op_key is a non-empty string of at most 160 characters, "
                "generated by the caller once per write",
            recovery=["call again with a fresh op_key (a uuid), or none"])
    return key.strip()


def _plain(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


#: WHERE A KEY IS FOUND: the keyed act's `caused_by`, which the store indexes
#: (`idx_operational_caused_by`). Review finding: the lookup used to be
#: `json_extract(detail, '$.op')` over every act of the participant (or, for
#: the Contributions conversation, of the whole Brain), inside the write
#: transaction. A key's act now carries `caused_by = "opkey:<digest>"`, a
#: value that is never an act id, so no lineage reader ever reaches it, and
#: finding it is one indexed equality -- no index migration needed.
KEY_PREFIX = "opkey:"


def key_ref(owner: str, name: str) -> str:
    """The `caused_by` a key's act carries: one per (owner, key name)."""
    return KEY_PREFIX + hashlib.sha256(
        f"{owner}\x1f{name}".encode("utf-8")).hexdigest()[:40]


def find(corpus, owner: str, name: str) -> dict | None:
    """The act recording key `name` for `owner`, or None. Indexed."""
    from mentis.conversation.anchors import KEYED
    for a in corpus.operational(caused_by=key_ref(owner, name), act=KEYED):
        if (a.get("detail") or {}).get("op") == name:
            return a
    return None


def remember(cv, owner: str, name: str, request: dict, result: dict, *,
             actor: str, execution: str | None = None,
             runtime: str | None = None,
             conversation: str | None = None) -> str:
    """Record what key `name` came to, findable by `find`."""
    from mentis.conversation.anchors import KEYED, digest
    return cv.record_act(
        actor=actor, act=KEYED, conversation=conversation,
        execution=execution, runtime=runtime,
        caused_by=key_ref(owner, name),
        about=[v for v in result.values()
               if isinstance(v, str) and v.startswith("ent-")][:8],
        detail={"op": name, "digest": digest(request), "result": result})


def keyed(corpus, cv, *, participant: str, op: str, args: dict,
          run: Callable[[dict], dict], execution: str | None = None,
          runtime: str | None = None) -> dict:
    """`run(args without op_key)`, once per (participant, op, op_key).

    Without a key, or for a read, it is just `run`."""
    key = key_of(args)
    call = {k: v for k, v in args.items() if k != "op_key"}
    if key is None or not is_write(op):
        return run(call)
    from mentis.conversation.anchors import digest
    from mentis.worker import NotPermitted
    name = f"worker:{op}:{key}"
    request = {"route": "worker", "op": op, "args": call}

    def prior():
        got = find(corpus, participant, name)
        if got is None:
            return None
        if got["detail"].get("digest") != digest(request):
            raise NotPermitted(
                op=op, boundary="validation",
                why=f"op_key {key!r} was already used for a different "
                    f"{op} by this participant; nothing was written",
                recovery=["send this write again with a new op_key"])
        return {**got["detail"]["result"], "replayed": True, "op_key": key}

    def kept(out):
        if op == "arm_detached" and isinstance(out, dict):
            # Never persist the bearer secret in operation-keyed results.
            # A resend identifies the same arm, but cannot recover its token.
            out = {**{k: v for k, v in out.items() if k != "report_token"},
                   "token_unavailable": True,
                   "note": "The arm is recorded, but its token was returned only once. "
                           "If it was lost, do not start that helper; arm a new operation."}
        return _plain({k: v for k, v in out.items() if k not in _NOT_REPLAYED}
                      if isinstance(out, dict) else {"result": out})

    def record(out):
        remember(cv, participant, name, request, kept(out), actor=participant,
                 execution=execution, runtime=runtime)

    with _lock_for((participant, name)):
        if op in OUTSIDE_TRANSACTION:
            got = prior()
            if got is not None:
                return got
            pending = _Pending(prior, record)
            token = _pending.set(pending)
            try:
                out = run(call)
            except _Replayed as replayed:
                return replayed.result
            finally:
                _pending.reset(token)
            if pending.written:
                return out
            # IT WROTE NOTHING THROUGH `writing` -- it delegated nothing (the
            # owner's later word was shown instead) -- so there is no
            # delegation the key could be lost from; the answer is kept as
            # before, findable by a resend.
            with corpus.atomic():
                got = prior()
                if got is not None:
                    return got
                record(out)
            return out
        with corpus.atomic():
            got = prior()
            if got is not None:
                return got
            out = run(call)
            record(out)
            return out


class _Replayed(Exception):
    """Raised inside `writing` when the key was recorded meanwhile: the
    transaction is rolled back with nothing written, and `keyed` answers
    with the first answer."""

    def __init__(self, result: dict):
        super().__init__("op_key already recorded")
        self.result = result


class _Pending:
    """The key of the call in progress, for `writing` to ask and record."""

    def __init__(self, prior, record):
        self.prior, self.record = prior, record
        self.written = False


_pending: contextvars.ContextVar = contextvars.ContextVar(
    "mentis_opkey_pending", default=None)


class _Writes:
    """What `writing` yields: `done(out)` records the key with `out`."""

    def __init__(self, pending):
        self._pending = pending

    def done(self, out):
        if self._pending is not None:
            self._pending.record(out)
            self._pending.written = True
            self._pending = None
        return out


@contextlib.contextmanager
def writing(corpus):
    """The write phase of an `OUTSIDE_TRANSACTION` operation, as ONE
    transaction with its op key.

        with opkeys.writing(corpus) as w:
            ... every write ...
            return w.done(result)

    Inside a keyed call it asks for the key again, under the write lock, and
    if a send of the same key recorded it meanwhile it writes nothing and the
    call is answered with that first answer. `done` records the key in the
    same transaction. Without a key it is `corpus.atomic()` alone. A block
    that raises, or ends without `done`, commits nothing of its writes.
    """
    pending = _pending.get()
    if pending is not None and pending.written:
        pending = None              # a second write phase is the op's own
    with corpus.atomic():
        if pending is not None:
            got = pending.prior()
            if got is not None:
                raise _Replayed(got)
        yield _Writes(pending)
        if pending is not None and not pending.written:
            # a keyed write phase that ended without `done` would commit writes with no
            # key, and a retry would write them again: roll it back instead
            raise RuntimeError("opkeys.writing: a keyed write phase ended without done()")
