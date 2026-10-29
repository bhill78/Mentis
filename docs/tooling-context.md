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

Nothing is invented. Every fact says how it is known:

- **declared** — explicitly provided by the runtime or backend, or by what MARS
  itself controls (its local worker's tools and shell, the Antigravity calls it
  builds, the session's cwd and directories it passes);
- **observed** — established for one particular tool call (Claude's tool name on
  that call's `tool_call`, Codex's `cwd` on that command);
- **not reported** — the runtime has not supplied it. It stays not reported:
  never filled from the operating system ("Windows means PowerShell") and never
  carried over from a previous tool call.

## MARS: `session/new` response `_meta["mars/tooling"]`

Always present (not only with consent):

```json
{
  "backend": "claude", "version": "0.97.0",
  "cwd": "C:\\Work\\Mentis-wt\\x",
  "additional_directories": ["C:\\Work\\repo"],
  "model": {"id": "sonnet", "how": "declared"},
  "shell": {"name": null, "how": "not-reported", "per_call": true,
            "why": "the runtime chooses PowerShell or Bash itself; it names the tool on each call's tool_call"},
  "tools": null, "tools_how": "not-reported", "tools_why_not": "the runtime does not list its tools over ACP",
  "native_edit": {"value": true, "how": "declared"},
  "mcp_servers": ["mentis"],
  "sandbox": {"permissions": "forwarded", "enforced_by": "client"},
  "command_cwd": "per-call",
  "limitations": []
}
```

- `shell.name`: `"powershell"`, `"bash"`, `"cmd"` or `null`; `shell.how`:
  `"declared"` (MARS's own worker decides it — the local backend) or
  `"not-reported"`; `per_call: true` when the runtime names the tool on each
  call (Claude), so the shell of a call can be observed.
- `tools`: `[{name, kind}]` only where declared (the local backend's OpenHands
  tools; Antigravity, whose calls MARS builds), else `null` with `tools_why_not`.
- `native_edit`: `{value, how}`; `value` null when not reported.
- `command_cwd`: `"per-call"` when the runtime sends each command's cwd
  (Codex), else `"not-reported"`. MARS never reports where a shell has moved to.
- `sandbox.enforced_by` as `mars.consent.enforced_by`.

## MARS: per tool call `_meta["mars/tool"]`

On every forwarded `tool_call`, `tool_call_update` and the `toolCall` of a
`session/request_permission`, where MARS holds the runtime's own name for that
call (Claude sends `_meta.claudeCode.toolName` on `tool_call`, not on the
permission request; MARS remembers it by `toolCallId`):

```json
{"name": "PowerShell", "shell": "powershell", "how": "observed"}
```

The name is observed on that call's own `tool_call`; MARS carries it to the
permission request for the SAME `toolCallId` only. A permission request whose
call MARS saw no name for gets no `mars/tool`: it is not reported. `shell` is
set only when the name says it (`PowerShell` → `powershell`, `Bash` → `bash`;
the local backend's `terminal` → its worker's declared shell).

## Mentis: reading an operation (run consent)

The shell is, in order: the call's observed `mars/tool.shell`; the session's
declared `shell.name`; otherwise NOT REPORTED. A command whose shell is not
reported is read both ways; only when both readings agree is it classified,
otherwise it is a command Mentis cannot read safely (`other`, asked or
refused as before). The cmdlet-name guess is gone.

The working directory of a command is, in order: the call's own `cwd`
(observed, Codex); a directory the command itself sets before acting
(`Set-Location C:epo; ...`, observed in the command); the session's
declared `cwd` while no shell command has yet run in the session; otherwise
NOT REPORTED. Nothing is carried over from a previous command. A part of a
command whose effect depends on a working directory that is not reported
(relative paths, tests, builds, Git, programs run there) is not within the
task: it keeps the ask/refuse behaviour. The agent is told so, and how to make
its commands readable (start them by setting an absolute directory).

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
