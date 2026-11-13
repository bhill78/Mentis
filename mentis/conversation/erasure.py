"""Permanent deletion of a Conversation, with epistemic preservation.

OWNER DECISION 2026-11-13 (contract `conv-mgmt/erasure-design.md`):
permanent deletion removes a Conversation's CONTENT without destroying the
knowledge, relationships and historical evidence Mentis legitimately
established from it. It is built on the one sanctioned exception to the
append-only record, attested erasure (`mentis.spine.erasure`, schema
0002): named content columns are replaced by a marker naming the deletion
act, every other column -- ids, links, who, what, when, the chain -- stays.

WHAT IS ERASED AND WHAT IS KEPT is `inventory` below, decided per Kind,
relation and act, and reported by `impact` before anything is done.

TRASH AND DELETED ARE NOT WRITABLE (`Guard`): installed on the store, asked
inside every append's transaction, so no interface -- Fluid, /api, the
worker door, MCP through it, the CLI, a run's result -- can add to a
Conversation in Trash, and nothing at all can be added to a deleted one.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid

from mentis.spine import erasure as _er

from .versions import Refused

DELETED = "conversation-deleted"
TRASHED_ACT = "conversation-trashed"

#: Kinds whose entries only ever describe the content they hang off -- an
#: anchor names a place in a post, a reaction reacts to it, an answer fills a
#: response set, a tombstone ends a line. Erased with what they hang off.
OCCURRENCE_KINDS = frozenset({
    "anchor", "reaction", "response-set", "answer", "marked-ready",
    "own-words", "interpretation", "interpretation-reply", "timer-mark",
    "deletion"})
#: Relations by which a later entry is a VERSION of the one it points at (a
#: rename, an edit, a tombstone): erased with it.
VERSION_RELATIONS = ("supersedes", "proposes-to-supersede")
#: A link touching erased content keeps its body when exactly one end is
#: erased and the relation belongs to the SURVIVING record's own standing or
#: provenance (its words are that record's, not the deleted content's).
KEEP_BODY_RELATIONS = frozenset({
    "establishes", "supersedes", "proposes-to-supersede", "proposes",
    "supports", "disputes", "declines", "withdraws", "carries-intake",
    "scoped-to", "in-context", "outcome-of", "pictured-by",
    "participates-in", "produced", "purged", "designated-as", "draws-on",
    "observes", "adopts", "regards"})
#: Relations that may quote: a surviving record's `extracted-from` /
#: `derived-from` body is erased only when it carries a citation.
QUOTING_RELATIONS = frozenset({"extracted-from", "derived-from"})
#: Acts with a conversation of their own (or none) that may carry the
#: deleted content anyway: an operation key's recorded result (a rename's
#: new name, a post's text). Erased when they refer to erased entries.
CARRYING_ACTS = frozenset({"operation-keyed"})
#: Acts recorded in the Conversation that are NOT erased: the deletion's own
#: attestation, and nothing else. (Standing acts on surviving records --
#: material-recorded/established/... -- carry no conversation; the inventory
#: reports any that do and keeps them: see `KEEP_ACTS`.)
KEEP_ACTS = frozenset({
    DELETED, "material-recorded", "material-established", "material-proposed",
    "material-superseded", "material-disputed", "material-placed",
    "material-edited", "material-deleted", "material-set-aside",
    "adoption-requested", "adoption-declined", "supersession-proposed",
    "governance-arrived", "schema-migrated", "bootstrap-applied",
    "magnet-extracted", "authority-granted", "artifact-purged"})

#: in Trash: the acts still accepted, and why (contract §4)
TRASH_ALLOWS = {
    "conversation-restored": "Restore returns it to the list",
    DELETED: "permanent deletion is from Trash",
    "delivery-failed": "closes a run that could not deliver",
    "execution-stop-asked": "stopping a run closes it",
    "operation-keyed": "the idempotency record of an operation that was "
                       "itself allowed (Restore, Delete)",
}
#: deleted: nothing, except the operation key of the deletion itself
DELETED_ALLOWS = {
    "operation-keyed": "the idempotency record of the deletion",
}

CANNOT_ERASE = [
    {"what": "earlier backups, snapshots and exports",
     "why": "copies made before deletion are outside this Brain"},
    {"what": "MARS session logs and data directories",
     "why": "MARS keeps its own logs; Mentis does not own them"},
    {"what": "git worktrees and commits",
     "why": "Git belongs to the work; Mentis does not rewrite it"},
    {"what": "agent workspaces and files outside Mentis",
     "why": "they are the agents' and the owner's own files"},
    {"what": "the physical disk blocks SQLite freed",
     "why": "freed space is zeroed in the database file and the WAL is "
            "truncated, but the file system may keep old blocks"},
]


#: the refusal codes of a write into Trash or a deleted Conversation
NOT_WRITABLE = ("conversation-in-trash", "conversation-deleted")


def status_of(refusal, default: int) -> int:
    """409 for a refusal that says the Conversation is not writable."""
    if isinstance(refusal, dict) and refusal.get("code") in NOT_WRITABLE:
        return 409
    return default


class ConversationNotWritable(RuntimeError):
    """A write into a Conversation in Trash (409 `conversation-in-trash`) or
    deleted (409 `conversation-deleted`).

    NOT a `versions.Refused`: the many doors that turn a Refused into their
    own answer (422, a worker's NotPermitted, a quiet skip) would each say it
    differently or not at all. This goes up to the HTTP layer, rolling back
    whatever transaction it is raised in, and is answered 409 there."""

    status = 409

    def __init__(self, refusal: dict):
        super().__init__(refusal.get("error", "refused"))
        self.refusal = refusal


def _refuse(cid, state, what):
    if state == "deleted":
        return ConversationNotWritable({
            "error": "This conversation was permanently deleted. Nothing can "
                     "be added to it.",
            "code": "conversation-deleted", "conversation": cid,
            "refused": what})
    return ConversationNotWritable({
        "error": "This conversation is in Trash. Restore it to add to it.",
        "code": "conversation-in-trash", "conversation": cid,
        "refused": what})


# -- the write guard ---------------------------------------------------------------

_STATE_ACTS = {
    "conversation-archived": "archived", "conversation-unarchived": "active",
    "conversation-trashed": "trashed", "conversation-restored": "active",
    DELETED: "deleted"}


class Guard:
    """`Store.write_guard`: refuses rows that would add to a Conversation in
    Trash or deleted. Its view of which Conversations are guarded is caught
    up from the operational stream's sequence on each call (one range read
    on the primary key; the acts of other processes are seen too)."""

    def __init__(self, store):
        self.store = store
        self._lock = threading.Lock()
        self._seen = 0
        self._state: dict = {}
        #: set while a deletion is writing its own rows
        self.erasing = threading.local()

    def guarded(self) -> dict:
        conn = self.store._conn
        acts = tuple(_STATE_ACTS)
        with self._lock:
            top = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM operational").fetchone()[0]
            if top < self._seen:          # a restore went back: start again
                self._seen, self._state = 0, {}
            if top > self._seen:
                for cid, act in conn.execute(
                        "SELECT conversation, act FROM operational WHERE seq > ? "
                        f"AND act IN ({','.join('?' * len(acts))}) ORDER BY seq",
                        (self._seen, *acts)):
                    if cid:
                        self._state[cid] = _STATE_ACTS[act]
                self._seen = top
            return {c: s for c, s in self._state.items()
                    if s in ("trashed", "deleted")}

    def home(self, conn, x, guarded, depth=0):
        """The guarded Conversation `x` belongs to, or None: itself, a post
        homed there, a topic of it, or a version of one of those."""
        if x in guarded:
            return x
        if not isinstance(x, str) or not x.startswith("ent-") or depth > 25:
            return None
        for (to,) in conn.execute(
                "SELECT link_to FROM entry WHERE link_from = ? AND "
                "link_relation IN ('in-conversation', 'topic-of', "
                "'supersedes', 'proposes-to-supersede')", (x,)):
            got = self.home(conn, to, guarded, depth + 1)
            if got:
                return got
        return None

    def __call__(self, table, rows):
        if getattr(self.erasing, "on", False):
            return
        guarded = self.guarded()
        if not guarded:
            return
        conn = self.store._conn
        for r in rows:
            if table == "operational":
                act = r.get("act")
                about = r.get("about")
                if isinstance(about, str):
                    try:
                        about = json.loads(about)
                    except ValueError:
                        about = []
                ids = [r.get("conversation"), r.get("turn"),
                       *(about or [])]
                for x in ids:
                    cid = self.home(conn, x, guarded) if x else None
                    if not cid:
                        continue
                    state = guarded[cid]
                    allows = DELETED_ALLOWS if state == "deleted" \
                        else TRASH_ALLOWS
                    if act not in allows:
                        raise _refuse(cid, state, act)
            elif table == "delivery":
                cid = r.get("conversation")
                if cid in guarded:
                    raise _refuse(cid, guarded[cid], "delivery")
            else:
                for x in (r.get("link_to"), r.get("link_from")):
                    cid = self.home(conn, x, guarded) if x else None
                    if cid:
                        raise _refuse(cid, guarded[cid],
                                      r.get("link_relation") or "entry")


def install(corpus) -> Guard | None:
    store = getattr(corpus, "_store", None)
    if store is None:
        return None
    if not isinstance(getattr(store, "write_guard", None), Guard):
        store.write_guard = Guard(store)
    return store.write_guard


# -- what a deletion erases ----------------------------------------------------------

def _q(corpus, sql, args=()):
    return corpus._store._rows(sql, args)


def _js(ids):
    return json.dumps(sorted(set(ids)))


def inventory(cv, cid) -> dict:
    """Everything a deletion of `cid` erases and keeps, decided from the
    record. Read only. See the progress log for the rule per Kind,
    relation and act."""
    c = cv.corpus
    posts = [r[0] for r in _q(c, "SELECT link_from FROM entry WHERE "
                                 "link_relation = 'in-conversation' AND "
                                 "link_to = ?", (cid,))]
    topics = []
    for (t,) in _q(c, "SELECT link_from FROM entry WHERE link_relation = "
                      "'topic-of' AND link_to = ?", (cid,)):
        elsewhere = _q(c, "SELECT 1 FROM entry WHERE link_relation = "
                          "'topic-of' AND link_from = ? AND link_to <> ? "
                          "LIMIT 1", (t, cid))
        if not elsewhere:
            topics.append(t)
    erase = {cid, *posts, *topics}
    roots = set(erase)
    kind_of = {}

    def kinds(ids):
        ids = [i for i in ids if i not in kind_of]
        for i, k in _q(c, "SELECT id, def_name FROM entry WHERE id IN "
                          "(SELECT value FROM json_each(?))", (_js(ids),)):
            kind_of[i] = k
    kinds(erase)
    frontier = set(erase)
    while frontier:
        nxt = set()
        rows = _q(c, "SELECT l.link_from, l.link_to, l.link_relation, "
                     "f.def_name FROM entry l JOIN entry f ON f.id = "
                     "l.link_from WHERE l.link_to IN (SELECT value FROM "
                     "json_each(?)) AND f.link_relation IS NULL",
                  (_js(frontier),))
        for frm, to, rel, fkind in rows:
            if frm in erase:
                continue
            kind_of[frm] = fkind
            if rel in VERSION_RELATIONS and (
                    fkind == kind_of.get(to) or fkind == "deletion"):
                nxt.add(frm)
            elif fkind in OCCURRENCE_KINDS:
                nxt.add(frm)
        erase |= nxt
        frontier = nxt
    # LINKS touching erased entries: structure kept; bodies by the rule
    links_erased, links_kept = [], 0
    for lid, frm, to, rel, body in _q(
            c, "SELECT id, link_from, link_to, link_relation, body FROM "
               "entry WHERE link_relation IS NOT NULL AND (link_from IN "
               "(SELECT value FROM json_each(?)) OR link_to IN (SELECT value "
               "FROM json_each(?)))", (_js(erase), _js(erase))):
        if body == "{}" or _er.erased_by(body):
            links_kept += 1
            continue
        both = frm in erase and to in erase
        if both:
            links_erased.append(lid)
            continue
        if rel in QUOTING_RELATIONS:
            try:
                cite = (json.loads(body) or {}).get("cite")
            except ValueError:
                cite = None
            if cite:
                links_erased.append(lid)
            else:
                links_kept += 1
            continue
        if rel in KEEP_BODY_RELATIONS:
            links_kept += 1
            continue
        links_erased.append(lid)
    # FILES produced here
    produced = _q(c, "SELECT l.link_to, o.id FROM entry l JOIN operational o "
                     "ON o.id = l.link_from WHERE l.link_relation = 'produced' "
                     "AND o.conversation = ?", (cid,))
    own_acts = {r[0] for r in _q(c, "SELECT id FROM operational WHERE "
                                    "conversation = ?", (cid,))}
    files_removed, files_kept = [], []
    # rows a writer that did not keep the index left after its mark: read,
    # never written here
    lag = _er.lagging(lambda sql, args=(): _q(c, sql, args))         if c._store._refs else []
    for adm in sorted({a for a, _ in produced}):
        why = _shared_why(c, adm, erase, own_acts, lag)
        (files_kept if why else files_removed).append(
            {"id": adm, **_file_label(c, adm), **({"why": why} if why else {})})
    erase_files = {f["id"] for f in files_removed}
    # ACTS
    acts_erased, acts_kept = [], []
    for aid, act in _q(c, "SELECT id, act FROM operational WHERE "
                          "conversation = ? ORDER BY seq", (cid,)):
        (acts_kept if act in KEEP_ACTS else acts_erased).append((aid, act))
    entry_ids = sorted(erase | erase_files)
    carrying = []
    if entry_ids:
        for aid, act, conv in _q(
                c, "SELECT DISTINCT o.id, o.act, o.conversation FROM ref_index "
                   "r JOIN operational o ON o.id = r.src WHERE r.target IN "
                   "(SELECT value FROM json_each(?)) AND r.kind LIKE 'act:%'",
                (_js(entry_ids),)):
            if act in CARRYING_ACTS and conv != cid:
                carrying.append((aid, act))
    deliveries = [r[0] for r in _q(c, "SELECT id FROM delivery WHERE "
                                      "conversation = ?", (cid,))]
    # SURVIVING RECORDS linked to what is erased (not erased themselves)
    surviving = []
    seen = set()
    for lid, frm, to, rel in _q(
            c, "SELECT l.id, l.link_from, l.link_to, l.link_relation FROM "
               "entry l WHERE l.link_relation IS NOT NULL AND (l.link_from IN "
               "(SELECT value FROM json_each(?)) OR l.link_to IN (SELECT "
               "value FROM json_each(?)))", (_js(erase), _js(erase))):
        other = to if frm in erase else frm
        if other in erase or other in seen or not isinstance(other, str):
            continue
        seen.add(other)
        got = c.read([other])
        if not got or got[0]["family"] != "entry" or got[0].get("link"):
            continue
        k = (got[0].get("definition") or {}).get("name")
        if k in ("contribution", "conversation", "participant", "topic"):
            continue
        surviving.append({"id": other, "kind": k,
                          "title": _title(got[0]), "relation": rel})
    kinds(erase)
    return {
        "conversation": cid, "entries": sorted(erase), "roots": sorted(roots),
        "posts": sorted(posts), "topics": sorted(topics),
        "kind_of": {i: kind_of.get(i) for i in erase},
        "links_erased": sorted(links_erased), "links_kept": links_kept,
        "files_removed": files_removed, "files_kept": files_kept,
        "acts_erased": acts_erased, "acts_kept": acts_kept,
        "carrying": carrying, "deliveries": deliveries,
        "surviving": surviving,
    }


def _shared_why(c, adm, erase, own_acts, lag=()) -> str | None:
    """Why this file is not exclusive to the deleted Conversation, or None.
    Decided from the reference index (and its lag), never from a path."""
    got = c.read([adm])
    body = (got[0]["body"] if got else {}) or {}
    if body.get("collection"):
        return "part of a source collection"
    refs = [tuple(r) for r in _q(
        c, "SELECT src, kind FROM ref_index WHERE target = ?", (adm,))]
    refs += [(src, kind) for src, _, t, kind in lag if t == adm]
    for src, rel in refs:
        if src in erase or src in own_acts:
            continue
        if rel == "body":
            # a link's words: inside when the link hangs off erased content
            lk = _q(c, "SELECT link_from, link_to FROM entry WHERE id = ? AND "
                       "link_relation IS NOT NULL", (src,))
            if lk and (lk[0][0] in erase or lk[0][1] in erase):
                continue
        if rel == "link:pictured-by":
            return "a profile picture"
        if rel.startswith("act:"):
            return "supplied to work elsewhere"
        if rel == "link:produced" or rel == "link:purged":
            continue
        return "referenced by something that is kept"
    return None


def _file_label(c, adm) -> dict:
    got = c.read([adm])
    body = (got[0]["body"] if got else {}) or {}
    env = body.get("envelope") or {}
    name = env.get("claimed_name") or body.get("name") or adm
    size = body.get("size") or env.get("size")
    if size is None:
        try:
            from mentis.spine import held
            p = held.path(c.root, held.digest_of(body.get("locator")))
            size = p.stat().st_size
        except Exception:                                   # noqa: BLE001
            size = None
    return {"label": name, "size": size,
            "digest": _digest(body.get("locator"))}


def _digest(locator):
    try:
        from mentis.spine import held
        return held.digest_of(locator)
    except Exception:                                       # noqa: BLE001
        return None


def _title(e) -> str:
    b = e.get("body") or {}
    for k in ("title", "name", "statement", "text", "summary"):
        v = b.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()[:120]
    return e["id"]


# -- the impact read --------------------------------------------------------------

def impact(cv, cid) -> dict:
    """What a permanent deletion of `cid` would do, in counts and labels, and
    the token that names exactly this impact. Requires Trash."""
    state = cv.conversation_state(cid)
    if not cv.is_conversation(cid) and state != "deleted":
        raise Refused({"error": f"{cid} is not a conversation in this record",
                       "conversation": cid})
    if state != "trashed":
        raise Refused({"error": "only a conversation in Trash can be "
                                "permanently deleted",
                       "conversation": cid, "state": state,
                       "code": "not-in-trash"})
    inv = inventory(cv, cid)
    return _impact_of(cv, cid, inv)


def _impact_of(cv, cid, inv) -> dict:
    c = cv.corpus
    posts = set(inv["posts"])
    replies = {r[0] for r in _q(c, "SELECT DISTINCT link_from FROM entry WHERE "
                                   "link_relation = 'replies-to' AND link_from "
                                   "IN (SELECT value FROM json_each(?))",
                                (_js(posts),))}
    versions = [e for e in inv["entries"] if e not in inv["roots"]]
    others = sorted({r[0] for r in _q(
        c, "SELECT DISTINCT h.link_to FROM entry l JOIN entry h ON "
           "h.link_from = l.link_from AND h.link_relation = 'in-conversation' "
           "WHERE l.link_relation = 'linked-into' AND l.link_to = ? AND "
           "h.link_to <> ?", (cid, cid))} | {r[0] for r in _q(
        c, "SELECT DISTINCT link_to FROM entry WHERE link_relation = "
           "'linked-into' AND link_from IN (SELECT value FROM json_each(?)) "
           "AND link_to <> ?", (_js(posts), cid))})
    work_elsewhere = _q(
        c, "SELECT COUNT(*) FROM operational o JOIN operational p ON p.id = "
           "o.caused_by WHERE (o.conversation = ? AND COALESCE(p.conversation,"
           "'') <> ?) OR (p.conversation = ? AND COALESCE(o.conversation,'') "
           "<> ?)", (cid, cid, cid, cid))[0][0]
    out = {
        "conversation": cid,
        "counts": {
            "posts": len(posts - replies), "replies": len(replies & posts),
            "versions": len(versions), "topics": len(inv["topics"]),
            "entries": len(inv["entries"]),
            "links_with_words_erased": len(inv["links_erased"]),
            "acts": len(inv["acts_erased"]) + len(inv["carrying"]),
            "acts_kept": len(inv["acts_kept"]),
            "runs_material": len(inv["deliveries"]),
        },
        "files_removed": [{"label": f["label"], "size": f["size"]}
                          for f in inv["files_removed"]],
        "files_kept": [{"label": f["label"], "why": f["why"]}
                       for f in inv["files_kept"]],
        "surviving_records": inv["surviving"],
        "relationships": {
            "other_conversations": others,
            "work_across": work_elsewhere,
            "surviving_records": len(inv["surviving"]),
        },
        "cannot_erase": CANNOT_ERASE,
    }
    out["token"] = hashlib.sha256(json.dumps(
        out, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return out


# -- the deletion -------------------------------------------------------------------

def delete(cv, cid, *, by, token, route="fluid", in_flight=None,
           dispatching=()) -> dict:
    """PERMANENTLY DELETE `cid` (in Trash, owner only, impact `token`
    current). One transaction: the purge acts of its exclusive files, the
    `conversation-deleted` act, the erasure rows, the erasing UPDATEs, and a
    verification of exactly those rows -- any failure rolls all of it back.
    After the commit: the exclusive files' bytes are unlinked where nothing
    else holds them, derived extractions forgotten, the WAL truncated."""
    from mentis.operational.work_overview import owner_of
    c = cv.corpus
    store = c._store
    owner = owner_of(cv)
    if not by or owner is None or by != owner:
        raise Refused({"error": "only the owner can permanently delete a "
                                "conversation", "code": "owner-only",
                       "conversation": cid})
    started = time.perf_counter()
    # Trash's work check, read before the write (as Trash itself is)
    checked = cv.trash_check(cid, dispatching=dispatching)
    guard = install(c)
    with c.atomic():
        t0 = time.perf_counter()
        if cv.conversation_state(cid) != "trashed":
            raise Refused({"error": "only a conversation in Trash can be "
                                    "permanently deleted", "conversation": cid,
                           "state": cv.conversation_state(cid),
                           "code": "not-in-trash"})
        marker_, here = checked
        if not cv._flight_unchanged(cid, marker_[0], marker_[1]):
            raise Refused({"error": "the record kept changing while the "
                                    "deletion was being checked; try again",
                           "code": "record-moved", "retry": True,
                           "conversation": cid})
        running = max(here["running"], int((in_flight or {}).get("running")
                                           or 0))
        if running or here["waiting"] or here.get("pending"):
            from . import trash_refusal_words
            raise Refused({"error": trash_refusal_words(
                running, here["waiting"], here.get("pending") or 0),
                "code": "work-in-flight", "conversation": cid,
                "running": running, "waiting": here["waiting"],
                "pending": here.get("pending") or 0})
        if store._refs:
            _er.catch_up(store._conn)
        inv = inventory(cv, cid)
        imp = _impact_of(cv, cid, inv)
        if token != imp["token"]:
            raise Refused({"error": "what this deletion would do has changed "
                                    "since it was shown; look again",
                           "code": "impact-changed", "conversation": cid,
                           "impact": imp})
        # the exclusive files: possession ended, as `artifacts.purge` records
        # it (act + `purged` link), in this transaction
        from mentis.artifacts import PURGE
        purged = []
        for f in inv["files_removed"]:
            aid = cv.record_act(
                actor=by, act=PURGE, about=[f["id"]],
                because="its conversation was permanently deleted",
                detail={"digest": f["digest"], "shared_with": []})
            c.write(body={"reason": "its conversation was permanently "
                                    "deleted"},
                    attributed_to=by,
                    link={"from": aid, "to": f["id"], "relation": "purged"})
            purged.append(aid)
        targets = ([("entry", e) for e in inv["entries"]]
                   + [("entry", f["id"]) for f in inv["files_removed"]]
                   + [("entry", lid) for lid in inv["links_erased"]]
                   + [("operational", a) for a, _ in inv["acts_erased"]]
                   + [("operational", a) for a, _ in inv["carrying"]]
                   + [("delivery", d) for d in inv["deliveries"]])
        # rows already erased are not erased twice (none should be)
        conn = store._conn
        targets = [(t, r) for t, r in targets if not conn.execute(
            "SELECT 1 FROM erasure WHERE tbl = ? AND row_id = ?",
            (t, r)).fetchone()]
        aid = f"opr-{uuid.uuid4().hex[:12]}"
        counts = dict(imp["counts"])
        counts.update({"files_removed": len(inv["files_removed"]),
                       "files_kept": len(inv["files_kept"]),
                       "surviving_records": len(inv["surviving"])})
        record = {"id": aid, "at": time.time(), "actor": by, "act": DELETED,
                  "conversation": cid, "about": [cid], "because": None,
                  "detail": {"authorized": {"by": by, "route": route,
                                            "impact_token": token},
                             "impact": counts}}
        guard.erasing.on = True
        try:
            done = store.erase(record, targets)
        finally:
            guard.erasing.on = False
        _verify_erased(conn, aid, done["planned"])
        held_ms = (time.perf_counter() - t0) * 1000
    # AFTER THE COMMIT: caches that hold content by id, bytes, extractions,
    # the WAL
    _er.erased([t[1] for t in targets if t[0] == "entry"])
    removed = _remove_bytes(c, inv["files_removed"])
    ck = store.checkpoint()
    return {"conversation": cid, "deleted": True, "act": aid,
            "erased_rows": done["rows"], "digest": done["digest"],
            "counts": counts, "purged": purged, "bytes_removed": removed,
            "files_kept": imp["files_kept"],
            "surviving_records": inv["surviving"],
            "checkpoint": ck, "writer_held_ms": round(held_ms, 1),
            "total_ms": round((time.perf_counter() - started) * 1000, 1),
            "cannot_erase": CANNOT_ERASE}


def _verify_erased(conn, aid, planned):
    """Inside the transaction: every planned row now holds the marker and
    its residual, and the act's digest covers exactly the erasure rows."""
    from mentis.spine.store import Store
    rows = []
    for tbl, rid, h, res in planned:
        cols = Store.CHAINED[tbl]
        r = conn.execute(f"SELECT {','.join(cols)}, hash FROM {tbl} WHERE "
                         f"id = ?", (rid,)).fetchone()
        d = dict(zip(cols, r[:len(cols)]))
        if (r[len(cols)] or "") != h or not _er.holds_marker(tbl, d, aid) \
                or _er.residual(tbl, d) != res:
            raise RuntimeError(f"erasure of {tbl} {rid} did not verify; "
                               "nothing was deleted")
        rows.append((tbl, rid, h, res))
    got = [tuple(x) for x in conn.execute(
        "SELECT tbl, row_id, row_hash, residual FROM erasure WHERE "
        "deletion = ?", (aid,))]
    act = conn.execute("SELECT detail FROM operational WHERE id = ?",
                       (aid,)).fetchone()
    e = json.loads(act[0])["erasure"]
    if sorted(got) != sorted(rows) or e["rows"] != len(got) \
            or e["digest"] != _er.digest(got):
        raise RuntimeError("the deletion's erasure rows did not verify; "
                           "nothing was deleted")


