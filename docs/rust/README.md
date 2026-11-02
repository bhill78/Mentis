# The Rust migration: what R1's packages share

Plan: `PLAN-r3.md` (`adm-6e15a0d880ba`), as corrected by the owner in Turn #1025 `ent-9a3dff0b382f` and Turn #1034 `ent-a60e9f7e22b4`, which win where they differ. Where note `ent-beb03f957b87` says so, `adm-56082aa297b0` governs: restart (3.2), snapshot (3.3), retirement lists (5) and write prerequisites (6). Source citations here are at `b8e324c`.

**Destination:** one Rust executable owns the backend, `corpus.db` stays authoritative and unchanged, MARS stays separate, and Python leaves at the end. Rust never writes a Brain until R7, and R7 needs its own approval.

**Performance under concurrent agents, Fluid and Magnets stays a primary objective.** It is measured and reported at every release, and no release is held back by a threshold.

## Where things are

| What | Where |
|---|---|
| Everything that isn't a route | [`P1.0-inventory.md`](P1.0-inventory.md) |
| Every route, classified | [`routes.md`](routes.md) |
| What R1 has to pass, with A1 to A15 mapped. **Frozen once reviewed** | [`R1-acceptance.md`](R1-acceptance.md) |
| How the fixtures are built, and what they must come out as | `tools/r1/`, [`evidence/`](evidence/) |
| What an agent may be told across a restart, in full | `tests/front/restart_messages.json` |
| What a front restart does to agent calls | [`../rust-front-restart.md`](../rust-front-restart.md) |
| What Python keeps, and until when | [`P1.0-inventory.md`](P1.0-inventory.md), section I |
| What a Rust write needs first. Not R1 work | [`write-prerequisites.md`](write-prerequisites.md) |
| Route table: format, re-reading | [`contracts/route-table.md`](contracts/route-table.md), `crates/mentis-server/src/route_table.rs` |
| Record: read traits, read scope | [`contracts/record.md`](contracts/record.md), `crates/mentis-record/src/lib.rs` |
| Ops: the read signature for R2 and R3 | [`contracts/ops.md`](contracts/ops.md), `crates/mentis-ops/src/lib.rs`, `crates/mentis-rules/src/lib.rs` |
| `GET /private/live` | [`contracts/live-snapshot.md`](contracts/live-snapshot.md), `crates/mentis-server/src/live.rs` |
| Launcher | [`contracts/launcher.md`](contracts/launcher.md), `crates/mentis-server/src/launch.rs` |
| Bench command | [`contracts/bench.md`](contracts/bench.md) |

Dependencies run one way: `mentis-server` → `mentis-ops` → `mentis-rules` → `mentis-record`. Only `mentis-record` may depend on `rusqlite`.

## Who builds what

| Package | Builds | Reads | Touches |
|---|---|---|---|
| P1.1 | The `mentis-record` traits, locks, chain verifier, and the 20 unit tests named in `R1-acceptance.md`, section G | record | `crates/mentis-record` |
| P1.2 | The front, checks, passthrough, peer header, drain, latency log, table re-read | route-table, launcher, live | `crates/mentis-server`, adding `src/front/` |
| P1.3 | `now_reads`, `names`, pulse, `moved`, topics, static's table entry | ops, record, live | `crates/mentis-rules`, `crates/mentis-ops`, one handler file each in `crates/mentis-server/src/handlers/` |
| P1.4 | `tools/bench/`, the baseline, SQL trace, `answers.py record --brain`, nonzero exits | bench | `tools/bench/` |
| P1.5 | `mentis-launch` with its `--upstream`, deploy scripts, launch paths, `--answers-at`, trusted peer, worker transport, `/private/live`, and the named deliverables P1.5-PAIR and P1.5-J4-before | launcher, live, `R1-acceptance.md` | `crates/mentis-server/src/bin/mentis-launch.rs`, `mentis/`, `docs/cutover/` |

P1.3 and P1.2 meet at `HANDLERS` in `crates/mentis-server/src/lib.rs`, which is one list and merges by adding lines. Each package adds its crates' dependencies to the root `[workspace.dependencies]`, one line each, and takes `Cargo.lock` from a build after merging rather than resolving it by hand.

## Choices made here that r3 did not settle

Each is reversible and within the approved plan.

