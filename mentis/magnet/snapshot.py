"""THE ONE VALIDATED DEFINITION SNAPSHOT, AND THE BOUNDARY IT IS READ UNDER.

Revised security contract adm-c5c73679ac1e §3 and §6 (Part B's amendment): a
managed request's `configuration_digest` must cover the *entire validated
durable* Magnet definition, and the definition must be read once, under the
same serialization boundary definition mutation is made under, with those bytes
retained through validation and the snapshot's commit and released only after
that commit or its refusal. B supplies the seam; nothing else may validate one
read and serialize another.

What that means here, concretely:

  `boundary(root)`   `mentis.magnet.boundary` -- the one lock every definition
                     write is made under (`magnet.write`, `set_conversation`,
                     `correct_conversation`, `arrangements.create_magnet`,
                     `reconfigure_magnet`, `lift_all`). Re-entrant within a
                     thread, so taking it again inside a write is safe.
  `holding(root, mid)`
                     the §3 boundary as a context manager: ONE read, validated
                     under the hold, yielded as a `Snapshot`, and the hold is
                     released only when the body leaves -- whether that body
                     committed or refused. A definition replaced under the hold
                     by a writer that did not take the boundary is `NotSerialized`:
                     a falsely atomic snapshot is refused rather than published.
  `expect=<digest>`  the first-send linearization. A concurrent update is either
                     before the read, and an explicit stale digest is `Stale`
                     (409), or after the commit, and the snapshot already taken
                     stays frozen -- the file changing afterwards cannot reach it.

THE DIGEST'S COVERAGE. `digest` is SHA-256 of `canonical`, which is the whole
validated definition with exactly two fields left out:

  `conversation`     the nonauthoritative own-Conversation mirror. The record's
                     claim overrides it (§3), so it is carried beside the digest
                     (`Snapshot.conversation`) and never inside it: a Magnet
                     opening its Conversation must not invalidate a snapshot.
  `schema_version`   the file's own version, not what the definition says. It is
                     carried as `Snapshot.schema_version`; the managed schema and
                     policy version are the request's (§4), not the file's.

Everything else is covered -- the name, every source and its configuration,
selection and its filters, collection and synthesis behaviour, activation,
processing, ai, outputs, destinations, presentation, and any facet a later
schema adds, because the coverage is "all of it but those two" and not a list
of fields to keep up to date.

CANONICAL BYTES (§3). Object keys sorted by Unicode scalar order recursively,
array order as given, UTF-8, no BOM, no whitespace, literal Unicode, only the
escaping JSON requires, no Unicode or newline normalization. Numbers in this
schema are integers: an integral value is written as an integer, and a value
that is not integral cannot be digested identically by both halves, so it is
refused (`NotCanonical`) rather than digested differently in each. Lone
surrogates are refused. `tests/fixtures/magnet-definition-digest/vectors.json`
is the golden vector file both this module and the client are held to.
"""
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import re
import time

from mentis.fluid import _checks as W

#: Every key a validated definition can hold: `schema._OPTION`, which the fixed
#: facet and field names also match. See `_plain`.
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,39}")

#: Carried beside the digest, never inside it (see the module docstring).
UNDIGESTED = ("conversation", "schema_version")
#: An integer this schema can carry identically in Python and in JavaScript.
INTEGER_MOST = 2 ** 53 - 1
#: The canonical bytes of a definition are bounded by the definition file's own
#: bound: `mentis.magnet.activation.DEFINITION_MOST` is the same number.
CANONICAL_MOST = W.MAX_BYTES


class Stale(RuntimeError):
    """The definition is not the revision the caller said it had: 409. Nothing
    was read for them, and nothing is substituted."""


class NotSerialized(RuntimeError):
    """The definition was replaced while this snapshot's boundary was held, so
    the seam did not in fact serialize the two: 409. The snapshot is refused
    rather than published as atomic (§3)."""


class NotCanonical(W.Refused):
    """This definition cannot be digested identically by both halves: 422."""


class TooLarge(W.Unreadable):
    """The definition file is past the bound, so it is not read at all: 409."""


def durable(definition) -> dict:
    """The definition the digest covers: all of it but `UNDIGESTED`."""
    return {k: v for k, v in definition.items() if k not in UNDIGESTED}


def _number(v, where):
    if isinstance(v, int):
        got = v
    elif float(v).is_integer():
        got = int(v)
    else:
        raise NotCanonical(f"{where}: {v!r} is not an integer, and this schema's "
                           "numbers are integers; it cannot be digested "
                           "identically in both halves")
    if not -INTEGER_MOST <= got <= INTEGER_MOST:
        raise NotCanonical(f"{where}: {got} is outside the integers this schema "
                           f"carries (±{INTEGER_MOST})")
    return got


def _plain(v, where="definition"):
    """`v` with every number an exact integer and no lone surrogate: what both
    halves can write the same way. Key order is `json.dumps(sort_keys=True)`'s,
    which is Unicode scalar order; a key outside ASCII, which no definition can
    hold, is refused so that the client's UTF-16 sort cannot disagree."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return _number(v, where)
    if isinstance(v, str):
        if any(0xD800 <= ord(c) <= 0xDFFF for c in v):
            raise NotCanonical(f"{where}: a lone surrogate cannot be encoded")
        return v
    if isinstance(v, list):
        return [_plain(x, f"{where}[{i}]") for i, x in enumerate(v)]
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            # Every key a definition can hold is an identifier
            # (`schema._OPTION`, and the fixed facet and field names). Held to
            # that here so both halves sort them the same way: the client sorts
            # UTF-16 code units and keeps insertion order, which agrees with
            # Unicode scalar order for these and for nothing numeric.
            if not isinstance(k, str) or not _KEY.fullmatch(k):
                raise NotCanonical(f"{where}: {k!r} is not a key a definition "
                                   "can hold")
            out[k] = _plain(x, f"{where}.{k}")
        return out
    raise NotCanonical(f"{where}: {type(v).__name__} is not a value a "
                       "definition can hold")


def canonical(definition) -> bytes:
    """The canonical bytes of `definition`'s durable part (see the module)."""
    data = _plain(durable(definition))
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":")).encode("utf-8")
    if len(raw) > CANONICAL_MOST:
        raise NotCanonical(f"definition: its canonical form is longer than "
                           f"{CANONICAL_MOST} bytes")
    return raw


