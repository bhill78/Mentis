"""The scope and repeated-failure detectors read recorded events, not words.

Regression cases from the Task Gravity reconciliation (2026-11-17, evidence in
`C:\\Work\\Mentis-env\\evidence\\task-gravity`). On TEST, 133 of 137 scope
signals came from matching the words of a prohibition against a child's text,
77 of 85 repeated-failure signals had no recorded failure, later owner
instructions were never read, material earlier evaluations wrote was cited as
prior failure, and the same delegation was evaluated again as it gained acts.
Each case below is one of those, with the genuine cases beside them.
"""
import pytest

from mentis.conversation import text as text_part
from mentis.operational import completion
from tests.test_epistemic_learning import (  # noqa: F401
    built, server, a_request, helper, hand_out, close, opened_acts,
    words_of, L,
)
from tests.test_epistemic_run_failures import failed_after_start


# -- the record shapes these read, made the way the record makes them ---------

def owner_request(cv, cid, owner, agent, words):
    """A request the owner asked for and an agent carries."""
    turn = cv.say(cid, owner, [text_part(words)], addressed_to=[agent])
    request = cv.expect(turn, of=agent, kind="result", by=owner)
    # THE ORDINARY PATH WRITES AN ASSIGNMENT, BY THE OWNER, TO THE CARRIER
    # (`posting`): its actor is who assigned, not who carries.
    cv.assign(request, agent, by=owner, because="addressed to them")
    return request


def handed(cv, cid, by, who, under, words):
    """Work handed out under `under`: the child request and its
    `work-delegated` act, as `delegate` records them."""
    turn = cv.say(cid, by, [text_part(words)], addressed_to=[who])
    child = cv.expect(turn, of=who, kind="result", by=by, caused_by=under)
    cv.record_act(actor=by, act="work-delegated", conversation=cid, turn=turn,
                  caused_by=under, about=[child])
    return child


def claimed_met(cv, request, by, summary="done as asked"):
    return completion.claim(cv, request, {"result": "met", "summary": summary},
                            actor=by, via="test")


def approval_answered(cv, cid, request, owner, agent, label="Revise"):
    """The approval a claim asks for, and the owner's answer to it: a decision
    request recorded under the work, and `decision-answered` by the person it
    was asked of (the shape of opr-dbe71063566f / opr-7973a46d2b6b on TEST)."""
    turn = cv.say(cid, agent, [text_part("Approve this work?")],
                  addressed_to=[owner])
    decision = cv.expect(turn, of=owner, kind="decision", by=agent,
                         caused_by=request,
                         because="a decision only the owner can make")
    return cv.record_act(actor=owner, act="decision-answered",
                         conversation=cid, turn=turn, caused_by=decision,
                         because="answered by the person it was asked of",
                         detail={"label": label, "option": 1})


def scope_fired(cv, request):
    got = L.signals(cv, request)
    return [s for s in got["fired"] if s["signal"] == "scope-expansion"], got


@pytest.fixture()
def world(server):
    grant, op = server.session()
    cv = server.st.cv
    cid, spare = a_request(op, "Somewhere to summon a builder")
    who = helper(op, cid, spare, alias="@Builder-Detectors")
    return {"op": op, "cv": cv, "cid": cid, "agent": grant["participant"],
            "who": who, "owner": cv.resolve_participant("@brian"),
            "server": server}


# -- scope: the wording of a prohibition is not an event -----------------------

