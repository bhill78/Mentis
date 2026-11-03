"""Fluid workspace manifests: which objects a workspace holds, BESIDE the record.

    <corpus>/presentation/fluid-workspaces/<workspace-id>.json

WHAT ONE IS: a named, curated list of REFERENCES, zero or more, belonging to no
Conversation -- a blank workspace, or one holding several Magnets, is ordinary.
References by shape only; never Markdown, never bytes, never a source record.

WHAT ONE IS NOT: an arrangement. Where a thing is drawn and how it looks stay in
`mentis.fluid.arrangements` and `mentis.presentation`; this module reads neither,
and a manifest may not carry them (`RESERVED`), at any depth, so a later reader
of a manifest cannot be handed layout or theme. Nor is it a resolution: `curated`
says somebody chose this reference, not that the record still says what it said.
What a reference resolves to is never kept here, and nothing here resolves one.
`curated_references` is the frozen fields alone, for whatever reads them later.

WORKSPACE MANIFEST V1, as the file holds it (`ops` is the file's own: it is never
in what a read answers):

    {"format": "mentis.fluid-workspace", "schema_version": 1,
     "id": "wsp-...", "name": "", "revision": 1,
     "created": <seconds>, "updated": <seconds>,
     "objects": [<WorkspaceObjectV1>, ...], "ops": [[<op>, <digest>], ...]}

WORKSPACE OBJECT V1:

    {"id": "wob-...", "kind": "magnet", "ref": "mag-...", "curated": true,
     "provenance": {"source": {"kind": "participant", "ref": "ent-..."},
                    "brain"?: <id>, "by"?: <participant id>, "at"?: <seconds>},
     "observed"?: {"version"?: <text>, "at"?: <seconds>}}

`source` says where the reference came from, in the same kind/ref terms: chosen
directly by the owner is `participant`, found through a Magnet is `magnet`.
`observed` is what was seen when it was curated, at least one of the two; it is
never refreshed here.

REFS use what already exists (`_FORMS`): a Magnet's `mag-` id; a Conversation's
or participant's id in the shape arrangements take for a key; an admission's
`adm-`; a post's `ent-`; a citation as `mentis.sources.extract.cite` parses it; a
`live:<post>:<key>` or `brain:<entry>` address as zones keep them. Nothing in the
Python holds a chat's id apart from a Conversation's, so `chat` takes that shape.
`wsp-` is a workspace's and is none of those three, nor who curated something.
`other` is any bounded text, for what has no convention yet.

IDENTITY: a workspace's id is minted once and never changes: lower case, since
the file system may not tell case apart, and always prefixed, so never a device
name or a path. With an operation key it is derived from the key, so a retried
create finds what it made. An object's id is derived from kind and ref.

ORDER AND DUPLICATES: `objects` is the curated order. An addition goes last; only
`reorder`, given every id exactly once, moves anything. Kind and ref together ARE
the object: adding it again changes nothing and the first provenance stands, and
within one create the first stands. Removed and added again, it goes last.

UNKNOWN FIELDS are additive. Those a later V1 adds to a manifest, object,
provenance, source, observed or tombstone are kept through every write and
returned, within bounds, a tombstone's under `tombstone` in what is answered. A
file of any other `schema_version` or `format` is refused whole: a read says so
(`unreadable`), a mutation raises `Unreadable`, and it is left as it is.

MUTATIONS happen under arrangements' lock, whole file by temporary file and
rename (`mentis.fluid._checks`), and each may carry an operation key: the same
key and request answers `replayed` without writing, the same key for a different
request is a `Conflict`. A file remembers every key it was given, for good, so
this holds however many operations follow; what limits them is `MAX_BYTES`, so a
workspace can fill with keys, and then a request that would add one is refused
with every key still answering. Reads take the lock too, because Windows refuses
a rename over a file somebody has open. A request that would leave the file over
its bounds is refused before anything is touched. The lock is one process's,
which is what the arrangements assume.

DELETION is explicit and of the workspace only: `delete` replaces the file with a
tombstone holding its id, when, and its operation keys. Its name, objects and
unknown fields are gone. What they referred to -- the Magnets, Conversations,
files and any arrangement -- is not touched. A deleted id reads as deleted, is
never used again, and refuses mutation (`Gone`), while its keys still replay, so
a retried create or delete cannot bring it back. A tombstone is never removed:
the file IS the memory that the id was used, so their number is not bounded. A
delete with no key always fits, a tombstone holding less than its workspace; one
with a key may not, in a workspace full of keys.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import time
from typing import Literal, NotRequired, TypedDict

from mentis.fluid import _checks as W
from mentis.sources.extract import cite as _cite

FORMAT = "mentis.fluid-workspace"
SCHEMA_VERSION = 1
FOLDER = "fluid-workspaces"

KINDS = ("magnet", "conversation", "chat", "file", "image", "evidence",
         "report", "participant", "other")

MAX_BYTES = W.MAX_BYTES
MAX_WORKSPACES = 500
MAX_OBJECTS = 200
MAX_NAME = W.MAX_LABEL
MAX_REF = 1000
MAX_VERSION = 200
MAX_OP = 120
MAX_EXTRAS = 32
MAX_EXTRA_BYTES = 4096
MAX_EXTRA_DEPTH = 6
MAX_SECONDS = 1e11
MAX_REVISION = 2 ** 53

#: Names no manifest carries at any depth: layout and theme are presentation's,
#: and what a reference resolved to is not a curated reference.
RESERVED = frozenset({
    "layout", "layouts", "arrangement", "tree", "pages", "zones", "floats",
    "theme", "themes", "look", "looks", "appearance", "background",
    "presentation", "resolved", "resolution", "authoritative"})

_WORKSPACE_ID = re.compile(r"wsp-[a-z0-9_-]{1,60}")
_OBJECT_ID = re.compile(r"wob-[0-9a-f]{16}")
_MAGNET_REF = re.compile(r"mag-[A-Za-z0-9_-]{1,60}")
_ADMISSION_REF = re.compile(_cite.ADM)
_POST_REF = re.compile(r"ent-[0-9a-f]{8,76}")
_EXTRA_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,79}")
_DIGEST = re.compile(r"[0-9a-f]{64}")

Refused = W.Refused
Unreadable = W.Unreadable


class Conflict(ValueError):
    """An operation key already used for a different request, or an id already
    held by a workspace that was not made under this key."""


class NotFound(LookupError):
    """No workspace has this id."""


class Gone(LookupError):
    """This workspace was deleted, and its id is not used again."""


class ObjectSourceV1(TypedDict):
    kind: Literal["magnet", "conversation", "chat", "file", "image", "evidence",
                  "report", "participant", "other"]
    ref: str


class ProvenanceV1(TypedDict):
    source: ObjectSourceV1
    brain: NotRequired[str]
    by: NotRequired[str]
    at: NotRequired[float]


class ObservedV1(TypedDict, total=False):
    version: str
    at: float


class WorkspaceObjectV1(TypedDict):
    id: str
    kind: Literal["magnet", "conversation", "chat", "file", "image", "evidence",
                  "report", "participant", "other"]
    ref: str
    curated: Literal[True]
    provenance: ProvenanceV1
    observed: NotRequired[ObservedV1]


class WorkspaceManifestV1(TypedDict):
    format: Literal["mentis.fluid-workspace"]
    schema_version: Literal[1]
    id: str
    name: str
    revision: int
    created: float
    updated: float
    objects: list[WorkspaceObjectV1]


_SOURCE_FIELDS = frozenset(ObjectSourceV1.__annotations__)
_PROVENANCE_FIELDS = frozenset(ProvenanceV1.__annotations__)
_OBSERVED_FIELDS = frozenset(ObservedV1.__annotations__)
_OBJECT_FIELDS = frozenset(WorkspaceObjectV1.__annotations__)
_MANIFEST_FIELDS = frozenset(WorkspaceManifestV1.__annotations__) | {"ops"}
_TOMBSTONE_FIELDS = frozenset({"format", "schema_version", "id", "deleted", "ops"})


# -- checking: what the file holds is checked as what is sent is ----------------

def _is_id(v) -> bool:
    return bool(W._CONVERSATION.fullmatch(v)) and not v.startswith("wsp-")


def _is_magnet(v) -> bool:
    return bool(_MAGNET_REF.fullmatch(v))


def _is_admission(v) -> bool:
    return bool(_ADMISSION_REF.fullmatch(v))


def _is_post(v) -> bool:
    return bool(_POST_REF.fullmatch(v))


def _is_citation(v) -> bool:
    try:
        _cite.parse(v)
    except _cite.Malformed:
        return False
    return True


def _is_live(v) -> bool:
    parts = v.split(":", 2)
    return len(parts) == 3 and parts[0] == "live" and all(parts[1:])


def _is_brain(v) -> bool:
    return v.startswith("brain:") and bool(W._TURN.fullmatch(v[6:]))


def _is_any(v) -> bool:
    return True


_FORMS = {
    "magnet": (_is_magnet,),
    "conversation": (_is_id,),
    "chat": (_is_id,),
    "file": (_is_admission, _is_live),
    "image": (_is_admission, _is_live),
    "evidence": (_is_citation, _is_admission, _is_post, _is_live, _is_brain),
    "report": (_is_admission, _is_post, _is_live),
    "participant": (_is_id,),
    "other": (_is_any,),
}


def _kind(v, where) -> str:
    if not isinstance(v, str) or v not in KINDS:
        raise Refused(f"{where}: must be one of {list(KINDS)}")
    return v


def _ref(kind, v, where) -> str:
    v = W._text(v, where, most=MAX_REF)
    if v != v.strip() or not any(form(v) for form in _FORMS[kind]):
        raise Refused(f"{where}: {v!r} is not a reference to a {kind}")
    return v


def _seconds(v, where) -> float:
    return W._num(v, where, 0, MAX_SECONDS)


def _json(v, where, depth=0) -> None:
    """An unknown field's value: plain JSON, shallow, none of it `RESERVED`."""
    if depth > MAX_EXTRA_DEPTH:
        raise Refused(f"{where}: nested too deeply")
    if isinstance(v, dict):
        for k, x in v.items():
            _extra_name(k, where)
            _json(x, f"{where}.{k}", depth + 1)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _json(x, f"{where}[{i}]", depth + 1)
    elif isinstance(v, float):
        W._num(v, where, float("-inf"), float("inf"))
    elif not (v is None or isinstance(v, (bool, int, str))):
        raise Refused(f"{where}: {type(v).__name__} is not JSON")


