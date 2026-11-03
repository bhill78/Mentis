"""Selecting a workspace's objects for a request, and what the work may then read.

Everything goes through the real request door and the real worker door with a real
grant, as `tests/test_workspace_objects.py` does: the read recomputes what the door
recorded, and would otherwise be testing a copy of it."""
from __future__ import annotations

import json

import pytest

from mentis.fluid import commands
from mentis.fluid import workspace_manifest as wm
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_agent_request_routing import a_magnet, ask, conversations
from tests.test_workspace_objects import (a_run, a_workspace, door, reference, refused,
                                          routed, run_routed)


def stocked(world, *magnets):  # noqa: F811
    """A workspace holding these Magnet references, and their ids in order."""
    wid = a_workspace(world, *(reference("magnet", m) for m in magnets))
    return wid, [wm.object_id("magnet", m) for m in magnets]


def read(world, token, wid):  # noqa: F811
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer
    return answer


def refs(answer):
    return [o.get("ref") for o in answer["objects"]]


def routed_acts(world):  # noqa: F811
    return world["cv"].corpus.operational(act=commands.REQUEST_ROUTED)


def routed_act(world):  # noqa: F811
    acts = routed_acts(world)
    assert len(acts) == 1
    return acts[0]


# -- what the request door accepts --------------------------------------------

def test_an_explicit_selection_is_answered_alone_and_in_its_order(world):  # noqa: F811
    wid, (a, b, c) = stocked(world, "mag-a", "mag-b", "mag-c")
    token, got = run_routed(world, {"workspace": wid}, objects=[c, a])
    assert got["route"]["rule"] == "workspace"
    answer = read(world, token, wid)
    assert answer["selection"] == "explicit" and refs(answer) == ["mag-c", "mag-a"]
    assert answer["withheld"] == 0 and answer["missing"] == 0
    assert "mag-b" not in json.dumps(answer) and b not in json.dumps(answer)


def test_left_out_means_all_it_holds(world):  # noqa: F811
    wid, _ = stocked(world, "mag-a", "mag-b")
    token, _ = run_routed(world, {"workspace": wid})
    answer = read(world, token, wid)
    assert answer["selection"] == "all" and refs(answer) == ["mag-a", "mag-b"]
    assert "selection" not in routed_act(world)["detail"], "recorded as it always was"


def test_leaving_it_out_keeps_following_the_manifest(world):  # noqa: F811
    wid, _ = stocked(world, "mag-a")
    token, _ = run_routed(world, {"workspace": wid})
    wm.add_object(world["root"], wid, {"object": reference("magnet", "mag-later")})
    assert refs(read(world, token, wid)) == ["mag-a", "mag-later"]


def test_an_empty_selection_selects_nothing_and_is_not_everything(world):  # noqa: F811
    wid, _ = stocked(world, "mag-a")
    token, _ = run_routed(world, {"workspace": wid}, objects=[])
    answer = read(world, token, wid)
    assert answer["selection"] == "explicit" and answer["objects"] == []
    assert "mag-a" not in json.dumps(answer)


def test_a_whole_workspace_can_be_selected_at_the_bound(world):  # noqa: F811
    magnets = [f"mag-{i}" for i in range(wm.MAX_OBJECTS)]
    wid, ids = stocked(world, *magnets)
    token, _ = run_routed(world, {"workspace": wid}, objects=list(reversed(ids)))
    assert refs(read(world, token, wid)) == list(reversed(magnets))


@pytest.mark.parametrize("bad", [
    None, "wob-0123456789abcdef", {"wob-0123456789abcdef": 1}, 7, [7], [None], [""],
    ["mag-a"], ["WOB-0123456789ABCDEF"], ["wob-0123456789abcde"],
    ["wob-0123456789abcdef\n"], [["wob-0123456789abcdef"]],
    ["wob-0123456789abcdef", "wob-0123456789abcdef"],
    [f"wob-{i:016x}" for i in range(wm.MAX_OBJECTS + 1)]])
def test_a_malformed_selection_is_400_and_leaves_nothing(world, bad):  # noqa: F811
    wid, _ = stocked(world, "mag-a")
    before = conversations(world)
    status, got = ask(world, {"workspace": wid}, objects=bad)
    assert status == 400, got
    assert conversations(world) == before and not world["sent"]
    assert not routed_acts(world)


