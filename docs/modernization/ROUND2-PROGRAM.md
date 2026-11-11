# Round 2 — the owner's program (verbatim, 2026-11-10)

Source: the owner's pasted task "Mentis Mark IV / MARS — Final Modernization Integration,
Runtime Parity, and Release Preparation". Kept here so every builder and reviewer works from
the owner's own words. Plan and ownership: `ROUND2.md`.

## Owner authorization

I approve all ten decisions (O1–O10) from the November 10 **Mentis/MARS Modernization — Candidate Review**, subject to the governing requirements below.

The modernization candidate currently exists on Mentis `modernize` — `687d2fd` and MARS `modernize` — `82fdbf2`. Continue from these candidates. Preserve their completed work and evidence. **Do not restart the modernization from scratch or repeat investigations already resolved by evidence.**

The objective is to complete the integration, establish runtime parity, resolve remaining correctness and capability issues, and prepare one production-ready Mentis/MARS release.

## 1. Governing principles

### 1.1 Preserve and expand authorized capability
The modernization must not unnecessarily restrict what I or my agents can accomplish within the authority and permissions I have granted. Preserve the distinction between: runtime capability (what the runtime can technically perform); execution availability (what tools and environments are available); owner authorization (what the agent is permitted to do); provenance (who performed the operation and under whose authority).

An agent operating within its authorized scope should be able to use its available capabilities without unnecessary Mentis intervention. Do not preserve accidental overbroad authority merely because it existed previously. Instead, preserve legitimate functionality through correctly authorized operations. If a proposed restriction would remove an existing legitimate capability, provide an authorized path that preserves that capability. If this requires changing the owner's intended authority boundary, stop and request a specific decision.

### 1.2 Runtime independence
**Mentis must not become a Claude-centric agent system.** Claude, Codex, Antigravity, Kimi/K3, supported local models, and future runtimes must participate in the same Mentis work, knowledge, authority, coordination, and reporting system. Equivalent Mentis functionality is required. Identical runtime implementations are not. A runtime's native limitations must be represented accurately, with supported fallback behavior where possible. Do not silently remove functionality because a runtime lacks a Claude-specific feature.

### 1.3 Correctness before optimization
Performance improvements must preserve authorization, provenance, context correctness, completion semantics, and durable work history. Do not sacrifice correctness or necessary context to reduce latency, token consumption, or implementation complexity.

### 1.4 Preserve long-running project continuity
Preserve the relationship between original requests, work ownership, authority, execution, completion claims, supporting evidence, independent verification, later defects/corrections/challenges, epistemic records and decisions. The work must remain understandable and recoverable when the original agent or runtime is no longer available.

## 2. Integrate the existing modernization candidate
Preserve: completion claims for all agent scopes; completion reconciliation; historical provenance and later findings; runtime session continuity; startup and capacity improvements; compiled permission rules; independent CLI contributions; structured refusals; resource leases; durable reporting and idempotency; accurate execution and work states. Do not replace these mechanisms without evidence that they fail a required contract. Integrate against the actual DAY-TO-DAY release lineage (includes Quiet Chat round 5, absent from main). **Preserve Quiet Chat round 5 and all subsequent production functionality.**

## 3. O1 — Release lineage and deployment preparation
Verify: existing production functionality preserved; Mentis and MARS use compatible commits; frontend and backend release identities match; existing rollback path remains available; the release does not recreate the unbounded Brain-copy accumulation defect. Use a bounded backup and rollback arrangement. Do not create another series of full disposable Brain copies.

## 4. O2 — Consent narrowing and automatic restart
Approved when the work remains authorized. Requirements: narrowing takes effect against the active execution; the old execution is halted before replacement work proceeds; the replacement receives the new consent and current authority; new owner instructions and Workflow changes are preserved; explicit owner Stop or withdrawal is never overridden; restart limits prevent loops; unrestartable work appears in Needs You with its actual reason; parent work does not incorrectly complete while a required child is interrupted. Do not restart merely because a runtime ended normally. Preserve the distinction between interruption, cancellation, failure, and completion. Investigate and verify the remaining consent-narrowing window identified in the candidate report.

