# Contract: the bench command

For P1.4, moving `run_workload.py`, `benchgate.py`, `compare.py`, `tools/answers.py` and what they import from `C:\Work\Mentis-workspace\day-to-day\mirps-shared-ops\measure` to `tools/bench/`. **No new harness.** The one change is to run a command rather than a Python tree.

## `--command`

A JSON array of strings, one per argument, with placeholders. `run_workload.py --command`, `answers.py record --command` and `$env:MENTIS_UNDER_TEST` all take this one format, so tests and the bench start the same thing.

| Placeholder | Is |
|---|---|
| `{brain}` | This boot's fresh copy of the Brain |
| `{port}` | The public port, in 8831-8839 |
| `{ws}` | This boot's workspace |
| `{mars}` | The command that cannot exist, `workload-no-mars-here` |
| `{run}` | This boot's directory. Everything temporary goes under it |

**Python alone, the baseline:**

```json
["C:\\Work\\Mentis-workspace\\r1-fixtures\\venv\\Scripts\\python.exe", "-m", "mentis.web", "{brain}", "--port", "{port}", "--workspace", "{ws}", "--mars", "{mars}"]
```

**The pair:**

```json
["C:\\Work\\Mentis-wt\\rust-r1\\target\\release\\mentis-launch.exe", "{brain}", "--port", "{port}", "--workspace", "{ws}", "--mars", "{mars}",
 "--python", "C:\\Work\\Mentis-workspace\\r1-fixtures\\venv\\Scripts\\python.exe", "--code", "C:\\Work\\Mentis-wt\\rust-r1", "--dist", "C:\\Work\\Mentis-workspace\\r1-fixtures\\py-b8e324c\\apps\\fluid-web\\dist",
 "--run-dir", "{run}", "--attached"]
```

## What the bench guarantees to the command

Today's start (`run_workload.py:78-110`), unchanged:

- **Fresh copies** of `corpus.db`, `mentis-corpus.json`, `presentation/` and `derived/`, per boot.
- **Environment:** `MENTIS*` removed, `PATH` stripped of anything named Mars or Mentis, `MENTIS_FLUID_DIST` set to the bundle, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONIOENCODING=utf-8`, plus any `--server-env`. `PYTHONPATH` is `--code`.
- **cwd** is `{run}`, and stdout and stderr go to `{run}/server.log`.

## What the command guarantees to the bench

| Requirement | Why |
|---|---|
| **Stays running in the foreground,** with everything it starts in its process tree | `Server.tree` sums CPU and RSS from the root, and `stop` kills that tree. And `benchgate` treats a process with the bench tree in its command line as invalidating **unless it descends from the holder**, so a detached front would void the run. Hence `--attached` |
| **Ready is `GET /api/pulse` answering 200 on `{port}`,** with `X-Mentis-Client: 1`, within 240 s | As today |
| **Goes quiet:** under 0.15 cores for 2 s within `--boot-quiet-s` | As today |
| **Object reads extract,** `GET /fluid/api/objects?post=<REF>` says `extracted: true` | The harness refuses otherwise. Through the front, that is forwarded to Python, which reads `MENTIS_FLUID_DIST` |
| **`/api/worker/session`** answers through `{port}` with a grant | As today: it's forwarded |
| **Its private port is outside 8831-8839** | The gate invalidates anything else listening there. `mentis-launch`'s default is +10000 |
| **Exits 0 or dies to a kill,** and leaves no process behind once its tree is killed | Row N's isolation record, and the next boot |

The harness reports RSS and CPU **by process name within the tree, as well as summed:** `python.exe` and `mentis-server.exe` apart. R1's "Python stayed busy" and R2's memory row need them apart.

## What each result records

As today (`workload_sha`, code commit, `isolation`), plus:

- `command`, the array as given.
- `binary`: for each executable in `command` not named `python`, its path and SHA-256.
- `brain`: the `corpus.db` digest of the master it ran on, by hashing the file. `compare.py` and `answers.py compare` refuse two results that differ, as they refuse a different `workload_sha`, since a difference between two snapshots proves nothing about the code. So a new `BRAIN-COPY` master means re-recording `baseline`.
- `--code` stays required. It names the Python tree whose commit is recorded and which the gate watches for change. The gate watches the binaries' digests too.

## The baseline

`--command` changes `workload_sha`, and `compare.py` refuses a mismatch. So P1.4 records **one new baseline on Python alone,** under the moved tools, **label `baseline`,** with `--code C:\Work\Mentis-workspace\r1-fixtures\py-b8e324c`, `PY-ALONE`'s commit. It adds timing for `history` and `kinds`, which C0 v2 lacks at the agent levels. C0 v2 stays as context and is not compared against. A label that already has a result is refused, because a result is evidence.

## Commands the acceptance uses

The real forms, since `R1-acceptance.md` rows B and N depend on them. `compare.py` takes `labels` and `--noise` as they stand today (`compare.py:194-195`). `run_workload.py --brain` is today's. **P1.4 adds `--brain` to `answers.py record`,** with the same meaning.

**Each of these exits nonzero on any difference, on an invalid run or bad status, and on a self-check failure.** P1.4 makes that true where it isn't, with a test. A row treats any nonzero exit as failed.

```
python tools/bench/run_workload.py --command $env:MENTIS_UNDER_TEST --code C:\Work\Mentis-wt\rust-r1 --brain C:\Work\Mentis-workspace\r1-fixtures\brain-copy-master --label R1 --levels n-sql,n-cpu,n-agents-write,agents-4
python tools/bench/compare.py baseline R1
python tools/bench/compare.py --noise baseline R1
python tools/bench/answers.py record --command $env:MENTIS_UNDER_TEST --code C:\Work\Mentis-wt\rust-r1 --brain C:\Work\Mentis-workspace\r1-fixtures\brain-copy-master --label R1 --twice
python tools/bench/answers.py compare baseline R1
python tools/bench/answers.py selftest baseline
```

Each release runs only its levels, bounded to about 15 minutes.

## The gate still applies

`benchgate`'s rules don't change. Nothing else runs during a timed run: `cargo`, `rustc`, `pytest` or a UI build anywhere on the machine invalidates it. So build the release binary **before** taking the lock. `BENCH_HOLDER` names who holds it. The Python is the fixtures' `venv`. The master's files are read-only, so the bench's own copies of them must be made writable, and it never opens the master through SQLite.

**P1.4 must also re-point** `HERE`, `BENCH`, `BUNDLE_DIR`, `RUNLOCK` and the results directory, which are all relative to the old tree. Results and the bundle stay out of Git, under `C:\Work\Mentis-workspace\day-to-day\`. `tools/bench/` holds code only.

**A statement trace for test builds** is P1.4's other half: `rusqlite`'s `trace` feature behind a test-only switch in `mentis-record`, counting per route. Today's trace wraps Python's `sqlite3` (`measure/workload/trace/`), which can't see Rust's SQL.
