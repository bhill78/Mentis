"""Files and folders a Scratch question names: the `//` path selector's
listing, the references a question is sent with, and what Mentis itself does
with them around the answer (copy in, copy out, ZIP).

WHAT A REFERENCE IS. The owner types `//` in the Scratch question and picks a
file or folder; Enter picks it to READ, Shift+Enter picks it as a place to
WRITE. Each pick is a `PathRef` -- `{path, kind: file|folder, access:
read|write, exists, overwrite?}` -- shown as a chip and sent with the question
(`refs`). Navigating the listing grants nothing: only a sent reference does,
for that one question, and only to the runtime answering it.

WHAT EACH REFERENCE BECOMES (measured; see the plan
`ws-e-scratch-paths.md`):

* READ folder -- `--add-dir`. With nothing to write, the runtime gets only
  Read, Glob and Grep. With something to write, it gets the write tools AND a
  per-invocation deny rule for each READ folder, which the CLI enforces --
  measured to hold in two spellings and to be SILENTLY IGNORED in a third
  (`//C:/...`), so the adapter writes exactly the two that held.
* READ file -- Mentis copies it into the run's private scratch (`in/`); its
  folder is never given.
* WRITE folder -- `--add-dir` with the write tools, as before.
* WRITE file -- the runtime writes `out/<name>` in its private scratch, and
  Mentis copies it to the destination after the answer. Never over an
  existing file unless the owner confirmed replacing it for this question.
* WRITE `.zip` -- Mentis builds the ZIP itself, deterministically, from the
  question's READ references (or from `out/` when there are none). Same rule
  about existing files.

What Mentis writes is reported as written by Mentis, beside what the runtime
reported writing. None of this is recorded: it travels with the question, in
the Scratch, like the rest of its provenance.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import socket
import stat
import threading
import time
import zipfile



class Refused(ValueError):
    """A path, a reference or a file operation refused, with the reason.
    `mentis.web.scratch` says it to the owner as a Scratch refusal. (This
    module does not touch the Scratch store: only the Scratch routes do.)"""

#: How many references one question may carry.
MAX_REFS = 8
#: The listing: matches shown, entries looked at, time spent looking.
MAX_MATCHES = 50
SCAN_CAP = 5000
SCAN_BUDGET_S = 0.2
#: How long a listing may take before the drive is said to be slow.
LIST_TIMEOUT_S = 1.5
#: Listings still running after their timeout; past this many, say busy.
MAX_SLOW = 4
#: A READ file is copied in; these bound the copy.
READ_FILE_CAP = 25 * 1024 * 1024
READ_TOTAL_CAP = 50 * 1024 * 1024
#: A file copied out of the private scratch.
OUT_FILE_CAP = 200 * 1024 * 1024
#: A ZIP Mentis builds.
ZIP_FILES_CAP = 5000
ZIP_BYTES_CAP = 200 * 1024 * 1024
#: Walking a folder tree (a ZIP, or a READ folder copied in).
WALK_FOLDERS_CAP = 2000
WALK_S = 10.0
#: Every entry in a ZIP Mentis builds carries this time, so the same inputs
#: make the same bytes.
ZIP_TIME = (1980, 1, 1, 0, 0, 0)

_HIDDEN = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x2) | getattr(
    stat, "FILE_ATTRIBUTE_SYSTEM", 0x4)
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
#: Cloud files that are not on this disk (OneDrive "online-only").
_OFFLINE = 0x00400000 | 0x00040000 | 0x1000

PLAIN_ONLY = (r"choose a folder on this machine by its ordinary path "
              r"(for example C:\Users\you\Documents); \\?\, "
              r"\\.\ and network (UNC) paths are not accepted")


def device_or_network(path: str) -> bool:
    r"""A `\\?\` or `\\.\` device path, or a UNC/network path, in either
    slash. REFUSED, NOT NORMALISED (found by independent review): the check
    that keeps the Brain out compares path STRINGS, and these spellings of
    the same folder -- `\\?\<brain>`, `\\localhost\C$\...` -- slipped past
    it, and would name a whole drive as easily as one folder."""
    bare = path.replace("/", "\\")
    return bare.startswith("\\\\")


def _inside(child: str, parent: str) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(child),
                                   os.path.normcase(parent)]) \
            == os.path.normcase(parent)
    except ValueError:
        return False


def _reparse(st) -> bool:
    """A link, a junction, or any other reparse point -- cloud placeholders
    included (`sources.bindings.is_reparse`, the same test)."""
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool((getattr(st, "st_file_attributes", 0) or 0) & _REPARSE)


def _brain(corpus) -> str:
    return os.path.realpath(corpus.root)


def _touches_brain(path: str, here: str) -> bool:
    return _inside(here, path) or _inside(path, here)


# -- the listing ------------------------------------------------------------------

_drives_cache: list | None = None
_slow_lock = threading.Lock()
_slow = 0


def _drive_type(root: str) -> int:
    try:
        import ctypes
        return int(ctypes.windll.kernel32.GetDriveTypeW(root))
    except Exception:                                     # noqa: BLE001
        return 0


def _drives() -> list:
    """The drives on this machine, once per server process. No drive is
    opened to find them; a network drive is listed as refused."""
    global _drives_cache
    if _drives_cache is None:
        out = []
        if os.name == "nt":
            roots = (os.listdrives() if hasattr(os, "listdrives") else
                     [f"{c}:\\" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                      if os.path.exists(f"{c}:\\")])
            for root in roots:
                row = {"name": root, "path": root, "kind": "folder"}
                if _drive_type(root) == 4:              # DRIVE_REMOTE
                    row["refused"] = "a network drive; not offered"
                out.append(row)
        else:
            out.append({"name": "/", "path": "/", "kind": "folder"})
        _drives_cache = out
    return [dict(r) for r in _drives_cache]


def _split(prefix: str):
    """(folder to list, what is typed of the name) -- or a refusal."""
    raw = prefix.strip()
    if raw.startswith('"'):
        raw = raw[1:]
        if raw.endswith('"'):
            raw = raw[:-1]
    if device_or_network(raw):
        raise Refused(PLAIN_ONLY)
    cut = max(raw.rfind("\\"), raw.rfind("/"))
    if cut < 0:
        return None, raw
    return raw[:cut + 1], raw[cut + 1:]


def _scan(parent: str, typed: str, here: str) -> dict:
    """ONE folder, read once, in the order the disk gives it. Each entry's
    type and attributes come from the directory read itself (DirEntry), so
    nothing is opened or stat-ed one by one -- measured 95-630 ms on large
    folders when it was."""
    fold = typed.casefold()
    show_hidden = typed.startswith(".") or bool(typed and os.name == "nt"
                                                and typed[0] in "$~")
    found, scanned, more, partial = [], 0, False, False
    t_end = time.monotonic() + SCAN_BUDGET_S
    with os.scandir(parent) as it:
        for e in it:
            scanned += 1
            if scanned > SCAN_CAP or (scanned % 64 == 0
                                      and time.monotonic() > t_end):
                partial = True
                break
            if not e.name.casefold().startswith(fold):
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            attrs = getattr(st, "st_file_attributes", 0) or 0
            hidden = (attrs & _HIDDEN) if os.name == "nt" else \
                e.name.startswith(".")
            # SKIPPED UNLESS NAMED: hidden and system entries appear only
            # when what is typed names them (a leading `.`, `$`, or the
            # whole name).
            if hidden and not (show_hidden or e.name.casefold() == fold):
                continue
            if len(found) >= MAX_MATCHES:
                more = True
                break
            path = os.path.join(parent, e.name)
            is_dir = stat.S_ISDIR(st.st_mode)
            row = {"name": e.name, "path": path,
                   "kind": "folder" if is_dir else "file"}
            if _reparse(st):
                row["refused"] = ("a link or junction; not followed"
                                  if not attrs & _OFFLINE else
                                  "a cloud file that is not on this disk")
            elif _touches_brain(path, here):
                row["refused"] = "holds this Brain's record"
            elif not is_dir:
                if not stat.S_ISREG(st.st_mode):
                    row["refused"] = "not a plain file"
                else:
                    row["size"] = st.st_size
            found.append(row)
    found.sort(key=lambda r: (r["kind"] != "folder", r["name"].casefold()))
    return {"entries": found, "more": more, "partial": partial,
            "scanned": scanned}


def listing(corpus, prefix: str) -> dict:
    """What `//<prefix>` offers: the entries of ONE folder -- the one the
    typed path is in -- whose names start with what is typed after it.

    Bounded three ways: at most `MAX_MATCHES` entries (`more`), at most
    `SCAN_CAP` entries or `SCAN_BUDGET_S` seconds looked at (`partial`), and
    `LIST_TIMEOUT_S` for the whole read, on a thread of its own, after which
    the answer is that the drive is slow (`slow`) rather than a wait. Never
    recursive, never recorded. Links, junctions and cloud placeholders are
    listed as refused and never entered; so is anything holding the Brain."""
    host = socket.gethostname()
    base = {"host": host, "prefix": prefix, "parent": None, "entries": [],
            "more": False, "partial": False, "slow": False, "refused": None}
    try:
        parent, typed = _split(prefix or "")
    except Refused as exc:
        return {**base, "refused": str(exc)}
    if parent is None:
        # NOTHING TO LIST YET: a drive is what is typed first. Cheap and
        # cached; nothing is scanned.
        if os.name == "nt" and re.fullmatch(r"[A-Za-z]?:?", typed or ""):
            letter = (typed or "")[:1].upper()
            return {**base, "drives": True,
                    "entries": [d for d in _drives()
                                if d["name"].startswith(letter)]}
        if os.name != "nt" and not typed:
            return {**base, "drives": True, "entries": _drives()}
        return {**base, "refused": "start with a drive, like C:\\"
                if os.name == "nt" else "start with /"}
    if os.name == "nt" and re.fullmatch(r"[A-Za-z]:", parent[:2]) is None:
        return {**base, "refused": "start with a drive, like C:\\"}
    if not os.path.isabs(parent):
        return {**base, "refused": "start with a drive, like C:\\"
                if os.name == "nt" else "start with /"}
    here = _brain(corpus)
    norm = os.path.normpath(parent)
    holder: dict = {}

    def work():
        try:
            st = os.lstat(norm)
            if _reparse(st):
                raise Refused("that folder is a link or junction; "
                                     "it is not followed")
            if not stat.S_ISDIR(st.st_mode):
                raise Refused("no such folder on this machine")
            real = os.path.realpath(norm)
            if device_or_network(real):
                raise Refused(PLAIN_ONLY)
            # THROUGH A LINK SOMEWHERE ABOVE: the folder typed is not the
            # folder that would be read. Refused, said with the reason.
            if os.path.normcase(real) != os.path.normcase(
                    os.path.abspath(norm)):
                raise Refused(
                    f"that path goes through a link, a junction or a short "
                    f"name; it is {real} on disk -- type that instead")
            if _inside(real, here):
                raise Refused("that folder lies inside this Brain's "
                                     "record; Scratch never reaches it")
            holder["out"] = {"parent": real if real.endswith(os.sep)
                             else real + os.sep,
                             **_scan(real, typed, here)}
        except Refused as exc:
            holder["refused"] = str(exc)
        except FileNotFoundError:
            holder["refused"] = "no such folder on this machine"
        except PermissionError:
            holder["refused"] = "this folder cannot be read"
        except OSError as exc:
            holder["refused"] = (f"this folder could not be listed "
                                 f"({type(exc).__name__})")

    global _slow
    with _slow_lock:
        if _slow >= MAX_SLOW:
            return {**base, "slow": True,
                    "refused": "drives are slow to answer; try again shortly"}

    def run():
        global _slow
        try:
            work()
        finally:
            with _slow_lock:
                holder["done"] = True
                if holder.get("late"):
                    _slow -= 1
    t = threading.Thread(target=run, daemon=True, name="scratch-paths")
    t.start()
    t.join(LIST_TIMEOUT_S)
    with _slow_lock:
        if not holder.get("done"):
            holder["late"] = True
            _slow += 1
    if holder.get("late"):
        return {**base, "slow": True,
                "refused": "this drive is slow to answer; nothing was listed"}
    if "refused" in holder:
        return {**base, "refused": holder["refused"]}
    return {**base, **holder["out"]}


# -- the references a question is sent with -------------------------------------------

def _plain_name(name: str) -> bool:
    return bool(name) and name not in (".", "..") and not re.search(
        r'[<>:"/\\|?*\x00-\x1f]', name)


def _checked(corpus, raw, here) -> dict:
    """One reference, checked the way the folder chooser checks a folder
    (`mentis.sources.filesystem.folders`) and more: an ordinary absolute
    path, as typed AND as resolved; not a link or junction; not the Brain,
    nothing inside it, nothing holding it. Returned resolved."""
    if not isinstance(raw, dict):
        raise Refused("each file or folder is {path, kind, access}")
    path = raw.get("path")
    kind, access = raw.get("kind"), raw.get("access")
    if not isinstance(path, str) or not path.strip() or len(path) > 1024:
        raise Refused("each file or folder needs its path")
    path = path.strip()
    if kind not in ("file", "folder") or access not in ("read", "write"):
        raise Refused(f"{path}: kind is file or folder, access is "
                             "read or write")
    if device_or_network(path):
        raise Refused(f"{path}: {PLAIN_ONLY}")
    if not os.path.isabs(path) or (os.name == "nt" and not re.match(
            r"[A-Za-z]:[\\/]", path)):
        raise Refused(f"{path}: choose it by its absolute path")
    overwrite = raw.get("overwrite") is True
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        st = None
    except OSError as exc:
        raise Refused(f"{path}: cannot open it ({type(exc).__name__})")
    if st is None and not (kind == "file" and access == "write"):
        raise Refused(f"{path}: not found on this machine")
    if st is not None and _reparse(st):
        raise Refused(f"{path}: that is a link, junction or cloud "
                             "placeholder; it is not followed")
    if st is None:
        # A NEW FILE TO WRITE: its folder must exist, and is checked as one.
        parent, name = os.path.split(os.path.normpath(path))
        if not _plain_name(name):
            raise Refused(f"{path}: not a plain file name")
        try:
            pst = os.lstat(parent)
        except OSError:
            raise Refused(f"{path}: its folder {parent} does not exist")
        if _reparse(pst) or not stat.S_ISDIR(pst.st_mode):
            raise Refused(f"{path}: its folder is a link, junction or "
                                 "not a folder")
        real = os.path.join(os.path.realpath(parent), name)
        exists = False
    else:
        if kind == "folder" and not stat.S_ISDIR(st.st_mode):
            raise Refused(f"{path}: that is not a folder")
        if kind == "file" and not stat.S_ISREG(st.st_mode):
            raise Refused(f"{path}: that is not a plain file")
        real = os.path.realpath(path)
        exists = True
    # AND AS RESOLVED: a mapped or linked spelling can resolve to one.
    if device_or_network(real):
        raise Refused(f"{path}: {PLAIN_ONLY}")
    if (_inside(real, here) or (kind == "folder" and _inside(here, real))):
        raise Refused(f"{path}: this folder holds or lies inside this "
                             "Brain's record; Scratch never reaches it")
    if kind == "file" and access == "read" and st.st_size > READ_FILE_CAP:
        raise Refused(f"{path}: larger than {READ_FILE_CAP >> 20} MB; "
                             "choose its folder to read it in place")
    if kind == "file" and access == "write" and exists and not overwrite:
        raise Refused(f"{path}: already exists; allow replacing it "
                             "for this question, or choose another name")
    if kind == "file" and access == "write" and not _plain_name(
            os.path.basename(real)):
        raise Refused(f"{path}: not a plain file name")
    out = {"path": real, "kind": kind, "access": access, "exists": exists}
    if kind == "file" and access == "write" and overwrite:
        out["overwrite"] = True
    if kind == "file" and exists:
        out["size"] = st.st_size
    return out


def refs_of(corpus, body) -> list:
    """The files and folders the owner sent with this question, checked and
    resolved, in order. `access` (a list of folder paths) is the earlier form
    and still means what it meant: folders to read and write."""
    refs, legacy = body.get("refs"), body.get("access")
    raw = []
    if legacy not in (None, []):
        if (not isinstance(legacy, list) or len(legacy) > MAX_REFS
                or not all(isinstance(v, str) and v.strip() for v in legacy)):
            raise Refused(f"selected folders are a list of up to "
                                 f"{MAX_REFS} folder paths")
        raw += [{"path": p, "kind": "folder", "access": "write"}
                for p in legacy]
    if refs not in (None, []):
        if not isinstance(refs, list):
            raise Refused("refs is a list of files and folders")
        raw += refs
    if len(raw) > MAX_REFS:
        raise Refused(f"a question can name up to {MAX_REFS} files "
                             "and folders")
    here = _brain(corpus)
    out = []
    for r in raw:
        got = _checked(corpus, r, here)
        same = next((o for o in out if os.path.normcase(o["path"])
                     == os.path.normcase(got["path"])), None)
        if same is None:
            out.append(got)
        elif (same["kind"], same["access"]) != (got["kind"], got["access"]):
            raise Refused(f"{got['path']} is named twice, as "
                                 f"{same['access']} and {got['access']}")
    _consistent(out)
    # A READ FOLDER THAT WILL BE COPIED IN must fit, said now, before asking.
    for f in FilePlan(out).copied_folders:
        try:
            folder_members(f)
        except Refused as exc:
            raise Refused(
                f"{f}: its name has characters a permission rule cannot "
                f"name exactly, so in a question that also writes it is "
                f"copied in to keep it read-only -- and it cannot be ({exc}). "
                "Ask about it in a question that writes nothing, or choose "
                "a smaller folder")
        except OSError as exc:
            raise Refused(f"{f}: cannot be read ({type(exc).__name__})")
    return out


def _consistent(refs) -> None:
    """What one question's references can mean together."""
    reads = [r for r in refs if r["kind"] == "folder" and r["access"] == "read"]
    for w in refs:
        if w["kind"] == "folder" and w["access"] == "write":
            outer = next((r for r in reads if _inside(w["path"], r["path"])),
                         None)
            if outer:
                # A DENY ON THE OUTER FOLDER ALSO DENIES THE INNER ONE, and
                # making the outer one writable would widen what was chosen.
                raise Refused(
                    f"{w['path']} is inside {outer['path']}, which is chosen "
                    "to read only; the runtime cannot write in one while "
                    "keeping the other read-only. Make the outer folder "
                    "Write here, or choose a write folder outside it")
    names = {}
    for w in refs:
        if w["kind"] == "file" and w["access"] == "write":
            n = os.path.basename(w["path"]).casefold()
            if n in names:
                raise Refused(f"two files to write are both named "
                                     f"{os.path.basename(w['path'])}")
            names[n] = w
    total = sum(r.get("size", 0) for r in refs
                if r["kind"] == "file" and r["access"] == "read")
    if total > READ_TOTAL_CAP:
        raise Refused(f"the files to read add up to more than "
                             f"{READ_TOTAL_CAP >> 20} MB; choose their folder "
                             "to read them in place")


