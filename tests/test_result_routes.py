"""The /api/work result bindings as the server actually answers them.

The reviewed projection package verified the reader; these are the integration
seam it could not reach, because it edited no shared route file: the owner and
other-viewer overviews over real HTTP, the detail page's group and item
continuation, the 409 a moved cursor is answered with, and that no response
anywhere carries the internal `_result_index`.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from mentis import artifacts
from mentis.operational import current_work as cw
from mentis.spine import held
from tests._loop import get, world  # noqa: F401
from tests.test_result_destinations import ask, claim, result


@pytest.fixture(autouse=True)
def fresh_models():
    cw.forget()
    yield
    cw.forget()


def refused(w, path):
    """The status and body of a read the server refuses."""
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(w["base"] + path)
    return caught.value.code, json.loads(caught.value.read())


def shown(body, exp):
    return next(i for i in body["items"] if i["expectation"] == exp)


def all_items(page):
    return [i for g in page["groups"] for i in g["items"]]


def nowhere(body):
    """Nothing internal is on the wire, however deeply it sits."""
    return "_result_index" not in json.dumps(body)


@pytest.mark.parametrize("viewer", ["owner", "other"])
def test_overview_summarises_results_bounded_and_keeps_the_index_off_the_wire(world, viewer):
    exp = ask(world)
    r = result(world, exp, count=6)
    who = (world["who"]["@brian"] if viewer == "owner" else world["steward"])
    body = get(world, f"/api/work?viewer={who}")
    summary = shown(body, exp)["result_summary"]
    group = summary["groups"][0]
    # 8 x 4 for a summary: the page is bounded, and what it left out is counted
    # from the structure, not guessed from what was read.
    assert len(group["items"]) == 4
    assert group["total_items"] == 6 and group["omitted_items"] == 2
    assert summary["total_groups"] == 1 and summary["omitted_groups"] == 0
    assert summary["availability_checked_at"]
    assert all(i["available"] and i["artifact"]["state"] == "held"
               for i in group["items"])
    # The exact Turn this run's return mapped, not a nearby narrative reply.
    assert [t["turn"] for t in shown(body, exp)["update_turns"]] == [r["reply"]]
    assert {i["ref"] for i in group["items"]} <= set(r["refs"])
    assert nowhere(body)


def test_other_viewers_shared_answer_holds_structure_and_availability_is_read_again(world):
    """The cached answer is record-derived only: byte loss that writes nothing
    to the record still changes the next response (adm-55f5877ffeac 3)."""
    exp = ask(world)
    r = result(world, exp)
    cv = world["cv"]
    path = f"/api/work?viewer={world['steward']}"
    first = get(world, path)
    steady = cv.corpus.steady
    assert all_items(shown(first, exp)["result_summary"])[0]["available"]
    held.path(cv.corpus.root, r["blobs"][0]["digest"]).unlink()
    second = get(world, path)
    item = all_items(shown(second, exp)["result_summary"])[0]
    assert cv.corpus.steady == steady      # the record did not move
    assert not item["available"] and not item["actionable"]
    assert item["artifact"]["state"] == "held-but-missing"
    assert "url" not in item["artifact"] and item["reason"]
    assert nowhere(second)


def test_detail_pages_groups_then_one_groups_items(world):
    exp = ask(world)
    first = result(world, exp, count=25, generation=1)
    result(world, exp, count=2, generation=2)
    body = get(world, f"/api/work/{exp}")
    page = body["result_groups"]
    assert "_result_index" not in body and nowhere(body)
    assert page["total_groups"] == 2 and page["omitted_groups"] == 0
    big = next(g for g in page["groups"]
               if g["id"] == next(g["id"] for g in page["groups"]
                                  if g["total_items"] == 25))
    # 20 x 20 for a detail page, and the rest is reachable through this
    # group's own cursor -- never through an offset.
    assert len(big["items"]) == 20 and big["omitted_items"] == 5
    assert big["next_items_after"]
    rest = get(world, f"/api/work/{exp}?result_group={big['id']}"
                      f"&items_after={big['next_items_after']}")["result_groups"]
    assert len(rest["groups"]) == 1 and rest["groups"][0]["id"] == big["id"]
    assert len(rest["groups"][0]["items"]) == 5
    assert rest["groups"][0]["next_items_after"] is None
    # A continuation does not re-show what the first page showed.
    seen = {i["ref"] for i in big["items"]}
    assert not seen & {i["ref"] for i in rest["groups"][0]["items"]}
    assert len(seen | {i["ref"] for i in rest["groups"][0]["items"]}) == 25
    assert set(first["refs"]) >= seen


def test_detail_keeps_every_old_field_and_a_non_trunk_is_still_404(world):
    exp = ask(world)
    r = result(world, exp)
    body = get(world, f"/api/work/{exp}")
    assert body["expectation"] == exp and "state" in body and "title" in body
    code, said = refused(world, f"/api/work/{r['start']}")
    assert code == 404 and said["error"]


@pytest.mark.parametrize("cursor", ["results_before=broken",
                                    "result_group=g-nope",
                                    "results_before=broken&result_group=g-1"])
def test_a_cursor_that_no_longer_names_this_read_is_409_refresh(world, cursor):
    exp = ask(world)
    result(world, exp, count=25)
    code, said = refused(world, f"/api/work/{exp}?{cursor}")
    # Its own kind: not a BadQuery (the query was well formed), and not a
    # Conversation write conflict borrowing 409.
    assert code == 409
    assert said["kind"] == "ResultsRefreshRequired"
    assert said["refresh_results"] is True and "refresh" in said["error"]


def test_an_item_cursor_from_another_work_is_refused_not_answered(world):
    mine, theirs = ask(world), ask(world, "another piece of work")
    result(world, mine, count=25)
    result(world, theirs, count=25)
    group = next(g for g in get(world, f"/api/work/{theirs}")["result_groups"]["groups"]
                 if g["next_items_after"])
    code, said = refused(world, f"/api/work/{mine}?result_group={group['id']}"
                                f"&items_after={group['next_items_after']}")
    assert code == 409 and said["kind"] == "ResultsRefreshRequired"


def test_an_unverified_reference_gets_no_descriptor_through_the_route(world):
    exp = ask(world)
    r = result(world, exp)
    claim(world, exp, r["refs"] + ["adm-000000000000"])
    body = get(world, f"/api/work/{exp}")
    foreign = next(i for i in all_items(body["result_groups"])
                   if i["ref"] == "adm-000000000000")
    assert foreign["association"] == "unverified" and not foreign["actionable"]
    assert "artifact" not in foreign
    assert artifacts  # the reach code itself is untouched by this binding
