"""Regressions from the independent review of 6c48eab (conv-mgmt/
review-erasure.md): each probe there asserted a defect; each test here
asserts its correction. Fresh fixture Brains only.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid

import pytest

import mentis.api as api
from mentis.conversation import erasure as ER
from mentis.spine import erasure as SE
from mentis.spine import held
from mentis.web import fixture
from tests.test_conversation_erasure import (_post_file, _req, text,
                                             world)  # noqa: F401

MARK = "PRIVATE-POST-MARKER-q9Q5f"


@pytest.fixture
def w(tmp_path):
    root = tmp_path / "brain"
    built = fixture.build(str(root))
    built["corpus"].close()
    c = api.open_corpus(str(root))
    cv = api.brain(c).conversations
    me = built["who"]["@brian"]
    cid = cv.open_conversation("Delete target", attributed_to=me)
    p = cv.say(cid, me, text(MARK))
    other = cv.open_conversation("Keep target", attributed_to=me)
    yield dict(root=root, c=c, cv=cv, me=me, cid=cid, p=p, other=other,
               tmp=tmp_path)
    c.close()


def trash(w, cid=None):
    w["cv"].change_conversation_state(cid or w["cid"], "trash", by=w["me"])


def delete(w, token=None, cid=None):
    cid = cid or w["cid"]
    return ER.delete(w["cv"], cid, by=w["me"],
                     token=token or ER.impact(w["cv"], cid)["token"])


def file(w):
    return _post_file(w["cv"], w["c"], w["cid"], w["me"],
                      b"EXCLUSIVE-OR-SHARED-CONTENT-q9Q5f", "private.txt")


# 1 -----------------------------------------------------------------------------

def test_1_a_produced_candidate_note_is_knowledge_not_a_file(w):
    from mentis.conversation import ladder_writes
    out = ladder_writes.record(w["cv"], kind="note",
                               body={"text": "PRESERVE-CANDIDATE-NOTE-q9Q5f"},
                               by=w["me"], context={"conversation": w["cid"],
                                                    "turn": w["p"]})
    note = out["entry"]
    before = w["c"].read([note])[0]
    trash(w)
    inv = ER.inventory(w["cv"], w["cid"])
    assert note not in {f["id"] for f in inv["files_removed"]}
    assert note not in {f["id"] for f in inv["files_kept"]}
    delete(w)
    assert w["c"].read([note])[0] == before


# 2 -----------------------------------------------------------------------------

def test_2_a_file_a_kept_link_names_is_kept(w):
    _, adm, digest = file(w)
    lesson = w["c"].create_and_establish(kind="lesson",
                                         body={"text": "kept knowledge"},
                                         attributed_to=w["me"])
    link = w["c"].write(body={"reason": "Supporting evidence file " + adm},
                        attributed_to=w["me"],
                        link={"from": lesson, "to": w["p"],
                              "relation": "supports"})
    before = w["c"].read([link])[0]
    trash(w)
    inv = ER.inventory(w["cv"], w["cid"])
    assert adm in {f["id"] for f in inv["files_kept"]}
    delete(w)
    assert w["c"].read([link])[0] == before
    assert held.path(str(w["root"]), digest).exists()
    assert not w["c"].read([adm])[0]["body"].get("erased")


def test_2_a_file_another_run_was_handed_is_kept(w):
    _, adm, digest = file(w)
    d = "dlv-" + uuid.uuid4().hex[:12]
    w["c"]._store.append_delivery(dict(
        id=d, execution="exe-" + uuid.uuid4().hex[:12],
        conversation=w["other"], participant=w["me"], runtime="stub",
        mechanism="stub", at=time.time(),
        material={"parts": [{"type": "file", "ref": adm}]},
        behavioural_sources=[], operation_ok=True))
    trash(w)
    inv = ER.inventory(w["cv"], w["cid"])
    assert {f["id"]: f["why"] for f in inv["files_kept"]}[adm] == \
        "supplied to work elsewhere"
    delete(w)
    assert held.path(str(w["root"]), digest).exists()


def test_2_a_file_an_act_s_detail_names_elsewhere_is_kept(w):
    _, adm, digest = file(w)
    w["cv"].record_act(actor=w["me"], act="turn-said",
                       conversation=w["other"],
                       detail={"returned": [adm]})
    trash(w)
    inv = ER.inventory(w["cv"], w["cid"])
    assert adm in {f["id"] for f in inv["files_kept"]}
    delete(w)
    assert held.path(str(w["root"]), digest).exists()


# 3 -----------------------------------------------------------------------------

def test_3_an_authority_reason_is_erased(w):
    exp = w["cv"].record_act(actor=w["me"], act="expectation-recorded",
                             conversation=w["cid"], turn=w["p"],
                             detail={"expected_of": w["me"],
                                     "work": "ordinary request"})
    a = w["cv"].grant_authority(exp, ["coordinate"], by=w["me"],
                                source="explicit",
                                because="PRIVATE-AUTHORITY-REASON-q9Q5f")
    w["cv"].record_act(actor=w["me"], act="expectation-met",
                       conversation=w["cid"], caused_by=exp, about=[exp],
                       detail={})
    trash(w)
    delete(w)
    act = w["c"].operational(id=a)[0]
    assert act["because"] is None and SE.erased_by(act["detail"])
    assert act["actor"] == w["me"] and act["act"] == "authority-granted"


def test_3_an_edit_by_version_id_with_no_conversation_is_erased(w):
    from mentis.conversation import versions
    head = versions.edit(w["cv"], w["p"], by=w["me"],
                         text="second version")["version"]
    edit = versions.edit(w["cv"], head, by=w["me"], text="third version",
                         because="PRIVATE-EDIT-REASON-q9Q5f")
    trash(w)
    delete(w)
    act = w["c"].operational(id=edit["act"])[0]
    assert act["because"] is None and SE.erased_by(act["detail"])


# 4 -----------------------------------------------------------------------------

@pytest.mark.parametrize("permanent", [False, True])
def test_4_a_reaction_cannot_be_deleted_in_trash_or_after(w, permanent):
    from mentis.conversation import anchors, versions
    a = anchors.create_anchor(w["cv"], {"version": w["p"], "type": "version"},
                              by=w["me"])["anchor"]
    reaction = anchors.react(w["cv"], a, {"token": "+1"},
                             by=w["me"])["reaction"]
    trash(w)
    if permanent:
        delete(w)
    before = w["c"].advance()
    with pytest.raises(ER.ConversationNotWritable):
        versions.delete(w["cv"], reaction, by=w["me"],
                        because="NEW-WRITE-IN-TRASH-q9Q5f")
    assert w["c"].advance() == before


@pytest.mark.parametrize("permanent", [False, True])
def test_4_http_reaction_delete_is_refused(world, permanent):
    from mentis.conversation import anchors
    from tests.test_conversation_erasure import delete as http_delete
    from tests.test_conversation_erasure import trash as http_trash
    cv, me = world["cv"], world["me"]
    a = anchors.create_anchor(cv, {"version": world["posts"][0],
                                   "type": "version"}, by=me)["anchor"]
    r = anchors.react(cv, a, {"token": "+1"}, by=me)["reaction"]
    http_trash(world)
    if permanent:
        http_delete(world)
    before = world["corpus"].advance()
    status, got = _req(world, "POST", f"/api/entries/{r}/delete",
                       {"attributed_to": me,
                        "because": "NEW-HTTP-REASON-q9Q5f"})
    assert status == 409, (status, got)
    assert world["corpus"].advance() == before


def test_4_a_long_version_line_cannot_be_edited_in_trash(w):
    from mentis.conversation import versions
    head = w["p"]
    for i in range(30):
        head = versions.edit(w["cv"], head, by=w["me"],
                             text="edited " + str(i))["version"]
    trash(w)
    with pytest.raises(ER.ConversationNotWritable):
        versions.edit(w["cv"], head, by=w["me"],
                      text="NEW-WRITE-AFTER-THIRTY-EDITS-q9Q5f")


# 5 -----------------------------------------------------------------------------

def test_5_the_impact_token_names_the_files_not_their_labels(w):
    _, adm_a, _ = _post_file(w["cv"], w["c"], w["cid"], w["me"], b"A0",
                             "same.txt")
    _, adm_b, _ = _post_file(w["cv"], w["c"], w["cid"], w["me"], b"B0",
                             "same.txt")
    w["cv"].say(w["other"], w["me"], [{"type": "file", "ref": adm_b}])
    elsewhere = w["cv"].open_conversation("Another survivor",
                                          attributed_to=w["me"])
    trash(w)
    before = ER.impact(w["cv"], w["cid"])
    w["cv"].say(elsewhere, w["me"], [{"type": "file", "ref": adm_a}])
    trash(w, w["other"])
    delete(w, cid=w["other"])
    after = ER.impact(w["cv"], w["cid"])
    assert before["token"] != after["token"]
    with pytest.raises(ER.Refused) as refused:
        delete(w, before["token"])
    assert refused.value.refusal["code"] == "impact-changed"


# 6 and 7 (owner decision 2026-11-13: deferred physical cleanup) -------------------

def test_6_a_held_snapshot_leaves_cleanup_failed_never_completed(w):
    trash(w)
    reader = sqlite3.connect(str(w["root"] / "corpus.db"))
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM entry").fetchall()
    w["c"]._store._conn.execute("PRAGMA busy_timeout=1")
    try:
        result = delete(w)
        assert result["deleted"] is True
        pc = result["physical_cleanup"]
        assert pc["status"] == "failed" and not pc["database"]["verified"]
        assert pc["reason"]
    finally:
        reader.rollback()
        reader.close()
        w["c"]._store._conn.execute("PRAGMA busy_timeout=5000")
    # the owner's Finish cleanup, now nothing holds a snapshot
    again = ER.cleanup(w["cv"], w["cid"], by=w["me"])
    assert again["status"] == "completed"
    raw = b"".join((w["root"] / n).read_bytes() for n in
                   ("corpus.db", "corpus.db-wal")
                   if (w["root"] / n).exists())
    assert MARK.encode() not in raw
    acts = w["c"].operational(conversation=w["cid"], act=ER.CLEANUP_ACT)
    assert [a["detail"]["status"] for a in acts] == ["failed", "completed"]


def test_7_an_extraction_not_removed_is_reported(w, monkeypatch):
    from mentis.sources.extract import store as xs
    _, adm, digest = file(w)
    extractor = "probe@1+" + "a" * 12
    xs.write(str(w["root"]), digest, dict(
        extractor_id=extractor, name="probe", version="1", options={},
        deps=[], locator_scheme="sha256", status="ok"),
        "PRIVATE-EXTRACTION-q9Q5f", [])
    monkeypatch.setattr(xs, "forget", lambda *a, **kw: False)
    trash(w)
    result = delete(w)
    assert result["deleted"] is True
    pc = result["physical_cleanup"]
    assert pc["status"] == "failed"
    assert any(r["what"] == "extractions" for r in pc["files"]["remaining"])
    monkeypatch.undo()
    assert ER.cleanup(w["cv"], w["cid"], by=w["me"])["status"] == "completed"


def test_7_a_crash_between_commit_and_cleanup_is_finished_by_the_replay(
        w, monkeypatch):
    _, adm, digest = file(w)
    trash(w)
    token = ER.impact(w["cv"], w["cid"])["token"]

    def crash(*a, **kw):
        raise RuntimeError("injected crash boundary after DB commit")
    monkeypatch.setattr(ER, "cleanup", crash)
    with pytest.raises(RuntimeError, match="injected crash"):
        delete(w, token)
    monkeypatch.undo()
    # committed: deleted; nothing recorded of cleanup yet: pending
    assert w["cv"].conversation_state(w["cid"]) == "deleted"
    assert ER.cleanup_status(w["cv"], w["cid"])["status"] == "pending"
    assert held.path(str(w["root"]), digest).exists()
    from types import SimpleNamespace
    from mentis.fluid.commands import delete_conversation
    st = SimpleNamespace(cv=w["cv"], corpus=w["c"])
    status, result, _ = delete_conversation(
        st, w["cid"], {"author": w["me"], "token": token})
    assert status == 200 and result["replayed"]
    assert result["physical_cleanup"]["status"] == "completed"
    assert not held.path(str(w["root"]), digest).exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows file sharing semantics")
def test_7_a_really_locked_extraction_leaves_cleanup_failed(w):
    import ctypes
    from ctypes import wintypes
    from mentis.sources.extract import store as xs
    _, adm, digest = file(w)
    extractor = "probe@1+" + "b" * 12
    xs.write(str(w["root"]), digest, dict(
        extractor_id=extractor, name="probe", version="1", options={},
        deps=[], locator_scheme="sha256", status="ok"),
        "PRIVATE-LOCKED-EXTRACTION-q9Q5f", [])
    p = xs.key_dir(str(w["root"]), digest, extractor) / "text"
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD,
                                   wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(p), 0x80000000, 1, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        trash(w)
        result = delete(w)
        assert result["deleted"] is True
        assert result["physical_cleanup"]["status"] == "failed"
    finally:
        kernel.CloseHandle(handle)
    assert ER.cleanup(w["cv"], w["cid"], by=w["me"])["status"] == "completed"
    assert not p.exists()


# 8 -----------------------------------------------------------------------------

def test_8_an_imported_erased_row_stays_attested_through_the_next_import(w):
    import shutil
    from mentis.exchange import format as fmt
    from mentis.exchange.apply import apply
    from mentis.exchange.export import export
    from tests.test_exchange_apply import record_fork
    tmp = w["tmp"]
    marker = w["root"] / "mentis-corpus.json"

    def fork(name):
        dest = tmp / name
        w["c"].snapshot(str(dest / "corpus.db"))
        if marker.exists():
            shutil.copy2(marker, dest / marker.name)
        record_fork(str(dest))
        return dest
    first_fork, next_fork = fork("fork1"), fork("fork2")
    lesson = w["c"].create_and_establish(kind="lesson",
                                         body={"text": "Kept lesson"},
                                         attributed_to=w["me"])
    link = w["c"].write(body={"cite": {"text": MARK}}, attributed_to=w["me"],
                        link={"from": lesson, "to": w["p"],
                              "relation": "extracted-from"})
    trash(w)
    delete(w)
    first = str(tmp / "first.zip")
    export(str(w["root"]), out=first, item=lesson)
    assert fmt.read(first).manifest.get("erasures")
    apply(str(first_fork), first, backup_dest=str(tmp / "b1"))
    second = str(tmp / "second.zip")
    export(str(first_fork), out=second, item=lesson)
    att = fmt.read(second).manifest.get("erasures")
    assert any(a["row_id"] == link for a in att)
    apply(str(next_fork), second, backup_dest=str(tmp / "b2"))
    c = api.open_corpus(str(next_fork))
    try:
        assert SE.erased_by(c.read([link])[0]["body"])
        assert c.verify_chain()["intact"]
    finally:
        c.close()
