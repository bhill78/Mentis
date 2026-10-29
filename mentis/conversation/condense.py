"""Governance condensation: how much of what governs a run the run reads.

WHY THIS EXISTS. Everything placed at a Conversation or on the whole Brain
reaches every execution there in full, because placement is how material comes
to govern and what governs must be read. That is right for the rule that
always binds and wrong for the Discipline that applies only to releases: every
run pays for text that does not bear on its work, and enough such text buries
the text that does. The owner already says, at placement, where material
applies; the placement can now also say HOW MUCH of it a run is handed when
nothing says its condition holds -- the condition in one line, or a reference
to where the full text stands.

WHAT THIS NEVER DOES. The authoritative text is never rewritten, abbreviated
or summarised. A conditional delivery states the condition and where the
material is read in full (`resolve`); a reference delivery states that the
material stands and where it is read; and anything that cannot be represented
safely in shorthand is delivered in full, exactly as `Composition` renders it.
Condensation only ever says less WITH A POINTER; it never says something
different.

AND IT DECIDES NOTHING NEW. Standing and supersession are resolved by
`compose` before a component reaches this module, so a superseded or
non-standing item is never condensed -- it is never here. Whether a condition
is met is the knowledge channel's own term overlap (`knowledge.meets`), asked
of the condition rather than of the corpus. What the owner declared is read
from the placement link's body, where `Conversations.place` wrote it. Pure:
no I/O beyond the corpus reads it is given.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import Component, Composition, placement_delivery
from .knowledge import meets

FULL, CONDITIONAL, REFERENCE = "full", "conditional", "reference"

#: HOW MUCH CONDITION A SHORTHAND LINE CAN CARRY. Longer than this is a
#: paragraph, and a paragraph cut to a line is a summary -- the one thing this
#: module never produces. Over the limit the material is delivered in full.
CONDITION_LIMIT = 240


@dataclass(frozen=True)
class Delivery:
    """One composed component and how much of it a run is handed.

    The component is the composition's own, unchanged: condensation decides a
    level and states why, and the record of what governs (`sources()`) is
    untouched by it.
    """

    component: Component        # the composed component, unchanged
    level: str                  # FULL | CONDITIONAL | REFERENCE
    condition: str | None       # the applicability text used, verbatim
    why: str                    # why this level (stated, for the record)


def condense(corp, composition, *, known=(), question=None) -> tuple[Delivery, ...]:
    """One Delivery per component, in the composition's own order.

    THE RULES, IN ORDER, the first that decides wins (operating model §3):
    standing and supersession are resolved before this (a component here
    stands); what does not govern passes through FULL; the Persona being worn
    is always FULL; material named for the work or listed in `known` is FULL;
    otherwise the placement's declared delivery decides, absent meaning FULL;
    a conditional whose condition `question` meets is FULL; a reference
    renders only in the closing index line.
    """
    known = frozenset(known or ())
    governing = set(composition.governing())
    return tuple(_delivery(corp, c, c in governing, known, question)
                 for c in composition.components)


def render(deliveries) -> str:
    """What the run reads.

    FULL components render EXACTLY as `Composition._rendered` renders them --
    the method is called, not copied, so a full delivery cannot drift from
    what an execution has always read. A conditional component is one line
    naming its condition and where the full text stands; references close the
    payload in a single index line. The authoritative text of anything not
    FULL never appears.
    """
    deliveries = tuple(deliveries)
    composed = Composition(tuple(d.component for d in deliveries), (), ())
    blocks, referenced = [], []
    for d in deliveries:
        if d.level == REFERENCE:
            referenced.append(d)
        elif d.level == CONDITIONAL:
            blocks.append(_conditional_line(d))
        else:
            blocks.append(composed._rendered(d.component))
    if referenced:
        blocks.append("Also standing, by reference: "
                      + ", ".join(_index_entry(d) for d in referenced))
    return "\n\n".join(blocks)


def _delivery(corp, c, governs, known, question) -> Delivery:
    """The first rule that decides, in the order `condense` states them."""
    # 2. WHAT DOES NOT GOVERN IS NEVER CONDENSED: the orientation, the
    # request, invocation strings and the knowledge channel's material.
    if not governs:
        return Delivery(c, FULL, None,
                        "not governing material, so it is delivered exactly "
                        "as composed")
    # 3. THE PERSONA BEING WORN.
    if c.scope == "invocation:persona":
        return Delivery(c, FULL, None,
                        "the Persona this run operates as is always delivered "
                        "in full")
    # 4. NAMED FOR THIS WORK (however it also arrived -- `also` keeps that it
    # was named when another scope supplied it first), OR KNOWN TO IT.
    if c.scope == "invocation:named" or "invocation:named" in c.also:
        return Delivery(c, FULL, None,
                        "named for this work: a condition known to apply")
    if c.source_id in known:
        return Delivery(c, FULL, None,
                        "listed as known to this work: a condition known to "
                        "apply")
    # 5. WHAT THE PLACEMENT DECLARES. The component's scope says where it was
    # placed; absent a declared delivery, placed material is delivered in
    # full, as it always was.
    declared = placement_delivery(corp, c.source_id, c.scope)
    if declared is None:
        return Delivery(c, FULL, None,
                        "its placement declares no delivery, so it is "
                        "delivered in full, as before")
    level = declared["delivery"]
    if level == FULL:
        return Delivery(c, FULL, None, "placed with delivery full")
    if level == REFERENCE:
        return Delivery(c, REFERENCE, None,
                        "placed by reference: it stands, and the run is given "
                        "where to read it rather than the text")
    if level == CONDITIONAL:
        # The condition is the link's `when`, else the entry's own
        # applicability field (Discipline/Workflow `about`, "When it
        # applies"), which the component already carries.
        condition = declared.get("when") or c.about or ""
        if not condition.strip():
            return Delivery(c, FULL, None,
                            "placed conditional, but no condition is recorded "
                            "to state, so it is delivered in full")
        if len(condition) > CONDITION_LIMIT:
            return Delivery(c, FULL, condition,
                            f"its condition is longer than {CONDITION_LIMIT} "
                            f"characters and cannot be represented safely in "
                            f"shorthand, so it is delivered in full")
        # 6. A CONDITION KNOWN TO APPLY TO THIS WORK is no condition at all,
        # for this run.
        if question and meets(question, condition):
            return Delivery(c, FULL, condition,
                            "the question meets its condition, so the "
                            "condition is known to apply and it is delivered "
                            "in full")
        return Delivery(c, CONDITIONAL, condition,
                        "placed conditional, and nothing says its condition "
                        "applies to this work")
    # A DECLARED LEVEL NOTHING RECOGNISES reads as none: full, never a guess.
    return Delivery(c, FULL, None,
                    f"its placement declares a delivery nothing recognises "
                    f"({level!r}), so it is delivered in full")


def _conditional_line(d: Delivery) -> str:
    """The one line a conditional delivery renders as. The format is fixed:
    what it is, its condition verbatim, and how to read the full text before
    acting under it."""
    c = d.component
    title = f"{c.title} " if c.title else ""
    return (f"[governs · {c.source_kind} · conditional] {title}— applies "
            f"when: {d.condition}. Read it in full with "
            f"resolve(\"{c.source_id}\") before acting under it. "
            f"(reference: {c.source_id})")


def _index_entry(d: Delivery) -> str:
    """A reference in the closing index line: the id, and what it is called
    where its Kind gives it a name."""
    c = d.component
    return f"{c.source_id} ({c.title})" if c.title else str(c.source_id)
