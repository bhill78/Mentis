"""Run the Magnet additions' disposable fixture pair and its gated preview.

    python tools/quiet_magnet_additions_preview.py --front <mentis-server.exe>
      --launcher <mentis-launch.exe> --root .preview/quiet-magnet-additions-fixture
      --dist apps/fluid-web/dist [--verify-only] [--report-config <file>]

This stays in the foreground. A caller leaving it running arranges the request's
detached-result reporting (`arm_detached`) and launches it hidden, as the work
rules say. Nothing is restarted and nothing is retried: a process that ends ends
the run, and a failed check is a failure, not a second attempt.

WHAT IT CLAIMS, AND WHAT IT DOES NOT. The read-only trial's helper could say
`no_mutation: True`, because its access path refused every write. This one does
not and must not: two writes are deliberately possible through it (a record-only
post into the Magnet's own Conversation, and one Magnet creation in the one
fixture arrangement). What it records instead is `writes_allowed` -- exactly
which two, into which Conversation and arrangement -- and a baseline of the
fixture record taken before the preview is used, so a later reader can see what
the trial actually changed rather than being told nothing changed.

It reuses the read-only helper's `safe_root`, `ask`, `wait_for`, `launch_state`
and `DetachedReporter` by importing them. Neither that helper nor its seed is
changed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quiet_magnet_fixture import REPO, safe_root
from quiet_magnet_preview import DetachedReporter, ask, launch_state, wait_for
import quiet_magnet_additions_fixture as fixture

CLIENT = {"X-Mentis-Client": "1"}


def same_file(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".preview/quiet-magnet-additions-fixture")
    ap.add_argument("--front", required=True,
                    help="explicit candidate-built mentis-server executable")
    ap.add_argument("--launcher", required=True,
                    help="explicit candidate-built mentis-launch executable")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--node", default="node")
    ap.add_argument("--dist", default=str(REPO / "apps" / "fluid-web" / "dist"))
    # The read-only trial holds 8911-8913 and the parent clone holds 8941-8943.
    ap.add_argument("--python-port", default=8951, type=int)
    ap.add_argument("--front-port", default=8952, type=int)
    ap.add_argument("--preview-port", default=8953, type=int)
    ap.add_argument("--verify-only", action="store_true",
                    help="start, check identity and the gate, stop owned processes")
    ap.add_argument("--report-config",
                    help="private one-time arm_detached report configuration, "
                         "never an artifact")
    ap.add_argument("--stop-file",
                    help="foreground evaluation ends when this work-owned file exists")
    args = ap.parse_args()

    root = safe_root(args.root)
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    if manifest.get("format") != fixture.FORMAT or not manifest.get("setup_closed"):
        raise ValueError("this preview serves a completed additions fixture "
                         f"({fixture.FORMAT}) and nothing else")
    primary = manifest["primary"]
    allowed = manifest["writes_allowed"]
    brain = root / "primary"
    for port in (args.python_port, args.front_port, args.preview_port):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError as error:
                raise RuntimeError(f"port {port} held; choose/claim another") from error
    dist = Path(args.dist).resolve()
    if not (dist / "index.html").is_file() or not (dist / "render-check.js").is_file():
        raise ValueError("build the candidate UI first (index.html and "
                         "render-check.js required)")

    run = root / f"run-{time.time_ns()}"
    run.mkdir()
    ws = root / "workspace"
    ws.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("MENTIS", "MARS", "Q2_"))
           and k.upper() != "PYTHONPATH"}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    no_window = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    command = [str(Path(args.launcher).resolve()), str(brain),
               "--port", str(args.front_port),
               "--private-port", str(args.python_port), "--workspace", str(ws),
               "--mars", "quiet-magnet-additions-no-mars",
               "--python", str(Path(args.python).resolve()), "--code", str(REPO),
               "--front", str(Path(args.front).resolve()), "--dist", str(dist),
               "--run-dir", str(run), "--attached"]
    children: list[subprocess.Popen] = []
    owned_state = None
    ready = None
    logs = []
    report = DetachedReporter(args.report_config,
                              root / "detached-receipt.json").report

    def launch(words, name):
        log = open(run / name, "ab")
        logs.append(log)
        child = subprocess.Popen(words, cwd=REPO, env=env, stdout=log,
                                 stderr=subprocess.STDOUT, creationflags=no_window)
        children.append(child)
        return child

    try:
        pair = launch(command, "launcher-output.log")
        wait_for(f"http://127.0.0.1:{args.front_port}/api/brain?identity=1", pair, 90)
        owned_state = launch_state(run / "launch.json")
        proxy = launch([args.node,
                        str(REPO / "tools" / "quiet-magnet-additions-preview.mjs"),
                        "--front", f"http://127.0.0.1:{args.front_port}",
                        "--port", str(args.preview_port), "--dist", str(dist),
                        "--log", str(root / "traffic.jsonl"),
                        "--manifest", str(root / "manifest.json")], "preview.log")
        base = f"http://127.0.0.1:{args.preview_port}"
        # THE PROXY REFUSES TO LISTEN AT ALL unless it has confirmed the
        # server's identity for itself, so this answering is already evidence.
        wait_for(base + "/__q2/brain", proxy)

        identities = {
            "python": ask(f"http://127.0.0.1:{args.python_port}/api/brain?identity=1"),
            "front": ask(f"http://127.0.0.1:{args.front_port}/api/brain?identity=1"),
            "through_preview": ask(base + "/api/brain?identity=1"),
            "server": ask(base + "/api/server"),
        }
        for name, (status, body) in identities.items():
            if status != 200 or not isinstance(body, dict):
                raise RuntimeError(f"{name} did not answer its identity: {status}")
            if body.get("corpus_id") != primary["corpus_id"]:
                raise RuntimeError(f"{name} serves another Brain than this fixture")
        if not same_file(identities["server"][1].get("corpus", ""), str(brain)):
            raise RuntimeError("/api/server names another corpus directory than "
                               "this fixture's Brain")

        # THE GATE, ASKED OF THE RUNNING PREVIEW rather than assumed from code.
        gate = {
            "capability": ask(base + "/__q2/magnet-capabilities"),
            "page_read_only": ask(base + "/__q2/brain"),
            "capacity_refused": ask(base + "/api/capacity"),
            "other_write_refused": ask(base + "/fluid/api/requests",
                                       method="POST", body=b"{}"),
            "magnet_own_conversation_refused": ask(
                base + f"/fluid/api/magnets/{primary['magnets']['primary']}"
                       "/conversation", method="POST", body=b"{}"),
            "unbound_post_refused": ask(base + "/fluid/api/posts",
                                        method="POST", body=b"{}"),
            "encoded_alias_refused": ask(base + "/fluid/api/po%73ts",
                                         method="POST", body=b"{}"),
        }
        capability = gate["capability"][1]
        if gate["capability"][0] != 200 or capability != {
                "fixture": True, "corpus_id": primary["corpus_id"],
                "conversations": [allowed["conversation"]],
                "arrangements": [allowed["arrangement"]]}:
            raise RuntimeError(f"the fixture capability is not what it should "
                               f"be: {gate['capability']}")
        if gate["page_read_only"][1].get("readOnly") is not True:
            raise RuntimeError("the page's own Brain choice is not read-only")
        for name in ("capacity_refused", "other_write_refused",
                     "magnet_own_conversation_refused", "encoded_alias_refused"):
            if gate[name][0] < 400:
                raise RuntimeError(f"the preview did not refuse {name}: {gate[name]}")
        # A write with none of the page's own framing is refused BEFORE the
        # body is read: 403 (no client header) rather than anything recorded.
        if gate["unbound_post_refused"][0] < 400:
            raise RuntimeError("the preview forwarded an unframed write")

        baseline = fixture.snapshot(root)
        (root / "runtime-baseline.json").write_text(json.dumps(baseline, indent=2),
                                                    "utf-8")
        state = owned_state
        ready = {
            "status": "running",
            "checked": "identity of the Python/front pair and of the preview's "
                       "own gate; the preview refused to listen until it had "
                       "confirmed the server's Brain for itself",
            "checked_at": time.time(),
            "preview": base + f"/quiet2?c={primary['A']}&at=1",
            "helper_pid": os.getpid(), "launcher_pid": pair.pid,
            "preview_pid": proxy.pid,
            "python_pid": state["python"]["pid"], "front_pid": state["front"]["pid"],
            "front_sha256": hashlib.sha256(Path(args.front).read_bytes()).hexdigest(),
            "launcher_sha256": hashlib.sha256(Path(args.launcher).read_bytes()).hexdigest(),
            "fixture_manifest": str(root / "manifest.json"),
            "fixture_brain": str(brain),
            "runtime_baseline": str(root / "runtime-baseline.json"),
            "run_dir": str(run),
            # NOT "no mutation": this preview exists so that two writes can be
            # made. What they are is said here, in full.
            "writes_allowed": {
                "post": f"record-only plain text or a reply inside "
                        f"{allowed['conversation']}",
                "magnet": f"one Magnet creation in {allowed['arrangement']} "
                          f"from {allowed['magnet_sources']}",
                "everything_else": "refused before forwarding"},
            "identities": identities, "gate": gate}
        (root / "ready.json").write_text(json.dumps(ready, indent=2), "utf-8")
        print(json.dumps({k: v for k, v in ready.items()
                          if k not in ("identities", "gate")}, indent=2), flush=True)
        report("succeeded",
               "Disposable Quiet Magnet additions preview started and verified: "
               "the Rust/Python pair and the preview all serve the fixture "
               "Brain, the preview confirmed that identity for itself before "
               "listening, and its gate refuses capacity, other writes and "
               "encoded aliases while offering the two scoped fixture writes. "
               "The preview remains running; browser evaluation is separate.",
               [str(root / "ready.json"), ready["preview"], ready["front_sha256"]])
        if args.verify_only:
            return 0
        while True:
            if args.stop_file and Path(args.stop_file).is_file():
                ready["status"] = "completed and verified; foreground preview stopped"
                (root / "ready.json").write_text(json.dumps(ready, indent=2), "utf-8")
                return 0
            if any(child.poll() is not None for child in children):
                raise RuntimeError("a preview process ended; no restart was attempted")
            time.sleep(0.5)
    except BaseException as error:
        report("failed", "Disposable Quiet Magnet additions preview helper "
                         "failed: " + str(error), [str(run)])
        raise
    finally:
        if owned_state:
            for family in ("front", "python"):
                pid = owned_state.get(family, {}).get("pid")
                if pid and os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for child in reversed(children):
            if child.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for log in logs:
            log.close()
        if ready is not None:
            ready.update(status="completed and verified" if args.verify_only
                         else "stopped", preview_running=False,
                         stopped_at=time.time())
            (root / "ready.json").write_text(json.dumps(ready, indent=2), "utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
