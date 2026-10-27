"""`mentis brain import <brain> <zip> --apply`: write the conflict-free part.

Design adm-6cebfabd6e9c, slice 2 (§3-§7, O3-O7). The preview's Plan
(`preview.classify`) is re-run on the receiving Brain, opened for writing, and
ONLY what it leaves unconflicted is written:

  written    rows the Plan calls `new` and nothing blocks: new Conversations,
             Turns with their original times (so they interleave by time and
             later Turns here renumber, O3), new items -- as candidates, since
             standing never travels -- held bytes before the Admissions that
             name them, and new Participants whose alias this Brain allows
  skipped    every row a conflict blocks (diverged lines, a rename over a
             Conversation or Participant that stands here, differing or absent
             Kinds O6, a foreign answer to a question answered here O7, an
             unresolved @name O4, refused acts and rows), every `diverged`
             row, and -- to a fixed point -- every row that depends on a
             skipped one or names something neither here nor written with it.
             Each is named, with why.

THE ORDER, AND WHAT A FAILURE LEAVES:

  0. refused, nothing written, while Mentis serves the Brain or anything else
     has it open: stop it first (`_alone`). The SERVE lock is held for the
     whole apply, so no server starts over it meanwhile;
  1. refused, nothing written, when the file comes from this Brain's own fork
     (origin fork_id == this fork_id), or the Plan refuses the whole import
     (a row corrupt here, schemas that differ);
  2. a no-op that says so when an earlier `import-applied` act names the same
     manifest sha256 (idempotent: a re-delivered file changes nothing);
  3. a backup, verified usable before anything is written (`mentis.spine.
     backup`), in the default backups folder beside the Brain;
  4. ONE transaction, BEGIN IMMEDIATE, in which the Plan and the selection
     are made AGAIN -- so what anybody wrote since the first Plan, during the
     backup included, is classified, and no other writer can commit until
     this one has -- then the bytes of held Admissions, put by digest
     (possession before the record of it, as `admit` requires), the rows
     through `Store.append_imported` (the import's only write path, whose
     rules nothing here can relax), the owner establishing the imported
     structure (`establish_structural`, O5: Conversations, Topics and
     Participants, and nothing else, ever), and one `import-applied` act by
     the owner recording what was done.

A failure inside 4 rolls the transaction back, and the bytes it newly put
are removed again, so the Brain is as it was (the backup, outside it, is
kept).

THE `import-applied` ACT is the record of the import (§3, O3, O4, O7). Its
detail carries the manifest sha256; the origin's corpus_id and fork_id;
counts; every row added as (id, fingerprint, origin_seq, origin_hash), with
the door's rewrites; the participant map; the answers kept here against
those shown from there; every row skipped and every conflict; and, for each
Conversation it touched, the whole Turn numbering before and after, so a
"#n" written before the import still resolves to the Turn it meant.
"""

from __future__ import annotations

import collections
import os

from mentis.conversation import CONVERSATION, IN_CONVERSATION, PARTICIPANT
from mentis.spine import brainlock, held
from mentis.spine.imported import (STRUCTURAL_KINDS, ImportRefused,
                                   establish_structural)

from . import ExchangeRefused, format as fmt
from ._rows import one_read
from ._select import IDENTICAL, select
from .identity import identity_from
from .preview import IMPORT_APPLIED, classify


class ImportFailed(RuntimeError):
    """The apply failed inside its transaction; nothing was written."""


# -- nobody else may be writing ---------------------------------------------------

