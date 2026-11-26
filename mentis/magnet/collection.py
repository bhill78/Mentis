"""Latest or explicitly selected collections, read only from immutable Admissions.

No lift, activation, live-source lookup or repair is performed by this read.
Older activations remain in the append-only record.
"""
from __future__ import annotations

import hashlib
import json
import re

from mentis import artifacts
from mentis.fluid import read as fluid

from . import MAGNET_ID, Unreadable, read as definition
from . import activation as X


class UnreadableCollection(ValueError):
    """A recorded collection cannot be served as the evidence it claims."""


class UndigestibleRow(ValueError):
    """ONE recorded row has no exact content identity, so that row alone refuses.

    Raised by `row_digest` for the row it was given, and never for the batch:
    the owner's correction (`opr-87b0f7e52098`) is that a single odd row must
    report itself, not take the whole collection's identities -- and with them
    the new-item diff -- with it.
    """


def _config(st, mid):
    if not MAGNET_ID.fullmatch(mid):
        raise fluid.BadRequest("that is not a Magnet id")
    try:
        config = definition(st.corpus.root, mid)
    except Unreadable as exc:
        raise UnreadableCollection(str(exc)) from None
    if config is None:
        raise fluid.NotFound(mid)
    return config


def _retained(st, mid, act):
    bad = UnreadableCollection("this Magnet's latest retained collection is missing or invalid; "
                               "no live source was substituted")
    try:
        detail = act["detail"]
        recorded = detail["artifact"]
        ref = recorded["ref"]
        if ref not in act["about"] or detail["mode"] != X.MODE or not act["turn"]:
            raise bad
        got = artifacts.describe(st.corpus, ref, verify=True)
        if (got["state"] != "held" or got["source"] != f"magnet:{mid}"
                or got["door"] != "magnet-extract" or got["claimed_media_type"] != X.MEDIA_TYPE
                or got["digest"] != recorded["digest"] or got["size"] != recorded["size"]):
            raise bad
        raw = got["_bytes"]
        if len(raw) != recorded["size"] or len(raw) > X.ARTIFACT_MOST:
            raise bad
        # Reuse the activation format, identity and provenance verifier, which is read-only.
        verified = X._verified(st, mid, raw, recorded["digest"], X.MEDIA_TYPE)
        if (verified["by"] != act["actor"]
                or verified["operation"]["index"] != detail["operation"]["index"]
                or verified["operation"]["name"] != detail["operation"]["name"]
                or verified["definition_sha256"] != detail["definition_sha256"]
                or verified["state"] != detail["page"]["state"]):
            raise bad
        page = json.loads(raw)["page"]
        activation = {"post": act["turn"],
                      "artifact": {"ref": ref, "digest": recorded["digest"],
                                   "size": recorded["size"], "media_type": X.MEDIA_TYPE},
                      "at": act["at"], "state": verified["state"]}
        return activation, page
    except (KeyError, TypeError, ValueError, OSError, X._Stop):
        raise bad from None


