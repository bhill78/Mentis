"""Who answers an agent's permission request, when MARS forwards one.

MARS forwards every `session/request_permission` from a backend unchanged and
never picks an allow option itself (MARS docs/API.md, Permissions). Mentis
answers each one under its own authority, and nothing else
(docs/run-consent.md):

  1. BY THE RUN'S GRANT, for what the run was already given: reading
     anywhere that is not protected -- a shell command that only reads is a
     read -- its own Mentis tools (each checked again by `/api/worker`), and
     editing files inside the workspace it was asked to work in.
  2. BY THE OWNER'S CONSENT for this task or this run
     (`mentis.operational.consent`): an operation inside the task's
     boundary when the owner let routine work proceed, or a tool the owner
     allowed for this run, used inside the approved workspaces. Consent set
     to `deny` refuses at once whatever would otherwise be asked.
  3. BY THE OWNER, for everything else. The request becomes an ordinary
     DECISION FORM on the post the run is working on (`worker._decision_form`,
     the machinery `request_decision` uses), owed by the owner. Its question
     is what the operation does, in words (`mentis.operations`), never the raw
     command; its answers are Allow once, Allow <tool> for this run, Allow
     within this task, and Deny -- the wider two only for an operation
     inside the task's boundary. The run waits for the answer.

A RUNTIME'S OWN "ALWAYS ALLOW" IS NEVER CHOSEN. Claude's "don't ask again"
writes a rule into the workspace's settings that outlives the run and that
no record holds; consent is held in the record instead, and every allow
selects the request's `allow_once`.

EVERY ANSWER IS RECORDED (`operation-answered`, caused by the run): what was
asked, in words and exactly, and who answered how. What the run then did is
on its end act (`tool_calls`).

FAIL CLOSED. No answer within `WAIT_S` (inside MARS's own 1800 s
`permission_s`: the owner may not be watching), the run stopped, or nowhere to ask (no request, no
Conversation): the request is refused with the backend's reject option.

AND THE QUESTION STOPS ASKING. Nothing but this wait can consume its answer,
so when the wait ends unanswered the asker closes the question as lapsed
(`Conversations.retire_permission_question`): the question, its form and its
options stay as asked, an answer is refused as closed, and it leaves Needs
You. It is not the owner's withdrawal and decides nothing for them. A server
that died mid-wait leaves its questions open; the next one to serve the
Brain closes them before it runs anything (`retire_unconsumable`).
"""

from __future__ import annotations

import os
import time

from mentis.operations import (DEFAULT_CATEGORIES, GUARDED, RESEARCH, describe, inside,
                               is_guarded, read_only)
from mentis.operational import consent as _consent

#: How long a run waits for the owner, inside MARS's permission_s (1800 s).
WAIT_S = 1770.0
#: How often the wait looks for the answer: often while the owner is likely
#: looking, then less, so a long wait costs the server little.
POLL_S = 0.5
POLL_LATER_S, POLL_SLOWS_AFTER_S = 2.0, 30.0
#: Tool kinds the run's grant answers wherever they point.
READS = {"read", "search", "think"}
__all__ = ["COMPILED_SCOPE_RUNTIMES", "GUARDED", "READS", "WAIT_S", "Decision", "decide",
           "make_policy", "mars_consent", "runtime_rules", "standing_answer"]

ONCE, TOOL, TASK, DENY = "once", "tool", "task", "deny"
#: allow public web research for the rest of this task
RESEARCH_TASK = "research"


def _inside(path: str, root: str) -> bool:
    if not os.path.isabs(path):
        return False          # resolved against nothing the run names: not inside
    return inside(path, root)


def _guarded(path: str, root: str) -> bool:
    return is_guarded(path, root)


def _allow_once(request: dict) -> str | None:
    return next((o["option_id"] for o in request.get("options") or ()
                 if o.get("kind") == "allow_once"), None)


def _reject(request: dict) -> str | None:
    return next((o["option_id"] for o in request.get("options") or ()
                 if o.get("kind") == "reject_once"), None)


def standing_answer(request: dict, workspace: str | None) -> str | None:
    """The option the run's own grant answers with, or None for the owner.
    Reads by tool kind, and edits inside the workspace that touch no
    guarded file."""
    tool = request.get("tool_call") or {}
    kind = tool.get("kind")
    allow = _allow_once(request)
    if allow is None:
        return None
    if kind in READS:
        return allow
    if kind == "edit" and workspace:
        paths = [loc.get("path") for loc in tool.get("locations") or ()
                 if isinstance(loc, dict) and loc.get("path")]
        if paths and all(_inside(p, workspace) and not _guarded(p, workspace)
                         for p in paths):
            return allow
    return None


#: RUNTIMES GIVEN THE RUN'S CONSENT AS THEIR OWN PERMISSION RULES
#: (`mentis.permission_rules`), so the operations those rules allow never
#: reach Mentis. Only runtimes where the replay of every recorded request
#: (`tools/permission_replay.py`, docs/modernization/permission-replay.md)
#: found no request the compiled rules would allow that Mentis would have
#: asked about or refused. Every other runtime is answered per operation.
COMPILED_SCOPE_RUNTIMES: frozenset = frozenset({"claude"})


