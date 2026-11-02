"""MEASUREMENT ONLY. Loaded by every Python process started with this directory on
PYTHONPATH, and only on the untimed statement-capture boot (it slows every statement).

Every connection made through Python's `sqlite3` gets a trace callback, which appends
one line per statement to trace-<pid>.log in $WORKLOAD_TRACE_DIR:
    <time.time()>\t<thread name>\t<statement>
Per process, so a candidate that moves reads to a child Python process is still counted.
A statement run outside Python's sqlite3 is invisible here. mentis-record built with
`sql-trace` writes the same lines to the same directory, with its thread as rust:<name>;
a build without it reads invisibly, and run_workload.py says so rather than reporting the
zero as a result.
"""
import os

_dir = os.environ.get("WORKLOAD_TRACE_DIR")
if _dir:
    import sqlite3
    import threading
    import time

    _fd = os.open(os.path.join(_dir, f"trace-{os.getpid()}.log"),
                  os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0))
    _real = sqlite3.connect

    def _traced(sql):
        line = f"{time.time():.4f}\t{threading.current_thread().name}\t{' '.join(sql.split())[:400]}\n"
        os.write(_fd, line.encode("utf-8", "replace"))

    def connect(*a, **k):
        c = _real(*a, **k)
        c.set_trace_callback(_traced)
        return c

    sqlite3.connect = connect
