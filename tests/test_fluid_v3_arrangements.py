"""Arrangement v3, the universal Magnet's configuration storage and the three
kinds of save (Surface Tension P2, plan §3.7 and §3.10).

Every test works on a fixture corpus in `tmp_path` (or the `world` fixture's):
no live Brain is opened."""
import copy
import json
import pathlib
import urllib.error
import urllib.request

import pytest

from mentis.fluid import _checks as W
from mentis.fluid import arrangements as A
from tests._loop import world  # noqa: F401

KEY = "home"


# -- fixtures ------------------------------------------------------------------------

def zone(zid, **extra):
    return {"type": "zone", "id": zid, "show": "objects",
            "slot": {"follow": True, "show": "objects", "items": [],
                     "present": "cards"}, **extra}


def mzone(mid, **extra):
    return {"type": "zone", "id": mid, "show": "magnet",
            "options": {"magnet": mid}, **extra}


def row(*kids):
    return {"type": "split", "dir": "row",
            "sizes": [1 / len(kids)] * len(kids), "kids": list(kids)}


def seed(**over):
    s = {"sources": [{"kind": "conversation", "conversation": "conv-1"}],
         "selection": {"informationTypes": ["post", "image"]},
         "collection": {"mode": "one-time"},
         "synthesis": {"mode": "manual"},
         "notifications": {"newItems": True, "changes": False,
                           "failures": False},
         "presentation": {"renderer": "cards"}}
    s.update(over)
    return s


def config(mid, **over):
    return {"id": mid, **seed(**over)}


def v3(tree=None, **extra):
    return {"format": A.FORMAT, "version": 3, "tree": tree or zone("stage"),
            **extra}


def v2(tree=None, **extra):
    return {"format": A.FORMAT, "version": 2, "tree": tree or zone("stage"),
            **extra}


def dp(order=(), place=None, level=None, at=1):
    return {"order": list(order), "place": dict(place or {}),
            "level": dict(level or {}), "updatedAt": at}


def fl(fid, z, n=0, **extra):
    return {"id": fid, "zone": z, "x": 10 + n, "y": 20 + n, "w": 300,
            "h": 200, **extra}


@pytest.fixture()
def root(tmp_path):
    return str(tmp_path / "corpus")


def path_of(root, key=KEY):
    return pathlib.Path(root) / "presentation" / A.FOLDER / f"{key}.json"


def put(root, layout, key=KEY):
    """A stored arrangement, written as the store writes one (checked)."""
    W._atomic(path_of(root, key), {"key": key, "layout": A.check(layout),
                                   "saved": 1.0, "ops": []})


def stored(root, key=KEY):
    return A.arrangement(root, key)["layout"]


def full(root, layout, op=None, key=KEY):
    body = {"layout": layout}
    if op:
        body["op"] = op
    return A.save(root, key, body)


def all_ids(n):
    return [z["id"] for z in A._leaves(n)]


# -- versions --------------------------------------------------------------------------

def test_v1_and_v2_files_read_and_save_byte_identically(root):
    for version in (1, 2):
        raw = {"format": A.FORMAT, "version": version,
               "tree": row(zone("z1"), zone("z2", fit=True)),
               "conversation": {"width": 480}}
        if version == 2:
            raw["focus"] = {"floats": [fl("w1", zone("f1"), min=True)]}
        saved = full(root, copy.deepcopy(raw))
        assert saved["layout"] == raw
        before = path_of(root).read_bytes()
        assert stored(root) == raw
        assert path_of(root).read_bytes() == before
        assert stored(root)["version"] == version


def test_v3_round_trips_presentations_spatial_and_zone_level(root):
    raw = v3(tree=row(zone("a", level="compact"), zone("b")),
             focus={"floats": [fl("w1", zone("f1", level="icon"))]},
             presentations={"medium": dp(["a", "b"], {"a": "dock", "b": "stack"},
                                         {"a": "expanded"}, 17),
                            "compact": dp(["b"], {"b": "sheet", "gone": "launcher"},
                                          {}, 18)},
             spatial={"makeRoom": "drag"})
    assert A.check(raw) == raw
    saved = full(root, copy.deepcopy(raw))["layout"]
    assert saved == {k: v for k, v in raw.items() if k != "presentations"}
    assert stored(root) == saved


@pytest.mark.parametrize("bad, words", [
    ({"bogus": 1}, "has no 'bogus'"),
    ({"presentations": {"wide": dp()}}, "presentations: 'wide'"),
    ({"presentations": {"medium": {**dp(), "extra": 1}}}, "'extra'"),
    ({"presentations": {"medium": {"order": [], "place": {}, "level": {}}}},
     "'updatedAt' is missing"),
    ({"presentations": {"medium": dp(["a", "a"])}}, "each id once"),
    ({"presentations": {"medium": dp(place={"a": "floating"})}}, "floating"),
    ({"presentations": {"medium": dp(level={"a": "huge"})}}, "huge"),
    ({"spatial": {"makeRoom": "drag", "snap": True}}, "'snap'"),
    ({"spatial": {"makeRoom": "always"}}, "always"),
    ({"spatial": {}}, "'makeRoom' is missing"),
])
def test_unknown_v3_keys_and_values_are_refused(bad, words):
    with pytest.raises(A.Refused, match=words):
        A.check(v3(**bad))