def test_a_prohibition_naming_codex_does_not_flag_the_delegation_it_ordered(world):
    """opr-9b5dfee81922: "Delegate ... to Codex" and "Do not substitute a
    Claude-generated design for Codex's work". The delegation to Codex was
    flagged on "design" and "Codex", and the summaries on "Codex"."""
    op, cv = world["op"], world["cv"]
    cid, trunk = a_request(
        op, "You remain the coordinator. Delegate the actual redesign and "
            "interactive prototype to Codex. Do not substitute a "
            "Claude-generated design for Codex's work. No production "
            "deployment. Never stop other agents' processes.")
    hand_out(op, world["who"], "Codex: produce the navigation redesign and "
                               "the interactive design prototype", cid, trunk)
    got = close(op, trunk, result="partial",
                outcome="Delegated the design and navigation prototype to "
                        "Codex; the deployment waits; the process tree is "
                        "unchanged")
    learned = got["learning"]
    assert learned["fired"] == [], learned["fired"]
    assert learned["evaluated"] is False
    assert opened_acts(cv) == []


def test_an_outcome_that_mentions_what_was_excluded_is_not_the_excluded_act(world):
    """opr-4453c8ca780e: "never stop other agents' processes" against an
    outcome mentioning a "process tree"."""
    op, cv = world["op"], world["cv"]
    _, trunk = a_request(op, "Deploy the candidate to TEST. Never stop other "
                             "agents' processes. Do not deploy to production.")
    got = close(op, trunk, outcome="Deployed to TEST; the process tree of the "
                                   "other agents was inspected; production "
                                   "untouched")
    assert got["learning"]["fired"] == []
    assert opened_acts(cv) == []


# -- scope: work after a met claim, and what the owner did in between ---------

def test_work_handed_out_after_a_met_claim_with_nothing_from_the_owner_fires(world):
    cv, cid = world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"],
                        "Polish the governance forms")
    before = handed(cv, cid, world["agent"], world["who"], req, "The polish")
    claim = claimed_met(cv, req, world["agent"])
    after = handed(cv, cid, world["agent"], world["who"], req,
                   "A redesign nobody asked for")
    fired, _ = scope_fired(cv, req)
    (one,) = fired
    assert one["subject"] == ["after-met", after]
    assert one["basis"] == L.OBSERVED
    assert one["evidence"][:2] == [after, claim]
    assert before not in one["evidence"]


def test_a_later_owner_answer_authorizes_what_follows_it(world):
    """opr-e56371b90f24: claimed met 17:15, the owner answered "Revise" 17:28,
    the redesign was delegated 17:32 and flagged 17:33."""
    cv, cid = world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"],
                        "Polish the governance forms")
    claimed_met(cv, req, world["agent"])
    answer = approval_answered(cv, cid, req, world["owner"], world["agent"])
    redesign = handed(cv, cid, world["agent"], world["who"], req,
                      "Task-first redesign of the governance forms")
    fired, got = scope_fired(cv, req)
    assert fired == []
    (row,) = [r for r in got["ruled_out"] if r["ref"] == redesign]
    assert row["reason"] == "owner-authorized"
    assert answer in row["because"]
    assert not L.consider(cv, req, trigger="run-ended")["evaluated"]


def test_work_handed_out_before_the_owner_answered_is_still_seen(world):
    """The owner's later answer does not reach back: work handed out between
    the claim and their answer was handed out with nothing from them."""
    cv, cid = world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"],
                        "Polish the governance forms")
    claimed_met(cv, req, world["agent"])
    early = handed(cv, cid, world["agent"], world["who"], req, "Ahead of them")
    approval_answered(cv, cid, req, world["owner"], world["agent"])
    later = handed(cv, cid, world["agent"], world["who"], req, "As they said")
    fired, _ = scope_fired(cv, req)
    assert [s["subject"] for s in fired] == [["after-met", early]]
    assert all(later not in s["evidence"] for s in fired)


def test_work_the_owner_recorded_under_it_themselves_is_theirs(world):
    cv, cid = world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"],
                        "Polish the governance forms")
    claimed_met(cv, req, world["agent"])
    theirs = handed(cv, cid, world["owner"], world["who"], req,
                    "Also do the record pages")
    then = handed(cv, cid, world["agent"], world["who"], req,
                  "The record pages, as the owner then asked")
    fired, got = scope_fired(cv, req)
    assert fired == []
    assert {r["ref"]: r["reason"] for r in got["ruled_out"]
            if r["ref"] in (theirs, then)} == {theirs: "owner-authorized",
                                               then: "owner-authorized"}


