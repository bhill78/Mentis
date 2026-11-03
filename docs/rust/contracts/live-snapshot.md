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

`mentis_ops::overlay` holds this rule against ordinary safe route code, within the
limits below. `Snapshots::overlay()` gives no `Overlay` unless what is held is fresh.
A route cannot name or read `LiveSnapshot.fields`: the decode field and `LiveFields` are private to
`live.rs`, and `LiveSnapshot`, `State`, `Held`, `Polled` and `Snapshots` neither print, serialize nor
compare the two decoded lists. `live.rs` projects them only into a redacted `Overlay`.

Coherence is bound to the durable read, not to a public `Position`. Inside
`mentis-ops`, an op mints an opaque `ReadToken<'scope>` from the `ReadScope` it was handed.
The constructor and token fields are crate-private, the token has no `Deserialize`, and its
lifetime borrows that scope. Server code cannot build one from `ReadAnswer::as_of`, construct one
directly, or keep one after the scope. `Overlay::coherent_with` is private. `LiveSnapshotRead` is
the executable seam proof: public `run` gives it a real scope, it performs any durable query first,
then calls the real crate-private `read_token` and applies one fixed projection.

| The read | The call inside its op | Forwards (`OpError::NotOwned`) when |
|---|---|---|
| Shows the lists, such as `/api/activity` and the `RUNNING` lines | `overlay.active_executions(&read)?`, `overlay.run_observations(&read)?` | The field is absent, or the poll has no marker or is before the token's real read |
| `/api/conversations` live counts | `overlay.conversation_counts(&read, durable_counts)?` | The field is absent; or a changed count comes from a markerless or behind poll |
| Fluid `_live` compare-first step | `overlay.live_workers_changed(&read, &open_runs, &durable_workers)?`; only `true` then reads both lists with the first row's calls | Either field is absent; or a changed worker map comes from a markerless or behind poll |
| Expectation `live_execution` | `overlay.live_execution(&state, &read)?`, then `.as_bool()?` or `.refs()?` | The field is absent; or the poll is markerless or behind and only the overlay changes the requested boolean/list |

These are the only comparisons. There is no general callback: `work_out`, `Unsettled`,
`Durable`, `Absent`, and the panic catcher do not exist. Therefore no public signature runs
caller code while lending it an unchecked list, and neither the static-exfiltration nor panic-hook
consumer has a method to call. Compile-fail doctests cover both old consumer names, passing a
`Position` where a token is required, the known name `ReadToken::new`, `LiveSnapshot`
serialization/comparison, and `Overlay`/`LiveExecution` comparison. They do **not** prove that no
unknown public minter exists. The token lifetime is checked against the real `read_token` by the
M10 mutation test; a doctest cannot name that crate-private function from its external test crate.
`Overlay` and `LiveExecution` keep redacted `Debug` and no `PartialEq`.

**What is still not enforced:**

- **Deliberate forgery.** A deliberately lying `ReadScope` or `RecordReader`, a forged marker via
  the explicitly named cross-crate decoder hook, or a real older scope gets past the guard. The
  token trusts `scope.position()`. These are outside the honest-route threat model.
- **`unsafe`.** `mentis-ops` forbids unsafe code, but unsafe code anywhere else, including
  `mentis-server`, can manufacture a token or violate its memory boundary.
- **The outcome reveals one required bit.** Forward versus answer says whether the fixed comparison
  changed the durable answer. The rule requires that distinction so a truly unchanged answer can
  return unchanged.
- **`live_execution` trusts its `ExpectationState` input.** An op could supply a made-up state to
  probe that one required bit. The method still never yields its references from an incoherent poll.
- **The durable value is the op's word.** The guard does not validate a supplied durable count,
  open-run list, worker map or expectation state. It only decides whether the fixed comparison's
  live contribution may be used. Those arguments cannot carry either decoded live list into the
  call because the comparisons are implemented inside `overlay`.
- **Repeated calls are an oracle.** Calls to `conversation_counts`, `live_workers_changed` and
  `live_execution` can be repeated with chosen durable inputs to recover more than one bit. Only
  code inside `mentis-ops`, which can mint the token, can do this in ordinary safe Rust.
- **An overlay is for one read.** It must be obtained immediately before that read and dropped
  afterwards. A held `Overlay` keeps answering after the front snapshot's freshness has ended;
  the type does not carry a clock and does not enforce this lifetime.
- **A row from a coherent poll is an ordinary row.** `ActiveExecution` and `RunObservation` keep
  their `Debug`, `Clone`, and serialization for reads whose answers show them.

Globals, files, threads, output, and panic hooks are no longer a separate accidental safe-code exception:
there is no caller callback receiving an unchecked list. Route access to the decode fields is also
closed through ordinary field access and representation traits. Deliberate unsafe access and the
public cross-crate decoder hook remain stated limits above.

Acceptance tests both directions through the real poll client, real Python producers, public
`mentis_ops::run`, and `LiveSnapshotRead`: a durable end landing while a poll is in flight forwards
when the old overlay changes the answer, while a moved record whose overlay makes no difference
does not. They also test the deliberate window after `end_execution` and before its durable end,
the correcting reread, real byte omission/decoding, markerless forwarding through every fixed path,
and the raw two-reference, overlay-only and durable-only unions plus their booleans. The hand-built
matrix remains additional guard coverage, not the parity proof. The review did not trace the
`record_delivery` exception path far enough to verify that a durable end follows when
`record_delivery` raises; that exception remains unverified.

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
