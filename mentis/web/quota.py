"""Known quota failures, read back from the record (runtime capacity, item 5).

WHY. A run that hit its runtime's quota is recorded as `delivery-failed` with
`runtime_evidence.error_kind == "rate_limited"` (dispatch), and nothing read it
back: automatic selection kept choosing the runtime that had just refused
(audit 2026-10-29, Gemini at 16:22 and 16:32).

WHAT HOLDS. Each such failure holds its own act's runtime from AUTOMATIC
selection until the reset its runtime reported (`runtime_evidence.resets_at`,
kept from MARS's `retryAfterSeconds`), or, with no reset reported, for the
owner's 60-minute cooldown from the failure.

HELD PER (RUNTIME, MODEL). A failure whose `execution-started` act says which
concrete model ran holds that model; one with no known model holds the whole
runtime. Holds of sibling models stand side by side.

A hold ends when it expires -- judged against `now` on every call -- or when a
later run reported its work done (a `result-returned` whose terminal is
`reported_done` and whose start, its `caused_by`, came after the failure): a
success on a known model clears that model's hold and the runtime-wide one,
never a sibling's; a success on an unknown model clears only the runtime-wide
one. Which model it ran is read from its start, never from anything current.

A PURE READ. Nothing is stored apart from the acts the record already holds;
nothing retries and nothing is scheduled. The history read is shared while the
record's operational position has not moved (`SharedAnswers`); expiry is
evaluated fresh each call.

    holds = {runtime: {"until": epoch, "why": str, "model": str | None,
                       "since": epoch, "basis": act id,
                       "scopes": [every standing hold of this runtime, one per
                                  model-or-None, each with the same fields]}}

The outer fields are the longest-standing scope's, so a reader that asks only
whether a runtime is held and why reads what it always read.
"""

from __future__ import annotations

import time

FAILED = "delivery-failed"
RETURNED = "result-returned"
REPORTED_DONE = "reported_done"

#: How far back a quota failure is read: long enough to cover a reported reset
#: (weekly windows), short enough to stay a bounded read.
LOOKBACK = 7 * 24 * 3600
#: The owner's cooldown for a quota failure that reported no reset (2026-10-29).
COOLDOWN = 3600


def quota_holds(cv, now: float | None = None) -> dict:
    """The holds on automatic selection from known quota failures, as
    `{runtime: {"until", "why", "model", "since", "basis", "scopes"}}`. Empty
    when none holds, or when the record cannot be read."""
    now = time.time() if now is None else now
    try:
        pending = _pending(cv, now)
    except Exception:                                     # noqa: BLE001
        return {}
    scopes: dict = {}
    for hold in pending:
        if hold["until"] <= now:
            continue
        key = (hold["runtime"], hold["model"])
        kept = scopes.get(key)
        # THE LONGEST STANDING HOLD SPEAKS for its scope: a reported weekly
        # reset is not shortened by a later failure that reported none.
        if kept is None or hold["until"] > kept["until"]:
            scopes[key] = {k: hold[k] for k in
                           ("until", "why", "model", "since", "basis")}
    out: dict = {}
    for (runtime, _), hold in scopes.items():
        kept = out.get(runtime)
        if kept is None or hold["until"] > kept["until"]:
            out[runtime] = dict(hold)
        out[runtime].setdefault("scopes", [])
    for (runtime, _), hold in scopes.items():
        out[runtime]["scopes"].append(hold)
    return out


def _pending(cv, now) -> list:
    """Every uncleared quota hold in the lookback, expired or not: what the
    record says, shared while the record holds still."""
    from mentis.conversation.shared_answer import answers_of
    corpus = cv.corpus

    def version():
        if corpus.uncommitted:
            return None
        return corpus.advance()[1]
    return answers_of(cv).get(("quota-holds",), lambda: _read(cv, now),
                              version=version)


def _read(cv, now) -> list:
    acts = cv.history(act=(FAILED, RETURNED), since=now - LOOKBACK,
                      newest_first=True)
    failures = [a for a in acts if a["act"] == FAILED and a.get("runtime")
                and _evidence(a).get("error_kind") == "rate_limited"]
    if not failures:
        return []
    # WHEN EACH SUCCESS STARTED AND ON WHICH MODEL, from its `execution-started`
    # act: a success that began before the failure says nothing about the
    # runtime after it, and the same act says which model each failure ran.
    done = [a for a in acts if a["act"] == RETURNED and a.get("runtime")
            and (a.get("detail") or {}).get("terminal") == REPORTED_DONE
            and a.get("caused_by")]
    starts = {}
    ids = list(dict.fromkeys(a["caused_by"] for a in [*done, *failures]
                             if a.get("caused_by")))
    for k in range(0, len(ids), 500):
        for s in cv.history(id=tuple(ids[k:k + 500])):
            starts[s["id"]] = s
    since_any: dict = {}
    since_model: dict = {}
    for a in done:
        start = starts.get(a["caused_by"])
        if start is None:
            continue
        began = start["at"]
        if began > since_any.get(a["runtime"], float("-inf")):
            since_any[a["runtime"]] = began
        ran = _started_model(start)
        if ran and began > since_model.get((a["runtime"], ran), float("-inf")):
            since_model[(a["runtime"], ran)] = began
    out = []
    for f in failures:
        ev = _evidence(f)
        model = _started_model(starts.get(f.get("caused_by")))
        if not model:
            model = ev.get("model") if isinstance(ev.get("model"), str) else None
        # A MODEL'S HOLD IS CLEARED BY A SUCCESS OF THAT MODEL; A RUNTIME-WIDE
        # ONE BY ANY SUCCESS ON THE RUNTIME.
        cleared = (since_model.get((f["runtime"], model), float("-inf")) if model
                   else since_any.get(f["runtime"], float("-inf")))
        if cleared > f["at"]:
            continue
        reset = ev.get("resets_at")
        reported = isinstance(reset, (int, float)) and not isinstance(reset, bool)
        until = float(reset) if reported else f["at"] + COOLDOWN
        out.append({
            "runtime": f["runtime"], "until": until, "model": model,
            "since": f["at"], "basis": f["id"],
            "why": (f"{f['runtime']} hit its quota at {_clock(f['at'])}; held "
                    f"from automatic selection until {_clock(until, f['at'])} "
                    + ("(reported reset)" if reported
                       else "(60-minute cooldown, no reset reported)"))})
    return out


def _evidence(act) -> dict:
    ev = (act.get("detail") or {}).get("runtime_evidence")
    return ev if isinstance(ev, dict) else {}


def _started_model(start) -> str | None:
    """The concrete model an `execution-started` act says ran, or None."""
    d = (start or {}).get("detail") or {}
    for key in ("effective_model", "selected_model"):
        if isinstance(d.get(key), str) and d[key]:
            return d[key]
    return None


def _clock(t, day_of=None) -> str:
    """HH:MM local time; with the date when it falls on another day than
    `day_of` (a reset days away is not read as today's)."""
    at = time.localtime(t)
    if day_of is not None and time.localtime(day_of)[:3] != at[:3]:
        return time.strftime("%Y-%m-%d %H:%M", at)
    return time.strftime("%H:%M", at)


__all__ = ["quota_holds", "LOOKBACK", "COOLDOWN"]
