"""The filesystem connector: declare, bind, plan, confirm.

  declare   record a collection in the Brain: a stable id, its name, who
            declared it and when, and the include/exclude filters that are
            its acquisition and absence scope. Append-only, an act.
  bind      tell THIS machine which folder the collection is
            (`mentis.sources.bindings`). Nothing is recorded.
  plan      survey the bound folder and preview exactly what a
            sweep would record against the latest recorded observations:
            new, changed, reappeared and absent objects, the bytes to be
            copied, every selected file that will not be acquired and why,
            and every part of the folder that could not be examined. Returns
            a plan id that names that preview. Stages the bytes of new,
            changed and reappeared files machine-locally; writes nothing to
            the record or held store.
  sweep     confirm the staged bytes and scope without reading the folder.
            Verify every staged file and admit it with held.put; re-hash the
            existing held copy of every unchanged object, refusing as
            held.put would. Recheck binding, scope and record inside the
            transaction.


SELECTION IS THE ACQUISITION BOUNDARY (Turn 29, A). Every selected file that
is acquired has its exact bytes retained, whatever its type. A file the
filters leave out is visible, may be a link target, and is never opened.

SAFETY ON THE WAY IN. Every reparse point -- symlink, junction, cloud
placeholder -- is refused and not followed, because `is_symlink` alone misses
Windows junctions (measured). Every folder is checked to resolve inside the
bound root. A file is opened and `fstat`ed, and refused if it is not the
object `lstat` saw. A folder that cannot be listed makes everything beneath
it unexamined, which withholds absence there rather than inferring it.
"""

from __future__ import annotations

import pathlib
import hashlib
import mimetypes
import os
import posixpath
import re
import stat
import sys
import time
import unicodedata
import urllib.parse
import uuid
from fnmatch import fnmatchcase

from mentis.sources import (DECLARED, OVER_HELD_LIMIT, SWEPT, PlanChanged,
                            Refused, apply, canonical, diff, effective_scope,
                            fingerprint, latest, observation, prepare,
                            record_revision)
from mentis.sources import bindings, lifecycle, sensitive
# THE LIFECYCLE THE CONNECTORS SHARE (`mentis.sources.lifecycle`). Re-imported
# so each is still `filesystem.X`, the same object: `runs.py` recognises
# `filesystem.Cancelled`, and the tests and `git.py` reach for these here.
from mentis.sources.lifecycle import (Cancelled, _Quiet, _binding_changed,
                                      _custody, _decided, _last_binding,
                                      _patterns, _plan_id, _preview)
# PRIVATE STAGING (Stage C), shared from `mentis.sources.lifecycle` so another
# connector can stage a preview the same way. Re-imported, so each is still
# `filesystem.X`; what the shared code reads from this connector -- the store,
# the tunables, `_survey`, `_cleanup_stage_blobs` -- it reads from this module
# when called, so replacing one here replaces it there.
from mentis.sources.lifecycle import (_PROCESS_TOKEN, _STAGE_LOCK, _STAGES,
                                      STAGE_CAP, STAGE_DISK_HEADROOM,
                                      STAGE_MEMORY_BYTES, STAGE_TOTAL_BYTES,
                                      STAGE_TTL, _admit_stage,
                                      _cleanup_stage_blobs, _inside,
                                      _is_process_alive, _is_stage_live,
                                      _process_start_time,
                                      _record_stage_owner, _remove_stage_dir)
from mentis.spine import held

CONNECTOR = "filesystem"

#: The link resolver's version. Part of every Markdown observation's
#: relations, so a change to how links are resolved is a relation change the
#: record shows, not one that silently disappears.
#:
#: `/2` STOPPED RECORDING `in_scope` (Sources slice 1, B3). Whether a target
#: is selected is a fact about the collection's scope NOW, and scopes are
#: revisable -- so recording it made relations, which are part of the stable
#: state `token` compares, change whenever the scope did: every linking
#: Markdown file would have been re-admitted as "changed" with identical bytes,
#: and every reference pinned to one would have falsely shown "newer version
#: exists". It is computed when read (`reading.links`), exactly like
#: "acquired". Every other field is kept, the resolved key included (G1): it
#: is what a later live render needs to locate a target.
RESOLVER = "markdown-links/2"

#: What wrote these records, honestly known.
WRITER = "filesystem-connector"

#: MEDIA TYPE FROM THE EXTENSION, AND THE SAME ON EVERY MACHINE. Found by
#: independent review: `mimetypes.guess_type` uses the module-level table,
#: which on Windows reads HKEY_CLASSES_ROOT, so the answer is a fact about the
#: software installed here rather than about the file. Measured on this
#: machine: 252 extensions differ from Python's own table -- `.csv` as
#: `application/vnd.ms-excel` rather than `text/csv`, `.zip` as
#: `application/x-zip-compressed`, and `.wav`, `.ico`, `.exe` and more.
#:
#: WHY THAT MATTERED RATHER THAN BEING COSMETIC: `payload_type` is inside
#: `STABLE`, the token that decides whether an observation is new. A
#: machine-local value in it meant the SAME unchanged bytes re-admitted as
#: "changed" on a second machine, or on this one after any installer rewrote a
#: MIME key -- appending a spurious version and double-counting
#: `counts.changed`. An own `MimeTypes` never reads the registry, so the
#: recorded type is a fact about the extension and replay stays honest.
_TYPES = mimetypes.MimeTypes()

_MARKDOWN = (".md", ".markdown")


#: This connector's private stages live under the source cache, here.
STAGE_DIR = "filesystem-stages"
_this = sys.modules[__name__]


def _serialized(fn):
    return lifecycle._serialized(_this, fn)


def _stage_cache(corpus):
    return lifecycle._stage_cache(_this, corpus)


def _abandon_stage(corpus, key):
    return lifecycle._abandon_stage(_this, corpus, key)


def _forget_stages(corpus, collection=None, root=None):
    return lifecycle._forget_stages(_this, corpus, collection=collection,
                                    root=root)


def _stage_budget(corpus, base, used):
    return lifecycle._stage_budget(_this, corpus, base, used)


def _over_budget(budget, wanted):
    return lifecycle._over_budget(_this, budget, wanted)


def _staged_survey(corpus, *args, **kwargs):
    return lifecycle._staged_survey(_this, corpus, *args, **kwargs)



def source_of(collection: str) -> str:
    return f"{CONNECTOR}:{collection}"


# -- the declaration: in the Brain, append-only --------------------------------

def declare(corpus, cv, *, name: str, include=None, exclude=None,
            declarer, written_by=None) -> dict:
    """Record a collection with this connector's declaration fields."""
    return lifecycle.declare(_this, corpus, cv, name=name, include=include,
                             exclude=exclude, declarer=declarer,
                             written_by=written_by)


def declarations(corpus) -> list[dict]:
    """This connector's collections. The reads list every connector's
    (`mentis.sources.declarations`); this is for what only a folder can do."""
    from mentis.sources import declarations as _all
    return [d for d in _all(corpus) if d.get("connector") == CONNECTOR]


def declaration(corpus, collection: str) -> dict | None:
    for d in declarations(corpus):
        if d["collection"] == collection:
            return d
    return None


def _matches(patterns, rel: str) -> bool:
    """A pattern matches a path or any folder above it. `*` crosses `/`."""
    parts = rel.split("/")
    cands = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    return any(fnmatchcase(c, p) for p in patterns for c in cands)


def selected(scope: dict, rel: str) -> bool:
    """Whether a scope -- the effective one, or a declaration, which has the
    same `include`/`exclude` -- selects a relative path."""
    return _matches(scope["include"], rel) and not _matches(scope["exclude"], rel)


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _within(within) -> tuple[str, str]:
    """(as typed, for the disk; as an identity prefix). Refuses escape."""
    if not within:
        return "", ""
    w = str(within).replace("\\", "/").strip("/")
    if (os.path.isabs(str(within)) or re.match(r"^[A-Za-z]:", w)
            or any(p in ("", ".", "..") for p in w.split("/"))):
        raise Refused(f"{within!r} is not a folder inside the collection")
    return w, _nfc(w)


