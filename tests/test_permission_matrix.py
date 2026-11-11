"""Round 2 (O3): the permission-enforcement matrix, one pinned fact per row.

docs/modernization/CONTRACT.md "Round 2 — A (authority)" holds the matrix: for
each runtime, what its runtime enforces itself, what MARS enforces, what
Mentis decides, and what nothing enforces. These tests pin the Mentis side of
every row; MARS's side is pinned in MARS (`consent.rs`, `tooling.rs`,
`backends/acp_tests.rs`). Live evidence is listed in the contract.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from mentis import permission_rules as R
from mentis.execution import RunSpec
from mentis.execution.mars import _RunState, shell_cwd
from mentis.execution.tooling import effective, render
from mentis.operational import consent as C
from mentis.web import permissions as P
from mentis.web.permissions import decide, enforcement, mars_consent, runtime_options
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_run_consent import OPTS, _request, ws  # noqa: F401

def _contract_of(runtime):
    """The capability contract MARS declares for this runtime (offline profiles)."""
    from mentis.core import runtime_contract as RC
    from tests.conformance_runtime.profiles import PROFILES
    return RC.of_backend(PROFILES[runtime]["backend"])



def _consent(mode, workspaces, categories=("read", "edit", "test", "build", "run")):
    return {"mode": mode, "workspaces": list(workspaces), "categories": list(categories),
            "tools": [], "source": "owner", "research": {}}


def _bash(command, cwd):
    return {"tool_call": {"kind": "execute", "title": command,
                          "raw_input": {"command": command}},
            "options": OPTS, "shell": "bash", "shell_cwd": cwd}


def _read(path):
    return {"tool_call": {"kind": "read", "title": f"Read {path}",
                          "locations": [{"path": path}], "raw_input": {"file_path": path}},
            "options": OPTS}


# ---------------------------------------------------------------------------
# Claude: what Claude Code decides itself unless told to ask


#: Measured 2026-11-10 (claude-agent-acp 0.97.0, Claude Code 2.1.322; CONTRACT
#: "Round 2 — A", probes C1-C7): run WITHOUT asking the client in default mode.
CLAUDE_RAN_UNASKED = ["echo hello", "sleep 2", "pwd", "ls", "cat notes.txt", "git status",
                      'find apps -name "*.txt"', "cat .env"]
#: ... and asked the client.
CLAUDE_ASKED = ["mkdir newdir", "touch newfile.txt", "echo hi > out.txt",
                "bash -c 'mkdir viabash'", "sleep 1 && mkdir chained", "rm newfile.txt",
                'python -c "print(1)"']


@pytest.mark.parametrize("mode", ["ask", "task", "deny"])
def test_outside_approve_all_every_self_decided_claude_tool_reaches_mentis(mode, tmp_path):
    """The `sleep`/`echo` finding: Claude runs read-only commands and reads
    inside its directories by itself. Outside Approve All its rules now name
    every such tool as an ask rule (sent as deny), so each call reaches Mentis."""
    ws = str(tmp_path)
    rules = P.runtime_rules(_consent(mode, [ws]), workspace=ws, runtime="claude")
    assert set(R.SELF_DECIDED) <= set(rules["deny"])
    assert rules["allow"] == [R.MENTIS_TOOLS]          # nothing else is ever allowed
    for tool in R.SELF_DECIDED:
        for paths in ([], [os.path.join(ws, "notes.txt")], [os.path.join(ws, ".env")]):
            # a secret by name: Read/Grep/Glob are refused by Claude itself (and kept
            # out of its searches); everything else reaches Mentis
            secret = tool in R.READ_TOOLS and paths and paths[0].endswith(".env")
            assert R.applied_verdict(rules, mode, tool, paths) == ("deny" if secret else "ask"),                 (tool, paths)
    # Mentis's own tools are still the runtime's to allow under task
    expected = "allow" if mode == "task" else "ask"
    assert R.applied_verdict(rules, mode, "mcp__mentis__orient") == expected


def test_what_claude_ran_unasked_is_now_decided_by_mentis(tmp_path):
    """What Claude ran unasked, decided by Mentis: the read-only commands are
    still allowed at once by the run's grant (no capability lost), and the
    secret it read without asking (`cat .env`, Read `.env`) is asked of the owner."""
    ws = str(tmp_path)
    c = _consent("task", [ws])
    for command in CLAUDE_RAN_UNASKED:
        d = decide(_bash(command, ws), workspace=ws, consent=c)
        expected = "ask" if ".env" in command else "allow"
        assert d.outcome == expected, (command, d.op.outside)
    assert decide(_read(os.path.join(ws, ".env")), workspace=ws, consent=c).outcome == "ask"
    assert decide(_read(os.path.join(ws, "notes.txt")), workspace=ws, consent=c).outcome == "allow"


def test_approve_all_compiles_every_tool_and_asks_nothing(tmp_path):
    rules = P.runtime_rules(_consent("all", [str(tmp_path)]), workspace=str(tmp_path),
                            runtime="claude")
    assert rules == {"allow": list(R.ALL_TOOLS), "deny": []}


def test_compiled_rules_never_reach_edits_or_shell_outside_approve_all(tmp_path):
    """O3: compiled permissions are not extended to file edits, shell
    commands or other runtime operations."""
    assert R.COMPILED_CLASSES == frozenset({"mentis-tools", "approve-all"})
    for mode in ("ask", "task", "deny"):
        rules = P.runtime_rules(_consent(mode, [str(tmp_path)]), workspace=str(tmp_path),
                                runtime="claude")
        assert not [r for r in rules["allow"] if r != R.MENTIS_TOOLS], mode


def test_a_narrowing_from_approve_all_still_halts_and_ask_rules_alone_never_do(tmp_path):
    ws = str(tmp_path)
    rules = {m: P.runtime_rules(_consent(m, [ws]), workspace=ws, runtime="claude")
             for m in ("all", "task", "ask", "deny")}
    from mentis.web.compiled_runs import narrower
    assert narrower(rules["all"], "all", rules["task"], "task")
    for a in ("task", "ask", "deny"):
        for b in ("task", "ask", "deny"):
            assert not narrower(rules[a], a, rules[b], b), (a, b)


def test_shell_commands_start_where_mars_declared(tmp_path):
    """With `command_cwd: "session"` (MARS starts Claude Code with
    CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1) every request carries the
    session's cwd; otherwise only until a first shell command ran."""
    spec = RunSpec(run_id="r", backend="claude", workspace=str(tmp_path), prompt="p")
    state = _RunState(spec=spec, result=None, on_event=None, command_cwd="session")
    state.tools = {"a": {"kind": "execute"}, "b": {"kind": "execute"}}
    assert shell_cwd(state, "b") == str(tmp_path)
    state.command_cwd = None
    assert shell_cwd(state, "b") is None
    state.tools = {"b": {"kind": "execute"}}
    assert shell_cwd(state, "b") == str(tmp_path)


