"""LEDGER: what a writer was told was written, durable before it asks again.

Format, version 1: JSON Lines. The first line is `{"format": "r1-ledger", "version": 1}`. Every
later line is one acknowledged write: `{"id": str, "table": str, "seq": int, "hash": str}`, where
`table` is `entry`, `operational` or `delivery`, and `seq` and `hash` are that row's in the record.

`Ledger.acknowledged` appends, flushes and fsyncs, and only then returns. `Writer.write` holds its
lock across the whole of send, acknowledge and fsync, so the next write can't begin until the last
one's row is on disk. A kill test (rows E and J15) kills the servers and never this process.
`verify` then says what the record lacks or holds differently: every row of the ledger must be
present with the same `id`, `seq` and `hash`.
"""

from __future__ import annotations

import json
import os
import pathlib
import threading

VERSION = 1
HEADER = {"format": "r1-ledger", "version": VERSION}
TABLES = ("entry", "operational", "delivery")


class Ledger:
    def __init__(self, path) -> None:
        self.path = pathlib.Path(path)
        if self.path.exists():
            raise FileExistsError(f"{self.path} exists: a ledger belongs to one run")
        self._fh = open(self.path, "x", encoding="utf-8", newline="\n")
        self._line(HEADER)

    def _line(self, doc: dict) -> None:
        self._fh.write(json.dumps(doc, sort_keys=True) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def acknowledged(self, id: str, table: str, seq: int, hash: str) -> None:
        if table not in TABLES:
            raise ValueError(f"no chained table {table!r}")
        self._line({"id": id, "table": table, "seq": seq, "hash": hash})

    def close(self) -> None:
        self._fh.close()


class Writer:
    """One write at a time. `send` performs the write and returns the acknowledged row as
    `(id, table, seq, hash)`, or raises when none was acknowledged, which records nothing."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger
        self._lock = threading.Lock()

    def write(self, send):
        with self._lock:
            row = send()
            self._ledger.acknowledged(*row)
            return row


def read(path) -> list[dict]:
    """A ledger's rows. Refuses another format or version, and anything malformed."""
    lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    if not lines or json.loads(lines[0]) != HEADER:
        raise ValueError(f"{path} isn't an r1-ledger of version {VERSION}")
    rows = [json.loads(line) for line in lines[1:]]
    for row in rows:
        if set(row) != {"id", "table", "seq", "hash"} or row["table"] not in TABLES:
            raise ValueError(f"{path} holds a malformed row: {row}")
    return rows


def verify(path, conn) -> list[str]:
    """Each thing the record `conn` reads lacks or holds differently. Empty when all is present."""
    wrong = []
    for row in read(path):
        found = conn.execute(f"SELECT id, seq, hash FROM {row['table']} WHERE id = ?",
                             (row["id"],)).fetchone()
        if found is None:
            wrong.append(f"missing: {row['table']} {row['id']}")
        elif tuple(found) != (row["id"], row["seq"], row["hash"]):
            wrong.append(f"different: {row['table']} {row['id']}: {tuple(found)} against {row}")
    return wrong
