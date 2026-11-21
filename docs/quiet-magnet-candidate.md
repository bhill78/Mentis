# Limited Quiet Magnet candidate — implementation and fixture trial

Status: implemented and committed; a detached, write-refusing fixture preview is
running and has been checked in headless Edge. The initial Part C independent
review passed; bounded final-snapshot review remains outstanding. This is not
overall Work completion, an accepted design, a deployment or a merge to main.

Work: `opr-49af16960257`, under `opr-9548d7a9c1f7`, Conversation
`ent-c0d3b497df7f`. Authority: owner `ent-0287d3c6ad8c`; revised plan
`adm-ac898dc06e43`, mapping `adm-654a86f51d6b`, yellow reference
`adm-c02af321cfbe`. Source base `71b064703ffe8094cc391555ac1695e0dca60996`.

Branch: `quiet-magnet-candidate` in
`C:/Work/Mentis-workspace/day-to-day/quiet-magnet-candidate`.
Tested source commit: `e655eeef7f1988f4ae4dad94097fc0c9cf3360e7`.
The client remains the tested e655eeef tree. Helper-only correction
`0a215f39d2e4f355a89b864e2b187fe9a653f4cf` supplies the required client header for
detached startup reporting and permits one reporting attempt; its three focused
pytest tests passed. Later report commits add documentation. No push, main integration, production/TEST replacement,
activation, synthesis, new Brain schema or deployment occurred.

## What the candidate contains

Explicit discovery reads only the current Conversation's saved arrangement. A
saved Magnet opens as a locally movable yellow puck with a joined quick card and
deliberate Overview, Posts, Files and unavailable Perspectives destinations.
Pointer, keyboard, touch, Escape, edge clamping and narrow layouts use the same
object. Numeric new/changed badges, changed totals, populated Perspectives and
Perspective counts are absent. The UI explains change tracking and Perspectives
are unavailable. Source tally and loaded-file counts have explicit scope labels.

The existing `quiet2/space/registry.ts` is the one lifetime owner, with distinct
graph/Magnet resource families and tombstoned ids. The graph provider is not used
to construct a Magnet. The viewer store has a typed `canvas` presentation, distinct
from parked and max; Magnet details use its stage selection. Graph-only full screen
placement remains graph-only. History carries ids, resolved Brain key and origin
references, not reads, credentials, resources or draft text.

Origin A is captured separately from source B and existing Magnet Conversation C.
Candidate source/item/own/return moves use shared history and reader paths, and
files use the existing media viewer and held-artifact description. The shared
leaving mechanism asks all places actually displaced before one commit, including
centre, duplicate destination columns and occupied max return reservations.
Covering still-mounted content does not count as displacement. In-memory fixtures
cover unfinished challenges, Stay at each guard, occupied s1/s2 and retained drafts;
the read-only browser trial exposes no composer or send authority.

Reads preserve source status, cursors, result versions and provenance. Partial
object extraction retries its input cursor explicitly before advancing; no retry
loop or broader legacy fallback exists. Identity loss/cross-Brain movement retires
resources, and late/cancelled completions cannot publish into another resource.

## Concrete API limit and unfinished work

Native `/fluid/api/magnets/<id>/read?mode=page` returns post identity/version metadata,
not per-post text. The fixture summary also omits `latest`, explaining that its last
16 links cannot establish the newest post under every accepted import order.
The card therefore shows post-number links and says text previews are unavailable;
it does not fabricate readable excerpts or fall back to legacy unfiltered reading.
This trial does **not** establish full preview-text fidelity to the accepted picture.
That contract/presentation limit is returned for the carrier's review.

Quill's initial independent Part C review `ent-ba5936b51e47` / verdict
`opr-1b58c31792bb` passed at `f5003f44`, with no blocker. It covered shared
lifecycle/unknown identity, canvas-stage placement, history and atomic guards;
it did not independently judge the final Part A, rendered or fixture evidence.
A bounded final-snapshot review is recorded with return/resume:
`opr-69400ceef7f6`, request `opr-01cf1ff299c9`, post `ent-47bab137b946`.
It covers only the previously uncovered Part A/evidence and final focus delta,
including whether the native text-preview limitation is material. No final
verdict is claimed yet. Final evidence note: `ent-9287d0be30aa`.

