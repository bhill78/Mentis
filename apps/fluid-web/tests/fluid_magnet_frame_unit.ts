/* SURFACE COMPOSITION, PACKAGE 4: THE MAGNET ON THE FRAME (owner Turn #1512;
 * plan ent-2d8422d49d7c, package 4; review ent-9ccf09ea5728, correction 1).
 *
 *   * every level is one SurfaceChrome on the one target (this Magnet's):
 *     the icon a hidden frame whose body is the disc (bodyIsControl), compact,
 *     standard and expanded a full frame whose body is the pane;
 *   * the disc has no hold, right-click or menu of its own, so a hold or a
 *     right-click opens exactly one action surface: the frame's T2;
 *   * a tap is still Expand and a double-tap still Open as workspace;
 *   * tab, query and scroll are view state keyed by the Magnet, the config is
 *     the arrangement's: nothing the frame holds;
 *   * no chrome inside the frame, and none around it from its float. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { keepSlot, type Zone } from '../src/fluid/workspace/tree'
import { workspace, type Arr } from '../src/fluid/workspace/place'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, type Ops } from '../src/fluid/surface/actions/providers/ops'
import type { Level } from '../src/fluid/surface/types'
import { contextOpens, pressOf, pressZone, type Timers } from '../src/fluid/surface/chrome'
import { MAGNET_CHOICES, conversationSeed } from '../src/fluid/surface/magnet/choices'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'
import { MagnetZone } from '../src/fluid/surface/magnet/MagnetZone'
import type { ZoneCtl } from '../src/fluid/workspace/TreeView'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')
const count = (s: string, re: RegExp) => (s.match(re) ?? []).length

/* nothing here reaches a server */
;(globalThis as any).fetch = async () => new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
bindOps(new Proxy({} as Ops, { get: (_, k) => (k === 'confirm' ? () => false : () => {}) }))
installProviders()

const ID = 'mag-0123456789abcdef' as const
const config: MagnetConfig = { id: ID, ...conversationSeed('c1') }
const zoneAt = (level: Level): Zone => ({ type: 'zone', id: ID, show: 'magnet', name: 'Tidewater', options: { magnet: ID }, level } as Zone)
const arrAt = (level: Level, configured = true): Arr => ({
  tree: { type: 'zone', id: 'a', show: 'objects', name: 'a', slot: keepSlot() } as Zone, pages: [],
  focus: { floats: [{ id: 'w-1', zone: zoneAt(level), x: 24, y: 24, w: 360, h: 480 }] },
  ...(configured ? { magnets: { [ID]: config } } : {}),
} as Arr)
const ctl = { drag: () => {} } as unknown as ZoneCtl
const draw = (level: Level, configured = true, floating = true) => {
  workspace.quiet(() => arrAt(level, configured))
  return renderToStaticMarkup(createElement(MagnetZone, {
    z: zoneAt(level), r: { x: 0, y: 0, w: 360, h: 480 }, ctl, page: '', first: false,
    ...(floating ? { floating: { id: ID, props: { onPointerDown: () => {} } } } : {}),
  }))
}

