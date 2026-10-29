"""`mentis brain import --preview`: what an import WOULD do. Writes nothing.

`classify(store, export) -> Plan` is the SHARED CONTRACT the later apply
consumes. A Plan says, for every row of the export, whether it is

  new        its id is absent here
  identical  same id, same fingerprint: already here, skipped -- or a row an
             earlier import wrote here rewritten, arriving as it did then
             (its `import-applied` act records both fingerprints)
  corrupt    same id, different fingerprint: cannot happen except by damage,
             and refuses the WHOLE import (`Plan.refused`)
  diverged   it continues a version line that this Brain continued too

with the reason, and it lists the conflicts the owner must see first:

  diverged-line   both sides superseded the same version: "named X here,
                  Y there", "edited here, deleted there" (design §5) -- and
                  a rename THERE of a Conversation, Topic or Participant that
                  stands here, though nothing here renamed it: the door
                  would write it as a proposal, which lists as a second one
  renumbering     Turns arriving by their original time renumber later Turns
                  here, shown as "#812 -> #815" (O3). Shown, never blocking;
                  computed LAST, over exactly the rows the apply would write
                  (`_select`), so it equals what the apply records
  unresolved-name an incoming Participant is absent here and its alias names
                  somebody here, or a former name here (O4: always ask)
  name-refused    its alias is one no Participant may take here
  kind-differs    a Kind or Relation the rows were written under has no
  kind-absent     identical body here: refused with a field-level difference,
                  and so are its dependents (O6)
  answered-both   a question answered here and there: this Brain's answer is
                  kept and the other shown (O7). Any answer kept out keeps
                  out the reply Turn that says it (`answer_replies`)
  refused-act     an act an import never writes: outside the meaning-giving
                  acts, or an answer that would let work waiting here resume;
                  and "decision form not carried": a form travels whole, so
                  one with a question still open there is kept out with all
                  its acts (written open, it would be a decision owed here)
  refused-row     an `establishes`, `scoped-to` or `carries-intake` link:
                  standing never travels, whatever the file says

A row blocked by a conflict keeps its class and names the conflicts in
`blocked_by`; everything not blocked could still be applied (design §5: an
unresolved conflict blocks that line only).

Before any of it the two schema ledgers must be identical, row for row (ids
and checksums), or the preview is refused (`ExchangeRefused`).
"""

from __future__ import annotations

import collections
import dataclasses
import json

from mentis.conversation import (
    CONTRIBUTION, CONVERSATION, DECISION_ANSWERED, DECISION_FORM,
    DECISION_FORM_ATTACHED, IN_CONVERSATION, PARTICIPANT)
from mentis.spine.imported import STRUCTURAL_KINDS

from . import ExchangeRefused, format as fmt
from ._rows import Reader, one_read, store_of
from ._select import (CORRUPT, DIVERGED, IDENTICAL, NEW, rewrites_recorded,
                      select)
from .export import (EXPECTATION_MET, EXPECTATION_RECORDED, MEANING_ACTS,
                     never_carried)
from .identity import identity_from

#: acts on this Brain that say work here was started, waited or resumed under
#: a request -- an answer closing a question of that request could resume it
RUN_ACTS = ("execution-started", "work-resumed", "work-awaited",
            "result-returned", "delivery-failed", "result-recovered")
ANSWER_ACTS = (DECISION_ANSWERED, EXPECTATION_MET)
#: the act an apply records itself by (`apply.IMPORT_APPLIED`)
IMPORT_APPLIED = "import-applied"


@dataclasses.dataclass
class RowPlan:
    id: str
    table: str                      # "entry" | "act"
    kind: str | None                # Kind, Relation or act name
    state: str                      # new | identical | corrupt | diverged
    reason: str
    fingerprint: str
    blocked_by: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Conflict:
    id: str
    type: str
    subject: str | None
    words: str
    detail: dict = dataclasses.field(default_factory=dict)
    blocks: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Plan:
    manifest_sha256: str
    origin: dict
    receiver: dict
    ledger_identical: bool
    rows: list
    conflicts: list
    kinds: list                     # definition (name, version) -> here
    evidence: list
    stubs: list
    refused: list                   # reasons the WHOLE import is refused
    counts: dict

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)

    def row(self, rid) -> RowPlan | None:
        return next((r for r in self.rows if r.id == rid), None)


def _ledger_key(rows) -> list:
    return [(r.get("id"), r.get("checksum")) for r in rows]


