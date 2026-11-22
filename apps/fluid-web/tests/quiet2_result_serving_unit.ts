/* WHICH BRAIN THE SERVER SERVES, AGAINST THE REAL BINDING (independent
 * re-review adm-af5263a65134, F1 and F2).
 *
 * `results/serving.ts` is two lines, and both findings turn on them, so they
 * are checked against the things they actually read and not against a stand-in:
 *
 *   - the REAL `brainBinding.ts` -- `createBinding()` for the arms, and the
 *     page's own module binding for `servingBrainKey()` itself, so the
 *     production path is executed and not merely described;
 *   - the REAL `spaceBrainKey` constructor (`space/registry.ts`), to show what
 *     the hand-off used to supply instead: two serving instances of one corpus
 *     at one origin have the SAME graph key, and distinct binding keys. The
 *     constructor is not changed, asked to change, or wrong -- it was being
 *     asked the wrong question;
 *   - the REAL `brainVerdict` (`results/launch.ts`), because what `serving.ts`
 *     answers only matters through what the result decisions then read it as.
 *
 * THE PAGE BINDING IS A SINGLETON AND MOVES ONE WAY, which is the behaviour
 * under test: only a reload binds a moved page again. So the cases that move it
 * are last, and they are in this file alone. */
import assert from 'node:assert/strict'
import { servingBrainKey, servingKeyOf, servingNow, servingOf } from '../src/quiet2/results/serving'
import { createBinding, page as pageBinding } from '../src/brainBinding'
import { BRAIN_MOVED, BRAIN_UNCONFIRMED, actingWords, brainVerdict, mayAct, servingOfKey } from '../src/quiet2/results/launch'
import { spaceBrainKey } from '../src/quiet2/space/registry'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }

const ORIGIN = 'https://fixture.invalid'
const CORPUS = 'fixture-corpus'
const ONE = `${CORPUS}@instance-1`
const TWO = `${CORPUS}@instance-2`

/* -- what a binding answers, at each of its three states -------------------- */
{
  const b = createBinding()
  eq(servingKeyOf(b), null, 'a page that has not bound yet names no Brain')
  eq(brainVerdict(ONE, servingKeyOf(b)), 'unknown',
    'so nothing saved is replayed against it: unknown decides nothing, and decides it fail-closed')

  b.saw(ONE)
  eq(servingKeyOf(b), ONE, 'once an answer names a Brain, that is the Brain being served')
  eq(brainVerdict(ONE, servingKeyOf(b)), 'same', 'and this page’s own results are its own')
}
{
  /* F1: A MOVED PAGE HAS NO CURRENT BRAIN. `bound()` still answers with the
     Brain the page was OPENED on -- it must, because that is what its writes
     name -- and answering results with THAT is exactly what let every pending
     read and open chooser go on acting as though nothing had happened. */
  const b = createBinding()
  b.saw(ONE)
  b.saw(TWO)
  eq(b.moved(), true, 'another Brain answering moves the page (brainBinding.ts’s own rule)')
  eq(b.bound(), ONE, 'and what it is still bound to is the Brain it was opened on')
  eq(servingKeyOf(b), null, 'F1: SO WHAT IT IS SERVING IS NOT KNOWN, and `serving.ts` says so')
  eq(brainVerdict(ONE, servingKeyOf(b)), 'unknown',
    'F1: a result saved before the move is not resumed, and a late read is not placed')
}
{
  /* the server refusing a write as another Brain's (409 `BrainChanged`) moves
     the page the same way, and so empties the serving key the same way */
  const b = createBinding()
  b.saw(ONE)
  b.move()
  eq(servingKeyOf(b), null, 'a refused write moves the page, and a moved page serves nothing known')
}
{
  /* an answer that names NO Brain decides nothing either way */
  const b = createBinding()
  b.saw(ONE)
  b.saw(null)
  eq(servingKeyOf(b), ONE, 'an answer naming no Brain leaves the binding where it was')
}

/* -- F2: the key that was supplied instead ---------------------------------- */
{
  /* `useBrain` builds `brain.key` with exactly these fields. Two serving
     instances of one corpus at one origin are one graph key and two binding
     keys: that difference IS the finding. */
  const at = { corpusId: CORPUS, origin: ORIGIN, proxy: null }
  eq(spaceBrainKey(at), spaceBrainKey({ ...at }),
    'F2: the graph key is built from origin, proxy and corpus -- the serving instance is not among them')
  eq(brainVerdict(ONE, TWO), 'other-instance',
    'F2: while the keys `serving.ts` answers with tell those two instances apart')
  eq(brainVerdict(spaceBrainKey(at), spaceBrainKey({ ...at })), 'same',
    'F2: so a result saved against the replaced instance looked like this page’s own, judged by the graph key')
}