def test_zone_level_is_checked_in_v3():
    with pytest.raises(A.Refused, match="level"):
        A.check(v3(tree=zone("a", level="workspace")))


def test_dock_is_refused_under_compact_and_kept_under_medium():
    with pytest.raises(A.Refused, match="dock"):
        A.check(v3(presentations={"compact": dp(["a"], {"a": "dock"})}))
    ok = v3(presentations={"medium": dp(["a"], {"a": "dock"})})
    assert A.check(ok) == ok


def test_a_thirteenth_float_is_refused_in_v3():
    floats = [fl(f"w{i}", zone(f"f{i}"), i) for i in range(13)]
    with pytest.raises(A.Refused, match="at most 12 floats"):
        A.check(v3(focus={"floats": floats}))
    assert A.check(v3(focus={"floats": floats[:12]}))


def test_a_v3_field_in_a_v2_document_is_dropped_as_today():
    raw = v2(tree=zone("a", level="icon"),
             presentations={"medium": dp()}, spatial={"makeRoom": "drag"},
             magnets={"mag-1": config("mag-1")}, bogus=True)
    got = A.check(raw)
    assert got == v2(tree=zone("a"))


# -- full saves -------------------------------------------------------------------------

def test_full_save_keeps_all_stored_class_records_and_ignores_incoming(root):
    put(root, v3(presentations={"compact": dp(["stage"], {"stage": "sheet"}),
                                "medium": dp(["stage"], {"stage": "stack"})}))
    got = full(root, v3(tree=zone("stage", level="expanded"),
                        presentations={"medium": dp([], at=99)}))
    assert got["layout"]["presentations"]["compact"] == dp(["stage"], {"stage": "sheet"})
    assert got["layout"]["presentations"]["medium"] == dp(["stage"], {"stage": "stack"})
    assert stored(root)["tree"]["level"] == "expanded"


def test_full_and_scoped_saves_preserve_the_stored_magnets_map(root):
    kept = {"mag-a": config("mag-a", presentation={"renderer": "ring"})}
    put(root, v3(tree=row(zone("stage"), mzone("mag-a")), magnets=kept))
    stale = {"mag-a": config("mag-a"), "mag-z": config("mag-z")}
    got = full(root, v3(tree=row(zone("stage"), mzone("mag-a")), magnets=stale))
    assert got["layout"]["magnets"] == kept
    got = full(root, v3(tree=row(zone("stage"), mzone("mag-a"))))
    assert got["layout"]["magnets"] == kept
    with pytest.raises(A.Refused, match="'magnets'"):
        A.save(root, KEY, {"scope": "compact", "presentation": None,
                           "magnets": stale})
    got = A.save(root, KEY, {"scope": "compact",
                             "presentation": dp(["mag-a"], {"mag-a": "stack"})})
    assert got["layout"]["magnets"] == kept
    assert stored(root)["magnets"] == kept


def test_stale_wide_full_save_against_stored_magnet_zone_membership(root):
    # Stored now: the phone added mag-new beside `notes`, removed mag-old,
    # and both devices know mag-both.
    put(root, v3(tree=row(zone("stage"), zone("notes"), mzone("mag-new"),
                          mzone("mag-both")),
                 focus={"floats": [fl("w-keep", mzone("mag-float"))]},
                 magnets={m: config(m) for m in
                          ("mag-new", "mag-both", "mag-float")}))
    # The desk's stale layout: it never saw mag-new or mag-float, still has
    # mag-old, moved mag-both into a window, and made an unrelated wide edit.
    desk = v3(tree=row(zone("stage", level="expanded"), zone("notes"),
                       mzone("mag-old")),
              focus={"floats": [fl("w-both", mzone("mag-both"), 5)]},
              conversation={"width": 640},
              magnets={m: config(m) for m in ("mag-old", "mag-both")})
    got = full(root, desk)["layout"]
    ids = all_ids(got["tree"])
    assert "mag-new" in ids, "a phone-added zone survives the stale save"
    assert ids.index("mag-new") == ids.index("notes") + 1, "kept where it was stored"
    assert "mag-old" not in ids, "a phone-removed zone is not resurrected"
    assert [f["zone"]["id"] for f in got["focus"]["floats"]] == ["mag-both", "mag-float"]
    assert "mag-both" not in ids, "the save's wide placement wins for a shared id"
    assert got["tree"]["kids"][0]["level"] == "expanded"
    assert got["conversation"] == {"width": 640}, "unrelated wide edits save"
    assert set(got["magnets"]) == {"mag-new", "mag-both", "mag-float"}
    assert stored(root) == got


def test_full_save_ignores_incoming_presentations(root):
    phone = dp(["phone-new"], {"phone-new": "sheet"}, at=200)
    put(root, v3(presentations={"compact": phone}))
    stale = dp(["phone-old"], {"phone-old": "stack"}, at=100)
    got = full(root, v3(tree=zone("desk"),
                        presentations={"compact": stale}))['layout']
    assert got["tree"]["id"] == "desk"
    assert got["presentations"] == {"compact": phone}


