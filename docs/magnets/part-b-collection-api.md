# Part B collection interface (Part C)

This contract precedes implementation. Baseline: `12fecc0172eaca0745fd0eeda3dba9a43d54df54`.
Owner-only HTTP reads retain existing authorization and Brain binding. No worker operation,
private capture route, source acquisition, refresh, or filesystem grant is added.

## Retained page

`GET /fluid/api/magnets/<id>/collection` keeps its exact existing response:
`{magnet,config,activation,page}`. `config` is current configuration; `page` is frozen.
`activation` is `{post,artifact:{ref,digest,size,media_type},at,state}` or null.

`GET /fluid/api/magnets/<id>/collection?batch=<adm-ref>&digest=<64 lowercase hex>`
selects an explicitly recorded batch. Both query values are required together. It returns
the same shape; it never substitutes latest. A batch belonging to another Magnet or absent
from its activation record is 404. Wrong digest or missing/corrupt/purged/invalid retained
bytes is 422 `{error:<explanation>,kind:"Unreadable",refused:true}`. Malformed query
is 400 `{error:<explanation>,kind:"BadRequest"}`.

## Bounded history

`GET /fluid/api/magnets/<id>/collection/history?limit=20&cursor=<token>`
returns `{magnet,batches:[{post,artifact:{ref,digest,size,media_type},at,state}],next}`.
Default/maximum limit 20, minimum 1. `next` is null or an opaque `mc1` cursor, bound to
the Magnet and an append-order snapshot. Later activations do not shift subsequent pages.
Each listed batch is verified against its Admission, complete digest, format, operation,
captured definition and activation act before listing; unreadable history fails explicitly.
History reads at most limit+1 activation records and verifies at most limit batches.
No result page bytes are returned by listing. Bad cursor is 400; absent Magnet is 404.

Python API: `collection.read(st,mid,batch=None,digest=None)` and
`collection.history(st,mid,limit=20,cursor=None)`. The shared router owner applies the
minimal fragment in `part-b-collection-router.patch`; Part C does not edit shared files.

## Exact held file row

The schema keeps 0..20 explicitly configured sources. New activation needs at least one
supported source among them: a Conversation or an exact held filesystem file. A file-only
Magnet can collect manually; no source Conversation is required or added. A Magnet with no
configured source at all exists, converses and reopens; Collect on it is refused with
`no-readable-source` and records nothing, and the client says so without sending the request
(`quiet2/magnets/configuration.ts` `NO_SOURCE_TO_COLLECT`). Unsupported source
kinds remain unavailable alongside supported sources and make a useful batch partial;
an unsupported-only configuration still refuses with `no-readable-source`. A page with
no useful results refuses (or reports sources busy) rather than adding other sources.
A file source requires one exact collection id and relative path. Missing path, directory,
glob, traversal or absolute path is refused at activation preflight with:
“Choose one held file; collection-wide file reads are unavailable.” Historical generic
definitions and verification retain their original interpretation. Conversation source keys
are unchanged. Type/date filters apply to Conversation content, not exact file selections.

Rust captures only the latest already-recorded filesystem observation for collection/path
under M1's Background read/deadline. Missing, absent/deleted, non-held, purged, corrupt,
non-text, NUL or invalid UTF-8 content gives an unavailable source with no results.
No live path is opened. A successful row preserves all five mandatory keys:

```json
{"kind":"file","id":"adm-…","version":"adm-…","conversation":null,"author":null,
 "at":1790000000.0,"via":"held-source","value":{
 "ref":"adm-…","digest":"<complete SHA-256>","collection":"col-…","path":"file.txt",
 "text":"captured text","offset":0,"end":13,"size":13,"acquired_at":1790000000.0,
 "shortened":false,"omitted_bytes":0,"next_offset":null,
 "citation":"adm-…@<first 12 digest hex>[0:13]"}}
```

`at=acquired_at` is original Admission acquisition time. `id=version=value.ref` pins
that observation. Digest covers the complete held observation. Text encodes to exactly
`end-offset` bytes, `end<=65536` on a UTF-8 boundary; `size` is complete original size.
`shortened=(end<size)`, `omitted_bytes=size-end`, `next_offset=end` if shortened else null.
Only the prefix is retained; a shortened source is partial with an explicit reason.
The citation spelling matches Python `sources.reading.read().cite`.
Only this exact acquired-file shape admits null home/author and Admission version.
Conversation and historical rows retain the mandatory keys and home checks.

The Magnet's own Conversation is the activation's output destination, separate from
its configured collection sources. Creating that destination does not add it to the
source list. Activation remains manual, one-time, one `extract` operation in `m1-page`
mode; configuration of other modes does not enable automatic collection.

## The proposal — one sentence becomes a configuration (Part G1)

Owner's correction `ent-8a4357b5f7fc`, amendment `adm-c38044ee5157` §4: "Purpose-driven
creation should lead directly to activation and useful results, without requiring the user
to navigate several configuration screens."

### The door

