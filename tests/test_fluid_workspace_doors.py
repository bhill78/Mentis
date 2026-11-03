"""A workspace's doors (`mentis.fluid.commands.workspace_command`), what refers to a
Magnet once a workspace can, and a workspace's layout as an arrangement under its
id. Contract: `docs/magnets/M1-contract.md`."""
from __future__ import annotations

import itertools
import json
import pathlib
import urllib.error
import urllib.request

import pytest

import mentis.magnet as M
from mentis.fluid import arrangements as A
from mentis.fluid import commands
from mentis.fluid import workspace_manifest as wm
from mentis.worker import CAPABILITY_HEADER, OPERATIONS
from tests._loop import a_conversation, rt, world  # noqa: F401


_ops = itertools.count(1)


def op():
    return f"door-{next(_ops)}"


def post(world, path, body=None, headers=None):  # noqa: F811
    req = urllib.request.Request(
        world["base"] + "/fluid/api/" + path,
        data=json.dumps({} if body is None else body).encode(),
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1",
                 **(headers or {})},
        method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def get(world, path, headers=None):  # noqa: F811
    req = urllib.request.Request(
        world["base"] + "/fluid/api/" + path,
        headers={"X-Mentis-Client": "1", **(headers or {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def blank(world, **more):  # noqa: F811
    status, got = post(world, "workspaces", {"op": op(), **more})
    assert status == 201, got
    return got["id"]


def conversations(world):  # noqa: F811
    return {c["id"] for c in world["cv"].all_conversations()}


def obj(ref="mag-a", kind="magnet"):
    return {"kind": kind, "ref": ref, "provenance": {
        "source": {"kind": "participant", "ref": "ent-owner"}}}


SEED = {"sources": [{"kind": "conversation", "conversation": "ent-src"}],
        "selection": {}, "collection": {"mode": "one-time"},
        "synthesis": {"mode": "manual"},
        "notifications": {"newItems": False, "changes": False,
                          "failures": False},
        "presentation": {"renderer": "disc"}}
BASE = {"format": A.FORMAT, "version": 2,
        "tree": {"type": "zone", "id": "stage", "show": "objects"}}


def a_magnet(world, key="home"):  # noqa: F811
    status, got = post(world, f"arrangements/{key}/magnets", {
        "seed": SEED,
        "attach": {"zone": {"type": "zone", "show": "magnet", "name": "Board"},
                   "base": BASE}})
    assert status == 200, got
    return got["magnet"]["id"]


def a_definition(world, mid="mag-kept"):  # noqa: F811
    """A definition nothing refers to."""
    M.write(world["root"], mid, {**json.loads(json.dumps(SEED)), "id": mid})
    assert M.references(world["root"], mid) == []
    return mid


def spoil(world, wid):  # noqa: F811
    path = wm._path(world["root"], wid)
    path.write_text("{ not a manifest", encoding="utf-8")
    return path


def arrangement_file(world, key):  # noqa: F811
    return A._path(world["root"], key)


# -- reading ------------------------------------------------------------------

def test_reading_none_and_some(world):  # noqa: F811
    assert get(world, "workspaces") == (200, {"workspaces": []})
    one = blank(world, name="One")
    status, got = get(world, f"workspaces/{one}")
    assert status == 200 and got["id"] == one
    assert got["manifest"]["name"] == "One" and got["manifest"]["objects"] == []
    assert "ops" not in got["manifest"]
    _, listed = get(world, "workspaces")
    assert [(w["id"], w["name"], w["objects"]) for w in listed["workspaces"]] \
        == [(one, "One", 0)]


def test_a_read_says_404_410_409_and_400(world):  # noqa: F811
    assert get(world, "workspaces/wsp-nobody")[0] == 404
    gone = blank(world)
    assert post(world, f"workspaces/{gone}/delete", {"op": op()})[0] == 200
    status, got = get(world, f"workspaces/{gone}")
    assert status == 410 and got["kind"] == "Gone"
    _, listed = get(world, "workspaces")
    assert listed["workspaces"] == []
    bad = blank(world)
    spoil(world, bad)
    status, got = get(world, f"workspaces/{bad}")
    assert status == 409 and got["kind"] == "Unreadable"
    _, listed = get(world, "workspaces")
    assert [w["id"] for w in listed["workspaces"]] == [bad]
    assert "unreadable" in listed["workspaces"][0], "not lost to sight"
    assert get(world, "workspaces/not-a-workspace")[0] == 400
    assert get(world, "workspaces/WSP-LOUD")[0] == 400


# -- making one ---------------------------------------------------------------

def test_a_blank_one_makes_nothing_else(world):  # noqa: F811
    before = conversations(world)
    status, got = post(world, "workspaces", {"op": op()})
    assert status == 201 and got["replayed"] is False and got["changed"] is True
    assert got["manifest"]["objects"] == [] and got["manifest"]["name"] == ""
    assert "conversation" not in got["manifest"]
    assert conversations(world) == before
    assert not (pathlib.Path(world["root"]) / "presentation" / "magnets").exists()


def test_a_retry_is_the_same_one_and_another_request_is_refused(world):  # noqa: F811
    key = op()
    status, first = post(world, "workspaces", {"name": "A", "op": key})
    assert status == 201
    status, again = post(world, "workspaces", {"name": "A", "op": key})
    assert status == 200 and again["replayed"] is True
    assert again["changed"] is False and again["id"] == first["id"]
    assert again["manifest"] == first["manifest"]
    status, got = post(world, "workspaces", {"name": "B", "op": key})
    assert status == 422 and got["refused"] is True and got["kind"] == "Conflict"
    assert wm.workspace(world["root"], first["id"])["manifest"]["name"] == "A"
    assert len(get(world, "workspaces")[1]["workspaces"]) == 1


def test_it_needs_a_key_of_every_door(world):  # noqa: F811
    wid = blank(world)
    oid = wm.object_id("magnet", "mag-a")
    for path in ("workspaces", f"workspaces/{wid}/rename",
                 f"workspaces/{wid}/objects", f"workspaces/{wid}/reorder",
                 f"workspaces/{wid}/delete",
                 f"workspaces/{wid}/objects/{oid}/remove"):
        for body in ({}, {"op": "  "}, {"op": 7}):
            status, got = post(world, path, body)
            assert status == 400 and "op" in got["error"], (path, body)
    assert len(get(world, "workspaces")[1]["workspaces"]) == 1


def test_made_from_a_magnet(world):  # noqa: F811
    mid = a_definition(world)
    before = conversations(world)
    key = op()
    status, got = post(world, "workspaces",
                        {"name": "Seen", "from": {"magnet": mid}, "op": key})
    assert status == 201, got
    only, = got["manifest"]["objects"]
    assert (only["kind"], only["ref"], only["curated"]) == ("magnet", mid, True)
    assert only["provenance"]["source"] == {"kind": "magnet", "ref": mid}
    assert "from" not in got["manifest"]
    assert conversations(world) == before, "no Conversation is made"
    assert "conversation" not in got["manifest"]
    assert M.read(world["root"], mid).get("conversation") is None
    status, again = post(world, "workspaces",
                         {"name": "Seen", "from": {"magnet": mid}, "op": key})
    assert status == 200 and again["replayed"] is True


def test_made_from_a_conversation(world, a_conversation=a_conversation):  # noqa: F811
    cid = a_conversation(world)
    before = conversations(world)
    status, got = post(world, "workspaces",
                       {"from": {"conversation": cid}, "op": op()})
    assert status == 201, got
    only, = got["manifest"]["objects"]
    assert (only["kind"], only["ref"]) == ("conversation", cid)
    assert only["provenance"]["source"] == {"kind": "conversation", "ref": cid}
    assert conversations(world) == before


def test_from_stands_first_with_any_objects_it_comes_with(world):  # noqa: F811
    mid = a_definition(world)
    status, got = post(world, "workspaces", {
        "from": {"magnet": mid}, "op": op(),
        "objects": [obj("mag-other"), obj(mid)]})
    assert status == 201, got
    assert [o["ref"] for o in got["manifest"]["objects"]] == [mid, "mag-other"]
    assert got["manifest"]["objects"][0]["provenance"]["source"]["kind"] == "magnet"


def test_from_something_not_there_is_refused_and_makes_nothing(world):  # noqa: F811
    status, got = post(world, "workspaces",
                       {"from": {"magnet": "mag-nobody"}, "op": op()})
    assert status == 422 and got["refused"] is True
    status, _ = post(world, "workspaces",
                     {"from": {"conversation": "ent-nobody"}, "op": op()})
    assert status == 400
    status, _ = post(world, "workspaces",
                     {"from": {"conversation": "wsp-nobody"}, "op": op()})
    assert status == 400
    for bad in ({"workspace": "wsp-x"}, {"magnet": "mag-a", "conversation": "e"},
                "mag-a", {"magnet": ""}):
        assert post(world, "workspaces", {"from": bad, "op": op()})[0] == 400
    assert get(world, "workspaces")[1]["workspaces"] == []


def test_a_retry_outlives_what_it_started_from(world):  # noqa: F811
    mid = a_definition(world)
    key = op()
    body = {"from": {"magnet": mid}, "op": key}
    status, first = post(world, "workspaces", body)
    assert status == 201
    oid = first["manifest"]["objects"][0]["id"]
    assert post(world, f"workspaces/{first['id']}/objects/{oid}/remove",
                {"op": op()})[0] == 200
    assert post(world, f"magnets/{mid}/delete")[1]["deleted"] is True
    status, again = post(world, "workspaces", body)
    assert status == 200 and again["replayed"] is True


MISSING_SEEDS = ({"magnet": "mag-nobody"}, {"conversation": "ent-nobody"})
NOT_SEED_WORDS = (M.MISSING, "is not a conversation")


@pytest.mark.parametrize("seed", MISSING_SEEDS)
@pytest.mark.parametrize("bad,says", [
    ({"op": "k" * (wm.MAX_OP + 1)}, "op"),
    ({"op": "a\nkey"}, "op"),
    ({"op": "a-key-\ud800"}, "Unicode"),
    ({"name": 7}, "name"),
    ({"name": "n" * (wm.MAX_NAME + 1)}, "name"),
    ({"objects": "mag-a"}, "objects"),
    ({"objects": [{"kind": "no"}]}, "objects"),
    ({"objects": [obj()] * (wm.MAX_OBJECTS + 1)}, "objects"),
    ({"layout": {}}, "layout"),
    ({"conversation": "ent-chosen"}, "conversation"),
    ({"format": "another"}, "format"),
])
def test_a_malformed_request_is_400_whether_or_not_its_seed_is_there(world, seed, bad,  # noqa: F811
                                                                     says):
    status, got = post(world, "workspaces", {"op": op(), "from": seed, **bad})
    assert status == 400 and got["kind"] == "BadRequest", got
    assert says in got["error"]
    assert not any(w in got["error"] for w in NOT_SEED_WORDS)
    assert get(world, "workspaces")[1]["workspaces"] == []


def test_a_malformed_seed_is_400_and_not_a_missing_one(world):  # noqa: F811
    for seed in ({"magnet": "not-a-magnet"}, {"conversation": "wsp-nobody"}):
        status, got = post(world, "workspaces", {"from": seed, "op": op()})
        assert status == 400 and got["kind"] == "BadRequest", got
        assert not any(w in got["error"] for w in NOT_SEED_WORDS)


@pytest.mark.parametrize("seed", MISSING_SEEDS)
def test_a_request_over_a_bound_is_400_whether_or_not_its_seed_is_there(  # noqa: F811
        world, monkeypatch, seed):
    blank(world)
    with monkeypatch.context() as patch:
        patch.setattr(wm, "MAX_WORKSPACES", 1)
        status, got = post(world, "workspaces", {"from": seed, "op": op()})
    assert status == 400 and "at most" in got["error"], got
    monkeypatch.setattr(wm, "MAX_BYTES", 300)
    status, got = post(world, "workspaces", {"from": seed, "op": op()})
    assert status == 400 and "larger" in got["error"], got
    assert len(get(world, "workspaces")[1]["workspaces"]) == 1


def test_a_well_formed_request_still_hears_its_seed_is_not_there(world):  # noqa: F811
    status, got = post(world, "workspaces", {
        "from": {"magnet": "mag-nobody"}, "op": "k" * wm.MAX_OP})
    assert status == 422 and got["error"] == M.MISSING and got["refused"] is True
    assert got["magnet"] == "mag-nobody"
    status, got = post(world, "workspaces", {
        "from": {"conversation": "ent-nobody"}, "op": op()})
    assert status == 400 and "is not a conversation" in got["error"]
    assert get(world, "workspaces")[1]["workspaces"] == []


def test_a_refused_seed_keeps_no_key(world):  # noqa: F811
    mid, key = "mag-later", op()
    body = {"from": {"magnet": mid}, "op": key}
    assert post(world, "workspaces", body)[0] == 422
    a_definition(world, mid)
    status, got = post(world, "workspaces", body)
    assert status == 201 and got["replayed"] is False


@pytest.mark.parametrize("seed", MISSING_SEEDS)
def test_a_used_key_is_answered_by_the_key_and_not_by_the_seed(world, seed):  # noqa: F811
    key = op()
    status, first = post(world, "workspaces", {"name": "A", "op": key})
    assert status == 201
    status, got = post(world, "workspaces", {"name": "A", "from": seed, "op": key})
    assert status == 422 and got["kind"] == "Conflict", got
    status, got = post(world, "workspaces", {"name": 7, "from": seed, "op": key})
    assert status == 400 and got["kind"] == "BadRequest", got
    status, again = post(world, "workspaces", {"name": "A", "op": key})
    assert status == 200 and again["replayed"] is True
    assert again["manifest"] == first["manifest"]


def test_a_retry_of_a_deleted_workspace_is_answered_by_its_key(world):  # noqa: F811
    mid, key = a_definition(world), op()
    body = {"from": {"magnet": mid}, "op": key}
    status, first = post(world, "workspaces", body)
    assert status == 201
    assert post(world, f"workspaces/{first['id']}/delete", {"op": op()})[0] == 200
    assert post(world, f"magnets/{mid}/delete")[1]["deleted"] is True
    status, again = post(world, "workspaces", body)
    assert status == 200 and again["replayed"] is True and again["manifest"] is None
    status, got = post(world, "workspaces",
                       {"from": {"magnet": "mag-nobody"}, "op": key})
    assert status == 422 and got["kind"] == "Conflict", got


def test_an_unreadable_file_under_the_key_is_409_whatever_the_seed(world):  # noqa: F811
    key = op()
    status, first = post(world, "workspaces", {"op": key})
    assert status == 201
    path = spoil(world, first["id"])
    held = path.read_bytes()
    status, got = post(world, "workspaces",
                       {"from": {"magnet": "mag-nobody"}, "op": key})
    assert status == 409 and got["kind"] == "Unreadable", got
    assert path.read_bytes() == held


def test_only_a_well_formed_request_asks_after_an_unreadable_arrangement(world):  # noqa: F811
    path = arrangement_file(world, "home")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not an arrangement", encoding="utf-8")
    held = path.read_bytes()
    seed = {"magnet": "mag-nobody"}
    status, got = post(world, "workspaces", {"from": seed, "op": "k" * 121})
    assert status == 400 and "op" in got["error"], got
    status, got = post(world, "workspaces", {"from": seed, "op": op()})
    assert status == 409 and got["kind"] == "Unreadable", got
    assert path.read_bytes() == held


def test_a_magnet_known_only_by_what_an_arrangement_embeds_is_not_lifted(world):  # noqa: F811
    mid = "mag-embedded"
    folder = arrangement_file(world, "home").parent
    folder.mkdir(parents=True, exist_ok=True)
    config = {**json.loads(json.dumps(SEED)), "id": mid}
    arrangement_file(world, "home").write_text(json.dumps({"layout": {
        "format": A.FORMAT, "version": 3,
        "tree": {"type": "zone", "id": "stage", "show": "objects"},
        "magnets": {mid: config}}}), encoding="utf-8")
    assert M.references(world["root"], mid), "the fixture embeds it"
    status, got = post(world, "workspaces",
                       {"from": {"magnet": mid}, "op": op()})
    assert status == 201, got
    assert not M.exists(world["root"], mid), "a create makes no Magnet"


def test_what_a_manifest_does_not_carry_is_refused(world):  # noqa: F811
    for field in ("layout", "tree", "theme", "id", "conversation", "revision"):
        status, got = post(world, "workspaces", {field: "x", "op": op()})
        assert status == 400, (field, got)


# -- changing one -------------------------------------------------------------

def test_rename_add_reorder_and_remove(world):  # noqa: F811
    wid = blank(world)
    status, got = post(world, f"workspaces/{wid}/rename",
                       {"name": "Named", "op": op()})
    assert status == 200 and got["manifest"]["name"] == "Named"
    status, one = post(world, f"workspaces/{wid}/objects",
                       {"object": obj("mag-a"), "op": op()})
    assert status == 200 and one["object"] == wm.object_id("magnet", "mag-a")
    _, two = post(world, f"workspaces/{wid}/objects",
                  {"object": obj("mag-b"), "op": op()})
    assert [o["ref"] for o in two["manifest"]["objects"]] == ["mag-a", "mag-b"]
    status, got = post(world, f"workspaces/{wid}/reorder",
                       {"order": [two["object"], one["object"]], "op": op()})
    assert status == 200
    assert [o["ref"] for o in got["manifest"]["objects"]] == ["mag-b", "mag-a"]
    status, got = post(world, f"workspaces/{wid}/objects/{one['object']}/remove",
                       {"op": op()})
    assert status == 200
    assert [o["ref"] for o in got["manifest"]["objects"]] == ["mag-b"]


@pytest.mark.parametrize("door,body", [
    ("rename", {"name": "R"}),
    ("objects", {"object": obj("mag-a")}),
    ("reorder", {"order": []}),
    ("delete", {}),
])
def test_each_door_retries_and_refuses_another_request(world, door, body):  # noqa: F811
    wid = blank(world)
    key = op()
    path = f"workspaces/{wid}/{door}"
    status, first = post(world, path, {**body, "op": key})
    assert status == 200 and first["replayed"] is False, first
    status, again = post(world, path, {**body, "op": key})
    assert status == 200 and again["replayed"] is True
    assert again["changed"] is False
    other = "rename" if door != "rename" else "delete"
    status, got = post(world, f"workspaces/{wid}/{other}",
                       {"name": "Different", "op": key})
    assert status == 422 and got["kind"] == "Conflict", got
    assert "error" in got and got["refused"] is True


def test_removing_retries_and_refuses_another_request(world):  # noqa: F811
    wid = blank(world)
    _, added = post(world, f"workspaces/{wid}/objects",
                    {"object": obj("mag-a"), "op": op()})
    oid, key = added["object"], op()
    path = f"workspaces/{wid}/objects/{oid}/remove"
    assert post(world, path, {"op": key})[1]["replayed"] is False
    status, again = post(world, path, {"op": key})
    assert status == 200 and again["replayed"] is True
    status, got = post(world, f"workspaces/{wid}/rename", {"name": "N", "op": key})
    assert status == 422 and got["kind"] == "Conflict"
    assert post(world, path, {"op": op()})[0] == 404, "no longer held"


def _every_door(wid):
    oid = wm.object_id("magnet", "mag-a")
    return [(f"workspaces/{wid}/rename", {"name": "N"}),
            (f"workspaces/{wid}/objects", {"object": obj("mag-b")}),
            (f"workspaces/{wid}/objects/{oid}/remove", {}),
            (f"workspaces/{wid}/reorder", {"order": []}),
            (f"workspaces/{wid}/delete", {})]


def test_every_door_says_404(world):  # noqa: F811
    for path, body in _every_door("wsp-nobody"):
        status, got = post(world, path, {**body, "op": op()})
        assert status == 404 and got["kind"] == "NotFound", path
    assert not wm._path(world["root"], "wsp-nobody").exists()


def test_every_door_says_410_and_a_kept_key_still_answers(world):  # noqa: F811
    wid = blank(world)
    named = op()
    assert post(world, f"workspaces/{wid}/rename",
                {"name": "N", "op": named})[0] == 200
    delete_key = op()
    status, gone = post(world, f"workspaces/{wid}/delete", {"op": delete_key})
    assert status == 200 and gone["manifest"] is None and "deleted" in gone
    for path, body in _every_door(wid):
        status, got = post(world, path, {**body, "op": op()})
        assert status == 410 and got["kind"] == "Gone", path
    status, got = post(world, f"workspaces/{wid}/delete", {"op": delete_key})
    assert status == 200 and got["replayed"] is True
    status, got = post(world, f"workspaces/{wid}/rename",
                       {"name": "N", "op": named})
    assert status == 200 and got["replayed"] is True


def test_every_door_says_409_and_leaves_it_as_it_is(world):  # noqa: F811
    wid = blank(world)
    path_of = spoil(world, wid)
    held = path_of.read_bytes()
    for path, body in _every_door(wid):
        status, got = post(world, path, {**body, "op": op()})
        assert status == 409 and got["kind"] == "Unreadable", path
    assert path_of.read_bytes() == held


def test_malformed_is_400_not_a_200_with_an_error(world):  # noqa: F811
    wid = blank(world)
    for path, body in [(f"workspaces/{wid}/rename", {}),
                       (f"workspaces/{wid}/objects", {"object": {"kind": "no"}}),
                       (f"workspaces/{wid}/reorder", {"order": ["nope"]}),
                       (f"workspaces/{wid}/objects/nope/remove", {}),
                       ("workspaces/not-one/rename", {"name": "N"})]:
        status, got = post(world, path, {**body, "op": op()})
        assert status == 400 and got["kind"] == "BadRequest", (path, got)


def test_a_key_that_no_longer_fits_is_refused(world, monkeypatch):  # noqa: F811
    wid = blank(world)
    path = wm._path(world["root"], wid)
    monkeypatch.setattr(wm, "MAX_BYTES", path.stat().st_size)
    held = path.read_bytes()
    status, got = post(world, f"workspaces/{wid}/rename",
                       {"name": "N", "op": op()})
    assert status == 400 and "larger" in got["error"]
    assert path.read_bytes() == held


# -- the door ------------------------------------------------------------------

def test_a_worker_grant_is_refused(world):  # noqa: F811
    wid = blank(world)
    grant = {CAPABILITY_HEADER: "a-grant"}
    assert get(world, "workspaces", headers=grant)[0] == 403
    assert get(world, f"workspaces/{wid}", headers=grant)[0] == 403
    assert post(world, "workspaces", {"op": op()}, headers=grant)[0] == 403
    assert post(world, f"workspaces/{wid}/delete", {"op": op()},
                headers=grant)[0] == 403
    assert wm.workspace(world["root"], wid)["manifest"] is not None


def test_it_needs_the_client_header(world):  # noqa: F811
    req = urllib.request.Request(
        world["base"] + "/fluid/api/workspaces", data=b"{}",
        headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(req)
    assert caught.value.code == 403


def test_command_of_names_each_and_no_other():
    wid, oid = "wsp-a", "wob-0123456789abcdef"
    assert commands.command_of("workspaces") == (commands.WORKSPACES, None)
    for verb, name in commands.WORKSPACE_ACTS.items():
        assert commands.command_of(f"workspaces/{wid}/{verb}") == (name, wid)
    assert commands.command_of(f"workspaces/{wid}/objects/{oid}/remove") == (
        commands.WORKSPACE_REMOVE, f"{wid}/{oid}")
    for rest in (f"workspaces/{wid}", f"workspaces/{wid}/objects/{oid}",
                 f"workspaces/{wid}/objects//remove",
                 f"workspaces/{wid}/objects/{oid}/delete"):
        assert commands.command_of(rest) is None, rest


def test_it_adds_no_worker_operation_and_the_front_forwards_it():
    assert not {o for o in OPERATIONS if "workspace" in o}
    table = json.loads(pathlib.Path(__file__).parent.parent.joinpath(
        "crates", "mentis-server", "route-table.default.json"
    ).read_text(encoding="utf-8"))
    assert not [r for r in table["routes"] if "workspaces" in r["path"]
                or "arrangements" in r["path"]]


# -- what refers to a Magnet ----------------------------------------------------

def test_references_answers_a_workspace_and_leaves_arrangement_items_alone(world):  # noqa: F811
    mid = a_magnet(world)
    assert M.references(world["root"], mid) == [
        {"arrangement": "home", "placed": True, "held": False}]
    assert A.references(world["root"], mid) == M.references(world["root"], mid)
    second = blank(world, objects=[obj(mid)])
    first = blank(world, objects=[obj(mid)])
    oid = wm.object_id("magnet", mid)
    assert M.references(world["root"], mid) == [
        {"arrangement": "home", "placed": True, "held": False},
        *[{"workspace": w, "object": oid} for w in sorted([first, second])]]
    assert A.references(world["root"], mid) == [
        {"arrangement": "home", "placed": True, "held": False}]


def test_only_a_magnet_object_of_that_id_refers_to_it(world):  # noqa: F811
    mid = a_definition(world)
    blank(world, objects=[
        obj("mag-other"), obj(mid, "other"),
        {"kind": "magnet", "ref": "mag-found", "provenance": {
            "source": {"kind": "magnet", "ref": mid}}}])
    assert M.references(world["root"], mid) == []


def test_delete_is_refused_while_a_workspace_holds_it_and_allowed_after(world):  # noqa: F811
    mid = a_definition(world)
    root = world["root"]
    wid = blank(world, objects=[obj(mid)])
    status, got = post(world, f"magnets/{mid}/delete")
    assert status == 422 and got["refused"] is True
    assert "still place or hold" in got["error"]
    assert M.read(root, mid) is not None
    oid = wm.object_id("magnet", mid)
    assert post(world, f"workspaces/{wid}/objects/{oid}/remove",
                {"op": op()})[0] == 200
    assert M.references(root, mid) == []
    assert post(world, f"magnets/{mid}/delete") == (
        200, {"magnet": mid, "deleted": True})
    assert M.read(root, mid) is None


def test_a_deleted_workspace_holds_nothing(world):  # noqa: F811
    mid = a_definition(world)
    wid = blank(world, objects=[obj(mid)])
    assert post(world, f"workspaces/{wid}/delete", {"op": op()})[0] == 200
    assert M.references(world["root"], mid) == []
    assert post(world, f"magnets/{mid}/delete")[1]["deleted"] is True


def test_an_unreadable_manifest_makes_delete_409(world):  # noqa: F811
    mid = a_definition(world)
    wid = blank(world)
    spoil(world, wid)
    with pytest.raises(wm.Unreadable, match=wid):
        M.references(world["root"], mid)
    status, got = post(world, f"magnets/{mid}/delete")
    assert status == 409 and got["kind"] == "Unreadable"
    assert M.read(world["root"], mid) is not None


# -- a workspace's layout -------------------------------------------------------

LAYOUT = {"format": A.FORMAT, "version": 2,
          "tree": {"type": "zone", "id": "stage", "show": "objects"}}


def test_a_layout_is_read_and_kept_under_the_workspace_id(world):  # noqa: F811
    wid = blank(world, name="Laid out")
    before = wm._path(world["root"], wid).read_bytes()
    status, got = get(world, f"arrangements/{wid}")
    assert status == 200 and got == {"key": wid, "layout": None, "saved": None}
    status, saved = post(world, f"arrangements/{wid}",
                         {"layout": LAYOUT, "op": op()})
    assert status == 200, saved
    status, got = get(world, f"arrangements/{wid}")
    assert status == 200 and got["layout"]["tree"]["id"] == "stage"
    assert arrangement_file(world, wid).exists()
    assert wm._path(world["root"], wid).read_bytes() == before, \
        "layout stays out of the manifest"
    assert not ({"layout", "tree"} & set(get(world, f"workspaces/{wid}")[1]["manifest"]))


def test_a_key_with_no_workspace_is_refused_on_every_arrangement_door(world):  # noqa: F811
    assert get(world, "arrangements/wsp-nobody")[0] == 404
    gone = blank(world)
    assert post(world, f"workspaces/{gone}/delete", {"op": op()})[0] == 200
    assert get(world, f"arrangements/{gone}")[0] == 410
    bad = blank(world)
    spoil(world, bad)
    assert get(world, f"arrangements/{bad}")[0] == 409
    for key, want in (("wsp-nobody", 404), (gone, 410), (bad, 409)):
        for path, body in (
                (f"arrangements/{key}", {"layout": LAYOUT}),
                (f"arrangements/{key}/magnets", {"seed": SEED}),
                (f"arrangements/{key}/magnets/mag-a/remove", {})):
            status, got = post(world, path, {**body, "op": op()})
            assert status == want, (path, got)
    assert not arrangement_file(world, "wsp-nobody").exists()
    assert not arrangement_file(world, gone).exists()


def test_a_key_shaped_otherwise_is_not_a_workspace(world):  # noqa: F811
    for key in ("wsp-LOUD", "WSP-loud", "wsp-"):
        assert get(world, f"arrangements/{key}")[0] == 400, key
        with pytest.raises(A.Refused):
            A.check_key(key)
    assert A.check_key("wsp-quiet") == "wsp-quiet"
    assert get(world, "arrangements/ent-nobody")[0] == 400


def test_magnets_and_holds_under_a_workspace_key(world):  # noqa: F811
    wid = blank(world)
    mid = a_magnet(world, wid)
    assert M.references(world["root"], mid) == [
        {"arrangement": wid, "placed": True, "held": False}]
    status, got = get(world, f"arrangements/{wid}")
    assert status == 200 and mid in got["layout"]["magnets"]
    assert post(world, f"magnets/{mid}/delete")[0] == 422
    status, got = post(world, f"arrangements/{wid}/magnets/{mid}/remove",
                       {"op": op()})
    assert status == 422, "a zone still shows it"
    status, got = post(world, f"arrangements/{wid}",
                       {"sharedZone": {"op": "remove", "id": mid}, "op": op()})
    assert status == 200, got
    assert M.references(world["root"], mid) == [
        {"arrangement": wid, "placed": False, "held": True}]
    assert post(world, f"magnets/{mid}/delete")[0] == 422
    status, got = post(world, f"arrangements/{wid}/magnets/{mid}/remove",
                       {"op": op()})
    assert status == 200, got
    assert M.references(world["root"], mid) == []
    assert post(world, f"magnets/{mid}/delete")[1]["deleted"] is True


def test_deleting_a_workspace_leaves_its_arrangement_unread(world):  # noqa: F811
    wid = blank(world)
    mid = a_magnet(world, wid)
    root = world["root"]
    path = arrangement_file(world, wid)
    held = path.read_bytes()
    assert post(world, f"workspaces/{wid}/delete", {"op": op()})[0] == 200
    assert path.read_bytes() == held, "the file is left"
    assert M.read(root, mid) is not None, "and no definition goes"
    assert M.references(root, mid) == [], "and it holds nothing any more"
    assert get(world, f"arrangements/{wid}")[0] == 410
    assert post(world, f"magnets/{mid}/delete")[1]["deleted"] is True, \
        "nothing could ever end that hold, so it does not keep the Magnet"


def test_an_unreadable_arrangement_of_a_deleted_workspace_blocks_nothing(world):  # noqa: F811
    mid = a_definition(world)
    wid = blank(world)
    assert post(world, f"arrangements/{wid}", {"layout": LAYOUT,
                                               "op": op()})[0] == 200
    path = arrangement_file(world, wid)
    path.write_text("{ not an arrangement", encoding="utf-8")
    assert post(world, f"magnets/{mid}/delete")[0] == 409, "while it stands"
    assert post(world, f"workspaces/{wid}/delete", {"op": op()})[0] == 200
    assert post(world, "magnets/lift")[1]["skipped"] == {}
    assert post(world, f"magnets/{mid}/delete")[1]["deleted"] is True


def test_an_arrangement_of_a_workspace_that_never_was_is_unread(world):  # noqa: F811
    mid = a_definition(world)
    path = arrangement_file(world, "wsp-nobody")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not an arrangement", encoding="utf-8")
    assert M.references(world["root"], mid) == []


def test_an_unreadable_manifest_keeps_its_arrangement_counted(world):  # noqa: F811
    wid = blank(world)
    mid = a_magnet(world, wid)
    spoil(world, wid)
    with pytest.raises(wm.Unreadable):
        M.references(world["root"], mid)
    assert post(world, f"magnets/{mid}/delete")[0] == 409


def test_a_request_routes_without_reading_objects(world):  # noqa: F811
    """The workspace's objects decide nothing about where a request goes: it goes to
    the workspace's own Conversation, made then, whatever Magnet it holds."""
    mid = a_magnet(world)
    wid = blank(world, objects=[obj(mid)])
    agent = world["cv"].create_participant("@Scribe")
    status, got = post(world, "requests", {
        "from": {"workspace": wid}, "author": world["who"]["@brian"],
        "text": "Report", "action": "ask-participant", "addressed_to": [agent],
        "dispatch": [{"participant": agent, "work": "Report"}], "op": op()})
    assert status == 200, got
    assert got["route"]["rule"] == "workspace" and got["route"]["created"] is True
    assert M.read(world["root"], mid).get("conversation") is None


# -- a workspace's id is no Conversation's ---------------------------------------

def test_the_plain_conversation_open_refuses_a_workspace_key(world):  # noqa: F811
    wid = blank(world)
    before = conversations(world)
    who = world["who"]["@brian"]
    for key in (wid, "wsp-anything", "WSP-loud"):
        status, got = post(world, "conversations", {"author": who, "op": key})
        assert status == 400 and got["kind"] == "BadRequest", key
    assert conversations(world) == before
    status, got = post(world, "conversations", {"author": who, "op": "plain-key"})
    assert status == 201, got


def test_conversation_doors_do_not_take_a_workspace_id(world):  # noqa: F811
    wid = blank(world)
    who = world["who"]["@brian"]
    status, got = post(world, "posts", {"conversation": wid, "author": who,
                                        "text": "Hello"})
    assert status == 400 and "not a conversation" in got["error"]
    assert get(world, f"collections/conversation?id={wid}")[0] >= 400
    status, got = post(world, "requests", {
        "from": {"conversation": wid}, "author": who, "text": "Hello",
        "op": op()})
    assert status >= 400, got
    assert wid not in conversations(world)


def test_a_workspace_own_conversation_is_still_opened(world):  # noqa: F811
    """The refusal is the plain route's: a workspace's first request isn't keyed so."""
    wid = blank(world, name="Own")
    agent = world["cv"].create_participant("@Scribe")
    status, got = post(world, "requests", {
        "from": {"workspace": wid}, "author": world["who"]["@brian"],
        "text": "Report", "action": "ask-participant", "addressed_to": [agent],
        "dispatch": [{"participant": agent, "work": "Report"}], "op": op()})
    assert status == 200 and got["home_name"] == "Own", got