def runtime_rules(consent: dict, *, workspace, runtime) -> dict | None:
    """The compiled rules for a run on this runtime, or None."""
    if runtime not in COMPILED_SCOPE_RUNTIMES:
        return None
    if runtime == "claude":
        from mentis.permission_rules import compile_claude
        return compile_claude(consent, workspace=workspace)
    return None


def mars_consent(cv, run, workspace) -> dict | None:
    """What MARS is told of a run's consent: its mode, the workspaces
    beyond the one it runs in, and -- for a runtime in
    `COMPILED_SCOPE_RUNTIMES` -- `runtime_rules`, the consent as that
    runtime's own allow and deny rules. None when the owner gave none and
    nothing is compiled.

    A run given rules is TRACKED from before its consent is read until it
    ends (`compiled_runs`), so a narrowing at any moment reaches it."""
    from mentis.web import compiled_runs
    start = cv._act(run) or {}
    where = workspace or (start.get("detail") or {}).get("workspace")
    compiled = start.get("runtime") in COMPILED_SCOPE_RUNTIMES
    if compiled:
        compiled_runs.opening(cv, run, workspace=where)
    for _ in range(5):
        c = _consent.of_run(cv, run, workspace=workspace)
        rules = runtime_rules(c, workspace=where, runtime=start.get("runtime"))
        if not compiled or compiled_runs.settle(cv, run, rules, c["mode"]):
            break
    else:
        rules = None          # consent kept changing while it was read: none
        if compiled:
            compiled_runs.settle(cv, run, None, c["mode"])
    if c["source"] == "none":
        # ALWAYS TOLD, even with no owner consent: `ask` with no workspaces
        # adds no directory and confines nothing in MARS, and MARS's answer
        # (`enforced_by`) is how the run's record says truthfully whether
        # anything enforces consent on its runtime at all (round 2, O3: a
        # `local` run in full access neither asks nor is confined).
        return {"mode": _consent.ASK, "workspaces": [],
                **({"runtime_rules": rules} if rules else {})}
    extra = [w for w in c["workspaces"]
             if not (workspace and os.path.normcase(os.path.normpath(w))
                     == os.path.normcase(os.path.normpath(workspace)))]
    # Approve All is Mentis's answer, not a runtime capability: MARS hears `task`.
    return {"mode": _consent.TASK if c["mode"] == _consent.ALL else c["mode"],
            "workspaces": extra, **({"runtime_rules": rules} if rules else {})}


#: WHAT ENFORCES A RUN'S CONSENT, by what MARS reported it applied
#: (`mars/consent.enforced_by`, docs/modernization/CONTRACT.md "Round 2 — A",
#: permission-enforcement matrix). Mentis never claims more than this.
ENFORCEMENT_WORDS = {
    "client": "Every operation the runtime would ask about reaches Mentis, which decides it.",
    "sandbox+client": ("The runtime's own sandbox confines what it may change, and it works "
                       "inside the sandbox without asking (what it reads there is not decided "
                       "by Mentis); only what the runtime escalates reaches Mentis."),
    "sandbox": ("The runtime asks nothing: it is confined by its sandbox and the rules it was "
                "started with; Mentis decides nothing while it runs."),
    "none": ("The runtime neither asks nor is confined: this consent is recorded, but "
             "nothing enforces it."),
}


def enforcement(applied: dict | None) -> dict:
    """What enforces a run's consent, in words, from MARS's report (`applied`,
    the `session/new` result's `mars/consent`). `enforced: True` only where
    something does; unknown (no report yet) is not enforced."""
    by = (applied or {}).get("enforced_by") if isinstance(applied, dict) else None
    rules = (applied or {}).get("runtime_rules") if isinstance(applied, dict) else None
    out = {"by": by, "enforced": by in ("client", "sandbox+client", "sandbox"),
           "words": ENFORCEMENT_WORDS.get(by, "Not reported: how this run's consent is "
                                              "enforced is not known.")}
    if isinstance(rules, dict) and rules.get("applied"):
        out["runtime_rules"] = {"allow": rules.get("allow"), "ask": rules.get("deny"),
                                "refuse": rules.get("refuse", 0)}
        out["words"] += (" Operations its compiled rules allow are decided by the runtime from "
                         "those rules, and are recorded as they are seen.")
        if rules.get("refuse"):
            from mentis.permission_rules import secret_read_path
            out["words"] += (" " + secret_read_path().replace("your own", "its own")
                             .replace("you", "the agent")
                             + " Other protected files and locations are asked of the owner.")
    return out


