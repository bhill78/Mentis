# R3: the grant mirror and the Rust door for reads

For review before building (`PLAN-r3`, section 4: revocation and authority). `adm-56082aa297b0` governs, with `adm-d613177f95fb` section 4 where it doesn't differ. Citations are at `d9281dc`. **Nothing here is built or run.** The timings are design values, accepted from @Quill's review (Turn `ent-ff93ad615193`), except `CLAIM_WAIT` and `CLAIM_POLL`, which are new and not yet reviewed. None is a measurement. The owner's Turns `ent-35d399218b85` (the watch is allowed) and `ent-95415d070be6` (Python's restart semantics are preserved) govern section 4's barrier.

## 1. The one place the plan's wording can't hold, and what this adds

The plan says a failed revoke push "marks the mirror invalid until it re-pulls". A failed push means the front wasn't told, so nothing Python does at that moment can mark the front's copy. A front that is suspended, or too busy to answer within the timeout, wakes up still holding the dead grant, and agents' connections are waiting in its backlog (the same behaviour row K measured for Python).

**So this adds a lease and a fence.** A lease can't see a Python that has died, because its grants end with the process (`authority.py:9-11`) and nothing returns to fence, **so it also adds a boot check.** Python still mints, pushes every change in order and serves the pull. Generations still catch a gap, and an unknown token still forwards.

- **Lease:** the front answers from the mirror only while a confirmation from Python, *sent* within the last `LEASE`, says the mirror is current.
- **Fence:** when a push that removes or narrows a grant fails, the Python call doesn't return until any lease that could predate the change has run out.
- **Boot check:** immediately before admitting a read, and again before answering it, the front asks the kernel whether the Python process that gave it the table has ended (section 4).
- **Ownership barrier:** a process can give up the Brain before it has ended, so the boot check can't order a read against a replacement. Python holds a kernel lock for as long as it owns the Brain, and a replacement can't finish taking ownership while the front is answering, so the front's last check and its first byte can't be separated by one (section 4).

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
3. *No answer from the mirror passes its last check after its Python gave up ownership, and no answer that passed is still unsent when a replacement takes ownership.* A replacement can take ownership only by its claim (section 4), which can't complete while the front is between its last check and its first byte. So a replacement can't take ownership while such an answer is on its way. This holds however long the old process object takes to be signalled, whatever the lease says, and with the front suspended anywhere.

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
| The tail finds another claim, or the owner lock released | Close the watch and the owner handle, discard; pull. This read forwards |
| The tail finds the claim busy, or can't take a clear answer from either file | No change to the state. This read forwards |

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
| `CLAIM_WAIT` | 30 s | How long a starting Python waits for the claim's two locks, then refuses (section 4). Meant to be long enough for a dying process's handles to close and a running front's tails to finish. Safety assumes nothing about it: running out only refuses the start |
| `CLAIM_POLL` | 10 ms | How often that wait tries again, as `LockFileEx` and `flock` are used here without blocking |

All eight are design values, not measurements.

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

