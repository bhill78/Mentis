"""Reading acquired sources back: discover, history, links, bounded pages.

THE SANCTIONED SOURCE CAPABILITY (Turn 19, option 1; Turn 29, C). Every
dispatched agent gets these, as reads, over every acquired collection in the
corpus. Said exactly, because it would be easy to say more:

  * They read the RECORD: Admissions and the bytes the corpus holds. They
    never touch a bound folder, so they work identically when a collection
    is unbound, rebound, or its folder is gone.
  * They reach Bulk Source acquisitions and nothing else. An Admission from
    any other door -- a returned or submitted artifact -- is refused here and
    stays under `read_artifact`'s reach rules.
  * They are NOT authorised per read by Governance, and nothing here claims
    they are. There are no collection ACLs and no per-agent grants: holding a
    worker grant at all is what admits them, like every other read.
  * They are not recorded as acts, like `resolve`.
  * A SCRATCH ANSWER HOLDS THEM TOO, BY ITS OWN OWNER DECISION
    (opr-9fa00d2183a9: "Quick Ask can quote acquired files and held
    artifacts. Its reads stay unrecorded, as all Quick Ask reads are."). It
    was decided separately because "every dispatched agent" does not include
    a Quick Ask, whose runtime is launched with `--tools ""`, so for it these
    are a new power rather than a formalisation of its own tools. Its reads
    are unrecorded by design, which these are for every reader anyway. See
    `mentis.worker.SOURCE_READS` and `permitted`. What it saw before that
    decision, by an earlier ruling (#66, ent-c36debac8263), it still sees:
    the names -- `find`'s acquired hits and `resolve`'s provenance of an
    `adm-` (`provenance` below).
  * AN ACQUIRED IMAGE IS ALSO SERVED BY `read_artifact` (Sources B, B1), so a
    model can look at it: base64 pages are bytes nobody sees. Its reach there
    is exactly this module's -- `mentis.artifacts.acquired_reach`.

EVERY CONNECTOR, ROUTED BY ITS DECLARATION (Sources slice 1, B2). Where a
collection's Admissions are recorded (`<connector>:<col>`), and how an object
key is normalised and labelled, are asked of the declaration's connector
(`mentis.sources.registry`), never assumed to be a folder's.

Pages are bounded (`PAGE_BYTES`), verified against the digest before any
byte is served, and cite the Admission, the digest and the exact byte range.
"""

from __future__ import annotations

import base64
import difflib
import json

from mentis.sources import (PRODUCED, SWEPT, Refused, declarations,
                            effective_scope, latest, observation, revisions,
                            source_id)
from mentis.sources import registry
from mentis.spine import held

#: The largest page served in one answer. A page is a window, not the file.
PAGE_BYTES = 64 * 1024

#: Bounded listings, like every other worker read.
LIST = 200

#: WHAT A LINK'S TARGET IS, read from the record now and never from the live
#: source (G2). Each relation gets exactly one. They used to collapse into
#: "not acquired", which hid the difference between a target the scope left
#: out, one a sweep could not take, one recorded gone, and one that is not in
#: the collection at all -- the four things a person deciding what to do
#: about it needs told apart.
ACQUIRED = "acquired"
OUTSIDE_SCOPE = "not acquired · outside scope"
WITHHELD = "not acquired · withheld"
ABSENT = "recorded absent"
OUTSIDE_COLLECTION = "outside collection"
#: Not in the spec's five, and needed: an in-scope target that no sweep has
#: recorded and none withheld -- a link to a file that is not there, most
#: often. Saying "outside scope" or "withheld" of it would be untrue.
NOT_OBSERVED = "not acquired · not observed"
NOT_RESOLVED = "not resolved"
SAME_DOCUMENT = "same document"


def _label(decl_or_conn, key, o=None) -> str:
    conn = decl_or_conn if isinstance(decl_or_conn, str) \
        else decl_or_conn["connector"]
    try:
        return registry.label(conn, key, o)
    except Refused:
        return key


def _summary(e: dict, connector: str | None = None) -> dict:
    o = observation(e)
    key = o.get("object")
    return {"ref": e["id"], "path": key, "key": key,
            "label": _label(connector or o.get("connector") or "", key, o),
            "state": o.get("state"),
            "action": o.get("action"), "digest": o.get("digest"),
            "size": o.get("size"), "payload_type": o.get("payload_type"),
            "text": (o.get("encoding") or {}).get("text"),
            "batch": o.get("batch"), "admitted_at": e["body"].get("admitted_at")}


def _source(decl) -> str:
    return source_id(decl["connector"], decl["collection"])


def _latest(corpus, decl) -> dict[str, dict]:
    return latest(corpus, _source(decl))


def _key(decl, path) -> str:
    try:
        return registry.normalise(decl["connector"], path)
    except Refused:
        return str(path or "").strip()


def _sweeps(corpus, collection) -> list[dict]:
    return [a for a in corpus.operational(act=SWEPT)
            if a["detail"].get("collection") == collection]


def collections(corpus) -> dict:
    out = []
    for d in declarations(corpus):
        lat = _latest(corpus, d)
        present = sum(1 for e in lat.values()
                      if observation(e).get("state") == "present")
        eff = effective_scope(corpus, d["collection"], d)
        out.append({"collection": d["collection"], "name": d["name"],
                    "connector": d["connector"],
                    "declared_by": d["declared_by"],
                    "declared_at": d["declared_at"],
                    # THE SCOPE IN FORCE. Revisable (owner decision 1), so
                    # the declaration's own filters are no longer the answer.
                    "include": eff["include"], "exclude": eff["exclude"],
                    # A CONNECTOR'S OWN SCOPE FIELDS (a Git ref and commit
                    # window), said only where it has some.
                    **({"options": eff["options"]} if eff["options"]
                       else {}),
                    "scope_revised": eff["revision"] is not None,
                    "objects_present": present,
                    "objects_absent": len(lat) - present})
    return {"collections": out,
            "note": "acquired material as recorded. Whether a collection is "
                    "bound on any machine is not part of the record."}


def _collection(corpus, collection: str) -> dict:
    """By id, or by a name exactly one declaration carries."""
    decls = declarations(corpus)
    hit = [d for d in decls if d["collection"] == collection]
    if not hit:
        hit = [d for d in decls if d["name"] == collection]
    if len(hit) != 1:
        raise Refused(f"{collection!r} names {len(hit)} collections; give "
                      "its id (col-...)")
    return hit[0]


