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
import os
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
    DELETED, "conversation-erasure-cleanup", "conversation-erasure-reapplied",
    "artifact-purged"})
#: (Review 2026-11-13, finding 3: standing and governance acts recorded in
#: the conversation -- authority-granted, material-*, governance-arrived ...
#: -- carried the conversation's words in `because` and `detail`. They are
#: erased to their skeleton like every other act there: who, what, when and
#: the ids they name. The records they established are entries, and keep
#: their bodies and standing.)
#: Relations by which an entry HANGS FROM conversation-owned content, for the
#: guard (`Guard.home`), besides versions (same Kind) and occurrence Kinds.
HANGS_FROM = frozenset({"in-conversation", "topic-of", "anchors-in",
                        "reacts-to", "responds-to", "in-response-set"})

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
    "conversation-erasure-cleanup": "the status of its physical cleanup, "
                                    "recorded after each attempt",
    "conversation-erasure-reapplied": "the owner re-applied a deletion a "
                                      "restored Brain did not hold",
}
#: AFTER EACH PHYSICAL CLEANUP ATTEMPT (owner decision 2026-11-13, B)
CLEANUP_ACT = "conversation-erasure-cleanup"
REAPPLIED_ACT = _er.REAPPLIED_ACT
CLEANUP_STATES = ("pending", "completed", "failed")

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

    def home(self, conn, x, guarded, depth=None):
        """The guarded Conversation `x` belongs to, or None: itself, a post
        homed there, a topic of it, a version or tombstone of one, or an
        occurrence hanging from one (an anchor, a reaction, a response set,
        an answer ...) -- followed to a fixed point, with NO depth limit (a
        version line of any length; review finding 4)."""
        if x in guarded:
            return x
        if not isinstance(x, str) or not x.startswith("ent-"):
            return None
        seen, frontier = {x}, [x]
        while frontier:
            nxt = []
            for to, rel, fkind, tkind in conn.execute(
                    "SELECT l.link_to, l.link_relation, f.def_name, t.def_name "
                    "FROM entry l JOIN entry f ON f.id = l.link_from "
                    "LEFT JOIN entry t ON t.id = l.link_to "
                    "WHERE l.link_from IN (SELECT value FROM json_each(?)) "
                    "AND l.link_relation IS NOT NULL",
                    (json.dumps(frontier),)):
                follows = (rel in HANGS_FROM
                           or fkind in OCCURRENCE_KINDS
                           or (rel in VERSION_RELATIONS
                               and (fkind == tkind or fkind == "deletion")))
                if not follows or not isinstance(to, str):
                    continue
                if to in guarded:
                    return to
                if to not in seen:
                    seen.add(to)
                    nxt.append(to)
            frontier = nxt
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
    # LINKS touching erased entries: the row and both ends ALWAYS stay; the
    # body of every link with an erased endpoint is erased WHOLE (review
    # round 3, finding 1: no heuristic can tell which words quote the
    # deleted content). A deep-dive child keeps its reason in its own opening
    # post and act, which `anchors.origin` reads when the link's is gone.
    links_erased, links_kept = [], 0
    for lid, frm, to, rel, body in _q(
            c, "SELECT id, link_from, link_to, link_relation, body FROM "
               "entry WHERE link_relation IS NOT NULL AND (link_from IN "
               "(SELECT value FROM json_each(?)) OR link_to IN (SELECT value "
               "FROM json_each(?)))", (_js(erase), _js(erase))):
        if body == "{}" or _er.erased_by(body):
            links_kept += 1
            continue
        links_erased.append(lid)
    # rows a writer that did not keep the index left after its mark: read,
    # never written here
    lag = _er.lagging(lambda sql, args=(): _q(c, sql, args)) \
        if c._store._refs else []
    # ACTS: every act recorded in the conversation, and every act with NO
    # conversation whose turn or `about` is erased content (an edit addressed
    # by version id records none; review finding 3) -- erased to their
    # skeleton; only the deletion's own system acts are kept
    acts_erased, acts_kept, seen_acts = [], [], set()
    for aid, act in _q(c, "SELECT id, act FROM operational WHERE "
                          "conversation = ? ORDER BY seq", (cid,)):
        seen_acts.add(aid)
        (acts_kept if act in KEEP_ACTS else acts_erased).append((aid, act))
    about_e = _acts_about(c, erase, lag)
    for aid, act, conv in about_e:
        if aid in seen_acts or conv is not None or act in KEEP_ACTS:
            continue
        seen_acts.add(aid)
        acts_erased.append((aid, act))
    deliveries = [r[0] for r in _q(c, "SELECT id FROM delivery WHERE "
                                      "conversation = ?", (cid,))]
    # FILES produced here: ADMISSIONS ONLY (a `produced` candidate note is
    # knowledge, never a file; review finding 1)
    produced = _q(c, "SELECT l.link_to, o.id FROM entry l JOIN operational o "
                     "ON o.id = l.link_from JOIN entry a ON a.id = l.link_to "
                     "AND a.family = 'admission' WHERE l.link_relation = "
                     "'produced' AND o.conversation = ?", (cid,))
    inside = (set(erase) | set(links_erased) | {a for a, _ in acts_erased}
              | set(deliveries))
    files_removed, files_kept = [], []
    for adm in sorted({a for a, _ in produced}):
        why = _shared_why(c, adm, inside, lag)
        (files_kept if why else files_removed).append(
            {"id": adm, **_file_label(c, adm), **({"why": why} if why else {})})
    erase_files = {f["id"] for f in files_removed}
    entry_ids = sorted(erase | erase_files)
    carrying = []
    if entry_ids:
        for aid, act, conv in _acts_about(c, set(entry_ids), lag):
            if act in CARRYING_ACTS and conv not in (cid, None) \
                    and aid not in seen_acts:
                seen_acts.add(aid)
                carrying.append((aid, act))
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


