# Part B Perspectives owner API

Part P interface, based on Part A `12fecc0172`. This contract is published before
implementation for the carrier. No UI, dispatch policy, worker API, collection
writer, or deployment change belongs to it.

**Owner correction received:** `ent-21d18fc9dc7c` and `ent-d85254fe5e1b`
supersede the B7 audience premise. Configured/explicitly authorized sources set
collection scope; technical agent access does not. Do not assume one human
audience. The rejected audience question `opr-dbb31856813b` is not an outstanding
valid approval gate; its author/carrier must reconcile it, without another broad
question.

**The gate is OPEN, because the correction is now enforced (Part A).** The
paragraph this replaces published a closed gate and said why: worker Brain and
acquired-source reads did not enforce the configured-source boundary, so
production `prepare`, `finalize` and `reconcile` refused 422
`grounded-answers-blocked` and listing/state reads returned
`grounded_answers:false`. That enforcement exists: `mentis/magnet/scope.py`,
applied at the one door through `mentis.worker.permitted` and
`worker._magnet_confined`, confines a run carrying a Magnet's exchange to that
Magnet's own recorded collection batches, the posts of its own Conversation and
the references the owner explicitly selected for that exchange. So
`GROUNDED_ANSWERS_ENABLED` is `True`, `require_grounded()` admits, and
listing/state reads return `grounded_answers:true`. The refusal keeps its code
(`grounded-answers-blocked`) for a build that shuts the gate again. See
"Part A — the Magnet scope contract" below for what a run may read, what it may
not, and the two fields Parts B and F are written against. Lifecycle, selection,
durable history and existing ordinary replies are unchanged.

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
first durable result with `replayed:true`. The grounded gate is checked before
keyed replay, so preserved qualified results cannot be replayed while disabled.
GETs retain raw historical records; they do not qualify an answer.

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
| GET `/perspectives/{topic}` | none | `{magnet, ...Perspective, current_question:{text,revision}|null, selected, brain, disclosure}` |
| GET `/perspectives/{topic}/history` | `limit=20` (1..100), `cursor?` | `Page`; oldest first, stable frozen high-water mark, cursor bound to Brain/Magnet/Topic |
| POST `/perspectives` | `{brain,op,name,question,reason?}` | `{perspective,question:Artifact,event:Event,brain}` |
| POST `/perspectives/selected` | `{brain,op,perspective:Topic|null}` | `{selected,event,brain}`; independent of collection definition/arrangement |
| POST `/perspectives/{topic}/rename` | `{brain,op,name}` | `{perspective,event,brain}`; durable display name, same Topic identity |
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

Question-first creation needs no backend naming operation: the client derives
`name` from the question (use the question unchanged through 52 characters,
otherwise its first 49 characters plus "?") and sends both `name` and `question`.
The existing create contract still requires nonblank text for each; the owner
need not fill in a separate name field.

Optional renaming appends a `magnet-perspective-event` with `event:"rename"`,
`data:{name}` and an immutable event snapshot artifact. `name` uses the existing
nonblank-text bound (65,536 characters); extra fields are refused. List/detail
reads use the newest rename event, falling back to the original `created` name.
Earlier names and snapshots remain in history. The Topic id, Topic label,
question, durable selection, collection definition and pagination identities do
not change. Renames require this Magnet's own recorded Perspective and writable
Conversation, the same owner/Brain checks and `anchors.keyed` retry behavior as
other lifecycle writes. Renaming does not enable grounded answers.

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

Preserved grounded fixture integration (unavailable in the product; never use
for ordinary Composer assistance): use `prepared.text` as the beginning of the asking text, append all
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
The later correction supersedes that premise, and Part A replaced the sentence
that said the boundary was missing. The response's current disclosure
(`mentis.magnet.perspectives.DISCLOSURE`) is:

> Selected evidence is recorded. This Magnet's answers are grounded in its own collection: a run carrying one of its exchanges reads that Magnet's recorded collection batches, the posts of its own Conversation and the references the owner selected, and every other Brain record or acquired source is refused at the door (mentis.magnet.scope). A Perspective answer and an evolving summary are grounded in the collected rows and nothing else; no authorization widens them. The owner may authorize one conversation exchange to reach a named outside source, and an answer that reached one says so in its provenance.

This is evidence accounting plus the boundary that now backs it. It is still
not a complete input audit of the runtime's own tools: what Mentis serves is
enforced, and a runtime's own web search is recorded and told, not policed.
Neither configured retention mode, automatic material recording nor adoption is
implemented. TEST/DAY-TO-DAY were not modified by Part A.


## Ordinary discussion and current question

Detail reads include `current_question:{text,revision}` from the latest durable
question event, independent of bounded history pages. `revision` is the immutable
question Admission reference; `question` keeps its original artifact descriptor.
List reads remain bounded metadata. Read a selected Topic directly even if it is
outside the first list page. No artifact bytes need to be fetched for ordinary help.

`PerspectiveStore.ordinaryContext()` returns
`Promise<{perspective:string;name:string;question:string;revision:string}|null>`.
It freshly reads durable selection and question detail and checks Brain, Topic,
selection and revision on late responses. It supplies inquiry wording only, with
no evidence, prepare or qualification. The carrier owns the Composer send adapter.
The discussion button copies this saved wording into the existing Composer draft;
another nonempty draft is retained and must be handled explicitly by its owner.

Lifecycle writes freeze Brain, Magnet, path, target, exact arguments and key before
sending. One bounded pending action is kept in browser storage until answered;
only explicit unchanged retry resends it. Create/branch and subsequent selection
use separate frozen keys; an acknowledged create is never recomputed for a lost
selection acknowledgement. A failed refresh after acknowledgement reports saved
state, not an uncertain write. Selection never changes collection configuration.

The Perspective router contains only Perspective routes. The carrier owns the
canonical collection latest/exact/history routes and blank-selector preservation,
and verifies those on integration. This package does not carry that fragment.


## Part A — the Magnet scope contract

Published by Part A (`mentis/magnet/scope.py`, `tests/test_magnet_scope.py`) for
Parts B and F to be written against. **Part A owns none of their files**: this is
the contract, not the implementation of their halves.

### What a Magnet-scoped execution is

A run carrying a managed Magnet exchange is dispatched with one of two scopes,
decided from the frozen managed context and nothing else
(`mentis.web.dispatch._magnet_scope`):

| Scope | When | May read |
|---|---|---|
| `magnet:<mag-id>` | the exchange names no saved Perspective question (`selector.perspective is null`) — ordinary conversation | the Magnet's own recorded collection batches; the posts of its own Conversation; the references the owner selected in this exchange's `magnet_context`; the acquired collections its definition configures |
| `magnet-synthesis:<mag-id>` | the exchange names a saved Perspective question — a Perspective answer or an evolving summary | the same, **less every source read**: a synthesis run reads no live collection at all, not even a configured one |

`mentis.worker.permitted` narrows what either may CALL to the intersection of
what its request granted with `scope.MAY_CALL` (plus `scope.OUTSIDE_READS` for
`magnet:` only). A read that cannot be pointed at one Magnet is refused, not
narrowed: `find`, `recall`, `governed`, `work_overview`, `brief`,
`owner_decisions`, and `delegate` (a child's grant is minted from its own
request, so delegating would be a way out of the confinement). The refusal is
the door's existing scope wording, naming the scope.

`scope.why_not` then confines each remaining read by TARGET, refusing with the
`place` boundary and words that name the Magnet, its Conversation and the
owner's correction `ent-d85254fe5e1b`. A Magnet-scoped grant is deliberately
not mirrored to the Rust front (`mentis.mirror.mirrored`), so the front
forwards it instead of answering a moved read under the ordinary worker set.

**Narrowing only.** Nothing in `scope.py` admits a read the ordinary rules
would have refused. In particular a Magnet-scoped run still cannot
`read_artifact` its own collection batch unless the ordinary reach rules allow
it — closing that is **Part B's** read-side widening (`opr-d4b617de6850`), and
`tests/test_magnet_scope.py` asserts the scope gate is silent about it so the
two halves stay distinguishable.

