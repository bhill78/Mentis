# Two environments, one release path

    Build -> TEST -> Accept -> DAY-TO-DAY

## "Deploy to DAY-TO-DAY" is the whole lifecycle

Owner decision, 2026-11-19, standing. A deployment to DAY-TO-DAY is **not complete** until all
eight hold for the release production runs:

1. All approved changes are committed.
2. They are integrated into the main branch of each repository they belong to (Mentis, MARS).
3. Main is pushed, and the remote confirms it.
4. The release's artifacts are built from those exact commits.
5. Required tests and independent review passed.
6. The release was verified on TEST.
7. It was promoted to DAY-TO-DAY without interrupting active work.
8. Production's health and the identity of what it runs were verified.

A request to deploy to DAY-TO-DAY is a request for all of it, integration and push included; it
is never permission to include anything but the approved change. One command does it and stops
at the first condition that does not hold:

    mentis_env.py production <id> --owner-approved "<the owner's words>"

and one command says where a release stands, from evidence read now (the remote itself, the
commit's own tree, the release folder, the records, the running server):

    mentis_env.py lifecycle <id>          exit 0 only when all eight hold

The four things the workflow keeps apart:

| | Command | Needs |
|---|---|---|
| Prepare and test a candidate | `build-binaries`, `build`, `deploy test`, `record` | a commit that contains what TEST serves (the integration branch); exact commits and hashes |
| Integrate and push | `production` (fast-forward only), or ordinary Git | the owner's words |
| Promote a verified candidate | `production`, or `promote` alone | every check below |
| Confirm a completed release | `lifecycle`, `status` | nothing: they only read |

**TEST** is a persistent integration environment (owner, 2026-11-19): it serves the integration
branch `test/integration`, into which accepted work is merged, and nothing integrated leaves it
because something else needs verifying. A candidate need not be on `main`, but it must CONTAIN what
TEST serves: `deploy test` asks Git whether the serving release's commit is an ancestor of the
candidate's and refuses, changing nothing, when it is not, listing the commits that would be
dropped. Removing integrated work is the owner's decision
(`--replaces-integration "what and why" --owner-approved "..."`, recorded). `rollback test` goes
back to a release TEST already served and is not subject to this. To verify something in
isolation, use the rehearsal environments. A release still names the exact commit of its
code and of every binary in it, and their hashes. A TEST deploy stops for runs in flight;
ending them needs `--interrupt-runs` **and** `--owner-approved` with the words for that.

**DAY-TO-DAY** is refused unless:

- the release's commit, and the commit each binary was built from, are on the **remote** main of
  their repository (`sources` in `environments.json`), asked of the remote with `git ls-remote`
  at that moment. A local `main` or `origin/main` is not evidence;
- the release's `code/` is `git archive` of its commit, file for file; the interface was built
  from that commit by this tool (or is byte-for-byte one an intact release built from the same
  `apps/fluid-web` tree); each binary is one `build-binaries` built from a commit, or one the
  owner attested (`attest-binary`, reported as an attestation);
- review, tests, browser and owner gates are recorded as passed after TEST verified it, and
  TEST is serving it now;
- no run is in flight. A promotion cannot be told to interrupt runs: it waits.

**When main has advanced.** If the remote main of Mentis, or of MARS, has commits the release
does not, promotion stops and lists them: build a release from main as it is and verify that on TEST, or state why
the older commit is the one to run (`--main-ahead-ok "why"`, recorded). If the candidate
branched before main moved, `production` pushes nothing: integrating would need a merge, the
merge is a new commit nobody tested, so it is ordinary Git work followed by a new release and a
new verification. Nothing is ever merged into a release silently. Every repository is checked
before anything is pushed to any of them, and each push is recorded as it happens. A local
`main` that is checked out in a worktree is never moved by the tool: that is its owner's
`git merge --ff-only`.

**Runs in flight, and draining.** Runs are counted when a switch is prepared. At the last moment
before anything is stopped the server is asked to **drain** (`POST /api/server/drain`, the
owner's route: trusted-local mode, or `MENTIS_OWNER_TOKEN`): from that moment it starts no new
run, and it answers, in the same moment, how many dispatches it holds (`mentis/web/drain.py`).
Zero, and the last thing asked of it before the stop is to mark itself as **stopping**: it does
that only if it still holds nothing (decided in the same moment), and then stays draining for
longer than the stop can take to kill its backend. That duration (`STOP_DRAIN_S`, 306 s) is not
an estimate: every step of the stop before the backend is killed has its own named timeout (the
identity checks, the front's stop command, the wait for the front, each `taskkill`), their sum
is `STOP_BEFORE_KILL_MAX_S` (276 s), and the tool refuses to stop a server that states a shorter
duration. A step that runs out of its time fails the stop; it never waits on. The server
measures every duration on its monotonic clock, so a clock correction neither ends a drain
early nor keeps one late, and the tool reads the duration the server states (`lasts_s`), not
wall-clock stamps. So no run the server starts can begin before the process that starts runs is
gone, and "no run was interrupted" rests on that answer and on the stop having finished inside
it; the record says so in words (`runs_interrupted_rests_on`). Anything else, and the drain is cleared, work
goes on, and the switch is refused with nothing stopped. `--wait-for-runs SECONDS` waits that
long for held runs to finish, the server starting nothing new meanwhile (default 0: refuse at
once); if they have not finished, the drain is cleared and the switch refused. (`production`
still refuses, before it pushes anything, when runs are in flight at its start: its wait covers
runs that began while it integrated.) Runs already going
are never stopped by a drain. A start the server refused while draining is recorded on its
request as a failure before start, saying why, and listed in the result (`drain.starts_refused`):
the work stays open. **Nothing restarts a refused start**, whether the deployment went ahead or
was cancelled: not the server, not the tool, and not delegation recovery at the next start (a
child that failed before start is not one recovery reads; its rule is unchanged). That includes
what the server would have started by itself, such as the resumption of work whose child
finished during the wait. Whoever deploys reads the list and addresses that work again.

**A drain belongs to the deployment that set it.** The server gives each drain an id in the
answer to the call that set it (never in a read), and the tool names it on every later call:
extend, stopping, clear. A call that names another drain, or none, changes nothing, so a
request that arrives late from a deployment that gave up cannot end a newer drain or its
stopping phase, and a second deployment cannot take over a server that is already draining (it
is refused, and that drain is not touched). What ends a drain: a clear naming it; its bound
(120 s after the last call for it; the stopping phase after the duration it was given, at most
600 s); the process ending. The owner can also end an ORDINARY drain that is not theirs to
name, with `{"on": false, "force": true}` on the same route, logged as forced. A stopping drain
is never force-cleared: by then the tool is killing the server. `/api/working` and
`/api/server` report `draining`.

**When the stop itself fails** part way (a step ran out of its time, a port is still held), the
tool does not tell the server to take work again: what is still running is not known. It
reports FAILED, saying that a backend still alive stays draining until its stopping bound and
then takes work again by itself, and starts nothing. Look at `status`.

**What a drain does not cover.** A hand-started CLI session (`/api/worker/session`, the MCP
bridge) is not a run the server started: it is not counted as held and a drain does not wait
for it. A restart breaks the bridge call it has in flight and ends its grant; the CLI process
itself goes on, and its bridge resends the writes it kept in its outbox when the session next
acts.

**A server from before the drain** (it answers 404 to the request) is handled as it always was:
runs are counted again at the last moment before the stop, and the result says no drain was
available (`drain.used: false`). THE OLD RACE REMAINS for such a server: a run that begins in
the instant between that count and the stop cannot be prevented, and the tool never claims it
was:
after the restart it reads the record back, and a run the restart ended is listed
(`runs_ended_by_restart`), condition 7 does not hold, and the deployment is reported INCOMPLETE.
A run that was already open and unheld before the stop, and had started while the stopped
server process was alive, may have been a dispatch caught between being recorded and being
taken hold of: it is listed as not excluded, and condition 7 then does not hold either (only a
run older than that server process is excluded). The same when the environment was not
answering but processes of it were alive and were stopped. "No run was interrupted" is said
only when the record was read back and leaves no such doubt; otherwise it is reported as not
known, and the deployment as incomplete.

**A gate record** names who (`--by`) and what was run or read and where its output is
(`--evidence`); neither can be blank.

**Binaries.** `mentis_env.py build-binaries --component mars|front --commit <commit>` archives
that one commit, runs `cargo build --release --locked`, and records beside the releases
(`releases\BINARIES.json`) which commit each resulting file is. `build` refuses a binary it does
not know the commit of.

**Failure.** Nothing reports success for a partial deployment. `production` and `promote` end
non-zero and print the eight conditions with what is missing; each attempt is appended to
`<root>\lifecycle\<id>.json`. Source history is never rolled back, runs are never interrupted,
and a failed check is never skipped to finish.

**Emergency.** `promote <id> --owner-approved "..." --emergency "<the owner's words>"` waives
exactly one thing: that a source commit is not on its remote main yet. Gates, TEST and artifact
checks still apply. It is recorded with what it waived, the deployment stays INCOMPLETE in
`status` and `lifecycle`, and no ordinary release is promoted over it until main has the source.

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
reads a checkout's HEAD. It also shows the candidate under test, its four gates (review, tests, browser,
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
    mentis_env.py record <id> tests   --result pass|fail --by <who> --evidence "<what ran, and where its output is>"
    mentis_env.py record <id> owner   --result pass|fail --by owner --evidence "<the owner's words>"

The latest record of each gate decides it. A gate nobody recorded is `missing`, never passed.
Review is by a runtime other than the author's. Browser means a person or agent drove a real
browser; HTTP 200 is not that. Owner acceptance is the owner's own, never recorded for them.
Merging source and approving production are separate: nothing here merges, and no merge deploys.

## Promotion to DAY-TO-DAY

    mentis_env.py promote <id> --owner-approved "<the owner's words for this promotion>"

Promotion alone, with the same checks as `production` (it does not integrate or push). Refused
unless: all four gates passed; the release was served and verified in TEST; TEST is serving it
**now**; its source is on the remote main and its artifacts are its commits' (above); and
`--owner-approved` is given. It then starts DAY-TO-DAY from the same folder TEST ran. Nothing is
rebuilt. It refuses while runs are in flight and cannot be told to go on, and refuses a
migrating release without `--migrate`. It repoints `start-mentis.ps1`, keeping
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
