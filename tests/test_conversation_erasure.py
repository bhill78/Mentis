"""Permanent deletion with epistemic preservation (owner decision 2026-11-13;
contract conv-mgmt/erasure-design.md).

Attested erasure (schema 0002-erasure, `mentis.spine.erasure`), the erase /
keep inventory (`mentis.conversation.erasure.inventory`), files, the
reference index, the Trash / deleted write guard, the routes and readers.
Destructive: every Brain here is a pytest fixture Brain.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from mentis import artifacts
from mentis.conversation import erasure as ER
from mentis.conversation import posting, versions
from mentis.spine import erasure as SE
from mentis.spine import held
from mentis.web import _Handler, _State, fixture
from mentis.worker import CAPABILITY_HEADER

_ops = itertools.count(1)
SEEDS = {
    "name": "SEEDNAME-q7Zr2",
    "renamed": "SEEDRENAMED-k3Lw9",
    "post": "SEEDPOST-a1Bx4",
    "reply": "SEEDREPLY-c9Dy5",
    "edited": "SEEDEDITED-e2Fz6",
    "topic": "SEEDTOPIC-g4Hv7",
    "file": "SEEDFILENAME-i6Ju8",
    "bytes": "SEEDBYTES-m8Np0",
    "material": "SEEDMATERIAL-o1Pq2",
    "detail": "SEEDDETAIL-s3Rt4",
}


def text(s):
    return [{"type": "text", "text": s}]


def _post_file(cv, corpus, cid, me, data, name, words="with a file"):
    st = artifacts.stage(corpus.root, data, "text/plain")
    out, _ = posting.post(cv, corpus, cid, {"author": me, "parts": [
        {"type": "text", "text": words},
        {"type": "file", "ref": st["staged"], "alt": name,
         "media_type": "text/plain"}]}, written_by=lambda: None)
    post = out.get("turn") or out.get("id")
    body = corpus.read([post])[0]["body"]
    adm = [p["ref"] for p in body["parts"] if p.get("type") == "file"][0]
    return post, adm, st["digest"]


@pytest.fixture()
def world(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    built = fixture.build(str(root))
    state = _State(str(root))
    import mentis.web as web
    monkeypatch.setattr(web, "dispatch_soon", lambda st, **kw: None)
    handler = type("H", (_Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    cv, corpus = state.cv, state.corpus
    me = built["who"]["@brian"]
    c = cv.open_conversation(SEEDS["name"], attributed_to=me)
    cv.rename_conversation(c, SEEDS["renamed"], by=me)
    p1 = cv.say(c, me, text(SEEDS["post"] + " the first post"))
    p2 = cv.say(c, me, text(SEEDS["reply"] + " a reply"), replies_to=p1)
    p3 = cv.say(c, me, text("to be edited"))
    versions.edit(cv, p3, by=me, text=SEEDS["edited"] + " edited words")
    t = cv.open_topic(c, SEEDS["topic"], attributed_to=me)
    cv.assign_topic(p1, t)
    # files: exclusive; one Admission named in two conversations; the same
    # bytes under another Admission elsewhere; one a kept record cites; one
    # also a profile picture
    fx, adm_x, dig_x = _post_file(cv, corpus, c, me,
                                  (SEEDS["bytes"] + " exclusive").encode(),
                                  SEEDS["file"] + "-x.txt")
    fs, adm_s, dig_s = _post_file(cv, corpus, c, me, b"shared admission",
                                  "shared.txt")
    fb, adm_b, dig_b = _post_file(cv, corpus, c, me, b"same bytes twice",
                                  "same-bytes.txt")
    fr, adm_r, dig_r = _post_file(cv, corpus, c, me, b"cited by a note",
                                  "cited.txt")
    fa, adm_a, dig_a = _post_file(cv, corpus, c, me, b"also an avatar",
                                  "avatar.png")
    other = cv.open_conversation("Elsewhere", attributed_to=me)
    away = cv.say(other, me, text("placed into it"))
    cv.link_into(away, c, by=me)
    o_shared = cv.say(other, me, [{"type": "text", "text": "same admission"},
                                  {"type": "file", "ref": adm_s}])
    o_bytes, adm_b2, _ = _post_file(cv, corpus, other, me, b"same bytes twice",
                                    "same-bytes-elsewhere.txt")
    note = corpus.create_and_establish(
        kind="note", body={"text": "a note citing a file"}, attributed_to=me)
    corpus.write(body={"cite": None}, attributed_to=me,
                 link={"from": note, "to": adm_r, "relation": "extracted-from"})
    corpus.write(body={"reason": "chosen as this Participant's picture"},
                 attributed_to=me, link={"from": built["who"]["@Vera"],
                                         "to": adm_a,
                                         "relation": "pictured-by"})
    # knowledge from its posts: a lesson and a rule extracted from p1, an
    # outcome of p2
    lesson = corpus.create_and_establish(
        kind="lesson", body={"text": "lesson kept from the first post"},
        attributed_to=me)
    corpus.write(body={"cite": None}, attributed_to=me,
                 link={"from": lesson, "to": p1, "relation": "extracted-from"})
    rule = corpus.create_and_establish(
        kind="rule", body={"text": "rule kept from the first post"},
        attributed_to=me)
    corpus.write(body={"cite": None}, attributed_to=me,
                 link={"from": rule, "to": p1, "relation": "extracted-from"})
    outcome = corpus.create_and_establish(
        kind="outcome", body={"text": "outcome kept", "result": "met"},
        attributed_to=me)
    corpus.write(body={}, attributed_to=me,
                 link={"from": outcome, "to": p2, "relation": "outcome-of"})
    # a run's material, and an act with words, recorded in the conversation
    corpus._store.append_delivery({
        "id": "dlv-" + "1" * 12, "execution": "exe-" + "2" * 12,
        "conversation": c, "participant": built["who"]["@Nadia"],
        "runtime": "claude", "mechanism": "stub", "at": time.time(),
        "material": {"text": SEEDS["material"] + " delivered"},
        "behavioural_sources": [], "operation_ok": True})
    cv.record_act(actor=built["who"]["@Nadia"], act="turn-said",
                  conversation=c, turn=p2, about=[p2],
                  detail={"said": SEEDS["detail"] + " in an act"})
    yield {"base": f"http://127.0.0.1:{httpd.server_address[1]}",
           "st": state, "cv": cv, "corpus": corpus, "me": me, "c": c,
           "other": other, "away": away, "posts": [p1, p2, p3],
           "topic": t, "who": built["who"], "root": str(root),
           "files": {"x": (fx, adm_x, dig_x), "s": (fs, adm_s, dig_s),
                     "b": (fb, adm_b, dig_b), "r": (fr, adm_r, dig_r),
                     "a": (fa, adm_a, dig_a)},
           "adm_b2": adm_b2, "o_shared": o_shared, "o_bytes": o_bytes,
           "note": note, "lesson": lesson, "rule": rule, "outcome": outcome}
    httpd.shutdown()
    state.corpus.close() if hasattr(state.corpus, "close") else None


def _req(world, method, path, body=None, headers=None):
    req = urllib.request.Request(
        world["base"] + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1",
                 **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"raw": raw.decode("utf-8", "replace")}


def change(world, cid, verb, **more):
    return _req(world, "POST", f"/fluid/api/conversations/{cid}/{verb}",
                {"author": world["me"], "op": f"er-{next(_ops)}", **more})


def trash(world, cid=None):
    status, got = change(world, cid or world["c"], "trash")
    assert status == 200, got


def delete(world, cid=None):
    cid = cid or world["c"]
    status, imp = _req(world, "GET",
                       f"/fluid/api/conversations/{cid}/deletion-impact")
    assert status == 200, imp
    status, got = _req(world, "POST", f"/fluid/api/conversations/{cid}/delete",
                       {"author": world["me"], "token": imp["token"]})
    assert status == 200, got
    return imp, got


def all_rows(world):
    conn = world["corpus"]._store._conn
    out = {}
    for t in ("entry", "operational", "delivery"):
        for r in conn.execute(f"SELECT * FROM {t} ORDER BY seq"):
            out[(t, r["id"])] = tuple(r)
    return out


def raw_bytes(root):
    raw = b""
    for n in ("corpus.db", "corpus.db-wal", "corpus.db-shm"):
        p = os.path.join(root, n)
        if os.path.exists(p):
            with open(p, "rb") as fh:
                raw += fh.read()
    return raw


# -- 1. attested erasure: triggers -------------------------------------------------

def _deletion_act(world, aid=None):
    aid = aid or f"opr-{os.urandom(6).hex()}"
    world["corpus"]._store.append_operational({
        "id": aid, "at": time.time(), "actor": world["me"],
        "act": SE.DELETION_ACT, "about": [], "detail": {}})
    return aid


def _row(conn, tbl, rid):
    return conn.execute(f"SELECT * FROM {tbl} WHERE id = ?", (rid,)).fetchone()


def test_the_triggers_refuse_every_unsanctioned_change(world):
    store = world["corpus"]._store
    conn = store._conn
    p = world["posts"][0]
    a = _deletion_act(world)
    b = _deletion_act(world)
    h = _row(conn, "entry", p)["hash"]
    bad = [
        # no erasure record at all
        ("UPDATE entry SET body = ? WHERE id = ?", (SE.marker(a), p)),
        # a non-content column
        ("UPDATE entry SET attributed_to = 'someone' WHERE id = ?", (p,)),
        ("UPDATE entry SET hash = 'x' WHERE id = ?", (p,)),
        ("DELETE FROM entry WHERE id = ?", (p,)),
        ("DELETE FROM operational WHERE id = ?", (a,)),
        ("DELETE FROM delivery WHERE id = ?", ("dlv-" + "1" * 12,)),
    ]
    for sql, args in bad:
        with pytest.raises(sqlite3.DatabaseError):
            with store.write():
                conn.execute(sql, args)
    # an erasure record without its act, or naming a row with another hash
    for row in ((f"opr-{'9' * 12}", "entry", p, h, "r"),
                (a, "entry", p, "not-its-hash", "r"),
                (a, "entry", "ent-nosuchrow00", "", "r")):
        with pytest.raises(sqlite3.DatabaseError):
            with store.write():
                conn.execute("INSERT INTO erasure (deletion, tbl, row_id, "
                             "row_hash, residual) VALUES (?,?,?,?,?)", row)
    with store.write():
        conn.execute("INSERT INTO erasure (deletion, tbl, row_id, row_hash, "
                     "residual) VALUES (?,?,?,?,?)", (a, "entry", p, h, "r"))
    # the marker naming another act; a content change that is not the marker;
    # a content change together with a structural one
    for sql, args in (
            ("UPDATE entry SET body = ? WHERE id = ?", (SE.marker(b), p)),
            ("UPDATE entry SET body = '{}' WHERE id = ?", (p,)),
            ("UPDATE entry SET body = ?, written_by = 'x' WHERE id = ?",
             (SE.marker(a), p))):
        with pytest.raises(sqlite3.DatabaseError):
            with store.write():
                conn.execute(sql, args)
    # the sanctioned one passes, once
    with store.write():
        conn.execute("UPDATE entry SET body = ? WHERE id = ?",
                     (SE.marker(a), p))
    for new in (SE.marker(a), SE.marker(b), "{}"):
        with pytest.raises(sqlite3.DatabaseError):
            with store.write():
                conn.execute("UPDATE entry SET body = ? WHERE id = ?",
                             (new, p))
    # erasure rows are append-only; a second for the same row is refused
    for sql in ("UPDATE erasure SET residual = 'x'", "DELETE FROM erasure",
                "INSERT OR REPLACE INTO erasure (deletion, tbl, row_id, "
                "row_hash, residual) VALUES ('%s', 'entry', '%s', '%s', 'y')"
                % (a, p, h)):
        with pytest.raises(sqlite3.DatabaseError):
            with store.write():
                conn.execute(sql)
    # operational: `because` must go to NULL with the detail
    act = world["corpus"].operational(conversation=world["c"])[0]["id"]
    ah = _row(conn, "operational", act)["hash"]
    with store.write():
        conn.execute("INSERT INTO erasure (deletion, tbl, row_id, row_hash, "
                     "residual) VALUES (?,?,?,?,?)",
                     (a, "operational", act, ah, "r"))
    with pytest.raises(sqlite3.DatabaseError):
        with store.write():
            conn.execute("UPDATE operational SET detail = ?, because = 'x' "
                         "WHERE id = ?", (SE.marker(a), act))
    with pytest.raises(sqlite3.DatabaseError):
        with store.write():
            conn.execute("UPDATE operational SET detail = ?, actor = 'x' "
                         "WHERE id = ?", (SE.marker(a), act))


def test_the_migration_is_declared_and_its_triggers_are_required(world):
    from mentis.spine import migrations as M
    st = M.status_of(world["root"])
    assert st.state == M.OPEN and st.version == 2 and st.min_reader == 2
    assert [r["id"] for r in st.ledger] == ["0001-adopt", "0002-erasure"]
    assert "erasure_attested" in M.required_triggers(st.ledger)
    # a migration may not drop an append-only trigger it does not re-create
    assert M.forbidden("DROP TRIGGER entry_no_update")
    assert M.forbidden("DROP TRIGGER erasure_no_delete")
    assert M.forbidden("DELETE FROM erasure")


def test_a_version_1_brain_upgrades_and_its_index_is_the_rebuild(tmp_path):
    from mentis.spine import migrations as M
    import mentis.api as api
    root = str(tmp_path / "old")
    M.create_brain(root, ms=(M.ADOPT,))
    c = api.open_corpus(root, access="read")
    assert c._store.status.state == M.NEEDS_MIGRATE
    c.close()
    assert M.apply(root)["applied"] == ["0002-erasure"]
    c = api.open_corpus(root)
    cv = api.brain(c).conversations
    p = cv.resolve_participant("@o", about="the owner")
    cid = cv.open_conversation("x", attributed_to=p)
    cv.say(cid, p, text("y"))
    conn = c._store._conn
    kept = SE.index_rows(conn)
    with c._store.write():
        SE.rebuild(conn)
    assert SE.index_rows(conn) == kept and kept
    assert c.verify_chain()["intact"]
    c.close()


# -- 1. the verifier -------------------------------------------------------------

def _tamper(root, *sqls):
    """What an attacker with the file does: triggers dropped, rows edited."""
    conn = sqlite3.connect(os.path.join(root, "corpus.db"))
    try:
        for s in sqls:
            conn.execute(s)
        conn.commit()
    finally:
        conn.close()


def _verify(root):
    import mentis.api as api
    c = api.open_corpus(root, access="read")
    try:
        return c.verify_chain()
    finally:
        c.close()


def test_the_verifier_accepts_an_attested_erasure_and_counts_it(world):
    trash(world)
    _, got = delete(world)
    v = world["corpus"].verify_chain()
    assert v["intact"], v
    assert v["erasures"]["acts"] == 1 and v["erasures"]["broken"] is None
    assert v["erasures"]["rows"] == got["erased_rows"]
    assert v["erasures"]["pending"] == 0
    assert sum(s["erased"] for s in v["streams"].values()) == got["erased_rows"]
    assert all(v["streams"][t]["erased"] > 0
               for t in ("entry", "operational", "delivery"))
    # the separate backup / copy walks call the same code
    from mentis.spine import backup
    conn = sqlite3.connect(os.path.join(world["root"], "corpus.db"))
    conn.row_factory = sqlite3.Row
    try:
        b = backup._chain(conn)
    finally:
        conn.close()
    assert b["intact"] and b["erasures"] == v["erasures"]


@pytest.mark.parametrize("how", ["structural", "erasure-row", "act-digest",
                                 "plain-row", "marker-act"])
def test_the_verifier_detects_tampering(world, how):
    trash(world)
    _, got = delete(world)
    world["st"].corpus.close()
    root = world["root"]
    p = world["posts"][0]
    act = got["act"]
    other = world["away"]
    sqls = {
        "structural": ["DROP TRIGGER entry_no_update",
                       f"UPDATE entry SET attributed_to = 'x' WHERE id = '{p}'"],
        "erasure-row": ["DROP TRIGGER erasure_no_update",
                        f"UPDATE erasure SET residual = 'x' WHERE row_id = '{p}'"],
        "act-digest": ["DROP TRIGGER operational_no_update",
                       "UPDATE operational SET detail = json_set(detail, "
                       f"'$.erasure.digest', 'x') WHERE id = '{act}'"],
        "plain-row": ["DROP TRIGGER entry_no_update",
                      f"UPDATE entry SET body = '{{}}' WHERE id = '{other}'"],
        "marker-act": ["DROP TRIGGER entry_no_update",
                       "UPDATE entry SET body = '{\"erased\":\"opr-000000000000\"}'"
                       f" WHERE id = '{p}'"],
    }[how]
    _tamper(root, *sqls)
    v = _verify(root)
    assert v["intact"] is False, v


def test_the_digest_alone_is_checked_against_the_rows(world):
    """An erasure row removed (its act's count and digest no longer match)."""
    trash(world)
    _, got = delete(world)
    world["st"].corpus.close()
    _tamper(world["root"], "DROP TRIGGER erasure_no_delete",
            "DELETE FROM erasure WHERE seq = (SELECT MAX(seq) FROM erasure "
            "WHERE tbl = 'delivery')")
    v = _verify(world["root"])
    assert v["intact"] is False
    # the erased delivery row has no erasure row now: a content break, and
    # the act's count no longer matches
    assert v["streams"]["delivery"]["broken_at"] is not None \
        or v["erasures"]["broken"] is not None


def test_an_attested_row_not_yet_erased_is_pending(world):
    store = world["corpus"]._store
    conn = store._conn
    a = _deletion_act(world)
    p = world["posts"][1]
    h = _row(conn, "entry", p)["hash"]
    with store.write():
        conn.execute("INSERT INTO erasure (deletion, tbl, row_id, row_hash, "
                     "residual) VALUES (?,?,?,?,?)", (a, "entry", p, h, "r"))
    v = world["corpus"].verify_chain()
    assert v["erasures"]["pending"] == 1
    # the act records no rows, while one names it: its digest does not match
    assert v["erasures"]["broken"]["deletion"] == a


# -- 1.5 physical removal ----------------------------------------------------------

def test_seeded_content_is_gone_from_the_database_files(world):
    root = world["root"]
    before = raw_bytes(root)
    seeded = [s.encode() for k, s in SEEDS.items()]
    present = [s for s in seeded if s in before]
    # the bytes themselves are held outside corpus.db; everything else is in it
    assert set(present) >= {s.encode() for k, s in SEEDS.items()
                            if k != "bytes"}
    trash(world)
    _, got = delete(world)
    assert got["checkpoint"]["truncated"], got["checkpoint"]
    after = raw_bytes(root)
    left = [s for s in seeded if s in after]
    assert left == [], left
    # the exclusive file's bytes are gone from the store (unlinked)
    assert not held.path(root, world["files"]["x"][2]).exists()


# -- 2. what is erased, what is kept --------------------------------------------------

def test_knowledge_from_its_posts_keeps_body_and_standing(world):
    corpus = world["corpus"]
    keep = [world["lesson"], world["rule"], world["outcome"], world["note"]]
    before = {e["id"]: e for e in corpus.read(keep)}
    standing = {k: corpus.stands(k)["stands"] for k in keep}
    trash(world)
    delete(world)
    after = {e["id"]: e for e in corpus.read(keep)}
    assert after == before
    assert {k: corpus.stands(k)["stands"] for k in keep} == standing
    # their links still resolve: both ends exist
    for k in keep:
        for l in corpus.links(frm=k):
            assert corpus.read([l["link"]["to"]]), l


def test_other_conversations_are_byte_for_byte_untouched(world):
    before = all_rows(world)
    trash(world)
    _, got = delete(world)
    after = all_rows(world)
    conn = world["corpus"]._store._conn
    erased = {(t, r) for t, r in conn.execute(
        "SELECT tbl, row_id FROM erasure")}
    assert len(erased) == got["erased_rows"]
    for key, row in before.items():
        if key in erased:
            assert after[key] != row
            continue
        assert after[key] == row, key
    # nothing of another conversation was erased
    other_posts = {world["away"], world["o_shared"], world["o_bytes"]}
    assert not {r for _, r in erased} & other_posts
    assert not any(t == "operational" and before[(t, r)][5] == world["other"]
                   for t, r in erased if (t, r) in before
                   and t == "operational")


def test_the_inventory_erases_its_content_and_keeps_structure(world):
    cv, c = world["cv"], world["c"]
    trash(world)
    inv = ER.inventory(cv, c)
    p1, p2, p3 = world["posts"]
    assert {c, p1, p2, p3, world["topic"]} <= set(inv["entries"])
    # the rename's version and the edit's version are erased with them
    versions_ = [e for e in inv["entries"] if e not in inv["roots"]]
    assert len(versions_) >= 2
    kinds = set(inv["kind_of"].values())
    assert kinds <= {"conversation", "contribution", "topic"} | \
        ER.OCCURRENCE_KINDS
    for kept in (world["lesson"], world["rule"], world["outcome"],
                 world["note"], world["away"], world["other"]):
        assert kept not in inv["entries"]
    assert [f["id"] for f in inv["files_removed"]] == sorted(
        [world["files"]["x"][1], world["files"]["b"][1]])
    delete(world)
    corpus = world["corpus"]
    # every link is still there, both ends still exist
    for l in corpus.links(to=c) + corpus.links(frm=p1) + corpus.links(to=p1):
        assert corpus.read([l["link"]["from"]]) or \
            l["link"]["from"].startswith("opr-")
        assert corpus.read([l["link"]["to"]])
    # erased bodies are the marker; ids, authors and times are kept
    for e in corpus.read([c, p1, p2, p3, world["topic"]]):
        assert SE.erased_by(e["body"])
        assert e["attributed_to"] and e["recorded_at"]


# -- 3. files and the reference index --------------------------------------------

def test_files_exclusive_removed_shared_kept(world):
    root = world["root"]
    trash(world)
    imp, got = delete(world)
    labels = {f["label"] for f in imp["files_removed"]}
    assert labels == {SEEDS["file"] + "-x.txt", "same-bytes.txt"}
    kept = {f["label"]: f["why"] for f in imp["files_kept"]}
    assert kept == {"shared.txt": "referenced by something that is kept",
                    "cited.txt": "referenced by something that is kept",
                    "avatar.png": "a profile picture"}
    fx, adm_x, dig_x = world["files"]["x"]
    assert not held.path(root, dig_x).exists()
    # same bytes under another Admission elsewhere: this Admission is purged
    # and erased, the bytes stay for the other
    _, adm_b, dig_b = world["files"]["b"]
    assert held.path(root, dig_b).exists()
    assert artifacts.describe(world["corpus"], world["adm_b2"],
                              verify=False)["state"] == "held"
    for key in ("s", "r", "a"):
        _, adm, dig = world["files"][key]
        assert held.path(root, dig).exists()
        assert world["corpus"].read([adm])[0]["body"].get("content") == "held"
    for adm in (adm_x, adm_b):
        assert SE.erased_by(world["corpus"].read([adm])[0]["body"])
        assert world["corpus"].links(relation="purged", to=adm)


def test_the_reference_index_is_its_rebuild(world):
    store = world["corpus"]._store
    conn = store._conn
    trash(world)
    delete(world)
    world["cv"].say(world["other"], world["me"], text("after"))
    with store.write():
        SE.catch_up(conn)
    kept = SE.index_rows(conn)
    with store.write():
        SE.rebuild(conn)
    assert SE.index_rows(conn) == kept
    # a part's reference is indexed with its home conversation
    _, adm_s, _ = world["files"]["s"]
    rows = conn.execute("SELECT src, src_conversation, kind FROM ref_index "
                        "WHERE target = ?", (adm_s,)).fetchall()
    assert (world["o_shared"], world["other"], "part") in [tuple(r) for r in
                                                           rows]


def test_an_index_left_behind_is_caught_up(world):
    """A writer that did not keep the index (an older release): the impact
    read counts what it left after the mark without writing, the deletion
    catches the index up, and the file another conversation now names is
    kept."""
    store = world["corpus"]._store
    conn = store._conn
    _, adm_x, dig_x = world["files"]["x"]
    store._refs = False
    try:
        p = world["cv"].say(world["other"], world["me"],
                            [{"type": "file", "ref": adm_x}])
    finally:
        store._refs = True
    assert not conn.execute("SELECT 1 FROM ref_index WHERE src = ?",
                            (p,)).fetchone()
    trash(world)
    imp, got = delete(world)
    assert SEEDS["file"] + "-x.txt" in {f["label"] for f in imp["files_kept"]}
    assert held.path(world["root"], dig_x).exists()
    assert conn.execute("SELECT 1 FROM ref_index WHERE src = ?",
                        (p,)).fetchone()


# -- 5. export / import ------------------------------------------------------------

def test_export_refuses_a_deleted_conversation_and_carries_erased_rows(
        world, tmp_path):
    import zipfile
    from mentis.exchange import ExchangeRefused
    from mentis.exchange.apply import check_erased
    from mentis.exchange.export import export
    trash(world)
    delete(world)
    with pytest.raises(ExchangeRefused):
        export(world["root"], out=str(tmp_path / "gone.zip"),
               conversation=world["c"])
    with pytest.raises(ExchangeRefused):
        export(world["root"], out=str(tmp_path / "gone-post.zip"),
               turn=world["posts"][0])
    # the other conversation still exports; what it carries of the deleted
    # one is erased rows, attested, and none of the deleted words
    got = export(world["root"], out=str(tmp_path / "other.zip"),
                 conversation=world["other"])
    with zipfile.ZipFile(got["path"]) as z:
        blob = b"".join(z.read(n) for n in z.namelist())
        manifest = json.loads(z.read("MANIFEST.json"))
        rows = {}
        for n in z.namelist():
            if n.endswith(".jsonl") or n.endswith(".json"):
                pass
    assert not [s for s in SEEDS.values() if s.encode() in blob]
    att = manifest["erasures"]
    entries = []
    with zipfile.ZipFile(got["path"]) as z:
        for n in z.namelist():
            if n.startswith("entries"):
                for line in z.read(n).decode("utf-8").splitlines():
                    if line.strip():
                        entries.append(json.loads(line))
    erased = [e for e in entries if SE.erased_by(e.get("body"))]
    assert {(a["tbl"], a["row_id"]) for a in att} >= {
        ("entry", e["id"]) for e in erased}
    check_erased(manifest, entries, [])           # attested: accepted
    if erased:
        forged = dict(manifest, erasures=[])
        with pytest.raises(ExchangeRefused):
            check_erased(forged, entries, [])


def test_an_import_never_brings_back_an_id_the_target_erased(world):
    """Present ids are refused by the import's check, erased ones included:
    content cannot come back under an erased id."""
    from mentis.spine import imported
    trash(world)
    delete(world)
    p1 = world["posts"][0]
    here_e, _ = imported._present(world["corpus"]._store, [p1], [])
    assert p1 in here_e


# -- cost --------------------------------------------------------------------------

def test_deleting_a_1000_post_conversation_holds_the_writer_briefly(world):
    """Measured: the deletion's whole write transaction (inventory, purge
    acts, the act, erasure rows, UPDATEs, verification) for 1,000 posts with
    replies and acts. Bound: a few seconds."""
    cv, corpus, me = world["cv"], world["corpus"], world["me"]
    big = cv.open_conversation("big", attributed_to=me)
    prev = None
    t0 = time.perf_counter()
    with corpus.atomic():
        for i in range(1000):
            p = cv.say(big, me, text(f"post {i} " + "words " * 30),
                       replies_to=prev if i % 3 else None)
            cv.record_act(actor=me, act="turn-said", conversation=big,
                          turn=p, about=[p], detail={"said": "x" * 200})
            prev = p
    built = time.perf_counter() - t0
    trash(world, big)
    imp, got = delete(world, big)
    assert imp["counts"]["posts"] + imp["counts"]["replies"] == 1000
    print(f"\n1000-post deletion: built {built:.1f}s, writer held "
          f"{got['writer_held_ms']:.0f} ms, total {got['total_ms']:.0f} ms, "
          f"{got['erased_rows']} rows erased")
    assert got["writer_held_ms"] < 5000, got["writer_held_ms"]
    assert corpus.verify_chain()["intact"]
