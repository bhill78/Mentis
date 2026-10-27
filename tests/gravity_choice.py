"""The owner choosing to pursue a finding, through the production seams.

Discovered work is picked up only once its owner has chosen to pursue it, or
their follow-up permission on the original request covers it (Task Gravity:
coordinating authority alone never does). Tests whose subject is something
ELSE about picked-up work -- its reach, worktree, handoff, governed material,
authority -- take the owner's-choice step here, the way production does: the
finding is put to the owner of the work it was found under in the one
decision Mentis asks about findings (`operational.ask_about_findings`, what a
finished trunk asks), and the owner chooses Pursue. Nothing is written by
hand.
"""

from __future__ import annotations


def owner_chooses(surface, grant, finding):
    """`grant` is a run of the work `finding` was found under; the owner of
    that work is asked about it and chooses to pursue it."""
    from mentis.operational import (_owner_of, ask_about_findings,
                                    resolve_reconsideration_decision,
                                    trunk_of)
    brain = surface.brain
    root = trunk_of(brain, grant["expectation"])
    owner = _owner_of(brain, surface.cv._act(root["root_act"]))
    asked = ask_about_findings(
        brain, [finding], conversation=grant["conversation"],
        by=grant["participant"], owner=owner, caused_by=grant["expectation"],
        originating_turn=root["originating_turn"],
        question="Pursue this on its own?")
    got = resolve_reconsideration_decision(
        surface.cv, asked["expectation"], actor=owner, pursue=[finding])
    assert got.get("ok"), got
    return got
