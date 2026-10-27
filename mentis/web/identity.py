"""What code THIS running server is, observed rather than inferred.

TWO THINGS ARE RUNNING, AND ONLY ONE IS FIXED AT START. (A headless server
serves no interface, so Mark IV's third, the UI build, is gone.)

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

UNTRACKED FILES COUNT. A tree with a new file nobody committed is not that
commit either, so "dirty" includes them and they are also counted apart.

Anything that cannot be observed is None with a `why_not`. Nothing here says
"live", "deployed", "integrated" or "reviewed": a branch name is a label on a
commit, not a statement about what is running anywhere, and this reports the
commit.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[2]


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
            "branch_at_start": branch,
            # WHERE THIS SERVER'S CODE IS, so a bridge started for an agent CLI
            # (tools/mcp_bridge.py) imports the same code the server runs, whether
            # that is an installed release or a development checkout.
            "root": str(REPO)}


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


_START = {
    "started_at": time.time(),
    "pid": os.getpid(),
    "python": sys.version.split()[0],
    "code": _code_at_start(),
    "code_fingerprint": _fingerprint(),
    # set by `serving()`, when the server is about to answer requests
    "modules_at_serving": None,
}


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
        # NO RELEASES, NO INSTALLS: this server runs from a checkout, and
        # `code.commit` names what it runs (`tools/mcp_bridge.py` reads it).
        "release": None,
        "release_why_not": None,
        "workspace": workspace,
        "corpus": corpus,
        "not_claimed": "nothing here says deployed, integrated or reviewed; "
                       "git remains the authority for where a commit is",
    }
