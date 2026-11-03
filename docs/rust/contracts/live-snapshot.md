# Contract: `GET /private/live`

Code: `crates/mentis-server/src/live.rs`, the type, timings and the state rule. P1.5 writes Python's route, P1.3 the front's client. Governed by section 3.3 of `adm-56082aa297b0`.

**Why it exists.** Run state lives only in Python until R7. The pulse token's live half needs it, and from R4 so do reads that show run or work state.

**It is never used for authority or a write decision.**

## The request

`GET http://127.0.0.1:<private port>/private/live`, with `X-Mentis-Boot-Secret`. No `X-Mentis-Client`. Refused 403, `{"error", "kind": "PermissionError"}`, without the right secret. Only ever on the private port (`contracts/launcher.md`).

**Python's route reads no record.** It calls `st.agents.live_now()` and `st.agents.run_marks()`, under the service's lock and nothing else, so a long write can't hold it up and it costs no statement. A later named field may use the service lock or copy another process-local registry with that registry's own lock (or with no lock where the registry has none), but it must not hold two locks at once, touch git or files, call MARS, or run a record statement. The one MARS exception is a direct read of the in-process `running()` set under MARS's own lock, provided no other lock is held; that is a local copy, not an ACP call.

Growth is measured, not rejected by definition. The **10 ms p95 per-field budget is the Builder's first screen**, not the owner's number and not a release pass/fail rule in the approved plan. This correction also chooses a **15 ms p95 total** for all added fields and a **750 KiB total encoded-field limit**. The earlier 14.09 ms/about 686 KiB sum mis-paired the 1,000-active `run_observations` case (9.95 ms/about 685 KB) with an eight-active `active_executions` case. For matched 1,000-active populations, the figures are arithmetic rather than a measurement: about 14.8 ms and about 814-830 KiB. That case exceeds the byte cap and is a limit, not a pass. The 15 ms timing cap is checked at admission; exceeding it fails admission and leaves the dependent routes forwarded to Python.

**One rule when the byte cap is met** (`_added_live_fields`, `web/__init__.py`). The cap is on the total of the added fields' encoded bytes; `live_now` and `run_marks` are required and not counted. The added fields are taken in one fixed order, `active_executions` and then `run_observations`, and a field that would take the running total past 750 KiB is omitted from that snapshot and adds nothing to the total. Exactly 750 KiB is within it. So a field over the cap alone is omitted, whichever it is, and in the matched 1,000-active case, where neither field is over and the total is, `run_observations` is omitted and `active_executions` stays: Turn views and live counts go on answering, and only the routes that need `run_observations` forward. A field that can't be encoded strictly as JSON (`allow_nan=False`, no `default`), or whose producer raises, is omitted the same way. An omitted field costs the envelope nothing, and the absent-field rule forwards every route that needs it. The front treats a field it can't read as absent too, and carries what a member says (`tooling` included) as raw text at any depth, so no added field can make a poll unreadable and so stale the pulse.

For each added field, copy its real objects, project its named JSON members and serialise it at the larger of its measured realistic process-lifetime size and declared structural bound on the target Windows host. Evidence states the population, active-result size, repetitions, p95 and encoded bytes, and reports load figures without turning them into a pass/fail line. A later population beyond the measured bound reopens the gate. Any lock-free copy also needs a source argument and a concurrent test proving the copy itself is atomic; timing it is not that proof.

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
| `live_hash` | **Python's exact expression,** `hashlib.sha256(repr((live_now, run_marks)).encode()).hexdigest()[:12]` (`web/__init__.py:172`). One Python function serves this and `/api/pulse`, so Python-alone answers can't drift. Rust never computes it, because `repr` is Python's. **R1 uses only this** |
| `taken_at` | `time.time()` when taken. For logs and reports, never for freshness |
| `fields.live_now` | `Service.live_now`: `[instance, liveness]` pairs (`core/service.py:1306`) |
| `fields.run_marks` | `Service.run_marks`, positionally: run, `performing_since`, `last_event.at`, `ended_at`, stop, permission count, activity (`core/service.py:1312`). Something that moves, **not a status:** nothing may read a state out of it |
| `fields.active_executions` | Optional. `Conversations.active_execution_rows`: `reference`, `participant`, `conversation`, `runtime`, `persona`, `for_expectation` of each live handle, in start order. Moves neither `generation` nor `live_hash` |
| `fields.run_observations` | Optional. `MentisService.run_observations`: `agents_runs`' answer, by run, in its order. `consent_applied` and `tooling` are absent until the run has ended. Moves neither `generation` nor `live_hash` |

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

## Coherence with a durable read

Freshness alone does not make a live overlay coherent with a newer durable snapshot. Immediately before writing a poll's HTTP request, the front samples the durable position and records it as that poll's marker. `Position` is three independent maxima and has no total ordering, so the read is "after" the poll (and the poll is "before" the read) when **any** component of the read's position is greater than the matching component of the poll marker. A failed sample gives the poll no marker. If an overlay entry would change a Rust read's answer and the held poll has no marker or is before the durable position used by the read, the route forwards to Python. An overlay that makes no difference may be ignored; the durable answer does not forward merely because the record advanced.

