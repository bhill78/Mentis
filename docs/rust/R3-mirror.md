# R3: the grant mirror and the Rust door for reads

For review before building (`PLAN-r3`, section 4: revocation and authority). `adm-56082aa297b0` governs, with `adm-d613177f95fb` section 4 where it doesn't differ. Citations are at `d9281dc`. **Nothing here is built or run.** Timings are proposals, fixed by this review, and none has been measured.

## 1. The one place the plan's wording can't hold, and what this adds

The plan says a failed revoke push "marks the mirror invalid until it re-pulls". A failed push means the front wasn't told, so nothing Python does at that moment can mark the front's copy. A front that is suspended, or too busy to answer within the timeout, wakes up still holding the dead grant, and agents' connections are waiting in its backlog (the same behaviour row K measured for Python).

**So this adds a lease and a fence, and changes nothing else in the plan's design.** Python still mints, pushes in order and serves the pull. Generations still catch a gap, and an unknown token still forwards.

- **Lease:** the front answers from the mirror only while a confirmation from Python, *sent* within the last `LEASE`, says the mirror is current.
- **Fence:** when a push that removes or narrows a grant fails, the Python call doesn't return until any lease that could predate the change has run out.

**Alternatives rejected:**

| Alternative | Why not |
|---|---|
| Push again until it lands | An unbounded revoke, and a retry loop `AGENTS.md` rules out |
| Kill the front | Supervision, also ruled out |
| Check with Python on every read | Puts every read back behind the interpreter, which is what R3 exists to stop |

**The guarantee, which is what to attack:** *once a change that removes or narrows a grant has returned, no read the front admits afterwards is admitted on the old grant.* A read already admitted finishes, as on Python today (`adm-d613177f95fb`, section 4).

"Fail closed" here means **forward, never refuse and never serve**. Python holds the table, so forwarding is always the right answer, and it costs only speed.

## 2. What is mirrored

Python's table stays the only authority (`authority.py:25`). The mirror holds, per grant:

```json
{"<sha256 hex of the token>": {"corpus": "C:\\b", "scope": "worker", "operations": ["respond"]}}
```

| Choice | Why |
|---|---|
| **Keyed by the token's SHA-256, not the token** | The plan accepted a route that "hands out grants". This way the pull and the front's memory hold nothing that can be presented, and the lookup needs no constant-time compare. It goes beyond the plan and is reversible |
| **Only `corpus`, `scope`, `operations`** | The door needs only these. No moved read uses anything else from the grant: `_result` passes them only `args` (`worker.py:4115-4142`), and `Surface.permits`, set by the door, is read only by `orient` (`:839`), which isn't moved. `delivered`, `participant` and the rest stay in Python. A later release adds a field if it needs one |
| **`TRANSIENT_SCOPE` isn't mirrored at all** | Its token is unknown to Rust, so it forwards and `note_deleted_reads` keeps working. The door also forwards that scope if it ever sees it. Nothing in `mentis/` mints this scope at `d9281dc` (only tests do), and the rule stands regardless |
| **`operations` not a list or null, or a value that won't serialise** | Not mirrored, so it forwards. `permitted` uses `in`, which would mean something else on a string |

## 3. The protocol

**Python's state:** `boot_id` (random per process), `generation` (integer, up by one per mirrored change, starting at 0), `down` (bool, starts false) and `fence_until`. None of it exists without a boot secret: Python alone has `mirror = None` and behaves exactly as today.

### Changes

Every mutator follows the same order. Lock order is `_changes`, then `_lock`, and the pull takes only `_lock`.

```
with _changes:                     # one change at a time, so pushes go in table order
    with _lock:
        change the table           # Python refuses this grant from here on
        if the mirrored view moved: generation += 1; t = perf_counter()
    if the view moved and not down:
        push (generation, change), PUSH_TIMEOUT
        anything but a 200 {"ok": true}: down = True; fence_until = max(fence_until, t + FENCE)
if the change removed or narrowed, and now < fence_until: sleep until fence_until   # holding no lock
```

| Mutator | Pushes | Fenced |
|---|---|---|
| `_grant` (`authority.py:75`), `grant_session` (`:108`) | `set`, unless transient | No. A token the front lacks forwards |
| `authorise_for` (`:35`) | Only when a minted grant's `scope` or `operations` changed. `set`, or `drop` if it became transient. `delivered` alone (`web/dispatch.py:1824`) pushes nothing | Yes |
| `revoke` (`:98`) | `drop`, only if a token was spent | Yes |
| `end_session` (`:148`) | `drop`, only if a grant ended | Yes |

Pushes aren't retried. Once `down` is set, later changes bump the generation and push nothing, so a dead front costs one `PUSH_TIMEOUT` per outage.

### The three routes

