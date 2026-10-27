"""Agent access through the existing bridge: four more reads, and session
grants for runtimes Mentis has no adapter for.

WHAT MUST HOLD, against a real HTTP server and the real `/api/worker` door:
  - `governed`, `owner_decisions`, `capabilities` and `brief` are READS: in
    `READS`, so every scope -- a dispatched run, a hand-started session, a
    Quick Ask -- holds them through `permitted()`, and nothing else admits them;
  - each answers what the function it wraps answers: the register
    `/api/governed` serves, `Conversations.owner_decisions`,
    `api.capability_names()`, and `Conversations.orientation` composed for
    the CALLING Participant -- the grant's, never an argument;
  - a session on a runtime with no adapter (`local`, `kimi`) is granted
    exactly what a `claude` session is, its label is only written on its
    acts, and a label that breaks the name rule or reads as a runtime Mentis
    runs is refused.
"""

from __future__ import annotations

import pytest

from mentis.worker import (ACT_TOOLS, CAPABILITY_HEADER, READS,
                           SESSION_PARTICIPANT, SESSION_ROUTE, SESSION_SCOPE,
                           TOOLS, TRANSIENT_SCOPE, permitted,
                           session_label_problem)
from mentis.conversation import text
from tests.test_manual_session import _mcp, _post, world  # noqa: F401

NEW_READS = ("governed", "owner_decisions", "capabilities", "brief")


def _session(world, runtime="claude"):
    st, url = world["st"], world["url"]
    status, grant = _post(url + SESSION_ROUTE,
                          {"corpus": st.path, "runtime": runtime},
                          {"X-Mentis-Client": "1"})
    assert status == 200, grant

    def op(_op, **args):
        return _post(url + "/api/worker",
                     {"corpus": st.path, "op": _op, "args": args},
                     {CAPABILITY_HEADER: grant["grant"]})
    return grant, op


# -- the reads ---------------------------------------------------------------

def test_new_reads_are_reads_for_every_scope():
    assert set(NEW_READS) <= set(READS)
    for scope in ("worker", "organising", SESSION_SCOPE, TRANSIENT_SCOPE,
                  "unrecognised"):
        assert set(NEW_READS) <= set(permitted(scope)), scope
    defined = {t["name"] for t in TOOLS}
    assert set(NEW_READS) <= defined
    assert not set(NEW_READS) & {t["name"] for t in ACT_TOOLS}
    for t in TOOLS:
        if t["name"] in NEW_READS:
            assert t["description"] and t["inputSchema"]["type"] == "object"


def test_governed_is_the_register_the_ui_reads(world):
    st = world["st"]
    _, op = _session(world)
    status, proposed = op("propose_material", kind="rule",
                          body={"text": "Zebra crossings need a lollipop."})
    assert status == 200, proposed
    status, got = op("governed", q="zebra lollipop")
    assert status == 200, got
    from mentis.conversation.register import governed
    from mentis.web import _surface
    assert got == governed(_surface(st).brain, q="zebra lollipop", limit=40)
    assert proposed["entry"] in repr(got)
    # A bad filter is the register's own answer, not a malfunction.
    status, bad = op("governed", state="nonsense")
    assert status == 200 and "error" in bad and "groups" in bad
    status, bad = op("governed", limit=0)
    assert status == 200 and "error" in bad


def test_owner_decisions_lists_what_was_asked(world):
    st, cv = world["st"], world["st"].cv
    cid = cv.open_conversation("Decisions here")
    post = cv.say(cid, world["owner"], [text("Shall we ship?")])
    cv.record_act(actor=world["owner"], act="expectation-recorded",
                  conversation=cid, turn=post,
                  detail={"expects": "decision", "question": "Ship it now?"})
    _, op = _session(world)
    status, got = op("owner_decisions", conversation=cid)
    assert status == 200, got
    assert got["conversation"] == cid
    assert got["open_count"] == 1 and got["answered_count"] == 0
    assert got["open"][0]["question"] == "Ship it now?"
    assert got["open"][0]["post"] == post
    want = cv.owner_decisions(cid)
    assert {k: got[k] for k in want} == want
    # Asked badly, it says so.
    for args in ({}, {"conversation": post}, {"conversation": cid,
                                              "most": "many"},
                 {"conversation": cid, "most": 0}):
        status, said = op("owner_decisions", **args)
        assert status == 200 and said["refused"] is True, (args, said)


def test_capabilities_are_the_names_a_requirement_may_use(world):
    import mentis.api as api
    _, op = _session(world)
    status, got = op("capabilities")
    assert status == 200, got
    assert got["capabilities"] == sorted(api.capability_names())
    assert got["count"] == len(got["capabilities"])
    assert "call_mentis_tools" in got["capabilities"]


def test_brief_is_composed_for_the_caller(world):
    st, cv = world["st"], world["st"].cv
    grant, op = _session(world)
    pid = grant["participant"]
    cid = cv.open_conversation("Briefing room", about="where briefs are read")
    owed = cv.say(cid, world["owner"], [text("Session, please look.")],
                  addressed_to=[pid])
    cv.say(cid, world["owner"], [text("For the owner's own notes.")])
    status, got = op("brief", conversation=cid)
    assert status == 200, got
    assert got["for"] == pid and got["for_alias"] == SESSION_PARTICIPANT
    assert got["conversation"] == cid and got["name"] == "Briefing room"
    assert got["unresolved_for_you"] == [owed]
    mine = cv.orientation(cid, pid)
    assert {k: v for k, v in got.items()
            if k not in ("for", "for_alias")} == mine
    # Naming somebody else is not how the caller is decided.
    status, again = op("brief", conversation=cid, participant=world["owner"])
    assert status == 200 and again["for"] == pid
    for args in ({}, {"conversation": owed}, {"conversation": "  "}):
        status, said = op("brief", **args)
        assert status == 200 and said["refused"] is True, (args, said)


