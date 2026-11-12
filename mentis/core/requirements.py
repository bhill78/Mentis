"""What a piece of work requires of whoever runs it: its WORK REQUIREMENTS
(docs/model-selection-contract.md section 2).

NOT SIZE, NOT WORDS. Two structured judgements about the work, each with where
it came from, and nothing read from the brief:

  * `solution`: `specified` -- what to do is known, however much of it there is;
    `open` -- the answer is not known yet, however small the change.
  * `reasoning`: the thinking and planning the work demands (`light`,
    `substantial`, `deep`), not how big it is.

Plus how the work relates to other work (`relation`: `new`, `continues`,
`revises`, `implements`, `verifies`), whether it is bounded exploratory work
(`exploratory`, with what makes it done), the capabilities it requires, and
its `scope` (`narrow`, `broad`): INFORMATIONAL ONLY, recorded as said and
never an input to the need -- narrow scope is not low reasoning.

Every value carries its source: `stated` (somebody said it for this work),
`inherited` (from the work it continues), `compat` (from a legacy `difficulty`
word) or `default` (nothing said; the soft default applies).

Pure functions, free of the record: the lineage that finds what work continues
is `mentis.web.dispatch`'s, and what is suitable for a requirement is
`mentis.suitability`'s. Nothing here chooses a model.
"""

from __future__ import annotations

#: The reasoning demand, least first.
LEVELS = ("light", "substantial", "deep")

#: Whether the solution is known; `open` is the more demanding.
SOLUTIONS = ("specified", "open")

#: How work relates to other work.
RELATIONS = ("new", "continues", "revises", "implements", "verifies")

#: Where a value came from.
SOURCES = ("stated", "inherited", "compat", "default")

#: How much of the system the work touches. Informational: recorded, never an
#: input to `need` (narrow scope is not low reasoning).
SCOPES = ("narrow", "broad")

#: Relations that carry the requirements of the work they continue.
INHERITING = ("continues", "revises")

#: The legacy `difficulty` words, as (solution, reasoning); None where the word
#: says nothing about it. `ordinary`, `default` and anything else imply
#: nothing (the soft default applies).
#:
#: `bounded` IS SCOPE, NOT A KNOWN ANSWER (owner, round 2, 2026-11-12: round 2
#: of the composer mockups was delegated `bounded` -- "one focused revision" --
#: and ran as specified/coding work, an open design problem). It reads as
#: `scope: narrow` (`COMPAT_SCOPE`) and `reasoning: substantial`, its solution
#: UNSTATED. Its need is the same as before (substantial, not open), so no
#: historical pick changes.
COMPAT = {"mechanical": ("specified", "light"),
          "bounded": (None, "substantial"),
          "routine": ("specified", "substantial"),
          "complex": ("open", "deep"),
          "architecture": ("open", "deep"),
          "debugging": ("open", "deep")}

#: The scope a legacy `difficulty` word says.
COMPAT_SCOPE = {"bounded": "narrow"}

#: What each legacy tier meant, as (solution, reasoning): the owner-approved
#: tier table (#1401) read as requirements.
TIER_NEED = {"economy": ("specified", "light"),
             "coding": ("specified", "substantial"),
             "frontier": ("open", "deep")}

#: The reasoning level nothing stated gets: the soft default, matching
#: `routing.DEFAULT_TIER` (coding).
SOFT_LEVEL = "substantial"

#: The least effort a need is met at: today's tier targets.
EFFORT_FLOOR = {"light": "low", "substantial": "medium", "deep": "high"}

#: What forces a need whatever else is said (review, authority-sensitive work).
FORCED_NEED = {"level": "deep", "open": True}


class Invalid(ValueError):
    """A requirement stated in a shape this vocabulary does not hold."""


def level_rank(level) -> int:
    return LEVELS.index(level)


def solution_rank(solution) -> int:
    return SOLUTIONS.index(solution)


