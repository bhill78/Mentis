"""Regressions from the re-review of 993c63f (conv-mgmt/rereview-erasure4.md):
each probe there asserted a defect; each test here asserts its correction.
Fresh fixture Brains only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import mentis.api as api
from mentis.conversation import erasure as ER
from mentis.exchange import format as fmt
from mentis.exchange.export import export
from mentis.spine import erasure as SE
from mentis.spine import held
from mentis.spine import migrations as M
from tests.test_conversation_erasure_review import (MARK, delete, file,
                                                    trash, w)  # noqa: F401
from tests.test_conversation_erasure_review2 import backup, reopen, restore


# 1 ------------------------------------------------------------------------------

def test_1_a_link_citing_an_erased_link_loses_its_body(w):
    note = w["c"].create_and_establish(kind="note",
                                       body={"text": "Surviving finding"},
                                       attributed_to=w["me"])
    assess = w["c"].create_and_establish(
        kind="note", body={"text": "Independent evidence assessment"},
        attributed_to=w["me"])
    first = w["c"].write(body={"cite": {"text": MARK}}, attributed_to=w["me"],
                         link={"from": note, "to": w["p"],
                               "relation": "supports"})
    second = w["c"].write(body={"cite": {"text": MARK},
                                "reason": "Assessing the quoted evidence"},
                          attributed_to=w["me"],
                          link={"from": assess, "to": first,
                                "relation": "supports"})
    third = w["c"].write(body={"reason": "and about that assessment " + MARK},
                         attributed_to=w["me"],
                         link={"from": note, "to": second,
                               "relation": "supports"})
    trash(w)
    delete(w)
    for lid in (first, second, third):
        row = w["c"].read([lid])[0]
        assert SE.erased_by(row["body"]) and MARK not in json.dumps(row)
    out = str(w["tmp"] / "assess.zip")
    export(str(w["root"]), out=out, item=assess)
    assert not any(MARK in json.dumps(e) for e in fmt.read(out).entries)
    assert w["c"].read([assess])[0]["body"]["text"] == \
        "Independent evidence assessment"


def test_1_a_link_citing_an_erased_act_loses_its_body(w):
    act = w["cv"].record_act(actor=w["me"], act="turn-said",
                             conversation=w["cid"], turn=w["p"],
                             about=[w["p"]], detail={"said": MARK})
    note = w["c"].create_and_establish(
        kind="note", body={"text": "Independent run assessment"},
        attributed_to=w["me"])
    link = w["c"].write(body={"cite": {"text": MARK},
                              "reason": "The run's response is the evidence"},
                        attributed_to=w["me"],
                        link={"from": note, "to": act, "relation": "supports"})
    trash(w)
    delete(w)
    assert SE.erased_by(w["c"].operational(id=act)[0]["detail"])
    row = w["c"].read([link])[0]
    assert SE.erased_by(row["body"]) and row["link"]["to"] == act
    out = str(w["tmp"] / "run.zip")
    export(str(w["root"]), out=out, item=note)
    assert not any(MARK in json.dumps(e) for e in fmt.read(out).entries)


# 2 ------------------------------------------------------------------------------

def _earlier_rules_index(w, act):
    """The index as an earlier build left it: no rules sentinel, and the
    act's reason unindexed (that build did not read `because`)."""
    conn = w["c"]._store._conn
    with w["c"].atomic():
        conn.execute("DELETE FROM ref_index WHERE src = '~rules'")
        conn.execute("DELETE FROM ref_index WHERE src = ? AND kind LIKE "
                     "'detail:%'", (act,))


def test_2_an_index_of_earlier_rules_refuses_until_rebuilt(w):
    from mentis.web import _State
    _, adm, digest = file(w)
    note = w["c"].create_and_establish(
        kind="note", body={"text": "Surviving older knowledge"},
        attributed_to=w["me"])
    act = w["cv"].record_act(actor=w["me"], act="material-recorded",
                             conversation=w["other"], about=[note],
                             because="Kept evidence file " + adm,
                             detail={"entry": note})
    _earlier_rules_index(w, act)
    trash(w)
    with pytest.raises(ER.Refused) as refused:
        ER.impact(w["cv"], w["cid"])
    assert refused.value.refusal["code"] == "reference-index-stale"
    with pytest.raises(ER.Refused) as refused:
        ER.delete(w["cv"], w["cid"], by=w["me"], token="x")
    assert refused.value.refusal["code"] == "reference-index-stale"
    assert held.path(str(w["root"]), digest).exists()
    # server start rebuilds it; then the file is kept, as it is referenced
    w["c"].close()
    st = _State(str(w["root"]))
    try:
        assert st.reindexed_at_start and st.reindexed_at_start["rows"]
        inv = ER.inventory(st.cv, w["cid"])
        assert adm in {f["id"] for f in inv["files_kept"]}
        ER.delete(st.cv, w["cid"], by=w["me"],
                  token=ER.impact(st.cv, w["cid"])["token"])
    finally:
        st.corpus.close()
    assert held.path(str(w["root"]), digest).exists()
    reopen(w)


