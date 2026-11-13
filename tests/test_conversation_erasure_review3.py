"""Regressions from the re-review of 2c23150 (conv-mgmt/rereview-erasure3.md):
each probe there asserted a defect; each test here asserts its correction.
Fresh fixture Brains only.
"""
from __future__ import annotations

import json
import os
import sqlite3

import pytest

import mentis.api as api
from mentis.conversation import erasure as ER
from mentis.exchange import ExchangeRefused
from mentis.exchange import format as fmt
from mentis.exchange.apply import apply
from mentis.exchange.export import export
from mentis.spine import erasure as SE
from mentis.spine import held
from mentis.spine import migrations as M
from tests.test_conversation_erasure import _req, world  # noqa: F401
from tests.test_conversation_erasure_review import (MARK, delete, file,
                                                    trash, w)  # noqa: F401
from tests.test_conversation_erasure_review2 import (backup, fork, reopen,
                                                     restore)


# 1 ------------------------------------------------------------------------------

@pytest.mark.parametrize("shape", ["embedded", "short", "object-key"])
def test_1_every_link_with_an_erased_end_loses_its_whole_body(w, shape):
    private = "SECRET-7" if shape == "short" else "PRIVATE-LINK-QUOTATION-q3F8k"
    source = w["cv"].say(w["cid"], w["me"], [{"type": "text", "text": (
        "Before the secret: " + private + "; after the secret.")
        if shape == "embedded" else private}])
    note = w["c"].create_and_establish(
        kind="note", body={"text": "Independent surviving knowledge"},
        attributed_to=w["me"])
    body = ({private: "source statement"} if shape == "object-key"
            else {"reason": "Evidence reported " + private + " as its "
                            "conclusion."})
    link = w["c"].write(body=body, attributed_to=w["me"],
                        link={"from": note, "to": source,
                              "relation": "supports"})
    trash(w)
    got = delete(w)
    assert got["deleted"]
    row = w["c"].read([link])[0]
    assert SE.erased_by(row["body"]) and private not in json.dumps(row)
    assert row["link"]["from"] == note and row["link"]["to"] == source
    out = str(w["tmp"] / "note.zip")
    export(str(w["root"]), out=out, item=note)
    assert not any(private in json.dumps(e) for e in fmt.read(out).entries)
    assert w["c"].read([note])[0]["body"]["text"] == \
        "Independent surviving knowledge"


# 2 ------------------------------------------------------------------------------

def test_2_a_file_named_in_a_surviving_act_s_reason_is_kept(w):
    _, adm, digest = file(w)
    note = w["c"].create_and_establish(
        kind="note", body={"text": "Kept evidence-based knowledge"},
        attributed_to=w["me"])
    act = w["cv"].record_act(actor=w["me"], act="material-recorded",
                             conversation=w["other"], about=[note],
                             because="This knowledge uses retained "
                                     "attachment " + adm,
                             detail={"entry": note, "kind": "note"})
    before = w["c"].operational(id=act)[0]
    trash(w)
    inv = ER.inventory(w["cv"], w["cid"])
    assert adm in {f["id"] for f in inv["files_kept"]}
    delete(w)
    assert w["c"].operational(id=act)[0] == before
    assert held.path(str(w["root"]), digest).exists()


# 3 ------------------------------------------------------------------------------

def _later_deleted_reaction(w):
    from mentis.conversation import anchors
    cid = w["cv"].open_conversation("Later deleted", attributed_to=w["me"])
    secret = "PRIVATE-REACTION-q3F8k"
    p = w["cv"].say(cid, w["me"], [{"type": "text", "text": secret}])
    a = anchors.create_anchor(w["cv"], {"version": p, "type": "version"},
                              by=w["me"])["anchor"]
    reaction = anchors.react(w["cv"], a, {"token": secret},
                             by=w["me"])["reaction"]
    return cid, reaction, secret


