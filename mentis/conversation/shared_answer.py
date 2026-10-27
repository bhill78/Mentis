"""One computation per question at a time, and its answer reused while the
record it was read from has not moved.

WHY (the owner's slowdown, measured 2026-10-25). Opening a conversation in
Fluid took 17-27 s. The page asks `/fluid/api/home/work` twice and
`/api/capacity` once as it opens; each is seconds of pure-Python work (the
whole work history, or three runtimes' rate-limit files), and the server
runs every request on its own thread under one interpreter lock. Two copies
of the same 5 s answer computed side by side took 11-20 s each and starved
every other request on the page (`/api/brain`, 0.7 s alone, took 8-10 s).

  SINGLE FLIGHT  a request for an answer already being computed waits for
                 that computation instead of starting another.
  REUSED ONLY WHILE TRUE  an answer is kept with the `version` it was read at
                 (the record's `steady` count, plus whatever else it
                 depends on) and given again only while `version` is the
                 same -- and, where `fresh_for` is set, while it is younger
                 than that. A `version` of None (a commit under way) is never
                 kept or reused: that call computes straight through.
  KEPT ONLY IF NOTHING MOVED  `version` is asked again after the
                 computation; an answer read while the record moved is
                 returned to its caller and not kept.

Bounded: the oldest answers are dropped past `LIMIT`.
"""

from __future__ import annotations

import collections
import threading
import time

LIMIT = 64


class SharedAnswers:
    def __init__(self, limit: int = LIMIT):
        self._lock = threading.Lock()
        self._kept: collections.OrderedDict = collections.OrderedDict()
        self._running: dict = {}
        self._limit = limit

    def get(self, key, compute, *, version, fresh_for: float | None = None):
        """`compute()`'s answer for `key`, shared as the module says.
        `version` is a callable, asked before and after computing."""
        while True:
            before = version()
            if before is None:
                return compute()
            with self._lock:
                kept = self._kept.get(key)
                if kept is not None and kept[0] == before and (
                        fresh_for is None
                        or time.monotonic() - kept[2] < fresh_for):
                    self._kept.move_to_end(key)
                    return kept[1]
                running = self._running.get(key)
                if running is None:
                    running = self._running[key] = threading.Event()
                    mine = True
                else:
                    mine = False
            if not mine:
                # Someone is computing it: wait, then look again (their
                # answer is kept if the record held still; if not, compute).
                running.wait()
                continue
            try:
                value = compute()
                after = version()
                if after is not None and after == before:
                    with self._lock:
                        self._kept[key] = (before, value, time.monotonic())
                        self._kept.move_to_end(key)
                        while len(self._kept) > self._limit:
                            self._kept.popitem(last=False)
                return value
            finally:
                with self._lock:
                    self._running.pop(key, None)
                running.set()


def answers_of(state) -> SharedAnswers:
    """The answers kept for ONE server state (its Brain, its runtimes): never
    shared between two states in one process, as tests run many."""
    with _MAKING:
        got = getattr(state, "_shared_answers", None)
        if got is None:
            got = SharedAnswers()
            setattr(state, "_shared_answers", got)
        return got


_MAKING = threading.Lock()
