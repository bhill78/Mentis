"""PY-ALONE starts as the document says, on BRAIN-SEED, running PY_COMMIT."""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

from tests.front import restart_messages
from tools.r1 import common, py_alone


def test_it_runs_the_fixed_commit_on_a_seed_copy_and_answers(brain_seed, tmp_path):
    copy = tmp_path / "brain"
    shutil.copytree(brain_seed, copy)
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
    from mentis.worker import CAPABILITY_HEADER, NotPermitted, _over

    copy = tmp_path / "brain"
    shutil.copytree(brain_seed, copy)
    via = f"http://127.0.0.1:{py_alone.PORT}"
    with py_alone.running(copy):
        received = time.time()
        with pytest.raises(NotPermitted) as refused:
            _over(via, str(copy), "answer", {}, "no-such-grant")
        told = f"{refused.type.__name__}: {refused.value}"
        request = urllib.request.Request(
            f"{via}/api/worker", method="POST",
            headers={"Content-Type": "application/json", CAPABILITY_HEADER: "no-such-grant"},
            data=json.dumps({"corpus": str(copy), "op": "answer", "args": {}}).encode("utf-8"))
        with pytest.raises(urllib.error.HTTPError) as answered:
            urllib.request.urlopen(request, timeout=10)
        assert answered.value.code == 403
        line = {"received_at": received, "answered_at": time.time(),
                "body": answered.value.read().decode("utf-8", "replace")}
        (tmp_path / "worker-refusals.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
        refusals = restart_messages.Refusals(tmp_path / "worker-refusals.jsonl",
                                             copy / "corpus.db")
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
