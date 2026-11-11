"""O7: the approved background behaviour is bounded (AGENTS.md "Background work").

The capacity/catalogue keeper only asks MARS while dispatches are recent and ends with the
service (`tests/test_execution_continuity.py` proves the activity bound); the bridge outbox
starts no thread of its own, resends only when the session itself calls or starts, and gives
up a kept write after `MAX_AGE_S`.
"""
import json
import threading
import time

from mentis import outbox as outbox_mod
from mentis.core import service as service_mod
from mentis.core.service import MentisService
from mentis.outbox import Outbox


class _Mars:
    generation = 1

    def __init__(self):
        self.asked = 0

    def backends(self):
        self.asked += 1
        return [{"id": "claude"}]

    def close(self):
        pass


def test_the_keeper_thread_ends_when_the_service_closes(tmp_path, monkeypatch):
    monkeypatch.setattr(service_mod, "KEEP_BACKENDS_S", 0.05)
    svc = MentisService(str(tmp_path / "instances"), execution=_Mars())
    svc.keep_current()
    keepers = [t for t in threading.enumerate() if t.name == "mentis-keep-current"]
    assert keepers, "the keeper runs"
    svc.close()
    for t in keepers:
        t.join(2)
    assert not any(t.is_alive() for t in keepers), "and stops with the service"


def test_an_idle_keeper_asks_mars_once_in_many_ticks(tmp_path, monkeypatch):
    monkeypatch.setattr(service_mod, "KEEP_BACKENDS_S", 0.01)
    ex = _Mars()
    svc = MentisService(str(tmp_path / "instances"), execution=ex)
    try:
        svc.keep_current()
        time.sleep(0.5)                       # ~50 ticks, no dispatch
        assert ex.asked == 1, f"idle: only the start-up prime, got {ex.asked}"
    finally:
        svc.close()


def test_the_outbox_starts_no_thread_and_gives_up_after_max_age(tmp_path):
    before = {t.ident for t in threading.enumerate()}
    box = Outbox("@Claude-CLI-TEST", str(tmp_path), "exe-1")
    assert box.hold()
    box.put("contribute", {"op_key": "fresh", "kind": "finding", "text": "x"})
    box.put("contribute", {"op_key": "old", "kind": "finding", "text": "y"})
    # age the second entry past the bound, as a week-old file would hold it
    lines = [json.loads(l) for l in open(box.path, encoding="utf-8")]
    for line in lines:
        if line["key"] == "old":
            line["at"] = time.time() - outbox_mod.MAX_AGE_S - 1
    with open(box.path, "w", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(l) + "\n" for l in lines))
    assert [p["key"] for p in box.pending()] == ["fresh"], "a kept write is given up after MAX_AGE_S"
    box.ack("fresh")
    assert box.pending() == []
    box.release()
    assert {t.ident for t in threading.enumerate()} <= before | {threading.get_ident()}, \
        "the outbox runs nothing in the background"
