/* SURFACE TENSION P4r: THE CHROME FIXES FROM THE OWNER'S PREVIEW (Turn #1458).
 *
 *   (a)/(b) every window and card has × -- Close, this device only, one
 *           click -- whatever it shows; Close hides it here and Reopen brings
 *           it back; Remove from workspace stays apart in T2;
 *   (c)     a docked Contents (or Media) section floats through transition(),
 *           alone or beside another; where Float is refused it says why;
 *           a window docks and is removed through transition();
 *   (d)     Ctrl/⌘+K opens the palette wherever Mentis has focus, a text
 *           field included, and the browser never gets it; the composer's
 *           Link is Ctrl/⌘+Shift+K. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { floatsAlone } from '../src/fluid/focus/model'
import type { Float } from '../src/fluid/focus/types'
import { workspace, type Arr } from '../src/fluid/workspace/place'
import type { Node, Slot, Zone } from '../src/fluid/workspace/tree'
import { capsFor, transition } from '../src/fluid/surface/transition'
import type { SurfaceCtx } from '../src/fluid/surface/types'
import { applyControlChange, refusedControlChange } from '../src/fluid/surface/controlChange'
import { closeHere, reopenHere } from '../src/fluid/surface/ClosedHere'
import { closeShown } from '../src/fluid/surface/chrome'
import { chromeTarget, sectionHost, windowHost, type SectionCtl } from '../src/fluid/surface/chromeHosts'
import { findActionKey, isFindActionKey, registry } from '../src/fluid/surface/actions/registry'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { hostCtx } from '../src/fluid/surface/actions/targets'
import { markOf } from '../src/fluid/composer/marks'
import { dismissToast, toastSnapshot } from '../src/fluid/frame/toasts'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')
installProviders()
const wide = hostCtx('wide', () => ({ ok: false, reason: 'no apply here' }))

const z = (id: string, show = 'objects', slot?: Slot): Zone => ({ type: 'zone', id, show: show as Zone['show'], name: id, ...(slot ? { slot } : {}) })
const feedSlot = (source: string): Slot => ({ follow: false, show: 'objects', items: [], present: 'cards', feed: { source } })
const media = (): Zone => ({ ...z('media', 'objects', feedSlot('media')), name: 'Contents' })
const row = (kids: Node[]): Node => ({ type: 'split', dir: 'row', sizes: kids.map(() => 1 / kids.length), kids })
const floatOf = (zone: Zone): Float => ({ id: 'float-' + zone.id, zone, x: 40, y: 40, w: 300, h: 200 })
const ctxOf = (arr: Arr, closed: string[] = []): SurfaceCtx => ({
  arr, page: null, cls: 'wide', deviceLocal: { closed: new Set(closed) }, session: { emphasis: {} },
  viewport: { w: 1280, h: 800 }, caps: capsFor(arr, null, 'wide', undefined, 'conversation'),
})
const env = { page: null, cls: 'wide' as const, viewport: { w: 1280, h: 800 } }
const reset = (arr: Arr) => { workspace.arr = arr; workspace.kind = 'conversation'; workspace.closed = { wide: new Set(), medium: new Set(), compact: new Set() } }

/* == (a)/(b): × on every window and card, by kind =============================== */

/* What each kind's chrome is handed, read from the component that draws it. */
const floats = read('fluid/focus/Floats.tsx')
const header = read('fluid/focus/FloatingHeader.tsx')
const narrow = read('fluid/focus/NarrowFloats.tsx')
const zonesSrc = read('fluid/workspace/Zones.tsx')
const thread = read('fluid/conversation/ThreadWindow.tsx')
const brain = read('fluid/brain/BrainFloat.tsx')
ok(/closeHere: closeHere\(f\.zone\.id\)/.test(floats), "a desktop window's head is handed × Close here (Floats.tsx)")
ok(header.includes('closeHere: floating.closeHere') && /<(SurfaceChrome|LegacySurfaceChromeBar) /.test(header), 'FloatingHeader lends it to the chrome as Close')
ok(/!workspaceZone && <FloatingHeader name=\{name\} floating=\{floating\}/.test(floats),
  'the conversation and a run, as windows, draw FloatingHeader with that same `floating`')