def test_the_run_is_told_its_commands_start_in_its_working_directory():
    claude = {"backend": "claude", "shell": {"name": None, "how": "not-reported", "per_call": True},
              "command_cwd": "session", "tools_how": "not-reported"}
    eff = effective(claude, backend="claude", workspace="C:\\repo")
    assert eff["command_cwd"] == "session"
    text = render(eff, [])
    assert "every shell command starts in the working directory" in text
    assert "your shell's current directory is not reported" not in text
    assert effective({**claude, "command_cwd": "whatever"}, backend="claude",
                     workspace="C:\\repo")["command_cwd"] == "not-reported"


# ---------------------------------------------------------------------------
# every runtime: told its consent, and what enforces it said truthfully


@pytest.mark.parametrize("runtime", ["codex", "antigravity", "kimi-k3", "local", "gemini"])
def test_only_claude_is_given_runtime_rules(runtime, tmp_path):
    for mode in ("ask", "task", "deny", "all"):
        assert P.runtime_rules(_consent(mode, [str(tmp_path)]), workspace=str(tmp_path),
                               runtime=runtime) is None


def _run_on(world, ws, runtime, consent=None):
    cid = a_conversation(world, f"Matrix {runtime}")
    turn, exp = _request(world, cid, consent=consent)
    return world["cv"].record_act(actor=world["steward"], act="execution-started",
                                  conversation=cid, turn=turn, execution=f"inst-{runtime}",
                                  runtime=runtime, caused_by=exp, because="test",
                                  detail={"workspace": ws["repo"]})


