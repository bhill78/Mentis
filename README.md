# Mentis

Mentis is a Brain: an append-only record of conversations, knowledge and authority that
people and agents work on together. This repository is the headless foundation: the
record, its HTTP API and the MCP bridge agents use, with agent execution delegated to
**MARS** (Mentis Agent Runtime Service, a separate project). There is no UI yet; the
Fluid workspace (web, then desktop and mobile) will be built on the same API.

Mentis was lifted from **Mark IV** (`github.com/bhill78/Mentis-Mark-4`, branch
`agent-access` at 314b4721), which remains the reference implementation. The first commit
here is Mark IV's `mentis` package verbatim; every later commit is a reviewable change
against it.

## The four parts and who owns what

```
             people (Fluid, later)          agents (Claude, Codex, Antigravity, Kimi, local models)
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

Applications will live in top-level `apps/<name>/` (for example `apps/fluid-web`) and use
only the HTTP API; anything they share belongs in `mentis/`, not in an app. No `apps/`
folder exists until the first application is built.

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

Connect an agent CLI to it with `tools/mcp_bridge.py --session <runtime> --server
http://127.0.0.1:8790` registered as an MCP server in that CLI.

## Test

```
.venv\Scripts\python -m pytest -q                                     # targeted tests
set MENTIS_TEST_BRAIN=<copy of a Brain> && .venv\Scripts\python -m pytest -q -m brain
docker compose run --rm dev                                           # the same, on Linux
```
