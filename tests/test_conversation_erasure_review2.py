"""Regressions from the re-review of e7ae67b (conv-mgmt/rereview-erasure.md):
each probe there asserted a defect; each test here asserts its correction.
Fresh fixture Brains only.
"""
from __future__ import annotations

import json
import os
import shutil

import pytest

import mentis.api as api
from mentis.conversation import erasure as ER
from mentis.exchange import ExchangeRefused
from mentis.exchange import format as fmt
from mentis.exchange.apply import apply
from mentis.exchange.export import export
from mentis.spine import backup as B
from mentis.spine import erasure as SE
from mentis.spine import held
from mentis.spine import migrations as M
from tests.test_conversation_erasure_review import (MARK, delete, file,
                                                    trash, w)  # noqa: F401


def backup(w, name="b"):
    return B.backup(str(w["root"]), dest=str(w["tmp"] / name))["backup"]


def restore(w, b):
    w["c"].close()
    plan = B.restore_plan(str(w["root"]), b)
    return B.restore(str(w["root"]), b, confirm=plan["digest"])


def fork(w, name):
    from tests.test_exchange_apply import record_fork
    path = w["tmp"] / name
    w["c"].snapshot(str(path / "corpus.db"))
    marker = w["root"] / "mentis-corpus.json"
    if marker.exists():
        shutil.copy2(marker, path / marker.name)
    record_fork(str(path))
    return path


def reopen(w):
    w["c"] = api.open_corpus(str(w["root"]))
    w["cv"] = api.brain(w["c"]).conversations


# 1 ------------------------------------------------------------------------------

