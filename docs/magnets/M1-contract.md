# Magnet M1: the contract

M1 is Magnet definitions independent of workspaces, one shared read in Rust, and a client that uses it. Nothing here is deployed by M1. Anything marked "not built" is a forward shape only.

## A definition

One file per `mag-` id: `<brain>/presentation/magnets/<id>.json`. It isn't in the record and adds no Kind. Python (`mentis/magnet`) is the only writer, atomically, under the lock arrangements are written under. The Rust front only reads these files.

- **Arrangements refer, definitions hold.** A kept arrangement holds zones naming an id. `magnets` on the arrangement wire is a projection of the definitions, so the client's shape is unchanged. One id can sit in several arrangements, and a reconfigure is seen in all of them the next time each is read. Nothing pushes it to a client already holding one.
- **`magnetsHeld`, on disk only:** ids an arrangement holds with no zone, so Undo finds what it took out. `POST .../magnets/<id>/remove` ends the hold, not the definition.
- **Lifting.** A file that still embeds `magnets` is read as it is, and a read never rewrites it. The first write to that arrangement lifts its entries and drops the map. `POST /fluid/api/magnets/lift` lifts every arrangement and rewrites none, so **run it once per Brain at deployment**: until then a Magnet has no definition, and the client uses its store path. Lifting is lossless and idempotent, keeps ids, doesn't de-duplicate and creates no Conversation. An embedded copy that disagrees with its definition is kept as `<id>.from-<key>.json`.
- **Roll back only before writing.** Once this build has written an arrangement, the file has no map, so an older build (`surface-tension`) refuses its Magnet zones. :8790 runs its own Brain and isn't affected.

## Removing and deleting

| Act | What goes |
|---|---|
| Zone out (`sharedZone` remove) | That placement. The arrangement holds the id |
| `POST /fluid/api/arrangements/<key>/magnets/<id>/remove` | That arrangement's hold. **Never the definition** |
| `POST /fluid/api/magnets/<id>/delete` | The definition, only once no arrangement places it. Refused with 422 while one does, and 409 if an arrangement can't be read, because it might be the one |

Undo and Redo go through create with the fixed `id`. A definition already kept is placed as it stands, so Undo can't roll back a later change, and `seed` may be left out. Only a Magnet nothing holds is written from its seed.

`mentis.magnet.references(root, magnet_id) -> [{"arrangement": key, "placed": bool, "held": bool}]` is the one answer to what refers to a Magnet. Anything that comes to refer to one must extend it, because delete relies on it. Named layouts need no look: `shape_of` keeps no Magnet in them.

## The schema

Everything is optional and additive. Absent reads as it always did, and nothing is defaulted in, so a definition round-trips exactly.

| Field | Values |
|---|---|
| `schema_version` | The file's, not on the wire. Absent is 1. **A later or malformed one makes the definition unavailable: never defaulted, and never overwritten.** Arrangement reads say so in `magnets_unreadable`, and the route as `unavailable` |
| `activation` | `manual`, `scheduled` (`schedule`), `event` (`event`), `source-change`, `condition` (`condition`) |
| `processing.operations` | Ordered, at most 20: `extract`, `compare`, `correlate`, `classify`, `transform`, `change-detect`, `other`, each with `name?` and scalar `options?` |
| `ai.mode` | `none` (the default in meaning), `selective`, `local`, `runtime`, `agent`, with `runtime?`, `model?`, `agent?` |
| `outputs` | `findings`, `structured`, `records`, `relationships`, `proposals`, `notifications`, `work` |
| `destinations` | `magnet-conversation`, `brain`, `workspace`, `workflow`, each with `ref?` |
| `presentation.theme` | `minimal`, `anchored`, `glass`, `floating` |
| Source kinds | Adds `agent-results`, `file`, `database` to the existing five |
| `conversation` | Nullable. See below |

Every one is saved and bounds-checked, and reported through `notRunning` and availability. **None is executed in M1.**

## A Magnet's own Conversation

`conversation` is its own field, distinct from any source, and only this writes it: `POST /fluid/api/magnets/<id>/conversation {author, name?, op?}` goes through `open_conversation`, under the authority any other Conversation creation has. It is created once, and asked again it answers the one it has. Two first requests make one. A reconfigure can't set it, and a new seed can't name one. Recovery by fixed id keeps it. M1 doesn't refuse a source that names the same Conversation.

## The read

