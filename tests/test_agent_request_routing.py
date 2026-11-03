"""Where an agent request goes (`mentis.fluid.commands.agent_request`), and so its
result. The owner's rule is Turn ent-663461b42e8b: a workspace has its own
Conversation, created when first needed; inside a Magnet, the Magnet's; inside a
Conversation, that one; a chosen destination overrides the workspace's; and no
Magnet is ever inferred as primary."""
from __future__ import annotations

import itertools
import json
import pathlib
import threading
import time
import urllib.error
import urllib.request

import pytest

import mentis.magnet as M
import mentis.web as web
from mentis.fluid import arrangements as A
from mentis.fluid import commands
from mentis.fluid import workspace_manifest as wm
from mentis.web import dispatch as D
from mentis.web import _State
from mentis.worker import CAPABILITY_HEADER, OPERATIONS
from tests._loop import a_conversation, rt, world  # noqa: F401


_ops = itertools.count(1)


def post(world, body, path="requests", headers=None):  # noqa: F811
    req = urllib.request.Request(
        world["base"] + "/fluid/api/" + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1",
                 **(headers or {})},
        method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def ask(world, origin, text="Make a report from this", **more):  # noqa: F811
    agent = world.setdefault("agent", world["cv"].create_participant("@Scribe"))
    return post(world, {"from": origin, "author": world["who"]["@brian"],
                        "text": text, "action": "ask-participant",
                        "addressed_to": [agent],
                        "dispatch": [{"participant": agent, "work": text}],
                        "op": f"ask-{next(_ops)}", **more})


def conversations(world):  # noqa: F811
    return {c["id"] for c in world["cv"].all_conversations()}


def home_of(world, turn):  # noqa: F811
    return world["cv"].conversation_of(turn)


def posts_in(world, cid):  # noqa: F811
    return [t["turn"] for t in world["cv"].turns(cid)]


def magnet_object(mid):
    return {"kind": "magnet", "ref": mid, "provenance": {
        "source": {"kind": "participant", "ref": "ent-owner"}}}


def a_workspace(world, *objects, name="Evidence"):  # noqa: F811
    return wm.create(world["root"], {"name": name,
                                     "objects": list(objects)})["id"]


def a_magnet(world):  # noqa: F811
    status, got = post(world, {
        "seed": {"sources": [{"kind": "conversation", "conversation": "ent-src"}],
                 "selection": {}, "collection": {"mode": "one-time"},
                 "synthesis": {"mode": "manual"},
                 "notifications": {"newItems": False, "changes": False,
                                   "failures": False},
                 "presentation": {"renderer": "disc"}},
        "attach": {"zone": {"type": "zone", "show": "magnet", "name": "Board"},
                   "base": {"format": A.FORMAT, "version": 2,
                            "tree": {"type": "zone", "id": "stage",
                                     "show": "objects"}}}},
        path="arrangements/home/magnets")
    assert status == 200, got
    return got["magnet"]["id"]


def own_conversation_of(world, mid):  # noqa: F811
    status, got = post(world, {"author": world["who"]["@brian"]},
                       path=f"magnets/{mid}/conversation")
    assert status in (200, 201), got
    return got["conversation"]


# -- a workspace's own Conversation -------------------------------------------

def test_a_workspace_request_creates_its_conversation_and_goes_there(world):  # noqa: F811
    wid = a_workspace(world)
    before = conversations(world)
    status, got = ask(world, {"workspace": wid})
    assert status == 200, got
    cid = got["route"]["conversation"]
    assert got["route"] == {"rule": "workspace", "conversation": cid,
                            "created": True}
    assert conversations(world) - before == {cid}
    assert got["home"] == cid and home_of(world, got["post"]) == cid
    assert got["home_name"] == "Evidence", "named as the workspace is"
    assert wm.workspace(world["root"], wid)["manifest"]["conversation"] == cid
    assert [s["conversation"] for s in world["sent"]] == [cid]


def test_later_workspace_requests_use_the_same_conversation(world):  # noqa: F811
    wid = a_workspace(world)
    _, first = ask(world, {"workspace": wid})
    cid = first["route"]["conversation"]
    known = conversations(world)
    status, again = ask(world, {"workspace": wid}, text="And another")
    assert status == 200
    assert again["route"] == {"rule": "workspace", "conversation": cid,
                              "created": False}
    assert conversations(world) == known
    assert posts_in(world, cid) == [first["post"], again["post"]]


def test_an_unnamed_workspace_gets_a_provisional_name(world):  # noqa: F811
    status, got = ask(world, {"workspace": a_workspace(world, name="")})
    assert status == 200 and got["home_name"].startswith("Unnamed")


def test_each_workspace_has_its_own_conversation(world):  # noqa: F811
    _, one = ask(world, {"workspace": a_workspace(world)})
    _, two = ask(world, {"workspace": a_workspace(world)})
    assert one["route"]["conversation"] != two["route"]["conversation"]


def test_nothing_but_a_request_creates_one(world):  # noqa: F811
    before = conversations(world)
    mid = a_magnet(world)
    wid = a_workspace(world, magnet_object(mid))
    root = world["root"]
    wm.rename(root, wid, {"name": "Renamed"})
    wm.add_object(root, wid, {"object": magnet_object("mag-other")})
    wm.workspace(root, wid)
    wm.workspaces(root)
    wm.curated_references(wm.workspace(root, wid)["manifest"])
    assert conversations(world) == before
    assert "conversation" not in wm.workspace(root, wid)["manifest"]
    assert M.read(root, mid).get("conversation") is None


# -- multi-Magnet and Magnet-free ---------------------------------------------