def _spelled_on_disk(parent, comp) -> tuple[str | None, str | None]:
    """(the spelling this component really has, why it could not be told).

    A SOURCE IDENTITY IS THE NAME THE FILE SYSTEM HAS, so the spelling typed
    into `--within` cannot be allowed to become part of one. Windows opens
    `DoCs` and `docs.` for a folder named `docs`, so `lstat` succeeding says
    nothing about the name -- the directory has to be asked what its entries
    are really called.

    ACCEPTANCE IS EXACT BYTE EQUALITY. The loose case, NFC and trailing-dot
    matching below only decides what to SAY about a mismatch; it can never
    admit a spelling the directory does not have.

    TWO REASONS FOR NOT KNOWING, AND THEY ARE NOT THE SAME -- found by
    independent review. This returned None both for "no entry is called that"
    and for "the parent could not be listed at all", and the caller reported
    the first. Measured with a root that denies List Folder Contents: a
    correctly spelled `--within` was refused with "that is not how the folder
    is spelled on disk", sending the owner to rename a folder that was already
    right. Failing closed is correct; the reason has to be true.
    """
    try:
        with os.scandir(parent) as it:
            names = [e.name for e in it]
    except OSError as exc:
        return None, (f"the folder holding it could not be listed "
                      f"({type(exc).__name__}), so its real name could not "
                      f"be read")
    if comp in names:
        return comp, None
    wanted = {comp.casefold(), comp.rstrip(". ").casefold(),
              _nfc(comp).casefold(), _nfc(comp).rstrip(". ").casefold()}
    for name in names:
        if name.casefold() in wanted or _nfc(name).casefold() in wanted:
            return name, None
    return None, None


# -- reading one file, exactly --------------------------------------------------

class _Moved(Exception):
    pass


def _opened_path(fd: int, path: str) -> str:
    """Resolve the opened object, rather than a path that can be replaced."""
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        final_path = ctypes.WinDLL("kernel32", use_last_error=True).GetFinalPathNameByHandleW
        final_path.argtypes = (wintypes.HANDLE, wintypes.LPWSTR,
                               wintypes.DWORD, wintypes.DWORD)
        final_path.restype = wintypes.DWORD
        handle = msvcrt.get_osfhandle(fd)
        needed = final_path(handle, None, 0, 0)
        if not needed:
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_unicode_buffer(needed + 1)
        written = final_path(handle, buffer, len(buffer), 0)
        if not written or written >= len(buffer):
            raise OSError("cannot resolve the opened source handle")
        result = buffer.value
        if result.startswith("\\\\?\\UNC\\"):
            return "\\\\" + result[8:]
        return result[4:] if result.startswith("\\\\?\\") else result
    handle_path = f"/proc/self/fd/{fd}"
    if os.path.exists(handle_path):
        return os.path.realpath(handle_path)
    # No descriptor path facility: verify the path still names this handle.
    current = os.stat(path, follow_symlinks=False)
    opened = os.fstat(fd)
    if (current.st_ino, current.st_dev) != (opened.st_ino, opened.st_dev):
        raise _Moved()
    return os.path.realpath(path)


