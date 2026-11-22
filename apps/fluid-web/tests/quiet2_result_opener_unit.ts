/* OPENING A RESULT, AND COMING BACK FROM IT, checked without a browser
 * (src/quiet2/results/{opener,launch,history}.ts).
 *
 * The rows are the navigation review's own falsifiers: H1 (a side column is
 * not a page), H2 (one centre entry per displacement; no double pop), H3 (a
 * cross-conversation source is not a dead end), H4/H5 (an explicit return
 * restores the Place AND the pending decision; nothing stale is reopened or
 * submitted), H6 (focus per opening, not one module-global), H8 (a reload
 * promises only what survives it), and B4's one host operation -- including
 * that a failure is never reported as having left, and that a recorded
 * external link leaves this page, its dock and its draft exactly as they
 * were. */
import assert from 'node:assert/strict'
import {
  BRAIN_MOVED, BRAIN_UNCONFIRMED, MAX_LIVE_LAUNCHES, acceptsLate, beginOpening, brainVerdict, clearLaunches, corpusOf, focusChoice, historyOf,
  holdLaunch, isPlaced, launchOf, latestOpening, liveLaunches, placedLaunch, releaseLaunch, restoreOf, sameBrain,
  type LaunchContext, type LaunchPlace,
} from '../src/quiet2/results/launch'
import {
  closePlan, entersCentre, historyStep, isResultHistory, keepsReturnBar, resultIntent, resumeResult, sameResult,
  type Shown,
} from '../src/quiet2/results/history'
import {
  displaces, leaves, navigationOf, openResultTarget, pending,
  type Navigation, type OpenerHost, type Opened, type Placed, type Read,
} from '../src/quiet2/results/opener'
import type { ResultDestination, ResultTarget } from '../src/quiet2/results/targets'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const no = (a: unknown, what: string) => { assert.ok(!a, what); checks++ }

const ONE = 'corpus-a@instance-1'
const AGAIN = 'corpus-a@instance-2'
const OTHER = 'corpus-b@instance-1'
const HERE = 'https://mentis.example'
const SHA = 'b'.repeat(40)

const PLACE: LaunchPlace = { conversation: 'ent-conv', centre: null }
const RECORD_PLACE: LaunchPlace = { conversation: 'ent-conv', centre: { brain: { stack: [{ page: 'record', entry: 'ent-rec' }], origin: { from: 'link' } } } }

const launch = (over: Partial<LaunchContext> = {}): LaunchContext => ({
  opening: beginOpening(), brainKey: ONE, place: PLACE, thread: null, reading: { scroll: 420, offset: 12 },
  reply: 'ent-reply', draft: 'thread:ent-conv:ent-root', focus: { control: 'result:adm-1', fallback: { kind: 'conversation' } },
  ...over,
})

const dest = (over: Partial<ResultDestination> & { target: ResultTarget }): ResultDestination => ({
  label: 'a result', source: null, basis: ['returned-by-run'], verified: true,
  availability: 'ok', available: true, opens: 'file', ...over,
})
const FILE = dest({ target: { kind: 'artifact', ref: 'adm-667a23eb07a8' } })

interface Did { files: number; launches: number[]; posts: string[]; records: string[]; conversations: string[]; tabs: string[]; said: string[] }
/* A HOST WHOSE MOVES REALLY FINISHED ON THE PRESS says `completed`: the page's
   own record route does (`enterBrain` is a state change), and its guarded
   conversation and post routes do not -- those are the rows further down. */
function host(over: Partial<OpenerHost> = {}): OpenerHost & { did: Did } {
  const did: Did = { files: 0, launches: [], posts: [], records: [], conversations: [], tabs: [], said: [] }
  return {
    did, brainKey: ONE, origin: HERE,
    file: (o) => { did.files++; did.launches.push(o.launch.opening); return 'max' },
    post: (c, p) => { did.posts.push(`${c}/${p}`); return 'completed' },
    record: (r) => { did.records.push(r); return 'completed' },
    conversation: (c) => { did.conversations.push(c); return 'completed' },
    external: (h) => { did.tabs.push(h); return true },
    say: (w) => { did.said.push(w) },
    ...over,
  }
}