def test_v2_full_save_preserves_stored_spatial_and_zone_levels(root):
    put(root, v3(tree=row(zone("stage", level="expanded"),
                          zone("notes", level="icon")),
                 focus={"floats": [fl("w1", zone("float", level="compact"))]},
                 spatial={"makeRoom": "drag"}))
    got = full(root, v2(tree=row(zone("notes"), zone("stage")),
                        focus={"floats": [fl("w1", zone("float"))]}))["layout"]
    assert got["version"] == 3
    assert got["spatial"] == {"makeRoom": "drag"}
    assert {z["id"]: z.get("level") for z in A._leaves(got["tree"])} == {
        "notes": "icon", "stage": "expanded"}
    assert got["focus"]["floats"][0]["zone"]["level"] == "compact"


def test_first_full_save_keeps_no_magnet_zone_without_a_stored_config(root):
    got = full(root, v3(tree=row(zone("stage"), mzone("mag-x")),
                        magnets={"mag-x": config("mag-x")}))["layout"]
    assert all_ids(got["tree"]) == ["stage"]
    assert "magnets" not in got


# -- scoped saves --------------------------------------------------------------------------

def test_scoped_save_changes_only_its_class_and_null_deletes(root):
    put(root, v3(tree=row(zone("stage"), zone("notes", level="icon")),
                 focus={"floats": [fl("w1", zone("f1"))]},
                 spatial={"makeRoom": "expand"},
                 presentations={"medium": dp(["stage"], {"stage": "dock"})}))
    rest = lambda: {k: v for k, v in stored(root).items() if k != "presentations"}  # noqa: E731
    before = json.dumps(rest(), sort_keys=True)
    A.save(root, KEY, {"scope": "compact",
                       "presentation": dp(["notes"], {"notes": "sheet"}, at=5)})
    assert json.dumps(rest(), sort_keys=True) == before
    assert stored(root)["presentations"] == {
        "medium": dp(["stage"], {"stage": "dock"}),
        "compact": dp(["notes"], {"notes": "sheet"}, at=5)}
    A.save(root, KEY, {"scope": "medium", "presentation": None})
    assert json.dumps(rest(), sort_keys=True) == before
    assert set(stored(root)["presentations"]) == {"compact"}
    A.save(root, KEY, {"scope": "compact", "presentation": None})
    assert "presentations" not in stored(root)


def test_scoped_save_refuses_a_wide_snapshot_and_dock_in_compact(root):
    put(root, v3())
    with pytest.raises(A.Refused, match="'layout'"):
        A.save(root, KEY, {"scope": "compact", "presentation": None,
                           "layout": v3()})
    with pytest.raises(A.Refused, match="dock"):
        A.save(root, KEY, {"scope": "compact",
                           "presentation": dp(["stage"], {"stage": "dock"})})


def test_op_replay_for_every_kind_of_save(root):
    put(root, v3())
    a = full(root, v3(tree=zone("stage", level="icon")), op="op-full")
    full(root, v3(tree=zone("stage", level="expanded")))
    again = full(root, v3(tree=zone("stage", level="icon")), op="op-full")
    assert again["replayed"] is True
    assert again["layout"]["tree"]["level"] == "expanded", "a replay never undoes a later save"
    with pytest.raises(A.Conflict):
        full(root, v3(tree=zone("stage", level="compact")), op="op-full")
    assert a["replayed"] is False

    scoped = {"scope": "medium", "presentation": dp(["stage"], {"stage": "stack"}),
              "op": "op-scoped"}
    assert A.save(root, KEY, dict(scoped))["replayed"] is False
    A.save(root, KEY, {"scope": "medium", "presentation": None})
    again = A.save(root, KEY, dict(scoped))
    assert again["replayed"] is True and "presentations" not in again["layout"]
    with pytest.raises(A.Conflict):
        A.save(root, KEY, {**scoped, "presentation": None})

    patch = {"sharedZone": {"op": "add", "zone": zone("extra")}, "op": "op-patch"}
    assert A.save(root, KEY, copy.deepcopy(patch))["replayed"] is False
    again = A.save(root, KEY, copy.deepcopy(patch))
    assert again["replayed"] is True
    floats = again["layout"]["focus"]["floats"]
    assert [f["zone"]["id"] for f in floats] == ["extra"], "added once"


# -- named layouts ---------------------------------------------------------------------------

def test_shape_of_drops_presentations_and_magnets_and_keeps_spatial():
    raw = A.check(v3(tree=row(zone("stage"), mzone("mag-a")),
                     focus={"floats": [fl("w1", mzone("mag-b")),
                                       fl("w2", zone("side"))]},
                     pages=[{"id": "p1", "title": "P",
                             "tree": row(zone("pz"), mzone("mag-c"))}],
                     presentations={"compact": dp(["mag-a"], {"mag-a": "stack"})},
                     spatial={"makeRoom": "drag"},
                     magnets={m: config(m) for m in ("mag-a", "mag-b", "mag-c")}))
    shaped = A.shape_of(raw)
    assert "presentations" not in shaped and "magnets" not in shaped
    assert shaped["spatial"] == {"makeRoom": "drag"}
    assert all_ids(shaped["tree"]) == ["stage"]
    assert [f["zone"]["id"] for f in shaped["focus"]["floats"]] == ["side"]
    assert all_ids(shaped["pages"][0]["tree"]) == ["pz"]
    assert A.check(shaped) == shaped


