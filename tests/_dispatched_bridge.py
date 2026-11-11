"""A dispatched run's real Mentis bridge, driven as a runtime drives it, and a door
in front of the server that can lose an answer.

`Bridge(spec)` starts the MCP server a dispatch handed the run (`spec.mcp_servers`,
built by `core.service.mcp_servers_for` with the run's grant and execution) and
sends it tool calls over stdio, as an agent CLI would.

`Cutting(target)` is a door between that bridge and the server. Each
`/api/worker` POST takes the next step of its `plan`:
  * "pass":         forwarded, answered.
  * "drop-before":  the connection ends with nothing forwarded (nothing done).
  * "drop-after":   forwarded and done, and the connection ends before the
                    answer (the front dying with the answer in hand).
  * "503-after":    forwarded and done, then a 503 (Python-reached).
"""
from __future__ import annotations

import json
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Bridge:
    def __init__(self, spec):
        server = spec.mcp_servers[0]
        self.proc = subprocess.Popen(
            [server["command"], *server["args"]], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8")
        self._id = 0
        self.ask("initialize", {})

    def ask(self, method, params):
        self._id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._id,
                                          "method": method,
                                          "params": params}) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def call(self, name, **args):
        """(is_error, value or text) of one tool call."""
        got = self.ask("tools/call", {"name": name, "arguments": args})["result"]
        text = got["content"][0]["text"]
        if got.get("isError"):
            return True, "\n".join(c.get("text", "") for c in got["content"])
        return False, json.loads(text)

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=30)
        return self.proc.stderr.read()


class Cutting:
    def __init__(self, target: str):
        self.target = target.rstrip("/")
        self.plan: list[str] = []
        self.seen: list[tuple[str, str]] = []
        door = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                step = door.plan.pop(0) if (door.plan and self.path == "/api/worker") \
                    else "pass"
                try:
                    op = json.loads(body).get("op")
                except ValueError:
                    op = None
                door.seen.append((step, op))
                if step == "drop-before":
                    self.close_connection = True
                    return
                req = urllib.request.Request(
                    door.target + self.path, data=body, method="POST",
                    headers={k: v for k, v in self.headers.items()
                             if k.lower() not in ("host", "content-length")})
                try:
                    with urllib.request.urlopen(req, timeout=60) as fh:
                        status, data = fh.status, fh.read()
                except urllib.error.HTTPError as exc:
                    status, data = exc.code, exc.read()
                if step == "drop-after":
                    self.close_connection = True
                    return
                if step == "503-after":
                    status, data = 503, json.dumps({
                        "error": "Python stopped with this request in hand, so "
                                 "the result is unknown."}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
