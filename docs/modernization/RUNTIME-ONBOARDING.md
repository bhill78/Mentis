# Runtime onboarding and parity (round 2, O9 / program §11-12)

Mentis is not a Claude-centric agent system. Every runtime does the same Mentis work
through the same work model, epistemic model, authority and reporting: what differs is
declared, measured and represented, never assumed. This document is the contract a
runtime joins by, the suite that holds it to that contract, and where each runtime stands
today. MARS's side: MARS `docs/onboarding.md`, `docs/API.md` "Capability reporting"
(`contract`), `rust/crates/mars/src/runtime_contract.rs`.

## The four capability states

Every capability of every runtime is in exactly one state:

| State | Means | Who says |
|---|---|---|
| `supported` | shown to work through MARS, with evidence (a measurement or a conformance run) | MARS (`runtime_contract::verified`, or a `backends.json` declaration: `source: declared`) |
| `unsupported` | known absent, with what showed it and, where one exists, the `fallback` Mentis uses | MARS |
| `temporarily-unavailable` | the runtime has it but cannot take work now: signed out / probe failed (MARS), or quota exhausted / held (Mentis's overlay, `MentisService.runtime_contract`) | MARS + Mentis |
| `not-yet-verified` | nothing has shown it either way; **never read as support** | default |

ACP compatibility alone never makes a capability `supported`: an agent advertising
`loadSession` stays `not-yet-verified` (with `advertised`) until a run resumed. A MARS
older than the contract is read as every capability `not-yet-verified`.

Mentis consumes the contract (`mentis/core/runtime_contract.py`) instead of branching on
runtime names: `continuity.decide` does not ask a runtime with `native_resume:
unsupported` for a resume and records that the continuation is given the record-derived
context; the `capabilities` tool shows each runtime's contract by state; quota (the
runtime's own capacity report at 100%, or a hold from the record's `rate_limited`
failures) makes a runtime temporarily unavailable, and automatic selection excludes it
and says so (`execution_select`; `test_contract.py`).

## Where each runtime stands: the states MARS declares

| Capability | claude | codex | antigravity | gemini | local |
|---|---|---|---|---|---|
| native_resume | supported (`session/resume`) | supported (`session/resume`) | unsupported | not-yet-verified | unsupported |
| context_restoration | not-yet-verified | supported (record-derived) | supported (record-derived) | not-yet-verified | not-yet-verified |
| permission_enforcement | supported (`forwarded+runtime-rules`) | **not-yet-verified** (`sandbox+runtime-reviewer`) | supported (`pre-turn`) | not-yet-verified (`forwarded`) | not-yet-verified (`none`) |
| mcp_tools | supported (stdio) | supported (stdio) | supported (stdio) | not-yet-verified | not-yet-verified |
| cancellation | supported (`cooperative+kill`) | supported (`cooperative+kill`) | supported (`kill`) | not-yet-verified | not-yet-verified |
| execution_events | supported | supported | supported (translated) | **not-yet-verified** (acp) | supported |
| completion_reporting | supported | supported | supported (translated) | not-yet-verified | not-yet-verified |
| model_discovery | supported | supported | **not-yet-verified** (`agy models`) | not-yet-verified | unsupported |
| capacity_reporting | **not-yet-verified** (quota) | **not-yet-verified** (quota) | **not-yet-verified** (quota) | unsupported | **not-yet-verified** (resources) |
| delegation_coordination | supported | supported | supported | not-yet-verified | not-yet-verified |

Read from a copy of the MARS `modernize` bf6f991 release build (`_mars/backends`, no
`backends.json`; kimi-k3 is a configured runtime and is not listed). Bold: changed in
bf6f991. A state MARS declares without having shown it carries its `kind` and `source:
"mars"` (not `verified`). gemini has nothing supported. `local` was unavailable on this
machine (MARS reports its availability, not its capabilities, as such).

## What a runtime must provide (program §12)

