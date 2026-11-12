"""Recorded outcome facts per attempt; no scores or suitability promotion.

An execution handle can be reused. Attribution therefore follows the start
act and write order, including an explicit result reference on owner verdicts.
An exit, or an agent's claim of success, never becomes recorded success here.
"""
from __future__ import annotations

from collections import defaultdict
import json

RESULT_VERDICT = "result-verdict"
LEVELS = ("claimed", "recorded", "verified", "owner_accepted", "owner_rejected")
FAILURE_CLASSES = ("substantive", "infrastructure", "quota", "permission",
                   "cancelled", "interrupted", "capability_missing", "unclassified")
_ACTS = ("expectation-recorded", "execution-started", "delivery-failed",
         "result-returned", "result-recovered", "outcome-claimed", "expectation-met",
         "review-verdict", RESULT_VERDICT, "execution-stop-asked")


def requirement_profile(request=None, start=None) -> dict:
    """Group by requirement values, never by provenance or unique lineage ids."""
    rd, sd = (request or {}).get("detail") or {}, (start or {}).get("detail") or {}
    routing = {**(rd.get("routing") or {}), **(sd.get("routing") or {})}
    req = sd.get("requirements") or routing.get("requirements") or rd.get("requirements") or {}

    def value(key, default):
        got = req.get(key, default)
        return got.get("value", default) if isinstance(got, dict) else got

    compat = {"mechanical": ("specified", "light"),
              "bounded": ("specified", "substantial"),
              "routine": ("specified", "substantial"),
              "complex": ("open", "deep"), "architecture": ("open", "deep"),
              "debugging": ("open", "deep")}
    solution, reasoning = compat.get(routing.get("difficulty") or rd.get("difficulty"),
                                     ("unstated", "unstated"))
    return {"solution": value("solution", solution),
            "reasoning": value("reasoning", reasoning),
            "relation": value("relation", "new"),
            "exploratory": value("exploratory", False),
            "requires": sorted(set(req.get("requires") or routing.get("requires")
                                   or rd.get("requires") or ()))}


def failure_class(failure) -> str:
    """Classify actual dispatch end/pre-start fields, keeping unknowns unknown."""
    d = (failure or {}).get("detail") or {}
    ev = d.get("runtime_evidence") or {}
    kind = str(ev.get("error_kind") or "").lower()
    terminal = str(d.get("terminal") or "").lower()
    stop = str(ev.get("stop_reason") or "").lower()
    text = " ".join(str(x or "") for x in (
        (failure or {}).get("because"), d.get("error"), ev.get("error"))).lower()
    explicit = d.get("failure_classification")
    if (kind in ("rate_limited", "quota", "quota_exhausted") or explicit == "quota"
            or (d.get("before_execution_started") and any(s in text for s in (
                "every eligible runtime is exhausted", "held after a quota failure",
                "quota hold", "hit its quota")))):
        return "quota"
    if terminal == "cancelled" or stop == "cancelled":
        return "cancelled"
    if terminal == "interrupted" or kind == "server_restart":
        return "interrupted"
    if (kind in ("permission_denied", "consent_denied", "permission_refused", "consent_refused")
            or ev.get("denied") or explicit == "permission"
            or any(s in text for s in ("permission denied", "permission refused",
                                       "consent refused", "consent denied"))):
        return "permission"
    requested = d.get("requested") or {}
    if (kind == "capability_missing" or explicit == "capability_missing"
            or (d.get("before_execution_started") and requested.get("requires")
                and any(s in text for s in ("no available runtime can be given this work",
                                            "no runtime left to choose from is known to have",
                                            "unsupported", "unknown capability",
                                            "unconfirmed_capabilities", "capability")))):
        return "capability_missing"
    if (d.get("terminated_by") or kind in ("backend_exited", "backend_unavailable")
            or "timeout" in kind or terminal == "stopped_at_deadline"
            or d.get("before_execution_started") or explicit == "infrastructure"):
        return "infrastructure"
    if explicit in FAILURE_CLASSES:
        return explicit
    return "unclassified"


