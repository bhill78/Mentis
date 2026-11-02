# R1 acceptance

Appendix A of `PLAN-r3.md` (`adm-6e15a0d880ba`), carried over with the owner's correction (Turn #1016 `ent-b8ef5a9d035b`, Turn #1025 `ent-9a3dff0b382f`, item 1) applied. Where note `ent-beb03f957b87` says so, `adm-56082aa297b0` governs instead: its section 3.2 restart table, section 3.3 snapshot, section 5 retirement lists and section 6. Every one of its checks A1 to A15 maps to a row here, in "A1 to A15" below.

## What decides R1

**R1 may succeed by establishing a correct, usable, Rust-owned server foundation.** A release may establish infrastructure or transfer ownership without improving latency.

| | |
|---|---|
| **Mandatory, pass or fail** | Correctness, Brain safety, authority, restart behaviour, and a valid bench run. Rows A to M, O, P and Q, and row N's validity. **Any failure stops the release** |
| **Measured and reported, never pass or fail** | Everything about speed, in section "Performance". **No result there can stop, delay or re-sequence a release,** and none is re-run until it passes |
| **Always reported** | **Performance under concurrent agents, Fluid and Magnets stays a primary objective of the migration.** Every release report gives these figures, whatever they show |

### What the correction removed from r3

| r3 | Now |
|---|---|
| Section 3, requirement 3: "measured gain under concurrent load" | Measured and reported |
| Section 3: "A missed gate stops the release and is reported, and it is not re-run until it passes" | Removed. "Better than noise" stays as a **description** the report can use |
| Section 4, the R1 **gain gate** row | Removed as a gate. The comparison is reported |
| Section 4: "**If the gain gate is missed, R1 isn't offered alone**" | Removed. R1 is offered on its mandatory rows. The report says plainly what improved and what didn't |
| Section 4, marks (37.6 ms topic, 50 ms pulse) and the forwarded-overhead limit (p50 adds ≤ 5 ms, p95 no worse than noise) | Reported beside the figure, not pass or fail |
| Row N, "Section 4's marks and gain gate" | **Row N still requires a valid run with 0 bad statuses.** Its figures are reported |

**Unchanged:** every test below, kill points, the chain codec, and every Brain, authority and restart requirement. Not relaxed, not reinterpreted.

## The oracle is frozen

**Once this document's commit is reviewed, what it expects is fixed.** A package implements the frozen test under its frozen file name, to its frozen count. It doesn't choose or revise the result.

- **A test that disagrees with a frozen expectation fails.** That holds whatever the disagreement teaches.
- **Changing an expectation is a visible revision:** a commit to this document or the file it names, its reason stated in the commit and in the release report, and re-reviewed for what it changes. It is never a pass.
- **Windows is the gate.** On Windows, the expected result of each row is all passed, 0 failed, 0 errors and 0 skipped, except where a row says otherwise.
- **A row that cannot run fails.** No fixture, no browser, no logged-in runtime or no MARS means the row fails and R1 isn't accepted. Nothing here skips.

The rows' test files don't exist yet, apart from row Q's fixture checks: P1.1 to P1.5 write them. Their names and counts are final.

## Deployment

This document decides acceptance, not deployment.

| Release | Who decides | Why |
|---|---|---|
| **An accepted front-only release, with no run active** | Standing yes (Turn `ent-a60e9f7e22b4`). **The owner is told what changed** | Replaces asking per release. `docs/cutover/deploy-front.ps1` lists active runs first |
| **An accepted front-only release, with a run active** | Asked | A front restart can change a run's outcome (`docs/rust-front-restart.md`), and the standing yes covers only times with no active run |
| **Anything that restarts Python, interrupts runs, changes Brain writes or needs a semantic migration** | Asked (Turn `ent-9a3dff0b382f`, item 4) | So **R1's first deploy and R3's are asked:** each restarts Python and ends live runs |

Follows the existing release and rollback process. Independent review of implemented changes stays required; no further whole-plan review is.

## Fixtures

Everything built lives outside the repository, under `C:\Work\Mentis-workspace\r1-fixtures`, named by `$env:MENTIS_R1_FIXTURES`. **What is committed is how to build each one and what it must come out as.** A fixture that doesn't match fails its test, and never skips. **G0's fixtures are `BRAIN-SEED`, `BRAIN-COPY`, `PY-ALONE` and `LEDGER`,** built and checked at G0. `PAIR` is the system under test: see `PAIR`, below.

**Setup, once,** from this clone. `tools/r1/setup_env.py` makes the detached checkout, the test environment and Fluid's build, and installs Chromium:

```powershell
$env:MENTIS_R1_FIXTURES = 'C:\Work\Mentis-workspace\r1-fixtures'
python tools/r1/setup_env.py
```

**Every row's `python` below is that environment's,** so activate it first, and every row runs from the clone root, `C:\Work\Mentis-wt\rust-r1`, on the commit under test:

```powershell
$env:MENTIS_R1_FIXTURES = 'C:\Work\Mentis-workspace\r1-fixtures'
& C:\Work\Mentis-workspace\r1-fixtures\venv\Scripts\Activate.ps1
Set-Location C:\Work\Mentis-wt\rust-r1
```

The environment is Python 3.12.10 with exactly `docs/rust/evidence/r1-venv-freeze.txt`: `pyproject.toml`'s `dev` extra (`pytest==8.4.2`, `playwright==1.61.0`) and the runtime pins. Chromium is installed by `python -m playwright install chromium`, which for Playwright 1.61.0 is Chrome for Testing 149.0.7827.55 (`chromium-1228`), into the machine's own `%LOCALAPPDATA%\ms-playwright`.

### `BRAIN-SEED`

| | |
|---|---|
| **Committed** | `tools/r1/seed_brain.py`, `tools/r1/seed_data.json` |
| **Invocation** | `python tools/r1/seed_brain.py <new directory>`. `tests/front/conftest.py`'s `brain_seed` runs it, per test module |
| **What it is** | Python's own commands at `b8e324c`: `create_corpus`, the bootstrap baseline and Welcome tour for owner `@r1-owner`, then two Conversations, 5 Topics and 4 posts from the seed data, and the Brain's marker |
| **Reproducible by** | Pinning, not normalising. In that process alone, `uuid.uuid4` is a seeded generator and `time.time` a fixed clock. So two builds are **byte-identical** in `corpus.db`, under Python 3.12.10's SQLite 3.49.1 |
| **Identity** | `docs/rust/evidence/brain-seed-identity.json`: `corpus.db`'s SHA-256, a content digest over every column of every table that normalises nothing, `mentis-corpus.json`'s and the sibling trees' digests, code commit, and both files' Git blobs. `corpus.db` is `a429d9ee...`, 354 entries, 30 acts |
| **Checked by** | `brain_seed` compares every build with that file, and any difference fails. `test_fixture_seed.py` builds it twice |

### `BRAIN-COPY`

