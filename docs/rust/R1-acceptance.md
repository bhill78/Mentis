# R1 acceptance

Appendix A of `PLAN-r3.md`, carried over with the owner's correction (Turn #1016 `ent-b8ef5a9d035b`, Turn #1025 `ent-9a3dff0b382f`, item 1) applied.

## What decides R1

**R1 may succeed by establishing a correct, usable, Rust-owned server foundation.** A release may establish infrastructure or transfer ownership without improving latency.

| | |
|---|---|
| **Mandatory, pass or fail** | Correctness, Brain safety, authority, restart behaviour, and a valid bench run. Rows A to M, and row N's validity. **Any failure stops the release** |
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

**A count may change only with the reason stated in the release report.** Windows is the gate. On Windows, the expected result of each row is all passed, 0 failed, 0 errors and 0 skipped, except where a row says otherwise. These test files don't exist yet: P1.1 to P1.5 write them.

## Deployment

This document decides acceptance, not deployment. **R1's first deployment restarts Python and ends live runs, so it returns to the owner** (Turn #1025, item 4). Later accepted front-only releases that don't interrupt runs may deploy under standing authorisation, under the existing release and rollback process. Independent review of implemented changes stays required; no further whole-plan review is.

## Fixtures

| Name | What | Provenance recorded with it |
|---|---|---|
| `BRAIN-COPY` | A copy of DAY-TO-DAY's Brain, made with SQLite's backup API from a read-only connection, with `artifacts/`, `instances/`, `presentation/` and `mentis-corpus.json`. **Never the live Brain** | Source path, time, `advance()`, row counts per table, chain head, `verify_chain` result, code commit |
| `BRAIN-SEED` | A small Brain seeded by Python's own commands, rebuilt per test module | Seed script and commit |
| `PAIR` | The launcher `--attached`, starting Python on a private port and the front on a test port, on a fresh copy of either Brain. `MENTIS_UNDER_TEST` names it, in the format of `contracts/bench.md` | Both commits and binary digest |
| `PY-ALONE` | Python alone on a second copy, the other side of every differential case | Commit |
| `LEDGER` | A write client that appends each acknowledged write to a file and fsyncs before the next: id, table, `seq`, `hash` | Kept with the run |

Setup: from the work's clone, `$env:MENTIS_UNDER_TEST` is the launcher command and `$env:MENTIS_TEST_BRAIN_COPY` is `BRAIN-COPY`.

## Tests

| Row | Command | Fixture | Expected |
|---|---|---|---|
| A | `python -m pytest tests/front/test_front_contract.py -q` | `PAIR`, `PY-ALONE`, `BRAIN-SEED` | 55 passed |
| B | `python tools/bench/answers.py record --command $env:MENTIS_UNDER_TEST --code <clone> --label R1 --twice`, `answers.py compare baseline R1`, `answers.py selftest baseline` | `BRAIN-COPY` | 47 reads, 0 unexplained differences. The self-check passes. Evidence that forwarding is transparent; it doesn't prove the whole API, and R1 doesn't claim that |
| C | `python -m pytest tests/front/test_read_your_writes.py -q` | `PAIR`, `BRAIN-SEED` | 2 passed: 300 commits each, for pulse and topics, 0 misses. Reported as a trial, not as a guarantee about every read |
| D | `python -m pytest tests/front/test_locks.py -q` | `PAIR`, `BRAIN-SEED` | 7 passed |
| E | `python -m pytest tests/front/test_kill.py -q` | `PAIR`, `LEDGER`, `BRAIN-COPY` | 18 passed: 6 kill points, 3 times each |
| F | `python -m pytest tests/front/test_python_killed.py -q` | `PAIR`, `BRAIN-SEED` | 3 passed |
| G | `cargo test -p mentis-record` | Generated values, `BRAIN-COPY` | All passed, with the run's total stated. Includes 10,000 generated rows at a fixed seed, every case in the codec table, and the 3 altered copies |
| H | `python -m pytest tests/front/test_sqlite.py -q` | `PAIR`, `BRAIN-COPY` | 4 passed |
| I | `python -m pytest tests/front/test_wrote_nothing.py -q` | `PAIR`, `BRAIN-COPY` | 2 passed |
| J | `python -m pytest tests/front/test_restart.py -q`, then `-m live` | `PAIR`, `BRAIN-SEED`, MARS | 5 passed, then 2 live passed. The live cases need a logged-in runtime on Windows; if none is available, R1 isn't accepted |
| K | `python -m pytest tests/front/test_live_snapshot.py -q` | `PAIR`, `BRAIN-SEED` | 4 passed |
| L | `python -m pytest tests/test_worker_boundary.py tests/test_moved_run_acts.py tests/test_topic_lookup.py -q` | Their own | The baseline run's pass count first, on `b8e324c`. **`test_find_numbers_hits_as_turn_number_does` already fails there** (`opr-f50abde73219`), and is counted as that, not as R1's |
| M | `npm test`, for what changed in `apps/fluid-web` | | R1 changes no Fluid source. If that changes, the files run and the counts are stated |
| N | `python tools/bench/run_workload.py --command $env:MENTIS_UNDER_TEST --code <clone> --label R1 --levels n-sql,n-cpu,n-agents-write,agents-4`, then `python tools/bench/compare.py baseline R1`, and `python tools/bench/compare.py --noise baseline R1` | `BRAIN-COPY`, under the bench gate | **Required: isolation valid, bad statuses 0.** The figures are measured and reported, as below |

