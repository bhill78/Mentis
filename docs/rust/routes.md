# Every route, classified (P1.0)

Read from the dispatch code at `b8e324c`: `do_GET` and `do_POST` (`web/__init__.py:6440`, `:6491`), `_routes` (`:2015`), `fluid/__init__.py`, `fluid/commands.py`, `web/sources.py`, `web/ladder.py`, `web/exchange_import.py`.

**Until its release, every route is forwarded,** so a late or wrong row here costs nothing but time.

## How to read it

**Class,** from census section 5, with the census's words:

| Class | Means |
|---|---|
| `durable` | Reads the record only |
| `derived` | Also needs a `derived/` file or the JS engine |
| `live` | Needs run state only Python holds |
| `composition` | Composed per Persona, scope and grant |
| `write` | Appends, or changes a durable file |
| `GET-write` | A GET that writes. See the inventory, section D |
| `bytes` | Serves or takes bytes, with its own protections |
| `machine` | Asks this machine: git, processes, runtimes, pickers |
| `static` | Fluid's build |

**Census:** `yes` the census classified it (section 5). `I` the census classified it from the handler without tracing. `no` the census didn't check it, or never mentions it: **classified here from the branch's head, not traced,** so its package reads the handler before relying on the class.

**Release:** `r3` the plan names this route at this release. `P1.0` the plan doesn't name it, and I placed it by what it reads. Those are proposals, and the owner can reorder.

**Every route has a release.** Writes are all R7. Their family is named, and the order is W0's.

**A route's release isn't when its Python goes.** A release moves serving, and Python's code stays while it has a caller: `P1.0-inventory.md`, section I. In particular `fluid/objects.py`, its lock and cache, `quickjs-ng` and `render_check` stay to R7, all of `_UNGATED_READS` and `_WORKER_READ_GATE` stay to R7, and `work_overview` stays on Python to R6.

## R1: owned by the front

| Method | Path | Class | Census | Release | Notes |
|---|---|---|---|---|---|
| GET | `/api/pulse` | live | yes | r3 R1 | Durable half in Rust, live half from `/private/live` |
| GET | `/fluid/api/topics` | durable | yes | r3 R1 | One consumer, the `#` palette |
| GET | `/fluid/api/names` | durable | yes | r3 R1 | |
| GET | any other path not under `/api/` or `/fluid/api/` | static | no | r3 R1 | `_static`: a missing file, `..`, or `render-check.js` all get `index.html` at 200. No build gets a JSON 404. Content types come from Python's `mimetypes`, which on Windows reads the registry, so compare headers in the contract test rather than assuming a table |
| * | `/private/*` | new | n/a | R1 | The front's own, never forwarded. `contracts/launcher.md` |

## R1: forwarded, and only these change on Python's side

| Method | Path | Class | Notes |
|---|---|---|---|
| GET | `/private/live` | live | New. P1.5. Private port only, with the secret |
| GET | `/private/grants` | live | New. R3. Private port only, with the secret. The whole mirrored table: `R3-mirror.md`, section 3 |
| GET | `/private/grants/position` | live | New. R3. Private port only, with the secret. Who Python is and how far its table has got |

## R2: the post window

The first five rows are what R2 owns (`route-table.default.json`, `handlers/window.rs`, `mentis_ops::window`, `mentis-extract`). A case the route can't be sure of Python's answer to is forwarded, so Python still answers: an engine failure, a lone surrogate in a body, a later version of a Conversation. The `P1.0` rows are proposals, not in R2's scope, and stay forwarded until they are planned.

| Method | Path | Class | Census | Release |
|---|---|---|---|---|
| GET | `/fluid/api/collections/conversation` | durable | yes | r3 R2 |
| GET | `/fluid/api/posts?ids=`, with `&thread=1` | derived (`thread=1`) | yes | r3 R2 |
| GET | `/fluid/api/collections/thread` | durable | yes | r3 R2 |
| GET | `/fluid/api/objects`: `post=`, `posts=`, `thread=`, `conversation=` | derived | yes | r3 R2 |
| GET | `/fluid/api/objects/<address>` | derived | yes | r3 R2 |
| GET | `/fluid/api/collections/stream` | durable | yes | P1.0 R2 |
| GET | `/fluid/api/collections/selection` | durable | yes | P1.0 R2 |
| GET | `/fluid/api/latest` | durable | yes | P1.0 R2 |
| GET | `/fluid/api/changes` | durable | yes | P1.0 R2 |
| GET | `/fluid/api/anchors`, `/fluid/api/posts/<id>/anchors` | durable | yes | P1.0 R2 |
| GET | `/fluid/api/response-sets`, `/<id>`, `/<id>/history`, `/<id>/accounting` | durable | yes | P1.0 R2 |