def _extra_name(k, where) -> None:
    W._match(_EXTRA_NAME, k, f"{where}: field name")
    if k.casefold() in RESERVED:
        raise Refused(f"{where}.{k}: a workspace manifest does not carry this")


def _extras(v, known, where) -> dict:
    """What `v`, a mapping, holds beyond its `known` fields: kept, within bounds."""
    if not isinstance(v, dict):
        raise Refused(f"{where}: must be a mapping")
    out = {k: x for k, x in v.items() if k not in known}
    if len(out) > MAX_EXTRAS:
        raise Refused(f"{where}: at most {MAX_EXTRAS} further fields")
    for k, x in out.items():
        _extra_name(k, where)
        _json(x, f"{where}.{k}")
        if len(json.dumps(x)) > MAX_EXTRA_BYTES:
            raise Refused(f"{where}.{k}: larger than {MAX_EXTRA_BYTES} bytes")
    return out


def _provenance(v, where) -> dict:
    out = _extras(v, _PROVENANCE_FIELDS, where)
    s = v.get("source")
    src = _extras(s, _SOURCE_FIELDS, f"{where}.source")
    kind = _kind(s.get("kind"), f"{where}.source.kind")
    out["source"] = {**src, "kind": kind,
                     "ref": _ref(kind, s.get("ref"), f"{where}.source.ref")}
    if "brain" in v:
        out["brain"] = W._match(W._TURN, v["brain"], f"{where}.brain")
    if "by" in v:
        out["by"] = _ref("participant", v["by"], f"{where}.by")
    if "at" in v:
        out["at"] = _seconds(v["at"], f"{where}.at")
    return out


