"""Execution Mode (owner decision 2026-11-11), replacing the interim execution policy.

`mentis.execution.mode`: the owner selects `sandboxed` / `unrestricted-host` / `container` on a
dispatch, independent of run consent (Permission Mode). It is recorded on the request it
creates, kept by the owner's continuations of it, never inherited by a request an agent
records (which may state only `sandboxed`); unrestricted host execution carries the owner's
acknowledgement of the current notice; a mode the runtime's contract does not support is
refused, never substituted. A run's start act records what it executes in; MARS is sent
`execution_mode` (and, under unrestricted-host, none of the consent options); the run is told
the truth about it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from mentis.execution import mode as M
from mentis.execution.tooling import effective, render
from mentis.operational import consent as C
from mentis.web.permissions import enforcement, runtime_options

from tests._loop import _coordinator, a_conversation, say, world  # noqa: F401
from tests.test_run_consent import (_call, _carried_with_a_result, _contract_of, _request,
                                    ws)  # noqa: F401

HOST = {"execution_mode": "unrestricted-host", "execution_mode_ack": M.NOTICE_ID}


def _owner(world):
    from mentis.conversation.owner import _owner as o
    return o(world["cv"])


@pytest.fixture()
def contracts(world, monkeypatch):
    """The service answers each runtime's contract from the offline profiles (MARS's own)."""
    monkeypatch.setattr(world["state"].agents, "runtime_contract",
                        lambda rt, holds=None: _contract_of(rt), raising=False)
    return world


def _post(world, cid, spec, **body):
    payload = {"author": body.pop("author", world["who"]["@brian"]), "text": "build it",
               "action": "ask-participant", "dispatch": [spec], **body}
    req = urllib.request.Request(
        world["base"] + f"/api/conversations/{cid}/turns", method="POST",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _detail(world, exp):
    return (world["cv"]._act(exp).get("detail") or {}).get("execution_mode")


# -- the dispatch spec ----------------------------------------------------------------

def test_the_owners_selection_is_recorded_on_the_request(contracts, ws):
    world = contracts
    cid = a_conversation(world, "Modes")
    code, out = _post(world, cid, {"participant": world["steward"], "runtime": "codex", **HOST})
    assert code == 200, out
    exp = out["expectations"][0]
    assert _detail(world, exp) == {"mode": "unrestricted-host", "ack": M.NOTICE_ID,
                                   "selected_by": _owner(world)}
    got = M.of_request(world["cv"], exp)
    assert got["mode"] == "unrestricted-host" and got["request"] == exp
    # independent of consent: none was given, and none was made
    assert C.of_request(world["cv"], exp)["source"] == "none"
    # sandboxed needs no acknowledgement
    code, out = _post(world, cid, {"participant": world["steward"], "runtime": "antigravity",
                                   "execution_mode": "sandboxed"})
    assert code == 200 and _detail(world, out["expectations"][0])["mode"] == "sandboxed"
    # absent: nothing recorded, the runtime's default
    code, out = _post(world, cid, {"participant": world["steward"], "runtime": "codex"})
    assert code == 200 and _detail(world, out["expectations"][0]) is None


@pytest.mark.parametrize("ack", [None, "unrestricted-host/v0", ""])
def test_unacknowledged_unrestricted_host_is_refused_before_anything_is_written(contracts, ws, ack):
    world = contracts
    cid = a_conversation(world, "Ack")
    before = len(world["cv"]._c.operational(act="expectation-recorded"))
    spec = {"participant": world["steward"], "runtime": "codex",
            "execution_mode": "unrestricted-host",
            **({"execution_mode_ack": ack} if ack is not None else {})}
    code, out = _post(world, cid, spec)
    assert code == 400 and out["kind"] == "ExecutionModeNotAcknowledged", out
    assert len(world["cv"]._c.operational(act="expectation-recorded")) == before


@pytest.mark.parametrize("runtime,mode", [("claude", "sandboxed"), ("local", "unrestricted-host"),
                                          ("kimi-k3", "sandboxed"), ("codex", "container"),
                                          ("codex", "yolo")])
def test_a_mode_the_runtime_does_not_support_is_refused(contracts, ws, runtime, mode):
    world = contracts
    cid = a_conversation(world, "Unsupported")
    spec = {"participant": world["steward"], "runtime": runtime, "execution_mode": mode,
            "execution_mode_ack": M.NOTICE_ID}
    code, out = _post(world, cid, spec)
    assert code == 400 and out["kind"] == "ExecutionModeUnsupported", out
    assert out["why"]


def test_only_the_owner_chooses_wider_than_sandboxed(contracts, ws):
    world = contracts
    cid = a_conversation(world, "Agent")
    code, out = _post(world, cid, {"participant": world["who"]["@brian"], "runtime": "codex",
                                   **HOST}, author=world["steward"])
    assert code == 400 and out["kind"] == "ExecutionModeNotPermitted", out


# -- inheritance -------------------------------------------------------------------------

def test_an_owners_continuation_keeps_it_and_may_change_it(contracts, ws):
    world = contracts
    cid = a_conversation(world)
    ada, first, answered = _carried_with_a_result(world, cid, runtime="codex", **HOST)
    assert M.of_request(world["cv"], first)["mode"] == "unrestricted-host"
    cont = say(world, cid, "carry on", replies_to=answered, action="ask-participant",
               dispatch=[{"participant": ada, "work": "carry on"}])["expectations"][0]
    assert world["cv"]._act(cont)["caused_by"] == first
    got = M.of_request(world["cv"], cont)
    assert got["mode"] == "unrestricted-host" and got["request"] == first
    narrowed = say(world, cid, "carry on", replies_to=answered, action="ask-participant",
                   dispatch=[{"participant": ada, "work": "carry on",
                              "execution_mode": "sandboxed"}])["expectations"][0]
    assert M.of_request(world["cv"], narrowed)["mode"] == "sandboxed"


def test_an_agents_request_never_inherits_and_never_states_wider(contracts, ws):
    world = contracts
    cv = world["cv"]
    cid = a_conversation(world, "Delegated")
    turn, parent = _request(world, cid)
    cv_parent = cv._act(parent)
    assert cv_parent["actor"] == _owner(world)
    # the owner's selection on the parent (as posting records it)
    turn2 = say(world, cid, "do it")["turn"]
    parent = cv.expect(turn2, of=world["steward"], kind="result", by=_owner(world),
                       detail={"execution_mode": {"mode": "unrestricted-host",
                                                  "ack": M.NOTICE_ID,
                                                  "selected_by": _owner(world)}})
    _, child = _request(world, cid, by=world["steward"], caused_by=parent)
    assert M.of_request(cv, parent)["mode"] == "unrestricted-host"
    assert M.of_request(cv, child) is None                     # never inherited
    # an agent's own record of anything wider is never read
    forged = cv.expect(turn2, of=world["steward"], kind="result", by=world["steward"],
                       caused_by=parent, detail={"execution_mode": {"mode": "unrestricted-host"}})
    assert M.of_request(cv, forged) is None
    stated = cv.expect(turn2, of=world["steward"], kind="result", by=world["steward"],
                       caused_by=parent, detail={"execution_mode": {"mode": "sandboxed"}})
    assert M.of_request(cv, stated)["mode"] == "sandboxed"


def test_a_delegation_may_state_only_sandboxed(contracts, ws):
    from mentis.web import _surface
    from mentis.worker import NotPermitted, _operate
    world = contracts
    cid = a_conversation(world)
    _coach, parent, grant = _coordinator(world, cid)
    builder = world["cv"].create_participant("@Builder")
    world["cv"].join(builder, cid, attributed_to=_owner(world))
    for wider in ("unrestricted-host", "container"):
        with pytest.raises(NotPermitted):
            _operate(_surface(world["state"]), "delegate",
                     {"participant": builder, "work": "build it", "execution_mode": wider}, grant)
    out = _operate(_surface(world["state"]), "delegate",
                   {"participant": builder, "work": "build it", "execution_mode": "sandboxed"}, grant)
    assert _detail(world, out["expectation"])["mode"] == "sandboxed"
    plain = _operate(_surface(world["state"]), "delegate",
                     {"participant": builder, "work": "build more"}, grant)
    assert _detail(world, plain["expectation"]) is None


# -- what the run is given ---------------------------------------------------------------

def _started(world, ws, runtime, *, selected=None, consent=None):
    cv = world["cv"]
    cid = a_conversation(world, "Run")
    turn = say(world, cid, "work")["turn"]
    exp = cv.expect(turn, of=world["steward"], kind="result", by=_owner(world),
                    detail={**({"execution_mode": selected} if selected else {}),
                            **({"consent": consent} if consent else {})} or None)
    decided = M.resolve(cv, exp, runtime=runtime, contract=_contract_of(runtime))
    run = cv.record_act(actor=world["steward"], act="execution-started", conversation=cid,
                        turn=turn, execution="inst-m", runtime=runtime, caused_by=exp,
                        because="test", detail={"workspace": ws["repo"],
                                                "execution_mode": decided})
    return run, decided


def test_resolve_records_what_the_run_executes_in(contracts, ws):
    world = contracts
    sel = {"mode": "unrestricted-host", "ack": M.NOTICE_ID, "selected_by": _owner(world)}
    run, got = _started(world, ws, "codex", selected=sel)
    assert got["requested"] == got["effective"] == "unrestricted-host"
    assert got["source"] == "selected" and got["isolation"] == "host"
    assert "agent-full-access" in got["mechanism"]
    assert got["ack_act"] == world["cv"]._act(run)["caused_by"]
    _, default = _started(world, ws, "codex")
    assert (default["requested"], default["effective"], default["source"], default["isolation"]) == (
        None, "sandboxed", "runtime-default", "sandbox")
    with pytest.raises(M.Unsupported):
        _started(world, ws, "claude", selected={"mode": "sandboxed", "ack": None,
                                                 "selected_by": _owner(world)})


@pytest.mark.parametrize("runtime", ["codex", "antigravity"])
def test_unrestricted_host_sends_the_mode_and_no_consent_options(contracts, ws, runtime):
    world = contracts
    task = C.consent_value({"mode": "task", "workspaces": [ws["repo"]]})
    sel = {"mode": "unrestricted-host", "ack": M.NOTICE_ID, "selected_by": _owner(world)}
    run, _ = _started(world, ws, runtime, selected=sel, consent=task)
    assert runtime_options(world["cv"], run, ws["repo"], runtime,
                           _contract_of(runtime)) == {"execution_mode": "unrestricted-host"}


def test_sandboxed_and_default_keep_the_consent_options_exactly(contracts, ws):
    world = contracts
    task = C.consent_value({"mode": "task", "workspaces": [ws["repo"]]})
    run, _ = _started(world, ws, "codex", consent=task)
    assert runtime_options(world["cv"], run, ws["repo"], "codex",
                           _contract_of("codex")) == {"escalations": "client"}
    run, _ = _started(world, ws, "antigravity", consent=task)
    assert runtime_options(world["cv"], run, ws["repo"], "antigravity",
                           _contract_of("antigravity")) == {"allow": ["command(*)"]}
    sb = {"mode": "sandboxed", "ack": None, "selected_by": _owner(world)}
    run, _ = _started(world, ws, "codex", selected=sb, consent=task)
    assert runtime_options(world["cv"], run, ws["repo"], "codex", _contract_of("codex")) == {
        "execution_mode": "sandboxed", "escalations": "client"}
    run, _ = _started(world, ws, "antigravity", selected=sb, consent=task)
    assert runtime_options(world["cv"], run, ws["repo"], "antigravity",
                           _contract_of("antigravity")) == {"execution_mode": "sandboxed",
                                                            "allow": ["command(*)"]}


def test_the_run_is_told_host_execution_and_its_boundary_never_a_sandbox(ws):
    decided = {"requested": "unrestricted-host", "effective": "unrestricted-host",
               "source": "selected", "isolation": "host"}
    meta = {"sandbox": {"permissions": "backend-mode", "enforced_by": "none", "isolation": "host",
                        "execution_mode": {"name": "unrestricted-host", "isolation": "host"}}}
    eff = effective(meta, backend="codex", workspace=ws["repo"],
                    consent={"mode": "task", "categories": list(C.DEFAULT_CATEGORIES)},
                    enforcement="sandbox+runtime-reviewer", execution_mode=decided)
    text = render(eff)
    assert eff["execution_mode"]["applied"] is True and eff["execution_mode"]["container"] is False
    assert "not in a sandbox or a container" in text and "Deployments" in text
    assert "governance" in text and "Mentis tools" in text
    # installation-neutral (owner, 2026-11-11)
    assert "DAY-TO-DAY" not in text and "does not imply a push, merge or deployment" in text
    assert "- Sandbox:" not in text and "inside its sandbox" not in text
    # selected but not reported applied by MARS: said so, and nothing more is claimed
    eff2 = effective({"sandbox": {"permissions": "none", "enforced_by": "sandbox"}},
                     backend="antigravity", workspace=ws["repo"], execution_mode=decided)
    assert eff2["execution_mode"]["applied"] is False
    assert "did not report applying it" in render(eff2)


def test_enforcement_reports_host_execution_not_isolation():
    got = enforcement({"mode": "task", "enforced_by": "none",
                       "execution_mode": {"name": "unrestricted-host", "isolation": "host",
                                          "container": False, "sandbox": "off",
                                          "mechanism": "codex-acp session mode agent-full-access"}})
    assert got["enforced"] is False and got["isolation"] == "host"
    assert got["execution_mode"] == "unrestricted-host"
    assert "not container isolation" in got["words"] and "does not enforce" in got["words"]
    # claude under host execution still forwards: the ordinary client words
    claude = enforcement({"mode": "task", "enforced_by": "client",
                          "execution_mode": {"name": "unrestricted-host", "isolation": "host"}})
    assert claude["enforced"] is True and "reaches Mentis" in claude["words"]


def test_asks_follows_the_contract_not_the_name():
    assert M.asks(_contract_of("claude"), "unrestricted-host") is True
    assert M.asks(_contract_of("codex"), "unrestricted-host") is False
    assert M.asks(_contract_of("antigravity"), "unrestricted-host") is False
    assert M.asks(_contract_of("codex"), "sandboxed") is True


# -- the HTTP surface ----------------------------------------------------------------------

def test_the_catalogue_says_each_runtimes_modes_and_the_notice(contracts):
    got = _call(contracts, "/api/execution")
    assert got["unrestricted_host_notice"]["id"] == M.NOTICE_ID
    text = got["unrestricted_host_notice"]["text"]
    for words in ("files outside its workspace", "local credentials", "network services",
                  "local processes"):
        assert words in text
    for row in got["runtimes"]:
        modes = row["execution_modes"]
        assert set(modes["modes"]) == {"sandboxed", "unrestricted-host", "container"}
        assert modes["modes"]["container"]["state"] == "unsupported"
        for m in modes["modes"].values():
            assert set(m) >= {"state", "mechanism", "permission_enforcement", "why"}


def test_a_runs_consent_answer_says_its_execution(contracts, ws):
    world = contracts
    sel = {"mode": "unrestricted-host", "ack": M.NOTICE_ID, "selected_by": _owner(world)}
    run, _ = _started(world, ws, "codex", selected=sel)
    got = _call(world, f"/api/runs/{run}/consent")["execution"]
    exp = world["cv"]._act(run)["caused_by"]
    assert got["mode"] == "unrestricted-host" and got["source"] == "selected"
    assert got["isolation"] == "host" and "agent-full-access" in got["mechanism"]
    assert got["acknowledged"]["act"] == exp and got["acknowledged"]["at"]
    assert got["applied_by_mars"] is False                     # no MARS report yet
    assert "not enforced" in got["permission_enforcement"]
    run2, _ = _started(world, ws, "antigravity")
    plain = _call(world, f"/api/runs/{run2}/consent")["execution"]
    assert (plain["mode"], plain["source"], plain["acknowledged"]) == ("sandboxed", "runtime-default",
                                                                      None)


def test_the_superseded_policy_route_is_gone(world):
    req = urllib.request.Request(world["base"] + "/api/execution-policy",
                                 headers={"X-Mentis-Client": "1"})
    with pytest.raises(urllib.error.HTTPError) as got:
        urllib.request.urlopen(req)
    assert got.value.code == 404


# -- the real dispatch, on the offline conformance rig -------------------------------------

def _rig_ask(rig, cid, who, **spec):
    out = rig.post(f"/api/conversations/{cid}/turns",
                   {"author": rig.owner, "text": "build it", "action": "ask-participant",
                    "dispatch": [{"participant": who, "work": "build it",
                                  "runtime": rig.runtime, **spec}]})
    return out["expectations"][0]


def test_a_dispatched_run_records_and_sends_its_mode(tmp_path):
    from mentis.web import dispatch as D
    from tests.conformance_runtime.profiles import PROFILES
    from tests.conformance_runtime.rig import Rig
    rig = Rig("codex", root=tmp_path, profile=PROFILES["codex"])
    try:
        import mentis.web as web
        captured = []
        orig = web.dispatch_soon
        web.dispatch_soon = lambda st, **kw: captured.append(kw)
        try:
            cid = rig.conversation("mode")
            who = rig.participant(cid, "@Dev")
            exp = _rig_ask(rig, cid, who, **HOST)
        finally:
            web.dispatch_soon = orig
        D.dispatch(rig.state, **captured[-1])
        start = rig.runs(exp)[0]
        rec = start["detail"]["execution_mode"]
        assert (rec["requested"], rec["effective"], rec["source"], rec["isolation"]) == (
            "unrestricted-host", "unrestricted-host", "selected", "host")
        assert rec["ack_act"] == exp
        spec = rig.execution.performed[-1]
        assert spec.options.get("execution_mode") == "unrestricted-host"
        assert "escalations" not in spec.options
    finally:
        rig.close()


def test_a_runtime_chosen_later_that_lacks_the_mode_refuses_the_run(tmp_path):
    """No runtime named at the post: the mode is checked on the runtime that would run it,
    and the run is refused before it starts -- never another mode."""
    from mentis.web import dispatch as D
    from tests.conformance_runtime.profiles import PROFILES
    from tests.conformance_runtime.rig import Rig
    rig = Rig("claude", root=tmp_path, profile=PROFILES["claude"])
    try:
        cid = rig.conversation("refused")
        who = rig.participant(cid, "@Dev")
        turn = rig.cv.say(cid, rig.owner, [{"type": "text", "text": "do it"}])
        exp = rig.cv.expect(turn, of=who, kind="result", by=rig.owner,
                            detail={"execution_mode": {"mode": "sandboxed", "ack": None,
                                                       "selected_by": rig.owner}})
        got = D.dispatch(rig.state, conversation=cid, turn=turn, participant=who, work="do it",
                         expectation=exp, runtime="claude")
        assert got["ok"] is False and got["before_execution_started"]
        assert not rig.runs(exp) and not rig.execution.performed
        failed = rig.failures(exp)[0]
        assert failed["detail"]["stage"] == "execution-mode"
        assert "does not support execution mode sandboxed" in failed["because"]
    finally:
        rig.close()


def test_host_by_a_runtimes_default_on_agent_work_is_said(contracts):
    """Round-3 final review S1: work an agent delegates runs in its runtime's default; where
    that default is host execution (claude), the run's record says it was not the owner's
    choice. Owner-recorded work carries no such note."""
    world = contracts
    cv = world["cv"]
    cid = a_conversation(world, "Delegated to a host runtime")
    turn, parent = _request(world, cid)
    _, child = _request(world, cid, by=world["steward"], caused_by=parent)
    got = M.resolve(cv, child, runtime="claude", contract=_contract_of("claude"))
    assert got["source"] == "runtime-default" and got["effective"] == "unrestricted-host"
    assert "not selected by the owner" in got["host_by_runtime_default"]
    own = M.resolve(cv, parent, runtime="claude", contract=_contract_of("claude"))
    assert "host_by_runtime_default" not in own
    sandboxed = M.resolve(cv, child, runtime="codex", contract=_contract_of("codex"))
    assert "host_by_runtime_default" not in sandboxed
