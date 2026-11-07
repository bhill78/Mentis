"""Two delegations to the SAME participant, running at the same time.

HYPOTHESIS (from the Quiet Chat record, where one participant's execution id
was reused across consecutive runs): a second piece of work given to a
participant while its first is still running might attach to the first's
instance, be refused, or have results mixed with it.

What is asserted is the CORRECT behaviour: two distinct executions, each
result attributed to its own expectation, and the parent resumed once, after
both. The first run is held open on a threading.Event inside the fake
runtime's script function (the fakes run the script synchronously in the
dispatching thread, so the first dispatch runs on a worker thread).
"""

from __future__ import annotations

import json
import threading
import urllib.request

from tests._loop import a_conversation, say, world  # noqa: F401
from tests._loop import runs  # noqa: F401


def test_two_concurrent_delegations_to_one_participant_do_not_collide(world):
    import time

    from mentis.execution import RunResult
    from mentis.web import dispatch as D
    from mentis.worker import CAPABILITY_HEADER
    from tests._loop import script_every_backend

    svc = world["state"].agents
    cv = world["cv"]
    caretaker = cv.create_participant("@Caretaker")
    builder = cv.create_participant("@Builder")
    cid = a_conversation(world, "Concurrency")

    def door(token, op, args):
        req = urllib.request.Request(
            world["base"] + "/api/worker", method="POST",
            data=json.dumps({"op": op, "args": args}).encode(),
            headers={"Content-Type": "application/json",
                     CAPABILITY_HEADER: token})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    first_in = threading.Event()
    release = threading.Event()
    ran, lock = [], threading.Lock()
    hand_on = {"args": []}

    def perform(spec):
        token = svc.authority.grant_of(spec.run_id)
        mine = None
        if "[[hand-on]]" in spec.prompt:
            for args in hand_on["args"]:
                door(token, "delegate", args)
        else:
            # The orientation lists sibling posts, so the work is read from
            # the task block that opens the prompt, not searched for.
            mine = ("task-A" if spec.prompt.startswith("# Your task\n\ntask-A")
                    else "task-B")
            with lock:
                ran.append(mine)
            if mine == "task-A":
                first_in.set()
                assert release.wait(30), "first run was never released"
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn",
                         text=("RESULT-" + mine if "[[hand-on]]" not in spec.prompt
                              else "handed on"),
                         started_at=now, finished_at=now)

    script_every_backend(svc, perform)

    asked = say(world, cid, "@Caretaker get two things done",
                action="ask-participant",
                dispatch=[{"participant": caretaker,
                           "work": "two tasks [[hand-on]]"}])
    parent, basis = asked["expectations"][0], asked["turn"]
    hand_on["args"] = [
        {"participant": builder, "work": w, "constraint_basis": basis,
         "return_to_me": True} for w in ("task-A", "task-B")]

    def sent_for(expectation):
        spec = next(s for s in world["sent"]
                    if s.get("expectation") == expectation)
        world["sent"].remove(spec)
        return spec

    D.dispatch(world["state"], **sent_for(parent))
    kids = [a for a in cv.history(caused_by=parent)
            if a["act"] == "expectation-recorded"]
    assert len(kids) == 2
    by_work = {}
    for k in kids:
        spec = next(s for s in world["sent"] if s.get("expectation") == k["id"])
        by_work["task-A" if "task-A" in json.dumps(spec, default=str)
                else "task-B"] = (k["id"], sent_for(k["id"]))
    (a_id, a_spec), (b_id, b_spec) = by_work["task-A"], by_work["task-B"]

    out = {}
    t = threading.Thread(
        target=lambda: out.update(a=D.dispatch(world["state"], **a_spec)))
    t.start()
    try:
        assert first_in.wait(30), "first delegation never started"
        # The first is still running. Dispatch the second now.
        out["b"] = D.dispatch(world["state"], **b_spec)
        assert not out.get("a"), "first run should still be held open"
    finally:
        release.set()
        t.join(60)

    def started(expectation):
        return [a for a in cv.history(caused_by=expectation)
                if a["act"] == "execution-started"][-1]

    sa, sb = started(a_id), started(b_id)
    assert out["b"].get("ok", True) and out["a"].get("ok", True), out
    assert sa["execution"] != sb["execution"], (
        f"both delegations shared execution {sa['execution']}")

    # Each result is attributed to its own expectation: the reply that
    # answers it carries that run's execution and only that run's text.
    bodies = {t["turn"]: json.dumps(t["entry"]["body"])
              for t in cv.turns(cid)}
    for exp, work, started_act in ((a_id, "task-A", sa), (b_id, "task-B", sb)):
        said = [a for a in cv.history(caused_by=exp) if a["act"] == "turn-said"]
        assert len(said) == 1, f"{work}: {len(said)} replies"
        assert said[0]["execution"] == started_act["execution"]
        assert said[0]["detail"]["answers_request"] == exp
        other = "task-B" if work == "task-A" else "task-A"
        body = bodies[said[0]["turn"]]
        assert "RESULT-" + work in body and "RESULT-" + other not in body, body

    # The parent resumed exactly once, after both.
    resumed = [a for a in cv.history(caused_by=parent)
               if a["act"] == "work-resumed"]
    assert len(resumed) == 1
    assert len([s for s in world["sent"]
                if s.get("expectation") == parent]) == 1
