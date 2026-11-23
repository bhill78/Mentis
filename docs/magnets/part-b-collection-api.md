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

New activation requires 1..20 explicitly configured sources, including at least one
supported source: a Conversation or an exact held filesystem file. A file-only Magnet
can collect manually; no source Conversation is required or added. Unsupported source
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

## Authentic compatibility fixture

`tests/fixtures/magnet-conformance/legacy/brain-12fecc01.zip` is a complete fixture
Brain produced before verifier changes using baseline preflight and commit HTTP doors.
`receipt.json` holds those answers and the actual `magnet-extracted` act. It contains two
Conversation sources and an unavailable path-less file source. The generator asserts exact
baseline HEAD and is not a post-change fixture rewrite mechanism.
