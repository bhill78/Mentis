"""WS-P (docs/modernization/CONTRACT.md): timing spans, capacity off the dispatch path, the
`mars/backends` cache, and session continuity across runs of the same work.

The execution boundary is tested against a stand-in for `mars stdio`
(`tests/fakes/mars_continuity_stand_in.py`) that either speaks the WS-P keys (`new`, `refuse`)
or does not (`old`). Dispatch is tested with the real dispatch, grants, acts and resumption, and
`FakeExecution` standing in for MARS: `resumes=None` is a MARS without continuity.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from mentis.core import service as service_mod
from mentis.core.service import MentisService
from mentis.execution import FakeExecution, RunResult, RunSpec
from mentis.execution.mars import MarsExecution
from mentis.web import continuity as C
from mentis.web import dispatch as D
from tests._loop import a_conversation, grant_of_run, script_every_backend, world  # noqa: F401
from tests.test_delegate_coordinate import _present

STAND_IN = Path(__file__).with_name("fakes") / "mars_continuity_stand_in.py"


# -- the execution boundary --------------------------------------------------------------------

@pytest.fixture()
def mars(tmp_path):
    made = []

    def start(mode):
        log = tmp_path / f"told-{mode}-{len(made)}.jsonl"
        ex = MarsExecution([sys.executable, str(STAND_IN), str(log), mode], startup_s=30)
        made.append(ex)
        return ex, log

    yield start
    for ex in made:
        ex.close()


def _told(log):
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _spec(tmp_path, run_id, prompt, **kw):
    return RunSpec(run_id=run_id, backend="stand-in", workspace=str(tmp_path), prompt=prompt,
                   **kw)


def test_timing_spans_and_mars_timing_are_recorded(mars, tmp_path):
    ex, _ = mars("new")
    res = ex.perform(_spec(tmp_path, "r1", "the full prompt"))
    assert res.stop_reason == "end_turn"
    t = res.timing
    order = ["loop_entered", "connected", "session_opened", "prompt_sent", "first_event",
             "last_event"]
    assert all(isinstance(t[k], float) for k in order), t
    assert [t[k] for k in order] == sorted(t[k] for k in order)
    assert res.started_at <= t["loop_entered"] <= res.finished_at
    assert t["mars"] == {"spawn_ms": 12, "initialize_ms": 30, "new_session_ms": 40,
                         "load_ms": 0, "resolve_ms": 1}
    assert res.runtime_session == {"token": "rt-0", "backend": "stand-in", "supported": True}
    assert res.resumed is None
    assert ex.generation == 1


def test_a_resumed_session_is_sent_the_continuation(mars, tmp_path):
    ex, log = mars("new")
    first = ex.perform(_spec(tmp_path, "r1", "the full prompt"))
    token = first.runtime_session["token"]
    second = ex.perform(_spec(tmp_path, "r2", "the full prompt again",
                              resume={"token": token}, continuation="only what is new"))
    assert second.resumed == {"asked": True, "resumed": True, "why": "loaded"}
    told = _told(log)
    news = [e for e in told if e["event"] == "new"]
    assert "mars/resume" not in news[0]["meta"]
    assert news[1]["meta"]["mars/resume"] == {"token": token}
    assert [e["text"] for e in told if e["event"] == "prompt"] == [
        "the full prompt", "only what is new"]


def test_a_mars_that_does_not_resume_is_sent_the_full_prompt(mars, tmp_path):
    ex, log = mars("refuse")
    first = ex.perform(_spec(tmp_path, "r1", "the full prompt"))
    second = ex.perform(_spec(tmp_path, "r2", "the full prompt again",
                              resume={"token": first.runtime_session["token"]},
                              continuation="only what is new"))
    assert second.resumed == {"asked": True, "resumed": False, "why": "not loaded"}
    assert [e["text"] for e in _told(log) if e["event"] == "prompt"][-1] == \
        "the full prompt again"


def test_an_older_mars_without_the_keys_works_unchanged(mars, tmp_path):
    ex, log = mars("old")
    first = ex.perform(_spec(tmp_path, "r1", "the full prompt"))
    assert first.stop_reason == "end_turn" and first.text == "ok"
    assert first.runtime_session is None and "mars" not in first.timing
    second = ex.perform(_spec(tmp_path, "r2", "the full prompt again",
                              resume={"token": "anything"}, continuation="only what is new"))
    assert second.resumed["resumed"] is False
    assert [e["text"] for e in _told(log) if e["event"] == "prompt"][-1] == \
        "the full prompt again"


def test_a_per_turn_backend_gives_its_token_on_the_prompt_result(mars, tmp_path):
    """agy: the conversation id is known only after a turn, so `mars/resume` is null on
    session/new and arrives on the session/prompt result; that token is the one kept."""
    ex, log = mars("perturn")
    first = ex.perform(_spec(tmp_path, "r1", "the full prompt"))
    assert first.runtime_session == {"token": "mars1.rt-0", "backend": "stand-in",
                                     "supported": True}
    assert first.timing["mars"]["total_ms"] == 83
    assert first.timing["mars"]["adapter"] == "agy-direct"
    second = ex.perform(_spec(tmp_path, "r2", "the full prompt again",
                              resume={"token": "mars1.rt-0"}, continuation="only what is new"))
    assert second.resumed["resumed"] is True
    assert [e["text"] for e in _told(log) if e["event"] == "prompt"][-1] == "only what is new"
    assert second.runtime_session["token"] == "mars1.rt-0"


# -- mars/backends, cached ---------------------------------------------------------------------

class _CountingMars(FakeExecution):
    """A FakeExecution that says which MARS process answers (`generation`)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.generation = 1
        self.asked = 0
        self.gate = None

    def backends(self):
        self.asked += 1
        if self.gate is not None:
            self.gate.wait(10)
        return super().backends()


