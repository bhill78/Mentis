"""`<root>/state/install.json`: which release is current, and which Brain.

THE FILE (Stage 1 shared contract):

    {"format": 1, "current": "<semver>+<commit12>", "previous": <name> | null,
     "brain": "<absolute path>", "port": <int>, "owner_alias": "@x" | null}

`current` and `previous` are release directory names under `<root>/releases`.
Keys this module does not name are kept as they were when the file is
rewritten, so a later field never has to be taught to every writer. Two such
keys install writes: `id` (shared interface I3), a uuid4 made by the first
install and kept by every re-run, repair and update, which the server
reports in `/api/server` -- text when present -- and `set_aside`, the
damaged release folders `install --repair` renamed aside.

WRITTEN BY ATOMIC REPLACE. The new content goes to a temporary file in the
same directory, is flushed and fsynced, and is renamed over the old one; then
the directory is fsynced where the OS allows it (not on Windows, where a
directory cannot be opened to sync). A reader sees the old file or the new
one, never a mix, and a crash never leaves it half-written. The update
journal (`state/update.journal.json`) is written the same way, with
`write_json_atomic`.

Stdlib only: the installer imports this from inside the package zip, before
any dependency is installed.

Used by the installer, the launcher's `mentis.cli`, the health check, the
updater and release retention. Its interface is frozen:
`write_json_atomic`, `read_json`, `load`, `save`, `update`, `venv_python`,
`release_dir`, `InstallStateError`; `bundled` was added for bundled mode, and
`venv_python` answers a bundled release's `runtime/python.exe`.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

from mentis import home

FORMAT = 1
#: the contract's fields; anything else in the file is carried as it is
FIELDS = ("format", "current", "previous", "brain", "port", "owner_alias")


class InstallStateError(RuntimeError):
    """install.json is missing where it is needed, unreadable, or not a
    format 1 install.json. Said in words; nothing was changed."""


def _layout(where=None) -> home.Layout:
    if isinstance(where, home.Layout):
        return where
    return home.Layout(where)


def write_json_atomic(path, obj) -> None:
    """Write `obj` as JSON to `path` by atomic replace, fsynced."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False)
            + "\n").encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    if sys.platform != "win32":
        dfd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


def read_json(path) -> dict | None:
    """The JSON object at `path`, or None when there is no such file. A file
    that is present but is not a JSON object raises InstallStateError."""
    path = pathlib.Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise InstallStateError(f"{path} is not readable JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise InstallStateError(f"{path} does not hold a JSON object")
    return doc


def _check(doc: dict, where) -> dict:
    problems = []
    if doc.get("format") != FORMAT:
        problems.append(f"format is {doc.get('format')!r}, not {FORMAT}")
    if not (isinstance(doc.get("current"), str) and doc["current"]):
        problems.append("names no current release")
    if doc.get("previous") is not None and not isinstance(doc["previous"], str):
        problems.append("previous is not a release name")
    brain = doc.get("brain")
    if not (isinstance(brain, str) and os.path.isabs(brain)):
        problems.append("brain is not an absolute path")
    port = doc.get("port")
    if not (isinstance(port, int) and not isinstance(port, bool)
            and 0 < port < 65536):
        problems.append(f"port {port!r} is not a TCP port")
    alias = doc.get("owner_alias")
    if alias is not None and not isinstance(alias, str):
        problems.append("owner_alias is not text")
    if "id" in doc and not (isinstance(doc["id"], str) and doc["id"]):
        problems.append("id is not text")
    for name in (doc.get("current"), doc.get("previous")):
        if isinstance(name, str) and name:
            try:
                _layout(where).release(name)
            except ValueError as exc:
                problems.append(str(exc))
    if problems:
        raise InstallStateError(
            f"{_layout(where).install_json}: " + "; ".join(problems))
    return doc


def load(where=None, *, required: bool = False) -> dict | None:
    """install.json under this root (a path, a `home.Layout`, or None for
    `home.root()`), checked against the contract. None when there is none,
    or InstallStateError when there is none and `required` is true. One that
    is present but wrong always raises."""
    lay = _layout(where)
    doc = read_json(lay.install_json)
    if doc is None:
        if required:
            raise InstallStateError(
                f"nothing is installed at {lay.root} (no {lay.install_json})")
        return None
    return _check(doc, lay)


def save(state, where=None) -> dict:
    """Check `state` against the contract and write it as install.json, by
    atomic replace. Returns what was written. `save(root, state)` -- the
    root first -- is accepted too."""
    if not isinstance(state, dict) and isinstance(where, dict):
        state, where = where, state
    lay = _layout(where)
    doc = {"format": FORMAT, "previous": None, "owner_alias": None, **state}
    _check(doc, lay)
    write_json_atomic(lay.install_json, doc)
    return doc


def update(where=None, **changes) -> dict:
    """Read install.json, change the named fields, write it back atomically.
    Fields not named, including ones this module does not know, are kept."""
    lay = _layout(where)
    doc = load(lay, required=True)
    doc.update(changes)
    return save(doc, lay)


def release_dir(where, name: str) -> pathlib.Path:
    """`<root>/releases/<name>`; a name that is not one directory name is
    refused (`home.Layout.release`)."""
    return _layout(where).release(name)


#: where a bundled release carries its Python (RELEASE.json `runtime.path`)
RUNTIME_DIR = "runtime"


def bundled(release: os.PathLike | str) -> dict | None:
    """The `runtime` block of a release's RELEASE.json -- {"kind": "embedded",
    "python": "3.12.x", "path": "runtime"} -- when it carries its own Python
    (BUNDLED MODE: no venv, no pip, no .pth), else None. A block naming any
    other path is not honoured: the runtime is always `runtime/`."""
    try:
        doc = json.loads((pathlib.Path(release) / home.RELEASE_FILE)
                         .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rt = doc.get("runtime") if isinstance(doc, dict) else None
    if isinstance(rt, dict) and rt.get("path") == RUNTIME_DIR:
        return rt
    return None


def venv_python(release: os.PathLike | str) -> pathlib.Path:
    """The interpreter a release runs with: its bundled
    `runtime/python.exe` when its RELEASE.json declares a runtime (bundled
    mode), else its own virtual environment's. The name is kept from before
    bundled mode: every caller asks this for "the release's Python"."""
    rel = pathlib.Path(release)
    if bundled(rel) is not None:
        return rel / RUNTIME_DIR / "python.exe"
    if sys.platform == "win32":
        return rel / ".venv" / "Scripts" / "python.exe"
    return rel / ".venv" / "bin" / "python"
