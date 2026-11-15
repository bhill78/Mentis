"""B7 effectiveness, completed: the verdict is an `outcome` OF the adopted item
it evaluated, delivery and application are told apart, and an evaluation's
brief shows its request's claims in record order.

Real chokepoints only (the worker door's `record_outcome` -> Hook B), over the
same harness as tests/test_epistemic_learning.py.
"""
from mentis.conversation import ladder
from mentis.conversation import ladder_writes
from mentis.operational import learning as L
from mentis.spine.seam import _Boundary

from tests.test_epistemic_learning import (  # noqa: F401  (fixtures)
    a_request, built, close, server, words_of)


def adopted_lesson(op, cv, cid, earlier_outcome_turn, text):
    status, lesson = op("record_material", kind="lesson",
                        basis=[earlier_outcome_turn],
                        body={"text": text, "limits": "Seen once."})
    assert status == 200, lesson
    ladder_writes.owner_act(cv, lesson["entry"], "adopt",
                            {"because": "fixture owner adoption"},
                            by=cv.resolve_participant("@brian"))
    assert cv.corpus.stands(lesson["entry"])["stands"] is True
    return lesson["entry"]


def deliver(cv, cid, expectation, lesson):
    """What the dispatch boundary writes when it hands a run this item."""
    _Boundary(cv.corpus, conversation=cid).deliver(
        [lesson], mechanism="dispatch", participant=L._carrier(cv, expectation),
        behavioural_sources=[{"source_id": lesson, "source_kind": "lesson",
                              "tier": "adopted", "scope": "question:test",
                              "for_expectation": expectation}])


BACKGROUND = ("A background test left running when a dispatched run ends its "
              "turn dies with the run and gives no result")


def ineffective_case(server):
    grant, op = server.session()
    cv = server.st.cv
    cid, earlier = a_request(op, "Run the margin browser checks for round 8")
    first = close(op, earlier, result="failed", outcome=BACKGROUND)
    lesson = adopted_lesson(op, cv, cid, first["turn"],
                            BACKGROUND + "; the brief has to say to wait for it.")
    _, trunk = op("record_request", conversation=cid,
                  text="Run the margin browser checks for round 9")
    got = close(op, trunk["expectation"], result="failed", outcome=BACKGROUND)
    return op, cv, cid, lesson, trunk["expectation"], got


def test_the_signal_names_the_item_and_tells_delivery_from_application(server):
    op, cv, cid, lesson, trunk, got = ineffective_case(server)
    (fired,) = got["learning"]["fired"]
    assert fired["reading"] == "ineffective"
    assert fired["lesson"] == lesson
    assert fired["context"] == got["turn"]
    # NEVER DELIVERED, NEVER NAMED: said as such, and neither is a verdict.
    assert fired["facts"] == {"lesson": lesson, "delivered": [], "named": False}
    assert "no delivery record says it was given" in fired["because"]
    assert "delivery is not application" in fired["because"]
    (one,) = got["learning"]["opened"]
    said = words_of(cv, one["evaluation"])
    assert "The effectiveness verdict" in said
    assert f"{lesson}: in_context {got['turn']}" in said
    assert "`attempted` is true ONLY if the evidence shows" in said


def test_an_effectiveness_evaluation_stays_pending_until_its_verdict_is_an_outcome_of_the_item(server):
    op, cv, cid, lesson, trunk, got = ineffective_case(server)
    (one,) = got["learning"]["opened"]
    evaluation = one["evaluation"]
    assert L.verdicts_missing(cv, evaluation) == [lesson]

    # Closing it without the verdict: held pending, the item named.
    done = close(op, evaluation, outcome="Weighed it; nothing to record")
    assert done["reconciled"]["recorded"] == "pending", done["reconciled"]
    assert any(lesson in r and "effectiveness verdict not recorded" in r
               for r in done["reconciled"]["reasons"]), done["reconciled"]

    # The verdict, through the ordinary door: an outcome OF the lesson.
    status, verdict = op("record_material", kind="outcome",
                         outcome_of=lesson, in_context=got["turn"],
                         basis=[got["turn"]],
                         body={"text": "Delivered to neither run; no evidence "
                                       "it was applied, so it cannot be said "
                                       "to have failed.",
                               "result": "inconclusive", "attempted": False})
    assert status == 200, verdict
    assert L.verdicts_missing(cv, evaluation) == []
    again = close(op, evaluation, outcome="Verdict recorded: inconclusive",
                  references=[{"ref": verdict["entry"]}])
    assert again["reconciled"]["recorded"] == "met", again["reconciled"]

    # SUBSEQUENT RETRIEVAL: the verdict travels with the lesson, and the
    # lesson's standing is untouched.
    trail = ladder.trailer(cv.corpus, cv, lesson)
    assert [o["id"] for o in trail["outcomes"]] == [verdict["entry"]], trail
    assert trail["outcomes"][0]["result"] == "inconclusive"
    assert cv.corpus.stands(lesson)["stands"] is True
    assert [c["entry"] for c in ladder.cited_by(cv.corpus, lesson)
            if c["relation"] == "outcome-of"] == [verdict["entry"]]


