/* SURFACE COMPOSITION, PACKAGE 2: THE SHARED AND ORDINARY HOSTS ON THE FRAME
 * (owner Turn #1512; plan ent-2d8422d49d7c, package 2; review ent-9ccf09ea5728's
 * corrections).
 *
 *   * every floating surface is FloatingFrame: one frame, the window's body in
 *     it, where it came from in its header, its head's mouse drag on its bar only;
 *   * every section is SectionChrome around its body: its caption tools are
 *     header content, never a second bar;
 *   * the docked run is the minimal frame, its one header the run's (who,
 *     what it is doing now, Stop), RunPanel drawing no head of its own;
 *   * the launcher is a hidden frame whose body is its own button
 *     (bodyIsControl); the Page bar is SurfaceBar, the one bar-only surface;
 *   * the Brain window and Home's zones are frames; Home's conversation column
 *     a hidden one;
 *   * left for packages 3 and 4: NarrowFloats' conversation and run cards on
 *     the temporary FloatingHeader (moved by package 3), the Magnet on the
 *     legacy adapter, which stays until both are moved; the Top bar's
 *     Activity is not converted;
 *   * package 1's framework/content action boundary is unchanged. */
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { regionActions } from '../src/fluid/surface/chrome'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, type Ops } from '../src/fluid/surface/actions/providers/ops'
import { SectionChrome } from '../src/fluid/surface/SurfaceChrome'
import { FloatingFrame, barDrag, onBar } from '../src/fluid/focus/FloatingHeader'
import type { ZoneCtl } from '../src/fluid/workspace/TreeView'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')
const count = (s: string, re: RegExp) => (s.match(re) ?? []).length

bindOps(new Proxy({} as Ops, { get: (_, k) => (k === 'confirm' ? () => false : () => {}) }))
installProviders()

/* -- 1. a floating surface, drawn ------------------------------------------------ */
{
  const html = renderToStaticMarkup(createElement(FloatingFrame, {
    name: 'Notes', floating: { id: 'z1', closeHere: { run: () => {} }, from: createElement('button', { className: 'fl-from' }, 'Survey · #12'), window: {} },
    body: createElement('div', { className: 'fl-body the-body' }, 'Body'), onMenu: () => {},
  }))
  ok(html.startsWith('<div class="fl-host">') && html.includes('class="sc-frame fl-frame"'), 'a floating surface is one frame, in a wrapper that draws nothing')
  eq(count(html, /class="sc"/g), 1, 'one framework bar: no window head beside it')
  ok(!html.includes('fl-head'), 'no header-only window head')
  ok(html.indexOf('fl-from') < html.indexOf('class="sc-body"') && html.indexOf('class="sc"') < html.indexOf('fl-from'),
    'where it came from is header content, in the bar, before the body')
  ok(html.indexOf('class="sc-body"') < html.indexOf('the-body'), 'what it shows is the body')
  ok(html.includes('sc-close'), '× Close here, as lent')
  ok(html.includes('<span class="zc-name" title="Notes">Notes</span>'), 'the rich title as the window head drew it')
}
{
  const html = renderToStaticMarkup(createElement(FloatingFrame, {
    name: 'Run', floating: { id: 'r1', placement: 'stack' }, visibility: 'minimal',
    header: { content: createElement('span', { className: 'fr-head-in' }, 'Reading') }, body: createElement('p', null, 'x'), onMenu: () => {},
  }))
  ok(html.includes('data-visibility="minimal"') && html.includes('data-placement="stack"') && html.includes('fr-head-in') && html.includes('sc-close'),
    'a card frame keeps its placement, its header content and × (always on a stack card)')
}

