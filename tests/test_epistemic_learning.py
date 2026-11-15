"""The epistemic ladder reading work history back, through the real chokepoints.

Every case here drives the ACTUAL trigger path: a Brain built by the ordinary
fixture, a hand-started session through the real `/api/worker` door, and either
`worker` `record_outcome` (Hook B, after its transaction commits) or
`web.dispatch`'s own `finally` (Hook A). Nothing calls the signal functions
directly except where a case is about one bound.

THE PRIMARY ACCEPTANCE CASE AND WHERE ITS EVIDENCE COMES FROM. The owner named
the conversation-management release as the incident. Its Mentis-side narrative
does not exist: the scope-control rule the incident produced (ent-8d7c436f78f2
in the day-to-day Brain) was written straight through the generic entry door
with `proposed_by` and `placed_at` both empty, so there is no Conversation, Turn
or work record for it to be traced from. What IS real and checkable is this
repository's own history, and the texts below are taken from it verbatim:

  7866e2f (2026-11-12) "Conversation management backend: Archive, Unarchive,
      Trash, Restore as acts" -- the authorized objective, whose own message
      draws the boundary: "Nothing is rewritten or deleted; Restore is exact."
      and "No permanent-deletion code or route."
  c7b44de (2026-11-12) "Rust front: conversation list state parity (Active,
      Archived, Trash)" -- work inside that objective.
  3290dd4, 34d255b, f90208d (2026-11-13) "Attested erasure (schema 0002) and
      permanent deletion of a Conversation in Trash", "Deferred physical
      cleanup, the deletion ledger ...", "The Trash/deleted write guard is
      installed on every corpus opened writable" -- permanent deletion, a new
      Brain schema and a ledger, one day after the release said it had no
      permanent-deletion code or route.

So the work records here are RECONSTRUCTED FROM THAT GIT HISTORY, with the
commits' own words, and nothing in this Brain is claimed as their source. What
the case tests is the mechanism, on the incident's real shape and real words:
that the difference between the authorized objective and what was executed is
findable from the record alone, with no lesson named in advance.
"""
from __future__ import annotations

import json
import shutil

import pytest

from mentis.operational import learning as L
from mentis.web import dispatch as D
from mentis.web import fixture
from tests.test_delegate_opkey_crash import Server

# -- the incident's own words (git, C:\Work\Mentis) ---------------------------

OBJECTIVE = (
    "Conversation management backend: Archive, Unarchive, Trash, Restore as "
    "acts. Each change is one operational act on the Conversation, written "
    "through the same Fluid door and author check as rename. Nothing is "
    "rewritten or deleted; Restore is exact. No permanent-deletion code or "
    "route.")

IN_SCOPE = ("Rust front: conversation list state parity, so the list rows "
            "carry Active, Archived and Trash as the backend acts record them")

EXPANSION = (
    "Attested erasure at Brain schema 0002: permanently delete a Conversation "
    "in Trash, with a deletion ledger written before the commit, deferred "
    "physical cleanup, write guards installed on every corpus opened "
    "writable, and a reverse migration for rollback")


# -- harness ------------------------------------------------------------------

@pytest.fixture(scope="module")
def built(tmp_path_factory):
    where = tmp_path_factory.mktemp("learning-base")
    root = where / "corpus"
    fixture.build(str(root))
    return str(root)


@pytest.fixture()
def server(built, tmp_path, monkeypatch):
    """A Mentis process over a fresh copy of the Brain, dispatches captured."""
    root = tmp_path / "corpus"
    shutil.copytree(built, root)
    s = Server(root, tmp_path, monkeypatch)
    try:
        yield s
    finally:
        s.close()


def a_request(op, text, **kw):
    _, opened = op("open_conversation", name="Release")
    status, got = op("record_request", conversation=opened["conversation"],
                     text=text, **kw)
    assert status == 200, got
    return opened["conversation"], got["expectation"]


def helper(op, cid, under, alias="@Builder-Conv"):
    status, got = op("summon_participant", alias=alias, conversation=cid,
                     under=under)
    assert status == 200, got
    return got["participant"]