def before_open(cv, run, workspace, told: dict) -> None:
    """IMMEDIATELY BEFORE THE SESSION OPENS: what MARS is told is read again
    from the consent in force and replaces `told` in place (it is the
    `RunSpec.consent` about to be sent), so a consent narrowed since it was
    first read is the one the runtime's rules come from."""
    from mentis.web import compiled_runs
    start = cv._act(run) or {}
    if start.get("runtime") not in COMPILED_SCOPE_RUNTIMES:
        return
    compiled_runs.nudge(cv, run)          # a halt pending since before the open
    fresh = mars_consent(cv, run, workspace)
    if not fresh or not fresh.get("runtime_rules"):
        told.pop("runtime_rules", None)
    if fresh:
        told.update(fresh)
    compiled_runs.opened(cv, run)


#: WHAT THE CONSENT'S CATEGORIES COME TO IN AGY'S OWN ALLOW RULES (MARS
#: docs/API.md, `allow`). Headless agy cannot ask: a command with no rule is
#: refused and the turn ends with nothing said, so without this no run could
#: read a diff. `--sandbox` stays on underneath: measured 2026-11-03, a
#: permitted command still cannot write the workspace or leave it, cannot open
#: a socket, and cannot read a credentials directory or Mentis's or MARS's data.
_AGY_SHELL = frozenset({"test", "build", "run"})


def runtime_options(cv, run, workspace, runtime) -> dict:
    """What MARS passes to this run's runtime for its consent. Only Antigravity
    has a mechanism that needs telling; `ask` and `deny` add nothing, because
    a runtime that cannot ask is refused, never answered for. Nor does a narrowed
    consent get a narrower rule: agy matches a rule against the whole command
    line, so `command(git *)` misses the `Set-Location` a run is told to start
    with and passes `git -c alias.x=!anything`. It is refused instead."""
    if runtime != "antigravity":
        return {}
    c = _consent.of_run(cv, run, workspace=workspace)
    if c["source"] == "none":
        return {}
    # APPROVE ALL ALSO ALLOWS THE TOOLS OF THE OWNER'S USER-LEVEL MCP SERVERS the
    # run is given (WS-M assembly; MARS adds `mcp(<name>/*)` for exactly those):
    # Mentis would allow them under Approve All. Under any narrower consent they
    # stay refused by agy and reported as such -- a non-Mentis MCP tool is
    # nothing a narrower consent decides without asking, and agy cannot ask.
    if c["mode"] == _consent.ALL:
        return {"allow": ["command(*)"], "allow_given_mcp": True}
    if c["mode"] == _consent.TASK and _AGY_SHELL.intersection(c["categories"]):
        return {"allow": ["command(*)"]}
    return {}


def offers(op, consent) -> list[str]:
    """What the owner may answer this operation with. The wider answers only
    for an operation inside the task's boundary, consent apart."""
    out = [ONCE]
    if op.category == RESEARCH:
        return [ONCE, RESEARCH_TASK, DENY]
    other_only = all(c in (*consent["categories"], "other") for c in (op.parts or [op.category]))
    if op.in_workspaces and other_only and op.tools and op.category != "mentis":
        out.append(TOOL)
    if op.within or op.offer_workspace:
        out.append(TASK)
    return [*out, DENY]


def _words(op, consent, offer, alias) -> tuple[str, str]:
    """An answer's label and what choosing it leads to."""
    ws = consent["workspaces"]
    where = (ws[0] if len(ws) == 1 else f"{len(ws)} approved workspaces") if ws \
        else "the run's workspace"
    if offer == ONCE:
        return "Allow once", "Only this operation; the next one like it is asked again."
    if offer == TOOL:
        return (f"Allow {op.tool_label} for this run",
                f"Every {op.tool_label} operation inside {where} proceeds until "
                f"this run ends; anything outside is still asked.")
    if offer == TASK:
        cats = ", ".join(consent["categories"] if consent["mode"] in (_consent.TASK, _consent.ALL)
                         else DEFAULT_CATEGORIES)
        if op.offer_workspace and not op.within:
            return (f"Allow within this task, adding {op.offer_workspace}",
                    f"Adds {op.offer_workspace} to the task's workspaces; routine "
                    f"work there ({cats}) proceeds for the rest of this task, "
                    f"including work it delegates. Anything else is still asked.")
        return ("Allow within this task",
                f"Routine work ({cats}) inside {where} proceeds without asking for "
                f"the rest of this task, including work it delegates. Anything "
                f"else is still asked.")
    if offer == RESEARCH_TASK:
        return ("Allow web research for this task",
                "Public web searches and public pages read with the runtime's own web "
                "tool proceed for the rest of this task, including work it delegates. "
                "Shell network commands, uploads and logins are still asked.")
    return "Deny", f"Refuse this operation; {alias} is told it was refused."


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


class Decision:
    """What the policy answers one request with, before anything is written:
    `outcome` is "allow", "deny" or "ask" (the owner); `by` names the
    authority for an allow or deny (grant, research, all, task, tool, deny)."""

    __slots__ = ("outcome", "by", "op", "consent", "workspace")

    def __init__(self, outcome, by, op, consent, workspace):
        self.outcome, self.by, self.op = outcome, by, op
        self.consent, self.workspace = consent, workspace

    def __repr__(self):
        return f"Decision({self.outcome!r}, {self.by!r}, {self.op.summary!r})"


