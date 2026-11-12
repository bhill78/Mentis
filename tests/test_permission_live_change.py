"""Changing Permission Mode while a run works (item 5.7).

The owner's change (`POST /api/runs/<run>/consent`) decides every later
request of the run. It also decides again a request the run is ALREADY
waiting on: the wait is woken by the owner's act, and a request the new mode
allows or refuses is answered with that authority and its question closed as
`consent-changed`; one the new mode still asks about keeps waiting. Another
run's waiting request is decided by its own consent, so a change to one run
never answers another's. The change's answer says how it reaches the run --
applied, pending (and when), unsupported or unknown -- from what MARS said it
applied (`permissions.change_effect`).
"""

from __future__ import annotations

import threading
import time

import pytest

from mentis.operational import consent as C
from mentis.web import permissions as P
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_run_consent import _policy_world, _shell, get, post, ws  # noqa: F401


def _wait_for(obs, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline and not obs.get("permissions"):
        time.sleep(0.05)
    return next(iter(obs["permissions"]))


def _ask(policy, run, request, obs):
    got: dict = {}
    t = threading.Thread(target=lambda: got.setdefault("a", policy(run, "inst-c", request, obs)))
    t.start()
    return t, got, _wait_for(obs)


def _question(world, form):
    return world["cv"].decision_form(form)["questions"][0]


def _in_ws(ws, name="probe"):
    """Routine inside the run's workspace: asked under `ask`, allowed under `task`."""
    return _shell(f"mkdir {ws['repo']}\\{name}")


def test_a_waiting_request_is_answered_by_the_new_mode(world, ws):
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    t, got, form = _ask(policy, run, _in_ws(ws), obs)
    assert _question(world, form)["open"]
    answer = post(world, f"/api/runs/{run}/consent", {"mode": "task"})
    t.join(10)
    assert got["a"] == "once"                      # allowed, the runtime's allow_once
    q = _question(world, form)
    assert not q["open"] and not q["answered"] and q["lapsed"]["reason"] == "consent-changed"
    last = C.answered(world["cv"], run)[-1]
    assert (last["answer"], last["by"], last["form"]) == ("allowed", "task", form)
    # the change's answer says what became of the waiting request
    assert answer["effect"]["answered_now"] == [
        {"form": form, "answer": "allowed", "by": "task", "summary": last["operation"]["summary"]}]
    assert "answered under it" in answer["effect"]["words"]
    # and the next request is decided by it without asking
    assert policy(run, "inst-c", _in_ws(ws, "next"), obs) == "once"
    assert C.answered(world["cv"], run)[-1]["by"] == "task"


def test_never_wait_refuses_a_waiting_request(world, ws):
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    outside = _shell(f"echo x > {ws['other']}\\notes.txt")
    t, got, form = _ask(policy, run, outside, obs)
    post(world, f"/api/runs/{run}/consent", {"mode": "deny"})
    t.join(10)
    assert got["a"] is None
    assert _question(world, form)["lapsed"]["reason"] == "consent-changed"
    last = C.answered(world["cv"], run)[-1]
    assert (last["answer"], last["by"]) == ("refused", "deny")


def test_a_request_the_new_mode_still_asks_keeps_waiting(world, ws):
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    outside = _shell(f"echo x > {ws['other']}\\notes.txt")      # outside the task
    t, got, form = _ask(policy, run, outside, obs)
    answer = post(world, f"/api/runs/{run}/consent", {"mode": "task"})
    assert answer["effect"]["answered_now"] == []
    time.sleep(0.5)
    assert t.is_alive() and _question(world, form)["open"]
    obs["stop"] = True                              # end the wait
    t.join(10)
    assert _question(world, form)["lapsed"]["reason"] == "run-stopped"


def test_changing_one_run_never_answers_another(world, ws):
    """Two runs on two requests, both waiting: the owner widens one of them."""
    _, _, _, run_a, policy = _policy_world(world, ws)
    _, _, _, run_b, _ = _policy_world(world, ws)
    obs_a: dict = {}
    obs_b: dict = {}
    ta, got_a, form_a = _ask(policy, run_a, _in_ws(ws, "a"), obs_a)
    tb, got_b, form_b = _ask(policy, run_b, _in_ws(ws, "b"), obs_b)
    post(world, f"/api/runs/{run_a}/consent", {"mode": "all"})
    ta.join(10)
    assert got_a["a"] == "once" and C.answered(world["cv"], run_a)[-1]["by"] == "all"
    time.sleep(0.5)
    assert tb.is_alive() and _question(world, form_b)["open"]
    assert C.of_run(world["cv"], run_b)["mode"] == "ask"
    assert not [a for a in C.answered(world["cv"], run_b)]
    obs_b["stop"] = True
    tb.join(10)
    assert got_b["a"] is None


def test_an_owner_answer_that_landed_first_stands(world, ws):
    """The question is closed under the write lock before the run is told:
    when the owner's own answer is there first, it is the run's answer and
    the change closes nothing."""
    from tests.test_run_consent import _answer_form
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    t, got, form = _ask(policy, run, _in_ws(ws), obs)
    _answer_form(world, cid, obs, "Deny")
    post(world, f"/api/runs/{run}/consent", {"mode": "task"})
    t.join(10)
    assert got["a"] == "no"                        # the owner's Deny: the reject option
    q = _question(world, form)
    assert q["answered"] and q["lapsed"] is None


@pytest.mark.parametrize("applied,state,at", [
    ({"enforced_by": "client"}, "applied", "next-request"),
    ({"enforced_by": "sandbox+client", "escalations_to": "client"}, "applied", "next-request"),
    ({"enforced_by": "sandbox+client"}, "pending", "next-run"),
    ({"enforced_by": "sandbox"}, "pending", "next-run"),
    ({"enforced_by": "none"}, "unsupported", None),
    ({"mode": "ask"}, "unknown", None),
    (None, "pending", "session-open"),
])
def test_how_a_change_reaches_a_run_is_said_from_what_mars_applied(applied, state, at):
    got = P.change_effect(applied, held=True, ended=False)
    assert (got["state"], got["at"]) == (state, at) and got["words"]


def test_a_halting_ended_or_unheld_run_says_so():
    client = {"enforced_by": "client"}
    assert P.change_effect(client, held=True, ended=False, halting=True)["at"] == "restart"
    assert P.change_effect(client, held=False, ended=True)["at"] == "next-run"
    assert P.change_effect(client, held=False, ended=False)["state"] == "unknown"


def test_the_consent_read_carries_the_effect(world, ws):
    cid, turn, exp, run, policy = _policy_world(world, ws)
    got = get(world, f"/api/runs/{run}/consent")
    # this test world holds no live session for the run: said as not known
    assert got["effect"]["state"] in ("unknown", "pending")
    assert got["effect"]["answered_now"] == []


def test_mars_consent_is_kept_on_the_run_as_its_session_opens():
    """`RunSpec.on_open`: the observation carries MARS's report while the run
    works, not only after it ends."""
    from mentis.core.service import _opened_into
    obs: dict = {}
    _opened_into(obs)({"enforced_by": "client", "mode": "ask"})
    assert obs["consent_applied"] == {"enforced_by": "client", "mode": "ask"}
    assert obs["session_opened_at"] > 0
    assert _opened_into(None) is None


# ---------------------------------------------------------------------------
# races (independent review of qc-permissions, review-B.md CRITICAL 1 and 2)


def _set_mode(world, run, mode):
    C.set_task(world["cv"], run, owner=world["who"]["@brian"],
               consent={"mode": mode, "workspaces": [], "categories": list(C.DEFAULT_CATEGORIES)},
               because="race regression")


def _until(predicate, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def test_a_change_before_the_wait_registers_is_not_lost(world, ws, monkeypatch):
    """CRITICAL 2: the owner changes the mode after the question is recorded
    but before its wait is registered. The wait decides once more as it
    registers, so the change answers it."""
    import mentis.worker as worker
    _, _, _, run, policy = _policy_world(world, ws)
    real_form = worker._decision_form
    created, release = threading.Event(), threading.Event()
    form_id: dict = {}

    def paused_form(*a, **kw):
        result = real_form(*a, **kw)
        form_id["id"] = result["form"]
        created.set()
        assert release.wait(8)
        return result
    monkeypatch.setattr(worker, "_decision_form", paused_form)
    obs: dict = {}
    got: dict = {}
    t = threading.Thread(target=lambda: got.setdefault(
        "a", policy(run, "inst-c", _in_ws(ws, "late"), obs)), daemon=True)
    t.start()
    try:
        assert created.wait(8)
        assert form_id["id"] not in P._WAITS
        post(world, f"/api/runs/{run}/consent", {"mode": "task"})
        release.set()
        t.join(8)
        assert not t.is_alive() and got["a"] == "once"
        q = _question(world, form_id["id"])
        assert not q["open"] and q["lapsed"]["reason"] == "consent-changed"
        assert [(a["answer"], a["by"]) for a in C.answered(world["cv"], run)] == [("allowed", "task")]
    finally:
        release.set()
        obs["stop"] = True
        t.join(8)


def test_a_superseded_mode_never_authorizes_a_waiting_request(world, ws, monkeypatch):
    """CRITICAL 1: the verdict and the closing of the question are one step
    under the write lock. While the wait decides under `task`, the owner's
    change back to `ask` cannot land in between: it waits for the lock and is
    recorded after the question was answered -- and with the change first,
    the request keeps waiting."""
    _, _, _, run, policy = _policy_world(world, ws)
    real_decide = P.decide
    deciding, release = threading.Event(), threading.Event()

    def paused_decide(request, **kw):
        out = real_decide(request, **kw)
        if kw["consent"]["mode"] == "task" and not deciding.is_set():
            deciding.set()
            assert release.wait(8)
        return out
    obs: dict = {}
    got: dict = {}
    t = threading.Thread(target=lambda: got.setdefault(
        "a", policy(run, "inst-c", _in_ws(ws, "stale"), obs)), daemon=True)
    t.start()
    try:
        _until(lambda: any(w["run"] == run for w in P._WAITS.values()))
        monkeypatch.setattr(P, "decide", paused_decide)
        _set_mode(world, run, "task")
        assert deciding.wait(8)                    # the verdict is being formed under task
        back = threading.Thread(target=lambda: _set_mode(world, run, "ask"), daemon=True)
        back.start()
        back.join(0.5)
        assert back.is_alive(), "a consent act landed inside the verdict"
        release.set()
        t.join(8)
        back.join(8)
        assert not back.is_alive()
        # answered under task, which WAS in force when the question closed; the ask came after
        assert got["a"] == "once"
        q = _question(world, next(f for f in [a.get("form") for a in C.answered(world["cv"], run)] if f))
        met = q["lapsed"]["act"]
        sets = [a for a in world["cv"].history(caused_by=world["cv"]._act(run)["caused_by"])
                if a["act"] == C.SET]
        order = world["cv"]._write_order([met, sets[-1]["id"]])
        assert order[met] < order[sets[-1]["id"]]
        assert C.of_run(world["cv"], run)["mode"] == "ask"
    finally:
        release.set()
        obs["stop"] = True
        t.join(8)


def test_task_then_back_to_ask_before_the_wait_decides_keeps_asking(world, ws, monkeypatch):
    """The other order: both changes land before the wait decides (it is held
    before it takes the lock). It decides under `ask`: nothing is allowed."""
    _, _, _, run, policy = _policy_world(world, ws)
    real_again_lock = world["cv"]._c.atomic
    held, release = threading.Event(), threading.Event()
    me: dict = {}

    def paused_atomic():
        if threading.get_ident() == me.get("waiter") and not held.is_set():
            held.set()
            assert release.wait(8)
        return real_again_lock()
    obs: dict = {}
    got: dict = {}

    def waiter():
        me["waiter"] = threading.get_ident()
        got["a"] = policy(run, "inst-c", _in_ws(ws, "back"), obs)
    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    try:
        _until(lambda: any(w["run"] == run for w in P._WAITS.values()))
        _until(lambda: all(w["checked"].is_set() for w in P._WAITS.values() if w["run"] == run))
        monkeypatch.setattr(world["cv"]._c, "atomic", paused_atomic)
        _set_mode(world, run, "task")
        assert held.wait(8)
        _set_mode(world, run, "ask")
        release.set()
        time.sleep(0.6)
        assert t.is_alive() and "a" not in got
        assert C.answered(world["cv"], run) == []
    finally:
        release.set()
        obs["stop"] = True
        t.join(8)
    assert got["a"] is None