def test_a_workspace_of_several_magnets_never_uses_one_of_theirs(world):  # noqa: F811
    with_own = a_magnet(world), a_magnet(world)
    own = {own_conversation_of(world, m) for m in with_own}
    without = a_magnet(world)
    wid = a_workspace(world, *[magnet_object(m) for m in (*with_own, without)])
    status, got = ask(world, {"workspace": wid})
    assert status == 200, got
    assert got["route"]["rule"] == "workspace" and got["route"]["created"]
    assert got["route"]["conversation"] not in own
    assert all(not posts_in(world, c) for c in own)
    assert M.read(world["root"], without).get("conversation") is None, \
        "a workspace's request creates nothing for a Magnet it holds"


def test_a_workspace_of_one_magnet_does_not_treat_it_as_primary(world):  # noqa: F811
    mid = a_magnet(world)
    own = own_conversation_of(world, mid)
    _, got = ask(world, {"workspace": a_workspace(world, magnet_object(mid))})
    assert got["route"]["conversation"] != own


def test_a_blank_workspace_routes_the_same(world):  # noqa: F811
    wid = a_workspace(world)
    assert wm.workspace(world["root"], wid)["manifest"]["objects"] == []
    status, got = ask(world, {"workspace": wid})
    assert status == 200 and got["route"]["created"]


def test_routing_reads_nothing_of_what_a_workspace_holds(world, monkeypatch):  # noqa: F811
    mid = a_magnet(world)
    wid = a_workspace(world, magnet_object(mid))
    monkeypatch.setattr(M, "read", lambda *_: pytest.fail("read a Magnet"))
    status, got = ask(world, {"workspace": wid})
    assert status == 200 and got["route"]["rule"] == "workspace", got


# -- inside a Magnet, inside a Conversation -----------------------------------

def test_inside_a_magnet_goes_to_its_conversation(world):  # noqa: F811
    mid = a_magnet(world)
    own = own_conversation_of(world, mid)
    known = conversations(world)
    status, got = ask(world, {"magnet": mid})
    assert status == 200, got
    assert got["route"] == {"rule": "magnet", "conversation": own,
                            "created": False}
    assert home_of(world, got["post"]) == own and conversations(world) == known
    assert [s["conversation"] for s in world["sent"]] == [own]


def test_inside_a_magnet_with_none_creates_its_one(world):  # noqa: F811
    mid = a_magnet(world)
    before = conversations(world)
    status, got = ask(world, {"magnet": mid})
    assert status == 200, got
    cid = got["route"]["conversation"]
    assert got["route"]["created"] and conversations(world) - before == {cid}
    assert M.read(world["root"], mid)["conversation"] == cid
    assert own_conversation_of(world, mid) == cid, "its own door answers the same"
    _, again = ask(world, {"magnet": mid})
    assert again["route"] == {"rule": "magnet", "conversation": cid,
                              "created": False}


def test_a_magnet_in_a_workspace_still_uses_its_own_inside_it(world):  # noqa: F811
    mid = a_magnet(world)
    wid = a_workspace(world, magnet_object(mid))
    _, inside = ask(world, {"magnet": mid})
    _, level = ask(world, {"workspace": wid})
    assert inside["route"]["conversation"] != level["route"]["conversation"]
    assert "conversation" in wm.workspace(world["root"], wid)["manifest"]


def test_an_absent_magnet_is_refused(world):  # noqa: F811
    before = conversations(world)
    status, got = ask(world, {"magnet": "mag-none"})
    assert status == 422 and got["reason"]["code"] == "state"
    assert conversations(world) == before


def test_inside_a_conversation_stays_there(world):  # noqa: F811
    cid = a_conversation(world)
    known = conversations(world)
    status, got = ask(world, {"conversation": cid})
    assert status == 200, got
    assert got["route"] == {"rule": "conversation", "conversation": cid,
                            "created": False}
    assert home_of(world, got["post"]) == cid and conversations(world) == known


def test_an_ordinary_post_is_answered_as_it_was(world):  # noqa: F811
    cid = a_conversation(world)
    status, got = post(world, {"conversation": cid, "text": "Hello",
                               "author": world["who"]["@brian"]}, path="posts")
    assert status == 200 and got["home"] == cid and "route" not in got


# -- a chosen destination -----------------------------------------------------

def test_a_destination_overrides_the_workspace_and_creates_nothing(world):  # noqa: F811
    wid = a_workspace(world)
    cid = a_conversation(world)
    known = conversations(world)
    status, got = ask(world, {"workspace": wid}, destination={"conversation": cid})
    assert status == 200, got
    assert got["route"] == {"rule": "destination", "conversation": cid,
                            "created": False}
    assert home_of(world, got["post"]) == cid and conversations(world) == known
    assert "conversation" not in wm.workspace(world["root"], wid)["manifest"]
    assert [s["conversation"] for s in world["sent"]] == [cid]


def test_a_destination_leaves_the_default_for_the_next_request(world):  # noqa: F811
    wid = a_workspace(world)
    cid = a_conversation(world)
    _, made = ask(world, {"workspace": wid})
    own = made["route"]["conversation"]
    _, chosen = ask(world, {"workspace": wid}, destination={"conversation": cid})
    _, after = ask(world, {"workspace": wid})
    assert chosen["route"]["conversation"] == cid
    assert after["route"] == {"rule": "workspace", "conversation": own,
                              "created": False}


def test_a_destination_can_be_a_magnet(world):  # noqa: F811
    mid = a_magnet(world)
    wid = a_workspace(world, magnet_object(mid), magnet_object(a_magnet(world)))
    status, got = ask(world, {"workspace": wid}, destination={"magnet": mid})
    assert status == 200, got
    assert got["route"]["rule"] == "destination" and got["route"]["created"]
    assert M.read(world["root"], mid)["conversation"] == got["route"]["conversation"]
    assert "conversation" not in wm.workspace(world["root"], wid)["manifest"]


def test_a_destination_the_record_does_not_hold_is_refused(world):  # noqa: F811
    wid = a_workspace(world)
    before = conversations(world)
    status, got = ask(world, {"workspace": wid},
                      destination={"conversation": "ent-absent"})
    assert status == 400 and got["conversation"] == "ent-absent"
    assert conversations(world) == before
    assert "conversation" not in wm.workspace(world["root"], wid)["manifest"]


