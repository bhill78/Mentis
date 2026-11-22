/* THE FORM'S OWN READ OF THE EXACT MATERIAL A DECISION APPROVES, checked
 * without a server or a browser (src/experimental/materialStanding.ts).
 *
 * The seam review finding F2 left open: the guard that withholds the choices of
 * an approval of one exact thing that cannot be inspected could only act where
 * the HOST resolved that id, and only Quiet Chat's Needs you does. This is the
 * shared form resolving for itself, through the same read.
 *
 * What it holds this code to:
 *   - A READ THAT HAS NOT ANSWERED IS NOT AN ANSWER. Pending, failed, too many
 *     to read and answered-for-another-Brain each claim NOTHING about any
 *     reference: no availability, no absence.
 *   - WHAT IT RESOLVED IS WHAT THE SERVER SAID, by the exact id and nothing
 *     else; an id it resolved nothing for is answered null.
 *   - ONE BRAIN, AND IT IS THE PAGE'S. Every answer, the reader's FIRST own
 *     read as much as any later one, is established against the identity the
 *     host/page already bound; another Brain's answer, an answer naming no
 *     Brain where the page named one, and a page that binds itself and cannot
 *     yet say which Brain each show nothing (re-review finding F1-R1). Where
 *     the page binds no Brain at all, the reader's own first answer binds it,
 *     as before.
 *   - A LATE ANSWER FROM A SUPERSEDED READ CHANGES NOTHING.
 *   - AND NEITHER DOES A SUPERSEDED READING ANSWER FOR ITSELF: what is in hand
 *     after it is what was read BEFORE it began, and the store says so. */
import assert from 'node:assert/strict'
import { createBinding } from '../src/brainBinding'
import {
  ANOTHER_ID, IDS_MAX, NO_BRAIN_SAID, NOT_ANSWERED_FOR, NOT_PROJECTED, NOT_RESOLVED,
  OTHER_BRAIN, READ_SAID, TOO_MANY, UNCONFIRMED_BRAIN, createStandingStore, keyOf,
  type AboutAnswer,
} from '../src/experimental/materialStanding'
import type { About } from '../src/quiet2/needs/inspect'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const BRAIN = { corpus_id: 'c1', instance: 'i1' }
const OTHER = { corpus_id: 'c1', instance: 'i2' }

/** One request as `needs-you/about` answers it: the declared exact record of
 *  one question, with that id resolved by the same resolver as every other
 *  reference there. */
function about(id: string, declared: { id: string; state: string; available: boolean; why?: string | null } | null): About {
  return {
    id, kind: 'form', form: 'ent-form', says: 'asks you to decide', asked_by_name: '@Coach',
    subject: [], evidence: [], context: [], referenced: [],
    question_references: declared
      ? [{
        expectation: id,
        presentation_status: { state: 'complete', problems: [] },
        primary: {
          kind: 'record', id: declared.id, label: 'the exact candidate design',
          availability: {
            id: declared.id, type: 'record', kind: 'note', label: 'the exact candidate design',
            available: declared.available, state: declared.state, why: declared.why ?? null,
            opens: declared.available ? 'record' : null, relation: 'the one source this question is about',
          },
        },
      }]
      : [],
  }
}

const answer = (brain: typeof BRAIN, ...items: About[]): AboutAnswer => ({ about: items, brain })

/* -- THE QUESTIONS ONE READ IS FOR ------------------------------------------- */
eq(keyOf(['opr-b', 'opr-a', 'opr-b']), 'opr-a,opr-b',
  'the same set of questions is one read however the form was drawn, and each question once')
eq(keyOf([]), '', 'and no questions needing material is no read at all')
ok(IDS_MAX <= 64, 'one read never asks for more than the server takes (mentis/fluid/read.py BATCH)')

