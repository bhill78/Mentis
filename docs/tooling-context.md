# The effective tooling context of a run

What one execution can actually do, said once and used twice: delivered to the
agent with its Discipline guidance, and used by run consent
(`docs/run-consent.md`) to read what its operations do.

## Four things kept apart

| | what it says | where it comes from | may it permit anything? |
|---|---|---|---|
| **Discipline** | useful tools, methods, practice | standing governance (`kind: discipline`, its `tools` and `tool_use`) | no — naming a tool grants nothing |
| **Runtime capability** | what the selected runtime can do (edit natively, run a shell, call MCP) | MARS's backend catalogue | no |
| **Tool availability** | what is reachable for THIS execution: the shell it runs, the tools it reports, its cwd and directories | MARS `session/new` → `_meta["mars/tooling"]`, and per call `_meta["mars/tool"]` | no |
| **Owner authorization** | which operations this run may perform | the run's grant and run consent | yes — only this |

Nothing is invented. A fact MARS does not have is reported as not reported,
with why, never filled in from a default ("Windows means PowerShell").

## MARS: `session/new` response `_meta["mars/tooling"]`

Always present (not only with consent):

```json
{
  "backend": "claude", "version": "0.97.0",
  "cwd": "C:\\Work\\Mentis-wt\\x",
  "additional_directories": ["C:\\Work\\repo"],
  "model": {"id": "sonnet", "how": "requested"},
  "shell": {"name": null, "how": "per-call",
            "why": "the runtime chooses PowerShell or Bash itself and names it on each command"},
  "tools": null, "tools_why_not": "the runtime does not list its tools over ACP",
  "native_edit": true,
  "mcp_servers": ["mentis"],
  "sandbox": {"permissions": "forwarded", "enforced_by": "client"},
  "cwd_persists": "within-session-directories",
  "limitations": []
}
```

- `shell.name`: `"powershell"`, `"bash"`, `"cmd"` or `null`. `shell.how`:
  `"worker"` (MARS's own worker decides it — the local backend), `"per-call"`
  (the runtime names it on each command, see below), `"not-reported"`.
- `tools`: `[{name, kind}]` only where MARS knows them (the local backend's
  OpenHands tools; Antigravity, whose calls MARS builds), else `null` with
  `tools_why_not`.
- `native_edit`: the runtime edits files with its own tool (true), only
  through a shell (false), or unknown (null).
- `cwd_persists`: how a `cd` carries to the next command — `"within-session-directories"`
  (Claude: kept only inside cwd and additional directories, otherwise reset to cwd),
  `"per-call"` (the runtime sends each command's cwd: Codex), `"no"`, or `"unknown"`.
- `sandbox.enforced_by` as `mars.consent.enforced_by`.

## MARS: per tool call `_meta["mars/tool"]`

On every forwarded `tool_call`, `tool_call_update` and the `toolCall` of a
`session/request_permission`, where MARS holds the runtime's own name for that
call (Claude sends `_meta.claudeCode.toolName` on `tool_call`, not on the
permission request; MARS remembers it by `toolCallId`):

```json
{"name": "PowerShell", "shell": "powershell"}
```

`shell` is set only when the name says it (`PowerShell` → `powershell`,
`Bash` → `bash`; the local backend's `terminal` → its worker's shell).
Absent when MARS does not know: a client never assumes.

## Mentis: reading an operation (run consent)

The shell is, in order: the call's `mars/tool.shell`; the session's
`shell.name` when `how` is `worker`; otherwise UNKNOWN. An unknown shell is
read both ways; only when both readings agree is the operation classified,
otherwise it is a command Mentis cannot read safely (`other`, asked or
refused as before). The cmdlet-name guess is gone.

The working directory of a command is, in order: the call's own `cwd`
(Codex); the run's tracked shell directory — the directory a previous
command's `cd`/`Set-Location`/`Push-Location` left the shell in, kept only
inside the session's directories when `cwd_persists` is
`within-session-directories`; the session `cwd`.

## Mentis: what the agent is told

Appended to the run's prompt with the other per-run facts (follow-up
permission, run consent), never in the shared Conversation foundation, so
shared blocks stay byte-identical across runtimes and grants:

```
---
Your tooling for this run (as MARS reports it; it permits nothing):
- Runtime: claude 0.97.0, model sonnet (requested).
- Shell: PowerShell — ...
- Working directory: ...; also reachable: ...
- File editing: your own edit tool.
- Mentis tools: mentis (MCP) ...
- Sandbox: ...
What you may do is your run consent and grant, above; a tool named here or in
a Discipline is not permission.
How "CLI and MARS development" applies here:
- tests: <command in this shell's syntax, for this workspace>
```

Discipline guidance is adapted, not rewritten: each tool the Discipline names
is matched against this run (present, how to call it in this shell, or not
available), and the Discipline's own text is delivered unchanged.