def _read_exact(path: str, st, *, root: str) -> bytes | None:
    """The file's bytes, or None if it is over what `held` accepts. Refuses a
    file that is not the object `lstat` saw (replaced between check and
    open). Bounded: never reads more than the held limit plus one byte."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
    try:
        fst = os.fstat(fd)
        if (not stat.S_ISREG(fst.st_mode)
                or (fst.st_ino, fst.st_dev) != (st.st_ino, st.st_dev)):
            raise _Moved()
        if not _inside(_opened_path(fd, path), root):
            raise _Moved()
        chunks, n = [], 0
        while n <= held.MAX_BYTES:
            b = os.read(fd, min(1 << 20, held.MAX_BYTES + 1 - n))
            if not b:
                break
            chunks.append(b)
            n += len(b)
        data = b"".join(chunks)
    finally:
        os.close(fd)
    return None if len(data) > held.MAX_BYTES else data


_BOMS = ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe\x00\x00", "utf-32-le"),
         (b"\x00\x00\xfe\xff", "utf-32-be"), (b"\xff\xfe", "utf-16-le"),
         (b"\xfe\xff", "utf-16-be"))


def encoding_of(data: bytes) -> dict:
    """What the bytes are, as far as is checked. Not a classifier: `text`
    means strict UTF-8 with no NUL, which is what a text page may be decoded
    as. Anything else is read as bytes."""
    bom = next((name for sig, name in _BOMS if data.startswith(sig)), None)
    try:
        data.decode("utf-8")
        utf8 = True
    except UnicodeDecodeError:
        utf8 = False
    nul = b"\x00" in data
    return {"bom": bom, "utf8_strict": utf8, "nul": nul,
            "text": utf8 and not nul}


# -- Markdown links: authored, and resolved separately ---------------------------

_FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.M | re.S)
#: An inline link or image: `[label](dest)` / `![alt](dest)`.
#:
#: A LINKED IMAGE IS TWO RELATIONS (`markdown-links/2`). Notes exported from
#: the web wrap nearly every image in a link to itself --
#: `[![alt](img.png)](img.png)` -- and the `/1` pattern stopped the outer
#: label at the image's own `]`, so it matched the OUTER link with the inner
#: image's destination and consumed the image: measured on the owner's D&D
#: folder, 791 of its 964 embeds were recorded as `links-to`. The label may
#: now hold one image, the outer link is read as a link, and images are found
#: by a pass of their own, so each is recorded as the embed it is.
_DEST = (r"\(\s*(<[^>\n]*>|[^)\s]+)"
         r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
_IMAGE = re.compile(r"!\[(?:[^\]\\\n]|\\.)*\]" + _DEST)
_LINK = re.compile(r"(?<!!)\[(?:!\[(?:[^\]\\\n]|\\.)*\]\([^)\n]*\)"
                   r"|[^\]\\\n]|\\.)*\]" + _DEST)
_REFDEF = re.compile(r"^ {0,3}\[([^\]\n]+)\]:\s*(<[^>\n]*>|\S+)", re.M)
_WIKI = re.compile(r"(!?)\[\[([^\]\n]+?)\]\]")


def _resolve(src: str, raw: str, syntax: str) -> dict:
    t = raw.strip()
    if t.startswith("<") and t.endswith(">"):
        t = t[1:-1]
    if syntax == "wiki":
        return {"resolution": "not-resolved", "resolved": None,
                "why": "a wiki link names a note, not a path; resolving it "
                       "is not built"}
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", t) and not re.match(
            r"^[A-Za-z]:[\\/]", t):
        return {"resolution": "external", "resolved": None}
    t = t.split("#", 1)[0].split("?", 1)[0]
    t = urllib.parse.unquote(t).replace("\\", "/")
    if not t:
        return {"resolution": "same-document", "resolved": None}
    if t.startswith("/") or re.match(r"^[A-Za-z]:", t):
        return {"resolution": "absolute", "resolved": None}
    j = posixpath.normpath(posixpath.join(posixpath.dirname(src), t))
    if j == ".." or j.startswith("../"):
        return {"resolution": "outside-collection", "resolved": None}
    # NO `in_scope` HERE, deliberately (`markdown-links/2`): see RESOLVER.
    return {"resolution": "in-collection", "resolved": _nfc(j)}


def links_of(src: str, text: str) -> list[dict]:
    """Every link as authored, with the resolver's answer beside it. Linking
    to something never acquires it, reads it or claims it exists."""
    body = _FENCE.sub("", text)
    found = []
    for m in _IMAGE.finditer(body):
        found.append((m.start(), "embeds", "inline", m.group(1)))
    for m in _LINK.finditer(body):
        found.append((m.start(), "links-to", "inline", m.group(1)))
    for m in _REFDEF.finditer(body):
        found.append((m.start(), "links-to", "reference", m.group(2)))
    for m in _WIKI.finditer(body):
        target = m.group(2).split("|", 1)[0].split("#", 1)[0]
        found.append((m.start(), "embeds" if m.group(1) else "links-to",
                      "wiki", target))
    out = []
    for _, rel, syntax, raw in sorted(found, key=lambda f: f[0]):
        out.append({"rel": rel, "syntax": syntax, "authored": raw,
                    "resolver": RESOLVER, **_resolve(src, raw, syntax)})
    return out


#: THE SAME PATTERNS OVER BYTES, so an embed's place in a held file is a
#: byte range in the units `read_source` and a search hit use. A pattern
#: kept in one spelling cannot disagree with the one that recorded the
#: relation.
_FENCE_B = re.compile(_FENCE.pattern.encode(), _FENCE.flags & ~re.U)
_IMAGE_B = re.compile(_IMAGE.pattern.encode())
_WIKI_B = re.compile(_WIKI.pattern.encode())


def embeds_in(data: bytes, start: int, end: int) -> list[dict]:
    """Every embed authored wholly inside `data[start:end]`, as `links_of`
    reads embeds, with its byte range in the file (Sources A, A1:
    `embeds_in_excerpt`). Each says `syntax` and `authored` exactly as the
    recorded relation does, so the record -- never this text -- decides
    what its target is. An embed inside a fenced code block is not one,
    as when it was recorded."""
    fences = [(m.start(), m.end()) for m in _FENCE_B.finditer(data)]
    out = []
    for pat, syntax in ((_IMAGE_B, "inline"), (_WIKI_B, "wiki")):
        for m in pat.finditer(data, start, end):
            if any(a <= m.start() < b for a, b in fences):
                continue
            if syntax == "wiki":
                if not m.group(1):
                    continue                     # a wiki LINK, not an embed
                raw = m.group(2).decode("utf-8", "replace")
                raw = raw.split("|", 1)[0].split("#", 1)[0]
            else:
                raw = m.group(1).decode("utf-8", "replace")
            out.append({"syntax": syntax, "authored": raw,
                        "offset": m.start(), "end": m.end()})
    out.sort(key=lambda r: r["offset"])
    return out


# -- the survey: source read, private local staging at preview ----------------

def _ready(corpus, collection) -> tuple[dict, dict]:
    decl = declaration(corpus, collection)
    if decl is None:
        raise Refused(f"{collection!r} is not a collection declared in this "
                      "corpus")
    bnd = bindings.binding(corpus, collection)
    if bnd is None:
        raise Refused(
            f"{collection!r} is not bound on this machine, so there is no "
            "folder to sweep. Nothing is inferred from that: acquired "
            "material and its retained bytes are unaffected. Bind it first.")
    root = bnd["root"]
    try:
        st = os.lstat(root)
    except OSError as exc:
        raise Refused(f"the bound folder is unavailable ({type(exc).__name__})"
                      "; nothing is inferred absent. Rebind or restore it.")
    if bindings.is_reparse(st) or not stat.S_ISDIR(st.st_mode) \
            or os.path.realpath(root) != root:
        raise Refused("the bound folder no longer resolves to the folder that "
                      "was bound; rebind it deliberately")
    return decl, bnd


def _excluded_by(patterns, rel: str) -> str | None:
    """The exclude pattern that leaves this path out, as `_matches` reads it."""
    parts = rel.split("/")
    cands = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    return next((p for p in patterns for c in cands if fnmatchcase(c, p)),
                None)


def _category_of_pattern(pattern: str | None) -> str | None:
    return next((c for c, d in sensitive.CATEGORIES.items()
                 if pattern in d["patterns"]), None)


#: K4 IS BOUNDED. Excluded folders are listed where the walk met them and
#: never entered; unselected files are counted by category and pattern.
BOUNDARY_CAP = 200
BOUNDARY_PATTERN_CAP = 100
UNSELECTED_CAP = 100
CATEGORY_FILES_CAP = 50


#: RAW GIT OBJECTS ARE NEVER ACQUIRED THROUGH THE FOLDER CONNECTOR (K6),
#: whatever the scope. Found by independent review: only the Repository
#: preset excluded `.git`, so a custom scope of `*` acquired loose objects.
#: Enforced here, in the survey, without rewriting anybody's scope: a path
#: with a `.git` component at any depth, in any case, is refused unread and
#: never entered, and its history is not examined -- so nothing previously
#: acquired under it is ever recorded absent.
GIT_REFUSAL = ("refused: Git metadata is never acquired through the folder "
               "connector; add the repository through the Git connector")


def _git_path(rel: str) -> bool:
    return any(p.lower() == ".git" for p in rel.split("/"))


def _not_selected(boundaries, unselected) -> dict:
    """What was discovered and left out, in a bounded, recordable shape.

    AN EXCLUDED FOLDER'S CONTENTS ARE UNKNOWN, NOT ZERO. The walk stops at
    its boundary (an excluded folder is never entered), so nothing beneath
    it was listed, counted or read; saying how much it holds would need the
    walk this deliberately does not do."""
    by_pattern: dict[str, int] = {}
    for b in boundaries:
        by_pattern[b["pattern"]] = by_pattern.get(b["pattern"], 0) + 1
    # CAPPED WITH ITS OWN FLAG. Found by independent review: one folder per
    # distinct exclude pattern grew this list without bound, and the path
    # list's flag did not describe it.
    patterns = sorted(by_pattern.items())
    groups = sorted(({"category": c, "pattern": p, "files": n}
                     for (c, p), n in unselected.items()),
                    key=lambda g: (-g["files"], g["pattern"] or "",
                                   g["category"] or ""))
    return {
        "excluded_folders": boundaries[:BOUNDARY_CAP],
        "excluded_folders_total": len(boundaries),
        "excluded_folders_truncated": len(boundaries) > BOUNDARY_CAP,
        "excluded_folders_by_pattern": [
            {"pattern": p, "category": _category_of_pattern(p), "folders": n}
            for p, n in patterns[:BOUNDARY_PATTERN_CAP]],
        "excluded_folders_by_pattern_total": len(patterns),
        "excluded_folders_by_pattern_truncated":
            len(patterns) > BOUNDARY_PATTERN_CAP,
        "excluded_folder_contents": "unknown",
        "excluded_folder_note": (
            "excluded folders are reported where the walk met them and are "
            "never entered, so the files and bytes inside them are unknown: "
            "not zero, and not complete"),
        "unselected_files": groups[:UNSELECTED_CAP],
        "unselected_files_total": sum(unselected.values()),
        "unselected_files_truncated": len(groups) > UNSELECTED_CAP,
    }


def repository_at(root: str) -> dict | None:
    """Whether the folder is a Git working tree, or inside one (K6).

    ONLY `lstat` OF A `.git` ENTRY, here and in each folder above: nothing
    is opened or run, and no path is returned, so this says where the
    repository top is relative to the folder (`levels_up`) and nothing else.
    It is an offer of the Git connector, never a collection or an
    association."""
    at, up = os.path.realpath(root), 0
    while True:
        try:
            os.lstat(os.path.join(at, ".git"))
            return {"detected": True, "at": "root" if up == 0 else "enclosing",
                    "levels_up": up, "offer": "git",
                    "note": ("this folder is a Git repository" if up == 0 else
                             "this folder is inside a Git repository")
                    + ". Its committed history can be added as a separate "
                      "Git collection through the Git connector; nothing is "
                      "added or associated automatically"}
        except OSError:
            pass
        parent = os.path.dirname(at)
        if not parent or parent == at:
            return None
        at, up = parent, up + 1


def _survey(corpus, scope, root, within, *, keep: bool,
            progress=None, sensitive_decisions=None, prior=None,
            category_decisions=None, stage_dir=None, budget=None) -> dict:
    """Walk the bound folder under a SCOPE -- the effective one, a proposed
    revision, or a draft's -- never the declaration's own filters directly,
    because a declaration is not necessarily what is in force."""
    progress = progress or _Quiet()
    choices = sensitive.decisions(sensitive_decisions)
    cchoices = sensitive.category_decisions(category_decisions)
    boundaries: list[dict] = []
    unselected: dict[tuple, int] = {}

    def leave_out(ident, pattern):
        cats = sensitive.categories_of(ident)
        key = (cats[0] if cats else None, pattern)
        unselected[key] = unselected.get(key, 0) + 1
    prior = prior or {}
    flags = []
    staged, in_memory = set(), {}
    staged_bytes = 0
    files, visible, refused, unexamined = [], [], [], []
    bound_git_metadata = any(p.lower() == ".git" for p in re.split(r"[\\/]", root))
    if bound_git_metadata:
        # Refuse before within resolution: its spelling checks list parents.
        # Nothing under this bound root is listed or inferred absent.
        refused.append({"path": "", "reason": GIT_REFUSAL})
    disk_within, within_id = _within(within)
    start = root
    if disk_within and not bound_git_metadata:
        # REFUSED BEFORE ANYTHING IS LISTED (K4, K6). Found by independent
        # review: `within` was walked from its own folder, so starting inside
        # an excluded one listed it while the preview said excluded folders
        # are never entered. Asked of the typed identity and every folder
        # above it; a spelling that differs from the disk is refused below
        # before the folder it names is listed.
        if _git_path(within_id):
            raise Refused(f"{within!r} is inside Git metadata, which is never "
                          "acquired through the folder connector; add the "
                          "repository through the Git connector. Nothing was "
                          "examined.")
        pattern = _excluded_by(scope["exclude"], within_id)
        if pattern is not None:
            raise Refused(f"{within!r} is inside a folder this scope excludes "
                          f"(by {pattern!r}), and excluded folders are never "
                          "entered. Nothing was examined.")
        for comp in disk_within.split("/"):
            parent = start
            start = os.path.join(start, comp)
            try:
                st = os.lstat(start)
            except OSError as exc:
                raise Refused(f"cannot examine {within!r}: "
                              f"{type(exc).__name__}")
            if bindings.is_reparse(st) or not stat.S_ISDIR(st.st_mode):
                raise Refused(f"{within!r} is not an ordinary folder in the "
                              "collection")
            # THE TYPED SPELLING MUST BE THE ONE ON DISK. Found by independent
            # review: `--within DoCs` for a folder named `docs` opened fine
            # and then built identities under `DoCs/`, so the same files were
            # admitted a SECOND time under a parallel identity -- and the next
            # full sweep recorded `absent` for paths that never existed. The
            # log is append-only, so neither could be taken back. Refused
            # rather than quietly corrected: which folder was meant is the
            # owner's to say, and a connector that re-spells what it was asked
            # for would be choosing an identity on their behalf.
            real, why_not = _spelled_on_disk(parent, comp)
            if why_not:
                # NOT A SPELLING COMPLAINT. The name could not be read at all,
                # so nothing is claimed about it.
                raise Refused(f"cannot confirm how {comp!r} in {within!r} is "
                              f"spelled: {why_not}. Nothing was examined.")
            if real != comp:
                raise Refused(
                    f"{within!r} is not how that folder is spelled on disk"
                    + (f": {comp!r} is {real!r}" if real else
                       f": nothing in that folder is called {comp!r}")
                    + ". A source identity is the name the file system has, "
                    "so sweeping this spelling would admit the same files "
                    "again under a second identity")
    #: Every on-disk spelling that produced each identity, so a
    #: normalisation clash can be refused with both real names.
    spellings: dict[str, list[str]] = {}
    stack = [] if bound_git_metadata else [(disk_within, start)]
    while stack:
        rel, d = stack.pop()
        progress.check()
        progress.folder(_nfc(rel))
        try:
            directory_state = os.lstat(d)
        except OSError as exc:
            unexamined.append({"path": _nfc(rel), "reason":
                               f"folder could not be listed ({type(exc).__name__})"})
            continue
        if bindings.is_reparse(directory_state):
            unexamined.append({"path": _nfc(rel),
                               "reason": "folder replaced by a reparse point"})
            continue
        if not _inside(os.path.realpath(d), root):
            unexamined.append({"path": _nfc(rel),
                               "reason": "resolves outside the bound folder"})
            continue
        try:
            with os.scandir(d) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            unexamined.append({"path": _nfc(rel), "reason":
                               f"folder could not be listed "
                               f"({type(exc).__name__})"})
            continue
        for e in entries:
            erel = f"{rel}/{e.name}" if rel else e.name
            ident = _nfc(erel)
            try:
                st = os.lstat(e.path)
            except OSError as exc:
                refused.append({"path": ident, "reason":
                                f"not examined ({type(exc).__name__})"})
                continue
            if bindings.is_reparse(st):
                refused.append({"path": ident, "reason":
                                "refused: a symlink, junction or other "
                                "reparse point; not followed"})
                continue
            if stat.S_ISDIR(st.st_mode):
                pattern = _excluded_by(scope["exclude"], ident)
                if pattern is None and _git_path(ident):
                    refused.append({"path": ident, "reason": GIT_REFUSAL})
                elif pattern is None:
                    stack.append((erel, e.path))
                else:
                    # THE BOUNDARY ONLY (K4): never entered, contents unknown.
                    cats = sensitive.categories_of(ident)
                    boundaries.append({"path": ident, "pattern": pattern,
                                       "category": cats[0] if cats else None,
                                       "contents": "unknown"})
                continue
            if not stat.S_ISREG(st.st_mode):
                refused.append({"path": ident,
                                "reason": "refused: not a regular file"})
                continue
            if not selected(scope, ident):
                visible.append(ident)
                leave_out(ident, _excluded_by(scope["exclude"], ident))
                continue
            if _git_path(ident):
                # A `.git` FILE (a worktree or submodule pointer), refused
                # unread like the folder.
                refused.append({"path": ident, "reason": GIT_REFUSAL})
                continue
            files.append((ident, e.path, st))
            spellings.setdefault(ident, []).append(erel)

    # TWO ON-DISK NAMES FOR ONE IDENTITY, SAID WITH BOTH NAMES. Found by
    # independent review: NTFS keeps `café.md` in NFC and in NFD as two files,
    # identity is the NFC relative path, and the generic duplicate guard in
    # `mentis.sources.apply` then refused the whole batch with the normalised
    # path only -- so the owner was told a collection could not be planned and
    # could not see which files to do anything about. `plan` refuses too, so
    # there was no way even to look. (A scope can now be revised, so an
    # exclude is one way out as well as a rename.)
    #
    # THE IDENTITY RULE IS UNCHANGED, deliberately: NFC stays canonical, and
    # one identity still cannot have two latest observations. What changed is
    # that the refusal is usable -- it names the actual spellings, so renaming
    # one is an obvious next step -- and that it happens HERE, where both
    # names are known, rather than two layers up where only the normalised one
    # survives. `apply`'s guard stays as the backstop for any other connector.
    clashes = {i: sorted(set(v)) for i, v in spellings.items()
               if len(set(v)) > 1}
    if clashes:
        shown = "; ".join(
            f"{i!r} is on disk as " + " and ".join(repr(x) for x in v)
            for i, v in sorted(clashes.items())[:5])
        raise Refused(
            f"{len(clashes)} source "
            f"{'identity' if len(clashes) == 1 else 'identities'} would come "
            f"from more than one file: {shown}. These differ only in Unicode "
            f"normalisation, so they are one source identity and cannot both "
            f"be its latest observation. Rename one of each pair, or revise "
            f"the scope to exclude one, and plan again. Nothing was recorded "
            f"and nothing was read.")

    observations, withheld = [], {}
    #: EVIDENCE CATEGORIES (K5): every selected file in one, by category.
    cat_new = {c: [] for c in sensitive.CATEGORIES}
    cat_admitted = {c: [] for c in sensitive.CATEGORIES}
    for ident, path, st in sorted(files, key=lambda f: f[0]):
        progress.check()
        progress.folder(posixpath.dirname(ident))
        rule = sensitive.rule(ident)
        previous = observation(prior.get(ident, {})).get("state") == "present"
        cats = sensitive.categories_of(ident)
        if not previous:
            for c in cats:
                cat_new[c].append((ident, st.st_size))
        if rule:
            choice = choices.get(ident)
            if previous and choice is not None:
                raise Refused("previously acquired flagged files cannot be changed by a sensitive decision; revise the scope explicitly")
            flags.append({"path": ident, "size": st.st_size, "rule": rule,
                          "previously_acquired": previous,
                          "decision": choice if not previous else None})
            if not previous and choice != "include":
                if choice == "exclude":
                    visible.append(ident)
                    leave_out(ident, "sensitive decision: exclude")
                else:
                    withheld[ident] = "sensitive file: explicit include/exclude decision required"
                continue
        # NO READ BEFORE CATEGORY CONSENT, as for a flagged file (K5). A file
        # already acquired keeps exact change detection and does not block.
        if cats and not previous:
            if any(cchoices.get(c) == "exclude" for c in cats):
                visible.append(ident)
                leave_out(ident, "category decision: exclude")
                continue
            pending = [c for c in cats if cchoices.get(c) != "include"]
            if pending:
                withheld[ident] = (
                    "evidence category ("
                    + ", ".join(sensitive.category_label(c) for c in pending)
                    + "): explicit category include/exclude decision "
                      "required")
                continue
        if st.st_size > held.MAX_BYTES:
            withheld[ident] = OVER_HELD_LIMIT
            continue
        try:
            data = _read_exact(path, st, root=root)
        except _Moved:
            withheld[ident] = "not acquired: replaced while being read"
            continue
        except OSError as exc:
            withheld[ident] = f"not acquired: unreadable ({type(exc).__name__})"
            continue
        if data is None:
            withheld[ident] = OVER_HELD_LIMIT
            continue
        digest = hashlib.sha256(data).hexdigest()
        # STAGE ONLY WHAT A CONFIRM WILL ADMIT. Bytes the record already
        # holds for this object, under this digest, are not copied: confirm
        # re-hashes that held copy instead, the same check held.put makes.
        unchanged = (previous and observation(prior[ident]).get("digest") == digest
                     and held.has(corpus.root, digest))
        if keep and not unchanged and digest not in staged:
            if staged_bytes + len(data) > budget["room"]:
                raise Refused(_over_budget(budget, staged_bytes + len(data)))
            if budget["memory"] + len(data) <= STAGE_MEMORY_BYTES:
                in_memory[digest] = data
                budget["memory"] += len(data)
            else:
                (pathlib.Path(stage_dir) / digest).write_bytes(data)
            staged.add(digest)
            staged_bytes += len(data)
        progress.read(len(data))
        enc = encoding_of(data)
        rels = []
        if ident.lower().endswith(_MARKDOWN) and enc["text"]:
            rels = links_of(ident, data.decode("utf-8"))
        if not previous:
            for c in cats:
                cat_admitted[c].append(ident)
        observations.append({
            "object": ident, "state": "present", "retention": "held",
            "digest": digest, "size": len(data),
            "payload_type": (_TYPES.guess_type(ident)[0]
                             or "application/octet-stream"),
            "encoding": enc, "relations": rels,
            "native": {"mtime_ns": st.st_mtime_ns,
                       "media_type_from": "extension"}})

    # Retained acquisitions remain readable even after leaving the live scope.
    # Report them from recorded metadata without opening an excluded/missing
    # file or changing its acquisition/absence semantics.
    reported = {f["path"] for f in flags}
    for ident, entry in sorted(prior.items()):
        rule = sensitive.rule(ident)
        if rule and ident not in reported:
            if ident in choices:
                raise Refused("previously acquired flagged files cannot be changed by a sensitive decision; revise the scope explicitly")
            flags.append({"path": ident, "size": observation(entry).get("size"),
                          "size_from": "record", "rule": rule,
                          "previously_acquired": True, "decision": None})
    flags.sort(key=lambda f: f["path"])
    if set(choices) - {f["path"] for f in flags}:
        raise Refused("a sensitive decision does not name a selected file in this preview; preview again")
    # ACQUIRED BEFORE, from the record, whatever the live scope now says:
    # reported, never blocking, never changed by a category decision.
    cat_recorded = {c: 0 for c in sensitive.CATEGORIES}
    for ident, entry in prior.items():
        if observation(entry).get("state") == "present":
            for c in sensitive.categories_of(ident):
                cat_recorded[c] += 1
    categories = []
    for c in sensitive.CATEGORIES:
        new = cat_new[c]
        if not new and not cat_recorded[c] and c not in cchoices:
            continue
        categories.append({
            "category": c, "label": sensitive.category_label(c),
            "decision": cchoices.get(c),
            "new_files": len(new), "new_bytes": sum(n for _, n in new),
            "files": [p for p, _ in new[:CATEGORY_FILES_CAP]],
            "files_truncated": len(new) > CATEGORY_FILES_CAP,
            "previously_acquired": cat_recorded[c],
            "admitted": cat_admitted[c] if cchoices.get(c) == "include"
            else []})
    if set(cchoices) - {c["category"] for c in categories if c["new_files"]}:
        raise Refused("a category decision names a category with nothing "
                      "new to acquire in this preview; preview again")
    final_scope = sensitive.scope_with_decisions(scope, choices, cchoices)
    blocked = [u["path"] for u in unexamined] + [r["path"] for r in refused]

    def examined(obj: str) -> bool:
        # NEVER ABSENT: whatever an earlier sweep acquired under `.git` keeps
        # its history and is not examined, whether or not it is still there.
        if _git_path(obj):
            return False
        if within_id and not (obj == within_id
                              or obj.startswith(within_id + "/")):
            return False
        for p in blocked:
            if p == "" or obj == p or obj.startswith(p + "/"):
                return False
        return selected(final_scope, obj)

    return {"sensitive_files": flags, "sensitive_decisions": choices,
            "category_decisions": cchoices, "categories": categories,
            "not_selected": _not_selected(boundaries, unselected),
            "observations": observations, "withheld": withheld,
            "visible": visible, "refused": refused, "unexamined": unexamined,
            "examined": examined, "within": within_id,
            "newly_written_digests": set(), "staged": staged,
            "in_memory": in_memory,
            "stage_dir": str(stage_dir), "staged_bytes": staged_bytes}


def _require_decisions(s):
    if not _decided(s):
        raise Refused("undecided sensitive files or evidence categories: "
                      "give each an include/exclude decision in a new preview")


# This holds only consent metadata, never source bytes. A confirm cannot add
# consent to an undecided preview and read a secret before rejecting its id.
_DECISION_PLANS = {}
DECISION_TTL = 60 * 60
DECISION_CAP = 128


def _remember_decisions(corpus, pid, s):
    now = time.time()
    for key, value in list(_DECISION_PLANS.items()):
        if now - value[0] > DECISION_TTL:
            _DECISION_PLANS.pop(key, None)
    if s["sensitive_decisions"] or s["category_decisions"]:
        while len(_DECISION_PLANS) >= DECISION_CAP:
            _DECISION_PLANS.pop(next(iter(_DECISION_PLANS)))
        _DECISION_PLANS[(corpus.corpus_id, pid)] = (
            now, (s["sensitive_decisions"], s["category_decisions"]),
            _decided(s))


def _check_decision_plan(corpus, pid, choices, categories=None):
    choices = sensitive.decisions(choices)
    categories = sensitive.category_decisions(categories)
    if choices or categories:
        got = _DECISION_PLANS.get((corpus.corpus_id, pid))
        if (got is None or time.time() - got[0] > DECISION_TTL
                or got[1] != (choices, categories) or not got[2]):
            raise Refused("sensitive decisions need a matching, fully decided preview; preview again")


def _proposed(eff: dict, scope) -> dict:
    """A proposed revision's scope, checked: the filters it would put in
    force, on top of the act it would revise."""
    if not isinstance(scope, dict):
        raise Refused("a scope is {include: [...], exclude: [...]}")
    inc = _patterns(scope.get("include"), ["*"])
    exc = _patterns(scope.get("exclude"), [])
    if (inc, exc) == (eff["include"], eff["exclude"]):
        raise Refused("that is already this collection's scope")
    return {"include": inc, "exclude": exc, "act": eff["act"],
            "revision": "proposed"}



def _plan_snapshot(corpus, cv, collection: str, *, within=None, scope=None,
         progress=None, sensitive_decisions=None,
         category_decisions=None) -> tuple:
    """Preview a sweep. Stages bytes machine-locally; no record or held writes.

    With `scope`, previews a REVISION: what a sweep under those filters
    would record. Nothing is revised until that plan is confirmed."""
    decl, bnd = _ready(corpus, collection)
    eff = effective_scope(corpus, collection, decl)
    under = _proposed(eff, scope) if scope is not None else eff
    prior = latest(corpus, source_of(collection))
    _forget_stages(corpus, collection=collection)
    s = _staged_survey(corpus, under, bnd["root"], within, keep=True,
                progress=progress, prior=prior, sensitive_decisions=sensitive_decisions,
                category_decisions=category_decisions)
    under = sensitive.scope_with_decisions(under, s["sensitive_decisions"],
                                           s["category_decisions"])
    revising = scope is not None or under["exclude"] != eff["exclude"]
    d = diff(prior, s["observations"], examined=s["examined"],
             withheld=set(s["withheld"]))
    changed, last = _binding_changed(corpus, collection, bnd["binding"], prior)
    pid = _plan_id({"collection": collection,
                    "declaration": decl["declaration"],
                    "binding": bnd["binding"]}, under, s, d, prior)
    _remember_decisions(corpus, pid, s)
    staged_digests = {o["object"]: o["digest"] for o, a, t in d["admit"]}
    _STAGES[(corpus.corpus_id, pid)] = {
        "at": time.time(),
        "collection": collection,
        "declaration": decl["declaration"],
        "binding": bnd["binding"],
        "root": bnd["root"],
        "within": s["within"],
        "scope": under,
        "eff_act": eff["act"],
        "revising": revising,
        "survey": s,
        "prior_fingerprint": fingerprint(prior),
        "staged_digests": staged_digests,
        "newly_written_digests": s.get("newly_written_digests", set()),
        "sensitive_decisions": s["sensitive_decisions"],
        "category_decisions": s["category_decisions"],
        "can_confirm": _decided(s),
    }
    return decl, bnd, eff, under, s, d, changed, pid


def _sweep_snapshot(corpus, cv, collection: str, plan_id: str, *, within=None,
          acknowledge_binding_change: bool = False, actor="human",
          written_by=WRITER, scope=None, because=None,
          progress=None, sensitive_decisions=None,
          category_decisions=None) -> tuple:
    """Validate and admit the private stage before opening the transaction."""
    progress = progress or _Quiet()
    _check_decision_plan(corpus, plan_id, sensitive_decisions,
                         category_decisions)
    decl, bnd = _ready(corpus, collection)
    source = source_of(collection)

    stage = _STAGES.get((corpus.corpus_id, plan_id))
    if stage is None:
        raise PlanChanged(f"{plan_id!r} is not what would be recorded now: "
                          "the preview was superseded, lost or expired; "
                          "Plan again.")
    if time.time() - stage["at"] > STAGE_TTL:
        _abandon_stage(corpus, (corpus.corpus_id, plan_id))
        raise PlanChanged(f"{plan_id!r} has expired (previews expire after {STAGE_TTL}s); "
                          "Plan again.")
    if not stage["can_confirm"]:
        raise Refused("undecided sensitive files or evidence categories: "
                      "give each an include/exclude decision in a new preview")
    if stage.get("collection") != collection:
        raise Refused(f"{plan_id!r} is not a preview of collection {collection!r}; "
                      "preview again")
    if stage.get("binding") != bnd["binding"]:
        raise PlanChanged("the collection binding changed since the preview"
                          + _custody(corpus, stage["survey"])
                          + " Plan again.")
    disk_within, within_id = _within(within)
    if disk_within:
        bound_git_metadata = any(p.lower() == ".git" for p in re.split(r"[\\/]", bnd["root"]))
        if not bound_git_metadata:
            if _git_path(within_id):
                raise Refused(f"{within!r} is inside Git metadata, which is never "
                              "acquired through the folder connector; add the "
                              "repository through the Git connector. Nothing was "
                              "examined.")
            eff0 = effective_scope(corpus, collection, decl)
            pattern = _excluded_by(eff0["exclude"], within_id)
            if pattern is not None:
                raise Refused(f"{within!r} is inside a folder this scope excludes "
                              f"(by {pattern!r}), and excluded folders are never "
                              "entered. Nothing was examined.")
    if (stage.get("within") or "") != (within_id or ""):
        raise Refused("within does not match the preview; preview again")

    prior0 = latest(corpus, source)
    changed, last = _binding_changed(corpus, collection, bnd["binding"],
                                     prior0)
    if changed and not acknowledge_binding_change:
        raise Refused(
            "this is the first sweep under a new or changed binding. A "
            "binding does not certify that the folder holds the same "
            "material, so nothing is recorded until the previewed differences "
            "are confirmed with acknowledge_binding_change.")

    eff = effective_scope(corpus, collection, decl)
    if eff["act"] != stage["eff_act"]:
        raise PlanChanged("this collection's scope was revised since "
                          "the preview" + _custody(corpus, stage["survey"])
                          + " Plan again.")
    under = stage["scope"]
    if scope is not None:
        supplied = sensitive.scope_with_decisions(
            _proposed(eff, scope), stage["sensitive_decisions"], stage["category_decisions"])
        if any(supplied[k] != under[k] for k in ("include", "exclude")):
            raise PlanChanged("scope does not match the previewed revision; preview again")
    revising = stage["revising"]

    _admit_stage(corpus, stage)

    s = stage["survey"]
    # The replay and diff, before the transaction rather than inside it (R1);
    # `apply` uses them only if this source has not moved since.
    prepared = prepare(corpus, source=source, observations=s["observations"],
                       examined=s["examined"], withheld=set(s["withheld"]))
    # CANCEL IS ALLOWED UNTIL THE TRANSACTION OPENS, and not after.
    progress.check()

    return decl, bnd, eff, under, s, changed, last, revising, prepared


NOUN = "folder"
PLAN_CHANGE_REASON = "binding, the scope or the record changed since it was previewed"


def _basis(collection, decl, bnd, s, scope):
    return {"collection": collection, "declaration": decl["declaration"],
            "binding": bnd["binding"]}


def _scope_view(scope):
    return {"include": scope["include"], "exclude": scope["exclude"]}


def _preview_result(corpus, s, d, pid, changed, bnd):
    return _preview(corpus, s, d, pid=pid, changed=changed)


def _confirm_scope(scope, under, s):
    return {"sensitive_decisions": s["sensitive_decisions"],
            "category_decisions": s["category_decisions"],
            **({"scope": scope} if scope is not None else {})}


def _sweep_detail(s, plan_id, bnd, changed, last, decl):
    return _act_detail(s, plan_id, bnd["binding"], changed, last,
                       decl["declaration"])


def _sweep_done(corpus, plan_id):
    _abandon_stage(corpus, (corpus.corpus_id, plan_id))


def _plan_extra(bnd):
    return {"repository": repository_at(bnd["root"])}


@_serialized
def plan(corpus, cv, collection: str, *, within=None, scope=None,
         progress=None, sensitive_decisions=None,
         category_decisions=None) -> dict:
    """Preview a sweep using this connector's snapshot policy."""
    return lifecycle.plan(_this, corpus, cv, collection, within=within,
                          scope=scope, progress=progress,
                          sensitive_decisions=sensitive_decisions,
                          category_decisions=category_decisions)