def hand_out(op, who, work, cid, under, **kw):
    """Work handed out under the request, through the real `delegate`."""
    status, got = op("delegate", participant=who, work=work,
                     conversation=cid, under=under, **kw)
    assert status == 200, got
    return got["expectation"]


def close(op, expectation, result="done", outcome="the work as asked", **kw):
    status, got = op("record_outcome", expectation=expectation, result=result,
                     outcome=outcome, **kw)
    assert status == 200, got
    return got


def words_of(cv, expectation) -> str:
    """What an evaluation request actually says, read from its Turn."""
    act = cv._act(expectation)
    body = cv.corpus.read([act["turn"]])[0]["body"]
    return " ".join(p.get("text", "") for p in (body.get("parts") or ())
                    if p.get("type") == "text")


def opened_acts(cv):
    return [a for a in cv.corpus.operational(act=L.OPENED)]


def shipped_then_grown(op, cid=None):
    """The incident's recorded shape: the release handed out, claimed with its
    own boundary, and then grown under the same request."""
    if cid is None:
        cid, trunk = a_request(op, OBJECTIVE)
    else:
        _, got = op("record_request", conversation=cid, text=OBJECTIVE)
        trunk = got["expectation"]
    who = helper(op, cid, trunk, alias=f"@Builder-{trunk[-6:]}")
    inside = hand_out(op, who, IN_SCOPE, cid, trunk)
    claim = close(op, trunk,
                  outcome="Archive, Unarchive, Trash and Restore shipped as "
                          "acts. Nothing is rewritten or deleted. No "
                          "permanent-deletion code or route.")
    grew = hand_out(op, who, EXPANSION, cid, trunk)
    return {"conversation": cid, "trunk": trunk, "who": who,
            "inside": inside, "claim": claim, "grew": grew}


# -- the primary acceptance case ----------------------------------------------

