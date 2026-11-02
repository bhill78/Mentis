# Contract: the launcher

Code: `crates/mentis-server/src/launch.rs`, the names and the state file. P1.5 builds `mentis-launch` and the Python side. The installer package (branch `installer-from-main`) consumes this contract and builds nothing of it.

## What it is

`mentis-launch` starts both processes **as siblings,** says they answer, and exits. **Nothing restarts either one,** and no process watches the other. If Python dies, owned routes keep answering, forwarded routes answer 503 with the reason, and the owner restarts it. That is why this isn't the supervision `AGENTS.md` rules out, and why Python running beside the front needs no exception to it.

```
mentis-launch <brain>
    --port 8760 [--host 127.0.0.1] [--private-port 18760]
    --workspace <dir> [--writable-root <dir>]... [--mars <command>]
    --python <python.exe> --code <dir holding mentis/>
    [--front <mentis-server.exe>] [--dist <Fluid's dist>] [--route-table <file>]
    [--run-dir <dir>]
    [--attached] [--upstream <loopback url>]
    [--only front|python]
mentis-launch stop [--run-dir <dir>] --front
mentis-launch recover [--run-dir <dir>]
```

| Argument | Rule |
|---|---|
| `<brain>`, `--port`, `--host`, `--workspace`, `--writable-root`, `--mars` | As `python -m mentis.web` takes them. `--host` and `--port` are the **public** address, which `tailscale serve` and every bridge already point at |
| `--private-port` | Default public + 10000. Always bound on 127.0.0.1. In use: refuse, don't pick another |
| `--front` | Default: `mentis-server.exe` beside `mentis-launch.exe` |
| `--dist` | Fluid's build. Default `MENTIS_FLUID_DIST`, else `<code>/apps/fluid-web/dist`, as `conversation/render_check.py:47` |
| `--run-dir` | Default `%LOCALAPPDATA%\Mentis\run\<port>`. **Never in the Brain** |
| `--attached` | Stays running as both processes' parent, until killed, doing nothing else. For tests and the bench only: their process accounting works by tree |
| `--upstream` | **For row J's J6 and J7 only.** What step 4 gives the front as `--upstream`, in place of the private port, so `tools/r1/door_recorder.py` can stand between the front and Python. Only `http://127.0.0.1:<port>`; anything else is refused. Python, the wait in step 3 and the state file don't change, and it isn't remembered: `--only front` takes it again or goes direct. Installers and deploy scripts never pass it. P1.5 builds it, and it changes nothing without it |
| `--only` | Start one side, using the existing state file's secret and ports. For a front-only deploy, or restarting a dead Python |

Absolute paths only: nothing is found through `PATH`, because the bench strips `PATH`. Both processes inherit the launcher's environment, so what DAY-TO-DAY's launcher sets today (`MENTIS_MARS_COMMAND`, `MARS_BACKENDS_FILE`, `PYTHONIOENCODING`) reaches Python as it does now.

## The order

