"""`workspace_objects`: a workspace's curated references, to work routed from it.

The selection check is the Caretaker's, under finding 5 of ent-ee00ea77ae6f: a run
reads W only if its request, or an ancestor in its delegation lineage, was routed
from W by `POST /fluid/api/requests`. Everything here goes through the real door with a real
grant, and every route through the real request door, because the check recomputes
that door's digest and would otherwise be testing a copy of it."""
from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request

import pytest

from mentis import artifacts
from mentis.conversation import versions
from mentis.fluid import workspace_manifest as wm
from mentis.worker import (ALL_TOOLS, CAPABILITY_HEADER, READ_ONLY, SESSION_SCOPE,
                           TOOLS, TRANSIENT_SCOPE, WORKSPACE_READ, _over,
                           permitted)
from mentis.web import _surface
from tests._loop import _answer, _continue, a_conversation, say, world  # noqa: F401
from tests.gravity_choice import owner_chooses
from tests.test_agent_request_routing import a_magnet, ask


def reference(kind, ref, *, source=("magnet", "mag-chosen"), **more):
    return {"kind": kind, "ref": ref,
            "provenance": {"source": {"kind": source[0], "ref": source[1]}, **more}}


def a_workspace(world, *objects, **extras):  # noqa: F811
    return wm.create(world["root"], {"name": "Evidence", "objects": list(objects),
                                     **extras})["id"]


def door(world, token, op=WORKSPACE_READ, **args):  # noqa: F811
    state = world["state"]
    req = urllib.request.Request(
        world["base"] + "/api/worker", method="POST",
        data=json.dumps({"corpus": state.path, "op": op, "args": args}).encode(),
        headers={"Content-Type": "application/json", CAPABILITY_HEADER: token})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


_runs = iter(range(10 ** 6))


def a_run(world, expectation=None, *, scope="worker", conversation=None,  # noqa: F811
          operations=None):
    """A grant minted as dispatch mints one, for the run carrying `expectation`."""
    cv, fnd = world["cv"], world["state"].agents.authority
    exp = cv._act(expectation) if expectation else None
    iid = f"run-{next(_runs)}"
    fnd.authorise_for(iid, {
        "scope": scope, "runtime": "claude",
        "participant": world.get("agent") or cv.create_participant("@Scribe"),
        **({"expectation": expectation} if expectation else {}),
        **({"operations": operations} if operations else {}),
        **({"conversation": conversation or (exp and exp["conversation"])}
           if exp or conversation else {})})
    return fnd._grant(iid, world["state"].path)


def routed(world, origin, **more):  # noqa: F811
    status, got = ask(world, origin, **more)
    assert status == 200, got
    return got


def run_routed(world, origin, **more):  # noqa: F811
    got = routed(world, origin, **more)
    return a_run(world, got["expectations"][0]), got


def refused(answer) -> str:
    status, body = answer
    assert status == 403, body
    return json.dumps(body)


# -- which workspace ----------------------------------------------------------

