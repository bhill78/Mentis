"""The Fluid workspace manifest: fixtures only, never a real Brain."""
import json
import os
import threading

import pytest

from mentis.fluid import _checks
from mentis.fluid import workspace_manifest as wm

OWNER = {"source": {"kind": "participant", "ref": "ent-5936369158a8"}}
CITATION = "adm-0123456789ab@0123456789ab[0:10]"


def obj(kind="magnet", ref="mag-one", provenance=OWNER, **more):
    return {"kind": kind, "ref": ref, "provenance": provenance, **more}


def ids(answer):
    return [o["id"] for o in answer["manifest"]["objects"]]


def file_of(root, wid):
    return root / "presentation" / "fluid-workspaces" / f"{wid}.json"


@pytest.fixture
def root(tmp_path):
    return tmp_path / "brain"


# -- round trip -----------------------------------------------------------------

def test_a_blank_workspace_belongs_to_no_conversation_and_round_trips(root):
    made = wm.create(root, {"name": "Thinking"})
    wid = made["id"]
    assert wid.startswith("wsp-") and made["changed"] and not made["replayed"]
    assert file_of(root, wid).is_file()
    got = wm.workspace(root, wid)
    assert got == {"id": wid, "manifest": made["manifest"]}
    m = got["manifest"]
    assert m["format"] == "mentis.fluid-workspace" and m["schema_version"] == 1
    assert m["objects"] == [] and m["revision"] == 1 and m["name"] == "Thinking"
    assert set(m) == {"format", "schema_version", "id", "name", "revision",
                      "created", "updated", "objects"}
    assert "conversation" not in m


def test_a_workspace_holds_several_magnets_and_every_kind_of_object(root):
    objects = [
        obj(ref="mag-one"),
        obj(ref="mag-two", observed={"version": "r7", "at": 1000.5}),
        obj("conversation", "ent-355226311ae3"),
        obj("chat", "ent-355226311ae4"),
        obj("file", "adm-0123456789ab"),
        obj("image", "live:ent-0c4161449472:img-1"),
        obj("evidence", CITATION, provenance={
            "source": {"kind": "magnet", "ref": "mag-one"},
            "brain": "day-to-day", "by": "ent-3a5fb342dd6b", "at": 10}),
        obj("report", "ent-0c4161449472"),
        obj("participant", "ent-3a5fb342dd6b"),
        obj("other", "https://example.com/a thing"),
    ]
    made = wm.create(root, {"name": "Compare", "objects": objects})
    got = wm.workspace(root, made["id"])["manifest"]["objects"]
    assert [o["kind"] for o in got] == [o["kind"] for o in objects]
    assert [o["ref"] for o in got] == [o["ref"] for o in objects]
    assert all(o["curated"] is True for o in got)
    assert got[1]["observed"] == {"version": "r7", "at": 1000.5}
    assert got[6]["provenance"]["source"] == {"kind": "magnet", "ref": "mag-one"}
    assert got[0]["id"] == wm.object_id("magnet", "mag-one")


def test_a_list_is_by_id_in_brief_and_nothing_is_nothing(root):
    assert wm.workspaces(root) == []
    a = wm.create(root, {"name": "a", "objects": [obj()]})["id"]
    b = wm.create(root, {"name": "b"})["id"]
    listed = wm.workspaces(root)
    assert [w["id"] for w in listed] == sorted([a, b])
    assert {w["name"]: w["objects"] for w in listed} == {"a": 1, "b": 0}


def test_a_workspace_never_made_reads_as_none_and_cannot_be_changed(root):
    assert wm.workspace(root, "wsp-absent") == {"id": "wsp-absent", "manifest": None}
    with pytest.raises(wm.NotFound):
        wm.rename(root, "wsp-absent", {"name": "x"})
    with pytest.raises(wm.NotFound):
        wm.delete(root, "wsp-absent")


# -- it is not an arrangement, and not a resolution -------------------------------

def test_nothing_of_arrangements_is_touched(root):
    wm.create(root, {"objects": [obj()]})
    assert [p.name for p in (root / "presentation").iterdir()] == ["fluid-workspaces"]


