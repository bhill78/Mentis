"""The reads every open view polls are answered again while nothing they read
has moved (mentis/web `_POLLED`, keyed by what `/api/pulse` compares).

A write, or a run this process holds moving, makes the next read compute
afresh; a route outside the polled set is never kept."""

from __future__ import annotations

import json
import urllib.request

import mentis.web as W
from tests._loop import a_conversation, say, world  # noqa: F401


def _get(world, path):
    req = urllib.request.Request(world["base"] + path, headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_a_polled_read_is_kept_until_the_record_moves(world, monkeypatch):
    calls = []
    real = W._routes

    def counting(st, path, *a, **k):
        if path == "/api/working":
            calls.append(path)
        return real(st, path, *a, **k)

    monkeypatch.setattr(W, "_routes", counting)
    W._POLLED._d.clear()
    first = _get(world, "/api/working")
    assert _get(world, "/api/working") == first
    assert len(calls) == 1
    cid = a_conversation(world, "Kept reads")
    say(world, cid, "a write moves the record")
    _get(world, "/api/working")
    assert len(calls) == 2


def test_other_routes_are_never_kept(world):
    W._POLLED._d.clear()
    _get(world, "/api/conversations")
    assert not [k for k in W._POLLED._d if k[2] == "/api/conversations"]


def test_fluid_polled_reads_are_kept_too(world, monkeypatch):
    import mentis.fluid as F
    calls = []
    real = F.route

    def counting(st, path, q):
        calls.append(path)
        return real(st, path, q)

    monkeypatch.setattr(F, "route", counting)
    W._POLLED._d.clear()
    a = _get(world, "/fluid/api/needs-you/items")
    assert _get(world, "/fluid/api/needs-you/items") == a and len(calls) == 1
    say(world, a_conversation(world, "Kept fluid"), "moves it")
    _get(world, "/fluid/api/needs-you/items")
    assert len(calls) == 2


def test_working_is_never_kept_past_its_second(world, monkeypatch):
    import time as T
    calls = []
    real = W._routes

    def counting(st, path, *a, **k):
        if path == "/api/working":
            calls.append(path)
        return real(st, path, *a, **k)

    monkeypatch.setattr(W, "_routes", counting)
    W._POLLED._d.clear()
    now = [1000.2]
    monkeypatch.setattr(W.time, "time", lambda: now[0])
    _get(world, "/api/working")
    _get(world, "/api/working")
    assert len(calls) == 1
    now[0] = 1001.3
    _get(world, "/api/working")
    assert len(calls) == 2


def test_a_run_mars_stops_reporting_is_not_kept_running(world, monkeypatch):
    W._POLLED._d.clear()
    running = {"inst-a"}
    monkeypatch.setattr(W, "_running", lambda st: set(running))
    k1 = W._polled_key(world["state"], "/fluid/api/needs-you/items", {})
    running.clear()
    assert W._polled_key(world["state"], "/fluid/api/needs-you/items", {}) != k1