def _observed(v, where) -> dict:
    out = _extras(v, _OBSERVED_FIELDS, where)
    if "version" not in v and "at" not in v:
        raise Refused(f"{where}: a version, a time, or both")
    if "version" in v:
        out["version"] = W._text(v["version"], f"{where}.version",
                                 most=MAX_VERSION)
    if "at" in v:
        out["at"] = _seconds(v["at"], f"{where}.at")
    return out


def object_id(kind, ref) -> str:
    """The one id this kind and ref have, wherever they are curated."""
    text = f"{kind}\0{ref}".encode("utf-8", "surrogatepass")
    return "wob-" + hashlib.sha256(text).hexdigest()[:16]


def _object(v, where, *, stored=False) -> dict:
    """A `WorkspaceObjectV1`. What is sent may leave `id` and `curated` out; what
    is kept may not."""
    out = _extras(v, _OBJECT_FIELDS, where)
    kind = _kind(v.get("kind"), f"{where}.kind")
    ref = _ref(kind, v.get("ref"), f"{where}.ref")
    oid = object_id(kind, ref)
    if (stored or "id" in v) and v.get("id") != oid:
        raise Refused(f"{where}.id: this kind and ref have the id {oid}")
    if (stored or "curated" in v) and v.get("curated") is not True:
        raise Refused(f"{where}.curated: must be true")
    out.update(id=oid, kind=kind, ref=ref, curated=True,
               provenance=_provenance(v.get("provenance"),
                                      f"{where}.provenance"))
    if "observed" in v:
        out["observed"] = _observed(v["observed"], f"{where}.observed")
    return out