| # | Item | Contract | Where |
|---|---|---|---|
| 1 | Adapter or transport | An ACP agent over stdio (a `backends.json` entry, no MARS code) or a per-turn CLI adapter in MARS `backends/`. Mentis talks to MARS only, over ACP; no runtime SDK is ever a Mentis dependency. | MARS `registry.rs`, `backends/` |
| 2 | Capability declarations | The ten contract capabilities, each in one of the four states, with evidence. New runtimes start `not-yet-verified`. | MARS `runtime_contract.rs`; `_mars/backends[].contract` |
| 3 | Runtime and model discovery | Listed in `_mars/backends` with `available`/`reason`; models from ACP config options or the CLI's own list; routing tiers only for exact tagged ids. | MARS probe; Mentis `runtimes_discover`, `models_list` |
| 4 | Tool and MCP access | The client's `mcpServers` passed unchanged; the Mentis bridge (`mentis`) is given to every dispatched run under its grant and must win over any user-level `mentis` registration (`mcp_isolation`, proven with a decoy). | MARS `mcp_isolation.rs` (Builder M); Mentis `mcp_servers_for` |
| 5 | Permission and sandbox enforcement | `permission_enforcement.kind`: `forwarded` / `forwarded+runtime-rules` / `sandbox+runtime-reviewer` / `pre-turn` / `none`. Mentis compiles rules only for a runtime whose kind includes `runtime-rules`; a `pre-turn` runtime is told its consent before the turn (`permissions.runtime_options`) and its tooling block says up front whether shell commands are permitted; `none` is named, never assumed safe. | MARS `consent.rs`; Mentis `web/permissions.py` (Builder A); `test_enforcement.py` |
| 6 | Session creation and optional resume | `session/new`; a resume token (`mars/resume`) only where MARS can load the runtime's own session. Resume is optional: a runtime is conformant without it. | MARS `continuity.rs`; Mentis `web/continuity.py` |
| 7 | Context restoration without resume | A fresh session continuing the same work is sent the full composition **plus** the request in full and its previous run's reply (`continuity.restoration_block`). | Mentis `dispatch` (full payload only) |
| 8 | Cancellation | `session/cancel` ends the turn `cancelled` (cooperative where the runtime has it; MARS kills what the turn started in every case). Mentis records it cancelled, never completed or met. | MARS session; Mentis Stop route |
| 9 | Execution events | Standard `session/update` notifications (translated for a CLI adapter). | MARS |
| 10 | Completion and outcome reporting | A turn ends only with the `session/prompt` answer or a MARS error kind, never process exit; the agent's final ```` ```outcome ```` block is its claim, reconciled by Mentis. | MARS contract §3; Mentis `operational/completion.py` |
| 11 | Capacity reporting | A quota reader in MARS where the runtime reports without spending a turn; otherwise `capacity_reporting: unsupported` and the record's `rate_limited` holds are the only signal. | MARS `capacity.rs`; Mentis `quota.py`, `capacity_view` |
| 12 | Durable reporting and idempotency | Every write op takes `op_key` (server dedupe per grant participant, op and key); the bridge keeps an outbox; the final-reply claim is server-side. | Mentis `opkeys.py`, `outbox.py`, bridge |
| 13 | Shared-resource coordination | `claim_resource` / `release_resource` / `resources` in every scope; conflicts refused with a structured refusal (`boundary: resource`). | Mentis `operational/leases.py` |
| 14 | Conformance testing | `tests/conformance_runtime/` offline (scripted profile per runtime) must pass; the profile's states must equal MARS's (`test_profiles_say_what_mars_declares`). | this repository |
| 15 | Live validation | `tools/runtime_conformance.py --runtime <id> --model <m> --root <throwaway folder> --mars "<mars.exe> stdio"` (or `MENTIS_CONFORMANCE_ROOT` / `MENTIS_CONFORMANCE_MARS`) against a MARS build, with evidence under `<root>\evidence` (each run's MCP report, refusals and consent included); every universal check passed, or the runtime is not conformant. | this repository |

## Steps to add a runtime

1. In MARS: add the entry (`backends.json` for an ACP agent; a built-in plus adapter
   otherwise), declare `mcp_isolation` and prove it with a decoy, and leave every contract
   capability `not-yet-verified`.
2. In Mentis: add a profile to `tests/conformance_runtime/profiles.py` with MARS's states
   and its resume behaviour (`on-new` / `per-prompt` / `none`); run
   `python -m pytest tests/conformance_runtime -q -p no:cacheprovider`. Nothing else in
   Mentis changes: no name branch is added.
3. Live: `python tools/runtime_conformance.py --runtime <id> --model <model>
   --scenarios main,failure,cancellation,continuity,delegation --port <free>
   --root <throwaway folder> --mars "<mars.exe> stdio"`, with
   `MARS_LOCAL_PYTHON` etc. as the runtime needs. Check the live Brain counts it prints are
   unchanged.
4. Record each verified capability in MARS (`runtime_contract::verified` or the entry's
   declarations) citing the evidence file; leave the rest `not-yet-verified`. Add the
   runtime's row to the matrix below.

## The conformance suite

`tests/conformance_runtime/` (offline by default; `MENTIS_RUNTIME_CONFORMANCE=<id>[:<model>]`
with `MENTIS_CONFORMANCE_MARS=<mars command>` runs the same tests live). Every scenario
drives the real HTTP server, dispatch, grants, worker door, acts, reconciliation, leases
and continuity; only the execution differs (a scripted runtime per profile, or MARS and
the real runtime). The task's STEP lines are the instructions for both.

| Group | Scenario / check | What must hold |
|---|---|---|
| universal | `main`: receive_assigned_work, use_mentis_tools, contribute_knowledge, durable_reports_op_key, claim_release_resource, resource_conflict_refused, meaningful_refusal, completion_claim, completion_reconciled | the run starts on the named runtime; `record_material` through the bridge is attributed; a write repeated with one `op_key` is recorded once; a lease is claimed and released; a conflicting claim and a release of another's lease are refused with a `boundary`; the ```` ```outcome ```` block becomes `outcome-claimed` (claimant, execution, runtime, work) and is reconciled into `expectation-met` |
| universal | `failure` | a run the runtime cannot do (a model it does not offer) ends `delivery-failed`; no claim, no met |
| universal | `cancellation` | Stop ends the run `cancelled`; no claim, no met |
| universal | `continuity`: continuity_context, continuity_claim | run 2 (after the owner answers run 1's decision) knows run 1's self-invented codeword and the owner's choice: by native resume or by restored context |
| universal | `delegation` | `delegate` records a child request; the child runs on the runtime and claims its own outcome |
| native | `native_resume` | reported, not required |
| enforcement | permission_enforcement_observed, `consent_narrowing` | what MARS applied; a narrowing halts and restarts a run holding compiled rules (Builder A's code, observed) |
| performance | timing, cancel_latency, continuation_timing | recorded, never asserted |

A runtime may be conformant without native resume. It is not conformant if it loses work,
bypasses authority or misreports completion: any universal check failed.

## Runtime-name branches in Mentis (inventory, not removed)

New code must consume the contract; these existing branches are listed for the integrator:

| Where | Branch | Kind |
|---|---|---|
| `mentis/web/permissions.py` `COMPILED_SCOPE_RUNTIMES = {"claude"}`, `runtime_rules` `if runtime == "claude"` | which runtime gets compiled rules (Builder A's; matches the contract: only claude declares `forwarded+runtime-rules`) | authority |
| ~~`mentis/web/permissions.py` `runtime_options` `if runtime != "antigravity"`~~ | removed (r2-fix): the pre-turn allow list and the tooling block's shell line read `permission_enforcement.kind == "pre-turn"` | authority |
| `mentis/core/service.py` `NAMED_ONLY = {"gemini"}` | gemini runs only when named (owner decision #1167) | selection policy |
| `mentis/execution/__init__.py` `FakeExecution` default backends | test stand-in | tests |
| `mentis/conversation/runtime_names.py` `RUNTIMES`, `MODEL_FAMILIES` | names a Participant may not take | naming |
| `mentis/web/fixture.py`, `mentis/web/__init__.py` demo bindings | fixture data | fixtures |

## Replaceable local worker boundary

The `local` runtime is MARS's own ACP agent (`python -m mars.workers.local_agent`, run by
`MARS_LOCAL_PYTHON`), today around the OpenHands SDK. Mentis never imports it: it sees
the backend id `local`, its contract and ACP. To replace it, point a `backends.json`
entry (or the built-in's argv) at any other ACP agent that serves an OpenAI-compatible
local model, keep `mcp_isolation: client-wins`, and re-run step 3 above. Nothing in
Mentis changes.

## Parity matrix

See `RUNTIME-PARITY.md` (every cell backed by a check result or marked not-run / blocked).
