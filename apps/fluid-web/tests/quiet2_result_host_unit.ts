/* MOUNTING THE RESULT OPENER: the host's own moves, checked without a browser
 * (src/quiet2/results/hostOpen.ts).
 *
 * EVERY ROW HERE IS ONE OF THE INDEPENDENT REVIEW'S FALSIFIERS
 * (adm-f3244dbc4bae). The review's five failing probes are reproduced first,
 * each against the code the hand-off now tells the integrator to call rather
 * than against a snippet in prose:
 *
 *   B1   the exact Admission survives the file adapter (`R1`), and a file with
 *        no source post opens without asking a post for its pictures (`R1b`)
 *   B2   the caller's launch reaches the viewer (`R2`, in the opener suite),
 *        and a second open does not take the first viewer's way back (`R3`)
 *   B3   a navigation that has only begun is not a departure (`R4`, in the
 *        opener suite), and the dock waits for the answer
 *   B4   closing, going to source, landing on an entry again and restoring a
 *        Place are decisions with answers, not prose
 *
 * The fixtures are synthetic: no Brain, no server, no DOM, no bytes. */
import assert from 'node:assert/strict'
import {
  closeSteps, dockStep, fileContent, pressed, restoreSteps, resultViewers, resumeSteps, siblingsOf, sourceSteps,
} from '../src/quiet2/results/hostOpen'
import {
  beginOpening, clearLaunches, historyOf, holdLaunch, isPlaced, launchOf, restoreOf,
  type LaunchContext, type LaunchPlace,
} from '../src/quiet2/results/launch'
import { resumeResult, resultIntent, type Shown } from '../src/quiet2/results/history'
import type { FileOpen, Opened } from '../src/quiet2/results/opener'
import type { HeldBytes, ViewerItem } from '../src/quiet/media/view'
import type { ViewImage } from '../src/quiet2/viewer/types'
import { heldItem } from '../src/quiet2/brain/logic'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const no = (a: unknown, what: string) => { assert.ok(!a, what); checks++ }

const BRAIN = 'fixture-corpus@instance-1'
const REF = 'adm-123456789abc'
const PLACE: LaunchPlace = { conversation: 'ent-111111111111', centre: null }
const ELSEWHERE: LaunchPlace = { conversation: 'ent-999999999999', centre: null }

const launch = (over: Partial<LaunchContext> = {}): LaunchContext => holdLaunch({
  opening: beginOpening(), brainKey: BRAIN, place: PLACE, thread: null,
  reading: { scroll: 417, offset: 12 }, reply: 'ent-222222222222', draft: 'conversation:ent-111111111111',
  focus: { control: 'needs-ref:' + REF, fallback: { kind: 'conversation' } }, ...over,
})

/** the existing inspector shape: metadata, no item and no URL */
const held: HeldBytes = { ref: REF, state: 'held', name: 'notes.md', size: 18, claimed_media_type: 'text/markdown' }
const open = (over: Partial<FileOpen> = {}): FileOpen => ({
  ref: REF, item: null, file: held, source: { kind: 'brain', brainKey: BRAIN },
  /* THE RESULT'S OWN IDENTITY, which the opener carries from the destination
     and the host writes into the history entry (re-review F12) */
  target: { kind: 'artifact', ref: REF }, launch: launch(), settled: () => {}, ...over,
})
/** the page's own reader, exactly as `brain/logic.ts` gives it */
const page = { item: (ref: string, about: HeldBytes | null) => heldItem(ref, about) }

