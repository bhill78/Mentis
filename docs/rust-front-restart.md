# What restarting the Rust front does to agent calls

Section 3.2 of `adm-56082aa297b0`, checked against the source at `b8e324c`. Tested by `docs/rust/R1-acceptance.md` row J, whose expected results are frozen. Every case has one, with the message allowed for it in `tests/front/restart_messages.json`. Labels say where the expectation comes from: **S** read in source, **M** measured, **R1** R1's wording, frozen here. If a test disagrees, the test fails, and this page and its assertion are revised visibly with a reason.

## What survives and what doesn't

**Survives:** the Python and MARS processes, their execution state, grants, and the connection between Python and MARS, which doesn't pass through the front.

**Doesn't:** any promise about the turn. An agent gets an error from a tool call, nothing retries it automatically, and the agent may change course or end its turn. **Restarting the front can change a run's outcome.** So a rollback or restart that replaces the front reads "processes survive; a run may be affected".

**The gap.** The front stops accepting the moment a planned stop begins, so the gap is the drain, up to 35 s, plus the next front's start. A crash's gap is only the start. It is measured and reported, and nothing here makes it zero.

## The cases

| Case | What happens | Status |
|---|---|---|
| **A.** A call arrives during the gap | `NoOwner`: "no Mentis is answering... nothing else to try" (`worker.py:6733`). Nothing was done, so this is true | S |
| **B.** A call was forwarded, and the front dies before replying | Today it's false for a write: Python may still commit. R1 changes this wording to say the result is unknown, as the timeout message does (`worker.py:6728-6732`). See below | **R1** for sent and reply; **S** for sending. J4, J8 |
| **C.** An MCP server starts during the gap | **A hand-started bridge exits:** `running_release` fails, and `main` returns 1 (`tools/mcp_bridge.py:118-119`), so that session may have no Mentis tools. **A dispatched run doesn't use the bridge:** its server is `boot_command` (`core/service.py:1242-1248`), which doesn't ask the server anything to list its tools, so its first call meets case A. **The effect on a hand-started session:** exit 1, the server `failed`, and no `mcp__mentis__` tool in the session's list | **S** for both, **M** for the session (`docs/rust/evidence/j16-probe.json`). J3, J16 |
| **D.** An agent repeats a write | Safe only for writes carrying an operation key: the second answers `replayed: true` and writes nothing (`conversation/anchors.py:223-243`). Others can duplicate. The list is below | **S,** and **M** for J12's three (`docs/rust/evidence/j12-probe.json`). J10, J11, J12 |
| **E.** A planned restart | The front stops accepting, finishes the calls in flight up to 35 s (the worker's own limit is 30 s), then exits. The gap remains | **R1,** P1.2 builds it. J1 |
| **F.** Fluid | The next poll recovers: a failed beat only backs off (`apps/fluid-web/src/fluid/identity/activity.ts:181-185`). A composer's retry carries its `op` key (`apps/fluid-web/src/fluid/Composer.tsx:144`, `:502`). Retrying is the person's: the composer shows the error and keeps the draft | **S.** J13, J14 |

## Case B in detail

Three ways for a call to end, read from `_over` (`worker.py:6693-6737`) and from `urllib` and `http.client` under Python 3.12. J4 and J8 assert R1's column, with the exact words in `tests/front/restart_messages.json`. The run before the wording changes is the named step P1.5-J4-before, and it isn't the acceptance check.

| The front dies | What `_over` sees | Today's message | R1's |
|---|---|---|---|
| While the request is being sent | `URLError`, since `do_open` wraps only `h.request` | `NoOwner`. True: Python never had the whole request | Unchanged, entry `B-sending` |
| After sending, before the reply starts | Bare `RemoteDisconnected` or `ConnectionResetError`, since `getresponse` isn't wrapped | `NoOwner`. **False for a write** | "OwnerError: Mentis at {via} stopped before answering {name}: the request was sent, so the result is unknown. It may still have done it: do not report it as not done. Check the record, or call it again if it is safe to repeat." Entry `B-sent` |
| While the reply's body is arriving | `http.client.IncompleteRead`, **which isn't an `OSError`,** so `_over` doesn't catch it. It surfaces through `serve`'s catch-all as `IncompleteRead: ...` (`worker.py:6975-6983`). A reset here is a bare `OSError`, as in the row above | Not false, and says nothing useful | The same words, entry `B-reply`. **The third row is an addition to section 3.2** |

The `URLError` test already exists on the timeout path (`worker.py:6711-6722`), so telling "not sent" from "sent" needs no new mechanism.

**When Python dies instead,** the front's 503 reaches the agent as `OwnerError`, "could not answer this" (`worker.py:6708`). The 503's reason has to be true too, and both are frozen: `Python-reached`, "Python stopped with this request in hand, so the result is unknown. It may still have done it: check the record before repeating it.", and `Python-unreached`, "Python is not answering behind this front, so this request did not reach it and nothing was done."

## Case D: which writes carry a key

**Two things are called `op`.** In a `POST /api/worker` body, `op` is the operation's name. The key is `args.op`. Everywhere else, `op` in the body is the key.

An operation's key is checked against a digest of the request, so reusing one for a different request is refused. A call that omits an optional key isn't keyed: `anchors.keyed` runs it as a plain write (`conversation/anchors.py:211-212`).

### Agent operations, `POST /api/worker`

From `ALL_TOOLS` and `READ_ONLY` in `worker.py`. **5 of 28 writes take a key, and none requires it.** Row J11 checks this list against the code, so it can't drift silently.

| Writes | Which | Repeating one |
|---|---|---|
| **Key available: 5** | `answer`, `timer`, `anchor`, `react`, `deep_dive` | With the same key: one occurrence, `replayed: true` |
| **No key, a guard read in source: 5** | `take_up`, `request_input`, `summon_participant`, `claim_resource`, `release_resource` | `take_up` refuses, "already carried" (`worker.py:4752`), measured for J12. `request_input` returns the first open wait (`:5010`, `:5077`). `summon_participant` finds the existing one (`:5526`). `claim_resource` by the same holder renews its own lease (`operational/leases.py`); `release_resource` of a lease already released writes nothing |
| **No key, no guard read: 22** | `contribute`, `record_request`, `record_outcome`, `request_decision`, `await_work`, `record_discovered_work`, `change_workflow`, `record_verdict`, `return_artifact`, `read_artifact`, `open_topic`, `open_conversation`, `delegate`, `propose_material`, `propose_revision`, `resume_intake`, `attach_follow_up`, `respond`, `record_material`, `request_adoption`, `challenge`, `withdraw_challenge` | **Could duplicate** through the front's `op` key, which these lack. Since WS-I every write also accepts Python's own `op_key` (`mentis/opkeys.py`), which the bridge's outbox always sends; this row is about callers that send neither. "No guard read" means I found none, not that none exists: a later check in the command may refuse. Row J12 fixes the result for two of these: `open_conversation` and `record_discovered_work` each write twice, measured on Python alone. `read_artifact` is here because a dispatched run's read records the supply (`worker.py:321`) |

So after case B an agent has to **check the record before repeating most writes,** as the timeout message already tells it to.

### HTTP routes

Read from `fluid/commands.py`, `conversation/posting.py`, `conversation/anchors.py`, `fluid/arrangements.py` and `web/__init__.py`.

| Key | Routes |
|---|---|
| **Required** | `POST /fluid/api/response-sets`, `/fluid/api/response-sets/<id>/{answers,own-words,show,start-new,move}`, `/fluid/api/interpretations/<id>/{confirm,change,decline}` (`fluid/commands.py:823-825`). `.../address` when the action is ask-participant (`posting.py:583`) |
| **Optional** | `POST /fluid/api/posts`, `/api/conversations/<id>/turns` (keyed only with an `author`, `posting.py:95`). `.../address` when record-only. `/fluid/api/posts/<id>/{reactions,comments,deep-dives}`, `/api/anchors`, `/api/anchors/<id>/{reactions,deep-dives}`. `/fluid/api/conversations`, `/fluid/api/conversations/group`, `/fluid/api/conversations/<id>/{name,members}`, `/fluid/api/work/<id>/workflow`, `/fluid/api/arrangements/<key>`, `/fluid/api/response-sets/<id>/{ready,send-back}`, `/api/conversations/<id>/{participants,topics}`, `/api/timers/<post>/<name>/marks` |
| **None** | `POST /fluid/api/posts/<id>/{edit,delete,topics,unfile,move}`, `/fluid/api/reactions/<id>/withdraw`, `/fluid/api/layouts`, `/fluid/api/layouts/defaults`, `/fluid/api/layouts/<id>/delete`. `/api/conversations`, `/api/conversations/<id>/instructions`, `/api/turns/<id>/{expect,topics,unfile,move,link,unlink}`. All of `/api/entries...`, `/api/governance/arrive`, `/api/ladder/vocabulary`, `/api/personas`, `/api/participants...`, `/api/presentation/...`, `/api/sources/...`, `/api/artifacts`, `/api/exchange/import/...`, `/api/worker/session`, `/api/worker/session/end`, `/api/intake/resume`, `/api/runs/<run>/{stop,consent}` |

Fluid's own composer and toolbar send keys where the route takes them. Whether every Fluid caller does isn't checked here.

## When a restart may happen

**Deploying.** `docs/cutover/deploy-front.ps1` (P1.5, `docs/rust/contracts/launcher.md`) lists active runs and asks before it restarts the front. The owner's standing yes covers an accepted front-only release only when no run is active, and the owner is told what changed (Turn `ent-a60e9f7e22b4`). Anything that restarts Python, interrupts runs, changes Brain writes or needs a semantic migration goes back to the owner (Turn `ent-9a3dff0b382f`, item 4).

**Rolling back a route** is an edit to the route table, with no restart, and none of this applies.

## What row J has to show

Each case behaves as this page says, and every message the agent sees is on the allowed list for its case, with any other failing. A `NotPermitted` message counts only if Python really refused that call and the call wrote nothing, on the evidence in `R1-acceptance.md`, "J". No acknowledged write is lost, and a keyed write doesn't duplicate. The gap is measured and reported. **The agent's turn isn't required to succeed.**
