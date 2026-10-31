/* MAGNET POLISH (owner Turn #1592; request Turn #1595). What it adds to the
 * one universal Magnet, and what this test holds it to:
 *
 *   1. visibility: an opaque face, a canvas-coloured halo, an accent rim, a
 *      name plate and badges, legible in every atmosphere (WCAG contrast from
 *      the theme tokens), its coarse-pointer target and touch-trigger geometry
 *      untouched;
 *   2. the orbit: arcs per kind it holds, satellites for what is new, its
 *      state in the ring, and nothing turning under reduced motion;
 *   3. the editor: every facet of the SAME config, sent through
 *      magnet.reconfigure, with unavailable values kept and explained;
 *   4. the summary card: posts, files, images and media, attachments (and any
 *      other kind it selects), counted and listed from its live results and
 *      its source's own totals, never a copied history;
 *   5. free movement: the disc moves its own window and nothing else, through
 *      the existing placement path, docking and opening nothing. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Holder, workspace, type Arr } from '../src/fluid/workspace/place'
import { keepSlot, type Zone } from '../src/fluid/workspace/tree'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, type Ops } from '../src/fluid/surface/actions/providers/ops'
import type { MagnetConfig, MagnetLive, MagnetResult, MagnetSeed } from '../src/fluid/surface/magnet/types'
import { MAGNET_CHOICES, conversationSeed } from '../src/fluid/surface/magnet/choices'
import {
  BUILD_ENV, SELECTION_KEPT, changeOf, createAdapters, draftProblems, glyphOf, holdingOf, holdingWords, magnetStatus, notRunning,
  orbitArcs, sourceChoices, tidySelection,
} from '../src/fluid/surface/magnet/model'
import { conversationAdapter, objectTypeOf, pictureOf, type ConversationReads, type ObjectRow } from '../src/fluid/surface/magnet/conversation'
import { createLive, revisionOf } from '../src/fluid/surface/magnet/live'
import { Orbit, arcPath } from '../src/fluid/surface/magnet/Orbit'
import { SummaryBody } from '../src/fluid/surface/magnet/Summary'
import { Editor } from '../src/fluid/surface/magnet/Editor'
import { MagnetZone } from '../src/fluid/surface/magnet/MagnetZone'
import { setDraft } from '../src/fluid/surface/magnet/client'
import type { ZoneCtl } from '../src/fluid/workspace/TreeView'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')
const count = (s: string, re: RegExp) => (s.match(re) ?? []).length
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0)) }

/* the network, recorded */
type Call = { url: string; method: string; body: Record<string, any> | null }
const calls: Call[] = []
let kept: { layout: unknown; saved: number | null } = { layout: null, saved: null }
let answer: (body: Record<string, any>, url: string) => unknown = () => ({})
;(globalThis as any).fetch = async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase()
  const body = init?.body ? JSON.parse(String(init.body)) : null
  calls.push({ url: String(url), method, body })
  const reply = String(url).endsWith('/layouts') ? { layouts: [], defaults: { home: null, conversation: null, unnamed: null } }
    : method === 'GET' ? kept : answer(body, String(url))
  return new Response(JSON.stringify(reply), { status: 200, headers: { 'Content-Type': 'application/json' } })
}
bindOps(new Proxy({} as Ops, { get: (_, k) => (k === 'confirm' ? () => false : () => {}) }))
installProviders()

const ID = 'mag-00112233445566aa' as const
const cfg = (over: Partial<MagnetConfig> = {}): MagnetConfig => ({ id: ID, ...conversationSeed('c1'), ...over })

/* -- 1. what an object is: images and media, files, attachments, links, forms ------- */
const row = (address: string, is: NonNullable<NonNullable<ObjectRow['preview']>['is']> | null, extra: Partial<ObjectRow> = {}): ObjectRow =>
  ({ address, kind: 'media', title: address, post: 'p', number: 1, preview: is ? { is } : null, ...extra })