@pytest.mark.parametrize("origin", ["magnet", "conversation"])
@pytest.mark.parametrize("objects", [[], ["wob-0123456789abcdef"], None])
def test_only_a_workspace_selects(world, origin, objects):  # noqa: F811
    ref = a_magnet(world) if origin == "magnet" else a_conversation(world, "Here")
    before = conversations(world)
    status, got = ask(world, {origin: ref}, objects=objects)
    assert status == 400, got
    assert "objects" in got["error"]
    assert conversations(world) == before and not world["sent"]


def test_an_object_of_nothing_or_of_another_workspace_is_refused(world):  # noqa: F811
    wid, (a,) = stocked(world, "mag-a")
    _, (other,) = stocked(world, "mag-elsewhere")
    nothing = "wob-0123456789abcdef"
    before = conversations(world)
    for bad in ([other], [nothing], [a, other]):
        status, got = ask(world, {"workspace": wid}, objects=bad, op="kept-free")
        assert status == 422 and got["refused"] is True, got
        assert a not in got["objects"]
    assert conversations(world) == before and not world["sent"]
    assert not routed_acts(world)
    status, got = ask(world, {"workspace": wid}, objects=[a], op="kept-free")
    assert status == 200, "a refusal keeps no key"


@pytest.mark.parametrize("gone, code", [("deleted", 410), ("absent", 404)])
def test_a_workspace_that_is_not_there_is_said_before_its_objects(world, gone, code):  # noqa: F811
    wid, (a,) = stocked(world, "mag-a")
    if gone == "deleted":
        wm.delete(world["root"], wid)
    else:
        wid = "wsp-nobody"
    status, got = ask(world, {"workspace": wid}, objects=[a])
    assert status == code, got


def test_selecting_routes_nothing(world):  # noqa: F811
    """No Conversation of a selected Magnet, and an override still overrides."""
    mid = a_magnet(world)
    wid = a_workspace(world, reference("magnet", mid), reference("magnet", "mag-b"))
    oid = wm.object_id("magnet", mid)
    own = routed(world, {"workspace": wid}, objects=[oid])
    assert own["route"]["rule"] == "workspace"
    elsewhere = a_conversation(world, "Elsewhere")
    over = routed(world, {"workspace": wid}, objects=[oid],
                  destination={"conversation": elsewhere})
    assert over["route"]["rule"] == "destination"
    assert over["route"]["conversation"] == elsewhere
    answer = read(world, a_run(world, over["expectations"][0]), wid)
    assert refs(answer) == [mid]


def test_a_selection_leaves_the_manifest_as_it_was(world):  # noqa: F811
    """A result is not curated, and neither is a selection."""
    wid, (a, _) = stocked(world, "mag-a", "mag-b")
    before = wm.held(world["root"], wid)["objects"]
    routed(world, {"workspace": wid}, objects=[a])
    assert wm.held(world["root"], wid)["objects"] == before


def test_the_answer_does_not_carry_the_selection(world):  # noqa: F811
    wid, (a,) = stocked(world, "mag-a")
    assert a not in json.dumps(routed(world, {"workspace": wid}, objects=[a]))


# -- what is recorded ---------------------------------------------------------

@pytest.mark.parametrize("route", ["workspace", "destination"])
def test_the_record_keeps_no_object_id_and_a_destination_no_workspace(world, route):  # noqa: F811
    wid, (a, b) = stocked(world, "mag-a", "mag-b")
    more = ({"destination": {"conversation": a_conversation(world, "Elsewhere")}}
            if route == "destination" else {})
    routed(world, {"workspace": wid}, objects=[b, a], **more)
    detail = routed_act(world)["detail"]
    said = json.dumps(detail)
    assert a not in said and b not in said and "wob-" not in said
    assert "mag-a" not in said and "mag-b" not in said
    assert (wid in said) == (route == "workspace")
    assert detail["selection"] == [commands.selection_digest(wid, b),
                                   commands.selection_digest(wid, a)]


def test_the_routing_digest_is_not_changed_by_a_selection(world):  # noqa: F811
    from mentis.conversation import anchors
    wid, (a,) = stocked(world, "mag-a")
    routed(world, {"workspace": wid}, objects=[a])
    assert routed_act(world)["detail"]["digest"] == anchors.digest(
        {"from": ["workspace", wid], "destination": None})