@pytest.mark.parametrize("origin", [{"magnet": "mag-x"}, {"conversation": "ent-x"}])
def test_only_a_workspace_request_names_a_destination(world, origin):  # noqa: F811
    status, got = ask(world, origin, destination={"conversation": "ent-y"})
    assert status == 400 and "destination" in got["error"]


# -- what is not a request ----------------------------------------------------

@pytest.mark.parametrize("origin", [
    None, "wsp-a", {}, {"workspace": ""}, {"workspace": 7},
    {"workspace": "wsp-a", "magnet": "mag-a"}, {"workspace-of": "wsp-a"},
    {"participant": "ent-a"}])
def test_from_must_name_one_place(world, origin):  # noqa: F811
    before = conversations(world)
    status, got = ask(world, origin)
    assert status == 400 and "from" in got["error"]
    assert conversations(world) == before


@pytest.mark.parametrize("destination", [
    "ent-a", {}, {"workspace": "wsp-a"}, {"conversation": ""},
    {"conversation": "ent-a", "magnet": "mag-a"}])
def test_a_destination_must_name_one_conversation_or_magnet(world, destination):  # noqa: F811
    status, got = ask(world, {"workspace": a_workspace(world)},
                      destination=destination)
    assert status == 400 and "destination" in got["error"]


def test_conversation_in_the_body_is_refused_not_read(world):  # noqa: F811
    wid = a_workspace(world)
    status, got = ask(world, {"workspace": wid},
                      conversation=a_conversation(world))
    assert status == 400 and "conversation" in got["error"]
    assert "conversation" not in wm.workspace(world["root"], wid)["manifest"]


def test_workspaces_that_cannot_be_used_are_said(world):  # noqa: F811
    root = world["root"]
    cid = a_conversation(world)
    before = conversations(world)
    for dest in ({}, {"destination": {"conversation": cid}}):
        status, got = ask(world, {"workspace": "wsp-absent"}, **dest)
        assert status == 404 and got["kind"] == "NotFound"

        gone = a_workspace(world)
        wm.delete(root, gone)
        status, got = ask(world, {"workspace": gone}, **dest)
        assert status == 410 and got["kind"] == "Gone"

        broken = a_workspace(world)
        path = pathlib.Path(root, "presentation", wm.FOLDER, f"{broken}.json")
        path.write_text("{", encoding="utf-8")
        status, got = ask(world, {"workspace": broken}, **dest)
        assert status == 409 and got["kind"] == "Unreadable"
        assert path.read_text(encoding="utf-8") == "{"

        status, got = ask(world, {"workspace": "../evil"}, **dest)
        assert status == 400
    assert conversations(world) == before and not world["sent"]


# -- a request refused or failed leaves nothing -------------------------------

def test_a_refused_request_creates_no_conversation(world):  # noqa: F811
    wid = a_workspace(world)
    mid = a_magnet(world)
    before = conversations(world)
    for origin in ({"workspace": wid}, {"magnet": mid}):
        status, got = post(world, {"from": origin, "text": "Do it",
                                   "author": world["who"]["@brian"],
                                   "action": "not-an-action",
                                   "op": f"refused-{origin}"})
        assert status == 422 and got["refused"] is True, got
    assert conversations(world) == before and not world["sent"]
    assert "conversation" not in wm.workspace(world["root"], wid)["manifest"]
    assert M.read(world["root"], mid).get("conversation") is None
    status, got = ask(world, {"workspace": wid})
    assert status == 200 and got["route"]["created"], "the first real one still makes it"


def test_no_author_creates_no_conversation(world):  # noqa: F811
    wid = a_workspace(world)
    before = conversations(world)
    status, got = post(world, {"from": {"workspace": wid}, "text": "Do it"})
    assert status == 400 and "author" in got["error"]
    status, got = post(world, {"from": {"workspace": wid}, "text": "Do it",
                               "author": "ent-nobody"})
    assert status == 422
    assert conversations(world) == before


def test_a_request_without_a_key_is_refused_and_creates_nothing(world):  # noqa: F811
    wid = a_workspace(world)
    before = conversations(world)
    for op in ({}, {"op": ""}, {"op": "  "}, {"op": 7}):
        body = {"from": {"workspace": wid}, "text": "Do it",
                "author": world["who"]["@brian"], **op}
        status, got = post(world, body)
        assert status == 400 and "op" in got["error"], got
    assert conversations(world) == before and not world["sent"]


def _magnet_key(mid):
    return {"op": f"magnet-conversation:{mid}"}, {
        "route": "fluid-magnet-conversation", "magnet": mid}


def test_the_magnet_route_commits_its_key_and_claim_as_one(
        world, monkeypatch):  # noqa: F811
    mid = a_magnet(world)
    author = {"author": world["who"]["@brian"]}
    before = conversations(world)
    real = commands._claim

    def fail(*_):
        raise PermissionError(13, "the process ended here")

    monkeypatch.setattr(commands, "_claim", fail)
    status, _ = post(world, author, path=f"magnets/{mid}/conversation")
    assert status == 500
    assert conversations(world) == before, "the Conversation went with the claim"
    monkeypatch.setattr(commands, "_claim", real)
    status, got = post(world, author, path=f"magnets/{mid}/conversation")
    assert status == 201 and got["created"] is True, got
    assert _claims(world["state"], "magnet", mid) == [got["conversation"]]
    key = [a for a in world["state"].corpus.operational(act="operation-keyed")
           if (a.get("detail") or {}).get("op") == f"magnet-conversation:{mid}"]
    assert len(key) == 1 and key[0]["detail"]["result"]["conversation"] == (
        got["conversation"])


