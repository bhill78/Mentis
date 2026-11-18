import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import type { SpaceRead } from '../src/surfaces/space/layout'
import {
  SPACE_OPENING,
  SPACE_VIEW_DEFAULTS,
  autoDistance,
  createSpaceSession,
  defaultCamera,
  framesItself,
  letsGoOfSelection,
  materialKey,
  spacePath,
  spaceSessionInside,
  type SpaceCamera,
} from '../src/surfaces/space/session'

/* ------------------------------------------------------------------------ *
 * ONE OPEN 3D BRAIN'S LIFETIME: what survives a remount, and what must not.
 *
 * The property these checks are about is the one that made the graph unusable
 * in a working column: moving it, maximising it or restoring it REMOUNTS the
 * renderer, and everything the renderer knew -- where the eye was, what was
 * chosen, what had been read -- lived in it. So: the view comes back exactly,
 * a move reads nothing, and nothing that is merely being restored is mistaken
 * for somebody choosing it.
 *
 * What is checked here is the decision, not the drawing. Whether the canvas
 * then paints the same pixels is browser evidence, and belongs to whoever
 * verifies the integrated candidate.
 * ---------------------------------------------------------------------- */

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const is = (a: unknown, b: unknown, what: string) => { assert.strictEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const here = fileURLToPath(new URL('.', import.meta.url))
const readSrc = (file: string) => readFileSync(here + '../src/' + file, 'utf8')
const bare = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')

const graph = (n: number): SpaceRead => ({
  nodes: Array.from({ length: n }, (_, i) => ({
    entry: `e${i}`, kind: 'decision', layer: 'how', conversation: 'c1',
    at: 100 + i, summary: `thing ${i}`, deleted: false, edited: false, replaced: false,
  })),
  edges: [],
  conversations: { c1: 'Alpha' },
  layers: ['how', 'that', 'said'],
  total: n,
  omitted: 0,
  cap: 6000,
  material: false,
})

/* -- the defaults are the ones Fluid always had --------------------------- */
eq({ ...SPACE_VIEW_DEFAULTS }, {
  selected: null, material: false, palette: 'none', allStrands: false,
  turns: true, options: false, asOf: null, playing: false,
}, 'an unbound surface opens on exactly what it always opened on')
eq({ ...SPACE_OPENING }, { turn: 0.6, rise: 0.42 }, 'the eye starts where it always started')
const fresh = defaultCamera()
eq([fresh.initialized, fresh.framing, fresh.zoomed, fresh.selectionRevision, [...fresh.walk]], [false, 'auto', false, 0, []],
  'an untouched camera says so: nothing is settled, nothing is held, nothing chosen')
eq([spacePath('records'), spacePath('material')], ['/api/space', '/api/space?material=1'],
  'the two reads are the two the surface always read, and no other')
eq([materialKey(false), materialKey(true)], ['records', 'material'], 'asking for acquired material is the other key')

/* -- framing: the container frames an untouched view, and only that ------- */
ok(framesItself({ framing: 'auto', zoomed: false }), 'nobody has touched it: the container may frame it')
ok(!framesItself({ framing: 'held', zoomed: false }), 'turned but not zoomed is still held: no re-fit')
ok(!framesItself({ framing: 'auto', zoomed: true }), 'zoomed is held however it got there')
is(autoDistance(300), 300 * 1.85, 'the auto distance is the canvas\'s own formula')
is(autoDistance(300, 400, 900), 300 * 1.85 * 1.4, 'a portrait field needs the eye further out')
is(autoDistance(300, 900, 400), 300 * 1.85, '...and a landscape one does not')

/* -- the session: what it tells, and what it keeps quiet ------------------ */
const s = createSpaceSession({ id: 'v1', brainKey: 'brain:here' })
const into = spaceSessionInside(s)
is(s.id, 'v1', 'it is the id the host gave it')
is(s.brainKey, 'brain:here', 'and it is bound to one Brain')
let told = 0
const stop = s.subscribe(() => { told += 1 })
const snap0 = s.getSnapshot()
is(s.getSnapshot(), snap0, 'the same snapshot until something changes')
eq([snap0.visible, snap0.disposed, snap0.read.key, snap0.read.data], [false, false, 'records', null],
  'nothing is visible, read or disposed before a host says so')

s.setView({ turns: true })
is(told, 0, 'setting what is already set tells nobody')
is(s.getSnapshot(), snap0, '...and the snapshot does not move')
s.setView({ palette: 'layer', allStrands: true })
is(told, 1, 'a real change is one notification')
is(s.getSnapshot().view.palette, 'layer', 'and it is in the snapshot')
;(s.setView as (p: Record<string, unknown>) => void)({ selected: 'e3' })
is(s.getSnapshot().view.selected, null, 'the selection is not settable through setView: it is an act, not a field')

/* -- choosing travels; reconciling does not ------------------------------- */
const rev = () => s.getCamera().selectionRevision
s.select('e1', 'user')
is(rev(), 1, 'a choice carries a revision, which is what the eye flies for')
s.select('e1', 'user')
is(rev(), 1, 'choosing what is already chosen is not a second flight')
s.select('e2', 'reconcile')
is(rev(), 1, 'reconciling moves the selection and nothing else')
is(s.getSnapshot().view.selected, 'e2', '...and it really does move it')
s.select(null, 'reconcile')
is([rev(), s.getSnapshot().view.selected][0], 1, 'letting go of something no longer drawn is not a choice either')
s.select(null, 'user')
is(rev(), 1, 'nothing changed, so nothing is owed a flight')
s.select('e4', 'user')
is(rev(), 2, 'the next real choice is the next revision')

/* -- the camera is a value, kept outside what renders --------------------- */
const mine: SpaceCamera = {
  initialized: true, framing: 'held', zoomed: true,
  eye: { turn: 1.2345, rise: -0.5, out: 123.456, at: { x: 7, y: -8, z: 9 } },
  walk: ['e1', 'e2'], selectionRevision: 2,
}
const quiet = told
s.saveCamera(mine)
is(told, quiet, 'saving a camera frame tells nobody: a pointer frame must not render the page')
is(s.getSnapshot(), s.getSnapshot(), '...and the snapshot it would render from has not moved')
const back = s.getCamera()
eq(back, mine, 'what was saved comes back exactly')
ok(back !== mine && back.eye !== mine.eye && back.eye.at !== mine.eye.at && back.walk !== mine.walk,
  'both ways are copies: neither side can reach into the other\'s camera')
mine.eye.out = 0
is(s.getCamera().eye.out, 123.456, 'changing the caller\'s copy afterwards changes nothing kept')

/* -- A REMOUNT IS NOT A RE-FRAMING. The renderer's own hydration rule, run
      in the order it runs in: read the camera, and only re-fit it if nobody
      has taken hold of the eye. ------------------------------------------- */
const hydrate = (camera: SpaceCamera, radius: number): SpaceCamera => {
  if (!camera.initialized && camera.eye.out === 0) camera.eye.out = autoDistance(radius)
  if (framesItself(camera)) camera.eye.out = autoDistance(radius)
  return camera
}
const heldEye = hydrate(s.getCamera(), 980).eye
eq(heldEye, { turn: 1.2345, rise: -0.5, out: 123.456, at: { x: 7, y: -8, z: 9 } },
  'remounted in a bigger host, a held eye is exactly where it was left')
const auto = hydrate({ ...defaultCamera() }, 980)
is(auto.eye.out, autoDistance(980), 'an untouched eye is still framed by what it is drawn in')
const rotated = hydrate({ ...defaultCamera(), framing: 'held', eye: { turn: 2, rise: 0.1, out: 500, at: { x: 0, y: 0, z: 0 } }, initialized: true }, 980)
is(rotated.eye.out, 500, 'turned-only is held too: a move does not push the eye back out')

/* -- the read: two keys, each retaining its own last good answer ---------- */
const a = graph(3)
const b = graph(9)
into.publish('records', { data: a, loading: false, error: null })
is(s.getSnapshot().read.data, a, 'what settled is what is drawn')
is(s.getSnapshot().read.key, 'records', '...under its own key')
s.setView({ material: true })
eq([s.getSnapshot().read.key, s.getSnapshot().read.data], ['material', null],
  'asked for acquired material, the records answer is NOT shown as though it were that answer')
into.publish('material', { data: b, loading: false })
is(s.getSnapshot().read.data, b, 'the material answer is drawn once it lands')
s.setView({ material: false })
is(s.getSnapshot().read.data, a, 'toggled back, the retained records answer is there at once -- no re-read to look at it')
eq(into.retained('material').data, b, '...and the material answer is still retained for its own key')

const beforeQuiet = into.told()
into.publish('material', { data: graph(11) })
is(into.told(), beforeQuiet, 'an answer for the key nobody is looking at notifies nobody')
is(s.getSnapshot().read.data, a, '...and does not touch what is drawn')

into.publish('records', { error: 'the server said no' })
eq([s.getSnapshot().read.data, s.getSnapshot().read.error], [a, 'the server said no'],
  'a failed re-read keeps the last good answer for its key AND says it failed')
into.publish('records', { data: graph(4), error: null })
is(s.getSnapshot().read.error, null, 'a later good read clears its own error')

/* -- letting go of a selection, and when that is not evidence -------------- */
ok(!letsGoOfSelection({ selected: 'e1', settled: false, drawn: false, hiddenLayer: false }),
  'an answer that has not landed is not evidence that a thing has gone')
ok(letsGoOfSelection({ selected: 'e1', settled: true, drawn: false, hiddenLayer: false }),
  'gone from a read that landed is gone')
ok(letsGoOfSelection({ selected: 'e1', settled: true, drawn: true, hiddenLayer: true }),
  'a selection in a layer somebody turned off is let go, as it always was')
ok(!letsGoOfSelection({ selected: 'e1', settled: true, drawn: true, hiddenLayer: false }), 'otherwise it is kept')
ok(!letsGoOfSelection({ selected: null, settled: true, drawn: false, hiddenLayer: false }), 'nothing chosen, nothing to let go of')

/* -- hidden, parked, detached: the clock stops and does not restart ------- */
s.setView({ asOf: 1234, playing: true })
s.setVisible(true)
eq([s.getSnapshot().visible, s.getSnapshot().view.playing], [true, true], 'drawn and playing')
s.setVisible(false)
eq([s.getSnapshot().visible, s.getSnapshot().view.playing, s.getSnapshot().view.asOf], [false, false, 1234],
  'parked: the clock stops where it is, and the moment is kept')
s.setVisible(true)
is(s.getSnapshot().view.playing, false, 'coming back does not start playing again, and does not catch up')
s.setView({ playing: true })
is(s.getSnapshot().view.playing, true, 'only pressing Play plays')

/* -- one renderer, and detaching is not disposing ------------------------- */
const release = s.attachRenderer()
ok(into.attached(), 'the canvas that attached is the one drawing it')
const second = s.attachRenderer()
is(into.attached(), true, 'a second canvas does not take the session from the first')
second()
is(into.attached(), true, '...and letting go of a refused attachment detaches nothing')
release()
is(into.attached(), false, 'the renderer let go')
is(s.getSnapshot().view.playing, false, 'detaching stops the clock too')
eq([s.getSnapshot().disposed, s.getSnapshot().read.data !== null, s.getCamera().eye.out], [false, true, 123.456],
  'DETACHED IS NOT DISPOSED: the read and the camera are still here to come back to')
release()
is(into.attached(), false, 'letting go twice is harmless')

/* -- disposal: once, and late callbacks reach nothing --------------------- */
const atDispose = told
s.dispose()
is(told, atDispose + 1, 'disposal is said once')
eq([s.getSnapshot().disposed, s.getSnapshot().visible, s.getSnapshot().read.data], [true, false, null],
  'disposed: not visible, holding no read')
s.dispose()
is(told, atDispose + 1, 'disposing again says nothing: it is idempotent')
into.publish('records', { data: graph(2) })
s.select('e9', 'user')
s.setView({ palette: 'conversation' })
s.saveCamera(defaultCamera())
eq([s.getSnapshot().read.data, s.getSnapshot().view.selected, s.getSnapshot().view.palette], [null, 'e4', 'layer'],
  'a result, a choice or a frame arriving after disposal changes nothing')
is(s.getCamera().eye.out, 123.456, '...the camera it was disposed with is not overwritten either')
is(s.attachRenderer()(), undefined, 'attaching to a disposed session is a no-op that is safe to release')
stop()

/* -- the pieces only the renderer can do, read in the source -------------- */
const surface = readSrc('surfaces/space/SpaceSurface.tsx')
const canvas = readSrc('surfaces/space/BrainSpace.tsx')
const reader = readSrc('surfaces/space/SpaceSessionReader.tsx')

ok(!/\buseApi\b/.test(surface), 'the frame no longer reads the Brain itself: the reader does')
ok(/\{own && <SpaceSessionReader session=\{own\} \/>\}/.test(surface),
  'a reader is mounted here ONLY when no host supplied a session')
ok(/useSyncExternalStore\(live\.subscribe, live\.getSnapshot\)/.test(surface),
  'the frame renders from the session\'s snapshot, which is stable until something changes')
ok(/live\.select\(id, 'user'\)/.test(surface) && /live\.select\(null, 'reconcile'\)/.test(surface),
  'a click is a choice and a vanished selection is a reconciliation, and the surface says which')
ok(/settled: data !== null/.test(surface), 'nothing is reconciled against an answer that has not landed')
ok(!/id="space-options"/.test(surface) && !/name="space-palette"/.test(surface),
  'the options panel and its radios are this surface\'s own, not the document\'s')
ok(/useId\(\)/.test(surface), '...which is what gives them their names')
ok(/spacing: 5000/.test(reader) && /spacePath\(key\)/.test(reader),
  'the reader is the reader it always was: the same path at the same spacing')
ok(/<KeyReader key=\{key\}/.test(reader), 'one mount per material key, so no answer is labelled with the other key')
ok(!/setInterval|setTimeout|new Map|cache/i.test(bare(reader)), 'it polls nothing and caches nothing')

const hydration = bare(canvas).indexOf('kept.current')
ok(hydration > 0 && hydration < bare(canvas).indexOf('useEffect('),
  'the camera is hydrated during the first render -- before any effect, observer or paint can overwrite it')
ok(/if \(framesItself\(state\.camera\)\) E\.out =/.test(canvas),
  'a paint re-fits the distance only while nobody has taken hold of the eye')
ok(!/if \(!zoomed\.current\) E\.out/.test(canvas), '...and not on the zoom flag alone, which rotating never set')
ok(/const revision = state\.camera\.selectionRevision\s*\n\s*if \(revision === state\.consumed\) return/.test(canvas),
  'the eye flies for a choice and not for a remount, a re-read or a new index')
ok(/state\.consumed = revision/.test(canvas), '...and a flight is marked flown before it starts')
ok(/index\.current\.get\(selected\)/.test(canvas) && /painter\.current\(\)/.test(canvas),
  'a flight in progress reads where things are, and how to draw them, as they are now')
ok(/\/\/ eslint-disable-next-line react-hooks\/exhaustive-deps\n\s*\}, \[selected\]\)/.test(canvas),
  '...so a re-read or a resize in the middle of a flight neither restarts nor cancels it')
ok(/session\.attachRenderer\(\)/.test(canvas) && /keep\(\)\s*\n\s*release\(\)/.test(canvas),
  'the renderer attaches, and checkpoints the camera before it lets go')
ok(/&& watched$/m.test(canvas), 'nothing animates while nobody is looking at it')
ok(/state\.camera\.framing = 'held'/.test(canvas), 'taking hold of the eye is recorded as that')

const css = readSrc('surfaces/space/space.css')
ok(/container-name: space/.test(css), 'the field is its own container')
ok(!/@container app/.test(css), 'what floats over the Brain no longer asks the app how wide the Brain is')
ok(!/100vw/.test(css), '...nor the window')
ok(/@container space \(max-width: 380px\)/.test(css), 'a working column has its own rules')
ok(/100cqi/.test(css), 'the options panel is as wide as there is room for here')

console.log(`space session: ${checks} checks passed`)