def test_2_reindex_command_rebuilds_under_this_build_s_rules(w):
    _, adm, _ = file(w)
    act = w["cv"].record_act(actor=w["me"], act="material-recorded",
                             conversation=w["other"], about=[],
                             because="needs " + adm, detail={})
    _earlier_rules_index(w, act)
    w["c"].close()
    assert ER._main(["reindex", str(w["root"])]) == 0
    reopen(w)
    conn = w["c"]._store._conn
    assert SE.index_rules(conn) == SE.REF_RULES
    assert conn.execute("SELECT 1 FROM ref_index WHERE src = ? AND target = ?",
                        (act, adm)).fetchone()


PRIOR = Path(r"C:\Work\Mentis-workspace\qc-usability\conv-mgmt"
             r"\review-scratch\erasure4")


@pytest.mark.skipif(not (PRIOR / "code-2c23150").is_dir(),
                    reason="the reviewer's prior-commit snapshot is not here")
def test_2_a_real_prior_commit_brain_keeps_its_referenced_file(tmp_path):
    from mentis.web import _State
    root = tmp_path / "prior"
    manifest = tmp_path / "prior.json"
    subprocess.run([sys.executable, "-B", str(PRIOR / "make_prior_brain.py"),
                    str(root), str(manifest)], check=True,
                   cwd=str(PRIOR / "code-2c23150"))
    ids = json.loads(manifest.read_text(encoding="utf-8"))
    c = api.open_corpus(str(root))
    cv = api.brain(c).conversations
    try:
        cv.change_conversation_state(ids["cid"], "trash", by=ids["me"])
        with pytest.raises(ER.Refused) as refused:
            ER.impact(cv, ids["cid"])
        assert refused.value.refusal["code"] == "reference-index-stale"
    finally:
        c.close()
    st = _State(str(root))
    try:
        inv = ER.inventory(st.cv, ids["cid"])
        assert ids["adm"] in {f["id"] for f in inv["files_kept"]}
        ER.delete(st.cv, ids["cid"], by=ids["me"],
                  token=ER.impact(st.cv, ids["cid"])["token"])
        assert ids["adm"] in st.corpus.operational(id=ids["act"])[0][
            "because"]
    finally:
        st.corpus.close()
    assert held.path(str(root), ids["digest"]).exists()


# 3 ------------------------------------------------------------------------------

def test_3_a_failure_after_the_commit_keeps_the_ledger(w, monkeypatch):
    import sqlite3
    b = backup(w)
    trash(w)
    real = w["cv"].record_act

    def disk_full(*a, **kw):
        if kw.get("act") == ER.CLEANUP_ACT:
            raise sqlite3.OperationalError("database or disk is full")
        return real(*a, **kw)
    with monkeypatch.context() as m:
        m.setattr(w["cv"], "record_act", disk_full)
        got = delete(w)
    assert got["deleted"] is True
    assert got["physical_cleanup"]["status"] == "pending"
    assert "disk is full" in got["physical_cleanup"]["reason"]
    assert [e["deletion"] for e in SE.ledger_entries(w["root"])] == \
        [got["act"]]
    assert list(Path(SE.erase_set_dir(w["root"])).glob("*.json"))
    out = restore(w, b)
    assert out["erasure_ledger"]["served_writable"] is False
    with pytest.raises(M.BrainNotWritable):
        api.open_corpus(str(w["root"]), access="read")
    ER.reapply(str(w["root"]), by=w["me"])
    reopen(w)


# 4 ------------------------------------------------------------------------------

def _gate_by_failed_undo(w, monkeypatch):
    real = SE.ledger_record

    def fail_after_ledger(*a, **kw):
        real(*a, **kw)
        raise OSError("injected failure after the durable ledger")

    def cannot(*a, **kw):
        raise OSError("injected: the ledger cannot be put back")
    with monkeypatch.context() as m:
        m.setattr(SE, "ledger_record", fail_after_ledger)
        m.setattr(SE, "ledger_restore", cannot)
        m.setattr(os, "remove", cannot)
        with pytest.raises(ER.Refused):
            delete(w)