/* -- which Brain, and which instance of it (review B3 item 7) --------------- */
{
  eq(brainVerdict(ONE, ONE), 'same', 'the Brain this page was bound to')
  eq(brainVerdict(ONE, AGAIN), 'other-instance', 'the same corpus, restored or served elsewhere, is NOT the same Brain here')
  eq(brainVerdict(ONE, OTHER), 'other-brain', 'another Brain entirely')
  eq(brainVerdict(ONE, null), 'unknown', 'an unknown Brain is never treated as a match')
  eq(corpusOf(ONE), 'corpus-a', 'the corpus is readable for the wording')
  no(sameBrain(ONE, AGAIN) || sameBrain(null, null), 'and the whole key is what is compared')
}

/* -- one opening at a time (H6, and late reads) ----------------------------- */
{
  clearLaunches()
  const first = holdLaunch(launch())
  eq(launchOf(first.opening), first, 'the opening being made is held')
  ok(acceptsLate(first.opening, { latest: latestOpening(), brainKey: ONE }, ONE), 'its own read may act')
  const second = holdLaunch(launch())
  no(acceptsLate(first.opening, { latest: latestOpening(), brainKey: ONE }, ONE), 'a read that finishes late cannot replace the newer opening')
  ok(acceptsLate(second.opening, { latest: latestOpening(), brainKey: ONE }, ONE), 'the newest one still may')
  no(acceptsLate(second.opening, { latest: latestOpening(), brainKey: AGAIN }, ONE), 'but not once the server serves another instance')
  /* AND THAT CANCELLATION TAKES NOTHING AWAY FROM THE FIRST (review B2): the
     viewer it opened is still on the page, and still owes its reader a way
     back to the row it was pressed in. The number decides what may act; the
     registry says what is still open. */
  eq(launchOf(first.opening), first, 'a newer opening does not end an earlier one: its viewer is still open')
  releaseLaunch(second.opening)
  no(launchOf(second.opening), 'and a released opening holds nothing')
  releaseLaunch(first.opening)
}
/* -- the bound on what is kept ----------------------------------------------- */
{
  clearLaunches()
  const kept = holdLaunch(launch())
  placedLaunch(kept.opening)
  ok(isPlaced(kept.opening), 'a placed viewer says so')
  for (let i = 0; i < MAX_LIVE_LAUNCHES + 4; i++) holdLaunch(launch())
  ok(liveLaunches().length <= MAX_LIVE_LAUNCHES, 'openings nothing released are bounded, not endless')
  eq(launchOf(kept.opening), kept, 'and the one with a viewer on the page is the last to be dropped, not the first')
}

/* -- what may be written into a history entry (H8) -------------------------- */
{
  const l = launch({ decision: { form: 'form-1', question: 'opr-q', item: 'item-1', ref: 'adm-1', role: 'subject' } })
  const mark = historyOf(l)
  eq(Object.keys(mark).sort(), ['brainKey', 'opening', 'place'], 'an entry holds which opening, which Brain, which Place -- and nothing else')
  ok(!JSON.stringify(mark).includes('thread:ent-conv'), 'no draft key in the history')
  ok(!JSON.stringify(mark).includes('item-1'), 'and no decision token in it either')
  eq(JSON.parse(JSON.stringify(mark)), mark, 'it is serializable as written')
}