def _objects(v, where) -> list:
    """Sent: the first of each kind and ref stands."""
    if not isinstance(v, list) or len(v) > MAX_OBJECTS:
        raise Refused(f"{where}: a list of at most {MAX_OBJECTS} objects")
    out = {}
    for i, o in enumerate(v):
        got = _object(o, f"{where}[{i}]")
        out.setdefault(got["id"], got)
    return list(out.values())


def _name(v, where="name") -> str:
    return W._text(v, where, most=MAX_NAME, blank=True)


def _op(v):
    return None if v is None else W._text(v, "op", most=MAX_OP)


def _ops(v) -> list:
    if not isinstance(v, list):
        raise Refused("ops: a list of operation keys")
    for o in v:
        if not (isinstance(o, list) and len(o) == 2):
            raise Refused("ops: each is an [operation key, digest] pair")
        W._text(o[0], "ops: operation key", most=MAX_OP)
        W._match(_DIGEST, o[1], "ops: digest")
    return [list(o) for o in v]


def _known_version(data) -> str | None:
    """Why this build will not read `data` at all, or None."""
    if data.get("format") != FORMAT:
        return f"format {data.get('format')!r} is not a workspace manifest"
    v = data.get("schema_version")
    if type(v) is not int or v != SCHEMA_VERSION:
        return f"schema_version {v!r} is not one this build reads"
    return None


def _kept(data, wid) -> dict:
    """A file's whole content, checked; a tombstone has `deleted`."""
    if data.get("id") != wid:
        raise Refused(f"id: {data.get('id')!r} is not this file's")
    if "deleted" in data:
        for k in _MANIFEST_FIELDS - _TOMBSTONE_FIELDS:
            if k in data:
                raise Refused(f"{k}: a tombstone does not hold this")
        out = _extras(data, _TOMBSTONE_FIELDS, "tombstone")
        out.update(format=FORMAT, schema_version=SCHEMA_VERSION, id=wid,
                   deleted=_seconds(data["deleted"], "deleted"),
                   ops=_ops(data.get("ops")))
        return out
    out = _extras(data, _MANIFEST_FIELDS, "manifest")
    objects = data.get("objects")
    if not isinstance(objects, list) or len(objects) > MAX_OBJECTS:
        raise Refused(f"objects: a list of at most {MAX_OBJECTS} objects")
    objects = [_object(o, f"objects[{i}]", stored=True)
               for i, o in enumerate(objects)]
    if len({o["id"] for o in objects}) != len(objects):
        raise Refused("objects: the same object twice")
    revision = data.get("revision")
    if type(revision) is not int or not 1 <= revision <= MAX_REVISION:
        raise Refused(f"revision: {revision!r} is not one")
    out.update(format=FORMAT, schema_version=SCHEMA_VERSION, id=wid,
               name=_name(data.get("name")), revision=revision,
               created=_seconds(data.get("created"), "created"),
               updated=_seconds(data.get("updated"), "updated"),
               objects=objects, ops=_ops(data.get("ops")))
    return out


