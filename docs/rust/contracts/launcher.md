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
    [--attached]
    [--only front|python]
mentis-launch stop [--run-dir <dir>] --front
```

| Argument | Rule |
|---|---|
| `<brain>`, `--port`, `--host`, `--workspace`, `--writable-root`, `--mars` | As `python -m mentis.web` takes them. `--host` and `--port` are the **public** address, which `tailscale serve` and every bridge already point at |
| `--private-port` | Default public + 10000. Always bound on 127.0.0.1. In use: refuse, don't pick another |
| `--front` | Default: `mentis-server.exe` beside `mentis-launch.exe` |
| `--dist` | Fluid's build. Default `MENTIS_FLUID_DIST`, else `<code>/apps/fluid-web/dist`, as `conversation/render_check.py:47` |
| `--run-dir` | Default `%LOCALAPPDATA%\Mentis\run\<port>`. **Never in the Brain** |
| `--attached` | Stays running as both processes' parent, until killed, doing nothing else. For tests and the bench only: their process accounting works by tree |
| `--only` | Start one side, using the existing state file's secret and ports. For a front-only deploy, or restarting a dead Python |

Absolute paths only: nothing is found through `PATH`, because the bench strips `PATH`. Both processes inherit the launcher's environment, so what DAY-TO-DAY's launcher sets today (`MENTIS_MARS_COMMAND`, `MARS_BACKENDS_FILE`, `PYTHONIOENCODING`) reaches Python as it does now.

## The order

1. **Look.** Public or private port in use: refuse, exit 3, in words. No state is written.
2. **Secret.** `secrets.token_urlsafe(32)`'s equivalent, unless `--only`.
3. **Python:** `<python> -m mentis.web <brain> --host 127.0.0.1 --port <private> --answers-at http://<host>:<port> --workspace ... [--mars ...]`, cwd `<code>`, with `MENTIS_BOOT_SECRET` in its environment. It refuses as it always has, exit 3, and `.mentis.serve.lock` stays Python's. Wait for `GET /api/server` on the private port, up to 240 s, the bench's own limit: a large Brain's start is slow.
4. **Front:** `<front> <brain> --host <host> --port <port> --upstream http://127.0.0.1:<private> --dist <dist> --run-dir <run dir> [--route-table <file>]`, with `MENTIS_BOOT_SECRET` in its environment. Wait for `GET /api/server` through it, up to 30 s.
5. **Say so.** Write `<run dir>/launch.json` (`LaunchState`), atomically, readable by this user alone (`mentis/readonly.py:259`'s `keep_to_user`, before any secret goes in). If that can't be done: refuse. Print one line, `Mentis on http://<host>:<port>`, and exit 0.

**A start that fails stops what this invocation started,** then exits 3 with the reason. It isn't recovery: nothing has been handed over yet, and no half-server is left behind. After step 5 it touches nothing.

**Surviving the launcher.** Both processes must outlive the launcher and whatever started it, with no console attached and output appended to `<run dir>/front.log` and `<run dir>/python.log`. On Windows, deploy scripts start the launcher through `Win32_Process.Create`, as `mars-switch` does, to leave any job the caller is in. The POSIX path is `setsid`.

## The secret

- **One per full launch.** It travels in `MENTIS_BOOT_SECRET`, **never on a command line,** where any local user could read it from the process list.
- **It outlives a front restart.** Python keeps it for life, so a restarted front takes it from `launch.json`. `--only python` also reuses it, so a Python restart doesn't strand a running front.
- **It proves "from this boot's front"** and guards `/private/*`. It grants no authority over the record: every effect still passes the grant check.

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

It never restarts Python. A release that needs that isn't front-only, and goes back to the owner (Turn `ent-9a3dff0b382f`, item 4). Whether a release is accepted isn't something the script can know: whoever runs it answers for that.

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