def _act_detail(s, plan_id, bnd_token, changed, last, decl_id) -> dict:
    return {"plan": plan_id, "binding": bnd_token,
            "sensitive_included": [p for p, c in s["sensitive_decisions"].items() if c == "include"],
            "sensitive_files": s["sensitive_files"],
            # CATEGORY CONSENT, RECORDED BY CATEGORY WITH WHAT IT ADMITTED,
            # and never as a claim that those files hold no secrets (K5).
            "category_decisions": s["category_decisions"],
            "category_included": {c["category"]: c["admitted"]
                                  for c in s["categories"]
                                  if c["decision"] == "include"},
            **({"category_note": sensitive.CONSENT_NOTE}
               if s["category_decisions"] else {}),
            "categories": [{k: v for k, v in c.items() if k != "admitted"}
                           for c in s["categories"]],
            # DISCOVERED BUT NOT ACQUIRED, part of the record (K4).
            "not_selected": s["not_selected"],
            "binding_changed": changed, "previous_binding": last,
            "declaration": decl_id, "resolver": RESOLVER,
            "not_acquired": [{"path": k, "reason": v} for k, v
                             in sorted(s["withheld"].items())],
            "refused": s["refused"], "unexamined": s["unexamined"],
            "visible_not_selected": len(s["visible"])}


