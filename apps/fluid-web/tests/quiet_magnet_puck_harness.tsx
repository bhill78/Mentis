import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import Magnet from '../src/quiet2/magnets/Magnet'
import EvidenceViews from '../src/quiet2/magnets/EvidenceViews'
import Summary from '../src/quiet2/magnets/Summary'
import SettingsView from '../src/quiet2/magnets/SettingsView'
import SearchView from '../src/quiet2/magnets/SearchView'
import { emptyPlaces } from '../src/quiet2/magnets/places'
import type { MagnetResource, MagnetSnapshot } from '../src/quiet2/magnets/contract'

let snap: MagnetSnapshot = { title: 'Colony Island fixture', x: 80, y: 70, tab: 'Summary',
  open: false, wide: false, overlay: null, places: emptyPlaces(), query: '', searchType: 'All',
  searchTarget: null, searchListScroll: 0, lens: null, returnRoute: null, settingsReturn: null,
  context: null, contextSuppressed: false,
  loading: false, status: 'ok', activation: { post: 'ent-batch12345', artifact: { ref: 'adm-batch12345' }, at: 1, state: 'complete' },
  summary: { key: 'conversation:ent-source123', status: 'ok', summary: { posts: 28 } },
  results: [{ kind: 'post', id: 'ent-post12345', number: 28, author: '@fixture' }, { kind: 'file', id: 'adm-fixture', post: 'ent-post12345', value: { title: 'fixture-notes.md' } }], next: 'next' }
const listeners = new Set<() => void>()
const calls: string[] = []
const resource: MagnetResource = { id: 'qm-test', brainKey: 'fixture', saved: { id: 'mag-fixture', name: 'Colony Island fixture', config: { id: 'mag-fixture', sources: [{ kind: 'conversation', conversation: 'ent-source123' }], selection: {}, conversation: 'ent-magnet123', collection: { mode: 'one-time' }, synthesis: { mode: 'manual' }, notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } } }, snapshot: () => snap, subscribe: (fn) => { listeners.add(fn); return () => { listeners.delete(fn) } }, update: (change) => { snap = { ...snap, ...change }; listeners.forEach((f) => f()) }, read: async (more) => { calls.push(more ? 'more' : 'read') }, cancel: () => { calls.push('cancel') }, dispose: () => {} }
Object.assign(window, { magnetTest: { calls, resource } })
function Harness() {
  const [event, setEvent] = useState('')
  const [draft, setDraft] = useState('')
  return <div className="q2"><button id="outside" onClick={() => setEvent('outside')}>Outside</button><output id="event">{event}</output>
    <div style={{ position: 'relative', height: 'calc(100vh - 30px)', width: '100vw' }}>
      <Magnet resource={resource} onExpand={() => setEvent('expand')} onCollapse={() => setEvent('collapse')}
        footerComposer={<form id="composer"><label>Message inside this Magnet<textarea id="message" value={draft} onChange={(e) => setDraft(e.target.value)} /></label></form>}
        views={{
          Summary: <Summary resource={resource} onPost={() => setEvent('post')} />,
          All: <EvidenceViews resource={resource} lens="All" onPost={() => setEvent('post')} onFile={() => setEvent('file')} />,
          Posts: <EvidenceViews resource={resource} lens="Posts" onPost={() => setEvent('post')} onFile={() => setEvent('file')} />,
          Files: <EvidenceViews resource={resource} lens="Files" onPost={() => setEvent('post')} onFile={() => setEvent('file')} />,
          Perspectives: <p>Perspectives unavailable in this harness.</p>,
          Conversation: <p id="conversation-view">Conversation view</p>,
          search: <SearchView resource={resource} />,
          settings: <SettingsView resource={resource} hasOwnConversation canReset
            onReset={() => resource.update({ x: 12, y: 12 })} onRemove={() => setEvent('close')}
            onSource={() => setEvent('source')} onConversation={() => setEvent('own')} onOrigin={() => setEvent('origin')} />,
        }} />
    </div></div>
}
createRoot(document.getElementById('root')!).render(<Harness />)
