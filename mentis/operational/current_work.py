"""CURRENT WORK, KEPT: what an agent orients by, without rebuilding history.

`work_overview` was a projection rebuilt on every call: every trunk ever
recorded in a Conversation (433 in Mentis Fluid Workspace, 2,075 Brain-wide,
most of them ended weeks ago) had its whole operational lineage walked again,
one row at a time -- 38,000 statements to show 20 items. Each statement hands
the interpreter lock back and forth, so beside a busy thread every one cost
9-16 ms and a single call took minutes (2026-10-31).

THIS KEEPS THE SAME PROJECTION AND UPDATES IT. One read model of the Brain,
kept on a thread of its own (`start`), holding each trunk's item exactly as
`work_overview.project` words it -- a Conversation's current work is that,
filtered (`of`) -- and an index of what each item read:

  * BUILT set-based: the lineage of every trunk read a level at a time for all
    of them together (`Conversations._prefetch_lineage`), and lookups that
    repeat per item asked once per reading.
  * UPDATED FROM A CURSOR: what was written after it (`Store.since`, the read
    the pulse already makes) is placed against the index, and only the items
    those writes reach are projected again. An item depends on every
    expectation its projection read -- its own lineage, and any other work it
    waits on -- so a write under awaited work reaches the waiting item too.
  * REBUILT whole only for what a projection reads of entries (`REBUILDS`:
    people, Personas, governing material, placements, a Conversation's name),
    a kind not yet classified, a gap longer than `CAP`, or a record that is
    not at or past the cursor. And reconciled -- rebuilt and compared --
    every `RECONCILE_S`. Read beside the writer, never under its lock.
  * GIT: items whose stage asked git are projected again every `GIT_S`.
  * TIME: an item whose stage is time-dependent (`stage.RESUME_GRACE_S` after
    its last act) is projected again until that window has passed.

NOT A SECOND RECORD. Nothing here is written anywhere or read back as
authority: it is the projection, kept in this process, derived only from the
record and replaced by recomputing it. A restart starts empty. Full history
stays where it was: `history`, `resolve` and `work.detail`.

READS DO NOT BUILD IT. A reader waits briefly (`WAIT_S`) for the model to
catch up with the record as it stood when asked, then is answered from it;
before the first build after a start, it is told so at once (`NotReady`).
Its readers: `work_overview` and `brief` (`orientation.outstanding`), and
through `operational.read_model` every work and obligation route: Home's
Work, `/api/work` for the owner, `/api/owed` and a Conversation's `owed`.

WHAT THIS PROCESS OBSERVES OF RUNS (`observe`): the server's own
observation (`web._runtime_observation`) and the executions it holds
(`active_executions`), which qualify runs the record says are open and move
with no write. Their SIGNATURE -- only what a projection reads of them:
whether each run is going, ended or not handed over, and each handle's
liveness -- is kept with the model. When it moves, the items with a run
open in their tree (`rt`), and the work and obligations a changed handle
names, are projected again. Without an observer the model says it has no
live feed (`RUNTIME`), as it always did.

OBLIGATIONS, KEPT BESIDE THE WORK (`states`): `expectation_state` of every
expectation in the record, with an index of what each read -- its own acts,
its Turn, its form, the replies that answered it -- placed and updated the
same way. What is owed is the ones nobody has answered (`owed`).

PLACING AND SCOPE (`place`, `below`, `found`): what `_scoped_group` and
`_in_scope` read of each item that the item itself does not carry -- what
was observed of its open runs, what the work it waits on is doing, the acts
under it, and which requests are kept as discovered work.
"""
from __future__ import annotations

import json
import threading
import time

from mentis.operational import work_overview as wo

#: Rows of any one kind after the cursor beyond which the gap is not placed:
#: the model is rebuilt.
CAP = 2000

#: How often the model is rebuilt and compared with what was kept.
RECONCILE_S = 900.0

#: How long a reader waits for the maintained model to catch up with the
#: record as it stood when asked, before answering from it as it stands.
WAIT_S = 2.0

#: How often the maintainer brings the model up to date unasked.
MAINTAIN_S = 5.0


class NotReady(Exception):
    """The first build after a start has not finished: nothing to answer."""

