"""Repository worktrees owned by the request that needs one.

AS DECIDED (Artifacts & Files, after ent-2bb8f23bb2f4, option A):

  * A request that EXPLICITLY requires an isolated repository owns a worktree
    and a branch. Nothing infers the need: the owner declares it on the
    request (`repository: {"base": ...}`), or a coordinator declares it for a
    child it delegates (`repository: true`).
  * Every run and resumption of THAT request reuses it, whichever execution or
    session carries the work. Unrelated work never does: the worktree is the
    run's workspace, and a session bound to one workspace is not reused for
    another (`agents_summon`).
  * A delegated child that needs repository access gets its OWN worktree and
    branch, cut from the parent's branch, and returns changes as that branch
    for the parent to inspect and integrate.
  * Mentis owns the lifecycle and records it: who owns the worktree, its base,
    branch and path; it is removed promptly once its work is integrated or
    explicitly abandoned; orphans left by a crash are reconciled.
  * CLOSING A REQUEST IS NOT PERMISSION TO DESTROY UNINTEGRATED CHANGES. A
    worktree whose request is closed but whose work is neither integrated nor
    explicitly abandoned is preserved, and its unresolved state reported.

CLOSEOUT (the owner's requirement, 2026-10-25): "at work closeout, reconcile
the recorded outcome, preserve any unique unmerged work, and remove the
disposable worktree. Routine completion must not leave cleanup dependent on
a forgotten 'met' marker. Keep genuinely unfinished work visibly parked."
When a run of the request has ended and nothing holds its tree (`_settle`):
uncommitted changes are COMMITTED on the request's own branch as a WIP
commit attributed to the run that left them; a tree whose every commit is in
its integration target is REMOVED, folder and branch, whether or not anybody
marked the request met; a clean tree whose branch holds work the target does
not is PARKED -- the folder goes, the branch and the record stay, recorded
as `worktree-parked`, and `ensure` attaches it again when the request is
continued. A folder exists only for work that is active.

THREE DIFFERENT THINGS, KEPT APART. A worktree is neither the per-execution
scratch (`mentis.foundation.scratch`, private to one session, disposable) nor
artifact custody (`mentis.artifacts`, durable bytes that cross between work).
It is a source tree owned by a request, handed back as a branch.

WHERE. `<corpus>/worktrees/<expectation>`, with a sidecar
`<expectation>.mentis.json` written BEFORE git creates the directory, so a
crash between the two leaves something recognisable as Mentis's. Branches are
`mentis/<expectation>`. The git operations run in the owner's process, against
the server's project repository.
"""

from __future__ import annotations

import collections
import json
import os
import pathlib
import re
import shutil
import subprocess
import threading
import time

DIR = "worktrees"
BRANCH = "mentis/"
SIDECAR = ".mentis.json"

PROVISIONED = "worktree-provisioned"
REATTACHED = "worktree-reattached"
REMOVED = "worktree-removed"
ABANDONED = "worktree-abandoned"
COMMITTED = "worktree-committed"
#: A review was given the reviewed request's own worktree to read, instead of
#: a tree of its own (`ensure`, `repository: {"review_of": ...}`).
LENT = "worktree-lent"
#: The folder was removed and the branch and record kept: work returned but
#: not integrated, parked until it is integrated, continued or abandoned.
PARKED = "worktree-parked"

_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")
_LOCK = threading.RLock()          # one lifecycle decision at a time, per process
#: Requests whose worktree a dispatch in this process is using, by count.
_HELD: collections.Counter = collections.Counter()
#: Reviews reading another request's worktree in this process: the reviewing
#: request -> the reviewed request whose tree it was lent. Under `_LOCK`.
_LENT: dict[str, str] = {}
#: ONE REQUEST'S WORKTREE AT A TIME, apart from every other request's. Taken
#: inside `_LOCK` by the lifecycle (`settle`, `ensure`) and ALONE by `commit`
#: and by the recording of unrecorded commits (`_record_outside`), neither
#: taking `_LOCK` under it: the order is always `_LOCK` then this, and a
#: commit waits for at most one settle of its own tree -- never for a
#: `reconcile` of all of them.
_REQUEST_LOCKS: dict[str, threading.RLock] = {}
_REQUEST_LOCKS_GUARD = threading.Lock()
#: How long `commit` waits for its own request's tree before saying it did
#: nothing. Under the worker's 30 s HTTP timeout (`worker._over`), so the
#: answer arrives while somebody is still listening for it.
COMMIT_WAIT_S = 15.0


def _request_lock(expectation) -> threading.RLock:
    with _REQUEST_LOCKS_GUARD:
        return _REQUEST_LOCKS.setdefault(expectation, threading.RLock())


class RepositoryRefused(ValueError):
    """The request's repository cannot be given, said in words."""


# -- git, and nothing clever ------------------------------------------------------

def _git(repo, *args, check=True, strip=True) -> str:
    """`strip=False` for output whose leading spaces MEAN something: the
    first porcelain status line is ` M path`, and stripping it turned the
    path into `ath` -- so a modified file read as a different, clean one."""
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
    if check and out.returncode != 0:
        raise RepositoryRefused(
            f"git {' '.join(args)} failed in {repo}: "
            f"{(out.stderr or out.stdout).strip()[:400]}")
    if out.returncode != 0:
        return ""
    return out.stdout.strip() if strip else out.stdout


def _ok(repo, *args) -> bool:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True
                          ).returncode == 0


def is_repository(path) -> bool:
    return bool(path) and _ok(path, "rev-parse", "--git-dir")


# -- where ------------------------------------------------------------------------

def root(record) -> pathlib.Path:
    return pathlib.Path(record) / DIR


def path_for(record, expectation) -> pathlib.Path:
    if not expectation or not _SAFE.match(expectation):
        raise RepositoryRefused(f"{expectation!r} cannot name a worktree")
    return root(record) / expectation


def _sidecar(record, expectation) -> pathlib.Path:
    return root(record) / (expectation + SIDECAR)


def branch_for(expectation) -> str:
    return BRANCH + expectation


def _same(a, b) -> bool:
    return os.path.normcase(os.path.abspath(str(a))) == \
        os.path.normcase(os.path.abspath(str(b)))


