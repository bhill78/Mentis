"""The frozen baselines say what R1-acceptance.md says they say."""

from __future__ import annotations

import json

from tools.r1 import common


def _evidence(name: str) -> dict:
    return json.loads((common.EVIDENCE / name).read_text(encoding="utf-8"))


def test_row_l_is_45_passed_and_the_one_allowed_failure():
    doc = _evidence("row-L-b8e324c.json")
    assert doc["commit"].startswith(common.PY_COMMIT)
    assert doc["totals"] == {"failed": 1, "passed": 45}
    assert [n for n, o in doc["outcomes"].items() if o == "failed"] == [
        "tests/test_topic_lookup.py::test_find_numbers_hits_as_turn_number_does"]
    assert "MENTIS_FLUID_DIST" in doc["command"]
    assert doc["with_a_fluid_build"] == {"passed": 46}


def test_row_m_is_57_passed_and_the_one_runner_skip():
    doc = _evidence("row-M-b8e324c.json")
    assert doc["commit"].startswith(common.PY_COMMIT)
    assert doc["totals"] == {"passed": 57, "skipped": 1}
    assert [n for n, o in doc["outcomes"].items() if o == "skipped"] == ["fluid_objects_unit.mjs"]


def test_the_rebuild_proof_left_the_master_alone_and_made_a_new_identity():
    doc = _evidence("brain-copy-rebuild-proof.json")
    committed = _evidence("brain-copy-manifest.json")
    assert doc["tool_blob"] == common.git_blob(common.HERE / "copy_brain.py")
    assert doc["retained_master"]["unchanged"] is True
    assert doc["retained_master"]["digests_after"] == committed["digests"]
    assert doc["scratch_deleted"] is True
    rebuilt = doc["rebuilt"]
    assert rebuilt["verify_chain_intact"] is True
    assert rebuilt["checks_against_its_own_manifest_with_the_chain"] is True
    assert rebuilt["digests"]["corpus_db"] != committed["digests"]["corpus_db"]
    assert "isn't what" in rebuilt["refused_by_the_committed_manifest"]
    assert set(rebuilt["holds_the_committed_head_at_its_seq"].values()) == {True}


def test_j12_is_known_and_is_the_result_the_page_states():
    doc = _evidence("j12-probe.json")
    assert doc["code_commit"].startswith(common.PY_COMMIT)
    assert doc["open_conversation"]["statuses"] == [200, 200]
    assert doc["open_conversation"]["conversations_named"] == 2
    assert doc["record_discovered_work"]["statuses"] == [200, 200]
    assert doc["record_discovered_work"]["turns_saying"] == 2
    assert doc["record_discovered_work"]["work_discovered_acts"] == 2
    assert doc["take_up"]["statuses"] == [200, 403]
    assert doc["take_up"]["second_said"] == (
        "'<expectation>' is already carried; taking it up would take it from whoever has it")
    assert doc["take_up"]["carrier_is_the_session"] is True
