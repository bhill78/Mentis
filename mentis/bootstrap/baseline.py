"""Seed a Brain with the baseline every Brain starts from.

    python -m mentis.bootstrap.baseline <brain> --owner @alias
        [--runtime claude] [--match KEY=<entry>|new ...] [--check]

WHAT IT IS. baseline.json is versioned release data: the owner and @Caretaker
Participants, five Personas, four rules, one decision, one Discipline, one
Workflow, and the designation that @Caretaker carries intake wearing the
Caretaker Persona. Every item has a stable key. Nothing here is a new kind of
record: an item is an ordinary Persona, rule, decision, Discipline or Workflow
entry, written as the owner with its origin stamped
`bootstrap:<baseline>@<version>/<key>`, and the run records one
`bootstrap-applied` act mapping each key to the entry that carries it here.

ONE ITEM NAMES ANOTHER BY ITS KEY. A Workflow's activities name a Persona and
a Discipline, which are entries of THIS Brain, so the release data says
`baseline:<key>` and the run writes the entry that item has here (the
current one, or the proposal this run writes for it). The digest is of the
shipped text, keys and all, so it is the same in every Brain; whether an
entry already carries an item is asked of the text with its keys resolved.
A Persona, Discipline or Workflow is matched by name as well as by text.

FIRST INSTALLATION is run by the owner and ESTABLISHES what it writes, the way
the owner creating it by hand would. In a Brain that already holds material,
an item whose exact text stands is MATCHED and nothing is written for it; a
Persona of the same name with other text is the owner's and keeps standing,
with the shipped text PROPOSED to supersede it. A rule or decision has no name
to match by, so where the Brain already holds standing material of that Kind
and none carries the text, the run refuses rather than guess: the owner names
the counterpart with `--match key=<entry>`, or says `--match key=new`.

A LATER VERSION never establishes and never overwrites. For each item whose
shipped text changed it proposes the new text to supersede the CURRENT item,
which is the newest standing entry in its supersession chain, including an
owner's own successor. An item already carrying the text, or already proposed
with it, gets nothing. Items no longer shipped are reported, not retired. New
items arrive as proposals. Running the same version again writes nothing.

EVERY RUN VALIDATES what it relies on before it reports success, inside the
same transaction: each key resolves to an entry of its Kind in THIS Brain, the
owner is the owner, intake resolves to the baseline's carrier wearing the
current Caretaker item through the recorded designation (or its successor),
and each recorded whole-Brain placement is a `scoped-to` link from its item
(or an entry its chain runs through) to this Brain's whole-Brain destination.
A later version checks the version it builds on the same way before it plans,
so a bad prior record refuses even under `--check`. A failure refuses and
rolls the whole run back.

`--check` plans and reports without writing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys

import mentis.api as api
from mentis.conversation import (CARRIES_INTAKE, SCOPED_TO, WHOLE_BRAIN,
                                  WHOLE_BRAIN_SCOPE)

HERE = pathlib.Path(__file__).resolve().parent
BASELINE = HERE / "baseline.json"
APPLIED = "bootstrap-applied"
STEP = "baseline"
OWNER_ABOUT = "the owner"
# In file order, and the order matters: an item that names another by key
# (`REF`) is written after it, so a Workflow follows the Personas and the
# Discipline its activities name.
SECTIONS = {"personas": "persona", "rules": "rule", "decisions": "decision",
            "lessons": "lesson", "disciplines": "discipline",
            "workflows": "workflow"}
FIELDS = {"persona": ("name", "behaviour", "about"), "rule": ("text",),
          "decision": ("text",), "lesson": ("text",),
          "discipline": ("name", "about", "text", "tools", "tool_use",
                         "requires", "inputs", "outputs", "verification",
                         "limits"),
          "workflow": ("name", "about", "projects", "text", "activities",
                       "decisions", "done_when", "evidence", "interrupted",
                       "persona", "requires")}
# What must be said; every other field may be empty.
REQUIRED = {"persona": ("name", "behaviour"), "rule": ("text",),
            "decision": ("text",), "lesson": ("text",),
            "discipline": ("name", "about", "text"),
            "workflow": ("name", "about", "text", "activities")}
# Stored as a list; absent is the empty list.
LISTS = ("tools", "requires", "projects", "activities", "decisions")
# Material with a name is matched by it, as a Persona always was.
NAMED = ("persona", "discipline", "workflow")
# Another Brain's record id in shipped text would be a live dependency on a
# Brain this one is not.
_FOREIGN_ID = re.compile(r"\b(?:ent|adm|opr|col)-[0-9a-f]{12}\b")
# Another item of this baseline, by key (see the module docstring).
REF = re.compile(r"baseline:([a-z0-9][a-z0-9-]*)")


class BootstrapRefused(ValueError):
    """Existing material needs an owner's decision, not a new default."""