def test_a_selection_digest_is_of_that_workspace():
    oid = wm.object_id("magnet", "mag-a")
    assert commands.selection_digest("wsp-a", oid) != commands.selection_digest(
        "wsp-b", oid)


# -- replay -------------------------------------------------------------------

def test_a_retry_of_the_selection_replays_and_starts_nothing(world):  # noqa: F811
    wid, (a, b) = stocked(world, "mag-a", "mag-b")
    _, first = ask(world, {"workspace": wid}, objects=[b, a], op="same")
    status, again = ask(world, {"workspace": wid}, objects=[b, a], op="same")
    assert status == 200 and again["replayed"] and again["post"] == first["post"]
    assert len(world["sent"]) == 1
    assert len(routed_acts(world)) == 1


@pytest.mark.parametrize("first, then", [
    ("ab", "a"), ("ab", "ba"), ("a", "ab"), ("a", "b"), ("a", ""), ("", "a"),
    ("a", None), (None, "a"), (None, "")])
def test_a_retry_cannot_change_the_selection(world, first, then):  # noqa: F811
    wid, (a, b) = stocked(world, "mag-a", "mag-b")
    pick = {"a": a, "b": b}

    def selecting(chosen):
        return {} if chosen is None else {"objects": [pick[c] for c in chosen]}
    status, got = ask(world, {"workspace": wid}, op="same", **selecting(first))
    assert status == 200, got
    status, again = ask(world, {"workspace": wid}, op="same", **selecting(then))
    assert status == 422 and again["refused"] is True, again
    assert len(world["sent"]) == 1
    token = a_run(world, got["expectations"][0])
    expected = ([f"mag-{c}" for c in first] if first is not None
                else ["mag-a", "mag-b"])
    assert refs(read(world, token, wid)) == expected


def test_a_retry_holds_after_the_object_was_taken_out(world):  # noqa: F811
    wid, (a, _) = stocked(world, "mag-a", "mag-b")
    _, first = ask(world, {"workspace": wid}, objects=[a], op="same")
    wm.remove_object(world["root"], wid, a)
    status, again = ask(world, {"workspace": wid}, objects=[a], op="same")
    assert status == 200 and again["post"] == first["post"], again


def test_a_retry_holds_after_the_workspace_was_deleted(world):  # noqa: F811
    wid, (a,) = stocked(world, "mag-a")
    _, first = ask(world, {"workspace": wid}, objects=[a], op="same")
    wm.delete(world["root"], wid)
    status, again = ask(world, {"workspace": wid}, objects=[a], op="same")
    assert status == 200 and again["post"] == first["post"], again
    status, _ = ask(world, {"workspace": wid}, objects=[], op="same")
    assert status == 422


def test_a_malformed_retry_is_still_malformed(world):  # noqa: F811
    wid, (a,) = stocked(world, "mag-a")
    ask(world, {"workspace": wid}, objects=[a], op="same")
    status, _ = ask(world, {"workspace": wid}, objects=[a, a], op="same")
    assert status == 400


# -- a manifest that changes after the request ----------------------------------

def test_what_is_added_later_is_not_selected(world):  # noqa: F811
    wid, (a, _) = stocked(world, "mag-a", "mag-b")
    token, _ = run_routed(world, {"workspace": wid}, objects=[a])
    wm.add_object(world["root"], wid, {"object": reference("magnet", "mag-later")})
    answer = read(world, token, wid)
    assert refs(answer) == ["mag-a"] and "mag-later" not in json.dumps(answer)
    assert answer["revision"] > 1


def test_a_reorder_does_not_change_the_selected_order(world):  # noqa: F811
    wid, (a, b, c) = stocked(world, "mag-a", "mag-b", "mag-c")
    token, _ = run_routed(world, {"workspace": wid}, objects=[c, a])
    wm.reorder(world["root"], wid, {"order": [a, b, c]})
    assert refs(read(world, token, wid)) == ["mag-c", "mag-a"]


