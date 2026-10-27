"""The corpus's own byte store: what an Admission with `content: held` names.

A HELD Admission is neither inline nor external. Its bytes are in this corpus's
own directory, beside `corpus.db`, as immutable files named by their sha256:

    <corpus>/artifacts/sha256/<first two hex>/<full hex>

and its `locator` is `sha256:<hex>`. The spine commits to the digest, so the
bytes are tamper-evident without the hash chain having to cover them, and a
file that no longer hashes to its own name is reported as corrupt rather than
served or repaired.

WHY THIS IS SPINE AND NOT A LAYER ABOVE IT. `held` is one of the four things an
Admission's content can be, and a snapshot of a corpus that held bytes but did
not carry them would be a copy in which every one of them reads as missing. So
the store lives where `snapshot` does. Nothing here knows a Kind, an act or a
Participant; recording who brought bytes across is `mentis.artifacts`.

WHAT THIS NEVER DOES. It never follows a path it was given -- it is handed
bytes -- never overwrites a blob, never repairs one, and deletes one only when
the caller has decided on a purge that the record already carries.

Ported from the returned-artifact and artifact-ingress prototypes (Jim,
executions b29cce03 and 1c661f71), where every property below was measured.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import tempfile
import time

#: Where held bytes live, relative to the corpus directory.
STORE = pathlib.Path("artifacts") / "sha256"

#: How an Admission names held bytes.
LOCATOR = "sha256:"

#: The link relation by which the record ends possession of an Admission's
#: bytes. The spine reads it for one thing only: a snapshot does not carry
#: bytes that only purged Admissions name. What a purge IS belongs above.
PURGED = "purged"

#: One crossing, bounded. The largest file in the three governance proposals
#: the prototype was measured against was 3.1 MB. A size, not a policy.
MAX_BYTES = 25 * 1024 * 1024

#: A write in progress. Never a blob, never copied, never served.
_INCOMING = ".incoming-"


def is_digest(s) -> bool:
    return (isinstance(s, str) and len(s) == 64
            and all(c in "0123456789abcdef" for c in s))


def digest_of(locator) -> str | None:
    """The digest a held locator names, or None if it names none."""
    if isinstance(locator, str) and locator.startswith(LOCATOR):
        d = locator[len(LOCATOR):]
        return d if is_digest(d) else None
    return None


def path(root: str, digest: str) -> pathlib.Path:
    if not is_digest(digest):
        raise ValueError(f"{digest!r} is not a sha256 digest")
    return pathlib.Path(root) / STORE / digest[:2] / digest


def put(root: str, data: bytes) -> tuple[str, bool]:
    """Store bytes under their digest. Returns (digest, newly_written).

    Identical bytes are stored once. A blob that already exists is re-hashed
    before it is trusted as the copy of these bytes; one that fails is NOT
    overwritten, because a silently repaired blob would hide a corruption the
    record should report.
    """
    if len(data) > MAX_BYTES:
        raise ValueError(f"{len(data)} bytes is over the {MAX_BYTES} byte cap")
    digest = hashlib.sha256(data).hexdigest()
    target = path(root, digest)
    if target.exists():
        if hashlib.sha256(_read(target)).hexdigest() != digest:
            raise IOError(f"a blob for {digest} exists and does not hash to "
                          "its own name; refusing to write over the evidence")
        return digest, False
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=_INCOMING)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            _settle(tmp, target)
        except (FileExistsError, PermissionError):
            # TWO WRITERS OF THE SAME BYTES: the other put it there first.
            # The blob is named by its content, so one that is now there and
            # hashes to its name IS these bytes; anything else is re-raised.
            if not (target.exists() and hashlib.sha256(
                    _read(target)).hexdigest() == digest):
                raise
            os.unlink(tmp)
            return digest, False
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return digest, True


def _settle(tmp: str, target: pathlib.Path) -> None:
    """Move a finished write to its name, NEVER OVER A BLOB ALREADY THERE:
    `os.replace` overwrote one when a second writer of the same bytes came
    second. Raises FileExistsError (or, on Windows, PermissionError) when the
    name is taken."""
    if os.name == "nt":
        os.rename(tmp, target)      # refuses an existing target on Windows
    else:
        os.link(tmp, target)        # refuses an existing target everywhere
        os.unlink(tmp)


def _read(p: pathlib.Path) -> bytes:
    """A blob's bytes, through Windows' transient refusals.

    On Windows a file that has just been put in place -- by a rename, by
    another thread or process writing the same bytes -- can refuse to be
    opened for a moment (PermissionError, measured: 64 refused reads in 40
    rounds of 8 writers and 4 readers of the same bytes). Two concurrent
    confirmations of one sweep failed about 1 run in 30 on it. The refusal
    passes within milliseconds, so the read is retried for a bounded time and
    a refusal that outlasts it is raised as it is."""
    for wait in (0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5):
        try:
            return p.read_bytes()
        except PermissionError:
            if os.name != "nt":
                raise
            time.sleep(wait)
    return p.read_bytes()


def read(root: str, digest: str) -> bytes:
    """The bytes held under a digest, unverified, through Windows' transient
    refusals. What SERVES bytes asks `state(..., verify=True)` instead."""
    return _read(path(root, digest))


def has(root: str, digest: str) -> bool:
    return is_digest(digest) and path(root, digest).is_file()


def state(root: str, digest: str, *, verify: bool) -> tuple[str, bytes | None]:
    """What stands behind a digest: `present`, `missing` or `corrupt`.

    `verify=False` asks only whether the file is there, which is cheap enough
    for a listing. Anything that SERVES bytes verifies, so nothing is ever
    handed on that is not what the record committed to.
    """
    p = path(root, digest)
    if not p.is_file():
        return "missing", None
    if not verify:
        return "present", None
    data = _read(p)
    if hashlib.sha256(data).hexdigest() != digest:
        return "corrupt", None
    return "present", data


def size(root: str, digest: str) -> int:
    return path(root, digest).stat().st_size


def blobs(root: str) -> list[str]:
    """Every digest this directory holds bytes for. In-progress writes excluded."""
    src = pathlib.Path(root) / STORE
    if not src.exists():
        return []
    return sorted(f.name for f in src.glob("*/*")
                  if f.is_file() and is_digest(f.name))


def incoming(root: str) -> list[str]:
    """Writes that never completed. Harmless, and reported rather than hidden."""
    src = pathlib.Path(root) / STORE
    if not src.exists():
        return []
    return sorted(str(f) for f in src.glob(f"*/{_INCOMING}*") if f.is_file())


def remove(root: str, digest: str) -> bool:
    """Delete one blob. Returns whether there was one.

    Only for a purge the record ALREADY carries: the caller writes the act
    first, so a crash between the two leaves a record saying purged over bytes
    that are still there -- which the sweep reports -- and never bytes gone
    with nothing saying why.
    """
    p = path(root, digest)
    try:
        p.unlink()
    except FileNotFoundError:
        return False
    return True


def copy(root: str, target_root: str, digests, *, verify: bool = False) -> dict:
    """Copy these blobs into another corpus directory's store.

    NAMED, never wholesale. A snapshot copies what its own record says is held
    and not purged, so bytes that were purged -- or that no Admission names --
    do not ride along into a copy made after the fact. A blob that is missing
    here is reported, not invented; one that is already present in the target
    is left alone, because it is named by its content.

    `not_present` is a fact about this directory, not a verdict: bytes the
    record names that are not here were purged or were lost, and which of
    those it is is the record's to say (`mentis.artifacts.sweep`), not this.

    `verify`: what a restore relies on. Each copy is written to a temp name,
    hashed, and put in place only if it hashes to its name; a source that does
    not is `source_corrupt` and is not copied. A blob already in the target is
    re-hashed: one that fails is `target_corrupt` and is left exactly as it is
    -- this never writes over a blob -- for the caller to deal with.
    """
    copied, present, missing = [], [], []
    source_corrupt, target_corrupt = [], []
    for d in sorted(set(digests)):
        src = path(root, d)
        dst = path(target_root, d)
        if not src.is_file():
            missing.append(d)
            continue
        if dst.exists():
            if verify and hashlib.sha256(_read(dst)).hexdigest() != d:
                target_corrupt.append(d)
            else:
                present.append(d)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not verify:
            shutil.copy2(src, dst)
            copied.append(d)
            continue
        fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=_INCOMING)
        try:
            h = hashlib.sha256()
            with os.fdopen(fd, "wb") as out, open(src, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            if h.hexdigest() != d:
                os.unlink(tmp)
                source_corrupt.append(d)
                continue
            _settle(tmp, dst)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        copied.append(d)
    out = {"copied": copied, "already_present": present,
           "not_present": missing}
    if verify:
        out.update(source_corrupt=source_corrupt,
                   target_corrupt=target_corrupt)
    return out