def test_a_named_layout_saved_from_v3_keeps_no_magnet(root):
    got = A.save_layout(root, {"id": "mine", "name": "Mine", "layout": v3(
        tree=row(zone("stage"), mzone("mag-a")),
        magnets={"mag-a": config("mag-a")}, spatial={"makeRoom": "off"})})
    kept = next(l for l in got["layouts"] if l["id"] == "mine")["layout"]
    assert all_ids(kept["tree"]) == ["stage"]
    assert "magnets" not in kept and kept["spatial"] == {"makeRoom": "off"}
    got = A.save_layout(root, {"id": "mine2", "name": "Mine 2", "layout": v3(
        tree=row(zone("stage"), mzone("mag-unsnapshotted")))})
    kept = next(l for l in got["layouts"] if l["id"] == "mine2")["layout"]
    assert all_ids(kept["tree"]) == ["stage"]


# -- the Magnet configuration ----------------------------------------------------------------

EVERY_SOURCE = [{"kind": "brain", "brain": "day-to-day"},
                {"kind": "conversation", "conversation": "ent-cd0ddc9713a5"},
                {"kind": "connector", "connector": "drive", "location": "/Shared/x"},
                {"kind": "connector", "connector": "mail"},
                {"kind": "web", "url": "https://example.org/feed", "domain": "example.org"},
                {"kind": "web"},
                {"kind": "other", "type": "rss", "ref": "feed:42"}]


@pytest.mark.parametrize("collection", [
    {"mode": "one-time"}, {"mode": "scheduled", "schedule": "0 9 * * 1-5"},
    {"mode": "continuous"}, {"mode": "paused"},
    {"mode": "scheduled", "schedule": "PT1H"}])
@pytest.mark.parametrize("synthesis", [
    {"mode": "manual"}, {"mode": "scheduled", "schedule": "P1D"},
    {"mode": "on-new-information"}])
@pytest.mark.parametrize("renderer", list(A.RENDERERS))
def test_a_magnet_config_round_trips_every_facet_and_value(collection, synthesis, renderer):
    c = config("mag-every", sources=EVERY_SOURCE,
               selection={"criteria": "anything about magnets",
                          "phrases": ["surface tension", "x" * 500],
                          "topics": ["ent-123", "tpc-9"],
                          "informationTypes": list(A.INFORMATION_TYPES),
                          "dates": {"after": "2026-01-01",
                                    "before": "2026-10-30T12:00:00Z"},
                          "filters": {"author": "brian", "min": 3, "kept": True}},
               collection=collection, synthesis=synthesis,
               notifications={"newItems": True, "changes": True, "failures": True},
               presentation={"renderer": renderer})
    assert A.magnet_config(copy.deepcopy(c)) == c
    layout = v3(tree=mzone("mag-every"), magnets={"mag-every": c})
    assert A.check(layout) == layout


def _bad(**over):
    return config("mag-bad", **over)


@pytest.mark.parametrize("bad, words", [
    ({**config("mag-bad"), "extra": 1}, "'extra'"),
    ({k: v for k, v in config("mag-bad").items() if k != "synthesis"}, "'synthesis' is missing"),
    ({**config("mag-bad"), "id": "conv-1"}, "id"),
    (_bad(sources=[]), "1..20 sources"),
    (_bad(sources=[{"kind": "conversation", "conversation": "c"}] * 21), "1..20 sources"),
    (_bad(sources=[{"kind": "telepathy"}]), "telepathy"),
    (_bad(sources=[{"kind": "conversation", "conversation": "c", "x": 1}]), "'x'"),
    (_bad(sources=[{"kind": "conversation"}]), "'conversation' is missing"),
    (_bad(sources=[{"kind": "web", "url": "ftp://x"}]), "http"),
    (_bad(selection={"phrases": ["x" * 501]}), "phrases"),
    (_bad(selection={"phrases": ["p"] * 21}), "phrases"),
    (_bad(selection={"topics": ["t"] * 51}), "topics"),
    (_bad(selection={"informationTypes": ["video"]}), "video"),
    (_bad(selection={"informationTypes": ["post", "post"]}), "once"),
    (_bad(selection={"dates": {"after": "yesterday"}}), "ISO 8601"),
    (_bad(selection={"dates": {"during": "2026-01-01"}}), "'during'"),
    (_bad(selection={"filters": {f"k{i}": i for i in range(21)}}), "20 entries"),
    (_bad(selection={"filters": {"k": [1]}}), "text, a number"),
    (_bad(selection={"mood": "x"}), "'mood'"),
    (_bad(collection={"mode": "sometimes"}), "sometimes"),
    (_bad(collection={"mode": "scheduled"}), "schedule"),
    (_bad(collection={"mode": "scheduled", "schedule": "every tuesday"}), "cron"),
    (_bad(collection={"mode": "scheduled", "schedule": "P"}), "cron"),
    (_bad(collection={"mode": "one-time", "schedule": "PT1H"}), "only a scheduled"),
    (_bad(synthesis={"mode": "automatic"}), "automatic"),
    (_bad(synthesis={"mode": "scheduled", "schedule": "* * *"}), "cron"),
    (_bad(notifications={"newItems": True, "changes": False}), "'failures' is missing"),
    (_bad(notifications={"newItems": 1, "changes": False, "failures": False}), "true or false"),
    (_bad(notifications={"newItems": True, "changes": False, "failures": False, "push": True}), "'push'"),
    (_bad(presentation={"renderer": "carousel"}), "carousel"),
    (_bad(presentation={"renderer": "cards", "level": "icon"}), "'level'"),
])
def test_a_bad_magnet_config_is_refused(bad, words):
    with pytest.raises(A.Refused, match=words):
        A.magnet_config(bad)


