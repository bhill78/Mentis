"""The candidates automatic selection judges: (runtime, model, effort), each
with what is known of its suitability for the work's need
(docs/model-selection-contract.md section 4).

NOT A REGISTRY. Which models exist is MARS's: its `modelCatalogue` per backend,
or, where a backend has none, its `routingModels` and `models`. Which are
suitable is the owner's standing (`mentis.suitability`, Workstream C), read
through `standing` and `verdict` here and nowhere else. Choosing among the
candidates -- capability, capacity, review independence, continuity -- stays in
`MentisService.execution_select`.

PURE, free of the record: `standing` is read by the caller where it holds one,
and handed in.
"""

from __future__ import annotations

from mentis.core import requirements as R
from mentis.core import routing

#: Where a statement taken from MARS's own tier tag comes from: the same
#: owner-approved table (#1401), as MARS advertises it for rollback.
MARS_TAG = "legacy-tier"


def _suitability():
    """`mentis.suitability`, or None while it is not part of this build."""
    try:
        import mentis.suitability as suitability
        return suitability
    except ImportError:
        return None


def legacy_standing() -> list[dict]:
    """The owner-approved tier table as standing statements."""
    s = _suitability()
    return [dict(x) for x in getattr(s, "LEGACY_STANDING", None) or ()]


def standing(cv) -> list[dict]:
    """What stands for this record: established statements plus the legacy
    table. With no record, the legacy table alone."""
    s = _suitability()
    if s is None:
        return []
    if cv is None:
        return legacy_standing()
    return list(s.standing(cv))


def _escape(model: str) -> str:
    """An fnmatch pattern matching exactly this id."""
    return "".join(f"[{c}]" if c in "*?[]" else c for c in model)


def mars_tags(backend, statements) -> list[dict]:
    """MARS's own tier tags (`routingModels`) as legacy standing, for the ids
    the legacy table does not name: the same table, as MARS still advertises
    it. An id the table names is governed by what stands for it (so the owner
    superseding it is honoured), never by the tag."""
    named = {s.get("pattern") for s in legacy_standing()}
    named |= {s.get("pattern") for s in statements or ()
              if s.get("source") == "legacy-tier"}
    runtime = (backend or {}).get("id")
    out = []
    for row in (backend or {}).get("routingModels") or ():
        if not isinstance(row, dict) or row.get("tier") not in routing.TIERS:
            continue
        model = row.get("id")
        if not isinstance(model, str) or not model or model in named:
            continue
        sol, level = R.TIER_NEED[row["tier"]]
        out.append({"id": f"legacy-tier:{runtime}:{model}",
                    "pattern": _escape(model), "runtimes": [runtime],
                    "reasoning_max": level, "open": sol == "open",
                    "insufficient": False, "source": MARS_TAG,
                    "basis": f"MARS tags {model} {row['tier']} (#1401)",
                    "evidence": [], "proposed_by": None, "supersedes": None})
    return out


def verdict(statements, runtime, model, aliases, need) -> dict:
    """The contract's `verdict`, through `mentis.suitability`. Without it, only
    MARS's tags are read, exactly (the tier table as it was)."""
    need = {"level": need["level"], "open": bool(need["open"])}
    s = _suitability()
    if s is not None:
        return s.verdict(statements, runtime, model, list(aliases or ()), need)
    for st in statements:
        if st.get("source") != MARS_TAG or runtime not in (st.get("runtimes") or ()):
            continue
        if st["pattern"] != _escape(model or ""):
            continue
        ok = (R.level_rank(st["reasoning_max"]) >= R.level_rank(need["level"])
              and (not need["open"] or st["open"]))
        return {"verdict": "established" if ok else "unknown", "by": "legacy",
                "statement": st["id"],
                "why": "MARS's tier tag" + ("" if ok else " does not cover this need")}
    return {"verdict": "unknown", "by": None, "statement": None,
            "why": "no standing suitability statement matches"}


def _canonical(efforts) -> list[str] | None:
    if efforts is None:
        return None
    return sorted({e for e in efforts if e in routing.EFFORT_ORDER},
                  key=routing.effort_rank)


def catalogue_of(backend) -> dict | None:
    """MARS's `modelCatalogue` for this backend, when it has one."""
    got = (backend or {}).get("modelCatalogue")
    return got if isinstance(got, dict) and isinstance(got.get("models"), list) \
        else None


