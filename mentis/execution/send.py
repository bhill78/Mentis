"""THE ACTUAL SEND BOUNDARY: what is checked as the bytes cross, and what
became of them.

An `Execution` sends a run's prompt at one place and one moment. Two things
belong to that moment and nowhere else.

ELIGIBILITY, SERIALIZED (`RunSpec.send_gate`). A caller that decided a run may
go may have decided it some time ago -- before the connection, the session and
the tooling. Whatever it checked then can have changed since. The send gate is
entered at the send itself: a caller-supplied context manager, in which the
caller rechecks what it must and records its reservation, in its own record
transaction. Entering it is the last thing before the bytes are handed over,
and nothing but the hand-over lies between. So of an edit and a send, one wins:
an edit that commits first is seen by the gate and nothing is sent; a send
whose reservation commits first is the one that happened, and a later edit
finds the reservation and blocks the NEXT send -- it cannot unsend this one. A
gate that cannot answer, or whose reservation cannot commit, refuses: nothing
is sent.

WHAT BECAME OF THE BYTES (`RunSpec.on_delivery`). Preparing a prompt is not
sending it, sending is not delivery, and a send that failed is not delivery
either. The states are told apart and reported separately:

- `prepared`: composed, and nothing was sent.
- `refused`: the send gate refused at the boundary; nothing was sent.
- `sent`: the bytes were handed over. NOT delivery, and never reported as it.
- `supplied`: the runtime acknowledged THESE bytes -- the send returned with
  the turn's stop reason, or the session reported an update after the send.
  This is the only state that says delivered.
- `failed`: the send itself failed, with no acknowledgement of these bytes.
- `unconfirmed`: the bytes were handed over and nothing says whether they
  arrived (the connection or the loop went while they were in flight).

An acknowledgement is tied to the send it answers (`send`, the ordinal, and the
reservation the gate returned), so a later acknowledgement is never read back
as proof that an earlier send was delivered, nor the other way round.

Nothing here is specific to any kind of work: a caller that passes neither a
gate nor a delivery callback is sent exactly as it always was.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

log = logging.getLogger(__name__)

#: Composed; nothing was sent.
PREPARED = "prepared"
#: The send gate refused at the boundary; nothing was sent.
REFUSED = "refused"
#: The bytes were handed over. Not delivery.
SENT = "sent"
#: The runtime acknowledged these bytes. Delivery.
SUPPLIED = "supplied"
#: The send failed, with nothing acknowledged.
FAILED = "failed"
#: Handed over; whether they arrived is not known.
UNCONFIRMED = "unconfirmed"

#: The states that end a send's story. Exactly one is reported per send.
TERMINAL = (PREPARED, REFUSED, SUPPLIED, FAILED, UNCONFIRMED)

#: What an acknowledgement was read from.
BY_RESULT = "prompt_result"
BY_UPDATE = "session_update"


def _tell(on_delivery: Callable[[dict[str, Any]], None] | None,
          report: dict[str, Any]) -> None:
    """Report, never failing the run for it: an audit that raises is said in
    the log and the run goes on as it would have."""
    if on_delivery is None:
        return
    try:
        on_delivery(dict(report))
    except Exception:                                     # noqa: BLE001
        log.warning("delivery report %s failed for run %s",
                    report.get("state"), report.get("run"), exc_info=True)


class SendBoundary:
    """One send of one run: its gate, and what became of its bytes.

    Held by the `Execution` doing the sending. `reserve` runs the caller's
    gate (off any event loop: it may take a record transaction); `handed_over`
    marks the moment the bytes crossed; `acknowledge` records the first
    evidence that they arrived; `say` makes the one terminal report.
    """

    def __init__(self, spec: Any, *, ordinal: int = 1) -> None:
        self.spec = spec
        self.ordinal = int(ordinal)
        #: what the gate returned when it allowed the send, or None
        self.reservation: dict[str, Any] | None = None
        self.sent_at: float | None = None
        #: what the acknowledgement of these bytes was read from, or None
        self.acknowledged: str | None = None
        self.acknowledged_at: float | None = None
        #: the terminal state already reported, so none is reported twice
        self.said: str | None = None

    # ---- the gate ----------------------------------------------------------

    def reserve(self) -> str | None:
        """Enter the caller's send gate and let it go again, immediately
        before the bytes are handed over. A refusal reason, or None to send.

        FAILS CLOSED: a gate that raises, and a reservation that cannot
        commit, both refuse -- an eligibility that cannot be confirmed is not
        a send.
        """
        gate = getattr(self.spec, "send_gate", None)
        if gate is None:
            return None
        try:
            with gate() as answer:
                if isinstance(answer, str) and answer.strip():
                    return answer
                if isinstance(answer, dict):
                    self.reservation = dict(answer)
                return None
        except Exception as exc:                          # noqa: BLE001
            log.warning("send gate failed for run %s; not sent",
                        getattr(self.spec, "run_id", None), exc_info=True)
            return ("whether it may be sent could not be confirmed "
                    f"({type(exc).__name__})")

    # ---- what became of the bytes -----------------------------------------

    def handed_over(self, at: float | None = None) -> None:
        """The bytes have been handed to the runtime. Reported as `sent`,
        which is not delivery: only an acknowledgement is. Said once."""
        if self.sent_at is not None:
            return
        self.sent_at = float(at if at is not None else time.time())
        _tell(getattr(self.spec, "on_delivery", None), self._report(SENT))

    def acknowledge(self, basis: str, at: float | None = None) -> None:
        """The first evidence that THESE bytes arrived. Evidence before the
        hand-over is not evidence of it, and the first basis stands."""
        if self.sent_at is None or self.acknowledged is not None:
            return
        when = float(at if at is not None else time.time())
        if when < self.sent_at:
            return
        self.acknowledged, self.acknowledged_at = basis, when

    def say(self, state: str, *, why: str | None = None,
            basis: str | None = None) -> None:
        """Make this send's one terminal report. A second is ignored: the
        first observation of what became of the bytes is the answer."""
        if state not in TERMINAL:
            raise ValueError(f"{state!r} does not end a send")
        if self.said is not None:
            return
        if state == SUPPLIED and not (basis or self.acknowledged):
            # NEVER SUPPLIED WITHOUT AN ACKNOWLEDGEMENT OF THESE BYTES: a
            # caller that asks for one anyway gets the honest state instead.
            state, why = UNCONFIRMED, why or "nothing acknowledged the send"
        self.said = state
        _tell(getattr(self.spec, "on_delivery", None),
              self._report(state, why=why, basis=basis or self.acknowledged))

    def after_failure(self, exc: BaseException, *, refused: bool = False) -> None:
        """What a send that raised became.

        Nothing handed over: nothing to say here (the coordination reports
        `prepared`). Acknowledged: those bytes arrived, however the run ended
        afterwards -- a send is not unsent by what follows it. `refused` is
        for the caller to decide and means the other end ANSWERED and did not
        take them, which is a `failed` send. Everything else -- a connection
        that went, a loop that closed, an error nobody can place -- leaves it
        unknown whether the bytes arrived, and unknown is `unconfirmed`, not
        delivered and not failed.
        """
        if self.sent_at is None or self.said is not None:
            return
        if self.acknowledged:
            self.say(SUPPLIED)
        elif refused:
            self.say(FAILED, why=f"{type(exc).__name__}: {exc}")
        else:
            self.say(UNCONFIRMED, why=f"{type(exc).__name__}: {exc}")

    def _report(self, state: str, *, why: str | None = None,
                basis: str | None = None) -> dict[str, Any]:
        return {"state": state,
                "run": getattr(self.spec, "run_id", None),
                "backend": getattr(self.spec, "backend", None),
                "send": self.ordinal,
                "reservation": dict(self.reservation) if self.reservation else None,
                "at": time.time(),
                "sent_at": self.sent_at,
                "acknowledged": basis,
                "acknowledged_at": self.acknowledged_at if basis else None,
                "why": why}


class DeliveryWatch:
    """What the caller's `on_delivery` was actually told.

    The send boundary lives inside the `Execution`, and a run can end before
    it is ever reached -- a stop held on the run, a boundary that never opened
    a session. The coordination that asked for the run wraps its callback in
    this, and afterwards tells the caller the honest state itself where the
    boundary told it nothing. Exactly one terminal report either way.
    """

    def __init__(self, tell: Callable[[dict[str, Any]], None]) -> None:
        self._tell = tell
        self._terminal: str | None = None
        self.reports: list[dict[str, Any]] = []

    def __call__(self, report: dict[str, Any]) -> None:
        state = report.get("state")
        if state in TERMINAL:
            if self._terminal is not None:
                return
            self._terminal = str(state)
        self.reports.append(dict(report))
        self._tell(report)

    def terminal(self) -> str | None:
        return self._terminal

    def otherwise(self, state: str, *, run: str | None = None,
                  backend: str | None = None, why: str | None = None,
                  sent_at: float | None = None) -> None:
        """Report `state` only if nothing terminal was reported for this run."""
        if self._terminal is not None:
            return
        if state not in TERMINAL:
            raise ValueError(f"{state!r} does not end a send")
        self({"state": state, "run": run, "backend": backend, "send": 1,
              "reservation": None, "at": time.time(), "sent_at": sent_at,
              "acknowledged": None, "acknowledged_at": None, "why": why})