/* -- a side column is not a page (H1) --------------------------------------- */
{
  no(entersCentre('s1') || entersCentre('s2') || entersCentre('none'), 'a working column never displaces the centre')
  ok(entersCentre('max'), 'only maximised does')
  eq(historyStep('none', 's1'), 'none', 'opening beside the conversation adds no entry and runs no centre guard')
  eq(historyStep('s1', 's2'), 'none', 'moving between columns adds none')
  eq(historyStep('s1', 'none'), 'none', 'closing a column gives up none')
  eq(historyStep('none', 'max'), 'push', 'maximised over the conversation is one entry')
  eq(historyStep('s1', 'max'), 'push', 'and so is maximising one already open beside it')
  eq(historyStep('max', 's1'), 'consume', 'restoring it to its column consumes that entry, and keeps the viewer')
  eq(historyStep('max', 'none'), 'consume', 'closing it consumes it')
  eq(historyStep('max', 'max'), 'none', 'and nothing stacks a duplicate for max-to-max')
  for (const p of ['max', 's1', 's2', 'none'] as Shown[]) eq(historyStep(p, p), 'none', `no change is no entry: ${p}`)
}

/* -- closing returns to the reader, never to the source (H2, B3 item 3) ----- */
{
  eq(closePlan(true, true), 'back', 'it owns the entry and the Place is behind: one step back, as the browser’s own Back')
  eq(closePlan(true, false), 'replace', 'it owns the entry with nothing behind: this entry becomes the Place, adding nothing')
  eq(closePlan(false, true), 'frame-only', 'navigation has since left: only the frame closes')
  ok(keepsReturnBar('frame-only'), 'and the explicit return bar is what restores the launch then')
  no(keepsReturnBar('back') || keepsReturnBar('replace'), 'a close that walked the history owes no bar')
}

/* -- landing on a result entry again (H2, H8, B3 item 7) -------------------- */
{
  const target: ResultTarget = { kind: 'artifact', ref: 'adm-667a23eb07a8' }
  const h = resultIntent(ONE, 7, target, RECORD_PLACE)
  ok(isResultHistory(h) && !isResultHistory({ brain: {} }) && !isResultHistory(null), 'a result entry is told apart from the others')
  eq(JSON.stringify(h), JSON.stringify(resultIntent(ONE, 7, target, RECORD_PLACE)), 'the same result is byte-identical, so centreHistory walks back to it')
  ok(sameResult(h.result, resultIntent(ONE, 7, target, PLACE).result), 'the same opening of the same target is the same result')
  no(sameResult(h.result, resultIntent(ONE, 8, target, RECORD_PLACE).result), 'another opening is not')
  const live = resumeResult(h, { brainKey: ONE, live: () => true, words: BRAIN_MOVED })
  eq(live.how, 'live', 'this page’s Brain with the launch still live: reopen it')
  const reloaded = resumeResult(h, { brainKey: ONE, live: () => false, words: BRAIN_MOVED })
  eq(reloaded.how, 'resolve', 'after a reload the target is resolved again')
  eq(reloaded.how === 'resolve' && reloaded.place, RECORD_PLACE, 'and the Place it was over -- a record, not merely a conversation (focused review M2.3)')
  const moved = resumeResult(h, { brainKey: AGAIN, live: () => true, words: BRAIN_MOVED })
  eq(moved.how, 'other-brain', 'Forward must not reopen a prior Brain instance’s file')
  eq(moved.how === 'other-brain' && moved.place, RECORD_PLACE, 'the reader is left on the Place, honestly')
  eq(resumeResult(h, { brainKey: null, live: () => true, words: BRAIN_MOVED }).how, 'other-brain', 'an unknown Brain replays nothing')
}

