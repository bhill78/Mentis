# Explainable refusals (WS-I)

Every refusal below is now a structured `NotPermitted` (`mentis/refusal.py`): `op`,
`boundary`, `why`, `recovery` (supported next calls) and `who` (who can lift it). The door
answers it as a 403 with `{error, kind, refusal: {...}}`. The worker client rebuilds the
fields (`worker._over`), and the MCP bridge renders each one on its own line
(`refusal.render`). A refusal raised with words only behaves as it always did.

"Layer" says whether the boundary sits where it should, as judged while converting it.

| # | Where (this branch) | Investigation ref | Op(s) | Boundary | Recovery offered | Who can lift it | Layer assessment |
|---|---|---|---|---|---|---|---|
| 1 | `web/__init__.py` `/api/worker` admission | 3104 | any op the scope does not list | scope | `contribute` (sessions), `delegate` (where held), return the need | owner, via a request granting it | **Right.** One door decides admission from the grant. The words stay identical because the Rust front and `permission_matrix.json` hold them. Fields are added beside them. |
| 2 | `worker._operation` preamble: grant names no Participant | 4990 | every act | scope | use reads; report it | whoever dispatched the run | **Right, but late.** A grant without a Participant could be refused when it is minted. It is kept here because Quick Ask grants legitimately have none. |
| 3 | `under` on a dispatched run, or on an op that does not take it | 5009 | any | lineage | call without `under` | n/a | **Right.** `SESSION_UNDER` lists which ops take `under`. |
| 4 | `under` names work no session recorded | 5009 | any `SESSION_UNDER` op | ownership | `record_request` then `under`; `contribute` | owner | **Right.** |
| 5 | **New:** session coordination without `under` | (WS-I) | `delegate`, `summon_participant`, `attach_follow_up`, `change_workflow`, `resume_intake` | coordination | `record_request` → `under=<its expectation>`; `contribute(kind="proposed-work")` | owner, by asking for the work | **Right, per call.** `permitted` is per-grant and static, but `under` is per-call, so the gate lives at the operation. The ops stay listed (tools/list and Rust parity unchanged). |
| 6 | `_where` | 5051 | `delegate`, `summon_participant`, `open_topic`, anchors | place | name the dispatched Conversation; `open_conversation`; return the need | whoever may act there | **Right.** |
| 7 | `_somewhere` | 5062 | session `open_topic`/`summon`/`delegate` without a Conversation | place | `open_conversation`, or `under` | — | **Right.** This was the good model that the others follow. |
| 8 | `take_up` without `under` | 5180s | `take_up` | lineage | `take_up(..., under=...)` | — | **Right.** |
| 9 | `take_up` outside follow-up permission | 5190 | `take_up` | governance | return to the carried request; `contribute(proposed-work, regarding=[finding])` | owner | **Right layer for the refusal.** The policy itself is `operational.pursuit_permitted`. The new recovery gives the agent a way to put the finding to the owner. |
| 10 | `record_outcome` on work no session recorded | 5243 | `record_outcome` | ownership | `record_outcome` on a session's request; `contribute(..., regarding)` | the work's carrier | **Right.** Now accepts any session participant (see Deviation D-I3). |
| 11 | `change_workflow`: no request / not a session's / no `coordinate` | 5387 | `change_workflow` | lineage / ownership / coordination | name the request; `request_decision` | owner | **Right.** `workflow_change.check` refusals are left as words (validation of the Workflow itself). |
| 12 | `timer` with no carried request | 5713 / `timers.py:307` | `timer` | lineage | leave it to the owner; say so in the answer | owner | **Duplicated.** The worker check comes first. `timers.check` (a `Refused` dict) is the real rule and is also reached by the owner's routes. The worker check is converted. `timers.py` is left as is, so its own refusal still arrives as words. Recommended: move the structure into `timers.py` and drop the worker copy. |
| 13 | `record_discovered_work` with no request (**the incident**) | 5803 | `record_discovered_work` | lineage | `contribute(kind=problem\|finding\|proposed-work, ...)`; `record_request` → `record_discovered_work(..., under=...)` | nobody needs to: both are open | **The boundary was right and the surface was wrong.** Discovered work must have a parent. What was missing was a way for a requestless session to report a finding, and `contribute` is that way. The refusal now names it. |
| 14 | `return_artifact` with no request | 5855 | `return_artifact` | lineage | name the path in the answer | — | **Right.** Sessions are not shown it (`SESSION_CARRIED`). |
| 15 | `resume_intake` without `coordinate` | 5977 | `resume_intake` | coordination | leave it to whoever coordinates | owner | **Right.** For sessions, gate 5 now comes first. |
| 16 | `attach_follow_up` without `coordinate` / without a parent | 6003 | `attach_follow_up` | coordination / lineage | carry it; say it in the reply | owner | **Right.** |
| 17 | Ladder refusals (`requires_basis` and the rest) | `ladder_writes.py:146` | `record_material`, `propose_material`, `challenge`, ... | validation | `basis=[...]`; `contribute(observation)` needs none | — | **Rule right, structure late.** `ladder_writes` raises `ValueError`, and the worker converts it, adding a basis recovery when the words name `requires_basis`. Recommended: `ladder_writes` raises structured refusals itself. |
| 18 | **New:** `op_key` malformed, or reused for a different write | (WS-I) | any write | validation | resend with a new key | — | Right (`mentis/opkeys.py`). |
| 19 | **New:** `contribute` arguments; `authorized_by` malformed | (WS-I) | `contribute`, any session write | validation | the call's shape | — | Right. |
| 20 | **New (review):** session bound as a Participant it is not (`session_identity.resolve`) | (review) | session start | ownership | omit `--participant`; pick a new name | the owner | **Right.** Decided once, at the session route, from the record. |

## Gaps

- Of the 162 `raise NotPermitted` in `worker.py`, the ones above are converted. The rest still
  raise words only. They render as before and carry no `refusal` field.
- The Rust front's `refused_body` (for the moved reads it answers itself) carries no `refusal`.
  That path is unreachable today, because every scope may ask every moved read
  (`test_every_scope_the_mirror_holds_may_ask_all_six_moved_reads`).
- `delegate`'s operation key is written just after the delegation, not in its transaction,
  because it consults the agent service. A per-key in-process lock makes a concurrent resend
  wait for the first send. A crash in the gap between the two commits would let a resend
  delegate again.
