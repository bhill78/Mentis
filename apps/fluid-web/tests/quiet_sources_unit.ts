/* MANAGE SOURCES IN QUIET CHAT, checked without a server or a browser
 * (src/quiet2/sources/words.ts): how a source stands (the run is read before
 * the backend's own `state`, which ignores it), what counts as needing
 * attention, the browser's tabs, kinds, search and order, what a failure is
 * said to be (the system's words kept; advice only for words it is known to
 * say; nothing that could be a credential shown), what a refresh and a
 * change of selection are said to do, and which kinds Add a source offers. */
import assert from 'node:assert/strict'
import type { CollectionView, Descriptor, RunView } from '../src/surfaces/sources/route'
import {
  SEARCH_FROM, attentionCount, failed, failureShort, failureWords, footWords, itemWord, kindsShown, listed, patternWords,
  heldWords, previewWords, redact, reviseWords, running, size, standing, sweepWords,
} from '../src/quiet2/sources/words'
import { plan } from '../src/quiet2/centreHistory'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { SOURCES_EVENT, placeWord, thingWord, writeRoute, type SearchAnswer, type SourcesRoute } from '../src/surfaces/sources/route'
import { admittedWords, heldLine, heldNote, kindsOf, kindsWords } from '../src/surfaces/sources/sqlite/figures'
import { searchProgress } from '../src/surfaces/sources/ContentSearch'
import { MISSING_FOLDER, folderMissing } from '../src/surfaces/sources/pick/PickSource'
import { chipAsk } from '../src/quiet2/sources/moving'
import { adding, previewHeld } from '../src/quiet2/sources/holding'
import { DISCARD, leaving } from '../src/quiet2/leaving'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import AddSourcePage from '../src/quiet2/sources/AddSourcePage'

const src = fileURLToPath(new URL('../src/', import.meta.url))

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const run = (state: RunView['state'], kind: RunView['kind'] = 'sweep', failure: string | null = null): RunView => ({
  run: 'run-1', key: 'col', kind, state, progress: { files: 12, bytes: 2048, current: 'a/b.md' }, started_at: 1, ended_at: state === 'running' ? null : 2,
  result: null, failure, failure_kind: failure ? 'Refused' : null, cancel_requested: false,
})
const source = (o: Partial<CollectionView> & { bound?: boolean; swept?: number | null; present?: number; bytes?: number }): CollectionView => ({
  collection: o.collection ?? 'col-' + (o.name ?? 'x'), name: o.name ?? 'Notes', connector: o.connector ?? 'filesystem', declared_by: 'ent-me', declared_at: 1_790_000_000,
  declaration: 'd', declared_scope: { include: ['*'], exclude: [] }, scope: { include: ['*'], exclude: [] }, revisions: [],
  counts: { present: o.present ?? 3, absent: 0, links_to: 0, embeds: 0, held_bytes: o.bytes ?? 1024, visible_not_selected: 0 },
  last_sweep: o.swept === null ? null : { act: 'a', at: o.swept ?? 1_794_000_000, actor: 'ent-me', batch: 'b', plan: 'p', counts: { new: 3 }, scope: { declaration: 'd', revision: null, within: null }, binding: 'x', binding_changed: false, not_acquired: [], refused: [], unexamined: [], visible_not_selected: 0 },
  sweeps: [], binding: { bound: o.bound ?? true, binding: 'bnd', state: o.bound === false ? 'not bound on this machine' : 'bound' },
  state: 'acquired · not refreshing', run: o.run ?? null,
})