@pytest.mark.parametrize("name", ["layout", "theme", "Theme", "look", "tree", "zones",
                                  "presentation", "resolved", "authoritative"])
def test_presentation_and_resolution_are_refused_at_any_depth(root, name):
    with pytest.raises(wm.Refused):
        wm.create(root, {name: {}})
    with pytest.raises(wm.Refused):
        wm.create(root, {"objects": [obj(**{name: 1})]})
    with pytest.raises(wm.Refused):
        wm.create(root, {"note": {"inner": [{name: 1}]}})
    prov = {**OWNER, name: 1}
    with pytest.raises(wm.Refused):
        wm.create(root, {"objects": [obj(provenance=prov)]})
    assert wm.workspaces(root) == []


def test_a_file_holding_a_theme_is_unreadable(root):
    wid = wm.create(root, {})["id"]
    data = json.loads(file_of(root, wid).read_text("utf-8"))
    file_of(root, wid).write_text(json.dumps({**data, "theme": "glass"}), "utf-8")
    assert "unreadable" in wm.workspace(root, wid)


def test_curated_references_are_the_frozen_fields_alone(root):
    prov = {**OWNER, "later": 1, "source": {**OWNER["source"], "later": 1}}
    made = wm.create(root, {"later": 1, "objects": [
        obj(provenance=prov, later=1, observed={"at": 5, "later": 1})]})
    m = made["manifest"]
    assert m["objects"][0]["later"] == 1
    got = wm.curated_references(m)
    assert got == [{"id": wm.object_id("magnet", "mag-one"), "kind": "magnet",
                    "ref": "mag-one", "curated": True, "provenance": OWNER,
                    "observed": {"at": 5}}]


def test_curated_is_only_ever_true(root):
    assert wm.create(root, {"objects": [obj(curated=True)]})["manifest"]["objects"]
    for bad in (False, None, 1, "true"):
        with pytest.raises(wm.Refused):
            wm.create(root, {"objects": [obj(curated=bad)]})


# -- bounds and refusal ----------------------------------------------------------

@pytest.mark.parametrize("wid", [
    "../evil", "..", "wsp-../evil", "wsp-a/b", "wsp-a\\b", "wsp-a.json", "WSP-a",
    "wsp-UPPER", "wsp-", "con", "nul", "wsp-a\n", "wsp-a b", "c:evil", "",
    "wsp-" + "a" * 61, None, 7])
def test_ids_that_could_escape_or_collide_are_refused(root, wid):
    with pytest.raises(wm.Refused):
        wm.workspace(root, wid)
    with pytest.raises(wm.Refused):
        wm.delete(root, wid)
    assert not root.exists()


@pytest.mark.parametrize("kind, ref", [
    ("magnet", "ent-0c4161449472"), ("magnet", "mag-a/b"),
    ("conversation", "../x"), ("conversation", "a:b"),
    ("chat", "a.b"), ("file", "ent-0c4161449472"), ("file", "adm-xyz"),
    ("image", "live:only"), ("image", "live::key"),
    ("evidence", "adm-0123456789ab@bad[0:1]"), ("report", "mag-one"),
    ("participant", "brain:ent-1"), ("other", " padded "), ("other", ""),
    ("other", "line\nbreak"), ("other", "x" * (wm.MAX_REF + 1)),
    ("nonsense", "mag-one"), (None, "mag-one"), (["magnet"], "mag-one"),
    ("magnet", None), ("magnet", 7)])
def test_a_reference_must_have_its_kinds_shape(root, kind, ref):
    with pytest.raises(wm.Refused):
        wm.create(root, {"objects": [obj(kind, ref)]})


@pytest.mark.parametrize("prov", [
    None, {}, "owner", {"source": None}, {"source": {"kind": "magnet"}},
    {"source": {"kind": "magnet", "ref": "ent-0c4161449472"}},
    {**OWNER, "at": "soon"}, {**OWNER, "at": float("nan")}, {**OWNER, "at": -1},
    {**OWNER, "brain": "a/b"}, {**OWNER, "by": "a:b"}])
def test_provenance_is_required_and_checked(root, prov):
    with pytest.raises(wm.Refused):
        wm.create(root, {"objects": [obj(provenance=prov)]})


