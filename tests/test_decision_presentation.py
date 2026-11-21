"""Creation, completion and read contract on disposable fixture Brains."""
import json

import pytest

from mentis.decision_presentation import InvalidDecision, fields, validate_batch
from mentis.operational import completion
from mentis.web import _surface
from mentis.worker import NotPermitted, _operate, _decision_form
from tests._loop import _coordinator, a_conversation, world  # noqa: F401
from tests.decision_descriptors import question
from tests.test_decision_resume_parent import _answer


def operate(world, grant, name, **args):
    return _operate(_surface(world["state"]), name, args, grant)


@pytest.mark.parametrize("field,value,path", [
    ("question", "", ".question"), ("question", "x" * 1001, ".question"),
    ("because", None, ".because"), ("because", "x" * 2001, ".because"),
    ("presentation", None, ".presentation"),
    ("options", [], ".options"),
    ("options", [{"label": "Yes"}, {"label": "No"}], ".consequence"),
    ("options", [{"label": "Wait", "consequence": "defer"}, {"label": " wait ", "consequence": "hold"}], ".label"),
])
def test_invalid_question_fields(field, value, path):
    q = question(**{field: value})
    with pytest.raises(InvalidDecision, match="questions") as exc:
        validate_batch({"questions": [q]})
    assert any(path in p["path"] for p in exc.value.problems)


@pytest.mark.parametrize("update,path", [
    ({"version": True}, "version"), ({"version": 2}, "version"),
    ({"stages": []}, "stages"), ({"stages": ["launch"]}, "stages"),
    ({"scope": ""}, "scope"), ({"primary_reason": ""}, "primary_reason"),
    ({"permission": True}, "permission"),
    ({"primary": {"kind": "record", "id": "wrong", "label": "source"}}, "id"),
    ({"primary": {"kind": "commit", "sha": "abc123", "label": "commit"}}, "sha"),
    ({"primary": {"kind": "url", "url": "javascript:alert(1)", "label": "source"}}, "url"),
    ({"supporting": [None] * 25}, "supporting"),
    ({"applies_when": "x" * 1001}, "applies_when"),
])
def test_invalid_presentation(update, path):
    q = question()
    q["presentation"].update(update)
    with pytest.raises(InvalidDecision) as exc:
        validate_batch(q)
    assert any(path in p["path"] for p in exc.value.problems)


def test_free_response_and_choice_need_no_artifact_and_do_not_gain_options():
    q = question("Which maintenance window can you attend?")
    q.pop("options")
    q["presentation"].update(type="free_response", stages=[], scope="Propose a schedule; no deployment permission.")
    got = validate_batch(q)[0]
    assert "options" not in got and got["presentation"]["primary"] is None
    q["options"] = None
    with pytest.raises(InvalidDecision, match="omit_for_free_response"):
        validate_batch(q)
    q = question()
    q["presentation"].update(type="choice", stages=[])
    assert validate_batch(q)[0]["options"] == q["options"]


def test_exact_artifact_and_no_generic_approval():
    q = question()
    q["presentation"].update(type="artifact_approval", primary={"kind": "commit", "sha": "a" * 40,
                                                              "repository": "bhill78/Mentis", "label": "Chart candidate"})
    assert validate_batch(q)[0] == q
    with pytest.raises(InvalidDecision, match="specific_approval"):
        validate_batch({**q, "question": "Approve this work?"})
    q["presentation"]["primary"] = {"kind": "url", "url": "http://localhost:8765", "label": "Mutable preview"}
    with pytest.raises(InvalidDecision, match="exact_artifact"):
        validate_batch(q)


def test_read_legacy_incomplete_unsupported_and_malformed_are_preserved():
    assert fields({"question": "Which window?"}, "Planning") ["presentation_status"]["state"] == "legacy"
    assert fields({"question": "Approve this work?", "options": [{"label": "Yes"}]}, "Read it")["presentation_status"]["state"] == "incomplete"
    for meta, state in (({"version": 7, "future": [1]}, "unsupported"), ([], "incomplete")):
        q = {"question": "Question?", "presentation": meta}
        assert fields(q, "context")["presentation"] == meta
        assert fields(q, "context")["presentation_status"]["state"] == state