def decide(request: dict, *, workspace: str | None, consent: dict,
           pending=None) -> Decision:
    """THE POLICY'S VERDICT, AS A PURE FUNCTION of the request, the run's
    workspace, its consent (`consent.of_run`) and -- read only when an edit
    rests on the run's standing allowance -- the carrier's pending Workflow
    change (`pending`: a callable returning it or None, or the value). It
    reads nothing else and writes nothing: the live policy and the replay
    (`tools/permission_replay.py`) both call it.

    `op.why` gets only what the decision itself adds (the pending change);
    the words of the task are the asker's to add (`_task_words`)."""
    cats = (consent["categories"] if consent["mode"] in (_consent.TASK, _consent.DENY, _consent.ALL)
            else list(DEFAULT_CATEGORIES))
    command_cwd = request.get("shell_cwd") if "shell_cwd" in request else workspace
    op = describe(request, cwd=command_cwd, workspaces=consent["workspaces"],
                  categories=cats, run_workspace=workspace,
                  shell=request.get("shell"))

    standing = standing_answer(request, workspace)
    # A CARRIER'S WORKFLOW CHANGE AUTHORISES NO IMPLEMENTATION (owner
    # ruling 2026-10-29), held here, where each operation is decided:
    # while one is pending, the run's implicit allowance to edit in its own
    # workspace does not apply, so an edit proceeds only under the consent
    # the owner gave, and is otherwise asked or refused below. Reads are
    # untouched. See `workflow_change.pending_carrier_change`.
    if standing is not None and not read_only(op):
        change = pending() if callable(pending) else pending
        if change:
            standing = None
            op.why = ((op.why + " -- ") if op.why else "") + (
                "this work's Workflow was changed by its carrier "
                f"({change['id']}); a Workflow change authorises no edits")
    protected = any("protected location" in o for o in op.outside)
    allow = _allow_once(request)

    def out(outcome, by):
        return Decision(outcome, by, op, consent, workspace)

    if allow is not None and not protected and (
            standing is not None or op.category == "mentis" or read_only(op)):
        return out("allow", "grant")
    # PUBLIC WEB RESEARCH THE OWNER'S REQUEST ASKED FOR: a read-only search
    # or public page through the runtime's own web tool, whatever the
    # consent mode. Nothing else on the network (`operations.research_of`).
    if allow is not None and op.category == RESEARCH             and (consent.get("research") or {}).get("authorized"):
        return out("allow", "research")
    # APPROVE ALL, chosen by the owner: whatever the runtime asks, the
    # protected locations included, is allowed and recorded as theirs.
    if allow is not None and consent["mode"] == _consent.ALL:
        return out("allow", "all")
    if allow is not None and consent["mode"] in (_consent.TASK, _consent.DENY) and op.within:
        return out("allow", "task")
    if allow is not None and op.tools and op.in_workspaces and not protected             and set(op.tools) <= set(consent["tools"])             and all(c in (*cats, "other") for c in (op.parts or [op.category])):
        return out("allow", "tool")
    if consent["mode"] == _consent.DENY:
        return out("deny", "deny")
    return out("ask", None)


