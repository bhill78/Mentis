# Approval and actionable follow-ups

Present work for approval with an ordinary owner decision. `respond` accepts
`outcome.approval`; `record_outcome` accepts `approval` alongside its result:

```json
{"text":"The candidate is ready for your decision.",
 "outcome":{"result":"met","summary":"candidate presented",
  "approval":{"mode":"create","questions":[{
   "question":"Should we implement the chart design?",
   "because":"The design is ready; implementation needs your direction.",
   "options":[
    {"label":"Implement","consequence":"Implement this design; integration and deployment need separate authorization."},
    {"label":"Defer","consequence":"Leave implementation unstarted until you request it."}],
   "presentation":{"version":1,"type":"artifact_approval",
    "scope":"Implementation of the chart design only.","stages":["implementation"],
    "primary":{"kind":"commit","repository":"bhill78/Mentis",
     "sha":"0123456789abcdef0123456789abcdef01234567","label":"Chart design"}}}]}}}
```

New ordinary `request_decision` asks require the same complete descriptor, in
shorthand or `questions[]`. Supply the actual question (maximum 1,000 code
points), context in `because` (2,000), and a consequence for every offered
choice (labels 200, consequences 2,000). Form-level `because` may supply context.
Presentation requires integer `version:1`, `type`, `scope` (2,000), `stages`
and an explicit `primary`. Types are `artifact_approval`, `action_approval`,
`choice`, `free_response`. Approval stages are one or more of `design`,
`implementation`, `integration`, `deployment`, `other`; other types may use `[]`.
Free responses omit options. Choices need at least two distinct trimmed labels.

References are `{kind:"record",id:"ent-…|opr-…|adm-…",label:"…"}`,
`{kind:"commit",repository:"…",sha:"<full 40-character hash>",label:"…"}`,
or `{kind:"url",url:"https://…",label:"…"}` (HTTP previews are supported).
Reference labels are limited to 160 code points. An artifact approval requires
an exact record or commit, rather than a mutable preview alone. Other types
may use `primary:null` with `primary_reason` explaining why no source is needed.
Optional `supporting` holds up to 24 references. Optional `applies_when` (1,000)
states a condition; it never skips or closes questions. Unknown presentation
keys and unsupported versions are refused on creation. Invalid batches append
nothing; existing historical records remain readable without migration.

To bind questions already asked, use
`approval:{mode:"existing",form:"opr-…",questions:["opr-…"]}` with their
exact identities. They must belong to this carried request and have complete
presentation data. Binding writes no questions and never reopens them or
interprets their answers as affirmative. `create` supplies its own complete
descriptors; Mentis generates no question, options, consequences or scope.
It appends to this execution's eligible ordinary form, even after attachment
to its own result post. It refuses closed, ineligible, ambiguous or overflowing
targets (20 questions total), without creating a fallback form. Identical
retries on the same execution/request/result post reuse the exact question IDs;
changed approval descriptors conflict. Summary and evidence changes do not.

Final outcome blocks support **one inline JSON object** on the `approval:` line,
with these same modes. Nested YAML and artifact shorthand are unsupported.
Malformed final blocks retain the original reply and an unclaimed diagnostic.
Claim-time approval refusals in run-end and `respond` retain the outcome claim
and a `bad-approval` diagnostic, omit the approval binding, and cannot reconcile
as met. `record_outcome` refuses atomically, including its result Turn.

Presentation is read-only metadata and grants nothing. Existing answer indexes,
own words, withdrawal reasons and authority remain unchanged. Closing all form
questions may resume Work under its existing rules, including after withdrawal;
an answer is never interpreted here as approval of implementation or deployment.

A partial claim records whether anything can continue it: a returning child,
awaited work, open decision/input, or armed detached operation. Without one, the
claim is still recorded, its answer explains how to add a continuation, and work
views show `stopped: nothing will resume it`. It stays unresolved across date
filters. If the next step is explicitly the owner's future action, name it in
`owner_wait` in the outcome. This is a manual wait, with no automatic wake-up.
Prefer `request_decision` or `request_input` when an answer can resume the work.

