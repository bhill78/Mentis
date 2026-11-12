"""Reply context, approval identity and thread placement (Workstream R).

THE INCIDENT, RECONSTRUCTED (continuity report, 2026-11-11). A Builder
delivered round 3 of a design under a Caretaker's request; a newer, unrelated
delivery (the attachment-strip fix) came after it; the owner approved round 3
by REPLYING to its delivery. The run that carried the approval was given the
approval's words and the last four posts, took "this work" to mean the newest
delivery, and merged and deployed that.

What holds now, through the real post, owe, dispatch and worker paths:

  * the dispatched task names the reply target -- post, author, position,
    opening words -- and the work it belongs to: the request it answered, the
    delegation that produced it, the request above that, its claim evidence
    and what it returned; never the newer unrelated delivery;
  * the request records `in_reply_to` additively, and a resumed run, and the
    brief for the request, still carry it;
  * `resolve` of a Turn says what it replies to, what replies to it and the
    work it belongs to;
  * a run places decision forms and outcome records only within its work's
    thread, and its answer only under the request's own post;
  * earlier rounds the owner has since replied past say so in work_overview,
    in the "already being carried" list and against decisions;
  * `history` of a Conversation gives posts; work_overview titles skip a
    leading @mention.
"""

from __future__ import annotations

import time

import pytest

from mentis.conversation import text
from mentis.execution import RunResult
from tests._loop import (a_conversation, grant_of_run, say,  # noqa: F401
                         script_every_backend, world)


@pytest.fixture()
def told(world, monkeypatch):
    """Dispatch for real; each run records its grant and prompt and stops."""
    import mentis.web as web
    from mentis.web import dispatch as D
    svc = world["state"].agents
    seen: list[dict] = []

    def stop(spec):
        seen.append({"grant": grant_of_run(svc, spec, world["state"].path),
                     "prompt": spec.prompt})
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=False, error_kind="test_stop",
                         error="stopped once the grant was minted",
                         started_at=now, finished_at=now)

    script_every_backend(svc, stop)
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: D.dispatch(world["state"], **kw))
    return seen


def _tick():
    time.sleep(0.03)        # acts in write order with distinct times


def _answer(cv, cid, by, request, words, *, replies_to, claim=None,
            returned=()):
    """A run's answer post, as `respond` writes it: the Turn under the
    request's post, its `turn-said`, a claim, and any returned artifacts."""
    from mentis.operational import completion
    turn = cv.say(cid, by, [text(words)], replies_to=replies_to)
    cv.record_act(actor=by, act="turn-said", conversation=cid, turn=turn,
                  caused_by=request,
                  because="this execution's answer to the request it carries",
                  detail={"answers_request": request,
                          "answers_turn": replies_to})
    if claim:
        completion.claim(cv, request, claim, actor=by, via="respond",
                         reply_turn=turn, conversation=cid)
        if claim["result"] == "met":
            cv.record_act(actor=by, act="expectation-met", conversation=cid,
                          turn=replies_to, caused_by=request,
                          because="claimed met")
    for ref in returned:
        cv.record_act(actor=by, act="artifact-returned", conversation=cid,
                      caused_by=request, about=[ref])
    _tick()
    return turn


