"""Where a piece of work STANDS: building, awaiting review, needing the owner's
decision, ready to deploy, deployed, blocked -- or answered, with nothing
produced. Owner's requirement: "an execution ending is not completion".

DERIVED, NEVER STORED. Every stage is read from what the record already
holds about the trunk and everything under it, and from git:

    produced work   `worktree-committed` acts in the trunk's tree (a review
                    child's own commits excluded). Each branch's newest
                    commit -- the trunk's and every child's -- is open
                    unless the trunk's branch (or another open branch)
                    already holds it. An open tip committed before the
                    newest one already in the target is SUPERSEDED (a
                    competing branch that lost) and set aside. Merged and
                    deployed need every other open tip contained; a PASS
                    must cover each. The HEAD is the newest of them.
    reviews         a delegated child whose Persona's name says "review"
                    (`dispatch.review_signal`'s rule), or whose brief or
                    `because` opens as a review ("Review ...", "Re-review
                    ...", "Independent check ..."): most reviews here were
                    delegated without a Persona. The commit it reviewed is
                    its worktree's `base_commit`; without a worktree, the
                    head recorded when it was delegated.
    verdict         a `review-verdict` act (REVIEW_VERDICT, detail
                    `{verdict: pass|block|incomplete, commit, lacks?}`) when
                    one is recorded -- `stage_source: "recorded"`; otherwise
                    the review's returned answer read for a leading PASS /
                    BLOCK / FAIL / "Review incomplete" / "could not run" /
                    "Blocked" -- `stage_source: "computed-from-prose"`.
    merged          the head is an ancestor of the integration target's tip
                    (the trunk's worktree `integration_target`, else "main").
    deployed        the head is an ancestor of the commit this server runs
                    (`/api/server` `code.commit`, `web.identity._START`).

FIRST MATCH WINS, in STAGES order: blocked, awaiting_owner, building,
not_started, then -- where work was produced -- deployed, ready_to_deploy,
awaiting_review; where none was, ended ("Answered"). Deployed is checked
before review: a head the server runs IS deployed, and if no PASS covers it
the words say "not reviewed" rather than pretending it waits.

GIT IS ASKED AS LITTLE AS POSSIBLE. Branch tips are read from the
repository's ref files (`read_ref`, `refs_digest`), never by a process.
Containment comes from ONE `git rev-list --all --parents` per repository
(`graph`), held until a branch tip moves, so it is a bit test however many
requests a read projects; only a commit no ref reaches is listed on its own
(`ancestors`, memoised by sha, failures for FAILED_TTL_S). A warm read starts
no git process at all. Where git cannot be asked, the stage is `unknown` and
says why: nothing is guessed.

A SHARED ANSWER'S VERSION (`answer_version`) follows every branch tip of
every repository stage derivation has read, the commit this server runs, and
the resumption grace, since each changes a stage without the record moving.
"""

from __future__ import annotations

import collections
import re
import subprocess
import threading

#: The act a review records its verdict as. Package B's tool writes it;
#: detail `{verdict: "pass"|"block"|"incomplete", commit, lacks?: [...]}`.
REVIEW_VERDICT = "review-verdict"
VERDICTS = ("pass", "block", "incomplete")

COMMITTED = "worktree-committed"
PROVISIONED = "worktree-provisioned"
#: Where the trunk's own worktree stands is a STORAGE fact, said in the
#: evidence (`stage_evidence.worktree`), never a stage: parked work that was
#: returned and not merged still reads "Awaiting review" / "Ready to deploy".
REATTACHED, REMOVED, PARKED = ("worktree-reattached", "worktree-removed",
                               "worktree-parked")
_WORKTREE_ACTS = (PROVISIONED, REATTACHED, REMOVED, PARKED)
STARTED, RETURNED, FAILED, RECOVERED = (
    "execution-started", "result-returned", "delivery-failed",
    "result-recovered")

#: Every stage, in the order the rules try them (and the Ledger lists them).
STAGES = ("blocked", "awaiting_owner", "building", "awaiting_review",
          "parked", "ready_to_deploy", "deployed", "ended", "not_started",
          "unknown")
#: The leading words for each stage, as the owner reads them.
WORDS = {"blocked": "Blocked", "awaiting_owner": "Needs your decision",
         "building": "Building", "awaiting_review": "Awaiting review",
         # WORK WAS PRODUCED AND NOBODY HAS IT: no run, no review pending,
         # no PASS covering it. "Awaiting review" used to say this too, and
         # read as if a reviewer were coming (owner, 2026-10-26). A review
         # delegated and not yet run still reads "Awaiting review".
         "parked": "Parked",
         "ready_to_deploy": "Ready to deploy", "deployed": "Deployed",
         "ended": "Answered", "not_started": "Not started",
         "unknown": "Unknown"}
#: The owner chose to leave a request where it stopped (`dispatch.WORK_PARKED`).
WORK_PARKED = "work-parked"

#: How many ancestor sets are kept (each is one repository's history).
MEMO_MAX = 128
GIT_TIMEOUT_S = 20
_RUNNING = ("running", "continuing")
_STALLED = ("not-resumed", "resumable-not-resumed")
_NOT_STARTED = ("owed", "unassigned", "resumed-no-run")
_ENDED = ("returned", "recovered", "replied")
_LIVE_RUN = ("tool-running", "model-outstanding", "helper-outstanding")


