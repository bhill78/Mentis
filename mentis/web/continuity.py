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
import os

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


def consent_before_start(cv, expectation, workspace) -> dict:
    """The consent a run of `expectation` in `workspace` starts with, read
    before its start is recorded: what `consent.of_run` gives a new run (its
    request's consent, the run's workspace where that counts, and no tools
    allowed for it yet), so the continuity decision can be recorded on the
    start itself."""
    from mentis.operational import consent as _consent
    if not expectation:
        return {}
    got = _consent.of_request(cv, expectation)
    ws = list(got["workspaces"])
    if workspace and (got["granted_at"] == expectation or got["source"] == "none"
                      or any(_consent.inside(workspace, w) for w in ws)):
        if workspace not in ws:
            ws.insert(0, workspace)
    return {**got, "workspaces": ws, "tools": []}


def start_note(resume, why, resumed_from) -> str | None:
    """What the start record says about the runtime session, in words."""
    if resume:
        return ("continuation asked: MARS is asked to resume the runtime "
                "session this work's previous run left; whether it did is "
                "recorded on this run's end (`continuity`)")
    if resumed_from:
        return f"a fresh runtime session: {why.removeprefix('fresh session: ')}"
    return None


def authority_signature(authority: dict | None) -> str:
    a = authority or {}
    return signature({"scope": a.get("scope"),
                      "organising": sorted(a.get("organising") or ()),
                      "permitted": sorted(a.get("permitted") or ())})


def _path(p) -> str | None:
    if not p:
        return None
    return os.path.normcase(os.path.normpath(os.path.abspath(str(p))))


def basis(*, participant, backend, model, context, authority, consent,
          workflow_line, workspace=None) -> dict:
    """What a session was opened under, recorded beside its token so a later
    run can tell whether it is still the same: who, where (its workspace and
    the additional directories its consent gives MARS), on what, and under
    which governance, Workflow, authority and consent."""
    return {"participant": participant, "backend": backend,
            "model": model or None, "context": context or None,
            "workspace": _path(workspace),
            "directories": sorted({_path(w) for w in
                                   (consent or {}).get("workspaces") or () if w}),
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
           exclude=None, contract: dict | None = None) -> tuple[dict | None, str]:
    """Whether this run asks MARS to continue the previous runtime session:
    `({"token"}, why)` or `(None, why not)`. `now` is this run's `basis`.

    `contract` is the runtime's capability contract (`MentisService.
    runtime_contract`): a runtime it declares to have NO native resume is not
    asked, and the record says the continuation is given the record-derived
    context instead -- decided by the declared state, never by the runtime's
    name. Not yet verified is still asked: MARS says whether it resumed."""
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
    if contract is not None:
        from mentis.core.runtime_contract import resume_words
        unsupported = resume_words(contract)
        if unsupported:
            return None, f"fresh session: {unsupported}"
    held, why = previous_session(cv, expectation, participant, exclude=exclude)
    if held is None:
        return None, why
    for key, words in (("participant", "a different participant"),
                       ("backend", "a different runtime"),
                       ("model", "a different model"),
                       ("workspace", "a different workspace"),
                       ("directories", "different additional directories"),
                       ("context", "the governing material changed"),
                       ("workflow", "the Workflow changed"),
                       ("authority", "what the work may do changed"),
                       ("consent", "the run consent changed")):
        if held.get(key) != now.get(key):
            return None, f"fresh session: {words}"
    return {"token": held["token"]}, "same work, participant, runtime and terms"


RESUME_NOTICE = (
    "# Continuing your session\n\n"
    "This is the same session as your previous run of this work, in the same "
    "workspace. The governing material and the reply format you were told "
    "then still stand unchanged. Everything else below is as it stands NOW "
    "and replaces what you were told before: what is new since that run, "
    "the objects, posts and artifacts you may read, other work's leases in "
    "this workspace, the consent, and what this run may do.")


def continuation_prompt(*, task: str, authority: dict | None,
                        authority_line: str | None, consent_text: str,
                        closing: str, split: str) -> str:
    """What a resumed session is sent. `task` is the opening task block (the
    resume text, with the owner's follow-ups and what returned), `closing`
    the closing block, which stays last. `consent_text` is everything about
    the run's situation the full payload tells it apart from the governance:
    referenced objects and posts, offered artifacts, the unconfirmed
    capability note, follow-up permission, consent and research, leases, an
    owed render check -- each current, since any of them may have changed."""
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


#: How much of the previous run's reply a fresh session is given in full.
RESTORED_REPLY_MAX = 6000

RESTORATION_HEADING = "# The work as it began, and where your previous run left it"


def restoration_block(cv, expectation, *, exclude=None) -> str:
    """WHAT A FRESH SESSION CONTINUING THE SAME WORK MUST BE TOLD, from the record
    (round 2, context restoration): the request this work carries, in the owner's
    own words and in full, and what the previous run of it replied, verbatim.

    A resumed runtime session still holds both; a fresh one -- a runtime without
    native resume (its capability contract says so), or one whose resume MARS
    could not load -- otherwise sees only the resume text and a one-line preview
    of the original post (measured, round-2 conformance: a fresh continuation did
    not know its own task or what it had said). It goes into the full payload
    only, never into the continuation a resumed session is sent. "" when there is
    nothing to restore."""
    from mentis.web.dispatch import request_words
    asked = (request_words(cv, expectation) or "").strip() if expectation else ""
    said, run = "", None
    try:
        starts = [a for a in cv.history(caused_by=expectation)
                  if a.get("act") == _STARTED and a.get("id") != exclude]
        for start in sorted(starts, key=lambda a: a.get("at") or 0, reverse=True):
            end = cv.run_end(start["id"])
            if end and end.get("act") == _RETURNED:
                run = start["id"]
                said = _turn_words(cv, end.get("turn")) or str(
                    (end.get("detail") or {}).get("final_text") or "")
                break
    except Exception:                                     # noqa: BLE001
        said = ""
    if not asked and not said:
        return ""
    lines = [RESTORATION_HEADING, "",
             "This is a fresh session: it does not hold your earlier run of this work. "
             "What follows is restored from the record so you can continue it."]
    if asked:
        lines += ["", "The request this work carries, as it was asked:", "", asked]
    if said:
        cut = said[:RESTORED_REPLY_MAX]
        lines += ["", f"What your previous run of it replied (run {run}"
                  + (", cut to the first " f"{RESTORED_REPLY_MAX} characters" if len(said) > len(cut) else "")
                  + "):", "", cut]
    return "\n".join(lines)


def _turn_words(cv, turn) -> str:
    if not turn:
        return ""
    try:
        got = cv._c.read([turn])
    except Exception:                                     # noqa: BLE001
        return ""
    if not got:
        return ""
    parts = (got[0].get("body") or {}).get("parts") or ()
    return "\n".join(p.get("text") or "" for p in parts if isinstance(p, dict)).strip()