def compat(difficulty) -> tuple | None:
    """(solution, reasoning) a legacy difficulty word means, or None."""
    return COMPAT.get(difficulty) if isinstance(difficulty, str) else None


def compat_scope(difficulty) -> str | None:
    """The scope a legacy difficulty word says (`bounded`: narrow), or None."""
    return COMPAT_SCOPE.get(difficulty) if isinstance(difficulty, str) else None


def _text(value):
    value = str(value).strip() if value is not None else ""
    return value or None


def check(*, solution=None, reasoning=None, relation=None, relation_ref=None,
          exploratory=None, done_when=None, scope=None) -> dict:
    """The stated fields, validated: `{"solution", "reasoning", "relation",
    "relation_ref", "exploratory", "done_when", "scope"}`, None where not
    stated. Raises `Invalid` in words a caller can act on."""
    solution, reasoning, relation = (_text(solution), _text(reasoning),
                                     _text(relation))
    scope = _text(scope)
    if scope and scope not in SCOPES:
        raise Invalid(f"scope is one of {list(SCOPES)}, not {scope!r}")
    if solution and solution not in SOLUTIONS:
        raise Invalid(f"solution is one of {list(SOLUTIONS)}, not {solution!r}")
    if reasoning and reasoning not in LEVELS:
        raise Invalid(f"reasoning is one of {list(LEVELS)}, not {reasoning!r}")
    if relation and relation not in RELATIONS:
        raise Invalid(f"relation is one of {list(RELATIONS)}, not {relation!r}")
    if relation_ref is None:
        refs = []
    elif isinstance(relation_ref, str):
        refs = [relation_ref.strip()] if relation_ref.strip() else []
    elif isinstance(relation_ref, (list, tuple)):
        refs = list(dict.fromkeys(str(r).strip() for r in relation_ref
                                  if r is not None and str(r).strip()))
    else:
        raise Invalid("relation_ref is a record id or a list of them")
    if refs and not relation:
        raise Invalid("relation_ref names what the work relates to; state "
                      "`relation` with it")
    if relation == "implements" and not refs:
        raise Invalid("`implements` names what it implements: give relation_ref, "
                      "the approved artifact or decision")
    if exploratory is not None and not isinstance(exploratory, bool):
        raise Invalid("exploratory is true or false")
    done_when = _text(done_when)
    if exploratory and not done_when:
        raise Invalid("exploratory work says when it is done: give `done_when`, "
                      "something a reader can check")
    if done_when and not exploratory:
        raise Invalid("done_when is only for exploratory work")
    return {"solution": solution, "reasoning": reasoning, "relation": relation,
            "relation_ref": refs, "exploratory": exploratory,
            "done_when": done_when, "scope": scope}


