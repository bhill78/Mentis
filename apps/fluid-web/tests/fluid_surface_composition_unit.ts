/* SURFACE COMPOSITION: HEADER, BODY, FOOTER (owner Turn #1512; plan
 * ent-2d8422d49d7c, package 1; review ent-9ccf09ea5728's corrections).
 *
 *   * region actions: header first, then footer, each id once; the
 *     framework's own (Close, Remove, Find an action…, and every surface
 *     mechanic: Focus, Float, Dock, Fit, the arrangement's verbs) never
 *     content's, while content and specific actions stay placeable;
 *   * full / minimal / hidden: what each draws (chrome.ts layoutOf), browser-free;
 *   * a region action leaves T1, T1 keeps its whole budget, and the action
 *     stays exactly once in T2 and the palette;
 *   * a disabled region action keeps the registry's reason;
 *   * presses: the body's own button opens the frame's T2 on hold and
 *     right-click; other controls, conversation content and a text selection
 *     keep theirs; the grip drags;
 *   * the frame draws a required body, the header in the bar or above the
 *     body, the footer after the body, a rich title, and in hidden no bar;
 *   * focus or a press anywhere in the frame aims Ctrl/⌘+K at it;
 *   * the temporary legacy adapter and the header-only FloatingHeader are gone
 *     (package 5): nothing defines or calls either. */
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  FRAMEWORK_OWNED, NOT_T1, budgetOf, contextOpens, layoutOf, pressOf, pressZone, primaryAsk, regionActions, t1Of,
  type LayoutIn, type PressHit, type Timers,
} from '../src/fluid/surface/chrome'
import { chromeTarget, guarded, sectionHost, type SectionCtl } from '../src/fluid/surface/chromeHosts'
import { disabled, AVAILABLE, paletteList, registry } from '../src/fluid/surface/actions/registry'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, type Ops } from '../src/fluid/surface/actions/providers/ops'
import { hostCtx } from '../src/fluid/surface/actions/targets'
import { RegionActions } from '../src/fluid/surface/actions/ActionMenu'
import { NESTED_SURFACE, SurfaceBar, SurfaceChrome, ownsPress, swallowNextClick } from '../src/fluid/surface/SurfaceChrome'
import { SHARED_VERBS, SPECIFIC_IDS, type ActionCtx, type ActionDef, type ActionTarget } from '../src/fluid/surface/actions/types'
import { CHROME_VISIBILITIES, SURFACE_VERBS } from '../src/fluid/surface/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')

const calls: string[] = []
const spy = (name: string) => (...a: unknown[]) => { calls.push(`${name}(${a.filter((x) => typeof x === 'string').join(',')})`) }
bindOps(new Proxy({} as Ops, {
  get: (_, k) => k === 'confirm' ? () => false
    : k === 'object' ? new Proxy({}, { get: (_o, m) => spy('object.' + String(m)) })
    : spy(String(k)),
}))
installProviders()
const ctx: ActionCtx = { ...hostCtx('wide', () => ({ ok: false, reason: 'no apply here' })), input: 'fine' }

/* -- 1. region actions ------------------------------------------------------------- */
eq(regionActions(['search', 'settings'], ['settings', 'export']), { header: ['search', 'settings'], footer: ['export'] }, 'an id in both regions is drawn once, in the header')
eq(regionActions(['search', 'search'], []), { header: ['search'], footer: [] }, 'an id named twice in one region is drawn once')
eq(regionActions(['close', 'removeFromWorkspace', 'findAction', 'search'], ['close']), { header: ['search'], footer: [] },
  "Close, Remove and Find an action… are the framework's: no region draws them")
const MECHANICS = [...SURFACE_VERBS, 'fit', 'split', 'merge', 'tidyAround', 'makeRoom', 'keepArrangement',
  'saveLayout', 'restoreLayout', 'undo', 'resetPlace', 'putAllAway', 'layouts', 'sketch'] as const
