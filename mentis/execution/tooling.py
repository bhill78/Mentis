"""What one run can actually do, said once (docs/tooling-context.md).

`effective` joins what MARS reports for the session (`_meta["mars/tooling"]`)
with what Mentis itself declares for the run -- its working directory, the
MCP servers it was given, the owner's run consent -- into one record of the
run's tooling. Every fact says how it is known: DECLARED (provided by the
runtime or backend, or by what MARS or Mentis itself controls), OBSERVED (for
one tool call), or NOT REPORTED. Nothing is filled from the operating system
or carried over from an earlier call.

`render` is what the agent is told: that record in a few lines, then how each
Discipline it was given applies here -- each tool the Discipline names, as it
can (or cannot) be reached in THIS run, in this shell's syntax. The
Discipline's own text is delivered unchanged elsewhere; this only places it.

FOUR THINGS KEPT APART. A Discipline says what is useful; runtime capability
and tool availability say what this run can reach; only the owner's run
consent and the run's grant say what it may do. Nothing here permits anything,
and the block says so.
"""

from __future__ import annotations

import os
from typing import Any

DECLARED, OBSERVED, NOT_REPORTED = "declared", "observed", "not-reported"
SHELL_WORDS = {"powershell": "PowerShell", "bash": "Bash", "cmd": "cmd"}

#: What every run is told about stopping processes (docs/tooling-context.md).
PROCESS_OWNERSHIP = (
    "- Processes: other agents run on this machine as the same user. Stop only the processes "
    "you started, by their pid (record a dev server's pid when you start it, then "
    "`taskkill /PID <pid> /T /F` or `kill <pid>`). Never stop processes by name "
    "(`taskkill /IM`, `Stop-Process -Name`, `Get-Process <name> | Stop-Process`, `pkill`, "
    "`killall`): that stops other agents' work too.")


#: The capability contract's `permission_enforcement.kind`s of a runtime confined by its own
#: sandbox that runs every command inside it without asking (codex): escalations go to its
#: own reviewer first (`sandbox+runtime-reviewer`, codex-acp `agent` mode) or to Mentis
#: (`sandbox+client`, the `workspace-write` mode MARS runs a consented codex session in).
SANDBOX_REVIEWER = "sandbox+runtime-reviewer"
SANDBOX_CLIENT = "sandbox+client"


def _not_reported(why: str) -> dict:
    return {"how": NOT_REPORTED, "why": why}