#: What a Conversation is made of (`web.moved`): placed, never rebuilt.
from mentis.web.moved import CONVERSATION_MATERIAL  # noqa: E402

RUNTIME = {"runs": None, "why_not": "the worker read has no live MARS feed"}

#: The acts that start and end a run, as `work` names them.
from mentis.operational.work import ENDS as _ENDS, STARTED as _STARTED  # noqa: E402,I001
from mentis.operational.work import _LIVE as _LIVE_HANDLE  # noqa: E402


def _canon(item) -> str:
    return json.dumps(item, sort_keys=True, default=str)


def _obs_key(obs):
    """Every field of one observed run a projection reads: what
    `runs.run_state` words its state and summary from (the times it quotes,
    and the latest event's words and time) and `work_overview._runtime_ok`.
    The rest of `run_state`'s answer (activity, permissions, stopping) is not
    carried into a WorkItem or WorkDetail, so it moves nothing here."""
    if obs is None:
        return None
    last = obs.get("last_event")
    return (obs.get("ended_at"), obs.get("opened_at"),
            obs.get("performing_since"), bool(obs.get("running")),
            (last.get("what"), last.get("at")) if last else None,
            wo._runtime_ok(obs))


def signature(runtime, handles) -> tuple:
    """THE PART OF WHAT THIS PROCESS OBSERVES THAT A PROJECTION READS: the
    observation's answer for each run, each handle's liveness, why it could
    not be asked, and the executions held here (`active_executions`)."""
    runs, inst = runtime.get("runs"), runtime.get("instances")
    return (
        runtime.get("why_not"),
        None if runs is None else tuple(sorted(
            (k, _obs_key(v)) for k, v in runs.items())),
        None if inst is None else tuple(sorted(
            (k, v in _LIVE_HANDLE) for k, v in inst.items())),
        tuple(sorted(handles)))


def _handles(cv) -> list:
    """The executions this process holds, as a projection reads them."""
    try:
        return [(str(e.reference), e.for_expectation, e.participant,
                 e.conversation) for e in cv.active_executions()]
    except Exception:                                     # noqa: BLE001
        return []


def cursor_text(advance) -> str:
    return ".".join(str(int(x)) for x in advance)


def parse_cursor(text):
    """A cursor this module gave, or None (then everything is new)."""
    try:
        got = tuple(int(x) for x in str(text).split("."))
    except (TypeError, ValueError):
        return None
    return got if len(got) == 3 else None


class _Reading(wo._Ctx):
    """`work_overview._Ctx`, noting which work each item's projection read."""

    def __init__(self, cv):
        super().__init__(cv)
        self.read = set()
        self.git_used = False
        self._stage_git = None

    # WHETHER AN ITEM ASKED GIT: `stage._git_of` keeps one `Git` on the
    # context; asking for it is what marks the item as depending on git,
    # which writes nothing to the record when work merges or deploys.
    @property
    def stage_git(self):
        self.git_used = True
        return self._stage_git

    @stage_git.setter
    def stage_git(self, value):
        self._stage_git = value

    def descendants(self, expectation):
        self.read.add(expectation)
        return super().descendants(expectation)

    def state(self, expectation):
        self.read.add(expectation)
        return super().state(expectation)


