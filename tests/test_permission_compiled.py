"""WS-A permission enforcement: the pure verdict, compiled runtime rules,
and the write-behind audit (docs/modernization/CONTRACT.md, WS-A;
docs/modernization/permission-replay.md).

  * `decide` gives the verdict the policy gave before it was factored out
    (the reference below is that code, verbatim but for writing nothing).
  * Compiled rules NEVER BROADEN: under every reading of Claude Code's rule
    semantics the replay considers, a request the rules allow is one
    `decide` allows without asking -- whatever pending Workflow change might
    arrive mid-run.
  * Automatic answers are written in order behind the answer; refusals and
    owner answers before it; a flush waits for all of them.
  * `runtime_rules` reach MARS only for runtimes in COMPILED_SCOPE_RUNTIMES.
"""

from __future__ import annotations

import itertools
import os
import threading
import time

import pytest

from mentis.operations import DEFAULT_CATEGORIES, describe, read_only
from mentis.operational import consent as C
from mentis import permission_rules as R
from mentis.web import permissions as P
from mentis.web.permissions import _allow_once, decide, standing_answer
from tests._loop import a_conversation, say, world  # noqa: F401

OPTS = [{"option_id": "once", "kind": "allow_once", "name": "Yes"},
        {"option_id": "no", "kind": "reject_once", "name": "No"}]


# ---------------------------------------------------------------------------
# the reference: the policy's decision before `decide` existed


def _old_verdict(request, workspace, consent, pending):
    cats = (consent["categories"] if consent["mode"] in (C.TASK, C.DENY, C.ALL)
            else list(DEFAULT_CATEGORIES))
    command_cwd = request.get("shell_cwd") if "shell_cwd" in request else workspace
    op = describe(request, cwd=command_cwd, workspaces=consent["workspaces"],
                  categories=cats, run_workspace=workspace, shell=request.get("shell"))
    standing = standing_answer(request, workspace)
    if standing is not None and not read_only(op):
        if pending:
            standing = None
    protected = any("protected location" in o for o in op.outside)
    allow = _allow_once(request)
    if allow is not None and not protected and (
            standing is not None or op.category == "mentis" or read_only(op)):
        return ("allow", "grant")
    if allow is not None and op.category == "research" \
            and (consent.get("research") or {}).get("authorized"):
        return ("allow", "research")
    if allow is not None and consent["mode"] == C.ALL:
        return ("allow", "all")
    if allow is not None and consent["mode"] in (C.TASK, C.DENY) and op.within:
        return ("allow", "task")
    if allow is not None and op.tools and op.in_workspaces and not protected \
            and set(op.tools) <= set(consent["tools"]) \
            and all(c in (*cats, "other") for c in (op.parts or [op.category])):
        return ("allow", "tool")
    if consent["mode"] == C.DENY:
        return ("deny", "deny")
    return ("ask", None)


