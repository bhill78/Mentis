"""Python's half of the mirror. `docs/rust/R3-mirror.md`, sections 2 and 3, with a recorder where a
front goes: each mutator pushes or doesn't, in order, `down` or not, and fences from `last_confirmed`.
"""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest

from mentis import mirror as grant_mirror
from mentis.authority import Authority
from mentis.mirror import FENCE, PUSH_TIMEOUT, key_of
from mentis.worker import SESSION_SCOPE, TRANSIENT_SCOPE
from tests.front.mirror_harness import SECRET, ServerPython, free_port, http

CORPUS = "C:\\the-brain"


class Recorder:
    """A front's public port as far as a push goes: says what it's told to, and keeps what came."""

    def __init__(self, answer=b'{"ok": true}', status=b"200 OK", swallow=False):
        self.answer, self.status, self.swallow = answer, status, swallow
        self.seen: list[dict] = []
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(64)
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(conn,), daemon=True).start()

    def _one(self, conn):
        with conn:
            got = b""
            while b"\r\n\r\n" not in got:
                more = conn.recv(65536)
                if not more:
                    return
                got += more
            head, _, body = got.partition(b"\r\n\r\n")
            length = next(int(line.split(b":")[1]) for line in head.split(b"\r\n")
                          if line.lower().startswith(b"content-length"))
            while len(body) < length:
                body += conn.recv(65536)
            self.seen.append({"head": head.decode("latin-1"), **json.loads(body)})
            if self.swallow:
                time.sleep(2 * PUSH_TIMEOUT)
                return
            conn.sendall(b"HTTP/1.1 " + self.status + b"\r\nContent-Length: %d\r\nConnection: close"
                         b"\r\n\r\n%s" % (len(self.answer), self.answer))

    def close(self):
        self.listener.close()


@pytest.fixture
def recorder():
    made = Recorder()
    yield made
    made.close()


def authority(port: int) -> Authority:
    table = Authority()
    table.mirror = grant_mirror.Mirror(CORPUS, f"http://127.0.0.1:{port}", SECRET,
                                       "X-Mentis-Boot-Secret")
    return table


def test_python_alone_pushes_nothing_and_has_no_mirror():
    table = Authority()
    token = table._grant("a", CORPUS)
    table.authorise_for("a", {"scope": "organising"})
    table.revoke("a")
    assert table.mirror is None and token


def test_a_mint_pushes_a_set_and_is_not_fenced(recorder):
    table = authority(recorder.port)
    token = table._grant("a", CORPUS)
    seen = recorder.seen[-1]
    assert (seen["generation"], seen["key"]) == (1, key_of(token))
    assert seen["grant"] == {"corpus": CORPUS, "scope": "worker", "operations": None}
    assert "X-Mentis-Boot-Secret: " + SECRET in seen["head"]
    assert seen["schema"] == 1 and seen["boot_id"] == table.mirror.boot_id
    assert token not in json.dumps({k: v for k, v in seen.items() if k != "head"})


def test_a_grant_session_pushes_a_set(recorder):
    table = authority(recorder.port)
    token, _ = table.grant_session(CORPUS, runtime="claude", participant="p")
    assert recorder.seen[-1]["key"] == key_of(token)
    assert recorder.seen[-1]["grant"]["scope"] == SESSION_SCOPE


def test_authorise_for_pushes_only_what_the_mirror_holds_changing(recorder):
    table = authority(recorder.port)
    table._grant("a", CORPUS)
    assert len(recorder.seen) == 1
    # `delivered` alone (`web/dispatch.py:1824`) pushes nothing.
    table.authorise_for("a", {"delivered": ["ent-1"]})
    assert len(recorder.seen) == 1
    table.authorise_for("a", {"scope": "organising", "operations": ["delegate"]})
    assert len(recorder.seen) == 2
    assert recorder.seen[-1]["grant"]["operations"] == ["delegate"]
    # Before anything is minted, nothing is pushed.
    table.authorise_for("b", {"scope": "organising"})
    assert len(recorder.seen) == 2


def test_a_grant_that_can_no_longer_be_mirrored_is_a_drop(recorder):
    table = authority(recorder.port)
    table._grant("a", CORPUS)
    table.authorise_for("a", {"scope": TRANSIENT_SCOPE})
    assert recorder.seen[-1]["grant"] is None


