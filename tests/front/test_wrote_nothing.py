"""Row I: Rust wrote nothing. `R1-acceptance.md`, "I: Rust wrote nothing, 3". A fresh BRAIN-COPY.

Not "Brain byte-identical", which Python's own startup can make false: so the front-only session
has no Python in it, and the restart compares what a restart adds.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import time

from tests.front import test_sqlite as pair
from tools.r1 import common, copy_brain

#: What `retire_unconsumable` writes, `web/permissions.py:399`.
RETIRED_ACT = "expectation-met"

#: Whatever opens a file, or reads or writes one by path, in Rust.
OPENS_A_FILE = re.compile(
    r"File::(open|create|options)|OpenOptions|fs::(read|write|copy|rename|remove_file|hard_link)"
    r"|CreateFile|libc::open")
NAMES_THE_DATABASE = re.compile(r"corpus\.db|CORPUS_DB")
OPENS_A_CONNECTION = re.compile(r"Connection::open|open_with_flags|sqlite3_open")


def state_of(brain) -> dict:
    """Row counts per table and `advance()`, from `copy_brain`, on nothing holding it open."""
    held = copy_brain._positions(brain / "corpus.db")
    return {"rows": held["rows"], "advance": held["advance"]}


def digests_of(brain) -> dict:
    return copy_brain.digests(brain)


def test_a_front_only_session_changes_nothing(brain_copy):
    state, digests = state_of(brain_copy), digests_of(brain_copy)
    with pair.running_front(brain_copy):
        for path in ("/api/pulse", "/fluid/api/topics?q=load", "/fluid/api/names?ids=ent-nothing",
                     "/"):
            assert pair.get(path)[0] == 200, path
        # Something forwarded, with nothing behind the front to take it: the front only answers.
        assert pair.get("/api/server")[0] == 503
    assert state_of(brain_copy) == state
    assert digests_of(brain_copy) == digests, "corpus.db or a sibling changed under a reader"


def test_a_python_restart_adds_only_retire_unconsumables_acts(brain_copy):
    with pair.running_pair(brain_copy) as running:
        before = _record_position(brain_copy)
        running.kill_python()
        filled = {"{brain}": str(brain_copy), "{port}": str(pair.PORT),
                  "{ws}": str(running.run / "ws"), "{mars}": pair.NO_MARS,
                  "{run}": str(running.run)}
        command = [filled.get(word, word) for word in pair.template() if word != "--attached"]
        restarted = subprocess.run(command + ["--only", "python"], cwd=running.run,
                                   env=pair.environment(), capture_output=True, text=True,
                                   encoding="utf-8", timeout=pair.START_LIMIT_S)
        assert restarted.returncode == 0, restarted.stdout + restarted.stderr
        pair.wait_for_server(pair.PORT + 10000)
        time.sleep(1)
        after = _record_position(brain_copy)
        added = _acts_after(brain_copy, before["operational"])
    assert after["entry"] == before["entry"], "an entry appeared"
    assert after["delivery"] == before["delivery"], "a delivery appeared"
    assert [a for a in added if a["act"] != RETIRED_ACT] == [], added
    assert len(added) == after["operational"] - before["operational"]
    # Each is listed, for the release report.
    (common.fixtures_root() / "row-I-restart.json").write_text(
        json.dumps(added, indent=1) + "\n", encoding="utf-8")


def _record_position(brain) -> dict:
    conn = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        return {t: conn.execute(f"SELECT COALESCE(MAX(seq), 0) FROM {t}").fetchone()[0]
                for t in ("entry", "operational", "delivery")}
    finally:
        conn.close()


def _acts_after(brain, seq: int) -> list[dict]:
    conn = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        return [{"seq": s, "id": i, "act": a, "because": b} for s, i, a, b in conn.execute(
            "SELECT seq, id, act, because FROM operational WHERE seq > ? ORDER BY seq", (seq,))]
    finally:
        conn.close()


def _code_of(path) -> list[str]:
    """A Rust file's lines, less what is in comments."""
    return [line.split("//", 1)[0] for line in
            path.read_text(encoding="utf-8").splitlines()]


def test_corpus_db_is_opened_read_only_and_only_through_sqlite():
    crates = common.REPO / "crates"
    files = sorted(crates.rglob("*.rs"))
    assert len(files) > 5, "the workspace's source is where it was"
    wrong = []
    for path in files:
        if path.name == "source_check.rs":
            continue
        lines = _code_of(path)
        if any(NAMES_THE_DATABASE.search(line) for line in lines):
            wrong += [f"{path}: {line.strip()}" for line in lines if OPENS_A_FILE.search(line)]
    assert not wrong, wrong

    source = crates / "mentis-record" / "src"
    opening = []
    for path in sorted(source.rglob("*.rs")):
        opening += [(path.name, line.strip()) for line in _code_of(path)
                    if OPENS_A_CONNECTION.search(line)]
    assert opening == [("open.rs", "let conn = Connection::open_with_flags(db, OPEN_FLAGS)?;")]

    contract = (source / "lib.rs").read_text(encoding="utf-8")
    flags = contract[contract.index("pub const OPEN_FLAGS"):contract.index("pub const OPEN_PRAGMAS")]
    assert "SQLITE_OPEN_READ_ONLY" in flags
    assert "READ_WRITE" not in flags and "CREATE" not in flags
    assert "immutable=" not in "\n".join(line for path in sorted(source.rglob("*.rs"))
                                         for line in _code_of(path))

    # And only this crate can reach a connection at all.
    for manifest in sorted(crates.glob("*/Cargo.toml")):
        if manifest.parent.name != "mentis-record":
            assert "rusqlite" not in manifest.read_text(encoding="utf-8"), manifest