def effective(meta: dict | None, *, backend: str, workspace: str,
              mcp_servers=(), requested_model: str | None = None,
              consent: dict | None = None, enforcement: str | None = None,
              escalations_to: str | None = None, secrets_refused: int = 0,
              execution_mode: dict | None = None,
              secrets_refused_all: bool = True) -> dict:
    """The run's tooling: MARS's report for the session, and Mentis's own.

    `meta` is `_meta["mars/tooling"]`, or None from a MARS that does not
    report it -- then every fact MARS would have given is not reported, with
    that as the reason. `consent` is the run's consent as
    `operational.consent.of_run` reads it (the owner's authorization)."""
    m = meta if isinstance(meta, dict) else {}
    why = ("this MARS does not report its tooling" if not m
           else "MARS did not report it")
    shell = m.get("shell") if isinstance(m.get("shell"), dict) else None
    if not shell or shell.get("how") != DECLARED or not shell.get("name"):
        shell = {"name": None, "how": NOT_REPORTED,
                 "per_call": bool((shell or {}).get("per_call")),
                 "why": (shell or {}).get("why") or why}
    tools = m.get("tools") if m.get("tools_how") == DECLARED and isinstance(m.get("tools"), list) else None
    edit = m.get("native_edit") if isinstance(m.get("native_edit"), dict) else None
    model = m.get("model") if isinstance(m.get("model"), dict) and (m["model"].get("id")) else None
    return {
        "backend": backend,
        "version": m.get("version"),
        "model": model or ({"id": requested_model, "how": DECLARED, "by": "mentis"}
                           if requested_model else _not_reported(why)),
        "shell": shell,
        "tools": ({"how": DECLARED, "list": [{"name": t.get("name"), "kind": t.get("kind")}
                                              for t in tools if isinstance(t, dict)]}
                  if tools is not None else _not_reported(m.get("tools_why_not") or why)),
        "native_edit": (edit if edit and edit.get("how") == DECLARED and edit.get("value") is not None
                        else _not_reported((edit or {}).get("why") or why)),
        "command_cwd": (m["command_cwd"] if m.get("command_cwd") in ("per-call", "session")
                        else NOT_REPORTED),
        # WHERE IT WORKS, as Mentis asked MARS to start it, and what MARS
        # added to the session's reach.
        "cwd": {"path": workspace, "how": DECLARED},
        "additional_directories": [d for d in (m.get("additional_directories") or ())
                                   if isinstance(d, str)],
        # WHAT MARS GAVE THE SESSION when it assembled it (`mars/mcp`, O8):
        # the run's own servers and the owner's that were allowed; else the
        # run's own, as Mentis asked for them.
        "mcp_servers": (_mcp_given(m["mcp"]) if isinstance(m.get("mcp"), dict)
                        and isinstance(m["mcp"].get("given"), list)
                        else sorted({s.get("name") for s in mcp_servers
                                     if isinstance(s, dict) and s.get("name")})),
        "mcp_not_given": (_mcp_not_given(m["mcp"]) if isinstance(m.get("mcp"), dict)
                          else []),
        "mcp_notes": [{"name": g.get("name"), "note": g["note"]}
                      for g in ((m.get("mcp") or {}).get("given") or ())
                      if isinstance(g, dict) and isinstance(g.get("note"), str)],
        "sandbox": (m.get("sandbox") if isinstance(m.get("sandbox"), dict)
                    else _not_reported(why)),
        "limitations": [x for x in (m.get("limitations") or ()) if isinstance(x, str)],
        # THE OWNER'S AUTHORIZATION, and nothing else, says what may be done.
        "consent": ({k: consent.get(k) for k in ("mode", "label", "workspaces", "categories")}
                    if consent else {"mode": "ask"}),
        "reported_by_mars": bool(m),
        # HOW THE RUNTIME'S CONSENT IS ENFORCED, as its capability contract
        # declares it (`permission_enforcement.kind`): a `pre-turn` runtime is
        # told up front what it may not try (N1).
        "permission_enforcement": enforcement,
        # WHO DECIDES A REQUEST TO LEAVE THE SANDBOX: "client" when Mentis asked MARS to
        # route it to Mentis (`permissions.reviews_escalations`), else the runtime's own.
        "escalations_to": escalations_to,
        # HOW MANY SECRET FILES BY NAME the runtime was told to refuse by exact path
        # (`permissions.secret_read_deny`, agy), 0 when none.
        "secrets_refused": secrets_refused,
        # THE EXECUTION MODE the run's start recorded (`execution.mode`), and whether MARS
        # reported applying it (`sandbox.execution_mode.name`).
        "execution_mode": ({"name": execution_mode.get("effective"),
                            "requested": execution_mode.get("requested"),
                            "source": execution_mode.get("source"),
                            "isolation": execution_mode.get("isolation"),
                            "container": False,
                            "applied": ((m.get("sandbox") or {}).get("execution_mode") or {}).get("name")
                            == execution_mode.get("effective")
                            if isinstance(m.get("sandbox"), dict) else False}
                           if execution_mode else None),
        # False when that list is not every secret file found (a walk stopped at its bound,
        # or a path MARS cannot take as an exact rule): the run is told so.
        "secrets_refused_all": secrets_refused_all,
    }


_MCP_REASONS = {
    "other-brain": "another Mentis Brain",
    "mentis-outside-execution": "this Mentis without your run's grant",
    "mentis-unverified": "a Mentis surface whose Brain is not stated",
    "owner-denied": "denied by the owner's MCP policy",
    "owner-not-allowed": "not allowed by the owner's MCP policy",
}


def _mcp_given(report: dict) -> list[str]:
    return sorted({g.get("name") for g in report.get("given") or ()
                   if isinstance(g, dict) and isinstance(g.get("name"), str)})


def _mcp_not_given(report: dict) -> list[dict]:
    """The owner's servers this run does not have, and why: excluded ones
    (not those the run's own server of the same name replaces) and ones
    that could not be given."""
    out = []
    for e in report.get("excluded") or ():
        if isinstance(e, dict) and e.get("name") and not e.get("replaced_by_client"):
            out.append({"name": e["name"],
                        "why": _MCP_REASONS.get(e.get("reason"), e.get("reason") or "excluded")})
    for e in report.get("unavailable") or ():
        if isinstance(e, dict) and e.get("why"):
            out.append({"name": e.get("name"), "why": e["why"]})
    return out


# -- what the agent is told ---------------------------------------------------