## R3: agent reads, through the door

`POST /api/worker` with `op`, id `worker` in the route table: `R3-mirror.md`, section 5. R3's door takes these and forwards every other operation, and `POST /private/grants`, a push from Python, is the front's own under `/private/*`.

| Op | Class | Census | Release |
|---|---|---|---|
| `kinds`, `capabilities`, `history`, `owner_decisions`, `governed`, `resolve` (kind by kind) | durable | yes | r3 R3 |

**R3 retires nothing here.** The whole of `_UNGATED_READS` and `_WORKER_READ_GATE` stay until the last write family in R7, because these reads still reach Python through Quick Ask grants, unknown tokens, `resolve` kinds not yet moved, and mirror fallback.

**Stays on the door's list, later:** `find`, `check_rendering`, `sources`, `source_history`, `source_links`, `read_source`, `search_sources` are R5. `orient`, `recall`, `brief`, `work_overview` are R6. `workspace_objects` is a read with no release yet, and forwards. Every other operation is a write, R7. Quick Ask grants always forward.

## R4: lists and needs-you

| Method | Path | Class | Census | Release |
|---|---|---|---|---|
| GET | `/fluid/api/conversations?activity=1`, `?ids=` | live | yes | r3 R4 |
| GET | `/fluid/api/home/needs-you` | durable | yes | r3 R4 |
| GET | `/fluid/api/needs-you/items`, `/fluid/api/needs-you` | durable | yes | r3 R4 |
| GET | `/fluid/api/decisions`, and `/api/turns?ids=` | durable | yes | r3 R4 |
| GET | `/api/turns/<id>` | durable | yes | P1.0 R4 |
| GET | `/fluid/api/participants` | durable | yes | P1.0 R4 |
| GET | `/api/participants` | durable | I | P1.0 R4 |
| GET | `/api/conversations` | live | yes | P1.0 R4 |
| GET | `/api/conversations/<id>/thread/<root>` | durable | no | P1.0 R4 |
| GET | `/api/personas` | durable | no | P1.0 R4.2 |
| GET | `/api/intake` | live | no | P1.0 R4.2 |

## R5: search, Magnets, sources reads

| Method | Path | Class | Census | Release |
|---|---|---|---|---|
| GET | `/fluid/api/magnets/<id>/read` | derived, `presentation/` | n/a | Magnet M1, new and Rust's from the start: Python has no such route, and a Magnet with no definition is forwarded to its 404. `docs/magnets/M1-contract.md` |
| GET | `/api/references` | derived | yes | r3 R5 |
| GET | `/fluid/api/search` | durable | no | P1.0 R5.1; literal post search within one Conversation, with cost growing with that Conversation |
| GET | `/fluid/api/object-refs` | derived | no | r3 R5, for serving. **Its Python path stays to R7:** it is one of `fluid/objects.py`'s callers |
| GET | `/fluid/api/home/for-you` | derived | yes | P1.0 R5.3 deferred. Can start a rebuild: section D |
| GET | `/fluid/api/document` | bytes, derived | no | P1.0 R5 |
| GET | `/api/sources/search`, `/provenance`, `/page`, `/cite`, `/rendered`, `/record`, `/<c>/objects`, `/<c>/history`, `/<c>/links`, `/<c>/page` | derived, `/search` triggers extraction | no | r3 R5.2 |

## R6: work and composition

