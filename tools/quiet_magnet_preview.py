"""Run the disposable fixture pair and built, write-refusing preview.

This stays in the foreground. A caller leaving it running must arrange the
request's detached-result reporting and launch it hidden, as the work rules say.
Nothing is restarted, and only PIDs launched here are stopped on exit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quiet_magnet_fixture import REPO, FORMAT, safe_root, snapshot


def ask(url: str, *, method: str = "GET", body: bytes | None = None) -> tuple[int, object]:
    request = urllib.request.Request(url, data=body, method=method, headers={"X-Mentis-Client": "1"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            content = response.read()
            try: value = json.loads(content)
            except ValueError: value = content.decode("utf-8", "replace")
            return response.status, value
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def wait_for(url: str, process: subprocess.Popen, seconds: float = 45) -> None:
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError(f"process {process.pid} exited {process.returncode}; inspect fixture logs")
        try:
            if ask(url)[0] == 200: return
        except (OSError, ValueError): pass
        time.sleep(0.1)
    raise RuntimeError(f"did not answer: {url}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".preview/quiet-magnet")
    ap.add_argument("--front", required=True, help="explicit candidate-built mentis-server executable")
    ap.add_argument("--launcher", required=True, help="explicit candidate-built mentis-launch executable")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--node", default="node")
    ap.add_argument("--dist", default=str(REPO / "apps" / "fluid-web" / "dist"))
    ap.add_argument("--python-port", default=8911, type=int)
    ap.add_argument("--front-port", default=8912, type=int)
    ap.add_argument("--preview-port", default=8913, type=int)
    ap.add_argument("--verify-only", action="store_true", help="start, inspect read contracts/refusals, stop owned processes")
    args = ap.parse_args()
    root = safe_root(args.root)
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    if manifest.get("format") != FORMAT or not manifest.get("setup_closed"):
        raise ValueError("seed setup must have completed first")
    for port in (args.python_port, args.front_port, args.preview_port):
        with socket.socket() as sock:
            try: sock.bind(("127.0.0.1", port))
            except OSError as error: raise RuntimeError(f"port {port} held; choose/claim another") from error
    dist = Path(args.dist).resolve()
    if not (dist / "index.html").is_file() or not (dist / "render-check.js").is_file():
        raise ValueError("build the candidate UI first (index.html and render-check.js required)")
    run = root / "run"
    run.mkdir(exist_ok=True)
    ws = root / "workspace"
    ws.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("MENTIS", "MARS", "Q2_")) and k.upper() != "PYTHONPATH"}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    no_window = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    command = [str(Path(args.launcher).resolve()), str(root / "primary"), "--port", str(args.front_port),
        "--private-port", str(args.python_port), "--workspace", str(ws), "--mars", "quiet-magnet-no-mars",
        "--python", str(Path(args.python).resolve()), "--code", str(REPO), "--front", str(Path(args.front).resolve()),
        "--dist", str(dist), "--run-dir", str(run), "--attached"]
    children: list[subprocess.Popen] = []
    owned_state = None
    logs = []
    def launch(words, name):
        log = open(run / name, "ab")
        logs.append(log)
        child = subprocess.Popen(words, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=no_window)
        children.append(child)
        return child
    try:
        pair = launch(command, "launcher-output.log")
        wait_for(f"http://127.0.0.1:{args.front_port}/api/brain?identity=1", pair, 90)
        owned_state = json.loads((run / "launch.json").read_text("utf-8"))
        proxy = launch([args.node, str(REPO / "tools" / "quiet-magnet-preview.mjs"), "--front", f"http://127.0.0.1:{args.front_port}",
            "--port", str(args.preview_port), "--dist", str(dist), "--log", str(root / "traffic.jsonl")], "preview.log")
        base = f"http://127.0.0.1:{args.preview_port}"
        wait_for(base + "/__q2/brain", proxy)
        identity_python = ask(f"http://127.0.0.1:{args.python_port}/api/brain?identity=1")
        identity_front = ask(base + "/api/brain?identity=1")
        if identity_python[1].get("corpus_id") != manifest["primary"]["corpus_id"] or identity_front[1].get("corpus_id") != manifest["primary"]["corpus_id"]:
            raise RuntimeError("Python/front/fixture corpus identity mismatch")
        # The routed object extractor is bounded to four cold post extractions
        # per request. Warm each cursor through the sanctioned GET route as a
        # SETUP prerequisite. This is memory cache only, never a Brain write.
        # Repeating a partial page (rather than advancing it) preserves objects.
        primary = manifest["primary"]
        mid, b = primary["magnets"]["primary"], primary["B"]
        warm = []
        cursor = None
        for page in range(4):
            url = base + f"/fluid/api/magnets/{mid}/read?mode=page&source=conversation%3A{b}&types=file,image,attachment"
            if cursor: url += "&cursor=" + cursor
            for attempt in range(10):
                status, body = ask(url)
                if status != 200: raise RuntimeError(f"fixture setup object warm refused: {status}: {body}")
                source = body["sources"][0]
                warm.append({"page": page, "attempt": attempt, "status": source["status"], "results": len(source.get("results", []))})
                if source["status"] == "ok": break
                if source["status"] != "partial": raise RuntimeError(f"fixture object warm unavailable: {source}")
            else: raise RuntimeError("fixture setup object warm exceeded ten bounded attempts")
            cursor = source.get("next")
            if not cursor: break
        else: raise RuntimeError("fixture setup object warm exceeded four bounded pages")
        (root / "setup-warm.json").write_text(json.dumps(warm, indent=2), "utf-8")
        before = snapshot(root)
        (root / "runtime-baseline.json").write_text(json.dumps(before, indent=2), "utf-8")
        a, b = manifest["primary"]["A"], manifest["primary"]["B"]
        mid = manifest["primary"]["magnets"]["primary"]
        probes = {
            "identity_python": identity_python,
            "identity_front": identity_front,
            "arrangement": ask(base + f"/fluid/api/arrangements/{a}"),
            "summary": ask(base + f"/fluid/api/magnets/{mid}/read?mode=summary"),
            "posts": ask(base + f"/fluid/api/magnets/{mid}/read?mode=page&source=conversation%3A{b}&types=post"),
            "files": ask(base + f"/fluid/api/magnets/{mid}/read?mode=page&source=conversation%3A{b}&types=file,image,attachment"),
            "missing_definition": ask(base + "/fluid/api/magnets/mag-doesnotexist/read?mode=summary"),
            "own_post_refused": ask(base + f"/fluid/api/magnets/{mid}/conversation", method="POST", body=b"{}"),
            "capacity_refused": ask(base + "/api/capacity"),
            "ui_read_only": ask(base + "/__q2/brain"),
        }
        for name in ("arrangement", "summary", "posts", "files"):
            if probes[name][0] != 200: raise RuntimeError(f"fixture probe {name} failed: {probes[name]}")
        if probes["own_post_refused"][0] != 403 or probes["capacity_refused"][0] != 403:
            raise RuntimeError("preview did not refuse writes before forwarding")
        if snapshot(root) != before: raise RuntimeError("fixture logical record/presentation/held bytes changed during read probes")
        state = owned_state
        ready = {"status": "running", "fixture_probes": "completed and verified", "checked_at": time.time(), "preview": base + f"/quiet2?c={a}&at=1",
            "helper_pid": os.getpid(), "launcher_pid": pair.pid, "preview_pid": proxy.pid,
            "python_pid": state["python"]["pid"], "front_pid": state["front"]["pid"],
            "front_sha256": hashlib.sha256(Path(args.front).read_bytes()).hexdigest(),
            "launcher_sha256": hashlib.sha256(Path(args.launcher).read_bytes()).hexdigest(),
            "fixture_manifest": str(root / "manifest.json"), "runtime_baseline": str(root / "runtime-baseline.json"),
            "no_mutation": True, "probes": probes}
        (root / "ready.json").write_text(json.dumps(ready, indent=2), "utf-8")
        print(json.dumps({k: v for k, v in ready.items() if k != "probes"}, indent=2), flush=True)
        if args.verify_only: return 0
        while True:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("a preview process ended; no restart was attempted")
            time.sleep(0.5)
    finally:
        # The launcher's siblings may already have outlived it; stop exactly
        # the two PIDs this invocation's fresh launch.json names as well.
        if owned_state:
            owned = owned_state
            for family in ("front", "python"):
                pid = owned.get(family, {}).get("pid")
                if pid and os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for child in reversed(children):
            if child.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    child.terminate()
                try: child.wait(timeout=10)
                except subprocess.TimeoutExpired: child.kill(); child.wait()
        for log in logs: log.close()


if __name__ == "__main__":
    raise SystemExit(main())