def is_zip(ref) -> bool:
    return (ref["kind"] == "file" and ref["access"] == "write"
            and ref["path"].lower().endswith(".zip"))


class FilePlan:
    """What one question's references mean for its run."""

    def __init__(self, refs):
        self.refs = list(refs)
        self.read_folders = [r["path"] for r in refs
                             if r["kind"] == "folder" and r["access"] == "read"]
        self.write_folders = [r["path"] for r in refs
                              if r["kind"] == "folder"
                              and r["access"] == "write"]
        self.read_files = [r for r in refs
                           if r["kind"] == "file" and r["access"] == "read"]
        self.zips = [r for r in refs if is_zip(r)]
        self.write_files = [r for r in refs if r["kind"] == "file"
                            and r["access"] == "write" and not is_zip(r)]
        reads_any = bool(self.read_folders or self.read_files)
        #: Whether the runtime itself writes anything: in a WRITE folder, or
        #: into `out/` for Mentis to copy or ZIP.
        self.writes = bool(self.write_folders or self.write_files
                           or (self.zips and not reads_any))
        #: READ FOLDERS A DENY RULE CANNOT NAME EXACTLY, in a question that
        #: writes: never given to the runtime -- copied in, read-only by being
        #: a copy (found by review: `rd [x]` was written through its rule).
        from mentis.foundation.runtimes.claude import rule_expressible
        self.copied_folders = [f for f in self.read_folders
                               if self.writes and not rule_expressible(f)]
        given = [f for f in self.read_folders if f not in self.copied_folders]
        #: The folders given to the runtime (`--add-dir`): write, then read.
        self.access = tuple(self.write_folders + given)
        #: Of those, the ones it must not change.
        self.read_only = tuple(given) if self.writes else ()
        self.files = "write" if self.writes else "read"
        # WHERE EACH COPY SITS in the private scratch: (ref, rel path).
        self.copies, taken = [], set()
        folder_refs = [r for r in refs if r["kind"] == "folder"
                       and r["path"] in self.copied_folders]
        for r in self.read_files + folder_refs:
            name = os.path.basename(r["path"].rstrip("\\/")) or "drive"
            rel, k = f"in/{name}", 1
            while rel.casefold() in taken:
                k += 1
                rel = f"in/{k}/{name}"
            taken.add(rel.casefold())
            self.copies.append((r, rel))

    def __bool__(self):
        return bool(self.refs)

    def legacy(self) -> bool:
        """Only WRITE folders: exactly what a question sent before refs."""
        return bool(self.refs) and len(self.write_folders) == len(self.refs)

    def lines(self) -> list[str]:
        """Each reference, as the answerer is told it."""
        out = []
        for f in self.read_folders:
            if f not in self.copied_folders:
                out.append(f"- READ ONLY (folder): {f} -- read anything in "
                           "it; do not create or change files there.")
        for r, rel in self.copies:
            out.append(f"- READ ONLY ({r['kind']}): {r['path']} -- a copy is "
                       f"at {rel}{'/' if r['kind'] == 'folder' else ''} in "
                       "your working directory; read the copy, the original "
                       "is not reachable.")
        for f in self.write_folders:
            out.append(f"- WRITE HERE (folder): {f} -- you may read, create "
                       "and change files in it.")
        for r in self.write_files:
            name = os.path.basename(r["path"])
            out.append(f"- WRITE THIS FILE: {r['path']} -- write it as "
                       f"out/{name} in your working directory (the "
                       "destination itself is not reachable by your tools); "
                       "Mentis copies it there after you finish"
                       + (" (replacing the existing file, as the owner "
                          "allowed)." if r.get("overwrite") else
                          " (it will not replace an existing file)."))
        for r in self.zips:
            src = ("the READ items above" if (self.read_folders
                                              or self.read_files)
                   else "everything you write into out/ in your working "
                        "directory")
            out.append(f"- ZIP: {r['path']} -- Mentis builds this ZIP itself "
                       f"after you answer, from {src}. Do not try to make a "
                       "ZIP yourself; say what it will contain.")
        return out


