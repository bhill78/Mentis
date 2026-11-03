/* Presentation class and input mode (Surface Tension P5, plan §3.1 and §4 P5):
 * the 760/761/1024/1025 boundaries, input mode from mocked media queries,
 * and isNarrow keeping its meaning (every class but wide = max-width 1024). */
import assert from 'node:assert/strict'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }

/* The media queries, mocked before frame/narrow.ts reads them. */
let width = 1280
let coarse = false
const answers = (q: string): boolean => {
  if (q === '(max-width: 1024px)') return width <= 1024
  if (q === '(max-width: 760px)') return width <= 760
  if (q === '(pointer: coarse), (hover: none)') return coarse
  return false
}
const changeFns: (() => void)[] = []
;(globalThis as any).matchMedia = (q: string) => ({
  get matches() { return answers(q) }, media: q,
  addEventListener: (_e: string, fn: () => void) => { changeFns.push(fn) },
})
const narrow = await import('../src/fluid/frame/narrow')
const { presentationClass, classOf, inputModeOf, classNow, inputMode, isNarrow, remeasure, NARROW, COARSE, CLASS_QUERIES } = narrow

/* the pure rule, at each boundary */
eq([1025, 1024, 761, 760, 320, 1920].map(presentationClass), ['wide', 'medium', 'medium', 'compact', 'compact', 'wide'],
  'presentationClass: > 1024 wide, 761-1024 medium, <= 760 compact')

/* from media queries: the same class at each boundary */
for (const w of [1025, 1024, 761, 760, 500]) {
  width = w
  eq(classOf(answers), presentationClass(w), `classOf(media) at ${w} px is presentationClass(${w})`)
  eq(classNow(), presentationClass(w), `classNow() at ${w} px reads the mocked media`)
}
eq(CLASS_QUERIES, ['(max-width: 1024px)', '(max-width: 760px)'], 'the two class boundaries are the media queries listened to')

/* input mode, from mocked media queries */
eq([inputModeOf(() => true), inputModeOf(() => false)], ['coarse', 'fine'], 'inputModeOf: coarse where (pointer: coarse) or (hover: none) matches')
eq(COARSE, '(pointer: coarse), (hover: none)', 'coarse is a coarse pointer, or none that hovers')
coarse = true
eq(inputMode(), 'coarse', 'inputMode() reads a coarse pointer')
coarse = false
eq(inputMode(), 'fine', 'inputMode() reads a fine pointer')

/* isNarrow keeps its meaning: what NARROW (max-width 1024) matched before P5 */
eq(NARROW, '(max-width: 1024px)', 'NARROW is unchanged')
for (const w of [1280, 1025, 1024, 900, 761, 760, 375]) {
  width = w
  remeasure()
  eq(isNarrow(), answers(NARROW), `isNarrow() at ${w} px is what (max-width: 1024px) says`)
  eq(isNarrow(), presentationClass(w) !== 'wide', `and is presentationClass !== 'wide' at ${w} px`)
}

/* a class switch inside narrow (medium -> compact) is heard, as is the input changing */
width = 900
remeasure()
const before = changeFns.length
ok(before >= 3, 'the two class queries and the input query are listened to')
width = 700
changeFns.forEach((fn) => fn())
eq(classNow(), 'compact', 'medium -> compact is a class switch')
eq(isNarrow(), true, 'still narrow')
coarse = true
changeFns.forEach((fn) => fn())
eq(inputMode(), 'coarse', 'and input changing is heard')

function ok(v: unknown, what: string) { assert.ok(v, what); checks++ }

/* P4's interim surface/input.ts is gone: its readers use these hooks */
import('node:fs').then(({ readFileSync, existsSync }) => {
  const src = (p: string) => new URL('../src/fluid/' + p, import.meta.url)
  ok(!existsSync(src('surface/input.ts')), "P4's interim surface/input.ts is replaced by frame/narrow.ts")
  for (const f of ['surface/SurfaceChrome.tsx', 'focus/FloatingHeader.tsx', 'focus/NarrowFloats.tsx'])
    ok(readFileSync(src(f), 'utf8').includes("from '../frame/narrow'") && !readFileSync(src(f), 'utf8').includes('surface/input'), `${f} reads class and input from frame/narrow.ts`)
  console.log(`fluid presentation class: ${checks} checks passed`)
})
