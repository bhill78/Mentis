"""Execution Mode: the technical environment a dispatched run executes in.

OWNER DECISION, 2026-11-11 (superseding the interim `host-development-unrestricted`
policy, its standing owner act and its selection from consent categories). Exactly two
user-facing execution controls, independent of each other:

- PERMISSION MODE is Mentis's existing run consent (`mentis.operational.consent`: ask,
  routine work, never wait, Approve All). Nothing here reads or changes it.
- EXECUTION MODE is this: `sandboxed`, `unrestricted-host`, `container`. MARS translates it
  into each runtime's own mechanism and declares, per runtime, which modes it supports
  (`contract.execution_modes`, MARS `consent::execution_modes`). Mentis passes that
  through and decides nothing from a runtime's name. `container` is never available now.

WHERE IT COMES FROM. The owner selects it on a dispatch (`dispatch[].execution_mode`), and
it is recorded on the request that dispatch creates (`detail.execution_mode = {mode, ack,
selected_by}`), so every run of THAT request -- continuations the owner records, re-addressing,
retries -- uses it (`of_request`). A request an agent records (delegate, discovered work)
never inherits it, and may state only `sandboxed` (`requested`). Absent, the runtime runs in
its default, exactly as before. Unrestricted host execution must carry the owner's
acknowledgement of the current notice (`NOTICE`); a mode the runtime does not support is
refused, never substituted.

WHAT IS RECORDED. The run's own start act (`execution-started`) carries what was decided
(`execution_mode: {requested, effective, source, mechanism, isolation, ack_act}`); MARS's
report on the run's end (`consent_applied.execution_mode`) says what was applied.

WHAT IT IS NOT. Unrestricted host execution is the host: the runtime runs as the owner's
user, with the machine's files, credentials, network and processes. It grants no Mentis
authority -- every Mentis operation still goes through `/api/worker` against the run's grant
-- and it is reported as host execution, never as isolation.
"""

from __future__ import annotations

SANDBOXED = "sandboxed"
UNRESTRICTED_HOST = "unrestricted-host"
CONTAINER = "container"
MODES = (SANDBOXED, UNRESTRICTED_HOST, CONTAINER)
#: Where the selection is held on a request, and the decision on a run's start act.
DETAIL = "execution_mode"
SUPPORTED, UNSUPPORTED, UNVERIFIED = "supported", "unsupported", "unverified"

#: What the owner acknowledges before choosing unrestricted host execution. The id changes
#: whenever the text's meaning does, so an acknowledgement of older words does not count.
NOTICE_ID = "unrestricted-host/v1"
NOTICE = {
    "id": NOTICE_ID,
    "text": ("Unrestricted host execution runs the agent directly on this computer as your "
             "user, without its runtime's sandbox and not in a container. The agent may "
             "technically access files outside its workspace, local credentials, network "
             "services and local processes. Mentis still checks every Mentis operation "
             "against the run's grant, and your Permission Mode is recorded, but a runtime "
             "that does not ask in this mode does not enforce it."),
}

#: What a run in unrestricted host execution is told (installation-neutral).
BOUNDARY = ("Your execution is unrestricted on the host (Execution Mode unrestricted-host, "
            "chosen by the owner for this request): your runtime runs as the owner's user on "
            "this machine, not in a sandbox or a container, so you can run shell commands, read "
            "and write source files, install dependencies, build, test and use Git. It does not "
            "extend your Mentis authority: your Mentis operations are still checked against "
            "your grant; do not delegate unrelated work, change governance or adopt records "
            "beyond what it allows. Deployments, a live Brain and production systems need the "
            "owner's approval through Mentis. What completes your task is its objective and "
            "Workflow: a commit does not imply a push, merge or deployment unless they ask for "
            "it. Reach Mentis only through your Mentis tools: never call its HTTP routes "
            "directly or edit Brain, Mentis or MARS data files.")