const all = new Set(['post', 'file', 'image', 'attachment', 'link', 'form'])
eq(objectTypeOf(row('pic', { family: 'media', word: 'image', source: 'attachment' }), all), 'image', 'an attached picture is an image')
eq(objectTypeOf(row('vid', { family: 'media', word: 'video', source: 'link' }), all), 'image', 'a video (even a video link) is media, with images')
eq(objectTypeOf(row('doc', { family: 'file', word: 'doc', source: 'attachment' }), all), 'attachment', 'a file attached to a post is an attachment')
eq(objectTypeOf(row('ret', { family: 'file', word: 'file', source: 'returned' }), all), 'file', 'a file a run returned is a file')
eq(objectTypeOf(row('doc', { family: 'file', source: 'attachment' }), new Set(['post', 'file', 'image'])), 'file',
  'a Magnet that selects files but not attachments still sees its attached files, as files')
eq(objectTypeOf(row('url', { family: 'link', source: 'link' }), all), 'link', 'a link is a link')
eq(objectTypeOf(row('frm', { family: 'section', fillable: true }), all), 'form', 'something to fill in is a form')
eq(objectTypeOf(row('sec', { family: 'section' }), all), null, 'a section of a post\'s own words is none of them')
eq(objectTypeOf({ address: 'old', kind: 'figure', title: 'x', post: 'p', number: 1, preview: { type: 'image/png' } }), 'image', 'an undescribed row is read from its words, as before')
eq(pictureOf(row('a', null, { preview: { artifact: { url: '/x.png' } } })), '/x.png', 'a picture is read from its artifact')
eq(pictureOf(row('b', null, { preview: { ref: 'adm-1' } })), '/api/artifacts/adm-1', '… or its reference')

/* the adapter, by selection: attachments apart when selected; summary totals from the source */
const reads: string[] = []
const rows: ObjectRow[] = [
  row('live:p3:pic', { family: 'media', word: 'image', source: 'figure' }, { number: 3 }),
  row('live:p2:doc', { family: 'file', source: 'attachment' }, { number: 2 }),
  row('live:p1:out', { family: 'file', source: 'returned' }, { number: 1 }),
  row('live:p4:url', { family: 'link', source: 'link' }, { number: 4 }),
]
const fake: ConversationReads = {
  posts: async (c) => { reads.push(`posts(${c})`); return { ids: [`${c}-p4`, `${c}-p3`, `${c}-p2`] } },
  objects: async (c) => { reads.push(`objects(${c})`); return rows },
  search: async () => [],
  about: async (c) => { reads.push(`about(${c})`); return { title: c === 'c1' ? 'Tidewater' : 'Harbour', activity: 1000, about: 'A survey of the tide.', posts: 240 } },
}
const adapters = createAdapters()
adapters.register(conversationAdapter(fake))
const live = createLive(adapters)
const m = cfg()
const l = await live.load(m, BUILD_ENV)
eq(l.results.map((x) => `${x.kind}:${x.id}`), ['post:c1-p4', 'post:c1-p3', 'post:c1-p2', 'image:live:p3:pic', 'attachment:live:p2:doc', 'file:live:p1:out'],
  'a new conversation Magnet collects posts, files, images and media, and attachments, each its own kind; links it does not select')
eq(l.summaries[0].summary, { title: 'Tidewater', initial: 'T', activity: 1000, about: 'A survey of the tide.', posts: 240 }, 'its summary carries what the source says of itself and its own post total')
const noAttach = await live.load(cfg({ id: 'mag-noattach', selection: { informationTypes: ['post', 'file', 'image'] } }), BUILD_ENV)
eq(noAttach.results.filter((x) => x.kind !== 'post').map((x) => `${x.kind}:${x.id}`), ['image:live:p3:pic', 'file:live:p2:doc', 'file:live:p1:out'],
  'an older Magnet (posts, files, images) keeps every file it showed')

