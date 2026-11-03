"""What automatic model and effort routing reads: tiers, efforts and the tuples
MARS advertises (owner request, Mentis Setup Installation / Updates #1401).

NOT A REGISTRY AND NOT A SCHEDULER. Which models exist and what each is tagged
is MARS's (`_mars/backends`: `routingModels`, `effectiveDefaultModel`); this
holds only the fixed vocabulary, the order it is read in, and which of the
advertised tuples are adequate for a tier. Nothing here chooses a runtime:
`MentisService.execution_select` does, with the gates it always had. Pure and
free of the record, so conversation validation, selection and dispatch can all
ask it.

EXPLICIT-ONLY IS THE ABSENCE OF A TUPLE. An effort outside `EFFORT_ORDER`
(`default`, `ultra`, anything else) and a model MARS did not tag (an alias, a
dynamic model) never appears in what `tuples_of` returns, so automatic routing
cannot reach it; naming it still runs it exactly.
"""

from __future__ import annotations

#: The tiers, weakest first.
TIERS = ("economy", "coding", "frontier")

#: The least effort each tier is adequate at.
TARGET_EFFORT = {"economy": "low", "coding": "medium", "frontier": "high"}

#: Canonical efforts, least first. Anything else is explicit-only.
EFFORT_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh", "max")

#: What an explicit difficulty asks for. `ordinary` and `default`, the words
#: every older path sends, are deliberately not here: alone they imply nothing.
DIFFICULTY_TIER = {"mechanical": "economy",
                   "bounded": "coding", "routine": "coding",
                   "complex": "frontier", "architecture": "frontier",
                   "debugging": "frontier"}


def tier_rank(tier) -> int:
    return TIERS.index(tier)


def effort_rank(effort) -> int:
    return EFFORT_ORDER.index(effort)


def required_tier(*, difficulty=None, authority_sensitive=False, review=False,
                  workflow_tier=None, advisory_tier=None) -> tuple:
    """(the tier this work needs or None, the sources that decided it).

    Review and authority-sensitive work are frontier whatever else is said;
    below that the stronger of the Workflow's default and an advisory tier; an
    explicit difficulty only when neither says anything."""
    forced = [name for name, on in (("review", review),
                                    ("authority_sensitive", authority_sensitive))
              if on]
    if forced:
        return "frontier", forced
    said = [(s, t) for s, t in (("workflow_default", workflow_tier),
                                ("advisory", advisory_tier)) if t in TIERS]
    if said:
        best = max((t for _, t in said), key=tier_rank)
        return best, [s for s, t in said if t == best]
    tier = DIFFICULTY_TIER.get(difficulty) if isinstance(difficulty, str) else None
    return (tier, ["difficulty"]) if tier else (None, [])


def tuples_of(backend) -> list[dict]:
    """The automatic tuples this backend advertises: `{"model", "tier",
    "efforts"}` with only canonical efforts, least first. A model with none is
    not a tuple (MARS proved no effort for it)."""
    out = []
    for row in (backend or {}).get("routingModels") or ():
        if not isinstance(row, dict) or row.get("tier") not in TIERS \
                or not isinstance(row.get("id"), str) or not row["id"]:
            continue
        efforts = sorted({e for e in row.get("efforts") or ()
                          if e in EFFORT_ORDER}, key=effort_rank)
        if efforts:
            out.append({"model": row["id"], "tier": row["tier"],
                        "efforts": efforts})
    return out


def default_model_of(backend) -> str | None:
    """The model this backend runs when none is asked for, when MARS knows."""
    got = (backend or {}).get("effectiveDefaultModel")
    return got if isinstance(got, str) and got else None


def adequate(backend, tier, model=None, effort=None) -> list[dict]:
    """The tuples of this backend good enough for `tier`, least sufficient
    first: `{"model", "tier", "effort"}`.

    A model at or above the tier, at the least advertised effort at or above
    the tier's target. A named `model` narrows to that exact model, and a named
    `effort` is kept as it is, so it only asks that the model advertises it;
    whether it is enough for the tier is `effort_short`'s to say."""
    floor = tier_rank(tier)
    target = effort_rank(TARGET_EFFORT[tier])
    default = default_model_of(backend)
    rows = []
    for row in tuples_of(backend):
        if tier_rank(row["tier"]) < floor or (model and row["model"] != model):
            continue
        if effort:
            if effort not in row["efforts"]:
                continue
            chosen = effort
        else:
            enough = [e for e in row["efforts"] if effort_rank(e) >= target]
            if not enough:
                continue
            chosen = enough[0]
        rows.append({"model": row["model"], "tier": row["tier"],
                     "effort": chosen})
    rows.sort(key=lambda r: (rank_of(r), 0 if r["model"] == default else 1))
    return rows


def rank_of(row) -> tuple:
    """How much of a tuple this is: the model's tier, then its effort. Lower is
    more efficient; a named effort outside the canonical order ranks last."""
    effort = row["effort"]
    return (tier_rank(row["tier"]),
            effort_rank(effort) if effort in EFFORT_ORDER else len(EFFORT_ORDER))


def effort_short(effort, tier) -> bool:
    """Whether a named effort is below what this tier targets."""
    if effort not in EFFORT_ORDER:
        return True
    return effort_rank(effort) < effort_rank(TARGET_EFFORT[tier])
