# R1 acceptance

Appendix A of `PLAN-r3.md` (`adm-6e15a0d880ba`), carried over with the owner's correction (Turn #1016 `ent-b8ef5a9d035b`, Turn #1025 `ent-9a3dff0b382f`, item 1) applied. Where note `ent-beb03f957b87` says so, `adm-56082aa297b0` governs instead: its section 3.2 restart table, section 3.3 snapshot, section 5 retirement lists and section 6. Every one of its checks A1 to A15 maps to a row here, in "A1 to A15" below.

## What decides R1

**R1 may succeed by establishing a correct, usable, Rust-owned server foundation.** A release may establish infrastructure or transfer ownership without improving latency.

| | |
|---|---|
| **Mandatory, pass or fail** | Correctness, Brain safety, authority, restart behaviour, and a valid bench run. Rows A to M, O and P, and row N's validity. **Any failure stops the release** |
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

This document decides acceptance, not deployment.

| Release | Who decides | Why |
|---|---|---|
| **An accepted front-only release, with no run active** | Standing yes (Turn `ent-a60e9f7e22b4`). **The owner is told what changed** | Replaces asking per release. `docs/cutover/deploy-front.ps1` lists active runs first |
| **An accepted front-only release, with a run active** | Asked | A front restart can change a run's outcome (`docs/rust-front-restart.md`), and the standing yes covers only times with no active run |
| **Anything that restarts Python, interrupts runs, changes Brain writes or needs a semantic migration** | Asked (Turn `ent-9a3dff0b382f`, item 4) | So **R1's first deploy and R3's are asked:** each restarts Python and ends live runs |

Follows the existing release and rollback process. Independent review of implemented changes stays required; no further whole-plan review is.

## Fixtures

| Name | What | Provenance recorded with it |
|---|---|---|
| `BRAIN-COPY` | A copy of DAY-TO-DAY's Brain, made with SQLite's backup API from a read-only connection, with `artifacts/`, `instances/`, `presentation/` and `mentis-corpus.json`. **Never the live Brain** | Source path, time, `advance()`, row counts per table, chain head, `verify_chain` result, code commit |
| `BRAIN-SEED` | A small Brain seeded by Python's own commands, rebuilt per test module | Seed script and commit |
| `PAIR` | The launcher `--attached`, starting Python on a private port and the front on a test port, on a fresh copy of either Brain. `MENTIS_UNDER_TEST` names it, in the format of `contracts/bench.md` | Both commits and binary digest |
| `PY-ALONE` | Python alone on a second copy, the other side of every differential case | Commit |
| `LEDGER` | A write client that appends each acknowledged write to a file and fsyncs before the next: id, table, `seq`, `hash` | Kept with the run |

`adm-56082aa297b0`'s F1 is `BRAIN-SEED`, and its F2 is `BRAIN-COPY`. Its proposed `tests/rust_front/` is `tests/front/` here, with appendix A's file names. Test files are proposals until each package writes them.

Setup: from the work's clone, `$env:MENTIS_UNDER_TEST` is the launcher command and `$env:MENTIS_TEST_BRAIN_COPY` is `BRAIN-COPY`.

## Tests

