"""Row J's refusal evidence: a reverse proxy the harness owns, between the front and Python.

The front's `--upstream` is this. So what Python answered and when reach the harness without passing
through the front, and nothing the front writes, anywhere, can add to them: the lines are held in
this process's memory, not in a file. A front that goes round it, or invents an answer, leaves no
line, and its `NotPermitted` then fails `restart_messages.decide`.

It lives in the test process, which is never killed, so it outlives a front restart and a front
kill. Python stays up through both, as J6 and J7 do. It changes no Python and is in no production
path.

It carries bytes and judges nothing. It reads each exchange's path, status and length, and the
headers go on unchanged, the boot secret and the peer included, with none of its own added. Python
frames every answer with Content-Length or by closing, so that is all it has to carry, and the
front's own framing checks stand before it.
"""

from __future__ import annotations

import http.client
import http.server
import threading
import time

CHUNK = 64 * 1024
WORKER_DOOR = "/api/worker"


class _Carry(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = ""
    sys_version = ""
    disable_nagle_algorithm = True

    def _carry(self) -> None:
        received_at = time.time()  # before Python can have anything of this call
        upstream = http.client.HTTPConnection("127.0.0.1", self.server.python_port)
        try:
            upstream.putrequest(self.command, self.path, skip_host=True,
                                skip_accept_encoding=True)
            for name, value in self.headers.items():
                upstream.putheader(name, value)
            upstream.endheaders()
            left = int(self.headers.get("Content-Length") or 0)
            while left:
                chunk = self.rfile.read(min(left, CHUNK))
                if not chunk:  # the front died mid-body, so Python never gets the whole request
                    self.close_connection = True
                    return
                upstream.send(chunk)
                left -= len(chunk)
            answer = upstream.getresponse()
            first = b""
            if (answer.status == 403 and self.command == "POST"
                    and self.path.split("?", 1)[0] == WORKER_DOOR):
                # Read whole and held before a byte is relayed, so a message an agent saw has its
                # line, and a front that dies now still leaves the fact that Python answered.
                first = answer.read()
                self.server.recorder.answered(received_at, time.time(), first)
            self.wfile.write(
                f"HTTP/1.1 {answer.status} {answer.reason}\r\n".encode("latin-1"))
            for name, value in answer.getheaders():
                self.wfile.write(f"{name}: {value}\r\n".encode("latin-1"))
            self.wfile.write(b"\r\n")
            self.wfile.write(first)
            self.wfile.flush()
            while chunk := answer.read1(CHUNK):
                self.wfile.write(chunk)
                self.wfile.flush()
            self.close_connection = answer.will_close
        except (OSError, http.client.HTTPException):
            self.close_connection = True  # either side's end shows as the other's end
        finally:
            upstream.close()

    do_GET = do_POST = do_OPTIONS = do_HEAD = do_PUT = do_DELETE = _carry

    def log_message(self, *args) -> None:
        pass


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128

    def handle_error(self, request, client_address) -> None:
        pass  # a killed front is what this is for


class DoorRecorder:
    """Carries the front's calls to Python on `python_port`. `url` is the front's `--upstream`.

    `refusals` holds one `{"received_at", "answered_at", "body"}` per 403 Python answered on
    `POST /api/worker`: the times bound the call, Unix seconds from `time.time`, the clock the
    Brain's rows are stamped with, and `body` is the whole answer as `_over` decodes it.
    """

    def __init__(self, python_port: int):
        self._lock = threading.Lock()
        self._refusals: list[dict] = []
        self._server = _Server(("127.0.0.1", 0), _Carry)
        self._server.python_port = python_port
        self._server.recorder = self
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> DoorRecorder:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)

    def answered(self, received_at: float, answered_at: float, body: bytes) -> None:
        with self._lock:
            self._refusals.append({"received_at": received_at, "answered_at": answered_at,
                                   "body": body.decode("utf-8", "replace")})

    @property
    def refusals(self) -> list[dict]:
        with self._lock:
            return list(self._refusals)