def load(path=BASELINE) -> dict:
    return json.loads(pathlib.Path(path).read_text("utf-8"))


def items(spec):
    """(key, kind, body) for every shipped item, in file order."""
    for section, kind in SECTIONS.items():
        for it in spec.get(section) or []:
            yield it["key"], kind, {
                f: it.get(f, [] if f in LISTS else "") for f in FIELDS[kind]}


def digest(body) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def refs_in(value) -> list[str]:
    """The baseline keys a shipped value names, wherever they sit in it."""
    if isinstance(value, str):
        m = REF.fullmatch(value)
        return [m.group(1)] if m else []
    if isinstance(value, dict):
        return [k for v in value.values() for k in refs_in(v)]
    if isinstance(value, list):
        return [k for v in value for k in refs_in(v)]
    return []


def resolved(body, entries):
    """`body` with every `baseline:<key>` written as `entries[key]`, or None
    when a key it names has no entry here yet."""
    def walk(v):
        if isinstance(v, str):
            m = REF.fullmatch(v)
            if not m:
                return v
            if not entries.get(m.group(1)):
                raise KeyError(m.group(1))
            return entries[m.group(1)]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v
    try:
        return walk(body)
    except KeyError:
        return None


def validate_spec(spec, corpus=None):
    """Refuse broken release data before anything is written."""
    problems = []
    if not spec.get("baseline"):
        problems.append("no baseline name")
    if not isinstance(spec.get("version"), int) or spec["version"] < 1:
        problems.append("version must be a positive integer")
    kinds, order = {}, []
    for section, kind in SECTIONS.items():
        for it in spec.get(section) or []:
            key = it.get("key")
            if not isinstance(key, str) or not key:
                problems.append(f"{section}: an item has no key")
                continue
            if key in kinds:
                problems.append(f"{key}: key used twice")
            kinds[key] = kind
            order.append((key, it))
            for f in FIELDS[kind]:
                v = it.get(f, [] if f in LISTS else "")
                if f in REQUIRED[kind] and (
                        not v or (isinstance(v, str) and not v.strip())):
                    problems.append(f"{key}: {f} is missing or empty")
                elif f in LISTS and not isinstance(v, list):
                    problems.append(f"{key}: {f} is a list")
                elif f not in LISTS and not isinstance(v, str):
                    problems.append(f"{key}: {f} is missing or empty")
                elif _FOREIGN_ID.search(json.dumps(v)):
                    problems.append(
                        f"{key}: {f} names a record of another Brain "
                        f"({_FOREIGN_ID.search(json.dumps(v)).group()})")
    # A key named must be an item written BEFORE the one naming it, so its
    # entry exists here when this one is written.
    earlier = set()
    for key, it in order:
        for f in FIELDS[kinds[key]]:
            for ref in refs_in(it.get(f)):
                if ref not in earlier:
                    problems.append(f"{key}: {f} names baseline:{ref}, which "
                                    "is not an item shipped before it")
        earlier.add(key)
    people = spec.get("participants") or {}
    if (people.get("owner") or {}).get("about") != OWNER_ABOUT:
        problems.append(f"participants: owner must be about {OWNER_ABOUT!r}")
    d = spec.get("designation") or {}
    if d.get("participant") not in people or d.get("participant") == "owner":
        problems.append(f"designation: participant {d.get('participant')!r} "
                        "is not a baseline Participant")
    elif not (people[d["participant"]] or {}).get("alias"):
        problems.append(f"designation: participant {d['participant']!r} has "
                        "no alias")
    if kinds.get(d.get("persona")) != "persona":
        problems.append(f"designation: persona {d.get('persona')!r} is not a "
                        "baseline Persona")
    if corpus is not None:
        for kind in set(kinds.values()):
            got = corpus.current_definition(kind)
            allowed = (got or {}).get("body", {}).get("fields")
            if got is None or (allowed is not None
                               and not set(FIELDS[kind]) <= set(allowed)):
                # A Brain made before vocabulary revision operating-model-1
                # is revised by its tool first; this never redefines a Kind.
                problems.append(f"this Brain's {kind} Kind cannot carry "
                                f"{list(FIELDS[kind])}" + (
                                    " (apply tools/operating_vocabulary.py "
                                    "first)" if kind in ("discipline",
                                                         "workflow") else ""))
    if problems:
        raise BootstrapRefused("baseline data is broken: " + "; ".join(problems))