def test_an_agent_carrying_its_own_request_does_not_authorize_itself(world):
    """A hand-started session records the request it carries. Its own later
    acts are not the owner's."""
    op, cv = world["op"], world["cv"]
    cid, trunk = a_request(op, "Polish the governance forms")
    close(op, trunk)
    grew = hand_out(op, world["who"], "A redesign nobody asked for", cid, trunk)
    fired, _ = scope_fired(cv, trunk)
    assert [s["subject"] for s in fired] == [["after-met", grew]]


def test_independently_authorized_sibling_work_is_not_this_requests(world):
    """Two requests of the owner's in one Conversation. Work under the second,
    handed out after the first was claimed met, is not work under the first."""
    cv, cid = world["cv"], world["cid"]
    first = owner_request(cv, cid, world["owner"], world["agent"],
                          "Polish the governance forms")
    claimed_met(cv, first, world["agent"])
    second = owner_request(cv, cid, world["owner"], world["agent"],
                           "Redesign the Sources browser")
    handed(cv, cid, world["agent"], world["who"], second, "The redesign")
    for _ in range(2):
        failed_after_start(cv, cid, second)
    got = L.signals(cv, first)
    assert got["fired"] == []


# -- scope: discovered work pursued past its permission -----------------------

def test_a_finding_pursued_without_permission_or_choice_fires(world):
    op, cv = world["op"], world["cv"]
    cid, trunk = a_request(op, "Add a Jump to latest control")
    status, found = op("record_discovered_work", under=trunk,
                       work="Rewrite the release helper's retention",
                       because="real, and not this work")
    assert status == 200, found
    finding = found["expectation"]
    assert scope_fired(cv, trunk)[0] == []          # recorded and left: deferred
    started = cv.record_act(actor=world["agent"], act="execution-started",
                            conversation=cid, turn=cv._act(finding)["turn"],
                            execution="fixture-pursuit", runtime="claude",
                            caused_by=finding, because="taken up regardless")
    (one,), _ = scope_fired(cv, trunk)
    assert one["subject"] == ["finding-pursued", finding]
    assert one["basis"] == L.OBSERVED
    assert one["evidence"] == [finding, started]
    assert "permission on it does not cover" in one["because"]


# -- repeated failure: failed runs on this request, and nothing else ----------

def test_partial_progress_is_not_a_failure(world):
    """68 of 85 signals on TEST fired on a `partly` claim, with words in
    common with some unadopted entry somewhere in the Brain."""
    op, cv = world["op"], world["cv"]
    status, note = op("record_material", kind="note", body={
        "text": "Accepted the verified list padding fix; other workstreams "
                "remain running and integration waits"})
    assert status == 200, note
    cid, trunk = a_request(op, "Integrate the Quiet Chat polish")
    for said in ("Accepted the verified list padding fix; other workstreams "
                 "remain running",
                 "Checked typography; integration waits for the running "
                 "preview correction"):
        got = close(op, trunk, result="partial", outcome=said)
        assert got["learning"]["fired"] == [], got["learning"]["fired"]
    assert opened_acts(cv) == []


def test_failures_and_similar_words_elsewhere_are_not_this_requests(world):
    """134 of 255 cited "prior" records on TEST came from other
    Conversations."""
    op, cv = world["op"], world["cv"]
    cid, other = a_request(op, "Run the browser checks for round 5")
    for _ in range(3):
        failed_after_start(cv, cid, other)
    close(op, other, result="failed",
          outcome="The browser checks crashed before reporting, quota "
                  "exhausted")
    status, said = op("record_material", kind="note", body={
        "text": "The browser checks crashed before reporting when quota was "
                "exhausted"})
    assert status == 200, said
    _, opened = op("open_conversation", name="Elsewhere")
    status, here = op("record_request", conversation=opened["conversation"],
                      text="Run the browser checks for round 6")
    assert status == 200, here
    trunk = here["expectation"]
    failed_after_start(cv, opened["conversation"], trunk)   # one: no recurrence
    got = close(op, trunk, result="partial",
                outcome="The browser checks crashed before reporting, quota "
                        "exhausted")
    fired = [s for s in got["learning"]["fired"]
             if s["signal"] == "repeated-failure"]
    assert fired == [], fired