def derive(*, solution=None, reasoning=None, difficulty=None, relation=None,
           relation_ref=None, exploratory=None, done_when=None, requires=(),
           scope=None, continuation=None, inherited=None, approval=None,
           detected=None) -> tuple[dict, list[str]]:
    """(the work's requirements, warnings for whoever stated them).

    `continuation`: what the record says this work continues when no relation
    was stated, `{"value": "continues"|"revises", "ref": [ids], "found":
    [words]}` or None. `inherited`: what that work required, `{"solution",
    "reasoning", "from"}` (None values where it said nothing), read by the
    caller from the record. `approval`: for `implements`, the owner approval
    the record holds that its relation_ref names (`{"ref", "by", "why"}`), or
    None. `detected`: what the record shows this continues when the caller
    stated a relation that does not inherit (`{"value", "ref", "found"}`).

    LINEAGE (contract section 2): `continues` and `revises` take the solution
    and reasoning of what they continue; a stated or legacy value LOWER than
    inherited is raised to it, and the warning and the record say so.
    `implements` takes only what it states when it names an owner approval;
    otherwise it keeps the requirements of the work it names, and is told what
    would make the lowering legitimate. `verifies` takes only what it states.
    `new` inherits nothing; stated where the record shows a continuation, it
    is honoured, and what was detected and overridden is recorded and said.
    `scope` is recorded, never inherited and never an input to the need. A
    model or effort is never part of this."""
    said = check(solution=solution, reasoning=reasoning, relation=relation,
                 relation_ref=relation_ref, exploratory=exploratory,
                 done_when=done_when, scope=scope)
    warnings: list[str] = []
    legacy = compat(difficulty)
    if said["relation"]:
        rel = {"value": said["relation"], "ref": said["relation_ref"],
               "source": "stated"}
    elif continuation and continuation.get("value") in INHERITING:
        rel = {"value": continuation["value"],
               "ref": list(continuation.get("ref") or ()),
               "source": "inherited"}
        if continuation.get("found"):
            rel["found"] = list(continuation["found"])
    else:
        rel = {"value": "new", "ref": [], "source": "default"}
    unapproved = rel["value"] == "implements" and not approval
    if rel["value"] == "implements" and approval:
        rel["approval"] = dict(approval)
    takes = ((inherited or {}) if rel["value"] in INHERITING or unapproved
             else {})
    from_ids = list((takes or {}).get("from") or ())
    if (detected and detected.get("ref") and rel["source"] == "stated"
            and rel["value"] not in INHERITING and not unapproved):
        # HONOURED, AND SAID: the record shows a continuation the caller
        # states this is not.
        rel["detected"] = {"value": detected.get("value") or "continues",
                           "ref": list(detected["ref"]),
                           **({"found": list(detected["found"])}
                              if detected.get("found") else {}),
                           "overridden": True}
        warnings.append(
            f"the record shows this continues {', '.join(detected['ref'])}"
            + (f" ({'; '.join(detected['found'])})" if detected.get("found")
               else "")
            + f"; relation {rel['value']!r} was stated, so nothing is inherited "
              f"from it. That is recorded (relation.detected, overridden)")
    what = ("work this implements without an owner approval" if unapproved
            else f"work this {rel['value']}")

    def one(name, stated_value, legacy_value, order):
        if stated_value:
            got = {"value": stated_value, "source": "stated", "from": []}
        elif legacy_value:
            got = {"value": legacy_value, "source": "compat", "from": []}
        else:
            got = {"value": "unstated", "source": "default", "from": []}
        prior = takes.get(name)
        if prior in order:
            if got["value"] == "unstated":
                got = {"value": prior, "source": "inherited", "from": from_ids}
            elif order.index(got["value"]) < order.index(prior):
                said_how = (f"the legacy difficulty {difficulty!r} reads as"
                            if got["source"] == "compat" else "stated")
                warnings.append(
                    f"{name} {got['value']!r} ({said_how}) is lower than the "
                    f"{prior!r} of the {what} "
                    f"({', '.join(from_ids) or 'recorded'}), so it is raised to "
                    f"{prior!r}. Work that continues another keeps what that "
                    f"work needed; state relation `new` if it does not "
                    f"continue it")
                got = {"value": prior, "source": "inherited", "from": from_ids,
                       "raised_from": {"value": got["value"],
                                       "source": got["source"]}}
        return got

    scope_said = said["scope"] or compat_scope(difficulty)
    req = {"solution": one("solution", said["solution"],
                           legacy[0] if legacy else None, SOLUTIONS),
           "reasoning": one("reasoning", said["reasoning"],
                            legacy[1] if legacy else None, LEVELS),
           "relation": rel,
           "exploratory": {"value": bool(said["exploratory"]),
                           "done_when": said["done_when"],
                           "source": ("stated" if said["exploratory"] is not None
                                      else "default")},
           "scope": ({"value": scope_said,
                      "source": "stated" if said["scope"] else "compat"}
                     if scope_said else {"value": "unstated", "source": "default"}),
           "requires": list(dict.fromkeys(str(r) for r in requires or ()))}
    took = {k: req[k]["value"] for k in ("solution", "reasoning")
            if req[k]["source"] == "inherited"}
    if took and rel["source"] == "inherited":
        # NOT STATED BY THE CALLER, SO SAID TO IT: what the record found this
        # continues, and what it keeps from it.
        warnings.append(
            f"the record shows this continues {', '.join(rel['ref'])}"
            + (f" ({'; '.join(rel['found'])})" if rel.get("found") else "")
            + "; it keeps "
            + " and ".join(f"{k} {v!r}" for k, v in took.items())
            + " from that work. State relation `new` if it does not continue it")
    if unapproved:
        warnings.append(
            "`implements` takes its own requirements only when relation_ref "
            "names an owner approval the record holds: an owner decision the "
            "owner answered, the owner's verdict accepting the result, or a "
            "Turn the owner wrote (cite the owner's words). "
            f"{', '.join(rel['ref'])} is none of these, so "
            + ("this keeps " + " and ".join(f"{k} {v!r}" for k, v in took.items())
               + f" from the work it names ({', '.join(from_ids)})"
               if took else
               "it keeps whatever the work it names required (nothing was "
               "recorded for it)"))
    return req, warnings


