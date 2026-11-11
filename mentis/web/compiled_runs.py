"""Live runs holding compiled permission rules, and what happens when the
authority those rules were compiled from narrows while they run
(docs/modernization/CONTRACT.md WS-A; `mentis.permission_rules`).

A runtime is handed its rules when its session opens and cannot be handed
new ones mid-session. AUTHORITY CHANGES REMAIN EFFECTIVE because:

  1. A run is TRACKED from before its consent is first read
     (`permissions.mars_consent`) until it ends. A consent set while its
     rules are being computed marks it dirty, and they are computed again.
  2. Immediately before the session opens (`permissions.before_open`,
     called by `MentisService.agents_perform` just before `perform`) the
     rules are computed once more from the consent in force and replace what
     was going to be sent. A narrowing up to that moment needs no halt.
  3. After that, whenever the owner sets consent (`consent.AFTER_SET`), the
     rules are compiled again. If what MARS APPLIES of them
     (`permission_rules.effective`: allow rules only under `task`, deny
     rules as `ask`) is NARROWER -- an operation the old applied rules
     allowed is no longer allowed by the new ones -- the run is halted
     (`agents_halt_run`, the Stop path). A run whose session has not opened
     yet is held to the cancel as it opens (`MarsExecution.precancel`: no
     session, or one cancelled before its prompt). A halt that still cannot
     take stays pending and is tried again on every request, event and
     consent set of the run -- no polling thread; meanwhile every permission
     request of the run is refused (`halting`). `execution-restart-asked` is recorded only once the
     halt took effect. A recheck that fails halts the run: it fails closed.
     A run whose applied rules allow nothing (consent `ask`/`deny`) is never
     halted; widening never is.
  4. When the halted run has ended, `restart_if_asked` (from `dispatch`,
     INSTEAD OF `resume_if_ready` for that ending) sends the same request
     again to its carrier, recorded as `work-restarted` -- unless the owner
     stopped it, or it is met or withdrawn. It is not a continuation, so
     continuity opens a FRESH session with rules from the new consent. A
     delegated child restarted this way has not ended: the work waiting on
     it is not resumed until the restarted run ends.

A carrier's Workflow change needs no restart: no compiled rule rests on the
standing edit allowance it withdraws (only `mentis-tools` and `approve-all`
are compiled).

Between the halt being asked and the runtime stopping, what the runtime does
by its old rules is outside Mentis's reach; every request that reaches
Mentis for the run is refused from the moment the narrowing is recorded.
"""

from __future__ import annotations

import threading
import time
import traceback

RESTART_ASKED = "execution-restart-asked"
RESTARTED = "work-restarted"
STOP_ASKED = "execution-stop-asked"
#: How long a pending halt keeps trying while the session is still opening.

_lock = threading.Lock()


def _live(cv) -> dict:
    got = getattr(cv, "_compiled_live", None)
    if got is None:
        got = {}
        try:
            cv._compiled_live = got
        except Exception:                                 # noqa: BLE001
            pass
    return got


def attach(cv, st) -> None:
    """Where halting and dispatching go for this record (`make_policy`)."""
    try:
        cv._compiled_st = st
    except Exception:                                     # noqa: BLE001
        pass


def opening(cv, run, *, workspace) -> None:
    """The run's consent is about to be read for its session."""
    with _lock:
        held = _live(cv).get(run)
        if held is None:
            _live(cv)[run] = {"rules": None, "mode": None, "workspace": workspace,
                              "open": False, "dirty": False, "halt": None}
        else:
            held["dirty"] = False


def settle(cv, run, rules, mode) -> bool:
    """Store the rules computed for the run. False when a consent was set
    while they were computed (compute again)."""
    with _lock:
        held = _live(cv).get(run)
        if held is None:
            return True
        if held["dirty"]:
            held["dirty"] = False
            return False
        held["rules"], held["mode"] = rules, mode
        return True


def opened(cv, run) -> None:
    """The session is opening with the rules last settled. A consent set
    after they were read (it marked the run dirty) is checked now."""
    with _lock:
        held = _live(cv).get(run)
        if held is None:
            return
        held["open"] = True
        dirty, held["dirty"] = held["dirty"], False
    if dirty:
        recheck(cv, only=run)


def untrack(cv, run) -> None:
    with _lock:
        _live(cv).pop(run, None)


def tracked(cv) -> dict:
    with _lock:
        return {k: dict(v) for k, v in _live(cv).items()}


def halting(cv, run) -> bool:
    """Whether the run is being stopped for stale rules: Mentis refuses its
    requests meanwhile."""
    with _lock:
        held = _live(cv).get(run)
        return bool(held and held.get("halt"))


# ---------------------------------------------------------------------------
# narrower


