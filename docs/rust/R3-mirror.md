# R3: the grant mirror and the Rust door for reads

`PLAN-r3`, section 4: revocation and authority. `adm-56082aa297b0` governs, with `adm-d613177f95fb` section 4 where it doesn't differ. Citations are at `d9281dc`. **Built on `r3-barrier`, and run on BRAIN-SEED: section 8 says on what.** The timings are design values, accepted from @Quill's review (Turn `ent-ff93ad615193`), except `CLAIM_WAIT`, `CLAIM_POLL` and `SEND_BOUND`, which are implementation constants set from measurement (`docs/rust/evidence/r3-constants.json`), not contract values. The owner's Turns `ent-35d399218b85` (the watch is allowed) and `ent-95415d070be6` (Python's restart semantics are preserved), and the owner's answers on form `opr-3b88b6d63c61`, govern section 4's barrier.

## 1. The one place the plan's wording can't hold, and what this adds

The plan says a failed revoke push "marks the mirror invalid until it re-pulls". A failed push means the front wasn't told, so nothing Python does at that moment can mark the front's copy. A front that is suspended, or too busy to answer within the timeout, wakes up still holding the dead grant, and agents' connections are waiting in its backlog (the same behaviour row K measured for Python).

**So this adds a lease and a fence.** A lease can't see a Python that has died, because its grants end with the process (`authority.py:9-11`) and nothing returns to fence, **so it also adds a boot check.** Python still mints, pushes every change in order and serves the pull. Generations still catch a gap, and an unknown token still forwards.

- **Lease:** the front answers from the mirror only while a confirmation from Python, *sent* within the last `LEASE`, says the mirror is current.
- **Fence:** when a push that removes or narrows a grant fails, the Python call doesn't return until any lease that could predate the change has run out.
- **Boot check:** immediately before admitting a read, and again before answering it, the front asks the kernel whether the Python process that gave it the table has ended (section 4).
- **Ownership barrier:** a process can give up the Brain before it has ended, so the boot check can't order a read against a replacement. Python holds a kernel lock for as long as it owns the Brain, and a replacement can't finish taking ownership while the front is answering, so the front's last check and the last byte it hands to the socket can't be separated by one (section 4).

**Other additions to the plan:** the position route, the keys and reduced fields of section 2, and so no push for a change the mirror doesn't hold (`delivered`, or a `revoke` that spent nothing).

**Alternatives rejected:**

| Alternative | Why not |
|---|---|
| Push again until it lands | An unbounded revoke, and a retry loop `AGENTS.md` rules out |
| Kill the front | Supervision, also ruled out |
| Check with Python on every read | Puts every read back behind the interpreter, which is what R3 exists to stop |

**The guarantees, which are what to attack:**

1. *Once a change that removes or narrows a grant has returned, no read the front admits afterwards is admitted on the old grant.* A read already admitted finishes, as on Python today (`adm-d613177f95fb`, section 4).
2. *No read is admitted on a grant of a Python process that has ended, and no answer is sent that was read after it ended.*
3. *No answer from the mirror passes its last check after its Python gave up ownership, and no answer that passed is still being handed to the socket when a replacement takes ownership: the whole of it has been handed over first, or the connection is aborted first.* A replacement of this build takes ownership by completing its claim, and a Python from before this build by taking the serve lock (section 4). The front's tail holds both off from before its last check until the answer has been handed over or aborted. This holds however long the old process object takes to be signalled, whatever the lease says, and with the front suspended anywhere. "Handed to the socket" is not "received by the client" (section 4, I20).

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
| **`scope` not a string (null included)** | Not mirrored, so it forwards. Rust matches scopes by name and has no answer of its own for any other shape. A minted grant whose `scope` becomes one is a `drop` |
| **`operations` not null or a list of strings** | Not mirrored, so it forwards. `permitted` uses `in`, which would mean something else on a string. A minted grant whose `operations` becomes one is a `drop` |

## 3. The protocol

**Python's state:** `boot_id` (random per process, 32 lowercase hex), `generation` (integer, up by one per mirrored change, starting at 0), `down` (bool, starts false) and `last_confirmed` (`perf_counter` when a pull, or a position saying `down` false, was last answered; starts as never). None of it exists without a boot secret: Python alone has `mirror = None` and behaves exactly as today. The one thing a Python without a secret may do is claim ownership, and only on a Brain a mirrored Python has served (section 4).

### Changes

Every mutator follows the same order. Lock order is `_changes`, then `_lock`, and the pull takes only `_lock`.

```
with _changes:                     # one change at a time, so pushes go in table order
    with _lock:
        change the table           # Python refuses this grant from here on
        if the mirrored view moved:
            generation += 1; t = perf_counter()
            deadline = last_confirmed + FENCE          # never later than t + FENCE
    if the view moved:
        push (generation, change), PUSH_TIMEOUT
        anything but a 200 {"ok": true}: failed = True; with _lock: down = True
if the change removed or narrowed, failed, and now < deadline: sleep until deadline   # holding no lock
```

**Why the deadline comes from `last_confirmed`:** only a confirmation answered before `t` can give a lease on a table without this change. One answered after `t` either shows the higher generation, so `behind`, or is a pull or position that already includes the change. The front's send time precedes Python's answer, so every such lease ends by `last_confirmed + LEASE`. If nothing has ever been confirmed, nothing is waited for.

| Mutator | Pushes | Fenced |
|---|---|---|
| `_grant` (`authority.py:75`), `grant_session` (`:108`) | `set`, unless not mirrored (section 2) | No. A token the front lacks forwards |
| `authorise_for` (`:35`) | Only when a minted grant's `scope` or `operations` changed. `set`, or `drop` if it can no longer be mirrored. `delivered` alone (`web/dispatch.py:1824`) pushes nothing | Yes |
| `revoke` (`:98`) | `drop`, only if a token was spent | Yes |
| `end_session` (`:148`) | `drop`, only if a grant ended | Yes |

**Every mirrored change is pushed once, before it returns, as the plan says, `down` or not.** Pushes aren't retried. `down` only makes positions tell the front to pull, which is the plan's "invalid until it re-pulls". It plays no part in the fence.

**What pushing during an outage costs:** up to one `PUSH_TIMEOUT` per mirrored change, held in `_changes`, so later changes wait behind it and don't reach `t` until then. A front answering 404 costs a round trip. Nothing listening costs the full 500 ms, on every mint and every revoke, for as long as it lasts. A front bound only to another address (below) is in that state for life.

### The three routes

The secret is required as for `/private/live`. Each private-port route answers 403 without it, and with no boot secret these paths mean what they always did.

| Route | Where | Body and answer |
|---|---|---|
| `POST /private/grants` | **Public port, the front's own.** Honoured only from a loopback peer with the secret, as `/private/stop` is (`front/connection.rs:305-310`). Anything else stays 404 | `{"schema":1,"boot_id","generation","key":<sha256 hex>,"grant":{…} or null}` → `{"ok":true}`. `null` is a `drop` |
| `GET /private/grants` | Private port, Python's | `{"schema":1,"boot_id","generation","corpus":<st.path>,"grants":{…}}`. Taken under `_lock`, clears `down`, sets `last_confirmed` |
| `GET /private/grants/position` | Private port, Python's | `{"schema":1,"boot_id","generation","down","pid":<os.getpid()>}`. Under `_lock`, reads no record, sets `last_confirmed` unless `down` |

**Push target:** always `http://127.0.0.1:<port of answers_at>`, so the secret never leaves loopback. A front bound only to another address refuses the connection, so `down` is set and everything forwards. That is safe, with no gain.

**Not `/private/live`:** its contract says it is never used for authority, and it polls only while a pulse is asked for.

**A malformed push discards before it answers.** Malformed means: over `BODY_LOOK`, not JSON, an unknown `schema`, a field missing or of the wrong type, `key` not 64 lowercase hex, or a `grant` that isn't null or an object section 2 would mirror. The front discards its table, and only then answers 400. Python takes that as a failed push, so it sets `down` and fences. A request refused for its peer or secret is a 404 and changes nothing.