def test_the_conversation_management_scope_expansion_is_recognised(server):
    """The incident's real shape, reconstructed from git: the release is handed
    out, delivered and CLAIMED with its own boundary ("No permanent-deletion
    code or route", 7866e2f), and then permanent deletion, a new Brain schema
    and a deletion ledger are handed out under the same request and taken on
    (3290dd4, 34d255b, the next day). The record notices the difference between
    what the work committed to and what it then did, without being told what
    the lesson is."""
    grant, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(op, OBJECTIVE)
    who = helper(op, cid, trunk)
    inside = hand_out(op, who, IN_SCOPE, cid, trunk)
    # THE COMMITMENT, in the release's own words.
    shipped = close(op, trunk,
                    outcome="Archive, Unarchive, Trash and Restore shipped as "
                            "acts. Nothing is rewritten or deleted. No "
                            "permanent-deletion code or route.")
    assert shipped["result"] == "done"
    assert shipped["learning"]["evaluated"] is False, shipped["learning"]
    # AND THEN THE WORK GREW, under the same request.
    grew = hand_out(op, who, EXPANSION, cid, trunk)

    got = close(op, trunk,
                outcome="Permanent deletion from Trash, attested erasure at "
                        "schema 0002 and the deletion ledger are in")
    learned = got["learning"]
    assert learned["evaluated"] is True, learned
    # THE SIGNAL, AND THE WORK IT POINTS AT: the expansion, not the in-scope part
    (fired,) = [s for s in learned["fired"]
                if s["signal"] == "scope-expansion"]
    assert grew in fired["evidence"], fired
    assert inside not in fired["evidence"], fired
    assert "claimed 'met'" in fired["because"], fired

    # ONE EVALUATION, RECORDED AS WORK, AND ACTUALLY ASKED OF SOMEBODY
    (one,) = learned["opened"]
    assert one["signal"] == "scope-expansion"
    assert one["carrier"] == grant["participant"]
    # THE DOOR TOOK IT, for real: `dispatches` is popped by `/api/worker` and
    # handed to `dispatch_soon`, which this harness captures.
    (spec,) = [k for k in server.sent
               if k.get("expectation") == one["evaluation"]]
    assert spec["participant"] == one["carrier"]
    assert "dispatches" not in got
    (act,) = opened_acts(cv)
    assert act["detail"]["evaluation"] == one["evaluation"]

    # WHAT THE EVALUATION IS TOLD: the real objective, the real evidence, what
    # was ruled out -- and NOT the answer. No Kind is named for it, no lesson
    # is stated, and nothing says a lesson exists.
    said = words_of(cv, one["evaluation"])
    assert "No permanent-deletion code or route" in said
    assert grew in said
    assert "scope-expansion" in said
    for leading in ("the lesson is", "scope expansion requires owner",
                    "you should conclude", "record a lesson saying"):
        assert leading.lower() not in said.lower(), leading
    assert "`record_material`" in said and "request_adoption" in said

    # AND IT HAS AN OBSERVABLE OUTCOME. The same session that was handed it
    # does it, through the ordinary doors: an evidence-supported candidate of
    # an existing Kind with real provenance, a rule left for the owner, and the
    # evaluation closed.
    grew_turn = cv._act(grew)["turn"]
    status, found = op("record_material", kind="finding",
                       basis=[grew_turn, shipped["turn"]],
                       body={"text": "Work handed out under the conversation-"
                                     "management request (" + grew + ") added "
                                     "permanent deletion and a new Brain "
                                     "schema after the request had been "
                                     "claimed complete with 'no "
                                     "permanent-deletion code or route'."})
    assert status == 200 and found.get("entry"), found
    status, rule = op("record_material", kind="rule",
                      basis=[grew_turn, shipped["turn"]],
                      body={"text": "Work that materially changes the scope of "
                                    "an authorized request is put to the owner "
                                    "before it is started.",
                            "about": "scope of work requests and delegation"})
    assert status == 200 and rule.get("entry"), rule
    status, asked = op("request_adoption", entry=rule["entry"],
                       because="a preventive measure only the owner can "
                               "establish")
    assert status == 200, asked
    # LEFT AWAITING APPROVAL: recorded, proposed, and governing nothing.
    from mentis.conversation import ladder
    assert ladder.adoption_status(cv.corpus, rule["entry"]) == \
        ladder.ADOPTION_REQUESTED
    assert cv.corpus.stands(rule["entry"])["stands"] is False

    done = close(op, one["evaluation"], outcome="Scope difference confirmed; "
                                                "finding recorded, rule left "
                                                "for the owner",
                 references=[{"ref": found["entry"]}, {"ref": rule["entry"]}])
    # THE LOOP GUARD: closing an evaluation never opens another one.
    assert done["learning"]["evaluated"] is False
    assert "IS a learning evaluation" in done["learning"]["why"]
    assert len(opened_acts(cv)) == 1

    # AND IT NEVER REOPENS for the same request and signal.
    status, again = op("record_outcome", expectation=trunk, result="done",
                       outcome="said again")
    assert status == 200, again
    assert again["learning"]["evaluated"] is False
    assert [d["signal"] for d in again["learning"]["deduped"]] == \
        ["scope-expansion"]
    assert len(opened_acts(cv)) == 1


# -- the contrasting cases ----------------------------------------------------

def test_a_routine_clarification_produces_no_lesson(server):
    """A question asked under the work, answered, and the work done: the
    clarification is seen, named as not being execution, and nothing fires."""
    grant, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(
        op, "Add a Jump to latest control beside the composer in Quiet Chat")
    # A QUESTION ASKED UNDER THE WORK, as the record holds one: a request for
    # a clarification, which changes nothing about the objective.
    from mentis.conversation import text as text_part
    asked_turn = cv.say(cid, grant["participant"], [text_part(
        "Should Jump to latest sit left or right of the composer?")])
    asked = cv.expect(asked_turn, of=None, kind="clarification",
                      by=grant["participant"], caused_by=trunk,
                      because="which side the control sits on")
    got = close(op, trunk, outcome="Jump to latest added beside the composer")
    learned = got["learning"]
    assert learned["evaluated"] is False
    assert "no signal" in learned["why"], learned
    assert learned["fired"] == []
    rows = [r for r in learned["ruled_out"] if r["ref"] == asked]
    assert [r["reason"] for r in rows] == ["clarification"], learned["ruled_out"]
    assert opened_acts(cv) == []


