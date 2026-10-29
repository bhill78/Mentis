"""`mentis brain export`: the closure of one marked thing, written as a zip.

READ ONLY. The Brain is opened `access="read"` -- the SHARED open lock only,
so this runs beside a serving server -- and the whole closure is read in ONE
read transaction, so it describes one committed moment. Nothing is written
to the Brain; the zip goes to a path outside every Brain.

THE CLOSURE (design §2, with O2):

  conversation  the Conversation and its versions (renames) with their
                `supersedes` links; every Turn `in-conversation` with its
                versions and deletion records; the Topics `topic-of` it and
                the Participants `participates-in` it; anchors in its Turns
                and reactions to them; the thread links among all of these
                (`THREAD_RELATIONS`); the Participants named as authors,
                addressees or actors, with their rename versions; held
                Admissions the Turns name, with their bytes; and the
                meaning-giving acts (`MEANING_ACTS`).
  turn          the Turn's version line, anchors and reactions, its
                `in-conversation` link and the Conversation entry it is homed
                on (with its name line, so it reads by its name), the Topics
                it is filed under, its authors, and the meaning-giving acts
                on it. Every other Turn is a stub.
  item          the item's version line and its own outbound links (its
                grounds), its authors and the Admissions it names. Never its
                standing.

Everything referenced and not carried is a STUB in `stubs.json`. Standing is
EVIDENCE in `evidence.json`: the `establishes`, `scoped-to`,
`carries-intake` and `designated-as` links are never rows of the export.
"""

from __future__ import annotations

import datetime
import json
import os

from mentis.conversation import (
    ABOUT_TOPIC, ANCHORS_IN, CARRIES_INTAKE, CONTRIBUTION, CONVERSATION,
    DESIGNATED_AS,
    CONVERSATION_RENAMED, DECISION_ANSWERED, DECISION_FORM,
    DECISION_FORM_ATTACHED, DRAWS_ON, IN_CONVERSATION, OPENED_FROM,
    PARTICIPANT, PARTICIPANT_RENAMED, PARTICIPATES_IN, PRODUCED,
    PROVISIONALLY_NAMED, PURGED, REACTS_TO, REPLIES_TO, SCOPED_TO, SHOWN_IN,
    TOPIC, TOPIC_OF)
from mentis.spine import held, migrations

from . import ExchangeRefused, format as fmt
from ._rows import Reader, act_record, one_read, record
from .identity import identity_from

ANCHOR = "anchor"
REACTION = "reaction"
ADMISSION = "admission"
TURN_ADDRESSED = "turn-addressed"
EXPECTATION_RECORDED = "expectation-recorded"
EXPECTATION_MET = "expectation-met"

#: Relations a Conversation or Turn closure carries between its rows, besides
#: the superseding one (which is read from the data).
THREAD_RELATIONS = (IN_CONVERSATION, REPLIES_TO, ABOUT_TOPIC, TOPIC_OF,
                    PARTICIPATES_IN, ANCHORS_IN, REACTS_TO, OPENED_FROM,
                    DRAWS_ON, SHOWN_IN, PRODUCED)

#: THE ONLY ACTS AN EXPORT CARRIES: what a reader shows -- names, addressing,
#: which question was asked and how it was answered. `decision-form` is the
#: act a form's questions and its attachment name; the design lists the form
#: acts as "expectation-recorded / expectation-met for decision forms", and
#: without the form act itself none of them reads as a form. Expectation acts
#: are carried only for a decision form's questions.
MEANING_ACTS = (CONVERSATION_RENAMED, PARTICIPANT_RENAMED,
                PROVISIONALLY_NAMED, TURN_ADDRESSED, DECISION_FORM,
                DECISION_FORM_ATTACHED, DECISION_ANSWERED,
                EXPECTATION_RECORDED, EXPECTATION_MET)

def never_carried(reader: Reader) -> set:
    """The relations that put things in force: never rows of an export."""
    return {reader.establishes(), SCOPED_TO, CARRIES_INTAKE, DESIGNATED_AS}