def _acts_about(c, ids, lag=()) -> list:
    """(act id, act, conversation) of every act whose `turn` or `about`
    names one of these ids."""
    ids = set(ids)
    if not ids:
        return []
    out = {}
    for aid, act, conv in _q(
            c, "SELECT o.id, o.act, o.conversation FROM operational o WHERE "
               "o.turn IN (SELECT value FROM json_each(?))", (_js(ids),)):
        out[aid] = (aid, act, conv)
    for aid, act, conv in _q(
            c, "SELECT DISTINCT o.id, o.act, o.conversation FROM ref_index r "
               "JOIN operational o ON o.id = r.src WHERE r.target IN (SELECT "
               "value FROM json_each(?)) AND r.kind LIKE 'act:%'", (_js(ids),)):
        out[aid] = (aid, act, conv)
    for src, conv, t, kind in lag:
        if t in ids and kind.startswith("act:") and src not in out:
            got = c.operational(id=src)
            if got:
                out[src] = (src, got[0]["act"], got[0].get("conversation"))
    return list(out.values())


def _shared_why(c, adm, inside, lag=()) -> str | None:
    """Why this file is not exclusive to the deleted Conversation, or None.
    Decided from the reference index (and its lag), never from a path.
    EVERY SURVIVING REFERENCE COUNTS (review finding 2): a kept link's words,
    any act's about or detail, any run's material -- anything whose source
    is not itself erased by this deletion (`inside`: the erased entries,
    erased link bodies, erased acts and deliveries)."""
    got = c.read([adm])
    body = (got[0]["body"] if got else {}) or {}
    if body.get("collection"):
        return "part of a source collection"
    refs = [tuple(r) for r in _q(
        c, "SELECT src, kind FROM ref_index WHERE target = ?", (adm,))]
    refs += [(src, kind) for src, _, t, kind in lag if t == adm]
    for src, rel in refs:
        if rel in ("link:produced", "link:purged"):
            continue                    # the file's own possession records
        if src in inside:
            continue
        if rel == "link:pictured-by":
            return "a profile picture"
        if rel.startswith("act:") or rel.startswith("detail:") \
                or rel == "material":
            return "supplied to work elsewhere"
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
            # link reasons erased (n): every link with an erased end
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
    # THE TOKEN NAMES WHAT WOULD BE DONE, NOT ONLY WHAT IS SHOWN (review
    # finding 5): every file's Admission id and digest, and a digest of the
    # exact erase set (entries, link bodies, acts, deliveries)
    erase_set = sorted(
        [("entry", e) for e in inv["entries"]]
        + [("entry", f["id"]) for f in inv["files_removed"]]
        + [("entry", x) for x in inv["links_erased"]]
        + [("operational", a) for a, _ in inv["acts_erased"]]
        + [("operational", a) for a, _ in inv["carrying"]]
        + [("delivery", d) for d in inv["deliveries"]])
    out["erase_digest"] = hashlib.sha256(json.dumps(
        erase_set).encode("utf-8")).hexdigest()
    basis = {**out,
             "files_removed_ids": [(f["id"], f.get("digest"))
                                   for f in inv["files_removed"]],
             "files_kept_ids": [(f["id"], f.get("digest"), f.get("why"))
                                for f in inv["files_kept"]]}
    out["token"] = hashlib.sha256(json.dumps(
        basis, sort_keys=True, default=str).encode("utf-8")).hexdigest()
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
    undo: dict = {}
    try:
        return _delete_now(cv, cid, c, store, checked, guard, undo, by=by,
                           token=token, route=route, in_flight=in_flight,
                           started=started)
    except BaseException:
        _undo_ledger(c, undo)            # the commit did not happen
        raise