def make_policy(st):
    """The policy `MentisService.permission_policy` calls for every request.

    AUTOMATIC ANSWERS ARE RECORDED BEHIND THE ANSWER: an allow by the run's
    grant, the owner's consent or Approve All goes to an ordered write-behind
    queue (`_Audit`), drained continuously and waited for at the run's end
    (`policy.flush`) and at exit. A refusal and everything the owner answers
    is written before the run hears it, in the same order."""
    audit = _audit_for(st.cv)
    from mentis.web import compiled_runs
    compiled_runs.attach(st.cv, st)

    def policy(run, instance, request, obs):
        cv = st.cv
        try:
            workspace = st.agents.agents_observe(instance).workspace
        except Exception:                                 # noqa: BLE001
            workspace = None
        start = cv._act(run)
        workspace = workspace or ((start or {}).get("detail") or {}).get("workspace")
        consent = _consent.of_run(cv, run, workspace=workspace)

        def pending():
            from mentis.conversation.workflow_change import pending_carrier_change
            return pending_carrier_change(cv, (start or {}).get("caused_by"))

        d = decide(request, workspace=workspace, consent=consent, pending=pending)
        op = d.op
        # A RUN BEING STOPPED FOR STALE RULES is refused everything it asks
        # until it stops (`compiled_runs`): its consent was narrowed.
        if compiled_runs.halting(cv, run):
            compiled_runs.nudge(cv, run)
            audit.record(start, op, "refused", "stale-rules", run=run, wait=True)
            return None
        if d.outcome == "allow":
            audit.record(start, op, "allowed", d.by, run=run, wait=False)
            return _allow_once(request)
        if d.outcome == "deny":
            audit.record(start, op, "refused", "deny", run=run, wait=True)
            return None
        words = _task_words(cv, start)
        if words:
            op.why = words + ((" -- " + op.why) if op.why else "")
        return _ask_owner(st, cv, run, request, obs, op, consent, start)

    def observe_event(run, kind, data, at):
        """A run's tool calls, recorded as they are seen, for a run whose
        compiled rules MARS applied (`operations-observed`, batched)."""
        compiled_runs.nudge(st.cv, run)
        if kind not in ("tool_call", "tool_call_update"):
            return
        held = compiled_runs.tracked(st.cv).get(run)
        if not held or not effective_allows(held.get("rules"), held.get("mode")):
            return
        audit.observe(cv_start(run), run, data, at)

    def cv_start(run):
        return st.cv._act(run)

    def end_of_run(run, consent, tool_calls, evidence):
        """At the run's end, before its end act: every answer and observed
        call written -- or, past `FLUSH_S`, the end act says how many were
        not -- and for a run handed compiled rules, `evidence["audit"]`."""
        audit.observed_flush(run)
        done = audit.flush(run, timeout=FLUSH_S)
        audit.end_run(run)
        compiled_runs.untrack(st.cv, run)
        asked = audit.answered.pop(run, 0)
        if not done and isinstance(evidence, dict):
            evidence["permission_records_unwritten"] = audit.pending()
        rules = (consent or {}).get("runtime_rules") if isinstance(consent, dict) else None
        if rules and isinstance(evidence, dict):
            evidence["audit"] = audit_of(rules, tool_calls, answered=asked,
                                         mode=(consent or {}).get("mode"))

    def before_open_(run, workspace, told):
        before_open(st.cv, run, workspace, told)

    policy.flush = audit.flush
    policy.end_of_run = end_of_run
    policy.observe_event = observe_event
    policy.before_open = before_open_
    policy.audit = audit
    return policy


#: How long a run's end waits for its permission records before it is
#: written anyway, saying how many were not.
FLUSH_S = 60.0


def effective_allows(rules, mode) -> list:
    from mentis.permission_rules import effective
    return effective(rules, "task" if mode == "task" else mode)["allow"]


def audit_of(rules: dict, tool_calls, *, answered: int, mode=None) -> dict:
    """WHAT A RUN UNDER COMPILED RULES DID, for its end act (`detail.audit`).

    Its tool calls, as MARS reported them (the ACP `tool_call` updates),
    counted by kind and by how they ended; how many permission requests
    still reached Mentis (each recorded as `operation-answered`); and the
    rules as MARS applied them (`permission_rules.effective`: allow only
    under `task`, which is what MARS hears for Approve All; deny as `ask`).
    Each call was also recorded as it was seen (`operations-observed`)."""
    from mentis.permission_rules import effective
    eff = effective(rules, mode)
    calls = [c for c in (tool_calls or ()) if isinstance(c, dict)]
    by_kind: dict = {}
    by_status: dict = {}
    for c in calls:
        k = str(c.get("kind") or "other")
        by_kind[k] = by_kind.get(k, 0) + 1
        st_ = str(c.get("status") or "unknown")
        by_status[st_] = by_status.get(st_, 0) + 1
    return {"compiled_rules": {"allow": len(rules.get("allow") or ()),
                               "deny": len(rules.get("deny") or ())},
            "applied": {"allow": len(eff["allow"]), "ask": len(eff["ask"]),
                        "refuse": len(eff["refuse"])},
            "tool_calls": len(calls), "by_kind": by_kind, "by_status": by_status,
            "asked_mentis": answered,
            "decided_by_runtime_rules_at_most": (max(len(calls) - answered, 0)
                                                 if eff["allow"] else 0)}


def _task_words(cv, start) -> str | None:
    """What the run was asked to do, in a line: why its operations relate."""
    exp = cv._act((start or {}).get("caused_by")) if start else None
    if not exp or not exp.get("turn"):
        return None
    try:
        got = cv._c.read([exp["turn"]])
    except Exception:                                     # noqa: BLE001
        return None
    words = " ".join(p.get("text", "") for p in
                     ((got[0].get("body") or {}).get("parts") or [] if got else [])
                     if p.get("type") == "text")
    words = " ".join(words.split())
    return ("Working on: " + (words[:157] + "…" if len(words) > 160 else words)) \
        if words else None


def _record(cv, start, op, answer, by, form=None) -> None:
    """Record an answer before the run hears it, in order behind every
    automatic answer still being written (`_Audit`)."""
    _audit_for(cv).record(start, op, answer, by, form=form, wait=True)


