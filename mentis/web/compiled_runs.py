"""Live runs holding compiled permission rules, and what happens when the
authority those rules were compiled from narrows while they run
(docs/modernization/CONTRACT.md WS-A; `mentis.permission_rules`).

A runtime is handed its rules when its session opens and cannot be handed
new ones mid-session. So AUTHORITY CHANGES REMAIN EFFECTIVE only if a session
whose rules have gone stale stops relying on them:

  1. `track` remembers, per record, the rules each live run was handed.
  2. Whenever the owner sets consent (`consent.AFTER_SET`: a task or run
     consent narrowed, Approve All revoked, `deny` set, a tool revoked),
     `recheck` compiles every tracked run's rules again from the consent now
     in force. If they are NARROWER -- an allow the run holds is no longer
     covered, or a deny it lacks is now due -- the run's session is halted at
     once (`agents_halt_run`, the Stop button's path), with an
     `execution-restart-asked` act saying why. Widening restarts nothing: the
     stale rules ask Mentis about the rest, which answers under the wider
     consent.
  3. When that run has ended (`dispatch.dispatch`, after its end act and any
     resumption), `restart_if_asked` dispatches the SAME request again to its
     carrier, recorded as `work-restarted`. It is not a continuation
     (`resumed_from` is not given), so continuity opens a FRESH session
     (`continuity.decide`), whose rules are compiled from the new consent.

A carrier's Workflow change needs no restart: it withdraws only the run's
standing allowance to edit (`permissions.decide`), and no edit rule is
compiled from that allowance -- under `ask` there is none, and under routine
work an edit is allowed by the owner's consent, which a Workflow change does
not touch. `test_permission_compiled` holds both.

Between the narrowing being recorded and the runtime stopping, what the
runtime decides by its stale rules is outside Mentis's reach; every request
that reaches Mentis is answered under the new consent. The window is the
cancel's (MARS ends the turn, or kills the session within its grace).
"""

from __future__ import annotations

import threading
import traceback

RESTART_ASKED = "execution-restart-asked"
RESTARTED = "work-restarted"

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


def track(cv, run, rules, *, workspace) -> None:
    """A run's session is being handed these rules."""
    with _lock:
        _live(cv)[run] = {"rules": rules, "workspace": workspace}


def untrack(cv, run) -> None:
    with _lock:
        _live(cv).pop(run, None)


def tracked(cv) -> dict:
    with _lock:
        return dict(_live(cv))


def narrower(old: dict | None, new: dict | None) -> bool:
    """Whether `new` takes away anything `old` allows: an allow of `old` not
    covered by `new` (a path rule is covered by its bare tool), or a deny of
    `new` that `old` lacks."""
    old = old or {"allow": [], "deny": []}
    new = new or {"allow": [], "deny": []}
    have = set(new.get("allow") or ())
    for rule in old.get("allow") or ():
        if rule in have:
            continue
        tool = rule.split("(", 1)[0]
        if "(" in rule and tool in have:
            continue
        return True
    return bool(set(new.get("deny") or ()) - set(old.get("deny") or ()))


def recheck(cv) -> list[str]:
    """After the owner set consent: halt every tracked run whose rules are
    now narrower than the consent in force. Returns the runs halted."""
    from mentis.operational import consent as _consent
    from mentis.web.permissions import runtime_rules
    st = getattr(cv, "_compiled_st", None)
    halted = []
    for run, held in tracked(cv).items():
        try:
            start = cv._act(run) or {}
            c = _consent.of_run(cv, run, workspace=held["workspace"])
            now = runtime_rules(c, workspace=held["workspace"],
                                runtime=start.get("runtime"))
            if not narrower(held["rules"], now):
                continue
            if _halt(cv, st, run, start, held["rules"], now, c):
                halted.append(run)
        except Exception:                                 # noqa: BLE001
            traceback.print_exc()
    return halted


def _halt(cv, st, run, start, old, new, consent) -> bool:
    from mentis.conversation.owner import _owner
    untrack(cv, run)
    why = ("the owner narrowed what this run may do without asking "
           f"(consent now: {consent.get('mode')}); its session's compiled "
           "permission rules are stale, so it is stopped and the work "
           "continues in a fresh session under the new consent")
    who = _owner(cv) or start.get("actor")
    cv.record_act(actor=who, act=RESTART_ASKED,
                  conversation=start.get("conversation"), turn=start.get("turn"),
                  execution=start.get("execution"), runtime=start.get("runtime"),
                  caused_by=run, because=why[:300],
                  detail={"reason": "consent-narrowed",
                          "rules_before": {k: len(v) for k, v in (old or {}).items()},
                          "rules_now": ({k: len(v) for k, v in new.items()}
                                        if new else None),
                          "mode_now": consent.get("mode")})
    agents = getattr(st, "agents", None)
    if agents is None:
        return False
    try:
        return bool(agents.agents_halt_run(run, by=who or "mentis", why=why))
    except Exception:                                     # noqa: BLE001
        traceback.print_exc()
        return False


def restart_if_asked(st, run) -> dict | None:
    """After a run ended: if it was stopped for stale rules, dispatch the
    same request again, fresh. Returns the dispatch keywords, or None.

    Not when the work is met, withdrawn, already running again, or was
    resumed since this run started (`resume_if_ready` got there first)."""
    cv = st.cv
    untrack(cv, run)
    asked = [a for a in cv._c.operational(caused_by=run) if a["act"] == RESTART_ASKED]
    if not asked:
        return None
    start = cv._act(run) or {}
    exp = start.get("caused_by")
    own = cv._c.operational(caused_by=exp) if exp else []
    if not exp or any(a["act"] == RESTARTED and (a.get("detail") or {}).get("run") == run
                      or a["act"] == "work-resumed" and a["at"] >= start.get("at", 0)
                      for a in own):
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
