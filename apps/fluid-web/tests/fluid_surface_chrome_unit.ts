/* SURFACE TENSION P4: SURFACE CHROME (plan adm-b848fa881c8d §3.6, §4 P4).
 *
 *   * T1's budget per placement (§3.6's table);
 *   * a width cut removes T1 from the end and never removes ⋯;
 *   * × on stack cards, the conversation's stand-in included (the narrow defect);
 *   * coarse input: T1 always visible, 44 px targets;
 *   * long-press: the timer opens T2 on the title (and body); a grip hold is a
 *     drag, never T2; movement past 8 px or a mouse never opens it;
 *   * T2 is a bottom sheet in compact and in coarse medium;
 *   * Close and Remove from workspace are separated by group, wording and
 *     confirmation, and Remove is never a one-tap T1 control on coarse input;
 *   * the six chromes it replaces draw it. */
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import {
  APART_WORD, NOT_T1, T1_BUDGET, T2_APART, asksFirst, budgetOf, closeShown, cutToWidth, pressOf, removeQuestion, t1Of, t1Room, t1Shown, t2Form, t2Mark,
  LONG_PRESS_MS, LONG_PRESS_SLOP, type Timers,
} from '../src/fluid/surface/chrome'
import { chromeTarget, guarded, launcherHost, sectionHost, windowHost, type SectionCtl } from '../src/fluid/surface/chromeHosts'
import { registry } from '../src/fluid/surface/actions/registry'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, type Ops } from '../src/fluid/surface/actions/providers/ops'
import { hostCtx } from '../src/fluid/surface/actions/targets'
import { WORDS } from '../src/fluid/surface/actions/words'
import type { ActionCtx, ActionDef } from '../src/fluid/surface/actions/types'
import type { InputMode, PresentationClass } from '../src/fluid/surface/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')

/* -- every operation a spy ---------------------------------------------------- */
const calls: string[] = []
let confirms = false
const spy = (name: string) => (...a: unknown[]) => { calls.push(`${name}(${a.filter((x) => typeof x === 'string').join(',')})`) }
bindOps(new Proxy({} as Ops, {
  get: (_, k) => k === 'confirm' ? (q: string) => { calls.push('confirm:' + q); return confirms }
    : k === 'object' ? new Proxy({}, { get: (_o, m) => spy('object.' + String(m)) })
    : spy(String(k)),
}))
installProviders()
const ctxOf = (cls: PresentationClass, input: InputMode): ActionCtx => ({ ...hostCtx(cls, () => ({ ok: false, reason: 'no apply here' })), input })

/* -- 1. T1's budget per placement ------------------------------------------------ */
eq(T1_BUDGET, { launcher: 0, nested: 2, dock: 4, float: 3, stack: 2, sheet: 2, 'page-root': 5, 'page-bar': 5 }, "T1's budgets are §3.6's table")
eq(budgetOf('dock', 'icon'), 0, 'an icon has no direct controls, wherever it is')
eq(budgetOf('float', 'standard'), 3, 'a window header has three')
eq(t2Mark('dock'), '⚙', 'a section caption opens T2 from ⚙')
eq(t2Mark('float'), '⚙', 'a window header opens T2 from ⚙')
eq(t2Mark('page-bar'), '⚙', 'the Page bar opens T2 from ⚙')
eq(t2Mark('stack'), '⋯', 'a stack card opens T2 from ⋯')
eq(t2Mark('launcher'), '⋯', 'a launcher tile opens T2 from ⋯')

/* a docked section that lends everything: the registry's T1 is within budget */
const ctl: SectionCtl = {
  focus: spy('primary'), lens: true, float: spy('float'), canSplitRow: true, canSplitCol: true, whyNoSplitRow: null, whyNoSplitCol: null,
  canMerge: true, canClose: true, split: spy('split'), merge: spy('merge'), close: spy('remove'), fit: false, canFit: true, toggleFit: spy('fit'),
}
const section = (input: InputMode) => chromeTarget('z1', 'section', 'dock',
  guarded(sectionHost(ctl, { lensOn: spy('lens'), search: spy('search'), settings: spy('settings') }), 'Notes', input), { following: true })
for (const input of ['fine', 'coarse'] as const) {
  const t = section(input), c = ctxOf('wide', input)
  const t1 = t1Of(registry.primary(t, c, budgetOf('dock', 'standard')), budgetOf('dock', 'standard'))
  eq(t1.map((d) => d.id), ['makePrimary', 'focus', 'search', 'fit'], `${input}: a section's T1 is its host's first four`)
  const listed = registry.list(t, c).map((x) => x.def.id)
  ok(t1.every((d) => listed.includes(d.id)), `${input}: T1 ⊆ T2`)
}
const win = chromeTarget('w1', 'float', 'float', windowHost({ primary: spy('primary'), focus: spy('lens'), dockBack: spy('dock'), minimise: { on: false, run: spy('min') }, tidy: spy('tidy'), close: spy('remove') }))
eq(t1Of(registry.primary(win, ctxOf('wide', 'fine'), 3), 3).map((d) => d.id), ['makePrimary', 'collapse', 'focus'], "a window's T1 is three: Make primary, Collapse, Focus")