def per_execution(cv, *, expectation=None) -> list[dict]:
    """Evidence for each recorded start (and separately failures before start).

    Review targets/independence follow the existing completion projection.
    Later facts with an explicit result/claim reference stay with that attempt.
    Unscoped request verdicts attach to its latest attempt at the time stated.
    """
    from mentis.operational.completion import verdict_index

    acts = cv.history(act=_ACTS)
    positions = {a["id"]: i for i, a in enumerate(acts)}
    requests = {a["id"]: a for a in acts if a["act"] == "expectation-recorded"}
    attempts, by_start = [], {}
    for a in acts:
        if a["act"] != "execution-started":
            continue
        request = a.get("caused_by")
        if request not in requests:
            request = next((r for r in a.get("about") or () if r in requests), request)
        d = a.get("detail") or {}
        row = {"started": a["id"], "execution": a.get("execution"),
               "expectation": request, "participant": a.get("actor"),
               "runtime": a.get("runtime"), "model": d.get("effective_model"),
               "effort": d.get("selected_effort") or d.get("requested_effort"),
               "requirements": requirement_profile(requests.get(request), a),
               "level": None, "failure_class": None, "evidence": [],
               "reconciled_by": [], "before_start": False}
        attempts.append(row)
        by_start[a["id"]] = row
    by_request, by_execution = defaultdict(list), defaultdict(list)
    for row in attempts:
        by_request[row["expectation"]].append(row)
        if row["execution"]:
            by_execution[row["execution"]].append(row)
    attributed = dict(by_start)

    def preceding(rows, act):
        return next((r for r in reversed(rows)
                     if positions[r["started"]] <= positions[act["id"]]), None)

    def target(a):
        d = a.get("detail") or {}
        if d.get("reconciled_from") in attributed:
            return attributed[d["reconciled_from"]]
        if a.get("caused_by") in by_start:
            return by_start[a["caused_by"]]
        execution = a.get("execution") or d.get("claimed_by")
        rows = by_execution.get(execution, ()) if execution else ()
        request = a.get("caused_by")
        if request in requests:
            rows = [r for r in rows if r["expectation"] == request]
        return preceding(rows, a)

    facts = defaultdict(list)
    for a in acts:
        name, d = a["act"], a.get("detail") or {}
        if name not in ("outcome-claimed", "expectation-met", "delivery-failed",
                        "result-returned", "result-recovered", "execution-stop-asked"):
            continue
        row = target(a)
        if row is None and name == "delivery-failed" and d.get("before_execution_started"):
            request = a.get("caused_by")
            row = {"started": None, "execution": None, "expectation": request,
                   "participant": a.get("actor"),
                   "runtime": a.get("runtime") or (d.get("requested") or {}).get("runtime"),
                   "model": None, "effort": None,
                   "requirements": requirement_profile(requests.get(request)),
                   "level": None, "failure_class": None, "evidence": [],
                   "reconciled_by": [], "before_start": True}
            attempts.append(row)
        # Older met acts sometimes name only the request. They can describe
        # its current attempt, but are kept distinct from an agent claim.
        if row is None and name == "expectation-met":
            row = preceding(by_request.get(a.get("caused_by"), ()), a)
        if row is not None:
            attributed[a["id"]] = row
            facts[id(row)].append(a)

    for a in acts:
        if a["act"] != RESULT_VERDICT:
            continue
        d = a.get("detail") or {}
        request = next((r for r in a.get("about") or () if r in requests), a.get("caused_by"))
        row = (attributed.get(d["result"]) if d.get("result") else
               preceding(by_request.get(request, ()), a))
        if row is not None and row["expectation"] == request:
            facts[id(row)].append(a)

    for request, reviews in verdict_index(cv).items():
        for a in reviews:
            if a["id"] not in positions:
                continue
            # A review begun before a retry judges the earlier attempt even
            # when the reviewer returns after that retry has started.
            review_request = next((r for r in a.get("about") or () if r in requests),
                                  a.get("caused_by"))
            row = preceding(by_request.get(request, ()), requests.get(review_request, a))
            if (row is not None and a.get("actor")
                    and a["actor"] != row["participant"]
                    and (not a.get("execution") or a["execution"] != row["execution"])):
                facts[id(row)].append(a)

    for row in attempts:
        own = sorted(facts[id(row)], key=lambda a: positions[a["id"]])
        row["evidence"] = [a["id"] for a in own]
        levels = set()
        latest_review, latest_owner = None, None
        failures, stopped = [], False
        for a in own:
            name, d = a["act"], a.get("detail") or {}
            if name == "outcome-claimed":
                levels.add("claimed")
            elif name == "expectation-met":
                levels.add("recorded")
                if d.get("reconciled_by"):
                    row["reconciled_by"].append(d["reconciled_by"])
            elif name == "review-verdict":
                latest_review = d.get("verdict")
            elif name == RESULT_VERDICT:
                latest_owner = d.get("verdict")
            elif name == "delivery-failed":
                failures.append(a)
            elif name == "execution-stop-asked":
                stopped = True
        if latest_review == "pass":
            levels.add("verified")
        row["level"] = next((x for x in reversed(LEVELS[:3]) if x in levels), None)
        if latest_owner in ("accepted", "rejected"):
            row["level"] = "owner_" + latest_owner
        row["review_verdict"] = latest_review
        row["owner_verdict"] = latest_owner
        row["facts"] = sorted(levels, key=LEVELS.index)
        if latest_owner == "rejected" or (latest_owner is None and latest_review == "block"):
            row["failure_class"] = "substantive"
        elif stopped:
            row["failure_class"] = "cancelled"
        elif failures:
            row["failure_class"] = failure_class(failures[-1])
    attempts.sort(key=lambda r: positions[r["started"] or r["evidence"][0]])
    return [r for r in attempts if expectation is None or r["expectation"] == expectation]


