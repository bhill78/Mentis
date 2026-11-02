"""mentis-record's statement trace: off unless asked for, twice over, and what it writes is what the
bench reads. Here and not in the crate, because row G's 40 is the whole of `cargo test -p mentis-record`.
"""
import os, pathlib, shutil, sqlite3, subprocess, tomllib

import pytest

from .conftest import REPO
import run_workload as RW

PROBE = REPO / "tests" / "bench" / "trace_probe"
CRATE = REPO / "crates" / "mentis-record"
TARGET = REPO / "target" / "trace-probe"
MARK = "SELECT COUNT(*) AS trace_probe_mark FROM entry"
SCHEMA = """
    PRAGMA journal_mode=WAL;
    CREATE TABLE corpus (one INTEGER PRIMARY KEY, corpus_id TEXT, chained_from_first INTEGER);
    INSERT INTO corpus VALUES (1, 'corpus-under-test', 1);
    CREATE TABLE schema_migration (seq INTEGER PRIMARY KEY, id TEXT, checksum TEXT);
    CREATE TABLE entry (seq INTEGER PRIMARY KEY);
    CREATE TABLE operational (seq INTEGER PRIMARY KEY);
    CREATE TABLE delivery (seq INTEGER PRIMARY KEY);
"""


def build(tmp, *features):
    """The probe, copied out, because the next build replaces it where it was built."""
    subprocess.run(["cargo", "build", "--quiet", "--locked", "--manifest-path", str(PROBE / "Cargo.toml"),
                    "--target-dir", str(TARGET), *features], cwd=REPO, check=True, timeout=900)
    name = "with" if features else "without"
    return pathlib.Path(shutil.copy(TARGET / "debug" / "trace-probe.exe", tmp / f"{name}.exe"))


@pytest.fixture(scope="module")
def probes(tmp_path_factory):
    if not shutil.which("cargo"):
        pytest.skip("no cargo here")
    tmp = tmp_path_factory.mktemp("probes")
    return {"without": build(tmp), "with": build(tmp, "--features", "sql-trace")}


@pytest.fixture
def brain(probes, tmp_path):
    """A scratch Brain with the ledger this build names."""
    root = tmp_path / "brain"
    root.mkdir()
    ledger = subprocess.run([probes["without"], "ledger"], capture_output=True, text=True, check=True).stdout
    db = sqlite3.connect(root / "corpus.db")
    db.executescript(SCHEMA)
    for seq, line in enumerate(ledger.splitlines(), 1):
        db.execute("INSERT INTO schema_migration VALUES (?, ?, ?)", (seq, *line.split()))
    db.commit()
    db.close()
    return root


def read(exe, brain, cwd, trace_dir=None):
    env = {k: v for k, v in os.environ.items() if k != "WORKLOAD_TRACE_DIR"}
    if trace_dir:
        env["WORKLOAD_TRACE_DIR"] = str(trace_dir)
    got = subprocess.run([exe, "read", brain], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr
    assert got.stdout.strip() == "connections 2"


def test_no_manifest_turns_it_on():
    assert "default" not in tomllib.loads((CRATE / "Cargo.toml").read_text(encoding="utf-8"))["features"]
    for manifest in [REPO / "Cargo.toml", *(REPO / "crates").glob("*/Cargo.toml")]:
        if manifest.parent != CRATE:
            assert "sql-trace" not in manifest.read_text(encoding="utf-8"), manifest


def test_no_workspace_build_has_it():
    tree = subprocess.run(["cargo", "tree", "--locked", "--workspace", "-e", "features"], cwd=REPO,
                          capture_output=True, text=True, check=True, timeout=120).stdout
    assert "mentis-record" in tree and "sql-trace" not in tree


def test_the_code_is_behind_the_feature_at_the_one_place():
    lines = [x.strip() for x in (CRATE / "src" / "open.rs").read_text(encoding="utf-8").splitlines()]
    at = lines.index("let conn = Connection::open_with_flags(db, OPEN_FLAGS)?;")
    assert lines[at + 1:at + 3] == ['#[cfg(feature = "sql-trace")]', "let conn = crate::trace::switched_on(conn)?;"]
    lib = (CRATE / "src" / "lib.rs").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert '#[cfg(feature = "sql-trace")]\nmod trace;' in lib


def test_without_the_feature_the_variable_does_nothing(probes, brain, tmp_path):
    traces = tmp_path / "traces"
    traces.mkdir()
    read(probes["without"], brain, tmp_path, traces)
    assert list(traces.iterdir()) == []
    assert b"WORKLOAD_TRACE_DIR" not in probes["without"].read_bytes()


def test_with_the_feature_and_no_variable_it_stays_off(probes, brain, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    read(probes["with"], brain, work)
    assert list(work.iterdir()) == []
    assert not list(tmp_path.glob("trace-*.log")) and not list(brain.glob("trace-*.log"))


def test_asked_for_it_traces_every_connection_as_the_bench_reads_it(probes, brain, tmp_path):
    traces = tmp_path / "traces"
    traces.mkdir()
    read(probes["with"], brain, tmp_path, traces)
    assert len(list(traces.glob("trace-*.log"))) == 1
    rows = RW.load_trace(traces)
    assert rows, "nothing traced"
    assert all(r[2].startswith("rust:") for r in rows)
    assert [r[3] for r in rows].count(MARK) == 2, "one on each of the two connections"
    assert sum("query_only" in r[3] for r in rows) >= 2, "the trace starts before the pragmas"
    count = RW.count_window(rows, rows[0][0], rows[-1][0])
    assert count["request_thread_statements"] == count["all_threads_statements"] == len(rows)
    assert count["processes"] == 1 and count["request_thread_data"] >= 2


def test_a_trace_that_cannot_be_written_stops_rather_than_reads_as_no_statements(probes, brain, tmp_path):
    env = {**os.environ, "WORKLOAD_TRACE_DIR": str(tmp_path / "no" / "such" / "dir")}
    got = subprocess.run([probes["with"], "read", brain], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert got.returncode != 0 and "no statement trace at" in got.stderr
