"""Known quota failures held from automatic selection (runtime capacity,
items 2 and 5, 2026-10-29).

  * MARS's `retryAfterSeconds` survives to the recorded `delivery-failed`
    evidence as `retry_after_s` and an absolute `resets_at`;
  * `quota_holds` reads `rate_limited` failures back from the record: held
    until the reported reset, else for the owner's 60-minute cooldown; cleared
    by a later reported-done run on that runtime that STARTED after the
    failure; dropped once expired; other failures ignored; the history read
    shared while the record holds still;
  * the holds reach `execution_select` from `_dispatch`, and
    `execution_usable` from the posting (`owe`) and `delegate` judges.
"""

from __future__ import annotations

import inspect
import time

import pytest

from mentis.execution import RunResult
from mentis.web import quota as Q
from mentis.web.quota import quota_holds
from tests._loop import a_conversation, say, world  # noqa: F401
from tests._loop import runs  # noqa: F401

RATE_LIMITED = {"error_kind": "rate_limited", "error": "quota reached"}


def _tick():
    """Acts are ordered by `at`; keep consecutive writes apart."""
    time.sleep(0.02)


def _failure(cv, runtime="gemini", evidence=RATE_LIMITED, caused_by=None):
    return cv.record_act(actor="tester", act="delivery-failed",
                         runtime=runtime, caused_by=caused_by,
                         because="terminal 'failed'",
                         detail={"terminal": "failed",
                                 **({"runtime_evidence": dict(evidence)}
                                    if evidence is not None else {})})


def _start(cv, runtime="gemini"):
    return cv.record_act(actor="tester", act="execution-started",
                         runtime=runtime, because="a run")


def _returned(cv, start, runtime="gemini", terminal="reported_done"):
    return cv.record_act(actor="tester", act="result-returned",
                         runtime=runtime, caused_by=start,
                         because="the run reported",
                         detail={"terminal": terminal})


def _at(cv, act):
    return cv._act(act)["at"]


# -- the holds -----------------------------------------------------------------

def test_a_quota_failure_with_no_reset_holds_for_sixty_minutes(world):
    cv = world["cv"]
    failed = _failure(cv)
    at = _at(cv, failed)
    holds = quota_holds(cv, now=at + 10)
    assert set(holds) == {"gemini"}
    h = holds["gemini"]
    assert h["until"] == pytest.approx(at + 3600)
    assert h["since"] == at and h["basis"] == failed and h["model"] is None
    assert h["why"].startswith("gemini hit its quota at ")
    assert h["why"].endswith("(60-minute cooldown, no reset reported)")
    assert time.strftime("%H:%M", time.localtime(at + 3600)) in h["why"]
    # still held just before the cooldown ends; gone at it
    assert "gemini" in quota_holds(cv, now=at + 3599)
    assert quota_holds(cv, now=at + 3600) == {}


def test_a_reported_reset_is_held_to_and_the_model_kept(world):
    cv = world["cv"]
    now = time.time()
    failed = _failure(cv, evidence={**RATE_LIMITED, "retry_after_s": 7200.0,
                                    "resets_at": now + 7200,
                                    "model": "gemini-2.5-pro"})
    h = quota_holds(cv, now=_at(cv, failed) + 3700)["gemini"]
    assert h["until"] == pytest.approx(now + 7200)
    assert h["model"] == "gemini-2.5-pro"
    assert h["why"].endswith("(reported reset)")
    assert quota_holds(cv, now=now + 7201) == {}


def test_a_later_reported_done_run_clears_the_hold(world):
    cv = world["cv"]
    _failure(cv)
    assert "gemini" in quota_holds(cv)
    _tick()
    start = _start(cv)
    _tick()
    # a run that did not report its work done shows nothing
    _returned(cv, start, terminal="failed")
    assert "gemini" in quota_holds(cv)
    _returned(cv, start)
    assert quota_holds(cv) == {}


def test_a_success_that_started_before_the_failure_does_not_clear_it(world):
    cv = world["cv"]
    start = _start(cv)
    _tick()
    failed = _failure(cv)
    _tick()
    _returned(cv, start)
    assert quota_holds(cv)["gemini"]["basis"] == failed


def test_a_success_on_another_runtime_does_not_clear_it(world):
    cv = world["cv"]
    _failure(cv)
    _tick()
    _returned(cv, _start(cv, "codex"), runtime="codex")
    assert set(quota_holds(cv)) == {"gemini"}