def test_repeated_failed_runs_on_one_request_fire_with_those_runs_as_evidence(world):
    op, cv = world["op"], world["cv"]
    cid, trunk = a_request(op, "Run the browser checks")
    one = failed_after_start(cv, cid, trunk)
    assert [r["reason"] for r in L.signals(cv, trunk)["ruled_out"]
            if r["signal"] == "repeated-failure"] == ["first-of-its-kind"]
    two = failed_after_start(cv, cid, trunk)
    (fired,) = [s for s in L.signals(cv, trunk)["fired"]
                if s["signal"] == "repeated-failure"]
    assert fired["evidence"] == [one, two]
    assert fired["basis"] == L.OBSERVED
    assert fired["subject"] == ["failed-runs", one]


def test_a_run_somebody_stopped_is_not_a_failed_run(world):
    op, cv = world["op"], world["cv"]
    cid, trunk = a_request(op, "Run the browser checks")
    for _ in range(3):
        failed_after_start(cv, cid, trunk, detail={"terminal": "cancelled"})
    assert L.signals(cv, trunk)["fired"] == []


def test_a_clean_completion_after_failures_is_not_a_repeated_failure(world):
    op, cv = world["op"], world["cv"]
    cid, trunk = a_request(op, "Run the browser checks")
    for _ in range(2):
        failed_after_start(cv, cid, trunk)
    got = close(op, trunk, outcome="Browser checks passed")
    assert [s for s in got["learning"]["fired"]
            if s["signal"] == "repeated-failure"] == []


# -- evaluations do not feed evaluations, and are not opened twice ------------

def test_what_an_evaluation_wrote_is_never_evidence_of_a_later_failure(world):
    """19 entries recorded by evaluations were cited 44 times by 34 later
    ones on TEST, outright dismissals among them (ent-2b4478bf27fb)."""
    op, cv, server = world["op"], world["cv"], world["server"]
    cid, trunk = a_request(op, "Run the browser checks")
    for _ in range(2):
        failed_after_start(cv, cid, trunk)
    opened = L.consider(cv, trunk, trigger="run-ended")
    (one,) = opened["opened"]
    status, said = op("record_material", kind="finding",
                      basis=[cv._act(one["evaluation"])["turn"]],
                      body={"text": "The evidence does not establish scope "
                                    "expansion or a repeated execution failure "
                                    "of the browser checks."})
    assert status == 200, said
    done = close(op, one["evaluation"], outcome="Nothing worth preserving",
                 references=[{"ref": said["entry"]}])
    assert done["learning"]["evaluated"] is False
    # THE SAME WORDS, in a later ending of the same request and of another.
    again = close(op, trunk, result="partial",
                  outcome="A repeated execution failure of the browser checks "
                          "was suspected; scope expansion was not established")
    assert again["learning"]["fired"] == [], again["learning"]["fired"]
    _, other = op("record_request", conversation=cid,
                  text="Run the browser checks again")
    more = close(op, other["expectation"], result="failed",
                 outcome="A repeated execution failure of the browser checks")
    assert [s for s in more["learning"]["fired"]
            if s["signal"] in ("repeated-failure", "scope-expansion")] == []
    assert len(opened_acts(cv)) == 1