@pytest.mark.parametrize("runtime", ["claude", "codex", "antigravity", "kimi-k3", "local"])
def test_every_run_tells_mars_its_consent_so_mars_says_what_enforces_it(world, ws, runtime):
    """No owner consent: MARS still hears `ask` with no workspaces (which adds
    nothing and confines nothing), so its `enforced_by` reaches the record."""
    run = _run_on(world, ws, runtime)
    told = mars_consent(world["cv"], run, ws["repo"])
    rules = told.pop("runtime_rules", None)
    assert told == {"mode": "ask", "workspaces": []}
    assert (rules is not None) == (runtime == "claude")
    assert runtime_options(world["cv"], run, ws["repo"], runtime, _contract_of(runtime)) == {}


def test_antigravity_pre_turn_allow_is_the_only_option_consent_adds(world, ws):
    given = C.consent_value({"mode": "task", "workspaces": [ws["repo"]],
                             "categories": ["read", "test"]})
    run = _run_on(world, ws, "antigravity", consent=given)
    assert runtime_options(world["cv"], run, ws["repo"], "antigravity", _contract_of("antigravity")) == {"allow": ["command(*)"]}
    for other in ("claude", "codex", "kimi-k3", "local"):
        assert runtime_options(world["cv"], run, ws["repo"], other, _contract_of(other)) == {}


@pytest.mark.parametrize("mode,mcp", [("all", True), ("task", False), ("ask", False), ("deny", False)])
def test_antigravity_is_allowed_the_given_user_mcp_servers_only_under_approve_all(world, ws, mode, mcp):
    """Headless agy cannot ask: a user-level MCP server's tools are allowed
    ahead of time only where Mentis would allow them without asking."""
    given = C.consent_value({"mode": mode, "workspaces": [ws["repo"]],
                             "categories": ["read", "test"]})
    run = _run_on(world, ws, "antigravity", consent=given)
    got = runtime_options(world["cv"], run, ws["repo"], "antigravity", _contract_of("antigravity"))
    assert bool(got.get("allow_given_mcp")) is mcp
    assert not [a for a in got.get("allow", []) if a.startswith("mcp(")]


@pytest.mark.parametrize("applied,enforced,words", [
    ({"enforced_by": "client"}, True, "reaches Mentis"),
    ({"enforced_by": "sandbox+client"}, True, "without asking"),
    ({"enforced_by": "sandbox"}, True, "Mentis decides nothing"),
    ({"enforced_by": "none"}, False, "nothing enforces it"),
    (None, False, "Not reported"),
    ({}, False, "Not reported"),
])
def test_enforcement_is_said_as_mars_reported_it(applied, enforced, words):
    got = enforcement(applied)
    assert got["enforced"] is enforced and words in got["words"]


def test_a_local_run_in_full_access_is_never_shown_as_consent_enforced():
    """MARS's `local` worker in full access neither asks nor is confined."""
    got = enforcement({"mode": "task", "workspaces": [], "enforced_by": "none"})
    assert got == {"by": "none", "enforced": False, "words": P.ENFORCEMENT_WORDS["none"]}


def test_compiled_rules_are_said_to_be_the_runtimes_decision():
    got = enforcement({"enforced_by": "client", "runtime_rules": {
        "applied": True, "allow": 1, "deny": 11, "enforced_by": "runtime"}})
    assert got["enforced"] and got["runtime_rules"] == {"allow": 1, "ask": 11, "refuse": 0}
    assert "decided by the runtime from those rules" in got["words"]