def test_magnet_ids_are_stable_and_match_their_key():
    with pytest.raises(A.Refused, match="its own id"):
        A.check(v3(magnets={"mag-a": config("mag-b")}))
    with pytest.raises(A.Refused, match="magnets key"):
        A.check(v3(magnets={"conv-1": config("mag-a")}))
    with pytest.raises(A.Refused, match="at most 50"):
        A.check(v3(magnets={f"mag-{i}": config(f"mag-{i}") for i in range(51)}))
    with pytest.raises(A.Refused, match="Magnet zone's id"):
        A.check(v3(tree={**mzone("mag-a"), "id": "z1"}, magnets={"mag-a": config("mag-a")}))
    with pytest.raises(A.Refused, match="options"):
        A.check(v3(tree={**mzone("mag-a"), "options": {"magnet": "mag-a", "x": 1}},
                   magnets={"mag-a": config("mag-a")}))


def test_check_refuses_a_saved_magnet_zone_whose_config_is_absent():
    with pytest.raises(A.Refused, match="mag-gone.*is not in this arrangement's magnets"):
        A.check(v3(tree=row(zone("stage"), mzone("mag-gone"))))
    floating = v3(focus={"floats": [fl("w1", mzone("mag-gone"))]})
    with pytest.raises(A.Refused, match="mag-gone"):
        A.check(floating)
    assert A.check(floating, refs=False)["focus"]["floats"][0]["zone"]["id"] == "mag-gone"


# -- the Magnet operations ----------------------------------------------------------------------

def attach(**extra):
    return {"zone": {"type": "zone", "show": "magnet", "name": "Board"}, **extra}


def create(root, op=None, key=KEY, **body):
    body = {"seed": seed(), "attach": attach(), **body}
    if op:
        body["op"] = op
    return A.create_magnet(root, key, body)


def remove_zone(root, mid, **extra):
    return A.save(root, KEY, {"sharedZone": {"op": "remove", "id": mid}, **extra})


def test_create_writes_config_and_zone_together_and_replays(root):
    put(root, v3())
    got = create(root, op="op-1")
    mid = got["magnet"]["id"]
    assert mid.startswith("mag-") and got["layout"]["magnets"] == {mid: got["magnet"]}
    (where, page, z, window) = A.magnet_zones(got["layout"])[mid]
    assert (where, page, z["name"], window["min"]) == ("float", None, "Board", True)
    again = create(root, op="op-1")
    assert again["replayed"] is True and again["magnet"] == got["magnet"]
    assert len(stored(root)["magnets"]) == 1
    with pytest.raises(A.Conflict):
        create(root, op="op-1", seed=seed(presentation={"renderer": "list"}))


def test_reconfigure_and_remove_are_idempotent_and_removal_waits_for_the_zone(root):
    put(root, v3())
    mid = create(root, op="op-c")["magnet"]["id"]
    change = {"presentation": {"renderer": "gallery"},
              "selection": {"informationTypes": ["file"]}}
    got = A.reconfigure_magnet(root, KEY, mid, {"change": change, "op": "op-r"})
    assert got["magnet"]["presentation"] == {"renderer": "gallery"}
    assert got["magnet"]["sources"] == seed()["sources"], "facets not named are kept"
    zone_before = A.magnet_zones(got["layout"])[mid]
    A.reconfigure_magnet(root, KEY, mid, {"change": {"presentation": {"renderer": "disc"}}})
    again = A.reconfigure_magnet(root, KEY, mid, {"change": change, "op": "op-r"})
    assert again["replayed"] is True
    assert again["magnet"]["presentation"] == {"renderer": "disc"}, "a replay never undoes a later change"
    assert A.magnet_zones(again["layout"])[mid] == zone_before, "id, zone and placement unchanged"
    with pytest.raises(A.Refused, match="never changes"):
        A.reconfigure_magnet(root, KEY, mid, {"change": {"id": "mag-other"}})
    with pytest.raises(A.Refused, match="'mood'"):
        A.reconfigure_magnet(root, KEY, mid, {"change": {"mood": 1}})

    with pytest.raises(A.Declined, match="still shows") as exc:
        A.remove_magnet(root, KEY, mid, {"op": "op-x"})
    assert exc.value.reason["code"] == "state"
    assert mid in stored(root)["magnets"]
    remove_zone(root, mid)
    assert mid in stored(root)["magnets"], "removing the zone never removes the config"
    got = A.remove_magnet(root, KEY, mid, {"op": "op-x"})
    assert got["removed"] is True and "magnets" not in got["layout"]
    again = A.remove_magnet(root, KEY, mid, {"op": "op-x"})
    assert again["replayed"] is True
    assert A.remove_magnet(root, KEY, mid, {})["removed"] is False


