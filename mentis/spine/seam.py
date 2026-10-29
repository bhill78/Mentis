"""The spine slice: admission, candidate material, standing, history, delivery.

The engine understands Entries, Definitions at a version, Links, and exactly two
substrate roles. It contains no branch on any Kind or Relation NAME -- standing
and history are computed from the roles a Relation definition declares about
itself, and every other relationship is inert and merely reported.

Permissive by default: nothing here decides whether a caller may do something.
The only refusals are shape refusals, and the only thing a caller cannot express
is a delivery observation, because no seam call takes one.

Storage is SQLite (`store.py`). This layer knows a Store has queries; it holds
no SQL, and nothing above it knows there is a database at all. Reads that used
to scan the whole corpus are indexed lookups now -- the logical model is
unchanged, the physical cost is not.
"""

from __future__ import annotations

import os
import time
import uuid

from mentis.spine import held, seed, store

# Structural families the spine knows by construction.
DEFINITION = "definition"
ADMISSION = "admission"
PARTICIPANT = "participant"
CONVERSATION = "conversation"
ENTRY = "entry"

#: Origin may name a durable thing, or the literal below for a direct human act.
HUMAN = "human"


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Corpus:
    """A corpus at a path the user chose. Nothing is copied anywhere else."""

    def __init__(self, root: str, *, access: str = "auto"):
        self.root = root
        self._store = store.Store(root, access=access)
        # A definition is immutable once written, so an exact (name, version)
        # lookup is cacheable. `current_definition` is NOT cached: a new
        # version may be appended at any moment.
        self._pinned: dict[tuple, dict | None] = {}
        self._role_cache: dict[str, str] = {}
        # NOT THE SAME CACHE, because it may legitimately answer None and a
        # None answer must stay re-askable: a corpus can acquire the
        # declaration later. See `proposal_relation`.
        self._proposing_cache: dict[str, str] = {}
        # A Brain `create_corpus` made, or one whose creation died between
        # its schema commit and this seed. Vocabulary is data, never schema.
        if not self._store.read_only and self._store.count() == 0:
            self._seed()
        from mentis.core.context_cache import revisions_for
        self._store.revisions = revisions_for(self)

    @property
    def context_cache(self):
        from mentis.core.context_cache import cache_for
        return cache_for(self)

    @property
    def revisions(self):
        from mentis.core.context_cache import revisions_for
        return revisions_for(self)

    @property
    def schema_status(self):
        """What the open check found (`mentis.spine.migrations.Status`)."""
        return self._store.status

    @property
    def read_only(self) -> bool:
        return self._store.read_only

    # -- identity and lifecycle ---------------------------------------------

    @property
    def corpus_id(self) -> str:
        """Durable identity, held inside the corpus. The path is a location."""
        return self._store.corpus_id

    def reference(self, entry_id: str) -> str:
        """A reference to one of our entries that survives leaving this corpus."""
        return store.reference(self.corpus_id, entry_id)

    def snapshot(self, path: str) -> dict:
        """One consistent portable copy, safe to take while the corpus is live.

        THE RECORD AND THE BYTES IT HOLDS. `path` is where `corpus.db` goes, and
        every blob a held Admission names goes into the byte store beside it --
        so a snapshot taken into `<dir>/corpus.db` is a corpus at `<dir>`. A
        snapshot of the database alone would be a copy in which every held
        artifact reads as missing.

        Database first, then bytes. Bytes are always written before the
        Admission that names them, so whatever the database copy names was
        already on disk when it was taken. Only bytes that are named by a held
        Admission that is NOT purged, AND present, are copied. A purged
        Admission names nothing to copy, even when its bytes are still on
        disk -- a purge that crashed before its delete, or the same bytes
        staged again since -- and bytes nothing names were never part of the
        record.
        """
        self._store.snapshot(path)
        named = {d for d in (held.digest_of(e["body"].get("locator"))
                             for e in self._store.by_definition(ADMISSION)
                             if e["body"].get("content") == "held"
                             and not self.links(relation=held.PURGED,
                                                to=e["id"])) if d}
        return held.copy(self.root, os.path.dirname(os.path.abspath(path)),
                         named)

    def close(self):
        self._store.close()

    def atomic(self):
        """All-or-nothing across several appends. A nested call joins the outer."""
        return self._store.write()

    # -- seeding ------------------------------------------------------------

    def _seed(self):
        """Bootstrap vocabulary, written with exactly the primitive a caller
        gets. Nothing here is privileged except the substrate roles, which the
        public seam deliberately cannot set."""
        with self.atomic():
            for k in seed.KINDS:
                self._define(k["kind"], dict(k), attributed_to=HUMAN)
            for r in seed.RELATIONS:
                self._define(r["relation"], dict(r), attributed_to=HUMAN)

    # -- definitions, as data through the public seam -----------------------

    def _define(self, name, body, *, attributed_to, written_by=None) -> str:
        """Append the next version of a definition. Never mutates a prior one.

        The engine holds no vocabulary. It holds the rule that a definition has
        a name and a version, and that the version only ever goes up.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("a definition needs a name")
        current = self.current_definition(name)
        version = current["definition"]["version"] + 1 if current else 1
        return self._append(DEFINITION, {"name": name, "version": version},
                            body, attributed_to=attributed_to,
                            written_by=written_by)

    def _family_of(self, name) -> str | None:
        cur = self.current_definition(name)
        if cur is None:
            return None
        return "kind" if "kind" in cur["body"] else "relation"

    def define_kind(self, name, *, fields, properties=None, attributed_to,
                    written_by=None, removing=()) -> str:
        """Define a Kind, or the next version of one. Ordinary permitted work.

        `fields` is the only property the engine reads -- it bounds an entry
        body. Everything in `properties` is carried verbatim and interpreted by
        nobody, which is what keeps Kind metadata descriptive.

        THIS REPLACES, IT DOES NOT MERGE, AND THAT IS NOT CHANGING. A definition
        is a complete statement of what a Kind is, readable whole, rather than an
        accumulation of edits nobody can see the end of. Omitting a property
        therefore removes it.

        WHICH LEAVES ONE THING THAT MUST NOT BE SILENT. For the few declarations
        production actually branches on (`seed.BEHAVIOURAL_PROPERTIES`), omission
        and deletion are the same keystroke and completely different intentions:
        restating `meaning` and forgetting `knowing` takes every placed procedure
        in a Conversation out of delivery, with nothing to see but an empty
        `governs()`. Measured on `conversation-instruction`.
        SO OMISSION OF THOSE IS REFUSED, and deletion is said out loud: name the
        property in `removing`. Absence still means absence afterwards -- nothing
        here infers a value, and a Kind that never declared one is unaffected.
        What is no longer possible is removing one by accident.
        """
        if self._family_of(name) == "relation":
            raise ValueError(f"{name!r} is already defined as a relation")
        if not isinstance(fields, (list, tuple)) or not all(
                isinstance(f, str) for f in fields):
            raise ValueError("fields must be a list of names")
        said = dict(properties or {})
        letting_go = set(removing or ())
        # A VALUE IN NEITHER CHANNEL IS NOT A VALUE. `knowing` has exactly two,
        # and the engine still branches on NOTHING in `properties` -- what it
        # refuses here is a declaration that cannot MEAN anything to the
        # readers above it. `knowing: "banana"`, `""` or `True` was admitted,
        # and material of such a Kind was then selected by neither channel:
        # not propositional, so relevance never considered it; not procedural,
        # so placement never carried it. That is indistinguishable from the
        # Kind declaring nothing -- except that `propose_material` admitted it,
        # `Surface.resolve` qualified it, and the register listed it, each on
        # the strength of a word none of them could read. ABSENCE ALREADY SAYS
        # "in neither ladder", honestly and in one way; a typo must not be a
        # second way of saying it.
        if "knowing" in said and said["knowing"] not in (seed.KNOWING_THAT,
                                                         seed.KNOWING_HOW):
            raise ValueError(
                f"`knowing` on {name!r} must be {seed.KNOWING_THAT!r} (its "
                f"material states something) or {seed.KNOWING_HOW!r} (it "
                f"directs how work is done), or absent entirely. "
                f"{said['knowing']!r} is neither, and material of a Kind "
                f"declaring it would be delivered by no channel at all -- "
                f"which is what ABSENT already says, in one way, on purpose")
        # REMOVING IT AND KEEPING IT ARE NOT BOTH POSSIBLE. `removing` existed
        # so that a deliberate deletion could be told apart from a typo, and a
        # call that names a property there while also restating it in
        # `properties` was accepted -- with the property KEPT, because
        # `removing` only ever suppressed the refusal. So the one argument whose
        # entire job is to say what the caller means was reporting an intention
        # the call did not carry out, silently, in the direction nobody checks.
        # A caller believing something false about what they just did is the
        # defect `removing` was added to prevent.
        both = letting_go & set(said)
        if both:
            raise ValueError(
                f"{', '.join(map(repr, sorted(both)))} is named in `removing` "
                f"and also declared in `properties` for {name!r}. Those are "
                f"opposite requests and this call cannot be both: drop it from "
                f"`properties` to remove it, or from `removing` to keep it")
        was = self.current_definition(name)
        if was is not None:
            had = was["body"]
            dropped = [p for p in seed.BEHAVIOURAL_PROPERTIES
                       if p in had and p not in said and p not in letting_go]
            if dropped:
                raise ValueError(
                    f"this would remove {', '.join(map(repr, dropped))} from "
                    f"{name!r}, and production reads "
                    f"{'them' if len(dropped) > 1 else 'it'} to decide what the "
                    f"Kind's material DOES. Defining a Kind replaces its "
                    f"properties, so restate "
                    f"{'these' if len(dropped) > 1 else 'this'} to keep "
                    f"{'them' if len(dropped) > 1 else 'it'}, or name "
                    f"{'them' if len(dropped) > 1 else 'it'} in `removing` to "
                    f"say the removal is meant")
            unknown = letting_go - set(had)
            if unknown:
                raise ValueError(
                    f"{name!r} does not declare {', '.join(map(repr, sorted(unknown)))}, "
                    "so there is nothing there to remove")
        elif letting_go:
            raise ValueError(
                f"{name!r} is not defined yet, so nothing can be removed from it")
        body = dict(said)
        body["kind"] = name
        body["fields"] = list(fields)
        return self._define(name, body, attributed_to=attributed_to,
                            written_by=written_by)

    def define_relation(self, name, *, inverse, properties=None, attributed_to,
                        written_by=None) -> str:
        """Define an ordinary Relation, or the next version of one.

        It cannot carry a substrate role. A caller may invent any vocabulary
        they like; they may not invent engine mechanics by naming one, and they
        may not quietly redefine a relation that already carries a role. Adding
        a role remains an explicit change to the substrate.
        """
        if self._family_of(name) == "kind":
            raise ValueError(f"{name!r} is already defined as a kind")
        if not isinstance(inverse, str) or not inverse.strip():
            raise ValueError("a relation needs an inverse label, so that "
                             "direction survives")
        current = self.current_definition(name)
        if current is not None and current["body"].get("substrate_role") is not None:
            raise ValueError(
                f"{name!r} carries a substrate role; changing one is a "
                "substrate change, not a definition written through the seam")
        if current is not None and current["body"].get(seed.PROPOSES_ROLE):
            raise ValueError(
                f"{name!r} declares that it proposes a substrate role; "
                "changing that declaration is a substrate change, not a "
                "definition written through the seam")
        body = dict(properties or {})
        body["relation"] = name
        body["inverse"] = inverse
        body["directed"] = True
        body["substrate_role"] = None
        # NOR MAY ONE BE MINTED IN PASSING. A caller may invent any vocabulary
        # they like; declaring that a relation proposes a substrate role is a
        # statement about the substrate and has its own door below.
        body.pop(seed.PROPOSES_ROLE, None)
        return self._define(name, body, attributed_to=attributed_to,
                            written_by=written_by)

    def define_proposal_relation(self, name, *, inverse, proposes_role,
                                 properties=None, attributed_to,
                                 written_by=None) -> str:
        """Declare a Relation whose links PROPOSE a substrate role, never it.

        ITS OWN DOOR BECAUSE IT IS ITS OWN STATEMENT. A relation reaching this
        still carries `substrate_role: None` -- `stands` is inert to it, it
        confers nothing and it ends nothing -- but it tells a reader which
        role its links are about, so nothing above has to know its name. That
        is a claim about the substrate's vocabulary rather than an ordinary
        definition, and `define_relation` will not mint one by accident.

        A fresh corpus gets this from `seed.RELATIONS`. This is how a corpus
        that predates the declaration acquires it.
        """
        if proposes_role not in (seed.ESTABLISHES, seed.SUPERSEDES):
            raise ValueError(
                f"{proposes_role!r} is not a substrate role; the engine "
                f"understands {seed.ESTABLISHES!r} and {seed.SUPERSEDES!r}")
        if self._family_of(name) == "kind":
            raise ValueError(f"{name!r} is already defined as a kind")
        if not isinstance(inverse, str) or not inverse.strip():
            raise ValueError("a relation needs an inverse label, so that "
                             "direction survives")
        current = self.current_definition(name)
        if current is not None and current["body"].get("substrate_role") is not None:
            raise ValueError(
                f"{name!r} carries a substrate role; a relation that PERFORMS "
                "a role cannot also be declared to merely propose one")
        body = dict(properties or {})
        body["relation"] = name
        body["inverse"] = inverse
        body["directed"] = True
        body["substrate_role"] = None
        body[seed.PROPOSES_ROLE] = proposes_role
        self._proposing_cache.pop(proposes_role, None)
        return self._define(name, body, attributed_to=attributed_to,
                            written_by=written_by)

    # -- raw append --------------------------------------------------------

    def _append(self, family, definition, body, *, attributed_to,
                origin=None, link=None, written_by=None) -> str:
        """The one place a durable record is made, and the one place the two
        constitutive provenance facts are written.

        `written_by` is left as None when it is not honestly known. An unknown
        writer is recorded as unknown; it is never filled in from anything else.
        """
        record = self._record(family, definition, body,
                              attributed_to=attributed_to, origin=origin,
                              link=link, written_by=written_by)
        self._store.append_entry(record)
        return record["id"]

    @staticmethod
    def _record(family, definition, body, *, attributed_to, origin=None,
                link=None, written_by=None) -> dict:
        """The record `_append` writes, made and not yet written -- so that
        `admit_many` and `link_many` write exactly what it would."""
        return {
            "id": _new_id(family[:3]), "family": family,
            "definition": definition, "body": body,
            "attributed_to": attributed_to, "written_by": written_by,
            "recorded_at": _now(), "origin": origin, "link": link,
        }

    # -- reading -----------------------------------------------------------

    def all_entries(self) -> list[dict]:
        return self._store.all_entries()

    def read(self, ids) -> list[dict]:
        return self._store.by_ids(ids)

    def admissions_from(self, source: str) -> list[dict]:
        """Admissions from one source, in the record's append order. Generic:
        the spine knows no connector, and a connector needs no registry of its
        own to find what it admitted."""
        return self._store.admissions_from(source)

    def last_admission_seq(self, source: str) -> int:
        """A position to compare, not an identity: where `source`'s latest
        Admission sits in append order (0 for none). Unchanged means
        `admissions_from(source)` is unchanged, because nothing is ever
        removed or rewritten. One index seek."""
        return self._store.last_admission_seq(source)

    def definitions(self) -> list[dict]:
        """Every Kind and Relation definition, every version. Only those.

        For a reader that needs the vocabulary and nothing else, instead of
        decoding every entry in the corpus to find the definitions among them.
        """
        return self._store.by_family(DEFINITION)

    def count_of_kind(self, kind: str) -> int:
        """How many entries `entries_of_kind` would return, without reading
        them."""
        return self._store.count_of_definition(kind)

    def count_of_links(self) -> dict[str, int]:
        """How many links of each Relation the store holds, without reading
        them. A Relation with none is absent, not zero -- the caller names the
        Relations it wants to report."""
        return self._store.count_of_links()

    def linked_node_tally(self, relation, to, kind) -> tuple[int, float | None]:
        """How many nodes of `kind` this relation points at `to`, and the newest
        `recorded_at` among them -- without reading any of them."""
        return self._store.linked_node_tally(relation, to, kind)

    def linked_node_tallies(self, relation, to_any, kind) -> dict:
        """`linked_node_tally` for many endpoints in one read; an endpoint
        with nothing linked is absent (its tally is (0, None))."""
        return self._store.linked_node_tallies(relation, to_any, kind)

    def read_set(self, ids) -> list[dict]:
        """`read`, for a set of ids of any size: same rows, same order."""
        return self._store.by_id_set(ids)

    @property
    def writes(self) -> int:
        """Moves whenever THIS PROCESS appends a row, of any kind, and again
        when a transaction that appended commits. Not identity, not a count to
        do arithmetic with, not a version, never durable, and no use as a clock
        between processes.

        It exists so a caller holding a short-lived read scope can notice that
        the record moved under it without asking the database. See
        `Conversations.reading`.

        Rows appended plus transactions committed (R1): a reader on another
        thread no longer waits for an open transaction, so it can take its
        answer between the appends and the commit. The commit moving this too
        is what keeps that answer from being reused once the rows are visible.
        Between COMMIT and that count the rows are visible and this has not
        moved; a reader that must not straddle a commit asks `steady`."""
        return self._store.writes + self._store.commits

    @property
    def steady(self):
        """`writes`, if no commit is under way in this process; else None.

        WHAT AN ANSWER NEEDS TO BE ONE MOMENT OF THE RECORD. A thread inside
        `reading_beside_writer()` (R1) does not wait for another thread's open
        transaction: each of its reads sees the last committed record AS OF
        THAT READ, so two reads with a COMMIT between them describe two
        records. A COMMIT is bracketed by two counts in the store --
        `committing` moves just before the statement, `commits` just after it
        returns -- and while they differ this is None. A computation that
        reads this before it starts and again after it ends, and gets the
        same number both times, saw no COMMIT:

          * none was under way at the start, nor at the end (neither is None);
          * so any that ran in between began after the start and finished
            before the end, and finishing moved `commits`, so the number.

        So every read in it saw the record as it stood at the start, and that
        record already held every commit that had finished: nothing is
        half-seen, and nothing visible before it began is missed. A bare
        `writes` cannot say this: it stands still between COMMIT and
        `commits`, which is exactly when the rows become visible.

        Outside that scope, reads wait on the lock while a transaction is open
        and this is merely stricter than it needs to be. An open transaction
        that is not committing does not make this None: its rows are invisible
        to every reader but its own thread until its COMMIT, and that COMMIT
        is counted. In-process only, as `writes` is."""
        st = self._store
        if st.committing != st.commits:
            return None
        return st.writes + st.commits

    def settled(self, compute, otherwise, *, tries=3):
        """`compute()`, if nothing was written while it ran; else `otherwise()`.

        FOR A READ THAT ASKS ITS QUESTIONS IN A DIFFERENT ORDER THAN THE ONE
        IT REPLACES. Reading a scoped set up front -- which Kinds are
        propositional, which Turns are here -- and then the rest is cheaper
        than the whole-record read it replaces, but it puts some reads EARLIER
        than they were. A write committed in between could then be missed
        where the old order would have seen it. Asked as one computation and
        taken only if the write count did not move, every read in it saw the
        same record: no write the old order observed is missed. If one
        landed, the whole computation is taken again, and after `tries` the
        old code path itself answers.

        TAKEN ONLY BETWEEN TWO EQUAL `steady` READINGS. "Readers wait on
        the store's lock while a write is open" stopped being true inside
        `reading_beside_writer()` (R1): there each read sees the record as
        last committed, so a computation spanning a COMMIT could read half
        of it before and half after, with `Store.writes` -- moved at the
        appends, before it began -- unmoved. `steady` is the rule that holds
        beside the writer too; a try that starts while a commit is under way
        is not computed at all, because it could not be accepted.
        In-process only, as `writes` is."""
        for _ in range(tries):
            before = self.steady
            if before is None:
                continue
            value = compute()
            if self.steady == before:
                return value
        return otherwise()

    def entries_of_kind(self, kind: str) -> list[dict]:
        """Every node entry written against this Kind, at any version."""
        return [e for e in self._store.by_definition(kind)
                if e["family"] == ENTRY and e.get("link") is None]

    def entries_of_kinds(self, kinds) -> list[dict]:
        """Every node entry written against any of these Kinds, in append
        order -- what `entries_of_kind` gives for each, interleaved as the
        record holds them."""
        return [e for e in self._store.nodes_of_definitions(kinds)
                if e["family"] == ENTRY and e.get("link") is None]

    def links(self, *, relation=None, to=None, frm=None,
              to_any=None, frm_any=None) -> list[dict]:
        """Link entries, filtered. Indexed, so layers above need no SQL.

        A reader asking about SOME things -- one Conversation's Turns -- names
        them with `to_any` / `frm_any` rather than reading the relation for the
        whole corpus and filtering. See `Store.links`."""
        return self._store.links(relation=relation, to=to, frm=frm,
                                 to_any=to_any, frm_any=frm_any)

    def definition_for(self, entry: dict) -> dict | None:
        """The definition version this entry was written against, always.

        A later version of the same definition never reinterprets it.
        """
        ref = entry.get("definition") or {}
        name, version = ref.get("name"), ref.get("version")
        if name is None or version is None:
            return None
        key = (name, version)
        if key not in self._pinned:
            rows = self._store.definition_rows(name, version)
            self._pinned[key] = rows[0] if rows else None
        return self._pinned[key]

    def current_definition(self, name: str) -> dict | None:
        best = None
        for e in self._store.definition_rows(name):
            if best is None or e["definition"]["version"] > best["definition"]["version"]:
                best = e
        return best

    # -- the seam ----------------------------------------------------------

    def admit(self, *, source, locator, observed_at, payload,
              payload_type="text/plain", envelope=None, content="inline",
              batch=None, attributed_to=HUMAN, written_by=None) -> str:
        """Bring material in. Produces an Admission and nothing else.

        There is no argument that makes this yield an epistemic entry, and no
        later step promotes it. That is the Ladder, as shape.
        """
        return self._append(*self._admission(
            source=source, locator=locator, observed_at=observed_at,
            payload=payload, payload_type=payload_type, envelope=envelope,
            content=content, batch=batch), attributed_to=attributed_to,
            written_by=written_by)

    def admit_many(self, items, *, attributed_to=HUMAN,
                   written_by=None) -> list[str]:
        """Several `admit`s, in order, as one append. Each item is `admit`'s
        own keyword arguments (bar the attribution, which is one for all), and
        each is refused exactly as `admit` would refuse it -- possession of
        held bytes included -- before anything is written. All are written or
        none. What it saves is the per-row cost of a Sources sweep's 30k
        Admissions inside the write transaction (R1); what it writes is what
        30k `admit` calls would."""
        records = [self._record(*self._admission(**item),
                                attributed_to=attributed_to,
                                written_by=written_by) for item in items]
        with self.atomic():
            self._store.append_entries(records)
        return [r["id"] for r in records]

    def _admission(self, *, source, locator, observed_at, payload,
                   payload_type="text/plain", envelope=None, content="inline",
                   batch=None) -> tuple:
        """What `admit` checks and appends: (family, definition, body)."""
        if content not in ("inline", "external", "absent", "held"):
            raise ValueError("content must be inline, external, absent or held")
        if content == "held":
            # POSSESSION BEFORE THE RECORD OF IT. `held` means the bytes are in
            # this corpus's own store under the digest the locator names; an
            # Admission saying so over bytes that are not there would be the
            # record claiming something it cannot back.
            digest = held.digest_of(locator)
            if digest is None:
                raise ValueError("held content needs a locator of the form "
                                 f"{held.LOCATOR}<sha256>")
            if not held.has(self.root, digest):
                raise ValueError(f"no bytes are held for {digest}; possession "
                                 "must come before the record of it")
        return (ADMISSION, {"name": "admission", "version": 1}, {
            "source": source, "locator": locator, "observed_at": observed_at,
            "admitted_at": _now(), "payload": payload if content == "inline" else None,
            "payload_type": payload_type, "envelope": envelope or {},
            "content": content, "batch": batch,
        })

    def write(self, *, body, attributed_to, kind=None, origin=None,
              link=None, written_by=None) -> str:
        """Create an entry. Candidate material unless something establishes it.

        A node names a Kind. A LINK names a Relation and needs no Kind -- it is
        governed by the relation definition, which is what gives it meaning.
        Requiring a Kind as well would have put a Kind name in the engine.

        Permissive: anyone may write anything the shape allows.
        """
        if link is None and kind is None:
            raise ValueError("a node must name a kind")
        stored_link, definition = None, None
        if link:
            rel = self.current_definition(link["relation"])
            if rel is None:
                raise ValueError(f"no definition for relation {link['relation']!r}")
            stored_link = {
                "from": link["from"], "to": link["to"],
                "relation": link["relation"],
                "relation_version": rel["definition"]["version"],
            }
            definition = {"name": link["relation"],
                          "version": rel["definition"]["version"]}
        if kind is not None:
            kdef = self.current_definition(kind)
            if kdef is None:
                raise ValueError(f"no definition for {kind!r}")
            fields = kdef["body"].get("fields")
            if fields is not None and not set(body) <= set(fields):
                raise ValueError(
                    f"{kind} allows {sorted(fields)}, got {sorted(body)}")
            definition = {"name": kind, "version": kdef["definition"]["version"]}
        return self._append(ENTRY, definition, body,
                            attributed_to=attributed_to, origin=origin,
                            link=stored_link, written_by=written_by)

    def link_many(self, links, *, body, attributed_to,
                  written_by=None) -> list[str]:
        """Several Links of one Relation, in order, as one append: what
        `write(link=...)` once per link would write, the Relation's current
        version looked up once rather than per link. Each link is
        {"from", "to", "relation"}. All are written or none. For the
        `produced` links of a Sources sweep (R1)."""
        links = list(links)
        relations = {link["relation"] for link in links}
        current = {}
        for name in relations:
            rel = self.current_definition(name)
            if rel is None:
                raise ValueError(f"no definition for relation {name!r}")
            current[name] = rel["definition"]["version"]
        records = [self._record(
            ENTRY, {"name": link["relation"], "version": current[link["relation"]]},
            dict(body), attributed_to=attributed_to, written_by=written_by,
            link={"from": link["from"], "to": link["to"],
                  "relation": link["relation"],
                  "relation_version": current[link["relation"]]})
            for link in links]
        with self.atomic():
            self._store.append_entries(records)
        return [r["id"] for r in records]

    def establish(self, target, *, attributed_to, reason="",
                  written_by=None) -> str:
        """One act: a Link carrying the establishing role. It names no Kind.

        `reason` rides on the LINK. Why something happened belongs on the act
        that records it, never on a rewrite of the objects it connects.
        """
        return self.write(body={"reason": reason or "established"},
                          attributed_to=attributed_to, written_by=written_by,
                          link={"from": target, "to": target,
                                "relation": self._role_relation(seed.ESTABLISHES)})

    def superseding_relation(self) -> str:
        """Which relation currently carries the superseding role. Public, so a
        layer above can write a supersession without holding the relation's
        name or reaching into the spine's vocabulary module for the role."""
        return self._role_relation(seed.SUPERSEDES)

    def _role_relation(self, role: str) -> str:
        """Which relation currently declares this substrate role.

        Looked up in the data. The engine knows the two ROLES; it does not know
        what anybody chose to call them. Cached, because a relation carrying a
        role cannot be redefined through the seam -- the answer cannot change.
        """
        if role not in self._role_cache:
            for e in self._store.by_family(DEFINITION):
                if e["body"].get("substrate_role") == role:
                    self._role_cache[role] = e["body"]["relation"]
                    break
            else:
                raise ValueError(f"no relation declares the {role} role")
        return self._role_cache[role]

    def create_and_establish(self, *, kind, body, attributed_to,
                             origin=None, written_by=None) -> str:
        """A deliberate human creation: create AND establish, one operation.

        No self-approval ceremony -- the human does not propose to themselves and
        then approve. Atomic: a corpus holding the entry without the act that
        established it would be a false history.
        """
        with self.atomic():
            eid = self.write(kind=kind, body=body, attributed_to=attributed_to,
                             origin=origin or HUMAN, written_by=written_by)
            self.establish(eid, attributed_to=attributed_to,
                           written_by=written_by, reason="created directly")
        return eid

    # -- proposed, which is not done ----------------------------------------

    #: How many proposals one read returns before it starts saying how many it
    #: left out. Competing proposals are legal and unbounded; a read is not.
    PROPOSALS_READ_LIMIT = 50

    def proposal_relation(self, role: str = seed.SUPERSEDES) -> str | None:
        """Which relation, if any, declares that its links PROPOSE this role.

        None means NOT DECLARED, which is a third answer and never "none
        exist": a corpus written before the declaration holds no such relation,
        and a reader is entitled to be told that rather than handed an empty
        list that looks like an answered question.

        Read from the definitions, so the engine holds no relation name.
        """
        if role not in self._proposing_cache:
            best = None
            for e in self._store.by_family(DEFINITION):
                b = e["body"]
                if b.get(seed.PROPOSES_ROLE) != role:
                    continue
                v = e["definition"]["version"]
                if best is None or v > best[0]:
                    best = (v, b["relation"])
            if best is None:
                return None
            self._proposing_cache[role] = best[1]
        return self._proposing_cache[role]

    def propose_supersession(self, replacement, predecessors, *,
                             attributed_to, reason="", written_by=None) -> dict:
        """Record that this is PUT FORWARD to replace those. Nothing else.

        ONE LINK PER PREDECESSOR, for the same reason `supersedes` writes one
        per predecessor: the link is what carries the fact, so a proposal
        naming three predecessors names each of them and a reader walking from
        any one of them finds it.

        WHAT IT DOES NOT DO, stated because this is exactly the fact that was
        missing. It does not establish the replacement, it does not confer
        standing on anything, it does not end anything, and `stands()` for
        every predecessor is the same before and after -- the relation carries
        no substrate role, so the engine cannot read it as an ending even if
        somebody wanted it to. Several competing proposals may name the same
        predecessor and all of them stay in the record.

        Written all together, so a proposal that names three predecessors is
        never half-recorded.
        """
        relation = self.proposal_relation(seed.SUPERSEDES)
        if relation is None:
            raise ValueError(
                "no relation declares that it proposes the superseding role, "
                "so this record cannot say that one thing is put forward to "
                "replace another")
        named = list(dict.fromkeys(predecessors))
        if not named:
            raise ValueError("a proposed replacement names what it proposes "
                             "to replace; naming nothing proposes nothing")
        links = {}
        with self.atomic():
            for pred in named:
                links[pred] = self.write(
                    body={"reason": reason or "proposed as a replacement"},
                    attributed_to=attributed_to, written_by=written_by,
                    link={"from": replacement, "to": pred,
                          "relation": relation})
        return {"relation": relation, "replacement": replacement,
                "predecessors": named, "links": links}

    def proposed_supersessions(self, entry_id, *, limit=None) -> dict | None:
        """What is proposed to replace this, and what this proposes to replace.

        TWO DIRECTIONS, NEVER MERGED, and neither is `superseded_by`. A reader
        looking at one item has to be able to tell the successors that are
        merely PROPOSED from the one that actually ended it, and the two
        answers live in different fields precisely so that no caller has to
        decide which a list is.

        None when no relation declares the proposing role: not declared, which
        is not the same as none recorded.

        A proposal whose own link was superseded is WITHDRAWN. It is left out
        of `items` and counted, exactly as `stands` leaves a superseded link
        out of `incoming` -- one mechanism, applied to a different target.
        """
        relation = self.proposal_relation(seed.SUPERSEDES)
        if relation is None:
            return None
        cap = self.PROPOSALS_READ_LIMIT if limit is None else max(1, int(limit))
        memo = {}

        def view(links, other):
            kept, withdrawn = [], 0
            for x in links:
                if self._superseded(x["id"], None, memo):
                    withdrawn += 1
                    continue
                kept.append({
                    "entry": x["link"][other],
                    "link": x["id"],
                    "reason": (x["body"] or {}).get("reason"),
                    "attributed_to": x["attributed_to"],
                    "written_by": x["written_by"],
                    "at": x["recorded_at"],
                })
            kept.sort(key=lambda r: r["at"] or 0, reverse=True)
            return {"items": kept[:cap], "total": len(kept),
                    "omitted": max(0, len(kept) - cap),
                    "withdrawn": withdrawn}

        return {
            "entry": entry_id, "relation": relation,
            # naming THIS as what they would replace
            "successors": view(
                self._store.links(relation=relation, to=entry_id), "from"),
            # and what THIS is put forward to replace
            "predecessors": view(
                self._store.links(relation=relation, frm=entry_id), "to"),
            "confers": "nothing. Every predecessor named here stands exactly "
                       "as it stood; only an owner establishing a successor "
                       "replaces anything, and that writes its own link.",
        }

    # -- computed standing and history -------------------------------------

    def _role(self, link_entry) -> str | None:
        link = link_entry["link"]
        d = self.definition_for(
            {"definition": {"name": link["relation"],
                            "version": link["relation_version"]}})
        return d["body"].get("substrate_role") if d else None

    def _superseded(self, link_id, as_at, memo) -> bool:
        """Is this LINK itself superseded by an act that still counts?

        There is no correction-of-correction machinery: superseding anything,
        including a link, is the same mechanism applied to a different target.
        """
        if link_id in memo:
            return memo[link_id]
        memo[link_id] = False                       # guards a cycle
        for other in self._store.links(to=link_id):
            if as_at is not None and other["recorded_at"] > as_at:
                continue
            if self._role(other) != seed.SUPERSEDES:
                continue
            if not self._superseded(other["id"], as_at, memo):
                memo[link_id] = True
                break
        return memo[link_id]

    def stands(self, entry_id, as_at=None) -> dict:
        """What the record says about this entry, now or as at a time.

        Generic by construction: the engine names only the two substrate roles.
        Everything else -- disputes, support, derivation -- is returned grouped
        by its own label, and the reader decides what it means.
        """
        established_by, superseded_by, other, memo = [], [], {}, {}
        for link in self._store.links(to=entry_id):
            if as_at is not None and link["recorded_at"] > as_at:
                continue
            if self._superseded(link["id"], as_at, memo):
                continue
            role = self._role(link)
            if role == seed.ESTABLISHES:
                established_by.append(link["id"])
            elif role == seed.SUPERSEDES:
                superseded_by.append(link["link"]["from"])
            else:
                other.setdefault(link["link"]["relation"], []).append(link["id"])
        return {
            "entry": entry_id,
            "stands": bool(established_by) and not superseded_by,
            "established_by": sorted(established_by),
            "superseded_by": sorted(superseded_by),
            "incoming": {k: sorted(v) for k, v in sorted(other.items())},
        }

    def superseded_now(self, entry_ids) -> set:
        """Which of these entries `stands(...)["superseded_by"]` would answer
        non-empty for now -- an act of the superseding role, itself still
        counting, points at it -- read a LEVEL at a time for all of them
        rather than once per entry and once per link below it.

        The same rule `_superseded` applies, over the same links in the same
        order; only the reads are shared. Every level is one indexed read of
        the links pointing at the level above, so the cost is the depth of
        the deepest supersession chain, not the number of entries."""
        incoming, frontier, seen = {}, list(dict.fromkeys(entry_ids)), set()
        seen.update(frontier)
        while frontier:
            nxt = []
            for link in self._store.links(to_any=frontier):
                if self._role(link) != seed.SUPERSEDES:
                    continue
                incoming.setdefault(link["link"]["to"], []).append(link["id"])
                if link["id"] not in seen:
                    seen.add(link["id"])
                    nxt.append(link["id"])
            frontier = nxt

        def superseded(eid, memo):
            if eid in memo:
                return memo[eid]
            memo[eid] = False                       # guards a cycle
            for other in incoming.get(eid, ()):
                if not superseded(other, memo):
                    memo[eid] = True
                    break
            return memo[eid]

        return {e for e in dict.fromkeys(entry_ids) if superseded(e, {})}

    def advance(self) -> tuple[int, int, int]:
        """How far this record has got. See `store.advance`."""
        return self._store.advance()

    def since(self, advance, cap: int, *, acts_in_full: bool = False):
        """What was written after `advance`, as the rows that say where.
        See `store.since`."""
        return self._store.since(advance, cap, acts_in_full=acts_in_full)

    # -- bounded reads for the Fluid read model. See the Store's own. -------

    def heads(self, ids) -> dict:
        """What each of these rows is, without its body. See `store.heads`."""
        return self._store.heads(ids)

    def members_page(self, to, **kw) -> dict:
        """One bounded page of what is linked to `to`. See
        `store.members_page`."""
        return self._store.members_page(to, **kw)

    def activity_page(self, kind, **kw) -> tuple[list[str], int]:
        """Nodes of a Kind, most recently active first, one page. See
        `store.activity_page`."""
        return self._store.activity_page(kind, **kw)

    def member_total(self, to, **kw) -> int:
        return self._store.member_total(to, **kw)

    def home_numbers(self, to, ids, **kw) -> dict:
        """Ranks among what is linked to `to`. See `store.home_numbers`."""
        return self._store.home_numbers(to, ids, **kw)

    def reply_closure(self, root, **kw) -> list:
        """Everything under `root` by a relation. See `store.reply_closure`."""
        return self._store.reply_closure(root, **kw)

    def toward_page(self, who, **kw) -> list:
        """Nodes that turn toward `who`, newest first, one page. See
        `store.toward_page`."""
        return self._store.toward_page(who, **kw)

    def toward_since(self, applied, **kw) -> dict:
        """Whom the nodes touched after `applied` turn toward. See
        `store.toward_since`."""
        return self._store.toward_since(applied, **kw)

    def stream_page(self, **kw) -> dict:
        """Every node of a Kind with a home, by record position, one page.
        See `store.stream_page`."""
        return self._store.stream_page(**kw)

    def verify_chain(self) -> dict:
        """Is each durable stream internally consistent, and where not.

        NOT `has this record been altered`, which is what this used to say
        and is broader than what it checks. It walks the hash chains over
        the three event streams and reports the first inconsistency. It
        says nothing about the corpus identity row, nothing about the
        separate instance corpus, and nothing about a chain that was
        rewritten rather than edited under.

        On the seam because integrity is something a reader is entitled to
        ask about the record, not a detail of how it is stored.
        """
        return self._store.verify_chain()

    def history(self, entry_id) -> list[str]:
        """The supersession chain through this entry, oldest first."""
        memo = {}

        def counted(links):
            return [x for x in links
                    if self._role(x) == seed.SUPERSEDES
                    and not self._superseded(x["id"], None, memo)]

        def older_than(x):
            found = counted(self._store.links(frm=x))
            return found[-1]["link"]["to"] if found else None

        def newer_than(x):
            found = counted(self._store.links(to=x))
            return found[-1]["link"]["from"] if found else None

        chain, seen, cur = [entry_id], {entry_id}, entry_id
        while True:                                  # walk to the oldest
            prev = older_than(cur)
            if prev is None or prev in seen:
                break
            chain.insert(0, prev)
            seen.add(prev)
            cur = prev
        cur = entry_id
        while True:                                  # and to the newest
            nxt = newer_than(cur)
            if nxt is None or nxt in seen:
                break
            chain.append(nxt)
            seen.add(nxt)
            cur = nxt
        return chain

    # -- operational history -----------------------------------------------

    def record_operational(self, *, actor, act, conversation=None,
                           turn=None, execution=None, runtime=None,
                           because=None, caused_by=None, about=(),
                           detail=None) -> str:
        """Record that somebody did something. Append-only, never revised.

        Six questions, six places: `actor` who, `act` what, `conversation`
        where, `at` when, `execution`/`runtime` how, and why as either
        `because` in words or `caused_by` pointing at the act this followed
        from. Nothing is manufactured -- an unrecorded reason stays null.

        There is deliberately NO topic column. A Topic is a data-defined Kind,
        and the spine names no Kind: a finer scope than the Conversation goes
        in `about`, as an ordinary durable reference.

        `act` is vocabulary, not engine behaviour: nothing here branches on it.
        """
        if not actor or not act:
            raise ValueError("an operational act needs an actor and an act")
        oid = _new_id("opr")
        self._store.append_operational({
            "id": oid, "at": _now(), "actor": actor, "act": act,
            "conversation": conversation, "turn": turn,
            "execution": execution, "runtime": runtime, "because": because,
            "caused_by": caused_by, "about": list(about),
            "detail": detail or {},
        })
        return oid

    def operational(self, **kw) -> list[dict]:
        """Read operational history. Indexed by id, turn, actor, conversation,
        execution and causal parent."""
        return self._store.operational(**kw)

    def operational_under(self, parents, *, act=None) -> list[tuple]:
        """Every act caused by any of these, as (seq, act) in write order:
        `operational(caused_by=p)` for each `p`, in one read. See
        `Store.operational_under`."""
        return self._store.operational_under(parents, act=act)

    def operational_marks(self, *, act, execution=None) -> list[dict]:
        """Which acts of these kinds exist, as marks (seq, id, act,
        execution, caused_by) with nothing decoded. See
        `Store.operational_marks`."""
        return self._store.operational_marks(act=act, execution=execution)

    def operational_order(self, ids) -> dict:
        """The record's own write order for these acts: id -> seq."""
        return self._store.operational_order(ids)

    # -- delivery ----------------------------------------------------------

    def execution(self, conversation=None):
        """A delivery boundary holding its own durable execution reference."""
        return _Boundary(self, conversation)

    def deliveries(self, *, participant=None, execution=None) -> list[dict]:
        """Read delivery evidence, optionally narrowed.

        Readable through the seam; still not writable through it. That is the
        whole point of the separate table. Both filters are indexed -- status
        questions are asked per participant and would otherwise re-read every
        delivery ever recorded.
        """
        if execution is not None:
            return self._store.deliveries_for(execution)
        if participant is not None:
            return self._store.deliveries_by_participant(participant)
        return self._store.deliveries()

    def verify_use(self, execution_ref, claimed_ids, as_at=None) -> dict:
        """Was this material actually delivered to this execution?

        Reads delivery records only. An entry existing in the corpus is not an
        answer to this question.
        """
        delivered = {}
        for rec in self._store.deliveries_for(execution_ref):
            if as_at is not None and rec["at"] > as_at:
                continue
            for item in rec["material"]:
                delivered[item["entry"]] = item["rendered"]
        return {cid: delivered.get(cid, "not_delivered") for cid in claimed_ids}