| | |
|---|---|
| **Committed** | `tools/r1/copy_brain.py`, and the manifest `docs/rust/evidence/brain-copy-manifest.json` |
| **Master** | `C:\Work\Mentis-workspace\r1-fixtures\brain-copy-master`. **One retained snapshot,** kept until R1 is accepted. A new one is built as in "If the master is lost" |
| **How the live Brain is read** | `corpus.db` through SQLite's backup API from a `file:...corpus.db?mode=ro` connection, the only way it is opened. Then `artifacts/`, `instances/`, `presentation/`, `derived/` and `mentis-corpus.json` are copied by name, so they are at least as new as the database. Locks, `scratch/` and `worktrees/` aren't copied. **No server or test opens the live Brain** |
| **Sealed** | Row counts, position and the chain are read once, before sealing. Every file is then read-only, and SQLite never opens the master again |
| **Manifest** | Source path, time, `advance()`, per-table row counts, chain heads, `verify_chain`'s result, code commit, the Git blob of the tool that built it, SQLite version, and digests of `corpus.db`, the marker and each tree. **A later change to the tool doesn't rewrite it:** its blob has only to be in the tool's history |
| **Each test** | `conftest.py`'s `brain_copy`, or `python tools/r1/copy_brain.py fresh <new directory> --manifest docs/rust/evidence/brain-copy-manifest.json`: a copy from the master, checked against the manifest **before use**. A mismatch raises and fails. 61.5 s here, digests included |

As built: see the evidence file. Position `39304.45666.3574`, chain intact, 7,353 artifacts of 3.3 GB.

**What is and isn't reproducible.** `adm-56082aa297b0`'s F2 is a copy of DAY-TO-DAY with "its positions and digest recorded". It never promised a byte-identical rebuild, and a Brain that keeps moving can't give one.

- **This master, with this manifest, is one retained snapshot.** It can be verified, and it can't be regenerated. It stays until R1 is accepted.
- **The definition is what's reproducible:** the recipe always yields a valid `BRAIN-COPY`, with a new identity.
- **Losing the master means building a new one** and committing its manifest as a visible revision, with the reason.

**If the master is lost.** With no master at that path, build one, with its manifest going to a new file. `build` refuses a manifest that already exists, so it can't silently replace the committed one:

```powershell
python tools/r1/copy_brain.py build "$env:LOCALAPPDATA\Mentis\Mark-IV\brain" --manifest "$env:MENTIS_R1_FIXTURES\brain-copy-manifest.new.json"
```

Until the new manifest is committed, every fresh copy fails against the old one, and so does row Q. Replacing it is a person's act: copy it over `docs/rust/evidence/brain-copy-manifest.json` and commit, with the reason in the commit and in the release report. Then re-record `baseline`: see below.

**Proved once:** `docs/rust/evidence/brain-copy-rebuild-proof.json`, by `tools/r1/prove_brain_copy_rebuild.py`. A second master was built in a scratch directory under `r1-fixtures`, through the backup API from a `mode=ro` connection, at `39352.45926.3584`. Its chain and its own manifest checked, the committed manifest refused it, and it holds each committed head at that head's `seq`. The retained master's digests, taken by hashing alone either side of the build, didn't change. The 3.3 GB scratch copy was then deleted.

**What rests on this snapshot.** No row's frozen expectation holds its position, row counts or digests: each compares a copy with its own manifest, or with itself before and after. Rows G, H, I and P are relative to whichever copy they run on, and the figures in this section and row E's 61.5 s describe this master and decide nothing. Two things do depend on it, and both hold for a later snapshot:

| What | Depends on | So |
|---|---|---|
| Rows B and N's `baseline` | **This master:** `baseline` and `R1` must be recorded on one snapshot, or a difference between them proves nothing | Each result records the master's `corpus.db` digest, and `compare` refuses two that differ (`contracts/bench.md`). A new master means re-recording `baseline` |
| The bench's fixed references, `ent-ca4a27445105` and `ent-0ceca1e70bd0` | Being in the copy | Later snapshots hold them, because the record is append-only |

### `PY-ALONE`

