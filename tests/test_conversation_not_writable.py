"""Trash and Deleted are not writable, enforced at the backend (contract §4).

Every write route is driven over HTTP against a Conversation in Trash
(refused, 409 `conversation-in-trash`, nothing written that touches it),
after Restore (accepted), and after permanent deletion (refused, 409
`conversation-deleted`). Archive never refuses. The guard sits on the store
every interface writes through (`conversation.erasure.Guard`), so the sweep
at the end also drives every other POST the server and the worker door
answer, with this conversation's ids, and checks that nothing touching it was
written whatever each answered.
"""
from __future__ import annotations

import json
import time

import pytest

from mentis import artifacts
from mentis.conversation import erasure as ER
from mentis.worker import CAPABILITY_HEADER, OPERATIONS, READ_ONLY
from tests.test_conversation_erasure import (_req, change, delete, text,
                                             trash, world)  # noqa: F401


def touching(world, cid):
    """Every row that names the conversation, one of its posts or topics."""
    conn = world["corpus"]._store._conn
    ids = {cid} | {r[0] for r in conn.execute(
        "SELECT link_from FROM entry WHERE link_relation IN "
        "('in-conversation', 'topic-of') AND link_to = ?", (cid,))}
    js = json.dumps(sorted(ids))
    rows = set()
    rows |= {("e", r[0]) for r in conn.execute(
        "SELECT id FROM entry WHERE link_from IN (SELECT value FROM "
        "json_each(?)) OR link_to IN (SELECT value FROM json_each(?))",
        (js, js))}
    rows |= {("o", r[0]) for r in conn.execute(
        "SELECT o.id FROM operational o WHERE o.conversation IN (SELECT "
        "value FROM json_each(?)) OR o.turn IN (SELECT value FROM "
        "json_each(?)) OR EXISTS (SELECT 1 FROM json_each(o.about) a WHERE "
        "a.value IN (SELECT value FROM json_each(?)))", (js, js, js))}
    rows |= {("d", r[0]) for r in conn.execute(
        "SELECT id FROM delivery WHERE conversation = ?", (cid,))}
    return rows


def _grant(world, cid):
    """A run's grant in `cid`, as a coordinator's is minted (tests/_loop)."""
    st, cv = world["st"], world["cv"]
    coach = cv.create_participant("@Coach")
    status, got = _req(world, "POST", f"/api/conversations/{cid}/turns",
                       {"author": world["me"], "text": "@Coach coordinate",
                        "action": "ask-participant",
                        "dispatch": [{"participant": coach,
                                      "work": "coordinate",
                                      "coordinate": True}]})
    assert status == 200, got
    parent = got["expectations"][0]
    auth = st.agents.authority
    iid = f"nw-{parent[-6:]}"
    auth.authorise_for(iid, dict(scope="organising",
                                 operations=cv.authority_of(parent)[
                                     "operations"],
                                 expectation=parent, conversation=cid,
                                 participant=coach, runtime="claude"))
    return auth._grant(iid, st.path), parent, coach


def _op(world, token, op, /, **args):
    return _req(world, "POST", "/api/worker",
                {"corpus": world["st"].path, "op": op, "args": args},
                headers={CAPABILITY_HEADER: token})


def _end_the_run(world, parent, coach):
    """The coordinator's request answered, so Trash's work check passes."""
    cv, c = world["cv"], world["c"]
    turn = cv._act(parent)["turn"]
    cv.say(c, coach, text("done"), replies_to=turn)
    cv.record_act(actor=coach, act="result-returned", conversation=c,
                  caused_by=parent, about=[parent], detail={"ok": True})
    cv.record_act(actor=world["me"], act="expectation-met",
                  conversation=c, caused_by=parent, about=[parent],
                  detail={})


