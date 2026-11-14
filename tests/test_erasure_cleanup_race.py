"""Integrated review C1: deferred cleanup must never remove bytes a NEW holder
in another conversation committed while the cleanup was running, and must
never let an Admission commit over bytes it removed."""
import threading

from mentis import artifacts
from mentis.conversation import erasure as ER
from mentis.spine import held

from tests.test_conversation_erasure import _post_file, trash, world  # noqa: F401


def _start_delete(world):
    trash(world)
    cv, cid = world["cv"], world["c"]
    return ER.delete(cv, cid, by=world["me"],
                     token=ER.impact(cv, cid)["token"], cleanup_later=True)


def _finish(world):
    t = ER.cleanup_thread(world["c"])
    t.join(20)
    assert not t.is_alive()
    return ER.cleanup_status(world["cv"], world["c"])


def test_a_holder_committed_before_the_check_keeps_its_bytes(world, monkeypatch):
    _, _, digest = world["files"]["x"]
    data = held.read(world["root"], digest)
    entered, release = threading.Event(), threading.Event()
    real = ER._clean_files

    def wait_first(c, files):
        entered.set()
        assert release.wait(20)
        return real(c, files)
    monkeypatch.setattr(ER, "_clean_files", wait_first)
    got = _start_delete(world)
    assert got["deleted"] and entered.wait(20)
    try:
        post, adm, d2 = _post_file(world["cv"], world["corpus"], world["other"],
                                   world["me"], data, "still-needed.txt")
        assert d2 == digest
    finally:
        release.set()
    status = _finish(world)
    assert status["status"] == "completed", status
    assert held.path(world["root"], digest).is_file()
    desc = artifacts.describe(world["corpus"], adm, verify=True)
    assert desc["state"] != "held-but-missing", desc
    assert held.read(world["root"], digest) == data
    assert world["corpus"].verify_chain()["intact"]


def test_a_holder_arriving_during_the_unlink_is_refused_not_orphaned(
        world, monkeypatch):
    """The reviewer's sequence: cleanup has read the holders; the same bytes
    are attached to another conversation. The poster waits for the lock; when
    it gets it the bytes are gone, so it is refused -- no Admission is ever
    committed over missing bytes -- and cleanup's `completed` is true."""
    _, _, digest = world["files"]["x"]
    data = held.read(world["root"], digest)
    seen, release = threading.Event(), threading.Event()
    real = ER._live_digests

    def pause_after_read(c, digests):
        out = real(c, digests)
        seen.set()
        assert release.wait(20)
        return out
    monkeypatch.setattr(ER, "_live_digests", pause_after_read)
    got = _start_delete(world)
    assert got["deleted"] and seen.wait(20)
    result = {}

    def poster():
        try:
            result["post"] = _post_file(world["cv"], world["corpus"],
                                        world["other"], world["me"], data,
                                        "still-needed.txt")
        except Exception as exc:                            # noqa: BLE001
            result["error"] = exc
    t = threading.Thread(target=poster)
    t.start()
    t.join(0.5)
    assert t.is_alive(), "the poster must wait for cleanup's write lock"
    release.set()
    t.join(20)
    assert not t.is_alive()
    status = _finish(world)
    assert world["corpus"].verify_chain()["intact"]
    if "post" in result:
        _, adm, _ = result["post"]
        desc = artifacts.describe(world["corpus"], adm, verify=True)
        assert desc["state"] != "held-but-missing", desc
        assert held.read(world["root"], digest) == data
    else:
        assert "attach it again" in str(result["error"]) \
            or "no bytes are held" in str(result["error"]), result["error"]
        assert status["status"] == "completed", status
        assert not held.path(world["root"], digest).exists()