def test_one_further_failure_is_not_new_evidence_and_two_after_an_answer_are(world):
    op, cv = world["op"], world["cv"]
    cid, trunk = a_request(op, "Run the browser checks")
    for _ in range(2):
        failed_after_start(cv, cid, trunk)
    (one,) = L.consider(cv, trunk, trigger="run-ended")["opened"]
    third = failed_after_start(cv, cid, trunk)
    waiting = L.consider(cv, trunk, trigger="run-ended")
    assert not waiting["evaluated"]
    assert [r["reason"] for r in waiting["ruled_out"]
            if r["signal"] == "repeated-failure"] == ["being-evaluated"]
    close(op, one["evaluation"], outcome="A quota limit; nothing to preserve")
    answered = L.consider(cv, trunk, trigger="run-ended")
    assert not answered["evaluated"]
    assert [r["reason"] for r in answered["ruled_out"]
            if r["signal"] == "repeated-failure"] == ["already-evaluated"]
    fourth = failed_after_start(cv, cid, trunk)
    fresh = L.consider(cv, trunk, trigger="run-ended")
    assert fresh["evaluated"]
    (signal,) = [s for s in fresh["fired"] if s["signal"] == "repeated-failure"]
    assert signal["evidence"] == [third, fourth]
    assert one["evaluation"] in signal["because"]


def test_a_child_gaining_acts_is_the_same_event_and_is_not_evaluated_again(world):
    """34 children were flagged twice on TEST and 2 three times, because the
    identity was the evidence and the evidence grew."""
    cv, cid = world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"],
                        "Polish the governance forms")
    claimed_met(cv, req, world["agent"])
    after = handed(cv, cid, world["agent"], world["who"], req, "More")
    assert L.consider(cv, req, trigger="run-ended")["evaluated"]
    # the child runs, and reports: three more acts on the same event
    began = cv.record_act(actor=world["who"], act="execution-started",
                          conversation=cid, turn=cv._act(after)["turn"],
                          execution="fixture-child", runtime="codex",
                          caused_by=after, because="dispatched")
    completion.claim(cv, after, {"result": "partly", "summary": "under way"},
                     actor=world["who"], via="test")
    again = L.consider(cv, req, trigger="run-ended")
    assert not again["evaluated"]
    assert [d["signal"] for d in again["deduped"]] == ["scope-expansion"]
    assert began  # the act exists; it changed the evidence, not the event
    assert len(opened_acts(cv)) == 1


def test_an_event_evaluated_before_signals_named_their_subject_is_not_reopened(world):
    """What TEST already evaluated under the old identity stays evaluated."""
    cv, cid = world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"],
                        "Polish the governance forms")
    claimed_met(cv, req, world["agent"])
    after = handed(cv, cid, world["agent"], world["who"], req, "More")
    turn = cv.say(cid, world["agent"], [text_part("an earlier evaluation")])
    cv.expect(turn, of=world["agent"], kind="result", by=world["agent"],
              caused_by=req,
              detail={L.MARK: True, "signal": "scope-expansion",
                      "signals": [{"signal": "scope-expansion",
                                   "reading": "deviation",
                                   "evidence": [after, "opr-000000000000"],
                                   "because": "more work was handed out after "
                                              "this request was claimed "
                                              "complete: 'More'."}]})
    got = L.consider(cv, req, trigger="run-ended")
    assert not got["evaluated"]
    assert [d["signal"] for d in got["deduped"]] == ["scope-expansion"]


# -- the brief ----------------------------------------------------------------

def test_the_brief_says_the_event_why_the_evidence_and_the_question(world):
    op, cv = world["op"], world["cv"]
    cid, trunk = a_request(op, "Add a Jump to latest control. " + "x " * 600)
    # things read and set aside, which used to be listed in every brief
    for n in range(6):
        status, _ = op("record_discovered_work", under=trunk,
                       work=f"An unrelated deferred finding number {n}",
                       because="real, and not this work")
        assert status == 200
    close(op, trunk)
    grew = hand_out(op, world["who"], "A redesign nobody asked for", cid, trunk)
    (one,) = L.consider(cv, trunk, trigger="run-ended")["opened"]
    said = words_of(cv, one["evaluation"])
    for part in ("What happened: scope-expansion (deviation; observed in the "
                 "record)", "Why it might matter:", "Evidence:",
                 "The question:", "What is asked", grew, trunk,
                 "`record_material`", "request_adoption", "`hypothesis`"):
        assert part in said, part
    assert "An unrelated deferred finding" not in said
    assert "6 other thing(s)" in said
    assert len(said) < 3000, len(said)
    # NOTHING IS LOST: what was set aside is on the opening act.
    (act,) = opened_acts(cv)
    assert len([r for r in act["detail"]["ruled_out"]
                if r["reason"] == "deferred"]) == 6


