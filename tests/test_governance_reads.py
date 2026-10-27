"""The Governance reads: engines that were built and had no caller.

WHAT THESE PIN DOWN.

  `seam.history()` and `stands(as_at=)` are reachable, and the then/now answer
  is TWO answers side by side rather than one merged one.

  An execution sheet distinguishes ABSENT (no delivery record), EMPTY (a record
  listing no behavioural material) and UNKNOWN (the rendered payload, the
  model), and never turns any of them into another.

  The four historical questions answer from the record and state their own
  empty answers; counts are counts of delivery records, and anything no record
  names is UNCOUNTED rather than counted as zero.

  "Since you last looked" is a PAIR OF ARRIVALS and the acts between them.
  Never arrived is absent; one arrival bounds nothing; and there is no
  mark-as-read anywhere.

  The Applies facet says which way material can reach an execution at all, and
  says it from placements and composition scopes rather than from any Kind
  name.
"""

from __future__ import annotations

import time

import pytest

from mentis.conversation import text as text_part
from mentis.conversation import governance as gov
from mentis.web import _State, _routes, fixture


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "corpus"
    fixture.build(str(root))
    st = _State(str(root), str(tmp_path))
    cv = st.cv
    conv = cv.open_conversation("Reads", about="acceptance")
    owner = cv.resolve_participant("@brian")
    agent = cv.resolve_participant("@Ada")
    for p in (owner, agent):
        cv.join(p, conv)
    return {"st": st, "cv": cv, "corpus": st.corpus, "brain": st.brain,
            "conv": conv, "owner": owner, "agent": agent}


def post(world, path, payload):
    return _routes(world["st"], path, {}, payload, "POST")


def get(world, path, query=None):
    q = {k: (v if isinstance(v, list) else [v])
         for k, v in (query or {}).items()}
    return _routes(world["st"], path, q, None, "GET")


def write(world, kind, text, *, establish=True):
    got = post(world, "/api/entries",
               {"kind": kind, "body": {"text": text},
                "attributed_to": world["owner"], "establish": establish})
    assert "entry" in got, got
    return got["entry"]


def deliver(world, *, persona=None, named=(), material=()):
    """One real execution with one real delivery record."""
    cv = world["cv"]
    ex = cv.begin_execution(participant=world["agent"],
                            conversation=world["conv"], persona=persona,
                            material=list(material), runtime="claude")
    comp = cv.compose(conversation=world["conv"], participant=world["agent"],
                      persona=persona, behavioural=list(named),
                      material=ex.material, request="do the thing")
    cv.record_delivery(ex, comp, mechanism="stub")
    cv.end_execution(ex.reference)
    return ex.reference


# -- 1. one item's history ---------------------------------------------------

def test_the_supersession_chain_is_reachable_oldest_first(world):
    a = write(world, "rule", "First.")
    b = write(world, "rule", "Second.")
    post(world, f"/api/entries/{a}/supersede",
         {"replacement": b, "because": "better",
          "attributed_to": world["owner"]})

    got = get(world, "/api/governance/history", {"entry": a})
    assert got["chain"] == [a, b] and got["oldest_first"] is True
    assert [r["entry"] for r in got["timeline"]] == [a, b]


def test_the_timeline_says_established_or_that_nobody_established_it(world):
    proposed = write(world, "rule", "Never established.", establish=False)
    got = get(world, "/api/governance/history", {"entry": proposed})
    row = got["timeline"][0]
    assert row["established"] == [], "nobody did, and that is the sentence"
    assert row["state"] == "candidate"


def test_the_timeline_carries_the_supersession_reason_in_its_own_words(world):
    a = write(world, "rule", "Old.")
    b = write(world, "rule", "New.")
    post(world, f"/api/entries/{a}/supersede",
         {"replacement": b, "because": "the audit asked for a month",
          "attributed_to": world["owner"]})
    row = get(world, "/api/governance/history", {"entry": a})["timeline"][0]
    assert row["superseded_by"][0]["reason"] == "the audit asked for a month"