# -- around the run: copy in, copy out, ZIP -----------------------------------------------

def _open_plain(path: str):
    """`path` opened for reading, and the OPENED file checked to be the plain
    file `lstat` names -- not a link swapped in between the look and the
    open (same device and inode, a regular file)."""
    before = os.lstat(path)
    if _reparse(before) or not stat.S_ISREG(before.st_mode):
        raise Refused(f"{path}: not a plain file")
    fh = open(path, "rb")
    try:
        now = os.fstat(fh.fileno())
        if (not stat.S_ISREG(now.st_mode)
                or (now.st_ino, now.st_dev) != (before.st_ino, before.st_dev)):
            raise Refused(f"{path}: changed while it was being opened")
    except BaseException:
        fh.close()
        raise
    return fh


def _copy_capped(src: str, out, cap: int) -> int:
    """Copy `src` (checked as it is opened) into the open file `out`, never
    more than `cap` bytes whatever the file claimed to be. Returns bytes."""
    n = 0
    with _open_plain(src) as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                return n
            n += len(chunk)
            if n > cap:
                raise Refused(f"{src}: larger than the copy limit")
            out.write(chunk)


def _copy_in(src: str, dest: str, cap: int) -> int:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "xb") as out:
        return _copy_capped(src, out, cap)


def folder_members(folder: str, cap_files: int = 2000) -> list:
    """Every plain file of a READ folder that is copied in: (rel, path, size),
    bounded in files, folders, time and bytes -- or refused, with why."""
    top = os.lstat(folder)
    if _reparse(top) or not stat.S_ISDIR(top.st_mode):
        raise Refused(f"{folder} is no longer a plain folder")
    members: list = []
    _walk(folder, "", "", members, limit=cap_files)
    if sum(m[2] for m in members) > READ_TOTAL_CAP:
        raise Refused(f"{folder} holds more than {READ_TOTAL_CAP >> 20} MB")
    return members