/* -- 1. the icon: a hidden frame, the disc its body ------------------------------- */
{
  const html = draw('icon')
  eq(count(html, /class="sc-frame mg-frame"/g), 1, 'the disc is drawn in one frame')
  ok(html.includes('data-visibility="hidden"') && html.includes('data-level="icon"') && html.includes('data-placement="float"'),
    'a hidden frame, at its level, where it is placed')
  ok(!html.includes('class="sc"'), 'no framework bar at rest')
  eq(count(html, /class="sc-t2/g), 1, 'one ⋯ (revealed on hover or focus; a trigger on touch): the frame\'s T2')
  ok(/<div class="sc-body" data-own="true">\s*<button type="button" class="mg-disc"/.test(html),
    'the body is the disc, the frame\'s own button (a hold or right-click on it is the frame\'s)')
  ok(!html.includes('sc-pop') && !html.includes('sc-bottom'), 'no action surface is open at rest')
}
{
  const html = draw('icon', false)
  ok(/<div class="sc-body" data-own="true">\s*<button type="button" class="mg-disc mg-disc-missing"/.test(html),
    'a disc whose config is gone is the same frame\'s body')
}

/* -- 2. compact, standard, expanded: a full frame, the pane its body ----------------- */
for (const level of ['compact', 'standard', 'expanded'] as Level[]) {
  const html = draw(level)
  eq(count(html, /class="sc-frame mg-frame"/g), 1, `${level}: one frame`)
  eq(count(html, /class="sc"/g), 1, `${level}: one framework bar`)
  ok(html.includes('data-visibility="full"') && html.includes(`data-level="${level}"`), `${level}: a full frame at its level`)
  ok(html.includes('class="sc-grip'), `${level}: the window's drag is the frame's grip`)
  ok(html.includes('class="mg-title"') && html.includes('class="mg-mini"'), `${level}: the rich title, its initial and its name`)
  ok(html.indexOf('class="sc-body"') < html.indexOf('class="mg-tabs"') && html.indexOf('class="mg-tabs"') < html.indexOf('class="mg-body"'),
    `${level}: the tabs and what they show are the body`)
  ok(!html.includes('mg-disc'), `${level}: no disc`)
}
{
  const html = draw('standard', false)
  ok(/class="sc-body">\s*<div class="mg-body"><p class="mg-quiet"><b>Magnet configuration unavailable/.test(html), 'a missing config is said in the body')
  const docked = draw('standard', true, false)
  ok(docked.includes('class="sc-grip') && docked.includes('data-placement="float"'),
    'drawn without a float\'s head, the grip is the section\'s drag (ZoneCtl)')
}

/* -- 3. one target, one frame, one action surface, from the source ----------------- */
const zone = read('fluid/surface/magnet/MagnetZone.tsx')
eq(count(zone, /<SurfaceChrome /g), 1, 'one SurfaceChrome element for every level: a level change moves the frame, never swaps it')
ok(/<SurfaceChrome target=\{target\}/.test(zone) && count(zone, /const target: ActionTarget = useMemo/g) === 1, 'on the one target, made once')
ok(!/LegacySurfaceChromeBar|<(FloatingFrame|FloatingHeader|SectionChrome|ActionMenu|Sheet|IconMenu)\b/.test(zone),
  'no other chrome, no Magnet-only menu: the frame\'s T2 is the one action surface')
const disc = zone.slice(zone.indexOf('function Disc('), zone.indexOf('/* -- the pane'))
ok(!/onContextMenu|onPointerDown|pressOf|setMenu/.test(disc), 'the disc has no hold or right-click of its own (the frame\'s, through bodyIsControl)')
ok(/onClick=\{tap\} onDoubleClick=\{doubleTap\}/.test(disc), 'a tap and a double-tap stay the disc\'s')
ok(disc.includes("run(MAGNET_CHOICES.discTap === 'expand' ? 'expand' : 'openAsWorkspace')") && disc.includes("if (MAGNET_CHOICES.discDoubleTap === 'openAsWorkspace') run('openAsWorkspace')"),
  'a tap is Expand, a double-tap Open as workspace, as choices.ts holds them')
eq([MAGNET_CHOICES.discTap, MAGNET_CHOICES.discDoubleTap], ['expand', 'openAsWorkspace'], '… and choices.ts holds them so')
ok(/visibility=\{icon \? 'hidden' : 'full'\} bodyIsControl=\{icon\}/.test(zone), 'hidden with the disc as its own button only at the icon')
const pane = zone.slice(zone.indexOf('function Pane('), zone.indexOf('function Results('))
ok(/useViewState<TabId>\(view, 'tab'/.test(pane) && /useViewState<string>\(view, 'q'/.test(pane) && /useViewState<Record<string, number>>\(view, 'scroll'/.test(pane),
  'tab, query and scroll are the Magnet\'s view state, not the frame\'s')
ok(/const config = arr\.magnets\?\.\[id\]/.test(zone), 'the config is the arrangement\'s')

/* the frame's own press handling: what makes a hold or right-click on the disc the frame's */
{
  const disc = { grip: false, title: false, control: true, own: true, conversation: false }
  eq(pressZone(disc, 'body'), 'body', 'a press on the disc (the body\'s own button) is a body press')
  ok(contextOpens(pressZone(disc, 'body'), 'body'), '… so a right-click on it opens the frame\'s T2')
  eq(pressZone({ ...disc, own: false }, 'body'), 'control', 'any other button in a body keeps its own presses')
  const due: (() => void)[] = []
  const timers: Timers = { set: (fn) => { due.push(fn); return due.length }, clear: () => {} }
  let menus = 0
  const p = pressOf(pressZone(disc, 'body'), 'touch', { x: 0, y: 0 }, { menu: () => { menus++ }, drag: () => {} }, timers)
  due.forEach((fn) => fn()); p.up()
  eq(menus, 1, 'a hold on the disc opens the frame\'s T2 once')
  let mouse = 0
  pressOf(pressZone(disc, 'body'), 'mouse', { x: 0, y: 0 }, { menu: () => { mouse++ }, drag: () => {} }, timers)
  eq(mouse, 0, 'a mouse press is a click, never a hold (its right-click is the menu)')
}
const chrome = read('fluid/surface/SurfaceChrome.tsx')
ok(chrome.includes("bodyIsControl && e.currentTarget.classList.contains('sc-body')") && chrome.includes('<div className="sc-body" data-own={bodyIsControl || undefined} {...region}>'),
  'the frame\'s body takes the hold and right-click of its own button')

/* the float draws no chrome around it: the Magnet frames itself */
const floats = read('fluid/focus/Floats.tsx')
ok(/return <WorkspaceZone z=\{f\.zone\}[^\n]*floating=\{floating\} \/>/.test(floats) && /if \(props\.z\.show === MAGNET_SHOW\) return <MagnetZone \{\.\.\.props\} \/>/.test(read('fluid/workspace/Zones.tsx')),
  'a floating or docked Magnet is drawn by MagnetZone alone: no frame around its frame')

/* CSS: the frame fills the zone; the icon's ⋯ is off the disc */
const css = read('fluid/surface/magnet/magnet.css')
ok(/\.mg-zone > \.mg-frame \{/.test(css) && /\.mg-pane > \.mg-frame > \.sc-body \{ display: flex; flex-direction: column; \}/.test(css), 'the frame fills the zone, the pane laid out in its body')
ok(/\.mg-at-icon > \.mg-frame > \.sc-access \{/.test(css) && !css.includes('.mg-chrome'), 'the icon\'s ⋯ has its place; the old chrome wrapper is gone')

console.log(`fluid_magnet_frame_unit: ${checks} checks passed`)