def from_routing(routing) -> dict | None:
    """The requirements an older record implies, from its `routing` fields
    (`difficulty`, `inherited_tier`, `advisory_tier`), or what it recorded
    itself. None when it implies nothing."""
    routing = routing or {}
    if isinstance(routing.get("requirements"), dict):
        return routing["requirements"]
    legacy = compat(routing.get("difficulty"))
    inherited = TIER_NEED.get(routing.get("inherited_tier"))
    if not (legacy or inherited):
        return None
    pick = legacy or inherited
    source = "compat" if legacy else "inherited"
    from_ids = [] if legacy else list(routing.get("inherited_from") or ())

    def one(value):
        return ({"value": value, "source": source, "from": from_ids} if value
                else {"value": "unstated", "source": "default", "from": []})
    scope = compat_scope(routing.get("difficulty")) if legacy else None
    return {"solution": one(pick[0]),
            "reasoning": one(pick[1]),
            "relation": {"value": "new", "ref": [], "source": "default"},
            "exploratory": {"value": False, "done_when": None,
                            "source": "default"},
            "scope": ({"value": scope, "source": "compat"} if scope
                      else {"value": "unstated", "source": "default"}),
            "requires": []}


def demand(req) -> dict:
    """What a recorded requirement asks for, for inheritance: `{"solution",
    "reasoning"}`, None where it said nothing (unstated)."""
    req = req or {}
    sol = (req.get("solution") or {}).get("value")
    rea = (req.get("reasoning") or {}).get("value")
    return {"solution": sol if sol in SOLUTIONS else None,
            "reasoning": rea if rea in LEVELS else None}


def strongest(demands) -> dict:
    """The most demanding of several `demand`s, field by field."""
    sol = [d["solution"] for d in demands if d.get("solution") in SOLUTIONS]
    rea = [d["reasoning"] for d in demands if d.get("reasoning") in LEVELS]
    return {"solution": max(sol, key=solution_rank) if sol else None,
            "reasoning": max(rea, key=level_rank) if rea else None}