The old detached-arming refusal was resolved on resumption by using this
request's recorded result post `ent-88273687a475`. First resumed launch
`opr-26b614672234` failed: startup probes passed, but the helper omitted the
required `X-Mentis-Client` on its report, received 403 and stopped. That failure
was explicitly recorded in `ent-ef7eb2126305`; it was not presented as a live
preview. Helper correction `0a215f39` passed three focused tests, and a new
operation was armed explicitly rather than retried automatically.

New operation `opr-7abd450b837c` completed startup verification and its report
was accepted: `opr-5e6d40f33cc4`, Turn `ent-bd6daee935a8`. The preview remains
**running** at the address below. At **2026-11-21 22:25:17 UTC**, headless Edge
passed all 26 integrated checkpoints again, and the full runtime record/content
comparison remained unchanged. Live owned PIDs: helper 17440, launcher 60844,
proxy 37536, private Python 53492, Rust front 58172. No process from another
request was stopped. No detached report token or private launcher state is
included in returned artifacts.

Quill's three nonblocking findings are preserved as discovered work
`opr-56cd90a4e178` / `ent-bbb8ef3170bb`, unassigned and unfixed:

- N1: another max viewer parks an expanded Magnet instead of returning its puck
  to canvas; Back to Magnet recovers it.
- N2: browser Back can omit carries-on notices for non-interrupted work; guarded
  page controls still emit the notes.
- N3: the details stage advertises aria-modal while its container allows clicks
  through to outer page controls. The working row underneath remains mounted/inert.

The reviewer classified each nonblocking. They are recorded for later authorized
work, not pursued as an expansion of this candidate.

Known nonblocking observations: native metadata rows display participant ids where
aliases are not supplied; an unavailable read repeats its explanation in the empty
groups; the existing build reports circular/chunk-size warnings. No unrelated repair
was undertaken. Main/global Work and prior rounds remain with the carrier.

## Exact fixture and reproduction

The preserved root is `.preview/quiet-magnet` inside this checkout. Never reseed it;
`seed` refuses existing content. Setup used sanctioned corpus/Conversation/artifact/
arrangement operations and the existing own-Conversation operation to create C and
its `own-conversation-claimed` act. No raw record editing or forged C reference.

| Identity | Actual fixture reference |
|---|---|
| Primary corpus | `12e7fdb3-20eb-4735-8462-d88f5b7dc7cb` |
| A, origin and arrangement key | `ent-4e1472cecef5` |
| A post anchor | `ent-d8fb0ae14448`, post 1 |
| B, collection source | `ent-369c86abf3f4` |
| C, own Magnet Conversation | `ent-a272b0b8ee99` |
| Primary Magnet | `mag-c1e8af64f95056df` |
| Missing-own Magnet | `mag-7a1b461b71b4c60d` |
| Own claim | `opr-a1520c48bd65` |
| Held Markdown | `adm-a254aea0c429`, post `ent-b370a17e4832` |
| Submitted attachment | `adm-df3c61e256ec`, post `ent-679470ad99aa` |
| Image | `adm-9bba320fe3e0`, post `ent-601bd08b6672` |
| Secondary corpus | `f6e458f0-5f1d-4c71-83fc-96ba2cb8ec44` |

The manifest records both Brains' A/B/C, definition/arrangement digests and setup
completion. Source B holds 36 contributions: eight dated-out roots, 27 in-range
roots and a reply. The first post page has 20 roots; Load more yields 27 selected
roots, while the source-wide tally remains 36. Files include held Markdown, a
human-ingress text attachment and an image, attributed to their source posts.

The running preview holds Python 8931, Rust 8932 and read-only built preview
8933. Do not start a second helper on these ports. The checked address is:

`http://127.0.0.1:8933/quiet2?c=ent-4e1472cecef5&at=1`