def _body(row) -> dict:
    try:
        b = json.loads(row["body"]) if isinstance(row["body"], str) \
            else row["body"]
    except ValueError:
        return {}
    return b if isinstance(b, dict) else {}


def _detail(row) -> dict:
    try:
        d = json.loads(row["detail"] or "{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _about(row) -> list:
    try:
        a = json.loads(row["about"] or "[]")
    except ValueError:
        return []
    return a if isinstance(a, list) else []


def _is_node(row) -> bool:
    return row["family"] == "entry" and row["link_relation"] is None


def label_of(row) -> str | None:
    """A short human label for a row: its name, alias or first words."""
    b = _body(row)
    for key in ("name", "alias", "title"):
        if isinstance(b.get(key), str) and b[key].strip():
            return b[key].strip()[:120]
    for part in b.get("parts") or ():
        if isinstance(part, dict) and isinstance(part.get("text"), str) \
                and part["text"].strip():
            return part["text"].strip()[:120]
    for key in ("text", "behaviour", "what", "reason"):
        if isinstance(b.get(key), str) and b[key].strip():
            return b[key].strip()[:120]
    return None


class Closure:
    """What one export carries, built on one read transaction."""

    def __init__(self, reader: Reader):
        self.r = reader
        self.sup = reader.supersedes()
        self.never = never_carried(reader)
        self.rows: dict = {}            # carried entry id -> raw row
        self.acts: dict = {}            # carried act id -> raw row
        self.refs: set = set()          # ids named and perhaps not carried
        self.blobs: dict = {}           # digest -> admission id
        self.purged: list = []          # admissions whose bytes are gone

    # -- building -----------------------------------------------------------

    def add(self, rows):
        for row in rows:
            if row["link_relation"] in self.never:
                continue
            self.rows.setdefault(row["id"], row)

    def nodes(self, kind=None) -> list:
        return [r for r in self.rows.values() if _is_node(r)
                and (kind is None or r["def_name"] == kind)]

    def lines(self):
        """Every version line through what is carried: `supersedes` links in
        either direction, to a fixed point. Deletion records are versions,
        and an ended filing's deletion record is reached the same way."""
        frontier = set(self.rows)
        while frontier:
            found = (self.r.links(relations=[self.sup], to_any=frontier)
                     + self.r.links(relations=[self.sup], frm_any=frontier))
            ends = set()
            for link in found:
                if link["id"] in self.rows:
                    continue
                ends |= {link["link_from"], link["link_to"]}
            ends -= set(self.rows)
            got = self.r.entries(ends)
            # a supersession that ends something never carried (an
            # establishing link, a placement) is standing: evidence only
            fresh = []
            for link in found:
                if link["id"] in self.rows:
                    continue
                far = [got.get(e) or self.rows.get(e)
                       for e in (link["link_from"], link["link_to"])]
                if any(x is None or x["link_relation"] in self.never
                       for x in far):
                    if any(x is None for x in far):
                        self.refs |= {link["link_from"], link["link_to"]}
                    continue
                fresh.append(link)
                for x in far:
                    if x["id"] not in self.rows:
                        fresh.append(x)
            before = set(self.rows)
            self.add(fresh)
            frontier = set(self.rows) - before

    def inbound(self, relation, to_ids, *, kinds=None) -> list:
        """Carry `relation` links INTO these ids and the nodes they come from
        (of `kinds`, when given). Returns the nodes pulled in."""
        links = self.r.links(relations=[relation], to_any=to_ids)
        got = self.r.entries(link["link_from"] for link in links)
        pulled = []
        for link in links:
            node = got.get(link["link_from"])
            if node is None or not _is_node(node) or (
                    kinds is not None and node["def_name"] not in kinds):
                continue
            self.add([link, node])
            pulled.append(node)
        return pulled

    def outbound(self, relations=None, *, from_ids=None):
        """Carry the links these nodes make (of `relations`, or every one
        never carried excepted); a target not carried is a stub."""
        ids = from_ids if from_ids is not None else [
            n["id"] for n in self.nodes() if n["def_name"] != PARTICIPANT]
        for link in self.r.links(relations=relations, frm_any=ids):
            if link["link_relation"] in self.never \
                    or link["link_relation"] == self.sup:
                continue
            self.add([link])
            self.refs.add(link["link_to"])

    def turn_shape(self):
        turns = [n["id"] for n in self.nodes(CONTRIBUTION)]
        anchors = self.inbound(ANCHORS_IN, turns, kinds=(ANCHOR,))
        self.inbound(REACTS_TO, [a["id"] for a in anchors], kinds=(REACTION,))
        self.lines()

    def participants(self):
        """The Participants named as authors, addressees or actors."""
        named = set()
        for row in self.rows.values():
            named.add(row["attributed_to"])
            if row["def_name"] == CONTRIBUTION:
                named |= {a for a in _body(row).get("addressed_to") or ()
                          if isinstance(a, str)}
        for act in self.acts.values():
            named.add(act["actor"])
            if act["act"] == TURN_ADDRESSED:
                named |= {a for a in _about(act) if isinstance(a, str)}
        got = self.r.entries(n for n in named if isinstance(n, str))
        self.add([g for g in got.values()
                  if _is_node(g) and g["def_name"] == PARTICIPANT])
        self.lines()

    def admissions(self):
        """Held Admissions the carried rows name, with their bytes."""
        named = set()
        for row in self.rows.values():
            if row["def_name"] == CONTRIBUTION:
                for part in _body(row).get("parts") or ():
                    if isinstance(part, dict) and isinstance(
                            part.get("ref"), str):
                        named.add(part["ref"])
            if row["link_to"]:
                named.add(row["link_to"])
        got = self.r.entries(named - set(self.rows))
        adms = [g for g in got.values() if g["family"] == ADMISSION]
        purged = {link["link_to"] for link in self.r.links(
            relations=[PURGED], to_any=[a["id"] for a in adms])}
        for a in adms:
            self.add([a])
            b = _body(a)
            digest = held.digest_of(b.get("locator"))
            if b.get("content") != "held" or digest is None:
                continue
            if a["id"] in purged:
                self.purged.append(a["id"])
                continue
            self.blobs.setdefault(digest, a["id"])
        self.refs |= named

    # -- acts ---------------------------------------------------------------

    def meaning_acts(self, *, conversations, turns, pending_forms):
        """The meaning-giving acts about what is carried. `pending_forms`:
        whether forms on no post yet, in these Conversations, belong here
        (a Conversation export) or not (a Turn export)."""
        conversations, turns = list(conversations), list(turns)
        rows = []
        if conversations:
            rows += self.r.acts(
                "act IN (?, ?) AND conversation IN "
                "(SELECT value FROM json_each(?))",
                (CONVERSATION_RENAMED, PROVISIONALLY_NAMED,
                 json.dumps(conversations)))
        if turns:
            rows += self.r.acts(
                "act IN (?, ?, ?) AND turn IN (SELECT value FROM json_each(?))",
                (TURN_ADDRESSED, DECISION_FORM, DECISION_FORM_ATTACHED,
                 json.dumps(turns)))
        if pending_forms and conversations:
            rows += self.r.acts(
                "act = ? AND turn IS NULL AND conversation IN "
                "(SELECT value FROM json_each(?))",
                (DECISION_FORM, json.dumps(conversations)))
        # a form attached to a carried post is carried with it
        attached = [a["caused_by"] for a in rows
                    if a["act"] == DECISION_FORM_ATTACHED and a["caused_by"]]
        rows += [a for a in self.r.acts_by_ids(attached).values()
                 if a["act"] == DECISION_FORM]
        forms = sorted({a["id"] for a in rows if a["act"] == DECISION_FORM})
        questions = self.r.acts(
            "act = ? AND json_extract(detail, '$.form') IN "
            "(SELECT value FROM json_each(?))",
            (EXPECTATION_RECORDED, json.dumps(forms))) if forms else []
        rows += questions
        qids = [q["id"] for q in questions]
        if qids:
            rows += self.r.acts(
                "act IN (?, ?) AND caused_by IN "
                "(SELECT value FROM json_each(?))",
                (DECISION_ANSWERED, EXPECTATION_MET, json.dumps(qids)))
        for a in rows:
            self.acts.setdefault(a["id"], a)

    def participant_acts(self):
        people = [n["id"] for n in self.nodes(PARTICIPANT)]
        if not people:
            return
        for a in self.r.acts(
                "act = ? AND json_extract(detail, '$.participant') IN "
                "(SELECT value FROM json_each(?))",
                (PARTICIPANT_RENAMED, json.dumps(people))):
            self.acts.setdefault(a["id"], a)

    def act_refs(self):
        for a in self.acts.values():
            self.refs |= {x for x in (a["caused_by"], a["turn"],
                                      a["conversation"]) if x}
            self.refs |= {x for x in _about(a) if isinstance(x, str)}
            d = _detail(a)
            self.refs |= {d[k] for k in ("reply", "version", "replaces",
                                         "form", "post")
                          if isinstance(d.get(k), str)}

    # -- what goes beside the rows -----------------------------------------

    def definitions(self) -> list:
        named = sorted({(r["def_name"], r["def_version"])
                        for r in self.rows.values()
                        if r["def_name"] is not None})
        out = []
        for name, version in named:
            rows = [d for d in self.r.definitions_named(name)
                    if d["def_version"] == version]
            if not rows and name == ADMISSION:
                # the spine's own fixed shape (`seam._admission`): no
                # definition row on any Brain, so nothing to compare
                out.append({"name": name, "version": version, "body": None,
                            "body_sha256": None, "fixed": True})
                continue
            if not rows:
                out.append({"name": name, "version": version, "body": None,
                            "body_sha256": None,
                            "missing": "the exporting Brain holds no such "
                                       "definition"})
                continue
            body = _body(rows[0])
            out.append({"name": name, "version": version, "body": body,
                        "body_sha256": fmt.body_sha256(body),
                        "family": "kind" if "kind" in body else "relation"})
        return out

    def evidence(self) -> list:
        """Standing on the origin, for every carried node: who established
        it, where it is placed, intake designations, and what superseded it.
        Never imported as links."""
        ids = [n["id"] for n in self.rows.values() if _is_node(n)]
        est = self.r.establishes()
        standing = self.r.links(relations=[est], to_any=ids)
        placed = self.r.links(relations=[SCOPED_TO, CARRIES_INTAKE],
                              frm_any=ids)
        ended = {}
        for link in self.r.links(relations=[self.sup], to_any=[
                x["id"] for x in standing + placed]):
            ended.setdefault(link["link_to"], []).append(link["link_from"])
        superseded = {}
        for link in self.r.links(relations=[self.sup], to_any=ids):
            superseded.setdefault(link["link_to"], []).append(
                link["link_from"])
        out = {}

        def one(eid):
            return out.setdefault(eid, {
                "entry": eid, "kind": self.rows[eid]["def_name"],
                "established": [], "placements": [], "intake": [],
                "superseded_by": superseded.get(eid, [])})

        for link in standing:
            if link["link_to"] not in self.rows:
                continue
            one(link["link_to"])["established"].append({
                "link": link["id"], "by": link["attributed_to"],
                "at": link["recorded_at"],
                "reason": _body(link).get("reason"),
                "ended_by": ended.get(link["id"], [])})
        for link in placed:
            key = ("placements" if link["link_relation"] == SCOPED_TO
                   else "intake")
            one(link["link_from"])[key].append({
                "link": link["id"], "to": link["link_to"],
                "by": link["attributed_to"], "at": link["recorded_at"],
                "ended_by": ended.get(link["id"], [])})
        for eid in ids:
            if superseded.get(eid) and eid not in out:
                one(eid)
        return [out[k] for k in sorted(out)]

    def stubs(self, fork_id) -> list:
        wanted = {x for x in self.refs if isinstance(x, str) and x}
        wanted -= set(self.rows) | set(self.acts)
        entries = self.r.entries(wanted)
        acts = self.r.acts_by_ids(wanted - set(entries))
        out = []
        for ref in sorted(wanted):
            if ref in entries:
                e = entries[ref]
                out.append({"id": ref, "kind": e["def_name"] or e["family"],
                            "label": label_of(e), "origin": fork_id})
            elif ref in acts:
                a = acts[ref]
                out.append({"id": ref, "kind": "act", "act": a["act"],
                            "label": a["because"], "origin": fork_id})
            elif "-" in ref and len(ref) <= 40 and " " not in ref:
                out.append({"id": ref, "kind": None, "label": None,
                            "origin": fork_id,
                            "note": "not in the exporting Brain either"})
        return out


# -- the three roots ---------------------------------------------------------

def _root(reader, cl, eid, *, kind, flag) -> dict:
    got = reader.entries([eid]).get(eid)
    if got is None:
        raise ExchangeRefused(f"{eid} is not in this Brain")
    if kind is not None and (not _is_node(got) or got["def_name"] != kind):
        raise ExchangeRefused(f"{eid} is {got['def_name'] or got['family']!r}"
                              f", not a {kind}; {flag} names a {kind}")
    if kind is not None and reader.links(relations=[cl.sup], frm_any=[eid]):
        raise ExchangeRefused(f"{eid} is a later version of a {kind}, not "
                              f"one of its own; name the {kind} it revises")
    return got


def conversation_closure(reader, cid) -> Closure:
    cl = Closure(reader)
    root = _root(reader, cl, cid, kind=CONVERSATION, flag="--conversation")
    cl.add([root])
    cl.inbound(IN_CONVERSATION, [cid], kinds=(CONTRIBUTION,))
    cl.inbound(TOPIC_OF, [cid], kinds=(TOPIC,))
    cl.inbound(PARTICIPATES_IN, [cid], kinds=(PARTICIPANT,))
    cl.lines()
    cl.turn_shape()
    cl.outbound(THREAD_RELATIONS)
    cl.meaning_acts(conversations=[cid],
                    turns=[n["id"] for n in cl.nodes(CONTRIBUTION)],
                    pending_forms=True)
    cl.participants()
    cl.participant_acts()
    cl.admissions()
    cl.lines()
    cl.act_refs()
    return cl


def turn_closure(reader, tid) -> Closure:
    cl = Closure(reader)
    root = _root(reader, cl, tid, kind=CONTRIBUTION, flag="--turn")
    cl.add([root])
    cl.lines()
    cl.turn_shape()
    turns = [n["id"] for n in cl.nodes(CONTRIBUTION)]
    # its home: the in-conversation link and the Conversation entry, with
    # the name line that says what it is called -- nothing else of it
    homes = reader.links(relations=[IN_CONVERSATION], frm_any=[tid])
    convs = reader.entries(h["link_to"] for h in homes)
    for h in homes:
        if h["link_to"] in convs:
            cl.add([h, convs[h["link_to"]]])
    # the Topics it is filed under, each with its own topic-of link
    filings = reader.links(relations=[ABOUT_TOPIC], frm_any=turns)
    topics = {k: v for k, v in reader.entries(
        f["link_to"] for f in filings).items() if v["def_name"] == TOPIC}
    cl.add(topics.values())
    for t in reader.links(relations=[TOPIC_OF], frm_any=list(topics)):
        if t["link_to"] in convs:
            cl.add([t])
    cl.lines()
    cl.outbound(THREAD_RELATIONS, from_ids=[
        n["id"] for n in cl.nodes() if n["def_name"] in (
            CONTRIBUTION, ANCHOR, REACTION, TOPIC)])
    cl.meaning_acts(conversations=list(convs), turns=turns,
                    pending_forms=False)
    cl.participants()
    cl.participant_acts()
    cl.admissions()
    cl.lines()
    cl.act_refs()
    return cl


def item_closure(reader, iid) -> Closure:
    cl = Closure(reader)
    root = _root(reader, cl, iid, kind=None, flag="--item")
    if not _is_node(root):
        raise ExchangeRefused(f"{iid} is a {root['family']} row, not an item")
    if root["def_name"] in (CONVERSATION, CONTRIBUTION):
        flag = ("--conversation" if root["def_name"] == CONVERSATION
                else "--turn")
        raise ExchangeRefused(f"{iid} is a {root['def_name']}; export it "
                              f"with {flag}")
    cl.add([root])
    cl.lines()
    cl.outbound(None)
    cl.participants()
    cl.participant_acts()
    cl.admissions()
    cl.lines()
    cl.act_refs()
    return cl


# -- where the file may go ---------------------------------------------------

def _inside_a_brain(path: str) -> str | None:
    """The Brain folder `path` would be written inside, if any."""
    from mentis.spine import brainlock
    d = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isfile(os.path.join(d, migrations.DB)) or os.path.exists(
                os.path.join(d, brainlock.OPEN_LOCK)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def export(brain: str, *, out: str, conversation=None, turn=None, item=None,
           by=None) -> dict:
    """Export one Conversation, Turn or item of the Brain at `brain` to the
    zip `out`. Returns the manifest as written, with the path."""
    from mentis.spine.store import Store
    roots = [(k, v) for k, v in (("conversation", conversation),
                                 ("turn", turn), ("item", item)) if v]
    if len(roots) != 1:
        raise ExchangeRefused("name exactly one of --conversation, --turn "
                              "or --item")
    kind, root = roots[0]
    out = os.path.abspath(out)
    inside = _inside_a_brain(out)
    if inside is not None:
        raise ExchangeRefused(f"{out} is inside the Brain at {inside}; an "
                              f"export is written outside every Brain")
    if os.path.exists(out):
        raise ExchangeRefused(f"{out} already exists; nothing was written")
    if not os.path.isdir(os.path.dirname(out)):
        raise ExchangeRefused(f"{os.path.dirname(out)} is not a folder")
    st = Store(os.path.abspath(brain), access="read")
    try:
        with one_read(st) as r:
            ledger = r.ledger()
            if not ledger:
                raise ExchangeRefused(
                    "this Brain predates the schema ledger, so a receiving "
                    "Brain could not check that the two share a schema: "
                    + st.status.explain(os.path.abspath(brain)))
            who = identity_from(r)
            build = {"conversation": conversation_closure,
                     "turn": turn_closure, "item": item_closure}[kind]
            cl = build(r, root)
            entries = [record(row) for row in sorted(
                cl.rows.values(), key=lambda x: x["seq"])]
            acts = [act_record(row) for row in sorted(
                cl.acts.values(), key=lambda x: x["seq"])]
            definitions = cl.definitions()
            evidence = cl.evidence()
            stubs = cl.stubs(who["fork_id"])
            heads = r.heads()
        blobs, missing = {}, []
        for digest, adm in sorted(cl.blobs.items()):
            state, data = held.state(st.root, digest, verify=True)
            if state == "present":
                blobs[digest] = data
            else:
                missing.append({"digest": digest, "admission": adm,
                                "state": state})
    finally:
        st.close()
    manifest = {
        "origin": {"corpus_id": who["corpus_id"],
                   "marker_corpus_id": who["corpus_id"],
                   "fork_id": who["fork_id"]},
        "ledger": [{k: row[k] for k in ("seq", "id", "from_version",
                                        "to_version", "checksum")}
                   for row in ledger],
        "exporter": migrations.code_identity(),
        "exported_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds"),
        "by": by,
        "marks": [{"id": root, "kind": kind}],
        "origin_heads": heads,
        "blobs_missing": missing,
        "blobs_purged": sorted(cl.purged),
    }
    written = fmt.write(out, manifest=manifest, entries=entries, acts=acts,
                        definitions=definitions, evidence=evidence,
                        stubs=stubs, blobs=blobs)
    return {"path": out, **written}
