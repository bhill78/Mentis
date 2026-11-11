"""Explainable refusals: what was refused, at which boundary, why, and what to do next.

WS-I of the modernization contract (`docs/modernization/CONTRACT.md`). A refusal
used to be one sentence. An agent told "this execution carries no request" could
not tell whether it had used the wrong tool, lacked authority, or needed to
record something first -- and the 2026-11-10 incident (an owner-authorized CLI
cleanup session that found a real defect and could not record it) came from
exactly that. A refusal now carries, besides its words:

    op        the operation refused
    boundary  which kind of boundary refused it (`BOUNDARIES`)
    why       the reason, in one sentence
    recovery  supported next calls, each a short string naming a tool and how
    who       who can lift the boundary, where anybody can

The words (`str(exc)`) stay the whole answer for a reader that knows nothing of
the fields; the fields are there for a reader -- the worker, the bridge, a UI --
that renders them. `render` is the one way they are written out.

This module imports nothing from Mentis, so the worker, the web door and the
bridge can all depend on it.
"""

from __future__ import annotations

from typing import Any, Iterable

#: Which boundary refused, in the contract's words.
#:   lineage       the call needs work it is carried under (a request, `under`)
#:   scope         the grant's scope does not admit the operation
#:   coordination  organising work beyond what is carried needs `coordinate`
#:   governance    standing, adoption or establishment is the owner's
#:   place         where it would act (a Conversation, a Turn) is out of reach
#:   ownership     the thing named belongs to somebody else
#:   validation    the arguments do not say what the operation needs
#:   resource      a shared resource is held by somebody else
BOUNDARIES = ("lineage", "scope", "coordination", "governance", "place",
              "ownership", "validation", "resource")

FIELDS = ("op", "boundary", "why", "recovery", "who")


class StructuredRefusal(PermissionError):
    """A `PermissionError` that can say, as data, why and what next.

    Constructed exactly as before -- `NotPermitted("words")` -- by every
    refusal that has not been converted; those carry no fields and render as
    they always did. A converted one names its fields:

        raise NotPermitted(op="record_discovered_work", boundary="lineage",
                           why="...", recovery=["contribute(...)"], who="...")

    and, given no words, its words are `render`'s.
    """

    def __init__(self, message: str | None = None, *, op: str | None = None,
                 boundary: str | None = None, why: str | None = None,
                 recovery: Iterable[str] | None = None,
                 who: str | None = None) -> None:
        if boundary is not None and boundary not in BOUNDARIES:
            raise ValueError(f"unknown refusal boundary {boundary!r}")
        self.op = op
        self.boundary = boundary
        self.why = why
        self.recovery = [str(r) for r in (recovery or ())]
        self.who = who
        if message is None:
            message = words(why=why, recovery=self.recovery, who=who) or ""
        super().__init__(message)

    @property
    def structured(self) -> bool:
        return self.boundary is not None

    def as_dict(self) -> dict[str, Any]:
        """The fields, for a wire. Empty for a refusal that carries none."""
        if not self.structured:
            return {}
        return {"op": self.op, "boundary": self.boundary, "why": self.why,
                "recovery": list(self.recovery), "who": self.who}


def words(*, why: str | None, recovery: Iterable[str] = (),
          who: str | None = None) -> str:
    """The refusal said as prose: the reason, then what to do, then who can lift it."""
    out = [why.rstrip(".") + "." if why else ""]
    recovery = list(recovery or ())
    if recovery:
        out.append("What you can do instead: " + "; ".join(recovery) + ".")
    if who:
        out.append("Who can lift this: " + who.rstrip(".") + ".")
    return " ".join(x for x in out if x)


def render(exc: BaseException) -> str:
    """How the worker and the bridge show a refusal to an agent.

    The words, and -- for a structured refusal whose words do not already say
    them -- each field on its own line, so an agent reading the tool error sees
    the boundary and the supported next calls without parsing anything."""
    text = f"{type(exc).__name__}: {exc}"
    fields = exc.as_dict() if isinstance(exc, StructuredRefusal) else {}
    if not fields:
        return text
    lines = [text, "", f"refused: {fields['op'] or '(this call)'}",
             f"boundary: {fields['boundary']}"]
    if fields.get("why"):
        lines.append(f"why: {fields['why']}")
    for r in fields.get("recovery") or ():
        lines.append(f"recovery: {r}")
    if fields.get("who"):
        lines.append(f"who can lift it: {fields['who']}")
    return "\n".join(lines)


def from_wire(payload: Any) -> dict[str, Any]:
    """The keyword arguments a refusal's fields arrived as, or {} if none did.

    Tolerant: an older server sends no `refusal`, and a malformed one is
    dropped rather than turning a refusal into a malfunction."""
    if not isinstance(payload, dict):
        return {}
    got = payload.get("refusal")
    if not isinstance(got, dict) or got.get("boundary") not in BOUNDARIES:
        return {}
    recovery = got.get("recovery")
    return {"op": got.get("op") if isinstance(got.get("op"), str) else None,
            "boundary": got["boundary"],
            "why": got.get("why") if isinstance(got.get("why"), str) else None,
            "recovery": [str(r) for r in recovery]
            if isinstance(recovery, list) else [],
            "who": got.get("who") if isinstance(got.get("who"), str) else None}


def body(exc: PermissionError) -> dict[str, Any]:
    """The 403 body the HTTP door answers a refusal with."""
    out: dict[str, Any] = {"error": str(exc), "kind": "PermissionError"}
    if isinstance(exc, StructuredRefusal) and exc.structured:
        out["refusal"] = exc.as_dict()
    return out
