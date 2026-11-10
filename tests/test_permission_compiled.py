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
    rules = R.compile_claude(_consent("task", [ws["repo"]]), workspace=ws["repo"],
                             classes=R.ALL_CLASSES)
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
    rules = R.compile_claude(_consent("ask", [ws["repo"]]), workspace=ws["repo"],
                             classes=R.ALL_CLASSES)
    assert not any(r.startswith("Edit(") for r in rules["allow"])
    rules = R.compile_claude(_consent("task", [ws["repo"]], categories=("read", "test")),
                             workspace=ws["repo"], classes=R.ALL_CLASSES)
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
        self.observed = []
        self.gate = gate

    def record_act(self, **kw):
        if self.gate is not None:
            self.gate.wait(10)
        if kw["act"] == P.OBSERVED:
            self.observed.append(kw["detail"]["calls"])
            return "opr-o"
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
    assert rules == {"allow": ["mcp__mentis__*"], "deny": []}
    ends = [a for a in world["cv"]._c.operational(act="result-returned")
            if a["runtime"] == "claude"]
    audit = ends[-1]["detail"]["audit"]
    assert audit["tool_calls"] == 2 and audit["by_kind"] == {"read": 1, "edit": 1}
    assert audit["asked_mentis"] == 0 and audit["applied"] == {"allow": 1, "ask": 0}
    observed = [a for a in world["cv"]._c.operational(act=P.OBSERVED)]
    assert observed == []        # a scripted backend emits no events


# ---------------------------------------------------------------------------
# authority changes remain effective: a narrowing stops stale compiled rules


def _blocking_claude(world, monkeypatch):
    """Dispatch for real in threads; the first run on each backend works until
    it is halted, later runs end at once. Returns (specs, halted)."""
    import mentis.web as web
    from mentis.execution import RunResult
    from mentis.web import dispatch as D
    from tests._loop import script_every_backend
    svc = world["state"].agents
    specs, halted = [], threading.Event()
    real_halt = svc.agents_halt_run

    def halt(run, **kw):
        got = real_halt(run, **kw)
        halted.set()
        return got
    monkeypatch.setattr(svc, "agents_halt_run", halt)

    def work(spec):
        specs.append(spec)
        first = len(specs) == 1
        if first:
            halted.wait(20)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         text="stopped" if first else "done",
                         stop_reason="cancelled" if first else "end_turn",
                         started_at=now, finished_at=now)

    script_every_backend(svc, work)
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: threading.Thread(
        target=D.dispatch, args=(world["state"],), kwargs=kw, daemon=True).start())
    return specs, halted


def _start_compiled(world, tmp_path, runtime, consent):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True, exist_ok=True)
    cid = a_conversation(world, f"Narrow {runtime}")
    got = say(world, cid, "change it", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "change it",
                         "runtime": runtime,
                         "consent": {**consent, "workspaces": [str(repo)]}}])
    exp = got["expectations"][0]
    cv = world["cv"]
    deadline = time.time() + 20
    run = None
    while time.time() < deadline and run is None:
        run = next((a["id"] for a in cv._c.operational(caused_by=exp)
                    if a["act"] == "execution-started"), None)
        time.sleep(0.05)
    assert run
    return cid, exp, run, str(repo)


