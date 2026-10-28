import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { columnZone, dockBack, dockFloat, floatObject, floatOut, locate, makePrimary, moveFloat, primaryOf, swapBack, tidyFloats, updateFloatSlot } from '../src/fluid/focus/model'
import { fromLayout, toLayout, type Arr } from '../src/fluid/workspace/place'
import { THIS_POST, allPageViews, onPage, pageView } from '../src/fluid/focus/page'
import { findZone, fitMeasureKey, keepSlot, zones, type Node, type Zone } from '../src/fluid/workspace/tree'
import { APPEARANCE_PRESETS, zoneAppearanceStyle } from '../src/fluid/present'

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
const restyled = updateFloatSlot(floated, fl.id, (slot) => ({ ...slot, appearance: { panel: 'tinted', content: 'solid', opacity: .4 } }))
eq(restyled.focus!.floats![0].zone.slot!.appearance, { panel: 'tinted', content: 'solid', opacity: .4 }, 'a floating zone appearance updates in its float rather than the absent tree')

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

/* A column edge is an outer tree dock: the old tree keeps all its geometry. */
const outerFloat = floatObject(pair, 'live:p:outer', 'Outer', { x: 5, y: 6, w: 300, h: 200 })
const outer = dockFloat(outerFloat, outerFloat.focus!.floats![0].id, columnZone(outerFloat).id, 'left')
eq(zones(outer.tree).map((x) => x.name), ['Outer', 'left', 'right'], 'a column edge docks at the outside of This post')
eq(((outer.tree as any).kids[1] as any).sizes, [.3, .7], 'the existing tree keeps its internal shares')

/* Object centre keeps its live address and closes only that float. */
const target = arr({ ...z('target'), slot: keepSlot() })
const obj = floatObject(target, 'live:p:k', 'One', { x: 0, y: 0, w: 220, h: 120 })
const kept = dockFloat(obj, obj.focus!.floats![0].id, 'target', 'center')
eq((kept.tree as Zone).slot!.items, ['live:p:k'], 'centre keeps the object in the target')
eq(kept.focus?.floats ?? [], [], 'the object float closes')

const movingTree: Node = { type: 'split', dir: 'row', sizes: [.5, .5], kids: [{ ...z('source'), slot: keepSlot(['live:p:move']) }, z('destination')] }
const movingFloat = floatObject(arr(movingTree), 'live:p:move', 'Move', { x: 0, y: 0, w: 320, h: 220 }, 'source')
const movedEdge = dockFloat(movingFloat, movingFloat.focus!.floats![0].id, 'destination', 'bottom')
eq(findZone(movedEdge.tree, 'source')!.slot!.items, [], 'docking a placement float moves it out of its source')
ok(zones(movedEdge.tree).some((x) => x.slot?.items.includes('live:p:move')), 'the same reference is placed in the new edge section')

/* A drop cannot use the explicit Focus exchange to replace the conversation. */
const refused = dockFloat(obj, obj.focus!.floats![0].id, columnZone(obj).id, 'center')
eq(refused, obj, 'conversation centre refuses a floating object')

/* A manual rectangle belongs to the floating place, including through a Focus swap. */
const resized = moveFloat(floated, fl.id, { x: 71, y: 82, w: 777, h: 555 })
const resizedSwap = makePrimary(resized, fl.zone.id)
eq([resizedSwap.focus!.floats![0].x, resizedSwap.focus!.floats![0].y, resizedSwap.focus!.floats![0].w, resizedSwap.focus!.floats![0].h],
  [71, 82, 777, 555], 'manual size survives a Focus swap')

/* Layout persistence round-trips focus and drops collisions/garbage. */
const layout = toLayout(first)
eq(toLayout(fromLayout(layout)!), layout, 'focus round-trips through storage')
const bad = structuredClone(layout) as any
bad.focus.floats.push({ id: 'stage', zone: z('stage'), x: 0, y: 0, w: 1, h: 1 })
const read = fromLayout(bad)!
eq(read.focus!.floats!.length, 1, 'a float colliding with tree content is dropped')
ok(locate(read, primaryOf(read)), 'the restored primary names present content')

/* Fit rereads placement changes, not changes to what the zone renders. */
const fitted: Node = { type: 'split', dir: 'row', sizes: [.4, .6], kids: [{ ...z('fit'), fit: true }, z('other')] }
const changedContent: Node = { ...(fitted as any), kids: [{ ...(fitted as any).kids[0], name: 'Different object' }, (fitted as any).kids[1]] }
eq(fitMeasureKey(changedContent), fitMeasureKey(fitted), 'Fit content changes do not request another measurement')
const movedFit: Node = { ...(fitted as any), kids: [(fitted as any).kids[1], (fitted as any).kids[0]] }
ok(fitMeasureKey(movedFit) !== fitMeasureKey(fitted), 'moving fitted content to another place requests a measurement')

