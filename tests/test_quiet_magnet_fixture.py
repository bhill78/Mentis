"""Focused fixture preconditions. Runtime browser/navigation checks live with the candidate."""
import json
from pathlib import Path

import mentis.api as api
from mentis import artifacts, magnet
from mentis.fluid import arrangements
from tools.quiet_magnet_fixture import REPO, seed, snapshot, safe_root


def test_representative_setup_owns_distinct_conversations_and_artifacts(tmp_path):
    root = tmp_path / "fixture"
    manifest = seed(root)
    assert manifest["setup_closed"]
    p, second = manifest["primary"], manifest["secondary"]
    assert len({p["A"], p["B"], p["C"]}) == 3
    assert p["corpus_id"] != second["corpus_id"]
    assert p["source_posts"] > 20 and p["dated_out_posts"] > 0
    assert p["magnets"]["primary"] != p["magnets"]["missing_own"]
    corpus = api.open_corpus(str(root / "primary"), access="read")
    cv = api.conversations(corpus)
    try:
        assert magnet.read(corpus.root, p["magnets"]["primary"])["conversation"] == p["C"]
        assert not magnet.read(corpus.root, p["magnets"]["missing_own"]).get("conversation")
        claims = corpus.operational(act="own-conversation-claimed", detail_is={"magnet": p["magnets"]["primary"]})
        assert claims[0]["conversation"] == p["C"]
        for item in ("held_file", "attachment", "image"):
            assert artifacts.describe(corpus, p[item]["ref"])["state"] == "held"
            post = corpus.read([p[item]["post"]])[0]
            assert p[item]["ref"] in {part.get("ref") for part in post["body"]["parts"]}
        assert cv.conversation_name(p["C"]).startswith("Fixture C")
    finally:
        corpus.close()
    assert snapshot(root) == json.loads((root / "seed-baseline.json").read_text("utf-8"))


def test_seed_refuses_existing_work_and_root_escapes(tmp_path):
    import pytest
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("preserved")
    with pytest.raises(ValueError, match="existing directory"):
        seed(occupied)
    assert (occupied / "keep.txt").read_text() == "preserved"
    with pytest.raises(ValueError, match="inside this checkout"):
        safe_root(REPO.parent)


def test_snapshot_reads_without_changing_main_record_or_artifact_bytes(tmp_path):
    root = tmp_path / "fixture"
    seed(root)
    before = snapshot(root)
    after = snapshot(root)
    assert before == after
    assert before["primary"]["held"]
    assert before["primary"]["content_files"]