| | |
|---|---|
| **Copy** | `C:\Work\Mentis-workspace\r1-fixtures\py-b8e324c`, a clean detached checkout of **`b8e324c`** (`git worktree add --detach`), with Fluid's build in `apps\fluid-web\dist` |
| **Why `b8e324c`, not R1's commit** | It is the other side of a differential. P1.5 changes Python, and P1.5's changes must leave Python alone behaving exactly as today (`contracts/launcher.md`). A `PY-ALONE` running R1's Python would carry any such regression onto both sides, and a difference between the sides could never show it |
| **Environment** | The `venv` above. `MENTIS*` and `PYTHONPATH` removed. `MENTIS_FLUID_DIST` is that build, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONIOENCODING=utf-8` |
| **Command** | `cd py-b8e324c; ..\venv\Scripts\python.exe -m mentis.web <fresh copy> --port 8851 --workspace <copy>.run\ws --mars workload-no-mars-here`. `tools/r1/py_alone.py` is that, and refuses the master |
| **Port, data** | Public 8851, never 8760. The Brain is a fresh copy of the row's fixture. Workspace and log are `<copy>.run\` |
| **Fluid's build isn't byte-reproducible** | Two builds of `b8e324c` gave 16 files of the same total size and different digests. No expectation here rests on its digest: P5 asserts what the page does. `browser-proof.json` names the one it ran |
| **Proved** | `docs/rust/evidence/py-alone-proof.json`: started once on `BRAIN-SEED`. It said commit `b8e324c`, not dirty, and answered `/api/server`, `/api/pulse` and `/` with 200 in under 3 s |

### `LEDGER`

| | |
|---|---|
| **Committed** | `tools/r1/ledger.py` |
| **Format, version 1** | JSON Lines. First line `{"format": "r1-ledger", "version": 1}`. Each later line one acknowledged write: `{"id", "table", "seq", "hash"}`. Anything else is refused on reading |
| **Behaviour** | `Writer.write` holds one lock across send, append and `fsync`, so **the next write can't begin until the last one's row is on disk.** A write with no acknowledgement records nothing. `verify` names every row the record lacks or holds differently |
| **Checked by** | `tests/front/test_fixture_tools.py`, including the order of send and `fsync`, and rows surviving a hard kill of the writer |
| **In a run** | One new file per run, beside that run's copy. Kept with the run. The test process holds it and is never killed |

### `PAIR`: the system under test, not a G0 fixture

**`PAIR` is what R1 builds, not something R1 is tested on:** it is the launcher running the front. So it isn't one of G0's fixtures, and it isn't built at G0.

- **The governing plan** (`adm-56082aa297b0` section 2, which note `ent-beb03f957b87` says governs G0) lists its fixtures as F1 and F2, in section 3, and puts the launcher in P1.5, under "Parallel packages, after G0".
- **`PAIR` is in appendix A's fixture table** of `adm-6e15a0d880ba`, as what the tests start.
- **Building it before G0 would mean writing R1 before G0.** `crates/mentis-server/src/main.rs` today serves nothing and has no forwarding, so `test_an_owned_and_a_forwarded_read_match_py_alone` can't pass before P1.2 and P1.3 exist.

Every input is resolved here, and its build and first check are the named deliverable **P1.5-PAIR** below.

```powershell
cargo build --release --locked -p mentis-server
$env:MENTIS_UNDER_TEST = '["C:\\Work\\Mentis-wt\\rust-r1\\target\\release\\mentis-launch.exe", "{brain}", "--port", "{port}", "--workspace", "{ws}", "--mars", "{mars}", "--python", "C:\\Work\\Mentis-workspace\\r1-fixtures\\venv\\Scripts\\python.exe", "--code", "C:\\Work\\Mentis-wt\\rust-r1", "--dist", "C:\\Work\\Mentis-workspace\\r1-fixtures\\py-b8e324c\\apps\\fluid-web\\dist", "--run-dir", "{run}", "--attached"]'
```

`--front` is its default, `mentis-server.exe` beside the launcher. `--route-table` is its default, the table in the binary, and J5 and O2 pass their own. The five `{}` are `contracts/bench.md`'s, which the harness fills per boot:

| | In the pytest rows | In the bench, rows B and N |
|---|---|---|
| `{brain}` | The row's fixture, a fresh copy | Its copy, from `--brain` |
| `{port}` | 8852, with Python on the default private 18852 | 8831-8839, with Python on +10000 |
| `{ws}`, `{run}` | `<copy>.run\ws`, `<copy>.run` | As the bench makes them |
| `{mars}` | `workload-no-mars-here`. For J6, J7, J16, O and P: `C:\Work\MARS-venv\Scripts\mars.exe stdio`, with `MARS_BACKENDS_FILE=%LOCALAPPDATA%\mars\backends.json` | `workload-no-mars-here` |

**Provenance recorded with each run:** the commit, and `mentis-launch.exe`'s and `mentis-server.exe`'s SHA-256.

### The order

**P1.5-PAIR's 4 tests run on the integrated P1.2, P1.3 and P1.5, and before any row that uses `PAIR`.** P1.1 comes with them, since the front's open and P1.3's reads stand on its traits. The rows that use `PAIR` are A, C, D, E, F, H, I, J, K and P by name, B and N through `$env:MENTIS_UNDER_TEST`, and O through the launcher. G, L and M don't use it, and Q's other tests don't.

**No package waits on `PAIR` to start.** Until the integration, this is what stands for each:

| Package | Its own tests until then | A frozen row before `PAIR`? |
|---|---|---|
| **P1.1** | Row G whole: 40, by `cargo test -p mentis-record`, on generated values and `BRAIN-COPY` | **Yes** |
| **P1.2** | `cargo test -p mentis-server`, and the front started by hand with `contracts/launcher.md`'s step 4 command against `PY-ALONE` | **No.** Every row testing the front uses `PAIR`. It can start, and what it runs until then isn't frozen and accepts nothing |
| **P1.3** | `cargo test` of `mentis-rules` and `mentis-ops`, with the budgets `contracts/ops.md` asks for, on `BRAIN-SEED`, over P1.1's read traits as `crates/mentis-record/src/lib.rs` already states them | **No.** Row A's Pulse, Topics and Names use `PAIR`. The same applies |
| **P1.4** | Its tests of the nonzero exits (`contracts/bench.md`), `baseline` recorded with `PY-ALONE`'s command and commit, and `answers.py selftest baseline` | **Partly.** B's self-check and N's `baseline` stand; `compare baseline R1` waits for `PAIR` |
| **P1.5** | **Python's changes:** rows L and M, and **P1.5-J4-before,** which runs `b8e324c`'s `_over` against a stand-in that resets after sending, with no front. **The launcher:** its refusals, its order against a stand-in `--front`, and what `--upstream` gives that stand-in | **Partly.** L and M stand. The launcher's success against a real front waits for the integration, and it is what `test_fixture_pair.py` then checks |

A package's own tests still keep to rows G and K. Row G's 40 is the whole of `mentis-record`, and a test with `live` in its path changes row K's 9, so neither may gain one without a visible revision.

### What P1.5 owes

| Deliverable | What | Done when |
|---|---|---|
| **P1.5-PAIR** | `PAIR`'s build, and `tests/front/test_fixture_pair.py` with exactly 4 tests: `test_the_pair_starts_and_both_answer`, `test_an_owned_and_a_forwarded_read_match_py_alone`, `test_its_commits_and_binary_digests_are_recorded`, `test_killing_its_tree_leaves_no_process_and_no_lock` | 4 passed, on `BRAIN-SEED`, on the integrated P1.2, P1.3 and P1.5, before any row that uses `PAIR` is run. It adds them to row Q |
| **P1.5-J4-before** | J4's scenario run once **before** the worker's wording changes, on `b8e324c`'s `_over`, with the old message and path written to `docs/rust/evidence/j4-before.json` | The file is committed. **It decides nothing:** J4's assertions are R1's result. If it shows a path this document doesn't list, that is a visible revision |

`adm-56082aa297b0`'s F1 is `BRAIN-SEED`, and its F2 is `BRAIN-COPY`. Its proposed `tests/rust_front/` is `tests/front/` here, with appendix A's file names.

## Tests

| Row | Command | Fixture | Expected |
|---|---|---|---|
| A | `python -m pytest tests/front/test_front_contract.py -q` | `PAIR`, `PY-ALONE`, `BRAIN-SEED` | 120 passed |
| B | `python tools/bench/answers.py record --command $env:MENTIS_UNDER_TEST --code C:\Work\Mentis-wt\rust-r1 --brain C:\Work\Mentis-workspace\r1-fixtures\brain-copy-master --label R1 --twice`, then `python tools/bench/answers.py compare baseline R1`, then `python tools/bench/answers.py selftest baseline` | `BRAIN-COPY` | 47 reads, 0 unexplained differences. The self-check passes. **Each exits nonzero on any difference and on a self-check failure,** which P1.4 must make true, and any nonzero exit fails the row. Evidence that forwarding is transparent; it doesn't prove the whole API, and R1 doesn't claim that |
| C | `python -m pytest tests/front/test_read_your_writes.py -q` | `PAIR`, `BRAIN-SEED` | 2 passed: 300 commits each, for pulse and topics, 0 misses. Reported as a trial, not as a guarantee about every read |
| D | `python -m pytest tests/front/test_locks.py -q` | `PAIR`, `BRAIN-SEED` | 7 passed |
| E | `python -m pytest tests/front/test_kill.py -q` | `PAIR`, `LEDGER`, `BRAIN-COPY` | **60 passed:** 6 kill points, 10 runs each, parametrised so pytest counts them. About 95 minutes: section E |
| F | `python -m pytest tests/front/test_python_killed.py -q` | `PAIR`, `BRAIN-SEED` | 3 passed |
| G | `cargo test -p mentis-record --test chain_verifier --test codec_differential`, then `cargo test -p mentis-record` | Generated values, `BRAIN-COPY` | **13 passed** in the two named targets, then **40 passed, 0 ignored,** across the whole crate: section G |
| H | `python -m pytest tests/front/test_sqlite.py -q` | `PAIR`, `BRAIN-COPY` | 4 passed |
| I | `python -m pytest tests/front/test_wrote_nothing.py -q` | `PAIR`, `BRAIN-COPY` | 3 passed |
| J | `python -m pytest tests/front/test_restart.py -q`, then `python -m pytest tests/front/test_restart.py -q -m live` | `PAIR`, `LEDGER`, `BRAIN-SEED`, MARS, and for J6 and J7 `tools/r1/door_recorder.py` | 13 passed, then 3 live passed, each to the assertions in "J" and the allowed messages in `tests/front/restart_messages.json`. **This doesn't require the agent's turn to succeed.** The live cases need a logged-in runtime on Windows; if none is available, the row fails and R1 isn't accepted |
| K | `python -m pytest tests/front/test_live_snapshot.py -q`, and `cargo test -p mentis-server live` for the exact boundaries | `PAIR`, `BRAIN-SEED` | 20 passed, and **9 passed, 0 ignored.** At `6eb1f65` that filter selects exactly `live.rs`'s 9 `live::tests::*` in the library, and 0 of the 1 test in `src/main.rs`. The filter is a substring of the test's path, so a package adding a test with `live` in its path changes this count, and that fails until it is a visible revision. Name such a test otherwise |
| L | `$env:MENTIS_FLUID_DIST = 'C:\Work\Mentis-workspace\r1-fixtures\no-fluid-build'`, `python -m pytest tests/test_worker_boundary.py tests/test_moved_run_acts.py tests/test_topic_lookup.py -q --junitxml=C:\Work\Mentis-workspace\r1-fixtures\row-L.xml`, then `python tools/r1/compare_outcomes.py pytest docs/rust/evidence/row-L-b8e324c.json C:\Work\Mentis-workspace\r1-fixtures\row-L.xml` | Their own | **45 passed and 1 failed, 46 tests, and every test has its baseline outcome.** The comparison decides, not pytest's exit code. Any test missing, added or changed fails the row, in either direction. The one allowed failure: section L |
| M | `Set-Location apps/fluid-web`, `npm ci`, `npm test \| Out-File -Encoding utf8 C:\Work\Mentis-workspace\r1-fixtures\row-M.txt`, `Set-Location ../..`, `python tools/r1/compare_outcomes.py npm docs/rust/evidence/row-M-b8e324c.json C:\Work\Mentis-workspace\r1-fixtures\row-M.txt`, `git diff --exit-code b8e324c -- apps/fluid-web` | | **57 passed, 0 failed, 1 skipped, per file,** and no difference from `b8e324c`. Unconditional: section M |
| O | `python -m pytest tests/front/test_deploy_rollback.py -q -m live` | A disposable fixture server on `BRAIN-COPY`, MARS | 6 live passed |
| P | `python -m pytest tests/front/test_usable.py -q -m live` | `PAIR`, `BRAIN-COPY`, `BRAIN-SEED` for P5, MARS, Chromium | **5 live passed.** No browser means the row **fails,** and never skips: **a runtime that can't run headless Chromium can't accept this row** |
| N | `python tools/bench/run_workload.py --command $env:MENTIS_UNDER_TEST --code C:\Work\Mentis-wt\rust-r1 --brain C:\Work\Mentis-workspace\r1-fixtures\brain-copy-master --label R1 --levels n-sql,n-cpu,n-agents-write,agents-4`, then `python tools/bench/compare.py baseline R1`, then `python tools/bench/compare.py --noise baseline R1` | `BRAIN-COPY`, under the bench gate | **Required: isolation valid, bad statuses 0.** **Each exits nonzero on an invalid run, a bad status, or a refused comparison,** which P1.4 must make true, and any nonzero exit fails the row. The figures are measured and reported, as below |
| Q | `python -m pytest tests/front/test_fixture_tools.py tests/front/test_fixture_seed.py tests/front/test_fixture_brain_copy.py tests/front/test_fixture_py_alone.py tests/front/test_fixture_browser.py tests/front/test_fixture_evidence.py -q`, and from the integration in "The order" also `tests/front/test_fixture_pair.py` | `BRAIN-SEED`, the `BRAIN-COPY` master, `PY-ALONE`, Chromium, and from the integration `PAIR` | **69 passed at G0: 46, 3, 11, 4, 1, 4. 73 from the integration, with P1.5-PAIR's 4.** The fixtures themselves, and that the frozen baselines say what this document says |

`baseline` in row N is the one re-record on Python alone from P1.4, under the same `workload_sha` as R1. It adds timing for `history` and `kinds`. C0 v2 stays as context, since `compare.py` refuses a different workload.

Row N is one bench run, about 15 minutes, on a machine with nothing else building: `cargo`, `rustc`, `pytest` or a UI build anywhere invalidates it (`contracts/bench.md`). **Schedule it after the packages' builds, not during them,** and after row E's 95 minutes. Row N also shows the routes work under load. A run with bad statuses is a correctness failure, whatever its speed.

## Performance: measured and reported, never pass or fail

The baseline is C0 v2 (code `b8e324c`, workload `6a4c08a5c7083ce4`), one boot, three rounds. **These cells are small and noisy:** 17 to 34 samples at the agent levels, with p95 varying between rounds of the same code by up to 12.85× for the window and 17.88× for topic. So a figure is a description, not a verdict.

The report gives each of these, beside the C0 v2 and new `baseline` figures, in `compare.py`'s own table:

| Reported | C0 v2 today, pooled p95 ms (best-worst round), at `n-sql` / `n-cpu` / `n-agents-write` / `agents-4` | Reference mark, for context |
|---|---|---|
| Topic | 244 (111-436) / 2,653 (1,075-2,653) / 781 (313-1,950) / 471 (132-509) | 37.6 ms. On weak ground: it came from a no-engine v1 run with a stray process holding a core |
| Pulse | 25.9 (7-25.9) / 565 (227-565) / 151 (19.9-151) / 312 (217-312) | 50 ms |
| Forwarded route overhead, p50 and p95 | none today | p50 adds 5 ms |
| Whether the worst round beats the baseline's best, per level, palette and pulse | | "Better than noise", in section 3's sense |
| Python's cores, per level | 1.58 at `agents-4`, 1.54 at `n-agents-write`, 1.99 at `n-sql`, 1.0 at `n-cpu` | |
| Front and Python RSS, separately | Python 1,058 to 1,363 MB max | |
| Snapshot age beside pulse, polls timed out, and stale and unavailable transitions, per level | not applicable | The 250 ms poll timeout sits below C0's pulse p95 at `n-cpu`, so this shows whether a busy Python goes stale. Reported, as the rest; a stale state under load is correct, not a failure |

**After a deploy:** the front keeps per-route p50 and p95 in a log, and the release report compares them with the bench while real agents are active. It is what shows whether a gain reached DAY-TO-DAY. Magnets on the bench are stand-ins, there's no MARS on it, and live state is empty there, so this is the only evidence for those.

**What the report says plainly:** R1's user-visible benefit is expected to be narrow (the `#` palette, the check for new replies, Fluid's files). Opening a Conversation, the lists and search don't improve until R2 and later.

