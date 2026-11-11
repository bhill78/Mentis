"""A pre-turn runtime's refused command (Antigravity under consent without
test/build/run): never mistaken for completed work, and recoverable without
widening consent.

MARS (r2-agy) writes agy an explicit `deny: ["command(*)"]` when nothing allows a
command: the refusal comes back to the model as a failed tool call and the turn
goes on (measured live 2026-11-10, agy 1.5.5); MARS reports what was refused in
the prompt result's `_meta["mars/denied"]`. A refusal that still ends the run
(an older MARS, or a refused action no deny rule covers) is `permission_denied`
with `deniedActions`, each naming the command line where agy streamed it.

These pin, on every path:

  * the refused command is named in the run's end act (`runtime_evidence.denied`),
    whether the turn went on or ended;
  * a run that ended on a refusal is never recorded met: no reply, no claim from
    it, and a claim made earlier in it stays pending with the refusal named;
  * a turn that went on past a refusal keeps its work and claim, but a claim
    of met waits for an independent review pass (then met, the refusal noted);
  * consent is never widened for it (nothing is allowed that was not).
"""

from __future__ import annotations

import time

import pytest

from mentis.execution import RunResult, RunSpec
from mentis.execution.mars import MarsExecution
from mentis.operational import completion as C
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_completion_reconcile import _claim, _met, _work
from tests.test_run_consent import ws  # noqa: F401

DIR = {"action": "command", "display_name": "run_command", "command": "dir",
       "message": "permission check failed for command \"dir\": Permission denied "
                  "for command(dir). Matches user-configured deny rule."}


# -- what MARS reports reaches the run ------------------------------------------


def test_a_refusal_that_ended_the_run_names_the_command():
    from acp import RequestError
    spec = RunSpec(run_id="r1", backend="antigravity", prompt="x", workspace=".")
    exc = RequestError(-32603, "action denied by permissions policy", {"mars": {
        "kind": "permission_denied",
        "deniedActions": [{"action": "command", "display_name": "RunCommand",
                           "command": "Get-ChildItem   -Force\n| Select Name"}]}})
    res = MarsExecution._failed_result(spec, 0.0, exc)
    assert res.error_kind == "permission_denied"
    assert res.error.endswith("(refused: command `Get-ChildItem -Force | Select Name`)")
    assert res.denied == [{"action": "command", "display_name": "RunCommand",
                           "command": "Get-ChildItem   -Force\n| Select Name"}]


def test_the_continued_turns_refusals_are_read_from_the_prompt_result():
    """`mars/denied` on the prompt result is read with the same bounds as
    `deniedActions` (string fields only, at most 20)."""
    got = MarsExecution._denied({"deniedActions": [DIR, {"action": "x", "n": 1}, "junk"]
                                 + [DIR] * 30})
    assert got[0] == DIR and got[1] == {"action": "x"} and len(got) == 19  # the first 20 entries, junk skipped
    assert MarsExecution._denied({"deniedActions": None}) is None


# -- through dispatch: the end act, and what the record makes of it -------------


def _dispatch_with(world, monkeypatch, result_of):
    import mentis.web as web
    from mentis.web import dispatch as D
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: D.dispatch(st, **kw))
    st, cv = world["state"], world["cv"]
    st.agents.execution.script = {"antigravity": result_of}
    ada = cv.create_participant("@Ada", about="an agent")
    cid = a_conversation(world)
    say(world, cid, "list the files", action="ask-participant",
        dispatch=[{"participant": ada, "work": "list the files", "runtime": "antigravity"}])
    spec = st.agents.execution.performed[-1]
    acts = cv.history(execution=spec.run_id)
    started = [a for a in acts if a["act"] == "execution-started"]
    assert started, [a["act"] for a in acts]
    exp = started[-1]["caused_by"]
    end = cv.run_end(started[-1]["id"])
    return cv, exp, end


def test_a_run_ended_by_a_refusal_is_failed_named_and_never_met(world, monkeypatch):
    def refuse(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         error_kind="permission_denied",
                         error="action denied by permissions policy (refused: command `dir`)",
                         denied=[DIR], started_at=now, finished_at=now)
    cv, exp, end = _dispatch_with(world, monkeypatch, refuse)
    assert end["act"] == "delivery-failed"
    assert "refused: command `dir`" in end["because"]
    assert end["detail"]["runtime_evidence"]["denied"] == [DIR]
    assert C.refused_in(end) == ["command `dir`"]
    assert not _met(cv, exp)
    assert not [a for a in cv._own_acts(exp) if a["act"] == C.OUTCOME_CLAIMED]