def test_an_expired_hold_is_dropped_against_now_each_call(world):
    cv = world["cv"]
    at = _at(cv, _failure(cv))
    assert quota_holds(cv, now=at + 4000) == {}
    # the same record, asked earlier again: expiry is not cached
    assert "gemini" in quota_holds(cv, now=at + 60)


def test_other_failures_are_ignored(world):
    cv = world["cv"]
    _failure(cv, evidence={"error_kind": "agent_error", "error": "exit 1"})
    _failure(cv, evidence={"error_kind": "auth_required"})
    _failure(cv, evidence=None)
    _failure(cv, runtime=None)
    assert quota_holds(cv) == {}


def test_failures_beyond_the_lookback_are_not_read(world, monkeypatch):
    cv = world["cv"]
    asked = {}
    real = cv.history

    def history(**kw):
        if kw.get("act"):
            asked.update(kw)
        return real(**kw)
    monkeypatch.setattr(cv, "history", history)
    quota_holds(cv, now=1_000_000.0)
    assert asked["since"] == 1_000_000.0 - Q.LOOKBACK
    assert Q.LOOKBACK >= 7 * 24 * 3600
    assert asked["newest_first"] is True
    assert set(asked["act"]) == {"delivery-failed", "result-returned"}


def test_the_read_is_shared_until_the_record_moves(world, monkeypatch):
    cv = world["cv"]
    at = _at(cv, _failure(cv))
    reads = []
    real = cv.history

    def history(**kw):
        if kw.get("act"):
            reads.append(kw)
        return real(**kw)
    monkeypatch.setattr(cv, "history", history)
    first = quota_holds(cv, now=at + 1)
    assert quota_holds(cv, now=at + 2) == first
    # expiry is evaluated fresh from the shared read
    assert quota_holds(cv, now=at + 4000) == {}
    assert len(reads) == 1
    # a write moves the record's operational position: read again
    _tick()
    _returned(cv, _start(cv))
    assert quota_holds(cv) == {}
    assert len(reads) == 2


def test_it_is_a_pure_read(world):
    cv = world["cv"]
    _failure(cv)
    before = cv.corpus.advance()
    quota_holds(cv)
    quota_holds(cv, now=time.time() + 10_000)
    assert cv.corpus.advance() == before


# -- MARS's reset time reaches the record (item 2) -----------------------------

def test_mars_retry_after_is_kept_on_the_result():
    from acp import RequestError
    from mentis.execution import RunSpec
    from mentis.execution.mars import MarsExecution
    spec = RunSpec(run_id="r1", backend="gemini", prompt="x", workspace=".")
    exc = RequestError(-32603, "quota",
                       {"mars": {"kind": "rate_limited",
                                 "retryAfterSeconds": 1800}})
    res = MarsExecution._failed_result(spec, time.time(), exc)
    assert res.error_kind == "rate_limited" and res.retry_after_s == 1800.0
    plain = RequestError(-32603, "boom", {"mars": {"kind": "backend_error"}})
    assert MarsExecution._failed_result(spec, 0.0, plain).retry_after_s is None
    assert MarsExecution._failed_result(
        spec, 0.0, ConnectionError("gone")).retry_after_s is None


@pytest.fixture()
def synchronous(world, monkeypatch):
    import mentis.web as web
    from mentis.web import dispatch as D
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: D.dispatch(st, **kw))
    return world


def test_a_rate_limited_reset_reaches_delivery_failed_and_holds(synchronous):
    from acp import RequestError
    from mentis.execution.mars import MarsExecution
    world = synchronous
    st, cv = world["state"], world["cv"]
    ex = st.agents.execution

    def quota(spec):
        return MarsExecution._failed_result(spec, time.time(), RequestError(
            -32603, "You have exhausted your capacity",
            {"mars": {"kind": "rate_limited", "backend": spec.backend,
                      "retryAfterSeconds": 1800}}))
    ex.script = {"codex": quota}
    ada = cv.create_participant("@Ada", about="an agent")
    cid = a_conversation(world)
    say(world, cid, "please", action="ask-participant",
        dispatch=[{"participant": ada, "work": "please", "runtime": "codex"}])
    spec = ex.performed[0]
    failed = [a for a in cv.history(execution=spec.run_id)
              if a["act"] == "delivery-failed"]
    assert len(failed) == 1
    ev = failed[0]["detail"]["runtime_evidence"]
    assert ev["error_kind"] == "rate_limited"
    assert ev["retry_after_s"] == 1800.0
    assert ev["resets_at"] == pytest.approx(ev["finished_at"] + 1800)
    h = quota_holds(cv)["codex"]
    assert h["until"] == pytest.approx(ev["resets_at"])
    assert h["basis"] == failed[0]["id"]
    assert h["why"].endswith("(reported reset)")