@_serialized
def sweep(corpus, cv, collection: str, plan_id: str, *, within=None,
          acknowledge_binding_change: bool = False, actor="human",
          written_by=WRITER, scope=None, because=None,
          progress=None, sensitive_decisions=None,
          category_decisions=None) -> dict:
    """Confirm exactly the staged preview, in the shared transaction."""
    return lifecycle.sweep(_this, corpus, cv, collection, plan_id,
                           within=within, scope=scope, progress=progress,
                           acknowledge_binding_change=acknowledge_binding_change,
                           actor=actor, written_by=written_by, because=because,
                           sensitive_decisions=sensitive_decisions,
                           category_decisions=category_decisions)


# -- a new collection: previewed before anything is declared -------------------
#
# THE FLOW THE OWNER SEES IS name -> folder -> scope -> preview -> confirm, and
# the confirmation is "1 collection declared, N Admissions, 1 sweep". So a
# folder is previewed as a DRAFT: nothing is declared, nothing is bound and
# nothing is recorded. Confirming it declares, binds and sweeps as ONE
# transaction -- a plan that no longer matches leaves no declaration behind,
# and the machine-local binding is taken back with it. The draft itself is
# this process's memory only (it holds a path, which never enters the
# Brain); a restart forgets it and the owner previews again.
#
# AND IT IS BOUNDED (review note 5). Every preview of a new folder used to
# keep its draft until it was acquired, so previewing again and again grew
# memory without limit. A draft is superseded by the next preview of the same
# folder in the same corpus, expires after DRAFT_TTL, and at most DRAFT_CAP
# are kept; the oldest goes first. Confirming a draft that has gone is
# refused with "preview the folder again", which is what a restart says too.