/* -- how a source stands ---------------------------------------------------- */
{
  const s = standing(source({}))
  eq([s.tone, s.label, s.attention], ['ok', 'Connected here', false], 'bound and taken: connected here')
  ok(/^3 files · refreshed /.test(s.words), 'a folder holds files, and says when it was refreshed')

  const r = standing(source({ run: run('running') }))
  eq([r.tone, r.label, r.attention], ['run', 'Refreshing now', false], 'a running sweep is said first, whatever the backend state says')
  eq(r.words, '12 files, 2.0 KB so far', 'progress is files and bytes: no percentage')
  eq(standing(source({ run: run('running', 'plan') })).label, 'Looking at the source', 'a preview looks; it is not called a refresh')

  const f = standing(source({ run: run('refused', 'plan', 'authentication required: https://git.example.com/a/b.git') }))
  eq([f.tone, f.label, f.words, f.attention], ['bad', 'Last preview failed', 'sign-in was refused', true], 'a refused run needs attention, in a few words')
  eq(standing(source({ run: run('failed', 'sweep', 'disk full') })).label, 'Last refresh failed', 'a failed sweep is a failed refresh')
  eq(standing(source({ run: run('cancelled', 'sweep', 'cancelled by the owner') })).attention, false, 'a cancelled run is not a problem')
  eq(standing(source({ run: run('done') })).tone, 'ok', 'a finished run leaves the source as it stands')

  const off = standing(source({ bound: false }))
  eq([off.tone, off.label], ['off', 'Not connected on this machine'], 'held, not connected here')
  ok(/^3 files held · taken /.test(off.words), 'what is held stays said when it is not connected')
  eq([standing(source({ bound: false, swept: null })).tone, standing(source({ bound: false, swept: null })).words], ['none', 'nothing taken yet'], 'declared only')
  eq(standing(source({ swept: null })).words, 'nothing taken yet', 'connected, nothing taken')
  eq(running(source({ run: run('done') })), null, 'only a running run is running')
  eq(failed(source({ run: run('cancelled') })), null, 'cancelled is not failed')
}

/* -- words for what is held ---------------------------------------------------- */
eq([itemWord('filesystem', 1), itemWord('filesystem', 2), itemWord('git', 7), itemWord('sqlite', 1), itemWord('slack', 3)],
  ['file', 'files', 'items', 'record', 'items'], 'a repository holds change records too, so it is counted in items')
eq([size(0), size(900), size(2048), size(5 * 1024 * 1024), size(3 * 1024 ** 3), size(null)], ['0 B', '900 B', '2.0 KB', '5.0 MB', '3.0 GB', '—'], 'sizes')

/* -- failures ------------------------------------------------------------------ */
{
  const a = failureWords('authentication required: https://git.example.com/acme/handbook.git')
  eq(a.title, 'sign-in was refused', 'a known failure is named')
  ok(/Mentis holds no password/.test(a.advice ?? ''), 'and says what to do, without asking for a password')
  eq(a.said, 'authentication required: https://git.example.com/acme/handbook.git', 'the system’s own words are kept')
  eq(failureWords('unknown host key: example').title, 'this machine does not know the server’s key', 'host key')
  eq(failureWords('not found, or no access: x').title, 'it was not found, or this machine has no access to it', 'not found')
  eq(failureWords('unreachable: https://git.invalid/x.git could not be reached').title, 'the server could not be reached', 'unreachable')
  const u = failureWords('the plan is stale')
  eq([u.title, u.advice, u.said], [null, null, 'the plan is stale'], 'an unknown failure is shown as said, with nothing guessed')
  eq(failureWords(null).said, 'No reason was given.', 'no reason')
  eq(redact('fatal: could not read https://brian:hunter2@git.example.com/a.git'), 'fatal: could not read https://…@git.example.com/a.git', 'a credential in an address is never shown')
  eq(failureWords('unreachable: ssh://token@host/x').said, 'unreachable: ssh://…@host/x', 'and not in a failure')
  eq(redact('git@host:owner/repo.git'), 'git@host:owner/repo.git', 'an ssh short address has no secret in it')
  eq(failureShort('x'.repeat(100)).length, 58, 'a long unknown failure is cut for a row')
}