def _family(rule: str) -> tuple[str, str | None]:
    name, _, rest = rule.partition("(")
    return name, (rest[:-1] if rest.endswith(")") else None)


def _covers(allow: str, by: list[str]) -> bool:
    """Whether the allow rule's scope is wholly inside the rules `by`."""
    if allow in by:
        return True
    name, spec = _family(allow)
    if name in by:                                   # a bare tool covers its paths
        return True
    if name.startswith("mcp__"):
        return any(b.endswith("__*") and name.startswith(b[:-1]) for b in by)
    return False


def _plain(pattern: str) -> str:
    """A pattern's literal prefix, case classes read as their letter."""
    import re
    p = re.sub(r"\[([a-zA-Z])[a-zA-Z]\]", r"\1", pattern)
    cut = min([i for i in (p.find("*"), p.find("?"), p.find("[")) if i >= 0] or [len(p)])
    return p[:cut].lower()


def _intersects(ask: str, allow: str) -> bool:
    """Whether an ask (deny) rule can match something the allow rule allows.
    Conservative: True unless they are plainly about different things."""
    a_name, a_spec = _family(ask)
    w_name, w_spec = _family(allow)
    if w_name.startswith("mcp__") or a_name.startswith("mcp__"):
        if not (w_name.startswith("mcp__") and a_name.startswith("mcp__")):
            return False                  # an MCP tool and a built-in one
        if a_spec is not None or w_spec is not None:
            return True
        return _covers(ask, [allow]) or _covers(allow, [ask])
    families = {"Read": {"Read", "Grep", "Glob"},
                "Edit": {"Edit", "Write", "MultiEdit", "NotebookEdit"}}
    same = a_name == w_name or w_name in families.get(a_name, ()) \
        or a_name in families.get(w_name, ())
    if not same:
        return False
    if a_spec is None or w_spec is None:
        return True
    pa, pw = _plain(a_spec), _plain(w_spec)
    return pa.startswith(pw) or pw.startswith(pa)


def _applied(rules, mode) -> list:
    """The allows MARS applied that Mentis would not answer the same way
    anyway: its own tools are allowed by Mentis in every mode, so a rule
    allowing them is never something to lose."""
    from mentis.permission_rules import MENTIS_TOOLS, effective
    return [r for r in effective(rules, mode)["allow"] if r != MENTIS_TOOLS]


def narrower(old_rules, old_mode, new_rules, new_mode) -> bool:
    """Whether something the OLD rules, as MARS applied them, allowed is no
    longer allowed by the NEW ones as MARS would apply them. The run's own
    Mentis tools never count: Mentis allows them in every mode."""
    from mentis.permission_rules import effective
    old = _applied(old_rules, old_mode)
    if not old:
        return False                      # nothing the runtime decided
    new = effective(new_rules, new_mode)
    before = effective(old_rules, old_mode)["ask"]
    fresh_asks = [r for r in new["ask"] if r not in before]
    for rule in old:
        if not _covers(rule, new["allow"]):
            return True
        if any(_intersects(a, rule) for a in fresh_asks):
            return True
    return False


# ---------------------------------------------------------------------------
# recheck, halt, restart


def recheck(cv, *, only=None, cause=None) -> list[str]:
    """After the owner set consent (`cause`, the act): halt every open
    tracked run whose applied rules are now narrower; retry a halt still
    pending. Returns the runs a halt was asked for."""
    from mentis.operational import consent as _consent
    from mentis.web.permissions import runtime_rules
    st = getattr(cv, "_compiled_st", None)
    asked = []
    for run, held in tracked(cv).items():
        if only is not None and run != only:
            continue
        if held.get("halt"):
            _try_halt(cv, st, run)        # still pending: try again now
            continue
        if not held["open"] or held["rules"] is None:
            with _lock:
                h = _live(cv).get(run)
                if h is not None:
                    h["dirty"] = True     # read again before the session opens
            continue
        # A RUN UNDER THE HOST DEVELOPMENT POLICY (`execution.policy`): halted when the
        # owner's consent or policy no longer covers it; a failed check halts it.
        if isinstance(held["rules"], dict) and held["rules"].get("policy"):
            try:
                from mentis.execution import policy as _policy
                if _policy.still_holds(cv, run, held["workspace"]):
                    continue
                why = ("the owner's consent or execution policy no longer covers this run's "
                       f"unrestricted host execution ({held['rules']['policy']})")
            except Exception as exc:                      # noqa: BLE001
                traceback.print_exc()
                why = f"its execution policy could not be checked ({type(exc).__name__})"
            _request_halt(cv, st, run, why, cause, stale="its session runs under an execution "
                          "policy it no longer has")
            asked.append(run)
            continue
        # WHAT WAS SENT decides whether a failure must halt: a run whose
        # applied rules decide nothing has nothing stale to stop.
        if not _applied(held["rules"], held["mode"]):
            continue
        try:
            start = cv._act(run) or {}
            c = _consent.of_run(cv, run, workspace=held["workspace"])
            now = runtime_rules(c, workspace=held["workspace"],
                                runtime=start.get("runtime"))
            if not narrower(held["rules"], held["mode"], now, c.get("mode")):
                continue
            why = ("the owner narrowed what this run may do without asking "
                   f"(consent now: {c.get('mode')})")
        except Exception as exc:                          # noqa: BLE001
            traceback.print_exc()
            why = f"its permission rules could not be checked ({type(exc).__name__})"
        _request_halt(cv, st, run, why, cause)
        asked.append(run)
    return asked


