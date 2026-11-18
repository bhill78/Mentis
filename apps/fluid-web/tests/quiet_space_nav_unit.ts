/* THE 3D BRAIN IN QUIET CHAT: its navigation, checked without a server, a
 * browser or a canvas (owner request ent-af6b8ce6355f; contract and rows from
 * the B1 addendum adm-9f12e8153ca3, §§1, 3, 4).
 *
 * What is checked here:
 *   - §1 THE AGREED CONTRACT: the calls Quiet Chat makes on a session are
 *     exactly the ones the contract names, and a session's id, Brain key and
 *     disposal behave as the registry depends on;
 *   - §1 BRAIN KEYS: an identity not yet read is never a key, and two Brains
 *     (or two origins, or the two proxied Brains) never share one;
 *   - §1 THE REGISTRY: one live graph per Brain, ids never reused, one
 *     release path, disposal once, a closed id expired for this page;
 *   - §3 PARKING: a parked graph keeps its id and its renderer's state, holds
 *     no column and no maximised reservation, is invisible to `maximised`,
 *     `inColumn` and column settlement, and is parked -- never closed -- by
 *     every generic path;
 *   - §3 COMING BACK: the restoration priority, including max without `from`,
 *     an old column that is now occupied, and one that is no longer shown;
 *   - §3 THE GUARD SET: which places a transition actually displaces, so the
 *     leaving question is put for those and no others, and a Stay leaves
 *     everything as it was;
 *   - §3 HISTORY: the entry shapes, that the same graph entry is found behind
 *     rather than pushed again, and every expiry case -- a closed id, a
 *     reload, an inspect target, another Brain -- with its wording;
 *   - §4 ROUTING: every family row, an arbitrary linked id NOT inheriting the
 *     chosen node's kind, an unplaced Turn, acquired material, substrate
 *     taking precedence over the how/that fallback, and deletion not changing
 *     the family;
 *   - what is resolved and what is not: the graph's own settled read first,
 *     then the entry itself, and a Turn's Conversation only from the act that
 *     recorded THAT turn.
 *
 * What is NOT checked here (it needs a browser, and Part A's session): the
 * canvas, the camera's exact restoration, visibility pausing in fact, the
 * container sizing of the floating parts, focus moving into a restored
 * reader, and the drag actually landing in a composer. Those are the
 * integrated candidate's browser checks. */
import assert from 'node:assert/strict'
import { plan } from '../src/quiet2/centreHistory'
import { forgetUnfinished, leaving, tell, unfinished } from '../src/quiet2/leaving'
import {
  SESSION_CALLS, type SpaceCamera, type SpaceNode, type SpaceRead, type SpaceSession,
  type SpaceSnapshot,
} from '../src/quiet2/space/contract'
import {
  CLOSED_NOTICE, afterClose, graphIntent, inspectIntent, isSpaceHistory, resumeSpace,
  type SpaceDestination,
} from '../src/quiet2/space/history'
import {
  affectedPlaces, graphVisible, parkedFrom, restoreTo, restoresReceded,
  type ColumnRoom,
} from '../src/quiet2/space/placement'
import { forgetSpaceSessions, provideSpaceSessions } from '../src/quiet2/space/provider'
import {
  forgetSessions, invalidateOtherBrains, isClosedSession, liveSessions, nextSpaceSessionId,
  openSession, releaseAllSessions, releaseSession, sessionById, sessionOfBrain, spaceBrainKey,
} from '../src/quiet2/space/registry'
import {
  answers, entryFactsPath, factsFrom, factsInRead, knownOf, resolveEntryFacts,
  type EntryFacts,
} from '../src/quiet2/space/resolve'
import { CLIENT_HEADERS, read as readJson } from '../src/api'
import { SUBSTRATE, destinationWords, isAdmission, routeNode } from '../src/quiet2/space/routing'
import { postSource, type ViewerSource } from '../src/quiet2/viewer/types'
import {
  closeViewer, inColumn, maximised, moveViewer, openViewer, parkViewer, parkedPlaceOf, parkedViewers,
  returnViewer, settleColumns, shownViewer, spaceViewer, titleOf, viewerOf,
} from '../src/quiet2/viewer/viewers'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

/* -- a session that does nothing but answer the contract ------------------- */

