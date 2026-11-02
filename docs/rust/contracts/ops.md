# Contract: the read signature R2 and R3 build on

Code: `crates/mentis-ops/src/lib.rs`, `crates/mentis-rules/src/lib.rs`. It only gains.

## The shape

```
door or route       parses the request; checks what is its to check (Host, grant, permitted)
  mentis_ops::run   a scope from the class's pool, then the op
    ReadOp::read    the read: statements through the scope, rules from mentis-rules
      returns       ReadAnswer { rows, as_of, more, not_searched }  or  OpError
  door or route     shapes the answer exactly as that route always has
```

```rust
pub trait ReadOp: Send + Sync {
    type Args: Send;
    type Row: Serialize + Send;
    const NAME: &'static str;
    const BUDGET: Budget;
    fn read(&self, scope: &mut dyn ReadScope, request: &ReadRequest<Self::Args>)
        -> Result<ReadAnswer<Self::Row>, OpError>;
}
```

**An adapter is thin.** Fluid routes, agent reads and Magnet sources all call `run`, with different classes. Same op, same answer. What differs per consumer is policy, like how a deleted entry shows (census, `op-now`), and that stays in the adapter.

## What an op may not do

- **Hold a lock across a statement or a JS call.** Consumers must not serialise on each other: that is what this migration is for.
- **Need a memo** for correctness or for its budget. An answer costs the same just after a commit as before it.
- **Write,** or call anything that does. A scope can't.
- **Read live state itself.** A live input arrives in `Args`, from the snapshot, already checked for age by the adapter (`contracts/live-snapshot.md`). It can't then read an older state by accident.
- **Know about a grant.** Authority is the door's, before `run`. Every agent read still goes through `/api/worker`, and R3's door checks `permitted` against the grant. An op has no route around that because it has no route at all.

## Budget

`BUDGET` is the most statements one call may run at any state of the record, counted from `ReadScope::statements`, position included. It is fixed per call, not per id. Walking a chain only for touched ids stays allowed, and its bound is what the budget states. A test states the budget for warm, just-after-a-commit and cold, and R3's `kinds` and `resolve` set theirs when built.

## What `OpError` becomes

| `OpError` | Fluid | Agent door |
|---|---|---|
| `NotOwned` | **Forward to Python unchanged.** 503 with the reason if Python can't answer | The same |
| `Busy` | 503 `{"error", "kind": "Busy"}` | The same, as `web/__init__.py:6935` |
| `BadRequest` | 400 `{"error", "kind": "BadRequest"}`, in the route's own words | The worker's own refusal shape |
| `NotFound` | 404, as `fluid/__init__.py:272` | As the operation answers today (`known: false` is an answer, not an error) |
| `Record` | 500, or 503 for an expired scope, with the words | The same |

The status codes are bound by the contract tests for each route. Where a route's Python answer differs from this table, the route wins, and the adapter says so in a comment.

## A request's deadline

`ReadRequest.deadline` is held by `run`, for every op, so no op has to remember it. Past it the answer is `Busy`, and nothing partial, because `rows` is whole:

| When the deadline has passed | What happens |
|---|---|
| On arrival | `Busy`. No scope is taken, so nothing holds a place in the class's cap |
| Once the scope is open | `Busy`, for the wait a scope can take |
| Before a statement | `Busy`. It doesn't start |
| At a row of a running statement | `Busy`. The statement stops there |
| Between two rows, or in a statement with no rows yet | It can't be stopped from here. It goes on until its next row, or to the scope's limit of 2 s, which ends it as an expired scope |
| After the last statement | The op answers. All that's left is work in memory, and stopping saves nobody anything |

The scope's limit is unchanged and separate: it protects the record, and the deadline is the caller's.

## Rules (`mentis-rules`)