/* -- B1: the exact Admission, and no post that is not there ----------------- */
{
  clearLaunches()
  /* R1: the hand-off's old fallback was `heldItem('', file)`, which built the
     item's identity and its artifact address from an empty string. */
  const r = fileContent(open(), page)
  ok(!('why' in r), 'an ordinary held file opens')
  const content = 'why' in r ? null : r.content
  const item = content && content.kind === 'file' ? content.item : null
  eq(item?.ref, REF, 'THE EXACT ADMISSION THAT WAS ASKED FOR reaches the viewer (R1)')
  eq(item?.url, '/api/artifacts/' + REF, 'and its bytes are read at that address, not at /api/artifacts/')
  eq(fileContent(open({ ref: '', file: { ...held, ref: REF } }), page).hasOwnProperty('why'), false,
    'a descriptor that carries the identity is read under it, rather than under nothing')
  eq(fileContent(open({ ref: '', file: { ...held, ref: '' } }), page), { why: 'That file has no reference to read: nothing was opened.' },
    'and with no reference anywhere, nothing is opened and it is said')
  const itemFirst = heldItem(REF, held)!
  const carried = fileContent(open({ ref: '', item: itemFirst }), page)
  ok(!('why' in carried), 'an item the caller already read is used as it is')
  eq(fileContent(open({ item: { ...itemFirst, ref: 'adm-ffffffffffff' } }), page).hasOwnProperty('why'), true,
    'an item for another Admission is refused rather than drawn under this reference')
  eq(fileContent(open({ file: { ...held, state: 'not-held' } }), page),
    { why: 'Those contents could not be opened: Mentis does not hold them.' }, 'and bytes Mentis does not hold say so')
}
{
  /* R1b: `picturesOf(postOf(...) ?? undefined)` reads `post.blocks` straight
     away, so the old adapter threw a TypeError for every file whose source is
     not a post this page has drawn -- a Brain-sourced artifact, an unplaced
     return, a post not read yet. The post is asked for first now. */
  const threw = { item: page.item, post: () => null, pictures: () => { throw new Error('picturesOf was called with no post') } }
  const brainSourced = fileContent(open(), threw)
  ok(!('why' in brainSourced), 'a Brain-sourced artifact opens with no post at all (R1b)')
  eq(siblingsOf({ kind: 'brain', brainKey: BRAIN }, threw), undefined, 'and is never asked for a post’s pictures')
  eq(siblingsOf({ kind: 'post', conversation: 'ent-c', post: 'ent-88' }, threw), undefined,
    'nor is a post this page has not drawn: `postOf` answers nothing for it')
  const PICTURES: ViewImage[] = [{ url: '/api/artifacts/adm-1', name: 'a.png', alt: 'a' }]
  const drawn = { item: page.item, post: (p: string) => (p === 'ent-88' ? { post: p } : null), pictures: () => PICTURES }
  eq(siblingsOf({ kind: 'post', conversation: 'ent-c', post: 'ent-88' }, drawn), PICTURES,
    'a post that IS drawn still opens its picture in its own collection')
  const picture: ViewerItem = { url: '/api/artifacts/adm-1', ref: 'adm-1', name: 'a.png', alt: 'a', kind: 'image', mediaType: 'image/png', size: 12 }
  const gallery = fileContent({ ...open({ item: picture, ref: 'adm-1' }), source: { kind: 'post', conversation: 'ent-c', post: 'ent-88' } }, drawn)
  eq('why' in gallery ? null : gallery.content.kind, 'gallery', 'which is what the collection viewer needs')
}

/* -- B2: every placed viewer keeps its own way back ------------------------- */
{
  clearLaunches()
  const viewers = resultViewers(launchOf)
  const first = launch()
  const mark = historyOf(first)
  viewers.place('v1', first, { kind: 'artifact', ref: REF }, 's1')
  ok(isPlaced(first.opening), 'a successful placement registers its launch')
  /* R3: the second open used to delete the first launch, so the first side
     viewer could only ever return to a Place -- as if the page had reloaded. */
  const second = launch()
  viewers.place('v2', second, { kind: 'artifact', ref: 'adm-2' }, 's2')
  eq(restoreOf(mark, { brainKey: BRAIN, launch: launchOf }).how, 'live',
    'OPENING A SECOND VIEWER LEAVES THE FIRST ITS LIVE RETURN (R3): two results open beside a conversation return to their own rows')
  eq(viewers.launchOf('v1')?.opening, first.opening, 'each viewer knows its own launch')
  eq(viewers.viewerOf(second.opening), 'v2', 'and each opening its own viewer')
  eq(viewers.whereOf('v2'), 's2', 'with where it actually went')
  viewers.moved('v2', 'max')
  eq(viewers.whereOf('v2'), 'max', 'kept as it moves')
  /* and closing IS what releases it */
  const gone = viewers.forget('v1')
  eq(gone?.opening, first.opening, 'closing hands back the launch for the close plan')
  no(launchOf(first.opening), 'and releases it')
  eq(restoreOf(mark, { brainKey: BRAIN, launch: launchOf }).how, 'place', 'after which only its Place is promised, honestly')
  eq(viewers.launchOf('v2')?.opening, second.opening, 'the viewer still open is untouched by the other’s close')
}

/* -- B3: what the dock does with each answer -------------------------------- */
{
  const arms: Opened[] = [{ what: 'opened', how: 'file', where: 's1' }, { what: 'opened', how: 'post', where: 'none' }]
  const waits: Opened[] = [{ what: 'leaving', how: 'post' }, { what: 'placing' }]
  const keeps: Opened[] = [
    { what: 'cancelled', why: 'x' }, { what: 'external', href: 'https://e.test/' },
    { what: 'identity', words: 'x' }, { what: 'unavailable', why: 'x' }, { what: 'refused', why: 'x' },
  ]
  for (const o of arms) eq(dockStep(o), 'arm', `a real open arms the way back: ${o.what}`)
  for (const o of waits) eq(dockStep(o), 'wait', `an open still happening arms nothing yet: ${o.what}`)
  for (const o of keeps) eq(dockStep(o), 'keep', `and nothing that did not open keeps the row, the form and the draft: ${o.what}`)
  ok(pressed({ what: 'leaving', how: 'post' }) && pressed({ what: 'external', href: 'https://e.test/' }), 'a press that did something, or is still doing it, is not a failure')
  no(pressed({ what: 'unavailable', why: 'x' }) || pressed({ what: 'refused', why: 'x' }), 'and one that could not be taken says so')
}