## 5. O3 — Compiled permission rules
Approved for Claude: Approve All; Mentis's own tools under existing authorization. All other operations continue through existing enforcement unless equivalent enforcement has been demonstrated. Requirements: no unauthorized permission widening; protected and secret paths remain protected; owner escalations remain synchronous; consent narrowing invalidates outdated execution authority; automatic permission auditing remains durable and ordered; refusals remain explainable; runtime-specific permission behavior is explicitly tested. Do not extend compiled permissions to filesystem edits, shell commands, or additional runtime operations without equivalence evidence. Resolve the observed Claude `sleep`/`echo` behavior sufficiently to establish what is controlled by Claude itself and what Mentis can enforce. Do not claim that Mentis controls a command category that the runtime can execute without consulting it.

## 6. O4 — CLI authority and legitimate independent work
Approved: narrow the default coordination authority of hand-started CLI sessions. An independent session must retain the ability to: execute ordinary local work through its native runtime; use authorized tools; read permitted Mentis knowledge; contribute attributed findings; create requests through supported operations; carry work it is authorized to carry; obtain coordination authority when explicitly granted by the owner. Do not require an unrelated Mentis request merely to contribute knowledge. Do not convert every independent CLI session into an internally dispatched Mentis agent. Preserve the distinction between execution authority and coordination authority.

## 7. O5 — Session identity and attribution
Approved: distinct CLI contributor identities replace pooled `@ManualSession`. Preserve historical records; record actual execution and runtime; distinguish separate sessions even on the same host; record the contributor separately from the authorizing party; prevent impersonation of the owner or configured agents; do not treat a client-claimed host name as verified identity; preserve correct provenance across retries and reconnections. Design so future independent runtime hosts can participate without changing the Mentis work model.

## 8. O6 — Completion, reconciliation, and accountability
Approved for every agent, including delegated children and worker-scope agents, without organising authority. Preserve met/partly met/not met claims; evidence references; claimant, execution, runtime and work identity; reconciliation against actual completion requirements; open decisions and dependencies; required independent review; parent/child relationships; historical claims and later findings. Distinguish: 1 execution ended; 2 agent replied; 3 agent claimed completion; 4 Mentis recorded the objective met; 5 independent verification passed; 6 later evidence challenged the original result. A claim is not independent verification. A normal runtime exit is not a completion claim. A later bug does not automatically establish that the original claim was false. Preserve the ability to trace later defects and fixes back to earlier work and completion evidence. Reserve green styling for actual met or verified work.

## 9. O7 — Background capacity and durable delivery
Approved: activity-bound backend/capacity refresh and client-side outbox recovery, kept bounded — not uncontrolled watchdogs, polling loops, or unnecessary background services. Update applicable `AGENTS.md` guidance to distinguish approved runtime-maintenance and durable-delivery behavior from prohibited uncontrolled retry mechanisms. Preserve correct quota-aware runtime selection. An exhausted runtime, such as K3 when its quota is unavailable, must be represented accurately rather than silently selected as available.

## 10. O8 — MCP configuration and capability preservation
Approved: explicit MCP configuration for dispatched sessions. Maintain strict isolation for MARS internal probe, catalogue, and usage-check sessions. For actual agent execution sessions: preserve access to authorized user-level MCP capabilities; prevent accidental connections to the wrong Brain; ensure Mentis's bridge points to the intended Brain and execution context; do not silently remove tools made available by the owner; preserve runtime-specific supported tools; report unavailable capabilities accurately. Do not solve the background MCP exposure by disabling legitimate tools for all dispatched agents. Establish a controlled configuration mechanism that provides the appropriate authorized tools to each execution.

## 11. O9 — Runtime parity and live verification (release gate)
Universal Mentis capabilities — every supported runtime must be able to: receive assigned work; execute within its granted authority; report completion outcomes; preserve completion evidence and provenance; contribute knowledge; use supported Mentis tools; participate in authorized delegation and coordination; claim and release shared resources; report execution status and failure; support cancellation; preserve durable reports; receive meaningful capability and authorization refusals.

