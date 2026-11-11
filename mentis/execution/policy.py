"""Development execution policies: how much of the host a dispatched runtime may use.

THE INTERIM POLICY (owner decision, 2026-11-11): `host-development-unrestricted`.
For an AUTHORISED SOFTWARE-DEVELOPMENT run on a runtime that declares it (codex,
antigravity: MARS's capability contract, `permission_enforcement.execution_policies`),
the runtime runs in its own documented unrestricted mode -- codex-acp `full-access`,
agy `--dangerously-skip-permissions` without `--sandbox` -- so shell commands, source
reads and writes, dependency installs, builds, tests and Git are not blocked by its
native sandbox, and nothing is asked mid-run.

WHAT IT IS NOT.
- It is HOST execution, not isolation. The runtime runs as the owner on this machine,
  with its filesystem and network; it is recorded and told as such, never as a sandbox
  or a container.
- It grants NO Mentis authority. Every Mentis operation the run makes still goes through
  `/api/worker` against the run's grant: delegating, changing governance, adopting
  epistemic records are exactly as permitted as before. Deploying to DAY-TO-DAY or
  changing production still needs the owner's approval; the run is told so
  (`BOUNDARY`). On the host, that boundary is held by authority and instruction, not by
  a sandbox -- said plainly wherever enforcement is reported.
- It is TEMPORARY: to be replaced by unrestricted execution inside an assigned container
  (`SUCCESSOR`), which MARS declares unsupported until it can assign one.

WHEN IT IS SELECTED -- all of, per run, never by a runtime's name:
1. the owner's standing authorisation is in force: the newest `execution-policy-set` act
   BY THE OWNER for this policy is enabled and names the runtime (`authorise`);
2. the runtime's contract declares the policy;
3. the run's request carries owner-given consent (`source` not `none`) of routine work
   or Approve All, whose categories make it development work: `edit` and `git`, and at
   least one of `test`, `build`, `run` (`DEVELOPMENT`);
4. the run has a workspace.
A hand-started session, a run with no owner consent, or a consent narrowed below
development work is never given it. Each selection is recorded
(`execution-policy-selected`, caused by the run's start): the policy, the runtime, the
execution, the workspace(s), and the owner act that authorised it.
"""

from __future__ import annotations

HOST_DEV = "host-development-unrestricted"
SUCCESSOR = "container-development-unrestricted"
SET = "execution-policy-set"
SELECTED = "execution-policy-selected"
#: Consent categories that make a run development work (all of `NEEDS`, one of `ANY`).
DEVELOPMENT = {"needs": ("edit", "git"), "any": ("test", "build", "run")}
#: What a run under the policy is told it still may not do (its grant decides the rest).
BOUNDARY = ("Your execution is unrestricted on the host (owner's interim development policy "
            f"{HOST_DEV}): you may run shell commands, read and write source files, install "
            "dependencies, build, test and use Git without asking. This is the owner's machine, "
            "not a container. It does not extend your Mentis authority: do not delegate unrelated "
            "work, change governance or adopt records beyond what your grant allows, and do not "
            "deploy to DAY-TO-DAY, touch the live Brain or change any production system -- those "
            "need the owner's approval through Mentis. Reach Mentis only through your Mentis "
            "tools: never call its HTTP routes directly or edit Brain, Mentis or MARS data files.")


def authorise(cv, *, owner, enabled: bool, runtimes, authorization: str,
              policy: str = HOST_DEV, written_by=None) -> str:
    """The OWNER turns the policy on or off for these runtimes, with the words of the
    decision that authorises it. Only the owner's act counts (`authorisation`)."""
    if policy != HOST_DEV:
        raise ValueError(f"unknown execution policy {policy!r}")
    names = sorted({str(r) for r in runtimes or ()})
    if enabled and not names:
        raise ValueError("name the runtimes the policy applies to")
    if not (authorization or "").strip():
        raise ValueError("say the owner decision that authorises it")
    act = cv.record_act(actor=owner, act=SET,
                         because=f"{policy} {'enabled' if enabled else 'disabled'}"
                                 + (f" for {', '.join(names)}" if enabled else ""),
                         detail={"policy": policy, "enabled": bool(enabled),
                                 "runtimes": names if enabled else [],
                                 "authorization": authorization.strip(),
                                 "isolation": "host", "temporary": True,
                                 "successor": SUCCESSOR,
                                 **({"written_by": written_by} if written_by else {})})
    # A LIVE RUN NO LONGER COVERED (disabled, or its runtime dropped) is halted and restarted
    # fresh under what is now in force, as for a consent narrowing (`web.compiled_runs`).
    try:
        from mentis.web import compiled_runs
        compiled_runs.recheck(cv, cause=act)
    except Exception:                                     # noqa: BLE001
        import traceback
        traceback.print_exc()
    return act


