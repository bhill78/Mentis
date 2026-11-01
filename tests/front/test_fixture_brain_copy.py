"""BRAIN-COPY: built from a read-only connection, sealed, and a mismatch fails.

The mechanics run on a small master made from BRAIN-SEED, so they can be broken. One test holds
the real master to its committed manifest.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat

import pytest

from tests.front.conftest import COPY_MANIFEST
from tools.r1 import common, copy_brain


@pytest.fixture
def small(brain_seed, tmp_path):
    source = tmp_path / "source"
    shutil.copytree(brain_seed, source)
    before = common.sha256_file(source / "corpus.db")
    master, manifest = tmp_path / "master", tmp_path / "manifest.json"
    doc = copy_brain.build(source, master, manifest)
    return {"source": source, "master": master, "manifest": manifest, "doc": doc,
            "source_before": before}


def test_the_manifest_says_everything_it_must(small):
    doc = small["doc"]
    assert doc["source"] == str(small["source"])
    assert doc["code_commit"] == common.head_of(common.code_dir())
    assert doc["verify_chain"]["intact"] is True
    assert doc["advance"] == [doc["rows"]["entry"], doc["rows"]["operational"],
                              doc["rows"]["delivery"]]
    assert set(doc["heads"]) == {"entry", "operational", "delivery"}
    assert set(doc["digests"]["trees"]) == {"artifacts", "instances", "presentation", "derived"}
    assert doc["digests"]["files"]["mentis-corpus.json"]
    assert doc["digests"]["corpus_db"]


def test_building_leaves_the_source_alone_and_seals_the_master(small):
    assert common.sha256_file(small["source"] / "corpus.db") == small["source_before"]
    for path in small["master"].rglob("*"):
        if path.is_file():
            assert not os.stat(path).st_mode & stat.S_IWRITE, f"{path} is writable"
    assert not list(small["master"].glob("corpus.db-*"))
    with pytest.raises(SystemExit):
        copy_brain.build(small["source"], small["master"], small["manifest"])


def test_a_fresh_copy_checks_and_is_writable(small, tmp_path):
    copy = copy_brain.fresh(tmp_path / "copy", small["master"], small["manifest"])
    assert os.stat(copy / "corpus.db").st_mode & stat.S_IWRITE
    copy_brain.check(copy, small["manifest"], verify_chain=True)


def _change_an_artifact(copy):
    one = next(p for p in sorted((copy / "artifacts").rglob("*")) if p.is_file())
    one.write_bytes(one.read_bytes() + b"x")


def _lose_the_artifacts(copy):
    shutil.rmtree(copy / "artifacts")


def _lose_the_marker(copy):
    (copy / "mentis-corpus.json").unlink()


def _lose_a_row(copy):
    conn = sqlite3.connect(copy / "corpus.db")
    conn.execute("DELETE FROM scratch_setting")
    conn.commit()
    conn.close()


@pytest.mark.parametrize("fault", [_change_an_artifact, _lose_the_artifacts, _lose_a_row,
                                   _lose_the_marker])
def test_a_mismatch_fails_and_says_where(small, tmp_path, fault):
    copy = copy_brain.fresh(tmp_path / "copy", small["master"], small["manifest"])
    fault(copy)
    with pytest.raises(copy_brain.Mismatch):
        copy_brain.check(copy, small["manifest"])


def test_no_master_fails_rather_than_skips(tmp_path):
    with pytest.raises(copy_brain.Mismatch):
        copy_brain.fresh(tmp_path / "copy", tmp_path / "nothing", COPY_MANIFEST)


def test_the_real_master_is_what_its_committed_manifest_says(brain_copy):
    copy_brain.check(brain_copy, COPY_MANIFEST, verify_chain=True)
    doc = json.loads(COPY_MANIFEST.read_text(encoding="utf-8"))
    assert doc["tool_blob"] == common.git_blob(common.HERE / "copy_brain.py")
    assert doc["verify_chain"]["intact"] is True
    assert set(doc["digests"]["trees"]) == set(copy_brain.SIBLING_DIRS)
    for name, tree in doc["digests"]["trees"].items():
        assert tree["files"] > 0, f"{name}/ was empty when the master was built"
    for path in common.master_dir().rglob("*"):
        if path.is_file():
            assert not os.stat(path).st_mode & stat.S_IWRITE, f"{path} is writable"
    assert not list(common.master_dir().glob("corpus.db-*"))