/* -- what a stored launch can still restore (H8) ---------------------------- */
{
  clearLaunches()
  const l = holdLaunch(launch({ place: RECORD_PLACE }))
  const mark = historyOf(l)
  const now = { brainKey: ONE, launch: launchOf }
  eq(restoreOf(mark, now).how, 'live', 'while the page lives, the whole launch comes back')
  releaseLaunch(l.opening)
  const after = restoreOf(mark, now)
  eq(after.how, 'place', 'after a reload, its Place -- and no promised draft or focus')
  eq(after.how === 'place' && after.place, RECORD_PLACE, 'the saved Place, as it was')
  const elsewhere = restoreOf(mark, { brainKey: AGAIN, launch: launchOf })
  eq(elsewhere.how, 'other-brain', 'and another instance restores nothing')
  eq(elsewhere.how === 'other-brain' && elsewhere.words, BRAIN_MOVED, 'with the existing binding words')
}

/* -- focus, per opening (H6) ------------------------------------------------- */
{
  const l = launch({ focus: { control: 'needs-ref:adm-1', fallback: { kind: 'decision', item: 'item-1' } } })
  eq(focusChoice(l, { isConnected: true }, () => false), { how: 'invoker' }, 'the very control that was pressed, where it is still in the page')
  eq(focusChoice(l, { isConnected: false }, (c) => c === 'needs-ref:adm-1'), { how: 'control', control: 'needs-ref:adm-1' },
    'else the same control by identity, drawn again in the restored pane (a menu that unmounted)')
  eq(focusChoice(l, null, () => false), { how: 'fallback', fallback: { kind: 'decision', item: 'item-1' } },
    'else this launch’s own fallback: the decision pill for a decision launch')
  eq(focusChoice(launch({ focus: { control: null, fallback: { kind: 'latest' } } }), null, () => true), { how: 'fallback', fallback: { kind: 'latest' } },
    'and the Latest trigger for a Latest launch -- not whatever opened something else')
}

/* -- one host operation opens every target (B4) ----------------------------- */
{
  clearLaunches()
  const l = holdLaunch(launch())
  {
    const h = host()
    const r = openResultTarget(FILE, l, h)
    eq(r, { what: 'opened', how: 'file', where: 'max' }, 'held bytes open in the page’s viewer')
    ok(leaves(r) && displaces(r), 'a real open is a departure, and a maximised one owes the history an entry')
    eq(h.did.files, 1, 'through the host’s existing viewer, once')
    eq(h.did.launches, [l.opening], 'AND THE CALLER’S OWN LAUNCH REACHES IT (review B2): the viewer returns to the control that was pressed, not to one the host made for itself afterwards')
  }
  {
    const h = host({ file: () => 'choosing' })
    const r = openResultTarget(FILE, l, h)
    eq(r, { what: 'placing' }, 'while the reader chooses a column, nothing has been opened')
    no(leaves(r) || displaces(r), 'so nothing has been left and no entry is owed (a cancelled placement leaves none)')
  }
  {
    const h = host({ file: () => null })
    const r = openResultTarget(FILE, l, h)
    eq(r.what, 'unavailable', 'a viewer that could not open it says so')
    no(leaves(r), 'and the caller keeps its decision and its draft: no false "left" transition')
    eq(h.did.said.length, 1, 'the reader is told, once')
  }
  {
    const h = host()
    eq(openResultTarget(dest({ target: { kind: 'post', conversation: 'ent-c', post: 'ent-88' }, opens: 'post' }), l, h),
      { what: 'opened', how: 'post', where: 'none' }, 'a post opens its exact post, loading its thread and conversation (H3)')
    eq(h.did.posts, ['ent-c/ent-88'], 'by identity, not by what happens to be drawn')
  }
  {
    const h = host({ post: () => 'failed' })
    eq(openResultTarget(dest({ target: { kind: 'post', conversation: 'ent-c', post: 'ent-88' }, opens: 'post' }), l, h).what, 'unavailable',
      'a post that could not be read is said, not a dead end')
  }
  {
    const h = host()
    eq(openResultTarget(dest({ target: { kind: 'record', ref: 'ent-rec' }, opens: 'record' }), l, h).what, 'opened', 'a record opens the record page')
    eq(h.did.records, ['ent-rec'], 'and never a synthetic post')
    eq(openResultTarget(dest({ target: { kind: 'record', ref: 'ent-conv' }, opens: 'conversation' }), l, h).what, 'opened', 'a conversation record opens the conversation')
    eq(h.did.conversations, ['ent-conv'], 'through the existing route')
  }
  {
    const h = host({ record: undefined })
    const r = openResultTarget(dest({ target: { kind: 'record', ref: 'ent-rec' }, opens: 'record' }), l, h)
    eq(r.what, 'unavailable', 'a host that cannot inspect that record says so')
    no(leaves(r), 'and the reader has not left')
  }
  {
    const gone = dest({ target: { kind: 'artifact', ref: 'adm-1' }, available: false, availability: 'held-but-corrupt', reason: 'its bytes do not read as what was stored' })
    const h = host()
    const r = openResultTarget(gone, l, h)
    eq(r, { what: 'unavailable', why: 'its bytes do not read as what was stored' }, 'an unavailable target is its own exact reason')
    eq(h.did.files, 0, 'nothing is opened')
    eq(h.did.said, ['its bytes do not read as what was stored'], 'and nothing unrelated is shown instead')
  }
  {
    /* `ok` with no route: available, and still nothing to open (M2.2) */
    const h = host()
    eq(openResultTarget(dest({ target: { kind: 'artifact', ref: 'adm-1' }, opens: null }), l, h).what, 'unavailable', 'held with no route opens nothing')
    eq(h.did.files, 0, 'and does not reach the viewer')
  }
}