def test_backends_are_cached_and_dropped_on_mars_restart_or_age(tmp_path, monkeypatch):
    ex = _CountingMars()
    svc = MentisService(str(tmp_path / "instances"), execution=ex)
    for _ in range(5):
        svc.runtime_names()
        svc.execution_select()
    assert ex.asked == 1, "one dispatch's many reads are one ask"
    ex.generation = 2                                  # MARS restarted
    svc.runtime_names()
    assert ex.asked == 2
    monkeypatch.setattr(service_mod, "BACKENDS_REUSE_S", 0.0)
    svc.runtime_names()
    assert ex.asked == 3, "past its age it is asked again"


def test_an_old_catalogue_is_refreshed_in_the_background(tmp_path, monkeypatch):
    ex = _CountingMars()
    svc = MentisService(str(tmp_path / "instances"), execution=ex)
    svc.runtime_names()
    monkeypatch.setattr(service_mod, "BACKENDS_REFRESH_S", 0.0)
    ex.gate = threading.Event()                        # the refresh is slow
    t0 = time.monotonic()
    assert svc.runtime_names() == ["antigravity", "claude", "codex", "local"]
    assert time.monotonic() - t0 < 2, "the held catalogue answered at once"
    ex.gate.set()
    deadline = time.monotonic() + 5
    while ex.asked < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ex.asked == 2


def test_an_execution_without_a_generation_is_not_cached(tmp_path):
    ex = FakeExecution()
    svc = MentisService(str(tmp_path / "instances"), execution=ex)
    svc.runtime_names()
    ex._backends = ex._backends[:1]
    assert svc.runtime_names() == ["claude"]


# -- capacity: never waited for once one is held ------------------------------------------------

def test_selection_never_waits_for_capacity_once_one_is_held(tmp_path):
    from tests.test_capacity_selection import CountingExecution, TWO, _report, _window
    ex = CountingExecution(TWO, {"claude": _report(_window("five_hour", 1.0, 3600, 18000))},
                           delay=30)
    svc = MentisService(str(tmp_path / "instances"), execution=ex)
    # an OLD answer is held: claude exhausted
    held = {"claude": _report(_window("five_hour", 1.0, 3600, 18000))}
    svc._capacity = (time.monotonic() - 3 * service_mod.CAPACITY_REUSE_S, held, None)
    t0 = time.monotonic()
    sel = svc.execution_select()
    assert time.monotonic() - t0 < 1, "selection did not wait for MARS"
    assert sel.runtime == "codex" and "claude" in sel.excluded
    assert ex.calls == 1, "a newer answer is being read in the background"
    svc.execution_select()
    assert ex.calls == 1, "one read in flight, shared"
    ex.release.set()


def test_dispatch_starts_the_capacity_read_before_selection(world):
    svc = world["state"].agents
    seen = []
    svc.capacity_prime = lambda: seen.append(time.time())
    cid = a_conversation(world)
    pid = world["cv"].create_participant("@Ada")
    D.dispatch(world["state"], conversation=cid, turn=world["cv"].say(
        cid, world["who"]["@brian"], [{"type": "text", "text": "x"}]),
        participant=pid, work="do it")
    assert seen


# -- dispatch: timing on the start and the end -------------------------------------------------

