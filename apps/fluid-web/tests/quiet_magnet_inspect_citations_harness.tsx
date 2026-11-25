/** Mounted regression fixture for H1 review blockers B1 and B2.
 *
 *  The real frame, the real view-state spine, the real `Inspection`, the real
 *  `MiniConversation` and the real Perspectives panel, composed exactly as
 *  `Host.tsx` composes them -- through `withInspections`. Only HTTP is
 *  synthetic; nothing here is a stand-in for a product component, and no Brain
 *  is opened.
 *
 *  B1 needs a list long enough to scroll inside the one scroll container.
 *  B2 needs an actual citation control, so the synthetic Conversation read
 *  returns a post whose words contain a collected post reference and a retained
 *  artifact reference: `MiniConversation` turns those into its own
 *  "Inspect ... inside Magnet" buttons. */
import { createRoot } from 'react-dom/client'
import Magnet from '../src/quiet2/magnets/Magnet'
import EvidenceViews from '../src/quiet2/magnets/EvidenceViews'
import Summary from '../src/quiet2/magnets/Summary'
import SearchView from '../src/quiet2/magnets/SearchView'
import MiniConversation from '../src/quiet2/magnets/MiniConversation'
import Perspectives from '../src/quiet2/magnets/InquiryPanel'
import { withInspections } from '../src/quiet2/magnets/Inspection'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { inspect, setOpen } from '../src/quiet2/magnets/places'
import { page } from '../src/brainBinding'
import '../src/quiet2/quiet2.css'
import '../src/quiet2/magnets/host.css'
import '../src/quiet2/magnets/magnet.css'
import '../src/quiet2/magnets/conversation.css'

const SOURCE = 'ent-citesource11', OWN = 'ent-citeown1111', ME = 'ent-citeowner11', AGENT = 'ent-citeagent11'
const LENS = 'ent-citetopic111', REVISION = 'adm-citerevision1', BATCH = 'adm-c17eba7c1111'
const CITED = 'ent-c17e9051115'
const id = 'mag-citations' as const
page.saw('cite-fixture@instance-one')

const config = { id, sources: [{ kind: 'conversation', conversation: SOURCE }], conversation: OWN, selection: {},
  collection: { mode: 'one-time' }, synthesis: { mode: 'manual' },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } } as const
/** Enough retained items that the view really scrolls. */
const results = Array.from({ length: 35 }, (_, i) => ({ kind: 'post', id: `ent-c17e905111${i}`, version: `ent-c17e905111${i}`,
  conversation: SOURCE, number: i + 1,
  value: { text: `Retained item ${i + 1}: captured words belonging to this batch.\n`.repeat(8) } }))
const activation = { post: 'ent-citebatchpost', artifact: { ref: BATCH, digest: 'c'.repeat(64), size: 42, media_type: 'application/json' }, at: 1795000000, state: 'complete' }

const probe: any = { reads: 0, artifactReads: [] }
;(window as any).probe = probe
const json = (body: any) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
const turn = (n: number, text: string) => ({ id: `ent-citeturn${n}111`, number: n, author: ME, author_alias: '@fixture',
  at: 1795000000, parts: [{ type: 'text', text }], replies: [], thread_replies: 0, expectations: [] })

