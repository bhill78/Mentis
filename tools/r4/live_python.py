"""Python's own server on a copy, whose live registries a test can move: what no HTTP route does.

    <venv python> tools/r4/live_python.py <copy> --port P --control C --workspace W

The server is `mentis.web.serve`, the real one. A second port takes one JSON line per request and acts
on that process's own objects, `begin_execution`, `end_execution`, `agents_open_run` and `agents_end_run`,
so `/private/live` answers from real registries through its real producers, and with `--count` says how
many statements it ran. For tests and measurements on a copy only.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import socket
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from mentis import web  # noqa: E402


COUNT = {"n": 0}


def counting() -> None:
    """SQLite's own trace on every read connection Python opens, and its writer's."""
    from mentis.spine import store as S

    def trace(_statement) -> None:
        COUNT["n"] += 1

    real = S.Store._read_connection

    def traced(self):
        conn = real(self)
        conn.set_trace_callback(trace)
        return conn

    S.Store._read_connection = traced

    def on_the_writer() -> None:
        while getattr(web._Handler, "state", None) is None:
            time.sleep(.05)
        web._Handler.state.corpus._store._conn.set_trace_callback(trace)

    threading.Thread(target=on_the_writer, daemon=True).start()


def act(st, ask: dict):
    what = ask["do"]
    if what == "begin":
        return st.cv.begin_execution(participant=ask["participant"], conversation=ask.get("conversation"),
                                     runtime=ask.get("runtime"),
                                     for_expectation=ask.get("for_expectation")).reference
    if what == "end":
        st.cv.end_execution(ask["reference"])
        return True
    if what == "open_run":
        st.agents.agents_open_run(ask["instance"], ask["run"])
        return True
    if what == "end_run":
        st.agents.agents_end_run(ask["run"])
        return True
    if what == "retain":
        # Executions begun and ended, as a long-lived process has retained them.
        for _ in range(ask["count"]):
            st.cv.end_execution(st.cv.begin_execution(participant=ask["participant"],
                                                      conversation=ask.get("conversation")).reference)
        return True
    if what == "count":
        # How many statements since last asked, with `--count`.
        said, COUNT["n"] = COUNT["n"], 0
        return said
    if what == "measure":
        # The whole added-field step, as `/private/live` takes it.
        took = []
        for _ in range(ask["times"]):
            started = time.perf_counter_ns()
            fields = web._added_live_fields(st.agents, st.cv)
            took.append(time.perf_counter_ns() - started)
        took.sort()
        return {"p50_ms": took[len(took) // 2] / 1e6, "p95_ms": took[int(len(took) * .95)] / 1e6,
                "fields": {name: len(text) for name, text in fields}}
    raise ValueError(what)


def control(port: int) -> None:
    server = socket.create_server(("127.0.0.1", port))
    while getattr(web._Handler, "state", None) is None:
        time.sleep(.05)
    st = web._Handler.state
    while True:
        conn, _ = server.accept()
        with conn, conn.makefile("rwb") as stream:
            for line in stream:
                try:
                    answer = {"ok": act(st, json.loads(line))}
                except Exception as exc:  # noqa: BLE001 - said to the test that asked
                    answer = {"error": f"{type(exc).__name__}: {exc}"}
                stream.write(json.dumps(answer).encode() + b"\n")
                stream.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("copy")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--control", type=int, required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--mars", default="workload-no-mars-here")
    parser.add_argument("--count", action="store_true")
    args = parser.parse_args()
    if args.count:
        counting()
    threading.Thread(target=control, args=(args.control,), daemon=True).start()
    web.serve(str(pathlib.Path(args.copy).resolve()), host="127.0.0.1", port=args.port,
              workspace=args.workspace, mars=args.mars)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
