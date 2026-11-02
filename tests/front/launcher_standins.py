"""Stand-ins for the launcher's two processes, for what P1.5 can run before there is a front.

`--front <python.exe>` with the Brain a directory holding this file as `__main__.py` runs it as the
front, and `--code <dir>` holding it as `mentis/web/__main__.py` runs it as Python, so the launcher
is started exactly as it will be, with no binary to build. Each writes one line of what it was given
to `events.jsonl`, and answers only what `behaviour.json` beside it says to.

Standard library only, and it never opens a Brain.
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import sys
import threading
import time

HERE = pathlib.Path(os.environ["MENTIS_STANDIN_DIR"])
SECRET = "MENTIS_BOOT_SECRET"


def main() -> None:
    behaviour = json.loads((HERE / "behaviour.json").read_text(encoding="utf-8"))
    is_front = "--upstream" in sys.argv
    who = "front" if is_front else "python"
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1])
    with open(HERE / "events.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps({"who": who, "at": time.time(), "pid": os.getpid(), "argv": args,
                              "secret": os.environ.get(SECRET), "cwd": os.getcwd(),
                              "dist_env": os.environ.get("MENTIS_FLUID_DIST"),
                              "mars_env": os.environ.get("MENTIS_MARS_COMMAND")}) + "\n")
    mode = behaviour.get(who)
    if mode == "refuse":
        print(f"{who} stand-in refuses, in words", file=sys.stderr, flush=True)
        raise SystemExit(3)
    if mode == "silent":
        time.sleep(3600)

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def answer(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/server":
                return self.answer(200, {"who": who, "pid": os.getpid()})
            if path == "/fluid/api/home/activity":
                return self.answer(200, behaviour.get("activity", {"open": 0, "items": []}))
            if path == "/fluid/api/runs":
                return self.answer(200, {"runs": behaviour.get("runs", [])})
            return self.answer(404, {"error": "no such semantic surface"})

        def do_POST(self):
            if (self.path == "/private/stop" and is_front
                    and self.headers.get("X-Mentis-Boot-Secret") == os.environ.get(SECRET)):
                self.answer(200, {"stopping": True})
                threading.Timer(0.2, os._exit, [0]).start()
                return None
            return self.answer(404, {"error": "no such semantic surface"})

        def log_message(self, *a):
            pass

    host = args[args.index("--host") + 1]
    server = http.server.ThreadingHTTPServer((host, port), Handler)
    print(f"{who} stand-in on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