/* Tidy changes positions only, keeps back-to-front order, and wraps left. */
const tidyStart = arr(z('stage'), { floats: [
  { id: 'f1', zone: z('one'), x: 1, y: 2, w: 300, h: 200 },
  { id: 'f2', zone: z('two'), x: 3, y: 4, w: 260, h: 240 },
  { id: 'f3', zone: z('three'), x: 5, y: 6, w: 220, h: 100 },
] })
const tidied = tidyFloats(tidyStart, 1000, 500)
eq(tidied.focus!.floats!.map((f) => [f.id, f.x, f.y]), [['f1', 688, 12], ['f2', 728, 224], ['f3', 456, 12]], 'Tidy stacks at the right and wraps into a column to its left')
eq(tidied.focus!.floats!.map((f) => [f.id, f.zone.id, f.w, f.h]), tidyStart.focus!.floats!.map((f) => [f.id, f.zone.id, f.w, f.h]), 'Tidy preserves order, content, and sizes')

/* A float's material is computed by the same appearance mapping as its zone. */
const floatVars = (preset: string) => zoneAppearanceStyle(APPEARANCE_PRESETS.find((p) => p.id === preset)!.a, 'dark').style as Record<string, string>
eq(floatVars('clear')['--zf-bg'], 'transparent', 'Clear leaves the floating material open')
eq(floatVars('clear')['--zf-border'], 'none', 'Clear uses lift rather than a border')
ok(floatVars('clear')['--zf-blur'].includes('18px'), 'Clear still blurs a busy atmosphere behind it')
ok(floatVars('quiet')['--zf-bg'] !== 'transparent', 'Quiet paints its content veil as the floating material')
ok(floatVars('quiet')['--zf-border'].includes('var(--line)'), 'Quiet has a hairline')
ok(floatVars('glass')['--zf-bg'].includes('var(--surface)'), 'Glass uses the appearance panel fill')
eq(floatVars('solid')['--zf-border'], '1px solid var(--line-strong)', 'Solid uses the stronger treatment line')
eq(floatVars('solid')['--zf-blur'], 'none', 'fully Solid needs no backdrop blur')

const themeCss = readSrc('theme.css')
ok(themeCss.includes('--float-shadow:') && themeCss.includes('--float-border:'), 'theme.css defines float shadow and border tokens on :root')
ok(themeCss.includes('--float-shadow-front:') && themeCss.includes('--float-border-front:'), 'theme.css defines active front float tokens')
ok(themeCss.includes('--float-blur:') && themeCss.includes('--float-bg:'), 'theme.css defines float blur and background tokens')
/* EVERY PAGE IS A WORKING SPACE (focus/page.ts): a Focus change made on a
   page through `onPage` is that page's alone, and This post's is its own. */