class _Model:
    """One immutable moment of the read model; replaced, never edited."""

    __slots__ = ("cursor", "items", "trunks", "deps", "built_at", "due", "git",
                 "git_at", "_reach", "place", "below", "rt", "runtime",
                 "rtsig", "viewer", "states", "sdeps", "found", "_sreach")

    def __init__(self, cursor, items, trunks, deps, built_at, due, git,
                 git_at, *, place, below, rt, runtime, rtsig, viewer,
                 states, sdeps, found):
        # `cursor`: the record's position this model was brought up to --
        # where its next update reads from. `due`: per item, until when its
        # stage may still move with no write (see `_window`). `git`: items
        # whose stage asked git, projected again every `GIT_S` (`git_at`).
        # `place`: per item, (`_seen`, `_awaits`) -- what places it in a
        # scoped read and is never sent. `below`: the acts under each trunk,
        # as the projection walked them. `rt`: items with a run in their tree
        # that no end names, which the runtime observation can move.
        # `runtime`, `rtsig`: the observation they were projected with, and
        # its signature. `viewer`: whom they were projected for. `states`,
        # `sdeps`: every expectation's state and what it read. `found`:
        # requests kept as discovered work.
        self.cursor, self.items = cursor, items
        self.trunks, self.deps, self.built_at = trunks, deps, built_at
        self.due, self.git, self.git_at = due, git, git_at
        self.place, self.below, self.rt = place, below, rt
        self.runtime, self.rtsig, self.viewer = runtime, rtsig, viewer
        self.states, self.sdeps, self.found = states, sdeps, found
        self._reach = None
        self._sreach = None

    def replace(self, **changes) -> "_Model":
        """This moment with some fields changed: a new model, never this one
        edited."""
        fields = {k: getattr(self, k) for k in self.__slots__
                  if not k.startswith("_")}
        fields.update(changes)
        return _Model(**fields)

    def reach(self) -> dict:
        """Every act, Turn and execution an item read -> those items."""
        if self._reach is None:
            self._reach = _invert(self.deps)
        return self._reach

    def sreach(self) -> dict:
        """Every act and Turn an expectation's state read -> those."""
        if self._sreach is None:
            self._sreach = _invert(self.sdeps)
        return self._sreach

    def owed(self, *, participant=None, conversation=None) -> list:
        """The expectations nobody has answered, in write order: carried by
        `participant` and recorded in `conversation`, where given. Each is
        `expectation_state` as it reads now."""
        return [s for s in self.states.values()
                if not s["response_present"]
                and (participant is None or s["expected_of"] == participant)
                and (conversation is None
                     or s["conversation"] == conversation)]

    def of(self, cid):
        """This Conversation's current work, or the Brain's (`cid` None):
        the same items, filtered -- each is projected on its own."""
        if cid is None:
            return self.items
        return {t: i for t, i in self.items.items()
                if self.trunks[t].get("conversation") == cid}

    def order(self, items) -> list:
        """As the overview orders: by group, newest first, then trunk order."""
        pos = {t: n for n, t in enumerate(self.trunks)}
        rank = {g: n for n, g in enumerate(wo.GROUPS)}
        got = sorted(items, key=lambda i: pos.get(i["expectation"], len(pos)))
        got.sort(key=wo._newest, reverse=True)
        got.sort(key=lambda i: rank[i["group"]])
        return got


def _invert(deps) -> dict:
    got = {}
    for key, under in deps.items():
        for ref in under:
            got.setdefault(ref, set()).add(key)
    return got


def _window(item, projected_at):
    """Until when this item's stage may still move with no write: its last
    act plus `stage.RESUME_GRACE_S`, if that was still ahead when it was
    projected; None if not. Such an item is projected again on each update
    until a projection is made after that moment (review: an item read inside
    its window and next read long after it kept the in-window stage)."""
    from mentis.operational.stage import RESUME_GRACE_S
    at = wo.parse_since(item.get("last_activity_at"))
    if at is None:
        return None
    until = at + RESUME_GRACE_S + 1
    return until if until > projected_at else None


#: WHAT A PROJECTION READS OF ENTRIES, AND SO REBUILDS: who people are and
#: which Personas they wear, the governing Workflows and Disciplines, where
#: governed material is placed and whether it stands, designations, and a
#: Conversation's own entry (its name). Measured on the live record, the week
#: to 2026-10-31: a few a day. Turn edits are placed (`_update`).
REBUILDS = frozenset({"participant", "persona", "workflow", "discipline",
                      "establishes", "scoped-to", "designated-as",
                      "conversation",
                      # FORMS AND THEIR ANSWERS: whether an input is given is
                      # read from its response set's entries, whose links
                      # name the set and nothing an item read (re-review)
                      "answer", "response-set", "responds-to",
                      "in-response-set", "marked-ready", "withdraws",
                      "own-words", "interpretation", "interpretation-reply"})

#: WHAT A PROJECTION DOES NOT READ, beyond a Conversation's own material: the
#: knowledge recorded about work (an outcome is read as its reply Turn, which
#: the acts beside it reach), forms and their answers, timers, proposals and
#: provenance links. Placed against the index like any write; they rebuild
#: nothing (review: `record_material` rebuilt the whole Brain). A kind in
#: neither list rebuilds, until it is classified.
PLACED = frozenset({
    "note", "finding", "lesson", "outcome", "outcome-of", "problem",
    "hypothesis", "solution", "rule", "decision", "observation", "observes",
    "extracted-from", "derived-from", "in-context", "shown-in",
    "timer-mark", "proposes", "proposes-to-supersede",
    "declines", "participates-in"}) | CONVERSATION_MATERIAL

