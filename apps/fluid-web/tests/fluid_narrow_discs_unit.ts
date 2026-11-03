/* DISCS AT NARROW AND TOUCH WIDTHS (finding Turn #1614; Caretaker's brief,
 * Turn #1663). What this test holds the change to:
 *
 *   1. in medium and compact a Magnet starts at the level wide gives it, so a
 *      dormant one is its disc there too; Expand, Collapse and Reset are this
 *      class's record's, and the wide level is untouched;
 *   2. such a disc is a free disc (drawn over the page, not a card); nothing
 *      else is -- not another window, not an opened Magnet;
 *   3. its move is this class's record's `at`, never its window's rectangle,
 *      and leaves the wide arrangement and the other class byte-identical;
 *   4. where each disc is drawn: its `at`, held in the room, else a free slot
 *      of the disc grid, never covering another disc;
 *   5. through the Holder, the move is one undo step that survives a reload
 *      from the tab copy, and a phone Save sends it scoped;
 *   6. drawn: a free disc offers its drag, its tap and double-tap and its hold
 *      (the frame's), none of them by hover; the wide window is drawn as
 *      before. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Holder, toLayout, workspace, type Arr } from '../src/fluid/workspace/place'
import { keepSlot, type Zone } from '../src/fluid/workspace/tree'
import type { Float } from '../src/fluid/focus/types'
import { findSurface, stateOf } from '../src/fluid/surface/state'
import { capsFor, freeDisc, transition } from '../src/fluid/surface/transition'
import { levelShown } from '../src/fluid/surface/levels'
import { DISC_GRID, discPlaces } from '../src/fluid/focus/narrowView'
import type { DevicePlacement, PresentationClass, SurfaceCtx } from '../src/fluid/surface/types'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, type Ops } from '../src/fluid/surface/actions/providers/ops'
import { MAGNET_CHOICES, conversationSeed } from '../src/fluid/surface/magnet/choices'
import { MagnetZone } from '../src/fluid/surface/magnet/MagnetZone'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'
import type { ZoneCtl } from '../src/fluid/workspace/TreeView'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const same = (a: unknown, b: unknown, what: string) => { assert.equal(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')
const bytes = (v: unknown) => JSON.stringify(v)
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0)) }
bindOps(new Proxy({} as Ops, { get: (_, k) => (k === 'confirm' ? () => false : () => {}) }))
installProviders()

const ID = 'mag-00112233445566bb' as const
const config: MagnetConfig = { id: ID, ...conversationSeed('c1') }
const mz = (level?: Zone['level']): Zone => ({ type: 'zone', id: ID, show: 'magnet', name: 'Tidewater', options: { magnet: ID }, ...(level ? { level } : {}) })
const sec = (id: string): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot: keepSlot() })
const win = (zone: Zone, x: number): Float => ({ id: 'f-' + zone.id, zone, x, y: 900, w: 360, h: 480 })
const arrWith = (level: Zone['level'] | null = 'icon'): Arr => ({
  tree: sec('s1'), pages: [], magnets: { [ID]: config },
  focus: { floats: [win(sec('w1'), 40), win(mz(level ?? undefined), 1500)] },
} as Arr)
const wideOf = (a: Arr) => { const { presentations: _p, ...rest } = toLayout(a) as Record<string, unknown>; return bytes(rest) }
const ctxOf = (arr: Arr, cls: PresentationClass, device?: DevicePlacement): SurfaceCtx => ({
  arr, page: null, cls, ...(device ? { device } : {}), deviceLocal: { closed: new Set() },
  session: { emphasis: {} }, viewport: { w: 390, h: 844 }, caps: capsFor(arr, null, cls, device),
})
const shown = (arr: Arr, cls: PresentationClass, device?: DevicePlacement) => levelShown(stateOf(arr, ID, cls, device)!.level)
const isFree = (arr: Arr, id: string, cls: PresentationClass, device?: DevicePlacement) => {
  const s = stateOf(arr, id, cls, device)
  return !!s && freeDisc(findSurface(arr, id)!, s)
}

/* -- 1. its level in medium and compact: the wide one, until this class says ---------- */
for (const cls of ['medium', 'compact'] as const) {
  same(shown(arrWith('icon'), cls), 'icon', `${cls}: a dormant Magnet is its disc here too (it was a standard pane)`)
  same(stateOf(arrWith('icon'), ID, cls)!.level.override, undefined, `${cls}: derived from wide, it is no override of this class's`)
  same(shown(arrWith('standard'), cls), 'standard', `${cls}: one opened on the desktop is opened here`)
  same(shown(arrWith(null), cls), 'standard', `${cls}: with no level of its own, standard as before`)
  const arr = arrWith('icon'), before = wideOf(arr)
  const up = transition(ctxOf(arr, cls), ID, { prop: 'level', step: 1 })
  ok(up.ok && up.layer === 'device', `${cls}: Expand from the disc is this class's`)
  if (!up.ok) continue
  same(up.device!.level[ID], 'compact', `${cls}: one step up, in this class's record`)
  same(wideOf(up.arr), before, `${cls}: and the wide arrangement is byte-identical (its level still icon)`)
  same(shown(arr, cls, up.device), 'compact', `${cls}: opened here`)
  same(shown(arr, 'wide'), 'icon', `${cls}: still a disc on the desktop`)
  const reset = transition(ctxOf(arr, cls, up.device), ID, { prop: 'level', to: 'reset' })
  ok(reset.ok && reset.layer === 'device' && shown(arr, cls, reset.ok ? reset.device : undefined) === 'icon', `${cls}: Reset size goes back to what wide gives it, its disc`)
}
same(stateOf(arrWith('icon'), ID, 'wide')!.level.override, 'icon', 'wide: the level is the zone\'s, as before')
same(stateOf(arrWith('icon'), ID, 'wide')!.level.auto, 'standard', 'wide: its automatic level is as before')
{
  const minimised: Arr = { ...arrWith(), focus: { floats: [{ ...win(sec('w1'), 40), min: true }] } }
  same(levelShown(stateOf(minimised, 'w1', 'compact')!.level), 'standard', 'a minimised window is not folded to a tab when narrow: only a Magnet takes its wide level')
}