def test_timing_is_on_the_start_and_on_the_end(world):
    cv = world["cv"]
    cid = a_conversation(world)
    owner = world["who"]["@brian"]
    pid = cv.create_participant("@Ada")
    turn = cv.say(cid, owner, [{"type": "text", "text": "do it"}])
    exp = cv.expect(turn, of=pid, kind="result", by=owner, conversation=cid)
    triggered = time.time() - 1
    out = D.dispatch(world["state"], conversation=cid, turn=turn, participant=pid,
                     work="do it", expectation=exp, triggered_at=triggered)
    assert out["ok"], out
    start = next(a for a in cv.history(caused_by=exp) if a["act"] == D.STARTED)
    end = next(a for a in cv.history(caused_by=start["id"]) if a["act"] == D.RETURNED)
    st, en = start["detail"]["timing"], end["detail"]["timing"]
    assert st["triggered_at"] == triggered
    for k in ("selection_started", "selection_done", "started_recorded"):
        assert st["triggered_at"] <= st[k] <= time.time()
    assert "runtime_bound" in st["steps"] and "requirements_read" in st["steps"]
    assert st["selection_started"] <= st["selection_done"] <= st["started_recorded"]
    for k in ("triggered_at", "selection_started", "selection_done", "started_recorded",
              "perform_called", "ended"):
        assert isinstance(en[k], float), k
    assert en["started_recorded"] <= en["perform_called"] <= en["ended"]
    assert "payload_built" in en["steps"] and "composed" in en["steps"]
    assert "timing" not in (end["detail"].get("runtime_evidence") or {})
    # a MARS without continuity: no session token, no continuity
    assert "runtime_session" not in end["detail"] and "continuity" not in end["detail"]


# -- dispatch: a resumed run continues its runtime session -------------------------------------

WRAP_UP = "Wrap up: give me a usable preview of what is finished. Start nothing new."


def _op(world, grant, name, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), name, args, grant)


@pytest.fixture()
def team(world):
    """As `test_follow_up_attach.team`: each run of an expectation in `on_run` first calls its
    next function with the run's grant; one in `hold` waits on its gate. Every run returns."""
    svc = world["state"].agents
    plan = {"on_run": {}, "hold": {}, "results": []}

    def perform(spec):
        grant = grant_of_run(svc, spec, world["state"].path)
        queue = plan["on_run"].get(grant["expectation"]) or []
        if queue:
            plan["results"].append(queue.pop(0)(grant))
        gate = plan["hold"].get(grant["expectation"])
        if gate is not None:
            gate.wait(timeout=120)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done: here is what I did",
                         started_at=now, finished_at=now)

    script_every_backend(svc, perform)
    return plan


def _resumed_with_a_follow_up(world, team, resumes, between=None):
    """The owner's request is carried; its carrier hands a part to a Builder and ends. While
    the Builder still runs, the owner follows up; the carrier is resumed with it. Returns the
    resumed run's spec as sent to MARS, the prompt actually sent, and its end act."""
    from tests.test_follow_up_attach import _ask_mentis, _run, _start
    cv = world["cv"]
    ex = world["state"].agents.execution
    ex.resumes = resumes
    cid = a_conversation(world)
    builder = _present(world, cid, "@Builder-1")
    work = _ask_mentis(world, cid, "Build the feature.")
    parts = []
    team["on_run"][work] = [lambda g: parts.append(
        {**_op(world, g, "delegate", participant=builder, work="part 1", return_to_me=True),
         "participant": builder})]
    _run(world, work)
    t, gate = _start(world, team, parts[0])
    try:
        follow = _ask_mentis(world, cid, WRAP_UP)
        team["on_run"][follow] = [lambda g: _op(world, g, "attach_follow_up", work=work,
                                                because="it wraps up that work")]
        _run(world, follow)
        out = team["results"][-1]
        resume = out["dispatches"][0]
        assert resume["resumed_from"] == out["resumed"]
        if between:
            between(cv, work)
        D.dispatch(world["state"], **resume)
        spec = ex.performed[-1]
    finally:
        gate.set()
        t.join(60)
    starts = [a for a in cv.history(caused_by=work) if a["act"] == D.STARTED]
    end = next(a for a in cv.history(caused_by=starts[-1]["id"]) if a["act"] == D.RETURNED)
    first_end = next(a for a in cv.history(caused_by=starts[0]["id"])
                     if a["act"] == D.RETURNED)
    return {"spec": spec, "end": end, "first_end": first_end, "work": work}


def _sent_for(world, spec):
    ex = world["state"].agents.execution
    return ex.sent[max(i for i, s in enumerate(ex.performed) if s is spec)]


