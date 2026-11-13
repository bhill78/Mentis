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

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import threading

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
    """Every id named anywhere in a decoded body: values AND object keys
    (an inventory keyed by Admission id; review round 2, finding 4)."""
    if isinstance(value, str):
        out.update(_ID.findall(value))
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str):
                out.update(_ID.findall(k))
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


def act_refs(aid: str, act: str, about, detail=None, because=None) -> list:
    """An act's references: its `about` ids (`act:<act>`), and every id its
    detail or its `because` names (`detail:<act>`) -- unless the detail is
    erased (its `because` then is NULL). Every text column of every act
    (review round 3, finding 2)."""
    out, seen = [], {aid}
    for t in dict.fromkeys(about or ()):
        if isinstance(t, str) and t and t not in seen:
            seen.add(t)
            out.append((aid, t, f"act:{act}"))
    found: set = set()
    if detail is not None and erased_by(detail) is None:
        _ids_in(detail, found)
    if isinstance(because, str):
        _ids_in(because, found)
    for t in sorted(found - seen):
        out.append((aid, t, f"detail:{act}"))
    return out


def delivery_refs(did: str, material) -> list:
    """What a run was handed names (`material`), unless erased."""
    if material is None or erased_by(material) is not None:
        return []
    found: set = set()
    _ids_in(material, found)
    return [(did, t, "material") for t in sorted(found - {did})]


def _decode(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


_ENTRY_Q = ("SELECT seq, id, family, body, link_from, link_to, link_relation "
            "FROM entry WHERE seq > ? ORDER BY seq")
_ACT_Q = ("SELECT seq, id, act, conversation, about, detail, because FROM "
          "operational WHERE seq > ? ORDER BY seq")
_DLV_Q = ("SELECT seq, id, conversation, material FROM delivery "
          "WHERE seq > ? ORDER BY seq")


def _rows_after(query, marks, home_of) -> tuple:
    """(rows, new marks) for every record row after `marks` (entry, op,
    delivery positions). `home_of(src)` gives a src's home conversation."""
    eseq, oseq, dseq = marks
    rows = []
    for seq, eid, family, body, lf, lt, rel in query(_ENTRY_Q, (eseq,)):
        eseq = seq
        if family == "definition":
            continue
        for src, t, kind in entry_refs(eid, _decode(body), lf, lt, rel):
            rows.append((src, home_of(src), t, kind))
    for seq, aid, act, conv, about, detail, because in query(_ACT_Q,
                                                             (oseq,)):
        oseq = seq
        for src, t, kind in act_refs(aid, act, _decode(about) or [],
                                     _decode(detail), because):
            rows.append((src, conv, t, kind))
    for seq, did, conv, material in query(_DLV_Q, (dseq,)):
        dseq = seq
        for src, t, kind in delivery_refs(did, _decode(material)):
            rows.append((src, conv, t, kind))
    return rows, (eseq, oseq, dseq)


def ref_rows_all(query) -> tuple:
    """Every ref_index row the record implies, and the marks (max entry,
    operational and delivery seq) they cover. `query(sql, args)` reads only.
    THE REBUILD, and what migration 0002 fills the table with."""
    home = {}
    for frm, to in query("SELECT link_from, link_to FROM entry "
                         "WHERE link_relation = ? ORDER BY seq",
                         (_IN_CONVERSATION,)):
        home.setdefault(frm, to)
    rows, marks = _rows_after(query, (0, 0, 0), home.get)
    # a src homed by a link written later: as the maintained index has it
    rows = {(s, home.get(s) if k in ("part", "body") or k.startswith("link:")
             else c, t, k) for s, c, t, k in rows}
    return sorted(rows, key=lambda r: (r[0], r[2], r[3])), marks


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


def _marks(conn):
    m = conn.execute("SELECT entry_seq, op_seq, delivery_seq FROM "
                     "ref_index_mark WHERE one = 1").fetchone()
    return (m[0], m[1], m[2]) if m else None


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
                     "WHERE src = ? AND src_conversation IS NULL AND "
                     "(kind IN ('part', 'body') OR kind LIKE 'link:%')",
                     (to, frm))
    last = first_seq + len(flats) - 1
    moved = conn.execute(
        "UPDATE ref_index_mark SET entry_seq = ? WHERE entry_seq = ?",
        (last, first_seq - 1)).rowcount
    if not moved:
        catch_up(conn)          # behind (another writer, a crash): once