def test_an_unrelated_issue_deferred_is_not_scope_creep(server):
    """Discovered work recorded and left for another bounded task: the
    mechanism names it scope MANAGEMENT and fires nothing, even though its
    words share nothing with the objective."""
    grant, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(
        op, "Add a Jump to latest control beside the composer in Quiet Chat")
    status, found = op("record_discovered_work", under=trunk,
                       work="The release helper's retention prunes below two "
                            "verified backups when a restore check is skipped",
                       because="real, and nothing to do with the composer")
    assert status == 200, found
    got = close(op, trunk, outcome="Jump to latest added beside the composer")
    learned = got["learning"]
    assert learned["evaluated"] is False, learned
    rows = [r for r in learned["ruled_out"]
            if r["ref"] == found["expectation"]]
    assert [r["reason"] for r in rows] == ["deferred"], rows
    assert opened_acts(cv) == []


def test_an_owner_authorised_change_of_scope_is_not_a_deviation(server):
    """The owner's own follow-up widens what is authorized. Work on what they
    asked for shares no word with the ORIGINAL objective and is still not a
    difference: the follow-up is read as authorization and its words count."""
    grant, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(
        op, "Add a Jump to latest control beside the composer in Quiet Chat")
    who = helper(op, cid, trunk, alias="@Builder-Quiet")
    # THE LATER WORD, HANDED TO THE WORK IT IS ABOUT (`attach_follow_up`), the
    # path the requester's own follow-up takes while the work is open. Work
    # done under it is authorized, so growing past the claim below -- into
    # exactly the subject the original request did not have -- is not a
    # difference.
    from mentis.conversation import text as text_part
    fturn = cv.say(cid, grant["participant"], [text_part(
        "Also install the deletion ledger and the attested-erasure schema "
        "while you are in there")])
    follow = cv.expect(fturn, of=None, kind="result", by=grant["participant"],
                       because="an addition to this work")
    attached = cv.attach_follow_up(follow, trunk, by=grant["participant"],
                                   because="a follow-up about work under way")
    assert attached.get("attached"), attached
    close(op, trunk, outcome="Jump to latest added beside the composer")
    grew = hand_out(op, who, "Install the deletion ledger and the attested-"
                             "erasure schema 0002", cid, trunk)
    got = close(op, trunk, outcome="composer control and the ledger, as asked")
    learned = got["learning"]
    assert [s for s in learned["fired"]
            if s["signal"] == "scope-expansion"] == [], learned["fired"]
    reasons = {r["reason"] for r in learned["ruled_out"]
               if r["ref"] in (grew, attached["attached"])}
    rows = [r for r in learned["ruled_out"] if r["ref"] == grew]
    assert "owner-authorized" in reasons, learned["ruled_out"]
    # THE SAME FACT LIMB 1 FIRES ON -- work handed out after the request was
    # claimed complete -- SEEN, and cleared by the owner's own word.
    assert rows and "claimed complete" in rows[0]["because"], rows
    assert [a["detail"]["signal"] for a in opened_acts(cv)
            if a["detail"]["signal"] == "scope-expansion"] == []


def test_material_relied_on_while_challenged_is_noticed(server):
    """contested-basis: a request governed by material somebody has disputed,
    with the challenge still open when the work ends."""
    grant, op = server.session()
    cv = server.st.cv
    cid, _ = a_request(op, "Integrate the Quiet round 8 packages")
    status, rule = op("record_material", kind="rule",
                      body={"text": "Integration runs the full suite before "
                                    "every merge into a shared branch.",
                            "about": "integration of parallel packages"})
    assert status == 200, rule
    # The request says what governs it; somebody challenges that material.
    from mentis.conversation import text as text_part
    turn = cv.say(cid, grant["participant"],
                  [text_part("Integrate the round 8 packages")])
    trunk = cv.expect(turn, of=grant["participant"], kind="result",
                      by=grant["participant"],
                      because="integrate the round 8 packages",
                      detail={"manual_session": True,
                              "governed": [rule["entry"]]})
    status, said = op("challenge", target=rule["entry"],
                      because="the full suite is not this repository's "
                              "process; tests here are targeted")
    assert status == 200, said
    got = close(op, trunk, outcome="packages integrated, targeted tests run")
    learned = got["learning"]
    (fired,) = [s for s in learned["fired"]
                if s["signal"] == "contested-basis"]
    assert rule["entry"] in fired["evidence"], fired
    assert "open challenge" in fired["because"], fired
    (one,) = learned["opened"]
    assert one["signal"] == "contested-basis"


