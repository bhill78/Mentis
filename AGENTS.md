# Working on Mentis (for agents and developers)

Read README.md first: it says what Mentis, MARS, Git and the future Fluid applications
each own. This file is how to work here without breaking those boundaries.

## Boundaries that must hold

- **Mentis never runs agents itself.** All agent execution goes through
  `mentis.execution` to MARS over ACP. Do not add runtime adapters, process
  supervision, watchdogs, wake checks, recovery heuristics or retry loops to Mentis:
  that machinery is what Mark IV accumulated and this repository deliberately left
  behind. If an agent misbehaves, the fix belongs in MARS or in the request, not in a
  Mentis-side handler.
- **A finished run is not finished work.** `RunResult` reports how a session ended.
  Whether work remains is decided from the record (the request, its stage, what was
  returned). Unfinished work is continued by addressing it to an agent again
  (re-addressing, `continues`, `delegate`), with the recorded context.
- **Authority goes through one door.** Every agent operation is checked by
  `/api/worker` against a grant, using `mentis.worker.permitted`. Add a capability by
  adding an operation there, never by a side route. Reads stay reads.
- **The record is append-only.** Never rewrite or delete entries; Brain format, record
  ids and relationships must stay readable by Mark IV and by this build.
- **Git belongs to the work.** Mentis does not manage worktrees, park branches, clean
  residue or make commits on anyone's behalf. Use ordinary Git.
- **Applications use the HTTP API.** Shared behaviour goes in `mentis/`, not in an app.

## Brains

- Never open the live Brain (`%LOCALAPPDATA%\Mentis\Mark-IV\brain`) from a development
  server or test. Make a copy with SQLite's backup API from a read-only connection
  (`file:...corpus.db?mode=ro`), plus `mentis-corpus.json`, `presentation/`, `derived/`.
- Tests that read a real Brain take its copy from `MENTIS_TEST_BRAIN` and must leave it
  byte-for-byte unchanged (`tests/test_brain_compat.py` checks).

## Developing

- Native Windows first; source and Git on the Windows filesystem, outside the user
  profile (e.g. `C:\Work\Mentis`). Docker (`compose.yaml`) is for Linux checks and
  isolated tooling against the same host checkout; it is never required.
- Several agents may work at once, each in its own plain clone or branch. Integrate with
  ordinary `git merge`. Codex's sandbox makes `.git` read-only: its work is committed by
  whoever integrates it.
- Tests are targeted: run the tests for what you changed, and the execution-boundary
  tests when touching dispatch or `mentis.execution`. Live tests (`-m live`) need a real
  MARS and logged-in runtimes. Mark IV's full suite is not this repository's process.
- Mark IV is the reference: when behaviour is unclear, read how Mark IV did it
  (`github.com/bhill78/Mentis-Mark-4`), and lift rather than reinvent.

## Workspace hygiene

Ordinary housekeeping, done by whoever coordinates the work (usually the CLI agent
integrating it) with plain Git. It is not a service, a lifecycle, or a reconciler:
nothing in Mentis or MARS creates, tracks or cleans workspaces.

- **Look before creating.** Before a new clone, worktree or branch, list what exists:
  `git worktree list`, `git branch -vv`, `git branch -r`, and the extra clones beside the
  repository (by convention `C:\Work\Mentis-wt\<name>`, `C:\Work\MARS-wt\<name>`), with
  `git status` and `git log --branches --not --remotes` in each. Reuse a clean one
  that fits rather than adding another.
- **One per piece of work**, named for the work (`fix-sources`), not for the agent.
  Temporary Brain copies and server workspaces follow the same rule.
- **Remove after integration and push.** Once a branch is merged and the result pushed
  (`git merge-base --is-ancestor <branch> origin/main`), delete its clone or
  `git worktree remove` it, `git branch -d` the branch, and delete its temporary Brain
  copy and server workspace. Use `-d`, never `-D`: refusal means it is not merged.
- **Never delete work.** A workspace with uncommitted changes, stashes, or commits not in
  `origin/main` is kept and reported (path, branch, what is unfinished), not removed.
  Remote branches are deleted only when the owner agrees.