const CAMERA: SpaceCamera = { initialized: false, framing: 'auto', zoomed: false, eye: { turn: 0.6, rise: 0.42, out: 10, at: { x: 0, y: 0, z: 0 } }, walk: [], selectionRevision: 0 }
const SNAP: SpaceSnapshot = {
  view: { selected: null, material: false, palette: 'none', allStrands: false, turns: true, options: false, asOf: null, playing: false },
  read: { key: 'records', data: null, loading: true, error: null },
  visible: false, disposed: false,
}

interface Fake extends SpaceSession { disposals: number; visibility: boolean[] }
const fakes: Fake[] = []
function fakeSession(input: { id: string; brainKey: string }): Fake {
  const f: Fake = {
    id: input.id, brainKey: input.brainKey, disposals: 0, visibility: [],
    getSnapshot: () => SNAP,
    subscribe: () => () => {},
    getCamera: () => CAMERA,
    saveCamera: () => {},
    setView: () => {},
    select: () => {},
    setVisible: (v) => { f.visibility.push(v) },
    attachRenderer: () => () => {},
    dispose: () => { f.disposals++ },
  }
  fakes.push(f)
  return f
}
const wire = () => provideSpaceSessions({ createSpaceSession: fakeSession, SpaceSessionReader: (() => null) as never })
const clean = () => { forgetSessions(); forgetSpaceSessions(); fakes.length = 0 }

/* -- §1 the contract Quiet Chat was built against -------------------------- */
{
  const s: SpaceSession = fakeSession({ id: 'sp0', brainKey: 'k' })
  for (const call of SESSION_CALLS) {
    ok(typeof (s as unknown as Record<string, unknown>)[call] === 'function', `the contract's ${call} is what Quiet Chat calls`)
  }
  eq(SESSION_CALLS.length, 9, 'the whole session contract, and nothing invented beside it')
  eq(s.getSnapshot().read.key, 'records', 'a read is one of the two material keys')
  fakes.length = 0
}

/* -- §1 which Brain a graph belongs to ------------------------------------- */
{
  eq(spaceBrainKey({ corpusId: null, origin: 'http://127.0.0.1:8780' }), null,
    'an identity not read yet is not a key: nothing is opened against a guessed Brain')
  eq(spaceBrainKey({ corpusId: '   ', origin: 'http://127.0.0.1:8780' }), null, 'an empty identity is no identity')
  const a = spaceBrainKey({ corpusId: 'c1', origin: 'http://127.0.0.1:8780' })
  const b = spaceBrainKey({ corpusId: 'c2', origin: 'http://127.0.0.1:8780' })
  const sameBrainOtherServer = spaceBrainKey({ corpusId: 'c1', origin: 'http://127.0.0.1:8781' })
  const proxied = spaceBrainKey({ corpusId: 'c1', origin: 'http://127.0.0.1:8780', proxy: 'dayday' })
  ok(a && b && sameBrainOtherServer && proxied, 'a read identity is a key')
  ok(a !== b, 'two corpora are two keys')
  ok(a !== sameBrainOtherServer, 'the same corpus on another server is another key')
  ok(a !== proxied, 'the pinned proxy Brain is part of the key')
  eq(a, spaceBrainKey({ corpusId: 'c1', origin: 'http://127.0.0.1:8780' }), 'the same Brain is the same key')
}

/* -- §1 the registry: one graph per Brain, one release path ---------------- */
{
  clean()
  eq(openSession('k1'), null, 'with no graph module wired in, nothing is created rather than stood in for')
  wire()
  const first = openSession('k1')!
  ok(first, 'the first explicit Open creates the one session for this Brain')
  eq(openSession('k1'), first, 'opening again is the SAME session: no second graph, no second read')
  eq(liveSessions().length, 1, 'one live graph per resolved Brain')
  const other = openSession('k2')!
  ok(other.id !== first.id, 'another Brain is another session, with its own id')
  eq(sessionOfBrain('k1'), first, 'a Brain finds its own graph')

  /* ONE RELEASE PATH, and disposal exactly once */
  releaseSession(first.id)
  eq((first as Fake).disposals, 1, 'the release path disposes it once')
  releaseSession(first.id)
  eq((first as Fake).disposals, 1, 'releasing an id already released disposes nothing twice')
  eq(sessionById(first.id), null, 'it is gone from the registry')
  ok(isClosedSession(first.id), 'and its id is expired for this page: an old entry cannot attach')
  const again = openSession('k1')!
  ok(again.id !== first.id, 'a fresh Open is a fresh id, never a reused one')

  /* A BRAIN CHANGE takes every other Brain's graph with it */
  invalidateOtherBrains('k1')
  eq(sessionById(other.id), null, 'a graph of another Brain is disposed when the page serves this one')
  eq((other as Fake).disposals, 1, 'disposed once')
  /* THE PAGE GOING: nothing survives it */
  releaseAllSessions()
  eq(liveSessions().length, 0, 'the owner unmounting leaves no session')
  const idA = nextSpaceSessionId(); const idB = nextSpaceSessionId()
  ok(idA !== idB, 'ids are never reused within a page')
  clean()
}