The secret is required as for `/private/live`. Each private-port route answers 403 without it, and with no boot secret these paths mean what they always did.

| Route | Where | Body and answer |
|---|---|---|
| `POST /private/grants` | **Public port, the front's own.** Honoured only from a loopback peer with the secret, as `/private/stop` is (`connection.rs:297`). Anything else stays 404 | `{"schema":1,"boot_id","generation","digest","grant":{…} or null}` → `{"ok":true}` |
| `GET /private/grants` | Private port, Python's | `{"schema":1,"boot_id","generation","corpus":<st.path>,"grants":{…}}`. Taken under `_lock`, clears `down` |
| `GET /private/grants/position` | Private port, Python's | `{"schema":1,"boot_id","generation","down"}`. Under `_lock`, reads no record |

**Push target:** always `http://127.0.0.1:<port of answers_at>`, so the secret never leaves loopback. A front bound only to another address refuses the connection, so `down` is set and everything forwards. That is safe, with no gain.

**Not `/private/live`:** its contract says it is never used for authority, and it polls only while a pulse is asked for.

### The front's state

Pure, with no clock of its own, as `front/snapshot.rs`'s `State` is, so every rule can be tested at exact moments.

```
Empty                                        nothing to serve from
Pulling { sent, pending }                    one pull at a time; pending = pushes that arrived meanwhile
Held { boot, generation, table, confirmed_sent, behind }
```

**Serve only if** `Held`, not `behind`, and `now - confirmed_sent <= LEASE`.

| Event | Effect |
|---|---|
| Pull answered, known schema | Adopt, with `confirmed_sent` = the pull's send time. Replay `pending` above its generation; a gap pulls again |
| Pull refused or failed | `Empty`. Tried again at the next trigger below, not on a timer |
| Push, same boot, `generation == held + 1` | Apply. **Doesn't touch `confirmed_sent`** (see section 4, row 6) |
| Push, `generation <= held` | Already included. Ack |
| Push, `generation > held + 1`, or another boot | Discard the table and pull. Ack, because nothing is served until a table taken after this arrives |
| Push while `Empty` or `Pulling` | Keep in `pending`. Ack. A push that finds no pull in flight is itself a trigger |
| Position, `generation == held`, not `down`, same boot | `confirmed_sent` = that poll's send time, `behind` cleared |
| Position, `generation > held`, or `down` | `behind`; pull |
| Position, `generation < held` | Ignored, no lease credit: the poll raced a push it hasn't seen. A real regression never earns credit again, so it ends in forwarding |
| Position, another boot, or unknown schema | Discard; pull |
| Poll connection ends, refused, or reset | Discard at once (Python gone). This is the `Snapshots` connection-in-hand behaviour |
| Poll times out, non-200, unreadable | Nothing. The lease keeps running out |

**Pull triggers:** front start; a discard; a push that needs one; a presented grant while not `Held`. One at a time, and nothing retries on a timer.

**Polling:** every `POSITION_EVERY`, one at a time, using the same in-hand connection as `Snapshots`, whenever `Held` with at least one grant or while pulling. Agents read at intervals longer than the 5 s the pulse uses, so asking on demand would forward nearly every read of a lone agent. Polling has no supervising role, and it stops when no grants are held.

**A Python restart with an empty mirror:** no poll is running, but Python starts with `down` false, so its first mint pushes with a new `boot_id`, which discards and pulls.

### Timings

| Name | Value | Why |
|---|---|---|
| `PUSH_TIMEOUT` | 500 ms | The whole push. Windows takes about 2 s to refuse a loopback connect (`contracts/live-snapshot.md`), so a dead front costs this, not 2 s |
| `POSITION_EVERY` | 500 ms | As `/private/live` |
| `LEASE` | 3 s | Above C0's worst pulse p95, 565 ms (M), so a loaded Python doesn't normally push reads back to it. It only sets the worst-case fence |
| `FENCE` | `LEASE` + 100 ms | Python's `perf_counter` and Rust's `Instant` read the same clock on Windows (QPC) and Linux (`CLOCK_MONOTONIC`). The margin is for scheduling, not drift |

**Worst case for a revoke:** 3.6 s (`PUSH_TIMEOUT` + `FENCE`), once per outage. A successful push adds one loopback round trip. Both are reported as measurements.

## 4. Revoke: the exact order, and each failure

`t` is when the table changed. Python refuses the grant from `t`. Between `t` and the revoke's return, a Rust read may still pass, and that is before the revoke happened as far as its caller can tell.

