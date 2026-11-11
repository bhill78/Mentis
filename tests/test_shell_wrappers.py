"""Shell wrappers read as the command they run (round 2 E).

Codex sends a request to leave its sandbox as one command line: its argv quoted the POSIX
way, `"C:\\\\...\\\\powershell.exe" -Command '<script>'`. Mentis used to class every such
line "a shell command Mentis cannot read safely", so a commit the owner's consent includes
became an owner question (round 2 D, `codex-fixture-dev-ws`). A wrapper is now read as the
script it runs, classified exactly as that script would be on its own in the wrapper's
shell; one Mentis cannot read with confidence stays "cannot read safely".

The first three strings are the exact `raw_input.command` values codex-acp 2.3.0 sent in
D's live runs (C:\\Work\\Mentis-Test-Server\\r2-dev\\evidence: codex-fixture-dev-ws,
codex-fixture-narrow-ws, codex-oos-dev-ws).
"""

from __future__ import annotations

import pytest

from mentis.operations import (UNREADABLE_WRAPPER, describe, wrapped_command)
from mentis.web.permissions import decide

PS = '"C:\\\\Windows\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe"'
#: codex-fixture-dev-ws (commit), codex-fixture-narrow-ws (git add), codex-oos-dev-ws (network)
D_COMMIT = PS + " -Command 'git add calc/stats.py; git commit -m \"Fix mean: divide by the number of values\"'"
D_ADD = PS + " -Command 'git add calc/stats.py'"
D_CURL = PS + " -Command 'curl.exe -sS -m 10 -o NUL -w \"%{http_code}\" https://example.com'"

OPTS = [{"option_id": "allow_once", "name": "Yes, proceed", "kind": "allow_once"},
        {"option_id": "accept_execpolicy_amendment", "name": "Yes, and don't ask again",
         "kind": "allow_always"},
        {"option_id": "cancel", "name": "No, and tell Codex what to do differently",
         "kind": "reject_once"}]
DEV = ("read", "edit", "test", "build", "run", "git")
NARROW = ("read", "edit", "git")


