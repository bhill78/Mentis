"""Shared working-context cache and revision tracking.

Operating model contract §4.

Derived and reconstructable; nothing durable lives only in this cache.
Single-flight coalescing ensures concurrent identical requests compute once.
Bounded by maximum entry count and maximum bytes (LRU).
Revisions tracks domain write counters per corpus, invalidating cached context
when dependent domains move.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import threading
from typing import Any, Callable, Iterable, Set

#: Safe fallback limits from §4
DEFAULT_MAX_ENTRIES = 512
DEFAULT_MAX_BYTES = 64_000_000


class Flight:
    """An in-flight computation for single-flight coalescing."""

    def __init__(self) -> None:
        self.event = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None


class ContextCache:
    """Bounded LRU context cache with single-flight coalescing and domain invalidation."""

    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_bytes: int = DEFAULT_MAX_BYTES,
        revisions: Revisions | None = None,
        disabled: bool | None = None,
        steady: Callable[[], Any] | None = None,
    ) -> None:
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.revisions = revisions
        #: `Corpus.steady`: the write count when no commit is under way, else
        #: None. Revisions are noted when a write is APPENDED, inside its
        #: transaction, so a read begun after the note and before the COMMIT
        #: sees the record without it while its token already counts it.
        #: Asked before and after computing, as `Conversations._recall` asks
        #: it, so a kept value is one moment of the record.
        self.steady = steady
        self._disabled_override = disabled
        self._lock = threading.Lock()
        self._entries: collections.OrderedDict[Any, dict] = collections.OrderedDict()
        self._in_flight: dict[Any, Flight] = {}
        self.total_bytes = 0
        self._stats = {
            "hits": 0,
            "misses": 0,
            "coalesced": 0,
            "evictions": 0,
            "invalidations": 0,
        }
        self._by_kind_stats: dict[str, dict] = collections.defaultdict(
            lambda: {"hits": 0, "misses": 0, "coalesced": 0, "entries": 0, "bytes": 0}
        )

    @property
    def disabled(self) -> bool:
        if self._disabled_override is not None:
            return self._disabled_override
        return os.environ.get("MENTIS_CONTEXT_CACHE") == "0"

    @staticmethod
    def _kind_of(key: Any) -> str:
        if isinstance(key, (tuple, list)) and len(key) > 0 and key[0] is not None:
            return str(key[0])
        return "unknown"

    @staticmethod
    def _approx_size(obj: Any) -> int:
        try:
            return len(json.dumps(obj, default=str).encode("utf-8"))
        except Exception:
            return 256

    def get(
        self,
        key: Any,
        compute: Callable[[], Any],
        *,
        deps: frozenset[str],
        with_meta: bool = False,
    ) -> Any:
        """Single-flight get for `key`.

        If `with_meta` is True, returns (value, {"hit": bool, "coalesced": bool}).
        Otherwise returns value.
        """
        kind = self._kind_of(key)

        # MENTIS_CONTEXT_CACHE=0 disables caching (every get computes)
        if self.disabled:
            with self._lock:
                self._stats["misses"] += 1
                self._by_kind_stats[kind]["misses"] += 1
            val = compute()
            meta = {"hit": False, "coalesced": False}
            return (val, meta) if with_meta else val

        with self._lock:
            if key in self._entries:
                self._stats["hits"] += 1
                self._by_kind_stats[kind]["hits"] += 1
                self._entries.move_to_end(key)
                val = self._entries[key]["value"]
                meta = {"hit": True, "coalesced": False}
                return (val, meta) if with_meta else val

            if key in self._in_flight:
                flight = self._in_flight[key]
                self._stats["coalesced"] += 1
                self._by_kind_stats[kind]["coalesced"] += 1
                is_leader = False
            else:
                flight = Flight()
                self._in_flight[key] = flight
                self._stats["misses"] += 1
                self._by_kind_stats[kind]["misses"] += 1
                is_leader = True

        if not is_leader:
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            meta = {"hit": False, "coalesced": True}
            return (flight.value, meta) if with_meta else flight.value

        # Leader executes compute outside lock
        before_token = (
            self.revisions.token(deps) if self.revisions is not None else None
        )
        before_steady = self.steady() if self.steady is not None else 0
        try:
            val = compute()
        except BaseException as exc:
            with self._lock:
                flight.error = exc
                self._in_flight.pop(key, None)
                flight.event.set()
            raise

        after_token = (
            self.revisions.token(deps) if self.revisions is not None else None
        )
        after_steady = self.steady() if self.steady is not None else 0

        with self._lock:
            flight.value = val
            self._in_flight.pop(key, None)
            # Follow the rule of Conversations._recall:
            # a value computed while one of its domains moved is returned but not kept
            if (
                (before_token is None or before_token == after_token)
                and before_steady is not None and before_steady == after_steady
                and not self.disabled
            ):
                self._put_locked(key, val, deps, kind)
            flight.event.set()

        meta = {"hit": False, "coalesced": False}
        return (val, meta) if with_meta else val

    def _put_locked(
        self, key: Any, value: Any, deps: frozenset[str], kind: str
    ) -> None:
        size = self._approx_size(value)
        if key in self._entries:
            old = self._entries.pop(key)
            self.total_bytes -= old["size"]
            self._by_kind_stats[kind]["entries"] -= 1
            self._by_kind_stats[kind]["bytes"] -= old["size"]
        self._entries[key] = {
            "value": value,
            "size": size,
            "deps": deps,
            "kind": kind,
        }
        self.total_bytes += size
        self._by_kind_stats[kind]["entries"] += 1
        self._by_kind_stats[kind]["bytes"] += size
        self._entries.move_to_end(key)
        self._evict_if_needed_locked()

    def _evict_if_needed_locked(self) -> None:
        while len(self._entries) > self.max_entries or (
            self.total_bytes > self.max_bytes and len(self._entries) > 1
        ):
            _, entry = self._entries.popitem(last=False)
            self.total_bytes -= entry["size"]
            self._stats["evictions"] += 1
            ekind = entry["kind"]
            self._by_kind_stats[ekind]["entries"] -= 1
            self._by_kind_stats[ekind]["bytes"] -= entry["size"]

    def invalidate_domains(self, touched: Set[str]) -> None:
        if not touched:
            return
        with self._lock:
            to_remove = []
            for k, entry in self._entries.items():
                if ("__all__" in touched) or bool(entry["deps"] & touched):
                    to_remove.append(k)
            for k in to_remove:
                entry = self._entries.pop(k)
                self.total_bytes -= entry["size"]
                self._stats["invalidations"] += 1
                ekind = entry["kind"]
                self._by_kind_stats[ekind]["entries"] -= 1
                self._by_kind_stats[ekind]["bytes"] -= entry["size"]

    def stats(self) -> dict:
        with self._lock:
            by_kind = {}
            for k, s in self._by_kind_stats.items():
                by_kind[k] = dict(s)
            return {
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "coalesced": self._stats["coalesced"],
                "evictions": self._stats["evictions"],
                "invalidations": self._stats["invalidations"],
                "entries": len(self._entries),
                "bytes": self.total_bytes,
                "by_kind": by_kind,
            }

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self.total_bytes = 0
            for k in self._by_kind_stats:
                self._by_kind_stats[k]["entries"] = 0
                self._by_kind_stats[k]["bytes"] = 0


class Revisions:
    """Per-corpus revision counters for dependency domains."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._revisions: dict[str, int] = collections.defaultdict(int)
        self._unknown_writes = 0
        self._listeners: list[Callable[[Set[str]], None]] = []

    def add_listener(self, fn: Callable[[Set[str]], None]) -> None:
        with self._lock:
            self._listeners.append(fn)

    def token(self, deps: Iterable[str]) -> tuple:
        with self._lock:
            # Current revision of each dependency domain
            return tuple(
                (d, self._revisions[d] + self._unknown_writes)
                for d in sorted(deps)
            )

    def note_write(self, entry_or_act: dict) -> set[str]:
        touched = self.classify_write(entry_or_act)
        with self._lock:
            if "__all__" in touched:
                self._unknown_writes += 1
                for d in list(self._revisions.keys()):
                    self._revisions[d] += 1
            else:
                for d in touched:
                    self._revisions[d] += 1
            listeners = list(self._listeners)
        for fn in listeners:
            fn(touched)
        return touched

    def classify_write(self, item: dict) -> set[str]:
        if not isinstance(item, dict):
            return self._bump_all()

        touched = set()

        # Operational act
        if "act" in item:
            act = str(item.get("act") or "")
            cid = item.get("conversation")
            if cid:
                touched.add(f"conversation:{cid}")

            # work domain: expectations, met/assigned/discovered/pursued/dismissed acts,
            # decisions answered or withdrawn
            if act in (
                "expectation-recorded",
                "work-assigned",
                "work-met",
                "work-discovered",
                "work-pursued",
                "work-dismissed",
                "decision-answered",
                "decision-withdrawn",
                "work-recorded",
                "outcome-recorded",
                "reconsideration-offered",
            ):
                touched.add("work")

            # governance domain: decisions answered or withdrawn,
            # challenges/withdrawals of governing material
            if act in ("decision-answered", "decision-withdrawn"):
                touched.add("governance")
            if act in (
                "challenge",
                "challenge-raised",
                "challenge-resolved",
                "withdraw_challenge",
                "withdraw-challenge",
            ):
                touched.add("governance")
                touched.add("knowledge")
            if act in ("request-adoption", "adopt", "request_adoption"):
                touched.add("knowledge")
            if act in ("participant-joined", "summon-participant", "alias-set"):
                touched.add("participants")

            if act in ("conversation-opened", "turn-said", "topic-opened"):
                # already touched conversation:<cid> if cid was present
                pass

            if not touched:
                return self._bump_all(cid)
            return touched

        # Entry (definition, admission, link)
        d = item.get("definition") or {}
        def_name = (
            d.get("name") if isinstance(d, dict) else item.get("def_name")
        )
        link = item.get("link") or {}
        rel = (
            link.get("relation")
            if isinstance(link, dict)
            else item.get("link_relation")
        )

        cid = None
        body = item.get("body")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except Exception:
                body = {}
        if isinstance(body, dict):
            cid = body.get("conversation")
        if not cid and def_name == "conversation":
            cid = item.get("id")
        if cid:
            touched.add(f"conversation:{cid}")

        # governance: rule/decision/persona/discipline/workflow entries,
        # establishes, supersedes, proposes-to-supersede, scoped-to, carries-intake,
        # challenges/withdrawals of governing material
        if def_name in ("rule", "decision", "persona", "discipline", "workflow"):
            touched.add("governance")
        if rel in (
            "establishes",
            "supersedes",
            "proposes-to-supersede",
            "scoped-to",
            "carries-intake",
        ):
            touched.add("governance")
            link_to = (
                link.get("to")
                if isinstance(link, dict)
                else item.get("link_to")
            )
            if link_to and str(link_to).startswith("ent-"):
                touched.add(f"conversation:{link_to}")
        if rel in ("disputes", "withdraws"):
            touched.add("governance")
            touched.add("knowledge")

        # knowledge: that-Kinds, adoption, challenges of findings
        if def_name in (
            "source-material",
            "note",
            "problem",
            "solution",
            "hypothesis",
            "finding",
            "outcome",
            "lesson",
        ):
            touched.add("knowledge")
        if rel in ("adopts", "request-adoption", "derived-from", "supports"):
            touched.add("knowledge")

        # participants
        if def_name == "participant" or rel == "participates-in":
            touched.add("participants")

        if not touched:
            return self._bump_all(cid)

        return touched

    def _bump_all(self, cid: str | None = None) -> set[str]:
        # Unknown write: bump every domain!
        domains = {
            "governance",
            "knowledge",
            "work",
            "participants",
            "__all__",
        }
        with self._lock:
            for k in list(self._revisions.keys()):
                domains.add(k)
        if cid:
            domains.add(f"conversation:{cid}")
        return domains


