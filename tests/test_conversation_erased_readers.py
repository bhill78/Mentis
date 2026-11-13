"""Readers over a permanently deleted conversation (contract §5).

Every Python GET this server answers is asked before the deletion (so every
cache is warm) and again after it: none fails, none returns any of the
deleted content (seeded unique strings), an erased post reads as a deleted
placeholder and the conversation as "Deleted conversation", deleted
conversations are out of every list and search, and references to them
resolve to deleted.
"""
from __future__ import annotations

import json

import pytest

from mentis.spine import erasure as SE
from tests.test_conversation_erasure import (SEEDS, _req, delete, trash,
                                             world)  # noqa: F401


def _paths(world):
    c, other = world["c"], world["other"]
    p1, p2, p3 = world["posts"]
    away = world["away"]
    t = world["topic"]
    ids = ",".join([p1, p2, p3, away, world["o_shared"]])
    adm = world["files"]["x"][1]
    out = [
        f"/fluid/api/posts?ids={ids}", f"/fluid/api/posts?ids={ids}&thread=1",
        f"/fluid/api/conversations?ids={c},{other}",
        "/fluid/api/conversations?activity=1",
        "/fluid/api/conversations?activity=1&state=active",
        "/fluid/api/conversations?activity=1&state=archived",
        "/fluid/api/conversations?activity=1&state=trashed",
        "/fluid/api/conversations?state=deleted",
        f"/fluid/api/conversations?activity=1&q={SEEDS['renamed'][:8]}",
        f"/fluid/api/collections/conversation?id={c}",
        f"/fluid/api/collections/conversation?id={c}&shape=flat",
        f"/fluid/api/collections/conversation?id={other}",
        f"/fluid/api/collections/thread?root={p1}",
        "/fluid/api/collections/stream",
        f"/fluid/api/collections/selection?ids={p1},{away}",
        f"/fluid/api/search?conversation={c}&q={SEEDS['post'][:8]}",
        f"/fluid/api/search?conversation={other}&q=placed",
        "/fluid/api/changes?since=f1.0.0.0",
        f"/fluid/api/objects?conversation={c}",
        f"/fluid/api/objects?conversation={other}",
        f"/fluid/api/objects?post={p1}", f"/fluid/api/objects?posts={p1},{away}",
        f"/fluid/api/objects?thread={p1}",
        f"/fluid/api/objects/{p1}", f"/fluid/api/objects/{adm}",
        f"/fluid/api/object-refs?ids={p1},{c},{adm}",
        f"/fluid/api/document?ref={adm}",
        "/fluid/api/participants", "/fluid/api/names",
        f"/fluid/api/topics?conversation={c}", "/fluid/api/topics",
        "/fluid/api/governed", "/fluid/api/home/needs-you",
        "/fluid/api/home/work", "/fluid/api/home/activity",
        "/fluid/api/home/briefing", "/fluid/api/home/for-you",
        "/fluid/api/needs-you", "/fluid/api/needs-you/items",
        f"/fluid/api/posts/{p1}/anchors", f"/fluid/api/anchors?post={p1}",
        "/fluid/api/decisions", "/fluid/api/latest", "/fluid/api/work",
        "/fluid/api/runs",
        f"/fluid/api/conversations/{c}/tombstone",
        "/api/conversations", f"/api/conversations/{c}",
        f"/api/conversations/{c}/work", f"/api/conversations/{other}",
        f"/api/turns?conversation={c}", f"/api/turns/{p1}",
        f"/api/turns/{away}",
        f"/api/references?q={SEEDS['renamed'][:8]}",
        f"/api/references?q={SEEDS['post'][:8]}", f"/api/references?q={c}",
        f"/api/references?q={p1}", f"/api/entries/{p1}",
        f"/api/entries/{c}", f"/api/entries/{t}",
        f"/api/entries/{world['lesson']}", f"/api/history?entry={p1}",
        f"/api/provenance?entry={world['lesson']}",
        f"/api/neighborhood?entry={world['lesson']}",
        "/api/intake", "/api/owed", "/api/working", "/api/activity",
        "/api/work", "/api/participants", "/api/operational",
        f"/api/operational?conversation={c}", "/api/governed",
        f"/api/space?conversation={c}", f"/api/space/said?conversation={c}",
        f"/api/artifacts/{adm}?describe=1", "/api/pulse",
    ]
    return out


def _sweep(world):
    out = {}
    for path in _paths(world):
        status, got = _req(world, "GET", path)
        out[path] = (status, json.dumps(got, default=str))
    return out


def test_every_reader_after_deletion_fails_nothing_and_leaks_nothing(world):
    before = _sweep(world)                      # every cache warm
    errors_before = {p for p, (s, _) in before.items() if s >= 500}
    trash(world)
    delete(world)
    after = _sweep(world)
    broken = {p: v for p, v in after.items()
              if v[0] >= 500 and p not in errors_before}
    assert not broken, json.dumps(broken, indent=1)[:4000]
    leaks = {p: [s for s in SEEDS.values() if s in body]
             for p, (_, body) in after.items()}
    leaks = {p: v for p, v in leaks.items() if v}
    assert not leaks, leaks