def test_the_timeline_carries_disputes_open_and_set_aside(world):
    r = write(world, "rule", "Two reviewers.")
    d = post(world, f"/api/entries/{r}/dispute",
             {"because": "one is enough", "attributed_to": world["agent"]})
    post(world, f"/api/entries/{r}/set-aside",
         {"dispute": d["disputed"], "because": "not for releases",
          "attributed_to": world["owner"]})
    post(world, f"/api/entries/{r}/dispute",
         {"because": "still too slow", "attributed_to": world["agent"]})
    row = get(world, "/api/governance/history", {"entry": r})["timeline"][0]
    assert [x["open"] for x in row["disputes"]] == [False, True]
    assert row["state"] == "stands"


def test_history_refuses_an_item_the_record_does_not_hold(world):
    assert "error" in get(world, "/api/governance/history", {"entry": "ent-no"})


# -- 2. standing as at a time ------------------------------------------------

def test_then_and_now_are_two_answers_never_merged(world):
    proposed = write(world, "rule", "Later established.", establish=False)
    before = time.time()
    time.sleep(0.05)            # the clock here ticks coarsely; separate them
    post(world, f"/api/entries/{proposed}/establish",
         {"because": "it holds", "attributed_to": world["owner"]})

    got = get(world, "/api/governance/standing",
              {"entry": proposed, "as_at": str(before)})
    assert got["then"]["state"] == "candidate"
    assert got["now"]["state"] == "stands"
    assert got["changed"] is True
    assert set(got) >= {"then", "now"} and "state" not in got


def test_standing_as_at_needs_a_time_and_an_item(world):
    r = write(world, "rule", "Something.")
    assert "error" in get(world, "/api/governance/standing", {"entry": r})
    assert "error" in get(world, "/api/governance/standing",
                          {"entry": r, "as_at": "yesterday"})


# -- 3. the execution sheet --------------------------------------------------

def test_no_delivery_record_is_absent_and_says_so(world):
    got = get(world, "/api/governance/execution", {"execution": "exe-nobody"})
    assert got["record"] == "absent"
    assert "absent, not empty" in got["why"]
    assert got["persona"]["answer"] == "no_record"


def test_a_record_listing_nothing_is_empty_and_that_is_an_answer(world):
    cv = world["cv"]
    ex = cv.begin_execution(participant=world["agent"], runtime="claude")
    # A composition with no components at all: the record is written and it
    # lists nothing.
    from mentis.conversation import Composition
    cv.record_delivery(ex, Composition((), (), ()), mechanism="stub")
    got = get(world, "/api/governance/execution", {"execution": ex.reference})
    assert got["record"] == "empty" and got["sources"] == 0
    assert "empty, not absent" in got["why"]


def test_sources_are_grouped_by_how_they_reached_the_execution(world):
    persona = [p["id"] for p in world["corpus"].entries_of_kind("persona")
               if world["corpus"].stands(p["id"])["stands"]][0]
    named = write(world, "rule", "Named for this invocation.")
    placed = post(world, f"/api/conversations/{world['conv']}/instructions",
                  {"text": "Answer briefly.", "establish": True,
                   "attributed_to": world["owner"]})["entry"]
    ref = deliver(world, persona=persona, named=[named],
                  material=["supplied just now"])

    got = get(world, "/api/governance/execution", {"execution": ref})
    assert got["record"] == "present"
    groups = got["groups"]
    assert [s["source_id"] for s in groups["persona_selected"]] == [persona]
    assert [s["source_id"] for s in groups["named"]] == [named]
    assert placed in [s["source_id"] for s in groups["placed"]]
    assert groups["supplied"] and groups["orientation"] and groups["request"]


def test_a_record_that_names_no_persona_is_not_none(world):
    ref = deliver(world)
    got = get(world, "/api/governance/execution", {"execution": ref})
    assert got["persona"]["answer"] == "lists_none"
    assert "not the same as none was worn" in got["persona"]["why"]


def test_the_rendered_payload_and_the_model_stay_unknown(world):
    ref = deliver(world)
    got = get(world, "/api/governance/execution", {"execution": ref})
    assert got["rendered_payload"]["known"] is False
    assert got["model"]["known"] is False


def test_invocation_scoped_material_has_no_durable_identity(world):
    ref = deliver(world, material=["supplied just now"])
    got = get(world, "/api/governance/execution", {"execution": ref})
    supplied = got["groups"]["supplied"][0]
    assert supplied["durable"] is False and supplied["text"] is None