/* -- §1 the source union: the Brain has no post --------------------------- */
{
  const post: ViewerSource = { kind: 'post', conversation: 'c1', post: 'ent-1' }
  const brain: ViewerSource = { kind: 'brain', brainKey: 'k1' }
  eq(postSource(post), post, 'a post source is the post it came from')
  eq(postSource(brain), null, 'the Brain itself has no post, and none is invented for it')
  eq(titleOf({ kind: 'brain-space' }), '3D Brain', 'the graph is called what the reader calls it')
}

/* -- §3 parking: open, holding its view, shown nowhere --------------------- */
{
  clean(); wire()
  const s = openSession('k1')!
  const id = openViewer({ kind: 'brain-space' }, { kind: 'brain', brainKey: 'k1' }, 's1', { sessionId: s.id })
  eq(spaceViewer()?.id, id, 'the page has one graph, and finds it')
  eq(inColumn('s1')?.id, id, 'shown in a column, it is in that column')
  parkViewer(id)
  const v = viewerOf(id)!
  eq(v.place, 'parked', 'parked')
  eq(v.state, { sessionId: s.id }, 'its frame state -- the session id, and nothing else -- is untouched')
  eq(shownViewer(v), false, 'parked is not shown')
  eq(inColumn('s1'), null, 'it holds no column while parked')
  eq(maximised(), null, 'and reserves no maximised place')
  eq(parkedPlaceOf(id), { place: 's1', from: null }, 'where it was is remembered, so it can ask for it back')
  eq(parkedViewers().length, 1, 'it is still open')

  /* COLUMN SETTLEMENT HAS NOTHING TO RELEASE */
  eq(settleColumns([]), 0, 'a column closing does not touch a parked graph')
  eq(viewerOf(id)?.place, 'parked', 'it is still parked, still open, still the same session')

  /* A MOVE IS FOR ONE THAT IS SHOWN */
  moveViewer(id, 's2')
  eq(viewerOf(id)?.place, 'parked', 'a parked graph comes back through the page, not through a move')
  returnViewer(id, 's1', null)
  eq(viewerOf(id)?.place, 's1', 'back where it was, the same viewer')
  eq(viewerOf(id)?.id, id, 'and the same id across park and return')
  eq(viewerOf(id)?.parkedFrom, undefined, 'it no longer remembers being parked')
  clean(); closeViewer(id)
}

/* -- §3 a generic path never closes the graph ------------------------------ */
{
  clean(); wire()
  const s = openSession('k1')!
  const graph = openViewer({ kind: 'brain-space' }, { kind: 'brain', brainKey: 'k1' }, 'max', { sessionId: s.id })
  /* ANOTHER VIEWER TAKES MAX: the graph has no column to fall back to, and is
     parked rather than closed -- its session, and the reader's view, survive */
  const block = { kind: 'block', post: 'ent-2', block: 0, element: 0, label: 'Table' } as const
  const other1 = openViewer(block, { kind: 'post', post: 'ent-2' }, 'max')
  eq(viewerOf(graph)?.place, 'parked', 'displaced from max with nowhere to go, the graph parks')
  eq((s as Fake).disposals, 0, 'and nothing of it is disposed')
  eq(maximised()?.id, other1, 'the viewer that asked for max has it')
  closeViewer(other1)

  /* A COLUMN THAT CLOSES while another viewer is maximised: the graph parks */
  returnViewer(graph, 's2', null)
  const other = openViewer(block, { kind: 'post', post: 'ent-3' }, 'max')
  eq(settleColumns(['s1']), 1, 'the column it was in is no longer shown')
  eq(viewerOf(graph)?.place, 'parked', 'with max taken, it parks instead of closing')
  eq((s as Fake).disposals, 0, 'still not disposed: only the release path disposes')
  closeViewer(other); closeViewer(graph); clean()
}