def test_invalid_batch_and_on_cannot_bypass_author_validation(world):
    cv = world["cv"]
    _, parent, grant = _coordinator(world, a_conversation(world))
    before = len(cv.history())
    for args in ({"questions": [question(), question(because=None)]},
                 {"question": "Approve this work?", "on": cv._act(parent)["turn"], "form_detail": {"permission": True}}):
        with pytest.raises(NotPermitted, match="questions"):
            operate(world, grant, "request_decision", **args)
    assert len(cv.history()) == before


def test_metadata_roundtrips_pending_attached_reads_and_exact_reference_mapping(world):
    from mentis.fluid.inspect import about
    from mentis.fluid.home import needs_you_items
    cv = world["cv"]
    _, _, grant = _coordinator(world, a_conversation(world))
    q = question()
    q["presentation"]["primary"] = {"kind": "record", "id": "ent-0123456789ab", "label": "Missing proposal"}
    got = operate(world, grant, "request_decision", questions=[q, question("Which chart width?")])
    form = cv.decision_form(got["form"])
    assert form["pending"] and form["questions"][0]["presentation"] == q["presentation"]
    assert all(x["presentation_status"]["state"] == "complete" for x in form["questions"])
    items = needs_you_items(world["state"], at=0)["items"]
    row = next(x for x in items if x["key"] == got["form"])
    assert len(row["questions"]) == 2
    out = operate(world, grant, "respond", text="These are the chart questions.")
    assert cv.decision_form(got["form"])["post"] == out["turn"]
    mapping = about(world["state"], [got["expectation"]])["about"][0]["question_references"]
    assert mapping[0]["primary"]["availability"]["state"] == "missing"
    assert mapping[0]["primary"]["id"] == "ent-0123456789ab" and mapping[1]["primary"] is None


def create_outcome(q=None, **more):
    return {"result": "met", "summary": "Chart candidate prepared", "approval": {"mode": "create", "questions": [q or question()]}, **more}


def test_attachment_append_retry_changed_summary_and_conflict(world):
    cv = world["cv"]
    actor, parent, grant = _coordinator(world, a_conversation(world))
    asked = operate(world, grant, "request_decision", **question("Choose a chart width?"))
    out = operate(world, grant, "respond", text="Candidate ready", outcome=create_outcome())
    form = cv.decision_form(asked["form"])
    assert [q["index"] for q in form["questions"]] == [0, 1]
    d = cv._act(out["claim"])["detail"]
    assert d["approval_questions"] == [form["questions"][1]["expectation"]]
    assert len(cv.decision_forms_on(out["turn"])) == 1
    execution = cv._act(out["claim"])["execution"]
    retry = completion.claim(cv, parent, create_outcome(summary="Different report", evidence=["new evidence"]),
                             actor=actor, execution=execution, reply_turn=out["turn"], via="reply")
    assert cv._act(retry)["detail"]["approval_questions"] == d["approval_questions"]
    conflict = completion.claim(cv, parent, create_outcome(question("Different action?")),
                                actor=actor, execution=execution, reply_turn=out["turn"], via="reply")
    bad = cv._act(conflict)["detail"]
    assert "approval" not in bad and "conflicting_create" in bad["outcome_unclaimed"]["why"]
    assert completion.reconcile(cv, parent, conflict)["recorded"] == "pending"
    assert len(cv.decision_form(asked["form"])["questions"]) == 2