def test_3_a_missing_erase_set_refuses_everything_until_repaired(w):
    b = backup(w)
    cid, reaction, secret = _later_deleted_reaction(w)
    source = fork(w, "source")
    path = str(w["tmp"] / "reaction.zip")
    export(str(source), out=path, item=reaction)
    w["cv"].change_conversation_state(cid, "trash", by=w["me"])
    got = ER.delete(w["cv"], cid, by=w["me"],
                    token=ER.impact(w["cv"], cid)["token"])
    restore(w, b)
    os.remove(os.path.join(SE.erase_set_dir(w["root"]), got["act"] + ".json"))
    root = str(w["root"])
    # every open refuses, the import's included: nothing comes back
    with pytest.raises((M.BrainNotWritable, ExchangeRefused)) as refused:
        apply(root, path, backup_dest=str(w["tmp"] / "ib"))
    assert "erase set" in str(refused.value)
    with SE.ledger_unchecked():
        c = api.open_corpus(root, access="read")
        try:
            assert not c.read([reaction])
            missing = SE.ledger_check(c._store._conn, c.root)
            assert missing and "erase set cannot be read" in missing[0]["why"]
        finally:
            c.close()
    # the deletion act is not in this (restored) record: nothing to rebuild
    # the erase set from, so repair keeps the line and the Brain stays shut
    assert ER._main(["check", root, "--repair"]) == 1
    with pytest.raises(M.BrainNotWritable):
        api.open_corpus(root)


def test_3_check_repair_rebuilds_an_erase_set_from_the_record(w):
    trash(w)
    got = delete(w)
    os.remove(os.path.join(SE.erase_set_dir(w["root"]), got["act"] + ".json"))
    w["c"].close()
    root = str(w["root"])
    with pytest.raises(M.BrainNotWritable):
        api.open_corpus(root)
    assert ER._main(["check", root, "--repair"]) == 0
    reopen(w)
    line = SE.ledger_entries(w["root"])[0]
    assert ("entry", w["p"]) in SE.read_erase_set(w["root"], line)["rows"]


def test_3_the_import_door_itself_checks_the_ledger(w):
    b = backup(w)
    cid, reaction, secret = _later_deleted_reaction(w)
    original = w["c"].read([reaction])[0]
    w["cv"].change_conversation_state(cid, "trash", by=w["me"])
    ER.delete(w["cv"], cid, by=w["me"], token=ER.impact(w["cv"], cid)["token"])
    restore(w, b)
    c = api.open_corpus(str(w["root"]), access="write")
    try:
        with pytest.raises(SE.LedgerDamaged, match="permanently deleted"):
            c._store.append_imported([original], [])
        assert not c.read([reaction])
    finally:
        c.close()
    reopen(w)


# 4 ------------------------------------------------------------------------------

def _torn(root, entry):
    with open(SE.ledger_path(root), "ab") as fh:
        fh.write(json.dumps(entry).encode()[:70])
        fh.flush()
        os.fsync(fh.fileno())
    raise OSError("interrupted append after a durable partial write")


def test_4_a_torn_append_is_taken_back_in_the_same_handler(w, monkeypatch):
    before = SE.ledger_snapshot(w["root"])
    trash(w)
    with monkeypatch.context() as m:
        m.setattr(SE, "ledger_append", _torn)
        with pytest.raises(ER.Refused) as refused:
            delete(w)
    assert refused.value.refusal["code"] == "ledger-unwritable"
    assert SE.ledger_snapshot(w["root"]) == before
    w["c"].close()
    reopen(w)
    assert w["cv"].conversation_state(w["cid"]) == "trashed"


def test_4_a_torn_line_left_behind_is_recovered_by_reapply(w, monkeypatch):
    trash(w)

    def cannot(*a, **kw):
        raise OSError("cannot put it back")
    with monkeypatch.context() as m:
        m.setattr(SE, "ledger_append", _torn)
        m.setattr(SE, "ledger_restore", cannot)
        m.setattr(os, "remove", cannot)
        with pytest.raises(ER.Refused):
            delete(w)
    w["c"]._store.ledger_gate = None
    w["c"].close()
    root = str(w["root"])
    with pytest.raises(M.BrainNotWritable) as refused:
        api.open_corpus(root)
    assert "damaged" in str(refused.value)
    done = ER.reapply(root, by=w["me"])
    assert done["damaged_lines"] and done["still_missing"] == []
    assert done["reapplied"][0]["reapplied"]
    reopen(w)
    assert w["cv"].conversation_state(w["cid"]) == "deleted"
    assert SE.erased_by(w["c"].read([w["p"]])[0]["body"])
    assert all("unreadable" not in e for e in SE.ledger_entries(w["root"]))


