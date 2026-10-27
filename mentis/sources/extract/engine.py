"""Making, finding and locating extractions (C1.6, C1.7, C2).

WHAT IS EXTRACTED is decided by configuration (`config.CURRENT`): for an
observation's payload type, the current identity of each configured
extractor name that accepts its bytes' signature. The record decides
nothing here and learns nothing: no act, Admission or link is written about
an extraction, ever (R1, C2).

FROM RETAINED, VERIFIED BYTES ONLY. An extraction is made from the held
store's bytes for a digest, verified against it before a byte is used --
never from a bound folder. WHICH Admission may be read is the caller's
question, asked first: `search` and `read_source` reach a source exactly as
they reach its raw bytes (present, held, not purged), and only then ask for
its extraction. A purged Admission is not made readable by another one
holding the same bytes.

WHEN. In the background after a sweep, for each newly present source with a
current extractor (`after_sweep`, one thread per call -- the B5 pattern),
and on demand when a search or read finds one missing (`schedule`, then a
bounded `wait`). A key being made is `pending`; a key one process is making
is never made twice by it (a lock per key), and two processes writing one
key leave one (`store.write` renames atomically and never replaces).

EXACT IDENTITY. A key is made only by the identity it is filed under, and
only if that identity is runnable here (`extract.runnable`): it is intact
and its installed libraries are the versions it declares -- checked before
it runs and again before its output is written. Otherwise it is
`unavailable`, and nothing else is substituted.

ONLY WHAT THE BYTES DECIDE IS STORED. A key is a deterministic function of
(source bytes, identity), so `failed:` is written only for what that pair
decides: output the core refuses, a misaligned map, or an exception the
extractor raises on these bytes. A failure of the environment
(`extract.TRANSIENT`: out of memory, an OS error, recursion depth, a missing
import, or `extract.Transient`) is never written. It is kept in this
process's memory as `transient`, with its reason, and the key is tried again
by the next search, read or sweep after `RETRY_SECONDS`.

EXTRACTIONS GO WITH THE LAST POSSESSION OF THEIR BYTES (C2), even one in
flight. Purge removes the held bytes and THEN forgets the digest's
extractions. A build therefore checks that the held bytes still exist AFTER
it has published its key -- or failed to -- and, if they are gone, removes
what it wrote and reports the source unavailable. Either that check sees
the bytes, and purge's forget comes after the publication and removes it, or
it sees them gone and takes its own write back. No lock is shared with
purge, and nothing is recorded. A sweep also reclaims any digest directory
whose held bytes are gone (`reclaim`), whatever left it there.
"""

from __future__ import annotations

import threading
import time

from mentis.sources import extract as X
from mentis.sources.extract import config, store
from mentis.spine import held

#: How long a search waits for extractions it found missing before it
#: answers, reporting any still being made as `extraction_pending`.
WAIT = 30.0
#: How long a key whose last attempt failed for a reason of the environment
#: is left before it is tried again.
RETRY_SECONDS = 60.0

PENDING = "pending"
MISSING = "missing"
UNAVAILABLE = "unavailable"
CORRUPT = "corrupt"
TRANSIENT = "transient"

_LOCK = threading.Lock()
_KEY_LOCKS: dict[tuple, threading.Lock] = {}
_PENDING: set[tuple] = set()
#: Keys whose last attempt failed for a reason of the environment, by key:
#: (why, when). Memory only; never stored, never recorded.
_TRANSIENT: dict[tuple, tuple[str, float]] = {}
#: Source digests whose held bytes verified, by (root, digest, size, mtime).
_VERIFIED: set[tuple] = set()


def _key(root, digest, extractor_id) -> tuple:
    return (str(root), digest, extractor_id)


def _key_lock(k) -> threading.Lock:
    with _LOCK:
        lk = _KEY_LOCKS.get(k)
        if lk is None:
            lk = _KEY_LOCKS[k] = threading.Lock()
        return lk