/* -- the browser: tabs, kind, search, order --------------------------------------- */
{
  const all = [
    source({ name: 'Zeta notes', swept: 100, bytes: 10 }),
    source({ name: 'Alpha repo', connector: 'git', swept: 300, bytes: 500, bound: false }),
    source({ name: 'Handbook', connector: 'git', swept: 200, bytes: 50, run: run('refused', 'plan', 'authentication required: x') }),
    source({ name: 'Ledger', connector: 'sqlite', swept: null, bytes: 0 }),
  ]
  const label = (c: string) => ({ filesystem: 'Folder on this machine', git: 'Git repository', sqlite: 'SQLite database file' }[c] ?? c)
  const names = (rows: CollectionView[]) => rows.map((c) => c.name)
  const by = { q: '', tab: 'all' as const, kind: '', order: 'recent' as const }
  eq(names(listed(all, by, label)), ['Alpha repo', 'Handbook', 'Zeta notes', 'Ledger'], 'most recently refreshed first; never refreshed last')
  eq(names(listed(all, { ...by, order: 'name' }, label)), ['Alpha repo', 'Handbook', 'Ledger', 'Zeta notes'], 'by name')
  eq(names(listed(all, { ...by, order: 'size' }, label)), ['Alpha repo', 'Handbook', 'Zeta notes', 'Ledger'], 'largest first')
  eq(names(listed(all, { ...by, tab: 'here' }, label)), ['Handbook', 'Zeta notes', 'Ledger'], 'connected here')
  eq(names(listed(all, { ...by, tab: 'away' }, label)), ['Alpha repo'], 'not connected')
  eq(names(listed(all, { ...by, tab: 'attention' }, label)), ['Handbook'], 'needs attention is a failed or refused last run, nothing else')
  eq(names(listed(all, { ...by, kind: 'git' }, label)), ['Alpha repo', 'Handbook'], 'by kind')
  eq(names(listed(all, { ...by, q: '  ZETA ' }, label)), ['Zeta notes'], 'search by name, any case')
  eq(names(listed(all, { ...by, q: 'sqlite' }, label)), ['Ledger'], 'search by kind words')
  eq(listed(all, { ...by, q: 'nothing like it' }, label), [], 'no match')
  eq(all.map((c) => c.name), ['Zeta notes', 'Alpha repo', 'Handbook', 'Ledger'], 'the list read is not reordered in place')
  eq(attentionCount(all), 1, 'the tab’s count')
  eq(footWords(4, all), '4 sources · 3 connected on this machine · 560 B held', 'the foot, all shown')
  eq(footWords(1, all), '1 of 4 sources · 3 connected on this machine · 560 B held', 'the foot, narrowed')
  eq(footWords(1, [all[0]]), '1 source · 1 connected on this machine · 10 B held', 'one source')
}

/* -- what a refresh and a change of selection are said to do ------------------------ */
eq(sweepWords({ new: 3, changed: 2, reappeared: 1, absent: 1, withheld: 2, not_examined: 4, unchanged: 9 }),
  '3 new, 3 changed, 1 gone from the source, 2 withheld, 4 not examined', 'each thing a sweep did, kept apart')
eq(sweepWords({ unchanged: 86 }), 'nothing changed (86 unchanged)', 'nothing changed')
eq(sweepWords(null), 'nothing changed', 'no counts')
eq(previewWords({ new: 1, changed: 1 }), '1 new, 1 changed', 'a preview that would take something')
eq(previewWords({ unchanged: 5 }), 'Nothing has changed since the last refresh.', 'a preview with nothing to take')
eq(reviseWords({ not_examined: 1 }), '1 would leave the selection: kept as held, no longer refreshed.', 'what leaves a selection is kept, and said')
eq(reviseWords({ new: 2, not_examined: 1 }), '2 new. 1 would leave the selection: kept as held, no longer refreshed.', 'both')
eq(reviseWords({}), 'This change takes nothing new and leaves nothing out that is held.', 'a change with no effect on what is held')
eq([patternWords(['*']), patternWords([]), patternWords(['*.md', '*.txt']), patternWords(null)], ['everything', 'nothing', '*.md  *.txt', 'nothing'], 'patterns as a person reads them')