def _routes(world, token, asked):
    """(name, method, path, body, worker?) for the write routes, built with
    this conversation's ids. Each body is a valid write when the
    conversation is active."""
    c, me = world["c"], world["me"]
    p1 = world["posts"][0]
    away = world["away"]
    other = world["other"]
    staged = artifacts.stage(world["root"], b"attach " + str(time.time())
                             .encode(), "text/plain")["staged"]
    n = iter(range(10_000))

    def op():
        return f"nw-{time.time_ns()}-{next(n)}"
    return [
        ("fluid post", "POST", "/fluid/api/posts",
         lambda: {"author": me, "conversation": c, "parts": text("new"),
                  "op": op()}),
        ("fluid reply", "POST", "/fluid/api/posts",
         lambda: {"author": me, "conversation": c, "parts": text("re"),
                  "replies_to": p1, "op": op()}),
        ("fluid attachment", "POST", "/fluid/api/posts",
         lambda: {"author": me, "conversation": c, "op": op(),
                  "parts": [{"type": "file", "ref": staged,
                             "alt": "a.txt", "media_type": "text/plain"}]}),
        ("fluid edit", "POST", f"/fluid/api/posts/{p1}/edit",
         lambda: {"attributed_to": me, "text": f"edited {op()}"}),
        ("fluid comment", "POST", f"/fluid/api/posts/{p1}/comments",
         lambda: {"author": me, "text": "a comment", "op": op()}),
        ("fluid reaction", "POST", f"/fluid/api/posts/{p1}/reactions",
         lambda: {"author": me, "token": "+1", "op": op()}),
        ("fluid rename", "POST", f"/fluid/api/conversations/{c}/name",
         lambda: {"author": me, "name": f"renamed {op()}", "op": op()}),
        ("fluid link into it", "POST", f"/fluid/api/conversations/{c}/members",
         lambda: {"author": me, "add": [world["o_shared"]], "op": op()}),
        ("fluid link out of it", "POST",
         f"/fluid/api/conversations/{other}/members",
         lambda: {"author": me, "add": [p1], "op": op()}),
        ("api turn", "POST", f"/api/conversations/{c}/turns",
         lambda: {"author": me, "text": "api words"}),
        ("api topic", "POST", f"/api/conversations/{c}/topics",
         lambda: {"name": f"topic {op()}", "author": me}),
        ("api participant", "POST", f"/api/conversations/{c}/participants",
         lambda: {"alias": "@Vera", "author": me}),
        ("api file to topic", "POST",
         f"/api/turns/{world['posts'][1]}/topics",
         lambda: {"topic": world["topic"], "by": me}),
        ("api link", "POST", f"/api/turns/{world['o_shared']}/link",
         lambda: {"conversation": c, "by": me}),
        ("api request", "POST", f"/api/conversations/{c}/turns",
         lambda: {"author": me, "text": "@Vera look",
                  "action": "ask-participant",
                  "dispatch": [{"participant": world["who"]["@Vera"],
                                "work": "look"}]}),
        ("worker respond", "WORKER", "respond",
         lambda: {"text": "a result", "replies_to": asked}),
        ("worker record_material", "WORKER", "record_material",
         lambda: {"kind": "note", "body": {"text": "n"},
                  "in_context": c}),
        ("worker delegate", "WORKER", "delegate",
         lambda: {"participant": world["who"]["@Ada"], "work": "w"}),
        ("worker open_topic", "WORKER", "open_topic",
         lambda: {"name": f"t {op()}"}),
        ("worker anchor", "WORKER", "anchor",
         lambda: {"version": p1, "type": "version"}),
        ("worker request_decision", "WORKER", "request_decision",
         lambda: {"question": "which?", "on": asked}),
    ]


def _send(world, token, method, path, body):
    if method == "WORKER":
        return _op(world, token, path, **body)
    return _req(world, method, path, body)


def test_every_write_route_is_refused_in_trash_and_accepted_after_restore(
        world):
    c = world["c"]
    token, parent, coach = _grant(world, c)
    _end_the_run(world, parent, coach)
    routes = _routes(world, token, world["cv"]._act(parent)["turn"])
    trash(world)
    refused = {}
    for name, method, path, body in routes:
        before = touching(world, c)
        status, got = _send(world, token, method, path, body())
        after = touching(world, c)
        assert after == before, (name, status, got, after - before)
        refused[name] = (status, got.get("code"), got.get("error"))
    wrong = {k: v for k, v in refused.items()
             if v[:2] != (409, "conversation-in-trash")}
    assert not wrong, wrong
    status, _ = change(world, c, "restore")
    assert status == 200
    accepted = {}
    for name, method, path, body in routes:
        status, got = _send(world, token, method, path, body())
        accepted[name] = (status, got.get("error") if status >= 300 else None)
    bad = {k: v for k, v in accepted.items() if v[0] >= 300}
    assert not bad, bad