for (const id of MECHANICS) {
  eq(regionActions([id, 'search'], [id, 'export']), { header: ['search'], footer: ['export'] }, `${id} is a surface mechanic: no header or footer draws it`)
}
for (const id of ['focus', 'exitFocus', 'float', 'dock', 'fullscreen', 'putAway', 'expand', 'collapse', 'makePrimary', 'bringToFront', 'showAsSheet'] as const) {
  ok(FRAMEWORK_OWNED.includes(id), `${id} is framework-owned`)
}
const CONTENT = ['open', 'peek', 'openAsWorkspace', 'keep', 'search', 'filter', 'present', 'export', 'details', 'settings', 'copyLink',
  ...SPECIFIC_IDS] as const
eq(CONTENT.filter((id) => FRAMEWORK_OWNED.includes(id)), [], 'content and resource-specific actions stay placeable in a region')
eq(regionActions(['post.reply', 'form.validate'], ['export', 'copyLink']), { header: ['post.reply', 'form.validate'], footer: ['export', 'copyLink'] },
  'content and specific actions are drawn where content places them')
eq([...SHARED_VERBS, ...SPECIFIC_IDS].filter((id) => !FRAMEWORK_OWNED.includes(id) && !(CONTENT as readonly string[]).includes(id)), [],
  'every registered id is either a framework mechanic or content\'s to place: none is unclassified')
eq(regionActions(), { header: [], footer: [] }, 'no regions, no region actions')

/* -- 2. full / minimal / hidden ---------------------------------------------------- */
const ctl: SectionCtl = {
  focus: spy('primary'), lens: true, float: spy('float'), canSplitRow: true, canSplitCol: true, whyNoSplitRow: null, whyNoSplitCol: null,
  canMerge: true, canClose: true, split: spy('split'), merge: spy('merge'), close: spy('remove'), fit: false, canFit: true, toggleFit: spy('fit'),
}
const section = chromeTarget('z1', 'section', 'dock',
  guarded(sectionHost(ctl, { lensOn: spy('lens'), search: spy('search'), settings: spy('settings') }), 'Notes', 'fine'), { following: true })
const budget = budgetOf('dock', 'standard')
const plain = t1Of(registry.primary(section, ctx, budget), budget).map((d) => d.id)
eq(plain, ['makePrimary', 'focus', 'search', 'fit'], "without regions, a section's T1 is its host's first four")

const layIn = (over: Partial<LayoutIn>): LayoutIn => ({
  visibility: 'full', placement: 'dock', level: 'standard', input: 'fine', close: 'available', grip: true, headerContent: false,
  primary: registry.primary(section, ctx, primaryAsk('dock', 'standard', (over.header?.length ?? 0) + (over.footer?.length ?? 0))),
  ...over,
})
const full = layoutOf(layIn({ header: ['search'], footer: ['settings'], headerContent: true }))
const eligible = registry.primary(section, ctx, 99).filter((d) => !NOT_T1.includes(d.id) && d.id !== 'search' && d.id !== 'settings').slice(0, budget)
eq(full.t1.map((d) => d.id), eligible.map((d) => d.id), 'full: a region action leaving T1 frees its slot for the next action, within the budget')
ok(full.t1.length > plain.length - 2, 'full: T1 is not merely shortened by what the regions draw')
ok(!full.t1.some((d) => d.id === 'search' || d.id === 'settings'), 'full: what a header or footer draws is not drawn again in T1')
ok(!full.t1.some((d) => NOT_T1.includes(d.id)), 'full: Close and Remove are never T1')
eq({ access: full.access, bar: full.bar, grip: full.grip, title: full.title, chip: full.chip, headerAt: full.headerAt, close: full.close },
  { access: 'bar', bar: true, grip: true, title: true, chip: true, headerAt: 'bar', close: true },
  'full: grip · rich title · chip · header · T1 · T2 · × in one bar')
eq([full.headerActions, full.footerActions], [['search'], ['settings']], 'full: the regions keep their own actions')
{
  const named = layoutOf(layIn({ header: ['focus', 'float', 'dock'], footer: ['fit', 'makePrimary'] }))
  eq([named.headerActions, named.footerActions], [[], []], 'full: Focus, Float, Dock, Fit and Make primary named by a region are not drawn there')
  eq(named.t1.map((d) => d.id), plain, 'full: the mechanics a region names stay in T1, where the framework draws them')
}

