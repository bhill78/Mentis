"""The interim host development execution policy (owner decision, 2026-11-11).

`mentis.execution.policy`: an authorised development run on a runtime that declares
`host-development-unrestricted` is sent `execution_policy` (and nothing that would
confine or ask), the selection is recorded with the owner act that authorised it, and
nothing else ever gets it: no owner act, a disabled one, another runtime, a run without
owner consent, a consent narrowed below development work, an act by anyone but the owner.
"""

from __future__ import annotations

import json
import os

import pytest

from mentis.execution import policy as P
from mentis.execution.tooling import effective, render
from mentis.operational import consent as C
from mentis.web.permissions import enforcement, runtime_options

from tests._loop import world  # noqa: F401
from tests.test_run_consent import _call, _contract_of, _policy_world, ws  # noqa: F401

DEV = {"mode": "task"}          # default categories: read, edit, test, build, run, git
WORDS = "Owner decision 2026-11-11: temporary unrestricted development execution"


def _owner(world):
    from mentis.conversation.owner import _owner as o
    return o(world["cv"])


def _authorise(world, runtimes=("codex", "antigravity"), enabled=True, actor=None):
    return P.authorise(world["cv"], owner=actor or _owner(world), enabled=enabled,
                       runtimes=runtimes, authorization=WORDS)


def _run(world, ws, given=DEV):
    consent = C.consent_value({**given, "workspaces": [ws["repo"]]}) if given else None
    _, _, _, run, _ = _policy_world(world, ws, consent)
    return run


@pytest.mark.parametrize("runtime", ["codex", "antigravity"])
def test_an_authorised_development_run_gets_the_policy_and_it_is_recorded(world, ws, runtime):
    act = _authorise(world)
    run = _run(world, ws)
    got = runtime_options(world["cv"], run, ws["repo"], runtime, _contract_of(runtime))
    # only the policy: no shell allow rule, no secret deny, no escalation route
    assert got == {"execution_policy": P.HOST_DEV}
    rec = P.of_run(world["cv"], run)
    assert rec["policy"] == P.HOST_DEV and rec["runtime"] == runtime and rec["run"] == run
    assert rec["workspace"] == ws["repo"] and ws["repo"] in rec["workspaces"]
    assert rec["authorization"] == {"act": act, "by": _owner(world), "words": WORDS}
    assert rec["isolation"] == "host" and rec["container"] is False
    assert rec["successor"] == P.SUCCESSOR
    assert rec["execution"] == "inst-c"


@pytest.mark.parametrize("given", [
    {"mode": "all"},
    {"mode": "task", "categories": ["read", "edit", "test", "git"]},
    {"mode": "task", "categories": ["read", "edit", "build", "git", "install", "network"]},
])
def test_routine_work_or_approve_all_covering_development_selects_it(world, ws, given):
    _authorise(world)
    run = _run(world, ws, given)
    assert runtime_options(world["cv"], run, ws["repo"], "codex",
                           _contract_of("codex")) == {"execution_policy": P.HOST_DEV}


@pytest.mark.parametrize("given", [
    None,                                                        # no owner consent
    {"mode": "ask"},
    {"mode": "deny"},
    {"mode": "task", "categories": ["read", "edit", "test"]},     # no git
    {"mode": "task", "categories": ["read", "git", "test"]},      # no edit
    {"mode": "task", "categories": ["read", "edit", "git"]},      # nothing built or run
])
def test_a_run_that_is_not_authorised_development_never_gets_it(world, ws, given):
    _authorise(world)
    run = _run(world, ws, given)
    for rt in ("codex", "antigravity"):
        got = runtime_options(world["cv"], run, ws["repo"], rt, _contract_of(rt))
        assert "execution_policy" not in got, (rt, given)
    assert P.of_run(world["cv"], run) is None


