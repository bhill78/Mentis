/* SURFACE COMPOSITION, PACKAGE 3: P5'S CARDS ON THE FRAME (owner Turn #1512;
 * plan ent-2d8422d49d7c, package 3).
 *
 *   * a narrow card -- stack in compact, sheet in medium -- is one frame with a
 *     required body: the conversation (or its stand-in) and a run in
 *     FloatingFrame, a section or a thread framing itself; no header-only head
 *     beside a body any more;
 *   * its × is Close on this device (closeHere -> workspace.apply 'open'), never
 *     a shared change; Move up / down change this class's order only;
 *   * ordering, geometry and the arrangement are as P5 left them, and the one
 *     Reopen list is ClosedHere (no P4r closed-window list). */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { FloatingFrame } from '../src/fluid/focus/FloatingHeader'
import { chromeTarget, windowHost } from '../src/fluid/surface/chromeHosts'
import { t2Mark } from '../src/fluid/surface/chrome'
import { registry } from '../src/fluid/surface/actions/registry'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, type Ops } from '../src/fluid/surface/actions/providers/ops'
import { hostCtx } from '../src/fluid/surface/actions/targets'
import type { ActionCtx } from '../src/fluid/surface/actions/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')
const count = (s: string, re: RegExp) => (s.match(re) ?? []).length

/* every shared operation a spy: none may be reached from a card's × */
const calls: string[] = []
bindOps(new Proxy({} as Ops, { get: (_, k) => (k === 'confirm' ? () => false : (...a: unknown[]) => { calls.push(String(k) + a.filter((x) => typeof x === 'string').join(',')) }) }))
installProviders()
const ctxOf = (cls: 'medium' | 'compact'): ActionCtx => ({ ...hostCtx(cls, () => ({ ok: false, reason: 'no apply here' })), input: 'coarse' })

/* -- 1. a card, drawn: one frame, its body required ------------------------------- */
for (const placement of ['stack', 'sheet'] as const) {
  const html = renderToStaticMarkup(createElement(FloatingFrame, {
    name: 'Conversation', onMenu: () => {},
    floating: { id: 'conv', placement, closeHere: { run: () => {} }, moveUp: { run: () => {} }, moveDown: { run: () => {} } },
    body: createElement('div', { className: 'fl-body fq-float-body' }, createElement('p', { className: 'stand-in' }, 'the column')),
  }))
  ok(html.startsWith('<div class="fl-host">') && html.includes('class="sc-frame fl-frame"') && html.includes(`data-placement="${placement}"`),
    `${placement}: the card is one frame, at its class's placement`)
  eq(count(html, /class="sc"/g), 1, `${placement}: one framework bar`)
  ok(!html.includes('fl-head'), `${placement}: no header-only head beside the body`)
  ok(html.indexOf('class="sc"') < html.indexOf('class="sc-body"') && html.indexOf('class="sc-body"') < html.indexOf('stand-in'),
    `${placement}: what the card shows is the frame's body, after its bar`)
  ok(html.includes('sc-close') && html.includes(`>${t2Mark(placement)}</button>`), `${placement}: × Close here and ⋯ every action`)
}

/* -- 2. the card's × and its order: this device, this class ------------------------ */
for (const cls of ['compact', 'medium'] as const) {
  const ran: string[] = []
  const at = cls === 'compact' ? 'stack' : 'sheet'
  const card = chromeTarget('s1', 'float', at, windowHost({}, {
    closeHere: { run: () => { ran.push('closeHere') } }, moveUp: { run: () => { ran.push('moveUp') } }, moveDown: { run: () => { ran.push('moveDown') } },
  }))
  const listed = registry.list(card, ctxOf(cls))
  eq(listed.find((x) => x.def.id === 'close')?.availability.state, 'available', `${cls}: the card's Close is available`)
  ok(!listed.some((x) => x.def.id === 'removeFromWorkspace' && x.availability.state === 'available'), `${cls}: a card lends no shared Remove`)
  calls.length = 0
  await registry.run('close', card, ctxOf(cls))
  await registry.run('moveUp', card, ctxOf(cls))
  await registry.run('moveDown', card, ctxOf(cls))
  eq(ran, ['closeHere', 'moveUp', 'moveDown'], `${cls}: ×, Move up and Move down run the card's own device-local operations`)
  eq(calls, [], `${cls}: no shared operation is reached`)
}

/* -- 3. NarrowFloats, read from its source ----------------------------------------- */
const narrow = read('fluid/focus/NarrowFloats.tsx')
ok(!narrow.includes('<FloatingHeader') && !narrow.includes('menuAt=') && /import \{ FloatingFrame, type FloatingZoneHead \} from '\.\/FloatingHeader'/.test(narrow),
  'no card draws the header-only FloatingHeader')
ok(/\? <FloatingFrame name=\{name\} floating=\{head\} onMenu=\{\(\) => \{\}\} body=\{<div className="fl-body fq-float-body">\s*\{stand \? <PlacedZone z=\{stand\} page=\{page\}[^}]*\/> : <ConvStub \/>\}<\/div>\} \/>/.test(narrow),
  "the conversation's card (its stand-in, or the stub) is a frame whose body is what it shows")
ok(/<FloatBody f=\{f\} page=\{page\} r=\{r\} floating=\{head\} \/>/.test(narrow), "a run's card hands FloatBody the head, so it draws its frame (run status and Stop as header content)")
ok(/<div ref=\{at\} className="fl-body fq-float-body"><FloatBody f=\{f\} page=\{page\} r=\{r\} floating=\{\{ \.\.\.head, setSlot, useLookForPlace \}\} \/><\/div>/.test(narrow),
  'a section or thread card frames itself, measured as before')
eq(count(narrow, /<FloatBody /g), count(narrow, /<FloatBody [^>]*floating=/g), 'every FloatBody is handed its floating head: none is a bare body')
ok(/const head = \{ id: f\.zone\.id, placement, closeHere: closeHere\(f\.zone\.id\), moveUp: up, moveDown: down,/.test(narrow),
  "every card's head carries × Close here and this class's Move up / Move down")
ok(!narrow.includes('closeFloat') && !/prop: 'exists'/.test(narrow) && !narrow.includes('onClose='), "a card's × never removes the window from the arrangement")
ok(narrow.includes("workspace.apply(idOf(f), { prop: 'order', to }, { cls: narrowCls })"), "Move up / down write this class's order only")
ok(narrow.includes('derive(a, narrowCls, record)') && narrow.includes('openFloats(all, closed).sort((x, y) => view.order.indexOf(idOf(x)) - view.order.indexOf(idOf(y)))'),
  "the cards come in the class's derived order, what is closed here left out")
ok(/view\.place\[idOf\(f\)\] === 'sheet' \? 'sheet' : 'stack'/.test(narrow), 'stack or sheet as the class record places it')
ok(!/beginDrag|moveFloat|fl-resize|updateFloatRect/.test(narrow) && narrow.includes("['--fh' as string]: Math.round(f.h) + 'px'"),
  'no rectangle and no drag: the desktop rectangle is only read for the card height')
eq(count(narrow, /<ClosedHere /g), 1, 'one Reopen list: ClosedHere')
const p4rList = /fq-reopen|data-reopen|reopenHere|surface\/here'/
ok(!p4rList.test(narrow) && !p4rList.test(read('fluid/focus/Floats.tsx')),
  "P4r's closed-window list is not reintroduced")

console.log(`fluid_narrow_cards_unit: ${checks} checks passed`)
