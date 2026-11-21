"""Concrete Ask Mentis selections use the existing Work and execution grants.

All Brains are fixtures; only execution is scripted. Posting, delayed intake,
assignment, authority derivation and permission enforcement are production code.
"""
from __future__ import annotations

import copy
import json
import time
import urllib.error
import urllib.request

import pytest

from mentis.conversation import posting
from mentis.execution import RunResult
from mentis.operational import consent as C, follow_up_of
from mentis.operational.runs import asked_with
from mentis.web import dispatch as D, resume_intake
from mentis.worker import AUTHORITY, may_coordinate
from tests._loop import (a_conversation, grant_of_run, post, say,
                         script_every_backend, world, _written)  # noqa: F401


@pytest.fixture()
def observed(world):
    kept = []
    svc = world["state"].agents

    def perform(spec):
        grant = grant_of_run(svc, spec, world["state"].path)
        start = next(a for a in world["cv"].history(execution=spec.run_id)
                     if a["act"] == "execution-started")
        kept.append({"grant": grant, "start": start, "spec": spec,
                     "consent": C.of_run(world["cv"], start["id"]),
                     "asked_with": asked_with(world["cv"], start)})
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=False, error_kind="test_stop",
                         error="stop after the real grant is minted",
                         started_at=now, finished_at=now)

    script_every_backend(svc, perform)
    return kept


def _run(world, expectation):
    pending = next(k for k in world["sent"] if k["expectation"] == expectation)
    world["sent"].remove(pending)
    D.dispatch(world["state"], **pending)
    return pending


