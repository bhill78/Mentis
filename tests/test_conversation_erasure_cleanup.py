"""Immediate logical deletion, deferred physical cleanup (owner decision
2026-11-13; conv-mgmt/decision-deferred-cleanup.md, amendment A-E).

A. two outcomes: `deleted` (logical, final) and `physical_cleanup`
   (pending | completed | failed, verified, never inferred);
B. each attempt is an append-only `conversation-erasure-cleanup` act;
C. retried only by explicit acts: Finish cleanup, the next deletion, server
   start -- never on a timer;
D. the deletion ledger beside the Brain directory: a Brain restored from a
   backup taken before a deletion is not served writable until the owner
   re-applies it;
E. copies made before stay copies (the backup still holds the words).
"""
from __future__ import annotations

import json
import os

import pytest

import mentis.api as api
from mentis.conversation import erasure as ER
from mentis.spine import backup as B
from mentis.spine import erasure as SE
from mentis.spine import migrations as M
from mentis.web import _State
from tests.test_conversation_erasure import (_req, delete as http_delete,
                                             trash as http_trash,
                                             world)  # noqa: F401
from tests.test_conversation_erasure_review import MARK, delete, file, trash, w  # noqa: F401,E501


def test_a_the_two_outcomes_are_reported_and_the_ledger_written(w):
    trash(w)
    got = delete(w)
    assert got["deleted"] is True
    pc = got["physical_cleanup"]
    assert pc["status"] == "completed" and pc["reason"] is None
    assert pc["database"]["verified"] and pc["files"]["verified"]
    assert pc["ledger"]["written"]
    lines = SE.ledger_entries(w["root"])
    assert [l["deletion"] for l in lines] == [got["act"]]
    assert set(lines[0]) == {"corpus_id", "conversation", "deletion", "digest",
                             "rows", "at", "at_iso", "by", "erase_set",
                             "erase_set_digest"}
    es = SE.read_erase_set(w["root"], lines[0])
    assert ("entry", w["p"]) in es["rows"] and es["conversation"] == w["cid"]
    assert MARK.encode() not in open(os.path.join(
        SE.erase_set_dir(w["root"]), lines[0]["erase_set"]), "rb").read()
    assert MARK not in json.dumps(lines)
    assert SE.ledger_path(w["root"]) == str(w["root"]) + ".erasures.jsonl"
    tomb = ER.tombstone(w["cv"], w["cid"])
    assert tomb["deleted"] is True
    assert tomb["physical_cleanup"]["status"] == "completed"


def test_a_a_ledger_that_cannot_be_written_refuses_the_deletion(w, monkeypatch):
    """Round 3 (review round 2, finding 1): the ledger is written BEFORE the
    commit; if it cannot be, nothing is deleted."""
    def broken(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(SE, "ledger_append", broken)
    trash(w)
    before = w["c"].advance()
    with pytest.raises(ER.Refused) as refused:
        delete(w)
    assert refused.value.refusal["code"] == "ledger-unwritable"
    assert w["c"].advance() == before
    assert w["cv"].conversation_state(w["cid"]) == "trashed"
    assert MARK in json.dumps(w["c"].read([w["p"]])[0]["body"])


def test_b_each_attempt_is_an_act_and_none_yet_is_pending(w, monkeypatch):
    monkeypatch.setattr(ER, "cleanup", lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("crash after commit")))
    trash(w)
    with pytest.raises(RuntimeError):
        delete(w)
    monkeypatch.undo()
    st = ER.cleanup_status(w["cv"], w["cid"])
    assert st["status"] == "pending" and st["act"] is None
    assert ER.tombstone(w["cv"], w["cid"])["physical_cleanup"]["status"] == \
        "pending"
    got = ER.cleanup(w["cv"], w["cid"], by=w["me"])
    acts = w["c"].operational(conversation=w["cid"], act=ER.CLEANUP_ACT)
    assert [a["id"] for a in acts] == [got["act"]]
    assert acts[0]["about"] == [w["cid"], ER.deleted(w["cv"])[w["cid"]]["act"]]


def test_c_the_next_deletion_retries_an_earlier_cleanup(w, monkeypatch):
    monkeypatch.setattr(ER, "cleanup", lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("crash after commit")))
    trash(w)
    with pytest.raises(RuntimeError):
        delete(w)
    monkeypatch.undo()
    trash(w, w["other"])
    got = delete(w, cid=w["other"])
    assert {"conversation": w["cid"], "status": "completed"} in \
        got["earlier_cleanups_retried"]
    assert ER.cleanup_status(w["cv"], w["cid"])["status"] == "completed"


def test_c_server_start_retries_and_nothing_runs_on_its_own(w, monkeypatch):
    monkeypatch.setattr(ER, "cleanup", lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("crash after commit")))
    trash(w)
    with pytest.raises(RuntimeError):
        delete(w)
    monkeypatch.undo()
    root = str(w["root"])
    w["c"].close()
    st = _State(root)
    try:
        assert st.cleanup_at_start == [{"conversation": w["cid"],
                                        "status": "completed"}]
        assert ER.cleanup_status(st.cv, w["cid"])["status"] == "completed"
        # a second start finds nothing to do and writes nothing
        n = st.corpus._store.operational_count()
    finally:
        st.corpus.close()
    st2 = _State(root)
    try:
        assert st2.cleanup_at_start == []
        assert st2.corpus._store.operational_count() == n
    finally:
        st2.corpus.close()
    w["c"] = api.open_corpus(root)