| # | What happens | Why the guarantee holds | Revoke returns |
|---|---|---|---|
| 1 | Push is acked | The ack means applied, or that nothing will be served until a table including it (section 3) | About `t` + one round trip |
| 2 | Front dead | Nobody to admit anything. If a new front starts, its pull is after `t` | `t` + `FENCE` |
| 3 | Front suspended or stalled, push times out | A position sent before `t` gives a lease ending before `t` + `LEASE`. Any sent after `t` shows a higher generation, so `behind` | `t` + `FENCE` |
| 4 | Push reaches the front, ack lost | Applied, and Python is more cautious than it needed to be. `down` makes the next position pull | `t` + `FENCE` |
| 5 | Later revoke while `down` | Nothing pushed. Since the failure that set `down`, the front can serve only until that failure's `fence_until`, unless a pull taken after that failure cleared it | Waits at most to `fence_until` |
| 6 | Timed-out push arrives late, after a later change | **Why a push never renews the lease:** this late arrival would otherwise extend the lease past the later change's fence. It either applies or is ignored, with no lease credit | Already returned |
| 7 | Pull in flight when the push arrives | The answer may hold the grant. The push waits in `pending` and is replayed on adoption, and only then can anything be served | About `t` + one round trip |
| 8 | Pull answered before `t`, adopted after | As row 7 if the push arrived. Otherwise `confirmed_sent` is before `t`, so as row 3 | By row |
| 9 | Pull clears `down`, then a failing push sets it again | `down` stays set with the table already current. The next position pulls again and clears it. Forwards meanwhile | `t` + `FENCE` |
| 10 | Python killed | Every grant is dead. The poll connection ends, so the front discards at once. A read admitted in that instant finishes, and the Brain is unchanged by it | Nothing returns |
| 11 | Python suspended | No confirmation, so the lease runs out within `LEASE`. Reads forward and wait, as they would on Python | Nothing returns while suspended |

**Unverified, and wanted from the review:** I haven't confirmed that no mutator runs inside a store write transaction. A fence there would hold the writer for up to 3.6 s. Build task: check each call site. If one does, the fence moves after that transaction, and the guarantee is restated for that caller. `revoke` at `core/service.py:1322` is clear: it runs in a `finally` with no transaction open at that level.

## 5. The door

`POST /api/worker` gets a rule owned by Rust. Every case below that isn't "answer" sends the request on byte for byte, using `send_on`'s existing handling of bytes already in hand (`connection.rs:352`).

| Step, in Python's order | Forward when |
|---|---|
| Framing | A query, `Expect`, `Transfer-Encoding`, no well-formed `Content-Length`, or over `BODY_LOOK` (1 MiB, not read at all). Otherwise read the whole body before deciding |
| Host, client header (`web/__init__.py:6662`, `:6691`) | Host refused, or no grant presented. Python words those |
| `Content-Type` (`:6700`) | Not `application/json` |
| JSON (`:6705`) | `serde_json` refuses it. It accepts strictly less than `json.loads` (NaN, lone surrogates, other encodings), and its last duplicate key wins, as Python's does. Not an object, too |
| `op` | Not a string naming a moved read |
| `args` | Present and not an object |
| Corpus (`:3035`) | `corpus` is present, non-empty and not exactly the pull's `corpus`. Python resolves paths and words the refusal |
| **Mirror, checked last before reading** | Not servable, token not held, transient scope, or a scope or `op` whose `repr` isn't printable ASCII |
| Held grant for another corpus (`:3045`) | **Answer** 403 in Python's wording |
| `permitted` refuses (`:3050`) | **Answer** 403 in Python's wording. **Unreachable today:** every scope holds all six moved reads, which the matrix shows. It exists so a future shape is refused the same, never served |
| Permitted | `mentis_ops::run`, class `Agent`. `NotOwned` forwards, including any `resolve` kind not yet moved. `Busy` and `Record` follow `contracts/ops.md` |

**What Rust checks is never carried into Python.** A forwarded request is checked again in full, and a grant on any other route still gets that door's 403.

## 6. The route table, and the permission matrix

```json
{"id": "worker", "method": "POST", "path": "/api/worker", "owner": "rust"}
```

`HANDLERS` and `ROUTES` each gain `worker`, and `Door` gains `Worker`. `connection.rs`'s "only a GET is ever answered" changes for this one route. Additions are line by line, so R2's merge is separate. `routes.md` and `contracts/launcher.md` gain the routes above. `/private/*` is still decided before the table.

**Generating the matrix:** `tools/r3/permission_matrix.py` imports `mentis.worker` and writes `tests/front/permission_matrix.json`.

| Axis | Values |
|---|---|
| Scope | `None`, `""`, `worker`, `organising`, `intake`, `manual-session`, `transient-read`, an unknown scope, one holding a quote and one non-ASCII |
| `operations` | `None`, `[]`, every subset of `AUTHORITY` (64), `["delegate"]`, `["resolve_intake"]`, `["deep_dive"]`, an unknown name |
| Operation | All of `OPERATIONS`, `SESSION_ACTS`, `""`, an unknown name, one holding a quote and one non-ASCII |

