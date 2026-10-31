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
  * REBUILT whole when a write cannot be placed that way: governed material,
    participants, definitions, a gap longer than `CAP`, or a record that is not
    at or past the cursor. And reconciled -- rebuilt and compared -- every
    `RECONCILE_S`.
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

#: Kinds that are written as a Conversation's own material. Anything else --
#: governed material, participants, Personas, definitions -- rebuilds.
from mentis.web.moved import CONVERSATION_MATERIAL, PEOPLE  # noqa: E402

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

    def descendants(self, expectation):
        self.read.add(expectation)
        return super().descendants(expectation)

    def state(self, expectation):
        self.read.add(expectation)
        return super().state(expectation)


class _Model:
    """One immutable moment of the read model; replaced, never edited."""

    __slots__ = ("cursor", "items", "trunks", "deps", "built_at", "due",
                 "_reach")

    def __init__(self, cursor, items, trunks, deps, built_at, due):
        # `cursor`: the record's position this model was brought up to --
        # where its next update reads from. `due`: per item, until when its
        # stage may still move with no write (see `_window`).
        self.cursor, self.items = cursor, items
        self.trunks, self.deps, self.built_at = trunks, deps, built_at
        self.due = due
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


class CurrentWork:
    """The kept current work of one Conversation (`cid`), or the Brain's."""

    def __init__(self, cv, cid=None):
        self.cv, self.cid = cv, cid
        self._updating = threading.Lock()
        self._model: _Model | None = None
        self._thread = None
        self.failed: str | None = None      # the maintainer's last failure
        self._wanted = threading.Event()
        self._moved = threading.Condition()
        self.stats = {"builds": 0, "updates": 0, "projected": 0,
                      "reconciled": 0, "reconcile_differences": 0,
                      "rebuilt_because": {}}

    # -- projecting ---------------------------------------------------------

    def _project(self, ctx, act):
        """One item, and everything it read. ITS OWN MOTION: what awaited
        work is doing is worked out again for each item, never taken from an
        earlier item's answer, or this item would depend on work without
        having read it (review: two trunks awaiting the same work)."""
        viewer = wo.owner_of(self.cv)
        ctx.read, ctx.motion, ctx.visiting = set(), {}, set()
        item = wo.project(ctx, act, viewer=viewer, runtime=RUNTIME)
        item.pop("_seen", None)
        item.pop("_awaits", None)
        under = {act["id"]}
        if act.get("turn"):
            under.add(act["turn"])
        for e in ctx.read:
            under.add(e)
            own = self.cv._act(e)
            if own and own.get("turn"):
                under.add(own["turn"])
            for a in ctx.descendants(e):
                under.add(a["id"])
                if a.get("turn"):
                    under.add(a["turn"])
                if a.get("execution"):
                    under.add(a["execution"])
        return item, under

    def _build(self, why):
        cv = self.cv
        with cv.reading():
            advance = cv._c._store.advance()
            trunks = wo._trunks(cv, self.cid)
            cv._prefetch_lineage([a["id"] for a in trunks], acts=trunks)
            ctx = _Reading(cv)
            items, deps = {}, {}
            for a in trunks:
                items[a["id"]], deps[a["id"]] = self._project(ctx, a)
        now = time.time()
        due = {tid: _window(it, now) for tid, it in items.items()}
        old = self._model
        self._model = _Model(cursor_text(advance), items,
                             {a["id"]: a for a in trunks}, deps, now, due)
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
        # THE CURSOR IS TAKEN FIRST. Rows read after it may run past it; the
        # next update reads them again, which projects those items again --
        # never one missed.
        advance = store.advance()
        got = store.since(parse_cursor(model.cursor), CAP, acts_in_full=True)
        if got is None:
            self._build("gap")
            return
        entries, acts, delivered = got
        timed = self._time_dependent(model)
        if not (entries or acts or delivered or timed):
            return
        reach = model.reach()
        touched = set(timed)
        for eid, kind, frm, to, rel in entries:
            k = kind or rel
            # BRINGING SOMEONE INTO A CONVERSATION changes no item -- an item
            # names people by their participant entry, whose renames still
            # rebuild -- and every delegation writes one: placed, not rebuilt
            # (15 of 18 rebuilds replaying 2026-10-30 22:00 onward).
            if k == "participates-in":
                for ref in (eid, frm, to):
                    touched |= reach.get(ref, set())
                continue
            # A NEW VERSION OF A TURN AN ITEM READ (an edit, a deletion)
            # changes only the items that read it; any other supersession --
            # a Conversation renamed, governed material -- rebuilds.
            if rel in ("supersedes", "deletes") and to in reach:
                touched |= reach[to]
                continue
            if k in PEOPLE or k not in CONVERSATION_MATERIAL:
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
        trunks = dict(model.trunks)
        with cv.reading():
            if new_trunk:
                now_trunks = {a["id"]: a for a in wo._trunks(cv, self.cid)}
                touched |= set(now_trunks) ^ set(trunks)
                trunks = now_trunks
            ids = [t for t in touched if t in trunks]
            cv._prefetch_lineage(ids, acts=[trunks[t] for t in ids])
            ctx = _Reading(cv)
            items, deps, due = (dict(model.items), dict(model.deps),
                                dict(model.due))
            for tid in set(items) - set(trunks):
                items.pop(tid, None)
                deps.pop(tid, None)
                due.pop(tid, None)
            now = time.time()
            for tid in ids:
                items[tid], deps[tid] = self._project(ctx, trunks[tid])
                due[tid] = _window(items[tid], now)
        self._model = _Model(cursor_text(advance), items, trunks, deps,
                             model.built_at, due)
        self.stats["updates"] += 1
        self.stats["projected"] += len(ids)

    def refresh(self, *, wait: bool = False) -> None:
        """Bring the model to the record now. Without `wait`, a reader that
        finds an update under way goes on with the model as it stands."""
        if self._model is None:
            wait = True                 # nothing to answer from yet
        if not self._updating.acquire(blocking=wait):
            return
        try:
            if self._model is None:
                self._build("first")
            elif time.time() - self._model.built_at >= RECONCILE_S:
                self.reconcile(_held=True)
            else:
                self._update()
        finally:
            self._updating.release()

    def reconcile(self, *, _held: bool = False) -> list[str]:
        """Rebuild in full and say which items differed from what was kept.
        Every difference is counted: none is expected."""
        if not _held:
            self._updating.acquire()
        try:
            kept = self._model
            if kept is not None:
                self._update()               # the kept model, brought up to now
                kept = self._model
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
        answers from the model as it stands -- its `cursor` says which moment
        that is. Before the first build has finished, `NotReady`, at once
        (with `wait`, after it). UNMAINTAINED (a CLI, a test): brought up to
        date here, in the caller."""
        if self._thread is None or not self._thread.is_alive():
            # UNMAINTAINED, OR THE MAINTAINER HAS STOPPED: brought up to date
            # here rather than answered from a model that no longer moves
            # (review)
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
                self.failed = None
            except Exception as exc:                      # noqa: BLE001
                # SAID, AND TRIED AGAIN: readers are answered from the model
                # as it stood, with its cursor, meanwhile -- and told why
                # there is none, if there is none.
                self.failed = f"{type(exc).__name__}: {exc}"
                try:
                    traceback.print_exc()
                except Exception:                         # noqa: BLE001
                    pass                                  # no stderr to say it on
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
