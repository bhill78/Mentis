# Part B Perspectives owner API

Part P interface, based on Part A `12fecc0172`. This contract is published before
implementation for the carrier. No UI, dispatch policy, worker API, collection
writer, or deployment change belongs to it.

**Owner correction received:** `ent-21d18fc9dc7c` and `ent-d85254fe5e1b`
supersede the B7 audience premise. Configured/explicitly authorized sources set
collection scope; technical agent access does not. Do not assume one human
audience. The rejected audience question `opr-dbb31856813b` is not an outstanding
valid approval gate; its author/carrier must reconcile it, without another broad
question. Existing worker Brain and acquired-source reads do not enforce the
configured-source boundary. This package is preserved as **fixture implementation**.
Production `prepare` and `finalize` now refuse 422 `grounded-answers-blocked`,
including retries. No HTTP parameter or setting enables them. Focused tests
replace the closed internal product gate only in their fixture process.
Lifecycle, selection, durable history and existing ordinary replies remain usable.
Listing/state reads return `grounded_answers:false`. Do not enable grounded
answers or deploy them on the strength of provenance or an audience assertion.

All paths below start `/fluid/api/magnets/{magnet}`. Reads require
`X-Mentis-Client: 1` and refuse worker credentials, like existing Fluid reads.
Writes use the existing owner session and additionally require the confirmed
`X-Mentis-Brain: {corpus_id}@{instance}` and JSON `{brain, op, ...}`. `brain` is
that same string. `op` is a nonempty string, at most 160 characters, unique per
owner action. Retries carry identical bodies and keys. A key with changed body
is refused. The owner is read from the Brain; `author` is not accepted.

Responses are JSON. Success is 200 (including creation); refusals are 422 with
`{refused:true, code:string, error:string, ...details}`. Bad JSON/shape is 400;
wrong Brain is 409. A missing required Brain header is 409. Existing owner and
worker-credential doors still apply. Writes never dispatch. Replays return the
first durable result with `replayed:true`. No successful GET records a receipt;
the client must POST a fresh reconciliation before presenting qualified output.

```ts
type Ref = string; // adm-..., immutable Admission
type Topic = string; // ent-..., conversation-local Perspective identity
type Artifact = {ref: Ref; digest: string; size: number; media_type: string};
type Event = {seq: number; post: string; event: string; perspective: Topic|null;
  snapshot: Artifact; data: Record<string, unknown>};
type Perspective = {perspective: Topic; name: string; retired: boolean;
  question: Artifact|null; events: number};
type Page = {magnet:string; perspective:Topic|null; events:Event[];
  next:string|null; through:number; brain:string; disclosure:string};
type Selection = {batch:Ref; source:string; item:string; version:string;
  part?:number; start:number; end:number;
  stance:'supporting'|'contradicting'|'context'};
type Prepared = {intent:string; magnet:string; perspective:Topic;
  brain:string; question:Artifact; manifest:Artifact; records:Artifact;
  artifacts:Artifact[]; parts:FilePart[]; reach:'work'; request_op:string;
  text:string; closure:{count:number; bytes:number}; disclosure:string};
type FilePart = {type:'file'; ref:Ref; media_type:string; alt:string};
type Receipt = {receipt:Artifact; status:'pending'|'qualified'|'unqualified';
  execution:string|null; request:string; required_unavailable:Ref[];
  reachable_not_declared:{ref:Ref; because:string; [key:string]:unknown}[];
  available:{ref:Ref; because:string; [key:string]:unknown}[];
  closure:{count:number; bytes:number}|null; disclosure:string};
```

