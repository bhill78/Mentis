/* MAGNET PRESENCE (package D2). What it adds to the existing surface, and what
 * this test holds it to:
 *
 *   1. a Magnet's theme draws in its full zone, its placement's Look over it
 *      property by property, and changes nothing it holds or how it is kept;
 *   2. its preview, on a rest or keyboard focus: identity, activity and latest
 *      finding, from its summary, reading no page, held in the viewport;
 *   3. a compact file list and a small gallery, opening the existing float;
 *   4. optional participant and latest fields, per source: absence draws
 *      nothing and says no error, and active-now is not drawn or implied. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement, type ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { workspace, type Arr } from '../src/fluid/workspace/place'
import { keepSlot, type Zone } from '../src/fluid/workspace/tree'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, type Ops } from '../src/fluid/surface/actions/providers/ops'
import { provide, type ObjectTarget } from '../src/fluid/objects/actions'
import type { MagnetConfig, MagnetLive, MagnetResult, MagnetSourceAdapter } from '../src/fluid/surface/magnet/types'
import { MAGNET_CHOICES, conversationSeed } from '../src/fluid/surface/magnet/choices'
import { BUILD_ENV, changeOf, createAdapters, magnetLook, magnetStatus, notRunning } from '../src/fluid/surface/magnet/model'
import { MAGNET_THEME_LOOK, PREVIEW_REACH, participantsBeyond, previewPlacement, summaryLatest } from '../src/fluid/surface/magnet/presentation'
import { conversationAdapter, type ConversationReads, type ObjectRow } from '../src/fluid/surface/magnet/conversation'
import { createLive } from '../src/fluid/surface/magnet/live'
import type { MagnetRoute, RouteAnswer } from '../src/fluid/surface/magnet/route'
import { MagnetPreview, SummaryBody, previewIdOf } from '../src/fluid/surface/magnet/Summary'
import { FileList, ImageGallery } from '../src/fluid/surface/magnet/Objects'
import { MagnetZone } from '../src/fluid/surface/magnet/MagnetZone'
import { closePeek, openPeek } from '../src/fluid/surface/magnet/client'
import { DEFAULT_APPEARANCE } from '../src/fluid/present/types'
import type { ZoneCtl } from '../src/fluid/workspace/TreeView'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')

bindOps(new Proxy({} as Ops, { get: (_, k) => (k === 'confirm' ? () => false : () => {}) }))
installProviders()

const ID = 'mag-00112233445566bb' as const
const SOURCE = { kind: 'conversation' as const, conversation: 'ent-2865e11386f6' }
const cfg = (over: Partial<MagnetConfig> = {}): MagnetConfig => ({ id: ID, ...conversationSeed(SOURCE.conversation), ...over })
const themed = (theme: string) => cfg({ presentation: { renderer: 'disc', theme } as MagnetConfig['presentation'] })

/* -- 1. its theme, under its own look -------------------------------------------------- */
{
  const SOLID = MAGNET_CHOICES.slideLook
  for (const theme of ['minimal', 'anchored', 'glass', 'floating'] as const) {
    eq(magnetLook(undefined, undefined, false, themed(theme)), MAGNET_THEME_LOOK[theme], `${theme} is its look as a pane`)
    eq(magnetLook(undefined, undefined, true, themed(theme)), MAGNET_THEME_LOOK[theme], `${theme} is its look as a slide-out, not the opaque default`)
    eq(magnetLook(undefined, { panel: 'solid', content: 'solid', opacity: 0.3 }, false, themed(theme)), MAGNET_THEME_LOOK[theme], `${theme} stands over the place's look`)
  }
  eq(magnetLook({ opacity: 0.4 }, undefined, false, themed('glass')), { panel: 'tinted', content: 'tinted', opacity: 0.4 }, 'its own opacity overrides only that of the theme')
  eq(magnetLook({ panel: 'solid', content: 'transparent' }, undefined, true, themed('floating')), { panel: 'solid', content: 'transparent', opacity: 0.82 }, '… and its panel and content each theirs')
  eq(magnetLook(undefined, undefined, true, cfg()), SOLID, 'no theme: the slide-out is opaque, as it was')
  eq(magnetLook(undefined, undefined, false, cfg()), DEFAULT_APPEARANCE, 'no theme: a pane takes the place\'s look, as it was')
  eq(magnetLook(undefined, undefined, true, themed('future')), SOLID, 'a theme this build does not know is never guessed')

  const adapters = createAdapters()
  eq(notRunning(themed('glass'), BUILD_ENV, adapters).filter((x) => x.facet === 'presentation'), [], 'a known theme is drawn, so not said to be kept undrawn')
  eq(magnetStatus(themed('glass'), { unread: 0, loading: false, held: 1, off: notRunning(themed('glass'), BUILD_ENV, adapters).filter((x) => x.facet === 'presentation').length }).limited, false, '… and does not mark the disc limited')
  ok(notRunning(themed('future'), BUILD_ENV, adapters).some((x) => x.facet === 'presentation'), 'an unknown one still is said')
  eq(changeOf(themed('glass'), { ...conversationSeed(SOURCE.conversation), presentation: { renderer: 'disc', theme: 'glass' } }), {}, 'drawing a theme changes nothing of its configuration')
}