def _delete_now(cv, cid, c, store, checked, guard, undo, *, by, token, route,
                in_flight, started):
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
        targets, files = _targets_of(inv)
        counts = dict(imp["counts"])
        counts.update({"files_removed": len(inv["files_removed"]),
                       "files_kept": len(inv["files_kept"]),
                       "surviving_records": len(inv["surviving"])})
        done, aid, purged, targets = _perform(
            cv, cid, targets, files, counts, by=by, route=route,
            token=token, guard=guard, undo=undo)
        held_ms = (time.perf_counter() - t0) * 1000
    return _after_commit(cv, cid, aid, done, inv, imp, counts, purged,
                         targets, by=by, held_ms=held_ms, started=started)


def _targets_of(inv) -> tuple:
    """The (table, row id) erase set and the files to purge, from an
    inventory."""
    targets = ([("entry", e) for e in inv["entries"]]
               + [("entry", f["id"]) for f in inv["files_removed"]]
               + [("entry", lid) for lid in inv["links_erased"]]
               + [("operational", a) for a, _ in inv["acts_erased"]]
               + [("operational", a) for a, _ in inv["carrying"]]
               + [("delivery", d) for d in inv["deliveries"]])
    files = [{"admission": f["id"], "digest": f["digest"]}
             for f in inv["files_removed"]]
    return targets, files