def index_act(conn, row: dict, seq: int) -> None:
    for src, t, kind in act_refs(row["id"], row["act"],
                                 _decode(row["about"]) or [],
                                 _decode(row.get("detail")),
                                 row.get("because")):
        conn.execute(_INSERT, (src, row.get("conversation"), t, kind))
    moved = conn.execute(
        "UPDATE ref_index_mark SET op_seq = ? WHERE op_seq = ?",
        (seq, seq - 1)).rowcount
    if not moved:
        catch_up(conn)          # behind (another writer, a crash): once


def index_delivery(conn, row: dict, seq: int) -> None:
    for src, t, kind in delivery_refs(row["id"], _decode(row["material"])):
        conn.execute(_INSERT, (src, row.get("conversation"), t, kind))
    moved = conn.execute(
        "UPDATE ref_index_mark SET delivery_seq = ? WHERE delivery_seq = ?",
        (seq, seq - 1)).rowcount
    if not moved:
        catch_up(conn)


def catch_up(conn) -> dict:
    """Index every row after the mark (idempotent: the index is UNIQUE), and
    move the mark to the end. Inside a write transaction."""
    marks = _marks(conn)
    rows, top = _rows_after(
        lambda sql, args=(): conn.execute(sql, args).fetchall(),
        marks or (0, 0, 0), lambda s: _home_of(conn, s))
    conn.executemany(_INSERT, rows)
    # homes written in this stretch reach the rows indexed before them
    for lf, lt in conn.execute(
            "SELECT link_from, link_to FROM entry WHERE link_relation = ? "
            "AND seq > ?", (_IN_CONVERSATION, (marks or (0,))[0])).fetchall():
        conn.execute("UPDATE ref_index SET src_conversation = ? "
                     "WHERE src = ? AND src_conversation IS NULL AND "
                     "(kind IN ('part', 'body') OR kind LIKE 'link:%')",
                     (lt, lf))
    if marks:
        conn.execute("UPDATE ref_index_mark SET entry_seq = ?, op_seq = ?, "
                     "delivery_seq = ? WHERE one = 1", top)
    else:
        conn.execute("INSERT INTO ref_index_mark (one, entry_seq, op_seq, "
                     "delivery_seq) VALUES (1, ?, ?, ?)", top)
    return {"rows": len(rows), "entry_seq": top[0], "op_seq": top[1],
            "delivery_seq": top[2]}


def lagging(query) -> list:
    """The ref rows of every record row after the index's mark, computed and
    NOT written: what a read-only question (the deletion impact) adds to the
    index where a writer that does not keep it left it behind."""
    m = query("SELECT entry_seq, op_seq, delivery_seq FROM ref_index_mark "
              "WHERE one = 1")
    marks = (m[0][0], m[0][1], m[0][2]) if m else (0, 0, 0)
    rows, _ = _rows_after(query, marks, lambda s: None)
    return rows


def rebuild(conn) -> dict:
    """Drop every row and make the index again from the record. Inside a
    write transaction. The index is derived: nothing is lost."""
    rows, marks = ref_rows_all(
        lambda sql, args=(): conn.execute(sql, args).fetchall())
    conn.execute("DELETE FROM ref_index")
    conn.executemany(_INSERT, rows)
    conn.execute("DELETE FROM ref_index_mark")
    conn.execute("INSERT INTO ref_index_mark (one, entry_seq, op_seq, "
                 "delivery_seq) VALUES (1, ?, ?, ?)", marks)
    return {"rows": len(rows), "entry_seq": marks[0], "op_seq": marks[1],
            "delivery_seq": marks[2]}


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
    # the reference index follows: what an erased body, detail or material
    # named it names no more (structure -- links, `about` -- stays)
    if has_index(conn):
        for tbl, kinds in (("entry", "kind IN ('part', 'body')"),
                           ("operational", "kind LIKE 'detail:%'"),
                           ("delivery", "kind = 'material'")):
            gone = [rid for t, rid, _, _ in planned if t == tbl]
            for i in range(0, len(gone), 500):
                conn.execute(f"DELETE FROM ref_index WHERE {kinds} AND src IN "
                             f"(SELECT value FROM json_each(?))",
                             (json.dumps(gone[i:i + 500]),))
    return n


