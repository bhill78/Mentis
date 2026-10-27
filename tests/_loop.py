"""The operating-loop helpers several lifted suites share.

Mark IV kept these inside other test modules (test_operating_loop,
test_work_authority, test_work_resumption, test_decision_withdraw), which are
not lifted. Only the helpers are, here, adapted to `FakeExecution`: where
Mark IV replaced `Foundation._perform`, these script the run on the service's
`Execution` (`mentis.execution.FakeExecution.script`), which is the only
thing replaced -- dispatch, grants, acts and the reply are the real ones.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from mentis.conversation import text
from mentis.execution import RunResult
from mentis.web import _Handler, _State, fixture


# -- a server whose dispatches are captured rather than run (test_operating_loop)

@pytest.fixture()
def world(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    built = fixture.build(str(root))
    state = _State(str(root))

    sent: list[dict] = []

    def capture(st, **kw):
        sent.append(kw)

    import mentis.web as web
    monkeypatch.setattr(web, "dispatch_soon", capture)

    handler = type("H", (_Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    cv = state.cv

    # A Caretaker-shaped designation: one durable Participant, one established
    # Persona, one established link between them. The alias is deliberately
    # NOT "Caretaker": nothing in the mechanism may depend on what it is called.
    steward = cv.create_participant("@Steward", about="carries what nobody was named for")
    persona = cv.define_persona("Steward", "Answer if you can; delegate if you should.")
    designation = cv.designate_intake_carrier(steward, persona)

    yield {"base": f"http://127.0.0.1:{httpd.server_address[1]}",
           "state": state, "cv": cv, "who": built["who"],
           "conversations": built, "sent": sent,
           "steward": steward, "persona": persona,
           "designation": designation, "root": str(root)}
    httpd.shutdown()


def post(world, path, payload):
    req = urllib.request.Request(
        world["base"] + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def get(world, path):
    with urllib.request.urlopen(world["base"] + path) as r:
        return json.loads(r.read())


def a_conversation(world, name="Somewhere"):
    return post(world, "/api/conversations", {"name": name})["conversation"]


def say(world, conversation, textual, **kw):
    return post(world, f"/api/conversations/{conversation}/turns",
                {"author": world["who"]["@brian"], "text": textual, **kw})


# -- the run, and only the run, scripted --------------------------------------

def script_every_backend(svc, fn) -> None:
    """Every backend the service's FakeExecution lists runs `fn(spec)`."""
    ex = svc.execution
    ex.script = {b["id"]: fn for b in ex.backends()}


def grant_of_run(svc, spec, path) -> dict | None:
    """The grant the run behind `spec` actually holds, read while it runs."""
    return svc.authority.grant_for(svc.authority.grant_of(spec.run_id), path)


@pytest.fixture()
def runs(world, monkeypatch):
    """Dispatch for real; every run fails at once, after its grant is minted.

    Returns the grants in dispatch order, so a test reads what a run was
    ACTUALLY permitted rather than what some layer meant to permit.
    (test_work_authority)"""
    import mentis.web as web
    from mentis.web import dispatch as D

    svc = world["state"].agents
    grants: list[dict] = []

    def stop(spec):
        grants.append(grant_of_run(svc, spec, world["state"].path))
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=False, error_kind="test_stop",
                         error="stopped deliberately, once the grant was minted",
                         started_at=now, finished_at=now)

    script_every_backend(svc, stop)
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: D.dispatch(world["state"], **kw))
    return grants


def _answer(world, cid, turn, by):
    """The carrier's result, replying to the Turn it answers -- as dispatch does."""
    return world["cv"].say(cid, by, [text("done, and here is what I found")],
                           replies_to=turn)


def _continue(world, cid, result_turn, carrier, **spec):
    """THE ORDINARY GESTURE: reply in the thread and continue with the carrier."""
    return say(world, cid, "carry on with that", replies_to=result_turn,
               action="ask-participant",
               dispatch=[{"participant": carrier, "work": "carry on", **spec}])


# -- runs that complete as their work text says (test_work_resumption) ---------

@pytest.fixture()
def rt(world, monkeypatch):
    """Runs complete as the work text says: `[[return]]`, `[[refuse]]`,
    `[[fail]]`, and `[[hold:NAME]]` to wait on a barrier until released.
    The grant each run was actually minted is kept."""
    svc = world["state"].agents
    grants, gates = [], {}

    def perform(spec):
        grants.append(grant_of_run(svc, spec, world["state"].path))
        for name, gate in gates.items():
            if f"[[hold:{name}]]" in spec.prompt:
                gate.wait(timeout=10)
        now = time.time()
        if "[[fail]]" in spec.prompt:
            return RunResult(run_id=spec.run_id, backend=spec.backend,
                             started=True, error_kind="agent_error",
                             error="the runtime exited 1",
                             started_at=now, finished_at=now)
        said = ("I will not do this; it is outside what I can do."
                if "[[refuse]]" in spec.prompt else "done: here is the chart")
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn", text=said,
                         started_at=now, finished_at=now)

    script_every_backend(svc, perform)
    return {"grants": grants, "gates": gates}


def _coordinator(world, cid, carrier=None):
    """Owner addresses a carrier and grants THIS work coordination. Its
    dispatch is captured, not run, so the parent is not running."""
    coach = carrier or world["cv"].create_participant("@Coach")
    out = say(world, cid, "@Coach coordinate the chart", action="ask-participant",
              dispatch=[{"participant": coach, "work": "coordinate",
                         "coordinate": True}])
    parent = out["expectations"][0]
    grants = world["state"].agents.authority
    iid = f"coord-{len(grants._grants)}-{parent[-6:]}"
    grants.authorise_for(iid, dict(scope="organising",
                                   operations=world["cv"].authority_of(parent)[
                                       "operations"],
                                   expectation=parent, conversation=cid,
                                   participant=coach, runtime="claude"))
    grant = grants.grant_for(grants._grant(iid, world["state"].path),
                             world["state"].path)
    world["sent"].clear()
    return coach, parent, grant


# -- a decision the owner withdraws (test_decision_withdraw) ------------------

OPTIONS = [{"label": "Strip the dangling links, then migrate",
            "consequence": "all 41,211 migrate; three links are gone"},
           {"label": "Hold the migration",
            "consequence": "nothing changes tonight"}]

REASON = "No longer needed: the migration was cancelled upstream."


def _ask(world, grant, **args):
    """A decision asked as its own Turn, as every one before P9 was."""
    from tests.decision_asked import asked_as_own_turn
    return asked_as_own_turn(world, grant,
                             "How should the three rejects be handled?",
                             options=args.get("options"))


def _withdraw(world, cid, asked, text=REASON, **kw):
    body = {"replies_to": asked["turn"], "action": "record-only",
            "because": f"withdrawing expectation {asked['expectation']}",
            "chose": {"expectation": asked["expectation"], "withdraw": True}}
    body.update(kw)
    return say(world, cid, text, **body)


def _written(world):
    """Everything the record holds, by count: a refusal must change none."""
    cv = world["cv"]
    return (len(cv.history()), len(cv.corpus.all_entries()))


# -- a Participant named the old way (test_participant_rename) -----------------

def named_before_the_rule(cv, alias, about=""):
    """A Participant written the way the record held them before names were
    reserved -- as the live Brain holds @Claude, @Codex and @Antigravity."""
    return cv.corpus.create_and_establish(
        kind="participant", body={"alias": alias, "about": about},
        attributed_to="human")