## Detached helper protocol and HTTP API

1. Post the promise with `respond`, leaving the request open.
2. Call `arm_detached` through `/api/worker` with `what`, `result_location`,
   `arming_post` (your promise post), and optionally a positive integer `pid`.
   The grant supplies the originating request. Only its current carrier may arm
   it; an arm cannot target another request or conversation.
3. Give the returned `operation` and `report_token` to that one helper before
   letting it detach. Mentis neither starts nor monitors the helper. Keep the
   token out of posts, evidence, shell arguments, logs and version control.
4. At its actual verdict the helper submits exactly one report. Report a failure
   or rollback too; `unknown` means its actual result could not be determined.

`POST /api/detached/<operation>/report`, JSON with `X-Mentis-Client: 1`:

```json
{"token":"<one-time secret>","result":"succeeded",
 "summary":"4037e33 deployed; smoke passed",
 "evidence":["C:/release/REPORT.md","commit 4037e33"]}
```

Results: `succeeded`, `failed`, `rolled_back`, `unknown`. A nonempty summary is
required; evidence is an array of strings. The response identifies the operation,
report act, result Turn, originating expectation and resumption (if any).
Unknown arms, wrong tokens and already spent tokens return 403 without writing;
malformed verdicts return 400 without spending the token. GET is unsupported.

The report token is the sole report authority: no owner session is needed. A
worker grant is refused on this route and remains admissible only at `/api/worker`.
The token authorizes only one verdict on one operation, with no arbitrary Turn,
request, carrier, dispatch, or file-read arguments. The record holds only its
SHA-256 hash, including after a restart and in keyed arming answers. Arming with
the same `op_key` again returns the same operation but no secret: if that first
answer was lost, do not start its helper; make a new arm. The unresolved old arm
remains visible. Protect the helper's token file with the same local access rules
as other deployment credentials. Use a trusted connection to the named server.

The report appends `detached-reported` under the originating request and a
record-only Turn replying to the arming post in the same conversation. It calls
the existing `claim_resumption`/`resume_dispatch` path. The resumption includes
operation, report, arming post and originating request, and instructs that carrier
to reconcile that request. The report itself never claims the work met. A report
arriving while the carrier runs is handed over when that run ends; an unanswered
report prevents an earlier met claim from closing the request before handover.
Reports for met or withdrawn work remain recorded and visible and resume nothing.
An owner's Stop on the arming run also prevents automatic resumption. A person
can explicitly continue the request and reconcile its durable report afterward.
Unreported operations show `armed <when>, no report yet` in work views. The Rust
front forwards this unowned POST route unchanged to Python.

There is no timer, timeout-driven continuation, retry service, polling or watchdog.
If the helper never reports, nothing wakes to check it. After a lost HTTP answer,
the helper can inspect its receipt/evidence and a person can inspect the record;
the one-time token cannot create a second report. The report and resumption claim
commit together. A crash after that commit but before dispatch leaves both records
durable; continuing that request is a person's act, as with an existing lost dispatch.

## PowerShell helper integration

Save the token privately when arming and pass its path plus the operation id to
the helper. Call the CLI once at the helper's verdict, after the restarted server
can accept that verdict. Integrate this at the helper's existing final verdict;
the example adds no wait or process supervision:

```powershell
# $Operation, $TokenFile and $Base were supplied when the operation was armed.
# $Result is succeeded, failed, rolled_back or unknown, from the actual verdict.
& $Python 'C:\Work\Mentis\tools\report_detached.py' `
    --server $Base --operation $Operation --token-file $TokenFile `
    --result $Result --summary $Verdict --evidence $ReportPath
if ($LASTEXITCODE -ne 0) {
    Add-Content -LiteralPath $ReportPath -Value 'Mentis report was not confirmed.'
}
```

Alternatively supply the token through `MENTIS_DETACHED_TOKEN` (or `--token-env`
with another variable's name). `tools/report_detached.py` makes one HTTP call,
prints the receipt, and exits nonzero if refused or unconfirmed. It needs only
Python's standard library. No existing deployment helper is modified by this work.
