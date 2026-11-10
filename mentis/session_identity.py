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


def resolve(cv, *, runtime: str, host: str | None,
            participant: str | None) -> str:
    """The Participant this session is bound to. Raises `ValueError` saying why
    when it may not be bound to the one asked for.

    `participant` is an `ent-` reference or an alias. Never the owner: a session
    recorded as the owner would make every act it writes read as the owner's
    own. An alias nobody holds is created, described as a CLI agent; one that
    is reserved, former or not of the allowed characters is refused by
    `resolve_participant` with what to do instead.
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
        try:
            pid = cv.resolve_participant(alias, about=describe(runtime, host),
                                         written_by="mentis/manual-session")
        except Refused as refused:
            raise ValueError(refused.refusal.get("error") or str(refused)) from None
    if pid == _owner(cv):
        raise ValueError(
            "a hand-started session is not bound to the owner's own "
            "Participant: what it writes would read as the owner's own act. "
            "Name another participant, or none for this runtime and host's own")
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
