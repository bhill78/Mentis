"""Negative controls: each barrier test has to fail on a build that gets the barrier wrong.
`docs/rust/R3-mirror.md`, section 8. **A barrier test that passes on its control counts as failed.**

`MENTIS_R3_FRONTS` names the directory `tools/r3/build_fronts.ps1` built.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

CONTROLS = {
    "after-first": ("tests/front/test_mirror_ownership.py", [
        "test_i18_a_complete_success_does_not_cross_ownership",
        "test_i19_suspended_part_way_and_resumed_before_the_bound",
        "test_i19_suspended_past_the_bound_it_is_aborted_and_then_released",
        "test_i21_a_client_that_does_not_drain_is_reset_and_never_gets_a_whole_answer",
    ]),
    "before-write": ("tests/front/test_mirror_ownership.py", [
        "test_i6_a_tail_stopped_after_its_checks_holds_a_replacement_off",
        "test_i6_past_the_claim_wait_the_replacement_refuses_and_changes_nothing",
    ]),
    "before-write-legacy": ("tests/front/test_mirror_legacy.py", [
        "test_i17b_a_tail_stopped_in_its_send_makes_an_older_python_refuse",
    ]),
    "no-serve": ("tests/front/test_mirror_legacy.py", [
        "test_i17a_an_older_python_past_the_serve_lock_stops_the_mirror",
        "test_i17b_a_tail_stopped_in_its_send_makes_an_older_python_refuse",
        "test_i17c_a_read_queued_on_a_suspended_front_with_the_old_owner_lock_still_held",
    ]),
}


def _control_front(name: str) -> str:
    fronts = os.environ.get("MENTIS_R3_FRONTS")
    assert fronts, "MENTIS_R3_FRONTS isn't set, so there are no controls and this fails"
    build = name.removesuffix("-legacy")
    exe = pathlib.Path(fronts) / build / "mentis-server.exe"
    assert exe.exists(), exe
    return str(exe)


@pytest.mark.parametrize("control", list(CONTROLS))
def test_each_barrier_test_fails_on_its_control(control, tmp_path):
    file, tests = CONTROLS[control]
    pattern = " or ".join(tests)
    env = {**os.environ, "MENTIS_R3_FRONT": _control_front(control)}
    done = subprocess.run(
        [sys.executable, "-m", "pytest", file, "-q", "--tb=no", "-rfE", "-p", "no:cacheprovider",
         "--basetemp", str(tmp_path / "t"), "-k", pattern],
        cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=1500)
    said = done.stdout + done.stderr
    failed = set(re.findall(r"^(?:FAILED|ERROR) \S+::(\S+)", said, flags=re.MULTILINE))
    passing = [test for test in tests if test not in failed]
    assert not passing, f"these passed on the {control} control:\n{passing}\n{said[-2000:]}"