/* -- 2. what it holds, its orbit, its state -------------------------------------- */
const h = holdingOf(l.results, 240)
eq(h, [{ type: 'post', count: 240 }, { type: 'file', count: 1 }, { type: 'image', count: 1 }, { type: 'attachment', count: 1 }],
  'holding: posts are the source\'s total, other kinds counted from the live results, in the fixed order')
eq(holdingWords(h), '240 posts, 1 files, 1 images & media, 1 attachments', 'said in words for the disc\'s label')
eq(holdingWords([]), 'nothing yet', '… or that it holds nothing yet')
const arcs = orbitArcs(h)
eq(arcs.map((a) => a.type), ['post', 'file', 'image', 'attachment'], 'one arc per kind it holds')
ok(arcs.every((a, i) => a.to > a.from && (i === 0 || a.from > arcs[i - 1].to)), 'arcs run clockwise with a gap between each')
ok(arcs.at(-1)!.to <= 1 && arcs[0].from >= 0, '… within one turn')
ok(arcs.slice(1).every((a) => a.to - a.from >= 0.05), 'a kind with few items still has an arc that can be seen')
ok(arcs[0].to - arcs[0].from > 0.5, 'the kind it holds most has the most of the ring')
eq(orbitArcs([{ type: 'post', count: 3 }]), [{ type: 'post', from: 0, to: 1 }], 'one kind: the whole ring')
ok(/^M [\d.]+ [\d.]+ A 34 34 0 1 1 [\d.]+ [\d.]+ A/.test(arcPath(0, 1, 34)), 'a whole ring is drawn as two half arcs')

const st = (o: Partial<Parameters<typeof magnetStatus>[1]> = {}, c: MagnetConfig | undefined = m) =>
  magnetStatus(c, { unread: 0, loading: false, held: 3, off: 0, ...o })
eq(magnetStatus(undefined, { unread: 0, loading: false, held: 0, off: 0 }).state, 'missing', 'no config: missing')
eq(st({ error: 'gone', unread: 4 }).state, 'error', 'an error before anything else')
eq(st({ loading: true, held: 0 }).state, 'reading', 'reading, while it holds nothing yet')
eq(st({ loading: true, held: 3 }).state, 'quiet', 'a refresh of what it holds is not shown as reading')
eq(st({ unread: 2 }, cfg({ collection: { mode: 'paused' } })).state, 'paused', 'paused, said before what is new')
eq([st({ unread: 2 }).state, st({ unread: 2 }).words], ['new', '2 new since you last opened it'], 'new items, counted')
eq(st({ off: 1 }).limited, true, 'what it asks but this build does not run is said beside its state')
eq([glyphOf(m), glyphOf(cfg({ sources: [{ kind: 'conversation', conversation: 'c1' }, { kind: 'web', domain: 'x.org' }] }))], ['conversation', 'mixed'], 'its source badge')

{
  const html = renderToStaticMarkup(createElement(Orbit, { holding: h, state: 'new', unread: 5, renderer: 'disc' }))
  eq(count(html, /class="mg-arc"/g), 4, 'the orbit draws an arc per kind')
  ok(/data-type="attachment"/.test(html) && /data-type="post"/.test(html), '… each marked with its kind (its colour)')
  eq(count(html, /class="mg-sat"/g), 3, 'new items are satellites, at most three')
  ok(html.includes('class="mg-orbit-halo"') && html.includes('aria-hidden="true"'), 'over a halo, and decorative: the disc\'s label says it')
  const reading = renderToStaticMarkup(createElement(Orbit, { holding: [], state: 'reading', unread: 0, renderer: 'ring' }))
  ok(reading.includes('class="mg-orbit-empty"') && !reading.includes('mg-sat') && reading.includes('data-renderer="ring"'), 'reading is the empty ring; the ring renderer draws it heavier')
}
const css = read('fluid/surface/magnet/magnet.css')
const reduced = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
ok(reduced.length > 0 && /\.mg-sats, \.mg-orbit-empty, \.mg-orbit-arcs/.test(reduced) && /animation: none !important/.test(reduced),
  'reduced motion: the satellites, the reading ring and the pulse stand still')
