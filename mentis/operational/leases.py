"""SHARED RESOURCES, LEASED: who is using a worktree, a path, a port or a service.

Several agents work at once -- dispatched runs and hand-started sessions --
and until this nothing said which of them was using what. Two of them could
build in one worktree, start test servers on one port, or restart one service
under each other. This is the record saying so, and nothing more:

  * A LEASE is a `resource-claimed` act, held by (participant, execution) --
    for a dispatched run, also by the run (`execution-started` act) it was
    claimed in. It names a resource (`kind`, `name`), a `mode` (`exclusive` or
    `shared`), a `ttl_s` and a `purpose`.
  * It ENDS at a `resource-released` act (the holder's release, or the
    dispatch end hook `end_run` when the holder's run ends), at TTL expiry, or
    when the run that holds it has ended (a run whose hook never ran -- the
    server stopped -- holds nothing). An ended or expired lease never blocks.
  * A CONFLICT is two live leases on OVERLAPPING resources, held by different
    holders, at least one exclusive. Paths (`worktree` and `path` share one
    namespace) overlap when one contains the other; ports and services
    overlap only when equal. Nothing else is ever compared, so unrelated work
    is never serialized.
  * CLAIMING AGAIN RENEWS. The same holder claiming the same resource writes a
    new claim that replaces its previous one (`detail.renews`): that is how a
    session keeps a lease past its TTL.

WHAT IT IS NOT. It is not a lock anything enforces on the filesystem, the
network or Git: Mentis still creates no worktree and commits nothing. It
confers no authority. A lease is a statement other agents are told and asked
to respect, and a conflicting claim is refused so an agent learns of the
holder before it starts, not after it has collided.

THE PROJECTION (`_Projection`) is kept in this process from a cursor over the
operational table's `seq`: one rowid range read of only the two lease acts
written since the last look, so a call costs what has changed, not the Brain's
70k+ rows. The first read in a process scans once; it is rebuilt every
`REBUILD_S` and whenever a claim's transaction fails. It is not a second
record: it is derived only from the acts and replaced by recomputing them.
"""
from __future__ import annotations

import logging
import ntpath
import os
import posixpath
import re
import threading
import time

_log = logging.getLogger(__name__)

CLAIMED = "resource-claimed"
RELEASED = "resource-released"
STARTED = "execution-started"

KINDS = ("worktree", "path", "port", "service")
PATH_KINDS = ("worktree", "path")
MODES = ("exclusive", "shared")

TTL_DEFAULT = 1800
TTL_MAX = 14400

#: How often the projection is rebuilt from the record rather than advanced.
REBUILD_S = 600.0

#: What a refused claim is told it may do instead.
RECOVERY = (
    "wait until the holder's lease ends (its run ends, it releases, or the "
    "lease expires) and claim again",
    "ask the holder (named above) to release it -- e.g. in the Conversation "
    "it works in",
    "use another worktree, path, port or service and claim that instead",
    "call `resources` to see every live lease",
)

#: The clock leases are judged by. A module attribute so tests can move it.
_clock = time.time


class LeaseError(ValueError):
    """An argument that names no resource this module can lease."""


# -- names ----------------------------------------------------------------------

_DRIVE = re.compile(r"^[A-Za-z]:")
_MSYS = re.compile(r"^/([A-Za-z])(/|$)")


def normalize(kind, name) -> str:
    """The resource's key: the name as every claim on it compares.

    Paths must be absolute. On Windows (or for a drive-lettered path anywhere)
    they compare case-insensitively with either slash; a Git Bash `/c/...`
    path is the same as `C:\\...`. Ports are integers 1-65535. Services are
    names, compared case-insensitively.
    """
    if kind not in KINDS:
        raise LeaseError(f"`kind` is one of {list(KINDS)}, not {kind!r}")
    text = str(name if name is not None else "").strip()
    if not text:
        raise LeaseError(f"a {kind} lease needs a `name`")
    if kind == "port":
        try:
            port = int(text)
        except ValueError:
            raise LeaseError(f"a port is a number, not {text!r}") from None
        if not 1 <= port <= 65535:
            raise LeaseError(f"a port is 1-65535, not {port}")
        return str(port)
    if kind == "service":
        return " ".join(text.lower().split())
    msys = _MSYS.match(text)
    if msys and (os.name == "nt"):
        text = f"{msys.group(1).upper()}:\\" + text[len(msys.group(0)):]
    if os.name == "nt" or _DRIVE.match(text) or text.startswith("\\\\"):
        if not (_DRIVE.match(text) and text[2:3] in ("\\", "/")) \
                and not text.startswith(("\\\\", "//")):
            raise LeaseError(f"a {kind} is named by its absolute path, "
                             f"not {text!r}")
        return ntpath.normcase(ntpath.normpath(text)).rstrip("\\") or "\\"
    if not text.startswith("/"):
        raise LeaseError(f"a {kind} is named by its absolute path, not {text!r}")
    return posixpath.normpath(text).rstrip("/") or "/"