/* -- F3: "no Brain" IS TWO STATES, AND NEITHER OF THEM IS AN EXEMPTION ------
 *
 * (independent review adm-1cb30e65d05f.) `null` was true of a page that had
 * not bound yet and of a page that had moved, and every gate that mattered
 * read it as "nothing to compare" and acted: a launch MADE in either state
 * placed an artifact, navigated to a record, reported `opened` and was then
 * written into the history under whatever identity had answered meanwhile.
 * The states are distinct values now, and `mayAct` acts on one of the three. */
{
  const b = createBinding()
  eq(servingOf(b), { how: 'unconfirmed' }, 'F3: a page that has not bound yet CANNOT SAY -- not "no Brain to check"')
  eq(mayAct(null, servingOf(b)), 'unconfirmed',
    'F3: so an opening made then may not act, which is exactly what `launch.brainKey &&` used to let through')
  eq(mayAct(ONE, servingOf(b)), 'unconfirmed', 'and neither may one made against a Brain this page can no longer confirm')

  b.saw(ONE)
  eq(servingOf(b), { how: 'serving', key: ONE }, 'a confirmed answer is the Brain, by its whole key')
  eq(mayAct(ONE, servingOf(b)), 'act', 'an opening made against it acts: the preserved, ordinary case')
  eq(mayAct(null, servingOf(b)), 'unconfirmed',
    'F3: AND AN OPENING THAT NAMED NO BRAIN DOES NOT ACQUIRE THIS ONE by finishing after it was confirmed')
  eq(mayAct(TWO, servingOf(b)), 'other-instance', 'another instance of the same corpus is told apart, as before')
  eq(mayAct('other@i1', servingOf(b)), 'other-brain', 'and another corpus')

  b.saw(TWO)
  eq(servingOf(b), { how: 'moved' }, 'F3: and a moved page is MOVED, which is not the same answer as "not yet"')
  eq(mayAct(ONE, servingOf(b)), 'moved', 'nothing made before the move acts')
  eq(mayAct(null, servingOf(b)), 'moved', 'nor does an opening made after it that named no Brain')
  eq(servingKeyOf(b), null, 'while the KEY form still answers null for both, for the entry and the resume that hold one')
}
{
  /* THE READER IS TOLD WHICH, AND THE WORDS ARE THE ONES THE PAGE ALREADY USES
     for a write in that state (`brainBinding.ts` UNCONFIRMED): not sent, not
     opened, try again in a moment. No new rule -- the same direction, on the
     read side. */
  eq(actingWords('unconfirmed'), BRAIN_UNCONFIRMED, 'a page that cannot say says so, and says what to do about it')
  eq(actingWords('moved'), BRAIN_MOVED, 'a moved page is told to reload, as it already was')
  eq(actingWords('other-instance'), BRAIN_MOVED, 'and another instance reads as the move it is')
  eq(actingWords('unconfirmed') === actingWords('moved'), false, 'F3: the two states are not told to the reader as one')
}
{
  /* A CALLER THAT STILL ANSWERS WITH A KEY ALONE IS READ FAIL-CLOSED: omitting
     the state cannot reopen the bypass, which is how it was open to begin with. */
  eq(servingOfKey(ONE), { how: 'serving', key: ONE }, 'a key is a confirmed identity')
  eq(servingOfKey(null), { how: 'unconfirmed' }, 'F3: and no key is "cannot say", never "exempt"')
  eq(mayAct(null, servingOfKey(null)), 'unconfirmed', 'so a host that supplies neither refuses rather than opening')
}

/* -- and the page's own, which is the one the build uses -------------------- */
{
  /* THE REAL MODULE BINDING, not a made one: `servingBrainKey()` is what
     `mount.ts` calls when a host supplies no `serving`. Moving it is one-way,
     so this is the last case in the file. */
  eq(servingNow(), { how: 'unconfirmed' }, 'F3: the real page, before anything has answered, cannot say which Brain it is on')
  eq(servingBrainKey(), pageBinding.bound(), 'the page’s own key is its binding’s, before anything has moved')
  pageBinding.saw(ONE)
  eq(servingBrainKey(), ONE, 'binding the real page binding is what `servingBrainKey()` answers')
  eq(servingNow(), { how: 'serving', key: ONE }, 'and the real page is serving it')
  pageBinding.saw(TWO)
  eq(servingBrainKey(), null, 'F1/F2: and the real page, once moved, serves no Brain this page may act for')
  eq(servingNow(), { how: 'moved' }, 'F3: which the real page says as MOVED, so a press made now is refused and told')
}

console.log(`quiet2_result_serving_unit: ${checks} checks passed`)