Each shape records `permitted`'s exact ordered result, and the SHA-256 of its full refusal text for every refused operation, plus the texts themselves for a sample. Non-ASCII names check the door's forward, not Rust's wording.

| Test | What it catches |
|---|---|
| `crates/mentis-rules/tests/permitted_matrix.rs` | Rust differs from the file |
| `tests/front/test_permission_matrix.py` | The file differs from a fresh generation, so changing a Python rule without Rust fails here. A changed rule goes to both or waits |

## 7. What fails closed, in one place

| Condition | Result |
|---|---|
| Mirror `Empty`, `Pulling`, `behind`, or past its lease | Forward |
| Unknown token, or a Quick Ask grant | Forward |
| Python has no secret, or an old Python answers the pull 404 | Never `Held`: forward |
| Unknown schema on any private answer | Discard: forward |
| Python gone | Discard. Forwarded requests get R1's 503 with the reason |
| Any doubt about the request | Forward (section 5) |

Rust never refuses for a mirror reason, and never serves one.

## 8. Tests

All on F1 or a copy of F1 under `C:\tmp\r3-work`, in the existing front harness, with the front built in this worktree's own target directory. Final counts are reported with the build.

| File | Must show |
|---|---|
| `crates/mentis-server/src/grants.rs` (unit) | Every row of section 3's event table and section 4, at exact moments, no clock |
| `crates/mentis-rules/tests/permitted_matrix.rs`, `tests/front/test_permission_matrix.py` | Section 6 |
| `crates/mentis-rules` (`standing_many`) | Matches `Corpus.stands` on a dump, `as_at` included |
| `tests/front/test_mirror_python.py` | Each mutator pushes or doesn't, per section 3, in order. Python alone pushes nothing. The routes refuse without the secret. No token in any route's answer. No lock held during a fence |
| `tests/front/test_mirror_protocol.py` | Boot pull, gap, late push, push during a pull, new boot, old Python 404, old front 404 |
| `tests/front/test_door_answers.py` | Each moved read, per grant shape and `resolve` kind, equal to Python alone across F1 and a Brain copy: status, JSON, errors. Every "forward when" row goes to Python |
| `tests/front/test_door_authority.py` | Revoked, ended, previous-boot (what "expired" is here: grants have no clock) and other-corpus grants behave as on Python. A grant on another route still 403 |
| `tests/front/test_mirror_revocation.py` | **Load:** 4 readers per grant, 300 mint and revoke cycles. Any read *started* after the revoke returned must get Python's 403. Repeated with the front suspended by `NtSuspendProcess`, with a push proxy that stalls, and with one that drops the ack. Fence time reported |
| `tests/front/test_mirror_restart.py` | Front restart during a run: the mirror rebuilds and the agent's next read works, forwarded or not. Python restart: old tokens refused, new ones served |
| `tests/test_worker_boundary.py` | Retargeted: `owner` runs over Python alone and through a front. In-process `_Handler` with a secret and a real mirror, front as a subprocess with `--upstream`. Nothing in the test weakens |
| `tests/front/test_wrote_nothing.py` | Extended: R3's reads add no rows, leave sibling hashes unchanged |

**Reported, never a gate:** moved-read p95 and statements beside C0; forwards per reason, which is where a too-short lease would show; position-poll cost to Python.

**Run from R1's suite:** the rows covering `/private/*`, the Grant row and `test_python_side.py`, because they touch the same paths.

## 9. Deploy and rollback

| Step | Effect |
|---|---|
| **First deploy** | One Python restart, ending live runs, with the new front. **Asked of the owner** (Turn #1025 item 4). Later front-only releases fall under the standing yes when no run is active |
| **New front, old Python** | Pull gets 404, so never `Held`: everything forwards |
| **Old front, new Python** | Push gets 404, so `down` after one `PUSH_TIMEOUT` and at most one fence: everything forwards |
| **Roll back the door** | Route table `worker` → `python`, in force within 2 s, no restart. Pushes continue harmlessly |
| **Roll back a front** | Previous binary, as the row above |
| **Roll back R3** | Prior launcher and tag, restarting Python. Ends live runs, owner's call |
| **`rollback-to-python.ps1`** | No secret, so no mirror |
| **Brain** | Rust writes nothing in any case |

Python's fallback is untouched: `_UNGATED_READS`, `_WORKER_READ_GATE` and the moved reads' paths and `Surface` methods all stay (`PLAN-r3`, section 5). The only Python changes are the mirror's push (`authority.py`, one new module), the two private routes (`_refused_private`, `web/__init__.py:6348`) and wiring in `serve` (`:7298`).
