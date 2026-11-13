"""Attested erasure and the reference index (schema 0002-erasure).

THE ONE SANCTIONED EXCEPTION TO AN APPEND-ONLY RECORD (owner decision
2026-11-13; contract `conv-mgmt/erasure-design.md`). A permanent deletion may
replace the CONTENT columns of named rows -- `entry.body`,
`operational.detail` (with `operational.because` set to NULL) and
`delivery.material` -- with a fixed marker naming the deletion act:

    {"erased":"<deletion act id>"}

and nothing else. Every other column, the row's stored `prev_hash` and `hash`
included, stays exactly as it was, so the chain still links. What makes the
change acceptable to `Store.verify_chain` is an `erasure` row per erased row:

    (deletion, tbl, row_id, row_hash = the row's stored hash,
     residual = sha256 of `Store._canonical(tbl, CHAINED[tbl], row after)`)

and the deletion act's own chained detail, which carries the count and a
digest over those rows (`digest`). The triggers (migration 0002) let exactly
that UPDATE through and nothing else; DELETE stays refused everywhere.

THE REFERENCE INDEX (`ref_index`) is derived: rebuildable from the record at
any time (`rebuild`), never chained, maintained in the same transaction as
each append (`index_entries`, `index_acts`), and caught up from its mark
(`catch_up`) wherever a writer that did not keep it -- or a crash -- left it
behind. It answers "what refers to this" without scanning every body:

    src               the referring entry (a link's `from`), or act id
    src_conversation  the conversation the src is homed in (its
                      `in-conversation` link; an act's own `conversation`)
    target            the id referred to
    kind              `part` (a post part's `ref`), `body` (any id in a body),
                      `link:<relation>` (a link's `to`), `act:<act>` (an act's
                      `about`)
"""

from __future__ import annotations

import hashlib
import json
import re

#: the act that attests a permanent deletion
DELETION_ACT = "conversation-deleted"
#: per table, the column that carries the marker and the others erased with it
MARKED = {"entry": "body", "operational": "detail", "delivery": "material"}
NULLED = {"operational": ("because",)}
TABLES = ("entry", "operational", "delivery")

#: an id somebody may refer to: entries, admissions, acts, deliveries
_ID = re.compile(r"\b(?:ent|adm|opr|dlv|exe)-[0-9a-f]{8,32}\b")
_IN_CONVERSATION = "in-conversation"


def marker(deletion: str) -> str:
    """The exact text an erased content column holds (no spaces)."""
    return '{"erased":"' + deletion + '"}'


#: IN-PROCESS CACHES THAT HOLD ROW CONTENT BY ID AS IF IMMUTABLE, told after
#: a permanent deletion commits which entry ids were erased. Each is a
#: callable(ids). Registered by the cache's own module (`fluid.objects`).
ON_ERASED: list = []


def erased(ids) -> None:
    for fn in list(ON_ERASED):
        try:
            fn(ids)
        except Exception:                                   # noqa: BLE001
            pass


def erased_by(value) -> str | None:
    """The deletion act an erased value names, or None. Takes a decoded
    body/detail/material (a dict) or its stored text."""
    if isinstance(value, str):
        if not value.startswith('{"erased":'):
            return None
        try:
            value = json.loads(value)
        except ValueError:
            return None
    # the stored marker (one key), or the shape a reader is handed for it
    # (`store._erased_body`: its Kind's empty fields beside `erased`)
    if isinstance(value, dict) and isinstance(value.get("erased"), str):
        return value["erased"]
    return None


def residual(table: str, row: dict) -> str:
    """sha256 hex of the row's canonical bytes as it stands (after erasure)."""
    from mentis.spine.store import Store
    return hashlib.sha256(Store._canonical(
        table, Store.CHAINED[table], row).encode("utf-8")).hexdigest()


def line(tbl: str, row_id: str, row_hash: str, resid: str) -> str:
    return "\x1e".join((tbl, row_id, row_hash, resid))


def digest(rows) -> str:
    """The digest an act carries over its erasure rows: sha256 hex of the
    lines `tbl RS row_id RS row_hash RS residual`, sorted by (tbl, row_id),
    joined by a newline. `rows` are (tbl, row_id, row_hash, residual)."""
    lines = [line(*r) for r in sorted(rows, key=lambda r: (r[0], r[1]))]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# -- the reference index ---------------------------------------------------------