def test_medium_shared_zone_patch_preserves_wide_and_pending_changes(root):
    put(root, v3(tree=row(zone("stage"), zone("notes")),
                 focus={"floats": [fl("w1", zone("f1"))]},
                 conversation={"width": 500}, spatial={"makeRoom": "drag"},
                 presentations={"medium": dp(["notes", "stage"],
                                             {"notes": "stack", "stage": "dock"},
                                             {"notes": "compact"}, 3)}))
    before = stored(root)
    # The session's own dirty state -- a wide tree, rectangles, levels,
    # spatial, other zones' placement -- is not part of the patch, and a
    # patch that tries to carry another zone's entry is refused.
    with pytest.raises(A.Refused, match="only its own placement"):
        A.save(root, KEY, {"sharedZone": {"op": "add", "zone": zone("new")},
                           "scope": "medium",
                           "presentation": dp(["new", "stage"],
                                              {"new": "stack", "stage": "sheet"})})
    with pytest.raises(A.Refused, match="'layout'"):
        A.save(root, KEY, {"sharedZone": {"op": "add", "zone": zone("new")},
                           "layout": v3(tree=zone("wide-edit"))})
    with pytest.raises(A.Refused, match="only an add"):
        A.save(root, KEY, {"sharedZone": {"op": "remove", "id": "notes"},
                           "scope": "medium", "presentation": {"place": "stack"}})
    assert stored(root) == before, "a refused patch writes nothing"

    got = A.save(root, KEY, {"sharedZone": {"op": "add", "zone": zone("new"),
                                            "wideFallback": "launcher"},
                             "scope": "medium",
                             "presentation": {"place": "stack", "level": "icon",
                                              "index": 1}})["layout"]
    medium = got["presentations"]["medium"]
    assert medium["order"] == ["notes", "new", "stage"]
    assert medium["place"] == {"notes": "stack", "stage": "dock", "new": "stack"}
    assert medium["level"] == {"notes": "compact", "new": "icon"}
    assert got["tree"] == before["tree"], "the wide tree is untouched"
    assert got["focus"]["floats"][0] == before["focus"]["floats"][0]
    assert got["focus"]["floats"][1]["zone"]["id"] == "new"
    assert got["focus"]["floats"][1]["min"] is True
    for k in ("conversation", "spatial"):
        assert got[k] == before[k]

    got = remove_zone(root, "notes", scope="medium")["layout"]
    assert all_ids(got["tree"]) == ["stage"]
    assert "notes" not in got["presentations"]["medium"]["order"]
    assert "notes" not in got["presentations"]["medium"]["place"]
    assert "notes" not in got["presentations"]["medium"]["level"]
    assert got["focus"]["floats"] == stored(root)["focus"]["floats"]
    for k in ("conversation", "spatial"):
        assert got[k] == before[k]


def test_magnet_reconfigure_recreates_missing_config_same_id(root):
    # A legacy/recovery state: a session holds zone mag-lost, whose config the
    # store no longer has.
    put(root, v3())
    with pytest.raises(A.Declined) as exc:
        A.reconfigure_magnet(root, KEY, "mag-lost",
                             {"change": {"presentation": {"renderer": "ring"}}})
    assert exc.value.reason == {"code": "state", "message": A.MISSING,
                                "retryable": True}
    assert "magnets" not in stored(root), "the refusal writes nothing"
    # Recovery: create with the fixed id and a complete seed.
    got = create(root, id="mag-lost",
                 attach=attach(scope="compact", presentation={"place": "stack"}))
    assert got["magnet"]["id"] == "mag-lost"
    assert "mag-lost" in A.magnet_zones(got["layout"])
    # Another create in compact, then a reload: both survive.
    other = create(root, attach=attach(scope="compact",
                                       presentation={"place": "sheet"}))
    reloaded = stored(root)
    assert set(reloaded["magnets"]) == {"mag-lost", other["magnet"]["id"]}
    assert set(A.magnet_zones(reloaded)) == {"mag-lost", other["magnet"]["id"]}
    assert reloaded["presentations"]["compact"]["place"] == {
        "mag-lost": "stack", other["magnet"]["id"]: "sheet"}
    with pytest.raises(A.Declined, match="already in this workspace"):
        create(root, id="mag-lost")


def test_undo_of_remove_and_redo_of_create_recreate_under_the_same_id(root):
    put(root, v3())
    made = create(root, seed=seed(presentation={"renderer": "ring"}))
    mid, cfg = made["magnet"]["id"], made["magnet"]
    # Remove from workspace, committed: the zone, then the config.
    remove_zone(root, mid)
    A.remove_magnet(root, KEY, mid, {})
    assert mid not in (stored(root).get("magnets") or {})
    # Undo of that Remove: one create with the fixed id.
    back = create(root, id=mid, seed={k: v for k, v in cfg.items() if k != "id"})
    assert back["magnet"] == cfg and mid in A.magnet_zones(back["layout"])
    # Undo of the create (zone out, then the config), and Redo of it.
    remove_zone(root, mid)
    A.remove_magnet(root, KEY, mid, {})
    redo = create(root, id=mid, seed={k: v for k, v in cfg.items() if k != "id"})
    assert redo["magnet"] == cfg
    assert set(stored(root)["magnets"]) == {mid}
    assert set(A.magnet_zones(stored(root))) == {mid}


