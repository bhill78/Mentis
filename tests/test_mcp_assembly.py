"""O8: a dispatched run states its MCP configuration, and records what it was given.

Pinned on the Mentis side (MARS's assembly is tested in MARS, `mcp_assembly`):

  * the owner's policy file (`<brain>/mcp-policy.json`): absent is "allow every
    non-Mentis user server"; a malformed one fails closed and says why;
  * every RunSpec carries the statement: the intended Brain (this record),
    server (where this process answers) and execution (the run), the policy,
    and the Mentis server addresses;
  * MARS's `mars/mcp` answer is kept in the run's evidence -- given, excluded
    with reason, unavailable -- and a MARS that does not answer is said so;
  * the run is told the servers it actually has and those it does not, and why.
"""

from __future__ import annotations

import json
import time

import pytest

from mentis.execution import RunResult
from mentis.execution import mcp_policy as P
from mentis.execution.tooling import effective, render
from tests._loop import a_conversation, say, world  # noqa: F401

REPORT = {
    "backend": "codex", "enforcement": "disabled-by-name",
    "given": [{"name": "mentis", "source": "client", "mentis": "intended"},
              {"name": "decoy_echo", "source": "user", "scope": "user",
               "file": "C:\\h\\.codex\\config.toml", "how": "runtime-loads"}],
    "excluded": [{"name": "mentis", "source": "user", "scope": "user", "file": "f",
                  "reason": "other-brain", "detail": "it reaches Brain L", "replaced_by_client": True},
                 {"name": "brain2", "source": "user", "scope": "user", "file": "f",
                  "reason": "other-brain", "detail": "it reaches Brain D"}],
    "unavailable": [{"name": "off", "source": "user", "scope": "user", "file": "f",
                     "why": "enabled = false in Codex's config.toml"}],
}


def test_no_policy_file_allows_every_non_mentis_user_server(tmp_path):
    policy, why = P.read_policy(str(tmp_path))
    assert why is None
    assert policy["user"] == {"default": "allow"}
    assert "127.0.0.1:8760" in policy["mentis_servers"]


def test_policy_file_is_read(tmp_path):
    (tmp_path / P.FILE).write_text(json.dumps({
        "format": P.FORMAT, "version": 1,
        "user_servers": {"default": "deny", "allow": ["docs", "codex:search"],
                         "other_brains": ["archive"]},
        "mentis_servers": ["127.0.0.1:9000"]}), encoding="utf-8")
    policy, why = P.read_policy(str(tmp_path))
    assert why is None
    assert policy == {"user": {"default": "deny", "allow": ["docs", "codex:search"],
                               "other_brains": ["archive"]},
                      "mentis_servers": [*P.DEFAULT_MENTIS_SERVERS, "127.0.0.1:9000"]}


def test_the_owners_mentis_servers_add_to_the_defaults(tmp_path):
    """Review L2: naming another Mentis address never drops this installation's own."""
    (tmp_path / P.FILE).write_text(json.dumps({
        "format": P.FORMAT, "version": 1,
        "mentis_servers": ["127.0.0.1:9000", "127.0.0.1:8760"]}), encoding="utf-8")
    policy, why = P.read_policy(str(tmp_path))
    assert why is None
    assert set(P.DEFAULT_MENTIS_SERVERS) <= set(policy["mentis_servers"])
    assert "127.0.0.1:9000" in policy["mentis_servers"]
    assert len(policy["mentis_servers"]) == len(set(policy["mentis_servers"]))


@pytest.mark.parametrize("text", [
    "{not json",
    json.dumps({"format": "other", "version": 1}),
    json.dumps({"format": P.FORMAT, "version": 1, "user_servers": {"default": "maybe"}}),
    json.dumps({"format": P.FORMAT, "version": 1, "user_servers": {"deny": "x"}}),
    json.dumps({"format": P.FORMAT, "version": 1, "extra": 1}),
])
def test_an_unreadable_policy_fails_closed_and_says_why(tmp_path, text):
    (tmp_path / P.FILE).write_text(text, encoding="utf-8")
    policy, why = P.read_policy(str(tmp_path))
    assert why
    assert policy["user"] == {"default": "deny"}
    stated = P.statement(brain=str(tmp_path), server=None, execution="inst-1")
    assert stated["user"] == {"default": "deny"}
    assert stated["policy_unreadable"]