ok(/\.mg-sats \{[^}]*animation: mg-orbit/.test(css) && /\[data-state="reading"\] \.mg-orbit-empty \{[^}]*animation: mg-orbit/.test(css), '… which otherwise turn')

/* -- 3. visibility: legible on every atmosphere ------------------------------------ */
{
  const lum = (hex: string) => {
    const n = hex.replace('#', '')
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }
  const contrast = (a: string, b: string) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
  /* a translucent colour, laid over the canvas it sits on */
  const solid = (v: string, under: string): string | null => {
    if (/^#[0-9a-f]{6}$/i.test(v)) return v
    const m = /^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)$/.exec(v)
    if (!m) return null
    const u = [1, 3, 5].map((i) => parseInt(under.slice(i, i + 2), 16))
    const a = Number(m[4])
    return '#' + [1, 2, 3].map((i, j) => Math.round(Number(m[i]) * a + u[j] * (1 - a)).toString(16).padStart(2, '0')).join('')
  }
  const atm = read('atmosphere.css')
  const blocks = [...atm.matchAll(/:root(?:\[data-atmosphere='([a-z]+)'\])? \{([^}]*)\}/g)]
  const tok = (body: string, name: string) => /^#|^rgba/.test((new RegExp(`--${name}:\\s*([^;]+);`).exec(body)?.[1] ?? '').trim())
    ? new RegExp(`--${name}:\\s*([^;]+);`).exec(body)![1].trim() : null
  let seen = 0
  const worst = { face: 99, plate: 99, rim: 99, badge: 99 }
  for (const [, name, body] of blocks) {
    const canvas = tok(body, 'canvas'), accent = tok(body, 'accent'), ink = tok(body, 'accent-ink'), text = tok(body, 'text'), raised = tok(body, 'surface-raised'), att = tok(body, 'attention')
    if (!canvas || !accent || !ink || !text || !raised || !att || !/^#/.test(canvas)) continue
    seen++
    const plate = solid(raised, canvas)!
    const face = contrast(solid(canvas, canvas)!, solid(accent, canvas)!)
    const rim = contrast(solid(ink, canvas)!, canvas)
    const pl = contrast(solid(text, canvas)!, plate)
    const badge = contrast(canvas, solid(att, canvas)!)
    worst.face = Math.min(worst.face, face); worst.plate = Math.min(worst.plate, pl); worst.rim = Math.min(worst.rim, rim); worst.badge = Math.min(worst.badge, badge)
    ok(face >= 3, `${name ?? 'default'}: the initial on the face is large-text legible (${face.toFixed(2)}:1)`)
    ok(rim >= 3, `${name ?? 'default'}: the accent rim stands off its canvas-coloured halo (${rim.toFixed(2)}:1, non-text 3:1)`)
    ok(pl >= 4.5, `${name ?? 'default'}: the name plate reads at text contrast (${pl.toFixed(2)}:1)`)
    ok(badge >= 3, `${name ?? 'default'}: the unread and status badges read (${badge.toFixed(2)}:1)`)
  }
  ok(seen >= 8, `every atmosphere with its own colours was checked (${seen})`)
  console.log(`  contrast, worst over ${seen} atmospheres: face ${worst.face.toFixed(2)}, rim ${worst.rim.toFixed(2)}, plate ${worst.plate.toFixed(2)}, badge ${worst.badge.toFixed(2)}`)
  /* the disc is opaque, haloed and rimmed; every colour is a token */
  /* the frame's reset (.fx button: background none, colour inherited) outranks a
     bare .mg-disc: that is what left the stage-A disc see-through */
  ok(/\.fx button \{[^}]*background: none/.test(read('fluid/frame/frame.css')) && /\n\.fx \.mg-disc, \.mg-disc \{/.test(css),
    'the disc\'s face is set above the frame\'s button reset, so it is never see-through')
  for (const b of ['mg-tab', 'mg-row', 'mg-line', 'mg-link', 'mg-chip', 'mg-thumb'])
    ok(new RegExp(`\\n\\.mg-zone \\.${b} \\{`).test(css), `… and so is every other Magnet button's look (${b})`)
  ok(/\.wk-float\.fq-magnet\[data-level="icon"\], \.mg-at-icon, \.mg-at-icon > \.mg-frame, \.mg-at-icon > \.mg-frame > \.sc-body \{ pointer-events: none; \}/.test(css)
    && /\.mg-at-icon \.mg-disc, \.mg-at-icon \.sc-access, \.mg-at-icon \.mg-card \{ pointer-events: auto; \}/.test(css),
    'at its disc only the round disc, its ⋯ and its card take a press: a square box never covers a neighbouring disc')
  const disc = /\.mg-disc \{([^}]*)\}/.exec(css)![1]
  ok(/background: var\(--accent\)/.test(disc) && /color: var\(--canvas\)/.test(disc), 'an opaque face in the accent, its initial in the canvas colour')
  ok(/box-shadow: 0 0 0 2px var\(--canvas\), 0 0 0 4px var\(--accent-ink\)/.test(disc), 'a canvas-coloured halo, then an accent rim: it stands off any background')
  ok(/width: 56px/.test(disc) && MAGNET_CHOICES.disc >= 44, 'the disc stays 56 px: above the 44 px touch target')
  ok(/touch-action: none/.test(disc), 'a touch on it is the disc\'s (to tap, hold or move), never a page pan')
  const name = /\.mg-name \{([^}]*)\}/.exec(css)![1]
  ok(/background: var\(--surface-raised\)/.test(name) && /pointer-events: none/.test(name), 'its name on an opaque plate, which takes no press (the target is the disc)')
  ok(/\[data-access='trigger'\] \.mg-name \{ top: auto; bottom: calc\(100% \+ 15px\); \}/.test(css), 'on touch the name sits above, clear of the ⋯ beneath')
  ok(/\.mg-at-icon > \.mg-frame\[data-access='trigger'\] > \.sc-access \{ right: -36px; bottom: -36px; \}/.test(css), 'the touch trigger geometry (F6) is unchanged')
}