## A: contract cases, 120

Each compares status, the headers named, and body against `PY-ALONE`, except where a case is about the front alone.

**Revision, `opr-f2ea91ab6992`: which comparison uses the changed Python, and why.** The owner decided "Python answers its own failures" (`ent-d3d2c2c99ff6`): a handler that raises with nothing yet written answers a 500, so a silent close is meant to say Python went, and every silent close with a request in hand gets the front's 503. `PY-ALONE` is frozen at `b8e324c`, before that decision, and is **not** rebuilt or changed: on these paths it still closes with 0 bytes, so comparing it with `PAIR` would now fail for the decision's sake and not for a regression.

So Parser's 10 cases below, 5 `urlparse` raises and 5 past what Python can hold, compare `PAIR` with **this commit's Python alone** (`py_alone.running(code=common.REPO)`), and each must be that 500. These two groups used to pin the 4 GiB rule and the unparsable-target rule, both deleted with this decision. Every other case in row A still compares with `PY-ALONE`, and the row is still 120. The same two groups in `test_front_forms.py`, and `test_handler_failure.py`, which are no row, use the changed Python for the same reason.

**What this revision doesn't claim: a declared body Python hasn't read.** Closing with unread bytes sends RST on Windows and can lose the 500, and the front then gives its 503 for a Python that is still running. It is measured and not hidden: nothing in this row or the front has a threshold for it. The rates are in the Turn returning this revision, as an open point on `opr-f2ea91ab6992`.

