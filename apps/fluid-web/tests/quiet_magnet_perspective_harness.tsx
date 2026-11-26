import { useState, useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import Perspectives from '../src/quiet2/magnets/InquiryPanel'
import { miniComposerDraft, saveMiniComposer, subscribeMiniComposer } from '../src/quiet2/magnets/conversation'
import { perspectivesOf } from '../src/quiet2/magnets/perspectives'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { page } from '../src/brainBinding'
const A = 'ent-fixturetopicA', B = 'ent-fixturetopicB', mid = 'mag-perspective-browser'
const collectionSource = 'ent-fixturesource111'
page.saw('perspective-fixture@instance')
const initial = () => ({ selected: A as string | null, topics: [A, B].map((perspective, i) => ({ perspective, name: i ? 'Alternative' : 'Original', retired: false, question: { ref: `adm-revision${i}`, digest: 'a'.repeat(64), size: 20, media_type: 'application/json' }, current_question: { text: i ? 'Alternative hypothesis' : 'Latest saved question \u03b1\u{1f642}', revision: `adm-revision${i}` }, events: 105 })), ledger: {} as Record<string, any>, edits: 0 })
let db = JSON.parse(localStorage.getItem('perspective-browser-db') ?? 'null') ?? initial()
const persist = () => localStorage.setItem('perspective-browser-db', JSON.stringify(db))
let batch = 0
const api = { calls: [] as any[], loseNext: false, edits: () => db.edits,
  // Simulate the Magnet reporting a newly collected batch: the only thing
  // that drives the panel's one automatic read of a kept question.
  collectAgain: async () => { batch++; resource.cancel(); await resource.read() } }
;(window as any).perspectiveTest = api
const response = (v: any) => new Response(JSON.stringify({ brain: 'perspective-fixture@instance', magnet: mid, ...v }), { status: 200 })
window.fetch = async (input: any, init: any = {}) => {
  const url = new URL(String(input), location.href), path = url.pathname
  if (path.endsWith('/needs-you/brain')) return response({ brain: { corpus_id: 'perspective-fixture', instance: 'instance' } })
  if (!path.includes('/perspectives')) throw new Error(`Unexpected non-Perspective API ${path}`)
  const tail = path.split('/perspectives')[1], [topic, verb] = tail.slice(1).split('/')
  api.calls.push({ tail, method: init.method ?? 'GET', body: init.body && JSON.parse(init.body) })
  if (init.method === 'POST') {
    const body = JSON.parse(init.body)
    if (!db.ledger[body.op]) {
      let result: any
      if (tail === '/selected') { db.selected = body.perspective; result = { selected: db.selected } }
      else if (!tail) {
        const id = `ent-newtopic${db.topics.length}11`, ref = `adm-newquestion${db.topics.length}`
        db.topics.push({ perspective: id, name: body.name, retired: false, question: { ref }, current_question: { text: body.question, revision: ref }, events: 2 }); result = { perspective: id }
      } else {
        const row = db.topics.find((r: any) => r.perspective === topic)
        if (verb === 'question') { const ref = `adm-edit${++db.edits}`; row.current_question = { text: body.text, revision: ref }; row.question = { ref }; row.events++ }
        // H6's durable rename: the display name only. Identity and question stay.
        else if (verb === 'rename') { row.name = body.name; row.events++ }
        else if (verb === 'retire') { row.retired = true; if (db.selected === topic) db.selected = null }
        else if (verb === 'resume') row.retired = false
        else throw new Error(`Unavailable grounded route ${verb}`)
        result = { perspective: topic }
      }
      db.ledger[body.op] = result; persist()
    }
    if (api.loseNext) { api.loseNext = false; throw new Error('Fixture lost acknowledgement') }
    return response(db.ledger[body.op])
  }
  if (!tail) return response({ perspectives: db.topics, selected: db.selected, next: null })
  if (verb === 'history') return response({ perspective: topic, events: [{ post: 'ent-oldrevision1', event: 'question', seq: 1, perspective: topic, snapshot: { ref: 'adm-oldrevision' }, data: { text: 'Old first-page wording' } }], next: null })
  return response({ ...db.topics.find((r: any) => r.perspective === topic), selected: db.selected })
}
// A real MagnetResource (the one `useCollectedMark` and `SupportingItems` are
// built against), fed a fixture `get` instead of a fixture Brain -- so the
// collected batch can actually change, which is what the panel watches to
// drive its one automatic read of a kept question.
const config = { id: mid, sources: [{ kind: 'conversation', conversation: collectionSource }], conversation: 'ent-ownfixture111', selection: {}, collection: { mode: 'one-time' }, synthesis: { mode: 'manual' }, notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } }
const resource = createMagnetResource({ id: mid, brainKey: 'http://fixture||perspective-fixture', saved: { id: mid, name: 'Fixture', config: config as any },
  get: async (path: string) => {
    if (path.startsWith('/fluid/api/participants')) return { status: 200, body: { participants: [], me: 'ent-fixtureowner111' } }
    return { status: 200, body: { magnet: mid, config,
      activation: { post: `ent-fixturebatch${batch}1`, artifact: { ref: `adm-fixturebatch${batch}1` }, at: batch, state: 'complete' },
      page: { sources: [{ key: `conversation:${collectionSource}`, source: config.sources[0], status: 'ok', results: [
        { kind: 'post', id: `ent-fixtureitem${batch}1`, conversation: collectionSource, version: `ent-fixtureitem${batch}1`, number: 1, value: { text: `Collected item from batch ${batch}` } },
      ] }] } } }
  } })
const originalUpdate = resource.update
const r: any = Object.assign(resource, { update: (v: any) => { originalUpdate(v); if (v.tab) (window as any).showTab(v.tab) } })
function App() {
  const [tab, setTab] = useState('Perspectives'); (window as any).showTab = setTab
  const draft = useSyncExternalStore((fn) => subscribeMiniComposer(r, fn), () => miniComposerDraft(r), () => miniComposerDraft(r))
  const store = perspectivesOf(r)
  return <main><button onClick={() => setTab('Perspectives')}>Open Perspectives</button><button onClick={() => setTab('Conversation')}>Open Conversation draft</button>{tab === 'Perspectives' ? <Perspectives resource={r} canWrite={true} onEvidence={() => {}} /> : <label>Conversation draft<textarea value={draft.text} onChange={(e) => saveMiniComposer(r, { ...draft, text: e.target.value })} /></label>}<button onClick={() => { localStorage.removeItem('perspective-browser-db'); location.reload() }}>Reset fixture</button><output>{store.snapshot().selected}</output></main>
}
void resource.read()
createRoot(document.getElementById('root')!).render(<App />)
