import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import RunControls from '../src/quiet2/activity/RunControls'
import { guardWrites } from '../src/brainBinding'
import '../src/quiet2/dock.css'

const query = new URLSearchParams(location.search)
const held = query.get('held') !== '0'
let published = query.get('pending') !== '1'
let fail = false
let otherBrain = false
let delayed = false
let finish: (() => void) | null = null
let reads = 0
const text = 'BEGIN\n' + 'x'.repeat(11000) + '\nMIDDLE\n' + 'y'.repeat(11000) + '\nTAIL\n'
const recorded = { terminal: 'failed', collector_text: text, collector_version: 1, collector_chars: text.length,
  error: 'FULL ERROR ' + 'e'.repeat(700) + ' ERROR TAIL', notes: ['FULL NOTE ' + 'n'.repeat(700) + ' NOTE TAIL'], reply_turn: 'ent-answer', artifacts: ['adm-exact'] }
const fetchFixture: typeof fetch = async (input) => {
  const url = String(input)
  if (url.includes('needs-you/brain')) return Response.json({ brain: { corpus_id: otherBrain ? 'other' : 'fixture', instance: 'one' } })
  if (url.includes('/feed')) {
    reads++
    if (delayed) await new Promise<void>(resolve => { finish = resolve })
    if (fail) return Response.json({ error: 'fixture read refused' }, { status: 403 })
    return Response.json({ run: 'fixture-run', held_here: held, ended_at: 9, events: [{ id: 'm', kind: 'message', seq: 1, at: 1, text: 'live summary sentinel' }], next: 301, ...(published ? { recorded } : {}) })
  }
  throw new Error('Unexpected fixture request: ' + url)
}
window.fetch = fetchFixture
guardWrites()
function Fixture() {
  const [opened, setOpened] = useState<string | null>(null)
  const [publishedLabel, setPublishedLabel] = useState(published)
  return <main style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
    <p>Sanitized synthetic C2 fixture; no Brain or runtime is contacted.</p>
    <button onClick={() => { published = true; setPublishedLabel(true) }}>Publish terminal</button><span>{publishedLabel ? 'Published' : 'Pending'}</span>
    <button onClick={() => { fail = !fail }}>Toggle read failure</button>
    <button onClick={() => { delayed = true }}>Delay next read</button>
    <button onClick={() => { otherBrain = true; finish?.() }}>Switch Brain and finish read</button>
    <button onClick={() => { document.querySelector('#reads')!.textContent = String(reads) }}>Count reads</button><output id="reads" />
    <RunControls run="fixture-run" who="Builder" ended runtime="codex" referenceWords={{ names: s => s, links: s => s, open: (id, words) => <button data-ref={id} onClick={() => setOpened(id)}>{words}</button> }} />
    {opened && <dialog open aria-label="Fixture exact reference"><p>{opened}</p><button onClick={() => { const id = opened; setOpened(null); requestAnimationFrame(() => document.querySelector<HTMLButtonElement>(`[data-ref="${id}"]`)?.focus()) }}>Close reference</button></dialog>}
  </main>
}
createRoot(document.getElementById('root')!).render(<Fixture />)
