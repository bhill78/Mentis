# Astronomy TEST source handoff

Prepared for **@Magnet-Experience-Integrator**, the sole integrator, under owner
scope `ent-bafd3112a474`. Configuration is in `astronomy-test-sources.json`.
No source configuration, collection, deployment or DAY-TO-DAY content write is
performed by this implementation. Perspective, Composer and Summary are outside
this change. Existing acquisition review and the public spike are reused from
`adm-1158d2e00ad8`; no acquisition policy or parser changed.

## Operation availability

`write_source` is an organising operation in the existing `worker.AUTHORITY` /
`permitted` model, with matching Rust rules. An ordinary worker, Scratch,
Magnet conversation or synthesis grant cannot call it. An explicit organising
operation list must include `write_source`; `coordinate` alone grants nothing
here. Existing unrestricted organising grants follow the existing `None`
semantics. Hand-started sessions must name a recorded request they carry in
`under`, just as the existing coordinating operations require.

Integrate and deploy this commit as part of the one accepted TEST candidate.
Use a TEST-attached grant that admits this operation through `/api/worker`.
The attached work bridge targets DAY-TO-DAY; its credential must not be used
against TEST. Do not drop a worker grant to call `/api/sources` as the local
owner, mint a substitute grant, or treat trusted-local access as worker authority.
The running candidate and the grant must both offer `write_source` before
collection can proceed. This is the material deployment/grant seam for the
integrator, not a new owner decision.

## Exact acquisition sequence

1. Check the running TEST release and read the current astronomy definition.
   Keep its complete source roster and other fields. The saved measurement
   had `col-fea202869d76`, schedule `PT6H`, and 75 Google News rows; reread
   instead of overwriting anything accepted since that measurement.
2. For each `previews[].args` in the JSON, call `write_source` through the worker
   door. The HTTP body is `{"op":"write_source","args":<those args>}`;
   use the grant header the bridge already carries. Supply a unique `op_key`
   per new preview; resending a lost answer keeps that same key.
3. Inspect the returned plan, held-body preview and refusal details. Confirm
   an acceptable preview with `write_source(action="acquire", connector=<same
   connector>, draft=<returned draft>, plan=<returned plan>, op_key=<new key>)`.
   The real draft, plan and collection ids are returned at runtime and must
   never be guessed. If the source changes, the connector refuses the plan;
   inspect that refusal rather than weakening the check or starting a retry loop.
4. Append each successfully acquired collection as
   `{"kind":"file","collection":<returned collection>}` to the **latest**
   astronomy Magnet source roster, using the already supported owner-authorized
   configuration interface available to the integrator. Do not remove or
   rewrite earlier collections, admissions, batches or configuration history.
   The new operation itself changes no Magnet definition and grants no new
   configuration or activation authority.
5. Run the existing integrated TEST collection path. Measure admitted body
   lengths after excluding connector headers and provenance, both per source
   and across the real Magnet. Confirm substantial relevant astronomy evidence
   before requesting synthesis and re-answer through the existing paths.
   Those operations and their live verification belong to the integrator.

For refresh, `write_source(action="plan", collection=<id>)` returns the plan;
confirm with `action="sweep", collection=<id>, plan=<returned plan>` and a new
`op_key`. A proposed `scope` must be identical on plan and sweep. Alternatively,
`action="revise_scope"` appends `include`, `exclude`, optional `options` and
`because` without fetching. Acquisition keeps all existing registry checks;
there is no binding-change override, local binding, erasure or delete action.

## Evidence depth and boundaries

The completed NASA spike read 10 inline entries (263,560 response bytes), with
9 above 1,500 characters and a median of 4,129.5. These counts include captions
and other inline publisher text; they describe that spike, not a current TEST
collection or pure prose. NASA's ongoing feed includes administrative and
Earth-related items; inspect actual relevance. Appending ten entries to 75
headline stubs does not make the overall median substantive.

The ESA Euclid and Universe Today URLs are selected **static articles**, not
feeds or automatic discovery. Prior retained authored ranges were 2,879 and
8,190 characters respectively, as reported in the supplied evidence. Their
preview/acquire calls still obey current robots handling, public-address
checks and transport caps. A refusal remains a refusal; no fallback, alternate
user agent, cookie, credential or deeper crawl is configured.

Astrobites (HTTP 403) and AAS Nova (feed response cap) remain excluded. Feed
response cap 1 MiB, 60 fetches / 16 MiB per feed sweep, webpage depth 0, ordinary
robots policy, redirects, timeouts and all other limits stay unchanged.