def _write(cv, start, op, answer, by, form=None) -> None:
    if not start:
        return
    summary, hit1 = redact_flag(op.summary)
    command, hit2 = redact_flag(op.command or "")
    try:
        cv.record_act(actor=start["actor"], act=_consent.ANSWERED,
                      conversation=start.get("conversation"), turn=start.get("turn"),
                      execution=start.get("execution"), runtime=start.get("runtime"),
                      caused_by=start["id"],
                      because=f"{answer} by {by}: {summary}"[:300],
                      detail={"operation": {
                                  "summary": summary, "category": op.category,
                                  "tool": op.tool, "tool_label": op.tool_label,
                                  "within": op.within, "outside": op.outside[:3],
                                  "resources": op.resources[:5],
                                  "command": command[:2000] or None,
                                  "cwd": op.cwd},
                              "answer": answer, "by": by,
                              **({"redacted": True} if hit1 or hit2 else {}),
                              **({"form": form} if form else {})})
    except Exception:                                     # noqa: BLE001
        pass                  # recording an answer never blocks the answer


OBSERVED = "operations-observed"

import threading  # noqa: E402

from mentis.redaction import redact, redact_flag  # noqa: E402,F401


def _write_observed(cv, start, calls, batch) -> None:
    """What a run under compiled rules did, as it was seen: its tool calls,
    in the order MARS reported them. Allowed by the rules the runtime was
    handed, or answered by Mentis (then also recorded as answered)."""
    if not start:
        return
    try:
        cv.record_act(actor=start["actor"], act=OBSERVED,
                      conversation=start.get("conversation"), turn=start.get("turn"),
                      execution=start.get("execution"), runtime=start.get("runtime"),
                      caused_by=start["id"],
                      because=f"{len(calls)} tool calls seen while the run worked "
                              f"under compiled permission rules (batch {batch})",
                      detail={"calls": calls, "batch": batch})
    except Exception:                                     # noqa: BLE001
        pass


class _Audit:
    """THE ORDERED WRITE-BEHIND QUEUE for `operation-answered` acts.

    One per record (`_audit_for`), one writer thread, first in first out, so
    the record holds the answers in the order they were given. An automatic
    answer (grant, research, Approve All, task consent, a tool allowed for
    the run) is queued and the run is answered at once; a refusal and every
    answer the owner gave are queued and WAITED FOR, so they are written
    before the run hears them and after everything queued before them.

    WHEN IT IS WRITTEN. The writer drains continuously; `flush` waits for
    everything queued so far. It is called when a run ends, before its end
    act is written (`MentisService.agents_perform`), before any reader of a
    run's answers (`consent.answered`), and at exit.

    IF THE PROCESS DIES. Automatic answers given but not yet written are
    lost -- at most the few the writer had not reached, normally none, since
    it starts on each at once. They were allowed under authority the record
    already holds, and what the run did is still on its end act
    (`tool_calls`). Nothing the owner answered, and no refusal, can be lost
    this way: those are written before the run is answered."""

    IDLE_S = 2.0

    def __init__(self, cv):
        import threading
        from collections import deque
        self._cv = cv
        self._q = deque()
        self._cond = threading.Condition()
        self._queued = 0          # items ever queued
        self._written = 0         # items ever written (or failed), in order
        self._thread = None
        self.answered: dict = {}  # run -> answers given (for its audit)
        self._observed: dict = {}  # run -> tool calls seen, not yet queued

    #: A run's observed tool calls are written every this many seconds or
    #: this many calls, whichever comes first, and at its end.
    OBSERVED_S, OBSERVED_N = 10.0, 50

    def record(self, start, op, answer, by, *, run=None, form=None, wait=False):
        run = run or (start or {}).get("id")
        with self._cond:
            if run:
                self.answered[run] = self.answered.get(run, 0) + 1
        self._enqueue(lambda: _write(self._cv, start, op, answer, by, form), wait=wait)

    def observe(self, start, run, data, at) -> None:
        """One tool-call event of a run under compiled rules: buffered, and
        written in order (`operations-observed`) every `OBSERVED_S` seconds
        or `OBSERVED_N` calls. A crash loses at most that much; the end act
        still lists every call (`tool_calls`)."""
        cid = (data or {}).get("tool_call_id") or (data or {}).get("toolCallId")
        if not cid:
            return
        with self._cond:
            buf = self._observed.setdefault(run, {"calls": {}, "since": time.time(),
                                                   "start": start, "batch": 0})
            call = buf["calls"].setdefault(cid, {"id": cid, "first_at": at})
            for k in ("kind", "title", "status"):
                if data.get(k) is not None:
                    value, hit = redact_flag(str(data[k]))
                    call[k] = value[:300]
                    if hit:
                        call["redacted"] = True
            locs = [loc.get("path") for loc in data.get("locations") or ()
                    if isinstance(loc, dict) and loc.get("path")]
            if locs:
                call["paths"] = locs[:5]
            due = (len(buf["calls"]) >= self.OBSERVED_N
                   or time.time() - buf["since"] >= self.OBSERVED_S)
            # AND ON A CLOCK, so a run that goes quiet is not left unwritten.
            if not due and not buf.get("timer"):
                t = threading.Timer(self.OBSERVED_S, self.observed_flush, args=(run,))
                t.daemon = True
                buf["timer"] = t
                t.start()
        if due:
            self.observed_flush(run)

    def observed_flush(self, run) -> None:
        """Queue the run's buffered calls as one `operations-observed` act."""
        with self._cond:
            buf = self._observed.get(run)
            if not buf or not buf["calls"]:
                return
            calls = list(buf["calls"].values())
            buf["calls"], buf["since"] = {}, time.time()
            timer, buf["timer"] = buf.get("timer"), None
            if timer is not None:
                timer.cancel()
            buf["batch"] += 1
            start, batch = buf["start"], buf["batch"]
        self._enqueue(lambda: _write_observed(self._cv, start, calls, batch))

    def end_run(self, run) -> None:
        with self._cond:
            buf = self._observed.pop(run, None)
        if buf and buf.get("timer"):
            buf["timer"].cancel()

    def _enqueue(self, fn, *, wait=False):
        import threading
        with self._cond:
            self._queued += 1
            mine = self._queued
            self._q.append(fn)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._drain, daemon=True,
                                                name="permission-audit")
                self._thread.start()
            self._cond.notify_all()
            if wait:
                while self._written < mine:
                    self._cond.wait(1.0)

    def _drain(self):
        import threading
        while True:
            with self._cond:
                if not self._q:
                    self._cond.wait(self.IDLE_S)
                if not self._q:
                    if self._thread is threading.current_thread():
                        self._thread = None
                    return
                item = self._q[0]
            try:
                item()
            except Exception:                             # noqa: BLE001
                pass              # a record that failed never stops the next
            finally:
                with self._cond:
                    self._q.popleft()
                    self._written += 1
                    self._cond.notify_all()

    def flush(self, run=None, timeout: float = 60.0) -> bool:
        """Wait until everything queued so far is written. True when it is."""
        deadline = time.time() + timeout
        with self._cond:
            target = self._queued
            while self._written < target:
                left = deadline - time.time()
                if left <= 0:
                    return False
                self._cond.wait(min(left, 1.0))
        return True

    def pending(self) -> int:
        with self._cond:
            return self._queued - self._written