/* -- 2. what is a free disc -------------------------------------------------------- */
for (const cls of ['medium', 'compact'] as const) {
  ok(isFree(arrWith('icon'), ID, cls), `${cls}: a dormant Magnet window is a free disc`)
  ok(!isFree(arrWith('standard'), ID, cls), `${cls}: an opened one is a card, as before`)
  ok(!isFree(arrWith('icon'), 'w1', cls), `${cls}: another window is a card, as before`)
  const docked: Arr = { tree: mz('icon'), pages: [], magnets: { [ID]: config } } as Arr
  ok(!isFree(docked, ID, cls), `${cls}: a Magnet docked in a section is placed by the section`)
}

/* -- 3. its move: this class's `at`, nothing wide, nothing of the other class ---------- */
for (const cls of ['medium', 'compact'] as const) {
  const arr = arrWith('icon'), other: DevicePlacement = { order: ['w1'], place: { w1: 'stack' }, level: {}, updatedAt: 3 }
  const before = { wide: wideOf(arr), raw: bytes(arr), other: bytes(other) }
  const out = transition(ctxOf(arr, cls), ID, { prop: 'rect', rect: { x: 120.4, y: 300.6, w: 360, h: 480 } })
  ok(out.ok && out.layer === 'device', `${cls}: a disc's move is a device outcome`)
  if (!out.ok) continue
  eq(out.device!.at, { [ID]: { x: 120, y: 301 } }, `${cls}: kept as this class's \`at\`, in whole pixels`)
  same(bytes(out.arr), before.raw, `${cls}: the arrangement it returns is byte-identical`)
  same(wideOf(out.arr), before.wide, `${cls}: the window's desktop rectangle (1500, 900) is unchanged`)
  same(bytes(other), before.other, `${cls}: the other class's record is untouched`)
  const again = transition(ctxOf(arr, cls, out.device), ID, { prop: 'rect', rect: { x: 120, y: 301, w: 1, h: 1 } })
  ok(!again.ok, `${cls}: moved to where it is, nothing changes`)
  const card = transition(ctxOf(arr, cls), 'w1', { prop: 'rect', rect: { x: 1, y: 1, w: 300, h: 300 } })
  ok(!card.ok, `${cls}: a card has no rectangle to move`)
  const opened = transition(ctxOf(arrWith('standard'), cls), ID, { prop: 'rect', rect: { x: 1, y: 1, w: 300, h: 300 } })
  ok(!opened.ok, `${cls}: nor has an opened Magnet`)
}
{
  const arr = arrWith('icon')
  const out = transition(ctxOf(arr, 'wide'), ID, { prop: 'rect', rect: { x: 10, y: 20, w: 360, h: 480 } })
  ok(out.ok && out.layer === 'shared' && !out.device, 'wide: the disc\'s move is its window\'s, as before')
}

