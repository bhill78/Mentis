"""The runtime capability contract, as Mentis reads it (round 2, O9 / program §12).

MARS declares, per backend, what the runtime can do for work run on it, each capability in
exactly one of four states (MARS `docs/API.md` "Capability contract", `runtime_contract.rs`):

  * ``supported`` -- shown to work through MARS, with its evidence;
  * ``unsupported`` -- known absent, with the ``fallback`` Mentis uses instead, if any;
  * ``temporarily-unavailable`` -- the runtime has it but cannot take work now;
  * ``not-yet-verified`` -- nothing has shown it either way. Never read as supported.

Mentis CONSUMES the contract instead of branching on runtime names: what a runtime is, is
MARS's to say; what Mentis does about it (ask for a native resume or send the record-derived
context, select it or not) is decided here from the states. Quota is Mentis's to overlay,
because Mentis holds the record of quota failures (`quota.quota_holds`) and reads MARS's
capacity: a runtime whose capacity view is exhausted, or that is held, is
``temporarily-unavailable`` as a whole and in every capability it supports.

A MARS that sends no contract (older than round 2) is read as every capability
``not-yet-verified``, so nothing is claimed that MARS did not say.

Nothing here permits anything, launches anything or writes to the record.
"""

from __future__ import annotations

SUPPORTED = "supported"
UNSUPPORTED = "unsupported"
UNAVAILABLE = "temporarily-unavailable"
UNVERIFIED = "not-yet-verified"

#: The four states, in the order a reader is told them.
STATES = (SUPPORTED, UNSUPPORTED, UNAVAILABLE, UNVERIFIED)

#: Every capability the contract covers, in MARS's order.
CAPABILITIES = (
    "native_resume",
    "context_restoration",
    "permission_enforcement",
    "mcp_tools",
    "cancellation",
    "execution_events",
    "completion_reporting",
    "model_discovery",
    "capacity_reporting",
    "delegation_coordination",
)

_NO_CONTRACT = ("MARS reported no capability contract for this runtime (a MARS older than "
                "the round-2 contract), so nothing about it is established")


def of_backend(backend: dict | None) -> dict:
    """The contract MARS gave for one `_mars/backends` entry, normalized: every capability
    present, each with a known state (anything else MARS might say is read as
    `not-yet-verified`, never as support)."""
    raw = (backend or {}).get("contract")
    raw = raw if isinstance(raw, dict) else {}
    caps_in = raw.get("capabilities") if isinstance(raw.get("capabilities"), dict) else {}
    caps = {}
    for name in CAPABILITIES:
        c = caps_in.get(name)
        c = dict(c) if isinstance(c, dict) else {}
        if c.get("state") not in STATES:
            c = {"state": UNVERIFIED,
                 "evidence": (_NO_CONTRACT if not raw else
                              f"MARS gave {name} no state Mentis knows"),
                 "source": "none"}
        caps[name] = c
    # Capabilities MARS added that Mentis does not know yet are kept, as they are.
    for name, c in caps_in.items():
        if name not in caps and isinstance(c, dict):
            caps[name] = dict(c)
    availability = raw.get("availability")
    if not isinstance(availability, dict) or availability.get("state") not in STATES:
        available = bool((backend or {}).get("available"))
        availability = ({"state": SUPPORTED} if available else
                        {"state": UNAVAILABLE,
                         "why": (backend or {}).get("reason") or "MARS lists it unavailable"})
    out = {"version": raw.get("version"), "from_mars": bool(raw),
           "availability": dict(availability), "capabilities": caps}
    # EXECUTION MODES (owner, 2026-11-11; `mentis.execution.mode`): MARS's declaration, kept
    # as MARS gave it; quota and availability never change it.
    if isinstance(raw.get("execution_modes"), dict):
        out["execution_modes"] = raw["execution_modes"]
    return out


def with_quota(contract: dict, *, exhausted: str | None = None,
               held: str | None = None) -> dict:
    """The contract with Mentis's quota knowledge laid over it: `exhausted` (the capacity
    view says no window is left, in words) or `held` (the record's quota hold, in words).
    Either makes the runtime, and every capability it supports, temporarily unavailable,
    saying why. Unsupported and unverified capabilities stay as they are."""
    why = held or exhausted
    if not why:
        return contract
    out = {**contract, "availability": {"state": UNAVAILABLE, "why": why, "source": "quota"},
           "capabilities": {}}
    for name, c in contract["capabilities"].items():
        c = dict(c)
        if c.get("state") == SUPPORTED:
            c.update(state=UNAVAILABLE, why=why)
        out["capabilities"][name] = c
    return out


def state(contract: dict | None, name: str) -> str:
    """One capability's state; `not-yet-verified` when the contract does not say."""
    c = ((contract or {}).get("capabilities") or {}).get(name)
    s = c.get("state") if isinstance(c, dict) else None
    return s if s in STATES else UNVERIFIED


def summary(contract: dict) -> dict:
    """`{state: [capability, ...]}`, empty states left out, and `availability`
    (the runtime as a whole, with why when it is not available): what a reader
    is shown. Availability is kept (review L1): a held or exhausted runtime is
    said to be one, not only through its capabilities."""
    out: dict[str, list[str]] = {}
    for name, c in contract["capabilities"].items():
        out.setdefault(c.get("state") or UNVERIFIED, []).append(name)
    shown = {s: sorted(out[s]) for s in STATES if s in out}
    avail = contract.get("availability") or {}
    if avail.get("state"):
        shown["availability"] = {k: avail[k] for k in ("state", "why", "source") if avail.get(k)}
    return shown


def resume_words(contract: dict | None) -> str | None:
    """Why a continuation must not ask for a native resume, or None when it may ask.

    Only `unsupported` stops the asking: a runtime that is merely not yet verified is still
    asked, because MARS answers whether it resumed and the full composition is sent whenever
    it did not (continuity is never lost by asking)."""
    if state(contract, "native_resume") != UNSUPPORTED:
        return None
    c = contract["capabilities"]["native_resume"]
    return ("the runtime has no native resume (MARS capability contract"
            + (f": {c['evidence']}" if c.get("evidence") else "")
            + "); the continuation is given the record-derived context")
