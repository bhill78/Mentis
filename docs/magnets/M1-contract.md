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

Every one is saved and bounds-checked, and what a value asks that this build doesn't run is said through `notRunning` and availability. **Nothing runs by itself.** Through the Rust front, one explicit `POST` runs "Manual activation" below, and only for a definition that passes "What can run":

| Field | Manual activation runs | Stays saved, and doesn't run |
|---|---|---|
| `activation` | `manual`, which absence isn't | `scheduled`, `event`, `source-change`, `condition` |
| `processing.operations` | Exactly one, `extract`, in mode `m1-page` | Every other operation, none, more than one, or any other `options` |
| `ai.mode` | Absent or exactly `none`, so no AI | `selective`, `local`, `runtime`, `agent` |
| `outputs` | Absent or exactly `records` | Every other output, or any other list |
| `destinations` | Absent or exactly `magnet-conversation`, with no `ref` | `brain`, `workspace`, `workflow`, a `ref`, or any other list |
| Source kinds | `conversation` | `brain`, `connector`, `web`, `other`, `agent-results`, `file`, `database` |

A definition asking for anything in the last column but a source kind is refused whole, with nothing read. Those source kinds answer `unavailable` beside a `conversation` source, so the page can't be `complete`, and a definition with no `conversation` source is refused. The other fields aren't saved-only either: the client draws a `presentation.theme` it knows and an activation doesn't ask about it, a later `schema_version` is refused, `sources` are what the page reads, and `conversation` is where it goes.

`notRunning` stops saying `processing`, `outputs` and `destinations` for a definition that passes "What can run". That is judged from the definition alone: nothing a server sends says whether it has the processor.

## A Magnet's own Conversation

`conversation` is its own field, distinct from any source, and only this writes it: `POST /fluid/api/magnets/<id>/conversation {author, name?, op?}` goes through `open_conversation`, under the authority any other Conversation creation has. The route ignores the client's `op` and uses its own stable `magnet-conversation:<id>` key; that prefix is reserved and the plain Conversation-open route refuses it. Other keyed doors may record that string as their operation key, but their different request does not reserve the Magnet's key and is skipped when this route looks for its outcome. Manual activation is one of them, and it skips this route's outcome in turn, so an activation under that string writes once and then replays even where this route's outcome is under the same author and key, in the same transaction or before it. It is created once, and committed with its key and its claim. Asked again it answers the one the record claims, with `created` false, correcting the file if it names another or none: that is also how a retry after a failed file write gets the same Conversation. With no claim it answers what the file names, as for a Magnet from before claims, and an activation of that Magnet claims what the file names. With neither, an outcome already under the key, from before claims, is answered and claimed, not repeated. Two first requests make one even when their authors differ. A reconfigure can't set it, and a new seed can't name one. If a deleted Magnet is recreated under its old id, it gets its claimed Conversation back for every author. M1 doesn't refuse a source that names the same Conversation.

**Its name comes from the Magnet, whichever door opens it** (this route with no `name`, an activation, a request from the Magnet): `<name> (Magnet)`, where `<name>` is the current name of the one Conversation it reads, else the name on its zone, else the name of its lone operation, and `Magnet <id>` with none of those. So it isn't "Unnamed", and it can't be taken for its source. It isn't provisional. A `name` given to this route still wins. The key's recorded request doesn't hold the name, so an outcome under the key from before names were given replays as it did, and nothing already opened is renamed.

## Where an agent request goes

`POST /fluid/api/requests` is `POST /fluid/api/posts` with `from` where the request was started, in place of `conversation`, and with an operation key (`op`) it can't go without. It records, owes and dispatches through the same `posting.post`, and a result is said in the Conversation its request is in.

| `from` | Goes to |
|---|---|
| `{"workspace": id}` | The workspace's own Conversation, separate from its Magnets' |
| `{"magnet": id}` | That Magnet's own Conversation |
| `{"conversation": id}` | That Conversation |

A workspace's or Magnet's Conversation is created by the first request that goes to it, through `open_conversation`, and only then: making a workspace, curating it or reading it creates none. Only a request from a workspace may name a `destination`, `{"conversation": id}` or `{"magnet": id}`. That overrides the workspace's Conversation and creates nothing for it. Routing never reads a workspace's `objects`, so no Magnet is primary, however many there are.

**Only a request from a workspace may select `objects`:** an ordered list of `wob-` ids, at most the 200 a workspace can hold. Left out, the work may read all the workspace holds. An empty list selects nothing, and null is malformed, not "everything". Selecting routes nothing, and a selection is never added to the manifest. Nothing is recorded or started when one is refused, and the key stays free for a corrected request:

| What `objects` is | Answer |
|---|---|
| On a request from a Magnet or a Conversation | 400 |
| Not a list, over the bound, not `wob-` ids, or naming one twice | 400 |
| Naming an object the workspace doesn't hold, whether no workspace does or only another does | 422, its ids in `objects` |