def _cooling(k) -> str | None:
    """Why this key's last attempt failed for a reason of the environment,
    while it is still left alone; None once it may be tried again."""
    with _LOCK:
        got = _TRANSIENT.get(k)
    if got is None or time.time() - got[1] >= RETRY_SECONDS:
        return None
    return got[0]


# -- which extractors -------------------------------------------------------------

def head(root, digest: str, n: int = 64) -> bytes:
    try:
        with open(held.path(root, digest), "rb") as f:
            return f.read(n)
    except (FileNotFoundError, ValueError):
        return b""


def configured(payload_type: str | None, head_bytes: bytes) -> list[tuple]:
    """`(name, extractor or None)` for each extractor configured for this
    payload type, in order. None: configured, but no identity of that name
    is registered here. One registered that does not accept these bytes'
    signature is left out."""
    out = []
    for name in config.names_for(payload_type):
        ext = X.current(name)
        if ext is None:
            out.append((name, None))
        elif ext.takes(payload_type, head_bytes):
            out.append((name, ext))
    return out


def has_extractor(payload_type: str | None) -> bool:
    return bool(config.names_for(payload_type))


# -- the state of one key -------------------------------------------------------------

def state(root, digest: str, ext) -> tuple[str, store.Stored | None, str]:
    """(state, the stored key or None, why). State is `ok`, `empty` or
    `failed` (made, by its status), `pending`, `transient` (the last attempt
    failed for a reason of the environment; tried again later), `missing`,
    `unavailable` or `corrupt`."""
    xid = ext.id if isinstance(ext, X.Extractor) else ext
    try:
        got = store.load(root, digest, xid)
    except store.Corrupt as exc:
        return CORRUPT, None, str(exc)
    if got is not None:
        return X.kind_of(got.status), got, got.status
    k = _key(root, digest, xid)
    if k in _PENDING:
        return PENDING, None, "being made"
    why = _cooling(k)
    if why is not None:
        return TRANSIENT, None, (f"{why}; not stored, tried again within "
                                 f"{RETRY_SECONDS:g}s")
    why = X.runnable(X.by_id(xid) if not isinstance(ext, X.Extractor)
                     else ext)
    if why:
        return UNAVAILABLE, None, why
    return MISSING, None, "not made yet"


def verified(root, digest: str) -> str:
    """`present` when the held bytes verify against their digest (once per
    version of the file in this process), else `missing` or `corrupt`."""
    try:
        st = held.path(root, digest).stat()
    except (FileNotFoundError, ValueError):
        return "missing"
    k = (str(root), digest, st.st_size, st.st_mtime_ns)
    if k in _VERIFIED:
        return "present"
    s, _ = held.state(root, digest, verify=True)
    if s == "present":
        _VERIFIED.add(k)
    return s


# -- making one --------------------------------------------------------------------