/* -- B4: closing is a sequence, and a cancelled one keeps the viewer -------- */
{
  clearLaunches()
  const l = launch()
  const plan = closeSteps({ viewer: 'v1', where: 'max', launch: l }, { owns: true, conversation: PLACE.conversation })
  eq(plan.history, { how: 'back', to: PLACE }, 'a maximised result gives up its entry through the centre’s own one step back')
  eq(plan.then.map((s) => s.do), ['restore', 'focus', 'forget'],
    'AND THE VIEWER IS GIVEN UP LAST (H7): these run in the history move’s `then`, which a reader who chooses Stay never reaches')
  eq(plan.bar, false, 'a close that walked the history owes no return bar')
  const side = closeSteps({ viewer: 'v2', where: 's1', launch: l }, { owns: false, conversation: PLACE.conversation })
  eq(side.history, null, 'a side column never walked the centre’s history, and never pops it (H1)')
  eq(side.then.map((s) => s.do), ['restore', 'focus', 'forget'], 'it restores and closes at once')
  const left = closeSteps({ viewer: 'v3', where: 'max', launch: l }, { owns: false, conversation: PLACE.conversation })
  eq(left.history, null, 'navigation has since left this entry: the history is left alone')
  ok(left.bar, 'and the explicit return bar is what still owes the reader their way back')
  const unknown = closeSteps({ viewer: 'v4', where: 'max', launch: null }, { owns: true, conversation: null })
  eq(unknown.then.map((s) => s.do), ['forget'], 'a viewer with no launch of ours is simply closed')
  /* B4.3: THE HISTORY MOVE IS TO A WHOLE PLACE, so the conversation it was
     opened in is not pressed a second time behind it -- one close, one
     question. A side close, which walks no history, still presses it. */
  const away = launch({ place: ELSEWHERE })
  const walked = closeSteps({ viewer: 'v5', where: 'max', launch: away }, { owns: true, conversation: PLACE.conversation })
  const restore = walked.then.find((s) => s.do === 'restore')
  eq(restore && restore.do === 'restore' && restore.place.map((p) => p.do), ['thread', 'reading', 'reply', 'draft'],
    'B4.3: a close that walked the history to the whole Place does not press that conversation again')
  const beside = closeSteps({ viewer: 'v6', where: 's1', launch: away }, { owns: false, conversation: PLACE.conversation })
  const asides = beside.then.find((s) => s.do === 'restore')
  eq(asides && asides.do === 'restore' && asides.place[0]?.do, 'conversation',
    'while a side close, which moved no history, asks for it itself (F15)')
  /* N3: an ordinary maximised picture keeps the baseline's return to its post */
  const ordinary = closeSteps({ viewer: 'v7', where: 'max', launch: null, source: { kind: 'post', conversation: 'ent-c', post: 'ent-88' } }, { owns: false, conversation: 'ent-c' })
  eq(ordinary.then.map((s) => s.do), ['forget', 'reveal'], 'N3: the frame closes and its own post is brought back into view')
  const sideOrdinary = closeSteps({ viewer: 'v8', where: 's1', launch: null, source: { kind: 'post', conversation: 'ent-c', post: 'ent-88' } }, { owns: false, conversation: 'ent-c' })
  eq(sideOrdinary.then.map((s) => s.do), ['forget'], 'N3: a column viewer never did that, and still does not')
  const focus = closeSteps({ viewer: 'v1', where: 'max', launch: l }, { owns: true, conversation: PLACE.conversation, invoker: { isConnected: true } })
  const choice = focus.then.find((s) => s.do === 'focus')
  eq(choice && choice.do === 'focus' && choice.choice, { how: 'invoker' }, 'focus returns to the control that was pressed, where it is still there (H6)')
}