def test_magnet_create_collects_orphans_before_limit(root):
    # 3 configs a stored zone names, 47 that none does (zones never saved,
    # or undone): 50 in all.
    shown = [f"mag-shown{i}" for i in range(3)]
    orphans = [f"mag-orphan{i}" for i in range(47)]
    put(root, v3(tree=row(zone("stage"), *[mzone(m) for m in shown]),
                 magnets={m: config(m) for m in shown + orphans}), )
    got = create(root)
    assert set(got["layout"]["magnets"]) == set(shown) | {got["magnet"]["id"]}

    # 50 that stored zones all name: the bound declines the next one.
    pages = [{"id": f"p{p}", "title": f"P{p}",
              "tree": row(*[mzone(f"mag-{p}-{i}") for i in range(10)])}
             for p in range(5)]
    mids = [f"mag-{p}-{i}" for p in range(5) for i in range(10)]
    put(root, v3(pages=pages, magnets={m: config(m) for m in mids}))
    with pytest.raises(A.Declined, match="50 Magnets") as exc:
        create(root)
    assert exc.value.reason["code"] == "limit"


def test_twelve_stored_floats_store_a_launcher_add_as_a_docked_leaf(root):
    floats = [fl(f"w{i}", zone(f"f{i}"), i) for i in range(12)]
    put(root, v3(tree=row(zone("stage"), zone("notes")), focus={"floats": floats}))
    got = create(root, wideFallback="launcher",
                 attach=attach(scope="compact", presentation={"place": "stack"}))
    mid = got["magnet"]["id"]
    assert len(got["layout"]["focus"]["floats"]) == 12, "no thirteenth window"
    assert A.magnet_zones(got["layout"])[mid][0] == "tree"
    assert got["layout"]["presentations"]["compact"]["place"][mid] == "stack"
    for place in ("dock", "sheet"):
        got = A.save(root, KEY, {"sharedZone": {"op": "add", "zone": zone(f"z-{place}")},
                                 "scope": "medium",
                                 "presentation": {"place": place}})["layout"]
        assert len(got["focus"]["floats"]) == 12
        assert f"z-{place}" in all_ids(got["tree"])


def test_launcher_adds_in_a_row_get_discs_that_do_not_overlap(root):
    # One disc already put away at the grid's first slot, one the owner moved
    # off the grid, and an open window over the corner (not a disc).
    floats = [fl("w-a", zone("fa"), min=True) | {"x": 24, "y": 24},
              fl("w-b", zone("fb"), min=True) | {"x": 170, "y": 60},
              fl("w-c", zone("fc"))]
    put(root, v3(tree=row(zone("stage"), zone("notes")), focus={"floats": floats}))
    for i in range(6):
        A.save(root, KEY, {"sharedZone": {"op": "add", "zone": zone(f"m{i}"),
                                          "wideFallback": "launcher"},
                           "scope": "medium",
                           "presentation": {"place": "stack"}})
    got = stored(root)["focus"]["floats"]
    assert len(got) == 9 and all(f["min"] for f in got[3:])
    assert [(f["x"], f["y"]) for f in got[:3]] == [
        (f["x"], f["y"]) for f in floats], "nothing already there moved"
    disc = 56
    discs = [(f["x"], f["y"]) for f in got if f.get("min")]
    for i, (ax, ay) in enumerate(discs):
        for bx, by in discs[i + 1:]:
            assert abs(ax - bx) >= disc or abs(ay - by) >= disc, (
                f"discs at {(ax, ay)} and {(bx, by)} overlap")
    assert all(f["w"] == 360 and f["h"] == 480 for f in got[3:])


def test_magnet_create_requires_resolved_base_for_new_place(root):
    with pytest.raises(A.Refused, match="send attach.base"):
        create(root)
    assert not path_of(root).exists(), "no blank layout is invented or written"
    with pytest.raises(A.Refused, match="send `base`"):
        A.save(root, KEY, {"sharedZone": {"op": "add", "zone": zone("x")}})
    with pytest.raises(A.Refused, match="send `base`"):
        A.save(root, KEY, {"scope": "compact", "presentation": None})
    assert not path_of(root).exists()

    # The Holder's resolved persisted/default-tier arrangement (a default
    # named layout here), without the session's unsaved edits.
    base = v2(tree=row(zone("default-stage"), zone("default-side")),
              appearance={"panel": "tinted"})
    got = create(root, attach=attach(base=base))
    mid = got["magnet"]["id"]
    kept = got["layout"]
    assert kept["version"] == 3
    assert all_ids(kept["tree"]) == ["default-stage", "default-side"]
    assert kept["appearance"] == {"panel": "tinted"}
    assert [f["zone"]["id"] for f in kept["focus"]["floats"]] == [mid]
    assert set(kept) == {"format", "version", "tree", "appearance", "focus", "magnets"}

    # A concurrent writer won: a later base never overwrites what is stored.
    other = create(root, attach=attach(base=v2(tree=zone("someone-else"))))
    assert all_ids(stored(root)["tree"]) == ["default-stage", "default-side"]
    assert set(stored(root)["magnets"]) == {mid, other["magnet"]["id"]}

    # The scoped save's base is the same rule, on another place.
    A.save(root, "ent-other", {"scope": "compact", "presentation": dp(["a"], {"a": "sheet"}),
                               "base": v2(tree=zone("a"))})
    assert stored(root, "ent-other")["tree"]["id"] == "a"