def _request_halt(cv, st, run, why, cause=None,
                  stale="its session's compiled permission rules are stale") -> None:
    why = (why + f"; {stale}, so it is "
           "stopped and the work continues in a fresh session under the consent "
           "now in force")
    with _lock:
        held = _live(cv).get(run)
        if held is None:
            return
        held["halt"] = {"why": why, "at": time.time(), "cause": cause}
    # NO POLLING THREAD. A halt that cannot take yet stays pending: the
    # execution keeps a cancel asked before its session opens and cancels it
    # the moment it does (`MarsExecution.cancel`), and every request, event
    # and consent set of the run tries again (`nudge`, `recheck`). Meanwhile
    # every request of the run is refused.
    _try_halt(cv, st, run)




def nudge(cv, run) -> None:
    """A sign of life from a run being halted: try again now. Called on the
    ACP event loop too, so what it records is queued, not waited for."""
    if halting(cv, run):
        _try_halt(cv, getattr(cv, "_compiled_st", None), run, wait=False)


def _try_halt(cv, st, run, *, wait=True) -> bool:
    with _lock:
        held = _live(cv).get(run)
        halt = dict((held or {}).get("halt") or {})
    if not halt:
        return False
    if halt.get("took"):
        return True
    agents = getattr(st, "agents", None)
    if agents is None:
        return False
    try:
        took = bool(agents.agents_halt_run(run, by=SYSTEM, why=halt["why"]))
    except Exception:                                     # noqa: BLE001
        traceback.print_exc()
        return False
    if took:
        with _lock:
            h = _live(cv).get(run)
            if h is None or (h.get("halt") or {}).get("took"):
                return True
            h["halt"]["took"] = True
        _record_asked(cv, run, halt["why"], halt.get("cause"), wait=wait)
    return took


#: Mentis's own acts are recorded as Mentis, never in the owner's name.
SYSTEM = "mentis"
#: At most this many restarts of one request per `RESTART_WINDOW_S`; then the
#: work is held for the owner (`restart-held`).
RESTART_CAP, RESTART_WINDOW_S = 3, 3600.0
RESTART_HELD = "restart-held"


def _record_asked(cv, run, why, cause=None, *, wait=True) -> None:
    """Through the ordered write-behind queue (`permissions._Audit`), never
    on the caller's thread: the ACP event loop must not write the record.
    The run's end flushes it before its end act is written."""
    from mentis.web.permissions import _audit_for

    def write():
        start = cv._act(run) or {}
        cv.record_act(actor=SYSTEM, act=RESTART_ASKED,
                      conversation=start.get("conversation"), turn=start.get("turn"),
                      execution=start.get("execution"), runtime=start.get("runtime"),
                      caused_by=run, because=why[:300],
                      detail={"reason": "consent-narrowed",
                              **({"consent_act": cause} if cause else {})})
    _audit_for(cv)._enqueue(write, wait=wait)


#: What `restart_if_asked` returns for a halted run it did not restart: the
#: run's work has not ended, so nothing waiting on it resumes.
HELD = "held"