def build(root, digest: str, ext: X.Extractor) -> store.Stored:
    """Make one key from the held bytes, by exactly this identity, and
    store it. Raises `Unavailable` when it cannot be run here or the bytes
    are not held and verified (or stop being held while it runs), and
    `Transient` -- storing nothing -- when it fails for a reason of the
    environment. An extractor that raises anything else on these bytes, or
    whose output is not a valid representation, is stored as
    `failed: <why>`."""
    why = X.runnable(ext)
    if why:
        raise X.Unavailable(f"{ext.id}: {why}")
    sch = X.scheme(ext.locator_scheme)
    if sch is None:
        raise X.Unavailable(f"{ext.id}: its locator scheme "
                            f"{ext.locator_scheme} is not registered")
    s, data = held.state(root, digest, verify=True)
    if s != "present":
        raise X.Unavailable(f"the source bytes {digest[:12]} are {s}")
    k = _key(root, digest, ext.id)
    try:
        text, spans, status = ext.extract(data, ext.options_copy())
        bad = X.check(text, spans, status, sch)
        if bad:
            text, spans, status = "", [], f"failed: invalid output: {bad}"
    except X.Misaligned as exc:
        text, spans, status = "", [], f"failed: {exc}"
    except X.TRANSIENT as exc:
        why = f"{type(exc).__name__}: {str(exc)[:300]}"
        with _LOCK:
            _TRANSIENT[k] = (why, time.time())
        raise X.Transient(f"{ext.id} on {digest[:12]}: {why}") from exc
    except Exception as exc:                              # noqa: BLE001
        text, spans, status = "", [], (f"failed: {type(exc).__name__}: "
                                       f"{str(exc)[:300]}")
    # Checked again: nothing it ran may have changed what its id means.
    why = X.runnable(ext)
    if why:
        raise X.Unavailable(f"{ext.id}: {why}")
    manifest = {"extractor_id": ext.id, "name": ext.name,
                "version": ext.version, "options": X.snapshot(ext.options),
                "deps": X.snapshot(ext.all_deps),
                "locator_scheme": ext.locator_scheme, "status": status}
    store.tidy(root, digest)
    try:
        got = store.write(root, digest, manifest, text, spans)
    except (OSError, store.Corrupt) as exc:
        # A purge deleting the digest while this published it.
        if _gone(root, digest):
            raise X.Unavailable(f"the source bytes {digest[:12]} were "
                                "removed while being extracted") from exc
        raise
    if _gone(root, digest):
        raise X.Unavailable(f"the source bytes {digest[:12]} were removed "
                            "while being extracted")
    with _LOCK:
        _TRANSIENT.pop(k, None)
    return got


def _gone(root, digest: str) -> bool:
    """AFTER publishing: are the held bytes gone? Then a purge has ended the
    last possession of them, and whatever this or another build left under
    the digest is taken back (C2)."""
    if held.path(root, digest).exists():
        return False
    store.forget(root, digest)
    return True


def reclaim(root) -> list[str]:
    """Every digest directory in the store whose held bytes are gone,
    deleted: derived material of bytes no longer possessed (C2). Writes
    nothing to the record."""
    out = []
    for digest in store.digests(root):
        if not held.path(root, digest).exists() and store.forget(root,
                                                                  digest):
            out.append(digest)
    return out


def ensure(root, digest: str, ext: X.Extractor) -> store.Stored:
    """The key, made now if it is missing. Raises `Unavailable` (or
    `Transient`, while a failure of the environment is left alone) or
    `store.Corrupt`."""
    got = store.load(root, digest, ext.id)
    if got is not None:
        return got
    k = _key(root, digest, ext.id)
    why = _cooling(k)
    if why is not None:
        raise X.Transient(f"{ext.id} on {digest[:12]}: {why}; tried again "
                          f"within {RETRY_SECONDS:g}s")
    with _key_lock(k):
        got = store.load(root, digest, ext.id)
        if got is not None:
            return got
        with _LOCK:
            _PENDING.add(k)
        try:
            return build(root, digest, ext)
        finally:
            with _LOCK:
                _PENDING.discard(k)


def representation(root, digest: str, extractor_id: str, *,
                   make: bool = True) -> store.Stored:
    """Exactly this identity's key for this source: stored, or made by that
    identity if it is registered and runnable here. Never another
    identity's. Raises `Unavailable` or `store.Corrupt`."""
    got = store.load(root, digest, extractor_id)
    if got is not None:
        return got
    ext = X.by_id(extractor_id)
    if ext is None:
        raise X.Unavailable(f"{extractor_id} is not stored for this source "
                            "and is not registered here")
    if not make:
        raise X.Unavailable(f"{extractor_id} is not stored for this source")
    return ensure(root, digest, ext)


# -- in the background ------------------------------------------------------------------

