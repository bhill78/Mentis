"""WHAT THE SERVER PROMISES A PRESS THAT ASKS AGAIN (P4).

`apps/fluid-web/src/work/freshness.ts` re-reads one result group at the moment
a human presses a POST, a BRAIN RECORD or a CONVERSATION result, and moves
nobody unless that fresh answer still says the target is there. These are the
promises it is entitled to rest on, pinned at the route the press actually
calls -- `GET /api/work/<expectation>?result_group=<group>` -- rather than at
the reader underneath it.

The artifact half of this is already pinned by
`test_result_destinations.py::test_request_time_availability_moves_without_structural_cache_expiry`.
This is the half that was missing: a post, record or conversation that stops
being readable AFTER the page was drawn, answered again at request time, in
the record's own words.

Nothing here changes who may read what. The last test says so: the answer does
not depend on who asks, so a press that re-reads gains no reach by re-reading.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from mentis.conversation import text, versions
from mentis.operational import current_work as cw
from tests._loop import a_conversation, get, world  # noqa: F401
from tests.test_result_destinations import ask, claim, result

NOWHERE = "ent-ffffffffffff"


@pytest.fixture(autouse=True)
def fresh_models():
    cw.forget()
    yield
    cw.forget()


@pytest.fixture()
def referenced(world):
    """One Work whose claimed results are a post, a conversation, a record,
    a post that will be deleted, and an id this Brain does not hold."""
    cv, who = world["cv"], world["who"]["@brian"]
    exp = ask(world)
    r = result(world, exp)
    cid = a_conversation(world, "Somewhere else")
    doomed = cv.say(cid, who, [text("a post that will be deleted")])
    live = cv.say(cid, who, [text("a post that stays")])
    record = cv.corpus.write(kind="note", body={"text": "a durable note"},
                             attributed_to=who, written_by="fixture")
    claim(world, exp, [live, cid, record, doomed, NOWHERE], r["reply"])
    return {"exp": exp, "conversation": cid, "post": live, "record": record,
            "doomed": doomed, "group": r["reply"], "who": who}


def page(world, ref, *, group=None, viewer=None):
    who = viewer or ref["who"]
    path = f"/api/work/{ref['exp']}?viewer={who}"
    if group:
        path += f"&result_group={group}"
    body = get(world, path)
    return body, body["result_groups"]


def row(result_page, ref):
    return next(i for g in result_page["groups"] for i in g["items"]
                if i["ref"] == ref)


def refused(world, path):
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(world["base"] + path)
    return caught.value.code, json.loads(caught.value.read())


def test_each_non_artifact_result_says_what_opens_it_and_where(world, referenced):
    """The three words a press dispatches on, and the facts it goes to."""
    _, shown = page(world, referenced)

    post = row(shown, referenced["post"])
    assert post["available"] and post["actionable"] and post["reason"] is None
    assert post["inspection"]["opens"] == "post"
    assert post["inspection"]["state"] == "ok"
    assert post["inspection"]["conversation"] == referenced["conversation"]
    # The exact post and its number: a press goes to the post, not the top.
    assert post["inspection"]["post"] == referenced["post"]
    assert post["inspection"]["number"] == 2

    conversation = row(shown, referenced["conversation"])
    assert conversation["inspection"]["opens"] == "conversation"
    assert conversation["inspection"]["conversation"] == referenced["conversation"]
    assert conversation["available"]

    record = row(shown, referenced["record"])
    assert record["inspection"]["opens"] == "record"
    assert record["inspection"]["id"] == referenced["record"]
    assert record["available"]

    # Nothing claims to be an artifact, so the opener's describe read is never
    # the thing that would have to answer for these.
    for item in (post, conversation, record):
        assert item["kind"] != "artifact" and "artifact" not in item


def test_a_post_deleted_after_the_page_was_drawn_is_refused_when_it_is_pressed(
        world, referenced):
    """THE WHOLE POINT: the same group, read again, and the record's own words."""
    _, first = page(world, referenced, group=referenced["group"])
    assert row(first, referenced["doomed"])["available"]

    versions.delete(world["cv"], referenced["doomed"],
                    by=referenced["who"], because="no longer wanted")

    _, again = page(world, referenced, group=referenced["group"])
    gone = row(again, referenced["doomed"])
    assert gone["available"] is False and gone["actionable"] is False
    assert gone["inspection"]["opens"] is None
    assert gone["inspection"]["state"] == "deleted"
    assert gone["reason"] == gone["inspection"]["why"] == "This post was deleted."
    # Its neighbours are untouched: one target stopping being readable never
    # takes the rest of the group down with it.
    assert row(again, referenced["post"])["available"]
    assert row(again, referenced["conversation"])["available"]


def test_an_id_the_brain_does_not_hold_is_listed_and_unopenable(world, referenced):
    _, shown = page(world, referenced, group=referenced["group"])
    missing = row(shown, NOWHERE)
    assert missing["available"] is False and missing["inspection"]["opens"] is None
    assert missing["inspection"]["state"] == "missing"
    assert missing["reason"] == "This Brain holds nothing with this id."


def test_the_group_read_again_names_its_work_and_says_when_it_was_checked(
        world, referenced):
    """Both identities a late answer is matched against before it moves anybody."""
    body, shown = page(world, referenced, group=referenced["group"])
    assert body["expectation"] == referenced["exp"]
    assert [g["id"] for g in shown["groups"]] == [referenced["group"]]
    first = shown["availability_checked_at"]
    assert first
    _, again = page(world, referenced, group=referenced["group"])
    assert again["availability_checked_at"] >= first


def test_a_group_that_is_no_longer_there_is_refused_rather_than_answered_empty(
        world, referenced):
    """A press whose group has gone is told to read again, never handed an
    empty page it would read as 'there is nothing to open'."""
    code, body = refused(
        world, f"/api/work/{referenced['exp']}?viewer={referenced['who']}"
               f"&result_group={NOWHERE}")
    assert code == 409 and body["kind"] == "ResultsRefreshRequired"
    assert "refresh" in body["error"].lower()


def test_re_reading_gains_no_reach_it_did_not_have(world, referenced):
    """Asking again is a read of the same page by the same door. Another
    viewer is told exactly the same thing about what is readable, so nothing
    about authorisation is decided by WHEN a result is checked."""
    _, mine = page(world, referenced, group=referenced["group"])
    _, theirs = page(world, referenced, group=referenced["group"],
                     viewer=world["steward"])

    def readability(shown):
        # The group also carries this run's returned artifact, whose freshness
        # is the opener's own describe read; only the three kinds checked here.
        return {i["ref"]: (i["available"], i["inspection"]["opens"],
                           i["inspection"]["state"], i["reason"])
                for g in shown["groups"] for i in g["items"] if "inspection" in i}

    assert set(readability(mine)) == {
        referenced["post"], referenced["conversation"], referenced["record"],
        referenced["doomed"], NOWHERE}
    assert readability(mine) == readability(theirs)