# -- git ---------------------------------------------------------------------

_ANCESTORS: "collections.OrderedDict[tuple, frozenset]" = \
    collections.OrderedDict()
_MEMO_LOCK = threading.Lock()
#: (repository, sha) git could not list, and when: asked again only after
#: FAILED_TTL_S.
_FAILED: dict = {}
FAILED_TTL_S = 600.0


def _git(repo, *args) -> tuple[str | None, str | None]:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args],
                             capture_output=True, text=True,
                             timeout=GIT_TIMEOUT_S)
    except Exception as exc:                              # noqa: BLE001
        return None, f"git could not be asked: {type(exc).__name__}: {exc}"
    if out.returncode != 0:
        return None, ((out.stderr or out.stdout).strip().splitlines()
                      or ["git failed"])[0]
    return out.stdout, None


_SHA = re.compile(r"^[0-9a-f]{40}$")


def _git_dirs(repo) -> tuple | None:
    """(this checkout's git dir, the common git dir), read from disk: a
    worktree's `.git` is a file naming its git dir, which names the common
    one in `commondir`."""
    import pathlib
    dot = pathlib.Path(repo) / ".git"
    try:
        if dot.is_dir():
            return dot, dot
        line = dot.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    own = pathlib.Path(line[len("gitdir:"):].strip())
    if not own.is_absolute():
        own = (pathlib.Path(repo) / own).resolve()
    try:
        common = (own / (own / "commondir").read_text(
            encoding="utf-8").strip()).resolve()
    except OSError:
        common = own
    return own, common


def read_ref(repo, ref) -> str | None:
    """The sha a branch points at, READ FROM THE REPOSITORY'S FILES -- a loose
    ref, else `packed-refs` -- with no process started (on this machine a
    git process costs about half a second). None when it cannot be read that
    way, and the caller asks git."""
    if _SHA.match(ref or ""):
        return ref
    dirs = _git_dirs(repo)
    if dirs is None:
        return None
    name = ref if ref.startswith("refs/") else "refs/heads/" + ref
    for d in dict.fromkeys(dirs):
        try:
            got = (d / name).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        return got if _SHA.match(got) else None
    try:
        packed = (dirs[1] / "packed-refs").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in packed.splitlines():
        bits = line.split(" ", 1)
        if len(bits) == 2 and bits[1].strip() == name and _SHA.match(bits[0]):
            return bits[0]
    return None


def ancestors(repo, sha) -> tuple[frozenset | None, str | None]:
    """Every commit reachable from `sha` (itself included), memoised by
    (repository, sha): a commit's ancestry never changes."""
    import time
    key = (str(repo), sha)
    with _MEMO_LOCK:
        if key in _ANCESTORS:
            _ANCESTORS.move_to_end(key)
            return _ANCESTORS[key], None
        failed = _FAILED.get(key)
        if failed is not None and time.monotonic() - failed[0] < FAILED_TTL_S:
            return None, failed[1]
    out, why = _git(repo, "rev-list", sha)
    if out is None:
        # A COMMIT GIT DOES NOT HOLD (its branch deleted and collected) is
        # asked again only after FAILED_TTL_S, not on every read.
        with _MEMO_LOCK:
            _FAILED[key] = (time.monotonic(), why)
            while len(_FAILED) > 4 * MEMO_MAX:
                _FAILED.pop(next(iter(_FAILED)))
        return None, why
    got = frozenset(out.split())
    with _MEMO_LOCK:
        _ANCESTORS[key] = got
        while len(_ANCESTORS) > MEMO_MAX:
            _ANCESTORS.popitem(last=False)
    return got, None


#: Above this many commits the whole graph is not held (`graph`); each
#: ancestor set is then listed on its own (`ancestors`).
GRAPH_MAX = 50_000
#: How many repositories' graphs are held at once.
GRAPHS_HELD = 8
_GRAPHS: dict = {}


def graph(repo) -> tuple | None:
    """EVERY COMMIT ANY REF REACHES, with each one's ancestors as a bitmask:
    `(refs digest, {sha: index}, [ancestor bits])`, from ONE
    `git rev-list --all --parents`, rebuilt only when a branch tip moves
    (`refs_digest`). Containment of any two such commits is then one bit
    test, however many requests a read projects. None when it cannot be
    read, or the repository is larger than GRAPH_MAX."""
    digest = refs_digest(repo)
    if digest is None:
        return None
    key = str(repo)
    with _MEMO_LOCK:
        got = _GRAPHS.get(key)
    if got is not None and got[0] == digest:
        # (digest, None, None) remembers that this state has no graph
        return got if got[1] is not None else None
    out, _ = _git(repo, "rev-list", "--all", "--parents", "--topo-order",
                  "--reverse")
    lines = out.splitlines() if out is not None else None
    if lines is None or len(lines) > GRAPH_MAX:
        # NO GRAPH FOR THIS STATE, remembered until a branch tip moves, so a
        # warm read does not list the whole repository again
        with _MEMO_LOCK:
            _GRAPHS[key] = (digest, None, None)
            while len(_GRAPHS) > GRAPHS_HELD:
                _GRAPHS.pop(next(iter(_GRAPHS)))
        return None
    index, bits = {}, []
    for line in lines:
        shas = line.split()
        if not shas:
            continue
        m = 1 << len(bits)
        for parent in shas[1:]:
            j = index.get(parent)
            if j is not None:
                m |= bits[j]
        index[shas[0]] = len(bits)
        bits.append(m)
    got = (digest, index, bits)
    with _MEMO_LOCK:
        _GRAPHS[key] = got
        while len(_GRAPHS) > GRAPHS_HELD:
            _GRAPHS.pop(next(iter(_GRAPHS)))
    return got