**The record keeps a selection as `selection` on `agent-request-routed`,** in order, and only when one was made. It is digests of the workspace and object ids, not `wob-` ids: `history` shows an act's detail, an object's id is a hash of its ref, and under a `destination` the act doesn't name the workspace. So the digests say nothing without the workspace's id. **Limit:** somebody who can read that act and already has the workspace's id and a ref can test whether that ref was selected, and nothing more.

The answer is the post's, with `route` `{rule, conversation, created}`. A workspace that isn't there is 404, a deleted one 410, an unreadable one 409, and all three hold with a `destination` too. The door is the Fluid server's and refuses a worker grant: an agent still asks through `/api/worker`, naming a Conversation.

**The record decides which Conversation, and the files follow.** One transaction commits the Conversation, the act claiming it for this workspace or Magnet (`own-conversation-claimed`), the request, what it owes, its key, and what it has to start (`agent-request-routed`). Only after that commit is `conversation` written to the file and the run started, so a file can lag the record but can't name a Conversation this door didn't commit. The claim is asked before the file: a file that names none, or names another, whether the record lacks that one (a restored Brain) or holds it (a stale or edited copy), is corrected from the claim, and the request goes to the claim. With no claim, a file naming a Conversation the record holds is still used, and no claim is made for it. With neither, a Magnet's Conversation is opened under the same `magnet-conversation:<id>` key the direct route uses, so an outcome already under that key, from before claims, is claimed and answered with `created` false, whoever opened it, not repeated. A claim is for good: a Magnet recreated under the same id has the same Conversation. A process can end at any point, and:

| Where it ended | What the record holds | What happens next |
|---|---|---|
| Before the commit | Nothing of this request | The retry makes it all |
| After the commit, before the file | The claim and the request | Any request finds the claim and tells the file, and no second Conversation is made |
| After the file, before the run started | The expectation, with no run | A retry of the key starts it |
| After the run's start or end was recorded | That start or end | A retry starts nothing. An interrupted run is a result to recover, as for any run |

A retry is the same `from`, `destination`, `objects` and key, and is answered from where the request first went, even if the workspace has since been deleted or the object has since been taken out. The same key for another request is 422, and that includes selecting differently, in another order, or leaving out or adding `objects`: the first accepted selection stands. Nothing retries on anyone's behalf: work no retry asks for reads as owed and not started, and a recorded failure stays somebody's to continue. A file that can't be written refuses nothing, because the request already stands and the claim keeps answering.

**Not built:** a client that calls this door, resolving a workspace's objects as context, and placing a result in a workspace beyond its Conversation. A result post is not added to the manifest, which holds what somebody curated.

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

A `summary` of a Conversation also says, on the source, `participants` (the first 12 to join as `{id, alias}`, in id order, with `participants_more: true` when there are others) and `latest` (`{id, at, author, preview}` of the newest post the tally counts, so not one only linked in, or null with no posts; `preview` is at most 200 characters of its text parts as it now reads, null if it is deleted or has none). Both are read at a cost that doesn't grow with the Conversation, from at most 256 joins and the last 16 links into it, plus one more to prove whether all links were read, through the existing link index. A field it can't answer, including joins naming no more than 12 people or a Conversation with more links than that bounded read can exhaust (accepted imports need not put a post before its link), is left out and named with its reason in `absent` (`[{field, reason}]`) and the summary stands, other source kinds and pages omit them, and who is active now stays unavailable because this reads no live state.

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

## Manual activation

**Both halves are built: the Rust door and processor (`crates/mentis-server/src/front/activate.rs`) and Python's validation and materialization (`mentis/magnet/activation.py`).** Both are built against this section and `tests/fixtures/magnet-conformance/activation/`. Where the words and a fixture differ, that is a defect in this contract, not a choice for either side.

One explicit `POST` materializes one bounded, provenance-preserving M1 page in the Magnet's own Conversation. `m1-page` is the first mode of `extract`, not what `extract` means: other modes are neither designed nor ruled out here. No schedule, event, source change, condition, agent or background trigger can start it.

| Who | Owns |
|---|---|
| **Rust** | The public door, the public body limit, the M1 read, the exact artifact bytes, classifying Python's answers, cancellation and the deadlines. It never writes the Brain |
| **Python** | The body's fields, the author, the key, the definition, the schema, the executable subset, every semantic refusal's words, verifying the artifact, the held bytes and every record write |

Once a commit is complete:

- One transaction holds the claim on the Conversation when absent, including one the file already names, the Turn, its Admission, its `magnet-extracted` act, the `produced` link and the keyed result.
- A same-key replay writes nothing, doesn't read the definition, and answers the first result even if the Magnet has since changed or gone.
- At most one activation at a time holds a page or an artifact for the handoff: there is no queue and no retry.

### The public request

`POST /fluid/api/magnets/<id>/activate`, with a body of exactly `{"author": "ent-...", "op": "..."}`.