def candidates_of(backend) -> list[dict]:
    """Every model this backend offers, as a candidate in MARS's order:
    `{"runtime", "model", "aliases", "efforts", "effort_in_id", "status",
    "group", "order", "source"}`. `efforts` is None when not known for that
    model. A backend that lists no model gives one candidate, its own default
    (`model` None)."""
    b = backend or {}
    runtime = b.get("id")
    tags = {r["id"]: r for r in b.get("routingModels") or ()
            if isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"]}
    out: list[dict] = []
    seen: set = set()

    def add(model, *, aliases=(), efforts=None, effort_in_id=False,
            status="listed", group=None, source):
        if model in seen:
            return
        seen.add(model)
        if efforts is None and model in tags:
            efforts = tags[model].get("efforts")
        out.append({"runtime": runtime, "model": model,
                    "aliases": [a for a in aliases or () if isinstance(a, str)],
                    "efforts": _canonical(efforts),
                    "effort_in_id": bool(effort_in_id), "status": status,
                    "group": group, "order": len(out), "source": source})

    cat = catalogue_of(b)
    if cat is not None:
        for m in cat["models"]:
            if not isinstance(m, dict) or not isinstance(m.get("id"), str) \
                    or not m["id"] or m.get("aliasOf"):
                continue
            add(m["id"], aliases=m.get("aliases") or (),
                efforts=m.get("efforts"),
                effort_in_id=m.get("effortInId") is True,
                status=m.get("status") or "unknown",
                group=m.get("quotaGroup"), source="catalogue")
    else:
        for model in tags:
            add(model, source="routingModels")
        for m in b.get("models") or ():
            model = m.get("id") if isinstance(m, dict) else m
            if isinstance(model, str) and model:
                add(model, effort_in_id=routing.effort_suffix(model) is not None
                    and routing.names_efforts_in_models(b), source="models")
    if not out:
        out.append({"runtime": runtime, "model": None, "aliases": [],
                    "efforts": None, "effort_in_id": False, "status": "unknown",
                    "group": None, "order": 0, "source": "runtime-default"})
    return out


def strength(statement) -> tuple:
    """How much a statement says a model can do: (reasoning, open)."""
    if not statement:
        return (-1, False)
    return (R.level_rank(statement["reasoning_max"]), bool(statement.get("open")))


def judge(backend, cand, need, statements, *, effort=None) -> dict:
    """One candidate judged for this need, before capacity: `{**cand, "effort",
    "send_effort", "effort_verified", "verdict", "by", "statement", "strength",
    "usable", "why"}`. `usable` is whether the effort floor (or a named effort)
    can be met and nothing excludes it; `verdict` says if it is suitable."""
    model = cand["model"]
    floor = R.effort_floor(need["level"])
    default = routing.default_model_of(backend)
    subject = model or default
    if subject:
        v = verdict(statements, cand["runtime"], subject, cand["aliases"], need)
    else:
        v = {"verdict": "unknown", "by": None, "statement": None,
             "why": "the runtime does not say which model it runs"}
    stmt = next((s for s in statements if s.get("id") == v["statement"]), None)
    row = {**cand, "verdict": v["verdict"], "by": v["by"],
           "statement": v["statement"], "strength": strength(
               stmt if v["verdict"] == "established" else None),
           "effort": None, "send_effort": None, "effort_verified": False,
           "usable": True, "why": v["why"]}
    if cand["status"] == "refused":
        return {**row, "usable": False,
                "why": "MARS saw the runtime refuse this model"}
    if model is None:
        if effort:
            row.update(effort=effort, send_effort=effort)
        return row
    suffix = routing.effort_suffix(model) if cand["effort_in_id"] else None
    if effort:
        if suffix is not None:
            if suffix != effort:
                return {**row, "usable": False,
                        "why": f"its id says effort {suffix}, not the named {effort}"}
            return {**row, "effort": effort, "send_effort": effort,
                    "effort_verified": True}
        if cand["efforts"] is None:
            return {**row, "usable": False,
                    "why": f"whether it takes the named effort {effort!r} is not known"}
        if effort not in cand["efforts"] or routing.effort_conflicts(
                backend, model, effort):
            return {**row, "usable": False,
                    "why": f"it does not advertise the named effort {effort!r}"}
        return {**row, "effort": effort, "send_effort": effort,
                "effort_verified": True}
    if suffix is not None:
        if routing.effort_rank(suffix) < routing.effort_rank(floor):
            return {**row, "usable": False,
                    "why": f"its effort {suffix} is below the {floor} this needs"}
        # THE EFFORT IS THE MODEL: sending it again adds nothing.
        return {**row, "effort": suffix, "effort_verified": True}
    if cand["efforts"] is None:
        return {**row, "effort_floor_unverified": True}
    enough = [e for e in cand["efforts"]
              if routing.effort_rank(e) >= routing.effort_rank(floor)
              and not routing.effort_conflicts(backend, model, e)]
    if not enough:
        return {**row, "usable": False,
                "why": f"it advertises no effort at or above {floor}"}
    return {**row, "effort": enough[0], "send_effort": enough[0],
            "effort_verified": True}


def rank(row) -> tuple:
    """Least sufficient first: verified efforts before unverified, then the
    weaker statement, then the lesser effort."""
    effort = row.get("effort")
    return (0 if row.get("effort_verified") else 1, row["strength"],
            routing.effort_rank(effort) if effort in routing.EFFORT_ORDER
            else len(routing.EFFORT_ORDER))


def order(backend, rows) -> list[dict]:
    """Rows of one backend least sufficient first; then its default model,
    then MARS's order."""
    default = routing.default_model_of(backend)
    return sorted(rows, key=lambda r: (rank(r), 0 if r["model"] == default else 1,
                                       r["order"]))


def tier_of_row(row) -> str | None:
    """The legacy tier an established row's statement corresponds to."""
    lvl, opened = row["strength"]
    if lvl < 0:
        return None
    return R.tier_of({"level": R.LEVELS[lvl], "open": opened})


def public(row, *, outcome, why=None, capacity=None) -> dict:
    """What `selection.candidates` records of a row."""
    return {"runtime": row["runtime"], "model": row["model"],
            "effort": row.get("effort"), "verdict": row.get("verdict"),
            "by": row.get("by"), "statement": row.get("statement"),
            "capacity": capacity if capacity is not None else row.get("capacity"),
            "outcome": outcome, "why": why or row.get("why"),
            **({"effort_floor_unverified": True}
               if row.get("effort_floor_unverified") else {}),
            **({"source": row["source"]} if row.get("source") else {})}


def route_of(row) -> dict:
    """A judged row as the route selection runs: the model and the effort it
    SENDS (none where the effort is in the id or not known), the legacy tier
    its statement corresponds to, and the row."""
    return {"model": row["model"], "tier": tier_of_row(row),
            "effort": row.get("send_effort"), "row": row,
            **({"exploratory": True} if row.get("verdict") == "unknown" else {})}


def unsuited_words(rows) -> str:
    """Why nothing on a runtime is suitable for this need, briefly."""
    if not rows:
        return "it offers no model"
    counts: dict = {}
    for r in rows:
        if r.get("verdict") == "insufficient":
            key = "insufficient by the owner's statement"
        elif r.get("verdict") == "established" and not r.get("usable"):
            key = r.get("why") or "not usable"
        elif r.get("verdict") == "established":
            key = r.get("capacity_why") or "exhausted"
        else:
            key = "suitability not established"
        counts[key] = counts.get(key, 0) + 1
    return "; ".join(f"{n} model{'s' if n > 1 else ''}: {k}"
                     for k, n in counts.items())


def account(listed, unlisted, picked, chosen_runtime, route) -> list[dict]:
    """`selection.candidates`: every candidate judged, with its outcome and why.

    `selected` -- what runs; `excluded` -- insufficient (the statement cited),
    refused, unusable at this effort, exhausted, or kept off by a gate;
    `deferred` -- suitable or unknown, and not chosen, with why."""
    out = list(unlisted)
    for runtime, rows in listed.items():
        for r in rows:
            if picked is not None and r is picked:
                out.append(public(r, outcome="selected",
                                  why=("not established; preferred for "
                                       "exploratory work (D2)"
                                       if r["verdict"] == "unknown" else
                                       "established and chosen")))
            elif r["verdict"] == "insufficient":
                out.append(public(r, outcome="excluded",
                                  why=f"insufficient by statement {r['statement']}"))
            elif not r["usable"]:
                out.append(public(r, outcome="excluded"))
            elif r.get("capacity") == "exhausted":
                out.append(public(r, outcome="excluded",
                                  why=r.get("capacity_why")))
            elif r["verdict"] == "unknown":
                out.append(public(r, outcome="deferred",
                                  why=f"suitability not established: {r['why']}"))
            else:
                out.append(public(r, outcome="deferred",
                                  why="established; another candidate was chosen"))
    if picked is None and chosen_runtime:
        # THE RUNTIME'S OWN DEFAULT RAN: nothing above was chosen.
        out.append({"runtime": chosen_runtime, "model": None, "effort": None,
                    "verdict": None, "by": None, "statement": None,
                    "capacity": None, "outcome": "selected",
                    "why": ("the runtime's own default: "
                            + (route.get("tier_unfulfilled_because")
                               or "no candidate was chosen"))})
    return out
