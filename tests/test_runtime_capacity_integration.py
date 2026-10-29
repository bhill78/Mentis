"""The five runtime-capacity changes together (owner approval, 2026-10-29), through
real posts and dispatches on a fixture Brain: a quota failure a run records holds
its runtime from automatic selection; a named runtime is kept and disclosed; a
later reported success clears the hold."""

from __future__ import annotations

import time

from mentis.execution import RunResult
from mentis.web.quota import quota_holds
from tests._loop import a_conversation, say, script_every_backend, world  # noqa: F401


def _started(cv, expectation):
    got = [a for a in cv.history(caused_by=expectation) if a["act"] == "execution-started"]
    assert got, "the run did not start"
    return got[-1]["detail"] | {"runtime": got[-1]["runtime"]}


def _script(world, failing):
    def perform(spec):
        now = time.time()
        if spec.backend in failing:
            return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                             error_kind="rate_limited",
                             error="You have exhausted your daily quota on this model.",
                             started_at=now, finished_at=now)
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done: the work is finished.",
                         started_at=now, finished_at=now)
    script_every_backend(world["state"].agents, perform)


def _ask(world, cid, who, runtime=None):
    got = say(world, cid, "do the work", action="ask-participant",
              dispatch=[{"participant": who, "work": "do the work",
                         **({"runtime": runtime} if runtime else {})}])
    assert "error" not in got, got
    return got["expectations"][0]


def test_a_recorded_quota_failure_holds_its_runtime_until_a_later_success(world, monkeypatch):
    import mentis.web as web
    from mentis.web import dispatch as D
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: D.dispatch(world["state"], **kw))
    cv = world["cv"]
    cid = a_conversation(world)
    ada, bob = world["who"]["@Ada"], cv.create_participant("@Bob")
    cv.join(bob, cid)
    _script(world, failing={"codex"})

    # 1. A run named onto codex hits its quota; the record holds codex.
    first = _ask(world, cid, ada, runtime="codex")
    assert _started(cv, first)["runtime"] == "codex"
    holds = quota_holds(cv)
    assert "codex" in holds and "60-minute cooldown" in holds["codex"]["why"]

    # 2. Automatic selection excludes it, and says why.
    for _ in range(3):
        auto = _started(cv, _ask(world, cid, bob))
        assert auto["runtime"] != "codex", "an exhausted runtime was selected automatically"
        assert "excluded as exhausted" in auto["selection_because"]
        assert "codex" in auto["selection_inputs"]["holds"]

    # 3. Named again, it is kept, and the exhaustion is disclosed.
    named = _started(cv, _ask(world, cid, ada, runtime="codex"))
    assert named["runtime"] == "codex"
    assert any("codex" in d for d in named["selection_inputs"].get("disclosed") or [])

    # 4. A later reported success on codex clears the hold.
    _script(world, failing=set())
    _ask(world, cid, ada, runtime="codex")
    assert "codex" not in quota_holds(cv)
