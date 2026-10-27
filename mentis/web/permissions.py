"""Who answers an agent's permission request, when MARS forwards one.

MARS forwards every `session/request_permission` from a backend unchanged and
never picks an allow option itself (MARS docs/API.md, Permissions). Mentis
used to answer every one "allow once". Now each request is answered under
Mentis's own authority, in one of two ways, and nothing else:

  1. BY THE RUN'S GRANT, for what the run was already given: reading
     (`read`, `search`, `think`) anywhere it can reach, and editing files
     inside the workspace the run was asked to work in. That is the work it
     was handed; asking the owner each time would only teach them to click.
  2. BY THE OWNER, for everything else -- running commands, deleting,
     fetching, editing outside the workspace, anything a backend names that
     is not above. The request becomes an ordinary DECISION FORM on the post
     the run is working on (`worker._decision_form`, the same machinery
     `request_decision` uses), owed by the owner, with the backend's own
     options as its answers. It shows in Needs You and is answered where it
     was asked, like any decision. The run waits for the answer.

FAIL CLOSED. No answer within `WAIT_S` (inside MARS's own 300 s
`permission_s`), the run stopped, or nowhere to ask (no request, no
Conversation): the request is refused with the backend's reject option. The question stays in
the record as asked -- only the owner may withdraw a decision -- and its form
names the run, so Fluid can say the run no longer waits for it.
"""

from __future__ import annotations

import os
import time

#: How long a run waits for the owner, inside MARS's permission_s (300 s).
WAIT_S = 270.0
POLL_S = 0.5
#: Tool kinds the run's grant answers wherever they point.
READS = {"read", "search", "think"}


def _inside(path: str, root: str) -> bool:
    try:
        path = os.path.normcase(os.path.realpath(path))
        root = os.path.normcase(os.path.realpath(root))
        return os.path.commonpath([path, root]) == root
    except (ValueError, OSError):
        return False


def standing_answer(request: dict, workspace: str | None) -> str | None:
    """The option the run's own grant answers with, or None for the owner."""
    tool = request.get("tool_call") or {}
    kind = tool.get("kind")
    allow = next((o["option_id"] for o in request.get("options") or ()
                  if o.get("kind") == "allow_once"), None)
    if allow is None:
        return None
    if kind in READS:
        return allow
    if kind == "edit" and workspace:
        paths = [loc.get("path") for loc in tool.get("locations") or ()
                 if isinstance(loc, dict) and loc.get("path")]
        if paths and all(_inside(p, workspace) for p in paths):
            return allow
    return None


def _question(alias: str, tool: dict) -> str:
    title = " ".join(str(tool.get("title") or tool.get("kind") or "a tool").split())
    return f"Allow {alias} to: {title[:200]}?"


def make_policy(st):
    """The policy `MentisService.permission_policy` calls for every request."""

    def policy(run, instance, request, obs):
        cv = st.cv
        try:
            workspace = st.agents.agents_observe(instance).workspace
        except Exception:                                 # noqa: BLE001
            workspace = None
        standing = standing_answer(request, workspace)
        if standing is not None:
            return standing
        return _ask_owner(st, cv, run, request, obs)

    return policy


def _ask_owner(st, cv, run, request, obs):
    from mentis.worker import NotPermitted, _decision_form
    start = cv._act(run)
    options = [o for o in request.get("options") or () if o.get("option_id")]
    if start is None or not start.get("caused_by") or len(options) < 2:
        return None
    tool = request.get("tool_call") or {}
    actor = start["actor"]
    alias = cv.alias(actor) or "the agent"
    labels: dict[str, str] = {}
    for o in options:
        label = " ".join(str(o.get("name") or o.get("kind") or o["option_id"]).split())
        base, n = label, 2
        while label.casefold() in {k.casefold() for k in labels}:
            label, n = f"{base} ({n})", n + 1
        labels[label] = o["option_id"]

    def act(name, **kw):
        kw.setdefault("caused_by", start["caused_by"])
        return cv.record_act(actor=actor, act=name, execution=start.get("execution"),
                             runtime=start.get("runtime"), **kw)

    try:
        got = _decision_form(
            cv, {"questions": [{"question": _question(alias, tool),
                                "because": "the agent asked permission for this "
                                           "while it works; it waits for your answer",
                                "options": [{"label": k} for k in labels]}],
                 **({"on": start["turn"]} if start.get("turn") else {})},
            actor=actor, parent=start["caused_by"], here=start.get("conversation"),
            wrote=None, act=act, where=lambda c: c,
            form_detail={"permission": True, "run": run,
                         "tool": {k: tool.get(k) for k in ("title", "kind")}},
            execution=start.get("execution"))
    except NotPermitted:
        return None
    form = got["form"]
    if obs is not None:
        obs["permission"] = {"form": form, "title": tool.get("title"),
                             "kind": tool.get("kind"), "asked_at": time.time(),
                             "options": list(labels),
                             "conversation": start.get("conversation"),
                             "post": got.get("post")}
    deadline = time.time() + WAIT_S
    try:
        while time.time() < deadline:
            if obs is not None and (obs.get("stop") or obs.get("ended_at")):
                break
            drawn = cv.decision_form(form)
            q = (drawn or {}).get("questions") or []
            if q and q[0].get("answer"):
                label = (q[0]["answer"].get("label") or "").strip()
                return next((oid for k, oid in labels.items()
                             if k.casefold() == label.casefold()), None)
            if q and q[0].get("withdrawn"):
                return None
            time.sleep(POLL_S)
        return None
    finally:
        if obs is not None:
            obs["permission"] = None

