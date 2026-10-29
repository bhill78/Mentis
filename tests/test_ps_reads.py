"""PowerShell commands that only read, as asked of the owner on 2026-10-29
(@Caretaker's run): cmdlets that read by their verb, strings that only
substitute variables, and readers that read no directory while the shell's
directory is not reported."""

import os

import pytest

from mentis.operations import describe, read_only
from mentis.web import permissions as P

_PS = {"mars/tool": {"name": "PowerShell", "shell": "powershell"}}


def _op(command, cwd=r"C:\repo", meta=_PS):
    tc = {"kind": "execute", "title": command, "raw_input": {"command": command}}
    if meta:
        tc["field_meta"] = meta
    req = {"tool_call": tc}
    if cwd:
        req["shell_cwd"] = cwd
    return describe(req, cwd=None, workspaces=[r"C:\repo"], run_workspace=r"C:\repo")


def _allowed(op):
    return read_only(op) and op.within


@pytest.mark.parametrize("cwd", [r"C:\repo", None])
@pytest.mark.parametrize("command", [
    # asked of the owner, 2026-10-29
    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'mentis|fluid' -and "
    "$_.Name -match 'python|node' } | Select-Object ProcessId,CreationDate,CommandLine | Format-List; "
    r"Get-Content 'C:\repo\server.err.log' -Tail 15",
    r"Set-Location 'C:\repo'; git merge-base --is-ancestor f7a7446 HEAD; " + '"f7a7446 ancestor of HEAD: $LASTEXITCODE"',
    '"== $r"', '"${env:USERPROFILE}"', "Get-Date", "echo hi",
    "Get-NetTCPConnection -LocalPort 8760 -State Listen | Format-Table",
])
def test_powershell_that_only_reads_is_allowed(command, cwd):
    op = _op(command, cwd)
    assert _allowed(op), (command, op.summary, op.outside)


@pytest.mark.parametrize("command", [
    '"$(Remove-Item x)"', '"a $(Get-Date) b"',                  # a subexpression runs
    "Get-Credential", "Get-Clipboard", "Get-PackageProvider -Name NuGet",
    "Get-CimInstance Win32_Process -ComputerName srv1",         # another machine
    "Get-Help Get-Item -Online", "Test-Connection example.com",
    "Get-ChildItem " + os.path.join(os.path.expanduser("~"), ".ssh"),
    # found by the independent review, 2026-10-29
    r'"${C:\Users\x\.ssh\id_rsa}"', '"$C:notes.txt"', r'"${FileSystem::\\attacker\share\x}"',
    r"${C:\Users\x\.ssh\id_rsa}", "$C:notes.txt",
    r".\Get-Evil.ps1", r"C:\tmp\get-x.exe", r"tools\cat.exe x",
    "Get-Service -Co x", "Get-CimInstance Win32_Process -CimS $s", "Get-WmiObject Win32_Process -Cred x",
    "Get-WSManInstance -ResourceURI winrm/config -ConnectionURI http://attacker",
    "Get-Service spooler | % Stop", "Get-Process notepad | % Kill",
    r"Get-ChildItem C:\repo | ForEach-Object -MemberName Delete",
    "Get-AzAccessToken", "Get-History", "Get-WindowsUpdateLog",
    '"a\u201d;Remove-Item\tC:\\x;\u201cb"', r"Get-Content \\attacker\share\x", "Get-Content //attacker/share/x",
])
def test_powershell_that_may_do_more_stays_asked_without_a_cwd_too(command):
    assert not _allowed(_op(command, cwd=None)), command


@pytest.mark.parametrize("command", [
    "Get-ChildItem " + os.path.join(os.path.expanduser("~"), ".ssh"),
    r'"${C:\Users\x\.ssh\id_rsa}"', r".\Get-Evil.ps1", "Get-Service -Co x", "Get-Process notepad | % Kill",
    "Get-History", '"a\u201d;Remove-Item\tC:\\x;\u201cb"', r"Get-Content \\attacker\share\x",
])
def test_powershell_that_may_do_more_stays_asked(command):
    assert not _allowed(_op(command)), command


@pytest.mark.parametrize("command", ["Get-ChildItem", "git status", "Get-Content notes.txt"])
def test_a_read_of_an_unreported_directory_stays_asked(command):
    assert _allowed(_op(command))
    assert not _allowed(_op(command, cwd=None)), command


def test_a_glob_is_a_read_of_the_directory():
    bash = {"mars/tool": {"name": "Bash", "shell": "bash"}}
    assert not _allowed(_op("echo *", cwd=None, meta=bash))
    assert _allowed(_op("echo hi", cwd=None, meta=bash))


def test_verbs_are_read_as_powershell_only():
    bash = {"mars/tool": {"name": "Bash", "shell": "bash"}}
    assert _op("Get-CimInstance Win32_Process", meta=bash).category == "other"
    assert not _allowed(_op('"== $r"', meta=bash))


def test_the_owner_has_longer_than_marss_old_limit_and_less_than_its_new_one():
    assert 300 < P.WAIT_S < 1800
    assert P.POLL_LATER_S <= 2.0