# -- the files --------------------------------------------------------------------

def _path(root, wid):
    W._match(_WORKSPACE_ID, wid, "workspace")
    folder = (W._dir(root) / FOLDER).resolve()
    path = (folder / f"{wid}.json").resolve()
    if path.parent != folder or path.name != f"{wid}.json":
        raise Refused(f"workspace: {wid!r} is not well formed")
    return path


def _on_disk(path, wid) -> tuple[dict | None, str | None]:
    """(what the file holds, why it is unreadable), read ONCE. Whatever is there,
    the answer is these two, never an exception, and nothing of a file that is
    not wholly a manifest is used -- not its operation keys either."""
    try:
        if path.stat().st_size > MAX_BYTES:
            return None, "the saved workspace is larger than a workspace can be"
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError, RecursionError):
        return None, "the saved workspace could not be read"
    if not isinstance(data, dict):
        return None, "the saved workspace is not one"
    why = _known_version(data)
    if why:
        return None, f"the saved workspace cannot be read: {why}"
    try:
        return _kept(data, wid), None
    except Refused as exc:
        return None, f"the saved workspace is not one: {exc}"
    except Exception as exc:                              # noqa: BLE001
        return None, f"the saved workspace is not one: {type(exc).__name__}"


def _readable(path, wid) -> dict | None:
    kept, why = _on_disk(path, wid)
    if why:
        raise Unreadable(f"{why}; it was left as it is")
    return kept


def _write(path, data) -> None:
    """Keep `data` whole, or refuse with the file as it was. The bound is on what
    a read will find: `_atomic` writes text, so each line ends as this platform's
    do, and a file over the bound would be unreadable, its keys with it."""
    try:
        text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)
        size = len(text.encode("utf-8")) + text.count("\n") * (len(os.linesep) - 1)
    except UnicodeEncodeError:
        raise Refused("the workspace holds text that is not valid Unicode") from None
    if size > MAX_BYTES:
        raise Refused(f"the workspace would be larger than {MAX_BYTES} bytes")
    W._atomic(path, data)


def _scan(root) -> list:
    """(id, what it holds, why it is unreadable) for each file, by id."""
    folder = W._dir(root) / FOLDER
    try:
        with os.scandir(folder) as it:
            names = sorted(e.name[:-5] for e in it if e.name.endswith(".json")
                           and _WORKSPACE_ID.fullmatch(e.name[:-5]))
    except FileNotFoundError:
        return []
    return [(wid, *_on_disk(_path(root, wid), wid)) for wid in names]


def _digest(request) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True,
                                     ensure_ascii=True).encode()).hexdigest()


def _replayed(kept, op, digest) -> dict | None:
    """The answer to an operation key already kept, or None."""
    if op is None:
        return None
    for k, d in kept["ops"]:
        if k != op:
            continue
        if d != digest:
            raise Conflict("operation key already used for a different request")
        return {**_answer(kept), "changed": False, "replayed": True}
    return None


def _answer(kept) -> dict:
    if "deleted" in kept:
        further = {k: v for k, v in kept.items() if k not in _TOMBSTONE_FIELDS}
        return {"id": kept["id"], "manifest": None, "deleted": kept["deleted"],
                **({"tombstone": further} if further else {})}
    return {"id": kept["id"],
            "manifest": {k: v for k, v in kept.items() if k != "ops"}}


def _remembered(ops, op, digest) -> list:
    return ops if op is None else ops + [[op, digest]]


# -- reading ----------------------------------------------------------------------