| Function | Python it replaces | Built by | Notes |
|---|---|---|---|
| `now_reads(scope, ids)` | `presented` `conversation/versions.py:266`, `lineage` `:171`, and the four batched copies (census, `op-now`) | P1.3 | Facts, no policy. Blanks a deleted body by `_blank`'s rule, a body false to Python included. Where `presented` raises, on a deleted body or a deletion's body that is true to Python and not an object, or holds a reason that isn't text, `Reading.python_says` is set and the route forwards, so the answer, its 500 included, is Python's own |
| `names(scope, ids)` | `_names` `fluid/read.py:194`, `_conversation_name` `worker.py:747`, `alias`, `_name` `operational/work_overview.py:142` | P1.3 | A held id with no name is `None`; an id not held is absent. The route shows each as it does today |
| `standing_many(scope, ids, as_at)` | `Corpus.stands` `spine/seam.py:877` and its copies (census, `op-standing`) | R3 | The top-ranked shared operation. `as_at` kept. A check before a write still reads through the writer, in Python |
| `lines_of(scope, ids)` | `objects._lines`, `versions.lineage` | R2 | With the first of `Corpus.history`, which a later version needs to name its post |
| `ended(scope, links)` | `read._in_force`'s `stands` for each | R2 | Two statements for the set |
| `alias_reads(scope, ids)` | `Conversations.alias` | R2 | A body it can't read is `None`, and the route forwards |

Tested against Python on a dump, including `as_at`, at each release that reads them. **Where Python and Rust disagree it is a defect,** not a difference to list: see the owner's rule in `AGENTS.md`.

## For R2 and R3, specifically

- **R2 adds** `extract(bundle, input)` and its pool in its own package, `mentis-extract`, as its own interface: one engine to each of the pool's threads, whose bundle is compiled when it first reaches that thread. No lock is held over a call. The window's routes run its ops as `Foreground`; no op or pool assumes it.
- **A window read has two steps, so JavaScript never holds a read scope.** `ReadOp::read` does every statement and answers a `Prepared` plan. `run` then lets the scope go, and the adapter calls the plan's `finish`, which hashes held files and runs what isn't cached, with no statement and no scope. A cold page is many times `READ_SCOPE_LIMIT`, and a scope kept over it would hold one of the class's connections from every other reader. `finish` can't read the record: what a plan will need is read ahead of it, and what wasn't is forwarded.
- **What an engine can't do is Python's to say.** A time limit, a memory limit, an exception or a bundle that won't compile is `NotOwned`, and the request goes on to Python, whose answer holds its own exception's words. Only the text limit (`MAX_CHARS`) has Rust's own answer, in Python's words.
- **A reading, then a route's shape.** `run(Objects)` and `ObjectsPlan::read` answer an `ObjectsReading` with no HTTP, route or Fluid state in it. `ObjectsPlan::finish` is that reading and the route's body, and it's the only part that knows the route's keys and words. A consumer names what it wants without walking a conversation: `ObjectsAsk::Posts`, or `Versions`, which no route sends. A `PostReading` holds what names each object (`ObjectSource`: root, version, part, key, both addresses), its scope (`Whereabouts`), its provenance (`Wanted`: the version's author and time, what its run returned, the bundle digest in `Key`) and its freshness (`Key.version`, `as_of`). A collection's `shape`, `topic`, `from`, `before` and `limit` stay its own arguments: only a page's ids and counts reach the reading. What a consumer inherits unchanged: `NotOwned` has only Python to go to, and one post's ends the whole read; the engines are one queue, first come first served, with one cache and no notion of class, and `read` and `finish` have no deadline, so a large read holds up a route's turn on them.
- **R3 adds** the door and the grant mirror. Its ops use `Agent`. Quick Ask grants always forward, so an agent op never sees one, and `note_deleted_reads` stays in Python (`worker.py:4377`).
- **Neither needs the other.** They share only `ReadOp`, `run`, `ReadScope` and `Rules`, and they add new ops, not new signatures. If either needs a change to what's here, that is a change to this contract: bring it back rather than diverge.