def test_c_finish_cleanup_route_owner_only(world):
    c = world["c"]
    http_trash(world)
    status, got = _req(world, "POST", f"/fluid/api/conversations/{c}/cleanup",
                       {"author": world["me"]})
    assert status == 409 and got["code"] == "not-deleted"
    http_delete(world)
    status, got = _req(world, "POST", f"/fluid/api/conversations/{c}/cleanup",
                       {"author": world["who"]["@Vera"]})
    assert status == 403
    status, got = _req(world, "POST", f"/fluid/api/conversations/{c}/cleanup",
                       {"author": world["me"]})
    assert status == 200 and got["deleted"] is True
    assert got["physical_cleanup"]["status"] == "completed"
    status, tomb = _req(world, "GET",
                        f"/fluid/api/conversations/{c}/tombstone")
    assert tomb["physical_cleanup"]["status"] == "completed"
    status, rows = _req(world, "GET", "/fluid/api/conversations?state=deleted")
    assert rows["conversations"][0]["physical_cleanup"]["status"] == \
        "completed"


def _restore(root, backup_dir):
    plan = B.restore_plan(root, backup_dir)
    return B.restore(root, backup_dir, confirm=plan["digest"])


def test_d_a_pre_deletion_backup_is_never_served_silently(w, tmp_path):
    root = str(w["root"])
    made = B.backup(root, dest=str(tmp_path / "before-deletion"))
    trash(w)
    got = delete(w)
    w["c"].close()
    # the ledger is beside the Brain, so the backup never carried it
    assert not any(n.endswith(".erasures.jsonl")
                   for n in os.listdir(made["backup"]))
    out = _restore(root, made["backup"])
    assert out["erasure_ledger"]["served_writable"] is False
    assert [m["deletion"] for m in out["erasure_ledger"]["missing"]] == \
        [got["act"]]
    # not served writable, saying which deletion and how to re-apply it
    with pytest.raises(M.BrainNotWritable) as refused:
        api.open_corpus(root, access="write")
    words = str(refused.value)
    assert w["cid"] in words and "reapply" in words
    with pytest.raises(M.BrainNotWritable):
        _State(root)
    # not read either, nor exported (round 3, finding 2)
    with pytest.raises(M.BrainNotWritable):
        api.open_corpus(root, access="read")
    # E: the restored Brain still holds the words until re-applied
    assert MARK.encode() in open(os.path.join(root, "corpus.db"), "rb").read()
    # the owner's explicit re-apply, recorded as its own act
    done = ER.reapply(root, by=w["me"])
    assert done["still_missing"] == []
    assert done["reapplied"][0]["original"] == got["act"]
    c = api.open_corpus(root, access="write")
    try:
        cv = api.brain(c).conversations
        assert cv.conversation_state(w["cid"]) == "deleted"
        assert c.operational(act=SE.REAPPLIED_ACT)[0]["about"][1] == got["act"]
        assert c.verify_chain()["intact"]
        assert ER.cleanup_status(cv, w["cid"])["status"] == "completed"
    finally:
        c.close()
    raw = b"".join(open(os.path.join(root, n), "rb").read()
                   for n in ("corpus.db", "corpus.db-wal")
                   if os.path.exists(os.path.join(root, n)))
    assert MARK.encode() not in raw
    # E: the backup itself is a copy made before, and still holds them
    assert MARK.encode() in open(os.path.join(made["backup"], "corpus.db"),
                                 "rb").read()
    w["c"] = api.open_corpus(root)


def test_d_a_brain_from_before_erasure_existed_is_refused_too(tmp_path):
    import time
    from mentis.spine.store import Store
    root = str(tmp_path / "old")
    M.create_brain(root, ms=(M.ADOPT,))
    # a schema-1 Brain holding a conversation a later deletion removed
    s = Store(root, _maintenance=True)
    try:
        s.append_entry({"id": "ent-000000000000", "family": "entry",
                        "definition": {"name": "conversation", "version": 1},
                        "body": {"name": MARK, "about": ""},
                        "attributed_to": "ent-1", "recorded_at": time.time()})
        cid = s.corpus_id
    finally:
        s.close()
    SE.ledger_append(root, {"corpus_id": cid, "conversation": "ent-000000000000",
                            "deletion": "opr-000000000000", "digest": "x",
                            "rows": 1, "at": 0, "by": "ent-1"})
    conn = B._connect(os.path.join(root, "corpus.db"))
    try:
        missing = SE.ledger_check(conn, root)
    finally:
        conn.close()
    assert missing and "predates erasure" in missing[0]["why"]
    M.apply(root)
    with pytest.raises(M.BrainNotWritable):
        api.open_corpus(root, access="write")


def test_d_check_command_says_what_is_missing(w, tmp_path, capsys):
    root = str(w["root"])
    made = B.backup(root, dest=str(tmp_path / "b"))
    trash(w)
    delete(w)
    w["c"].close()
    _restore(root, made["backup"])
    assert ER._main(["check", root]) == 1
    assert w["cid"] in capsys.readouterr().out
    assert ER._main(["reapply", root, "--by", w["me"]]) == 0
    assert ER._main(["check", root]) == 0
    w["c"] = api.open_corpus(root)