| Group | Cases | n |
|---|---|---|
| Host | Allowed: IP literal, `localhost`, `x.localhost`, `x.ts.net`, a `MENTIS_ALLOWED_HOSTS` entry, bracketed IPv6 with port. Refused, **421:** `evil.example`, `a.ts.net.evil.example`, `localhost:1:2`, no Host | 10 |
| Client header | Missing on GET, missing on POST, `/api/server` exempt, a preflight grants nothing | 4 |
| Grant | Presented on another route: 403 with that door's own wording (`contracts/route-table.md`). Presented on `/api/worker`: forwarded, and a 403 from Python there relayed as Python sent it | 2 |
| Framing, refused or closed by the front exactly as Python does and never reinterpreted (`web/__init__.py:6276-6340,6497`) | `Transfer-Encoding: chunked`; `Transfer-Encoding : chunked`; duplicate Content-Length; conflicting Content-Length; non-digit Content-Length; a GET with a body; a second request pipelined after a refused one, which must not reach Python; HEAD | 8 |
| Parser, where the front and Python could read one request two ways. Each is in `tests/front/request_forms.py`, and what it is comes from Python's own parse there | Python reads the target as `/private/`, the front's own 404 and no snapshot, 19. Python reads it elsewhere however it looks, Python's answer, 22. `urlparse` raises, Python's own 500 from both, 5. HTTP/0.9's form under `/private/`, the front's body alone, 4, and elsewhere, Python's, 2. HTTP/0.9's form under `/private/` with a bad header, Python's refusal, 1. A request line Python refuses before any route, with `/private/` in it, 4. A Content-Length past what Python can hold, from 2^63-1 to past 2^64, Python's own 500 from both, 5 | 62 |
| Streaming | Export ZIP (`:6755-6775`): first bytes arrive before Python has finished writing, whole-body digest equal. Client disconnects mid-body: no error row, no stuck worker. An artifact's bytes with its security headers. A 200 MB body isn't buffered in memory: the front's RSS stays within 32 MB of its idle level | 4 |
| Forwarded answers (A3) | A JSON 404 from Python, with its status and body. A 500 from Python, by a test hook, passed through as Python sent it. Response headers, repeated ones included, in order | 3 |
| Peer | Non-loopback peer: picker refused with Python's wording. Loopback peer: allowed. Forged inbound `X-Mentis-Peer`: stripped. Header without the secret on the private port: ignored, socket peer used | 4 |
| Pulse | No `since`; `since` current; `since` older with `moved`; `since` past the record; malformed `since`; a gap over `CAP`; a run-only act isn't placed in a Conversation | 7 |
| Topics | `q` of load, mag, rev, sta and zzzz (as in `answers.py`), with a limit, with a bad limit | 7 |
| Names | Empty ids, a known Conversation, an unknown id, over the limit | 4 |
| Static | Index, hashed asset, missing file, `..` traversal, no build present | 5 |

The 200 MB row is correctness, not a performance mark: it shows a body is streamed rather than held. **No route streams events:** `text/event-stream` appears nowhere in `mentis/` at `b8e324c`, so the export ZIP and artifact bytes are what Streaming has to carry.

**Listed behaviour differences:** the pulse token's live half can lag, can read `unavailable`, and has `live: {state, age_ms}` added when not fresh (`contracts/live-snapshot.md`); and `/private/*` on the public port is the front's own (`contracts/launcher.md`). Nothing else may differ.

## D: locks, 7

Migrate refuses while the front has the Brain open. Restore refuses likewise. The front refuses while `.mentis.restoring` exists. The front refuses on an unsupported ledger. A second Python on the same Brain refuses, on `.mentis.serve.lock`. The front's shared `.mentis.lock` doesn't stop Python starting. A killed front leaves no lock behind.

## E: kill tests with the acknowledgement ledger, 60

Hard kills, by `TerminateProcess`, under the writing load. **A6's requirement stands: at least 10 runs per kill point.** K1 to K6 each run 10 times, parametrised over point and run so pytest counts every one: **6 × 10 = 60 passed.**

Each kill is placed at its window by a test hook or a test-held request, not by timing, so each of the 10 runs lands where it matters. A point that can only be hit by timing says so in its test.

| A6's point | K |
|---|---|
| Front during a read | K6 |
| Front during a forwarded write | K1 and K2, split at the moment that decides what the agent may be told |
| Python during a write | K3 and K4, split at commit |
| Both | K5 |

**Run time, about 95 minutes.** Per run, about 95 s: a fresh checked `BRAIN-COPY` 61.5 s, measured. Python's start on it 2.7 s, measured, and the front's. The load and kill about 10 s, and the restart, both estimated. Both verifiers and the ledger about 15 s, from Python's verifier and digests at 10.5 s measured, plus Rust's, estimated. It is a correctness row, so it has no time limit: the figure is for scheduling.

| Point | Killed | When |
|---|---|---|
| K1 | Front | During a forwarded write's request body |
| K2 | Front | Python has committed; the response is on its way back |
| K3 | Python | Inside a write, before commit |
| K4 | Python | Straight after acknowledging a write |
| K5 | Both | During writes |
| K6 | Front | With a forwarded read in hand, during writes: Python suspended, the read sent, and its caller still waiting when the front is killed |

**What K6 proves, and what it doesn't.** It places a front killed with a read in hand, on a read the caller is still waiting for, so a read that had already finished can't pass for it. That read is forwarded, so it is Python doing the reading. **It doesn't place a kill inside a read scope of the front's own:** nothing can hold one open from outside, R1 adds no hook to the shipped binary, and on row E's writing load nothing would be stuck in one. Row H2 is where a stuck scope is held, in a test build, and row D's "a killed front leaves no lock behind" is what a kill there could leave. So A6's "front during a read" is K6 for a forwarded read, and those two for the front's own.

After each run, and after Python restarts:

- **Every `LEDGER` row is present,** with the same `id`, `seq` and `hash`. Chain verification alone couldn't detect a missing row.
- **Any write not in the ledger is wholly present or wholly absent:** no partial command.
- **The chain verifies,** by both Python and Rust.
- **The write answered during the kill got the right words,** whole, by `decide` in `tests/front/restart_messages.py`: K1 `B-sending` or `B-sent`. K2 `B-sent` or `B-reply`. K3 and K4 `Python-reached`. K5 any of `A`, `B-sending`, `B-sent`, `B-reply`, `Python-reached`. Never "nobody answered" for a write that may have committed. K6's read fails with `B-sent` or `B-reply`, and `A` would be a read that never got in.
- **No orphan process** and no stale lock. `-wal` and `-shm` were recovered by SQLite alone.

## F: Python killed, 3

Owned routes still answer. Others answer 503 with exactly `front_503_error.Python-unreached` from `tests/front/restart_messages.json`. No orphan process.

## G: the chain codec, normative

From `spine/store.py:524-526,567-592,593-611`. Rust must produce the same bytes.

```
row_hash  = lowercase hex SHA-256 of UTF-8( prev + RS + canonical )
prev      = previous row's hash in this table by seq, or "" for the first row
RS        = U+001E
canonical = table RS field RS field ...    in the column order of CHAINED[table]
field     = "-"                            when the value is NULL
          | <byte length> ":" <text>       otherwise, where text = Python str(value)
```