**No digest.** The push had a `digest` field with nothing defined behind it, and it is removed. The plan doesn't ask for one. The push crosses loopback TCP with a framed body, and generations catch a lost change. A digest of the change would catch nothing else, and a digest of the table would need one canonical encoding across two languages and one more failure path, for a divergence nothing here can produce.

### The front's state

Pure, with no clock of its own, as `front/snapshot.rs`'s `State` is, so every rule can be tested at exact moments.

```
Empty                                        nothing to serve from
Locating { pending }                         asking position who Python is; pending = pushes that arrived meanwhile
Pulling { boot, watch, sent, pending }       one pull at a time, after the watch is open
Held { boot, watch, owner, generation, table, confirmed_sent, behind }
```

**Serve only if** `Held`, not `behind`, `now - confirmed_sent <= LEASE`, and `watch` has not ended. The state takes the answer to that last one as an input, read by the door at that moment (section 4). **Answer only if** the tail's checks pass as well (section 4), and those are inputs in the same way. `owner` is a read-only handle on the owner lock's file.

| Event | Effect |
|---|---|
| Position answered while `Locating`, known schema | Open a watch on its `pid`, then send the pull. If the watch can't be opened, `Empty`: nothing is served without one |
| Pull answered, known schema, `boot_id` = the position's | If the claim file says that boot and the owner lock's file opens, adopt, with `confirmed_sent` = the pull's send time, and replay `pending` of that boot above its generation; a gap pulls again. Otherwise close the watch, `Empty`: nothing is served for a boot that doesn't own this Brain |
| Pull answered, another `boot_id` | Close the watch and discard: it may be on the wrong process (section 4). The discard is a trigger |
| Position or pull refused, failed, or not whole within `POSITION_TIMEOUT` or `PULL_TIMEOUT` | Connection dropped, so no late answer can count. `Empty`, and `pending` goes with it, because any later pull includes those changes. Tried again at the next trigger below, not on a timer |
| Push, same boot, `generation == held + 1` | Apply. **Doesn't touch `confirmed_sent`** (see section 4, row 6) |
| Push, `generation <= held` | Already included. Ack |
| Push, `generation > held + 1`, or another boot | Discard the table and pull. Ack, because nothing is served until a table taken after this arrives |
| Push while `Empty`, `Locating` or `Pulling` | Keep in `pending`. Ack. A push that finds no pull in flight is itself a trigger |
| Push, malformed | Discard, then 400 (above). Never ack |
| Position, `generation == held`, not `down`, same boot | `confirmed_sent` = that poll's send time, `behind` cleared |
| Position, `generation > held`, or `down` | `behind`; pull |
| Position, `generation < held` | Ignored, no lease credit: the poll raced a push it hasn't seen. A real regression never earns credit again, so it ends in forwarding |
| Position, another boot, another `pid`, or unknown schema | Close the watch, discard; pull |
| Poll connection ends, or is reset | Discard (Python gone). This is the `Snapshots` connection-in-hand behaviour. It saves the next read a check and **nothing relies on it** |
| Poll not whole within `POSITION_TIMEOUT` | Connection dropped, no credit, and the next poll opens a new one. The lease keeps running out. A refused connect on Windows lands here, since it takes longer than the timeout |
| Poll non-200, unreadable | Nothing. The lease keeps running out |
| The door finds the watch ended | Close it, discard; pull. This read forwards |
| The tail finds another claim, the owner lock released, or the serve lock taken exclusive | Close the watch and the owner handle, discard; pull. This read forwards |
| The tail finds the claim busy, or can't take a clear answer from any of the three files | No change to the state. This read forwards |

**Pull triggers:** front start; a discard; a push that needs one; a presented grant while not `Held`. Each starts at `Locating`. One at a time, and nothing retries on a timer.

**Polling:** every `POSITION_EVERY`, one at a time, using the same in-hand connection as `Snapshots`, whenever `Held` with at least one grant or while pulling. Agents read at intervals longer than the 5 s the pulse uses, so asking on demand would forward nearly every read of a lone agent. Polling has no supervising role, and it stops when no grants are held.

**A Python restart with an empty mirror:** no poll is running, but Python starts with `down` false, so its first mint pushes with a new `boot_id`, which discards and pulls.

### Timings

| Name | Value | Why |
|---|---|---|
| `PUSH_TIMEOUT` | 500 ms | The whole push. Windows takes 2-2.5 s to refuse a loopback connect (`contracts/live-snapshot.md`), so a dead front costs this, not that |
| `POSITION_EVERY` | 500 ms | As `/private/live` |
| `POSITION_TIMEOUT` | 250 ms | One position, connect included. Its only cost when missed is one poll's credit: `LEASE` survives several in a row |
| `PULL_TIMEOUT` | 500 ms | One pull, connect included. A miss means forwarding until the next trigger |
| `LEASE` | 3 s | Above C0's worst pulse p95, 565 ms (M), so a loaded Python doesn't normally push reads back to it. It only sets the worst-case fence |
| `FENCE` | `LEASE` + 100 ms | Python's `perf_counter` and Rust's `Instant` read the same clock on Windows (QPC) and Linux (`CLOCK_MONOTONIC`). The margin is for scheduling, not drift |
| `CLAIM_WAIT` | 30 s, **measured below** | How long a starting Python waits for the claim's two locks, then refuses (section 4). Has to exceed `SEND_BOUND`, or one stalled client could refuse a start. Safety assumes nothing about it: running out only refuses the start |
| `CLAIM_POLL` | 10 ms, **measured below** | How often that wait tries again, as `LockFileEx` and `flock` are used here without blocking. A trade between load and how quickly a start proceeds |
| `SEND_BOUND` | 5 s, **measured below** | How long a tail that has had bytes accepted may hold its locks for the rest, then aborts the connection (section 4). Safety assumes nothing about it: it limits how long a stalled client can hold up a start, and sets which slow clients get aborted |

The first six are design values, not measurements. **The last three aren't contract values:** nothing establishes them, Windows gives no bound on a lock's release after termination, and @Quill rejected the first two as design values. A shortened value is used in tests. Only the relation `CLAIM_WAIT` > `SEND_BOUND` is part of the design, and `tests/front/test_mirror_constants.py` holds to it.

**What the build measured,** on this machine, on BRAIN-SEED, on a debug build of the front, so they say how much room there is and no more. `tests/front/test_mirror_constants.py` writes `docs/rust/evidence/r3-constants.json`:

| Constant | Measured | So |
|---|---|---|
| `CLAIM_POLL` | A try costs about 2 µs. A claim behind a 20 ms tail got the lock a median 1.3 ms past its release at 10 ms, 1.7 ms at 1 ms, and 31 ms at 50 ms | 10 ms stays: going lower gains nothing measurable, and going higher costs a start real time |
| `CLAIM_WAIT` | A claim after a real kill waited at most 0.4 ms for the old owner's locks. Under 20 rounds of the load test, the longest wait was 5.0 s, which was the suspended front that test makes on purpose | 30 s stays. Nothing here came near it, and it only limits how long a start waits on a front that is stopped |
| `SEND_BOUND` | A reading client held a tail for a median 5 ms for a 32 MiB answer. A client taking 64 KiB per ms got all of an 8 MiB answer and was never aborted | 5 s stays. **On Windows a non-blocking send takes the whole of one write if the send buffer isn't already full,** so the bound is rarely reached there at all: a stalled client's answer is accepted by the kernel in one write, and it is I20's case, not I21's |

**That last row changes what the tail costs on Windows, not what it guarantees.** "Handed to the socket" comes sooner than this document assumed, so I18's wait and I21's abort need a send buffer already full. The tests offer writes piecemeal through `tail-probe` to reach them.

