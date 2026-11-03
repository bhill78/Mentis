# R3: the seams between the door and the reads

Owner's amendment, Turn #1294. **The property:** R3's reads can later be called by a consumer that isn't an agent, without a second retrieval implementation. Grants, `/api/worker` framing, the mirror and `permitted` stay at the door. Each consumer's authorization stays at its own boundary.

The ops in section 2 are built (section 8). The door, the mirror and the wire are not. Citations are at `e05c74b`. No signature in `contracts/ops.md` changes. Python's answer stays the first rule: equal bytes or forward.

## 1. Conclusions

- **No moved read's answer depends on who is asking.** Section 3 has the check. No op needs an argument filled in from a grant.
- **What couples these reads to agents is wording, not data.** Several answers tell the reader which tool to call next. Those sentences belong to the door (section 5).
- **Three inputs aren't the caller and aren't statements either:** the clock, held files and the render engine (section 4).

## 2. The ops

One new module per op in `mentis_ops`. The door calls `run(&op, record, ReadClass::Agent, &request)`. The class is the caller's, and no op names it. Where an answer has totals beside its rows, `Row` is one page and `rows` holds that one row, as `TopicsPage` does (`topics.rs:40`).

| Read | Op, `NAME` | `Args` | `Row` |
|---|---|---|---|
| `kinds` | `Kinds`, `"kinds"` | `at`: the time to report | `KindsPage`: Kinds with counts and split, `definitions`, `links`, `as_read_at` |
| `capabilities` | `Capabilities`, `"capabilities"` | none | `CapabilityNames`: `capabilities`, `count` |
| `history` | `History`, `"history"` | `conversation`, `turn`, `participant`: filters, all optional | `HistoryPage`: `acts`, `matched`, `not_returned` |
| `history set=` | `SetChanges`, `"set_changes"` | `set`. `since` is `ReadRequest.cursor` | `ChangesPage`: `changes`, `cursor`, `not_returned`, and for a decision form `open`, `closed` |
| `owner_decisions` | `OwnerDecisions`, `"owner_decisions"` | `conversation`. `most` is `ReadRequest.limit` | `DecisionsPage`: `open`, `answered`, both counts |
| `governed` | `Governed`, `"governed"` | `kind`, `q`, `state`. `limit` and `cursor` are `ReadRequest`'s | `GovernedPage`: `query`, `groups`, `totals`, `omitted`, `matched`, `walked`, `kinds`, `why_not`, and `next_cursor` only when a cursor was given |
| `resolve` | `Resolve`, `"resolve"` | `reference` | `Resolved`: the common fields, plus one variant per kind (section 6) |

`history`'s `participant` is the actor a caller asks about. It is a filter and has nothing to do with who is calling.

`Governed` takes `cursor` though the agent door never sends it, because `register.governed` is one read with two callers (`fluid/__init__.py:168`). R6's `/api/governed` and `/fluid/api/governed` then need no second op. With no cursor each group is cut separately, and with one a single page is cut (`register.py:512-519`). The op keeps both.

`standing_many(scope, ids, as_at)` keeps `as_at`, and `Resolve` and `Governed` call it with `None`, as Python does. No op's `Args` exposes it, because no moved read has a Python answer to compare with.

## 3. Does the answer depend on who is asking?

**No, for all six.** This confirms the claim in section 2 of `R3-mirror.md`, checked here separately:

| Way a caller could get in | What the code does |
|---|---|
| `_result`'s arguments | `participant`, `grant` and `scope` reach only `orient`, `brief`, `recall` and `work_overview`. The moved reads' branches pass only `args` (`worker.py:4115-4142`) |
| `Surface.permits`, set by the door (`web/__init__.py:3079`) | Read only by `orient` (`worker.py:839`, `:844`) |
| `Surface.read_scope` | Read only by three other methods (`worker.py:787`, `:915`, `:2181`), none of them moved |
| Helpers below the reads | `presented`, `stands`, `anchors`, `responses`, `register`, `reading.provenance` and `artifacts.describe`, `sniffed`, `deleted_from` take a corpus or `cv` and a reference, with no caller argument |
| Restricted or lineage visibility | Enforced only for bytes: `artifacts.reachable` takes the grant (`artifacts.py:986`) and serves `read_artifact`, which isn't moved. No moved read calls it |
| Thread-local state | `Conversations._scope` is a memo for one read and `store._beside` chooses how a read runs. `service._thread` and `dispatch._here` aren't read by these reads |
| `note_deleted_reads` (`worker.py:4377`) | Runs after the answer and doesn't change it. Acts only on `TRANSIENT_SCOPE`, which forwards |