def test_a_recurring_failure_with_new_evidence_is_recognised_each_time(server):
    """The same failure on a second request fires again -- the dedup is per
    (request, signal), never per category -- and the same request does not."""
    grant, op = server.session()
    cv = server.st.cv
    # What the record already holds about this failure.
    cid, earlier = a_request(
        op, "Run the margin browser checks for the Quiet round 5 candidate")
    first = close(op, earlier, result="failed",
                  outcome="A test left running in the background when the run "
                          "ended died with the run and gave no result")
    status, lesson = op(
        "record_material", kind="lesson", basis=[first["turn"]],
        body={"text": "A test left running in the background when a dispatched "
                      "run ends its turn dies with the run and gives no "
                      "result; the brief has to say to wait for it.",
              "limits": "Seen on one runtime."})
    assert status == 200, lesson

    # A later, separate request that ends the same way.
    _, again = op("record_request", conversation=cid,
                  text="Run the margin browser checks for the round 6 candidate")
    got = close(op, again["expectation"], result="failed",
                outcome="A test left running in the background when the run "
                        "ended died with the run and gave no result")
    learned = got["learning"]
    assert learned["evaluated"] is True, learned
    (fired,) = [s for s in learned["fired"] if s["signal"] == "repeated-failure"]
    assert lesson["entry"] in fired["evidence"], fired
    assert len(opened_acts(cv)) == 1

    # A third request, same failure: noticed AGAIN, not deduplicated away.
    _, third = op("record_request", conversation=cid,
                  text="Run the margin browser checks for the round 7 candidate")
    more = close(op, third["expectation"], result="failed",
                 outcome="A test left running in the background when the run "
                         "ended died with the run and gave no result")
    assert more["learning"]["evaluated"] is True, more["learning"]
    assert len(opened_acts(cv)) == 2
    # The SAME request again: deduplicated.
    status, repeat = op("record_outcome", expectation=third["expectation"],
                        result="failed",
                        outcome="A test left running in the background when "
                                "the run ended died with the run and gave no "
                                "result")
    assert status == 200, repeat
    assert "repeated-failure" in [d["signal"]
                                  for d in repeat["learning"]["deduped"]], \
        repeat["learning"]
    assert len([a for a in opened_acts(cv)
                if a["detail"]["signal"] == "repeated-failure"]) == 2


def test_a_consequential_successful_adaptation_is_recognised_positively(server):
    """Two corrections and then met: the same evidence, read as ADAPTATION, and
    the brief asks what worked rather than what went wrong."""
    grant, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(
        op, "Make the Quiet composer pills fit a narrow phone line")
    close(op, trunk, result="partial",
          outcome="pills wrap but a long model id is cut")
    close(op, trunk, result="partial",
          outcome="the model id keeps its note; the warning is still cut")
    got = close(op, trunk, result="done",
                outcome="pills wrap in their corner and never cut a warning")
    learned = got["learning"]
    assert learned["evaluated"] is True, learned
    (fired,) = [s for s in learned["fired"]
                if s["signal"] == "repeated-correction"]
    assert fired["reading"] == "adaptation", fired
    assert "what worked" in fired["because"], fired
    (one,) = learned["opened"]
    assert one["reading"] == "adaptation"
    said = words_of(cv, one["evaluation"])
    assert "repeated-correction (adaptation)" in said


def test_an_ordinary_completed_task_leaves_nothing_behind(server):
    """Done the first time, nothing recorded about it, no challenge: nothing
    fires and nothing at all is written for the evaluation."""
    grant, op = server.session()
    cv = server.st.cv
    before = len(cv.corpus.operational())
    cid, trunk = a_request(
        op, "Rename a conversation from its header in Quiet Chat")
    got = close(op, trunk, outcome="renaming works from the header")
    learned = got["learning"]
    assert learned["evaluated"] is False and learned["fired"] == []
    assert "no signal" in learned["why"]
    assert opened_acts(cv) == []
    assert "dispatches" not in got
    # Only the outcome's own acts were written; nothing of this mechanism's.
    after = cv.corpus.operational()
    assert not [a for a in after[max(0, before - 1):]
                if a["act"] == L.OPENED]