_DRAFTS: dict[tuple[str, str], dict] = {}
DRAFT_TTL = 60 * 60            # seconds
DRAFT_CAP = 16


def _forget_drafts(corpus_id: str, root: str | None = None) -> None:
    return lifecycle.forget_drafts(_this, corpus_id, root)


@_serialized
def preview_new(corpus, *, name: str, root: str, include=None, exclude=None,
                progress=None, sensitive_decisions=None,
                category_decisions=None) -> dict:
    """Preview acquiring a folder that is not yet a collection."""
    name = (name or "").strip()
    if not name:
        raise Refused("a collection needs a name")
    inc = _patterns(include, ["*"])
    exc = _patterns(exclude, [])
    real = bindings._checked_root(corpus, root)
    _forget_stages(corpus, root=real)
    draft = f"draft-{uuid.uuid4().hex[:12]}"
    scope = {"include": inc, "exclude": exc, "act": draft}
    s = _staged_survey(corpus, scope, real, None, keep=True, progress=progress,
                sensitive_decisions=sensitive_decisions,
                category_decisions=category_decisions)
    base_exc = exc
    scope = sensitive.scope_with_decisions(scope, s["sensitive_decisions"],
                                           s["category_decisions"])
    exc = scope["exclude"]
    d = diff({}, s["observations"], examined=s["examined"],
             withheld=set(s["withheld"]))
    pid = _plan_id({"draft": draft, "name": name}, scope, s, d, {})
    _forget_drafts(corpus.corpus_id, real)
    staged_digests = {o["object"]: o["digest"] for o, a, t in d["admit"]}
    _STAGES[(corpus.corpus_id, pid)] = {
        "at": time.time(),
        "draft": draft,
        "name": name,
        "root": real,
        "include": inc,
        "exclude": exc,
        "base_exclude": base_exc,
        "scope": scope,
        "survey": s,
        "staged_digests": staged_digests,
        "newly_written_digests": s.get("newly_written_digests", set()),
        "sensitive_decisions": s["sensitive_decisions"],
        "category_decisions": s["category_decisions"],
        "can_confirm": _decided(s),
    }
    _DRAFTS[(corpus.corpus_id, draft)] = {"name": name, "root": real,
                                          "include": inc, "exclude": exc,
                                          "base_exclude": base_exc,
                                          "plan_id": pid,
                                          "sensitive_decisions": s["sensitive_decisions"],
                                          "category_decisions": s["category_decisions"],
                                          "can_confirm": _decided(s),
                                          "at": time.time()}
    return {"draft": draft, "collection": None, "name": name,
            **_preview(corpus, s, d, pid=pid, changed=False),
            "scope": {"include": inc, "exclude": exc, "act": None,
                      "revision": None},
            "repository": repository_at(real),
            "confirm": {"draft": draft, "plan": pid,
                        "acknowledge_binding_change": False}}