def forget() -> None:
    """Drop every memoised ancestor set and version (tests)."""
    with _MEMO_LOCK:
        _ANCESTORS.clear()
        _FAILED.clear()
        _GRAPHS.clear()
    _VERSIONS.clear()
    _ANSWER.clear()


def deployed_commit() -> tuple[str | None, str | None]:
    """The commit this server runs, as `/api/server` reports it."""
    try:
        from mentis.web import identity
        code = identity._START["code"]
    except Exception as exc:                              # noqa: BLE001
        return None, f"what this server runs could not be read: {exc}"
    return code.get("commit"), (None if code.get("commit") else
                                code.get("commit_why_not")
                                or "this server did not record its commit")


#: How long `git_version` reuses its answer (s).
VERSION_TTL_S = 5.0
_VERSIONS: dict = {}


def git_version(repo=None, ref="main") -> str | None:
    """WHAT GIT SAYS THAT THE RECORD DOES NOT, as one cheap string, for a
    cached answer's version: the sha `ref` points at in `repo` (default:
    the repository this server runs from) and the commit this server runs.
    A merge or a deploy changes it without the record moving. Read from the
    ref files (`read_ref`), else one `git rev-parse`; reused for
    VERSION_TTL_S; None when git cannot say."""
    import time
    if repo is None:
        try:
            from mentis.web import identity
            repo = identity.REPO
        except Exception:                                 # noqa: BLE001
            return None
    key = (str(repo), ref)
    now = time.monotonic()
    got = _VERSIONS.get(key)
    if got is not None and now - got[0] < VERSION_TTL_S:
        return got[1]
    out = read_ref(repo, ref)
    if out is None:
        out, _ = _git(repo, "rev-parse", "--verify", "--quiet",
                      f"{ref}^{{commit}}")
    dep, _ = deployed_commit()
    value = None if not out else f"{out.strip()}:{dep or '-'}"
    _VERSIONS[key] = (now, value)
    return value


class _GitUnknown(Exception):
    pass


#: Every repository stage derivation has read, most recent last, so a shared
#: answer's version (`answer_version`) follows each of them.
_SEEN_REPOS: dict = {}
SEEN_MAX = 32
#: How long `answer_version` reuses its answer (s).
ANSWER_TTL_S = 2.0
_ANSWER: dict = {}


def _seen(repo) -> None:
    key = str(repo)
    _SEEN_REPOS.pop(key, None)
    _SEEN_REPOS[key] = True
    while len(_SEEN_REPOS) > SEEN_MAX:
        _SEEN_REPOS.pop(next(iter(_SEEN_REPOS)))


def refs_digest(repo) -> str | None:
    """A digest of every branch tip of a repository, READ FROM ITS FILES:
    each loose ref under refs/heads, and packed-refs. Any branch moving
    changes it. None when the repository's git dir cannot be read."""
    import hashlib
    import os
    dirs = _git_dirs(repo)
    if dirs is None:
        return None
    common = dirs[1]
    h = hashlib.sha1()
    heads = common / "refs" / "heads"
    for root, subdirs, files in os.walk(heads):
        subdirs.sort()
        for f in sorted(files):
            path = os.path.join(root, f)
            try:
                with open(path, "rb") as fh:
                    body = fh.read(100)
            except OSError:
                continue
            h.update(os.path.relpath(path, heads).encode() + b"\0" + body)
    try:
        h.update(b"packed\0" + (common / "packed-refs").read_bytes())
    except OSError:
        pass
    return h.hexdigest()[:20]


