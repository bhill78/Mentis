"""A Python handler that raises on a whole request: what happens TODAY, through the front and alone.

THE EXPECTED ANSWER HERE IS PENDING THE OWNER'S DECISION (`opr-f2ea91ab6992`, what a silent close
from Python should mean). This freezes the evidence, not the behaviour. It is no row of
`R1-acceptance.md`, it doesn't say the difference below is right, and whichever way that decision
goes this test is to change with it. Today the two differ: Python alone closes with no answer, and
the front answers its 503 that Python stopped.

The request is `ent-cc5f27261d53`'s: `do_POST` doesn't catch `json.loads`.
"""

from __future__ import annotations

import shutil

from tests.front.pair import (FRONT_503, PY_PORT, Answer, Pair, advance, ask, exchange, process_tree,
                              request)
from tools.r1 import py_alone

BAD_JSON = (b"POST /api/conversations HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"X-Mentis-Client: 1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 2\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"{x")
#: In both logs, whole, once for this one request. `socketserver`'s `handle_error` prints it.
IN_THE_LOG = ("Exception occurred during processing of request from ('127.0.0.1', ",
              "in do_POST",
              "json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: "
              "line 1 column 2 (char 1)")


def logged_once(text: str) -> None:
    for words in IN_THE_LOG:
        assert text.count(words) == 1, (words, text)


def test_pending_owner_decision_a_handler_that_raises_is_silent_alone_and_503_through_the_front(
        brain_seed, tmp_path):
    alone_copy, pair_copy = tmp_path / "alone" / "brain", tmp_path / "pair" / "brain"
    shutil.copytree(brain_seed, alone_copy)
    shutil.copytree(brain_seed, pair_copy)

    run_dir = tmp_path / "alone" / "run"
    with py_alone.running(alone_copy, port=PY_PORT, run_dir=run_dir) as alone:
        assert exchange(PY_PORT, BAD_JSON, wait=20.0) == b"", "Python alone closes with no answer"
        assert alone.poll() is None, "and goes on"
        assert ask(PY_PORT, "GET", "/api/server").status == 200
    logged_once((run_dir / "server.log").read_text(encoding="utf-8", errors="replace"))

    with Pair(pair_copy) as pair:
        python, tree, before = pair.python_pid, process_tree(pair.python_pid), advance(pair.brain)
        through = Answer(exchange(pair.port, BAD_JSON, wait=20.0))
        words = (b'{"error": "' + FRONT_503["Python-reached"].encode() + b'"}')
        assert through.comparable == ("HTTP/1.1 503 Service Unavailable", [
            ("Server", through.header("Server")), ("Connection", "close"),
            ("Content-Type", "application/json"), ("Content-Length", str(len(words))),
            ("Cache-Control", "no-store")], words), through.raw
        assert through.header("Server").startswith("BaseHTTP/0.6 Python/")

        # Nothing else happened: the same process, on the same port, and nothing in the record.
        assert pair.python_pid == python and process_tree(python) == tree
        assert exchange(pair.private_port, request("GET", "/api/server"))[:15] == b"HTTP/1.1 200 OK"
        assert ask(pair.port, "GET", "/api/server").status == 200
        assert advance(pair.brain) == before
        logged_once((pair.run_dir / "python.log").read_text(encoding="utf-8", errors="replace"))