def test_4_another_open_store_is_gated_too(w, monkeypatch):
    trash(w)
    reader = api.open_corpus(str(w["root"]), access="read")
    try:
        assert MARK in json.dumps(reader.read([w["p"]])[0])
        _gate_by_failed_undo(w, monkeypatch)
        with pytest.raises(M.BrainNotWritable) as refused:
            reader.read([w["p"]])
        assert w["cid"] in str(refused.value)
        with pytest.raises(M.BrainNotWritable):
            w["c"].read([w["p"]])
    finally:
        reader.close()
    w["c"].close()
    ER.reapply(str(w["root"]), by=w["me"])
    reopen(w)
    assert SE.erased_by(w["c"].read([w["p"]])[0]["body"])


_CHILD = r"""
import json, sys
sys.path.insert(0, sys.argv[2])
import mentis.api as api
from mentis.spine import migrations as M
c = api.open_corpus(sys.argv[1], access="read")
print("open", flush=True)
sys.stdin.readline()
import time
time.sleep(0.1)       # past the Store's WATCH_S: another process's change
try:
    row = c.read([sys.argv[3]])
    print(json.dumps({"read": row}), flush=True)
except M.BrainNotWritable as exc:
    print(json.dumps({"refused": str(exc)}), flush=True)
c.close()
"""


def test_4_a_store_open_in_another_process_is_gated_too(w, monkeypatch):
    trash(w)
    repo = str(Path(__file__).resolve().parents[1])
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "MENTIS_SERVER")}
    child = subprocess.Popen(
        [sys.executable, "-c", _CHILD, str(w["root"]), repo, w["p"]],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)
    try:
        assert child.stdout.readline().strip() == "open"
        _gate_by_failed_undo(w, monkeypatch)
        child.stdin.write("go\n")
        child.stdin.flush()
        said = json.loads(child.stdout.readline())
    finally:
        child.wait(30)
    assert "refused" in said and MARK not in json.dumps(said)
    w["c"].close()
    ER.reapply(str(w["root"]), by=w["me"])
    reopen(w)


def test_4_the_watch_costs_a_stat_per_scope(w, capsys):
    """Measured, not bounded tightly: what one read scope costs with the
    ledger watch, against the same scope without it."""
    store = w["c"]._store
    n = 3000

    def run():
        t = time.perf_counter()
        for _ in range(n):
            store._rows("SELECT 1")
        return (time.perf_counter() - t) / n * 1e6
    with_watch = run()
    real = store._watch
    store._watch = lambda conn: None
    try:
        without = run()
    finally:
        store._watch = real
    t = time.perf_counter()
    for _ in range(200):
        SE.ledger_signature(store.root)
    stat = (time.perf_counter() - t) / 200 * 1e6
    with capsys.disabled():
        print(f"\nledger watch: {with_watch:.1f} us per read scope with it, "
              f"{without:.1f} us without (+{with_watch - without:.1f} us); "
              f"one ledger signature (two stats) costs {stat:.1f} us and is "
              f"taken at most once per WATCH_S per Store")
    assert with_watch - without < 100


# noncritical ----------------------------------------------------------------------

@pytest.mark.parametrize("how", ["check", "reapply"])
def test_repair_rebuilds_every_deletion_the_record_holds_and_warns(w, how,
                                                                    capsys):
    b = backup(w)
    trash(w)
    got = delete(w)
    Path(SE.ledger_path(w["root"])).write_bytes(b'{"corpus_id":')
    Path(SE.erase_set_dir(w["root"]), got["act"] + ".json").unlink()
    w["c"].close()
    root = str(w["root"])
    if how == "check":
        rc = ER._main(["check", root, "--repair"])
    else:
        rc = ER._main(["reapply", root, "--by", w["me"]])
    assert rc == 2
    assert "LOST ITS ROLLBACK PROTECTION" in capsys.readouterr().err
    lines = SE.ledger_entries(root)
    assert [e["deletion"] for e in lines] == [got["act"]]
    assert ("entry", w["p"]) in SE.read_erase_set(root, lines[0])["rows"]
    # and the earlier backup is still refused
    plan_out = restore({"c": api.open_corpus(root), "root": w["root"]}, b)
    assert plan_out["erasure_ledger"]["served_writable"] is False
    ER.reapply(root, by=w["me"])
    reopen(w)