def _post(world, path, body):
    request = urllib.request.Request(world["base"] + path, method="POST",
                                     data=json.dumps(body).encode(), headers={
                                         "Content-Type": "application/json",
                                         "X-Mentis-Client": "1"})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def _unassigned(world, cid, settings, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(world["cv"], "intake_carrier", lambda: {
            "resolved": False, "reason": "none", "detail": "no designation"})
        out = say(world, cid, "carry this", action="ask-mentis",
                  ask_mentis=settings)
    assert not out["assigned"] and not world["sent"]
    return out


@pytest.mark.parametrize("coordinate", [None, True, False])
@pytest.mark.parametrize("delayed", [False, True])
def test_selections_reach_one_assignment_and_actual_grant(
        world, observed, tmp_path, monkeypatch, coordinate, delayed):
    cv = world["cv"]
    cid = a_conversation(world)
    ws = tmp_path / "approved"
    ws.mkdir()
    settings = {"consent": {"mode": "all", "workspaces": [str(ws)],
                            "categories": ["read", "test"]},
                "follow_up": {"depth": 1}}
    if coordinate is not None:
        settings["coordinate"] = coordinate
    expected = posting.ask_mentis_permissions(settings)
    if delayed:
        out = _unassigned(world, cid, settings, monkeypatch)
        exp = out["expectation"]
        assert not cv.authority_of(exp)["act"]
        # Later browser values cannot replace what was recorded at submission.
        settings.update(consent="ask", coordinate=True, follow_up="ask")
        resumed = resume_intake(cv, exp, by=world["who"]["@brian"],
                                enqueue=lambda **kw: world["sent"].append(kw))
        assert resumed["resumed"]
        before = _written(world)
        again = resume_intake(cv, exp, by=world["who"]["@brian"],
                              enqueue=lambda **kw: world["sent"].append(kw))
        assert not again["resumed"] and _written(world) == before
    else:
        out = say(world, cid, "carry this", action="ask-mentis", ask_mentis=settings)
        exp = out["expectation"]
    detail = cv._act(exp)["detail"]
    assert {k: detail[k] for k in expected} == expected
    if coordinate is None:
        assert "coordinate" not in detail
    acts = cv.history(caused_by=exp)
    assert len([a for a in acts if a["act"] == "expectation-assigned"]) == 1
    assert len([a for a in acts if a["act"] == "authority-granted"]) == 1
    assert cv.authority_of(exp)["operations"] == (
        [] if coordinate is False else sorted(AUTHORITY))
    assert not cv.authority_of(exp).get("unresolved")
    _run(world, exp)
    actual = observed[-1]
    assert may_coordinate(actual["grant"]) is (coordinate is not False)
    assert actual["consent"]["mode"] == "all"
    assert str(ws) in actual["consent"]["workspaces"]
    assert actual["consent"]["categories"] == ["read", "test"]
    assert actual["spec"].consent["mode"] == "task"  # existing MARS boundary
    assert actual["asked_with"]["follow_up"] == {"depth": 1}
    assert follow_up_of(cv, exp) == {"depth": 1}


@pytest.mark.parametrize("mode", ["ask", "task", "deny", "all"])
def test_each_consent_mode_reaches_the_execution_policy(world, observed, tmp_path, mode):
    from mentis.web.permissions import make_policy
    from tests.test_run_consent import _shell
    cid = a_conversation(world)
    ws = tmp_path / "approved"
    ws.mkdir()
    out = say(world, cid, "carry this", action="ask-mentis", ask_mentis={
        "coordinate": False, "consent": {"mode": mode, "workspaces": [str(ws)]},
        "follow_up": "ask"})
    _run(world, out["expectation"])
    actual = observed[-1]
    assert actual["consent"]["mode"] == mode
    assert not may_coordinate(actual["grant"])
    assert actual["spec"].consent["mode"] == ("task" if mode == "all" else mode)
    # The existing policy answers real operation requests from the same run.
    policy = make_policy(world["state"])
    request = {**_shell("python -m pytest -q"), "shell_cwd": str(ws),
               "shell": "powershell"}
    run = actual["start"]["id"]
    if mode != "ask":  # Ask deliberately waits for the owner on non-standing operations.
        assert policy(run, "fixture", request, {}) == "once"
    if mode == "deny":
        outside = {**_shell("curl https://example.com"), "shell_cwd": str(ws)}
        assert policy(run, "fixture", outside, {}) == "no"


@pytest.mark.parametrize("route", ["classic", "posts", "requests"])
def test_owner_posting_doors_and_retries_carry_the_whole_object(world, route):
    cid = a_conversation(world)
    body = {"author": world["who"]["@brian"], "text": "carry this",
            "action": "ask-mentis", "op": "permission-request",
            "ask_mentis": {"consent": "all", "coordinate": False,
                           "follow_up": "unrestricted"}}
    if route == "classic":
        path = f"/api/conversations/{cid}/turns"
    elif route == "posts":
        path = "/fluid/api/posts"
        body["conversation"] = cid
    else:
        path = "/fluid/api/requests"
        body["from"] = {"conversation": cid}
    first = _post(world, path, body)
    assert "error" not in first, first
    before = _written(world)
    replay = _post(world, path, body)
    assert replay["replayed"] and replay["turn"] == first["turn"]
    assert _written(world) == before and len(world["sent"]) == 1
    for key, replacement in (("coordinate", True), ("consent", "ask"),
                             ("follow_up", "ask")):
        changed = copy.deepcopy(body)
        changed["ask_mentis"][key] = replacement
        try:
            refused = _post(world, path, changed)
        except urllib.error.HTTPError as exc:
            assert exc.code == 422
            refused = json.loads(exc.read())
        assert "error" in refused, refused
        assert _written(world) == before and len(world["sent"]) == 1


@pytest.mark.parametrize("settings", [
    False, [], "all", {"coordinate": None}, {"coordinate": 1},
    {"coordinate": "false"}, {"runtime": "codex"}, {"authority": ["coordinate"]},
    {"execution_mode": "host"}, {"preset": "default"},
    {"consent": {"mode": "everything"}},
    {"consent": {"workspaces": ["relative"]}},
    {"consent": {"categories": ["everything"]}},
    {"consent": {"mode": "all", "runtime": "codex"}},
    {"follow_up": {"depth": 0}}, {"follow_up": {"depth": True}},
    {"follow_up": {"depth": 1, "other": True}},
])
def test_invalid_or_inappropriate_fields_write_nothing(world, settings):
    cid = a_conversation(world)
    before = _written(world)
    out = say(world, cid, "carry this", action="ask-mentis", ask_mentis=settings)
    assert "error" in out
    assert _written(world) == before and not world["sent"]


def test_protected_or_missing_workspaces_refuse_before_writing(world, tmp_path, monkeypatch):
    cid = a_conversation(world)
    protected = tmp_path / "protected"
    protected.mkdir()
    monkeypatch.setenv("MENTIS_PROTECTED_PATHS", str(protected))
    before = _written(world)
    for path in (protected, tmp_path / "missing"):
        out = say(world, cid, "carry this", action="ask-mentis", ask_mentis={
            "consent": {"mode": "all", "workspaces": [str(path)]}})
        assert "error" in out
        assert _written(world) == before and not world["sent"]


@pytest.mark.parametrize("action", [None, "record-only", "ask-participant"])
@pytest.mark.parametrize("settings", [{}, {"coordinate": False}])
def test_permissions_on_other_actions_are_refused_even_when_empty(world, action, settings):
    cid = a_conversation(world)
    before = _written(world)
    out = say(world, cid, "just record", action=action, ask_mentis=settings)
    assert "error" in out and "ask-mentis" in out["error"]
    assert _written(world) == before and not world["sent"]


def test_record_only_without_permissions_still_owes_nothing(world):
    out = say(world, a_conversation(world), "just record", action="record-only")
    assert out["nothing_is_owed"] and out["expectations"] == []
    assert not world["sent"]


def test_domain_rejects_non_owner_settings(world):
    cid = a_conversation(world)
    before = _written(world)
    out, later = posting.post(world["cv"], world["state"].corpus, cid, {
        "author": world["steward"], "text": "carry this", "action": "ask-mentis",
        "ask_mentis": {"consent": "all", "coordinate": True}},
        written_by=lambda: "fixture")
    assert "only the owner" in out["error"]
    assert not later and _written(world) == before


@pytest.mark.parametrize("route", ["classic", "posts", "requests"])
@pytest.mark.parametrize("worker", [False, True])
def test_owner_doors_refuse_worker_grants_and_missing_owner_session(world, route, worker):
    cid = a_conversation(world)
    body = {"author": world["who"]["@brian"], "text": "carry this",
            "action": "ask-mentis", "op": "refused-owner",
            "ask_mentis": {"consent": "all", "coordinate": True}}
    path = f"/api/conversations/{cid}/turns"
    if route == "posts":
        path = "/fluid/api/posts"
        body["conversation"] = cid
    elif route == "requests":
        path = "/fluid/api/requests"
        body["from"] = {"conversation": cid}
    headers = {"Content-Type": "application/json", "X-Mentis-Client": "1"}
    if worker:
        headers["X-Mentis-Worker"] = world["state"].agents.authority._grant(
            "fixture-worker", world["state"].path)
    else:
        headers["Authorization"] = "Bearer invalid-owner-session"
    before = _written(world)
    request = urllib.request.Request(world["base"] + path, method="POST",
                                     data=json.dumps(body).encode(), headers=headers)
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(request)
    assert refused.value.code == (403 if worker else 401)
    assert _written(world) == before and not world["sent"]


def test_absent_and_empty_transport_preserve_existing_ask_authority(world, observed):
    cid = a_conversation(world)
    for extra in ({}, {"ask_mentis": {}}):
        out = say(world, cid, "carry this", action="ask-mentis", **extra)
        _run(world, out["expectation"])
        assert may_coordinate(observed[-1]["grant"])
        assert observed[-1]["consent"]["mode"] == "ask"
        assert observed[-1]["asked_with"]["follow_up"] == "ask"


def test_resume_and_delegation_use_recorded_values_without_defaults(world, crew, tmp_path):
    from tests.test_work_continuation import _op, _run, _run_child, _pending
    from tests.test_delegate_coordinate import _present
    cv = world["cv"]
    cid = a_conversation(world)
    reviewer = _present(world, cid, "@Reviewer")
    ws = tmp_path / "approved"
    ws.mkdir()
    out = say(world, cid, "carry this and review it", action="ask-mentis", ask_mentis={
        "consent": {"mode": "task", "workspaces": [str(ws)]},
        "coordinate": True, "follow_up": {"depth": 1}})
    exp = out["expectation"]
    crew["on_run"][exp] = [lambda g: _op(
        world, g, "delegate", participant=reviewer, work="review it",
        return_to_me=True, resume_on_return=True, review_of=exp,
        consent={"mode": "all"})]
    _run(world, exp)
    child = crew["results"][-1]
    assert "error" not in child, child
    child_exp = child["expectation"]
    assert C.of_request(cv, child_exp)["mode"] == "task"  # cannot widen
    assert follow_up_of(cv, exp) == {"depth": 1}
    _run_child(world, child)
    assert not may_coordinate(crew["grants"][child_exp][-1])
    assert _pending(world, exp)
    _run(world, exp)
    first, resumed = crew["grants"][exp]
    assert resumed["operations"] == first["operations"]
    assert may_coordinate(resumed)
    assert C.of_request(cv, exp)["mode"] == "task"
    assert len([a for a in cv.history(caused_by=exp)
                if a["act"] == "authority-granted"]) == 1


from tests.test_work_continuation import crew  # noqa: E402,F401
