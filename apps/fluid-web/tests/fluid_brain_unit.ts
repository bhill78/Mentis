import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { SPACE_HASH, atSpace } from '../src/surfaces/space/navigation'
import { sourcesPath } from '../src/surfaces/sources/navigation'
import { goHome, kindWord } from '../src/fluid/brain/address'
import { STORE_KEY, closeOver, loadOverlays, minimise, openOver, placeOver, readOverlays, saveOverlays, shownRect, toFront, type Overlays } from '../src/fluid/brain/overlays'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const here = fileURLToPath(new URL('.', import.meta.url))
const readSrc = (file: string) => readFileSync(here + '../src/' + file, 'utf8')

/* -- the address: Mark IV's, beside Manage Sources' ----------------------- */
eq(SPACE_HASH, '#/brain/space', 'the 3D Brain keeps Mark IV\'s address')
ok(atSpace('#/brain/space') && atSpace('#/brain/space/'), 'the 3D Brain is addressable')
ok(!atSpace('#/brain/sources') && !atSpace('') && !atSpace('#/brain'), 'another Brain surface is not the 3D Brain')
eq(sourcesPath(SPACE_HASH), null, 'the 3D Brain is not read as Manage Sources')

/* -- where a thing lives -------------------------------------------------- */
const went: string[] = []
const doors = { openPost: (c: string, p: string) => went.push(`post ${c} ${p}`), openConversation: (c: string) => went.push(`conv ${c}`) }
ok(goHome({ entry: 't1', kind: 'contribution', conversation: 'c1' }, doors), 'a Turn has a home')
ok(goHome({ entry: 'c2', kind: 'conversation', conversation: 'c2' }, doors), 'a Conversation is its own home')
ok(goHome({ entry: 'd1', kind: 'decision', conversation: 'c3' }, doors), 'a Decision lives in its Conversation')
ok(!goHome({ entry: 'p1', kind: 'participant', conversation: null }, doors), 'what the record places nowhere goes nowhere')
eq(went, ['post c1 t1', 'conv c2', 'conv c3'], 'each goes where it lives')
eq(kindWord({ kind: 'contribution' }), 'turn', 'a contribution is called a turn')
eq(kindWord({ kind: 'decision' }), 'decision', 'any other kind keeps its own name')

/* -- what floats over the Brain: this tab's view state ------------------- */
const room = { w: 1200, h: 800 }
const d1 = { type: 'entry' as const, entry: 'd1', kind: 'decision', conversation: 'c1', title: 'Use SQLite' }
const t1 = { type: 'entry' as const, entry: 't1', kind: 'contribution', conversation: 'c1', title: 'hello' }
let l: Overlays = openOver([], d1, room)
eq(l.map((o) => o.id), ['entry:d1'], 'opening a thing floats it')
ok(l[0].x >= 0 && l[0].x + l[0].w <= room.w && l[0].y >= 0 && l[0].y + l[0].h <= room.h, 'it opens inside the field')
l = openOver(l, t1, room)
eq(l.map((o) => o.id), ['entry:d1', 'entry:t1'], 'several stay open together, the newest in front')
ok(l[0].x !== l[1].x || l[0].y !== l[1].y, 'a second does not land on the first')
const moved = placeOver(l, 'entry:d1', { x: 40, y: 50, w: 10, h: 10 })
eq([moved[0].x, moved[0].y, moved[0].w >= 220, moved[0].h >= 120], [40, 50, true, true], 'moved and sized, never smaller than a Focus float')
l = openOver(moved, d1, room)
eq(l.map((o) => o.id), ['entry:t1', 'entry:d1'], 'opening one already open brings it forward')
eq([l[1].x, l[1].y], [40, 50], '...where it was left')
l = minimise(l, 'entry:d1')
ok(l.find((o) => o.id === 'entry:d1')?.min, 'put away, it stays open')
l = minimise(l, 'entry:d1', false)
eq([l.at(-1)?.id, l.at(-1)?.min], ['entry:d1', false], 'brought back, in front')
eq(toFront(l, 'entry:t1').map((o) => o.id), ['entry:d1', 'entry:t1'], 'pressed, a surface comes to the front')
eq(closeOver(l, 'entry:t1').map((o) => o.id), ['entry:d1'], 'closing one leaves the others')
let many: Overlays = []
for (let i = 0; i < 20; i++) many = openOver(many, { ...d1, entry: 'e' + i }, room)
eq(many.length, 12, 'no more than Focus allows')
eq(many[0].id, 'entry:e8', 'the oldest give way')
eq(shownRect({ ...l[0], x: 5000, y: 5000 }, room).x <= room.w - 120 && shownRect({ ...l[0], x: 5000, y: 5000 }, room).y <= room.h - 36, true,
  'a surface left off the field after a resize is drawn back within reach')

/* kept for the tab, under its own key, read back tolerantly */
const kept = new Map<string, string>()
const storage = { getItem: (k: string) => kept.get(k) ?? null, setItem: (k: string, v: string) => { kept.set(k, v) }, removeItem: (k: string) => { kept.delete(k) } }
saveOverlays(storage, l)
eq([...kept.keys()], [STORE_KEY], 'only the Brain\'s own key is written')
ok(!/workspace|layout|arrangement/i.test(STORE_KEY), 'it is not a conversation\'s arrangement')
eq(loadOverlays(storage), l, 'what was open comes back in this tab')
saveOverlays(storage, [])
eq(kept.size, 0, 'nothing open, nothing kept')
eq(readOverlays('not json'), [], 'unreadable view state is left, not guessed')
eq(readOverlays(JSON.stringify([{ id: 'entry:x', shows: { type: 'entry', entry: 'y', kind: 'k', conversation: null, title: 't' }, x: 0, y: 0, w: 300, h: 200 }])), [],
  'a surface whose id does not match what it shows is dropped')
ok(!/sessionStorage|localStorage|workspace\./.test(readSrc('fluid/brain/overlays.ts').replace(/\/\*[\s\S]*?\*\//g, '')), 'the model touches no storage but the one it is handed')
ok(/sessionStorage/.test(readSrc('fluid/brain/BrainPlace.tsx')) && !/workspace\.(edit|live|quiet)/.test(readSrc('fluid/brain/BrainPlace.tsx')),
  'overlays are kept for the tab and never edit the workspace')

/* -- the wiring: reached from the Brain menu, loaded only when gone to ---- */
const shell = readSrc('fluid/Shell.tsx')
ok(/lazy\(\(\) => import\('\.\/brain\/BrainPlace'\)\)/.test(shell), 'the 3D Brain is loaded lazily, outside the main bundle')
ok(!/^import .*surfaces\/space\/SpaceSurface/m.test(shell), 'the Shell never imports the drawing itself')
ok(/onSpace=\{openSpace\}/.test(shell), 'the Shell hands the Brain menu its door')
ok(/atSpace=\{view === 'space'\}/.test(readSrc('fluid/frame/TopBar.tsx')), 'the Brain menu says when you are in the 3D Brain')
ok(/onSpace=\{onSpace\}/.test(readSrc('fluid/frame/BarControls.tsx')), 'the Brand passes the door to the Brain menu')

console.log(`brain: ${checks} checks passed`)