# -- 4. the four history questions -------------------------------------------

def test_what_changed_reads_governance_acts_only(world):
    world["cv"].say(world["conv"], world["owner"], [text_part("chatter")])
    r = write(world, "rule", "Something.", establish=False)
    post(world, f"/api/entries/{r}/establish",
         {"attributed_to": world["owner"], "because": "it is right"})

    got = get(world, "/api/governance/questions", {"question": "changed"})
    kinds = {a["what"] for a in got["acts"]}
    assert kinds <= set(gov.GOVERNANCE_ACTS)
    assert "material-established" in kinds
    assert "turn-said" not in kinds
    quoted = [a["because"] for a in got["acts"]
              if a["what"] == "material-established"]
    assert "it is right" in quoted


def test_what_changed_says_its_own_empty_answer(world):
    got = get(world, "/api/governance/questions",
              {"question": "changed", "conversation": world["conv"]})
    assert got["acts"] == [] and got["empty"]


def test_what_executions_received_gives_three_distinct_answers(world):
    cv = world["cv"]
    ref_full = deliver(world)
    empty = cv.begin_execution(participant=world["agent"], runtime="claude")
    from mentis.conversation import Composition
    cv.record_delivery(empty, Composition((), (), ()), mechanism="stub")

    got = gov.what_executions_received(world["brain"],
                                       executions=["exe-never-ran"])
    answers = {r["execution"]: r["answer"] for r in got["executions"]}
    assert answers[ref_full] == "received"
    assert answers[empty.reference] == "empty"
    assert answers["exe-never-ran"] == "absent"


def test_what_was_used_counts_records_and_says_so(world):
    persona = world["cv"].define_persona("Auditor", "Check the numbers.")
    named = write(world, "rule", "Named twice.")
    deliver(world, persona=persona, named=[named])
    deliver(world, persona=persona, named=[named])
    deliver(world)                      # names no Persona at all

    got = get(world, "/api/governance/questions",
              {"question": "used", "conversation": world["conv"]})
    row = [r for r in got["personas"] if r["entry"] == persona][0]
    assert row["records"] == 2
    assert [r["entry"] for r in got["named_material"]] == [named]
    assert got["named_material"][0]["records"] == 2
    assert got["records_naming_no_persona"] == 1
    assert got["counts_are"].startswith("counts of delivery records")


def test_what_was_used_says_who_received_it_and_which_record_was_last(world):
    """A COUNT THAT CAN BE OPENED. "Named in two records" left no way to ask
    who by, and no way to reach the latest of them."""
    persona = world["cv"].define_persona("Auditor", "Check the numbers.")
    named = write(world, "rule", "Named twice.")
    deliver(world, persona=persona, named=[named])
    last = deliver(world, persona=persona, named=[named])

    got = get(world, "/api/governance/questions",
              {"question": "used", "conversation": world["conv"]})
    row = [r for r in got["personas"] if r["entry"] == persona][0]
    assert row["participants"] == [world["agent"]]
    assert row["latest"]["execution"] == last
    assert row["latest"]["participant"] == world["agent"]
    assert row["latest"]["delivery"] and row["latest"]["at"]
    # THE TWO COUNTS ARE DIFFERENT QUESTIONS. `records` counts the records that
    # named it THIS WAY; `records_any_way` counts every record that named it.
    assert row["records"] == 2 and row["records_any_way"] == 2
    assert row["executions"] == 2
    named_row = got["named_material"][0]
    assert named_row["participants"] == [world["agent"]]
    assert named_row["latest"]["execution"] == last


def test_what_was_used_and_the_deliveries_read_cannot_disagree(world):
    """The same answer, asked twice: the question read here is the one
    `deliveries_naming` answers, and it is asked rather than recomputed."""
    persona = world["cv"].define_persona("Auditor", "Check the numbers.")
    deliver(world, persona=persona)

    used = get(world, "/api/governance/questions",
               {"question": "used", "conversation": world["conv"]})
    row = [r for r in used["personas"] if r["entry"] == persona][0]
    naming = get(world, "/api/governance/deliveries", {"entry": [persona]})
    mine = naming["per_entry"][0]
    assert row["latest"]["delivery"] == mine["latest"]
    assert row["participants"] == mine["participants"]
    assert row["records_any_way"] == mine["records"]