def test_without_the_owners_authorisation_nothing_changes(world, ws):
    run = _run(world, ws)
    assert runtime_options(world["cv"], run, ws["repo"], "codex",
                           _contract_of("codex")) == {"escalations": "client"}
    assert runtime_options(world["cv"], run, ws["repo"], "antigravity",
                           _contract_of("antigravity")) == {"allow": ["command(*)"]}
    assert P.of_run(world["cv"], run) is None


def test_only_named_runtimes_and_only_while_enabled(world, ws):
    _authorise(world, runtimes=["codex"])
    run = _run(world, ws)
    assert "execution_policy" not in runtime_options(world["cv"], run, ws["repo"], "antigravity",
                                                     _contract_of("antigravity"))
    # a runtime that does not declare the policy never gets it, even if named
    _authorise(world, runtimes=["codex", "claude"])
    assert "execution_policy" not in runtime_options(world["cv"], run, ws["repo"], "claude",
                                                     _contract_of("claude"))
    # the owner's newest act decides: disabled
    _authorise(world, enabled=False, runtimes=())
    run2 = _run(world, ws)
    assert runtime_options(world["cv"], run2, ws["repo"], "codex",
                           _contract_of("codex")) == {"escalations": "client"}


def test_an_agent_cannot_authorise_it(world, ws):
    _authorise(world, actor=world["steward"])            # not the owner
    run = _run(world, ws)
    assert "execution_policy" not in runtime_options(world["cv"], run, ws["repo"], "codex",
                                                     _contract_of("codex"))


def test_authorising_needs_runtimes_and_the_decision_words(world):
    with pytest.raises(ValueError):
        P.authorise(world["cv"], owner=_owner(world), enabled=True, runtimes=(),
                    authorization=WORDS)
    with pytest.raises(ValueError):
        P.authorise(world["cv"], owner=_owner(world), enabled=True, runtimes=["codex"],
                    authorization=" ")
    with pytest.raises(ValueError):
        P.authorise(world["cv"], owner=_owner(world), enabled=True, runtimes=["codex"],
                    authorization=WORDS, policy=P.SUCCESSOR)


def test_the_run_is_told_host_execution_and_its_boundary_never_a_sandbox(ws):
    selected = {"policy": P.HOST_DEV}
    meta = {"sandbox": {"permissions": "backend-mode", "enforced_by": "none",
                        "isolation": "host", "execution_policy": P.HOST_DEV}}
    eff = effective(meta, backend="codex", workspace=ws["repo"],
                    consent={"mode": "task", "categories": list(C.DEFAULT_CATEGORIES)},
                    enforcement="sandbox+runtime-reviewer", execution_policy=selected)
    text = render(eff)
    assert eff["execution_policy"] == {"name": P.HOST_DEV, "isolation": "host",
                                       "container": False, "applied": True}
    assert "not a container" in text and "deploy" in text and "governance" in text
    # installation-neutral: no installation's own server or process is named (owner, 2026-11-11)
    assert "DAY-TO-DAY" not in text and "does not imply a push, merge or deployment" in text
    assert "- Sandbox:" not in text and "inside its sandbox" not in text
    # selected but not reported applied by MARS: said so, and nothing more is claimed
    eff2 = effective({"sandbox": {"permissions": "none", "enforced_by": "sandbox"}},
                     backend="antigravity", workspace=ws["repo"], execution_policy=selected)
    assert eff2["execution_policy"]["applied"] is False
    assert "did not report applying it" in render(eff2)


def test_enforcement_reports_host_execution_not_isolation():
    got = enforcement({"mode": "task", "enforced_by": "none",
                       "execution_policy": {"name": P.HOST_DEV, "isolation": "host",
                                            "container": False,
                                            "mechanism": "codex-acp session mode full-access"}})
    assert got["enforced"] is False and got["isolation"] == "host"
    assert got["execution_policy"] == P.HOST_DEV
    assert "not container isolation" in got["words"]