/* -- §3 where a parked graph comes back to -------------------------------- */
{
  const room = (shown: ('s1' | 's2')[], busy: ('s1' | 's2')[] = []): ColumnRoom =>
    ({ shown, free: (s) => shown.includes(s) && !busy.includes(s) })
  eq(restoreTo({ place: 's1', from: null }, room(['s1', 's2'])), { place: 's1', from: null },
    'its own column, while it is still shown and free')
  eq(restoreTo({ place: 's1', from: null }, room(['s1', 's2'], ['s1'])), { place: 's2', from: null },
    'an old column that filled up while it was parked is not overwritten: another free one takes it')
  eq(restoreTo({ place: 's1', from: null }, room(['s1'], ['s1'])), { place: 'max', from: null },
    'with no free column it comes back maximised')
  eq(restoreTo({ place: 's2', from: null }, room(['s1'])), { place: 's1', from: null },
    'a column no longer shown gives way to one that is')
  eq(restoreTo({ place: 'max', from: 's1' }, room(['s1', 's2'])), { place: 'max', from: 's1' },
    'maximised comes back maximised, keeping the column Restore returns it to')
  eq(restoreTo({ place: 'max', from: 's1' }, room(['s1', 's2'], ['s1'])), { place: 'max', from: null },
    'but a stale `from` is dropped rather than pointing at occupied content')
  eq(restoreTo({ place: 'max', from: null }, room([])), { place: 'max', from: null },
    'max without a `from` stays max without one')
  eq(parkedFrom({ place: 's1', from: 's2' }), { place: 's1', from: null },
    'a column viewer parks with no maximised reservation')
  eq(parkedFrom({ place: 'max', from: 's2' }), { place: 'max', from: 's2' },
    'a maximised one parks remembering the column it left')
}

/* -- §3 what a transition displaces, and so what is asked about ----------- */
{
  const room: ColumnRoom = { shown: ['s1', 's2'], free: (s) => s === 's2' }
  eq(affectedPlaces({ what: 'place', into: 's1' }, room), ['s1'],
    'opening into an occupied column asks about that column')
  eq(affectedPlaces({ what: 'place', into: 's2' }, room), [],
    'an empty column loses nothing, so nothing is asked')
  eq(affectedPlaces({ what: 'place', into: 'max' }, room), [],
    'maximising covers the page; it takes nothing away')
  eq(affectedPlaces({ what: 'inspect' }, room), ['centre'],
    'reading a chosen thing takes the centre reading column')
  eq(affectedPlaces({ what: 'close' }, room), [],
    'the graph’s own close discards the graph, which the guard does not speak for')
  eq(affectedPlaces({ what: 'elsewhere', into: 'centre' }, room), ['centre'],
    'going elsewhere in the centre asks about the centre')

  /* AND THE QUESTION IS THE EXISTING ONE: a half-written record in the centre
     is asked about before a chosen thing replaces it, and a Stay loses
     nothing because nothing has moved yet. */
  forgetUnfinished()
  const stop = tell(() => ({ what: 'this new rule', dirty: true, lost: 'nothing of it is in the Brain.' }), 'centre')
  const asked = leaving(unfinished('centre'))
  ok(asked.ask, 'the centre holding unsaved words is asked about before the graph sends a reader there')
  eq(asked.ask!.title, 'Leave this new rule unfinished?', 'in the page’s own words')
  eq(leaving(unfinished('s1')), { ask: null, note: null }, 'and only that place is asked about')
  stop(); forgetUnfinished()
}

/* -- §1 when the canvas is actually visible ------------------------------- */
{
  eq(graphVisible({ drawn: true, inertHost: false, documentVisible: true }), true, 'drawn, not inert, shown: visible')
  eq(graphVisible({ drawn: false, inertHost: false, documentVisible: true }), false, 'parked or unmounted: not visible')
  eq(graphVisible({ drawn: true, inertHost: true, documentVisible: true }), false,
    'in a column behind a maximised viewer the host is inert: not visible, so the canvas pauses')
  eq(graphVisible({ drawn: true, inertHost: false, documentVisible: false }), false,
    'a hidden browser tab: not visible')
  eq(restoresReceded({ was: true, atRevision: 3 }, 3), true,
    'a conversation brought back to show a reader is put back as it was')
  eq(restoresReceded({ was: true, atRevision: 3 }, 4), false,
    'unless the reader has changed the layout themselves since: their word is last')
}