/* -- PENDING: NOTHING IS KNOWN, AND NOTHING IS CLAIMED ----------------------- */
{
  const store = createStandingStore(createBinding())
  const key = keyOf(['opr-one'])
  const gen = store.begin(key)
  ok(store.reading(key), 'a read begun has not finished')
  eq(store.shown(key), null, 'and nothing is in hand while it is on its way')
  eq(store.why(key), null, 'which is not a reason: it is simply not read yet')
  ok(store.took(key, gen, answer(BRAIN, about('opr-one', { id: 'ent-abc123', state: 'missing', available: false, why: 'This Brain holds nothing with this id.' }))),
    'the answer of the latest read is taken')
  ok(!store.reading(key), 'and the read is over')
  const refs = store.shown(key)!
  ok(refs, 'what it resolved is in hand')
  const stood = refs.get('ent-abc123')!
  eq([stood.available, stood.state, stood.why], [false, 'missing', 'This Brain holds nothing with this id.'],
    'exactly as the server resolved that exact id: whether there is anything to look at, what became of it, and its own reason')
  eq(refs.get('ent-other') ?? null, null, 'and an id this read resolved nothing for is answered null, never substituted')
}

/* -- A READ THAT FAILED CLAIMS NOTHING EITHER -------------------------------- */
{
  const store = createStandingStore(createBinding())
  const key = keyOf(['opr-one'])
  const gen = store.begin(key)
  ok(store.took(key, gen, null, 'the server answered 500.'), 'a failure is an answer to the read, not to the question')
  eq(store.shown(key), null, 'nothing is in hand')
  eq(store.why(key), 'the server answered 500.', 'and why is said in the page’s own words')
}
{
  const store = createStandingStore(createBinding())
  const key = keyOf(['opr-one'])
  ok(store.took(key, store.begin(key), { error: 'what this request is about could not be read' } as AboutAnswer),
    'an answer with no resolutions in it is a failure of the read')
  eq(store.shown(key), null, 'and claims nothing')
  ok(store.why(key), 'with the server’s own reason where it gave one')
}

/* -- ONE BRAIN, FOR EVERY SET ------------------------------------------------ */
{
  const store = createStandingStore(createBinding())
  const first = keyOf(['opr-one'])
  const second = keyOf(['opr-two'])
  store.took(first, store.begin(first), answer(BRAIN, about('opr-one', { id: 'ent-abc123', state: 'ok', available: true })))
  ok(store.shown(first), 'the first answer binds the reader to the Brain that gave it')
  store.took(second, store.begin(second), answer(OTHER, about('opr-two', { id: 'ent-abc123', state: 'ok', available: true })))
  eq(store.shown(second), null, 'an answer for another Brain shows nothing')
  eq(store.why(second), OTHER_BRAIN, 'and says so, with the way back')
  eq(store.shown(first), null, 'AND NOTHING EARLIER IS CURRENT EITHER: the page has moved')
  eq(store.why(first), OTHER_BRAIN, 'so a form is never drawn against one Brain’s resolution of another’s id')
}
{
  const store = createStandingStore(createBinding())
  const key = keyOf(['opr-one'])
  store.took(key, store.begin(key), { about: [about('opr-one', { id: 'ent-abc123', state: 'ok', available: true })] })
  ok(store.shown(key), 'an answer naming no Brain decides nothing about the binding, as every other read of it')
}

/* -- A SUPERSEDED READ CHANGES NOTHING -------------------------------------- */
{
  const store = createStandingStore(createBinding())
  const key = keyOf(['opr-one'])
  const old = store.begin(key)
  const now = store.begin(key)
  ok(!store.took(key, old, answer(BRAIN, about('opr-one', { id: 'ent-abc123', state: 'missing', available: false }))),
    'an older read’s answer arriving late is discarded')
  ok(store.reading(key), 'the latest read is still the one on its way')
  ok(store.took(key, now, answer(BRAIN, about('opr-one', { id: 'ent-abc123', state: 'ok', available: true }))),
    'and only its own answer is taken')
  eq(store.shown(key)!.get('ent-abc123')!.state, 'ok', 'so what is shown is the latest read’s resolution')
}

/* -- EVERY REQUEST OF ONE READ, MERGED BY EXACT ID -------------------------- */
{
  const store = createStandingStore(createBinding())
  const key = keyOf(['opr-one', 'opr-two'])
  store.took(key, store.begin(key), answer(BRAIN,
    about('opr-one', { id: 'ent-aaa111', state: 'missing', available: false, why: 'This Brain holds nothing with this id.' }),
    about('opr-two', { id: 'ent-bbb222', state: 'ok', available: true })))
  const refs = store.shown(key)!
  eq(refs.get('ent-aaa111')!.state, 'missing', 'each question’s own declared record is resolved under its own id')
  eq(refs.get('ent-bbb222')!.state, 'ok', 'and one question’s resolution is never another’s')
}