def workspace(root, wid) -> dict:
    """`{"id", "manifest"}`, with `manifest` null when there is none: none ever,
    `deleted` when it was, `unreadable` when it cannot be read."""
    path = _path(root, wid)
    with W._lock(root):
        kept, why = _on_disk(path, wid)
    if why:
        return {"id": wid, "manifest": None, "unreadable": why}
    return _answer(kept) if kept else {"id": wid, "manifest": None}


def workspaces(root) -> list:
    """Each workspace in brief, by id: deleted ones are not listed, and unreadable
    ones are, said why, so they are not lost to sight."""
    with W._lock(root):
        scanned = _scan(root)
    out = []
    for wid, kept, why in scanned:
        if why:
            out.append({"id": wid, "unreadable": why})
        elif kept and "deleted" not in kept:
            out.append({"id": wid, "name": kept["name"],
                        "objects": len(kept["objects"]),
                        "revision": kept["revision"],
                        "updated": kept["updated"]})
    return out


def curated_references(manifest) -> list:
    """The manifest's objects as the frozen V1 fields and nothing else: copies, in
    the curated order, with no unknown field. This is not a resolution."""
    out = []
    for o in manifest["objects"]:
        p = o["provenance"]
        got = {k: copy.deepcopy(o[k]) for k in _OBJECT_FIELDS - {"provenance"}
               if k in o}
        got["provenance"] = {k: p[k] for k in _PROVENANCE_FIELDS - {"source"}
                             if k in p}
        got["provenance"]["source"] = {k: p["source"][k] for k in _SOURCE_FIELDS}
        if "observed" in got:
            got["observed"] = {k: v for k, v in got["observed"].items()
                               if k in _OBSERVED_FIELDS}
        out.append(got)
    return out


# -- mutating ---------------------------------------------------------------------

def create(root, body) -> dict:
    """A new workspace from `{name?, objects?, op?}`, with whatever further fields
    it carries kept. Its id is minted, never sent."""
    if not isinstance(body, dict):
        raise Refused('send {"name"?: ..., "objects"?: [...], "op"?: ...}')
    for k in ("id", "revision", "created", "updated", "ops", "deleted"):
        if k in body:
            raise Refused(f"{k}: is the workspace's own, not sent")
    if "format" in body or "schema_version" in body:
        why = _known_version({"format": FORMAT, "schema_version": SCHEMA_VERSION,
                              **body})
        if why:
            raise Refused(why)
    op = _op(body.get("op"))
    extras = _extras(body, _MANIFEST_FIELDS | {"op"}, "manifest")
    name = _name(body.get("name", ""))
    objects = _objects(body.get("objects", []), "objects")
    digest = _digest({"do": "create", "name": name, "objects": objects,
                      "extras": extras})
    with W._lock(root):
        if op is None:
            wid = "wsp-" + secrets.token_hex(8)
        else:
            wid = "wsp-" + hashlib.sha256(op.encode("utf-8", "surrogatepass")
                                          ).hexdigest()[:16]
        path = _path(root, wid)
        kept = _readable(path, wid)
        if kept:
            replay = _replayed(kept, op, digest)
            if replay:
                return replay
            raise Conflict("this id is already held by a workspace not made "
                           "under this key; nothing was changed")
        live = sum(1 for _w, k, why in _scan(root)
                   if why or "deleted" not in k)
        if live >= MAX_WORKSPACES:
            raise Refused(f"at most {MAX_WORKSPACES} workspaces")
        now = time.time()
        kept = {**extras, "format": FORMAT, "schema_version": SCHEMA_VERSION,
                "id": wid, "name": name, "revision": 1, "created": now,
                "updated": now, "objects": objects,
                "ops": _remembered([], op, digest)}
        _write(path, kept)
    return {**_answer(kept), "changed": True, "replayed": False}


