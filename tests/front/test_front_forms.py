"""The front against Python on request forms it could read differently, with no launcher and none of
R1's Python changes in the way: `contracts/launcher.md`'s step 4 by hand, on PY-ALONE. Not a row: it
needs only the front's binary, so it can run before integration. Row A has these cases on `PAIR`.

But for the forms Python now answers with its own 500 (`opr-f2ea91ab6992`), which PY-ALONE predates.
Those two compare a front with this clone's Python before it, as row A's do.

A second front stands before a recorder, which is the evidence for what a request carries: the
recorder keeps each head it is sent, and `X-Mentis-Boot-Secret` is either in it or not.

`MENTIS_R1_FRONT` names the binary, by default this clone's debug build.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import socket
import subprocess
import threading
import time
import unicodedata

import pytest

from tests.front import request_forms as forms
from tests.front.pair import PORT, PY_PORT, SPARE_PORTS, Answer, exchange
from tools.r1 import common, py_alone

SECRET = "forms-secret"
RECORDER_PORT, RECORDED_FRONT_PORT = SPARE_PORTS[:2]
PY_NOW_PORT, FRONT_OF_PY_NOW_PORT = SPARE_PORTS[2:4]
NO_SURFACE = b'{"error": "no such semantic surface"}'
_DEFAULT_FRONT = common.REPO / "target" / "debug" / "mentis-server.exe"


class Recorder:
    """Stands where Python goes, and keeps each head it is sent."""

    def __init__(self, port: int):
        self.heads: list[bytes] = []
        self.listener = socket.create_server(("127.0.0.1", port))
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                sock, _ = self.listener.accept()
            except OSError:
                return
            with sock:
                got = b""
                while b"\r\n\r\n" not in got:
                    more = sock.recv(1 << 16)
                    if not more:
                        break
                    got += more
                self.heads.append(got)
                sock.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")

    def take(self) -> list[bytes]:
        taken, self.heads = self.heads, []
        return taken

    def close(self):
        self.listener.close()


def front(brain, port: int, upstream: int, log: pathlib.Path) -> subprocess.Popen:
    exe = os.environ.get("MENTIS_R1_FRONT") or str(_DEFAULT_FRONT)
    with open(log, "ab") as out:
        started = subprocess.Popen(
            [exe, str(brain), "--host", "127.0.0.1", "--port", str(port),
             "--upstream", f"http://127.0.0.1:{upstream}", "--dist", str(common.dist_dir())],
            env={**os.environ, "MENTIS_BOOT_SECRET": SECRET}, stdout=out, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 30
    while True:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return started
        except OSError:
            assert started.poll() is None and time.monotonic() < deadline, f"see {log}"
            time.sleep(0.05)


@pytest.fixture(scope="module")
def recorder(brain_seed, tmp_path_factory):
    parent = tmp_path_factory.mktemp("forms")
    theirs, ours = parent / "py" / "brain", parent / "front" / "brain"
    theirs.parent.mkdir()
    ours.parent.mkdir()
    shutil.copytree(brain_seed, theirs)
    shutil.copytree(brain_seed, ours)
    listening = Recorder(RECORDER_PORT)
    with py_alone.running(theirs, port=PY_PORT):
        one = front(theirs, PORT, PY_PORT, parent / "front.log")
        two = front(ours, RECORDED_FRONT_PORT, RECORDER_PORT, parent / "recorded.log")
        try:
            yield listening
        finally:
            for started in (one, two):
                started.kill()
                started.wait(timeout=30)
            listening.close()


@pytest.fixture(scope="module")
def python_now(brain_seed, tmp_path_factory):
    """This clone's Python and a front before it, for the forms that differ from PY-ALONE by the
    owner's decision. `R1-acceptance.md`, "A"."""
    parent = tmp_path_factory.mktemp("forms-now")
    theirs, ours = parent / "py" / "brain", parent / "front" / "brain"
    theirs.parent.mkdir()
    ours.parent.mkdir()
    shutil.copytree(brain_seed, theirs)
    shutil.copytree(brain_seed, ours)
    with py_alone.running(theirs, port=PY_NOW_PORT, code=common.REPO):
        started = front(ours, FRONT_OF_PY_NOW_PORT, PY_NOW_PORT, parent / "front.log")
        try:
            yield
        finally:
            started.kill()
            started.wait(timeout=30)


def bytes_of(line: str, *headers: str) -> bytes:
    return "\r\n".join([line, "Host: localhost", "Connection: close", *headers, "", ""]).encode("latin-1")


def plain(method: str, target: str) -> bytes:
    return bytes_of(f"{method} {target} HTTP/1.1", *(["Content-Length: 0"] if method == "POST" else []))


def seen_by(recorder, data: bytes) -> list[bytes]:
    recorder.take()
    exchange(RECORDED_FRONT_PORT, data)
    return recorder.take()


