"""Mentis consumes the runtime capability contract (round 2, O9 / program §12), never a name.

  * the four states, read from MARS; a MARS without a contract claims nothing;
  * quota is Mentis's overlay: an exhausted or held runtime is temporarily unavailable, and
    automatic selection never picks it silently (K3 out of capacity);
  * a runtime with no native resume is not asked for one: its continuation is given the
    record-derived context, and the record says why;
  * the profiles the offline mode serves say what MARS declares (checked against a MARS
    build when one is named).
"""

from __future__ import annotations

import json
import os
import subprocess
import time

import pytest

from mentis.core import runtime_contract as RC
from mentis.core.service import MentisService
from mentis.execution import FakeExecution
from tests.conformance_runtime.profiles import PROFILES
from tests.conformance_runtime.rig import MARS_ENV


def _svc(tmp_path, backends, capacity=None):
    return MentisService(str(tmp_path / "i"), execution=FakeExecution(backends, capacity=capacity))


def _hold(rid, why="rate_limited: K3 quota exhausted"):
    now = time.time()
    return {rid: {"until": now + 3600, "why": f"{rid}: {why}", "model": None,
                  "since": now - 60, "basis": "act-1"}}


def test_every_profile_states_every_capability_in_one_of_four_states():
    for rid, prof in PROFILES.items():
        c = RC.of_backend(prof["backend"])
        assert c["from_mars"], rid
        assert set(RC.CAPABILITIES) <= set(c["capabilities"]), rid
        for name in RC.CAPABILITIES:
            assert RC.state(c, name) in RC.STATES, (rid, name)


def test_a_mars_without_a_contract_claims_nothing():
    c = RC.of_backend({"id": "claude", "available": True, "supports": {"load": True}})
    assert not c["from_mars"]
    assert {RC.state(c, n) for n in RC.CAPABILITIES} == {RC.UNVERIFIED}
    assert c["availability"]["state"] == RC.SUPPORTED
    assert RC.resume_words(c) is None, "unverified is still asked: MARS says if it resumed"


def test_an_unknown_state_is_never_read_as_support():
    b = {"id": "x", "available": True,
         "contract": {"version": 1, "capabilities": {"native_resume": {"state": "probably"}}}}
    assert RC.state(RC.of_backend(b), "native_resume") == RC.UNVERIFIED


def test_quota_makes_a_runtime_temporarily_unavailable_with_its_reason(tmp_path):
    backends = [PROFILES["claude"]["backend"], PROFILES["kimi-k3"]["backend"]]
    svc = _svc(tmp_path, backends)
    held = svc.runtime_contract("kimi-k3", holds=_hold("kimi-k3"))
    assert held["availability"]["state"] == RC.UNAVAILABLE
    assert "K3 quota exhausted" in held["availability"]["why"]
    # what it was never shown to support stays what it is: not claimed, not lost
    assert RC.state(held, "capacity_reporting") == RC.UNSUPPORTED
    assert RC.state(held, "cancellation") == RC.UNVERIFIED
    free = svc.runtime_contract("claude", holds=_hold("kimi-k3"))
    assert free["availability"]["state"] == RC.SUPPORTED
    assert RC.state(free, "native_resume") == RC.SUPPORTED


def test_an_exhausted_runtime_by_its_own_report_is_temporarily_unavailable(tmp_path):
    now = time.time()
    cap = {"claude": {"backend": "claude", "source": "claude /usage", "observedAt": now,
                      "plan": "max", "modelGroups": {}, "notes": [],
                      "windows": [{"label": "five_hour", "usedFraction": 1.0,
                                   "windowSeconds": 18000, "resetsAt": now + 3600,
                                   "group": None, "raw": {}}]}}
    svc = _svc(tmp_path, [PROFILES["claude"]["backend"]], capacity=cap)
    svc.capacity_prime() if hasattr(svc, "capacity_prime") else None
    svc._capacity_answer(5, prefer_held=False)
    c = svc.runtime_contract("claude")
    assert c["availability"]["state"] == RC.UNAVAILABLE, c["availability"]
    assert RC.state(c, "native_resume") == RC.UNAVAILABLE


