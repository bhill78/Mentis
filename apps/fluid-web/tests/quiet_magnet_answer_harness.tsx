/** PART F's SCREENSHOT HARNESS: the Summary tab and the Perspectives panel
 *  with a REAL recorded answer, mounted in a browser on this checkout's dev
 *  server.
 *
 *  Synthetic HTTP, no Brain and no agent: the fixture serves exactly what the
 *  server's own routes serve -- a collection read, the Perspective listing with
 *  its `standing` Topic, one Perspective's detail, and its bounded history with
 *  `answered` events carrying the text, the provenance and the basis that
 *  `mentis/magnet/perspectives_work.answer` records. The components are the
 *  real ones (`Summary`, `Perspectives`) over a real `MagnetResource` and the
 *  real `PerspectiveStore`, so what is photographed is what the owner sees.
 *
 *  The answer wording here is what the server actually writes for this
 *  collection, taken from the Python oracle's own output
 *  (`tests/test_magnet_perspectives.py`): statements about what the Magnet has
 *  gathered, what arrived in this collection, and what each source gave.
 *
 *  `?outside=1` serves the same answer with Part A's `explored_outside` true,
 *  so the rendered distinction between grounded-in-the-collection and
 *  explored-outside can be photographed side by side. Nothing in the product
 *  can produce that for a synthesis -- A refuses it structurally -- which is
 *  exactly why it has to be driven here to be seen. */
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import Summary from '../src/quiet2/magnets/Summary'
import Perspectives from '../src/quiet2/magnets/InquiryPanel'
import { perspectivesOf } from '../src/quiet2/magnets/perspectives'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { page } from '../src/brainBinding'

const mid = 'mag-answerfixture1'
const STANDING = 'ent-standingtopic1'
const ASKED_TOPIC = 'ent-askedtopic1111'
const SOURCE = 'ent-answersource11'
const batchRef = 'adm-answerbatch21'
page.saw('answer-fixture@instance')
const outside = new URLSearchParams(location.search).has('outside')

