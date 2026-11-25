/* THE CARD AS THE FRAME DRAWS IT, with the persistent composer in the footer
   slot it is made for: the real `Magnet`, the real `ComposerBar` with the real
   `fluid/Composer` inside it, the real mini store, and the product's own global
   styling -- which is what decides how much of a 320x640 card is left to read.
   Synthetic HTTP only; no Brain, no agent, no server of the app's own.

   `quiet_magnet_mini_harness.tsx` beside this one mounts the same bar in a
   hand-built card to exercise what it writes; this one exists for what the
   frame and the bar do to each other. */
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import Magnet from '../src/quiet2/magnets/Magnet'
import MiniConversation from '../src/quiet2/magnets/MiniConversation'
import ComposerBar from '../src/quiet2/magnets/ComposerBar'
import { Layer } from '../src/fluid/frame/layer'
import { page } from '../src/brainBinding'
import { emptyPlaces } from '../src/quiet2/magnets/places'
import { loadWorking, saveWorking } from '../src/quiet2/magnets/workingState'
import { miniConversationOf } from '../src/quiet2/magnets/conversation'
import '../src/theme.css'
import '../src/app.css'
import '../src/atmosphere.css'
import '../src/fluid/fluid.css'
import '../src/fluid/frame/frame.css'
import '../src/fluid/frame/bar.css'
import '../src/fluid/conversation/conversation.css'
import '../src/quiet2/quiet2.css'
import '../src/quiet2/magnets/magnet.css'
const OWN = 'ent-frameown111', ME = 'ent-frameowner1', AGENT = 'ent-frameagent1'
page.saw('frame-corpus@frame-instance')
const empty = new URLSearchParams(location.search).has('empty')
let state: any = { title: 'Frame Magnet', loading: false, results: [], x: 12, y: 12, open: true, wide: false,
  tab: 'Summary', overlay: null, places: emptyPlaces(), query: '', searchType: 'All', searchTarget: null,
  searchListScroll: 0, lens: null, returnRoute: null, settingsReturn: null, context: null,
  contextSuppressed: false, carried: null, ...loadWorking('http://synthetic.invalid||frame-corpus', 'mag-frame') }
const heard = new Set<() => void>()
const r: any = { id: 'frame-browser', brainKey: 'http://synthetic.invalid||frame-corpus',
  saved: { id: 'mag-frame', name: 'Frame Magnet', config: { conversation: OWN, sources: [{ kind: 'conversation', conversation: 'ent-framesource' }] } },
  snapshot: () => state, subscribe: (fn: () => void) => { heard.add(fn); return () => heard.delete(fn) },
  update: (change: any) => { state = { ...state, ...change }; saveWorking(r.brainKey, r.saved.id, state); heard.forEach((fn) => fn()); (window as any).frame?.notify?.() },
  read: async () => {}, cancel: () => {}, dispose: () => {} }
const turn = (n: number, text = `Frame post ${n}.`) => ({ id: `ent-framepost${n}11`, number: n, author: ME,
  author_alias: '@fixture', at: 1795000000, parts: [{ type: 'text', text }], replies: [], thread_replies: 0, expectations: [] })
const api: any = { calls: [], records: new Map(), resolve: null, mode: 'immediate', brain: 'frame-instance', canWrite: true }
;(window as any).frame = api
window.fetch = async (input: any, init: any = {}) => {
  const path = String(input), response = (body: any) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  if (path === '/fluid/api/needs-you/brain') return response({ brain: { corpus_id: 'frame-corpus', instance: api.brain } })
  if (path.startsWith('/fluid/api/participants')) return response({ me: ME, participants: [{ id: ME, alias: '@Owner', default_runtime: null, runtime_mode: 'undeclared' }, { id: AGENT, alias: '@FixtureAgent', default_runtime: null, runtime_mode: 'undeclared' }] })
  if (path === '/api/personas') return response({ personas: [] })
  if (path.startsWith('/api/who/')) return response({ designated_persona: null })
  if (path === '/api/execution') return response({ runtimes: [], running: [], default_runtime: null })
  if (path === '/api/capacity') return response({ runtimes: [] })
  if (path.includes('/perspectives')) return response({ brain: 'frame-corpus@frame-instance', magnet: r.saved.id, perspectives: [], selected: null, next: null })
  if (path.endsWith('/collection')) return response(empty
    ? { magnet: r.saved.id, config: r.saved.config, activation: null, page: null }
    : { magnet: r.saved.id, config: r.saved.config, activation: { post: 'ent-framecollect', at: 1795000000, artifact: { ref: 'adm-framebatch1', digest: 'captured', size: 42, media_type: 'application/json' } }, page: { sources: [] } })
  if (path === '/fluid/api/posts' || path === '/fluid/api/requests') {
    const body = JSON.parse(init.body); api.calls.push({ path, body, headers: init.headers })
    if (!api.records.has(body.op)) api.records.set(body.op, { post: `ent-framerecord${api.records.size + 1}`, number: api.records.size + 1 })
    const answer = api.records.get(body.op)
    if (api.mode === 'hold') return new Promise((resolve) => { api.resolve = () => resolve(response(answer)) })
    return response({ ...answer, replayed: api.calls.filter((c: any) => c.body.op === body.op).length > 1 })
  }
  if (path.startsWith(`/api/conversations/${OWN}`)) return response({ id: OWN, name: 'Frame Magnet conversation',
    participants: [], topics: [], turns: [turn(1), turn(2)], turns_total: 2, owed: [], batch: { older: 0, first: 1 } })
  if (path.startsWith('/fluid/api/search')) return response({ hits: [], more: false })
  throw Error(`Fixture refused unexpected fetch: ${path}`)
}
api.resource = r
api.state = () => state
api.store = () => miniConversationOf(r, true, 'frame-corpus@frame-instance').store.snapshot()
/* Enough in every view that the reading area has something to scroll. */
const long = (title: string) => <section><h3>{title}</h3>{Array.from({ length: 45 }, (_, n) => <p key={n}>{title} reading line {n}</p>)}</section>
function App() {
  const [, bump] = useState(0)
  api.notify = () => bump((n) => n + 1)
  return <main className="fx q2" style={{ fontFamily: 'sans-serif', background: '#191b1f', height: '100vh', color: '#eee8e6', position: 'relative' }}>
    <Layer />
    <Magnet resource={r} onExpand={() => {}} onCollapse={() => {}}
      footerComposer={<ComposerBar resource={r} canWrite={api.canWrite} />}
      views={{ Summary: long('Summary'), All: long('All'), Posts: long('Posts'), Files: long('Files'),
        Perspectives: long('Perspectives'), search: long('Search'), settings: long('Settings'),
        Conversation: <MiniConversation resource={r} canWrite={api.canWrite} onEvidence={(ref) => { api.evidence = ref }} /> }} />
  </main>
}
createRoot(document.getElementById('root')!).render(<App />)