/* -- Add a source: only what the system says is available ---------------------------- */
{
  const d = (id: string, label: string, available: boolean, summary = ''): Descriptor => ({
    id, label, available, binding: 'local-folder', scope_fields: [], presets: [], preview: 'exact', modes: [], live: null, browse: 'hierarchy', key: 'path', summary, connect: '',
  })
  const ds = [d('filesystem', 'Folder on this machine', true, 'Files under a folder you choose'), d('git', 'Git repository', true, 'A repository'), d('slack', 'Slack', false)]
  eq(kindsShown(ds, '').map((x) => x.id), ['filesystem', 'git'], 'unavailable kinds are not offered')
  eq(kindsShown(ds, 'repo').map((x) => x.id), ['git'], 'narrowed by name')
  eq(kindsShown(ds, 'folder you').map((x) => x.id), ['filesystem'], 'and by what a kind says of itself')
  eq(kindsShown(ds, 'slack'), [], 'a search never brings an unavailable kind forward')
  ok(SEARCH_FROM > 3, 'three kinds are cards with no search line')
}

/* -- the centre column in the browser's history (centreHistory.ts) --------------------
   The page's own Back asks the BROWSER to go back to the place, where it is
   behind; only a place that is not behind is pushed. So Back from a file is
   the source, Back from the source is the conversation, and neither can be
   a different page. */
{
  type Place = { source: { view: { page: string; col: string }; reading: null | { at: string; col: string; key: string } } }
  const src: Place = { source: { view: { page: 'source', col: 'c1' }, reading: null } }
  const file: Place = { source: { view: { page: 'source', col: 'c1' }, reading: { at: 'object', col: 'c1', key: 'a.md' } } }
  const other: Place = { source: { view: { page: 'source', col: 'c2' }, reading: null } }
  eq(plan([null, src, file], 2, src), -1, 'Back from a file read in place: one entry back, the source')
  eq(plan([null, src, file], 2, null), -2, 'Back to the conversation from a file: two entries back')
  eq(plan([null, src], 1, null), -1, 'Back from a source: the conversation, one entry back')
  eq(plan([null, src], 1, src), 0, 'the place already shown is not entered twice')
  eq(plan([null, src], 1, file), null, 'a file is a new entry')
  eq(plan([null, src, null, other], 3, src), -2, 'the nearest entry behind that is the place')
  eq(plan([null, src, null, other], 3, null), -1, 'and the nearest conversation, not the first')
  eq(plan([undefined, undefined, src] as (Place | null | undefined)[], 2, null), null, 'after a reload what is behind is unknown: pushed, never guessed')
  eq(plan<Place>([null], 0, null), 0, 'the conversation, from the conversation')
}

/* ============================================================================
 * FUNCTIONAL REPAIRS, 2026-11-18 (the UI audit's confirmed defects D-2 … D-14)
 * ========================================================================== */