def test_a_delivery_record_naming_no_participant_is_counted_on_its_own(world):
    """It is a fact about the record, not a participant with no name."""
    cv = world["cv"]
    persona = cv.define_persona("Auditor", "Check the numbers.")
    ex = cv.begin_execution(participant=None, conversation=world["conv"],
                            persona=persona, runtime="claude")
    comp = cv.compose(conversation=world["conv"], participant=None,
                      persona=persona, material=ex.material,
                      request="do the thing")
    cv.record_delivery(ex, comp, mechanism="stub")
    cv.end_execution(ex.reference)

    got = get(world, "/api/governance/deliveries", {"entry": [persona]})
    mine = got["per_entry"][0]
    assert mine["participants"] == []
    assert mine["records_naming_no_participant"] == 1


def test_what_executions_received_says_which_persona_each_one_received(world):
    """THE THREE PERSONA ANSWERS, ONE PER ROW, and never collapsed: from the
    record, the record lists none, or there is no record to say."""
    cv = world["cv"]
    persona = cv.define_persona("Auditor", "Check the numbers.")
    wearing = deliver(world, persona=persona)
    bare = deliver(world)

    got = gov.what_executions_received(world["brain"],
                                       executions=["exe-never-ran"])
    rows = {r["execution"]: r["persona"] for r in got["executions"]}
    assert rows[wearing] == {"answer": "from_the_record", "persona": persona}
    assert rows[bare]["answer"] == "lists_none"
    assert "not the same as none was worn" in rows[bare]["why"]
    assert rows["exe-never-ran"]["answer"] == "no_record"


def test_the_persona_answer_is_the_same_one_the_execution_sheet_gives(world):
    """One question, one helper: two copies could answer "none" where the
    other says "no record"."""
    persona = world["cv"].define_persona("Auditor", "Check the numbers.")
    for ref in (deliver(world, persona=persona), deliver(world),
                "exe-never-ran"):
        sheet = get(world, "/api/governance/execution", {"execution": ref})
        row = [r for r in gov.what_executions_received(
            world["brain"], executions=[ref])["executions"]
            if r["execution"] == ref][0]
        assert row["persona"] == sheet["persona"], ref


def test_what_ended_keeps_what_ended_and_names_its_replacement(world):
    a = write(world, "rule", "Old.")
    b = write(world, "rule", "New.")
    post(world, f"/api/entries/{a}/supersede",
         {"replacement": b, "because": "better",
          "attributed_to": world["owner"]})
    got = get(world, "/api/governance/questions", {"question": "ended"})
    row = [r for r in got["ended"] if r["entry"] == a][0]
    assert row["state"] == "ended" and row["never_held"] is False
    assert row["replaced_by"] == [b] and row["chain"] == [a, b]
    assert world["corpus"].read([a])[0]["body"]["text"] == "Old."


def test_a_proposal_replaced_before_establishment_never_held(world):
    proposed = write(world, "rule", "Draft.", establish=False)
    post(world, f"/api/entries/{proposed}/revise",
         {"body": {"text": "The revision."}, "because": "tightened",
          "attributed_to": world["owner"]})
    got = get(world, "/api/governance/questions", {"question": "ended"})
    row = [r for r in got["ended"] if r["entry"] == proposed][0]
    assert row["state"] == "replaced" and row["never_held"] is True


def test_an_unknown_question_names_the_four(world):
    got = get(world, "/api/governance/questions", {"question": "vibes"})
    assert "error" in got and len(got["questions"]) == 4


# -- 5. arrivals, and since you last looked ----------------------------------

def test_never_arrived_is_absent_and_not_zero(world):
    got = get(world, "/api/governance/since", {"participant": world["owner"]})
    assert got["arrivals"] == 0 and got["bounded"] is False
    assert got["changed"] is None and "Absent, not zero" in got["why"]