def row_digest(row) -> str:
    """One recorded row's own content identity, over the bytes the batch holds.

    Sorted keys, compact separators, literal UTF-8: deterministic, so the read
    that serves an identity and the send that validates it compute the same
    digest from the same verified immutable row. It is NOT the managed selector
    canonicalization (`message_context.canonical`), which refuses the
    non-integer `at`/`acquired_at` timestamps a collected row carries. Nothing
    derives it from captured text: the row as recorded is the whole input.

    A row this cannot state exactly -- a non-finite number (`json.loads`
    accepts `NaN` and `Infinity`, so a recorded batch can hold one), a value no
    encoder accepts, nesting too deep to walk, a lone surrogate -- raises
    `UndigestibleRow` FOR THAT ROW. The caller drops that one row's identity and
    keeps the others (`references`), so one odd row no longer costs the batch
    its new-item count.
    """
    try:
        text = json.dumps(row, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    except (TypeError, ValueError, RecursionError) as exc:
        raise UndigestibleRow(f"this row has no exact content identity: {exc}") from None


def references(activation, page) -> dict:
    """THE EXACT IDENTITY OF EACH COLLECTED ROW, so a supporting record can be
    what a message is about (owner ent-3191baeb33d2 §§1, 6; contract §3).

    Derived from the verified immutable batch and served BESIDE it -- the page
    itself is returned exactly as recorded. Each identity is the row's captured
    version: the recorded batch it belongs to, and that row's own digest. It
    carries no title, text, label or captured content, and it grants nothing:
    what an agent may actually read is still decided by the existing gates, and
    the retained collection is still not answer evidence (`message_context`).

    An id two rows share has no exact identity, so neither is offered; the card
    then refuses it in words, as it does any row this cannot state exactly -- and
    a row whose own bytes cannot be digested (`UndigestibleRow`) is exactly such
    a row, left out on its own while the rest of the batch keeps its identities.
    """
    if not activation or not isinstance(page, dict):
        return {}
    batch = activation["artifact"]["ref"]
    out, seen = {}, set()
    for one in page.get("sources") or ():
        for row in (one.get("results") or () if isinstance(one, dict) else ()):
            rid = row.get("id") if isinstance(row, dict) else None
            if not isinstance(rid, str) or not rid or len(rid) > 128:
                continue
            if rid in seen:
                out.pop(rid, None)
                continue
            seen.add(rid)
            try:
                digest = row_digest(row)
            except UndigestibleRow:
                continue        # this row only: it is offered no identity, like a shared id
            out[rid] = {"kind": "collected_item", "ref": rid,
                        "version": batch, "digest": digest}
    return out


def member(st, mid, selected) -> dict:
    """The selected collected record, verified against this Magnet's recorded
    batch, or `Refused`. The send boundary's one membership check.

    Identity only, and scoped exactly as the collection read is: the batch must
    be a recorded extract of THIS Magnet that still verifies (so a forged,
    foreign, deleted, unreadable or restricted batch refuses), and the row must
    be in it at exactly the digest the message was about (so a stale or forged
    row refuses). Nothing here widens source access, reads a live source or
    substitutes anything.
    """
    from mentis import artifacts
    from mentis.fluid.message_context import refuse
    ref, version, want = selected["ref"], selected["version"], selected["digest"]

    def stale():
        refuse("stale-reference", "the selected collected record changed or is not "
               "in that collection", status=409)

    if not isinstance(version, str) or not re.fullmatch(r"adm-[0-9a-f]{12}", version):
        refuse("invalid-reference", "a collected record is selected at its recorded "
               "batch identity")
    acts = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is={"magnet": mid},
                                 about=version, newest_first=True, limit=1)
    if not acts or acts[0]["detail"].get("artifact", {}).get("ref") != version:
        stale()
    if artifacts.deleted_from(st.corpus, st.cv, version):
        stale()
    made = artifacts.producing_act(st.corpus, st.cv, version)
    if made and made.get("caused_by") and artifacts.restriction_of(st.cv, made["caused_by"]):
        refuse("restricted-reference", "that collection was recorded under restricted work",
               status=403)
    try:
        activation, page = _retained(st, mid, acts[0])
    except UnreadableCollection:
        stale()
    got = references(activation, page).get(ref)
    if not got or got["digest"] != want:
        stale()
    return got


# -- hydration: one selected row as readable evidence (Part B) -----------------
#
# `member` above verifies that a selection IS one of this Magnet's own recorded
# rows, and returns its identity. That was all the send boundary carried, so an
# agent was handed an id it could not quote (plan adm-43ecee5872e9 section 3,
# Part B). `hydrated` adds the two things a quotable row needs -- the text the
# BATCH ITSELF retains, and the cite a reply's reference resolves through -- and
# adds nothing else:
#
#   * `member` STAYS THE SINGLE MEMBERSHIP CHECK (contract
#     `docs/magnets/part-b-perspectives-api.md`, "the contract Part B
#     implements its hydration against", 1). It is called first and unchanged,
#     so a forged, foreign, stale, deleted or restricted selection refuses with
#     exactly the words and status it always did, before anything is hydrated.
#   * NOTHING LIVE IS READ, AND NOTHING IS SUBSTITUTED. Every byte comes out of
#     the same verified immutable batch `member` just checked. An id the row
#     happens to name -- its post, its Admission, its address -- is NOT
#     followed: a row whose text the batch did not retain hydrates no text, and
#     says so by leaving the field out rather than going to find some.
#   * HYDRATION WIDENS NO REACH. What crosses into the prompt is what the owner
#     selected in that exchange; the run must still ask the one door for
#     anything else (contract 2).