def test_what_cannot_be_mirrored_is_never_pushed(recorder):
    table = authority(recorder.port)
    table.authorise_for("a", {"scope": TRANSIENT_SCOPE})
    table._grant("a", CORPUS)
    assert recorder.seen == []
    table.revoke("a")
    assert recorder.seen == [], "nothing was held, so nothing is dropped"
    assert table.mirror.generation == 0


def test_a_revoke_pushes_a_drop_only_if_a_token_was_spent(recorder):
    table = authority(recorder.port)
    table.revoke("nobody")
    assert recorder.seen == []
    token = table._grant("a", CORPUS)
    table.revoke("a")
    assert recorder.seen[-1]["key"] == key_of(token) and recorder.seen[-1]["grant"] is None


def test_end_session_pushes_a_drop_only_if_a_grant_ended(recorder):
    table = authority(recorder.port)
    assert table.end_session("nothing", CORPUS) is None
    assert recorder.seen == []
    token, _ = table.grant_session(CORPUS, runtime="claude", participant="p")
    assert table.end_session(token, CORPUS)["participant"] == "p"
    assert recorder.seen[-1]["grant"] is None


def test_pushes_go_in_table_order_under_many_threads(recorder):
    table = authority(recorder.port)
    threads = [threading.Thread(target=table._grant, args=(f"i{n}", CORPUS)) for n in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # Each push was answered before the next began, so what the recorder saw is what was sent.
    assert [seen["generation"] for seen in recorder.seen] == list(range(1, 31))


def test_every_mirrored_change_is_pushed_while_down(recorder):
    table = authority(recorder.port)
    table.mirror.down = True
    table._grant("a", CORPUS)
    table.revoke("a")
    assert len(recorder.seen) == 2


def _failing(port_status):
    return Recorder(answer=b"{}", status=port_status)


def test_any_answer_but_ok_true_sets_down():
    for recorder in (_failing(b"404 Not Found"), Recorder(answer=b'{"ok": false}')):
        table = authority(recorder.port)
        table._grant("a", CORPUS)
        assert table.mirror.down
        recorder.close()


def test_nothing_listening_costs_at_most_the_push_timeout():
    table = authority(free_port())
    began = time.perf_counter()
    table._grant("a", CORPUS)
    assert time.perf_counter() - began < PUSH_TIMEOUT + 0.25
    assert table.mirror.down


def test_with_nothing_ever_confirmed_a_failed_revoke_waits_for_nothing():
    """Old front, new Python: it never confirmed anything, so no lease can predate this."""
    recorder = _failing(b"404 Not Found")
    table = authority(recorder.port)
    table._grant("a", CORPUS)
    began = time.perf_counter()
    table.revoke("a")
    assert time.perf_counter() - began < 0.5
    recorder.close()


def test_a_failed_revoke_waits_until_last_confirmed_plus_the_fence():
    recorder = _failing(b"404 Not Found")
    table = authority(recorder.port)
    table._grant("a", CORPUS)
    table.mirror_position(1)
    table.mirror.down = False
    table.mirror_position(1)
    confirmed = table.mirror.last_confirmed
    table.revoke("a")
    assert time.perf_counter() >= confirmed + FENCE
    assert time.perf_counter() < confirmed + FENCE + 0.5
    recorder.close()


def test_a_later_revoke_during_an_outage_is_fenced_by_its_own_confirmations():
    """Section 4, row 5: its deadline covers every confirmation before its own `t`, and one measured
    from the first failure would be wrong."""
    recorder = _failing(b"404 Not Found")
    table = authority(recorder.port)
    table._grant("a", CORPUS)
    table._grant("b", CORPUS)
    # A pull clears `down` and confirms, then a position while not down does too.
    table.mirror_pull()
    time.sleep(0.2)
    table.mirror_position(1)
    confirmed = table.mirror.last_confirmed
    table.revoke("a")
    assert table.mirror.down
    assert time.perf_counter() >= confirmed + FENCE
    # `down` is set, so positions don't confirm, and a fence measured from an old confirmation
    # returns as soon as its push fails.
    table.mirror_position(1)
    assert table.mirror.last_confirmed == confirmed
    time.sleep(max(0.0, confirmed + FENCE - time.perf_counter()))
    began = time.perf_counter()
    table.revoke("b")
    assert time.perf_counter() - began < 0.5
    recorder.close()


def test_a_successful_revoke_doesn_t_wait(recorder):
    table = authority(recorder.port)
    table._grant("a", CORPUS)
    table.mirror_position(1)
    began = time.perf_counter()
    table.revoke("a")
    assert time.perf_counter() - began < 0.5


def test_a_fence_holds_no_lock():
    recorder = _failing(b"404 Not Found")
    table = authority(recorder.port)
    table._grant("a", CORPUS)
    table._grant("b", CORPUS)
    table.mirror_pull()
    fencing = threading.Thread(target=table.revoke, args=("a",))
    fencing.start()
    time.sleep(0.8)
    assert fencing.is_alive(), "it is fencing"
    assert table._changes.acquire(timeout=0.2), "`_changes` is free"
    table._changes.release()
    assert table._lock.acquire(timeout=0.2), "`_lock` is free"
    table._lock.release()
    began = time.perf_counter()
    assert table.grant_for("nothing", CORPUS) is None
    table.mirror_position(1)
    assert time.perf_counter() - began < 0.2
    fencing.join()
    recorder.close()


def test_a_grant_is_refused_from_the_moment_the_table_changes_during_a_push():
    recorder = Recorder(swallow=True)
    table = authority(recorder.port)
    token = table._grant("a", CORPUS)
    table.mirror.down = False
    revoking = threading.Thread(target=table.revoke, args=("a",))
    revoking.start()
    time.sleep(0.1)
    assert table.grant_for(token, CORPUS) is None
    revoking.join()
    recorder.close()


def test_a_pull_clears_down_and_confirms_and_holds_only_what_section_2_says(recorder):
    table = authority(recorder.port)
    token = table._grant("a", CORPUS)
    table.authorise_for("b", {"scope": TRANSIENT_SCOPE})
    table._grant("b", CORPUS)
    table.mirror.down = True
    pulled = table.mirror_pull()
    assert not table.mirror.down and table.mirror.last_confirmed is not None
    assert list(pulled["grants"]) == [key_of(token)]
    assert pulled["grants"][key_of(token)] == {"corpus": CORPUS, "scope": "worker",
                                               "operations": None}
    assert token not in json.dumps(pulled)
    assert set(pulled) == {"schema", "boot_id", "generation", "corpus", "grants"}


def test_a_position_while_down_confirms_nothing(recorder):
    table = authority(recorder.port)
    table.mirror.down = True
    position = table.mirror_position(9)
    assert position["down"] is True and position["pid"] == 9
    assert table.mirror.last_confirmed is None
    table.mirror.down = False
    table.mirror_position(9)
    assert table.mirror.last_confirmed is not None


def test_a_scope_not_a_string_is_not_mirrored(recorder):
    assert grant_mirror.mirrored({"corpus": "c", "scope": None, "operations": None}) is None
    assert grant_mirror.mirrored({"corpus": "c", "scope": 3, "operations": None}) is None
    assert grant_mirror.mirrored({"corpus": "c", "scope": "s", "operations": "x"}) is None
    assert grant_mirror.mirrored({"corpus": "c", "scope": "s", "operations": [1]}) is None
    assert grant_mirror.mirrored({"corpus": "c", "scope": "s", "operations": []})["operations"] == []


def test_the_routes_refuse_without_the_secret_and_python_alone_has_none(brain_seed, tmp_path):
    import shutil
    brain = tmp_path / "brain"
    shutil.copytree(brain_seed, brain)
    port = free_port()
    python = ServerPython(brain, port, control=tmp_path / "c")
    try:
        python.wait_answering()
        for path in ("/private/grants", "/private/grants/position"):
            assert http(port, "GET", path)[0] == 403
            assert http(port, "GET", path, headers={"X-Mentis-Boot-Secret": "wrong"})[0] == 403
            status, body = http(port, "GET", path, headers={"X-Mentis-Boot-Secret": SECRET})
            assert status == 200
            assert json.loads(body)["schema"] == 1
        token = python.session()
        for path in ("/private/grants", "/private/grants/position"):
            _, body = http(port, "GET", path, headers={"X-Mentis-Boot-Secret": SECRET})
            assert token.encode() not in body
        assert http(port, "POST", "/private/grants", {})[0] == 404, "the private port takes no push"
    finally:
        python.end()
    alone = tmp_path / "alone"
    shutil.copytree(brain_seed, alone)
    port = free_port()
    python = ServerPython(alone, port, control=tmp_path / "d", secret=None)
    try:
        python.wait_answering()
        assert not (alone / ".mentis.claim").exists()
        status, _ = http(port, "GET", "/private/grants", headers={"X-Mentis-Client": "1"})
        assert status != 403, "with no secret these paths mean what they always did"
    finally:
        python.end()
