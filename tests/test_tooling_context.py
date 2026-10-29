"""The effective tooling context (docs/tooling-context.md).

What a run is told it can reach: declared, observed or not reported, never
filled from the operating system; Discipline tools placed in this run's shell;
and nothing in it permits anything.
"""

from __future__ import annotations

from types import SimpleNamespace

from mentis.execution.tooling import NOT_REPORTED, effective, for_run, render
from tests._loop import a_conversation, say, world  # noqa: F401

DISC = {"name": "CLI and MARS development",
        "tools": ["git", "mentis bridge (tools/mcp_bridge.py)", "pytest (targeted)", "an unheard-of tool"]}
CLAUDE = {"backend": "claude", "version": "0.97.0",
          "shell": {"name": None, "how": "not-reported", "per_call": True, "why": "chosen per call"},
          "tools": None, "tools_how": "not-reported", "tools_why_not": "not listed over ACP",
          "native_edit": {"value": True, "how": "declared"}, "command_cwd": "not-reported",
          "sandbox": {"permissions": "forwarded", "enforced_by": "client"}}
LOCAL_RO = {"backend": "local", "shell": {"name": "powershell", "how": "declared"},
            "tools": [{"name": "workspace_read", "kind": "read"}], "tools_how": "declared",
            "native_edit": {"value": False, "how": "declared"}, "command_cwd": "not-reported"}
LOCAL_FULL = {"backend": "local", "shell": {"name": "powershell", "how": "declared"},
              "tools": [{"name": "terminal", "kind": "execute"}, {"name": "file_editor", "kind": "edit"}],
              "tools_how": "declared", "native_edit": {"value": True, "how": "declared"}}
CODEX = {"backend": "codex", "shell": {"name": None, "how": "not-reported"},
         "command_cwd": "per-call", "tools_how": "not-reported"}


def _eff(meta, ws="C:\\repo", **kw):
    return effective(meta, backend=(meta or {}).get("backend", "x"), workspace=ws,
                     mcp_servers=[{"name": "mentis"}], **kw)


def test_nothing_is_filled_in_that_mars_did_not_report():
    e = _eff(None)
    assert e["shell"]["how"] == NOT_REPORTED and e["shell"]["name"] is None
    assert e["tools"]["how"] == NOT_REPORTED and e["native_edit"]["how"] == NOT_REPORTED
    assert e["model"]["how"] == NOT_REPORTED and e["reported_by_mars"] is False
    assert "this MARS does not report its tooling" in e["shell"]["why"]
    # a shell that is not DECLARED is not taken, whatever name it carries
    e = _eff({"shell": {"name": "powershell", "how": "observed"}})
    assert e["shell"]["name"] is None


def test_a_per_call_shell_is_written_both_ways_and_said_so():
    text = render(_eff(CLAUDE), [DISC])
    assert "not reported before you run a command" in text
    assert "Set-Location 'C:\\repo'; git status" in text and "cd '/c/repo' && git status" in text
    assert "your shell's current directory is not reported" in text
    assert "File editing: your own edit tool." in text


def test_a_declared_shell_is_written_once():
    text = render(_eff(LOCAL_FULL), [DISC])
    assert "Shell: PowerShell (declared)" in text
    assert "Set-Location 'C:\\repo'; git status" in text and "cd '/c/repo'" not in text
    assert "terminal (execute), file_editor (edit)" in text


def test_a_discipline_cannot_manufacture_a_tool():
    text = render(_eff(LOCAL_RO), [DISC])
    assert "git: not available in this run" in text
    assert "pytest (targeted): not available in this run" in text
    assert "File editing: none: you cannot change files." in text
    # a tool the Discipline names that nothing reports is said to be unknown
    assert "an unheard-of tool: named by the Discipline; whether it is reachable here is not reported" in render(_eff(CLAUDE), [DISC])


def test_nothing_in_it_permits_anything():
    text = render(_eff(CLAUDE, consent={"mode": "task", "workspaces": ["C:\\repo"]}), [DISC])
    assert text.startswith("Your tooling for this run") and "It permits nothing" in text
    assert "a tool named here or in a Discipline is not permission" in text


def test_codex_commands_carry_their_own_directory():
    text = render(_eff(CODEX), [DISC])
    assert "your shell's current directory is not reported" not in text


def test_the_mentis_bridge_is_named_only_when_attached():
    e = effective(CLAUDE, backend="claude", workspace="C:\\repo", mcp_servers=[])
    assert "mentis bridge (tools/mcp_bridge.py): not attached to this run" in render(e, [DISC])


def test_a_venv_in_the_workspace_is_used_for_tests(tmp_path):
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_text("")
    text = render(_eff(LOCAL_FULL, ws=str(tmp_path)), [DISC])
    assert f"& '{tmp_path / '.venv' / 'Scripts' / 'python.exe'}' -m pytest -q" in text


def test_for_run_reads_consent_and_delivered_disciplines(world):
    """The run's own consent and its delivered Disciplines, and no other run's."""
    cv = world["cv"]
    cid = a_conversation(world, "Tooling")
    turn = say(world, cid, "work")["turn"]
    given = C.consent_value({"mode": "task", "workspaces": [str(world.get("tmp", "C:\\"))]}) \
        if False else None
    exp = cv.expect(turn, of=world["steward"], kind="result", by=world["who"]["@brian"])
    run = cv.record_act(actor=world["steward"], act="execution-started", conversation=cid,
                        turn=turn, execution="inst-t", runtime="claude", caused_by=exp,
                        because="test", detail={"workspace": "C:\\repo"})
    inst = SimpleNamespace(runtime="claude", workspace="C:\\repo", requested_model="sonnet")
    told, eff = for_run(cv, run, inst, delivered=["ent-not-a-discipline"],
                        mcp_servers=[{"name": "mentis"}])(CLAUDE)
    assert eff["consent"] == {"mode": "ask"} and eff["disciplines"] == []
    assert eff["model"] == {"id": "sonnet", "how": "declared", "by": "mentis"}
    assert "How the Discipline" not in told
    # two runs, two runtimes: each is told only its own tooling
    _, other = for_run(cv, run, SimpleNamespace(runtime="local", workspace="C:\\other",
                                                requested_model=None), (), ())(LOCAL_RO)
    assert other["cwd"]["path"] == "C:\\other" and eff["cwd"]["path"] == "C:\\repo"
    assert other["shell"]["name"] == "powershell" and eff["shell"]["name"] is None
