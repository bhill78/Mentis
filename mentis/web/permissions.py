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

FAIL CLOSED. No answer within `WAIT_S` (inside MARS's own 300 s
`permission_s`), the run stopped, or nowhere to ask (no request, no
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

from mentis.operations import (DEFAULT_CATEGORIES, GUARDED, describe, inside,
                               is_guarded, read_only)
from mentis.operational import consent as _consent

#: How long a run waits for the owner, inside MARS's permission_s (300 s).
WAIT_S = 270.0
POLL_S = 0.5
#: Tool kinds the run's grant answers wherever they point.
READS = {"read", "search", "think"}
__all__ = ["GUARDED", "READS", "WAIT_S", "make_policy", "standing_answer"]

ONCE, TOOL, TASK, DENY = "once", "tool", "task", "deny"


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


def mars_consent(cv, run, workspace) -> dict | None:
    """What MARS is told of a run's consent: its mode and the workspaces
    beyond the one it runs in. None when the owner gave none."""
    c = _consent.of_run(cv, run, workspace=workspace)
    if c["source"] == "none":
        return None
    extra = [w for w in c["workspaces"]
             if not (workspace and os.path.normcase(os.path.normpath(w))
                     == os.path.normcase(os.path.normpath(workspace)))]
    return {"mode": c["mode"], "workspaces": extra}


def offers(op, consent) -> list[str]:
    """What the owner may answer this operation with. The wider answers only
    for an operation inside the task's boundary, consent apart."""
    out = [ONCE]
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
        cats = ", ".join(consent["categories"] if consent["mode"] == _consent.TASK
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
    return "Deny", f"Refuse this operation; {alias} is told it was refused."


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def make_policy(st):
    """The policy `MentisService.permission_policy` calls for every request."""

    def policy(run, instance, request, obs):
        cv = st.cv
        try:
            workspace = st.agents.agents_observe(instance).workspace
        except Exception:                                 # noqa: BLE001
            workspace = None
        start = cv._act(run)
        workspace = workspace or ((start or {}).get("detail") or {}).get("workspace")
        consent = _consent.of_run(cv, run, workspace=workspace)
        cats = (consent["categories"] if consent["mode"] in (_consent.TASK, _consent.DENY)
                else list(DEFAULT_CATEGORIES))
        op = describe(request, cwd=workspace, workspaces=consent["workspaces"],
                      categories=cats, run_workspace=workspace)
        op.why = _task_words(cv, start)

        standing = standing_answer(request, workspace)
        protected = any("protected location" in o for o in op.outside)
        allow = _allow_once(request)
        if allow is not None and not protected and (
                standing is not None or op.category == "mentis" or read_only(op)):
            _record(cv, start, op, "allowed", "grant")
            return allow
        if allow is not None and consent["mode"] in (_consent.TASK, _consent.DENY) and op.within:
            _record(cv, start, op, "allowed", "task")
            return allow
        if allow is not None and op.tools and op.in_workspaces and not protected \
                and set(op.tools) <= set(consent["tools"]) \
                and all(c in (*cats, "other") for c in (op.parts or [op.category])):
            _record(cv, start, op, "allowed", "tool")
            return allow
        if consent["mode"] == _consent.DENY:
            _record(cv, start, op, "refused", "deny")
            return None
        return _ask_owner(st, cv, run, request, obs, op, consent, start)

    return policy


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
    if not start:
        return
    try:
        cv.record_act(actor=start["actor"], act=_consent.ANSWERED,
                      conversation=start.get("conversation"), turn=start.get("turn"),
                      execution=start.get("execution"), runtime=start.get("runtime"),
                      caused_by=start["id"],
                      because=f"{answer} by {by}: {op.summary}"[:300],
                      detail={"operation": {
                                  "summary": op.summary, "category": op.category,
                                  "tool": op.tool, "tool_label": op.tool_label,
                                  "within": op.within, "outside": op.outside[:3],
                                  "resources": op.resources[:5],
                                  "command": (op.command or "")[:2000] or None,
                                  "cwd": op.cwd},
                              "answer": answer, "by": by,
                              **({"form": form} if form else {})})
    except Exception:                                     # noqa: BLE001
        pass                  # recording an answer never blocks the answer


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
    waiting[form] = {"form": form, "title": op.summary, "summary": op.summary,
                     "kind": op.kind, "asked_at": time.time(),
                     "options": list(labels),
                     "conversation": start.get("conversation"),
                     "post": got.get("post")}
    # THE CLOCK STARTED WHEN MARS ASKED (`asked_at`, set on the event loop),
    # not when a thread was free to wait: MARS gives up at 300 s whatever.
    deadline = (request.get("asked_at") or time.time()) + WAIT_S
    lapse = "timed-out"
    try:
        while time.time() < deadline:
            if obs is not None and (obs.get("stop") or obs.get("ended_at")):
                lapse = "run-stopped" if obs.get("stop") else "run-ended"
                break
            drawn = cv.decision_form(form)
            q = (drawn or {}).get("questions") or []
            if q and q[0].get("answer"):
                said = (q[0]["answer"].get("label") or "").strip()
                chosen = next((c for k, c in labels.items()
                               if k.casefold() == said.casefold()), None)
                return _apply(cv, run, start, op, consent, chosen, allow, reject,
                              form, _owner(cv))
            if q and q[0].get("withdrawn"):
                _record(cv, start, op, "refused", "owner", form)
                return None
            time.sleep(POLL_S)
        _record(cv, start, op, "refused", "unanswered", form)
        # NOTHING WILL CONSUME AN ANSWER NOW, so the question stops asking.
        # An answer that landed after the last look stands: the retirement
        # writes nothing then (`retire_permission_question`).
        _retire(cv, form, lapse, run)
        return None
    finally:
        waiting.pop(form, None)


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
    Returns the `expectation-met` acts written."""
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