def _ids_in(value, out: set):
    if isinstance(value, str):
        out.update(_ID.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            _ids_in(v, out)
    elif isinstance(value, list):
        for v in value:
            _ids_in(v, out)


def entry_refs(eid: str, body, link_from=None, link_to=None,
               relation=None) -> list:
    """(src, target, kind) for one entry. `body` decoded."""
    out = []
    # AN ERASED BODY REFERS TO NOTHING (its marker names only its deletion)
    erased = erased_by(body) is not None
    if relation is not None:
        if link_from and link_to:
            out.append((link_from, link_to, f"link:{relation}"))
        if erased:
            return out
        found: set = set()
        _ids_in(body, found)
        # a link's body refers from the LINK, so what its words name goes
        # with its words when they are erased
        for t in sorted(found - {link_from, link_to}):
            out.append((eid, t, "body"))
        return out
    if erased:
        return out
    parts = set()
    if isinstance(body, dict) and isinstance(body.get("parts"), list):
        for p in body["parts"]:
            if isinstance(p, dict) and isinstance(p.get("ref"), str):
                parts.add(p["ref"])
    found = set()
    _ids_in(body, found)
    for t in sorted(parts):
        out.append((eid, t, "part"))
    for t in sorted(found - parts - {eid}):
        out.append((eid, t, "body"))
    return out


def act_refs(aid: str, act: str, about) -> list:
    return [(aid, t, f"act:{act}") for t in dict.fromkeys(about or ())
            if isinstance(t, str) and t]


def _decode(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def ref_rows_all(query) -> tuple:
    """Every ref_index row the record implies, and the marks (max entry seq,
    max operational seq) they cover. `query(sql, args)` reads only.
    THE REBUILD, and what migration 0002 fills the table with."""
    home = {}
    for frm, to in query("SELECT link_from, link_to FROM entry "
                         "WHERE link_relation = ? ORDER BY seq",
                         (_IN_CONVERSATION,)):
        home.setdefault(frm, to)
    rows = set()
    eseq = 0
    for seq, eid, family, body, lf, lt, rel in query(
            "SELECT seq, id, family, body, link_from, link_to, link_relation "
            "FROM entry ORDER BY seq"):
        eseq = seq
        if family == "definition":
            continue
        for src, t, kind in entry_refs(eid, _decode(body), lf, lt, rel):
            rows.add((src, home.get(src), t, kind))
    oseq = 0
    for seq, aid, act, conv, about in query(
            "SELECT seq, id, act, conversation, about FROM operational "
            "ORDER BY seq"):
        oseq = seq
        for src, t, kind in act_refs(aid, act, _decode(about) or []):
            rows.add((src, conv, t, kind))
    return sorted(rows, key=lambda r: (r[0], r[2], r[3])), (eseq, oseq)


def has_index(conn) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ref_index'"
    ).fetchone())


_INSERT = ("INSERT OR IGNORE INTO ref_index (src, src_conversation, target, "
           "kind) VALUES (?, ?, ?, ?)")


def _home_of(conn, src):
    r = conn.execute("SELECT link_to FROM entry WHERE link_from = ? AND "
                     "link_relation = ? ORDER BY seq LIMIT 1",
                     (src, _IN_CONVERSATION)).fetchone()
    return r[0] if r else None


def index_entries(conn, flats, first_seq: int) -> None:
    """Inside the append's transaction: the rows of these appended entries
    (flattened, in order, the first at `first_seq`), and the mark moved on
    only if it stood just before them (otherwise `catch_up` covers them)."""
    rows = []
    homes = []
    for f in flats:
        if f.get("family") == "definition":
            continue
        rel = f.get("link_relation")
        body = _decode(f.get("body"))
        for src, t, kind in entry_refs(f["id"], body, f.get("link_from"),
                                       f.get("link_to"), rel):
            rows.append((src, t, kind))
        if rel == _IN_CONVERSATION and f.get("link_from"):
            homes.append((f["link_to"], f["link_from"]))
    for src, t, kind in rows:
        conn.execute(_INSERT, (src, _home_of(conn, src), t, kind))
    for to, frm in homes:
        conn.execute("UPDATE ref_index SET src_conversation = ? "
                     "WHERE src = ? AND src_conversation IS NULL", (to, frm))
    last = first_seq + len(flats) - 1
    moved = conn.execute(
        "UPDATE ref_index_mark SET entry_seq = ? WHERE entry_seq = ?",
        (last, first_seq - 1)).rowcount
    if not moved:
        catch_up(conn)          # behind (another writer, a crash): once