/* -- §3 the entries, and finding the graph again rather than pushing it ---- */
{
  const g = graphIntent('k1', 'sp1')
  const i = inspectIntent('k1', 'sp1', { kind: 'record', entry: 'ent-9' })
  ok(isSpaceHistory(g) && isSpaceHistory(i), 'both are graph entries of the centre')
  eq(isSpaceHistory({ brain: { stack: [], origin: { from: 'link' } } }), false, 'an ordinary record entry is not')
  eq(g, { space: { brainKey: 'k1', sessionId: 'sp1', phase: 'graph' } }, 'a graph entry is intent: the Brain and the session')
  eq(i.space.phase === 'inspect' && i.space.target, { kind: 'record', entry: 'ent-9' },
    'an inspect entry carries what is being read, not a copy of it')
  /* THE SAME GRAPH ENTRY IS THE SAME DATA, so the existing history search
     walks BACK to it instead of growing a second graph entry. */
  eq(graphIntent('k1', 'sp1'), g, 'built the same way every time it is reached')
  const trail = [null, g, i]
  eq(plan(trail, 2, g), -1, 'in-page Back to 3D Brain goes back one entry, to the graph')
  eq(plan(trail, 2, i), 0, 'and asking for where you already are moves nothing')
  eq(plan(trail, 2, graphIntent('k1', 'sp2')), null, 'another session is not behind: it would be pushed')
  eq(plan([null, g], 1, null), -1, 'the conversation is still behind the graph')
}

/* -- §3 nothing is ever resurrected --------------------------------------- */
{
  const liveOne = (id: string) => id === 'sp1'
  eq(resumeSpace(graphIntent('k1', 'sp1'), { brainKey: 'k1', live: liveOne }),
    { how: 'live', space: { brainKey: 'k1', sessionId: 'sp1', phase: 'graph' } },
    'the extant session of this Brain is restored, never recreated')
  eq(resumeSpace(graphIntent('k1', 'sp2'), { brainKey: 'k1', live: liveOne }),
    { how: 'expired-graph', notice: CLOSED_NOTICE },
    'a closed or reloaded graph entry becomes the ordinary centre, and says so')
  eq(CLOSED_NOTICE, '3D Brain view was closed. Open a new view.', 'in the words the addendum fixes')
  const target: SpaceDestination = { kind: 'post', conversation: 'c1', post: 'ent-7' }
  eq(resumeSpace(inspectIntent('k1', 'sp2', target), { brainKey: 'k1', live: liveOne }),
    { how: 'expired-inspect', target },
    'an expired inspect entry may still show its target, as an ordinary reader')
  eq(resumeSpace(inspectIntent('k9', 'sp1', target), { brainKey: 'k1', live: liveOne }),
    { how: 'other-brain' },
    'an entry made against another Brain is not replayed at all')
  eq(resumeSpace(graphIntent('k1', 'sp1'), { brainKey: null, live: liveOne }),
    { how: 'other-brain' },
    'and an identity not known yet never matches')
  eq(afterClose(graphIntent('k1', 'sp1')), { replaceWith: null },
    'closing the graph leaves the ordinary centre in its entry')
  eq(afterClose(inspectIntent('k1', 'sp1', target)), { replaceWith: target },
    'closing it while a reader is up leaves the reader, with the graph origin gone')
}