_CACHES: dict[str, ContextCache] = {}
_REVISIONS: dict[str, Revisions] = {}
_LOCK = threading.Lock()


def _identity(corpus: Any) -> str:
    # ID AND PATH. A copy of a Brain keeps its original's id, so two copies
    # open in one process (a test, a rehearsal) would otherwise share answers.
    return "{}@{}".format(getattr(corpus, "corpus_id", None),
                          getattr(corpus, "root", getattr(corpus, "path", id(corpus))))


def cache_for(corpus: Any) -> ContextCache:
    """Return the ContextCache instance for this corpus (one per corpus in the process)."""
    rev = revisions_for(corpus)
    cid = _identity(corpus)
    with _LOCK:
        if cid not in _CACHES:
            steady = (lambda: corpus.steady) if hasattr(corpus, "steady") else None
            cache = ContextCache(revisions=rev, steady=steady)
            rev.add_listener(cache.invalidate_domains)
            _CACHES[cid] = cache
        return _CACHES[cid]


def revisions_for(corpus: Any) -> Revisions:
    """Return the Revisions instance for this corpus (one per corpus in the process)."""
    cid = _identity(corpus)
    with _LOCK:
        if cid not in _REVISIONS:
            _REVISIONS[cid] = Revisions()
        return _REVISIONS[cid]