def test_automatic_selection_never_silently_picks_an_exhausted_runtime(tmp_path):
    """K3 is out of capacity: the record holds it. Unnamed work goes elsewhere and says so;
    named work is not substituted, and its exhaustion is disclosed."""
    backends = [PROFILES["kimi-k3"]["backend"], PROFILES["claude"]["backend"]]
    svc = _svc(tmp_path, backends)
    sel = svc.execution_select(holds=_hold("kimi-k3"))
    assert sel.runtime == "claude"
    assert any("exhausted" in b and "kimi-k3" in b for b in sel.because), sel.because
    named = svc.execution_select(runtime="kimi-k3", holds=_hold("kimi-k3"))
    assert named.runtime == "kimi-k3"
    said = " ".join(named.because) + json.dumps(named.inputs.get("disclosed") or [])
    assert "kimi-k3" in said and ("exhausted" in said or "held" in said), said


def test_only_held_runtimes_left_is_a_refusal_naming_when_it_ends(tmp_path):
    svc = _svc(tmp_path, [PROFILES["kimi-k3"]["backend"]])
    from mentis.api.errors import RuntimeNotPresent
    with pytest.raises(RuntimeNotPresent) as got:
        svc.execution_select(holds=_hold("kimi-k3"))
    assert "kimi-k3" in str(got.value)


def test_the_capabilities_tool_tells_each_runtimes_contract(tmp_path):
    from mentis.worker import _runtime_capabilities
    svc = _svc(tmp_path, [p["backend"] for p in PROFILES.values()])
    rows = _runtime_capabilities(svc, ["call_mentis_tools"])
    assert "native_resume" in rows["claude"]["contract"][RC.SUPPORTED]
    assert "native_resume" in rows["antigravity"]["contract"][RC.UNSUPPORTED]
    assert "capacity_reporting" in rows["kimi-k3"]["contract"][RC.UNSUPPORTED]


def test_the_capabilities_tool_shows_a_held_runtime_as_held(tmp_path, monkeypatch):
    """Review L1: K3 held by the record's quota failure is shown temporarily
    unavailable, with why, through the path the agent reads (`capabilities`),
    not only where selection decides."""
    from mentis import worker as W
    from mentis.web import quota as Q
    svc = _svc(tmp_path, [p["backend"] for p in PROFILES.values()])
    rows = W._runtime_capabilities(svc, ["call_mentis_tools"], holds=_hold("kimi-k3"))
    k3 = rows["kimi-k3"]["contract"]
    assert k3["availability"]["state"] == RC.UNAVAILABLE
    assert "K3 quota exhausted" in k3["availability"]["why"]
    assert RC.SUPPORTED not in k3, "nothing it supports is shown usable while held"
    assert rows["claude"]["contract"]["availability"]["state"] == RC.SUPPORTED
    # the tool itself reads the holds from the record
    monkeypatch.setattr(Q, "quota_holds", lambda cv, now=None: _hold("kimi-k3"))
    surface = type("S", (), {"cv": object(), "agents": svc})()
    shown = W.Surface.capabilities(surface)
    assert shown["runtimes"]["kimi-k3"]["contract"]["availability"]["state"] == RC.UNAVAILABLE


def test_no_native_resume_is_decided_by_the_contract_not_the_name(monkeypatch):
    from mentis.web import continuity as C
    from mentis.web import dispatch as D
    monkeypatch.setattr(D, "withdrawal_of", lambda cv, exp: None)
    no = RC.of_backend(PROFILES["antigravity"]["backend"])
    # the same contract under another name decides the same way
    renamed = RC.of_backend({**PROFILES["antigravity"]["backend"], "id": "future-runtime"})
    for c in (no, renamed):
        got, why = C.decide(None, expectation="e", participant="p", resumed_from="r",
                            now={}, contract=c)
        assert got is None and "record-derived context" in why
    assert RC.resume_words(RC.of_backend(PROFILES["claude"]["backend"])) is None
    assert RC.resume_words(RC.of_backend(PROFILES["codex"]["backend"])) is None