def overview(corpus, collection: str, *, decl: dict | None = None,
             lat: dict[str, dict] | None = None) -> dict:
    """One collection as recorded, for the owner's page: scope in force and
    its revisions, counts, links, held bytes and every sweep.

    `decl` and `lat` are what a caller already read IN THIS REQUEST -- the
    declaration and its latest Admissions -- passed so the source's history
    is read once, not once per consumer (opr-1f9237698d13: the overview list
    read it three times per collection). Never cached across requests: each
    call that is not handed them reads the record as it stands now."""
    d = decl if decl is not None else _collection(corpus, collection)
    if lat is None:
        lat = _latest(corpus, d)
    present = [observation(e) for e in lat.values()
               if observation(e).get("state") == "present"]
    rels = [r for o in present for r in o.get("relations") or ()]
    sweeps = _sweeps(corpus, d["collection"])
    eff = effective_scope(corpus, d["collection"], d)
    last = sweeps[-1] if sweeps else None
    return {
        "collection": d["collection"], "name": d["name"],
        "connector": d["connector"], "declared_by": d["declared_by"],
        "declared_at": d["declared_at"], "declaration": d["declaration"],
        "declared_scope": {"include": d.get("include"),
                           "exclude": d.get("exclude"),
                           **({"options": d["options"]} if d.get("options")
                              else {})},
        "scope": eff,
        "revisions": revisions(corpus, d["collection"]),
        "counts": {"present": len(present),
                   "absent": len(lat) - len(present),
                   "links_to": sum(1 for r in rels if r["rel"] == "links-to"),
                   "embeds": sum(1 for r in rels if r["rel"] == "embeds"),
                   "held_bytes": sum(o.get("size") or 0 for o in present),
                   "visible_not_selected": (last["detail"].get(
                       "visible_not_selected") if last else None)},
        "last_sweep": _sweep_row(last) if last else None,
        "sweeps": [_sweep_row(a) for a in reversed(sweeps)],
        "note": "past observations held here, not the live source",
    }


def _sweep_row(a) -> dict:
    det = a["detail"]
    return {"act": a["id"], "at": a["at"], "actor": a.get("actor"),
            "batch": det.get("batch"), "plan": det.get("plan"),
            "counts": det.get("counts"), "scope": det.get("scope"),
            "binding": det.get("binding"),
            "binding_changed": det.get("binding_changed"),
            "not_acquired": det.get("not_acquired") or [],
            "refused": det.get("refused") or [],
            "unexamined": det.get("unexamined") or [],
            "visible_not_selected": det.get("visible_not_selected")}


def objects(corpus, collection: str, *, q: str | None = None,
            state: str | None = "present", offset: int = 0,
            limit: int = LIST, prefix: str | None = None) -> dict:
    """The latest observation of each object, filtered by key or label.

    Summaries are built only for the requested page."""
    d = _collection(corpus, collection)
    conn = d["connector"]
    limit = max(1, min(int(limit or LIST), LIST))
    offset = max(0, int(offset or 0))

    lat = _latest(corpus, d)
    ql = q.lower() if q else None

    if prefix is not None:
        pfx_norm = str(prefix or "").replace("\\", "/").strip("/")
        pfx_slash = (pfx_norm + "/") if pfx_norm else ""
        folder_counts: dict[str, int] = {}
        child_entries: list[tuple[str, dict]] = []

        for key, e in lat.items():
            obs = observation(e)
            if state and obs.get("state") != state:
                continue
            if ql:
                if ql not in key.lower():
                    lbl = _label(conn or obs.get("connector") or "", key, obs)
                    if ql not in (lbl or "").lower():
                        continue

            if pfx_slash:
                if not key.startswith(pfx_slash):
                    continue
                rel = key[len(pfx_slash):]
            else:
                rel = key

            slash_idx = rel.find("/")
            if slash_idx != -1:
                folder_name = rel[:slash_idx]
                folder_counts[folder_name] = folder_counts.get(folder_name, 0) + 1
            else:
                child_entries.append((key, e))

        child_entries.sort(key=lambda item: item[0])
        matched = len(child_entries)
        page_slice = child_entries[offset:offset + limit]
        page_objects = [_summary(e, conn) for _, e in page_slice]
        next_offset = offset + limit if offset + limit < matched else None

        folders = [
            {"name": name,
             "path": f"{pfx_norm}/{name}" if pfx_norm else name,
             "count": count}
            for name, count in sorted(folder_counts.items(), key=lambda x: x[0])
        ]
        return {
            "collection": d["collection"],
            "name": d["name"],
            "connector": conn,
            "prefix": pfx_norm,
            "folders": folders,
            "objects": page_objects,
            "matched": matched,
            "next_offset": next_offset,
        }

    matched_entries: list[tuple[str, dict]] = []
    for key, e in lat.items():
        obs = observation(e)
        if state and obs.get("state") != state:
            continue
        if ql:
            if ql not in key.lower():
                lbl = _label(conn or obs.get("connector") or "", key, obs)
                if ql not in (lbl or "").lower():
                    continue
        matched_entries.append((key, e))

    matched_entries.sort(key=lambda item: item[0])
    matched = len(matched_entries)
    page_slice = matched_entries[offset:offset + limit]
    page_objects = [_summary(e, conn) for _, e in page_slice]
    next_offset = offset + limit if offset + limit < matched else None

    return {
        "collection": d["collection"],
        "name": d["name"],
        "connector": conn,
        "objects": page_objects,
        "matched": matched,
        "next_offset": next_offset,
    }


def history(corpus, collection: str, path: str) -> dict:
    """Every recorded observation of one object, in append order."""
    d = _collection(corpus, collection)
    path = _key(d, path)
    rows = [_summary(e, d["connector"])
            for e in corpus.admissions_from(_source(d))
            if observation(e).get("object") == path]
    if not rows:
        return {"collection": d["collection"], "path": path, "known": False,
                "why_not": "no observation of that path is recorded"}
    return {"collection": d["collection"], "path": path,
            "label": _label(d, path), "known": True,
            "observations": rows,
            "note": "each is a past observation, not the live file"}


def _withheld_reasons(corpus, collection):
    """A function: key -> the reason the latest sweep that examined it
    recorded for not acquiring it, or None. From the sweep acts' own detail,
    newest first: a sweep whose area covered the key and did not withhold it
    ends the search, because that sweep saw it otherwise."""
    sweeps = []
    for a in reversed(_sweeps(corpus, collection)):
        det = a["detail"]
        within = (det.get("scope") or {}).get("within")
        why = {r["path"]: r["reason"] for r in det.get("not_acquired") or ()}
        why.update({r["path"]: r["reason"] for r in det.get("refused") or ()
                    if r.get("path") not in why})
        sweeps.append((within, why))

    def reason(key):
        for within, why in sweeps:
            if key in why:
                return why[key]
            if not within or key == within or key.startswith(within + "/"):
                return None
        return None
    return reason