def test_a_turn_that_went_on_past_a_refusal_is_held_until_a_review_passes(world, monkeypatch):
    """The model was handed the refusal, used its other tools and claimed met:
    the work and the claim are kept (the recovery is legitimate, nothing was
    widened), but the claim is not recorded met on the agent's word after a
    refusal -- it waits, the refusal named, for an independent review pass."""
    def recovered(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn",
                         text="The shell was refused; I listed the folder with my "
                              "file tools: a.txt.\n\n```outcome\nresult: met\n"
                              "summary: listed without shell\n```",
                         denied=[DIR], started_at=now, finished_at=now)
    cv, exp, end = _dispatch_with(world, monkeypatch, recovered)
    assert end["act"] == "result-returned"
    assert end["detail"]["runtime_evidence"]["denied"] == [DIR]
    claims = [a for a in cv._own_acts(exp) if a["act"] == C.OUTCOME_CLAIMED]
    assert [c["detail"]["result"] for c in claims] == ["met"]
    assert not _met(cv, exp)
    out = C.reconcile_latest(cv, exp)
    assert out["recorded"] == "pending"
    assert out["reasons"] == ["the runtime refused during its run: command `dir`; "
                              "an independent review must pass first"]


def test_a_review_pass_records_the_held_claim_met_with_the_refusal_noted(world):
    from tests.test_completion_reconcile import _review_of, _run
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    start = _start(cv, exp, cid, who)
    claim = _claim(cv, exp, cid, who)
    cv.record_act(actor=who, act="result-returned", conversation=cid, execution="inst-1",
                  caused_by=start, detail={"runtime_evidence": {"denied": [DIR]}})
    assert C.reconcile(cv, exp, claim)["recorded"] == "pending"
    rex = cv.create_participant("@Rex", about="a reviewer")
    review = _review_of(cv, exp, cid, who, rex)
    _run(cv, review, cid, rex, execution="inst-rex")
    cv.record_act(actor=rex, act="review-verdict", conversation=cid,
                  caused_by=review, about=[review],
                  detail={"verdict": "pass", "summary": "listing checked"})
    got = C.on_review_pass(cv, review)
    assert got and got[0]["recorded"] == "met"
    met = _met(cv, exp)
    assert met[0]["detail"]["reconciled_from"] == claim
    assert met[0]["detail"]["notes"][0] == "the runtime refused during its run: command `dir`"


def test_a_turn_that_went_on_and_claimed_nothing_is_not_met(world, monkeypatch):
    def recovered(spec):
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="I could not run dir.",
                         denied=[DIR], started_at=now, finished_at=now)
    cv, exp, end = _dispatch_with(world, monkeypatch, recovered)
    assert end["act"] == "result-returned"
    assert not _met(cv, exp)


# -- reconciliation, directly ------------------------------------------------------


def _start(cv, exp, cid, who):
    return cv.record_act(actor=who, act="execution-started", conversation=cid,
                         execution="inst-1", runtime="antigravity", caused_by=exp)


def test_a_claim_made_before_the_refusal_ended_the_run_stays_pending_named(world):
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    start = _start(cv, exp, cid, who)
    claim = _claim(cv, exp, cid, who)
    cv.record_act(actor=who, act="delivery-failed", conversation=cid, execution="inst-1",
                  caused_by=start,
                  because="terminal 'failed', exit None: permission_denied: action denied "
                          "by permissions policy (refused: command `dir`)",
                  detail={"runtime_evidence": {"error_kind": "permission_denied",
                                               "denied": [DIR]}})
    out = C.reconcile(cv, exp, claim)
    assert out["recorded"] == "pending"
    assert out["reasons"] == ["its run ended on a permission refusal after the claim: "
                              "command `dir`"]
    assert not _met(cv, exp)


@pytest.mark.parametrize("denied,words", [
    ([{"action": "command"}], ["command"]),
    ([DIR, DIR, {"action": "read_file"}], ["command `dir`", "read_file"]),
    ([{"command": "x"}, "junk", None], []),
    (None, []),
])
def test_refused_in_reads_only_what_was_recorded(denied, words):
    end = {"detail": {"runtime_evidence": {"denied": denied}}}
    assert C.refused_in(end) == words
    assert C.refused_in(None) == [] and C.refused_in({"detail": {}}) == []


# -- consent is never widened -------------------------------------------------------


def test_nothing_is_allowed_ahead_for_narrow_consent(world, ws):
    """The recovery comes from MARS's deny rule, which refuses exactly what was
    refused before: Mentis still allows nothing ahead for read/edit/git."""
    from mentis.operational import consent as K
    from mentis.web.permissions import runtime_options
    from tests.test_run_consent import _contract_of, _policy_world
    narrower = K.consent_value({"mode": "task", "workspaces": [ws["repo"]],
                                "categories": ["read", "edit", "git"]})
    _, _, _, run, _ = _policy_world(world, ws, narrower)
    assert runtime_options(world["cv"], run, ws["repo"], "antigravity",
                           _contract_of("antigravity")) == {}