#: ONE ROW'S SHARE of the managed context. `message_context.CONTEXT_MAX`
#: (64 KiB) bounds the whole hydrated context and still refuses outright; this
#: bounds one row inside it, so selecting a single retained file -- whose text
#: the batch may hold up to 64 KiB of -- cannot exhaust the message's cap on
#: its own, and 16 selections can still reach it. Text cut here is never cut
#: silently: `shortened`, `omitted_bytes` and a `cite` narrowed to the bytes
#: actually hydrated all say so.
ROW_TEXT_MOST = 8 * 1024


def _value(row) -> dict:
    got = row.get("value") if isinstance(row, dict) else None
    return got if isinstance(got, dict) else {}


def retained_text(row) -> str | None:
    """The text THIS BATCH retains for this row, or None if it retains none.

    A held-source file row carries the captured range (`value.text`, verified
    whole by `activation._verified_file`). A collected post row carries its
    identity and provenance only -- the batch never captured its words -- so
    nothing is hydrated for it and nothing goes looking.
    """
    got = _value(row).get("text")
    return got if isinstance(got, str) else None


def cite(row) -> str | None:
    """What a reply pointing at this row resolves through.

    The batch's own citation where it recorded one (`adm-ref@digest[0:end]`,
    the same form `mentis.sources.reading` serves). Otherwise the row's own
    recorded version or id, which the owner's selection also put within the
    run's reach (`mentis.magnet.scope._selected_refs`), so a reply citing it
    resolves at the one door instead of naming something unreadable.
    """
    said = _value(row).get("citation")
    if isinstance(said, str) and said.strip():
        return said.strip()
    for key in ("version", "id"):
        got = row.get(key) if isinstance(row, dict) else None
        if isinstance(got, str) and got.startswith(("ent-", "adm-")):
            return got
    return None


def _bounded(text: str) -> tuple[str, int]:
    """`(text, omitted)` cut to `ROW_TEXT_MOST` UTF-8 bytes at a codepoint
    boundary. Bytes are the unit because the cap and the cite's range are."""
    raw = text.encode("utf-8")
    if len(raw) <= ROW_TEXT_MOST:
        return text, 0
    cut = ROW_TEXT_MOST
    while cut > 0 and raw[cut] & 0xC0 == 0x80:      # never split a codepoint
        cut -= 1
    return raw[:cut].decode("utf-8"), len(raw) - cut


def _narrowed(said: str | None, end: int) -> str | None:
    """A recorded `...[0:N]` cite restated for the bytes actually hydrated, so
    a quote and its citation never claim a range that was not supplied."""
    if not said or not re.fullmatch(r".*\[0:[0-9]+\]", said):
        return said
    return said.rsplit("[", 1)[0] + f"[0:{end}]"


def _batch_page(st, mid, version):
    """The recorded batch `member` has just verified, read again to hydrate out
    of it. `(activation, page)`, or `(None, None)` where it cannot be served --
    never a substitute, as everywhere else in this module."""
    acts = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is={"magnet": mid},
                                 about=version, newest_first=True, limit=1)
    if not acts or acts[0]["detail"].get("artifact", {}).get("ref") != version:
        return None, None
    try:
        return _retained(st, mid, acts[0])
    except UnreadableCollection:
        return None, None


def hydrated(st, mid, selected) -> dict:
    """The selected collected row as readable evidence: its verified identity,
    the text the batch retains for it, and its cite. `Refused` otherwise.

    The identity is `member`'s, unchanged. The row is then located in the same
    recorded batch by the identity `member` returned -- id AND digest, so the
    row hydrated is the row that was verified.
    """
    from mentis.fluid.message_context import refuse
    identity = member(st, mid, selected)            # THE ONE MEMBERSHIP CHECK
    _, page = _batch_page(st, mid, identity["version"])
    row = None
    for one in (page or {}).get("sources") or ():
        for candidate in (one.get("results") or () if isinstance(one, dict) else ()):
            if not isinstance(candidate, dict) or candidate.get("id") != identity["ref"]:
                continue
            try:
                if row_digest(candidate) == identity["digest"]:
                    row = candidate
            except UndigestibleRow:
                continue
    if row is None:
        # `member` admitted it a moment ago, so the batch has changed under the
        # send or cannot be stated exactly. Either way it is not substituted.
        refuse("stale-reference", "the selected collected record changed or is not "
               "in that collection", status=409)
    out = dict(identity)
    said = cite(row)
    text = retained_text(row)
    if text is not None:
        kept, omitted = _bounded(text)
        out["text"] = kept
        if omitted:
            out["shortened"] = True
            out["omitted_bytes"] = omitted
            said = _narrowed(said, len(kept.encode("utf-8")))
    if said:
        out["cite"] = said
    return out