/* -- D-3: what a reference chip's press means in Quiet Chat (moving.ts) -------------
   The chip announces a Sources ADDRESS (route.ts `writeRoute`); Quiet Chat has
   screens, not addresses. Each of the three presses must land on a screen. */
{
  const say = (r: SourcesRoute) => chipAsk(writeRoute(r))
  eq(say({ at: 'observation', ref: 'adm-1' }), { to: 'content', route: { at: 'observation', ref: 'adm-1' }, col: null, ref: 'adm-1' },
    '"Open in Sources" and "Go to latest": the hosted reader, on that observation; its source is asked of the record')
  eq(say({ at: 'compare', a: 'adm-1', b: 'adm-2' }), { to: 'content', route: { at: 'compare', a: 'adm-1', b: 'adm-2' }, col: null, ref: 'adm-2' },
    '"Compare": the hosted compare view')
  const cite = say({ at: 'observation', ref: 'adm-1', extraction: 'pdf-1', span: { offset: 4, end: 9 } })
  eq(cite.to === 'content' && cite.route, { at: 'observation', ref: 'adm-1', extraction: 'pdf-1', span: { offset: 4, end: 9 } },
    'a citation of extracted text keeps its extraction and its place')
  eq(say({ at: 'object', col: 'col-1', key: 'notes/a b.md' }), { to: 'content', route: { at: 'object', col: 'col-1', key: 'notes/a b.md' }, col: 'col-1', ref: null },
    'a held object names its own source')
  eq(say({ at: 'collection', col: 'col-1', tab: 'sweeps' }), { to: 'source', col: 'col-1' }, 'a source: its page (Quiet Chat has no tabs)')
  eq([say({ at: 'flow', connector: 'git' }), say({ at: 'add' }), say({ at: 'overview' })],
    [{ to: 'add', connector: 'git' }, { to: 'add', connector: null }, { to: 'browser' }], 'Add a source, and the browser')
  eq(chipAsk(''), { to: 'browser' }, 'an empty address is the browser, never an error')

  /* and Quiet Chat LISTENS: the event only Fluid's shell heard */
  const quiet = readFileSync(src + 'quiet2/Quiet2.tsx', 'utf8')
  ok(/window\.addEventListener\(SOURCES_EVENT,/.test(quiet), 'Quiet2 listens for the chip event (mentis:sources)')
  eq(SOURCES_EVENT, 'mentis:sources', 'the event the chips dispatch')
  for (const chip of ['AcquiredChip.tsx', 'CiteChip.tsx']) {
    const text = readFileSync(src + 'surfaces/sources/' + chip, 'utf8')
    ok(/e\.key !== 'Escape'/.test(text) && /addEventListener\('keydown', esc, true\)/.test(text), `${chip}: Escape closes the popover`)
  }
}

/* -- D-2: "Open <name>" after a SQLite revise goes somewhere ------------------------- */
{
  const edit = readFileSync(src + 'surfaces/sources/sqlite/SqliteEdit.tsx', 'utf8')
  ok(!/go=\{\(\)\s*=>\s*\{\}\}/.test(edit), 'the editor is no longer handed a `go` that does nothing')
  /* BOTH halves of the defect: the editor's `go` did nothing, AND the button only
     pressed it for a result that names its collection -- which a revise's does not */
  const flow = readFileSync(src + 'surfaces/sources/sqlite/SqliteFlow.tsx', 'utf8')
  ok(/const col=result\.collection\?\?editing\?\.collection;if\(col\)go\(/.test(flow), 'the button opens the collection being edited when the result names none')
  ok(!/result\.collection&&go\(/.test(flow), 'and no longer needs the result to name it')
  ok(/onOpen: \(\)=>void/.test(edit) && /r\.at==='collection'\)onOpen\(\)/.test(edit), 'its host is REQUIRED to say how the page of the source is opened')
  ok(/onOpen=\{\(\) => \{ close\(\); changed\(\) \}\}/.test(readFileSync(src + 'quiet2/sources/SourcePage.tsx', 'utf8')), 'Quiet Chat: the editor is closed and the page read again')
  ok(/onOpen=\{\(\) => go\(\{ at: 'collection', col: c\.collection, tab: 'overview' \}\)\}/.test(readFileSync(src + 'surfaces/sources/Collection.tsx', 'utf8')), 'Fluid: the overview of the source')
}

/* -- D-5: the form's own Cancel asks what Back asks ---------------------------------- */
{
  const quiet = readFileSync(src + 'quiet2/Quiet2.tsx', 'utf8')
  ok(/onBack=\{sourcesBack\}.*onCancel=\{sourcesBack\}/.test(quiet), 'Cancel leaves through the same guarded way out as Back')
  ok(/const sourcesBack = \(\) => guarded\(sourcesOut\)/.test(quiet), 'which asks first where something would be lost')
  const filled = leaving(adding({ typed: true, preview: false, run: null, done: false }))
  eq([filled.ask?.title, filled.ask?.lines, filled.ask?.leave], ['Leave Add a source unfinished?', ['What you have filled in here is not saved anywhere.'], DISCARD], 'something filled in: the same question, the same words')
  eq(leaving(adding({ typed: false, preview: false, run: null, done: false })).ask, null, 'nothing filled in: it leaves at once')
  eq(leaving(adding({ typed: true, preview: true, run: null, done: true })).ask, null, 'the source was taken: nothing is unfinished')
}

/* -- D-14: a refresh preview that found nothing holds nobody -------------------------- */
{
  const nothing = { counts: { unchanged: 7 } as Record<string, number>, binding_changed: false, can_confirm: true }
  const plain = { revising: false, decisionsDirty: false }
  eq(previewWords(nothing.counts), 'Nothing has changed since the last refresh.', 'the preview in question')
  eq(previewHeld(nothing, plain), false, 'nothing to apply: no leave question')
  eq(leaving({ what: 'Notes', dirty: false, preview: previewHeld(nothing, plain), run: null }).ask, null, 'so leaving goes at once')
  eq(previewHeld({ ...nothing, counts: { unchanged: 6, changed: 1 } }, plain), true, 'a preview that would take something is still asked about')
  eq(previewHeld({ ...nothing, counts: { absent: 1 } }, plain), true, 'something gone from the source counts')
  eq(previewHeld({ ...nothing, binding_changed: true }, plain), true, 'the first refresh of a place located again: taking it accepts the place')
  eq(previewHeld({ ...nothing, can_confirm: false }, plain), true, 'a preview waiting for decisions')
  eq(previewHeld(nothing, { revising: false, decisionsDirty: true }), true, 'decisions begun and not previewed')
  eq(previewHeld(nothing, { revising: true, decisionsDirty: false }), true, 'a change of selection is unsaved work of the reader')
  eq(previewHeld(null, plain), false, 'no preview in hand')
}

/* -- D-11: one SQLite acquisition, counted the same way everywhere ------------------- */
{
  const admit = ['customers/@schema', 'customers/k-1', 'customers/k-2', 'customers/k-3', 'orders/@schema', 'orders/k-1', 'orders/k-2'].map((path) => ({ path }))
  eq(kindsOf(admit), { schema: 2, row: 5 }, 'what a plan would record, by what it is')
  eq(admittedWords(admit), '7 Admissions recorded (5 rows and 2 table schemas)', 'the confirmation: 7 is rows AND schemas, and says so')
  eq(heldLine(2, { row: 5, schema: 2 }), '2 tables · 5 rows are now in Mentis, held as 7 records (5 rows and 2 table schemas).', 'the result: rows, and the records they are held as')
  eq(heldWords({ connector: 'sqlite', counts: { ...source({}).counts, present: 7, kinds: { row: 5, schema: 2 } } }), '7 records (5 rows and 2 table schemas)', 'the source page: "a copy of 7 records" adds up')
  eq(heldWords({ connector: 'filesystem', counts: { ...source({}).counts, present: 7 } }), '7 files', 'a folder names no kinds')
  /* AFTER A REVISE that takes no new row (the plan's `new` is 0, two rows widened) */
  eq(heldLine(2, { row: 6, schema: 2 }), '2 tables · 6 rows are now in Mentis, held as 8 records (6 rows and 2 table schemas).', 'the rows HELD after the revise, never the 0 new of the plan')
  /* KINDS ABSENT (the count not read yet, or the read failed): no number of rows at all,
     for a first acquisition as for a revise -- the plan's `new` is not what is held */
  eq(heldLine(2, null), '2 tables are now in Mentis.', 'before the count is read, no number is claimed')
  eq(heldLine(1, undefined), '1 table is now in Mentis.', 'one table')
  eq(heldLine(2, {}), '2 tables are now in Mentis.', 'a count that names no kinds says no rows either')
  for (const absent of [null, undefined, {}]) ok(!/\d[\d,]* rows?\b/.test(heldLine(3, absent)), 'kinds absent: never a number of rows')
  eq([heldNote('pending'), heldNote('failed'), heldNote('read')], ['Counting what is held…', 'The exact counts could not be read.', ''], 'said beside it while the count is read, and where it could not be')
  eq(sweepWords({ widened: 2, unchanged: 6 }), '2 widened', 'a revise that widened two rows did not change nothing')
  eq(kindsWords({ schema: 1, snapshot: 1 }), '1 table held whole and 1 table schema', 'a keyless table is one record, not rows')
  eq(heldLine(1, { schema: 1, snapshot: 1 }), '1 table · 1 table held whole are now in Mentis, held as 2 records (1 table held whole and 1 table schema).', 'and is never counted as rows')
  eq(kindsWords({ row: 1, schema: 1, snapshot: 2 }), '1 row, 2 tables held whole and 1 table schema', 'all three')
  eq([kindsWords(undefined), kindsWords({})], ['', ''], 'no kinds, no words')
  ok(!/\brows?\b/.test(heldLine(1, { schema: 1, snapshot: 1 })), 'a keyless table: a snapshot, and the word "rows" nowhere')
  eq(heldLine(2, { row: 3, schema: 2, snapshot: 1 }), '2 tables · 3 rows and 1 table held whole are now in Mentis, held as 6 records (3 rows, 1 table held whole and 2 table schemas).', 'a keyed table beside a keyless one')
  const flow = readFileSync(src + 'surfaces/sources/sqlite/SqliteFlow.tsx', 'utf8')
  ok(!/counts\.new\?\?0\)\} rows are now in Mentis/.test(flow), 'the result line is not built from the `new` of the plan any more')
  ok(!/heldLine\([^)]*counts\.new/.test(flow), 'nor is the `new` of the plan given to it as a stand-in')
}