def _incident(world):
    """The record of the evening, built through the owner's door and the
    record's own writers. Every owner request is dispatched by address; its
    run is captured, not run."""
    cv = world["cv"]
    cid = a_conversation(world, "Quiet Chat")
    care = cv.create_participant("@Caretaker")
    build = cv.create_participant("@Builder-QuietComposer")

    def ask(words, **kw):
        out = say(world, cid, words, action="ask-participant",
                  dispatch=[{"participant": care, "work": words}], **kw)
        _tick()
        return out["turn"], out["expectations"][0]

    # round 2: asked, presented, claimed partly -- left open
    p2, r2 = ask("@Caretaker one composer revision, then wait for my decision")
    a2 = _answer(cv, cid, care, r2, "Round 2 is ready: 6357352",
                 replies_to=p2,
                 claim={"result": "partly", "summary": "round 2 presented",
                        "evidence": ["commit 6357352"]})
    # round 3: the owner rejects round 2 by replying to it -- a NEW request
    p3, r3 = ask("@Caretaker no, this is not it; another round",
                 replies_to=a2)
    # the Caretaker delegates round 3 to the Builder
    d3 = cv.say(cid, care, [text("@Builder-QuietComposer build round 3")],
                replies_to=p3)
    child = cv.expect(d3, of=build, kind="result", by=care, caused_by=r3,
                      because="round 3")
    cv.record_act(actor=care, act="work-delegated", conversation=cid,
                  turn=d3, caused_by=r3, about=[child])
    _tick()
    b3 = _answer(cv, cid, build, child,
                 "Round 3 is committed: Operations settings list pull-outs",
                 replies_to=d3,
                 claim={"result": "met", "summary": "round 3 built",
                        "evidence": ["commit 4037e33"]},
                 returned=["adm-round3screens"])
    c3 = _answer(cv, cid, care, r3,
                 "Round 3 is back; implementation waits on your say-so",
                 replies_to=p3,
                 claim={"result": "met", "summary": "round 3 presented",
                        "evidence": ["commit 4037e33"]})
    # the screenshot line: a separate request, delivered LATER
    ps, rs = ask("@Caretaker attach screenshots so I control how I view them")
    fix = _answer(cv, cid, care, rs,
                  "Attachment-strip fix built: 8d57515",
                  replies_to=ps,
                  claim={"result": "met", "summary": "attachment fix",
                         "evidence": ["commit 8d57515"]})
    return {"cid": cid, "care": care, "build": build, "p2": p2, "r2": r2,
            "a2": a2, "p3": p3, "r3": r3, "d3": d3, "child": child,
            "b3": b3, "c3": c3, "ps": ps, "rs": rs, "fix": fix}


def _approve(world, w):
    out = say(world, w["cid"],
              "@Caretaker I approve of this work. Can you go ahead, merge it, "
              "check it into git, and arm the deployment?",
              replies_to=w["b3"], action="ask-participant",
              dispatch=[{"participant": w["care"],
                         "work": "@Caretaker I approve of this work. Can you "
                                 "go ahead, merge it, check it into git, and "
                                 "arm the deployment?"}])
    return out["turn"], out["expectations"][0]


def _reply_block(prompt):
    """The IN REPLY TO block of a prompt's task, alone."""
    start = prompt.index("IN REPLY TO.")
    end = prompt.index("\n---\n", start)
    return prompt[start:end]


# -- 1, 2. the reply target reaches the run, and stays on the request -----------

def test_the_approval_s_run_is_told_round_three_and_not_the_newer_delivery(
        world, told):
    cv = world["cv"]
    w = _incident(world)
    approval, req = _approve(world, w)
    prompt = told[-1]["prompt"]
    block = _reply_block(prompt)
    # the task opens with the owner's words, then the reply target
    assert prompt.index("# Your task") < prompt.index("IN REPLY TO.")
    assert w["b3"] in block and "@Builder-QuietComposer" in block
    assert f"#{cv.turn_number(w['b3'])} " in block
    assert "Round 3 is committed" in block
    assert w["child"] in block and w["r3"] in block      # request + parent
    assert "4037e33" in block and "adm-round3screens" in block
    assert w["d3"] in block                               # the delegation
    # never the attachment fix, never round 2
    for wrong in (w["fix"], w["rs"], "8d57515", w["r2"], w["a2"], "6357352"):
        assert wrong not in block, wrong
    # said as context, not as a decision
    assert "not a decision" in block
    # the orientation says what the carried post replies to, with no Topic
    assert f"The post you are carrying ({approval}) replies to:" in prompt
    after = prompt.index(f"The post you are carrying ({approval})")
    assert w["b3"] in prompt[after:after + 300]


def test_the_request_records_in_reply_to_and_never_round_two_or_the_fix(
        world, told):
    cv = world["cv"]
    w = _incident(world)
    _, req = _approve(world, w)
    got = cv._act(req)["detail"]["in_reply_to"]
    assert got["turn"] == w["b3"]
    assert got["author"] == w["build"]
    assert got["requests"] == [w["child"], w["r3"]]
    assert w["r2"] not in got["requests"] and w["rs"] not in got["requests"]
    # threading, not lineage: it continues nothing
    assert cv._act(req).get("caused_by") is None
    # and the earlier rejection recorded its own target: round 2's answer
    assert cv._act(w["r3"])["detail"]["in_reply_to"]["requests"] == [w["r2"]]