This rule covers `/api/conversations`' live count, entries `_live` adds that the durable Fluid conversation rows do not cover, expectation `live_execution`, `/api/activity`, and the `RUNNING` lines in full `/api/brain` and brain-scope `/api/context`. R4.1 owns the comparable poll-position/read-position seam. Record scopes block for up to `BUSY_TIMEOUT`, so the sample runs in `spawn_blocking` from the poll loop, and a poll waits for it for at most `SAMPLE_WITHIN` (50 ms). **A slow sample leaves that poll no marker; it does not hold the poll.** The poll asks anyway, so the pulse's hash stays fresh and an overlay that changes an answer forwards. The sample still running is kept and the next poll waits for that one rather than starting another, so there is only ever one; taken earlier, it is still from before that poll asks. While it waits the poll goes on reading the connection in hand, so a kill is heard as it happens during a sample, as it is between polls.

`mentis_ops::overlay` holds this rule against ordinary safe code, within the limits listed below the table. `Snapshots::overlay()` gives no `Overlay` unless what is held is fresh, and an `Overlay` gives neither list without the read's position, here `as_of`:

| The read | The call | Forwards (`OpError::NotOwned`) when |
|---|---|---|
| Shows the lists, such as `/api/activity` and the `RUNNING` lines | `overlay.active_executions(as_of)?`, `overlay.run_observations(as_of)?` | The field is absent, or the poll has no marker or is before `as_of` |
| Has a durable answer the overlay may change, such as `/api/conversations`' count and `_live` | `overlay.work_out(as_of, durable, compare)?`. `compare` takes `(&durable, live)`, gets the fields from `live.active_executions()?` and `live.run_observations()?`, and returns `Ok(None)` for no difference, which answers exactly `durable`, or `Ok(Some(changed))` | A field it asked for is absent, or it returned `Some` and the poll has no marker or is before `as_of` |
| Expectation `live_execution` | `overlay.live_execution(&state, as_of)?`, then `.as_bool()?` or `.refs()?` | The field is absent; or the poll has no marker or is before `as_of`, and for `.as_bool()` only the overlay makes it true, or for `.refs()` the overlay adds a reference |

A read that needs more to answer than to compare, as `_live` needs aliases, compares first with `work_out` and reads the list with the first row's calls only if that says it differs.

**How `work_out` keeps the lists in.** The caller no longer says "no difference" with a value of its own: the durable answer goes in first, and `None` carries nothing. `compare` is a plain `fn`, so it captures nothing. Its answer has to be `Durable`, which only `mentis-ops` adds to and only for plain owned data, so a list can't be the answer and `compare` can't write one into a `RefCell` it was handed. Its only error is `Absent`, which only the overlay makes. A panic's payload is replaced before `catch_unwind` could hand it on. `Debug` on `Overlay`, `Unsettled` and `LiveExecution` shows no list, reference or count, and `Overlay` and `LiveExecution` have no `PartialEq` to compare them against a guess. Each escape is a `compile_fail` doctest or a unit test in `overlay.rs`.

**What is still not enforced:**

- **`as_of` is the caller's word.** `Position` is a plain value, so a route passing an old or made-up position gets a marked poll's lists. A markerless poll forwards whatever is passed.
- **`durable` is the caller's word too.** `None` gives back what went in, so a wrong durable value answers wrongly. It can't carry a list, because it is fixed before `compare` sees one.
- **`compare`'s comparison is ordinary code.** A wrong one answers `durable` when the overlay did change it.
- **The outcome is itself one bit.** Whether a call forwards says whether the overlay made a difference, which the rule requires, because a truly unchanged answer must not forward. A caller repeating calls with a `compare` built to probe could work a list out bit by bit. `live_execution` called with a made-up state says the same kind of bit.
- **`compare` can reach what isn't passed to it:** statics and thread-locals, files and standard output, spawned threads, a panic hook, and `unsafe`.
- **`LiveSnapshot.fields` is public.** It is `mentis-server`'s decode type. `Snapshots` keeps what it holds private and `mentis-ops` can't name the type, so an op can't use it, but route code in `mentis-server` can and shouldn't.
- **A row, once out, is an ordinary row.** `ActiveExecution` and `RunObservation` keep their `Debug`, `Clone` and serialization, for what a coherent read shows.

These are for review to catch, in the route that does them.

Acceptance covers both directions. A durable end that lands while the poll is in flight makes the read position newer than the marker and must forward if the old overlay changes the answer. A moved record with an overlay that makes no difference must not forward. There is also a deliberate window after `end_execution` and before its durable end: Turn views remain consistent with the still-open record, but `/api/conversations` can differ from Python's live count for up to one poll. The durable end then moves the token. A reread forwards and corrects the count if the held poll is still older than the durable end; a poll taken after it already has the right count and forwards nothing. "Turn views remain consistent" covers runs with a durable start. The review did not trace the `record_delivery` exception path far enough to verify that a durable end follows when `record_delivery` raises; that exception remains unverified.

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