class Refused(ValueError):
    """An execution mode that cannot be given, said in words (answered 400)."""
    kind = "ExecutionModeRefused"

    def __init__(self, error: str, why: str | None = None):
        super().__init__(error)
        self.why = why

    def body(self) -> dict:
        return {"error": str(self), "kind": self.kind, "why": self.why}


class NotAcknowledged(Refused):
    kind = "ExecutionModeNotAcknowledged"


class Unsupported(Refused):
    kind = "ExecutionModeUnsupported"


class NotPermitted(Refused):
    kind = "ExecutionModeNotPermitted"


def isolation(mode: str | None) -> str:
    return {SANDBOXED: "sandbox", UNRESTRICTED_HOST: "host"}.get(mode or "", "none-reported")


def modes_of(contract: dict | None) -> dict | None:
    """The runtime's `execution_modes` as MARS declares them, or None when it does not."""
    m = (contract or {}).get("execution_modes") if isinstance(contract, dict) else None
    return m if isinstance(m, dict) and isinstance(m.get("modes"), dict) else None


def catalogue(contract: dict | None) -> dict:
    """What the runtime catalogue shows for one runtime (`GET /api/execution`): MARS's
    declaration, or -- from a MARS that says nothing -- every mode unverified and why."""
    m = modes_of(contract)
    if m is not None:
        return {"default": m.get("default"),
                "modes": {mode: {"state": (m["modes"].get(mode) or {}).get("state") or UNVERIFIED,
                                 "mechanism": (m["modes"].get(mode) or {}).get("mechanism"),
                                 "permission_enforcement":
                                     (m["modes"].get(mode) or {}).get("permission_enforcement")
                                     or "Not reported.",
                                 "why": (m["modes"].get(mode) or {}).get("why")}
                          for mode in MODES}}
    why = "MARS did not report this runtime's execution modes"
    return {"default": None,
            "modes": {mode: {"state": UNSUPPORTED if mode == CONTAINER else UNVERIFIED,
                             "mechanism": None, "permission_enforcement": "Not reported.",
                             "why": why} for mode in MODES}}


def fact(contract: dict | None, mode: str | None) -> dict:
    return ((modes_of(contract) or {}).get("modes") or {}).get(mode or "") or {}


def supported(contract: dict | None, mode: str, runtime: str | None = None) -> None:
    """Raises `Unsupported` unless the runtime's contract declares the mode supported."""
    f = fact(contract, mode)
    if f.get("state") == SUPPORTED:
        return
    why = (f.get("why") or f.get("state")) if f else (
        "MARS did not report this runtime's execution modes" if contract is not None
        else "the runtime's capability contract could not be read")
    raise Unsupported(f"runtime {runtime or '(unnamed)'} does not support execution mode "
                      f"{mode}: {why}", why=why)


def requested(raw_mode, raw_ack=None, *, by_owner: bool, selected_by: str | None) -> dict | None:
    """The selection a dispatch spec or a delegation states, validated, as recorded on the
    request it creates; None when it states none. Raises `Refused`."""
    if raw_mode is None:
        return None
    if raw_mode not in MODES:
        raise Unsupported(f"execution_mode is one of {', '.join(MODES)}, not {raw_mode!r}",
                          why="unknown execution mode")
    if not by_owner and raw_mode != SANDBOXED:
        raise NotPermitted(f"only the owner may choose execution mode {raw_mode}; a request an "
                           "agent records may state only sandboxed",
                           why="an agent cannot widen its own execution")
    if raw_mode == UNRESTRICTED_HOST and raw_ack != NOTICE_ID:
        raise NotAcknowledged("unrestricted host execution needs the owner's acknowledgement "
                              f"of the current notice ({NOTICE_ID})",
                              why=f"execution_mode_ack must be {NOTICE_ID!r}")
    if raw_mode == CONTAINER:
        raise Unsupported("execution mode container is not available",
                          why="MARS cannot assign a container yet")
    return {"mode": raw_mode, "ack": raw_ack if raw_mode == UNRESTRICTED_HOST else None,
            "selected_by": selected_by}


