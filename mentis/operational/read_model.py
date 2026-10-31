"""THE READ MODEL: one interface to the state Mentis derives from its record.

FROZEN AT STAGE 1. Every reader of derived state -- the work and obligation
routes now, the composer lookup, `find`, orientation and the change feed as
they move onto it -- asks `ReadModel`, never a projection of its own. Stage 3
implements this same interface as an embedded Rust crate (`mentis-index`)
and dual-runs it against `PythonReadModel` until the two agree, so what is
written here is the contract that crate is held to. A method is added to it
only with a contract as precise as these; none is changed in place.

WHAT IT IS NOT. Not a second record, and never authority: everything it
answers is derived from `corpus.db` and replaced by deriving it again. It
writes nothing. Governance, grants and the append path are not here.

POSITIONS. The record's position is a CURSOR, "<entry>.<operational>.
<delivery>": the highest `seq` of each append-only table a reading has seen
(`Store.advance`, `current_work.cursor_text`). Cursors compare per table.

FRESHNESS, said per method:
  * KEPT (`work_items`, `owed`): answered from a model kept on a thread of
    its own (`current_work.CurrentWork`) and updated from the record's tail.
    A call asks it to catch up with the record as it stood when the call was
    made, waits at most `current_work.WAIT_S` for that, and answers from the
    model as it then stands. `as_of` is the cursor the answer is at, and
    `standing` is None when that is the record's position and the last
    update succeeded -- otherwise it says how far behind, why, and which
    work was recorded since that the answer does not hold yet. Before the
    first build after a start, a call waits for that build.
  * READ (`stands_many`, `conversation_summary`, `topics`, `find`): read
    from the record at the call, as of the moment they run.
  * TAILED (`since`): the rows written after a cursor, exactly.

SCOPE. `Scope(conversation=, participant=)`: what part of the Brain a call
is about. Unset fields do not narrow. Each method says which fields it
reads; a field it does not read is ignored, never an error.

The shapes returned are the ones the HTTP routes already serve (the Work
Overview contract v1 for a WorkItem, `expectation_state` for an obligation),
so moving a consumer onto this changes no response.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol, runtime_checkable

from mentis.operational import current_work as cw


@dataclass(frozen=True)
class Scope:
    """What part of the Brain a call is about. None does not narrow."""

    conversation: str | None = None
    participant: str | None = None


@dataclass(frozen=True)
class WorkItems:
    """Every piece of work (a TRUNK, `work.is_trunk`) in a scope, as one
    moment of the kept model.

    order    trunk ids, in the order the record wrote their requests.
    trunks   id -> its `expectation-recorded` act.
    items    id -> its WorkItem, exactly as `work_overview.project` words it
             for `viewer` with `runtime`: contract v1 (`ui/src/work/
             contract.ts`), stage fields included. Shared: never mutate one;
             `item(id)` gives a copy carrying the placing fields.
    place    id -> (`_seen`, `_awaits`): what was observed of its open runs
             and what the work it waits on is doing -- what places it in a
             scoped read (`work_overview._scoped_group`), never sent.
    below    id -> the acts under it, as its projection walked them
             (`work_overview._in_scope` reads them).
    states   expectation id -> `expectation_state`, Brain-wide: what is
             owed and what is met (`_in_scope`).
    found    requests kept as discovered work (`work-discovered`).
    viewer   whom the items were projected for: the record's owner
             (`work_overview.owner_of`), None where it names none.
    runtime  the run observation they were projected with
             (`web._runtime_observation`'s shape).
    as_of, standing   see FRESHNESS.
    """

    as_of: str
    viewer: str | None
    runtime: Mapping
    order: tuple
    trunks: Mapping[str, dict]
    items: Mapping[str, dict]
    place: Mapping[str, tuple]
    below: Mapping[str, list]
    states: Mapping[str, dict]
    found: frozenset
    standing: dict | None = None

    def item(self, tid) -> dict:
        """A copy of one WorkItem with its placing fields, as a projection
        returns it before they are dropped."""
        seen, awaits = self.place.get(tid, (None, None))
        return {**self.items[tid], "_seen": seen, "_awaits": awaits}


@dataclass(frozen=True)
class Owed:
    """What is owed in a scope: every expectation nobody has answered.

    rows   `expectation_state` of each, in the order the record wrote the
           requests (oldest first). Shared: never mutate one.
    as_of, standing   see FRESHNESS."""

    as_of: str
    rows: tuple
    standing: dict | None = None


@dataclass(frozen=True)
class Found:
    """What `find` found, and what it did not search.

    found          the hits, best first (`Surface.find`'s rows, `limit` of
                   them), each with `what` among `kinds`.
    matched        how many hits there were before `limit`.
    not_searched   what the search did not read and why -- files whose text
                   could not be read or is still being made -- exactly as the
                   content scan reports it. Empty is a claim that everything
                   in scope was read.
    pending        of those, the ones still being made (asked again later,
                   they are searched).
    kinds          the kinds searched; a kind not listed was not searched.
    """

    found: tuple
    matched: int
    not_searched: tuple
    pending: tuple
    kinds: tuple


@dataclass(frozen=True)
class Changes:
    """The rows written after a cursor (`Store.since`).

    cursor     the record's position taken BEFORE the rows were read: every
               row up to it is here, and a row written after it may be too
               -- the next call, from this cursor, gives it again. Never one
               missed; one may be given twice.
    entries    (id, kind, link_from, link_to, link_relation) per entry.
    acts       each act in full, as `operational` gives it.
    delivered  (conversation, execution) per delivery.
    """

    cursor: str
    entries: tuple
    acts: tuple
    delivered: tuple


#: The kinds `find` searches, as `Surface.find` names its hits.
FIND_KINDS = ("entry", "turn", "participant", "conversation", "topic", "link",
              "block", "acquired")


@runtime_checkable
class ReadModel(Protocol):
    """THE FROZEN INTERFACE. See the module docstring for freshness."""

    def work_items(self, scope: Scope = Scope()) -> WorkItems:
        """Every piece of work in `scope.conversation` (the Brain's, unset),
        as the kept model holds it. `scope.participant` is not read: items
        are projected for the record's owner, and what anybody else owes is
        `owed`. KEPT."""

    def owed(self, scope: Scope = Scope()) -> Owed:
        """Every expectation nobody has answered, carried now by
        `scope.participant` (`assigned_carrier`) and recorded in
        `scope.conversation`, where set. Being addressed is not owing. KEPT."""

    def stands_many(self, ids: Iterable[str]) -> dict:
        """id -> whether that entry stands now: established, and nothing that
        still counts supersedes it (`Seam.stands`). None for an id the
        record does not hold. READ."""

    def conversation_summary(self, ids: Iterable[str]) -> dict:
        """id -> the Conversations list's row for it
        (`Conversations.conversation_summaries`: name, about, Turns, last
        activity, participants, Topics, awaiting, live runs). An id that is
        not a Conversation is absent. READ."""

    def topics(self, q: str) -> list:
        """The Topics whose name contains `q`, case-folded, leading `#`
        ignored: `{id, name, conversation}` each, in the order the
        Conversations and their Topics are listed. Topics only: a fast
        existence check for the composer, never a text search. READ."""

    def find(self, q: str, kinds: Iterable[str] | None = None,
             scope: Scope = Scope(), *, limit: int = 12) -> Found:
        """Everything `q` names or mentions, of `kinds` (all of FIND_KINDS,
        unset): exact identity and Turn-number hits first, then names, then
        Turns, then acquired material by name and by content.
        `scope.conversation` decides a bare Turn number and is offered first;
        it never filters. What was not searched is said (`Found`). READ."""

    def since(self, seq: str) -> Changes | None:
        """The rows written after cursor `seq`. None when more than
        `current_work.CAP` rows of a table came after it, or the record is
        not at or past it: the caller then treats everything as moved.
        TAILED."""


class PythonReadModel:
    """`ReadModel` over the existing Python readers: the kept current-work
    model for work and obligations, and the record's own readers for the
    rest. What Stage 3's Rust crate is checked against."""

    def __init__(self, cv, *, observe=None, surface=None):
        self.cv = cv
        self._kept = cw.current_work(cv, observe=observe)
        self._surface = surface

    # -- kept ------------------------------------------------------------

    def _model(self):
        try:
            return self._kept.current()
        except cw.NotReady:
            # THE FIRST BUILD AFTER A START is under way on its own thread:
            # a route waits for it rather than answering nothing
            return self._kept.current(wait=True)

    def work_items(self, scope: Scope = Scope()) -> WorkItems:
        model = self._model()
        cid = scope.conversation
        trunks = {t: a for t, a in model.trunks.items()
                  if cid is None or a.get("conversation") == cid}
        return WorkItems(
            as_of=model.cursor, viewer=model.viewer, runtime=model.runtime,
            order=tuple(trunks), trunks=trunks,
            items={t: model.items[t] for t in trunks},
            place=model.place, below=model.below, states=model.states,
            found=frozenset(model.found),
            standing=self._kept.standing(model, cid))

    def owed(self, scope: Scope = Scope()) -> Owed:
        model = self._model()
        return Owed(as_of=model.cursor,
                    rows=tuple(model.owed(participant=scope.participant,
                                          conversation=scope.conversation)),
                    standing=self._kept.standing(model, scope.conversation))

    # -- read --------------------------------------------------------------

    def stands_many(self, ids: Iterable[str]) -> dict:
        corpus = self.cv.corpus
        out = {}
        for i in dict.fromkeys(ids):
            out[i] = (corpus.stands(i)["stands"] if corpus.read([i])
                      else None)
        return out

    def conversation_summary(self, ids: Iterable[str]) -> dict:
        want = set(ids)
        live = self.cv.active_executions()
        return {r["id"]: r for r in self.cv.conversation_summaries(live)
                if r["id"] in want}

    def topics(self, q: str) -> list:
        needle = (q or "").strip().lower().lstrip("#")
        if not needle:
            return []
        out = []
        for c in self.cv.all_conversations():
            for t in self.cv.topics(c["id"]):
                if needle in t["body"]["name"].lower():
                    out.append({"id": t["id"], "name": t["body"]["name"],
                                "conversation": c["id"]})
        return out

    def find(self, q: str, kinds: Iterable[str] | None = None,
             scope: Scope = Scope(), *, limit: int = 12) -> Found:
        from mentis.worker import Surface
        surface = self._surface or Surface(self.cv.corpus.root,
                                           corpus=self.cv.corpus)
        kinds = tuple(FIND_KINDS if kinds is None else kinds)
        got = surface.find(q, limit=10 ** 6, here=scope.conversation)
        rows = [r for r in got.get("found", ()) if _kind_of(r) in kinds]
        return Found(found=tuple(rows[:limit]), matched=len(rows),
                     not_searched=tuple(got.get("not_searched") or ()),
                     pending=tuple(got.get("pending") or ()), kinds=kinds)

    # -- tailed ------------------------------------------------------------

    def since(self, seq: str) -> Changes | None:
        store = self.cv._c._store
        at = cw.parse_cursor(seq)
        if at is None:
            raise ValueError(f"not a cursor: {seq!r}")
        now = store.advance()
        got = store.since(at, cw.CAP, acts_in_full=True)
        if got is None:
            return None
        entries, acts, delivered = got
        return Changes(cursor=cw.cursor_text(now), entries=tuple(entries),
                       acts=tuple(acts), delivered=tuple(delivered))


def _kind_of(row) -> str:
    """A `Surface.find` row's kind, as FIND_KINDS names it."""
    if row.get("matched") == "content" or str(row.get("ref", "")).startswith(
            "adm-"):
        return "acquired"
    what = row.get("what")
    return what if what in FIND_KINDS else "entry"


def read_model(st) -> PythonReadModel:
    """The server's read model: the kept model of its record, observing the
    runs this server holds (`web._runtime_observation`)."""
    from mentis.web import _runtime_observation
    got = getattr(st, "_read_model", None)
    if (got is None or got.cv is not st.cv
            or got._kept is not cw.current_work(st.cv)):
        # the server's own observation, whoever asked for the model first
        got = st._read_model = PythonReadModel(
            st.cv, observe=lambda: _runtime_observation(st))
    return got