def test_one_arrival_bounds_nothing_and_says_so(world):
    post(world, "/api/governance/arrive", {"participant": world["owner"]})
    got = get(world, "/api/governance/since", {"participant": world["owner"]})
    assert got["arrivals"] == 1 and got["bounded"] is False
    assert "bounds nothing" in got["why"]


def test_a_pair_of_arrivals_bounds_the_acts_between_them(world):
    owner = world["owner"]
    post(world, "/api/governance/arrive", {"participant": owner})
    r = write(world, "rule", "Written between the two looks.", establish=False)
    post(world, f"/api/entries/{r}/establish", {"because": "it holds",
                                                "attributed_to": owner})
    post(world, "/api/governance/arrive", {"participant": owner})

    got = get(world, "/api/governance/since", {"participant": owner})
    assert got["bounded"] is True and got["arrivals"] == 2
    assert got["changed"]["total"] >= 1
    assert r in [a["about"][0] for a in got["changed"]["acts"] if a["about"]]
    assert "no mark-as-read" in got["no_read_marker"]


def test_acts_after_the_latest_arrival_are_outside_the_window(world):
    owner = world["owner"]
    post(world, "/api/governance/arrive", {"participant": owner})
    post(world, "/api/governance/arrive", {"participant": owner})
    r = write(world, "rule", "After both looks.", establish=False)
    post(world, f"/api/entries/{r}/establish", {"because": "it holds",
                                                "attributed_to": owner})
    got = get(world, "/api/governance/since", {"participant": owner})
    assert got["changed"]["total"] == 0


def test_arrivals_are_per_participant(world):
    post(world, "/api/governance/arrive", {"participant": world["owner"]})
    post(world, "/api/governance/arrive", {"participant": world["owner"]})
    got = get(world, "/api/governance/since", {"participant": world["agent"]})
    assert got["arrivals"] == 0


def test_an_arrival_needs_somebody_to_have_arrived(world):
    assert "error" in post(world, "/api/governance/arrive", {})


def test_asking_what_changed_records_nothing(world):
    """There is no mark-as-read anywhere, and reading the catch-up is not one
    by another name: the only last-looked fact is an arrival, and an arrival is
    somebody arriving."""
    owner = world["owner"]
    post(world, "/api/governance/arrive", {"participant": owner})
    post(world, "/api/governance/arrive", {"participant": owner})
    before = len(world["corpus"].operational())
    get(world, "/api/governance/since", {"participant": owner})
    get(world, "/api/governance/questions", {"question": "changed"})
    assert len(world["corpus"].operational()) == before


# -- 6. applies, and per-row conditions --------------------------------------

def test_applies_separates_placed_by_persona_and_when_named(world):
    placed = post(world, f"/api/conversations/{world['conv']}/instructions",
                  {"text": "Answer briefly.", "establish": True,
                   "attributed_to": world["owner"]})["entry"]
    named = write(world, "rule", "Reaches nobody unless named.")
    persona = [p["id"] for p in world["corpus"].entries_of_kind("persona")
               if world["corpus"].stands(p["id"])["stands"]][0]

    got = get(world, "/api/governance/applies")
    by_entry = {r["entry"]: r["applies"] for r in got["rows"]}
    assert by_entry[placed] == "placed"
    assert by_entry[named] == "when_named"
    assert by_entry[persona] == "by_persona"
    assert got["facets"]["any_way"] == len(got["rows"])
    assert "Not a record that anything did" in got["limit"]


def test_applies_can_be_asked_about_named_items_only(world):
    r = write(world, "rule", "One item.")
    got = get(world, "/api/governance/applies", {"entry": [r]})
    assert [x["entry"] for x in got["rows"]] == [r]


def test_conditions_count_delivery_records_and_say_what_of(world):
    persona = world["cv"].define_persona("Auditor", "Check the numbers.")
    named = write(world, "rule", "Named once.")
    before = get(world, "/api/governance/conditions",
                 {"entry": [persona]})["executions_with_records"]
    deliver(world, persona=persona, named=[named])
    deliver(world, persona=persona)

    got = get(world, "/api/governance/conditions",
              {"entry": [persona, named]})
    rows = {r["entry"]: r for r in got["rows"]}
    assert rows[persona]["selected_as_persona_in"] == 2
    assert rows[named]["named_in"] == 1
    assert got["executions_with_records"] == before + 2
    assert "never how good" in got["counts_are"]


