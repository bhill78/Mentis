/** REAL-SHAPE DENSITY CHECK (not a pinned test): a fixture shaped like the
 *  real astronomy Magnet's own batch -- 75 rows, all linking the same host
 *  (news.google.com), split 4/71 across two days, so collection.css's
 *  compaction is measured against the shape that actually produced only 11
 *  visible rows (ent-e27a43b60927 / ent-e20fb2f91abf), not the part4 fixture's
 *  3-site/5-day shape and its 900x1200 forced panel. The card here keeps its
 *  DEFAULT size: wide, no `dimensions` override, so the geometry cap in
 *  Magnet.tsx (740 px tall) applies exactly as it does for a reader who has
 *  never dragged the panel. Driven by quiet_magnet_density_shots.py.
 *
 *  REPRESENTATIVE EXCERPTS, AND THE REAL BASE STYLES (correction, review
 *  ent-f94e543d798e): the prior fixture carried only a headline and a link
 *  on every row, which never exercised `.q2-magnet-row-more`'s excerpt
 *  paragraph at all, and it imported only `host.css` -- the canvas's own
 *  positioning -- never `theme.css`/`app.css`/`atmosphere.css`, so none of
 *  the type, colour or `--radius-pop`/`--pop-lift` tokens the real app
 *  always has loaded were present. A quarter of these rows (every 4th,
 *  starting at the very first so the most obvious case is covered) carry a
 *  short captured excerpt after their header, the same shape a directly
 *  fetched article gives `rowBody` where a bare feed entry gives none; the
 *  rest keep the headline-only shape most of the real batch actually has. */
import { createRoot } from 'react-dom/client'
import Magnet from '../src/quiet2/magnets/Magnet'
import EvidenceViews from '../src/quiet2/magnets/EvidenceViews'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { setOpen, goTab } from '../src/quiet2/magnets/places'
import '../src/theme.css'
import '../src/app.css'
import '../src/atmosphere.css'
import '../src/quiet2/magnets/host.css'

const source = 'ent-source654321', id = 'mag-density'
const config = { id, sources: [{ kind: 'conversation', conversation: source }], conversation: 'ent-own654321', selection: {},
  collection: { mode: 'one-time' }, synthesis: { mode: 'manual' }, notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' } } as const

const now = Math.floor(Date.now() / 1000)
const DAY = 86400
const TITLES = [
  'Phoenix Mars Mission - Agence spatiale canadienne', "Scientists have found a weird 'inside out' planetary system. Here's what it looks like - Space",
  'Nancy Grace Roman Space Telescope - NASA Science (.gov)', 'Space calendar 2026: Rocket launches, skywatching events, missions & more! - Space',
  'Juno - NASA Science (.gov)', '60 Years and Counting - Mysteries of the Universe - NASA (.gov)',
]

// A SHORT CAPTURED EXCERPT, THE SHAPE A DIRECTLY FETCHED ARTICLE GIVES
// (`heldHeader`/`rowBody`, links.tsx): never the headline said again, and
// close to the length that actually dropped the fixture's hover density
// from 20 to 19 (review ent-f94e543d798e's own diagnostic used a 123-char
// excerpt on the first row).
const EXCERPTS = [
  'The mission returned new observations of the atmosphere, revealing a pattern scientists will investigate in the next flyby.',
  'Researchers say the find reshapes how the system formed, and a follow-up observation window opens next month.',
  'The agency confirmed the instrument is operating normally after the anomaly, and the schedule is unaffected.',
  'A joint team will publish the full dataset once the calibration review now underway is complete.',
]

let n = 0
const results: any[] = []
// 4 items "Today", 71 items "Yesterday" -- the real split, all one host.
for (const [day, count] of [[0, 4], [1, 71]] as const) {
  for (let i = 0; i < count; i++) {
    n += 1
    const title = TITLES[n % TITLES.length]
    const link = `https://news.google.com/rss/articles/CBMi${n}`
    // EVERY 4TH ROW CARRIES AN EXCERPT (representative, not universal: most
    // of the real batch is headline-only aggregator entries; some rows are
    // a directly fetched article with its own captured excerpt).
    const text = n % 4 === 1 ? `${title}\n\n${link}\n\n${EXCERPTS[(n >> 2) % EXCERPTS.length]}` : `${title}\n\n${link}`
    results.push({ kind: 'file', id: `file-${n}`, version: `ent-version${String(n).padStart(6, '0')}`, conversation: source,
      at: now - day * DAY - i * 11,
      via: 'held-source', value: { text } })
  }
}

const resource = createMagnetResource({ id: 'mg-density', brainKey: 'fixture|test|brain-density', saved: { id, name: 'Space missions and astronomy', config: config as any },
  get: async () => ({ status: 200, body: { magnet: id, config,
    activation: { post: 'ent-batch654321', artifact: { ref: 'adm-batch654321' }, at: now, state: 'complete' },
    page: { sources: [{ key: `conversation:${source}`, source: config.sources[0], status: 'ok', results }] } } }) })
// DELIBERATELY NO `dimensions` OVERRIDE: this is the default card an owner who
// has never dragged the panel sees. `wide: true` matches the measured real
// card ("stepped to its larger panel").
resource.update({ x: 32, y: 24, wide: true })
setOpen(resource, true)
goTab(resource, 'All')
Object.assign(window, { density: { resource } })
createRoot(document.getElementById('root')!).render(<div className="q2 q2-arr-one">
  <div className="q2-magnet-canvas"><Magnet resource={resource} onExpand={() => {}} onCollapse={() => {}}
    views={{
      All: <EvidenceViews resource={resource} lens="All" onPost={() => {}} onFile={() => {}} canWrite={() => true} />,
      Posts: <EvidenceViews resource={resource} lens="Posts" onPost={() => {}} onFile={() => {}} canWrite={() => true} />,
      Files: <EvidenceViews resource={resource} lens="Files" onPost={() => {}} onFile={() => {}} canWrite={() => true} />,
      Images: <EvidenceViews resource={resource} lens="Images" onPost={() => {}} onFile={() => {}} canWrite={() => true} />,
      Perspectives: <p>Perspectives unavailable in this harness.</p>,
      Conversation: <p>Conversation view</p>,
    }} /></div>
</div>)