/* -- B4: putting the reader back, conversation included --------------------- */
{
  clearLaunches()
  const here = launch()
  eq(restoreSteps(here, { conversation: 'ent-111111111111', appliedCentre: true }).map((s) => s.do), ['thread', 'reading', 'reply', 'draft'],
    'in the conversation it was opened in, the thread it was in, the reading offset, the reply target and the draft KEY come back')
  const away = launch({ place: ELSEWHERE, thread: { root: 'ent-root', at: 'ent-at' } })
  const steps = restoreSteps(away, { conversation: 'ent-111111111111' })
  eq(steps.map((s) => s.do), ['conversation', 'centre', 'thread', 'reading', 'reply', 'draft'],
    'A RESULT OPENED IN ANOTHER CONVERSATION RETURNS TO THAT CONVERSATION (B4): the centre’s own move keeps the one shown, so it is asked for first')
  eq(steps[0], { do: 'conversation', conversation: 'ent-999999999999' }, 'by its exact id')
  eq(steps.find((s) => s.do === 'thread'), { do: 'thread', root: 'ent-root', at: 'ent-at' }, 'into the thread it was opened in, at the reply it was reading')
  ok(!JSON.stringify(steps).includes('fixture-corpus'), 'nothing of the Brain key is replayed into the page')
  /* F3: AND THE ABSENCE OF A THREAD IS RESTORED TOO. A launch made in the
     conversation flow said nothing about the thread, so a reader who entered
     a thread after opening the result was left in that thread -- with its
     composer and its draft place -- by the control that promised to put them
     back. "No thread" is a step like any other now, both ways. */
  const flow = launch()
  eq(restoreSteps(flow, { conversation: 'ent-111111111111', appliedCentre: true }).find((s) => s.do === 'thread'),
    { do: 'thread', root: null, at: null },
    'F3: a launch made in the flow restores the flow, not whatever thread was entered since')
  const bare = launch({ reading: null, reply: null, draft: null })
  eq(restoreSteps(bare, { conversation: 'ent-111111111111', appliedCentre: true }).map((s) => s.do), ['thread', 'reply'],
    'and what the launch does not hold is not invented')
}

/* -- B4: go to source is not a dead end ------------------------------------- */
{
  const source = { conversation: 'ent-c', post: 'ent-88' }
  eq(sourceSteps({ where: 'max', from: 's1' }, source, { columns: ['s1', 's2'] }).map((s) => s.do), ['to-column', 'go-to-post'],
    'a maximised result with a column of its own goes back to it, and then to the post (H3)')
  eq(sourceSteps({ where: 'max', from: null }, source, { columns: [] }).map((s) => s.do), ['park', 'go-to-post'],
    'WITH NO COLUMN IT PARKS INSTEAD OF SITTING OVER THE POST (B4): nothing is closed, nothing is lost, and the post is actually on screen')
  eq(sourceSteps({ where: 'max', from: 's2' }, source, { columns: [] }).map((s) => s.do), ['park', 'go-to-post'],
    'and a column that is no longer shown is not moved to')
  eq(sourceSteps({ where: 's1' }, source, { columns: ['s1'] }).map((s) => s.do), ['go-to-post'],
    'a result already beside the conversation only shows the post')
}

/* -- B4: landing on a result entry again ------------------------------------ */
{
  clearLaunches()
  const viewers = resultViewers(launchOf)
  const l = launch()
  const target = { kind: 'artifact' as const, ref: REF }
  viewers.place('v1', l, target, 'max')
  const entry = resultIntent(BRAIN, l.opening, target, PLACE)
  const live = resumeResult(entry, { brainKey: BRAIN, live: (o) => !!launchOf(o), words: 'moved' })
  eq(resumeSteps(live, viewers), [{ do: 'show-viewer', viewer: 'v1', where: 'max' }],
    'ITS VIEWER IS SHOWN AGAIN (B4): Back and Forward are connected to the viewer store, not to a comment')
  viewers.forget('v1')
  const reloaded = resumeResult(entry, { brainKey: BRAIN, live: (o) => !!launchOf(o), words: 'moved' })
  eq(resumeSteps(reloaded, viewers), [{ do: 'resolve', target, back: PLACE }],
    'and with no viewer left, the target is resolved again with that Place as the way back')
  const moved = resumeResult(entry, { brainKey: 'fixture-corpus@instance-2', live: () => true, words: 'moved' })
  eq(resumeSteps(moved, viewers).map((s) => s.do), ['say', 'leave-on'],
    'another instance of the same corpus replays nothing: it is said, and the reader is left on the Place (H5)')
}

/* -- nothing here reaches a renderer, a permission or a byte ---------------- */
{
  const shown: Shown[] = ['max', 's1', 's2', 'none']
  for (const where of shown) {
    const viewers = resultViewers(launchOf)
    clearLaunches()
    const l = launch()
    viewers.place('v', l, null, where)
    eq(viewers.whereOf('v'), where, `a viewer is registered wherever it was placed: ${where}`)
  }
}

console.log(`quiet2 result host: ${checks} checks ok`)