def _target_status(corpus, d, lat):
    """A function: recorded relation -> what its target is (G2), against
    `lat`, the observation of each key that counts. Shared by `links` and
    `rendered`, so a note's embeds are said the same way in both."""
    eff = effective_scope(corpus, d["collection"], d)
    reason = _withheld_reasons(corpus, d["collection"])
    try:
        mod = registry._module(d["connector"])
        in_scope = lambda k: mod.selected(eff, k)          # noqa: E731
    except Refused:
        in_scope = lambda k: True                          # noqa: E731

    def status(r) -> dict:
        res = r.get("resolution")
        k = r.get("resolved")
        if res == "in-collection" and k:
            e = lat.get(k)
            if e is not None and observation(e).get("state") == "present":
                return {"target": ACQUIRED, "target_ref": e["id"],
                        "in_scope": in_scope(k)}
            if e is not None:
                return {"target": ABSENT, "target_ref": e["id"],
                        "in_scope": in_scope(k)}
            if not in_scope(k):
                return {"target": OUTSIDE_SCOPE, "in_scope": False}
            why = reason(k)
            if why:
                return {"target": WITHHELD, "reason": why, "in_scope": True}
            return {"target": NOT_OBSERVED, "in_scope": True}
        if res in ("outside-collection", "absolute", "external"):
            return {"target": OUTSIDE_COLLECTION}
        if res == "same-document":
            return {"target": SAME_DOCUMENT}
        return {"target": NOT_RESOLVED}
    return status


#: H8/U7: how a `same-content` relation between a HEAD file and a retained
#: Git blob is now known. It is not recorded on either observation.
SAME_CONTENT_BASIS = ("derived when read, against the observation read: a "
                      "HEAD file's recorded blob id is the blob's id and both "
                      "hold this observation's digest; the other side is "
                      "taken from the latest recorded observations; not "
                      "recorded as a relation, and true of the record now, "
                      "not of the live repository")


def _may_have_same_content(o: dict) -> bool:
    """Whether an observation can have a same-content answer at all: a
    present retained blob, or a present HEAD file with a recorded blob id.
    Commits, trees, change records and renames never do."""
    from mentis.sources.git import is_blob_key, is_git_internal_key
    key = str(o.get("object") or "")
    return (o.get("state") == "present"
            and (is_blob_key(key)
                 or (not is_git_internal_key(key)
                     and bool((o.get("native") or {}).get("blob")))))


def same_content(lat: dict, key: str) -> list[dict] | None:
    """Which observations in this collection hold the same retained bytes as
    the latest observation of `key` (H8/U7); see `_same_content`."""
    e = lat.get(key)
    return _same_content(lat, observation(e) if e else {})


def _same_content(lat: dict, o: dict) -> list[dict] | None:
    """Which observations in this collection hold the same retained bytes as
    the observation `o` -- the one being read, historical or latest. It is
    never replaced by whatever is latest at `o`'s key.

    For a retained blob (`.git/blobs/<id>`): every acquired HEAD file whose
    latest observation is present, records `native.blob == <id>` and holds
    `o`'s digest. For a HEAD file: the retained blob of `o`'s OWN recorded
    blob id, when that is held with `o`'s digest. The two stay distinct
    observations with their own identity and provenance; this only says
    they share held bytes. None when `o` is neither."""
    from mentis.sources.git import BLOBS, is_git_internal_key
    if not _may_have_same_content(o):
        return None
    key = o["object"]
    digest = o.get("digest")
    if key.startswith(BLOBS):
        blob = key[len(BLOBS):]
        hits = [(p, pe) for p, pe in sorted(lat.items())
                if not is_git_internal_key(p)]
    else:
        blob = o["native"]["blob"]
        hits = [(BLOBS + blob, lat.get(BLOBS + blob))]
    out = []
    for p, pe in hits:
        po = observation(pe) if pe else {}
        if (po.get("state") == "present" and po.get("digest") == digest
                and (p.startswith(BLOBS)
                     or (po.get("native") or {}).get("blob") == blob)):
            out.append({"rel": "same-content", "path": p, "ref": pe["id"],
                        "blob": blob, "digest": digest, "derived": True,
                        "basis": SAME_CONTENT_BASIS})
    return out


def _recorded_same_content(lat: dict, blob_key: str, r: dict) -> dict:
    """A `same-content` relation an earlier candidate sweep RECORDED on a
    blob observation. It is passed on as recorded, labelled as of its sweep,
    with whether the record still bears it out now."""
    from mentis.sources.git import BLOBS
    e = lat.get(r.get("resolved") or "")
    o = observation(e) if e else {}
    b = lat.get(blob_key)
    holds = (o.get("state") == "present"
             and (o.get("native") or {}).get("blob") == blob_key[len(BLOBS):]
             and b is not None
             and o.get("digest") == observation(b).get("digest"))
    return {"recorded_as_of_its_sweep": True, "holds_now": holds,
            "note": "recorded by an earlier sweep from that sweep's HEAD; "
                    "the derived same-content answer is the current one"}


