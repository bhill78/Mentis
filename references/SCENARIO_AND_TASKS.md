# Shared Scenario and Standardized Evaluation Tasks — Generation 1

This document defines the single realistic Magnet scenario, representative corpus/lineage dataset, and eight standardized evaluation task scenarios (`T1`–`T8`) used identically across all six Generation 1 static Quiet UI concepts (`C1`–`C6`).

Canonical machine-readable dataset: [`shared/scenario-data.json`](shared/scenario-data.json).

---

## 1. Established Design Principles Preserved

Per the owner request (`ent-8bcfb7953748`), reviewed Perspective design (`magnet-perspectives-design-draft.md` / `magnet-perspectives-final-review.md`), and Quiet integration findings (`ent-a778e8063a6f`), every concept preserves:

- **One universal configurable Magnet** with stable `mag-` identity, configuration digest, source rules, provenance, and its own Conversation, independent of workspace placement.
- **Magnet collection vs. Perspective inquiry separation**: switching, creating, revising, or retiring a Perspective never modifies the Magnet's configuration or collected evidence.
- **Interpretations without automatic knowledge standing**: syntheses are versioned interpretations with human-auditable manifests and no numeric truth scores; they never automatically become established Brain knowledge.
- **Explicit, non-automatic agent continuation**: no background refresh or hidden token spend; continuation is initiated explicitly with visible scope, runtime, estimated cost, and authority boundaries.
- **Quiet 2 conversation-first foundation**: preserves Quiet's article typography, composer destination clarity, unsent draft protection, and reading anchor continuity.

---

## 2. Canonical Shared Scenario

### 2.1 Originating Context
- **Brain**: `DAY-TO-DAY`
- **Originating Conversation**: `Release Readiness — Checkout v4.2` (`ent-conv-rel-402`) — 18 posts, 4 participants.
- **Reading Anchor**: **Post `#14`** (`@maya`, Nov 21, 9:12 AM) referencing the Magnet because EU-West p99 tail latency threatens the v4.2 release cut in four hours, followed by Post `#15` (`@Caretaker`) noting two new traces arrived since `P1·S3` with no automatic refresh started.
- **Protected Unsent Draft** (in originating Quiet composer):
  > *"Before we freeze v4.2, @maya can you confirm whether the Redis warmup patch also covers the cold-start spike seen in SRC-04?"*

### 2.2 The Magnet (Constant Across All Perspectives)
- **Identity**: `Checkout Latency & Cache Watch` (`mag-checkout-latency`)
- **Purpose**: Collects p99 latency traces, cache-invalidation incidents, and replication-lag notes for Checkout v4.x across engineering threads and uploaded trace logs.
- **Frozen Configuration Digest**: `sha256:9f4b8e21…c218` *(must remain visibly unchanged across all Perspective switches/creations)*.
- **Sources & Filter**: 3 sources (`#checkout-ops`, `#cache-postmortems`, `traces-nov/`) · `tag:latency OR p99>450ms`.
- **Bounded Capture Disclosure**: `Bounded page 1 of 1 (200-entry cap) · 14 matched · complete corpus not claimed`.
- **Separate Activity Counters** (`ent-acf27da22438`): `1 new since you looked` · `2 new since P1·S3`.
- **Dedicated Magnet Conversation**: `Magnet: Checkout Latency & Cache Watch` (`ent-conv-mag-8841`, 9 posts, 4 participants).
- **Retention & Visibility Policy**: Run artifact until Keep (`ent-d2d095d5f325`); all-input visibility required (`ent-aded719e96c9`) — 1 restricted item (`SRC-09`) in scope, with backend enforcement honestly marked as pending.

### 2.3 Representative Curated Evidence (7 of 14 Bounded Items)

| Code | Reference | Author & Source | Edge Case Exercised |
|---|---|---|---|
| `SRC-01` | `ent-88a1c04#v2` (cited `#v1 · L12–L28`) | `@maya` · `#checkout-ops` | **Edited after citation**: `S1–S3` pin `#v1`; Turn is now `#v2`. |
| `SRC-02` | `adm-4d91e0bc7a2f` (immutable digest) | `@Atlas · codex` · `traces-nov/` | **Shared original**: cited by both `P1` and `P2`, de-duplicated (not double-counted). |
| `SRC-04` | `ent-91b4e10#v1` (`L4–L19`) | `@brian` · `#cache-postmortems` | **Contradictory evidence**: refutes `P1·S1`'s single-cause cold-start claim (`610ms` spike at 9% miss rate). |
| `SRC-07` | `ent-93c0f77#v1` (deleted) | `@maya` · `#checkout-ops` | **Deleted / unavailable**: historical edge preserved honestly in `P1·S1`, never silently dropped or treated as current. |
| `SRC-09` | `adm-7f22a910e4c1` (restricted) | `@maya` · `traces-nov/ [ops-security]` | **All-input visibility gate**: syntheses citing `SRC-09` must carry visibility warning. |
| `SRC-13` | `ent-99d2a11#v1` (`L1–L9`) | `@brian` · `#checkout-ops` | **New since `S3`**: shard-3 replica lag `420ms` during warm-cache burst. |
| `SRC-14` | `adm-b30199ef12a0` (immutable digest) | `@Louie · claude` · `traces-nov/` | **New since `S3`**: bimodal read-through jitter histogram. |

### 2.4 Three Perspectives Over the Same Magnet