def ledger_refusal(mine: list, theirs: list) -> str | None:
    a, b = _ledger_key(mine), _ledger_key(theirs)
    if a == b:
        return None
    for i, (x, y) in enumerate(zip(a, b), start=1):
        if x != y:
            return (f"the schema ledgers differ at row {i}: here {x[0]} "
                    f"({str(x[1])[:12]}), in the export {y[0]} "
                    f"({str(y[1])[:12]})")
    return (f"the schema ledgers differ in length: {len(a)} rows here, "
            f"{len(b)} in the export")


def _kind(row) -> str | None:
    if fmt.is_act(row):
        return row.get("act")
    link = row.get("link") or {}
    return link.get("relation") or (row.get("definition") or {}).get("name")


def _body(row) -> dict:
    b = row.get("body")
    if isinstance(b, str):
        try:
            b = json.loads(b)
        except ValueError:
            return {}
    return b if isinstance(b, dict) else {}


def _alias_key(alias) -> str:
    return str(alias or "").strip().lstrip("@").casefold()


def _say(entry) -> str:
    b = _body(entry)
    kind = (entry.get("definition") or {}).get("name") or entry.get("def_name")
    if kind == "deletion":
        return "deleted"
    for key in ("name", "alias"):
        if b.get(key):
            return f"named {b[key]!r}" if key == "name" else f"called {b[key]}"
    return f"edited ({entry['id']})"


def _definition_diff(theirs: dict, mine: dict) -> dict:
    tf, mf = list(theirs.get("fields") or ()), list(mine.get("fields") or ())
    changed = {}
    for key in sorted((set(theirs) | set(mine)) - {"fields"}):
        if theirs.get(key) != mine.get(key):
            changed[key] = {"here": mine.get(key), "there": theirs.get(key)}
    return {"fields_added": [f for f in tf if f not in mf],
            "fields_removed": [f for f in mf if f not in tf],
            "properties_changed": changed}


def _words_of_diff(name, d) -> str:
    bits = []
    if d["fields_added"]:
        bits.append(f"fields only there: {d['fields_added']}")
    if d["fields_removed"]:
        bits.append(f"fields only here: {d['fields_removed']}")
    if d["properties_changed"]:
        bits.append(f"properties that differ: "
                    f"{sorted(d['properties_changed'])}")
    return f"{name!r} differs here: " + ("; ".join(bits) or "its body differs")


