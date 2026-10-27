"""The lifecycle the source connectors share: plan ids, previews, custody,
and private staging.

Moved here verbatim from `mentis.sources.filesystem` (plan adm-b0c0a3bbac27,
step 1), where the Git connector already imported them from. None of them
knows what a folder or a repository is. `filesystem` re-imports every one,
so `filesystem.Cancelled` and the rest remain the same objects.

Collection declaration, draft expiry, preview output and the confirmation
transaction are shared below. Snapshot preparation stays with the adapters:
folders confirm private stages; Git confirms under its mirror lock.

Private staging (Stage C) followed (sqlite plan adm-b9c51d9f0ae2, Q3); see
its section below for how a connector supplies what it reads.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import pathlib
import re
import shutil
import threading
import time
import uuid

from mentis.sources import SWEPT, Refused, canonical, fingerprint, sensitive
from mentis.spine import held


def _patterns(ps, default) -> list[str]:
    out = []
    for p in (ps if ps is not None else default):
        p = str(p).replace("\\", "/").strip()
        if not p:
            raise Refused("an empty filter pattern means nothing; leave it out")
        out.append(p)
    return out


def _custody(corpus, s) -> str:
    """What a refused sweep is actually holding, said rather than implied.

    FOUND BY INDEPENDENT REVIEW. These refusals said "nothing was recorded",
    which is true of the RECORD and was being read as "nothing crossed". The
    bytes of every selected file are read and put into the held store BEFORE
    the transaction opens -- that ordering is deliberate, so an Admission can
    never name bytes Mentis does not have -- so a refusal leaves blobs in
    custody that no Admission names.

    IT FAILS IN THE SAFE DIRECTION and the atomicity that matters is intact:
    bytes without a record, never a record without bytes. Nothing claims
    possession of them as acquired material, because an Admission is the only
    thing that claims that and none was written.

    THEY ARE NOT DELETED HERE, deliberately. The held store is content
    addressed and blobs are shared by digest -- two paths with equal bytes are
    two objects and one blob -- so a refusal cannot know that a digest it
    stored is not also named by an Admission somebody else made. Deleting on
    refusal could destroy bytes the record legitimately depends on.
    `mentis.artifacts.sweep` already reports exactly these as `unnamed_blobs`
    and removes them on request, which is where an orphan belongs.

    AND ONLY THE GENUINELY UNNAMED ONES ARE CLAIMED, which the first attempt at
    this got wrong. It tested `held.has`, which answers "is this blob in the
    store" and not "did this refusal leave it unnamed" -- so after a successful
    sweep, a later refused one announced that every file's bytes were orphans
    `artifacts.sweep` would discard, while that sweep reported none. Replacing
    an understatement with an overstatement about the one fact this exists to
    state. The live digests the record names are subtracted, from
    `mentis.artifacts`' own `_live_digests`, so the two surfaces cannot
    disagree; and BLOBS are counted as blobs rather than miscounted as files,
    because two selected files with equal bytes are one blob.
    """
    from mentis.artifacts import _live_digests
    digests = {o["digest"] for o in s["observations"] if o.get("digest")}
    on_disk = {d for d in digests if held.has(corpus.root, d)}
    unnamed = sorted(on_disk - _live_digests(corpus))
    if not unnamed:
        return (". Nothing was recorded, and no bytes are left "
                "unnamed: whatever this read into the held store is "
                "already named by an Admission the record holds.")
    one = len(unnamed) == 1
    return (f". Nothing was recorded. {len(unnamed)} "
            f"{'blob' if one else 'blobs'} of selected bytes "
            f"{'was' if one else 'were'} read into the held store before the "
            f"refusal and {'is' if one else 'are'} named by no Admission: "
            f"nothing claims Mentis possesses "
            f"{'it' if one else 'them'} as acquired material, and "
            f"`mentis.artifacts.sweep` reports "
            f"{'it' if one else 'them'} as unnamed and will discard "
            f"{'it' if one else 'them'} on request. Not removed here, because "
            f"the store is content addressed and another Admission may name "
            f"the same digest.")


class Cancelled(Refused):
    """The owner cancelled a plan or a sweep before its transaction opened.
    Nothing was recorded."""


class _Quiet:
    """Progress nobody is watching. `mentis.sources.runs` supplies a real one
    to a background run; plan and sweep called directly get this."""

    def folder(self, rel):
        pass

    def read(self, n):
        pass

    def check(self):
        pass


def _decided(s):
    return not any(not f["previously_acquired"] and f["decision"] is None
                   for f in s["sensitive_files"]) and not any(
        c["new_files"] and c["decision"] is None
        for c in s.get("categories", ()))


def _last_binding(corpus, collection) -> tuple[str | None, bool]:
    for a in corpus.operational(act=SWEPT, newest_first=True):
        if a["detail"].get("collection") == collection:
            return a["detail"].get("binding"), True
    return None, False


def _binding_changed(corpus, collection, token, prior) -> tuple[bool, str | None]:
    last, swept = _last_binding(corpus, collection)
    if swept:
        return last != token, last
    return bool(prior), None


def _plan_id(basis: dict, scope: dict, s, d, prior) -> str:
    """Names one preview exactly.

    `basis` says what it is a preview OF: an existing collection under one
    binding, or a draft not yet declared. `scope` is the scope it was
    surveyed under AND the act that put it in force (B3: "a plan id includes
    the effective scope act"). A proposed revision's scope is its proposed
    filters on top of the act it revises -- so a plan made under one scope
    is refused if a different one has been recorded since."""
    body = {**basis, "within": s["within"],
            "scope": {"include": scope["include"],
                      "exclude": scope["exclude"], "act": scope.get("act")},
            "admit": [(o["object"], a, t) for o, a, t in d["admit"]],
            "absent": d["absent"], "withheld": sorted(s["withheld"].items()),
            "refused": s["refused"], "unexamined": s["unexamined"],
            "prior": fingerprint(prior)}
    if d.get("kept"):
        body["kept"] = d["kept"]
    if "sensitive_files" in s:
        body["sensitive_decisions"] = s["sensitive_decisions"]
        body["sensitive_files"] = s["sensitive_files"]
    if s.get("categories") or s.get("category_decisions"):
        body["category_decisions"] = s["category_decisions"]
        body["categories"] = [{k: c[k] for k in ("category", "decision",
                                                 "new_files", "new_bytes")}
                              for c in s["categories"]]
    return "plan-" + hashlib.sha256(canonical(body).encode()).hexdigest()[:24]


def _preview(corpus, s, d, *, pid, changed) -> dict:
    """What a plan says, the same shape for a collection, a revision and a
    draft. Writes nothing anywhere."""
    admit = [{"path": o["object"], "action": a, "size": o["size"],
              "digest": o["digest"], "payload_type": o["payload_type"]}
             for o, a, _ in d["admit"]]
    rels = [r for o, _, _ in d["admit"] for r in o.get("relations") or ()]
    return {
        **({"sensitive_files": s["sensitive_files"],
            "sensitive_decisions": s["sensitive_decisions"],
            "can_confirm": _decided(s)} if "sensitive_files" in s else {}),
        **({"categories": [{k: v for k, v in c.items() if k != "admitted"}
                           for c in s["categories"]],
            "category_decisions": s["category_decisions"],
            "category_note": sensitive.CONSENT_NOTE}
           if "categories" in s else {}),
        **({"not_selected": s["not_selected"]}
           if "not_selected" in s else {}),
        "plan": pid, "within": s["within"] or None,
        "binding_changed": changed,
        "admit": admit, "absent": d["absent"],
        "counts": {"new": sum(1 for a in admit if a["action"] == "new"),
                   "changed": sum(1 for a in admit if a["action"] == "changed"),
                   "reappeared": sum(1 for a in admit
                                     if a["action"] == "reappeared"),
                   "kept": len(d["kept"]),
                   "widened": sum(1 for a in admit if a["action"] == "widened"),
                   "absent": len(d["absent"]),
                   "unchanged": len(d["unchanged"]),
                   "not_acquired": len(s["withheld"]),
                   "refused": len(s["refused"]),
                   "unexamined": len(s["unexamined"]),
                   "not_examined": len(d["not_examined"]),
                   "visible_not_selected": len(s["visible"])},
        "unchanged": len(d["unchanged"]),
        "not_acquired": [{"path": k, "reason": v}
                         for k, v in sorted(s["withheld"].items())],
        "refused": s["refused"], "unexamined": s["unexamined"],
        "absence_withheld": d["not_examined"],
        "visible_not_selected": len(s["visible"]),
        "links": {"links_to": sum(1 for r in rels if r["rel"] == "links-to"),
                  "embeds": sum(1 for r in rels if r["rel"] == "embeds")},
        "largest": sorted(({"path": a["path"], "size": a["size"]}
                           for a in admit), key=lambda x: -x["size"])[:5],
        "bytes_to_retain": sum(a["size"] for a in admit),
        "bytes_new_to_store": sum(
            a["size"] for a in {x["digest"]: x for x in admit}.values()
            if a["digest"] in s.get("newly_written_digests", set())
            or not held.has(corpus.root, a["digest"])),
    }


def _inside(child: str, parent: str) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(child),
                                   os.path.normcase(parent)]) \
            == os.path.normcase(parent)
    except ValueError:
        return False


# -- private staging: a preview's bytes, machine-local until confirmed ----------
#
# STAGE C'S HELPERS, moved from `mentis.sources.filesystem` (sqlite plan
# adm-b9c51d9f0ae2, Q3) so a connector that previews from a staged snapshot
# shares them rather than copying them. Those that take `c` take the
# connector's module and read from it WHEN CALLED: its store `c._STAGES`, its
# tunables `c.STAGE_*`, its cache folder `c.STAGE_DIR`, its `c._survey`, and
# its own names for the helpers here (`c._abandon_stage` and the rest), so a
# test that replaces one on the connector replaces it here too. The folder
# connector re-imports the store and the tunables below as its own.

# Private machine-local snapshots. Never delete anything in the held store.
_STAGES: dict[tuple[str, str], dict] = {}
STAGE_TTL = 60 * 60
STAGE_CAP = 16
#: Only new, changed and reappeared bytes are staged, so the byte bound is on
#: those, aggregated over every live private stage on this machine (stages
#: from dead processes are treated as abandoned and removed on the next preview).
#: It is derived from free disk rather than fixed, so a
#: collection of any size refreshes as it did before staging: what a stage
#: takes is what the held store will need anyway. The room left is the cache
#: volume's free space less STAGE_DISK_HEADROOM, halved when the held store
#: is on the same volume, because confirm then writes the same bytes there
#: again. STAGE_TOTAL_BYTES, when set, is a fixed ceiling on the aggregate.
STAGE_DISK_HEADROOM = 1024 * 1024 * 1024
STAGE_TOTAL_BYTES = None
#: Staged bytes are kept in this process's memory, up to this much across
#: every live preview, and only the rest is written to the private disk
#: stage. Measured: reading back thousands of freshly written small files at
#: confirm cost ~7 ms each here (on-access scanning of new files), which made
#: a first acquisition slower than reading the source again. Memory is as
#: private and machine-local as the disk stage, and a restart forgets both.
STAGE_MEMORY_BYTES = 64 * 1024 * 1024
_STAGE_LOCK = threading.RLock()
_PROCESS_TOKEN = uuid.uuid4().hex


def _process_start_time(pid: int) -> int | None:
    if pid <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if kernel32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel), ctypes.byref(user)):
                return (creation.dwHighDateTime << 32) + creation.dwLowDateTime
            return None
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            return int(os.stat(f"/proc/{pid}").st_ctime_ns)
        except (OSError, AttributeError, ValueError):
            return None


def _is_process_alive(pid: int, expected_start_time: int | None = None) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if not handle:
            err = kernel32.GetLastError()
            return err == 5
        try:
            if expected_start_time is not None:
                creation = wintypes.FILETIME()
                exit_time = wintypes.FILETIME()
                kernel = wintypes.FILETIME()
                user = wintypes.FILETIME()
                if kernel32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel), ctypes.byref(user)):
                    actual_start = (creation.dwHighDateTime << 32) + creation.dwLowDateTime
                    if actual_start != expected_start_time:
                        return False
            STILL_ACTIVE = 259
            exit_code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return exit_code.value == STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
        except PermissionError:
            return True
        except OSError:
            return False
        if expected_start_time is not None:
            actual_start = _process_start_time(pid)
            if actual_start is not None and actual_start != expected_start_time:
                return False
        return True


def _record_stage_owner(directory: pathlib.Path) -> None:
    owner_info = {
        "pid": os.getpid(),
        "token": _PROCESS_TOKEN,
        "start_time": _process_start_time(os.getpid()),
        "at": time.time(),
    }
    (directory / ".owner").write_text(json.dumps(owner_info), encoding="utf-8")


def _is_stage_live(directory: pathlib.Path, active: set[str]) -> bool:
    if str(directory) in active:
        return True
    owner_file = directory / ".owner"
    if not owner_file.is_file():
        return False
    try:
        owner_info = json.loads(owner_file.read_text(encoding="utf-8"))
    except Exception:
        return False
    if owner_info.get("token") == _PROCESS_TOKEN:
        return False
    pid = owner_info.get("pid")
    start_time = owner_info.get("start_time")
    if isinstance(pid, int) and _is_process_alive(pid, start_time):
        return True
    return False


def _serialized(c, fn):
    @functools.wraps(fn)
    def run(*args, **kwargs):
        with _STAGE_LOCK:
            # A cache-wide OS lock also bounds concurrent processes and stops
            # expiry/eviction racing a confirmation that owns private bytes.
            corpus = args[0] if args else kwargs["corpus"]
            lock_path = c._stage_cache(corpus) / ".lock"
            with lock_path.open("a+b") as lock:
                if lock.tell() == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                if os.name == "nt":
                    import msvcrt
                    deadline = time.monotonic() + 60
                    while True:
                        try:
                            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                            break
                        except OSError:
                            if time.monotonic() >= deadline:
                                raise Refused("local preview cache is busy; retry")
                            time.sleep(0.05)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    return fn(*args, **kwargs)
                finally:
                    lock.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock, fcntl.LOCK_UN)
    return run


def _stage_cache(c, corpus):
    from mentis.sources.git import source_cache
    base = (pathlib.Path(source_cache()) / c.STAGE_DIR).resolve()
    if _inside(str(base), os.path.realpath(corpus.root)) or _inside(
            os.path.realpath(corpus.root), str(base)):
        raise Refused("local staging cache must be outside the corpus")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _remove_stage_dir(directory, base):
    # Check the resolved absolute target before recursive deletion. A cache
    # name alone is not proof of ownership, and links must never redirect it.
    directory = pathlib.Path(directory)
    base = pathlib.Path(base).resolve()
    resolved = directory.resolve()
    if (directory.is_symlink() or resolved != directory.absolute()
            or resolved.parent.parent != base
            or not re.fullmatch(r"[0-9a-f]{64}", directory.name)):
        raise Refused("refusing cleanup outside the private staging cache")
    shutil.rmtree(directory, ignore_errors=False)


def _cleanup_stage_blobs(corpus, stage):
    directory = pathlib.Path(stage["survey"]["stage_dir"])
    # The evicted stage can belong to a different corpus than the caller.
    if directory.parent.name != stage["survey"]["stage_corpus"]:
        raise Refused("private staging directory does not match its corpus")
    if directory.exists():
        _remove_stage_dir(directory, stage["survey"]["stage_cache"])


def _abandon_stage(c, corpus, key):
    stage = c._STAGES.pop(key, None)
    if stage:
        c._cleanup_stage_blobs(corpus, stage)


def _forget_stages(c, corpus, collection=None, root=None):
    now = time.time()
    for k, s in list(c._STAGES.items()):
        if (now - s["at"] > c.STAGE_TTL or
            (k[0] == corpus.corpus_id and
             ((collection is not None and s.get("collection") == collection) or
              (root is not None and s.get("root") == root)))):
            c._abandon_stage(corpus, k)
    while len(c._STAGES) >= c.STAGE_CAP:
        c._abandon_stage(corpus, min(c._STAGES, key=lambda k: c._STAGES[k]["at"]))


def _stage_budget(c, corpus, base, used):
    free = shutil.disk_usage(base).free
    try:
        same = os.stat(base).st_dev == os.stat(corpus.root).st_dev
    except OSError:
        same = True
    room = (free - c.STAGE_DISK_HEADROOM) // (2 if same else 1)
    if c.STAGE_TOTAL_BYTES is not None:
        room = min(room, c.STAGE_TOTAL_BYTES - used)
    memory = sum(len(b) for x in c._STAGES.values()
                 for b in x["survey"].get("in_memory", {}).values())
    return {"room": max(room, 0), "used": used, "free": free,
            "same_volume": same, "memory": memory}


def _over_budget(c, budget, wanted):
    fixed = ("" if c.STAGE_TOTAL_BYTES is None
             else f", a fixed ceiling of {c.STAGE_TOTAL_BYTES} bytes")
    return (f"preview would stage {wanted} new or changed bytes, over the local "
            f"staging byte limit of {budget['room']} bytes for this preview "
            f"({budget['used']} bytes already in private stages, "
            f"{budget['free']} bytes free on the cache volume, "
            f"{c.STAGE_DISK_HEADROOM} bytes kept free"
            + (", halved because confirm copies them to the held store on the same volume"
               if budget["same_volume"] else "")
            + fixed + "). Nothing was recorded or held; free disk space, "
            "confirm or let other previews expire, or narrow the scope, "
            "and preview again")


def _staged_survey(c, corpus, *args, protect=(), **kwargs):
    """`protect` names this process's stages the cap may not evict: a
    connector whose new preview is built FROM an earlier one (SQLite consent
    re-preview copies its captured snapshot) passes that one. Empty, as the
    folder connector calls it, eviction is exactly as before."""
    base = c._stage_cache(corpus)
    active = {s["survey"]["stage_dir"] for s in c._STAGES.values()}
    directories = []
    # Only stages owned by a live process count; abandoned stages left by an
    # earlier process or after a restart are removed on the next preview.
    for directory in base.glob("*/*"):
        if directory.is_dir() and re.fullmatch(r"[0-9a-f]{64}", directory.name):
            if str(directory) not in active and time.time() - directory.stat().st_mtime > c.STAGE_TTL:
                _remove_stage_dir(directory, base)
            elif not _is_stage_live(directory, active):
                _remove_stage_dir(directory, base)
            else:
                directories.append(directory)
    # Evict this process's oldest stages if the cap is reached, to avoid self-lockout.
    while len(directories) >= c.STAGE_CAP:
        evictable = [k for k in c._STAGES if k not in protect]
        if not evictable:
            break
        c._abandon_stage(corpus, min(evictable, key=lambda k: c._STAGES[k]["at"]))
        directories = [d for d in directories if d.exists()]
    used = sum(f.stat().st_size for d in directories for f in d.iterdir()
               if f.is_file() and re.fullmatch(r"[0-9a-f]{64}", f.name))
    # Refuse only when live stages of other processes fill the cap; do not advise
    # confirming previews this process cannot see.
    if len(directories) >= c.STAGE_CAP:
        raise Refused(f"local preview cache is full ({c.STAGE_CAP} stages held by other live processes); "
                      "wait for expiry")
    budget = c._stage_budget(corpus, base, used)
    parent = base / corpus.corpus_id
    parent.mkdir(exist_ok=True)
    if parent.resolve() != parent:
        raise Refused("private staging corpus directory must not redirect outside the cache")
    directory = parent / hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    directory.mkdir()
    _record_stage_owner(directory)
    try:
        survey = c._survey(corpus, *args, **kwargs, stage_dir=directory,
                         budget=budget)
        survey.update(stage_cache=str(base), stage_corpus=corpus.corpus_id)
        os.utime(directory, None)
        return survey
    except BaseException:
        _remove_stage_dir(directory, base)
        raise


def _admit_stage(corpus, stage):
    s = stage["survey"]
    done = set()
    for o in s["observations"]:
        obj, digest = o["object"], o["digest"]
        if digest in done:
            continue
        if digest not in s["staged"]:
            # UNCHANGED: the preview relied on the held copy. Re-hash it, as
            # held.put does an existing blob, and refuse exactly as it would.
            got, _ = held.state(corpus.root, digest, verify=True)
            if got == "corrupt":
                raise IOError(f"a blob for {digest} exists and does not hash to "
                              "its own name; refusing to write over the evidence")
            if got != "present":
                raise Refused(f"the held copy of {obj!r} that the preview relied "
                              "on is missing; preview again")
            done.add(digest)
            continue
        data = s["in_memory"].get(digest)
        if data is None:
            target = pathlib.Path(s["stage_dir"]) / digest
            try:
                with target.open("rb") as fh:
                    data = fh.read(held.MAX_BYTES + 1)
            except FileNotFoundError:
                raise Refused(f"staged bytes for {obj!r} are missing from local staging; preview again")
        if hashlib.sha256(data).hexdigest() != digest:
            raise Refused(f"staged bytes for {obj!r} failed integrity verification; preview again")
        actual, newly = held.put(corpus.root, data)
        if newly:
            s["newly_written_digests"].add(actual)
        done.add(digest)


# -- collection lifecycle ----------------------------------------------------
# Connector globals are read at call time: stores, tunables and test seams
# remain owned by the adapter. Snapshot policy is deliberately adapter-local.

def declare(c, corpus, cv, *, name, include=None, exclude=None,
            declarer, written_by=None, options=None):
    name = (name or "").strip()
    if not name:
        raise c.Refused("a collection needs a name")
    include = c._patterns(include, ["*"])
    exclude = c._patterns(exclude, [])
    extra = ({"options": c.checked_options(options)}
             if hasattr(c, "checked_options") else {})
    collection = f"col-{c.uuid.uuid4().hex[:12]}"
    detail = {"collection": collection, "name": name, "connector": c.CONNECTOR,
              "include": include, "exclude": exclude, **extra,
              "declared_by": declarer, "declared_at": c.time.time(),
              "written_by": written_by}
    act = cv.record_act(actor=declarer, act=c.DECLARED, about=[collection],
                        because="a Bulk Source collection declared", detail=detail)
    return {**detail, "declaration": act}


def binding_state(c, corpus, collection):
    bnd = c.bindings.binding(corpus, collection)
    if bnd is None:
        return {"bound": False, "binding": None,
                "state": "not bound on this machine"}
    extra = c._binding_extra(bnd) if hasattr(c, "_binding_extra") else {}
    return {"bound": True, "binding": bnd["binding"], "state": "bound",
            "bound_at": bnd.get("bound_at"), **extra}


def forget_drafts(c, corpus_id, root=None):
    now = c.time.time()
    gone = []
    def discard(key):
        if hasattr(c, "_draft_gone"):
            gone.append(c._DRAFTS.pop(key))
        else:
            c._DRAFTS.pop(key, None)

    for k, d in list(c._DRAFTS.items()):
        if now - d["at"] > c.DRAFT_TTL or (
                root is not None and k[0] == corpus_id and d["root"] == root):
            discard(k)
    while len(c._DRAFTS) >= c.DRAFT_CAP:
        discard(min(c._DRAFTS, key=lambda k: c._DRAFTS[k]["at"]))
    if hasattr(c, "_draft_gone"):
        for d in gone:
            c._draft_gone(d, root)


def plan(c, corpus, cv, collection, *, scope=None, **kwargs):
    decl, bnd, eff, under, s, d, changed, pid = c._plan_snapshot(
        corpus, cv, collection, scope=scope, **kwargs)
    revising = scope is not None or under["exclude"] != eff["exclude"]
    out = {"collection": collection, "name": decl["name"],
           **c._preview_result(corpus, s, d, pid, changed, bnd),
           "scope": {**c._scope_view(under), "act": eff["act"],
                     "revision": "proposed" if revising else eff["revision"]},
           **(c._plan_extra(bnd) if hasattr(c, "_plan_extra") else {}),
           "confirm": {"plan": pid, "acknowledge_binding_change": changed,
                       **c._confirm_scope(scope, under, s)}}
    if revising:
        out["revising"] = {"from": {**c._scope_view(eff), "act": eff["act"]},
                           "to": c._scope_view(under)}
    if changed:
        out["binding_note"] = (
            "this collection's binding is new or changed since its last "
            f"sweep. A binding certifies nothing about the {c.NOUN}: check these "
            "differences against what was recorded before confirming, and "
            "confirm with acknowledge_binding_change.")
    return out


def sweep(c, corpus, cv, collection, plan_id, *, actor, written_by,
          scope=None, because=None, progress=None, **kwargs):
    progress = progress or c._Quiet()
    decl, bnd, eff, under, s, changed, last, revising, prepared = c._sweep_snapshot(
        corpus, cv, collection, plan_id, actor=actor, written_by=written_by,
        scope=scope, because=because, progress=progress, **kwargs)

    def check(prior, d):
        current = c.bindings.binding(corpus, collection)
        if current is None or current["binding"] != bnd["binding"]:
            raise c.PlanChanged("the collection binding changed during the "
                                "sweep" + c._custody(corpus, s) + " Plan again.")
        now = c._plan_id(c._basis(collection, decl, bnd, s, under), under, s, d, prior)
        if now != plan_id:
            raise c.PlanChanged(
                f"{plan_id} is not what would be recorded now ({now}): the "
                + c.PLAN_CHANGE_REASON + c._custody(corpus, s) + " Plan again.")

    with corpus.atomic():
        if c.effective_scope(corpus, collection, decl)["act"] != eff["act"]:
            raise c.PlanChanged("this collection's scope was revised since the "
                                "preview" + c._custody(corpus, s) + " Plan again.")
        revision = eff["revision"]
        if revising:
            extra = c._revision_options(under) if hasattr(c, "_revision_options") else {}
            revision = c.record_revision(
                corpus, cv, collection, include=under["include"],
                exclude=under["exclude"], by=actor, because=because,
                written_by=written_by, **extra)
        extra = {"prepared": prepared} if prepared is not None else {}
        result = c.apply(
            corpus, cv, source=c.source_of(collection), collection=collection,
            connector=c.CONNECTOR, observations=s["observations"],
            examined=s["examined"], withheld=set(s["withheld"]),
            scope={"declaration": decl["declaration"], "revision": revision,
                   "within": s["within"] or None},
            act_detail=c._sweep_detail(s, plan_id, bnd, changed, last, decl),
            actor=actor, written_by=written_by, check=check,
            observed_at=c.time.time(), compare=s.get("compare", getattr(c, "_compare", None)), **extra)
    if hasattr(c, "_sweep_done"):
        c._sweep_done(corpus, plan_id)
    return result
