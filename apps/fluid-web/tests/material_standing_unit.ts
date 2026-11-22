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
 *   - ONE BRAIN. The first answer binds the reader; another Brain's answer
 *     shows nothing, for every set, until the page is reloaded.
 *   - A LATE ANSWER FROM A SUPERSEDED READ CHANGES NOTHING. */
import assert from 'node:assert/strict'
import { createBinding } from '../src/brainBinding'
import {
  IDS_MAX, OTHER_BRAIN, TOO_MANY, createStandingStore, keyOf,
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

console.log(`material standing: ${checks} checks ok`)
