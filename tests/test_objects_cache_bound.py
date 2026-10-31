"""The object-extraction cache is bounded by what it holds, not by a count
smaller than one Conversation.

WHAT MUST HOLD:
  - a walk over more posts than the old 512-entry bound is served from cache
    the second time (Contents reads a whole Conversation's objects);
  - what is held never exceeds `CACHE_BYTES`, the oldest going first, and the
    accounting stays exact as entries come and go;
  - emptied from outside (as tests do), it starts its accounting again.
"""

from __future__ import annotations

import json

import pytest

from mentis.fluid import objects


@pytest.fixture
def fake(monkeypatch):
    runs = []

    def run(post, bundle):
        runs.append(post["id"])
        return ({"objects": [{"key": post["id"], "pad": "x" * post["pad"]}]},
                None, {"bundle": "test", "sha256": "0"})

    def input_of(corpus, root, version_entry, returned):
        return {"id": version_entry["id"], "pad": version_entry.get("pad", 10)}
    monkeypatch.setattr(objects, "_run", run)
    monkeypatch.setattr(objects, "input_of", input_of)
    objects._cache.clear()
    yield runs
    objects._cache.clear()


def _extract(i, pad=10):
    return objects.extract(None, f"p{i}", {"id": f"v{i}", "pad": pad},
                           returned=[], digest="d")


def test_a_walk_larger_than_the_old_bound_is_cached_the_second_time(fake):
    for i in range(1600):
        assert not _extract(i)["cached"]
    for i in range(1600):
        assert _extract(i)["cached"], i
    assert len(fake) == 1600


def test_what_is_held_stays_within_its_bytes(fake, monkeypatch):
    monkeypatch.setattr(objects, "CACHE_BYTES", 20_000)
    for i in range(200):
        _extract(i, pad=500)
    held = objects._held["bytes"]
    assert held <= objects.CACHE_BYTES
    assert held == sum(objects._sizes[k] for k in objects._cache)
    assert set(objects._sizes) == set(objects._cache)
    # the newest are kept, the oldest went first
    assert _extract(199, pad=500)["cached"]
    assert not _extract(0, pad=500)["cached"]


def test_emptied_from_outside_it_counts_again(fake):
    _extract(1)
    objects._cache.clear()
    _extract(2)
    assert objects._held["bytes"] == objects._sizes[next(iter(objects._cache))]
    assert objects._held["bytes"] == len(json.dumps(
        {"extracted": True, "objects": [{"key": "v2", "pad": "x" * 10}],
         "renderer": {"bundle": "test", "sha256": "0"}}))
