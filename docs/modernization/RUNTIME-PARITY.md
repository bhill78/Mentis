# Runtime parity matrix (round 2, 2026-11-10)

Every cell is a check result from `tests/conformance_runtime` (offline: scripted profile;
live: `tools/runtime_conformance.py` against MARS `r2-parity` release build, fixture Brain,
fixture server on 8841-8847) or is marked not-run / capacity-blocked. Evidence files (text,
small): `C:\Work\Mentis-Test-Server\r2-parity\evidence\<runtime>-<stamp>.{md,json}`. The
live Brain was counted read-only before and after every live run: unchanged in all of them
(entry 47276, operational 80829).

Offline: all 44 tests pass for all five profiles (claude, codex, antigravity, kimi-k3,
local), including the check that the profiles' contract states equal MARS's.

| | Claude (sonnet) | Codex (gpt-6-luna) | Antigravity (gemini-3.8-flash-medium) | Kimi / K3 | Local (qwen3.5:9b via Ollama, MARS `local` worker) |
|---|---|---|---|---|---|
| **Universal contract** | **passed, every check** (claude-20261110-221050 main; -220551 failure, cancel, continuity, delegation) | **passed, every check** (codex-20261110-221050; -221736 continuity) | **passed, every check** (antigravity-20261110-221200) | **capacity-blocked** (one attempt, see below); offline passed | **not conformant live**: main failed (OpenHands `stuck`, twice: local-20261110-221113, -221736 `main_single`); failure, cancellation, continuity passed; delegation child ran but did not claim |
| Receive assigned work / use Mentis tools | passed | passed | passed | blocked | partial: `request_decision` and the claim worked (continuity); the six-step main never got past step 1 |
| Contribute knowledge (`record_material`) | passed | passed | passed | blocked | failed (main) |
| Durable reports (`op_key` repeat recorded once) | passed | passed | passed | blocked | failed (main); not-run in `main_single` (an SDK stuck detector stops identical repeated calls) |
| Leases: claim/release, conflict refused | passed | passed | passed | blocked | failed (main) |
| Meaningful refusal (`boundary` named, nothing changed) | passed | passed | passed | blocked | failed (main) |
| Completion claim + reconciliation | passed | passed | passed | blocked | passed in continuity; failed in main/delegation child |
| Failure → failed, never completed | passed (`backend_unavailable` model) | passed | passed (`backend_error`) | n/a | passed (`backend_error` NotFound) |
| Cancellation → cancelled, no claim | passed, 1.0 s | passed, 1.0 s | passed, 1.0 s (kill) | not-run | passed, 3.0 s |
| Continuity (prior context carried) | passed (native resume) | passed (native resume after the fix; restored context before it) | passed (restored context) | not-run | passed (restored context) |
| Delegation / coordination | passed | passed | passed | not-run | failed (child did not claim) |
| **Native resume** | supported: `session/resume`, resumed | supported after the MARS fix (`acp.rs target_mode`): before it, `set_mode default` was refused and every codex continuation opened fresh | unsupported (no agy resume), fallback verified | not-yet-verified | unsupported, fallback verified |
| **Permission enforcement** | `forwarded+runtime-rules`; MARS applied `enforced_by client`; consent narrowing halted the run and restarted it fresh (claude-20261110-221050) | `sandbox+client`; Mentis compiles no rules; observed only | `pre-turn`; no mid-run asking; see deviation 2 | forwarded (declared, unverified) | `none` in full access: consent cannot be enforced there |
| **Tool / MCP availability** | Mentis bridge via client-wins | Mentis bridge via `isolate` | Mentis bridge via private home; MARS allows `mcp(mentis/*)` | `client-wins` (MARS-measured), unverified here | bridge offered; model largely failed to use it |
| **Durable reporting** | op_key passed; claim server-side | passed | passed | blocked | failed / not-run |
| **Concurrency** | claude, codex, antigravity and local live suites ran at the same time against separate servers and MARS processes without interference; no same-runtime concurrency test was run | same | same | not-run | same |
| **Live verification** | done | done | done | capacity-blocked | done, failing |
| **Capacity limitations** | `/usage` 7-day 15% | rollout 16% | Gemini models 1%; Argon High not used | MARS reads no quota (capacity_reporting unsupported); out of capacity per owner | local resources only |
| **Timing (perform, s)** | 13.9 main; 3.6 resumed continuation; MARS open 1.9-2.2 | 34.5 main; 20.7 fresh continuation | 29.2 main; 9.7 continuation | 5.5 (empty turn) | 164.6 main (stuck); 29.3 continuation |

## Known deviations and open items

1. **K3 out-of-capacity is not reported as `rate_limited`.** The single K3 attempt (kimi-k3-20261110-221211)
   ended `end_turn` with no output after 5.5 s. MARS reported no error kind, so Mentis
   recorded it `delivery-failed` "nothing reported" (correct: not completed), but wrote **no
   quota hold**, so automatic selection can pick K3 again. Capacity cannot be read without a
   turn (`capacity_reporting: unsupported`). Marked capacity-blocked on the owner's word, not
   proven. Needs a captured K3 ACP stream (one more call, the owner's decision) to map its
   quota error in MARS.
2. **Antigravity refuses MCP tools the owner's agy `permissions.allow` does not list**
   (Builder M's finding, with M's per-execution MCP assembly). On r2-parity MARS writes
   `mcp(<name>/*)` into the private home's allow list for every client-passed server
   (`agy.rs::mcp_config`, `settings_json`), which is why the Mentis tools work; user-level
   servers M's assembly adds are not in that list. Fixable either in MARS (allow every
   server written to the private home's `mcp_config.json`) or through `mars/options` `allow`
   from Mentis `permissions.runtime_options` (Builder A's code). Reported to the integrator,
   not changed.
3. **Local worker with qwen3.5:9b fails the multi-step tool task** (OpenHands `stuck`) and a
   delegated child ends without a claim. Mentis records both honestly (failed / unclaimed),
   so nothing is misreported or lost, but the runtime does not meet the universal contract
   live. Previous evaluation (local-llm-eval/REPORT.md) found the same reliability ceiling.
4. **Codex native resume** was broken before this round's MARS fix (mode reset to a
   `default` mode codex-acp does not have). Fixed and verified (codex-20261110-221736).
5. **Context restoration** was missing before this round: a fresh session continuing work
   saw only the resume text and a one-line preview of the original request. Fixed in Mentis
   (`continuity.restoration_block`); antigravity, codex (pre-fix) and local continuations
   pass on it.
6. **Claude auto-approves some shell (echo, sleep) without asking** (round-1 finding,
   unchanged): Mentis does not control that category on Claude.