def _wait(cond, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_narrowing_a_compiled_run_halts_it_and_restarts_fresh(world, tmp_path, monkeypatch):
    from mentis.web import compiled_runs
    specs, halted = _blocking_claude(world, monkeypatch)
    cid, exp, run, repo = _start_compiled(world, tmp_path, "claude", {"mode": "all"})
    cv = world["cv"]
    assert _wait(lambda: specs and run in compiled_runs.tracked(cv))
    assert "Bash" in specs[0].consent["runtime_rules"]["allow"]
    # THE OWNER NARROWS: Approve All revoked, anything not routine refused.
    C.set_task(cv, run, owner=world["who"]["@brian"],
               consent={"mode": "deny", "workspaces": [repo],
                        "categories": ["read", "edit"]}, because="narrowed")
    assert halted.is_set()
    asked = [a for a in cv._c.operational(caused_by=run)
             if a["act"] == compiled_runs.RESTART_ASKED]
    assert asked and asked[0]["detail"]["reason"] == "consent-narrowed"
    # nothing Mentis answers for the old run allows what the new consent refuses
    policy = P.make_policy(world["state"])
    req = {"tool_call": {"kind": "execute", "title": "curl https://example.com",
                         "raw_input": {"command": "curl https://example.com"}},
           "shell_cwd": repo, "options": OPTS}
    assert policy(run, "inst-x", req, {}) is None
    # the work continues, in a FRESH session, under rules compiled from the new consent
    assert _wait(lambda: len(specs) >= 2)
    fresh = specs[1]
    assert fresh.resume is None
    assert fresh.consent["mode"] == "deny"
    assert fresh.consent["runtime_rules"] == {"allow": ["mcp__mentis__*"], "deny": []}
    restarted = [a for a in cv._c.operational(caused_by=exp)
                 if a["act"] == compiled_runs.RESTARTED]
    assert len(restarted) == 1 and restarted[0]["detail"]["run"] == run


def test_widening_restarts_nothing(world, tmp_path, monkeypatch):
    from mentis.web import compiled_runs
    specs, halted = _blocking_claude(world, monkeypatch)
    cid, exp, run, repo = _start_compiled(world, tmp_path, "claude",
                                          {"mode": "task", "categories": ["read", "edit"]})
    cv = world["cv"]
    assert _wait(lambda: run in compiled_runs.tracked(cv))
    C.set_task(cv, run, owner=world["who"]["@brian"],
               consent={"mode": "all", "workspaces": [repo]}, because="widened")
    assert not halted.is_set()
    assert not [a for a in cv._c.operational(caused_by=run)
                if a["act"] == compiled_runs.RESTART_ASKED]
    world["state"].agents.agents_halt_run(run, by="test", why="end the test run")


def test_a_run_without_compiled_rules_is_not_restarted(world, tmp_path, monkeypatch):
    from mentis.web import compiled_runs
    specs, halted = _blocking_claude(world, monkeypatch)
    cid, exp, run, repo = _start_compiled(world, tmp_path, "codex", {"mode": "all"})
    cv = world["cv"]
    assert _wait(lambda: specs) and "runtime_rules" not in (specs[0].consent or {})
    C.set_task(cv, run, owner=world["who"]["@brian"],
               consent={"mode": "deny", "workspaces": [repo]}, because="narrowed")
    assert not halted.is_set() and run not in compiled_runs.tracked(cv)
    assert not [a for a in cv._c.operational(caused_by=run)
                if a["act"] == compiled_runs.RESTART_ASKED]
    world["state"].agents.agents_halt_run(run, by="test", why="end the test run")


def test_a_carriers_workflow_change_leaves_no_compiled_edit_standing(ws):
    """A Workflow change withdraws only the run's standing allowance to edit.
    Under `ask` no Edit rule is compiled from it; under routine work the edit
    rests on the owner's consent, which `decide` still honours while the
    change is pending -- so no compiled rule outlives what it withdrew."""
    change = {"id": "opr-change"}
    for consent in (_consent("ask", [ws["repo"]]), _consent("task", [ws["repo"]]),
                    _consent("deny", [ws["repo"]])):
        rules = R.compile_claude(consent, workspace=ws["repo"], classes=R.ALL_CLASSES)
        for tool in R.EDIT_TOOLS:
            path = os.path.join(ws["repo"], "src", "app.py")
            if R.claude_verdict(rules, tool, [path]) == "allow":
                assert decide(_file("edit", path, tool), workspace=ws["repo"],
                              consent=consent, pending=change).outcome == "allow"
            else:
                assert consent["mode"] == "ask"


def test_narrower_reads_what_mars_applies():
    from mentis.web.compiled_runs import narrower
    mcp = {"allow": ["mcp__mentis__*"], "deny": []}
    every = {"allow": list(R.ALL_TOOLS), "deny": []}
    # allow rules apply only under task (Approve All is sent as task)
    assert not narrower(mcp, "ask", None, "deny")           # nothing was applied
    assert not narrower(mcp, "deny", None, "ask")
    assert narrower(mcp, "task", mcp, "ask")                # task -> ask: allow dropped
    assert narrower(every, "all", mcp, "task")
    assert not narrower(mcp, "task", every, "all")          # widening
    old = {"allow": ["mcp__mentis__*", "Read(//c/w/**)", "Edit(//c/w/**)"], "deny": []}
    assert not narrower(old, "task", {"allow": ["Read", "Edit", "Bash", "mcp__mentis__*"],
                                      "deny": []}, "all")
    assert narrower(old, "task", {"allow": ["mcp__mentis__*", "Read(//c/w/**)"],
                                  "deny": []}, "task")
    # a new deny (applied as ask) narrows only where it meets an old allow
    assert narrower(old, "task", {**old, "deny": ["Read(//[cC]/[wW]/**/.[eE][nN][vV])"]}, "task")
    assert not narrower(old, "task", {"allow": old["allow"] + ["Edit(//c/v/**)"],
                                      "deny": ["Edit(//[cC]/[vV]/**/.[gG][iI][tT])"]}, "task")
    assert not narrower(mcp, "task", {**mcp, "deny": ["Edit(//c/w/**/.env)"]}, "task")
    assert not narrower(old, "task", dict(old), "task")


@pytest.mark.parametrize("start,new", [
    ({"mode": "ask"}, {"mode": "task", "categories": list(DEFAULT_CATEGORIES)}),
    ({"mode": "task", "categories": ["read", "edit"]},
     {"mode": "task", "categories": ["read", "edit"], "extra": True}),
    ({"mode": "task", "categories": ["read"]}, {"mode": "task", "categories": ["read", "edit"]}),
])
def test_widening_never_halts(world, tmp_path, monkeypatch, start, new):
    """The security review's probes: ask -> task (what "Allow within this
    task" records), adding a workspace, adding a category."""
    from mentis.web import compiled_runs
    specs, halted = _blocking_claude(world, monkeypatch)
    cid, exp, run, repo = _start_compiled(world, tmp_path, "claude", start)
    cv = world["cv"]
    assert _wait(lambda: run in compiled_runs.tracked(cv)
                 and compiled_runs.tracked(cv)[run]["open"])
    other = tmp_path / "other"
    other.mkdir(exist_ok=True)
    new = dict(new)
    ws_ = [repo, str(other)] if new.pop("extra", None) else [repo]
    C.set_task(cv, run, owner=world["who"]["@brian"], consent={**new, "workspaces": ws_},
               because="widened")
    assert not halted.is_set()
    assert not [a for a in cv._c.operational(caused_by=run)
                if a["act"] == compiled_runs.RESTART_ASKED]
    world["state"].agents.agents_halt_run(run, by="test", why="end the test run")


class _Agents:
    def __init__(self, takes_after=0):
        self.tries, self.takes_after = 0, takes_after

    def agents_halt_run(self, run, *, by, why):
        self.tries += 1
        return self.tries > self.takes_after


def _tracked_run(world, consent):
    """A recorded claude run whose session is open with compiled rules."""
    import tempfile
    from mentis.web import compiled_runs
    repo = tempfile.mkdtemp()
    cid = a_conversation(world, "Tracked")
    turn = say(world, cid, "work")["turn"]
    cv = world["cv"]
    exp = cv.expect(turn, of=world["steward"], kind="result", by=world["who"]["@brian"],
                    detail={"consent": {**consent, "workspaces": [repo]}})
    run = cv.record_act(actor=world["steward"], act="execution-started", conversation=cid,
                        turn=turn, execution="inst-t", runtime="claude", caused_by=exp,
                        because="test", detail={"workspace": repo})
    told = P.mars_consent(cv, run, repo)
    compiled_runs.opened(cv, run)
    return cv, run, repo, told


def _restart_asked(cv, run):
    from mentis.web import compiled_runs
    return [a for a in cv._c.operational(caused_by=run)
            if a["act"] == compiled_runs.RESTART_ASKED]


def test_a_narrowing_before_the_session_opens_reaches_its_rules(world, monkeypatch):
    from mentis.web import compiled_runs
    cv, run, repo, told = _tracked_run(world, {"mode": "all"})
    with compiled_runs._lock:
        compiled_runs._live(cv)[run]["open"] = False          # still opening
    agents = _Agents()
    monkeypatch.setattr(cv, "_compiled_st", type("S", (), {"agents": agents})(), raising=False)
    assert "Bash" in told["runtime_rules"]["allow"]
    C.set_task(cv, run, owner=world["who"]["@brian"],
               consent={"mode": "ask", "workspaces": [repo]}, because="narrowed")
    assert agents.tries == 0                                   # nothing to halt yet
    P.before_open(cv, run, repo, told)                         # as the session opens
    assert told["mode"] == "ask" and "Bash" not in told["runtime_rules"]["allow"]
    compiled_runs.untrack(cv, run)


def test_a_halt_that_cannot_take_yet_stays_pending(world, monkeypatch):
    from mentis.web import compiled_runs
    cv, run, repo, told = _tracked_run(world, {"mode": "all"})
    agents = _Agents(takes_after=3)
    monkeypatch.setattr(compiled_runs, "HALT_POLL_S", 0.2)
    policy = P.make_policy(world["state"])
    monkeypatch.setattr(cv, "_compiled_st", type("S", (), {"agents": agents})(), raising=False)
    C.set_task(cv, run, owner=world["who"]["@brian"],
               consent={"mode": "deny", "workspaces": [repo]}, because="narrowed")
    assert compiled_runs.halting(cv, run) and not _restart_asked(cv, run)
    # refused meanwhile, whatever the request
    assert policy(run, "inst-t", _mcp("mcp__mentis__find"), {}) is None
    assert _wait(lambda: agents.tries > 3 and _restart_asked(cv, run))
    assert len(_restart_asked(cv, run)) == 1
    compiled_runs.untrack(cv, run)


def test_a_recheck_that_fails_halts_the_run(world, monkeypatch):
    from mentis.web import compiled_runs
    cv, run, repo, told = _tracked_run(world, {"mode": "task"})
    agents = _Agents()
    monkeypatch.setattr(cv, "_compiled_st", type("S", (), {"agents": agents})(), raising=False)

    def broken(*a, **kw):
        raise RuntimeError("unreadable")
    monkeypatch.setattr(P, "runtime_rules", broken)
    assert compiled_runs.recheck(cv) == [run]
    assert agents.tries == 1 and _restart_asked(cv, run)
    compiled_runs.untrack(cv, run)


def test_restart_respects_the_owners_stop(world, monkeypatch):
    from mentis.web import compiled_runs
    import mentis.web as web
    cv, run, repo, told = _tracked_run(world, {"mode": "all"})
    monkeypatch.setattr(cv, "_compiled_st", type("S", (), {"agents": _Agents()})(),
                        raising=False)
    C.set_task(cv, run, owner=world["who"]["@brian"],
               consent={"mode": "deny", "workspaces": [repo]}, because="narrowed")
    assert _restart_asked(cv, run)
    start = cv._act(run)
    cv.record_act(actor=world["who"]["@brian"], act=compiled_runs.STOP_ASKED,
                  conversation=start["conversation"], turn=start["turn"],
                  caused_by=run, because="the owner stopped it")
    dispatched = []
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: dispatched.append(kw))
    assert compiled_runs.restart_if_asked(world["state"], run) is None and not dispatched


