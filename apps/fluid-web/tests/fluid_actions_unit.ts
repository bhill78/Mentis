/* W7: ONE ACTION ROW EVERYWHERE; OPEN, PEEK AND FOCUS DISTINCT.
 *
 * Where Open goes for each kind of address, the row's one order, and -- by
 * reading the source -- that the places which drew their own buttons now
 * draw the shared row, and that no ⤢ is left that opens a detail. */
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { ACTION_ORDER, openRoute } from '../src/fluid/objects/route'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')

/* -- Open, per kind of address ------------------------------------------------ */
eq(openRoute('post:p-123'), { to: 'post', id: 'p-123' }, 'a whole post opens as the post read in its context')
eq(openRoute('brain:ent-9f'), { to: 'brain', entry: 'ent-9f' }, "a Brain entry opens in the record's inspector")
eq(openRoute('live:p-1:chart#0'), { to: 'object', address: 'live:p-1:chart#0' }, 'a live object opens its detail')
eq(openRoute('exact:v1:0:chart#0'), { to: 'object', address: 'exact:v1:0:chart#0' }, 'an exact object opens its detail')
eq(openRoute('post:'), { to: 'object', address: 'post:' }, 'a bare prefix is not a post')
eq(openRoute('brain:'), { to: 'object', address: 'brain:' }, 'a bare prefix is not a Brain entry')

/* -- the one order ----------------------------------------------------------------- */
eq([...ACTION_ORDER], ['open', 'peek', 'float', 'keep', 'primary', 'focus'], 'Open · Peek · Float · Keep · ◎ · ⛶')
const row = read('fluid/objects/ObjectActions.tsx')
ok(row.includes('ACTION_ORDER.filter') && !/const ORDER\b/.test(row), 'the row draws the shared order, not its own')
ok(row.includes("a === 'open' && onOpen"), "a place's own Open replaces act.open only for Open")

const actions = read('fluid/objects/actions.ts')
ok(/open: \{ icon: '◨', label: 'Open', says: 'Open details: the full view, with its own navigation' \}/.test(actions), 'Open looks like ◨ with its words in the tooltip')
ok(actions.includes('open: (t) => impl.open(t)') && actions.includes('open: (t) => openTarget(t)'), 'act.open goes through the provided implementation')
ok(/openObject\(r\.address, t\.anchor \?\? null\)/.test(actions), 'an object opens with openObject out of its anchor')
ok(!/⤢/.test(actions), 'the action set has no ⤢')

/* -- every origin draws the row ------------------------------------------------------ */
const origins = [
  'fluid/present/Present.tsx', 'fluid/conversation/Grip.tsx', 'fluid/render/post.tsx',
  'fluid/brain/BrainKept.tsx', 'fluid/brain/BrainObject.tsx', 'fluid/frame/BarControls.tsx',
  'fluid/search-in/FocusSearch.tsx', 'fluid/present/viewer.tsx',
  'fluid/focus/LensLayer.tsx', 'fluid/conversation/Carries.tsx', 'fluid/sections/ContentsView.tsx',
  'fluid/render/ObjectRefPart.tsx',
]
for (const f of origins) ok(read(f).includes('<ObjectActions'), `${f} draws the one action row`)

const present = read('fluid/present/Present.tsx')
ok(!present.includes("data-act=\"peek\"") && !present.includes("data-act=\"open\""), 'a section card has no hand-made Peek or Open')
ok(!present.includes("'Keep…'"), "a section card's Keep is the row's ◆")
ok(!/isViewable\(o\)\) inspect\(/.test(present), 'a click on a picture card opens its detail; Peek is ◱')
ok(present.includes('onOpen={() => go()}'), "a card's Open is the card's own click")

const post = read('fluid/render/post.tsx')
ok(/address: 'post:' \+ post\.id/.test(post) && post.includes("only={['peek', 'focus']}"), "a post's toolbar leaves Open to the card and keeps Peek and Focus for post:<id>")
const postCard = read('fluid/conversation/PostCard.tsx')
ok(postCard.includes('nav.read(a.readIn, id, post.number)'), "a post's card click and keyboard action still read it")

const viewer = read('fluid/present/viewer.tsx')
ok(!viewer.includes('data-act="inworkspace"'), "Peek's ⊡ In the workspace is now the row's ◨ Open")
ok(viewer.includes("['open', 'float', 'keep', 'primary', 'focus']"), 'Peek offers Open, never itself')

const floats = read('fluid/focus/Floats.tsx')
const floatingHeader = read('fluid/focus/FloatingHeader.tsx')
/* owner feedback, round 2: one window chrome; Surface Tension P4: that chrome is SurfaceChrome, whose
   ⚙ lists Dock (dockBack, lent by chromeHosts windowHost) and whose × is Close */
ok(floats.includes('dockBack: dock') && floats.includes('<FloatingFrame') && /<SurfaceChrome /.test(floatingHeader)
  && read('fluid/surface/chromeHosts.ts').includes('h.dock = { run: w.dockBack'),
  'every float uses the shared window frame and its menu keeps dock back')

/* -- no ⤢ opens a detail; each ⤢ left says it enlarges ------------------------------- */
function tsx(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = dir + '/' + n
    return statSync(p).isDirectory() ? tsx(p) : /\.tsx$/.test(n) ? [p] : []
  })
}
const ENLARGES = /Full screen|in place|Open it here|Conversation focus|full screen/
let drawn = 0
for (const file of tsx(src + 'fluid')) {
  const lines = readFileSync(file, 'utf8').replace(/\r\n/g, '\n').split('\n')
  lines.forEach((line, i) => {
    if (!/['>{]⤢|⤢['<}]/.test(line) || line.trim().startsWith('*') || line.trim().startsWith('//')) return
    drawn++
    const near = lines.slice(Math.max(0, i - 3), i + 2).join('\n')
    const where = `${file.slice(src.length)}:${i + 1}`
    ok(!/openObject\(|inspect\(|act\.open|data-act="open"/.test(near), `${where}: ⤢ does not open a detail`)
    ok(ENLARGES.test(near), `${where}: ⤢ says it enlarges in place or full screen`)
  })
  const text = lines.join('\n')
  ok(!/data-act="open"/.test(text), `${file.slice(src.length)}: no hand-made Open button bypasses act`)
}
ok(drawn >= 4, 'the ⤢ left are the full screens and in-place expansions')

/* openObject is called only where Open is implemented or a section opens its own */
for (const file of tsx(src + 'fluid')) {
  const rel = file.slice(src.length).replace(/\\/g, '/')
  if (/openObject\(/.test(readFileSync(file, 'utf8'))) ok(['fluid/workspace/Zones.tsx'].includes(rel), `${rel}: calls openObject only as a section's own Open`)
}

console.log(`fluid actions: ${checks} checks passed`)