| Method/path | Body/query | Result |
|---|---|---|
| GET `/perspectives` | `limit=20` (1..100), `cursor?` | `{magnet, perspectives:Perspective[], selected:Topic|null, next, brain, disclosure}` |
| GET `/perspectives/{topic}` | none | `{magnet, ...Perspective, selected, brain, disclosure}` |
| GET `/perspectives/{topic}/history` | `limit=20` (1..100), `cursor?` | `Page`; oldest first, stable frozen high-water mark, cursor bound to Brain/Magnet/Topic |
| POST `/perspectives` | `{brain,op,name,question,reason?}` | `{perspective,question:Artifact,event:Event,brain}` |
| POST `/perspectives/selected` | `{brain,op,perspective:Topic|null}` | `{selected,event,brain}`; independent of collection definition/arrangement |
| POST `/perspectives/{topic}/question` | `{brain,op,text,reason?}` | `{perspective,question:Artifact,event,brain}`; immutable revision |
| POST `/perspectives/{topic}/challenge` | `{brain,op,text,reason?}` | `{perspective,event,brain}` |
| POST `/perspectives/{topic}/retire` | `{brain,op,reason?}` | `{perspective,event,brain}` |
| POST `/perspectives/{topic}/resume` | `{brain,op,reason?}` | `{perspective,event,brain}`; records lifecycle only, never starts an agent |
| POST `/perspectives/{topic}/branch` | `{brain,op,name,question,reason?}` | same as create; explicit parent Topic retained |
| POST `/perspectives/{topic}/prepare` | `{brain,op,question:Ref,batches:Ref[],selections:Selection[],priors?:Ref[],declared_context?:Ref[],continuation?:boolean}` | `Prepared` |
| GET `/perspectives/{topic}/intents/{intent}` | none | `{prepared:Prepared,binding:{request,post}|null,answers:Artifact[]}`; recover original uncertain intent after reload |
| POST `/perspectives/{topic}/bind` | `{brain,op,intent,request}` | `{intent,request,post,event,brain}`; validates actual immutable asking Turn, owner, original request operation key, exact question prefix and every required file part; refuses Conversation reach |
| POST `/perspectives/{topic}/reconcile` | `{brain,op,intent,execution?,declared_context?:Ref[],purpose:'resume'|'attach'|'display'|'reuse'}` | `Receipt`; each fresh action appends a version; explicit extra declarations are counted |
| POST `/perspectives/{topic}/finalize` | `{brain,op,intent,execution,answer}` | `{answer:Artifact,receipt:Receipt,event,brain}`; recomputes reconciliation and snapshots actual answer version only when qualified |

An intent is the prepare event's immutable post id. A selected lens may be null;
retirement deselects the lens if selected. Selection changes never collect or run
anything. A retired Perspective cannot prepare a new question until resumed.
Question edits do not invalidate existing intents: retry/bind uses the original
snapshot, not current selected lens, latest batch or revised question. Each
prepare returns `request_op` derived from its intent. Use it unchanged as the
ordinary Composer request `op`. Do not use prepare's `op` for sending.

Example lifecycle:

```json
POST /fluid/api/magnets/mag-example/perspectives
{"brain":"corpus@instance","op":"create-1","name":"Counterevidence","question":"What contradicts the claim?"}
POST /fluid/api/magnets/mag-example/perspectives/selected
{"brain":"corpus@instance","op":"select-1","perspective":"ent-topic"}
POST /fluid/api/magnets/mag-example/perspectives/ent-topic/prepare
{"brain":"corpus@instance","op":"prepare-1","question":"adm-question","batches":["adm-batch"],"selections":[],"priors":[],"declared_context":[],"continuation":false}
```

An empty selections array explicitly selects all captured text ranges. Nonempty
selections name captured source keys and immutable result id/version; post ranges
are Unicode codepoint offsets in a text part (`part`, default 0), file ranges are
UTF-8 byte offsets in the captured first page. No live source substitution.
Selection does not shrink an indivisible batch's counted bytes. Missing attachment
bytes are dependencies, even when merely referenced inside the batch. Acquired
non-image files captured inline are pinned source ranges, not worker artifact
attachments. Prior answers must be Part P immutable answers from this same Brain
and Magnet. Their manifests and transitive original dependencies are included.
Shared originals deduplicate by version/digest/range; zero original support is
labelled `unsupported`, never independent corroboration. Omissions remain explicit.

