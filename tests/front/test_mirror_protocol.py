"""The protocol between a real Python and a real front. `docs/rust/R3-mirror.md`, section 3. The state
machine's every row is `grants.rs`'s unit tests; this is what only real processes can show.
"""

from __future__ import annotations

import json
import shutil
import socket

from mentis.mirror import key_of
from tests.front.mirror_harness import (SECRET, ServerPython, http, read_as, wait_until, world,
                                        free_port)


def _push(port: int, body: bytes, secret: str | None = SECRET, peer=None) -> tuple[int, bytes]:
    headers = f"X-Mentis-Boot-Secret: {secret}\r\n" if secret else ""
    with socket.create_connection(("127.0.0.1", port), timeout=30) as sock:
        sock.sendall((f"POST /private/grants HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n{headers}"
                      f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
                      "Connection: close\r\n\r\n").encode() + body)
        got = b""
        while True:
            more = sock.recv(65536)
            if not more:
                break
            got += more
    head, _, answer = got.partition(b"\r\n\r\n")
    return int(head.split(b" ")[1]), answer


def _well_formed(boot: str, generation: int, key: str, grant=None) -> bytes:
    return json.dumps({"schema": 1, "boot_id": boot, "generation": generation, "key": key,
                       "grant": grant}).encode()


def _answered_count(w) -> int:
    return len(w.front.events("last-byte"))


def test_a_front_starts_holding_nothing_and_pulls_when_python_says(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        assert _answered_count(w) >= 1, "the world only comes up once it has answered"


def test_a_token_minted_after_the_pull_reaches_the_front_by_its_push(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        before = _answered_count(w)
        token = w.b.session()
        assert read_as(w.public, token)[0] == 200
        assert _answered_count(w) == before + 1, "no pull in between: the push put it there"


def test_a_revoked_token_gets_python_s_403_from_the_next_read(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        w.b.end_session(w.token)
        before = _answered_count(w)
        status, body = read_as(w.public, w.token)
        assert status == 403 and b"live worker grant" in body
        assert _answered_count(w) == before
        assert w.front.forwards()[-1] == "unknown token"


def test_a_push_refused_for_its_secret_is_a_404_and_changes_nothing(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        boot = w.b.boot()
        key = key_of(w.token)
        body = _well_formed(boot, 2, key)
        assert _push(w.public, body, secret="not it")[0] == 404
        assert _push(w.public, body, secret=None)[0] == 404
        w.wait_held(w.token, limit=2.0)


def test_a_malformed_push_discards_and_only_then_answers_400(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        for bad in (b"not json", b"[]", json.dumps({"schema": 9}).encode(),
                    _well_formed(w.b.boot(), 2, "NOT-HEX")):
            w.wait_held(w.token)
            status, _ = _push(w.public, bad)
            assert status == 400, bad
            # Discarded before the answer, so the very next read isn't the mirror's.
            before = _answered_count(w)
            assert read_as(w.public, w.token)[0] == 200, "Python answers it"
            assert _answered_count(w) == before, bad


def test_a_late_push_is_acked_and_changes_nothing(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        status, body = _push(w.public, _well_formed(w.b.boot(), 0, key_of(w.token)))
        assert (status, json.loads(body)) == (200, {"ok": True})
        w.wait_held(w.token, limit=2.0)


def test_a_gap_is_acked_discards_and_a_pull_mends_it(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        status, _ = _push(w.public, _well_formed(w.b.boot(), 99, key_of(w.token)))
        assert status == 200
        # The pull says generation 1, the waiting 99 is a gap, it pulls again; forwarding meanwhile.
        assert read_as(w.public, w.token)[0] == 200
        # A push beyond what Python has is never mended by a pull: nothing is held until the
        # position shows no regression, so a read keeps being Python's or the mirror's alike.
        assert read_as(w.public, w.token)[0] == 200


def test_a_push_from_another_boot_discards_and_a_pull_comes_back(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        assert _push(w.public, _well_formed("f" * 32, 1, key_of(w.token)))[0] == 200
        w.wait_held(w.token)


def test_a_new_boot_is_taken_up_by_its_first_mint(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        w.b.kill()
        replacement = w.python()
        replacement.wait_answering()
        token = replacement.session()
        w.wait_held(token)
        assert read_as(w.public, w.token)[0] == 403


def test_an_old_front_gets_a_404_for_a_push_and_python_carries_on(brain_seed, tmp_path):
    """A stand-in on the public port that answers every push 404: `down`, and no wait."""
    brain = tmp_path / "brain"
    shutil.copytree(brain_seed, brain)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    public = listener.getsockname()[1]

    def old_front():
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            with conn:
                conn.recv(65536)
                conn.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n"
                             b"Connection: close\r\n\r\n")

    import threading
    threading.Thread(target=old_front, daemon=True).start()
    port = free_port()
    python = ServerPython(brain, port, control=tmp_path / "c",
                          answers_at=f"http://127.0.0.1:{public}")
    try:
        python.wait_answering()
        token = python.session()
        status, body = http(port, "GET", "/private/grants/position",
                            headers={"X-Mentis-Boot-Secret": SECRET})
        assert status == 200 and json.loads(body)["down"] is True
        assert read_as(port, token)[0] == 200
        wait_until(lambda: python.answering(), limit=2)
    finally:
        python.end()
        listener.close()
