"""An older reader refuses a 0002-erasure Brain, and writes nothing to it (owner, 2026-11-14).

0002-erasure raises `min_reader` to 2. A release from before it -- `OLD_PY_COMMIT`'s Python, and the
front DAY-TO-DAY serves (`msel-front-62a67e4`, copied beside the fixtures) -- must say plainly that
it can't serve such a Brain, and leave it exactly as it was: the record's bytes, its chain, the
deletion ledger and its erase sets. The Brain is a copy of the erasure fixture, which holds one
permanently deleted Conversation and its ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess

import pytest

from tools.r1 import common

#: A free port nothing in this suite uses.
PORT = 8961


def _fixture() -> pathlib.Path:
    source = common.fixtures_root() / "erasure"
    assert (source / "brain" / "corpus.db").is_file(), f"no erasure fixture at {source}"
    return source


@pytest.fixture
def migrated(tmp_path):
    """A copy of the erasure fixture beside its ledger and erase sets, as a Brain sits."""
    source = _fixture()
    shutil.copytree(source / "brain", tmp_path / "brain")
    shutil.copytree(source / "brain.erasures", tmp_path / "brain.erasures")
    shutil.copyfile(source / "brain.erasures.jsonl", tmp_path / "brain.erasures.jsonl")
    return tmp_path / "brain"


def _digest(path) -> str:
    h = hashlib.sha256()
    for p in sorted(pathlib_walk(path)):
        h.update(str(p.relative_to(path)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def pathlib_walk(path) -> list:
    return [p for p in pathlib.Path(path).rglob("*") if p.is_file()]


def _state(brain) -> dict:
    """Everything the older reader must leave as it was."""
    parent = brain.parent
    return {
        "corpus_db": common.sha256_file(brain / "corpus.db"),
        "artifacts": common.tree_digest(brain / "artifacts"),
        "ledger": common.sha256_file(parent / "brain.erasures.jsonl"),
        "erase_sets": _digest(parent / "brain.erasures"),
        "chain": _chain(brain),
        "ledger_rows": _rows(brain, "schema_migration"),
        "wal": (brain / "corpus.db-wal").is_file() and (brain / "corpus.db-wal").stat().st_size,
    }


def _rows(brain, table) -> list:
    conn = sqlite3.connect(f"file:{(brain / 'corpus.db').as_posix()}?mode=ro", uri=True)
    try:
        return [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
    finally:
        conn.close()


def _chain(brain) -> dict:
    """This commit's verifier over a bare read-only connection: the chain as it stands."""
    code = ("import json, sqlite3, sys\n"
            "from mentis.spine import backup\n"
            "conn = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True)\n"
            "conn.row_factory = sqlite3.Row\n"
            "got = backup._chain(conn)\n"
            "got.pop('note', None)\n"
            "print(json.dumps(got, sort_keys=True))\n")
    done = subprocess.run([str(common.venv_python()), "-c", code, (brain / "corpus.db").as_posix()],
                          cwd=common.REPO, capture_output=True, text=True, encoding="utf-8",
                          env=_env(), check=True)
    return json.loads(done.stdout)


def _env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("MENTIS") and k.upper() != "PYTHONPATH"}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    return env


def _new_files(brain, before: set) -> list:
    return sorted(str(p.relative_to(brain)) for p in pathlib_walk(brain)
                  if p.relative_to(brain).as_posix() not in before)


def _names(brain) -> set:
    return {p.relative_to(brain).as_posix() for p in pathlib_walk(brain)}


def _left_alone(brain, before: dict, names: set) -> None:
    after = _state(brain)
    assert after == before, "the older reader changed the Brain, its chain or its ledger"
    assert after["chain"]["intact"] is True
    # A lock file it takes to say it is there, empty, is the only thing it may leave.
    for name in _new_files(brain, names):
        assert name.startswith(".mentis.") and name.endswith(".lock"), name
        assert (brain / name).stat().st_size == 0, name


def test_the_older_python_refuses_to_serve_it_and_writes_nothing(migrated, tmp_path):
    old = common.old_code_dir()
    assert (old / "mentis" / "web" / "__init__.py").is_file(), f"no {common.OLD_PY_COMMIT} at {old}"
    before, names = _state(migrated), _names(migrated)
    assert before["chain"]["intact"] is True and before["chain"]["erasures"]["rows"] > 0
    done = subprocess.run(
        [str(common.venv_python()), "-m", "mentis.web", str(migrated), "--port", str(PORT),
         "--workspace", str(tmp_path / "ws"), "--mars", "workload-no-mars-here"],
        cwd=old, env=_env(), capture_output=True, text=True, encoding="utf-8", timeout=120)
    said = done.stdout + done.stderr
    assert done.returncode != 0, said
    assert "needs a reader of at least 2" in said and "It needs a newer Mentis" in said, said
    assert "Traceback" not in said, said
    _left_alone(migrated, before, names)


def test_the_older_python_opens_it_for_writing_only_to_refuse(migrated):
    """Its API, asked to write, refuses the same way, and leaves the Brain as it was."""
    before, names = _state(migrated), _names(migrated)
    code = ("import sys\n"
            "import mentis.api as api\n"
            "from mentis.spine import migrations\n"
            "try:\n"
            "    api.open_corpus(sys.argv[1], access='write')\n"
            "except migrations.BrainNotWritable as exc:\n"
            "    print('REFUSED', exc)\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit('opened writable')\n")
    done = subprocess.run([str(common.venv_python()), "-c", code, str(migrated)],
                          cwd=common.old_code_dir(), env=_env(), capture_output=True, text=True,
                          encoding="utf-8", timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.startswith("REFUSED") and "needs a newer Mentis" in done.stdout, done.stdout
    _left_alone(migrated, before, names)


def test_the_older_front_refuses_to_open_it_and_writes_nothing(migrated):
    front = common.old_front()
    assert front.is_file(), f"no older front at {front}"
    before, names = _state(migrated), _names(migrated)
    done = subprocess.run([str(front), "--verify-chains", str(migrated)], env=_env(),
                          capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert done.returncode == 3, done.stdout + done.stderr
    assert "this build does not read this Brain's schema" in done.stderr, done.stderr
    assert "0002-erasure" in done.stderr, done.stderr
    assert done.stdout == ""
    _left_alone(migrated, before, names)
