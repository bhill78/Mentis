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
| `POST /fluid/api/magnets/<id>/delete` | The definition, only once no arrangement refers to it, by a zone, a hold or a copy it still embeds, and no workspace curates it. Refused with 422 while one does, and 409 if an arrangement or a workspace manifest can't be read, because it might be the one. It changes neither: holds end only by `/remove`, and curating only by the workspace's `/objects/<oid>/remove` |

Undo and Redo go through create with the fixed `id`. A definition already kept is placed as it stands, so Undo can't roll back a later change, and `seed` may be left out. Only a Magnet nothing holds is written from its seed.

`mentis.magnet.references(root, magnet_id)` is the one answer to what refers to a Magnet. Anything that comes to refer to one must extend it, because delete relies on it. Named layouts need no look: `shape_of` keeps no Magnet in them. It answers a list, arrangements first by key, then workspaces by id:

| Item | Says |
|---|---|
| `{"arrangement": key, "placed": bool, "held": bool}` | An arrangement shows it in a zone, or holds it with none. `key` may be a workspace's id, for a workspace's layout |
| `{"workspace": id, "object": wob}` | A workspace curates it, as this object. A deleted workspace holds nothing |

## The schema

Everything new is optional and additive. Absent reads as it always did, and nothing is defaulted in, so a definition round-trips exactly.

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
| `sources` | **Each source once, by its key** (`kind:` and what names it): a status and a cursor are one key's. Python refuses a repeat in a seed, a reconfigure or a definition file, the Rust read declines such a file, and the client's `draftProblems` says so. An arrangement that already embeds a repeat stays readable: it answers with the first of each key, and lifting writes that. Different sources that only share a key keep their original entry beside the definition, as `<id>.from-<key>.json` |
| `conversation` | Nullable. See below |

Every one is saved and bounds-checked, and reported through `notRunning` and availability. **None is executed in M1.**

## A Magnet's own Conversation

`conversation` is its own field, distinct from any source, and only this writes it: `POST /fluid/api/magnets/<id>/conversation {author, name?, op?}` goes through `open_conversation`, under the authority any other Conversation creation has. The route ignores the client's `op` and uses its own stable `magnet-conversation:<id>` key; that prefix is reserved and the plain Conversation-open route refuses it. Other keyed doors may record that string as their operation key, but their different request does not reserve the Magnet's key and is skipped when this route looks for its outcome. It is created once, and committed with its key and its claim. Asked again it answers the one the record claims, with `created` false, correcting the file if it names another or none: that is also how a retry after a failed file write gets the same Conversation. With no claim it answers what the file names, as for a Magnet from before claims. With neither, an outcome already under the key, from before claims, is answered and claimed, not repeated. Two first requests make one even when their authors differ. A reconfigure can't set it, and a new seed can't name one. If a deleted Magnet is recreated under its old id, it gets its old Conversation back for every author. M1 doesn't refuse a source that names the same Conversation.

## Where an agent request goes

`POST /fluid/api/requests` is `POST /fluid/api/posts` with `from` where the request was started, in place of `conversation`, and with an operation key (`op`) it can't go without. It records, owes and dispatches through the same `posting.post`, and a result is said in the Conversation its request is in.

| `from` | Goes to |
|---|---|
| `{"workspace": id}` | The workspace's own Conversation, separate from its Magnets' |
| `{"magnet": id}` | That Magnet's own Conversation |
| `{"conversation": id}` | That Conversation |

A workspace's or Magnet's Conversation is created by the first request that goes to it, through `open_conversation`, and only then: making a workspace, curating it or reading it creates none. Only a request from a workspace may name a `destination`, `{"conversation": id}` or `{"magnet": id}`. That overrides the workspace's Conversation and creates nothing for it. Routing never reads a workspace's `objects`, so no Magnet is primary, however many there are.

The answer is the post's, with `route` `{rule, conversation, created}`. A workspace that isn't there is 404, a deleted one 410, an unreadable one 409, and all three hold with a `destination` too. The door is the Fluid server's and refuses a worker grant: an agent still asks through `/api/worker`, naming a Conversation.

**The record decides which Conversation, and the files follow.** One transaction commits the Conversation, the act claiming it for this workspace or Magnet (`own-conversation-claimed`), the request, what it owes, its key, and what it has to start (`agent-request-routed`). Only after that commit is `conversation` written to the file and the run started, so a file can lag the record but can't name a Conversation this door didn't commit. The claim is asked before the file: a file that names none, or names another, whether the record lacks that one (a restored Brain) or holds it (a stale or edited copy), is corrected from the claim, and the request goes to the claim. With no claim, a file naming a Conversation the record holds is still used, and no claim is made for it. With neither, a Magnet's Conversation is opened under the same `magnet-conversation:<id>` key the direct route uses, so an outcome already under that key, from before claims, is claimed and answered with `created` false, whoever opened it, not repeated. A claim is for good: a Magnet recreated under the same id has the same Conversation. A process can end at any point, and:

| Where it ended | What the record holds | What happens next |
|---|---|---|
| Before the commit | Nothing of this request | The retry makes it all |
| After the commit, before the file | The claim and the request | Any request finds the claim and tells the file, and no second Conversation is made |
| After the file, before the run started | The expectation, with no run | A retry of the key starts it |
| After the run's start or end was recorded | That start or end | A retry starts nothing. An interrupted run is a result to recover, as for any run |