/* -- 4. the disc, drawn ------------------------------------------------------------ */
const zoneAt = (level: 'icon' | 'compact'): Zone => ({ type: 'zone', id: ID, show: 'magnet', name: 'Tidewater', options: { magnet: ID }, level } as Zone)
const arrAt = (level: 'icon' | 'compact', c: MagnetConfig = m): Arr => ({
  tree: { type: 'zone', id: 'a', show: 'objects', name: 'a', slot: keepSlot() } as Zone, pages: [],
  focus: { floats: [{ id: 'w-1', zone: zoneAt(level), x: 24, y: 24, w: 360, h: 480 }] }, magnets: { [ID]: c },
} as Arr)
const drawn = (level: 'icon' | 'compact', c: MagnetConfig = m, move = true) => {
  workspace.quiet(() => arrAt(level, c))
  return renderToStaticMarkup(createElement(MagnetZone, {
    z: zoneAt(level), r: { x: 0, y: 0, w: 360, h: 480 }, ctl: { drag: () => {} } as unknown as ZoneCtl, page: '', first: false,
    floating: { id: ID, props: { onPointerDown: () => {} }, ...(move ? { move: () => {}, raise: () => {} } : {}) },
  }))
}
{
  const html = drawn('icon')
  ok(/<button type="button" class="mg-disc" data-renderer="disc" data-state="[a-z]+" data-glyph="conversation"/.test(html), 'the disc says its renderer, state and source')
  ok(html.includes('class="mg-orbit"') && html.includes('class="mg-face"') && html.includes('class="mg-src"') && html.includes('class="mg-name"'),
    'its orbit, face, source badge and name plate')
  ok(/aria-label="Tidewater: a magnet of a conversation\. [^"]*It holds [^"]*drag to move it\."/.test(html), 'its label says what it reads, how it is, what it holds and that it moves')
  ok(!drawn('icon', m, false).includes('drag to move it'), 'without a window to move, it does not offer to move')
  const limited = drawn('icon', cfg({ notifications: { newItems: true, changes: false, failures: false } }))
  ok(limited.includes('class="mg-state"') && limited.includes('data-limited="true"'), 'what it asks but this build does not run shows a status badge')
}