def _shells(eff: dict) -> list[str]:
    """The shells to write commands for: the declared one, else both."""
    name = (eff.get("shell") or {}).get("name")
    return [name] if name in ("powershell", "bash") else ["powershell", "bash"]


def _msys(path: str) -> str:
    p = path.replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        p = "/" + p[0].lower() + p[2:]
    return p


def _in(directory: str, shell: str, command: str) -> str:
    """`command` run in `directory`, in that shell's own syntax."""
    if shell == "powershell":
        return f"Set-Location '{directory}'; {command}"
    return f"cd '{_msys(directory)}' && {command}"


def _python(ws: str, shell: str) -> str | None:
    venv = os.path.join(ws, ".venv", "Scripts", "python.exe")
    if not os.path.isfile(venv):
        return None
    return f"& '{venv}'" if shell == "powershell" else f"'{_msys(venv)}'"


def _has_shell_tool(eff: dict) -> bool | None:
    """Whether this run has a shell at all: from its declared tools when
    there are any, else not known (None)."""
    tools = eff.get("tools") or {}
    if tools.get("how") != DECLARED:
        return None
    return any(t.get("kind") == "execute" for t in tools.get("list") or ())


def _tool_line(word: str, eff: dict, ws: str) -> str:
    """One tool a Discipline names, as it can be reached in this run."""
    w = word.lower()
    if "bridge" in w or w.startswith("mentis"):
        return (f"- {word}: attached to this run as the `mentis` MCP server; every call is "
                "checked against your grant" if "mentis" in eff.get("mcp_servers", ())
                else f"- {word}: not attached to this run")
    shell_tool = _has_shell_tool(eff)
    if shell_tool is False:
        return f"- {word}: not available in this run (none of your tools runs commands)"
    shells = _shells(eff)
    if "pytest" in w:
        forms = []
        for sh in shells:
            py = _python(ws, sh) or "python"
            forms.append((sh, _in(ws, sh, f"{py} -m pytest -q <test files>")))
    elif "npm" in w:
        pkg = next((d for d in (ws, os.path.join(ws, "apps", "fluid-web"))
                    if os.path.isfile(os.path.join(d, "package.json"))), None)
        if pkg is None:
            return f"- {word}: no package.json in your working directory or apps/fluid-web"
        forms = [(sh, _in(pkg, sh, "npm test")) for sh in shells]
    elif w == "git" or w.startswith("git "):
        forms = [(sh, _in(ws, sh, "git status")) for sh in shells]
    else:
        return f"- {word}: named by the Discipline; whether it is reachable here is not reported"
    said = "; ".join(f"`{f}`" + (f" ({SHELL_WORDS[sh]})" if len(forms) > 1 else "")
                     for sh, f in forms)
    return f"- {word}: {said}"


