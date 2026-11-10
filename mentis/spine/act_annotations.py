"""What every act an actor writes during one call also says about it.

WS-I (`docs/modernization/CONTRACT.md`): a hand-started session's acts record
which host it ran on and who authorized the write (`authorized_by`), apart from
who executed it (the actor). Those facts belong on EVERY act the call writes --
the Turn's act, the expectation, a ladder write, the operation key -- and the
operations writing them are many and deep. So the door says them once, for the
duration of the call, and `record_operational` adds them to the `detail` of
each act written by that actor in that execution.

Nothing here decides anything. An annotation never overrides a key the writer
put in `detail` itself, and an act by anybody else in the same call (a
Participant summoned, the owner's own act) is left as it is.

Imports nothing: the spine sits beneath everything that sets it.
"""

from __future__ import annotations

import contextlib
import contextvars
from typing import Any, Iterator

_CURRENT: contextvars.ContextVar[tuple[str, str | None, dict] | None] = \
    contextvars.ContextVar("mentis_act_annotations", default=None)


@contextlib.contextmanager
def annotating(actor: str | None, execution: str | None,
               detail: dict[str, Any] | None) -> Iterator[None]:
    """Within this block, acts by `actor` in `execution` also carry `detail`."""
    if not actor or not detail:
        yield
        return
    token = _CURRENT.set((actor, execution, dict(detail)))
    try:
        yield
    finally:
        _CURRENT.reset(token)


def annotate(actor: str, execution: str | None,
             detail: dict[str, Any] | None) -> dict[str, Any] | None:
    """`detail` with the current annotation added, where it applies."""
    current = _CURRENT.get()
    if current is None:
        return detail
    who, where, extra = current
    # An act written without an execution (an expectation, a link's act) is
    # still this call's when its actor is; one naming ANOTHER execution is not.
    if actor != who or (where is not None and execution is not None
                        and execution != where):
        return detail
    merged = dict(extra)
    merged.update(detail or {})
    return merged
