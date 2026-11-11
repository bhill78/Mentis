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


def _function(name: str) -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index(f"function {name}(")
    end = text.index("\n}\n", start) + 3
    return text[start:end]


@pytest.mark.skipif(not shutil.which("powershell.exe"), reason="Windows PowerShell not present")
def test_the_new_run_command_names_the_local_worker_python_and_the_rollback_does_not(tmp_path):
    """Round 3 final (B4): MARS_LOCAL_PYTHON is set in the NEW pair's run command when the
    interpreter is usable; without one (or for the rollback pair) the line is a remark and
    nothing else in the command changes."""
    body = _function("Write-RunCommand")
    new, old = tmp_path / "new.cmd", tmp_path / "old.cmd"
    script = tmp_path / "write.ps1"
    script.write_text(
        "$RouteTable=''; $RunDir='C:/r'; $Repo='C:/c'; $Brain='C:/b'; $Port=1; $PrivatePort=2;"
        " $Work='C:/w'; $Python='C:/p.exe'; $Dist='C:/d'\n" + body + "\n"
        f"Write-RunCommand '{new}' 'L.exe' 'F.exe' 'M.exe' 'C:/venv/Scripts/python.exe'\n"
        f"Write-RunCommand '{old}' 'L.exe' 'F.exe' 'M.exe'\n", encoding="utf-8")
    out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                          "Bypass", "-File", str(script)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
    new_lines = new.read_text(encoding="ascii").splitlines()
    old_lines = old.read_text(encoding="ascii").splitlines()
    assert 'set "MARS_LOCAL_PYTHON=C:/venv/Scripts/python.exe"' in new_lines
    assert not any("MARS_LOCAL_PYTHON=" in line for line in old_lines)
    assert [ln for ln in new_lines if "MARS_LOCAL_PYTHON" not in ln] == \
        [ln for ln in old_lines if "MARS_LOCAL_PYTHON" not in ln]


def test_a_missing_local_worker_python_never_aborts_the_release():
    text = SCRIPT.read_text(encoding="utf-8")
    block = text[text.index("$script:LocalPythonUse = ''\n  if (Test-Path -LiteralPath $LocalPython)"):]
    block = block[:block.index("\n  foreach ($check in")]
    assert "Abort" not in block and "throw" not in block
    assert "Write-RunCommand $RunCmd $Launcher $Front $Mars $script:LocalPythonUse" in text
    assert "Write-RunCommand $RollbackCmd $OldLauncher $OldFront $LaunchOldMars\n" in text


def test_live_deploy_needs_the_owner_credential_and_rollback_starts_as_before():
    """Round-3 final review S5: a live deploy aborts without the owner's credential (a
    rehearsal only says so), and only the NEW pair's run command carries the route table."""
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "tools" / "release_modernize"
            / "deploy.ps1").read_text(encoding="utf-8")
    assert "owner-auth.json" in text and "owner credential missing" in text
    assert "if ($Rehearse) { Log \"owner credential missing" in text
    assert "else { Abort \"owner credential missing" in text
    assert "$RouteTable -and $NewPair" in text
    assert "Write-RunCommand $RunCmd $Launcher $Front $Mars $script:LocalPythonUse $true" in text
    assert "Write-RunCommand $RollbackCmd $OldLauncher $OldFront $LaunchOldMars\n" in text
