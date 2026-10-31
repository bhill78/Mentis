"""Stage 1c: the composer's, a notification's and `@`'s narrow reads.

What holds, through the real HTTP routes over a fixture Brain:

  * `GET /api/conversations/<id>?fields=` answers only the fields asked for,
    each exactly as the full read (`?batch=0`) gives it, and nothing owed;
    an unknown field, no field, or something that is not a Conversation is
    refused by name; the full read is unchanged;
  * `GET /fluid/api/names?ids=` gives each id's name in the order asked --
    a Conversation's current name, a Topic's, a Participant's alias -- and
    null for an id the record does not hold;
  * `GET /fluid/api/participants?q=&runtimes=1` adds what each returned name
    declared runs its work, by `/api/participants`' rule; without it the
    answer is what it was.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from tests._loop import a_conversation, post, say, world  # noqa: F401

#: Fluid's routes want the interface's header too; conftest adds it to
#: `/api/` paths only.
CLIENT = {"X-Mentis-Client": "1"}


def _get_status(world, path):
    req = urllib.request.Request(world["base"] + path, headers=CLIENT)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(world, path):
    status, body = _get_status(world, path)
    assert status == 200, (status, body)
    return body


def fluid_post(world, path, payload):
    req = urllib.request.Request(
        world["base"] + path, data=json.dumps(payload).encode(),
        headers={**CLIENT, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _place(world):
    """A Conversation with two people, a Topic, a post filed under it and
    something owed -- so the full read has more than the narrow one."""
    cv = world["cv"]
    owner = world["who"]["@brian"]
    cid = a_conversation(world, "Narrow reads")
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=owner)
    cv.declare_runtime_default(bob, "claude", by=owner,
                               because="declared claude as the default")
    topic = post(world, f"/api/conversations/{cid}/topics",
                 {"name": "Lookup", "author": owner})["topic"]
    said = say(world, cid, "please look", action="ask-participant",
               dispatch=[{"participant": bob, "work": "look"}])
    assert "error" not in said, said
    return cid, bob, topic


def test_fields_answers_only_what_is_asked_in_the_full_reads_shape(world):
    cid, bob, topic = _place(world)
    full = get(world, f"/api/conversations/{cid}?batch=0")
    assert full["owed"], "the fixture owes something, so the full read is bigger"
    narrow = get(world, f"/api/conversations/{cid}"
                        "?fields=name,participants,topics")
    assert set(narrow) == {"id", "name", "participants", "topics"}
    assert narrow["id"] == cid
    assert narrow["name"] == full["name"] == "Narrow reads"
    assert narrow["participants"] == full["participants"]
    assert narrow["topics"] == full["topics"]
    assert any(p["participant"] == bob and p["default_runtime"] == "claude"
               and p["runtime_mode"] == "default"
               for p in narrow["participants"])
    assert [t["id"] for t in narrow["topics"]] == [topic]
    assert len(json.dumps(narrow)) < len(json.dumps(full))


def test_fields_one_at_a_time(world):
    cid, _bob, _topic = _place(world)
    assert set(get(world, f"/api/conversations/{cid}?fields=topics")) == \
        {"id", "topics"}
    got = get(world, f"/api/conversations/{cid}?fields=name,about")
    assert got == {"id": cid, "name": "Narrow reads", "about": got["about"]}


def test_fields_refuses_what_it_cannot_answer(world):
    cid, bob, _topic = _place(world)
    _, unknown = _get_status(world, f"/api/conversations/{cid}?fields=owed")
    assert "no such field: 'owed'" in unknown["error"]
    _, none = _get_status(world, f"/api/conversations/{cid}?fields=,")
    assert "name the fields" in none["error"]
    _, other = _get_status(world, f"/api/conversations/{bob}?fields=name")
    assert "not a conversation" in other["error"]


def test_fields_absent_leaves_the_full_read_as_it_was(world):
    cid, _bob, _topic = _place(world)
    full = get(world, f"/api/conversations/{cid}?batch=0")
    for key in ("participants", "topics", "owed", "failures", "turns",
                "turns_total", "instructions", "batch"):
        assert key in full


def test_names_batch(world):
    cid, bob, topic = _place(world)
    owner = world["who"]["@brian"]
    fluid_post(world, f"/fluid/api/conversations/{cid}/name",
         {"author": owner, "name": "Renamed"})
    got = get(world, f"/fluid/api/names?ids={topic},{cid},{bob},ent-000000000000")
    assert list(got["names"]) == [topic, cid, bob, "ent-000000000000"]
    assert got["names"][cid] == "Renamed", "a renamed Conversation as it now reads"
    assert got["names"][topic] == "Lookup"
    assert got["names"][bob] == "@Bob"
    assert got["names"]["ent-000000000000"] is None
    status, refused = _get_status(world, "/fluid/api/names")
    assert status == 400 and "name what to read" in refused["error"]


def test_participants_search_with_runtimes(world):
    _cid, bob, _topic = _place(world)
    plain = get(world, "/fluid/api/participants?q=bo")
    assert [r["id"] for r in plain["participants"]] == [bob]
    assert set(plain["participants"][0]) == {"id", "alias", "about"}
    got = get(world, "/fluid/api/participants?q=bo&runtimes=1")
    row = got["participants"][0]
    assert row["default_runtime"] == "claude"
    assert row["runtime_mode"] == "default"
    everyone = get(world, "/fluid/api/participants?runtimes=1")
    brian = next(r for r in everyone["participants"]
                 if r["id"] == world["who"]["@brian"])
    assert brian["default_runtime"] is None
    assert brian["runtime_mode"] in ("undeclared", "auto")