def _perform(cv, cid, targets, files, counts, *, by, route, token, guard,
             extra=None, undo=None):
    """Inside the deletion's transaction: the files' purge records, then
    `Store.erase` (the act, the erasure rows, the UPDATEs), verified, then
    the DELETION LEDGER line and its erase-set sidecar, written and fsynced
    BEFORE the commit (review round 2, finding 1): if they cannot be written
    the deletion is refused and nothing changes. If the commit then fails,
    the ledger lists a deletion the Brain does not hold, which refuses the
    Brain until the owner's `reapply` completes it."""
    c = cv.corpus
    store = c._store
    from mentis.artifacts import PURGE
    purged = []
    for f in files:
        aid = cv.record_act(
            actor=by, act=PURGE, about=[f["admission"]],
            because="its conversation was permanently deleted",
            detail={"digest": f["digest"], "shared_with": []})
        c.write(body={"reason": "its conversation was permanently "
                                "deleted"},
                attributed_to=by,
                link={"from": aid, "to": f["admission"],
                      "relation": "purged"})
        purged.append(aid)
    # rows already erased are not erased twice (none should be)
    conn = store._conn
    targets = [(t, r) for t, r in targets if not conn.execute(
        "SELECT 1 FROM erasure WHERE tbl = ? AND row_id = ?",
        (t, r)).fetchone()]
    aid = f"opr-{uuid.uuid4().hex[:12]}"
    record = {"id": aid, "at": time.time(), "actor": by, "act": DELETED,
              "conversation": cid, "about": [cid], "because": None,
              "detail": {"authorized": {"by": by, "route": route,
                                        "impact_token": token},
                         "impact": counts,
                         # what physical cleanup must remove: ids and
                         # digests, never names
                         "files": files,
                         **(extra or {})}}
    guard.erasing.on = True
    try:
        done = store.erase(record, targets)
    finally:
        guard.erasing.on = False
    _verify_erased(conn, aid, done["planned"])
    # THE LEDGER BEFORE IT CHANGES, so a deletion that does not commit can be
    # taken back out of it (review round 3, finding 6)
    if undo is not None:
        undo["ledger"] = (_er.ledger_snapshot(c.root),
                          os.path.join(_er.erase_set_dir(c.root),
                                       aid + ".json"))
    try:
        _er.ledger_record(c.root, {
            "corpus_id": c.corpus_id, "conversation": cid, "deletion": aid,
            "digest": done["digest"], "rows": done["rows"],
            "at": time.time(), "at_iso": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "by": by,
            **({"reapplies": extra["reapplies"]}
               if extra and extra.get("reapplies") else {})},
            [(t, r) for t, r, _, _ in done["planned"]], files)
    except OSError as exc:
        _undo_ledger(c, undo)
        raise Refused({
            "error": "the deletion ledger could not be written, so nothing "
                     f"was deleted: {exc}. Make "
                     f"{_er.ledger_path(c.root)} writable and try again",
            "code": "ledger-unwritable", "conversation": cid}) from exc
    except BaseException:
        _undo_ledger(c, undo)
        raise
    return done, aid, purged, targets


def _undo_ledger(c, undo) -> None:
    """The deletion did not happen: put the ledger back as it was and remove
    its erase set. If that cannot be done, the open Store is GATED -- every
    read and write scope refuses with the ledger's words until reapply or
    check --repair -- since the ledger now lists a deletion this Brain does
    not hold. (A process that dies here is refused at its next open, and the
    owner's reapply completes the deletion.)"""
    if not undo or not undo.get("ledger"):
        return
    previous, sidecar = undo.pop("ledger")
    try:
        # the erase set first: without it no intent of this deletion stays
        try:
            os.remove(sidecar)
        except FileNotFoundError:
            pass
        if _er.ledger_snapshot(c.root) != previous:
            _er.ledger_restore(c.root, previous)
    except Exception:                                       # noqa: BLE001
        c._store.ledger_gate = True