# -- reading this Brain --------------------------------------------------------

def _entry(corpus, eid, kind):
    got = corpus.read([eid]) if isinstance(eid, str) else []
    if (got and got[0].get("family") == "entry" and got[0].get("link") is None
            and (got[0].get("definition") or {}).get("name") == kind):
        return got[0]
    return None


def _same(body, wanted, kind) -> bool:
    return all((body or {}).get(f, "") == wanted[f] for f in FIELDS[kind])


def _current(corpus, eid, kind):
    """The newest entry in this item's supersession chain, if it stands and
    is still of the item's Kind."""
    newest = corpus.history(eid)[-1]
    if _entry(corpus, newest, kind) is None:
        return None
    return newest if corpus.stands(newest)["stands"] else None


def _proposed(corpus, eid, body, kind):
    """An open proposal to supersede `eid` that already carries `body`."""
    found = corpus.proposed_supersessions(eid) or {}
    for p in (found.get("successors") or {}).get("items", []):
        e = _entry(corpus, p["entry"], kind)
        if e and _same(e["body"], body, kind):
            return p["entry"]
    return None


def applied(cv, name=None):
    """The latest version of this baseline applied here, as its act."""
    acts = [a for a in cv.history(act=APPLIED, detail_is={"step": STEP})
            if name is None or (a.get("detail") or {}).get("baseline") == name]
    return max(acts, key=lambda a: a["detail"]["version"]) if acts else None


def check(corpus, cv, act) -> tuple[list[str], list[str]]:
    """Does what the applied baseline says still resolve here? (problems,
    notes). Reads only."""
    d = act["detail"]
    problems, notes = [], []
    for key, it in d["items"].items():
        if _entry(corpus, it["entry"], it["kind"]) is None:
            problems.append(f"{key}: {it['entry']} is not a {it['kind']} in "
                            "this Brain")
        elif _current(corpus, it["entry"], it["kind"]) is None:
            notes.append(f"{key}: no standing {it['kind']} carries it here "
                         f"({it['entry']} or its successor has ended, or "
                         "was never established)")
    owner = _entry(corpus, d.get("owner"), "participant")
    if owner is None or owner["body"].get("about") != OWNER_ABOUT:
        problems.append(f"owner {d.get('owner')} is not this Brain's owner "
                        "Participant")
    if _entry(corpus, d.get("caretaker"), "participant") is None:
        problems.append(f"carrier {d.get('caretaker')} is not a Participant "
                        "in this Brain")
    designation = d.get("designation")
    if not isinstance(designation, dict):
        designation = {}
    key, link_id = designation.get("persona"), designation.get("link")
    want = (_current(corpus, d["items"][key]["entry"], "persona")
            if key in d["items"] else None)
    now = cv.intake_carrier()
    got = corpus.read([link_id]) if isinstance(link_id, str) else []
    relation = ((got[0].get("link") or {}) if got else {}).get("relation")
    if relation != CARRIES_INTAKE:
        problems.append(f"designation {link_id} is not a {CARRIES_INTAKE} "
                        "link in this Brain")
    if not now.get("resolved"):
        problems.append(f"intake does not resolve: {now.get('detail')}")
    elif now["participant"] != d.get("caretaker"):
        problems.append(f"intake is carried by {now['alias']}, not the "
                        f"baseline carrier {d.get('caretaker')}")
    elif want is None or now["persona"] != want:
        problems.append(f"intake is carried wearing {now['persona']}, not "
                        f"the standing {key!r} Persona ({want})")
    elif (relation == CARRIES_INTAKE
          and now["designation"] not in corpus.history(link_id)):
        problems.append(f"intake resolves through {now['designation']}, "
                        f"which is not designation {link_id} or its "
                        "successor")
    placements = d.get("placements") or {}
    if not isinstance(placements, dict):
        problems.append("placements is not a mapping of baseline keys")
        placements = {}
    for key, plc in placements.items():
        problems += _placement_problems(corpus, cv, d["items"], key, plc)
        if (isinstance(plc, dict) and isinstance(plc.get("link"), str)
                and corpus.read([plc["link"]])
                and corpus.stands(plc["link"])["superseded_by"]):
            notes.append(f"{key}: placement at {plc.get('where')} was ended "
                         "by owner")
    return problems, notes


