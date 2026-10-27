"""Which rows of an export an apply writes, and why each other one is not.

Shared by the preview and the apply, so the two cannot disagree: the
preview's renumbering is computed over exactly the rows this selects
(review ent-cca01f8347bb, finding 4), and the apply writes exactly those.
"""

from __future__ import annotations

import json

from mentis.spine import held, imported

from . import format as fmt
#: what a row of the export is here (`preview` says it, with the reason)
NEW, IDENTICAL, CORRUPT, DIVERGED = "new", "identical", "corrupt", "diverged"

#: Detail fields of a carried act that name another row it is about. An act
#: whose such row is skipped is skipped with it (a rename's version, a form's
#: attachment, an answer's reply).
DETAIL_REFS = ("version", "link", "reply", "form", "post", "replaces")


def door_refs(row) -> set:
    """What the door requires to be here or in the batch (`imported.check`)."""
    if fmt.is_act(row):
        refs = {row.get("conversation"), row.get("turn"), row.get("caused_by")}
        refs |= {a for a in (row.get("about") or ()) if isinstance(a, str)}
    else:
        link = row.get("link") or {}
        refs = {link.get("from"), link.get("to")}
    return {r for r in refs if isinstance(r, str) and r}


def depends_on(row) -> set:
    """Everything a row needs written first. Besides what the door checks:
    the rows an act's detail is about, and WHO the row names -- its author,
    observer, actor and addressees. A Participant kept out (an unresolved
    @name, O4) keeps out what names them: the owner's answer may yet map
    them to somebody here, and a row already written under the other id
    could never be rewritten to say so."""
    out = door_refs(row)
    if fmt.is_act(row):
        d = row.get("detail") or {}
        out |= {d[k] for k in DETAIL_REFS if isinstance(d.get(k), str)}
        out.add(row.get("actor"))
    else:
        out |= {row.get("attributed_to"), row.get("written_by")}
        body = row.get("body") or {}
        out |= {a for a in body.get("addressed_to") or ()
                if isinstance(a, str)}
    return {r for r in out if isinstance(r, str) and r}


def here_refs(reader, export) -> set:
    """The rows the export names, and does not carry, that are here."""
    ids = {e["id"] for e in export.entries} | {a["id"] for a in export.acts}
    wanted = set()
    for row in list(export.entries) + list(export.acts):
        wanted |= door_refs(row)
    wanted -= ids
    return set(reader.entries(wanted)) | set(reader.acts_by_ids(wanted))


