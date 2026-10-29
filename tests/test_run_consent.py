"""Run consent: operations described, consent inherited, requests answered.

`mentis.operations` (what a permission request would do, and whether it is
inside the task), `mentis.operational.consent` (the owner's consent on a
request, carried down and only narrowed), and `mentis.web.permissions`
(who answers: the grant, the consent, or the owner with a readable
question). docs/run-consent.md is the contract.
"""

from __future__ import annotations

import os
import threading
import time

import pytest

from mentis.operations import describe, read_only
from mentis.operational import consent as C
from mentis.web.permissions import make_policy, mars_consent
import json
import urllib.request

from tests._loop import a_conversation, say, world  # noqa: F401


def _call(world, path, payload=None):
    req = urllib.request.Request(
        world["base"] + path, method="POST" if payload is not None else "GET",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def post(world, path, payload):
    return _call(world, path, payload)


def get(world, path):
    return _call(world, path)

OPTS = [{"option_id": "once", "kind": "allow_once", "name": "Yes"},
        {"option_id": "always", "kind": "allow_always", "name": "Yes, and don't ask again"},
        {"option_id": "no", "kind": "reject_once", "name": "No"}]


def _shell(command, **raw):
    return {"tool_call": {"kind": "execute", "title": command,
                          "raw_input": {"command": command, **raw}},
            "options": OPTS}


@pytest.fixture()
def ws(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("x = 1\n")
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    return {"repo": str(root), "other": str(other), "tmp": str(tmp_path)}


# ---------------------------------------------------------------------------
# operations


@pytest.mark.parametrize("command,category,within", [
    ("git status", "read", True),
    ("cd src && grep -n 'def ' app.py | head -20", "read", True),
    ("ls /c/Work 2>/dev/null; git log --oneline -5", "read", True),
    ("for d in a b; do echo $d; done", "read", True),
    ("python -m pytest tests/test_app.py -q", "test", True),
    ("npm run build", "build", True),
    ("npm test", "test", True),
    ("python tools/check.py --fast", "run", True),
    ("sed -i 's/x/y/' src/app.py", "edit", True),
    ("echo hi > src/out.txt", "edit", True),
    ("git add -A && git commit -m 'wip'", "git", True),
    ("git -c user.name=v -c user.email=v@x commit -qm wip", "git", True),
    ("git -c core.sshCommand=evil fetch", "other", False),
    ("& $tool --version", "other", False),
    ("git push origin main", "git-remote", False),
    ("git fetch -q", "git-remote", False),
    ("curl https://example.com", "network", False),
    ("pip install requests", "install", False),
    ("rm -rf build", "delete", False),
    ("python -c 'import os; os.remove(\"x\")'", "other", False),
    ("bash -c 'rm x'", "other", False),
    ("echo $(whoami)", "other", False),
    ("sqlite3 corpus.db .tables", "other", False),
    ("find . -name '*.pyc' -delete", "other", False),
])
def test_commands_are_described_by_what_they_do(ws, command, category, within):
    op = describe(_shell(command), cwd=ws["repo"], workspaces=[ws["repo"]])
    assert op.category == category, (command, op.parts, op.outside)
    assert op.within is within, (command, op.outside)
    assert op.command == command and op.summary and command not in op.summary


@pytest.mark.parametrize("command,category,within", [
    ('git add calc; if ($?) { git commit -m "x" }; git log -2', "git", True),
    ("$out = git status; $LASTEXITCODE -eq 0", "read", True),
    ("$f = rm -rf build", "delete", False),
])
def test_powershell_expressions_are_read_in_powershell(ws, command, category, within):
    """PowerShell syntax, read as PowerShell. Unreported, the Bash reading of
    a `$x` in program position (it runs what `$x` holds) keeps it asked."""
    op = describe(_shell(command), cwd=ws["repo"], workspaces=[ws["repo"]], shell="powershell")
    assert op.category == category, (command, op.parts, op.outside)
    assert op.within is within, (command, op.outside)
    assert describe(_shell(command), cwd=ws["repo"], workspaces=[ws["repo"]]).category == "other"


def test_declared_bash_syntax_is_read_as_bash(ws):
    command = "find . -path ./node_modules -prune -o -type f \\( -name '*.py' \\) -print"
    op = describe(_shell(command), cwd=ws["repo"], workspaces=[ws["repo"]], shell="bash")
    assert op.category == "read" and op.within


def test_powershell_edits_name_their_file(ws):
    op = describe(_shell('Set-Content -Path src\\app.py -Value "x = 2`n"'),
                  cwd=ws["repo"], workspaces=[ws["repo"]], shell="powershell")
    assert op.category == "edit" and op.within
    assert op.resources == [os.path.join(ws["repo"], "src", "app.py")]
    assert op.summary.startswith("Write src")


def test_shell_is_only_taken_from_verified_facts(ws):
    ambiguous = describe(_shell(r"echo harmless \; rm -rf build"),
                         cwd=ws["repo"], workspaces=[ws["repo"]])
    assert ambiguous.category == "other" and not ambiguous.within
    assert "cannot read safely" in ambiguous.summary

    agreed = describe(_shell("git status"), cwd=ws["repo"], workspaces=[ws["repo"]])
    assert agreed.category == "read" and agreed.within
    assert agreed.tool.startswith("shell:")

    observed = _shell('Set-Content -Path src\\app.py -Value "x = 2`n"')
    observed["tool_call"]["field_meta"] = {
        "mars/tool": {"name": "PowerShell", "shell": "powershell", "how": "observed"}}
    assert describe(observed, cwd=ws["repo"], workspaces=[ws["repo"]]).within

    claude = {**_shell('Set-Content -Path src\\app.py -Value "x = 2`n"'),
              "claudeCode": {"toolName": "PowerShell"}}
    assert describe(claude, cwd=ws["repo"], workspaces=[ws["repo"]]).within


def test_powershell_commit_message_is_routine_git(ws):
    command = ('git add a b; git -c user.name="X" -c user.email="x@y" commit '
               '-m "Add sub`n`nCo-Authored-By: Claude <noreply@anthropic.com>"; '
               'git log --oneline -1')
    op = describe(_shell(command), cwd=ws["repo"], workspaces=[ws["repo"]],
                  shell="powershell")
    assert op.category == "git" and op.within, op.outside


def test_unreported_and_command_set_working_directories(ws):
    missing = describe({**_shell("python -m pytest -q"), "shell_cwd": None,
                        "shell": "powershell"},
                       cwd=ws["repo"], workspaces=[ws["repo"]])
    assert missing.category == "test" and not missing.within
    assert "where it runs is not reported" in " ".join(missing.outside)
    assert ws["repo"] not in missing.summary
    assert "current directory (not reported)" in missing.summary

    located = describe({**_shell(f"Set-Location {ws['repo']}; python -m pytest -q"),
                        "shell_cwd": None, "shell": "powershell"},
                       cwd=ws["other"], workspaces=[ws["repo"]])
    assert located.category == "test" and located.within, located.outside
    assert ws["repo"] in located.summary

    git_at = describe({**_shell(f"git -C {ws['repo']} status"), "shell_cwd": None},
                      cwd=ws["other"], workspaces=[ws["repo"]])
    assert git_at.category == "read" and git_at.within, git_at.outside

    absolute_tests = describe(
        {**_shell(f"python -m pytest -q {ws['repo']}\\tests"), "shell_cwd": None},
        cwd=ws["other"], workspaces=[ws["repo"]])
    assert absolute_tests.category == "test" and absolute_tests.within


def test_request_shell_cwd_is_used_in_summary(ws):
    op = describe({**_shell("python -m pytest -q"), "shell_cwd": ws["repo"]},
                  cwd=ws["other"], workspaces=[ws["repo"]])
    assert op.within and ws["repo"] in op.summary


def test_the_boundary_is_said_in_words(ws, monkeypatch):
    brain = os.path.join(ws["tmp"], "brains")
    os.makedirs(brain)
    monkeypatch.setenv("MENTIS_PROTECTED_PATHS", brain)
    inside = [ws["repo"]]
    out = describe(_shell(f"echo x > {ws['other']}\\notes.txt"), cwd=ws["repo"],
                   workspaces=inside)
    assert not out.within and "outside the approved workspaces" in out.outside[0]
    # outside only because of where it works: the repository is offered
    assert out.offer_workspace == ws["other"]
    hook = describe(_shell("echo x > .git/hooks/pre-commit"), cwd=ws["repo"],
                    workspaces=inside)
    assert not hook.within and "run code or change permissions" in hook.outside[0]
    secret = describe(_shell(f"cat {brain}\\corpus.db"), cwd=ws["repo"], workspaces=inside)
    assert not secret.within and "protected" in secret.outside[0]
    env = describe(_shell("cat .env"), cwd=ws["repo"], workspaces=inside)
    assert not env.within
    unknown = describe(_shell("cp a.py $TARGET"), cwd=ws["repo"], workspaces=inside)
    assert not unknown.within and "variable" in " ".join(unknown.outside)
    # a category the owner did not permit
    allowed = describe(_shell("git push"), cwd=ws["repo"], workspaces=inside,
                       categories=("read", "git", "git-remote"))
    assert allowed.within


def test_codex_argv_and_its_own_cwd(ws):
    req = {"tool_call": {"kind": "execute", "title": "x",
                         "raw_input": {"command": ["powershell.exe", "-Command",
                                                   "Get-Content src\\app.py"],
                                       "cwd": ws["repo"]}}, "options": OPTS}
    op = describe(req, cwd=None, workspaces=[ws["repo"]])
    assert op.category == "read" and op.within


def test_the_runs_own_mentis_tools_are_its_grants():
    op = describe({"tool_call": {"kind": "other", "title": "mcp__mentis__find"},
                   "options": OPTS}, cwd=None, workspaces=[])
    assert op.category == "mentis" and op.within


# ---------------------------------------------------------------------------
# consent on the record


def _request(world, cid, *, by=None, of=None, caused_by=None, consent=None, repo=None):
    cv = world["cv"]
    turn = say(world, cid, "work on the repository")["turn"]
    detail = {**({"consent": consent} if consent else {}),
              **({"repository": {"path": repo}} if repo else {})}
    return turn, cv.expect(turn, of=of or world["steward"], kind="result",
                           by=by or world["who"]["@brian"], caused_by=caused_by,
                           detail=detail or None)


def _run(world, cid, turn, exp, workspace):
    return world["cv"].record_act(actor=world["steward"], act="execution-started",
                                  conversation=cid, turn=turn, execution="inst-c",
                                  runtime="claude", caused_by=exp, because="test",
                                  detail={"workspace": workspace})


def test_consent_is_the_owners_and_children_only_narrow(world, ws):
    cv = world["cv"]
    cid = a_conversation(world, "Consent")
    given = C.consent_value({"mode": "task", "workspaces": [ws["repo"]]})
    turn, origin = _request(world, cid, consent=given)
    assert C.of_request(cv, origin)["mode"] == "task"
    # a child the carrier delegates inherits, and cannot widen
    wider = {"mode": "task", "workspaces": [ws["other"], ws["repo"]],
             "categories": ["read", "network"]}
    _, child = _request(world, cid, by=world["steward"], caused_by=origin, consent=wider)
    got = C.of_request(cv, child)
    assert got["mode"] == "task" and got["workspaces"] == [ws["repo"]]
    assert got["categories"] == ["read"] and got["source"] == "narrowed"
    # an agent cannot give itself consent
    _, alone = _request(world, cid, by=world["steward"], consent=given)
    assert C.of_request(cv, alone)["mode"] == "ask"
    # the child's run workspace counts only inside what it inherited
    run = _run(world, cid, turn, child, ws["other"])
    assert ws["other"] not in C.of_run(cv, run)["workspaces"]


def test_refused_consent_says_why(ws, tmp_path, monkeypatch):
    monkeypatch.setenv("MENTIS_PROTECTED_PATHS", ws["other"])
    for bad in ({"mode": "always"}, {"mode": "task", "workspaces": ["relative"]},
                {"mode": "task", "workspaces": [ws["other"]]},
                {"mode": "task", "categories": ["everything"]}):
        with pytest.raises(ValueError):
            C.consent_value(bad)
    assert C.consent_value(None) is None and C.consent_value("ask") is None


# ---------------------------------------------------------------------------
# answering


def _policy_world(world, ws, consent=None):
    cid = a_conversation(world, "Policy")
    turn, exp = _request(world, cid, consent=consent)
    run = _run(world, cid, turn, exp, ws["repo"])
    return cid, turn, exp, run, make_policy(world["state"])


def _answers(world, run):
    return [(a["by"], a["answer"]) for a in C.answered(world["cv"], run)]


def test_routine_work_proceeds_under_task_consent(world, ws):
    given = C.consent_value({"mode": "task", "workspaces": [ws["repo"]]})
    cid, turn, exp, run, policy = _policy_world(world, ws, given)
    obs: dict = {}
    for command in ("git status", "python -m pytest -q", "sed -i 's/1/2/' src/app.py",
                    "git add -A && git commit -m x", "npm run build"):
        assert policy(run, "inst-c", _shell(command), obs) == "once", command
    # a runtime's persistent "always" option is never chosen, and nothing was asked
    assert not obs.get("permissions")
    by = _answers(world, run)
    assert by[0] == ("grant", "allowed") and ("task", "allowed") in by
    # what MARS is told: the mode and the workspaces beyond its own cwd
    assert mars_consent(world["cv"], run, ws["repo"]) == {"mode": "task", "workspaces": []}


def test_policy_uses_reported_cwd_and_absolute_edits_need_none(world, ws):
    given = C.consent_value({"mode": "task", "workspaces": [ws["repo"]]})
    cid, turn, exp, run, policy = _policy_world(world, ws, given)
    reported = {**_shell("python -m pytest -q"), "shell_cwd": ws["repo"],
                "shell": "powershell"}
    assert policy(run, "inst-c", reported, {}) == "once"

    absolute = {**_shell(f"Set-Content -Path {ws['repo']}\\absolute.txt -Value x"),
                "shell_cwd": None, "shell": "powershell"}
    assert policy(run, "inst-c", absolute, {}) == "once"

    missing = {**_shell("python -m pytest -q"), "shell_cwd": None,
               "shell": "powershell"}
    op = describe(missing, cwd=ws["repo"], workspaces=[ws["repo"]])
    assert not op.within


def test_deny_never_waits(world, ws):
    given = C.consent_value({"mode": "deny", "workspaces": [ws["repo"]]})
    cid, turn, exp, run, policy = _policy_world(world, ws, given)
    t0 = time.time()
    assert policy(run, "inst-c", _shell("git push origin main"), {}) is None
    assert time.time() - t0 < 5
    assert _answers(world, run) == [("deny", "refused")]
    # routine work inside the task still proceeds, without asking
    assert policy(run, "inst-c", _shell("git status"), {}) == "once"
    assert policy(run, "inst-c", _shell("python -m pytest -q"), {}) == "once"
    assert _answers(world, run)[-1] == ("task", "allowed")


def _answer_form(world, cid, obs, label, timeout=20):
    """Answer the first permission form the policy raised, as Fluid does."""
    cv = world["cv"]
    deadline = time.time() + timeout
    while time.time() < deadline and not obs.get("permissions"):
        time.sleep(0.05)
    form = next(iter(obs["permissions"]))
    drawn = cv.decision_form(form)
    q = drawn["questions"][0]
    assert obs["permissions"][form]["decision"] == q["expectation"]
    i = [o["label"] for o in q["options"]].index(label)
    post(world, f"/api/conversations/{cid}/turns",
         {"author": world["who"]["@brian"], "text": label, "action": "record-only",
          "replies_to": drawn["post"], "addressed_to": [],
          "chose": {"expectation": q["expectation"], "option": i, "label": label}})
    return drawn


def test_out_of_scope_is_asked_in_words_and_an_answer_holds(world, ws):
    """No consent: the owner is asked, readably, and 'Allow within this
    task, adding <dir>' makes later routine work there proceed."""
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    got = {}
    command = f"echo x > {ws['other']}\\notes.txt"
    t = threading.Thread(target=lambda: got.setdefault(
        "a", policy(run, "inst-c", _shell(command, description="Write notes"), obs)))
    t.start()
    label = f"Allow within this task, adding {ws['other']}"
    drawn = _answer_form(world, cid, obs, label)
    t.join(30)
    assert got["a"] == "once"
    q = drawn["questions"][0]
    assert command not in q["question"] and "asks to write" in q["question"]
    assert drawn["operation"]["command"] == command
    assert drawn["operation"]["agent_says"] == "Write notes"
    assert [o["label"] for o in q["options"]][0] == "Allow once"
    assert all(o.get("consequence") for o in q["options"])
    # the answer is consent now: the next routine edit there is not asked
    later = {}
    assert policy(run, "inst-c", _shell(f"echo y > {ws['other']}\\more.txt"), later) == "once"
    assert not later.get("permissions")
    now = C.of_run(world["cv"], run)
    assert now["mode"] == "task" and ws["other"] in now["workspaces"]
    assert ("owner", "allowed") in _answers(world, run)


def test_a_tool_allowed_for_the_run_stays_inside_the_workspace(world, ws):
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    got = {}
    t = threading.Thread(target=lambda: got.setdefault(
        "a", policy(run, "inst-c", _shell("sqlite3 data.db .tables"), obs)))
    t.start()
    _answer_form(world, cid, obs, "Allow sqlite3 for this run")
    t.join(30)
    assert got["a"] == "once" and C.of_run(world["cv"], run)["tools"] == ["sqlite3"]
    assert policy(run, "inst-c", _shell("sqlite3 other.db .schema"), {}) == "once"
    # the same tool outside the workspace is still asked; only once/deny offered
    obs2: dict = {}
    got2 = {}
    t2 = threading.Thread(target=lambda: got2.setdefault(
        "a", policy(run, "inst-c", _shell(f"cd {ws['other']} && sqlite3 x.db .tables"), obs2)))
    t2.start()
    drawn = _answer_form(world, cid, obs2, "Deny")
    t2.join(30)
    assert got2["a"] == "no"
    labels = [o["label"] for o in drawn["questions"][0]["options"]]
    assert "Allow sqlite3 for this run" not in labels and labels[-1] == "Deny"


def test_the_owner_changes_a_runs_consent(world, ws):
    cid, turn, exp, run, policy = _policy_world(world, ws)
    got = post(world, f"/api/runs/{run}/consent", {"mode": "task"})
    assert got["consent"]["mode"] == "task" and got["consent"]["source"] == "owner-changed"
    got = post(world, f"/api/runs/{run}/consent", {"allow_tool": "sqlite3"})
    assert got["consent"]["tools"] == ["sqlite3"]
    got = post(world, f"/api/runs/{run}/consent", {"revoke_tool": "sqlite3"})
    assert got["consent"]["tools"] == []
    assert policy(run, "inst-c", _shell("python -m pytest"), {}) == "once"
    read = get(world, f"/api/runs/{run}/consent")
    assert read["operations"][-1]["by"] == "task"
    rows = {r["id"]: r for r in get(world, f"/fluid/api/runs?ids={run}")["runs"]}
    assert rows[run]["consent"]["mode"] == "task"


def test_posting_records_consent_and_refuses_a_bad_one(world, ws):
    cid = a_conversation(world, "Posting")
    care = world["steward"]
    ok = say(world, cid, "build it", addressed_to=[care],
             dispatch=[{"participant": care,
                        "consent": {"mode": "task", "workspaces": [ws["repo"]]}}])
    exp = next(a for a in world["cv"]._c.operational(turn=ok["turn"])
               if a["act"] == "expectation-recorded")
    assert exp["detail"]["consent"]["workspaces"] == [ws["repo"]]
    import urllib.error
    try:
        bad = say(world, cid, "build it", addressed_to=[care],
                  dispatch=[{"participant": care, "consent": {"mode": "forever"}}])
    except urllib.error.HTTPError as exc:
        bad = json.loads(exc.read())
    assert "consent mode" in bad.get("error", ""), bad


@pytest.mark.parametrize("command,within", [
    ("Get-Content README.md", False),          # relative: where it reads is not reported
    ("ls", False),                             # the shell's own directory
    (r"Get-Content C:\repo\README.md", True),  # absolute: nothing depends on the shell
    (r"Set-Location C:\repo; ls", True),       # the command sets it itself
])
def test_a_read_needs_a_verified_place(command, within):
    req = {"tool_call": {"kind": "execute", "title": command, "raw_input": {"command": command},
                         "field_meta": {"mars/tool": {"name": "PowerShell", "shell": "powershell"}}},
           "shell_cwd": None}
    op = describe(req, cwd=r"C:\repo", workspaces=[r"C:\repo"], run_workspace=r"C:\repo")
    assert op.category == "read" and op.within is within
    from mentis.operations import read_only
    assert read_only(op) is within


@pytest.mark.parametrize("command,where", [
    (r"Set-Location C:\repoA; git status --short; python -m pytest -q", r"C:\repoA"),
])
def test_the_question_names_where_the_command_sets_itself(command, where):
    """Found in the integrated demonstration: the summary named the session's
    starting directory although the command set its own first."""
    req = {"tool_call": {"kind": "execute", "title": command, "raw_input": {"command": command},
                         "field_meta": {"mars/tool": {"name": "PowerShell", "shell": "powershell"}}},
           "shell_cwd": r"C:\server-ws"}
    op = describe(req, cwd=r"C:\server-ws", workspaces=[r"C:\repoA"], run_workspace=r"C:\server-ws")
    assert f"in {where}" in op.summary and "server-ws" not in op.summary


_PS = {"mars/tool": {"name": "PowerShell", "shell": "powershell"}}


def _ps_op(command, meta=_PS):
    tc = {"kind": "execute", "title": command, "raw_input": {"command": command}}
    if meta:
        tc["field_meta"] = meta
    return describe({"tool_call": tc, "shell_cwd": r"C:\repo"}, cwd=r"C:\repo",
                    workspaces=[r"C:\repo"], run_workspace=r"C:\repo")


@pytest.mark.parametrize("command", [
    # asked of the owner by @Reviewer, 2026-10-29: a file read into $c, then a slice printed
    r"Set-Location 'C:\repo'; $c = Get-Content mentis/web/__init__.py; $c[3170..3300] -join " + '"`n"',
    r"$c = Get-Content a.py; $c[1325..1340] -join " + '"`n"' + r"; '----'; $c[4670..4705] -join " + '"`n"',
    r"Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch '\.git\' } | Select-Object -ExpandProperty FullName",
    r"Get-Content notes.txt | ForEach-Object { $_ -replace '(?i)(key)', '$1<redacted>' }",
    r"$x = $c.Count; $x.ToString()",
])
def test_powershell_expressions_only_read(command):
    op = _ps_op(command)
    assert op.category == "read" and op.within, (command, op.summary, op.outside)
    assert "$" not in op.summary


@pytest.mark.parametrize("command", [
    r"$p.Kill()", r"$f.Delete()", r"& $cmd", r". $script", r"$c[0..3] | Invoke-Expression",
    r"[System.IO.File]::Delete('x'); $c[1]", r"$x = Remove-Item -Recurse C:\repo\src",
])
def test_powershell_that_can_invoke_stays_asked(command):
    assert not read_only(_ps_op(command)), command


def test_a_variable_in_program_position_is_not_an_expression_in_bash():
    for command in (r"$CMD -rf", r"$x -eq 0"):
        assert _ps_op(command, {"mars/tool": {"name": "Bash", "shell": "bash"}}).category == "other"
    # shell not reported: the two readings disagree, so it is asked
    assert _ps_op(r"$c[1..3] -join ','", None).category == "other"


def test_a_pure_expression_after_a_set_location_reads_there():
    op = _ps_op(r"Set-Location C:\repoA; git log -1; $PSVersionTable.PSVersion.ToString()")
    assert op.category == "read" and "server-ws" not in op.summary
    assert op.resources == [r"C:\repoA"]
