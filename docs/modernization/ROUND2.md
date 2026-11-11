# Round 2 — plan, ownership and working rules

The owner's words: `ROUND2-PROGRAM.md` (read it first). Round 1 contract: `CONTRACT.md`.

## Base

- Mentis integration branch **`release/dayday-modernize`** (worktree `C:\Work\Mentis-wt\modernize`)
  = DAY-TO-DAY release `cbfabaa` (branch `release/dayday-eff-r5`, Quiet Chat round 5) + `modernize`
  `687d2fd`, merged cleanly at `63a1835`. Fluid tsc + npm test pass on it.
- MARS integration branch **`modernize`** (`C:\Work\MARS-wt\modernize`) `82fdbf2`, which descends
  from the MARS DAY-TO-DAY runs (`4a92477`, binary `day-to-day\releases\deleg-4a92477\mars.exe`).
- DAY-TO-DAY today: Rust front `mentis-server.exe` + launcher from `releases\magnet-1c0c13a` on
  :8760, Python `mentis.web` on :18760 from `C:\Work\Mentis-dayday`, MARS `deleg-4a92477`.

## Builders and what each owns

Each builder works only in its own worktrees, commits on its own branch, never pushes, never
merges, never edits another builder's owned files. Anything outside its ownership that must
change: stop, describe it in the hand-back, the integrator decides.

| Builder | Mentis worktree / branch | MARS worktree / branch | Owns | Temp ports |
|---|---|---|---|---|
| A — authority | `Mentis-wt\r2-authority` / `r2-authority` | `MARS-wt\r2-authority` / `r2-authority` | O2, O3, O4, O5: `mentis/web/permissions.py`, `permission_rules.py`, `web/compiled_runs.py`, consent/restart code, authority/identity code in `worker.py` (`_authority`, participant/session identity, grants), MARS `consent.rs`, `continuity.rs` runtime_rules mapping | 8821–8829 |
| M — MCP | `Mentis-wt\r2-mcp` / `r2-mcp` | `MARS-wt\r2-mcp` / `r2-mcp` | O8: MARS `mcp_isolation.rs` and per-session MCP assembly; Mentis's side of what MCP servers a dispatched execution is given (`execution/mars.py` MCP block, bridge launch args) | 8831–8839 |
| P — parity | `Mentis-wt\r2-parity` / `r2-parity` | `MARS-wt\r2-parity` / `r2-parity` | O9 + §12: capability states in MARS (`registry.rs`, `catalog.rs`, `capacity*`, adapters `backends/*` except permission mapping), Mentis's consumption of capability states, the runtime-conformance suite (new `tests/conformance_runtime/`, `tools/runtime_conformance.py`), onboarding doc `docs/modernization/RUNTIME-ONBOARDING.md` (Mentis) + MARS `docs/onboarding.md`, live per-runtime verification, local-model worker | 8841–8859 |
| R — release | `Mentis-wt\r2-release` / `r2-release` | (none: reads only) | O1, O7 + §14 harness: deploy helper + bounded backup/rollback under `C:\Work\Mentis-workspace\day-to-day\modernize-release\`, Rust front route compatibility, `AGENTS.md`, `test_brainlock_claim` environment, perf harness `tools/perf_runtime.py` | 8861–8869 |

Shared files nobody else touches without the integrator: `docs/modernization/CONTRACT.md` (append
your own section only: "Round 2 — <builder>"), `mentis/web/dispatch.py` (A and P may need it: keep
edits small and local, name each hunk in the hand-back), `QUIET-CHAT-INTERFACE.md` (append only).

## Working rules (all builders)

- **Production is off limits.** Never stop, start, restart or write to :8760, :18760 or the live
  Brain `%LOCALAPPDATA%\Mentis\Mark-IV\brain`; never run anything from `C:\Work\Mentis-dayday` or
  `C:\Work\MARS-dayday`; never touch :8790 (Quiet Chat Mark 2 dev, MARS off), :8770, :8773, or
  `quiet-mark-2`. Never push, never merge to `main`, never deploy.
- **MCP checks use decoys.** The owner's user-level registrations (`~/.claude.json` `mentis`,
  `~/.codex/config.toml` `[mcp_servers.mentis]`, Kimi, Gemini/Antigravity) point at DAY-TO-DAY.
  Any live runtime session you start must be given an explicit client `mentis` server (a fixture
  bridge or a no-tools decoy) and must run with a HOME/config redirected per MARS conventions or
  with isolation proven first. Record live counts (`/api/server` is not enough: count acts in the
  live Brain read-only with `sqlite3 ... "select count(*) from entry"` via a read-only URI) before
  and after any live-runtime experiment.
- **Brains.** Throwaway fixture Brains only (`python -m mentis.web.fixture.build` or the round-1
  experiment harness), under `C:\Work\Mentis-Test-Server\r2-<builder>\`, deleted when done. Never
  copy the live Brain. (R alone may make ONE representative perf Brain: copy `corpus.db` only,
  hardlink `artifacts/` — see R's brief — and delete it when measurements are recorded.)
- **Tests.** Focused tests only during development. Default TMP (never set TMP/TEMP/basetemp for
  pytest); unset PYTHONPATH, MENTIS_SERVER and CLAUDE*/CODEX* first. `python -m pytest <files> -q
  -p no:cacheprovider`. The integrator runs the one full suite at the end. MARS: `cargo test`,
  `cargo clippy --all-targets -- -D warnings` in your MARS worktree (`rust\`).
- **Runtime calls cost quota.** Kimi K3 is out of capacity: check `/api/capacity` (or MARS
  capacity) once; if exhausted, do not call it again — report "capacity-blocked". Antigravity:
  use a Flash model with quota (never Argon High). Claude/Codex: keep live runs few and short.
- **Clean up** every server, runtime process, fixture Brain, temp home you start. List any you
  could not remove.
- **No Quiet Chat work.** Fluid changes only where a backend state you add needs wording (keep to
  the O6 vocabulary: green only for met/verified).
- Commit with clear messages ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Hand-back (each builder, as its final message)

1. Branch tips (Mentis, MARS) and a one-line summary per commit.
2. What each owner requirement you own now does, with the evidence (test names, live run ids,
   numbers). Mark each item: done-verified / done-unverified / blocked (why) / conflict (needs an
   owner decision — say exactly which capability vs which boundary).
3. Tests run and their results, exactly; tests you did not run.
4. Edits outside your ownership (file:hunk, why).
5. Everything you started and whether it was cleaned up.
6. Open defects you found but did not fix.