def _contains(outer: str, inner: str) -> bool:
    if outer == inner:
        return True
    sep = "\\" if ("\\" in outer or _DRIVE.match(outer)) else "/"
    return inner.startswith(outer if outer.endswith(sep) else outer + sep)


def overlaps(a_kind, a_key, b_kind, b_key) -> bool:
    """Whether two resources are the same thing or one contains the other."""
    if a_kind in PATH_KINDS and b_kind in PATH_KINDS:
        return _contains(a_key, b_key) or _contains(b_key, a_key)
    return a_kind == b_kind and a_key == b_key


# -- the projection ---------------------------------------------------------------

class _Projection:
    """Live-or-recent leases of one store, advanced from a `seq` cursor."""

    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()
        self.generation = 0
        self.reset()

    def reset(self):
        with self.lock:
            self.generation = getattr(self, "generation", 0) + 1
            self.cursor = 0
            self.built = 0.0
            self.leases: dict[str, dict] = {}

    def refresh(self) -> dict[str, dict]:
        """Advance from the cursor and answer the leases not yet expired.

        THE STORE IS READ OUTSIDE THIS PROJECTION'S LOCK. A claim holds the
        store's writer lock and then asks this; a reader holding this lock
        while waiting for the store would deadlock with it. So the cursor is
        taken under the lock, the rows read without it, and applied under it
        again -- skipping what another reader applied meanwhile, and starting
        over if the projection was reset in between."""
        import json
        for _ in range(3):
            with self.lock:
                if self.built == 0.0 or _clock() - self.built > REBUILD_S:
                    self.generation += 1
                    self.cursor, self.leases = 0, {}
                    self.built = _clock()
                cursor, generation = self.cursor, self.generation
            rows = self.store._rows(
                "SELECT seq, id, at, actor, act, execution, about, detail "
                "FROM operational WHERE seq > ? AND act IN (?, ?) "
                "ORDER BY seq", (cursor, CLAIMED, RELEASED))
            with self.lock:
                if generation != self.generation:
                    continue
                for row in rows:
                    if row["seq"] <= self.cursor:
                        continue
                    self.cursor = row["seq"]
                    self._apply(row, json.loads(row["detail"] or "{}"),
                                json.loads(row["about"] or "[]"))
                # What has expired can never come back: drop it.
                now = _clock()
                for lid in [k for k, v in self.leases.items()
                            if v["expires"] <= now]:
                    del self.leases[lid]
                return dict(self.leases)
        raise RuntimeError("the lease projection kept being reset")

    def _apply(self, row, detail, about):
        if row["act"] == CLAIMED:
            for old in detail.get("renews") or ():
                self.leases.pop(old, None)
            self.leases[row["id"]] = {
                "lease": row["id"], "kind": detail.get("kind"),
                "name": detail.get("name"), "key": detail.get("key"),
                "mode": detail.get("mode"),
                "purpose": detail.get("purpose"),
                "participant": row["actor"],
                "execution": row["execution"],
                "run": detail.get("run"),
                "since": row["at"],
                "expires": row["at"] + float(detail.get("ttl_s")
                                             or TTL_DEFAULT)}
        else:
            for gone in about:
                self.leases.pop(gone, None)


_PROJECTIONS: dict[int, _Projection] = {}
_PROJECTIONS_LOCK = threading.Lock()


def _projection(cv) -> _Projection:
    store = cv._c._store
    with _PROJECTIONS_LOCK:
        got = _PROJECTIONS.get(id(store))
        if got is None or got.store is not store:
            got = _PROJECTIONS[id(store)] = _Projection(store)
        return got


def _run_ended(cv, run) -> bool:
    if not run:
        return False
    try:
        return cv.run_end(run) is not None
    except Exception:                                     # noqa: BLE001
        return False


def live(cv) -> list[dict]:
    """Every lease that holds now: unreleased, unexpired, its run not ended."""
    out = [dict(v) for v in _projection(cv).refresh().values()
           if not _run_ended(cv, v.get("run"))]
    return sorted(out, key=lambda v: v["since"])


# -- the operations ----------------------------------------------------------------

def _current_run(cv, execution) -> str | None:
    """The newest run (`execution-started`) of this execution, or None for a
    hand-started session, which has none."""
    if not execution:
        return None
    got = cv._c.operational(execution=execution, act=STARTED,
                            newest_first=True, limit=1)
    return got[0]["id"] if got else None


def _when(at) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(at))


