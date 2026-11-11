# Working on Mentis (for agents and developers)

Read README.md first: it says what Mentis, MARS, Git and the future Fluid applications
each own. This file is how to work here without breaking those boundaries.

## Boundaries that must hold

- **Mentis never runs agents itself.** All agent execution goes through
  `mentis.execution` to MARS over ACP. Do not add runtime adapters, process
  supervision, watchdogs, wake checks, recovery heuristics or retry loops to Mentis:
  that machinery is what Mark IV accumulated and this repository deliberately left
  behind. If an agent misbehaves, the fix belongs in MARS or in the request, not in a
  Mentis-side handler. Two bounded mechanisms are approved (owner, O7, 2026-11-10) and
  are not exceptions to this rule; see "Background work" below for what makes them
  acceptable and what remains prohibited.
- **A finished run is not finished work.** `RunResult` reports how a session ended.
  Whether work remains is decided from the record (the request, its stage, what was
  returned). Unfinished work is continued by addressing it to an agent again
  (re-addressing, `continues`, `delegate`), with the recorded context.
- **Authority goes through one door.** Every agent operation is checked by
  `/api/worker` against a grant, using `mentis.worker.permitted`. Add a capability by
  adding an operation there, never by a side route. Reads stay reads. During the Rust
  migration it is still one door, with two implementations (below).
- **The record is append-only.** Never rewrite or delete entries; Brain format, record
  ids and relationships must stay readable by Mark IV and by this build.
- **Git belongs to the work.** Mentis does not manage worktrees, park branches, clean
  residue or make commits on anyone's behalf. Use ordinary Git.
- **Applications use the HTTP API.** Shared behaviour goes in `mentis/`, not in an app.

## Background work: what is approved and what is not

Approved by the owner (O7). Keep both bounded exactly as described here:

- **Activity-bound runtime maintenance** (`mentis.core.service`: `keep_current`,
  `_backends`, `capacity_prime`). The server keeps MARS's catalogue held so a dispatch
  never waits on it. It primes once at start. After that it asks MARS again only while a
  dispatch happened within `ACTIVE_WINDOW_S`, every `KEEP_BACKENDS_S`. An idle server asks
  MARS nothing. Capacity is never read to keep anything warm: a dispatch starts one read
  when it begins. One keeper runs per service, and it ends when the service closes. A
  failed refresh keeps what is held. It never marks an exhausted runtime as available. An
  exhausted runtime (for example K3 without quota) must stay reported as exhausted, and
  quota-aware selection decides on what MARS reported. Tests:
  `tests/test_execution_continuity.py::test_keep_current_*` and
  `tests/test_bounded_maintenance.py`.
- **Client-side durable delivery** (`mentis.outbox`, the bridge in `mentis.worker.serve`).
  A hand-started session keeps each write in a local outbox file under its `op_key` until
  the server answers. It resends kept writes only when the session itself acts: at the
  session's start (writes from its own earlier, ended sessions) and before its next tool
  call. Resending stops at the first answer that is lost again. A refused resend is
  acknowledged and told to the agent. It is never tried again. A kept write is given up
  after `MAX_AGE_S` (7 days). The server records a keyed write once, however often it
  arrives (`mentis.opkeys`). There is no timer, thread or service behind any of this.

Still prohibited: anything that wakes on its own to look for work or failures. That
includes watchdogs, wake checks, polling loops over runs or the record, timers that
retry dispatches or restart agents, unbounded resend or retry, and background services
added to keep something warm while nothing is happening. A new background mechanism
needs three things: an owner decision, a stated bound (what starts it, when it stops,
at most how often or how many), and a test of that bound. Restarting an execution after
a consent change (O2) is not a loop. It is one decision per owner action, with a restart
limit. It never overrides an owner's Stop.

## During the Rust migration

The destination is a fully Rust-owned backend, with the Brain unchanged and MARS separate
(`docs/rust/README.md`). Until it arrives:

- **Rust owns HTTP; Python temporarily keeps what hasn't moved.** A front on the public
  port answers what the route table gives it and forwards everything else to Python on a
  private loopback port. Python runs beside the front, not under it: a launcher starts
  both and nothing restarts either, so this is not the supervision ruled out above.
- **One door, two implementations, until the last write family moves.** Rust's door
  answers reads it owns; Python's checks everything else, and every write. A generated
  matrix covers every operation against every grant shape, and allow, refuse and the
  wording must match. A grant Rust doesn't hold is forwarded, never refused or served.
  Authority and one-door semantics don't change: no side route, no second rule, and a
  Rust check is never carried into a Python write.
- **Once Rust owns a responsibility, it changes in Rust.** The Python fallback stays
  compatible until it is retired. No permanent dual implementation, and no known semantic
  divergence: a difference between them is a defect to fix, not a difference to list.
- **Rust never writes the Brain** until the release that has its own owner approval.

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

## Working with Mentis from a CLI

Attach `tools/mcp_bridge.py --session <runtime> --server <url>` to the CLI. For an
agent started directly through MARS, supply that command as the `mentis` MCP server in
the ACP session's `mcpServers`; keep it session-local rather than changing machine-wide
configuration.

At the start of a piece of work, call `orient` and `recall`, then `record_request` in
the Conversation carrying the work. `brief(conversation, expectation=…)` then gives the prepared orientation for that request -- Persona, Workflow,
condensed governance, Task Gravity and what the Brain knows -- as compact rendered blocks (`detail: true` for the
structured form). Pursue recorded side work yourself with `take_up` only where its Task Gravity allows. At the end call `record_outcome`; if the work
produced a durable finding or lesson, call `record_material` separately with the
outcome Turn as its basis. Record the work boundary and what was learned, not every Git
commit. Personal CLI memory is a useful cache, but durable cross-runtime lessons and
owner decisions belong in Mentis.

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
