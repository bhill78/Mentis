# Contract: `GET /private/live`

Code: `crates/mentis-server/src/live.rs`, the type, timings and the state rule. P1.5 writes Python's route, P1.3 the front's client. Governed by section 3.3 of `adm-56082aa297b0`.

**Why it exists.** Run state lives only in Python until R7. The pulse token's live half needs it, and from R4 so do reads that show run or work state.

**It is never used for authority or a write decision.**

## The request

`GET http://127.0.0.1:<private port>/private/live`, with `X-Mentis-Boot-Secret`. No `X-Mentis-Client`. Refused 403, `{"error", "kind": "PermissionError"}`, without the right secret. Only ever on the private port (`contracts/launcher.md`).

**Python's route reads no record.** It calls `st.agents.live_now()` and `st.agents.run_marks()`, under the service's lock and nothing else, so a long write can't hold it up and it costs no statement. A later named field may use the service lock or copy another process-local registry with that registry's own lock (or with no lock where the registry has none), but it must not hold two locks at once, call MARS, touch git or files, or run a record statement. The copied work must also stay bounded for the lifetime of the process; an ever-growing registry is not made cheap merely by copying it before serialisation.

## The envelope

```json
{
  "schema": 1,
  "boot_id": "b1f3c07a",
  "generation": 17,
  "live_hash": "a1b2c3d4e5f6",
  "taken_at": 1793562208.0485663,
  "fields": {
    "live_now": [["inst-1", "live"]],
    "run_marks": [["opr-1", 1793562000.5, null, null, false, 2, "Run npm test"]]
  }
}
```

| Field | Meaning |
|---|---|
| `schema` | The envelope's version, `SNAPSHOT_SCHEMA`. Read first, on its own, so a later schema need not parse as this one |
| `boot_id` | Random per Python process. **Separate from `generation`,** so a changed boot can be told from a moved generation |
| `generation` | Integer. Goes up within a boot when `(live_now, run_marks)` differs from the last snapshot taken. Nothing else moves it, and it restarts with each boot |
| `live_hash` | **Python's exact expression,** `hashlib.sha256(repr((live_now, run_marks)).encode()).hexdigest()[:12]` (`web/__init__.py:2592`). One Python function serves this and `/api/pulse`, so Python-alone answers can't drift. Rust never computes it, because `repr` is Python's. **R1 uses only this** |
| `taken_at` | `time.time()` when taken. For logs and reports, never for freshness |
| `fields.live_now` | `Service.live_now`: `[instance, liveness]` pairs (`core/service.py:1200`) |
| `fields.run_marks` | `Service.run_marks`, positionally: run, `performing_since`, `last_event.at`, `ended_at`, stop, permission count, activity (`:1206`). Something that moves, **not a status:** nothing may read a state out of it |

**Later releases only add named fields to `fields`.** The front's type ignores what it doesn't know, and a field a release adds is optional in the type. Anything else changes `schema`. A release names the fields it adds and tests a stalled Python.

**Gate on R4.** Before R4 is built, the `fields` R4 to R6 need are listed from P1.0, starting with `live_now` and `run_marks`, and reviewed. Without that, those reads stay on Python.

## Polling

| Rule | Value | Constant |
|---|---|---|
| Every | 500 ms | `POLL_EVERY` |
| Timeout | 250 ms | `POLL_TIMEOUT` |
| Only while a pulse was asked for within | 5 s | `POLL_WHILE_ASKED_WITHIN` |

One poll at a time. A late answer is discarded. No retry beyond the next tick. On the first pulse after polling was off, polling starts, and that pulse doesn't wait for it.

**While polling is on, one connection to Python is always in hand,** and never more than one: the poll unanswered, or between polls an open connection with nothing sent on it, which the next poll asks on. It isn't a poll, and it costs Python a handler waiting to read and nothing else, because a request is counted only once it is parsed. It goes when polling stops. This is how a kill is heard as it happens, because the connection in hand ends with the process. A new connection to a closed port can't say so that fast: Windows keeps it pending for about 2.5 s before reporting it refused.