def test_a_resumed_run_is_sent_the_continuation_with_the_follow_up(world, team):
    got = _resumed_with_a_follow_up(world, team, resumes=True)
    spec, end = got["spec"], got["end"]
    token = got["first_end"]["detail"]["runtime_session"]["token"]
    assert spec.resume == {"token": token}
    sent = _sent_for(world, spec)
    assert sent == spec.continuation and sent != spec.prompt
    assert sent.startswith(C.RESUME_NOTICE)
    assert WRAP_UP in sent and "The owner gave a follow-up on this work" in sent
    assert "What this run may do now: scope organising" in sent
    assert sent.rstrip().splitlines()[0] == "# Continuing your session"
    assert "\n# Before you return" in sent
    assert sent.rfind("# Before you return") > sent.rfind(WRAP_UP)
    assert D.REPLY_HEADING not in sent, "the reply format is not sent again"
    # the full composition was still built, for a MARS that would not resume
    assert D.REPLY_HEADING in spec.prompt and WRAP_UP in spec.prompt
    detail = end["detail"]
    assert detail["continuity"]["asked"] and detail["continuity"]["resumed"]
    assert detail["runtime_session"]["token"] == token


def test_a_mars_that_does_not_resume_gets_the_full_prompt(world, team):
    got = _resumed_with_a_follow_up(world, team, resumes=False)
    spec, end = got["spec"], got["end"]
    assert spec.resume is not None
    assert _sent_for(world, spec) == spec.prompt
    assert end["detail"]["continuity"] == {
        "asked": True, "resumed": False, "why": "not resumable here",
        "decided": "same work, participant, runtime and terms"}


def test_an_older_mars_gets_the_full_prompt_and_nothing_is_asked(world, team):
    got = _resumed_with_a_follow_up(world, team, resumes=None)
    spec, end = got["spec"], got["end"]
    assert spec.resume is None and spec.continuation is None
    assert _sent_for(world, spec) == spec.prompt
    assert end["detail"]["continuity"]["asked"] is False
    assert end["detail"]["continuity"]["decided"] == "the earlier run left no runtime session"


def test_narrowed_consent_forces_a_fresh_session(world, team):
    from mentis.operational import consent as _consent

    def narrow(cv, work):
        start = [a for a in cv.history(caused_by=work) if a["act"] == D.STARTED][-1]
        _consent.set_task(cv, start["id"], owner=world["who"]["@brian"],
                          consent={"mode": "deny"}, because="tighter now")
    got = _resumed_with_a_follow_up(world, team, resumes=True, between=narrow)
    spec, end = got["spec"], got["end"]
    assert spec.resume is None
    assert _sent_for(world, spec) == spec.prompt
    assert end["detail"]["continuity"]["decided"] == "fresh session: the run consent changed"


# -- the decision, term by term ----------------------------------------------------------------

BASIS = dict(participant="ent-p", backend="claude", model="opus", context="c#abc",
             authority={"scope": "worker", "organising": [], "permitted": ["respond"]},
             consent={"mode": "task", "workspaces": ["C:/x"], "categories": ["read"]},
             workflow_line=None)


@pytest.mark.parametrize("change, words", [
    ({"participant": "ent-q"}, "a different participant"),
    ({"backend": "codex"}, "a different runtime"),
    ({"model": "sonnet"}, "a different model"),
    ({"context": "c#def"}, "the governing material changed"),
    ({"workflow_line": "This request's Workflow was changed"}, "the Workflow changed"),
    ({"authority": {"scope": "worker", "organising": [], "permitted": []}},
     "what the work may do changed"),
    ({"consent": {"mode": "deny", "workspaces": ["C:/x"], "categories": ["read"]}},
     "the run consent changed"),
])
def test_any_change_of_terms_forces_a_fresh_session(monkeypatch, change, words):
    held = {"token": "t", **C.basis(**BASIS)}
    monkeypatch.setattr(C, "previous_session", lambda *a, **k: (held, None))
    monkeypatch.setattr(D, "withdrawal_of", lambda cv, e: None)
    same, why = C.decide(None, expectation="e", participant="ent-p", resumed_from="r",
                         now=C.basis(**BASIS))
    assert same == {"token": "t"}
    got, why = C.decide(None, expectation="e", participant="ent-p", resumed_from="r",
                        now=C.basis(**{**BASIS, **change}))
    assert got is None and why == f"fresh session: {words}"


def test_only_a_continuation_asks_and_never_a_withdrawn_request(monkeypatch):
    monkeypatch.setattr(C, "previous_session",
                        lambda *a, **k: ({"token": "t", **C.basis(**BASIS)}, None))
    assert C.decide(None, expectation="e", participant="ent-p", resumed_from=None,
                    now=C.basis(**BASIS))[0] is None
    monkeypatch.setattr(D, "withdrawal_of", lambda cv, e: {"act": "w"})
    assert C.decide(None, expectation="e", participant="ent-p", resumed_from="r",
                    now=C.basis(**BASIS)) == (None, "the request was withdrawn")