def _after_commit(cv, cid, aid, done, inv, imp, counts, purged, targets, *,
                  by, held_ms, started) -> dict:
    """THE LOGICAL DELETION IS DONE (committed): nothing here can undo it or
    turn it into a failure. The deletion ledger line (fsynced), the caches
    that hold content by id, then one physical cleanup attempt -- recorded,
    with its verified status -- and a retry of earlier ones still pending
    or failed (an explicit act's own step, never a background one)."""
    c = cv.corpus
    _er.erased([t[1] for t in targets if t[0] == "entry"])
    physical = cleanup(cv, cid, by=by)
    retried = retry_pending(cv, by=by, besides={cid})
    return {"conversation": cid, "deleted": True, "act": aid,
            "erased_rows": done["rows"], "digest": done["digest"],
            "counts": counts, "purged": purged,
            "files_kept": imp["files_kept"],
            "surviving_records": inv["surviving"],
            "physical_cleanup": physical,
            "earlier_cleanups_retried": retried,
            "ledger": _er.ledger_path(c.root),
            "writer_held_ms": round(held_ms, 1),
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


def _live_digests(c, digests) -> set:
    """Which of these digests a held, unpurged, unerased Admission names."""
    live = set()
    for aid, loc in _q(c, "SELECT id, json_extract(body, '$.locator') FROM "
                          "entry WHERE family = 'admission' AND "
                          "json_extract(body, '$.content') = 'held'"):
        d = _digest(loc)
        if d in digests and not _q(c, "SELECT 1 FROM entry WHERE "
                                      "link_relation = 'purged' AND link_to = ?"
                                      " LIMIT 1", (aid,)):
            live.add(d)
    return live


def _clean_files(c, files) -> dict:
    """UNLINK each removed file's bytes where no live Admission holds the
    digest, then VERIFY the path is absent and the derived extractions are
    gone. UNLINK ONLY: an artifact file may be a hardlink another Brain
    shares, so it is never opened for writing, truncated or overwritten."""
    from mentis.spine import held
    from mentis.artifacts import _forget_extractions
    from mentis.sources.extract import store as _extract
    digests = sorted({f["digest"] for f in files if f.get("digest")})
    live = _live_digests(c, set(digests))
    removed, absent, remaining, kept = [], [], [], []
    for d in digests:
        if d in live:
            kept.append(d)                  # another live holder: not ours
            continue
        try:
            if held.remove(c.root, d):
                removed.append(d)
        except OSError as exc:
            remaining.append({"digest": d, "what": "bytes",
                              "why": f"{type(exc).__name__}: {exc}"})
            continue
        try:
            _forget_extractions(c, d, live)
        except Exception:                                   # noqa: BLE001
            pass
        gone = not held.path(c.root, d).exists()
        ext = _extract._digest_dir(c.root, d)
        ext_gone = not ext.exists()
        if gone and ext_gone:
            absent.append(d)
        else:
            remaining.append({"digest": d,
                              "what": "bytes" if not gone else "extractions",
                              "why": "still on disk after removal"})
    return {"removed": removed, "absent": absent, "remaining": remaining,
            "kept_held_elsewhere": kept,
            "verified": not remaining and len(absent) + len(kept)
            == len(digests)}


def _clean_database(c) -> dict:
    """The WAL checkpointed with TRUNCATE and VERIFIED: busy 0, every frame
    checkpointed, the -wal file empty. The erasing write already ran with
    secure_delete on, so the database file holds no freed content once its
    pages are checkpointed."""
    import os
    store = c._store
    ck = store.checkpoint()
    res = ck.get("result") or []
    wal = os.path.join(c.root, "corpus.db-wal")
    try:
        size = os.path.getsize(wal)
    except OSError:
        size = 0
    ok = (len(res) == 3 and res[0] == 0 and res[1] == res[2]
          and size == 0)
    out = {"checkpoint": res, "wal_bytes": size, "verified": ok}
    if not ok:
        out["why"] = ck.get("why") or (
            "the write-ahead log still holds frames: another reader kept a "
            "snapshot open")
    return out


def cleanup(cv, cid, *, by=None) -> dict:
    """ONE PHYSICAL CLEANUP ATTEMPT for a deleted Conversation, its outcome
    VERIFIED and recorded (`conversation-erasure-cleanup`): `completed` only
    when the database, every file and the deletion ledger line are verified;
    otherwise `failed`, saying why and what remains. Never undoes or fails
    the logical deletion."""
    from mentis.operational.work_overview import owner_of
    c = cv.corpus
    d = deleted(cv).get(cid)
    if d is None:
        raise Refused({"error": f"{cid} has not been permanently deleted",
                       "conversation": cid, "code": "not-deleted"})
    act = c.operational(id=d["act"])
    detail = (act[0]["detail"] if act else {}) or {}
    files = detail.get("files") or []
    try:
        fs = _clean_files(c, files)
    except Exception as exc:                                # noqa: BLE001
        fs = {"removed": [], "absent": [], "remaining": [
            {"what": "files", "why": f"{type(exc).__name__}: {exc}"}],
              "verified": False}
    try:
        db = _clean_database(c)
    except Exception as exc:                                # noqa: BLE001
        db = {"verified": False, "why": f"{type(exc).__name__}: {exc}"}
    ledger = _ledger_repaired(c, cid, d)
    done = fs["verified"] and db["verified"] and ledger["written"]
    reasons = [x for x in (
        None if fs["verified"] else
        f"{len(fs['remaining'])} file(s) still on disk",
        None if db["verified"] else db.get("why"),
        None if ledger["written"] else ledger.get("why")) if x]
    status = {"status": "completed" if done else "failed",
              "database": db, "files": fs, "ledger": ledger,
              "reason": None if done else "; ".join(reasons)}
    actor = by or owner_of(cv) or "mentis"
    aid = cv.record_act(actor=actor, act=CLEANUP_ACT, conversation=cid,
                        about=[cid, d["act"]], detail=status)
    return {**status, "act": aid, "at": time.time()}


def _ledger_repaired(c, cid, d) -> dict:
    """The deletion's ledger line and erase-set sidecar: present and whole,
    or WRITTEN AGAIN from the record (its act and erasure rows) when lost
    (review round 2, finding 1). Says which, and why when it cannot."""
    path = _er.ledger_path(c.root)
    line = next((e for e in _er.ledger_entries(c.root, c.corpus_id)
                 if e.get("deletion") == d["act"]), None)
    if line is not None:
        try:
            _er.read_erase_set(c.root, line)
            return {"written": True, "path": path}
        except (OSError, ValueError):
            pass                        # the sidecar is lost: write it again
    act = c.operational(id=d["act"])
    detail = (act[0]["detail"] if act else {}) or {}
    rows = [(t, r) for t, r in c._store._rows(
        "SELECT tbl, row_id FROM erasure WHERE deletion = ? ORDER BY seq",
        (d["act"],))]
    got = [tuple(x) for x in c._store._rows(
        "SELECT tbl, row_id, row_hash, residual FROM erasure WHERE "
        "deletion = ?", (d["act"],))]
    try:
        _er.ledger_record(c.root, {
            "corpus_id": c.corpus_id, "conversation": cid,
            "deletion": d["act"], "digest": _er.digest(got),
            "rows": len(got), "at": d["at"], "at_iso": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(d["at"] or 0)),
            "by": d["by"], "repaired": True},
            rows, detail.get("files") or [], append=line is None)
    except OSError as exc:
        return {"written": False, "path": path,
                "why": f"the deletion ledger could not be written: {exc}"}
    return {"written": True, "path": path, "repaired": True}