def test_4_check_repair_drops_a_torn_line_after_a_complete_deletion(w):
    trash(w)
    got = delete(w)
    with open(SE.ledger_path(w["root"]), "ab") as fh:
        fh.write(b'{"corpus_id": "x", "conver')
    w["c"].close()
    root = str(w["root"])
    with pytest.raises(M.BrainNotWritable):
        api.open_corpus(root)
    # round 5: a damaged line set aside is warned of loudly (exit 2), never
    # a quiet success; the deletion the record holds is in the ledger
    assert ER._main(["check", root, "--repair"]) == 2
    assert os.path.exists(SE.ledger_path(root) + ".damaged")
    assert ER._main(["check", root]) == 0
    reopen(w)
    assert [e["deletion"] for e in SE.ledger_entries(w["root"])] == \
        [got["act"]]


# 5 ------------------------------------------------------------------------------

def test_5_a_tampered_pre_chain_erased_row_breaks_the_chain(w):
    w["c"].close()
    db = sqlite3.connect(str(w["root"] / "corpus.db"))
    try:
        saved = {r[0]: r[1] for r in db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND "
            "name IN ('entry_no_update', 'corpus_no_update')")}
        for name in saved:
            db.execute("DROP TRIGGER " + name)
        db.execute("UPDATE entry SET hash = NULL, prev_hash = NULL")
        db.execute("UPDATE corpus SET chained_from_first = NULL")
        for sql in saved.values():
            db.execute(sql)
        db.commit()
    finally:
        db.close()
    reopen(w)
    assert w["c"].verify_chain()["intact"]
    trash(w)
    delete(w)
    valid = w["c"].verify_chain()
    assert valid["intact"] and valid["streams"]["entry"]["erased"] > 0
    conn = w["c"]._store._conn
    trigger = conn.execute("SELECT sql FROM sqlite_master WHERE type = "
                           "'trigger' AND name = 'entry_no_update'"
                           ).fetchone()[0]
    conn.execute("DROP TRIGGER entry_no_update")
    conn.execute("UPDATE entry SET attributed_to = ? WHERE id = ?",
                 ("TAMPERED-ATTRIBUTION", w["p"]))
    conn.execute(trigger)
    got = w["c"].verify_chain()
    assert got["intact"] is False
    assert got["streams"]["entry"]["broken_at"]["id"] == w["p"]
    from mentis.spine import backup as B
    assert B._chain(conn)["intact"] is False


# 6 ------------------------------------------------------------------------------

def test_6_a_failed_commit_over_http_leaves_nothing_listed(world, monkeypatch):
    from tests.test_conversation_erasure import SEEDS
    from tests.test_conversation_erasure import trash as trash_world
    real = SE.ledger_record

    def fail_after_ledger(*a, **kw):
        real(*a, **kw)
        raise OSError("fsync/commit-boundary failure after the ledger")
    trash_world(world)
    cid = world["c"]
    token = ER.impact(world["cv"], cid)["token"]
    with monkeypatch.context() as m:
        m.setattr(SE, "ledger_record", fail_after_ledger)
        status, failed = _req(world, "POST",
                              f"/fluid/api/conversations/{cid}/delete",
                              {"author": world["me"], "token": token})
    assert status != 200 and failed.get("code") == "ledger-unwritable"
    # the deletion did not happen and the ledger says nothing of it, so the
    # still-trashed conversation reads as it is
    assert SE.ledger_check(world["corpus"]._store._conn, world["root"]) == []
    status, got = _req(world, "GET", f"/api/entries/{world['posts'][0]}")
    assert status == 200 and SEEDS["post"] in json.dumps(got)
    assert world["cv"].conversation_state(cid) == "trashed"


# noncritical --------------------------------------------------------------------

def test_inspection_says_a_restored_brain_is_not_usable(w):
    from mentis.brain.inspect import inspect
    b = backup(w)
    trash(w)
    got = delete(w)
    restore(w, b)
    result = inspect(str(w["root"]))
    assert result["usable"] is False
    assert got["act"] in result["explain"] and w["cid"] in result["explain"]
    with pytest.raises(M.BrainNotWritable) as refused:
        api.open_corpus(str(w["root"]))
    assert "NOT OPENED" in str(refused.value)
    assert "opened read-only" not in str(refused.value)
    ER.reapply(str(w["root"]), by=w["me"])
    reopen(w)
