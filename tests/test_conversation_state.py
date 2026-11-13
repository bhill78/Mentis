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
    assert after["state"] == "active" and after["state_at"] is None
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
