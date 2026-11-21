"""Independent reviewer's probes for commit 74f5a045 (not the builder's tests).

Each probe asks something the builder's suite does not: what a coordination-off
carrier may actually CALL, whether a refused submission poisons its op key,
whether an untouched Ask Mentis still records the same detail it did before,
and whether two requests left unassigned under different selections keep their
own when "all" is resumed.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pytest

from mentis.execution import RunResult
from mentis.web import dispatch as D, resume_intake
from tests._loop import (a_conversation, grant_of_run, say,
                         script_every_backend, world, _written)  # noqa: F401


@pytest.fixture()
def observed(world):
    kept = []
    svc = world["state"].agents

    def perform(spec):
        kept.append({"grant": grant_of_run(svc, spec, world["state"].path),
                     "spec": spec})
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=False, error_kind="test_stop", error="stop",
                         started_at=now, finished_at=now)

    script_every_backend(svc, perform)
    return kept


def _run(world, expectation):
    pending = next(k for k in world["sent"] if k["expectation"] == expectation)
    world["sent"].remove(pending)
    D.dispatch(world["state"], **pending)
    return pending


# -- A. What a coordination-off carrier may actually call ---------------------

def test_coordination_off_carrier_keeps_what_carrying_needs(world, observed):
    """`off grants none` is the approved behaviour; this says what it costs.

    The carrier must still be able to answer the owner's question, hand work
    on, and ask the owner a decision. It must lose organising.
    """
    cid = a_conversation(world)
    off = say(world, cid, "carry this", action="ask-mentis",
              ask_mentis={"coordinate": False})
    _run(world, off["expectation"])
    narrow = observed[-1]["grant"]
    on = say(world, cid, "carry this too", action="ask-mentis")
    _run(world, on["expectation"])
    wide = observed[-1]["grant"]

    from mentis.worker import permitted
    assert narrow["scope"] == "worker" and wide["scope"] in ("organising", "intake")
    may_narrow = set(permitted(narrow["scope"], narrow.get("operations")))
    may_wide = set(permitted(wide["scope"], wide.get("operations")))
    # Carrying the work itself survives coordination off.
    for keeps in ("delegate", "request_decision", "request_input",
                  "record_discovered_work", "await_work", "arm_detached",
                  "orient", "recall", "brief", "resolve", "find",
                  "claim_resource", "return_artifact", "change_workflow"):
        assert keeps in may_narrow, keeps
    # Organising does not.
    lost = may_wide - may_narrow
    assert lost == {"respond", "open_topic", "open_conversation",
                    "summon_participant", "propose_material", "deep_dive",
                    "resume_intake"}, sorted(lost)


# -- B. A refused submission must not poison its operation key ---------------

def test_refused_submission_leaves_its_op_key_usable(world):
    cid = a_conversation(world)
    body = {"author": world["who"]["@brian"], "text": "carry this",
            "action": "ask-mentis", "op": "one-key",
            "ask_mentis": {"consent": {"mode": "everything"}}}

    def send(payload):
        request = urllib.request.Request(
            world["base"] + f"/api/conversations/{cid}/turns", method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as answer:
                return json.loads(answer.read())
        except urllib.error.HTTPError as exc:
            return json.loads(exc.read())

    before = _written(world)
    refused = send(body)
    assert "error" in refused and _written(world) == before
    # The owner corrects the value and sends again under the same key.
    body["ask_mentis"] = {"consent": {"mode": "all"}}
    accepted = send(body)
    assert "error" not in accepted, accepted
    assert accepted.get("expectation")


# -- C. An untouched Ask Mentis records what it recorded before ---------------

def test_untouched_intake_records_no_permission_detail(world, observed):
    cid = a_conversation(world)
    out = say(world, cid, "carry this", action="ask-mentis")
    detail = world["cv"]._act(out["expectation"])["detail"] or {}
    assert not ({"consent", "coordinate", "follow_up"} & set(detail))
    _run(world, out["expectation"])
    assert observed[-1]["grant"]["scope"] in ("organising", "intake")


# -- D. Two late intakes keep their own selections through resume "all" ------

def test_resume_all_gives_each_request_its_own_selections(
        world, observed, monkeypatch, tmp_path):
    cv = world["cv"]
    cid = a_conversation(world)
    ws = tmp_path / "approved"
    ws.mkdir()
    with monkeypatch.context() as patch:
        patch.setattr(cv, "intake_carrier", lambda: {
            "resolved": False, "reason": "none", "detail": "no designation"})
        off = say(world, cid, "the quiet one", action="ask-mentis",
                  ask_mentis={"coordinate": False,
                              "consent": {"mode": "deny"}})
        on = say(world, cid, "the loud one", action="ask-mentis",
                 ask_mentis={"coordinate": True,
                             "consent": {"mode": "all",
                                         "workspaces": [str(ws)]}})
    assert not off["assigned"] and not on["assigned"]
    resumed = resume_intake(cv, "all", by=world["who"]["@brian"],
                            enqueue=lambda **kw: world["sent"].append(kw))
    assert len(resumed["resumed"]) == 2 and not resumed["refused"], resumed
    assert cv.authority_of(off["expectation"])["operations"] == []
    assert cv.authority_of(on["expectation"])["operations"]

    from mentis.operational import consent as C
    _run(world, off["expectation"])
    quiet_start = next(a for a in cv.history(execution=observed[-1]["spec"].run_id)
                       if a["act"] == "execution-started")
    assert C.of_run(cv, quiet_start["id"])["mode"] == "deny"
    _run(world, on["expectation"])
    loud_start = next(a for a in cv.history(execution=observed[-1]["spec"].run_id)
                      if a["act"] == "execution-started")
    assert C.of_run(cv, loud_start["id"])["mode"] == "all"