const minimal = layoutOf(layIn({ visibility: 'minimal', header: ['search'], headerContent: true }))
eq({ bar: minimal.bar, t1: minimal.t1, title: minimal.title, chip: minimal.chip, headerAt: minimal.headerAt, close: minimal.close, grip: minimal.grip },
  { bar: true, t1: [], title: false, chip: false, headerAt: 'bar', close: true, grip: true },
  'minimal: header content stands for the title, its actions stay, T1 moves to T2, × stays')
eq(layoutOf(layIn({ visibility: 'minimal' })).title, true, 'minimal without header content: the rich title is the fallback')
eq(layoutOf(layIn({ visibility: 'minimal', grip: false })).grip, false, 'minimal: a grip only where it moves')

for (const input of ['fine', 'coarse'] as const) {
  const h = layoutOf(layIn({ visibility: 'hidden', input, headerContent: true, header: ['search'], footer: ['settings'] }))
  eq({ bar: h.bar, t1: h.t1, grip: h.grip, close: h.close, headerAt: h.headerAt, access: h.access },
    { bar: false, t1: [], grip: false, close: false, headerAt: 'above', access: input === 'coarse' ? 'trigger' : 'reveal' },
    `hidden (${input}): no framework bar; header above the body; T2 ${input === 'coarse' ? 'from a persistent trigger' : 'revealed on focus and hover'}`)
  eq([h.headerActions, h.footerActions], [['search'], ['settings']], `hidden (${input}): content's regions are unaffected`)
}
eq(layoutOf(layIn({ visibility: 'hidden' })).headerAt, 'none', 'hidden with no header: nothing above the body')
for (const v of CHROME_VISIBILITIES) {
  eq(layoutOf(layIn({ visibility: v, footer: ['settings'] })).footerActions, ['settings'], `${v}: the footer follows the body, whatever the visibility`)
}
eq(layoutOf(layIn({ placement: 'stack', visibility: 'minimal', close: 'absent' })).close, true, 'minimal on a stack card: × is still drawn')
eq(primaryAsk('launcher', 'icon', 3), 0, 'an icon asks for no direct controls')

/* -- 3. T2 and the palette keep every region action exactly once ------------------ */
const listed = registry.list(section, ctx).map((x) => x.def.id)
for (const id of ['search', 'settings'] as const) {
  eq(listed.filter((x) => x === id).length, 1, `T2 lists ${id} exactly once, though a region draws it`)
  eq(paletteList(registry.list(section, ctx), '').filter((x) => x.def.id === id).length, 1, `the palette offers ${id} exactly once`)
}

/* -- 4. a disabled region action keeps its reason ---------------------------------- */
const formDef = (id: 'form.validate' | 'form.markReady', why: string | null): ActionDef => ({
  id, plane: 'resource', writes: 'none', label: id === 'form.validate' ? 'Check' : 'Mark ready', synonyms: [], group: 'resource',
  available: () => (why ? disabled(why) : AVAILABLE), run: () => { calls.push('run:' + id) },
})
registry.provide('test:form', () => [formDef('form.validate', null), formDef('form.markReady', 'Two answers are missing')])
const formTarget: ActionTarget = { resource: { address: 'form:1', kind: 'test:form' } }
const regionHtml = renderToStaticMarkup(createElement(RegionActions, { ids: ['form.validate', 'form.markReady', 'post.reply'], target: formTarget, ctx, region: 'footer' }))
ok(/data-action="form\.validate"/.test(regionHtml) && !/data-action="form\.validate"[^>]*aria-disabled/.test(regionHtml), 'an available region action is drawn enabled')
ok(/data-action="form\.markReady"[^>]*aria-disabled="true"/.test(regionHtml) && regionHtml.includes('Two answers are missing'),
  'a disabled region action is drawn disabled with the registry\'s reason')
ok(!regionHtml.includes('post.reply'), 'an id the registry does not offer here is not drawn')
eq(registry.list(formTarget, ctx).find((x) => x.def.id === 'form.markReady')?.availability,
  { state: 'disabled', reason: { code: 'state', message: 'Two answers are missing', retryable: true } }, 'T2 and the palette carry the same reason')