def test_brief_refuses_a_grant_that_names_nobody(world):
    st, url = world["st"], world["url"]
    cid = st.cv.open_conversation("Nobody's")
    token = "t-" + "q" * 20
    st.agents.authority._grants[token] = {
        "instance": "quick", "corpus": st.path, "scope": TRANSIENT_SCOPE,
        "operations": None, "expectation": None, "conversation": None,
        "participant": None, "runtime": "claude"}
    status, said = _post(url + "/api/worker",
                         {"corpus": st.path, "op": "brief",
                          "args": {"conversation": cid}},
                         {CAPABILITY_HEADER: token})
    assert status == 200 and said["refused"] is True, said
    # The other three need nobody, and a Quick Ask holds them.
    for name, args in (("capabilities", {}), ("governed", {}),
                       ("owner_decisions", {"conversation": cid})):
        status, got = _post(url + "/api/worker",
                            {"corpus": st.path, "op": name, "args": args},
                            {CAPABILITY_HEADER: token})
        assert status == 200 and not got.get("refused"), (name, got)


def test_reads_need_a_grant(world):
    st, url = world["st"], world["url"]
    status, _ = _post(url + "/api/worker",
                      {"corpus": st.path, "op": "capabilities", "args": {}},
                      {CAPABILITY_HEADER: "not-a-grant"})
    assert status == 403


# -- sessions on runtimes with no adapter ------------------------------------

@pytest.mark.parametrize("label", ["local", "kimi", "Kimi-K3", "qwen_2"])
def test_a_label_session_gets_what_a_claude_session_gets(world, label):
    st, cv = world["st"], world["st"].cv
    grant, op = _session(world, label)
    known, _ = _session(world, "claude")
    assert grant["scope"] == known["scope"] == SESSION_SCOPE
    assert grant["permits"] == known["permits"] == list(
        permitted(SESSION_SCOPE))
    assert grant["runtime"] == label
    held = [g for g in st.agents.authority._grants.values()
            if g["instance"] == grant["execution"]]
    assert len(held) == 1
    assert held[0]["operations"] == next(
        g for g in st.agents.authority._grants.values()
        if g["instance"] == known["execution"])["operations"]
    # It reads and acts through the same door; the label is on its acts.
    status, got = op("brief", conversation=cv.open_conversation("Lab"))
    assert status == 200 and got["for"] == grant["participant"]
    status, opened = op("open_conversation", name=f"Opened by {label}")
    assert status == 200, opened
    acts = cv.history(execution=grant["execution"])
    assert {a["runtime"] for a in acts
            if a["act"] in ("manual-session-started",
                            "conversation-opened")} == {label}
    # Given back like any session's, and renewed as the same execution.
    status, ended = _post(world["url"] + SESSION_ROUTE + "/end",
                          {"corpus": st.path, "grant": grant["grant"]},
                          {"X-Mentis-Client": "1"})
    assert status == 200 and ended["ended"] == grant["execution"]
    assert [a["runtime"] for a in cv.history(execution=grant["execution"])
            if a["act"] == "manual-session-ended"] == [label]


def test_a_label_session_is_renewed_as_itself(world):
    st = world["st"]
    grant, _ = _session(world, "kimi")
    st.agents.authority._grants.pop(grant["grant"])       # a restart
    status, again = _post(world["url"] + SESSION_ROUTE,
                          {"corpus": st.path, "runtime": "kimi",
                           "continues": grant["execution"]},
                          {"X-Mentis-Client": "1"})
    assert status == 200, again
    assert again["execution"] == grant["execution"]
    # Not as a different runtime.
    st.agents.authority._grants.pop(again["grant"])
    status, _ = _post(world["url"] + SESSION_ROUTE,
                      {"corpus": st.path, "runtime": "local",
                       "continues": grant["execution"]},
                      {"X-Mentis-Client": "1"})
    assert status == 403


def test_a_label_session_over_mcp_is_shown_the_same_tools(world):
    claude = _mcp(world, "claude", [])
    kimi = _mcp(world, "kimi", [("capabilities", {})])
    names = [t["name"] for t in kimi[1]["result"]["tools"]]
    assert names == [t["name"] for t in claude[1]["result"]["tools"]]
    assert set(NEW_READS) <= set(names)
    assert not kimi[2]["result"].get("isError"), kimi[2]


@pytest.mark.parametrize("label", ["", "  ", "kimi k3", "3dlocal", "@kimi",
                                   "kími", "local/model", "a" + "!" * 3,
                                   # reads as a runtime or model family
                                   "Claude", "agy", "codex-cli", "Codex_CLI",
                                   "c1aude", "gpt", "Gemini"])
def test_an_invalid_label_is_refused(world, label):
    st = world["st"]
    before = dict(st.agents.authority._grants)
    status, said = _post(world["url"] + SESSION_ROUTE,
                         {"corpus": st.path, "runtime": label},
                         {"X-Mentis-Client": "1"})
    assert 400 <= status < 500, (label, status, said)
    assert st.agents.authority._grants == before
    assert session_label_problem(label.strip()) is not None


def test_label_rule_accepts_names_and_leaves_adapters_alone():
    for ok in ("local", "kimi", "Kimi-K3", "ollama_llama3", "mars-local"):
        assert session_label_problem(ok) is None, ok