def digest(definition) -> str:
    """`configuration_digest`: 64 lowercase hexadecimal characters (§3)."""
    return hashlib.sha256(canonical(definition)).hexdigest()


@dataclasses.dataclass(frozen=True)
class Snapshot:
    """One validated definition, frozen. `definition` is the whole validated
    config as the file has it; `value` is the durable part the digest covers."""

    magnet: str
    definition: dict
    value: dict
    canonical: bytes
    digest: str
    #: The definition's revision identity. Its content IS its revision: the
    #: canonical digest, so two reads of the same revision agree and a changed
    #: definition is a different revision whichever writer changed it.
    revision: str
    #: The exact bytes on disk, which the activation protocol hashes (and Rust
    #: verifies). Not the digest: that one is canonical and excludes the mirror.
    file_sha256: str
    #: Recorded separately, never digested (§3).
    conversation: str | None
    schema_version: int
    taken: float

    def unchanged(self, other: "Snapshot") -> bool:
        return self.digest == other.digest and self.file_sha256 == other.file_sha256


def _read_bytes(root, mid, *, most=CANONICAL_MOST) -> bytes:
    """The definition's exact bytes. The boundary must already be held."""
    from . import _path, unreadable_words
    try:
        with open(_path(root, mid), "rb") as file:
            raw = file.read(most + 1)
    except FileNotFoundError:
        return b""
    except OSError as exc:
        raise W.Unreadable(unreadable_words(mid, exc)) from None
    if len(raw) > most:
        raise TooLarge(f"the Magnet definition {mid} is longer than {most} bytes")
    return raw


def raw_bytes(root, mid, *, most=CANONICAL_MOST) -> bytes:
    """ONE read of the definition's exact bytes under the boundary, after the
    idempotent lift, so an otherwise good unlifted Magnet is not a false miss.
    `b""` where there is no definition. The activation protocol's read
    (`mentis.magnet.activation`) is this one."""
    from mentis.fluid import arrangements
    from . import boundary
    with boundary(root):
        arrangements.lift_all(root)
        return _read_bytes(root, mid, most=most)


def take(root, mid) -> Snapshot | None:
    """The validated snapshot of `mid`, or None where there is no definition.
    THE BOUNDARY MUST ALREADY BE HELD: use `holding` unless you hold it
    yourself (a definition write does)."""
    from . import SCHEMA_VERSION, checked
    raw = _read_bytes(root, mid)
    if not raw:
        return None
    from . import unreadable_words
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        raise W.Unreadable(unreadable_words(mid, exc)) from None
    definition = checked(mid, data)
    version = data.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        version = SCHEMA_VERSION
    body = canonical(definition)
    return Snapshot(magnet=mid, definition=definition, value=durable(definition),
                    canonical=body, digest=hashlib.sha256(body).hexdigest(),
                    revision=hashlib.sha256(body).hexdigest(),
                    file_sha256=hashlib.sha256(raw).hexdigest(),
                    conversation=definition.get("conversation"),
                    schema_version=version, taken=time.time())


@contextlib.contextmanager
def holding(root, mid, *, expect=None, writes=False):
    """THE §3 BOUNDARY. One validated snapshot, read under the lock every
    definition write is made under, held through the caller's validation and
    commit, released only when the body leaves -- committed or refused.

    `expect`: the revision the caller says it read. A different one is `Stale`,
    before anything is yielded, and nothing is substituted.

    `writes`: the body itself replaces the definition under this hold (a
    reconfigure). Otherwise the definition is checked at the end and a
    replacement by a writer that did not take the boundary is `NotSerialized`.

    ORDERING. Take this hold before opening a record transaction, never inside
    one: `mentis.fluid.commands` opens the Magnet's Conversation under
    `asking_for_conversation`, commits the record, and only then writes the
    file under this boundary.
    """
    from . import MISSING, Declined, boundary
    with boundary(root):
        snap = take(root, mid)
        if snap is None:
            raise Declined("state", MISSING)
        if expect is not None and expect != snap.revision:
            raise Stale(f"the Magnet definition {mid} is at another revision "
                        "than the one this request read; nothing was read for "
                        "it and nothing was substituted")
        yield snap
        if not writes:
            raw = _read_bytes(root, mid)
            if hashlib.sha256(raw).hexdigest() != snap.file_sha256:
                raise NotSerialized(
                    f"the Magnet definition {mid} was replaced while this "
                    "snapshot's boundary was held, so the read and the write "
                    "were not serialized; nothing of it is published")


def unchanged(root, snap: Snapshot) -> bool:
    """Whether the definition is still the revision `snap` froze: the recheck a
    consumer makes immediately before it supplies those bytes (§4). A read, and
    it writes nothing."""
    from . import boundary
    with boundary(root):
        try:
            now = take(root, snap.magnet)
        except W.Unreadable:
            return False
    return now is not None and now.unchanged(snap)


__all__ = ["CANONICAL_MOST", "INTEGER_MOST", "NotCanonical", "NotSerialized",
           "Snapshot", "Stale", "TooLarge", "UNDIGESTED", "canonical", "digest",
           "durable", "holding", "raw_bytes", "take", "unchanged"]