def schedule(root, jobs) -> list[tuple]:
    """Make each missing `(digest, extractor)` in one background thread.
    Returns the keys it took on; a key already pending is left to whoever
    is making it, and one whose last attempt failed for a reason of the
    environment is left until `RETRY_SECONDS` have passed."""
    took = []
    jobs = [(d, e) for d, e in jobs if _cooling(_key(root, d, e.id)) is None]
    with _LOCK:
        for digest, ext in jobs:
            k = _key(root, digest, ext.id)
            if k not in _PENDING:
                _PENDING.add(k)
                took.append((digest, ext, k))
    if not took:
        return []

    def go():
        for digest, ext, k in took:
            try:
                with _key_lock(k):
                    if store.load(root, digest, ext.id) is None:
                        build(root, digest, ext)
            except Exception:                              # noqa: BLE001
                pass         # reported by `state` when it is next asked
            finally:
                with _LOCK:
                    _PENDING.discard(k)

    threading.Thread(target=go, name="source-extraction",
                     daemon=True).start()
    return [k for _, _, k in took]


def wait(root, jobs, timeout: float = WAIT) -> bool:
    """Block until none of `(digest, extractor)` is pending, or `timeout`.
    True when all are done."""
    keys = {_key(root, d, e.id) for d, e in jobs}
    end = time.time() + max(0.0, timeout)
    while True:
        with _LOCK:
            left = keys & _PENDING
        if not left:
            return True
        if time.time() >= end:
            return False
        time.sleep(0.02)


def after_sweep(corpus, admitted) -> list[tuple]:
    """Start extracting each newly admitted present source that has a
    current extractor (C2), after reclaiming any extraction whose held
    bytes are gone. Writes nothing to the record."""
    from mentis.sources import observation
    reclaim(corpus.root)
    jobs = []
    for e in corpus.read(list(admitted or ())):
        o = observation(e)
        if o.get("state") != "present" or e["body"].get("content") != "held":
            continue
        if not has_extractor(o.get("payload_type")):
            continue
        digest = held.digest_of(e["body"].get("locator"))
        if not digest:
            continue
        for _, ext in configured(o.get("payload_type"),
                                 head(corpus.root, digest)):
            if ext is not None and X.runnable(ext) is None \
                    and store.load(corpus.root, digest, ext.id) is None:
                jobs.append((digest, ext))
    return schedule(corpus.root, jobs) if jobs else []


# -- locating ----------------------------------------------------------------------------

def locate(got: store.Stored, start: int, end: int) -> dict:
    """Where code points `[start, end)` of a stored representation came
    from: the scheme, the location, its token and its display."""
    sch = X.scheme(got.manifest["locator_scheme"])
    if sch is None:
        raise X.Unavailable(f"the locator scheme "
                            f"{got.manifest['locator_scheme']} is not "
                            "registered here")
    loc = X.locate(got.map, sch, start, end)
    return {"scheme": sch.name, "loc": loc, "token": X.token(sch, loc),
            "display": sch.display(loc)}


def cite(ref: str, source_digest: str, got: store.Stored, start: int,
         end: int) -> str:
    from mentis.sources.extract import cite as C
    where = locate(got, start, end)
    return C.extracted(ref, source_digest, got.extractor_id,
                       got.representation_digest, start, end,
                       where["scheme"], where["token"])


# -- what the store holds, for a collection's status ------------------------------------

def progress(corpus, entries) -> dict:
    """For the latest present observations given: how many have a current
    extractor, and the state of each such key. From the store and this
    process's memory -- never from the record's acts."""
    from mentis.sources import observation
    counts: dict[str, int] = {}
    sources = 0
    for e in entries:
        o = observation(e)
        if o.get("state") != "present" or not has_extractor(
                o.get("payload_type")):
            continue
        digest = held.digest_of(e["body"].get("locator"))
        if not digest:
            continue
        sources += 1
        for name, ext in configured(o.get("payload_type"),
                                    head(corpus.root, digest)):
            st = (UNAVAILABLE if ext is None
                  else state(corpus.root, digest, ext)[0])
            counts[st] = counts.get(st, 0) + 1
    return {"sources_with_extractor": sources,
            "by_state": dict(sorted(counts.items())),
            "note": "derived material beside the record; nothing about it "
                    "is recorded"}