def test_a_restarted_run_has_not_ended_for_what_waits_on_it(world, tmp_path, monkeypatch):
    """The halted run's ending restarts the work INSTEAD of resuming whatever
    waits on it; the restarted run's own ending resumes them as always."""
    from mentis.web import compiled_runs
    from mentis.web import dispatch as D
    log = []
    real_restart, real_resume = compiled_runs.restart_if_asked, D.resume_if_ready

    def restart(st, run):
        got = real_restart(st, run)
        log.append(("restart", bool(got)))
        return got

    def resume(st, exp):
        log.append(("resume", exp))
        return real_resume(st, exp)
    monkeypatch.setattr(compiled_runs, "restart_if_asked", restart)
    monkeypatch.setattr(D, "resume_if_ready", resume)
    specs, halted = _blocking_claude(world, monkeypatch)
    cid, exp, run, repo = _start_compiled(world, tmp_path, "claude", {"mode": "all"})
    cv = world["cv"]
    assert _wait(lambda: run in compiled_runs.tracked(cv)
                 and compiled_runs.tracked(cv)[run]["open"])
    C.set_task(cv, run, owner=world["who"]["@brian"],
               consent={"mode": "deny", "workspaces": [repo]}, because="narrowed")
    assert _wait(lambda: len(log) >= 3)
    assert log[:3] == [("restart", True), ("restart", False), ("resume", exp)]