/* -- a recorded external link leaves the page as it was (P5, M2.4) ---------- */
{
  clearLaunches()
  const l = holdLaunch(launch())
  const h = host()
  const r = openResultTarget(dest({ target: { kind: 'url', href: 'https://example.org/x' }, opens: null }), l, h)
  eq(r, { what: 'external', href: 'https://example.org/x' }, 'the recorded link, in a new tab')
  no(leaves(r), 'THE DOCK AND THE DRAFT ARE INTACT: a new tab does not take this page anywhere')
  no(displaces(r), 'and the centre is untouched, so the history gains nothing')
  eq(h.did.tabs, ['https://example.org/x'], 'opened once, on the press')
  eq(h.did.files + h.did.posts.length + h.did.records.length, 0, 'and no Mentis route is taken for it')
  const unsafe = openResultTarget(dest({ target: { kind: 'url', href: 'file:///C:/Work/Mentis/x' }, opens: null }), l, host())
  eq(unsafe.what, 'unavailable', 'a local path recorded as a URL is refused here')
  const same = openResultTarget(dest({ target: { kind: 'url', href: HERE + '/api/artifacts/adm-1' }, opens: null }), l, host())
  eq(same.what, 'unavailable', 'and so is a same-origin API address')
}

/* -- a commit (V4) ---------------------------------------------------------- */
{
  clearLaunches()
  const l = holdLaunch(launch())
  const h = host()
  eq(openResultTarget(dest({ target: { kind: 'commit', sha: SHA, repository: 'bhill78/Mentis', record: 'ent-rec' }, opens: null }), l, h).what, 'opened',
    'a commit with a record goes through the existing record inspection')
  eq(h.did.records, ['ent-rec'], 'to that exact record')
  const bare = openResultTarget(dest({ target: { kind: 'commit', sha: SHA, repository: 'bhill78/Mentis' }, opens: null }), l, host())
  eq(bare.what, 'identity', 'without one, its identity is said as text')
  ok(bare.what === 'identity' && /no commit viewer/i.test(bare.words), 'and no commit browser is claimed')
  no(leaves(bare), 'saying so is not leaving')
}