### The contract Part B implements its hydration against

`mentis/fluid/message_context.py` is Part B's. Part A states what hydration may
and may not do; B implements it.

1. **A `collected_item` hydrates only from the Magnet's own recorded batch.**
   `collection.member(st, mid, r)` is already the membership check and stays the
   only one: its `(ref, version, digest)` triple is the identity, and a forged,
   foreign, stale, deleted or restricted selection must still refuse where the
   owner can act on it. Hydration adds the row's retained text and its `cite`;
   it must not reach a live source, substitute anything, or follow an id the row
   happens to name.
2. **Hydration widens no reach.** What crosses into the prompt is what the owner
   selected in that exchange. The scope gate is the door's; a hydrated byte is
   not a grant, and the run must still ask the door for anything else.
3. **The existing bounds hold unchanged**: 16 KiB raw selector, 64 KiB hydrated
   context, 16 references, and the inert-data header on the prompt.
4. **`require_grounded()` may be removed only from paths Part A made safe**, and
   only those. Its calls in `_artifact`, `_selections`, `prepare`, `accepted`
   and `gate` are now no-ops (the constant is `True`); deleting a call is a
   separate, deliberate act per path.
5. **Two seams in `message_context.py` are Part B's to close, not Part A's**:
   - `payload()` still tells every run "Grounded answers from the retained
     collection are unavailable until configured-source read enforcement is
     verified." That sentence is now false and must say what the run may read
     instead — the Magnet's own collection, its own Conversation's posts, the
     owner's selections — and, where the exchange carries one, that the owner
     authorized it to reach a named outside source.
   - `prepare()` is where an authorization could be accepted as a body field if
     the owner's client is to send one with the message; see below.

### The owner's per-exchange authorization

`scope.authorize(st, mid, turn=..., opens=[...], by=<owner>, op=...)` records
`magnet-exchange-authorized` on ONE asking Turn. `opens` is 1..4 entries, each
`{"kind":"runtime-web-search"}` or `{"kind":"collection","collection":"col-…"}`.
It refuses anybody but the recorded owner, any Turn that is not the owner's own
asking Turn in that Magnet's Conversation, and anything malformed. The door
reads it for that exchange's execution only: an act an execution wrote opens
nothing, a synthesis confinement reads none at all, and the next exchange is a
different Turn and so unauthorized again with no further act.

**Seam, unclaimed.** There is no HTTP route to call `authorize` yet — Part A
owns no door file — so today no client can create one and every exchange is
unauthorized. Whoever adds it (Part B's request door, or the integrator) wires
one owner write to `scope.authorize` and nothing else; `scope.py` needs no
change. Until then the authorization path is implemented, recorded and tested,
and reaches nothing.

### The provenance field Part F and the client render

`scope.provenance(cv, mid, turn=…, synthesis=…)`:

```ts
type MagnetAnswerProvenance = {
  grounded_in: 'collection';            // always: the collection is the ground
  outside_authorized: ({kind:'runtime-web-search'} |
                       {kind:'collection'; collection:string})[];  // [] when none
  outside_reads: {what:string; collection:string; ref?:string}[];  // what it reached
  explored_outside: boolean;            // THE FIELD TO RENDER
};
```

**`explored_outside` is the field name Part F and the client use.** It is true
only when an authorized read of something outside the Magnet's collection
actually happened in that exchange, recorded at the door as
`magnet-outside-source-read` on the authorized widening path only (an ordinary
read inside the Magnet's scope records nothing). `outside_authorized` is what
the owner opened — allowed, not necessarily used — so an interface can say
"allowed to look outside" and "did look outside" separately, which is the whole
point of the distinction. For a synthesis answer all three are empty or false,
structurally and unconditionally.

Part F renders `explored_outside` beside the citations: grounded-in-the-
collection and explored-outside must never be mistaken for each other.