def links(corpus, collection: str, path: str, *, ref: str | None = None) -> dict:
    """Links out of the latest observation, as authored and as resolved, and
    links into this path from the latest observations of the collection.

    WHAT EACH TARGET IS, FROM THE RECORD ONLY (G2): acquired (with its
    Admission), not acquired because the scope in force leaves it out, not
    acquired because a sweep withheld it (with the reason that sweep
    recorded), recorded absent, or outside the collection. Whether it is in
    scope is computed now from the effective scope -- it is no longer part of
    the recorded relation (`markdown-links/2`). Nothing here consults the
    live folder; being linked to, or being in the folder, never makes a
    target acquired."""
    d = _collection(corpus, collection)
    path = _key(d, path)
    if ref is not None:
        me = _bulk_admission(corpus, ref)
        own = observation(me)
        if own.get("collection") != collection or own.get("object") != path:
            raise Refused("capture-time reference must name this collection and key")
        lat = _captured_latest(corpus, d, own.get("batch"))
        out_links = []
        for rel in own.get("relations") or []:
            target = lat.get(rel.get("resolved"))
            state = observation(target).get("state") if target else None
            out_links.append({**rel, "target": ACQUIRED if state == "present" else
                              ABSENT if state == "absent" else NOT_OBSERVED if rel.get("resolved") else NOT_RESOLVED,
                              "target_ref": target["id"] if target else None})
        inbound = [{"from": key, "label": _label(d, key, observation(entry)), "ref": entry["id"],
                    "rel": rel["rel"], "authored": rel.get("authored", "")}
                   for key, entry in sorted(lat.items()) if observation(entry).get("state") == "present"
                   for rel in observation(entry).get("relations") or [] if rel.get("resolved") == path]
        return {"collection": collection, "path": path, "label": _label(d, path),
                "ref": ref, "state": "acquired" if own.get("state") == "present" else "recorded absent",
                "links": out_links, "linked_from": inbound, "projection": "capture-time",
                "batch": own.get("batch"), "note": "targets as recorded by the end of this capture batch; never the live source"}
    lat = _latest(corpus, d)
    status = _target_status(corpus, d, lat)

    def acquired(p):
        e = lat.get(p)
        if e is None:
            return "not acquired"
        return ("acquired" if observation(e).get("state") == "present"
                else "recorded absent")

    me = lat.get(path)
    out_links = []
    for r in (observation(me).get("relations") or []) if me else []:
        r = dict(r)
        # A RELATION RECORDED UNDER `markdown-links/1` CARRIED `in_scope` AS
        # OF ITS SWEEP. It is not passed on as though it were current.
        r.pop("in_scope", None)
        r.update(status(r))
        if r.get("rel") == "same-content":
            r.update(_recorded_same_content(lat, path, r))
        out_links.append(r)
    inbound = []
    for p, e in sorted(lat.items()):
        o = observation(e)
        if o.get("state") != "present":
            continue
        for r in o.get("relations") or []:
            if r.get("resolved") == path:
                inbound.append({"from": p, "label": _label(d, p, o),
                                "ref": e["id"], "rel": r["rel"],
                                "authored": r["authored"],
                                **(_recorded_same_content(lat, p, r)
                                   if r["rel"] == "same-content" else {})})
    # H8/U7: same-content is derived from the record, in both directions.
    for x in (same_content(lat, path) or ()) if d["connector"] == "git" else ():
        out_links.append({"rel": x["rel"], "resolved": x["path"],
                          "target": "acquired", "ref": x["ref"],
                          "blob": x["blob"], "derived": True,
                          "basis": x["basis"]})
        inbound.append({"from": x["path"], "label": _label(d, x["path"]),
                        "ref": x["ref"], "rel": x["rel"], "derived": True,
                        "basis": x["basis"]})
    return {"collection": d["collection"], "path": path,
            "label": _label(d, path),
            "ref": me["id"] if me else None, "state": acquired(path),
            "links": out_links, "linked_from": inbound,
            "note": "statuses are read from the record, never the live "
                    "source"}


def _captured_latest(corpus, decl, batch):
    """Replay through the last Admission of a capture, in append order."""
    entries = list(corpus.admissions_from(source_id(decl["connector"], decl["collection"])))
    end = max((i for i, e in enumerate(entries) if observation(e).get("batch") == batch), default=-1)
    if end < 0:
        raise Refused("capture batch is not reconstructable from this collection's record")
    return {observation(e)["object"]: e for e in entries[:end + 1]}


def record(corpus, ref: str) -> dict:
    """A bounded field view and schema from the same historical capture."""
    e = _bulk_admission(corpus, ref)
    o = observation(e)
    if o.get("connector") != "sqlite":
        raise Refused("structured record view is for SQLite observations")
    page = _read_admission(corpus, e)
    if page["next_offset"] is not None:
        return {"ref": ref, "bounded": True, "note": "record exceeds the field-view page; use the exact byte reader"}
    payload = json.loads(page["text"])
    decl = _collection(corpus, o["collection"])
    lat = _captured_latest(corpus, decl, o.get("batch"))
    schema_key = o["object"].split("/", 1)[0] + "/@schema"
    schema = lat.get(schema_key)
    return {"ref": ref, "cite": page["cite"], "payload": payload,
            "schema_ref": schema["id"] if schema else None,
            "schema_key": schema_key, "batch": o.get("batch"),
            "note": "lossless typed fields; omitted NULLs are described by the captured schema"}


def _bulk_admission(corpus, ref) -> dict:
    got = corpus.read([ref]) if isinstance(ref, str) and ref else []
    if not got or got[0]["family"] != "admission":
        raise Refused(f"{ref!r} is not an Admission in this corpus")
    e = got[0]
    o = observation(e)
    src = str(e["body"].get("source") or "")
    if not o or not o.get("connector") or not o.get("collection") \
            or src != source_id(o["connector"], o["collection"]):
        raise Refused(f"{ref!r} is not a Bulk Source acquisition; other "
                      "held artifacts are read with read_artifact, under "
                      "its own reach")
    return e


def read(corpus, *, ref: str | None = None, collection: str | None = None,
         path: str | None = None, offset: int = 0,
         length: int = PAGE_BYTES, extraction: str | None = None) -> dict:
    """One bounded page of an acquired object's exact retained bytes.

    By Admission ref (any observation, historical included), or by
    collection and path (the latest observation, which must be present).
    Text -- strict UTF-8 with no NUL -- comes back as text, with the page
    ending on a character boundary; anything else as base64.

    With `extraction` (an extractor id), one bounded window of THAT
    extraction of the source instead (Sources C, C3): offset and length in
    code points of the representation, under exactly the source's own reach
    -- every refusal below is made first."""
    lat = None
    if ref:
        e = _bulk_admission(corpus, ref)
    else:
        if not (collection and path):
            raise Refused("give an Admission ref, or a collection and a path")
        d = _collection(corpus, collection)
        p = _key(d, path)
        lat = _latest(corpus, d)
        e = lat.get(p)
        if e is None:
            raise Refused(f"{p!r} has never been acquired in "
                          f"{d['collection']}")
    return _read_admission(corpus, e, offset=offset, length=length,
                           extraction=extraction, lat=lat)