`baseline` in row N is the one re-record on Python alone from P1.4, under the same `workload_sha` as R1. It adds timing for `history` and `kinds`. C0 v2 stays as context, since `compare.py` refuses a different workload.

Row N is one bench run, about 15 minutes, on a machine with nothing else building: `cargo`, `rustc`, `pytest` or a UI build anywhere invalidates it (`contracts/bench.md`). **Schedule it after the packages' builds, not during them.** Row N also shows the routes work under load. A run with bad statuses is a correctness failure, whatever its speed.

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
| Snapshot age beside pulse | not applicable | |

**After a deploy:** the front keeps per-route p50 and p95 in a log, and the release report compares them with the bench while real agents are active. It is what shows whether a gain reached DAY-TO-DAY. Magnets on the bench are stand-ins, there's no MARS on it, and live state is empty there, so this is the only evidence for those.

**What the report says plainly:** R1's user-visible benefit is expected to be narrow (the `#` palette, the check for new replies, Fluid's files). Opening a Conversation, the lists and search don't improve until R2 and later.

## A: contract cases, 55

Each compares status, the headers named, and body against `PY-ALONE`, except where a case is about the front alone.

| Group | Cases | n |
|---|---|---|
| Host | Allowed: IP literal, `localhost`, `x.localhost`, `x.ts.net`, a `MENTIS_ALLOWED_HOSTS` entry, bracketed IPv6 with port. Refused, **421:** `evil.example`, `a.ts.net.evil.example`, `localhost:1:2`, no Host | 10 |
| Client header | Missing on GET, missing on POST, `/api/server` exempt, a preflight grants nothing | 4 |
| Grant | Presented on another route: 403 with that door's own wording (`contracts/route-table.md`). Presented on `/api/worker`: forwarded | 2 |
| Framing, refused or closed by the front exactly as Python does and never reinterpreted (`web/__init__.py:6276-6340,6497`) | `Transfer-Encoding: chunked`; `Transfer-Encoding : chunked`; duplicate Content-Length; conflicting Content-Length; non-digit Content-Length; a GET with a body; a second request pipelined after a refused one, which must not reach Python; HEAD | 8 |
| Streaming | Export ZIP (`:6755-6775`): first bytes arrive before Python has finished writing, whole-body digest equal. Client disconnects mid-body: no error row, no stuck worker. An artifact's bytes with its security headers. A 200 MB body isn't buffered in memory: the front's RSS stays within 32 MB of its idle level | 4 |
| Peer | Non-loopback peer: picker refused with Python's wording. Loopback peer: allowed. Forged inbound `X-Mentis-Peer`: stripped. Header without the secret on the private port: ignored, socket peer used | 4 |
| Pulse | No `since`; `since` current; `since` older with `moved`; `since` past the record; malformed `since`; a gap over `CAP`; a run-only act isn't placed in a Conversation | 7 |
| Topics | `q` of load, mag, rev, sta and zzzz (as in `answers.py`), with a limit, with a bad limit | 7 |
| Names | Empty ids, a known Conversation, an unknown id, over the limit | 4 |
| Static | Index, hashed asset, missing file, `..` traversal, no build present | 5 |

The 200 MB row is correctness, not a performance mark: it shows a body is streamed rather than held. **Listed behaviour differences:** the pulse token's live half can lag (`contracts/live-snapshot.md`), and `/private/*` on the public port is the front's own (`contracts/launcher.md`). Nothing else may differ.

## D: locks, 7

Migrate refuses while the front has the Brain open. Restore refuses likewise. The front refuses while `.mentis.restoring` exists. The front refuses on an unsupported ledger. A second Python on the same Brain refuses, on `.mentis.serve.lock`. The front's shared `.mentis.lock` doesn't stop Python starting. A killed front leaves no lock behind.

## E: kill tests with the acknowledgement ledger, 18

Hard kills, by `TerminateProcess`. Each kill point runs 3 times under the writing load.

| Point | Killed | When |
|---|---|---|
| K1 | Front | During a forwarded write's request body |
| K2 | Front | Python has committed; the response is on its way back |
| K3 | Python | Inside a write, before commit |
| K4 | Python | Straight after acknowledging a write |
| K5 | Both | During writes |
| K6 | Front | Holding a read scope open during writes |

After each run, and after Python restarts:

- **Every `LEDGER` row is present,** with the same `id`, `seq` and `hash`. Chain verification alone couldn't detect a missing row.
- **Any write not in the ledger is wholly present or wholly absent:** no partial command.
- **The chain verifies,** by both Python and Rust.
- **The write answered during the kill got the right words:** K1 and K2 as in "Restart behaviour" below, never "nobody answered" for a write that committed.
- **No orphan process** and no stale lock. `-wal` and `-shm` were recovered by SQLite alone.

## F: Python killed, 3

Owned routes still answer. Others answer 503 with the reason. No orphan process.

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
| Altered copies, 3 | A changed chained field, a removed row and a reordering: each is reported at the same `seq` as Python's verifier |

Rust and Python must agree across the whole of `BRAIN-COPY`: the same row counts, heads and result per table. P1.1 checks this codec against the code before relying on it, and any correction goes back into this section. I read it against `store.py` at `b8e324c` and the formula and field encoding match; the table's differential cases are P1.1's to prove.

## H: SQLite, 4

Recorded in the report: `sqlite_version()` and `PRAGMA compile_options` for Python's library (3.49.1 here, M) and the front's bundled one (3.54.1, from `rusqlite` 0.41.1), and which WAL fixes in SQLite's release notes separate them. The front opens with `SQLITE_OPEN_READ_ONLY`, `PRAGMA query_only=ON` and `busy_timeout=5000` to match `spine/store.py:307-314`, never `immutable`, and never touches `corpus.db*` except through SQLite (a source check).

1. **Two processes, one WAL:** the front reads committed rows during sustained Python writes, on the local disk.
2. **A stuck reader:** a read past the 2 s scope is ended within 2.5 s of its snapshot, both with a statement running and with the scope idle.
3. **The WAL recovers:** after that reader ends, a Python checkpoint completes and `-wal` shrinks or restarts. The largest size seen is reported and becomes the bound.
4. **A write through the front's connection is refused** by SQLite.

## I: Rust wrote nothing, 2

- **A front-only session** changes neither row counts per table nor `advance()`, and `corpus.db` isn't written by the front (its handle is read-only).
- **A Python restart** adds only `retire_unconsumable`'s acts (`web/__init__.py:7143-7152`), each listed.

Not "Brain byte-identical", which Python's own startup can make false.

## Restart behaviour

**A front restart preserves execution, not every call.** The run, its grant and its feed survive. A tool call in the gap doesn't automatically. "Runs unaffected" is withdrawn (Turn #1016, item 4).

| What the call meets | Today's answer (`worker.py:6687-6738`) | R1's answer |
|---|---|---|
| Connection refused: the front is down | `NoOwner`, "nothing else to try", which can end the turn | Retried for up to 10 s, for reads and writes alike, because nothing was delivered. After that the agent is told it never reached Mentis |
| Connection reset after sending: the front died mid-call | `NoOwner` too, which wrongly says nobody answered, though Python may have committed | "It may still have done it", the same words as a timeout |
| A planned restart | | The front stops accepting, finishes what it has forwarded (up to 30 s, the worker's own limit), then exits |

So a planned front restart should cost a run nothing, and a crash can still fail one call and change how that turn goes.

## J: restart, 5 and 2 live

1. A planned restart drains: a slow forwarded read and a forwarded write both finish.
2. A connection refused in the gap is retried and succeeds. The server sees the call once.
3. A gap longer than the 10 s retry: the agent is told it never reached Mentis, and nothing was recorded.
4. A reset after sending: the agent is told it may still have been done.
5. An owned route rolled back in the route table takes effect with no restart, within 2 s.
6. **Live:** a real MARS run through a planned front restart reaches its normal end with no failed call. The gap is reported.
7. **Live:** a real run through a front kill keeps its execution, grant and feed. Whether the turn survived is reported, not assumed.

## K: live snapshot, 4

1. The snapshot has its fields, and `generation` changes on a live change.
2. With Python stalled by a test hook, the durable half of pulse still moves and answers. How fast is reported. The live half keeps its last value.
3. After the stall, the live half catches up within one poll.
4. With no pulse asked for over 5 s, the private route receives no polls.

K2 was "answers within the mark" in r3. **What it proves stays mandatory:** a stalled Python doesn't hold up the durable half, so a pulse still answers rather than waiting on Python.

## Rollback, to show before release

Rollback is a correctness requirement, not a nicety:

| Level | How | Runs lost | Brain |
|---|---|---|---|
| One route | The table back to `python`, until its handler is retired | None | Rust wrote nothing |
| R1 | `rollback-to-python.ps1`: Python on 8760 again | Live runs end, as in any deploy | Rust wrote nothing. Python's startup acts are its own |

## Who has what

P1.0 and these interfaces are reviewed with the first release review. P1.1, P1.2 and P1.5 have independent cross-runtime review. A correction is re-reviewed for what it changes. Release reports list open retirements, so two half-owners stay visible. The owner's rule on Python changes is in `AGENTS.md`.
