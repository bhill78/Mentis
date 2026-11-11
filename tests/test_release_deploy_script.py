"""The modernize release helper's ordering guarantees (review M5, M6):
tools/release_modernize/deploy.ps1, read as text (it is never run by a test)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "release_modernize" / "deploy.ps1"


def _main_flow() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    return text[text.index("$downAt = Get-Date"):]


def test_a_stop_that_fails_part_way_leads_to_the_rollback():
    """M5: `stopped` is set before the stop begins and Stop-Pair runs inside the
    try whose catch rolls back, so a throwing stop never leaves DAY-TO-DAY down
    without a rollback, and the verdict says "after stop"."""
    flow = _main_flow()
    stopped = flow.index("$script:stopped = $true")
    opened = flow.index("try {", stopped)
    stop = flow.index("Stop-Pair", stopped)
    assert stopped < opened < stop, "Stop-Pair must run inside the try, after stopped is set"
    assert "Stop-Pair" not in flow[:opened], "no stop before the rolling-back try"
    rollback = flow.index("} catch { Rollback $_.Exception.Message }")
    assert stop < rollback
    assert "' after stop'" in flow


def test_retention_runs_only_after_a_passed_restore_check():
    """M6: an older backup is never deleted when the new one's restore check failed."""
    flow = _main_flow()
    ok_set = flow.index("$restoreOk = $true")
    verify = flow.index("'verify-restore'")
    guard = flow.index("if ($restoreOk) {")
    retain = flow.index("'retain'")
    assert verify < ok_set < guard < retain
    assert "retention skipped" in flow


@pytest.mark.skipif(not shutil.which("powershell.exe"), reason="Windows PowerShell not present")
def test_the_script_still_parses():
    cmd = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
           f"'{SCRIPT}', [ref]$null, [ref]$e); $e.Count")
    out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
                         capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "0", out.stdout + out.stderr
