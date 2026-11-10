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
     (`agents_halt_run`, the Stop path). A halt the runtime cannot take yet
     (the session is still opening) stays pending and is retried until it
     takes or the run ends; meanwhile every permission request of the run is
     refused (`halting`). `execution-restart-asked` is recorded only once the
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
HALT_WAIT_S = 600.0
HALT_POLL_S = 0.1

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
    with _lock:
        held = _live(cv).get(run)
        if held is not None:
            held["open"] = True


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


def narrower(old_rules, old_mode, new_rules, new_mode) -> bool:
    """Whether something the OLD rules, as MARS applied them, allowed is no
    longer allowed by the NEW ones as MARS would apply them."""
    from mentis.permission_rules import effective
    old = effective(old_rules, old_mode)
    new = effective(new_rules, new_mode)
    if not old["allow"]:
        return False                      # nothing was allowed by the runtime
    fresh_asks = [r for r in new["ask"] if r not in old["ask"]]
    for rule in old["allow"]:
        if not _covers(rule, new["allow"]):
            return True
        if any(_intersects(a, rule) for a in fresh_asks):
            return True
    return False


# ---------------------------------------------------------------------------
# recheck, halt, restart


def recheck(cv) -> list[str]:
    """After the owner set consent: halt every open tracked run whose
    applied rules are now narrower. Returns the runs a halt was asked for."""
    from mentis.operational import consent as _consent
    from mentis.web.permissions import runtime_rules
    st = getattr(cv, "_compiled_st", None)
    asked = []
    for run, held in tracked(cv).items():
        if held.get("halt"):
            continue
        if not held["open"] or held["rules"] is None:
            with _lock:
                h = _live(cv).get(run)
                if h is not None:
                    h["dirty"] = True     # recomputed before the session opens
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
        _request_halt(cv, st, run, why)
        asked.append(run)
    return asked


def _request_halt(cv, st, run, why) -> None:
    why = (why + "; its session's compiled permission rules are stale, so it is "
           "stopped and the work continues in a fresh session under the consent "
           "now in force")
    with _lock:
        held = _live(cv).get(run)
        if held is None:
            return
        held["halt"] = {"why": why, "at": time.time()}
    if _try_halt(cv, st, run, why):
        return
    threading.Thread(target=_keep_trying, args=(cv, st, run, why), daemon=True,
                     name="compiled-run-halt").start()


def _keep_trying(cv, st, run, why) -> None:
    deadline = time.time() + HALT_WAIT_S
    while time.time() < deadline:
        time.sleep(HALT_POLL_S)
        with _lock:
            if run not in _live(cv):
                return                    # ended (or untracked) before it took
        try:
            if cv.run_end(run) is not None:
                return
        except Exception:                                 # noqa: BLE001
            pass
        if _try_halt(cv, st, run, why):
            return


def _try_halt(cv, st, run, why) -> bool:
    agents = getattr(st, "agents", None)
    if agents is None:
        return False
    try:
        took = bool(agents.agents_halt_run(run, by="mentis", why=why))
    except Exception:                                     # noqa: BLE001
        traceback.print_exc()
        return False
    if took:
        _record_asked(cv, run, why)
    return took


def _record_asked(cv, run, why) -> None:
    from mentis.conversation.owner import _owner
    start = cv._act(run) or {}
    cv.record_act(actor=_owner(cv) or start.get("actor"), act=RESTART_ASKED,
                  conversation=start.get("conversation"), turn=start.get("turn"),
                  execution=start.get("execution"), runtime=start.get("runtime"),
                  caused_by=run, because=why[:300],
                  detail={"reason": "consent-narrowed"})


def restart_if_asked(st, run) -> dict | None:
    """After a run ended: if it was halted for stale rules, dispatch the same
    request again, fresh. Returns the dispatch keywords, or None (and then
    the ending is an ordinary one: `resume_if_ready` runs as always).

    Not when the owner stopped the run, or the work is met, withdrawn or
    running again."""
    cv = st.cv
    untrack(cv, run)
    acts = cv._c.operational(caused_by=run)
    asked = [a for a in acts if a["act"] == RESTART_ASKED]
    if not asked or any(a["act"] == STOP_ASKED for a in acts):
        return None
    start = cv._act(run) or {}
    exp = start.get("caused_by")
    if not exp or any(a["act"] == RESTARTED and (a.get("detail") or {}).get("run") == run
                      for a in cv._c.operational(caused_by=exp)):
        return None
    from mentis.web import dispatch as D
    state = cv.expectation_state(exp)
    if state.get("satisfied_by") or state.get("live_execution") \
            or D.withdrawal_of(cv, exp):
        return None
    carrier = start.get("actor")
    requires = D.recorded_requires(cv, exp)
    said = D.execution_scope(cv, exp)["constraints"]
    act = cv.record_act(actor=asked[-1]["actor"], act=RESTARTED,
                        conversation=start.get("conversation"), turn=start.get("turn"),
                        caused_by=exp, about=[exp],
                        because="its previous session was stopped because the owner "
                                "narrowed its consent; the work continues in a fresh "
                                "session under the consent now in force",
                        detail={"run": run, "asked": asked[-1]["id"],
                                "reason": (asked[-1].get("detail") or {}).get("reason")})
    words = D.request_words(cv, exp) or ""
    persona = D.started_persona(cv, exp, carrier) or D.delegated_persona(cv, exp)
    kw = dict(conversation=start.get("conversation"), turn=start.get("turn"),
              participant=carrier, persona=persona, expectation=exp,
              requires=tuple(requires), model=said.get("model"),
              effort=said.get("effort"),
              work=("Your previous session of this work was stopped "
                    f"({act}) because the owner narrowed what it may do without "
                    "asking. Continue the work under the consent stated below; "
                    "check what the previous session already did before redoing "
                    f"it, and end your run with a written report.\n\n{words}"),
              question=words or None,
              because=f"restarted fresh after consent narrowed ({asked[-1]['id']})")
    import mentis.web as web
    web.dispatch_soon(st, **kw)
    return kw


def after_set(cv, run=None) -> None:
    """`consent.AFTER_SET` hook."""
    if tracked(cv):
        recheck(cv)
