import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { columnZone, dockBack, dockFloat, floatObject, floatOut, locate, makePrimary, primaryOf, swapBack } from '../src/fluid/focus/model'
import { fromLayout, toLayout, type Arr } from '../src/fluid/workspace/place'
import { findZone, keepSlot, zones, type Node, type Zone } from '../src/fluid/workspace/tree'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const here = fileURLToPath(new URL('.', import.meta.url))
const readSrc = (file: string) => readFileSync(here + '../src/' + file, 'utf8')
const z = (id: string, name = id): Zone => ({ type: 'zone', id, show: 'objects', name, slot: keepSlot() })
const arr = (tree: Node, focus?: Arr['focus']): Arr => ({ tree, pages: [], ...(focus ? { focus } : {}) })

/* Leaf focus is an exact two-record rewrite: geometry and everyone else stay. */
const tree: Node = { type: 'split', dir: 'row', sizes: [.2, .3, .5], kids: [z('a'), z('b'), z('c')] }
const focused = makePrimary(arr(tree, { primary: 'a' }), 'c')
eq(zones(focused.tree).map((x) => x.id), ['c', 'b', 'a'], 'only the selected and primary leaves trade records')
eq((focused.tree as any).sizes, [.2, .3, .5], 'every share is unchanged')
eq(findZone(focused.tree, 'b'), z('b'), 'the other leaf is unchanged')
eq(primaryOf(focused), 'c', 'the incoming content is primary')
eq(primaryOf(swapBack(focused)), 'a', 'Esc restores the previous primary')

/* Float focus swaps content, never the floating place's rectangle. */
const floated = floatObject(arr(z('stage')), 'live:p:k', 'Survey', { x: 31, y: 42, w: 333, h: 222 })
const fl = floated.focus!.floats![0]
const first = makePrimary(floated, fl.zone.id)
eq(first.focus!.floats![0].zone.id, 'conv', 'the old primary occupies the float')
eq(({ ...first.focus!.floats![0], zone: undefined, id: undefined }), ({ ...fl, zone: undefined, id: undefined }), 'the float rectangle is exact')
eq(columnZone(first).name, 'Survey', 'the floating content occupies the primary column')
const again = makePrimary(first, first.focus!.floats![0].zone.id)
eq(columnZone(again).id, 'conv', 'pressing the same floating window swaps back')
eq(again.focus!.floats![0].zone.name, 'Survey', 'and restores its content')

/* Column and leaf exchange records in place. */
const columnLeaf = makePrimary(arr(z('leaf'), { column: { ...z('special'), show: 'conversation' }, primary: 'special' }), 'leaf')
eq(columnZone(columnLeaf).id, 'leaf', 'leaf content moves to the column')
eq((columnLeaf.tree as Zone).id, 'special', 'column content moves to the same leaf position')

/* Dock back restores the pair's original share. */
const pair = arr({ type: 'split', dir: 'row', sizes: [.3, .7], kids: [z('left'), z('right')] })
const out = floatOut(pair, 'left', { x: 5, y: 6, w: 300, h: 200 })
const back = dockBack(out, out.focus!.floats![0].id)
ok(Math.abs((back.tree as any).sizes[0] - .3) < 1e-12 && Math.abs((back.tree as any).sizes[1] - .7) < 1e-12, 'dock back restores the removed pair share')
eq(zones(back.tree).map((x) => x.id), ['left', 'right'], 'dock back restores its side')

/* Object centre keeps its live address and closes only that float. */
const target = arr({ ...z('target'), slot: keepSlot() })
const obj = floatObject(target, 'live:p:k', 'One', { x: 0, y: 0, w: 220, h: 120 })
const kept = dockFloat(obj, obj.focus!.floats![0].id, 'target', 'center')
eq((kept.tree as Zone).slot!.items, ['live:p:k'], 'centre keeps the object in the target')
eq(kept.focus?.floats ?? [], [], 'the object float closes')

/* Layout persistence round-trips focus and drops collisions/garbage. */
const layout = toLayout(first)
eq(toLayout(fromLayout(layout)!), layout, 'focus round-trips through storage')
const bad = structuredClone(layout) as any
bad.focus.floats.push({ id: 'stage', zone: z('stage'), x: 0, y: 0, w: 1, h: 1 })
const read = fromLayout(bad)!
eq(read.focus!.floats!.length, 1, 'a float colliding with tree content is dropped')
ok(locate(read, primaryOf(read)), 'the restored primary names present content')

/* Problem F: Floating-window appearance tokens and boundaries. */
const themeCss = readSrc('theme.css')
ok(themeCss.includes('--float-shadow:') && themeCss.includes('--float-border:'), 'theme.css defines float shadow and border tokens on :root')
ok(themeCss.includes('--float-shadow-front:') && themeCss.includes('--float-border-front:'), 'theme.css defines active front float tokens')
ok(themeCss.includes('--float-blur:') && themeCss.includes('--float-bg:'), 'theme.css defines float blur and background tokens')

const floatsCss = readSrc('fluid/focus/floats.css')
ok(floatsCss.includes('var(--surface-raised)') && floatsCss.includes('.fl-head'), 'floats.css uses raised surface token for the float header')
ok(floatsCss.includes('var(--float-border'), 'floats.css applies distinct float border with contrast')
ok(floatsCss.includes('var(--float-shadow'), 'floats.css applies deep float shadow')
ok(floatsCss.includes('.wk-float.front') && floatsCss.includes('--float-border-front'), 'floats.css marks front active window with accent emphasis')
ok(floatsCss.includes('backdrop-filter: blur(var(--float-blur'), 'floats.css ensures floats always blur')

/* Problem D: Window toolbar consolidation and layout. */
const treeCss = readSrc('fluid/workspace/tree.css')
ok(!treeCss.includes('.wk-zcap .wt-tools { position: absolute; right: 40px'), 'tree.css avoids absolute right: 40px positioning that overlaps toolbar controls')
ok(treeCss.includes('@container (max-width: 380px)'), 'tree.css provides container query for narrow caption consolidation')

const workspaceCss = readSrc('fluid/workspace/workspace.css')
ok(workspaceCss.includes('container-type: inline-size;'), 'workspace.css establishes container context on .wk-zcap')

const searchInCss = readSrc('fluid/search-in/search-in.css')
ok(searchInCss.includes('border-bottom: 1px solid var(--line);'), 'search-in.css styles search bar as a separate row')

console.log(`fluid focus: ${checks} checks passed`)