def stage(plan: FilePlan, scratch: str) -> None:
    """Copy each READ file -- and each READ folder a deny rule cannot name --
    into the private scratch, checked again now and capped as it is read."""
    left = READ_TOTAL_CAP
    for r, rel in plan.copies:
        base = os.path.join(scratch, *rel.split("/"))
        if r["kind"] == "file":
            left -= _copy_in(r["path"], base, min(READ_FILE_CAP, left))
            continue
        os.makedirs(base, exist_ok=True)
        for sub, path, _ in folder_members(r["path"]):
            left -= _copy_in(path, os.path.join(base, *sub.split("/")),
                             min(READ_FILE_CAP, left))
    if plan.write_files or (plan.zips and plan.writes):
        os.makedirs(os.path.join(scratch, "out"), exist_ok=True)


def _place(tmp: str, dest: str, overwrite: bool) -> None:
    """Put a finished file at `dest`. NEVER OVER AN EXISTING FILE unless the
    owner said so: the check is the rename itself, not a look beforehand.
    And its folder is looked at once more, immediately before: a folder
    swapped for a link or junction since it was checked is not written
    through."""
    pst = os.lstat(os.path.dirname(dest))
    if _reparse(pst) or not stat.S_ISDIR(pst.st_mode):
        raise Refused("its folder is now a link, junction or not a folder")
    if overwrite:
        os.replace(tmp, dest)
    elif os.name == "nt":
        os.rename(tmp, dest)              # refuses an existing destination
    else:
        os.link(tmp, dest)                # refuses an existing destination
        os.unlink(tmp)