@pytest.mark.skipif(not os.environ.get(MARS_ENV), reason=f"{MARS_ENV} names no MARS build")
def test_profiles_say_what_mars_declares(tmp_path):
    """The offline profiles' states are MARS's own, for every built-in MARS declares."""
    import shlex
    mars = shlex.split(os.environ[MARS_ENV], posix=False)
    if mars and mars[-1] == "stdio":
        mars = mars[:-1]
    data = tmp_path / "data"
    data.mkdir()
    env = {k: v for k, v in os.environ.items()}
    env["MARS_BACKENDS_FILE"] = str(tmp_path / "none.json")
    proc = subprocess.Popen([*mars, "--data-dir", str(data), "stdio"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    try:
        def call(i, method, params):
            proc.stdin.write((json.dumps({"jsonrpc": "2.0", "id": i, "method": method,
                                          "params": params}) + "\n").encode())
            proc.stdin.flush()
            while True:
                msg = json.loads(proc.stdout.readline())
                if msg.get("id") == i:
                    return msg["result"]
        call(1, "initialize", {"protocolVersion": 1})
        got = {b["id"]: b for b in call(2, "_mars/backends", {})["backends"]}
    finally:
        proc.kill()
    for rid in ("claude", "codex", "antigravity", "local"):
        if rid not in got:
            continue
        mars_states = {n: c["state"] for n, c in got[rid]["contract"]["capabilities"].items()}
        mine = {n: c["state"] for n, c in PROFILES[rid]["backend"]["contract"]["capabilities"].items()}
        # an unavailable runtime here shows supported as temporarily unavailable
        if got[rid]["contract"]["availability"]["state"] == "temporarily-unavailable":
            mine = {n: ("temporarily-unavailable" if s == "supported" else s)
                    for n, s in mine.items()}
        assert mars_states == mine, rid
        # how a client becomes the reviewer of escalations (round 2 E), as MARS declares it
        def review(contract):
            return (contract["capabilities"]["permission_enforcement"].get("client_review")
                    or {}).get("options")
        assert review(got[rid]["contract"]) == review(PROFILES[rid]["backend"]["contract"]), rid


#: MARS contract §3.4: the only `mars/limits` keys MARS accepts (any other is -32602).
MARS_LIMIT_KEYS = {"startup_s", "idle_s", "hard_s", "permission_s", "cancel_grace_s",
                   "session_ttl_s"}


def test_a_deadline_reaches_mars_as_a_limit_it_accepts(tmp_path):
    """A request's deadline is MARS's `hard_s`; `timeout_s` was refused by Rust MARS
    ("unknown limit 'timeout_s'"), so every run with a deadline failed to open."""
    from mentis.web import dispatch as D
    from tests.conformance_runtime.rig import Rig
    rig = Rig("claude", root=tmp_path, profile=PROFILES["claude"])
    try:
        cid = rig.conversation("deadline")
        who = rig.participant(cid, "@Timed")
        turn = rig.cv.say(cid, rig.owner, [__import__("mentis.conversation", fromlist=["text"]).text("do it")])
        exp = rig.cv.expect(turn, of=who, kind="result", by=rig.owner, conversation=cid)
        D.dispatch(rig.state, conversation=cid, turn=turn, participant=who, work="do it",
                   expectation=exp, runtime="claude", deadline_s=120)
        spec = rig.execution.performed[-1]
        assert spec.limits == {"hard_s": 120.0}
        assert set(spec.limits) <= MARS_LIMIT_KEYS
    finally:
        rig.close()
