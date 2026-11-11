"""Host-only delegation and the four execution-mode states (round 4, owner decisions 2 and 4).

  * DELEGATION TO A HOST-ONLY RUNTIME RUNS. Claude, the local worker and kimi have only host
    execution (their MARS contracts: default `unrestricted-host`, `sandboxed` unverified or
    unsupported). A carrier's `delegate` to one of them is not refused for lacking a sandbox:
    the child runs, through the real dispatch, and its start act records what it actually ran
    in -- host isolation, the runtime's default, "not selected by the owner" -- and never
    claims sandbox protection. There is no universal sandbox requirement.
  * TEMPORARILY UNAVAILABLE IS ITS OWN STATE. A runtime that cannot take work now (MARS says so,
    or Mentis holds its quota) shows every mode it supports as `temporarily-unavailable` with
    the why; unsupported and unverified modes stay as declared (Claude's Sandboxed stays
    unverified). A mode in that state is not refused as unsupported -- it is the runtime's
    availability, decided where it always is -- and a refused mode says its state.
"""

from __future__ import annotations

import copy

import pytest

from mentis.core import runtime_contract as RC
from mentis.execution import mode as M
from tests.conformance_runtime.profiles import PROFILES
from tests.conformance_runtime.rig import Rig
from tests.conformance_runtime.scenarios import PASSED, delegation


# -- host-only delegation ---------------------------------------------------------------------

@pytest.mark.parametrize("runtime", ["claude", "local", "kimi-k3"])
def test_a_delegation_to_a_host_only_runtime_runs_and_records_host_execution(tmp_path, runtime):
    rig = Rig(runtime, root=tmp_path, profile=PROFILES[runtime])
    try:
        modes = PROFILES[runtime]["backend"]["contract"]["execution_modes"]
        assert modes["default"] == M.UNRESTRICTED_HOST
        assert modes["modes"]["sandboxed"]["state"] != M.SUPPORTED   # host-only
        [check] = delegation(rig)
        assert check.status == PASSED, check.evidence
        owner = rig.owner
        # the runs of requests (the fixture Brain holds older, unrelated runs)
        starts = [s for s in rig.cv._c.operational(act="execution-started")
                  if (rig.cv._act(s.get("caused_by")) or {}).get("act") == "expectation-recorded"]
        child = [s for s in starts
                 if (rig.cv._act(s["caused_by"]) or {}).get("actor") not in (None, owner)]
        assert child, "the delegated child never started"
        rec = child[0]["detail"]["execution_mode"]
        assert rec["requested"] is None and rec["source"] == "runtime-default"
        assert rec["effective"] == M.UNRESTRICTED_HOST and rec["isolation"] == "host"
        assert rec["mechanism"] and "host" in rec["mechanism"]
        assert "not selected by the owner" in rec["host_by_runtime_default"]
        # nothing claims a sandbox, and nothing was sent to MARS to change the mode
        assert rec["isolation"] != "sandbox"
        child_spec = [s for s in rig.execution.performed
                      if s.run_id == child[0].get("execution")]
        assert child_spec and "execution_mode" not in (child_spec[0].options or {})
        # the parent, which the owner asked for, carries no such note
        parent = [s for s in starts if (rig.cv._act(s["caused_by"]) or {}).get("actor") == owner]
        assert parent and "host_by_runtime_default" not in parent[0]["detail"]["execution_mode"]
    finally:
        rig.close()


# -- the four states ----------------------------------------------------------------------------

def _backend(runtime, *, available=True, reason=None):
    b = copy.deepcopy(PROFILES[runtime]["backend"])
    b["available"] = available
    b["reason"] = reason
    if not available:
        b["contract"]["availability"] = {"state": RC.UNAVAILABLE, "why": reason}
    return b


def test_an_unavailable_runtime_shows_its_supported_modes_temporarily_unavailable():
    """A MARS that does not overlay the modes itself is brought level by Mentis; one that does
    is unchanged; unsupported and unverified modes are never touched."""
    got = M.catalogue(RC.of_backend(_backend("claude", available=False, reason="not signed in")))
    assert got["modes"]["unrestricted-host"]["state"] == M.UNAVAILABLE
    assert got["modes"]["unrestricted-host"]["why"] == "not signed in"
    assert got["modes"]["unrestricted-host"]["mechanism"]          # kept
    assert got["modes"]["sandboxed"]["state"] == "unverified"       # Claude Sandboxed
    assert got["modes"]["container"]["state"] == "unsupported"
    up = M.catalogue(RC.of_backend(_backend("claude")))
    assert up["modes"]["unrestricted-host"]["state"] == M.SUPPORTED
    assert up["modes"]["sandboxed"]["state"] == "unverified"
    codex = M.catalogue(RC.of_backend(_backend("codex", available=False, reason="probe failed")))
    assert {m: v["state"] for m, v in codex["modes"].items()} == {
        "sandboxed": M.UNAVAILABLE, "unrestricted-host": M.UNAVAILABLE, "container": "unsupported"}
    # MARS already saying it: the same answer, nothing doubled
    already = _backend("codex", available=False, reason="probe failed")
    already["contract"]["execution_modes"] = RC.modes_unavailable(
        already["contract"]["execution_modes"], "probe failed")
    assert M.catalogue(RC.of_backend(already)) == codex
    # a state Mentis does not know is unverified, never support
    odd = _backend("codex")
    odd["contract"]["execution_modes"]["modes"]["sandboxed"]["state"] = "maybe"
    assert M.catalogue(RC.of_backend(odd))["modes"]["sandboxed"]["state"] == "unverified"


def test_a_quota_hold_makes_supported_modes_temporarily_unavailable_too():
    held = RC.with_quota(RC.of_backend(_backend("codex")), held="codex quota held until 12:00")
    modes = held["execution_modes"]["modes"]
    assert modes["sandboxed"]["state"] == M.UNAVAILABLE
    assert modes["unrestricted-host"]["why"] == "codex quota held until 12:00"
    assert modes["container"]["state"] == "unsupported"
    local = RC.with_quota(RC.of_backend(_backend("local")), exhausted="no local capacity")
    assert local["execution_modes"]["modes"]["unrestricted-host"]["state"] == "unverified"


def test_a_temporarily_unavailable_mode_is_not_refused_as_unsupported_and_a_refusal_says_its_state():
    down = RC.of_backend(_backend("codex", available=False, reason="not signed in"))
    M.supported(down, M.UNRESTRICTED_HOST, "codex")                 # the runtime's availability
    with pytest.raises(M.Unsupported) as got:
        M.supported(RC.of_backend(_backend("claude")), M.SANDBOXED, "claude")
    body = got.value.body()
    assert body["kind"] == "ExecutionModeUnsupported" and body["state"] == "unverified"
    assert "not verified" in str(got.value) and body["why"]
    with pytest.raises(M.Unsupported) as got:
        M.supported(RC.of_backend(_backend("local")), M.SANDBOXED, "local")
    assert got.value.body()["state"] == "unsupported"
    # resolve keeps the selection's mode: never another one
    assert M.STATES == ("supported", "unsupported", "temporarily-unavailable", "unverified")