- **Claude**: verify compiled permissions, session resume, completion claims, knowledge contribution, resource leases, cancellation, durable reporting, consent changes.
- **Codex**: live verification of execution and completion claims; native session resume where supported; sandbox and permission behavior; MCP tools; delegation and coordination; cancellation; resource leases; durable reporting; correct attribution. Do not assume Claude's permission or session behavior applies.
- **Antigravity**: execution and completion claims; fresh-session continuation with correct context; pre-turn authorization rules; tool availability; cancellation; resource coordination; durable reporting. No native resume: preserve continuity through record-derived context; do not claim unsupported native resume.
- **Kimi / K3**: verify the installed runtime adapter and capability contract. K3 is currently out of capacity. Do not waste time repeatedly attempting unavailable model calls. Run all available offline and contract tests. If capacity becomes available, perform live verification. Otherwise report live verification as capacity-blocked, not passed or failed.
- **Local models**: verify the existing local-model worker against the same universal contract: tool access, completion reporting, knowledge contribution, authorization boundaries, cancellation, durable reporting, resource coordination. Use supported local models and existing local infrastructure. Do not make OpenHands or any particular local-model SDK a permanent Mentis architectural dependency. Preserve the replaceable worker boundary.

## 12. Future runtime onboarding
Establish a reusable MARS runtime-onboarding contract; a future runtime must join without a new work model, epistemic model, or authorization system. Define: 1 runtime adapter or supported transport; 2 capability declarations; 3 runtime and model discovery; 4 tool and MCP access; 5 permission and sandbox enforcement; 6 session creation and optional resume; 7 context restoration when resume is unavailable; 8 cancellation; 9 execution events; 10 completion and outcome reporting; 11 capacity reporting; 12 durable reporting and idempotency; 13 shared-resource coordination; 14 conformance testing; 15 live validation requirements. Capabilities must distinguish: supported; unsupported; temporarily unavailable; not yet verified. Do not infer support from ACP compatibility alone. Keep runtime-specific behavior inside MARS adapters wherever possible; Mentis consumes a stable capability and execution contract rather than branching on runtime names.

**Conformance suite**: implement a reusable runtime-conformance suite; run the same behavioral contract tests against each available runtime. Separate universal Mentis requirements; optional native capabilities; runtime-specific enforcement; performance measurements. A runtime can be conformant without native resume. A runtime cannot be conformant if it silently loses work, bypasses authority, or misreports completion.

## 13. O10 — Quiet Chat
Not part of this implementation. Do not modify `quiet-mark-2` or resume Quiet Chat feature development. Document new backend states/fields in `docs/modernization/QUIET-CHAT-INTERFACE.md`. No earlier Quiet Chat cutover milestone.

## 14. Performance verification
Baseline: managed startup 18.8 s p50; native 1.9 s p50; repeated fresh sessions for continuations; frequent synchronous permission round trips; repeated capacity checks. The candidate's ~2.2 s warm startup on a small test Brain does not establish production performance. Measure: cold and warm startup; p50 and p95; continuation latency; session reuse and context preservation; cache and token behavior; permission round trips; tool-call latency; total task duration; runtime failure and cancellation behavior. Test under representative development load where possible. Report separately per runtime. Do not claim Claude improvements apply to other runtimes.

## 15. Integration and review
Use existing branches and infrastructure; parallelize; assign clear ownership of shared interfaces and files; one coherent integrated candidate. No additional persistent Brains, full Brain copies, unnecessary preview servers, or abandoned worktrees. Run: focused tests; runtime-conformance tests; permission-equivalence tests; completion and provenance tests; concurrency and lease tests; crash and retry tests; independent code review; integrated Mentis regression suite; MARS regression suite; frontend build and type checks where affected. Verify the two pre-existing Brain-lock test failures remain unchanged, or resolve their environment requirements if available without expanding product scope. Do not report unexecuted tests as passed.

## 16. Required final evidence
A release identity; B runtime parity matrix (universal contract, native resume, permission enforcement, tool/MCP availability, completion reporting, durable reporting, cancellation, concurrency, live verification, capacity limitations, known deviations — for Claude, Codex, Antigravity, Kimi/K3, local models); C performance; D completion and accountability; E authorization; F reliability; G future onboarding; H review; I deployment (exact candidate, rollback arrangement, deployment procedure).

## 17. Completion and deployment boundary
Proceed with implementation, integration, testing, independent review, and release preparation. **Do not deploy to DAY-TO-DAY, restart production, merge into production, or enable production mutations until the final integrated candidate is presented for explicit release confirmation.** Do not declare runtime parity when a supported runtime has not met its universal contract. Do not conceal capacity-blocked or unverified cases. If a runtime cannot provide an optional native capability, preserve the appropriate supported fallback. If a legitimate authorized capability would be lost, stop that change and report the specific conflict. Do not begin Quiet Chat daily-use cutover.