const config = { id: mid, name: 'Bench calibration', conversation: 'ent-answerconv111',
  sources: [{ kind: 'conversation', conversation: SOURCE },
            { kind: 'file', collection: 'col-benchlogs', path: 'nested/calibration.txt' }],
  selection: { informationTypes: ['post', 'file'], dates: {} }, collection: { mode: 'one-time' },
  synthesis: { mode: 'manual' }, notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' } }

const rows = [
  { kind: 'post', id: 'ent-answeritem111', version: 'ent-answeritem111', conversation: SOURCE,
    author: 'ent-answerauthor1', at: 1763900000, number: 11, via: 'home',
    value: { parts: [{ type: 'text', text: 'Calibration of the bench reference drifted by 37 microns this week. Calibration matters.' }] } },
  { kind: 'post', id: 'ent-answeritem222', version: 'ent-answeritem222', conversation: SOURCE,
    author: 'ent-answerauthor1', at: 1764000300, number: 12, via: 'home',
    value: { parts: [{ type: 'text', text: 'The bench reference was recalibrated. Calibration of the spare bench is still pending.' }] } },
  { kind: 'post', id: 'ent-answeritem333', version: 'ent-answeritem333', conversation: SOURCE,
    author: 'ent-answerauthor1', at: 1764086700, number: 13, via: 'home',
    value: { parts: [{ type: 'text', text: 'A newly arrived record: the spare bench drifted by 12 microns overnight.' }] } },
]
const held = [{ kind: 'file', id: 'adm-answerfile111', version: 'adm-answerfile111', conversation: null,
  author: null, at: 1764000400, via: 'held-source',
  value: { ref: 'adm-answerfile111', digest: 'a'.repeat(64), collection: 'col-benchlogs',
    path: 'nested/calibration.txt', text: 'Bench log: reference 37um, spare 12um.', offset: 0, end: 38,
    size: 38, acquired_at: 1764000400, shortened: false, omitted_bytes: 0, next_offset: null,
    citation: `adm-answerfile111@${'a'.repeat(12)}[0:38]` } }]

const provenance = (explored: boolean) => explored
  ? { grounded_in: 'collection', explored_outside: true,
      outside_authorized: [{ kind: 'runtime-web-search' }],
      outside_reads: [{ what: 'runtime-web-search', collection: 'the runtime’s own web search' }] }
  : { grounded_in: 'collection', explored_outside: false, outside_authorized: [], outside_reads: [] }

const EARLIER = [
  'This Magnet has gathered 3 records from 2 sources, collected 2026-11-25.',
  'From the Conversation: 2 records, most recently “The bench reference was recalibrated. Calibration of the spare bench is still pending.”.',
  'From the held file: 1 record, most recently “Bench log: reference 37um, spare 12um.”.',
  'The material it holds was written between 2026-11-23 and 2026-11-25.',
].join('\n')
const CURRENT = [
  'This Magnet has gathered 4 records from 2 sources, collected 2026-11-26.',
  '1 of them arrived in this collection and was not in the one before it.',
  'New, from the Conversation (2026-11-26): “A newly arrived record: the spare bench drifted by 12 microns overnight.”',
  'From the Conversation: 3 records, most recently “A newly arrived record: the spare bench drifted by 12 microns overnight.”.',
  'From the held file: 1 record, most recently “Bench log: reference 37um, spare 12um.”.',
  'The material it holds was written between 2026-11-23 and 2026-11-26.',
].join('\n')
const ASKED = [
  '2 of the 4 records this Magnet has collected mention “spare” and “drifted”. Here is what they say.',
  'From the Conversation (2026-11-26), on “spare” and “drifted”: “A newly arrived record: the spare bench drifted by 12 microns overnight.”',
  'From the Conversation (2026-11-23), on “drifted”: “Calibration of the bench reference drifted by 37 microns this week. Calibration matters.”',
].join('\n')

const WRITTEN_BY = 'Written by Mentis from this Magnet’s collected rows alone. The records it names are the records it read, quoted as they were captured; nothing outside this collection was read, and no authorization can widen it. It is not an agent’s interpretation.'

const ASKED_EARLIER = [
  '1 of the 3 records this Magnet has collected mention “spare” and “drifted”. Here is what they say.',
  'From the Conversation (2026-11-23), on “drifted”: “Calibration of the bench reference drifted by 37 microns this week. Calibration matters.”',
].join('\n')

const answered = (seq: number, post: string, text: string, batch: string, topic = STANDING, over = {}) => ({
  seq, post, event: 'answered', perspective: topic,
  snapshot: { ref: `adm-answersnap${seq}`, digest: 'b'.repeat(64), size: 512, media_type: 'application/json' },
  data: { text, answer: { ref: `adm-answerpkg${seq}1` }, written_by: WRITTEN_BY,
    provenance: provenance(outside), basis: { batch, rows: 4, new_count: seq - 1 }, ...over } })

const standingDetail = { magnet: mid, perspective: STANDING, name: 'What this Magnet has gathered',
  retired: false, question: { ref: 'adm-standingq111', digest: 'c'.repeat(64), size: 64, media_type: 'application/json' },
  current_question: { text: 'What is the state of what this Magnet has gathered?', revision: 'adm-standingq111' },
  events: 5, selected: ASKED_TOPIC, standing: STANDING }
const askedDetail = { magnet: mid, perspective: ASKED_TOPIC, name: 'Does the spare bench drift?',
  retired: false, question: { ref: 'adm-askedq1111111', digest: 'e'.repeat(64), size: 64, media_type: 'application/json' },
  current_question: { text: 'Does the spare bench drift, and by how much?', revision: 'adm-askedq1111111' },
  events: 4, selected: ASKED_TOPIC, standing: STANDING }

/** The standing Perspective's own answers: the evolving summary, and the one it
 *  superseded when this collection brought a record the earlier answer had not
 *  read. The asked question keeps its own, in its own Topic. */
const histories: Record<string, unknown[]> = {
  [STANDING]: [answered(1, 'ent-answerevent1', EARLIER, 'adm-answerbatch11'),
               answered(2, 'ent-answerevent2', CURRENT, batchRef)],
  [ASKED_TOPIC]: [answered(1, 'ent-askedevent111', ASKED_EARLIER, 'adm-answerbatch11', ASKED_TOPIC),
                  answered(2, 'ent-askedevent222', ASKED, batchRef, ASKED_TOPIC)],
}

const response = (v: unknown) => new Response(JSON.stringify({ brain: 'answer-fixture@instance', magnet: mid, ...(v as object) }), { status: 200 })
const realFetch = window.fetch
window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const path = new URL(String(input), location.href).pathname
  if (path.endsWith('/needs-you/brain')) return response({ brain: { corpus_id: 'answer-fixture', instance: 'instance' } })
  if (path.includes('/perspectives')) {
    const tail = path.split('/perspectives')[1]
    const [topic, verb] = tail.slice(1).split('/')
    if (init.method === 'POST') return response({ perspective: topic || STANDING, text: CURRENT })
    if (!tail) return response({ perspectives: [standingDetail, askedDetail], selected: ASKED_TOPIC, standing: STANDING, next: null, grounded_answers: true })
    if (verb === 'history') return response({ perspective: topic, events: histories[topic] ?? [], next: null, through: 2 })
    return response(topic === STANDING ? standingDetail : { ...askedDetail, perspective: topic })
  }
  if (path.includes('/collection')) return response({ config, activation: { post: 'ent-answeract111', artifact: { ref: batchRef, digest: 'd'.repeat(64), size: 4096, media_type: 'application/json' }, at: 1764100000, state: 'complete' }, page: { sources: [
    { key: `conversation:${SOURCE}`, source: config.sources[0], status: 'ok', results: rows },
    { key: 'file:col-benchlogs:nested/calibration.txt', source: config.sources[1], status: 'ok', results: held }] } })
  return realFetch(input, init)
}

