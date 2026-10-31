"""Agent reads take turns only where they cost seconds.

WHAT MUST HOLD, against a real HTTP server and the real `/api/worker` door:
  - while a heavy read holds the gate, a cheap read (`resolve`, `history`)
    is answered at once -- it never waits for the turn it does not need;
  - a heavy read (`orient`) still waits for the gate, and is answered once
    the gate is free;
  - the cheap set is reads only: nothing in it can write.
"""

from __future__ import annotations

import threading
import time

from mentis.conversation import text
from mentis.worker import READ_ONLY
from mentis.web import _UNGATED_READS, _WORKER_READ_GATE
from tests.test_agent_access_reads import _session
from tests.test_manual_session import world  # noqa: F401


def test_the_ungated_reads_are_reads():
    assert _UNGATED_READS <= set(READ_ONLY)


def test_a_cheap_read_does_not_wait_for_a_heavy_one(world):
    st = world["st"]
    cid = st.cv.open_conversation("Gate", attributed_to=world["owner"])
    turn = st.cv.say(cid, world["owner"], [text("hello")])
    _, op = _session(world)

    assert _WORKER_READ_GATE.acquire(timeout=5)   # a heavy read is running
    heavy = {}
    try:
        t0 = time.monotonic()
        status, got = op("resolve", ref=turn)
        assert status == 200, got
        status, got = op("history", conversation=cid)
        assert status == 200, got
        assert time.monotonic() - t0 < 5, "a cheap read waited for the gate"

        def ask():
            heavy["got"] = op("orient", conversation=cid)
        waiting = threading.Thread(target=ask)
        waiting.start()
        waiting.join(timeout=1.0)
        assert waiting.is_alive(), "a heavy read did not wait for its turn"
    finally:
        _WORKER_READ_GATE.release()
    waiting.join(timeout=30)
    assert not waiting.is_alive()
    assert heavy["got"][0] == 200, heavy["got"]


def test_owner_decisions_does_not_wait_for_a_heavy_read(world):
    st = world["st"]
    cid = st.cv.open_conversation("Gate decisions", attributed_to=world["owner"])
    _, op = _session(world)
    assert _WORKER_READ_GATE.acquire(timeout=5)
    try:
        t0 = time.monotonic()
        status, got = op("owner_decisions", conversation=cid)
        assert status == 200, got
        assert time.monotonic() - t0 < 5
    finally:
        _WORKER_READ_GATE.release()


def test_a_read_that_cannot_get_its_turn_in_time_is_answered_busy_and_not_run(
        world, monkeypatch):
    """Before, it waited however long the turn took and then ran -- minutes
    after the worker had given up at 30 s, holding the turn the next read
    needed (2026-10-31). Now it is told "busy" while the worker still listens,
    and nothing runs for it."""
    import mentis.web as web
    import mentis.worker as worker
    st = world["st"]
    cid = st.cv.open_conversation("Gate busy", attributed_to=world["owner"])
    _, op = _session(world)
    monkeypatch.setattr(web, "_READ_TURN_WAIT_S", 0.5)
    ran = []
    real = worker._result
    monkeypatch.setattr(worker, "_result",
                        lambda s, name, args, **kw: (ran.append(name),
                                                     real(s, name, args, **kw))[1])
    assert web._READ_TURN_WAIT_S < worker.ASK_TIMEOUT_S
    assert _WORKER_READ_GATE.acquire(timeout=5)
    try:
        t0 = time.monotonic()
        status, got = op("orient", conversation=cid)
        assert time.monotonic() - t0 < 5
    finally:
        _WORKER_READ_GATE.release()
    assert status == 503, got
    assert "busy" in str(got).lower() and "nothing was done" in str(got)
    assert "orient" not in ran
    # and the turn is free again: the next read is answered
    status, got = op("orient", conversation=cid)
    assert status == 200, got


def test_the_turn_wait_is_well_inside_the_worker_s_timeout():
    import mentis.web as web
    import mentis.worker as worker
    assert web._READ_TURN_WAIT_S <= worker.ASK_TIMEOUT_S - 5
