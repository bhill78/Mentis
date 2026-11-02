# The bench

Moved from `mirps-shared-ops\measure` for R1. What the command must do, what each result records and how rows B and N use these tools: [`docs/rust/contracts/bench.md`](../../docs/rust/contracts/bench.md). How the workload was drawn and C0's figures stay in the old tree's `workload\README.md`.

This directory holds code only. Everything else is in `C:\Work\Mentis-workspace\day-to-day\r1-bench\` (`BENCH_HOME` moves it, for tests):

| Under it | What |
|---|---|
| `bundle\render-check.js` | The object reader given to every server. Part of `workload_sha` |
| `results\<label>\` | `workload.json`, `raw.json`, `progress.log`, `answers*.json`. A label that has a result is refused |
| `run\<label>\` | Each boot's copies and logs, deleted after a run |
| `RUNLOCK`, `gate-events.jsonl`, `stale-locks\`, `gate-samples\`, `gate-results\` | The gate |

Nothing else may run during a timed run: `cargo`, `rustc`, `pytest` or a UI build anywhere invalidates it. Build first, then set `BENCH_HOLDER` and run. Changing anything `workload_sha` covers (`benchgate.HASHED`) means re-recording `baseline`.

| Exit | Means |
|---|---|
| 0 | Valid, with nothing badly answered, no difference, or the self-check passed |
| 3 | Refused: nothing ran, or the comparison isn't allowed |
| 4 | It ran, and came to an invalid run, a bad status, a difference or a self-check failure. The result is kept |
| Anything else nonzero | It stopped: a server that didn't start, a missing result, a crash |

A bad status is any non-200 foreground read, any background status but 200, including 503, any request that got no answer, or a refused write. Tests: `tests/bench/`.
