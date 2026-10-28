import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { SPACE_HASH, atSpace } from '../src/surfaces/space/navigation'
import { sourcesPath } from '../src/surfaces/sources/navigation'
import { OBJECT_MIME, POST_MIME, brainRef, dragPayload, entryOfRef, goHome, isBrainRef, kindWord } from '../src/fluid/brain/address'
import { CONVERSATION_OVERLAY, STORE_KEY, closeOver, dockOver, loadOverlays, minimise, openOver, placeOver, readOverlays, saveOverlays, shownRect, toFront, type Overlays } from '../src/fluid/brain/overlays'

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

const shell = readSrc('fluid/Shell.tsx')
/* -- a conversation over the Brain: one place, floating or docked -------- */
const cA = { type: 'conversation' as const, conversation: 'cA', title: 'Alpha' }
const cB = { type: 'conversation' as const, conversation: 'cB', title: 'Beta' }
let c = openOver(openOver([], d1, room), cA, room)
eq(c.map((o) => o.id), ['entry:d1', CONVERSATION_OVERLAY], 'a conversation floats beside what is open')
c = dockOver(c, CONVERSATION_OVERLAY, 'right')
eq(c[1].dock, 'right', 'it docks as a column')
const before = { x: c[1].x, w: c[1].w }
c = openOver(c, cB, room)
eq([c.length, c.at(-1)?.shows, c.at(-1)?.dock], [2, cB, 'right'], 'another conversation takes the one place, where it was')
c = dockOver(c, CONVERSATION_OVERLAY, null)
eq([c.at(-1)?.dock, c.at(-1)?.x, c.at(-1)?.w], [undefined, before.x, before.w], 'floated again, it is where it last floated')
c = minimise(c, CONVERSATION_OVERLAY)
ok(c.some((o) => o.id === CONVERSATION_OVERLAY && o.min), 'put away, the conversation is still over the Brain')
eq(closeOver(c, CONVERSATION_OVERLAY).map((o) => o.id), ['entry:d1'], 'closed, only its surface goes')
for (let i = 0; i < 20; i++) c = openOver(c, { ...d1, entry: 'x' + i }, room)
ok(c.some((o) => o.id === CONVERSATION_OVERLAY), 'the conversation never gives way to objects')
eq(readOverlays(JSON.stringify(dockOver(openOver([], cA, room), CONVERSATION_OVERLAY, 'left')))[0].dock, 'left', 'docked comes back docked')

const place = readSrc('fluid/brain/BrainPlace.tsx')
ok(/<Mount id=\{CONVERSATION_ID\} \/>/.test(place), 'the real conversation column is moved into the surface')
ok(!/ConversationColumn|PostCard|StreamColumn/.test(place.replace(/\/\*[\s\S]*?\*\//g, '')), 'no second conversation view is built here')
ok(/<Hosted id=\{CONVERSATION_ID\}>/.test(shell.slice(shell.indexOf("{view === 'space' ? ("), shell.indexOf(") : view === 'sources' ? ("))),
  'the Shell draws the one conversation for the Brain, as it does for its own column')
ok(/const place = view === 'home' \? homeConv : view === 'conversation' \|\| view === 'space' \? here : null/.test(shell),
  'posts in the conversation over the Brain act there (reply, include)')

/* -- carried out of the Brain: Fluid's own drop paths ----------------------- */
const keepSrc = readSrc('fluid/workspace/keep.tsx')
ok(keepSrc.includes(`export const DRAG = '${OBJECT_MIME}'`) && keepSrc.includes(`export const POST = '${POST_MIME}'`),
  'the Brain carries the very mimes the sections read')
const asMap = (p: [string, string][]) => Object.fromEntries(p)
const turnDrag = asMap(dragPayload({ entry: 't1', kind: 'contribution' }, 'http://x'))
eq(JSON.parse(turnDrag[POST_MIME]), { post: 't1' }, 'a Turn goes as a post: a section keeps what it is made of')
ok(!(OBJECT_MIME in turnDrag), '...and not as a Brain reference')
const decDrag = asMap(dragPayload({ entry: 'd1', kind: 'decision' }, 'http://x'))
eq(JSON.parse(decDrag[OBJECT_MIME]), { address: 'brain:d1', from: 'the 3D Brain' }, 'anything else goes as one object, by reference')
ok(!('text/uri-list' in decDrag), 'a decision is not offered as a file')
const admDrag = asMap(dragPayload({ entry: 'adm-0a1b', kind: 'admission' }, 'http://host:1'))
eq(admDrag['text/uri-list'], 'http://host:1/api/artifacts/adm-0a1b', 'acquired material is also the artifact the composer takes by reference')
eq([brainRef('e1'), entryOfRef('brain:e1'), entryOfRef('needs-you:e1'), isBrainRef('brain:')], ['brain:e1', 'e1', null, false],
  'the Brain address names its entry and nothing else')
const zonesSrc = readSrc('fluid/workspace/Zones.tsx')
ok(/slot\.items\.filter\(\(a\) => !isAsk\(a\) && !isBrainRef\(a\)\)/.test(zonesSrc), 'a section does not ask the post registry for a Brain address')
ok(/<BrainKept refs=\{fromBrain\}/.test(zonesSrc), 'a section draws what it keeps from the Brain')
const keptSrc = readSrc('fluid/brain/BrainKept.tsx').replace(/\/\*[\s\S]*?\*\//g, '')
ok(!/method:\s*'POST'|fluidFetch|store\.(keep|record|post|send)\(/.test(keptSrc + readSrc('fluid/brain/BrainPlace.tsx') + readSrc('fluid/brain/BrainObject.tsx')),
  'opening or moving a Brain object writes nothing to the record')
ok(/EntryInspect[^>]*readOnly/.test(keptSrc), 'kept, it is inspected read only')

/* -- the wiring: reached from the Brain menu, loaded only when gone to ---- */
ok(/lazy\(\(\) => import\('\.\/brain\/BrainPlace'\)\)/.test(shell), 'the 3D Brain is loaded lazily, outside the main bundle')
ok(!/^import .*surfaces\/space\/SpaceSurface/m.test(shell), 'the Shell never imports the drawing itself')
ok(/onSpace=\{openSpace\}/.test(shell), 'the Shell hands the Brain menu its door')
ok(/atSpace=\{view === 'space'\}/.test(readSrc('fluid/frame/TopBar.tsx')), 'the Brain menu says when you are in the 3D Brain')
ok(/onSpace=\{onSpace\}/.test(readSrc('fluid/frame/BarControls.tsx')), 'the Brand passes the door to the Brain menu')

console.log(`brain: ${checks} checks passed`)