/* -- 5. the summary: posts, files, images and media, attachments ---------------------- */
{
  const res = (kind: string, id: string, n: number): MagnetResult => ({ source: { kind: 'conversation', conversation: 'c1' }, kind, id,
    value: kind === 'post' ? { post: id } : { address: id, kind: 'media', title: id, post: 'p', number: n, preview: { artifact: { url: `/a/${id}.png` } } } })
  const lv: MagnetLive & { loading: boolean } = {
    config: m, loading: false, tabs: [],
    summaries: [{ source: m.sources[0], summary: { title: 'Tidewater', about: 'A survey of the tide.', posts: 240, activity: 1000 } }],
    results: [res('post', 'p9', 9), res('post', 'p8', 8), res('image', 'i1', 1), res('image', 'i5', 5), res('attachment', 'a1', 2), res('file', 'f1', 3)],
  }
  const status = magnetStatus(m, { unread: 2, loading: false, held: 6, off: 0 })
  const html = renderToStaticMarkup(createElement(SummaryBody, { id: ID, config: m, title: 'Tidewater', live: lv, unread: 2, status, workspace: () => {} }))
  ok(html.includes('A survey of the tide.') && html.includes('2 new') && html.includes('From a conversation'), 'its summary: what the source says, what is new, where it reads')
  ok(/No synthesized summary: synthesis is manual/.test(html), 'it says no synthesized summary exists, and why')
  for (const [t, n] of [['post', 240], ['file', 1], ['image', 2], ['attachment', 1]] as const)
    ok(new RegExp(`data-type="${t}" data-count="${n}"`).test(html), `${t}: counted (${n})`)
  ok(html.indexOf('/a/i5.png') < html.indexOf('/a/i1.png'), 'images and media as thumbnails, newest first')
  eq(count(html, /class="mg-link mg-all"/g), 4, 'each kind it holds opens the Magnet at that kind ("All")')
  ok(html.includes('Open as workspace') && html.includes('Configure'), 'and the Magnet itself: Configure, Open as workspace')
  const narrow = renderToStaticMarkup(createElement(SummaryBody, { id: ID, config: cfg({ selection: { informationTypes: ['post', 'image', 'link'] } }), title: 'Tidewater', live: lv, unread: 0, status }))
  ok(/data-type="attachment"><h4>[\s\S]*?Not collected by this magnet/.test(narrow) && /data-type="file"><h4>[\s\S]*?Not collected/.test(narrow),
    'a kind it does not collect is said, with Configure')
  ok(/data-type="link" data-count="0"/.test(narrow), 'and any other kind it selects is accounted for too')
  const sumSrc = read('fluid/surface/magnet/Summary.tsx')
  ok(!/fetch\(|store\.load|getJson|postJson/.test(sumSrc), 'the summary reads nothing of its own: it is the live results and the source\'s summary')
}

/* -- 6. the editor: the same config, every facet, reasons for what is not run --------- */
{
  eq(changeOf(m, { ...conversationSeed('c1') }), {}, 'nothing changed: nothing to send')
  const next: MagnetSeed = { ...conversationSeed('c2'), selection: { informationTypes: ['image'] }, presentation: { renderer: 'gallery' } }
  eq(Object.keys(changeOf(m, next)).sort(), ['presentation', 'selection', 'sources'], 'only the facets that changed are sent')
  eq(tidySelection({ criteria: '  ', phrases: ['a', ' ', 'b '], dates: { after: '', before: '2026-10-01' }, informationTypes: ['image', 'post'] }),
    { phrases: ['a', 'b'], informationTypes: ['post', 'image'], dates: { before: '2026-10-01' } }, 'a cleared field is left out, types in their fixed order')
  eq(draftProblems({ ...next, sources: [] }), ['A Magnet reads at least one source.'], 'a Magnet reads at least one source')
  ok(draftProblems({ ...next, sources: [{ kind: 'conversation', conversation: '' }] })[0].includes('Choose the conversation'), 'a new conversation source names its conversation')
  ok(draftProblems({ ...next, selection: { informationTypes: [] } })[0].includes('at least one type'), 'it collects at least one type')
  ok(draftProblems({ ...next, collection: { mode: 'scheduled' } })[0].includes('schedule'), 'a schedule needs its timing')
  const kinds = sourceChoices(BUILD_ENV, adapters)
  eq(kinds.map((k) => [k.kind, k.availability.state]), [['brain', 'disabled'], ['conversation', 'available'], ['connector', 'disabled'], ['web', 'disabled'], ['other', 'disabled']],
    'every source kind is offered; only what this build reads is available')
  ok(kinds.every((k) => k.availability.state === 'available' || (k.availability.state === 'disabled' && k.availability.reason.message.length > 10)), '… the rest each with its reason')
  const asks = notRunning(cfg({ selection: { informationTypes: ['post'], phrases: ['tide'] }, collection: { mode: 'paused' } }), BUILD_ENV, adapters)
  eq(asks.map((x) => x.facet), ['selection', 'collection'], 'phrases and a pause are kept and said')
  ok(asks[0].reason.message.includes(SELECTION_KEPT) && asks[1].reason.message.startsWith('Paused'), '… each with what this build does with it')

  workspace.quiet(() => arrAt('compact'))
  const form = renderToStaticMarkup(createElement(Editor, { id: ID, config: m, at: 'all' }))
  for (const part of ['sources', 'collects', 'when', 'presentation']) ok(form.includes(`data-part="${part}"`), `the editor has its ${part}`)
  ok(/aria-label="Source 1: conversation"/.test(form), 'the conversation source is chosen from the conversations, as a value')
  eq(count(form, /type="checkbox" checked=""/g), 4, 'the types it selects are ticked (posts, files, images and media, attachments)')
  ok(/class="mg-chip" aria-disabled="true" title="Reading the web is not in this build\."/.test(form), 'an unavailable source kind is offered disabled, with its reason')
  ok(/<button type="submit" class="fl-btn mg-save" disabled="">Save<\/button>/.test(form), 'with nothing changed, Save waits')
  setDraft(ID, { ...conversationSeed('c1'), presentation: { renderer: 'ring' } })
  const edited = renderToStaticMarkup(createElement(Editor, { id: ID, config: m, at: 'all' }))
  ok(/<button type="submit" class="fl-btn mg-save">Save<\/button>/.test(edited) && edited.includes('Discard'), 'a change: Save, or Discard')
  ok(/value="ring" checked=""|checked="" value="ring"|name="mg-renderer-[^"]+" checked=""/.test(edited), 'the draft is what the editor shows')
  const pane = drawn('compact')
  ok(pane.includes('aria-label="Summary"') && pane.includes('aria-label="Configure"'), 'the pane offers its Summary and Configure beside its tabs')
  setDraft(ID, null)
  const ed = read('fluid/surface/magnet/Editor.tsx')
  ok(/saveConfig\(id, change\)/.test(ed) && !/createMagnet|conversationSeed/.test(ed), 'the editor saves the same Magnet through reconfigure: never a new one')
  ok(!/kind === 'conversation' \? .*magnet\.(configure|reconfigure)/.test(ed), 'no conversation-only configuration path')
}

/* the client's reconfigure: the same id, its zone and place untouched */
{
  const stored = { format: 'mentis.fluid-arrangement', version: 3, tree: { type: 'zone', id: 'a', show: 'objects', name: 'a', slot: keepSlot() },
    focus: { floats: [{ id: 'w-1', zone: zoneAt('icon'), x: 300, y: 200, w: 360, h: 480 }] }, magnets: { [ID]: m } }
  kept = { layout: stored, saved: 10 }
  const hold = new Holder(() => ({ tree: { type: 'zone', id: 'start', show: 'objects', name: 'start', slot: keepSlot() } as Zone, pages: [] }))
  hold.enter('c1', 'conversation')
  await flush()
  const change = changeOf(m, { ...conversationSeed('c2'), selection: { informationTypes: ['image'] } })
  const after: MagnetConfig = { ...m, ...change } as MagnetConfig
  answer = (_b, url) => (url.endsWith('/reconfigure') ? { key: 'c1', saved: 11, magnet: after, layout: { ...stored, magnets: { [ID]: after } } } : {})
  calls.length = 0
  const got = await hold.reconfigureMagnet(ID, change)
  const sent = calls.find((c) => c.method === 'POST')!
  ok(sent.url.endsWith(`/arrangements/c1/magnets/${ID}/reconfigure`), 'the editor\'s save is magnet.reconfigure on its id')
  eq(Object.keys(sent.body!).sort(), ['change', 'op'], '… sending the change and an operation key only')
  eq(got.id, ID, 'the same Magnet comes back')
  const f = hold.arr.focus!.floats!.find((x) => x.zone.id === ID)!
  eq([f.x, f.y, f.zone.id, f.zone.options], [300, 200, ID, { magnet: ID }], 'its zone, id and place are untouched')
  eq(hold.arr.magnets?.[ID]?.sources, [{ kind: 'conversation', conversation: 'c2' }], 'its config is the new one')
  ok(revisionOf(after) !== revisionOf(m), 'a change of what it collects is a new revision: it reads again')
  reads.length = 0
  const re = await live.load(after, BUILD_ENV)
  ok(reads.includes('objects(c2)') && !reads.some((x) => x.includes('(c1)')) && !reads.includes('posts(c2)'),
    'the same Magnet now reads its new source, and only what it now selects (images: the object index, no posts)')
  ok(re.results.every((x) => x.kind === 'image' && (x.source as { conversation: string }).conversation === 'c2'), '… and shows the new type, from it')
}

/* -- 7. free movement: its own window, nothing else ------------------------------- */
{
  const drag = read('fluid/focus/drag.ts')
  ok(/export function moveFloatFrom\(id: string, at: \{ x: number; y: number \}, origin: HTMLElement, label: string\)/.test(drag)
    && /beginDragNow\(\{ type: 'float', id, only: 'move' \}, from, origin, label\)/.test(drag), 'the disc moves its window through the one drag path (beginDragNow), as a move only')
  ok(/const t = d\.payload\.type === 'float' && d\.payload\.only === 'move' \? undefined : d\.target/.test(drag), 'a move docks and keeps nowhere: no target is taken')
  ok(/workspace\.live\(onPage\(\(v\) => moveFloat\(v, id, planned\?\.rect \?\? raw\), startPage\)/.test(drag), 'only that window\'s rectangle is moved (moveFloat on its id)')
  const dock = read('fluid/focus/DockLayer.tsx')
  ok(/const moveOnly = drag\?\.payload\.type === 'float' && drag\.payload\.only === 'move'/.test(dock) && /if \(!drag\?\.started \|\| moveOnly\) return null/.test(dock),
    'and no dock pad is offered while it moves')
  const floats = read('fluid/focus/Floats.tsx')
  ok(/move: \(at\) => \{ if \(el\.current\) \{ adopt\(\); moveFloatFrom\(f\.id, at, el\.current, name\) \} \}/.test(floats), 'each window lends its own move: one Magnet, one window')
  const zone = read('fluid/surface/magnet/MagnetZone.tsx')
  ok(/const move = at === 'float' \? floating\?\.move : undefined/.test(zone), 'a disc moves freely only as a window; a section or the stack places it by its own rules')
  ok(!/openAsWorkspace|expand/.test(zone.slice(zone.indexOf('function startMove('), zone.indexOf('/* -- the pane'))), 'a move opens nothing')
}

console.log(`fluid magnet polish: ${checks} checks passed`)