def _read_admission(corpus, e, *, offset: int = 0, length: int = PAGE_BYTES,
                    extraction: str | None = None,
                    lat: dict | None = None) -> dict:
    """`read` of an Admission already found. `lat` is the collection's
    latest map when the caller has already replayed it; it is not replayed
    again."""
    o = observation(e)
    if o.get("state") != "present" or e["body"].get("content") != "held":
        raise Refused(f"{e['id']} records {o.get('object')!r} as "
                      f"{o.get('state')}; there are no bytes for it. Its "
                      "history may hold earlier acquisitions.")
    if corpus.links(relation=held.PURGED, to=e["id"]):
        raise Refused(f"{e['id']} was purged; its bytes are no longer held")
    digest = held.digest_of(e["body"].get("locator"))
    if extraction is not None:
        return _read_extraction(corpus, e, o, digest, extraction, offset,
                                length)
    st, data = held.state(corpus.root, digest, verify=True)
    if st != "present":
        raise Refused(f"the bytes of {e['id']} are {st}; nothing is served "
                      "that is not what the record committed to")
    size = len(data)
    offset = max(0, int(offset or 0))
    length = max(1, min(int(length or PAGE_BYTES), PAGE_BYTES))
    if offset > size:
        raise Refused(f"offset {offset} is past the end ({size} bytes)")
    text = (o.get("encoding") or {}).get("text")
    if text:
        # A PAGE STARTS AND ENDS ON A CHARACTER: never inside a UTF-8
        # sequence. An offset inside one moves back to its start; the end
        # moves back to a boundary, or forward past one character if the
        # page would otherwise be empty.
        while 0 < offset < size and (data[offset] & 0xC0) == 0x80:
            offset -= 1
    end = min(size, offset + length)
    if text:
        while offset < end < size and (data[end] & 0xC0) == 0x80:
            end -= 1
        if end == offset and end < size:
            end += 1
            while end < size and (data[end] & 0xC0) == 0x80:
                end += 1
    out = {"ref": e["id"], "collection": o.get("collection"),
           "path": o.get("object"), "digest": digest, "size": size,
           "offset": offset}
    if text:
        out["text"] = data[offset:end].decode("utf-8")
        out["encoding"] = "utf-8" + (" (with BOM)" if o["encoding"].get("bom")
                                      == "utf-8" else "")
    else:
        out["bytes_b64"] = base64.b64encode(data[offset:end]).decode("ascii")
        out["encoding"] = "bytes"
    out["end"] = end
    out["next_offset"] = end if end < size else None
    out["cite"] = f"{e['id']}@{digest[:12]}[{out['offset']}:{end}]"
    out["note"] = ("exact retained bytes as acquired, verified against the "
                   "digest; a past observation, not the live file")
    from mentis.sources.git import is_git_internal_key, is_commit_key
    if is_git_internal_key(o.get("object")):
        nature = "author's claim" if is_commit_key(o["object"]) else "change evidence"
        out.update(nature=nature, claim_or_evidence=nature)
    from mentis.sources.git import (CONNECTOR as GIT, BLOB_TYPE, blob_type_of,
                                    is_blob_key)
    if o.get("connector") == GIT:
        recorded, own = o.get("payload_type"), blob_type_of(data)
        if is_blob_key(o.get("object")) and recorded != own:
            # An earlier candidate sweep's type, kept as recorded. Say where
            # it came from, and what the bytes' own type is.
            if recorded == BLOB_TYPE:
                came = ("a fixed Git-blob type an earlier candidate sweep "
                        "gave every retained blob")
            elif text:
                came = ("the filename that selected this blob in an earlier "
                        "candidate sweep (application/octet-stream where "
                        "that name had no known type)")
            else:
                came = ("an earlier candidate sweep, which typed every blob "
                        "whose bytes are not text application/octet-stream "
                        "without reading their signature")
            out["payload_type_note"] = (
                f"payload type {recorded!r} is from {came}; it is kept as "
                f"recorded, not re-admitted. The bytes' own type is {own!r}. "
                "Whether they are text is the recorded encoding")
        # SAME-CONTENT IS OF THE OBSERVATION READ -- this page's bytes --
        # never of whatever is latest at its key. Nothing is replayed for a
        # key that cannot have it.
        if _may_have_same_content(o):
            if lat is None:
                lat = latest(corpus, e["body"]["source"])
            out["same_content"] = _same_content(lat, o)
    return out


#: The largest window of an extraction served in one answer, in code points.
WINDOW_CHARS = 64 * 1024


def _read_extraction(corpus, e, o, digest, extraction, offset,
                     length) -> dict:
    """One window of one exact extraction of a source the caller may read.
    Never another identity's: an id that is not stored and cannot be run
    here is refused, never substituted."""
    from mentis.sources import extract as X
    from mentis.sources.extract import engine, store
    if not X.is_id(extraction):
        raise Refused(f"`extraction` is an extractor id, "
                      f"name@version+hash12, not {extraction!r}")
    st = engine.verified(corpus.root, digest)
    if st != "present":
        raise Refused(f"the bytes of {e['id']} are {st}; nothing is made or "
                      "served from bytes that are not what the record "
                      "committed to")
    ext = X.by_id(extraction)
    try:
        if (ext is not None and store.load(corpus.root, digest, extraction)
                is None and not ext.takes(o.get("payload_type"),
                                          engine.head(corpus.root, digest))):
            raise Refused(f"{extraction} does not accept "
                          f"{o.get('payload_type')}")
        got = engine.representation(corpus.root, digest, extraction)
    except X.Transient as exc:
        raise Refused(f"{extraction} of {e['id']} could not be made just "
                      f"now, for a reason of this machine: {exc}. Nothing "
                      "was stored; it is tried again later") from None
    except X.Unavailable as exc:
        raise Refused(f"{extraction} of {e['id']} is not reproducible "
                      f"here: {exc}") from None
    except store.Corrupt as exc:
        raise Refused(f"the stored extraction is corrupt and is not "
                      f"served: {exc}") from None
    if X.kind_of(got.status) != X.OK:
        raise Refused(f"{extraction} of {e['id']} is {got.status}; there "
                      "is no text to read")
    size = len(got.text)
    offset = max(0, int(offset or 0))
    length = max(1, min(int(length or WINDOW_CHARS), WINDOW_CHARS))
    if offset >= size:
        raise Refused(f"offset {offset} is past the end ({size} code "
                      "points)")
    end = min(size, offset + length)
    where = engine.locate(got, offset, end)
    return {"ref": e["id"], "collection": o.get("collection"),
            "path": o.get("object"), "digest": digest,
            "source_digest": digest,
            "extraction": {"extractor_id": got.extractor_id,
                           "representation_digest":
                               got.representation_digest,
                           "map_digest": got.manifest["map_digest"],
                           "locator_scheme": got.manifest["locator_scheme"],
                           "status": got.status},
            "unit": "codepoint", "size": size, "offset": offset, "end": end,
            "next_offset": end if end < size else None,
            "text": got.text[offset:end],
            "encoding": "extracted text (UTF-8, NFC, LF)",
            "scheme": where["scheme"], "loc": where["loc"],
            "display": where["display"],
            "cite": engine.cite(e["id"], digest, got, offset, end),
            "note": "an extraction of the exact retained bytes, by exactly "
                    "this extractor identity; offsets are code points in "
                    "it. `loc` is where in the source this window came "
                    "from"}