**The door, Rust's and in Python's order and words.** `door.json` has the exact bytes. Every row that exists at this commit is held against Python's real door.

| # | Check | Refused with |
|---|---|---|
| 1 | The head can't be read: a `Content-Length` of anything but digits, two of them, a header line that isn't `Name: value` | **400, an HTML page,** in `parse_request`'s words. This is before Host, so a foreign Host doesn't change it. `do_POST`'s JSON answers for a bad length are never reached |
| 2 | Host | 421 |
| 3 | Any `Transfer-Encoding` | 501 |
| 4 | `X-Mentis-Client`, unless a worker grant is presented | 403 |
| 5 | A worker grant (`X-Mentis-Worker`) | 403, naming the path, whether or not the client header came. It can't reach preflight |
| 6 | A non-empty body whose type isn't `application/json` | 415. An empty body is exempt, goes on as `{}`, and gets Python's 400 for it |
| 7 | A body over 65,536 bytes | 413, this package's own bytes. 65,536 is accepted. It comes after the door, and before parsing or preflight |

**`Content-Length` spellings, pinned.** `+2`, `-1`, `-0`, `x`, an empty value, `2 ` (trailing space), `1_0`, `0x2`, `2.0`, a non-ASCII digit and a folded value are all row 1. Accepted: absent or `0` (an empty body), plain digits, leading zeros (`00053`, or thousands of them), and leading spaces, which the header parser removes before anything looks.

**A very long `Content-Length` is only over the limit, and leading zeros count for nothing** (`door.json`, the `very_long_length` and `long_leading_zeros` rows). Digits of any length pass row 1 and are read by the number they spell, never by how many were sent. 5,000 zeros are an empty body, for row 6 too. The same zeros then `53` are a body of 53 bytes, then `65536` is accepted and then `65537` is refused. Anything over 65,536, however far past 64 bits or Python's integer-string digit limit, is row 7's 413 with nothing read, and rows 2 to 6 still answer first, in their own words.

**Python's shared door fails these on its other paths in two ways. Both are defects, not a difference between the halves. Package C fixes them for this route, and the rest are `ent-d613f231201d` and `ent-1225b30e0f08`:**

- **Overflow.** With 4,300 digits or fewer, a value of 2^63 or more answers **500** on a path that names a Fluid command, because `_read_body` fails with `OverflowError` before the client, grant, type or size is looked at (a smaller one may fail with `MemoryError` or `OverflowError`, depending on the machine). A path that names no command answers its 405, which comes before the read.
- **The digit limit.** Past 4,300 digits, Python's default limit on reading an integer from a string, leading zeros included, `int()` raises `ValueError` in `do_POST`, before any routing. The 400 meant to answer it goes through `send_response` to `_discard_small_body`, whose own `int()` raises again, so the answer is **500** on every POST path, command or not. A refused Host's 421 takes the same way out and becomes that 500, and 5,000 zeros are a 500 too. Only the 501 for `Transfer-Encoding` survives, because `_discard_small_body` returns before its `int()`.

On this route's exact path, Python alone gives every such row the answer in its `expect` or `reaches`, the 413's bytes included, and never reads a body past the limit. So the length is read by value before either `int()` sees it (`_Handler._declared_length`): a fix in `handle_post` or `_read_body` would come too late for the second failure. The `python_today` fields record what the sibling path still does.

Past the door, Rust hands the exact body bytes to preflight, and Python decides, in this order and on Python alone too:

| # | Check | Answer |
|---|---|---|
| 1 | A malformed Magnet id (`schema.MAGNET_ID`), asked of the raw path segment as sent, never percent-decoded. `mag-bad!` and `mag-a%2fb` are both malformed. Whatever the body holds | 400 |
| 2 | **Nested more than 64 levels** of `[` and `{`, asked of the text `json.loads` would read and before it does. Whatever is inside a string doesn't count | 400, `body-too-deep`, in fixed words. Where `json.loads` gives up depends on the interpreter, and `commands.py` catches only `ValueError`, so without this one body would be a 400 here and a 500 there |
| 3 | Not JSON | 400, `the body is not JSON: ...`, as every Fluid POST, with `json.loads`'s own words (`public_bodies.json`, `not-json-*`) |
| 4 | **A lone surrogate anywhere in the body,** escaped or as raw bytes, even under a field that would be refused | 400, and its words don't echo the value. `json.loads` keeps one, and a private answer can't encode it |
| 5 | Not an object | 400 |
| 6 | Any field but `author` and `op`: `page`, `artifact`, `definition`, `digest`, `cursor`, `sources`, `types`, `mode`, `destination`, `operation`, a protocol field or a ticket | 400 |
| 7 | `author` absent, not text or blank | 400, in `commands._author`'s words |
| 8 | `author` the record doesn't hold, or holds as something other than a Participant | 422, in `commands._author`'s words |
| 9 | `op` absent, not text, blank or over 200 characters | 400 |
| 10 | The key already used for this activation | The stored result, as a replay |
| 11 | The key used for another request | 422, in `anchors.prior_outcome`'s words |