/* -- D-8: a place and its things, called what they are -------------------------------- */
{
  eq(['filesystem', 'git', 'sqlite', 'slack', undefined].map(placeWord), ['folder', 'repository', 'database', 'source', 'source'], 'the place a preview reads')
  eq([thingWord('sqlite', 1), thingWord('sqlite', 7), thingWord('git', 0), thingWord('filesystem', 0)], ['record', 'records', 'items', 'files'], 'and what is counted in it')
  eq(standing(source({ connector: 'git', run: run('running') })).words, '12 items, 2.0 KB so far', 'a repository being taken is not "12 files"')
  eq(standing(source({ connector: 'sqlite', run: run('running') })).words, '12 records, 2.0 KB so far', 'nor a database')
  const answer = { coverage: { complete: true, exhaustive: true, examined: { objects: 7, bytes: 1 }, total: { objects: 7, bytes: 1 }, remaining: { objects: 0, bytes: 0 }, matches_so_far: 1, slice: 1 }, next: null, slice: { continuation: null } } as unknown as SearchAnswer
  eq(searchProgress(answer, thingWord('sqlite', 2)).coverage, 'complete: all 7 records searched', 'a database search counts records')
  eq(searchProgress(answer).coverage, 'complete: all 7 files searched', 'the words of a folder are unchanged')
  const parts = readFileSync(src + 'surfaces/sources/parts.tsx', 'utf8')
  ok(/Reading the \$\{placeWord\(connector\)\} for a preview/.test(parts) && !/Reading the folder for a preview/.test(parts), 'the run bar names the place by its connector')
}

