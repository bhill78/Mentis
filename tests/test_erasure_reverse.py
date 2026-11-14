"""The reverse of 0002-erasure, for rollback (owner decision 2026-11-14).

`migrations.reverse_erasure`: refused, with no override, after any deletion;
otherwise removes the erasure table, the reference index, restores 0001's
protection triggers and ledger, and lowers user_version -- every existing
record unchanged, one `schema-migration-reversed` act appended. The reversed
Brain re-migrates forward. And what 441ae94 makes of it (see the docstring of
`test_441ae94_and_the_reversed_brain`).
"""
from __future__ import annotations

import inspect as _inspect
import json
import os
import sqlite3
import subprocess
import sys
import time

import pytest

import mentis.api as api
from mentis.conversation import erasure as ER
from mentis.spine import erasure as SE
from mentis.spine import migrations as M
from mentis.web import fixture

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def text(s):
    return [{"type": "text", "text": s}]


@pytest.fixture
def b(tmp_path):
    """A Brain the candidate made and used: posts, a rename, Archive, Trash,
    Restore, a file -- and no deletion."""
    from mentis import artifacts
    from mentis.conversation import posting
    root = str(tmp_path / "brain")
    built = fixture.build(root)
    built["corpus"].close()
    c = api.open_corpus(root)
    cv = api.brain(c).conversations
    me = built["who"]["@brian"]
    a = cv.open_conversation("CAND-A", attributed_to=me)
    pa = cv.say(a, me, text("CANDIDATE-POST-1"))
    cv.rename_conversation(a, "CAND-A-RENAMED", by=me)
    arc = cv.open_conversation("CAND-B", attributed_to=me)
    cv.change_conversation_state(arc, "archive", by=me)
    tr = cv.open_conversation("CAND-T", attributed_to=me)
    pt = cv.say(tr, me, text("CANDIDATE-POST-T"))
    cv.change_conversation_state(tr, "trash", by=me)
    st = artifacts.stage(root, b"CANDIDATE-FILE", "text/plain")
    got, _ = posting.post(cv, c, a, {"author": me, "parts": [
        {"type": "file", "ref": st["staged"], "alt": "c.txt",
         "media_type": "text/plain"}]}, written_by=lambda: None)
    c.close()
    return {"root": root, "me": me, "a": a, "pa": pa, "arc": arc, "tr": tr,
            "pt": pt, "file_post": got["turn"], "tmp": tmp_path}