class _Boundary:
    """Foundation's side. The only thing that can write a delivery record."""

    def __init__(self, corpus: Corpus, conversation=None):
        self.corpus = corpus
        self.reference = _new_id("exe")
        self.conversation = conversation

    def deliver(self, entry_ids, *, mechanism="stub", rendered="body",
                participant=None, runtime=None, behavioural_sources=None,
                operation_ok=True) -> str:
        """Compose material and record that it was delivered through `mechanism`.

        The record says what crossed, to whom, by what means, and which
        behavioural material contributed. It does not claim the recipient read,
        understood, remembered, followed or used it -- there is deliberately no
        field in which that could be written.
        """
        entries = self.corpus.read(entry_ids)
        found = {e["id"] for e in entries}
        rec = {
            "id": _new_id("dlv"),
            "execution": self.reference,
            "conversation": self.conversation,
            "participant": participant,
            "runtime": runtime,
            "mechanism": mechanism,
            "at": _now(),
            "material": [{"entry": e["id"],
                          "definition": e["definition"],
                          "rendered": rendered} for e in entries],
            "behavioural_sources": list(behavioural_sources or []),
            "operation_ok": bool(operation_ok) and found == set(entry_ids),
        }
        self.corpus._store.append_delivery(rec)
        return rec["id"]


def open_corpus(path: str, *, access: str = "auto") -> Corpus:
    """Open the corpus where the user put it. Nothing is imported or copied.

    NEVER CREATES ONE, and never changes its schema (D2): a path with no Brain
    is `BrainMissing`, and a Brain the schema check does not allow writing is
    opened read-only -- or refused, with `access="write"`. See
    `mentis.spine.migrations`."""
    if not path:
        raise ValueError("a corpus path is required")
    return Corpus(os.path.abspath(path), access=access)


def create_corpus(path: str) -> Corpus:
    """Make a new Brain at `path` and open it: the explicit act of creation.

    The schema is built by the migration runner (`migrations.create_brain`),
    exactly as an adoption builds it, and the bootstrap vocabulary is seeded
    by the first open. Refuses where a Brain already exists."""
    from mentis.spine import migrations
    if not path:
        raise ValueError("a corpus path is required")
    path = os.path.abspath(path)
    migrations.create_brain(path)
    return Corpus(path, access="write")
