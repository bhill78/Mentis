"""A real Python server under the mirror's tests, with the moments a test has to aim at:
`docs/rust/R3-mirror.md`, section 8.

It calls `mentis.web.serve`, so it claims, binds and serves through the real code. What it adds:

- `--wait-for-go`: imported and waiting, so a replacement's claim comes within the lease.
- a stop that leaves it alive: its port and locks are free and its process object isn't signalled,
  for as long as a test needs, which is what a kill looks like to the front between the release and
  the signal.
- a teardown that gives up its port, `.mentis.serve.lock` and `.mentis.sole.lock`, and keeps the
  owner lock.
- a fault point at each step of a claim, logged on the raw clock so it compares with a front's trace.

Commands arrive as files in `--control`, and what happened is written there: nothing reaches in.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import pathlib
import socket
import sys
import threading
import time


def qpc() -> int:
    now = ctypes.c_longlong()
    ctypes.windll.kernel32.QueryPerformanceCounter(ctypes.byref(now))
    return now.value


def die() -> None:
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel.TerminateProcess(kernel.GetCurrentProcess(), 9)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("brain")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--answers-at", default=None)
    ap.add_argument("--control", required=True)
    ap.add_argument("--code", required=True)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--claim-wait", type=float, default=None)
    ap.add_argument("--die-at", default=None)
    ap.add_argument("--pause-at", default=None)
    ap.add_argument("--wait-for-go", action="store_true")
    args = ap.parse_args()
    sys.path.insert(0, args.code)
    control = pathlib.Path(args.control)
    control.mkdir(parents=True, exist_ok=True)

    def say(name: str, text: str = "") -> None:
        (control / name).write_text(text, encoding="utf-8")

    def wait_for(name: str) -> None:
        while not (control / name).exists():
            time.sleep(0.002)

    say("pid", str(os.getpid()))
    from mentis import web
    from mentis.spine import brainlock
    if args.claim_wait is not None:
        brainlock.CLAIM_WAIT = args.claim_wait

    steps = open(control / "steps.jsonl", "a", encoding="utf-8", buffering=1)

    def at_step(name: str) -> None:
        steps.write(json.dumps({"step": name, "at": qpc()}) + "\n")
        if name == args.die_at:
            die()
        if name == args.pause_at:
            say(f"paused-{name}")
            wait_for(f"go-{name}")

    brainlock._at_step = at_step
    if args.die_at == "partial":
        def partial(fh, _boot_id):
            os.lseek(fh.fileno(), 0, os.SEEK_SET)
            os.write(fh.fileno(), b"part")
            die()
        brainlock._write_claim = partial

    servers = []

    class Captured(web._Server):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.refusing = False
            servers.append(self)

        def verify_request(self, request, client_address):
            return not self.refusing
    web._Server = Captured

    def commands() -> None:
        while True:
            if (control / "stop").exists():
                (control / "stop").unlink()
                servers[0].shutdown()
            if (control / "give-up").exists():
                (control / "give-up").unlink()
                # As a kill does, as far as the private port goes: nothing new is answered.
                # The connection a front polls on stays, so the lease stays valid.
                servers[0].refusing = True
                held = web._Handler.serve_lock
                held.sole.release()
                held.serve_lock.release()
                say("gave-up", str(qpc()))
            if (control / "late-position").exists():
                boot, generation = (control / "late-position").read_text().split()
                (control / "late-position").unlink()
                threading.Thread(target=late_answers, daemon=True,
                                 args=(args.port, boot, int(generation), say)).start()
            if (control / "exit").exists():
                os._exit(0)
            time.sleep(0.002)

    threading.Thread(target=commands, daemon=True).start()
    say("imported", str(qpc()))
    if args.wait_for_go:
        wait_for("go")
    try:
        web.serve(os.path.abspath(args.brain), host="127.0.0.1", port=args.port,
                  workspace=args.workspace, mars="workload-no-mars-here",
                  answers_at=args.answers_at)
    except brainlock.BrainBusy as refused:
        print(f"Mentis refused to start: {refused}", file=sys.stderr, flush=True)
        say("refused", str(refused))
        os._exit(3)
    say("stopped", str(qpc()))
    # Alive, with its port and locks free, until told otherwise.
    while True:
        time.sleep(1)


def late_answers(port: int, boot: str, generation: int, say) -> None:
    """Positions and pulls from a boot that has let go: what a thread in an orderly stop might do."""
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(16)
    say("late-listening")
    position = {"schema": 1, "boot_id": boot, "generation": generation, "down": False,
                "pid": os.getpid()}
    pull = {"schema": 1, "boot_id": boot, "generation": generation,
            "corpus": "unused", "grants": {}}
    while True:
        conn, _ = listener.accept()
        threading.Thread(target=_late_one, daemon=True, args=(conn, position, pull)).start()


def _late_one(conn: socket.socket, position: dict, pull: dict) -> None:
    got = b""
    with conn:
        while True:
            while b"\r\n\r\n" not in got:
                more = conn.recv(65536)
                if not more:
                    return
                got += more
            head, _, got = got.partition(b"\r\n\r\n")
            path = head.split(b" ")[1]
            if not path.startswith(b"/private/grants"):
                # Anything forwarded to it: an answer that isn't a 200, so a test can tell it.
                conn.sendall(b"HTTP/1.1 503 Gone\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                return
            body = json.dumps(position if path.endswith(b"position") else pull).encode()
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body))


if __name__ == "__main__":
    main()
