"""Read-only UI descriptions of existing authoring doors; no write path.

Sections are the approved navigation. Fields and standing come from the
Brain's definitions; reach follows the composition vocabulary. Specific
creation doors are described here because those API adapters own their shape.
"""

import re

from mentis.conversation.register import kind_definitions
from mentis.conversation import (SCOPED_TO, versions, whole_brain_ids)


#: THE SECTIONS THIS SURFACE HAS ALWAYS HAD, and their words. A declared
#: section reuses one of these where it names it, and is a tab of its own
#: otherwise.
SECTION_LABELS = {"instructions": "Instructions", "personas": "Personas",
                  "rules": "Rules & decisions"}

#: THE FALLBACK: how the Kinds this surface has always known were offered
#: before a Kind could declare it, so a Brain whose definitions declare
#: nothing is authored exactly as it was. A declaration replaces the row.
_KNOWN = {"conversation-instruction": ("instructions", "instruction"),
          "persona": ("personas", "persona"),
          "rule": ("rules", "entry"), "decision": ("rules", "entry"),
          "lesson": ("rules", "entry")}

#: Where the whole tab name may come from: short, lower case, URL-safe.
_SECTION = re.compile(r"^[a-z][a-z0-9-]{0,39}$")


def _declared(said) -> dict | None:
    """A Kind's own `authoring` declaration, read as far as it can be.

    A DESCRIPTION, SO IT IS READ AND NEVER REFUSED. What cannot be used --
    no usable `section`, or a door other than the generic entry door -- makes
    the declaration unusable and the fallback applies; a missing key takes
    its default."""
    if not isinstance(said, dict):
        return None
    section = said.get("section")
    if not isinstance(section, str) or not _SECTION.match(section) \
            or section == "start":
        return None
    if said.get("door", "entry") != "entry":
        return None
    label = said.get("section_label")
    return {"section": section,
            "section_label": (label if isinstance(label, str) and label.strip()
                              else SECTION_LABELS.get(section,
                                                      section.capitalize())),
            "door": "entry",
            "placeable": said.get("placeable", True) is not False,
            "persona_placeable": said.get("persona_placeable") is True,
            "basis": said.get("basis") is True}


def authoring(corpus, kind):
    """How the owner's Governance surface offers to write this Kind, or None.

    THE KIND'S OWN DECLARATION FIRST (`authoring` on its current definition,
    see `seed.KIND_PROPERTIES`), so a Kind added later gets a builder by being
    defined, with no change here. The map above only for a Kind that declares
    nothing. Standing and reach are always the definition's own answers."""
    definition = kind_definitions(corpus).get(kind)
    if not definition:
        return None
    shape = _declared(definition.get("authoring"))
    if shape is None:
        known = _KNOWN.get(kind)
        if not known:
            return None
        section, door = known
        shape = {"section": section, "section_label": SECTION_LABELS[section],
                 "door": door, "placeable": door != "persona",
                 "persona_placeable": False,
                 # the supporting-references step these three always had
                 "basis": door == "entry"}
    return {**shape,
            "declared": _declared(definition.get("authoring")) is not None,
            "placement_directs_work": definition["knowing"] == "how",
            "standing_apt": definition["standing_apt"],
            "expects_falsifier": definition["expects_falsifier"]}


def authoring_listing(corpus) -> dict:
    """What `/api/governance/authoring` answers, and `/fluid/api/governance/
    authoring` with it: every Kind as `kind_definitions` declares it, with
    how it is authored here, and the runtime Capability vocabulary a
    `capabilities` form input chooses from -- so a builder cannot offer a
    word selection would not understand. ONE READ for both doors, so they
    can never say different things."""
    from mentis.api.types import Capability
    return {"kinds": sorted(({**d, "authoring": authoring(corpus, d["kind"])}
                             for d in kind_definitions(corpus).values()),
                            key=lambda r: r["kind"]),
            "capabilities": [c.value for c in Capability]}


