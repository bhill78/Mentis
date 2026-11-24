/** Mounted fixture for R2 of the inspection re-review (adm-6a1f95f203bf): the
 *  Conversation place's reading position across a tab change, an inspection
 *  return, a close and reopen, and content that arrives after the view does.
 *
 *  The real frame, the real view-state spine, the real `Inspection` composed the
 *  way `Host.tsx` composes it, and the real `MiniConversation` with its own real
 *  Composer -- the Magnet's isolated draft is what the unsaved-edit check reads
 *  back. Only HTTP is synthetic; nothing here stands in for a product component
 *  and no Brain is opened.
 *
 *  `?slow=<ms>` makes the Conversation read answer late, which is what a reader
 *  returning to a saved position actually meets: the view renders first and the
 *  posts arrive after it. */
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

const SOURCE = 'ent-readsource11', OWN = 'ent-readown11111', ME = 'ent-readowner111', AGENT = 'ent-readagent111'
const LENS = 'ent-readtopic111', REVISION = 'adm-readrevision1', BATCH = 'adm-readbatch1111'
const CITED = 'ent-readpost1115'
const id = 'mag-reading-position' as const
page.saw('read-fixture@instance-one')

const flags = new URLSearchParams(location.search)
const config = { id, sources: [{ kind: 'conversation', conversation: SOURCE }], conversation: OWN, selection: {},
  collection: { mode: 'one-time' }, synthesis: { mode: 'manual' },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } } as const
const results = Array.from({ length: 35 }, (_, i) => ({ kind: 'post', id: `ent-readpost111${i}`, version: `ent-readpost111${i}`,
  conversation: SOURCE, number: i + 1,
  value: { text: `Retained item ${i + 1}: captured words belonging to this batch.\n`.repeat(8) } }))
const activation = { post: 'ent-readbatchpost', artifact: { ref: BATCH, digest: 'c'.repeat(64), size: 42, media_type: 'application/json' }, at: 1795000000, state: 'complete' }

const probe: any = { reads: 0, slow: Number(flags.get('slow') ?? 0) }
;(window as any).probe = probe
const json = (body: any) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
const turn = (n: number, text: string) => ({ id: `ent-readturn${n}111`, number: n, author: ME, author_alias: '@fixture',
  at: 1795000000, parts: [{ type: 'text', text }], replies: [], thread_replies: 0, expectations: [] })
/** Enough recorded words that the Conversation view really scrolls past 400. */
/** The reference is cited twice on purpose: once at the top, and once in the
 *  last post, so a citation can be clicked from a position far down the list
 *  without the click itself having to scroll the view to reach it. */
const turns = [turn(1, `The collected evidence for this is ${CITED} and the retained batch is ${BATCH}.`),
  ...Array.from({ length: 23 }, (_, i) => turn(i + 2, `Conversation reading line ${i + 2}. ${'More recorded words to read in this Conversation. '.repeat(4)}`)),
  turn(25, `The same collected evidence, cited again at the end of the reading: ${CITED}.`)]

window.fetch = async (input: any, init: any = {}) => {
  const url = new URL(String(input), location.href), path = url.pathname
  if (path === '/fluid/api/needs-you/brain') return json({ brain: { corpus_id: 'read-fixture', instance: 'instance-one' } })
  if (path === '/fluid/api/participants') return json({ me: ME, participants: [
    { id: ME, alias: '@Owner', default_runtime: null, runtime_mode: 'undeclared' },
    { id: AGENT, alias: '@FixtureAgent', default_runtime: null, runtime_mode: 'undeclared' }] })
  if (path === '/api/personas') return json({ personas: [] })
  if (path.startsWith('/api/who/')) return json({ designated_persona: null })
  if (path === '/api/execution') return json({ runtimes: [], running: [], default_runtime: null })
  if (path === '/api/capacity') return json({ runtimes: [] })
  if (path.startsWith('/fluid/api/search')) return json({ hits: [], more: false })
  if (path.endsWith('/collection')) return json({ magnet: id, config, activation, page: { sources: [{ key: `conversation:${SOURCE}`, source: config.sources[0], status: 'ok', results }] } })
  if (path.includes('/perspectives')) {
    const tail = path.split('/perspectives')[1], [topic, verb] = tail.slice(1).split('/')
    const row = { perspective: LENS, name: 'Original', retired: false, question: { ref: REVISION, digest: 'd'.repeat(64), size: 20, media_type: 'application/json' },
      current_question: { text: 'Does the retained batch answer this?', revision: REVISION }, events: 1 }
    const base = { brain: 'read-fixture@instance-one', magnet: id }
    if (!tail) return json({ ...base, perspectives: [row], selected: LENS, next: null })
    if (verb === 'history') return json({ ...base, perspective: topic, next: null,
      events: [{ post: 'ent-readrevision1', event: 'question', seq: 1, perspective: topic, snapshot: { ref: REVISION, digest: 'd'.repeat(64) }, data: { text: 'Original saved wording' } }] })
    return json({ ...base, ...row, selected: LENS })
  }
  if (path.startsWith(`/api/conversations/${OWN}`)) {
    probe.reads++
    // Content that arrives after the view: the read answers, slowly, and a read
    // that was abandoned and started again is answered the same way.
    if (probe.slow) await new Promise((r) => setTimeout(r, probe.slow))
    return json({ id: OWN, name: 'Reading position fixture conversation',
      participants: [{ participant: AGENT, alias: '@FixtureAgent', default_runtime: null, runtime_mode: 'undeclared' }],
      topics: [], turns, turns_total: turns.length, owed: [], batch: { older: 0, first: 1 } })
  }
  if (path.startsWith('/api/artifacts/')) {
    return json({ ref: decodeURIComponent(path.split('/api/artifacts/')[1]), state: 'held', media_type: 'text/plain',
      name: 'reading-fixture.txt', size: 23, text: 'Synthetic retained bytes' })
  }
  throw new Error(`Fixture refused unexpected fetch: ${path}`)
}

const resource = createMagnetResource({ id: 'qm-reading-position', brainKey: 'http://fixture||read-fixture',
  saved: { id, name: 'Reading position fixture', config: config as any },
  get: async (p) => { const r = await window.fetch(p); return { status: r.status, body: await r.json() } } })
resource.update({ x: 32, y: 32 })
setOpen(resource, true)
probe.resource = resource

const source = () => { throw new Error('unexpected main-surface navigation') }
const evidence = (ref: string) => { probe.evidence = ref; inspect(resource, ref) }
const views = withInspections(resource, {
  Summary: <Summary resource={resource} onPost={source} />,
  All: <EvidenceViews resource={resource} lens="All" onPost={source} onFile={source} />,
  Posts: <EvidenceViews resource={resource} lens="Posts" onPost={source} onFile={source} />,
  Files: <EvidenceViews resource={resource} lens="Files" onPost={source} onFile={source} />,
  Perspectives: <Perspectives resource={resource} canWrite={true} onEvidence={evidence} />,
  Conversation: <MiniConversation resource={resource} canWrite={true} onFull={() => { probe.full = true }} onEvidence={evidence} />,
  search: <SearchView resource={resource} />,
}, source)

createRoot(document.getElementById('root')!).render(<div className="q2 q2-arr-one">
  <div className="q2-work-row" style={{ height: '100vh', overflow: 'auto', boxSizing: 'border-box', background: '#ddd' }}>
    <div style={{ height: 1800, width: '100%' }}>Surrounding Conversation</div>
  </div>
  <div className="q2-magnet-canvas"><Magnet resource={resource} onExpand={() => {}} onCollapse={() => {}} views={views} /></div>
</div>)
