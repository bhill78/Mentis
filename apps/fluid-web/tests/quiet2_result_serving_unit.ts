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
import { servingBrainKey, servingKeyOf } from '../src/quiet2/results/serving'
import { createBinding, page as pageBinding } from '../src/brainBinding'
import { brainVerdict } from '../src/quiet2/results/launch'
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

/* -- and the page's own, which is the one the build uses -------------------- */
{
  /* THE REAL MODULE BINDING, not a made one: `servingBrainKey()` is what
     `mount.ts` calls when a host supplies no `serving`. Moving it is one-way,
     so this is the last case in the file. */
  eq(servingBrainKey(), pageBinding.bound(), 'the page’s own key is its binding’s, before anything has moved')
  pageBinding.saw(ONE)
  eq(servingBrainKey(), ONE, 'binding the real page binding is what `servingBrainKey()` answers')
  pageBinding.saw(TWO)
  eq(servingBrainKey(), null, 'F1/F2: and the real page, once moved, serves no Brain this page may act for')
}

console.log(`quiet2_result_serving_unit: ${checks} checks passed`)
