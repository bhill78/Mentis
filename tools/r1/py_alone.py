"""PY-ALONE: Python alone, the other side of every differential case.

    <fixtures>\\venv\\Scripts\\python.exe tools/r1/py_alone.py <Brain copy> [--port 8851] [--once]

Always the checkout of PY_COMMIT with the environment below, whatever clone this is run from:
R1-acceptance.md, "Fixtures", says why. `--once` starts it, proves it answers, stops it and
exits 0, or exits nonzero with the reason. Without it, it stays up until killed. Only `running`'s
`code` runs anything else, and what that runs isn't PY-ALONE.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402

PORT = 8851
#: The command that can't exist, as the bench: no MARS is reachable from this server.
NO_MARS = "workload-no-mars-here"
START_LIMIT_S = 240


def command(brain, port: int, workspace) -> list[str]:
    return [str(common.venv_python()), "-m", "mentis.web", str(brain),
            "--port", str(port), "--workspace", str(workspace), "--mars", NO_MARS]


def environment(dist=None) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("MENTIS")}
    env.update(MENTIS_FLUID_DIST=str(dist or common.dist_dir()), PYTHONDONTWRITEBYTECODE="1",
               PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    return env


def get(port: int, path: str, timeout: float = 10.0) -> tuple[int, bytes]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 headers={"X-Mentis-Client": "1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return fh.status, fh.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _answers(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), 0.5).close()
        return True
    except OSError:
        return False


@contextlib.contextmanager
def running(brain, *, port: int = PORT, run_dir=None, dist=None, code=None):
    """Python alone on `brain`, answering, until the block ends. `brain` must be a copy: this
    refuses the fixtures' master. `dist` replaces Fluid's build, to serve a broken one. `code` runs
    another checkout, which then isn't PY-ALONE: only what R1-acceptance.md, "A", names uses it."""
    brain = pathlib.Path(brain).resolve()
    if brain == common.master_dir().resolve():
        raise SystemExit("PY-ALONE runs on a fresh copy, never on the master")
    # Windows lets a second server bind a port one already holds, and the first goes on answering, so
    # a test would be comparing with some other Brain's Python and never know.
    if _answers(port):
        raise RuntimeError(f"something already answers on {port}")
    run_dir = pathlib.Path(run_dir or brain.parent / f"{brain.name}.run")
    (run_dir / "ws").mkdir(parents=True, exist_ok=True)
    # The code that will open it, PY_COMMIT's or another checkout, opens it at its own schema.
    common.current_schema(brain, code=code or common.code_dir())
    with open(run_dir / "server.log", "ab") as log:
        proc = subprocess.Popen(command(brain, port, run_dir / "ws"), cwd=code or common.code_dir(),
                                env=environment(dist), stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + START_LIMIT_S
        while True:
            if proc.poll() is not None:
                raise RuntimeError(f"PY-ALONE exited {proc.returncode}; see {run_dir}/server.log")
            try:
                if get(port, "/api/pulse", 2.0)[0] == 200:
                    break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError(f"PY-ALONE did not answer within {START_LIMIT_S} s")
            time.sleep(0.2)
        yield proc
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.wait(timeout=30)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="start PY-ALONE")
    ap.add_argument("brain", type=pathlib.Path)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    started = time.monotonic()
    with running(a.brain, port=a.port) as proc:
        status, server = get(a.port, "/api/server")
        pulse_status, pulse = get(a.port, "/api/pulse")
        index_status, index = get(a.port, "/")
        print(json.dumps({
            "code_commit": common.head_of(common.code_dir()),
            "command": command(a.brain, a.port, "<run>/ws"),
            "pid": proc.pid,
            "seconds_to_answer": round(time.monotonic() - started, 1),
            "server_status": status,
            "server": json.loads(server),
            "pulse_status": pulse_status,
            "pulse": json.loads(pulse),
            "index_status": index_status,
            "index_bytes": len(index),
        }, indent=1))
        if not a.once:
            proc.wait()
    if status != 200 or pulse_status != 200 or index_status != 200:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
