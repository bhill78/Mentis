"""Compiled scope: a run's consent as the runtime's own permission rules
(docs/modernization/CONTRACT.md, WS-A; docs/modernization/permission-replay.md).

Every permission request a runtime raises reaches Mentis today
(`mentis.web.permissions`). For the operations whose answer does not depend
on anything that can change while a run works, the same answer can be given
by the runtime itself, from rules handed to it when the session opens. This
module says which rules, and -- so the claim can be checked -- how the
runtime reads them.

NEVER BROADER. A rule set compiled here allows only what `permissions.decide`
allows without asking, for the same request, under the same consent. Anything
a rule does not allow still reaches Mentis exactly as today. Deny rules are
written first for the protected locations (`operations.protected_roots`,
secrets by name) and for the files inside a workspace that become commands
or permissions (`operations.GUARDED`): an allow rule never reaches them.

WHICH OPERATION CLASSES ARE COMPILED is `COMPILED_CLASSES`, set from the
replay (`tools/permission_replay.py`) -- a class is listed only where the
replay of the recorded requests showed the compiled verdict never allowed
what Mentis would have asked about or refused:

  mentis-tools  the run's own Mentis tools (`mcp__mentis__*`); Mentis grants
                them in every mode, and `/api/worker` checks each again.
  file-reads    Claude's Read tool inside the run's workspace and the task's
                approved workspaces, secrets and protected locations denied.
  file-edits    Claude's file-edit tools inside the approved workspaces when
                the owner's consent is routine work (`task`/`deny`) with the
                `edit` category, guarded files, secrets and protected
                locations denied. NOT under `ask`: there an edit rests on the
                run's standing allowance, which a carrier's pending Workflow
                change withdraws mid-run (`workflow_change`), and a rule handed
                to the runtime at the start could not be withdrawn with it.
  approve-all   the owner's Approve All: every tool, by name.

Shell commands are not compiled. Claude matches `Bash(prefix:*)` against a
command line it splits by its own reading; Mentis classifies every simple
command and the paths it touches (`operations.describe`). A prefix rule
that matched what Mentis would ask about (`cat ~/.ssh/id_rsa` under
`Bash(cat:*)`) would broaden authority, so shell commands stay per-operation.

CLAUDE CODE RULE SEMANTICS RELIED ON (the `claude` runtime only), as
documented ("Configure permissions", settings `permissions.allow/ask/deny`)
and as read in the shipped CLI (`@anthropic-ai/claude-code` 1.0.128,
`cli.js`: path rules are matched with the `ignore` package, gitignore
syntax, created with its default `ignorecase: true`):

  * deny rules are checked first, then ask, then allow; no matching rule
    means the runtime asks, which reaches Mentis as today.
  * a bare tool name (`Read`, `Bash`) matches every use of that tool;
    `mcp__server__*` matches every tool of that MCP server; a full
    `mcp__server__tool` matches that tool.
  * `Read(path)` applies to Read (and, best effort, Grep and Glob);
    `Edit(path)` applies to every built-in file-edit tool (Edit, Write,
    MultiEdit, NotebookEdit).
  * a path pattern starting `//` is an absolute filesystem path; Windows
    paths are matched in POSIX form, `C:\\Work\\x` as `/c/Work/x`.
  * gitignore syntax: `*` and `?` do not cross `/`, `**` crosses any number
    of directories (including none), and a pattern that matches a directory
    matches everything beneath it.

The matcher below implements exactly this, with case sensitivity as a
parameter: the replay is run both ways, and a class is compiled only when
neither reading broadens.
"""

from __future__ import annotations

import os
import re

from mentis.operations import GUARDED, protected_roots

#: Operation classes compiled into runtime rules (see the module doc and
#: docs/modernization/permission-replay.md for the evidence per class).
COMPILED_CLASSES = frozenset({"mentis-tools", "file-reads", "file-edits", "approve-all"})
ALL_CLASSES = ("mentis-tools", "file-reads", "file-edits", "approve-all")

#: Claude's file tools, by the rule family that governs them.
READ_TOOLS = ("Read", "Grep", "Glob")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
#: Every tool Approve All allows by name. Anything else still asks Mentis,
#: which allows it under Approve All.
ALL_TOOLS = ("Bash", "PowerShell", *READ_TOOLS, *EDIT_TOOLS, "WebFetch", "WebSearch",
             "mcp__mentis__*")
