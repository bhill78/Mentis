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
