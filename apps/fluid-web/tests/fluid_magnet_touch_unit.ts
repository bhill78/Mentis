/* THE MAGNET'S TOUCH GESTURE (owner Turn #1592: magnets can be moved
 * anywhere; decision opr-bfaee2630555: change the gesture model for touch).
 *
 * Before: on touch a press on the disc that moved past its slop BEFORE the
 * hold (500 ms) was a move; a press that paused first opened T2 and, moving
 * on, moved the disc with T2 still open over it. Now:
 *
 *   * a press that moves past the disc's touch slop is a move WHENEVER it
 *     moves: after the hold opened T2, the move puts T2 away (pressOf `held`,
 *     SurfaceChrome heldMove) and the disc's own drag carries on;
 *   * a still hold (and a wobble under that slop) still opens T2 and leaves
 *     it open; a tap is still Expand, a double-tap Open as workspace;
 *   * mouse and pen are as they were: only a touch press is given `held`;
 *   * a toast lying over the lower right lets presses through to a disc moved
 *     there, its action alone taking them. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { keepSlot, type Zone } from '../src/fluid/workspace/tree'
import { workspace, type Arr } from '../src/fluid/workspace/place'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, type Ops } from '../src/fluid/surface/actions/providers/ops'
import { LONG_PRESS_SLOP, pressOf, pressZone, type Timers } from '../src/fluid/surface/chrome'
import { MAGNET_CHOICES, conversationSeed } from '../src/fluid/surface/magnet/choices'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'
import { MagnetZone } from '../src/fluid/surface/magnet/MagnetZone'
import type { ZoneCtl } from '../src/fluid/workspace/TreeView'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')

/* -- 1. the press: a hold, then a move ------------------------------------------- */
const disc = pressZone({ grip: false, title: false, control: true, own: true, conversation: false }, 'body')
const after = MAGNET_CHOICES.moveAfter.touch
const run = (pointer: string, steps: (p: ReturnType<typeof pressOf>, hold: () => void) => void, held = true) => {
  const due: (() => void)[] = []
  const timers: Timers = { set: (fn) => { due.push(fn); return due.length }, clear: (t) => { due[(t as number) - 1] = () => {} } }
  const got = { menu: 0, putAway: 0 }
  const p = pressOf(disc, pointer, { x: 100, y: 100 }, {
    menu: () => { got.menu++ }, drag: () => {},
    ...(held ? { held: { after, move: () => { got.putAway++ } } } : {}),
  }, timers)
  steps(p, () => { due.forEach((fn) => fn()); due.length = 0 })
  return got
}

eq(run('touch', (p, hold) => { hold(); p.up() }), { menu: 1, putAway: 0 }, 'touch: a still hold opens T2 once and leaves it open')
eq(run('touch', (p, hold) => { hold(); p.move(104, 105); p.move(100 + after - 1, 100); p.up() }), { menu: 1, putAway: 0 },
  'touch: a hold that wobbles within the disc\'s slop keeps T2 open')
eq(run('touch', (p, hold) => { hold(); p.move(100 + after + 1, 100) }), { menu: 1, putAway: 1 },
  'touch: a hold that then moves past the disc\'s slop is a move: T2 is put away')
eq(run('touch', (p, hold) => { hold(); p.move(130, 100); p.move(400, 300); p.move(1900, 1050) }), { menu: 1, putAway: 1 },
  '… once, however far it goes on')
eq(run('touch', (p, hold) => { p.move(100 + LONG_PRESS_SLOP + 1, 100); hold(); p.move(400, 300) }), { menu: 0, putAway: 0 },
  'touch: a press that moves before the hold opens nothing (the disc\'s drag has it, as before)')
eq(run('touch', (p, hold) => { hold(); p.up(); p.move(400, 300) }), { menu: 1, putAway: 0 },
  'touch: once released, T2 stays: a later move is not this press')
eq(run('touch', (p, hold) => { hold(); p.cancel(); p.move(400, 300) }), { menu: 1, putAway: 0 }, '… nor once cancelled')
eq(run('touch', (p, hold) => { hold(); p.move(400, 300) }, false), { menu: 1, putAway: 0 },
  'without `held` (every other surface, and pen and mouse) a hold then a move keeps T2 open, as before')