@pytest.fixture()
def ws(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("x = 1\n")
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    return {"repo": str(root), "other": str(other), "tmp": str(tmp_path)}


def _consent(mode, workspaces, categories=DEFAULT_CATEGORIES, tools=(), research=False):
    return {"mode": mode, "workspaces": list(workspaces), "categories": list(categories),
            "tools": list(tools), "research": {"authorized": research}}


def _file(kind, path, tool):
    return {"tool_call": {"kind": kind, "title": f"{tool} {path}",
                          "locations": [{"path": path}],
                          "_meta": {"claudeCode": {"toolName": tool}}},
            "options": OPTS}


def _shell(command, cwd, shell=None):
    req = {"tool_call": {"kind": "execute", "title": command,
                         "raw_input": {"command": command}},
           "shell_cwd": cwd, "options": OPTS}
    if shell:
        req["shell"] = shell
    return req


def _mcp(name):
    return {"tool_call": {"kind": "other", "title": name,
                          "_meta": {"claudeCode": {"toolName": name}}}, "options": OPTS}


def _paths(ws):
    repo, other = ws["repo"], ws["other"]
    home = os.path.expanduser("~")
    return [os.path.join(repo, "src", "app.py"), os.path.join(repo, "new.txt"),
            os.path.join(repo, ".git", "config"), os.path.join(repo, ".GIT", "hooks", "x"),
            os.path.join(repo, "src", ".claude", "settings.json"),
            os.path.join(repo, ".mcp.json"), os.path.join(repo, ".env"),
            os.path.join(repo, "conf", ".ENV.local"), os.path.join(repo, "k", "server.pem"),
            os.path.join(repo, "id_rsa"), os.path.join(repo, "Credentials.json"),
            os.path.join(other, "a.py"), os.path.join(ws["tmp"], "loose.txt"),
            repo.upper() + os.sep + "SRC" + os.sep + "APP.PY",
            os.path.join(home, ".ssh", "config"),
            os.path.join(os.environ.get("LOCALAPPDATA") or home, "Mentis", "x", "corpus.db"),
            os.path.join(repo, "..", "other", "b.py")]


def _requests(ws):
    out = []
    for p in _paths(ws):
        for tool in ("Read", "Grep", "Glob"):
            out.append((tool, _file("read" if tool == "Read" else "search", p, tool), [p]))
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            out.append((tool, _file("edit", p, tool), [p]))
    for name in ("mcp__mentis__find", "mcp__mentis__delegate", "mcp__other__x"):
        out.append((name, _mcp(name), []))
    for cmd in ("git status", "cat ~/.ssh/id_rsa", "rm -rf src", "python -m pytest -q",
                "curl https://example.com"):
        out.append(("Bash", _shell(cmd, ws["repo"], "bash"), []))
        out.append(("PowerShell", _shell(cmd, ws["repo"], "powershell"), []))
    return out


def _consents(ws):
    repo, other = ws["repo"], ws["other"]
    return [_consent("ask", [repo]), _consent("ask", []),
            _consent("task", [repo]), _consent("task", [repo, other]),
            _consent("task", [repo], categories=("read", "test")),
            _consent("deny", [repo]), _consent("deny", [repo], categories=("read",)),
            _consent("all", [repo]), _consent("ask", [repo], tools=["edit", "write"]),
            _consent("task", [repo], research=True)]


def test_decide_is_the_policy_it_replaced(ws):
    n = 0
    for (_, req, _), consent, pending in itertools.product(
            _requests(ws), _consents(ws), (None, {"id": "opr-change"})):
        got = decide(req, workspace=ws["repo"], consent=consent, pending=pending)
        assert (got.outcome, got.by) == _old_verdict(req, ws["repo"], consent, pending), \
            (req["tool_call"]["title"], consent["mode"], pending)
        n += 1
    assert n > 1000


def test_decide_reads_a_pending_change_only_when_it_matters(ws):
    asked = []

    def pending():
        asked.append(1)
        return {"id": "opr-c"}
    read = decide(_file("read", os.path.join(ws["repo"], "x"), "Read"), workspace=ws["repo"],
                  consent=_consent("ask", [ws["repo"]]), pending=pending)
    assert read.outcome == "allow" and not asked
    edit = decide(_file("edit", os.path.join(ws["repo"], "x"), "Edit"), workspace=ws["repo"],
                  consent=_consent("ask", [ws["repo"]]), pending=pending)
    assert edit.outcome == "ask" and asked and "opr-c" in edit.op.why


# ---------------------------------------------------------------------------
# compiled rules never broaden


SEMANTICS = [(True, True), (False, True), (True, False), (False, False)]


@pytest.mark.parametrize("classes", [{c} for c in R.ALL_CLASSES] + [set(R.COMPILED_CLASSES)])
def test_compiled_rules_never_allow_what_mentis_would_not(ws, classes):
    allowed = 0
    for consent in _consents(ws):
        rules = R.compile_claude(consent, workspace=ws["repo"], classes=classes)
        for tool, req, paths in _requests(ws):
            for ic, cover in SEMANTICS:
                k = R.claude_verdict(rules, tool, paths, ignorecase=ic,
                                     read_rules_cover_search=cover)
                if k != "allow":
                    continue
                allowed += 1
                for pending in (None, {"id": "opr-change"}):
                    m = decide(req, workspace=ws["repo"], consent=consent, pending=pending)
                    assert m.outcome == "allow", (classes, consent["mode"], tool, paths,
                                                  pending, m.op.outside)
    assert allowed, "the class compiled nothing at all"


def test_protected_and_guarded_are_denied_before_any_allow(ws):
    rules = R.compile_claude(_consent("task", [ws["repo"]]), workspace=ws["repo"])
    for p in (os.path.join(ws["repo"], ".git", "config"),
              os.path.join(ws["repo"], "a", ".vscode", "settings.json"),
              os.path.join(ws["repo"], ".env")):
        assert R.claude_verdict(rules, "Edit", [p]) == "deny", p
    assert R.claude_verdict(rules, "Read", [os.path.join(ws["repo"], ".git", "config")]) == "allow"
    assert R.claude_verdict(rules, "Read", [os.path.join(ws["repo"], "x", ".env.prod")]) == "deny"
    assert R.claude_verdict(rules, "Read", [os.path.join(ws["other"], "x.py")]) == "ask"
    assert R.claude_verdict(rules, "Bash", []) == "ask"
    assert R.claude_verdict(rules, "mcp__mentis__find", []) == "allow"
    assert R.claude_verdict(rules, "mcp__mentisx__find", []) == "ask"


def test_edits_are_not_compiled_where_they_rest_on_the_standing_allowance(ws):
    """Under `ask` an edit is allowed by the run's own allowance, which a
    carrier's Workflow change withdraws mid-run: no Edit rule is handed out."""
    rules = R.compile_claude(_consent("ask", [ws["repo"]]), workspace=ws["repo"])
    assert not any(r.startswith("Edit(") for r in rules["allow"])
    rules = R.compile_claude(_consent("task", [ws["repo"]], categories=("read", "test")),
                             workspace=ws["repo"])
    assert not any(r.startswith("Edit(") for r in rules["allow"])


def test_approve_all_is_every_tool_and_no_deny(ws):
    rules = R.compile_claude(_consent("all", [ws["repo"]]), workspace=ws["repo"])
    assert rules["deny"] == [] and "Bash" in rules["allow"] and "PowerShell" in rules["allow"]
    assert R.compile_claude(_consent("all", []), workspace=None, classes={"file-reads"}) is None


@pytest.mark.parametrize("path,ok", [
    ("C:\\Work\\x", "//c/Work/x"), ("C:\\", None), ("relative\\x", None),
    ("C:\\Work\\a[1]", None), ("C:\\Work\\(x)", None), ("\\\\server\\share\\x", None),
])
def test_rule_paths_are_written_only_when_safe(path, ok):
    if os.name != "nt" and path.startswith("C:"):
        pytest.skip("Windows paths")
    assert R.rule_path(path) == ok


def test_gitignore_semantics_of_the_matcher():
    m = R._path_matches
    assert m("//c/w/**", "C:\\w\\a\\b.py", True)
    assert not m("//c/w/**", "C:\\w", True)
    assert m("//c/w/**/.git", "C:\\w\\.git\\config", True)          # a directory covers
    assert m("//c/w/**/.git", "C:\\w\\sub\\.git", True)
    assert not m("//c/w/**/.git", "C:\\w\\.github\\x", True)
    assert m("//c/w/**/*.pem", "C:\\w\\a\\k.PEM", True)
    assert not m("//c/w/**/*.pem", "C:\\w\\a\\k.PEM", False)
    assert not m("//c/w/*.py", "C:\\w\\a\\b.py", True)              # * stays in a directory
    assert not m("**/x", "C:\\x", True)                              # relative: never emitted


def test_deny_beats_allow_and_any_path_denies():
    rules = {"allow": ["Edit(//c/w/**)"], "deny": ["Edit(//c/w/**/.git)"]}
    assert R.claude_verdict(rules, "Write", ["C:\\w\\a.py"]) == "allow"
    assert R.claude_verdict(rules, "Write", ["C:\\w\\a.py", "C:\\w\\.git\\x"]) == "deny"
    assert R.claude_verdict(rules, "Write", ["C:\\w\\a.py", "C:\\v\\a.py"]) == "ask"
    assert R.claude_verdict(rules, "Write", []) == "ask"


# ---------------------------------------------------------------------------
# the write-behind audit


class _FakeCV:
    def __init__(self, gate=None):
        self.acts = []
        self.gate = gate

    def record_act(self, **kw):
        if self.gate is not None:
            self.gate.wait(10)
        self.acts.append((kw["detail"]["by"], kw["because"]))
        return f"opr-{len(self.acts)}"


class _Op:
    def __init__(self, n):
        self.summary, self.category, self.tool, self.tool_label = f"op {n}", "read", "t", "t"
        self.within, self.outside, self.resources = True, [], []
        self.command, self.cwd = None, None


START = {"id": "opr-run", "actor": "ent-a", "conversation": None, "turn": None,
         "execution": "inst", "runtime": "claude"}


def test_automatic_answers_are_written_in_order_and_flushed():
    cv = _FakeCV()
    audit = P._Audit(cv)
    for i in range(50):
        audit.record(START, _Op(i), "allowed", "grant")
    audit.record(START, _Op(50), "refused", "owner", wait=True)
    assert [b for _, b in cv.acts] == [f"allowed by grant: op {i}" for i in range(50)] \
        + ["refused by owner: op 50"]
    assert audit.flush() and audit.pending() == 0
    assert audit.answered["opr-run"] == 51


def test_the_answer_does_not_wait_for_its_record_but_a_refusal_does():
    gate = threading.Event()
    cv = _FakeCV(gate)
    audit = P._Audit(cv)
    t0 = time.time()
    audit.record(START, _Op(1), "allowed", "grant")
    assert time.time() - t0 < 1 and cv.acts == []          # answered; not yet written
    assert audit.flush(timeout=0.2) is False                  # a flush waits for it
    done = []
    t = threading.Thread(target=lambda: (audit.record(START, _Op(2), "refused", "deny",
                                                      wait=True), done.append(1)))
    t.start()
    time.sleep(0.2)
    assert not done                                           # the refusal waits its turn
    gate.set()
    t.join(10)
    assert done and [b for b, _ in cv.acts] == ["grant", "deny"]


def test_a_crash_loses_at_most_what_was_queued_and_never_a_refusal():
    """Simulated: the writer never gets to run (a process that died). The
    automatic answer is not in the record; the run end act's tool calls
    still show it. A refusal is never answered before it is written."""
    gate = threading.Event()
    cv = _FakeCV(gate)
    audit = P._Audit(cv)
    audit.record(START, _Op(1), "allowed", "grant")
    assert audit.pending() == 1 and cv.acts == []
    gate.set()
    assert audit.flush(timeout=10) and len(cv.acts) == 1


def test_readers_of_a_runs_answers_see_every_answer_given():
    cv = _FakeCV()
    cv._c = type("S", (), {"operational": lambda self, **kw: []})()
    cv._write_order = lambda ids: {}
    gate = threading.Event()
    cv.gate = gate
    audit = P._audit_for(cv)
    audit.record(START, _Op(1), "allowed", "grant")
    threading.Timer(0.2, gate.set).start()
    C.answered(cv, "opr-run")                                 # waits for the write
    assert len(cv.acts) == 1


def test_end_of_run_flushes_and_summarises_compiled_runs():
    class St:
        cv = _FakeCV()
    policy = P.make_policy(St)
    policy.audit.record(START, _Op(1), "allowed", "grant")
    evidence: dict = {}
    calls = [{"id": "1", "kind": "read", "status": "completed"},
             {"id": "2", "kind": "edit", "status": "completed"},
             {"id": "3", "kind": "edit", "status": "failed"}]
    policy.end_of_run("opr-run", {"mode": "task", "runtime_rules": {"allow": ["Read"], "deny": []}},
                      calls, evidence)
    assert len(St.cv.acts) == 1
    a = evidence["audit"]
    assert a["tool_calls"] == 3 and a["by_kind"] == {"read": 1, "edit": 2}
    assert a["asked_mentis"] == 1 and a["by_status"]["failed"] == 1
    plain: dict = {}
    policy.end_of_run("opr-run", {"mode": "task"}, calls, plain)
    assert "audit" not in plain


# ---------------------------------------------------------------------------
# runtime rules reach only enabled runtimes


def test_runtime_rules_only_for_enabled_runtimes(ws, monkeypatch):
    c = _consent("task", [ws["repo"]])
    monkeypatch.setattr(P, "COMPILED_SCOPE_RUNTIMES", frozenset({"claude"}))
    assert P.runtime_rules(c, workspace=ws["repo"], runtime="claude")["allow"]
    for other in ("gemini", "codex", "antigravity", None):
        assert P.runtime_rules(c, workspace=ws["repo"], runtime=other) is None
    monkeypatch.setattr(P, "COMPILED_SCOPE_RUNTIMES", frozenset())
    assert P.runtime_rules(c, workspace=ws["repo"], runtime="claude") is None


def test_mars_is_told_the_rules_of_a_claude_run_without_owner_consent(world, monkeypatch):
    """No consent from the owner: the run's own Mentis tools and reads in its
    workspace are still compiled; MARS hears `ask` with no workspaces."""
    from tests.test_run_consent import _policy_world  # noqa: F401
    import tempfile
    repo = tempfile.mkdtemp()
    cid = a_conversation(world, "Rules")
    turn = say(world, cid, "work")["turn"]
    exp = world["cv"].expect(turn, of=world["steward"], kind="result",
                             by=world["who"]["@brian"])
    run = world["cv"].record_act(actor=world["steward"], act="execution-started",
                                 conversation=cid, turn=turn, execution="inst-r",
                                 runtime="claude", caused_by=exp, because="test",
                                 detail={"workspace": repo})
    told = P.mars_consent(world["cv"], run, repo)
    assert told["mode"] == "ask" and told["workspaces"] == []
    assert not any(r.startswith("Edit(") for r in told["runtime_rules"]["allow"])
    monkeypatch.setattr(P, "COMPILED_SCOPE_RUNTIMES", frozenset())
    assert P.mars_consent(world["cv"], run, repo) is None


def test_a_compiled_claude_run_ends_with_its_audit(world, tmp_path, monkeypatch):
    """Dispatched for real on a scripted claude backend: MARS is handed the
    rules, and the run's end act carries `detail.audit` from its tool calls."""
    import mentis.web as web
    from mentis.execution import RunResult
    from mentis.web import dispatch as D
    from tests._loop import script_every_backend
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    specs = []

    def done(spec):
        specs.append(spec)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         text="done", stop_reason="end_turn", started_at=now,
                         finished_at=now,
                         tool_calls=[{"id": "t1", "title": "Read a.py", "kind": "read",
                                      "status": "completed"},
                                     {"id": "t2", "title": "Edit a.py", "kind": "edit",
                                      "status": "completed"}])

    script_every_backend(world["state"].agents, done)
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: D.dispatch(world["state"], **kw))
    cid = a_conversation(world, "Compiled")
    say(world, cid, "change it", action="ask-participant",
        dispatch=[{"participant": world["steward"], "work": "change it", "runtime": "claude",
                   "consent": {"mode": "task", "workspaces": [str(repo)]}}])
    assert [s.backend for s in specs] == ["claude"]
    rules = specs[0].consent["runtime_rules"]
    assert any(r.startswith("Edit(") for r in rules["allow"])
    ends = [a for a in world["cv"]._c.operational(act="result-returned")
            if a["runtime"] == "claude"]
    audit = ends[-1]["detail"]["audit"]
    assert audit["tool_calls"] == 2 and audit["by_kind"] == {"read": 1, "edit": 1}
    assert audit["asked_mentis"] == 0