def _dest_ok(corpus, ref) -> str | None:
    """The destination, checked again at the moment of writing."""
    dest = ref["path"]
    parent = os.path.dirname(dest)
    try:
        pst = os.lstat(parent)
    except OSError:
        return f"its folder {parent} is gone"
    if _reparse(pst) or not stat.S_ISDIR(pst.st_mode):
        return "its folder is now a link, junction or not a folder"
    real = os.path.realpath(parent)
    if device_or_network(real) or _touches_brain(
            os.path.join(real, os.path.basename(dest)), _brain(corpus)):
        return "its folder is not one Scratch may write in"
    try:
        st = os.lstat(dest)
    except FileNotFoundError:
        return None
    if _reparse(st) or not stat.S_ISREG(st.st_mode):
        return "something that is not a plain file is there now"
    if not ref.get("overwrite"):
        return "a file is there now, and replacing it was not confirmed"
    return None


def _tmp_beside(dest: str) -> str:
    return os.path.join(os.path.dirname(dest),
                        f".{os.path.basename(dest)}.mentis-{secrets.token_hex(4)}")


def copy_out(corpus, ref, scratch: str) -> dict:
    name = os.path.basename(ref["path"])
    src = os.path.join(scratch, "out", name)
    row = {"by": "mentis", "tool": "copy", "path": ref["path"],
           "from": f"out/{name}"}
    try:
        st = os.lstat(src)
    except OSError:
        return {**row, "outcome": "not written",
                "why": f"the answer did not write out/{name}"}
    if _reparse(st) or not stat.S_ISREG(st.st_mode):
        return {**row, "outcome": "refused", "why": "not a plain file"}
    if st.st_size > OUT_FILE_CAP:
        return {**row, "outcome": "refused",
                "why": f"larger than {OUT_FILE_CAP >> 20} MB"}
    why = _dest_ok(corpus, ref)
    if why:
        return {**row, "outcome": "refused", "why": why}
    tmp = _tmp_beside(ref["path"])
    try:
        with open(tmp, "xb") as out:
            size = _copy_capped(src, out, OUT_FILE_CAP)
        _place(tmp, ref["path"], bool(ref.get("overwrite")))
    except Refused as exc:
        return {**row, "outcome": "refused", "why": str(exc)}
    except FileExistsError:
        return {**row, "outcome": "refused",
                "why": "a file appeared there first; it was not replaced"}
    except OSError as exc:
        return {**row, "outcome": "refused",
                "why": f"could not be written ({type(exc).__name__})"}
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {**row, "outcome": "done", "size": size}