def _alone(root) -> brainlock.Lock:
    """Refuse while Mentis serves this Brain or anything else has it open,
    and hold the SERVE lock for the whole apply, so no server starts over it
    meanwhile. REFUSED RATHER THAN WAITED FOR, the safer of the two (review
    ent-cca01f8347bb, finding 3): a served Brain has agents running over it
    that would read the import half-arrived, and a wait would end in an
    import landing under work the owner left running. The transaction below
    serialises against any writer regardless; this keeps the owner from
    importing under live work at all."""
    serve = brainlock._take(root, brainlock.SERVE_LOCK, False)
    if serve is None:
        who = brainlock.serving(root) or {}
        raise ExchangeRefused(
            f"Mentis is serving the Brain at {root}"
            + (f" (pid {who.get('pid')}, port {who.get('port')})"
               if who else "")
            + ". Stop Mentis first, then import; nothing was written")
    if brainlock.is_open(root):
        serve.release()
        raise ExchangeRefused(
            f"the Brain at {root} is open elsewhere (a Mentis worker, a CLI "
            f"or another program). Stop it first, then import; nothing was "
            f"written")
    return serve


# -- reading this Brain ----------------------------------------------------------

def _owner(reader) -> str:
    """This Brain's owner, as the baseline identifies them (the first
    Participant row about the owner, as `wakecheck._owner` and the installer
    read it), else the direct human act."""
    from mentis.bootstrap.baseline import OWNER_ABOUT
    row = reader.conn.execute(
        "SELECT id FROM entry WHERE def_name = 'participant' "
        "AND family = 'entry' AND link_relation IS NULL "
        "AND json_extract(body, '$.about') = ? ORDER BY seq LIMIT 1",
        (OWNER_ABOUT,)).fetchone()
    return row[0] if row else "human"


def _already_applied(store, sha) -> dict | None:
    got = store.operational(act=IMPORT_APPLIED,
                            detail_is={"manifest_sha256": sha}, limit=1)
    return got[0] if got else None


def numbering(store, conversation) -> list[dict]:
    """The Conversation's Turns as `Conversations.turns` numbers them: its
    Contributions sorted by `recorded_at`, stably over write order. Read
    through the store, so inside a write it sees that write's own rows."""
    rows = store._rows(
        "SELECT e.id, e.recorded_at FROM entry l JOIN entry e "
        "ON e.id = l.link_from WHERE l.link_relation = ? AND l.link_to = ? "
        "AND e.def_name = 'contribution' AND e.family = 'entry' "
        "AND e.link_relation IS NULL ORDER BY e.seq",
        (IN_CONVERSATION, conversation))
    seen, turns = set(), []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            turns.append((r[0], r[1]))
    turns.sort(key=lambda t: t[1])
    return [{"turn": t, "number": i} for i, (t, _) in enumerate(turns,
                                                                  start=1)]


# -- deciding what is written ---------------------------------------------------

def _mapped(row, kinds) -> dict:
    """The row written against this Brain's version of its Kind or Relation,
    where the identical body is held here under another version number."""
    d = row.get("definition") or {}
    here = kinds.get((d.get("name"), d.get("version")))
    if here is None or here == d.get("version"):
        return row
    out = {**row, "definition": {**d, "version": here}}
    if row.get("link"):
        out["link"] = {**row["link"], "relation_version": here}
    return out


def _record_row(row) -> dict:
    """A row as the door is handed it: the record, without the evidence of
    its place on the origin's chain."""
    return {k: v for k, v in row.items() if k not in fmt.EVIDENCE_FIELDS}


def _participant_map(plan, export, sel, sup) -> list:
    versions = {e["link"]["from"] for e in export.entries
                if (e.get("link") or {}).get("relation") == sup}
    types = collections.defaultdict(set)
    for c in plan.conflicts:
        if c.type in ("unresolved-name", "name-refused"):
            types[c.subject].add(c.type)
    out = []
    for e in export.entries:
        if ((e.get("definition") or {}).get("name") != PARTICIPANT
                or e.get("link") or e["id"] in versions):
            continue
        pid, p = e["id"], plan.row(e["id"])
        if p is not None and p.state == IDENTICAL:
            how, here = "the same Participant, already here", pid
        elif pid in sel.send:
            how, here = "new here, created by this import", pid
        elif "unresolved-name" in types.get(pid, ()):
            how, here = "unresolved: the owner has not said who this is", None
        elif "name-refused" in types.get(pid, ()):
            how, here = "refused: its name is not one allowed here", None
        else:
            how, here = f"not applied: {sel.skipped.get(pid)}", None
        out.append({"there": pid, "here": here,
                    "alias": (e.get("body") or {}).get("alias"), "how": how})
    return out