def test_a_magnet_key_from_before_claims_is_claimed_not_repeated(world):  # noqa: F811
    mid = a_magnet(world)
    by = world["who"]["@brian"]
    key, request = _magnet_key(mid)
    status, opened, _ = commands.open_conversation(
        world["state"], {"author": by, **key}, written_by=lambda: "test",
        operation_request=request, operation_across_actors=True)
    assert status == 201, opened
    assert _claims(world["state"], "magnet", mid) == []
    known = conversations(world)

    status, got = post(world, {"author": by}, path=f"magnets/{mid}/conversation")
    assert status == 200 and got["created"] is True, got
    assert got["conversation"] == opened["conversation"]
    assert conversations(world) == known
    assert _claims(world["state"], "magnet", mid) == [opened["conversation"]]
    assert _file_of(world, "magnet", mid) == opened["conversation"]


def _a_magnet_key_from_before_claims(world, by):  # noqa: F811
    """What main left: an outcome under the key, no claim, nothing in the file."""
    mid = a_magnet(world)
    key, request = _magnet_key(mid)
    status, opened, _ = commands.open_conversation(
        world["state"], {"author": by, **key}, written_by=lambda: "test",
        operation_request=request, operation_across_actors=True)
    assert status == 201, opened
    assert _claims(world["state"], "magnet", mid) == []
    assert _file_of(world, "magnet", mid) is None
    return mid, opened["conversation"]


@pytest.mark.parametrize("opener", ["the requester", "somebody else"])
def test_a_request_recovers_a_magnet_key_from_before_claims(world, opener):  # noqa: F811
    by = (world["who"]["@brian"] if opener == "the requester"
          else world["cv"].create_participant("@Earlier"))
    mid, cid = _a_magnet_key_from_before_claims(world, by)
    known = conversations(world)

    status, got = ask(world, {"magnet": mid})

    assert status == 200, got
    assert got["route"] == {"rule": "magnet", "conversation": cid,
                            "created": False}, "it was found, not created"
    assert home_of(world, got["post"]) == cid
    assert [s["conversation"] for s in world["sent"]] == [cid]
    assert conversations(world) == known, "no second Conversation"
    assert _claims(world["state"], "magnet", mid) == [cid]
    assert _file_of(world, "magnet", mid) == cid

    status, again = ask(world, {"magnet": mid}, text="Another")
    assert status == 200 and again["route"]["conversation"] == cid, again
    status, direct = post(world, {"author": world["who"]["@brian"]},
                          path=f"magnets/{mid}/conversation")
    assert status == 200 and direct["created"] is False, direct
    assert direct["conversation"] == cid
    assert conversations(world) == known
    assert _claims(world["state"], "magnet", mid) == [cid]


def test_a_destination_magnet_recovers_its_key_from_before_claims(world):  # noqa: F811
    mid, cid = _a_magnet_key_from_before_claims(world, world["who"]["@brian"])
    wid = a_workspace(world)
    known = conversations(world)
    status, got = ask(world, {"workspace": wid}, destination={"magnet": mid})
    assert status == 200, got
    assert got["route"] == {"rule": "destination", "conversation": cid,
                            "created": False}
    assert conversations(world) == known
    assert _claims(world["state"], "magnet", mid) == [cid]


def test_a_refused_request_leaves_a_magnet_key_from_before_claims_unclaimed(world):  # noqa: F811
    mid, cid = _a_magnet_key_from_before_claims(world, world["who"]["@brian"])
    known = conversations(world)
    status, got = ask(world, {"magnet": mid}, action="no-such-action")
    assert status >= 400, got
    assert conversations(world) == known
    assert _claims(world["state"], "magnet", mid) == [], "undone with the request"
    assert _file_of(world, "magnet", mid) is None
    status, got = ask(world, {"magnet": mid})
    assert status == 200 and got["route"]["conversation"] == cid, got
    assert _claims(world["state"], "magnet", mid) == [cid]


def test_a_failed_request_commits_no_claim_of_an_older_magnet_key(
        world, monkeypatch):  # noqa: F811
    mid, cid = _a_magnet_key_from_before_claims(world, world["who"]["@brian"])
    real = commands.write_post

    def fail(*_, **__):
        raise PermissionError(13, "the process ended here")

    monkeypatch.setattr(commands, "write_post", fail)
    status, _ = ask(world, {"magnet": mid})
    assert status == 500
    assert _claims(world["state"], "magnet", mid) == []
    monkeypatch.setattr(commands, "write_post", real)
    status, got = ask(world, {"magnet": mid})
    assert status == 200 and got["route"]["conversation"] == cid, got
    assert _claims(world["state"], "magnet", mid) == [cid]


def test_a_new_magnets_first_request_records_its_key_with_its_claim(world):  # noqa: F811
    mid = a_magnet(world)
    status, got = ask(world, {"magnet": mid})
    assert status == 200 and got["route"]["created"] is True, got
    cid = got["route"]["conversation"]
    assert _claims(world["state"], "magnet", mid) == [cid]
    keyed = [a for a in world["state"].corpus.operational(act="operation-keyed")
             if (a.get("detail") or {}).get("op") == f"magnet-conversation:{mid}"]
    assert len(keyed) == 1 and keyed[0]["detail"]["result"]["conversation"] == cid


def test_a_shared_keys_unrelated_act_is_not_a_magnets_conversation(world):  # noqa: F811
    mid = a_magnet(world)
    by = world["who"]["@brian"]
    elsewhere = a_conversation(world)
    status, _ = post(world, {"author": by, "conversation": elsewhere,
                             "text": "squat", "action": "record-only",
                             "op": f"magnet-conversation:{mid}"}, path="posts")
    assert status == 200
    known = conversations(world)
    status, got = ask(world, {"magnet": mid})
    assert status == 200 and got["route"]["created"] is True, got
    assert got["route"]["conversation"] != elsewhere
    assert conversations(world) - known == {got["route"]["conversation"]}