`POST /fluid/api/magnets/propose` `{sentence, magnet?}`. Owner-only, Brain-bound and
client-headered like every other POST under `/fluid/api/`; a worker grant is refused there
as it is everywhere. **It reads only.** No entry, no operational act, no definition file,
no dispatch — proved by `tests/test_magnet_write_paths.py::test_a_proposal_writes_nothing_*`,
which counts every `entry` and `operational` row before and after. `sentence` is 1..2000
characters (`MAX_SENTENCE`, the schema's `MAX_CRITERIA`); `magnet` is an existing `mag-…`
or absent. Anything else is 400 with plain words and no identifier in them.

The answer is `{proposal: {…}}`:

```json
{"proposal": {
  "sentence": "follow the solid electrolytes work",
  "name": "The solid electrolytes work",
  "sources": [{"kind": "conversation", "conversation": "ent-…"}],
  "selection": {"criteria": "follow the solid electrolytes work",
                "informationTypes": ["post", "file", "image", "attachment"]},
  "cadence": {"mode": "scheduled", "schedule": "PT6H"},
  "words": {"sources": "Solid electrolytes", "collect": "Posts, files, images and attachments",
            "cadence": "Every six hours"},
  "listed": [{"title": "Solid electrolytes", "says": "Conversation · posts and their attachments"}],
  "seed": {"sources": […], "selection": {…}, "collection": {"mode": "one-time"}, "…": "…"},
  "change": {"identity": {"name": "…"}, "sources": […], "…": "…"},
  "unavailable": [{"title": "Harbour feeds", "kind": "rss-atom", "why": "…"}]
}}
```

`words` and `listed` are what the interface shows: ordinary words only — no `mag-…`, no
`ent-…`, no `one-time`/`manual`/`scheduled`. `seed` and `change` are what a press applies.
`unavailable` names what was found and could not be proposed, in the registry's own words.

**A name is derived, never demanded** (`proposed_name`): the sentence with its opener
("I want to follow", "keep an eye on", …) removed, cut to `MAX_NAME`.

### Validated before it is ever shown

Every proposal is built by `runnable_definition`, which passes the whole definition through
`mentis.magnet.schema.magnet_config`, and the cadence through `schema.facet("collection", …)`
and `schema._when`. A mode the schema does not carry cannot leave this door. Proved by
`tests/test_magnet_definitions.py::test_a_proposal_is_schema_valid_before_it_is_ever_shown`.

### Which source kinds are available is derived at runtime, never listed

`reads_here(source)` builds a one-source definition and asks the code that actually
collects whether it could run it: `mentis.magnet.activation._cannot_run_code` (the
contract's own first-failing-line check) and `activation.runnable_files` (its own file
rule). Which connectors exist and which are available is
`mentis.sources.registry.descriptors()`, read on every call; which collections exist is
`mentis.sources.declarations(corpus)`.

Consequences, all of them free of further change here:

- **Part C** widening a `file` source to a path prefix or a whole collection makes the
  path-less candidate `{"kind": "file", "collection": "col-…"}` pass `runnable_files`, and
  the proposal stops looking for an exact file.
- **Part W** flipping `rss-atom`, `web-search` and `web` to `available=True` makes
  collections of those connectors proposable; until it does, each is reported in
  `unavailable` with the registry's own `why_not`.
- A kind in the Magnet schema that nothing collects (`web`, `brain`, `database`,
  `connector`, `other`, `agent-results`) is never proposed, because `reads_here` says no.

A candidate is proposed only where the sentence's own words name it (word overlap with the
Conversation's or collection's name), at most `PROPOSE_MOST` (5). **A sentence that matches
nothing proposes no source at all** and says so (`NOTHING_MATCHES`) — a Magnet with no
sources is a valid Magnet (#521 §4), and a source nobody asked for is not an answer.

### The cadence

`proposed_cadence` reads "every hour"/"hourly", "every day"/"daily", "every week"/"weekly"
from the sentence, and otherwise proposes `PT6H`. It is in the proposal, so periodic refresh
is on from the start rather than being something to go and switch on afterwards.

### Acceptance: no new command

**There is no accept door.** One press runs the existing doors in this order:

1. `POST /fluid/api/arrangements/<key>/magnets` with `seed` (a Magnet that does not exist
   yet), or `POST /fluid/api/arrangements/<key>/magnets/<id>/reconfigure` with `change`
   (one that does). The configuration is applied.
2. `POST /fluid/api/magnets/<id>/activate` — the first collection runs.
3. `POST /fluid/api/arrangements/<key>/magnets/<id>/reconfigure` with
   `{collection: <cadence>}` — periodic refresh is on.

**Why the cadence lands last.** `activation._cannot_run_code` requires
`collection.mode == "one-time"` for the manual activation that runs this build's first
collection, so a definition carrying the cadence cannot be activated by hand. The first
collection therefore runs from the one-time facets and the cadence is applied immediately
after it, in the same press. Until **Part D2**'s due runner interprets
`collection.mode = "scheduled"`, a *manual* Collect on a Magnet carrying a cadence is
refused with `collection-not-supported`, and the Sources panel says the cadence instead of
offering Collect. That is a seam for Part D2 and the integrator, not a defect of this part.

**Seam named for `mentis/magnet/activation.py`'s owner:** `_cannot_run_code` is private to
that module and is read here, because the derivation must come from the real contract rather
than a copy of it. A public name for "could this definition run" belongs in `activation.py`;
Part C holds that file this round, so none was added.

## Authentic compatibility fixture

`tests/fixtures/magnet-conformance/legacy/brain-12fecc01.zip` is a complete fixture
Brain produced before verifier changes using baseline preflight and commit HTTP doors.
`receipt.json` holds those answers and the actual `magnet-extracted` act. It contains two
Conversation sources and an unavailable path-less file source. The generator asserts exact
baseline HEAD and is not a post-change fixture rewrite mechanism.