| Row | Command | Fixture | Expected |
|---|---|---|---|
| A | `python -m pytest tests/front/test_front_contract.py -q` | `PAIR`, `PY-ALONE`, `BRAIN-SEED` | 58 passed |
| B | `python tools/bench/answers.py record --command $env:MENTIS_UNDER_TEST --code <clone> --label R1 --twice`, `answers.py compare baseline R1`, `answers.py selftest baseline` | `BRAIN-COPY` | 47 reads, 0 unexplained differences. The self-check passes. Evidence that forwarding is transparent; it doesn't prove the whole API, and R1 doesn't claim that |
| C | `python -m pytest tests/front/test_read_your_writes.py -q` | `PAIR`, `BRAIN-SEED` | 2 passed: 300 commits each, for pulse and topics, 0 misses. Reported as a trial, not as a guarantee about every read |
| D | `python -m pytest tests/front/test_locks.py -q` | `PAIR`, `BRAIN-SEED` | 7 passed |
| E | `python -m pytest tests/front/test_kill.py -q` | `PAIR`, `LEDGER`, `BRAIN-COPY` | 18 passed: 6 kill points, 3 times each. Why this covers A6's 4 points, 10 times each: section E |
| F | `python -m pytest tests/front/test_python_killed.py -q` | `PAIR`, `BRAIN-SEED` | 3 passed |
| G | `cargo test -p mentis-record --test chain_verifier --test codec_differential`, then `cargo test -p mentis-record` | Generated values, `BRAIN-COPY` | **13 passed** in the two named targets: section G. The whole crate's run passes too, with its total stated, since P1.1's unit tests aren't fixed here |
| H | `python -m pytest tests/front/test_sqlite.py -q` | `PAIR`, `BRAIN-COPY` | 4 passed |
| I | `python -m pytest tests/front/test_wrote_nothing.py -q` | `PAIR`, `BRAIN-COPY` | 3 passed |
| J | `python -m pytest tests/front/test_restart.py -q`, then `-m live` | `PAIR`, `LEDGER`, `BRAIN-SEED`, MARS | 13 passed, then 3 live passed. Passes as "A10 passes when" says, which **doesn't require the agent's turn to succeed.** The live cases need a logged-in runtime on Windows; if none is available, R1 isn't accepted |
| K | `python -m pytest tests/front/test_live_snapshot.py -q`, and `cargo test -p mentis-server live` for the exact boundaries | `PAIR`, `BRAIN-SEED` | 20 passed, and the crate's `live` tests, stated with that run's own count |
| L | `python -m pytest tests/test_worker_boundary.py tests/test_moved_run_acts.py tests/test_topic_lookup.py -q` | Their own | The baseline run's pass count first, on `b8e324c`. **`test_find_numbers_hits_as_turn_number_does` already fails there** (`opr-f50abde73219`), and is counted as that, not as R1's |
| M | `npm test`, for what changed in `apps/fluid-web` | | R1 changes no Fluid source. If that changes, the files run and the counts are stated |
| O | `python -m pytest tests/front/test_deploy_rollback.py -q -m live` | A disposable fixture server on `BRAIN-COPY`, MARS | 6 live passed |
| P | `python -m pytest tests/front/test_usable.py -q -m live`, and row M for any Fluid file changed | `PAIR`, `BRAIN-COPY`, MARS | 4 live passed |
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
| Snapshot age beside pulse, polls timed out, and stale and unavailable transitions, per level | not applicable | The 250 ms poll timeout sits below C0's pulse p95 at `n-cpu`, so this shows whether a busy Python goes stale. Reported, as the rest; a stale state under load is correct, not a failure |

**After a deploy:** the front keeps per-route p50 and p95 in a log, and the release report compares them with the bench while real agents are active. It is what shows whether a gain reached DAY-TO-DAY. Magnets on the bench are stand-ins, there's no MARS on it, and live state is empty there, so this is the only evidence for those.

**What the report says plainly:** R1's user-visible benefit is expected to be narrow (the `#` palette, the check for new replies, Fluid's files). Opening a Conversation, the lists and search don't improve until R2 and later.

## A: contract cases, 58

Each compares status, the headers named, and body against `PY-ALONE`, except where a case is about the front alone.

| Group | Cases | n |
|---|---|---|
| Host | Allowed: IP literal, `localhost`, `x.localhost`, `x.ts.net`, a `MENTIS_ALLOWED_HOSTS` entry, bracketed IPv6 with port. Refused, **421:** `evil.example`, `a.ts.net.evil.example`, `localhost:1:2`, no Host | 10 |
| Client header | Missing on GET, missing on POST, `/api/server` exempt, a preflight grants nothing | 4 |
| Grant | Presented on another route: 403 with that door's own wording (`contracts/route-table.md`). Presented on `/api/worker`: forwarded | 2 |
| Framing, refused or closed by the front exactly as Python does and never reinterpreted (`web/__init__.py:6276-6340,6497`) | `Transfer-Encoding: chunked`; `Transfer-Encoding : chunked`; duplicate Content-Length; conflicting Content-Length; non-digit Content-Length; a GET with a body; a second request pipelined after a refused one, which must not reach Python; HEAD | 8 |
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