/* -- stale reads and another Brain (H5, B3 item 7) -------------------------- */
{
  clearLaunches()
  const l = holdLaunch(launch())
  const moved = host({ brainKey: AGAIN })
  const r = openResultTarget(FILE, l, moved)
  eq(r, { what: 'refused', why: BRAIN_MOVED }, 'an opening made against another instance is refused, not resolved')
  eq(moved.did.files, 0, 'nothing is read')
  no(leaves(r), 'and nothing is left')
  const older = l
  holdLaunch(launch())
  const late = openResultTarget(FILE, older, host())
  eq(late.what, 'refused', 'a read that finished after a newer opening cannot draw over it')
  const given = openResultTarget(FILE, older, host(), { latest: older.opening })
  eq(given.what, 'opened', 'and an immediate press is judged against its own opening')
}

/* -- F3: AN OPENING THAT NAMES NO BRAIN IS REFUSED, NOT EXEMPT -------------
 *
 * (independent review adm-1cb30e65d05f.) `launch.brainKey && …` and `if (!was)
 * return true` made the one opening whose Brain cannot be checked the one
 * opening nothing could refuse: a press made before this page had confirmed
 * which Brain it is on, or after it had moved, resolved its target, opened a
 * viewer, navigated to a record and reported `opened`. */
{
  clearLaunches()
  const unknown = holdLaunch(launch({ brainKey: null }))
  const serving = host()
  const r = openResultTarget(FILE, unknown, serving)
  eq(r, { what: 'refused', why: BRAIN_UNCONFIRMED }, 'F3: a press that named no Brain opens nothing, whatever is served now')
  eq(serving.did.files, 0, 'F3: and nothing is read, so no viewer is made and no placement happens')
  eq(serving.did.said, [BRAIN_UNCONFIRMED], 'F3: the reader is told which state the page is in, once')
  no(leaves(r), 'and the dock, the form and the unsent draft are kept: nothing was left')

  const RECORD = dest({ target: { kind: 'record', ref: 'ent-record12345' }, opens: 'record' })
  const toRecord = host()
  eq(openResultTarget(RECORD, unknown, toRecord).what, 'refused', 'F3: nor does it navigate to a record')
  eq(toRecord.did.records, [], 'F3: the record route is not even asked -- the gate is before the target')
}
{
  /* AND A PAGE THAT CANNOT SAY REFUSES AN OPENING THAT DID NAME ONE: both
     sides must be confirmed, and the same. A host that supplies no state at
     all is read through `servingOfKey`, so this is also what a host wired with
     `brainKey` alone does -- omitting the state cannot reopen the bypass. */
  clearLaunches()
  const l = holdLaunch(launch())
  const cannotSay = host({ brainKey: null })
  eq(openResultTarget(FILE, l, cannotSay), { what: 'refused', why: BRAIN_UNCONFIRMED },
    'F3: a page with no confirmed identity opens nothing a confirmed launch asks for either')
  eq(cannotSay.did.files, 0, 'nothing is read')
  const hasMoved = host({ brainKey: null, serving: () => ({ how: 'moved' as const }) })
  eq(openResultTarget(FILE, l, hasMoved), { what: 'refused', why: BRAIN_MOVED },
    'F3: and a MOVED page is told apart from one that has not answered yet, in the reader’s own words')
}
{
  /* THE LATE GATE TAKES THE SAME RULE (F3). `acceptsLate` is what the opener
     re-enters after a fresh read, and `if (!was) return true` was its own copy
     of the exemption. */
  clearLaunches()
  const l = holdLaunch(launch({ brainKey: null }))
  no(acceptsLate(l.opening, { latest: latestOpening(), brainKey: ONE }, null),
    'F3: an answer to an opening that named no Brain does not act because a Brain has since answered')
  no(acceptsLate(l.opening, { latest: latestOpening(), brainKey: null }, null),
    'F3: nor because none has')
  no(acceptsLate(l.opening, { latest: latestOpening(), serving: { how: 'moved' } }, ONE),
    'F3: a moved page accepts nothing late, by the state and not only by the key')
  ok(acceptsLate(l.opening, { latest: latestOpening(), serving: { how: 'serving', key: ONE } }, ONE),
    'preserved: a confirmed identity on both sides, the same one, still acts')
}

