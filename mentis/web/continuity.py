"""Session continuity across runs of the same work (WS-P,
docs/modernization/CONTRACT.md).

MARS keeps no process between runs. What it can keep is the RUNTIME's own
session (a Claude Code session id, an agy conversation): session/new returns a
token for it (`_meta["mars/resume"]`), and a later session/new may ask for it
back. This module decides, from the record alone, whether a run may ask:

  * only a CONTINUATION -- the same expectation resumed (`resume_if_ready` ->
    `resume_dispatch`) -- by the same participant, on the same backend and
    model, whose previous run of that expectation ended with a result and a
    token;
  * and only while nothing the session was told has changed: the governing
    material (the binding's fingerprint), the Workflow (its change line), the
    run's authority and its consent. Any difference at all -- narrowed,
    revoked or widened -- starts a fresh session, which is told everything.

It also writes the CONTINUATION PROMPT a resumed session is sent: a resume
notice, what is new (the resume text: follow-ups, children's results,
answered decisions), and always the current authority, consent and the
closing block. The full composition is built anyway, and sent whenever MARS
does not say it resumed.

Nothing here permits anything, and nothing is kept outside the record.
"""

from __future__ import annotations

import hashlib
import json

#: The act a run's normal end is recorded as (`dispatch.RETURNED`).
_RETURNED = "result-returned"
_STARTED = "execution-started"


def signature(value) -> str:
    """A short, stable tag of a JSON-shaped value."""
    raw = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def consent_signature(c: dict | None) -> str:
    """What of a run's consent a session was told, as a tag: its mode,
    workspaces, routine categories, the tools the owner allowed and whether
    research is authorised. Not who granted it or when."""
    c = c or {}
    return signature({
        "mode": c.get("mode"),
        "workspaces": sorted(c.get("workspaces") or ()),
        "categories": sorted(c.get("categories") or ()),
        "tools": sorted(c.get("tools") or ()),
        "research": bool((c.get("research") or {}).get("authorized")),
    })


def authority_signature(authority: dict | None) -> str:
    a = authority or {}
    return signature({"scope": a.get("scope"),
                      "organising": sorted(a.get("organising") or ()),
                      "permitted": sorted(a.get("permitted") or ())})


def basis(*, participant, backend, model, context, authority, consent,
          workflow_line) -> dict:
    """What a session was opened under, recorded beside its token so a later
    run can tell whether it is still the same."""
    return {"participant": participant, "backend": backend,
            "model": model or None, "context": context or None,
            "authority": authority_signature(authority),
            "consent": consent_signature(consent),
            "workflow": signature(workflow_line or "")}


def previous_session(cv, expectation, participant, *, exclude=None):
    """The runtime session the latest earlier run of `expectation` left, as
    `(runtime_session, None)`, or `(None, why not)`."""
    try:
        acts = [a for a in cv.history(caused_by=expectation)
                if a.get("act") == _STARTED and a.get("id") != exclude]
    except Exception as exc:                              # noqa: BLE001
        return None, f"the earlier runs could not be read ({exc})"
    if not acts:
        return None, "no earlier run of this work"
    last = max(enumerate(acts), key=lambda p: (p[1].get("at") or 0, p[0]))[1]
    if last.get("actor") != participant:
        return None, "the earlier run was another participant's"
    try:
        ends = [a for a in cv.history(caused_by=last["id"])
                if a.get("act") == _RETURNED]
    except Exception as exc:                              # noqa: BLE001
        return None, f"how the earlier run ended could not be read ({exc})"
    if not ends:
        return None, "the earlier run did not end with a result"
    held = (ends[-1].get("detail") or {}).get("runtime_session")
    if not isinstance(held, dict) or not held.get("token"):
        return None, "the earlier run left no runtime session"
    if held.get("supported") is False:
        return None, "MARS said that runtime session cannot be resumed"
    return held, None


def decide(cv, *, expectation, participant, resumed_from, now: dict,
           exclude=None) -> tuple[dict | None, str]:
    """Whether this run asks MARS to continue the previous runtime session:
    `({"token"}, why)` or `(None, why not)`. `now` is this run's `basis`."""
    if not resumed_from:
        return None, "not a continuation of the same work"
    if not expectation:
        return None, "this run carries no request"
    try:
        from mentis.web.dispatch import withdrawal_of
        if withdrawal_of(cv, expectation):
            return None, "the request was withdrawn"
    except Exception:                                     # noqa: BLE001
        return None, "whether the request was withdrawn could not be read"
    held, why = previous_session(cv, expectation, participant, exclude=exclude)
    if held is None:
        return None, why
    for key, words in (("participant", "a different participant"),
                       ("backend", "a different runtime"),
                       ("model", "a different model"),
                       ("context", "the governing material changed"),
                       ("workflow", "the Workflow changed"),
                       ("authority", "what the work may do changed"),
                       ("consent", "the run consent changed")):
        if held.get(key) != now.get(key):
            return None, f"fresh session: {words}"
    return {"token": held["token"]}, "same work, participant, runtime and terms"


RESUME_NOTICE = (
    "# Continuing your session\n\n"
    "This is the same session as your previous run of this work: what you "
    "were told then still stands, the governing material and the reply format "
    "included, and nothing about them has changed. What is new since that run "
    "follows. The authority and consent below are the current ones and "
    "replace anything you were told before.")


def continuation_prompt(*, task: str, authority: dict | None,
                        authority_line: str | None, consent_text: str,
                        closing: str, split: str) -> str:
    """What a resumed session is sent. `task` is the opening task block (the
    resume text, with the owner's follow-ups and what returned), `closing`
    the closing block, which stays last."""
    a = authority or {}
    may = (f"What this run may do now: scope {a.get('scope') or 'worker'}; "
           + ("organising operations: " + ", ".join(a["organising"])
              if a.get("organising") else "no organising operations")
           + ". Mentis checks every operation against this.")
    if authority_line:
        may += "\n\n" + authority_line
    parts = [RESUME_NOTICE, task, may]
    if consent_text.strip():
        parts.append(consent_text.strip())
    parts.append(closing)
    return split.join(parts)
