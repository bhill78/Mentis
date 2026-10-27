"""Seed a Brain with the welcome tour every new Brain starts with.

    python -m mentis.bootstrap <corpus> --owner @alias   # baseline, then tour
    python -m mentis.bootstrap.welcome <corpus>          # tour only
    python -m mentis.bootstrap.welcome <corpus> --update-tour

THE TOUR NEEDS THE BASELINE. Who answers for Mentis -- the owner, @Caretaker,
the Caretaker Persona and the `carries-intake` designation -- is the
baseline's (baseline.py), not the tour's. The tour's guide is the carrier the
applied baseline resolves to, and it refuses if the baseline is missing or no
longer resolves.

The tour is the Conversation in welcome_tour.json: Topics, Turns with replies,
a Conversation instruction, a reaction, an anchored comment and a deep dive,
with screenshots from ./screenshots attached where the content names them.

It records a `bootstrap-applied` act carrying the tour version, so running it
again does nothing, and a later version of the tour can tell that an earlier
one was seeded: a fresh tour is skipped if any version is here already.
Nothing here dispatches work: Turns are said, not asked, so no agent runs.

LATER VERSIONS ONLY ADD. A version's new material lives under `additions`.
A fresh Brain gets it in place, each run of Turns after the Turn it names
in `after`. A Brain seeded with an earlier version gets nothing unless the
owner asks with `--update-tour`. Then the additions are appended to the
existing tour Conversation, filed under its Topics. No existing Turn is
edited, moved or replied to, so an owner's edits stand.

The content lives in welcome_tour.json so wording changes never touch code.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import mentis.api as api
from mentis import artifacts
from mentis.conversation import anchors
from mentis.bootstrap import baseline
from mentis.conversation import text as part

HERE = pathlib.Path(__file__).resolve().parent
TOUR = HERE / "welcome_tour.json"
SHOTS = HERE / "screenshots"
APPLIED = "bootstrap-applied"


def _done(cv, step, version=None) -> bool:
    for a in cv.history(act=APPLIED, detail_is={"step": step}):
        d = a.get("detail") or {}
        if version is None or d.get("version") == version:
            return True
    return False


BootstrapRefused = baseline.BootstrapRefused


def additions(spec, after=0):
    """The additive versions later than `after`, oldest first."""
    return sorted((a for a in spec.get("additions", [])
                   if after < a["version"] <= spec["version"]),
                  key=lambda a: a["version"])


def validate_spec(spec):
    """Catch broken anchors and references before any setup writes happen.

    An addition must stand on its own, because an existing tour gets it
    appended: its replies and anchors name only its own Turns."""
    turns, topics = {}, {t["key"] for t in spec["topics"]}

    def check(ts, marks, inside):
        for t in ts:
            if t["key"] in turns:
                raise ValueError(f"turn {t['key']}: key used twice")
            if t.get("topic") and t["topic"] not in topics:
                raise ValueError(f"turn {t['key']}: no topic {t['topic']}")
            if t.get("after") and t["after"] not in turns:
                raise ValueError(f"turn {t['key']}: after unknown {t['after']}")
            if t.get("replies_to") and t["replies_to"] not in (
                    turns if inside is None else inside):
                raise ValueError(f"turn {t['key']}: replies to {t['replies_to']}, "
                                 "which is not earlier in its own part")
            turns[t["key"]] = t["text"]
            if inside is not None:
                inside.add(t["key"])
        for a in marks:
            if inside is not None and a["turn"] not in inside:
                raise ValueError(f"anchor {a['key']}: {a['turn']} is not in its addition")
            if not a["excerpt"] or a["excerpt"] not in turns.get(a["turn"], ""):
                raise ValueError(f"anchor {a['key']}: excerpt absent from {a['turn']}")

    check(spec["turns"], spec.get("anchors", []), None)
    for add in additions(spec):
        if add["turns"] and not add["turns"][0].get("after"):
            raise ValueError(f"addition {add['version']}: first turn needs after")
        check(add["turns"], add.get("anchors", []), set())


def fresh_plan(spec):
    """Every Turn and anchor of this version, in reading order: each run of
    added Turns sits after the Turn its first one names."""
    order, marks = list(spec["turns"]), list(spec.get("anchors", []))
    for add in additions(spec):
        at = None
        for t in add["turns"]:
            if t.get("after"):
                at = 1 + next(i for i, x in enumerate(order)
                              if x["key"] == t["after"])
            order.insert(at, t)
            at += 1
        marks += add.get("anchors", [])
    return order, marks


def seeded_version(cv, tour):
    """The latest version of `tour` this Brain holds, and its Conversation."""
    version, conv = 0, None
    for a in cv.history(act=APPLIED):
        d = a.get("detail") or {}
        if d.get("tour") != tour or d.get("step") not in ("tour", "tour-update"):
            continue
        if d["step"] == "tour":
            conv = a.get("conversation")
        version = max(version, d.get("version") or 0)
    return version, conv


def render_spec(spec, alias):
    """Replace the guide token in all content, including anchored excerpts."""
    def render(value):
        if isinstance(value, str):
            return value.replace("{guide_alias}", alias)
        if isinstance(value, list):
            return [render(v) for v in value]
        if isinstance(value, dict):
            return {k: render(v) for k, v in value.items()}
        return value
    return render(spec)


def _excerpt_anchor(cv, turn, excerpt, by):
    text = cv.corpus.read([turn])[0]["body"]["parts"][0]["text"]
    start = text.index(excerpt)          # content error if absent: fail loudly
    return anchors.create_anchor(cv, {
        "version": turn, "type": "text-range", "part": 0, "start": start,
        "end": start + len(excerpt), "unit": "codepoint",
        "expected_excerpt": excerpt}, by=by)["anchor"]


def _people(cv, who, spec):
    return {"guide": who["guide"],
            "newcomer": cv.resolve_participant(
                spec["participants"]["newcomer"]["alias"],
                about=spec["participants"]["newcomer"]["about"]),
            "owner": who["owner"]}


def seed_tour(corpus, cv, who, spec) -> dict | None:
    """A fresh tour at this version; nothing if any version is here already."""
    spec = render_spec(spec, cv.alias(who["guide"]))
    validate_spec(spec)
    if seeded_version(cv, spec["tour"])[0]:
        return None
    with corpus.atomic():
        people = _people(cv, who, spec)
        c = spec["conversation"]
        conv = cv.open_conversation(c["name"], about=c["about"],
                                    attributed_to=people["guide"])
        for p in people.values():
            cv.join(p, conv)
        cv.instruct_conversation(conv, spec["instruction"]["text"],
                                 about=spec["instruction"]["about"])
        topics = {t["key"]: cv.open_topic(conv, t["name"], about=t["about"])
                  for t in spec["topics"]}
        order, marks = fresh_plan(spec)
        turns, dives = _post(corpus, cv, conv, people, topics, spec,
                             order, marks)
        cv.record_act(actor=people["guide"], act=APPLIED, conversation=conv,
                      about=[conv, *dives],
                      because="the welcome tour every new Brain starts with",
                      detail={"step": "tour", "tour": spec["tour"],
                              "version": spec["version"], "turns": turns})
    return {"conversation": conv, "deep_dives": dives, "turns": len(turns)}


def update_tour(corpus, cv, who, spec) -> dict | None:
    """Append later versions' additions to an existing tour, on request.

    Only adds: new Turns, filed under the tour's Topics (found by name, then
    by description; opened under the tour's name if the owner removed both).
    No existing Turn is edited, moved or replied to."""
    spec = render_spec(spec, cv.alias(who["guide"]))
    validate_spec(spec)
    have, conv = seeded_version(cv, spec["tour"])
    if not have:
        raise BootstrapRefused("no welcome tour is seeded here to update; "
                               "run without --update-tour to seed one")
    pending = additions(spec, have)
    if not pending:
        return None
    if not conv or not cv.corpus.read([conv]):
        raise BootstrapRefused(f"the welcome tour Conversation {conv} is gone")
    with corpus.atomic():
        people = _people(cv, who, spec)
        members = set(cv.participants(conv))
        for p in people.values():
            if p not in members:
                cv.join(p, conv)
        held = cv.topics(conv)
        topics, opened = {}, []
        for t in spec["topics"]:
            found = ([x["id"] for x in held if x["body"].get("name") == t["name"]]
                     or [x["id"] for x in held
                         if x["body"].get("about") == t["about"]])
            if found:
                topics[t["key"]] = found[0]
        out = {"conversation": conv, "from": have, "to": spec["version"],
               "turns": 0, "topics_opened": opened}
        for add in pending:
            for t in add["turns"]:
                key = t.get("topic")
                if key and key not in topics:
                    d = next(x for x in spec["topics"] if x["key"] == key)
                    topics[key] = cv.open_topic(conv, d["name"], about=d["about"])
                    opened.append(d["name"])
            turns, dives = _post(corpus, cv, conv, people, topics, spec,
                                 add["turns"], add.get("anchors", []))
            cv.record_act(actor=people["guide"], act=APPLIED, conversation=conv,
                          about=[conv, *dives],
                          because="the owner asked for the welcome tour's "
                                  "additions, appended without rewriting it",
                          detail={"step": "tour-update", "tour": spec["tour"],
                                  "version": add["version"], "turns": turns})
            out["turns"] += len(turns)
    return out


def _post(corpus, cv, conv, people, topics, spec, order, marks):
    """Say these Turns and anchors in `conv`; return their ids and deep dives."""
    def parts_of(t, where):
        # A screenshot not yet taken is left out, never a broken image.
        parts = [part(t["text"])]
        names = t.get("screenshot") or []
        for name in [names] if isinstance(names, str) else names:
            shot = SHOTS / f"{name}.png"
            if not shot.is_file():
                continue
            adm = artifacts.hold(
                corpus, cv, shot.read_bytes(), act=artifacts.SUBMITTED,
                actor=people[t["author"]], source="bootstrap:welcome-tour",
                door="bootstrap",
                claimed_name=spec.get("screenshots", {}).get(name, name) + ".png",
                claimed_media_type="image/png", conversation=where,
                because="a screenshot in the welcome tour")["admission"]
            parts.append(artifacts.part(adm, corpus=corpus))
        return parts

    turns = {}
    for t in order:
        tid = cv.say(conv, people[t["author"]], parts_of(t, conv),
                     replies_to=turns.get(t.get("replies_to")))
        if t.get("topic"):
            cv.assign_topic(tid, topics[t["topic"]])
        turns[t["key"]] = tid

    dives = []
    for a in marks:
        aid = _excerpt_anchor(cv, turns[a["turn"]], a["excerpt"],
                              people["newcomer"])
        for r in a.get("reactions", []):
            anchors.react(cv, aid, {"token": r["token"]}, by=people[r["by"]])
        if a.get("comment"):
            cm = a["comment"]
            q = cv.say(conv, people[cm["by"]],
                       [{"type": "anchor", "ref": aid}, part(cm["text"])],
                       replies_to=turns[a["turn"]])
            if a.get("comment_reply"):
                r = a["comment_reply"]
                cv.say(conv, people[r["by"]], [part(r["text"])],
                       replies_to=q)
        if a.get("deep_dive"):
            dd = a["deep_dive"]
            out = anchors.deep_dive(cv, aid, {"why": dd["why"]},
                                    by=people[dd["by"]])
            child = out["conversation"]
            cv.join(people["guide"], child)
            cv.join(people["owner"], child)
            for t in dd.get("turns", []):
                cv.say(child, people[t["author"]], parts_of(t, child))
            dives.append(child)
    return turns, dives


def load() -> dict:
    return json.loads(TOUR.read_text("utf-8"))


def bootstrap(corpus, *, update=False, spec=None):
    """Seed the tour, guided by the carrier the applied baseline resolves to;
    with `update`, append a newer version's additions to the existing tour."""
    spec = spec if spec is not None else load()
    validate_spec(spec)
    cv = api.brain(corpus).conversations
    out = updated = None
    with corpus.atomic():
        who = baseline.people(corpus, cv)
        if update:
            updated = update_tour(corpus, cv, who, spec)
        else:
            out = seed_tour(corpus, cv, who, spec)
    have = seeded_version(cv, spec["tour"])[0]
    return {"tour": out, "tour_update": updated,
            # Said, never applied: an existing tour changes only on request.
            "tour_update_available": (
                {"from": have, "to": spec["version"], "with": "--update-tour"}
                if 0 < have < spec["version"] else None)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("corpus")
    ap.add_argument("--update-tour", action="store_true",
                    help="append a newer tour's additions to an existing tour")
    a = ap.parse_args(argv)
    from mentis.bootstrap.new_brain import open_or_create
    try:
        corpus = open_or_create(str(pathlib.Path(a.corpus).resolve()))
    except BootstrapRefused as exc:
        print(f"bootstrap refused: {exc}", file=sys.stderr)
        return 1
    try:
        print(json.dumps(bootstrap(corpus, update=a.update_tour), indent=2))
    except BootstrapRefused as exc:
        print(f"bootstrap refused: {exc}", file=sys.stderr)
        return 1
    finally:
        corpus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