@_serialized
def acquire_new(corpus, cv, draft: str, plan_id: str, *, actor="human",
                written_by=WRITER, progress=None) -> dict:
    """Confirm a draft: declare, bind and sweep, or none of them."""
    progress = progress or _Quiet()
    _forget_drafts(corpus.corpus_id)
    if (corpus.corpus_id, draft) not in _DRAFTS:
        raise PlanChanged(f"{draft!r} is not a preview this server holds "
                          "(a restart forgets previews). Nothing was declared; preview the folder again.")
    stage = _STAGES.get((corpus.corpus_id, plan_id))
    if stage is None or stage.get("draft") != draft:
        raise PlanChanged(f"{draft!r} is not what would be recorded now: "
                          "the preview was superseded, lost or expired. "
                          "Nothing was declared. preview the folder again.")
    if time.time() - stage["at"] > STAGE_TTL:
        _abandon_stage(corpus, (corpus.corpus_id, plan_id))
        raise PlanChanged(f"{draft!r} has expired (previews expire after {STAGE_TTL}s). "
                          "Nothing was declared. preview the folder again.")
    if not stage["can_confirm"]:
        raise Refused("undecided sensitive files or evidence categories: "
                      "give each an include/exclude decision in a new preview")
    real = bindings._checked_root(corpus, stage["root"])

    _admit_stage(corpus, stage)

    s = stage["survey"]
    scope = stage["scope"]
    progress.check()

    def check(prior, d):
        now = _plan_id({"draft": draft, "name": stage["name"]}, scope, s, d,
                       prior)
        if now != plan_id:
            raise PlanChanged(
                f"{plan_id} is not what would be recorded now ({now}): the "
                "record changed since it was previewed" + _custody(corpus, s)
                + " Nothing was declared. Preview again.")

    bound = None
    try:
        with corpus.atomic():
            made = declare(corpus, cv, name=stage["name"],
                           include=stage["include"], exclude=stage["exclude"],
                           declarer=actor, written_by=written_by)
            col = made["collection"]
            bound = bindings.bind(corpus, col, real, written_by=written_by)
            out = apply(
                corpus, cv, source=source_of(col), collection=col,
                connector=CONNECTOR, observations=s["observations"],
                examined=s["examined"], withheld=set(s["withheld"]),
                scope={"declaration": made["declaration"], "revision": None,
                       "within": None},
                act_detail=_act_detail(s, plan_id, bound["binding"], False,
                                       None, made["declaration"]),
                actor=actor, written_by=written_by, check=check,
                observed_at=time.time())
    except BaseException:
        if bound is not None:
            bindings.unbind(corpus, bound["collection"],
                            written_by=written_by)
        raise
    _DRAFTS.pop((corpus.corpus_id, draft), None)
    _abandon_stage(corpus, (corpus.corpus_id, plan_id))
    return {**out, "collection": col, "declaration": made["declaration"],
            "binding": bound["binding"], "name": stage["name"]}


