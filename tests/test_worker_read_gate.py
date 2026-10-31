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