@pytest.mark.parametrize("observed", [
    {}, {"later": 1}, None, "r1", {"version": ""}, {"version": "x" * 201},
    {"at": True}])
def test_observed_when_given_says_something(root, observed):
    with pytest.raises(wm.Refused):
        wm.create(root, {"objects": [obj(observed=observed)]})


def test_bounds(root):
    with pytest.raises(wm.Refused):
        wm.create(root, {"name": "x" * (wm.MAX_NAME + 1)})
    with pytest.raises(wm.Refused):
        wm.create(root, {"op": "x" * (wm.MAX_OP + 1)})
    many = [obj(ref=f"mag-{i}") for i in range(wm.MAX_OBJECTS + 1)]
    with pytest.raises(wm.Refused):
        wm.create(root, {"objects": many})
    with pytest.raises(wm.Refused):
        wm.create(root, {f"f{i}": 1 for i in range(wm.MAX_EXTRAS + 1)})
    with pytest.raises(wm.Refused):
        wm.create(root, {"later": "x" * wm.MAX_EXTRA_BYTES})
    deep = 1
    for _ in range(wm.MAX_EXTRA_DEPTH + 1):
        deep = [deep]
    with pytest.raises(wm.Refused):
        wm.create(root, {"later": deep})
    with pytest.raises(wm.Refused):
        wm.create(root, {"later": float("inf")})
    with pytest.raises(wm.Refused):
        wm.create(root, {"bad name": 1})
    for own in ("id", "revision", "created", "updated", "ops", "deleted"):
        with pytest.raises(wm.Refused):
            wm.create(root, {own: "wsp-mine"})
    assert wm.workspaces(root) == []


def test_a_full_workspace_refuses_a_new_object_but_not_one_it_holds(root):
    full = [obj(ref=f"mag-{i}") for i in range(wm.MAX_OBJECTS)]
    wid = wm.create(root, {"objects": full})["id"]
    with pytest.raises(wm.Refused):
        wm.add_object(root, wid, {"object": obj(ref="mag-more")})
    assert not wm.add_object(root, wid, {"object": full[0]})["changed"]


def test_the_whole_file_is_bounded_and_refusal_leaves_it_as_it_was(root, monkeypatch):
    wid = wm.create(root, {"objects": [obj()]})["id"]
    before = file_of(root, wid).read_bytes()
    monkeypatch.setattr(wm, "MAX_BYTES", len(before))
    with pytest.raises(wm.Refused):
        wm.add_object(root, wid, {"object": obj(ref="mag-two")})
    assert file_of(root, wid).read_bytes() == before


def test_a_file_too_large_is_not_read(root, monkeypatch):
    wid = wm.create(root, {})["id"]
    monkeypatch.setattr(wm, "MAX_BYTES", 10)
    assert "unreadable" in wm.workspace(root, wid)


def test_text_that_cannot_be_stored_is_refused_not_an_error(root):
    with pytest.raises(wm.Refused):
        wm.create(root, {"name": "\ud800"})
    wid = wm.create(root, {})["id"]
    with pytest.raises(wm.Refused):
        wm.add_object(root, wid, {"object": obj("other", "\ud800")})
    assert wm.workspace(root, wid)["manifest"]["objects"] == []


def test_the_number_of_workspaces_is_bounded(root, monkeypatch):
    monkeypatch.setattr(wm, "MAX_WORKSPACES", 2)
    first = wm.create(root, {})["id"]
    wm.create(root, {})
    with pytest.raises(wm.Refused):
        wm.create(root, {})
    wm.delete(root, first)
    wm.create(root, {})