def _mutate(root, wid, body, request, change) -> dict:
    """One change to a workspace there is, under the lock: `change(kept)` makes it
    in place and says whether it changed anything."""
    if not isinstance(body, dict):
        raise Refused("send a mapping")
    path = _path(root, wid)
    op = _op(body.get("op"))
    digest = _digest({**request, "workspace": wid})
    with W._lock(root):
        kept = _readable(path, wid)
        if kept is None:
            raise NotFound(f"no workspace {wid}")
        replay = _replayed(kept, op, digest)
        if replay:
            return replay
        if "deleted" in kept:
            raise Gone(f"workspace {wid} was deleted")
        changed = change(kept)
        if changed:
            if kept["revision"] >= MAX_REVISION:
                raise Refused("revision: this workspace can change no further")
            kept["revision"] += 1
            kept["updated"] = time.time()
        if changed or op is not None:
            kept["ops"] = _remembered(kept["ops"], op, digest)
            _write(path, kept)
    return {**_answer(kept), "changed": changed, "replayed": False}


def rename(root, wid, body) -> dict:
    """`{name, op?}`."""
    if not isinstance(body, dict):
        raise Refused('send {"name": ..., "op"?: ...}')
    name = _name(body.get("name"))

    def change(kept):
        changed = kept["name"] != name
        kept["name"] = name
        return changed
    return _mutate(root, wid, body, {"do": "rename", "name": name}, change)


def add_object(root, wid, body) -> dict:
    """`{object, op?}`: last, or nothing if this kind and ref are already held.
    The answer names the object's id (`object`)."""
    if not isinstance(body, dict):
        raise Refused('send {"object": ..., "op"?: ...}')
    obj = _object(body.get("object"), "object")

    def change(kept):
        if any(o["id"] == obj["id"] for o in kept["objects"]):
            return False
        if len(kept["objects"]) >= MAX_OBJECTS:
            raise Refused(f"objects: at most {MAX_OBJECTS}")
        kept["objects"].append(obj)
        return True
    answer = _mutate(root, wid, body, {"do": "add", "object": obj}, change)
    return {**answer, "object": obj["id"]}


def remove_object(root, wid, oid, body=None) -> dict:
    """`{op?}`: this object out of this workspace, and nothing it refers to."""
    W._match(_OBJECT_ID, oid, "object")
    body = {} if body is None else body

    def change(kept):
        if not any(o["id"] == oid for o in kept["objects"]):
            raise NotFound(f"no object {oid} in workspace {wid}")
        kept["objects"] = [o for o in kept["objects"] if o["id"] != oid]
        return True
    return _mutate(root, wid, body, {"do": "remove", "object": oid}, change)


def reorder(root, wid, body) -> dict:
    """`{order, op?}`: every object's id, each once, in the new order."""
    if not isinstance(body, dict):
        raise Refused('send {"order": [...], "op"?: ...}')
    order = body.get("order")
    if not isinstance(order, list) or len(order) > MAX_OBJECTS:
        raise Refused(f"order: a list of at most {MAX_OBJECTS} object ids")
    order = [W._match(_OBJECT_ID, o, "order") for o in order]

    def change(kept):
        held = {o["id"]: o for o in kept["objects"]}
        if len(order) != len(held) or set(order) != set(held):
            raise Refused("order: every object in this workspace, each once")
        changed = order != [o["id"] for o in kept["objects"]]
        kept["objects"] = [held[o] for o in order]
        return changed
    return _mutate(root, wid, body, {"do": "reorder", "order": order}, change)


def delete(root, wid, body=None) -> dict:
    """`{op?}`: the workspace becomes its tombstone (see the module)."""
    body = {} if body is None else body
    if not isinstance(body, dict):
        raise Refused('send {"op"?: ...}')
    path = _path(root, wid)
    op = _op(body.get("op"))
    digest = _digest({"do": "delete", "workspace": wid})
    with W._lock(root):
        kept = _readable(path, wid)
        if kept is None:
            raise NotFound(f"no workspace {wid}")
        replay = _replayed(kept, op, digest)
        if replay:
            return replay
        if "deleted" in kept:
            raise Gone(f"workspace {wid} was deleted")
        tomb = {"format": FORMAT, "schema_version": SCHEMA_VERSION, "id": wid,
                "deleted": time.time(),
                "ops": _remembered(kept["ops"], op, digest)}
        _write(path, tomb)
    return {**_answer(tomb), "changed": True, "replayed": False}