def subjects(corpus) -> list[dict]:
    """The subjects procedural material already names, to offer as suggestions.

    A SUGGESTION, NOT A VOCABULARY. Conflicts are found by comparing `about`
    (`conversation._conflicts`), so two people naming one subject two ways is
    two subjects and no conflict is ever reported. Offering what is already
    written is the whole remedy; nothing is refused for being new.

    WHICH MATERIAL, BY DECLARATION: every Kind whose CURRENT definition directs
    work (`knowing == "how"`, the material composition delivers and compares)
    and declares an `about` field. Values are grouped as `_conflicts` groups
    them -- trimmed, case folded -- and each is reported in its first wording,
    with how many entries use it and of which Kinds. Deleted material is not
    counted: naming its subject again is not reusing it, but it is not a
    subject anything current speaks to either.
    """
    from mentis.conversation import KNOWING_HOW
    from mentis.conversation.versions import inert_refusal
    seen: dict[str, dict] = {}
    for name, d in sorted(kind_definitions(corpus).items()):
        if d.get("knowing") != KNOWING_HOW or "about" not in (d.get("fields") or ()):
            continue
        for e in corpus.entries_of_kind(name):
            said = ((e.get("body") or {}).get("about") or "")
            said = said.strip() if isinstance(said, str) else ""
            if not said or inert_refusal(corpus, e["id"]):
                continue
            row = seen.setdefault(said.casefold(),
                                  {"about": said, "count": 0, "kinds": []})
            row["count"] += 1
            if name not in row["kinds"]:
                row["kinds"].append(name)
    return sorted(seen.values(), key=lambda r: (-r["count"], r["about"].casefold()))


def placements(corpus, eid) -> list[dict]:
    """Where this material is placed now, one row per destination, each
    named and saying whether it is the whole Brain. Ended placements are
    history and are not here."""
    brain_wide = whole_brain_ids(corpus)
    rows = {}
    for x in corpus.links(relation=SCOPED_TO, frm=eid):
        if corpus.stands(x["id"])["superseded_by"]:
            continue
        to = x["link"]["to"]
        if to in rows:
            continue
        got = corpus.read([to])
        rows[to] = {"where": to,
                    "name": ((got[0].get("body") or {}).get("name")
                             if got else None),
                    "whole_brain": to in brain_wide,
                    # A PERSONA DESTINATION CARRIES rather than applies where
                    # work happens; said so a reader need not infer it.
                    "persona": bool(got) and ((got[0].get("definition") or {})
                                              .get("name") == "persona"),
                    "link": x["id"],
                    "reason": (x.get("body") or {}).get("reason"),
                    "at": x.get("recorded_at")}
    return list(rows.values())


def actions(corpus, entry):
    """Offers for the two live states, leaving ended/deleted material read-only."""
    kind = (entry.get("definition") or {}).get("name")
    d = kind_definitions(corpus).get(kind, {})
    standing = corpus.stands(entry["id"])
    live = not standing["superseded_by"] and not versions.inert_refusal(corpus, entry["id"])
    may = versions.offers(corpus, entry)
    creation = authoring(corpus, kind)
    placed = placements(corpus, entry["id"])
    return {"edit": bool(live and may["edit"]),
            "edit_mode": may["edit_mode"],
            "delete": bool(live and may["delete"]),
            "establish": bool(live and not standing["stands"] and d.get("standing_apt") is True),
            "dispute": bool(live),
            "supersede": bool(live and d.get("standing_apt") is True),
            "set_aside": bool(live and standing["stands"]),
            "place": bool(live and creation and creation["placeable"]),
            # THE WHOLE BRAIN IS OFFERED ONLY FOR WHAT ALREADY GOVERNS: it
            # stands and its Kind directs work. The door asks the same.
            "place_whole_brain": bool(
                live and creation and creation["placeable"]
                and standing["stands"] and d.get("knowing") == "how"),
            "whole_brain_why_not": (
                None if (live and standing["stands"]
                         and d.get("knowing") == "how") else
                "only standing material whose Kind directs how work is done "
                "can be placed on the whole Brain"),
            # ENDING A PLACEMENT is offered while the material is live; on
            # ended material placements are history and reach nobody anyway.
            "unplace": bool(live and placed),
            "placements": placed,
            # WHAT THIS CARRIES, where it is a place material is put -- a
            # Persona's Disciplines. Ended placements are history, not here.
            "carries": carried(corpus, entry["id"])}


def carried(corpus, eid) -> list[dict]:
    """The material placed ON this entry now, oldest first: for a Persona,
    what it carries to every execution operating as it. Each row says
    whether it stands, because a candidate placed here carries nothing yet."""
    rows = {}
    for x in corpus.links(relation=SCOPED_TO, to=eid):
        if corpus.stands(x["id"])["superseded_by"]:
            continue
        frm = x["link"]["from"]
        if frm in rows:
            continue
        got = corpus.read([frm])
        if not got:
            continue
        body = got[0].get("body") or {}
        rows[frm] = {"entry": frm,
                     "kind": (got[0].get("definition") or {}).get("name"),
                     "name": body.get("name") or body.get("text", "")[:80],
                     "stands": corpus.stands(frm)["stands"],
                     "link": x["id"], "at": x.get("recorded_at")}
    return list(rows.values())