| Choice | Why |
|---|---|
| Crates live in `crates/` under a root `Cargo.toml`, with toolchain and licence policy copied from MARS | The request said root. r1 had said `rust/` |
| The HTTP library is left to P1.2 (r1 left it to the builder) | See the warning in `contracts/route-table.md`: a library that answers malformed framing itself would differ from Python's answers |
| **P1.2 uses none.** `front/head.rs` reads a head by `http.server`'s and `email`'s rules over tokio, and what it isn't sure of goes to Python, without the boot secret if Python might read it as under `/private/` | `Transfer-Encoding : chunked` and its like have to get Python's own answer, and a forwarded head has to go on byte for byte. Measured by hand against `PY-ALONE`: 65 raw requests, on the empty table and on one owning `static`, 0 differences. The rows on `PAIR` are what decide it |
| A forwarded request gets its own connection to Python, never kept | A kept one that Python dropped can't be told from Python dying with the request in hand, and those are the two opposite 503s |
| `mentis-server --verify-chains <brain>` prints `ChainVerifier`'s result | Rows E and J15 need Rust's verifier on the run's copy, and the Python harness needs something to call |
| `deny.toml` allows `foldhash` (Zlib) by name, as MARS allows `unicode-ident`: `rusqlite` needs it through `hashlink` and `hashbrown` | The policy is MIT, Apache or BSD, and this is a permissive licence for one crate. For the owner to ratify. `cargo-deny` isn't installed here, so this was checked with `cargo metadata`, not by running it |
| The launcher is a second binary, `mentis-launch`, and the deploy scripts call it | A stable command for an installer, no PowerShell in the launch contract, and a named path to POSIX. The detached start stays with the scripts, as in `mars-switch` |
| The route table is a JSON file, read once a second, with the last good table kept | `serde_json` is already here. Comparing bytes needs no file watcher |
| `sql` is `&'static str`, and a list of ids is one JSON parameter through `json_each` | It makes "statements fixed per call, not per id" true by construction |
| A scope's 2 s starts when its snapshot exists, not at open, and an idle scope is ended too | See `contracts/record.md`. The progress handler alone can't do either |
| One per-boot secret, `MENTIS_BOOT_SECRET`, that outlives a front restart | Python holds it for its whole life, so a restarted front has to present the same one |
| `/private/*` on the public port is the front's own, and is never forwarded | A forwarded `/private/live` would carry the front's secret to anyone who asked |
| Freshness is judged from when the poll was sent, on the front's monotonic clock | It needs no wall clock, and errs old rather than fresh |
| While polling is off, the snapshot's age keeps growing but doesn't count toward unavailable. A resumed front is stale until its first answer, with 10 s from the resume | The reconciliation required that resume isn't unavailable and left how. Stale, not fresh, because the hash is old; not unavailable, because nothing failed |
| With nothing held, the state is unavailable, and `live` is on unavailable as well as stale | Removes the special all-zero hash, and lets a report read the state from one place. Section 3.3 names `live` only for stale |
| A changed `boot_id` or lower `generation` isn't adopted, so it passes through unavailable | Section 3.3 lists a new boot as unavailable, and this makes that true. It costs a fast restart one extra reread |
| Row A grew by 3 cases, row I by 1, and row G has a fixed 13 | A3's error statuses and headers, A8's source check and A7's altered hash had no case. Row G had no fixed count |
| BRAIN-SEED pins `uuid4` and `time.time` in its own process | It gives a byte-identical `corpus.db`, so the identity needs no normalising |
| PY-ALONE is fixed at `b8e324c`, in its own checkout | P1.5 changes Python, and a differential that ran R1's Python on both sides couldn't see a regression there |
| Row L's command names a `MENTIS_FLUID_DIST` that doesn't exist | The one allowed failure turns on whether a Fluid build is present, and the row's outcome mustn't |
| R1's new wordings are frozen in `tests/front/restart_messages.json` | They had to be decidable before P1.2 and P1.5 write them. Reversible until this commit's review |
| The bench and `PAIR` run the launcher `--attached` | The bench gate counts only its own process tree; a detached front would invalidate the run |
| A `NotPermitted` message is checked against the harness's `tools/r1/door_recorder.py` and the record's rows, not its words | A pattern can't tell a false one, and a log the front wrote can't either, since the front is what's being judged (Quill, `ent-f5a9651b59d8`). It is on Python's side of the front, so it outlives a front restart and kill. No Python change and no production behaviour; the launcher gains only `--upstream`, for J6 and J7. Reversible until this commit's review |
| `copy_brain.py build` refuses a manifest that already exists, and row Q checks the manifest's tool blob is in the tool's history, not current | Build used to write over the committed manifest in silence. The manifest names what built the master, which a later change to the tool doesn't alter |
| A poll of `/private/live` that comes to nothing stays in hand, and the next tick looks at it rather than starting another. An answer is framed by its `Content-Length` | A suspended Python's port accepts into a backlog it can't drain, so a new connection each tick fills it in seconds, is then refused, and reads as Python gone. Windows also takes about 2 s to refuse a loopback connect, past the 250 ms timeout. Measured on row K. Framing by length is because `door_recorder` keeps a connection open whatever the request asks |
| An owned route forwards what it can't be sure Python would read the same: a query with a fragment or a byte outside printable ASCII, an escape that isn't UTF-8, a number in another script's digits, a name that isn't text, letters Python 3.12's case table doesn't know, and an id holding `/`, whose 400 quotes its `repr` | "Unknown means forwarded": Python's answer can't differ from itself. `mentis_ops::python` is held to Python at every code point |
| `now_reads` and `moved` read everything a walk could need first, a fixed number of statements, and then run Python's walk in memory | So what the walk remembers, and which branch of a fork it takes, come out as Python's do, and no statement count grows with the ids. Statements per call, position counted, the same warm, just after a commit and cold: pulse 1, pulse with `since` at most 19, topics 6, names 5 |
| Row K's "stalled" is a proxy in the harness holding `/private/live`, and K1's live change is real MARS with `tests/fakes/mars_acp_agent.py` | R1 adds no hook to Python, and on `workload-no-mars-here` a dispatch ends before a run opens, so nothing else moves Python's live state from outside it. No logged-in runtime is needed. Reversible until the review of this package |