eq(run('mouse', (p, hold) => { hold(); p.move(400, 300) }), { menu: 0, putAway: 0 }, 'mouse: a press is never a hold')
ok(after > LONG_PRESS_SLOP, 'the disc\'s touch slop is past the hold\'s, so a move before the hold cancels it first (unchanged)')

/* -- 2. who is given `held`: the frame's own movable button, on touch only ---------- */
const chrome = read('fluid/surface/SurfaceChrome.tsx')
ok(chrome.includes("const own = zone === 'body' && !!(e.target as Element | null)?.closest?.('.sc-body[data-own]')"),
  'only a press on the body\'s own button (the disc), not a header, footer or title')
ok(chrome.includes("const held = heldMove != null && own && e.pointerType === 'touch' ? { after: heldMove, move: closeMenu } : undefined"),
  'only on touch -- pen and mouse keep their hold and press as they were -- and it puts T2 away by closing it')
ok(chrome.includes('useChromeCore(target, label, frame, bodyIsControl ? heldMove : undefined)'), 'only where the body is its own button')
eq((chrome.match(/useChromeCore\(/g) ?? []).length, 3, 'the Page bar\'s core is given none (definition, frame, bar)')
ok(/useChromeCore\(target, label, bar\)/.test(chrome), '… the bar\'s core has no heldMove')

const zone = read('fluid/surface/magnet/MagnetZone.tsx')
ok(zone.includes('{...(icon && move ? { heldMove: MAGNET_CHOICES.moveAfter.touch } : {})}'),
  'the Magnet gives it at its disc, where the disc moves, at the disc\'s own touch slop')
const watch = zone.slice(zone.indexOf('function startMove('), zone.indexOf('/* -- the pane'))
ok(watch.includes("const slop = e.pointerType === 'mouse' ? MAGNET_CHOICES.moveAfter.mouse : MAGNET_CHOICES.moveAfter.touch")
  && /Math\.hypot\(m\.clientX - from\.x, m\.clientY - from\.y\) <= slop\) return/.test(watch),
  'the disc\'s drag starts at that same distance, so T2 goes as the disc starts to follow')
ok(!/menu|T2|closeMenu/.test(watch.replace(/\/\*[\s\S]*?\*\//g, '')), 'the drag itself knows nothing of T2: the frame puts it away')

/* -- 3. drawn: the disc's frame is as it was ---------------------------------------- */
;(globalThis as any).fetch = async () => new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
bindOps(new Proxy({} as Ops, { get: (_, k) => (k === 'confirm' ? () => false : () => {}) }))
installProviders()
const ID = 'mag-0123456789abcdef' as const
const config: MagnetConfig = { id: ID, ...conversationSeed('c1') }
const z = { type: 'zone', id: ID, show: 'magnet', name: 'Tidewater', options: { magnet: ID }, level: 'icon' } as Zone
workspace.quiet(() => ({
  tree: { type: 'zone', id: 'a', show: 'objects', name: 'a', slot: keepSlot() } as Zone, pages: [],
  focus: { floats: [{ id: 'w-1', zone: z, x: 24, y: 24, w: 360, h: 480 }] }, magnets: { [ID]: config },
} as Arr))
const html = renderToStaticMarkup(createElement(MagnetZone, {
  z, r: { x: 0, y: 0, w: 360, h: 480 }, ctl: { drag: () => {} } as unknown as ZoneCtl, page: '', first: false,
  floating: { id: ID, props: { onPointerDown: () => {} }, move: () => {} },
}))
ok(/<div class="sc-body" data-own="true">\s*<button type="button" class="mg-disc"/.test(html), 'the disc is still the frame\'s own body')
ok(!/heldmove|held-move/i.test(html), 'heldMove is behaviour, never drawn')
ok(html.includes('drag to move it'), 'it still says it can be dragged')

/* -- 4. the toast lets a disc under it be taken ------------------------------------- */
const css = read('fluid/frame/frame.css')
const rule = (sel: string) => new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ' \\{([^}]*)\\}').exec(css)?.[1] ?? ''
ok(/pointer-events: none/.test(rule('.fx-toast')), 'a toast at rest takes no press')
ok(!/pointer-events/.test(rule('.fx-toast.on')), 'shown, its words still take none (a disc in the lower right stays reachable under it)')
ok(/pointer-events: auto/.test(rule('.fx-toast.on button')), '… and its action does')

console.log(`fluid_magnet_touch_unit: ${checks} checks passed`)