The manifest pins Brain instance, Magnet, raw definition digest, Topic, question,
batch versions, original ranges/stances, direct and inherited edges, priors and
omissions. The immutable records package supplies exact durable Topic history;
`continuation:true` includes its question/answer/manifest dependencies. The
product reconstructs this via bounded server history. A native agent receives
the identity **and** these actual file parts, and uses existing `read_artifact`.
There is no worker operation or owner HTTP route for agents to call.

Ordinary Composer integration (preserve all runtime, Work, permission and reply
fields): use `prepared.text` as the beginning of the asking text, append all
`prepared.parts` as actual file parts, use `prepared.request_op`, `topics:[topic]`,
`from:{magnet}`, and set each dispatch `reach:'work'`. Bind the returned actual
expectation id. The text may have additional owner words and incidental `adm-`
ids; reconciliation discloses their real reach. A record-only post uses the
existing Part A path unchanged. No raw reply is silently converted into synthesis.

```json
POST /fluid/api/requests
{"from":{"magnet":"mag-example"},"author":"ent-owner","text":"What contradicts the claim?","parts":[{"type":"text","text":"What contradicts the claim?"},{"type":"file","ref":"adm-manifest","media_type":"application/json","alt":"Perspective evidence"}],"topics":["ent-topic"],"action":"ask-participant","addressed_to":["ent-agent"],"dispatch":[{"participant":"ent-agent","reach":"work","work":"Read the attached Perspective record package with read_artifact and answer the frozen question."}],"op":"perspective-request:ent-intent"}
```

The example abbreviates the parts: send **every** returned file part, including
definition, question, records, batches, manifest, prior answers and dependencies.

Closure is at most 32 distinct Admissions and 8,388,608 bytes, **including the
manifest itself**. Traversal inspects at most 33 nodes (one overflow sentinel),
uses an active stack for cycles, validates ranges and refuses missing/unreadable
dependencies. No depth cut-off counts as complete. An oversized batch refusal
names its actual byte size and the 8 MiB bound and says to narrow source/type/date
configuration and Collect again. No exception, automatic split or compression.

Reconciliation uses `artifacts.available` for the actual request/execution. Live
delivered facts or the execution's recorded dispatch delivery are required;
otherwise it remains pending. It compares both directions and includes owner
tokens, object/Turn references, lineage, governing, earlier returns and waited
returns. Only that producing execution's identified outputs are excluded from
inputs. Explicit `declared_context` is an owner declaration, not an inferred
manifest amendment, and counts against the same bound. Append receipts on resumes
and before every qualification, display, attachment or reuse. An immutable answer
version is not perpetual qualification; obtain a fresh display receipt. Newer
executions make late finalize attempts refuse. Raw ordinary replies stay readable.

For delegated native continuation, pass the descendant's actual `execution` to
reconcile/finalize. The server follows the existing recorded hand-off line to the
bound request, checks work reach and requires all prepared artifacts as real
file parts on the hand-off. Unrelated executions cannot use that binding. The
receipt's `request` names the actual descendant; an answer also preserves
`bound_request`. Outputs attached to that answer become counted inputs on reuse.

Baseline delivery limitation: `mentis.web.dispatch.governing_ids` computes current
governance; it is **not** a historical-delivery lookup. Part P uses actual live
grant facts, persists them on receipt versions, and can read an unambiguous
request-tagged recorded dispatch delivery after end. A resumed run without a
captured live receipt or an unambiguous delivery join stays `pending` with
`source:'recorded-delivery-join-unavailable'`. It never substitutes current
governance. Carrier acceptance must verify this on its real resumed runs; this
part adds no dispatch writer or worker operation to fill missing provenance.

The original approved disclosure ended with a single-owner-audience restriction.
The later correction supersedes that premise. The response's current disclosure
is:

> Selected evidence is recorded. This agent may read other Brain and acquired material; the list is not a complete input audit. Grounded Perspective answers are blocked until the configured-source access boundary is enforced.

This is evidence accounting, not authorization or an evidence-only boundary.
Neither configured retention mode, automatic material recording nor adoption is
implemented. TEST/DAY-TO-DAY were not modified. Real native/MARS verification,
independent implementation review and the missing boundary remain unverified.
No boundary implementation, new approval decision or review cycle is started by P.