/* -- 2. the head's mouse drag reaches only this frame's own bar --------------------- */
{
  /* a stand-in DOM: each node a class list and a parent; closest() as the browser's */
  type Fake = { cls: string; parentElement: Fake | null }
  const el = (cls: string, parentElement: Fake | null): Fake => ({ cls, parentElement })
  const closest = (from: Fake, sel: string): Fake | null => {
    const want = sel.split(',').map((x) => x.trim().replace(/^\./, ''))
    for (let n: Fake | null = from; n; n = n.parentElement) if (want.some((w) => n!.cls.split(' ').includes(w))) return n
    return null
  }
  const frame = el('sc-frame', el('fl-host', null))
  const bar = el('sc', frame)
  const nestedBar = el('sc', el('sc-frame', el('sc-body', frame)))
  const press = (target: Fake) => ({
    target: { closest: (x: string) => closest(target, x) } as unknown as EventTarget,
    currentTarget: { firstElementChild: frame } as unknown as HTMLElement,
  })
  ok(onBar(press(el('sc-title', bar))) && onBar(press(bar)), "a press on the frame's own bar is the head's")
  ok(!onBar(press(el('the-body', el('sc-body', frame)))), 'a press in the body is not')
  ok(!onBar(press(el('sc-title', nestedBar))), "a nested surface's bar is not this head")
  ok(barDrag(press(el('sc-title', bar))), 'the title drags the window with a mouse')
  ok(!barDrag(press(el('sc-grip', bar))) && !barDrag(press(el('button', bar))), 'the grip (its own drag) and a button in the bar do not start the head drag')
}

/* -- 3. a section, drawn ----------------------------------------------------------- */
const ctl = {
  stacked: false, across: false, canSplitRow: true, canSplitCol: true, whyNoSplitRow: null, whyNoSplitCol: null, canMerge: false, canClose: true,
  split: () => {}, merge: () => {}, close: () => {}, closing: false, widen: () => false, docked: true, fit: false, canFit: false, drag: () => {},
} as unknown as ZoneCtl
{
  const html = renderToStaticMarkup(createElement(SectionChrome, {
    id: 's1', name: 'Notes', ctl, title: createElement('span', { className: 'wk-what' }, 'Notes · Following #12'),
    header: { content: createElement('span', { className: 'wk-now' }, 'now #12') },
    body: createElement('div', { className: 'wk-zbody' }, 'what it shows'),
  }))
  ok(html.startsWith('<div class="sc-frame wk-zframe"') && html.includes('data-placement="dock"'), 'a section is a frame, its caption styled as the section caption (wk-zframe)')
  eq(count(html, /class="sc"/g), 1, 'one caption bar')
  ok(html.indexOf('wk-now') < html.indexOf('class="sc-body"') && html.indexOf('class="sc-body"') < html.indexOf('wk-zbody'),
    "the section's caption tools are header content in the bar; what it shows is the body")
  ok(html.includes('sc-grip'), "the section's drag is the frame's grip")
}
{
  const html = renderToStaticMarkup(createElement(SectionChrome, {
    id: 'run1', name: 'Caretaker', ctl, visibility: 'minimal', title: createElement('span', { className: 'wk-what' }, 'Caretaker'),
    header: { content: createElement('span', { className: 'fr-head-in' }, createElement('span', { className: 'fr-now' }, 'Reading'), createElement('button', { className: 'fr-stop' }, 'Stop')) },
    body: createElement('div', { className: 'fr-panel fr-framed' }, 'feed'),
  }))
  ok(html.includes('data-visibility="minimal"') && !html.includes('sc-t1') && html.includes('sc-t2') && html.includes('fr-stop'),
    "minimal (the docked run): the run's own head, no T1, ⚙ kept")
  eq(count(html, /fr-stop/g), 1, 'Stop once')
}
{
  const html = renderToStaticMarkup(createElement(SectionChrome, {
    id: 'conv', name: 'Conversation', ctl, kind: 'conversation', visibility: 'hidden', title: 'Conversation',
    body: createElement('div', { className: 'fx-conv' }, 'the column, with its own head'),
  }))
  ok(!html.includes('class="sc"') && html.includes('class="sc-access" data-access="reveal"') && html.includes('fx-conv'),
    "Home's conversation column: a hidden frame, the zone's ⚙ revealed, the column's own head the only head")
}