# -- the deletion ledger (owner decision 2026-11-13, amendment D) -----------------
#
# OUTSIDE THE BRAIN DIRECTORY, so restoring a Brain backup does not roll it
# back: `<brain dir>.erasures.jsonl`, append-only, one line per permanent
# deletion -- corpus id, conversation id, deletion act id, erasure digest,
# row count, when, by whom. No content. A Brain that does not hold a listed
# deletion is not served writable until the owner re-applies it.

LEDGER_SUFFIX = ".erasures.jsonl"
REAPPLIED_ACT = "conversation-erasure-reapplied"
_UNCHECKED = threading.local()


def ledger_path(root) -> str:
    return os.path.normpath(os.path.abspath(str(root))) + LEDGER_SUFFIX


def _write_atomic(path, data: bytes) -> None:
    """The whole file, written beside, fsynced, then os.replace'd over the
    old one and the directory fsynced where the platform allows: a reader
    sees the old file or the new one, never a torn one (review round 3,
    finding 4)."""
    tmp = path + ".partial"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    _fsync_dir(os.path.dirname(path) or ".")


def ledger_snapshot(root) -> bytes | None:
    """The ledger's bytes as they are now (None: no ledger yet)."""
    try:
        with open(ledger_path(root), "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def ledger_restore(root, previous: bytes | None) -> None:
    """Put the ledger back to `previous` (`ledger_snapshot`), atomically."""
    path = ledger_path(root)
    if previous is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        _fsync_dir(os.path.dirname(path) or ".")
        return
    _write_atomic(path, previous)


def ledger_append(root, entry: dict) -> str:
    """One more line: the whole ledger rewritten atomically with it."""
    path = ledger_path(root)
    line = (json.dumps(entry, sort_keys=True, ensure_ascii=False)
            + "\n").encode("utf-8")
    old = ledger_snapshot(root) or b""
    if old and not old.endswith(b"\n"):
        old += b"\n"
    _write_atomic(path, old + line)
    return path


def erase_set_dir(root) -> str:
    """Beside the ledger: one fsynced file per deletion, its exact erase set
    (ids only) -- `<brain dir>.erasures/<deletion act id>.json`."""
    return os.path.normpath(os.path.abspath(str(root))) + ".erasures"


def _fsync_dir(path):
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return                          # Windows: directories are not opened
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def erase_set_bytes(deletion, conversation, corpus_id, rows, files) -> bytes:
    """The sidecar's exact bytes: canonical JSON, ids only."""
    return json.dumps({
        "deletion": deletion, "conversation": conversation,
        "corpus_id": corpus_id,
        "rows": sorted([list(r) for r in rows]),
        "files": sorted([{"admission": f["admission"], "digest": f["digest"]}
                         for f in files], key=lambda f: f["admission"])},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def ledger_record(root, entry: dict, rows, files, *, append=True) -> str:
    """The deletion's erase-set sidecar, then its ledger line naming the
    sidecar and its digest -- each written and fsynced. Raises OSError, with
    nothing claimed, when either cannot be written."""
    d = erase_set_dir(root)
    os.makedirs(d, exist_ok=True)
    data = erase_set_bytes(entry["deletion"], entry["conversation"],
                           entry.get("corpus_id"), rows, files)
    name = entry["deletion"] + ".json"
    tmp = os.path.join(d, name + ".partial")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, os.path.join(d, name))
    _fsync_dir(d)
    line = {**entry, "erase_set": name,
            "erase_set_digest": hashlib.sha256(data).hexdigest()}
    if append:
        ledger_append(root, line)
    return name


def read_erase_set(root, entry) -> dict:
    """A ledger line's sidecar, verified against the digest the line holds.
    Raises ValueError when absent from the line, OSError when unreadable."""
    name = entry.get("erase_set")
    if not name:
        raise ValueError("this ledger line names no erase set")
    with open(os.path.join(erase_set_dir(root), name), "rb") as fh:
        data = fh.read()
    if hashlib.sha256(data).hexdigest() != entry.get("erase_set_digest"):
        raise ValueError("the erase set does not match its ledger line")
    got = json.loads(data)
    got["rows"] = [tuple(r) for r in got.get("rows") or []]
    return got


def ledger_claims(root, corpus_id) -> tuple:
    """What the ledger says this Brain deleted: ({(table, row id)},
    {conversation id}) over every listed deletion's erase set (an import
    must not bring any of it back; review round 2, finding 3). A line
    whose sidecar cannot be read claims its conversation still."""
    rows, convs = set(), set()
    for e in ledger_entries(root, corpus_id) + sidecar_intents(root,
                                                               corpus_id):
        if "unreadable" in e:
            raise LedgerDamaged(
                f"a line of {ledger_path(root)} is damaged "
                f"({e['unreadable'][:60]!r}); nothing is imported until "
                f"`python -m "
                f"mentis.conversation.erasure check \"{root}\" --repair`")
        if e.get("conversation"):
            convs.add(e["conversation"])
        try:
            rows |= set(read_erase_set(root, e)["rows"])
        except (OSError, ValueError) as exc:
            raise LedgerDamaged(
                f"the erase set of deletion {e.get('deletion')} cannot be "
                f"read ({exc}); nothing is imported until `python -m "
                f"mentis.conversation.erasure check \"{root}\" --repair` "
                f"rebuilds it") from exc
    return rows, convs


class LedgerDamaged(RuntimeError):
    """The deletion ledger or an erase set cannot be read: everything that
    depends on it refuses (import), and the owner repairs it."""


def sidecar_intents(root, corpus_id=None, lines=None) -> list:
    """Erase sets with no readable ledger line naming them -- a deletion
    whose line was lost or torn: each is the deletion's intent, as a ledger
    line would say it (`from_sidecar`), so the check refuses the Brain and
    reapply completes it."""
    d = erase_set_dir(root)
    try:
        names = sorted(n for n in os.listdir(d) if n.endswith(".json"))
    except OSError:
        return []
    lines = ledger_entries(root, corpus_id) if lines is None else lines
    named = {e.get("erase_set") for e in lines if "unreadable" not in e}
    out = []
    for n in names:
        if n in named:
            continue
        try:
            with open(os.path.join(d, n), "rb") as fh:
                data = fh.read()
            got = json.loads(data)
        except (OSError, ValueError):
            out.append({"unreadable": f"erase set {n}"})
            continue
        if corpus_id is not None and got.get("corpus_id") != corpus_id:
            continue
        out.append({"corpus_id": got.get("corpus_id"),
                    "conversation": got.get("conversation"),
                    "deletion": got.get("deletion"), "digest": None,
                    "rows": None, "erase_set": n,
                    "erase_set_digest": hashlib.sha256(data).hexdigest(),
                    "from_sidecar": True})
    return out


def import_refusal(conn, root, entries, acts, attested=()) -> None:
    """THE IMPORT DOOR'S LEDGER CHECK (`Store.append_imported`): refuse every
    incoming row the deletion ledger says was permanently deleted here -- an
    id in a listed erase set, a listed conversation or anything naming it --
    unless it arrives erased and attested; and refuse everything when the
    ledger or an erase set cannot be read (review round 3, finding 3)."""
    row = conn.execute("SELECT corpus_id FROM corpus").fetchone()
    if not os.path.exists(ledger_path(root)) and not os.path.isdir(
            erase_set_dir(root)):
        return
    rows, convs = ledger_claims(root, row[0] if row else None)
    if not rows and not convs:
        return
    ok = set(attested or ())
    bad = []
    for e in entries:
        link = e.get("link") or {}
        content = e.get("body")
        if ("entry", e["id"]) in ok and erased_by(content):
            continue
        if ("entry", e["id"]) in rows or e["id"] in convs \
                or link.get("to") in convs or link.get("from") in convs:
            bad.append(e["id"])
    for a in acts:
        if ("operational", a["id"]) in ok and erased_by(a.get("detail")):
            continue
        if ("operational", a["id"]) in rows \
                or a.get("conversation") in convs \
                or set(a.get("about") or ()) & convs:
            bad.append(a["id"])
    if bad:
        raise LedgerDamaged(
            f"{len(bad)} row(s) of this import were permanently deleted here "
            f"(the deletion ledger {ledger_path(root)} lists them): "
            f"{', '.join(bad[:8])}{' ...' if len(bad) > 8 else ''}; nothing "
            f"was imported")


def ledger_entries(root, corpus_id=None) -> list:
    """The ledger's lines (this corpus's only, when `corpus_id` is given). An
    unreadable line is returned as {"unreadable": text}: never skipped."""
    path = ledger_path(root)
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        return []
    out = []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            out.append({"unreadable": raw[:200]})
            continue
        if corpus_id is None or d.get("corpus_id") == corpus_id:
            out.append(d)
    return out


@contextlib.contextmanager
def ledger_unchecked():
    """The owner's re-apply opens the Brain writable although the ledger
    check fails: that is what it is for. This thread only."""
    _UNCHECKED.on = True
    try:
        yield
    finally:
        _UNCHECKED.on = False


def _deletion_holds(conn, deletion, rows, dig) -> bool:
    act = conn.execute("SELECT detail FROM operational WHERE id = ? AND act = ?",
                       (deletion, DELETION_ACT)).fetchone()
    if act is None:
        return False
    got = [tuple(r) for r in conn.execute(
        "SELECT tbl, row_id, row_hash, residual FROM erasure WHERE "
        "deletion = ?", (deletion,))]
    if rows is not None and len(got) != rows:
        return False
    if dig is not None and digest(got) != dig:
        return False
    for tbl, rid, _, _ in got:          # each named row holds its marker
        col = MARKED[tbl]
        r = conn.execute(f"SELECT {col} FROM {tbl} WHERE id = ?",
                         (rid,)).fetchone()
        if r is None or r[0] != marker(deletion):
            return False
    return True


def ledger_check(conn, root) -> list:
    """The ledger's deletions this Brain does NOT hold: each listed deletion
    must be in the record -- its act, its erasure rows matching the ledger's
    count and digest, every row erased -- or re-applied here (a
    `conversation-erasure-reapplied` act naming it, whose own deletion
    holds), or its conversation must not be in this record at all."""
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "corpus" not in tables or "operational" not in tables:
        return []
    cid = conn.execute("SELECT corpus_id FROM corpus").fetchone()
    cid = cid[0] if cid else None
    lines = ledger_entries(root, cid)
    entries = lines + sidecar_intents(root, cid, lines)
    if not entries:
        return []
    out = []
    for e in entries:
        if "unreadable" in e:
            out.append({**e, "why": "a ledger line or erase set is damaged; "
                                    "`check --repair` rewrites the ledger "
                                    "from the erase sets and the record"})
            continue
        dele, conv = e.get("deletion"), e.get("conversation")
        present = bool(conv) and bool(conn.execute(
            "SELECT 1 FROM entry WHERE id = ?", (conv,)).fetchone())
        if "erasure" not in tables:
            if present:
                out.append({**e, "why": "this Brain predates erasure "
                                        "(schema 0002) and holds it"})
            continue
        if not e.get("from_sidecar"):
            try:
                read_erase_set(root, e)
            except (OSError, ValueError) as exc:
                out.append({**e, "why": f"its erase set cannot be read "
                                        f"({exc}); `check --repair` rebuilds "
                                        f"it from the record"})
                continue
        if _deletion_holds(conn, dele, e.get("rows"), e.get("digest")):
            continue
        redone = False
        for (d,) in conn.execute(
                "SELECT o.detail FROM operational o WHERE o.act = ? AND "
                "EXISTS (SELECT 1 FROM json_each(o.about) a WHERE a.value = ?)",
                (REAPPLIED_ACT, dele)):
            try:
                again = json.loads(d).get("deletion")
            except (ValueError, AttributeError):
                again = None
            if again and _deletion_holds(conn, again, None, None):
                redone = True
                break
        if redone:
            continue
        if not conn.execute("SELECT 1 FROM entry WHERE id = ?",
                            (conv,)).fetchone():
            continue                    # never in this record: nothing to serve
        out.append({**e, "why": "its deletion is not in this Brain"})
    return out


def ledger_repair(conn, root) -> dict:
    """`check --repair`: the ledger REWRITTEN (atomically) from its readable
    lines, the erase sets with no readable line, and the record. A lost or
    damaged erase set whose deletion act is in the record is rebuilt from
    its erasure rows. Damaged lines are dropped and reported -- what they
    said is the erase sets'. Returns {kept, added, dropped, rebuilt}."""
    row = conn.execute("SELECT corpus_id FROM corpus").fetchone()
    cid = row[0] if row else None
    lines = ledger_entries(root)            # every corpus's lines are kept
    keep = [e for e in lines if "unreadable" not in e]
    dropped = [e["unreadable"] for e in lines if "unreadable" in e]
    has_erasure = bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='erasure'"
    ).fetchone())
    rebuilt = []

    def from_record(deletion, conversation):
        if not has_erasure:
            return None
        act = conn.execute("SELECT conversation, detail, at, actor FROM "
                           "operational WHERE id = ? AND act = ?",
                           (deletion, DELETION_ACT)).fetchone()
        if act is None:
            return None
        got = [tuple(r) for r in conn.execute(
            "SELECT tbl, row_id, row_hash, residual FROM erasure WHERE "
            "deletion = ?", (deletion,))]
        files = (_decode(act[1]) or {}).get("files") or []
        return {"corpus_id": cid, "conversation": conversation or act[0],
                "deletion": deletion, "digest": digest(got),
                "rows": len(got), "at": act[2], "by": act[3],
                "at_iso": None}, [(t, r) for t, r, _, _ in got], files
    out_lines = []
    for e in keep:
        try:
            read_erase_set(root, e)
            out_lines.append(e)
            continue
        except (OSError, ValueError):
            pass
        got = from_record(e.get("deletion"), e.get("conversation"))
        if got is None:
            out_lines.append(e)             # nothing to rebuild it from: kept
            continue
        line, rows, files = got
        ledger_record(root, {**line, **{k: e[k] for k in ("at", "at_iso", "by")
                                        if e.get(k) is not None}},
                      rows, files, append=False)
        out_lines.append({**e, "erase_set": e["deletion"] + ".json",
                          "erase_set_digest": hashlib.sha256(erase_set_bytes(
                              e["deletion"], line["conversation"],
                              line["corpus_id"], rows, files)).hexdigest()})
        rebuilt.append(e.get("deletion"))
    added = []
    for e in sidecar_intents(root, None, keep):
        if "unreadable" in e:
            dropped.append(e["unreadable"])
            continue
        got = from_record(e["deletion"], e["conversation"])
        line = {**e}
        line.pop("from_sidecar", None)
        if got is not None:
            line.update(digest=got[0]["digest"], rows=got[0]["rows"],
                        at=got[0]["at"], by=got[0]["by"])
        else:
            line["intent"] = True            # the commit never happened
        out_lines.append(line)
        added.append(e["deletion"])
    data = b"".join((json.dumps(x, sort_keys=True, ensure_ascii=False)
                     + "\n").encode("utf-8") for x in out_lines)
    _write_atomic(ledger_path(root), data)
    return {"kept": len(keep), "added": added, "dropped": dropped,
            "rebuilt": rebuilt}


def ledger_problems(conn, root) -> str | None:
    """The plain words an opener says when the ledger check fails, or None."""
    if getattr(_UNCHECKED, "on", False):
        return None
    try:
        missing = ledger_check(conn, root)
    except sqlite3.Error:
        return None
    if not missing:
        return None
    return ledger_problems_for(missing, root)


def ledger_problems_for(missing, root) -> str:
    names = "; ".join(
        f"conversation {m.get('conversation')} (deleted {m.get('at_iso') or m.get('at')} "
        f"by {m.get('by')}, act {m.get('deletion')}: {m['why']})"
        for m in missing[:10])
    more = f" and {len(missing) - 10} more" if len(missing) > 10 else ""
    return (f"{len(missing)} permanently deleted conversation(s) listed in "
            f"{ledger_path(root)} are not deleted in this Brain -- it was "
            f"restored from a backup taken before, or a deletion's commit "
            f"did not complete. Serving or exporting it would bring deleted "
            f"content back, so it is not opened: {names}{more}. Re-apply the "
            f"deletions with `python -m mentis.conversation.erasure reapply "
            f"\"{root}\" --by <owner>`: it completes exactly the deletions "
            f"the owner asked for")


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
