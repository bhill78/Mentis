# Contract: `GET /private/live`

Code: `crates/mentis-server/src/live.rs`, the type and timings. P1.5 writes Python's route, P1.2 or P1.3 the front's poll.

**Why it exists.** Run state lives only in Python until R7. The pulse token's live half needs it, and from R4 so do reads that show run or work state.

## The request

`GET http://127.0.0.1:<private port>/private/live`, with `X-Mentis-Boot-Secret`. No `X-Mentis-Client`. Refused 403, `{"error", "kind": "PermissionError"}`, without the right secret. Only ever on the private port (`contracts/launcher.md`).

**Python's route reads no record.** It calls `st.agents.live_now()` and `st.agents.run_marks()`, under the service's lock and nothing else, so a long write can't hold it up and it costs no statement.

## The answer

```json
{
  "generation": "b1f3.17",
  "taken_at": 1793562208.0485663,
  "hash": "a1b2c3d4e5f6",
  "live_now": [["inst-1", "live"]],
  "run_marks": [["opr-1", 1793562000.5, null, null, false, 2, "Run npm test"]]
}
```

| Field | Meaning |
|---|---|
| `generation` | `<boot id>.<n>`: `n` goes up when `(live_now, run_marks)` differs from the last snapshot this boot took. It changes with each Python boot and each live change, and with nothing else. **Compare for equality only** |
| `taken_at` | `time.time()` when taken. For logs and reports |
| `hash` | **Python's exact expression,** `hashlib.sha256(repr((live_now, run_marks)).encode()).hexdigest()[:12]` (`web/__init__.py:2592`). One Python function serves this and `/api/pulse`, so Python-alone answers can't drift. Rust never computes it, because `repr` is Python's |
| `live_now` | `Service.live_now`: `[instance, liveness]` pairs (`core/service.py:1200`) |
| `run_marks` | `Service.run_marks`, positionally: run, `performing_since`, `last_event.at`, `ended_at`, stop, permission count, activity (`:1206`). Something that moves, **not a status:** nothing may read a state out of it |

**Later releases only add named fields.** The front's type ignores what it doesn't know, and a field a release adds is optional in the type. Nothing here is renamed, retyped or removed until runs move in R7. A release names the fields it adds and tests a stalled Python.

## Polling (R1)

| Rule | Value | Constant |
|---|---|---|
| Every | 500 ms | `POLL_EVERY` |
| Timeout | 250 ms | `POLL_TIMEOUT` |
| Only while a pulse was asked for within | 5 s | `POLL_WHILE_ASKED_WITHIN` |

One poll at a time. A late answer is discarded. No retry beyond the next tick. On the first pulse after an idle period the poll starts, and that pulse doesn't wait for it.

## Freshness

**Age** is the front's monotonic now, minus the monotonic time the answering poll was **sent**. That overstates the age slightly, which is the safe direction, and it needs no wall clock. `taken_at` goes in the log beside it.

| Release | Rule |
|---|---|
| **R1** | Staleness is harmless and unbounded: nothing reads the token except to compare it (`apps/fluid-web/src/fluid/identity/activity.ts:146`). A late live half delays one refresh. The front logs the snapshot's age beside pulse. This is a listed behaviour change, and it ends in R7 |
| **R4 onward** | A read that shows run or work state uses the snapshot only if it is at most 2 s old (`MAX_AGE_FROM_R4`). Past that it forwards to Python. If Python can't answer: 503 with the reason. **It never serves an older state** |

## The pulse token

`"<durable>/<hash>"`, built by `pulse_token`. Durable comes from the front's own read and is never held up. The hash is the last heard. Before the first snapshot it is `000000000000`.

**Python goes away:** durable keeps moving and the live half keeps its last value. **Python comes back:** `generation` differs, so the hash changes and every reader rereads once, which is right. Tests: `R1-acceptance.md` row K.

## When the front restarts

The snapshot is the front's memory, so it starts empty and takes the first poll after the next pulse. One reader rereads once more than it needed to.
