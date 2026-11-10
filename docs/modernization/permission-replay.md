# Permission-policy equivalence replay (experiment E3, WS-A)

Tool: `tools/permission_replay.py`. Brain: `C:\Work\Mentis-brains\pre-eff-cbfabaa-20261108\corpus.db`,
opened read-only (`sqlite3` URI `mode=ro`). No Mentis Store or server was opened on it. Run on
2026-11-10, on `mod-perm`. It takes about 390 s.

## Result

| | count | share |
|---|---:|---:|
| Recorded `operation-answered` acts | 37,388 | 100% |
| Claude / Gemini | 37,372 / 16 | |
| Runs | 964 | |
| **Compiled verdict MORE PERMISSIVE than Mentis** (all four rule readings) | **0** | 0% |
| Compiled more restrictive: refuses what Mentis allowed | 1 | 0.003% |
| Compiled more restrictive: refuses what Mentis would ask the owner | 0 | 0% |
| Decided by a compiled rule (allow), so never reaching Mentis | 34,428 | 92.1% |
| Not matched by any rule, so reaching Mentis as today | 2,959 | 7.9% |
| Agreement (effective verdict = Mentis verdict) | 37,387 | 99.997% |

The gate is that the compiled verdict is never more permissive. It holds, so
`COMPILED_SCOPE_RUNTIMES = {"claude"}`. Gemini (16 answers) is not compiled, because no rule
syntax was built for it. Codex and Antigravity are not compiled either. Agy keeps its existing
`allow` option.

The one restrictive case was a Read of `%LOCALAPPDATA%\mars\backends.json`. The run started
under routine-work consent, and the owner switched it to Approve All partway through. Rules
compiled at the start deny protected locations, so this read would have been refused where
Mentis allowed it. The cause is that rules are fixed when the session opens (Deviation 3).

### Per operation class (each compiled alone, then together)

| Class | Rule allows | More permissive | Refuses allowed | Refuses asked |
|---|---:|---:|---:|---:|
| `mentis-tools` (`mcp__mentis__*`, every mode) | 11,388 | 0 | 0 | 0 |
| `file-reads` (`Read(//ws/**)`, secrets + protected denied) | 0* | 0 | 1 | 0 |
| `file-edits` (`Edit(//ws/**)` under task/deny + `edit`, or Approve All) | 1,787 | 0 | 0 | 0 |
| `approve-all` (every tool by name, no deny) | 32,787 | 0 | 0 | 0 |
| **compiled (all four)** | **34,428** | **0** | **1** | **0** |

\* In the recorded history, almost every Read either fell outside the run's own workspace and the
approved workspaces, or happened under Approve All, where `approve-all` already covers it. The
class is equivalent (0 permissive), so it stays compiled. Its rules decide nothing in this
history.

By the recorded answer, the rules take over 23,126 `grant` answers and 11,302 `all` answers. By
the mode at run start: Approve All 32,787, `ask` 1,557 (Mentis tools), `task` 84. Approve All
was the mode at start for 32,806 of the answers, so most of the gain depends on that mode.

What still reaches Mentis: every shell command outside Approve All, and reads and edits outside
the workspaces. It also includes edits under `ask`, which rest on the standing allowance. Owner
questions, research and tool-for-run consents reach Mentis too.

### Rule-semantics readings

Each request was evaluated under four readings of Claude Code's matching. They are case
insensitive or case sensitive, combined with Read rules reaching Grep and Glob or not. The results
were identical: 34,428 allowed and 0 more permissive in each.

## Method

1. **Request reconstruction.** Each answer records the operation: tool, label, category,
   command (up to 2,000 characters), working directory and paths (up to 5). From these the tool
   rebuilds an ACP permission request. Mentis tools come back as `mcp__mentis__*`. Shell commands
   come back as `execute` with the recorded shell and `shell_cwd`. File tools come back by kind
   with locations, and web tools as `fetch`. Where the adapter named no Claude tool (most edits
   and reads), the request is matched as every Claude tool of that kind: an edit as Edit, Write,
   MultiEdit and NotebookEdit; a search as Grep and Glob. A rule decides such a request only
   when all of those tools would get the same answer.
2. **Mentis verdict M.** `permissions.decide` is the live policy's verdict, factored out as a
   pure function. It runs over `consent.of_run` and `workflow_change.pending_carrier_change`.
   Both read a view of the record cut just before the answer: the acts that consent, lineage and
   Workflow-change reads look at, loaded into memory. **Fidelity check:** M equals the recorded
   answer R for 37,294 of 37,388 answers (99.75%). The 94 that differ are mostly test-server runs
   from when consent and the classifier were still being built (answered `task` or `tool` then;
   `ask` today), plus research fetches, `$`-variable PowerShell and unrecognised programs whose classification changed since. The gate
   counts a rule allow as more permissive if it disagrees with M **or** with R.
3. **Compiled verdict K.** `permission_rules.compile_claude` runs over the consent **as it stood
   when the run started**, which is what MARS hands the runtime. `permission_rules.claude_verdict`
   evaluates the request under those rules. Comparing start-of-run rules with answer-time
   verdicts covers everything that changed mid-run. In 81 of the 964 runs, consent changed
   during the run, and none of those changes produced a broadening.
4. **Effective verdict.** K where a rule decided (allow or deny), otherwise M (the request
   reaches Mentis).

### Claude Code semantics relied on

These come from the "Configure permissions" documentation and from the shipped CLI
(`@anthropic-ai/claude-code` 1.0.128 `cli.js` in the npm cache). There, path rules use the
`ignore` package (gitignore syntax) with its default `ignorecase: true`.

- Deny rules are checked before allow rules. A request no rule matches is asked of the client,
  which is Mentis.
- A bare name (`Bash`) matches every use of that tool. `mcp__mentis__*` matches every tool of
  that MCP server.
- `Read(...)` covers Read and, as a "best effort", Grep and Glob. `Edit(...)` covers every
  built-in edit tool.
- `//path` is absolute. Windows paths are matched in POSIX form (`/c/Work/x`). `*` and `?` stay
  within one directory, `**` crosses directories, and a matched directory covers its contents.
- Deny patterns are written with case classes (`.[eE][nN][vV]`), so they also hold under
  case-sensitive matching. The property tests showed this was needed: under case-sensitive
  matching, `repo\conf\.ENV.local` got past a lowercase deny.

## Limits

- The adapter actually in use (`@agentclientprotocol/claude-agent-acp` with the
  claude-agent-sdk 0.3.310 native binary) cannot be read. Its rule matching is assumed to be the
  documented one. That is why all four readings were replayed.
- Symlinks, junctions and 8.3 short names: Mentis resolves real paths, while Claude matches the
  literal path. A link inside a workspace that points at a protected location would be allowed by
  a Read or Edit rule. No such case appears in the history, and it is a residual risk.
- The recorded detail is not the raw request: commands are cut at 2,000 characters and paths at
  5. Classification ran against today's filesystem, and some workspaces no longer exist. These
  limits affect M and the fidelity figure, not the rules.
- Rules are fixed per session (Deviation 3 in CONTRACT.md). A narrowing during a run, or a
  carrier's Workflow change, does not reach rule-allowed operations until the next session. For
  Approve All in particular, an owner who narrows it mid-run is not obeyed by a live compiled run.
  The history has no such case, but the gap remains (see the report).
- Shell commands are not compiled. Equivalence would require reproducing Claude's command
  splitting, and a prefix rule would allow paths that Mentis asks about.