def extractions(corpus, e) -> list[dict]:
    """The extractions of one observation's bytes a reader can ask for:
    the current ones configured for its type, and any other identity the
    store holds for the same bytes (an older one a citation names)."""
    from mentis.sources.extract import engine, store
    o = observation(e)
    digest = held.digest_of(e["body"].get("locator"))
    if o.get("state") != "present" or not digest:
        return []
    out, seen = [], set()
    for name, ext in engine.configured(o.get("payload_type"),
                                       engine.head(corpus.root, digest)):
        if ext is None:
            out.append({"extractor_id": None, "name": name,
                        "state": engine.UNAVAILABLE, "current": True,
                        "why": "configured but not registered here"})
            continue
        st, got, why = engine.state(corpus.root, digest, ext)
        seen.add(ext.id)
        out.append({"extractor_id": ext.id, "name": ext.name, "state": st,
                    "status": got.status if got else None, "current": True,
                    "chars": len(got.text) if got else None,
                    "locator_scheme": ext.locator_scheme, "why": why})
    for xid in store.ids(corpus.root, digest):
        if xid in seen:
            continue
        st, got, why = engine.state(corpus.root, digest, xid)
        out.append({"extractor_id": xid, "name": xid.split("@")[0],
                    "state": st, "status": got.status if got else None,
                    "current": False,
                    "chars": len(got.text) if got else None,
                    "locator_scheme": (got.manifest["locator_scheme"]
                                       if got else None), "why": why})
    return out


# -- a pinned reference: what it is, and whether there is newer (B7) -----------

def provenance(corpus, ref: str) -> dict:
    """What an acquired observation IS, for a reference to it.

    THE REFERENCE NEVER MOVES (owner decision 3). The `adm-` a Turn carries is
    the observation it cited; this says which version of which object that
    is, the sweep that produced it, and whether a newer one has been
    recorded since -- shown, never followed silently."""
    e = _bulk_admission(corpus, ref)
    o = observation(e)
    col = o["collection"]
    decl = next((d for d in declarations(corpus) if d["collection"] == col),
                None)
    hist = [x for x in corpus.admissions_from(source_id(o["connector"], col))
            if observation(x).get("object") == o.get("object")]
    ids = [x["id"] for x in hist]
    n = ids.index(e["id"]) + 1 if e["id"] in ids else None
    last = hist[-1] if hist else e
    sweep = None
    for lk in corpus.links(relation=PRODUCED, to=e["id"]):
        act = (lk.get("link") or {}).get("from")
        got = corpus.operational(id=act) if act else []
        if got and got[0]["act"] == SWEPT:
            sweep = {"act": got[0]["id"], "at": got[0]["at"],
                     "actor": got[0].get("actor")}
            break
    try:
        d = registry.descriptor(o["connector"])
        conn = {"connector_label": d.label, "live": d.live}
    except Refused:
        conn = {"connector_label": o["connector"], "live": None}
    obj_key = str(o.get("object") or "")
    if obj_key.startswith(".git/commits/"):
        nature = "author's claim"
    elif obj_key.startswith(".git/"):
        nature = "change evidence"
    else:
        nature = "acquired file"
    return {"ref": e["id"], "what": "an acquired observation",
            "collection": col,
            "collection_name": decl["name"] if decl else None,
            "connector": o["connector"], **conn,
            "object": o.get("object"),
            "label": _label(o["connector"], o.get("object"), o),
            "nature": nature, "claim_or_evidence": nature,
            "action": o.get("action"), "state": o.get("state"),
            "batch": o.get("batch"), "digest": o.get("digest"),
            "size": o.get("size"), "payload_type": o.get("payload_type"),
            "text": (o.get("encoding") or {}).get("text"),
            "admitted_at": e["body"].get("admitted_at"),
            "sweep": sweep,
            "version": {"n": n, "of": len(hist)},
            "latest": last["id"],
            "latest_state": observation(last).get("state"),
            "extractions": (extractions(corpus, e)
                            if not corpus.links(relation=held.PURGED,
                                                to=e["id"]) else []),
            "newer_exists": last["id"] != e["id"],
            "observations": [{"ref": x["id"],
                              "state": observation(x).get("state"),
                              "action": observation(x).get("action"),
                              "admitted_at": x["body"].get("admitted_at")}
                             for x in hist],
            "note": "this reference names this observation and never moves; "
                    "a newer one is shown, never followed silently"}


def _rel_key(r) -> tuple:
    return (r.get("rel"), r.get("syntax"), r.get("authored"),
            r.get("resolution"), r.get("resolved"))


def compare(corpus, a: str, b: str) -> dict:
    """Two observations of ONE object: what differs in what was recorded, and
    for text the first page of each. A line diff is the interface's to draw;
    nothing here stores one."""
    pa, pb = provenance(corpus, a), provenance(corpus, b)
    if (pa["collection"], pa["object"]) != (pb["collection"], pb["object"]):
        raise Refused("these are observations of two different objects; "
                      "compare compares one object's versions")
    oa = observation(_bulk_admission(corpus, a))
    ob = observation(_bulk_admission(corpus, b))
    fields = {}
    for f in ("state", "digest", "size", "payload_type", "encoding"):
        if oa.get(f) != ob.get(f):
            fields[f] = {"a": oa.get(f), "b": ob.get(f)}
    ra = {_rel_key(r): r for r in oa.get("relations") or ()}
    rb = {_rel_key(r): r for r in ob.get("relations") or ()}

    def page(ref, o):
        if o.get("state") != "present" or not (o.get("encoding") or {}).get(
                "text"):
            return None
        try:
            return read(corpus, ref=ref)
        except Refused as exc:
            return {"refused": str(exc)}
    return {"collection": pa["collection"], "object": pa["object"],
            "label": pa["label"], "a": pa, "b": pb,
            "same_bytes": oa.get("digest") == ob.get("digest"),
            "differences": fields,
            "relations": {
                "added": [rb[k] for k in rb if k not in ra],
                "removed": [ra[k] for k in ra if k not in rb]},
            "pages": {"a": page(a, oa), "b": page(b, ob)}}


# -- a stored note, rendered with its stored images (Sources B, B3) -----------

#: The most of one note `rendered` returns. A note is read whole to be drawn;
#: past this the rest is said to be cut, never silently dropped.
RENDER_BYTES = 2 * 1024 * 1024