## Age

**Age** is the front's monotonic now, minus the monotonic time the last good poll was **sent**. That overstates the age slightly, which is the safe direction, and it needs no wall clock. `taken_at` goes in the log beside it.

**While polling is off,** the clock on the held snapshot keeps running, because that is the snapshot's true age, and the bound on unavailable doesn't, because nobody asked Python anything:

```
fresh        age <= 2 s
stale        age > 2 s,  and min(age, time since polling last turned on) <= 10 s
unavailable  otherwise
```

So resuming from idle, however long the idle was:

1. **The first pulse** answers `stale` with the true `age_ms` and the last hash. It isn't `fresh`, because the hash is old, and it isn't `unavailable`, because nothing has failed. **The hash doesn't change, so no reader rereads.**
2. **The first good answer** makes it `fresh`. If the live state moved while idle, the hash differs and readers reread once, which is right.
3. **If no answer comes,** it goes `unavailable` 10 s after the resume, not at once. A refused connection or a new boot is decided by the poll, as below.

## What a poll does

| The poll meets | Effect |
|---|---|
| A good answer, same `boot_id`, same or higher `generation` | Replaces what is held. Age restarts from this poll's send time |
| A timeout, a non-200, or an unreadable body | Nothing changes, and age keeps growing. This is what a suspended or very busy Python looks like, and a 403 from a Python holding another secret |
| Connection refused, or reset before an answer, or the connection in hand ending with nothing said | **Python is gone: unavailable at once,** not after 10 s. With polling on that is as the process ends. With polling off nothing is in hand, so after a kill during idle it is when the first poll's new connection is refused, measured at 2047 ms after the pulse that turned polling on, and until then the pulse is `stale` |
| A changed `boot_id` or a lower `generation` | **Discards what is held and isn't adopted.** Unavailable. With nothing held, the next poll's answer is adopted |
| An unknown `schema` | Discards what is held. Unavailable until a known schema answers |

## The states

These are correctness limits, not performance targets. 2 s sits well above C0's worst pulse p95 of 565 ms.

| State | When | Pulse, from R1 | Reads depending on live state, from R4 |
|---|---|---|---|
| **Fresh** | Age to 2 s | Normal token, no `live`: Python's shape exactly | Answer from the snapshot |
| **Stale** | 2 to 10 s | Durable half current, last hash kept, `live: {state, age_ms}` added | **Forward to Python. Never answer from the snapshot** |
| **Unavailable** | Past 10 s, Python gone, a new boot, or an unknown schema, or nothing held yet | Durable half current, hash is `unavailable`, `live: {state, age_ms}` added, with `age_ms` null when nothing is held | 503 with the reason if Python can't answer. Durable-only reads continue. **Never show last-known run state as current** |

## The pulse token

`"<durable>/<live>"`, built by `pulse_token`. Durable comes from the front's own read and is never held up.

**One reread per transition.** Stale keeps the hash, so entering or leaving it alone costs readers nothing. `unavailable` is one constant value, so readers reread once going in and once coming out, not on every beat (`apps/fluid-web/src/fluid/identity/activity.ts:146`).

**`live` is a listed additive difference from Python** (`R1-acceptance.md`, section A). It appears only when the state isn't fresh, and Fluid ignores it. Addition to section 3.3, which names `live` for stale: it is on unavailable too, so a report can read the state from one place.

| What happens | What readers see |
|---|---|
| Python stalls, then recovers within 10 s | Nothing, unless the live state moved |
| Python stalls past 10 s, then recovers | One reread going in, one coming out |
| Python killed | One reread. Then, when it restarts, one more |
| Python restarts between two polls | Two: into `unavailable`, then to the new hash |

Tests: `R1-acceptance.md` row K.

## When the front restarts

The snapshot is the front's memory, so it starts with nothing held, which is unavailable until the first answer, and polling starts on the next pulse. Its hash differs from any reader's, as a restart's would anyway.