ok(/floating=\{workspaceZone \? floating : undefined\}/.test(floats), 'a section, Contents or Media window is handed the same `floating`')
ok(/floating \? <FloatingHeader name=\{name\} floating=\{floating\}/.test(zonesSrc), '... and SlotZone draws its head from it')
ok(/floating \? <FloatingHeader name=\{name\} title=\{title\} floating=\{floating\}/.test(thread), "... and a reply thread's window too")
ok(/close: \{ run: onClose/.test(brain), 'the Brain window lends its own Close')
ok(/const head = \{ id: f\.zone\.id, placement, closeHere: closeHere\(f\.zone\.id\)/.test(narrow), 'a narrow card (stack or sheet, P5) is handed × Close here')

/* Every kind's chrome, as its host is lent: × is drawn, one click, available. */
const sec: SectionCtl = { canSplitRow: false, canSplitCol: false, whyNoSplitRow: null, whyNoSplitCol: null, canMerge: false, canClose: true,
  split: () => {}, merge: () => {}, close: () => {}, fit: false }
const kinds: Array<[string, ReturnType<typeof chromeTarget>, 'float' | 'stack' | 'dock']> = [
  ['window: a section / Contents / Media', chromeTarget('contents', 'float', 'float', windowHost({ dockBack: () => {}, close: () => {} }, { closeHere: closeHere('contents') })), 'float'],
  ['window: the conversation', chromeTarget('conv', 'conversation', 'float', windowHost({ dockBack: () => {} }, { closeHere: closeHere('conv') })), 'float'],
  ['window: a run', chromeTarget('run', 'float', 'float', windowHost({ close: () => {} }, { closeHere: closeHere('run') })), 'float'],
  ['window: a reply thread', chromeTarget('thread', 'float', 'float', windowHost({ close: () => {} }, { closeHere: closeHere('thread') })), 'float'],
  ['window: the Brain', chromeTarget('brain-1', 'brain', 'float', { close: { run: () => {} } }), 'float'],
  ['card: any (narrow stack)', chromeTarget('c', 'float', 'stack', windowHost({}, { closeHere: closeHere('c') })), 'stack'],
]
for (const [kind, t, at] of kinds) {
  const close = registry.list(t, wide).find((x) => x.def.id === 'close')
  eq(close?.availability.state, 'available', `${kind}: Close is offered`)
  ok(closeShown(at, close!.availability.state), `${kind}: × is drawn`)
  ok(registry.primary(t, wide, 99).every((d) => d.id !== 'close'), `${kind}: × is its own control, not one of T1's`)
}
/* Remove from workspace stays apart: never Close's ×, never on the conversation. */
const win = kinds[0][1]
ok(registry.list(win, wide).some((x) => x.def.id === 'removeFromWorkspace'), 'a window still offers Remove from workspace, in T2')
ok(floats.includes("f.zone.id === CONVERSATION_ID ? undefined"), 'the conversation window offers no Remove: it is closed here or docked')
/* A docked section: P5 projects local Close onto the tree (plan §3.9), lent by the rule (closeOffered). */
const docked = chromeTarget('s', 'section', 'dock', sectionHost(sec, { closeHere: closeHere('s') }))
ok(closeShown('dock', registry.list(docked, wide).find((x) => x.def.id === 'close')?.availability.state ?? 'absent'),
  'a docked section lent Close here draws × (P5); Remove stays in its ⚙')
ok(/closeOffered\('section', 'dock'\)[^\n]*closeHere: closeHere\(z\.id\)/.test(zonesSrc), '... and SlotZone lends it by the rule')

/* × does what it says: this device stops drawing it; nothing shared changes; Reopen brings it back. */
{
  const arr: Arr = { tree: z('a'), pages: [], focus: { floats: [floatOf(media())] } }
  reset(arr)
  closeHere('media').run()
  ok(workspace.closed.wide.has('media'), '× closes the window on this device')
  eq(workspace.arr, arr, 'and the arrangement is untouched (nothing shared changes)')
  eq(workspace.canUndo(), false, 'Close is no arrangement step')
  eq(toastSnapshot()?.action?.label, 'Reopen', 'the toast offers Reopen')
  ok(floats.includes('const floats = openFloats(a.focus?.floats ?? [], closed)'), 'the desktop does not draw a window closed here (P5 projection)')
  ok(floats.includes('<ClosedHere view={a} />') && !floats.includes('fq-reopen') && !floats.includes('reopenHere'),
    "ClosedHere is the one Reopen list: none beside the minimised tabs")
  reopenHere('media')
  ok(!workspace.closed.wide.has('media'), 'Reopen brings it back')
}

/* == (c): Contents and Media float through transition() ========================= */
eq([floatsAlone('conversation', null, media()), floatsAlone('conversation', null, z('m', 'media')), floatsAlone('conversation', null, z('a'))],
  [true, true, false], 'a Contents section showing Media is Contents: it may float alone, as Contents does')
{
  /* the owner's case: Contents · Media is the only section of This post */
  const alone: Arr = { tree: media(), pages: [] }
  const out = transition(ctxOf(alone), 'media', { prop: 'placement', to: { kind: 'float' } })
  ok(out.ok, 'transition(): the only section, Contents · Media, floats')
  if (out.ok) {
    eq(out.arr.focus?.floats?.[0].zone, media(), 'the window holds the same zone, id unchanged')
    ok((out.arr.tree as Zone).id !== 'media', 'the empty home leaf takes its place')
  }
  reset(alone)
  eq(refusedControlChange('media', { prop: 'placement', to: { kind: 'float' } }, env), null, 'Float is offered on it (nothing refuses it)')
  ok(applyControlChange('media', { prop: 'placement', to: { kind: 'float', rect: { x: 20, y: 20, w: 300, h: 300 } } }, env), "the section's Float, as TreeView runs it, floats it")
  eq(workspace.arr.focus?.floats?.length, 1, '... one window')
  eq(toastSnapshot()?.action?.label, 'Undo', '... said, with Undo')
  workspace.undo()
  eq(workspace.arr, alone, 'Undo docks it back as it was')
  /* beside another: as always */
  const pair: Arr = { tree: row([z('a'), media()]), pages: [] }
  reset(pair)
  ok(applyControlChange('media', { prop: 'placement', to: { kind: 'float' } }, env), 'beside another section it floats too')
  /* and the window docks back through transition() */
  ok(applyControlChange('media', { prop: 'placement', to: { kind: 'dock' } }, env), "the window's Dock runs transition()")
  eq(workspace.arr.tree, pair.tree, '... and it is back where it was')
}
{
  /* a section that may not float alone: Float is shown disabled, with why, never silently nothing */
  const lone: Arr = { tree: z('notes'), pages: [] }
  reset(lone)
  const why = refusedControlChange('notes', { prop: 'placement', to: { kind: 'float' } }, env)
  ok(typeof why === 'string' && why.length > 0, `a lone ordinary section: Float is refused with a reason ("${why}")`)
  ok(!applyControlChange('notes', { prop: 'placement', to: { kind: 'float' } }, env), '... pressed anyway, nothing moves')
  eq(toastSnapshot()?.text, why, '... and the reason is said')
  const t = chromeTarget('notes', 'section', 'dock', sectionHost({ ...sec, float: () => {}, whyNoFloat: why }))
  const fl = registry.list(t, wide).find((x) => x.def.id === 'float')!
  eq(fl.availability.state, 'disabled', "the section chrome's Float is disabled")
  eq(fl.availability.state === 'disabled' && fl.availability.reason.message, why, '... with the reason beside it')
}
/* every section path is transition()'s now */
const tree = read('fluid/workspace/TreeView.tsx')
ok(!tree.includes('floatOut(') && tree.includes('applyControlChange(z.id, floatTo(r), { page })') && tree.includes('whyNoFloat: refusedControlChange(z.id, floatTo(r), { page })'),
  "TreeView's Float (the section ⚙'s and the chrome's) runs transition(), not floatOut")
ok(read('fluid/workspace/zoneMenu.tsx').includes('off: ctl.whyNoFloat') && read('fluid/surface/chromeHosts.ts').includes('off: ctl.whyNoFloat'),
  'both section hosts lend the refusal as the reason')
ok(!floats.includes('dockBack(v') && floats.includes("applyControlChange(f.zone.id, { prop: 'placement', to: { kind: 'dock' } }, { page })")
  && floats.includes("applyControlChange(f.zone.id, { prop: 'exists', to: false }, { page })"), "a window's Dock and Remove run transition()")
ok(/<SectionChrome id=\{props\.z\.id\} name=\{who\} ctl=\{props\.ctl\}/.test(zonesSrc) && /<RunPanel run=\{run\} who=\{who\} floating /.test(zonesSrc)
  && !/onFloat=\{props\.ctl\.float\}/.test(zonesSrc), "a docked run draws the section chrome, not the panel's own ⇱ and ✕")

/* == (d): Ctrl/⌘+K ================================================================ */
const press = (k: Partial<KeyboardEvent> & { key: string }) => {
  let prevented = false, toggled = 0
  const took = findActionKey({ ...k, preventDefault: () => { prevented = true } }, () => { toggled++ })
  return { took, prevented, toggled }
}
eq(press({ key: 'k', ctrlKey: true }), { took: true, prevented: true, toggled: 1 }, 'Ctrl+K: the palette, and the browser does not get it')
eq(press({ key: 'k', metaKey: true }), { took: true, prevented: true, toggled: 1 }, '⌘+K on a Mac: the same')
eq(press({ key: 'K', ctrlKey: true }), { took: true, prevented: true, toggled: 1 }, 'with Caps Lock on: the same')
eq(press({ key: 'k' }), { took: false, prevented: false, toggled: 0 }, 'a plain k is typing')
eq(press({ key: 'K', ctrlKey: true, shiftKey: true }), { took: false, prevented: false, toggled: 0 }, "Ctrl+Shift+K is left to the composer's Link")
eq(press({ key: 'k', ctrlKey: true, altKey: true }), { took: false, prevented: false, toggled: 0 }, 'Ctrl+Alt+K is left alone')
ok(!/target|tagName|isContentEditable/.test(read('fluid/surface/actions/registry.ts').split('export function findActionKey')[1] ?? 'target'),
  'where focus is -- a text field included -- does not matter')
const menu = read('fluid/surface/actions/ActionMenu.tsx')
ok(menu.includes("window.addEventListener('keydown', key, { capture: true })"),
  'the palette hears it in the capture phase, before a handler that stops keys (a decision card, an ask form) can swallow it')
ok(menu.includes('findActionKey(e,'), '... through findActionKey')
/* the composer's marks do not collide */
eq(markOf({ key: 'k' }), undefined, "in the composer, Ctrl+K is no mark: it is the palette's")
eq(markOf({ key: 'K', shiftKey: true })?.label, 'Link', 'Ctrl+Shift+K is Link')
eq(markOf({ key: 'b' })?.label, 'Bold', 'Ctrl+B is still Bold')
ok(!isFindActionKey({ key: 'b', ctrlKey: true }), 'and no mark is the palette')
const composer = read('fluid/Composer.tsx')
ok(composer.includes('const m = markOf(e)') && composer.includes('<kbd>ctrl shift K</kbd> link'), 'the composer matches marks with markOf and says the new chord')

dismissToast()
console.log(`fluid_chrome_fix_unit: ${checks} checks ok`)