@pytest.mark.parametrize("bad", [2, 0, "1", 1.0, True, None])
def test_another_version_is_refused_whole_and_left_as_it_is(root, bad):
    wid = wm.create(root, {"objects": [obj()]})["id"]
    data = json.loads(file_of(root, wid).read_text("utf-8"))
    raw = json.dumps({**data, "schema_version": bad, "new": {"layout": 1}}).encode()
    file_of(root, wid).write_bytes(raw)

    got = wm.workspace(root, wid)
    assert got["manifest"] is None and "schema_version" in got["unreadable"]
    assert [w for w in wm.workspaces(root) if "unreadable" in w][0]["id"] == wid
    for act in (lambda: wm.rename(root, wid, {"name": "x"}),
                lambda: wm.add_object(root, wid, {"object": obj(ref="mag-2")}),
                lambda: wm.reorder(root, wid, {"order": []}),
                lambda: wm.delete(root, wid)):
        with pytest.raises(wm.Unreadable):
            act()
    assert file_of(root, wid).read_bytes() == raw


@pytest.mark.parametrize("content", [
    "not json", "[]", '"text"', "{}", '{"format": "mentis.fluid-arrangement", '
    '"schema_version": 1}', pytest.param("[" * 100000, id="nested-too-deep")])
def test_a_file_that_is_not_a_manifest_is_never_an_error(root, content):
    wid = wm.create(root, {})["id"]
    file_of(root, wid).write_text(content, "utf-8")
    assert "unreadable" in wm.workspace(root, wid)
    with pytest.raises(wm.Unreadable):
        wm.rename(root, wid, {"name": "x"})
    assert file_of(root, wid).read_text("utf-8") == content


@pytest.mark.parametrize("change", [
    lambda d: d.update(id="wsp-other"),
    lambda d: d.update(revision=0),
    lambda d: d.update(revision=True),
    lambda d: d.update(ops=[["only"]]),
    lambda d: d["objects"].append(dict(d["objects"][0])),
    lambda d: d["objects"][0].update(id="wob-0000000000000000"),
    lambda d: d["objects"][0].pop("id"),
    lambda d: d["objects"][0].pop("curated"),
    lambda d: d["objects"][0].update(curated=False),
    lambda d: d.update(deleted=5),
])
def test_a_stored_manifest_is_checked_as_what_is_sent_is(root, change):
    wid = wm.create(root, {"objects": [obj()]})["id"]
    data = json.loads(file_of(root, wid).read_text("utf-8"))
    change(data)
    file_of(root, wid).write_text(json.dumps(data), "utf-8")
    assert "unreadable" in wm.workspace(root, wid)


def test_unknown_fields_are_kept_through_every_write(root):
    wid = wm.create(root, {"later": {"a": [1, 2]}, "objects": [
        obj(later="o", observed={"at": 1, "later": "seen"},
            provenance={**OWNER, "later": "p",
                        "source": {**OWNER["source"], "later": "s"}})]})["id"]
    wm.rename(root, wid, {"name": "n"})
    wm.add_object(root, wid, {"object": obj(ref="mag-two")})
    m = wm.workspace(root, wid)["manifest"]
    assert m["later"] == {"a": [1, 2]}
    o = m["objects"][0]
    assert o["later"] == "o" and o["observed"]["later"] == "seen"
    assert o["provenance"]["later"] == "p"
    assert o["provenance"]["source"]["later"] == "s"


def test_a_later_v1_field_in_the_file_is_kept_by_a_write(root):
    wid = wm.create(root, {})["id"]
    data = json.loads(file_of(root, wid).read_text("utf-8"))
    file_of(root, wid).write_text(json.dumps({**data, "later": 1}), "utf-8")
    wm.rename(root, wid, {"name": "n"})
    assert json.loads(file_of(root, wid).read_text("utf-8"))["later"] == 1


def test_a_client_speaking_another_version_is_refused(root):
    with pytest.raises(wm.Refused):
        wm.create(root, {"schema_version": 2})
    with pytest.raises(wm.Refused):
        wm.create(root, {"format": "mentis.fluid-arrangement"})
    assert wm.create(root, {"schema_version": 1, "format": wm.FORMAT})["changed"]


# -- atomic and idempotent ----------------------------------------------------------

def test_a_failed_rename_leaves_the_file_and_no_temporary(root, monkeypatch):
    wid = wm.create(root, {"objects": [obj()]})["id"]
    path = file_of(root, wid)
    before = path.read_bytes()

    def fail(*_a):
        raise OSError("disk")
    monkeypatch.setattr(_checks.os, "replace", fail)
    with pytest.raises(OSError):
        wm.add_object(root, wid, {"object": obj(ref="mag-two")})
    with pytest.raises(OSError):
        wm.delete(root, wid)
    monkeypatch.undo()
    assert path.read_bytes() == before
    assert os.listdir(path.parent) == [path.name]


