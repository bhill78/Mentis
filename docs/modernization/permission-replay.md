# Permission-policy equivalence replay (experiment E3, WS-A)

Tool: `tools/permission_replay.py`. Brain: `C:\Work\Mentis-brains\pre-eff-cbfabaa-20261108\corpus.db`,
opened read-only (`sqlite3` URI `mode=ro`). No Mentis Store or server was opened on it. Run on
2026-11-10, on `mod-perm`. It takes about 390 s.

## Result

This is the second run, made after the security review. It reflects two changes:

- Only `mentis-tools` and `approve-all` are compiled.
- Rules are evaluated as MARS applies them: allow rules only when the consent MARS hears is
  `task` (Approve All is sent as `task`), and deny rules as Claude `ask`, so they reach Mentis.

| | count | share |
|---|---:|---:|
| Recorded `operation-answered` acts | 37,388 | 100% |
| Claude / Gemini | 37,372 / 16 | |
| Runs | 964 | |
| **Compiled verdict MORE PERMISSIVE than Mentis** (all four rule readings) | **0** | 0% |
| Compiled more restrictive | 0 | 0% |
| Decided by a compiled rule (allow), never reaching Mentis | 32,860 | 87.9% |
| Not matched by any applied rule, so reaching Mentis as today | 4,528 | 12.1% |
| Agreement (effective verdict = Mentis verdict) | 37,388 | 100% |

The gate holds: nothing is more permissive. So `COMPILED_SCOPE_RUNTIMES = {"claude"}`.
Gemini, Codex and Antigravity are not compiled; agy keeps its existing `allow` option.

### Per operation class (each compiled alone, then together, as MARS applies them)

| Class | Compiled | Rule allows | More permissive |
|---|---|---:|---:|
| `mentis-tools` (`mcp__mentis__*`) | yes | 9,831 | 0 |
| `approve-all` (every tool by name, no deny) | yes | 32,787 | 0 |
| `file-reads` (`Read(//ws/**)`) | **no** | 0 | 0 |
| `file-edits` (`Edit(//ws/**)`) | **no** | 1,787 | 0 |
| **compiled (`mentis-tools` + `approve-all`)** | | **32,860** | **0** |

`file-reads` and `file-edits` showed no broadening in the record, yet they are not compiled.
Mentis resolves real paths and Claude matches literal ones. A symlink, junction or 8.3 name
inside a workspace that leads to a protected location would pass the path rule where Mentis
asks. The record cannot show equivalence for that case.

Of the rule allows, 32,787 come from runs under Approve All. The other 73 are Mentis tools
under `task`. Under `ask` and `deny`, MARS applies no allow rule, so the 1,557 Mentis-tool
calls in `ask` runs still reach Mentis. By recorded answer, the rules take over 21,558
`grant` answers and 11,302 `all` answers.

What still reaches Mentis:

- everything outside Approve All except Mentis tools under `task`;
- shell commands, file reads and edits outside Approve All;
- owner questions, research, and tools allowed for one run.

### Rule-semantics readings

Each request was evaluated under four readings of Claude's matching: case-insensitive or
case-sensitive, crossed with Read rules reaching Grep and Glob or not. All four gave identical
results: 32,860 allowed, 0 more permissive. The first run of the replay, before the review,
compiled all four classes and treated deny as refuse. It gave 34,428 allowed, 0 more
permissive and 1 more restrictive.

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
- The recorded detail is not the raw request: commands are cut at 2,000 characters and paths at
  5. Classification ran against today's filesystem, and some workspaces no longer exist. These
  limits affect M and the fidelity figure, not the rules.
- Rules are compiled per session. A narrowing during a run halts that run and restarts the work
  in a fresh session (CONTRACT.md Deviation 3). The replay compares rules from the start of each
  run with the verdict at each answer, so it measures the outcome without that restart, the
  worst case: still 0 more permissive.
- Symlinks, junctions and 8.3 names are why the path classes are not compiled (see above).
- Shell commands are not compiled. Equivalence would require reproducing Claude's command
  splitting, and a prefix rule would allow paths that Mentis asks about.
