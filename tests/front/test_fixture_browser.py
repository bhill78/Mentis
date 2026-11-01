"""Row P5's check passes on a real Fluid build and fails on each deliberate fault."""

from __future__ import annotations

import json
import os
import subprocess

from tools.r1 import common


def test_the_check_passes_on_the_real_build_and_fails_when_broken(brain_seed, tmp_path):
    done = subprocess.run(
        [str(common.venv_python()), str(common.HERE / "prove_browser.py"), str(brain_seed),
         str(tmp_path / "work")],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    assert done.returncode == 0, done.stdout + done.stderr
    report = json.loads(done.stdout)
    assert report["real_build"]["passed"] is True
    faults = [k for k in report if k.startswith("fault_")]
    assert sorted(faults) == ["fault_api_read_aborted", "fault_known_post_absent",
                              "fault_page_error", "fault_script_missing",
                              "fault_stylesheet_missing"]
    assert not any(report[k]["passed"] for k in faults)
    assert report["fault_stylesheet_missing"]["checks"]["no_failed_same_origin_requests"] is False
    assert report["fault_page_error"]["checks"]["no_page_errors"] is False
    assert report["fault_known_post_absent"]["checks"][
        "fluid_controls_and_known_item_visible"] is False
