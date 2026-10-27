"""Locking a release folder read-only, and keeping a file to its owner.

A RELEASE IS LOCKED ONCE VERIFIED so no build, install, checkout or stray
command changes what a server runs. It is a guard against accident, not
against the owner deliberately undoing it (they own the files, and an owner
can always change their permissions).

WINDOWS: one inheritable DENY entry for the current user (no PowerShell, no
Set-Acl), denying exactly

    WD  write data / add file          AD  append data / add subdirectory
    WEA write extended attributes      WA  write attributes
    D   delete                         DC  delete child

and nothing else. It is written through the Windows security API itself
(GetNamedSecurityInfo / SetEntriesInAcl / SetNamedSecurityInfo, which also
carries it to everything already under the folder), NOT through `icacls`:
icacls adds SYNCHRONIZE to every entry it writes, even for a list of specific
rights, and a deny of SYNCHRONIZE denies reading files and listing the folder
too (measured 2026-10-15: `/deny *SID:(OI)(CI)(WD,AD,D,DC)` made every file
unreadable). The user is named by SID, so a localised or renamed account
cannot be misnamed. Unlocking removes that user's deny entries with
`icacls <dir> /remove:d *SID`, which only removes.

KNOWN LIMIT (Windows): the locked folder ITSELF can still be renamed, because
Windows grants a rename to whoever may delete children of the PARENT folder,
and `releases/` stays writable so new releases can be added. Nothing inside
it can be changed, added or deleted, and it cannot be removed (it is never
empty). The old Set-Acl lock had the same limit. Nor does the lock reach a
file whose DACL is protected (inheritance disabled): it stays writable, and
`is_locked` (which tries one file) need not notice; releases make none.

POSIX: every write bit is cleared on every file and directory (symlinks are
not followed: a venv's `bin/python` points at the system interpreter). root
ignores mode bits; that limit is said, not hidden.

Whether a folder is locked is MEASURED, not inferred from what was set:
`is_locked` tries to add a file at the top and to open an existing file for
writing, and both must be refused.
"""

from __future__ import annotations

import os
import pathlib
import stat
import subprocess
import sys
import uuid

#: the rights a locked release denies (see the docstring): FILE_WRITE_DATA,
#: FILE_APPEND_DATA, FILE_WRITE_EA, FILE_DELETE_CHILD, FILE_WRITE_ATTRIBUTES,
#: DELETE. Not SYNCHRONIZE, not READ_CONTROL.
DENY_MASK = 0x2 | 0x4 | 0x10 | 0x40 | 0x100 | 0x10000

_SID: str | None = None


def user_sid() -> str:
    """The current Windows user's SID, from `whoami`. Windows only."""
    global _SID
    if _SID is None:
        out = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                             capture_output=True, text=True, timeout=30,
                             creationflags=_NO_WINDOW)
        cells = [c.strip().strip('"') for c in out.stdout.strip().split('","')]
        sid = cells[-1].strip('"') if cells else ""
        if out.returncode != 0 or not sid.startswith("S-1-"):
            raise OSError("cannot tell this user's SID: whoami said "
                          f"{(out.stdout + out.stderr).strip()!r}")
        _SID = sid
    return _SID


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _icacls(*args: str) -> None:
    out = subprocess.run(["icacls", *args], capture_output=True, text=True,
                         timeout=600, creationflags=_NO_WINDOW)
    if out.returncode != 0:
        raise OSError(f"icacls {' '.join(args)} -> {out.returncode}: "
                      f"{(out.stdout + out.stderr).strip()}")


def _advapi():
    """advapi32 and kernel32 with the signatures used here, and the
    TRUSTEE_W / EXPLICIT_ACCESS_W structures. Windows only."""
    import ctypes
    from ctypes import wintypes as W

    class TRUSTEE_W(ctypes.Structure):
        _fields_ = [("pMultipleTrustee", ctypes.c_void_p),
                    ("MultipleTrusteeOperation", ctypes.c_int),
                    ("TrusteeForm", ctypes.c_int),
                    ("TrusteeType", ctypes.c_int),
                    ("ptstrName", ctypes.c_void_p)]

    class EXPLICIT_ACCESS_W(ctypes.Structure):
        _fields_ = [("grfAccessPermissions", W.DWORD),
                    ("grfAccessMode", ctypes.c_int),
                    ("grfInheritance", W.DWORD),
                    ("Trustee", TRUSTEE_W)]

    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    adv.ConvertStringSidToSidW.argtypes = [W.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    adv.ConvertStringSidToSidW.restype = W.BOOL
    adv.GetNamedSecurityInfoW.argtypes = [
        W.LPCWSTR, ctypes.c_int, W.DWORD, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p)]
    adv.GetNamedSecurityInfoW.restype = W.DWORD
    adv.SetEntriesInAclW.argtypes = [W.ULONG, ctypes.POINTER(EXPLICIT_ACCESS_W),
                                     ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_void_p)]
    adv.SetEntriesInAclW.restype = W.DWORD
    adv.SetNamedSecurityInfoW.argtypes = [W.LPWSTR, ctypes.c_int, W.DWORD,
                                          ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_void_p, ctypes.c_void_p]
    adv.SetNamedSecurityInfoW.restype = W.DWORD
    k32.LocalFree.argtypes = [ctypes.c_void_p]
    k32.LocalFree.restype = ctypes.c_void_p
    return adv, k32, TRUSTEE_W, EXPLICIT_ACCESS_W


SE_FILE_OBJECT, DACL_INFO = 1, 4
TRUSTEE_IS_SID, TRUSTEE_IS_USER = 0, 1