const resource = createMagnetResource({ id: `qm-${mid}`, brainKey: 'http://fixture||answer-fixture',
  saved: { id: mid, name: 'Bench calibration', config: config as never },
  get: async (path: string) => {
    if (path.startsWith('/fluid/api/participants')) return { status: 200, body: { participants: [], me: 'ent-answerowner11' } }
    return { status: 200, body: { magnet: mid, config,
      activation: { post: 'ent-answeract111', artifact: { ref: batchRef, digest: 'd'.repeat(64), size: 4096, media_type: 'application/json' }, at: 1764100000, state: 'complete' },
      page: { sources: [
        { key: `conversation:${SOURCE}`, source: config.sources[0], status: 'ok', results: rows },
        { key: 'file:col-benchlogs:nested/calibration.txt', source: config.sources[1], status: 'ok', results: held }] } } }
  } })

function App() {
  const [tab, setTab] = useState<'Summary' | 'Perspectives'>(
    new URLSearchParams(location.search).get('tab') === 'Perspectives' ? 'Perspectives' : 'Summary')
  return <div className="q2">
    <div className="q2-magnet-card">
      <header><h2>Bench calibration</h2></header>
      <nav>
        <button type="button" onClick={() => setTab('Summary')}>Summary</button>
        <button type="button" onClick={() => setTab('Perspectives')}>Perspectives</button>
      </nav>
      {tab === 'Summary'
        ? <Summary resource={resource} onPost={() => {}} />
        : <Perspectives resource={resource} canWrite={true} onEvidence={() => {}} />}
    </div>
  </div>
}

;(window as never as Record<string, unknown>).partF = { resource, store: () => perspectivesOf(resource) }
void (async () => {
  await resource.read()
  const store = perspectivesOf(resource)
  await store.read()
  await store.readSummary()
  await store.view(ASKED_TOPIC)
  createRoot(document.getElementById('root')!).render(<App />)
})()