def of_request(cv, expectation) -> dict | None:
    """The execution mode selected for this request: its own, or -- for a request the OWNER
    recorded that continues another -- the one it continues. A request an agent recorded
    never inherits, and anything wider than `sandboxed` on it is never read. None: the
    runtime's default."""
    from mentis.conversation.owner import _owner
    owner = _owner(cv)
    cur, seen = expectation, set()
    while cur and cur not in seen:
        seen.add(cur)
        a = cv._act(cur)
        if a is None or a.get("act") != "expectation-recorded":
            return None
        by_owner = bool(owner) and a.get("actor") == owner
        said = (a.get("detail") or {}).get(DETAIL)
        if isinstance(said, dict) and said.get("mode") in MODES:
            if said["mode"] != SANDBOXED and not by_owner:
                return None
            return {**said, "request": a["id"], "at": a.get("at")}
        if not by_owner:
            return None
        cur = a.get("caused_by")
    return None


def resolve(cv, expectation, *, runtime, contract) -> dict:
    """What a run of this request on this runtime executes in, as its start act records it.
    Raises `Unsupported` for a selected mode the runtime does not support."""
    sel = of_request(cv, expectation) if expectation else None
    if sel:
        supported(contract, sel["mode"], runtime)
        mode, source = sel["mode"], "selected"
    else:
        mode, source = (modes_of(contract) or {}).get("default"), "runtime-default"
    f = fact(contract, mode)
    return {"requested": sel["mode"] if sel else None, "effective": mode, "source": source,
            "mechanism": f.get("mechanism"), "isolation": isolation(mode),
            "permission_enforcement": f.get("permission_enforcement"),
            "ack_act": sel["request"] if sel and sel.get("ack") else None,
            "selected_by": sel.get("selected_by") if sel else None}


def of_run(cv, run) -> dict | None:
    """What the run's start act recorded, or None (a run from before Execution Mode)."""
    start = (cv._act(run) if cv is not None and run else None) or {}
    got = (start.get("detail") or {}).get(DETAIL)
    return got if isinstance(got, dict) else None


def options(cv, run) -> dict:
    """What MARS is sent for this run: the mode the owner selected, or nothing (default)."""
    got = of_run(cv, run) or {}
    return {"execution_mode": got["requested"]} if got.get("requested") in MODES else {}


def asks(contract: dict | None, mode: str | None) -> bool:
    """Whether the runtime still asks the client before operations in this mode, from its
    contract (`permission_enforcement.kind`), never its name: under unrestricted host
    execution only a runtime that forwards its requests does."""
    if mode != UNRESTRICTED_HOST:
        return True
    c = ((contract or {}).get("capabilities") or {}).get("permission_enforcement")
    kind = c.get("kind") if isinstance(c, dict) else None
    return isinstance(kind, str) and kind.startswith("forwarded")


def report(cv, run, applied: dict | None) -> dict:
    """`GET /api/runs/<run>/consent`'s `execution`: what was decided and what MARS applied."""
    got = of_run(cv, run) or {}
    mars = (applied or {}).get("execution_mode") if isinstance(applied, dict) else None
    mars = mars if isinstance(mars, dict) else {}
    mode = got.get("effective") or mars.get("name")
    ack = None
    if got.get("ack_act"):
        a = cv._act(got["ack_act"]) or {}
        ack = {"act": got["ack_act"], "at": a.get("at")}
    return {"mode": mode,
            "source": got.get("source") or ("runtime-default" if mode else None),
            "mechanism": mars.get("mechanism") or got.get("mechanism"),
            "isolation": mars.get("isolation") or got.get("isolation") or isolation(mode),
            "permission_enforcement": (mars.get("permission_enforcement")
                                       or got.get("permission_enforcement")),
            "acknowledged": ack,
            "applied_by_mars": bool(mars) and mars.get("name") == mode}
