"""Where a Conversation is listed: Archive, Unarchive, Trash, Restore.

Each change is one act on the Conversation (`Conversations.
change_conversation_state`), through the Fluid door rename uses
(`POST /fluid/api/conversations/<id>/<archive|unarchive|trash|restore>`).
Nothing is rewritten or deleted: the record only grows, and the
Conversation's id, posts, replies, links and files are the same before and
after. Trash is refused while work is in flight. There is no permanent
deletion route.
"""
from __future__ import annotations

import itertools
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from mentis.conversation import (CONVERSATION_STATE_ACTS,
                                 trash_refusal_words)
from mentis.conversation.versions import Refused
from mentis.core.context_cache import revisions_for
from mentis.fluid import commands
from mentis.web import _Handler, _State, fixture
from mentis.worker import CAPABILITY_HEADER

_ops = itertools.count(1)


def text(s):
    return [{"type": "text", "text": s}]


@pytest.fixture()
def world(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    built = fixture.build(str(root))
    state = _State(str(root))
    import mentis.web as web
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    handler = type("H", (_Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    cv = state.cv
    me = built["who"]["@brian"]
    c = cv.open_conversation("Kept whole", attributed_to=me)
    root_post = cv.say(c, me, text("the first post"))
    reply = cv.say(c, me, text("a reply"), replies_to=root_post)
    nested = cv.say(c, me, text("a reply to the reply"), replies_to=reply)
    t = cv.open_topic(c, "Filed", attributed_to=me)
    cv.assign_topic(root_post, t)
    other = cv.open_conversation("Elsewhere", attributed_to=me)
    away = cv.say(other, me, text("placed into it"))
    cv.link_into(away, c, by=me)
    yield {"base": f"http://127.0.0.1:{httpd.server_address[1]}",
           "st": state, "cv": cv, "me": me, "c": c, "other": other,
           "posts": [root_post, reply, nested], "away": away, "topic": t}
    httpd.shutdown()


def _req(world, method, path, body=None, headers=None):
    req = urllib.request.Request(
        world["base"] + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1",
                 **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def change(world, cid, verb, **more):
    return _req(world, "POST", f"/fluid/api/conversations/{cid}/{verb}",
                {"author": world["me"], "op": f"st-{next(_ops)}", **more})


def listed(world, state=None, q=None):
    path = "/fluid/api/conversations?activity=1&limit=40"
    if state:
        path += f"&state={state}"
    if q:
        path += f"&q={q}"
    status, got = _req(world, "GET", path)
    assert status == 200, got
    return got


def snapshot(world):
    """Everything about the Conversation a change must leave untouched."""
    cv, c, st = world["cv"], world["c"], world["st"]
    corpus = st.corpus
    rows = corpus.links(to=c)
    return {
        "name": cv.conversation_name(c),
        "posts": [e["id"] for e in cv.contributions(c)],
        "links_to": sorted(x["id"] for x in rows),
        "replies": sorted(x["id"] for p in world["posts"]
                          for x in corpus.links(relation="replies-to", to=p)),
        "topics": [x["id"] for x in cv.topics(c)],
        "count": corpus._store.count(),
    }


def test_each_change_is_one_act_and_nothing_else_moves(world):
    cv, c = world["cv"], world["c"]
    before = snapshot(world)
    acts_before = world["st"].corpus._store.operational_count()
    for verb, state in (("archive", "archived"), ("unarchive", "active"),
                        ("trash", "trashed"), ("restore", "active"),
                        ("archive", "archived"), ("trash", "trashed"),
                        ("restore", "active")):
        status, got = change(world, c, verb)
        assert status == 200, got
        assert got["state"] == state and got["conversation"] == c
        assert got["projection"]["state"] == state
        assert cv.conversation_state(c) == state
        after = snapshot(world)
        assert after == before, "nothing of the Conversation is rewritten"
    # seven changes, seven acts (plus their operation keys), no entry written
    acts = world["st"].corpus.operational(conversation=c,
                                          act=tuple(CONVERSATION_STATE_ACTS))
    assert [a["act"] for a in acts] == [
        "conversation-archived", "conversation-unarchived",
        "conversation-trashed", "conversation-restored",
        "conversation-archived", "conversation-trashed",
        "conversation-restored"]
    assert all(a["actor"] == world["me"] for a in acts)
    assert world["st"].corpus._store.operational_count() > acts_before


def test_restore_is_the_same_conversation_with_its_associations(world):
    cv, c = world["cv"], world["c"]
    status, row0 = _req(world, "GET", f"/fluid/api/conversations?ids={c}")
    before = row0["conversations"][0]
    assert change(world, c, "trash")[0] == 200
    assert change(world, c, "restore")[0] == 200
    status, row1 = _req(world, "GET", f"/fluid/api/conversations?ids={c}")
    after = row1["conversations"][0]
    assert after["id"] == c
    for k in ("name", "posts", "included", "participants", "created",
              "last_activity", "topics" if "topics" in before else "name"):
        assert after[k] == before[k], k
    assert before["state_at"] is None, "never moved: no state time"
    # brought back: active, with the Restore's own time -- newer than the
    # Trash it undid, so a reader can order the two
    assert after["state"] == "active" and after["state_at"]
    acts = world["st"].corpus.operational(conversation=c, act=tuple(CONVERSATION_STATE_ACTS))
    assert acts[-1]["act"] == "conversation-restored"
    assert after["state_at"] == acts[-1]["at"] > acts[-2]["at"]
    assert after["state_by"] == world["me"]
    # the post placed into it is still there, and its home is unchanged
    assert world["away"] in {x["link"]["from"] for x in world["st"].corpus
                             .links(relation="linked-into", to=c)}


def test_wrong_state_is_refused_and_writes_nothing(world):
    c = world["c"]
    n = world["st"].corpus._store.operational_count()
    for verb in ("unarchive", "restore"):
        status, got = change(world, c, verb)
        assert status == 422 and got["refused"], got
    assert change(world, c, "trash")[0] == 200
    status, got = change(world, c, "archive")
    assert status == 422 and "in Trash" in got["error"]
    assert world["cv"].conversation_state(c) == "trashed"
    assert world["st"].corpus._store.operational_count() == n + 2  # act + its key


def test_trash_refused_while_a_run_works_there(world):
    cv, c = world["cv"], world["c"]
    ex = cv.begin_execution(participant=world["me"], conversation=c)
    status, got = change(world, c, "trash")
    assert status == 422 and got["code"] == "work-in-flight", got
    assert got["running"] == 1
    assert got["error"] == "1 run still working. Stop or finish them first."
    assert cv.conversation_state(c) == "active"
    # archive is allowed: the work continues while archived
    status, got = change(world, c, "archive")
    assert status == 200 and got["state"] == "archived"
    assert cv.active_executions(conversation=c), "archiving stops nothing"
    assert change(world, c, "trash")[0] == 422
    cv.end_execution(ex.reference)


def _owner(world):
    from mentis.operational.work_overview import owner_of
    owner = owner_of(world["cv"])
    assert owner, "the fixture Brain names its owner"
    return owner


def test_trash_refused_while_a_local_question_waits_for_the_owner(world):
    cv, c = world["cv"], world["c"]
    owner = _owner(world)
    agent = cv.create_participant("@Asker")
    asked = cv.say(c, agent, text("may I go ahead?"))
    cv.expect(asked, of=owner, kind="decision", by=agent)
    status, got = change(world, c, "trash")
    assert status == 422 and got["code"] == "work-in-flight", got
    assert got["waiting"] == 1
    assert got["error"] == "1 waiting for you. Stop or finish them first."
    # the domain decides it itself: no caller-supplied count is needed
    with pytest.raises(Refused):
        cv.change_conversation_state(c, "trash", by=world["me"])
    assert cv.conversation_state(c) == "active"


def test_trash_refused_while_work_here_waits_on_a_question_asked_elsewhere(world):
    """A request in this Conversation waits on an owner decision recorded in
    another: its work view says waiting-on-you, so Trash is refused here."""
    from mentis.operational.work import conversation_work
    cv, c, other = world["cv"], world["c"], world["other"]
    owner = _owner(world)
    agent = cv.create_participant("@Worker")
    asking = cv.say(c, owner, text("please do the work"))
    req = cv.expect(asking, of=agent, kind="result", by=owner)
    there = cv.say(other, agent, text("a question asked over there"))
    cv.expect(there, of=owner, kind="decision", by=agent, caused_by=req)
    states = [i["state"]["value"] for i in conversation_work(cv, c, viewer=owner)["items"]]
    assert "waiting-on-you" in states, states
    assert cv.work_in_flight(c)["waiting"] >= 1
    status, got = change(world, c, "trash")
    assert status == 422 and got["code"] == "work-in-flight", got
    with pytest.raises(Refused):
        cv.change_conversation_state(c, "trash", by=world["me"])
    assert cv.conversation_state(c) == "active"
    # archive still allowed
    assert change(world, c, "archive")[0] == 200


@pytest.mark.parametrize("mode", ["claimed-met-pending", "claimed-partly",
                                  "started-no-end"])
def test_an_owner_decision_elsewhere_refuses_trash_whatever_the_headline(world, mode):
    """The work's headline state can be a pending or partial claim, or a run
    started with no end, while an owner decision asked in another
    Conversation is still unanswered: Trash is refused all the same."""
    from mentis.operational.completion import claim
    from mentis.operational.work import conversation_work
    cv, c, other = world["cv"], world["c"], world["other"]
    owner = _owner(world)
    agent = cv.create_participant("@Claimer")
    asking = cv.say(c, owner, text("please do the work"))
    req = cv.expect(asking, of=agent, kind="result", by=owner)
    there = cv.say(other, agent, text("please decide"))
    question = cv.expect(there, of=owner, kind="decision", by=agent,
                         caused_by=req)
    if mode == "started-no-end":
        cv.record_act(actor=agent, act="execution-started", conversation=c,
                      turn=asking, caused_by=req, execution="exe-open",
                      about=[req])
    else:
        claim(cv, req, {"result": "met" if mode == "claimed-met-pending"
                        else "partly", "summary": "a decision is still owed"},
              actor=agent, via="test")
    item = next(i for i in conversation_work(cv, c, viewer=owner)["items"]
                if i["expectation"] == req)
    assert item["state"]["value"] != "waiting-on-you", item["state"]
    assert any(r["expectation"] == question for r in item["you_owe"]["value"])
    assert cv.work_in_flight(c)["waiting"] >= 1
    status, got = change(world, c, "trash")
    assert status == 422 and got["code"] == "work-in-flight", got
    with pytest.raises(Refused):
        cv.change_conversation_state(c, "trash", by=world["me"])
    assert cv.conversation_state(c) == "active"
    if mode == "started-no-end":
        assert got["running"] >= 1


@pytest.mark.parametrize("mode", ["child-started-no-end",
                                  "cross-conversation-child-live",
                                  "grandchild-started-no-end"])
def test_a_delegated_child_in_flight_refuses_trash(world, mode):
    """The parent reads waiting-on-child while a delegated child (or its own
    child) runs or has a start with no end -- here or in a conversation
    opened under the request: Trash is refused."""
    cv, c = world["cv"], world["c"]
    owner = _owner(world)
    parent = cv.create_participant("@Parent")
    kid = cv.create_participant("@Child")
    asking = cv.say(c, owner, text("do the work"))
    req = cv.expect(asking, of=parent, kind="result", by=owner)
    where = c
    if mode.startswith("cross"):
        where = cv.open_conversation("opened under the request",
                                     attributed_to=owner)
        cv.record_act(actor=parent, act="conversation-opened",
                      conversation=where, caused_by=req, about=[where])

    def delegate(by, to, under, conv):
        cp = cv.say(conv, by, text("delegated"), addressed_to=[to])
        child = cv.expect(cp, of=to, kind="result", by=by, caused_by=under,
                          detail={"returns_to": by})
        cv.record_act(actor=by, act="work-delegated", conversation=conv,
                      turn=cp, caused_by=under, about=[child],
                      detail={"participant": to, "return_expected": True})
        return cp, child
    cp, child = delegate(parent, kid, req, where)
    if mode == "grandchild-started-no-end":
        gk = cv.create_participant("@Grandchild")
        cp, child = delegate(kid, gk, child, where)
        actor = gk
    else:
        actor = kid
    cv.record_act(actor=actor, act="execution-started", conversation=where,
                  turn=cp, caused_by=child, execution="exe-" + mode,
                  about=[child])
    ex = None
    if mode.startswith("cross"):
        ex = cv.begin_execution(participant=kid, conversation=where,
                                for_expectation=child)
    assert cv.work_in_flight(c)["running"] >= 1
    status, got = change(world, c, "trash")
    assert status == 422 and got["code"] == "work-in-flight", got
    with pytest.raises(Refused):
        cv.change_conversation_state(c, "trash", by=world["me"])
    assert cv.conversation_state(c) == "active"
    if ex:
        cv.end_execution(ex.reference)


@pytest.mark.parametrize("mode", ["child-started-no-end",
                                  "child-owner-question-elsewhere",
                                  "grandchild-started-no-end"])
def test_work_located_here_for_a_request_elsewhere_refuses_trash(world, mode):
    """The request is in another conversation; THIS one holds only the
    delegated child (or grandchild). Its work in flight -- a start with no
    end, or an owner decision it waits on, asked in a third conversation --
    refuses Trash HERE, not only on the request's conversation."""
    cv, a = world["cv"], world["c"]
    owner = _owner(world)
    parent = cv.create_participant("@ParentHere")
    kid = cv.create_participant("@ChildHere")
    asking = cv.say(a, owner, text("do the work"))
    req = cv.expect(asking, of=parent, kind="result", by=owner)
    b = cv.open_conversation("the child's own", attributed_to=owner)
    cv.record_act(actor=parent, act="conversation-opened", conversation=b,
                  caused_by=req, about=[b])

    def delegate(under, where, by, to):
        cp = cv.say(where, by, text("delegation"), addressed_to=[to])
        child = cv.expect(cp, of=to, kind="result", by=by, caused_by=under,
                          detail={"returns_to": by})
        cv.record_act(actor=by, act="work-delegated", conversation=where,
                      turn=cp, caused_by=under, about=[child],
                      detail={"participant": to, "return_expected": True})
        return cp, child
    cp, child = delegate(req, b, parent, kid)
    target = b
    if mode.startswith("grandchild"):
        target = cv.open_conversation("the grandchild's own",
                                      attributed_to=owner)
        cp, child = delegate(child, target, kid, parent)
    if mode == "child-owner-question-elsewhere":
        elsewhere = cv.open_conversation("a question", attributed_to=owner)
        qp = cv.say(elsewhere, kid, text("please decide"))
        cv.expect(qp, of=owner, kind="decision", by=kid, caused_by=child)
    else:
        cv.record_act(actor=kid, act="execution-started", conversation=target,
                      turn=cp, caused_by=child, execution="exe-" + mode,
                      about=[child])
    flight = cv.work_in_flight(target)
    assert flight["running"] + flight["waiting"] >= 1, flight
    status, got = change(world, target, "trash")
    assert status == 422 and got["code"] == "work-in-flight", got
    with pytest.raises(Refused):
        cv.change_conversation_state(target, "trash", by=world["me"])
    assert cv.conversation_state(target) == "active"


@pytest.mark.parametrize("mode", ["partly", "met", "partly-pending",
                                  "partly-pending-same-home", "partly-live",
                                  "nested-met-continuation"])
def test_a_continuation_in_flight_refuses_trash_whatever_the_claim(world, mode):
    """A partial or met claim on the original work takes precedence over
    `continuing` in its headline; its continuation -- running, started with
    no end, recorded and pending, live, or a continuation of a continuation,
    here or in another conversation -- still refuses Trash of the original's
    conversation."""
    from mentis.operational import completion as C
    cv, a = world["cv"], world["c"]
    owner = _owner(world)
    agent = cv.create_participant("@Continuer")
    p = cv.say(a, owner, text("do work"))
    req = cv.expect(p, of=agent, kind="result", by=owner)
    claim = C.claim(cv, req, {"result": "partly" if mode.startswith("partly")
                              else "met", "summary": "original attempt",
                              "owner_wait": "the owner asks for the next part"},
                    actor=agent, via="test")
    C.reconcile(cv, req, claim)
    b = a if mode == "partly-pending-same-home" else cv.open_conversation(
        "continuation", attributed_to=owner)
    cp = cv.say(b, owner, text("carry on with the original work"))
    cont = cv.expect(cp, of=agent, kind="result", by=owner, caused_by=req)
    cv.grant_authority(cont, [], by=owner, source="continuation",
                       because="continues the original work", origin=req)
    if mode == "nested-met-continuation":
        middle = cont
        b = cv.open_conversation("deeper continuation", attributed_to=owner)
        cp = cv.say(b, owner, text("carry on further"))
        cont = cv.expect(cp, of=agent, kind="result", by=owner,
                         caused_by=middle)
        cv.grant_authority(cont, [], by=owner, source="continuation",
                           because="continues the original work",
                           origin=middle)
    if "pending" not in mode:
        cv.record_act(actor=agent, act="execution-started", conversation=b,
                      turn=cp, caused_by=cont, execution="exe-" + mode,
                      about=[cont])
    ex = (cv.begin_execution(participant=agent, conversation=b,
                             for_expectation=cont)
          if mode.endswith("-live") else None)
    assert cont in cv._continuation_line(req)
    assert cv.work_in_flight(a)["running"] >= 1
    status, got = change(world, a, "trash")
    assert status == 422 and got["code"] == "work-in-flight", got
    with pytest.raises(Refused):
        cv.change_conversation_state(a, "trash", by=world["me"])
    assert cv.conversation_state(a) == "active"
    if ex:
        cv.end_execution(ex.reference)


def test_trash_of_a_large_conversation_does_not_hold_the_writer(world):
    """1,000 requests, each with an ended run: Trash's check is read before
    the write, so another write waits well under a second, and the change
    itself goes through."""
    import threading
    import time
    from mentis.fluid import commands as cmds
    cv, st = world["cv"], world["st"]
    owner = _owner(world)
    agent = cv.create_participant("@Many")
    big = cv.open_conversation("a large conversation", attributed_to=owner)
    with st.corpus.atomic():
        for i in range(1000):
            post = cv.say(big, owner, text(f"request {i}"))
            req = cv.expect(post, of=agent, kind="result", by=owner)
            start = cv.record_act(actor=agent, act="execution-started",
                                  conversation=big, turn=post, caused_by=req,
                                  execution=f"exe-{i}", about=[req])
            cv.record_act(actor=agent, act="result-returned",
                          conversation=big, turn=post, caused_by=start,
                          execution=f"exe-{i}", about=[req])
    entered, held = threading.Event(), {}
    real = cv._flight

    def measured(*a, **kw):
        entered.set()
        return real(*a, **kw)
    cv._flight = measured
    got = {}

    def trash():
        t = time.perf_counter()
        got["status"], got["answer"], _ = cmds.conversation_state(
            st, big, "trash", {"author": owner})
        got["seconds"] = time.perf_counter() - t

    def other_write():
        entered.wait(10)
        waits = []
        while "status" not in got:
            t = time.perf_counter()
            cv.say(world["other"], owner, text("an unrelated write"))
            waits.append(time.perf_counter() - t)
            time.sleep(0.02)
        held["max"] = max(waits) if waits else 0.0
    try:
        th, wr = threading.Thread(target=trash), threading.Thread(target=other_write)
        th.start(); wr.start(); th.join(120); wr.join(30)
    finally:
        cv._flight = real
    assert entered.is_set(), "Trash's check was read through _flight"
    assert got["status"] == 200, got
    assert held["max"] < 1.0, (held, got["seconds"])


@pytest.mark.parametrize("mode", ["pending-continuation-home",
                                  "pending-delegation-home"])
def test_a_pending_child_whose_parent_is_elsewhere_refuses_trash_here(world, mode):
    """The request is in A; this conversation (B) holds its continuation,
    recorded and pending, or its delegated child, recorded and not started.
    The child's own incoming relationship makes it pending: Trash of B is
    refused although its parent is not in B."""
    cv, a = world["cv"], world["c"]
    owner = _owner(world)
    agent = cv.create_participant("@PendingChild")
    p = cv.say(a, owner, text("the parent request"))
    parent = cv.expect(p, of=agent, kind="result", by=owner)
    b = cv.open_conversation("the child's home", attributed_to=owner)
    cp = cv.say(b, owner, text("the child"))
    child = cv.expect(cp, of=agent, kind="result", by=owner, caused_by=parent)
    if mode.startswith("pending-continuation"):
        cv.grant_authority(child, [], by=owner, source="continuation",
                           because="carry on", origin=parent)
        assert cv.continuation_pending(child)
    else:
        cv.record_act(actor=agent, act="work-delegated", conversation=b,
                      turn=cp, caused_by=parent, about=[child],
                      detail={"participant": agent, "return_expected": True})
    assert cv.work_in_flight(b)["running"] >= 1
    status, got = change(world, b, "trash")
    assert status == 422 and got["code"] == "work-in-flight", got
    with pytest.raises(Refused):
        cv.change_conversation_state(b, "trash", by=world["me"])
    assert cv.conversation_state(b) == "active"


@pytest.mark.parametrize("how", ["claim_resumption", "raw"])
def test_a_resumption_awaiting_its_next_run_refuses_trash(world, how):
    """`work-resumed` with no run started or ended since: its dispatch is
    under way (`_resumption_pending`, `resumed-no-run`)."""
    import time as _t
    cv, a = world["cv"], world["c"]
    owner = _owner(world)
    agent = cv.create_participant("@Resumer")
    p = cv.say(a, owner, text("the resuming work"))
    req = cv.expect(p, of=agent, kind="result", by=owner)

    def ended(cid, post, e, exe):
        start = cv.record_act(actor=agent, act="execution-started",
                              conversation=cid, turn=post, caused_by=e,
                              execution=exe, about=[e])
        cv.record_act(actor=agent, act="result-returned", conversation=cid,
                      turn=post, caused_by=start, execution=exe, about=[e])
    if how == "claim_resumption":
        b = cv.open_conversation("awaited work", attributed_to=owner)
        q = cv.say(b, owner, text("awaited"))
        awaited = cv.expect(q, of=agent, kind="result", by=owner)
        assert cv.await_work(req, awaited, by=agent, because="needs it")
        ended(a, p, req, "parent-run")
        _t.sleep(0.03)
        ended(b, q, awaited, "awaited-run")
        assert cv.claim_resumption(req, event={"kind": "awaited-run-ended",
                                               "expectation": awaited})
    else:
        ended(a, p, req, "the-run")
        cv.record_act(actor="mentis", act="work-resumed", conversation=a,
                      turn=p, caused_by=req, about=[req])
    assert cv._resumption_pending(cv._own_acts(req))
    status, got = change(world, a, "trash")
    assert status == 422 and got["code"] == "work-in-flight", got
    with pytest.raises(Refused):
        cv.change_conversation_state(a, "trash", by=world["me"])
    assert cv.conversation_state(a) == "active"


@pytest.mark.parametrize("what", ["start", "question"])
def test_work_appended_while_the_check_is_read_is_not_missed(world, monkeypatch, what):
    """Something appended AFTER Trash's facts were read but before the write:
    the marker was taken before the facts, so the write sees the record
    moved, the check is read again, and Trash is refused."""
    import threading
    import mentis.fluid.read as R
    cv, a, other = world["cv"], world["c"], world["other"]
    owner = _owner(world)
    agent = cv.create_participant("@Racer")
    p = cv.say(a, owner, text("work that is about to start"))
    req = cv.expect(p, of=agent, kind="result", by=owner)
    real = R.needs_you_in            # the last fact _flight reads
    done = {"n": 0}

    def late(*args, **kw):
        out = real(*args, **kw)
        if done["n"] == 0:
            done["n"] = 1

            def append():
                if what == "start":
                    cv.record_act(actor=agent, act="execution-started",
                                  conversation=a, turn=p, caused_by=req,
                                  execution="exe-racer", about=[req])
                else:
                    q = cv.say(other, agent, text("decide please"))
                    cv.expect(q, of=owner, kind="decision", by=agent,
                              caused_by=req)
            t = threading.Thread(target=append)
            t.start(); t.join()
        return out
    monkeypatch.setattr(R, "needs_you_in", late)
    status, got = change(world, a, "trash")
    assert done["n"] == 1
    assert status == 422 and got["code"] == "work-in-flight", got
    assert cv.conversation_state(a) == "active"


def test_a_caller_can_add_runs_it_holds_but_never_lower(world, monkeypatch):
    c = world["c"]
    monkeypatch.setattr(commands, "in_flight",
                        lambda st, cid: {"running": 2, "waiting": 0})
    status, got = change(world, c, "trash")
    assert status == 422 and got["running"] == 2
    assert got["error"] == "2 runs still working. Stop or finish them first."
    owner = _owner(world)
    asker = world["cv"].create_participant("@Asker2")
    asked = world["cv"].say(c, asker, text("a question"))
    world["cv"].expect(asked, of=owner, kind="decision", by=asker)
    with pytest.raises(Refused):
        world["cv"].change_conversation_state(
            c, "trash", by=world["me"], in_flight={"running": 0, "waiting": 0})


def test_the_domain_refuses_trash_whoever_calls_it(world):
    with pytest.raises(Refused):
        world["cv"].change_conversation_state(
            world["c"], "trash", by=world["me"], in_flight={"waiting": 1})
    with pytest.raises(Refused):
        world["cv"].change_conversation_state(world["c"], "erase",
                                              by=world["me"])
    assert trash_refusal_words(0, 3) == "3 waiting for you. Stop or finish them first."


def test_same_door_as_rename_a_worker_grant_is_refused(world):
    status, got = _req(world, "POST",
                       f"/fluid/api/conversations/{world['c']}/archive",
                       {"author": world["me"], "op": "w-1"},
                       headers={CAPABILITY_HEADER: "anything"})
    assert status == 403
    status, got = _req(world, "POST",
                       f"/fluid/api/conversations/{world['c']}/archive",
                       {"op": "w-2"})
    assert status == 400, "it needs to say who it is by"
    status, got = _req(world, "POST",
                       f"/fluid/api/conversations/{world['c']}/archive",
                       {"author": "ent-000000000000", "op": "w-3"})
    assert status == 422
    assert world["cv"].conversation_state(world["c"]) == "active"


def test_no_deletion_route_exists(world):
    for verb in ("delete", "erase", "purge"):
        status, got = _req(world, "POST",
                           f"/fluid/api/conversations/{world['c']}/{verb}",
                           {"author": world["me"], "op": f"d-{verb}"})
        assert status == 405, (verb, got)
    assert world["cv"].is_conversation(world["c"])


def test_permanent_deletion_says_it_is_not_available(world):
    status, got = _req(world, "GET", "/fluid/api/conversation-deletion")
    assert status == 200
    assert got["available"] is False
    assert got["why"].startswith("Not available yet.")


def test_a_retry_is_the_same_change(world):
    c = world["c"]
    body = {"author": world["me"], "op": "same-key"}
    s1, a = _req(world, "POST", f"/fluid/api/conversations/{c}/archive", body)
    s2, b = _req(world, "POST", f"/fluid/api/conversations/{c}/archive", body)
    assert s1 == 200 and s2 == 200 and b.get("replayed") and a["act"] == b["act"]


def test_the_list_says_and_filters_by_state(world):
    c, other = world["c"], world["other"]
    every = {r["id"]: r for r in listed(world)["conversations"]}
    assert every[c]["state"] == "active"
    assert change(world, c, "archive")[0] == 200
    every = {r["id"]: r for r in listed(world)["conversations"]}
    assert every[c]["state"] == "archived", "unfiltered lists everything"
    assert every[c]["state_at"] and every[c]["state_by"] == world["me"]
    active = [r["id"] for r in listed(world, "active")["conversations"]]
    assert c not in active and other in active
    assert [r["id"] for r in listed(world, "archived")["conversations"]] == [c]
    assert listed(world, "trashed")["conversations"] == []
    assert change(world, other, "trash")[0] == 200
    assert [r["id"] for r in listed(world, "trashed")["conversations"]] == [other]
    assert [r["id"] for r in listed(world, "archived", q="kept")
            ["conversations"]] == [c]
    assert listed(world, "active", q="kept")["conversations"] == []
    status, got = _req(world, "GET",
                       "/fluid/api/conversations?activity=1&state=gone")
    assert status == 400


def test_active_pages_skip_what_is_away(world):
    cv, me = world["cv"], world["me"]
    made = [cv.open_conversation(f"Page {i}", attributed_to=me)
            for i in range(7)]
    for m in made[:4]:
        assert change(world, m, "archive")[0] == 200
    seen, cursor = [], None
    while True:
        path = "/fluid/api/conversations?activity=1&limit=2&state=active"
        if cursor:
            path += f"&cursor={cursor}"
        got = _req(world, "GET", path)[1]
        seen += [r["id"] for r in got["conversations"]]
        assert all(r["state"] == "active" for r in got["conversations"])
        cursor = got["next"]
        if not cursor:
            break
    assert not set(made[:4]) & set(seen)
    assert set(made[4:]) <= set(seen)
    assert len(seen) == len(set(seen))


@pytest.mark.parametrize("trash_at", [1794543999.0, 1794544000.0],
                         ids=["clock-stepped-back", "clock-tied"])
def test_rows_order_states_by_the_record_not_the_clock(world, trash_at):
    """Wall time can step back or tie; each row's `state_seq` is the latest
    state act's place in the record's append order, so a Trash recorded
    after an Unarchive is newer whatever the clock said."""
    from unittest.mock import patch
    c = world["c"]
    with patch("mentis.spine.seam._now", return_value=1794543998.0):
        assert change(world, c, "archive")[0] == 200
    with patch("mentis.spine.seam._now", return_value=1794544000.0):
        status, unarch = change(world, c, "unarchive")
    before = unarch["projection"]
    with patch("mentis.spine.seam._now", return_value=trash_at):
        status, got = change(world, c, "trash")
    assert status == 200
    after = got["projection"]
    assert after["state"] == "trashed" and before["state"] == "active"
    assert after["state_at"] <= before["state_at"], "the clock did not move on"
    assert isinstance(after["state_seq"], int) and after["state_seq"] > before["state_seq"]
    row = listed(world)["conversations"]
    assert next(r for r in row if r["id"] == c)["state_seq"] == after["state_seq"]
    # never moved: no sequence
    other = next(r for r in row if r["id"] == world["other"])
    assert other["state_seq"] is None and other["state_at"] is None
    # the row's keys, in order, as the Rust front must give them
    keys = list(after)
    assert keys[keys.index("state"):keys.index("state") + 4] == [
        "state", "state_at", "state_by", "state_seq"]


def test_state_acts_move_the_conversations_domain_and_the_cache(world):
    cv, c = world["cv"], world["c"]
    rev = revisions_for(world["st"].corpus)
    assert rev.classify_write({"act": "conversation-trashed",
                               "conversation": c}) == {
        "conversations", f"conversation:{c}"}
    assert cv.conversation_states() == {}
    cv.change_conversation_state(c, "archive", by=world["me"])
    assert cv.conversation_states()[c]["state"] == "archived"
    cv.change_conversation_state(c, "trash", by=world["me"])
    assert cv.conversation_states()[c]["state"] == "trashed"
    cv.change_conversation_state(c, "restore", by=world["me"])
    assert cv.conversation_states() == {}


def test_one_statement_for_a_pages_states(world, monkeypatch):
    from mentis.spine import store as S
    cv, c = world["cv"], world["c"]
    count = {"n": 0}
    real = S.Store._read_connection

    def traced(self):
        conn = real(self)
        conn.set_trace_callback(lambda stmt: count.__setitem__(
            "n", count["n"] + ("FROM operational" in stmt)))
        return conn
    monkeypatch.setattr(S.Store, "_read_connection", traced)
    world["st"].corpus._store._conn.set_trace_callback(
        lambda stmt: count.__setitem__("n", count["n"] + ("FROM operational" in stmt)))
    cv.conversation_states([c, world["other"]])
    assert count["n"] == 1
