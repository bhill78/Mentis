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
Its readers: `work_overview` and `brief` (`orientation.outstanding`).
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


def _canon(item) -> str:
    return json.dumps(item, sort_keys=True, default=str)


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
                 "git_at", "_reach")

    def __init__(self, cursor, items, trunks, deps, built_at, due, git,
                 git_at):
        # `cursor`: the record's position this model was brought up to --
        # where its next update reads from. `due`: per item, until when its
        # stage may still move with no write (see `_window`). `git`: items
        # whose stage asked git, projected again every `GIT_S` (`git_at`).
        self.cursor, self.items = cursor, items
        self.trunks, self.deps, self.built_at = trunks, deps, built_at
        self.due, self.git, self.git_at = due, git, git_at
        self._reach = None

    def reach(self) -> dict:
        """Every act, Turn and execution an item read -> those items."""
        if self._reach is None:
            got = {}
            for tid, under in self.deps.items():
                for ref in under:
                    got.setdefault(ref, set()).add(tid)
            self._reach = got
        return self._reach

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
                      "conversation"})

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
    "answer", "response-set", "responds-to", "in-response-set",
    "interpretation", "interpretation-reply", "own-words", "marked-ready",
    "withdraws", "timer-mark", "proposes", "proposes-to-supersede",
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
        self.stats = {"builds": 0, "updates": 0, "projected": 0,
                      "reconciled": 0, "reconcile_differences": 0,
                      "failures": 0, "rebuilt_because": {}}

    # -- projecting ---------------------------------------------------------

    def _project(self, ctx, act):
        """One item, and everything it read. ITS OWN MOTION: what awaited
        work is doing is worked out again for each item, never taken from an
        earlier item's answer, or this item would depend on work without
        having read it (review: two trunks awaiting the same work)."""
        cv = self.cv
        viewer = wo.owner_of(cv)
        ctx.read, ctx.motion, ctx.visiting = set(), {}, set()
        ctx.git_used = False
        item = wo.project(ctx, act, viewer=viewer, runtime=RUNTIME)
        item.pop("_seen", None)
        item.pop("_awaits", None)
        # EVERYTHING THIS ITEM'S WORK HAS EVER AWAITED, ended or not. The
        # projection reads awaited work directly (`awaited_state`) and only
        # while the wait is open, so what it read is not enough: a wait that
        # ended can open again when that work moves again (review blocker).
        mine = [act["id"]] + [a["id"] for a in ctx.descendants(act["id"])
                              if a["act"] == "expectation-recorded"]
        awaited = {w for e in mine for w in cv.awaits(e)}
        under = {act["id"]}
        if act.get("turn"):
            under.add(act["turn"])
        for e in ctx.read | awaited:
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
        return item, under, ctx.git_used

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

        def read():
            with cv.reading():
                advance = cv._c._store.advance()
                trunks = wo._trunks(cv, self.cid)
                cv._prefetch_lineage([a["id"] for a in trunks], acts=trunks)
                ctx = _Reading(cv)
                items, deps, git = {}, {}, set()
                for a in trunks:
                    items[a["id"]], deps[a["id"]], used = self._project(ctx, a)
                    if used:
                        git.add(a["id"])
            return advance, trunks, items, deps, git
        advance, trunks, items, deps, git = self._beside(read)
        due = {tid: _window(it, started) for tid, it in items.items()}
        old = self._model
        self._model = _Model(cursor_text(advance), items,
                             {a["id"]: a for a in trunks}, deps, started, due,
                             git, started)
        self.stats["builds"] += 1
        self.stats["rebuilt_because"][why] = (
            self.stats["rebuilt_because"].get(why, 0) + 1)
        return old

    @staticmethod
    def _time_dependent(model):
        """Items whose stage may have moved with no write (`_window`)."""
        return {t for t, until in model.due.items() if until is not None}

    def _update(self):
        cv, model = self.cv, self._model
        store = cv._c._store
        now = time.time()
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
        if not (entries or acts or delivered or timed or git_due):
            return
        reach = model.reach()
        touched = set(timed) | (set(model.git) if git_due else set())
        for eid, kind, frm, to, rel in entries:
            k = kind or rel
            # A NEW VERSION OF A TURN (an edit, a deletion) changes only the
            # items that read it -- none, if none did; any other supersession
            # -- a Conversation renamed, governed material -- rebuilds.
            if rel in ("supersedes", "deletes"):
                if to in reach:
                    touched |= reach[to]
                    continue
                target = cv._entry(to) if to else []
                if target and cv._kind_of(target[0]) == "contribution":
                    continue
                self._build(f"entry {k}")
                return
            if k in REBUILDS or k not in PLACED:
                self._build(f"entry {k}")
                return
            for ref in (eid, frm, to):
                touched |= reach.get(ref, set())
        new_trunk = False
        for a in acts:
            for ref in (a.get("caused_by"), a["id"], a.get("turn"),
                        a.get("execution"), *(a.get("about") or ())):
                if ref:
                    touched |= reach.get(ref, set())
            if a["act"] == "expectation-recorded" and (
                    self.cid is None or a.get("conversation") == self.cid):
                new_trunk = True
            if a["act"] == "work-delegated":
                # WHAT IS A TRUNK CAN CHANGE: an expectation handed on under
                # another stops being one (`work_overview._trunks`).
                new_trunk = True
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
                got = {t: self._project(ctx, trunks[t]) for t in ids}
            return trunks, ids, got
        trunks, ids, got = self._beside(read)
        items, deps, due, git = (dict(model.items), dict(model.deps),
                                 dict(model.due), set(model.git))
        for tid in set(items) - set(trunks):
            items.pop(tid, None)
            deps.pop(tid, None)
            due.pop(tid, None)
            git.discard(tid)
        for tid, (item, under, used) in got.items():
            items[tid], deps[tid] = item, under
            due[tid] = _window(item, now)
            (git.add if used else git.discard)(tid)
        self._model = _Model(cursor_text(advance), items, trunks, deps,
                             model.built_at, due, git,
                             now if git_due else model.git_at)
        self.stats["updates"] += 1
        self.stats["projected"] += len(ids)

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
        self._wanted.set()
        if self._model is None and not wait:
            raise NotReady(
                "current work is still being prepared after this Mentis "
                "started; ask again shortly" if self.failed is None else
                f"current work could not be prepared: {self.failed}")
        limit = WAIT_S if wait_s is None else wait_s
        deadline = None if wait else time.monotonic() + limit
        with self._moved:
            while not self._caught_up(target):
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
                and (cid is None or a.get("conversation") == cid)]
        return out

    def _caught_up(self, target) -> bool:
        m = self._model
        return m is not None and all(
            a >= b for a, b in zip(parse_cursor(m.cursor), target))

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


def current_work(cv) -> CurrentWork:
    """The one kept model of this record in this process: the Brain's.
    A Conversation's current work is `model.of(conversation)`."""
    store = cv._c._store
    key = id(store)
    with _MODELS_LOCK:
        got = _MODELS.get(key)
        if got is None or got.cv._c._store is not store:
            got = _MODELS[key] = CurrentWork(cv, None)
        return got


def forget() -> None:
    """Drop every kept model (tests; a model is only ever derived)."""
    with _MODELS_LOCK:
        _MODELS.clear()
