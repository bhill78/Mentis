"""TEST-ONLY stand-ins for `mentis.suitability` and `mentis.evidence`
(Workstream C), implementing exactly the contract's semantics
(docs/model-selection-contract.md section 3), so Workstream B+D's tests run
before C merges. `tests/conftest.py` installs them ONLY when the real modules
cannot be imported; once C is merged, the real ones are used and this is
unused.
"""

from __future__ import annotations

import sys
import types
from fnmatch import fnmatchcase

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

ESTABLISHED = "suitability-established"
SUPERSEDED = "suitability-superseded"
DECLINED = "suitability-declined"


def standing(cv) -> list[dict]:
    acts = cv.history(act=(ESTABLISHED, SUPERSEDED, DECLINED)) if cv else []
    retired = set()
    for a in acts:
        if a["act"] in (SUPERSEDED, DECLINED):
            retired.update(a.get("about") or ())
        if a["act"] == ESTABLISHED and (a.get("detail") or {}).get("supersedes"):
            retired.add(a["detail"]["supersedes"])
    return [dict(s) for s in LEGACY_STANDING if s["id"] not in retired] + [
        {**(a.get("detail") or {}), "id": a["id"], "source": "owner"}
        for a in acts if a["act"] == ESTABLISHED and a["id"] not in retired]


def verdict(statements, runtime, model_id, aliases, need) -> dict:
    matches = []
    for index, s in enumerate(statements):
        if s.get("runtimes") is not None and runtime not in s["runtimes"]:
            continue
        if not any(fnmatchcase(n, s["pattern"])
                   for n in [model_id, *(aliases or ())] if n):
            continue
        by = ("legacy" if s.get("source") == "legacy-tier" else
              "pattern" if any(c in s["pattern"] for c in "*?[") else "direct")
        matches.append(({"legacy": 0, "pattern": 1, "direct": 2}[by], index, by, s))
    if not matches:
        return {"verdict": "unknown", "by": None, "statement": None,
                "why": "no standing suitability statement matches"}
    _, _, by, s = max(matches, key=lambda row: row[:2])
    if s.get("insufficient"):
        value, why = "insufficient", "the owner states it is insufficient"
    elif LEVELS.index(s["reasoning_max"]) >= LEVELS.index(need["level"]) and (
            not need["open"] or s["open"]):
        value, why = "established", "standing suitability covers this need"
    else:
        value, why = "unknown", "the matching statement does not cover this need"
    return {"verdict": value, "by": by, "statement": s["id"], "why": why}


def substantive_failure(cv, expectation):
    """The prior attempt's evidence if its work failed substantively: an owner
    `result-verdict` rejecting it, or a `review-verdict` blocking it."""
    for a in reversed(cv.history(caused_by=expectation)):
        d = a.get("detail") or {}
        if a["act"] == "result-verdict" and d.get("verdict") == "rejected":
            return {"class": "substantive", "level": "owner_rejected",
                    "acts": [a["id"]], "why": d.get("why") or "owner rejected"}
        if a["act"] == "review-verdict" and d.get("verdict") == "block":
            return {"class": "substantive", "level": "review_blocked",
                    "acts": [a["id"]], "why": d.get("why") or "review blocked"}
    return None


def install() -> None:
    """Register the stand-ins where the real modules are missing."""
    try:
        import mentis.suitability  # noqa: F401
    except ImportError:
        mod = types.ModuleType("mentis.suitability")
        mod.LEVELS, mod.LEGACY_STANDING = LEVELS, LEGACY_STANDING
        mod.standing, mod.verdict = standing, verdict
        mod.__stub__ = True
        sys.modules["mentis.suitability"] = mod
    try:
        import mentis.evidence  # noqa: F401
    except ImportError:
        mod = types.ModuleType("mentis.evidence")
        mod.substantive_failure = substantive_failure
        mod.__stub__ = True
        sys.modules["mentis.evidence"] = mod