/* -- §4 where each family is read ----------------------------------------- */
{
  const to = (f: Parameters<typeof routeNode>[0]) => {
    const r = routeNode(f)
    return r.how === 'go' ? r.to : r
  }
  eq(to({ entry: 'ent-c', kind: 'conversation', layer: 'place' }), { kind: 'conversation', conversation: 'ent-c' },
    'a Conversation is the conversation itself')
  eq(to({ entry: 'ent-t', kind: 'contribution', layer: 'said', conversation: 'ent-c' }),
    { kind: 'post', conversation: 'ent-c', post: 'ent-t' },
    'a Turn is the post, in the Conversation the record declares')
  eq(to({ entry: 'ent-r', kind: 'rule', layer: 'how' }), { kind: 'record', entry: 'ent-r' },
    'what directs work is Manage Brain’s own record presentation')
  eq(to({ entry: 'ent-l', kind: 'lesson', layer: 'that' }), { kind: 'record', entry: 'ent-l' },
    'and so is what is known')
  eq(to({ entry: 'ent-tp', kind: 'topic', layer: 'place' }), { kind: 'entry', entry: 'ent-tp' },
    'a Topic is read by the read-only inspector: no new dashboard')
  eq(to({ entry: 'ent-p', kind: 'participant', layer: 'who' }), { kind: 'entry', entry: 'ent-p' },
    'and a Participant likewise')
  eq(to({ entry: 'adm-abc123', kind: 'note', layer: 'material' }), { kind: 'entry', entry: 'adm-abc123' },
    'acquired material is read by the inspector, with its held bytes: no post is invented')
  ok(isAdmission('adm-41ecec0c74c0') && !isAdmission('ent-41ecec0c74c0'), 'an admission is known by its address')
  eq(to({ entry: 'ent-x', kind: 'something-new', layer: 'other' }), { kind: 'entry', entry: 'ent-x' },
    'an unknown Kind that declares no knowing is read honestly, not as governance')

  /* SUBSTRATE TAKES PRECEDENCE over the how/that fallback */
  for (const kind of ['anchor', 'reaction', 'observation']) {
    eq(to({ entry: 'ent-s', kind, layer: 'how' }), { kind: 'entry', entry: 'ent-s' },
      `${kind} is substrate: the inspector reads it even where its layer suggests a record`)
  }
  ok(SUBSTRATE.has('deletion') && SUBSTRATE.has('timer-mark'), 'and the rest of the substrate with them')

  /* AN UNPLACED TURN: asked about once, then read as an entry -- never a
     guessed root or post */
  eq(routeNode({ entry: 'ent-t2', kind: 'contribution', layer: 'said', conversation: null }),
    { how: 'resolve', entry: 'ent-t2', want: 'conversation' },
    'a Turn the graph did not place has its own metadata read first')
  eq(to({ entry: 'ent-t2', kind: 'contribution', conversation: null, resolved: true }),
    { kind: 'entry', entry: 'ent-t2' },
    'and one the record places nowhere is read as an entry, with no root invented')

  /* A LINK CARRIES AN ID, NOT A KIND */
  eq(routeNode({ entry: 'ent-unknown' }), { how: 'resolve', entry: 'ent-unknown', want: 'kind' },
    'an arbitrary linked id is resolved: it never inherits the chosen node’s kind')
  eq(to({ entry: 'ent-unknown', resolved: true }), { kind: 'entry', entry: 'ent-unknown' },
    'and one nothing can say anything about is read read-only, not as a record')
  eq(to({ entry: 'adm-ff00', resolved: false }), { kind: 'entry', entry: 'adm-ff00' },
    'material needs no read at all: its address says what it is')

  /* DELETION AND REPLACEMENT DO NOT CHANGE THE FAMILY: its own reader has the
     tombstone and version behaviour, and keeps it. */
  eq(to({ entry: 'ent-d', kind: 'rule', layer: 'how' }), { kind: 'record', entry: 'ent-d' },
    'a deleted record is still read by the record reader, which has its tombstone')
  eq(destinationWords({ kind: 'record', entry: 'e' }), 'Brain record', 'each destination is named for the reader')
  eq(destinationWords({ kind: 'post', conversation: 'c', post: 'p' }), 'Turn', 'a contribution is a turn, in the record’s own word')
}

/* -- §4 what is resolved, and from where ---------------------------------- */
{
  const read = {
    nodes: [{ entry: 'ent-1', kind: 'contribution', layer: 'said', conversation: 'ent-c', at: 1, summary: null, deleted: false, edited: false, replaced: false }],
    edges: [], conversations: {}, layers: [], total: 1, omitted: 0, cap: 6000, material: false,
  }
  eq(factsInRead('ent-1', read), { entry: 'ent-1', kind: 'contribution', layer: 'said', conversation: 'ent-c' },
    'the graph’s own settled read already states what a thing is: nothing is fetched for it')
  eq(factsInRead('ent-2', read), null, 'something the graph did not return is not in it')
  eq(factsInRead('ent-1', null), null, 'and with no read yet, nothing is claimed')

  eq(factsFrom('ent-2', null), { entry: 'ent-2', resolved: true },
    'a read that failed leaves the honest fallback, not a guess')
  eq(factsFrom('ent-2', { missing: true }), { entry: 'ent-2', resolved: true }, 'a missing entry likewise')
  eq(factsFrom('ent-2', { kind: 'rule' }), { entry: 'ent-2', kind: 'rule', layer: null, conversation: null, resolved: true },
    'the record says what kind it is')
  eq(factsFrom('ent-t', { kind: 'contribution', provenance: { produced_by: [{ conversation: 'ent-c', turn: 'ent-t' }] } }),
    { entry: 'ent-t', kind: 'contribution', layer: null, conversation: 'ent-c', resolved: true },
    'a Turn’s Conversation comes from the act that recorded THAT turn')
  eq(factsFrom('ent-t', { kind: 'contribution', provenance: { produced_by: [{ conversation: 'ent-c', turn: 'ent-other' }] } }),
    { entry: 'ent-t', kind: 'contribution', layer: null, conversation: null, resolved: true },
    'and never from an act that recorded something else: a nearby Conversation is not a placement')
}