/* -- 2. width cuts T1 from the end, never ⋯ ------------------------------------- */
const four = ['a', 'b', 'c', 'd']
eq(cutToWidth(four, Infinity, 28), four, 'unmeasured, nothing is cut')
eq(cutToWidth(four, 4 * 28, 28), four, 'room for four keeps four')
eq(cutToWidth(four, 2 * 28 + 10, 28), ['a', 'b'], 'room for two keeps the first two: cut from the end')
eq(cutToWidth(four, 0, 28), [], 'no room: no T1')
eq(cutToWidth(four, -50, 28), [], 'less than no room: still none, never negative')
eq(cutToWidth(four, 10 * 28, 28), four, 'more room never adds beyond the budget')
eq(cutToWidth(four, 2 * 44, 44), ['a', 'b'], 'coarse controls are wider, so fewer fit')
ok(t1Room(300, 120) < 300 - 120, "the title keeps its least before T1 takes room")
const chromeSrc = read('fluid/surface/SurfaceChrome.tsx')
ok(/className="sc-t2 wk-zmenu fl-btn"/.test(chromeSrc) && !/shown\.length > 0 && <button[^>]*sc-t2/.test(chromeSrc),
  '⋯/⚙ is drawn outside T1 and unconditionally: the width cut cannot remove it')
ok(chromeSrc.includes("k.classList.contains('sc-t1')"), 'the width reading leaves T1 out, so cutting it never changes the reading')

/* -- 3. × on stack cards, the conversation's stand-in included -------------------- */
ok(closeShown('stack', 'absent') && closeShown('stack', 'available') && closeShown('sheet', 'disabled'), '× is always drawn on a stack card and a sheet')
ok(!closeShown('float', 'absent') && closeShown('float', 'available'), 'elsewhere × is drawn only where Close is offered')
const card = chromeTarget('conv', 'float', 'stack', windowHost({}, { closeHere: { run: spy('closeHere') } }))
eq(registry.list(card, ctxOf('compact', 'coarse')).find((x) => x.def.id === 'close')?.availability.state, 'available', "a stack card's × is an available Close")
const narrow = read('fluid/focus/NarrowFloats.tsx')
/* P5 took the card's Close and the Reopen line into surface/ClosedHere.tsx, and
   the card's placement from the class (stack in compact, sheet in medium). */
