"""Run consent -- the owner's, on a request and its runs (docs/run-consent.md).

Which of an agent's operations need asking. It belongs to the request the
owner authorised, carries down every request delegated under it, and is
narrowed there, never widened: a child works in its parent's workspaces and
its parent's categories or fewer. The owner may change it later -- on the
task (`consent-set`, caused by the request) or for one run (`consent-set`
with `scope: "run"`, caused by the run's start act, which is how "allow this
tool for this run" is held). Read from the record every time; nothing here is
cached or stored anywhere else.

IT IS NOT TASK GRAVITY. `follow_up` says whether side work may be pursued;
this says which operations of the work proceed without a question. Neither
reads the other.

AN AGENT CANNOT GIVE ITSELF CONSENT. A consent written on a request somebody
other than the owner recorded only narrows what that request inherited; a
lineage that reaches no owner-given consent is `ask`.
"""

from __future__ import annotations

import os
import re

from mentis.operations import (CATEGORIES, DEFAULT_CATEGORIES, inside,
                               is_protected, protected_roots)

ASK, TASK, DENY, ALL = "ask", "task", "deny", "all"
MODES = (ASK, TASK, DENY, ALL)
SET = "consent-set"
ANSWERED = "operation-answered"

LABELS = {
    ASK: "Each operation the run's grant does not cover is asked",
    TASK: "Routine work in the approved workspaces proceeds",
    DENY: "Routine work in the approved workspaces proceeds; what would be asked is refused, never waiting for you",
    ALL: "Every operation is approved without asking you, including in a Brain, MARS's data and credentials",
}
#: APPROVE ALL is the owner's choice of answer, nothing more: every
#: permission request the runtime makes is allowed, and recorded as such
#: (`by: "all"`), the protected locations -- a Brain, MARS's data,
#: credentials -- included, at the owner's explicit choice (2026-10-29). It
#: gives the runtime no capability (MARS is told `task`) and grants no Mentis
#: operation: `/api/worker` still checks every one against the run's grant.


#: WHAT ASKS FOR WEB RESEARCH, in the owner's own request: the words that
#: make public web searches and public source pages intrinsic to the task
#: (docs/run-consent.md, "Research"). Matched on the owner's request only.
RESEARCH_ASKED = re.compile(
    r"\b(research(?:ing)?|cite|citations?|search (?:the )?(?:web|internet|online)|"
    r"web (?:search|research)|look (?:it |this |them |that )?up online|browse the web|"
    r"(?:your|the|with|cite|list|include|give me|and|their) sources|"
    r"latest|up[- ]to[- ]date|current (?:prices?|information|news|reviews?|models?))\b",
    re.IGNORECASE)


def _words_of(cv, level) -> str:
    """The words of the post a request was asked on."""
    turn = level.get("turn")
    got = cv._c.read([turn]) if turn else []
    parts = ((got[0].get("body") or {}).get("parts") or []) if got else []
    return " ".join(p.get("text") or "" for p in parts if isinstance(p, dict))


def research_of(cv, expectation) -> dict:
    """Whether this request authorizes public web research, and why.

    BY THE OWNER'S OWN REQUEST, read from its words; carried down every
    request delegated under it and never added below it: an agent's request
    cannot give itself research. The owner may turn it off (or on) for the
    task with a `consent-set` carrying `research`. It permits only research
    operations (`operations.research_of`): read-only public web searches and
    public pages through the runtime's own web tool -- never a shell network
    command, an upload, a login or anything run."""
    from mentis.conversation.owner import _owner
    owner = _owner(cv)
    out = {"authorized": False, "because": None, "source": None, "at": None}
    for level in reversed(_lineage(cv, expectation)):
        changed = [a for a in (_owner_sets(cv, level["id"], owner, "task") if owner else [])
                   if "research" in (a.get("detail") or {})]
        if changed:
            on = bool(changed[-1]["detail"]["research"])
            out = {"authorized": on, "because": "you changed it" if on else None,
                   "source": "owner-changed", "at": level["id"]}
        elif out["source"] is None and owner and level.get("actor") == owner:
            m = RESEARCH_ASKED.search(_words_of(cv, level))
            if m:
                out = {"authorized": True, "because": m.group(0), "source": "request",
                       "at": level["id"]}
    return out


def consent_value(raw, *, roots=None) -> dict | None:
    """The owner's consent as recorded, or ValueError in words. None (and
    `{"mode": "ask"}` with nothing else) is the default and stores nothing."""
    if raw in (None, ASK):
        return None
    if isinstance(raw, str):
        raw = {"mode": raw}
    if not isinstance(raw, dict):
        raise ValueError('consent is {"mode": "ask"|"task"|"deny"|"all", '
                         '"workspaces": [...], "categories": [...]}')
    mode = raw.get("mode", TASK)
    if mode not in MODES:
        raise ValueError(f'consent mode is "ask", "task", "deny" or "all", not {mode!r}')
    workspaces = _workspaces(raw.get("workspaces"), roots=roots)
    cats = raw.get("categories")
    if cats is None:
        categories = list(DEFAULT_CATEGORIES)
    else:
        if not isinstance(cats, list) or not all(isinstance(c, str) for c in cats):
            raise ValueError("consent categories is a list of names")
        bad = [c for c in cats if c not in CATEGORIES]
        if bad:
            raise ValueError(f"unknown consent categories {bad}; they are "
                             f"{', '.join(CATEGORIES)}")
        categories = list(dict.fromkeys(cats))
    if mode == ASK and not workspaces and categories == list(DEFAULT_CATEGORIES):
        return None
    return {"mode": mode, "workspaces": workspaces, "categories": categories}