def test_a_resumed_run_and_the_brief_still_carry_the_reply_target(
        world, told):
    from mentis.web import _surface
    from mentis.web import dispatch as D
    w = _incident(world)
    approval, req = _approve(world, w)
    # a later run of the SAME request -- a resume -- reads it from the record
    D.dispatch(world["state"], conversation=w["cid"], turn=approval,
               participant=w["care"],
               work="Resuming the work you were carrying.",
               expectation=req, question="approve round 3")
    block = _reply_block(told[-1]["prompt"])
    assert w["b3"] in block and w["child"] in block
    assert w["fix"] not in block
    # the brief for the request says it too
    brief = _surface(world["state"]).brief(w["cid"], w["care"],
                                           expectation=req)
    rendered = brief["prepared"]["rendered"]
    assert "IN REPLY TO." in rendered and w["b3"] in rendered
    assert w["fix"] not in _reply_block(rendered + "\n---\n")


def test_a_request_that_replies_to_nothing_is_told_nothing_new(world, told):
    w = _incident(world)
    prompt = told[-1]["prompt"]          # the screenshot request's run
    assert "IN REPLY TO." not in prompt
    assert "The post you are carrying" not in prompt
    assert w["fix"]                       # (the record was built)


# -- 3. resolve of a Turn -----------------------------------------------------------

def test_resolve_of_a_turn_says_its_thread_and_work(world, told):
    from mentis.web import _surface
    w = _incident(world)
    approval, req = _approve(world, w)
    s = _surface(world["state"])
    got = s.resolve(approval)
    assert got["replies_to"] == w["b3"]
    ident = got["in_reply_to"]
    assert ident["turn"] == w["b3"]
    assert [r["expectation"] for r in ident["requests"]] == [w["child"]]
    first = ident["requests"][0]
    assert first["delegated"]["parent"] == w["r3"]
    assert first["claim"]["evidence"] == ["commit 4037e33"]
    assert first["returned"] == ["adm-round3screens"]
    assert [r["expectation"] for r in got["work"]] == [req]
    b3 = s.resolve(w["b3"])
    assert approval in b3["replies"] and b3["replies_to"] == w["d3"]
    assert [r["expectation"] for r in b3["work"]] == [w["child"]]


# -- 4. thread placement ---------------------------------------------------------------

def _run_grant(world, w, told):
    _, req = _approve(world, w)
    return req, told[-1]["grant"]


def _op(world, name, args, grant):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), name, args, grant)


def test_a_decision_form_goes_only_within_the_work_s_thread(world, told):
    from mentis.worker import NotPermitted
    w = _incident(world)
    req, grant = _run_grant(world, w, told)
    q = {"question": "Merge round 3 (4037e33) into main?",
         "options": [{"label": "Merge"}, {"label": "Hold"}]}
    with pytest.raises(NotPermitted) as refused:
        _op(world, "request_decision", {**q, "on": w["fix"]}, grant)
    words = str(refused.value)
    assert w["fix"] in words and "not in the thread" in words
    assert w["b3"] in words                 # where it may go, listed
    # on the reply target, it is within the thread
    out = _op(world, "request_decision", {**q, "on": w["b3"]}, grant)
    assert out.get("ok") is not False and "error" not in out


def test_an_outcome_cannot_be_recorded_against_an_unrelated_post(world, told):
    """The 22:56 outcome named the attachment-fix post as its basis."""
    from mentis.worker import NotPermitted
    w = _incident(world)
    req, grant = _run_grant(world, w, told)
    approval = world["cv"]._act(req)["turn"]
    body = {"text": "merged, pushed and armed", "result": "merged",
            "attempted": True}
    with pytest.raises(NotPermitted) as refused:
        _op(world, "record_material",
            {"kind": "outcome", "body": body, "outcome_of": approval,
             "in_context": w["cid"], "basis": [approval, w["fix"]]}, grant)
    assert w["fix"] in str(refused.value)
    out = _op(world, "record_material",
              {"kind": "outcome", "body": body, "outcome_of": approval,
               "in_context": w["cid"], "basis": [approval, w["b3"]]}, grant)
    assert out.get("entry")


