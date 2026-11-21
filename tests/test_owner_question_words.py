"""Questions put to the owner say what is asked, then give exact references.

Task Gravity reconciliation, 2026-11-17: an approval was "Approve this work?"
followed by commit hashes and a post id, and an adoption request named its
material by identifier alone. The words were already in the record.
"""
from tests.test_epistemic_learning import (  # noqa: F401
    built, server, a_request, close,
)


def _text(cv, turn):
    body = cv.corpus.read([turn])[0]["body"]
    return " ".join(p.get("text", "") for p in (body.get("parts") or ())
                    if p.get("type") == "text")


def test_artifact_shorthand_is_atomic_clarification_refusal(server):
    _, op = server.session()
    cv = server.st.cv
    _, trunk = a_request(op, "Polish the governance forms")
    before = len(cv.history()), len(cv.corpus.all_entries())
    status, got = op("record_outcome", expectation=trunk, result="done",
                     outcome="Governance forms polished and serving on TEST",
                     approval={"artifacts": ["62aa19589535583d3c2cbc6563832c062623ef89"]})
    assert status in (400, 403), got
    assert "approval.mode" in str(got)
    assert (len(cv.history()), len(cv.corpus.all_entries())) == before


def test_an_adoption_request_quotes_the_material_it_asks_about(server):
    _, op = server.session()
    cv = server.st.cv
    _, trunk = a_request(op, "Polish the governance forms")
    first = close(op, trunk, result="partial", outcome="under way")
    status, rule = op("record_material", kind="rule", basis=[first["turn"]],
                      body={"text": "Work that materially changes the scope of "
                                    "an authorized request is put to the owner "
                                    "before it is started.",
                            "about": "scope of work requests"})
    assert status == 200, rule
    status, asked = op("request_adoption", entry=rule["entry"],
                       because="a preventive measure only the owner can establish")
    assert status == 200, asked
    (act,) = [a for a in cv.corpus.operational(act="adoption-requested")
              if rule["entry"] in (a["about"] or ())]
    said = _text(cv, cv._act(act["detail"]["ask"])["turn"])
    assert said.startswith("Adoption requested: this rule would stand")
    assert "Work that materially changes the scope" in said
    assert "Why it is put to you: a preventive measure only the owner" in said
    assert said.rstrip().endswith("Exact reference: " + rule["entry"])


def test_unkeyed_invalid_approval_retains_claim_and_diagnostic_without_form(server):
    from mentis.operational import completion
    _, op = server.session()
    cv = server.st.cv
    _, trunk = a_request(op, "Polish the governance forms")
    carrier = cv.assigned_carrier(trunk).get("carrier") or cv._act(trunk)["actor"]
    claim = completion.claim(cv, trunk, {"result": "met", "summary": "polished",
                                       "approval": {"artifacts": ["62aa1958"]}},
                             actor=carrier, via="test")
    detail = cv._act(claim)["detail"]
    assert detail["summary"] == "polished" and detail["result"] == "met"
    assert detail["outcome_unclaimed"]["kind"] == "bad-approval" and "approval" not in detail
    assert completion.reconcile(cv, trunk, claim)["recorded"] == "pending"
    assert not [a for a in cv._children(trunk) if a["act"] == "decision-form"]


def test_claim_time_manual_outcome_refusal_rolls_back_turn_and_claim(server):
    _, op = server.session()
    cv = server.st.cv
    _, trunk = a_request(op, "Polish the governance forms")
    before = len(cv.history()), len(cv.corpus.all_entries())
    status, got = op("record_outcome", expectation=trunk, result="done", outcome="Prepared",
                     approval={"mode": "existing", "form": "opr-0123456789ab",
                               "questions": ["opr-123456789abc"]})
    assert status in (400, 403) and "approval.form" in str(got)
    assert (len(cv.history()), len(cv.corpus.all_entries())) == before


def test_manual_outcome_creates_explicit_question_on_its_checked_result(server):
    from tests.decision_descriptors import question
    _, op = server.session()
    cv = server.st.cv
    _, trunk = a_request(op, "Polish the chart")
    q = question()
    got = close(op, trunk, approval={"mode": "create", "questions": [q]})
    d = cv._act(got["claim"])["detail"]
    form = cv.decision_form(d["approval"])
    assert form["post"] == got["turn"]
    assert form["questions"][0]["presentation"] == q["presentation"]
    assert got["reconciled"]["recorded"] == "pending"