def _remove_bytes(c, files) -> list:
    """Unlink each removed file's bytes where no held, unpurged, unerased
    Admission elsewhere names the same digest. UNLINK ONLY: an artifact file
    may be a hardlink another Brain shares, so it is never opened for
    writing, truncated or overwritten."""
    from mentis.spine import held
    from mentis.artifacts import _forget_extractions
    digests = {f["digest"] for f in files if f.get("digest")}
    if not digests:
        return []
    live = set()
    for aid, loc in _q(c, "SELECT id, json_extract(body, '$.locator') FROM "
                          "entry WHERE family = 'admission' AND "
                          "json_extract(body, '$.content') = 'held'"):
        d = _digest(loc)
        if d in digests and not _q(c, "SELECT 1 FROM entry WHERE "
                                      "link_relation = 'purged' AND link_to = ?"
                                      " LIMIT 1", (aid,)):
            live.add(d)
    out = []
    for d in sorted(digests - live):
        if held.remove(c.root, d):
            out.append(d)
        try:
            _forget_extractions(c, d, live)
        except Exception:                                   # noqa: BLE001
            pass
    return out


# -- tombstones ------------------------------------------------------------------

def deleted(cv) -> dict:
    """cid -> {at, by, act} for every deleted Conversation."""
    return {r[0]: {"at": r[1], "by": r[2], "act": r[3]} for r in _q(
        cv.corpus, "SELECT conversation, at, actor, id FROM operational "
                   "WHERE act = ? ORDER BY seq", (DELETED,))}