Open this address, choose **Open existing Magnet**, select **Island observatory**,
then hover/click the yellow puck. Open details for Posts, Files and unavailable
Perspectives. Source conversation opens B; Magnet conversation opens pre-created C;
Back to origin returns A. The second saved Magnet demonstrates missing C.

For a later restart, after stopping only the PIDs above and claiming free ports,
use the preserved exact-source binaries in the foreground (or build them offline):

```powershell
C:/Work/Mentis-workspace/r1-fixtures/venv/Scripts/python.exe tools/quiet_magnet_preview.py --root .preview/quiet-magnet --front C:/Work/Mentis-workspace/day-to-day/quiet-magnet-fixture/target/release/mentis-server.exe --launcher C:/Work/Mentis-workspace/day-to-day/quiet-magnet-fixture/target/release/mentis-launch.exe --python-port 8931 --front-port 8932 --preview-port 8933
```

That command remains foreground until stopped. A carrier leaving it detached must
first satisfy `arm_detached` and supply its private one-time report configuration
through `--report-config`; the code never contains a report token. `--stop-file`
is an optional foreground evaluation stop mechanism. Do not supply the existing
`.preview/quiet-magnet/stop-preview` marker when reproducing: it would stop at once.
See `docs/quiet-magnet-fixture.md` for fresh-root setup, bounds and clean launch.

Rust sources are unchanged from `71b06470`. The sibling fixture branch built them
with `cargo build -p mentis-server --release --offline` in its isolated target.
Front SHA-256: `0406877248539ebbc09266e3271d57d07643301e49da4700b742582820840fb8`.
Launcher SHA-256: `48a1148afb338bc281b4cb0fe6b6b86a63a7208ed03401177a1b4a3afbb38cd1`.
The candidate UI was built from clean `e655eeef`; `dist/build-identity.json` records
that exact commit, dirty=false and untracked=0 at build time.

## Verification commands and counts

The following final runs completed on `e655eeef`. Each final run had zero failed,
skipped, cancelled and errors. Counts are tests/checkpoints where the runner uses
them, and assertions for the older unit scripts; they are not one homogeneous suite.

From `apps/fluid-web`:

| Command | Passed |
|---|---:|
| `npm.cmd run build` | build + TypeScript pass; 0 diagnostics |
| `node tests/quiet_magnet_read_unit.mjs` | 16 tests |
| `node tests/quiet_magnet_navigation_unit.mjs` | 11 tests |
| `node tests/quiet_magnet_puck_unit.mjs` | 52 checks |
| `node tests/quiet_space_nav_unit.mjs` | 226 checks |
| `node tests/quiet_address_unit.mjs` | 282 checks |
| `node tests/quiet_nav_unit.mjs` | 127 checks |
| `node tests/draft_keep_unit.mjs` | 84 checks |
| `python tests/quiet_magnet_puck_browser.py` | 30 headless Edge checks |

The renderer harness exclusively used claimed port 5439 and stopped its own process.
From the repository root (the integrated browser check requires the running preview):

```powershell
New-Item -ItemType Directory -Force .pytest_tmp | Out-Null
C:/Work/Mentis-workspace/r1-fixtures/venv/Scripts/python.exe -m pytest -q tests/test_quiet_magnet_fixture.py --basetemp .pytest_tmp/quiet-magnet-final
node tools/test_quiet_magnet_preview.mjs
python tools/quiet_magnet_browser.py
C:/Work/Mentis-workspace/r1-fixtures/venv/Scripts/python.exe tools/quiet_magnet_fixture.py compare --root .preview/quiet-magnet --baseline .preview/quiet-magnet/runtime-baseline.json --out .preview/quiet-magnet/runtime-compare.json
```

Results: fixture pytest 3 passed; proxy 13 checks passed; integrated Edge 26 named
checkpoints passed, including rendered yellow, A/B/C navigation, browser Back,
source post anchor, held-file viewer, two local Magnets, narrow card/Escape,
missing C, reload expiry, 404 no fallback and unknown identity. API interception
was used only for 404 and unknown-identity browser cases; normal navigation/read
cases used the real Rust/Python fixture pair. The separate state/lifecycle fixtures
prove two Brain keys and stale completion isolation; no claim of two simultaneously
running Brain servers or typing in the read-only trial is made.