def test_an_item_no_delivery_record_names_is_uncounted_not_zero(world):
    r = write(world, "rule", "Never delivered.")
    got = get(world, "/api/governance/conditions", {"entry": [r]})
    row = got["rows"][0]
    assert row["uncounted"] is True
    assert row["why_uncounted"] == "no delivery record names it"


def test_conditions_needs_to_be_asked_about_something(world):
    assert "error" in get(world, "/api/governance/conditions")


# -- 8. which deliveries named a given item ----------------------------------

def test_the_deliveries_that_name_an_item_are_listed_newest_first(world):
    r = write(world, "rule", "Named twice.")
    first = deliver(world, named=[r])
    second = deliver(world, named=[r])

    got = get(world, "/api/governance/deliveries", {"entry": [r]})
    assert got["total"] == 2
    assert [d["execution"] for d in got["deliveries"]] == [second, first]
    row = got["per_entry"][0]
    assert row["answer"] == "named" and row["records"] == 2
    assert row["latest"] == got["deliveries"][0]["delivery"]
    assert row["latest_execution"] == second


def test_a_delivery_row_says_who_where_when_and_how_it_reached(world):
    persona = world["cv"].define_persona("Auditor", "Check the numbers.")
    named = write(world, "rule", "Named for this one.")
    deliver(world, persona=persona, named=[named])

    got = get(world, "/api/governance/deliveries", {"entry": [persona, named]})
    row = got["deliveries"][0]
    assert row["participant"] == world["agent"]
    assert row["runtime"] == "claude"
    assert row["conversation"] == world["conv"]
    assert row["at"]
    # the grouping is the execution sheet's own, read from the recorded scope
    assert [h["how"] for h in row["names"][persona]] == ["persona_selected"]
    assert [h["how"] for h in row["names"][named]] == ["named"]
    assert row["carries"] == [persona, named]


def test_an_item_no_delivery_record_names_is_absent_and_not_zero(world):
    r = write(world, "rule", "Never delivered.")
    got = get(world, "/api/governance/deliveries", {"entry": [r]})
    assert got["deliveries"] == [] and got["total"] == 0
    row = got["per_entry"][0]
    assert row["answer"] == "absent" and row["uncounted"] is True
    assert row["why_uncounted"] == "no delivery record names it"
    assert row["latest"] is None
    assert "no delivery record names any of these" in got["empty"]


def test_two_items_answer_which_records_carry_both(world):
    a = write(world, "rule", "One.")
    b = write(world, "rule", "The other.")
    deliver(world, named=[a, b])
    deliver(world, named=[a])

    got = get(world, "/api/governance/deliveries", {"entry": [a, b]})
    assert got["intersection"]["asked"] == 2
    assert got["intersection"]["records"] == 1
    assert got["intersection"]["executions"] == 1
    assert len(got["intersection"]["deliveries"]) == 1
    both = [d for d in got["deliveries"] if d["carries_all"]]
    assert [d["delivery"] for d in both] == got["intersection"]["deliveries"]
    assert "not that anything followed" in got["intersection"]["means"]


def test_one_item_alone_intersects_nothing_and_says_so(world):
    r = write(world, "rule", "Alone.")
    deliver(world, named=[r])
    got = get(world, "/api/governance/deliveries", {"entry": [r]})
    assert got["intersection"]["records"] is None
    assert "second `entry`" in got["intersection"]["why"]


def test_a_record_listing_no_behavioural_material_is_counted_as_empty(world):
    from mentis.conversation import Composition
    cv = world["cv"]
    r = write(world, "rule", "Named once.")
    deliver(world, named=[r])
    ex = cv.begin_execution(participant=world["agent"], runtime="claude")
    cv.record_delivery(ex, Composition((), (), ()), mechanism="stub")

    got = get(world, "/api/governance/deliveries", {"entry": [r]})
    assert got["records_listing_no_behavioural_material"] >= 1
    assert got["total"] == 1, "an empty record named nothing and claimed nothing"