## What changed after the first version of these documents

The foundation at `bcc76e3` was written to `adm-6e15a0d880ba`. The corrections after it:

| As first chosen | Now |
|---|---|
| Staleness harmless and unbounded in R1, with an opaque `generation` | Fresh, stale, unavailable from R1, with `boot_id` and an integer `generation` in an envelope. On-demand polling, the 250 ms timeout and age from the poll's send time are kept |
| A 10 s automatic retry in the worker, and "a planned restart should cost a run nothing" | **Removed.** No retry. Cases A to F, in `../rust-front-restart.md`. Drain is 35 s, not 30 s |
| Later front-only releases deploy if they don't interrupt runs | A standing yes only when no run is active, with the owner told what changed. A deploy script lists runs and asks. R1's first deploy and R3's are asked |
| `_UNGATED_READS` shortened at R3, the gate gone at R6, `render_check` gone at R5, `SharedAnswers` gone at R6 | All stay to R7 |
| `_POLLED` gone at R4 | R6, which also differs from section 5, because two of its routes are R6 |
| Rows J 5 and 2 live, K 4, none for A13 and A14 | J 13 and 3 live, K 20, new rows O and P |
| Row E 18, 3 runs per point, argued to cover A6 | **60, 10 per point.** A6's requirement stands, and the argument is gone |
| Row P HTTP-only, with a browser if the runtime could | **5 live, with a real browser.** No browser fails the row |
| The front logged Python's 403s to `worker-refusals.jsonl` for row J, and row A's Grant case checked the log | **Withdrawn,** with the front's `--run-dir`. The harness's `tools/r1/door_recorder.py` holds that evidence. Row A's Grant case stays 2, and checks the 403 is relayed as sent |
| Test files and fixtures as proposals, some counts left to a later run | **Frozen.** G0's fixtures built and recorded. `PAIR` is the system under test, checked as P1.5-PAIR on the integrated packages. Counts fixed in rows G, K, L, M. Moving and report-only oracles in A10 removed |

## Keeping things apart

- `.mentis-artifacts/`, `target/`: not committed. Fixtures live outside the repository, under `C:\Work\Mentis-workspace\r1-fixtures`.
- **Live Brain:** nothing in this workspace opens it, and no test may. `AGENTS.md`, "Brains".
- **Python:** R1's only Python changes are P1.5's, listed in `contracts/launcher.md`.