ok(TOO_MANY.includes('not read'), 'and more questions than one read covers is said as not read, never as material that is gone')

/* -- AN ANSWER THAT ESTABLISHED NOTHING IS NOT AN ANSWER FOR THAT QUESTION ---
   Review finding B1 (ent-5b7ef83a4e40): a successful HTTP envelope whose own
   per-item envelope failed, which projected nothing, which named the thing
   without resolving it, or which answered about another id, was taken as a
   settled read -- and a settled read with no standing for the exact id left the
   question with no guard at all, so its stored option became an offered answer.
   Each is now unestablished FOR THAT QUESTION, said as what became of the READ,
   and NEVER as the record being missing. */
{
  const key = keyOf(['opr-one'])
  const WANT = 'ent-abc123'
  /** what the store came to for the one question, given this one item */
  const after = (item: unknown, required = WANT) => {
    const store = createStandingStore(createBinding())
    store.took(key, store.begin(key), { about: [item], brain: BRAIN } as AboutAnswer)
    return { read: store.answeredFor(key, 'opr-one', required), shown: store.shown(key) }
  }
  const claimsNothing = (why: string | null, what: string) => {
    ok(why, what + ': why the READ established nothing is said')
    for (const word of ['holds nothing', 'deleted', 'erased', 'missing', 'purged']) {
      ok(!why!.includes(word), `${what}: and nothing is claimed about the record (${word})`)
    }
  }

  /* the API's own per-item failure envelope, on HTTP 200 (inspect.py:439-441) */
  {
    const got = after({ id: 'opr-one', error: 'what this request is about could not be read (RuntimeError)' })
    ok(!got.read.settled, 'a question whose own item came back as a read failure is not established')
    ok(got.read.why!.startsWith(READ_SAID), 'and the server’s own reason is said as the read’s')
    ok(got.read.why!.includes('RuntimeError'), 'in the server’s own words')
    claimsNothing(got.read.why, 'a per-item read failure')
    eq(got.shown!.get(WANT) ?? null, null, 'and nothing whatever was resolved for the id it declares')
  }
  /* a server that does not project what each question declares */
  {
    const got = after({ ...about('opr-one', null), question_references: undefined })
    ok(!got.read.settled, 'a read that did not project this question’s references establishes nothing')
    eq(got.read.why, NOT_PROJECTED, 'and says that, not that the thing is gone')
    claimsNothing(got.read.why, 'an unprojected read')
  }
  eq(after(about('opr-one', null)).read.why, NOT_PROJECTED,
    'and neither does one that projected no entry for this question')
  /* named, and not resolved: `availability` absent is NOT an absent record */
  {
    const bare = about('opr-one', { id: WANT, state: 'ok', available: true })
    delete (bare.question_references![0].primary as { availability?: unknown }).availability
    const got = after(bare)
    ok(!got.read.settled, 'a declaration the read did not resolve establishes nothing')
    eq(got.read.why, NOT_RESOLVED, 'and is said as the read not having said how it stands')
    claimsNothing(got.read.why, 'an unresolved declaration')
  }
  /* ANOTHER ID IS NEVER THIS ONE, from either side of the mismatch */
  {
    const crossed = about('opr-one', { id: WANT, state: 'ok', available: true })
    crossed.question_references![0].primary!.availability!.id = 'ent-somethingelse'
    eq(after(crossed).read.why, ANOTHER_ID, 'a resolution of another id is not this question’s material')
  }
  eq(after(about('opr-one', { id: 'ent-somethingelse', state: 'ok', available: true })).read.why, ANOTHER_ID,
    'and neither is a question answered about a record other than the one it declares')
  /* a question the answer simply skipped */
  {
    const got = after(about('opr-two', { id: WANT, state: 'ok', available: true }))
    ok(!got.read.settled, 'a question the answer carried nothing for is not established')
    eq(got.read.why, NOT_ANSWERED_FOR, 'and says the read said nothing about it')
    claimsNothing(got.read.why, 'a skipped question')
  }
  /* and the one case that IS established */
  {
    const got = after(about('opr-one', { id: WANT, state: 'missing', available: false, why: 'This Brain holds nothing with this id.' }))
    ok(got.read.settled, 'a question whose own item resolved its own declared id IS established')
    eq(got.read.why, null, 'with nothing left to say about the read')
    eq(got.shown!.get(WANT)!.state, 'missing', 'and what it established is the server’s own resolution of that id')
  }
}
/* ONE QUESTION'S RESOLUTION IS NEVER ANOTHER'S ANSWER, even for the same id. */
{
  const store = createStandingStore(createBinding())
  const key = keyOf(['opr-one', 'opr-two'])
  const SAME = 'ent-abc123'
  store.took(key, store.begin(key), {
    about: [about('opr-one', { id: SAME, state: 'missing', available: false }),
      { id: 'opr-two', error: 'what this request is about could not be read (RuntimeError)' }],
    brain: BRAIN,
  } as AboutAnswer)
  ok(store.answeredFor(key, 'opr-one', SAME).settled, 'the question whose item answered is established')
  ok(!store.answeredFor(key, 'opr-two', SAME).settled,
    'and the one whose item failed is not, though its sibling resolved the very same id')
}