1. **`P1` (Active) — `Cold-Start Latency & Cache Invalidation`** (`topic:ent-persp-p1`)
   - **Questions**: `Q1` (refined → `Q1.1` after `SRC-04` contradiction; original retained), `Q1.1` (open), `Q2` (evidence-arising from `SRC-09`), `Q3` (retired with reason: DNS ruled out by `SRC-02`).
   - **Syntheses**: `S1` (`@Atlas · codex`) → `S2` (`@Atlas · codex`) → **`S3`** (`@Louie · claude`, `ent-syn-p1-v3`), labeled *Interpretation · Not established Brain knowledge*, `Behind: 2 new`, `Restricted input: SRC-09`, `Mutual dep: P2·S1`, with full human-auditable manifest.
2. **`P2` (Active · Competing Inquiry) — `Write-Path Durability vs. Replication Lag`** (`topic:ent-persp-p2`)
   - Authored by `@maya` & `@Atlas (codex/gpt-6.1-sol)`. Explicitly **disagrees** with `P1`, cites `SRC-02` (de-duplicated) and `P1·S2`, creating a flagged **mutual dependency** (`P1·S3 ↔ P2·S1`). Does not cite `SRC-09`.
3. **`P3` (Dormant · Earlier Filter) — `Legacy Token Migration Risks`** (`topic:ent-persp-p3`)
   - No execution running; resumable from durable record. Labeled `Earlier filter` (Magnet filter updated Nov 19; historical `S1` preserved, never deleted).

### 2.5 Multi-Participant Context
- Humans: `@brian` (owner, personal filter: All 14 items), `@maya` (Staff Eng, author of `P2`, separate personal view state).
- Agents: `@Caretaker` (`codex`, coordinator), `@Atlas` (`codex/gpt-6.1-sol`, authored `P1·S1–S2` and `P2·S1`), `@Louie` (`claude/claude-opus-5`, independent runtime for `P1·S3`).

---

## 3. Standardized Evaluation Task Scenarios (`T1`–`T8`)

Every Generation 1 concept (and later Gen 2 / Gen 3 derivatives) must be evaluated against these exact eight tasks:

| Task | Owner Criteria Covered | Concrete Task Steps | What Good Looks Like |
|---|---|---|---|
| **T1 — Magnet Identity & Curated Inspection** | #1, #2 | Starting at Post `#14` in `Release Readiness — Checkout v4.2`, inspect the Magnet's purpose, stable ID, config digest (`sha256:9f4b8e21…c218`), bounded capture notice (`14 / 200`), and curated evidence list (`SRC-01`–`SRC-14`). | Magnet identity and collection bounds are immediately legible; personal view filter is distinct from shared Magnet scope; originating Post `#14` and unsent draft are never lost. |
| **T2 — Perspective Switching & Creation** | #1, #3 | Switch from `P1` to competing `P2` and dormant `P3` (`Earlier filter`), then open `+ New Perspective` to draft a new inquiry. | Visually obvious that Magnet config digest and curated collection do **not** change when switching or creating Perspectives; dormant/earlier-filter history stays intact. |
| **T3 — Evolving Questions & Synthesis History** | #4, #10 | Trace how `Q1` evolved to `Q1.1` (retaining `S1`), inspect retired `Q3` with its reason, and step through `S1 → S2 → S3`. | `S3` is unmistakably labeled as an *Interpretation* (never established Brain knowledge), shows `2 new since S3`, and preserves superseded history without silent overwriting. |
| **T4 — Provenance & Lineage Audit** | #2, #10 | Inspect `S3`'s manifest and verify all five audit edge cases: edited `SRC-01#v1→#v2`, deleted `SRC-07`, shared de-duplicated `SRC-02`, mutual dependency `P1·S3 ↔ P2·S1`, and restricted `SRC-09` visibility warning. | Every edge case is inspectable without leaving Quiet; direct originals are cleanly separated from prior synthesis interpretations; missing/restricted states are explicit. |
| **T5 — Explicit Agent Continuation** | #5, #8 | Initiate continuation of `P1` to evaluate new items `SRC-13` and `SRC-14` using `@Atlas (codex)` (independent runtime from `S3` author `@Louie`). | No automatic refresh; explicit pre-run summary shows perspective ref, destination Conversation, incremental inputs, runtime, estimated cost, and read-only/artifact-until-Keep authority before confirming. |
| **T6 — Magnet Conversation & Multi-Participant Collaboration** | #6, #8 | Open Magnet Conversation `ent-conv-mag-8841`, read posts `#6`–`#9` from `@maya`, `@Atlas`, `@Louie`, `@brian`, and prepare a reply addressed to `@Atlas`. | Distinct human vs. agent runtime attribution; Magnet Conversation is clearly distinguished from originating Conversation; originating unsent draft remains isolated and intact. |
| **T7 — Return to Originating Conversation** | #7 | From deep inside `P1·S3` or Magnet Conversation, return to `Release Readiness — Checkout v4.2` at Post `#14`. | One obvious action restores exact reading anchor `#14`, intact unsent draft (`Before we freeze v4.2…`), and resets composer destination unambiguously to the originating Conversation. |
| **T8 — Narrow-Screen Completion (`390×844`)** | #9 (plus #1–#8) | Repeat `T1`, `T3`, `T5`, `T6`, and `T7` at `390px` viewport width. | Zero horizontal overflow, readable Quiet typography, accessible tap/keyboard controls, clear orientation cue, and unmistakable return to originating Post `#14`. |
