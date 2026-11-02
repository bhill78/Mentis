"""Both chain verifiers, on a Brain copy, for rows E and J15. Python's own walk, by the tool that
already does it at PY_COMMIT, and Rust's, by the front's binary. Neither writes."""

from __future__ import annotations

import json
import sqlite3
import subprocess

from mentis.spine import backup


def python_verifier(brain) -> dict:
    """`Store.verify_chain`'s walk. `mode=ro` and not immutable: the copy may have a server on it,
    and what is in its WAL is part of what it says."""
    conn = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        return backup._chain(conn)
    finally:
        conn.close()


def rust_verifier(pair) -> list[dict]:
    done = subprocess.run([pair.state["front"]["executable"], "--verify-chains", str(pair.brain)],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def assert_both_verify(pair) -> None:
    python = python_verifier(pair.brain)
    rust = rust_verifier(pair)
    assert all(table["broke_at_seq"] is None for table in rust), rust
    assert python["intact"] is True, python
    assert {table["table"] for table in rust} == {"entry", "operational", "delivery"}
    # Both read the same record, so they say the same of each table.
    for table in rust:
        stream = python["streams"][table["table"]]
        assert stream["head"] == table["head"], table