def answer_version(st) -> str:
    """WHAT A SHARED ANSWER OF /api/work DEPENDS ON THAT THE RECORD DOES NOT:
    every branch tip of the server's configured repository and of every
    repository stage derivation has read (`refs_digest`), and the commit
    this server runs. A merge into any branch, or a commit on a child's
    branch, changes it without the record moving. Read from ref files, no
    git process; reused for ANSWER_TTL_S. It also moves once per
    RESUME_GRACE_S. "-" for the git part only when none of it can be read,
    so caching still works on the record's own count."""
    import time
    repos = list(dict.fromkeys(
        ([str(st.repository)] if getattr(st, "repository", None) else [])
        + list(_SEEN_REPOS)))
    key = tuple(repos)
    now = time.monotonic()
    got = _ANSWER.get(key)
    if got is not None and now - got[0] < ANSWER_TTL_S:
        value = got[1]
    else:
        parts = [refs_digest(r) for r in repos]
        value = "|".join(x or "?" for x in parts) if any(parts) else None
        _ANSWER.clear()
        _ANSWER[key] = (now, value)
    dep, _ = deployed_commit()
    # A RESUMPTION'S GRACE RUNS OUT WITHOUT THE RECORD MOVING (Building
    # becomes Blocked): the version moves at least once per grace period.
    period = int(time.time() // max(RESUME_GRACE_S, 1.0))
    if value is None and not dep:
        return f"-:{period}"
    return f"{value or '-'}:{dep or '-'}:{period}"


class Git:
    """One overview read's questions of git: each integration target is
    resolved once per read; ancestry comes from the module memo."""

    def __init__(self, deployed=None):
        self._tips, self._deployed, self._graphs = {}, deployed, {}

    def deployed(self) -> tuple[str | None, str | None]:
        if self._deployed is None:
            self._deployed = deployed_commit()
        return self._deployed

    def tip(self, repo, ref) -> tuple[str | None, str | None]:
        key = (str(repo), ref)
        if key not in self._tips and read_ref(repo, ref):
            self._tips[key] = read_ref(repo, ref), None
        if key not in self._tips:
            out, why = _git(repo, "rev-parse", "--verify", "--quiet",
                            f"{ref}^{{commit}}")
            self._tips[key] = ((out.strip(), None) if out else
                               (None, why or f"{ref} does not resolve in "
                                             f"{repo}"))
        return self._tips[key]

    def contains(self, repo, tip, commit) -> tuple[bool | None, str | None]:
        if not tip:
            return None, "no commit to look in"
        key = str(repo)
        if key not in self._graphs:
            self._graphs[key] = graph(repo)
        gr = self._graphs[key]
        if gr is not None and tip in gr[1]:
            # every ancestor of a commit some ref reaches is in the graph:
            # a commit the graph does not hold is not one of them
            i = gr[1].get(commit)
            return (i is not None and bool(gr[2][gr[1][tip]] >> i & 1)), None
        got, why = ancestors(repo, tip)
        if got is None:
            return None, why
        return commit in got, None


# -- reading the record ------------------------------------------------------

_REVIEW_BRIEF = re.compile(
    r"^(?:@\S+[\s,:]+)*(?:(?:please|now|then|next|do|an?|the|code|second|"
    r"final|fresh|full|independent(?:ly)?)\s+)*"
    r"(?:re-?review|review(?:er)?\b|independent\s+check)", re.I)
_REVIEW_ANYWHERE = re.compile(r"\bre-review\b|\bindependent check\b", re.I)


def is_review(brief, because, persona_name) -> bool:
    """A review: by its Persona's name, or by what it was asked to do."""
    if persona_name and "review" in persona_name.lower():
        return True
    for text in (brief, because):
        line = _first_line(text)
        if line and (_REVIEW_BRIEF.search(line)
                     or _REVIEW_ANYWHERE.search(line)):
            return True
    return False


_MARKS = re.compile(r"[*_`#>]+")


def _first_line(text) -> str | None:
    for line in str(text or "")[:2000].splitlines():
        line = _MARKS.sub("", line).strip()
        if line:
            return line
    return None


_VERDICT = re.compile(
    r"^\W*(?:(?:overall\s+|final\s+|review\s+)?verdict\s*(?:is\s*)?[:\-–—]?\s*)?"
    r"(?P<v>pass(?:ed)?|block(?:ed|ing)?|fail(?:ed|s)?|review\s+incomplete|"
    r"incomplete|could\s*n[o']?t\s+(?:run|complete|finish)|"
    r"could\s+not\s+(?:run|complete|finish)|unable\s+to\s+(?:run|review))\b",
    re.I)
_VERDICT_LINE = re.compile(
    r"\bverdict\s*(?:is\s*)?[:\-–—]\s*(?P<v>pass|block|fail|incomplete)\b",
    re.I)


def verdict_of(text) -> str | None:
    """A review's verdict from its answer's own words, or None: the first
    few lines are read for a leading verdict word, or a "Verdict:" line."""
    lines = []
    for ln in str(text or "")[:4000].splitlines():
        ln = _MARKS.sub("", ln).strip()
        if ln:
            lines.append(ln)
            if len(lines) == 12:
                break
    for i, line in enumerate(lines):
        m = _VERDICT.match(line) if i < 3 else None
        m = m or _VERDICT_LINE.search(line)
        if not m:
            continue
        v = m.group("v").lower()
        if v.startswith("pass"):
            return "pass"
        if v.startswith(("block", "fail")) and v != "blocked":
            return "block"
        return "incomplete"
    return None


def _clip(text, n=90) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _persona_name(ctx, persona) -> str | None:
    if not persona:
        return None
    names = ctx.__dict__.setdefault("_persona_names", {})
    if persona not in names:
        try:
            got = ctx.cv.corpus.read([persona])
            names[persona] = (str((got[0].get("body") or {}).get("name")
                                  or "") if got else None)
        except Exception:                                 # noqa: BLE001
            names[persona] = None
    return names[persona]


def _git_of(ctx) -> Git:
    g = getattr(ctx, "stage_git", None)
    if g is None:
        g = ctx.stage_git = Git()
    return g


def _result(stage, words, source, evidence) -> dict:
    return {"stage": stage, "stage_words": words, "stage_source": source,
            "stage_evidence": evidence}


def _evidence(**kw) -> dict:
    out = {"head": None, "merged": None, "deployed_commit": None,
           "review": None, "blocked": None, "worktree": None}
    out.update(kw)
    return out


def worktree_of(everything, trunk, key) -> str | None:
    """Where the trunk's own worktree stands, by the record's latest word
    about it: "attached" (provisioned or attached again), "parked" (folder
    removed, branch kept at closeout), "removed"; None when it never had
    one."""
    acts = sorted((a for a in everything if a.get("caused_by") == trunk
                   and a["act"] in _WORKTREE_ACTS), key=key)
    if not acts:
        return None
    last = acts[-1]["act"]
    return {PARKED: "parked", REMOVED: "removed"}.get(last, "attached")


def unknown(why) -> dict:
    return _result("unknown", "Unknown — " + _clip(why or "the record "
                                                    "cannot say", 80),
                   "unknown", _evidence(why=why))


#: How long a resumption that has not started a run yet reads as Building
#: (it is being dispatched) before it reads as Blocked.
RESUME_GRACE_S = 120.0


def _not_started(v, everything=()) -> dict:
    """NOTHING HAS RUN FOR IT. Resumed with nothing run since is not that:
    work happened under it and its carrier was asked to go on. Just resumed,
    it is being dispatched -- Building; resumed longer ago than
    RESUME_GRACE_S with still nothing run, it is blocked, said so."""
    if v == "resumed-no-run":
        import time
        resumed = [a for a in everything if a["act"] == "work-resumed"]
        newest = max((a.get("at") or 0 for a in resumed), default=None)
        if newest is not None and time.time() - newest < RESUME_GRACE_S:
            return _result("building", WORDS["building"] + " · resuming",
                           "computed", _evidence())
        why = "it was resumed and nothing has run since"
        return _result("blocked", "Blocked: " + why, "computed",
                       _evidence(blocked={"why": why, "act": None}))
    return _result("not_started", WORDS["not_started"]
                   + (" · unassigned" if v == "unassigned" else ""),
                   "computed", _evidence())


def _parked_by_owner(everything, trunk, key):
    """The newest `work-parked` act on this trunk, or None."""
    acts = [a for a in everything if a["act"] == WORK_PARKED
            and a.get("caused_by") == trunk]
    return max(acts, key=key) if acts else None


def _plain(state, v, owed_n, met, seen, awaits, everything, key,
           trunk=None) -> dict:
    """NOTHING DELEGATED AND NOTHING COMMITTED: the same rules as
    `stage_of`, with no reviews, no children and no git to ask."""
    parked = _parked_by_owner(everything, trunk, key) if trunk else None
    newest_start = max((a for a in everything if a["act"] == STARTED),
                       key=key, default=None)
    if parked and not (newest_start and key(newest_start) > key(parked)):
        return _result("parked", "Parked · by your decision, where it stopped",
                       "computed", _evidence(blocked={
                           "why": "the owner chose to park it",
                           "act": parked["id"]}))
    if v == "failed" and owed_n:
        return _result("awaiting_owner", WORDS["awaiting_owner"]
                       + (f" · {owed_n} open" if owed_n > 1 else "")
                       + " · its last run failed", "computed", _evidence())
    if v == "failed":
        fails = sorted((a for a in everything if a["act"] == FAILED), key=key)
        f = fails[-1] if fails else None
        why = "the last run failed" + (
            f" — {_clip(f.get('because'), 70)}" if f and f.get("because")
            else "")
        return _result("blocked", "Blocked: " + _clip(why, 90), "computed",
                       _evidence(blocked={"why": why,
                                          "act": f["id"] if f else None}))
    if v in _STALLED or (v == "waiting-on-work"
                         and awaits in ("ended", "stalled")):
        why = (state.get("label") or "it will not resume by itself"
               if v in _STALLED else "waiting on other work that is not "
                                     "moving")
        return _result("blocked", "Blocked: " + _clip(why, 90), "computed",
                       _evidence(blocked={"why": why, "act": None}))
    if owed_n:
        return _result("awaiting_owner", WORDS["awaiting_owner"]
                       + (f" · {owed_n} open" if owed_n > 1 else ""),
                       "computed", _evidence())
    if (v in _RUNNING or (v == "started-no-end" and seen == "live")
            or (v == "waiting-on-work" and awaits == "moving")
            or v == "waiting-on-decision"):
        words = WORDS["building"] + (" · waiting on a decision"
                                     if v == "waiting-on-decision" else "")
        return _result("building", words, "computed", _evidence())
    if v in _NOT_STARTED:
        return _not_started(v, everything)
    if met:
        return _result("ended", "Answered · objective met", "computed",
                       _evidence())
    if v in _ENDED or v in ("waiting-on-child", "claimed-met"):
        return _result("ended", WORDS["ended"] + " · nothing committed",
                       "computed", _evidence())
    return unknown(f"no stage rule covers its state {v!r}")


def stage_of(ctx, act, *, state, everything, children, execs, owed_n,
             met, seen=None, awaits=None) -> dict:
    """The stage of one trunk: `{stage, stage_words, stage_source,
    stage_evidence}`. See the module docstring for every rule. The
    evidence also says where the trunk's worktree is (`worktree_of`)."""
    out = _stage_of(ctx, act, state=state, everything=everything,
                    children=children, execs=execs, owed_n=owed_n, met=met,
                    seen=seen, awaits=awaits)
    out["stage_evidence"]["worktree"] = worktree_of(everything, act["id"],
                                                    ctx.order.key)
    return out


def _stage_of(ctx, act, *, state, everything, children, execs, owed_n,
              met, seen=None, awaits=None) -> dict:
    v = state.get("value")
    if state.get("source") == "unknown" or seen == "unknown" \
            or awaits == "unknown":
        return unknown(state.get("why") or "the work's state is unknown")
    key = ctx.order.key
    trunk = act["id"]
    if not children and not any(a["act"] in (COMMITTED, REVIEW_VERDICT)
                                for a in everything):
        return _plain(state, v, owed_n, met, seen, awaits, everything, key,
                      trunk=trunk)

    # -- the tree: delegations, children, runs ------------------------------
    deleg = {a["about"][0]: a for a in everything
             if a["act"] == "work-delegated" and a.get("about")}
    child_ids = {c["id"] for c in children}
    starts_of = collections.defaultdict(list)
    for a in everything:
        if a["act"] == STARTED and a.get("caused_by"):
            starts_of[a["caused_by"]].append(a)
    start_owner = {s["id"]: e for e, ss in starts_of.items() for s in ss}
    ends_of = collections.defaultdict(list)
    for a in everything:
        if a["act"] in (RETURNED, FAILED, RECOVERED):
            owner = start_owner.get(a.get("caused_by"), a.get("caused_by"))
            ends_of[owner].append(a)
    review_ids = set()
    for c in children:
        d = (deleg.get(c["id"]) or {}).get("detail") or {}
        if is_review(ctx.text(c.get("turn")), c.get("because"),
                     _persona_name(ctx, d.get("persona"))):
            review_ids.add(c["id"])

    by_exp = collections.defaultdict(list)
    for e in execs:
        by_exp[e["expectation"]].append(e)

    def moving(exp) -> bool:
        return any(e["state"] == "running"
                   or (e.get("_open") and e.get("_run") in _LIVE_RUN)
                   for e in by_exp.get(exp, ()))

    def pending(exp) -> bool:
        return any(e["state"] == "not_started" for e in by_exp.get(exp, ()))

    trunk_moving = (v in _RUNNING or (v == "started-no-end" and seen == "live")
                    or (v == "waiting-on-work" and awaits == "moving"))
    impl_moving = trunk_moving or any(
        moving(c) or pending(c) for c in child_ids - review_ids)
    review_moving = any(moving(c) or pending(c) for c in review_ids)
    newest_start = max((a for a in everything if a["act"] == STARTED),
                       key=key, default=None)

    # -- produced work ------------------------------------------------------
    commits = sorted((a for a in everything if a["act"] == COMMITTED
                      and a.get("caused_by") not in review_ids
                      and (a.get("detail") or {}).get("commit")), key=key)
    # the newest produced commit by the record; section 5 narrows it to the
    # newest one the trunk's branch does not already hold
    head_act = commits[-1] if commits else None
    head = (head_act["detail"]["commit"] if head_act else None)
    provisioned = {a.get("caused_by"): a.get("detail") or {}
                   for a in sorted(everything, key=key)
                   if a["act"] == PROVISIONED}

    # -- reviews and their verdicts -----------------------------------------
    reviews = []
    for r in children:
        if r["id"] not in review_ids:
            continue
        reviewed = (provisioned.get(r["id"]) or {}).get("base_commit")
        if not reviewed:
            before = [a for a in commits if key(a) < key(r)]
            reviewed = before[-1]["detail"]["commit"] if before else None
        ends = sorted(ends_of.get(r["id"], ()), key=key)
        last = ends[-1] if ends else None
        verdict = source = None
        if last is not None and last["act"] in (RETURNED, RECOVERED):
            text = (ctx.text(last.get("turn")) if last["act"] == RETURNED
                    else None) or (last.get("detail") or {}).get("text") \
                or last.get("because")
            verdict = verdict_of(text)
            source = "computed-from-prose"
        reviews.append({"expectation": r["id"], "reviewed": reviewed,
                        "verdict": verdict, "source": source,
                        "ended": last, "failed": bool(last and last["act"]
                                                      == FAILED),
                        "_key": key(last) if last else key(r)})
    for a in everything:
        if a["act"] != REVIEW_VERDICT:
            continue
        d = a.get("detail") or {}
        if str(d.get("verdict") or "").lower() not in VERDICTS:
            continue
        on = a.get("caused_by") if a.get("caused_by") in review_ids else (
            (a.get("about") or [None])[0])
        mine = next((x for x in reviews if x["expectation"] == on), None)
        if mine is None:
            mine = {"expectation": on, "reviewed": None, "ended": None,
                    "failed": False}
            reviews.append(mine)
        mine.update(verdict=str(d["verdict"]).lower(), source="recorded",
                    reviewed=d.get("commit") or mine.get("reviewed"),
                    lacks=list(d.get("lacks") or ()), _key=key(a), act=a["id"])
    reviews.sort(key=lambda x: x["_key"])

    def review_ev(rv):
        if rv is None:
            return None
        return {"expectation": rv["expectation"], "verdict": rv["verdict"],
                "source": rv["source"], "commit": rv["reviewed"]}

    def newer_commit_than(k) -> bool:
        return any(key(a) > k for a in commits)

    def blocked(why, act_id, rv=None, source="computed"):
        return _result("blocked", "Blocked: " + _clip(why, 90), source,
                       _evidence(head=head, review=review_ev(rv),
                                 blocked={"why": why, "act": act_id}))

    # -- 1. blocked ----------------------------------------------------------
    parked = _parked_by_owner(everything, trunk, key)
    if parked and not impl_moving and not review_moving \
            and not (newest_start and key(newest_start) > key(parked)):
        return _result("parked", "Parked · by your decision, where it stopped",
                       "computed", _evidence(head=head, blocked={
                           "why": "the owner chose to park it",
                           "act": parked["id"]}))
    if v == "failed" and owed_n:
        # A FAILED RUN WITH A QUESTION OPEN TO THE OWNER is theirs to answer
        # first (`dispatch._ask_owner_about_empty`): the question is what
        # moves it, so it is said before the failure.
        return _result("awaiting_owner", WORDS["awaiting_owner"]
                       + (f" · {owed_n} open" if owed_n > 1 else "")
                       + " · its last run failed",
                       "computed", _evidence(head=head))
    if v == "failed":
        fails = sorted((a for a in ends_of.get(trunk, ())
                        if a["act"] == FAILED), key=key)
        f = fails[-1] if fails else None
        return blocked("the last run failed"
                       + (f" — {_clip(f.get('because'), 70)}"
                          if f and f.get("because") else ""),
                       f["id"] if f else None)
    newest_child = max(children, key=key, default=None)
    if newest_child is not None and not impl_moving and not review_moving:
        ends = sorted(ends_of.get(newest_child["id"], ()), key=key)
        if ends and ends[-1]["act"] == FAILED and not (
                newest_start and key(newest_start) > key(ends[-1])):
            kind = ("the review" if newest_child["id"] in review_ids
                    else "the delegated work")
            return blocked(f"{kind} could not run"
                           + (f" — {_clip(ends[-1].get('because'), 70)}"
                              if ends[-1].get("because") else ""),
                           ends[-1]["id"],
                           next((r for r in reviews if r["expectation"]
                                 == newest_child["id"]), None))
    if v in _STALLED:
        return blocked(state.get("label") or "it will not resume by itself",
                       None)
    if v == "waiting-on-work" and awaits in ("ended", "stalled"):
        return blocked("waiting on other work that is not moving", None)
    latest = next((r for r in reversed(reviews) if r["verdict"]), None)
    if latest is not None and not impl_moving and not review_moving \
            and not newer_commit_than(latest["_key"]):
        if latest["verdict"] == "incomplete":
            return blocked("the review could not finish"
                           + (f" — lacks {', '.join(latest['lacks'])}"
                              if latest.get("lacks") else ""),
                           latest.get("act") or (latest["ended"] or {})
                           .get("id"), latest, latest["source"])
        if latest["verdict"] == "block":
            return blocked("the review found problems to fix",
                           latest.get("act") or (latest["ended"] or {})
                           .get("id"), latest, latest["source"])

    # -- 2. the owner's decision --------------------------------------------
    if owed_n:
        return _result("awaiting_owner", WORDS["awaiting_owner"]
                       + (f" · {owed_n} open" if owed_n > 1 else ""),
                       "computed", _evidence(head=head))
    # -- 3. building ---------------------------------------------------------
    if impl_moving or v == "waiting-on-decision":
        words = WORDS["building"] + (" · waiting on a decision"
                                     if v == "waiting-on-decision" else "")
        return _result("building", words, "computed", _evidence(head=head))
    if head is None and v in _NOT_STARTED:
        return _not_started(v, everything)

    # -- 4. nothing produced ------------------------------------------------
    if head is None:
        if review_moving:
            return _result("awaiting_review", "Awaiting review · in review",
                           "computed", _evidence())
        if met:
            return _result("ended", "Answered · objective met", "computed",
                           _evidence())
        if v in _ENDED or v in ("waiting-on-child", "claimed-met"):
            return _result("ended", WORDS["ended"] + " · nothing committed",
                           "computed", _evidence())
        return unknown(f"no stage rule covers its state {v!r}")

    # -- 5. produced work: what is not yet in the trunk's branch? ---------
    # EVERY BRANCH'S NEWEST COMMIT, the trunk's and each child's; one that
    # the trunk's branch (or another open branch) already holds is
    # integrated and drops out. What is left must all be merged, deployed
    # and covered by a PASS; the head is the newest of it.
    info = (provisioned.get(trunk) or provisioned.get(head_act.get(
        "caused_by")) or next(iter(provisioned.values()), None))
    repo = (info or {}).get("repo")
    if not repo:
        return unknown("commits are recorded, and no worktree under it says "
                       "which repository holds them")
    _seen(repo)
    g = _git_of(ctx)
    branch_of = collections.defaultdict(list)
    newest = {}
    for c in commits:                       # in record order
        branch_of[c.get("caused_by")].append(c["detail"]["commit"])
        newest[c.get("caused_by")] = c
    open_tips = sorted(newest.values(), key=key)

    def holds(tip_sha, sha) -> bool:
        got, why = g.contains(repo, tip_sha, sha)
        if got is None:
            raise _GitUnknown(f"git could not say whether {sha[:10]} is in "
                              f"{tip_sha[:10]}: {why}")
        return got

    try:
        trunk_tip = newest.get(trunk)
        if trunk_tip is not None:
            t = trunk_tip["detail"]["commit"]
            open_tips = [c for c in open_tips if c is trunk_tip
                         or not holds(t, c["detail"]["commit"])]
        if len(open_tips) > 1:
            shas = [c["detail"]["commit"] for c in open_tips]
            open_tips = [c for c, sha in zip(open_tips, shas)
                         if not any(o != sha and holds(o, sha)
                                    for o in shas)] or open_tips
    except _GitUnknown as exc:
        return unknown(str(exc))
    tops = [p.get("integration_target") for p in
            ([provisioned.get(trunk)] + list(provisioned.values())) if p]
    target = next((t for t in tops if t and not str(t).startswith(
        "mentis/")), None) or "main"
    tip, why_tip = g.tip(repo, target)
    if tip is None:
        return unknown(f"git could not say where {target} is: {why_tip}")
    in_target = {}
    every_tip = sorted(newest.values(), key=key)
    for c in every_tip:
        t = c["detail"]["commit"]
        got, why_m = g.contains(repo, tip, t)
        if got is None:
            return unknown(f"git could not say whether {t[:10]} is in "
                           f"{target}: {why_m}")
        in_target[t] = got
    # SUPERSEDED: an open tip committed BEFORE the newest tip of this tree
    # that is already in the target -- a competing branch that lost (only
    # the winner was merged). It is listed, never waited on. A tip
    # committed after the newest integrated one still counts.
    # the newest of EVERY branch's tip, open or held by another branch
    integrated = [c for c in every_tip if in_target[c["detail"]["commit"]]]
    newest_in = max(integrated, key=key) if integrated else None
    superseded = [c for c in open_tips
                  if newest_in is not None
                  and not in_target[c["detail"]["commit"]]
                  and key(c) < key(newest_in)]
    live = [c for c in open_tips if c not in superseded]
    head_act = max(live, key=key)
    head = head_act["detail"]["commit"]
    tips = list(dict.fromkeys(c["detail"]["commit"] for c in live))
    unmerged = [t for t in tips if not in_target[t]]
    merged = not unmerged
    dep, why_dep = g.deployed()
    deployed = None
    undeployed = []
    if dep:
        for t in tips:
            got, why_d = g.contains(repo, dep, t)
            if got is None and why_d and "bad" not in why_d.lower() \
                    and "unknown revision" not in why_d.lower():
                return unknown(f"git could not say whether {t[:10]} is "
                               f"deployed: {why_d}")
            if not got:
                undeployed.append(t)
        deployed = not undeployed

    def covers(rv, c) -> bool | None:
        r = rv.get("reviewed")
        if not r:
            return None
        if r == c:
            return True
        for line in branch_of.values():
            if r in line and c in line:
                return line.index(r) >= line.index(c)
        got, _ = g.contains(repo, r, c)
        return got

    passes = [r for r in reviews if r["verdict"] == "pass"]
    # A PASS COVERS THE WORK when every open branch tip is covered by some
    # PASS; the one named is the newest that covers the head.
    covering = next((r for r in reversed(passes) if covers(r, head)), None)
    if covering and not all(any(covers(r, t) for r in passes)
                            for t in tips):
        covering = None
    ev = dict(head=head, merged=merged, deployed_commit=dep,
              target=target, deployed_why=None if dep else why_dep,
              # WHICH TIPS: what is not yet in the target, not yet deployed,
              # and the losing branches set aside
              unmerged_tips=unmerged,
              undeployed_tips=undeployed if dep else None,
              superseded_tips=[c["detail"]["commit"] for c in superseded],
              review=review_ev(covering or (reviews[-1] if reviews
                                            else None)))
    src = covering["source"] if covering else "computed"
    if deployed:
        return _result("deployed", WORDS["deployed"] + ("" if covering else
                                                        " · not reviewed"),
                       src, _evidence(**ev))
    if covering:
        words = ("Ready to deploy · merged, not deployed" if merged
                 else "Ready to deploy · reviewed, not merged")
        if dep is None:
            words += " (what is deployed is unknown)"
        return _result("ready_to_deploy", words, src, _evidence(**ev))
    src_rv = (reviews[-1]["source"] or "computed") if reviews else "computed"
    if review_moving:
        words = "Awaiting review · in review"
    elif any(r["ended"] is None and not r["verdict"] for r in reviews):
        # a review delegated and not yet run: somebody is coming
        words = WORDS["awaiting_review"] + " · review delegated, not yet run"
    else:
        # NOBODY HAS IT. Nothing runs, no review is pending, no PASS covers
        # the head: the work sits where its last run left it. Said as
        # parked rather than as waiting for a reviewer nobody sent (owner,
        # 2026-10-26). A carrier resumed and about to run reads so for the
        # seconds its dispatch takes, as it always did.
        if reviews and reviews[-1]["ended"] is not None \
                and not reviews[-1]["verdict"]:
            why = "last review stated no verdict; nobody is working on it"
        elif any(r["verdict"] for r in reviews):
            why = "repaired after a review; re-review not started"
        else:
            why = "built, not reviewed; nobody is working on it"
        return _result("parked", WORDS["parked"] + " · " + why, src_rv,
                       _evidence(**ev))
    return _result("awaiting_review", words, src_rv, _evidence(**ev))
