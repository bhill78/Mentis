import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import Magnet from '../src/quiet2/magnets/Magnet'
import EvidenceViews from '../src/quiet2/magnets/EvidenceViews'
import { emptyPlaces } from '../src/quiet2/magnets/places'
import type { MagnetResource, MagnetSnapshot } from '../src/quiet2/magnets/contract'

let snap: MagnetSnapshot = { title: 'Colony Island fixture', x: 80, y: 70, tab: 'Summary',
  open: false, wide: false, overlay: null, places: emptyPlaces(), query: '', searchType: 'All',
  searchTarget: null, searchListScroll: 0, lens: null, returnRoute: null, settingsReturn: null,
  context: null, contextSuppressed: false,
  loading: false, status: 'partial', next: 'next', summary: { key: 'conversation:ent-source123', status: 'partial', summary: { posts: 28 } },
  results: [{ kind: 'post', id: 'ent-post12345', number: 28, author: '@fixture' }, { kind: 'file', id: 'adm-fixture', post: 'ent-post12345', value: { title: 'fixture-notes.md' } }] }
const listeners = new Set<() => void>()
const calls: string[] = []
const resource: MagnetResource = { id: 'qm-ind-test', brainKey: 'fixture', saved: { id: 'mag-fixture', name: 'Colony Island fixture', config: { id: 'mag-fixture', sources: [{ kind: 'conversation', conversation: 'ent-source123' }], selection: {} } }, snapshot: () => snap, subscribe: (fn) => { listeners.add(fn); return () => { listeners.delete(fn) } }, update: (change) => { snap = { ...snap, ...change }; calls.push(`update:${JSON.stringify(change)}`); listeners.forEach((f) => f()) }, read: async (more) => { calls.push(more ? 'more' : 'read') }, cancel: () => { calls.push('cancel') }, dispose: () => {} }
Object.assign(window, { indicatorTest: { calls, resource } })
function Harness() {
  const [event, setEvent] = useState('')
  return <div className="q2"><button id="outside" onClick={() => setEvent('outside')}>Outside</button><output id="event">{event}</output>
    <div style={{ position: 'relative', height: 'calc(100vh - 30px)', width: '100vw' }}>
      <Magnet resource={resource} onExpand={() => setEvent('expand')} onCollapse={() => setEvent('collapse')}
        views={{
          Summary: <p>Summary view</p>,
          All: <EvidenceViews resource={resource} lens="All" onPost={() => setEvent('post')} onFile={() => setEvent('file')} />,
          Posts: <EvidenceViews resource={resource} lens="Posts" onPost={() => setEvent('post')} onFile={() => setEvent('file')} />,
          Files: <EvidenceViews resource={resource} lens="Files" onPost={() => setEvent('post')} onFile={() => setEvent('file')} />,
          Perspectives: <p>Perspectives unavailable: no supported Perspectives type exists yet</p>,
          Conversation: <p>Conversation view</p>,
        }} />
    </div></div>
}
createRoot(document.getElementById('root')!).render(<Harness />)
