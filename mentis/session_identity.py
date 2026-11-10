"""Who a hand-started session is, where it ran, and who authorized what it writes.

WS-I of `docs/modernization/CONTRACT.md`.

ONE PARTICIPANT PER RUNTIME AND HOST, NOT ONE FOR EVERY SESSION. Every session
used to be recorded as the one shared @ManualSession, so nothing in the record
could tell a Claude Code session on one machine from a Codex session on
another. A session is now bound to a Participant of its own: the one the
bridge names (`--participant`), or by default the one for its runtime and host,
created on first use as an ordinary Participant described as an independently
launched CLI agent. Which session did something is still the act's own
`execution`, and which runtime its `runtime`; the host is `detail.host`.

THE ALIAS. The contract's words are `<Runtime> CLI · <HOST>`, but a Participant
alias is ASCII letters, digits, `-` and `_` (owner decision opr-938e0fa58007,
`participant_names.alias_problem`), so the default alias is
`@<Runtime>-CLI-<HOST>`. The readable form is the Participant's `about`.

WHO AUTHORIZED IT IS NOT WHO DID IT. `authorized_by` records where the
authority for a write came from -- the owner in the chat that started the
session, a recorded request, or nothing -- apart from the actor that executed
it. It is evidence, never authority: Mentis grants nothing because a session
says the owner asked.
"""

from __future__ import annotations

import re
import socket

#: How an independently launched CLI agent is described, so it is recognisable.
ABOUT = "an independently launched CLI agent"

#: Where the authority for a session's write came from.
AUTHORIZATION_SOURCES = ("owner-in-chat", "request", "none")

_HOST_OK = re.compile(r"[^A-Za-z0-9_-]+")


def host_label(host: str | None = None) -> str:
    """This machine's name, or `host`, as an alias may carry it."""
    raw = str(host or socket.gethostname() or "host").strip()
    label = _HOST_OK.sub("-", raw).strip("-_") or "host"
    return label[:40]


def runtime_label(runtime: str) -> str:
    """`claude` -> `Claude`, `codex-cli` -> `Codex-cli`: the runtime as named."""
    text = _HOST_OK.sub("-", str(runtime or "").strip()).strip("-_")
    return (text[:1].upper() + text[1:]) if text else "Session"


def default_alias(runtime: str, host: str | None = None) -> str:
    """The alias of the default Participant for this runtime on this host."""
    return f"@{runtime_label(runtime)}-CLI-{host_label(host)}"


def describe(runtime: str, host: str | None) -> str:
    return (f"{ABOUT}: {runtime_label(runtime)} CLI · {host_label(host)}. "
            f"Created on first use; each session is its own execution.")


#: Who wrote a session Participant's entry: the session route, and nothing else.
WRITTEN_BY = "mentis/manual-session"


def _refused(why: str, **kw):
    from mentis.worker import NotPermitted
    return NotPermitted(
        op="session", boundary="ownership", why=why,
        recovery=["start the session without --participant, to be this "
                  "runtime and host's own CLI participant",
                  "name a new participant that nobody else is or has been"],
        who="the owner", **kw)


def bindable_problem(cv, pid: str) -> str | None:
    """Why a session may not be bound to this existing Participant, or None.

    REVIEW FINDING (HIGH, impersonation): binding to any existing non-owner
    Participant let a session be @Caretaker -- write as it, withdraw its
    challenges, release its leases. A session may only be a Participant that
    was CREATED AS A SESSION PARTICIPANT (this route wrote its entry, described
    as an independently launched CLI agent) and that nothing but hand-started
    sessions ever acted as: every act of it that names an execution names one
    of its own sessions. A dispatched run as it (`execution-started`), or any
    act from another execution, makes it somebody else's."""
    got = cv.corpus.read([pid])
    entry = got[0] if got else None
    body = (entry or {}).get("body") or {}
    if (not entry or not str(body.get("about") or "").startswith(ABOUT)
            or entry.get("written_by") != WRITTEN_BY):
        return (f"{cv.alias(pid) or pid} is not a participant created for "
                f"independently launched CLI sessions; a session may not act "
                f"as another participant")
    acts = cv.corpus.operational(actor=pid)
    sessions = {a.get("execution") for a in acts
                if a.get("act") in ("manual-session-started",
                                    "manual-session-renewed")}
    for a in acts:
        if a.get("act") == "execution-started" or (
                a.get("execution") and a["execution"] not in sessions):
            return (f"{cv.alias(pid) or pid} has acted outside hand-started "
                    f"sessions (a dispatched run or another execution), so a "
                    f"session may not act as it")
    return None