def cleanup_status(cv, cid) -> dict:
    """The latest recorded cleanup of a deleted Conversation; `pending`
    when none has been recorded yet."""
    got = cv.corpus.operational(conversation=cid, act=CLEANUP_ACT,
                                newest_first=True, limit=1)
    if not got:
        return {"status": "pending", "reason": "no cleanup attempt recorded "
                                               "yet", "act": None, "at": None}
    a = got[0]
    det = a.get("detail") or {}
    return {**det, "act": a["id"], "at": a.get("at")}


def retry_pending(cv, *, by=None, besides=()) -> list:
    """Attempt cleanup again for every deleted Conversation whose status is
    not `completed` -- asked only by an explicit act (a deletion, server
    start, the owner's Finish cleanup), never on a timer. Each attempt
    records its act. Returns [{conversation, status}]."""
    out = []
    for cid in deleted(cv):
        if cid in besides:
            continue
        if cleanup_status(cv, cid).get("status") == "completed":
            continue
        try:
            got = cleanup(cv, cid, by=by)
            out.append({"conversation": cid, "status": got["status"]})
        except Exception as exc:                            # noqa: BLE001
            out.append({"conversation": cid, "status": "failed",
                        "reason": f"{type(exc).__name__}: {exc}"})
    return out


# -- tombstones ------------------------------------------------------------------

def deleted(cv) -> dict:
    """cid -> {at, by, act} for every deleted Conversation."""
    return {r[0]: {"at": r[1], "by": r[2], "act": r[3]} for r in _q(
        cv.corpus, "SELECT conversation, at, actor, id FROM operational "
                   "WHERE act = ? ORDER BY seq", (DELETED,))}


def tombstone(cv, cid, *, with_records=True, known=None) -> dict | None:
    d = (deleted(cv) if known is None else known).get(cid)
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
           "counts": detail.get("impact") or {},
           # TWO OUTCOMES (owner decision 2026-11-13): `deleted` is logical
           # and final; physical cleanup is tracked on its own
           "physical_cleanup": _status_view(cleanup_status(cv, cid))}
    if with_records:
        out["surviving_records"] = _surviving_now(cv, cid)
    return out


