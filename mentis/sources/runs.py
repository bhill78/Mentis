"""Planning and sweeping in the background, with progress and cancel (B5).

A THREAD, NOT A WORKER SYSTEM -- the stance `mentis.web.dispatch` takes.
Planning a large folder hashes every selected byte and sweeping reads it all
again, which is minutes rather than a request. So each runs in one in-process
thread per collection (or per draft), and the owner's interface asks how far
it has got. No queue, no scheduler, no resumption: a restart forgets a run,
and nothing was recorded by a run that did not finish, because a sweep is
still ONE transaction at its very end.

CANCEL IS ALLOWED UNTIL THAT TRANSACTION OPENS. The survey checks between
folders and between files; the sweep checks once more after the survey and
before `apply`. Once the transaction has begun the run finishes or refuses on
its own terms; a cancel asked for then changes nothing, and the run's end
state says what happened.

A RUN'S OWN FAILURE IS `failure`, NEVER `error`. Every answer that carries
an `error` key is read by the owner's interface as the ROUTE refusing
(`ui/src/api.ts`), so a run view that said `"error": null` was taken as a
refusal of every run -- found driving the built interface.

NOTHING HERE IS RECORDED. Progress is this process's memory; the record
learns only what a completed sweep writes.
"""

from __future__ import annotations

import threading
import time
import uuid

from mentis.sources import Refused

_LOCK = threading.Lock()
#: (corpus id, key) -> the latest run for that collection or draft
_RUNS: dict[tuple[str, str], "Run"] = {}

#: A RUN NOT FOR A COLLECTION IS FORGOTTEN once it has ended and been left
#: long enough (review note 5). A collection keeps its one latest run -- that
#: is bounded by how many collections exist. But a new folder's preview is
#: keyed `new-<uuid>` and its confirmation by the draft, so every preview left
#: a run holding the whole preview (about 1,000 rows for the owner's folder)
#: for the life of the process. Ended runs of that sort expire after
#: EPHEMERAL_TTL, and at most EPHEMERAL_CAP of them are kept, oldest out
#: first. A running one is never dropped.
EPHEMERAL = ("new-", "draft-")
EPHEMERAL_TTL = 60 * 60        # seconds
EPHEMERAL_CAP = 16


def _prune() -> None:
    """Under `_LOCK`."""
    now = time.time()
    ended = [(k, r) for k, r in _RUNS.items()
             if r.key.startswith(EPHEMERAL) and r.state != "running"]
    for k, r in ended:
        if now - (r.ended_at or now) > EPHEMERAL_TTL:
            _RUNS.pop(k, None)
    ended = sorted(((k, r) for k, r in ended if k in _RUNS),
                   key=lambda kr: kr[1].ended_at or 0)
    for k, _ in ended[:max(0, len(ended) - EPHEMERAL_CAP + 1)]:
        _RUNS.pop(k, None)


class Run:
    def __init__(self, key: str, kind: str, started_by=None):
        self.id = f"run-{uuid.uuid4().hex[:12]}"
        self.key, self.kind = key, kind
        #: What the server observed of the request that started it
        #: (`mentis.web._observed_writer`). A run is not recorded; this is
        #: said on its view, like everything else about it.
        self.started_by = started_by
        self.state = "running"
        self.files = 0
        self.bytes = 0
        self.current = None
        self.started_at = time.time()
        self.ended_at = None
        self.result = None
        self.failure = None
        self.failure_kind = None
        self._cancel = threading.Event()

    # -- the progress hooks `filesystem._survey` calls ------------------------
    def folder(self, rel):
        self.current = rel or "."

    def read(self, n):
        self.files += 1
        self.bytes += n

    def check(self):
        from mentis.sources.filesystem import Cancelled
        if self._cancel.is_set():
            raise Cancelled("cancelled by the owner before anything was "
                            "recorded")

    def view(self) -> dict:
        return {"run": self.id, "key": self.key, "kind": self.kind,
                "state": self.state, "started_by": self.started_by,
                "progress": {"files": self.files, "bytes": self.bytes,
                             "current": self.current},
                "started_at": self.started_at, "ended_at": self.ended_at,
                "result": self.result, "failure": self.failure,
                "failure_kind": self.failure_kind,
                "cancel_requested": self._cancel.is_set()}


def start(corpus, key: str, kind: str, work, started_by=None) -> dict:
    """Start `work(progress)` in a thread, unless one is already running for
    this collection or draft -- two sweeps of one collection at once would
    only have the second refused as a stale plan, after reading everything."""
    with _LOCK:
        _prune()
        was = _RUNS.get((corpus.corpus_id, key))
        if was is not None and was.state == "running":
            raise Refused(f"a {was.kind} is already running for this "
                          "collection; wait for it or cancel it")
        run = Run(key, kind, started_by)
        _RUNS[(corpus.corpus_id, key)] = run

    def go():
        try:
            run.result = work(run)
            run.state = "done"
        except Exception as exc:                          # noqa: BLE001
            from mentis.sources.filesystem import Cancelled
            run.state = "cancelled" if isinstance(exc, Cancelled) \
                else "refused" if isinstance(exc, Refused) else "failed"
            run.failure = str(exc)
            run.failure_kind = type(exc).__name__
        finally:
            run.ended_at = time.time()

    threading.Thread(target=go, name=f"source-{kind}-{key}",
                     daemon=True).start()
    return run.view()


def get(corpus, key: str) -> dict | None:
    run = _RUNS.get((corpus.corpus_id, key))
    return run.view() if run else None


def cancel(corpus, key: str) -> dict:
    run = _RUNS.get((corpus.corpus_id, key))
    if run is None or run.state != "running":
        return {"cancelled": False, "why": "nothing is running for this"}
    run._cancel.set()
    return {"cancelled": True, "run": run.id,
            "note": "asked to stop; nothing is recorded by a run that stops "
                    "before its transaction opens"}


def wait(corpus, key: str, timeout: float = 60.0) -> dict | None:
    """For tests and the CLI: block until the run for `key` ends."""
    end = time.time() + timeout
    while time.time() < end:
        run = _RUNS.get((corpus.corpus_id, key))
        if run is None or run.state != "running":
            return run.view() if run else None
        time.sleep(0.02)
    return get(corpus, key)
