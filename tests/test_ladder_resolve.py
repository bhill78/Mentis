"""`GET /api/ladder/resolve`: what ONE EXACT reference is, said before anything
is recorded with it (the compact editor's "paste a link or id").

A disposable fixture Brain behind a real HTTP server (`tests/_loop.py`).
"""
from __future__ import annotations

from urllib.parse import quote

import pytest

from mentis import artifacts

from tests._loop import world, post, get  # noqa: F401


@pytest.fixture
def me(world):
    return world["who"]["@brian"]


def _resolve(world, **q):
    return get(world, "/api/ladder/resolve?" + "&".join(f"{k}={quote(str(v))}" for k, v in q.items()))


def test_a_record_resolves_to_its_words_kind_standing_and_who_recorded_it(world, me):
    rule = post(world, "/api/entries", {"kind": "rule", "body": {"text": "Deploy to TEST first."},
                                        "attributed_to": me, "establish": False})["entry"]
    got = _resolve(world, ref=rule)
    assert got["found"] is True and got["usable"] is True and got["ref"] == rule
    assert got["kind"] == "rule" and got["label"] == "Deploy to TEST first."
    assert got["status"] == "recorded" and got["by"] == "@brian"
    post(world, f"/api/entries/{rule}/establish", {"attributed_to": me, "because": "the owner said so"})
    assert _resolve(world, ref=rule)["status"] == "adopted"


def test_a_post_resolves_by_its_id_and_by_its_conversation_and_number(world, me):
    conv = post(world, "/api/conversations", {"name": "Release check"})["conversation"]
    post(world, f"/api/conversations/{conv}/turns", {"author": me, "text": "Is TEST ready?"})
    turn = post(world, f"/api/conversations/{conv}/turns", {"author": me, "text": "It is.\nSecond line."})["turn"]
    by_id = _resolve(world, ref=turn)
    assert by_id["found"] and by_id["usable"] and by_id["kind"] == "contribution"
    assert by_id["label"] == "It is."
    assert by_id["where"]["conversation_name"] == "Release check" and by_id["where"]["number"] == 2
    by_number = _resolve(world, conversation=conv, number=2)
    assert by_number["ref"] == turn and by_number["label"] == "It is."
    none = _resolve(world, conversation=conv, number=99)
    assert none["found"] is False and "no post numbered 99" in none["why"]
    assert _resolve(world, conversation="ent-000000000000", number=1)["found"] is False
    assert _resolve(world, conversation=conv, number="two")["found"] is False


def test_only_an_exact_id_resolves_never_a_name_or_a_part_of_one(world, me):
    rule = post(world, "/api/entries", {"kind": "rule", "body": {"text": "Deploy to TEST first."},
                                        "attributed_to": me, "establish": False})["entry"]
    for text in ("Deploy to TEST first.", rule[:10], rule + "0", rule.upper(), " ", "ent-", "adm-zzzzzzzzzzzz"):
        got = _resolve(world, ref=text)
        assert got["found"] is False and got["why"], text
    unknown = _resolve(world, ref="ent-000000000000")
    assert unknown == {"found": False, "ref": "ent-000000000000", "why": "this Brain holds nothing with that id"}
    assert _resolve(world, ref="adm-000000000000")["found"] is False


def test_a_held_file_resolves_to_its_name_and_a_bad_passage_is_refused_before_recording(world, me):
    st = world["state"]
    data = b"The deploy call was refused from inside the hosting run.\n"
    held = artifacts.hold(st.corpus, st.cv, data, act="artifact-submitted", actor=me,
                          source=f"submission:{me}", door="human-ingress", claimed_name="deploy-log.txt",
                          claimed_media_type="text/plain")
    adm, digest = held["admission"], held["digest"]
    got = _resolve(world, ref=adm)
    assert got["found"] and got["usable"] and got["kind"] == "file" and got["label"] == "deploy-log.txt"
    assert got["file"]["size"] == len(data) and got["file"]["origin"] == "submission" and got["passage"] is False
    cite = f"{adm}@{digest[:12]}[0:10]"
    passage = _resolve(world, ref=cite)
    assert passage["found"] and passage["usable"] and passage["passage"] is True and passage["ref"] == cite
    # found, and said not to be usable: the range is outside the file
    outside = _resolve(world, ref=f"{adm}@{digest[:12]}[0:99999]")
    assert outside["found"] is True and outside["usable"] is False and "outside" in outside["why"]
    wrong = _resolve(world, ref=f"{adm}@{'0' * 12}[0:10]")
    assert wrong["usable"] is False and "digest" in wrong["why"]
    # a purged file is found and cannot be cited
    artifacts.purge(st.corpus, st.cv, adm, by=me, because="the owner decided")
    gone = _resolve(world, ref=adm)
    assert gone["found"] is True and gone["usable"] is False and gone["file"]["state"] == "purged"


def test_resolving_writes_nothing_and_agrees_with_the_door_that_records(world, me):
    note = post(world, "/api/entries", {"kind": "note", "body": {"text": "The deploy call was refused."},
                                        "attributed_to": me, "establish": False})["entry"]
    before = world["state"].corpus.advance()
    for ref in (note, "ent-000000000000", "nonsense"):
        _resolve(world, ref=ref)
    assert world["state"].corpus.advance() == before
    assert "error" in post(world, "/api/ladder/resolve", {"ref": note})
    assert world["state"].corpus.advance() == before
    # what it called usable, the recording door takes, with the same id
    lesson = post(world, "/api/entries", {"kind": "lesson", "body": {"text": "A hosted run cannot restart its host."},
                                          "attributed_to": me, "establish": False,
                                          "basis": [_resolve(world, ref=note)["ref"]]})
    assert lesson.get("entry"), lesson
    basis = get(world, f"/api/ladder/items/{lesson['entry']}")["basis"]
    assert [b["ref"] for b in basis] == [note]