def test_the_owner_route_sets_it(world):
    got = _call(world, "/api/execution-policy",
                {"enabled": True, "runtimes": ["codex"], "authorization": WORDS})
    assert got["in_force"]["enabled"] is True and got["in_force"]["runtimes"] == ["codex"]
    assert _call(world, "/api/execution-policy")["act"] == got["act"]


# -- review r3 fixes ------------------------------------------------------------------

def test_a_delegated_child_outside_the_consented_workspaces_never_gets_it(world, ws):
    from tests.test_run_consent import _request
    from tests._loop import a_conversation
    _authorise(world)
    cid = a_conversation(world, "Delegation")
    turn, parent = _request(world, cid, consent=C.consent_value(
        {"mode": "task", "workspaces": [ws["repo"]]}))
    # the agent delegates under the inherited consent, declaring another repository
    _, child = _request(world, cid, by=world["steward"], caused_by=parent, repo=ws["other"])
    run = world["cv"].record_act(actor=world["steward"], act="execution-started",
                                 conversation=cid, turn=turn, execution="inst-k",
                                 runtime="codex", caused_by=child, because="test",
                                 detail={"workspace": ws["other"]})
    assert "execution_policy" not in runtime_options(world["cv"], run, ws["other"], "codex",
                                                     _contract_of("codex"))
    # inside the inherited workspace it is still development work the owner consented to
    inner = os.path.join(ws["repo"], "src")
    run2 = world["cv"].record_act(actor=world["steward"], act="execution-started",
                                  conversation=cid, turn=turn, execution="inst-k2",
                                  runtime="codex", caused_by=child, because="test",
                                  detail={"workspace": inner})
    assert runtime_options(world["cv"], run2, inner, "codex",
                           _contract_of("codex")) == {"execution_policy": P.HOST_DEV}


def _opened(world, ws):
    from mentis.web import compiled_runs
    from mentis.web.permissions import before_open
    _authorise(world)
    run = _run(world, ws)
    assert runtime_options(world["cv"], run, ws["repo"], "codex",
                           _contract_of("codex")) == {"execution_policy": P.HOST_DEV}
    before_open(world["cv"], run, ws["repo"], {"mode": "task", "workspaces": []})
    held = compiled_runs.tracked(world["cv"])[run]
    assert held["open"] and not held.get("halt")
    return run


def test_narrowing_consent_halts_a_live_policy_run(world, ws):
    from mentis.web import compiled_runs
    run = _opened(world, ws)
    C.set_task(world["cv"], run, owner=_owner(world), because="narrow",
               consent=C.consent_value({"mode": "task", "workspaces": [ws["repo"]],
                                        "categories": ["read", "edit"]}))
    halt = compiled_runs.tracked(world["cv"])[run].get("halt")
    assert halt and "execution policy" in halt["why"]


def test_turning_the_policy_off_halts_a_live_policy_run(world, ws):
    from mentis.web import compiled_runs
    run = _opened(world, ws)
    _authorise(world, enabled=False, runtimes=())
    assert compiled_runs.tracked(world["cv"])[run].get("halt")


def test_a_selection_that_cannot_be_recorded_is_not_applied(world, ws, monkeypatch):
    _authorise(world)
    run = _run(world, ws)

    def fail(*a, **k):
        raise RuntimeError("store unavailable")
    monkeypatch.setattr(P, "record", fail)
    assert runtime_options(world["cv"], run, ws["repo"], "codex",
                           _contract_of("codex")) == {"escalations": "client"}


def test_the_route_refuses_a_caller_presenting_a_worker_grant(world):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        world["base"] + "/api/execution-policy", method="POST",
        data=json.dumps({"enabled": True, "runtimes": ["codex"],
                         "authorization": WORDS}).encode(),
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1",
                 "X-Mentis-Worker": "some-grant"})
    with pytest.raises(urllib.error.HTTPError) as got:
        urllib.request.urlopen(req)
    assert got.value.code in (400, 403)
    assert P.authorisation(world["cv"]) is None