def test_a_removed_object_is_missing_and_reveals_no_replacement(world):  # noqa: F811
    wid, (a, b, c) = stocked(world, "mag-a", "mag-b", "mag-c")
    token, _ = run_routed(world, {"workspace": wid}, objects=[a, b, c])
    wm.remove_object(world["root"], wid, b)
    wm.add_object(world["root"], wid, {"object": reference("magnet", "mag-new")})
    answer = read(world, token, wid)
    assert refs(answer) == ["mag-a", None, "mag-c"], "its place is kept"
    assert answer["objects"][1] == {
        "curated": True, "missing": True,
        "reason": "selected by the request, and this workspace no longer holds it"}
    assert answer["missing"] == 1 and answer["withheld"] == 0
    said = json.dumps(answer)
    assert "mag-new" not in said and "mag-b" not in said and b not in said


def test_one_curated_again_is_the_same_object(world):  # noqa: F811
    """An id is a kind and a ref: this is that reference, not a replacement."""
    wid, (a,) = stocked(world, "mag-a")
    token, _ = run_routed(world, {"workspace": wid}, objects=[a])
    wm.remove_object(world["root"], wid, a)
    assert read(world, token, wid)["missing"] == 1
    wm.add_object(world["root"], wid, {"object": reference("magnet", "mag-a")})
    answer = read(world, token, wid)
    assert refs(answer) == ["mag-a"] and answer["missing"] == 0


def test_a_deleted_workspace_answers_no_selection(world):  # noqa: F811
    wid, (a,) = stocked(world, "mag-a")
    token, _ = run_routed(world, {"workspace": wid}, objects=[a])
    wm.delete(world["root"], wid)
    answer = read(world, token, wid)
    assert answer["state"] == "deleted" and answer["objects"] == []
    assert answer["selection"] == "explicit"


# -- it is no reach, and the worker cannot change it ----------------------------

def test_a_selection_does_not_bring_a_reference_into_reach(world):  # noqa: F811
    outside = a_conversation(world, "Outside")
    theirs = say(world, outside, "Not for this run")["turn"]
    ref = f"live:{theirs}:key"
    wid = a_workspace(world, reference("report", ref), reference("magnet", "mag-b"))
    oid = wm.object_id("report", ref)
    token, _ = run_routed(world, {"workspace": wid}, objects=[oid])
    answer = read(world, token, wid)
    assert answer["objects"] == [{"kind": "report", "curated": True, "withheld": True,
                                  "reason": "outside this run's reach"}]
    assert answer["withheld"] == 1 and answer["missing"] == 0
    said = json.dumps(answer)
    assert theirs not in said and oid not in said and "mag-b" not in said


def test_what_was_not_selected_is_not_counted(world):  # noqa: F811
    outside = a_conversation(world, "Outside")
    theirs = say(world, outside, "Not for this run")["turn"]
    wid = a_workspace(world, reference("magnet", "mag-a"),
                      reference("report", f"live:{theirs}:key"))
    oid = wm.object_id("magnet", "mag-a")
    token, _ = run_routed(world, {"workspace": wid}, objects=[oid])
    answer = read(world, token, wid)
    assert refs(answer) == ["mag-a"] and answer["withheld"] == 0


def test_the_worker_cannot_widen_it(world):  # noqa: F811
    wid, (a, b) = stocked(world, "mag-a", "mag-b")
    token, _ = run_routed(world, {"workspace": wid}, objects=[a])
    status, answer = door(world, token, workspace=wid, objects=[a, b],
                          selection=None)
    assert status == 200 and refs(answer) == ["mag-a"], answer


def test_a_delegated_child_reads_what_its_ancestor_selected(world):  # noqa: F811
    wid, (a, _) = stocked(world, "mag-a", "mag-b")
    token, _ = run_routed(world, {"workspace": wid}, objects=[a])
    status, handed = door(world, token, op="delegate", participant=world["agent"],
                          work="Do the part")
    assert status == 200, handed
    child = a_run(world, handed["expectation"])
    assert refs(read(world, child, wid)) == ["mag-a"]


def test_a_selection_gives_no_way_into_another_workspace(world):  # noqa: F811
    wid, (a,) = stocked(world, "mag-a")
    other, _ = stocked(world, "mag-a")
    token, _ = run_routed(world, {"workspace": wid}, objects=[a])
    assert "mag-a" not in refused(door(world, token, workspace=other))


def test_it_adds_no_operation():
    """Selecting is the request door's, and reading is the read it already was."""
    from mentis.worker import OPERATIONS
    assert {op for op in OPERATIONS if "select" in op or "workspace" in op} == {
        "workspace_objects"}