def resolve(cv, *, runtime: str, host: str | None,
            participant: str | None) -> str:
    """The Participant this session is bound to. Raises `NotPermitted`
    (boundary `ownership`) when it may not be bound to the one asked for, and
    `ValueError` for a name no Participant may take.

    Only (a) a Participant created as a CLI session participant that nothing
    else has acted as (`bindable_problem`), or (b) a new alias, created here as
    one. Never the owner, never an existing agent, Persona or runtime's
    Participant. `host` is the client's CLAIM, used for the default alias and
    recorded as `host_claimed`; it proves nothing.
    """
    from mentis.conversation.owner import _owner
    from mentis.conversation.versions import Refused
    asked = str(participant or "").strip()
    if asked.startswith("ent-"):
        if not cv._is_kind(asked, "participant"):
            raise ValueError(f"{asked!r} is not a Participant in this record")
        pid = asked
    else:
        alias = ("@" + asked.lstrip("@")) if asked else default_alias(runtime, host)
        existing = cv.find_participant(alias) or next(
            (p["id"] for p in cv.all_participants()
             if str(p["body"].get("alias") or "").lower() == alias.lower()),
            None)
        if existing:
            pid = existing
        else:
            try:
                pid = cv.resolve_participant(alias, about=describe(runtime, host),
                                             written_by=WRITTEN_BY)
            except Refused as refused:
                raise ValueError(refused.refusal.get("error")
                                 or str(refused)) from None
            return pid
    if pid == _owner(cv):
        raise _refused(
            "a hand-started session is not bound to the owner's own "
            "Participant: what it writes would read as the owner's own act")
    problem = bindable_problem(cv, pid)
    if problem:
        raise _refused(problem)
    try:
        cv.refuse_reserved(pid)
    except Refused as refused:
        raise ValueError(refused.refusal.get("error") or str(refused)) from None
    return pid


def is_session_participant(cv, pid: str | None) -> bool:
    """Whether `pid` has been a hand-started session: the shared participant
    from before WS-I, or any Participant the record shows starting a session."""
    if not pid:
        return False
    from mentis.worker import SESSION_PARTICIPANT
    if cv.alias(pid) == SESSION_PARTICIPANT:
        return True
    return any(True for _ in cv.corpus.operational(
        actor=pid, act="manual-session-started"))


def authorization(value, *, under: str | None = None) -> dict | None:
    """`authorized_by` as it is stored, checked; None when none was said.

    Absent but carried `under` a request, it is that request. A malformed
    value raises `ValueError` naming what is wrong.
    """
    if value is None or value == {}:
        if under:
            return {"source": "request", "note": "", "request": under}
        return None
    if isinstance(value, str):
        value = {"source": "owner-in-chat", "note": value}
    if not isinstance(value, dict):
        raise ValueError("authorized_by is {source, note, request}")
    source = str(value.get("source") or "").strip()
    if source not in AUTHORIZATION_SOURCES:
        raise ValueError(f"authorized_by.source is one of "
                         f"{', '.join(AUTHORIZATION_SOURCES)}")
    note = value.get("note")
    if note is not None and not isinstance(note, str):
        raise ValueError("authorized_by.note is text")
    request = value.get("request")
    if request is not None and not isinstance(request, str):
        raise ValueError("authorized_by.request is a request's reference")
    request = (request or "").strip() or (under if source == "request" else None)
    if source == "request" and not request:
        raise ValueError("authorized_by.source 'request' names the request in "
                         "authorized_by.request, or is carried `under` it")
    return {"source": source, "note": (note or "").strip()[:2000],
            "request": request or None}
