"""Magnet definitions independent of workspaces (`docs/magnets/M1-contract.md`).

The migration fixture is `tests/fixtures/magnets/`: the fluid-dev Brain's own
arrangement files, copied, so real configs are what is lifted."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import shutil
import threading
import urllib.error
import urllib.request

import pytest

import mentis.magnet as M
from mentis.fluid import _checks as W
from mentis.fluid import arrangements as A
from mentis.magnet import schema as S
from tests._loop import world  # noqa: F401

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "magnets"
A_KEY, B_KEY = "ent-a", "ent-b"


@pytest.fixture()
def root(tmp_path):
    return str(tmp_path)


def seed(**over):
    return {"sources": [{"kind": "conversation", "conversation": "ent-src"}],
            "selection": {}, "collection": {"mode": "one-time"},
            "synthesis": {"mode": "manual"},
            "notifications": {"newItems": False, "changes": False, "failures": False},
            "presentation": {"renderer": "disc"}, **over}


def layout(**over):
    return {"format": A.FORMAT, "version": 3,
            "tree": {"type": "zone", "id": "stage", "show": "objects"}, **over}


def attach():
    return {"zone": {"type": "zone", "show": "magnet", "name": "Board"}}


def arrangement_path(root, key):
    return pathlib.Path(root) / "presentation" / A.FOLDER / f"{key}.json"


def definition_path(root, mid):
    return pathlib.Path(root) / "presentation" / M.FOLDER / f"{mid}.json"


def put(root, key, lay):
    W._atomic(arrangement_path(root, key),
              {"key": key, "layout": A.check(lay), "saved": 1.0, "ops": []})


def wire(root, key):
    return A.arrangement(root, key)["layout"]


def on_disk(root, key):
    return json.loads(arrangement_path(root, key).read_text(encoding="utf-8"))


def made(root, key=A_KEY, **body):
    if not arrangement_path(root, key).exists():
        put(root, key, layout())
    return A.create_magnet(root, key, {"seed": seed(), "attach": attach(), **body})


def place(root, key, mid):
    if not arrangement_path(root, key).exists():
        put(root, key, layout())
    return A.create_magnet(root, key, {"id": mid, "attach": attach()})


def take_out(root, key, mid):
    return A.save(root, key, {"sharedZone": {"op": "remove", "id": mid}})


def digests(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in pathlib.Path(folder).glob("*.json")}


# -- the migration fixture -------------------------------------------------------------

@pytest.fixture()
def fluid_dev(root):
    folder = arrangement_path(root, "x").parent
    folder.mkdir(parents=True)
    for f in FIXTURE.glob("*.json"):
        shutil.copy(f, folder / f.name)
    return root


def embedded():
    out = {}
    for f in FIXTURE.glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        for mid, c in (data["layout"].get("magnets") or {}).items():
            out.setdefault(mid, []).append((data["key"], c))
    return out


def test_the_fixture_is_the_real_shape():
    found = embedded()
    assert len(found) >= 16
    configs = [c for held in found.values() for _k, c in held]
    assert {c["presentation"]["renderer"] for c in configs} >= {"disc", "ring", "cards"}
    assert any(c["collection"]["mode"] == "continuous"
               and c["notifications"]["newItems"] for c in configs)


def test_a_read_rewrites_nothing_and_shows_every_field_as_it_was(fluid_dev):
    folder = arrangement_path(fluid_dev, "x").parent
    before = digests(folder)
    for f in FIXTURE.glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        got = A.arrangement(fluid_dev, data["key"])
        assert got["layout"].get("magnets") == data["layout"].get("magnets")
        assert got["saved"] == data["saved"]
    assert digests(folder) == before
    assert not (pathlib.Path(fluid_dev) / "presentation" / M.FOLDER).exists()


def test_lifting_is_lossless_idempotent_and_keeps_every_id(fluid_dev):
    folder = arrangement_path(fluid_dev, "x").parent
    before = digests(folder)
    wire_before = {p.stem: wire(fluid_dev, p.stem) for p in folder.glob("*.json")}
    found = embedded()

    first = A.lift_all(fluid_dev)
    assert first["lifted"] == len(found) and first["skipped"] == {}
    assert digests(folder) == before, "lifting never rewrites an arrangement"
    defs = pathlib.Path(fluid_dev) / "presentation" / M.FOLDER
    assert {p.stem for p in defs.glob("*.json")} == set(found)

    kept = digests(defs)
    again = A.lift_all(fluid_dev)
    assert again["lifted"] == 0
    assert digests(defs) == kept and digests(folder) == before

    for mid, held in found.items():
        file = json.loads((defs / f"{mid}.json").read_text(encoding="utf-8"))
        assert file["schema_version"] == S.SCHEMA_VERSION
        assert {k: v for k, v in file.items() if k != "schema_version"} == held[0][1]
    for key, lay in wire_before.items():
        assert wire(fluid_dev, key) == lay, "the wire is the same after a lift"


def test_magnets_reading_one_conversation_stay_separate(fluid_dev):
    A.lift_all(fluid_dev)
    by_source = {}
    for held in embedded().values():
        for s in held[0][1]["sources"]:
            by_source.setdefault(s.get("conversation"), set()).add(held[0][1]["id"])
    assert max(len(v) for v in by_source.values()) > 1, "the fixture has duplicates"
    defs = pathlib.Path(fluid_dev) / "presentation" / M.FOLDER
    assert len(list(defs.glob("*.json"))) == len(embedded())


def test_the_first_write_lifts_and_drops_the_map_and_changes_nothing_shown(fluid_dev):
    key = next(k for held in embedded().values() for k, _c in held)
    shown = wire(fluid_dev, key)
    got = A.save(fluid_dev, key, {"scope": "compact", "presentation": None})
    assert got["layout"]["magnets"] == shown["magnets"]
    assert "magnets" not in on_disk(fluid_dev, key)["layout"]
    assert wire(fluid_dev, key)["magnets"] == shown["magnets"]
    for mid in shown["magnets"]:
        assert definition_path(fluid_dev, mid).exists()


def test_a_copy_that_disagrees_with_the_definition_is_not_lost(root):
    one = {**seed(), "id": "mag-x"}
    other = {**seed(presentation={"renderer": "ring"}), "id": "mag-x"}
    put(root, A_KEY, layout(magnets={"mag-x": one}))
    put(root, B_KEY, layout(magnets={"mag-x": other}))
    A.lift_all(root)
    assert M.read(root, "mag-x") == one
    beside = definition_path(root, "mag-x").with_name(f"mag-x.from-{B_KEY}.json")
    assert json.loads(beside.read_text(encoding="utf-8")) == other
    assert wire(root, B_KEY)["magnets"]["mag-x"] == one, "one definition, seen by both"


# -- one definition in several arrangements --------------------------------------------

def test_one_definition_across_two_arrangements(root):
    mid = made(root)["magnet"]["id"]
    got = place(root, B_KEY, mid)
    assert got["magnet"]["id"] == mid
    assert set(wire(root, A_KEY)["magnets"]) == set(wire(root, B_KEY)["magnets"]) == {mid}
    assert "magnets" not in on_disk(root, A_KEY)["layout"]
    assert "magnets" not in on_disk(root, B_KEY)["layout"]

    A.reconfigure_magnet(root, A_KEY, mid,
                         {"change": {"presentation": {"renderer": "list"}}})
    for key in (A_KEY, B_KEY):
        assert wire(root, key)["magnets"][mid]["presentation"] == {"renderer": "list"}
    assert len(list(definition_path(root, mid).parent.glob("*.json"))) == 1


def test_a_stale_save_never_writes_a_definition(root):
    mid = made(root)["magnet"]["id"]
    kept = M.read(root, mid)
    stale = wire(root, A_KEY)
    stale["magnets"][mid] = {**kept, "presentation": {"renderer": "gallery"}}
    A.save(root, A_KEY, {"layout": stale})
    assert M.read(root, mid) == kept


# -- remove versus delete --------------------------------------------------------------

def test_removing_a_placement_leaves_the_definition(root):
    mid = made(root)["magnet"]["id"]
    place(root, B_KEY, mid)
    take_out(root, A_KEY, mid)
    assert mid not in A.magnet_zones(wire(root, A_KEY))
    assert mid in wire(root, A_KEY)["magnets"], "held, as the client expects"
    assert on_disk(root, A_KEY)["layout"]["magnetsHeld"] == [mid]
    A.remove_magnet(root, A_KEY, mid, {})
    assert "magnets" not in wire(root, A_KEY)
    assert "magnetsHeld" not in on_disk(root, A_KEY)["layout"]
    assert M.read(root, mid) is not None
    assert mid in A.magnet_zones(wire(root, B_KEY)), "the other placement stays"


def refused_and_unchanged(root, mid):
    """Delete says no, and neither the definition nor any arrangement changed."""
    folder = arrangement_path(root, "x").parent
    before = digests(folder), definition_path(root, mid).read_bytes()
    with pytest.raises(A.Declined, match="still place or hold") as exc:
        A.delete_definition(root, mid)
    assert exc.value.reason["code"] == "state"
    assert (digests(folder), definition_path(root, mid).read_bytes()) == before


def test_delete_waits_for_every_placement_and_every_hold(root):
    mid = made(root)["magnet"]["id"]
    place(root, B_KEY, mid)
    refused_and_unchanged(root, mid)
    take_out(root, A_KEY, mid)
    refused_and_unchanged(root, mid)
    take_out(root, B_KEY, mid)
    assert [r["held"] for r in M.references(root, mid)] == [True, True]
    refused_and_unchanged(root, mid)
    assert on_disk(root, A_KEY)["layout"]["magnetsHeld"] == [mid], "still held"

    A.remove_magnet(root, A_KEY, mid, {})
    refused_and_unchanged(root, mid)
    A.remove_magnet(root, B_KEY, mid, {})
    assert M.references(root, mid) == []
    assert A.delete_definition(root, mid) == {"magnet": mid, "deleted": True}
    assert definition_path(root, mid).exists() is False
    assert A.lift_all(root)["lifted"] == 0
    assert M.read(root, mid) is None
    assert A.delete_definition(root, mid)["deleted"] is False


def test_a_hold_refused_a_delete_so_undo_still_finds_its_definition(root):
    made_ = made(root)
    mid = made_["magnet"]["id"]
    take_out(root, A_KEY, mid)
    refused_and_unchanged(root, mid)
    back = A.create_magnet(root, A_KEY, {"id": mid, "attach": attach()})
    assert back["magnet"] == made_["magnet"]


def test_a_copy_still_embedded_refuses_a_delete_until_it_is_removed(root):
    c = {**seed(), "id": "mag-old"}
    other = {**seed(), "id": "mag-other"}
    put(root, A_KEY, layout(magnets={"mag-old": c, "mag-other": other}))
    A.lift_all(root)
    refused_and_unchanged(root, "mag-old")
    assert set(on_disk(root, A_KEY)["layout"]["magnets"]) == {"mag-old", "mag-other"}

    A.remove_magnet(root, A_KEY, "mag-old", {})
    assert A.delete_definition(root, "mag-old")["deleted"] is True
    assert A.lift_all(root)["lifted"] == 0
    assert M.read(root, "mag-old") is None
    assert set(wire(root, A_KEY)["magnets"]) == {"mag-other"}


@pytest.mark.parametrize("damage", ["unreadable", "gone"])
def test_a_hold_with_no_usable_definition_can_still_be_ended(root, damage):
    mid = made(root)["magnet"]["id"]
    take_out(root, A_KEY, mid)
    path = definition_path(root, mid)
    if damage == "gone":
        path.unlink()
    else:
        path.write_text("{nope", encoding="utf-8")
    assert M.references(root, mid)[0]["held"] is True
    with pytest.raises(A.Declined, match="still place or hold"):
        A.delete_definition(root, mid)
    assert A.remove_magnet(root, A_KEY, mid, {})["removed"] is True
    assert M.references(root, mid) == []
    assert A.delete_definition(root, mid)["deleted"] is (damage != "gone")


def test_delete_refuses_when_an_arrangement_cannot_be_read(root):
    mid = made(root)["magnet"]["id"]
    take_out(root, A_KEY, mid)
    arrangement_path(root, B_KEY).write_text("{nope", encoding="utf-8")
    with pytest.raises(A.Unreadable, match="nothing|could not"):
        A.delete_definition(root, mid)
    assert M.read(root, mid) is not None


def test_references_says_what_refers_and_extends_to_held_and_embedded(root):
    mid = made(root)["magnet"]["id"]
    place(root, B_KEY, mid)
    assert M.references(root, mid) == [
        {"arrangement": A_KEY, "placed": True, "held": False},
        {"arrangement": B_KEY, "placed": True, "held": False}]
    take_out(root, A_KEY, mid)
    assert M.references(root, mid)[0] == {"arrangement": A_KEY, "placed": False,
                                          "held": True}
    assert M.references(root, "mag-nobody") == []
    put(root, "ent-c", layout(magnets={"mag-old": {**seed(), "id": "mag-old"}}))
    assert M.references(root, "mag-old") == [
        {"arrangement": "ent-c", "placed": False, "held": True}]
    with pytest.raises(A.Refused):
        M.references(root, "../x")


# -- undo and redo, by fixed id --------------------------------------------------------

def test_undo_places_the_kept_definition_and_never_rolls_it_back(root):
    made_ = made(root)
    mid, first = made_["magnet"]["id"], made_["magnet"]
    place(root, B_KEY, mid)
    take_out(root, A_KEY, mid)
    A.remove_magnet(root, A_KEY, mid, {})
    A.reconfigure_magnet(root, B_KEY, mid,
                         {"change": {"presentation": {"renderer": "cards"}}})
    back = A.create_magnet(root, A_KEY, {
        "id": mid, "attach": attach(),
        "seed": {k: v for k, v in first.items() if k != "id"}})
    assert back["magnet"]["presentation"] == {"renderer": "cards"}
    assert mid in A.magnet_zones(back["layout"])


def test_redo_after_a_delete_recreates_under_the_same_id(root):
    made_ = made(root, seed=seed(ai={"mode": "local", "model": "m"}))
    mid, cfg = made_["magnet"]["id"], made_["magnet"]
    M.set_conversation(root, mid, "ent-own")
    cfg = M.read(root, mid)
    take_out(root, A_KEY, mid)
    A.remove_magnet(root, A_KEY, mid, {})
    A.delete_definition(root, mid)
    again = A.create_magnet(root, A_KEY, {
        "id": mid, "attach": attach(),
        "seed": {k: v for k, v in cfg.items() if k != "id"}})
    assert again["magnet"] == cfg, "its facets and its Conversation come back"


def test_a_magnet_zone_in_an_older_arrangement_is_not_a_reference(root):
    old = {"format": A.FORMAT, "version": 2, "tree": {
        "type": "zone", "id": "z1", "show": "magnet"}}
    assert A.save(root, A_KEY, {"layout": old})["layout"]["version"] == 2
    assert M.references(root, "mag-z1") == []


def test_placing_needs_a_seed_where_nothing_is_kept(root):
    put(root, A_KEY, layout())
    with pytest.raises(A.Refused, match="seed"):
        A.create_magnet(root, A_KEY, {"id": "mag-none", "attach": attach()})
    with pytest.raises(A.Refused, match="seed"):
        A.create_magnet(root, A_KEY, {"attach": attach()})


def test_a_definition_gone_from_under_a_zone_blocks_no_save_and_recovers(root):
    mid = made(root)["magnet"]["id"]
    definition_path(root, mid).unlink()
    shown = wire(root, A_KEY)
    assert mid in A.magnet_zones(shown) and "magnets" not in shown
    assert A.save(root, A_KEY, {"scope": "compact", "presentation": None})
    with pytest.raises(A.Declined, match="missing"):
        A.reconfigure_magnet(root, A_KEY, mid,
                             {"change": {"presentation": {"renderer": "list"}}})
    with pytest.raises(A.Refused, match="not in this arrangement"):
        A.save(root, A_KEY, {"sharedZone": {"op": "add", "zone": {
            "type": "zone", "id": "mag-new", "show": "magnet",
            "options": {"magnet": "mag-new"}}}})


# -- the schema ------------------------------------------------------------------------

EVERY_FACET = {
    "activation": {"mode": "scheduled", "schedule": "PT1H"},
    "processing": {"operations": [
        {"op": "extract", "name": "dates", "options": {"field": "when", "max": 3}},
        {"op": "change-detect"}, {"op": "other", "name": "custom"}]},
    "ai": {"mode": "runtime", "runtime": "claude", "model": "opus"},
    "outputs": ["findings", "proposals", "work"],
    "destinations": [{"kind": "magnet-conversation"},
                     {"kind": "workflow", "ref": "ent-wf"}],
    "presentation": {"renderer": "cards", "theme": "glass"},
    "sources": [{"kind": "agent-results", "conversation": "ent-1", "runtime": "codex"},
                {"kind": "agent-results"},
                {"kind": "file", "collection": "col-1", "path": "docs/a.md"},
                {"kind": "database", "collection": "col-2", "table": "t"},
                {"kind": "brain", "brain": "b-1"},
                {"kind": "conversation", "conversation": "ent-1"},
                {"kind": "connector", "connector": "slack", "location": "#a"},
                {"kind": "web", "domain": "example.com"},
                {"kind": "other", "type": "rss", "ref": "feed:1"}],
}


def test_every_facet_round_trips_through_a_definition_and_the_wire(root):
    mid = made(root, seed=seed(**EVERY_FACET))["magnet"]["id"]
    for k, v in EVERY_FACET.items():
        assert M.read(root, mid)[k] == v
        assert wire(root, A_KEY)["magnets"][mid][k] == v
    file = json.loads(definition_path(root, mid).read_text(encoding="utf-8"))
    assert file["schema_version"] == S.SCHEMA_VERSION
    assert "schema_version" not in wire(root, A_KEY)["magnets"][mid]
    change = {"ai": {"mode": "agent", "agent": "ent-who"},
              "activation": {"mode": "condition", "condition": "new evidence"}}
    got = A.reconfigure_magnet(root, A_KEY, mid, {"change": change})["magnet"]
    assert got["ai"] == change["ai"] and got["outputs"] == EVERY_FACET["outputs"]


def test_a_definition_from_before_reads_exactly_as_it_did():
    old = {**seed(), "id": "mag-old"}
    assert S.magnet_config(copy.deepcopy(old)) == old, "nothing is defaulted in"


@pytest.mark.parametrize("over, words", [
    ({"activation": {"mode": "sometimes"}}, "sometimes"),
    ({"activation": {"mode": "scheduled"}}, "schedule"),
    ({"activation": {"mode": "manual", "event": "x"}}, "only 'event'"),
    ({"activation": {"mode": "event", "event": "x" * 2001}}, "event"),
    ({"processing": {"operations": [{"op": "guess"}]}}, "guess"),
    ({"processing": {"operations": [{"op": "extract"}] * 21}}, "at most 20"),
    ({"processing": {"operations": [{"op": "extract", "options": {"a": [1]}}]}}, "text, a number"),
    ({"processing": {"steps": []}}, "'steps'"),
    ({"ai": {"mode": "always"}}, "always"),
    ({"ai": {"mode": "none", "model": "m"}}, "no AI"),
    ({"outputs": ["rumours"]}, "rumours"),
    ({"outputs": ["findings", "findings"]}, "once"),
    ({"destinations": [{"kind": "email"}]}, "email"),
    ({"destinations": [{"kind": "brain", "x": 1}]}, "'x'"),
    ({"presentation": {"renderer": "disc", "theme": "neon"}}, "neon"),
    ({"sources": [{"kind": "file"}]}, "'collection' is missing"),
    ({"sources": [{"kind": "database", "collection": "c", "sql": "x"}]}, "'sql'"),
    ({"mood": 1}, "'mood'"),
    ({"sources": [{"kind": "conversation", "conversation": "ent-src"}] * 2}, "each source once"),
])
def test_a_bad_new_facet_is_refused(over, words):
    with pytest.raises(A.Refused, match=words):
        S.magnet_config({**seed(), "id": "mag-bad", **over})


def test_a_reconfigure_cannot_set_a_magnets_own_fields(root):
    mid = made(root)["magnet"]["id"]
    for own in ({"conversation": "ent-1"}, {"schema_version": 1}):
        with pytest.raises(A.Refused, match=next(iter(own))):
            A.reconfigure_magnet(root, A_KEY, mid, {"change": own})


@pytest.mark.parametrize("bad", [
    '{"nope"', "[]", json.dumps({"id": "mag-x"}),
    json.dumps({**seed(), "id": "mag-other"}),
    json.dumps({**seed(), "id": "mag-x", "schema_version": S.SCHEMA_VERSION + 1}),
    json.dumps({**seed(), "id": "mag-x", "schema_version": "1"}),
])
def test_a_definition_that_cannot_be_read_is_said_never_defaulted_or_replaced(root, bad):
    put(root, A_KEY, layout(tree={"type": "zone", "id": "mag-x", "show": "magnet",
                                  "options": {"magnet": "mag-x"}},
                            magnets={"mag-x": {**seed(), "id": "mag-x"}}))
    path = definition_path(root, "mag-x")
    path.parent.mkdir(parents=True)
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(M.Unreadable):
        M.read(root, "mag-x")
    got = A.arrangement(root, A_KEY)
    assert set(got["magnets_unreadable"]) == {"mag-x"}
    assert "mag-x" in A.magnet_zones(got["layout"]), "the rest is still answered"
    with pytest.raises(M.Unreadable):
        A.reconfigure_magnet(root, A_KEY, "mag-x",
                             {"change": {"presentation": {"renderer": "list"}}})
    assert path.read_text(encoding="utf-8") == bad


# -- the shapes Python, Rust and the client share ----------------------------------------

CONFORMANCE = pathlib.Path(__file__).parent / "fixtures" / "magnet-conformance"


def test_definitions_read_here_as_rust_reads_them(root):
    all_of = json.loads((CONFORMANCE / "definitions.json").read_text(encoding="utf-8"))
    for d in all_of["readable"]:
        path = definition_path(root, d["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d), encoding="utf-8")
        got = M.read(root, d["id"])
        assert got == {k: v for k, v in d.items() if k != "schema_version"}
    for d in all_of["later_schema"]:
        path = definition_path(root, d["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d), encoding="utf-8")
        with pytest.raises(M.Unreadable):
            M.read(root, d["id"])


def test_every_source_kind_the_client_knows_is_one_here():
    rows = json.loads((CONFORMANCE / "source_keys.json").read_text(encoding="utf-8"))
    assert {r["source"]["kind"] for r in rows} == set(S.SOURCE_KINDS)
    for r in rows:
        assert S.magnet_config({**seed(sources=[r["source"]]), "id": "mag-k"})["sources"] == [r["source"]]
        assert S.source_key(r["source"]) == r["key"]


def repeated():
    all_of = json.loads((CONFORMANCE / "definitions.json").read_text(encoding="utf-8"))
    return all_of["repeated_sources"]


def test_a_source_named_twice_is_refused_everywhere_a_definition_is_made(root):
    for d in repeated():
        path = definition_path(root, d["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d), encoding="utf-8")
        with pytest.raises(M.Unreadable, match="each source once"):
            M.read(root, d["id"])
        path.unlink()

        with pytest.raises(A.Refused, match="each source once"):
            made(root, seed=seed(sources=d["sources"]))
        mid = made(root)["magnet"]["id"]
        before = M.read(root, mid)
        with pytest.raises(A.Refused, match="each source once"):
            A.reconfigure_magnet(root, A_KEY, mid, {"change": {"sources": d["sources"]}})
        assert M.read(root, mid) == before
        take_out(root, A_KEY, mid)


def test_an_arrangement_already_embedding_a_repeat_stays_readable(root):
    same, merged = repeated()
    put_raw = {"key": A_KEY, "saved": 1.0, "ops": [], "layout": {
        **layout(), "magnets": {same["id"]: same, merged["id"]: merged}}}
    W._atomic(arrangement_path(root, A_KEY), put_raw)
    raw = arrangement_path(root, A_KEY).read_bytes()

    shown = A.arrangement(root, A_KEY)
    assert "unreadable" not in shown
    assert shown["layout"]["magnets"][same["id"]]["sources"] == same["sources"][:1]
    assert shown["layout"]["magnets"][merged["id"]]["sources"] == merged["sources"][:1]
    assert arrangement_path(root, A_KEY).read_bytes() == raw, "a read rewrites nothing"

    assert A.lift_all(root)["lifted"] == 2
    assert M.read(root, same["id"])["sources"] == same["sources"][:1]
    assert M.read(root, merged["id"])["sources"] == merged["sources"][:1]
    same_beside = definition_path(root, same["id"]).with_name(f"{same['id']}.from-{A_KEY}.json")
    assert not same_beside.exists(), "a true repeat loses nothing"
    beside = definition_path(root, merged["id"]).with_name(f"{merged['id']}.from-{A_KEY}.json")
    assert json.loads(beside.read_text(encoding="utf-8")) == merged, "different sources aren't lost"
    assert A.lift_all(root)["lifted"] == 0
    assert A.save(root, A_KEY, {"scope": "compact", "presentation": None})
    assert "magnets" not in on_disk(root, A_KEY)["layout"]
    assert wire(root, A_KEY)["magnets"][same["id"]]["sources"] == same["sources"][:1]


def test_the_answers_the_client_is_tested_on_keep_their_sources_well_formed():
    for name in ("summary_answer.json", "page_answer.json"):
        answer = json.loads((CONFORMANCE / name).read_text(encoding="utf-8"))
        for one in answer["sources"]:
            assert S.magnet_config({**seed(sources=[one["source"]]), "id": "mag-k"})
            assert one["status"] in ("ok", "partial", "unavailable", "busy")


# -- a Magnet's own Conversation -------------------------------------------------------

def test_lifting_creates_no_conversation_and_the_field_is_not_a_source(fluid_dev):
    A.lift_all(fluid_dev)
    for mid, held in embedded().items():
        got = M.read(fluid_dev, mid)
        assert "conversation" not in got
        assert got["sources"] == held[0][1]["sources"]


def test_a_new_seed_names_no_conversation(root):
    put(root, A_KEY, layout())
    with pytest.raises(A.Refused, match="asked for"):
        made(root, seed=seed(conversation="ent-someone"))


def test_set_conversation_keeps_the_first_and_leaves_sources_alone(root):
    mid = made(root)["magnet"]["id"]
    before = M.read(root, mid)
    M.set_conversation(root, mid, "ent-own")
    assert M.set_conversation(root, mid, "ent-other")["conversation"] == "ent-own"
    assert M.read(root, mid) == {**before, "conversation": "ent-own"}
    with pytest.raises(A.Declined, match="missing"):
        M.set_conversation(root, "mag-none", "ent-own")


def _read_while_replacing(path, read, replace, monkeypatch):
    """Model Windows refusing a replace while its destination is being read."""
    reading = threading.Event()
    release = threading.Event()
    errors = []
    real_read = pathlib.Path.read_text
    real_replace = os.replace
    target = path.resolve()

    def held_read(self, *args, **kwargs):
        text = real_read(self, *args, **kwargs)
        if (threading.current_thread().name == "held-reader"
                and self.resolve() == target):
            reading.set()
            if not release.wait(2):
                raise TimeoutError("the test did not release the held read")
        return text

    def windows_replace(source, destination):
        if pathlib.Path(destination).resolve() == target \
                and reading.is_set() and not release.is_set():
            raise PermissionError(13, "destination is open by a reader")
        return real_replace(source, destination)

    def run(fn):
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 - carried to the test thread
            errors.append(exc)

    monkeypatch.setattr(pathlib.Path, "read_text", held_read)
    monkeypatch.setattr(os, "replace", windows_replace)
    reader = threading.Thread(target=lambda: run(read), name="held-reader")
    writer = threading.Thread(target=lambda: run(replace), name="writer")
    reader.start()
    assert reading.wait(2), "the reader never held the destination"
    writer.start()
    writer.join(.1)
    assert writer.is_alive(), "the writer reached os.replace during the read"
    release.set()
    reader.join(2)
    writer.join(2)
    assert not reader.is_alive() and not writer.is_alive()
    assert errors == []


def test_a_magnet_read_and_definition_replacement_share_the_lock(root, monkeypatch):
    mid = made(root)["magnet"]["id"]
    _read_while_replacing(
        definition_path(root, mid),
        lambda: M.read(root, mid),
        lambda: M.set_conversation(root, mid, "ent-own"),
        monkeypatch)
    assert M.read(root, mid)["conversation"] == "ent-own"


def test_an_arrangement_read_and_replacement_share_the_lock(root, monkeypatch):
    put(root, A_KEY, layout())
    _read_while_replacing(
        arrangement_path(root, A_KEY),
        lambda: A.arrangement(root, A_KEY),
        lambda: A.save(root, A_KEY, {"layout": layout()}),
        monkeypatch)


def test_correct_conversation_replaces_what_differs_and_leaves_sources_alone(root):
    mid = made(root)["magnet"]["id"]
    before = M.read(root, mid)
    assert M.correct_conversation(root, mid, "ent-own")["conversation"] == "ent-own"
    M.set_conversation(root, mid, "ent-other")
    assert M.correct_conversation(root, mid, "ent-right")["conversation"] == "ent-right"
    assert M.read(root, mid) == {**before, "conversation": "ent-right"}
    with pytest.raises(A.Declined, match="missing"):
        M.correct_conversation(root, "mag-none", "ent-own")


def _post(world, path, body):
    req = urllib.request.Request(
        world["base"] + "/fluid/api/" + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1"},
        method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _api_post(world, path, body):
    req = urllib.request.Request(
        world["base"] + "/api/" + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1"},
        method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _people(world):
    req = urllib.request.Request(world["base"] + "/fluid/api/participants",
                                 headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _two_authors(world):
    authors = [p["id"] for p in _people(world)["participants"]]
    assert len(authors) >= 2
    return authors[:2]


def test_the_routes_through_the_fluid_api(world):  # noqa: F811
    status, got = _post(world, "arrangements/home/magnets",
                        {"seed": seed(), "attach": {**attach(), "base": layout(version=2)}})
    assert status == 200, got
    mid = got["magnet"]["id"]
    assert "conversation" not in got["magnet"]

    status, got = _post(world, f"magnets/{mid}/delete", {})
    assert status == 422 and got["reason"]["code"] == "state"

    status, got = _post(world, "magnets/lift", {})
    assert status == 200 and got["lifted"] == 0

    status, got = _post(world, "magnets/mag-none/conversation", {})
    assert status == 422 and got["reason"]["code"] == "state"

    status, got = _post(world, f"magnets/{mid}/conversation", {"name": "Board's own"})
    assert status == 400, "the same authority as any other: it needs an author"

    author = world.get("author") or _people(world)["participants"][0]["id"]
    status, got = _post(world, f"magnets/{mid}/conversation",
                        {"author": author, "name": "Board's own", "op": "op-c1"})
    assert status == 201 and got["created"] is True, got
    own = got["conversation"]
    assert M.read(world["root"], mid)["conversation"] == own

    status, got = _post(world, f"magnets/{mid}/conversation",
                        {"author": author, "name": "Another", "op": "op-c2"})
    assert (status, got["created"], got["conversation"]) == (200, False, own)

    status, got = _post(world, "arrangements/home",
                        {"sharedZone": {"op": "remove", "id": mid}})
    assert status == 200
    status, got = _post(world, f"magnets/{mid}/delete", {})
    assert status == 422 and got["reason"]["code"] == "state", "still held"
    status, got = _post(world, f"arrangements/home/magnets/{mid}/remove", {})
    assert status == 200 and got["removed"] is True
    status, got = _post(world, f"magnets/{mid}/delete", {})
    assert status == 200 and got["deleted"] is True


def test_a_failed_definition_replace_retries_the_same_conversation(
        world, monkeypatch):  # noqa: F811
    status, got = _post(world, "arrangements/home/magnets",
                        {"seed": seed(), "attach": {**attach(),
                                                     "base": layout(version=2)}})
    assert status == 200, got
    mid = got["magnet"]["id"]
    author = world.get("author") or _people(world)["participants"][0]["id"]
    real_set = M.set_conversation
    attempted = []

    def fail_first(root, asked_mid, conversation):
        attempted.append(conversation)
        if len(attempted) == 1:
            raise PermissionError(13, "destination is open")
        return real_set(root, asked_mid, conversation)

    monkeypatch.setattr(M, "set_conversation", fail_first)
    body = {"author": author, "name": "Board's own"}
    status, failed = _post(world, f"magnets/{mid}/conversation", body)
    assert status == 500 and failed["kind"] == "PermissionError"
    assert M.read(world["root"], mid).get("conversation") is None

    status, retried = _post(world, f"magnets/{mid}/conversation",
                            {**body, "name": "A later retry's name"})
    # The claim committed with the key, so the record answers and repairs the file.
    assert status == 200 and retried["created"] is False, retried
    assert attempted == [retried["conversation"]]
    assert M.read(world["root"], mid)["conversation"] == retried["conversation"]


def test_a_different_author_retries_the_committed_conversation(
        world, monkeypatch):  # noqa: F811
    status, got = _post(world, "arrangements/home/magnets",
                        {"seed": seed(), "attach": {**attach(),
                                                     "base": layout(version=2)}})
    assert status == 200, got
    mid = got["magnet"]["id"]
    first_author, retrying_author = _two_authors(world)
    real_set = M.set_conversation
    attempted = []

    def fail_first(root, asked_mid, conversation):
        attempted.append(conversation)
        if len(attempted) == 1:
            raise PermissionError(13, "destination is open")
        return real_set(root, asked_mid, conversation)

    monkeypatch.setattr(M, "set_conversation", fail_first)
    status, failed = _post(world, f"magnets/{mid}/conversation",
                           {"author": first_author, "name": "First name"})
    assert status == 500 and failed["kind"] == "PermissionError"
    assert M.read(world["root"], mid).get("conversation") is None

    status, retried = _post(world, f"magnets/{mid}/conversation",
                            {"author": retrying_author,
                             "name": "Different author's retry"})
    # The claim committed with the key, so the record answers and repairs the file.
    assert status == 200 and retried["created"] is False, retried
    assert attempted == [retried["conversation"]]
    assert M.read(world["root"], mid)["conversation"] == retried["conversation"]


def test_plain_conversation_open_reserves_the_magnet_key_prefix(world):  # noqa: F811
    author = _two_authors(world)[0]
    status, got = _post(world, "conversations",
                        {"author": author, "name": "Squat",
                         "op": "magnet-conversation:mag-squat"})
    assert status == 400
    assert "magnet-conversation:" in got["error"]
    assert "reserved" in got["error"].lower()


@pytest.mark.parametrize("door", [
    "name", "posts", "topics", "participants", "reactions", "comments",
    "deep-dives",
])
def test_other_keyed_doors_do_not_reserve_a_magnet_conversation_key(
        world, door):  # noqa: F811
    status, got = _post(world, "arrangements/home/magnets",
                        {"seed": seed(), "attach": {**attach(),
                                                     "base": layout(version=2)}})
    assert status == 200, got
    mid = got["magnet"]["id"]
    first_author, second_author = _two_authors(world)
    key = f"magnet-conversation:{mid}"

    status, got = _post(world, "conversations",
                        {"author": first_author, "name": "Elsewhere"})
    assert status == 201, got
    elsewhere = got["conversation"]
    if door == "name":
        door_result = _post(
            world, f"conversations/{elsewhere}/name",
            {"author": first_author, "name": "Squat", "op": key})
    elif door == "posts":
        door_result = _post(
            world, "posts", {"author": first_author,
                              "conversation": elsewhere, "text": "squat",
                              "action": "record-only", "op": key})
    elif door in ("topics", "participants"):
        door_result = _api_post(
            world, f"conversations/{elsewhere}/{door}",
            {"author": first_author, "name": "Squat", "alias": "@Squat",
             "op": key})
    else:
        status, post = _post(
            world, "posts", {"author": first_author,
                              "conversation": elsewhere, "text": "target",
                              "action": "record-only"})
        assert status == 200, post
        turn = post.get("turn") or post.get("id") or post.get("post")
        extra = {"reactions": {"token": "ok"},
                 "comments": {"text": "squat"},
                 "deep-dives": {"why": "squat"}}[door]
        door_result = _post(
            world, f"posts/{turn}/{door}",
            {"by": first_author, "author": first_author, "op": key,
             **extra})
    assert door_result[0] == 200, door_result[1]

    first = _post(world, f"magnets/{mid}/conversation",
                  {"author": first_author, "name": "Magnet"})
    second = _post(world, f"magnets/{mid}/conversation",
                   {"author": second_author, "name": "Ignored"})
    assert first[0] == 201, first[1]
    assert second[0] == 200, second[1]
    assert second[1]["conversation"] == first[1]["conversation"]


def test_ordinary_operation_keys_remain_per_author(world):  # noqa: F811
    first_author, second_author = _two_authors(world)
    body = {"name": "Per-author", "op": "ordinary-key"}
    first = _post(world, "conversations", {"author": first_author, **body})
    second = _post(world, "conversations", {"author": second_author, **body})
    first_retry = _post(world, "conversations",
                        {"author": first_author, **body})
    second_mismatch = _post(
        world, "conversations",
        {"author": second_author, "name": "Different", "op": body["op"]})

    assert (first[0], second[0], first_retry[0], second_mismatch[0]) == (
        201, 201, 200, 422)
    assert first[1]["conversation"] != second[1]["conversation"]
    assert first_retry[1]["conversation"] == first[1]["conversation"]


def test_recreated_magnet_recovers_its_conversation_for_every_author(
        world):  # noqa: F811
    status, got = _post(world, "arrangements/home/magnets",
                        {"seed": seed(), "attach": {**attach(),
                                                     "base": layout(version=2)}})
    assert status == 200, got
    mid = got["magnet"]["id"]
    first_author, recovering_author = _two_authors(world)
    status, opened = _post(world, f"magnets/{mid}/conversation",
                           {"author": first_author, "name": "Original"})
    assert status == 201, opened
    original = opened["conversation"]

    status, got = _post(world, "arrangements/home",
                        {"sharedZone": {"op": "remove", "id": mid}})
    assert status == 200, got
    status, got = _post(world, f"arrangements/home/magnets/{mid}/remove", {})
    assert status == 200 and got["removed"] is True, got
    status, got = _post(world, f"magnets/{mid}/delete", {})
    assert status == 200 and got["deleted"] is True, got
    status, got = _post(world, "arrangements/home/magnets",
                        {"id": mid, "seed": seed(), "attach": attach()})
    assert status == 200 and got["magnet"]["id"] == mid, got
    assert M.read(world["root"], mid).get("conversation") is None

    status, recovered = _post(world, f"magnets/{mid}/conversation",
                              {"author": recovering_author,
                               "name": "Replacement name"})
    assert status == 200 and recovered["created"] is False, recovered
    assert recovered["conversation"] == original
    assert M.read(world["root"], mid)["conversation"] == original