def test_the_magnet_route_ignores_a_clients_key_and_a_request_shares_its_claim(
        world):  # noqa: F811
    mid = a_magnet(world)
    by = world["who"]["@brian"]
    status, opened = post(world, {"author": by, "op": "the-clients-own"},
                          path=f"magnets/{mid}/conversation")
    assert status == 201, opened
    keys = {(a.get("detail") or {}).get("op")
            for a in world["state"].corpus.operational(act="operation-keyed")}
    assert f"magnet-conversation:{mid}" in keys and "the-clients-own" not in keys
    code, asked = ask(world, {"magnet": mid})
    assert code == 200 and not asked["route"]["created"], asked
    assert asked["route"]["conversation"] == opened["conversation"]
    assert _claims(world["state"], "magnet", mid) == [opened["conversation"]]


@pytest.mark.parametrize("failure", [
    PermissionError(13, "destination is open"),
    wm.Refused("the workspace would be larger than it can be")])
def test_a_file_that_cannot_be_written_refuses_nothing_and_catches_up(
        world, monkeypatch, failure):  # noqa: F811
    wid = a_workspace(world)
    real = wm.set_conversation
    attempted = []

    def fail_first(root, asked, cid):
        attempted.append(cid)
        if len(attempted) == 1:
            raise failure
        return real(root, asked, cid)

    monkeypatch.setattr(wm, "set_conversation", fail_first)
    code, got = ask(world, {"workspace": wid}, op="one-request")
    assert code == 200 and got["route"]["created"], got
    cid = got["route"]["conversation"]
    assert posts_in(world, cid) == [got["post"]] and len(world["sent"]) == 1
    assert "conversation" not in wm.workspace(world["root"], wid)["manifest"]

    known = conversations(world)
    code, again = ask(world, {"workspace": wid}, text="Another")
    assert code == 200, again
    assert again["route"] == {"rule": "workspace", "conversation": cid,
                              "created": False}
    assert conversations(world) == known, "the record's claim answered"
    assert wm.workspace(world["root"], wid)["manifest"]["conversation"] == cid


def test_a_manifest_naming_what_the_record_lacks_is_corrected(world):  # noqa: F811
    wid = a_workspace(world)
    wm.set_conversation(world["root"], wid, "ent-lost")
    before = conversations(world)
    status, got = ask(world, {"workspace": wid})
    assert status == 200 and got["route"]["created"], got
    cid = got["route"]["conversation"]
    assert conversations(world) - before == {cid}
    assert wm.workspace(world["root"], wid)["manifest"]["conversation"] == cid


def test_a_manifest_naming_what_the_record_lacks_gives_way_to_the_claim(world):  # noqa: F811
    wid = a_workspace(world)
    _, got = ask(world, {"workspace": wid})
    cid = got["route"]["conversation"]
    wm.set_conversation(world["root"], wid, "ent-lost")
    known = conversations(world)
    status, again = ask(world, {"workspace": wid}, text="Another")
    assert status == 200, again
    assert again["route"] == {"rule": "workspace", "conversation": cid,
                              "created": False}
    assert conversations(world) == known
    assert wm.workspace(world["root"], wid)["manifest"]["conversation"] == cid


# -- the claim decides, whatever the file names -------------------------------

def _file_says(world, kind, ref, cid):  # noqa: F811
    """A copy gone stale, as nothing at this door would write it. `cid` None: no copy."""
    root = world["root"]
    if kind == "workspace":
        path = wm._path(root, ref)
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("conversation", None)
        path.write_text(json.dumps({**data, **({"conversation": cid} if cid else {})}),
                        encoding="utf-8")
    else:
        config = {k: v for k, v in M.read(root, ref).items() if k != "conversation"}
        M.write(root, ref, {**config, **({"conversation": cid} if cid else {})})


def _file_of(world, kind, ref):  # noqa: F811
    if kind == "workspace":
        return wm.workspace(world["root"], ref)["manifest"].get("conversation")
    return M.read(world["root"], ref).get("conversation")


def _claims(state, kind, ref):
    return [a["conversation"] for a in state.corpus.operational(
        act=commands.CONVERSATION_CLAIMED, detail_is={kind: ref})]


def _owned(world, kind):  # noqa: F811
    ref = a_workspace(world) if kind == "workspace" else a_magnet(world)
    status, got = ask(world, {kind: ref})
    assert status == 200 and got["route"]["created"], got
    return ref, got["route"]["conversation"]


#: What the file might say instead: `other` is a real Conversation, which a
#: file-first read cannot tell from the right one.
STALE = ["other", "ent-lost", None]


def _stale(world, how):  # noqa: F811
    return a_conversation(world) if how == "other" else how


@pytest.mark.parametrize("how", STALE)
@pytest.mark.parametrize("kind", ["workspace", "magnet"])
def test_a_request_goes_to_the_claim_and_the_file_is_corrected(world, kind, how):  # noqa: F811
    ref, cid = _owned(world, kind)
    stale = _stale(world, how)
    _file_says(world, kind, ref, stale)
    known, sent = conversations(world), len(world["sent"])

    status, got = ask(world, {kind: ref}, text="Another")

    assert status == 200, got
    assert got["route"] == {"rule": kind, "conversation": cid, "created": False}
    assert home_of(world, got["post"]) == cid
    assert [s["conversation"] for s in world["sent"][sent:]] == [cid]
    assert _file_of(world, kind, ref) == cid, "the file follows"
    assert _claims(world["state"], kind, ref) == [cid], "the claim did not move"
    assert conversations(world) == known, "no second Conversation"
    if how == "other":
        assert posts_in(world, stale) == [], "nothing went where the file said"


@pytest.mark.parametrize("how", STALE)
def test_a_destination_magnet_goes_to_its_claim(world, how):  # noqa: F811
    mid, cid = _owned(world, "magnet")
    wid = a_workspace(world)
    _file_says(world, "magnet", mid, _stale(world, how))
    status, got = ask(world, {"workspace": wid}, destination={"magnet": mid})
    assert status == 200, got
    assert got["route"] == {"rule": "destination", "conversation": cid,
                            "created": False}
    assert _file_of(world, "magnet", mid) == cid
    assert "conversation" not in wm.workspace(world["root"], wid)["manifest"]