class _Classifier:
    def __init__(self, reader: Reader, export: fmt.Export):
        self.r, self.x = reader, export
        self.conflicts: list[Conflict] = []
        self.entries = {e["id"]: e for e in export.entries}
        self.acts = {a["id"]: a for a in export.acts}
        self.plans: dict[str, RowPlan] = {}
        self.sup_here = reader.supersedes()
        defs = [d for d in export.definitions if d.get("body")]
        self.sup_there = next((d["body"].get("relation") for d in defs
                               if d["body"].get("substrate_role")
                               == "supersedes"), self.sup_here)
        self.never = never_carried(reader)

    def conflict(self, type_, subject, words, detail=None, blocks=()):
        c = Conflict(id=f"c{len(self.conflicts) + 1}", type=type_,
                     subject=subject, words=words, detail=detail or {},
                     blocks=sorted(set(blocks)))
        self.conflicts.append(c)
        for rid in c.blocks:
            if rid in self.plans and c.id not in self.plans[rid].blocked_by:
                self.plans[rid].blocked_by.append(c.id)
        return c

    # -- each row -----------------------------------------------------------

    def rows(self):
        here_e = self.r.entries(self.entries)
        here_a = self.r.acts_by_ids(self.acts)
        rewrites = rewrites_recorded(self.r, IMPORT_APPLIED)
        for table, rows, here in (("entry", self.x.entries, here_e),
                                  ("act", self.x.acts, here_a)):
            for row in rows:
                fp = fmt.fingerprint(row)
                mine = here.get(row["id"])
                rewrite = None if mine is None else self._rewritten(
                    rewrites.get(row["id"]), fp, mine)
                if mine is None:
                    state, why = NEW, "not in this Brain"
                elif fmt.fingerprint(mine) == fp:
                    state, why = IDENTICAL, "already here, the same"
                elif rewrite is not None:
                    state, why = IDENTICAL, (
                        f"already here, rewritten on import (written as "
                        f"{rewrite['written_as']})")
                else:
                    state, why = CORRUPT, ("this Brain holds a different row "
                                           "under the same id")
                self.plans[row["id"]] = RowPlan(
                    id=row["id"], table=table, kind=_kind(row), state=state,
                    reason=why, fingerprint=fp)

    @staticmethod
    def _rewritten(recorded, fp, mine) -> dict | None:
        """The earlier import's record of writing this row here as other
        than it arrived, when `fp` is the fingerprint it arrived with and
        the row here is the one that import wrote (ent-4b4f11a83d1d). A row
        that differs any other way is still corrupt."""
        here = fmt.fingerprint(mine)
        for r in recorded or ():
            if r.get("fingerprint") == fp and \
                    r.get("written_fingerprint") == here:
                return r
        return None

    # -- version lines ------------------------------------------------------

    def _sup_links_there(self) -> list:
        return [e for e in self.x.entries
                if (e.get("link") or {}).get("relation") == self.sup_there]

    def lines(self):
        there = self._sup_links_there()
        by_to = collections.defaultdict(list)
        for link in there:
            by_to[link["link"]["to"]].append(link)
        shared = [rid for rid, p in self.plans.items()
                  if p.table == "entry" and p.state == IDENTICAL
                  and not self.entries[rid].get("link")]
        here = collections.defaultdict(list)
        for link in self.r.links(relations=[self.sup_here], to_any=shared):
            here[link["link_to"]].append(link)
        for eid in shared:
            mine = {x["id"]: x for x in here.get(eid, [])}
            theirs = {x["id"]: x for x in by_to.get(eid, [])}
            only_here = [mine[k] for k in mine if k not in theirs]
            only_there = [theirs[k] for k in theirs if k not in mine]
            if not only_there:
                continue
            # A RENAME THERE OF STRUCTURE THAT STANDS HERE is the same
            # conflict, though only one side renamed: the door would write
            # its supersession as a proposal (it would end standing here),
            # and a proposed version is not a later version to the readers
            # that list Conversations and Participants, so it would list as
            # a second one. Its version, link and act are not sent; the
            # owner renames here if they want the other name.
            if not only_here and not (
                    self.plans[eid].kind in STRUCTURAL_KINDS
                    and self._stands_here(eid)):
                continue
            blocked = self._downstream(only_there, by_to)
            for rid in blocked:
                p = self.plans.get(rid)
                if p is not None and p.state == NEW:
                    p.state = DIVERGED
                    p.reason = (f"continues the version line of {eid}, "
                                f"which this Brain continued differently")
            head_here = self._head_here(only_here[-1]["link_from"]
                                        if only_here else eid)
            head_there = self._head_there(only_there[-1]["link"]["from"],
                                          by_to)
            root = self._root_there(eid)
            self.conflict(
                "diverged-line", root,
                f"{_say(head_here)} here, {_say(head_there)} there",
                {"at": eid, "here": head_here["id"],
                 "there": head_there["id"],
                 "here_links": [x["id"] for x in only_here],
                 "there_links": [x["id"] for x in only_there]},
                blocks=blocked)

    def _counts(self, link_id, memo) -> bool:
        """Is this link here still in force: not superseded by a link that
        is (`imported._counts`, over this read)."""
        if link_id in memo:
            return memo[link_id]
        memo[link_id] = True                      # guards a cycle
        for other in self.r.links(relations=[self.sup_here],
                                  to_any=[link_id]):
            if self._counts(other["id"], memo):
                memo[link_id] = False
                break
        return memo[link_id]

    def _stands_here(self, eid) -> bool:
        """`Corpus.stands(eid)["stands"]` on this Brain, over this read."""
        est, memo = self.r.establishes(), {}
        established = superseded = False
        for link in self.r.links(relations=[est, self.sup_here],
                                 to_any=[eid]):
            if not self._counts(link["id"], memo):
                continue
            if link["link_relation"] == est:
                established = True
            else:
                superseded = True
        return established and not superseded

    def _downstream(self, links, by_to) -> set:
        out, todo = set(), list(links)
        while todo:
            link = todo.pop()
            if link["id"] in out:
                continue
            out.add(link["id"])
            newer = link["link"]["from"]
            out.add(newer)
            todo.extend(by_to.get(newer, []))
        for a in self.x.acts:
            d = a.get("detail") or {}
            if d.get("version") in out or d.get("link") in out:
                out.add(a["id"])
        return out

    def _head_here(self, eid) -> dict:
        seen = {eid}
        while True:
            newer = self.r.links(relations=[self.sup_here], to_any=[eid])
            nxt = newer[-1]["link_from"] if newer else None
            if nxt is None or nxt in seen:
                break
            seen.add(nxt)
            eid = nxt
        row = self.r.entries([eid]).get(eid)
        rec = dict(row)
        rec["body"] = _body(row)
        rec["definition"] = {"name": row["def_name"]}
        return rec

    def _head_there(self, eid, by_to) -> dict:
        seen = {eid}
        while by_to.get(eid):
            nxt = by_to[eid][-1]["link"]["from"]
            if nxt in seen:
                break
            seen.add(nxt)
            eid = nxt
        return self.entries[eid]

    def _root_there(self, eid) -> str:
        older = {x["link"]["from"]: x["link"]["to"]
                 for x in self._sup_links_there()}
        seen = {eid}
        while eid in older and older[eid] not in seen:
            eid = older[eid]
            seen.add(eid)
        return eid

    # -- O3: Turn numbers ---------------------------------------------------

    def renumbering(self, send: set):
        """Computed LAST, over exactly the rows the apply would write
        (`send`, the settled `_select.Selection`): a Turn kept out by any
        conflict, or by what it depends on, arrives nowhere and renumbers
        nothing (review ent-cca01f8347bb, finding 4). A Turn is numbered
        when its Contribution and its place in the Conversation are both
        written, as `apply.numbering` reads it afterwards."""
        convs = [rid for rid, p in self.plans.items()
                 if p.state == IDENTICAL and p.kind == CONVERSATION]
        for cid in convs:
            homes = self.r.links(relations=[IN_CONVERSATION], to_any=[cid])
            turns = self.r.entries(h["link_from"] for h in homes)
            here = sorted(((t["recorded_at"], t["seq"], t["id"])
                           for t in turns.values()
                           if t["def_name"] == CONTRIBUTION),
                          key=lambda x: (x[0], x[1]))
            known = {t[2] for t in here}
            arriving = []
            for e in self.x.entries:
                link = e.get("link") or {}
                turn = self.entries.get(link.get("from"))
                if (link.get("relation") != IN_CONVERSATION
                        or link.get("to") != cid or e["id"] not in send
                        or turn is None or turn["id"] not in send
                        or turn["id"] in known
                        or (turn.get("definition") or {}).get("name")
                        != CONTRIBUTION or turn.get("link")):
                    continue
                known.add(turn["id"])
                arriving.append(turn)
            # in the order the apply appends them, so ties in time number
            # as the written rows' `seq` will
            order = {e["id"]: i for i, e in enumerate(self.x.entries)}
            arriving.sort(key=lambda t: order[t["id"]])
            if not arriving:
                continue
            merged = [(t[0], t[2], "here") for t in here] + [
                (a["recorded_at"], a["id"], "there") for a in arriving]
            merged.sort(key=lambda x: x[0])          # stable: here first
            before = {t[2]: i for i, t in enumerate(here, start=1)}
            after = {t[1]: i for i, t in enumerate(merged, start=1)}
            moved = [{"turn": tid, "before": n, "after": after[tid]}
                     for tid, n in before.items() if after[tid] != n]
            new_at = [{"turn": a["id"], "at": after[a["id"]]}
                      for a in arriving]
            if not moved:
                continue
            words = ", ".join(f"#{m['before']} -> #{m['after']}"
                              for m in moved)
            self.conflict(
                "renumbering", cid,
                f"{len(moved)} Turn(s) here would be renumbered: {words}",
                {"conversation": cid, "renumbered": moved,
                 "arriving": new_at})

    # -- O4: Participants ---------------------------------------------------

    def _lines_here(self, kind) -> dict:
        """root -> [versions oldest first] for every node of `kind` here."""
        nodes = {n["id"]: n for n in self.r.nodes_of(kind)}
        newer = {}
        for link in self.r.links(relations=[self.sup_here],
                                 frm_any=list(nodes)):
            if link["link_to"] in nodes:
                newer.setdefault(link["link_to"], link["link_from"])
        older = {v: k for k, v in newer.items()}
        out = {}
        for nid in nodes:
            if nid in older:
                continue
            line, cur, seen = [nodes[nid]], nid, {nid}
            while cur in newer and newer[cur] not in seen:
                cur = newer[cur]
                seen.add(cur)
                line.append(nodes[cur])
            out[nid] = line
        return out

    def participants(self):
        from mentis.conversation.participant_names import (alias_problem,
                                                           reserved_as)
        here = self._lines_here(PARTICIPANT)
        current = collections.defaultdict(list)
        former = collections.defaultdict(list)
        for pid, line in here.items():
            names = [_body(v).get("alias") for v in line]
            current[_alias_key(names[-1])].append(pid)
            for n in names[:-1]:
                if n and _alias_key(n) != _alias_key(names[-1]):
                    former[_alias_key(n)].append((pid, names[-1]))
        there_newer, versions = {}, set()
        sup_there = self._sup_links_there()
        for link in sup_there:
            there_newer.setdefault(link["link"]["to"], link["link"]["from"])
            versions.add(link["link"]["from"])
        for pid, p in self.plans.items():
            row = self.entries.get(pid)
            if (p.state != NEW or row is None or row.get("link")
                    or p.kind != PARTICIPANT or pid in versions):
                continue
            line, cur = [pid], pid
            while cur in there_newer and there_newer[cur] not in line:
                cur = there_newer[cur]
                line.append(cur)
            alias = _body(self.entries[cur]).get("alias")
            key = _alias_key(alias)
            blocks = line + [x["id"] for x in sup_there
                             if x["link"]["from"] in line]
            if current.get(key):
                self.conflict(
                    "unresolved-name", pid,
                    f"{alias} is new to this Brain, and {alias} already "
                    f"names somebody here: the same somebody, or a new "
                    f"Participant?",
                    {"alias": alias, "here": current[key]}, blocks=blocks)
            elif former.get(key):
                (who, now), = former[key][:1]
                self.conflict(
                    "unresolved-name", pid,
                    f"{alias} is new to this Brain, and {alias} is a former "
                    f"name of {now} here: the same somebody, or a new "
                    f"Participant with another name?",
                    {"alias": alias, "former_name_of": who, "now": now},
                    blocks=blocks)
            elif alias_problem(alias) or reserved_as(alias):
                self.conflict(
                    "name-refused", pid,
                    f"{alias} is not a name a Participant may take here: "
                    f"{alias_problem(alias) or 'it reads as ' + repr(reserved_as(alias))}",
                    {"alias": alias}, blocks=blocks)

    # -- O6: Kinds and Relations -------------------------------------------

    def kinds(self) -> list:
        out = []
        for d in self.x.definitions:
            name, version = d["name"], d["version"]
            if d.get("fixed"):
                out.append({"name": name, "version": version,
                            "here_version": version, "state": "fixed"})
                continue
            mine = self.r.definitions_named(name)
            same = [m for m in mine if d.get("body_sha256") and
                    fmt.body_sha256(_body(m)) == d["body_sha256"]]
            if same:
                out.append({"name": name, "version": version,
                            "here_version": same[0]["def_version"],
                            "state": "identical"})
                continue
            using = [rid for rid, row in self.entries.items()
                     if (row.get("definition") or {}).get("name") == name
                     and (row.get("definition") or {}).get("version")
                     == version]
            blocked = self._dependents(using)
            if not mine:
                out.append({"name": name, "version": version,
                            "here_version": None, "state": "absent"})
                self.conflict(
                    "kind-absent", name,
                    f"{name!r} (version {version}) is not defined in this "
                    f"Brain, so what was written under it is refused, with "
                    f"what depends on it",
                    {"name": name, "version": version,
                     "there": d.get("body")}, blocks=blocked)
                continue
            current = max(mine, key=lambda m: m["def_version"])
            diff = _definition_diff(d.get("body") or {}, _body(current))
            out.append({"name": name, "version": version,
                        "here_version": None, "state": "differs",
                        "compared_with": current["def_version"],
                        "difference": diff})
            self.conflict(
                "kind-differs", name,
                _words_of_diff(name, diff) + " -- what was written under it "
                "is refused, with what depends on it",
                {"name": name, "version": version,
                 "compared_with": current["def_version"], "difference": diff},
                blocks=blocked)
        return out

    def _dependents(self, ids) -> list:
        out = set(ids)
        grew = True
        while grew:
            grew = False
            for rid, row in self.entries.items():
                link = row.get("link") or {}
                if rid not in out and (link.get("from") in out
                                       or link.get("to") in out):
                    out.add(rid)
                    grew = True
            for aid, a in self.acts.items():
                if aid in out:
                    continue
                d = a.get("detail") or {}
                named = {a.get("turn"), a.get("conversation"),
                         a.get("caused_by"), *(a.get("about") or ()),
                         d.get("version"), d.get("reply")}
                if named & out:
                    out.add(aid)
                    grew = True
        return sorted(x for x in out if x in self.plans)

    # -- O7 and refused acts ------------------------------------------------

    def acts_refused(self):
        form_questions = {aid for aid, a in self.acts.items()
                          if a["act"] == EXPECTATION_RECORDED
                          and (a.get("detail") or {}).get("form")}
        for aid, a in self.acts.items():
            why = None
            if a["act"] not in MEANING_ACTS:
                why = (f"{a['act']!r} is not an act an import writes: only "
                       f"what gives a Turn its meaning travels, never a run "
                       f"or a dispatch")
            elif a["act"] == EXPECTATION_RECORDED and aid not in form_questions:
                why = ("an expectation that is not a decision form's "
                       "question would put work owed on this Brain")
            if why:
                self.conflict("refused-act", aid, why, {"act": a["act"]},
                              blocks=self._dependents([aid]))
        for rid, row in self.entries.items():
            rel = (row.get("link") or {}).get("relation")
            if rel in self.never:
                self.conflict(
                    "refused-row", rid,
                    f"a {rel!r} link puts something in force; standing does "
                    f"not travel, so it is never written",
                    {"relation": rel}, blocks=[rid])

    def answers(self):
        answers = [a for a in self.x.acts if a["act"] in ANSWER_ACTS
                   and self.plans[a["id"]].state == NEW]
        if not answers:
            return
        questions = sorted({a["caused_by"] for a in answers if a["caused_by"]})
        here_q = self.r.acts_by_ids(questions)
        here_ans = collections.defaultdict(list)
        for row in self.r.acts("act IN (?, ?) AND caused_by IN "
                               "(SELECT value FROM json_each(?))",
                               (*ANSWER_ACTS, json.dumps(questions))):
            here_ans[row["caused_by"]].append(row)
        for a in answers:
            q = a["caused_by"]
            mine = [x for x in here_ans.get(q, []) if x["id"] != a["id"]]
            if mine:
                kept = mine[0]
                self.conflict(
                    "answered-both", q,
                    f"answered here ({_answer_words(kept)}) and on the other "
                    f"machine ({_answer_words(a)}); this Brain's answer is "
                    f"kept and the other is shown, not written",
                    {"question": q, "here": kept["id"], "there": a["id"],
                     "here_answer": _answer(kept), "there_answer": _answer(a)},
                    blocks=self._dependents([a["id"]]))
                continue
            asked = here_q.get(q)
            if asked is None or not asked["caused_by"]:
                continue
            req = asked["caused_by"]
            runs = self.r.acts(
                "act IN (SELECT value FROM json_each(?)) AND "
                "(caused_by = ? OR id = ?)", (json.dumps(RUN_ACTS), req, req))
            if runs:
                self.conflict(
                    "refused-act", a["id"],
                    "this answer would close a question that work here is "
                    "waiting on, and so let that work resume; it is shown, "
                    "not written",
                    {"question": q, "request": req,
                     "runs": [x["id"] for x in runs]},
                    blocks=self._dependents([a["id"]]))

    def answer_replies(self):
        """An answer kept out keeps out the reply Turn that carries it
        (ent-8df809da5880). The reply IS the answer in words: arrived on its
        own it would stand under the form's post as the other machine's
        "Yes" beside this Brain's kept "No". So the reply, and what is
        about it, is blocked by the same conflicts that block its answer."""
        by_id = {c.id: c for c in self.conflicts}
        for aid, a in self.acts.items():
            p = self.plans[aid]
            if a["act"] not in ANSWER_ACTS or not p.blocked_by:
                continue
            reply = (a.get("detail") or {}).get("reply")
            if reply not in self.entries or self.plans[reply].state != NEW:
                continue
            held = [r for r in self._dependents([reply])
                    if self.plans[r].state == NEW]
            for cid in p.blocked_by:
                c = by_id[cid]
                c.blocks = sorted(set(c.blocks) | set(held))
                c.detail.setdefault("replies_held_back", [])
                if reply not in c.detail["replies_held_back"]:
                    c.detail["replies_held_back"].append(reply)
                for r in held:
                    if cid not in self.plans[r].blocked_by:
                        self.plans[r].blocked_by.append(cid)

    def replies_held(self, sel):
        """Each reply the selection held back as answering work open here
        (`_select.Selection.hold_replies`, the door's rule), shown as the
        conflict that keeps it, and its post, out. Its dependents are kept
        out by the selection as depending on them."""
        for lid, (post, why) in sorted(sel.held_replies.items()):
            self.conflict(
                "answers-work-here", lid,
                f"reply {lid}" + (f" and its post {post}" if post else "")
                + f" not applied: {why}",
                {"link": lid, "post": post},
                blocks=[lid] + ([post] if post else []))

    def responses_held(self, sel):
        """Each response-set entry the selection held back as answering an input
        open here (R2), shown as an answers-work-here conflict."""
        for rid, why in sorted(sel.held_responses.items()):
            self.conflict(
                "answers-work-here", rid,
                f"response-set entry {rid} not applied: {why}",
                {"entry": rid},
                blocks=[rid])

    # -- decision forms ------------------------------------------------------

    def forms(self):
        """A decision form travels whole, or not at all.

        Its two acts name the run that asked it, and that is inert here: no
        `execution-started` of it is here, so nothing examines, resumes or
        attaches anything for it (`imported.EXECUTION_INERT_ACTS`). What is
        NOT inert is a question still open: a question is an expectation of
        somebody, so written open here it would be a decision owed on this
        Brain, about a run this Brain never had. So a form travels only
        when every one of its new questions arrives closed -- answered, or
        withdrawn, by an act that is carried and not itself kept out. A
        form with an open question is kept out with all of its acts."""
        q_of = collections.defaultdict(list)
        for aid, a in self.acts.items():
            if a["act"] == EXPECTATION_RECORDED:
                form = (a.get("detail") or {}).get("form")
                if form:
                    q_of[form].append(aid)
        closes = collections.defaultdict(list)
        for aid, a in self.acts.items():
            if a["act"] in ANSWER_ACTS and a.get("caused_by"):
                closes[a["caused_by"]].append(aid)
        for form, questions in sorted(q_of.items()):
            open_ = [q for q in questions
                     if self.plans[q].state == NEW
                     and not any(not self.plans[x].blocked_by
                                 for x in closes.get(q, ()))]
            if not open_:
                continue
            group = {form, *questions}
            for aid, a in self.acts.items():
                d = a.get("detail") or {}
                if (a.get("caused_by") in group or d.get("form") == form) \
                        and a["act"] in (DECISION_FORM_ATTACHED,
                                         *ANSWER_ACTS, EXPECTATION_RECORDED):
                    group.add(aid)
            group = {g for g in group if g in self.plans
                     and self.plans[g].state == NEW}
            self.conflict(
                "refused-act", form,
                f"decision form not carried: {len(open_)} of its questions "
                f"are still open on the other machine, and written here each "
                f"would be a decision owed on this Brain for a run it never "
                f"had",
                {"form": form, "open_questions": sorted(open_),
                 "act": DECISION_FORM}, blocks=self._dependents(group))

    # -- what does not travel, and what was not carried --------------------

    def evidence(self) -> list:
        out = []
        ids = [e["entry"] for e in self.x.evidence]
        est = self.r.establishes()
        standing_here = collections.defaultdict(list)
        for link in self.r.links(relations=[est], to_any=ids):
            standing_here[link["link_to"]].append(link["id"])
        for e in self.x.evidence:
            p = self.plans.get(e["entry"])
            here = "new here" if p is None or p.state == NEW else "here"
            if e.get("established") and here == "new here":
                arrives = "would arrive as a candidate: not established here"
            elif e.get("established"):
                arrives = ("established here too" if standing_here.get(
                    e["entry"]) else "here, and not established here")
            else:
                arrives = "not established on the other machine"
            out.append({**e, "here": here, "arrives": arrives})
        return out

    def stubs(self) -> list:
        ids = [s["id"] for s in self.x.stubs]
        es, acts = self.r.entries(ids), self.r.acts_by_ids(ids)
        return [{**s, "here": ("in this Brain" if s["id"] in es
                               or s["id"] in acts else "not in this Brain")}
                for s in self.x.stubs]