def classify(cv, execution) -> dict | None:
    """Most recent attempt for a handle, or the exact execution-started id."""
    rows = [r for r in per_execution(cv)
            if r["started"] == execution or r["execution"] == execution]
    return rows[-1] if rows else None


def report(cv, *, runtime=None, model=None, expectation=None) -> dict:
    """Counts of recorded facts by runtime, effective model and requirements.

    Facts overlap (a verified result may also be claimed and recorded).
    Exclusive ladder counts and failure counts are supplied separately.
    No facts are synthesised for a higher rung's missing lower rung.
    """
    groups = {}
    rows = per_execution(cv, expectation=expectation)
    for row in rows:
        if runtime is not None and row["runtime"] != runtime:
            continue
        if model is not None and row["model"] != model:
            continue
        key = (row["runtime"], row["model"], json.dumps(row["requirements"], sort_keys=True))
        if key not in groups:
            groups[key] = {"runtime": row["runtime"], "model": row["model"],
                           "requirements": row["requirements"], "attempts": 0,
                           "before_start": 0, "facts": {k: 0 for k in LEVELS[:3]},
                           "levels": {k: 0 for k in (*LEVELS, "none")},
                           "failures": {k: 0 for k in FAILURE_CLASSES}}
        g = groups[key]
        g["attempts"] += 1
        g["before_start"] += int(row["before_start"])
        g["levels"][row["level"] or "none"] += 1
        for fact in row["facts"]:
            g["facts"][fact] += 1
        if row["failure_class"]:
            g["failures"][row["failure_class"]] += 1
    models = list(groups.values())
    return {"models": models, "attempts": sum(g["attempts"] for g in models)}


def substantive_failure(cv, expectation) -> dict | None:
    """D4: the latest attempt's substantive negative, never a quota escalation."""
    rows = per_execution(cv, expectation=expectation)
    latest = rows[-1] if rows else None
    return latest if latest and latest["failure_class"] == "substantive" else None
