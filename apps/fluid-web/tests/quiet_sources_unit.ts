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
  previewWords, redact, reviseWords, running, size, standing, sweepWords,
} from '../src/quiet2/sources/words'
import { plan } from '../src/quiet2/centreHistory'

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

console.log(`quiet_sources_unit: ${checks} checks passed`)
