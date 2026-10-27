"""Who has a Brain open, enforced by the operating system.

Deliverable 1, step 1 (brief adm-8ac4ef2f4866). Two locks, each an OS lock on
a file in the Brain directory, so a process that dies -- killed, crashed,
power cut -- releases what it held without anybody cleaning up:

  OPEN   `.mentis.lock`. Every guarded opener (server, worker, CLI, anything
         that constructs a `Store`) holds it SHARED for as long as the Brain is
         open. Migrate, reconcile and restore take it EXCLUSIVE, so they refuse
         while anything guarded has the Brain open, and an opener refuses while
         one of them is running.
  SERVE  `.mentis.serve.lock`, EXCLUSIVE, held by `mentis.web` for its whole
         life, so a second server on the same Brain refuses to start. Beside
         it, `.mentis.serve.json` says which process holds it -- for the
         refusal's message only; the lock, not the file, is the fact.

Two files rather than two ranges of one, because POSIX `flock` locks a whole
file: one file per lock behaves the same on Windows, macOS and Linux.

Windows: `LockFileEx` through ctypes (shared and exclusive, fail-immediately).
POSIX: `fcntl.flock`. No new dependency (psutil is Deliverable 2's).

KNOWN LIMIT, said rather than hidden: releases up to a24c2f0 take neither
lock. They cannot be refused by it; the schema tripwire (`user_version`)
shows afterwards that one opened the Brain, and Deliverable 2's upgrade
process covers it beforehand by detecting their processes.
"""

from __future__ import annotations

import json
import os
import sys
import time

OPEN_LOCK = ".mentis.lock"
SERVE_LOCK = ".mentis.serve.lock"
SERVE_INFO = ".mentis.serve.json"
#: written by a restore before it moves anything and removed only when it has
#: completed or been reversed. A lock dies with its process; this does not, so
#: an interrupted restore keeps every opener -- and every creator -- out until
#: somebody resumes it (`python -m mentis.brain restore --resume`).
RESTORING = ".mentis.restoring"

#: never copied into a backup, never moved by a restore
LOCK_FILES = (OPEN_LOCK, SERVE_LOCK, SERVE_INFO, RESTORING)


class BrainBusy(RuntimeError):
    """The lock is held by somebody else. Said in words; nothing waited."""


if sys.platform == "win32":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _OVERLAPPED(ctypes.Structure):
        _fields_ = [("Internal", ctypes.c_void_p),
                    ("InternalHigh", ctypes.c_void_p),
                    ("Offset", wintypes.DWORD),
                    ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE)]

    _k32.LockFileEx.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                wintypes.DWORD, wintypes.DWORD,
                                wintypes.DWORD, ctypes.POINTER(_OVERLAPPED))
    _k32.LockFileEx.restype = wintypes.BOOL
    _k32.UnlockFileEx.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                  wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(_OVERLAPPED))
    _k32.UnlockFileEx.restype = wintypes.BOOL
    _EXCLUSIVE, _NOWAIT = 0x2, 0x1

    def _lock(fh, shared: bool) -> bool:
        h = msvcrt.get_osfhandle(fh.fileno())
        ov = _OVERLAPPED()
        flags = _NOWAIT | (0 if shared else _EXCLUSIVE)
        return bool(_k32.LockFileEx(h, flags, 0, 1, 0, ctypes.byref(ov)))

    def _unlock(fh) -> None:
        h = msvcrt.get_osfhandle(fh.fileno())
        ov = _OVERLAPPED()
        _k32.UnlockFileEx(h, 0, 1, 0, ctypes.byref(ov))