@pytest.mark.parametrize("how", STALE)
@pytest.mark.parametrize("kind", ["workspace", "magnet"])
def test_the_claim_decides_after_a_reopened_server(world, kind, how):  # noqa: F811
    ref, cid = _owned(world, kind)
    stale = _stale(world, how)
    _file_says(world, kind, ref, stale)

    def from_a_new_server(op):
        again = _State(world["root"])
        status, got, _ = commands.agent_request(
            again, {"from": {kind: ref}, "text": "Back again",
                    "author": world["who"]["@brian"], "op": op},
            written_by=lambda: web._observed_writer(again, None))
        assert status == 200, got
        assert got["route"] == {"rule": kind, "conversation": cid, "created": False}
        assert _claims(again, kind, ref) == [cid]
        assert _file_of(world, kind, ref) == cid, "corrected on disk"

    from_a_new_server("back-once")
    from_a_new_server("back-twice")
    if how == "other":
        assert posts_in(world, stale) == []


@pytest.mark.parametrize("how", STALE)
def test_the_magnets_own_door_answers_the_claim_and_corrects_the_file(world, how):  # noqa: F811
    mid, cid = _owned(world, "magnet")
    stale = _stale(world, how)
    _file_says(world, "magnet", mid, stale)
    known = conversations(world)

    def asked():
        status, got = post(world, {"author": world["who"]["@brian"]},
                           path=f"magnets/{mid}/conversation")
        assert (status, got) == (200, {"magnet": mid, "created": False,
                                       "conversation": cid})
        assert _file_of(world, "magnet", mid) == cid

    asked()
    asked()
    assert conversations(world) == known
    assert _claims(world["state"], "magnet", mid) == [cid]

    _file_says(world, "magnet", mid, stale)
    again = _State(world["root"])
    status, got, _ = commands.magnet_definition_command(
        again, "magnet-conversation", mid, {"author": world["who"]["@brian"]},
        written_by=lambda: web._observed_writer(again, None))
    assert (status, got) == (200, {"magnet": mid, "created": False,
                                   "conversation": cid})
    assert _file_of(world, "magnet", mid) == cid


def test_the_magnets_own_door_answers_the_claim_it_cannot_write(world, monkeypatch):  # noqa: F811
    mid, cid = _owned(world, "magnet")
    stale = a_conversation(world)
    _file_says(world, "magnet", mid, stale)

    def cannot(*_):
        raise PermissionError(13, "destination is open")

    monkeypatch.setattr(M, "correct_conversation", cannot)
    status, got = post(world, {"author": world["who"]["@brian"]},
                       path=f"magnets/{mid}/conversation")
    assert (status, got["conversation"]) == (200, cid)
    assert _file_of(world, "magnet", mid) == stale


@pytest.mark.parametrize("kind", ["workspace", "magnet"])
def test_a_file_that_cannot_be_corrected_refuses_nothing_and_catches_up(
        world, monkeypatch, kind):  # noqa: F811
    ref, cid = _owned(world, kind)
    stale = a_conversation(world)
    _file_says(world, kind, ref, stale)
    module, name = ((wm, "set_conversation") if kind == "workspace"
                    else (M, "correct_conversation"))
    real, failed = getattr(module, name), []

    def fail_first(*args):
        if not failed:
            failed.append(args)
            raise PermissionError(13, "destination is open")
        return real(*args)

    monkeypatch.setattr(module, name, fail_first)
    status, got = ask(world, {kind: ref}, text="While it is open")
    assert status == 200 and got["route"]["conversation"] == cid, got
    assert failed and _file_of(world, kind, ref) == stale

    status, got = ask(world, {kind: ref}, text="After")
    assert status == 200 and got["route"]["conversation"] == cid, got
    assert _file_of(world, kind, ref) == cid
    assert posts_in(world, stale) == []


@pytest.mark.parametrize("kind", ["workspace", "magnet"])
def test_a_retry_corrects_the_file_from_the_claim(world, kind):  # noqa: F811
    ref = a_workspace(world) if kind == "workspace" else a_magnet(world)
    _, first = ask(world, {kind: ref}, op="same")
    cid = first["route"]["conversation"]
    stale = a_conversation(world)
    _file_says(world, kind, ref, stale)
    status, again = ask(world, {kind: ref}, op="same")
    assert status == 200 and again["replayed"] and again["post"] == first["post"]
    assert again["route"]["conversation"] == cid
    assert _file_of(world, kind, ref) == cid
    assert len(world["sent"]) == 1


def test_a_retry_answers_where_it_went_but_the_file_says_the_claim(world):  # noqa: F811
    """Sent where an unclaimed file said, and claimed elsewhere since: the answer is
    where the request went, and the file is still the claim's."""
    mid = a_magnet(world)
    unclaimed = a_conversation(world)
    M.set_conversation(world["root"], mid, unclaimed)
    _, first = ask(world, {"magnet": mid}, op="first")
    assert first["route"]["conversation"] == unclaimed
    _file_says(world, "magnet", mid, None)
    _, claimed = ask(world, {"magnet": mid}, text="Another")
    cid = claimed["route"]["conversation"]
    assert claimed["route"]["created"] and cid != unclaimed

    status, again = ask(world, {"magnet": mid}, op="first")
    assert status == 200 and again["replayed"], again
    assert again["route"]["conversation"] == unclaimed
    assert _file_of(world, "magnet", mid) == cid


