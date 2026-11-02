"""What the door says about a grant, on a real front and a real Python. `R3-mirror.md`, section 5.

Revoked, ended and other-corpus grants behave as on Python, a grant on another route still gets that
door's 403, and every "forward when" row goes to Python, which words each for itself.
"""

from __future__ import annotations

import json
import socket

from tests.front.mirror_harness import http, read_answer, read_as, world
from tests.front.test_mirror_protocol import _answered_count


def _raw(port: int, token: str | None, body: bytes, *, content_type="application/json",
         target="/api/worker", extra="") -> tuple[int, bytes]:
    grant = f"X-Mentis-Worker: {token}\r\n" if token else ""
    head = (f"POST {target} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-Mentis-Client: 1\r\n{grant}"
            f"Content-Type: {content_type}\r\nContent-Length: {len(body)}\r\n{extra}"
            f"Connection: close\r\n\r\n").encode("latin-1")
    with socket.create_connection(("127.0.0.1", port), timeout=60) as sock:
        sock.sendall(head + body)
        return read_answer(sock)


def _same_on_both(w, token, body, **options):
    """Python alone's answer, and through the front's door. Status and JSON have to agree."""
    direct = _raw(w.private, token, body, **options)
    through = _raw(w.public, token, body, **options)
    assert direct[0] == through[0], (direct, through)
    return through


def test_every_forward_row_goes_to_python_and_is_answered_as_python_would(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        token = w.token
        ask = json.dumps({"op": "capabilities"}).encode()
        answered = _answered_count(w)
        rows = {
            "a query": dict(body=ask, target="/api/worker?x=1"),
            "Expect": dict(body=ask, extra="X-Unrelated: 1\r\n"),
            "no grant": dict(body=ask, token=None),
            "not JSON's type": dict(body=ask, content_type="text/plain"),
            "not JSON": dict(body=b"{not json"),
            "not an object": dict(body=b"[1]"),
            "NaN": dict(body=b'{"op": "capabilities", "x": NaN}'),
            "op not a string": dict(body=b'{"op": 7}'),
            "op not moved": dict(body=b'{"op": "orient"}'),
            "args not an object": dict(body=b'{"op": "kinds", "args": 3}'),
            "another corpus": dict(body=json.dumps({"op": "kinds", "corpus": "C:\\nowhere"}).encode()),
            "ref missing": dict(body=b'{"op": "resolve", "args": {}}'),
            "a limit Python would coerce": dict(body=b'{"op": "history", "args": {"limit": "3"}}'),
        }
        for what, options in rows.items():
            options = dict(options)
            body = options.pop("body")
            presented = options.pop("token", token)
            try:
                _same_on_both(w, presented, body, **options)
            except AssertionError as differ:
                raise AssertionError(what) from differ
        # `Expect` isn't sent as a real one here, so only the rest are the door's to forward.
        assert _answered_count(w) == answered + 1, "the one with an unrelated header alone is answered"


def test_over_the_body_look_is_not_read_and_python_answers(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        answered = _answered_count(w)
        huge = json.dumps({"op": "capabilities", "pad": "x" * (1024 * 1024 + 1)}).encode()
        assert _raw(w.public, w.token, huge)[0] == 200
        assert _answered_count(w) == answered


def test_an_unknown_token_is_python_s_403(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        status, body = read_as(w.public, "no such token")
        assert status == 403 and b"live worker grant" in body


def test_an_ended_session_is_python_s_403(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        w.b.end_session(w.token)
        status, body = read_as(w.public, w.token)
        assert status == 403 and b"live worker grant" in body
        assert json.loads(body)["kind"] == "PermissionError"


def test_a_grant_on_another_route_gets_that_door_s_403(brain_seed, tmp_path):
    with world(brain_seed, tmp_path) as w:
        for path in ("/api/pulse", "/fluid/api/topics", "/api/server"):
            direct = http(w.private, "GET", path, headers={"X-Mentis-Worker": w.token,
                                                           "X-Mentis-Client": "1"})
            through = http(w.public, "GET", path, headers={"X-Mentis-Worker": w.token,
                                                           "X-Mentis-Client": "1"})
            assert direct[0] == through[0], path
            if path != "/api/server":
                assert through[0] == 403, path


def test_a_grant_the_mirror_holds_for_another_corpus_gets_the_same_403(brain_seed, tmp_path):
    """Python's words at `web/__init__.py:3046`, given by the door from a table it pulled. Only a push
    can make such a row: nothing else mints one."""
    from mentis.mirror import key_of
    from tests.front.test_mirror_protocol import _push, _well_formed
    with world(brain_seed, tmp_path) as w:
        token = "a token on another corpus"
        grant = {"corpus": "C:\\another", "scope": "worker", "operations": None}
        # The next generation after the world's one change.
        assert _push(w.public, _well_formed(w.b.boot(), 2, key_of(token), grant))[0] == 200
        before = _answered_count(w)
        status, body = read_as(w.public, token)
        assert status == 403
        assert json.loads(body) == {"error": "this question needs a live worker grant for this corpus",
                                    "kind": "PermissionError"}
        assert _answered_count(w) == before + 1, "it was the door's"