/* -- WHAT WAS READ IS NOT KEPT PAST THE DRAWING IT WAS MADE FOR -------------
   Review finding B2: a successful positive availability was never invalidated
   for the life of the page, so a form drawn again after its material was
   deleted went on offering the choice from a read nobody made again. */
{
  const store = createStandingStore(createBinding())
  const key = keyOf(['opr-one'])
  const WANT = 'ent-abc123'
  const there = () => store.took(key, store.begin(key), answer(BRAIN, about('opr-one', { id: WANT, state: 'ok', available: true })))

  const drawn = store.hold(key)
  there()
  ok(store.answeredFor(key, 'opr-one', WANT).settled, 'what a drawing read is in hand while it is drawn')
  const twice = store.hold(key)
  eq(store.shown(key)!.get(WANT)!.state, 'ok', 'and a second drawing of the same set shares the one read')
  twice()
  ok(store.shown(key), 'which one of them ending does not let go of')
  drawn()
  eq(store.shown(key), null, 'but the last one ending does: nothing positive survives the drawing it was read for')
  ok(!store.answeredFor(key, 'opr-one', WANT).settled,
    'so the next drawing establishes nothing until it has read again')
  ok(!store.reading(key), 'and nothing is left on its way, or polling, in between')
  /* AND THE NEXT DRAWING'S READ IS THE ONLY THING IN HAND */
  const again = store.hold(key)
  store.took(key, store.begin(key), answer(BRAIN, about('opr-one', { id: WANT, state: 'deleted', available: false, why: 'It was deleted.' })))
  eq(store.shown(key)!.get(WANT)!.state, 'deleted', 'what the material changed to is what the form is drawn against')
  again()
}
{
  const store = createStandingStore(createBinding())
  const key = keyOf(['opr-one'])
  store.hold(key)
  store.took(key, store.begin(key), answer(BRAIN, about('opr-one', { id: 'ent-abc123', state: 'ok', available: true })))
  store.forget(key)
  eq(store.shown(key), null, 'and what was read can be let go of outright')
}