1. **Look.** Public or private port in use: refuse, exit 3, in words. No state is written.
2. **Secret.** `secrets.token_urlsafe(32)`'s equivalent, unless `--only`.
3. **Python:** `<python> -m mentis.web <brain> --host 127.0.0.1 --port <private> --answers-at http://<host>:<port> --workspace ... [--mars ...]`, cwd `<code>`, with `MENTIS_BOOT_SECRET` in its environment. It refuses as it always has, exit 3, and `.mentis.serve.lock` stays Python's. Wait for `GET /api/server` on the private port, up to 240 s, the bench's own limit: a large Brain's start is slow.
4. **Front:** `<front> <brain> --host <host> --port <port> --upstream http://127.0.0.1:<private> --dist <dist> [--route-table <file>]`, with `MENTIS_BOOT_SECRET` in its environment. Wait for `GET /api/server` through it, up to 30 s.
5. **Say so.** Write `<run dir>/launch.json` (below), atomically, readable by this user alone (`mentis/readonly.py:259`'s `keep_to_user`, before any secret goes in). If that can't be done: refuse. Print one line, `Mentis on http://<host>:<port>`, and exit 0.

**A start that fails stops what this invocation started,** then exits 3 with the reason. It isn't recovery: nothing has been handed over yet, and no half-server is left behind. After step 5 it touches nothing.

**Surviving the launcher.** Both processes must outlive the launcher and whatever started it, with no console attached and output appended to `<run dir>/front.log` and `<run dir>/python.log`. On Windows, `deploy-front.ps1`, `rollback-to-python.ps1` and `cutover.ps1` start what they leave running through `Win32_Process.Create`, as `mars-switch` does, to leave any job the caller is in (`Start-Outside`, `docs/cutover/launch-common.ps1`). `CREATE_NEW_PROCESS_GROUP` doesn't do that: **the launcher run directly stays in its caller's job, and so do both processes.** Whatever may be in a job starts it the same way. The POSIX path is `setsid`.

## The state: `launch.json`

`<run dir>/launch.json`, `LaunchState` in `launch.rs`. It is the only state a later `--only`, `stop` or script needs: what used to be a second file, `launch-args.json`, is its `started_with`, so the two can't disagree and there is no moment when one is written and the other isn't.

| Field | What |
|---|---|
| `format` | 1. Any other is refused by whoever reads it. There is no reading of older forms: nothing has shipped with this file |
| `brain`, `public_host`, `public_port`, `private_port`, `answers_at` | As started |
| `secret` | See "The secret" |
| `front`, `python` | Each `{pid, start_time, executable, log}`. **`pid` and `start_time` together identify the process,** because a pid can be reused and a reused one can be the same interpreter: nothing is stopped by pid without comparing `start_time`. Windows: its creation time as a FILETIME, as `Process.StartTime.ToFileTimeUtc()` reads it. Linux: `/proc/<pid>/stat`'s field 22 |
| `started_with` | `{python, code, workspace, writable_roots, mars, dist, route_table}`, what a later start needs. An `--only` overrides what it is given and rewrites the file. `--upstream` is deliberately not here |

**Permissions:** this user alone, set before anything is written to the temporary file that's renamed over it. **Written** whole by step 5 and by each `--only`, and removed by a rollback. Installers don't depend on its fields.

## A launcher killed part way

Python and the front are detached before `launch.json` can say so, so a launcher killed in between would leave a process that may hold the Brain and that nothing has a record of. So from before the first process until `launch.json` is written there is a journal, `<run dir>/launch.starting.json`: `{format, launcher, started}`, each a `{pid, start_time}`, this user's alone.

- **Each process is on record before it runs.** On Windows it's created suspended, added to the journal, then let run. A kill between those leaves a suspended process that nobody has a record of, and which holds no port and no lock. On POSIX the journal is written just after the process starts, with nothing to hold it, so a kill exactly there leaves it unrecorded.
- **Creating the journal is the claim on the run directory.** A launcher still alive and starting there refuses any other, by name.
- **It goes when the start ends,** by publishing `launch.json` or by a start that fails stopping what it started.
- **What finds one, from a launcher that has died:** every recorded process gone, or all of them already in `launch.json`, because the kill landed between saying so and tidying up: it is cleared, and the command goes on. Otherwise a full start, `--only`, `stop` and both scripts refuse, naming what's still running and this command.
- **`mentis-launch recover`** stops the journal's processes that are still themselves, each with its tree, and removes it. **It doesn't start anything,** and nothing runs it by itself: stopping a Python is the owner's decision each time, and the front may already have answered somebody. A start is the next thing they run.

Under `--attached` the journal is the same. A killed tree leaves it with nothing alive, and the next start clears it.

## The secret

- **One per full launch.** It travels in `MENTIS_BOOT_SECRET`, **never on a command line,** where any local user could read it from the process list.
- **It outlives a front restart.** Python keeps it for life, so a restarted front takes it from `launch.json`. `--only python` also reuses it, so a Python restart doesn't strand a running front. `stop --front` reads it there too. These are why it is on disk: each is a new process with nowhere else to get it. It leaves Python's environment once read, so nothing Python starts inherits it.
- **What it proves:** that the sender could read `launch.json`, or was given it by the launcher. It doesn't prove the sender is the front. It guards `/private/*` and the trust in `X-Mentis-Peer`, and grants no authority over the record: every effect still passes the grant check, which looks at neither header.

| Against | Can it hold the secret? | So |
|---|---|---|
| **Anyone through the public port** | No: the front strips any inbound copy | It can't claim a peer or reach `/private/*` |
| **Anyone off this machine, at the private port** | No, and it can't connect: always bound on 127.0.0.1 | |
| **Another Windows user on this machine** | No: `launch.json` is this user's alone, and the environment of this user's processes isn't theirs to read. An administrator is not held off | It can't claim a peer, read the snapshot or stop the front. It can connect to the private port and is a loopback peer there, as on Python alone |
| **Any process running as this user** | **Yes. This is not defended, and the secret can't defend it** | It can present the secret, claim any peer and stop the front |

**Why the last row is out of scope and not a hole.** Holding the secret gets a process of this user nothing it doesn't already have. A claimed peer reaches one thing, `sources/picker.py`'s loopback check, which that process's own socket already passes, and any other claim only refuses the caller. `/private/stop` ends a front it could `taskkill`. `/private/live` is run state in a Python whose memory it can read. It can read the Brain's files too, whoever serves them. `tests/front/test_python_side.py` holds the part that can be run: the same picker answer and the same 403 from `/api/worker`, with the secret and without. One limit follows: an agent sandboxed to less than this user's rights gets from the secret whatever its sandbox lets it read. Its grant still decides its operations, but if it can read the run directory it can stop the front, which is why the run directory stays out of workspaces.

## The peer

| Who | Does |
|---|---|
| **Front, on every forwarded request** | Removes any inbound `X-Mentis-Peer` and `X-Mentis-Boot-Secret`. Adds `X-Mentis-Peer: <socket peer>` and `X-Mentis-Boot-Secret: <secret>`. The value is the peer IP alone, as `self.client_address[0]` is |
| **Python** | Believes `X-Mentis-Peer` only when `X-Mentis-Boot-Secret` equals its secret, by constant-time compare, and only when it has one. Otherwise it uses the socket peer and ignores the header. Python alone has no secret and behaves exactly as today. In all cases the value goes where `self.client_address[0]` goes today (`web/__init__.py:6914-6926`), and that is the only place |
| **Picker** | `sources/picker.py:103-108` is unchanged. It gets the true peer |

## `answers_at`

`python -m mentis.web` gains `--answers-at <url>`, default today's `http://{host}:{port}`, passed to `_State` at `web/__init__.py:7135`. So agents are told the public address and their calls pass through the front. `/api/server` keeps reporting the public host and port, because it reads `answers_at` (`:2054`). So does the picker's loopback check on `answers_at` (`sources/picker.py:105`).

**`.mentis.serve.json` will say the private port** (`:7129`). It is only ever used for the second-server refusal message (`spine/brainlock.py:216`), so nothing breaks. The message will name 18760; leave it.

## `/private/*`

| Where | What |
|---|---|
| **Public port** | The front answers `/private/*` itself and **never forwards it**. `POST /private/stop` is honoured only from a loopback peer with the secret. Everything else is 404 `{"error": "no such semantic surface"}`. That is a listed difference from Python alone, where such a GET returns `index.html` |
| **Private port** | Python answers `/private/live`, and from R3 the grant pull, only with the secret. Anything else under `/private/` is 404 |

## Stopping

- **Planned front stop:** `mentis-launch stop --front` sends `POST /private/stop` with the secret. The front stops accepting at once, finishes what it has forwarded, up to `DRAIN_LIMIT` (35 s; the worker's own limit is 30 s), and exits 0. **Processes survive; a run may be affected:** a call in the gap fails, and the agent may change course (`docs/rust-front-restart.md`).
- **Python:** as today, by `taskkill` of its tree. Ends live runs. **Owner's decision each time** (Turn #1025).
- **The Brain's locks** die with their process in every case.

## Deploying (P1.5)

`docs/cutover/deploy-front.ps1` replaces the front, and `docs/cutover/rollback-to-python.ps1` goes back to Python alone. Both are scripts a person or agent runs: nothing watches or retries.

**`deploy-front.ps1 -Front <binary> [-RunDir <dir>] [-YesWhenIdle]`:**

1. **Lists active runs,** from `GET /fluid/api/runs` through the running server.
2. **None active:** with `-YesWhenIdle` it goes on, which is how the owner's standing yes for an accepted front-only release is used (Turn `ent-a60e9f7e22b4`). Otherwise it asks.
3. **Any active, or the list can't be read:** it prints them, or says it couldn't read them, and **asks,** with `-YesWhenIdle` or without. Answered no, or with nobody to answer, it changes nothing and exits 3.
4. **Lists again** immediately before stopping, and goes back to step 3 if a run started since. A run can still start after that: the list is a moment, not a lock.
5. **Stops the front** with `mentis-launch stop --front`, then starts the new one with `--only front`, and waits for it to answer.
6. **Says what changed,** in a line for the owner's report: old and new binary digest, and the gap.

It never restarts Python. A release that needs that isn't front-only, and goes back to the owner (Turn `ent-9a3dff0b382f`, item 4). Whether a release is accepted isn't something the script can know: whoever runs it answers for that. **A front that is already dead:** it refuses, having changed nothing. It isn't a recovery path, and `--only front` is. **A new front that won't start:** it says the front is down and how to start the previous binary, with Python and `launch.json` as they were.

**`rollback-to-python.ps1`** stops only the Python `launch.json` identifies by pid and start time. A pid that isn't that process is left alone and said so. If something else holds the private port, it refuses before stopping anything, because Python alone couldn't then be what answers.

## The worker's transport (P1.5)

Telling apart what `_over` can already tell apart (`worker.py:6693-6737`). **No retry is added:** `docs/rust-front-restart.md`, cases A and B. The exact words are frozen in `tests/front/restart_messages.json`, and `R1-acceptance.md` names the run before they change, P1.5-J4-before.

| What the call meets | Answer |
|---|---|
| Connection refused, or the request couldn't be sent: a `URLError` | Unchanged, `NoOwner`. Nothing was done, so it is true |
| Reset after sending, or a reply cut short: a bare `OSError`, or `http.client.IncompleteRead` | The result is unknown, in the frozen words of entries `B-sent` and `B-reply`, which take the timeout's "It may still have done it". Never "nobody answered" |

## What the installer takes from this

1. **Ship** `mentis-launch.exe` and `mentis-server.exe` side by side, with `mentis/` and Fluid's `dist/`, and a Python to run it until R8.
2. **Start** by the one command above. It needs nothing else on `PATH`.
3. **Ready** when the launcher exits 0. Exit 3 means refused, with the reason on stderr.
4. **Don't depend on** the private port's value, `launch.json`'s fields, or either log's contents.
5. **New-Brain setup** stays the installer's and runs before this, as now: `python -m mentis.bootstrap` (`mentis/bootstrap/README.md:73-78`). Startup seeds nothing.

Until the launcher exists, a build from main still starts by `python -m mentis.web`, and that keeps working: Python alone stays a complete server until the first retirement, and the first retirement waits for every launch path to move (plan, section 3).

## R1's Python changes, all of them, all P1.5's

1. `--answers-at`.
2. The trusted peer.
3. `GET /private/live`, and a route guard for `/private/`.
4. The worker's transport wording. No retry.

Each leaves Python alone behaving exactly as it does today.