def test_the_consent_route_says_what_enforces_it(world, ws):
    from tests._loop import get
    run = _run_on(world, ws, "local")
    got = get(world, f"/api/runs/{run}/consent")
    assert got["consent"]["enforcement"]["enforced"] is False
    assert "Not reported" in got["consent"]["enforcement"]["words"]


# ---------------------------------------------------------------------------
# protected locations, owner escalations, audit (pinned elsewhere; named here)


def test_protected_locations_are_never_compiled_or_granted(tmp_path):
    ws = str(tmp_path)
    for mode in ("ask", "task", "deny"):
        c = _consent(mode, [ws])
        rules = P.runtime_rules(c, workspace=ws, runtime="claude")
        for path in (os.path.join(ws, ".env"), os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa")):
            assert R.applied_verdict(rules, mode, "Read", [path]) == "deny"
            assert R.applied_verdict(rules, mode, "Grep", [path]) == "deny"
            assert decide(_read(path), workspace=ws, consent=c).outcome in ("ask", "deny")


def test_the_halt_window_cancel_is_sent_with_the_consent(world, monkeypatch):
    """The narrowing's recheck runs in the owner's consent call: the cancel
    is asked before `set_task` returns (measured live: <= 2.5 ms after the
    consent act, the run ended 73-148 ms after it)."""
    from mentis.web import compiled_runs
    order = []
    monkeypatch.setattr(compiled_runs, "recheck",
                        lambda cv, **kw: order.append(("recheck", kw.get("cause"))) or [])
    monkeypatch.setattr(compiled_runs, "tracked", lambda cv: {"r": {}})
    cid = a_conversation(world, "Order")
    turn, exp = _request(world, cid)
    run = world["cv"].record_act(actor=world["steward"], act="execution-started",
                                 conversation=cid, turn=turn, execution="inst-o",
                                 runtime="claude", caused_by=exp, because="t",
                                 detail={"workspace": None})
    act = C.set_task(world["cv"], run, owner=world["who"]["@brian"],
                     consent={"mode": "ask", "workspaces": [], "categories": ["read"]},
                     because="narrow")
    assert order == [("recheck", act)]


# ---------------------------------------------------------------------------
# secrets inside a searched directory (round 2, after the hand-back)


@pytest.mark.parametrize("mode", ["ask", "task", "deny"])
def test_claude_hides_secrets_by_name_from_its_own_searches_outside_approve_all(mode, tmp_path):
    """Measured: a Claude `deny` Read rule keeps the files out of Grep and Glob
    results (an `ask` rule does not); MARS applies `refuse` as that deny."""
    ws = str(tmp_path)
    rules = P.runtime_rules(_consent(mode, [ws]), workspace=ws, runtime="claude")
    assert rules["refuse"] == R.hidden_secrets()
    for name in (".env", ".ENV", ".env.local", ".env.production", ".env.development.local",
                 "id_rsa", "id_ed25519", "credentials", "credentials.json", "auth.json"):
        for tool in R.READ_TOOLS:
            assert R.applied_verdict(rules, mode, tool, [os.path.join(ws, "sub", name)]) == "deny"
        assert R.applied_verdict(rules, mode, "Read", [rf"C:\elsewhere\{name}"]) == "deny"
    assert R.applied_verdict(rules, mode, "Grep", [os.path.join(ws, "sub", "code.py")]) == "ask"
    assert "refuse" not in P.runtime_rules(_consent("all", [ws]), workspace=ws, runtime="claude")


@pytest.mark.parametrize("mode", ["ask", "task", "deny"])
def test_only_high_confidence_secrets_are_refused_by_claude_itself(mode, tmp_path):
    """Review M1: the hard refuse list (no owner approval reaches it) names only
    files that are secrets by name with high confidence. Ordinary files the
    wider classifier also protects are asked of Mentis, as before."""
    ws = str(tmp_path)
    rules = P.runtime_rules(_consent(mode, [ws]), workspace=ws, runtime="claude")
    home = os.path.expanduser("~")
    for path in (os.path.join(ws, "src", "credentials.py"), os.path.join(ws, ".env.example"),
                 os.path.join(ws, ".env.sample"), os.path.join(ws, ".env.template"),
                 os.path.join(ws, "certs", "ca.pem"), os.path.join(ws, "id_rsa.pub"),
                 os.path.join(ws, "server.key"), os.path.join(ws, "cert.pfx"),
                 os.path.join(home, ".claude", "settings.json"),
                 os.path.join(home, ".ssh", "config")):
        for tool in R.READ_TOOLS:
            assert R.applied_verdict(rules, mode, tool, [path]) == "ask", (tool, path)
    # no protected location is refused wholesale: those are asked, as before
    assert all(r.startswith(("Read(**/", "Read(//**/")) for r in rules["refuse"]), rules["refuse"]


def test_the_hard_refuse_list_stays_inside_the_mentis_secret_classifier():
    """Every name Claude refuses itself is one Mentis already protects."""
    from mentis.operations import _SECRET_NAMES
    for g in R.HARD_SECRET_GLOBS:
        example = g.replace("*", "x")
        assert _SECRET_NAMES.search(os.sep + example), g


@pytest.mark.parametrize("mode", ["ask", "task"])
def test_an_owner_approved_read_of_a_refused_secret_has_an_authorized_path(mode, tmp_path):
    """Review M1: Claude refuses Read of `.env` itself, but a shell read of it
    reaches Mentis (Bash is an ask rule, not refused) and is asked of the
    owner with an Allow-once answer; the agent is told so in its tooling."""
    ws = str(tmp_path)
    env = os.path.join(ws, ".env")
    rules = P.runtime_rules(_consent(mode, [ws]), workspace=ws, runtime="claude")
    assert R.applied_verdict(rules, mode, "Read", [env]) == "deny"
    for tool in ("Bash", "PowerShell"):
        assert R.applied_verdict(rules, mode, tool, [env]) == "ask"
    got = decide(_bash("cat .env", ws), workspace=ws, consent=_consent(mode, [ws]))
    assert got.outcome == "ask"
    assert P.ONCE in P.offers(got.op, _consent(mode, [ws]))
    text = render(effective({}, backend="claude", workspace=ws,
                            consent=_consent(mode, [ws])))
    assert "read it with a shell command" in text and "asks the owner" in text
    assert "read it with a shell command" not in render(
        effective({}, backend="claude", workspace=ws, consent=_consent("all", [ws])))
    words = enforcement({"enforced_by": "client",
                         "runtime_rules": {"applied": True, "refuse": len(rules["refuse"])}})
    assert "shell command" in words["words"] and "asked of the owner" in words["words"]


@pytest.fixture()
def secrets_ws(tmp_path):
    ws = tmp_path / "repo"
    (ws / "sub").mkdir(parents=True)
    (ws / ".env").write_text("FAKE=1")
    (ws / "sub" / "id_rsa").write_text("FAKE")
    (ws / "a.py").write_text("FAKE")
    (ws / "src").mkdir()
    (ws / "src" / "b.py").write_text("FAKE")
    (ws / ".venv" / "lib").mkdir(parents=True)
    (ws / ".venv" / "lib" / "cacert.pem").write_text("public certs")
    return str(ws)


@pytest.mark.parametrize("command,secret", [
    ("grep -r FAKE .", True),
    ("grep -rn FAKE", True),
    ("grep -R FAKE sub", True),
    ("cd sub && grep -r FAKE .", True),
    ("grep -r --exclude=.env FAKE .", True),                     # id_rsa still read
    ("grep -r --exclude=.env --exclude=id_rsa FAKE .", False),
    ("grep -r FAKE src", False),
    ("grep FAKE a.py", False),                                  # not recursive
    ("rg FAKE", True),                                          # id_rsa (.env is hidden to rg)
    ("rg FAKE -g '!id_rsa'", False),
    ("rg --hidden FAKE -g '!id_rsa'", True),                    # .env read with --hidden
    ("rg FAKE src", False),
    ("findstr /s FAKE *", True),
])
def test_a_recursive_shell_search_over_secret_files_is_not_granted(secrets_ws, command, secret):
    """A shell search names a directory, not the secrets it prints: Mentis asks
    the owner (refuses under `deny`) unless it excludes them; Approve All allows."""
    req = _bash(command, secrets_ws)
    got = decide(req, workspace=secrets_ws, consent=_consent("task", [secrets_ws]))
    hit = any("hold secrets" in o for o in got.op.outside)
    assert hit is secret, (command, got.op.outside)
    if secret:
        assert got.outcome == "ask"
        assert decide(req, workspace=secrets_ws,
                      consent=_consent("deny", [secrets_ws])).outcome == "deny"
        assert decide(req, workspace=secrets_ws,
                      consent=_consent("all", [secrets_ws])).outcome == "allow"


def _protected_answer(command, ws):
    """'secret' / 'unclear' / None for one command under task consent, and
    that a protected answer is asked (task), refused (deny), allowed (all)."""
    req = _bash(command, ws)
    got = decide(req, workspace=ws, consent=_consent("task", [ws]))
    if any("hold secrets" in o for o in got.op.outside):
        kind = "secret"
    elif any("cannot read with confidence" in o for o in got.op.outside):
        kind = "unclear"
    else:
        return None, got
    assert got.outcome == "ask", (command, got.op.outside)
    assert decide(req, workspace=ws, consent=_consent("deny", [ws])).outcome == "deny"
    assert decide(req, workspace=ws, consent=_consent("all", [ws])).outcome == "allow"
    return kind, got


@pytest.mark.parametrize("command", [
    "grep -r -m 5 FAKE",              # review H1: the pattern was taken as the path
    "grep -rm5 FAKE .",
    "grep -r -A 2 FAKE .",
    "grep -r -B2 -C 3 FAKE",
    "grep -r --max-count 5 FAKE",
    "grep -r --max-count=5 FAKE .",
    "grep -r -e FAKE",
    "grep -r --regexp FAKE --context 1",
    "grep FAKE -r",
    "rg --hidden -A 2 FAKE",          # review H1
    "rg -m 3 FAKE",
    "rg -C 2 FAKE .",
    "rg --max-count 1 FAKE",
    "rg -e FAKE",
])
def test_a_search_whose_options_take_values_still_finds_the_secrets(secrets_ws, command):
    """Review H1: options that take a value (-m 5, -A 2, ...) are read with
    their value, so the real directory is checked (no path = the cwd)."""
    kind, got = _protected_answer(command, secrets_ws)
    assert kind == "secret", (command, got.op.outside)


@pytest.mark.parametrize("command", [
    "grep -r --frobnicate FAKE src",   # an option Mentis does not know
    "grep -r --co FAKE src",           # ambiguous prefix (--count/--context/--colour)
    "grep -r FAKE nosuchdir",          # a target that does not exist
    "grep -r FAKE $DIR",               # not literal
    "rg -K FAKE src",
    "rg --frobnicate FAKE src",
    "rg FAKE nosuchdir",
    "findstr /s /z FAKE *.py",
    "grep -r --exclude-from=skip.txt FAKE src",
])
def test_a_search_mentis_cannot_read_confidently_is_answered_as_protected(secrets_ws, command):
    kind, got = _protected_answer(command, secrets_ws)
    assert kind == "unclear", (command, got.op.outside)


@pytest.mark.parametrize("command,secret", [
    # review M2: limits on what is searched are honoured ...
    ("grep -r --include=*.py FAKE .", False),
    ("grep -r --include='*.py' FAKE", False),
    ("grep -rn --include *.py FAKE .", False),
    ("grep -r --exclude-dir=sub --exclude=.env FAKE .", False),
    ("grep -r --max-c=5 --include=*.py FAKE .", False),   # unique prefix resolved
    ("rg -t py FAKE", False),
    ("rg --hidden --type py FAKE", False),
    ("rg -tpy -uu FAKE", False),
    ("rg -g '*.py' FAKE", False),
    ("rg --hidden -g '*.py' FAKE .", False),
    ("rg --hidden -g '!.env' -g '!id_rsa' FAKE", False),
    ("rg --hidden -g '!sub' -g '!.env' FAKE", False),
    # ... and a limit that still lets a secret through does not hide it
    ("grep -r --include=*.py --include=.env FAKE .", True),
    ("grep -r --exclude=.env --include=.env FAKE .", True),   # the last match wins
    ("grep -r --exclude-dir=sub FAKE .", True),               # .env
    ("rg -T py --hidden FAKE", True),
    ("rg -g '*.py' -g '.env' FAKE", True),                    # a glob names a hidden file
    ("rg --hidden -g '!.env' FAKE", True),                    # id_rsa
    ("rg -t py -g '*' FAKE", True),                           # the glob decides first
    ("rg -t nosuchtype FAKE", True),                          # unknown type: everything counts
    ("findstr /s FAKE .env", True),
    ("findstr /s FAKE id_rsa", True),
])
def test_a_search_restricted_to_ordinary_files_is_not_an_owner_question(secrets_ws, command,
                                                                       secret):
    kind, got = _protected_answer(command, secrets_ws)
    if secret:
        assert kind == "secret", (command, got.op.outside)
    else:
        assert kind is None, (command, got.op.outside)
        assert got.outcome == "allow", (command, got.op.outside)


@pytest.mark.parametrize("command,secret", [
    ("findstr /s FAKE *.py", False),
    ("findstr /s /c:FAKE *.py", False),
    (r"findstr /s /i FAKE src\*", False),
    ("findstr /si FAKE *", True),
    ("findstr /s FAKE .env", True),
    ("findstr /s /d:sub;src FAKE *", True),
])
def test_findstr_masks_limit_what_is_searched(secrets_ws, command, secret):
    """findstr is not a program the classifier grants (always asked), but its
    masks still decide whether the question names a secret (review M2)."""
    from mentis.operations import tokens
    from mentis.secret_search import search
    got = search(tokens(command), secrets_ws)
    assert got is not None and got.unclear is None, command
    assert bool(got.secrets) is secret, (command, got.secrets)


def test_dependency_trees_do_not_make_ordinary_search_an_owner_question(tmp_path):
    ws = tmp_path / "repo"
    (ws / ".venv" / "lib").mkdir(parents=True)
    (ws / ".venv" / "lib" / "cacert.pem").write_text("x")
    (ws / "node_modules" / "x").mkdir(parents=True)
    (ws / "node_modules" / "x" / "test.key").write_text("x")
    (ws / "a.py").write_text("FAKE")
    got = decide(_bash("grep -rn FAKE .", str(ws)), workspace=str(ws),
                 consent=_consent("task", [str(ws)]))
    assert got.outcome == "allow"


def test_codex_enforcement_words_say_what_was_measured():
    """Round 2 D: under codex the consent's categories are not enforced inside the sandbox,
    and who answers a request to leave it is what MARS reported: Codex's own reviewer (a
    MARS that runs codex in `agent` mode, or says nothing) or Mentis (`escalations_to`)."""
    old = enforcement({"enforced_by": "sandbox+client"})
    assert "whatever kinds of operation the consent names" in old["words"]
    assert "may approve it without Mentis or the owner" in old["words"]
    assert old["escalations_to"] == "runtime-reviewer"
    new = enforcement({"enforced_by": "sandbox+client", "runtime_mode": "workspace-write",
                       "escalations_to": "client"})
    assert "reaches Mentis, which decides it by this consent" in new["words"]
    assert "without Mentis or the owner" not in new["words"] and new["escalations_to"] == "client"