#: How often items whose stage asked git are projected again: a merge or a
#: deploy writes nothing to the record (review).
GIT_S = 60.0


class CurrentWork:
    """The kept current work of one Conversation (`cid`), or the Brain's."""

    def __init__(self, cv, cid=None):
        self.cv, self.cid = cv, cid
        self._updating = threading.Lock()
        self._model: _Model | None = None
        self._thread = None
        self.failed: str | None = None      # the last failure, until it works
        self._broken = False                # the next refresh rebuilds
        self._wanted = threading.Event()
        self._moved = threading.Condition()
        #: What this process observes of runs (`web._runtime_observation`),
        #: set by the server; None: no live feed (`RUNTIME`).
        self.observe = None
        #: When the last pass that succeeded observed it (monotonic).
        self._observed_at = float("-inf")
        self.stats = {"builds": 0, "updates": 0, "projected": 0,
                      "obligations": 0, "reconciled": 0,
                      "reconcile_differences": 0, "failures": 0,
                      "rebuilt_because": {}}

    # -- projecting ---------------------------------------------------------

    def _observed(self):
        """(the runtime observation, its signature), now."""
        runtime = RUNTIME
        if self.observe is not None:
            try:
                runtime = self.observe()
            except Exception as exc:                      # noqa: BLE001
                runtime = {"runs": None, "instances": None,
                           "why_not": f"{type(exc).__name__}: {exc}"}
        return runtime, signature(runtime, _handles(self.cv))

    def _project(self, ctx, act, runtime=RUNTIME):
        """One item, and everything it read. ITS OWN MOTION: what awaited
        work is doing is worked out again for each item, never taken from an
        earlier item's answer, or this item would depend on work without
        having read it (review: two trunks awaiting the same work).

        (item, what it read, whether it asked git, its placing, the acts
        under it, whether a run in its tree has no end naming it)."""
        cv = self.cv
        viewer = wo.owner_of(cv)
        ctx.read, ctx.motion, ctx.visiting = set(), {}, set()
        ctx.git_used = False
        item = wo.project(ctx, act, viewer=viewer, runtime=runtime)
        place = (item.pop("_seen", None), item.pop("_awaits", None))
        # EVERYTHING THIS ITEM'S WORK HAS EVER AWAITED, ended or not. The
        # projection reads awaited work directly (`awaited_state`) and only
        # while the wait is open, so what it read is not enough: a wait that
        # ended can open again when that work moves again (review blocker).
        mine = [act["id"]] + [a["id"] for a in ctx.descendants(act["id"])
                              if a["act"] == "expectation-recorded"]
        # ...and what that awaited work awaits, all the way down: the motion
        # of a chain is read through it (re-review: A awaits B awaits C)
        awaited, frontier = set(), [w for e in mine for w in cv.awaits(e)]
        while frontier:
            w = frontier.pop()
            if w in awaited:
                continue
            awaited.add(w)
            for e in [w] + [a["id"] for a in ctx.descendants(w)
                            if a["act"] == "expectation-recorded"]:
                frontier.extend(cv.awaits(e))
        under = {act["id"]}
        if act.get("turn"):
            under.add(act["turn"])
        starts, ended = set(), set()
        for e in ctx.read | awaited | {act["id"]}:
            under.add(e)
            own = cv._act(e)
            if own and own.get("turn"):
                under.add(own["turn"])
            for a in ctx.descendants(e):
                under.add(a["id"])
                if a.get("turn"):
                    under.add(a["turn"])
                if a.get("execution"):
                    under.add(a["execution"])
                if a["act"] == _STARTED:
                    starts.add(a["id"])
                elif a["act"] in _ENDS:
                    ended.add(a.get("caused_by"))
        # A RUN NO END NAMES -- open, or closed only by a later run -- is
        # what the runtime observation is asked about (`_executions_of`,
        # `trunk_status._runs`): only such an item can move with it.
        return (item, under, ctx.git_used, place, ctx.descendants(act["id"]),
                bool(starts - ended))

    def _obligation(self, act):
        """One expectation's state (`expectation_state`), and what it read:
        its own acts (runs, assignments, answers, its being met), its Turn,
        its form, and the replies that answered it."""
        cv = self.cv
        state = cv.expectation_state(act["id"])
        under = {act["id"]}
        for ref in (act.get("turn"), (act.get("detail") or {}).get("form"),
                    state.get("turn")):
            if ref:
                under.add(ref)
        for a in cv._own_acts(act["id"]):
            under.add(a["id"])
        under.update(r for r in state.get("replies_from_expected") or () if r)
        return state, under

    def _beside(self, read):
        """`read()` beside the writer: committed state, without the writer's
        lock -- it never writes (review: every statement of a rebuild queued
        behind agents' writes). Read again under the lock only if something
        in it tried to write, as every scoped read does."""
        from mentis.spine.store import (beside_writer_refused,
                                        reading_beside_writer)
        try:
            with reading_beside_writer():
                got = read()
        except Exception:                                 # noqa: BLE001
            if not beside_writer_refused():
                raise
        if beside_writer_refused():
            return read()
        return got

    def _build(self, why):
        cv = self.cv
        started = time.time()       # windows are measured from here (review)
        self._pass_observed_at = time.monotonic()
        runtime, rtsig = self._observed()

        def read():
            with cv.reading():
                advance = cv._c._store.advance()
                trunks = wo._trunks(cv, self.cid)
                cv._prefetch_lineage([a["id"] for a in trunks], acts=trunks)
                ctx = _Reading(cv)
                items, deps, git, place, below, rt = {}, {}, set(), {}, {}, set()
                for a in trunks:
                    (items[a["id"]], deps[a["id"]], used, place[a["id"]],
                     below[a["id"]], moves) = self._project(ctx, a, runtime)
                    if used:
                        git.add(a["id"])
                    if moves:
                        rt.add(a["id"])
                states, sdeps = self._obligations_all()
                found = wo._found_ids(cv)
                viewer = wo.owner_of(cv)
            return (advance, trunks, items, deps, git, place, below, rt,
                    states, sdeps, found, viewer)
        (advance, trunks, items, deps, git, place, below, rt, states, sdeps,
         found, viewer) = self._beside(read)
        due = {tid: _window(it, started) for tid, it in items.items()}
        old = self._model
        self._model = _Model(cursor_text(advance), items,
                             {a["id"]: a for a in trunks}, deps, started, due,
                             git, started, place=place, below=below, rt=rt,
                             runtime=runtime, rtsig=rtsig, viewer=viewer,
                             states=states, sdeps=sdeps, found=found)
        self.stats["builds"] += 1
        self.stats["rebuilt_because"][why] = (
            self.stats["rebuilt_because"].get(why, 0) + 1)
        return old

    def _obligations_all(self):
        """Every expectation's state and what it read, in write order, read
        a causal level at a time (`_prefetch_lineage`) as `expectations`
        reads them. Inside the caller's reading."""
        cv = self.cv
        rows = cv._expectation_acts(self.cid)
        cv._prefetch_lineage([a["id"] for a in rows],
                             through_expectations=False, acts=rows)
        states, sdeps = {}, {}
        for a in rows:
            states[a["id"]], sdeps[a["id"]] = self._obligation(a)
        self.stats["obligations"] += len(rows)
        return states, sdeps

    @staticmethod
    def _time_dependent(model):
        """Items whose stage may have moved with no write (`_window`)."""
        return {t for t, until in model.due.items() if until is not None}

    def _update(self):
        cv, model = self.cv, self._model
        store = cv._c._store
        now = time.time()
        self._pass_observed_at = time.monotonic()
        runtime, rtsig = self._observed()
        # THE CURSOR IS TAKEN FIRST. Rows read after it may run past it; the
        # next update reads them again, which projects those items again --
        # never one missed.
        advance, got = self._beside(lambda: (
            store.advance(),
            store.since(parse_cursor(model.cursor), CAP, acts_in_full=True)))
        if got is None:
            self._build("gap")
            return
        entries, acts, delivered = got
        timed = self._time_dependent(model)
        git_due = now - model.git_at >= GIT_S and bool(model.git)
        observed = rtsig != model.rtsig
        if not (entries or acts or delivered or timed or git_due or observed):
            return
        reach, sreach = model.reach(), model.sreach()
        touched = set(timed) | (set(model.git) if git_due else set())
        owed = set()                      # expectations whose state may move
        if observed:
            # WHAT THIS PROCESS OBSERVES MOVED: every item a run with no end
            # is under, and the work and obligations a handle that came or
            # went names -- a handle naming no request, those its carrier
            # holds in its Conversation (`expectation_state`'s third source).
            if rtsig[:3] != model.rtsig[:3]:
                touched |= set(model.rt)
            for _ref, exp, who, conv in set(rtsig[3]) ^ set(model.rtsig[3]):
                named = {exp} if exp else {
                    e for e, s in model.states.items()
                    if s["conversation"] == conv and s["expected_of"] == who}
                owed |= named
                for e in named:
                    touched |= reach.get(e, set())

        def place(*refs):
            for ref in refs:
                if ref:
                    touched.update(reach.get(ref, ()))
                    owed.update(sreach.get(ref, ()))

        for eid, kind, frm, to, rel in entries:
            k = kind or rel
            # A NEW VERSION OF A TURN (an edit, a deletion) changes only the
            # items and obligations that read it -- none, if none did; any
            # other supersession -- a Conversation renamed, governed
            # material -- rebuilds.
            if rel in ("supersedes", "deletes"):
                if to in reach or to in sreach:
                    place(to)
                    continue
                target = cv._entry(to) if to else []
                if target and cv._kind_of(target[0]) == "contribution":
                    continue
                self._build(f"entry {k}")
                return
            if k in REBUILDS or k not in PLACED:
                self._build(f"entry {k}")
                return
            place(eid, frm, to)
        new_trunk = False
        found = model.found
        for a in acts:
            place(a.get("caused_by"), a["id"], a.get("turn"),
                  a.get("execution"), *(a.get("about") or ()))
            if a["act"] == "expectation-recorded" and (
                    self.cid is None or a.get("conversation") == self.cid):
                new_trunk = True
                owed.add(a["id"])
            if a["act"] == "work-delegated":
                # WHAT IS A TRUNK CAN CHANGE: an expectation handed on under
                # another stops being one (`work_overview._trunks`).
                new_trunk = True
            if a["act"] == "work-discovered" and a.get("about"):
                found = found | set(a["about"])
        for _conversation, execution in delivered:
            touched |= reach.get(execution, set())

        def read():
            trunks = dict(model.trunks)
            with cv.reading():
                hit = set(touched)
                if new_trunk:
                    now_trunks = {a["id"]: a for a in wo._trunks(cv, self.cid)}
                    hit |= set(now_trunks) ^ set(trunks)
                    trunks = now_trunks
                ids = [t for t in hit if t in trunks]
                cv._prefetch_lineage(ids, acts=[trunks[t] for t in ids])
                ctx = _Reading(cv)
                got = {t: self._project(ctx, trunks[t], runtime) for t in ids}
                exps = [a for a in cv._c.operational(id=sorted(owed))
                        if a["act"] == "expectation-recorded"
                        and (self.cid is None
                             or a.get("conversation") == self.cid)
                        ] if owed else []
                cv._prefetch_lineage([a["id"] for a in exps],
                                     through_expectations=False, acts=exps)
                obliged = {a["id"]: self._obligation(a) for a in exps}
            return trunks, ids, got, obliged
        trunks, ids, got, obliged = self._beside(read)
        items, deps, due, git = (dict(model.items), dict(model.deps),
                                 dict(model.due), set(model.git))
        place_, below, rt = dict(model.place), dict(model.below), set(model.rt)
        for tid in set(items) - set(trunks):
            for kept in (items, deps, due, place_, below):
                kept.pop(tid, None)
            git.discard(tid)
            rt.discard(tid)
        for tid, (item, under, used, placed, acts_below, moves) in got.items():
            items[tid], deps[tid] = item, under
            place_[tid], below[tid] = placed, acts_below
            due[tid] = _window(item, now)
            (git.add if used else git.discard)(tid)
            (rt.add if moves else rt.discard)(tid)
        states, sdeps = model.states, model.sdeps
        if obliged:
            states, sdeps = dict(states), dict(sdeps)
            for eid, (state, under) in obliged.items():
                states[eid], sdeps[eid] = state, under
            new = [a["id"] for a in acts if a["id"] in obliged
                   and a["id"] not in model.states]
            if new:
                # IN WRITE ORDER, as `expectations` lists them: the new ones
                # are the newest, in the order they were written
                states = {**{e: s for e, s in states.items()
                             if e in model.states},
                          **{e: states[e] for e in new}}
        self._model = _Model(cursor_text(advance), items, trunks, deps,
                             model.built_at, due, git,
                             now if git_due else model.git_at,
                             place=place_, below=below, rt=rt,
                             runtime=runtime, rtsig=rtsig,
                             viewer=model.viewer, states=states, sdeps=sdeps,
                             found=found)
        self.stats["updates"] += 1
        self.stats["projected"] += len(ids)
        self.stats["obligations"] += len(obliged)

    def refresh(self, *, wait: bool = False) -> None:
        """Bring the model to the record now. Without `wait`, a reader that
        finds an update under way goes on with the model as it stands.

        A FAILED UPDATE IS NOT RETRIED AS AN UPDATE: the next refresh rebuilds
        from the record, and the failure is kept (`failed`) and said to every
        reader until a refresh succeeds (review: one failing update froze
        the model, silently)."""
        if self._model is None:
            wait = True                 # nothing to answer from yet
        if not self._updating.acquire(blocking=wait):
            return
        try:
            if self._model is None:
                self._build("first")
            elif self._broken:
                self._build("after a failure")
            elif time.time() - self._model.built_at >= RECONCILE_S:
                self.reconcile(_held=True)
            else:
                self._update()
            self._broken, self.failed = False, None
            self._observed_at = getattr(self, "_pass_observed_at",
                                        self._observed_at)
        except Exception as exc:
            self._broken = True
            self.failed = f"{type(exc).__name__}: {exc}"
            self.stats["failures"] += 1
            raise
        finally:
            self._updating.release()

    def reconcile(self, *, _held: bool = False) -> list[str]:
        """Rebuild in full and say which items differed from what was kept.
        Every difference is counted: none is expected."""
        if not _held:
            self._updating.acquire()
        try:
            kept = self._model
            if kept is not None and not self._broken:
                try:
                    self._update()           # the kept model, brought up to now
                    kept = self._model
                except Exception:                         # noqa: BLE001
                    kept = None              # rebuilt below; nothing to compare
            self._build("reconcile")
            now = self._model
            if kept is None:
                return []
            differ = sorted(t for t in set(kept.items) | set(now.items)
                            if _canon(kept.items.get(t))
                            != _canon(now.items.get(t)))
            # AND EVERY OBLIGATION, said as `owed:<expectation>`
            differ += sorted(f"owed:{e}" for e in
                             set(kept.states) | set(now.states)
                             if _canon(kept.states.get(e))
                             != _canon(now.states.get(e)))
            self.stats["reconciled"] += 1
            self.stats["reconcile_differences"] += len(differ)
            return differ
        finally:
            if not _held:
                self._updating.release()

    # -- reading ------------------------------------------------------------

    def current(self, *, wait: bool = False, wait_s: float | None = None
                ) -> _Model:
        """The model, brought up to the record as it stood when asked.

        MAINTAINED (`start`): the maintainer is asked to catch up and this
        waits for it at most `wait_s` (until it has, with `wait`), then
        answers from the model as it stands -- `standing` says how that model
        stands against the record. Before the first build has finished,
        `NotReady`, at once (with `wait`, after it). A maintainer that has
        stopped is started again; a request never builds the model (review).
        UNMAINTAINED (a CLI, a test): brought up to date here, in the caller.
        """
        if self._thread is not None and not self._thread.is_alive():
            self._thread = None
            self.start()
        if self._thread is None:
            self.refresh(wait=wait)
            return self._model
        target = parse_cursor(cursor_text(self.cv._c._store.advance()))
        # AND WHAT THIS PROCESS OBSERVES OF RUNS NOW, which moves with no
        # write: caught up is caught up with both.
        asked_at = time.monotonic()
        observed = self._observed()[1] if self.observe is not None else None
        self._wanted.set()
        if self._model is None and not wait:
            raise NotReady(
                "current work is still being prepared after this Mentis "
                "started; ask again shortly" if self.failed is None else
                f"current work could not be prepared: {self.failed}")
        limit = WAIT_S if wait_s is None else wait_s
        deadline = None if wait else time.monotonic() + limit
        with self._moved:
            while not self._caught_up(target, observed, asked_at):
                left = None if deadline is None else deadline - time.monotonic()
                if left is not None and left <= 0:
                    break
                self._moved.wait(left)
        return self._model

    def standing(self, model, cid=None) -> dict | None:
        """HOW THIS ANSWER STANDS, said only when it is not current: the
        record has moved past the model (`behind`), the last refresh failed
        (`failed`), and the work recorded since the model's cursor, here,
        that it does not hold yet (`recorded_since`) -- so newly recorded work
        is never missing without a word (review). None when current."""
        store = self.cv._c._store
        now = store.advance()
        behind = any(a > b for a, b in zip(now, parse_cursor(model.cursor)))
        if not behind and self.failed is None:
            return None
        out = {"as_of": model.cursor, "record_at": cursor_text(now),
               "behind": behind, "failed": self.failed}
        got = store.since(parse_cursor(model.cursor), CAP, acts_in_full=True)
        if got is not None:
            out["recorded_since"] = [
                {"expectation": a["id"], "turn": a.get("turn"),
                 "conversation": a.get("conversation")}
                for a in got[1] if a["act"] == "expectation-recorded"
                and a["id"] not in model.items
                and (cid is None or a.get("conversation") == cid)
                # ONLY WORK OF ITS OWN, by the overview's own rule: not a
                # delegated child, a decision or an input (re-review)
                and _is_trunk(self.cv, a)]
        return out

    def _caught_up(self, target, observed=None, asked_at=None) -> bool:
        """At the record as it stood when asked, and -- with `observed` --
        having observed the runs as they were then: the same signature, or
        a pass that observed them after the ask (a signature that keeps
        moving is never waited out)."""
        m = self._model
        return m is not None and all(
            a >= b for a, b in zip(parse_cursor(m.cursor), target)) and (
            observed is None or m.rtsig == observed
            or (asked_at is not None and self._observed_at >= asked_at))

    def start(self) -> None:
        """Keep the model on a thread of its own: built now, then brought up
        to date whenever a reader asks or `MAINTAIN_S` passes. No request
        builds or updates it."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._maintain, daemon=True,
                                        name="current-work")
        self._thread.start()

    def _maintain(self) -> None:
        import traceback
        while True:
            try:
                self.refresh(wait=True)
            except BaseException:                         # noqa: BLE001
                # KEPT IN `failed` and said to readers (`standing`, NotReady);
                # the next refresh rebuilds. Printed where there is somewhere
                # to print it.
                try:
                    traceback.print_exc()
                except Exception:                         # noqa: BLE001
                    pass
                time.sleep(5)
            with self._moved:
                self._moved.notify_all()
            self._wanted.wait(MAINTAIN_S)
            self._wanted.clear()


_MODELS: dict = {}
_MODELS_LOCK = threading.Lock()


def current_work(cv, *, observe=None) -> CurrentWork:
    """The one kept model of this record in this process: the Brain's.
    A Conversation's current work is `model.of(conversation)`.

    THE SERVER'S OWN, WHEN IT ASKS (`observe`): what this process observes
    of runs, and the Conversations object whose executions it holds -- a
    worker's `Surface` opens another over the same store, which holds none
    -- so the model projects what the server's routes always read. Either
    object reads the same record; only the executions held differ."""
    store = cv._c._store
    key = id(store)
    with _MODELS_LOCK:
        got = _MODELS.get(key)
        if got is None or got.cv._c._store is not store:
            got = _MODELS[key] = CurrentWork(cv, None)
        if observe is not None:
            got.cv, got.observe = cv, observe
        return got


def forget() -> None:
    """Drop every kept model (tests; a model is only ever derived)."""
    with _MODELS_LOCK:
        _MODELS.clear()


def _is_trunk(cv, act) -> bool:
    """`work.is_trunk`; an act whose standing cannot be read is listed, as
    the overview lists unreadable work rather than dropping it."""
    from mentis.operational.work import is_trunk
    try:
        return is_trunk(cv, act)
    except Exception:                                     # noqa: BLE001
        return True