def _status_view(st) -> dict:
    """What a tombstone says of physical cleanup: status, when, why, and
    what remains -- no paths beyond the Brain's own, no names."""
    files = st.get("files") or {}
    return {"status": st.get("status"), "at": st.get("at"),
            "act": st.get("act"), "reason": st.get("reason"),
            "database": (st.get("database") or {}).get("verified"),
            "files_remaining": len(files.get("remaining") or []),
            "ledger": (st.get("ledger") or {}).get("written")}


# -- re-applying deletions a restored Brain does not hold (amendment D) ---------

def reapply(root, *, by, acknowledge_open_work=False) -> dict:
    """`python -m mentis.conversation.erasure reapply <brain> --by <owner>
    [--acknowledge-open-work]`: the owner's explicit act for a Brain that
    does not hold deletions its ledger lists (restored from an earlier
    backup, or a deletion whose commit did not complete). Each is applied
    again with EXACTLY ITS ORIGINAL ERASE SET (the ledger's sidecar; review
    round 2, finding 7) -- the rows of it this Brain holds, and only the
    files the original purged -- under its own new `conversation-deleted`
    act, and a `conversation-erasure-reapplied` act names the deletion it
    re-applies. Work in flight in the restored conversation refuses it,
    naming the work, unless the owner acknowledges it (finding 8): it is
    then recorded in that act."""
    import mentis.api as api
    from mentis.operational.work_overview import owner_of
    with _er.ledger_unchecked():
        c = api.open_corpus(root, access="write")
        try:
            cv = api.brain(c).conversations
            owner = owner_of(cv)
            if not by or by != owner:
                raise Refused({"error": "only the owner re-applies "
                                        "deletions", "code": "owner-only"})
            missing = _er.ledger_check(c._store._conn, c.root)
            done, damaged = [], []
            for e in missing:
                cid = e.get("conversation")
                if "unreadable" in e:
                    # a torn or damaged line: what it said is in its erase
                    # set, which reads as an intent of its own below
                    damaged.append(e["unreadable"])
                    continue
                if not cid:
                    done.append({**e, "reapplied": False,
                                 "why": "the ledger line names no "
                                        "conversation"})
                    continue
                done.append(_reapply_one(
                    cv, cid, e, by=by,
                    acknowledge_open_work=acknowledge_open_work))
            repaired = None
            if damaged or any(e.get("from_sidecar") for e in missing) \
                    or any("erase set cannot be read" in str(e.get("why"))
                           for e in missing):
                repaired = _er.ledger_repair(c._store._conn, c.root)
            left = _er.ledger_check(c._store._conn, c.root)
        finally:
            c.close()
    return {"brain": root, "reapplied": done, "still_missing": left,
            "damaged_lines": damaged, "ledger_repaired": repaired}


def _reapply_one(cv, cid, entry, *, by, acknowledge_open_work) -> dict:
    c = cv.corpus
    store = c._store
    try:
        es = _er.read_erase_set(c.root, entry)
    except (OSError, ValueError) as exc:
        return {"conversation": cid, "reapplied": False,
                "original": entry.get("deletion"),
                "why": "the original erase set cannot be read, so it cannot "
                       f"be re-applied exactly: {exc}"}
    marker_, here = cv.trash_check(cid)
    open_work = {k: here.get(k) or 0 for k in ("running", "waiting",
                                                 "pending")}
    if any(open_work.values()) and not acknowledge_open_work:
        from . import trash_refusal_words
        return {"conversation": cid, "reapplied": False,
                "original": entry.get("deletion"), "code": "work-in-flight",
                "open_work": open_work,
                "why": trash_refusal_words(open_work["running"],
                                           open_work["waiting"],
                                           open_work["pending"])
                + " The restored Brain cannot be written to resolve it: "
                  "re-apply with --acknowledge-open-work to delete anyway, "
                  "recording that work."}
    guard = install(c)
    t0 = time.perf_counter()
    started = t0
    undo: dict = {}
    try:
        got = _reapply_now(cv, cid, entry, es, c, store, guard, undo,
                           open_work=open_work, by=by, t0=t0)
    except BaseException:
        _undo_ledger(c, undo)
        raise
    aid, done, counts, purged, targets, held_ms = got
    out = _after_commit(cv, cid, aid, done, {"surviving": []},
                        {"files_kept": []}, counts, purged, targets, by=by,
                        held_ms=held_ms, started=started)
    return {"conversation": cid, "reapplied": True,
            "original": entry.get("deletion"), "act": aid,
            "rows": len(targets),
            "physical_cleanup": out["physical_cleanup"]["status"]}