def read(st, mid, *, batch=None, digest=None):
    config = _config(st, mid)
    if (batch is None) != (digest is None) or (batch is not None and (
            not isinstance(batch, str) or not re.fullmatch(r"adm-[0-9a-f]{12}", batch)
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest))):
        raise fluid.BadRequest("historical collection needs batch=<adm-ref> and digest=<SHA-256>")
    filters = {"magnet": mid}
    if batch is None:
        acts = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is=filters,
                                     newest_first=True, limit=1)
    else:
        acts = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is=filters,
                                     about=batch, newest_first=True, limit=1)
        if not acts or acts[0]["detail"].get("artifact", {}).get("ref") != batch:
            raise fluid.NotFound(batch)
        if acts[0]["detail"]["artifact"]["digest"] != digest:
            raise UnreadableCollection("the requested digest does not match this recorded collection")
    activation, page = _retained(st, mid, acts[0]) if acts else (None, None)
    return {"magnet": mid, "config": config, "activation": activation, "page": page,
            "references": references(activation, page)}


def new_since(st, mid, *, since):
    """Rows present in the latest batch but absent from an earlier named one.

    Identity is `row_digest`, the same content identity `references()` already
    serves beside every batch -- there is no second notion of "new". `since`
    names the collection batch (`adm-ref`) last shown to the viewer, as
    `history()` lists it; the caller holds that state, not this read. A
    `since` this Magnet never recorded, or whose retained batch no longer
    verifies, is refused -- never treated as empty, which would overstate
    what is new.
    """
    _config(st, mid)
    if not isinstance(since, str) or not re.fullmatch(r"adm-[0-9a-f]{12}", since):
        raise fluid.BadRequest("since=<adm-ref> names the collection batch last shown")
    filters = {"magnet": mid}
    acts = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is=filters,
                                 newest_first=True, limit=1)
    if not acts:
        raise fluid.NotFound(since)
    activation, page = _retained(st, mid, acts[0])
    current = references(activation, page)
    latest_ref = activation["artifact"]["ref"]
    if since == latest_ref:
        earlier_digests = {v["digest"] for v in current.values()}
    else:
        earlier_acts = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is=filters,
                                             about=since, newest_first=True, limit=1)
        if (not earlier_acts
                or earlier_acts[0]["detail"].get("artifact", {}).get("ref") != since):
            raise fluid.NotFound(since)
        earlier_activation, earlier_page = _retained(st, mid, earlier_acts[0])
        earlier_digests = {v["digest"] for v in references(earlier_activation, earlier_page).values()}
    new_ids = sorted(rid for rid, v in current.items() if v["digest"] not in earlier_digests)
    return {"magnet": mid, "batch": latest_ref, "new_count": len(new_ids), "new": new_ids}


def history(st, mid, *, limit=20, cursor=None):
    _config(st, mid)
    if isinstance(limit, str) and re.fullmatch(r"[0-9]{1,2}", limit):
        limit = int(limit)
    if type(limit) is not int or not 1 <= limit <= 20:
        raise fluid.BadRequest("history limit is 1..20")
    if cursor is None:
        upper = st.corpus.advance()[1]
        before = upper + 1
    else:
        match = re.fullmatch(r"mc1\.([A-Za-z0-9_-]+)\.([0-9]{1,20})\.([0-9]{1,20})", str(cursor))
        if not match or match[1] != mid:
            raise fluid.BadRequest("that is not this Magnet's collection history cursor")
        upper, before = int(match[2]), int(match[3])
        if not 0 < before <= upper + 1 <= 2**63 - 1:
            raise fluid.BadRequest("that collection history cursor is out of range")
    rows = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is={"magnet": mid},
        newest_first=True, through_seq=upper, before_seq=before, limit=limit + 1)
    batches = [_retained(st, mid, act)[0] for act in rows[:limit]]
    boundary = st.corpus.operational_order([rows[limit-1]["id"]]) if len(rows) > limit else {}
    next_cursor = f"mc1.{mid}.{upper}.{boundary[rows[limit-1]['id']]}" if boundary else None
    return {"magnet": mid, "batches": batches, "next": next_cursor}