def _holder_words(lease) -> str:
    who = lease["participant"]
    exe = (lease.get("execution") or "")[:8]
    return f"{who} (execution {exe})" if exe else who


def refusal_of(lease, *, kind, name, mode, op="claim_resource") -> dict:
    """The structured refusal for a claim that conflicts with `lease`."""
    why = (f"{kind} {name!r} ({mode}) overlaps {lease['kind']} "
           f"{lease['name']!r}, held {lease['mode']} by "
           f"{_holder_words(lease)} for "
           f"\"{lease.get('purpose') or 'no purpose given'}\", since "
           f"{_when(lease['since'])}, expiring {_when(lease['expires'])}")
    return {"op": op, "boundary": "resource", "why": why,
            "recovery": list(RECOVERY),
            "who": lease["participant"],
            "holder": {"participant": lease["participant"],
                       "execution": lease.get("execution"),
                       "run": lease.get("run")},
            "lease": lease["lease"],
            "resource": {"kind": lease["kind"], "name": lease["name"]},
            "mode": lease["mode"],
            "purpose": lease.get("purpose"),
            "since": lease["since"], "expires": lease["expires"]}


def _not_permitted(refusal: dict):
    """`worker.NotPermitted`, carrying the structured fields as `refusal`.

    Until WS-I's structured `NotPermitted` lands here, the fields ride as an
    attribute and the message says them all."""
    from mentis.worker import NotPermitted
    text = (f"{refusal['op']} refused (boundary: resource): {refusal['why']}. "
            f"Who can lift it: {refusal['who']}. Recovery: "
            + "; ".join(refusal["recovery"]))
    exc = NotPermitted(text)
    exc.refusal = refusal
    for k in ("op", "boundary", "why", "recovery", "who"):
        if not hasattr(exc, k):
            setattr(exc, k, refusal[k])
    return exc


def _ttl(ttl_s) -> int:
    if ttl_s in (None, ""):
        return TTL_DEFAULT
    try:
        ttl = int(ttl_s)
    except (TypeError, ValueError):
        raise LeaseError(f"`ttl_s` is a number of seconds, not {ttl_s!r}") from None
    if ttl < 1:
        raise LeaseError("`ttl_s` is at least 1 second")
    return min(ttl, TTL_MAX)


def claim(cv, *, participant, execution, runtime=None, kind, name,
          mode="exclusive", ttl_s=None, purpose=None, run=None) -> dict:
    """Claim a resource for (participant, execution), or refuse with the holder.

    The check and the write are one transaction under the store's writer lock
    (`atomic`), so of two claims racing for one resource exactly one wins.
    """
    if not participant:
        from mentis.worker import NotPermitted
        raise NotPermitted("a lease needs a Participant to hold it")
    key = normalize(kind, name)
    mode = mode or "exclusive"
    if mode not in MODES:
        raise LeaseError(f"`mode` is one of {list(MODES)}, not {mode!r}")
    ttl = _ttl(ttl_s)
    purpose = (str(purpose).strip() or None) if purpose is not None else None
    proj = _projection(cv)
    try:
        with cv._c.atomic():
            run = run if run is not None else _current_run(cv, execution)
            renews = []
            for lease in live(cv):
                if not overlaps(kind, key, lease["kind"], lease["key"]):
                    continue
                mine = (lease["participant"] == participant
                        and lease.get("execution") == execution)
                if mine:
                    if lease["kind"] == kind and lease["key"] == key:
                        renews.append(lease["lease"])
                    continue
                if "exclusive" in (mode, lease["mode"]):
                    raise _not_permitted(refusal_of(
                        lease, kind=kind, name=key, mode=mode))
            lid = cv.record_act(
                actor=participant, act=CLAIMED, execution=execution,
                runtime=runtime,
                because=purpose or f"claimed {kind} {key}",
                detail={"kind": kind, "name": str(name).strip(), "key": key,
                        "mode": mode, "ttl_s": ttl, "purpose": purpose,
                        "run": run,
                        **({"renews": renews} if renews else {})})
    except Exception as exc:
        if not getattr(exc, "refusal", None):
            proj.reset()
        raise
    now = _clock()
    return {"ok": True, "lease": lid, "kind": kind, "name": key, "mode": mode,
            "ttl_s": ttl, "expires": now + ttl, "expires_at": _when(now + ttl),
            "renewed": renews,
            "note": "a lease is a statement to other agents, not a lock: it "
                    "ends when your run ends, when you release it, or at its "
                    "expiry. Claim again to renew it."}