/* -- 4. where discs are drawn --------------------------------------------------------- */
{
  const disc = MAGNET_CHOICES.disc, room = { w: 390, h: 600 }
  const ids = ['a', 'b', 'c', 'd', 'e']
  const p = discPlaces(ids, undefined, room, disc)
  eq(p.a, { x: room.w - DISC_GRID.edge - disc, y: room.h - DISC_GRID.edge - disc }, 'the first disc nothing moved takes the grid\'s first slot, at the lower right, clear of the sections\' heads')
  ok(p.b.x < p.a.x && p.b.y === p.a.y, 'the next goes leftwards')
  const pts = ids.map((id) => p[id])
  ok(pts.every((q, i) => pts.every((r, j) => i === j || Math.abs(q.x - r.x) >= DISC_GRID.pitch || Math.abs(q.y - r.y) >= DISC_GRID.pitch)), 'no disc covers another')
  ok(pts.every((q) => q.x >= 0 && q.y >= 0 && q.x + disc <= room.w && q.y + disc <= room.h), 'every disc is wholly in the room')
  ok(new Set(pts.map((q) => q.y)).size > 1, 'a narrow room wraps them onto more rows')
  const moved = discPlaces(ids, { c: { x: 16, y: 16 }, e: { x: 5000, y: 5000 } }, room, disc)
  eq(moved.c, { x: 16, y: 16 }, 'a moved disc is where it was moved')
  eq(moved.e, { x: room.w - disc, y: room.h - disc }, 'one moved on a larger screen is held in this room')
  ok(Math.abs(moved.a.x - 16) >= DISC_GRID.pitch || Math.abs(moved.a.y - 16) >= DISC_GRID.pitch, 'the others take slots clear of a moved one')
  eq(discPlaces(['a'], undefined, { w: 0, h: 0 }, disc).a, { x: 0, y: 0 }, 'before the room is measured, nothing is off it')
}

/* -- 5. through the Holder: one undo step, kept in the tab copy, saved scoped --------- */
{
  type Call = { url: string; method: string; body: Record<string, any> | null }
  const calls: Call[] = []
  const stored = { ...toLayout(arrWith('icon')) }
  ;(globalThis as any).fetch = async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = init?.body ? JSON.parse(String(init.body)) : null
    calls.push({ url: String(url), method, body })
    const reply = String(url).endsWith('/layouts') ? { layouts: [], defaults: { home: null, conversation: null, unnamed: null } }
      : method === 'GET' ? { layout: stored, saved: 100 }
      : { saved: 101, layout: { ...stored, presentations: { [body.scope]: body.presentation } } }
    return new Response(JSON.stringify(reply), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  const tab = new Map<string, string>()
  ;(globalThis as any).sessionStorage = { getItem: (k: string) => tab.get(k) ?? null, setItem: (k: string, v: string) => { tab.set(k, v) }, removeItem: (k: string) => { tab.delete(k) } }
  const m = new Map<string, string>()
  const local ={ store: () => ({ getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v) }, removeItem: (k: string) => { m.delete(k) } }), brain: async () => 'brain-1' }
  const h = new Holder(() => ({ tree: sec('start'), pages: [] }), { local })
  h.enter('c-discs', 'conversation')
  await flush()
  const wide = wideOf(h.arr)
  const out = h.apply(ID, { prop: 'rect', rect: { x: 200, y: 64, w: 360, h: 480 } }, { page: null, cls: 'compact' })
  ok(out.ok && out.layer === 'device', 'the phone move applies, as a device change')
  eq(h.devices.compact?.at, { [ID]: { x: 200, y: 64 } }, 'kept in this tab\'s phone record')
  same(wideOf(h.arr), wide, 'the desktop arrangement in this tab is byte-identical')
  same(h.devices.medium, undefined, 'the tablet has no record made for it')
  same(h.changed(), true, 'the place reads as changed until Saved')
  /* a reload: a new Holder on the same tab copy */
  const r = new Holder(() => ({ tree: sec('start'), pages: [] }), { local })
  r.enter('c-discs', 'conversation')
  await flush()
  eq(r.devices.compact?.at, { [ID]: { x: 200, y: 64 } }, 'after a reload the disc is where it was moved')
  same(wideOf(r.arr), wide, 'and the desktop arrangement is as the Brain keeps it')
  await r.save('compact')
  const sent = calls.filter((c) => c.method === 'POST').at(-1)!
  eq(Object.keys(sent.body!).sort(), ['op', 'presentation', 'scope'], 'a phone Save is a scoped save')
  eq(sent.body!.presentation.at, { [ID]: { x: 200, y: 64 } }, 'carrying the disc\'s place')
  ok(!('layout' in sent.body!) && !('tree' in sent.body!), 'and nothing of the desktop arrangement')
  eq(r.devices.compact?.at, { [ID]: { x: 200, y: 64 } }, 'the record the Brain answers keeps it')
  h.undo()
  same(h.devices.compact?.at?.[ID], undefined, 'Undo takes the move back')
}