MENTIS_TOOLS = "mcp__mentis__*"

#: `operations._SECRET_NAMES`, as gitignore names of a file's last component.
SECRET_GLOBS = (".env", ".env.*", "auth.json", "credentials", "credentials.*",
                *(f"id_{k}{s}" for k in ("rsa", "ed25519", "ecdsa", "dsa")
                  for s in ("", ".pub")),
                "*.pem", "*.pfx", "*.key")

#: Characters that mean something in a rule or a gitignore pattern; a
#: directory whose path holds one gets no rule (its requests reach Mentis).
_UNSAFE = re.compile(r"[\[\]*?!#()\\{}]|\s$")


def rule_path(path: str) -> str | None:
    """An absolute path as a Claude `//` rule path (no trailing slash), or
    None when it cannot be written safely as one."""
    if not path or not os.path.isabs(path):
        return None
    p = os.path.normpath(path).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):(/.*)?$", p)
    if m:
        p = "/" + m.group(1).lower() + (m.group(2) or "/")
    if not p.startswith("/") or p.startswith("//"):
        return None                                  # a UNC path: none
    p = p.rstrip("/") or "/"
    if p == "/" or re.fullmatch(r"/[a-z]", p) or _UNSAFE.search(p):
        return None
    return "/" + p


def _ci(pattern: str) -> str:
    """A deny pattern that matches whatever the case: `.env` as
    `.[eE][nN][vV]`. Windows paths are case-insensitive, and an allow rule
    naming the workspace as written must not outrun a deny that names a
    file in another case, under either reading of Claude's matching."""
    return "".join(f"[{c.lower()}{c.upper()}]" if c.isalpha() else c for c in pattern)


def compile_claude(consent: dict, *, workspace: str | None,
                   classes=COMPILED_CLASSES, roots: list[str] | None = None) -> dict | None:
    """The run's consent (`consent.of_run`) as Claude permission rules:
    {"allow": [...], "deny": [...]}, or None when nothing is compiled."""
    classes = set(classes)
    mode = consent.get("mode")
    if mode == "all":
        # APPROVE ALL allows whatever is asked, the protected locations
        # included: no deny rule, and any other class is a subset of it.
        if "approve-all" in classes:
            return {"allow": list(ALL_TOOLS), "deny": []}
        allow = [MENTIS_TOOLS] if "mentis-tools" in classes else []
        if "file-reads" in classes:
            allow += [f"Read({rp}/**)" for rp in dict.fromkeys(
                rule_path(w) for w in [workspace, *(consent.get("workspaces") or [])] if w) if rp]
        if "file-edits" in classes:
            allow += [f"Edit({rp}/**)" for rp in dict.fromkeys(
                rule_path(w) for w in consent.get("workspaces") or ()) if rp]
        return {"allow": allow, "deny": []} if allow else None
    allow: list[str] = []
    deny: list[str] = []
    if "mentis-tools" in classes:
        allow.append(MENTIS_TOOLS)
    read_roots, edit_roots = [], []
    if "file-reads" in classes:
        for w in [workspace, *(consent.get("workspaces") or [])]:
            rp = rule_path(w) if w else None
            if rp and rp not in read_roots:
                read_roots.append(rp)
    if "file-edits" in classes and mode in ("task", "deny") \
            and "edit" in (consent.get("categories") or ()):
        for w in consent.get("workspaces") or ():
            rp = rule_path(w)
            if rp and rp not in edit_roots:
                edit_roots.append(rp)
    if read_roots or edit_roots:
        # DENY FIRST: the protected locations, wherever they are, then the
        # secrets and guarded files inside every root an allow names.
        for r in (roots if roots is not None else protected_roots()):
            rp = rule_path(r)
            if rp:
                deny += [f"Read({_ci(rp)}/**)", f"Edit({_ci(rp)}/**)"]
        for rp in read_roots:
            deny += [f"Read({_ci(rp)}/**/{_ci(g)})" for g in SECRET_GLOBS]
        for rp in edit_roots:
            deny += [f"Edit({_ci(rp)}/**/{_ci(g)})" for g in SECRET_GLOBS]
            deny += [f"Edit({_ci(rp)}/**/{_ci(g)})" for g in sorted(GUARDED)]
        allow += [f"Read({rp}/**)" for rp in read_roots]
        allow += [f"Edit({rp}/**)" for rp in edit_roots]
    if not allow:
        return None
    return {"allow": allow, "deny": list(dict.fromkeys(deny))}


