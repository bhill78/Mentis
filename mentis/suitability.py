"""Owner standing on model suitability, projected from append-only acts.

Act names are vocabulary data, not new Brain kinds. Proposals never stand.
Legacy ids are deliberately exact: discovery and provider descriptions add no
suitability, and a weak positive statement is unknown for stronger work.
"""
from __future__ import annotations

from copy import deepcopy
from fnmatch import fnmatchcase

PROPOSED = "suitability-proposed"
ESTABLISHED = "suitability-established"
SUPERSEDED = "suitability-superseded"
DECLINED = "suitability-declined"
ACTS = (PROPOSED, ESTABLISHED, SUPERSEDED, DECLINED)
LEVELS = ("light", "substantial", "deep")

LEGACY_STANDING = [
    {"id": f"legacy-tier:{model}", "pattern": model, "runtimes": None,
     "reasoning_max": level, "open": opened, "insufficient": False,
     "basis": "Owner-approved tier table (#1401)", "evidence": [],
     "proposed_by": None, "supersedes": None, "source": "legacy-tier"}
    for model, level, opened in (
        ("claude-haiku-4-5-20251001", "light", False),
        ("claude-sonnet-5", "substantial", False),
        ("claude-opus-5", "deep", True),
        ("claude-fable-5", "deep", True),
        ("gpt-6-luna", "light", False),
        ("gpt-6.1-terra", "substantial", False),
        ("gpt-6.1-sol", "deep", True),
    )
]


def validate(body, cv=None) -> dict:
    """A checked copy; evidence names existing operational acts or entries."""
    if not isinstance(body, dict):
        raise ValueError("a suitability statement is an object")
    pattern = body.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("pattern must be non-empty")
    if body.get("reasoning_max") not in LEVELS:
        raise ValueError(f"reasoning_max is one of {LEVELS}")
    runtimes = body.get("runtimes")
    if runtimes is not None and (not isinstance(runtimes, list) or any(
            not isinstance(r, str) or not r.strip() for r in runtimes)):
        raise ValueError("runtimes is a list of non-empty runtime names or null")
    for key in ("open", "insufficient"):
        if not isinstance(body.get(key, False), bool):
            raise ValueError(f"{key} is a boolean")
    basis = body.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        raise ValueError("basis must say what the statement rests on")
    evidence = body.get("evidence", [])
    if not isinstance(evidence, list) or any(
            not isinstance(e, str) or not e for e in evidence):
        raise ValueError("evidence is a list of act or entry ids")
    if cv is not None:
        for ref in evidence:
            if not cv._act(ref) and not cv.corpus.read([ref]):
                raise ValueError(f"evidence {ref!r} does not exist")
    supersedes = body.get("supersedes")
    if supersedes is not None and (not isinstance(supersedes, str) or not supersedes):
        raise ValueError("supersedes is a statement id or null")
    return {"pattern": pattern, "runtimes": deepcopy(runtimes),
            "reasoning_max": body["reasoning_max"], "open": body.get("open", False),
            "insufficient": body.get("insufficient", False), "basis": basis,
            "evidence": list(evidence), "proposed_by": body.get("proposed_by"),
            "supersedes": supersedes}


def history(cv) -> list[dict]:
    return cv.history(act=ACTS)


def _retired(acts) -> set:
    retired = set()
    for a in acts:
        d = a.get("detail") or {}
        if a["act"] in (SUPERSEDED, DECLINED):
            retired.update(a.get("about") or ())
        if a["act"] == ESTABLISHED:
            if d.get("supersedes"):
                retired.add(d["supersedes"])
            if d.get("proposal"):
                retired.add(d["proposal"])
    return retired


def _statement(a) -> dict:
    return {**deepcopy(a.get("detail") or {}), "id": a["id"],
            "source": "owner" if a["act"] == ESTABLISHED else "proposal"}


def standing(cv) -> list[dict]:
    acts = history(cv)
    retired = _retired(acts)
    return [s for s in deepcopy(LEGACY_STANDING) if s["id"] not in retired] + [
        _statement(a) for a in acts
        if a["act"] == ESTABLISHED and a["id"] not in retired]


def proposals(cv) -> list[dict]:
    acts = history(cv)
    retired = _retired(acts)
    return [_statement(a) for a in acts
            if a["act"] == PROPOSED and a["id"] not in retired]


def verdict(statements, runtime, model_id, aliases, need) -> dict:
    """Exact owner statements precede patterns, which precede legacy.

    Within equal specificity the newest standing statement speaks. Explicit
    insufficiency is a veto at that specificity; absence is never a veto.
    """
    if need.get("level") not in LEVELS or not isinstance(need.get("open"), bool):
        raise ValueError("need names a level and an open boolean")
    matches = []
    for index, s in enumerate(statements):
        pattern = s["pattern"]
        if s.get("runtimes") is not None and runtime not in s["runtimes"]:
            continue
        if not any(fnmatchcase(n, pattern) for n in [model_id, *(aliases or ())] if n):
            continue
        by = ("legacy" if s.get("source") == "legacy-tier" else
              "pattern" if any(c in pattern for c in "*?[") else "direct")
        matches.append(({"legacy": 0, "pattern": 1, "direct": 2}[by], index, by, s))
    if not matches:
        return {"verdict": "unknown", "by": None, "statement": None,
                "why": "No standing suitability statement matches this runtime and model"}
    _, _, by, s = max(matches, key=lambda row: row[:2])
    if s.get("insufficient"):
        value, why = "insufficient", "The owner explicitly states this model is insufficient"
    elif LEVELS.index(s["reasoning_max"]) >= LEVELS.index(need["level"]) and (
            not need["open"] or s["open"]):
        value, why = "established", "Standing suitability covers the required reasoning and solution"
    else:
        value, why = "unknown", "The matching statement does not establish suitability for this need"
    return {"verdict": value, "by": by, "statement": s["id"], "why": why}