def owned(record, info) -> str | None:
    """Why this is NOT this Brain's own worktree, or None when it is.

    A path in the record or in a sidecar is a claim, not a licence. Mentis
    acts only on `<root(record)>/<expectation>` on branch
    `mentis/<expectation>`, with the sidecar it wrote beside it saying the
    same. A copied Brain carries the original's record, and with it the
    original's paths; this is what keeps it from removing them.
    """
    exp = info.get("expectation") or ""
    try:
        mine = path_for(record, exp)
    except RepositoryRefused as exc:
        return str(exc)
    if not _same(info.get("path") or "", mine):
        return (f"{info.get('path')} is not under this Brain's worktrees "
                f"({root(record)})")
    if info.get("branch") != branch_for(exp):
        return f"{info.get('branch')!r} is not {branch_for(exp)!r}"
    try:
        side = json.loads(_sidecar(record, exp).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return f"no readable sidecar {_sidecar(record, exp)} says it is ours"
    if not (isinstance(side, dict) and _same(side.get("path") or "", mine)
            and side.get("branch") == info["branch"]
            and _same(side.get("repo") or "", info.get("repo") or "")):
        return f"the sidecar {_sidecar(record, exp)} does not match"
    return None


# -- what the record says ---------------------------------------------------------

def declared(cv, expectation) -> dict | None:
    """The request's declaration, or None: repository access is never
    inferred from the work's words.

    WHERE A DECLARATION IS, which is where the record already keeps what a
    request is carried under. Its own record, when it was made with one; or,
    for discovered work somebody PICKED UP, the latest pick-up -- the
    assigning act, which is where picking up already says reach and governed
    material (`artifacts._delegation`, `dispatch._governed_for`) because the
    discovered request's own record is never rewritten. The latest pick-up is
    the one in force, as for reach.
    """
    if not expectation:
        return None
    exp = cv._act(expectation)
    if exp is None or exp["act"] != "expectation-recorded":
        return None
    picked = [a for a in cv.history(caused_by=expectation)
              if a["act"] == "expectation-assigned"
              and (a["detail"] or {}).get("picked_up_under")]
    if picked:
        return (picked[-1]["detail"] or {}).get("repository")
    return (exp.get("detail") or {}).get("repository")


def _acts(cv, expectation) -> list[dict]:
    return [a for a in cv.history(caused_by=expectation)
            if a["act"] in (PROVISIONED, REATTACHED, REMOVED, ABANDONED,
                            PARKED)]


def recorded(cv, expectation) -> dict | None:
    """What was provisioned for this request, and whether it was removed,
    abandoned or parked since. None if nothing ever was."""
    acts = _acts(cv, expectation)
    made = [a for a in acts if a["act"] == PROVISIONED]
    if not made:
        return None
    latest = made[-1]
    info = dict(latest["detail"])
    info["provisioned_by"] = latest["id"]
    # Removal is about THIS provisioning: a request continued after its
    # earlier work was integrated gets a worktree again. Abandonment is the
    # owner's word about the request, and it stands whenever it was said.
    info["removed_by"] = next((a["id"] for a in acts if a["act"] == REMOVED
                               and a["at"] >= latest["at"]), None)
    info["abandoned_by"] = next((a["id"] for a in acts
                                 if a["act"] == ABANDONED), None)
    # PARKED until attached again or removed: the latest of those acts about
    # this provisioning says which.
    parked = None
    for a in acts:
        if a["at"] < latest["at"]:
            continue
        if a["act"] == PARKED:
            parked = a["id"]
        elif a["act"] in (REATTACHED, REMOVED, PROVISIONED):
            parked = None
    info["parked_by"] = parked
    return info


def _closed(cv, expectation) -> str | None:
    """Why this request is closed, or None while it is open. Fulfilment is the
    carrier's claim that it is answered; it says nothing about integration."""
    try:
        s = cv.expectation_state(expectation)
    except ValueError:
        return "unknown-request"
    return "fulfilled" if s["satisfied_by"] else None


# -- provisioning ------------------------------------------------------------------

def ensure(cv, record, repo, expectation) -> dict | None:
    """The worktree this request owns, provisioned on its first run.

    Returns None for a request that declared no repository -- which is every
    request that did not say so. Raises `RepositoryRefused` with the reason
    when one was declared and cannot be given.
    """
    decl = declared(cv, expectation)
    if not decl:
        return None
    with _LOCK, _request_lock(expectation):
        if decl.get("review_of"):
            got = _review(cv, record, repo, expectation, decl["review_of"])
            _HELD[expectation] += 1
            return got
        # A TREE LENT TO A REVIEW IS BEING READ: its own request's run
        # editing it now would change what the review is judging under it.
        readers = sorted(r for r, lent in _LENT.items() if lent == expectation)
        if readers:
            raise RepositoryRefused(
                f"this request's worktree is lent to review "
                f"{', '.join(readers)}, which is reading it now; this run "
                "would change it under the review. Run it again once that "
                "review's run has ended")
        got = _ensure(cv, record, repo, expectation, decl)
        # HELD FROM HERE UNTIL THE DISPATCH THAT ASKED ENDS (`release`), so a
        # reconcile at the end of some other run cannot remove the tree in
        # the gap before this run is recorded as live.
        _HELD[expectation] += 1
        return got


def _unhold(expectation) -> None:
    if _HELD[expectation] > 1:
        _HELD[expectation] -= 1
    else:
        _HELD.pop(expectation, None)


def release(expectation) -> None:
    """The dispatch that `ensure`d this request's worktree has ended -- and,
    for a review that was lent the reviewed request's tree, that tree is
    no longer being read."""
    with _LOCK:
        _unhold(expectation)
        lent = _LENT.pop(expectation, None)
        if lent:
            _unhold(lent)


def held_by_a_run(cv, expectation) -> str | None:
    """Why a run holds this request's worktree now, or None: a dispatch in
    this process is using it, it is lent to a review, or the record holds a
    run of the request open (wherever that run is)."""
    if _HELD.get(expectation):
        return "a run in this process is using it"
    if expectation in _LENT.values():
        return "it is lent to a review"
    try:
        if any(r.get("caused_by") == expectation for r in cv.open_runs()):
            return "the record holds a run of it open"
    except Exception as exc:                              # noqa: BLE001
        return f"whether a run holds it could not be read ({exc})"
    return None


def _review(cv, record, repo, expectation, reviewed) -> dict:
    """A review's repository: the reviewed request's EXISTING worktree, lent
    to read, when nothing holds it -- not a new branch and tree for every
    review and retry. Under `_LOCK`.

    LENT ONLY WHILE IDLE. If a run holds the reviewed tree (`held_by_a_run`)
    a review reading it would see edits half made, so the review gets what
    it got before this existed: its own worktree, cut from the reviewed
    request's branch. Once it has its own, every later run of the review
    reuses it (`_ensure`), so retries do not cut more.

    READ-ONLY BY WHAT IT IS TOLD AND WHAT IT CAN DO THROUGH MENTIS: the
    review owns no worktree, so `commit_work` refuses it, and its note says
    the tree is another request's. A process running as the owner can still
    write files there; that is the boundary every worktree already has.
    Held (`_HELD`) for the reviewed request while lent, so `reconcile` does
    not remove it under the review; given back by `release`.
    """
    own = recorded(cv, expectation)
    if own and not own["removed_by"] and not own["abandoned_by"]:
        return _ensure(cv, record, repo, expectation,
                       {"from_parent": reviewed})
    up = recorded(cv, reviewed)
    why = None
    if not up or up["removed_by"] or up["abandoned_by"]:
        why = "the reviewed request owns no live worktree"
    elif owned(record, up):
        why = f"the reviewed worktree is not this Brain's: {owned(record, up)}"
    else:
        why = held_by_a_run(cv, reviewed)
        if not why and (not pathlib.Path(up["path"]).is_dir()
                        or is_residue(up["repo"], up["path"])):
            # PARKED (or lost), or RESIDUE of a removal that stopped partway
            # (no .git, not registered): never lent as it stands. The
            # branch is the work, and the review reads
            # it where its request's own run would -- attached again, under
            # the reviewed request's own lock (after this request's: the
            # one place two request locks are held, and nothing that holds
            # a request lock alone ever waits for another).
            try:
                with _request_lock(reviewed):
                    _ensure(cv, record, repo, reviewed, {})
            except RepositoryRefused as exc:
                why = f"the reviewed worktree is missing and could not be " \
                      f"attached again: {exc}"
    if why:
        if not up or up["removed_by"] or up["abandoned_by"]:
            raise RepositoryRefused(
                f"this review reads the worktree of {reviewed}, which owns no "
                "live worktree to read or branch from")
        return _ensure(cv, record, repo, expectation,
                       {"from_parent": reviewed})
    _HELD[reviewed] += 1
    _LENT[expectation] = reviewed
    head = _git(up["path"], "rev-parse", "HEAD", check=False) or None
    exp = cv._act(expectation)
    cv.record_act(actor="mentis", act=LENT,
                  conversation=exp["conversation"], turn=exp["turn"],
                  caused_by=expectation, about=[reviewed],
                  because="a review reads the reviewed request's own "
                          "worktree while no run holds it",
                  detail={"path": up["path"], "branch": up["branch"],
                          "head": head, "reviewed": reviewed})
    return {**up, "lent_from": reviewed, "head": head, "read_only": True}


def _ensure(cv, record, repo, expectation, decl) -> dict:
    got = recorded(cv, expectation)
    if got and got["abandoned_by"]:
        raise RepositoryRefused(
            f"the owner abandoned the worktree this request owned "
            f"({got['abandoned_by']}); it is not recreated. Ask for the "
            "work again.")
    if got and got["removed_by"]:
        # CONTINUED AFTER ITS WORK WAS INTEGRATED. The same request, so
        # the same branch name -- cut from where that work went, which is
        # the only place it now is.
        target = got.get("integration_target")
        if not target or not _ok(got["repo"], "show-ref", "--verify",
                                 "--quiet", "refs/heads/" + target):
            raise RepositoryRefused(
                f"this request's earlier worktree was removed as "
                f"integrated into {target!r}, which no longer exists; "
                "there is nothing to continue from")
        return _provision(cv, record, got["repo"], expectation,
                          {"base": target, "_continues":
                           got["provisioned_by"],
                           "_target": target, "_parent": got.get("parent")})
    if got:
        foreign = owned(record, got)
        if foreign:
            raise RepositoryRefused(
                f"the recorded worktree is not this Brain's: {foreign}")
        where = pathlib.Path(got["path"])
        residue = is_residue(got["repo"], where)
        if where.is_dir() and not residue:
            return got
        # PARKED AT CLOSEOUT, OR CRASHED OR DELETED UNDER US. The branch is
        # the work; put it back where it was rather than cutting a new one
        # from the base. Attaching again clears the parked state
        # (`recorded`).
        _git(got["repo"], "worktree", "prune")
        if not _ok(got["repo"], "show-ref", "--verify", "--quiet",
                   "refs/heads/" + got["branch"]):
            raise RepositoryRefused(
                f"{got['path']} is gone and so is branch {got['branch']}; "
                "there is nothing to reattach")
        moved = None
        if residue:
            # NEVER HANDED TO A RUN: what a failed removal left is set aside
            # (it may hold edits that removal interrupted), and the branch
            # is attached at the path. Refused, in words, if it is locked.
            moved = set_aside(where, RESIDUE)
        _git(got["repo"], "worktree", "add", str(where), got["branch"])
        parked = got.get("parked_by")
        cv.record_act(actor="mentis", act=REATTACHED,
                      conversation=cv._act(expectation)["conversation"],
                      caused_by=expectation, about=[expectation],
                      because=("the worktree was parked at closeout; its "
                               "branch is attached again for the request's "
                               "continuation" if parked else
                               "the folder was residue of a removal that "
                               "did not finish; set aside, and the branch "
                               "attached again" if moved else
                               "the recorded worktree was missing; its "
                               "branch was attached again"),
                      detail={"path": str(where), "branch": got["branch"],
                              "parked_by": parked,
                              "residue_moved_to": moved and moved["path"],
                              "residue_files": moved and moved["files"]})
        return {**got, "parked_by": None}
    return _provision(cv, record, repo, expectation, decl)


def _provision(cv, record, repo, expectation, decl) -> dict:
    parent = decl.get("from_parent") or decl.get("_parent")
    if decl.get("_continues"):
        base = decl["base"]
        target = decl["_target"]
    elif parent:
        up = recorded(cv, parent)
        if not up or up["removed_by"] or up["abandoned_by"]:
            raise RepositoryRefused(
                f"this request takes its repository from {parent}, which owns "
                "no live worktree to branch from")
        repo, base, target = up["repo"], up["branch"], up["branch"]
    else:
        base = str(decl.get("base") or "").strip()
        if not base:
            raise RepositoryRefused("a repository request names its base")
        # NO REPOSITORY CONFIGURED IS AN ANSWER, NOT A FALLBACK. A server
        # started without --repository has none; it used to cut worktrees from
        # its workspace instead, which on a published release is the release
        # itself. Refused in words, recorded before the run starts.
        if not repo:
            raise RepositoryRefused(
                "this request declares a repository, and this Mentis has no "
                "repository configured to cut its worktree from (it was "
                "started without --repository). Nothing falls back to the "
                "workspace; start it with --repository <path>.")
        if not is_repository(repo):
            raise RepositoryRefused(
                f"{repo} is not a git repository, so no worktree can be cut "
                "from it")
        # The integration target is the base where the base is a branch. A
        # commit has no branch to be integrated into, so such a worktree is
        # only ever removed by being explicitly abandoned.
        target = base if _ok(repo, "show-ref", "--verify", "--quiet",
                             "refs/heads/" + base) else None
        if decl.get("branch") and not target:
            raise RepositoryRefused(
                f"{base!r} is not a branch of {repo}; a worktree declared "
                "from a branch is cut from one that exists")
    repo = str(pathlib.Path(repo).resolve())
    base_commit = _git(repo, "rev-parse", "--verify",
                       ("refs/heads/" + base if decl.get("branch") else base)
                       + "^{commit}")
    if decl.get("_continues"):
        # A continuation branches from where its work was integrated.
        why_ = ("the same request continued after its earlier work was "
                f"integrated into {target}")
    else:
        why_ = "this request explicitly requires an isolated repository"
    where = path_for(record, expectation)
    branch = branch_for(expectation)
    if _ok(repo, "show-ref", "--verify", "--quiet", "refs/heads/" + branch):
        raise RepositoryRefused(
            f"branch {branch} already exists and no worktree is recorded for "
            "it; reconcile before provisioning over it")
    exp = cv._act(expectation)
    info = {"expectation": expectation, "repo": repo, "path": str(where),
            "branch": branch, "base": base, "base_commit": base_commit,
            "integration_target": target, "parent": parent,
            "continues": decl.get("_continues"), "why": why_}
    # THE SIDECAR FIRST, so a crash before the act still leaves a directory
    # that says whose it is.
    root(record).mkdir(parents=True, exist_ok=True)
    _sidecar(record, expectation).write_text(
        json.dumps({**info, "created_at": time.time()}, indent=1),
        encoding="utf-8")
    _git(repo, "worktree", "add", "-b", branch, str(where), base_commit)
    act = cv.record_act(actor="mentis", act=PROVISIONED,
                        conversation=exp["conversation"], turn=exp["turn"],
                        caused_by=expectation, about=[expectation],
                        because=info["why"], detail=info)
    return {**info, "provisioned_by": act, "removed_by": None,
            "abandoned_by": None, "parked_by": None}


# -- which ignored material is disposable -------------------------------------------
#
# AS DECIDED (ent-aa55639d512a, option B): known disposable build and cache
# material may go with the worktree; ANY OTHER ignored file preserves it.
# Git-ignored is not disposable -- it only means "not tracked", and a log, an
# export or a scratch folder a worker made is a work product. So the set is
# defined by what the material IS, shown by evidence in the worktree, never by
# a filename pattern alone:
#
#   python bytecode  a .pyc/.pyo file directly inside a __pycache__ folder --
#                    where Python itself writes what it compiles from source
#   declared cache   a folder carrying a valid CACHEDIR.TAG, the standard way
#                    a tool says "everything in here is a cache" (pytest does)
#   npm install      a node_modules folder with npm's own record of what it
#                    installed (.package-lock.json) beside a package-lock.json
#                    that is COMMITTED and UNMODIFIED -- so it is reproducible
#                    from the repository by `npm ci`
#
# A file qualifies only through one of its OWN ancestor folders. Anything that
# cannot be shown -- a quoted path git had to escape, a folder whose tag does
# not verify, a lock file that is modified or untracked -- preserves the
# worktree and is reported. Build output such as ui/dist is deliberately not
# in the set: nothing in it shows it was produced by a build rather than
# placed there.

CACHEDIR_SIGNATURE = b"Signature: 8a477f597d28d172789f06886806bc55"


def _cache_root(where, rel_dir: str, tracked_clean) -> str | None:
    """Why this folder is disposable cache, or None."""
    d = pathlib.Path(where, rel_dir)
    name = d.name
    try:
        with open(d / "CACHEDIR.TAG", "rb") as fh:
            if fh.read(len(CACHEDIR_SIGNATURE)) == CACHEDIR_SIGNATURE:
                return "declares itself a cache (CACHEDIR.TAG)"
    except OSError:
        pass
    if name == "node_modules" and (d / ".package-lock.json").is_file():
        parent = str(pathlib.PurePosixPath(rel_dir).parent)
        lock = ("package-lock.json" if parent in (".", "")
                else f"{parent}/package-lock.json")
        if tracked_clean(lock):
            return ("npm install output, reproducible from the committed, "
                    f"unmodified {lock}")
    return _build_output(where, d)


#: What the UI build writes into its own output to say what it was built from
#: (`ui/build-identity.mjs`). Read as evidence, never trusted as a name.
BUILD_STAMP = "build-identity.json"
#: A file written after the build finished is not shown to be its output.
_BUILD_SLACK_S = 120
_SHA = re.compile(r"^[0-9a-f]{40}$")


def _build_output(where, d: pathlib.Path) -> str | None:
    """Why this folder is the UI build's own output, or None.

    AS DECIDED (Development and Integration, 2026-10-03): build output is
    disposable when the folder itself shows it -- the build's stamp says it
    was made from a CLEAN tree at a commit this worktree's HEAD contains, and
    nothing in it is newer than that stamp. It is then reproducible from
    committed source by building again. A dirty build, a build of a commit
    this tree does not hold, or a file added after the build still preserves
    the worktree.
    """
    stamp = d / BUILD_STAMP
    try:
        said = json.loads(stamp.read_text(encoding="utf-8"))
        made = stamp.stat().st_mtime
    except (OSError, ValueError):
        return None
    if not isinstance(said, dict):
        return None
    commit = said.get("commit")
    if (said.get("dirty") is not False or not isinstance(commit, str)
            or not _SHA.match(commit)):
        return None
    if not _ok(where, "merge-base", "--is-ancestor", commit, "HEAD"):
        return None
    for f in d.rglob("*"):
        try:
            if f.is_file() and f.stat().st_mtime > made + _BUILD_SLACK_S:
                return None
        except OSError:
            return None
    return (f"UI build output of clean commit {commit[:10]}, which this "
            "worktree holds; rebuilt from committed source")


def classify_ignored(where, ignored, dirty) -> tuple[dict, list]:
    """Split ignored paths into disposable (grouped by the cache folder that
    makes them so, with the reason) and kept (everything else)."""
    modified = {l[3:].strip() for l in dirty or ()}
    tracked_memo: dict[str, bool] = {}

    def tracked_clean(rel: str) -> bool:
        if rel not in tracked_memo:
            tracked_memo[rel] = (rel not in modified and _ok(
                where, "ls-files", "--error-unmatch", "--", rel))
        return tracked_memo[rel]

    root_memo: dict[str, str | None] = {}
    disposable: dict[str, dict] = {}
    kept: list[str] = []
    for rel in ignored or ():
        if rel.startswith('"'):
            kept.append(rel)            # git had to escape it: not reasoned about
            continue
        path = pathlib.PurePosixPath(rel.rstrip("/"))
        why, root = None, None
        if (path.suffix in (".pyc", ".pyo")
                and path.parent.name == "__pycache__"):
            root = str(path.parent)
            why = "compiled Python bytecode, regenerated from source"
        else:
            for anc in path.parents:
                a = str(anc)
                if a in (".", ""):
                    break
                if a not in root_memo:
                    root_memo[a] = _cache_root(where, a, tracked_clean)
                if root_memo[a]:
                    root, why = a, root_memo[a]
                    break
        if why:
            g = disposable.setdefault(root, {"why": why, "files": 0})
            g["files"] += 1
        else:
            kept.append(rel)
    return disposable, kept


# -- residue: a folder that is no longer a worktree -----------------------------------
#
# FOUND BY REVIEW (and on the live Brain, 10 of 37 folders). On Windows
# `git worktree remove` deletes in directory order, so `.git` goes first; a
# locked file then stops it with the admin entry already dropped. What is left
# is a folder of tracked files that git no longer knows: RESIDUE. Read as a
# worktree it looked like an unfinished operation forever, was handed to the
# next run as its workspace (edits in a non-repository, `commit_work` refused),
# and the cleanup tool deleted it. So: a folder is residue when its `.git` is
# missing AND git's own list no longer names it; residue is never a worktree
# (`status` reads it as absent), is never handed to a run, and is never
# deleted -- it is SET ASIDE by rename, counted, and the branch is attached
# again at the path. And a folder is removed in a safe order: renamed aside
# first (atomic, and refused as a whole by a lock), the admin entry pruned,
# the renamed copy deleted last, so a lock can never leave a half-worktree.

RESIDUE = "residue"        # set aside, contents unknown: never deleted by Mentis
DISCARD = "discard"        # a clean, integrated or parked tree mid-deletion
_ASIDE = re.compile(r"^(?P<expectation>.+)\.(?P<kind>residue|discard)-"
                    r"\d{8}-\d{6}(?:-\d+)?$")


def _registered(repo) -> set[str]:
    """Every worktree path git knows for this repository, normalised."""
    out = _git(repo, "worktree", "list", "--porcelain", check=False)
    return {os.path.normcase(os.path.abspath(l[len("worktree "):].strip()))
            for l in out.splitlines() if l.startswith("worktree ")}


def _locked(repo, where) -> bool:
    """Whether git holds this worktree locked (`git worktree lock`): the
    owner's word that it is not to be removed, honoured as git itself
    would."""
    want = os.path.normcase(os.path.abspath(str(where)))
    current = None
    for line in _git(repo, "worktree", "list", "--porcelain",
                     check=False).splitlines():
        if line.startswith("worktree "):
            current = os.path.normcase(os.path.abspath(
                line[len("worktree "):].strip()))
        elif line.startswith("locked") and current == want:
            return True
    return False


def is_residue(repo, where) -> bool:
    """Whether `where` is a folder that is no longer a worktree: present,
    without its `.git`, and not among the worktrees git lists."""
    p = pathlib.Path(where)
    if not p.is_dir() or (p / ".git").exists():
        return False
    return os.path.normcase(os.path.abspath(str(p))) not in _registered(repo)


def _count_files(where) -> int:
    n = 0
    try:
        for f in pathlib.Path(where).rglob("*"):
            if f.is_file():
                n += 1
    except OSError:
        pass
    return n


def aside_name(where, kind=RESIDUE) -> pathlib.Path:
    """`<folder>.<kind>-<timestamp>`, beside the folder; a free name."""
    p = pathlib.Path(where)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    cand = p.with_name(f"{p.name}.{kind}-{stamp}")
    n = 1
    while cand.exists():
        n += 1
        cand = p.with_name(f"{p.name}.{kind}-{stamp}-{n}")
    return cand


def set_aside(where, kind=RESIDUE) -> dict:
    """Rename the folder aside, in its own parent (atomic on one volume).
    Says where it went and how many files it held. Raises
    `RepositoryRefused` when the rename is refused -- a file inside it is
    open, so the folder is in use and nothing is done to it."""
    where = pathlib.Path(where)
    files = _count_files(where)
    target = aside_name(where, kind)
    try:
        os.rename(where, target)
    except OSError as exc:
        raise RepositoryRefused(
            f"{where} could not be set aside ({exc.strerror or exc}): a "
            "file in it is open or locked; nothing was changed") from exc
    return {"path": str(target), "files": files, "kind": kind}


def _discard_folder(repo, where, *, force=False) -> dict:
    """Delete a worktree's folder in the safe order. The tree is clean when
    this is called (or abandoned, `force`); checked once more by git right
    before. Rename aside first: refused as a whole if anything in it is
    open, with nothing changed. Then prune the admin entry (its path no
    longer exists), then delete the renamed copy. A delete that stops
    partway leaves `residue_left`: a folder git no longer knows, named
    `.discard-`, holding nothing that is not on the branch."""
    if not force and _git(where, "status", "--porcelain",
                          "--untracked-files=all", check=False,
                          strip=False).strip():
        raise RepositoryRefused(f"{where} is not clean; nothing was removed")
    if _locked(repo, where):
        raise RepositoryRefused(
            f"{where} is locked (`git worktree lock`); nothing was removed")
    moved = set_aside(where, DISCARD)
    _git(repo, "worktree", "prune", check=False)
    try:
        shutil.rmtree(moved["path"])
    except OSError as exc:
        return {"gone": False, "residue_left": moved["path"],
                "why": f"{exc.strerror or exc}"}
    return {"gone": True, "residue_left": None}


def residues(record) -> list[dict]:
    """Folders set aside under the worktree root, by kind and request."""
    out = []
    r = root(record)
    if not r.is_dir():
        return out
    for d in r.iterdir():
        m = _ASIDE.match(d.name) if d.is_dir() else None
        if m:
            out.append({"path": str(d), "kind": m.group("kind"),
                        "expectation": m.group("expectation")})
    return out


# -- state, computed and never stored ---------------------------------------------

#: What an unfinished git operation leaves in a worktree's OWN git directory.
#: `rebase-apply` is also `git am`; `sequencer` is a multi-commit cherry-pick
#: or revert; `BISECT_START` is written by every bisect, `BISECT_LOG` once
#: it has a step.
OPERATIONS = {
    "rebase-merge": "a rebase", "rebase-apply": "a rebase or am",
    "MERGE_HEAD": "a merge", "CHERRY_PICK_HEAD": "a cherry-pick",
    "REVERT_HEAD": "a revert", "sequencer": "a cherry-pick or revert sequence",
    "BISECT_LOG": "a bisect", "BISECT_START": "a bisect",
}


def operations(where) -> list[str]:
    """The unfinished git operations in this worktree, by what marks them.
    A git directory that cannot be read is reported as one, not as none."""
    gd = _git(where, "rev-parse", "--git-dir", check=False)
    if not gd:
        return ["unreadable git directory"]
    gd = pathlib.Path(gd)
    if not gd.is_absolute():
        gd = pathlib.Path(where) / gd
    return [m for m in OPERATIONS if (gd / m).exists()]


def reflog_tips(info: dict, st: dict) -> list[dict]:
    """Commits the worktree's HEAD reflog or the branch's reflog reached that
    are NOT in the integration target: what removal would leave unreachable
    by any name. Recorded, never a reason to keep the worktree -- a normal
    rebase leaves exactly this behind."""
    target = info.get("integration_target")
    has_target = bool(target) and _ok(info["repo"], "show-ref", "--verify",
                                      "--quiet", "refs/heads/" + target)
    seen: dict[str, dict] = {}
    logs = []
    if st["exists"]:
        logs.append((info["path"], "HEAD", "worktree HEAD"))
    if st["branch_exists"]:
        logs.append((info["repo"], "refs/heads/" + info["branch"],
                     info["branch"]))
    for repo, ref, label in logs:
        out = _git(repo, "reflog", "show", "--format=%H %gs", ref,
                   check=False)
        for line in out.splitlines():
            commit, _, subject = line.partition(" ")
            if not commit:
                continue
            if commit in seen:
                if label not in seen[commit]["reflogs"]:
                    seen[commit]["reflogs"].append(label)
                continue
            seen[commit] = {"commit": commit, "reflogs": [label],
                            "entry": subject}
    if has_target and seen:
        # ONE git call for every commit, not one per commit: which of them
        # the target does not reach. What the lifecycle does under its lock
        # must not grow with the commits a tree holds (measured by test).
        out = subprocess.run(
            ["git", "-C", str(info["repo"]), "rev-list",
             "--no-walk=unsorted", "--stdin"],
            input="\n".join([*seen, "^refs/heads/" + target]) + "\n",
            capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        if out.returncode == 0:
            outside = set(out.stdout.split())
            seen = {c: t for c, t in seen.items() if c in outside}
    return list(seen.values())


def status(info: dict) -> dict:
    """What git says about a request's worktree right now.

    INTEGRATED MEANS EVERYTHING THAT WOULD GO. Removal takes the worktree and
    deletes the branch, so both the branch AND the worktree's own HEAD must
    be in the target: a HEAD detached, or moved to a commit the branch does
    not hold, carries work nothing else may. A HEAD git cannot read is not
    integrated.

    HOLDING SOMETHING includes git-ignored files, listed apart as `ignored`:
    porcelain status leaves them out, and `git worktree remove` deletes them
    without a word. They are then split (`classify_ignored`): known
    disposable cache in `ignored_disposable`, everything else in
    `ignored_kept`, which preserves the worktree.

    AN UNFINISHED OPERATION -- a stopped rebase, a merge or cherry-pick in
    progress (`operations`) -- is unfinished work even when the tree reads
    clean and HEAD integrated, and preserves the worktree.

    RESIDUE (`is_residue`) IS NOT A WORKTREE: `exists` is False and
    `residue` True, so nothing reads its missing git directory as an
    operation in progress, and the lifecycle treats the folder as gone --
    after setting it aside.
    """
    repo, where, branch = info["repo"], info["path"], info["branch"]
    exists = pathlib.Path(where).is_dir()
    residue = exists and is_residue(repo, where)
    exists = exists and not residue
    has_branch = _ok(repo, "show-ref", "--verify", "--quiet",
                     "refs/heads/" + branch)
    out = {"path": where, "branch": branch, "exists": exists,
           "residue": residue,
           "branch_exists": has_branch, "dirty": None, "ignored": None,
           "ignored_disposable": None, "ignored_kept": None,
           "head": None, "worktree_head": None, "detached": None,
           "operations": None,
           "commits_beyond_base": None, "integrated": None,
           "integration_target": info.get("integration_target")}
    if exists:
        out["operations"] = operations(where)
        lines = [l for l in _git(where, "status", "--porcelain", "--ignored",
                                 "--untracked-files=all", check=False,
                                 strip=False).splitlines() if l.strip()]
        out["dirty"] = [l for l in lines if not l.startswith("!! ")]
        out["ignored"] = [l[3:] for l in lines if l.startswith("!! ")]
        out["ignored_disposable"], out["ignored_kept"] = classify_ignored(
            where, out["ignored"], out["dirty"])
        out["worktree_head"] = _git(where, "rev-parse", "--verify", "HEAD",
                                    check=False) or None
        out["detached"] = not _ok(where, "symbolic-ref", "-q", "HEAD")
    if has_branch:
        out["head"] = _git(repo, "rev-parse", branch)
        out["commits_beyond_base"] = int(_git(
            repo, "rev-list", "--count", f"{info['base_commit']}..{branch}")
            or 0)
        target = info.get("integration_target")
        if target and _ok(repo, "show-ref", "--verify", "--quiet",
                          "refs/heads/" + target):
            out["integrated"] = _ok(repo, "merge-base", "--is-ancestor",
                                    branch, target)
            if out["integrated"] and exists:
                wh = out["worktree_head"]
                out["integrated"] = bool(wh) and _ok(
                    repo, "merge-base", "--is-ancestor", wh, target)
    return out


# -- the lifecycle ------------------------------------------------------------------

def settle(cv, record, expectation) -> dict:
    """Apply the lifecycle to one request's worktree. Says what it did.

      running     a run is inside it, or it is lent to a review: nothing is
                  touched
      removed     its work is integrated into its target and nothing is
                  uncommitted -- whether or not anybody claimed the request
                  answered. An OPEN request's worktree goes when no run is
                  in it, everything on it is integrated, it waits on
                  nothing, and no child worktree of it is still alive; a
                  continuation of it gets one again, from where the work went
      parked      CLOSEOUT of returned work nobody integrated: its run ended,
                  nothing holds it, it is clean (uncommitted changes were
                  first committed as WIP on its branch, `_closeout_commit`)
                  and its branch holds commits the target does not. The
                  FOLDER is removed; the branch, sidecar and record stay,
                  and `ensure` attaches it again when the request is
                  continued. Recorded as `worktree-parked`
      abandoned   the owner abandoned it: removed, the tip recorded first
      unresolved  closed, but not clean -- ignored files that are not known
                  disposable cache, a HEAD off the request's branch -- or,
                  open or closed, a git operation still in progress:
                  PRESERVED, and reported with exactly what is outstanding
      open        kept for the request's next run: it waits on other work,
                  its run was interrupted (the owner's to continue), or a
                  child's worktree cut from it is still alive

    WHAT CLOSEOUT NEVER TOUCHES: a tree a run holds (`_HELD`), one lent to a
    review (`_LENT`), one whose request has a live execution, one with a
    git operation in progress, or one whose HEAD is not on the request's own
    branch. The WIP commit lands on that branch only, and a branch is deleted
    only when the target holds every commit on it.

    MEASURED, AND WHY THE RULE IS NOT "CLOSED". In the real acceptance run
    the child replied without claiming the request answered; its branch was
    merged, clean, and still kept, because the request was open. Integrated
    work is the owner's criterion.

    A WORKTREE WITH NO COMMITS GOES TOO, once its run has ended. It used to be
    kept while its request was open, on the grounds that "nothing has been
    done yet" -- and measured on the live Brain (2026-10-08), 29 of 112 live
    worktrees were held by exactly that and nothing else: reviews and probes
    that never commit, under requests nobody marks met, kept forever. Removing
    one loses nothing (it is clean, holds no unknown ignored file and no
    commit), and a later run of the same request is cut a fresh one from
    where the work went.
    """
    return _settle(cv, record, expectation,
                   _record_outside(cv, record, expectation))


#: A branch tip no pass recorded through: never equal to a real one.
_UNRECORDED = object()


def _record_outside(cv, record, expectation):
    """Record every commit of this request's branch no act holds, OUTSIDE
    `_LOCK`: under this request's lock only. Returns the branch tip it
    recorded through (None with no branch), or `_UNRECORDED`.

    WHY OUTSIDE (found by review). Recording walks the branch's whole
    first-parent line, and for each commit no act holds reads it and writes
    an act -- work that grows with the commits, and that inside `settle`
    held the lock every other lifecycle decision in the process waits for.
    Nothing here needs that lock: the request's own lock keeps its commit
    out, and `_settle` then checks, in one comparison it already has the
    answer for, that the tip has not moved since."""
    with _request_lock(expectation):
        info = recorded(cv, expectation)
        if info is None or info["removed_by"] or owned(record, info):
            return _UNRECORDED
        record_unrecorded(cv, info)
        return _git(info["repo"], "rev-parse", "-q", "--verify",
                    "refs/heads/" + info["branch"], check=False) or None


def _settle(cv, record, expectation, through) -> dict:
    """`settle` under the lock, once its branch is recorded through
    `through`."""
    with _LOCK, _request_lock(expectation):
        info = recorded(cv, expectation)
        if info is None:
            return {"expectation": expectation, "state": "none"}
        if info["removed_by"]:
            return {"expectation": expectation, "state": "removed",
                    "by": info["removed_by"]}
        foreign = owned(record, info)
        if foreign:
            # Not read, not settled, not removed: reported.
            return {"expectation": expectation, "path": info["path"],
                    "branch": info["branch"], "state": "not-this-brains",
                    "why": foreign}
        st = status(info)
        base = {"expectation": expectation, **st,
                "parked_by": info["parked_by"]}
        if (_HELD[expectation] or expectation in _LENT.values()
                or cv.expectation_state(expectation)["live_execution"]):
            return {**base, "state": "running"}
        if st["head"] != through:
            # Before anything can remove the branch, every commit on it is
            # recorded (`_record_outside`). One landed since that pass:
            # nothing is decided now, and the next settle records it.
            return {**base, "state": "open",
                    "note": "its branch moved while it was being settled; "
                            "recorded and settled at the next settle"}
        if not info["abandoned_by"] and not _used_since_provisioned(cv, info):
            return {**base, "state": "open",
                    "note": "provisioned; no run has used it yet"}
        closed = _closed(cv, expectation)
        moved = None
        if st["residue"]:
            # WHAT A FAILED REMOVAL LEFT is set aside first, so the folder
            # is gone from the path whatever is decided below; a lock
            # refuses the rename as a whole and nothing is decided.
            try:
                moved = set_aside(info["path"], RESIDUE)
            except RepositoryRefused as exc:
                return _kept(base, closed, info, st, note=f"kept: {exc}")
            base = {**base, "residue_moved_to": moved["path"],
                    "residue_files": moved["files"]}
        out = _decide(cv, record, expectation, info, st, base, closed)
        return ({**out, "residue_moved_to": moved["path"],
                 "residue_files": moved["files"]} if moved else out)


def _decide(cv, record, expectation, info, st, base, closed) -> dict:
    """`_settle`'s decision for a tree nothing holds, once the record's
    commits are through and any residue is set aside."""
    if info["abandoned_by"]:
        return _remove(cv, record, info, st,
                       why="abandoned by the owner",
                       force=True, state="abandoned")
    if st["operations"]:
        # Unfinished work, open request or not: never removed here.
        return {**base, "state": "unresolved", "closed": closed,
                "outstanding": _outstanding(info, st),
                "note": "preserved: a git operation is still in "
                        "progress in this worktree"}
    if not st["exists"] and not st["branch_exists"]:
        return _remove(cv, record, info, st, state="removed",
                       why="neither its folder nor its branch exists "
                           "any more; nothing is left to keep, and the "
                           "registration is closed")
    clean = st["dirty"] in ([], None) and not st["ignored_kept"]
    if st["integrated"] and clean and closed:
        children = _live_children(cv, expectation)
        if children:
            # Its branch is a live child's integration target (review).
            return _kept(base, closed, info, st,
                         note=f"kept: {len(children)} child worktree(s) "
                              "cut from it are still alive, and its "
                              "branch is where they integrate")
        return _remove(cv, record, info, st, state="removed",
                       why=f"{closed} and integrated into "
                           f"{info['integration_target']}")
    return _closeout(cv, record, expectation, info, st, base, closed)


def _closeout(cv, record, expectation, info, st, base, closed) -> dict:
    """CLOSEOUT: its run has ended and nothing holds it (`settle`)."""
    waiting = cv.waiting_on(expectation)
    if waiting["outstanding"]:
        return _kept(base, closed, info, st,
                     note="kept: the request waits on other work "
                          f"({len(waiting['outstanding'])} outstanding)")
    if not closed and cv.interruption_hold(expectation, waiting=waiting):
        # INTERRUPTED WORK IS THE OWNER'S TO DECIDE (`mentis.wakecheck`):
        # its run was closed so the request stops reading as live, not so
        # its tree -- the "preserved" an agent and the owner are told
        # about -- can be committed, parked or removed under them. A
        # request claimed met is closed and settles above as before.
        return {**base, "state": "open",
                "note": "its run was interrupted; kept for the "
                        "owner to keep, resume or discard"}
    on_branch = (st["exists"] and not st["detached"]
                 and _on_branch(info["path"], info["branch"]))
    wip = None
    if st["exists"] and st["dirty"]:
        # UNCOMMITTED CHANGES LEFT BY A RUN THAT ENDED are unique work:
        # committed on the request's own branch, attributed to the run,
        # so nothing is lost and the tree reads clean. Never ignored
        # files (`git add -A` keeps the repository's own rules), and
        # never on a HEAD that is not that branch.
        if not on_branch:
            return _kept(base, closed, info, st,
                         note="preserved: its HEAD is not on the "
                              "request's branch, so nothing was "
                              "committed at closeout")
        wip = _closeout_commit(cv, info)
        if wip.get("refused"):
            return _kept(base, closed, info, st,
                         note="preserved: its uncommitted changes could "
                              f"not be committed at closeout: "
                              f"{wip['refused']}")
        st = status(info)
        base = {**base, **st, "closeout_commit": wip}
        if st["dirty"]:
            return _kept(base, closed, info, st,
                         note="preserved: changes remain uncommitted "
                              "after the closeout commit")
    out = _closeout_clean(cv, record, expectation, info, st, base,
                          closed, on_branch)
    return {**out, "closeout_commit": wip} if wip else out


def _closeout_clean(cv, record, expectation, info, st, base, closed,
                    on_branch) -> dict:
    """The closeout decision for a tree with nothing uncommitted: preserved
    for ignored files, removed when integrated, parked otherwise."""
    if st["ignored_kept"]:
        return _kept(base, closed, info, st,
                     note="preserved: it holds git-ignored files that "
                          "are not known disposable cache or build "
                          "output; nothing is removed under them")
    if st["integrated"]:
        children = _live_children(cv, expectation)
        if children:
            # A child's branch integrates into this one, so the branch
            # -- which removal deletes -- must outlive the child.
            return {**base, "state": "open",
                    "note": f"kept: {len(children)} child worktree(s) "
                            "cut from it are still alive"}
        return _remove(cv, record, info, st, state="removed",
                       why=f"its work is integrated into "
                           f"{info['integration_target']} and nothing "
                           "is uncommitted; the request is not "
                           "answered, and continuing it cuts a new "
                           "worktree from there")
    # NOT INTEGRATED: the branch holds work the target does not.
    if not st["exists"]:
        if info["parked_by"]:
            return {**base, "state": "parked", "by": info["parked_by"]}
        return _park(cv, record, info, st, closed=closed,
                     why="its folder was found missing while its branch "
                         "holds work not integrated into "
                         f"{info['integration_target']}; the branch is "
                         "the work, kept parked")
    if not on_branch:
        return _kept(base, closed, info, st,
                     note="preserved: its HEAD is not on the request's "
                          "branch")
    if _serving(info["path"]):
        return _kept(base, closed, info, st,
                     note="kept: a server is serving from this worktree")
    return _park(cv, record, info, st, closed=closed,
                 why=("its run ended and " + (
                     f"its branch holds {st['commits_beyond_base']} "
                     f"commit(s) not in {info['integration_target']}"
                     if st["integrated"] is False else
                     "no branch to integrate into was recorded, so "
                     "integration cannot be established")
                     + "; the folder is removed and the branch kept "
                       "for review, integration or continuation"
                     + ("; the request was claimed answered, which is "
                        "not permission to discard the work"
                        if closed else "")))


def _kept(base, closed, info, st, *, note) -> dict:
    """The folder stays: `open` for an open request, `unresolved` -- reported
    at start with what is outstanding -- for a closed one."""
    if not closed:
        return {**base, "state": "open", "note": note}
    return {**base, "state": "unresolved", "closed": closed,
            "outstanding": _outstanding(info, st), "note": note}


def _on_branch(where, branch) -> bool:
    """Whether the worktree's HEAD is the request's own branch."""
    return _git(where, "symbolic-ref", "-q", "HEAD", check=False) == \
        "refs/heads/" + branch


def _serving(where) -> bool:
    """Whether a server is -- or may be -- serving code from this tree.
    Unknown counts as yes: nothing is parked under a server."""
    from mentis import servers
    try:
        got = servers.serving_from(str(where))
    except Exception:                                      # noqa: BLE001
        return True
    return got is None or bool(got)


def _closeout_commit(cv, info) -> dict:
    """Commit what a run left uncommitted, on the request's branch, as WIP
    attributed to the run that left it. Under `_LOCK` and the request lock
    (`_settle`); `commit` takes the request lock alone, so the two never
    run together and neither waits for the other's git. The same flags as
    `_commit`: no hooks, no signing (a hook here would be the run escaping
    its sandbox)."""
    where, exp = info["path"], info["expectation"]
    starts = sorted((a for a in cv.history(caused_by=exp)
                     if a["act"] == "execution-started" and a.get("execution")),
                    key=lambda a: a["at"])
    by = None
    if starts:
        s = starts[-1]
        by = (f"{s['runtime']}/{s['execution'][:8]}" if s.get("runtime")
              else s["execution"])
    try:
        _git(where, "add", "-A")
        staged = _names(where, "diff", "--cached", "--name-only")
        if not staged:
            return {"committed": False, "files": []}
        message = (f"WIP at closeout ({exp}): {len(staged)} file(s) left "
                   f"uncommitted by run {by or 'unknown'}")
        _git(where, "-c", f"core.hooksPath={os.devnull}",
             "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify",
             "-m", message,
             *(["--trailer", f"Mentis-Execution: {by}"] if by else []))
    except RepositoryRefused as exc:
        return {"committed": False, "refused": str(exc)}
    sha = _git(where, "rev-parse", "HEAD")
    act = _record_commit(
        cv, info, sha, staged, by, merge=False,
        extra={"attributed_by": "closeout", "closeout": True},
        because="the run ended with changes uncommitted in its worktree; "
                "committed at closeout so the work is not lost")
    return {"committed": True, "commit": sha, "files": staged, "by": by,
            "act": act}


def _tips_to_sidecar(record, info, st) -> list[dict]:
    """Reflog tips outside the target, merged into the sidecar BEFORE the
    folder goes (`_remove`, `_park`): what the worktree's HEAD reflog alone
    reached is otherwise lost with it."""
    side = _sidecar(record, info["expectation"])
    kept = json.loads(side.read_text(encoding="utf-8"))
    tips = {t["commit"]: t for t in kept.get("reflog_tips") or []}
    for t in reflog_tips(info, st):
        tips.setdefault(t["commit"], t)
    kept["reflog_tips"] = list(tips.values())
    side.write_text(json.dumps(kept, indent=1), encoding="utf-8")
    return kept["reflog_tips"]


def _park(cv, record, info, st, *, why, closed=None) -> dict:
    """Remove the folder only; keep the branch, the sidecar and the record,
    and record `worktree-parked`. The tree is clean and on its branch when
    this is called; `git worktree remove` without --force is the second
    guard, refusing anything uncommitted."""
    repo, where, branch = info["repo"], info["path"], info["branch"]
    tips = _tips_to_sidecar(record, info, st)
    base = {"expectation": info["expectation"], **st, "reflog_tips": tips}
    gone = {"gone": False, "residue_left": None}
    if st["exists"]:
        try:
            gone = _discard_folder(repo, where)
        except RepositoryRefused as exc:
            return _kept(base, closed, info, st,
                         note=f"kept: parking failed, {exc}")
    _git(repo, "worktree", "prune", check=False)
    exp = cv._act(info["expectation"])
    act = cv.record_act(actor="mentis", act=PARKED,
                        conversation=exp["conversation"],
                        caused_by=info["expectation"],
                        about=[info["expectation"]], because=why,
                        detail={"path": where, "branch": branch,
                                "head": st["head"],
                                "commits_beyond_base":
                                    st["commits_beyond_base"],
                                "integration_target":
                                    info.get("integration_target"),
                                "integrated": st["integrated"],
                                "closed": closed,
                                "folder_removed": st["exists"],
                                "residue_left": gone["residue_left"],
                                "why": why, "reflog_tips": tips})
    said = [f"branch {branch} kept at {st['head']}"]
    if st["exists"]:
        said.insert(0, "worktree folder removed" if gone["gone"] else
                    f"worktree folder set aside as {gone['residue_left']}; "
                    f"its deletion stopped ({gone['why']})")
    return {**base, "state": "parked", "act": act, "parked_by": act,
            "residue_left": gone["residue_left"], "said": said}


def park(cv, record, expectation, *, why) -> dict:
    """Park one request's worktree on request (`tools/worktree_cleanup.py`):
    the same act and the same guards as closeout, said in words when it
    cannot be done."""
    if not (why or "").strip():
        raise RepositoryRefused("parking says why")
    with _LOCK, _request_lock(expectation):
        info = recorded(cv, expectation)
        if info is None or info["removed_by"]:
            raise RepositoryRefused(f"{expectation} owns no live worktree")
        foreign = owned(record, info)
        if foreign:
            raise RepositoryRefused(f"not this Brain's worktree: {foreign}")
        if (_HELD[expectation] or expectation in _LENT.values()
                or cv.expectation_state(expectation)["live_execution"]):
            raise RepositoryRefused("a run holds this worktree")
        st = status(info)
        moved = set_aside(info["path"], RESIDUE) if st["residue"] else None
        if not st["exists"]:
            if info["parked_by"]:
                return {"expectation": expectation, **st, "state": "parked",
                        "by": info["parked_by"],
                        "residue_moved_to": moved and moved["path"]}
        elif st["operations"]:
            raise RepositoryRefused("a git operation is in progress in it")
        elif st["dirty"] or st["ignored_kept"]:
            raise RepositoryRefused("it holds uncommitted or ignored files")
        elif st["detached"] or not _on_branch(info["path"], info["branch"]):
            raise RepositoryRefused("its HEAD is not on the request's branch")
        elif _serving(info["path"]):
            raise RepositoryRefused("a server is serving from it")
        if not st["branch_exists"]:
            raise RepositoryRefused("its branch no longer exists")
        out = _park(cv, record, info, st, closed=_closed(cv, expectation),
                    why=why)
        return {**out, "residue_moved_to": moved["path"]} if moved else out


def _outstanding(info, st) -> list[str]:
    """Everything that keeps this worktree, said in words."""
    outstanding = []
    if st["operations"]:
        outstanding.append(
            "unfinished git operation(s): " + ", ".join(
                f"{OPERATIONS.get(m, m)} ({m})" for m in st["operations"]))
    if st["dirty"]:
        outstanding.append(f"{len(st['dirty'])} uncommitted change(s)")
    if any(k.startswith("ui/dist/") for k in st["ignored_kept"] or ()):
        outstanding.append(
            "ui/dist is not shown to be a clean build of a commit this "
            "worktree holds: rebuild it from a clean tree, or delete it")
    if st["ignored_kept"]:
        shown = ", ".join(st["ignored_kept"][:5])
        more = len(st["ignored_kept"]) - 5
        outstanding.append(
            f"{len(st['ignored_kept'])} git-ignored file(s) that are not "
            f"known disposable cache: {shown}"
            + (f" and {more} more" if more > 0 else ""))
    if st["integrated"] is False:
        outstanding.append(_not_in(info, st))
    if st["integrated"] is None:
        outstanding.append("no branch to integrate into was recorded, "
                           "so integration cannot be established")
    return outstanding


def _live_children(cv, expectation) -> list[str]:
    """Children of this request that own a worktree cut from it, or that
    declared one and are not yet given it.

    THE SECOND HALF IS WHAT KEEPS A CHILD CUTTABLE. A child takes its branch
    from this request's LIVE worktree (`_provision`), so a parent whose run
    ended before its child's dispatch reached `ensure` -- or whose child's
    dispatch failed before it -- must not lose its tree, or that child can
    never be given one (found by review).
    """
    history = cv.history()
    alive = [a["caused_by"] for a in history
             if a["act"] == PROVISIONED
             and (a["detail"] or {}).get("parent") == expectation
             and not (recorded(cv, a["caused_by"]) or {}).get("removed_by")]
    declaring = dict.fromkeys(
        a["id"] if a["act"] == "expectation-recorded" else a["caused_by"]
        for a in history
        if a["act"] in ("expectation-recorded", "expectation-assigned")
        and ((a["detail"] or {}).get("repository") or {}) ==
        {"from_parent": expectation})
    pending = [e for e in declaring
               if e not in alive and recorded(cv, e) is None
               and (declared(cv, e) or {}).get("from_parent") == expectation
               and not _closed(cv, e)]
    return alive + pending


def _used_since_provisioned(cv, info) -> bool:
    """Whether a dispatch of the request has got past this worktree since it
    was cut: a run started in it, or the dispatch failed before one could.

    ACROSS PROCESSES, unlike `_HELD`: `python -m mentis.worktrees reconcile`
    runs in its own process and cannot see a dispatch's hold, so a tree no
    dispatch has finished with yet is never taken as finished (found by
    review). A dispatch that failed after cutting it counts as finished
    with it, or that tree would be kept forever (found by re-review).
    In the record's own write order, not by clock: a clock that steps back
    would stamp the run before the tree it ran in.
    """
    used = [a["id"] for a in cv.history(caused_by=info["expectation"])
            if a["act"] in ("execution-started", "delivery-failed")]
    if not used:
        return False
    order = cv._write_order([info["provisioned_by"], *used])
    made = order.get(info["provisioned_by"])
    return made is not None and any(order.get(u, -1) > made for u in used)


def _not_in(info, st) -> str:
    """Which of the branch and the worktree's HEAD is not integrated."""
    target = info["integration_target"]
    wh = st["worktree_head"]
    if st["exists"] and st["head"] and wh != st["head"]:
        return (f"the worktree's HEAD {(wh or 'unreadable')[:10]}"
                f"{' (detached)' if st['detached'] else ''} is not "
                f"{info['branch']} and is not provably in {target}")
    return (f"{st['commits_beyond_base']} commit(s) on {info['branch']} "
            f"not in {target}")


def stop_servers_in(where) -> tuple[list[dict], list[str]]:
    """Stop every Mentis server serving code from this worktree, each only
    after it re-proves its identity. Returns (stopped, why-not lines)."""
    from mentis import servers
    stopped, not_stopped = [], []
    serving = servers.serving_from(str(where))
    if serving is None:
        return [], ["could not establish whether a server is serving from "
                    "this worktree (ports or a Python listener could not be "
                    "read); nothing removed"]
    for who in serving:
        why = servers.stop(who)
        if why:
            not_stopped.append(f"server on :{who['port']} still serving from "
                               f"this worktree: {why}")
        else:
            stopped.append({k: who[k] for k in ("port", "pid", "started_at",
                                                 "commit", "corpus")})
    return stopped, not_stopped


def _remove(cv, record, info, st, *, why, state, force=False) -> dict:
    """Remove, THEN record what was actually done.

    A refused removal -- a locked worktree, a file git will not delete -- is
    not recorded as a removal: the worktree stays recorded and live, is
    reported unresolved every time it is settled, and its request can still
    be continued. The tip is in the act, written before the branch is
    deleted. A crash between removing the tree and writing the act leaves
    the branch and no act; the next settle finishes and records it.

    REFLOG TIPS FIRST. What the worktree's HEAD reflog and the branch's
    reflog reached outside the target goes with them, so it is written to
    the sidecar before anything is removed -- merged with whatever an
    earlier, unfinished attempt already put there -- and from the sidecar
    into the act. A crash anywhere in between loses none of it.
    """
    repo, where, branch = info["repo"], info["path"], info["branch"]
    tips = _tips_to_sidecar(record, info, st)
    kept = {"reflog_tips": tips}
    base = {"expectation": info["expectation"], **st, "reflog_tips": tips}
    stopped = []
    if st["exists"]:
        # A TEST SERVER STILL SERVING FROM THE TREE goes first: removing the
        # files under it leaves a process nobody owns, and on Windows a
        # directory a process stands in is only half deleted.
        stopped, not_stopped = stop_servers_in(where)
        if not_stopped:
            return {**base, "state": "unresolved", "wanted": state,
                    "outstanding": not_stopped, "stopped_servers": stopped,
                    "note": "nothing was removed: a server is still serving "
                            "from this worktree"}
        if stopped and not force:
            # WHAT IT WROTE UNTIL IT STOPPED is part of the tree too: look
            # again before removing anything.
            again = status(info)
            if (again["dirty"] or again["ignored_kept"] or again["operations"]
                    or not again["integrated"]):
                return {**base, **again, "state": "unresolved",
                        "wanted": state, "stopped_servers": stopped,
                        "outstanding": _outstanding(info, again),
                        "note": "its server was stopped; what it left keeps "
                                "the worktree"}
            st = again
            base = {**base, **again}
        # In the safe order (`_discard_folder`): git's own check that the
        # tree is clean (unless abandoned) is a second guard behind the one
        # above; a lock refuses the whole folder with nothing changed.
        try:
            gone = _discard_folder(repo, where, force=force)
        except RepositoryRefused as exc:
            return {**base, "state": "unresolved", "wanted": state,
                    "outstanding": [f"removal failed: {exc}"],
                    "note": "nothing was recorded as removed; it is kept, "
                            "and settled again after the next run"}
    else:
        gone = {"gone": True, "residue_left": None}
    _git(repo, "worktree", "prune", check=False)
    exp = cv._act(info["expectation"])
    act = cv.record_act(actor="mentis", act=REMOVED,
                        conversation=exp["conversation"],
                        caused_by=info["expectation"],
                        about=[info["expectation"]], because=why,
                        detail={"path": where, "branch": branch,
                                "head": st["head"],
                                "worktree_head": st["worktree_head"],
                                "dirty": st["dirty"],
                                "residue_left": gone["residue_left"],
                                # What went with the tree: only known
                                # disposable cache, by folder and reason.
                                "ignored_disposable": st["ignored_disposable"],
                                "ignored_kept": st["ignored_kept"],
                                "integrated": st["integrated"],
                                "integration_target":
                                    info.get("integration_target"),
                                # Only ever non-empty when abandoned: what
                                # --force discarded mid-operation.
                                "operations": st["operations"],
                                "stopped_servers": stopped,
                                "reflog_tips": kept["reflog_tips"]})
    said = [f"stopped server :{s['port']} (pid {s['pid']})" for s in stopped]
    if st["exists"]:
        said.append("worktree removed" if gone["gone"] else
                    f"worktree folder set aside as {gone['residue_left']}; "
                    f"its deletion stopped ({gone['why']})")
    if st["branch_exists"]:
        if _ok(repo, "branch", "-D", branch):
            said.append(f"branch deleted at {st['head']}")
        else:
            said.append(f"branch {branch} could NOT be deleted; it is still "
                        f"at {st['head']}")
    _sidecar(record, info["expectation"]).unlink(missing_ok=True)
    return {**base, "state": state, "act": act, "said": said,
            "residue_left": gone["residue_left"]}


def abandon(cv, record, expectation, *, by, because) -> dict:
    """The owner abandons a request's worktree: explicit permission to
    discard what is in it. Recorded, then applied. Owner-only by where it is
    reachable -- no worker operation calls this."""
    if not (because or "").strip():
        raise RepositoryRefused("abandoning work says why")
    info = recorded(cv, expectation)
    if info is None or info["removed_by"]:
        raise RepositoryRefused(f"{expectation} owns no live worktree")
    foreign = owned(record, info)
    if foreign:
        raise RepositoryRefused(f"not this Brain's worktree: {foreign}")
    exp = cv._act(expectation)
    st = status(info)
    cv.record_act(actor=by, act=ABANDONED, conversation=exp["conversation"],
                  caused_by=expectation, about=[expectation], because=because,
                  detail={"branch": info["branch"], "head": st["head"],
                          "worktree_head": st["worktree_head"],
                          "operations": st["operations"]})
    return settle(cv, record, expectation)


#: ONE RECONCILE AT A TIME, AND NEVER A QUEUE OF THEM. Every run ending asks
#: for one; a pass over a few hundred worktrees takes minutes of git, so a
#: run ending while one is under way only asks that it go round once more.
_RECONCILING = threading.Lock()
_AGAIN = threading.Event()


def reconcile(cv, record) -> dict:
    """Every Mentis-owned worktree, against the record. Run at start and after
    every run ends.

    NEVER HOLDS `_LOCK` ACROSS THE PASS (the owner's slowdown, 2026-10-25). A
    pass settles every recorded worktree -- a `git status --ignored` and more
    for each, measured at 225 s for 280 of them -- and provisioning a new
    request's tree waits on `_LOCK`. Held across the pass, every dispatch
    queued behind every run that ended before it. Now each settle takes
    `_LOCK` for its own tree only, so a dispatch waits for at most one; the
    orphan scan, which must not see a provision between its sidecar and its
    act, still holds it, over the orphans alone.

    COALESCED: a reconcile asked for while one runs returns at once with
    `coalesced` set, and the running one goes round again before it ends,
    so whatever the later run left is still settled.

      settled    each recorded worktree, through `settle`
      orphans    a sidecar the record never recorded -- a crash between the
                 two. Removed if it holds nothing beyond its base; otherwise
                 preserved and reported.
      unmarked   anything else under the root: reported, never touched
    """
    if not _RECONCILING.acquire(blocking=False):
        _AGAIN.set()
        return {"settled": [], "orphans": [], "unmarked": [],
                "unresolved": [], "residue_moved": [], "residues": [],
                "coalesced": True}
    try:
        while True:
            _AGAIN.clear()
            got = _reconcile_once(cv, record)
            if not _AGAIN.is_set():
                return got
    finally:
        _RECONCILING.release()


def _reconcile_once(cv, record) -> dict:
    # Every branch's unrecorded commits first, each under its own request's
    # lock and not `_LOCK` (`_record_outside`).
    through = {a["caused_by"]: _record_outside(cv, record, a["caused_by"])
               for a in cv.history() if a["act"] == PROVISIONED}
    mine = [a for a in cv.history() if a["act"] == PROVISIONED]
    # Children after parents in time, so settle them first: a child's
    # branch is integrated into its parent's, which must still exist.
    mine.sort(key=lambda a: a["at"], reverse=True)
    # Each under `_LOCK` for its own tree only (`_settle`).
    settled = [_settle(cv, record, a["caused_by"],
                       through.get(a["caused_by"], _UNRECORDED))
               for a in mine]
    with _LOCK:
        # Read again under the lock: a request provisioned during the pass
        # has its act by now, and its sidecar is never taken for an orphan.
        known = {a["caused_by"] for a in cv.history()
                 if a["act"] == PROVISIONED}
        orphans, unmarked = [], []
        r = root(record)
        if r.is_dir():
            for side in r.glob("*" + SIDECAR):
                exp = side.name[:-len(SIDECAR)]
                if exp in known:
                    continue
                orphans.append(_orphan(record, side, exp))
            for d in r.iterdir():
                if d.is_dir() and d.name not in known and not (
                        r / (d.name + SIDECAR)).exists() \
                        and not _ASIDE.match(d.name):
                    unmarked.append(str(d))
        return {"settled": settled, "orphans": orphans, "unmarked": unmarked,
                "unresolved": [s for s in settled
                               if s["state"] == "unresolved"],
                # Folders set aside this pass, and every one still under
                # the root (`residues`): reported, never deleted here.
                "residue_moved": [s for s in settled
                                  if s.get("residue_moved_to")],
                "residues": residues(record)}


def _orphan(record, side, expectation) -> dict:
    try:
        info = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"sidecar": str(side), "state": "unreadable", "why": str(exc)}
    if not isinstance(info, dict) or info.get("expectation") != expectation:
        return {"sidecar": str(side), "expectation": expectation,
                "state": "not-this-brains",
                "why": "the sidecar names a different request"}
    foreign = owned(record, info)
    if foreign:
        return {"sidecar": str(side), "expectation": expectation,
                "path": info.get("path"), "state": "not-this-brains",
                "why": foreign}
    st = status(info)
    # Empty means nothing would be lost: no change, nothing ignored, no
    # commit on the branch, and a HEAD that is where the branch (or, with no
    # branch, the base) says.
    moved = st["exists"] and st["worktree_head"] != (
        st["head"] if st["branch_exists"] else info.get("base_commit"))
    empty = (st["dirty"] in ([], None) and not st["ignored_kept"]
             and not st["operations"]
             and not st["commits_beyond_base"] and not moved)
    if not empty:
        return {"expectation": expectation, **st, "state": "preserved",
                "note": "a Mentis worktree the record never recorded holds "
                        "changes; kept for the owner to judge"}
    if st["exists"]:
        _git(info["repo"], "worktree", "remove", info["path"], check=False)
    _git(info["repo"], "worktree", "prune", check=False)
    if st["branch_exists"]:
        _git(info["repo"], "branch", "-D", info["branch"], check=False)
    if pathlib.Path(info["path"]).exists():
        shutil.rmtree(info["path"], ignore_errors=True)
    side.unlink(missing_ok=True)
    return {"expectation": expectation, "state": "removed",
            "why": "provisioned but never recorded, and it held nothing"}


def commit(cv, record, expectation, message, *, by=None) -> dict:
    """Commit everything in this request's worktree on its branch, in the
    owner's process. Says what it did; raises `RepositoryRefused` in words.

    WHY THE OWNER COMMITS. Measured on codex 0.159.2 under its elevated
    `workspace-write` sandbox: a linked worktree's git directory and the
    repository's `.git` are kept read-only even when named as writable roots
    (`index.lock: Permission denied`), so a Codex run could edit and test in
    its worktree but never hand the work back as a branch. The git operations
    already run here (`_provision`, `_remove`), so this is the same process
    doing one more of them -- for every runtime, so the workflow is one.

    ONLY THIS REQUEST'S OWN WORKTREE, and only one that is live, this
    Brain's, and not in the middle of a git operation -- except a merge,
    which it concludes once no conflict is left in it. What `git add -A`
    takes is decided by the repository's own ignore rules. `by` names the
    execution that asked, as a `Mentis-Execution:` trailer on the commit.

    WHY IT DOES NOT TAKE `_LOCK` (measured 2026-10-24). `reconcile` holds
    `_LOCK` across a `status` of every live worktree, after EVERY run ends;
    over the live Brain's 77 trees that `status` alone took 49 s, against
    the worker's 30 s timeout. A commit queued behind it, the worker gave
    up, and the commit then landed with nobody told. It takes only its own
    request's lock, waits for that at most `COMMIT_WAIT_S`, and otherwise
    says it did nothing.

    A RETRY IS SAFE. A commit is recorded as a `worktree-committed` act. A
    call that finds nothing to commit while the branch's tip is this
    execution's own commit answers "already committed at <sha>" -- and
    records that commit if no act of it exists yet, which is the call that
    timed out before it could be told.
    """
    message = (message or "").strip()
    if not message:
        raise RepositoryRefused("a commit says what it is (message)")
    lock = _request_lock(expectation)
    if not lock.acquire(timeout=COMMIT_WAIT_S):
        return {"committed": False, "busy": True,
                "note": (f"NOTHING WAS DONE: this request's worktree was "
                         f"busy for {COMMIT_WAIT_S:g} s (Mentis is settling "
                         "it). Call commit_work again; a retry is safe and "
                         "says so if the work is already committed.")}
    try:
        return _commit(cv, record, expectation, message, by)
    finally:
        lock.release()


def _commit(cv, record, expectation, message, by) -> dict:
    info = recorded(cv, expectation)
    if info is None:
        raise RepositoryRefused(
            "this request owns no repository worktree, so there is "
            "nothing of it to commit")
    if info["removed_by"] or info["abandoned_by"]:
        raise RepositoryRefused(
            f"this request's worktree was "
            f"{'abandoned' if info['abandoned_by'] else 'removed'}; "
            "there is nothing to commit")
    foreign = owned(record, info)
    if foreign:
        raise RepositoryRefused(f"not this Brain's worktree: {foreign}")
    where = info["path"]
    if not pathlib.Path(where).is_dir():
        raise RepositoryRefused(f"{where} is missing")
    busy = operations(where)
    merging = busy == ["MERGE_HEAD"]
    if busy and not merging:
        raise RepositoryRefused(
            "a git operation is in progress in the worktree ("
            + ", ".join(f"{OPERATIONS.get(m, m)} ({m})" for m in busy)
            + "); commit_work concludes only a merge. Finish it with "
            f"`git -C {where} rebase --continue` (or `cherry-pick "
            "--continue`, `revert --continue`, `bisect reset`, as it is), "
            "or abort it, then call commit_work again")
    if _git(where, "symbolic-ref", "-q", "HEAD", check=False) \
            != "refs/heads/" + info["branch"]:
        raise RepositoryRefused(
            f"the worktree is not on {info['branch']}; commit only on "
            "the branch the work is handed back as")
    # A COMMIT NOBODY RECORDED -- the server died between a commit and its
    # act, or the run committed with git itself -- is recorded now, before
    # this call adds one of its own (found by review).
    record_unrecorded(cv, info)
    if merging:
        # A MERGE IS CONCLUDED, NOT REFUSED, once nothing in it is still in
        # conflict -- and only then. Checked BEFORE `git add -A`, which would
        # otherwise settle every conflict left as the working tree has it.
        unresolved = _merge_unresolved(where)
        if unresolved:
            raise RepositoryRefused(
                "a merge is in progress and it is not resolved: "
                + "; ".join(unresolved[:20])
                + ". Resolve each (remove every <<<<<<< ======= >>>>>>> "
                "block; for a binary file or one a side deleted, choose with "
                f"`git -C {where} checkout --ours -- <file>` or `--theirs` "
                "and then `git add <file>`, or `git rm <file>`) and call "
                "commit_work again, which concludes the merge; or abandon it "
                f"with `git -C {where} merge --abort`")
    _git(where, "add", "-A")
    staged = _names(where, "diff", "--cached", "--name-only")
    if not staged and not merging:
        return _already(cv, info, where, by)
    # NO HOOKS AND NO SIGNING. This runs as the owner, unsandboxed, over
    # content a sandboxed run wrote: a hook it could reach (a
    # `core.hooksPath` or a framework reading config from the worktree)
    # would be that run escaping its sandbox (found by review).
    _git(where, "-c", f"core.hooksPath={os.devnull}",
         "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify",
         "-m", message,
         *(["--trailer", f"Mentis-Execution: {by}"] if by else []))
    sha = _git(where, "rev-parse", "HEAD")
    act = _record_commit(cv, info, sha, staged, by, merge=merging)
    return {"committed": True, "branch": info["branch"], "commit": sha,
            "files": staged, "act": act,
            **({"merge": True, "note": "the merge in progress was concluded"}
               if merging else {})}


def _names(where, *args) -> list[str]:
    """Paths git lists, NUL-separated and so never quoted: without `-z` git
    writes `café.txt` as `"caf\\303\\251.txt"`, which names no file (found
    by review: such a file's markers were never read)."""
    out = _git(where, *args, "-z", check=False, strip=False)
    return [p for p in out.split("\0") if p]


#: Git's default conflict-marker-size; a marker line is AT LEAST this long
#: whatever the attribute says, so a file whose size is larger is still
#: caught by a seven-character run, and one whose size is smaller by its own.
_MARKER_SIZE = 7
#: How much of a blob git itself reads to call it binary.
_SNIFF = 8000


def _marker_line(size: int) -> re.Pattern:
    """A marker line: a run of `size` or more -- seven at most -- of `<`,
    `=`, `|` (diff3's base) or `>` opening the line and ending it or
    followed by a blank. The run's character is group 1."""
    n = max(1, min(size, _MARKER_SIZE))
    return re.compile(r"([<=|>])\1{%d,}(?:[ \t]|$)" % (n - 1))


def _hunk(kinds) -> bool:
    """Whether marker kinds (`<`, `=`, `|`, `>`), in file order, make a
    conflict hunk: a start, then LATER a separator (`=`, or diff3's `|`),
    then LATER an end, whatever lies between -- other markers included. A
    lone `=======` -- a Markdown setext underline -- or a lone `>>>>>>>` is
    none: counting each marker line on its own refused a resolved merge
    whose new heading was underlined (found by review).

    AN ORDER, NOT A STATE MACHINE that markers can reset: one that restarted
    on every start and forgot on a stray end let a real hunk whose side held
    `<<<<<<< literal` or `>>>>>>> literal` be committed (found by
    re-review). Once a start is seen it stays seen, and so does a separator
    after it."""
    seen = 0
    for k in kinds:
        if seen == 0 and k == "<":
            seen = 1
        elif seen == 1 and k in "=|":
            seen = 2
        elif seen == 2 and k == ">":
            return True
    return False


def _markers(path: pathlib.Path, size: int = _MARKER_SIZE) -> str | None:
    """Why this file is not resolved, or None. A file that cannot be read is
    NOT resolved: it used to count as removed, which let a merge conclude
    with its markers inside (found by review).

    ANY MARKER LENGTH. `conflict-marker-size=10` makes git write
    `<<<<<<<<<< HEAD`, which a fixed seven-character `<<<<<<< ` never
    matched, and such a merge concluded with its markers (found by review).
    Unresolved means a whole hunk of such lines (`_hunk`)."""
    marker = _marker_line(size)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            kinds = (m.group(1) for m in
                     (marker.match(line.rstrip("\r\n")) for line in fh) if m)
            if _hunk(kinds):
                return "still holds conflict markers"
    except OSError as exc:
        return f"cannot be read to check it ({exc.strerror or exc})"
    return None


def _marker_sizes(where, paths) -> dict[str, int]:
    """Each path's effective `conflict-marker-size`, as git resolves it from
    every attributes file it reads; the default where none is set."""
    if not paths:
        return {}
    out = subprocess.run(["git", "-C", str(where), "check-attr", "-z",
                          "--stdin", "conflict-marker-size"],
                         input="\0".join(paths).encode("utf-8"),
                         capture_output=True)
    sizes = dict.fromkeys(paths, _MARKER_SIZE)
    parts = out.stdout.decode("utf-8", "replace").split("\0")
    for path, _, value in zip(parts[0::3], parts[1::3], parts[2::3]):
        if value.isdigit() and int(value) > 0:
            sizes[path] = int(value)
    return sizes


def _changed(where, parent) -> set[str]:
    """Every path whose index or working-tree content is not `parent`'s,
    renames followed: both the source and the destination of each."""
    paths: set[str] = set()
    for cached in (["--cached"], []):
        recs = _names(where, "diff", *cached, "-M", "--name-status", parent)
        i = 0
        while i < len(recs):
            two = recs[i][:1] in ("R", "C")
            paths.update(recs[i + 1:i + (3 if two else 2)])
            i += 3 if two else 2
    return paths


_LEFTOVER = re.compile(r"^(.+):(\d+): leftover conflict marker$")


def _git_says_markers(where, parent) -> set[str]:
    """The paths `git diff --check` finds a leftover conflict marker in,
    against `parent`. Git's own reading, with each path's own marker size.
    The WORKING TREE's, which is what `git add -A` commits: a staged copy
    since fixed in the tree is not what lands. Run directly: it exits 2 when
    it finds something, which `_git` would read as nothing.

    Only where the lines git flags make a whole hunk (`_hunk`): git flags a
    lone `=======` too. Git names only the line numbers, so each flagged
    line is read from the working tree; a file that cannot be read keeps
    git's word."""
    out = subprocess.run(
        ["git", "-C", str(where), "-c", "core.quotePath=false", "diff",
         "-M", "--check", parent],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    flagged: dict[str, set[int]] = {}
    for m in map(_LEFTOVER.match, out.stdout.splitlines()):
        if m:
            flagged.setdefault(m.group(1), set()).add(int(m.group(2)))
    found = set()
    for path, numbers in flagged.items():
        try:
            with open(pathlib.Path(where, path), "rb") as fh:  # git's lines
                kinds = [line[:1].decode("latin-1")
                         for n, line in enumerate(fh, 1) if n in numbers]
        except OSError:
            found.add(path)
            continue
        if _hunk(kinds):
            found.add(path)
    return found


def _binary(where, sha) -> bool:
    out = subprocess.run(["git", "-C", str(where), "cat-file", "blob", sha],
                         capture_output=True)
    return out.returncode != 0 or b"\0" in out.stdout[:_SNIFF]


def _merge_unresolved(where) -> list[str]:
    """Every file of the merge in progress that is not resolved, each with
    why. Empty when the merge may be concluded.

    EVERYTHING ABOUT TO BE COMMITTED, not only what git still lists as
    unmerged: a file staged with `git add` while it still held its markers
    is no longer unmerged, and its markers were committed (found by review).
    Nor only what the incoming side touched: such a file staged and then
    moved with `git mv` sat at a path neither side had, and its markers were
    committed too (found by re-review). So every path -- in the index, in
    the working tree, or untracked and about to be added -- whose content is
    neither side's, renames followed; a file that is exactly one side's
    holds nothing that side did not already hold. Each is read with its own
    `conflict-marker-size`, and git's `diff --check` is asked as well.

    A CONFLICT GIT COULD NOT MARK -- a binary file, a file one side deleted,
    a symlink or submodule -- has no markers to remove, so `git add -A`
    would settle it as the working tree happens to have it: a resolution
    nobody chose. Refused while git still lists it unmerged; the run
    resolves it explicitly (`checkout --ours/--theirs` and `git add`, or
    `git rm`), and then it is the run's choice.
    """
    unmerged: dict[str, dict[int, tuple[str, str]]] = {}
    for rec in _names(where, "ls-files", "-u"):
        meta, _, path = rec.partition("\t")
        mode, sha, stage = meta.split()
        unmerged.setdefault(path, {})[int(stage)] = (mode, sha)
    unmatched = (_changed(where, "HEAD") & _changed(where, "MERGE_HEAD")) \
        | set(_names(where, "ls-files", "--others", "--exclude-standard"))
    sizes = _marker_sizes(where, sorted(unmatched | set(unmerged)))
    why: dict[str, str] = {}
    for path, stages in unmerged.items():
        if 2 not in stages or 3 not in stages:
            why[path] = ("deleted on one side and changed on the other; "
                         "keep it (`git add`) or delete it (`git rm`)")
        elif any(m in ("120000", "160000") for m, _ in stages.values()):
            why[path] = "a symlink or submodule conflict; choose one side"
        elif any(_binary(where, s) for _, s in stages.values()):
            why[path] = "a binary conflict, which has no markers; choose one side"
        elif not os.path.lexists(pathlib.Path(where, path)):
            why[path] = ("in conflict and missing from the working tree; "
                         "`git rm` it if deleting it is the resolution")
        else:
            said = _markers(pathlib.Path(where, path), sizes[path])
            if said:
                why[path] = said
    for path in sorted(unmatched - set(unmerged)):
        p = pathlib.Path(where, path)
        if os.path.lexists(p):
            said = _markers(p, sizes[path])
            if said:
                why[path] = said
    for path in (_git_says_markers(where, "HEAD")
                 & _git_says_markers(where, "MERGE_HEAD")) - set(why):
        why[path] = "git reports leftover conflict markers in it"
    return [f"{p} ({w})" for p, w in sorted(why.items())]


def _already(cv, info, where, by) -> dict:
    """Nothing to commit. Said as "already committed" when the branch's tip
    is this execution's own commit -- a retry of a call that committed and
    timed out -- and recorded then if it never was."""
    head = _git(where, "rev-parse", "HEAD")
    out = {"committed": False, "branch": info["branch"], "head": head}
    tip_by = _git(where, "log", "-1",
                  "--format=%(trailers:key=Mentis-Execution,valueonly)",
                  check=False).strip()
    beyond = _ok(where, "merge-base", "--is-ancestor", info["base_commit"],
                 head) and head != info["base_commit"]
    if by and beyond and tip_by == by:
        act = _record_commit(cv, info, head, _files(where, head), by,
                             merge=bool(_git(where, "rev-parse", "-q",
                                             "--verify", "HEAD^2",
                                             check=False)))
        return {**out, "committed": True, "already": True, "commit": head,
                "act": act,
                "note": f"already committed at {head}: the worktree has no "
                        "further changes, and the branch's tip is this "
                        "execution's commit"}
    return {**out, "note": "nothing to commit: the worktree has no changes"}


def _files(where, sha) -> list[str]:
    return _names(where, "diff-tree", "--no-commit-id", "--name-only", "-r",
                  "-m", "--first-parent", sha)


def _record_commit(cv, info, sha, files, by, *, merge, extra=None,
                   because="the request's run committed its work") -> str:
    """The `worktree-committed` act for this commit: the existing one when
    it was recorded already, so a retry never writes a second."""
    exp = info["expectation"]
    for a in cv.history(caused_by=exp):
        if a["act"] == COMMITTED and (a["detail"] or {}).get("commit") == sha:
            return a["id"]
    return cv.record_act(actor="mentis", act=COMMITTED,
                         conversation=cv._act(exp)["conversation"],
                         caused_by=exp, about=[exp], because=because,
                         detail={"commit": sha, "branch": info["branch"],
                                 "files": files, "by": by, "merge": merge,
                                 **(extra or {})})


def record_unrecorded(cv, info) -> list[str]:
    """Record every commit on the request's branch that has no
    `worktree-committed` act yet, oldest first. Returns the acts written.

    WITHOUT IT A COMMIT COULD BE LOST TO THE RECORD FOR GOOD: the server
    dying between a commit and its act left only a retry to notice, and a
    run that never retried -- or committed with git itself -- was never
    recorded (found by review). Run by the next `commit` and by every
    `settle`, so `reconcile` catches whatever no retry did.

    THE BRANCH'S OWN COMMITS: its first-parent line since the base, so
    commits a merge brought in from elsewhere are not taken as this
    request's. WHO MADE ONE: its `Mentis-Execution:` trailer, else the run
    of this request that had last started when it was committed (its
    session), else nobody named -- said as such, never guessed further.
    """
    repo, branch = info["repo"], info["branch"]
    base = info.get("base_commit")
    if not base or not _ok(repo, "show-ref", "--verify", "--quiet",
                           "refs/heads/" + branch):
        return []
    log = _git(repo, "log", "--first-parent", "-z",
               "--format=%H%x1f%ct%x1f%P%x1f"
               "%(trailers:key=Mentis-Execution,valueonly)",
               f"{base}..refs/heads/{branch}", check=False, strip=False)
    commits = [rec.split("\x1f") for rec in log.split("\0") if rec.strip()]
    if not commits:
        return []
    exp = info["expectation"]
    history = cv.history(caused_by=exp)
    known = {(a["detail"] or {}).get("commit") for a in history
             if a["act"] == COMMITTED}
    starts = sorted((a for a in history if a["act"] == "execution-started"
                     and a.get("execution")), key=lambda a: a["at"])
    written = []
    for sha, ct, parents, trailer in reversed(commits):
        sha = sha.strip()
        if sha in known:
            continue
        by = trailer.strip().splitlines()[-1].strip() if trailer.strip() \
            else None
        how = "trailer" if by else None
        if not by:
            # One clock-second of slack: git stamps whole seconds.
            ran = [s for s in starts if s["at"] <= int(ct) + 1]
            if ran:
                s = ran[-1]
                by = (f"{s['runtime']}/{s['execution'][:8]}"
                      if s.get("runtime") else s["execution"])
                how = "session"
        written.append(_record_commit(
            cv, info, sha, _files(repo, sha), by,
            merge=len(parents.split()) > 1,
            extra={"recorded_after": True, "attributed_by": how}))
    return written


def for_child(cv, expectation) -> str | None:
    """One line for a resumed parent about a child's branch, or None."""
    info = recorded(cv, expectation)
    if info is None:
        return None
    if info["removed_by"]:
        return f"its worktree was removed ({info['removed_by']})"
    st = status(info)
    return (f"branch {info['branch']} at {st['head'] and st['head'][:10]}, "
            f"{st['commits_beyond_base']} commit(s) beyond your branch"
            f"{', UNCOMMITTED changes left in its worktree' if st['dirty'] else ''}"
            f"; integrated: {st['integrated']}. Inspect and merge it into "
            f"your branch to take its changes.")


def note(info: dict) -> str:
    """What a run of the owning request is told, as facts."""
    if info.get("lent_from"):
        return (f"This review reads the repository worktree of the request "
                f"it reviews, {info['lent_from']}: {info['path']} on branch "
                f"{info['branch']}"
                + (f" at {info['head'][:10]}" if info.get("head") else "")
                + ". It is THAT request's worktree, lent to you to read and "
                "test while no run of it is working there. Do not change, "
                "commit or clean anything in it: this review owns no "
                "worktree, so `commit_work` is refused, and changes left "
                "there would be mistaken for the reviewed work. Report what "
                "you find; repairs are the reviewed request's to make.")
    return (f"This request owns the repository worktree {info['path']} on "
            f"branch {info['branch']}, cut from {info['base']} at "
            f"{info['base_commit'][:10]}"
            + (f", and its work integrates into {info['integration_target']}"
               if info.get("integration_target") else "")
            + ". It is this request's alone and is "
            "reused by every run of it. Edit and test there, then commit with "
            "the Mentis `commit_work` operation, which commits everything in "
            "the worktree on that branch: the branch is how your changes are "
            "handed back, and uncommitted changes keep the worktree from "
            "being cleaned up. Once the branch is integrated, Mentis removes "
            "the worktree.")


def _main(argv) -> int:
    """`python -m mentis.worktrees reconcile <corpus>`
    `python -m mentis.worktrees abandon <corpus> <expectation> --by <p>
        --because <why>`
    """
    import mentis.api as api
    if len(argv) < 2 or argv[0] not in ("reconcile", "abandon"):
        print(_main.__doc__)
        return 2
    corpus = api.open_corpus(argv[1], access="write")
    cv = api.brain(corpus).conversations
    if argv[0] == "reconcile":
        out = reconcile(cv, argv[1])
    else:
        opts = dict(zip(argv[3::2], argv[4::2]))
        if len(argv) < 3 or not opts.get("--by") or not opts.get("--because"):
            print(_main.__doc__)
            return 2
        out = abandon(cv, argv[1], argv[2], by=opts["--by"],
                      because=opts["--because"])
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