# ---------------------------------------------------------------------------
# how Claude Code reads them


def _glob_re(pattern: str, ignorecase: bool) -> re.Pattern:
    """A gitignore pattern (anchored, `//`-stripped) as a regex over a POSIX
    path. `**` crosses directories, `*` and `?` do not."""
    out, i, n = [], 0, len(pattern)
    while i < n:
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:[^/]*/)*")          # zero or more directories
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = pattern.find("]", i + 1)
            if j < 0:
                out.append(re.escape(c))
            else:
                out.append("[" + pattern[i + 1:j].replace("\\", "\\\\") + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$", re.I if ignorecase else 0)


def as_posix(path: str) -> str:
    """A filesystem path as Claude matches it: `C:\\x\\y` -> `/c/x/y`."""
    p = os.path.normpath(path).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):(/.*)?$", p)
    if m:
        p = "/" + m.group(1).lower() + (m.group(2) or "")
    return p


def _path_matches(pattern: str, path: str, ignorecase: bool) -> bool:
    """Whether a `//` path pattern matches the path or any directory above
    it (gitignore: a matched directory covers its contents)."""
    if not pattern.startswith("//"):
        return False                 # relative patterns are never emitted
    rx = _glob_re(pattern[1:], ignorecase)
    p = as_posix(path)
    parts = p.split("/")
    for k in range(len(parts), 1, -1):
        if rx.match("/".join(parts[:k])):
            return True
    return False


def _parse(rule: str) -> tuple[str, str | None]:
    m = re.match(r"^([^()]+)\((.*)\)$", rule)
    return (m.group(1), m.group(2)) if m else (rule, None)


def _rule_matches(rule: str, tool: str, paths: list[str], ignorecase: bool,
                  *, family_reads: tuple, family_edits: tuple) -> bool:
    name, spec = _parse(rule)
    if spec is None:
        if name.startswith("mcp__"):
            if name.endswith("__*"):
                return tool.startswith(name[:-1])
            if name.count("__") == 1:                       # mcp__server
                return tool.startswith(name + "__")
            return tool == name
        return tool == name
    if name == "Read" and tool in family_reads or name == "Edit" and tool in family_edits:
        # A path rule matches a request only through its path; a call that
        # names none is not matched (it reaches Mentis).
        return bool(paths) and all(_path_matches(spec, p, ignorecase) for p in paths)
    return False


def claude_verdict(rules: dict | None, tool: str | None, paths: list[str] | None = None,
                   *, ignorecase: bool = True, read_rules_cover_search: bool = True) -> str:
    """What Claude Code does with this tool call under these rules:
    "allow", "deny", or "ask" (the request reaches Mentis).

    DENY BEFORE ALLOW, and a deny rule matches a call if it matches ANY of
    its paths; an allow rule only if it matches ALL of them.
    `read_rules_cover_search=False` is the reading in which Read rules do
    not reach Grep and Glob at all (the documented "best effort"). Claude
    checks a call's path against allow and deny rules in one read-permission
    check, so a Read rule reaches Grep for both or for neither."""
    if not rules or not tool:
        return "ask"
    paths = [p for p in (paths or []) if p]
    reads = READ_TOOLS if read_rules_cover_search else ("Read",)
    for rule in rules.get("deny") or ():
        name, spec = _parse(rule)
        if spec is None:
            if _rule_matches(rule, tool, paths, ignorecase, family_reads=reads,
                             family_edits=EDIT_TOOLS):
                return "deny"
            continue
        if (name == "Read" and tool in reads or name == "Edit" and tool in EDIT_TOOLS) \
                and any(_path_matches(spec, p, ignorecase) for p in paths):
            return "deny"
    for rule in rules.get("allow") or ():
        if _rule_matches(rule, tool, paths, ignorecase, family_reads=reads,
                         family_edits=EDIT_TOOLS):
            return "allow"
    return "ask"
