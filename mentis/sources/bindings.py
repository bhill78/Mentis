"""Machine-local root bindings: which folder on THIS machine a collection is.

NEVER IN THE BRAIN. A binding maps a collection identity to an absolute path,
and the absolute path is a fact about one machine. It is kept in a file
outside every corpus -- `MENTIS_SOURCE_BINDINGS`, or
`%LOCALAPPDATA%/Mentis/Mark-IV/source-bindings.json` -- keyed by the corpus's
own durable identity, so a copied or snapshotted corpus carries no binding
and a new machine must bind deliberately before it can sweep.

WHAT A BINDING IS NOT. It is not the collection (that is the recorded
declaration), and it certifies nothing about what is in the folder. Every
bind -- first, changed or recreated -- mints a fresh opaque binding token. The
sweep act records the token, never the path, and a sweep under a token the
record has not seen before must be explicitly acknowledged
(`mentis.sources.filesystem`).

Unbinding changes nothing in the record. Acquired material, its history and
its retained bytes are untouched by it.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import time
import uuid


#: Where the file keeps who unbound what. Beside the corpus ids it is keyed by,
#: and never one of them.
UNBOUND = "unbound"


def store_path() -> str:
    return os.environ.get("MENTIS_SOURCE_BINDINGS") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        "Mentis", "Mark-IV", "source-bindings.json")


def _inside(child: str, parent: str) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(child),
                                   os.path.normcase(parent)]) \
            == os.path.normcase(parent)
    except ValueError:              # different drives
        return False


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _save(path: str, doc: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".",
                               prefix=".bindings-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def is_reparse(st) -> bool:
    """A symlink, a junction, or any other reparse point (cloud placeholders
    included). `is_symlink` alone misses Windows junctions -- measured."""
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0) or 0
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _checked_root_for_file(root: str) -> str:
    from mentis.sources import Refused
    if not root or not os.path.isabs(root):
        raise Refused("a file binding needs an absolute path")
    try:
        st = os.lstat(root)
    except OSError as exc:
        raise Refused(f"cannot bind file: {exc}") from None
    if is_reparse(st) or not stat.S_ISREG(st.st_mode):
        raise Refused("bind an ordinary file, not a link or reparse point")
    return os.path.realpath(root)


def _checked_root(corpus, root: str, *, kind="folder") -> str:
    from mentis.sources import Refused
    if not root or not os.path.isabs(root):
        raise Refused("a binding needs an absolute folder path")
    try:
        st = os.lstat(root)
    except OSError as exc:
        raise Refused(f"cannot bind {root!r}: {exc}")
    if is_reparse(st):
        raise Refused(f"{root!r} is a symlink, junction or other reparse "
                      "point; bind the folder it names instead")
    if kind == "file":
        _checked_root_for_file(root)
    elif not stat.S_ISDIR(st.st_mode):
        raise Refused(f"{root!r} is not a folder")
    real = os.path.realpath(root)
    here = os.path.realpath(corpus.root)
    if _inside(here, real) or _inside(real, here):
        raise Refused("a collection root may not contain the corpus or lie "
                      "inside it: a sweep would acquire the record itself")
    return real


def bind(corpus, collection: str, root: str, written_by=None,
         extra: dict | None = None, *, kind="folder") -> dict:
    """Bind (or rebind) a declared collection to a folder on this machine.

    Returns the new opaque binding token. The path goes to the machine-local
    file and nowhere else. `extra` is what a connector keeps beside the
    path about where the folder came from -- a Git mirror's credential-free
    address (`mentis.sources.git`) -- machine-local exactly as the path is."""
    from mentis.sources import Refused, declaration
    # ANY CONNECTOR'S COLLECTION. A folder and a Git repository are both a
    # folder on this machine; what that folder must BE is the connector's to
    # check before it calls this (`git.Connector.bind`), and nothing about it
    # is recorded either way.
    decl = declaration(corpus, collection)
    if decl is None:
        raise Refused(f"{collection!r} is not a collection declared in this "
                      "corpus")
    if kind not in ("folder", "file") or (kind == "file" and decl["connector"] != "sqlite"):
        raise Refused("file bindings are for SQLite collections only")
    real = _checked_root(corpus, root, kind=kind)
    path = store_path()
    if _inside(os.path.realpath(path), os.path.realpath(corpus.root)):
        raise Refused("the machine-local binding file may not live inside "
                      "the corpus; it would travel with it")
    doc = _load(path)
    mine = doc.setdefault(corpus.corpus_id, {})
    was = mine.get(collection)
    mine[collection] = {"root": real, "binding": f"bnd-{uuid.uuid4().hex[:12]}",
                        "bound_at": time.time(),
                        # What the server observed of the request. The file
                        # is this machine's, never the record's.
                        "bound_by": written_by,
                        **{k: v for k, v in (extra or {}).items()
                           if k not in ("root", "binding", "bound_at",
                                        "bound_by")}}
    _save(path, doc)
    return {"collection": collection, "binding": mine[collection]["binding"],
            "replaced": was["binding"] if was else None,
            "note": "the path is kept on this machine only; the record will "
                    "see the binding token, never the path"}


def unbind(corpus, collection: str, written_by=None) -> dict:
    path = store_path()
    doc = _load(path)
    was = doc.get(corpus.corpus_id, {}).pop(collection, None)
    if was is not None:
        # Who unbound it, as the server observed the request -- kept in this
        # machine's file beside the bindings, as `bound_by` is, and never in
        # the record. The last unbind of each collection; a rebind leaves it.
        doc.setdefault(UNBOUND, {}).setdefault(corpus.corpus_id, {})[
            collection] = {"binding": was.get("binding"),
                           "unbound_at": time.time(),
                           "unbound_by": written_by}
    _save(path, doc)
    return {"collection": collection, "unbound": was is not None,
            "note": "nothing in the record changed; acquired material and "
                    "its retained bytes are untouched"}


def binding(corpus, collection: str) -> dict | None:
    return _load(store_path()).get(corpus.corpus_id, {}).get(collection)


def unbound(corpus, collection: str) -> dict | None:
    """The last unbind of `collection` on this machine, and who did it."""
    return _load(store_path()).get(UNBOUND, {}).get(
        corpus.corpus_id, {}).get(collection)