def rendered(corpus, ref: str) -> dict:
    """One text observation, whole (to `RENDER_BYTES`), with every embed it
    records resolved to what the record holds -- for the Object page's
    Rendered view. READS ONLY THE RECORD AND THE HELD STORE: no bound folder,
    no external fetch, and nothing is written.

    WITHIN THE SAME PINNED CONTEXT. Each embed resolves, through its recorded
    relation (`resolved`), to the target's latest observation AS THE RECORD
    STOOD WHILE THIS OBSERVATION WAS CURRENT: for the latest observation of
    the note, the target's latest; for an older one, the target's latest
    appended before the note's next observation. A pinned old note is not
    drawn with images recorded after it was replaced. Each embed is said
    with `links`' statuses (G2); only `acquired` names an Admission, and
    whether that is an image is the bytes' signature (`view`)."""
    from mentis import artifacts
    e = _bulk_admission(corpus, ref)
    o = observation(e)
    d = _collection(corpus, o["collection"])
    src = _source(d)
    key = o.get("object")
    if not (o.get("encoding") or {}).get("text"):
        raise Refused(f"{ref} is not text; there is nothing to render")
    page = read(corpus, ref=ref, length=1)        # every refusal `read` makes
    seen: dict[str, dict] = {}
    passed = False
    for x in corpus.admissions_from(src):
        if passed and observation(x).get("object") == key:
            break                                  # the note's next version
        if x["id"] == e["id"]:
            passed = True
        k = observation(x).get("object")
        if k is not None:
            seen[k] = x
    status = _target_status(corpus, d, seen)
    digest = held.digest_of(e["body"].get("locator"))
    data = held.read(corpus.root, digest)
    cut = len(data) > RENDER_BYTES
    end = min(len(data), RENDER_BYTES)
    while 0 < end < len(data) and (data[end] & 0xC0) == 0x80:
        end -= 1
    embeds = []
    for r in o.get("relations") or ():
        if r.get("rel") != "embeds":
            continue
        row = {"syntax": r.get("syntax"), "authored": r.get("authored"),
               "resolution": r.get("resolution"),
               "resolved": r.get("resolved"), **status(r)}
        if row["target"] == ACQUIRED:
            t = artifacts.describe(corpus, row["target_ref"], verify=False)
            row["state"] = t["state"]
            got = (artifacts.sniffed(corpus, t.get("digest"))
                   if t["state"] == "held" else None)
            row["view"] = got["view"] if got else None
        embeds.append(row)
    text = data[:end].decode("utf-8")
    if text.startswith("﻿"):
        text = text[1:]
    return {"ref": e["id"], "collection": d["collection"], "key": key,
            "label": _label(d, key), "digest": digest, "size": len(data),
            "text": text, "truncated": cut, "embeds": embeds,
            "cite": page["cite"].split("[")[0] + f"[0:{end}]",
            "note": "rendered from the held bytes; embeds are resolved from "
                    "the record, never fetched from the folder or the web"}


# -- Git change evidence derived diffs & offline proofs (Stage H) -------------

def compare_change(corpus, change: str, path: str, *,
                   collection: str | None = None, offset: int = 0) -> dict:
    """Compare before and after for one path in a Git change record (H5).

    The change record may be given by Admission ref (`adm-...`) or by its
    key (`.git/changes/<sha>/<parent|root>`), with `collection` when given by
    key.

    The line diff is derived on demand from the WHOLE held before and after
    blobs using `difflib.unified_diff`, and served one page of at most
    PAGE_BYTES UTF-8 bytes from byte `offset`; a diff longer than that says so
    (`truncated`, `size`, `next_offset`) and is read on by offset. It is never
    stored as Sources material. If the file is binary, withheld, or a submodule, the
    reason is returned with no diff text.
    """
    lat = None
    if change.startswith("adm-"):
        e = _bulk_admission(corpus, change)
        col = observation(e).get("collection")
        d = _collection(corpus, col)
    else:
        if not collection:
            raise Refused("give a change record Admission ref, or a collection "
                          "and change key")
        d = _collection(corpus, collection)
        col = d["collection"]
        lat = _latest(corpus, d)
        e = lat.get(change)
        if e is None:
            raise Refused(f"{change!r} has not been recorded in {col}")
    o = observation(e)
    obj_key = str(o.get("object") or "")
    if not (obj_key.startswith(".git/changes/") or o.get("payload_type") == "application/x-git-diff-tree-raw"):
        raise Refused(f"{e['id']} is not a Git change record")

    r_before = None
    r_after = None
    for r in o.get("relations") or ():
        rel = r.get("rel")
        p = r.get("path") or r.get("authored")
        if p == path:
            if rel == "before":
                r_before = r
            elif rel == "after":
                r_after = r

    if not r_before and not r_after:
        raise Refused(f"{path!r} was not changed in {obj_key}")

    native = o.get("native") or {}
    status = (r_after.get("status") if r_after else None) or (r_before.get("status") if r_before else None)
    if lat is None:
        lat = _latest(corpus, d)

    def _side_info(r, side_name):
        if not r:
            return None
        res = r.get("resolution")
        blob_id = r.get("blob")
        mode = r.get("mode")
        if r.get("mode") == "160000":
            return {
                "submodule": True,
                "gitlink": r.get("gitlink"),
                "mode": mode,
                "note": "submodule (gitlink); content not followed",
            }
        if res != "in-collection" or not r.get("resolved"):
            return {
                "withheld": True,
                "reason": r.get("why") or "not held",
                "blob": blob_id,
                "mode": mode,
            }
        blob_key = r["resolved"]
        blob_adm = lat.get(blob_key)
        if not blob_adm:
            return {
                "withheld": True,
                "reason": f"blob {blob_key} not found in collection records",
                "blob": blob_id,
                "mode": mode,
            }
        try:
            p = _read_admission(corpus, blob_adm, lat=lat)
            # The diff is of the whole blob, never of its first page.
            _st, data = held.state(corpus.root, p["digest"], verify=True)
            return {
                "ref": blob_adm["id"],
                "blob": blob_id,
                "mode": mode,
                "size": p.get("size"),
                "encoding": p.get("encoding"),
                "page": p,
                "text": p.get("text"),
                "_complete_text": (data.decode("utf-8")
                         if p.get("encoding") != "bytes" else None),
            }
        except Refused as exc:
            return {
                "ref": blob_adm["id"],
                "blob": blob_id,
                "mode": mode,
                "withheld": True,
                "reason": str(exc),
            }

    before_info = _side_info(r_before, "before")
    after_info = _side_info(r_after, "after")

    is_submodule = ((before_info and before_info.get("submodule"))
                    or (after_info and after_info.get("submodule")))
    is_withheld = ((before_info and before_info.get("withheld"))
                   or (after_info and after_info.get("withheld")))
    is_binary = ((before_info and before_info.get("encoding") == "bytes")
                 or (after_info and after_info.get("encoding") == "bytes"))

    if is_submodule:
        diff_info = {
            "derived": False,
            "algorithm": None,
            "submodule": True,
            "text": None,
            "note": "submodule (gitlink); content not followed",
        }
    elif is_withheld:
        why = ((before_info.get("reason") if before_info and before_info.get("withheld") else None)
               or (after_info.get("reason") if after_info and after_info.get("withheld") else None))
        diff_info = {
            "derived": False,
            "algorithm": None,
            "withheld": True,
            "reason": why,
            "text": None,
            "note": f"diff withheld: {why}",
        }
    elif is_binary:
        diff_info = {
            "derived": False,
            "algorithm": None,
            "binary": True,
            "text": None,
            "note": "binary file; no text diff claimed",
        }
    else:
        text_before = (before_info.get("_complete_text") or "") if before_info else ""
        text_after = (after_info.get("_complete_text") or "") if after_info else ""
        lines_a = text_before.splitlines(keepends=True) if before_info else []
        lines_b = text_after.splitlines(keepends=True) if after_info else []
        from_label = f"a/{path}" if before_info else "/dev/null"
        to_label = f"b/{path}" if after_info else "/dev/null"
        diff_lines = list(difflib.unified_diff(lines_a, lines_b, fromfile=from_label, tofile=to_label))
        full_diff = "".join(diff_lines)
        diff_bytes = full_diff.encode("utf-8")
        start = max(0, int(offset or 0))
        if start and start >= len(diff_bytes):
            raise Refused(f"offset {start} is past the end of the diff "
                          f"({len(diff_bytes)} bytes)")
        while 0 < start < len(diff_bytes) and diff_bytes[start] & 0xC0 == 0x80:
            start -= 1
        end = min(len(diff_bytes), start + PAGE_BYTES)
        while start < end < len(diff_bytes) and diff_bytes[end] & 0xC0 == 0x80:
            end -= 1
        diff_info = {
            "derived": True,
            "algorithm": "Python difflib unified, n=3",
            "text": diff_bytes[start:end].decode("utf-8"),
            "offset": start,
            "truncated": start > 0 or end < len(diff_bytes),
            "next_offset": end if end < len(diff_bytes) else None,
            "size": len(diff_bytes),
            "size_unit": "bytes",
            "input_coverage": "complete",
            "versions_differ": text_before != text_after,
            "lines": len(diff_lines),
        }

    for side in (before_info, after_info):
        if side:
            side.pop("_complete_text", None)

    return {
        "collection": col,
        "change": e["id"],
        "change_key": obj_key,
        "commit": native.get("commit"),
        "parent": native.get("parent"),
        "parent_index": native.get("parent_index"),
        "path": path,
        "status": status,
        "evidence": {
            "source_native": True,
            "status": status,
            "old_mode": r_before.get("mode") if r_before else None,
            "new_mode": r_after.get("mode") if r_after else None,
            "old_blob": r_before.get("blob") if r_before else None,
            "new_blob": r_after.get("blob") if r_after else None,
        },
        "before": before_info,
        "after": after_info,
        "diff": diff_info,
        "note": "diff is derived on demand from held blobs; never stored as Sources material",
    }


