"""R4.2's real-data comparison, adapted from the independent review's harness (ent-4948a71f27a0).

Real Python and the front under test on one backup-API copy of a Brain. The front's upstream is a proxy
that passes `/private/live` to Python and answers 599 to anything else, so a 599 is exactly a forward.

    R42_FRONT   the mentis-server.exe under test
    R42_PYTHON  the Python to run `mentis.web` with (default: the R1 fixtures' venv)

Run from anywhere; a Brain is only ever opened at the path given, and `mkcopy.py` refuses the live one.
"""
import http.client
import json
import os
import pathlib
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = "r42-compare"
CODE = str(pathlib.Path(__file__).resolve().parents[2])
FRONT = os.environ.get("R42_FRONT", "")
FIXTURES = os.environ.get("MENTIS_R1_FIXTURES", r"C:\Work\Mentis-workspace\r1-fixtures")
PY = os.environ.get("R42_PYTHON", str(pathlib.Path(FIXTURES) / "venv" / "Scripts" / "python.exe"))
HERE = pathlib.Path(__file__).resolve().parent


class Proxy:
    """mode: pass | hang | hold. edit: rewrites a poll's JSON. forward=True carries everything to
    Python. `hold` leaves a poll unanswered until `release`; `edit_once` changes the next poll's answer
    and then holds, so what it left the front with stays."""

    def __init__(self, port, py_port):
        self.py_port = py_port
        self.mode = "pass"
        self.forward = False
        self.forwarded = 0
        self.polls = 0
        self.edit = None
        self.once = None
        self.released = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _send(self, status, body, ctype="application/json"):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _python(self, timeout):
                c = http.client.HTTPConnection("127.0.0.1", outer.py_port, timeout=timeout)
                sent = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                c.request(self.command, self.path, body=sent or None,
                          headers={k: v for k, v in self.headers.items() if k.lower() != "host"})
                r = c.getresponse()
                body = r.read()
                status, ctype = r.status, r.getheader("Content-Type", "application/json")
                c.close()
                return status, body, ctype

            def do_GET(self):  # noqa: N802
                if self.path.startswith("/private/live"):
                    outer.polls += 1
                    if outer.mode == "hang":
                        time.sleep(1.0)
                        self.close_connection = True
                        return
                    if outer.mode == "hold":
                        outer.released.wait()
                    status, body, ctype = self._python(5)
                    change, outer.once = outer.once, None
                    if change:
                        outer.mode = "hold"
                    for edit in (outer.edit, change):
                        if edit and status == 200:
                            doc = json.loads(body)
                            edit(doc)
                            body = json.dumps(doc).encode()
                    return self._send(status, body, ctype)
                outer.forwarded += 1
                if outer.forward:
                    status, body, ctype = self._python(120)
                    return self._send(status, body, ctype)
                return self._send(599, b"FORWARDED", "text/plain")

            do_POST = do_GET  # noqa: N815

        self.srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def hold(self):
        self.released.clear()
        self.mode = "hold"

    def edit_once(self, change):
        self.released.clear()
        self.once = change

    def release(self):
        self.mode = "pass"
        self.released.set()


def wait(port, limit=300):
    started = time.time()
    while time.time() - started < limit:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=.3).close()
            return
        except OSError:
            time.sleep(.1)
    raise SystemExit(f"nothing on {port}")


def get(port, target, timeout=300):
    """(status, body, seconds, content type), the body as the bytes the wire held."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}{target}",
                                 headers={"X-Mentis-Client": "1"})
    gave_up_at = time.monotonic() + 240
    while True:
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return (r.status, r.read(), time.perf_counter() - started,
                        r.headers.get("Content-Type"))
        except urllib.error.HTTPError as e:
            return e.code, e.read(), time.perf_counter() - started, e.headers.get("Content-Type")
        except urllib.error.URLError as e:
            # Thousands of one-shot connections use up the ephemeral ports: wait for TIME_WAIT.
            if getattr(e.reason, "winerror", None) != 10048 or time.monotonic() > gave_up_at:
                raise
            time.sleep(1.0)


def walk(a, b, at=""):
    """Every place two decoded answers differ."""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append((f"{at}.{k}", "<absent>", b[k]))
            elif k not in b:
                out.append((f"{at}.{k}", a[k], "<absent>"))
            else:
                out += walk(a[k], b[k], f"{at}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((f"{at}[len]", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            out += walk(x, y, f"{at}[{i}]")
    elif a != b or type(a) is not type(b):
        out.append((at, a, b))
    return out


def start_front(root, port, upstream_port, out, log):
    env = {**os.environ, "MENTIS_BOOT_SECRET": SECRET}
    front = subprocess.Popen([FRONT, str(root), "--host", "127.0.0.1", "--port", str(port),
                              "--upstream", f"http://127.0.0.1:{upstream_port}",
                              "--dist", str(out)], env=env, stdout=log, stderr=log)
    wait(port)
    return front


class Pair:
    """Python on `base`, the proxy on `base + 1`, the front on `base + 2`, and a pulse keeping it polled."""

    def __init__(self, root, out, base):
        self.out = pathlib.Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.pp, self.xp, self.fp = base, base + 1, base + 2
        env = {**os.environ, "MENTIS_BOOT_SECRET": SECRET, "PYTHONPATH": CODE,
               "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("MENTIS_R1_PORTS", None)
        self.pl = open(self.out / "py.log", "w")
        self.fl = open(self.out / "fr.log", "w")
        started = time.time()
        self.py = subprocess.Popen([PY, "-m", "mentis.web", str(root), "--host", "127.0.0.1",
                                    "--port", str(self.pp), "--workspace", str(self.out / "ws")],
                                   cwd=CODE, env=env, stdout=self.pl, stderr=self.pl)
        wait(self.pp)
        get(self.pp, "/api/server")
        print("python up", round(time.time() - started, 1), flush=True)
        self.proxy = Proxy(self.xp, self.pp)
        self.front = start_front(root, self.fp, self.xp, self.out, self.fl)
        self.beat = True
        threading.Thread(target=self._pulse, daemon=True).start()
        self.ready()

    def _pulse(self):
        while self.beat:
            try:
                get(self.fp, "/api/pulse", 5)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(.5)

    def ready(self, want=True, limit=15):
        started = time.time()
        while time.time() - started < limit:
            if (b'"live"' not in get(self.fp, "/api/pulse", 5)[1]) == want:
                return True
            time.sleep(.1)
        return False

    def panics(self):
        return (self.out / "fr.log").read_text(encoding="utf8", errors="replace").count("panicked")

    def stop(self):
        self.beat = False
        for p in (self.front, self.py):
            p.kill()
            p.wait(20)
        self.pl.close()
        self.fl.close()
        self.proxy.srv.shutdown()
