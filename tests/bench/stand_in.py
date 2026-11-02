"""What `--command` starts in these tests: answers as a server would, on {port}, and writes down what
the bench gave it. STAND_IN_BAD names a path prefix to answer 500, STAND_IN_VARY makes each boot's
answers differ, and STAND_IN_ONE_TOPIC leaves nothing for the self-check's reversal to change.

    stand_in.py {brain} --port {port} --workspace {ws} --mars {mars} --run {run}
"""
import argparse, http.server, json, os, pathlib, sys, uuid

ap = argparse.ArgumentParser()
ap.add_argument("brain")
ap.add_argument("--port", type=int, required=True)
ap.add_argument("--workspace", required=True)
ap.add_argument("--mars", required=True)
ap.add_argument("--run", required=True)
a = ap.parse_args()

brain = pathlib.Path(a.brain)
(pathlib.Path(a.run) / "given.json").write_text(json.dumps({
    "argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ),
    "corpus_writable": os.access(brain / "corpus.db", os.W_OK),
    "corpus_json_writable": os.access(brain / "mentis-corpus.json", os.W_OK),
    "brain_files": sorted(p.name for p in brain.iterdir()),
}))
print("stand-in up", flush=True)

BAD = os.environ.get("STAND_IN_BAD")
BOOT = uuid.uuid4().hex if os.environ.get("STAND_IN_VARY") else "same"


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def answer(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        path = self.path
        status, body = 200, {"ok": True, "boot": BOOT}
        if BAD and path.startswith(BAD):
            status, body = 500, {"error": "stand-in told to fail"}
        elif path.startswith("/fluid/api/objects"):
            body = {"extracted": True, "renderer": {"sha256": "stand-in"}, "before": None}
        elif path == "/api/worker/session":
            body = {"grant": "g", "scope": "s", "alias": "a", "runtime": "workload", "permits": ["find"]}
        elif path.startswith("/fluid/api/collections/conversation"):
            body = {"items": [{"id": "ent-aaaaaaaaaaaa"}]}
        elif path.startswith("/fluid/api/topics"):
            one = os.environ.get("STAND_IN_ONE_TOPIC")
            body = {"topics": [{"t": 1}] if one else [{"t": 1}, {"t": 2}], "boot": BOOT}
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = answer

    def log_message(self, *args):
        pass


http.server.ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