| Method | Path | Class | Census | Release |
|---|---|---|---|---|
| GET | `/api/work`, `/api/owed` | live | yes | r3 R6.2 |
| GET | `/fluid/api/home/work`, `/fluid/api/home/activity`, `/fluid/api/home/briefing`, `/fluid/api/work`, `/fluid/api/runs` | live | yes | r3 R6 |
| GET | `/api/context` | composition | yes | r3 R6 |
| GET | `/api/working` | live | yes | r3 R6 |
| GET | `/api/activity` | live | yes | P1.0 R6 |
| GET | `/api/conversations/<id>?fields=` | durable selected fields | I | P1.0 R4.2; full Conversation remains behind `CurrentWork` |
| GET | `/api/conversations/<id>` full form; `?batch=0` unchecked | composition, live | I; `batch=0` no | P1.0 R7 unless defect 1 moves `CurrentWork` earlier |
| GET | `/api/conversations/<id>/work` | live | yes | P1.0 **delete, not move**: 6,102 statements and no consumer found in `apps/fluid-web` (census). Confirm no external consumer first |
| GET | `/api/conversations/<id>/governs`, `/origin`, `/orientation`, `/media` | composition | no | P1.0 R6 |
| GET | `/fluid/api/settings` | durable file (`presentation/`) | no | P1.0 R6.3; stays while its Fluid-command writer remains |
| GET | `/api/brain`, `?identity=1` | composition; `identity=1` durable | no | P1.0 R6 |
| GET | `/api/kinds`, `/api/governance/authoring`, `/api/governance/subjects`, `/api/governed`, `/fluid/api/governed`, `/fluid/api/governance/authoring` | durable | yes (`kinds`, `governed`); no | P1.0 R6, beside the standing library's second consumer |
| GET | `/api/governance/history`, `/standing`, `/execution`, `/applies`, `/conditions`, `/deliveries`, `/questions`, `/since`, `/disputes` | durable | no | P1.0 R6 |
| GET | `/api/operational`, `/api/entries/<id>`, `/api/history`, `/api/provenance`, `/api/gravity`, `/api/resurrect`, `/api/integrity`, `/api/space`, `/api/space/said`, `/api/neighborhood` | durable | `operational`, `entry`, `space` yes; rest no | P1.0 R6 |
| GET | `/api/ladder/items`, `/items/<id>`, `/adoption`, `/adopted` | durable | no | P1.0 R6 |
| GET | `/api/anchors/<id>`, `/api/anchors/from/<x>`, `/api/anchors/<id>/interactions` | durable | no | P1.0 R6 |
| GET | `/api/timers/<post>/<name>`, `/api/timers/about/<ref>` | durable | no | P1.0 R6 |
| GET | `/fluid/api/layouts`, `/fluid/api/arrangements/<key>` | durable file (`presentation/`) | no | P1.0 R6 |
| GET | `/api/presentation`, `/api/presentation/scenes` | durable file (`presentation/`) | no | P1.0 R6 |
| GET | `/api/context-cache` | process-local stats | no | P1.0 **delete with `ContextCache`,** R6 |

## R7: machine-bound reads, which stay with what they ask

| Method | Path | Class | Census | Release |
|---|---|---|---|---|
| GET | `/api/execution` | machine: discovers runtimes, asks MARS | no | P1.0 R7, dispatch and runs |
| GET | `/api/capacity` | **GET-write** | no (census section 5 notes the write) | P1.0 R7, dispatch and runs |
| GET | `/api/runs/<run>/feed`, `/api/runs/<run>/consent` | live | yes | r3 R7, dispatch and runs |
| GET | `/api/who/<id>` | machine, live | no | P1.0 R7, dispatch and runs |
| GET | `/api/work/<id>` | machine, live | yes | r3 R7, waits on stage/git/`_FAILED` |
| GET | `/api/sources`, `/api/sources/<c>`, `/api/sources/<c>/run`, `/api/sources/folders`, `/api/sources/compare` | machine, live, derived | no | r3 R7, Sources jobs and acquisition |
| GET | `/api/server` | machine: this process's identity. **Exempt from the client header** | no | P1.0 R8: forwarded until Python is gone, then the Rust binary's own identity |
| GET | `/api/exchange/import/stage` | machine: a stage on disk | no | P1.0 R7, artifacts and exchange |

## R7: writes, by family

Order and whether families can move apart are W0's. Every row is `write`. **The census checked only `POST /api/worker/session` and `fluid/commands` by name, as writes.**