def test_a_deleted_conversation_refuses_everything(world):
    c = world["c"]
    token, parent, coach = _grant(world, c)
    _end_the_run(world, parent, coach)
    routes = _routes(world, token, world["cv"]._act(parent)["turn"])
    trash(world)
    delete(world)
    for name, method, path, body in routes:
        before = touching(world, c)
        status, got = _send(world, token, method, path, body())
        assert touching(world, c) == before, name
        assert status == 409 and got.get("code") == "conversation-deleted", \
            (name, status, got)
    for verb in ("restore", "archive", "unarchive", "trash"):
        status, got = change(world, c, verb)
        assert status in (409, 422), (verb, status, got)
    assert world["cv"].conversation_state(c) == "deleted"


def test_archive_never_refuses(world):
    c = world["c"]
    assert change(world, c, "archive")[0] == 200
    status, got = _req(world, "POST", "/fluid/api/posts",
                       {"author": world["me"], "conversation": c,
                        "parts": text("still writable")})
    assert status == 200, got


def test_restore_and_delete_are_the_acts_trash_allows(world):
    assert set(ER.TRASH_ALLOWS) == {
        "conversation-restored", "conversation-deleted", "delivery-failed",
        "execution-stop-asked", "operation-keyed"}
    assert set(ER.DELETED_ALLOWS) == {"operation-keyed"}


def test_a_run_s_result_cannot_write_into_trash(world):
    """Existing work's results: the run's reply and its result act are
    refused together; closing it (delivery-failed) is accepted."""
    cv, c, me = world["cv"], world["c"], world["me"]
    trash(world)
    nadia = world["who"]["@Nadia"]
    before = touching(world, c)
    with pytest.raises(ER.ConversationNotWritable):
        with world["corpus"].atomic():
            cv.say(c, nadia, text("a late result"))
            cv.record_act(actor=nadia, act="result-returned",
                          conversation=c, detail={"text": "late"})
    assert touching(world, c) == before
    cv.record_act(actor=nadia, act="delivery-failed", conversation=c,
                  detail={"why": "its conversation is in Trash"})


def test_the_sweep_every_post_route_writes_nothing_into_trash(world):
    """Every Fluid command verb and /api POST shape, and every worker
    operation that may write, asked with this conversation's ids: whatever
    each answers, nothing touching the conversation is written."""
    from mentis.fluid import commands as F
    c, me = world["c"], world["me"]
    p1 = world["posts"][0]
    token, parent, coach = _grant(world, c)
    _end_the_run(world, parent, coach)
    trash(world)
    base = {"author": me, "attributed_to": me, "conversation": c,
            "parts": text("x"), "text": "x", "name": "x", "replies_to": p1,
            "post": p1, "topic": world["topic"], "add": [world["away"]],
            "token": "+1", "why": "x", "by": me, "op": "sweep"}
    paths = ["/fluid/api/posts", "/fluid/api/requests"]
    paths += [f"/fluid/api/posts/{p1}/{v}" for v in F.POST_ACTS] + \
        [f"/fluid/api/posts/{p1}/address"]
    paths += [f"/fluid/api/conversations/{c}/{v}" for v in
              ("name", "members", "archive", "unarchive")]
    paths += [f"/api/conversations/{c}/{v}" for v in
              ("turns", "instructions", "participants", "topics")]
    paths += [f"/api/turns/{p1}/{v}" for v in
              ("address", "expect", "topics", "unfile", "move", "link",
               "unlink", "reactions", "deep-dives")]
    paths += [f"/api/turns/{world['away']}/link"]
    answered = {}
    for path in paths:
        before = touching(world, c)
        status, got = _req(world, "POST", path, dict(base))
        assert touching(world, c) == before, (path, status, got)
        answered[path] = (status, got)
    for name in sorted(set(OPERATIONS) - set(READ_ONLY)):
        before = touching(world, c)
        status, got = _op(world, token, name, **dict(base))
        assert touching(world, c) == before, (name, status, got)
        answered[name] = (status, got)
    # none of them was accepted: a 2xx here is an answer that wrote nothing
    # (a refusal said in the body, or nothing to do)
    ok = {k: v[1] for k, v in answered.items()
          if v[0] < 300 and not (isinstance(v[1], dict) and v[1].get("error"))}
    assert not ok, json.dumps(ok, indent=1, default=str)[:4000]