A retry is the same `from`, `destination` and key, and is answered from where the request first went, even if the workspace has since been deleted. The same key for another request is 422. Nothing retries on anyone's behalf: work no retry asks for reads as owed and not started, and a recorded failure stays somebody's to continue. A file that can't be written refuses nothing, because the request already stands and the claim keeps answering.

**Not built:** a client that calls this door, resolving a workspace's objects as context, and placing a result in a workspace beyond its Conversation.

## A workspace's doors

Over `mentis.fluid.workspace_manifest`, on the Fluid server's door, which refuses a worker grant. Nothing here writes to the record. Each POST requires an operation key, `op`: without one it is 400. The same key and request answers `replayed` and writes nothing, even after the workspace is deleted.

| Route | Does |
|---|---|
| `GET /fluid/api/workspaces` | `{"workspaces": [...]}`, each in brief. A deleted one isn't listed, and an unreadable one is, saying why |
| `GET /fluid/api/workspaces/<id>` | `{"id", "manifest"}` |
| `POST /fluid/api/workspaces` `{name?, objects?, from?, op}` | Makes one: 201, or 200 when `replayed`. Blank with neither `objects` nor `from` |
| `POST .../<id>/rename` `{name, op}` | Renames it |
| `POST .../<id>/objects` `{object, op}` | Adds one, last. The answer names it in `object` |
| `POST .../<id>/objects/<oid>/remove` `{op}` | Takes that object out, and touches nothing it refers to |
| `POST .../<id>/reorder` `{order, op}` | Every object's id, each once, in the new order |
| `POST .../<id>/delete` `{op}` | Leaves its tombstone. Its Conversation, Magnets and arrangement aren't touched |

`from` is `{"magnet": id}` or `{"conversation": id}`. It seeds one curated object of that kind, first, whose provenance `source` names the same thing. That Magnet or Conversation has only to be there: nothing is asked of what it owns, and no Conversation or Magnet is made. A Magnet that isn't there is 422 and a Conversation that isn't 400, as a request names them. That is asked last: a request that is malformed or over a bound is 400 and a key used for another request 422, whether or not its seed is there, and a retry is answered by its key whatever has since become of either.

| What happened | Answer |
|---|---|
| A workspace that isn't there | 404 |
| A deleted one | 410 |
| An unreadable one, left as it is | 409 |
| An operation key used for a different request | 422 |
| Anything malformed, or over a bound, a key that no longer fits included | 400 |

**A workspace's layout is an arrangement under its id:** `GET` and `POST /fluid/api/arrangements/<wsp-id>`, and the Magnet routes under it, behave as under any key. It stays out of the manifest. A key with no such workspace is 404, a deleted one 410, an unreadable one 409. Conversation doors don't take a `wsp-` id, and the plain Conversation-open route refuses a `wsp-` operation key. An arrangement under a workspace that was deleted, or never was, isn't read: `references` and lifting pass over it, because no door could reach it to end a hold, and its file is left as it is.

## The read

`GET /fluid/api/magnets/<id>/read?mode=summary|page&source=&cursor=&types=`. It has the front's normal Fluid checks, runs with `ReadClass::Background` and is listed in the route table. The op is `mentis_ops::magnet::MagnetRead`, `NAME` `magnet_read`. It composes `collections::collected`, `Objects`, `heads`, `now_reads` and the existing tally. It adds no retrieval, index, thread, store, service or extraction pool. It knows no grant and reads no live state. The route reads the definition and passes it in `Args`.

| `mode` | Answers |
|---|---|
| `summary` | `title`, `about`, `activity`, `posts`. Never walks posts, closures, acts or objects, and its statement count doesn't grow with a Conversation |
| `page` | One bounded page per source (`PAGE`, 20 roots). Objects are read only for the types asked |

**Each source answers for itself** in `sources[]`: `source` (as defined), `key`, `status`, `reason`, `summary`, `results`, `next`, `dates`. Each result keeps its source, `version`, `conversation`, `author` and `at`. `source=` narrows a page to one source. **There is one cursor per source**, and a cursor without `source=` is 400.

A `summary` of a Conversation also says, on the source, `participants` (the first 12 to join as `{id, alias}`, in id order, with `participants_more: true` when there are others) and `latest` (`{id, at, author, preview}` of the newest post the tally counts, so not one only linked in, or null with no posts; `preview` is at most 200 characters of its text parts as it now reads, null if it is deleted or has none). Both are read at a cost that doesn't grow with the Conversation, from at most 256 joins and the last 16 links into it through the existing link index. A field it can't answer, including one those don't settle (those joins naming no more than 12 people, no post among those links, or a last post written that isn't the newest by time), is left out and named with its reason in `absent` (`[{field, reason}]`) and the summary stands, other source kinds and pages omit them, and who is active now stays unavailable because this reads no live state.

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

- **A workspace as agent context:** a request resolves the selected objects to their records, relationships, provenance and authorization. User-curated references stay distinct from authoritative Brain records: `curated: true` is never standing. The grant and reach rules aren't decided here.
