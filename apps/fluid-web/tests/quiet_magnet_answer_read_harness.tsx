/** THE ANSWER AS IT IS READ, over the words TEST's own candidate holds.
 *
 *  Owner `ent-bce57ba67f38`. The fixture served here is not invented: it is
 *  the frozen reply `perspectives_work.finalize` holds for the owner's
 *  astronomy Magnet on release 20261126-94928a5 (reply Turn
 *  `ent-116c910c16c2`, read back from `/api/turns/` on the running TEST
 *  candidate), with the 17 collected rows that answer cites, exactly as
 *  `GET /fluid/api/magnets/<id>/collection` serves them. So its agent
 *  preamble, its fused sentences and its direct citation tokens are the real
 *  ones, and what is photographed is what the owner was reading.
 *
 *  Synthetic HTTP, no Brain and no agent, exactly as the other Magnet
 *  screenshot harnesses here (`quiet_magnet_answer_harness.tsx`): `fetch` is
 *  stubbed to the shapes the server's own routes serve, and the components
 *  are the real `Summary` and `Perspectives` over a real `MagnetResource`.
 *
 *  `?as=recorded` draws the SAME words through the reading this commit
 *  replaced -- the recorded text split on newlines, each line laid out as a
 *  statement, with no citation index -- which is what `InquiryPanel` did
 *  before. It is the before picture on the same words and the same
 *  stylesheet.
 *
 *  It asserts nothing: the unit files do that. */
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import Summary from '../src/quiet2/magnets/Summary'
import Perspectives from '../src/quiet2/magnets/InquiryPanel'
import { AnswerStatement } from '../src/quiet2/magnets/links'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { page } from '../src/brainBinding'
import { ANSWER, CONFIG_SOURCES, SOURCES, MID, STANDING } from './quiet_magnet_answer_read_fixture'

page.saw('answer-read-fixture@instance')
const asRecorded = new URLSearchParams(location.search).get('as') === 'recorded'

const config = {
  id: MID, name: 'Space missions and astronomy — what launched, what was found',
  conversation: 'ent-answerreadconv',
  sources: CONFIG_SOURCES,
  selection: { informationTypes: ['post', 'file'], dates: {} },
  collection: { mode: 'manual' }, synthesis: { mode: 'manual' },
  notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' },
}
const batchRef = 'adm-answerreadbat'
const QUESTION = 'What is the state of what this Magnet has gathered?'

const detail = { magnet: MID, perspective: STANDING, name: 'What this Magnet has gathered',
  retired: false,
  question: { ref: 'adm-answerreadq11', digest: 'c'.repeat(64), size: 64, media_type: 'application/json' },
  current_question: { text: QUESTION, revision: 'adm-answerreadq11' },
  events: 1, selected: STANDING, standing: STANDING }

/** Recorded as the server records an answer whose words are on the event.
 *  The words are the frozen reply's own characters, unchanged. */
const answered = {
  seq: 1, post: 'ent-answerreadans', event: 'answered', perspective: STANDING,
  snapshot: { ref: 'adm-answerreadsnp', digest: 'b'.repeat(64), size: 5155, media_type: 'application/json' },
  data: { text: ANSWER, question: QUESTION,
    answer: { ref: 'adm-answerreadpkg', digest: 'f'.repeat(64), size: 5155, media_type: 'application/json' },
    written_by: 'Written by an agent reasoning over this Magnet’s collected records.',
    provenance: { grounded_in: 'collection', explored_outside: false, outside_authorized: [], outside_reads: [] },
    basis: { batch: batchRef, rows: SOURCES.reduce((n, s) => n + s.results.length, 0), new_count: 0 } },
}

const response = (v: unknown) =>
  new Response(JSON.stringify({ brain: 'answer-read-fixture@instance', magnet: MID, ...(v as object) }), { status: 200 })
const realFetch = window.fetch
window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const path = new URL(String(input), location.href).pathname
  if (path.endsWith('/needs-you/brain'))
    return response({ brain: { corpus_id: 'answer-read-fixture', instance: 'instance' } })
  if (path.includes('/perspectives')) {
    const tail = path.split('/perspectives')[1]
    const [topic, verb] = tail.slice(1).split('/')
    if (init.method === 'POST') return response({ perspective: topic || STANDING })
    if (!tail) return response({ perspectives: [detail], selected: STANDING, standing: STANDING,
      next: null, grounded_answers: true })
    if (verb === 'history') return response({ perspective: topic, events: [answered], next: null, through: 1 })
    return response(detail)
  }
  if (path.includes('/collection')) return response(collection)
  return realFetch(input, init)
}

const collection = { magnet: MID, config,
  activation: { post: 'ent-answerreadact', state: 'complete', at: 1795971000,
    artifact: { ref: batchRef, digest: 'd'.repeat(64), size: 165925, media_type: 'application/json' } },
  page: { sources: SOURCES } }

const resource = createMagnetResource({
  id: `qm-${MID}`, brainKey: 'answer-read-fixture',
  saved: { id: MID, name: config.name, config: config as never },
  get: async (path: string) => {
    if (path.startsWith('/fluid/api/participants'))
      return { status: 200, body: { participants: [], me: 'ent-answerreadown' } }
    return { status: 200, body: collection }
  },
})

/** The reading this commit replaced, on the same words. */
function AsRecorded() {
  return <section className="q2-magnet-perspectives" aria-label="Perspectives">
    <div className="mgd-chatbubble"><b className="q2p-asked">{QUESTION}</b></div>
    <div className="mgd-answer">
      {ANSWER.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
        .map((line, i) => <AnswerStatement key={i} line={line} />)}
    </div>
  </section>
}

function App() {
  const [tab, setTab] = useState<'summary' | 'perspectives'>('summary')
  return <div className="q2-magnet-card">
    <div className="mgd-row" style={{ gap: 8, marginBottom: 12 }}>
      <button type="button" id="shot-summary" className="mgd-button" onClick={() => setTab('summary')}>Summary</button>
      <button type="button" id="shot-perspectives" className="mgd-button" onClick={() => setTab('perspectives')}>Perspectives</button>
    </div>
    {asRecorded ? <AsRecorded />
      : tab === 'summary'
        ? <Summary resource={resource} onPost={() => {}} />
        : <Perspectives resource={resource} canWrite={false} onEvidence={() => {}} />}
  </div>
}

void resource.read().finally(() => {
  createRoot(document.getElementById('root')!).render(<App />)
})