/* -- 5. presses --------------------------------------------------------------------- */
const hit = (h: Partial<PressHit>): PressHit => ({ grip: false, title: false, control: false, conversation: false, ...h })
eq(pressZone(hit({ control: true, own: true }), 'body'), 'body', "the body's own button: its hold opens the frame's T2 (Orbit's correction 1)")
eq(pressZone(hit({ control: true }), 'body'), 'control', 'any other control in the body keeps its own press')
eq(pressZone(hit({ conversation: true }), 'body'), 'control', 'conversation content keeps its own presses')
eq(pressZone(hit({ selection: true }), 'body'), 'control', 'a live text selection is the person\'s')
eq(pressZone(hit({}), 'body'), 'body', 'plain body content opens T2 on a hold')
eq(pressZone(hit({ grip: true, control: true }), 'body'), 'grip', 'the grip drags, wherever it is')
eq(pressZone(hit({ title: true, control: true }), 'bar'), 'title', 'in the bar, a press on the title is the title (the launcher icon today)')
eq(pressZone(hit({ control: true }), 'bar'), 'control', 'in the bar, a control keeps its press')
eq(pressZone(hit({}), 'bar'), 'title', 'the bar itself is held as the title')
ok(contextOpens('body', 'body') && !contextOpens('control', 'body') && !contextOpens('grip', 'body'),
  'right-click in the body: only plain content and the own button open T2; exempt targets keep the browser\'s menu')
ok(contextOpens('title', 'bar') && contextOpens('grip', 'bar') && !contextOpens('control', 'bar') && contextOpens('control', 'bar', true),
  "right-click in the bar: everything but an unrelated control; the framework's own buttons open T2")
{
  const due: Array<() => void> = []
  const timers: Timers = { set: (fn) => { due.push(fn); return due.length }, clear: () => { due.length = 0 } }
  let menus = 0
  const p = pressOf(pressZone(hit({ control: true, own: true }), 'body'), 'touch', { x: 0, y: 0 }, { menu: () => { menus++ }, drag: () => {} }, timers)
  ok(p.pending, "a touch held on the body's own button is pending a long-press")
  due.splice(0).forEach((f) => f())
  eq(menus, 1, 'and opens one T2')
}

