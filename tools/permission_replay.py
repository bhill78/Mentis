"""Permission-policy equivalence replay (experiment E3, CONTRACT.md WS-A).

Reads a Brain READ-ONLY (sqlite `mode=ro`; no Mentis Store or server is
opened on it) and, for every recorded `operation-answered` act:

  1. reconstructs the permission request from what was recorded (the
     operation's tool, command, working directory and paths);
  2. reconstructs the run's consent AS IT STOOD WHEN THE REQUEST WAS ANSWERED
     (`consent.of_run` over a view of the record cut at that act), and the
     carrier's pending Workflow change at that moment;
  3. evaluates the current policy (`permissions.decide`, pure) -> M;
  4. compiles the run's consent AS IT STOOD WHEN THE RUN STARTED -- which is
     what a runtime is handed -- into Claude rules
     (`permission_rules.compile_claude`) and evaluates the request under
     them with Claude Code's rule semantics (`permission_rules.claude_verdict`)
     -> K: allow, deny, or ask (the request reaches Mentis as today);
  5. compares. The effective verdict with compiled scope is K where a rule
     decided, else M. A disagreement is MORE PERMISSIVE when K allows what M
     (or the recorded answer R) did not allow without asking; MORE
     RESTRICTIVE when K refuses what M allowed or would have asked.

Usage:
  python tools/permission_replay.py [corpus.db] [--json out.json] [--examples N]
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mentis.operational import consent as C  # noqa: E402
from mentis.permission_rules import (ALL_CLASSES, COMPILED_CLASSES, EDIT_TOOLS,  # noqa: E402
                                     READ_TOOLS, claude_verdict, compile_claude)
from mentis.web.permissions import decide  # noqa: E402

DEFAULT_DB = r"C:\Work\Mentis-brains\pre-eff-cbfabaa-20261108\corpus.db"
#: The acts consent, lineage and Workflow-change reads look at, plus the
#: answers themselves and the ways a run ends. Readers filter by act, so a
#: view holding only these answers them as the whole record would.
KINDS = ("expectation-recorded", "execution-started", C.SET, "expectation-assigned",
         "authority-granted", C.ANSWERED, "result-returned", "delivery-failed",
         "result-recovered")
AUTO = {"grant", "research", "all", "task", "tool"}
CLAUDE_TOOLS = set(READ_TOOLS) | set(EDIT_TOOLS) | {"Bash", "PowerShell", "WebFetch",
                                                    "WebSearch"}


# ---------------------------------------------------------------------------
# the record, read-only


class Record:
    """The acts the policy reads, loaded once from a read-only connection."""

    def __init__(self, path: str):
        uri = "file:" + path.replace("\\", "/") + "?mode=ro"
        self.db = sqlite3.connect(uri, uri=True)
        self.db.row_factory = sqlite3.Row
        self.by_id: dict[str, dict] = {}
        self.seq: dict[str, int] = {}
        self.by_cause: dict[str, list[dict]] = collections.defaultdict(list)
        q = ("SELECT seq, id, at, actor, act, conversation, turn, execution, runtime, "
             "because, caused_by, about, detail FROM operational WHERE act IN (%s) "
             "ORDER BY seq" % ",".join("?" * len(KINDS)))
        for r in self.db.execute(q, KINDS):
            a = dict(r)
            s = a.pop("seq")
            a["about"] = json.loads(a["about"])
            a["detail"] = json.loads(a["detail"])
            self.by_id[a["id"]] = a
            self.seq[a["id"]] = s
            if a.get("caused_by"):
                self.by_cause[a["caused_by"]].append(a)
        owners = [r["id"] for r in self.db.execute(
            "SELECT id, body FROM entry WHERE def_name='participant' ORDER BY seq")
            if (json.loads(r["body"]) or {}).get("about") == "the owner"]
        self.owner = owners[0] if owners else None
        self._turns: dict[str, dict | None] = {}

    def turn(self, tid):
        if tid not in self._turns:
            r = self.db.execute("SELECT id, body FROM entry WHERE id=?", (tid,)).fetchone()
            self._turns[tid] = {"id": r["id"], "body": json.loads(r["body"])} if r else None
        return self._turns[tid]

    def answers(self):
        return [a for a in self.by_id.values() if a["act"] == C.ANSWERED]


class _Store:
    def __init__(self, view):
        self.v = view

    def operational(self, *, caused_by=None, id=None, **kw):
        if kw:
            raise NotImplementedError(kw)
        rec, cut = self.v.rec, self.v.cut
        if id is not None:
            a = rec.by_id.get(id)
            return [a] if a and rec.seq[a["id"]] <= cut else []
        return [a for a in rec.by_cause.get(caused_by, ()) if rec.seq[a["id"]] <= cut]

    def read(self, ids):
        return [t for t in (self.v.rec.turn(i) for i in ids) if t]


class _Corpus:
    def __init__(self, view):
        self.v = view

    def entries_of_kind(self, kind):
        assert kind == "participant"
        owner = self.v.rec.owner
        return [{"id": owner, "body": {"about": "the owner"}}] if owner else []


class View:
    """The `cv` surface consent and Workflow-change reads use, over the
    record as it stood at write position `cut` (inclusive)."""

    def __init__(self, rec: Record, cut: int):
        self.rec, self.cut = rec, cut
        self._c = _Store(self)
        self.corpus = _Corpus(self)

    def _act(self, oid):
        got = self._c.operational(id=oid) if oid else []
        return got[0] if got else None

    def _write_order(self, ids):
        return {i: self.rec.seq[i] for i in ids if i in self.rec.seq}

    def history(self, caused_by=None, **kw):
        return self._c.operational(caused_by=caused_by, **kw)

    def run_end(self, run):
        return None


# ---------------------------------------------------------------------------
# a recorded request, rebuilt

OPTS = [{"option_id": "once", "kind": "allow_once", "name": "Allow"},
        {"option_id": "no", "kind": "reject_once", "name": "Reject"}]


def reconstruct(op: dict) -> tuple[dict, list[str], list[str], str, bool]:
    """(request, claude tool names it may have been, paths, class, lossy)."""
    tool = (op.get("tool") or "").strip()
    label = op.get("tool_label") or ""
    command = op.get("command")
    resources = list(op.get("resources") or [])
    lossy = bool(command and len(command) >= 2000) or len(resources) >= 5
    if tool.startswith("mcp__"):
        req = {"tool_call": {"kind": "other", "title": tool,
                             "_meta": {"claudeCode": {"toolName": tool}}}}
        return {**req, "options": OPTS}, [tool], [], "mentis-tool", lossy
    if command is not None:
        prefix = tool.split(":", 1)[0]
        shell = prefix if prefix in ("bash", "powershell") else None
        names = {"bash": ["Bash"], "powershell": ["PowerShell"]}.get(prefix, ["Bash", "PowerShell"])
        req = {"tool_call": {"kind": "execute", "title": command,
                             "raw_input": {"command": command}},
               "shell_cwd": op.get("cwd"), "options": OPTS}
        if shell:
            req["shell"] = shell
        return req, names, [], "shell", lossy
    if op.get("category") in ("research", "network") or tool in ("webfetch", "websearch", "fetch"):
        target = resources[0] if resources else None
        raw = {"url": target} if target and "://" in target else {"query": target or ""}
        req = {"tool_call": {"kind": "fetch", "title": op.get("summary") or "", "raw_input": raw,
                             "_meta": {"claudeCode": {"toolName": label}}}, "options": OPTS}
        return req, [label] if label in CLAUDE_TOOLS else [], [], "web", lossy
    if tool in ("read", "grep", "glob", "search", "think") or op.get("category") == "read":
        kind = "read" if tool in ("read",) else "search"
        cls = "file-read"
    elif tool in ("edit", "write", "multiedit", "notebookedit") or op.get("category") == "edit":
        kind, cls = "edit", "file-edit"
    else:
        req = {"tool_call": {"kind": "other", "title": label,
                             "_meta": {"claudeCode": {"toolName": label}}}, "options": OPTS}
        return req, [label] if label in CLAUDE_TOOLS else [], resources, "other", lossy
    tc = {"kind": kind, "title": op.get("summary") or "",
          "locations": [{"path": p} for p in resources]}
    if label:
        tc["_meta"] = {"claudeCode": {"toolName": label}}
    # AN ADAPTER THAT NAMED NO TOOL (most of the record: label = the ACP
    # kind) could have been any Claude tool of that kind; the rules must give
    # every one of them the same answer for a rule to have decided it.
    names = [label] if label in CLAUDE_TOOLS else (
        list(EDIT_TOOLS) if cls == "file-edit" else
        ["Read"] if tool == "read" else ["Grep", "Glob"] if tool == "search" else [])
    return ({"tool_call": tc, "options": OPTS}, names, resources, cls, lossy)


def recorded_verdict(detail: dict) -> str:
    by = detail.get("by")
    if by in AUTO:
        return "allow"
    if by == "deny":
        return "deny"
    return "ask"                    # owner / unanswered: it reached the owner


def compiled_verdict(rules, names, paths, *, ignorecase, cover) -> str:
    """Every tool name the request may have been must get the same answer;
    otherwise it is not decided by a rule (it reaches Mentis)."""
    if not rules or not names:
        return "ask"
    got = {claude_verdict(rules, n, paths, ignorecase=ignorecase,
                          read_rules_cover_search=cover) for n in names}
    if got == {"allow"}:
        return "allow"
    if "deny" in got:
        return "deny"
    return "ask"


SEMANTICS = {"documented": (True, True), "case-sensitive": (False, True),
             "read-rules-skip-search": (True, False), "both": (False, False)}


# ---------------------------------------------------------------------------


def run(path: str, *, examples: int = 5, classes=ALL_CLASSES) -> dict:
    t0 = time.time()
    rec = Record(path)
    answers = rec.answers()
    starts_consent: dict[str, dict] = {}
    out = {"db": path, "answers": len(answers), "classes": {}, "semantics": {},
           "by_runtime": collections.Counter(), "fidelity": collections.Counter(),
           "fidelity_examples": [], "mode_at_start": collections.Counter(),
           "consent_changed_mid_run": 0, "runs": 0}
    per_class = {c: collections.Counter() for c in [*classes, "compiled"]}
    examples_of = collections.defaultdict(list)
    sem = {k: collections.Counter() for k in SEMANTICS}
    changed_runs = set()
    by_category = collections.defaultdict(collections.Counter)

    for a in answers:
        d = a["detail"] or {}
        op = d.get("operation") or {}
        runtime = a.get("runtime")
        out["by_runtime"][runtime] += 1
        run_id = a["caused_by"]
        start = rec.by_id.get(run_id)
        if start is None:
            out["fidelity"]["no-start-act"] += 1
            continue
        ws = (start.get("detail") or {}).get("workspace")
        at_answer = View(rec, rec.seq[a["id"]] - 1)
        consent = C.of_run(at_answer, run_id, workspace=ws)
        if run_id not in starts_consent:
            starts_consent[run_id] = C.of_run(View(rec, rec.seq[run_id]), run_id, workspace=ws)
        at_start = starts_consent[run_id]
        out["mode_at_start"][at_start["mode"]] += 1
        if (at_start["mode"], at_start["workspaces"], at_start["categories"]) != \
                (consent["mode"], consent["workspaces"], consent["categories"]):
            changed_runs.add(run_id)
        request, names, paths, cls, lossy = reconstruct(op)

        def pending(view=at_answer, exp=start.get("caused_by")):
            from mentis.conversation.workflow_change import pending_carrier_change
            return pending_carrier_change(view, exp)

        m = None
        try:
            m = decide(request, workspace=ws, consent=consent, pending=pending)
            M = m.outcome
        except Exception as exc:                          # noqa: BLE001
            M = "ask"
            out["fidelity"][f"decide-error:{type(exc).__name__}"] += 1
        R = recorded_verdict(d)
        fid = "agree" if M == R else f"M={M},R={R}"
        out["fidelity"][fid] += 1
        if M != R and len(out["fidelity_examples"]) < 40:
            out["fidelity_examples"].append({"id": a["id"], "by": d.get("by"),
                                             "decide_by": getattr(m, "by", None),
                                             "summary": op.get("summary"),
                                             "class": cls, "mode": consent["mode"],
                                             "lossy": lossy})
        cat = f"{cls}:{op.get('category')}"
        by_category[cat]["n"] += 1
        by_category[cat][f"M={M}"] += 1
        claude = runtime == "claude"

        for c in [*classes, "compiled"]:
            use = set(COMPILED_CLASSES) if c == "compiled" else {c}
            rules = compile_claude(at_start, workspace=ws, classes=use) if claude else None
            K = compiled_verdict(rules, names, paths, ignorecase=True, cover=True)
            cnt = per_class[c]
            cnt["n"] += 1
            if K == "allow":
                cnt["rule-allow"] += 1
                cnt[f"rule-allow-of:{d.get('by')}"] += 1
                cnt[f"rule-allow-mode:{at_start['mode']}"] += 1
            if K == "deny":
                cnt["rule-deny"] += 1
            if K == "allow" and (M != "allow" or R != "allow"):
                cnt["more-permissive"] += 1
                if len(examples_of[(c, "more-permissive")]) < examples:
                    examples_of[(c, "more-permissive")].append(
                        {"id": a["id"], "summary": op.get("summary"), "M": M, "R": R,
                         "by": d.get("by"), "mode_start": at_start["mode"],
                         "mode_now": consent["mode"]})
            elif K == "deny" and M == "allow":
                cnt["restrictive-refuses-allowed"] += 1
                if len(examples_of[(c, "refuses-allowed")]) < examples:
                    examples_of[(c, "refuses-allowed")].append(
                        {"id": a["id"], "summary": op.get("summary"), "by": d.get("by")})
            elif K == "deny" and M == "ask":
                cnt["restrictive-refuses-asked"] += 1
                if len(examples_of[(c, "refuses-asked")]) < examples:
                    examples_of[(c, "refuses-asked")].append(
                        {"id": a["id"], "summary": op.get("summary"), "by": d.get("by")})
            elif K == "ask" and M == "allow":
                cnt["fallback-to-mentis"] += 1
            E = K if K in ("allow", "deny") else M
            cnt["agree" if E == M else "disagree"] += 1
            if c == "compiled":
                by_category[cat][f"K={K}"] += 1
                for name, (ic, cover) in SEMANTICS.items():
                    K2 = compiled_verdict(rules, names, paths, ignorecase=ic, cover=cover)
                    sem[name]["rule-allow"] += K2 == "allow"
                    sem[name]["more-permissive"] += K2 == "allow" and (M != "allow" or R != "allow")
                    sem[name]["rule-deny"] += K2 == "deny"
    out["classes"] = {c: dict(v) for c, v in per_class.items()}
    out["semantics"] = {k: dict(v) for k, v in sem.items()}
    out["examples"] = {f"{c}/{k}": v for (c, k), v in examples_of.items()}
    out["by_category"] = {k: dict(v) for k, v in sorted(by_category.items(),
                                                         key=lambda kv: -kv[1]["n"])}
    out["by_runtime"] = dict(out["by_runtime"])
    out["fidelity"] = dict(out["fidelity"])
    out["mode_at_start"] = dict(out["mode_at_start"])
    out["consent_changed_mid_run"] = len(changed_runs)
    out["runs"] = len(starts_consent)
    out["seconds"] = round(time.time() - t0, 1)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("db", nargs="?", default=DEFAULT_DB)
    ap.add_argument("--json", help="write the full result here")
    ap.add_argument("--examples", type=int, default=5)
    args = ap.parse_args(argv)
    got = run(args.db, examples=args.examples)
    text = json.dumps(got, indent=1, default=str)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)
    worst = max(v.get("more-permissive", 0) for v in got["semantics"].values())
    return 1 if worst or got["classes"]["compiled"].get("more-permissive") else 0


if __name__ == "__main__":
    raise SystemExit(main())