def render(eff: dict, disciplines=()) -> str:
    """The run's tooling in a few lines, then each Discipline's tools placed
    in this run. Compact, and the same for the same facts."""
    shell = eff.get("shell") or {}
    model = eff.get("model") or {}
    lines = ["Your tooling for this run, as MARS and Mentis report it. It permits nothing: "
             "what you may do is your grant and the run consent; a tool named here or in a "
             "Discipline is not permission."]
    lines.append(f"- Runtime: {eff.get('backend')}"
                 + (f" {eff['version']}" if eff.get("version") else "")
                 + (f"; model {model['id']}" if model.get("id") else "; model not reported"))
    if shell.get("name"):
        lines.append(f"- Shell: {SHELL_WORDS.get(shell['name'], shell['name'])} (declared). "
                     "Write commands in its syntax.")
    elif shell.get("per_call"):
        lines.append("- Shell: not reported before you run a command. Your runtime chooses "
                     "PowerShell or Bash itself; use the syntax of the shell tool you actually call.")
    else:
        lines.append("- Shell: not reported.")
    cwd = (eff.get("cwd") or {}).get("path")
    extra = eff.get("additional_directories") or []
    lines.append(f"- Working directory: {cwd}" + (f"; also reachable: {', '.join(extra)}" if extra else ""))
    if eff.get("command_cwd") == "session" and _has_shell_tool(eff) is not False:
        lines.append("- Where a command runs: every shell command starts in the working "
                     "directory above (declared); a `cd` does not carry over to the next "
                     "command.")
    elif eff.get("command_cwd") != "per-call" and _has_shell_tool(eff) is not False:
        forms = " or ".join(f"{SHELL_WORDS[sh]} `{_in('C:\\dir', sh, '...')}`" for sh in _shells(eff))
        lines.append("- Where a command runs: your shell's current directory is not reported after "
                     "a command. A command that runs a program or uses relative paths is read as "
                     "routine only when it starts by setting an absolute directory: " + forms
                     + "; otherwise it is asked (or refused, under never-wait consent).")
    tools = eff.get("tools") or {}
    if tools.get("how") == DECLARED:
        lines.append("- Your tools: " + ", ".join(f"{t['name']} ({t.get('kind')})"
                                                  for t in tools.get("list") or ()))
    else:
        lines.append("- Your tools: not reported (your runtime does not list them).")
    edit = eff.get("native_edit") or {}
    if edit.get("how") == DECLARED:
        lines.append("- File editing: " + (
            "your own edit tool." if edit.get("value")
            else "no edit tool; files change only through your commands."
            if _has_shell_tool(eff) is not False else "none: you cannot change files."))
    if eff.get("mcp_servers"):
        lines.append(f"- MCP servers: {', '.join(eff['mcp_servers'])}")
    for said in eff.get("mcp_notes") or ():
        lines.append(f"- MCP server {said.get('name')}: {said['note']}")
    for gone in eff.get("mcp_not_given") or ():
        lines.append(f"- MCP server not available here: {gone.get('name') or 'some'} ({gone['why']})")
    sandbox = eff.get("sandbox") or {}
    mode = eff.get("execution_mode") or {}
    # UNRESTRICTED HOST EXECUTION, SAID AS SUCH (owner, 2026-11-11): never a sandbox or a
    # container. `host` is True only when MARS reported applying it.
    host = mode.get("name") == "unrestricted-host" and bool(mode.get("applied"))
    if mode.get("name") == "unrestricted-host":
        from mentis.execution.mode import BOUNDARY
        lines.append("- Execution: " + BOUNDARY if host else
                     "- Execution: unrestricted host execution was selected for this run but "
                     "MARS did not report applying it; your runtime's own sandbox and "
                     "permissions may still apply.")
    elif sandbox.get("how") != NOT_REPORTED and sandbox:
        said = ", ".join(f"{k} {v}" for k, v in sorted(sandbox.items()) if isinstance(v, (str, bool)))
        if said:
            lines.append(f"- Sandbox: {said}")
    # PROCESSES ARE OWNED (DAY-TO-DAY incident 2026-11-11, ent-e05dcf622c97): a Builder
    # stopped its dev server with `taskkill /IM node.exe` and ended other agents' runs.
    lines.append(PROCESS_OWNERSHIP)
    if eff.get("backend") == "claude" and (eff.get("consent") or {}).get("mode") != "all":
        # THE AUTHORIZED PATH TO A SECRET CLAUDE REFUSES ITSELF (review M1).
        from mentis.permission_rules import secret_read_path
        lines.append("- Secret files: " + secret_read_path())
    if eff.get("permission_enforcement") == "pre-turn" and not host:
        # A PRE-TURN RUNTIME CANNOT ASK: what the consent does not allow is
        # refused before it runs; MARS turns the refusal into a failed tool call the
        # turn continues from (agy deny rule, round 2 X), so the agent can recover.
        from mentis.web.permissions import pre_turn_shell
        if pre_turn_shell(eff.get("consent")):
            lines.append("- Shell commands: allowed in this run by the owner's consent, "
                         "decided before you started (your runtime cannot ask mid-run).")
        else:
            lines.append("- Shell commands: NOT permitted in this run. The owner's consent "
                         "does not include test, build or run, and your runtime cannot ask "
                         "for permission mid-run: a shell command you attempt is refused, "
                         "and the refusal comes back to you as a failed tool call. Carry on "
                         "with your own file read and list tools and the Mentis tools, and "
                         "say plainly in your outcome what you could not do.")
    if eff.get("secrets_refused"):
        lines.append(f"- Secret files: {eff['secrets_refused']} file(s) in your workspaces named "
                     "as secrets (.env, .env.<env>, SSH private keys, credentials, "
                     "credentials.json, auth.json), found when this run started, are refused "
                     "to your file tools and to commands in your sandbox by their exact path, by "
                     "the owner's consent; the refusal comes back to you as a failed tool call. "
                     + ("" if eff.get("secrets_refused_all", True) else
                        "Not every such file could be listed, and a file created later is not "
                        "among them: ")
                     + "Do not read files named as secrets in any other way.")
    consent = eff.get("consent") or {}
    kind = eff.get("permission_enforcement")
    if kind == SANDBOX_REVIEWER and eff.get("escalations_to") == "client":
        kind = SANDBOX_CLIENT
    if kind in (SANDBOX_REVIEWER, SANDBOX_CLIENT) and consent.get("mode") in ("task", "deny") \
            and not host:
        # A SANDBOXED RUNTIME THAT NEVER ASKS ABOUT ITS COMMANDS (codex): the
        # owner's categories reach it only as words. Measured (round 2 D): a run
        # under consent without test/build/run ran tests, a build and an
        # install, and its own reviewer approved a command outside the sandbox.
        from mentis.operations import DEFAULT_CATEGORIES
        cats = list(consent.get("categories") or ())
        missing = [c for c in DEFAULT_CATEGORIES if c not in cats]
        lines.append("- Consent is yours to keep: your runtime runs commands inside its "
                     "sandbox without asking Mentis, so nothing stops an operation the "
                     "owner's consent leaves out. It includes " + (", ".join(cats) or "nothing")
                     + (f"; it does NOT include {', '.join(missing)}: do not do those, and "
                        "report them as not permitted by the owner's consent" if missing else "")
                     + (". Approval to leave the sandbox is decided by your runtime's own "
                        "reviewer, not by the owner: ask for it only for operations the consent "
                        "includes." if kind == SANDBOX_REVIEWER else
                        ". When your sandbox blocks an operation the consent includes (for "
                        "example a commit: your sandbox keeps the Git directory read-only), "
                        "request to run it outside the sandbox with your runtime's own "
                        "escalated-permissions request (no Mentis tool is needed); that request "
                        "is asked of Mentis, which decides it by the owner's consent: allowed at "
                        "once when the consent includes it, otherwise refused or asked of the "
                        "owner."))
    for lim in eff.get("limitations") or ():
        lines.append(f"- Limitation: {lim}")
    for d in disciplines:
        named = [t for t in (d.get("tools") or ()) if isinstance(t, str)]
        if not named:
            continue
        lines.append(f"How the Discipline \"{d.get('name')}\" applies here (its tools, as this run can reach them):")
        lines.extend(_tool_line(t, eff, cwd or ".") for t in named)
    return "\n".join(lines)