/* -- 6. the frame, drawn ------------------------------------------------------------- */
const draw = (props: Partial<Parameters<typeof SurfaceChrome>[0]>) => renderToStaticMarkup(createElement(SurfaceChrome, {
  target: section, placement: 'dock', level: 'standard', label: 'Notes', title: createElement('b', { className: 'rich' }, 'Notes ', createElement('i', null, '3')),
  body: createElement('p', { className: 'the-body' }, 'Body'), grip: { onPointerDown() {} }, ...props,
}))
const closeOffered = registry.list(section, ctx).some((x) => x.def.id === 'close')
const at = (html: string, needle: string) => html.indexOf(needle)
{
  const html = draw({ header: { content: createElement('input', { className: 'q' }), actions: ['search'] }, footer: { content: createElement('span', { className: 'pager' }, '1/3'), actions: ['settings', 'search'] } })
  ok(html.includes('class="sc-frame"') && html.includes('data-visibility="full"') && html.includes('aria-label="Notes"'), 'the frame is labelled with the plain label')
  ok(html.includes('<b class="rich">Notes <i>3</i></b>'), 'the rich title is drawn as given')
  ok(at(html, 'class="sc"') < at(html, 'class="q"') && at(html, 'class="q"') < at(html, 'class="sc-body"'), 'full: the header content is in the one bar, before the body')
  ok(at(html, 'class="sc-body"') < at(html, 'the-body') && at(html, 'the-body') < at(html, 'sc-footer') && at(html, 'sc-footer') < at(html, 'class="pager"'),
    'the body is drawn, and the footer after it')
  eq((html.match(/data-action="search"/g) ?? []).length, 1, 'search is drawn once: in the header, not again in the footer or T1')
  eq((html.match(/data-action="settings"/g) ?? []).length, 1, 'settings is drawn once: in the footer, not in T1')
  ok(html.includes('class="sc-t2 wk-zmenu fl-btn"'), 'full: T2 is drawn')
  eq(html.includes('sc-close'), closeOffered, 'full: × is drawn exactly where Close is offered on a dock')
  eq((html.match(/class="sc"/g) ?? []).length, 1, 'one framework bar: never a content header plus a second window bar')
}
{
  const html = draw({ footer: { content: createElement('span', { className: 'pager' }, '1/3'), actions: ['focus', 'float', 'dock', 'export'] } })
  const foot = html.slice(at(html, 'sc-footer'))
  ok(!/data-action="(focus|float|dock)"/.test(foot), 'a footer that names Focus, Float or Dock does not draw them')
}
{
  const html = draw({ visibility: 'minimal', header: { content: createElement('span', { className: 'activity-head' }, 'Running') } })
  ok(html.includes('activity-head') && !html.includes('class="rich"') && !html.includes('sc-t1') && html.includes('sc-t2') && html.includes('sc-close') === closeOffered,
    'minimal: header content for the title, no T1, T2 and × kept')
  const card = draw({ placement: 'stack', visibility: 'minimal' })
  ok(card.includes('sc-close'), 'minimal on a stack card: × is drawn')
}
{
  const html = draw({ visibility: 'hidden', header: { content: createElement('span', { className: 'doc-head' }, 'Doc') } })
  ok(!html.includes('class="sc"') && html.includes('class="sc-access" data-access="reveal"') && html.includes('sc-t2'), 'hidden (fine): no bar; T2 in the revealed access')
  ok(at(html, 'sc-header') < at(html, 'sc-body') && html.includes('doc-head'), 'hidden: the header content is drawn above the body')
  ok(!html.includes('sc-close'), 'hidden: Close is reached through T2, not a direct ×')
}
{
  const launcher = chromeTarget('launcher:c', 'launcher-tile', 'launcher', {})
  const html = renderToStaticMarkup(createElement(SurfaceChrome, { target: launcher, placement: 'launcher', level: 'icon', label: 'Conversations', title: null,
    body: createElement('button', { type: 'button', className: 'icon' }, '💬'), bodyIsControl: true, visibility: 'hidden' }))
  ok(html.includes('class="sc-body" data-own="true"') && html.includes('class="icon"'), "a body that is the surface's own button is marked so its hold and right-click are the frame's")
}
{
  const html = renderToStaticMarkup(createElement(SurfaceBar, { variant: 'page-bar', target: section, level: 'standard', label: 'Home', title: 'Home' }))
  ok(html.startsWith('<div class="sc"') && !html.includes('sc-frame') && !html.includes('sc-body'), 'SurfaceBar is a bar and nothing else')
}