# -- this machine: binding state, the live file, choosing a folder -------------

def binding_state(corpus, collection: str) -> dict:
    """Machine-local binding metadata, without inspecting the source."""
    return lifecycle.binding_state(_this, corpus, collection)


def _opener(path: str) -> None:            # replaced in tests
    import subprocess
    if os.name != "nt":
        raise Refused("showing a file is only built for Windows Explorer")
    subprocess.Popen(["explorer.exe", f"/select,{path}"])


def reveal(corpus, collection: str, obj: str) -> dict:
    """Show this object's live file in Explorer (`live: local-reveal`, B8).

    NEVER RECORDED, AND THE PATH NEVER LEAVES THIS FUNCTION: not into the
    Brain, not into the answer. Every component is re-checked against the
    disk first -- each an ordinary folder, none a reparse point, its name
    the one entry on disk whose NFC form is the identity's -- and the file
    must still resolve inside the bound root. It reads no bytes and serves
    none: this is not a locator for serving (that is Slice 2's, and is not
    built).

    ONLY AN OBJECT THE RECORD HOLDS. The key must be one this collection has
    a recorded observation of; anything else is refused with one answer,
    before the disk is consulted, so this cannot be used to ask whether a
    file the record never acquired -- one the scope excludes, say -- exists
    in the bound folder (review note 4)."""
    try:
        decl, bnd = _ready(corpus, collection)
    except Refused as exc:
        why = str(exc)
        state = ("not bound on this machine" if "not bound" in why
                 else "folder unavailable")
        return {"revealed": False, "state": state, "why": why}
    key = _nfc(str(obj or "").replace("\\", "/").strip("/"))
    parts = key.split("/") if key else []
    if not parts or any(p in ("", ".", "..") for p in parts) \
            or re.match(r"^[A-Za-z]:", key):
        return {"revealed": False, "state": "refused",
                "why": "that is not an object key inside the collection"}
    if key not in latest(corpus, source_of(collection)):
        return {"revealed": False, "state": "refused",
                "why": "no observation of that object is recorded in this "
                       "collection"}
    at = bnd["root"]
    for i, comp in enumerate(parts):
        try:
            with os.scandir(at) as it:
                same = [e.name for e in it if _nfc(e.name) == comp]
        except OSError as exc:
            return {"revealed": False, "state": "unavailable",
                    "why": f"a folder could not be listed "
                           f"({type(exc).__name__})"}
        if len(same) != 1:
            return {"revealed": False, "state": "not found",
                    "why": "not found in the folder now" if not same else
                           "refused: two names on disk are this one object"}
        at = os.path.join(at, same[0])
        try:
            st = os.lstat(at)
        except OSError:
            return {"revealed": False, "state": "not found",
                    "why": "not found in the folder now"}
        if bindings.is_reparse(st):
            return {"revealed": False, "state": "refused",
                    "why": "refused: a link or junction"}
        last = i == len(parts) - 1
        if (not last and not stat.S_ISDIR(st.st_mode)) or \
                (last and not stat.S_ISREG(st.st_mode)):
            return {"revealed": False, "state": "not found",
                    "why": "not found in the folder now"}
    if not _inside(os.path.realpath(at), bnd["root"]):
        return {"revealed": False, "state": "refused",
                "why": "refused: resolves outside the bound folder"}
    _opener(at)
    return {"revealed": True, "state": "shown",
            "note": "opened on this machine; nothing was recorded"}


def folders(corpus, path: str | None = None) -> dict:
    """THE FOLDER CHOOSER: subfolders of one folder on this machine, or the
    places to start from. A local read, never recorded. Lists folders only;
    reparse points and the corpus are shown as refused, never entered."""
    here = os.path.realpath(corpus.root)
    if not path:
        starts = []
        if os.name == "nt":
            import string
            for letter in string.ascii_uppercase:
                d = f"{letter}:\\"
                if os.path.isdir(d):
                    starts.append({"name": d, "path": d})
        else:
            starts.append({"name": "/", "path": "/"})
        starts.append({"name": "Home", "path": os.path.expanduser("~")})
        return {"path": None, "parent": None, "folders": starts,
                "refused": None}
    if not os.path.isabs(path):
        raise Refused("choose a folder by its absolute path")
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise Refused(f"cannot open that folder ({type(exc).__name__})")
    if bindings.is_reparse(st) or not stat.S_ISDIR(st.st_mode):
        raise Refused("that is a link, junction or not a folder")
    real = os.path.realpath(path)
    out = []
    try:
        with os.scandir(real) as it:
            entries = sorted(it, key=lambda e: e.name.lower())
    except OSError as exc:
        raise Refused(f"that folder could not be listed ({type(exc).__name__})")
    for e in entries:
        try:
            est = os.lstat(e.path)
        except OSError:
            continue
        if bindings.is_reparse(est):
            out.append({"name": e.name, "path": None,
                        "refused": "a link or junction; not followed"})
            continue
        if not stat.S_ISDIR(est.st_mode):
            continue
        p = os.path.join(real, e.name)
        if _inside(here, p) or _inside(p, here):
            out.append({"name": e.name, "path": None,
                        "refused": "holds this Brain's record"})
            continue
        out.append({"name": e.name, "path": p})
    parent = os.path.dirname(real.rstrip("\\/")) or None
    if parent == real or (parent and os.path.normcase(parent)
                          == os.path.normcase(real)):
        parent = None
    refused = None
    if _inside(here, real) or _inside(real, here):
        refused = "this folder holds or lies inside this Brain's record"
    return {"path": real, "parent": parent, "folders": out,
            "refused": refused}


class Connector:
    """The filesystem connector over one corpus. Owner-side operations; a
    dispatched worker gets the reads only, through its grant
    (`mentis.worker`). `mentis.api.sources` hands a client the generic
    facade (`mentis.sources.registry.Sources`), which routes here."""

    def __init__(self, corpus, cv):
        self.corpus, self.cv = corpus, cv

    def declare(self, name, *, include=None, exclude=None, declarer="human",
                written_by=None):
        return declare(self.corpus, self.cv, name=name, include=include,
                       exclude=exclude, declarer=declarer,
                       written_by=written_by)

    def bind(self, collection, root, written_by=None):
        return bindings.bind(self.corpus, collection, root,
                             written_by=written_by)

    def unbind(self, collection, written_by=None):
        return bindings.unbind(self.corpus, collection,
                               written_by=written_by)

    def plan(self, collection, *, within=None, scope=None, progress=None,
             sensitive_decisions=None, category_decisions=None):
        return plan(self.corpus, self.cv, collection, within=within,
                    scope=scope, progress=progress, sensitive_decisions=sensitive_decisions,
                    category_decisions=category_decisions)

    def sweep(self, collection, plan_id, *, within=None,
              acknowledge_binding_change=False, actor="human", scope=None,
              because=None, progress=None, written_by=WRITER, sensitive_decisions=None,
              category_decisions=None):
        return sweep(self.corpus, self.cv, collection, plan_id, within=within,
                     acknowledge_binding_change=acknowledge_binding_change,
                     actor=actor, scope=scope, because=because,
                     progress=progress, written_by=written_by, sensitive_decisions=sensitive_decisions,
                     category_decisions=category_decisions)

    def preview_new(self, *, name, root, include=None, exclude=None,
                    progress=None, sensitive_decisions=None,
                    category_decisions=None):
        return preview_new(self.corpus, name=name, root=root, include=include,
                           exclude=exclude, progress=progress, sensitive_decisions=sensitive_decisions,
                           category_decisions=category_decisions)

    def acquire_new(self, draft, plan_id, *, actor="human", progress=None,
                    written_by=WRITER):
        return acquire_new(self.corpus, self.cv, draft, plan_id, actor=actor,
                           progress=progress, written_by=written_by)

    def binding_state(self, collection):
        return binding_state(self.corpus, collection)

    def reveal(self, collection, obj):
        return reveal(self.corpus, collection, obj)

    def folders(self, path=None):
        return folders(self.corpus, path)