@pytest.mark.skipif(os.name != "nt", reason="Windows real locked file")
def test_1_a_ledger_that_cannot_be_written_refuses_and_changes_nothing(w):
    import ctypes
    from ctypes import wintypes
    ledger = SE.ledger_path(w["root"])
    open(ledger, "w", encoding="utf-8").close()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD,
                                   wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(ledger, 0x80000000, 1, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        trash(w)
        before = w["c"].advance()
        with pytest.raises(ER.Refused) as refused:
            delete(w)
        assert refused.value.refusal["code"] == "ledger-unwritable"
        assert w["c"].advance() == before
    finally:
        kernel.CloseHandle(handle)
    assert w["cv"].conversation_state(w["cid"]) == "trashed"
    assert MARK in json.dumps(w["c"].read([w["p"]])[0]["body"])


def test_1_a_lost_ledger_line_is_repaired_by_cleanup_and_guards_restore(w):
    b = backup(w)
    trash(w)
    got = delete(w)
    os.remove(SE.ledger_path(w["root"]))         # lost after the fact
    shutil.rmtree(SE.erase_set_dir(w["root"]))
    again = ER.cleanup(w["cv"], w["cid"], by=w["me"])
    assert again["status"] == "completed" and again["ledger"]["repaired"]
    line = SE.ledger_entries(w["root"])[0]
    assert line["deletion"] == got["act"]
    assert ("entry", w["p"]) in SE.read_erase_set(w["root"], line)["rows"]
    out = restore(w, b)
    assert out["erasure_ledger"]["served_writable"] is False
    with pytest.raises(M.BrainNotWritable):
        api.open_corpus(str(w["root"]), access="write")
    assert ER.reapply(str(w["root"]), by=w["me"])["still_missing"] == []
    reopen(w)
    assert SE.erased_by(w["c"].read([w["p"]])[0]["body"])


def test_1_a_commit_that_fails_after_the_ledger_takes_its_intent_back(
        w, monkeypatch):
    """Round 4 (finding 6): the deletion did not happen, so the same handler
    puts the ledger back and removes the erase set; the open service and a
    fresh open both go on as before."""
    real = SE.ledger_record

    def then_fail(*a, **kw):
        real(*a, **kw)
        raise RuntimeError("the commit did not happen")
    before = SE.ledger_snapshot(w["root"])
    monkeypatch.setattr(SE, "ledger_record", then_fail)
    trash(w)
    with pytest.raises(RuntimeError):
        delete(w)
    monkeypatch.undo()
    assert w["cv"].conversation_state(w["cid"]) == "trashed"   # rolled back
    assert SE.ledger_snapshot(w["root"]) == before
    assert not os.listdir(SE.erase_set_dir(w["root"]))
    assert MARK in json.dumps(w["c"].read([w["p"]])[0]["body"])
    w["c"].close()
    reopen(w)
    assert w["cv"].conversation_state(w["cid"]) == "trashed"


def test_1_an_intent_that_cannot_be_taken_back_gates_the_open_store(
        w, monkeypatch):
    """...and when the undo itself fails, the open Store refuses every read
    and write; a fresh open refuses; the owner's reapply completes the
    deletion (the crash case is the same at the next open)."""
    real = SE.ledger_record

    def then_fail(*a, **kw):
        real(*a, **kw)
        raise RuntimeError("the commit did not happen")

    def cannot(*a, **kw):
        raise OSError("the ledger cannot be put back")
    monkeypatch.setattr(SE, "ledger_record", then_fail)
    monkeypatch.setattr(SE, "ledger_restore", cannot)
    monkeypatch.setattr(os, "remove", cannot)
    trash(w)
    with pytest.raises(RuntimeError):
        delete(w)
    monkeypatch.undo()
    assert w["c"]._store.ledger_gate
    with pytest.raises(M.BrainNotWritable) as refused:
        w["c"].read([w["p"]])
    assert w["cid"] in str(refused.value)
    with pytest.raises(M.BrainNotWritable):
        w["cv"].say(w["other"], w["me"], [{"type": "text", "text": "x"}])
    w["c"]._store.ledger_gate = None
    w["c"].close()
    with pytest.raises(M.BrainNotWritable) as refused:
        api.open_corpus(str(w["root"]))
    assert "commit did not complete" in str(refused.value)
    done = ER.reapply(str(w["root"]), by=w["me"])
    assert done["still_missing"] == [] and done["reapplied"][0]["reapplied"]
    reopen(w)
    assert w["cv"].conversation_state(w["cid"]) == "deleted"
    assert SE.erased_by(w["c"].read([w["p"]])[0]["body"])


# 2 ------------------------------------------------------------------------------

def test_2_read_open_export_and_cli_export_are_refused(w, capsys):
    b = backup(w)
    trash(w)
    got = delete(w)
    restore(w, b)
    root = str(w["root"])
    for access in ("read", "auto", "write"):
        with pytest.raises(M.BrainNotWritable) as refused:
            api.open_corpus(root, access=access)
        assert w["cid"] in str(refused.value) and got["act"] in \
            str(refused.value)
    with pytest.raises(M.BrainNotWritable):
        export(root, out=str(w["tmp"] / "x.zip"), conversation=w["cid"])
    assert not (w["tmp"] / "x.zip").exists()
    from mentis.brain.__main__ import main as cli
    rc = cli(["export", root, "--conversation", w["cid"], "--out",
              str(w["tmp"] / "y.zip")])
    err = capsys.readouterr().err
    assert rc != 0 and w["cid"] in err and not (w["tmp"] / "y.zip").exists()
    # the owner's inspection override still reads it (check command)
    assert ER._main(["check", root]) == 1
    ER.reapply(root, by=w["me"])
    reopen(w)


def test_2_a_pre_0002_brain_with_a_listed_deletion_is_refused_to_read(w):
    import time
    from mentis.spine.store import Store
    root = w["tmp"] / "old"
    M.create_brain(str(root), ms=(M.ADOPT,))
    s = Store(str(root), _maintenance=True)
    cid = "ent-000000000000"
    try:
        s.append_entry({"id": cid, "family": "entry",
                        "definition": {"name": "conversation", "version": 1},
                        "body": {"name": MARK, "about": ""},
                        "attributed_to": w["me"], "recorded_at": time.time()})
        identity = s.corpus_id
    finally:
        s.close()
    SE.ledger_append(root, {"corpus_id": identity, "conversation": cid,
                            "deletion": "opr-000000000000", "digest": "x",
                            "rows": 1, "at": 0, "by": w["me"]})
    with pytest.raises(M.BrainNotWritable) as refused:
        api.open_corpus(str(root))
    assert cid in str(refused.value)


# 3 ------------------------------------------------------------------------------

def test_3_an_import_cannot_bring_back_a_ledger_deleted_conversation(w):
    b = backup(w)
    cv, me = w["cv"], w["me"]
    cid = cv.open_conversation("Later created", attributed_to=me)
    p = cv.say(cid, me, [{"type": "text", "text": "IMPORT-RESURRECTION-q9Q5f"}])
    source = fork(w, "source")
    path = str(w["tmp"] / "before-deletion.zip")
    export(str(source), out=path, conversation=cid)
    cv.change_conversation_state(cid, "trash", by=me)
    ER.delete(cv, cid, by=me, token=ER.impact(cv, cid)["token"])
    restored = restore(w, b)
    assert restored["erasure_ledger"]["served_writable"]   # absent here
    with pytest.raises(ExchangeRefused, match="permanently deleted here"):
        apply(str(w["root"]), path, backup_dest=str(w["tmp"] / "ib"))
    reopen(w)
    assert not w["c"].read([p]) and not w["c"].read([cid])


# 4 ------------------------------------------------------------------------------

def test_4_a_file_named_in_a_json_key_is_kept(w):
    _, adm, digest = file(w)
    note = w["c"].create_and_establish(
        kind="note", body={"text": "retained attachment inventory"},
        attributed_to=w["me"])
    other_post = w["cv"].say(w["other"], w["me"],
                             [{"type": "text", "text": "reference kept"}])
    link = w["c"].write(body={"reason": "retained evidence inventory",
                              "files": {adm: {"use": "still required"}}},
                        attributed_to=w["me"],
                        link={"from": note, "to": other_post,
                              "relation": "supports"})
    before = w["c"].read([link])[0]
    trash(w)
    inv = ER.inventory(w["cv"], w["cid"])
    assert adm in {f["id"] for f in inv["files_kept"]}
    delete(w)
    assert w["c"].read([link])[0] == before
    assert held.path(str(w["root"]), digest).exists()


# 5 ------------------------------------------------------------------------------

def test_5_a_child_conversation_keeps_its_own_origin_reason(w):
    from mentis.conversation import anchors
    a = anchors.create_anchor(w["cv"], {"version": w["p"], "type": "version"},
                              by=w["me"])["anchor"]
    child = anchors.deep_dive(w["cv"], a, {
        "why": "OTHER-CONVERSATION-REASON-q9Q5f",
        "name": "Independent child"}, by=w["me"])["conversation"]
    link = w["c"].links(frm=child, relation="opened-from")[0]
    trash(w)
    delete(w)
    # round 4: the link's body is erased (it has an erased end); the
    # child's reason is read from its own opening act and post
    assert SE.erased_by(w["c"].read([link["id"]])[0]["body"])
    after = anchors.origin(w["cv"], child)
    assert after["why"] == "OTHER-CONVERSATION-REASON-q9Q5f"
    assert after["deleted"] is True and not after.get("unresolvable")
    assert after["excerpt"] is None


# 6 ------------------------------------------------------------------------------

def test_6_a_kept_link_that_quotes_the_post_has_its_whole_body_erased(w):
    note = w["c"].create_and_establish(
        kind="note", body={"text": "surviving independent knowledge"},
        attributed_to=w["me"])
    link = w["c"].write(body={"reason": "evidence", "cite": {"text": MARK}},
                        attributed_to=w["me"],
                        link={"from": note, "to": w["p"],
                              "relation": "supports"})
    words = w["c"].write(body={"reason": "as it said: " + MARK},
                         attributed_to=w["me"],
                         link={"from": note, "to": w["p"],
                               "relation": "derived-from"})
    trash(w)
    imp = ER.impact(w["cv"], w["cid"])
    assert imp["counts"]["links_with_words_erased"] >= 2
    delete(w)
    for lid in (link, words):
        row = w["c"].read([lid])[0]
        assert SE.erased_by(row["body"]) and MARK not in json.dumps(row)
        assert row["link"]["from"] == note and row["link"]["to"] == w["p"]
    assert w["c"].read([note])[0]["body"]["text"] == \
        "surviving independent knowledge"


# 7 ------------------------------------------------------------------------------

def test_7_reapply_erases_exactly_the_original_set(w):
    _, adm, digest = file(w)
    b = backup(w)
    w["cv"].say(w["other"], w["me"], [{"type": "file", "ref": adm}])
    trash(w)
    original = delete(w)
    conn = w["c"]._store._conn
    original_rows = {tuple(r) for r in conn.execute(
        "SELECT tbl, row_id FROM erasure WHERE deletion = ?",
        (original["act"],))}
    assert ("entry", adm) not in original_rows
    restore(w, b)
    done = ER.reapply(str(w["root"]), by=w["me"])
    assert done["still_missing"] == []
    reopen(w)
    new_rows = {tuple(r) for r in w["c"]._store._conn.execute(
        "SELECT tbl, row_id FROM erasure WHERE deletion = ?",
        (done["reapplied"][0]["act"],))}
    assert new_rows <= original_rows and ("entry", adm) not in new_rows
    assert not SE.erased_by(w["c"].read([adm])[0]["body"])
    assert held.path(str(w["root"]), digest).exists()


# 8 ------------------------------------------------------------------------------

def test_8_reapply_refuses_restored_work_in_flight_unless_acknowledged(w):
    cv, me = w["cv"], w["me"]
    agent = cv.create_participant("@RestoredAsker")
    asked = cv.say(w["cid"], agent, [{"type": "text",
                                      "text": "may I proceed?"}])
    exp = cv.expect(asked, of=me, kind="decision", by=agent)
    assert cv.work_in_flight(w["cid"])["waiting"] == 1
    b = backup(w)
    cv.record_act(actor=me, act="expectation-met", conversation=w["cid"],
                  caused_by=exp, about=[exp], detail={})
    trash(w)
    delete(w)
    restore(w, b)
    root = str(w["root"])
    refused = ER.reapply(root, by=me)
    r = refused["reapplied"][0]
    assert r["reapplied"] is False and r["code"] == "work-in-flight"
    assert r["open_work"]["waiting"] == 1 and "waiting for you" in r["why"]
    assert refused["still_missing"]
    done = ER.reapply(root, by=me, acknowledge_open_work=True)
    assert done["still_missing"] == []
    reopen(w)
    act = w["c"].operational(act=SE.REAPPLIED_ACT)[0]
    assert act["detail"]["open_work_acknowledged"]["waiting"] == 1


# 9 ------------------------------------------------------------------------------

def test_9_an_erased_row_imports_across_a_definition_version_mapping(w):
    from mentis.exchange.apply import ERASURE_ATTESTED
    dest = fork(w, "dest")
    c = w["c"]
    original = c.current_definition("extracted-from")
    body = original["body"]
    props = {k: v for k, v in body.items()
             if k not in ("relation", "inverse", "directed", "substrate_role")}
    c.define_relation("extracted-from", inverse=body["inverse"],
                      properties=props, attributed_to=w["me"])
    assert c.current_definition("extracted-from")["definition"]["version"] \
        != original["definition"]["version"]
    note = c.create_and_establish(kind="note",
                                  body={"text": "surviving knowledge"},
                                  attributed_to=w["me"])
    link = c.write(body={"cite": {"text": MARK}}, attributed_to=w["me"],
                   link={"from": note, "to": w["p"],
                         "relation": "extracted-from"})
    trash(w)
    delete(w)
    path = str(w["tmp"] / "mapping.zip")
    export(str(w["root"]), out=path, item=note)
    got = apply(str(dest), path, backup_dest=str(w["tmp"] / "mb"))
    assert got["applied"]
    d = api.open_corpus(str(dest))
    try:
        assert SE.erased_by(d.read([link])[0]["body"])
        att = d.operational(act=ERASURE_ATTESTED)[0]["detail"]["erasures"]
        mine = [a for a in att if a["row_id"] == link][0]
        assert mine["as_attested"]["def_version"] != \
            d.read([link])[0]["definition"]["version"]
        assert d.verify_chain()["intact"]
    finally:
        d.close()
    # and the next export from there still verifies
    again = str(w["tmp"] / "again.zip")
    export(str(dest), out=again, item=note)
    from mentis.exchange.apply import check_erased
    x = fmt.read(again)
    check_erased(x.manifest, x.entries, x.acts)


# noncritical --------------------------------------------------------------------

def test_a_completed_restore_resumed_still_reports_the_ledger(w):
    b = backup(w)
    trash(w)
    delete(w)
    restored = restore(w, b)
    resumed = B.resume_restore(str(w["root"]), restored["restore_id"])
    assert resumed["already"] and resumed["erasure_ledger"]["missing"]
    ER.reapply(str(w["root"]), by=w["me"])
    reopen(w)