def index_act(conn, row: dict, seq: int) -> None:
    for src, t, kind in act_refs(row["id"], row["act"],
                                 _decode(row["about"]) or []):
        conn.execute(_INSERT, (src, row.get("conversation"), t, kind))
    moved = conn.execute(
        "UPDATE ref_index_mark SET op_seq = ? WHERE op_seq = ?",
        (seq, seq - 1)).rowcount
    if not moved:
        catch_up(conn)          # behind (another writer, a crash): once


def catch_up(conn) -> dict:
    """Index every row after the mark (idempotent: the index is UNIQUE), and
    move the mark to the end. Inside a write transaction."""
    mark = conn.execute(
        "SELECT entry_seq, op_seq FROM ref_index_mark WHERE one = 1").fetchone()
    eseq, oseq = (mark[0], mark[1]) if mark else (0, 0)
    n = 0
    top_e, top_o = eseq, oseq
    for seq, eid, family, body, lf, lt, rel in conn.execute(
            "SELECT seq, id, family, body, link_from, link_to, link_relation "
            "FROM entry WHERE seq > ? ORDER BY seq", (eseq,)).fetchall():
        top_e = seq
        if family == "definition":
            continue
        for src, t, kind in entry_refs(eid, _decode(body), lf, lt, rel):
            conn.execute(_INSERT, (src, _home_of(conn, src), t, kind))
            n += 1
        if rel == _IN_CONVERSATION and lf:
            conn.execute("UPDATE ref_index SET src_conversation = ? "
                         "WHERE src = ? AND src_conversation IS NULL", (lt, lf))
    for seq, aid, act, conv, about in conn.execute(
            "SELECT seq, id, act, conversation, about FROM operational "
            "WHERE seq > ? ORDER BY seq", (oseq,)).fetchall():
        top_o = seq
        for src, t, kind in act_refs(aid, act, _decode(about) or []):
            conn.execute(_INSERT, (src, conv, t, kind))
            n += 1
    if mark:
        conn.execute("UPDATE ref_index_mark SET entry_seq = ?, op_seq = ? "
                     "WHERE one = 1", (top_e, top_o))
    else:
        conn.execute("INSERT INTO ref_index_mark (one, entry_seq, op_seq) "
                     "VALUES (1, ?, ?)", (top_e, top_o))
    return {"rows": n, "entry_seq": top_e, "op_seq": top_o}


def lagging(query) -> list:
    """The ref rows of every record row after the index's mark, computed and
    NOT written: what a read-only question (the deletion impact) adds to the
    index where a writer that does not keep it left it behind."""
    mark = query("SELECT entry_seq, op_seq FROM ref_index_mark WHERE one = 1")
    eseq, oseq = (mark[0][0], mark[0][1]) if mark else (0, 0)
    out = []
    for seq, eid, family, body, lf, lt, rel in query(
            "SELECT seq, id, family, body, link_from, link_to, link_relation "
            "FROM entry WHERE seq > ? ORDER BY seq", (eseq,)):
        if family == "definition":
            continue
        for src, t, kind in entry_refs(eid, _decode(body), lf, lt, rel):
            out.append((src, None, t, kind))
    for seq, aid, act, conv, about in query(
            "SELECT seq, id, act, conversation, about FROM operational "
            "WHERE seq > ? ORDER BY seq", (oseq,)):
        for src, t, kind in act_refs(aid, act, _decode(about) or []):
            out.append((src, conv, t, kind))
    return out


def rebuild(conn) -> dict:
    """Drop every row and make the index again from the record. Inside a
    write transaction. The index is derived: nothing is lost."""
    rows, (eseq, oseq) = ref_rows_all(
        lambda sql, args=(): conn.execute(sql, args).fetchall())
    conn.execute("DELETE FROM ref_index")
    conn.executemany(_INSERT, rows)
    conn.execute("DELETE FROM ref_index_mark")
    conn.execute("INSERT INTO ref_index_mark (one, entry_seq, op_seq) "
                 "VALUES (1, ?, ?)", (eseq, oseq))
    return {"rows": len(rows), "entry_seq": eseq, "op_seq": oseq}


def index_rows(conn) -> list:
    return [tuple(r) for r in conn.execute(
        "SELECT src, src_conversation, target, kind FROM ref_index "
        "ORDER BY src, target, kind")]


# -- erasing ---------------------------------------------------------------------