class Selection:
    """Which rows of the export are written, and why each other one is not.

    `rows` and `conflicts` are a Plan's (`preview.RowPlan`, `Conflict`)."""

    def __init__(self, rows, conflicts, export, here: set):
        self.x = export
        self.rows = {e["id"]: e for e in export.entries}
        self.rows.update({a["id"]: a for a in export.acts})
        by_id = {c.id: c for c in conflicts}
        self.here = {p.id for p in rows if p.state == IDENTICAL} | here
        self.send: set = set()
        self.skipped: dict = {}
        #: reply link -> (its post, held back with it, or None; why)
        self.held_replies: dict = {}
        #: response-set entry -> why
        self.held_responses: dict = {}
        for p in rows:
            if p.state == IDENTICAL:
                continue
            if p.blocked_by:
                self.skipped[p.id] = "; ".join(
                    f"{by_id[c].type}: {by_id[c].words}"
                    for c in p.blocked_by if c in by_id)
            elif p.state in (DIVERGED, CORRUPT):
                self.skipped[p.id] = p.reason
            elif p.state == NEW:
                self.send.add(p.id)

    def skip(self, rid, why):
        self.send.discard(rid)
        self.skipped.setdefault(rid, why)

    def settle(self):
        """Skip, to a fixed point, what depends on a skipped row or names
        something that is neither here nor written with it."""
        changed = True
        while changed:
            changed = False
            for rid in sorted(self.send):
                row = self.rows[rid]
                gone = sorted(r for r in depends_on(row) if r in self.skipped)
                if gone:
                    self.skip(rid, f"depends on {gone[0]}, which is not "
                                   f"applied")
                    changed = True
                    continue
                missing = sorted(r for r in door_refs(row)
                                 if r not in self.send and r not in self.here)
                if missing:
                    self.skip(rid, f"names {missing[0]}, which is neither in "
                                   f"this Brain nor carried by this file")
                    changed = True

    def hold_replies(self, store):
        """Hold back each reply the door would refuse as answering work open
        here (`imported.replies_closing_work_here`, the door's own rule), and
        the reply Turn it comes from when this file carries it, so the post
        does not arrive an orphan (as `preview.answer_replies` holds back a
        kept-out answer's reply). Then settle, so what depends on them
        follows. To a fixed point, though holding rows back only ever
        narrows what the rule can refuse."""
        while True:
            batch = [self.rows[rid] for rid in sorted(self.send)
                     if not fmt.is_act(self.rows[rid])]
            refused = imported.replies_closing_work_here(store, batch)
            if not refused:
                return
            for lid, why in sorted(refused.items()):
                post = self.rows[lid]["link"]["from"]
                post = post if post in self.send else None
                self.held_replies[lid] = (post, why)
                self.skip(lid, why)
                if post is not None:
                    self.skip(post, f"the post of reply {lid}, held back with "
                                    f"it: {why}")
            self.settle()

    def hold_responses(self, store):
        """Hold back each response-set entry the door would refuse as answering
        an input open here (R2), so the rest of the file still applies."""
        while True:
            batch = [self.rows[rid] for rid in sorted(self.send)
                     if not fmt.is_act(self.rows[rid])]
            refused = imported.responses_closing_work_here(store, batch)
            if not refused:
                return
            for rid, why in sorted(refused.items()):
                self.held_responses[rid] = why
                self.skip(rid, why)
            self.settle()

    def held_bytes(self, root, *, read: bool = True) -> dict:
        """digest -> bytes for every held Admission written (None for each
        when not `read`, as the preview asks). An Admission whose bytes are
        neither here nor in the file is skipped."""
        out = {}
        carried = set(self.x.blob_digests)
        for rid in sorted(self.send):
            row = self.rows[rid]
            body = row.get("body") or {}
            if row.get("family") != "admission" or body.get("content") != "held":
                continue
            digest = held.digest_of(body.get("locator"))
            if digest and held.has(root, digest):
                continue
            if digest in carried:
                out[digest] = self.x.blob(digest) if read else None
            else:
                self.skip(rid, "holds bytes that neither this Brain nor the "
                               "file holds")
        return out


def select(reader, rows, conflicts, export, root, *, store,
           read: bool = True):
    """The Selection settled, with the held bytes it needs: (sel, blobs).
    `store` is the spine Store the door will check against; inside a write,
    its reads go through the writer's connection."""
    sel = Selection(rows, conflicts, export, here_refs(reader, export))
    sel.settle()
    sel.hold_replies(store)
    sel.hold_responses(store)
    blobs = sel.held_bytes(root, read=read)
    sel.settle()
    return sel, blobs


def rewrites_recorded(reader, act_name) -> dict:
    """id -> [{fingerprint, written_fingerprint}] for every row an earlier
    import wrote HERE as other than it arrived (`written_as`): a supersession
    the door wrote as a proposal, or a row mapped to this Brain's version of
    an identical Kind. `fingerprint` is the row as it arrived."""
    out: dict = {}
    for a in reader.acts("act = ?", (act_name,)):
        d = a.get("detail")
        if isinstance(d, str):
            try:
                d = json.loads(d or "{}")
            except ValueError:
                continue
        for r in (d or {}).get("rows") or ():
            if isinstance(r, dict) and r.get("written_as") and r.get("id"):
                out.setdefault(r["id"], []).append(r)
    return out