def test_observed_calls_are_recorded_in_batches_and_at_the_end():
    cv = _FakeCV()
    audit = P._Audit(cv)
    audit.OBSERVED_N = 3
    for i in range(7):
        audit.observe(START, "opr-run", {"tool_call_id": f"t{i}", "kind": "read",
                                         "status": "pending", "title": f"Read {i}"}, i)
    audit.observe(START, "opr-run", {"tool_call_id": "t6", "status": "completed"}, 9)
    assert audit.flush()
    assert [len(b) for b in cv.observed] == [3, 3]           # written as it goes
    audit.observed_flush("opr-run")                          # and at the run's end
    assert audit.flush()
    assert [len(b) for b in cv.observed] == [3, 3, 1]
    assert cv.observed[-1][0]["status"] == "completed"


def test_an_end_act_says_when_records_were_not_written(monkeypatch):
    class St:
        cv = _FakeCV(gate=threading.Event())
    policy = P.make_policy(St)
    monkeypatch.setattr(P, "FLUSH_S", 0.2)
    policy.audit.record(START, _Op(1), "allowed", "grant")
    evidence: dict = {}
    policy.end_of_run("opr-run", {"mode": "task"}, [], evidence)
    assert evidence["permission_records_unwritten"] == 1
    St.cv.gate.set()


def test_an_unwritable_deny_compiles_no_allow(ws):
    bad = os.path.join(ws["tmp"], "odd[dir]")
    assert R.compile_claude(_consent("task", [ws["repo"]]), workspace=ws["repo"],
                            classes=R.ALL_CLASSES, roots=[bad]) is None