# -- the holds reach selection and the judges ----------------------------------

def _capturing(monkeypatch, svc, name, seen, answer=None):
    """Replace `svc.<name>` with one that takes `holds` and records them,
    delegating to the real method (with them, once it accepts them)."""
    real = getattr(svc, name)
    takes = "holds" in inspect.signature(real).parameters

    def fn(*a, holds=None, **kw):
        seen.append(holds)
        if answer is not None:
            got = answer(a, holds)
            if got is not ...:
                return got
        return real(*a, **({"holds": holds} if takes else {}), **kw)
    monkeypatch.setattr(svc, name, fn)


def test_dispatch_selection_receives_the_holds(synchronous, monkeypatch):
    world = synchronous
    st, cv = world["state"], world["cv"]
    ex = st.agents.execution

    def done(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn", text="ok",
                         started_at=now, finished_at=now)
    ex.script = {b["id"]: done for b in ex.backends()}
    failed = _failure(cv, runtime="gemini")
    seen = []
    _capturing(monkeypatch, st.agents, "execution_select", seen)
    ada = cv.create_participant("@Ada", about="an agent")
    cid = a_conversation(world)
    say(world, cid, "please", action="ask-participant",
        dispatch=[{"participant": ada, "work": "please"}])
    assert seen and seen[0]["gemini"]["basis"] == failed


def _held_why(args, holds):
    runtime = args[0]
    return (holds or {}).get(runtime, {}).get("why") or ...


def test_the_posting_judge_receives_the_holds(world, monkeypatch):
    st, cv = world["state"], world["cv"]
    ada = cv.create_participant("@Ada", about="an agent")
    cv.declare_runtime_default(ada, "codex", by=world["who"]["@brian"])
    failed = _failure(cv, runtime="codex")
    seen = []
    _capturing(monkeypatch, st.agents, "execution_usable", seen,
               answer=_held_why)
    cid = a_conversation(world)
    out = say(world, cid, "please", action="ask-participant",
              dispatch=[{"participant": ada, "work": "please"}])
    assert seen and seen[0]["codex"]["basis"] == failed
    # the held default did not bind: selection falls through
    constraints = cv._act(out["expectations"][0])["detail"].get(
        "constraints") or {}
    assert constraints.get("runtime") != "codex"


def test_the_delegate_judge_receives_the_holds(world, runs, monkeypatch):
    from mentis.web import _surface
    from mentis.worker import _operate
    st, cv = world["state"], world["cv"]
    cid = a_conversation(world)
    out = say(world, cid, "do the work", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "the work"}])
    assert "error" not in out, out
    grant = runs[-1]
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=world["who"]["@brian"])
    cv.declare_runtime_default(bob, "codex", by=world["who"]["@brian"])
    failed = _failure(cv, runtime="codex")
    seen = []
    _capturing(monkeypatch, st.agents, "execution_usable", seen,
               answer=_held_why)
    got = _operate(_surface(st), "delegate",
                   {"participant": bob, "work": "theirs"}, grant)
    assert seen and seen[0]["codex"]["basis"] == failed
    child = cv._act(got["expectation"])
    assert (child["detail"].get("constraints") or {}).get("runtime") != "codex"


def test_the_judge_reads_the_holds_only_when_it_judges():
    from mentis.web.dispatch import runtime_judge
    calls = []

    class Svc:
        def execution_usable(self, runtime, requires=(), model=None,
                             holds=None):
            return (holds or {}).get(runtime, {}).get("why")

    judge = runtime_judge(Svc(), holds=lambda: calls.append(1) or
                          {"codex": {"why": "held"}})
    assert calls == []
    assert judge("codex") == "held" and judge("claude") is None
    assert len(calls) == 2