def _placement_problems(corpus, cv, recorded, key, plc) -> list[str]:
    """What is wrong with one recorded whole-Brain placement, as problems.

    The record says item `key` was placed on the whole Brain by link `link`.
    That holds only if the key is an item, the destination is this Brain's
    whole-Brain destination, and the link is a `scoped-to` link from that
    item -- or an entry its supersession chain runs through -- to that
    destination. An ended link is the owner's removal and still holds.
    """
    if not isinstance(plc, dict):
        return [f"{key}: placement is not a record of a placement"]
    where, link_id = plc.get("where"), plc.get("link")
    if key not in recorded:
        return [f"{key}: placement names no baseline item"]
    if not isinstance(where, str) or not cv.is_whole_brain(where):
        return [f"{key}: placement destination {where} is not this Brain's "
                "whole-Brain destination"]
    got = corpus.read([link_id]) if isinstance(link_id, str) else []
    link = (got[0].get("link") or {}) if got else {}
    if link.get("relation") != SCOPED_TO:
        return [f"{key}: placement link {link_id} is not a {SCOPED_TO} link "
                "in this Brain"]
    if link.get("to") != where:
        return [f"{key}: placement link {link_id} does not reach {where}"]
    if link.get("from") not in corpus.history(recorded[key]["entry"]):
        return [f"{key}: placement link {link_id} does not place "
                f"{recorded[key]['entry']} or an entry it succeeds"]
    return []


def people(corpus, cv) -> dict:
    """The owner and intake carrier the applied baseline resolves to."""
    act = applied(cv)
    if act is None:
        raise BootstrapRefused("this Brain has no baseline; run "
                               "`python -m mentis.bootstrap` first")
    problems, _ = check(corpus, cv, act)
    if problems:
        raise BootstrapRefused("the baseline does not resolve: "
                               + "; ".join(problems))
    return {"owner": act["detail"]["owner"],
            "guide": act["detail"]["caretaker"]}


# -- planning --------------------------------------------------------------------