def release(cv, *, participant, execution, runtime=None, kind=None, name=None,
            lease=None, session=False, because=None) -> dict:
    """Release the caller's own live lease(s): one by id, or those on a resource.

    Only the holder's: the same participant and execution, or, for a
    hand-started session, the same participant's session leases (a restarted
    session is a new execution of the same participant)."""
    from mentis.worker import NotPermitted
    key = normalize(kind, name) if (kind or name) and not lease else None

    def own(v):
        if v["participant"] != participant:
            return False
        return v.get("execution") == execution or (session and not v.get("run"))

    with cv._c.atomic():
        held = live(cv)
        if lease:
            got = [v for v in held if v["lease"] == lease]
            if not got:
                raise NotPermitted(f"{lease!r} is not a live lease: it was "
                                   f"released, it expired, or its run ended")
        else:
            if key is None:
                raise NotPermitted("name the lease (`lease`) or the resource "
                                   "(`kind` and `name`) to release")
            got = [v for v in held if v["kind"] == kind and v["key"] == key]
        mine = [v for v in got if own(v)]
        if not mine:
            if got:
                raise NotPermitted(
                    f"that lease is held by {_holder_words(got[0])}, not by "
                    f"you; only its holder releases it, and it ends by itself "
                    f"when its run ends or it expires")
            return {"ok": True, "released": [], "note": "you hold no live "
                    "lease on that resource; nothing was recorded"}
        ids = [v["lease"] for v in mine]
        act = cv.record_act(actor=participant, act=RELEASED,
                            execution=execution, runtime=runtime,
                            about=ids, because=because or "released by holder",
                            detail={"reason": "released",
                                    "resources": [{"kind": v["kind"],
                                                   "name": v["key"]}
                                                  for v in mine]})
    return {"ok": True, "released": ids, "act": act}


def end_run(cv, started) -> list[str]:
    """The dispatch end hook: release every lease the run `started` held.

    Never raises: a run's end is recorded whatever happens here, and a lease
    this fails to release still ends with the run (`live` asks `run_end`)."""
    if cv is None or not started:
        return []
    try:
        held = [v for v in _projection(cv).refresh().values()
                if v.get("run") == started]
        if not held:
            return []
        first = held[0]
        with cv._c.atomic():
            cv.record_act(actor=first["participant"], act=RELEASED,
                          execution=first.get("execution"),
                          about=[v["lease"] for v in held],
                          because="the holder's run ended",
                          detail={"reason": "run-ended", "run": started,
                                  "resources": [{"kind": v["kind"],
                                                 "name": v["key"]}
                                                for v in held]})
        return [v["lease"] for v in held]
    except Exception:                                     # noqa: BLE001
        _log.exception("releasing the leases of run %s", started)
        return []


def listing(cv, *, participant=None, execution=None, kind=None, name=None) -> dict:
    """What `resources` answers: live leases, optionally on one resource."""
    held = live(cv)
    if kind or name:
        key = normalize(kind, name)
        held = [v for v in held if overlaps(kind, key, v["kind"], v["key"])]
    now = _clock()
    return {"leases": [{
        "lease": v["lease"], "kind": v["kind"], "name": v["key"],
        "mode": v["mode"], "purpose": v.get("purpose"),
        "holder": {"participant": v["participant"],
                   "execution": v.get("execution"), "run": v.get("run")},
        "yours": (v["participant"] == participant
                  and v.get("execution") == execution),
        "since": _when(v["since"]), "expires": _when(v["expires"]),
        "expires_in_s": int(v["expires"] - now)} for v in held],
        "note": "leases other agents hold; claim before using a worktree, "
                "path, port or service exclusively"}


def prompt_lines(cv, *, workspace, execution) -> str:
    """What dispatch tells a run of OTHER live work's leases inside its
    workspace. Empty when there is none. Never refuses the run."""
    if not workspace:
        return ""
    try:
        key = normalize("path", workspace)
    except LeaseError:
        return ""
    try:
        held = [v for v in live(cv)
                if v["kind"] in PATH_KINDS and v.get("execution") != execution
                and overlaps("path", key, v["kind"], v["key"])]
    except Exception:                                     # noqa: BLE001
        _log.exception("reading leases for a dispatch prompt")
        return ""
    if not held:
        return ""
    lines = [f"- {v['kind']} {v['key']} -- {v['mode']}, held by "
             f"{_holder_words(v)} for \"{v.get('purpose') or 'no purpose given'}\""
             f", since {_when(v['since'])}, expires {_when(v['expires'])}"
             for v in held]
    return ("\n\n---\nShared resources: other live work holds leases inside "
            f"this workspace ({workspace}):\n" + "\n".join(lines)
            + "\nDo not build, test or change files inside an exclusively held "
              "resource. Before using a worktree, path, port or test server "
              "exclusively, claim it with `claim_resource`; a conflicting claim "
              "is refused with its holder. Use another worktree or port if one "
              "is held.")