def _raw(root):
    conn = sqlite3.connect(os.path.join(root, "corpus.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _state(root):
    conn = _raw(root)
    try:
        return {"fp": M._fingerprint(conn),
                "ledger": [tuple(r) for r in conn.execute(
                    "SELECT * FROM schema_migration ORDER BY seq")],
                "uv": conn.execute("PRAGMA user_version").fetchone()[0],
                "tables": sorted(M._tables(conn)),
                "triggers": sorted(tuple(r) for r in conn.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type = "
                    "'trigger'"))}
    finally:
        conn.close()


def test_the_reversal_keeps_every_record_and_restores_0001(b):
    before = _state(b["root"])
    out = M.reverse_erasure(b["root"], by=b["me"], because="roll back")
    after = _state(b["root"])
    for t, v in before["fp"].items():
        if t != "operational":
            assert after["fp"][t] == v, t
    assert after["fp"]["operational"]["rows"] == \
        before["fp"]["operational"]["rows"] + 1
    conn = _raw(b["root"])
    try:
        rows = [tuple(r) for r in conn.execute(
            "SELECT * FROM operational ORDER BY seq")]
        last = conn.execute("SELECT act, actor, detail FROM operational "
                            "ORDER BY seq DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    assert last["act"] == M.REVERSED_ACT and last["actor"] == b["me"]
    detail = json.loads(last["detail"])
    assert detail["ledger_row"]["id"] == "0002-erasure"
    assert detail["ledger_row"]["checksum"] == M.ERASURE.checksum
    # the ledger, user_version, tables and triggers are exactly 0001's
    v1 = str(b["tmp"] / "v1")
    M.create_brain(v1, ms=(M.ADOPT,))
    fresh = _state(v1)
    assert [r[1] for r in after["ledger"]] == ["0001-adopt"]
    assert after["ledger"][0] == before["ledger"][0]
    assert after["uv"] == M.mirror(1) == fresh["uv"]
    assert after["tables"] == fresh["tables"]
    assert after["triggers"] == fresh["triggers"]
    assert out["to_version"] == 1
    # the chain is intact and the candidate says: needs migrate
    with SE.ledger_unchecked():
        c = api.open_corpus(b["root"], access="read")
        try:
            assert c.verify_chain()["intact"]
            assert c._store.status.state == M.NEEDS_MIGRATE
        finally:
            c.close()
    assert len(rows) == before["fp"]["operational"]["rows"] + 1


def test_the_reversed_brain_migrates_forward_and_deletes_again(b):
    M.reverse_erasure(b["root"], by=b["me"], because="roll back")
    assert M.apply(b["root"])["applied"] == ["0002-erasure"]
    assert M.status_of(b["root"]).state == M.OPEN
    c = api.open_corpus(b["root"])
    cv = api.brain(c).conversations
    try:
        assert cv.conversation_name(b["a"]) == "CAND-A-RENAMED"
        assert cv.conversation_state(b["arc"]) == "archived"
        assert cv.conversation_state(b["tr"]) == "trashed"
        assert c.verify_chain()["intact"]
        got = ER.delete(cv, b["tr"], by=b["me"],
                        token=ER.impact(cv, b["tr"])["token"])
        assert got["deleted"] and c.verify_chain()["intact"]
    finally:
        c.close()
    # and then the reversal is refused
    with pytest.raises(M.MigrationRefused, match="permanent deletion"):
        M.reverse_erasure(b["root"], by=b["me"], because="roll back")


def _signal(b, how):
    root = b["root"]
    if how == "deletion":
        c = api.open_corpus(root)
        cv = api.brain(c).conversations
        ER.delete(cv, b["tr"], by=b["me"], token=ER.impact(cv, b["tr"])["token"])
        c.close()
    elif how in ("act", "cleanup-act"):
        c = api.open_corpus(root)
        c._store.append_operational({
            "id": "opr-" + os.urandom(6).hex(), "at": time.time(),
            "actor": b["me"],
            "act": ("conversation-deleted" if how == "act"
                    else "conversation-erasure-cleanup"),
            "about": [], "detail": {}})
        c.close()
    elif how == "ledger-line":
        SE.ledger_append(root, {"corpus_id": "elsewhere", "deletion": "x"})
    elif how == "erase-set":
        os.makedirs(SE.erase_set_dir(root), exist_ok=True)
        with open(os.path.join(SE.erase_set_dir(root), "opr-x.json"),
                  "w") as fh:
            fh.write("{}")
    elif how == "marker":
        c = api.open_corpus(root)
        c._store.append_operational({
            "id": "opr-" + os.urandom(6).hex(), "at": time.time(),
            "actor": b["me"], "act": "turn-said", "about": [],
            "detail": {"erased": "opr-000000000000"}})
        c.close()


@pytest.mark.parametrize("how", ["deletion", "act", "cleanup-act",
                                 "ledger-line", "erase-set", "marker"])
def test_any_deletion_signal_refuses_and_changes_nothing(b, how):
    _signal(b, how)
    before = _state(b["root"])
    with pytest.raises(M.MigrationRefused, match="REFUSED") as refused:
        M.reverse_erasure(b["root"], by=b["me"], because="roll back")
    assert "no override" in str(refused.value)
    assert _state(b["root"]) == before
    assert M.main if hasattr(M, "main") else True


def test_there_is_no_override(b):
    params = set(_inspect.signature(M.reverse_erasure).parameters)
    assert params == {"root", "by", "because", "hook"}
    from mentis import migrate
    with pytest.raises(SystemExit):
        migrate.main([b["root"], "--reverse", "0002-erasure", "--by",
                      b["me"], "--because", "x", "--force"])
    assert migrate.main([b["root"], "--reverse", "0001-adopt", "--by",
                         b["me"], "--because", "x"]) == 2


def test_the_cli_reverses(b, capsys):
    from mentis import migrate
    assert migrate.main([b["root"], "--reverse", "0002-erasure", "--by",
                         b["me"], "--because", "rollback"]) == 0
    assert json.loads(capsys.readouterr().out)["to_version"] == 1


def test_a_failure_inside_the_reversal_leaves_the_brain_as_it_was(b):
    before = _state(b["root"])

    def boom(label):
        if label == "after-ledger":
            raise RuntimeError("injected failure inside the reversal")
    with pytest.raises(RuntimeError):
        M.reverse_erasure(b["root"], by=b["me"], because="roll back",
                          hook=boom)
    assert _state(b["root"]) == before
    assert M.status_of(b["root"]).state == M.OPEN


_OLD = r"""
import json, os, sys
sys.path.insert(0, sys.argv[2])
import mentis
assert os.path.normcase(os.path.abspath(mentis.__file__)).startswith(
    os.path.normcase(os.path.abspath(sys.argv[2])))
import mentis.api as api
from mentis.spine import migrations as M
from mentis import artifacts
from mentis.conversation import posting
root, ids = sys.argv[1], json.loads(sys.argv[3])
st = M.status_of(root)
out = {"state": st.state, "version": st.version, "problems": st.problems}
if st.state in M.WRITABLE:
    c = api.open_corpus(root, access="write")
    cv = api.brain(c).conversations
    out["names"] = sorted(x["body"]["name"] for x in cv.all_conversations())
    out["posts"] = [c.read([ids[k]])[0]["body"]["parts"][0]["text"]
                    for k in ("pa", "pt")]
    out["wrote"] = cv.say(ids["a"], ids["me"],
                          [{"type": "text", "text": "OLD-CODE-WRITE"}])
    out["into_trash"] = cv.say(ids["tr"], ids["me"],
                               [{"type": "text", "text": "OLD-INTO-TRASH"}])
    s = artifacts.stage(root, b"OLD-FILE", "text/plain")
    got, _ = posting.post(cv, c, ids["a"], {"author": ids["me"], "parts": [
        {"type": "file", "ref": s["staged"], "alt": "o.txt",
         "media_type": "text/plain"}]}, written_by=lambda: None)
    out["file_post"] = got.get("turn")
    out["note"] = c.create_and_establish(kind="note", body={"text": "OLD"},
                                         attributed_to=ids["me"])
    out["intact"] = c.verify_chain()["intact"]
    c.close()
print(json.dumps(out))
"""

_TOLERATE = '''        reversed_refs = set()
        for (detail,) in conn.execute(
                "SELECT detail FROM operational WHERE act = ?",
                ("schema-migration-reversed",)):
            try:
                reversed_refs.add(json.loads(detail)["ledger_row"][
                    "operational_ref"])
            except (TypeError, ValueError, KeyError):
                pass
        for oid in sorted(set(acts) - refs - reversed_refs):'''


def _snapshot(tmp_path, commit):
    dest = tmp_path / f"code-{commit}"
    dest.mkdir()
    arch = subprocess.run(["git", "-C", REPO, "archive", commit, "mentis"],
                          capture_output=True)
    if arch.returncode:
        pytest.skip(f"{commit} is not in this clone")
    import io
    import tarfile
    tarfile.open(fileobj=io.BytesIO(arch.stdout)).extractall(dest,
                                                             filter="data")
    return dest


def _run_old(code, b, ids):
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "MENTIS_SERVER")}
    got = subprocess.run([sys.executable, "-I", "-c", _OLD, b["root"],
                          str(code), json.dumps(ids)],
                         capture_output=True, text=True, env=env, cwd=str(code))
    assert got.returncode == 0, got.stderr
    return json.loads(got.stdout.strip().splitlines()[-1])


