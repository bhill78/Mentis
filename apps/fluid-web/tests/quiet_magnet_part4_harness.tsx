/** PART 4 VISUAL CHECK: a fixture shaped like the astronomy Magnet's own batch
 *  -- many rows, several days, several sites -- so the compact, grouped list
 *  and the fourth Images pill can be seen the way `04-browse.png` means them,
 *  rather than against the one or two rows most unit fixtures carry. Not a
 *  pinned test: a harness `quiet_magnet_part4_shots.py` drives with Playwright
 *  to produce screenshots for this part's own visual check. */
import { createRoot } from 'react-dom/client'
import Magnet from '../src/quiet2/magnets/Magnet'
import EvidenceViews from '../src/quiet2/magnets/EvidenceViews'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { setOpen, goTab } from '../src/quiet2/magnets/places'
import '../src/quiet2/magnets/host.css'

const source = 'ent-source654321', id = 'mag-part4'
const config = { id, sources: [{ kind: 'conversation', conversation: source }], conversation: 'ent-own654321', selection: {},
  collection: { mode: 'one-time' }, synthesis: { mode: 'manual' }, notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' } } as const

const now = Math.floor(Date.now() / 1000)
const DAY = 86400
const SITES: { host: string; headlines: string[] }[] = [
  { host: 'nasa.gov', headlines: ['Juno completes its 58th flyby of Jupiter', 'Perseverance drills a new sample on Mars', 'Artemis II crew begins launch rehearsal', 'Europa Clipper adjusts its trajectory', 'Voyager 1 sends a faint but readable signal'] },
  { host: 'space.com', headlines: ['A new exoplanet is found in the habitable zone', 'The ISS crew completes a six-hour spacewalk', 'A meteor shower peaks this weekend', 'A private crew returns from low orbit', 'Astronomers spot a rare type of supernova'] },
  { host: 'skyandtelescope.org', headlines: ['How to see the planets align this month', 'A beginner’s guide to observing Saturn', 'The best binoculars for a first telescope', 'What the next eclipse will look like locally'] },
]

let n = 0
const results: any[] = []
for (let day = 0; day < 5; day++) {
  const at = now - day * DAY - day * 37
  for (const site of SITES) for (const headline of site.headlines) {
    n += 1
    results.push({ kind: 'file', id: `file-${n}`, version: `ent-version${String(n).padStart(6, '0')}`, conversation: source, at: at - n * 11,
      via: 'held-source', value: { text: `${headline}\n\nhttps://${site.host}/article-${n}` } })
  }
  n += 1
  results.push({ kind: 'post', id: `post-${n}`, version: `ent-version${String(n).padStart(6, '0')}`, conversation: source, number: n, at,
    value: { parts: [{ type: 'text', text: `A note from the Conversation, day ${day}.` }] } })
  n += 1
  results.push({ kind: 'image', id: `image-${n}`, version: `ent-version${String(n).padStart(6, '0')}`, conversation: source, at: at - 5,
    value: { title: `Observation photo, day ${day}` } })
}

const resource = createMagnetResource({ id: 'mg-part4', brainKey: 'fixture|test|brain-part4', saved: { id, name: 'Space missions and astronomy', config: config as any },
  get: async () => ({ status: 200, body: { magnet: id, config,
    activation: { post: 'ent-batch654321', artifact: { ref: 'adm-batch654321' }, at: now, state: 'complete' },
    page: { sources: [{ key: `conversation:${source}`, source: config.sources[0], status: 'ok', results }] } } }) })
resource.update({ x: 32, y: 24, wide: true, dimensions: { width: 900, height: 1200 } })
setOpen(resource, true)
goTab(resource, 'All')
Object.assign(window, { part4: { resource } })
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
