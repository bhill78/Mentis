# Two environments, one release path

    Build -> TEST -> Accept -> DAY-TO-DAY

| | DAY-TO-DAY (production) | TEST |
|---|---|---|
| Address | http://127.0.0.1:8760 | http://127.0.0.1:8780 |
| Brain | `%LOCALAPPDATA%\Mentis\Mark-IV\brain` | `C:\Work\Mentis-env\test\brain` |
| Processes | its own front, backend, MARS | its own front, backend (MARS only when agents are on) |
| Gets | releases the owner approved, already verified in TEST | candidate releases |

Development branches and worktrees are not environments. `environments.json` defines the two.
Everything below is `python tools\env\mentis_env.py <command>` (use `C:\Work\Mentis\.venv\Scripts\python.exe`).

## What is running where

    mentis_env.py status

This is the one authoritative answer. It asks each running server what it is, hashes what its
processes actually run from, and names the release whose components match **by content**. It never
reads a checkout's HEAD. It also shows the candidate under test, its three gates (review, browser,
owner), whether it is ready, and what each environment can roll back to.

## A release

One folder under `C:\Work\Mentis-env\releases\<id>\`, never changed after it is built:

- `code\` is `git archive` of one commit, with the built interface in `code\apps\fluid-web\dist`.
  `code\BUILD.json` makes the server itself report the release id at `/api/server`.
- `bin\` holds `mentis-launch.exe`, `mentis-server.exe`, `mars.exe` and where each came from.
- `RELEASE.json` is the identity: commit, each component's digest, the Brain schema it reads, and
  every file's sha256. `mentis_env.py verify <id>` checks the folder against it.

Build one (the description is required and is in plain words):

    mentis_env.py build --commit <commit> --describe "what this contains, in plain words"

The front and MARS are reused from the newest release unless `--front-from` / `--mars-from` name
new ones. A reused front is refused when `crates/` at the commit differs from what it was built
from, unless `--front-differs-ok "why"` says the older front is right.

## Candidate to TEST

    mentis_env.py deploy test <id>

Stops TEST, starts it from the release folder, checks that what answers **is** that release, and
records it. If it does not verify, TEST goes back to the release it was on. It never touches
TEST's data. A release that would migrate the Brain is refused without `--migrate`.

## Acceptance

    mentis_env.py record <id> review  --result pass|fail --by <who> --evidence "<where>"
    mentis_env.py record <id> browser --result pass|fail --by <who> --evidence "<where>"
    mentis_env.py record <id> owner   --result pass|fail --by owner --evidence "<the owner's words>"

The latest record of each gate decides it. A gate nobody recorded is `missing`, never passed.
Review is by a runtime other than the author's. Browser means a person or agent drove a real
browser; HTTP 200 is not that. Owner acceptance is the owner's own, never recorded for them.
Merging source and approving production are separate: nothing here merges, and no merge deploys.

## Promotion to DAY-TO-DAY

    mentis_env.py promote <id> --owner-approved "<the owner's words for this promotion>"

Refused unless: all three gates passed; the release was served and verified in TEST; TEST is
serving it **now**; and `--owner-approved` is given. It then starts DAY-TO-DAY from the same
folder TEST ran. Nothing is rebuilt. It refuses while runs are in flight (`--interrupt-runs` to go
on) and refuses a migrating release without `--migrate`. It repoints `start-mentis.ps1`, keeping
the old one beside it.

DAY-TO-DAY is currently started the older way (its own run script and checkout). `status` already
identifies it by content as the baseline release. Its first promotion moves it onto release folders.

## Rollback

    mentis_env.py rollback test
    mentis_env.py rollback day-to-day --owner-approved "<the owner's words>"

Starts the environment's previous release folder. No Git history is rewritten and no interface
folder is reconstructed. It is refused when the Brain has since been migrated past what the older
release can read: that needs a forward fix.

## Start and stop

    mentis_env.py start test        (after a reboot; it outlives the session that ran it)
    mentis_env.py stop test

Nothing restarts either environment by itself. `stop day-to-day` needs `--owner-approved`.

## TEST's data

TEST was populated once from production by `mentis_env.py snapshot`, using Mentis's own
`mentis.brain backup --portable` and `restore` (see `snapshot.py` for exactly what is changed in
the copy and why). `C:\Work\Mentis-env\test\SNAPSHOT.json` records when and how. A deploy never
refreshes it, and `snapshot` refuses while TEST has a Brain. A refresh is the owner's separate,
explicit decision.

TEST is independent of production:

- its own Brain folder, owner credential, run directory, ports, source bindings, source cache,
  MARS data and resume key; stored files are copies, not hardlinks;
- **agents are off** (`"agents": false`): no MARS is started, so anything dispatched fails and is
  recorded as failed, including what a start would otherwise recover from the copied record.
  Turning them on is one word in `environments.json` and a restart, and is the owner's decision:
  an agent run in TEST uses the owner's runtime accounts and runs on this machine;
- runs get no user-level MCP servers (`mcp-policy.json` in the copy).

## Rehearsing

`rehearsal_setup.py <C:\Work\Mentis-env\rehearsal> <release id>` makes three throwaway environments
on fixture Brains (one with the `production` role) so promote, rollback and snapshot can be proved
with `--config <root>\environments.json` without touching either real environment.