def authorisation(cv, policy: str = HOST_DEV) -> dict | None:
    """The owner's act in force for this policy (the newest), or None. An act by anyone
    but the owner is never read."""
    from mentis.conversation.owner import _owner
    owner = _owner(cv)
    if not owner:
        return None
    acts = [a for a in cv._c.operational(actor=owner, act=SET)
            if (a.get("detail") or {}).get("policy") == policy]
    if not acts:
        return None
    order = cv._write_order([a["id"] for a in acts])
    last = max(acts, key=lambda a: (order.get(a["id"], -1), a["at"]))
    return last


def declared(contract: dict | None, policy: str = HOST_DEV) -> bool:
    """Whether the runtime's capability contract declares this policy."""
    c = ((contract or {}).get("capabilities") or {}).get("permission_enforcement")
    pol = (c.get("execution_policies") or {}).get(policy) if isinstance(c, dict) else None
    return isinstance(pol, dict) and isinstance(pol.get("options"), dict) \
        and pol.get("state") not in ("unsupported", "unavailable")


def development_consent(consent: dict | None) -> bool:
    """Owner-given routine-work or Approve All consent covering development work."""
    from mentis.operational import consent as _consent
    c = consent or {}
    if c.get("source") in (None, "none") or c.get("mode") not in (_consent.TASK, _consent.ALL):
        return False
    cats = set(c.get("categories") or ())
    return all(n in cats for n in DEVELOPMENT["needs"]) and bool(cats.intersection(DEVELOPMENT["any"]))


def select(cv, run, *, workspace, runtime, contract, consent) -> dict | None:
    """The policy this run is given, with why, or None (see the module docs)."""
    if not (run and workspace and runtime) or not declared(contract):
        return None
    if not development_consent(consent):
        return None
    # ONLY INSIDE THE CONSENTED WORKSPACES (review r3, finding 2): a delegated child whose
    # declared repository lies outside what the owner consented to is never given it.
    from mentis.operations import inside
    if not any(inside(workspace, w) for w in consent.get("workspaces") or ()):
        return None
    auth = authorisation(cv)
    detail = (auth or {}).get("detail") or {}
    if not detail.get("enabled") or runtime not in (detail.get("runtimes") or ()):
        return None
    return {"policy": HOST_DEV, "runtime": runtime, "run": run, "workspace": workspace,
            "workspaces": list(dict.fromkeys([workspace, *(consent.get("workspaces") or ())])),
            "authorization": {"act": auth["id"], "by": auth.get("actor"),
                              "words": detail.get("authorization")},
            "consent": {"mode": consent.get("mode"), "source": consent.get("source"),
                        "granted_at": consent.get("granted_at"),
                        "categories": list(consent.get("categories") or ())},
            "isolation": "host", "container": False, "temporary": True,
            "successor": SUCCESSOR}


def still_holds(cv, run, workspace) -> bool:
    """Whether a live run given the policy is still covered by it: the owner's
    authorisation still names its runtime, and its consent still covers development work
    in its workspace. Checked whenever the owner sets consent or the policy, and just
    before the session opens (`web.compiled_runs`); a run no longer covered is halted and
    restarted fresh under what is now in force."""
    from mentis.operational import consent as _consent
    from mentis.operations import inside
    runtime = (of_run(cv, run) or {}).get("runtime") or (cv._act(run) or {}).get("runtime")
    detail = (authorisation(cv) or {}).get("detail") or {}
    if not detail.get("enabled") or runtime not in (detail.get("runtimes") or ()):
        return False
    c = _consent.of_run(cv, run, workspace=workspace)
    return development_consent(c) and any(inside(workspace, w) for w in c.get("workspaces") or ())


def record(cv, run, selected: dict) -> str | None:
    """Record the selection, caused by the run's start, before the session opens."""
    start = cv._act(run)
    if not start:
        return None
    return cv.record_act(actor=start["actor"], act=SELECTED,
                         conversation=start.get("conversation"), turn=start.get("turn"),
                         execution=start.get("execution"), runtime=start.get("runtime"),
                         caused_by=run,
                         because=f"{selected['policy']} for {selected['runtime']} in "
                                 f"{selected['workspace']}, authorised by owner act "
                                 f"{selected['authorization']['act']}",
                         detail={**selected, "execution": start.get("execution")})


def of_run(cv, run) -> dict | None:
    """The policy recorded for this run, or None."""
    acts = cv._c.operational(caused_by=run, act=SELECTED)
    return (acts[-1].get("detail") or None) if acts else None