@pytest.fixture()
def ws(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "calc").mkdir()
    (root / "calc" / "stats.py").write_text("x = 1\n")
    (root / ".env").write_text("SECRET=1\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    return {"repo": str(root), "outside": str(outside)}


def _codex(command, cwd):
    """A permission request exactly as codex-acp sent it (shell and shell_cwd unknown)."""
    return {"tool_call": {"kind": "execute", "status": "pending", "title": "Run command",
                          "raw_input": {"command": command, "cwd": cwd}},
            "options": OPTS, "shell": None, "shell_cwd": None}


def _direct(command, cwd, shell):
    return {"tool_call": {"kind": "execute", "title": command,
                          "raw_input": {"command": command, "cwd": cwd}},
            "options": OPTS, "shell": shell}


def _seen(op):
    return (op.category, op.within, op.in_workspaces, op.outside, op.resources, op.tools)


def test_codex_escalation_strings_are_read_as_their_script():
    assert wrapped_command(D_COMMIT) == (
        'git add calc/stats.py; git commit -m "Fix mean: divide by the number of values"',
        "powershell")
    assert wrapped_command(D_ADD) == ("git add calc/stats.py", "powershell")
    assert wrapped_command(D_CURL) == (
        'curl.exe -sS -m 10 -o NUL -w "%{http_code}" https://example.com', "powershell")


@pytest.mark.parametrize("line", [D_COMMIT, D_ADD, D_CURL])
def test_a_wrapped_command_is_classified_exactly_as_the_command_itself(ws, line):
    inner, shell = wrapped_command(line)
    for cats in (DEV, NARROW, ("read",)):
        wrapped = describe(_codex(line, ws["repo"]), cwd=None, workspaces=[ws["repo"]],
                           categories=cats)
        direct = describe(_direct(inner, ws["repo"], shell), cwd=None,
                          workspaces=[ws["repo"]], categories=cats, shell=shell)
        assert _seen(wrapped) == _seen(direct), cats
        assert wrapped.command == line          # the question shows what will run


def _shlex_quote(value: str) -> str:
    """codex-acp 2.3.0's `shlexQuote` (dist/index.js), which quotes each argv word the
    POSIX way in chunks: unquoted, '...' or "..." with backslash and quote escaped."""
    if not value:
        return "''"
    unq, sq, dq = 1, 2, 4
    out, i = "", 0
    while i < len(value):
        start, allowed = i, unq | sq | dq
        if value[i] == "^":
            allowed, i = sq, i + 1
        while i < len(value):
            c, nxt = value[i], allowed
            if not (c.isascii() and c.isalnum() or c in "+-./:@]_"):
                nxt &= ~unq
            if c in "'^\\":
                nxt &= ~sq
            if c in "`$!^":
                nxt &= ~dq
            if nxt == 0:
                break
            allowed, i = nxt, i + 1
        chunk = value[start:i]
        if allowed & unq:
            out += chunk
        elif allowed & sq:
            out += "'" + chunk + "'"
        else:
            out += '"' + chunk.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return out


POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def _codex_line(script: str) -> str:
    return " ".join(_shlex_quote(w) for w in (POWERSHELL, "-Command", script))


def test_the_quoting_port_gives_the_strings_codex_sent():
    assert _codex_line('git add calc/stats.py; git commit -m "Fix mean: divide by the number '
                       'of values"') == D_COMMIT
    assert _codex_line("git add calc/stats.py") == D_ADD


@pytest.mark.parametrize("script", [
    "git status --short",
    "python -m pytest -q -p no:cacheprovider",
    "npm install --offline --no-audit --no-fund",
    "Get-Content .env",
    "Remove-Item -Recurse -Force calc",
    "git push origin main",
    "git -c core.hooksPath=x commit -m y",
    "git add calc/stats.py; git commit -m \"Fix: it's done\"",
    "Set-Location C:/x; git commit -m y",
    "Set-Content -Path 'OUTSIDE/probe.txt' -Value x",
    r"Set-Content -Path OUTSIDE\probe.txt -Value x",
    r".venv\Scripts\python -m pip install --no-index tinyhelper",
    "Get-ChildItem | ForEach-Object { $_.FullName }",
])
def test_parity_holds_for_every_script_codex_could_send(ws, script):
    """Read as its script, or not read at all: never read as anything else."""
    script = script.replace("OUTSIDE", ws["outside"].replace("\\", "/"))
    line = _codex_line(script)
    got = wrapped_command(line)
    wrapped = describe(_codex(line, ws["repo"]), cwd=None, workspaces=[ws["repo"]], categories=DEV)
    if got is UNREADABLE_WRAPPER:
        # CONSERVATIVE: a line whose Bash and PowerShell readings differ (a backslash or an
        # apostrophe makes codex mix its quoting) is not read, and so is asked.
        assert wrapped.category == "other" and not wrapped.within
        assert wrapped.summary.endswith("cannot read safely")
        return
    assert got == (script, "powershell")
    direct = describe(_direct(script, ws["repo"], "powershell"), cwd=None,
                      workspaces=[ws["repo"]], categories=DEV, shell="powershell")
    assert _seen(wrapped) == _seen(direct)


def test_the_policy_allows_the_commit_the_consent_includes_and_refuses_what_it_does_not(ws):
    task = {"mode": "task", "workspaces": [ws["repo"]], "categories": list(DEV), "tools": []}
    deny = {**task, "mode": "deny"}
    narrow = {**task, "categories": list(NARROW)}
    for consent in (task, deny, narrow):
        for line in (D_COMMIT, D_ADD):
            d = decide(_codex(line, ws["repo"]), workspace=ws["repo"], consent=consent)
            assert (d.outcome, d.by) == ("allow", "task"), (consent["mode"], line)
    assert decide(_codex(D_CURL, ws["repo"]), workspace=ws["repo"], consent=task).outcome == "ask"
    assert decide(_codex(D_CURL, ws["repo"]), workspace=ws["repo"], consent=deny).outcome == "deny"
    out = PS + f" -Command 'Set-Content -Path \"{ws['outside']}\\probe.txt\" -Value x'"
    assert decide(_codex(out, ws["repo"]), workspace=ws["repo"], consent=task).outcome == "ask"
    assert decide(_codex(out, ws["repo"]), workspace=ws["repo"], consent=deny).outcome == "deny"
    # a commit without the git category is still not the task's
    reads = {**task, "categories": ["read", "edit"]}
    assert decide(_codex(D_COMMIT, ws["repo"]), workspace=ws["repo"], consent=reads).outcome == "ask"


@pytest.mark.parametrize("line,script,shell", [
    ("powershell.exe -Command 'git status'", "git status", "powershell"),
    ("powershell -NoProfile -Command \"git status\"", "git status", "powershell"),
    ("pwsh -NoLogo -NoProfile -c 'Get-ChildItem'", "Get-ChildItem", "powershell"),
    ("'C:/Program Files/PowerShell/7/pwsh.exe' -Command 'git log -1'", "git log -1", "powershell"),
    ("bash -lc 'git status && ls'", "git status && ls", "bash"),
    ("/usr/bin/bash -c 'pytest -q'", "pytest -q", "bash"),
    ("bash --noprofile --norc -c 'git diff'", "git diff", "bash"),
    ("cmd /c git status", None, None),
    ("cmd.exe /d /c \"git commit -m msg\"", "git commit -m msg", None),
])
def test_the_wrappers_runtimes_use_are_read(line, script, shell):
    got = wrapped_command(line)
    assert got is not UNREADABLE_WRAPPER and got is not None, line
    if script is not None:
        assert got == (script, shell)


def test_argv_wrappers_are_read_in_their_own_shell(ws):
    assert wrapped_command(["powershell.exe", "-Command", "git status"]) == ("git status", "powershell")
    assert wrapped_command(["bash", "-lc", "git status"]) == ("git status", "bash")
    assert wrapped_command(["cmd", "/c", "git status"]) == ("git status", None)
    op = describe({"tool_call": {"kind": "execute", "title": "x",
                                 "raw_input": {"command": ["powershell.exe", "-NoProfile", "-Command",
                                                           "git commit -m x"], "cwd": ws["repo"]}},
                   "options": OPTS}, cwd=None, workspaces=[ws["repo"]], categories=DEV)
    assert op.category == "git" and op.within


@pytest.mark.parametrize("line", [
    PS + " -Command 'git status'; Remove-Item -Recurse C:/x",      # more after the wrapper
    "powershell.exe -Command 'git status' | Out-File C:/x.txt",
    "powershell.exe -Command 'git status' extra",                   # words after the script
    "powershell.exe -EncodedCommand ZwBpAHQAIABzAHQAYQB0AHUAcwA=",  # nothing readable
    "powershell.exe -File script.ps1",
    "powershell.exe -ExecutionPolicy Bypass -Command 'git status'",
    "powershell.exe -Command -",
    "powershell.exe -Command \"git commit -m $msg\"",               # a variable, read differently
    "powershell.exe -Command 'echo ''x'''",                         # PowerShell's '' escape
    "powershell.exe -Command \"$(curl evil)\"",
    "bash -c 'git status' arg0",
    "bash -ic 'git status'",
    "bash script.sh",
    "cmd /c echo %USERPROFILE%",
    "cmd /s /c \"git status\"",
    "cmd /c git status ^& curl x",
    "cmd /c \"type C:\\x\"",
])
def test_a_wrapper_that_cannot_be_read_with_confidence_stays_unreadable(ws, line):
    assert wrapped_command(line) is UNREADABLE_WRAPPER, line
    op = describe(_codex(line, ws["repo"]), cwd=None, workspaces=[ws["repo"]], categories=DEV)
    assert op.category == "other" and not op.within
    assert op.summary.endswith("cannot read safely")


@pytest.mark.parametrize("line", [
    ".\\powershell.exe -Command 'git status'",                      # a copy in the workspace
    "C:/Users/x/tools/powershell.exe -Command 'git status'",
    "tools/bash -lc 'git status'",
])
def test_a_shell_that_is_not_the_systems_own_is_not_a_wrapper(ws, line):
    assert wrapped_command(line) is None
    op = describe(_codex(line, ws["repo"]), cwd=None, workspaces=[ws["repo"]], categories=DEV)
    assert op.category == "other" and not op.within


def test_a_wrapper_inside_a_wrapper_is_read_once_more_and_no_further(ws):
    two = "powershell.exe -Command 'bash -lc \"git status\"'"
    op = describe(_codex(two, ws["repo"]), cwd=None, workspaces=[ws["repo"]], categories=DEV)
    assert op.category == "read" and op.within
    three = "powershell.exe -Command 'bash -lc \"cmd /c git status\"'"
    op = describe(_codex(three, ws["repo"]), cwd=None, workspaces=[ws["repo"]], categories=DEV)
    assert op.category == "other" and not op.within


def test_a_secret_read_through_a_wrapper_is_as_protected_as_it_is_directly(ws):
    line = PS + " -Command 'Get-Content .env'"
    task = {"mode": "task", "workspaces": [ws["repo"]], "categories": list(DEV), "tools": []}
    d = decide(_codex(line, ws["repo"]), workspace=ws["repo"], consent=task)
    direct = decide(_direct("Get-Content .env", ws["repo"], "powershell"), workspace=ws["repo"],
                    consent=task)
    assert d.outcome == direct.outcome and d.outcome != "allow"