**Worst case for a revoke, by design:** returns by the absolute deadline `t` + 3.1 s. `PUSH_TIMEOUT` isn't added, because it runs inside that time. A change whose `last_confirmed` is older than `FENCE` returns as soon as its push fails, at most `t` + 500 ms, so once positions have stopped, only the changes in the first 3.1 s wait for a deadline. Time spent queueing behind `_changes` comes before `t` (section 3). A successful push adds one loopback round trip. None of this has been measured. The build reports the fence times it observes (section 8).

## 4. Revoke: the exact order, and each failure

`t` is when the table changed. Python refuses the grant from `t`. Between `t` and the revoke's return, a Rust read may still pass, and that is before the revoke happened as far as its caller can tell.

| # | What happens | Why the guarantee holds | Revoke returns |
|---|---|---|---|
| 1 | Push is acked | The ack means applied, or that nothing will be served until a table including it (section 3) | About `t` + one round trip |
| 2 | Front dead | Nobody to admit anything. If a new front starts, its pull is after `t` | By `t` + `FENCE` |
| 3 | Front suspended or stalled, push times out | A position answered before `t` gives a lease ending by `last_confirmed` + `LEASE`. Any answered after `t` shows a higher generation, so `behind` | By `t` + `FENCE` |
| 4 | Push reaches the front, ack lost | Applied, and Python is more cautious than it needed to be. `down` makes the next position pull | By `t` + `FENCE` |
| 5 | Later revoke during an outage | Pushed again. If that fails, its own deadline covers every confirmation before its own `t`, whatever set or cleared `down` meanwhile. **Measuring from the failure that set `down`, as this document first did, is wrong:** for a first failure on a change at `t1`, a push applied with its ack lost lets a position at up to `t1` + 500 ms confirm, so a stalled front holds a lease to `t1` + 3.5 s, past `t1` + `FENCE` | By its own `t` + `FENCE`, and at once when `last_confirmed` is older than `FENCE` |
| 6 | Timed-out push arrives late, after a later change | **Why a push never renews the lease:** this late arrival would otherwise extend the lease past the later change's fence. It either applies or is ignored, with no lease credit | Already returned |
| 7 | Pull in flight when the push arrives | The answer may hold the grant. The push waits in `pending` and is replayed on adoption, and only then can anything be served | About `t` + one round trip |
| 8 | Pull answered before `t`, adopted after | As row 7 if the push arrived. Otherwise `confirmed_sent` is before `t`, so as row 3 | By row |
| 9 | Pull clears `down`, then a failing push sets it again | `down` stays set with the table already current. The next position pulls again and clears it. Forwards meanwhile | By `t` + `FENCE` |
| 10 | Python killed | Every grant is dead. The ownership barrier and the boot check below find that at the door, with or without the poll connection's end | Nothing returns |
| 11 | Python suspended | No confirmation, so the lease runs out within `LEASE`. Reads forward and wait, as they would on Python | Nothing returns while suspended |

**Fences and write transactions:** closed by @Quill's reading of the source at `d9281dc`, which is a reading and not a test result. All seven production mutation sites are outside a Brain write transaction: `_grant` (`core/service.py:1266`), `revoke` (`core/service.py:1322`, `:1390`), `authorise_for` (`web/dispatch.py:1683`, `:1824`), `end_session` (`web/__init__.py:2942`) and `grant_session` (`web/__init__.py:2985`). Durable acts beside them open their own `Store.write()` after the authority call returns. So a fence can occupy an HTTP or dispatch thread for up to 3.1 s, but doesn't hold SQLite's writer lock.

### The boot check: when Python dies

Grants end with the Python process, and no mutator returns to fence that. A lease alone would keep them alive for up to `LEASE`, and the poll connection's end is an event the front learns of only when a task of its own runs. Neither can order a read after the death. So the door asks the kernel directly. This settles guarantee 2. It doesn't settle guarantee 3, which is the next heading's.

**The watch.** A handle on the Python process, opened by the front and held for that boot: `OpenProcess(PROCESS_SYNCHRONIZE)` on Windows, `pidfd_open` on Linux 5.3 or later. Anywhere else, or if opening fails, there is no watch, so nothing is `Held` and everything forwards. The pid is one Python reports of itself, so a venv's `python.exe` stub isn't mistaken for the interpreter.

**The check.** `WaitForSingleObject(handle, 0)`, or `poll` with timeout 0 on the pidfd. It doesn't block, and it depends on nothing the front has run or scheduled: the kernel's answer changes when the process ends, whether or not the front is running.

**Why the watch is on the right process, though pids are reused.** The front opens the watch on the `pid` from a position saying boot `B`, and only then sends the pull, which it adopts only if the answer also says `B`. `B` was running when it reported that pid, and still running when it answered a pull sent after the watch was opened, so it held that pid throughout and the watch is on `B`. Any other answer closes the watch. Once open, the handle stops the pid being reused.

**When a process has "ended".** The moment its process object is signalled. Microsoft's order for termination is threads marked, resources freed, kernel objects closed, code removed, exit code set, process object signalled ("Terminating a Process", Windows docs). On Linux, a pidfd reads as ended once the last thread has exited. This order is documented, and not measured here. **So the old process gives up the private port and `.mentis.serve.lock` before it has "ended", with no stated bound between the two.** This document used to say a replacement couldn't answer in that time, which @Quill showed wrong and which isn't relied on any more. The barrier below doesn't depend on that signal at all.

