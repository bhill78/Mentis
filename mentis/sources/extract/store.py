"""The extraction store: derived material beside the corpus (C1.4, R1, R6, R7).

`<brain>/derived/extractions/<source_digest>/<extractor_id>/` holds exactly
three files and nothing else:

  text       the representation, UTF-8
  map        the origin map, canonical JSON
  manifest   {source_digest, extractor_id, name, version, options, deps,
              locator_scheme, representation_digest, map_digest, status,
              chars, made_at}, canonical JSON

NOT THE RECORD. Nothing here is an Admission, an act or a blob; a snapshot
(an SQLite backup) does not copy it; it may be deleted at any time and is
made again identically from the source's retained bytes (C1.6). What becomes
durable does so through the ordinary mechanisms -- a Turn quoting the
passage with its cite.

WRITES ARE ATOMIC. A key is written whole into a hidden sibling directory
(`.incoming-<uuid>`, under the source digest) and renamed into place; a key
that is already there is never replaced. A crash leaves no half-written key
that would verify, and two writers of one key leave the first one's.

A KEY IS READ ONLY IF IT VERIFIES: the text's sha256 is the manifest's
`representation_digest`, the map's is its `map_digest`, and the manifest
names the digest and identity it is filed under. Anything else is reported
as corrupt and never served.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import threading
import time
import uuid

from mentis.sources.extract import canonical, is_id, sha256
from mentis.spine import held

ROOT = pathlib.Path("derived") / "extractions"
FILES = ("text", "map", "manifest")
_INCOMING = ".incoming-"
#: An incoming directory older than this is a crash's leftover.
STALE_SECONDS = 60 * 60


class Corrupt(ValueError):
    """A stored key that does not verify. Never served."""


def base(root) -> pathlib.Path:
    return pathlib.Path(root) / ROOT


def _digest_dir(root, digest: str) -> pathlib.Path:
    if not held.is_digest(digest):
        raise ValueError(f"not a source digest: {digest!r}")
    return base(root) / digest


def key_dir(root, digest: str, extractor_id: str) -> pathlib.Path:
    if not is_id(extractor_id):
        raise ValueError(f"not an extractor id: {extractor_id!r}")
    return _digest_dir(root, digest) / extractor_id


class Stored:
    """One verified key, read whole."""

    __slots__ = ("manifest", "text", "map", "data")

    def __init__(self, manifest: dict, text: str, spans: list, data: bytes):
        self.manifest, self.text, self.map, self.data = (manifest, text,
                                                         spans, data)

    @property
    def extractor_id(self) -> str:
        return self.manifest["extractor_id"]

    @property
    def representation_digest(self) -> str:
        return self.manifest["representation_digest"]

    @property
    def status(self) -> str:
        return self.manifest["status"]


_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
#: Verified keys kept in memory, by path and the manifest's (size, mtime).
#: Few and small next to their sources; the oldest go first past this many.
CACHE_KEYS = 64


def load(root, digest: str, extractor_id: str) -> Stored | None:
    """The verified key, or None when it is not there. Raises `Corrupt`."""
    d = key_dir(root, digest, extractor_id)
    try:
        st = (d / "manifest").stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    # KEPT BY WHAT WOULD CHANGE IF ANY OF THE THREE DID, so a file altered
    # on disk is read and verified again -- and refused -- rather than
    # answered from an earlier verified copy.
    try:
        ck = (str(d),) + tuple((s.st_size, s.st_mtime_ns) for s in (
            st, (d / "text").stat(), (d / "map").stat()))
    except FileNotFoundError:
        raise Corrupt(f"{d.name} under {digest[:12]} is incomplete") from None
    with _CACHE_LOCK:
        got = _CACHE.get(ck)
    if got is not None:
        return got
    import json
    try:
        names = sorted(p.name for p in d.iterdir())
        mb = (d / "manifest").read_bytes()
        data = (d / "text").read_bytes()
        mapb = (d / "map").read_bytes()
    except FileNotFoundError:
        raise Corrupt(f"{d.name} under {digest[:12]} is incomplete") from None
    if names != sorted(FILES):
        raise Corrupt(f"{d.name} under {digest[:12]} holds {names}, not "
                      f"exactly {list(FILES)}")
    m = json.loads(mb.decode("utf-8"))
    if m.get("source_digest") != digest or m.get("extractor_id") \
            != extractor_id:
        raise Corrupt(f"the manifest at {digest[:12]}/{extractor_id} names "
                      f"{m.get('source_digest')}/{m.get('extractor_id')}")
    if sha256(data) != m.get("representation_digest"):
        raise Corrupt(f"{digest[:12]}/{extractor_id}: the text does not "
                      "match its representation_digest")
    if sha256(mapb) != m.get("map_digest"):
        raise Corrupt(f"{digest[:12]}/{extractor_id}: the map does not "
                      "match its map_digest")
    got = Stored(m, data.decode("utf-8"), json.loads(mapb.decode("utf-8")),
                 data)
    with _CACHE_LOCK:
        if len(_CACHE) >= CACHE_KEYS:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[ck] = got
    return got


def write(root, digest: str, manifest: dict, text: str,
          spans: list) -> Stored:
    """Write one key atomically. If it is already there, the one there
    stands and is returned: a key is never replaced."""
    final = key_dir(root, digest, manifest["extractor_id"])
    parent = final.parent
    parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    mapb = canonical(spans).encode("utf-8")
    m = dict(manifest)
    m.update(source_digest=digest, representation_digest=sha256(data),
             map_digest=sha256(mapb), chars=len(text), made_at=time.time())
    tmp = parent / f"{_INCOMING}{uuid.uuid4().hex}"
    tmp.mkdir()
    try:
        for name, b in (("text", data), ("map", mapb),
                        ("manifest", canonical(m).encode("utf-8"))):
            with open(tmp / name, "wb") as f:
                f.write(b)
                f.flush()
                os.fsync(f.fileno())
        try:
            os.rename(tmp, final)
        except OSError:
            if not (final / "manifest").exists():
                raise
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    return load(root, digest, manifest["extractor_id"])


def ids(root, digest: str) -> list[str]:
    """The extractor ids stored for one source digest."""
    try:
        return sorted(p.name for p in _digest_dir(root, digest).iterdir()
                      if p.is_dir() and is_id(p.name))
    except FileNotFoundError:
        return []


def digests(root) -> list[str]:
    try:
        return sorted(p.name for p in base(root).iterdir()
                      if p.is_dir() and held.is_digest(p.name))
    except FileNotFoundError:
        return []


#: Attempts at deleting a tree another thread or process is writing into,
#: renaming within or deleting at the same moment.
RMTREE_TRIES = 8


def _rmtree(d: pathlib.Path) -> bool:
    """Delete `d` whole, while a build may be renaming a key into it and
    another delete may be removing it too: a file or directory already gone
    is gone, and one that cannot be removed yet (a directory gaining a
    child, a file still open on Windows) is tried again. True when `d` is
    gone; never raises."""
    for attempt in range(RMTREE_TRIES):
        try:
            shutil.rmtree(d)
        except FileNotFoundError:
            pass
        except OSError:
            time.sleep(0.02 * (attempt + 1))
        if not d.exists():
            return True
    return not d.exists()


def remove(root, digest: str, extractor_id: str) -> bool:
    d = key_dir(root, digest, extractor_id)
    if not d.exists():
        return False
    return _rmtree(d)


def forget(root, digest: str) -> bool:
    """Every extraction of one source digest, deleted (purge, C2). True when
    there was something and it is gone. Never raises: it runs after a
    purge's acts are written, and what it cannot delete now -- a build
    publishing into it at this moment -- is taken back by that build, or
    by the next sweep (`engine.reclaim`)."""
    d = _digest_dir(root, digest)
    if not d.exists():
        return False
    return _rmtree(d)


def tidy(root, digest: str) -> None:
    """Remove a crash's leftover incoming directories under one digest."""
    try:
        kids = list(_digest_dir(root, digest).iterdir())
    except FileNotFoundError:
        return
    now = time.time()
    for p in kids:
        if p.name.startswith(_INCOMING):
            try:
                if now - p.stat().st_mtime > STALE_SECONDS:
                    shutil.rmtree(p, ignore_errors=True)
            except FileNotFoundError:
                pass