else:
    import fcntl

    import errno as _errno

    def _lock(fh, shared: bool) -> bool:
        # flock belongs to the open file, so two opens in one process are two
        # holders, as on Windows. KNOWN LIMIT: Linux emulates flock on NFS and
        # CIFS with per-process record locks, which do not behave so; a Brain
        # is expected on a local disk.
        try:
            fcntl.flock(fh.fileno(), (fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
                        | fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno in (_errno.EWOULDBLOCK, _errno.EAGAIN, _errno.EACCES):
                return False
            raise

    def _unlock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


class Lock:
    """One held lock. Released by `release()`, by GC, or by process death."""

    def __init__(self, path: str, fh, shared: bool):
        self.path, self._fh, self.shared = path, fh, shared

    @property
    def held(self) -> bool:
        return self._fh is not None

    def release(self) -> None:
        fh, self._fh = self._fh, None
        if fh is None:
            return
        try:
            _unlock(fh)
        except OSError:
            pass
        fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
        return False

    def __del__(self):
        try:
            self.release()
        except Exception:                                  # noqa: BLE001
            pass


def _take(root: str, name: str, shared: bool) -> Lock | None:
    path = os.path.join(root, name)
    fh = open(path, "a+b")
    if _lock(fh, shared):
        return Lock(path, fh, shared)
    fh.close()
    return None


def restoring(root: str) -> dict | None:
    """The unfinished restore this Brain is in the middle of, or None."""
    p = os.path.join(root, RESTORING)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh) or {"quarantine_id": None}
    except (OSError, ValueError):
        return {"quarantine_id": None, "unreadable": True}


def refuse_if_restoring(root: str) -> None:
    got = restoring(root)
    if got is not None:
        raise BrainBusy(
            f"the Brain at {root} is in the middle of an interrupted restore"
            + (f" (quarantine {got.get('quarantine_id')})"
               if got.get("quarantine_id") else "")
            + ". Nothing may open or create it until the restore is resumed "
              "or reversed: `python -m mentis.brain restore <brain> --resume "
              "<quarantine id> [--reverse]`")


def shared(root: str) -> Lock:
    """The OPEN lock, shared. Refuses while migrate/reconcile/restore runs,
    and while an interrupted restore is unresolved."""
    refuse_if_restoring(root)
    got = _take(root, OPEN_LOCK, True)
    if got is None:
        raise BrainBusy(
            f"the Brain at {root} is being migrated, reconciled or restored; "
            f"open it when that has finished")
    return got


def exclusive(root: str, purpose: str, *, restoring_ok: bool = False) -> Lock:
    """The OPEN lock, exclusive: nothing guarded may have the Brain open.
    Refused during an unresolved restore, except to the restore code that
    resumes or reverses it (`restoring_ok`)."""
    if not restoring_ok:
        refuse_if_restoring(root)
    got = _take(root, OPEN_LOCK, False)
    if got is None:
        raise BrainBusy(
            f"cannot {purpose}: the Brain at {root} is open in another "
            f"process or object (a server, a worker, a CLI). Stop it first")
    return got


def serve(root: str, *, port=None, token: str | None = None) -> Lock:
    """The SERVE lock: one server per Brain.

    `token`, when given, is this start's graceful-shutdown token (Stage 1
    runtime layer, `mentis.servers.stop_server`). It is written into SERVE_INFO
    only after the file has been made readable by this user alone; if that
    cannot be done the token is left out -- said on stderr -- and the server
    can then only be stopped hard."""
    got = _take(root, SERVE_LOCK, False)
    if got is None:
        who = serving(root) or {}
        raise BrainBusy(
            f"another Mentis server already serves the Brain at {root}"
            + (f" (pid {who.get('pid')}, port {who.get('port')})"
               if who else "") + "; refusing to start a second")
    info = {"pid": os.getpid(), "port": port, "started_at": time.time()}
    p = os.path.join(root, SERVE_INFO)
    try:
        if token is not None:
            try:
                from mentis import readonly
                # emptied first, so no earlier token outlives the restriction
                fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                os.close(fd)
                readonly.keep_to_user(p)
                info["token"] = token
            except OSError as exc:
                print(f"serve: the shutdown token was not written, because "
                      f"{p} could not be kept to this user ({exc}); this "
                      f"server can only be stopped hard", file=sys.stderr)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(info, fh)
    except OSError:
        pass
    return got


def unserve(root: str) -> None:
    """Remove what this process wrote about serving, when it refuses to
    start after taking the SERVE lock: a refused server leaves no claim
    naming a pid and port that serve nothing. Only its own."""
    p = os.path.join(root, SERVE_INFO)
    got = serving(root)
    if got is not None and got.get("pid") == os.getpid():
        try:
            os.remove(p)
        except OSError:
            pass


def serving(root: str) -> dict | None:
    """What the last server wrote about itself. Informative, not a fact."""
    try:
        with open(os.path.join(root, SERVE_INFO), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def is_open(root: str) -> bool:
    """Whether any guarded opener holds the Brain right now (probe only)."""
    got = _take(root, OPEN_LOCK, False)
    if got is None:
        return True
    got.release()
    return False