const closedHereSrc = read('fluid/surface/ClosedHere.tsx')
ok(/const head = \{ id: f\.zone\.id, placement, closeHere: closeHere\(f\.zone\.id\)/.test(narrow)
  && /!workspaceZone && <FloatingHeader name=\{name\} floating=\{head\}/.test(narrow),
  "every non-section card -- the conversation's stand-in too -- draws the chrome as a stack card with × Close here")
ok(!/!conv && <span className="fl-tools">/.test(narrow), "the conversation's card is no longer left without ×")
ok(/floating=\{workspaceZone \? \{ \.\.\.head,/.test(narrow), 'a section card has × Close here too')
ok(closedHereSrc.includes("workspace.apply(id, { prop: 'open', to: false })") && closedHereSrc.includes("workspace.apply(id, { prop: 'open', to: true })")
  && !existsSync(src + 'fluid/surface/here.ts'),
  '× on a card is the device-local Close (workspace.apply), and Reopen brings it back')
ok(!narrow.includes('closeFloat'), "a card's × never removes the window from the arrangement")

/* -- 4. coarse input -------------------------------------------------------------- */
eq(t1Shown('coarse'), 'always', 'coarse: T1 always shown')
eq(t1Shown('fine'), 'hover', 'fine: T1 revealed on hover and focus')
const css = read('fluid/surface/surfaceChrome.css')
ok(css.includes(".sc[data-input='coarse'] :is(.sc-grip, .sc-t2, .sc-close, .am-t1)") && css.includes('min-width: var(--touch-target, 44px)') && css.includes('min-height: var(--touch-target, 44px)'),
  'coarse: every chrome target is at least 44 px')
ok(css.includes(".sc[data-t1='hover'] .sc-t1 { opacity: 0;") && !/data-t1='always'[^{]*\{[^}]*opacity: 0/.test(css), 'only fine input hides T1 at rest')

/* -- 5. long-press ------------------------------------------------------------------ */
function fakeTimers() {
  let now = 0
  const due: Array<{ at: number; fn: () => void; id: number }> = []
  let n = 0
  const t: Timers & { advance(ms: number): void } = {
    set: (fn, ms) => { due.push({ at: now + ms, fn, id: ++n }); return n },
    clear: (id) => { const i = due.findIndex((d) => d.id === id); if (i >= 0) due.splice(i, 1) },
    advance(ms) { now += ms; for (const d of due.filter((x) => x.at <= now)) { due.splice(due.indexOf(d), 1); d.fn() } },
  }
  return t
}
const press = (zone: Parameters<typeof pressOf>[0], pointer = 'touch') => {
  const timers = fakeTimers(), got: string[] = []
  const p = pressOf(zone, pointer, { x: 10, y: 10 }, { menu: () => got.push('T2'), drag: () => got.push('drag') }, timers)
  return { p, timers, got }
}
eq(LONG_PRESS_MS, 500, 'the long-press is 500 ms')
eq(LONG_PRESS_SLOP, 8, 'and is cancelled by 8 px of movement')
{ const { timers, got } = press('title'); timers.advance(499); eq(got, [], 'held 499 ms on the title: nothing yet'); timers.advance(1); eq(got, ['T2'], 'held 500 ms on the title: T2 opens') }
{ const { timers, got } = press('body'); timers.advance(600); eq(got, ['T2'], "held on the surface's body: T2 opens") }
{ const { p, timers, got } = press('grip'); timers.advance(1000); p.up(); eq(got, ['drag'], 'held on the grip: the drag (armTouchDrag decides when), never T2') }
{ const { p, timers, got } = press('title'); p.move(10 + 9, 10); timers.advance(600); eq(got, [], 'moved 9 px: not a long-press (a scroll)') }
{ const { p, timers, got } = press('title'); p.move(10 + 5, 10 + 5); timers.advance(600); eq(got, ['T2'], 'moved within 8 px: still a long-press') }
{ const { p, timers, got } = press('title'); timers.advance(300); p.up(); timers.advance(400); eq(got, [], 'let go at 300 ms: a tap, not T2') }
{ const { timers, got } = press('title', 'mouse'); timers.advance(1000); eq(got, [], 'a mouse never long-presses (right-click opens T2)') }
{ const { timers, got } = press('control'); timers.advance(1000); eq(got, [], 'held on a control: the control is its own') }
ok(chromeSrc.includes('onContextMenu') && chromeSrc.includes('openMenu()'), 'right-click on the chrome opens T2')
ok(/closest\('section'\)/.test(chromeSrc) && chromeSrc.includes("zoneOf(e.target as Element, false)"), "the long-press reaches the surface's body, not only its title")

/* -- 6. T2 as a bottom sheet ------------------------------------------------------- */
eq(t2Form('compact', 'fine'), 'sheet', 'compact: a bottom sheet')
eq(t2Form('compact', 'coarse'), 'sheet', 'compact, coarse: a bottom sheet')
eq(t2Form('medium', 'coarse'), 'sheet', 'coarse medium: a bottom sheet')
eq(t2Form('medium', 'fine'), 'popover', 'fine medium: anchored')
eq(t2Form('wide', 'coarse'), 'popover', 'wide: anchored, whatever the input')
eq(t2Form('wide', 'fine'), 'popover', 'wide, fine: anchored')
ok(chromeSrc.includes("form === 'sheet'") && chromeSrc.includes('<BottomSheet') && chromeSrc.includes('<Sheet anchor={menu}'),
  'both forms draw the same ActionMenu')

/* -- 7. Close and Remove from workspace, kept apart ----------------------------------- */
ok(NOT_T1.includes('removeFromWorkspace') && NOT_T1.includes('close'), 'T1 never holds Remove (nor Close, which × draws)')
const sneaky = [{ id: 'removeFromWorkspace' }, { id: 'makePrimary' }, { id: 'close' }] as ActionDef[]
eq(t1Of(sneaky, 4).map((d) => d.id), ['makePrimary'], 'even a host order that put Remove first leaves it out of T1')
for (const cls of ['wide', 'medium', 'compact'] as const) {
  const t = section('coarse')
  const t1 = t1Of(registry.primary(t, ctxOf(cls, 'coarse'), 99), 99)
  ok(!t1.some((d) => d.id === 'removeFromWorkspace'), `${cls}, coarse: Remove is not a one-tap T1 control`)
  ok(registry.list(t, ctxOf(cls, 'coarse')).some((x) => x.def.id === 'removeFromWorkspace'), `${cls}, coarse: Remove is still in T2`)
}
eq(T2_APART, ['removeFromWorkspace'], 'T2 draws Remove apart')
eq(APART_WORD, 'Remove', '... under its own word')
const menuSrc = read('fluid/surface/actions/ActionMenu.tsx')
ok(menuSrc.includes("!set.includes(x)") && menuSrc.includes('am-apart') && chromeSrc.includes('apart={T2_APART} apartWord={APART_WORD}'),
  "Remove is drawn in its own section, after the groups, out of Close's Arrange group")
ok(WORDS.close.label === 'Close' && WORDS.close.glyph === '×' && WORDS.removeFromWorkspace.label === 'Remove from workspace' && WORDS.removeFromWorkspace.glyph !== '×',
  'their words and glyphs differ: × is only Close')
ok(/this device/.test(WORDS.close.says) && /every device/.test(WORDS.removeFromWorkspace.says), 'Close says this device, Remove says every device')
eq(asksFirst('removeFromWorkspace', 'coarse'), true, 'coarse: Remove asks first')
eq(asksFirst('removeFromWorkspace', 'fine'), false, 'fine: Remove is undone with Undo')
eq(asksFirst('close', 'coarse'), false, 'Close never asks: nothing shared changes')
ok(/every device/.test(removeQuestion('Notes')) && /Close \(×\) only hides it here/.test(removeQuestion('Notes')), "Remove's question says what it does and what Close does instead")
calls.length = 0; confirms = false
await registry.run('removeFromWorkspace', section('coarse'), ctxOf('compact', 'coarse'))
eq(calls, ['confirm:' + removeQuestion('Notes')], 'coarse: refused at the question, nothing removed')
calls.length = 0; confirms = true
await registry.run('removeFromWorkspace', section('coarse'), ctxOf('compact', 'coarse'))
eq(calls, ['confirm:' + removeQuestion('Notes'), 'remove()'], 'coarse: agreed, it is removed')
calls.length = 0
await registry.run('removeFromWorkspace', section('fine'), ctxOf('wide', 'fine'))
eq(calls, ['remove()'], 'fine: removed at once (Undo brings it back)')
ok(registry.list(section('fine'), ctxOf('wide', 'fine')).every((x) => x.def.id !== 'close'), 'a docked section offers no Close until P5 projects it: its × is not drawn')

/* -- 8. the launcher tile: Bring back and its ways back ------------------------------- */
const tile = chromeTarget('launcher:c1', 'launcher-tile', 'launcher', launcherHost(spy('restore'), [{ label: 'Restore as floating window', run: spy('asFloat') }]))
eq(t1Of(registry.primary(tile, ctxOf('wide', 'fine'), budgetOf('launcher', 'icon')), 0), [], 'a launcher tile has no T1: tap is the tile itself')
eq(registry.list(tile, ctxOf('wide', 'fine')).map((x) => x.def.id), ['bringBack', 'findAction'], "its ⋯ is Bring back, then Find an action…")
ok(menuSrc.includes('function Variants') && menuSrc.includes('am-variant'), "Bring back's other ways back are drawn as its rows in T2")

/* -- 9. the six chromes draw it ------------------------------------------------------- */
const tree = read('fluid/workspace/TreeView.tsx')
ok(!/export function ZoneTools/.test(tree) && !/export function FitTool/.test(tree), "TreeView's ZoneTools is gone")
/* the one chrome: the frame, or until surface composition package 2 moves the host, its header-only legacy adapter */
const drawsChrome = (s: string) => /<(SurfaceChrome|LegacySurfaceChromeBar) /.test(s)
for (const f of ['fluid/workspace/Zones.tsx', 'fluid/conversation/ThreadWindow.tsx', 'fluid/focus/ConvLeaf.tsx', 'fluid/Home.tsx'])
  ok(read(f).includes('<SectionChrome') && !read(f).includes('<ZoneTools'), `${f}: a section's caption is SectionChrome`)
ok(drawsChrome(read('fluid/focus/FloatingHeader.tsx')), 'the window header is SurfaceChrome')
ok(drawsChrome(read('fluid/brain/BrainFloat.tsx')) && !read('fluid/brain/BrainFloat.tsx').includes('fl-tools'), "the Brain window's header is SurfaceChrome")
ok(read('fluid/focus/Launcher.tsx').includes('placement="launcher" level="icon"') && !read('fluid/focus/Launcher.tsx').includes('fq-launch-more'), 'the launcher tile is SurfaceChrome')
ok(read('fluid/frame/TopBar.tsx').includes('<SurfaceBar variant="page-bar"') && !read('fluid/frame/TopBar.tsx').includes('WindowMinimizeControl'), "the Page bar's tools are SurfaceBar, the one bar-only chrome")
ok(!read('fluid/brain/BrainPlace.tsx').includes('⧉'), '⧉ is retired from the Brain window too')

console.log(`fluid_surface_chrome_unit: ${checks} checks ok`)