/* -- 4. every host, read from its source ------------------------------------------- */
const files: string[] = []
const walk = (dir: string) => { for (const n of readdirSync(dir)) { const p = dir + '/' + n; if (statSync(p).isDirectory()) walk(p); else if (/\.tsx$/.test(n)) files.push(p) } }
walk(src.replace(/\/$/, ''))
const rel = (f: string) => f.slice(src.length).replace(/^\//, '').replace(/\\/g, '/')
const using = (re: RegExp) => files.filter((f) => re.test(readFileSync(f, 'utf8'))).map(rel).sort()

eq(using(/<LegacySurfaceChromeBar /), ['fluid/focus/FloatingHeader.tsx', 'fluid/surface/magnet/MagnetZone.tsx'],
  'the legacy adapter is left only to the temporary FloatingHeader (P5, package 3) and the Magnet (package 4)')
ok(read('fluid/surface/SurfaceChrome.tsx').includes('export function LegacySurfaceChromeBar('), 'the adapter itself stays until packages 3 and 4 finish')
eq(using(/<FloatingHeader /), [], 'nothing draws the header-only window head since package 3 moved NarrowFloats')
eq(using(/<SurfaceBar /), ['fluid/frame/TopBar.tsx'], 'SurfaceBar has one caller: the Page bar')
eq(using(/<FloatingFrame /), ['fluid/conversation/ThreadWindow.tsx', 'fluid/focus/Floats.tsx', 'fluid/focus/NarrowFloats.tsx', 'fluid/workspace/Zones.tsx'],
  'the floating frame is drawn by the floats (conversation, run), the narrow conversation card (package 3), and by the section and thread that frame themselves')
eq(using(/<SectionChrome /), ['fluid/Home.tsx', 'fluid/conversation/ThreadWindow.tsx', 'fluid/focus/ConvLeaf.tsx', 'fluid/workspace/Zones.tsx'],
  'every docked section host draws SectionChrome')
for (const f of ['fluid/Home.tsx', 'fluid/conversation/ThreadWindow.tsx', 'fluid/focus/ConvLeaf.tsx', 'fluid/workspace/Zones.tsx']) {
  const s = read(f)
  eq(count(s, /<SectionChrome /g), count(s, /<SectionChrome [^]*?body=\{/g), `${f}: every SectionChrome is handed its body`)
  ok(!/<div className="wk-zcap[^"]*"( ref=\{cap\})?>\s*<SectionChrome/.test(s), `${f}: no caption wrapper around the frame`)
}
ok(!/extra=/.test(read('fluid/Home.tsx')) && !/extra=/.test(read('fluid/conversation/ThreadWindow.tsx')), 'caption tools are header content, not a bar extra')

const floats = read('fluid/focus/Floats.tsx')
ok(!floats.includes('<FloatingHeader') && /framed=\{\(head, panel\) => <FloatingFrame name=\{who\} floating=\{floating\} onMenu=\{onMenu\} header=\{\{ content: head \}\}/.test(floats),
  "a run's window: one frame, the run's head its header content")
ok(/return floating \? <FloatingFrame name=\{name\} floating=\{floating\} onMenu=\{onMenu\} body=\{<div className="fl-body fq-float-body">\{conv\}<\/div>\} \/> : <>\{conv\}<\/>/.test(floats),
  "the conversation's window: one frame; without `floating`, its body only (NarrowFloats' card, until package 3)")
ok(/: <RunPanel run=\{run\} who=\{who\} floating onClose=\{close\} onOpenPost=\{openPost\} \/>/.test(floats), "... and a run's body only, likewise")

const zones = read('fluid/workspace/Zones.tsx')
const run = zones.slice(zones.indexOf('if (props.z.show === RUN_SHOW)'), zones.indexOf('if (props.z.show === MAGNET_SHOW)'))
ok(run.includes('framed={(head, panel) => <SectionChrome') && run.includes('visibility="minimal"') && run.includes('body={panel}') && !run.includes('wk-zcap'),
  'the docked run is the minimal frame: the production minimal-mode surface')
const panel = read('fluid/runs/RunPanel.tsx')
const framed = panel.slice(panel.indexOf('if (framed)'), panel.indexOf('return (', panel.indexOf('if (framed)')))
ok(framed.includes('fr-head-in') && framed.includes('{now}{stop}') && !framed.includes('fr-close') && !framed.includes('<header') && !framed.includes('<section'),
  'framed, RunPanel hands its status and Stop to the frame and draws no head, ⇱ or ✕ of its own, nor a nested section')
ok(panel.includes('<header className="fr-head">'), 'unframed (over the composer, a narrow card), the panel keeps its own head')

const launcher = read('fluid/focus/Launcher.tsx')
ok(/<SurfaceChrome [^]*placement="launcher" level="icon" visibility="hidden"[^]*bodyIsControl[^]*body=\{<button type="button" className="fq-launch" onClick=\{onRestore\}/.test(launcher),
  'the launcher is a hidden frame, its icon button the body, whose hold and right-click are the frame\'s (bodyIsControl)')
const top = read('fluid/frame/TopBar.tsx')
ok(top.includes('<SurfaceBar variant="page-bar"') && !top.includes('<SurfaceChrome'), 'the Page bar is SurfaceBar; the Top bar\'s Activity is not converted for show')
const brain = read('fluid/brain/BrainFloat.tsx')
ok(/<SurfaceChrome [^]*className="fl-frame"[^]*body=\{<div className=\{'fl-body bz-body'/.test(brain) && !brain.includes('<header className="fl-head"'),
  'the Brain window is one frame, its body what it shows')
const home = read('fluid/Home.tsx')
ok(/<SectionChrome [^]*visibility="hidden"\s+body=\{conversation\?\.\(/.test(home) && !/tools: <SectionChrome/.test(home),
  "Home's conversation column is a hidden frame; its head carries no second set of the zone's tools")

/* NarrowFloats moved in package 3 (tests/fluid_narrow_cards_unit.ts); the Magnet is package 4: not moved here */
ok(!read('fluid/focus/NarrowFloats.tsx').includes('<FloatingHeader'), "NarrowFloats' cards are frames (package 3)")
ok(/onContextMenu/.test(read('fluid/surface/magnet/MagnetZone.tsx')), 'the Magnet keeps its own handlers (package 4)')

/* CSS: the frame wears the caption and the window head; the wrapper draws nothing */
const floatsCss = read('fluid/focus/floats.css')
ok(/\.fl-host \{ display: contents; \}/.test(floatsCss) && /\.fl-head, \.fl-frame > \.sc \{/.test(floatsCss), "a float's frame bar wears the window head")
ok(/\.wk-zcap, \.wk-zframe > \.sc \{/.test(read('fluid/workspace/workspace.css')), "a section's frame bar wears the caption")

/* -- 5. package 1's boundary, unchanged --------------------------------------------- */
eq(regionActions(['float', 'dock', 'focus', 'close', 'search'], ['removeFromWorkspace', 'settings']), { header: ['search'], footer: ['settings'] },
  "a region still never draws the framework's mechanics")
for (const f of ['fluid/Home.tsx', 'fluid/conversation/ThreadWindow.tsx', 'fluid/focus/ConvLeaf.tsx', 'fluid/workspace/Zones.tsx', 'fluid/focus/Floats.tsx', 'fluid/brain/BrainFloat.tsx', 'fluid/focus/Launcher.tsx'])
  ok(!/actions: \[/.test(read(f)), `${f}: names no region actions (no mechanics placed as content)`)

console.log(`fluid_surface_hosts_unit: ${checks} checks passed`)
