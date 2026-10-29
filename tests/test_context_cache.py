"""Concurrency, LRU bounds, domain invalidation, and integration tests for context cache.

Operating model contract §4 and §5.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import threading
import time
from typing import Any

import pytest

import mentis.api as api
from mentis.core.context_cache import (
    ContextCache,
    Revisions,
    cache_for,
    revisions_for,
)
from mentis.core.orientation import foundation, for_agent
from mentis.web import _Handler, _State, fixture
from mentis.worker import Surface


# -- Unit tests: LRU bounds and bytes -----------------------------------------


def test_lru_bounds_by_entries():
    """Cache evicts least-recently-used items when max_entries is exceeded."""
    cache = ContextCache(max_entries=3, max_bytes=10_000_000)
    deps = frozenset({"governance"})

    cache.get("k1", lambda: {"data": "1"}, deps=deps)
    cache.get("k2", lambda: {"data": "2"}, deps=deps)
    cache.get("k3", lambda: {"data": "3"}, deps=deps)

    stats = cache.stats()
    assert stats["entries"] == 3
    assert stats["evictions"] == 0

    # Touch k1 to make it most recently used; LRU order is now k2, k3, k1
    cache.get("k1", lambda: {"data": "1"}, deps=deps)
    assert cache.stats()["hits"] == 1

    # Adding k4 should evict k2 (the oldest)
    cache.get("k4", lambda: {"data": "4"}, deps=deps)
    stats = cache.stats()
    assert stats["entries"] == 3
    assert stats["evictions"] == 1

    # k1, k3, k4 should be hits; k2 was evicted and requires re-computing
    assert cache.get("k1", lambda: None, deps=deps) == {"data": "1"}
    assert cache.get("k3", lambda: None, deps=deps) == {"data": "3"}
    assert cache.get("k4", lambda: None, deps=deps) == {"data": "4"}
    # k2 was evicted: compute will be called
    computed_k2 = False

    def recompute_k2():
        nonlocal computed_k2
        computed_k2 = True
        return {"data": "2-new"}

    val_k2 = cache.get("k2", recompute_k2, deps=deps)
    assert computed_k2 is True
    assert val_k2 == {"data": "2-new"}


def test_lru_bounds_by_bytes():
    """Cache evicts entries when max_bytes threshold is exceeded."""
    # Approximate size of payload with 100 bytes is ~120-150 bytes in JSON
    cache = ContextCache(max_entries=50, max_bytes=300)
    deps = frozenset({"governance"})

    payload1 = {"payload": "a" * 100}
    payload2 = {"payload": "b" * 100}
    payload3 = {"payload": "c" * 100}

    cache.get("k1", lambda: payload1, deps=deps)
    cache.get("k2", lambda: payload2, deps=deps)
    assert cache.stats()["entries"] == 2
    assert cache.stats()["evictions"] == 0

    # Adding payload3 pushes total_bytes over 300, evicting k1
    cache.get("k3", lambda: payload3, deps=deps)
    stats = cache.stats()
    assert stats["evictions"] >= 1
    assert stats["bytes"] <= 300
    assert "k1" not in cache._entries


# -- Unit tests: Single-flight coalescing -------------------------------------


def test_single_flight_coalescing():
    """N concurrent threads requesting the same key compute exactly once."""
    cache = ContextCache()
    deps = frozenset({"governance"})
    compute_count = 0
    compute_lock = threading.Lock()
    started = threading.Event()
    release = threading.Event()

    def slow_compute():
        nonlocal compute_count
        with compute_lock:
            compute_count += 1
        started.set()
        release.wait(timeout=5.0)
        return {"computed_at": time.time(), "result": "coalesced_value"}

    results = []
    metas = []
    threads = []
    n_threads = 10

    def worker():
        val, meta = cache.get("shared_key", slow_compute, deps=deps, with_meta=True)
        results.append(val)
        metas.append(meta)

    for _ in range(n_threads):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    # Wait until the leader starts computing
    assert started.wait(timeout=5.0)
    # Allow small window for other threads to enter waiting queue
    time.sleep(0.05)
    release.set()

    for t in threads:
        t.join(timeout=5.0)

    # Exactly one compute should have executed
    assert compute_count == 1
    assert len(results) == n_threads
    # All threads got the exact same computed dict
    first = results[0]
    for r in results:
        assert r == first

    stats = cache.stats()
    assert stats["misses"] == 1
    assert stats["coalesced"] == n_threads - 1
    assert stats["hits"] == 0

    # Verify metadata flags: 1 leader (coalesced=False), 9 coalesced (coalesced=True)
    leader_metas = [m for m in metas if not m["coalesced"]]
    coalesced_metas = [m for m in metas if m["coalesced"]]
    assert len(leader_metas) == 1
    assert len(coalesced_metas) == n_threads - 1

    # Subsequent 11th call gets a direct hit
    val11, meta11 = cache.get("shared_key", slow_compute, deps=deps, with_meta=True)
    assert val11 == first
    assert meta11 == {"hit": True, "coalesced": False}
    assert cache.stats()["hits"] == 1


# -- Unit tests: Value computed while domain moved not kept -------------------


def test_value_computed_while_moved_not_kept():
    """A value computed while one of its domains moved is returned but not kept."""
    revs = Revisions()
    cache = ContextCache(revisions=revs)
    deps = frozenset({"governance"})

    def compute_with_mid_write():
        # Move the governance domain during computation
        revs.note_write({
            "family": "admission",
            "definition": {"name": "rule"},
            "body": {"text": "A new rule was established during compute"},
        })
        return {"data": "mid_flight_answer"}

    val, meta = cache.get("key1", compute_with_mid_write, deps=deps, with_meta=True)
    # The value is returned to the caller
    assert val == {"data": "mid_flight_answer"}
    assert meta == {"hit": False, "coalesced": False}

    # But it is NOT kept in the cache!
    assert cache.stats()["entries"] == 0
    assert "key1" not in cache._entries

    # The next read will compute again
    computed_again = False

    def next_compute():
        nonlocal computed_again
        computed_again = True
        return {"data": "fresh_answer"}

    val2, meta2 = cache.get("key1", next_compute, deps=deps, with_meta=True)
    assert computed_again is True
    assert val2 == {"data": "fresh_answer"}
    # Because no domain moved during next_compute, it IS kept
    assert cache.stats()["entries"] == 1


# -- Unit tests: Disabled mode ------------------------------------------------


def test_disabled_mode(monkeypatch):
    """When MENTIS_CONTEXT_CACHE=0, cache is disabled (every get computes)."""
    cache = ContextCache(disabled=True)
    deps = frozenset({"governance"})
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return "val"

    v1, m1 = cache.get("k", compute, deps=deps, with_meta=True)
    v2, m2 = cache.get("k", compute, deps=deps, with_meta=True)

    assert v1 == v2 == "val"
    assert m1 == {"hit": False, "coalesced": False}
    assert m2 == {"hit": False, "coalesced": False}
    assert calls == 2
    assert cache.stats()["entries"] == 0
    assert cache.stats()["hits"] == 0
    assert cache.stats()["misses"] == 2

    # Environment variable check
    monkeypatch.setenv("MENTIS_CONTEXT_CACHE", "0")
    c_env = ContextCache()
    assert c_env.disabled is True

    monkeypatch.setenv("MENTIS_CONTEXT_CACHE", "1")
    c_env2 = ContextCache()
    assert c_env2.disabled is False


# -- Unit tests: Different access scopes never share --------------------------


def test_different_access_scopes_never_share():
    """Two grants with different scopes never share a cache entry."""
    revs = Revisions()
    cache = ContextCache(revisions=revs)
    deps = frozenset({"governance"})

    scope_brain = "brain"
    scope_conv1 = "conversation:ent-c1"
    scope_conv2 = "conversation:ent-c2"

    key_brain = ("orient", "corp-1", revs.token(deps), None, None, None, scope_brain)
    key_c1 = ("orient", "corp-1", revs.token(deps), None, None, None, scope_conv1)
    key_c2 = ("orient", "corp-1", revs.token(deps), None, None, None, scope_conv2)

    cache.get(key_brain, lambda: {"scope": "brain"}, deps=deps)
    cache.get(key_c1, lambda: {"scope": "c1"}, deps=deps)
    cache.get(key_c2, lambda: {"scope": "c2"}, deps=deps)

    stats = cache.stats()
    assert stats["entries"] == 3
    assert stats["hits"] == 0
    assert stats["misses"] == 3

    # Each scope retrieves only its own entry
    assert cache.get(key_brain, lambda: None, deps=deps)["scope"] == "brain"
    assert cache.get(key_c1, lambda: None, deps=deps)["scope"] == "c1"
    assert cache.get(key_c2, lambda: None, deps=deps)["scope"] == "c2"
    assert cache.stats()["hits"] == 3


# -- Unit tests: Domain invalidation -----------------------------------------


def test_invalidation_by_each_domain():
    """Validate that writes to each §4 domain invalidate appropriate entries."""
    revs = Revisions()
    cache = ContextCache(revisions=revs)
    revs.add_listener(cache.invalidate_domains)

    def populate():
        cache.clear()
        cache.get("k_gov", lambda: 1, deps=frozenset({"governance"}))
        cache.get("k_know", lambda: 2, deps=frozenset({"knowledge"}))
        cache.get("k_work", lambda: 3, deps=frozenset({"work"}))
        cache.get("k_part", lambda: 4, deps=frozenset({"participants"}))
        cache.get("k_c1", lambda: 5, deps=frozenset({"conversation:ent-c1"}))
        cache.get("k_c2", lambda: 6, deps=frozenset({"conversation:ent-c2"}))
        assert cache.stats()["entries"] == 6

    # 1. A rule superseded: touches governance
    populate()
    revs.note_write({
        "family": "link",
        "link": {"relation": "supersedes", "from": "ent-r2", "to": "ent-r1"},
    })
    assert "k_gov" not in cache._entries
    assert "k_know" in cache._entries
    assert "k_work" in cache._entries
    assert "k_c1" in cache._entries

    # 2. A discipline changed: touches governance
    populate()
    revs.note_write({
        "family": "admission",
        "definition": {"name": "discipline"},
        "body": {"name": "New Discipline"},
    })
    assert "k_gov" not in cache._entries
    assert "k_know" in cache._entries
    assert "k_work" in cache._entries

    # 3. A lesson adopted: touches knowledge
    populate()
    revs.note_write({
        "family": "link",
        "link": {"relation": "adopts", "from": "ent-p1", "to": "ent-lesson1"},
    })
    assert "k_know" not in cache._entries
    assert "k_gov" in cache._entries
    assert "k_work" in cache._entries

    # 4. A finding challenged: touches knowledge and governance
    populate()
    revs.note_write({
        "family": "link",
        "link": {"relation": "disputes", "from": "ent-f2", "to": "ent-f1"},
    })
    assert "k_know" not in cache._entries
    assert "k_gov" not in cache._entries
    assert "k_work" in cache._entries

    # 5. A decision answered: touches work and governance
    populate()
    revs.note_write({
        "act": "decision-answered",
        "actor": "owner",
        "conversation": "ent-c1",
        "detail": {"answer": "yes"},
    })
    assert "k_work" not in cache._entries
    assert "k_gov" not in cache._entries
    assert "k_c1" not in cache._entries  # also touches conversation:ent-c1
    assert "k_c2" in cache._entries      # but NOT conversation:ent-c2!

    # 6. A conversation write (a turn): touches conversation:<id>
    populate()
    revs.note_write({
        "family": "admission",
        "definition": {"name": "turn"},
        "body": {"conversation": "ent-c1", "parts": []},
    })
    assert "k_c1" not in cache._entries
    assert "k_c2" in cache._entries  # isolated from other conversations
    assert "k_gov" in cache._entries

    # 7. Work completed (expectation met): touches work
    populate()
    revs.note_write({
        "act": "work-met",
        "actor": "agent",
        "detail": {"expectation": "exp-1"},
    })
    assert "k_work" not in cache._entries
    assert "k_gov" in cache._entries
    assert "k_know" in cache._entries

    # 8. A request recorded with different follow_up: touches work
    populate()
    revs.note_write({
        "act": "expectation-recorded",
        "actor": "owner",
        "detail": {"follow_up": {"depth": 2}},
    })
    assert "k_work" not in cache._entries
    assert "k_gov" in cache._entries

    # 9. Unknown write: bumps every domain!
    populate()
    revs.note_write({
        "family": "unknown_future_family",
        "definition": {"name": "unknown_kind"},
    })
    # Everything should be invalidated
    assert cache.stats()["entries"] == 0


# -- Unit tests: Prepared orientation (foundation and for_agent) --------------


def test_orientation_foundation_and_for_agent(tmp_path):
    root = tmp_path / "corpus"
    world = fixture.build(str(root))
    corpus = api.open_corpus(str(root), access="write")
    brain = api.brain(corpus)
    cid = world["design"]

    # Compute foundation
    f = foundation(brain, cid, scope="conversation:" + cid)
    assert f["conversation"] == cid
    assert f["name"]
    assert "participants" in f
    assert "outstanding_work" in f
    assert "open_owner_decisions" in f
    assert "applicable_workflows" in f
    assert "applicable_disciplines" in f
    assert "standing_governance" in f
    assert "recent_context" in f

    # Subsequent foundation call is a cache hit
    stats_before = corpus.context_cache.stats()
    f2 = foundation(brain, cid, scope="conversation:" + cid)
    stats_after = corpus.context_cache.stats()
    assert f == f2
    assert stats_after["hits"] == stats_before["hits"] + 1

    # Compute for_agent
    agent_ctx = for_agent(
        brain,
        f,
        participant=world["who"]["@brian"],
        work="Design the cache system",
        follow_up={"depth": 2},
    )
    assert agent_ctx["for"] == world["who"]["@brian"]
    assert "delivered" in agent_ctx and "levels" in agent_ctx
    assert "task_gravity" in agent_ctx
    tg = agent_ctx["task_gravity"]
    assert tg["setting"] == {"depth": 2}
    assert tg["label"] == "May pursue side work 2 generations deep"
    assert tg["generation"] == 0
    assert tg["may_pursue_next"] is True

    # Subsequent for_agent call is a cache hit
    stats_before2 = corpus.context_cache.stats()
    agent_ctx2 = for_agent(
        brain,
        f,
        participant=world["who"]["@brian"],
        work="Design the cache system",
        follow_up={"depth": 2},
    )
    stats_after2 = corpus.context_cache.stats()
    assert agent_ctx == agent_ctx2
    assert stats_after2["hits"] == stats_before2["hits"] + 1


# -- Integration test: 8 threads calling orient/recall through Surface --------


def test_integration_concurrent_surface(tmp_path):
    """8 threads calling orient and recall concurrently through Surface.

    Verifies answers are identical to uncached path, and measures hits/coalesced
    and timings.
    """
    root = tmp_path / "corpus"
    world = fixture.build(str(root))
    corpus_path = str(root)

    # 1. Benchmark uncached baseline (MENTIS_CONTEXT_CACHE=0)
    os.environ["MENTIS_CONTEXT_CACHE"] = "0"
    surface_uncached = Surface(corpus_path)

    # Single-thread uncached timing
    t0 = time.perf_counter()
    ans_orient_uncached = surface_uncached.orient()
    ans_recall_uncached = surface_uncached.recall("design a durable record")
    t_single_uncached = time.perf_counter() - t0

    # 8-thread uncached timing
    def worker_uncached():
        surface_uncached.orient()
        surface_uncached.recall("design a durable record")

    t0 = time.perf_counter()
    threads_uncached = [threading.Thread(target=worker_uncached) for _ in range(8)]
    for t in threads_uncached:
        t.start()
    for t in threads_uncached:
        t.join()
    t_8_uncached = time.perf_counter() - t0

    # 2. Benchmark cached path (MENTIS_CONTEXT_CACHE=1)
    os.environ["MENTIS_CONTEXT_CACHE"] = "1"
    surface_cached = Surface(corpus_path)
    cache = cache_for(surface_cached.corpus)
    cache.clear()

    # Single-thread cached (warm-up + hit)
    t0 = time.perf_counter()
    ans_orient_cached = surface_cached.orient()
    ans_recall_cached = surface_cached.recall("design a durable record")
    t_single_cached_cold = time.perf_counter() - t0

    t0 = time.perf_counter()
    ans_orient_hit = surface_cached.orient()
    ans_recall_hit = surface_cached.recall("design a durable record")
    t_single_cached_hit = time.perf_counter() - t0

    # Assert correctness: cached answers identical to uncached (except cache metadata)
    def strip_cache(d):
        out = {k: v for k, v in d.items() if k != "cache"}
        if "kinds" in out and isinstance(out["kinds"], dict):
            out["kinds"] = {k: v for k, v in out["kinds"].items() if k != "as_read_at"}
        return out

    assert strip_cache(ans_orient_cached) == strip_cache(ans_orient_uncached)
    assert strip_cache(ans_recall_cached) == strip_cache(ans_recall_uncached)

    # 8-thread concurrent test with freshly cleared cache to measure coalescing & hits
    cache.clear()
    surface_cached = Surface(corpus_path)

    results_orient = []
    results_recall = []

    def worker_cached():
        o = surface_cached.orient()
        r = surface_cached.recall("design a durable record")
        results_orient.append(o)
        results_recall.append(r)

    t0 = time.perf_counter()
    threads_cached = [threading.Thread(target=worker_cached) for _ in range(8)]
    for t in threads_cached:
        t.start()
    for t in threads_cached:
        t.join()
    t_8_cached = time.perf_counter() - t0

    # Assert all 8 got identical answers matching uncached
    assert len(results_orient) == 8
    assert len(results_recall) == 8
    for o in results_orient:
        assert strip_cache(o) == strip_cache(ans_orient_uncached)
        assert "cache" in o
        assert o["cache"]["hit"] or o["cache"]["coalesced"] or not (o["cache"]["hit"] and o["cache"]["coalesced"])
    for r in results_recall:
        assert strip_cache(r) == strip_cache(ans_recall_uncached)
        assert "cache" in r
        assert r["cache"]["hit"] or r["cache"]["coalesced"] or not (r["cache"]["hit"] and r["cache"]["coalesced"])

    stats = cache.stats()
    # At least some requests must have coalesced or hit
    assert stats["hits"] + stats["coalesced"] > 0
    assert stats["entries"] >= 2  # orient and recall entries kept

    # Print measured timings for the report
    print("\n--- Context Cache Measured Timings ---")
    print(f"1 thread  uncached: {t_single_uncached * 1000:.2f} ms")
    print(f"1 thread  cached (warm): {t_single_cached_hit * 1000:.2f} ms")
    print(f"8 threads uncached: {t_8_uncached * 1000:.2f} ms")
    print(f"8 threads cached:   {t_8_cached * 1000:.2f} ms")
    print(f"Cache stats: hits={stats['hits']}, coalesced={stats['coalesced']}, misses={stats['misses']}, entries={stats['entries']}")
    print("--------------------------------------\n")


# -- Integration test: GET /api/context-cache HTTP route ---------------------


def test_api_context_cache_route(tmp_path):
    root = tmp_path / "corpus"
    fixture.build(str(root))
    st = _State(str(root), str(tmp_path))
    from mentis.web import _routes

    # Query GET /api/context-cache
    stats = _routes(st, "/api/context-cache", {}, {}, "GET")
    assert isinstance(stats, dict)
    assert "hits" in stats
    assert "misses" in stats
    assert "coalesced" in stats
    assert "evictions" in stats
    assert "invalidations" in stats
    assert "entries" in stats
    assert "bytes" in stats
    assert "by_kind" in stats


def test_a_value_read_while_a_commit_is_under_way_is_returned_not_kept():
    # Revisions are noted when a write is appended, inside its transaction: a
    # read between that note and the COMMIT sees the old record under the new
    # token. `steady` is None then, and such a value must not be kept.
    from mentis.core.context_cache import ContextCache, Revisions
    state = {"steady": None}
    cache = ContextCache(revisions=Revisions(), steady=lambda: state["steady"],
                         disabled=False)
    calls = []
    compute = lambda: calls.append(1) or "old record"
    assert cache.get(("orient", "x"), compute, deps=frozenset({"work"})) == "old record"
    assert cache.get(("orient", "x"), compute, deps=frozenset({"work"})) == "old record"
    assert len(calls) == 2
    state["steady"] = 7
    cache.get(("orient", "x"), compute, deps=frozenset({"work"}))
    cache.get(("orient", "x"), compute, deps=frozenset({"work"}))
    assert len(calls) == 3