def _deny_writes(top: pathlib.Path) -> None:
    """Add one inheritable DENY entry of exactly DENY_MASK for the current
    user to `top`'s DACL, carried to everything under it."""
    import ctypes
    adv, k32, TRUSTEE_W, EXPLICIT_ACCESS_W = _advapi()
    DENY_ACCESS, INHERIT_ALL = 3, 3           # SUB_CONTAINERS_AND_OBJECTS_INHERIT

    sid, sd, new = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    old = ctypes.c_void_p()
    if not adv.ConvertStringSidToSidW(user_sid(), ctypes.byref(sid)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        err = adv.GetNamedSecurityInfoW(str(top), SE_FILE_OBJECT, DACL_INFO,
                                        None, None, ctypes.byref(old), None,
                                        ctypes.byref(sd))
        if err:
            raise ctypes.WinError(err)
        ea = EXPLICIT_ACCESS_W(DENY_MASK, DENY_ACCESS, INHERIT_ALL,
                               TRUSTEE_W(None, 0, TRUSTEE_IS_SID,
                                         TRUSTEE_IS_USER, sid.value))
        err = adv.SetEntriesInAclW(1, ctypes.byref(ea), old, ctypes.byref(new))
        if err:
            raise ctypes.WinError(err)
        err = adv.SetNamedSecurityInfoW(str(top), SE_FILE_OBJECT, DACL_INFO,
                                        None, None, new, None)
        if err:
            raise ctypes.WinError(err)
    finally:
        for p in (new, sd, sid):
            if p.value:
                k32.LocalFree(p)


def _only_user(path: str) -> None:
    """Replace `path`'s DACL with ONE entry, full control for the current
    user, and protect it from inheritance: every other trustee, inherited or
    explicit, is gone."""
    import ctypes
    adv, k32, TRUSTEE_W, EXPLICIT_ACCESS_W = _advapi()
    SET_ACCESS, NO_INHERITANCE = 2, 0
    FILE_ALL_ACCESS = 0x1F01FF
    PROTECTED_DACL = 0x80000000

    sid, new = ctypes.c_void_p(), ctypes.c_void_p()
    if not adv.ConvertStringSidToSidW(user_sid(), ctypes.byref(sid)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        ea = EXPLICIT_ACCESS_W(FILE_ALL_ACCESS, SET_ACCESS, NO_INHERITANCE,
                               TRUSTEE_W(None, 0, TRUSTEE_IS_SID,
                                         TRUSTEE_IS_USER, sid.value))
        # no old ACL: the new one holds this entry and nothing else
        err = adv.SetEntriesInAclW(1, ctypes.byref(ea), None, ctypes.byref(new))
        if err:
            raise ctypes.WinError(err)
        err = adv.SetNamedSecurityInfoW(path, SE_FILE_OBJECT,
                                        DACL_INFO | PROTECTED_DACL, None,
                                        None, new, None)
        if err:
            raise ctypes.WinError(err)
    finally:
        for p in (new, sid):
            if p.value:
                k32.LocalFree(p)


def _chmod_tree(top: pathlib.Path, change) -> None:
    for dirpath, dirnames, filenames in os.walk(top, followlinks=False):
        for name in filenames + dirnames:
            p = os.path.join(dirpath, name)
            st = os.lstat(p)
            if not stat.S_ISLNK(st.st_mode):
                os.chmod(p, change(stat.S_IMODE(st.st_mode)))
    st = os.lstat(top)
    os.chmod(top, change(stat.S_IMODE(st.st_mode)))


def lock(path: os.PathLike | str) -> None:
    """Make everything under `path` read-only for the current user. Safe to
    repeat."""
    top = pathlib.Path(path)
    if not top.is_dir():
        raise NotADirectoryError(f"{top} is not a directory")
    if sys.platform == "win32":
        unlock(top)     # one deny entry, however many times this is called
        _deny_writes(top)
        return
    _chmod_tree(top, lambda m: m & ~(stat.S_IWUSR | stat.S_IWGRP
                                     | stat.S_IWOTH))


def unlock(path: os.PathLike | str) -> None:
    """Undo `lock`: writable by the current user again. Safe on a folder that
    was never locked."""
    top = pathlib.Path(path)
    if sys.platform == "win32":
        _icacls(str(top), "/remove:d", f"*{user_sid()}")
        return
    _chmod_tree(top, lambda m: m | stat.S_IWUSR)


def is_locked(path: os.PathLike | str) -> bool:
    """Whether the current user is refused both adding a file at the top of
    `path` and writing the first existing file found under it. Measured by
    trying; anything that succeeds is undone."""
    top = pathlib.Path(path)
    probe = top / f".mentis-lock-probe-{uuid.uuid4().hex}"
    try:
        with open(probe, "xb"):
            pass
    except PermissionError:
        pass
    else:
        os.remove(probe)
        return False
    for dirpath, _dirs, files in os.walk(top):
        for name in files:
            p = os.path.join(dirpath, name)
            if os.path.islink(p):
                continue
            try:
                with open(p, "r+b"):
                    pass
            except PermissionError:
                return True
            return False
    return True


def keep_to_user(path: os.PathLike | str) -> None:
    """Make one existing file readable and writable by the current user
    only. Call it BEFORE writing anything secret into the file.

    Windows: the DACL is REPLACED by one entry, full control for the
    current user by SID, protected from inheritance -- any entry already on
    the file, inherited or explicit, is gone. POSIX: mode 0600."""
    p = str(path)
    if sys.platform == "win32":
        _only_user(p)
        return
    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