def test_the_rendered_payload_and_the_model_stay_unknown_on_every_row(world):
    r = write(world, "rule", "Named once.")
    deliver(world, named=[r])
    row = get(world, "/api/governance/deliveries", {"entry": [r]})["deliveries"][0]
    assert row["rendered_payload"]["known"] is False
    assert row["model"]["known"] is False


def test_the_read_is_bounded_and_says_what_it_left_out(world):
    r = write(world, "rule", "Named twice.")
    deliver(world, named=[r])
    deliver(world, named=[r])
    got = get(world, "/api/governance/deliveries", {"entry": [r], "limit": "1"})
    assert got["returned"] == 1 and got["omitted"] == 1
    assert got["total"] == 2, "the count is of records, not of what was returned"
    assert got["per_entry"][0]["records"] == 2


def test_deliveries_can_be_narrowed_to_one_conversation(world):
    cv = world["cv"]
    r = write(world, "rule", "Named in two places.")
    deliver(world, named=[r])
    elsewhere = cv.open_conversation("Elsewhere", about="another room")
    cv.join(world["agent"], elsewhere)
    ex = cv.begin_execution(participant=world["agent"], conversation=elsewhere,
                            runtime="claude")
    comp = cv.compose(conversation=elsewhere, participant=world["agent"],
                      behavioural=[r])
    cv.record_delivery(ex, comp, mechanism="stub")

    here = get(world, "/api/governance/deliveries",
               {"entry": [r], "conversation": world["conv"]})
    assert here["total"] == 1
    assert here["filtered_by"]["conversation"] == world["conv"]
    assert get(world, "/api/governance/deliveries", {"entry": [r]})["total"] == 2


def test_deliveries_needs_items_the_record_actually_holds(world):
    assert "error" in get(world, "/api/governance/deliveries")
    got = get(world, "/api/governance/deliveries", {"entry": ["ent-nobody"]})
    assert got["not_held"] == ["ent-nobody"]


def test_a_supersession_proposal_is_in_what_changed(world):
    """THE ONE NEW GOVERNANCE ACT IS ONE THE CHANGE FEED CAN SEE.

    `propose-supersession` writes `supersession-proposed`, and
    `GOVERNANCE_ACTS` -- which is what "what changed?" selects on -- did not
    list it. A proposal and a dispute between two arrivals reported one act:
    the dispute. The proposal is its own fact, and it is exactly the sort of
    fact somebody arriving needs told, because it establishes nothing and
    ends nothing and is therefore invisible in what stands.
    """
    owner = world["owner"]
    old = write(world, "rule", "Ship on Fridays.")
    new = write(world, "rule", "Ship on Mondays.", establish=False)

    post(world, "/api/governance/arrive", {"participant": owner})
    prop = post(world, f"/api/entries/{old}/propose-supersession",
                {"attributed_to": owner, "replacement": new,
                 "because": "Fridays never worked"})
    assert "error" not in prop, prop
    post(world, f"/api/entries/{new}/dispute",
         {"attributed_to": owner, "because": "Mondays are worse"})
    post(world, "/api/governance/arrive", {"participant": owner})

    got = get(world, "/api/governance/since", {"participant": owner})
    acts = got["changed"]["acts"]
    kinds = [a["what"] for a in acts]
    assert "supersession-proposed" in kinds, kinds
    assert "material-disputed" in kinds, kinds
    assert got["changed"]["total"] == 2, acts

    # AND THE TWO SIDES ARE KEPT APART. `about` carries predecessors AND the
    # replacement in one list, so a reader that listed it flat would name the
    # replacement as one of the things it replaces. The detail says which.
    one = next(a for a in acts if a["what"] == "supersession-proposed")
    assert one["detail"]["replacement"] == new
    assert one["detail"]["predecessors"] == [old]
    assert set(one["about"]) == {old, new}


def test_the_change_feed_advertises_only_acts_it_selects(world):
    """`vocabulary` is what the feed looks for, and it is one list."""
    post(world, "/api/governance/arrive", {"participant": world["owner"]})
    post(world, "/api/governance/arrive", {"participant": world["owner"]})
    got = get(world, "/api/governance/since", {"participant": world["owner"]})
    assert "supersession-proposed" in got["changed"]["vocabulary"]
    assert set(got["changed"]["vocabulary"]) == set(gov.GOVERNANCE_ACTS)
