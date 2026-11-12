import pytest

from mentis import evidence as E
from mentis import suitability as S
from tests.test_suitability import cv  # noqa: F401


def act(cv, name, cause=None, actor="builder", execution=None, **detail):
    return cv.record_act(actor=actor, act=name, caused_by=cause,
                         execution=execution, detail=detail)


def work(cv, **detail):
    return act(cv, "expectation-recorded", actor="owner", **detail)


def start(cv, exp, execution="session", model="model-a", **detail):
    return cv.record_act(actor="builder", act="execution-started", runtime="codex",
                         execution=execution, caused_by=exp,
                         detail={"effective_model": model, "selected_effort": "medium", **detail})


def result(cv, begun, execution="session", **detail):
    return act(cv, "result-returned", begun, execution=execution,
               terminal="reported_done", **detail)


def review(cv, exp, value, actor="reviewer", review_request=None):
    req = review_request or work(cv, repository={"review_of": exp})
    return cv.record_act(actor=actor, act="review-verdict", about=[req], caused_by=req,
                         detail={"verdict": value})


def owner_verdict(cv, exp, value, result=None):
    return cv.record_act(actor="owner", act=E.RESULT_VERDICT, about=[exp],
                         caused_by=exp, detail={"verdict": value, "why": "inspected", "result": result})


def test_claim_is_never_recorded_success_and_normal_exit_is_no_success(cv):
    exp = work(cv)
    begun = start(cv, exp)
    result(cv, begun)
    row = E.classify(cv, begun)
    assert row["level"] is None and row["failure_class"] is None
    act(cv, "outcome-claimed", exp, execution="session", result="met")
    row = E.classify(cv, begun)
    assert row["level"] == "claimed" and row["facts"] == ["claimed"]
    report = E.report(cv, expectation=exp)["models"][0]
    assert report["facts"]["recorded"] == 0
    assert report["levels"]["claimed"] == 1


def test_evidence_ladder_and_reconciliation_provenance(cv):
    exp, before = work(cv), S.standing(cv)
    begun = start(cv, exp)
    result(cv, begun)
    claim = act(cv, "outcome-claimed", exp, execution="session", result="met")
    met = act(cv, "expectation-met", exp, execution="session",
              reconciled_by="mentis", reconciled_from=claim)
    row = E.classify(cv, begun)
    assert row["level"] == "recorded" and row["reconciled_by"] == ["mentis"]
    assert met in row["evidence"]
    review(cv, exp, "pass", actor="builder")
    assert E.classify(cv, begun)["level"] == "recorded"
    review(cv, exp, "pass")
    assert E.classify(cv, begun)["level"] == "verified"
    owner_verdict(cv, exp, "accepted", met)
    assert E.classify(cv, begun)["level"] == "owner_accepted"
    owner_verdict(cv, exp, "rejected", met)
    assert E.classify(cv, begun)["level"] == "owner_rejected"
    assert E.substantive_failure(cv, exp)["started"] == begun
    assert S.standing(cv) == before


def test_implementer_verdict_cannot_verify_and_block_is_substantive(cv):
    exp = work(cv)
    begun = start(cv, exp)
    result(cv, begun)
    cv.record_act(actor="someone", act="review-verdict", about=[exp],
                  caused_by=exp, detail={"verdict": "pass"})
    assert E.classify(cv, begun)["level"] is None
    r = review(cv, exp, "block")
    row = E.substantive_failure(cv, exp)
    assert row["review_verdict"] == "block" and r in row["evidence"]
    assert row["failure_class"] == "substantive"


@pytest.mark.parametrize("detail,why,expected", [
    ({"terminal": "failed", "runtime_evidence": {"error_kind": "rate_limited", "resets_at": 42}}, "", "quota"),
    ({"before_execution_started": True, "requested": {}, "stage": "selection-or-summon"},
     "RuntimeNotPresent: every eligible runtime is exhausted: codex hit its quota", "quota"),
    ({"terminal": "failed", "runtime_evidence": {"error_kind": "permission_denied"}}, "", "permission"),
    ({"terminal": "failed", "runtime_evidence": {"denied": [{"command": "dir"}]}}, "", "permission"),
    ({"before_execution_started": True}, "PermissionError: consent refused", "permission"),
    ({"terminal": "cancelled"}, "owner stopped", "cancelled"),
    ({"terminal": "failed", "runtime_evidence": {"stop_reason": "cancelled"}}, "", "cancelled"),
    ({"terminal": "interrupted"}, "server restarted", "interrupted"),
    ({"terminal": "failed", "runtime_evidence": {"error_kind": "backend_exited", "backend_exit_code": -1}}, "", "infrastructure"),
    ({"terminal": "failed", "terminated_by": {"self": False, "command": "a recorded command"}}, "", "infrastructure"),
    ({"before_execution_started": True, "stage": "repository", "requested": {}}, "workspace cannot open", "infrastructure"),
    ({"terminal": "stopped_at_deadline", "runtime_evidence": {"error_kind": "timeout"}}, "", "infrastructure"),
    ({"before_execution_started": True, "stage": "selection-or-summon", "requested": {"requires": ["build_ui"]}},
     "Unsupported: no available runtime can be given this work: local (build_ui unsupported)", "capability_missing"),
    ({"terminal": "reported_done", "failure_classification": "substantive"}, "", "substantive"),
    ({"terminal": "failed", "error": "something unexplained"}, "", "unclassified"),
    ({"terminal": "reported_done"}, "nothing reported", "unclassified"),
])
def test_realistic_failure_shapes(cv, detail, why, expected):
    exp = work(cv)
    begun = start(cv, exp)
    if detail.get("before_execution_started"):
        cause, execution = exp, None
    else:
        cause, execution = begun, "session"
    f = cv.record_act(actor="builder", act="delivery-failed", caused_by=cause,
                      execution=execution, because=why, detail=detail)
    assert E.failure_class(cv._act(f)) == expected
    latest = E.per_execution(cv, expectation=exp)[-1]
    assert latest["failure_class"] == expected
    assert bool(E.substantive_failure(cv, exp)) == (expected == "substantive")


