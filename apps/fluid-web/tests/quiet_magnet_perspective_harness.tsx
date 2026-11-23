import { useState, useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import Perspectives from '../src/quiet2/magnets/InquiryPanel'
import { miniComposerDraft, saveMiniComposer, subscribeMiniComposer } from '../src/quiet2/magnets/conversation'
import { perspectivesOf } from '../src/quiet2/magnets/perspectives'
import { page } from '../src/brainBinding'
const A = 'ent-fixturetopicA', B = 'ent-fixturetopicB', mid = 'mag-perspective-browser'
page.saw('perspective-fixture@instance')
const initial = () => ({ selected: A as string | null, topics: [A, B].map((perspective, i) => ({ perspective, name: i ? 'Alternative' : 'Original', retired: false, question: { ref: `adm-revision${i}`, digest: 'a'.repeat(64), size: 20, media_type: 'application/json' }, current_question: { text: i ? 'Alternative hypothesis' : 'Latest saved question \u03b1\u{1f642}', revision: `adm-revision${i}` }, events: 105 })), ledger: {} as Record<string, any>, edits: 0 })
let db = JSON.parse(localStorage.getItem('perspective-browser-db') ?? 'null') ?? initial()
const persist = () => localStorage.setItem('perspective-browser-db', JSON.stringify(db))
const api = { calls: [] as any[], loseNext: false, edits: () => db.edits }
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
const r: any = { id: mid, brainKey: 'http://fixture||perspective-fixture', saved: { id: mid, name: 'Fixture', config: { sources: [], conversation: 'ent-ownfixture111' } }, snapshot: () => ({ tab: 'Perspectives' }), update: (v: any) => { if (v.tab) (window as any).showTab(v.tab) } }
function App() {
  const [tab, setTab] = useState('Perspectives'); (window as any).showTab = setTab
  const draft = useSyncExternalStore((fn) => subscribeMiniComposer(r, fn), () => miniComposerDraft(r), () => miniComposerDraft(r))
  const store = perspectivesOf(r)
  return <main><button onClick={() => setTab('Perspectives')}>Open Perspectives</button><button onClick={() => setTab('Conversation')}>Open Conversation draft</button>{tab === 'Perspectives' ? <Perspectives resource={r} canWrite={true} onEvidence={() => {}} /> : <label>Conversation draft<textarea value={draft.text} onChange={(e) => saveMiniComposer(r, { ...draft, text: e.target.value })} /></label>}<button onClick={() => { localStorage.removeItem('perspective-browser-db'); location.reload() }}>Reset fixture</button><output>{store.snapshot().selected}</output></main>
}
createRoot(document.getElementById('root')!).render(<App />)
