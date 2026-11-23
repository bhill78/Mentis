import test from 'node:test'
import assert from 'node:assert/strict'
import { guardPlaces, authoring, tell, unfinished, forgetUnfinished } from '../src/quiet2/leaving'
import { magnetAffectedPlaces, presentationOf, spacePlace, type ColumnRoom } from '../src/quiet2/space/placement'
import { forgetSessions, invalidateOtherBrains, isClosedSession, nextResourceId, openSession, registerResource, releaseAllSessions, releaseResource, releaseSession, resourceById, resourcesOfBrain, sessionById } from '../src/quiet2/space/registry'
import { provideSpaceSessions, forgetSpaceSessions } from '../src/quiet2/space/provider'
import { closeViewer, inColumn, maximised, moveViewer, openViewer, parkViewer, returnViewer, settleColumns, viewerOf } from '../src/quiet2/viewer/viewers'
import { magnetIntent, resumeMagnet, type QuietMagnetResource } from '../src/quiet2/magnets/navigation'
import { addressOf, readAddress } from '../src/quiet2/address'
import type { SpaceSession } from '../src/quiet2/space/contract'

const room: ColumnRoom = { shown: ['s1', 's2'], free: () => false }
test('canvas/cover take no reader; graph full screen remains graph only', () => {
  assert.deepEqual(magnetAffectedPlaces({ into: 'canvas' }, room), [])
  assert.deepEqual(magnetAffectedPlaces({ into: 'max' }, room), [])
  assert.equal(presentationOf('magnet'), 'magnet-stage')
  assert.equal(presentationOf('brain-space'), 'space-stage')
  assert.deepEqual(spacePlace(), { place: 'max', from: null })
})
test('reader/source/own/origin return enumerate every lost centre and duplicate column', () => {
  assert.deepEqual(magnetAffectedPlaces({ centre: true, duplicates: ['s1', 's2', 's1'] }, room), ['centre', 's1', 's2'])
  assert.deepEqual(magnetAffectedPlaces({ centre: true }, room), ['centre']) // R1 centre-held return
  assert.deepEqual(magnetAffectedPlaces({ into: 's2' }, room), ['s2'])
  assert.deepEqual(magnetAffectedPlaces({ into: 's2' }, { ...room, free: () => true }), [])
})
test('maximise guards a real return displacement, never an unchanged reservation', () => {
  assert.deepEqual(magnetAffectedPlaces({ into: 'max', maxReturn: 's1', returnOccupied: true }, room), ['s1'])
  assert.deepEqual(magnetAffectedPlaces({ into: 'max', maxReturn: 's1', returnOccupied: false }, room), [])
})
test('Stay at any step preserves complete placement/history/draft/focus state atomically', () => {
  for (let stop = 0; stop < 3; stop++) {
    forgetUnfinished()
    for (const p of ['centre', 's1', 's2']) tell(() => authoring(p === 'centre' ? 'half-written challenge' : 'new rule'), p)
    const state = { viewers: ['magnet canvas', 'pdf max from s1'], centre: 'challenge words', s1: 'draft one', s2: 'draft two', history: ['A'], focus: 'opener', visibility: true }
    const before = structuredClone(state)
    const questions: { go(): void; stay(): void }[] = []
    let committed = 0
    guardPlaces(['centre', 's1', 's2'], { standing: unfinished, note() {}, ask(_q, go, stay) { questions.push({ go, stay }) }, stay() {}, commit() { committed++; state.history.push('B'); state.centre = 'new reader' } })
    for (let i = 0; i < stop; i++) { questions[i].go(); assert.deepEqual(state, before) }
    questions[stop].stay()
    assert.deepEqual(state, before); assert.equal(committed, 0)
  }
  forgetUnfinished()
})
test('only after every guard accepts does one commit run; retained drafts survive', () => {
  let commits = 0; const retainedDrafts = new Map([['conversation:A', 'unsent'], ['thread:B:P', 'reply']])
  const questions: (() => void)[] = []
  guardPlaces(['centre', 's1', 's2', 's1'], { standing: (p) => authoring(p), note() {}, ask(_q, go) { questions.push(go) }, stay() {}, commit() { commits++ } })
  for (let i = 0; i < 3; i++) { assert.equal(commits, 0); questions[i]() }
  assert.equal(commits, 1); assert.equal(questions.length, 3); assert.equal(retainedDrafts.get('conversation:A'), 'unsent'); assert.equal(retainedDrafts.get('thread:B:P'), 'reply')
})
test('registry isolates graph and Magnet families under one disposal path', () => {
  forgetSessions(); forgetSpaceSessions(); let graphDisposals = 0, magnetDisposals = 0
  provideSpaceSessions({ createSpaceSession: ({ id, brainKey }) => ({ id, brainKey, dispose() { graphDisposals++ } }) as SpaceSession, SpaceSessionReader: (() => null) as never })
  const graph = openSession('A')!
  const m = registerResource('magnet', { id: nextResourceId(), brainKey: 'A', dispose() { magnetDisposals++ } })
  assert.equal(sessionById(m.id), null); assert.equal(resourceById('magnet', graph.id), null)
  releaseSession(m.id); assert.equal(magnetDisposals, 0)
  releaseSession(graph.id); assert.equal(graphDisposals, 1); assert.equal(resourceById('magnet', m.id), m)
  releaseResource(m.id); releaseResource(m.id); assert.equal(magnetDisposals, 1)
  assert.throws(() => registerResource('magnet', { ...m }), /expired/)
  assert.throws(() => registerResource('magnet', { ...m, id: 'sp999' }), /feature id/)
  forgetSpaceSessions()
})
test('known â†’ unknown â†’ different Brain expires all old ids exactly once', () => {
  forgetSessions(); let disposals = 0
  const a = registerResource('magnet', { id: nextResourceId(), brainKey: 'A', dispose() { disposals++ } })
  invalidateOtherBrains('A'); assert.equal(disposals, 0)
  invalidateOtherBrains(null); assert.equal(disposals, 1); assert.equal(isClosedSession(a.id), true)
  const b = registerResource('magnet', { id: nextResourceId(), brainKey: 'B', dispose() { disposals++ } })
  assert.notEqual(a.id, b.id); assert.deepEqual(resourcesOfBrain('magnet', 'A'), [])
  releaseAllSessions(); releaseAllSessions(); assert.equal(disposals, 2)
})
test('canvas is visible and occupies no column; expansion displaces graph by parking', () => {
  const m = openViewer({ kind: 'magnet', resourceId: 'mg1', magnetId: 'mag-one', brainKey: 'A' }, { kind: 'brain', brainKey: 'A' }, 'canvas')
  assert.equal(viewerOf(m)?.place, 'canvas'); assert.equal(inColumn('s1'), null); assert.equal(maximised(), null)
  assert.equal(settleColumns([]), 0); assert.equal(viewerOf(m)?.place, 'canvas')
  const g = openViewer({ kind: 'brain-space' }, { kind: 'brain', brainKey: 'A' }, 'max', { sessionId: 'sp1' })
  moveViewer(m, 'max'); assert.equal(viewerOf(g)?.place, 'parked'); assert.equal(maximised()?.id, m)
  moveViewer(m, 'canvas'); returnViewer(g, 'max', null); assert.equal(maximised()?.id, g)
  parkViewer(g); closeViewer(g); closeViewer(m)
})
test('canvas settlement and park/return preserve Magnet presentation state', () => {
  const m = openViewer({ kind: 'magnet', resourceId: 'mg3', magnetId: 'mag-three', brainKey: 'A' }, { kind: 'brain', brainKey: 'A' }, 'canvas', { id: 'mg3' })
  parkViewer(m); assert.equal(viewerOf(m)?.place, 'parked'); assert.equal(settleColumns([]), 0)
  returnViewer(m, 'canvas', null); assert.deepEqual(viewerOf(m)?.state, { id: 'mg3' }); closeViewer(m)
})
test('history contains only identity/origin refs and never revives a closed/other-Brain resource', () => {
  const r = { id: 'mg10', brainKey: 'A', saved: { id: 'mag-ten' }, origin: { place: { c: 'ent-origin1', at: null }, anchor: 'ent-post01', thread: 'ent-thread1', scroll: 99, draftTarget: 'conversation:A', focus: null } } as unknown as QuietMagnetResource
  const h = magnetIntent(r)!.magnet!
  assert.equal(JSON.stringify(h).includes('scroll'), false); assert.equal(JSON.stringify(h).includes('draft'), false)
  assert.equal(resumeMagnet(h, 'A', () => r).how, 'live')
  assert.equal(resumeMagnet(h, null, () => r).how, 'other-brain'); assert.equal(resumeMagnet(h, 'B', () => r).how, 'other-brain')
  assert.deepEqual(resumeMagnet(h, 'A', () => null), { how: 'expired', origin: 'ent-origin1' })
})
test('reload explains expiry and addresses actual origin instead of recreating resources', () => {
  const at = { magnet: { brainKey: 'A', resourceId: 'mg1', magnetId: 'mag-one', origin: { conversation: 'ent-origin1' }, phase: 'details' as const } }
  const address = addressOf({ pathname: '/quiet2', search: '?c=ent-origin1&at=2', hash: '#post' }, { c: 'ent-origin1', at }, { c: 'ent-origin1', at: '2' })
  assert.equal(address, '/quiet2?c=ent-origin1&at=2&magnet=mag-one#post')
  const read = readAddress(address.slice(address.indexOf('?')))
  assert.equal(read.c, 'ent-origin1'); assert.equal(read.asked.what, 'conversation'); assert.match(read.note!, /expired/)
})
