"""Whether a citation still says what it said (C1.6, R3, R5).

DIRECT (`adm-…@d12[s:e]`): the source is a held acquisition whose digest
begins `d12`, its bytes verify, and `[s:e]` lies inside them -> `verified`.

EXTRACTED (`adm-…@d12~id/r12[s:e]{scheme:token}`): the representation of
EXACTLY `(source digest, id)` -- read from the store, or made again by
exactly that identity where it is registered and runnable here -- must have
a representation digest beginning `r12`, hold `[s:e]`, and locate it, by its
own map and scheme, at exactly the `{scheme:token}` the citation carries.
Then it is `verified`.

NEVER RE-POINTED. Nothing here looks at any other identity's output, the
current extractor included. When that identity's key is gone and it cannot
be run here, the answer is `not reproducible here`, with what the citation
itself carries -- the source `adm-`, its location token -- and the quoted
text the Turn holds, passed in by whoever shows it. A representation that
exists under the id but differs from the citation is `mismatch`: a defect,
said as one.

REACH. The source must be a Bulk Source acquisition that is present, held
and not purged, as for every source read: a purged one is not reproducible
here, whatever else holds the same bytes.
"""

from __future__ import annotations

from mentis.sources import Refused, reading
from mentis.sources import extract as X
from mentis.sources.extract import cite as C, engine, store
from mentis.spine import held

VERIFIED = "verified"
#: Not answered yet: the key is being made again by its exact identity (in
#: the background, for a caller that may not wait), or its last attempt
#: failed for a reason of this machine and is tried again later.
PENDING = "pending"
NOT_REPRODUCIBLE = "not reproducible here"
MISMATCH = "mismatch"
UNREADABLE = "unreadable"


def _source(corpus, c: C.Cite) -> tuple[dict | None, str | None, str]:
    """(entry, digest, why not) for the citation's source, under source
    reach."""
    try:
        e = reading._bulk_admission(corpus, c.ref)
    except Refused as exc:
        return None, None, str(exc)
    from mentis.sources import observation
    o = observation(e)
    digest = held.digest_of(e["body"].get("locator"))
    if o.get("state") != "present" or e["body"].get("content") != "held" \
            or not digest:
        return e, digest, f"{c.ref} records no held bytes"
    if not digest.startswith(c.source12):
        return e, digest, (f"{c.ref} holds {digest[:12]}, not the cited "
                           f"{c.source12}")
    if corpus.links(relation=held.PURGED, to=e["id"]):
        return e, digest, f"{c.ref} was purged"
    return e, digest, ""


def verify(corpus, cite: str, *, quote: str | None = None,
           make: bool = True) -> dict:
    """What a citation is now. `quote` is the text the Turn quoted with it,
    returned as given when the citation cannot be reproduced. `make`: may a
    missing key be made again by its exact identity, now. Without it, a
    missing key whose identity is runnable here is started in the
    background and the answer is `pending` -- never built while the caller
    (the chip's hover) waits."""
    try:
        c = C.parse(cite)
    except C.Malformed as exc:
        return {"cite": cite, "status": "malformed", "why": str(exc)}
    out = {"cite": cite, **c.public(), "quote": quote}
    e, digest, why = _source(corpus, c)
    if e is not None:
        from mentis.sources import observation
        o = observation(e)
        out.update(collection=o.get("collection"), key=o.get("object"),
                   label=reading._label(o.get("connector") or "",
                                        o.get("object"), o))
    if not c.extracted:
        if why:
            return {**out, "status": UNREADABLE, "why": why}
        st, data = held.state(corpus.root, digest, verify=True)
        if st != "present":
            return {**out, "status": UNREADABLE,
                    "why": f"the source bytes are {st}"}
        if c.end > len(data):
            return {**out, "status": MISMATCH,
                    "why": f"[{c.start}:{c.end}] is past the end "
                           f"({len(data)} bytes)"}
        return {**out, "status": VERIFIED, "source_digest": digest}

    def unreproducible(reason):
        return {**out, "status": NOT_REPRODUCIBLE, "why": reason,
                "shows": {"source": c.ref, "location": f"{c.scheme}:"
                          f"{c.token}", "quote": quote}}

    if why:
        return unreproducible(why)
    if engine.verified(corpus.root, digest) != "present":
        return unreproducible("the source's held bytes are not present "
                              "and verified")
    try:
        got = engine.representation(corpus.root, digest, c.extractor_id,
                                    make=make)
    except X.Transient as exc:
        return {**out, "status": PENDING,
                "why": f"{exc}; nothing was stored, and it is tried again "
                       "later"}
    except X.Unavailable as exc:
        ext = X.by_id(c.extractor_id)
        if not make and X.runnable(ext) is None:
            engine.schedule(corpus.root, [(digest, ext)])
            st, _, why = engine.state(corpus.root, digest, ext)
            return {**out, "status": PENDING,
                    "why": f"{c.extractor_id} is being made again by its "
                           f"exact identity ({st}: {why}); ask again"}
        return unreproducible(f"{c.extractor_id} is not stored here and "
                              f"cannot be run: {exc}")
    except store.Corrupt as exc:
        return {**out, "status": MISMATCH, "why": str(exc)}
    out.update(source_digest=digest,
               representation_digest=got.representation_digest,
               map_digest=got.manifest["map_digest"],
               extraction_status=got.status)
    if not got.representation_digest.startswith(c.representation12):
        return {**out, "status": MISMATCH,
                "why": f"{c.extractor_id} gives {got.representation_digest[:12]}"
                       f" for this source, not the cited "
                       f"{c.representation12}: a defect, never re-pointed"}
    if c.end > len(got.text):
        return {**out, "status": MISMATCH,
                "why": f"[{c.start}:{c.end}] is past the representation's "
                       f"{len(got.text)} code points"}
    try:
        where = engine.locate(got, c.start, c.end)
    except X.Unavailable as exc:
        return unreproducible(str(exc))
    if (where["scheme"], where["token"]) != (c.scheme, c.token):
        return {**out, "status": MISMATCH,
                "why": f"the map locates [{c.start}:{c.end}] at "
                       f"{where['scheme']}:{where['token']}, not the cited "
                       f"{c.scheme}:{c.token}"}
    out["display"] = where["display"]
    return {**out, "status": VERIFIED, "text": got.text[c.start:c.end]}