def tombstone(cv, cid, *, with_records=True) -> dict | None:
    d = deleted(cv).get(cid)
    if d is None:
        return None
    c = cv.corpus
    got = c.read([cid])
    act = c.operational(id=d["act"])
    detail = (act[0]["detail"] if act else {}) or {}
    out = {"id": cid, "kind": "conversation", "deleted": True,
           "name": "Deleted conversation",
           "created": got[0]["recorded_at"] if got else None,
           "created_by": got[0]["attributed_to"] if got else None,
           "deleted_at": d["at"], "deleted_by": d["by"], "act": d["act"],
           "counts": detail.get("impact") or {}}
    if with_records:
        out["surviving_records"] = _surviving_now(cv, cid)
    return out


def _surviving_now(cv, cid) -> list:
    """Records that are kept and still point at the deleted conversation or
    its erased posts (titles are theirs)."""
    c = cv.corpus
    erased_ids = {r[0] for r in _q(
        c, "SELECT x.row_id FROM erasure x JOIN operational o ON o.id = "
           "x.deletion WHERE x.tbl = 'entry' AND o.conversation = ?", (cid,))}
    erased_ids.add(cid)
    out, seen = [], set()
    for frm, to, rel in _q(
            c, "SELECT link_from, link_to, link_relation FROM entry WHERE "
               "link_relation IS NOT NULL AND (link_from IN (SELECT value "
               "FROM json_each(?)) OR link_to IN (SELECT value FROM "
               "json_each(?)))", (_js(erased_ids), _js(erased_ids))):
        other = to if frm in erased_ids else frm
        if other in erased_ids or other in seen:
            continue
        seen.add(other)
        got = c.read([other])
        if not got or got[0]["family"] != "entry" or got[0].get("link"):
            continue
        k = (got[0].get("definition") or {}).get("name")
        if k in ("contribution", "conversation", "participant", "topic"):
            continue
        if _er.erased_by(got[0].get("body")):
            continue
        out.append({"id": other, "kind": k, "title": _title(got[0]),
                    "relation": rel})
    return out