/* -- §4 WHAT THE GRAPH'S READ DOES NOT ANSWER (B-1b) ----------------------- *
 * The graph's settled read holding a thing is not the same as its answering
 * the question asked about it. A Turn it returned with no Conversation is
 * still unplaced as far as the dispatcher knows, and the record itself must be
 * read before the read-only inspector is settled for. */
{
  const turn = (conversation: string | null): SpaceNode => ({
    entry: 'ent-1', kind: 'contribution', layer: 'said', conversation,
    at: 1, summary: null, deleted: false, edited: false, replaced: false,
  })
  const readOf = (...nodes: SpaceNode[]): SpaceRead =>
    ({ nodes, edges: [], conversations: {}, layers: [], total: nodes.length, omitted: 0, cap: 6000, material: false })

  const placed = readOf(turn('ent-c'))
  const unplaced = readOf(turn(null))

  /* THE QUESTION IS ASKED AT ALL: a Turn the graph did not place */
  eq(routeNode({ entry: 'ent-1', kind: 'contribution', layer: 'said', conversation: null }),
    { how: 'resolve', entry: 'ent-1', want: 'conversation' },
    'a Turn with no Conversation has its own metadata read first')

  /* ANSWERED BY THE GRAPH: nothing is read */
  ok(answers('conversation', knownOf({ entry: 'ent-1' }, placed)),
    'where the graph DID place it, the graph has already answered: no read')
  eq(knownOf({ entry: 'ent-1' }, placed),
    { entry: 'ent-1', kind: 'contribution', layer: 'said', conversation: 'ent-c' },
    'and what it says is taken as it stands')

  /* NOT ANSWERED BY THE GRAPH: the record is read before the fallback */
  eq(answers('conversation', knownOf({ entry: 'ent-1' }, unplaced)), false,
    'the graph holding the Turn but NOT its Conversation does not answer: the record is read')
  eq(knownOf({ entry: 'ent-1' }, unplaced),
    { entry: 'ent-1', kind: 'contribution', layer: 'said', conversation: null },
    'what the graph does know is still kept, and nothing is marked resolved')
  eq(routeNode(knownOf({ entry: 'ent-1' }, unplaced)),
    { how: 'resolve', entry: 'ent-1', want: 'conversation' },
    'so the dispatcher asks again rather than opening the entry inspector')
  ok(answers('kind', knownOf({ entry: 'ent-1' }, unplaced)),
    'the kind it DOES state is answered: a bare link id is not read twice for it')

  /* NOT IN THE READ AT ALL, and the link carrying nothing */
  eq(knownOf({ entry: 'ent-9' }, placed), { entry: 'ent-9' }, 'something the graph did not return adds nothing')
  eq(answers('kind', { entry: 'ent-9' }), false, 'and nothing is claimed about it')

  /* NOTHING ALREADY KNOWN IS OVERWRITTEN by the graph's summary */
  eq(knownOf({ entry: 'ent-1', kind: 'rule', layer: 'how', conversation: 'ent-k' }, unplaced),
    { entry: 'ent-1', kind: 'rule', layer: 'how', conversation: 'ent-k' },
    'what the chosen node carried stands: the summary fills gaps, it does not correct')

  /* AND THE RECORD'S ANSWER PLACES IT: the honest fallback is only reached
     when the record itself places it nowhere */
  eq(routeNode(factsFrom('ent-1', { kind: 'contribution', provenance: { produced_by: [{ conversation: 'ent-c2', turn: 'ent-1' }] } })),
    { how: 'go', to: { kind: 'post', conversation: 'ent-c2', post: 'ent-1' } },
    'the record places it, so it opens as its Turn in its own Conversation')
  eq(routeNode(factsFrom('ent-1', { kind: 'contribution' })),
    { how: 'go', to: { kind: 'entry', entry: 'ent-1' } },
    'and only a record that places it nowhere settles for the read-only inspector')
}