def need(req, *, forced=(), floors=()) -> dict:
    """The suitability this work needs: `{"level", "open", "soft", "sources"}`.

    `level` is the reasoning (unstated: `SOFT_LEVEL`, the soft default, with
    `soft` true), `open` is whether the solution is open. `forced` names what
    forces the need whatever else is said (`review`, `authority_sensitive`):
    deep, open allowed. `floors` are `(source, tier)` pairs -- an advisory tier,
    a Workflow activity's default tier -- that can only RAISE it. Scope and size
    are not inputs."""
    req = req or {}
    forced = [f for f in forced or () if f]
    if forced:
        return {**FORCED_NEED, "soft": False, "sources": list(forced)}
    rea = (req.get("reasoning") or {})
    sol = (req.get("solution") or {})
    stated = rea.get("value") in LEVELS
    level = rea["value"] if stated else SOFT_LEVEL
    is_open = sol.get("value") == "open"
    sources = [f"reasoning:{rea.get('source')}"] if stated else []
    if is_open:
        sources.append(f"solution:{sol.get('source')}")
    floors = [(s, TIER_NEED[t]) for s, t in floors or () if t in TIER_NEED]
    # A LEGACY DIFFICULTY WORD YIELDS TO THE FLOORS, as it always did
    # (`routing.required_tier`: the Workflow's default and an advisory tier
    # decide, a difficulty only when neither says anything). Only the new,
    # structured fields -- stated or inherited -- are raised by floors instead.
    legacy_only = (stated and rea.get("source") == "compat"
                   and sol.get("source") in ("compat", "default", None))
    if legacy_only and floors:
        stated, is_open, sources = False, False, []
    if not stated and floors:
        # NOTHING STATED THE REASONING, so the floors are what is said: the
        # strongest of them, even below the soft default (a Workflow activity
        # whose default is economy is economy, as it always was).
        top = max(level_rank(f[1]) for _, f in floors)
        level = LEVELS[top]
        sources += [s for s, f in floors if level_rank(f[1]) == top]
        if any(f[0] == "open" for _, f in floors) and not is_open:
            is_open = True
            sources += [s for s, f in floors if f[0] == "open"
                        and s not in sources]
        return {"level": level, "open": is_open, "soft": False,
                "sources": list(dict.fromkeys(sources))}
    for source, floor in floors:
        raises_level = level_rank(floor[1]) > level_rank(level)
        raises_open = floor[0] == "open" and not is_open
        if raises_level:
            level = floor[1]
        if raises_open:
            is_open = True
        if raises_level or raises_open:
            sources.append(source)
    soft = not stated and not is_open
    return {"level": level, "open": is_open, "soft": soft,
            "sources": ["default"] if soft else list(dict.fromkeys(sources))}


_SOURCE_WORDS = {"compat": "difficulty", "inherited": "inherited",
                 "stated": "stated", "default": "default"}


def tier_sources(need_) -> list[str]:
    """The old `routing.tier_sources` words for what decided this need:
    `review`, `authority_sensitive`, `workflow_default`, `advisory`,
    `difficulty` (a legacy word), `inherited`, `stated` (the new fields), or
    `default`."""
    out = []
    for s in need_.get("sources") or ():
        if ":" in s:
            out.append(_SOURCE_WORDS.get(s.split(":", 1)[1], s))
        else:
            out.append(s)
    return list(dict.fromkeys(out))


def effort_floor(level) -> str:
    """The least effort a need at this level is met at."""
    return EFFORT_FLOOR[level]


def tier_of(need_) -> str:
    """The legacy tier a need corresponds to, for the old `routing` fields:
    open or deep work is frontier, as only frontier was ever open."""
    if need_["open"] or need_["level"] == "deep":
        return "frontier"
    return {"light": "economy", "substantial": "coding"}[need_["level"]]


def need_of_tier(tier) -> dict | None:
    """The need a legacy tier stands for, or None."""
    got = TIER_NEED.get(tier)
    return {"level": got[1], "open": got[0] == "open"} if got else None


def exploratory_allowed(req, need_) -> tuple[bool, str | None]:
    """Whether unknown models may be preferred for this work (D2), and why not.
    Only work stated exploratory with a `done_when`; never review or
    authority-sensitive work, nor deep work with an open solution."""
    exp = (req or {}).get("exploratory") or {}
    if not exp.get("value") or not exp.get("done_when"):
        return False, None
    forced = [s for s in need_.get("sources") or ()
              if s in ("review", "authority_sensitive")]
    if forced:
        return False, (f"exploratory work is not run on an unproven model when it "
                       f"is {' and '.join(forced)}")
    if need_["level"] == "deep" and need_["open"]:
        return False, ("exploratory work needing deep reasoning on an open "
                       "solution is not run on an unproven model")
    return True, None
