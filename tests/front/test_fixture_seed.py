"""BRAIN-SEED builds the same twice, and what it is called is what it holds."""

from __future__ import annotations

import json
import shutil
import sqlite3

from tests.front.conftest import SEED_IDENTITY, build_seed
from tools.r1 import seed_brain


def test_two_builds_are_identical_and_are_the_recorded_identity(tmp_path):
    first = build_seed(tmp_path / "one")
    second = build_seed(tmp_path / "two")
    assert first == second
    assert first == json.loads(SEED_IDENTITY.read_text(encoding="utf-8"))
    assert (tmp_path / "one" / "corpus.db").read_bytes() == (
        tmp_path / "two" / "corpus.db").read_bytes()


def test_the_content_digest_sees_one_changed_column(brain_seed, tmp_path):
    copy = tmp_path / "brain"
    shutil.copytree(brain_seed, copy)
    before = seed_brain.content_digest(copy)
    conn = sqlite3.connect(copy / "corpus.db")
    conn.execute("UPDATE scratch_setting SET retain_days = retain_days + 1")
    conn.commit()
    conn.close()
    assert seed_brain.content_digest(copy)["sha256"] != before["sha256"]


def test_it_holds_what_the_tests_name(brain_seed):
    db = (brain_seed / "corpus.db").as_posix()
    conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT json_extract(body, '$.name') FROM entry WHERE def_name = 'conversation'")}
        posts = conn.execute(
            "SELECT COUNT(*) FROM entry WHERE def_name = 'contribution' "
            "AND body LIKE '%R1 known post: the harbour light is lit at dusk.%'").fetchone()[0]
    finally:
        conn.close()
    assert {"R1 known conversation", "R1 second conversation"} <= names
    assert posts == 1
    assert (brain_seed / "mentis-corpus.json").is_file()