/* -- NO DEPARTURE BEFORE THE NAVIGATION HAS SUCCEEDED (review B3) ----------- */
{
  clearLaunches()
  const l = holdLaunch(launch())
  const POST = dest({ target: { kind: 'post', conversation: 'ent-c', post: 'ent-88' }, opens: 'post' })
  const CONV = dest({ target: { kind: 'record', ref: 'ent-conv' }, opens: 'conversation' })
  const did: string[] = []
  {
    /* THE EXACT OLD ADAPTER: `(c, p) => { goToPost(c, p); return true }`. The
       page's `goToPost` returns nothing, runs the unsaved-work guard and
       reads a thread afterwards, so `true` says only that it has begun. */
    const h = host({ post: (c, p) => { did.push(`${c}/${p}`); return true as unknown as Navigation } })
    const r = openResultTarget(POST, l, h)
    eq(did, ['ent-c/ent-88'], 'the page is asked for the exact post')
    eq(r, { what: 'leaving', how: 'post' }, 'a boolean is read as "it has begun", never as "it arrived"')
    no(leaves(r), 'SO NOTHING HAS LEFT: the dock, the open form and the unsent draft are untouched')
    no(displaces(r), 'and the history is owed nothing yet')
    ok(pending(r), 'the caller waits for the answer rather than guessing')
  }
  {
    /* the reader answered the guard with Stay */
    const h = host({ conversation: () => ({ how: 'cancelled' }) })
    const r = openResultTarget(CONV, l, h)
    eq(r.what, 'cancelled', 'a reader who stays has not left')
    no(leaves(r) || pending(r), 'and nothing is pending for them either')
    eq(h.did.said, [], 'they are not told what they just chose')
  }
  {
    /* the guard passed, the thread read failed */
    const h = host({ post: () => ({ how: 'failed', why: 'That post could not be read.' }) })
    const r = openResultTarget(POST, l, h)
    eq(r, { what: 'unavailable', why: 'That post could not be read.' }, 'a failed read is said in the page’s own words')
    no(leaves(r), 'and is not a departure')
  }
  {
    /* THE LATE ANSWER IS WHERE THE DEPARTURE IS DECIDED */
    const said: Opened[] = []
    let answer: ((n: Navigation) => void) | null = null
    const h = host({ post: (_c, _p, settled) => { answer = settled; return 'requested' } })
    const r = openResultTarget(POST, l, h, { settled: (o) => said.push(o) })
    eq(r.what, 'leaving', 'the press itself says only that it asked')
    eq(said, [], 'and says nothing twice')
    answer!('requested')
    eq(said, [], '"still going" is not an answer')
    answer!('completed')
    eq(said, [{ what: 'opened', how: 'post', where: 'none' }], 'the guard passed and the post was read: NOW the reader has left')
    ok(said.every(leaves), 'which is the one rule the dock arms its way back on')
  }
  {
    const said: Opened[] = []
    let answer: ((n: Navigation) => void) | null = null
    const h = host({ conversation: (_c, settled) => { answer = settled; return 'requested' } })
    openResultTarget(CONV, l, h, { settled: (o) => said.push(o) })
    answer!({ how: 'cancelled', why: 'They stayed.' })
    eq(said, [{ what: 'cancelled', why: 'They stayed.' }], 'a cancellation that arrives late is a cancellation, not a departure')
    no(said.some(leaves), 'so the form and its draft are kept')
  }
  {
    /* A COLUMN CHOSEN AFTER THE PRESS: the one path that arms `leaveFor` on a
       placement that actually succeeded (review B4's last item). */
    const said: Opened[] = []
    let place: ((p: Placed) => void) | null = null
    const h = host({ file: (o) => { place = o.settled; return 'choosing' } })
    const r = openResultTarget(FILE, l, h, { settled: (o) => said.push(o) })
    eq(r, { what: 'placing' }, 'while the reader is choosing, nothing has been opened')
    place!({ how: 'completed', where: 's2' })
    eq(said, [{ what: 'opened', how: 'file', where: 's2' }], 'the column they chose is where it went')
    no(displaces(said[0]), 'a column is not the centre, so it owes no entry (H1)')
    const after: Opened[] = []
    const h2 = host({ file: (o) => { place = o.settled; return 'choosing' } })
    openResultTarget(FILE, l, h2, { settled: (o) => after.push(o) })
    place!({ how: 'cancelled' })
    eq(after.map((o) => o.what), ['cancelled'], 'and a placement the reader abandoned leaves no entry and no departure')
  }
  {
    /* `navigationOf` reads every shape the host can answer with */
    eq(navigationOf('completed').how, 'completed', 'the word itself')
    eq(navigationOf({ how: 'failed', why: 'x' }), { how: 'failed', why: 'x' }, 'the word with the page’s own reason')
    eq(navigationOf(true).how, 'requested', 'a legacy boolean has only begun')
    eq(navigationOf(undefined).how, 'failed', 'nothing at all is a failure')
    eq(navigationOf(false).how, 'failed', 'and so is a refusal')
    eq(navigationOf('whatever').how, 'requested', 'a word this build does not know is never read as success')
  }
}