| Family | Routes |
|---|---|
| **Posts and responses** | `POST /fluid/api/posts`, `/fluid/api/requests`, `/fluid/api/posts/<id>/{address,reactions,comments,deep-dives,edit,delete,topics,unfile,move}`, `/fluid/api/reactions/<id>/withdraw`, `/fluid/api/response-sets`, `/fluid/api/response-sets/<id>/{ready,send-back,answers,own-words,show,start-new,move}`, `/fluid/api/interpretations/<id>/{confirm,change,decline}`, `/api/conversations/<id>/turns`, `/api/turns/<id>/{address,expect,topics,unfile,move,link,unlink}`, `/api/anchors`, `/api/anchors/<id>/{reactions,deep-dives}`, `/api/timers/<post>/<name>/marks` |
| **Fluid commands** | `POST /fluid/api/conversations`, `/fluid/api/conversations/group`, `/fluid/api/conversations/<id>/{name,members}`, `/fluid/api/arrangements/<key>`, `/fluid/api/arrangements/<key>/magnets`, `/fluid/api/arrangements/<key>/magnets/<id>/{reconfigure,remove}`, `/fluid/api/magnets/lift`, `/fluid/api/magnets/<id>/{delete,conversation}`, `/fluid/api/settings`, `/fluid/api/layouts`, `/fluid/api/layouts/defaults`, `/fluid/api/layouts/<id>/delete`, `/api/conversations`, `/api/conversations/<id>/{instructions,participants,topics}`, `/api/presentation/looks`, `/looks/<id>`, `/choice`, `/scenes`, `/scenes/<id>`. Needs `X-Mentis-Presentation` on the last five |
| **Ladder and governance** | `POST /api/entries`, `/api/entries/<id>/{edit,delete,revise,establish,establish-replacement,supersede,propose-supersession,request-adoption,adopt,decline,withdraw-challenge,dispute,support,derive-from,draw-on,place,unplace,set-aside,activities}`, `/api/governance/arrive`, `/api/ladder/vocabulary`, `/api/personas`, `/api/participants`, `/api/participants/<id>/{rename,runtime-default,designated-persona,avatar}`. `/api/ladder/vocabulary` imports from `tools/`, so `tools/ladder_vocabulary.py` is a runtime dependency |
| **Sources** | `POST /api/sources/{bind,unbind,plan,declare,revise-scope,sweep,pick,sqlite/inspect,sqlite/find,sqlite/sample}`, `/api/sources/<c>/reveal`, `/api/sources/<c>/run/cancel`. `pick` opens a Windows dialog and `reveal` runs `explorer.exe`, each needing the true peer |
| **Artifacts and exchange** | `POST /api/artifacts` (needs `X-Mentis-Upload`), `GET /api/artifacts/<ref>`, `?describe=1`, `POST /api/presentation/pictures`, `GET /api/presentation/pictures/<sha>`, `GET /api/conversations/<id>/export`, `GET /api/turns/<id>/export` (streaming ZIP, own checks), `POST /api/exchange/import/{preview,stage}` |
| **Dispatch and runs, last and together** | `POST /api/worker` (every operation not in `READ_ONLY`), `/api/worker/session`, `/api/worker/session/end`, `/api/intake/resume`, `/api/runs/<run>/{stop,consent}`, `/api/entries/<id>/...` where dispatch is requested, `/fluid/api/work/<id>/workflow` |

## Not routes, though they look like it

| Path | What it is |
|---|---|
| `DELETE /api/exchange/import/stage` | **Unreachable.** `exchange_import.py:289` answers it, and `_Handler` has no `do_DELETE`, so HTTP gets 501 from `http.server` (`web/__init__.py:6432-6491`). I found no caller in `apps/fluid-web/src/api.ts`. Discovered work; do not port it as a route without checking |
| OPTIONS, any path | Answered by `do_OPTIONS`, 204, granting nothing, and with the artifact protections on artifact and picture paths. Forwarded in R1 |
| HEAD, PUT, DELETE, PATCH | 501, from `http.server`. Forwarded in R1, so Python's answer stands |
| `mentis/fluid/workspace_manifest.py` | Helper module only; it registers no HTTP route |