window.fetch = async (input: any, init: any = {}) => {
  const url = new URL(String(input), location.href), path = url.pathname
  if (path === '/fluid/api/needs-you/brain') return json({ brain: { corpus_id: 'cite-fixture', instance: 'instance-one' } })
  if (path === '/fluid/api/participants') return json({ me: ME, participants: [
    { id: ME, alias: '@Owner', default_runtime: null, runtime_mode: 'undeclared' },
    { id: AGENT, alias: '@FixtureAgent', default_runtime: null, runtime_mode: 'undeclared' }] })
  if (path === '/api/personas') return json({ personas: [] })
  if (path.startsWith('/api/who/')) return json({ designated_persona: null })
  if (path === '/api/execution') return json({ runtimes: [], running: [], default_runtime: null })
  if (path === '/api/capacity') return json({ runtimes: [] })
  if (path.endsWith('/collection')) return json({ magnet: id, config, activation, page: { sources: [{ key: `conversation:${SOURCE}`, source: config.sources[0], status: 'ok', results }] } })
  if (path.includes('/perspectives')) {
    const tail = path.split('/perspectives')[1], [topic, verb] = tail.slice(1).split('/')
    const row = { perspective: LENS, name: 'Original', retired: false, question: { ref: REVISION, digest: 'd'.repeat(64), size: 20, media_type: 'application/json' },
      current_question: { text: 'Does the retained batch answer this?', revision: REVISION }, events: 1 }
    const base = { brain: 'cite-fixture@instance-one', magnet: id }
    if (!tail) return json({ ...base, perspectives: [row], selected: LENS, next: null })
    if (verb === 'history') return json({ ...base, perspective: topic, next: null,
      events: [{ post: 'ent-citerevision1', event: 'question', seq: 1, perspective: topic, snapshot: { ref: REVISION, digest: 'd'.repeat(64) }, data: { text: 'Original saved wording' } }] })
    return json({ ...base, ...row, selected: LENS })
  }
  if (path.startsWith(`/api/conversations/${OWN}`)) {
    probe.reads++
    return json({ id: OWN, name: 'Citations fixture conversation',
      participants: [{ participant: AGENT, alias: '@FixtureAgent', default_runtime: null, runtime_mode: 'undeclared' }],
      topics: [], turns: [turn(1, `The collected evidence for this is ${CITED} and the retained batch is ${BATCH}.`)],
      turns_total: 1, owed: [], batch: { older: 0, first: 1 } })
  }
  if (path.startsWith('/api/artifacts/')) {
    probe.artifactReads.push(path)
    return json({ ref: decodeURIComponent(path.split('/api/artifacts/')[1]), state: 'held', media_type: 'text/plain',
      name: 'citation-fixture.txt', size: 23, text: 'Synthetic retained bytes' })
  }
  throw new Error(`Fixture refused unexpected fetch: ${path}`)
}

const resource = createMagnetResource({ id: 'qm-citations', brainKey: 'http://fixture||cite-fixture',
  saved: { id, name: 'Citations fixture', config: config as any },
  get: async (p) => { const r = await window.fetch(p); return { status: r.status, body: await r.json() } } })
resource.update({ x: 32, y: 32 })
setOpen(resource, true)
probe.resource = resource

/* The host's own `source` callback: inspection provenance never navigates away
 * in this fixture, and a call would be a product defect, not a fixture gap. */
const source = () => { throw new Error('unexpected main-surface navigation') }
/** Exactly the host's `evidence` callback; the probe only records what it saw. */
const evidence = (ref: string) => { probe.evidence = ref; inspect(resource, ref) }
const views = withInspections(resource, {
  Summary: <Summary resource={resource} onPost={source} />,
  All: <EvidenceViews resource={resource} lens="All" onPost={source} onFile={source} />,
  Posts: <EvidenceViews resource={resource} lens="Posts" onPost={source} onFile={source} />,
  Files: <EvidenceViews resource={resource} lens="Files" onPost={source} onFile={source} />,
  Perspectives: <Perspectives resource={resource} canWrite={false} onEvidence={evidence} />,
  Conversation: <MiniConversation resource={resource} canWrite={false} onEvidence={evidence} />,
  search: <SearchView resource={resource} />,
}, source)

createRoot(document.getElementById('root')!).render(<div className="q2 q2-arr-one">
  <div className="q2-work-row" style={{ height: '100vh', overflow: 'auto', boxSizing: 'border-box', background: '#ddd' }}>
    <div style={{ height: 1800, width: '100%' }}>Surrounding Conversation</div>
  </div>
  <div className="q2-magnet-canvas"><Magnet resource={resource} onExpand={() => {}} onCollapse={() => {}} views={views} /></div>
</div>)