def test_an_answer_goes_under_the_request_s_own_post(world, told):
    from mentis.conversation import REPLIES_TO
    from mentis.worker import NotPermitted
    cv = world["cv"]
    w = _incident(world)
    req, grant = _run_grant(world, w, told)
    approval = cv._act(req)["turn"]
    with pytest.raises(NotPermitted) as refused:
        _op(world, "respond", {"text": "done", "replies_to": w["fix"]}, grant)
    assert approval in str(refused.value) and "Leave" in str(refused.value)
    out = _op(world, "respond", {"text": "done", "replies_to": approval},
              grant)
    assert [x["link"]["to"] for x in cv._c.links(relation=REPLIES_TO,
                                                 frm=out["turn"])] == [approval]
    out = _op(world, "respond", {"text": "and more"}, grant)
    assert [x["link"]["to"] for x in cv._c.links(relation=REPLIES_TO,
                                                 frm=out["turn"])] == [approval]


# -- 5. superseded rounds ------------------------------------------------------------------

def test_an_earlier_round_says_the_owner_replied_to_a_later_one(world, told):
    from mentis.conversation import threads
    from mentis.conversation.owner import _owner
    from mentis.web import _surface
    cv = world["cv"]
    w = _incident(world)
    approval, req = _approve(world, w)
    owner = _owner(cv)
    got = threads.owner_replied_later(cv, w["r2"], owner)
    assert got == {"turn": approval, "request": req,
                   "at": got["at"], "via": w["b3"]}
    # the screenshot line was never replied past
    assert threads.owner_replied_later(cv, w["rs"], owner) is None
    # work_overview says it beside round 2, and not beside the fix
    from mentis.operational import current_work as cw
    cw.current_work(cv).current(wait_s=5)
    view = _surface(world["state"]).work_overview(w["cid"])
    rows = {i["expectation"]: i for i in view["items"]}
    assert rows[w["r2"]]["owner_replied"]["request"] == req
    assert (f"owner replied: {approval} → {req}"
            in rows[w["r2"]]["owner_replied"]["words"])
    assert "owner_replied" not in rows.get(w["rs"], {})
    # and the "already being carried" list of the next addressed request
    say(world, w["cid"], "@Caretaker one more thing", action="ask-participant",
        dispatch=[{"participant": w["care"], "work": "one more thing"}])
    prompt = told[-1]["prompt"]
    line = next(x for x in prompt.splitlines()
                if x.startswith(f"- request {w['r2']}"))
    assert f"owner replied: {approval} → {req}" in line


def test_a_decision_under_a_replied_past_round_says_so(world, told):
    from tests.decision_asked import asked_as_own_turn
    cv = world["cv"]
    w = _incident(world)
    # a decision asked under round 2, still open
    grant = {"participant": w["care"], "expectation": w["r2"],
             "conversation": w["cid"]}
    asked = asked_as_own_turn(world, grant, "Implement round 2?")
    _tick()
    approval, req = _approve(world, w)
    o = cv.orientation(w["cid"], w["care"])
    row = next(r for r in o["decisions"]["open"]
               if r["expectation"] == asked["expectation"])
    assert row["owner_replied"]["request"] == req
    from mentis.conversation import _render_orientation
    said = _render_orientation(o)
    assert f"owner replied since: {approval} → {req}" in said


# -- 6. retrieval polish -------------------------------------------------------------------

def test_history_of_a_conversation_gives_posts(world, told):
    from mentis.web import _surface
    w = _incident(world)
    s = _surface(world["state"])
    got = s.history(conversation=w["cid"])
    assert got["view"] == "posts"
    assert got["posts"][0]["turn"] == w["fix"]
    assert got["posts"][0]["replies_to"] == w["ps"]
    assert "Attachment-strip fix" in got["posts"][0]["said"]
    assert "acts" not in got
    acts = s.history(conversation=w["cid"], view="acts")
    assert "acts" in acts and acts["acts"]
    assert "acts" in s.history(turn=w["b3"])          # a filter means acts
    assert s.history(view="posts").get("refused")
    assert s.history(conversation=w["cid"], view="x").get("refused")


def test_work_overview_titles_skip_a_leading_mention(world, told):
    from mentis.operational import work_overview as wo
    assert wo._without_leading_mentions("@Caretaker\nShip round 3") \
        == "Ship round 3"
    assert wo._without_leading_mentions("@Caretaker I approve this") \
        == "I approve this"
    assert wo._without_leading_mentions("@Caretaker") == "@Caretaker"
    assert wo._without_leading_mentions("no mention here") == "no mention here"