def _answers(plan) -> list:
    return [{"question": c.detail.get("question"),
             "kept_here": c.detail.get("here"),
             "shown_from_there": c.detail.get("there"),
             "here_answer": c.detail.get("here_answer"),
             "there_answer": c.detail.get("there_answer")}
            for c in plan.conflicts if c.type == "answered-both"]


# -- apply ------------------------------------------------------------------------

def apply(brain: str, zip_path: str, *, backup_dest: str | None = None) -> dict:
    """Apply the conflict-free part of the export at `zip_path` to the Brain
    at `brain`. Returns what was done, in the words and data the
    `import-applied` act records. Raises `ExchangeRefused` with nothing
    written, or `ImportFailed` when the transaction failed and was undone."""
    import mentis.api as api
    from mentis.spine import backup as _backup
    root = os.path.abspath(brain)
    x = fmt.read(os.path.abspath(zip_path))
    alone = _alone(root)
    try:
        c = api.open_corpus(root, access="write")
        try:
            return _apply(c, root, x, backup_dest, _backup)
        finally:
            c.close()
    finally:
        alone.release()


def _already(was, x) -> dict:
    return {"applied": False, "already": was["id"],
            "manifest_sha256": x.manifest_sha256,
            "words": f"already applied by {was['id']}; nothing was written"}


def _refused(plan):
    if plan.refused:
        raise ExchangeRefused(" ".join(plan.refused))


def _writing(c, plan, x, root):
    """From a Plan, what the transaction writes: the settled selection, the
    held bytes it needs, the rows as the door is handed them, the
    Conversations whose numbering they touch, the structure the owner
    establishes, and the rows mapped to this Brain's Kind versions. Inside
    the write, every read here goes through the writer's connection."""
    st = c._store
    with one_read(st) as r:
        sel, blobs = select(r, plan.rows, plan.conflicts, x, root, store=st)
    kinds = {(k["name"], k["version"]): k["here_version"]
             for k in plan.kinds if k.get("here_version") is not None}
    entries = [_mapped(_record_row(e), kinds) for e in x.entries
               if e["id"] in sel.send]
    acts = [_record_row(a) for a in x.acts if a["id"] in sel.send]
    touched = sorted(
        {e["link"]["to"] for e in entries
         if (e.get("link") or {}).get("relation") == IN_CONVERSATION}
        | {e["id"] for e in entries if not e.get("link")
           and (e.get("definition") or {}).get("name") == CONVERSATION})
    sup = c.superseding_relation()
    versions = {e["link"]["from"] for e in entries
                if (e.get("link") or {}).get("relation") == sup}
    structural = [e["id"] for e in entries if not e.get("link")
                  and e.get("family") == "entry"
                  and (e.get("definition") or {}).get("name")
                  in STRUCTURAL_KINDS and e["id"] not in versions]
    mapped = {e["id"]: e["definition"]["version"] for e in entries
              if (e.get("definition") or {}).get("version")
              != ((sel.rows[e["id"]].get("definition") or {})
                  .get("version"))}
    return sel, blobs, entries, acts, touched, sup, structural, mapped