def test_owner_stop_and_d4_ignores_infrastructure(cv):
    exp = work(cv)
    begun = start(cv, exp)
    act(cv, "execution-stop-asked", begun, actor="owner", execution="session")
    assert E.classify(cv, begun)["failure_class"] == "cancelled"
    assert E.substantive_failure(cv, exp) is None


def test_reused_execution_and_late_owner_verdict_stay_with_explicit_result(cv):
    exp = work(cv)
    first = start(cv, exp)
    returned = result(cv, first)
    second = start(cv, exp, model="model-b")
    result(cv, second)
    v = owner_verdict(cv, exp, "rejected", returned)
    assert E.classify(cv, first)["level"] == "owner_rejected"
    assert v not in E.classify(cv, second)["evidence"]
    assert E.substantive_failure(cv, exp) is None
    owner_verdict(cv, exp, "accepted")
    assert E.classify(cv, second)["level"] == "owner_accepted"


def test_late_reconciliation_and_review_do_not_transfer_to_retry(cv):
    exp = work(cv)
    first = start(cv, exp)
    result(cv, first)
    c = act(cv, "outcome-claimed", exp, execution="session", result="met")
    r = work(cv, repository={"review_of": exp})
    second = start(cv, exp)
    result(cv, second)
    act(cv, "expectation-met", exp, execution="session", reconciled_from=c, reconciled_by="mentis")
    review(cv, exp, "pass", review_request=r)
    assert E.classify(cv, first)["level"] == "verified"
    assert E.classify(cv, second)["level"] is None


@pytest.mark.parametrize("difficulty,solution,reasoning", [
    ("mechanical", "specified", "light"), ("bounded", "unstated", "substantial"),
    ("routine", "specified", "substantial"), ("complex", "open", "deep"),
    ("architecture", "open", "deep"), ("debugging", "open", "deep"),
    ("ordinary", "unstated", "unstated"), ("default", "unstated", "unstated"),
    (None, "unstated", "unstated")])
def test_legacy_profiles(difficulty, solution, reasoning):
    profile = E.requirement_profile({"detail": {"routing": {"difficulty": difficulty}}})
    assert profile["solution"] == solution and profile["reasoning"] == reasoning


def test_report_groups_effective_model_and_profile_values_counts_only(cv):
    baseline = E.report(cv)["attempts"]
    for i in range(3):
        req = {"solution": {"value": "specified", "source": "stated", "from": [str(i)]},
               "reasoning": {"value": "substantial", "source": "stated"},
               "requires": ["build_ui"]}
        exp = work(cv, routing={"requirements": req})
        begun = start(cv, exp, execution=str(i), model="m1" if i < 2 else "m2",
                       selected_model="must-not-count-this")
        result(cv, begun, execution=str(i))
        act(cv, "outcome-claimed", exp, execution=str(i), result="met")
        if i == 0:
            act(cv, "expectation-met", exp, execution=str(i), reconciled_by="mentis")
    report = E.report(cv)
    assert report["attempts"] == baseline + 3
    first = next(g for g in report["models"] if g["model"] == "m1")
    assert first["model"] == "m1" and first["attempts"] == 2
    assert first["facts"] == {"claimed": 2, "recorded": 1, "verified": 0}
    assert first["levels"]["recorded"] == 1 and first["levels"]["claimed"] == 1
    assert E.report(cv, model="m2")["attempts"] == 1
    assert E.report(cv, runtime="no-such")["attempts"] == 0
    assert "score" not in str(report)


def test_before_start_history_does_not_hide_later_attempt(cv):
    exp = work(cv)
    act(cv, "delivery-failed", exp, before_execution_started=True, stage="selection-or-summon")
    begun = start(cv, exp)
    result(cv, begun)
    owner_verdict(cv, exp, "rejected")
    assert E.substantive_failure(cv, exp)["started"] == begun
    assert E.report(cv, expectation=exp)["attempts"] == 2


def test_start_requirements_are_historical_and_unknown_model_stays_unknown(cv):
    exp = work(cv, routing={"difficulty": "complex"})
    begun = start(cv, exp, model=None, requirements={
        "solution": {"value": "specified"}, "reasoning": {"value": "light"}})
    row = E.classify(cv, begun)
    assert row["model"] is None and row["requirements"]["reasoning"] == "light"
