# The Rust migration: what R1's packages share

Plan: `PLAN-r3.md` (`adm-6e15a0d880ba`), as corrected by the owner in Turn #1025 `ent-9a3dff0b382f` and Turn #1034 `ent-a60e9f7e22b4`, which win where they differ. Where note `ent-beb03f957b87` says so, `adm-56082aa297b0` governs: restart (3.2), snapshot (3.3), retirement lists (5) and write prerequisites (6). Source citations here are at `b8e324c`.

**Destination:** one Rust executable owns the backend, `corpus.db` stays authoritative and unchanged, MARS stays separate, and Python leaves at the end. Rust never writes a Brain until R7, and R7 needs its own approval.

**Performance under concurrent agents, Fluid and Magnets stays a primary objective.** It is measured and reported at every release, and no release is held back by a threshold.

## Where things are

| What | Where |
|---|---|
| Everything that isn't a route | [`P1.0-inventory.md`](P1.0-inventory.md) |
| Every route, classified | [`routes.md`](routes.md) |
| What R1 has to pass, with A1 to A15 mapped | [`R1-acceptance.md`](R1-acceptance.md) |
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
| P1.1 | The `mentis-record` traits, locks, chain verifier | record | `crates/mentis-record` |
| P1.2 | The front, checks, passthrough, peer header, drain, latency log, table re-read | route-table, launcher, live | `crates/mentis-server`, adding `src/front/` |
| P1.3 | `now_reads`, `names`, pulse, `moved`, topics, static's table entry | ops, record, live | `crates/mentis-rules`, `crates/mentis-ops`, one handler file each in `crates/mentis-server/src/handlers/` |
| P1.4 | `tools/bench/`, the baseline, SQL trace | bench | `tools/bench/` |
| P1.5 | `mentis-launch`, deploy scripts, launch paths, `--answers-at`, trusted peer, worker transport, `/private/live` | launcher, live | `crates/mentis-server/src/bin/mentis-launch.rs`, `mentis/`, `docs/cutover/` |

P1.3 and P1.2 meet at `HANDLERS` in `crates/mentis-server/src/lib.rs`, which is one list and merges by adding lines. Each package adds its crates' dependencies to the root `[workspace.dependencies]`, one line each, and takes `Cargo.lock` from a build after merging rather than resolving it by hand.

## Choices made here that r3 did not settle

Each is reversible and within the approved plan.

| Choice | Why |
|---|---|
| Crates live in `crates/` under a root `Cargo.toml`, with toolchain and licence policy copied from MARS | The request said root. r1 had said `rust/` |
| The HTTP library is left to P1.2 (r1 left it to the builder) | See the warning in `contracts/route-table.md`: a library that answers malformed framing itself would differ from Python's answers |
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
| The bench and `PAIR` run the launcher `--attached` | The bench gate counts only its own process tree; a detached front would invalidate the run |

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

## Keeping things apart

- `.mentis-artifacts/`, `target/`: not committed.
- **Live Brain:** nothing in this workspace opens it, and no test may. `AGENTS.md`, "Brains".
- **Python:** R1's only Python changes are P1.5's, listed in `contracts/launcher.md`.