**Where the door checks.** Twice, each the last thing before its step: before admitting a read (section 5's mirror row), and in the tail, after the read and before the first byte of the answer. An ended watch at the second check drops the answer and forwards the request with its bytes in hand. `mentis_ops::run` returns whole answers and a read has no effect, so nothing has been said and nothing is done twice.

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

**Why a check alone can't do it.** Whatever the front checks, a suspension can fall between that check and the send, and nothing bounds it. A wait on a replacement's start can't close that either: the front may stay suspended past any wait. So the last check and the first byte have to sit inside something a replacement must get past, and that takes a lock.

**Alternatives rejected.** A replacement that waits out `FENCE` before binding would cost up to 3.1 s at each start, lean on the shared clock, and still leave a front suspended between its check and its send. A claim file with no owner lock has no delay, but serves a Brain given up with no replacement started. Probing `.mentis.serve.lock` itself would make a starting Python refuse if it met the probe, and that lock stays Python's (`crates/mentis-record/src/lib.rs:220`).

**Two files beside the serve lock.** Both go in `brainlock.LOCK_FILES`, so neither is backed up or moved by a restore. They are in the Brain directory, not the run directory, because a replacement started by hand, on any port, takes the same Brain and has no run directory. Two files, not two ranges of one, for `brainlock`'s reason: `flock` locks a whole file.

| File | Who holds it, how | What it says |
|---|---|---|
| `.mentis.owner.lock` | The owning Python, exclusive, for its life | Its being held is the fact. Empty |
| `.mentis.claim` | A claiming Python, exclusive, for moments. The front's tail, shared, for moments | The owner's `boot_id`, 32 bytes |

Both use `brainlock`'s lock: `LockFileEx` on one byte at offset 0, or `flock`, never blocking. A lock dies with its process, and **a process that dies holding one can't have the replacement proceed until the kernel has let go of it,** so a slow release only makes the replacement wait.

**Who may hold what.** Only Python writes either file. The front opens both read-only, never creating them, so Rust still writes nothing to the Brain: a shared lock on a handle opened for reading is enough on both systems. A file missing, or failing to open, means nothing is served.

**A Python's start.** Right after the serve lock (`web/__init__.py:7306`), inside the `try` that gives it back on refusal (`:7308`), and so before the store opens (`:7311`) and before the port is bound (`:7347`). In `mentis/` at `d9281dc`, that `serve` is the only caller of `brainlock.serve` and `:7347` the only place `_Server` is made, so every server on a Brain comes through here.

```
serve lock                        # a second server still refuses here, and touches nothing below
no boot secret and no .mentis.claim: stop here         # Python alone, on a Brain never mirrored: as today
exclusive on .mentis.claim        # up to CLAIM_WAIT. From here every tail forwards
exclusive on .mentis.owner.lock   # the same deadline. From here the last owner has let go
write boot_id at offset 0 of .mentis.claim             # this write is the moment ownership is taken
release .mentis.claim; keep .mentis.owner.lock for life
```

**In that order, for reasons.** Claiming after the serve lock, so a Python that's refused changes nothing a running one depends on. The claim's lock before the owner's, so no tail can find the owner lock held by a replacement with the old boot's claim still in the file. The file's write after the owner lock, so a dying owner's handle has gone before the file changes. An orderly stop gives up the owner lock just before the serve lock (`:7362-7363`). The wait is on a lock, and is not a retried act: nothing failed.

**Past `CLAIM_WAIT`:** `BrainBusy`, so `main` exits 3 in words, as for a second server (`:7402-7405`), the locks given back, nothing bound and the claim's bytes unchanged, because the write comes last: *"a front on this Brain is stopped in the middle of an answer, or the last server hasn't finished dying; resume or end it and start again"*. Safety assumes nothing about this limit. Without it, a Python would wait forever on a front that nothing is going to resume.

**The tail: the door's last step, for every answer it gives from the mirror, 403s included.**

```
wait for the client's socket to take bytes              # holding nothing
open .mentis.claim read-only; try shared                # busy, or failed: forward
read it. Not this boot: discard; forward
try shared on the held owner handle                     # taken: release it; discard; forward
                                                        # any answer but "held exclusive": forward
watch ended: discard; forward
try_write the answer, once, without blocking            # would block: release; start this block again
release, close
write the rest, holding nothing
```

**Inside that block nothing awaits, and nothing depends on a client:** a client not draining waits in the first line, holding nothing. A read isn't run under it, because a read that finishes before a passing check is ordered before the claim, as the check is. Every forward releases first: a forward waits on Python, and that Python could be the one waiting on this lock.

**Why it holds.** Let `R` be when `B`'s owner lock is released. Let `X` be when `B'` takes `.mentis.claim` exclusive and `C` when it writes the claim, so `X < C`, and `R < C` because `B'` holds the owner lock by then. `X` may come before `R`, when a kill releases the serve lock first.

- A tail holds `.mentis.claim` shared from before its checks until its first bytes are accepted, so the whole of it lies before `X` or after `B'` lets the lock go. After that the file says `B'`, so it doesn't pass. **So every tail that passes, first byte included, is before `X`, and so before `C`.**
- A passing tail found the owner lock held. Before `X` no replacement can hold it, so the holder was `B` and its check was before `R`.
- A tail whose check comes after `R` either finds the lock not held, or finds the claim busy or another boot's, so it forwards. That is the "no replacement yet" case too, and it needs nothing from `B'` or from the signal.
- `C` doesn't happen during a passing tail, however long the front is suspended in it. **This is the one case where a suspended front holds up a Python.** It answers the case nothing else can.
- Nothing above reads a clock, or depends on the lease, the watch, the poll connection, a push or a task of the front's. The lease only helps `B'`'s wait end: once it runs out, nothing new is admitted to reach a tail.

**The narrowest thing that remains, stated rather than hidden.** A front stopped between its checks and its first byte (I6), or `B` released in those few syscalls, sends that one answer after `R`. No replacement can have taken ownership by then, or until it goes. The check was true when made, and the answer's read was finished before it. No design with only a check can do better, and this one guarantees what a check can't: no Python is answering in `B`'s place when it goes.

**The first byte is the commitment.** The status line starts in the first accepted write. If an answer is larger than the socket takes at once, the rest follows with nothing held, and is what remains of an answer already given, as bytes in a socket buffer are when Python is killed (I18). It is never a new success.

**Against the adverse orderings of the interval.** `B` is the old boot, `B'` its replacement. "Released" means `B`'s kernel objects have closed; "not signalled" means the watch still reads as running. The lease is valid throughout unless it says otherwise, because that's the case the lease can't help.

| # | Order of events | What decides it | Outcome |
|---|---|---|---|
| I1 | `B` released, not signalled, no `B'` yet, read arrives | Tail: owner lock not held | Forwarded: R1's 503 |
| I2 | `B` released, not signalled, `B'` has claimed but not bound, read arrives | Tail: claim says `B'` | Forwarded: R1's 503 |
| I3 | `B` released, not signalled, `B'` serving, read with the old token | Tail: claim says `B'` | Forwarded: `B'`'s 403 |
| I4 | Front suspended with a read queued; `B` released, not signalled; `B'` serving; front resumes, and the read runs before any task, poll or push | First tail of that read: claim says `B'`. Nothing had to run first | Forwarded: `B'`'s 403 |
| I5 | Front suspended before its tail, then as I1 | Tail: owner lock not held | Forwarded: R1's 503 |
| I6 | Front suspended in its tail after the checks, before the first byte; `B` released; `B'` starts | `B'` can't take the claim's lock, so doesn't bind | When resumed, the first byte goes, then `B'` claims. No `B'` could answer before it. Not resumed within `CLAIM_WAIT`: `B'` exits 3, no ownership taken |
| I7 | Tail has the claim's lock, `B'` is waiting for it, front not suspended | A tail holds it for a few non-blocking syscalls | The answer goes, `B'` claims on its next try. No visible wait expected, not measured |
| I8 | `B'` holds the claim's lock, waiting on `B`'s owner lock, read arrives | Tail: claim busy | Forwarded. No state change, so `B` is still `Held` if `B'` never finishes |
| I9 | `B'` has both locks, dies before the write | Nothing was claimed and `B'` answered nobody. Its locks die with it, and `B` had let go of the owner lock before `B'` took it | As I1: owner lock not held, forwarded |
| I10 | `B'` dies part way through the write | The file is neither `B` nor anyone. `B'` answered nobody | Forwarded until a later Python claims |
| I11 | `B` alive; a second Python started by mistake | It refuses at the serve lock, before the claim | `B` undisturbed and still served |
| I12 | `B` still answering positions after it released (a thread in an orderly stop) | Owner lock not held, or claim says `B'`. A late lease earns nothing | Forwarded |
| I13 | Pull answered by `B`, adoption after `C` | Adoption reads the claim: `B'` | Never `Held` on `B` |
| I14 | Kernel holds up `B`'s handles, so it isn't released, not signalled | Owner lock held, so no `B'` can have claimed | Served while `B`'s confirmations last, up to `LEASE`. Nobody can yet take ownership, so this is row 11, as before |
| I15 | Client not draining its socket when `B` is released | Tail's first line holds nothing, and the block's checks run when it can take bytes | Forwarded, as I1 |
| I16 | `B'` started by hand, no secret, any port, this build | The claim file exists, so it claims | Forwarded. A mirror needs a position from a Python with the secret, so nothing is `Held` again |
| I17 | `B'` is a build before this one, under a running front | **Not covered.** It takes neither lock | Section 9 rules this out by order: the front stops first |
| I18 | Tail passes, first bytes accepted, then `B` released and `B'` serves, rest of the answer still going | The commitment above | The answer finishes. It was committed before |

**What this leaves assumed, and unverified until the build runs it.**

- Shared and exclusive `LockFileEx` and `flock` exclude one another across processes, and die with the process. `brainlock` and `crates/mentis-record/tests/open_refusals.rs` rely on this for the other locks, and neither has run against these files.
- A write through one handle is visible to a read through another on the same machine once the writer's call has returned, with no flush. Durability isn't asked for: a power cut ends the front too.
- The Brain is on a local disk (`brainlock.py:94-96`'s known limit). On NFS or CIFS the locks may not behave so, and neither would the serve lock.
- Every Python that can serve this Brain is this build or later. Section 9 keeps that by order of steps, not by any check.
- Mark IV ignores two more dotfiles in a Brain directory. Not read in Mark IV's source here.
- A real kill's release, with kernel objects closed and the object not yet signalled, can't be produced on demand. Section 8 tests that state with a process that has given up its port and locks and stays alive, which is the same state to the front, and tests kills separately.
- Nothing of this has been built or run. All timings here are design values.

**Costs, all design estimates, none measured:**

| Cost | Size |
|---|---|
| Per answer from the mirror | Open, shared lock, read, one failed lock attempt, unlock and close: about six syscalls beside the two for the watch. Reported with moved-read p95 (section 8). An on-access scanner may slow the open |
| Python's start, ordinarily | Two lock calls, a write. **No startup delay:** nothing waits out a lease |
| Python's start, with a tail in progress or `B` still closing | Up to `CLAIM_WAIT` (30 s). Expected to be one `CLAIM_POLL` or none |
| **A new reason for a start to refuse** | Only if a front is stopped in the tail's few syscalls, or `B`'s handles don't close within `CLAIM_WAIT`. Exit 3, in words. The owner resumes or ends the front and starts again. No read has been wrong in any of this. A stopped front elsewhere than the tail costs nothing |
| A forward instead of an answer | Between `R` and `B'` serving, every moved read forwards and gets R1's 503, as every forwarded route already does. Python alone would refuse the connection there |
| Python alone | Nothing, on a Brain never mirrored. After a rollback, the two lock calls and a write at each start, with nobody to wait for |

**The watch's place now.** On a local disk the barrier reaches every case the watch did, and sooner, since a signalled process has released its locks. It stays because @Quill found it sound and the owner allowed it, and because it is a second fact from the kernel that doesn't depend on a file: guarantee 2 is still stated in its terms. Removing it later would be a separate decision, and nothing here relies on that.

### What the earlier design's guarantees become

| Mechanism or claim, as @Quill reviewed it (Turn `ent-bbfe4fa44abe`) | Now |
|---|---|
| Boot check defeats suspension and delayed monitor tasks, once signalled | Kept as written. Guarantee 2 |
| "An unsignalled dying process still holds the port and lock" (old section 4) | **Withdrawn: it contradicted the termination order.** Replaced by guarantee 3 |
| Served until `B` is signalled, within the lease | **Withdrawn for a released `B`** (I1 to I5). Stays only where `B` still holds its locks (I14) |
| PID reuse: position, then open watch, then pull, then matching `boot_id` | Kept, unchanged. Adoption now also reads the claim |
| Second check, after the read and before the first byte; drop and forward | Kept, now inside the tail and under its lock |
| "Second check passes, then `B` dies before the bytes go out: sent" | Kept for a suspension or death inside the tail, because the tail's lock means no replacement can have taken ownership by the time the first byte goes (I6) |
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
| **Before the first byte of the answer** | Any of the tail's checks refuses: the claim busy or another boot's, the owner lock not held, or the watch ended (section 4) |

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
| The claim says another boot, or the owner lock isn't held | Discard: forward |
| The claim is busy, or either file is missing or gives no clear answer | Forward |
| Unknown token, or a Quick Ask grant | Forward |
| Python has no secret, or an old Python answers the pull 404 | Never `Held`: forward |
| Unknown schema on any private answer | Discard: forward |
| Python gone | Discard at the check. Forwarded requests get R1's 503 with the reason |
| Malformed push | Discard, then 400 so that Python fences |
| Any doubt about the request | Forward (section 5) |

Rust never refuses for a mirror reason, and never serves one.

## 8. Tests

All on F1 or a copy of F1 under `C:\tmp\r3-work`, in the existing front harness, with the front built in this worktree's own target directory. Final counts are reported with the build.

| File | Must show |
|---|---|
| `crates/mentis-server/src/grants.rs` (unit) | Every row of section 3's event table and section 4, at exact moments, no clock. Whether the watch has ended is an input, so "ended, no monitor event, no push" must forward. A pull from another boot closes the watch. Each malformed shape discards and never acks |
| `crates/mentis-server/src/grants.rs` (watch) | On a real child process: not ended, then ended when it is killed, without running anything else in between. An unopenable pid gives no watch |
| `crates/mentis-server/src/grants.rs` (tail) | Each line of the tail in order, with the checks and the write as inputs: every refusal forwards having released first, a blocked write releases and starts again, and nothing is held across an await. **With a writer that stops in the tail, on real files, a Python taking `.mentis.claim` exclusive through `brainlock` is refused until it returns,** so the lock really spans the check and the first byte. Files opened read-only, none created, the bytes unchanged |
| `tests/front/test_mirror_ownership.py` | **The interval, on a real front and real Pythons, each answering "was this the lease?" by the forward's reason, which must be the barrier's and not the lease's.** For the interval without a kill, `B` is a harness that calls `serve`, stops it gracefully, and stays alive, so its port and locks are free and its process object is not signalled, for as long as the test needs. `B'` is imported and waiting before `B` stops, so its claim comes within the lease. **I1, I2, I3:** a read with the old token at each stage is never a 200. **I4, I5:** the same with the front under `NtSuspendProcess`, a read in its backlog, resumed after each stage. **I6:** a helper holding `.mentis.claim` shared as the tail does: `B'` doesn't bind, then binds once it is released. Held past a shortened `CLAIM_WAIT`: exit 3, in words, the serve lock free, the port never bound, the claim's bytes unchanged. **I8:** a claim held exclusive makes reads forward and leaves `Held`. **I9, I10:** `B'` killed at each step by a fault point in the harness: reads forward, and the next Python claims. **I11:** a refused second Python leaves both files unchanged and reads still answered. **I12:** a proxy serving `B`'s late position after `R` earns nothing. **I13:** a pull answered by `B` after the claim is never adopted. **I16:** a Python with no secret on another port, after a mirrored boot, claims. **Load, 20 rounds:** 4 readers per grant, front suspended at a random moment, `B` killed, `B'` started and answering, front resumed. Any 200 whose first byte the client received after the resume fails the test, and `B'` must either bind while the front was suspended or wait for it. Also under that load: `B'` claims within `CLAIM_WAIT` |
| `tests/test_brain_compat.py` (added to) | Python alone on a Brain never mirrored creates neither file and takes no lock beyond today's. `brainlock.LOCK_FILES` holds both, so a backup carries neither |
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

**Reported, never a gate:** moved-read p95, with the two checks and the tail's locks in it, and statements beside C0; how long a claim waited; forwards per reason, which is where a too-short lease would show; position-poll cost to Python.

**Run from R1's suite:** the rows covering `/private/*`, the Grant row and `test_python_side.py`, because they touch the same paths.

## 9. Deploy and rollback

| Step | Effect |
|---|---|
| **First deploy** | One Python restart, ending live runs, with the new front. **Asked of the owner** (Turn #1025 item 4). Later front-only releases fall under the standing yes when no run is active |
| **New front, old Python** | Pull gets 404, so never `Held`: everything forwards |
| **Old front, new Python** | Push gets 404, so `down`, one round trip per change, and no wait, because an old front never confirmed anything: everything forwards |
| **Roll back the door** | Route table `worker` → `python`, in force within 2 s, no restart. Pushes continue harmlessly |
| **Roll back a front** | Previous binary, as the row above, except that a revoke just after the stop may wait out what the last front was confirmed for |
| **Roll back R3** | Prior launcher and tag, restarting Python. **The front stops first, or a Python from before this build could take the Brain under it with neither lock (section 4, I17).** Nothing enforces this order. Ends live runs, owner's call |
| **`--only python` with older `--code`** | The same rule: not under a running R3 front |
| **`rollback-to-python.ps1`** | No secret, so no mirror. It stops the front before Python already (`:62-65`). That Python still claims, because the file exists: two lock calls and a write, and nobody to wait for |
| **Brain** | Rust writes nothing in any case |

Python's fallback is untouched: `_UNGATED_READS`, `_WORKER_READ_GATE` and the moved reads' paths and `Surface` methods all stay (`PLAN-r3`, section 5). The only Python changes are the mirror's push (`authority.py`, one new module), the two private routes (`_refused_private`, `web/__init__.py:6348`), the claim (`spine/brainlock.py`, called from `serve` after `:7306`) and wiring in `serve` (`:7298`).