def _answer(a) -> dict:
    d = a.get("detail") or {}
    if isinstance(d, str):
        d = json.loads(d or "{}")
    return {k: d[k] for k in ("option", "label", "words", "withdrawn",
                              "lapsed", "reply") if k in d} | {"by": a.get("actor"),
                                                     "at": a.get("at")}


def _answer_words(a) -> str:
    d = _answer(a)
    if d.get("withdrawn"):
        return "withdrawn"
    if d.get("lapsed"):
        # a run's permission question nothing could consume any more
        return "no longer asked"
    return str(d.get("label") or d.get("words") or d.get("option") or "?")


def classify(store, export: fmt.Export) -> Plan:
    """The Plan for importing `export` into the Brain behind `store` (a
    Store or Corpus, opened read-only). Reads, in one read transaction;
    writes nothing. Refused (`ExchangeRefused`) unless the two schema
    ledgers are identical."""
    st = store_of(store)
    with one_read(st) as r:
        refusal = ledger_refusal(r.ledger(), export.manifest.get("ledger")
                                 or [])
        if refusal:
            raise ExchangeRefused(refusal + "; an import needs both Brains "
                                  "at the same schema, row for row")
        c = _Classifier(r, export)
        c.rows()
        c.lines()
        c.participants()
        kinds = c.kinds()
        c.acts_refused()
        c.answers()
        c.forms()
        c.answer_replies()
        # LAST: over exactly what the apply would write (finding 4)
        sel, _ = select(r, list(c.plans.values()), c.conflicts, export,
                        st.root, store=st, read=False)
        c.replies_held(sel)
        c.responses_held(sel)
        c.renumbering(sel.send)
        evidence = c.evidence()
        stubs = c.stubs()
        receiver = identity_from(r)
    rows = list(c.plans.values())
    corrupt = [p.id for p in rows if p.state == CORRUPT]
    refused = ([f"{len(corrupt)} row(s) hold different content here under "
                f"the same id ({', '.join(corrupt[:5])}); that cannot happen "
                f"except by damage, so nothing may be imported"]
               if corrupt else [])
    new_by_kind = collections.Counter(p.kind for p in rows if p.state == NEW)
    counts = {
        "new": sum(new_by_kind.values()),
        "new_by_kind": dict(sorted(new_by_kind.items(),
                                   key=lambda kv: str(kv[0]))),
        "identical": sum(1 for p in rows if p.state == IDENTICAL),
        "diverged": sum(1 for p in rows if p.state == DIVERGED),
        "corrupt": len(corrupt),
        "blocked": sum(1 for p in rows if p.blocked_by),
        "conflicts": len(c.conflicts),
        "evidence": len(evidence),
        "stubs": len(stubs),
        "blobs": len(export.blob_digests),
    }
    origin = export.origin
    return Plan(
        manifest_sha256=export.manifest_sha256, origin=origin,
        receiver={**receiver,
                  "same_lineage": receiver["corpus_id"]
                  == origin.get("corpus_id"),
                  "same_fork": receiver["fork_id"] == origin.get("fork_id")},
        ledger_identical=True, rows=rows, conflicts=c.conflicts, kinds=kinds,
        evidence=evidence, stubs=stubs, refused=refused, counts=counts)