/* -- D-4: a place that is not there, in plain words ----------------------------------- */
{
  const f = failureWords("[WinError 2] The system cannot find the file specified: 'C:\\\\nope\\\\missing'")
  eq(f.title, 'that place does not exist on this machine', 'the headline is a plain sentence')
  ok(/WinError 2/.test(f.said), 'and the words of the system are kept as the detail')
  eq(failureWords("[WinError 3] The system cannot find the path specified: 'D:\\\\x'").title, 'that place does not exist on this machine', 'a missing parent too')
  eq(failureShort("[Errno 2] No such file or directory: '/x'"), 'that place does not exist on this machine', 'in a list row')
  eq(MISSING_FOLDER, 'That folder does not exist on this machine.', 'what the picker says when the path is used')
  /* what the folder chooser read answers for a missing path (mentis/sources/filesystem.py), and the system's own forms */
  ok(folderMissing('cannot open that folder (FileNotFoundError)'), 'the refusal the read itself gives a missing folder')
  ok(folderMissing('[WinError 2] The system cannot find the file specified'), 'the Windows form the audit saw')
  ok(folderMissing("[WinError 3] The system cannot find the path specified: 'D:\\\\x'") && folderMissing("[Errno 2] No such file or directory: '/x'"), 'a missing parent, and the POSIX form')
  ok(!folderMissing('that is a link, junction or not a folder') && !folderMissing('cannot open that folder (PermissionError)') && !folderMissing('choose a folder by its absolute path') && !folderMissing('Failed to fetch'), 'any other refusal leaves the path to the flow')
  ok(/folderMissing\(e\.message\)/.test(readFileSync(src + 'surfaces/sources/pick/PickSource.tsx', 'utf8')), 'and the picker decides on it')
  ok(/api\/sources\/folders/.test(readFileSync(src + 'surfaces/sources/pick/PickSource.tsx', 'utf8')), 'asked of the folder chooser read, when the path is used')
}