def test_a_met_ending_that_names_a_delivered_item_asks_whether_it_helped(server):
    grant, op = server.session()
    cv = server.st.cv
    cid, earlier = a_request(op, "Run the margin browser checks for round 8")
    first = close(op, earlier, result="failed", outcome=BACKGROUND)
    lesson = adopted_lesson(op, cv, cid, first["turn"], BACKGROUND + ".")
    _, trunk = op("record_request", conversation=cid,
                  text="Run the margin browser checks for round 9")
    deliver(cv, cid, trunk["expectation"], lesson)
    got = close(op, trunk["expectation"],
                outcome=f"Waited for the background test as {lesson} says; "
                        f"it gave its result")
    (fired,) = [f for f in got["learning"]["fired"]
                if f["signal"] == "adoption-effectiveness"]
    assert fired["reading"] == "applied"
    assert fired["lesson"] == lesson
    assert fired["facts"]["named"] is True and fired["facts"]["delivered"]
    assert got["learning"]["opened"], got["learning"]


def test_delivery_alone_is_not_application_and_opens_nothing_on_success(server):
    grant, op = server.session()
    cv = server.st.cv
    cid, earlier = a_request(op, "Run the margin browser checks for round 8")
    first = close(op, earlier, result="failed", outcome=BACKGROUND)
    lesson = adopted_lesson(op, cv, cid, first["turn"], BACKGROUND + ".")
    _, trunk = op("record_request", conversation=cid,
                  text="Run the margin browser checks for round 9")
    deliver(cv, cid, trunk["expectation"], lesson)
    got = close(op, trunk["expectation"], outcome="The checks passed")
    assert got["learning"]["evaluated"] is False, got["learning"]


def test_naming_an_item_the_work_was_never_given_is_not_application(server):
    grant, op = server.session()
    cv = server.st.cv
    cid, earlier = a_request(op, "Run the margin browser checks for round 8")
    first = close(op, earlier, result="failed", outcome=BACKGROUND)
    lesson = adopted_lesson(op, cv, cid, first["turn"], BACKGROUND + ".")
    _, trunk = op("record_request", conversation=cid,
                  text="Run the margin browser checks for round 9")
    got = close(op, trunk["expectation"], outcome=f"Followed {lesson}")
    assert got["learning"]["evaluated"] is False, got["learning"]


def test_the_brief_shows_claims_and_state_in_record_order(server):
    """A not-met claim after the request was recorded met is history beside
    it: the evaluation reads both, in the order they were written."""
    op, cv, cid, lesson, trunk, got = ineffective_case(server)
    # Make a fresh request met first, then claimed not-met.
    _, req = op("record_request", conversation=cid,
                text="Run the margin browser checks for round 10")
    met = close(op, req["expectation"], outcome="The checks ran")
    later = close(op, req["expectation"], result="failed", outcome=BACKGROUND)
    assert cv.expectation_state(req["expectation"])["satisfied_by"]
    (one,) = later["learning"]["opened"]
    said = words_of(cv, one["evaluation"])
    assert "in record order" in said
    met_at = said.index("recorded MET")
    not_met_at = said.index("claim not-met")
    assert said.index("claim met") < met_at < not_met_at, said
    assert "reopens nothing" in said