def test_statement_names_the_intended_brain_server_and_execution(tmp_path):
    stated = P.statement(brain=str(tmp_path), server="http://127.0.0.1:8831", execution="inst-9")
    assert stated == {"user": {"default": "allow"},
                      "intended": {"brain": str(tmp_path), "server": "http://127.0.0.1:8831",
                                   "execution": "inst-9"},
                      "mentis_servers": list(P.DEFAULT_MENTIS_SERVERS)}


def test_summary_keeps_given_excluded_and_unavailable():
    s = P.summary(REPORT, {"user": {}})
    assert s["reported"] is True and s["enforcement"] == "disabled-by-name"
    assert [g["name"] for g in s["given"]] == ["mentis", "decoy_echo"]
    assert s["excluded"][1] == {"name": "brain2", "scope": "user", "file": "f",
                                "reason": "other-brain", "detail": "it reaches Brain D"}
    assert s["unavailable"][0]["why"].startswith("enabled = false")
    # a MARS that does not answer: said, never read as "nothing was excluded"
    s = P.summary(None, {"user": {}, "policy_unreadable": "bad file"})
    assert s == {"reported": False, "why": "this MARS did not report the session's MCP servers",
                 "policy_unreadable": "bad file"}
    assert P.summary(None, None) is None


def test_the_run_is_told_what_it_has_and_what_it_does_not():
    eff = effective({"mcp": REPORT}, backend="codex", workspace="C:\\repo",
                    mcp_servers=[{"name": "mentis"}])
    assert eff["mcp_servers"] == ["decoy_echo", "mentis"]
    assert eff["mcp_not_given"] == [
        {"name": "brain2", "why": "another Mentis Brain"},
        {"name": "off", "why": "enabled = false in Codex's config.toml"}]
    text = render(eff)
    assert eff["mcp_notes"] == []
    assert "- MCP servers: decoy_echo, mentis" in text
    assert "- MCP server not available here: brain2 (another Mentis Brain)" in text
    # a server given but whose tools the runtime refuses: said
    noted = {**REPORT, "given": REPORT["given"] + [{"name": "x", "note": "agy refuses its tools"}]}
    eff = effective({"mcp": noted}, backend="antigravity", workspace="C:\repo")
    assert "- MCP server x: agy refuses its tools" in render(eff)
    assert P.summary(noted, {})["given"][-1] == {"name": "x", "note": "agy refuses its tools"}
    # without MARS's answer, the run's own servers as Mentis asked for them
    eff = effective({}, backend="codex", workspace="C:\\repo", mcp_servers=[{"name": "mentis"}])
    assert eff["mcp_servers"] == ["mentis"] and eff["mcp_not_given"] == []


@pytest.fixture()
def synchronous(world, monkeypatch):
    import mentis.web as web
    from mentis.web import dispatch as D
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: D.dispatch(st, **kw))
    return world


def test_a_dispatched_run_states_its_mcp_and_records_what_it_was_given(synchronous):
    world = synchronous
    st, cv = world["state"], world["cv"]
    ex = st.agents.execution

    def answer(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done",
                         mcp=P.summary(REPORT, spec.mcp), started_at=now, finished_at=now)

    ex.script = {"codex": answer}
    ada = cv.create_participant("@Ada", about="an agent")
    cid = a_conversation(world)
    say(world, cid, "please look", action="ask-participant",
        dispatch=[{"participant": ada, "work": "please look", "runtime": "codex"}])
    spec = ex.performed[0]
    assert spec.mcp["intended"] == {"brain": st.path, "server": st.agents._answers_at,
                                    "execution": spec.run_id} \
        if st.agents._answers_at else {"brain": st.path, "execution": spec.run_id}
    assert spec.mcp["user"] == {"default": "allow"}
    assert f"serve(r'{st.path}'" in spec.mcp_servers[0]["args"][2]
    returned = [a for a in cv.history(execution=spec.run_id) if a["act"] == "result-returned"]
    mcp = returned[0]["detail"]["runtime_evidence"]["mcp"]
    assert mcp["reported"] is True
    assert [(e["name"], e["reason"]) for e in mcp["excluded"]] == [
        ("mentis", "other-brain"), ("brain2", "other-brain")]