const rect = { x: 5, y: 6, w: 300, h: 200 }
const paged: Arr = {
  tree: { type: 'split', dir: 'row', sizes: [.5, .5], kids: [z('a'), z('b')] },
  pages: [{ id: 'p2', title: 'Two', tree: { type: 'split', dir: 'row', sizes: [.4, .6], kids: [z('x'), z('y')] } }],
}
const p2 = (a: Arr) => pageView(a, 'p2')
const p2primary = onPage((v) => makePrimary(v, 'x'), 'p2')(paged)
eq(primaryOf(p2(p2primary)), 'x', 'page 2: its section is primary')
eq(columnZone(p2(p2primary)).id, 'x', 'page 2: its column shows it')
eq(zones(p2primary.pages[0].tree).map((x) => x.id), ['conv', 'y'], 'page 2: the conversation took its leaf')
eq(p2(p2primary).focus?.previous, ['conv'], 'page 2 keeps its own Esc history')
ok(p2primary.tree === paged.tree && !p2primary.focus, 'making primary on page 2 leaves This post untouched')
eq(primaryOf(p2primary), 'conv', 'This post keeps the conversation primary')
const p2back = onPage(swapBack, 'p2')(p2primary)
eq(primaryOf(p2(p2back)), 'conv', 'Esc on page 2 swaps page 2 back')
eq(zones(p2back.pages[0].tree).map((x) => x.id), ['x', 'y'], 'and its section returns to its leaf')
const tpPrimary = onPage((v) => makePrimary(v, 'a'), THIS_POST)(paged)
ok(tpPrimary.pages === paged.pages, 'making primary on This post leaves every page untouched')
eq(primaryOf(tpPrimary), 'a', 'This post: its section is primary')
const both = onPage((v) => makePrimary(v, 'a'), THIS_POST)(p2primary)
const bothBack = onPage(swapBack, 'p2')(both)
eq([primaryOf(bothBack), primaryOf(p2(bothBack))], ['a', 'conv'], 'Esc on page 2 does not undo This post')
eq(bothBack.focus?.previous, ['conv'], 'This post keeps its Esc history')
const p2float = onPage((v) => floatOut(v, 'y', rect), 'p2')(paged)
eq(zones(p2float.pages[0].tree).map((x) => x.id), ['x'], 'page 2: the section floats out of its tree')
eq(p2float.pages[0].focus?.floats?.map((f) => f.zone.id), ['y'], 'page 2 owns the float')
ok(p2float.tree === paged.tree && !p2float.focus, 'floating on page 2 leaves This post untouched')
const p2fid = p2float.pages[0].focus!.floats![0].id
ok(onPage((v) => dockBack(v, p2fid), THIS_POST)(p2float) === p2float, "This post cannot dock page 2's float")
const p2docked = onPage((v) => dockBack(v, p2fid), 'p2')(p2float)
eq(zones(p2docked.pages[0].tree).map((x) => x.id), ['x', 'y'], 'page 2: Dock back returns it beside where it was')
ok(!p2docked.pages[0].focus, 'and leaves no empty focus on the page')
const p2dock = onPage((v) => dockFloat(v, p2fid, 'x', 'top'), 'p2')(p2float)
eq((p2dock.pages[0].tree as any).dir, 'col', 'page 2: docking at an edge splits its own section')
const p2obj = onPage((v) => floatObject(v, 'live:p:k', 'One', rect), 'p2')(paged)
eq([p2obj.focus, p2obj.pages[0].focus?.floats?.length], [undefined, 1], 'an object floated on page 2 is over page 2')
const p2swap = onPage((v) => makePrimary(v, 'y'), 'p2')(p2float)
eq(columnZone(p2(p2swap)).id, 'y', 'page 2: its float made primary goes to its column')
eq(p2swap.pages[0].focus?.floats?.[0].zone.id, 'conv', 'and the conversation floats in its place')
const p2tidied = onPage((v) => tidyFloats(v, 1000, 800), 'p2')(p2float)
eq(p2tidied.pages[0].focus!.floats![0].x, 1000 - 12 - rect.w, 'page 2: Tidy moves its floats')
ok(onPage((v) => tidyFloats(v, 1000, 800), THIS_POST)(p2float) === p2float, 'This post with no floats: nothing to tidy')
ok(onPage((v) => makePrimary(v, 'nope'), 'p2')(paged) === paged, 'nothing done on a page: the arrangement itself')
ok(onPage((v) => makePrimary(v, 'a'), 'closed')(paged).pages === paged.pages, "a page closed meanwhile: This post's")
eq(allPageViews(p2float).map((x) => x.view.focus?.floats?.length ?? 0), [0, 1], "every page's view, This post first")
eq(fromLayout(toLayout(p2swap))?.pages[0].focus?.column?.id, 'y', "a page's focus is kept with its layout")

const floatsCss = readSrc('fluid/focus/floats.css')
ok(floatsCss.includes('background: var(--zf-bg') && floatsCss.includes('.fl-head'), 'floats.css paints the float from its appearance material')
ok(floatsCss.includes('border: var(--zf-border'), 'floats.css takes its treatment edge from appearance')
ok(floatsCss.includes('var(--float-shadow'), 'floats.css applies deep float shadow')
ok(floatsCss.includes('.wk-float.front') && floatsCss.includes('--float-shadow-front'), 'floats.css lifts the front active float')
ok(floatsCss.includes('backdrop-filter: var(--zf-blur'), 'floats.css takes backdrop separation from appearance')

/* A workspace float has one caption and one menu: WorkspaceZone owns it,
   while the standalone float menu remains only for conversations and runs. */
const floatSource = readSrc('fluid/focus/Floats.tsx')
const zoneSource = readSrc('fluid/workspace/Zones.tsx')
ok(floatSource.includes('{!workspaceZone && <header className="fl-head"'), 'workspace floats do not render a second outer caption')
ok(floatSource.includes('{!workspaceZone && menuAt && <Sheet'), 'workspace floats do not render a second outer menu')
ok(zoneSource.includes('tidy={floating?.tidy}') && zoneSource.includes('Tidy floating windows'), 'the zone menu merges Tidy floating windows with its section items')

/* Problem D: Window toolbar consolidation and layout. */
const treeCss = readSrc('fluid/workspace/tree.css')
ok(!treeCss.includes('.wk-zcap .wt-tools { position: absolute; right: 40px'), 'tree.css avoids absolute right: 40px positioning that overlaps toolbar controls')
ok(treeCss.includes('@container (max-width: 380px)'), 'tree.css provides container query for narrow caption consolidation')

const workspaceCss = readSrc('fluid/workspace/workspace.css')
ok(workspaceCss.includes('container-type: inline-size;'), 'workspace.css establishes container context on .wk-zcap')

const searchInCss = readSrc('fluid/search-in/search-in.css')
ok(searchInCss.includes('border-bottom: 1px solid var(--line);'), 'search-in.css styles search bar as a separate row')

console.log(`fluid focus: ${checks} checks passed`)