/* -- WHAT IS IN HAND AFTER A READING IS ITS OWN ANSWER, OR IT IS NOT AN ANSWER
   FOR IT -----------------------------------------------------------------
   Review finding R1 on B2 (ent-f863f84301fc). The same question is drawn in two
   places -- a post and its thread -- and both drawings read for ONE set. Two
   readings made at the same moment, one per drawing, are two reads of that set,
   and only the later one's answer is kept: `took` discards the earlier. What
   the earlier reading is left holding is then what was read BEFORE either of
   them began -- the positive answer from before the material was deleted, which
   is the very thing it was made to replace. A sender that consults the store
   after its own read, without asking WHOSE answer is in hand, approves after
   deletion. So the store says which read's answer it holds. */
{
  const store = createStandingStore(createBinding())
  const key = keyOf(['opr-one'])
  const WANT = 'ent-abc123'
  const there = answer(BRAIN, about('opr-one', { id: WANT, state: 'ok', available: true }))
  const gone = answer(BRAIN, about('opr-one', { id: WANT, state: 'deleted', available: false, why: 'It was deleted; the record keeps that it was.' }))

  const drawn = store.hold(key)
  const twice = store.hold(key)
  eq(store.held(key), 0, 'nothing read is no read in hand, by generation')
  const first = store.begin(key)
  store.took(key, first, there)
  eq(store.held(key), first, 'and a read that was taken is the read in hand')
  ok(store.answeredFor(key, 'opr-one', WANT).settled, 'which established the material for the question')

  /* BOTH DRAWINGS READ AGAIN AT THE SAME MOMENT: one press in the post, one in
     its thread, each with its own read of the one set on its way. */
  const post = store.begin(key)
  const thread = store.begin(key)
  ok(post > first && thread > post, 'each reading is later than the drawing read and than the one before it')
  ok(store.reading(key), 'and while they are on their way, nothing has answered them')

  /* THE EARLIER ONE ANSWERS FIRST, with the server's own deleted resolution */
  eq(store.took(key, post, gone), false, 'the earlier reading’s answer is discarded: a later read supersedes it')
  eq(store.held(key), first, 'so what is in hand is still the read from BEFORE either reading began')
  ok(store.held(key) < post, 'which is not an answer for the earlier reading, however positive it is')
  ok(store.answeredFor(key, 'opr-one', WANT).settled,
    'and it still establishes the material — exactly the cache a sender must not be answered from')
  eq(store.shown(key)!.get(WANT)!.state, 'ok', 'it is the positive one, read before the deletion')

  /* THE LATER ONE ANSWERS, and that answer is an answer for BOTH readings: it
     began after either of them, so what it established is at least as new. */
  eq(store.took(key, thread, gone), true, 'the later reading’s answer is taken')
  ok(store.held(key) >= thread && store.held(key) >= post,
    'and is in hand for the later reading and for the earlier one alike')
  ok(store.answeredFor(key, 'opr-one', WANT).settled, 'that read established how the material stands')
  eq(store.shown(key)!.get(WANT)!.state, 'deleted', 'and what both readings are answered from is the deletion')
  eq(store.shown(key)!.get(WANT)!.available, false, 'resolved as nothing that can be inspected')

  /* A READING THAT FAILED IS STILL THAT READING'S OWN ANSWER */
  const failed = store.begin(key)
  eq(store.took(key, failed, null, 'the server did not answer.'), true, 'a read that failed is taken as that read')
  eq(store.held(key), failed, 'and is in hand for the reading that made it')
  ok(!store.answeredFor(key, 'opr-one', WANT).settled, 'establishing nothing, and claiming nothing')

  /* AND A READING OF A SET NOBODY DRAWS ANY MORE HOLDS NOTHING */
  const last = store.begin(key)
  twice()
  drawn()
  eq(store.held(key), 0, 'what was let go of is no read in hand')
  ok(store.held(key) < last, 'so a reading still on its way is answered by nothing it did not read itself')
}