def _workspaces(raw, *, roots=None) -> list[str]:
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        raw = [p for p in raw.replace(";", "\n").splitlines()]
    if not isinstance(raw, list):
        raise ValueError("consent workspaces is a list of absolute directories")
    out = []
    roots = roots if roots is not None else protected_roots()
    home = os.path.normcase(os.path.normpath(os.path.expanduser("~")))
    for p in raw:
        if not isinstance(p, str) or not p.strip():
            continue
        p = os.path.normpath(p.strip().strip('"'))
        if not os.path.isabs(p) or not os.path.isdir(p):
            raise ValueError(f"a workspace is an existing absolute directory: {p!r}")
        if is_protected(p, roots) or any(inside(r, p) for r in roots):
            raise ValueError(f"{p!r} holds a Brain, MARS's data or credentials, "
                             f"so it cannot be a workspace")
        drive, rest = os.path.splitdrive(p)
        if rest in ("", os.sep, "/") or os.path.normcase(p) == home:
            raise ValueError(f"{p!r} is a whole drive or the home directory, "
                             f"not a workspace")
        if p not in out:
            out.append(p)
    return out


def _narrow(outer: dict, inner: dict) -> dict:
    """What `inner` may have under `outer`: the less permissive mode, its
    workspaces that lie inside outer's, the categories both allow."""
    rank = {DENY: 0, ASK: 1, TASK: 2, ALL: 3}
    mode = min(outer["mode"], inner["mode"], key=rank.__getitem__)
    ws = [w for w in inner.get("workspaces") or ()
          if any(inside(w, o) for o in outer.get("workspaces") or ())] \
        or list(outer.get("workspaces") or ())
    cats = [c for c in inner.get("categories") or DEFAULT_CATEGORIES
            if c in (outer.get("categories") or ())]
    return {"mode": mode, "workspaces": ws, "categories": cats}


def _lineage(cv, expectation) -> list[dict]:
    """The request and every request above it, origin last."""
    out, cur, seen = [], expectation, set()
    while cur and cur not in seen:
        a = cv._act(cur)
        if a is None or a["act"] != "expectation-recorded":
            break
        seen.add(cur)
        out.append(a)
        cur = a.get("caused_by")
    return out


def _owner_sets(cv, cause, owner, scope) -> list[dict]:
    acts = [a for a in cv._c.operational(caused_by=cause)
            if a["act"] == SET and a.get("actor") == owner
            and ((a.get("detail") or {}).get("scope") or "task") == scope]
    order = cv._write_order([a["id"] for a in acts]) if acts else {}
    return sorted(acts, key=lambda a: (order.get(a["id"], -1), a["at"]))


def _declared(cv, act) -> str | None:
    decl = ((act.get("detail") or {}).get("repository"))
    where = decl if isinstance(decl, str) else (
        decl.get("path") if isinstance(decl, dict) else None)
    return os.path.normpath(where) if where and os.path.isabs(where) \
        and os.path.isdir(where) else None


def of_request(cv, expectation) -> dict:
    """The consent in force for this request: {mode, workspaces, categories,
    source, granted_at}. `granted_at` is the request where the owner gave or
    last changed it (None when nobody did)."""
    from mentis.conversation.owner import _owner
    owner = _owner(cv)
    eff, source, granted_at = None, "none", None
    for level in reversed(_lineage(cv, expectation)):
        detail = level.get("detail") or {}
        here = None
        try:
            here = consent_value(detail.get("consent"), roots=[]) \
                if detail.get("consent") is not None else None
        except ValueError:
            here = None
        # A REQUEST THAT SAYS "ask" NARROWS to it: `consent_value` stores
        # nothing for the default, but said below a wider consent it is a
        # narrowing (a delegated request under Approve All or routine work).
        if here is None and detail.get("consent") is not None and eff is not None:
            raw = detail["consent"]
            if raw == ASK or (isinstance(raw, dict) and raw.get("mode") == ASK):
                here = {"mode": ASK, "workspaces": [], "categories": list(DEFAULT_CATEGORIES)}
        changed = [a for a in (_owner_sets(cv, level["id"], owner, "task") if owner else [])
                   if "consent" in (a.get("detail") or {})]
        if changed:
            last = (changed[-1].get("detail") or {}).get("consent") or {}
            eff = {"mode": last.get("mode", ASK),
                   "workspaces": list(last.get("workspaces") or ()),
                   "categories": list(last.get("categories") or DEFAULT_CATEGORIES)}
            source, granted_at = "owner-changed", level["id"]
        elif here is not None and level.get("actor") == owner and owner:
            eff = dict(here)
            source, granted_at = "request", level["id"]
        elif here is not None and eff is not None:
            eff = _narrow(eff, here)
            source = "narrowed"
        elif eff is not None:
            source = "inherited"
        if eff is not None and level["id"] == granted_at:
            repo = _declared(cv, level)
            if repo and repo not in eff["workspaces"]:
                eff["workspaces"] = [*eff["workspaces"], repo]
    research = research_of(cv, expectation)
    if eff is None:
        return {"mode": ASK, "workspaces": [], "categories": list(DEFAULT_CATEGORIES),
                "source": "none", "granted_at": None,
                "label": _label(ASK, research), "research": research}
    return {**eff, "source": source, "granted_at": granted_at,
            "label": _label(eff["mode"], research), "research": research}