def _plan_first(corpus, cv, spec, owner_alias, match):
    """What a first installation would write here. Reads only."""
    problems, rows, used = [], {}, {}
    is_fresh = (
        not bool(corpus.entries_of_kind("persona")
                 or corpus.entries_of_kind("rule")
                 or corpus.entries_of_kind("decision")
                 or corpus.entries_of_kind(WHOLE_BRAIN))
        and not bool(match)
    )
    for key, kind, body in items(spec):
        standing = [e for e in corpus.entries_of_kind(kind)
                    if corpus.stands(e["id"])["stands"]]
        chosen = match.pop(key, None)
        # Carried here only if the items it names are already here: one
        # still to be written has no entry its text could name.
        here = resolved(body, {k: r.get("entry") for k, r in rows.items()})
        exact = [e["id"] for e in standing
                 if here is not None and _same(e["body"], here, kind)]
        named = [e["id"] for e in standing
                 if kind in NAMED and e["body"].get("name") == body["name"]]
        if chosen == "new":
            row = {"how": "establish"}
        elif chosen:
            e = _entry(corpus, chosen, kind)
            if e is None or not corpus.stands(chosen)["stands"]:
                problems.append(f"{key}: --match {chosen} is not a standing "
                                f"{kind} in this Brain")
                continue
            row = {"how": "matched" if here is not None
                   and _same(e["body"], here, kind) else "conflict",
                   "entry": chosen}
        elif len(exact) == 1:
            row = {"how": "matched", "entry": exact[0]}
        elif len(exact) > 1:
            problems.append(f"{key}: {len(exact)} standing {kind}s carry this "
                            f"text ({', '.join(exact)}); name one with --match")
            continue
        elif len(named) == 1:
            row = {"how": "conflict", "entry": named[0]}
        elif len(named) > 1:
            problems.append(f"{key}: {len(named)} standing {kind}s are named "
                            f"{body['name']!r} ({', '.join(named)}); name one "
                            "with --match")
            continue
        elif kind not in NAMED and standing:
            problems.append(
                f"{key}: no standing {kind} carries this text and this Brain "
                f"holds {len(standing)} standing {kind}(s); name its "
                f"counterpart with --match {key}=<entry>, or --match {key}=new")
            continue
        else:
            row = {"how": "establish"}
        if row.get("entry"):
            if row["entry"] in used:
                problems.append(f"{key}: {row['entry']} is already matched to "
                                f"{used[row['entry']]}")
            used[row["entry"]] = key
        if row["how"] == "conflict" and here is not None:
            row["proposal"] = _proposed(corpus, row["entry"], here, kind)
        if is_fresh and kind in ("rule", "decision") and row["how"] == "establish":
            row["place"] = WHOLE_BRAIN_SCOPE
        rows[key] = dict(row, kind=kind, body=body)
    for key in match:
        problems.append(f"--match {key}: no such baseline item")

    owners = [p["id"] for p in cv.all_participants()
              if (p.get("body") or {}).get("about") == OWNER_ABOUT]
    named = cv.participants_named(owner_alias)
    owner = owners[0] if owners else None
    if owner is None and named:
        problems.append(f"{owner_alias} exists but is not this Brain's owner "
                        f"Participant; it is not made one by guessing")

    d = spec["designation"]
    carrier = spec["participants"][d["participant"]]
    persona = rows.get(d["persona"], {}).get("entry")
    now = cv.intake_carrier()
    caretaker, intake = None, {"how": "designate"}
    if now.get("resolved"):
        caretaker, intake = now["participant"], {
            "how": "matched", "designation": now["designation"]}
        if d["persona"] in rows and now["persona"] != persona:
            problems.append(
                f"intake is carried by {now['alias']} wearing "
                f"{now['persona']}, which is not the Persona matched for "
                f"{d['persona']!r} ({persona or 'none; it would be new'}); "
                f"if it is that Persona, say --match {d['persona']}="
                f"{now['persona']}")
    elif cv.intake_designations():
        problems.append(f"intake does not resolve ({now.get('detail')}); the "
                        "existing designations need an owner's decision")
    else:
        found = cv.participants_named(carrier["alias"])
        if len(found) > 1:
            problems.append(f"{len(found)} Participants are named "
                            f"{carrier['alias']}; which carries intake is the "
                            "owner's decision")
        caretaker = found[0] if found else None
    placements = {k: {"where": WHOLE_BRAIN_SCOPE} for k, r in rows.items()
                  if r.get("place") == WHOLE_BRAIN_SCOPE}
    return problems, {"items": rows, "placements": placements,
                      "owner": owner, "caretaker": caretaker,
                      "intake": intake}


def _plan_update(corpus, spec, prior):
    """What a newer release would propose here. Reads only."""
    before, rows = prior["detail"]["items"], {}
    for key, kind, body in items(spec):
        if key not in before:
            rows[key] = {"how": "propose-new", "kind": kind, "body": body}
            continue
        was = before[key]
        cur = _current(corpus, was["entry"], kind)
        row = {"kind": kind, "body": body, "entry": cur or was["entry"]}
        here = resolved(body, {k: r.get("entry") for k, r in rows.items()})
        if was["digest"] == digest(body):
            row["how"] = "unchanged"
        elif cur is None:
            row["how"] = "ended"           # the owner ended it; nothing to supersede
        elif here is not None and _same(_entry(corpus, cur, kind)["body"],
                                        here, kind):
            row["how"] = "matched"
        else:
            row["how"] = "propose"
            row["proposal"] = (_proposed(corpus, cur, here, kind)
                               if here is not None else None)
        rows[key] = row
    removed = sorted(set(before) - set(rows))
    placements = dict(prior["detail"].get("placements") or {})
    return [], {"items": rows, "placements": placements, "removed": removed,
                "owner": prior["detail"]["owner"],
                "caretaker": prior["detail"]["caretaker"],
                "intake": {"how": "matched",
                           "designation": prior["detail"]["designation"]["link"]}}