def _walk(top: str, arc: str, skip: str, out: list, *,
          limit: int = ZIP_FILES_CAP, _budget: dict | None = None) -> None:
    """Every plain file under `top`, links and junctions NOT followed --
    bounded in files (`limit`), folders (`WALK_FOLDERS_CAP`) and time
    (`WALK_S`), past any of which it is refused rather than cut short."""
    budget = _budget if _budget is not None else {
        "folders": 0, "until": time.monotonic() + WALK_S}
    budget["folders"] += 1
    if budget["folders"] > WALK_FOLDERS_CAP:
        raise Refused(f"more than {WALK_FOLDERS_CAP} folders")
    if time.monotonic() > budget["until"]:
        raise Refused(f"reading the folders took longer than {WALK_S} seconds")
    with os.scandir(top) as it:
        entries = sorted(it, key=lambda e: e.name)
    for e in entries:
        st = e.stat(follow_symlinks=False)
        if _reparse(st):
            continue
        name = f"{arc}/{e.name}" if arc else e.name
        if stat.S_ISDIR(st.st_mode):
            _walk(e.path, name, skip, out, limit=limit, _budget=budget)
        elif stat.S_ISREG(st.st_mode) and os.path.normcase(
                e.path) != os.path.normcase(skip):
            out.append((name, e.path, st.st_size))
        if len(out) > limit:
            raise Refused(f"more than {limit} files")