| Case | Requirement |
|---|---|
| NULL against empty string | `-` against `0:` |
| A value containing RS, `:` or `-` | Can't shift a field boundary; the length decides |
| Unicode: multi-byte, astral, and a lone surrogate | Length in UTF-8 bytes. A lone surrogate fails in Python's encoding too, so Rust refuses, and neither appends |
| Integers: 0, negative, beyond 64 bits as text | Decimal, no `+`, as `str()` |
| Booleans | As the value stored. `True` written by Python becomes the text `True` before the row exists; the verifier reads what `CHAINED` columns hold, and differential tests cover both forms if any are present in the copy |
| Floats: exponent form (`1e+16`, `1e-05`), signed zero, integer-valued (`1.0`) | Python `repr` exactly, by differential test |
| Non-finite | Refused by Rust. Any already in the copy is reported, not silently accepted |
| Altered copies, 4 | A changed chained field, a removed row (A7's `seq` gap), a reordering, and a changed stored hash (A7's, added to appendix A's three): each is reported at the same `seq` as Python's verifier |

**The named targets, 13.** `codec_differential`, 8: one test for each of the 7 rows above the altered copies, and the 10,000 generated rows at a fixed seed. `chain_verifier`, 5: agreement across the whole copy, and the four altered copies.

**The whole crate, 40, 0 ignored, in `cargo test -p mentis-record`,** with 0 doctests:

| Where | n | Tests |
|---|---|---|
| `src/lib.rs`, at `6eb1f65` | 3 | `position_is_the_durable_half_of_a_pulse_token`, `a_position_is_exactly_three_unsigned_fields`, `a_value_is_text_only_when_it_is_text_and_utf8` |
| `tests/sqlite_links.rs`, at `6eb1f65` | 4 | `a_connection_opened_as_the_contract_says_refuses_to_write`, `a_list_of_ids_is_one_parameter_through_json_each`, `the_progress_handler_can_end_a_running_statement`, `the_bundled_sqlite_says_what_it_is` |
| The two named targets | 13 | Above |
| **P1.1:** `tests/open_refusals.rs` | 7 | `refuses_a_missing_brain`, `refuses_while_restoring`, `refuses_while_held_exclusive`, `refuses_a_ledger_this_build_does_not_name`, `takes_the_first_refusal_in_order`, `holds_the_lock_shared_until_dropped`, `never_touches_the_serve_lock` |
| **P1.1:** `tests/ledger_names.rs` | 1 | `names_every_python_migration`, generated from Python's `migrations` list |
| **P1.1:** `tests/read_scope.rs` | 11 | `position_is_fixed_with_the_snapshot`, `position_costs_no_statement_after_opening`, `a_running_statement_ends_at_the_limit`, `an_idle_scope_is_ended_by_the_reaper`, `a_scope_ends_within_2500_ms_of_its_snapshot`, `busy_at_the_cap_answers_at_once`, `one_class_at_its_cap_does_not_stop_another`, `statements_count_the_position`, `a_write_statement_is_refused`, `a_list_of_ids_reads_through_json_each`, `drop_commits_and_returns_the_connection` |
| **P1.1:** `tests/source_check.rs` | 1 | `corpus_db_is_opened_only_through_sqlite`, the check `contracts/record.md` asks for |

3 + 4 + 13 + 7 + 1 + 11 + 1 = 40.

Rust and Python must agree across the whole of `BRAIN-COPY`: the same row counts, heads and result per table. I read this codec against `store.py` at `b8e324c` and the formula and field encoding match; the table's differential cases are P1.1's to prove. **A differential that disagrees with this section fails:** correcting the section is a visible revision, with the reason.

## H: SQLite, 4

**The read scope is 2 s, and this is its test.** A9 proposed 5 s; it doesn't stand (note `ent-beb03f957b87`).

Recorded in the report: `sqlite_version()` and `PRAGMA compile_options` for Python's library (3.49.1 here, M) and the front's bundled one (3.54.1, from `rusqlite` 0.41.1), and which WAL fixes in SQLite's release notes separate them. The front opens with `SQLITE_OPEN_READ_ONLY`, `PRAGMA query_only=ON` and `busy_timeout=5000` to match `spine/store.py:307-314`, never `immutable`, and never touches `corpus.db*` except through SQLite (a source check).

1. **Two processes, one WAL:** the front reads committed rows during sustained Python writes, on the local disk.
2. **A stuck reader:** a read past the 2 s scope is ended within 2.5 s of its snapshot, both with a statement running and with the scope idle.
3. **The WAL recovers:** after that reader ends, a Python checkpoint completes and `-wal` shrinks or restarts. The largest size seen is reported and becomes the bound.
4. **A write through the front's connection is refused** by SQLite.

## I: Rust wrote nothing, 3

- **A front-only session** changes neither row counts per table, `advance()`, nor the hashes of the sibling Brain files, and `corpus.db` isn't written by the front (its handle is read-only).
- **A Python restart** adds only `retire_unconsumable`'s acts (`web/__init__.py:7143-7152`), each listed.
- **A source check:** `corpus.db*` is opened read-only, and only through SQLite, in `crates/`. A8 asks for this as a test, so it is counted here. Row H4 is the same fact at run time.

Not "Brain byte-identical", which Python's own startup can make false.

## Restart behaviour

**`docs/rust-front-restart.md` is the statement of this,** cases A to F. Processes survive; a run may be affected. "Runs unaffected" is withdrawn (Turn #1016, item 4). Nothing is retried automatically, and a planned restart can still change how a turn goes: the gap remains.

**A10 passes when** each case behaves as that page says and every message the agent sees is on the allowed list for its case, `tests/front/restart_messages.json`: any other message fails. A `NotPermitted` message is allowed only on the evidence of its own call, in "J". It must also show no acknowledged write lost, and no duplicate for keyed writes. The gap is measured and reported. **A10 does not require the agent's turn to succeed.** The plan's "once corrected by what the test finds" survives only as this: the test fails, and the page and assertion are then revised visibly with a reason.

## J: restart, 13 and 3 live

Numbers J5 to J7 keep their places from appendix A, because other documents cite them. `decide` is `tests/front/restart_messages.py`, reading the list, and a case passes only for the entries named. Every expected result here is final.

**A `NotPermitted` message passes J6 or J7 only if Mentis really refused that call.** Its words can't show that, because it carries whatever the door said, so entry `Refused` has no pattern and `decide` allows it only on two pieces of evidence from the same call:

- **Python answered 403 with those words.** `_over` turns a 403 from `/api/worker` into `NotPermitted` (`worker.py:6702-6707`). `tools/r1/door_recorder.py` stands between the front and Python, owned by the harness, and holds each such answer in the test process's memory before relaying it. `told_for` makes the message from a line's body as `_over` does, and it must equal the message whole. Each line vouches for one message. `tests/front/test_fixture_tools.py` holds `told_for` to the real `_over`, and `test_fixture_py_alone.py` holds the message and its line to one real call through the real door.
- **That call wrote nothing.** No row in `entry`, `operational` or `delivery` of the run's copy is stamped between the line's `received_at` and `answered_at`, with 50 ms added at each end. The recorder takes both times itself, on the clock those rows are stamped with: before it sends anything to Python, and once Python's whole answer is read. A refusal doesn't undo a commit: a call can write and then be answered 403.

**None of this evidence comes from the front.** It is what's being judged, and it writes nothing here, so a front that invents a `NotPermitted`, or turns Python's answer into one, has no line and fails, whatever it logs. A front that goes round the recorder leaves no line either. For J6 and J7 the harness starts the recorder first and adds `--upstream <its url>` to `$env:MENTIS_UNDER_TEST`, and to the `--only front` that restarts the front (`contracts/launcher.md`). The recorder lives in the test process, so it outlives the front's restart and kill, and Python stays up through both. No other row uses it.

With no evidence, it fails. So `NotPermitted: Mentis did the write but falsely says it did not` fails, a genuine refusal passes, and a refusal whose call wrote fails. **Two known limits, both failing rather than passing:** a row from anything else in that window counts as the call's, because the record can't attribute it. And `return_artifact`'s four refusals (`_read_for_return`, `worker.py:6513`) are raised on the worker's own side and never reach the door, so they have no line. J6's and J7's prompts make their calls one at a time and don't use `return_artifact`. If either limit fails a run, that is a failed row and a visible revision.

| # | Case | Must show |
|---|---|---|
| J1 | E | A planned stop: new connections are refused at once, a slow forwarded read and a forwarded write both finish, the front exits, and Python's pid is unchanged. A call past 35 s is cut at 35 s. The gap is reported |
| J2 | A | A call in the gap: `decide` gives `A` for what the agent is told, and Python sees no such call |
| J3 | C | Started in the gap: a hand-started bridge exits **1,** with `bridge_exit.C`'s stderr and nothing on stdout. A `boot_command` server stays up, lists exactly the `permits` it was started with, and its first call is J2's message |
| J4 | B | A reset after sending, with Python going on to commit: `decide` gives `B-sent`, R1's frozen wording, and the write is in the record exactly once. The run before the wording changes is **P1.5-J4-before,** and isn't this check |
| J5 | | An owned route rolled back in the route table takes effect with no restart, within 2 s |
| J6 | E, **live** | A real MARS run through a planned front restart. **Passes on:** every failed Mentis tool call in the window having a message `decide` allows, given that run's `Refusals`, and execution, grant and feed the same afterwards, with no process restarted. **Fails on** any other message. The gap, each failed call and whether the turn survived are reported, and don't decide it |
| J7 | B, **live** | A real run through a front kill. **Passes on the same two things as J6.** Whether the turn survived is reported, not assumed |
| J8 | B | The front killed while a reply's body is arriving: `decide` gives `B-reply`. Never `IncompleteRead` |
| J9 | B | Python killed with a call forwarded: the front's 503 body is `front_503_error.Python-reached`, whole, and `decide` gives `Python-reached` |
| J10 | D | Each keyed write repeated after a reset, under the same key. `anchor`, `react` and `deep_dive` as a session's tools, and `POST /fluid/api/posts`. `answer` and `timer` as a dispatched run's tools, each `POST /api/worker` under the grant dispatch started that run with. A session's scope can't make those two, and they need a request the run carries. So this row's `{mars}` is `tests/fakes/mars_stdio_stand_in.py`, which answers `mentis.execution.mars`'s ACP in `mars stdio`'s place, lists one backend and holds the turn. It runs nothing and isn't MARS: the composer's post to `@r1-agent`, dispatch, the grant and the MCP server's command are all Mentis's own, and the grant is read from that command. So this isn't a live case. One occurrence each, `replayed: true`, and the answer and the mark are the run's Participant's, the mark with the run's execution and request |
| J11 | D | **A source check:** the agent list in `docs/rust-front-restart.md` equals `ALL_TOOLS`, `READ_ONLY` and each schema's `op` |
| J12 | D | Each sent twice with the same arguments, through the front on `BRAIN-SEED`. **`open_conversation`:** 200, 200, different ids, 2 Conversations of that name. **`record_discovered_work`:** 200, 200, different expectations, 2 Turns with those words, 2 `work-discovered` acts. **`take_up`:** 200 at generation 1, then 403 with exactly `{"error": "'<expectation>' is already carried; taking it up would take it from whoever has it", "kind": "PermissionError"}`, and the carrier stays the session. Known, from Python alone: `docs/rust/evidence/j12-probe.json` |
| J13 | F | A reader polling through the gap gets an answer on its first poll after, and rereads once |
| J14 | F | A post retried across the gap under its composer's `op`: one post |
| J15 | | Through a planned restart and a kill, under writes: every `LEDGER` row is present, and both chain verifiers pass |
| J16 | C, **live** | A real hand-started session (`claude -p ... --strict-mcp-config --mcp-config <the bridge> --output-format stream-json --verbose --tools Read`) whose bridge starts in the gap. **Passes on:** the bridge alone exits **1,** with `bridge_exit.C`'s stderr; and the session's init event says `mentis` has status `failed`, and its tool list holds `Read` and no name starting `mcp__mentis__`. What the agent then did is reported, and doesn't decide it. Measured once: `docs/rust/evidence/j16-probe.json` |

## K: live snapshot, 20

Governed by `contracts/live-snapshot.md`, and A11 maps here. "Suspended" is the whole process, by `NtSuspendProcess`; "stalled" is a test hook on `/private/live` alone, so Python can still write. The exact boundaries are in `live.rs`'s tests, and these show the system keeps them.

| # | Python | Must show |
|---|---|---|
| K1 | Running | The envelope has its fields, with an integer `generation` and a separate `boot_id`. `generation` rises on a live change and on nothing else. The wrong secret gets 403 |
| K2 | Stalled | **The durable half still moves and answers, without waiting on Python.** How fast is reported. The hash is kept |
| K3 | Stalled, released | The live half catches up within one poll |
| K4 | Suspended | **The durable half answers** throughout, and equals the database's position |
| K5 | Suspended | Fresh to stale at 2 s: no `live` before, `live.state` stale after, hash unchanged |
| K6 | Suspended | Stale to unavailable at 10 s: the hash becomes `unavailable` |
| K7 | Suspended, resumed before 10 s | Back to fresh, and no hash change with no live change |
| K8 | Suspended, resumed after 10 s | Back to fresh, and the hash changes once |
| K9 | Killed while fresh | Unavailable from the refused poll, not after 10 s |
| K10 | Killed while stale | The same |
| K11 | Restarted between polls | The new `boot_id` discards: unavailable, then the new hash. **Two transitions, nothing older served** |
| K12 | Restarted while unavailable | One hash change only |
| K13 | Answers an unknown `schema`, by a stub | Unavailable, what was held is gone, and fresh again once a known schema answers |
| K14 | Answers a lower `generation`, by a stub | Discarded. Unavailable, then fresh |
| K15 | Through a full cycle | **One reread per transition:** a reader written as `activity.ts` is counts 2 for fresh, stale, unavailable, fresh, and 0 for fresh, stale, fresh |
| K16 | Through a full cycle | **Stale is never served as fresh:** sampled at 20 Hz, no answer without `live` has an age past 2 s by the test's own record of the last answered poll |
| K17 | No pulse over 5 s | The private route receives no polls |
| K18 | Running, resumed after idle of at least 15 s | **Resume isn't unavailable:** the first pulse is stale with the last hash, then fresh, and no answer says `unavailable` |
| K19 | Suspended during idle | After resume, stale for 10 s from the resume, then unavailable |
| K20 | Killed or restarted during idle | The first pulse is stale. The first poll decides: refused is unavailable, a new boot discards |

K2 was "answers within the mark" in r3. **What it proves stays mandatory:** a stalled Python doesn't hold up the durable half, so a pulse still answers rather than waiting on Python.

## O: deployment and rollback, 6 live

On a disposable fixture server, never DAY-TO-DAY. A13 maps here. `tests/front/test_deploy_rollback.py`.

1. **The launcher** starts Python on the private port and the front on the public one, on `BRAIN-COPY`, and exits 0.
2. **A route rolled back** by the table takes effect with no restart, and Python's and the front's pids are unchanged.
3. **`deploy-front.ps1` with a run active** lists the run and asks. Answered no, nothing changes.
4. **`deploy-front.ps1` with none active,** or answered yes: the front is replaced, Python's pid is unchanged, and the new binary answers.
5. **`rollback-to-python.ps1`:** Python on the public port again, no front, and the Brain changed only by Python's own startup acts, each listed.
6. **Restart:** the launcher again on the same Brain. Both answer, and both chain verifiers pass.

## P: usable, 5 live

Through the front, on a test server. A14 maps here. `tests/front/test_usable.py`.

1. **Fluid loads, at HTTP level:** the index, every asset it names, and the reads Fluid makes on opening all answer as Python's do.
2. **The palette answers:** `/fluid/api/topics` for a `#` query, from the front.
3. **A new post appears through pulse:** posted through the front, the durable half moves, `moved` names its Conversation, and the post reads back.
4. **A real agent run on MARS completes,** with its Mentis calls going through the front, shown by the front's log. Unlike J6, nothing is restarted, so this one does require the turn to succeed.
5. **Fluid opens in headless Chromium through the front,** on a fresh `BRAIN-SEED`, by `tools/r1/browser_check.py`. In one load, all of: **no uncaught page error. No same-origin request fails,** at the network, with a status of 400 or more, or as an asset answered with the index page, with none listed as allowed (Python answers a missing file with `index.html` and 200, so status alone can't see one). **Fluid's controls are visible by name:** the buttons New conversation, Latest activity, Search and Notifications, and the words Daily Briefing and Needs you. **A known item renders:** in the conversation menu, `R1 known conversation` with `3 posts`, and once opened, `R1 known post: the harbour light is lit at dusk.`

**A runtime without a browser can't accept this row.** Chromium that can't start exits 2, and P5 fails.

The check is proved on Python alone, in `docs/rust/evidence/browser-proof.json`: it passes on `b8e324c`'s real build, and it fails with the index's stylesheet missing, with its script missing, with an API read aborted, with a page error, and with a post the fixture doesn't hold.

## A1 to A15

Every check of `adm-56082aa297b0`, section 3.1. **These counts are frozen.**

| Check | What | Row | Test file | Fixed count |
|---|---|---|---|---|
| A1 | Owned routes match Python | A: Host 10, Client header 4, Grant 2, Pulse 7, Topics 7, Names 4, Static 5 | `tests/front/test_front_contract.py` | 39 of A's 120 |
| A2 | Forwarding transparent | B | `tools/bench/answers.py` | 47 reads, 0 unexplained |
| A3 | Forwarding framing | A: Framing 8, Parser 62, Streaming 4, Forwarded answers 3, Peer 4 | `tests/front/test_front_contract.py` | 81 of A's 120 |
| A4 | Read-your-writes | C | `tests/front/test_read_your_writes.py` | 2, of 300 commits each |
| A5 | Locks | D | `tests/front/test_locks.py` | 7 |
| A6 | Kill points and ledger | E | `tests/front/test_kill.py` | 60: 6 points, 10 runs each. A6's four points map to K1 to K6 in section E |
| A7 | Verifiers and codec | G | `crates/mentis-record/tests/chain_verifier.rs`, `codec_differential.rs` | 13, within the crate's 40 |
| A8 | Rust wrote nothing | I, and H4 at run time | `tests/front/test_wrote_nothing.py` | 3 |
| A9 | SQLite and bounded read | H. **2 s, not A9's 5 s** | `tests/front/test_sqlite.py` | 4 |
| A10 | Restart effect | J | `tests/front/test_restart.py`, `tests/front/restart_messages.json` | 13, and 3 live |
| A11 | Live-state freshness | K | `tests/front/test_live_snapshot.py`, `crates/mentis-server/src/live.rs` | 20, and 9 |
| A12 | Python killed | F | `tests/front/test_python_killed.py` | 3 |
| A13 | Deploy and rollback | **O, new** | `tests/front/test_deploy_rollback.py` | 6 live |
| A14 | Usable, **in a real browser** | **P, new**, and M | `tests/front/test_usable.py`, `tools/r1/browser_check.py` | 5 live: P1 HTTP level, P2 palette, P3 pulse, P4 MARS run, P5 headless Chromium. M: 57 passed, 1 skipped, and no Fluid difference |
| A15 | Reported, not a gate | N, and "Performance" | `tools/bench/run_workload.py`, `compare.py` | 4 levels, 0 bad statuses required. Figures reported |

## L: the baseline, per test

`docs/rust/evidence/row-L-b8e324c.json`, from a clean detached checkout of `b8e324c` that isn't the serving one: **46 tests, 45 passed, 1 failed.** Three runs agreed per test.

**The one allowed failure is `tests/test_topic_lookup.py::test_find_numbers_hits_as_turn_number_does`** (`opr-f50abde73219`, reported in Turn `ent-0fb6ebb24f1f`), and it fails **because no Fluid build is present:** `find`'s `block` hit needs Fluid's `render-check.js`. The same commit with a build gives 46 passed, which the baseline also records. So the row's command fixes `MENTIS_FLUID_DIST` to a directory that doesn't exist, `C:\Work\Mentis-workspace\r1-fixtures\no-fluid-build`, and a clone with a build can't change the outcome. It is counted as that failure, not as R1's.

## M: the baseline, per file

`docs/rust/evidence/row-M-b8e324c.json`, from the same checkout, Node 24.13.1, after `npm ci`: **58 files, 57 passed, 0 failed, 1 skipped.** The skip is the runner's own, `fluid_objects_unit.mjs (no FLUID_OBJECTS_CASES)`, and this row runs it as the runner does. There are no baseline failures.

**The row always runs, with `git diff --exit-code b8e324c -- apps/fluid-web`.** R1 changes no Fluid source, so nobody decides whether the row applies: a Fluid change shows up as a failed row, which needs a visible revision with its reason.

## Rollback, to show before release

Rollback is a correctness requirement, not a nicety:

| Level | How | Effect on runs | Brain |
|---|---|---|---|
| One route | The table back to `python`, until its handler is retired. No restart | None | Rust wrote nothing |
| The front | The previous binary, through `deploy-front.ps1` | Processes survive; a run may be affected (`docs/rust-front-restart.md`) | Rust wrote nothing |
| R1 | `rollback-to-python.ps1`: Python on 8760 again | Live runs end, as in any Python restart. Asked | Rust wrote nothing. Python's startup acts are its own |

## Who has what

P1.0 and these interfaces are reviewed with the first release review. P1.1, P1.2 and P1.5 have independent cross-runtime review. A correction is re-reviewed for what it changes. Release reports list open retirements, so two half-owners stay visible. The owner's rule on Python changes is in `AGENTS.md`.