def test_a_run_reads_the_workspace_its_request_was_routed_from(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-one"))
    token, got = run_routed(world, {"workspace": wid})
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer
    assert answer["state"] == "held" and answer["workspace"] == wid
    assert answer["withheld"] == 0
    assert [o["ref"] for o in answer["objects"]] == ["mag-one"]
    assert answer["objects"][0]["curated"] is True
    assert answer["objects"][0]["provenance"]["source"] == {"kind": "magnet",
                                                            "ref": "mag-chosen"}
    assert world["cv"]._act(answer["routed_by"])["turn"] == got["post"]


def test_a_conversation_destination_does_not_lose_the_workspace(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-one"))
    elsewhere = a_conversation(world, "Elsewhere")
    token, got = run_routed(world, {"workspace": wid},
                            destination={"conversation": elsewhere})
    assert got["route"]["conversation"] == elsewhere
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer
    assert [o["ref"] for o in answer["objects"]] == ["mag-one"]


def test_a_magnet_destination_does_not_lose_the_workspace(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-one"))
    token, got = run_routed(world, {"workspace": wid},
                            destination={"magnet": a_magnet(world)})
    assert got["route"]["rule"] == "destination"
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer


def test_a_destination_routed_run_does_not_read_another_workspace(world):  # noqa: F811
    wid, other = a_workspace(world), a_workspace(world)
    token, _ = run_routed(world, {"workspace": wid},
                          destination={"conversation": a_conversation(world)})
    refused(door(world, token, workspace=other))


def test_a_delegated_child_reads_through_its_ancestor(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-one"))
    token, _ = run_routed(world, {"workspace": wid})
    status, handed = door(world, token, op="delegate", participant=world["agent"],
                          work="Do the part")
    assert status == 200, handed
    child = a_run(world, handed["expectation"])
    status, answer = door(world, child, workspace=wid)
    assert status == 200, answer
    assert [o["ref"] for o in answer["objects"]] == ["mag-one"]
    other = a_workspace(world)
    refused(door(world, child, workspace=other))


def test_a_grandchild_reads_through_both_handoffs(world):  # noqa: F811
    wid = a_workspace(world)
    token, _ = run_routed(world, {"workspace": wid},
                          destination={"conversation": a_conversation(world)})
    for who in (world["agent"], world["cv"].create_participant("@Helper")):
        status, handed = door(world, token, op="delegate", participant=who,
                              work="Do the part")
        assert status == 200, handed
        token = a_run(world, handed["expectation"])
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer


# -- what is not a handoff: a continuation, and where a finding was found -------

def coordinating(world, who=None):  # noqa: F811
    """A dispatch the owner lets organise work, so its run may pick up findings."""
    agent = world.setdefault("agent", world["cv"].create_participant("@Scribe"))
    return {"dispatch": [{"participant": who or agent, "work": "Do it",
                          "coordinate": True}]}


def a_continuation(world, cid, first, **more):  # noqa: F811
    """The owner replying to a run's result, which continues the request."""
    agent, cv = world["agent"], world["cv"]
    result = _answer(world, cid, cv._act(first)["turn"], agent)
    if more:
        got = routed(world, more.pop("origin"), replies_to=result, **more)
        again = got["expectations"][0]
    else:
        again = _continue(world, cid, result, agent)["expectations"][0]
    assert cv._act(again)["caused_by"] == first, "not a continuation of it"
    assert artifacts._delegation(cv, cv._act(again)) is None
    return again


def test_a_continuation_of_routed_work_is_refused(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-x"))
    first = routed(world, {"workspace": wid}, **coordinating(world))
    again = a_continuation(world, first["route"]["conversation"],
                           first["expectations"][0])
    assert "mag-x" not in refused(door(world, a_run(world, again), workspace=wid))


def test_what_a_continuation_delegates_is_refused_too(world):  # noqa: F811
    """The walk stops at the continuation: its child does not climb past it."""
    wid = a_workspace(world)
    first = routed(world, {"workspace": wid}, **coordinating(world))
    again = a_continuation(world, first["route"]["conversation"],
                           first["expectations"][0])
    status, handed = door(world, a_run(world, again), op="delegate",
                          participant=world["agent"], work="Do the part")
    assert status == 200, handed
    refused(door(world, a_run(world, handed["expectation"]), workspace=wid))


def test_a_continuation_routed_from_the_workspace_itself_reads_it(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-one"))
    first = routed(world, {"workspace": wid}, **coordinating(world))
    again = a_continuation(world, first["route"]["conversation"],
                           first["expectations"][0],
                           origin={"workspace": wid}, **coordinating(world))
    status, answer = door(world, a_run(world, again), workspace=wid)
    assert status == 200, answer
    assert world["cv"]._act(answer["routed_by"])["turn"] == world["cv"]._act(again)["turn"]


def test_a_continuation_routed_elsewhere_reads_only_where_it_was_routed_from(world):  # noqa: F811
    """A destination override on the continuation itself: it reads the workspace
    it was routed from, and not the one the work it continues was routed from."""
    wid, other = a_workspace(world), a_workspace(world, reference("magnet", "mag-o"))
    first = routed(world, {"workspace": wid}, **coordinating(world))
    cid = first["route"]["conversation"]
    again = a_continuation(world, cid, first["expectations"][0],
                           origin={"workspace": other},
                           destination={"conversation": cid},
                           **coordinating(world))
    run = a_run(world, again)
    status, answer = door(world, run, workspace=other)
    assert status == 200, answer
    assert [o["ref"] for o in answer["objects"]] == ["mag-o"]
    refused(door(world, run, workspace=wid))


def found_under(world, token, grant):  # noqa: F811
    status, got = door(world, token, op="record_discovered_work",
                       work="Found on the way", because="Not this work")
    assert status == 200, got
    owner_chooses(_surface(world["state"]), grant, got["expectation"])
    return got["expectation"]


def a_coordinating_run(world, expectation):  # noqa: F811
    cv = world["cv"]
    exp = cv._act(expectation)
    token = a_run(world, expectation, operations=["coordinate"])
    return token, {"expectation": expectation, "conversation": exp["conversation"],
                   "participant": world["agent"]}


def picked_up(world, token, finding):  # noqa: F811
    status, got = door(world, token, op="delegate", participant=world["agent"],
                       work="Take it", expectation=finding)
    assert status == 200 and got["picked_up"] is True, got
    return got


def test_a_finding_nobody_picked_up_does_not_read_where_it_was_found(world):  # noqa: F811
    wid = a_workspace(world)
    first = routed(world, {"workspace": wid}, **coordinating(world))
    token, grant = a_coordinating_run(world, first["expectations"][0])
    finding = found_under(world, token, grant)
    assert world["cv"]._act(finding)["caused_by"] == first["expectations"][0]
    refused(door(world, a_run(world, finding), workspace=wid))


def test_picked_up_work_reads_through_the_work_that_picked_it_up(world):  # noqa: F811
    """Found under work from nowhere, handed on by a run routed from W, and that
    destination override is what it follows."""
    wid = a_workspace(world, reference("magnet", "mag-one"))
    cid = a_conversation(world)
    plain = say(world, cid, "Something else", action="ask-participant",
                **coordinating(world))["expectations"][0]
    finding = found_under(world, *a_coordinating_run(world, plain))
    routed_work = routed(world, {"workspace": wid},
                         destination={"conversation": cid},
                         **coordinating(world))["expectations"][0]
    token, _ = a_coordinating_run(world, routed_work)
    picked_up(world, token, finding)
    run = a_run(world, finding)
    status, answer = door(world, run, workspace=wid)
    assert status == 200, answer
    assert world["cv"]._act(answer["routed_by"])["turn"] == world["cv"]._act(routed_work)["turn"]
    assert [o["ref"] for o in answer["objects"]] == ["mag-one"]


def test_picked_up_work_does_not_read_through_where_it_was_found(world):  # noqa: F811
    """Found under work routed from W, handed on by a run from nowhere."""
    wid = a_workspace(world)
    first = routed(world, {"workspace": wid}, **coordinating(world))
    cid = first["route"]["conversation"]
    finding = found_under(world, *a_coordinating_run(world, first["expectations"][0]))
    plain = say(world, cid, "Something else", action="ask-participant",
                **coordinating(world))["expectations"][0]
    token, _ = a_coordinating_run(world, plain)
    picked_up(world, token, finding)
    assert world["cv"]._act(finding)["caused_by"] == first["expectations"][0]
    refused(door(world, a_run(world, finding), workspace=wid))


def test_the_latest_pick_up_is_the_one_in_force(world):  # noqa: F811
    """As `_delegation` reads reach: an earlier handoff gives nothing afterwards."""
    wid = a_workspace(world)
    first = routed(world, {"workspace": wid}, **coordinating(world))
    cid = first["route"]["conversation"]
    token, grant = a_coordinating_run(world, first["expectations"][0])
    finding = found_under(world, token, grant)
    picked_up(world, token, finding)
    run = a_run(world, finding)
    assert door(world, run, workspace=wid)[0] == 200
    plain = say(world, cid, "Something else", action="ask-participant",
                **coordinating(world))["expectations"][0]
    world["cv"].assign(finding, world["agent"], by=world["who"]["@brian"],
                       because="picked up again",
                       detail={"picked_up_under": plain})
    refused(door(world, run, workspace=wid))


def test_another_workspace_is_refused(world):  # noqa: F811
    wid, other = a_workspace(world), a_workspace(world, reference("magnet", "mag-x"))
    token, _ = run_routed(world, {"workspace": wid})
    assert "mag-x" not in refused(door(world, token, workspace=other))


def test_a_bare_id_gives_nothing(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-x"))
    token = a_run(world, conversation=a_conversation(world))
    assert "carries no request" in refused(door(world, token, workspace=wid))


def test_being_in_its_conversation_without_the_lineage_is_not_enough(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-x"))
    first = routed(world, {"workspace": wid})
    cid = first["route"]["conversation"]
    agent = world["agent"]
    out = say(world, cid, "Something else, not from the workspace",
              action="ask-participant", addressed_to=[agent],
              dispatch=[{"participant": agent, "work": "Something else"}])
    token = a_run(world, out["expectations"][0])
    assert "mag-x" not in refused(door(world, token, workspace=wid))


def test_requests_from_a_magnet_or_a_conversation_select_no_workspace(world):  # noqa: F811
    wid = a_workspace(world)
    for origin in ({"magnet": a_magnet(world)},
                   {"conversation": a_conversation(world)}):
        token, _ = run_routed(world, origin)
        refused(door(world, token, workspace=wid))


def test_a_refusal_says_nothing_of_whether_the_workspace_exists(world):  # noqa: F811
    wid, gone = a_workspace(world), a_workspace(world)
    held = a_workspace(world)
    wm.delete(world["root"], gone)
    token, _ = run_routed(world, {"workspace": wid})
    words = [refused(door(world, token, workspace=w)).replace(w, "W")
             for w in (held, gone, "wsp-never-was")]
    assert len(set(words)) == 1


@pytest.mark.parametrize("bad", [None, "", 7, ["wsp-x"], "../wsp-x", "mag-x"])
def test_something_that_is_not_a_workspace_id_is_refused(world, bad):  # noqa: F811
    token, _ = run_routed(world, {"workspace": a_workspace(world)})
    refused(door(world, token, workspace=bad))


# -- which references ---------------------------------------------------------

def test_what_is_outside_reach_reveals_nothing(world):  # noqa: F811
    outside = a_conversation(world, "Outside")
    theirs = say(world, outside, "Not for this run")["turn"]
    objects = [reference("report", f"live:{theirs}:key"),
               reference("evidence", f"live:{theirs}:other"),
               reference("evidence", f"brain:{theirs}"),
               reference("report", theirs),
               reference("conversation", outside),
               reference("chat", outside),
               reference("file", "adm-0123456789ab"),
               reference("evidence", "adm-0123456789ab@0123456789ab[0:4]"),
               reference("other", f"see {theirs}"),
               reference("participant",
                         world["cv"].create_participant("@Outsider"))]
    for o in objects:
        o["observed"] = {"version": f"seen in {outside}"}
        o["provenance"]["by"] = world["cv"].create_participant("@Curator")
    wid = a_workspace(world, *objects)
    token, _ = run_routed(world, {"workspace": wid})
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer
    assert answer["withheld"] == len(objects) == len(answer["objects"])
    assert [o["kind"] for o in answer["objects"]] == [o["kind"] for o in objects]
    for o in answer["objects"]:
        assert set(o) == {"kind", "curated", "withheld", "reason"}
        assert o["withheld"] is True and o["curated"] is True and o["reason"]
    said = json.dumps(answer)
    assert theirs not in said and outside not in said
    assert "wob-" not in said, "an object's id is a hash of its ref"
    assert "adm-" not in said and "seen in" not in said


def test_what_is_in_reach_is_answered_in_order(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-one"))
    first = routed(world, {"workspace": wid})
    cid = first["route"]["conversation"]
    mine = say(world, cid, "A Turn here")["turn"]
    wm.add_object(world["root"], wid,
                  {"object": reference("report", f"live:{mine}:key")})
    wm.add_object(world["root"], wid, {"object": reference("evidence", mine)})
    wm.add_object(world["root"], wid, {"object": reference("conversation", cid)})
    status, answer = door(world, a_run(world, first["expectations"][0]),
                          workspace=wid)
    assert status == 200, answer
    assert answer["withheld"] == 0
    assert [o["ref"] for o in answer["objects"]] == [
        "mag-one", f"live:{mine}:key", mine, cid]


def test_a_destination_override_reaches_the_destination_only(world):  # noqa: F811
    """Routing from W selects W; it gives no reach into W's own Conversation."""
    wid = a_workspace(world)
    own = routed(world, {"workspace": wid})["route"]["conversation"]
    held = say(world, own, "In the workspace's own Conversation")["turn"]
    wm.add_object(world["root"], wid, {"object": reference("evidence", held)})
    elsewhere = a_conversation(world, "Elsewhere")
    here = say(world, elsewhere, "In the destination")["turn"]
    wm.add_object(world["root"], wid, {"object": reference("evidence", here)})
    token, _ = run_routed(world, {"workspace": wid},
                          destination={"conversation": elsewhere})
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer
    assert answer["withheld"] == 1
    assert [o.get("ref") for o in answer["objects"]] == [None, here]
    assert held not in json.dumps(answer) and own not in json.dumps(answer)


def test_a_delegated_child_reaches_its_line_and_not_the_conversation(world):  # noqa: F811
    wid = a_workspace(world)
    first = routed(world, {"workspace": wid})
    cid = first["route"]["conversation"]
    other = say(world, cid, "Somebody else's Turn here")["turn"]
    wm.add_object(world["root"], wid, {"object": reference("evidence", other)})
    wm.add_object(world["root"], wid, {"object": reference("conversation", cid)})
    wm.add_object(world["root"], wid,
                  {"object": reference("report", first["post"])})
    parent = a_run(world, first["expectations"][0])
    _, handed = door(world, parent, op="delegate", participant=world["agent"],
                     work="Do the part")
    status, answer = door(world, a_run(world, handed["expectation"]),
                          workspace=wid)
    assert status == 200, answer
    assert answer["withheld"] == 2
    assert [o.get("ref") for o in answer["objects"]] == [None, None, first["post"]]
    assert other not in json.dumps(answer)
    status, widened = door(world, parent, op="delegate", participant=world["agent"],
                           work="Another part", reach="conversation")
    assert status == 200, widened
    _, answer = door(world, a_run(world, widened["expectation"]), workspace=wid)
    assert answer["withheld"] == 0


def test_a_deleted_turn_is_withheld(world):  # noqa: F811
    wid = a_workspace(world)
    first = routed(world, {"workspace": wid})
    cid = first["route"]["conversation"]
    turn = say(world, cid, "Soon gone")["turn"]
    wm.add_object(world["root"], wid, {"object": reference("evidence", turn)})
    versions.delete(world["cv"], turn, by=world["who"]["@brian"])
    _, answer = door(world, a_run(world, first["expectations"][0]), workspace=wid)
    assert answer["withheld"] == 1 and turn not in json.dumps(answer)


def test_an_artifact_is_judged_as_read_artifact_judges_it(world):  # noqa: F811
    wid = a_workspace(world)
    first = routed(world, {"workspace": wid})
    cid = first["route"]["conversation"]
    run = a_run(world, first["expectations"][0])
    outside = a_conversation(world, "Outside")

    def attached(conversation):
        return artifacts.hold(world["cv"].corpus, world["cv"], b"hello there",
                              act=artifacts.RETURNED, actor=world["agent"],
                              source="test", door="test",
                              conversation=conversation)["admission"]

    here, there = attached(cid), attached(outside)
    wm.add_object(world["root"], wid, {"object": reference("file", here)})
    wm.add_object(world["root"], wid, {"object": reference("file", there)})
    status, answer = door(world, run, workspace=wid)
    assert status == 200, answer
    assert answer["withheld"] == 1
    assert [o.get("ref") for o in answer["objects"]] == [here, None]
    assert there not in json.dumps(answer)


def test_a_reference_in_reach_loses_only_what_its_provenance_cannot_say(world):  # noqa: F811
    outside = a_conversation(world, "Outside")
    theirs = say(world, outside, "Not for this run")["turn"]
    stranger = world["cv"].create_participant("@Stranger")
    wid = a_workspace(world, reference("magnet", "mag-one",
                                       source=("evidence", theirs), by=stranger,
                                       brain=theirs, at=5.0))
    token, _ = run_routed(world, {"workspace": wid})
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer
    assert answer["withheld"] == 0 and answer["provenance_withheld"] == 1
    got = answer["objects"][0]
    assert got["ref"] == "mag-one"
    assert got["provenance"]["source"]["withheld"] is True
    assert "ref" not in got["provenance"]["source"]
    assert "by" not in got["provenance"] and "brain" not in got["provenance"]
    assert got["provenance"]["at"] == 5.0
    said = json.dumps(answer)
    assert theirs not in said and stranger not in said


# -- what it answers ----------------------------------------------------------

def test_only_frozen_fields_and_no_layout(world):  # noqa: F811
    o = reference("magnet", "mag-one", extraProvenance="kept in the file")
    o["extraObject"] = {"nested": "kept in the file"}
    o["observed"] = {"version": "v1", "at": 3.0, "extraObserved": "kept"}
    o["provenance"]["source"]["extraSource"] = "kept"
    wid = a_workspace(world, o, extraManifest="kept in the file")
    token, _ = run_routed(world, {"workspace": wid})
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer
    assert set(answer) == {"workspace", "state", "objects", "withheld",
                           "provenance_withheld", "routed_by", "name", "revision",
                           "note", "selection", "missing"}
    got = answer["objects"][0]
    assert set(got) == {"id", "kind", "ref", "curated", "provenance", "observed"}
    assert got["observed"] == {"version": "v1", "at": 3.0}
    assert "kept" not in json.dumps({k: v for k, v in answer.items() if k != "note"})
    for field in sorted(wm.RESERVED):
        assert f'"{field}"' not in json.dumps(answer), field


def test_it_writes_nothing_and_resolves_nothing(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-does-not-exist"))
    token, _ = run_routed(world, {"workspace": wid})
    cv, before = world["cv"], len(world["cv"].history())
    entries = len(cv.corpus.all_entries())
    path = pathlib.Path(world["root"]) / "presentation" / wm.FOLDER / f"{wid}.json"
    text = path.read_text(encoding="utf-8")
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer
    assert [o["ref"] for o in answer["objects"]] == ["mag-does-not-exist"]
    assert len(cv.history()) == before and len(cv.corpus.all_entries()) == entries
    assert path.read_text(encoding="utf-8") == text
    assert WORKSPACE_READ in READ_ONLY


def test_a_deleted_workspace_says_so(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-one"))
    token, _ = run_routed(world, {"workspace": wid})
    wm.delete(world["root"], wid)
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer
    assert answer["state"] == "deleted" and answer["objects"] == []
    assert answer["deleted"] > 0


def test_a_missing_workspace_says_so(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-one"))
    token, _ = run_routed(world, {"workspace": wid})
    (pathlib.Path(world["root"]) / "presentation" / wm.FOLDER / f"{wid}.json").unlink()
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer
    assert answer["state"] == "missing" and answer["objects"] == []


def test_an_unreadable_workspace_says_so_and_quotes_nothing(world):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-one"))
    token, _ = run_routed(world, {"workspace": wid})
    path = pathlib.Path(world["root"]) / "presentation" / wm.FOLDER / f"{wid}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["objects"][0]["ref"] = "live:ent-secretsecret"
    path.write_text(json.dumps(data), encoding="utf-8")
    status, answer = door(world, token, workspace=wid)
    assert status == 200, answer
    assert answer["state"] == "unreadable" and answer["objects"] == []
    assert "secret" not in json.dumps(answer) and answer["reason"]
    path.write_text("{not json", encoding="utf-8")
    _, answer = door(world, token, workspace=wid)
    assert answer["state"] == "unreadable"


# -- which grants -------------------------------------------------------------

@pytest.mark.parametrize("scope", [TRANSIENT_SCOPE, SESSION_SCOPE])
def test_grants_without_the_operation_refuse(world, scope):  # noqa: F811
    wid = a_workspace(world, reference("magnet", "mag-x"))
    assert WORKSPACE_READ not in permitted(scope)
    got = routed(world, {"workspace": wid})
    token = a_run(world, got["expectations"][0], scope=scope)
    assert "is not admissible" in refused(door(world, token, workspace=wid))


@pytest.mark.parametrize("scope", ["worker", "organising", "intake", None,
                                   "no-such-scope"])
def test_every_dispatched_run_holds_it(scope):
    assert WORKSPACE_READ in permitted(scope)


def test_a_run_is_offered_it_over_the_bridge_and_an_unbounded_caller_is_not(world):  # noqa: F811
    assert WORKSPACE_READ in {t["name"] for t in ALL_TOOLS}
    assert WORKSPACE_READ not in {t["name"] for t in TOOLS}
    wid = a_workspace(world, reference("magnet", "mag-one"))
    token, _ = run_routed(world, {"workspace": wid})
    got = _over(world["base"], world["state"].path, WORKSPACE_READ,
                {"workspace": wid}, token)
    assert [o["ref"] for o in got["objects"]] == ["mag-one"]