def _apply(c, root, x, backup_dest, _backup) -> dict:
    st = c._store
    with one_read(st) as r:
        me = identity_from(r)
        owner = _owner(r)
    origin = x.origin
    if origin.get("fork_id") == me["fork_id"]:
        raise ExchangeRefused(
            f"this file was exported from this Brain's own fork "
            f"({me['fork_id']}); importing it would import this Brain "
            f"into itself")
    was = _already_applied(st, x.manifest_sha256)
    if was is not None:
        return _already(was, x)
    # a first Plan, so a file refused whole is refused before the backup
    _refused(classify(c, x))

    # 3. a verified backup, before anything is written
    made = _backup.backup(root, dest=backup_dest)
    checked = _backup.verify_backup(made["backup"], brain=root)
    if not checked.get("usable"):
        raise ExchangeRefused(f"the backup taken first ({made['path']}) "
                              f"is not usable, so nothing was imported: "
                              f"{checked}")

    put = []
    try:
        # 4 and 5, UNDER THE WRITE LOCK (review ent-cca01f8347bb, finding
        # 3). The Plan and the selection are made again INSIDE the
        # transaction that appends: BEGIN IMMEDIATE holds every other
        # writer out from here to the commit, so nothing written since the
        # first Plan -- during the backup, by anybody -- can slip past the
        # diverged-line and answer checks.
        with c.atomic():
            was = _already_applied(st, x.manifest_sha256)
            if was is not None:
                return _already(was, x)
            plan = classify(c, x)
            _refused(plan)
            (sel, blobs, entries, acts, touched, sup, structural,
             mapped) = _writing(c, plan, x, root)
            # bytes before the records that name them
            for digest, data in sorted(blobs.items()):
                got, new = held.put(root, data)
                if got != digest:
                    raise ImportFailed(f"held bytes {digest[:12]} did not "
                                       f"hash to their name")
                if new:
                    put.append(digest)
            before = {cid: numbering(st, cid) for cid in touched}
            wrote = st.append_imported(entries, acts)
            est = (establish_structural(
                c, structural, owner=owner,
                because="imported structure, established here by its "
                        "owner") if structural else
                {"act": None, "established": {}, "already": []})
            after = {cid: numbering(st, cid) for cid in touched}
            detail = _detail(plan, x, sel, wrote, est, before, after,
                             put, owner, sup, mapped, st)
            act = c.record_operational(
                actor=owner, act=IMPORT_APPLIED,
                because=f"imported the conflict-free part of "
                        f"{os.path.basename(x.path)}",
                about=[m["id"] for m in x.manifest.get("marks") or ()
                       if m.get("id") in sel.send or m.get("id")
                       in sel.here],
                detail=detail)
    except BaseException as exc:
        for digest in put:
            _unput(root, digest)
        if isinstance(exc, ImportRefused):
            raise ExchangeRefused(str(exc)) from exc
        if isinstance(exc, (ImportFailed, ExchangeRefused,
                            KeyboardInterrupt)):
            raise
        raise ImportFailed(f"the import failed and was undone; nothing "
                           f"was written: {type(exc).__name__}: {exc}"
                           ) from exc
    return {"applied": True, "act": act, "backup": made["backup"],
            "structural_act": est["act"], **detail}


def _unput(root, digest):
    p = held.path(root, digest)
    try:
        os.remove(p)
        os.rmdir(p.parent)
    except OSError:
        pass