/* -- §4 THE READ ITSELF: the page's own client (B-1) ----------------------- *
 * The server refuses every JSON route that does not say it is this interface
 * (mentis/web `_missing_client`: 403 `missing X-Mentis-Client`), and a refusal
 * is indistinguishable here from an id the Brain does not hold -- so a bare
 * `fetch` would silently open every out-of-read link in the wrong reader.
 * This checks the request the resolve read actually makes, through api.ts's
 * own `read`, against a stub of the browser's fetch. */
{
  interface Asked { path: string; headers: Record<string, string> }
  const asked: Asked[] = []
  let reply: { status: number; body: unknown } = { status: 200, body: {} }
  const was = globalThis.fetch
  globalThis.fetch = (async (input: unknown, init?: RequestInit) => {
    asked.push({ path: String(input), headers: { ...(init?.headers as Record<string, string> | undefined) } })
    return {
      ok: reply.status >= 200 && reply.status < 300,
      status: reply.status, statusText: String(reply.status),
      text: async () => JSON.stringify(reply.body),
    } as unknown as Response
  }) as typeof globalThis.fetch
  const client = (path: string) => readJson<EntryFacts>(path)

  eq(entryFactsPath('ent-1'), '/api/entries/ent-1', 'the entry read is addressed as EntryInspect addresses it')
  eq(entryFactsPath('ent/1 2'), '/api/entries/ent%2F1%202', 'and an id is escaped into the path')

  /* THE HEADER THE SERVER REQUIRES is on the request, and it is the one the
     rest of the page sends. This is the check that would have caught B-1. */
  reply = { status: 200, body: { kind: 'contribution', provenance: { produced_by: [{ conversation: 'ent-c', turn: 'ent-1' }] } } }
  const got = await resolveEntryFacts('ent-1', client)
  eq(asked.length, 1, 'one read, for the one id')
  eq(asked[0]!.path, '/api/entries/ent-1', 'of the entry itself')
  eq(asked[0]!.headers['X-Mentis-Client'], '1',
    'and it SAYS it is this interface: without that header the server answers 403, not the record')
  eq(asked[0]!.headers, { ...CLIENT_HEADERS }, 'exactly what every other read of this page sends')
  eq(got, { entry: 'ent-1', kind: 'contribution', layer: null, conversation: 'ent-c', resolved: true },
    'so the record answers, and the Turn is placed where the record places it')
  eq(routeNode(got), { how: 'go', to: { kind: 'post', conversation: 'ent-c', post: 'ent-1' } },
    'and it opens as its Turn: the §4 family, not the read-only fallback')

  /* AN ENTRY THE BRAIN DOES NOT HOLD: the honest fallback */
  asked.length = 0
  reply = { status: 200, body: { id: 'ent-2', missing: true } }
  eq(await resolveEntryFacts('ent-2', client), { entry: 'ent-2', resolved: true },
    'a missing entry resolves to nothing claimed')

  /* A REFUSAL OR A FAILURE IS NOT A VERDICT: the same honest fallback, and
     nothing thrown at the dispatcher. The reader it opens shows its own
     error, read with its own client. */
  asked.length = 0
  reply = { status: 403, body: { error: 'missing X-Mentis-Client', kind: 'PermissionError' } }
  eq(await resolveEntryFacts('ent-3', client), { entry: 'ent-3', resolved: true },
    'a refused read leaves the honest fallback rather than a guess or a crash')
  eq(asked.length, 1, 'and it was tried exactly once')
  reply = { status: 500, body: { error: 'nope' } }
  eq(await resolveEntryFacts('ent-4', client), { entry: 'ent-4', resolved: true }, 'a failed read likewise')
  await resolveEntryFacts('ent-5', () => Promise.reject(new Error('offline')))
    .then((f) => eq(f, { entry: 'ent-5', resolved: true }, 'and a client that cannot reach the server at all'))

  globalThis.fetch = was
}

console.log(`quiet_space_nav_unit: ${checks} checks passed`)