def test_441ae94_and_the_reversed_brain(b):
    """THE DECISIVE CHECK, AND ITS FINDING (blocker, reported):
    441ae94 as released refuses the reversed Brain as NEEDS ATTENTION for
    exactly one reason -- the 0002 `schema-migrated` act stays in the record
    (no record may change) and 441ae94 requires a ledger row for every such
    act, while the old Rust front requires the ledger to be exactly [0001].
    With only that one check taught to accept the recorded reversal,
    441ae94 opens, reads (renames, posts of archived/trashed conversations,
    files) and writes (a turn, a file, an entry) the reversed Brain, its
    chain intact; and the candidate re-migrates and reads all of it."""
    ids = {k: b[k] for k in ("a", "pa", "tr", "pt", "me")}
    M.reverse_erasure(b["root"], by=b["me"], because="roll back")
    old = _snapshot(b["tmp"], "441ae94")
    released = _run_old(old, b, ids)
    assert released["state"] == M.NEEDS_ATTENTION
    assert len(released["problems"]) == 1
    assert "has no ledger row" in released["problems"][0]
    # the same code with that one check accepting the recorded reversal
    p = old / "mentis" / "spine" / "migrations.py"
    s = p.read_text(encoding="utf-8")
    s = s.replace("        for oid in sorted(set(acts) - refs):", _TOLERATE)
    p.write_text(s, encoding="utf-8", newline="")
    got = _run_old(old, b, ids)
    assert got["state"] == M.OPEN and got["intact"]
    assert "CAND-A-RENAMED" in got["names"]
    assert got["posts"] == ["CANDIDATE-POST-1", "CANDIDATE-POST-T"]
    # forward again, and the candidate reads what the old code wrote
    assert M.apply(b["root"])["applied"] == ["0002-erasure"]
    c = api.open_corpus(b["root"])
    try:
        cv = api.brain(c).conversations
        assert c.read([got["wrote"]])[0]["body"]["parts"][0]["text"] == \
            "OLD-CODE-WRITE"
        assert c.read([got["note"]])
        # COMPATIBILITY: the old code posted into the conversation the
        # candidate had put in Trash; it is still in Trash
        assert cv.conversation_state(b["tr"]) == "trashed"
        assert c.read([got["into_trash"]])
        assert c.verify_chain()["intact"]
    finally:
        c.close()