def test_a_retried_create_finds_what_it_made(root):
    body = {"name": "n", "objects": [obj()], "op": "op-1"}
    first = wm.create(root, body)
    again = wm.create(root, body)
    assert again["id"] == first["id"] and again["replayed"] and not again["changed"]
    assert len(wm.workspaces(root)) == 1
    with pytest.raises(wm.Conflict):
        wm.create(root, {**body, "name": "other"})


def test_without_a_key_each_create_is_a_new_workspace(root):
    assert wm.create(root, {})["id"] != wm.create(root, {})["id"]


def test_a_create_whose_key_is_forgotten_changes_nothing(root):
    body = {"op": "op-1"}
    wid = wm.create(root, body)["id"]
    for i in range(wm.MAX_OPS):
        wm.rename(root, wid, {"name": f"n{i}", "op": f"r{i}"})
    before = file_of(root, wid).read_bytes()
    with pytest.raises(wm.Conflict):
        wm.create(root, body)
    assert file_of(root, wid).read_bytes() == before


@pytest.mark.parametrize("act, other", [
    (lambda r, w, op: wm.rename(r, w, {"name": "n", "op": op}),
     lambda r, w, op: wm.rename(r, w, {"name": "m", "op": op})),
    (lambda r, w, op: wm.add_object(r, w, {"object": obj(ref="mag-2"), "op": op}),
     lambda r, w, op: wm.add_object(r, w, {"object": obj(ref="mag-3"), "op": op})),
])
def test_a_key_replays_its_own_request_and_conflicts_with_another(root, act, other):
    wid = wm.create(root, {"objects": [obj()]})["id"]
    first = act(root, wid, "k")
    assert first["changed"] and not first["replayed"]
    before = file_of(root, wid).read_bytes()
    again = act(root, wid, "k")
    assert again["replayed"] and not again["changed"]
    assert again["manifest"] == first["manifest"]
    assert file_of(root, wid).read_bytes() == before
    with pytest.raises(wm.Conflict):
        other(root, wid, "k")
    assert file_of(root, wid).read_bytes() == before


def test_removing_and_reordering_replay_rather_than_fail(root):
    a, b = obj(ref="mag-a"), obj(ref="mag-b")
    wid = wm.create(root, {"objects": [a, b]})["id"]
    ia, ib = wm.object_id("magnet", "mag-a"), wm.object_id("magnet", "mag-b")
    r1 = wm.reorder(root, wid, {"order": [ib, ia], "op": "o"})
    assert wm.reorder(root, wid, {"order": [ib, ia], "op": "o"})["replayed"]
    assert ids(r1) == [ib, ia]
    wm.remove_object(root, wid, ia, {"op": "r"})
    assert wm.remove_object(root, wid, ia, {"op": "r"})["replayed"]
    with pytest.raises(wm.NotFound):
        wm.remove_object(root, wid, ia)
    with pytest.raises(wm.Conflict):
        wm.remove_object(root, wid, ib, {"op": "r"})


def test_a_noop_under_a_key_is_remembered_without_a_new_revision(root):
    wid = wm.create(root, {"name": "n"})["id"]
    same = wm.rename(root, wid, {"name": "n", "op": "k"})
    assert not same["changed"] and same["manifest"]["revision"] == 1
    assert wm.rename(root, wid, {"name": "n", "op": "k"})["replayed"]
    with pytest.raises(wm.Conflict):
        wm.rename(root, wid, {"name": "m", "op": "k"})
    assert not wm.rename(root, wid, {"name": "n"})["changed"]


def test_only_the_last_keys_are_kept(root):
    wid = wm.create(root, {})["id"]
    for i in range(wm.MAX_OPS + 5):
        wm.rename(root, wid, {"name": f"n{i}", "op": f"k{i}"})
    ops = json.loads(file_of(root, wid).read_text("utf-8"))["ops"]
    assert len(ops) == wm.MAX_OPS and ops[-1][0] == f"k{wm.MAX_OPS + 4}"
    assert "ops" not in wm.workspace(root, wid)["manifest"]