def _enforcement_kind(contract):
    from mentis.web.permissions import enforcement_kind
    return enforcement_kind(contract)


def for_run(cv, run: str, instance, delivered=(), mcp_servers=(), contract=None):
    """The `RunSpec.tooling` function for one run, or None.

    It reads, once, what this run was given that the tooling block places:
    the owner's consent for it (`operational.consent.of_run`) and the
    Disciplines it was delivered (by source id, from its grant). Called by
    MARS execution with the session's `mars/tooling`, it returns the text and
    the effective tooling."""
    from mentis.conversation import DISCIPLINE
    from mentis.operational import consent as _consent
    try:
        given = _consent.of_run(cv, run, workspace=instance.workspace)
    except Exception:                                    # noqa: BLE001
        given = None
    disciplines = []
    ids = [i for i in dict.fromkeys(delivered or ()) if isinstance(i, str)]
    for e in (cv._c.read(ids) if ids else ()):
        if cv._is(e, DISCIPLINE):
            body = e.get("body") or {}
            disciplines.append({"id": e["id"], "name": body.get("name"),
                                "tools": body.get("tools") or []})
    disciplines.sort(key=lambda d: d["id"])

    from mentis.web.permissions import reviews_escalations, secret_read_deny
    from mentis.execution import mode as _mode
    try:
        chosen = _mode.of_run(cv, run)
    except Exception:                                    # noqa: BLE001
        chosen = None
    host = (chosen or {}).get("requested") == _mode.UNRESTRICTED_HOST
    escalations_to = "client" if given and not host and reviews_escalations(contract, given) else None
    refused, refused_all = 0, True
    if secret_read_deny(contract) and given and given.get("mode") != "all" and not host:
        from mentis.permission_rules import exact_secret_deny
        paths, refused_all = exact_secret_deny([instance.workspace, *(given.get("workspaces") or ())])
        refused = len(paths)

    def tooling(meta):
        eff = effective(meta, backend=instance.runtime, workspace=instance.workspace or ".",
                        mcp_servers=mcp_servers, requested_model=instance.requested_model,
                        consent=given if given and given.get("source") != "none" else None,
                        enforcement=_enforcement_kind(contract),
                        escalations_to=escalations_to, secrets_refused=refused,
                        execution_mode=chosen, secrets_refused_all=refused_all)
        eff["disciplines"] = [d["id"] for d in disciplines]
        return render(eff, disciplines), eff
    return tooling