`GET /fluid/api/magnets/<id>/read?mode=summary|page&source=&cursor=&types=`. It has the front's normal Fluid checks, runs with `ReadClass::Background` and is listed in the route table. The op is `mentis_ops::magnet::MagnetRead`, `NAME` `magnet_read`. It composes `collections::collected`, `Objects`, `heads`, `now_reads` and the existing tally. It adds no retrieval, index, thread, store, service or extraction pool. It knows no grant and reads no live state. The route reads the definition and passes it in `Args`.

| `mode` | Answers |
|---|---|
| `summary` | `title`, `about`, `activity`, `posts`. Never walks posts, closures, acts or objects, and its statement count doesn't grow with a Conversation |
| `page` | One bounded page per source (`PAGE`, 20 roots). Objects are read only for the types asked |

**Each source answers for itself** in `sources[]`: `source` (as defined), `key`, `status`, `reason`, `summary`, `results`, `next`, `dates`. Each result keeps its source, `version`, `conversation`, `author` and `at`. `source=` narrows a page to one source. **There is one cursor per source**, and a cursor without `source=` is 400.

| What happened | Answer |
|---|---|
| No place in the class for the whole request | **503** `{"kind": "Busy"}`. The client shows every source busy and doesn't fall back to the store |
| A source used its share of the deadline | 200, that source `busy`, the others answer |
| A source can't be read | 200, that source `unavailable` with a reason |
| Part of a source's objects weren't read | 200, that source `partial` with a reason |
| A later `schema_version` | 200, `unavailable` at the top, no sources |
| Bad `mode`, `types`, `cursor` or `source` | 400 |
| No definition, or an unreadable one | Forwarded. Python has no such route, so 404, and the client uses its store path |

**Selection in M1** applies `informationTypes` and `dates`. `after` is inclusive, `before` exclusive at the instant stated, and a date with no offset is UTC. A date this can't read is said (`applied: false`), not guessed. `dates` is on each source. `criteria`, `phrases`, `topics` and `filters` come back in `kept` with the reason: phrase semantics aren't decided, and Brain, agent-result and search sources depend on Track A's R5.1 `text_scan`.

### Limits, stated openly

- **Budget:** `MagnetRead::BUDGET` is per call. It grows with the sources in a definition (at most 20), never with what a Conversation holds.
- **Per-source shares aren't preemption.** A source's share is checked when a statement starts and at each row. **A statement already running is bounded by the existing `READ_SCOPE_LIMIT` (2 s), not by the share**, so a statement yielding no rows can use up the request.
- **Extraction.** It comes after the scope has gone, through the window's one shared engine queue, which has no notion of class. So `MagnetPlan::finish` reads posts one at a time and starts at most `UNCACHED_MOST` (4) uncached extractions per request. It may extract only while holding one of `FINISH_PLACES` (2), and stops at the handler's `FINISH_WITHIN` (4 s) or on abort. What's already kept costs no engine, and what's left answers `partial`. Asking again gets further, because what was read stays kept. A single extraction already running is bounded by the engine's own limit (2 s).
- **Abort.** The front watches this route's socket (`handlers::WATCHES_ITS_CLIENT`), and the client closing it sets `Ask::gone`. The op stops at the next statement or row, or the next post in `finish`, and the place goes back. The same bound on a running statement applies.

## The client

`MagnetSourceAdapter.fetch`, `search` and `summary` gain `at?: {magnet?, signal?}`. Leaving a Magnet aborts its read. The disc asks only for `summary`, and where the route answers it loads no Conversation: "new" comes from the source's activity, without a count, and the orbit counts posts until the Magnet is opened. Summary reads go one at a time and a Magnet's sources share one answer. Pages also go one at a time, so the client holds at most the class's two places. Where the route answers 404, everything reads through the store as before, for that Magnet.

## Shared fixtures

`tests/fixtures/magnet-conformance/` holds definitions, source keys, object types and answer shapes, checked by Python (`tests/test_magnet_definitions.py`), Rust (`crates/mentis-ops/tests/magnet.rs`) and the client (`apps/fluid-web/tests/fluid_magnet_route_unit.ts`). `tests/fixtures/magnets/` is a copy of the `fluid-dev` Brain's arrangement files, for migration.

## Forward shapes, not built

- **`WorkspaceObject`:** `{kind: magnet|conversation|chat|file|image|evidence|report|participant|other, ref, provenance, curated: true}`. A workspace holds references to these and owns its own identity and layout.
- **A workspace as agent context:** a request resolves the selected objects to their records, relationships, provenance and authorization. User-curated references stay distinct from authoritative Brain records: `curated: true` is never standing. The grant and reach rules aren't decided here.
