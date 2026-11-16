# Execution visibility: who is actually doing the work

2026-11-16. Visibility only: nothing here changes who performs work, how it is delegated, routed,
authorised or supervised.

## Two relations, never drawn as one

**Mentis delegation.** An independent execution Mentis dispatched for somebody's `delegate`: its own
run, runtime, model, authority and consent. The record links it to the work it came from (the
`work-delegated` act). `operational.runs.delegated_from` reads that link; `/api/activity` sends it on
each run as `delegated_from {by, by_name, expectation, at, run}` (`run`: the originating work's open
run, where one is open).

**Runtime-native worker.** A worker a runtime starts inside one run (a Claude sub-agent). It is a
tool call of that run. It has no participant, Work item, execution, authority or consent of its own:
its permission requests arrive on the run's session and are answered by the run's consent. MARS says
which of the run's tool calls belong to it and what the runtime reported of it
(`_meta["mars/tool"]`: `parent`, `worker`; MARS `docs/API.md` "Native workers").

## What is kept

| Where | What |
|---|---|
| run events and the live feed (`core/run_feed.py`) | tool entries carry `parent` (the worker's entry) and `worker` (facts merged as they arrive); a permission a worker asked for names it; `usage` has the context reading and the runtime's cost; `turn_usage` is what the runtime reported the turn consumed |
| `RunResult.tool_calls` and the run's end act | each call with `parent` / `worker` / `open_at_end`; a failed or stopped run records its calls too |
| the run's end act (`dispatch.usage_facts`) | `context_used`, `context_size` (how full the window was), `tokens` (+ `tokens_cover`), `tokens_by_model`, `cost`, `native_workers` |
| `/api/activity` runs | `runtime`, `model_requested`, `delegated_from`, `workers` (the live feed's summary) |
| `/api/runs/<run>/feed` | for a run no process holds: `recorded`, what its end act kept |

`used` / `size` on an end act are the runtime's last context reading. They read like consumption and
are not; `context_used` / `context_size` name the same reading for what it is. Consumption is only
what the runtime itself reported for the turn (`tokens`, `tokens_by_model`, `cost`). A worker's
`context_tokens` is the size its context reached, never a count of what it spent.

A call the runtime never reported finished (a cancelled or killed turn reports no end for what it
was running) is `open_at_end`; a reader says "cancelled with its run" or "no end reported", never
"pending".

## What each runtime exposes (measured, MARS `docs/native-workers.md`)

| Runtime | Native workers shown | Limit said in the Working view |
|---|---|---|
| Claude Code | each worker, its tool calls and permission requests under it, its model, duration, tool count and final context size; turn tokens by model and cost | none |
| Codex | that a worker started and completed (duration between the two reports) | its tool calls, model and usage are not exposed |
| Antigravity | that a worker was launched (never shown as running: nothing after the launch is reported) | what it does, when it ends and what it uses are not exposed; usage is the parent conversation only |
| Kimi | none | only the run's own activity is reported |
| local | none exist | everything it does is listed |

## Quiet Chat, Working

- A run that is a Mentis delegation says so, and whose; where the run it came from is open, it is
  set in under that run. It keeps its own Activity, Permission and Stop.
- A run's native workers are listed compactly under its row ("2 native sub-agents inside this
  run"), and in Activity each opens to its own tool calls, the permissions it asked for and what it
  handed back.
- Recent runs keep an Activity control: the same view from the live feed while this server still
  holds it, else from the run's recorded end.
- Usage lines name each figure: the context window, the turn's tokens as the runtime reported them
  (and what they leave out), tokens by model, and the runtime's cost.