def restart_if_asked(st, run, dispatched: dict | None = None):
    """After a run ended: if it was halted for stale rules, dispatch the same
    request again, fresh. Returns the dispatch keywords; `HELD` when it was
    halted but is not restarted (the cap, already restarted, running again);
    or None -- not a halted run, or the owner stopped it, or the work is met
    or withdrawn -- and then the ending is an ordinary one: `resume_if_ready`
    runs as always.

    NOTHING RESTARTS IT LATER BY ITSELF. Not restarted, the work reads
    "Stopped for a consent change · not restarted" (`operational.work`), sits
    in the owner's Needs You, and holds what waits on it as an interrupted
    run does (`Conversations._child_state`) until somebody continues it."""
    cv = st.cv
    untrack(cv, run)
    acts = cv._c.operational(caused_by=run)
    asked = [a for a in acts if a["act"] == RESTART_ASKED]
    if not asked or any(a["act"] == STOP_ASKED for a in acts):
        return None
    start = cv._act(run) or {}
    exp = start.get("caused_by")
    if not exp:
        return None
    own = cv._c.operational(caused_by=exp)
    mine = [a for a in own if a["act"] == RESTARTED
            and (a.get("detail") or {}).get("run") == run]
    if mine or any(a["act"] == RESTART_HELD and (a.get("detail") or {}).get("run") == run
                   for a in own):
        return HELD                       # once per halted run
    from mentis.web import dispatch as D
    state = cv.expectation_state(exp)
    if state.get("satisfied_by") or D.withdrawal_of(cv, exp):
        return None
    if state.get("live_execution"):
        return HELD
    cause = (asked[-1].get("detail") or {}).get("consent_act")
    recent = [a for a in own if a["act"] == RESTARTED
              and a["at"] >= time.time() - RESTART_WINDOW_S]
    if len(recent) >= RESTART_CAP:
        cv.record_act(actor=SYSTEM, act=RESTART_HELD,
                      conversation=start.get("conversation"), turn=start.get("turn"),
                      caused_by=exp, about=[exp],
                      because=f"restarted {len(recent)} times within the hour after "
                              "its consent was narrowed; held for the owner to "
                              "continue or change",
                      detail={"run": run, "restarts": [a["id"] for a in recent]})
        return HELD
    act = cv.record_act(actor=SYSTEM, act=RESTARTED,
                        conversation=start.get("conversation"), turn=start.get("turn"),
                        caused_by=exp, about=[exp],
                        because="its previous session was stopped because the owner "
                                "narrowed its consent; the work continues in a fresh "
                                "session under the consent now in force",
                        detail={"run": run, "asked": asked[-1]["id"],
                                "reason": (asked[-1].get("detail") or {}).get("reason"),
                                **({"consent_act": cause} if cause else {})})
    notice = ("Your previous session of this work was stopped "
              f"({act}) because the owner narrowed what it may do without "
              "asking. Continue the work under the consent stated below; "
              "check what the previous session already did before redoing it, "
              "and end your run with a written report.")
    if dispatched:
        # THE SAME CONTEXT THE HALTED RUN WAS GIVEN -- a resumption's text
        # with the owner's follow-ups and children's results, its deadline,
        # model, effort, Persona -- plus the follow-ups shown to it while it
        # ran, in a FRESH session: no `resumed_from`, so continuity opens a
        # new one under the new consent.
        kw = {k: v for k, v in dispatched.items()
              if k not in ("resumed_from", "triggered_at", "new_instance")}
        shown = _shown_to(cv, exp, start)
        kw["work"] = (notice + "\n\n" + (dispatched.get("work") or "")
                      + (("\n\nFollow-ups the owner gave while the stopped session "
                          "worked (already counted as given to this work):\n"
                          + "\n".join(shown)) if shown else ""))
        kw["because"] = f"restarted fresh after consent narrowed ({asked[-1]['id']})"
    else:
        carrier = start.get("actor")
        requires = D.recorded_requires(cv, exp)
        said = D.execution_scope(cv, exp)["constraints"]
        words = D.request_words(cv, exp) or ""
        persona = D.started_persona(cv, exp, carrier) or D.delegated_persona(cv, exp)
        kw = dict(conversation=start.get("conversation"), turn=start.get("turn"),
                  participant=carrier, persona=persona, expectation=exp,
                  requires=tuple(requires), model=said.get("model"),
                  effort=said.get("effort"), work=notice + "\n\n" + words,
                  question=words or None,
                  because=f"restarted fresh after consent narrowed ({asked[-1]['id']})")
    import mentis.web as web
    web.dispatch_soon(st, **kw)
    return kw


def _shown_to(cv, exp, start) -> list[str]:
    """The owner's follow-ups shown to the halted run while it worked, in
    their words (`follow-up-shown` on its execution, after it started)."""
    from mentis.web.dispatch import request_words
    out = []
    for a in cv._c.operational(caused_by=exp):
        if a["act"] != "follow-up-shown" or a.get("execution") != start.get("execution") \
                or a["at"] < start.get("at", 0):
            continue
        for fid in (a.get("detail") or {}).get("follow_ups") or ():
            f = cv._act(fid) or {}
            req = (f.get("detail") or {}).get("request")
            words = request_words(cv, req) if req else ""
            out.append(f"- the owner's follow-up ({req or fid}): {words}")
    return out


def after_set(cv, run=None, act=None) -> None:
    """`consent.AFTER_SET` hook: `act` is the owner's consent act."""
    if tracked(cv):
        recheck(cv, cause=act)