/* -- 6. drawn ----------------------------------------------------------------------------- */
{
  workspace.quiet(() => arrWith('icon'))
  const draw = (floating: Record<string, unknown>) => renderToStaticMarkup(createElement(MagnetZone, {
    z: mz('icon'), r: { x: 0, y: 0, w: 56, h: 56 }, ctl: {} as unknown as ZoneCtl, page: '', first: false, floating: { id: ID, ...floating },
  }))
  const free = draw({ placement: 'float', move: () => {} })
  ok(/class="mg-zone mg-at-icon"/.test(free) && free.includes('class="mg-disc"'), 'a free disc is drawn as the disc')
  ok(/aria-label="Tidewater: [^"]*Tap to open it out; double-tap opens the conversation; hold or right-click for its actions; drag to move it\."/.test(free),
    'it says its tap, double-tap, hold and drag')
  ok(!draw({ placement: 'stack', move: () => {} }).includes('drag to move it'), 'a disc in the stack is not offered a free move')
  const zone = read('fluid/surface/magnet/MagnetZone.tsx')
  ok(/if \(click\.current\) \{ doubleTap\(\); return \}/.test(zone), 'a second tap is a double-tap even where no dblclick comes (touch)')
  ok(/if \(now - doubled\.current < 500\) return/.test(zone), '… and a dblclick after it is not a second one')
  ok(/onPointerEnter=\{\(e\) => \{ if \(!opened && e\.pointerType === 'mouse'/.test(zone), 'only a mouse rest shows its card: nothing needs a hover')
  const narrow = read('fluid/focus/NarrowFloats.tsx')
  ok(/const discs = open\.filter\(isDisc\)/.test(narrow) && /const fs = open\.filter\(\(f\) => !isDisc\(f\)\)/.test(narrow), 'NarrowFloats takes the free discs out of the cards')
  ok(/workspace\.apply\(f\.zone\.id, \{ prop: 'rect'/.test(narrow) && !/moveFloat|moveFloatFrom|workspace\.(edit|live)\(/.test(narrow.slice(narrow.indexOf('function Discs'), narrow.indexOf('function Panel'))),
    'a disc\'s move goes through the class\'s record (transition), never the window\'s rectangle')
  const css = read('fluid/focus/floats.css')
  ok(/\.wk-page > \.fq-ndiscs \{[^}]*pointer-events: none/.test(css) && !/\.fq-ndisc[^{]*\{[^}]*(transition|animation)/.test(css),
    'the disc layer passes presses through and animates nothing (reduced motion has nothing to stop)')
  const floats = read('fluid/focus/Floats.tsx')
  ok(/const move = at === 'float' \|\| floating\?\.placement === 'float'/.test(zone) && !/placement: 'float'/.test(floats), 'the wide window lends no placement: drawn as before')
}

console.log(`fluid narrow discs: ${checks} checks passed`)