/* -- AND THE ONE BRAIN IS THE PAGE'S, NOT THIS READER'S ---------------------
   Re-review finding F1-R1. The reader took the Brain of whatever answered it
   FIRST as its own identity. Under a host that supplies the drawing's
   resolution (Quiet Chat's Needs you), no own read has happened before the
   owner presses Decide, so the reader's first answer IS the seam read -- and a
   response explicitly naming another corpus established the material and let an
   approval be recorded here. The identity every answer is established against
   is now the one the HOST/PAGE already bound, including that first own read. */
{
  /** a host/page, as this reader asks it: what it bound, whether it moved, and
   *  whether it binds itself to a Brain at all */
  const host = (bound: string | null, opts: { moved?: boolean; binds?: boolean } = {}) =>
    ({ bound: () => bound, moved: () => opts.moved ?? false, binds: () => opts.binds ?? true })
  const key = keyOf(['opr-one'])
  const WANT = 'ent-abc123'
  const there = (brain: typeof BRAIN | undefined) =>
    ({ about: [about('opr-one', { id: WANT, state: 'ok', available: true })], brain }) as AboutAnswer
  /** what ONE answer -- this reader's FIRST -- came to, under this host */
  const first = (brain: typeof BRAIN | undefined, h: ReturnType<typeof host>) => {
    const store = createStandingStore(createBinding(), h)
    ok(store.took(key, store.begin(key), there(brain)), 'the answer of the latest read is taken')
    return { read: store.answeredFor(key, 'opr-one', WANT), shown: store.shown(key), why: store.why(key) }
  }

  /* THE FIRST OWN READ, ANSWERED FOR ANOTHER BRAIN THAN THE PAGE IS SHOWING */
  {
    const got = first(OTHER, host('c1@i1'))
    ok(!got.read.settled, 'an answer for another Brain than the page bound establishes nothing ON THE FIRST READ')
    eq(got.read.why, OTHER_BRAIN, 'and says so, with the way back')
    eq(got.shown, null, 'nothing it resolved is in hand')
    eq(got.why, OTHER_BRAIN, 'for this set and for every other: the reader has moved')
  }
  /* AND IT IS NOT ENOUGH TO NAME NO BRAIN AT ALL, where the page named one */
  {
    const got = first(undefined, host('c1@i1'))
    ok(!got.read.settled, 'an answer that named no Brain has not claimed the page’s identity either')
    eq(got.read.why, NO_BRAIN_SAID, 'and is said as the answer not saying which Brain answered')
    for (const word of ['holds nothing', 'deleted', 'erased', 'missing']) {
      ok(!got.read.why!.includes(word), `and claims nothing about the record (${word})`)
    }
  }
  /* A PAGE THAT BINDS ITSELF AND CANNOT YET SAY WHICH BRAIN: fail-closed */
  {
    const got = first(BRAIN, host(null, { binds: true }))
    ok(!got.read.settled, 'a page that binds itself and cannot yet say which Brain establishes nothing')
    eq(got.read.why, UNCONFIRMED_BRAIN, 'and says it cannot confirm which Brain the server serves')
  }
  /* A PAGE THAT HAS ALREADY MOVED */
  {
    const got = first(BRAIN, host('c1@i1', { moved: true }))
    ok(!got.read.settled, 'and a page that has already moved uses nothing, however it was answered')
    eq(got.read.why, OTHER_BRAIN, 'with the way back')
  }
  /* THE POSITIVE CONTROL: the page's own Brain, on the very first read */
  {
    const got = first(BRAIN, host('c1@i1'))
    ok(got.read.settled, 'the page’s own Brain answering IS established, on the first read as on any later one')
    eq(got.read.why, null, 'with nothing left to say about the read')
    eq(got.shown!.get(WANT)!.state, 'ok', 'and what it established is that server’s own resolution of that id')
  }
  /* A PAGE THAT BINDS NO BRAIN AT ALL (legacy Fluid) has no identity to
     compare with, and there the reader's own first answer is still all there
     is -- which is what every assertion above this block checks. */
  {
    const got = first(OTHER, host(null, { binds: false }))
    ok(got.read.settled, 'a page that binds no Brain at all is bound by its own first answer, as before')
  }
  /* AND WHAT IS IN HAND IS STILL COMPARED WITH THE PAGE'S IDENTITY: a read
     answered before the page could say which Brain it is on is not
     retroactively an answer for whatever it turned out to be. */
  {
    let bound: string | null = null
    const store = createStandingStore(createBinding(),
      { bound: () => bound, moved: () => false, binds: () => false })
    store.took(key, store.begin(key), there(BRAIN))
    ok(store.answeredFor(key, 'opr-one', WANT).settled, 'what the read established while nothing was bound is in hand')
    bound = 'c1@i2'
    ok(!store.answeredFor(key, 'opr-one', WANT).settled,
      'and stops being in hand once the page binds a Brain the answer did not name')
    eq(store.shown(key), null, 'nothing it resolved is used for that page')
    eq(store.why(key), OTHER_BRAIN, 'and the way back is said')
    bound = 'c1@i1'
    ok(store.answeredFor(key, 'opr-one', WANT).settled, 'the Brain it did name is established as it always was')
  }
}

console.log(`material standing: ${checks} checks ok`)