# -- learning that has nothing to do with scope still happens -----------------

def test_a_correction_that_then_worked_is_still_recognised(world):
    op, cv = world["op"], world["cv"]
    _, trunk = a_request(op, "Make the composer pills fit a narrow line")
    close(op, trunk, result="failed", outcome="a long model id is cut")
    close(op, trunk, result="failed", outcome="the warning is still cut")
    got = close(op, trunk, outcome="pills wrap and never cut a warning")
    (fired,) = got["learning"]["fired"]
    assert (fired["signal"], fired["reading"], fired["basis"]) == \
        ("repeated-correction", "adaptation", L.OBSERVED)
    assert got["learning"]["evaluated"] is True


# -- found by independent review of this change -------------------------------

def test_the_owner_who_assigned_the_work_is_not_taken_for_its_carrier(world):
    cv, cid = world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"], "Polish")
    assert L._authorisers(cv, req) == {world["owner"]}
    assert world["agent"] in L._doing(cv, req)


def test_withdrawing_a_question_is_not_an_instruction(world):
    """The carrier asks whether it may do more; the owner closes the question
    without answering. Work handed out anyway is still the event."""
    cv, cid = world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"], "Polish")
    claimed_met(cv, req, world["agent"])
    turn = cv.say(cid, world["agent"], [text_part("May I also redesign it?")],
                  addressed_to=[world["owner"]])
    decision = cv.expect(turn, of=world["owner"], kind="decision",
                         by=world["agent"], caused_by=req)
    cv.record_act(actor=world["owner"], act="expectation-met",
                  conversation=cid, turn=turn, caused_by=decision,
                  because="not now", detail={"withdrawn": True})
    after = handed(cv, cid, world["agent"], world["who"], req, "The redesign")
    fired, _ = scope_fired(cv, req)
    assert [s["subject"] for s in fired] == [["after-met", after]]


def test_a_followup_the_carrier_recorded_itself_does_not_clear_its_own_work(world):
    """`follow-up-attached` counts only where the request handed over is one
    the person this work answers to recorded."""
    cv, cid = world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"], "Polish")
    claimed_met(cv, req, world["agent"])
    turn = cv.say(cid, world["agent"], [text_part("Also redesign it")])
    own = cv.expect(turn, of=world["agent"], kind="result", by=world["agent"])
    cv.record_act(actor=world["agent"], act="follow-up-attached",
                  conversation=cid, turn=turn, caused_by=req, about=[own, turn],
                  detail={"request": own, "turn": turn, "work": req,
                          "carrier": world["agent"]})
    after = handed(cv, cid, world["agent"], world["who"], req, "The redesign")
    fired, _ = scope_fired(cv, req)
    assert [s["subject"] for s in fired] == [["after-met", after]]
    # the owner's own follow-up, handed over the same way, does
    oturn = cv.say(cid, world["owner"], [text_part("Also do the record pages")])
    theirs = cv.expect(oturn, of=world["agent"], kind="result", by=world["owner"])
    cv.record_act(actor=world["agent"], act="follow-up-attached",
                  conversation=cid, turn=oturn, caused_by=req,
                  about=[theirs, oturn],
                  detail={"request": theirs, "turn": oturn, "work": req,
                          "carrier": world["agent"]})
    later = handed(cv, cid, world["agent"], world["who"], req, "Record pages")
    fired, got = scope_fired(cv, req)
    assert [s["subject"] for s in fired] == [["after-met", after]]
    assert [r["reason"] for r in got["ruled_out"] if r["ref"] == later] == \
        ["owner-authorized"]


