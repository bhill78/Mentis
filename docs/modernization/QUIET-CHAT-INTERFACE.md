# Quiet Chat Mark 2 — interface changes from WS-C (completion and accountability)

Documentation only. Quiet Chat (`apps/fluid-web/src/quiet*`, branch `quiet-mark-2`) is not
changed by WS-C. This file lists the server fields and values that changed or were added, and
what Quiet Chat's presentation needs to do to stay true to the record. The binding rules are
in `CONTRACT.md`, WS-C.

## What changed in meaning

A run ending no longer reads as completion anywhere on the server.

- **A claim is a new, separate fact.** An agent claims an outcome by ending its final reply with
  a fenced ```` ```outcome ```` block, through `respond(outcome=…)` / `respond(fulfils=true)`, or
  through `record_outcome`. It is recorded as the act **`outcome-claimed`**.
- **`expectation-met` is written only by reconciliation** for these paths
  (`mentis/operational/completion.py`). Its `detail.reconciled_from` names the claim and
  `detail.claimed_by` names the execution. The system paths that already wrote
  `expectation-met` are unchanged: owner closes, decision withdrawals and lapses, answers, and
  permission questions. **`satisfied_by` on an expectation therefore still means "recorded
  met"**, but for agent work it is now set only after the checks pass. It is no longer set
  immediately while the run is still going: a `respond(fulfils)` made during a run is recorded
  met when that run ends.
- A claim of met that the checks hold back is recorded as **`outcome-pending`**, with
  `detail = {claim, reasons[], notes[]?}`. Its `about` is `[expectation, claim]`.

## Act shapes (new)

`outcome-claimed`, with `about = [expectation]` and `caused_by = expectation`:

```
detail: {
  result: "met" | "partly" | "not-met",
  summary: str,
  evidence: [str],
  claimed_by: <execution id> | null,
  runtime: str | null,
  participant: <participant id>,
  via: "reply" | "respond" | "record_outcome",
  reply_turn: <Turn id> | null,       # the reply that carried the claim
  ...unknown keys from the block are kept (because, result_kind, results, …)
}
```

`outcome-pending`, by actor `mentis`: `detail: {claim: <outcome-claimed id>, reasons: [str],
notes?: [str]}`. Each reason is a short phrase, for example `its run has not ended yet`,
`its run failed after the claim`, `decision opr-… is open`, `input opr-… is awaited`,
`child opr-… has not ended`, `awaited work opr-… has not ended`, or `review required`. A
note of the form `child opr-… not met` is informational and blocks nothing.

The link relation **`regards`** (inverse `regarded-by`) runs from a later record (a material
entry, a discovered-work Turn, a `disputes` link, or a WS-I contribution) to an expectation,
an `outcome-claimed` act or a Turn. It is neutral.

## Posted reply text

When a run's final text (or a `respond` text) **ends** with a top-level outcome block, the
posted reply **does not contain the block**. A block mid-reply, inside another fence or in a
quote is left as text and is not a claim. The reply's last paragraph is one line instead,
attributed to the agent, with the agent's words markdown-escaped and clipped:

```
Claim by @Ada: met — <summary> · evidence: <e1>; <e2>; … (+N more) (the agent's claim; what Mentis recorded is shown with the work)
```

`met` is shown as `met`, `partly` as `partly done`, and `not-met` as `not met`. This line is the
agent's words and never Mentis's verdict. What was recorded comes from the record: the
`outcome-pending` / `expectation-met` acts, `claim.recorded` on work items, and the state words.
Quiet Chat should draw the recorded state from those, and never parse this line.

## Run state (`runs.run_state`, `/fluid/api/runs`, `/api/working`, activity feeds)

| Before | Now |
|---|---|
| `state: "completed"`, `words: "completed · <time>"` | `state: "ended"`, `words: "ended · <time>"` |

Every other run state is unchanged (`recovered`, `stopped`, `failed`, `superseded`, live
states).

**Quiet Chat needs these changes:**
- `quiet2/activity/records.ts`: `ENDED = new Set(['completed', …])` must include `'ended'`.
  Keep `'completed'` while the server is older.
- `quiet2/GlobalDock.tsx` (~line 299): `run.state !== 'completed'` should also treat
  `'ended'` as the plain case.

## Work overview (`/api/work/overview`, `operational/work_overview.py`)

`state` (the `trunk_status` value) has new values. The `status_words` (and the drawer's
`heading`) are exact:

| `state` | `status_words` | `heading` | `group` |
|---|---|---|---|
| `claimed-met` (now only reconciled for agent claims) | `Objective met · claimed by <who>`; a met no claim reconciled: `Objective met` or `Objective met · marked by <participant>` | `OBJECTIVE MET` | `completed` |
| `verified` (new; only review work of this work, by someone other than its claimants) | `Verified · <reviewer>` | `VERIFIED` | `completed` |
| `claim-pending` (new) | `Claimed met · pending: <first reason>` | `CLAIMED MET — PENDING, NOT COMPLETE` | in flight / returned (as ended work) |
| `claimed-partly` (new) | `Partly done · <summary>` | `PARTLY DONE — NOT COMPLETE` | as ended work |
| `claimed-not-met` (new) | `Not done · <summary>` | `NOT DONE — NOT COMPLETE` | as ended work |
| `returned` (no claim) | `Ended · no outcome claimed` (was `Ended · not marked complete`); a delegated child's own state: `Returned to <parent carrier>` | `ENDED — NO OUTCOME CLAIMED` | as ended work |

`objective_met` is true for `claimed-met` and `verified`, and false for every other value.

**Stage words** (`stage_words`): ended work never reads `Answered`. Met work reads
`Objective met` (was `Answered · objective met`). Ended work that is not met reads `Ended`,
`Ended · no outcome claimed`, `Ended · recovered, no outcome claimed`, `Ended · replied, no
outcome claimed`, or `Ended · <claim words above>`. `WORDS["ended"]` is now `"Ended"`.

**New fields on every work item:**
- `claim`: `null`, or `{act, result, summary, evidence[], claimed_by, participant,
  participant_alias, via, at (ISO), recorded: "met"|"pending"|"partly"|"not-met"|null,
  reasons[]}`. This is the newest claim about the work and what reconciliation made of it.
- `later_findings`: `[{id, kind, at}]`. These are records linked `regards` to this work: to the
  expectation, to a claim about it, to its own Turn, or to a claim's reply Turn. `kind` is the
  entry's Kind or the act name.

Each child in the `trunk_status` children items gets `words: "Returned to <parent carrier>"`
when it ended with no claim.

## Presentation Quiet Chat Mark 2 will need

1. **"Replied, not marked complete" must be neutral, not `--ok`.** `quiet2/status/status.css`
   line 31 inks `.q2-st-ear-replied` (and its swatch) with `var(--ok)`. A reply is not
   completion, and with WS-C a run ending is explicitly not completion either. The `replied`
   ear and swatch should use a neutral ink, such as the one used for "addressed".
   `.q2-st-ear-completed` and `.q2-st-p-completed .q2-st-word` may keep `--ok`, because
   `completed` there is `satisfied_by`, which is now the reconciled (or system) met.
2. **Words.** `status.ts` / `DogEar.tsx` say "Says it is complete" / "Completed" for
   `satisfied_by`. Those words remain true. For agent work, they now mean "claimed and
   recorded met after the checks". A claim that is pending, partial or not met does **not**
   set `satisfied_by`, so today's Quiet Chat shows such work as `replied`. To show it, read the
   claim from the post's acts (the inspector's `operational`, `/api/turns?ids=`). There,
   `outcome-claimed` and `outcome-pending` appear among the acts caused by the expectation.
   Then word it with the strings above: `Claimed met · pending: …`, `Partly done · …`,
   `Not done · …`.
3. **Run badges.** Any `--ok` ink keyed on run state `completed` or `recovered` must become
   neutral. Fluid made the same change in `fluid/fluid.css` (`.fw-run-ended`,
   `.fw-run-completed`, `.fw-run-recovered` → `--text-dim`). `--ok` is reserved for work that
   is recorded met or verified.
4. **Later findings.** These are optional. A post or work item may list `later_findings` as
   neutral "noted later" links. They never change the status mark.

## Not changed

- `_expectation_view` (the Turn view's `expectations[]`) gains no field in WS-C. It still
  carries `satisfied_by`, `response_present`, `live_execution`, `failures`, and the rest.
  Adding `claim` there is a possible follow-up. It was not added because the Turn view is on
  the hot read path that WS-P is working on.
- Group names (`needs_you`, `in_flight`, `completed`, `returned`, `unknown`) and the Fluid
  home placements (`needs-you`, `in-flight`, `completed`, `ended`) are unchanged.

## Round 2 — A (authority): fields a client may read

- `GET /api/runs/<run>/consent` → `consent.enforcement = {by, enforced, words,
  runtime_rules?}` (`mentis.web.permissions.enforcement`), read from what MARS reported it
  applied (`consent.applied.enforced_by`). `enforced` is true only for `client`,
  `sandbox+client` and `sandbox`; `none` (MARS `local` in full access) and an unreported
  enforcement are **not** enforced and must never be shown green or as "consent enforced".
  Every run now tells MARS its consent (even with no owner consent: `ask`, no workspaces), so
  `applied` is present for every run MARS opened.
- `GET /api/session-grants?request=<expectation>` → `{grants: [act...]}`: the owner's grants
  in force letting a hand-started CLI participant carry that request
  (`session-coordination-granted`; revoked by `session-coordination-revoked`). Owner-only
  `POST /api/session-grants {participant, request, because}` / `{revoke, because}`. Neutral
  wording ("<CLI participant> may carry this, granted by the owner"); nothing about it is met
  or verified.
- New operational acts: `session-coordination-granted`, `session-coordination-revoked`
  (actor: the owner). Acts written by a hand-started session now always carry its
  `execution` and `runtime` columns (before, an expectation or a Conversation it opened had
  none).

## Round 2 — E (enforcement): fields a client may read

- A run's tooling record (`runtime_evidence.tooling` on its end act) adds
  `escalations_to` (`"client"` when Mentis decides the run's requests to leave its sandbox,
  else null) and `secrets_refused` (how many secret files by name the runtime was told to
  refuse, by exact path; 0 when none).
- Consented codex runs now produce `operation-answered` acts for their escalations (commits
  "allowed by task", Mentis tool calls "allowed by grant", refusals "refused by owner") where
  Codex's own reviewer answered unrecorded before. A codex permission question may now read
  as the command the wrapper runs ("Reach the network with curl") instead of "a shell command
  Mentis cannot read safely".
- `runtime_evidence.denied` may name an agy `read_file` of a secret file
  ("Matches user-configured deny rule").
