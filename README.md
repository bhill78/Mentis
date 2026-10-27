# Mentis

Mentis is a Brain: an append-only record of conversations, knowledge and authority that
people and agents work on together. This repository is the headless foundation: the
record, its HTTP API and the MCP bridge agents use, with agent execution delegated to
**MARS** (Mentis Agent Runtime Service, a separate project). Its one interface is
**Fluid** (`apps/fluid-web`), a web workspace on the same HTTP API, lifted from Mark IV;
desktop and mobile come later on the same API.

Mentis was lifted from **Mark IV** (`github.com/bhill78/Mentis-Mark-4`, branch
`agent-access` at 314b4721), which remains the reference implementation. The first commit
here is Mark IV's `mentis` package verbatim; every later commit is a reviewable change
against it.

## The four parts and who owns what

```
             people (Fluid)                 agents (Claude, Codex, Antigravity, Kimi, local models)
                      |                                  |
                 HTTP API  <----- one Brain ----->  MCP bridge (mentis.worker)
                      \                                  /
                       +------------ Mentis -------------+
                       | record, knowledge, authority,   |
                       | conversations, work, delegation |
                       +----------------+----------------+
                                        | ACP (mars stdio)
                                      MARS  ----> agent sessions, events,
                                                  completion, cancel, cleanup
                Git: owned by whoever asked for the work, and by the agent doing it
```

- **Mentis** owns intent and continuity: what is asked, by whom, under what authority,
  what was returned, and whether anything remains. Its record (the spine) is
  append-only; nothing is rewritten.
- **MARS** owns running an agent. Mentis talks to it only through its public ACP
  interface (`mentis/execution/mars.py`), never by importing it. A finished MARS session
  is an observation, not a verdict: Mentis decides from its own record whether work is
  done, and can hand unfinished work to another agent with the recorded context.
- **Agents** reach Mentis through the MCP bridge, whether a person started them or MARS
  did. A person's CLI gets a hand-started session grant; a run started by Mentis carries
  that run's grant. Every call goes through the same door (`/api/worker`) and the same
  rules (`mentis.worker.permitted`).
- **Git** is ordinary Git. Mentis does not create, park, clean up or commit worktrees.
  A request may name a repository; the agent works in it, and the person or agent that
  owns the work commits.

## Layout

```
mentis/               the core, shared by every interface (Python package)
  spine/  brain/  corpus/        the record: append-only store, Brain identity, migrations
  conversation/                  conversations, Turns, participants, the epistemic ladder,
                                 governance, decisions, forms, orientation
  sources/  exchange/            sources and retrieval; Brain export and import
  operational/                   work tracking: requests, stages, the work overview
  fluid/                         the read models the Fluid workspace uses (no UI code)
  core/  api/                    MentisService and its types
  authority.py  worker.py        grants, and the agent surface + MCP bridge
  execution/                     the boundary to MARS (interface, MARS client)
  web/                           the HTTP API (the interface every application uses)
tools/mcp_bridge.py   starts the MCP bridge for an agent CLI against a running server
tests/                targeted tests for lifted code and the execution boundary
```

Applications live in top-level `apps/<name>/` and use only the HTTP API; anything they
share belongs in `mentis/`, not in an app.

```
apps/fluid-web/       Fluid: React + Vite, one page (index.html), served by the server
  src/fluid/          the workspace: frame, conversation, workspace zones, present,
                      sections (Home's registry), render (posts), runs (agent activity)
  src/experimental/   the Markdown Renderer's blocks, object kinds and forms
  render-check.mjs    builds dist/render-check.js, the readers the server runs
  tests/              client unit tests (npm test)
```

## Run it

Native Windows is the primary environment.

```
py -3.12 -m venv .venv
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m mentis.web <brain-dir> --port 8790 --workspace <dir> --mars "<mars command>"
```

`<mars command>` starts MARS's ACP server, e.g. `C:\Work\MARS-venv\Scripts\mars.exe stdio`
(or set `MENTIS_MARS_COMMAND`). Never point a development server at the live Brain: work
on a copy (see AGENTS.md).

### Fluid

```
cd apps\fluid-web
npm ci
npm run build                                  # dist/: the server serves it at / and /fluid
npm test                                       # client unit tests
set MENTIS_API=http://127.0.0.1:8790 && npm run dev   # or: a dev server against a running Mentis
```

The server serves `apps/fluid-web/dist` (or `MENTIS_FLUID_DIST`) and reads
`render-check.js` from it to check agents' Markdown. With nothing built it still serves
its API and says Fluid is not built; `node apps/fluid-web/render-check.mjs <file>`
builds the render-check bundle alone for a headless server.

### Connect an agent CLI

Every CLI starts the same bridge: `python -I tools/mcp_bridge.py --session <runtime>
--server http://127.0.0.1:8790`. It asks the server where its code is and serves from
exactly that code, so nothing needs updating when Mentis changes. The session gets a
hand-started grant (`manual-session` scope); every call is checked at `/api/worker`.

- **Claude Code**: an `--mcp-config` file, or `claude mcp add mentis -s user -- <python> -I <repo>\tools\mcp_bridge.py --session claude --server <url>`.
- **Codex**: `codex mcp add mentis -- <python> -I <repo>\tools\mcp_bridge.py --session codex --server <url>`. Non-interactive `codex exec` refuses MCP tools that need approval, so also set `mcp_servers.mentis.default_tools_approval_mode = "approve"` (Mark IV did the same).
- **Antigravity**: `agy mcp add mentis <python> -I <repo>\tools\mcp_bridge.py --session antigravity --server <url>`.
- **Kimi Code**: `~/.kimi-code/mcp.json` with the same command and `--session kimi`.
- **Agents started by Mentis** get the bridge automatically: each run's MARS session is
  given one MCP server named `mentis` carrying that run's grant.

## Test

```
.venv\Scripts\python -m pytest -q                                     # targeted tests
set MENTIS_TEST_BRAIN=<copy of a Brain> && .venv\Scripts\python -m pytest -q -m brain
docker compose run --rm dev                                           # the same, on Linux
```