**One fact for a future consumer, with no change now.** Because restriction covers only bytes, `resolve` gives a restricted artifact's name, size and digest to every grant, and `history` gives every grant its acts. That is today's behaviour, and the ops keep it. A consumer needing per-viewer filtering of those would add an explicit argument then. The Magnet research lists this as undesigned (`adm-4045a2e0cc9a`, section 7, "Restricted content").

## 4. Inputs that aren't the caller

None of these touches a signature.

| Input | Where | Seam |
|---|---|---|
| **Clock** | `kinds` reads `time.time()` for `as_read_at` (`worker.py:1035`) | `KindsArgs.at`, filled by the door, so the op reads no clock and a test can fix it |
| **Held files** | `resolve` of an artifact asks whether its file exists and reads its first bytes (`held.state`, `artifacts.sniffed`). These aren't statements, and `as_of` doesn't cover them | A field on the op's own struct, `Resolve { held }`, given by whoever constructs it. It holds a store root and nothing about a consumer. Until that is built, these kinds answer `NotOwned` |
| **Render engine** | `resolve` of a Turn with a fillable block or a response set, and of a response set (`_fill_blocks`, `render_check.answers`) | **`NotOwned` until R2's `extract` is merged, then call that.** No second extraction. R3 doesn't wait for R2: those cases forward |

## 5. What stays in the door

**Agent policy, never in an op:** token and grant lookup; the mirror, its lease and its forwarding rules; the corpus check; `permitted`; refusal wording; Quick Ask forwarding; `note_deleted_reads`, which stays in Python; `/api/worker` framing and the worker's answer shape, key order included.

**Parsing and defaults, per door:**

| Case | Door's rule |
|---|---|
| A value Python would coerce or trip on (`ref` absent or not a string, `limit` not a plain positive integer, a negative `limit`, which Python slices with) | Forward. `Args` are typed, so nothing odd reaches an op |
| A `limit` over the op's maximum (`history`'s has no cap in Python, and a budget needs one) | Forward |
| Default `limit` | **The door's, sent explicitly.** The agent door sends `PAGE` (40) for `governed` where Fluid's route takes the register's default of 50 (`worker.py:2093`, `register.py:80`). `owner_decisions` defaults to 5 and caps at `PAGE`. The agent door's `history` defaults to `PAGE` |
| `since` with no `set` | The door's refusal (`worker.py:4122`) |
| An `owner_decisions` read that fails | Forward. Python answers empty lists here (`conversation/__init__.py:6337`), so the route wins over `contracts/ops.md`'s `Record` row, and the adapter says so in a comment |

**Answers that only the door says.** The op returns the fact and the door adds the words:

| Words | Fact the op returns |
|---|---|
| `kinds`: `as_read`, `groups_mean`, `split_none_means` | The counts, and each `unknown_because` |
| `capabilities`: `note`, naming `delegate` | The names |
| `history`/`SetChanges`: `note`, and `refused` with its `why_not` | `cursor`, `ReadAnswer.more`, `BadRequest` for a bad `since` |
| `owner_decisions`: `refused`, whose words name `orient` | `NotFound` for a non-Conversation. An absent `conversation` never reaches the op |
| `governed`: `listed_because`, `governs_is_per_row`, `not_an_ask`, `{"error": …}` | The rows, `BadRequest` |
| `resolve`: every `note` (the response set's, the decision form's, the fillable block's, the reaction's), the `standing` sentence, and `{"known": false, "why_not"}` | `stands`, `established_by`, `superseded_by`, `knowing`, `NotFound` |
| `resolve`/`history`: the deleted marking's `note`, "Mark any passage…" | `deleted: {what, ref, when, by}` and `deleted_material` |

The wire's boolean `more` is `ReadAnswer.more.is_some()`. An artifact's `url` isn't in the row, because the worker has always removed it (`worker.py:1245`, `:1261`). `as_of` isn't on the agent wire, because Python doesn't send it.

## 6. What each row or answer carries

Only what already applies. `—` means the concept doesn't apply, and nothing is invented for it. On the agent door `as_of` exists only inside `ReadAnswer`, for every op, so it isn't repeated below.

| Read | Source identity | Scope | Provenance | Freshness |
|---|---|---|---|---|
| `kinds` | Kind name, definition `version` | The Brain | — (counts) | `as_read_at`; `entries_unknown_because`, `unknown_because` |
| `capabilities` | Names | — (code, not the record) | — | — |
| `history` | Act `id`. Acts have no versions | `conversation` or `turn`, else the Brain | `actor`, `actor_alias`, `execution`, `runtime`, `caused_by`, `about`, `because` | `matched`, `not_returned`. Python has no continuation here, so `more` is `None` |
| `SetChanges` | `entry` | The set or form | `by`, `by_alias`, `at` | `cursor`, `more`, `not_returned` |
| `owner_decisions` | `expectation`, `post` | `conversation` | — on the row. Python carries no asker here; resolve the post | Both counts beside the cut lists |
| `governed` | `entry`, `kind` | `placed_at`, `whole_brain` per row | `attributed_to`, `author_alias`, `at`, `proposed_by`, `established_by` | `totals`, `omitted`, `matched`, `walked`, `next_cursor`; `standing_apt_unknown` and `why_not` for what wasn't walked |