@pytest.mark.parametrize("kind", ["workspace", "magnet"])
def test_with_no_claim_a_file_naming_a_real_conversation_is_used(world, kind):  # noqa: F811
    """A Magnet's own from before claims: nothing here makes the file lead the record."""
    ref = a_workspace(world) if kind == "workspace" else a_magnet(world)
    named = a_conversation(world)
    _file_says(world, kind, ref, named)
    known = conversations(world)
    status, got = ask(world, {kind: ref})
    assert status == 200, got
    assert got["route"] == {"rule": kind, "conversation": named, "created": False}
    assert conversations(world) == known and _file_of(world, kind, ref) == named
    assert _claims(world["state"], kind, ref) == []
    if kind == "magnet":
        status, got = post(world, {"author": world["who"]["@brian"]},
                           path=f"magnets/{ref}/conversation")
        assert (status, got["conversation"], got["created"]) == (200, named, False)
        assert _claims(world["state"], kind, ref) == []


@pytest.mark.parametrize("kind", ["workspace", "magnet"])
def test_a_first_request_with_neither_claim_nor_file_makes_and_claims_one(world, kind):  # noqa: F811
    ref = a_workspace(world) if kind == "workspace" else a_magnet(world)
    before = conversations(world)
    status, got = ask(world, {kind: ref})
    assert status == 200 and got["route"]["created"], got
    cid = got["route"]["conversation"]
    assert conversations(world) - before == {cid}
    assert _claims(world["state"], kind, ref) == [cid]
    assert _file_of(world, kind, ref) == cid


def test_a_claim_answers_nothing_for_a_workspace_that_is_gone(world):  # noqa: F811
    wid, _ = _owned(world, "workspace")
    wm.delete(world["root"], wid)
    status, got = ask(world, {"workspace": wid}, text="After")
    assert status == 410 and got["kind"] == "Gone"


def test_a_claim_answers_nothing_for_a_magnet_that_is_gone(world, monkeypatch):  # noqa: F811
    mid, _ = _owned(world, "magnet")
    monkeypatch.setattr(M, "read", lambda *_: None)
    status, got = ask(world, {"magnet": mid}, text="After")
    assert status == 422 and got["reason"]["code"] == "state"
    status, got = post(world, {"author": world["who"]["@brian"]},
                       path=f"magnets/{mid}/conversation")
    assert status == 422 and got["reason"]["code"] == "state"


# -- retries and races --------------------------------------------------------

def test_a_retried_first_request_is_one_request(world):  # noqa: F811
    wid = a_workspace(world)
    _, first = ask(world, {"workspace": wid}, op="same")
    cid = first["route"]["conversation"]
    status, again = ask(world, {"workspace": wid}, op="same")
    assert status == 200 and again["replayed"] is True
    assert again["post"] == first["post"]
    assert posts_in(world, cid) == [first["post"]]
    assert len(world["sent"]) == 1


def test_a_reused_key_for_another_request_is_refused(world):  # noqa: F811
    wid = a_workspace(world)
    ask(world, {"workspace": wid}, op="same")
    status, got = ask(world, {"workspace": wid}, op="same", text="Different")
    assert status == 422 and got["refused"] is True