def _reapply_now(cv, cid, entry, es, c, store, guard, undo, *, open_work, by,
                 t0):
    with c.atomic():
        conn = store._conn
        targets = []
        for t, r in es["rows"]:
            if t not in _er.TABLES:
                continue
            if conn.execute(f"SELECT 1 FROM {t} WHERE id = ?",
                            (r,)).fetchone():
                targets.append((t, r))
        files = [f for f in es.get("files") or []
                 if conn.execute("SELECT 1 FROM entry WHERE id = ?",
                                 (f["admission"],)).fetchone()
                 and not conn.execute(
                     "SELECT 1 FROM entry WHERE link_relation = 'purged' "
                     "AND link_to = ?", (f["admission"],)).fetchone()]
        counts = {"reapplied_rows": len(targets),
                  "original_rows": len(es["rows"]),
                  "files_removed": len(files)}
        done, aid, purged, targets = _perform(
            cv, cid, targets, files, counts, by=by, route="reapply",
            token=None, guard=guard,
            extra={"reapplies": entry.get("deletion")}, undo=undo)
        guard.erasing.on = True
        try:
            cv.record_act(actor=by, act=REAPPLIED_ACT, conversation=cid,
                          about=[cid, entry.get("deletion"), aid],
                          detail={"deletion": aid,
                                  "original": entry.get("deletion"),
                                  "original_digest": entry.get("digest"),
                                  "original_rows": entry.get("rows"),
                                  "erase_set_digest": entry.get(
                                      "erase_set_digest"),
                                  "rows_held_here": len(targets),
                                  **({"open_work_acknowledged": open_work}
                                     if any(open_work.values()) else {})})
        finally:
            guard.erasing.on = False
        held_ms = (time.perf_counter() - t0) * 1000
    return aid, done, counts, purged, targets, held_ms


def _main(argv) -> int:
    """`python -m mentis.conversation.erasure check <brain> [--repair]`
    `python -m mentis.conversation.erasure reapply <brain> --by <owner>
        [--acknowledge-open-work]`"""
    import os
    import sys
    from mentis.spine.store import Store
    if len(argv) < 2 or argv[0] not in ("check", "reapply"):
        print(_main.__doc__)
        return 2
    root = os.path.abspath(argv[1])
    if argv[0] == "check":
        with _er.ledger_unchecked():        # inspection: the owner's override
            s = Store(root, access="read")
        try:
            repaired = (_er.ledger_repair(s._conn, root)
                        if "--repair" in argv else None)
            missing = _er.ledger_check(s._conn, root)
        finally:
            s.close()
        if repaired is not None:
            print(json.dumps({"repaired": repaired}, indent=1))
        print(json.dumps({"brain": root, "ledger": _er.ledger_path(root),
                          "missing": missing}, indent=1))
        return 1 if missing else 0
    if "--by" not in argv or argv.index("--by") + 1 >= len(argv):
        print("reapply needs --by <the owner Participant>", file=sys.stderr)
        return 2
    try:
        out = reapply(root, by=argv[argv.index("--by") + 1],
                      acknowledge_open_work="--acknowledge-open-work" in argv)
    except Refused as exc:
        print(json.dumps(exc.refusal), file=sys.stderr)
        return 1
    print(json.dumps(out, indent=1, default=str))
    return 1 if out["still_missing"] else 0


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


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