def test_work_parked_under_a_child_after_the_claim_is_still_this_requests(world):
    """Whoever carries the request, handing work out under one of its children
    after claiming the request met. The child's own carrier doing so is the
    child's work, and so is anything under discovered work."""
    op, cv, cid = world["op"], world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"], "Polish")
    child = handed(cv, cid, world["agent"], world["who"], req, "The polish")
    claimed_met(cv, req, world["agent"])
    theirs = handed(cv, cid, world["who"], world["who"], child,
                    "A check the builder needs")
    assert scope_fired(cv, req)[0] == []
    parked = handed(cv, cid, world["agent"], world["who"], child,
                    "A redesign nobody asked for")
    fired, _ = scope_fired(cv, req)
    assert [s["subject"] for s in fired] == [["after-met", parked]]
    assert all(theirs not in s["evidence"] for s in fired)


def test_a_run_a_restart_interrupted_is_not_a_failed_run(world):
    op, cv = world["op"], world["cv"]
    cid, trunk = a_request(op, "Run the browser checks")
    for _ in range(3):
        failed_after_start(cv, cid, trunk, detail={"terminal": "interrupted"})
    failed_after_start(cv, cid, trunk, detail={
        "runtime_evidence": {"stop_reason": "cancelled"}})
    assert L.signals(cv, trunk)["fired"] == []


def test_a_long_recurrence_does_not_swallow_the_next_one(world):
    """Every failure an evaluation counted is remembered, not only the four it
    listed: otherwise the rest look new for ever and a later recurrence is
    read as the one already evaluated."""
    op, cv = world["op"], world["cv"]
    cid, trunk = a_request(op, "Run the browser checks")

    def fail(n):
        return [failed_after_start(cv, cid, trunk) for _ in range(n)]

    fail(2)
    (one,) = L.consider(cv, trunk, trigger="run-ended")["opened"]
    fail(6)
    close(op, one["evaluation"], outcome="nothing to preserve")
    (two,) = L.consider(cv, trunk, trigger="run-ended")["opened"]
    close(op, two["evaluation"], outcome="nothing to preserve")
    assert not L.consider(cv, trunk, trigger="run-ended")["evaluated"]
    newest = fail(2)
    third = L.consider(cv, trunk, trigger="run-ended")
    assert third["evaluated"], third
    (signal,) = [s for s in third["fired"] if s["signal"] == "repeated-failure"]
    assert signal["evidence"] == newest


# -- found by the second independent review (Codex) ----------------------------

def test_the_owner_reassigning_a_request_claimed_met_is_them_acting_on_it(world):
    """Owner assigns to A; A claims it met; the owner assigns it to B; B hands
    out the continuation. The reassignment is the owner's act on the request.
    Without it, the same hand-out is still the event."""
    cv, cid = world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"], "Polish")
    claimed_met(cv, req, world["agent"])
    cv.assign(req, world["who"], by=world["owner"], because="carry on with it")
    later = handed(cv, cid, world["who"], world["agent"], req, "The continuation")
    fired, got = scope_fired(cv, req)
    assert fired == []
    assert [r["reason"] for r in got["ruled_out"] if r["ref"] == later] == \
        ["owner-authorized"]


def test_a_carrier_reassigning_its_own_request_does_not_clear_what_follows(world):
    cv, cid = world["cv"], world["cid"]
    req = owner_request(cv, cid, world["owner"], world["agent"], "Polish")
    claimed_met(cv, req, world["agent"])
    cv.assign(req, world["who"], by=world["agent"], because="passing it on")
    after = handed(cv, cid, world["who"], world["agent"], req, "The redesign")
    fired, _ = scope_fired(cv, req)
    assert [s["subject"] for s in fired] == [["after-met", after]]
