"""Approve All, the fourth consent mode (owner, 2026-10-29): every permission
request the runtime makes is approved without asking, the protected
locations included, each one recorded; MARS is told nothing wider than
`task`, and the owner may change it during the run."""

from __future__ import annotations

import os
import time

from mentis.operational import consent as C
from mentis.web.permissions import mars_consent
from tests._loop import world  # noqa: F401
from tests.test_run_consent import _answers, _policy_world, _shell, get, post, ws  # noqa: F401


def test_approve_all_is_a_mode_and_ranks_above_task():
    got = C.consent_value({"mode": "all"})
    assert got["mode"] == C.ALL and C.ALL in C.MODES
    narrowed = C._narrow({"mode": C.ALL, "workspaces": [], "categories": ["read"]},
                         {"mode": C.TASK, "workspaces": [], "categories": ["read"]})
    assert narrowed["mode"] == C.TASK          # a child may narrow it, never widen past it


def test_every_request_is_approved_and_recorded_without_asking(world, ws):
    given = C.consent_value({"mode": "all", "workspaces": [ws["repo"]]})
    cid, turn, exp, run, policy = _policy_world(world, ws, given)
    secret = os.path.join(os.path.expanduser("~"), ".ssh", "config")
    obs: dict = {}
    t0 = time.time()
    for command in ("git push origin main", "curl https://example.com", "pip install requests",
                    f"rm -rf {ws['other']}", "bash -c 'echo hi'", f"Remove-Item {secret}"):
        assert policy(run, "inst-c", _shell(command), obs) == "once", command
    assert time.time() - t0 < 10
    assert not obs.get("permissions")          # nothing was put to the owner
    by = _answers(world, run)
    assert by == [("all", "allowed")] * 6
    ops = get(world, f"/api/runs/{run}/consent")["operations"]
    assert [o["by"] for o in ops] == ["all"] * 6 and ops[-1]["operation"]["command"]


def test_mars_hears_no_wider_than_task(world, ws):
    given = C.consent_value({"mode": "all", "workspaces": [ws["repo"]]})
    cid, turn, exp, run, policy = _policy_world(world, ws, given)
    assert mars_consent(world["cv"], run, ws["repo"])["mode"] == "task"


def test_the_owner_turns_it_on_and_off_during_the_run(world, ws):
    cid, turn, exp, run, policy = _policy_world(world, ws)
    got = post(world, f"/api/runs/{run}/consent", {"mode": "all"})
    assert got["consent"]["mode"] == "all" and "including" in got["consent"]["label"]
    assert policy(run, "inst-c", _shell("git push origin main"), {}) == "once"
    got = post(world, f"/api/runs/{run}/consent", {"mode": "deny"})
    assert got["consent"]["mode"] == "deny"
    assert policy(run, "inst-c", _shell("git push origin main"), {}) is None
    assert _answers(world, run)[-2:] == [("all", "allowed"), ("deny", "refused")]
    rows = {r["id"]: r for r in get(world, f"/fluid/api/runs?ids={run}")["runs"]}
    assert rows[run]["consent"]["mode"] == "deny"