_AUDITS: "list" = []


def _audit_for(cv) -> _Audit:
    got = getattr(cv, "_permission_audit", None)
    if got is None:
        import weakref
        got = _Audit(cv)
        try:
            cv._permission_audit = got
        except Exception:                                 # noqa: BLE001
            return got
        _AUDITS.append(weakref.ref(got))
    return got


def flush_all(timeout: float = 30.0) -> None:
    """Write every queued answer of every record (at exit, and on shutdown)."""
    for ref in list(_AUDITS):
        a = ref()
        if a is not None:
            a.flush(timeout=timeout)


def _flush_before_read(cv, run=None) -> None:
    got = getattr(cv, "_permission_audit", None)
    if got is not None:
        got.flush()


import atexit as _atexit  # noqa: E402
_atexit.register(flush_all)
_consent.BEFORE_READ.append(_flush_before_read)


def _after_consent_set(cv, run=None, act=None) -> None:
    from mentis.web import compiled_runs
    compiled_runs.after_set(cv, run, act)


_consent.AFTER_SET.append(_after_consent_set)


def _ask_owner(st, cv, run, request, obs, op, consent, start):
    from mentis.conversation.owner import _owner
    from mentis.worker import NotPermitted, _decision_form
    # NOWHERE TO ASK IS A REFUSAL: a form on no post would be the run's
    # pending form, which its own later decisions join (`worker`).
    allow, reject = _allow_once(request), _reject(request)
    if start is None or not start.get("caused_by") or not start.get("turn") \
            or allow is None:
        _record(cv, start, op, "refused", "unanswered")
        return None
    actor = start["actor"]
    alias = cv.alias(actor) or "the agent"
    choices = offers(op, consent)
    labels: dict[str, str] = {}
    shown = []
    for c in choices:
        label, then = _words(op, consent, c, alias)
        labels[label] = c
        shown.append({"label": label, "consequence": then})

    def act(name, **kw):
        kw.setdefault("caused_by", start["caused_by"])
        return cv.record_act(actor=actor, act=name, execution=start.get("execution"),
                             runtime=start.get("runtime"), **kw)

    question = f"{alias} asks to {_lower_first(op.summary)}"
    if not op.within and op.outside:
        question += f" (outside this task: {op.outside[0]})"
    question = question[:480] + "?"
    operation = {**op.to_json(), "offers": choices}
    try:
        got = _decision_form(
            cv, {"because": "the agent asked permission for this while it works",
                 "questions": [{"question": question,
                                "because": "the agent asked permission for this "
                                           "while it works; it waits for your answer",
                                "options": shown}],
                 "on": start["turn"]},
            actor=actor, parent=start["caused_by"], here=start.get("conversation"),
            wrote=None, act=act, where=lambda c: c,
            form_detail={"permission": True, "run": run,
                         "tool": {"title": op.summary, "kind": op.kind},
                         "operation": operation},
            execution=start.get("execution"))
    except NotPermitted:
        _record(cv, start, op, "refused", "unanswered")
        return None
    form = got["form"]
    waiting = obs.setdefault("permissions", {}) if obs is not None else {}
    waiting[form] = {"form": form, "decision": got["expectation"],
                     "title": op.summary, "summary": op.summary,
                     "kind": op.kind, "asked_at": time.time(),
                     "options": list(labels),
                     "conversation": start.get("conversation"),
                     "post": got.get("post")}
    # THE CLOCK STARTED WHEN MARS ASKED (`asked_at`, set on the event loop),
    # not when a thread was free to wait: MARS gives up at 1800 s whatever.
    asked = request.get("asked_at") or time.time()
    deadline = asked + WAIT_S
    settled = False

    def taken():
        """What the owner's act on the question says now, or None."""
        q = (cv.decision_form(form) or {}).get("questions") or []
        if q and q[0].get("answer"):
            said = (q[0]["answer"].get("label") or "").strip()
            chosen = next((c for k, c in labels.items()
                           if k.casefold() == said.casefold()), None)
            return ("answer", _apply(cv, run, start, op, consent, chosen, allow,
                                     reject, form, _owner(cv)))
        if q and q[0].get("withdrawn"):
            _record(cv, start, op, "refused", "owner", form)
            return ("withdrawn", None)
        return None

    try:
        lapse = "timed-out"
        while time.time() < deadline:
            if obs is not None and (obs.get("stop") or obs.get("ended_at")):
                lapse = "run-stopped" if obs.get("stop") else "run-ended"
                break
            got = taken()
            if got:
                settled = True
                return got[1]
            slow = time.time() - asked > POLL_SLOWS_AFTER_S
            time.sleep(min(POLL_LATER_S if slow else POLL_S, max(deadline - time.time(), 0.01)))
        # NOTHING WILL CONSUME AN ANSWER NOW, so the question stops asking --
        # retired BEFORE the run is told no. An answer that landed after the
        # last look is under the same write lock first: the retirement then
        # writes nothing, and that answer is the one the run gets.
        retired = _retire(cv, form, lapse, run)
        settled = True
        if not retired:
            got = taken()
            if got:
                return got[1]
        _record(cv, start, op, "refused", "unanswered", form)
        return None
    finally:
        waiting.pop(form, None)
        # A WAIT THAT FAILED (the record unreadable mid-wait, say) still
        # leaves no question asking: the run is refused by MARS either way.
        if not settled:
            try:
                _retire(cv, form, "wait-failed", run)
            except Exception:
                pass