def _detail(plan, x, sel, wrote, est, before, after, put, owner,
            sup, mapped, st) -> dict:
    fps = {p.id: p.fingerprint for p in plan.rows}
    rows = []
    # A ROW WRITTEN HERE AS OTHER THAN IT ARRIVED -- a supersession the door
    # wrote as a proposal, a row mapped to this Brain's version of an
    # identical Kind -- records how it was written and the fingerprint of
    # the row as written, beside the fingerprint it arrived with, so a later
    # file carrying the origin's row reads it as already here and not as
    # damage (`preview._Classifier._rewritten`, ent-4b4f11a83d1d).
    written_as = {rid: f"definition version {v}" for rid, v in mapped.items()}
    written_as.update({r["id"]: r["written_as"]
                       for r in wrote.get("rewritten") or ()})
    with one_read(st) as r:
        here = r.entries(written_as)
    for table, rid_list in (("entry", wrote["entries"]),
                            ("act", wrote["acts"])):
        for rid in rid_list:
            row = sel.rows[rid]
            rows.append({"id": rid, "table": table,
                         "fingerprint": fps.get(rid),
                         "origin_seq": row.get("origin_seq"),
                         "origin_hash": row.get("origin_hash"),
                         **({"written_as": written_as[rid],
                             "written_fingerprint": fmt.fingerprint(
                                 here[rid])}
                            if rid in written_as and rid in here else {})})
    skipped = [{"id": rid, "table": ("act" if fmt.is_act(sel.rows[rid])
                                     else "entry"),
                "kind": (plan.row(rid).kind if plan.row(rid) else None),
                "why": why}
               for rid, why in sorted(sel.skipped.items())]
    numbering_ = {}
    for cid in sorted(after):
        b = {t["turn"]: t["number"] for t in before.get(cid, [])}
        moved = [{"turn": t["turn"], "before": b[t["turn"]],
                  "after": t["number"]}
                 for t in after[cid]
                 if t["turn"] in b and b[t["turn"]] != t["number"]]
        numbering_[cid] = {"before": before.get(cid, []), "after": after[cid],
                           "renumbered": moved}
    by_kind = collections.Counter(
        (plan.row(r["id"]).kind if plan.row(r["id"]) else None) for r in rows)
    return {
        "manifest_sha256": x.manifest_sha256,
        "origin": {"corpus_id": x.origin.get("corpus_id"),
                   "fork_id": x.origin.get("fork_id")},
        "by": owner,
        "counts": {"entries": len(wrote["entries"]),
                   "acts": len(wrote["acts"]),
                   "by_kind": {str(k): v for k, v in sorted(
                       by_kind.items(), key=lambda kv: str(kv[0]))},
                   "already_here": sum(1 for p in plan.rows
                                       if p.state == IDENTICAL),
                   "skipped": len(skipped), "conflicts": len(plan.conflicts),
                   "blobs_written": len(put),
                   "established": len(est["established"])},
        "rows": rows,
        "rewritten": list(wrote.get("rewritten") or ()),
        "skipped": skipped,
        "conflicts": [{"id": c.id, "type": c.type, "subject": c.subject,
                       "words": c.words} for c in plan.conflicts],
        "participants": _participant_map(plan, x, sel, sup),
        "answers": _answers(plan),
        "numbering": numbering_,
        "established": est["established"],
        "established_by": est["act"],
    }


def describe(out: dict) -> str:
    """What an apply did, in plain language."""
    if not out.get("applied"):
        return f"Import: {out['words']}."
    n = out["counts"]
    lines = [f"Import applied ({out['act']}), after a verified backup at "
             f"{out['backup']}.",
             f"Added: {n['entries']} entries and {n['acts']} acts"
             + (" (" + ", ".join(f"{v} {k}" for k, v in n["by_kind"].items())
                + ")" if n["by_kind"] else "") + f"; {n['already_here']} were "
             f"already here."]
    if n["established"]:
        lines.append(f"Established here by the owner: {n['established']} "
                     f"Conversation(s), Topic(s) or Participant(s). Nothing "
                     f"else imported stands until it is established here.")
    for cid, m in out["numbering"].items():
        if m["renumbered"]:
            lines.append(f"Renumbered in {cid}: " + ", ".join(
                f"#{x['before']} -> #{x['after']}" for x in m["renumbered"]))
    for a in out["answers"]:
        lines.append(f"Question {a['question']}: this Brain's answer is kept; "
                     f"the other machine's ({a['shown_from_there']}) is "
                     f"shown, not written.")
    if out["skipped"]:
        lines.append(f"Not applied ({len(out['skipped'])}):")
        for s in out["skipped"]:
            lines.append(f"  - {s['id']} ({s['kind']}): {s['why']}")
    else:
        lines.append("Not applied: nothing.")
    return "\n".join(lines)