/* -- read again on the explicit open (A4/P4) -------------------------------- */
{
  clearLaunches()
  const l = holdLaunch(launch())
  {
    const h = host({ read: () => ({ how: 'gone', why: 'It was permanently deleted.' }) })
    const r = openResultTarget(FILE, l, h)
    eq(r, { what: 'unavailable', why: 'It was permanently deleted.' }, 'a row drawn minutes ago is read again on the press: the server’s own word now')
    eq(h.did.files, 0, 'and the viewer is never reached for it')
  }
  {
    const h = host({ read: () => ({ how: 'unchecked' }) })
    eq(openResultTarget(FILE, l, h).what, 'opened', 'a host with no second reader opens what it has, as before')
  }
  {
    const said: Opened[] = []
    let answer: ((r: Read) => void) | null = null
    const h = host({ read: (_ref, settled) => { answer = settled; return { how: 'reading' } } })
    const r = openResultTarget(FILE, l, h, { settled: (o) => said.push(o) })
    eq(r, { what: 'leaving', how: 'file' }, 'while it is being read, nothing has been opened or left')
    answer!({ how: 'fresh', destination: FILE })
    eq(said, [{ what: 'opened', how: 'file', where: 'max' }], 'and the fresh read is what is opened')
  }
  {
    const h = host({ read: () => ({ how: 'fresh', destination: dest({ target: { kind: 'artifact', ref: 'adm-another' } }) }) })
    const r = openResultTarget(FILE, l, h)
    eq(r.what, 'refused', 'a read that answers about another identity is not this press’s answer')
    eq(h.did.files, 0, 'so nothing is opened for it')
  }
  {
    const gone = dest({ target: { kind: 'artifact', ref: 'adm-667a23eb07a8' }, available: false, availability: 'purged', reason: 'Its contents were purged from this Brain.' })
    const h = host({ read: () => ({ how: 'fresh', destination: gone }) })
    eq(openResultTarget(FILE, l, h).what, 'unavailable', 'and a fresh read that says it has gone is obeyed over the row in hand')
  }
}

const ALL: Opened[] = [
  { what: 'placing' }, { what: 'leaving', how: 'post' }, { what: 'cancelled', why: 'x' },
  { what: 'identity', words: 'x' }, { what: 'unavailable', why: 'x' }, { what: 'refused', why: 'x' },
]
for (const r of ALL) no(leaves(r), `nothing but a real open is a departure: ${r.what}`)

console.log(`quiet2 result opener: ${checks} checks ok`)
