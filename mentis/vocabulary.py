"""What the SHIPPED vocabulary declares, read off the declaration lists.

WHY THIS EXISTS AT ALL. The vocabulary is seeded once, when a corpus is empty
(`mentis/spine/seam.py`), and each Conversation Kind is defined once, when it is
not defined yet (`mentis/conversation._ensure_vocabulary`). Both are correct for
what they are -- bootstrap -- and neither is a migration. So a declaration added
to those lists afterwards reaches NEW corpora only, and every Brain that already
exists goes on carrying a definition that predates it. For a declaration
production branches on, that is not a cosmetic lag: measured on the live Brain,
17 of 17 Kinds carried no `knowing`, so every placed procedure in it was still
standing, still placed, and delivered to nobody.

THE DERIVATION IS THE DECLARATIONS THEMSELVES, NOT A TABLE BESIDE THEM. A
hand-written list of "which Kind should declare what" is a second statement of
the vocabulary, and the only thing a second statement reliably does is drift
from the first. So this reads `mentis/spine/seed.py`'s `KINDS` and
`mentis/conversation`'s `_KINDS` -- the lists the bootstrap itself writes from.
Adding a Kind or a declaration to either one is therefore automatically a thing
the migration tool offers and the integrity read notices, with no line here to
remember to change.

NOTHING HERE MUTATES ANYTHING. It answers two questions -- what does the
vocabulary declare, and what is a Brain missing -- and every repair is a
deliberate act somebody runs. See `tools/add_knowing.py` and
`tools/add_standing_apt.py`.

ABSENT IS STILL ABSENT. A Kind the vocabulary declares nothing for is not
missing anything: it is reported nowhere here, and no value is inferred for it.
A Kind the vocabulary declares but this Brain does not define is likewise not a
gap -- there is no definition to be missing a property from.
"""

from __future__ import annotations

from mentis import conversation as _conversation
from mentis.spine import seed

#: The repair for each declaration, so that a report can name the thing to run
#: rather than leaving a reader to find it. A declaration with no tool yet is
#: absent from this map and the reports say so rather than naming a wrong file.
TOOL_FOR = {
    "knowing": "tools/add_knowing.py",
    "standing_apt": "tools/add_standing_apt.py",
}


def declared(prop: str) -> dict[str, object]:
    """Every Kind the shipped vocabulary declares `prop` for, with its value.

    BOTH LISTS, because the vocabulary is written in two places for a reason:
    the spine seeds the epistemic Kinds and the Conversation layer defines its
    own. A reader of only one of them would conclude, wrongly, that `persona`
    declares no `knowing`.

    `_KINDS` ENTRIES ARE TUPLES, and `standing_apt` is its own position in them
    rather than a key in the trailing properties dict, with `ABSENT` meaning
    "nobody has said". That shape is read here exactly as
    `_ensure_vocabulary` reads it, which is the point: one shape, read the same
    way twice, rather than two statements of it.
    """
    out: dict[str, object] = {}
    for k in seed.KINDS:
        if prop in k:
            out[k["kind"]] = k[prop]
    for name, _fields, _meaning, standing_apt, *extra in _conversation._KINDS:
        if prop == "standing_apt":
            if standing_apt is not _conversation.ABSENT:
                out[name] = standing_apt
            continue
        props = extra[0] if extra else {}
        if prop in props:
            out[name] = props[prop]
    return out


def missing_declarations(corpus, properties=None) -> list[dict]:
    """Kinds whose CURRENT definition lacks a declaration the vocabulary makes.

    SCOPED TO `seed.BEHAVIOURAL_PROPERTIES` BY DEFAULT, and that is the whole
    judgement in this module: those are the declarations production BRANCHES
    on, so missing one changes what a Kind's material DOES. `meaning`,
    `capturable` and `truth_apt` are not reported, for the same reason
    `define_kind` does not guard them -- losing one costs a reader a sentence
    and costs the system nothing, and a report that lists cosmetic lag beside
    procedures that stopped being delivered is a report nobody reads twice.

    READ FROM THE CURRENT DEFINITION, AND BY KEY PRESENCE. `prop in body`, not
    a truthiness or an equality test: a Kind declaring `standing_apt: False`
    HAS the declaration, and `False` is an answer somebody established.
    """
    rows = []
    for prop in (properties if properties is not None
                 else seed.BEHAVIOURAL_PROPERTIES):
        for kind, value in sorted(declared(prop).items()):
            current = corpus.current_definition(kind)
            if current is None:
                continue
            if prop in (current.get("body") or {}):
                continue
            rows.append({"kind": kind, "property": prop,
                         "vocabulary_declares": value,
                         "current_version": current["definition"]["version"],
                         "repair": TOOL_FOR.get(prop)})
    return rows
