/* MAGNET MARKER PRESENTATION (package D, defects seen in the deployed UI at
 * 67b1018). What it holds the disc, its menu and its hover card to:
 *
 *   1. discs on the launcher's grid are drawn clear of each other, the left edge
 *      and the room, whichever window is raised; a moved one stays, and the column
 *      keeps clear of as many rows as there are;
 *   2. Full screen and Put away say why they do nothing;
 *   3. a preview's Markdown reads as plain words;
 *   4. a source naming nobody is never "0 participants";
 *   5. a disc shows its zone's own name;
 *   6. one post is one post;
 *   7, 8. a hover's page waits for and holds both lanes, ends on leaving, and shows
 *      recent posts, a gallery, a file list and Busy;
 *   9. who has a live run is told apart, from what the client holds;
 *  10. every theme is its own on the disc and the card. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { MagnetConfig, MagnetLive, MagnetResult } from '../src/fluid/surface/magnet/types'
import { conversationSeed } from '../src/fluid/surface/magnet/choices'
import { DISC_CELL, DISC_FOOT, discFlow, discsReach, settledDiscs } from '../src/fluid/surface/magnet/discs'
import { BUILD_ENV, countWords, createAdapters, magnetStatus, magnetTitle } from '../src/fluid/surface/magnet/model'
import { authorsHeld, plainWords, summaryLatest } from '../src/fluid/surface/magnet/presentation'
import { createMagnetRoute, type RouteGet } from '../src/fluid/surface/magnet/route'
import { conversationAdapter } from '../src/fluid/surface/magnet/conversation'
import { createLive } from '../src/fluid/surface/magnet/live'
import { MagnetPreview, SummaryLead } from '../src/fluid/surface/magnet/Summary'
import { bindMagnetOps, magnetDefs, type MagnetOps } from '../src/fluid/surface/magnet/provider'
import type { ActionCtx, ActionTarget } from '../src/fluid/surface/actions/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')

const ID = 'mag-00112233445566bb' as const
const SOURCE = { kind: 'conversation' as const, conversation: 'ent-2865e11386f6' }
const cfg = (over: Partial<MagnetConfig> = {}): MagnetConfig => ({ id: ID, ...conversationSeed(SOURCE.conversation), ...over })

/* -- 1. where a disc is drawn --------------------------------------------------------- */
{
  /* as the server places them: 24 + 96n, six to a row */
  const grid = (n: number) => Array.from({ length: n }, (_, i) => ({ id: 'w-' + i, x: 24 + 96 * (i % 6), y: 24 + 96 * Math.floor(i / 6) }))
  const room = { flow: 452, w: 1500, h: 900 }
  const feet = (at: { x: number; y: number }) => ({ l: at.x - DISC_FOOT.left, t: at.y - DISC_FOOT.top, r: at.x + DISC_FOOT.right, b: at.y + DISC_FOOT.bottom })
  const touching = (a: { x: number; y: number }, b: { x: number; y: number }) => { const p = feet(a), q = feet(b); return p.l < q.r && q.l < p.r && p.t < q.b && q.t < p.b }
  for (const n of [1, 2, 6, 7, 12]) {
    const drawn = [...settledDiscs(grid(n), room).values()]
    eq(drawn.length, n, `${n} discs each drawn`)
    for (let i = 0; i < n; i++) {
      const f = feet(drawn[i])
      ok(f.l >= 0 && f.t >= 0, `${n} discs: disc ${i}'s name and orbit are clear of the left and top edges`)
      ok(f.r <= room.flow, `${n} discs: disc ${i} stays within the column it stands over`)
      for (let j = i + 1; j < n; j++) ok(!touching(drawn[i], drawn[j]), `${n} discs: ${i} and ${j} do not touch`)
    }
  }
  const seven = settledDiscs(grid(7), room)
  eq(settledDiscs([...grid(7)].reverse(), room), seven, 'where each is drawn does not depend on window order, which a raise changes')
  eq(seven.get('w-6'), { x: DISC_CELL.x0 + DISC_CELL.w * 2, y: DISC_CELL.y0 + DISC_CELL.h }, 'the seventh takes its own slot\'s cell')

  /* a disc dragged away leaves its neighbours where they were */
  const moved = grid(7).map((d) => d.id === 'w-1' ? { ...d, x: 800, y: 500 } : d)
  const after = settledDiscs(moved, room)
  eq(after.get('w-1'), { x: 800, y: 500 }, 'a moved disc stays where it was put')
  for (const id of ['w-0', 'w-2', 'w-3', 'w-4', 'w-5', 'w-6']) eq(after.get(id), seven.get(id), `${id} does not shift for it`)
  /* … unless it would clip or cover another */
  eq(settledDiscs([{ id: 'a', x: 0, y: 0 }], room).get('a'), { x: DISC_FOOT.left, y: DISC_FOOT.top }, 'one dropped at the corner is drawn clear of the edges')
  eq(settledDiscs([{ id: 'a', x: 1490, y: 890 }], room).get('a'), { x: 1500 - DISC_FOOT.right, y: 900 - DISC_FOOT.bottom }, '… and of the far ones')
  const stacked = settledDiscs([{ id: 'a', x: 700, y: 300 }, { id: 'b', x: 705, y: 303 }], room)
  ok(!touching(stacked.get('a')!, stacked.get('b')!), 'two dropped together do not cover each other')

  /* the column */
  eq(discsReach(settledDiscs(grid(4), room).values(), 440), DISC_CELL.y0 + DISC_FOOT.bottom + 8, 'one row: the column clears one row')
  eq(discsReach(seven.values(), 440), DISC_CELL.y0 + DISC_CELL.h + DISC_FOOT.bottom + 8, 'seven: it clears both')
  eq(discsReach(after.values(), 440), DISC_CELL.y0 + DISC_CELL.h + DISC_FOOT.bottom + 8, 'one moved to the page reserves nothing')
  eq(discsReach([{ x: 900, y: 24 }], 440), 0, 'none over it: nothing reserved')
  eq(discsReach([{ x: 100, y: 400 }], 440), 0, 'one put far down the column covers what it was put on, and reserves nothing')
  eq(discFlow(null, 1400), 1400, 'no column: the room')
  eq(discFlow(44, 1400), DISC_CELL.x0 + 2 * DISC_CELL.w + DISC_FOOT.right, 'a column drawn as the rail still gets a row of three')
  const floats = read('fluid/focus/Floats.tsx'), column = read('fluid/workspaces/Column.tsx')
  ok(/settledDiscs\(/.test(floats) && /settledDiscs\(/.test(column), 'the layer and the column read the one rule')
  ok(/\(disc \|\| slide\) && settled/.test(floats), 'a disc and its slide-out are drawn at its cell; a pane keeps its rectangle')
  ok(!/moveFloat\([^)]*settled/.test(floats), 'and nothing drawn is written back')
  const css = read('fluid/surface/magnet/magnet.css')
  ok(/\.mg-name \{[^}]*max-width: 104px[^}]*-webkit-line-clamp: 2/.test(css), 'a name keeps to the width and the two lines its cell leaves')
}

/* -- 2. Full screen and Put away -------------------------------------------------------- */
{
  const ops: MagnetOps = {
    notHere: () => null, config: () => cfg(), existing: () => null, create: async () => cfg(), reveal() {}, current: () => null, conversationName: () => 'C',
    showTab() {}, configure() {}, peek() {}, look() {}, remove: async () => {}, adapters: () => createAdapters(),
  }
  bindMagnetOps(ops)
  const at = (level: 'icon' | 'compact') => ({
    resource: { address: 'magnet:' + ID, kind: 'magnet' },
    surface: { id: ID, caps: { putAway: true, fullscreen: true, placementsBy: { wide: new Set(['dock', 'float']), medium: new Set(['launcher']), compact: new Set(['launcher']) } }, state: { kind: 'magnet', placement: { kind: 'float' }, level: { auto: level }, emphasis: 'none', binding: { mode: 'held' }, open: true } },
  }) as unknown as ActionTarget
  const of = (id: string) => magnetDefs(at('icon')).find((d) => d.id === id)!
  const wide = { cls: 'wide' } as ActionCtx, narrow = { cls: 'compact' } as ActionCtx
  for (const cx of [wide, narrow]) {
    const a = of('fullscreen').available(at('icon'), cx)
    ok(a.state === 'disabled' && /no full screen/.test(a.reason.message), `Full screen is disabled, with why, in ${cx.cls}`)
  }
  const atDisc = of('putAway').available(at('icon'), wide)
  ok(atDisc.state === 'disabled' && /already where it is put away/.test(atDisc.reason.message), 'Put away at its disc, wide: disabled, with why')
  const opened = magnetDefs(at('compact')).find((d) => d.id === 'putAway')!.available(at('compact'), wide)
  ok(opened.state === 'disabled' && /Collapse folds it back/.test(opened.reason.message), '… opened: it points to Collapse')
  eq(of('putAway').available(at('icon'), narrow).state, 'available', 'on a narrow screen, where there is a launcher, it is what it was')
  bindMagnetOps(null)
}

/* -- 3. plain words ---------------------------------------------------------------------- */
{
  eq(plainWords('NO. In [`mentis/web/permissions.py`](file:///C:/Work/Mentis-wt/agy-x/mentis/web/permissions.py#L10) it checks.'), 'NO. In mentis/web/permissions.py it checks.', 'the seen defect: a link\'s label and its code marks')
  eq(plainWords('NO. In [`mentis/web/permissions.py`](file:///C:/Work/Mentis-wt/agy-'), 'NO. In mentis/web/permissions.py', 'cut inside its address')
  eq(plainWords('See [the report'), 'See the report', 'cut inside its label')
  eq(plainWords('# Heading\n\n- **one** thing\n- _two_ things\n\n1. three ~~four~~\n\n> said'), 'Heading one thing two things three four said', 'headings, lists, marks and quotes')
  eq(plainWords('![a chart](https://x.test/a.png) and [ref][1]'), 'a chart and ref', 'a picture by its words, and a reference link')
  eq(plainWords('see file:///C:/tmp/a/report.pdf now'), 'see report.pdf now', 'a bare local address, by its file\'s name')
  eq(plainWords('snake_case_name and 2*3*4 stay'), 'snake_case_name and 2*3*4 stay', 'what only looks like a mark stays')
  eq(plainWords('Before\n\n```chart version=1\na,b\n1,2\n```\n\nafter'), 'Before after', 'a block a post carries says nothing here')
  eq(plainWords('```py\nprint(1)\n```'), 'print(1)', 'a code block\'s words stay, without its fence')
  eq(summaryLatest([{ latest: { id: 'a', at: 1, preview: '**[x](y)**' } }])?.preview, 'x', 'the card\'s Latest goes through it')
  eq(summaryLatest([{ latest: { id: 'a', at: 1, preview: '```chart version=1\na\n```' } }])?.preview, null, 'nothing left is no words')
}

/* -- 4. who is here --------------------------------------------------------------------- */
const live = (summary: Record<string, unknown>, results: MagnetResult[] = []): MagnetLive & { loading: boolean } =>
  ({ config: cfg(), loading: false, tabs: [], results, statuses: [], summaries: [{ source: SOURCE, summary: { title: 'Tidewater', ...summary } }] })
{
  const lead = (s: Record<string, unknown>) => renderToStaticMarkup(createElement(SummaryLead, { config: cfg(), live: live(s), unread: 0 }))
  ok(!/participant/i.test(lead({ posts: 4, participants: [] })), 'a source naming nobody says nothing of participants, not zero')
  ok(/1 participant</.test(lead({ participants: [{ id: 'p', alias: 'a' }] })), 'one named is one')
  eq(authorsHeld([{ kind: 'post', id: '1' }, { kind: 'post', id: '2' }, { kind: 'post', id: '3' }, { kind: 'file', id: 'f' }, { kind: 'post', id: 'gone' }],
    (id) => ({ '1': { author: 'A', author_name: '@ann' }, '2': { author: 'B', author_name: '@bo' }, '3': { author: 'A', author_name: '@ann' } } as Record<string, { author: string; author_name: string }>)[id]),
  { names: ['@ann', '@bo'], keys: ['A', 'B'], more: 0 }, 'who has posted, from posts already held, each once, reading nothing')
}

/* -- 5, 6. its name, its counts ---------------------------------------------------------- */
eq(magnetTitle('Tide alerts', 'Harbour notes'), 'Tide alerts', 'a zone\'s own name wins over its source\'s')
eq(magnetTitle(undefined, 'Harbour notes'), 'Harbour notes', 'none: its source\'s')
eq(magnetTitle(ID, 'Harbour notes'), 'Harbour notes', 'a reference is not a name')
eq(magnetTitle('Magnet', 'Harbour notes'), 'Harbour notes', '… nor is the word itself')
eq(magnetTitle(ID, undefined), ID, 'but better than nothing')
eq(magnetTitle(undefined, undefined), 'Magnet', 'nothing at all')
eq([countWords(1, 'post'), countWords(2, 'post'), countWords(0, 'file'), countWords(1, 'attachment')], ['1 post', '2 posts', '0 files', '1 attachment'], 'counts agree with their nouns')
ok(/magnetTitle\(z\.name, /.test(read('fluid/surface/magnet/MagnetZone.tsx')), 'the disc\'s title reads it')

/* -- 7, 8. a hover's read ----------------------------------------------------------------- */
{
  const wait = () => new Promise((r) => setTimeout(r, 0))
  const open: { path: string; resolve: (x: { status: number; body: unknown }) => void; signal?: AbortSignal }[] = []
  const get: RouteGet = (path, signal) => new Promise((resolve) => { open.push({ path, resolve, ...(signal ? { signal } : {}) }) })
  const route = createMagnetRoute(get)
  const key = 'conversation:' + SOURCE.conversation
  const ok200 = (results: unknown[] = []) => ({ status: 200, body: { sources: [{ key, status: 'ok', results }] } })

  /* it waits for what is running, and nothing runs beside it */
  const summary = route.summary(ID)
  const page = route.page(ID, key, ['post'])
  await wait()
  eq(open.length, 2, 'a summary and a page may run together, as ever: the class\'s two places')
  const glance = route.glance!(ID, key, ['post'])
  const another = route.summary('mag-00112233445566cc')
  await wait()
  eq(open.length, 2, 'a hover waits for both')
  open.shift()!.resolve({ status: 200, body: { sources: [] } })
  await summary
  await wait()
  eq(open.length, 1, 'it does not start with a page still running')
  open.shift()!.resolve(ok200())
  await page
  await wait()
  eq(open.length, 1, 'now it runs, alone')
  ok(/mode=page/.test(open[0].path), '… a bounded page')
  const summaryThenPage = route.page(ID, key, ['file'])
  await wait()
  eq(open.length, 1, 'and while it reads nothing else of this client\'s starts: it takes one place and never the second')
  open.shift()!.resolve(ok200())
  await glance
  await wait()
  eq(open.length, 2, 'then the rest go on')
  open.shift()!.resolve({ status: 200, body: { sources: [] } })
  open.shift()!.resolve(ok200())
  await Promise.all([another, summaryThenPage])

  /* leaving ends it, waiting or reading */
  const blocker = route.summary('mag-00112233445566dd')
  const c1 = new AbortController()
  const waiting = route.glance!(ID, key, ['post'], undefined, c1.signal)
  await wait()
  eq(open.length, 1, 'one is waiting behind a summary')
  c1.abort()
  open.shift()!.resolve({ status: 200, body: { sources: [] } })
  await blocker
  await assert.rejects(waiting, { name: 'AbortError' })
  await wait()
  eq(open.length, 0, 'left while waiting, it never reads')
  const c2 = new AbortController()
  void route.glance!(ID, key, ['post'], undefined, c2.signal).catch(() => {})
  await wait()
  ok(open[0].signal === c2.signal, 'a read running carries its signal, so leaving ends it on the server too')
  c2.abort()
  open.shift()!.resolve(ok200())
  await wait()

  /* Busy is a source's say, not a failure; and asked again, it is read */
  const answers = [{ status: 503, body: { kind: 'Busy', error: 'No room.' } }, ok200([{ kind: 'post', id: 'p1' }])]
  const busyRoute = createMagnetRoute(async () => answers.shift()!)
  const adapters = createAdapters()
  adapters.register(conversationAdapter({ route: { ...busyRoute, summary: async () => ({ sources: [{ key, status: 'ok', summary: { title: 'T' } }] }) }, posts: async () => { throw new Error('the store is not read') }, objects: async () => { throw new Error('the store is not read') }, search: async () => [], about: async () => ({ title: 'T' }) }) as never)
  const cache = createLive(adapters)
  const first = await cache.load(cfg(), BUILD_ENV, { glance: true })
  eq(first.statuses?.[0].status, 'busy', 'no room: the source says Busy')
  eq(first.results, [], '… with nothing lost, and no fall back to the store')
  const second = await cache.load(cfg(), BUILD_ENV, { glance: true })
  eq(second.results.map((r) => r.id), ['p1'], 'looked at again, it reads')
  const third = await cache.load(cfg(), BUILD_ENV, { glance: true })
  eq(third.results.map((r) => r.id), ['p1'], 'and a page in hand is not read a third time')
  eq(answers.length, 0, '… as two answers show')

  /* what the card draws */
  const row = (address: string, kind: string, n: number, preview: object | null = null) => ({ source: SOURCE, kind, id: address, value: { address, kind: 'media', title: address, post: 'p', number: n, preview } })
  const results = [
    ...Array.from({ length: 6 }, (_, i) => row(`pic${i}`, 'image', i, { artifact: { url: `/p${i}.png` } })),
    ...Array.from({ length: 5 }, (_, i) => row(`doc${i}.pdf`, 'file', i)),
  ] as MagnetResult[]
  const card = (page: Parameters<typeof MagnetPreview>[0]['page'], summary: Record<string, unknown> = {}) => renderToStaticMarkup(createElement(MagnetPreview, {
    id: ID, config: cfg(), title: 'Tidewater', unread: 0, status: magnetStatus(cfg(), { unread: 0, loading: false, held: 0, off: 0 }), live: live(summary), page, onEnter() {}, onLeave() {},
  }))
  const full = card({ results, loading: false, statuses: [] })
  eq((full.match(/<img /g) ?? []).length, 4, 'a small gallery: four of six')
  ok(full.includes('6 images &amp; media'), '… saying how many in all')
  eq((full.match(/mg-hover-file"/g) ?? []).length, 3, 'a compact file list: three of five')
  ok(full.includes('5 files'), '… saying how many in all')
  ok(full.includes('/p5.png') && !full.includes('/p0.png'), 'newest first')
  ok(!/<button(?![^>]*tabindex="-1")/.test(full), 'nothing in it takes focus: it describes the disc')
  ok(card({ results: [], loading: true, statuses: [] }).includes('Reading what it holds'), 'reading says so')
  const busy = card({ results: [], loading: false, statuses: [{ source: SOURCE, status: 'busy', reason: 'No room just now.' }] })
  ok(busy.includes('data-status="busy"') && busy.includes('Busy') && busy.includes('No room just now.'), 'Busy is drawn, with why')
  ok(!/error/i.test(busy), '… and is no error')
  const latest = { latest: { id: 'l', at: 1000, preview: 'Latest words' } }
  ok(card({ results: [], loading: false, statuses: [] }, latest).includes('Latest words'), 'before any post is in hand, the summary\'s Latest')
  ok(!card({ results: [{ source: SOURCE, kind: 'post', id: 'p', value: { post: 'p' } }], loading: false, statuses: [] }, latest).includes('Latest words'), 'recent posts then stand for it')

  const zone = read('fluid/surface/magnet/MagnetZone.tsx'), runtime = read('fluid/surface/magnet/runtime.ts')
  ok(/function Previewed[\s\S]*?useMagnet\(config, \{ glance: asks \}\)/.test(zone), 'only a rest\'s preview asks for the page, as a glance')
  ok(/asks < MAGNET_CHOICES\.glanceAsks/.test(zone), '… and asks again only where a source read part, a bounded number of times')
  ok(!/glance/.test(zone.slice(zone.indexOf('function Disc('), zone.indexOf('export function startMove'))), 'a disc itself never does')
  ok(/fetch\('\/fluid\/api\/posts\?ids=' \+[^\n]*signal/.test(runtime) && !/thread=1/.test(runtime.slice(runtime.indexOf('readGlances'))), 'a hover\'s words: just its few posts, no threads, ended by leaving')
}

/* -- 9. who has a live run ---------------------------------------------------------------- */
{
  const summary = read('fluid/surface/magnet/Summary.tsx')
  ok(/useActivity\(\)[\s\S]*?workingIn\(all, s\.conversation\)/.test(summary), 'read from the one activity reader, for this Magnet\'s conversations')
  ok(!/fetch\(/.test(summary), 'with no read of its own')
  const css = read('fluid/surface/magnet/magnet.css')
  ok(/\.mg-person\[data-working\] \{[^}]*--live/.test(css), 'a ring on who has a run')
  ok(/Working now: /.test(summary), '… and words, so colour is not all that says it')
  const preview = summary.slice(summary.indexOf('export function MagnetPreview'))
  ok(preview.indexOf('<WorkingLine') < preview.indexOf('<HoverHolds'), '… above what it holds, which may run past the card\'s height')
}

/* -- 10. its theme ------------------------------------------------------------------------- */
{
  const css = read('fluid/surface/magnet/magnet.css')
  const rule = (selector: string) => {
    const at = css.indexOf(selector + ' {')
    return at < 0 ? '' : css.slice(at, css.indexOf('}', at))
  }
  ok(/background: var\(--canvas\)/.test(rule('.mg-at-icon[data-theme="minimal"] .mg-disc, .mg-slide[data-theme="minimal"] > .mg-disc')), 'minimal: a plain mark')
  ok(/display: none/.test(rule('.mg-at-icon[data-theme="minimal"] .mg-orbit')), '… with no orbit')
  ok(/border-radius: 10px/.test(rule('.mg-at-icon[data-theme="anchored"] .mg-disc, .mg-slide[data-theme="anchored"] > .mg-disc')), 'anchored: square')
  ok(/content: ''/.test(rule('.mg-at-icon[data-theme="anchored"] .mg-disc::after')), '… on a stem')
  ok(/transparent/.test(rule('.mg-at-icon[data-theme="glass"] .mg-disc, .mg-slide[data-theme="glass"] > .mg-disc')) && /backdrop-filter/.test(rule('.mg-at-icon[data-theme="glass"] .mg-disc, .mg-slide[data-theme="glass"] > .mg-disc')), 'glass: clear and frosted')
  ok(/translateY/.test(rule('.mg-at-icon[data-theme="floating"] .mg-disc, .mg-slide[data-theme="floating"] > .mg-disc')), 'floating: lifted')
  for (const t of ['minimal', 'anchored', 'floating'])
    ok(new RegExp(`\\.mg-preview\\[data-theme="${t}"\\], \\.mg-at-icon\\[data-theme="${t}"\\] \\.mg-card \\{[^}]*border-radius`).test(css), `${t} has a shape of its own on its card`)
  ok(/prefers-reduced-transparency: reduce\) \{\s*\.mg-at-icon\[data-theme="glass"\] \.mg-disc[^{]*\{ background: var\(--accent\)/.test(css), 'less transparency: a glass disc is solid')
  ok(/\.mg-at-icon\[data-theme="glass"\] \.mg-card \{ background: var\(--surface-raised\)/.test(css), '… and its card')
}

console.log(`fluid magnet marker: ${checks} checks passed`)