**Every walk for a surrogate keeps a stack of its own, and is never by recursion:** the public body, a definition's value and an artifact can each hold a depth that recursion in Python wouldn't reach.

### What can run

Python answers `ready` only for a definition that passes the full schema and every line below. The first that fails decides, in this order, each with its own code (`definitions.json`). A later `schema_version` is this list's first refusal, while a malformed one is `Unreadable`.

| Must be | Else |
|---|---|
| `schema_version` absent or one this build supports | `schema-version-not-supported` |
| `activation.mode` `manual` (absent isn't) | `activation-not-supported` |
| `collection.mode` `one-time` | `collection-not-supported` |
| `synthesis.mode` `manual` | `synthesis-not-supported` |
| Every notification flag false | `notifications-not-supported` |
| `processing.operations` exactly one, `extract`, with `name` optional | `pipeline-not-supported` |
| `options` absent, empty or exactly `{"mode": "m1-page"}` | `extract-mode-not-supported` |
| `ai` absent or exactly `{"mode": "none"}` | `ai-not-supported` |
| `outputs` absent or exactly `["records"]` | `output-not-supported` |
| `destinations` absent or exactly `[{"kind": "magnet-conversation"}]`, with no `ref` | `destination-not-supported` |
| At least one source of kind `conversation` | `no-readable-source` |

Absence of outputs or destinations resolves to this behaviour and doesn't rewrite the definition. Other source kinds answer `unavailable` beside a conversation source.

**Reading the definition.** Python first validates the body and looks up the key, before reading or changing anything about the Magnet. With neither a replay nor a collision, it takes the definition lock and runs the existing embedded-definition lift, so an unlifted Magnet doesn't get a false 404. Then it tests for absence, reads the exact bytes once and hashes them. Replay does neither.

| The bytes | Answer |
|---|---|
| None | 404 |
| At most 262,144 | May proceed |
| Over 262,144 | **409 `Unreadable`,** asked of the bytes, because `mentis.magnet.read` has no size check. Before `ready`, so nothing is read or committed |
| Not UTF-8, including a raw surrogate, or not JSON, or not a definition, or naming another id | 409 `Unreadable`, in `mentis.magnet.read`'s words |
| **A lone surrogate in the decoded value** (`\ud800` in the file is valid JSON and ASCII) | 409 `Unreadable`, not echoing it |

### The private protocol

On the public port the front decides every `/private/*` request itself and forwards none, so these paths answer the existing 404 there, and a forged page can't reach them. On Python's private loopback port they exist only when a boot secret is configured, and they require it exactly. Python alone has neither.

- `POST /private/magnets/<id>/activate/preflight`: `{"protocol": 1, "magnet": "<id>", "public_body_base64": "..."}`, standard base64 with padding, of the exact public body. Anything else in that shape is `internal-protocol-error` with no identity. `<id>` is here, in the path and in `magnet`, the **raw path segment** as the public request sent it. This route takes any one segment, so a malformed id reaches Python's first check and is never a 404. That answer is `refused`, status 400, with the raw segment in `magnet` and `author` and `op` `null` (`answers.json`, `refused-magnet-id-*`). A segment of more than 65,484 bytes would make a preflight's request line longer than `http.server` reads, though the public line fit. It can't be an id, so the front forwards the public request as it came, and Python's door gives that same 400's body.
- `POST /private/magnets/<id>/activate/commit`: the exact artifact bytes, as `application/json`, with `X-Mentis-Artifact-SHA256`. Not an envelope, and not base64.

Every private answer is an HTTP 200 carrying bounded JSON with `protocol`, `state` and `magnet`. **Its bytes are `json.dumps(..., ensure_ascii=False)` as UTF-8, at most 1 MiB (1,048,576 wire bytes).** A definition capped at 256 KiB may appear as both `raw` and `value`, at most 3 bytes across them per byte of the definition, so 786,432 bytes, leaving 262,144 for the envelope.

Before building any private answer, Python refuses text that cannot be encoded as UTF-8. A lone surrogate anywhere in the public body is `400`, and its wording does not echo the value. One in a definition's decoded value is `409 Unreadable`. One anywhere in a commit's artifact is `internal-protocol-error` with no identity and no write.

| `state` | Phase | Carries |
|---|---|---|
| `ready` | Preflight | `request` `{author, op, identity}` and `definition` `{sha256, raw, value}`. No public status or body |
| `refused` | Both | `author`, `op`, `status`, `body`: the exact public status and whole public body. Preflight 400, 401, 404, 409, 422 or 503. Commit 401, 413, 422 or 503 |
| `internal-protocol-error` | Both | `author`, `op`, public `status` 502 and its whole `body`. No write |
| `committed` | Commit | `author`, `op`, `status` 201, `body`: the whole stored result |
| `replay` | Both | The same envelope in either phase: `author`, `op`, `status` 200, `body`: the stored result, with the fresh top-level cursor |

`author` and `op` are each a string once Python has validated that field, and otherwise `null`. `ready`, `committed` and `replay` require both as strings. `refused` and `internal-protocol-error` may carry `null` for any field not validated when Python answered: a malformed id or body, an unknown author, an early commit `503 Busy` sent before the artifact is read, or an artifact that doesn't parse or holds a surrogate. `request.identity` (`{route, magnet}`) is unchanged.

Preflight has no comparand: Rust does not parse the public body and only checks an answer's shape. On a commit answer, Rust compares each non-null `author` and `op` with the `ready` answer it holds.

**The owner's authentication (round 4).** An activation writes the record, so it needs the owner's live session, as every other owner write does (`mentis.owner_auth`; `docs/modernization/CONTRACT.md`, "Round 3 final — B3" and "Round 4 — C1"). The boot secret proves only that the sender could read it, which any process of the same Windows user can, so it is not the owner. The front sends both private steps the public request's first `Authorization` and every `Cookie` line, as they came (a value holding CR, LF or NUL is not sent), and nothing else of the public head. Python checks them first at each step with `_owner_session`, the one session check, before reading the body: without a live session the answer is `refused`, status 401, `author` and `op` `null`, body `refusals.json`'s `owner-auth-required`, and nothing is read or written. Rust decides nothing about the session: it passes Python's 401 on as it does any refusal.

`replay` has the same envelope in either phase, plus the fresh top-level cursor. A preflight key collision is `refused` with `422`, replacing the separate `collision` state.

Rust validates the protocol version, `magnet` against the raw path segment it sent, which fields the state must have and may not have, the state against its status and body, and the body's shape. `definition.sha256` must be the digest of `raw`. It must not make up an identity, or reject an otherwise valid answer because Python couldn't safely recover one. A public body goes on as `json.dumps(body)` makes it, which is what `Py::dumps` writes, so a refusal is the same bytes whichever side said it.

**What Rust makes of an answer** (`answers.json` has every case):

| What happened | Preflight | Commit |
|---|---|---|
| A complete, well-formed answer | It decides. `ready` goes on to the read | It decides, including a complete early `503 Busy` |
| Timeout, reset, disconnect, a truncated answer, or no connection at all | **503 Busy,** no read and no commit. Safe, because preflight's only possible write is the idempotent lift | **503 `OutcomeUnknown`** |
| Complete but over 1 MiB, not JSON, an unknown or wrong-phase state, another HTTP status, a field missing, or a status or body that disagrees with its state | **502 `InternalProtocolError`,** no read and no commit | **503 `OutcomeUnknown`** |
| An identity that isn't the one held | Nothing to compare | **503 `OutcomeUnknown`** |
| `ready`, and `MagnetDefinition::parse` refuses what Python approved | **502 `InternalProtocolError`.** A disagreement between implementations, not configuration | Not reached |

`OutcomeUnknown` names the key and requires retrying with it, and a new key may record a second activation. Python may answer before consuming the whole body. If the whole answer arrives it decides. If the connection resets instead, the result is `OutcomeUnknown`: Rust must not infer that no write occurred.

### The artifact

Rust serializes it, and Python verifies it. Its bytes are `json.dumps(artifact)`'s default form, which is what `Py::dumps` writes: ASCII, `", "` and `": "`, no trailing newline, members in the order below. Those are the exact bytes hashed, sent and held.

```json
{"format": "mentis.magnet-extract", "version": 1, "mode": "m1-page", "magnet": "mag-...",
 "request": {"author": "ent-...", "op": "...", "identity": {"route": "fluid-magnet-activate", "magnet": "mag-..."}},
 "definition": {"sha256": "<digest of raw's UTF-8>", "raw": "<exact definition text>", "value": {}},
 "operation": {"index": 0, "op": "extract", "mode": "m1-page", "name": null, "options": {}},
 "page": {}}
```

`definition.raw` re-encoded as UTF-8 reproduces the bytes `sha256` covers. `definition.value` is what `mentis.magnet.read` makes of it, and not something the digest covers. `operation.options` is `{}` where the definition says none. `page` is the whole `MagnetRead` page answer, with its sources, statuses, reasons, results, per-source `next`, dates, `kept` and `cursor`.

**At most 25 MiB (26,214,400 bytes) of artifact.** Rust refuses more with 413 before sending anything, and Python enforces it too, before parsing. That 413 and the public body's are different bytes.

**Python's checks on a commit, in order** (`artifacts.json` spoils each in turn):

1. The cap, before parsing.
2. The digest against the header.
3. That it parses, a parser giving up on its depth included, and **holds no lone surrogate anywhere,** in `author`, `op`, `definition.raw`, `operation.name`, `page.kept` or any other string or key. Past this, Python could write the record and then be unable to encode its answer. So it comes before anything is named: `author` and `op` are `null`.
4. The format, version, mode and Magnet id.
5. The author, the key and the fixed identity, again.
6. `raw` against `sha256`.
7. The full definition and the executable subset, again, on `raw`, and `value` equal to what that gives. The operation must be what the definition says.
8. The page: its Magnet and mode, a cursor exactly as `change_cursor` writes one, each source configured and in order, its key, status and results, and no `summary` on a page. A post read `via: "home"` names its source's Conversation. A post read `via: "linked"` and a result of another kind name their own home, which M1 reports and may be another Conversation, so their `conversation` isn't compared with the source's.
9. The useful-source rule, again.
10. The key, inside the write transaction.
11. That the Magnet still exists.
12. The write.

A definition changed after preflight doesn't invalidate the activation, because the artifact keeps the earlier bytes. One deleted is 422 `magnet-deleted-during-activation`, with nothing written and no key consumed. A failure in checks 2 to 8 is `internal-protocol-error`, with nothing written, and with `author` and `op` `null` for whatever wasn't yet validated.

### What a page comes to

A source is **useful** only if it contributes at least one result to the page. A `partial` source with no results is not useful; neither is an `ok`-empty, `busy`, or `unavailable` source.

| The page | Answer |
|---|---|
| At least one useful source, every source `ok`, nothing in `kept` | `complete`. It means this page, not that a source is exhausted: `next` may be non-null |
| At least one useful source, and anything else | `partial`. A replay can't make progress, and a new key is a new activation and a new Turn |
| No useful source, any `busy` | 503 `Busy` |
| No useful source, none `busy` | 422 `no-readable-source`. Its machine code stays, and its words say what's true of both cases: no source produced a useful result. It also covers a readable Conversation with no results |

Neither refusal writes anything. Rust answers them after the read without committing, and Python enforces the same from the page. `useful_sources.json` has each case.

### The answer

First commit 201, replay 200. `results.json` has the exact bytes.

```json
{"magnet": "mag-...", "operation": {"index": 0, "op": "extract", "mode": "m1-page", "name": null},
 "state": "complete", "conversation": "ent-...", "conversation_created": false, "post": "ent-...",
 "artifact": {"ref": "adm-...", "digest": "<sha256>", "size": 12345, "media_type": "application/json"},
 "page": {"cursor": "f1....", "sources": 2, "results": 31, "statuses": {"ok": 2, "partial": 0, "busy": 0, "unavailable": 0}, "kept": []},
 "replayed": false, "cursor": "f1...."}
```

This is the whole shape of a `committed` or `replay` body, every field at every level and no other: Rust checks each field's presence and type, and `operation.name` is text or `null`. The keyed result stores everything but `replayed` and the top-level `cursor`. `page.cursor` is the one the artifact captured. The top-level one is read after the commit or replay, so a replay reports the record as it is now and the page as it was.

Every refusal is in `refusals.json`, with its status, body, exact bytes and who says it. Those about what runs have the neighbouring shape: `{"error", "refused": true, "magnet", "reason": {"code", "message", "retryable"}}`.

| Status | When |
|---|---|
| 400 | The door's, or a malformed id or body |
| 404 | No definition at preflight |
| 409 `Unreadable` | Above |
| 413 | The public body, or the artifact |
| 421, 415, 403, 501 | The door's |
| 422 | Unknown author, a key used for another request, unsupported configuration, later schema, no useful source, deleted during the activation |
| 502 `InternalProtocolError` | The two halves disagree, and nothing was written. An implementation defect, not a configuration to change |
| 503 `Busy` | The one place is taken, preflight was interrupted, or no useful source and one busy |
| 503 `OutcomeUnknown` | The commit may have happened. Retry with the same key |
| 503 `ProcessorUnavailable` | Python alone, or the rule rolled back: on the exact path and its trailing-slash spelling, it runs every check on the body, refuses as they refuse, answers a valid body with this, and never records an activation |

### Keys, races and recovery

The keyed identity is `{"route": "fluid-magnet-activate", "magnet": "<id>"}`, and the key is (author, `op`, that identity), through `anchors`.

- **Crash before the commit:** nothing durable, and the same key runs again.
- **Lost answer:** `OutcomeUnknown`. The same key finds the result or safely runs again. A new key may record a second activation.
- **The permits are not queues.** Rust holds one materialization place, taken before the read and held through the commit's answer, and Python holds one commit place. A request overlapping a holder gets 503 Busy where a complete Busy answer is available. After commit bytes have begun, failing to receive that answer is `OutcomeUnknown`. So an overlapping same-key request is Busy, not automatically a replay, and an overlapping different-key request doesn't automatically make a second Turn.
- **With commits that don't overlap,** once both preflights are done: the same key writes once and then replays, and different keys each write a Turn in one stable Conversation.
- **Beside the existing `magnets/<id>/conversation` route:** one claim, the same Conversation to both, and no duplicate or orphan. The route's own outcome under `magnet-conversation:<id>` is not a collision for an activation using that string as its key.
- **A file naming a Conversation the record holds, with no claim:** that Conversation is claimed in the commit, so a Magnet recreated under its id gets it back. A commit that refuses or fails leaves no claim.
- **A definition-file write failing after the commit** leaves the claim and the answer standing. A replay answers them, and a later request corrects the file.

### Cancellation and bounds

The route is in `handlers::WATCHES_ITS_CLIENT`. The last cancellation point is after the artifact is serialized and immediately before Rust writes the first byte of the commit request. `until_it_leaves` stops watching once the read finishes, so this needs its own check. Before that point, a client leaving means nothing is written. From that byte on, Python may commit though the client has gone, and recovery is by the same key.

Both looks read what the client sent ahead into the connection's buffer, where it stays for the next request, so those bytes don't hide the end of its stream. A half-close is taken for leaving: nothing tells the two apart. **The one exception is a client that sent 64 KiB or more ahead and then left.** The buffer stops there so that a client can't make the front hold more, and the end of its stream is behind what wasn't read, so the commit goes out. Its record is no worse than a client leaving just after the last look, and recovery is the same.

| Bound | Value |
|---|---|
| Public body | 64 KiB of wire bytes |
| Definition | 256 KiB of exact bytes |
| Private answer | 1 MiB of wire bytes |
| Artifact | 25 MiB, at most one held by either process, so 50 MiB of raw handoff across the pair, beside bounded M1 and JSON overhead |
| Preflight, connecting through its whole answer | 2 s |
| Commit, from its first byte through its whole answer | 5 s |
| Python holding its commit place for a body still coming | 5 s, then `internal-protocol-error` with nothing written, and the connection ends |
| Materialization and commit places | One each, not queued |

M1's own limits stay as "Limits, stated openly" has them. There is no queue, executor, scheduler, durable job state, retry loop, database or runtime.

### The record

One Python write transaction atomically records:

- the stable Magnet Conversation claim, when absent;
- the `record-only` Turn through `posting.post`, including its required `turn-said` act and Admission file part;
- the Admission;
- the `magnet-extracted` act;
- the `produced` relationship from that act to the Admission;
- the operation-keyed outcome.

No committed state may contain the Turn without `turn-said`, or any proper subset of this record set. Held bytes may precede the transaction and remain only as an inert unnamed blob after a crash. Conversation-file correction remains post-commit and does not alter the committed claim.

`magnet-extracted` records the actor, the Magnet Conversation, the Turn, the Admission in `about`, the Magnet id and mode, the operation's index and name, the raw definition's digest, the page cursor and state, the source-status and result counts, and the artifact's ref, digest and size. The Turn says it in a few words and names the Admission as a file part: the page isn't copied into its text. The context cache classifies the act as moving its own Conversation and nothing else, as it does `turn-said`.

### What this doesn't include

Schedules or triggers, continuous collection, notifications, connector or file sources, other pipelines, structured extraction, AI, agents or MARS, other destinations, migrating saved definitions silently, or deployment.

### The client's controls

`magnet/provider.ts`, in the one registry, and said in the Magnet's pane by `ActivationBar`:

| Action | Does |
|---|---|
| `magnet.activate` | One press is one key, kept from before it is sent until an answer says what came of it, past a reload (`magnet/activation.ts`). Disabled with the server's words where `activationRefusal` fails. Nothing presses for anybody. Running, complete, partial, Busy and every refusal are said in the server's words, and a result offers its post in the Magnet's own Conversation |
| Asking again | After `OutcomeUnknown`, no answer, or any failure that doesn't say nothing was written, the next press uses the kept key and author, and only that key. Asking under it, only a result or a 400, 404, 409 or 422 lets it go: a Busy says nothing about the lost answer |
| `magnet.setUpActivation` | Offered where a definition lacks manual activation or a step and asks for nothing else. Adds what it lacks to the same id through `magnet.reconfigure`, on that press alone. A definition asking for something else is its own to change in the editor |
| `magnet.conversation` | Asks `POST .../conversation {author}` and opens what it answers, never a source. The record decides, so it asks each time, and only this press can make one |

New Magnets from Fluid (`conversationSeed`) carry `activation {mode: manual}` and one `extract` step and nothing else: `ai`, `outputs` and `destinations` stay absent. The editor has a section each for activation, processing, AI, outputs, destinations and theme. Each value says whether it runs or is kept and not run, reusing `notRunning`. "Not set" takes a facet out, so what is unset stays absent. A list is never left empty, since `[]` asks for something absence doesn't. **`magnet.reconfigure` takes `null` for `activation`, `processing`, `ai`, `outputs` or `destinations`, which takes that facet out.** The other six are required, and null is still refused.

The boot secret now gates a write: `docs/rust/contracts/launcher.md`, "The secret".

## The client

`MagnetSourceAdapter.fetch`, `search` and `summary` gain `at?: {magnet?, signal?}`. Leaving a Magnet aborts its read. The disc asks only for `summary`, and where the route answers it loads no Conversation: "new" comes from the source's activity, without a count, and the orbit counts posts until the Magnet is opened. Summary reads go one at a time and a Magnet's sources share one answer. Pages also go one at a time, so the client holds at most the class's two places. A disc's hover reads one page once the pointer has rested (`glance`), waiting for and holding both lanes, so it takes one of those places and never stands beside another of this client's reads; leaving aborts it, and 503 shows Busy. Where the route answers 404, everything reads through the store as before, for that Magnet.

## Shared fixtures

`tests/fixtures/magnet-conformance/` holds definitions, source keys, object types and answer shapes, checked by Python (`tests/test_magnet_definitions.py`), Rust (`crates/mentis-ops/tests/magnet.rs`) and the client (`apps/fluid-web/tests/fluid_magnet_route_unit.ts`). Its `activation/` directory is "Manual activation"'s, checked by `tests/test_magnet_activation_contract.py`, `crates/mentis-ops/tests/magnet_activation.rs`, `crates/mentis-server/tests/magnet_activation_door.rs` and `crates/mentis-server/tests/magnet_activation_front.rs`. `tests/fixtures/magnets/` is a copy of the `fluid-dev` Brain's arrangement files, for migration.

## Forward shapes, not built

- **A workspace as agent context, beyond the read below:** a request resolves the selected objects to their records, relationships, provenance and authorization. User-curated references stay distinct from authoritative Brain records: `curated: true` is never standing.

## What an agent may read of a workspace

`workspace_objects(workspace)` through `/api/worker`. Python's door only: the Rust front forwards it. **This amends the boundary that gave agents no presentation context, for the manifest only.** Layout, theme and arrangements stay unreadable by construction: it answers `workspace_manifest.curated_references`, the frozen fields and no unknown one. It never resolves a reference, returns bytes or writes anything, and `curated: true` is never standing.

**Which workspace.** A run may read W only if the request it carries, or an ancestor in its delegation lineage, was routed from W by `POST /fluid/api/requests`, as its `agent-request-routed` act says. That lineage is who handed the work out, read from the delegation acts and not from `caused_by`: a delegated child follows the request that delegated it, and picked-up work follows its latest pick-up's `picked_up_under`, not the work it was found under. A continuation was not handed out, so it reads W only if it was itself routed from W. Under a `destination` that act names W only in its digest, so the digest is recomputed for the W asked about. This holds when a destination overrode W's Conversation. Anything else is refused, before W is looked at, so a refusal says nothing of whether W exists: naming a `wsp-` id gives nothing, and being in W's Conversation gives nothing. It costs a few indexed reads per request in the lineage. A Quick Ask and a hand-started session carry no routed request and don't hold the operation.

**Which objects.** With no selection, all the workspace now holds, in the frozen fields it always answered: neither `selection` nor `missing` is there. With one, and only then, `selection` says `explicit`, in every `state`, and the answer is what the request selected, in that order, read from the manifest as it now is. It comes from the act that routed the work, so a delegated child reads what its ancestor selected, and the worker's arguments can't change it. Whatever else the workspace holds isn't asked, counted or said, whenever it was added. A selected object it no longer holds answers `{curated, missing: true, reason}` in its place, with no kind, ref or id, and `missing`, on a `held` answer, counts them. An object's id is its kind and ref, so one taken out and curated again is the same object and is answered, with its provenance as it now reads. A selection is never a reach: what it names is judged as below.

**Which references.** Each is judged by the reach `artifacts.reachable` uses: `reach_of` gives work directly asked for its Conversation, and bounded (delegated) work only its own line.

| Reference | In reach when |
|---|---|
| `adm-`, or a citation of one | `artifacts.reachable` admits it, or it is acquired (`read_source` reads those for any grant) |
| `ent-`, `live:<post>:<key>`, `brain:<entry>` | The post stands, and is in the run's Conversation or is a Turn that asked for its line |
| `conversation`, `chat` | It is the run's Conversation |
| `participant` | It participates in the run's Conversation |
| `magnet` | Always: the id names no Conversation, and the Magnet's sources and Conversation are not read |
| `other` | Never: free text can't be judged |

A reference outside reach answers `{kind, curated, withheld: true, reason}`, and no ref, id (a hash of the ref), provenance or `observed`. `withheld` counts them. A reference in reach whose provenance names something outside reach keeps the object and loses that field (`provenance_withheld` counts them). The reason is fixed wording, because `reachable`'s own can name other work.

`state` is `held`, `deleted`, `missing` or `unreadable`. The last three have no objects, and `unreadable` says so in fixed wording, because a manifest's own refusal can quote a ref.
