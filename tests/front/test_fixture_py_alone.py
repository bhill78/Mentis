"""PY-ALONE starts as the document says, on BRAIN-SEED, running PY_COMMIT."""

from __future__ import annotations

import json
import shutil
import time
import urllib.parse

import pytest

from tests.front import restart_messages
from tools.r1 import common, door_recorder, py_alone


def test_it_runs_the_fixed_commit_on_a_seed_copy_and_answers(brain_seed, tmp_path):
    copy = tmp_path / "brain"
    shutil.copytree(common.recorded(brain_seed), copy)
    with py_alone.running(copy):
        status, body = py_alone.get(py_alone.PORT, "/api/server")
        assert status == 200
        server = json.loads(body)
        assert server["code"]["commit"].startswith(common.PY_COMMIT)
        assert server["code"]["dirty"] is False
        assert server["process"]["port"] == py_alone.PORT
        assert server["corpus"] == str(copy)
        status, body = py_alone.get(py_alone.PORT, "/fluid/api/topics?q=load")
        assert status == 200
        assert "Load testing" in body.decode("utf-8")
        for words in ("mag", "rev", "sta"):
            assert py_alone.get(py_alone.PORT, "/fluid/api/topics?q=" + urllib.parse.quote(words))[0] == 200


def test_a_refusal_from_its_door_passes_row_j_on_that_calls_evidence(brain_seed, tmp_path):
    from mentis.worker import NotPermitted, _over

    copy = tmp_path / "brain"
    shutil.copytree(common.recorded(brain_seed), copy)
    with py_alone.running(copy), door_recorder.DoorRecorder(py_alone.PORT) as recorder:
        before = time.time()
        with pytest.raises(NotPermitted) as refused:
            _over(recorder.url, str(copy), "answer", {}, "no-such-grant")
        after = time.time()
        told = f"{refused.type.__name__}: {refused.value}"
        # One call, so one line: the message and its evidence are the same answer.
        assert len(recorder.refusals) == 1
        line = recorder.refusals[0]
        assert before <= line["received_at"] <= line["answered_at"] <= after
        assert restart_messages.told_for(line["body"]) == told
        refusals = restart_messages.Refusals(recorder, copy / "corpus.db")
        assert restart_messages.decide(told, refusals=refusals) == ["Refused"], refusals.failed


def test_its_environment_holds_nothing_of_another_mentis(monkeypatch):
    monkeypatch.setenv("MENTIS_FLUID_DIST", "elsewhere")
    monkeypatch.setenv("MENTIS_BOOT_SECRET", "from elsewhere")
    monkeypatch.setenv("PYTHONPATH", "elsewhere")
    env = py_alone.environment()
    assert env["MENTIS_FLUID_DIST"] == str(common.dist_dir())
    assert "MENTIS_BOOT_SECRET" not in env and "PYTHONPATH" not in env


def test_it_refuses_the_master_and_never_takes_the_day_to_day_port():
    assert py_alone.PORT != 8760
    with pytest.raises(SystemExit):
        with py_alone.running(common.master_dir()):
            pass