def describe(plan: Plan) -> str:
    """The Plan in plain language, for a person."""
    n = plan.counts
    out = [f"Import preview (nothing was written). Export {plan.manifest_sha256[:12]} "
           f"from {plan.origin.get('fork_id')}"
           + (" -- the same lineage as this Brain"
              if plan.receiver.get("same_lineage") else
              " -- a different Brain from this one")
           + "."]
    if plan.refused:
        out.append("REFUSED: " + " ".join(plan.refused))
    out.append(f"New: {n['new']}"
               + (" (" + ", ".join(f"{v} {k}" for k, v in
                                   n["new_by_kind"].items()) + ")"
                  if n["new_by_kind"] else ""))
    out.append(f"Already here: {n['identical']}.")
    if n["diverged"]:
        out.append(f"Diverged: {n['diverged']} row(s) continue a line this "
                   f"Brain continued differently.")
    if plan.conflicts:
        out.append(f"Conflicts ({len(plan.conflicts)}):")
        for c in plan.conflicts:
            tail = (f" [blocks {len(c.blocks)} row(s)]" if c.blocks else "")
            out.append(f"  - {c.type}: {c.words}{tail}")
    else:
        out.append("Conflicts: none.")
    candidates = [e for e in plan.evidence
                  if e["arrives"].startswith("would arrive")]
    if plan.evidence:
        out.append(f"Standing that does not travel: {len(plan.evidence)} "
                   f"item(s); {len(candidates)} would arrive as candidates, "
                   f"established on the other machine and not here.")
    if plan.stubs:
        absent = sum(1 for s in plan.stubs if s["here"] != "in this Brain")
        out.append(f"Referenced and not carried: {len(plan.stubs)} "
                   f"({absent} not in this Brain).")
    return "\n".join(out)