## E: kill tests with the acknowledgement ledger, 18

Hard kills, by `TerminateProcess`. Each kill point runs 3 times under the writing load.

**Appendix A's count stands as the base, and covers A6.** A6 asks for 4 points, 10 runs each: front during a read, front during a forwarded write, Python during a write, both. K6 is the first. K1 and K2 are the second, split at the moment that decides what the agent may be told. K3 and K4 are the third, split at commit. K5 is the fourth. What A6 gets from 40 runs is more chances of landing in the window that matters, and these **place** the kill at that window with a test hook or a test-held request, not by timing. A point that can only be hit by timing has to say so in its test and run 10 times, as A6 does.

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
- **The write answered during the kill got the right words:** K1 and K2 as `docs/rust-front-restart.md`, cases A and B, never "nobody answered" for a write that may have committed.
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
| Altered copies, 4 | A changed chained field, a removed row (A7's `seq` gap), a reordering, and a changed stored hash (A7's, added to appendix A's three): each is reported at the same `seq` as Python's verifier |

**Fixed count, 13.** `codec_differential`, 8: one test for each of the 7 rows above the altered copies, and the 10,000 generated rows at a fixed seed. `chain_verifier`, 5: agreement across the whole copy, and the four altered copies.

Rust and Python must agree across the whole of `BRAIN-COPY`: the same row counts, heads and result per table. P1.1 checks this codec against the code before relying on it, and any correction goes back into this section. I read it against `store.py` at `b8e324c` and the formula and field encoding match; the table's differential cases are P1.1's to prove.

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

**A10 passes when** each case behaves as that page says, once corrected by what the test finds, and every message the agent sees is true. It must also show no acknowledged write lost, and no duplicate for keyed writes. The gap is measured and reported. **A10 does not require the agent's turn to succeed.**

## J: restart, 13 and 3 live

Numbers J5 to J7 keep their places from appendix A, because other documents cite them.

| # | Case | Must show |
|---|---|---|
| J1 | E | A planned stop: new connections are refused at once, a slow forwarded read and a forwarded write both finish, the front exits, and Python's pid is unchanged. A call past 35 s is cut at 35 s. The gap is reported |
| J2 | A | A call in the gap gets `NoOwner`'s words, and Python sees no such call |
| J3 | C | Started in the gap: a hand-started bridge exits 1 with its message; a `boot_command` server stays up, lists its tools, and its first call is J2 |
| J4 | B | A reset after sending, with Python going on to commit: the agent is told the result is unknown, and the write is in the record. **Tested before the wording changes,** to confirm the inference |
| J5 | | An owned route rolled back in the route table takes effect with no restart, within 2 s |
| J6 | E, **live** | A real MARS run through a planned front restart. **Reports the gap, any call that failed and with what words, and whether the turn survived.** Passes on every message being true and the processes, grant and feed surviving. It doesn't require a run with no failed call |
| J7 | B, **live** | A real run through a front kill keeps its execution, grant and feed. Whether the turn survived is reported, not assumed |
| J8 | B | The front killed while a reply's body is arriving: the agent is told the result is unknown, not `IncompleteRead` |
| J9 | B | Python killed with a call forwarded: the front's 503 reason says the result is unknown |
| J10 | D | Each keyed write repeated after a reset, under the same key: `answer`, `timer`, `anchor`, `react`, `deep_dive`, `POST /fluid/api/posts`. One occurrence each, `replayed: true` |
| J11 | D | **A source check:** the agent list in `docs/rust-front-restart.md` equals `ALL_TOOLS`, `READ_ONLY` and each schema's `op` |
| J12 | D | Repeating unkeyed writes does what the page says: `open_conversation` and `record_discovered_work`, which it says could duplicate, and `take_up`, which it says refuses. A surprise corrects the page |
| J13 | F | A reader polling through the gap gets an answer on its first poll after, and rereads once |
| J14 | F | A post retried across the gap under its composer's `op`: one post |
| J15 | | Through a planned restart and a kill, under writes: every `LEDGER` row is present, and both chain verifiers pass |
| J16 | C, **live** | **Measured:** a real session whose hand-started bridge starts in the gap. Reports whether it has Mentis tools and what the agent did. Passes on the report being made |

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

## P: usable, 4 live

Through the front, on a test server. A14 maps here. `tests/front/test_usable.py`.

1. **Fluid loads:** the index, every asset it names, and the reads Fluid makes on opening all answer as Python's do. No browser test tool exists in this repository, so this is HTTP-level. Whoever runs row P also opens it once in a browser, if their runtime can, and the report says whether that was done.
2. **The palette answers:** `/fluid/api/topics` for a `#` query, from the front.
3. **A new post appears through pulse:** posted through the front, the durable half moves, `moved` names its Conversation, and the post reads back.
4. **A real agent run on MARS completes,** with its Mentis calls going through the front, shown by the front's log. Unlike J6, nothing is restarted, so this one does require the turn to succeed.

## A1 to A15

Every check of `adm-56082aa297b0`, section 3.1. **A count may change only with the reason stated.**

| Check | What | Row | Test file | Fixed count |
|---|---|---|---|---|
| A1 | Owned routes match Python | A: Host 10, Client header 4, Grant 2, Pulse 7, Topics 7, Names 4, Static 5 | `tests/front/test_front_contract.py` | 39 of A's 58 |
| A2 | Forwarding transparent | B | `tools/bench/answers.py` | 47 reads, 0 unexplained |
| A3 | Forwarding framing | A: Framing 8, Streaming 4, Forwarded answers 3, Peer 4 | `tests/front/test_front_contract.py` | 19 of A's 58 |
| A4 | Read-your-writes | C | `tests/front/test_read_your_writes.py` | 2, of 300 commits each |
| A5 | Locks | D | `tests/front/test_locks.py` | 7 |
| A6 | Kill points and ledger | E | `tests/front/test_kill.py` | 18. Appendix A's stands, for section E's reason |
| A7 | Verifiers and codec | G | `crates/mentis-record/tests/chain_verifier.rs`, `codec_differential.rs` | 13 |
| A8 | Rust wrote nothing | I, and H4 at run time | `tests/front/test_wrote_nothing.py` | 3 |
| A9 | SQLite and bounded read | H. **2 s, not A9's 5 s** | `tests/front/test_sqlite.py` | 4 |
| A10 | Restart effect | J | `tests/front/test_restart.py` | 13, and 3 live |
| A11 | Live-state freshness | K | `tests/front/test_live_snapshot.py`, `crates/mentis-server/src/live.rs` | 20, and the crate's |
| A12 | Python killed | F | `tests/front/test_python_killed.py` | 3 |
| A13 | Deploy and rollback | **O, new** | `tests/front/test_deploy_rollback.py` | 6 live |
| A14 | Usable | **P, new**, and M | `tests/front/test_usable.py` | 4 live |
| A15 | Reported, not a gate | N, and "Performance" | `tools/bench/run_workload.py`, `compare.py` | 4 levels, 0 bad statuses required. Figures reported |

## Rollback, to show before release

Rollback is a correctness requirement, not a nicety:

| Level | How | Effect on runs | Brain |
|---|---|---|---|
| One route | The table back to `python`, until its handler is retired. No restart | None | Rust wrote nothing |
| The front | The previous binary, through `deploy-front.ps1` | Processes survive; a run may be affected (`docs/rust-front-restart.md`) | Rust wrote nothing |
| R1 | `rollback-to-python.ps1`: Python on 8760 again | Live runs end, as in any Python restart. Asked | Rust wrote nothing. Python's startup acts are its own |

## Who has what

P1.0 and these interfaces are reviewed with the first release review. P1.1, P1.2 and P1.5 have independent cross-runtime review. A correction is re-reviewed for what it changes. Release reports list open retirements, so two half-owners stay visible. The owner's rule on Python changes is in `AGENTS.md`.