def _label(mode, research) -> str:
    return LABELS[mode] + ("; public web research for this task proceeds"
                           if research and research.get("authorized") else "")


def of_run(cv, run, *, workspace: str | None = None) -> dict:
    """The consent in force for one run: its request's, the tools the owner
    allowed for this run, and the workspaces it is checked against. The
    run's own workspace counts when its request is where consent was given;
    a delegated child's counts only inside the workspaces it inherited."""
    from mentis.conversation.owner import _owner
    start = cv._act(run)
    exp = (start or {}).get("caused_by")
    workspace = workspace or ((start or {}).get("detail") or {}).get("workspace")
    got = of_request(cv, exp) if exp else {
        "mode": ASK, "workspaces": [], "categories": list(DEFAULT_CATEGORIES),
        "source": "none", "granted_at": None, "label": LABELS[ASK],
        "research": {"authorized": False, "because": None, "source": None, "at": None}}
    ws = list(got["workspaces"])
    if workspace and (got["granted_at"] == exp or got["source"] == "none"
                      or any(inside(workspace, w) for w in ws)):
        if workspace not in ws:
            ws.insert(0, workspace)
    tools: list[str] = []
    owner = _owner(cv)
    for a in (_owner_sets(cv, run, owner, "run") if owner and start else []):
        d = a.get("detail") or {}
        for t in d.get("allow_tools") or ():
            if t not in tools:
                tools.append(t)
        for t in d.get("revoke_tools") or ():
            if t in tools:
                tools.remove(t)
    end = cv.run_end(run) if start else None
    applied = ((((end or {}).get("detail") or {}).get("runtime_evidence") or {})
               .get("consent_applied"))
    return {**got, "workspaces": ws, "tools": tools, "run": run,
            "applied": applied}


def set_task(cv, run, *, owner, consent: dict, because: str) -> str:
    """The owner changes a task's consent for its later operations."""
    start = cv._act(run)
    exp = (start or {}).get("caused_by")
    if not exp:
        raise ValueError(f"{run!r} carries no request, so it has no task consent")
    return cv.record_act(actor=owner, act=SET, conversation=start.get("conversation"),
                         turn=start.get("turn"), execution=start.get("execution"),
                         runtime=start.get("runtime"), caused_by=exp,
                         because=because,
                         detail={"scope": "task", "run": run, "consent": consent})


def set_research(cv, run, *, owner, on: bool, because: str) -> str:
    """The owner turns public web research on or off for a run's task."""
    start = cv._act(run)
    exp = (start or {}).get("caused_by")
    if not exp:
        raise ValueError(f"{run!r} carries no request, so it has no task consent")
    return cv.record_act(actor=owner, act=SET, conversation=start.get("conversation"),
                         turn=start.get("turn"), execution=start.get("execution"),
                         runtime=start.get("runtime"), caused_by=exp,
                         because=because,
                         detail={"scope": "task", "run": run, "research": bool(on)})


def set_run_tools(cv, run, *, owner, allow=(), revoke=(), because: str) -> str:
    """The owner allows or revokes tools for this run only."""
    start = cv._act(run)
    if start is None:
        raise ValueError(f"{run!r} is not a recorded run")
    return cv.record_act(actor=owner, act=SET, conversation=start.get("conversation"),
                         turn=start.get("turn"), execution=start.get("execution"),
                         runtime=start.get("runtime"), caused_by=run,
                         because=because,
                         detail={"scope": "run", "allow_tools": list(allow),
                                 "revoke_tools": list(revoke)})


def answered(cv, run) -> list[dict]:
    """Every permission request of this run answered, oldest first."""
    acts = [a for a in cv._c.operational(caused_by=run) if a["act"] == ANSWERED]
    order = cv._write_order([a["id"] for a in acts]) if acts else {}
    acts.sort(key=lambda a: (order.get(a["id"], -1), a["at"]))
    return [{"id": a["id"], "at": a["at"], **(a.get("detail") or {})} for a in acts]