def verify_offline_path_proof(corpus, collection: str, commit_sha: str,
                              path: str) -> dict:
    """Prove offline from held bytes alone that a commit contains a path (H4).

    Verifies the cryptographic chain:
      commit -> root tree -> subtrees... -> blob/tree entry

    Every tree and blob is checked against Git's exact object identity:
      SHA-1 of `<kind> <len>\\0<bytes>`
    No external Git commands, working trees, or network are consulted.
    """
    from mentis.sources.git import (COMMITS, TREES, BLOBS,
                                    verify_git_object, _tree_of_commit,
                                    _parse_tree_entries)

    d = _collection(corpus, collection)
    lat = _latest(corpus, d)

    commit_adm = lat.get(f"{COMMITS}{commit_sha}")
    if not commit_adm:
        if any(observation(a).get("native", {}).get("parent") == commit_sha
               for key, a in lat.items() if key.startswith(".git/changes/")):
            return {"verified": False, "collection": collection,
                    "commit": commit_sha, "path": path,
                    "limitation": "parent commit anchor is outside this sweep's commit window and is not acquired here; before-side proof requires a separately retained parent anchor",
                    "reason": "parent commit bytes are not held in this collection"}
        raise Refused(f"commit {commit_sha} not found in collection {collection}")

    c_digest = held.digest_of(commit_adm["body"].get("locator"))
    st, commit_bytes = held.state(corpus.root, c_digest, verify=True)
    if st != "present" or not commit_bytes:
        raise Refused(f"commit bytes for {commit_sha} are {st}")
    verify_git_object("commit", commit_sha, commit_bytes)

    root_tree_id = _tree_of_commit(commit_bytes)
    if not root_tree_id:
        raise Refused(f"could not parse root tree from commit {commit_sha}")

    chain = []
    curr_tree_id = root_tree_id
    parts = [p for p in path.split("/") if p]
    if not parts:
        raise Refused("path cannot be empty")

    mode = None
    kind = None
    entry_sha = None

    for i, seg in enumerate(parts):
        is_leaf = (i == len(parts) - 1)
        tree_adm = lat.get(f"{TREES}{curr_tree_id}")
        if not tree_adm:
            raise Refused(f"tree {curr_tree_id} not held in collection {collection}")
        t_digest = held.digest_of(tree_adm["body"].get("locator"))
        st, tree_bytes = held.state(corpus.root, t_digest, verify=True)
        if st != "present" or not tree_bytes:
            raise Refused(f"tree bytes for {curr_tree_id} are {st}")
        verify_git_object("tree", curr_tree_id, tree_bytes)

        entries = _parse_tree_entries(tree_bytes)
        if seg not in entries:
            raise Refused(f"entry {seg!r} not found in tree {curr_tree_id}")

        mode, kind, entry_sha = entries[seg]
        hop = {
            "tree_id": curr_tree_id,
            "entry_name": seg,
            "mode": mode,
            "kind": kind,
            "entry_id": entry_sha,
        }
        chain.append(hop)

        if not is_leaf:
            if kind != "tree":
                raise Refused(f"intermediate path component {seg!r} is a {kind}, not a tree")
            curr_tree_id = entry_sha
        else:
            if kind == "blob":
                blob_adm = lat.get(f"{BLOBS}{entry_sha}")
                if not blob_adm:
                    raise Refused(f"blob {entry_sha} not held in collection {collection}")
                b_digest = held.digest_of(blob_adm["body"].get("locator"))
                st, blob_bytes = held.state(corpus.root, b_digest, verify=True)
                if st != "present" or blob_bytes is None:
                    raise Refused(f"blob bytes for {entry_sha} are {st}")
                verify_git_object("blob", entry_sha, blob_bytes)

    return {
        "verified": True,
        "collection": collection,
        "commit": commit_sha,
        "root_tree": root_tree_id,
        "path": path,
        "target": {
            "mode": mode,
            "kind": kind,
            "id": entry_sha,
        },
        "chain": chain,
        "note": "cryptographically verified offline from held store bytes only",
    }
