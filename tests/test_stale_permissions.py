"""A run's permission question stops asking when nothing can take its answer.

`mentis.web.permissions._ask_owner` is the only consumer of a permission
question's answer. When its wait ends unanswered -- timed out, run stopped or
ended -- the asker closes the question as lapsed
(`Conversations.retire_permission_question`); a server starting closes the
ones a dead server left (`retire_unconsumable`). Lapsed is not answered and
not withdrawn: Needs You drops it, a late answer is refused, nothing is
allowed, and every other decision is left as it is.
"""

from __future__ import annotations

import threading
import time

import pytest

from mentis.web import permissions as P
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_run_consent import (_answer_form, _policy_world, _shell, get,
                                    post, ws)  # noqa: F401


def _outside(ws):
    return _shell(f"echo x > {ws['other']}\\notes.txt", description="Write notes")


def _ask(world, ws, obs, policy, run):
    got = {}
    t = threading.Thread(target=lambda: got.setdefault(
        "a", policy(run, "inst-c", _outside(ws), obs)))
    t.start()
    deadline = time.time() + 20
    while time.time() < deadline and not obs.get("permissions"):
        time.sleep(0.05)
    form = next(iter(obs["permissions"]))
    return t, got, form


def _needs_you(world):
    return {i["key"] for i in get(world, "/fluid/api/needs-you/items")["items"]}


def _question(world, form):
    return world["cv"].decision_form(form)["questions"][0]


def _acts(world, caused_by, act):
    return [a for a in world["cv"].history(caused_by=caused_by) if a["act"] == act]


def test_an_active_question_stays_answerable(world, ws):
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    t, got, form = _ask(world, ws, obs, policy, run)
    assert form in _needs_you(world)
    _answer_form(world, cid, obs, "Allow once")
    t.join(30)
    assert got["a"] == "once"
    q = _question(world, form)
    assert q["answered"] and q["lapsed"] is None and not q["open"]


@pytest.mark.parametrize("end,reason", [("stop", "run-stopped"),
                                        ("ended_at", "run-ended")])
def test_a_run_that_stops_or_ends_leaves_no_question(world, ws, end, reason):
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    t, got, form = _ask(world, ws, obs, policy, run)
    assert form in _needs_you(world)
    obs[end] = time.time() if end == "ended_at" else True
    t.join(10)
    assert got["a"] is None
    q = _question(world, form)
    assert not q["open"] and not q["answered"] and q["withdrawn"] is None
    assert q["lapsed"]["reason"] == reason and q["lapsed"]["run"] == run
    # Mentis's act on the run's execution, not the owner's or the agent's
    assert q["lapsed"]["by"] == "mentis"
    assert form not in _needs_you(world)
    # the question and its options stay as asked
    assert q["question"] and [o["label"] for o in q["options"]][0] == "Allow once"


def test_timed_out_waits_do_not_accumulate(world, ws, monkeypatch):
    monkeypatch.setattr(P, "WAIT_S", 0.6)
    cid, turn, exp, run, policy = _policy_world(world, ws)
    forms = []
    for _ in range(3):           # an agent retrying after each refusal
        obs: dict = {}
        t, got, form = _ask(world, ws, obs, policy, run)
        t.join(10)
        assert got["a"] is None
        forms.append(form)
    assert all(_question(world, f)["lapsed"]["reason"] == "timed-out" for f in forms)
    assert not set(forms) & _needs_you(world)
    # what the run was told is still recorded: refused, nobody answered
    told = [a["detail"] for a in world["cv"].history(caused_by=run)
            if a["act"] == "operation-answered"]
    assert [(d["answer"], d["by"]) for d in told] == [("refused", "unanswered")] * 3


def test_a_late_answer_is_refused_and_restarts_nothing(world, ws, monkeypatch):
    monkeypatch.setattr(P, "WAIT_S", 0.6)
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    t, got, form = _ask(world, ws, obs, policy, run)
    t.join(10)
    drawn = world["cv"].decision_form(form)
    q = drawn["questions"][0]
    labels = [o["label"] for o in q["options"]]
    i = next(n for n, x in enumerate(labels) if x.startswith("Allow within this task"))
    label = labels[i]
    late = post(world, f"/api/conversations/{cid}/turns",
                {"author": world["who"]["@brian"], "text": label,
                 "action": "record-only", "replies_to": drawn["post"],
                 "addressed_to": [],
                 "chose": {"expectation": q["expectation"], "option": i,
                           "label": label}})
    assert "no longer asked" in late["error"] and late["lapsed"]
    assert not _acts(world, q["expectation"], "decision-answered")
    assert not [a for a in world["cv"].history(caused_by=run)
                if a["act"] == "consent-set"]
    assert not _acts(world, exp, "work-resumed")
    assert _question(world, form)["answer"] is None


def test_a_server_start_closes_only_what_a_dead_server_left(world, ws, monkeypatch):
    """A server killed mid-wait leaves its question open; the next one closes
    it before running anything. A genuine owner decision is untouched."""
    monkeypatch.setattr(P, "WAIT_S", 0.6)
    monkeypatch.setattr(P, "_retire", lambda *a, **k: [])   # died before retiring
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    t, got, orphan = _ask(world, ws, obs, policy, run)
    t.join(10)
    assert _question(world, orphan)["open"] and orphan in _needs_you(world)
    cv = world["cv"]
    asking = say(world, cid, "which way should this go?")["turn"]
    genuine = cv.expect(asking, of=world["who"]["@brian"], kind="decision",
                        by=world["steward"])
    assert cv.retire_permission_question(genuine, reason="run-ended") is None
    retired = P.retire_unconsumable(cv)
    assert len(retired) == 1
    assert _question(world, orphan)["lapsed"]["reason"] == "server-restarted"
    assert orphan not in _needs_you(world)
    assert not cv.expectation_state(genuine)["response_present"]
    assert genuine in _needs_you(world)
    # once: a second start finds nothing to close
    assert P.retire_unconsumable(cv) == []


def test_an_answer_that_lands_first_stands(world, ws):
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    t, got, form = _ask(world, ws, obs, policy, run)
    _answer_form(world, cid, obs, "Deny")
    t.join(30)
    q = _question(world, form)
    assert world["cv"].retire_permission_question(q["expectation"],
                                                  reason="run-ended") is None
    assert _question(world, form)["answer"]["label"] == "Deny"


def test_an_answer_in_the_last_moment_is_the_runs(world, ws, monkeypatch):
    """The owner answers after the wait's last look but before it gives up:
    the question is not retired, and the run gets that answer, not a no."""
    monkeypatch.setattr(P, "WAIT_S", 0.5)
    monkeypatch.setattr(P, "POLL_S", 3.0)     # one look, then past the deadline
    cid, turn, exp, run, policy = _policy_world(world, ws)
    obs: dict = {}
    t, got, form = _ask(world, ws, obs, policy, run)
    _answer_form(world, cid, obs, "Allow once")
    t.join(15)
    assert got["a"] == "once"
    q = _question(world, form)
    assert q["answered"] and q["lapsed"] is None