def zip_members(plan: FilePlan, ref, scratch: str) -> list:
    """(name in the ZIP, file on disk, size), sorted by name. From the READ
    references, each original read again now; or from `out/`."""
    members = []
    budget = {"folders": 0, "until": time.monotonic() + WALK_S}
    if plan.read_folders or plan.read_files:
        for r in plan.refs:
            if r["access"] != "read":
                continue
            if r["kind"] == "folder":
                # CHECKED AGAIN NOW: it was a plain folder when it was asked.
                top = os.lstat(r["path"])
                if _reparse(top) or not stat.S_ISDIR(top.st_mode):
                    raise Refused(f"{r['path']} is no longer a plain folder")
                _walk(r["path"], os.path.basename(r["path"].rstrip("\\/"))
                      or "drive", ref["path"], members, _budget=budget)
            else:
                st = os.lstat(r["path"])
                if not _reparse(st) and stat.S_ISREG(st.st_mode):
                    members.append((os.path.basename(r["path"]), r["path"],
                                    st.st_size))
    else:
        out = os.path.join(scratch, "out")
        if os.path.isdir(out):
            _walk(out, "", ref["path"], members, _budget=budget)
    names = [m[0] for m in members]
    dup = next((n for n in names if names.count(n) > 1), None)
    if dup:
        raise Refused(f"two files would both be {dup} in the ZIP")
    if len(members) > ZIP_FILES_CAP:
        raise Refused(f"more than {ZIP_FILES_CAP} files")
    if sum(m[2] for m in members) > ZIP_BYTES_CAP:
        raise Refused(f"more than {ZIP_BYTES_CAP >> 20} MB")
    return sorted(members)