def same_as_python(data: bytes) -> None:
    theirs = Answer(exchange(PY_PORT, data))
    ours = Answer(exchange(PORT, data))
    assert ours.comparable == theirs.comparable


def same_as_python_now(data: bytes) -> Answer:
    theirs = Answer(exchange(PY_NOW_PORT, data))
    ours = Answer(exchange(FRONT_OF_PY_NOW_PORT, data))
    assert ours.comparable == theirs.comparable
    return ours


def carries_proof(head: bytes) -> bool:
    return f"X-Mentis-Boot-Secret: {SECRET}".encode() in head


# -- the table, against this Python --------------------------------------------------------------


def test_the_targets_file_is_what_this_python_says():
    assert forms.TSV.read_text(encoding="ascii") == forms.table(), "--write it, and say why it moved"


def test_each_list_is_what_it_says_it_is():
    assert {forms.python_reads(t) for t in forms.PRIVATE_TARGETS} == {"private"}
    assert {forms.python_reads(t) for t in forms.ELSEWHERE_TARGETS} == {"elsewhere"}
    assert {forms.python_reads(t) for t in forms.RAISING_TARGETS} == {"raises"}


def test_no_latin_1_netloc_can_raise_under_nfkc():
    """`_checknetloc`'s other way to raise, which the front has no copy of because it can't happen:
    a head is Latin-1, and nothing in Latin-1 normalises to a character it looks for."""
    for code in range(0xa0, 0x100):
        assert not set(unicodedata.normalize("NFKC", chr(code))) & set("/?#@:"), hex(code)


# -- on the wire ---------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "POST", "OPTIONS"])
@pytest.mark.parametrize("target", forms.PRIVATE_TARGETS, ids=ascii)
def test_private_is_the_front_s_and_never_reaches_python(recorder, method, target):
    data = plain(method, target)
    got = Answer(exchange(PORT, data))
    assert got.status_line == "HTTP/1.1 404 Not Found", got
    assert got.body == NO_SURFACE, got
    assert seen_by(recorder, data) == []


@pytest.mark.parametrize("method", ["GET", "POST", "OPTIONS"])
@pytest.mark.parametrize("target", forms.ELSEWHERE_TARGETS, ids=ascii)
def test_elsewhere_is_python_s_answer_and_carries_the_proof(recorder, method, target):
    data = plain(method, target)
    same_as_python(data)
    seen = seen_by(recorder, data)
    assert len(seen) == 1 and carries_proof(seen[0]), seen


@pytest.mark.parametrize("method", ["GET", "POST", "OPTIONS"])
@pytest.mark.parametrize("target", forms.RAISING_TARGETS, ids=ascii)
def test_a_target_python_cannot_parse_goes_on_without_the_proof(recorder, python_now, method, target):
    data = plain(method, target)
    assert same_as_python_now(data).status == 500
    seen = seen_by(recorder, data)
    assert len(seen) == 1 and not carries_proof(seen[0]), seen


@pytest.mark.parametrize("target", forms.BARE_PRIVATE_TARGETS)
def test_http_0_9_under_private_is_the_front_s_body_alone(recorder, target):
    data = bytes_of(f"GET {target}")
    assert exchange(PORT, data) == NO_SURFACE
    assert seen_by(recorder, data) == []


@pytest.mark.parametrize("target", forms.BARE_ELSEWHERE_TARGETS)
def test_http_0_9_elsewhere_is_python_s_and_carries_the_proof(recorder, target):
    data = bytes_of(f"GET {target}")
    same_as_python(data)
    seen = seen_by(recorder, data)
    assert len(seen) == 1 and carries_proof(seen[0]), seen


def test_http_0_9_under_private_with_a_bad_header_is_python_s_refusal(recorder):
    data = bytes_of("GET /private/live", "no colon here")
    same_as_python(data)
    assert seen_by(recorder, data) == []


@pytest.mark.parametrize("line", forms.ODD_LINES)
def test_an_odd_line_is_python_s_refusal_and_needs_no_proof(recorder, line):
    data = bytes_of(line)
    same_as_python(data)
    assert not any(carries_proof(head) for head in seen_by(recorder, data))


@pytest.mark.parametrize("length", forms.ENORMOUS_LENGTHS)
@pytest.mark.parametrize("path", ["/api/conversations", "/fluid/api/posts", "/api/exchange/import/x",
                                  "/api/artifacts", "/api/no-such-route"])
def test_an_enormous_content_length_is_python_s_answer(python_now, path, length):
    got = same_as_python_now(bytes_of(f"POST {path} HTTP/1.1", "X-Mentis-Client: 1",
                                      "Content-Type: application/json", f"Content-Length: {length}"))
    assert got.status == (413 if path == "/api/artifacts" else 500), got