@pytest.mark.parametrize("kind", ["workspace", "magnet"])
def test_two_first_requests_make_one_conversation(world, kind):  # noqa: F811
    ref = a_workspace(world) if kind == "workspace" else a_magnet(world)
    world["agent"] = world["cv"].create_participant("@Scribe")
    before = conversations(world)
    answers, gate = [], threading.Barrier(6)

    def one(i):
        gate.wait(5)
        answers.append(ask(world, {kind: ref}, text=f"Request {i}"))

    threads = [threading.Thread(target=one, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert [s for s, _ in answers] == [200] * 6, answers
    cids = {a["route"]["conversation"] for _, a in answers}
    assert len(cids) == 1 and conversations(world) - before == cids
    assert sum(a["route"]["created"] for _, a in answers) == 1
    assert len(posts_in(world, cids.pop())) == 6


# -- persistence --------------------------------------------------------------

def test_it_survives_a_reopened_server(world):  # noqa: F811
    wid = a_workspace(world)
    _, first = ask(world, {"workspace": wid})
    cid = first["route"]["conversation"]
    again = _State(world["root"])
    assert wm.workspace(again.corpus.root, wid)["manifest"]["conversation"] == cid
    status, got, _ = commands.agent_request(
        again, {"from": {"workspace": wid}, "text": "Back again",
                "author": world["who"]["@brian"], "op": "back-again"},
        written_by=lambda: web._observed_writer(again, None))
    assert status == 200, got
    assert got["route"] == {"rule": "workspace", "conversation": cid,
                            "created": False}


def test_a_manifest_keeps_it_through_every_change(world):  # noqa: F811
    root = world["root"]
    wid = a_workspace(world, magnet_object("mag-one"), magnet_object("mag-two"))
    was = wm.workspace(root, wid)["manifest"]["revision"]
    answer = wm.set_conversation(root, wid, "ent-own")
    assert answer["changed"] and answer["manifest"]["revision"] == was + 1
    assert not wm.set_conversation(root, wid, "ent-own")["changed"]
    wm.rename(root, wid, {"name": "Another"})
    objects = wm.workspace(root, wid)["manifest"]["objects"]
    wm.reorder(root, wid, {"order": [o["id"] for o in reversed(objects)]})
    wm.remove_object(root, wid, objects[0]["id"])
    wm.add_object(root, wid, {"object": magnet_object("mag-three")})
    manifest = wm.workspace(root, wid)["manifest"]
    assert manifest["conversation"] == "ent-own"
    assert all("conversation" not in o for o in wm.curated_references(manifest)), \
        "not a curated reference"
    assert [o["ref"] for o in manifest["objects"]] == ["mag-two", "mag-three"]
    assert wm.workspaces(root)[0]["id"] == wid


def test_a_manifest_from_before_the_field_reads_as_none_and_can_take_one(world):  # noqa: F811
    root = world["root"]
    wid = a_workspace(world)
    path = pathlib.Path(root, "presentation", wm.FOLDER, f"{wid}.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "conversation" not in data and data["schema_version"] == wm.SCHEMA_VERSION
    status, got = ask(world, {"workspace": wid})
    assert status == 200 and got["route"]["created"]
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_only_the_request_door_names_it(world):  # noqa: F811
    root = world["root"]
    with pytest.raises(wm.Refused):
        wm.create(root, {"conversation": "ent-chosen"})
    wid = a_workspace(world)
    for bad in ("wsp-other", "../evil", "", None, 7):
        with pytest.raises(wm.Refused):
            wm.set_conversation(root, wid, bad)
    assert "conversation" not in wm.workspace(root, wid)["manifest"]


@pytest.mark.parametrize("value", ["wsp-other", "../evil", "", 7, None, ["ent-a"]])
def test_a_malformed_name_in_the_file_makes_it_unreadable(world, value):  # noqa: F811
    root = world["root"]
    wid = a_workspace(world)
    path = pathlib.Path(root, "presentation", wm.FOLDER, f"{wid}.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, "conversation": value}), encoding="utf-8")
    assert "unreadable" in wm.workspace(root, wid)
    with pytest.raises(wm.Unreadable):
        wm.set_conversation(root, wid, "ent-own")


def test_deleting_a_workspace_leaves_its_conversation(world):  # noqa: F811
    wid = a_workspace(world)
    _, got = ask(world, {"workspace": wid})
    cid = got["route"]["conversation"]
    wm.delete(world["root"], wid)
    tomb = json.loads(pathlib.Path(world["root"], "presentation", wm.FOLDER,
                                   f"{wid}.json").read_text(encoding="utf-8"))
    assert "conversation" not in tomb
    assert cid in conversations(world) and posts_in(world, cid) == [got["post"]]
    with pytest.raises(wm.Gone):
        wm.set_conversation(world["root"], wid, cid)


# -- the boundaries -----------------------------------------------------------

def test_a_worker_grant_is_refused_at_this_door(world):  # noqa: F811
    wid = a_workspace(world)
    before = conversations(world)
    agent = world["cv"].create_participant("@Scribe")
    status, got = post(world, {"from": {"workspace": wid}, "text": "Mine now",
                               "author": agent},
                       headers={CAPABILITY_HEADER: "a-grant"})
    assert status == 403 and got["kind"] == "PermissionError"
    assert conversations(world) == before
    assert "conversation" not in wm.workspace(world["root"], wid)["manifest"]


def test_it_needs_the_client_header_as_every_fluid_post_does(world):  # noqa: F811
    req = urllib.request.Request(
        world["base"] + "/fluid/api/requests", data=b"{}",
        headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(req)
    assert caught.value.code == 403


def test_it_adds_no_worker_operation():
    assert not {op for op in OPERATIONS if "workspace" in op or "route" in op}
    assert commands.command_of("requests") == (commands.REQUESTS, None)


def test_the_front_forwards_it_to_python_and_owns_none_of_it():
    table = json.loads(pathlib.Path(__file__).parent.parent.joinpath(
        "crates", "mentis-server", "route-table.default.json"
    ).read_text(encoding="utf-8"))
    assert not [r for r in table["routes"] if "requests" in r["path"]]


def test_the_module_starts_no_run_of_its_own():
    text = pathlib.Path(commands.__file__).read_text(encoding="utf-8")
    assert "mentis.execution" not in text and "subprocess" not in text


def _dispatched_for_real(world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: D.dispatch(world["state"], **kw))


def _reply_to(world, cid, request):  # noqa: F811
    deadline = time.time() + 15
    while time.time() < deadline:
        later = [t for t in world["cv"].turns(cid) if t["turn"] != request]
        if later:
            return later
        time.sleep(.05)
    pytest.fail(f"no result in {cid}")


@pytest.mark.parametrize("kind", ["workspace", "magnet", "destination"])
def test_the_result_comes_back_where_the_request_went(
        world, rt, monkeypatch, kind):  # noqa: F811
    _dispatched_for_real(world, monkeypatch)
    wid = a_workspace(world, magnet_object(a_magnet(world)))
    other = a_conversation(world)
    origin = {"magnet": a_magnet(world)} if kind == "magnet" else {"workspace": wid}
    more = {"destination": {"conversation": other}} if kind == "destination" else {}
    status, got = ask(world, origin, **more)
    assert status == 200, got
    cid = got["route"]["conversation"]
    if kind == "destination":
        assert cid == other
    reply = _reply_to(world, cid, got["post"])
    assert len(reply) == 1 and "done: here is the chart" in json.dumps(reply[0])
    assert home_of(world, reply[0]["turn"]) == cid
    assert rt["grants"][0]["conversation"] == cid, \
        "the run's authority is over where it was sent, by the ordinary grant"
    if kind == "destination":
        assert "conversation" not in wm.workspace(world["root"], wid)["manifest"]


@pytest.mark.parametrize("kind", ["workspace", "magnet"])
def test_the_result_and_grant_follow_the_claim_not_a_differing_file(
        world, rt, monkeypatch, kind):  # noqa: F811
    _dispatched_for_real(world, monkeypatch)
    ref = a_workspace(world) if kind == "workspace" else a_magnet(world)
    _, first = ask(world, {kind: ref})
    cid = first["route"]["conversation"]
    _reply_to(world, cid, first["post"])
    stale = a_conversation(world)
    _file_says(world, kind, ref, stale)
    grants, before = len(rt["grants"]), set(posts_in(world, cid))

    status, got = ask(world, {kind: ref}, text="Make another")

    assert status == 200 and got["route"]["conversation"] == cid, got
    deadline = time.time() + 15
    while time.time() < deadline and len(set(posts_in(world, cid)) - before) < 2:
        time.sleep(.05)
    new = set(posts_in(world, cid)) - before - {got["post"]}
    assert len(new) == 1, "the result is said where the claim says"
    assert home_of(world, new.pop()) == cid
    assert [g["conversation"] for g in rt["grants"][grants:]] == [cid], \
        "the run's authority is over the claim's Conversation"
    assert posts_in(world, stale) == []
    assert _file_of(world, kind, ref) == cid