def _retire(cv, form, reason, run) -> list[str]:
    drawn = cv.decision_form(form) or {}
    return [a for a in (cv.retire_permission_question(
                q["expectation"], reason=reason, run=run)
            for q in drawn.get("questions") or [] if q.get("open")) if a]


def retire_unconsumable(cv) -> list[str]:
    """At a server's start: close every run permission question still open.

    DEFINITE, NOT A GUESS. Only the wait that asked a question can take its
    answer, and that wait is a thread of the server that asked it. This runs
    while this server holds the Brain's one serving lock
    (`spine.brainlock`) and before it starts any run, so no wait of any
    server exists: every open permission question was left by a server
    that is gone, mid-wait or killed. Every other decision is left as it is.
    Returns the `expectation-met` acts written.

    WHO MAY CALL IT: only the server holding that lock, before it installs
    `make_policy` for any run (`web.serve`)."""
    return [a for a in (cv.retire_permission_question(e, reason="server-restarted")
                        for e in cv.open_permission_questions()) if a]


def _apply(cv, run, start, op, consent, chosen, allow, reject, form, owner):
    """The owner's answer, carried out: what it allows from now on is
    recorded as consent, and this request is answered `allow_once`."""
    if chosen is None or chosen == DENY:
        _record(cv, start, op, "refused", "owner", form)
        return reject if chosen == DENY else None
    if chosen == TOOL and owner:
        _consent.set_run_tools(cv, run, owner=owner, allow=op.tools,
                               because=f"allowed {op.tool_label} for this run, "
                                       f"answering {form}")
    if chosen == RESEARCH_TASK and owner:
        _consent.set_research(cv, run, owner=owner, on=True,
                              because=f"allowed web research for this task, answering {form}")
    if chosen == TASK and owner:
        ws = list(consent["workspaces"])
        if op.offer_workspace and op.offer_workspace not in ws:
            ws.append(op.offer_workspace)
        cats = (consent["categories"] if consent["mode"] == _consent.TASK
                else list(DEFAULT_CATEGORIES))
        _consent.set_task(cv, run, owner=owner,
                          consent={"mode": _consent.TASK, "workspaces": ws,
                                   "categories": cats},
                          because=f"allowed routine work within this task, "
                                  f"answering {form}")
    _record(cv, start, op, "allowed", "owner", form)
    return allow