const zoneAt = (level: 'icon' | 'compact' | 'standard'): Zone => ({ type: 'zone', id: ID, show: 'magnet', name: 'Tidewater', options: { magnet: ID }, level } as Zone)
const arrAt = (level: 'icon' | 'compact' | 'standard', c: MagnetConfig, docked = false): Arr => ({
  tree: docked ? zoneAt(level) : { type: 'zone', id: 'a', show: 'objects', name: 'a', slot: keepSlot() } as Zone, pages: [],
  focus: { floats: docked ? [] : [{ id: 'w-1', zone: zoneAt(level), x: 24, y: 24, w: 360, h: 480 }] }, magnets: { [ID]: c },
} as Arr)
const drawn = (level: 'icon' | 'compact' | 'standard', c: MagnetConfig, docked = false) => {
  workspace.quiet(() => arrAt(level, c, docked))
  return renderToStaticMarkup(createElement(MagnetZone, {
    z: zoneAt(level), r: { x: 0, y: 0, w: 360, h: 480 }, ctl: {} as unknown as ZoneCtl, page: '', first: false,
    ...(docked ? {} : { floating: { id: ID, props: { onPointerDown: () => {} }, move: () => {}, raise: () => {} } }),
  }))
}
{
  const pane = drawn('standard', themed('glass'), true)
  ok(/class="mg-zone mg-pane" data-magnet="[^"]+" data-level="standard" data-theme="glass"/.test(pane), 'a docked pane carries its theme')
  ok(/--zf-bg:color-mix\(in srgb, var\(--surface\)/.test(pane), '… and the Look that theme stands for, which no section chrome paints for it')
  const own = renderToStaticMarkup(createElement(MagnetZone, {
    z: { ...zoneAt('standard'), options: { magnet: ID, panel: 'solid', content: 'solid', opacity: 1 } } as Zone, r: { x: 0, y: 0, w: 360, h: 480 }, ctl: {} as unknown as ZoneCtl, page: '', first: false,
  }))
  ok(/--zf-bg:color-mix\(in srgb, var\(--surface-raised\) 100%/.test(own) && own.includes('data-theme="glass"'), 'its placement\'s own Look wins over the theme')
  const plain = drawn('standard', cfg(), true)
  ok(!plain.includes('data-theme=') && !plain.includes('--zf-bg'), 'no theme: drawn as it always was')
  ok(!drawn('standard', themed('future'), true).includes('--zf-bg'), 'an unknown theme draws nothing of its own')
  ok(drawn('icon', themed('minimal')).includes('data-theme="minimal"'), 'a disc carries its theme too')
  ok(drawn('compact', themed('floating')).includes('data-theme="floating"'), '… and a slide-out')

  const css = read('fluid/surface/magnet/magnet.css')
  for (const t of ['minimal', 'anchored', 'floating', 'glass'])
    ok(new RegExp(`\\.mg-at-icon\\[data-theme="${t}"\\]`).test(css), `the disc has a ${t} treatment`)
  ok(/\.mg-pane\[data-theme\]:not\(\.mg-slide\) \{ background: var\(--zf-bg/.test(css), 'a themed pane is painted by its Look')
  ok(/\.wk-float \.mg-pane\[data-theme\]:not\(\.mg-slide\), \.fq-nfloat \.mg-pane\[data-theme\]:not\(\.mg-slide\) \{ background: transparent;/.test(css), '… and not painted twice inside a window or a card')
  const floats = read('fluid/focus/Floats.tsx'), narrow = read('fluid/focus/NarrowFloats.tsx')
  ok(/magnetLook\(lookOf\(f\.zone\), placeAppearance, slide, workspace\.arr\.magnets/.test(floats), 'the window draws its theme')
  ok(/magnetLook\(lookOf\(f\.zone\), placeAppearance, false, workspace\.arr\.magnets/.test(narrow), 'and the narrow card')
}

/* -- 4. optional fields, per source ---------------------------------------------------- */
const PEOPLE = [{ id: 'ent-5936369158a8', alias: '@harbourmaster' }, { id: 'ent-5c21', alias: '@pilot' }]
const LATEST = { id: 'ent-7b1c94e2a0d3', at: 1793361600.5, author: 'ent-5936369158a8', preview: 'The tide table is up.' }
const ANSWER: RouteAnswer = { magnet: ID, sources: [{
  key: 'conversation:' + SOURCE.conversation, status: 'ok', reason: null,
  summary: { title: 'Tidewater', about: 'Harbour notes', activity: 1793361600.5, posts: 42 },
  participants: PEOPLE, participants_more: true, latest: LATEST,
}] }
const counts = { summary: 0, page: 0, posts: 0, objects: 0 }
const route = (answer: RouteAnswer): MagnetRoute => ({
  summary: async () => { counts.summary++; return answer },
  page: async () => { counts.page++; return { key: 'conversation:' + SOURCE.conversation, status: 'ok', results: [] } },
})
const reads = (r?: MagnetRoute): ConversationReads => ({
  posts: async () => { counts.posts++; return { ids: [] } }, objects: async () => { counts.objects++; return [] },
  search: async () => [], about: async () => ({ title: 'Tidewater' }), ...(r ? { route: r } : {}),
})
const liveOf = (r?: MagnetRoute) => {
  const adapters = createAdapters()
  adapters.register(conversationAdapter(reads(r)) as unknown as MagnetSourceAdapter)
  return createLive(adapters)
}
{
  const live = liveOf(route(ANSWER))
  const got = await live.load(cfg(), BUILD_ENV, { summaryOnly: true })
  const s = got.summaries[0].summary
  eq([s.participants, s.participants_more, s.latest], [PEOPLE, true, LATEST], 'what a source says of itself reaches the summary, from the source in the answer')
  eq([counts.summary, counts.page, counts.posts, counts.objects], [1, 0, 0, 0], 'the disc asks for the summary and nothing else')
  /* the preview reads as the disc does (useNow's `disc`): over a summary in hand, nothing */
  await live.load(cfg(), BUILD_ENV, { summaryOnly: true })
  eq([counts.summary, counts.page, counts.posts, counts.objects], [1, 0, 0, 0], 'so a preview over it reads nothing more: no summary, no page')

  const bare = await liveOf(route({ magnet: ID, sources: [{ key: 'conversation:' + SOURCE.conversation, status: 'ok', summary: { title: 'Tidewater' } }] })).load(cfg(), BUILD_ENV, { summaryOnly: true })
  eq(['participants', 'participants_more', 'latest'].filter((k) => k in bare.summaries[0].summary), [], 'a build that says none of them leaves none on the summary')
  const stored = await liveOf().load(cfg(), BUILD_ENV, { summaryOnly: true })
  eq(['participants', 'participants_more', 'latest'].filter((k) => k in stored.summaries[0].summary), [], 'nor does the store path, with no route')

  eq(summaryLatest([{ latest: LATEST, participants: PEOPLE }]), { id: LATEST.id, at: LATEST.at, author: '@harbourmaster', preview: 'The tide table is up.' }, 'latest: its author named from that source\'s participants')
  eq(summaryLatest([{ latest: LATEST }])?.author, null, 'an author no one names is left out, never drawn as a bare id')
  eq(summaryLatest([{ latest: { id: 'a', at: 5, preview: null } }, { latest: { id: 'b', at: 9, preview: ' words ' } }, { latest: { id: 'c', at: 7 } }]),
    { id: 'b', at: 9, author: null, preview: 'words' }, 'the newest across sources')
  eq(summaryLatest([{ latest: { id: 'a', at: 5, preview: null } }])?.preview, null, 'a deleted post or one of no words has no preview')
  for (const bad of [{}, { latest: null }, { latest: 'x' }, { latest: {} }, { latest: { id: 3 } }, null, 7])
    eq(summaryLatest([bad]), null, `absent or malformed latest is nothing: ${JSON.stringify(bad)}`)
  eq([participantsBeyond([{ participants_more: true }, {}]), participantsBeyond([{}, null]), participantsBeyond([{ participants_more: 'yes' }])], [true, false, false], 'participants_more only when a source says true')
}

/* -- 2. its preview -------------------------------------------------------------------- */
const live = (summary: Record<string, unknown>): MagnetLive & { loading: boolean } => ({ config: cfg(), loading: false, tabs: [], results: [], summaries: [{ source: SOURCE, summary: { title: 'Tidewater', ...summary } }] })
const preview = (summary: Record<string, unknown>, c = cfg()) => renderToStaticMarkup(createElement(MagnetPreview, {
  id: ID, config: c, title: 'Tidewater', unread: 0, status: magnetStatus(c, { unread: 0, loading: false, held: 0, off: 0 }), live: live(summary), onEnter: () => {}, onLeave: () => {},
}))
{
  const full = preview({ activity: 1000, participants: PEOPLE, participants_more: true, latest: LATEST })
  ok(full.includes('Tidewater') && full.includes('From a conversation') && full.includes('active'), 'identity and activity')
  ok(full.includes('Latest · @harbourmaster') && full.includes('The tide table is up.'), 'its latest finding')
  ok(full.includes('Participants: @harbourmaster, @pilot') && full.includes('and others') && full.includes('>H<') && full.includes('>P<'), 'who is here, past any @, and that there are others')
  ok(full.includes('role="tooltip"') && full.includes(`id="${previewIdOf(ID)}"`), 'a tooltip the disc can be described by')
  ok(!/<button|tabindex/i.test(full), 'it takes no focus')
  ok(!/active now/i.test(full), 'and never says who is active now')
  const empty = preview({})
  ok(empty.includes('Tidewater') && !empty.includes('mg-preview-latest') && !empty.includes('mg-people') && !empty.includes('mg-unavailable'), 'absent fields: nothing drawn and no error')
  const mute = preview({ latest: { id: 'ent-1', at: 1000, preview: null } })
  ok(mute.includes('Latest') && !mute.includes('mg-line-text'), 'a latest with no words says only that it is')
  ok(preview({}, themed('glass')).includes('data-theme="glass"'), 'it carries the glass theme')
  const css = read('fluid/surface/magnet/magnet.css')
  ok(/\.mg-preview\[data-theme="glass"\] \{[^}]*color-mix\(in srgb, var\(--surface-raised\) \d+%, transparent\)[^}]*backdrop-filter: blur/.test(css), 'a faint glass under the glass theme')
  ok(/prefers-reduced-transparency: reduce\) \{ \.mg-preview\[data-theme="glass"\] \{ background: var\(--surface-raised\)/.test(css), '… opaque for whoever asks for less transparency')

  closePeek()
  ok(!drawn('icon', cfg()).includes('mg-preview'), 'nothing until a rest or focus')
  openPeek(ID, 'hover')
  const shown = drawn('icon', cfg())
  ok(shown.includes('role="tooltip"') && shown.includes(`aria-describedby="${previewIdOf(ID)}"`), 'on a rest or focus it is drawn and describes the disc')
  ok(!shown.includes('class="mg-card"'), '… as a preview, not the summary card')
  ok(!drawn('icon', cfg(), true).includes('aria-describedby'), 'a disc in a section describes itself by nothing it does not draw')
  closePeek()
  openPeek(ID, 'pinned')
  const pinned = drawn('icon', cfg())
  ok(pinned.includes('class="mg-card"') && !pinned.includes('role="tooltip"'), 'Peek still opens the summary card')
  closePeek()

  const zone = read('fluid/surface/magnet/MagnetZone.tsx')
  ok(/function Previewed[\s\S]*?useNow\(id, config, undefined, true\)/.test(zone), 'the preview reads as the disc reads')
  ok(/onFocus=\{\(e\) => \{ if \(!opened && e\.currentTarget\.matches\(':focus-visible'\)\) \{[^}]*openPeek\(id, 'hover'\)/.test(zone), 'keyboard focus shows it; a press that focuses the disc does not')
  ok(/onBlur=\{\(\) => \{ if \(!opened\) \{ stay\(id\); closePeek\(id, true\) \} \}\}/.test(zone), 'leaving puts it away')
  const summary = read('fluid/surface/magnet/Summary.tsx')
  ok(/useEffect\(\(\) => onEscape\(ESC\.peek, \(\) => \{ closePeek\(id, true\); return true \}\), \[id\]\)/.test(summary), 'Esc puts it away')
  ok(/onPointerEnter=\{onEnter\} onPointerLeave=\{onLeave\}/.test(summary), 'the pointer may move onto it')
  for (const file of ['surface/magnet/useMagnet.ts', 'surface/magnet/live.ts'])
    ok(!/MagnetPreview|Previewed/.test(read('fluid/' + file)), `${file} is not changed for it`)

  /* every place a disc can be, in every viewport: wholly inside, and clear of the orbit where any side has room */
  const card = { width: 280, height: 240 }, D = MAGNET_CHOICES.disc, GUTTER = 8
  let placed = 0
  for (const v of [{ width: 1440, height: 900 }, { width: 1024, height: 700 }, { width: 768, height: 1024 }, { width: 390, height: 844 }, { width: 320, height: 568 }, { width: 300, height: 240 }]) {
    for (let left = -D; left <= v.width; left += 37) for (let top = -D; top <= v.height; top += 41) {
      const zone = { left, top }, disc = { left, top, width: D, height: D }
      const p = previewPlacement(zone, disc, v, card)
      const width = Math.min(card.width, v.width - GUTTER * 2), height = Math.min(card.height, v.height - GUTTER * 2)
      const x = p.x + left, y = p.y + top
      assert.ok(x >= GUTTER && y >= GUTTER && x + width <= v.width - GUTTER && y + height <= v.height - GUTTER, `inside ${v.width}x${v.height} from ${left},${top}: ${x},${y}`)
      const cx = left + D / 2, cy = top + D / 2
      const clear = x >= cx + PREVIEW_REACH || x + width <= cx - PREVIEW_REACH || y >= cy + PREVIEW_REACH || y + height <= cy - PREVIEW_REACH
      const room = cx + PREVIEW_REACH + width <= v.width - GUTTER || cx - PREVIEW_REACH - width >= GUTTER
        || (cx + PREVIEW_REACH >= GUTTER && cy + PREVIEW_REACH + height <= v.height - GUTTER) || (cy - PREVIEW_REACH - height >= GUTTER)
      if (room && cx >= 0 && cy >= 0 && cx <= v.width && cy <= v.height) assert.ok(clear, `clear of the disc in ${v.width}x${v.height} from ${left},${top}`)
      placed++
    }
  }
  ok(placed > 1000, `preview held in the viewport at ${placed} disc positions`)
  const underBar = previewPlacement({ left: 8, top: 56 }, { left: 8, top: 56, width: 56, height: 56 }, { left: 0, top: 48, width: 1280, height: 752 }, card)
  eq(underBar.y + 56, 56, 'a disc at the top holds its preview below the app\'s bar, where it can be seen')
  eq(previewPlacement({ left: 100, top: 300 }, { left: 100, top: 300, width: 56, height: 56 }, { width: 1000, height: 800 }, card).side, 'right', 'beside the disc first')
  eq(previewPlacement({ left: 900, top: 300 }, { left: 900, top: 300, width: 56, height: 56 }, { width: 1000, height: 800 }, card).side, 'left', 'then its other side')
  eq(previewPlacement({ left: 150, top: 100 }, { left: 150, top: 100, width: 56, height: 56 }, { width: 390, height: 844 }, card).side, 'below', 'then below, on a narrow page')
  eq(previewPlacement({ left: 150, top: 700 }, { left: 150, top: 700, width: 56, height: 56 }, { width: 390, height: 844 }, card).side, 'above', 'then above')
}

/* -- 3. a compact file list and a small gallery ------------------------------------------ */
{
  const floated: ObjectTarget[] = []
  provide({ float: (t) => { floated.push(t) } })
  const res = (kind: string, id: string, number: number, preview: ObjectRow['preview'] = null, title: string | null = id): MagnetResult =>
    ({ source: SOURCE, kind, id, value: { address: 'live:' + id, kind: 'media', title, post: 'p', number, preview } satisfies ObjectRow })
  const files = [res('file', 'old.pdf', 1, { is: { family: 'file', word: 'PDF' } }), res('file', 'new.md', 5), res('file', 'nameless', 3, null, null)]
  const list = renderToStaticMarkup(createElement(FileList, { results: files, kind: 'file' }))
  ok(list.indexOf('new.md') < list.indexOf('old.pdf'), 'files newest first')
  ok(list.includes('PDF · from #1') && list.includes('from #5'), 'each says what it is, where the source says, and where it is from')
  ok(list.includes('>media<'), 'with no title, its kind')
  ok(list.includes('aria-label="Files"'), 'a list with a name')
  ok(renderToStaticMarkup(createElement(FileList, { results: files, kind: 'attachment' })).includes('aria-label="Attachments"'), '… attachments, theirs')

  const pics = [res('image', 'a', 1, { artifact: { url: '/a.png' } }), res('image', 'b', 7, { ref: 'adm-1' }), res('image', 'c', 4)]
  const gallery = renderToStaticMarkup(createElement(ImageGallery, { results: pics }))
  ok(gallery.indexOf('/api/artifacts/adm-1') < gallery.indexOf('/a.png'), 'pictures newest first, read from what the result gives')
  ok(gallery.includes('alt="Open a"') && gallery.includes('loading="lazy"'), 'each has its words and waits to be seen')
  ok(gallery.includes('aria-label="Open c"') && gallery.includes('mg-tile-name'), 'media with no picture is named')

  const walk = (node: ReactElement<any> | ReactElement<any>[]): ReactElement<any>[] => [node].flat().flatMap((n) => !n?.props ? [] : [n, ...[n.props.children].flat().flatMap((c: any) => walk(c))])
  const anchor = { id: 'tile' } as unknown as HTMLElement
  for (const el of [FileList({ results: files, kind: 'file' }), ImageGallery({ results: pics })]) {
    floated.length = 0
    const buttons = walk(el).filter((n) => n.type === 'button')
    eq(buttons.length, 3, 'one button each')
    let stopped = false
    buttons[0].props.onClick({ currentTarget: anchor, stopPropagation: () => { stopped = true } })
    ok(stopped, 'its click goes no further: raising the Magnet would cover the float it opened')
    eq(floated.length, 1, 'opening goes through the existing float, once')
    eq(floated[0].anchor, anchor, '… from where it was asked')
    ok(floated[0].address.startsWith('live:') && floated[0].from?.startsWith('from #'), '… with its address and where it is from')
  }
  const objects = read('fluid/surface/magnet/Objects.tsx')
  ok(/act\.float\(/.test(objects) && !/fetch\(|store\.|useState|createPortal/.test(objects), 'no read, no store and no window of their own')
  const zone = read('fluid/surface/magnet/MagnetZone.tsx')
  ok(/tab === 'image' && renderer !== 'cards'\) return <ImageGallery/.test(zone) && /\(tab === 'file' \|\| tab === 'attachment'\) && renderer !== 'cards' && renderer !== 'gallery'\) return <FileList/.test(zone), 'a tab draws them, unless its renderer asks for cards or a gallery of files')

  /* a page is read for the types it selects, and only when opened */
  counts.summary = counts.page = counts.posts = counts.objects = 0
  const asked: string[][] = []
  const adapters = createAdapters()
  adapters.register(conversationAdapter(reads({ summary: async () => ANSWER, page: async (_m, key, types) => { asked.push([...types]); return { key, status: 'ok', results: [] } } })) as unknown as MagnetSourceAdapter)
  const paging = createLive(adapters)
  await paging.load(cfg(), BUILD_ENV, { summaryOnly: true })
  eq(asked, [], 'a disc reads no page')
  await paging.load(cfg(), BUILD_ENV)
  eq(asked, [['post', 'file', 'image', 'attachment']], 'opened, one page, for the object types it selects')
  /* Summary keeps its own recents and thumbs, reading nothing of its own */
  const lv = { config: cfg(), loading: false, tabs: [], summaries: [], results: pics }
  ok(renderToStaticMarkup(createElement(SummaryBody, { id: ID, config: cfg(), title: 'T', live: lv, unread: 0, status: magnetStatus(cfg(), { unread: 0, loading: false, held: 3, off: 0 }) })).includes('mg-thumbs'), 'the summary keeps its thumbnails')
}

console.log(`fluid magnet presence: ${checks} checks passed`)