def plan(corpus, cv, spec, owner_alias, match=None):
    validate_spec(spec, corpus)
    prior = applied(cv, spec["baseline"])
    if prior and prior["detail"]["version"] >= spec["version"]:
        return [], {"action": "unchanged", "prior": prior}
    if prior:
        # The update builds on what the prior version recorded; a record that
        # no longer resolves is refused here, before anything is planned on
        # it, rather than carried into the new act or reported as success.
        bad, _ = check(corpus, cv, prior)
        if bad:
            return [f"the applied baseline (version "
                    f"{prior['detail']['version']}) does not resolve: "
                    + "; ".join(bad)], {"action": "update"}
        problems, out = _plan_update(corpus, spec, prior)
        out["action"] = "update"
    else:
        problems, out = _plan_first(corpus, cv, spec, owner_alias,
                                    dict(match or {}))
        out["action"] = "install"
    return problems, out


# -- writing ---------------------------------------------------------------------

def _report(spec, p, act=None):
    return {"baseline": spec["baseline"], "version": spec["version"],
            "action": p["action"], "act": act,
            "owner": p.get("owner"), "caretaker": p.get("caretaker"),
            "intake": p.get("intake"),
            "items": {k: {x: r.get(x) for x in ("how", "entry", "proposal")
                          if r.get(x)}
                      for k, r in p.get("items", {}).items()},
            "placements": p.get("placements", {}),
            "removed": p.get("removed", [])}


def install(corpus, owner_alias, *, runtime=None, match=None, spec=None,
            dry_run=False) -> dict:
    """Install or update the baseline here, or report that nothing changed."""
    spec = spec if spec is not None else load()
    cv = api.brain(corpus).conversations
    with corpus.atomic():
        problems, p = plan(corpus, cv, spec, owner_alias, match)
        if problems:
            raise BootstrapRefused("; ".join(problems))
        if p["action"] == "unchanged":
            act = p["prior"]
            problems, notes = check(corpus, cv, act)
            if problems:
                raise BootstrapRefused("the applied baseline does not resolve: "
                                       + "; ".join(problems))
            d = act["detail"]
            return {"baseline": d["baseline"], "version": d["version"],
                    "action": "unchanged", "act": act["id"],
                    "applied_version": d["version"], "owner": d["owner"],
                    "caretaker": d["caretaker"], "items": d["items"],
                    "placements": d.get("placements", {}),
                    "removed": d.get("removed", []), "notes": notes}
        if dry_run:
            return dict(_report(spec, p), dry_run=True)
        act = _apply(corpus, cv, spec, p, owner_alias, runtime)
        problems, notes = check(corpus, cv, cv.history(act=APPLIED, detail_is={
            "step": STEP, "version": spec["version"]})[-1])
        if problems:
            raise BootstrapRefused("the baseline would not resolve: "
                                   + "; ".join(problems))
    return dict(_report(spec, p, act), notes=notes)


def _written(corpus, key, row, rows) -> dict:
    """The body this item is written with here: its keys resolved to the
    entries the items it names have now (written earlier in this run, or
    already here), and put to the checks every write door puts a body to --
    the references name what they say, a requirement names a real
    capability -- because this run writes past those doors."""
    from mentis.conversation import capability_refusal, reference_refusal
    body = resolved(row["body"], {k: r.get("entry") for k, r in rows.items()})
    if body is None:
        raise BootstrapRefused(f"{key}: names a baseline item with no entry "
                               "in this Brain")
    refusal = (reference_refusal(corpus, row["kind"], body)
               or capability_refusal(corpus, row["kind"], body,
                                     api.capability_names()))
    if refusal:
        raise BootstrapRefused(f"{key}: {refusal['error']}")
    return body


