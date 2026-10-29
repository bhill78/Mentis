# Run-scoped execution consent (2026-10-29)

The contract the Mentis, MARS and Fluid parts of run consent build to. An authorized
development task proceeds through ordinary operations inside its approved workspaces
without the owner answering the same permission question again and again; anything
beyond the task's boundary is still asked, or refused.

## What it is not

- **Not a second authorization system.** Permission requests are answered where they
  always were: MARS forwards each `session/request_permission` to Mentis, and
  `mentis/web/permissions.py` answers it under the run's grant or asks the owner with a
  decision form. Consent is one more input to that answer, read from the record.
- **Not authority from a request.** A command being asked for grants nothing. An agent
  cannot give itself consent; consent comes from the owner, on the original request or
  later on the run, and a delegated child inherits it only narrowed.
- **Not Task Gravity.** `follow_up` says whether side work may be *pursued*; consent
  says which *operations* need asking. Neither implies the other.
- **No sandbox is disabled and no shell command is auto-approved wholesale.** A shell
  command is allowed only when every part of it is classified (§3) and inside the task's
  boundary. A runtime's persistent "always allow" option is never chosen.

## 1. Consent on a request

Recorded on the owner's request as `detail.consent` of its `expectation-recorded` act
(posting: a dispatch spec's `consent`, beside `follow_up`):

```json
{"mode": "task",
 "workspaces": ["C:\\Work\\MARS", "C:\\Work\\MARS-wt"],
 "categories": ["read", "edit", "test", "build", "run", "git"]}
```

- `mode`: `"ask"` (default when absent: ask for each operation the grant does not
  already cover), `"task"` (operations within the task's boundary proceed without
  asking), `"deny"` (as `task`, but never wait for the owner: anything that would be
  asked is refused at once and logged).
- `workspaces`: absolute existing directories. The request's declared repository
  directory is always included. Never a Brain, MARS's data directory, or a credential
  location (refused in words).
- `categories`: what kinds of operation are routine for this task. Default
  `read, edit, test, build, run, git`. Optional: `delete` (recursive deletes),
  `git-remote` (fetch, pull, push, clone), `network`, `install` (package installs).

Effective consent is read from the request's lineage (`mentis.operational.consent`):
the original request's consent, replaced at any level where the owner changed it
(`consent-set`), and only ever narrowed below that. Workspaces of a child are those of
its parent; the child's own run workspace counts only when it is inside them. A
request whose lineage reaches no owner-given consent is `ask`.

## 2. Changing it on a run (owner only)

`GET /api/runs/<run>/consent` returns
`{"run", "consent": <effective>, "operations": [...], "applied": <what MARS reported>}`.

`POST /api/runs/<run>/consent` with any of:

- `{"mode": "ask"|"task"|"deny"}` changes the task's consent for subsequent
  operations. Recorded as a `consent-set` act by the owner, caused by the run's request.
- `{"workspaces": [...]}` replaces the task's workspaces; `{"add_workspace": dir}` adds one.
- `{"allow_tool": key}` / `{"revoke_tool": key}` allows or revokes one tool for this run
  only. Recorded as a `consent-set` act caused by the run (`scope: "run"`).

The effective consent is on every run row (`/api/working`, `/fluid/api/runs`) as
`consent`:

```json
{"mode": "task", "label": "Routine work in the approved workspaces proceeds",
 "workspaces": ["C:\\Work\\MARS"], "categories": ["read", "edit", "test", "build", "run", "git"],
 "tools": ["pytest"], "source": "request" | "owner-changed" | "inherited" | "none",
 "applied": {"enforced_by": "client", "workspaces": ["C:\\Work\\MARS"]} | null}
```

## 3. Operations (`mentis/operations.py`)

Every request is described as one **operation**, and the question the owner sees is that
description, never the raw command:

```json
{"summary": "Edit examples\\run_turn.py with PowerShell",
 "action": "edit", "category": "edit",
 "resources": ["C:\\Work\\MARS-wt\\local-tool-trace\\examples\\run_turn.py"],
 "workspace": "C:\\Work\\MARS-wt\\local-tool-trace",
 "why": "Working on: Repair the local backend's tool trace…",
 "agent_says": "Update the finish-tool handling",
 "tool": "powershell:Set-Content", "tool_label": "Set-Content",
 "within": true, "outside": [],
 "command": "Set-Content -Path examples\\run_turn.py ...", "cwd": "C:\\Work\\MARS-wt\\local-tool-trace",
 "kind": "execute"}
```

- `category`: `read`, `edit`, `delete`, `test`, `build`, `run`, `git`, `git-remote`,
  `network`, `install`, `mentis` (the run's own Mentis tools, already checked by
  `/api/worker`), or `other` (not classified: an unknown program, inline code,
  command substitution).
- `within`: inside the task boundary — every resolvable path it writes or runs in is
  inside the approved workspaces, it touches no protected location (Brains, MARS data,
  credentials) and no guarded file (`.git` internals, agent and editor settings), and
  its category is permitted. `outside` lists, in words, each reason it is not.

How a request is answered, in order:

1. **The run's grant** (unchanged): reads anywhere that is not protected — including a
   shell command classified wholly as `read` — the run's own Mentis tools, and edits
   inside the run's workspace that touch no guarded file.
2. **Consent**: `within`, `mode` `task` or `deny`, and the category permitted → allowed; or a
   tool allowed for this run and the operation `within` its workspaces → allowed.
3. `mode` `deny` → refused at once.
4. Otherwise **the owner is asked** with a decision form whose question is the
   operation's summary. Its options, each with a consequence:
   - *Allow once* — this operation only.
   - *Allow `<tool>` for this run* — this tool's operations inside the approved
     workspaces, until the run ends (only when `within` apart from consent).
   - *Allow within this task* — routine operations inside the task's workspaces, for
     the rest of this task (only when `within` apart from consent); or, when the
     operation is outside only because of where it works, *Allow within this task,
     adding `<dir>`*.
   - *Deny*.

   Only *Allow once* and *Deny* are offered for anything outside the boundary for any
   other reason.

The form act's detail carries `{"permission": true, "run", "operation": {...}}`, and
`Conversations.decision_form` returns it as `operation`.

## 4. The record

- `consent-set` (owner): a change of a task's or run's consent, as above.
- `operation-answered` (the run's actor): each request answered without the owner, or
  by the owner through a form: `{"operation": {summary, category, tool, within,
  command (≤ 2000 chars)}, "answer": "allowed"|"refused", "by": "grant"|"task"|"tool"|
  "owner"|"deny"|"unanswered", "form"?}`, caused by the run.
- What the run then did is already on its end act: `tool_calls` (title, kind, status,
  paths, as MARS reported them), and how MARS said consent was enforced
  (`runtime_evidence.consent_applied`). Nothing is recorded twice.

## 5. MARS (`_meta["mars/consent"]` on `session/new`)

`{"mode": "ask"|"task"|"deny", "workspaces": [abs dirs]}`. MARS:

- adds `workspaces` to the session's additional directories, so each runtime's own
  mechanism confines the work to them (Claude's added directories, Codex's sandbox
  writable roots, Antigravity's `--add-dir`);
- refuses a consent combined with options that disable a runtime's sandbox
  (Antigravity `sandbox: false`);
- still forwards every permission request and still picks no allow option itself;
- reports in the `session/new` response `_meta["mars/consent"]` what applied:
  `{"mode", "workspaces", "enforced_by": "client" | "sandbox+client" | "sandbox" |
  "none"}` — `none` for a backend that neither asks nor confines (the `local` worker's
  `full` access mode), so the record can say consent was not enforceable there.

## 6. Fluid

- Composer settings: *Each operation is asked* / *Routine work in the task proceeds* /
  *Never wait for me (refuse what would be asked)*, and the task's workspaces.
- A permission question shows what the agent wants to do, what it affects, why it
  relates to the task, and what each answer covers; the exact command is under
  *Details*.
- The run panel shows the consent in force, lets the owner change the mode and revoke
  a tool for subsequent operations, and lists the operations answered so far.