def build_zip(corpus, plan: FilePlan, ref, scratch: str) -> dict:
    """A ZIP Mentis builds itself: the same inputs make the same bytes
    (sorted names, one fixed time, fixed attributes), and it lands only
    where the owner chose, never over a file unless they confirmed."""
    row = {"by": "mentis", "tool": "zip", "path": ref["path"]}
    try:
        members = zip_members(plan, ref, scratch)
    except Refused as exc:
        return {**row, "outcome": "refused", "why": str(exc)}
    except OSError as exc:
        return {**row, "outcome": "refused",
                "why": f"a file could not be read ({type(exc).__name__})"}
    if not members:
        return {**row, "outcome": "not written", "why": "nothing to put in it"}
    why = _dest_ok(corpus, ref)
    if why:
        return {**row, "outcome": "refused", "why": why}
    tmp = _tmp_beside(ref["path"])
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            left = ZIP_BYTES_CAP
            for name, src, _ in members:
                info = zipfile.ZipInfo(name, ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 0
                info.external_attr = 0o644 << 16
                with z.open(info, "w") as w:
                    left -= _copy_capped(src, w, left)
        _place(tmp, ref["path"], bool(ref.get("overwrite")))
    except Refused as exc:
        return {**row, "outcome": "refused", "why": str(exc)}
    except FileExistsError:
        return {**row, "outcome": "refused",
                "why": "a file appeared there first; it was not replaced"}
    except OSError as exc:
        return {**row, "outcome": "refused",
                "why": f"could not be written ({type(exc).__name__})"}
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {**row, "outcome": "done", "files": len(members),
            "size": os.path.getsize(ref["path"])}


def collect(corpus, plan: FilePlan, scratch: str, res, into=None) -> list:
    """After the answer, before the private scratch is discarded: copy each
    WRITE file out and build each ZIP -- only if the answer finished. What
    the runtime wrote inside its private scratch is marked as such.

    Each result is added to `into` AS IT HAPPENS, so a file already written
    is reported even if something unexpected stops the rest."""
    for a in getattr(res, "actions", None) or ():
        if isinstance(a, dict) and isinstance(a.get("path"), str) and \
                _inside(os.path.abspath(a["path"]), scratch):
            a["private"] = True
    finished = (getattr(res, "exit_code", 1) == 0
                and not getattr(res, "error", None)
                and (getattr(res, "reported", "") or "").strip())
    done = into if into is not None else []
    for r in plan.write_files + plan.zips:
        if not finished:
            done.append({"by": "mentis", "tool": "zip" if is_zip(r) else "copy",
                         "path": r["path"], "outcome": "not written",
                         "why": "the answer did not finish"})
            continue
        try:
            done.append(build_zip(corpus, plan, r, scratch) if is_zip(r)
                        else copy_out(corpus, r, scratch))
        except Exception as exc:                          # noqa: BLE001
            done.append({"by": "mentis", "tool": "zip" if is_zip(r) else
                         "copy", "path": r["path"], "outcome": "refused",
                         "why": f"{type(exc).__name__}: {exc}"[:300]})
    return done