def _apply(corpus, cv, spec, p, owner_alias, runtime):
    stamp = f"bootstrap:{spec['baseline']}@{spec['version']}"
    if p["owner"] is None:
        p["owner"] = cv.create_participant(owner_alias, about=OWNER_ABOUT)
    owner = p["owner"]
    d = spec["designation"]
    if p["caretaker"] is None:
        who = spec["participants"][d["participant"]]
        p["caretaker"] = cv.create_participant(
            who["alias"], about=who.get("about", ""), attributed_to=owner)
    because = f"{spec['baseline']} version {spec['version']} ships this text"
    for key, row in p["items"].items():
        kind, origin = row["kind"], f"{stamp}/{key}"
        if row["how"] in ("establish", "propose-new", "conflict", "propose"):
            body = _written(corpus, key, row, p["items"])
        if row["how"] == "establish":
            row["entry"] = corpus.create_and_establish(
                kind=kind, body=body, attributed_to=owner, origin=origin)
        elif row["how"] == "propose-new":
            row["entry"] = row["proposal"] = corpus.write(
                kind=kind, body=body, attributed_to=owner, origin=origin)
        elif row["how"] in ("conflict", "propose") and not row.get("proposal"):
            row["proposal"] = corpus.write(
                kind=kind, body=body, attributed_to=owner, origin=origin)
            corpus.propose_supersession(row["proposal"], [row["entry"]],
                                        attributed_to=owner, reason=because)
    placements = {}
    for key, row in p["items"].items():
        if row.get("place") == WHOLE_BRAIN_SCOPE and row.get("entry"):
            res = cv.place(row["entry"], whole_brain=True, by=owner,
                           because="owner installed the Brain baseline")
            placements[key] = {"where": res["where"], "link": res["placement"]}
        elif key in p.get("placements", {}) and p["placements"][key].get("link"):
            placements[key] = p["placements"][key]
    p["placements"] = placements

    if p["intake"]["how"] == "designate":
        p["intake"] = {"how": "designated",
                       "designation": cv.designate_intake_carrier(
                           p["caretaker"], p["items"][d["persona"]]["entry"],
                           attributed_to=owner,
                           reason="owner installed the Brain baseline")}
        if runtime:
            cv.declare_runtime_default(p["caretaker"], runtime, by=owner)
    wb_id = cv.whole_brain()
    return cv.record_act(
        actor=owner, act=APPLIED,
        about=[owner, p["caretaker"]] + [r["entry"] for r in p["items"].values()]
              + ([wb_id] if wb_id else []),
        because=f"{spec['baseline']} version {spec['version']}",
        detail={"step": STEP, "baseline": spec["baseline"],
                "version": spec["version"], "owner": owner,
                "caretaker": p["caretaker"],
                "designation": {"persona": d["persona"],
                                "link": p["intake"]["designation"]},
                "items": {k: {"kind": r["kind"], "entry": r["entry"],
                              "digest": digest(r["body"]), "how": r["how"],
                              **({"proposal": r["proposal"]}
                                 if r.get("proposal") else {})}
                          for k, r in p["items"].items()},
                "placements": placements,
                "removed": p.get("removed", [])})


def parse_match(values) -> dict:
    out = {}
    for v in values or []:
        key, sep, target = v.partition("=")
        if not sep or not key or not target:
            raise BootstrapRefused(f"--match {v!r}: expected KEY=<entry> or "
                                   "KEY=new")
        out[key] = target
    return out


def arguments(ap):
    ap.add_argument("corpus")
    ap.add_argument("--owner", required=True,
                    help="the owner's alias; the existing owner is reused")
    ap.add_argument("--runtime", default=None,
                    help="runtime a newly designated carrier uses by default")
    ap.add_argument("--match", action="append", metavar="KEY=ENTRY|new",
                    help="name the existing entry a baseline item is, or "
                         "accept it as new")
    ap.add_argument("--check", action="store_true",
                    help="plan and report; write nothing")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arguments(ap)
    a = ap.parse_args(argv)
    from mentis.bootstrap.new_brain import open_or_create
    try:
        corpus = open_or_create(str(pathlib.Path(a.corpus).resolve()))
    except BootstrapRefused as exc:
        print(f"baseline refused: {exc}", file=sys.stderr)
        return 1
    try:
        print(json.dumps(install(corpus, a.owner, runtime=a.runtime,
                                 match=parse_match(a.match),
                                 dry_run=a.check), indent=2))
    except BootstrapRefused as exc:
        print(f"baseline refused: {exc}", file=sys.stderr)
        return 1
    finally:
        corpus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
