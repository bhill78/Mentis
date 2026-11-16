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
owner), whether its checks have passed, and what each environment can roll back to.

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

Nothing restarts either environment by itself. `start` and `stop` of `day-to-day` need
`--owner-approved`.

## What the tool will not be talked into

- An environment that uses DAY-TO-DAY's ports (8760, 18760) or anything under
  `%LOCALAPPDATA%\Mentis` or `%LOCALAPPDATA%\mars` is production whatever a configuration file
  calls it; a file that labels it `test` is refused.
- A release is named as served only when every observation agrees: backend code, the interface on
  disk **and** the page actually served, the front and MARS executables, the route table, the
  Brain, and the release the server itself reports. Anything that does not agree is the reason no
  release is named. The shared Python and its installed packages are hashed by content: TEST is
  where a release's runtime is established and recorded, and production must be on exactly what
  TEST last verified the release with.
- `status` never says an unconditional "ready". When every gate and every check that can be made
  without touching production has passed, it says so and lists what is still decided at promotion:
  the owner's approval, and the migration plan of the production Brain, which is made only then
  and can refuse. Readiness never runs a candidate's code against the production Brain.
- A rollback only goes back to a release that environment has actually served.
- A release folder is checked against a manifest digest kept outside it (`releases\INDEX.json`).
- Processes are stopped only while they are still the ones the launcher recorded (pid and start
  time, re-read immediately before each kill).
- Gates are recorded only for a release TEST has served and verified.

## TEST's data

TEST was populated once from production by `mentis_env.py snapshot`, using Mentis's own
`mentis.brain backup --portable` and `restore` (see `snapshot.py` for exactly what is changed in
the copy and why). `C:\Work\Mentis-env\test\SNAPSHOT.json` records when and how. A deploy never
refreshes it, and `snapshot` refuses while TEST has a Brain. A refresh is the owner's separate,
explicit decision.

TEST is independent of production:

- its own Brain folder, owner credential, run directory, ports, source bindings, source cache,
  MARS data and resume key; stored files are copies, not hardlinks;
- **agents are on** (`"agents": true`, the owner's decision of 2026-11-16): TEST starts its own
  MARS from the release's `bin\mars.exe` with TEST's own data folder, resume key and backends
  file, so its sessions and execution history are TEST's alone. Runs use the owner's runtime
  accounts and run on this machine. No consent in TEST reaches the production Brain or MARS
  data: `%LOCALAPPDATA%\Mentis` and `%LOCALAPPDATA%\mars` are protected paths in every Mentis.
  Setting `"agents": false` and restarting puts `agents_off.py` where MARS would be: no runtime
  is listed and anything dispatched fails and is recorded as failed;
- runs get no user-level MCP servers (`mcp-policy.json` in the copy).

## Rehearsing

`rehearsal_setup.py <C:\Work\Mentis-env\rehearsal> <release id>` makes three throwaway environments
on fixture Brains (one with the `production` role) so promote, rollback and snapshot can be proved
with `--config <root>\environments.json` without touching either real environment.
