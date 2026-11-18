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


def test_an_approval_question_says_what_the_work_did_before_its_references(server):
    _, op = server.session()
    cv = server.st.cv
    _, trunk = a_request(op, "Polish the governance forms")
    got = close(op, trunk, outcome="Governance forms polished and serving on TEST",
                approval={"artifacts": ["62aa19589535583d3c2cbc6563832c062623ef89"]})
    asked = [a for a in cv._children(trunk)
             if a["act"] == "expectation-recorded"
             and (a["detail"] or {}).get("expects") == "decision"]
    (decision,) = asked
    question = decision["detail"]["question"]
    lines = question.split("\n")
    assert lines[0] == "Approve this work?"
    assert lines[1] == "Governance forms polished and serving on TEST"
    assert lines[2].startswith("Exact references: artifacts 62aa1958")
    assert got["turn"] in lines[2]


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