def test_a_narrow_write_never_replaces_an_unreadable_arrangement(root):
    path_of(root).parent.mkdir(parents=True)
    path_of(root).write_text("{not json", encoding="utf-8")
    for call in (lambda: create(root, attach=attach(base=v3())),
                 lambda: A.save(root, KEY, {"scope": "compact", "presentation": None,
                                            "base": v3()}),
                 lambda: A.save(root, KEY, {"sharedZone": {"op": "remove", "id": "x"},
                                            "base": v3()}),
                 lambda: A.reconfigure_magnet(root, KEY, "mag-a",
                                              {"change": {"presentation": {"renderer": "ring"}}}),
                 lambda: A.remove_magnet(root, KEY, "mag-a", {})):
        with pytest.raises(A.Unreadable):
            call()
    assert path_of(root).read_text(encoding="utf-8") == "{not json"


def test_a_full_save_never_replaces_an_unreadable_arrangement(root):
    path_of(root).parent.mkdir(parents=True)
    path_of(root).write_text("{not json", encoding="utf-8")
    with pytest.raises(A.Unreadable, match="left as it is"):
        full(root, v3(tree=zone("desk")))
    assert path_of(root).read_text(encoding="utf-8") == "{not json"


def test_magnet_create_declines_before_a_docked_zone_would_exceed_limit(root):
    full_tree = row(*[row(*[zone(f"z-{group}-{i}") for i in range(10)])
                      for group in range(4)])
    put(root, v3(tree=full_tree))
    before = path_of(root).read_bytes()
    with pytest.raises(A.Declined) as exc:
        create(root, wideFallback="dock")
    assert exc.value.reason["code"] == "limit"
    assert path_of(root).read_bytes() == before


def test_validation_has_no_connector_web_collection_or_synthesis_side_effect(root, monkeypatch):
    import socket
    import subprocess
    import threading
    import mentis.web as web

    def boom(*a, **k):
        raise AssertionError("validation reached outside the arrangement")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(threading.Thread, "start", boom)
    monkeypatch.setattr(web, "dispatch_soon", boom)
    put(root, v3())
    unexecutable = seed(sources=EVERY_SOURCE,
                        collection={"mode": "continuous"},
                        synthesis={"mode": "scheduled", "schedule": "0 * * * *"},
                        notifications={"newItems": True, "changes": True, "failures": True})
    mid = create(root, seed=unexecutable)["magnet"]["id"]
    A.reconfigure_magnet(root, KEY, mid, {"change": {
        "collection": {"mode": "scheduled", "schedule": "PT5M"},
        "synthesis": {"mode": "on-new-information"}}})
    assert stored(root)["magnets"][mid]["sources"] == EVERY_SOURCE
    written = sorted(str(p.relative_to(root)).replace("\\", "/")
                     for p in pathlib.Path(root).rglob("*") if p.is_file())
    assert written == ["presentation/fluid-arrangements/home.json"]


# -- through the Fluid API --------------------------------------------------------------------

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


def _get(world, path):
    req = urllib.request.Request(world["base"] + "/fluid/api/" + path,
                                 headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_magnet_routes_through_the_fluid_api(world):
    status, got = _post(world, "arrangements/home/magnets",
                        {"seed": seed(), "attach": attach(base=v2()), "op": "op-h1"})
    assert status == 200, got
    mid = got["magnet"]["id"]
    assert _get(world, "arrangements/home")["layout"]["magnets"][mid] == got["magnet"]

    status, got = _post(world, f"arrangements/home/magnets/{mid}/reconfigure",
                        {"change": {"presentation": {"renderer": "list"}}})
    assert status == 200 and got["magnet"]["presentation"] == {"renderer": "list"}

    status, got = _post(world, "arrangements/home/magnets/mag-missing/reconfigure",
                        {"change": {"presentation": {"renderer": "list"}}})
    assert status == 422 and got["reason"] == {"code": "state", "message": A.MISSING,
                                               "retryable": True}

    status, got = _post(world, f"arrangements/home/magnets/{mid}/remove", {})
    assert status == 422 and got["reason"]["code"] == "state"

    status, got = _post(world, "arrangements/home",
                        {"sharedZone": {"op": "remove", "id": mid}, "op": "op-h2"})
    assert status == 200 and mid not in A.magnet_zones(got["layout"])
    status, got = _post(world, f"arrangements/home/magnets/{mid}/remove", {"op": "op-h3"})
    assert status == 200 and got["removed"] is True

    status, got = _post(world, "arrangements/home",
                        {"scope": "compact", "presentation": dp(["x"], {"x": "dock"})})
    assert status == 400 and "dock" in got["error"]
    status, got = _post(world, "arrangements/home/magnets",
                        {"seed": {**seed(), "mood": 1}, "attach": attach()})
    assert status == 400 and "'mood'" in got["error"]

    status, got = _post(world, "arrangements/home/magnets",
                        {"seed": seed(presentation={"renderer": "ring"}),
                         "attach": attach(), "op": "op-h1"})
    assert status == 422 and got["reason"]["code"] == "conflict"


def test_full_save_unreadable_refusal_is_machine_readable(world):
    path = path_of(world["root"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    status, got = _post(world, "arrangements/home", {"layout": v3()})
    assert status == 409
    assert got["reason"] == {
        "code": "unreadable",
        "message": "the saved arrangement could not be read; it was left as it is",
        "retryable": False,
    }
    assert path.read_text(encoding="utf-8") == "{not json"
