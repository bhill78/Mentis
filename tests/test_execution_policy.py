"""The interim host development execution policy (owner decision, 2026-11-11).

`mentis.execution.policy`: an authorised development run on a runtime that declares
`host-development-unrestricted` is sent `execution_policy` (and nothing that would
confine or ask), the selection is recorded with the owner act that authorised it, and
nothing else ever gets it: no owner act, a disabled one, another runtime, a run without
owner consent, a consent narrowed below development work, an act by anyone but the owner.
"""

from __future__ import annotations

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
    assert "not a container" in text and "DAY-TO-DAY" in text and "governance" in text
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