def test_existing_binding_keeps_closed_negative_answer_and_creates_nothing(world):
    cv = world["cv"]
    _, parent, grant = _coordinator(world, a_conversation(world))
    asked = operate(world, grant, "request_decision", **question())
    first = operate(world, grant, "respond", text="Please choose.")
    form = cv.decision_form(asked["form"])
    _answer(world, form, "Wait")
    before = cv.decision_form(asked["form"])
    out = operate(world, grant, "respond", text="Recording the exact binding.", outcome={"result": "partly", "approval": {
        "mode": "existing", "form": asked["form"], "questions": [asked["expectation"]]}})
    assert cv.decision_form(asked["form"]) == before
    assert cv._act(out["claim"])["detail"]["approval_questions"] == [asked["expectation"]]
    assert not cv.decision_forms_on(out["turn"])
    assert before["questions"][0]["answer"]["label"] == "Wait"


@pytest.mark.parametrize("closed,overflow", [(True, False), (False, True)])
def test_claim_time_refusals_keep_outcome_without_approval_or_met(world, closed, overflow):
    cv = world["cv"]
    actor, parent, grant = _coordinator(world, a_conversation(world))
    qs = [question(f"Choose chart {i}?") for i in range(20 if overflow else 1)]
    asked = operate(world, grant, "request_decision", questions=qs)
    first = operate(world, grant, "respond", text="Questions are ready.")
    if closed:
        _answer(world, cv.decision_form(asked["form"]), "Wait")
    out = completion.claim(cv, parent, create_outcome(), actor=actor,
                           execution=cv._act(first["said_act"])["execution"], reply_turn=first["turn"], via="reply")
    d = cv._act(out)["detail"]
    assert d["result"] == "met" and d["summary"] == "Chart candidate prepared"
    assert d["outcome_unclaimed"]["kind"] == "bad-approval" and "approval" not in d
    assert completion.reconcile(cv, parent, out)["recorded"] == "pending"
    assert len(cv.decision_form(asked["form"])["questions"]) == len(qs)


def test_structured_and_inline_json_match_and_shorthand_never_generates():
    out = create_outcome()
    text = "Ready\n\n```outcome\nresult: met\nsummary: Chart candidate prepared\napproval: " + json.dumps(out["approval"]) + "\n```"
    assert completion.inspect(text)["claim"] == completion.normalize(out)
    for value in ("commit abc123", "{broken", "", "[]"):
        raw = "Ready\n\n```outcome\nresult: met\napproval: " + value + "\n```"
        got = completion.inspect(raw)
        assert got["claim"] is None and got["text"] == raw
        assert got["unclaimed"]["kind"] == "bad-approval"


def test_prose_does_not_invent_yes_no_or_consequences():
    from mentis.web.prose_decisions import questions_in
    q, = questions_in([(0, "Should I merge the chart candidate?")])
    assert q["question"] == "Should I merge the chart candidate?" and "options" not in q


@pytest.mark.parametrize("metadata,expected", [(None, "legacy"), ({"version": 8, "future": [1]}, "unsupported"),
                                               ({}, "incomplete"), ([], "incomplete")])
def test_stored_formats_survive_pending_and_post_reads_without_rewrite(world, metadata, expected):
    from mentis.web import decisions_read
    cv = world["cv"]
    actor, parent, grant = _coordinator(world, a_conversation(world))
    q = question()
    if metadata is None:
        q.pop("presentation")
    else:
        q["presentation"] = metadata
    made = _decision_form(cv, {"questions": [q]}, actor=actor, parent=parent,
                          here=cv._act(parent)["conversation"], wrote=None,
                          execution=grant["instance"], where=lambda cid: cid,
                          act=lambda kind, **kw: cv.record_act(actor=actor, act=kind,
                              caused_by=parent, execution=grant["instance"], **kw))
    pending = decisions_read(world["state"], ids=[made["expectation"]])
    out = operate(world, grant, "respond", text="Historical fixture questions.")
    before = len(cv.history())
    posted = decisions_read(world["state"], post=out["turn"])
    resolved = _surface(world["state"]).resolve(out["turn"])
    for row in [pending["expectations"][0], posted["expectations"][0],
                resolved["decision_forms"][0]["questions"][0]]:
        assert row["presentation_status"]["state"] == expected
        if metadata is not None:
            assert row["presentation"] == metadata
    assert len(cv.history()) == before