New helper check on `0a215f39`, from repository root:

```powershell
C:/Work/Mentis-workspace/r1-fixtures/venv/Scripts/python.exe -m pytest -q tests/test_quiet_magnet_detached_report.py --basetemp .pytest_tmp/quiet-magnet-detached-final
```

Result: **3 passed, 0 failed, 0 skipped, 0 errors**. It verifies the required
client header and operation token, receipt-only persistence, no automatic second
verdict after success/refusal/lost response, and no report without configuration.
Only this helper changed on resumption, so unchanged client/build/unit suites
were not repeated. The 26-check browser run was repeated to verify the newly
started runtime at the actual handed-off address.

Initial development checks also completed: the first browser run exposed a
hover/click read timing defect (1 checkpoint then 1 failure); a later run corrected
the expected native root count (6 then 1 test failure); narrow Escape exposed a
focus-restoration defect (19 then 1 failure); a subsequent error-case locator was
too broad (20 then 1 test failure). The final 26-check run passes after the fixes.
An earlier fixture pytest invocation had 0 passed, 0 failed, 0 skipped and 3 setup
errors because `.pytest_tmp` did not exist; the documented mkdir/rerun passed 3.
Earlier focused source/renderer checks from their part branches are documented in
their returned results; every started process/test run was awaited to completion.

## No-mutation evidence and artifact contents

Setup writes end before the runtime baseline. The helper then warms the existing
memory-only object extractor through bounded same-page GETs as an explicit setup
precondition. Runtime baseline covers each Brain's full logical SQLite dump and
table counts (read-only connection, including WAL-visible records), presentation,
held artifacts and other content files including instance files. Physical SQLite/
WAL bytes and OS lock/`.mentis` files are excluded; the logical dump covers records.

The original foreground trial remained unchanged after its cleanup. After all
checks on the newly running detached preview, comparison again says
`unchanged:true`. Native reads and 10 routed identity/read/refusal probes were
checked. The access path refuses non-read methods and the writing capacity GET
before forwarding; it strips browser cookies/authority and targets only the named
loopback fixture front. Setup/probe traffic includes an intentionally refused own-
Conversation POST; browser traffic contains only GET/HEAD/OPTIONS and no activation,
Perspective/synthesis, own-Conversation creation, arrangement save or send request.
No legacy `mentis.fluid.magnet.seen:` key is used.

Evidence archive includes manifest, setup-warm log, baseline, unchanged comparison,
safe ready/probe result, accepted startup receipt, browser checkpoints/request trace, proxy traffic and
resting/quick/expanded/narrow PNGs. Private launcher state and report secrets are
excluded. The patch/bundle contains committed source and tests, not fixture bytes.
All workspaces and unpushed branches are preserved; nothing was deleted or merged
into a shared branch. Immediate owner action: nothing is required.


## Preserved workspaces

- `C:/Work/Mentis-workspace/day-to-day/quiet-magnet-candidate`, branch
  `quiet-magnet-candidate`: committed candidate, ignored disposable fixture,
  running preview metadata and logs; no uncommitted source.
- `C:/Work/Mentis-workspace/day-to-day/quiet-magnet-read`, branch
  `quiet-magnet-read`, tip `5d025acc`: committed Part A; its one local uncommitted
  optional-config contract edit matches the integrated parent seam and is preserved.
- `C:/Work/Mentis-workspace/day-to-day/quiet-magnet-puck`, branch
  `quiet-magnet-puck`, tip `3499656a`: committed renderer handoff and untracked
  browser log; integrated style/focus corrections are on the parent candidate.
- `C:/Work/Mentis-workspace/day-to-day/quiet-magnet-fixture`, branch
  `quiet-magnet-fixture`, tip `9ab98143`: committed fixture handoff, synthetic
  fixture/probe files and exact Rust binaries; no production data.

Nothing is merged into main or pushed. The final review request keeps this
bounded candidate pending; the overall Magnet Work remains with the carrier.