def test_concurrent_additions_are_all_kept(root):
    wid = wm.create(root, {})["id"]
    errors = []

    def add(i):
        try:
            wm.add_object(root, wid, {"object": obj(ref=f"mag-{i}"), "op": f"k{i}"})
            wm.workspace(root, wid)
        except Exception as exc:                          # noqa: BLE001
            errors.append(exc)
    threads = [threading.Thread(target=add, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    m = wm.workspace(root, wid)["manifest"]
    assert len(m["objects"]) == 20 and m["revision"] == 21


def test_revision_rises_only_on_change(root):
    wid = wm.create(root, {"objects": [obj()]})["id"]
    assert wm.add_object(root, wid, {"object": obj()})["manifest"]["revision"] == 1
    assert wm.rename(root, wid, {"name": "n"})["manifest"]["revision"] == 2


# -- order and duplicates -----------------------------------------------------------

def test_additions_go_last_in_the_order_they_came(root):
    wid = wm.create(root, {"objects": [obj(ref="mag-z")]})["id"]
    got = wm.add_object(root, wid, {"object": obj(ref="mag-a")})
    got = wm.add_object(root, wid, {"object": obj(ref="mag-m")})
    assert [o["ref"] for o in got["manifest"]["objects"]] == ["mag-z", "mag-a", "mag-m"]
    assert got["object"] == wm.object_id("magnet", "mag-m")


def test_kind_and_ref_are_the_object_and_the_first_provenance_stands(root):
    other = {"source": {"kind": "magnet", "ref": "mag-src"}}
    made = wm.create(root, {"objects": [obj(), obj(provenance=other)]})
    assert len(made["manifest"]["objects"]) == 1
    again = wm.add_object(root, made["id"], {"object": obj(provenance=other)})
    assert not again["changed"]
    assert again["manifest"]["objects"] == made["manifest"]["objects"]
    assert again["manifest"]["objects"][0]["provenance"] == OWNER
    # the same ref under another kind is another object
    assert wm.add_object(root, made["id"],
                         {"object": obj("other", "mag-one")})["changed"]


def test_an_object_id_sent_must_be_its_own(root):
    wid = wm.create(root, {})["id"]
    with pytest.raises(wm.Refused):
        wm.add_object(root, wid, {"object": obj(id="wob-0000000000000000")})
    good = wm.object_id("magnet", "mag-one")
    assert wm.add_object(root, wid, {"object": obj(id=good)})["object"] == good


def test_removed_and_added_again_keeps_its_id_and_goes_last(root):
    wid = wm.create(root, {"objects": [obj(ref="mag-a"), obj(ref="mag-b")]})["id"]
    ia = wm.object_id("magnet", "mag-a")
    wm.remove_object(root, wid, ia)
    got = wm.add_object(root, wid, {"object": obj(ref="mag-a")})
    assert ids(got) == [wm.object_id("magnet", "mag-b"), ia]


def test_reorder_takes_every_object_exactly_once(root):
    wid = wm.create(root, {"objects": [obj(ref="mag-a"), obj(ref="mag-b")]})["id"]
    ia, ib = wm.object_id("magnet", "mag-a"), wm.object_id("magnet", "mag-b")
    missing = wm.object_id("magnet", "mag-c")
    for bad in ([ia], [ia, ia], [ia, ib, ib], [ia, missing], ["../x", ib], "ab", None):
        with pytest.raises(wm.Refused):
            wm.reorder(root, wid, {"order": bad})
    assert ids(wm.workspace(root, wid)) == [ia, ib]
    assert not wm.reorder(root, wid, {"order": [ia, ib]})["changed"]
    assert ids(wm.reorder(root, wid, {"order": [ib, ia]})) == [ib, ia]


def test_the_file_is_the_same_whatever_built_it(root):
    a = wm.create(root, {"objects": [obj(ref="mag-a"), obj(ref="mag-b")]})
    b = wm.create(root, {})
    wm.add_object(root, b["id"], {"object": obj(ref="mag-b")})
    wm.add_object(root, b["id"], {"object": obj(ref="mag-a")})
    got = wm.reorder(root, b["id"], {"order": ids(a)})
    assert got["manifest"]["objects"] == a["manifest"]["objects"]


# -- deletion ------------------------------------------------------------------------

def test_deletion_keeps_identity_and_keys_and_nothing_else(root):
    wid = wm.create(root, {"name": "secret", "later": 1, "objects": [obj()]})["id"]
    answer = wm.delete(root, wid, {"op": "d"})
    assert answer["manifest"] is None and answer["changed"]
    kept = json.loads(file_of(root, wid).read_text("utf-8"))
    assert set(kept) == {"format", "schema_version", "id", "deleted", "ops"}
    assert "secret" not in file_of(root, wid).read_text("utf-8")
    got = wm.workspace(root, wid)
    assert got["manifest"] is None and got["deleted"] == answer["deleted"]
    assert wm.workspaces(root) == []


def test_a_deleted_workspace_refuses_everything_but_its_replays(root):
    wid = wm.create(root, {"objects": [obj()]})["id"]
    oid = wm.object_id("magnet", "mag-one")
    wm.delete(root, wid, {"op": "d"})
    assert wm.delete(root, wid, {"op": "d"})["replayed"]
    for act in (lambda: wm.delete(root, wid),
                lambda: wm.delete(root, wid, {"op": "other"}),
                lambda: wm.rename(root, wid, {"name": "x"}),
                lambda: wm.add_object(root, wid, {"object": obj()}),
                lambda: wm.remove_object(root, wid, oid),
                lambda: wm.reorder(root, wid, {"order": []})):
        with pytest.raises(wm.Gone):
            act()


def test_a_retried_create_cannot_bring_a_deleted_workspace_back(root):
    body = {"name": "n", "op": "make"}
    wid = wm.create(root, body)["id"]
    wm.delete(root, wid)
    again = wm.create(root, body)
    assert again["id"] == wid and again["replayed"] and again["manifest"] is None
    assert wm.workspaces(root) == []
    with pytest.raises(wm.Conflict):
        wm.create(root, {"name": "other", "op": "make"})


def test_a_key_used_by_a_mutation_conflicts_with_deleting(root):
    wid = wm.create(root, {})["id"]
    wm.rename(root, wid, {"name": "n", "op": "k"})
    with pytest.raises(wm.Conflict):
        wm.delete(root, wid, {"op": "k"})
    assert wm.workspace(root, wid)["manifest"]["name"] == "n"


def test_deleting_touches_only_its_own_file(root):
    keep = wm.create(root, {"objects": [obj()]})["id"]
    gone = wm.create(root, {"objects": [obj()]})["id"]
    other = root / "presentation" / "fluid-arrangements" / "home.json"
    other.parent.mkdir(parents=True)
    other.write_text("{}", "utf-8")
    before = file_of(root, keep).read_bytes()
    wm.delete(root, gone)
    assert file_of(root, keep).read_bytes() == before
    assert other.read_text("utf-8") == "{}"


def test_only_the_newest_tombstones_are_kept(root, monkeypatch):
    monkeypatch.setattr(wm, "MAX_TOMBSTONES", 2)
    made = [wm.create(root, {})["id"] for _ in range(3)]
    stamps = iter([1000.0, 2000.0, 3000.0])
    monkeypatch.setattr(wm.time, "time", lambda: next(stamps))
    for wid in made:
        wm.delete(root, wid)
    assert wm.workspace(root, made[0]) == {"id": made[0], "manifest": None}
    assert wm.workspace(root, made[1])["deleted"] == 2000.0
    assert wm.workspace(root, made[2])["deleted"] == 3000.0


def test_a_file_this_module_did_not_name_is_not_listed(root):
    wid = wm.create(root, {})["id"]
    folder = file_of(root, wid).parent
    (folder / ".incoming-x.json").write_text("{", "utf-8")
    (folder / "notes.txt").write_text("x", "utf-8")
    (folder / "WSP-UPPER.json").write_text("{}", "utf-8")
    assert [w["id"] for w in wm.workspaces(root)] == [wid]
