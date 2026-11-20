"""One open Needs You item of every kind the server can ask the owner, in the
`world` fixture of `tests/_loop.py`, each made the way production makes it.

Shared by the server tests of what an item is about
(`tests/test_needs_you_inspect.py`) and the browser tests
(`tests/test_quiet_needs_you_inspect_browser.py`).

    form        a decision form of two questions on a post (`request_decision`),
                whose words name a record, a post, a post number, a deleted
                post and an id the Brain does not hold
    findings    a decision about work found along the way (`ask_about_findings`)
    permission  a run's permission question (a decision form marked
                `permission`, with its operation)
    adoption    a request to adopt a Brain record (`request_adoption`)
    input       a block waiting for the owner's input (`request_input`'s shape)
    request     a plain request addressed to the owner
    own_post    a decision asked as its own post, naming its material
"""

from __future__ import annotations

from mentis.conversation import text
from tests._loop import _coordinator, a_conversation

GONE = "ent-000000000000"          # an id no Brain holds


def build(world) -> dict:
    from mentis.conversation import ladder_writes, responses, versions
    from mentis.operational import ask_about_findings, trunk_of
    from mentis.web import _surface
    from mentis.worker import _decision_form, _operate
    cv, st, owner = world["cv"], world["state"], world["who"]["@brian"]
    cid = a_conversation(world, "Chart migration")
    other = a_conversation(world, "Evidence room")
    coach, parent, grant = _coordinator(world, cid)

    def op(name, **args):
        return _operate(_surface(st), name, args, grant)

    # -- what the asks will name ------------------------------------------------
    evidence = cv.say(other, coach, [text(
        "Measured the old chart loader: 41,211 rows, three rejects.\n\nDetails follow.")])
    removed = cv.say(other, coach, [text("A draft nobody should rely on.")])
    versions.delete(cv, removed, by=coach, because="superseded draft")
    rule = ladder_writes.record(
        cv, kind="lesson", body={"text": "Strip dangling links before migrating a chart.",
                                 "limits": "charts only"},
        basis=[evidence], by=coach, context={"conversation": cid})["entry"]
    # a record whose first words are the same as the rule's: never to be shown for it
    twin = ladder_writes.record(
        cv, kind="lesson", body={"text": "Strip dangling links before migrating a chart.",
                                 "limits": "a different lesson with the same words"},
        basis=[evidence], by=coach, context={"conversation": other})["entry"]
    number = cv.turn_number(evidence)

    # -- form: two questions on a post, their words naming things by id -----------
    request_turn = cv._act(parent)["turn"]
    asking = cv.say(cid, coach, [text(
        "The migration is ready. Two things need your decision before tonight.")],
        addressed_to=[owner], replies_to=request_turn)
    form = op("request_decision", on=asking, because="the migration cannot start without these",
              questions=[
                  {"question": f"Apply {rule} to tonight's migration, as measured in {evidence}?",
                   "because": f"the measurement is in {evidence}",
                   "options": [{"label": "Apply it", "consequence": "the three links are stripped first"},
                               {"label": "Hold the migration", "consequence": "nothing changes tonight"}]},
                  {"question": f"Should {removed} and {GONE} still be considered?",
                   "options": [{"label": "Yes"}, {"label": "No"}]}])

    # -- findings: what to do with work found along the way -----------------------
    found = [op("record_discovered_work", work=w, because="found on the way")["expectation"]
             for w in ("Reconcile the base branch", "Rename the old flags")]
    brain = st.brain
    offer = ask_about_findings(
        brain, found, conversation=cid, by=coach, owner=owner, caused_by=parent,
        originating_turn=trunk_of(brain, parent)["originating_turn"],
        question="Finished. What should happen to the 2 things found along the way?")

    # -- permission: a run asks to run an operation -------------------------------
    def act(name, **kw):
        kw.setdefault("caused_by", parent)
        return cv.record_act(actor=coach, act=name, execution="inst-perm", runtime="claude", **kw)

    operation = {"summary": "Delete the old chart cache", "kind": "execute",
                 "command": "Remove-Item -Recurse C:\\charts\\cache", "cwd": "C:\\charts",
                 "tool": "shell", "tool_label": "PowerShell", "resources": ["C:\\charts\\cache"],
                 "workspace": "C:\\charts", "within": False,
                 "outside": ["it deletes files"], "why": "coordinate the chart",
                 "agent_says": "The cache is stale and blocks the migration."}
    run = cv.record_act(actor=coach, act="execution-started", conversation=cid, turn=request_turn,
                        execution="inst-perm", runtime="claude", caused_by=parent, because="test run")
    perm = _decision_form(
        cv, {"because": "the agent asked permission for this while it works",
             "questions": [{"question": "@Coach asks to delete the old chart cache (outside this task: it deletes files)?",
                            "because": "the agent asked permission for this while it works; it waits for your answer",
                            "options": [{"label": "Allow once", "consequence": "Only this operation; the next one like it is asked again."},
                                        {"label": "Deny", "consequence": "Refuse this operation; @Coach is told it was refused."}]}],
             "on": request_turn},
        actor=coach, parent=parent, here=cid, wrote=None, act=act, where=lambda c: c,
        form_detail={"permission": True, "run": run,
                     "tool": {"title": operation["summary"], "kind": "execute"},
                     "operation": operation},
        execution="inst-perm")

    # -- adoption: a proposal awaiting the owner ----------------------------------
    adoption = op("request_adoption", entry=rule, because="it held on two migrations")

    # -- input: a block waiting for the owner -------------------------------------
    block_post = cv.say(cid, coach, [text(
        "Fill in the cut-over window.\n\n```form version=1 name=cutover\n"
        "when: text \"When may it start?\" required\n```")], addressed_to=[owner])
    sid = responses.open_set(cv, block_post, block="cutover", by=coach)["set"]
    wait = cv.expect(block_post, of=owner, kind="input", by=coach, caused_by=parent,
                     because="the cut-over window only you can give",
                     detail={"response_set": sid, "block": "cutover", "part": 0,
                             "ready_before": []})

    # -- request: a plain ask of the owner ----------------------------------------
    asked = cv.say(cid, coach, [text(
        f"Can you confirm the old loader is retired? See #{number} is not here; the measurement is {evidence}.")],
        addressed_to=[owner])
    plain = cv.expect(asked, of=owner, kind="clarification", by=coach,
                      because="nobody else knows whether it is retired")

    # -- own post: a decision asked as its own post, naming its material -----------
    own = cv.say(cid, coach, [text("Should the lesson about dangling links stand as written?")],
                 addressed_to=[owner])
    own_exp = cv.expect(own, of=owner, kind="decision", by=coach, material=[twin],
                        because="it is cited by tonight's plan",
                        detail={"options": [{"label": "Keep it"}, {"label": "Rewrite it"}]})

    return {"cid": cid, "other": other, "coach": coach, "parent": parent, "grant": grant,
            "evidence": evidence, "evidence_number": number, "removed": removed,
            "rule": rule, "twin": twin, "asking": asking, "form": form["form"],
            "form_questions": [q["expectation"] for q in form["questions"]],
            "findings": found, "findings_decision": offer["expectation"],
            "findings_post": offer["turn"], "originating": trunk_of(brain, parent)["originating_turn"],
            "permission": perm["form"], "run": run, "request_turn": request_turn,
            "adoption": adoption, "input": wait, "input_post": block_post, "set": sid,
            "plain": plain, "plain_post": asked, "own": own_exp, "own_post": own}
