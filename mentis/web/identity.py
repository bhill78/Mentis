"""What code THIS running server is, observed rather than inferred.

THREE THINGS ARE RUNNING, AND ONLY ONE IS FIXED AT START.

  code at start   the commit checked out when this process started, read ONCE
                  and never re-read. It names the modules this process had
                  imported by then -- and ONLY those.

  code since      NOT fixed. Modules imported lazily on first use (the work,
                  register and worker surfaces among them) load from whatever
                  is checked out when they are first needed, and every worker
                  subprocess a dispatch starts reads the checkout as it is at
                  that moment. So the checkout NOW is read per request and
                  shown beside the start commit, with the mentis modules this
                  process loaded after it started serving, and whether the CODE
                  (CODE_SCOPE, by content) differs from what it was at start --
                  which catches an edit after a start that was already dirty,
                  and ignores an untracked note. What is NOT observed, and so
                  not claimed: which checkout a later load or a worker actually
                  read. A checkout that changed and changed back between two
                  looks looks unchanged. (An earlier version of this said a
                  later checkout "changes nothing that is running". False.)

  ui              the built interface in `ui/dist`, read from disk on EVERY
                  request, so a rebuild is served at once. Read now, with the
                  commit the build recorded.

UNTRACKED FILES COUNT. A tree with a new file nobody committed is not that
commit either, so "dirty" includes them and they are also counted apart.

Anything that cannot be observed is None with a `why_not`. Nothing here says
"live", "deployed", "integrated" or "reviewed": a branch name is a label on a
commit, not a statement about what is running anywhere, and this reports the
commit.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[2]
DIST = REPO / "ui" / "dist"
#: written by the UI build (see `ui/vite.config.ts`); absent for a build made
#: before that existed, which is said rather than guessed.
BUILD_FILE = "build-identity.json"


def _git(*args) -> tuple[str | None, str | None]:
    try:
        out = subprocess.run(["git", "-C", str(REPO), *args],
                             capture_output=True, text=True, timeout=10)
    except Exception as exc:                                  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    if out.returncode != 0:
        return None, (out.stderr or out.stdout).strip() or "git failed"
    return out.stdout.strip(), None


def _tree() -> dict:
    """The checkout as it is at the moment of asking: commit and dirtiness.

    Dirty counts untracked files too, and they are also counted apart. None
    with a reason when git cannot be asked -- never False.
    """
    commit, why = _git("rev-parse", "HEAD")
    status, why_status = _git("status", "--porcelain")
    lines = [ln for ln in (status or "").splitlines() if ln.strip()]
    return {
        "commit": commit,
        "commit_why_not": None if commit else why,
        "dirty": (bool(lines) if status is not None else None),
        "dirty_why_not": None if status is not None else why_status,
        "untracked": (sum(1 for ln in lines if ln.startswith("??"))
                      if status is not None else None),
    }


def _code_at_start() -> dict:
    tree = _tree()
    branch, _ = _git("rev-parse", "--abbrev-ref", "HEAD")
    subject, _ = (_git("log", "-1", "--format=%s") if tree["commit"]
                  else (None, None))
    return {**tree, "subject": subject,
            # A label, reported as observed at start. Not evidence of anything.
            "branch_at_start": branch}


#: WHAT COUNTS AS CODE for "has the running code changed": the Python the
#: server imports and every worker subprocess imports. Tests, trial code,
#: docs and `ui/src` are not it (the interface is judged by its own build
#: stamp), so an untracked note or a new screenshot is not a code change.
CODE_SCOPE = "mentis/**/*.py"


def _fingerprint(root: pathlib.Path = REPO) -> dict:
    """A digest of every file in CODE_SCOPE, tracked or not, by content.

    Content, not git: a start that was already dirty has no commit that names
    it, so "did the code change since start" is answered by comparing what
    the files hold, which also catches an edit that git would call no new
    commit."""
    import hashlib
    try:
        h, n = hashlib.sha256(), 0
        for f in sorted((root / "mentis").rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            h.update(f.relative_to(root).as_posix().encode() + b"\0")
            h.update(f.read_bytes() + b"\0")
            n += 1
        return {"digest": h.hexdigest(), "files": n, "why_not": None}
    except Exception as exc:                                  # noqa: BLE001
        return {"digest": None, "files": None,
                "why_not": f"{type(exc).__name__}: {exc}"}


def _mentis_modules() -> set:
    return {m for m in list(sys.modules) if m == "mentis" or m.startswith("mentis.")}


def _build(dist: pathlib.Path = DIST) -> dict:
    """The UI build on disk right now, which is the one being served."""
    index = dist / "index.html"
    if not index.is_file():
        return {"present": False, "why_not": f"no {index} to serve"}
    html = index.read_text(encoding="utf-8", errors="replace")
    assets = sorted(set(re.findall(r"assets/(index-[\w-]+\.(?:js|css))", html)))
    stamp = dist / BUILD_FILE
    stamped = None
    stamp_why = None
    if stamp.is_file():
        try:
            stamped = json.loads(stamp.read_text(encoding="utf-8"))
        except Exception as exc:                              # noqa: BLE001
            stamp_why = f"{BUILD_FILE} unreadable: {type(exc).__name__}"
    else:
        stamp_why = (f"this build carries no {BUILD_FILE}, so which commit it "
                     f"was built from is not recorded")
    return {"present": True, "assets": assets,
            "index_mtime": index.stat().st_mtime,
            "built_from": stamped, "built_from_why_not": stamp_why}


_START = {
    "started_at": time.time(),
    "pid": os.getpid(),
    "python": sys.version.split()[0],
    "code": _code_at_start(),
    "code_fingerprint": _fingerprint(),
    "ui_at_start": _build(),
    # set by `serving()`, when the server is about to answer requests
    "modules_at_serving": None,
}


def _release() -> dict:
    """The release this code was installed from, read ONCE at start (a
    release is immutable): {version, commit, path} from its RELEASE.json, or
    None when this is not a release -- run from a repository checkout, or a
    release made by the old `tools/release.py`, which carries none."""
    from mentis import home
    try:
        return {"release": home.release(REPO), "release_why_not": None}
    except Exception as exc:                                  # noqa: BLE001
        return {"release": None,
                "release_why_not": f"{home.RELEASE_FILE} unreadable: "
                                   f"{type(exc).__name__}: {exc}"}


_START.update(_release())


def _install() -> dict | None:
    """WHICH INSTALL this server belongs to (shared interface I3):
    {"id": <uuid>, "home": <absolute home>} when this code is a release in
    an install's `releases/` and that install's `state/install.json` records
    an id; None otherwise (a repository checkout, a release outside any
    install). Read on every request -- a small file -- so a server is never
    reported under an id its install no longer has. A program tells ITS
    server from another one answering on the same port by this."""
    rel = _START.get("release") or {}
    path = rel.get("path") if isinstance(rel, dict) else None
    if not path:
        return None
    rel_dir = pathlib.Path(path)
    if rel_dir.parent.name != "releases":
        return None
    root = rel_dir.parent.parent
    try:
        doc = json.loads((root / "state" / "install.json")
                         .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (isinstance(doc, dict) and isinstance(doc.get("id"), str)
            and doc["id"]):
        return None
    return {"id": doc["id"], "home": str(root)}


def serving() -> None:
    """Record which mentis modules were imported when the server began to
    serve, so anything loaded afterwards can be named as loaded later."""
    _START["modules_at_serving"] = _mentis_modules()


def identity(*, workspace: str, corpus: str, host=None, port=None) -> dict:
    out = _identity(workspace=workspace, corpus=corpus, host=host, port=port)
    start, now_ = out["code"]["commit"], out["checkout_now"]["commit"]
    out["checkout_now"]["differs_from_start"] = (
        None if not (start and now_) else start != now_)
    return out


def _code_change() -> dict:
    """Whether the code on disk (CODE_SCOPE) differs, by content, from what it
    was when this process started. None, with the reason, if either side
    could not be read."""
    start, now = _START["code_fingerprint"], _fingerprint()
    changed = (None if not (start["digest"] and now["digest"])
               else start["digest"] != now["digest"])
    return {"code_scope": CODE_SCOPE,
            "code_changed_since_start": changed,
            "code_changed_why_not": (None if changed is not None else
                                     start["why_not"] or now["why_not"])}


def _identity(*, workspace: str, corpus: str, host=None, port=None) -> dict:
    now = _build()
    at_start = _START["ui_at_start"]
    changed = (None if not (now.get("present") and at_start.get("present"))
               else now["assets"] != at_start["assets"])
    return {
        "process": {"pid": _START["pid"], "started_at": _START["started_at"],
                    "python": _START["python"], "host": host, "port": port},
        "code": {**_START["code"],
                 "repository": str(REPO),
                 "observed": "at process start. It names what this process "
                             "had imported by then, not everything that runs: "
                             "see `checkout_now`"},
        "checkout_now": {
            **_tree(),
            "differs_from_start": None,
            **_code_change(),
            "loaded_after_start": (
                sorted(_mentis_modules() - _START["modules_at_serving"])
                if _START["modules_at_serving"] is not None else None),
            "loaded_after_start_why_not": (
                None if _START["modules_at_serving"] is not None else
                "this process did not record which modules it had loaded "
                "when it began serving"),
            "observed": "now, from disk. It is NOT a record of what anything "
                        "read: code loaded after start, and each worker, read "
                        "the disk as it was at the moment they loaded, which "
                        "this does not keep. A checkout that changed and "
                        "changed back looks unchanged here"},
        "ui": {**now, "dist": str(DIST),
               "changed_since_start": changed,
               "observed": "now; the interface is read from disk on every "
                           "request, so a rebuild is served without a "
                           "restart"},
        # WHICH RELEASE, as the package builder stamped it. None from a
        # repository, with `release_why_not` None too: that is not a fault.
        "release": _START["release"],
        "release_why_not": _START["release_why_not"],
        # WHICH INSTALL (I3): None from a repository or outside an install
        "install": _install(),
        "workspace": workspace,
        "corpus": corpus,
        "not_claimed": "nothing here says deployed, integrated or reviewed; "
                       "git remains the authority for where a commit is",
    }