`not_searched` stays empty for all of these: each one already says in its own fields what it left out, and those fields are what Python sends.

**`resolve`, kind by kind.** Every answer has `ref`, `recorded_at`, `attributed_to`, `written_by` and the standing facts, plus `revision` and `deleted` where they apply.

| Kind | Moved | Source identity | Scope | Provenance beyond the common fields |
|---|---|---|---|---|
| Turn, no fillable block and no response set | Yes | `ref`, `revision`, `number` | `conversation` | `author`, `author_alias`, `addressed_to`, `references`, `decision_forms` |
| Turn with a block or set; response set | `NotOwned` (section 4) | As above; `set`, `version` | `conversation` | `by` on each answer |
| Conversation | Yes | `ref`, `revision` | Itself | `origin`, `participants` |
| Participant | Yes | `ref`, `alias` | `conversations` | — |
| Topic | Yes | `ref` | `conversation` | — |
| Anchor, reaction | Yes | `ref`, the anchor's version selector | Its Turn | `interactions`, `about` |
| Held artifact | `NotOwned` until `held` is built | `ref`, `digest`, `size`, `name` | — (Brain-wide reach is `read_artifact`'s) | `door`, `source`, `deleted` |
| Acquired observation | `NotOwned` until `held` is built | `ref`, `collection`, object key, which version of how many | `collection` | Sweep act, `connector`, whether a newer one exists |
| Link | Yes | `ref` | — | `relation`, `links_from`, `links_to`, and their kinds, names and alias |
| Any other kind | Yes | `ref` | — | `body` as recorded |

The build may keep any further kind `NotOwned`. A kind that forwards is always correct, and only slower.

## 7. Would this get in the way of `find`, `recall` or a Magnet?

No. Neither is pulled in here, and nothing Magnet is built. Against `adm-4045a2e0cc9a`, sections 7 and 9:

- **`find`, R5:** its identity branch calls `resolve`, and its Turn hits use `_turn_line` and `stands` (`worker.py:1838`, `:1921`, `:1892`). So `Resolve` is callable as it stands, and the Turn line must be a public function rather than private to `Resolve`, or R5 would copy it.
- **`orient`, R6:** `_kinds_in_brief` cuts `kinds` down, so it can run the `Kinds` op.
- **`seq` on each hit, and the acts stream:** no moved answer carries `seq`, because Python doesn't. A `Row` can gain the field later without changing the wire, since the door shapes the answer. `History` reads acts and is not a tail, and doesn't try to be one.
- **`History`'s `more` stays `None`,** so no cursor meaning is promised that a later `tail` would have to honour.

## 8. As built

One module per op in `crates/mentis-ops/src`, beside what they share: `stored` (JSON handed on as stored), `vocabulary` (the definitions, and `ground_of`, `group_of`), `acts`, `forms` (a decision form), and `turn_line`, public as section 7 asks. `standing_many` is in `mentis-rules`. Tested against Python by `tests/agent_reads.rs`, **as facts, not bytes:** the door's words are taken off Python's answer first. Byte equality with what the door sends is `crates/mentis-server/tests/worker_reads.rs`, on the changed BRAIN-SEED, with the door's words in `crates/mentis-server/src/worker_reads.rs`; a Brain copy hasn't been run against it.

**What answers `NotOwned`, so Python answers:**

| Op | Case | Why |
|---|---|---|
| `Resolve` | Held artifact, acquired observation | Held files. The `held` field isn't built |
| `Resolve` | Response set; Turn with a fillable block or a response set | The render engine, until R2's `extract` |
| `Resolve` | Anchor; Turn holding an anchor part; Conversation opened from an Anchor | Further than section 6's table: section 6 lets a build keep any kind. Reading one takes selectors, graphemes and each reactor's own line. Reactions moved |
| `SetChanges` | A page holding an interpretation | It reads the words it quotes |
| `History` | `limit` over `History::MOST`, 1000 | Section 5 |
| Any | A value Python raises on or can't be read here: a body true to Python and not an object, a lone surrogate in a field that is read, a repr that isn't plain ASCII | Python's answer, its 500 included, is Python's own |
| `Resolve`, `SetChanges` | A decision form with no request, or a question that is a reconsideration or an input | They take reads this doesn't make. A form with no request has Python read every act |
| `Kinds`, `OwnerDecisions` | A failed read | Python answers these in-band |

`Kinds` never has `entries_unknown_because` or `split_walked`. Each says the record moved between two of Python's reads, and a scope is one snapshot.
