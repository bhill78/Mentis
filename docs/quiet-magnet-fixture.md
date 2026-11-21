# Disposable Quiet Magnet fixture and preview

These helpers prepare a synthetic, local fixture. They never read DAY-TO-DAY or
persistent TEST, inherit credentials, bind production sources, dispatch agents,
activate a Magnet, or create a synthesis or Perspective.

Run from the candidate repository root using the existing test Python environment:

```powershell
C:/Work/Mentis-workspace/r1-fixtures/venv/Scripts/python.exe tools/quiet_magnet_fixture.py seed --root .preview/quiet-magnet
```

`seed` refuses an occupied directory. Its root must be inside the checkout. Keep
`.preview/` out of Git (add it to `.git/info/exclude` for this checkout). The output
manifest gives the actual IDs; a newly seeded fixture has new IDs.

The main fixture contains separate origin A, source B, and Magnet C Conversations;
two authors; 36 source contributions including a reply; eight before a real time
boundary; a held Markdown document, a human-ingress attachment and a small PNG,
each named on a source post. Two saved Magnets occupy A's arrangement. Only the
primary Magnet has C. A second, smaller Brain supplies a distinct corpus identity.

Creation of C uses the existing
`magnet_definition_command(... MAGNET_DEFINITION_ACTS['conversation'] ...)`
operation, the in-process implementation of the own-Conversation POST. It creates
the durable `own-conversation-claimed` act and sets the definition reference. The
fixture never forges `conversation` in a seed or manually changes record rows.
Other setup uses `api.create_corpus`, Conversation operations, artifact holding and
stage/submit/record operations, and `arrangements.create_magnet`.

Build the front from the candidate's Rust sources in an isolated target directory:

```powershell
cargo build -p mentis-server --release --offline
```

Build the candidate UI through its normal `apps/fluid-web` build before starting
the final preview. Both `dist/index.html` and `dist/render-check.js` are required.
After claiming three unused ports, run:

```powershell
C:/Work/Mentis-workspace/r1-fixtures/venv/Scripts/python.exe tools/quiet_magnet_preview.py --root .preview/quiet-magnet --front target/release/mentis-server.exe --launcher target/release/mentis-launch.exe --dist apps/fluid-web/dist --python-port 8931 --front-port 8932 --preview-port 8933
```

This command remains in the foreground. For a durable preview, the carrier must
arm the request's detached result reporting and start it hidden. It launches the
existing pair launcher with `--attached`, a fresh private run directory, an explicit
fixture Brain, candidate code/build, and an intentionally unavailable MARS command.
The Node access path has one explicit loopback fixture target. `/__q2/brain` marks
the UI read-only. Every non-read method and the known writing capacity GET are
rejected before forwarding, including encoded capacity paths. No production target
or Brain-switch route exists. Requests and forwarding/refusal outcomes go into
`traffic.jsonl`; authority headers and browser cookies are stripped.

The helper checks Python/front/manifest identity, then warms each object cursor
through bounded GET reads before taking `runtime-baseline.json`. The existing
route extracts at most four cold posts per request and may require repeated reads
of the **same partial page**. It records that setup in `setup-warm.json`. Cache
state is memory-only in the existing Rust extractor. It never advances a partial
cursor until that page answers `ok`, and it stops on a refusal or its fixed bound.

`ready.json` contains the checked preview URL, helper/launcher/preview/Python/front
PIDs, executable digests, manifest/baseline paths and probe evidence. It contains
no boot secret. The launcher's private state does; do not publish that file. In
`--verify-only` mode the helper runs the checks and stops its owned processes; that
is a completed contract probe, **not a running preview**. A normal run stays alive
without restart. Its finally path stops only PIDs from its own fresh launch state
and subprocess handles. On a sandbox that cannot terminate the launcher's siblings,
run this helper with the required process-cleanup permission; do not kill processes
by name.

The carrier's browser trial starts after `runtime-baseline.json` exists. Compare:

```powershell
C:/Work/Mentis-workspace/r1-fixtures/venv/Scripts/python.exe tools/quiet_magnet_fixture.py compare --root .preview/quiet-magnet --baseline .preview/quiet-magnet/runtime-baseline.json --out .preview/quiet-magnet/runtime-compare.json
```

The comparison reads SQLite with `mode=ro` and hashes a logical dump of every table,
including table counts, so WAL activity cannot hide a record change. It hashes all
presentation, held artifact and other content files, including files in the
separate instance service corpus. Database/WAL physical bytes and OS lock files
are excluded from the file comparison; the main record is covered by the logical dump. No source cache or
production binding is configured. Runtime no-write evidence must combine unchanged
snapshots with request traffic; a hidden button alone does not prove it.

Focused checks:

```powershell
New-Item -ItemType Directory -Force .pytest_tmp | Out-Null
C:/Work/Mentis-workspace/r1-fixtures/venv/Scripts/python.exe -m pytest -q tests/test_quiet_magnet_fixture.py --basetemp .pytest_tmp/quiet-magnet-fixture
node tools/test_quiet_magnet_preview.mjs
```

The first checks fixture preconditions, existing-directory/path refusal and
read-only snapshot stability (3 tests). The second checks 13 access-boundary cases.
The final integrated candidate still needs its own focused checks and headless
Windows browser evaluation; this fixture handoff makes no UI or overall Work claim.