/* -- D-12: a failed run does not disconnect a source ----------------------------------- */
ok(!/'Held · not refreshed'/.test(readFileSync(src + 'quiet2/sources/SourcePage.tsx', 'utf8')), 'the status says how it is connected, whatever the last run did')

/* -- ADD A SOURCE SAYS WHICH OF THREE THINGS IS TRUE (owner ent-24beca915507) ----------
   `descriptors` is `[]` both before `/api/sources` answers and when it answers with
   nothing, and the page used to read the two as one and say "No kind matches." --
   a verdict about the kinds, stated before anything had been asked. Opened straight
   from its own address, which is how a bookmark, a reload or a link arrives, that is
   what a reader met for as long as the read took (measured here: nine seconds on a
   cold server over a copy of TEST's Brain), and it is why a prior round reported the
   wizard as offering no kinds at all (ent-3e0abfa18d84). */
{
  const panel = (descriptors: Descriptor[], read: boolean) => renderToStaticMarkup(createElement(AddSourcePage, {
    descriptors, read, me: null, connector: null,
    onConnector: () => {}, onOpenSource: () => {}, onChanged: () => {}, onCancel: () => {},
  }))
  const kinds: Descriptor[] = [
    { id: 'filesystem', label: 'Folder on this machine', summary: 'Files under a folder you choose', available: true, binding: 'local-folder', presets: [], scope_fields: [] } as unknown as Descriptor,
  ]
  const reading = panel([], false)
  ok(reading.includes('Reading the kinds of source this Brain can take'), 'before the source system answers, the page says it is reading')
  ok(!reading.includes('No kind matches'), 'and states no verdict about kinds it has not been told about')
  const none = panel([], true)
  ok(none.includes('No kind of source can be taken on this machine'), 'answered with nothing, it says that, which is a different thing')
  ok(!none.includes('No kind matches'), 'and still does not blame a search nobody made')
  const some = panel(kinds, true)
  ok(some.includes('Folder on this machine'), 'answered with kinds, the kinds are offered')
  ok(!some.includes('No kind matches') && !some.includes('Reading the kinds'), 'and nothing is said about having none')
}

console.log(`quiet_sources_unit: ${checks} checks passed`)