def plan_rows(conn, deletion: str, targets) -> list:
    """For each (tbl, row_id): (tbl, row_id, row_hash, residual) -- what the
    erasure row will hold. Reads the rows as they stand; nothing written."""
    from mentis.spine.store import Store
    out = []
    mark = marker(deletion)
    for tbl, rid in targets:
        cols = Store.CHAINED[tbl]
        r = conn.execute(f"SELECT {','.join(cols)}, hash FROM {tbl} "
                         f"WHERE id = ?", (rid,)).fetchone()
        if r is None:
            raise LookupError(f"no {tbl} row {rid}")
        row = dict(zip(cols, r[:len(cols)]))
        row[MARKED[tbl]] = mark
        for c in NULLED.get(tbl, ()):
            row[c] = None
        out.append((tbl, rid, r[len(cols)] or "", residual(tbl, row)))
    return out


def write_rows(conn, deletion: str, planned) -> int:
    """Inside the deletion's transaction, AFTER its act is appended: the
    erasure rows, then the UPDATEs the triggers allow. Returns rows erased."""
    conn.executemany(
        "INSERT INTO erasure (deletion, tbl, row_id, row_hash, residual) "
        "VALUES (?, ?, ?, ?, ?)",
        [(deletion, t, rid, h, res) for t, rid, h, res in planned])
    mark = marker(deletion)
    n = 0
    for tbl in TABLES:
        ids = [rid for t, rid, _, _ in planned if t == tbl]
        if not ids:
            continue
        sets = [f"{MARKED[tbl]} = ?"] + [f"{c} = NULL"
                                          for c in NULLED.get(tbl, ())]
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            cur = conn.execute(
                f"UPDATE {tbl} SET {', '.join(sets)} WHERE id IN "
                f"(SELECT value FROM json_each(?))", (mark, json.dumps(chunk)))
            n += cur.rowcount
    if n != len(planned):
        raise RuntimeError(f"erasure updated {n} rows, {len(planned)} planned")
    # the reference index follows: what an erased body named it names no more
    if has_index(conn):
        gone = [rid for t, rid, _, _ in planned if t == "entry"]
        for i in range(0, len(gone), 500):
            conn.execute("DELETE FROM ref_index WHERE kind IN ('part', 'body') "
                         "AND src IN (SELECT value FROM json_each(?))",
                         (json.dumps(gone[i:i + 500]),))
    return n


# -- verifying -------------------------------------------------------------------

def load(conn) -> dict | None:
    """{(tbl, row_id): (deletion, row_hash, residual)} or None without the
    table (a Brain before 0002)."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name='erasure'").fetchone():
        return None
    return {(t, r): (d, h, res) for d, t, r, h, res in conn.execute(
        "SELECT deletion, tbl, row_id, row_hash, residual FROM erasure "
        "ORDER BY seq")}


def holds_marker(table: str, row: dict, deletion: str) -> bool:
    if row.get(MARKED[table]) != marker(deletion):
        return False
    return all(row.get(c) is None for c in NULLED.get(table, ()))


def check_acts(conn, erasures: dict) -> dict:
    """Per deletion act: the act exists, its erasure count and digest equal
    its detail; every erasure row names a row that exists. Returns
    {"acts": a, "rows": r, "broken": None | {...}} (pending is the walk's)."""
    by_act: dict = {}
    for (tbl, rid), (dele, h, res) in erasures.items():
        by_act.setdefault(dele, []).append((tbl, rid, h, res))
    broken = None
    acts = {r[0]: r[1] for r in conn.execute(
        "SELECT id, detail FROM operational WHERE act = ?", (DELETION_ACT,))}
    for dele in sorted(by_act):
        rows = by_act[dele]
        if dele not in acts:
            broken = broken or {"deletion": dele, "why": (
                "erasure rows name a deletion act that is not in the record")}
            continue
        d = _decode(acts[dele]) or {}
        e = (d.get("erasure") or {}) if isinstance(d, dict) else {}
        if e.get("rows") != len(rows) or e.get("digest") != digest(rows):
            broken = broken or {"deletion": dele, "why": (
                "the erasure rows do not match the count and digest their "
                "deletion act records")}
    for dele in sorted(set(acts) - set(by_act)):
        d = _decode(acts[dele]) or {}
        e = (d.get("erasure") or {}) if isinstance(d, dict) else {}
        if e.get("rows"):
            broken = broken or {"deletion": dele, "why": (
                "the deletion act records erasure rows the record does not "
                "hold")}
    for (tbl, rid) in sorted(erasures):
        if not conn.execute(f"SELECT 1 FROM {tbl} WHERE id = ?",
                            (rid,)).fetchone():
            broken = broken or {"table": tbl, "id": rid, "why": (
                "an erasure row names a row that does not exist")}
    return {"acts": len(acts), "rows": len(erasures), "broken": broken}