/* -- 7. sources: palette aim, presses, the legacy adapter ------------------------------ */
const chromeSrc = read('fluid/surface/SurfaceChrome.tsx')
ok(/className=\{'sc-frame'[^>]*onFocusCapture=\{core\.aim\} onPointerDownCapture=\{core\.aim\}/.test(chromeSrc.replace(/\n\s*/g, ' ')),
  'focus or a press anywhere in the frame (body, header, footer) aims Ctrl/⌘+K at it')
ok(chromeSrc.includes('const aim = () => pointAt({ target, ctx, name })') && chromeSrc.includes('useChromeCore(target, label, frame)'),
  'the frame aims the palette at its own target, under its plain label')
ok(!/bar\.current\?\.parentElement\?\.closest\('section'\)/.test(chromeSrc.slice(chromeSrc.indexOf('export function SurfaceChrome('), chromeSrc.indexOf('export function SurfaceBar('))),
  'the frame finds its body as its own element, not as the section around its bar')
ok(chromeSrc.includes('<div className="sc-body" data-own={bodyIsControl || undefined} {...region}>'), 'the body carries the frame\'s press and right-click handlers')

const files: string[] = []
const walk = (dir: string) => { for (const n of readdirSync(dir)) { const p = dir + '/' + n; if (statSync(p).isDirectory()) walk(p); else if (/\.tsx$/.test(n)) files.push(p) } }
walk(src.replace(/\/$/, ''))
const naming = (re: RegExp) => files.filter((f) => re.test(readFileSync(f, 'utf8'))).map((f) => f.slice(src.length).replace(/^\//, '').replace(/\\/g, '/')).sort()
/* package 2 moved the shared and ordinary hosts (tests/fluid_surface_hosts_unit.ts),
   package 3 P5's narrow cards (tests/fluid_narrow_cards_unit.ts), package 4
   the Magnet (tests/fluid_magnet_frame_unit.ts), and package 5 removed the
   adapter and the header-only FloatingHeader that was its last caller */
eq(naming(/LegacySurfaceChromeBar/), [], 'nothing defines, imports or calls the legacy adapter, or its props')
eq(naming(/function FloatingHeader\b|<FloatingHeader\b|\bFloatingHeader[,} ]/), [], 'nothing defines, imports or draws the header-only FloatingHeader')
ok(!/LegacySurfaceChromeBar/.test(read('fluid/surface/types.ts')), 'its props type is gone with it')
ok(!read('fluid/focus/NarrowFloats.tsx').includes('<FloatingHeader') && read('fluid/focus/NarrowFloats.tsx').includes('<FloatingFrame '),
  "NarrowFloats' cards are frames, no longer FloatingHeader's legacy path (package 3)")
const magnet = read('fluid/surface/magnet/MagnetZone.tsx')
ok(!/onContextMenu/.test(magnet), "the Magnet disc has no handlers of its own: its hold and right-click are its frame's (package 4)")

/* -- 8. browser findings F1-F5 (ent-6f474ff6ff1c) ------------------------------------- */
{
  /* F1, F2: a frame outside any .wk-zone (a docked run in section.fr-docked,
     Home's conversation in .fw-home-cell) reveals its ⚙ on fine hover and focus */
  const css = read('fluid/workspace/workspace.css')
  const reveal = /\.sc-frame:hover \.wk-zmenu, \.sc-frame:focus-within \.wk-zmenu \{ opacity: 1; pointer-events: auto; \}/
  ok(reveal.test(css), 'F1/F2: hovering or focusing any frame reveals its ⚙ (.wk-zmenu), without a .wk-zone ancestor')
  ok(css.search(reveal) > css.indexOf(':is(.wk, .wk-zone) .wk-zmenu {'), 'F1/F2: the reveal follows the rule that hides ⚙ at rest (and outweighs it: 0,3,0 over 0,2,0)')
}
{
  /* F3: the minimal docked-run frame has × and Close in its menu */
  const zones = read('fluid/workspace/Zones.tsx')
  const run = zones.slice(zones.indexOf('if (props.z.show === RUN_SHOW)'), zones.indexOf('if (props.z.show === MAGNET_SHOW)'))
  ok(/visibility="minimal"\s*also=\{closeOffered\('section', 'dock'\) \? \{ closeHere: closeHere\(props\.z\.id\) \} : undefined\}/.test(run),
    'F3: the docked run lends Close here to its minimal frame, as every docked section does')
  const runTarget = chromeTarget('run1', 'section', 'dock', guarded(sectionHost(ctl, { closeHere: { run: spy('closeHere') } }), 'Agent', 'fine'))
  const html = draw({ target: runTarget, label: 'Agent', visibility: 'minimal', header: { content: createElement('span', { className: 'run-head' }, 'Running') } })
  ok(html.includes('run-head') && /class="sc-close fl-btn fl-close"(?![^>]*aria-disabled)/.test(html),
    'F3: the minimal run frame draws one bar with its header, ⚙ and an available ×')
  eq((html.match(/class="sc"/g) ?? []).length, 1, 'F3: still one framework bar: no second window system')
  ok(registry.list(runTarget, ctx).some((x) => x.def.id === 'close' && x.availability.state === 'available'), "F3: Close is in the run frame's ⚙ and palette")
}
{
  /* F4: plain body content inside a layout section opens the frame's T2; a
     true nested surface keeps its own */
  ok(!/(^|, )section(,|$)/.test(NESTED_SURFACE) && NESTED_SURFACE.includes('.sc-frame'), 'F4: a bare section is not a nested surface; a frame is')
  /* a small DOM: closest by class (or `[data-float-id]`), contains by ancestry */
  type El = { cls: string[]; attrs?: string[]; parent: El | null; closest(sel: string): El | null; contains(o: El): boolean }
  const el = (parent: El | null, cls: string[], attrs: string[] = []): El => {
    const me: El = {
      cls, attrs, parent,
      closest(sel) {
        const parts = sel.split(',').map((s) => s.trim())
        for (let at: El | null = me; at; at = at.parent) {
          if (parts.some((p) => (p.startsWith('.') && at!.cls.includes(p.slice(1))) || (p.startsWith('[') && at!.attrs!.includes(p.slice(1, -1))) || at!.cls.includes('tag:' + p))) return at
        }
        return null
      },
      contains(o) { for (let at: El | null = o; at; at = at.parent) if (at === me) return true; return false },
    }
    return me
  }
  const frame = el(null, ['sc-frame'])
  const body = el(frame, ['sc-body'])
  const grow = el(body, ['tag:section', 'pz-grow'])
  const card = el(grow, ['card-text'])
  const asE = (x: El) => x as unknown as Element
  ok(ownsPress(asE(frame), asE(card)), "F4: plain card text inside a section.pz-grow is the frame's own: its right-click and hold open T2")
  ok(ownsPress(asE(frame), asE(body)), "F4: the body's padding is the frame's own")
  for (const nested of [['sc-frame'], ['wk-zone'], ['fr-docked']]) {
    const inner = el(body, ['tag:section', ...nested])
    ok(!ownsPress(asE(frame), asE(el(inner, ['text']))), `F4: a press inside a nested .${nested[0]} is not the outer frame's`)
  }
  ok(!ownsPress(asE(frame), asE(el(el(body, ['tag:section'], ['data-float-id']), ['text']))), "F4: a press inside a nested float is not the outer frame's")
  ok(!ownsPress(null, asE(card)), 'F4: no frame, nothing owned')
  /* the exemptions stand: they are decided by pressZone, not by the section */
  eq([pressZone(hit({ control: true }), 'body'), pressZone(hit({ conversation: true }), 'body'), pressZone(hit({ selection: true }), 'body')],
    ['control', 'control', 'control'], 'F4: controls, conversation content and a selection inside a layout section still keep their own presses')
  ok(/closest\('\.fx-conv, \.fq-conv-body'\)/.test(chromeSrc), 'F4: conversation content (section.fx-conv) is still found and exempt')
  ok(chromeSrc.includes('const mine = (t: EventTarget | null) => ownsPress(frame.current, t)'), 'F4: the frame uses ownsPress for its body, header and footer')
}
{
  /* F5: the synthetic click after a hold must not reach an anchored popover's
     outside-click, a later window listener (frame/Sheet.tsx); stopPropagation
     alone lets it, for both are on the same target */
  const win = new EventTarget()
  const later: Array<() => void> = []
  let closed = 0
  swallowNextClick(win, 500, (fn) => later.push(fn))          // the hold fires: swallow first...
  win.addEventListener('click', () => { closed++ }, { capture: true })   // ...then the popover opens and listens
  win.dispatchEvent(new Event('click', { cancelable: true }))
  eq(closed, 0, 'F5: the release click after a hold does not close the popover the hold opened')
  win.dispatchEvent(new Event('click', { cancelable: true }))
  eq(closed, 1, 'F5: the next click outside still closes it (normal outside-click close)')
  const win2 = new EventTarget()
  let closed2 = 0
  const later2: Array<() => void> = []
  swallowNextClick(win2, 500, (fn) => later2.push(fn))
  win2.addEventListener('click', () => { closed2++ }, { capture: true })
  later2.splice(0).forEach((f) => f())                      // no click came (a real device): the swallow lapses
  win2.dispatchEvent(new Event('click', { cancelable: true }))
  eq(closed2, 1, 'F5: where no click follows the hold, the swallow lapses and the next click closes as usual')
  const sheetSrc = read('fluid/frame/Sheet.tsx')
  ok(/setTimeout\(\(\) => window\.addEventListener\('click', outside, true\), 0\)/.test(sheetSrc),
    "F5: the popover's outside-click is a window capture listener added after it opens, so the swallow (added at the hold) is heard first")
  ok(chromeSrc.includes('const swallowClick = () => swallowNextClick(window)'), 'F5: the frame swallows through swallowNextClick')
  ok(/BottomSheet[\s\S]*className="sc-scrim" onPointerDown=/.test(chromeSrc), 'F5: the bottom sheet closes from its scrim on pointerdown, untouched by the swallowed click')
}

eq(calls.filter((c) => c.startsWith('run:')), [], 'drawing runs nothing')
console.log(`fluid_surface_composition_unit: ${checks} checks passed`)