# -- the single-correction boundary, and the bounds ---------------------------

def test_one_correction_is_ordinary_work(server):
    """`CORRECTIONS` is where repeated begins: one correction is named and
    ruled out rather than fired on."""
    grant, op = server.session()
    cid, trunk = a_request(op, "Collapse the composer without losing the draft")
    close(op, trunk, result="partial", outcome="the draft is lost on collapse")
    got = close(op, trunk, result="done", outcome="the draft survives")
    learned = got["learning"]
    assert learned["evaluated"] is False, learned
    rows = [r for r in learned["ruled_out"]
            if r["reason"] == "single-correction"]
    assert rows, learned["ruled_out"]


def test_at_most_one_evaluation_is_opened_per_ending(server):
    """Two signals true at one ending open one evaluation; the other keeps its
    key and is named, so a later ending may still open it."""
    grant, op = server.session()
    cv = server.st.cv
    trunk = shipped_then_grown(op)["trunk"]
    # TWO SIGNALS FRESH AT ONE ENDING: the claims are written straight through
    # `completion.claim`, so no ending in between has spent either key.
    from mentis.operational import completion
    for n in (1, 2):
        completion.claim(cv, trunk,
                         {"result": "not-met", "summary": f"round {n} short"},
                         actor=grant["participant"], via="test")
    learned = L.consider(cv, trunk, trigger="run-ended")
    assert {s["signal"] for s in learned["fired"]} == \
        {"scope-expansion", "repeated-correction"}, learned["fired"]
    assert len(learned["opened"]) == L.MOST_PER_CALL == 1
    (held,) = learned["deduped"]
    assert f"at most {L.MOST_PER_CALL}" in held["why"], held
    assert len(opened_acts(cv)) == 1
    # AND THE ONE HELD BACK KEPT ITS KEY: a later ending opens it.
    later = L.consider(cv, trunk, trigger="outcome-recorded")
    assert [o["signal"] for o in later["opened"]] == [held["signal"]]
    assert len(opened_acts(cv)) == 2


# -- Hook A: the run that ended ------------------------------------------------

def test_a_run_ending_opens_and_actually_dispatches_the_evaluation(server,
                                                                   monkeypatch):
    """Hook A, in `web.dispatch`'s own `finally`: the evaluation is opened for
    a request with no live session, and handed to `dispatch_soon` for real."""
    grant, op = server.session()
    cv = server.st.cv
    made = shipped_then_grown(op)
    trunk, grew = made["trunk"], made["grew"]
    started: list[dict] = []
    got = L.after_run(server.st, trunk, restarted=False,
                      start=lambda st, **kw: started.append(kw))
    assert got["considered"] is True and got["evaluated"] is True, got
    (one,) = got["opened"]
    assert grew in one["evidence"]
    # ASKED OF SOMEBODY, FOR REAL: the dispatch the door would make.
    (kw,) = started
    assert kw["expectation"] == one["evaluation"]
    assert kw["participant"] == one["carrier"]
    assert OBJECTIVE.split(".")[0] in kw["work"]
    assert cv._act(one["evaluation"])["detail"][L.MARK] is True


def test_a_restarted_run_is_passed_over(server):
    """A run restarted because its permission rules went stale has not ended:
    nothing is read, nothing is written, and the signal keeps its key for the
    ending that is one."""
    grant, op = server.session()
    cv = server.st.cv
    trunk = shipped_then_grown(op)["trunk"]
    held = L.after_run(server.st, trunk, restarted=True,
                       start=lambda st, **kw: pytest.fail("dispatched"))
    assert held["considered"] is False
    assert "has not ended" in held["why"]
    assert opened_acts(cv) == []
    # and the real ending still opens it, so nothing was lost
    done = L.after_run(server.st, trunk, restarted=False,
                       start=lambda st, **kw: None)
    assert done["evaluated"] is True
    assert len(opened_acts(cv)) == 1


