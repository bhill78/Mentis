import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import Magnet from '../src/quiet2/magnets/Magnet'
import type { MagnetResource, MagnetSnapshot } from '../src/quiet2/magnets/contract'

let snap: MagnetSnapshot = { title: 'Colony Island fixture', x: 80, y: 70, tab: 'Overview', pinned: false, expanded: false, loading: false, status: 'partial', next: 'next', summary: { key: 'conversation:ent-source123', status: 'partial', summary: { posts: 28 } }, results: [{ kind: 'post', id: 'ent-post12345', number: 28, author: '@fixture' }, { kind: 'file', id: 'adm-fixture', post: 'ent-post12345', value: { title: 'fixture-notes.md' } }] }
const listeners = new Set<() => void>()
const calls: string[] = []
const resource: MagnetResource = { id: 'qm-ind-test', brainKey: 'fixture', saved: { id: 'mag-fixture', name: 'Colony Island fixture', config: { id: 'mag-fixture', sources: [{ kind: 'conversation', conversation: 'ent-source123' }], selection: {} } }, snapshot: () => snap, subscribe: (fn) => { listeners.add(fn); return () => { listeners.delete(fn) } }, update: (change) => { snap = { ...snap, ...change }; calls.push(`update:${JSON.stringify(change)}`); listeners.forEach((f) => f()) }, read: async (more) => { calls.push(more ? 'more' : 'read') }, cancel: () => { calls.push('cancel') }, dispose: () => {} }
Object.assign(window, { indicatorTest: { calls, resource } })
function Harness() {
  const [event, setEvent] = useState('')
  return <div className="q2"><button id="outside" onClick={() => setEvent('outside')}>Outside</button><output id="event">{event}</output><div style={{ position: 'relative', height: 'calc(100vh - 30px)', width: '100vw' }}><Magnet resource={resource} onExpand={() => { setEvent('expand'); resource.update({ expanded: true, pinned: true }) }} onCollapse={() => resource.update({ expanded: false })} onClose={() => setEvent('close')} onPost={() => setEvent('post')} onFile={() => setEvent('file')} onSource={() => setEvent('source')} onConversation={() => setEvent('own')} onOrigin={() => setEvent('origin')} /></div></div>
}
createRoot(document.getElementById('root')!).render(<Harness />)
