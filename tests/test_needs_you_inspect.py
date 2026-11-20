"""What a Needs You request is about: `GET /fluid/api/needs-you/about`
(`mentis.fluid.inspect`), for every kind of request the owner can be asked.

The owner's requirement (2026-11-20, "Needs You: inspect before deciding"):
the subject is told apart from its evidence, each reference is resolved by
its exact id, what cannot be read says so, nothing is found by title, and
the read changes nothing.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from mentis.conversation import text
from mentis.fluid import inspect
from tests._loop import world  # noqa: F401
from tests.needs_you_kinds import GONE, build


def get(world, path):
    req = urllib.request.Request(world["base"] + path, headers={"X-Mentis-Client": "1"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def about(world, *ids):
    got = get(world, "/fluid/api/needs-you/about?ids=" + ",".join(ids))
    assert [a["id"] for a in got["about"]] == list(ids), "in the order asked"
    return got["about"] if len(ids) != 1 else got["about"][0]


def ids_of(rows):
    return [r["id"] for r in rows]


@pytest.fixture()
def kinds(world):
    return build(world)


def test_every_open_item_says_what_kind_it_is_and_what_is_asked(world, kinds):
    w = kinds
    items = get(world, "/fluid/api/needs-you/items")["items"]
    by_key = {i["key"]: i for i in items}
    want = {w["form"]: "form", w["findings_decision"]: "findings", w["permission"]: "permission",
            w["adoption"]["ask"]: "adoption", w["input"]: "input", w["plain"]: "request",
            w["own"]: "decision"}
    assert set(want) <= set(by_key), "the fixture's seven kinds are all open"
    for key, kind in want.items():
        a = about(world, by_key[key]["asks"][0])
        assert a["kind"] == kind, key
        assert a["says"].startswith("@Coach "), "who asks, in words"
        assert not inspect.mentions(a["says"]) or kind == "request", "no id as what is asked"
        for r in a["subject"] + a["evidence"] + a["context"] + a["referenced"]:
            assert r["relation"] and r["state"] and "available" in r
            assert not inspect.mentions(r.get("label") or "") or r["type"] == "post", r


def test_an_adoption_request_names_the_record_and_what_it_rests_on(world, kinds):
    w = kinds
    a = about(world, w["adoption"]["ask"])
    assert ids_of(a["subject"]) == [w["rule"]], "the subject is the record to adopt, by its id"
    rule = a["subject"][0]
    assert (rule["type"], rule["kind"], rule["opens"]) == ("record", "lesson", "record")
    assert rule["label"] == "Strip dangling links before migrating a chart."
    assert rule["relation"] == "the record you would adopt"
    assert ids_of(a["evidence"]) == [w["evidence"]], "its evidence is what the record rests on"
    ev = a["evidence"][0]
    assert ev["type"] == "post" and ev["opens"] == "post" and ev["conversation"] == w["other"]
    assert ev["number"] == w["evidence_number"] and ev["conversation_name"] == "Evidence room"
    assert ev["label"] == "Measured the old chart loader: 41,211 rows, three rejects."
    assert w["rule"] not in ids_of(a["evidence"] + a["context"] + a["referenced"]), "the subject is not also its own evidence"


def test_never_a_record_with_the_same_words(world, kinds):
    """Two lessons say exactly the same thing. Each ask gets the one it names."""
    w = kinds
    adoption = about(world, w["adoption"]["ask"])
    own = about(world, w["own"])
    assert ids_of(adoption["subject"]) == [w["rule"]]
    assert ids_of(own["subject"]) == [w["twin"]]
    assert adoption["subject"][0]["label"] == own["subject"][0]["label"], "same words"
    assert w["twin"] not in json.dumps(adoption) and w["rule"] not in json.dumps(own)
    assert own["subject"][0]["relation"] == "what this is about"


def test_a_decision_about_findings_names_each_finding_and_the_work_it_came_from(world, kinds):
    w = kinds
    a = about(world, w["findings_decision"])
    assert ids_of(a["subject"]) == w["findings"], "each finding, in the order asked, by its own id"
    assert [r["label"] for r in a["subject"]] == ["Reconcile the base branch", "Rename the old flags"]
    assert all(r["type"] == "finding" and r["opens"] == "post" and r["post"] for r in a["subject"])
    posts = [r["post"] for r in a["subject"]]
    assert len(set(posts)) == 2 and w["findings_post"] not in posts, "each opens its own post, not the asking one"
    assert a["evidence"] == [], "the record names no evidence for it, so none is claimed"
    context = {r["relation"]: r["id"] for r in a["context"]}
    assert context == {"where it was asked": w["findings_post"],
                       "the work they were found during": w["originating"]}
    assert a["says"] == "@Coach asks what should happen to the 2 things found along the way."


def test_a_permission_question_is_about_its_operation(world, kinds):
    w = kinds
    q = world["cv"].decision_form(w["permission"])["questions"][0]["expectation"]
    a = about(world, q)
    assert a["kind"] == "permission" and a["subject"] == []
    op = a["operation"]
    assert op["summary"] == "Delete the old chart cache"
    assert op["command"] == "Remove-Item -Recurse C:\\charts\\cache", "the exact command, to inspect"
    assert op["within"] is False and op["outside"] == ["it deletes files"]
    assert a["says"] == "@Coach asks permission to delete the old chart cache."
    run = next(r for r in a["context"] if r["relation"] == "the run that asks")
    assert run["id"] == w["run"] and run["type"] == "run" and run["label"] == "@Coach's run"
    assert run["opens"] is None, "a run is named; its request's post is not opened in its place"


def test_a_form_names_no_subject_and_lists_what_its_words_name(world, kinds):
    w = kinds
    first, second = w["form_questions"]
    a = about(world, first)
    assert a == {**about(world, second), "id": first}, "a question answers for its whole form"
    assert a["kind"] == "form" and a["form"] == w["form"]
    assert a["subject"] == [] and a["evidence"] == [], "no role the record does not state"
    assert {r["relation"]: r["id"] for r in a["context"]} == {
        "where it was asked": w["asking"], "the request this work answers": w["request_turn"]}
    named = {r["id"]: r for r in a["referenced"]}
    assert list(named) == [w["rule"], w["evidence"], w["removed"], GONE], "every id in its words, in order"
    assert all(r["relation"] == "named in the request's words" for r in named.values())
    assert named[w["rule"]]["opens"] == "record" and named[w["evidence"]]["opens"] == "post"


def test_what_cannot_be_read_says_so_and_is_never_dropped(world, kinds):
    w = kinds
    named = {r["id"]: r for r in about(world, w["form_questions"][0])["referenced"]}
    deleted = named[w["removed"]]
    assert (deleted["state"], deleted["available"], deleted["opens"]) == ("deleted", False, None)
    assert deleted["why"] == "This post was deleted." and deleted["label"] is None, "its words are not shown"
    assert deleted["conversation_name"] == "Evidence room", "where it was is still said"
    missing = named[GONE]
    assert (missing["state"], missing["available"], missing["opens"], missing["label"]) == ("missing", False, None, None)
    assert missing["why"] == "This Brain holds nothing with this id."


def test_an_adoption_whose_record_is_gone_still_names_it(world, kinds):
    """The subject cannot be read: it is listed as unreadable, not left out."""
    w = kinds
    cv, owner = world["cv"], world["who"]["@brian"]
    turn = cv.say(w["cid"], w["coach"], [text("Please adopt it.")], addressed_to=[owner])
    ask = cv.expect(turn, of=owner, kind="decision", by=w["coach"], material=[GONE],
                    because="it is ready")
    a = about(world, ask)
    assert ids_of(a["subject"]) == [GONE]
    assert a["subject"][0]["state"] == "missing" and a["subject"][0]["available"] is False


def test_an_input_and_a_plain_request(world, kinds):
    w = kinds
    a = about(world, w["input"])
    assert a["kind"] == "input"
    assert a["says"] == "@Coach waits for you to fill in the form “cutover”."
    r = about(world, w["plain"])
    assert r["kind"] == "request" and r["subject"] == []
    assert ids_of(r["context"]) == [w["plain_post"]]
    assert ids_of(r["referenced"]) == [w["evidence"]], "the id in its post's words; the #1 beside it is not resolved"


def test_a_post_number_in_prose_is_not_a_reference():
    assert inspect.mentions("PURSUE: #2, #3, #5. See ent-0bc926494728 and adm-f15046f4e90d; "
                            "commit 082a7a8211751bb84c05515ec2cbe4386d4daf1a") == [
        "ent-0bc926494728", "adm-f15046f4e90d"]
    assert inspect.mentions("student-abcdef12 xent-0bc926494728 ent-12") == []


def test_not_a_request_is_said_per_id_and_bad_asks_are_refused(world, kinds):
    w = kinds
    got = about(world, w["own"], w["rule"], "opr-000000000000", w["run"])
    assert got[0]["kind"] == "decision"
    assert got[1] == {"id": w["rule"], "error": "the record holds no such act"}
    assert got[2] == {"id": "opr-000000000000", "error": "the record holds no such act"}
    assert got[3] == {"id": w["run"], "error": "not a request"}
    for bad in ("", "?ids="):
        with pytest.raises(urllib.error.HTTPError) as exc:
            get(world, "/fluid/api/needs-you/about" + bad)
        assert exc.value.code == 400


def test_reading_it_writes_nothing(world, kinds):
    w = kinds
    corpus = world["state"].corpus
    before = corpus.advance()
    items = get(world, "/fluid/api/needs-you/items")["items"]
    about(world, *[i["asks"][0] for i in items])
    assert corpus.advance() == before, "no entry, link or act was written by reading"
    assert {i["key"] for i in get(world, "/fluid/api/needs-you/items")["items"]} == {i["key"] for i in items}


def test_an_act_named_in_the_words_is_named_and_nothing_is_opened_in_its_place(world, kinds):
    """An act has no page of its own. The post it was recorded on is not it."""
    w = kinds
    cv, owner = world["cv"], world["who"]["@brian"]
    act = w["adoption"]["act"]
    turn = cv.say(w["cid"], w["coach"], [text(f"Was {act} right? And is {w['other']} the place for it?")],
                  addressed_to=[owner])
    ask = cv.expect(turn, of=owner, kind="clarification", by=w["coach"])
    named = {r["id"]: r for r in about(world, ask)["referenced"]}
    assert named[act]["type"] == "activity" and named[act]["opens"] is None
    assert named[act]["label"] == "a record of activity (adoption requested)"
    assert named[act]["why"] == "It has no page of its own to open."
    room = named[w["other"]]
    assert (room["type"], room["label"], room["opens"]) == ("conversation", "Evidence room", "conversation")


def test_an_input_is_about_the_exact_response_set_its_done_is_matched_against(world, kinds):
    """One post carries two forms. The wait names one response set
    (`detail.response_set`, what `request_input` records and a Done is matched
    against); that set, not the post, is the subject."""
    w = kinds
    cv, owner = world["cv"], world["who"]["@brian"]
    assert w["set"] != w["other_set"]
    a = about(world, w["input"])
    assert ids_of(a["subject"]) == [w["set"]], "the subject is the set the request names, by its id"
    form = a["subject"][0]
    assert (form["type"], form["label"], form["block"], form["part"]) == ("form", "cutover", "cutover", 0)
    assert form["post"] == w["input_post"] and form["opens"] == "post" and form["anchor"] == "block:cutover"
    assert w["other_set"] not in json.dumps(a), "the other form on the same post is not it"
    assert w["input_post"] not in ids_of(a["subject"]), "the post is where it is, not what it is"
    # a second wait, on the other form of the same post, names the other set
    second = cv.expect(w["input_post"], of=owner, kind="input", by=w["coach"], caused_by=w["parent"],
                       detail={"response_set": w["other_set"], "block": "rollback", "part": 0,
                               "ready_before": []})
    b = about(world, second)
    assert ids_of(b["subject"]) == [w["other_set"]] and b["subject"][0]["block"] == "rollback"
    assert b["says"] == "@Coach waits for you to fill in the form “rollback”."
    # the set is authoritative: a `block` written beside it that disagrees is not believed
    lying = cv.expect(w["input_post"], of=owner, kind="input", by=w["coach"], caused_by=w["parent"],
                      detail={"response_set": w["other_set"], "block": "cutover", "part": 0,
                              "ready_before": []})
    assert about(world, lying)["subject"][0]["block"] == "rollback"
    # a set that is not there is said, never replaced by the post or another set
    lost = cv.expect(w["input_post"], of=owner, kind="input", by=w["coach"], caused_by=w["parent"],
                     detail={"response_set": "ent-000000000000", "block": "cutover", "part": 0,
                             "ready_before": []})
    gone = about(world, lost)["subject"]
    assert ids_of(gone) == ["ent-000000000000"]
    assert gone[0]["state"] == "missing" and gone[0]["available"] is False and gone[0]["opens"] is None


def test_the_answer_says_which_brain_it_is_and_never_where_it_is(world, kinds):
    """Which Brain answered: its id and an instance fingerprint that tells a restored copy from
    its original. Never the Brain's folder: no answer of this route carries a filesystem path."""
    import hashlib
    w = kinds
    brain = get(world, "/api/brain?identity=1")
    root, cid = brain["corpus_path"], brain["corpus_id"]
    want = {"corpus_id": cid, "instance": hashlib.sha256(f"{cid}\0{root}\0".encode("utf-8")).hexdigest()[:16]}  # no restore recorded
    for path in ("/fluid/api/needs-you/about?ids=" + w["own"], "/fluid/api/needs-you/about?items=1"):
        got = get(world, path)
        assert got["brain"] == want, (path, got["brain"])
        whole = json.dumps(got)
        assert root not in whole and root.replace("\\", "/") not in whole, f"{path} carries the Brain's folder"
        assert "corpus_path" not in whole
    # a copy of the same Brain, served from elsewhere, has another fingerprint
    other = hashlib.sha256(f"{cid}\0{root}-restored".encode("utf-8")).hexdigest()[:16]
    assert other != want["instance"]


def test_the_list_and_its_details_come_in_one_answer_of_one_brain(world, kinds):
    """`?items=1`: Quiet Chat's Needs you draws its list and every item's details from ONE
    answer, so they are one Brain's by construction. The list is `needs-you/items` exactly;
    each item's details are its first ask's, as `?ids=` gives them."""
    both = get(world, "/fluid/api/needs-you/about?items=1")
    plain = get(world, "/fluid/api/needs-you/items")
    assert both["items"] == plain["items"], "the list is the plain list exactly"
    assert both["counts"] == plain["counts"] and both["words"] == plain["words"]
    assert both["items"], "the fixture asks the owner things"
    firsts = [(it["asks"] or [it["key"]])[0] for it in both["items"]]
    assert [a["id"] for a in both["about"]] == firsts, "one detail per item, by its first ask, in order"
    alone = get(world, "/fluid/api/needs-you/about?ids=" + ",".join(firsts))
    assert both["about"] == alone["about"], "the same details as asking for them by id"
    assert both["brain"] == alone["brain"] and both["brain"]["corpus_id"], "and it says which Brain answered"
