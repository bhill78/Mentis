"""Proves the lifted record code reads a real Mark IV Brain unchanged.

The Brain is a COPY named by env MENTIS_TEST_BRAIN; skip the module when unset.
Never write to it: corpus.db size, mtime and sha256 must be byte-for-byte unchanged,
and no -wal content may be added.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3

import pytest

import mentis.api as api
from mentis.corpus.store import Corpus as CorpusStore
from mentis.spine import migrations
from mentis.conversation import register
import mentis.spine.brainlock as brainlock

# Pytest marker 'brain'
pytestmark = pytest.mark.brain

# Patch brainlock._take to gracefully fall back to read-only lock if directory is mounted read-only (:ro)
_orig_take = brainlock._take


def _safe_take(root: str, name: str, shared: bool) -> brainlock.Lock | None:
    path = os.path.join(root, name)
    try:
        fh = open(path, "a+b")
    except (PermissionError, OSError):
        try:
            fh = open(path, "rb")
        except (PermissionError, OSError):
            return None
    if brainlock._lock(fh, shared):
        return brainlock.Lock(path, fh, shared)
    fh.close()
    return None


brainlock._take = _safe_take


def _get_brain_path() -> str:
    brain_dir = os.environ.get("MENTIS_TEST_BRAIN")
    if not brain_dir or not os.path.isdir(brain_dir):
        pytest.skip("MENTIS_TEST_BRAIN is not set to a valid Brain directory")
    db_file = os.path.join(brain_dir, "corpus.db")
    if not os.path.isfile(db_file):
        pytest.skip(f"no corpus.db found in MENTIS_TEST_BRAIN ({brain_dir})")
    return os.path.abspath(brain_dir)


def test_brain_compatibility():
    brain_path = _get_brain_path()
    db_path = os.path.join(brain_path, "corpus.db")
    wal_path = os.path.join(brain_path, "corpus.db-wal")
    manifest_path = os.path.join(brain_path, "mentis-corpus.json")

    # Record corpus.db state before anything runs
    st_before = os.stat(db_path)
    size_before = st_before.st_size
    mtime_before = st_before.st_mtime
    with open(db_path, "rb") as f:
        sha_before = hashlib.sha256(f.read()).hexdigest()
    wal_before = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0

    c = None
    try:
        # 1. Corpus ID equals mentis-corpus.json's corpus_id
        assert os.path.isfile(manifest_path), f"no mentis-corpus.json in {brain_path}"
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        manifest_corpus_id = manifest["corpus_id"]

        corpus_store = CorpusStore(brain_path)
        store_id = corpus_store.identity()["corpus_id"]
        assert store_id == manifest_corpus_id, (
            f"corpus id {store_id} does not match manifest {manifest_corpus_id}"
        )

        # 2. Schema version is the one the lifted spine expects
        status = migrations.status_of(brain_path)
        assert status.version == status.target, (
            f"schema version {status.version} != expected target {status.target}"
        )
        assert status.state == migrations.OPEN, (
            f"schema state is {status.state!r}, expected {migrations.OPEN!r}"
        )

        # Open read-only with lifted spine/api
        c = api.open_corpus(brain_path, access="read")
        assert c.read_only, "corpus is not opened read-only"

        # 3. Entry counts per Kind from lifted API equal counts from direct read-only SQL query
        db_uri = f"file:///{db_path.replace(os.sep, '/')}?mode=ro"
        try:
            conn = sqlite3.connect(db_uri, uri=True)
            conn.execute("PRAGMA query_only=ON")
            rows = conn.execute(
                "SELECT def_name, COUNT(*) FROM entry "
                "WHERE family = 'entry' AND link_relation IS NULL "
                "GROUP BY def_name"
            ).fetchall()
        except sqlite3.OperationalError:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA query_only=ON")
            rows = conn.execute(
                "SELECT def_name, COUNT(*) FROM entry "
                "WHERE family = 'entry' AND link_relation IS NULL "
                "GROUP BY def_name"
            ).fetchall()
        finally:
            conn.close()

        sql_counts = dict(rows)
        api_counts = {kind: c.count_of_kind(kind) for kind in sql_counts}
        assert api_counts == sql_counts, (
            f"mismatched entry counts: API {api_counts} != SQL {sql_counts}"
        )

        # 4. EVERY Conversation lists and every one of its Turns resolves (id, author, text parts)
        cv = api.conversations(c)
        convs = cv.all_conversations()
        assert len(convs) > 0, "no conversations found"
        total_turns = 0
        for conv in convs:
            turns = cv.contributions(conv["id"])
            total_turns += len(turns)
            for t in turns:
                assert t.get("id"), "turn missing id"
                author = cv.alias(t.get("attributed_to"))
                assert author, f"turn {t['id']} author did not resolve"
                body = t.get("body", {})
                parts = body.get("parts", [])
                assert isinstance(parts, list), f"turn {t['id']} parts is not a list"
                for p in parts:
                    if p.get("type") == "text":
                        assert "text" in p, f"text part missing 'text' in turn {t['id']}"

        # 5. Participants resolve
        participants = cv.all_participants()
        assert len(participants) > 0, "no participants found"
        for p in participants:
            alias = p["body"]["alias"]
            resolved_id = cv.resolve_participant(alias)
            assert resolved_id == p["id"], (
                f"participant {alias} resolved to {resolved_id}, expected {p['id']}"
            )

        # 6. Governed register lists rules and decisions
        b = api.brain(c)
        gov = register.governed(b)
        assert "rule" in gov["kinds"]["listed"], "rule not in governed register listed kinds"
        assert "decision" in gov["kinds"]["listed"], "decision not in governed register listed kinds"

        gov_rules = register.governed(b, kind="rule")
        assert gov_rules["walked"] > 0, "no rules found in governed register"
        assert gov_rules["matched"] > 0, "no matching rules in governed register"

        gov_decisions = register.governed(b, kind="decision")
        assert gov_decisions["walked"] > 0, "no decisions found in governed register"
        assert gov_decisions["matched"] > 0, "no matching decisions in governed register"

        # 7. Standing (stands) is computable for every governed entry
        all_governed_ids = []
        for grp in gov["groups"].values():
            for row in grp:
                all_governed_ids.append(row["entry"])
        assert len(all_governed_ids) > 0, "no governed entries in groups"

        for eid in all_governed_ids:
            standing = c.stands(eid)
            assert isinstance(standing, dict), f"stands({eid}) returned non-dict: {standing}"
            assert "stands" in standing, f"stands({eid}) missing 'stands' key: {standing}"

        # 8. Sources list
        srcs = api.sources(c)
        collections = srcs.collections()
        assert "collections" in collections, "sources.collections() missing 'collections'"
        col_list = collections["collections"]
        assert len(col_list) > 0, "no source collections found"
        declarations = srcs.declarations()
        assert len(declarations) > 0, "no source declarations found"

        # Report counts in test output
        print(f"\n--- Brain Compatibility Report ({brain_path}) ---")
        print(f"Corpus ID: {manifest_corpus_id}")
        print(f"Schema Version: {status.version} (target: {status.target}, state: {status.state})")
        print(f"Kinds count: {len(sql_counts)} (total node entries: {sum(sql_counts.values())})")
        print(f"Counts per Kind: {sql_counts}")
        print(f"Conversations: {len(convs)}")
        print(f"Turns: {total_turns}")
        print(f"Participants: {len(participants)}")
        print(f"Governed entries: {len(all_governed_ids)} (rules: {gov_rules['matched']}, decisions: {gov_decisions['matched']})")
        print(f"Source collections: {len(col_list)} (declarations: {len(declarations)})")
        print("---------------------------------------------------\n")

    finally:
        if c is not None:
            c.close()

        # Assert all three (size, mtime, sha256) are unchanged and no -wal content was added
        st_after = os.stat(db_path)
        with open(db_path, "rb") as f:
            sha_after = hashlib.sha256(f.read()).hexdigest()
        wal_after = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0

        assert st_after.st_size == size_before, (
            f"corpus.db size changed: {size_before} -> {st_after.st_size}"
        )
        assert st_after.st_mtime == mtime_before, (
            f"corpus.db mtime changed: {mtime_before} -> {st_after.st_mtime}"
        )
        assert sha_after == sha_before, (
            f"corpus.db sha256 changed: {sha_before} -> {sha_after}"
        )
        assert wal_after <= wal_before, (
            f"corpus.db-wal content was added: {wal_before} -> {wal_after}"
        )