**Where the door checks.** Twice, each the last thing before its step: before admitting a read (section 5's mirror row), and in the tail, after the read and before any byte of the answer. An ended watch at the second check drops the answer and forwards the request with its bytes in hand. `mentis_ops::run` returns whole answers and a read has no effect, so nothing has been said and nothing is done twice.

**Against the adverse ordering, the front suspended throughout.** `B` is Python's boot before the restart, `B'` after.

| Order of events | What the door sees | Result |
|---|---|---|
| Lease valid, front suspended, `B` killed, `B'` starts, front resumes, a queued read runs before any monitor task or push from `B'` | First check: ended, because the kernel signalled it while the front slept | Forwarded: `B'`'s 403, or R1's 503 if `B'` isn't up |
| As above, not suspended: `B` killed, the read runs before the monitor task | First check: ended | Forwarded |
| Check passes, then `B` dies, front suspended there, `B'` writes, front resumes and reads | Second check: ended | Answer dropped, forwarded. The answer never reflects `B'`'s writes |
| Position says `B`, `B` dies, its pid is reused, the watch opens on the new process | Pull answers `B'`, or fails | Watch closed, never `Held` |
| Pull answered by `B`, `B` dies before adoption | First check: ended | Forwarded |

The orderings where the last check has passed, and where `B` is dying but not yet signalled, are the barrier's. They are in its table below.

**What the boot check assumes.**

- The documented termination order, only for the claim that a signalled process has closed its handles and run its last thread.
- Python and the front share one machine and one pid namespace. `--upstream`'s loopback rule and the launcher give that. A Linux setup with separate pid namespaces would defeat it, and `compose.yaml` runs no front.
- A process ending is what ends the table. `_State.agents` is assigned once (`web/__init__.py:96`), and nothing in `mentis/` calls `os.exec*`, which would keep a Linux pid.

**Cost:** two non-blocking syscalls per served read and one handle per boot, with no thread, timer or polling added. The `unsafe` calls are of the kind `mentis-launch.rs:1412-1418` already makes, with `Win32_System_Threading` already a feature. The position first adds up to 250 ms to a pull. Not measured: it is reported with moved-read p95.

**This isn't supervision.** The front never signals, restarts or reports on Python, and the check's only effect is that a read forwards. `contracts/launcher.md` holds the exception, in the terms of Turn `ent-35d399218b85`: solely to validate the lifetime of mirrored authorization state.

### The ownership barrier: when Python gives up the Brain

**What the owner decided (Turn `ent-95415d070be6`, on form `opr-83d578a2d05b`).** No mirrored success after a replacement can take ownership if it would reject the old token, including before the old process object is signalled. The decision's stated consequence is that the old token gets "the new Python's 403 (or 503), never a mirrored 200", so this covers a Brain that has been given up with **no** replacement started yet, as well as one that has been taken.

**The owner's two rulings on where that line falls (form `opr-3b88b6d63c61`).**

- **Claim completion is the point of ownership** ("Yes; claim completion controls", `ent-eb01fe85d419`). So an old-token answer whose checks passed may still go after `B` has released its locks, while the front's shared claim lock is what stops a replacement completing its claim (I6).
- **A complete success goes first** ("No; complete success first", `ent-6ed70c7fa2e5`). Accepting the first bytes commits nothing: the rest of a mirrored success may not be sent after a replacement takes ownership (I18). The tail below holds until the whole answer has been handed to the socket, or aborts the connection.

**Why a check alone can't do it.** Whatever the front checks, a suspension can fall between that check and the send, and nothing bounds it. A wait on a replacement's start can't close that either: the front may stay suspended past any wait. So the last check and the last byte handed over have to sit inside something a replacement must get past, and that takes a lock. **For a Python from before this build, that has to be the only lock such a Python asks for at start,** `.mentis.serve.lock`: it knows nothing of any newer one.

**Alternatives rejected.** A replacement that waits out `FENCE` before binding would cost up to 3.1 s at each start, lean on the shared clock, and still leave a front suspended between its check and its send. A claim file with no owner lock has no delay, but serves a Brain given up with no replacement started. Comparing `.mentis.serve.json`'s pid with the watch, or stopping the front first by instruction, leaves a front suspended between that check and its send while an older Python binds. An ordering of handles at Python's exit isn't documented, so nothing can arrange for the owner lock to go before the serve lock.

**Three new files beside the serve lock, and a change to how it is held.** All go in `brainlock.LOCK_FILES`, so none is backed up or moved by a restore. They are in the Brain directory, not the run directory, because a replacement started by hand, on any port, takes the same Brain and has no run directory. Separate files, not ranges of one, for `brainlock`'s reason: `flock` locks a whole file.

| File | Who holds it, how | What it says |
|---|---|---|
| `.mentis.serve.lock` | **A Python of this build on a mirrored Brain: shared, for its life, no longer exclusive.** The front's tail: shared, for its span. A Python from before this build, and a Python alone on a Brain never mirrored: exclusive, for life, as today | Held exclusive, it says somebody who doesn't know the claim has the Brain |
| `.mentis.sole.lock` | A Python of this build on a mirrored Brain, exclusive, for its life | What the serve lock's exclusivity did among such Pythons: one server per Brain, refused at once. Empty |
| `.mentis.owner.lock` | The owning Python, exclusive, for its life | Its being held is the fact. Empty |
| `.mentis.claim` | A claiming Python, exclusive, for moments. The front's tail, shared, for its span | The owner's `boot_id`, 32 bytes |

All use `brainlock`'s lock: `LockFileEx` on one byte at offset 0, or `flock`, never blocking. A lock dies with its process, and **a process that dies holding one can't have the replacement proceed until the kernel has let go of it,** so a slow release only makes the replacement wait.

**Why the serve lock can stop being exclusive.** Shared holders exclude an exclusive taker, so a Python from before this build still refuses beside a running one, in its usual words, as does `exchange/apply.py:88`, the only other taker. A Python of this build refuses beside an exclusive holder. A second Python of this build is refused at `.mentis.sole.lock` with the same words (`tests/front/test_locks.py:81`), before it has touched the claim. So every pair that refuses today still refuses.

**Who may hold what.** Only Python writes any of these files. The front opens them read-only, never creating them, so Rust still writes nothing to the Brain: a shared lock on a handle opened for reading is enough on both systems. A file missing, or failing to open, means nothing is served. The record opener still doesn't touch the serve lock (`crates/mentis-record/src/lib.rs:220`, `open_refusals.rs:133`); the tail is a separate use, and `contracts/record.md`'s "never touch" has to name it if this design is accepted.

**A Python's start.** In `brainlock.serve` (`web/__init__.py:7306`), inside the `try` that gives it back on refusal (`:7308`), and so before the store opens (`:7311`) and before the port is bound (`:7347`). `.mentis.serve.json` is written, as it is now, only by a Python that got past the refusals. In `mentis/` at `d9281dc`, that `serve` is the only caller of `brainlock.serve` and `:7347` the only place `_Server` is made, so every server on a Brain comes through here.

```
no boot secret and no .mentis.claim: exclusive on serve lock; stop here   # Python alone, never mirrored: as today
shared on .mentis.serve.lock      # refused at once: something holds it exclusive
exclusive on .mentis.sole.lock    # refused at once: a second server, which touches nothing below
exclusive on .mentis.claim        # up to CLAIM_WAIT. From here every tail forwards
exclusive on .mentis.owner.lock   # the same deadline. From here the last owner has let go
write all 32 bytes of boot_id at offset 0 of .mentis.claim, completed at the OS   # the moment ownership is taken
release .mentis.claim; keep the other three for life
```

**In that order, for reasons.** Claiming after the refusals, so a Python that's refused changes nothing a running one depends on. The claim's lock before the owner's, so no tail can find the owner lock held by a replacement with the old boot's claim still in the file. The file's write after the owner lock, so a dying owner's handle has gone before the file changes. An orderly stop gives up the owner lock, then `.mentis.sole.lock`, then the serve lock (`:7362-7363`). The wait is on a lock, and is not a retried act: nothing failed.

**The claim's write has to be complete at the OS before the exclusive lock is released.** A buffered `write()` that has returned isn't a completed `WriteFile`, and a front that read the old boot beside a new owner's lock would serve on stale authority. So:

- Unbuffered: an `os.open` descriptor and `os.write`, repeated until all 32 bytes are written, or a buffered file with an explicit `flush()` whose completion is checked. Anything short of 32 bytes refuses the start, with the claim's lock released only by that refusal (I10).
- **`brainlock._take` can't be reused as it stands:** it opens `a+b` (`brainlock.py:146`), which buffers and appends, so nothing written through it lands at offset 0.
- **Through the handle holding the lock.** On Windows a second handle in the same process can't access an exclusively locked range.
- The tail reads and compares all 32 bytes, and a file of any other length isn't this boot.
- No disk flush is asked for: durability isn't the point, because a power cut ends the front too. Microsoft documents that a synchronous `WriteFile` has completed when it returns and that file data is shared between handles. Section 8 tests the real cross-process read.

**Past `CLAIM_WAIT`:** `BrainBusy`, so `main` exits 3 in words, as for a second server (`:7402-7405`), the locks given back, nothing bound and the claim's bytes unchanged, because the write comes last: *"a front on this Brain is stopped in the middle of an answer, or the last server hasn't finished dying; resume or end it and start again"*. Safety assumes nothing about this limit. Without it, a Python would wait forever on a front that nothing is going to resume.

**The tail: the door's last step, for every answer it gives from the mirror, 403s included.**

```
wait for the client's socket to take bytes              # holding nothing
open .mentis.claim read-only; try shared                # busy, or failed: forward
open .mentis.serve.lock read-only; try shared           # held exclusive: release; discard; forward. Failed: release; forward
read the claim's 32 bytes. Not this boot: discard; forward
try shared on the held owner handle                     # taken: release it; discard; forward
                                                        # any answer but "held exclusive": forward
watch ended: discard; forward
try_write the answer without blocking                   # would block with nothing accepted: release; start this block again
deadline = now + SEND_BOUND                             # from the first accepted byte: whole, or aborted
until the whole answer has been accepted:
    past the deadline: abort the connection             # SO_LINGER 0, then close: a reset, dropping what the kernel holds
    wait for the socket to take bytes, up to the deadline; try_write the rest
release, close                                          # after the last byte is accepted, or after the abort
```

**Up to the first accepted byte nothing awaits, and nothing depends on a client:** a client not draining waits in the first line, holding nothing. After it, the tail awaits only the client's socket, only until the deadline, with both shared locks held, and a cancelled task or a panic drops them with their handles. A read isn't run under it, because a read that finishes before a passing check is ordered before the claim, as the check is. Every forward releases first: a forward waits on Python, and that Python could be the one waiting on this lock. A failed write means the client has gone, and it releases as well.

**Why an abort leaves no complete success.** Every answer from the mirror is framed by `Content-Length`, because `mentis_ops::run` returns whole answers. The abort only happens with bytes the socket hasn't accepted, so the client can't get them all: what it reads ends early, in a reset or short of the length. It may have seen the status line and part of the body. It can't see a whole answer, and the worker's transport already says of such a reply that the result is unknown (`contracts/launcher.md`, "The worker's transport"). The agent may ask again, and that read goes through a new tail.

**"Handed to the socket" is not "received by the client".** Release follows the last byte the kernel accepted. Those bytes may still be in the front's send buffer, on the wire or in the client's receive buffer, so a client that reads slowly can read the end of a complete success after a replacement has taken ownership (I20). No server can see what a client has read: HTTP has no acknowledgement, and a TCP ack only says the client's kernel has the bytes. These bytes were all accepted before any replacement could own the Brain, and nothing is sent after it. That is what this boundary guarantees, and all it guarantees.

**Why it holds.** Let `R` be when `B`'s owner lock is released. Let `X` be when `B'` takes `.mentis.claim` exclusive and `C` when it writes the claim, so `X < C`, and `R < C` because `B'` holds the owner lock by then. `X` may come before `R`, when a kill releases `.mentis.sole.lock` first. For a Python from before this build, `L`, let `E` be when it takes `.mentis.serve.lock` exclusive. It serves nothing before `E`.

- A tail holds `.mentis.claim` shared from before its checks until the whole answer is accepted or aborted, so the whole of it lies before `X` or after `B'` lets the lock go. After that the file says `B'`, so it doesn't pass. **So every tail that passes, last accepted byte included, is before `X`, and so before `C`.**
- A tail holds `.mentis.serve.lock` shared for the same span. **So every tail that passes lies wholly before `E`, or after `L` has given the lock up.** One that tries while `L` holds it finds it taken, so it forwards. A tail in progress makes `L` refuse.
- A passing tail found the owner lock held. Before `X` no replacement of this build can hold it, so the holder was `B` and its check was before `R`.
- A tail whose check comes after `R` either finds the lock not held, or finds the claim busy or another boot's, so it forwards. That is the "no replacement yet" case too, and it needs nothing from `B'` or from the signal.
- `C` and `E` don't happen during a passing tail, however long the front is suspended in it. **This is the one case where a suspended front holds up a Python.** It answers the case nothing else can.
- Nothing above reads a clock, or depends on the lease, the watch, the poll connection, a push or a task of the front's. `SEND_BOUND` only ends a hold, and the lease only helps `B'`'s wait end: once it runs out, nothing new is admitted to reach a tail.

**What remains under the owner's first ruling.** A front stopped between its checks and the end of its send (I6, I19), or `B` released in those moments, sends that one answer after `R`. No replacement can have taken ownership by then, or until it has gone.

**Against the adverse orderings of the interval.** `B` is the old boot, `B'` its replacement. "Released" means `B`'s kernel objects have closed; "not signalled" means the watch still reads as running. The lease is valid throughout unless it says otherwise, because that's the case the lease can't help.

| # | Order of events | What decides it | Outcome |
|---|---|---|---|
| I1 | `B` released, not signalled, no `B'` yet, read arrives | Tail: owner lock not held | Forwarded: R1's 503 |
| I2 | `B` released, not signalled, `B'` has claimed but not bound, read arrives | Tail: claim says `B'` | Forwarded: R1's 503 |
| I3 | `B` released, not signalled, `B'` serving, read with the old token | Tail: claim says `B'` | Forwarded: `B'`'s 403 |
| I4 | Front suspended with a read queued; `B` released, not signalled; `B'` serving; front resumes, and the read runs before any task, poll or push | First tail of that read: claim says `B'`. Nothing had to run first | Forwarded: `B'`'s 403 |
| I5 | Front suspended before its tail, then as I1 | Tail: owner lock not held | Forwarded: R1's 503 |
| I6 | Front suspended in its tail after the checks, before its first write; `B` released; `B'` starts | `B'` can't take the claim's lock, so doesn't bind. Allowed by the owner's first ruling | When resumed, the whole answer goes, then `B'` claims. No `B'` could answer before it. Not resumed within `CLAIM_WAIT`: `B'` exits 3, no ownership taken |
| I7 | Tail has the claim's lock, `B'` is waiting for it, front not suspended | A tail holds it for its checks and its send, a few syscalls if the socket takes the whole answer | The answer goes, `B'` claims on its next try. Up to `SEND_BOUND` if the client stalls. Not measured |
| I8 | `B'` holds the claim's lock, waiting on `B`'s owner lock, read arrives | Tail: claim busy | Forwarded. No state change, so `B` is still `Held` if `B'` never finishes |
| I9 | `B'` has both locks, dies before the write | Nothing was claimed and `B'` answered nobody. Its locks die with it, and `B` had let go of the owner lock before `B'` took it | As I1: owner lock not held, forwarded |
| I10 | `B'` dies part way through the write | The file is neither `B` nor anyone. `B'` answered nobody | Forwarded until a later Python claims |
| I11 | `B` alive; a second Python of this build started by mistake | It refuses at `.mentis.sole.lock`, before the claim. It held the serve lock shared for a moment, which changes nothing | `B` undisturbed and still served |
| I12 | `B` still answering positions after it released (a thread in an orderly stop) | Owner lock not held, or claim says `B'`. A late lease earns nothing | Forwarded |
| I13 | Pull answered by `B`, adoption after `C` | Adoption reads the claim: `B'` | Never `Held` on `B` |
| I14 | Kernel holds up `B`'s handles, so it isn't released, not signalled | Owner lock held, so no `B'` can have claimed | Served while `B`'s confirmations last, up to `LEASE`. Nobody can yet take ownership, so this is row 11, as before |
| I15 | Client not draining its socket when `B` is released, nothing of this answer accepted | Tail's first line holds nothing, and the block's checks run when it can take bytes | Forwarded, as I1 |
| I16 | `B'` started by hand, no secret, any port, this build | The claim file exists, so it claims | Forwarded. A mirror needs a position from a Python with the secret, so nothing is `Held` again |
| I17a | `B` killed: its serve lock gone, its owner lock still held, not signalled. `L`, a build before this one, takes the serve lock | Tail: serve lock held exclusive. The stale claim, the old owner lock and the unsignalled watch don't get a say | Forwarded: `L`'s 403 once it is bound, R1's 503 before. No order of steps is needed |
| I17b | Front suspended in its tail after the checks; `B` killed; `L` starts | `L` can't take the serve lock while the tail holds it shared, and refuses without waiting: exit 3, in today's words | When resumed, the whole answer goes, then `L` can be started again. The same case as I6, with a refusal in place of a wait |
| I17c | Front suspended before its tail; `B` killed; `L` serving; front resumes | First tail of that read: serve lock held exclusive | Forwarded |
| I17d | As I17a, then `L` stops or dies while `B`'s owner lock is still held | Tail passes, as nothing holds the serve lock exclusive | Answered. No Python owns the Brain, and none can while the tail holds. As I14 |
| I17e | `L` running, then a Python of this build starts | Refused at its shared try on the serve lock | `L` undisturbed. A pull finds an old Python's 404, so nothing is `Held` |
| I17f | A release before `brainlock` existed (`brainlock.py:23-26`: it takes no lock) | **Not covered, and no lock can cover it.** It asks for nothing a front could hold, and it can already start beside any server | Not a rollback target: `r1` and `d9281dc` both take the serve lock exclusive, as does what was lifted from Mark IV (`529f441`) |
| I18 | Tail passes, first bytes accepted, rest not yet; `B` released; `B'` waiting; client drains within `SEND_BOUND` | The owner's second ruling: the tail holds until the last byte is accepted | The whole answer is handed over, then the tail releases, then `B'` claims. Nothing is sent after `C` |
| I19 | As I18, with the front suspended part way through the send | The tail still holds, and the deadline is checked before each write | Resumed before the deadline: as I18. After it: aborted, then released. Not resumed within `CLAIM_WAIT`: `B'` exits 3 |
| I20 | Whole answer accepted by the socket, tail released, `B'` claims, client hasn't read it yet | **Stated, not closed:** "handed to the socket" isn't "received by the client" | The client can read a complete success after `C`. Every byte was accepted before `X` |
| I21 | As I18, with a client that doesn't drain within `SEND_BOUND` | The abort | Connection reset, then release, then `B'` claims. The client never gets a complete success |

**What this leaves assumed, and unverified until the build runs it.**

- Shared and exclusive `LockFileEx` and `flock` exclude one another across processes, and die with the process. `brainlock` and `crates/mentis-record/tests/open_refusals.rs` rely on this for the other locks, and neither has run against these files.
- A completed write through one handle is visible to a read through another on the same machine. Microsoft documents this, and it hasn't been run here. Section 8 tests it.
- A reset, with `SO_LINGER` 0, drops what the kernel still holds to send, and a client reading after it never gets the bytes the socket didn't accept. Section 8 tests this too.
- The Brain is on a local disk (`brainlock.py:94-96`'s known limit). On NFS or CIFS the locks may not behave so, and neither would the serve lock.
- Every Python that can serve this Brain takes the serve lock (I17f). `r1`, `d9281dc` and the Mark IV package lifted at `529f441` are read to do so. No released Mark IV binary has been run against this.
- Mark IV ignores three more dotfiles in a Brain directory. Not read in Mark IV's source here.
- A real kill's release, with kernel objects closed and the object not yet signalled, can't be produced on demand. Section 8 tests that state with a process that has given up its port and locks and stays alive, which is the same state to the front, and tests kills separately.
- Nothing of this has been built or run. All timings here are design values.

**Costs, all design estimates, none measured:**

| Cost | Size |
|---|---|
| Per answer from the mirror | Two opens, two shared locks, read, one failed lock attempt, unlocks and closes: about ten syscalls beside the two for the watch. Reported with moved-read p95 (section 8). An on-access scanner may slow the opens |
| **`SEND_BOUND`, on every answer, restart or not** | A client that hasn't taken a large answer within the bound gets a reset, with no replacement anywhere near. **Python and R1's front wait on a stalled client without limit** (`front/connection.rs:415`), so this is a behaviour Python alone doesn't have, which the owner's second ruling makes necessary. A smaller bound aborts more slow clients, and a larger one holds a start up longer. A client on loopback that keeps reading should never meet it. Aborts are counted and reported (section 8) |
| Python's start, ordinarily | Five lock calls, a write. **No startup delay:** nothing waits out a lease |
| Python's start, with a tail in progress or `B` still closing | Up to `CLAIM_WAIT`. With a stalled client, up to `SEND_BOUND`. Otherwise expected to be one `CLAIM_POLL` or none. None of these is measured |
| **New reasons for a start to refuse** | A front stopped in the tail, a tail that `CLAIM_WAIT` didn't outlast, or `B`'s handles not closing within it. Exit 3, in words. The owner resumes or ends the front and starts again. No read has been wrong in any of this. A stopped front elsewhere than the tail costs nothing |
| **Not addressed: file access** | Opening or locking any of the files can fail for its own reasons: permissions, an on-access scanner, a disk. On the front that forwards. On a starting Python it refuses the start in words. Nothing here retries it or tells it apart further |
| **Not addressed: lock starvation** | A starting Python's exclusive try holds no place in any queue, so tails whose shared holds keep overlapping can keep it from succeeding until `CLAIM_WAIT` runs out, and then it exits 3. Holding through the whole send makes this likelier than a first-write hold would. New tails stop passing once `B` has released, but they still take the lock for a moment before forwarding. There is no writer priority. The load test reports how long a claim waited (section 8) |
| A Python from before this build, under a running front | **It can refuse where it wouldn't have:** a start that meets a tail exits 3 at once, in words that name the last server, not the front. Started again, it succeeds unless a tail is in progress again or the front is stopped in one. Stopping the front first avoids this |
| A forward instead of an answer | Between `R` and `B'` serving, every moved read forwards and gets R1's 503, as every forwarded route already does. Python alone would refuse the connection there |
| Python alone | Nothing, on a Brain never mirrored. After a rollback, the same lock calls and a write at each start, with nobody to wait for |

**The watch's place now.** On a local disk the barrier reaches every case the watch did, and sooner, since a signalled process has released its locks. It stays because @Quill found it sound and the owner allowed it, and because it is a second fact from the kernel that doesn't depend on a file: guarantee 2 is still stated in its terms. Removing it later would be a separate decision, and nothing here relies on that.

### What the earlier design's guarantees become

| Mechanism or claim, as @Quill reviewed it (Turn `ent-bbfe4fa44abe`) | Now |
|---|---|
| Boot check defeats suspension and delayed monitor tasks, once signalled | Kept as written. Guarantee 2 |
| "An unsignalled dying process still holds the port and lock" (old section 4) | **Withdrawn: it contradicted the termination order.** Replaced by guarantee 3 |
| Served until `B` is signalled, within the lease | **Withdrawn for a released `B`** (I1 to I5). Stays only where `B` still holds its locks (I14) |
| PID reuse: position, then open watch, then pull, then matching `boot_id` | Kept, unchanged. Adoption now also reads the claim |
| Second check, after the read and before the first byte; drop and forward | Kept, now inside the tail and under its locks |
| "Second check passes, then `B` dies before the bytes go out: sent" | Kept for a suspension or death inside the tail, because the tail's locks mean no replacement can have taken ownership by the time the last byte is accepted (I6, I17b, I19) |
| Windows and Linux arrangement, one machine, one namespace | Kept |
| Revised fence: `last_confirmed` + `FENCE`, under the mutation lock, for ack-lost, late-position, stalled-front, later-mutation and late-push orders | **Kept, unchanged and independent:** a revoke isn't a restart. Section 3 and section 4's rows 1 to 9 stand as they were |
| Push while `down`: safe, with its liveness cost above two changes per second | Kept, unchanged, as a stated cost (section 3) |
| Lease | Kept for guarantee 1 and for row 11. Guarantee 3 doesn't use it |
| Pull and position timeouts, `digest` removal, malformed-push discard, `key`, non-string `scope`, `operations` | Kept, unchanged |

## 5. The door

`POST /api/worker` gets a rule owned by Rust. Every case below that isn't "answer" sends the request on byte for byte, using `send_on`'s existing handling of bytes already in hand (`front/connection.rs:352`).

| Step, in Python's order | Forward when |
|---|---|
| Framing | A query, `Expect`, `Transfer-Encoding`, no well-formed `Content-Length`, or over `BODY_LOOK` (1 MiB, not read at all). Otherwise read the whole body before deciding |
| Host, client header (`web/__init__.py:6662`, `:6691`) | Host refused, or no grant presented. Python words those |
| `Content-Type` (`:6700`) | Not `application/json` |
| JSON (`:6705`) | `serde_json` refuses it. It accepts strictly less than `json.loads` (NaN, lone surrogates, other encodings), and its last duplicate key wins, as Python's does. Not an object, too |
| `op` | Not a string naming a moved read |
| `args` | Present and not an object |
| Corpus (`:3035`) | `corpus` is present, non-empty and not exactly the pull's `corpus`. Python resolves paths and words the refusal |
| **Mirror, checked last before reading** | Not servable (the watch's check is the last of it, section 4), token not held, transient scope, or a scope or `op` whose `repr` isn't printable ASCII |
| Held grant for another corpus (`:3045`) | **Answer** 403 in Python's wording |
| `permitted` refuses (`:3050`) | **Answer** 403 in Python's wording. **Unreachable today:** every scope holds all six moved reads, which the matrix shows. It exists so a future shape is refused the same, never served |
| Permitted | `mentis_ops::run`, class `Agent`. `NotOwned` forwards, including any `resolve` kind not yet moved. `Busy` and `Record` follow `contracts/ops.md` |
| **Before the first byte of the answer** | Any of the tail's checks refuses: the claim busy or another boot's, the serve lock held exclusive, the owner lock not held, or the watch ended (section 4). Past the first accepted byte nothing forwards: the answer is whole or the connection is aborted |

Every **Answer** above goes out through the tail, the two 403s included: an old grant's refusal can differ from a replacement's words.

**What Rust checks is never carried into Python.** A forwarded request is checked again in full, and a grant on any other route still gets that door's 403.

## 6. The route table, and the permission matrix

```json
{"id": "worker", "method": "POST", "path": "/api/worker", "owner": "rust"}
```

`HANDLERS` and `ROUTES` each gain `worker`, and `Door` gains `Worker`. `connection.rs`'s "only a GET is ever answered" changes for this one route. Additions are line by line, so R2's merge is separate. `routes.md` and `contracts/launcher.md` gain the routes above. `launcher.md` already holds the watch's exception and the claim (its section "R3: the watch and the claim"). `/private/*` is still decided before the table.

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
| Mirror `Empty`, `Locating`, `Pulling`, `behind`, or past its lease | Forward |
| No watch, or the watch has ended | Discard: forward |
| The claim says another boot, the serve lock is held exclusive, or the owner lock isn't held | Discard: forward |
| The claim is busy, or any of the three files is missing or gives no clear answer | Forward |
| Unknown token, or a Quick Ask grant | Forward |
| Python has no secret, or an old Python answers the pull 404 | Never `Held`: forward |
| Unknown schema on any private answer | Discard: forward |
| Python gone | Discard at the check. Forwarded requests get R1's 503 with the reason |
| Malformed push | Discard, then 400 so that Python fences |
| Any doubt about the request | Forward (section 5) |

Rust never refuses for a mirror reason, and never serves one. The abort isn't a refusal: it is the one case where an answer has begun and can't be forwarded, and it comes from `SEND_BOUND` running out, not from the mirror's state.

## 8. Tests

All on F1 or a copy of F1 under `C:\tmp\r3-work`, in the existing front harness, with the front built in this worktree's own target directory. Final counts are reported with the build.

**The test build.** `tools/r3/build_fronts.ps1` builds it and the controls. The barrier's tests need a real front stopped at an exact line, which `NtSuspendProcess` alone can't aim. A Cargo feature, `tail-probe`, absent from every release build, adds three things to the tail: a stop at a named line that says so by a file and waits, a trace of when each answer's checks began (before their first lock) and passed, its last byte was accepted, it aborted and it released, and a scripted limit on what each `try_write` accepts. The trace uses the clock `FENCE` already relies on, so it can be compared with Python's `perf_counter`. These tests run on that build, and the rest of the suite on the ordinary one.

**Negative controls: each barrier test has to fail on a build that gets the barrier wrong.** Each is another test-only feature, and a barrier test that passes on its control counts as failed. `tests/front/test_mirror_controls.py` runs them:

| Control | Which tests it must fail |
|---|---|
| `mutant-release-after-first-write`: the design this section's I18 replaced | I18, I19, I21 |
| `mutant-release-before-write`: locks released between the checks and the write | I6, I17b |
| `mutant-no-serve-check`: the tail doesn't take the serve lock | I17a, I17b, I17c |
| A Python claim made with a buffered write and no flush, through a test-only flag | The claim's cross-process read |

| File | Must show |
|---|---|
| `crates/mentis-server/src/grants.rs` (unit) | Every row of section 3's event table and section 4, at exact moments, no clock. Whether the watch has ended is an input, so "ended, no monitor event, no push" must forward. A pull from another boot closes the watch. Each malformed shape discards and never acks |
| `crates/mentis-server/src/grants.rs` (watch) | On a real child process: not ended, then ended when it is killed, without running anything else in between. An unopenable pid gives no watch |
| `crates/mentis-server/src/grants.rs` (tail) | Each line of the tail in order, with the checks and the write as inputs: every refusal forwards having released first, a blocked write with nothing accepted releases and starts again, and nothing is held across an await before the first accepted byte. **Partial writes, scripted to stop in the status line, in the headers and in the body:** no release until the last byte is accepted, and past the deadline the order is abort, then release, and nothing is written after the abort. A dropped or cancelled tail releases. **With a writer that stops in the tail, on real files, a Python taking `.mentis.claim` exclusive through `brainlock` is refused until it returns, and so is a Python taking `.mentis.serve.lock` exclusive,** so the locks really span the check and the last byte. Files opened read-only, none created, the bytes unchanged |
| `crates/mentis-server/src/grants.rs` and `tests/test_brainlock_claim.py` (claim) | **The real cross-process read:** a real Python, through the real claim code, writes a boot and releases, and at that moment a real Rust process, through the tail's own read, must see all 32 bytes, over 1,000 rounds with no sleep, no flush of its own and the writer still alive. The buffered control has to fail. A short write refuses the start. Writing through the locked handle lands at offset 0 and leaves a 32-byte file, on both systems |
| `tests/front/test_mirror_ownership.py` | **The interval, on a real front and real Pythons,** listed below |
| `tests/front/test_mirror_legacy.py` | **A Python from before this build, against a real front,** listed below |
| `tests/test_brainlock_claim.py` | Python alone on a Brain never mirrored creates none of the new files and takes no lock beyond today's, exclusive on the serve lock as today. `brainlock.LOCK_FILES` holds all three, so a backup carries none |
| `tests/front/test_locks.py` (added to) | Its second-Python test passes unchanged in its words on a mirrored Brain, refused at `.mentis.sole.lock`. A second Python under a tail that is stopped refuses at once and doesn't wait. `exchange/apply.py`'s `_alone` still refuses beside a running Python |
| `tests/front/test_deploy_rollback.py` (`PYTHONS_OWN_FILES`) | Holds the three new files, and rollback's behaviour is section 9's |
| `crates/mentis-rules/tests/permitted_matrix.rs`, `tests/front/test_permission_matrix.py` | Section 6 |
| `crates/mentis-rules` (`standing_many`) | Matches `Corpus.stands` on a dump, `as_at` included |
| `tests/front/test_mirror_python.py` | Each mutator pushes or doesn't, per section 3, in order, `down` or not. Python alone pushes nothing. The routes refuse without the secret. No token in any route's answer. No lock held during a fence. The deadline is `last_confirmed` + `FENCE`, including section 4's row 5 order |
| `tests/front/test_mirror_protocol.py` | Boot pull, gap, late push, push during a pull, new boot, old Python 404, old front 404 |
| `tests/front/test_door_answers.py` | Each moved read, per grant shape and `resolve` kind, equal to Python alone across F1 and a Brain copy: status, JSON, errors. Every "forward when" row goes to Python |
| `tests/front/test_door_authority.py` | Revoked, ended and other-corpus grants behave as on Python. A grant on another route still 403 |
| `tests/front/test_mirror_revocation.py` | **Load:** 4 readers per grant, 300 mint and revoke cycles. Any read *started* after the revoke returned must get Python's 403. Repeated with the front suspended by `NtSuspendProcess`, with a push proxy that stalls, and with one that drops the ack. Fence time reported |
| `tests/front/test_mirror_restart.py` | Front restart during a run: the mirror rebuilds and the agent's next read works, forwarded or not. **Previous boot (what "expired" is here: grants have no clock), 20 rounds of each:** (a) front held with a valid lease, suspended by `NtSuspendProcess`, read queued in its backlog, Python killed, a new Python started, front resumed: the read is never a 200, and gets the new Python's 403 or R1's 503. (b) No suspension, with a proxy on `--upstream` that keeps the front's poll connection open after Python dies, so the socket's end is never seen: a read at once after the kill is never a 200. New tokens are served once pulled |
| `tests/test_worker_boundary.py` | Retargeted: `owner` runs over Python alone and through a front. In-process `_Handler` with a secret and a real mirror, front as a subprocess with `--upstream`. Nothing in the test weakens |
| `tests/front/test_wrote_nothing.py` | Extended: R3's reads add no rows, leave sibling hashes unchanged |

**`tests/front/test_mirror_ownership.py`.** Each answers "was this the lease?" by the forward's reason, which must be the barrier's and not the lease's. For the interval without a kill, `B` is a harness that calls `serve`, stops it gracefully, and stays alive, so its port and locks are free and its process object is not signalled, for as long as the test needs. `B'` is imported and waiting before `B` stops, so its claim comes within the lease. `C` is logged by `B'` on the shared clock.

- **I1, I2, I3:** a read with the old token at each stage is never a 200.
- **I4, I5:** the same with the front under `NtSuspendProcess`, a read in its backlog, resumed after each stage.
- **I6, on a real front, not a helper holding the lock:** a real read with the old token, stopped by `tail-probe` between its checks and its write, then `NtSuspendProcess` on the front. `B` released, `B'` started. `B'` must not bind while it is suspended. Resumed: the client gets the whole 200, the trace's release is before `C`, and `B'` binds. Left past a shortened `CLAIM_WAIT` instead: exit 3, in words, the locks free, the port never bound, the claim's bytes unchanged, and the client's answer then goes out when the front is resumed.
- **I18, a controlled partial write, on a real socket:** a client with a small `SO_RCVBUF` asks for an answer several times what the two buffers hold, and doesn't read. `tail-probe`'s limit also stops the first write inside the status line. With bytes accepted and the rest not, `B` is released and `B'` started. `B'` must not claim while bytes remain. The client then drains within `SEND_BOUND`. It must read the whole `Content-Length`, and the trace's last accepted byte and release must both be before `C`. **A complete success doesn't cross ownership.**
- **I19:** as I18, with the front suspended part way, resumed before the bound and past it.
- **I21:** as I18, with a client that doesn't read until past a shortened `SEND_BOUND`. It then reads everything there is: a reset, or fewer bytes than `Content-Length`, never all of them. The trace's order is abort, release, `C`.
- **I8:** a claim held exclusive makes reads forward and leaves `Held`.
- **I9, I10:** `B'` killed at each step by a fault point in the harness: reads forward, and the next Python claims.
- **I11:** a refused second Python leaves all the files unchanged and reads still answered.
- **I12:** a proxy serving `B`'s late position after `R` earns nothing.
- **I13:** a pull answered by `B` after the claim is never adopted.
- **I16:** a Python with no secret on another port, after a mirrored boot, claims.
- **Load, 20 rounds:** 4 readers per grant, front suspended at a random moment, `B` killed and waited on until signalled, `B'` started and answering, front resumed. **The rule, in I6's terms:** a complete old-token 200 finishing after the resume fails the test unless the trace shows that answer's checks passed before the suspension and its release before `C`, which is what I6 and I19 allow. A request the client sent after the resume, or one queued with no passed checks, is never a 200 under any trace. Any answer whose release is after `C` fails regardless. `B'` must either bind while the front was suspended, or wait for it when a tail was caught holding. Also under that load: how long `B'`'s claim waited is reported, and past `CLAIM_WAIT` it is a failed round unless the trace shows a tail stopped by the suspension, because lock starvation is not addressed and this is where it would show. **What shows a tail stopped by the suspension, for a `B'` still unclaimed after the load test's 5 s look:** with the front still suspended, `B'` is past the sole lock with no claim lock and the test's own exclusive try on the claim is refused, so the suspended front holds it. And one trace id both has checks begun and not let go before the suspension, and forwards or releases between the resume and `C`. A tail that began after the resume doesn't count, however close to `C` it lets go.

**`tests/front/test_mirror_legacy.py`.** `L` is a real `python -m mentis.web` from `git archive` of the rollback tag `r1`, which the test holds to `89d8f94519fe6e847ad0b4ade2a90bd9cfe2bea1`, the commit deployed: the code a rollback would run. It doesn't import anything of this build, and it runs on a copy of F1 with `--code` pointing at that export.

- **I17a, the teardown order @Quill named:** `B` is a harness that gives up `.mentis.serve.lock` and `.mentis.sole.lock` only, by a fault point, and stays alive with its owner lock held, so its stale claim, its owner lock and an unsignalled watch all still say `B`. The lease is valid. `L` starts and takes the serve lock. Every old-token read from then on is never a 200, with the reason "serve lock held exclusive": R1's 503 until `L` is bound and `L`'s 403 after.
- **I17b:** a real read stopped by `tail-probe` in its tail, then `NtSuspendProcess`, with `B` killed. `L` exits 3 in its usual words with nothing bound. Resumed, the answer completes, and `L` started again serves.
- **I17c:** the front suspended with a read in its backlog, `L` serving, resumed: never a 200. **Twice over:** with `B` killed, and with `B` as in I17a. After a real kill the owner lock has gone too, so the killed form passes on a tail that never looks at the serve lock, and only the other can fail on `mutant-no-serve-check`.
- **I17d:** as I17a, then `L` stopped, and the read answered. A further `L` is refused while the tail is held.
- **I17e:** `L` running, then this build's Python refuses in words and changes neither `L` nor the files. A front on `L` is never `Held`, pull 404. After `L` stops, this build's Python claims over the stale claim.
- **Section 9's rollback, both ways round:** the front stopped first, and not.

**Reported, never a gate:** moved-read p95, with the two checks and the tail's locks in it, and statements beside C0; how long a claim waited, and how long tails held; aborts past `SEND_BOUND`, with what `SEND_BOUND`, `CLAIM_WAIT` and `CLAIM_POLL` the run used, so the three provisional constants can be set from what is observed; forwards per reason, which is where a too-short lease would show; position-poll cost to Python.

**Run from R1's suite:** the rows covering `/private/*`, the Grant row and `test_python_side.py`, because they touch the same paths.

## 9. Deploy and rollback

| Step | Effect |
|---|---|
| **First deploy** | One Python restart, ending live runs, with the new front. **Asked of the owner** (Turn #1025 item 4). Later front-only releases fall under the standing yes when no run is active |
| **New front, old Python** | Pull gets 404, so never `Held`: everything forwards |
| **Old front, new Python** | Push gets 404, so `down`, one round trip per change, and no wait, because an old front never confirmed anything: everything forwards |
| **Roll back the door** | Route table `worker` → `python`, in force within 2 s, no restart. Pushes continue harmlessly |
| **Roll back a front** | Previous binary, as the row above, except that a revoke just after the stop may wait out what the last front was confirmed for |
| **Roll back R3** | Prior launcher and tag, restarting Python. **The front stops first, for a clean start, not for safety:** under a running front the older Python can only refuse, on meeting a tail, or take the serve lock, after which every tail forwards (section 4, I17a, I17b). Ends live runs, owner's call |
| **`--only python` with older `--code`** | The same: safe under a running R3 front, and it may have to be run again |
| **`rollback-to-python.ps1`** | No secret, so no mirror. It stops the front before Python already (`:62-65`). That Python still claims, because the file exists: the same lock calls and a write, and nobody to wait for |
| **Older Python, then this build again** | The older Python took the serve lock exclusive and ignored the rest. Once it has stopped, this build takes the serve lock shared and writes over the stale claim |
| **Brain** | Rust writes nothing in any case |

Python's fallback is untouched: `_UNGATED_READS`, `_WORKER_READ_GATE` and the moved reads' paths and `Surface` methods all stay (`PLAN-r3`, section 5). The only Python changes are the mirror's push (`authority.py`, one new module), the two private routes (`_refused_private`, `web/__init__.py:6348`), the claim and the serve lock's new mode (`spine/brainlock.py`, called from `serve` at `:7306`) and wiring in `serve` (`:7298`).