def test_an_erased_post_reads_as_a_deleted_placeholder(world):
    trash(world)
    delete(world)
    p1 = world["posts"][0]
    status, got = _req(world, "GET", f"/fluid/api/posts?ids={p1}")
    assert status == 200, got
    post = got["posts"][0]
    assert post["deleted"] is True and post.get("erased") is True
    assert post["parts"] == []
    status, got = _req(world, "GET",
                       f"/fluid/api/conversations?ids={world['c']}")
    row = got["conversations"][0]
    assert row["name"] == "Deleted conversation" and row["state"] == "deleted"


def test_deleted_conversations_are_out_of_every_list_and_search(world):
    c = world["c"]
    trash(world)
    delete(world)
    for state in ("", "&state=active", "&state=archived", "&state=trashed"):
        status, got = _req(world, "GET",
                           f"/fluid/api/conversations?activity=1&limit=60"
                           + state)
        assert status == 200
        assert c not in [r["id"] for r in got["conversations"]], state
    status, got = _req(world, "GET", "/fluid/api/conversations?state=deleted")
    tomb = [r for r in got["conversations"] if r["id"] == c]
    assert tomb and "name" not in tomb[0] or \
        tomb[0]["name"] == "Deleted conversation"
    assert tomb[0]["deleted_by"] == world["me"]
    status, got = _req(world, "GET", "/api/conversations")
    listed = got if isinstance(got, list) else got.get("conversations", [])
    assert c not in [r.get("id") for r in listed]
    status, got = _req(world, "GET", f"/api/references?q={c}")
    assert SEEDS["renamed"] not in json.dumps(got)


def test_the_tombstone_names_what_survives_and_no_content(world):
    trash(world)
    delete(world)
    status, got = _req(world, "GET",
                       f"/fluid/api/conversations/{world['c']}/tombstone")
    assert status == 200, got
    kept = {r["id"] for r in got["surviving_records"]}
    assert {world["lesson"], world["rule"], world["outcome"]} <= kept
    assert got["name"] == "Deleted conversation"
    assert not any(s in json.dumps(got) for s in SEEDS.values())


def test_impact_needs_trash_and_delete_is_the_owner_s(world):
    from mentis.worker import CAPABILITY_HEADER
    c = world["c"]
    status, got = _req(world, "GET",
                       f"/fluid/api/conversations/{c}/deletion-impact")
    assert status == 409 and got["code"] == "not-in-trash"
    trash(world)
    status, imp = _req(world, "GET",
                       f"/fluid/api/conversations/{c}/deletion-impact")
    assert status == 200
    # not the owner
    status, got = _req(world, "POST", f"/fluid/api/conversations/{c}/delete",
                       {"author": world["who"]["@Vera"],
                        "token": imp["token"]})
    assert status == 403, got
    # a worker grant never reaches the Fluid door
    status, got = _req(world, "POST", f"/fluid/api/conversations/{c}/delete",
                       {"author": world["me"], "token": imp["token"]},
                       headers={CAPABILITY_HEADER: "x"})
    assert status == 403
    # a stale token
    status, got = _req(world, "POST", f"/fluid/api/conversations/{c}/delete",
                       {"author": world["me"], "token": "0" * 64})
    assert status == 409 and got["code"] == "impact-changed"
    assert world["cv"].conversation_state(c) == "trashed"
    status, got = _req(world, "POST", f"/fluid/api/conversations/{c}/delete",
                       {"author": world["me"], "token": imp["token"]})
    assert status == 200 and got["deleted"]
    # the retry answers what it did
    status, again = _req(world, "POST",
                         f"/fluid/api/conversations/{c}/delete",
                         {"author": world["me"], "token": imp["token"]})
    assert status == 200 and again["replayed"]


def test_deletion_is_refused_while_work_is_in_flight(world):
    cv, c, me = world["cv"], world["c"], world["me"]
    trash(world)
    status, imp = _req(world, "GET",
                       f"/fluid/api/conversations/{c}/deletion-impact")
    # work appears under it (a question to the owner, recorded by hand: the
    # guard lets nothing new in, so it is written beside it as a record)
    from mentis.conversation import erasure as ER
    g = ER.install(world["corpus"])
    g.erasing.on = True
    try:
        cv.record_act(actor=world["who"]["@Nadia"],
                      act="expectation-recorded", conversation=c,
                      turn=world["posts"][0],
                      detail={"expected_of": me, "work": "answer me"})
    finally:
        g.erasing.on = False
    status, got = _req(world, "POST", f"/fluid/api/conversations/{c}/delete",
                       {"author": me, "token": imp["token"]})
    assert status in (409, 422) and got["code"] in ("work-in-flight",
                                                   "impact-changed"), got
    assert cv.conversation_state(c) == "trashed"
    assert not world["corpus"]._store._conn.execute(
        "SELECT 1 FROM erasure").fetchone()
