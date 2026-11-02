"""P1.5-J4-before: what `_over` says at PY_COMMIT when the far side stops mid-call. No front.

    <fixtures>\\venv\\Scripts\\python.exe tests/front/probe_j4_before.py > docs/rust/evidence/j4-before.json

`_over` is imported from the detached PY-ALONE checkout, whatever clone this is run from, so it
says what the words were before R1 changed them. It decides nothing: J4's assertions are R1's
result (`docs/rust/R1-acceptance.md`, "What P1.5 owes"). `j4` is the row's scenario. The others are
the rest of "Case B in detail" in `docs/rust-front-restart.md`, and the ways a reply can be cut
that the page doesn't name, so a path it doesn't list shows here.

Not collected by pytest: it has no `test_` in its name, and no row counts it.
"""

from __future__ import annotations

import json
import pathlib
import socket
import struct
import sys
import threading

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "tools" / "r1"))
import common  # noqa: E402

sys.path.insert(0, str(common.code_dir()))
sys.path.insert(1, str(HERE))
from mentis import worker  # noqa: E402
import restart_messages  # noqa: E402

CORPUS = "C:\\b\\brain"
#: Bigger than any socket buffer, so that sending blocks and meets the reset.
LARGE = "x" * (64 << 20)
JSON_HEAD = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 15\r\n\r\n"
REFUSED_HEAD = (b"HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\n"
                b"Content-Length: 15\r\n\r\n")


def read_request(conn: socket.socket) -> None:
    data = b""
    while b"\r\n\r\n" not in data:
        data += conn.recv(65536)
    head, _, body = data.partition(b"\r\n\r\n")
    length = next(int(line.split(b":")[1]) for line in head.split(b"\r\n")
                  if line.lower().startswith(b"content-length:"))
    while len(body) < length:
        body += conn.recv(65536)


def reset(conn: socket.socket) -> None:
    """An RST, as a killed process's socket with unread or unsent data gives."""
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("hh", 1, 0))
    conn.close()


def after_request(then):
    def stand_in(conn: socket.socket) -> None:
        read_request(conn)
        then(conn)
    return stand_in


def replying(data: bytes, end):
    def then(conn: socket.socket) -> None:
        conn.sendall(data)
        end(conn)
    return then


def while_sending(conn: socket.socket) -> None:
    conn.recv(1024)
    reset(conn)


#: name: (what the stand-in does, what the call sends)
SCENARIOS = {
    "j4": (after_request(reset), "the row's: reset after the whole request, nothing answered"),
    "closed_after_sending": (after_request(socket.socket.close),
                             "closed after the whole request, nothing answered"),
    "reset_while_sending": (while_sending, "reset while a large request is being sent"),
    "body_cut_by_close": (after_request(replying(JSON_HEAD + b'{"a":', socket.socket.close)),
                          "a 200's body cut short, by a close"),
    "body_cut_by_reset": (after_request(replying(JSON_HEAD + b'{"a":', reset)),
                          "a 200's body cut short, by a reset"),
    "refusal_body_cut_by_close": (after_request(replying(REFUSED_HEAD + b'{"a":',
                                                         socket.socket.close)),
                                  "a 403's body cut short, by a close"),
    "status_line_cut_by_close": (after_request(replying(b"HTTP/1.", socket.socket.close)),
                                 "the status line cut short, by a close"),
    "status_line_cut_by_reset": (after_request(replying(b"HTTP/1.", reset)),
                                 "the status line cut short, by a reset"),
    "headers_cut_by_close": (after_request(replying(b"HTTP/1.1 200 OK\r\nContent-Ty",
                                                    socket.socket.close)),
                             "the headers cut short, by a close"),
    "headers_cut_by_reset": (after_request(replying(b"HTTP/1.1 200 OK\r\nContent-Ty", reset)),
                             "the headers cut short, by a reset"),
}


def run(stand_in, args: dict) -> dict:
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]

    def serve() -> None:
        conn, _ = listener.accept()
        try:
            stand_in(conn)
        except OSError:
            pass
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        result = worker._over(f"http://127.0.0.1:{port}", CORPUS, "answer", args, "grant")
        return {"returned": result}
    except Exception as exc:  # noqa: BLE001  serve's catch-all, which is what the agent reads
        told = f"{type(exc).__name__}: {exc}".replace(str(port), "{port}")
        cause = exc.__cause__
        return {"raised": type(exc).__name__,
                "cause": type(cause).__name__ if cause else None,
                "told": told,
                "allowed_by_r1_list": restart_messages.decide(told)}
    finally:
        thread.join(timeout=10)
        listener.close()


def main() -> int:
    out: dict = {
        "code_commit": common.head_of(common.code_dir()),
        "over_from": pathlib.Path(worker.__file__).as_posix(),
        "python": sys.version.split()[0],
        "decides_nothing": "J4's assertions are R1's result; this is what was there before",
        "scenarios": {},
    }
    if not out["code_commit"].startswith(common.PY_COMMIT):
        raise SystemExit(f"{out['code_commit']} isn't {common.PY_COMMIT}")
    for name, (stand_in, what) in SCENARIOS.items():
        args = {"text": LARGE} if name == "reset_while_sending" else {}
        out["scenarios"][name] = {"what": what, **run(stand_in, args)}
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
