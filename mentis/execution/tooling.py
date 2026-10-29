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


def _not_reported(why: str) -> dict:
    return {"how": NOT_REPORTED, "why": why}


def effective(meta: dict | None, *, backend: str, workspace: str,
              mcp_servers=(), requested_model: str | None = None,
              consent: dict | None = None) -> dict:
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
        "command_cwd": ("per-call" if m.get("command_cwd") == "per-call" else NOT_REPORTED),
        # WHERE IT WORKS, as Mentis asked MARS to start it, and what MARS
        # added to the session's reach.
        "cwd": {"path": workspace, "how": DECLARED},
        "additional_directories": [d for d in (m.get("additional_directories") or ())
                                   if isinstance(d, str)],
        "mcp_servers": sorted({s.get("name") for s in mcp_servers
                               if isinstance(s, dict) and s.get("name")}),
        "sandbox": (m.get("sandbox") if isinstance(m.get("sandbox"), dict)
                    else _not_reported(why)),
        "limitations": [x for x in (m.get("limitations") or ()) if isinstance(x, str)],
        # THE OWNER'S AUTHORIZATION, and nothing else, says what may be done.
        "consent": ({k: consent.get(k) for k in ("mode", "label", "workspaces", "categories")}
                    if consent else {"mode": "ask"}),
        "reported_by_mars": bool(m),
    }


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
    if eff.get("command_cwd") != "per-call" and _has_shell_tool(eff) is not False:
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
    sandbox = eff.get("sandbox") or {}
    if sandbox.get("how") != NOT_REPORTED and sandbox:
        said = ", ".join(f"{k} {v}" for k, v in sorted(sandbox.items()) if isinstance(v, (str, bool)))
        if said:
            lines.append(f"- Sandbox: {said}")
    for lim in eff.get("limitations") or ():
        lines.append(f"- Limitation: {lim}")
    for d in disciplines:
        named = [t for t in (d.get("tools") or ()) if isinstance(t, str)]
        if not named:
            continue
        lines.append(f"How the Discipline \"{d.get('name')}\" applies here (its tools, as this run can reach them):")
        lines.extend(_tool_line(t, eff, cwd or ".") for t in named)
    return "\n".join(lines)


def for_run(cv, run: str, instance, delivered=(), mcp_servers=()):
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

    def tooling(meta):
        eff = effective(meta, backend=instance.runtime, workspace=instance.workspace or ".",
                        mcp_servers=mcp_servers, requested_model=instance.requested_model,
                        consent=given if given and given.get("source") != "none" else None)
        eff["disciplines"] = [d["id"] for d in disciplines]
        return render(eff, disciplines), eff
    return tooling