def test_a_run_with_no_request_is_passed_over(server):
    """Nothing to read work history for, said rather than crashed."""
    got = L.after_run(server.st, None, restarted=False,
                      start=lambda st, **kw: pytest.fail("dispatched"))
    assert got["considered"] is True and got["evaluated"] is False
    assert "no request" in got["why"]


def test_the_chokepoint_is_in_dispatch_and_survives_its_own_failure(server,
                                                                    monkeypatch):
    """The hook is called from the real `dispatch` for every ending, and a
    failure inside it never reaches the caller or the run's own ending."""
    seen: list[tuple] = []

    def boom(st, expectation, **kw):
        seen.append((expectation, kw.get("restarted")))
        raise RuntimeError("the evaluation could not be made")

    monkeypatch.setattr(L, "after_run", boom)
    # `_dispatch` refusing before anything starts is still an ending.
    monkeypatch.setattr(D, "_dispatch",
                        lambda st, **kw: {"ok": False, "why": "no runtime"})
    out = D.dispatch(server.st, conversation=None, turn=None,
                     participant=None, work="x", expectation=None)
    assert out == {"ok": False, "why": "no runtime"}
    assert seen == [(None, False)]


# -- what a signal could not read ---------------------------------------------

def test_a_question_that_cannot_be_read_does_not_take_the_others_with_it(server,
                                                                         monkeypatch):
    """One unreadable question is said in `unread`; the rest still answer, and
    the work's own ending is unaffected."""
    grant, op = server.session()
    trunk = shipped_then_grown(op)["trunk"]

    def broken(cv, expectation):
        raise RuntimeError("cannot read challenges")

    monkeypatch.setattr(L, "_contested", broken)
    got = L.signals(server.st.cv, trunk)
    assert [u["signal"] for u in got["unread"]] == ["contested-basis"]
    assert [s["signal"] for s in got["fired"]] == ["scope-expansion"]


# -- requirement 6: what the Brain knows reaches the next run ------------------

def test_adopted_knowledge_and_prior_experience_reach_a_brief(server):
    """`brief(work=...)` now carries both tiers whenever the work is known,
    under the existing bounds, each labelled for what it is -- and recorded
    material arrives as experience to weigh, never as governing material."""
    grant, op = server.session()
    cv = server.st.cv
    cid, trunk = a_request(
        op, "Run the margin browser checks for the Quiet round 8 candidate")
    done = close(op, trunk, result="failed",
                 outcome="a background test died with the run")
    status, lesson = op(
        "record_material", kind="lesson", basis=[done["turn"]],
        body={"text": "A background test left running when a dispatched run "
                      "ends its turn dies with the run and gives no result.",
              "limits": "One runtime, one timed instance."})
    assert status == 200, lesson

    status, got = op("brief", conversation=cid, detail=True,
                     work="a background test left running when a dispatched "
                          "run ends its turn")
    assert status == 200, got
    known = got["knowledge"]
    assert known["bounds"] == {"adopted": 5, "experience": 5}
    ids = [r["id"] for r in known["experience"]]
    assert lesson["entry"] in ids, known
    row = next(r for r in known["experience"] if r["id"] == lesson["entry"])
    # LABELLED AS WHAT IT IS: recorded, not adopted, with its own provenance.
    assert "not adopted" in known["means"]
    assert row["trailer"], row
    assert json.dumps(row["trailer"]).count("basis") >= 1
    # AND IT GOVERNS NOTHING: it is in neither the governing block nor the
    # standing governance the brief lists.
    assert lesson["entry"] not in [g["id"] for g in got.get("governing") or ()]
    assert lesson["entry"] not in [g["id"] for g
                                   in got["standing_governance"]]
    assert lesson["entry"] not in [r["id"] for r in known["adopted"]]


def test_a_brief_without_work_asks_the_knowledge_channel_nothing(server):
    """`work` absent means nobody asked: no tier, no question, as before."""
    grant, op = server.session()
    cid, _ = a_request(op, "Rename a conversation from its header")
    status, got = op("brief", conversation=cid, detail=True)
    assert status == 200, got
    assert "knowledge" not in got
