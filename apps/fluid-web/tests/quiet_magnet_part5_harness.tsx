/** PART 5's SCREENSHOT HARNESS: information presented by what it represents.
 *
 *  The real components (`Summary`, `Inspection`) over a real `MagnetResource`
 *  and the real `PerspectiveStore`, on this checkout's own dev server. Synthetic
 *  HTTP, no Brain and no agent: the fixture serves exactly what the server's own
 *  routes serve.
 *
 *  THE FIXTURE IS THE REAL MAGNET'S SHAPE. Its rows are acquired web rows
 *  written the way `mentis/sources/feeds.py::_entry_body` writes one -- headline,
 *  blank line, permalink, blank line, the summary, a `--` rule, then
 *  `Published:` and `Publisher:` -- with the bounds, digest and citation
 *  `collectionRows` verifies, so what is photographed is read back out of bytes
 *  of the recorded shape. Its answers carry `lines: [{text, cites}]` beside the
 *  joined `text`, which is what `mentis/magnet/perspectives_work.py::answer`
 *  records and what Part 5 renders.
 *
 *  Four states, by `?state=`:
 *    synthesis  (default) the Python synthesis: statement, the record's own
 *               words, and the collected records it was written from as presses
 *    briefing   an answer written as a document: prose, a heading and a table,
 *               drawn by `Prose` -- the presentation Part 3's dispatched run
 *               produces, shown now over a recorded answer of that shape
 *    briefing-multi the same document, but recorded as review `ent-19c3c55af28c`
 *               found a real one can be: a paragraph cut off mid-sentence and
 *               continued in the next entry, a table with one entry per row,
 *               and an ordered list with one entry per item -- each entry
 *               naming only the record it was actually written from
 *    unanswered no answer recorded: the lead is what the material NAMES, and no
 *               count is above the fold
 *    inspect    one collected record opened: its headline a heading, its address
 *               a link, its words prose -- not a block of its captured bytes
 *
 *  It asserts nothing about behaviour: `quiet_magnet_presentation_unit.ts` does
 *  that. */
import { createRoot } from 'react-dom/client'
import Summary from '../src/quiet2/magnets/Summary'
import Inspection from '../src/quiet2/magnets/Inspection'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { page } from '../src/brainBinding'
// THE SHEETS THE REAL SURFACE HAS, in the order the app loads them
// (`src/fluid/main.tsx`). Without `theme.css` every `var(--…)` is undefined,
// which invalidates the `font` shorthands that reference them -- the table that
// should be 0.9375rem sans inherits the serif measure around it, and the text
// colours fall back to transparent-ish defaults. A screenshot taken that way
// would be a picture of a missing stylesheet, not of this part.
import '../src/theme.css'
import '../src/app.css'
import '../src/experimental/renderable.css'
import '../src/quiet2/quiet2.css'
// The Magnet card's own design language. `Magnet.tsx` is what loads it in the
// app, and this harness mounts `Summary` and `Inspection` directly, so without
// these every `mgd-` heading, row and quotation renders unstyled.
import '../src/quiet2/magnets/design.css'
import '../src/quiet2/magnets/magnet.css'

const mid = 'mag-part5fixture1'
const STANDING = 'ent-p5standingtop1'
const batchRef = 'adm-p5batch11111'
page.saw('part5-fixture@instance')
const state = new URLSearchParams(location.search).get('state') ?? 'synthesis'

const config = { id: mid, name: 'Space missions and astronomy', conversation: 'ent-p5conv1111111',
  sources: [{ kind: 'file', collection: 'col-astronomy' }],
  selection: { informationTypes: ['post', 'file'], dates: {} }, collection: { mode: 'manual' },
  synthesis: { mode: 'manual' }, notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' } }

/** One acquired row, byte for byte in `_entry_body`'s recorded shape. */
const row = (hex: string, headline: string, body: string, published: string, publisher: string) => {
  const id = `adm-${hex}`, digest = hex[0].repeat(64)
  const text = `${headline}\n\n https://example.org/${hex}\n\n${body}\n\n--\nPublished: ${published}\nPublisher: ${publisher}\n`
    .replace('\n https://', '\nhttps://')
  const end = new TextEncoder().encode(text).length
  return { kind: 'file', id, version: id, conversation: null, author: null, at: 1795600000, via: 'held-source',
    value: { ref: id, digest, collection: 'col-astronomy', path: `space-missions/${hex}`, text,
      offset: 0, end, size: end, acquired_at: 1795600000, shortened: false, omitted_bytes: 0,
      next_offset: null, citation: `${id}@${digest.slice(0, 12)}[0:${end}]` } }
}

const held = [
  row('aaa111111111', 'Roman Space Telescope passes its final thermal test - NASA',
    'The Roman Space Telescope completed thermal vacuum testing at Goddard this month, clearing the '
    + 'last environmental milestone before it ships to the launch site.\n\nIts coronagraph remains the '
    + 'instrument to watch: the Roman Space Telescope will survey the infrared sky far faster than Hubble can.',
    '2026-03-27T07:00:00+00:00', 'NASA'),
  row('bbb222222222', 'Europa Clipper adjusts its Mars gravity assist - NASA',
    'Europa Clipper fired its thrusters for 68 seconds to refine the Mars gravity assist that sends it '
    + 'outward. Europa Clipper arrives in the Jovian system in 2030.',
    '2025-11-02T09:30:00+00:00', 'NASA'),
  row('ccc333333333', 'Artemis Programme names the Artemis III landing site - Space',
    'The Artemis Programme narrowed the Artemis III candidate regions to a shortlist near the lunar '
    + 'south pole, where permanently shadowed craters sit beside ridges with near-continuous sunlight.',
    '2024-06-14T12:00:00+00:00', 'Space'),
  row('eee444444444', 'JUICE completes its lunar-Earth flyby - ESA',
    'ESA reports that JUICE threaded the first lunar-Earth gravity assist ever attempted, trimming years '
    + 'from its cruise to Jupiter.',
    '2024-08-20T16:45:00+00:00', 'ESA'),
]

const provenance = { grounded_in: 'collection', explored_outside: false, outside_authorized: [], outside_reads: [] }
const WRITTEN_BY = 'Written by Mentis from this Magnet’s collected records alone.'

/** THE PYTHON SYNTHESIS, in the shape Part 2 writes it: one statement per
 *  recorded line, each naming the rows it was written from. */
const SYNTHESIS = [
  { text: 'This Magnet’s collected material speaks mainly about Roman Space Telescope, Europa Clipper and Artemis Programme.',
    cites: ['adm-aaa111111111', 'adm-bbb222222222', 'adm-ccc333333333'] },
  { text: 'Most recently, from the web search (2026-03-27) · Roman Space Telescope passes its final thermal test: “The Roman Space Telescope completed thermal vacuum testing at Goddard this month, clearing the last environmental milestone before it ships to the launch site.”',
    cites: ['adm-aaa111111111'] },
  { text: 'From the web search: most recently “JUICE completes its lunar-Earth flyby - ESA”',
    cites: ['adm-eee444444444'] },
  { text: 'The material it holds was written between 2024-06-14 and 2026-03-27.',
    cites: ['adm-ccc333333333'] },
  { text: 'This Magnet has gathered 4 records from 1 source, collected 26 November 2026.',
    cites: ['adm-aaa111111111', 'adm-bbb222222222', 'adm-ccc333333333'] },
]

/** AN ANSWER WRITTEN AS A DOCUMENT -- the presentation a dispatched run
 *  produces (Part 3), rendered here by `Prose` over a recorded answer of that
 *  shape so the presentation can be judged before that path is wired. */
const BRIEFING = [
  '## What launched, and what was found',
  '',
  'Four collected records describe one season of flight hardware clearing its last tests. The',
  '**Roman Space Telescope** finished thermal vacuum testing at Goddard and is cleared to ship;',
  '**Europa Clipper** trimmed its Mars gravity assist and still arrives at Jupiter in 2030; and',
  '**JUICE** completed the first lunar-Earth gravity assist ever attempted.',
  '',
  'The **Artemis Programme** is the outlier: its record is a decision rather than a test, narrowing',
  'the Artemis III shortlist to the lunar south pole, where shadowed craters sit beside',
  'near-continuously lit ridges.',
  '',
  '| Published | Mission | What the record says |',
  '|---|---|---|',
  '| 2026-03-27 | Roman Space Telescope | Thermal vacuum testing complete; cleared to ship |',
  '| 2025-11-02 | Europa Clipper | Gravity assist refined; Jupiter arrival 2030 |',
  '| 2024-08-20 | JUICE | First lunar-Earth assist flown |',
  '| 2024-06-14 | Artemis Programme | Artemis III shortlist narrowed to the south pole |',
  '',
  'What the collection does **not** hold: any record of a launch actually occurring, and nothing at',
  'all between November 2025 and March 2026.',
].join('\n')

/** THE SAME BRIEFING, RECORDED THE WAY A TABLE, A LIST AND A PARAGRAPH CAN
 *  ACTUALLY ARRIVE: as several recorded entries, each with its own citation,
 *  rather than the whole document in one entry. The fixture the independent
 *  review found (`02-summary-briefing.png`) could not show per-statement
 *  citation mapping or Markdown spanning entries, because it put the whole
 *  document in one `lines` entry. This one cannot make that mistake: the
 *  heading, the paragraph (cut off mid-sentence, continued in the next
 *  entry), the table (one entry per row) and the ordered list (one entry per
 *  item) are each split exactly where review `ent-19c3c55af28c` asked for --
 *  and each entry still names only the record it was actually written from. */
const BRIEFING_MULTI: { text: string; cites: string[] }[] = [
  { text: '## What launched, and what was found', cites: [] },
  { text: 'The **Roman Space Telescope** finished thermal vacuum testing at Goddard and is cleared to ship, and',
    cites: ['adm-aaa111111111'] },
  { text: '**Europa Clipper** trimmed its Mars gravity assist and still arrives at Jupiter in 2030.',
    cites: ['adm-bbb222222222'] },
  { text: '| Published | Mission | What the record says |\n|---|---|---|\n| 2026-03-27 | Roman Space Telescope | Thermal vacuum testing complete |',
    cites: ['adm-aaa111111111'] },
  { text: '| 2025-11-02 | Europa Clipper | Gravity assist refined; Jupiter arrival 2030 |', cites: ['adm-bbb222222222'] },
  { text: '| 2024-08-20 | JUICE | First lunar-Earth assist flown |', cites: ['adm-eee444444444'] },
  { text: '1. Thermal vacuum testing completed for Roman Space Telescope.', cites: ['adm-aaa111111111'] },
  { text: '2. Mars gravity assist refined for Europa Clipper.', cites: ['adm-bbb222222222'] },
  { text: '3. First lunar-Earth gravity assist flown for JUICE.', cites: ['adm-eee444444444'] },
]

const answered = (seq: number, post: string, lines: { text: string; cites: string[] }[]) => ({
  seq, post, event: 'answered', perspective: STANDING,
  snapshot: { ref: `adm-p5snap${seq}11111`, digest: 'b'.repeat(64), size: 512, media_type: 'application/json' },
  data: { text: lines.map((l) => l.text).join('\n'), lines, answer: { ref: `adm-p5pkg${seq}111111` },
    written_by: WRITTEN_BY, provenance, method: 'mentis.magnet.synthesis/1',
    basis: { batch: batchRef, rows: held.length, new_count: 0 } },
})

const standingDetail = { magnet: mid, perspective: STANDING, name: 'What this Magnet has gathered',
  retired: false, question: { ref: 'adm-p5standq11111', digest: 'c'.repeat(64), size: 64, media_type: 'application/json' },
  current_question: { text: 'What is the state of what this Magnet has gathered?', revision: 'adm-p5standq11111' },
  events: 1, selected: STANDING, standing: STANDING }

const events = state === 'unanswered' ? []
  : state === 'briefing' ? [answered(1, 'ent-p5event111111', [{ text: BRIEFING, cites: ['adm-aaa111111111', 'adm-bbb222222222'] }])]
    : state === 'briefing-multi' ? [answered(1, 'ent-p5event111111', BRIEFING_MULTI)]
      : [answered(1, 'ent-p5event111111', SYNTHESIS)]

const activation = { post: 'ent-p5act1111111',
  artifact: { ref: batchRef, digest: 'd'.repeat(64), size: 4096, media_type: 'application/json' },
  at: 1795700000, state: 'complete' }
const collectionBody = { config, activation,
  page: { sources: [{ key: 'file:col-astronomy:', source: config.sources[0], status: 'ok', results: held }] } }

const response = (v: unknown) => new Response(JSON.stringify({ brain: 'part5-fixture@instance', magnet: mid, ...(v as object) }), { status: 200 })
const realFetch = window.fetch
window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const path = new URL(String(input), location.href).pathname
  if (path.endsWith('/needs-you/brain')) return response({ brain: { corpus_id: 'part5-fixture', instance: 'instance' } })
  if (path.includes('/perspectives')) {
    const tail = path.split('/perspectives')[1]
    const [topic, verb] = tail.slice(1).split('/')
    // An answer is never WRITTEN by a screenshot: the fixture holds what is
    // already recorded, and an unanswered state stays unanswered.
    if (init.method === 'POST') return new Response(JSON.stringify({ error: 'nothing-new', code: 'nothing-new' }), { status: 409 })
    if (!tail) return response({ perspectives: [standingDetail], selected: STANDING, standing: STANDING, next: null, grounded_answers: true })
    if (verb === 'history') return response({ perspective: topic, events, next: null, through: events.length })
    return response(standingDetail)
  }
  if (path.includes('/collection')) return response(collectionBody)
  return realFetch(input, init)
}

const resource = createMagnetResource({ id: `qm-${mid}`, brainKey: 'http://fixture||part5-fixture',
  saved: { id: mid, name: 'Space missions and astronomy', config: config as never },
  get: async (path: string) => {
    if (path.startsWith('/fluid/api/participants')) return { status: 200, body: { participants: [], me: 'ent-p5owner11111' } }
    return { status: 200, body: { magnet: mid, ...collectionBody } }
  } })

function App() {
  // The frame the app puts this view in: `Magnet.tsx` renders the view inside
  // `.q2-magnet-view.mgd-body` within `.q2-magnet-card`, which is where the
  // card's own type, ink and rules come from.
  return <div className="q2">
    <div className="q2-magnet-card">
      <header><h2>Space missions and astronomy — what launched, what was found</h2></header>
      <div className="q2-magnet-view mgd-body">
        {state === 'inspect'
          ? <Inspection resource={resource} refId="adm-aaa111111111" source={() => {}} />
          : <Summary resource={resource} onPost={() => {}} />}
      </div>
    </div>
  </div>
}

void resource.read().finally(() => createRoot(document.getElementById('root')!).render(<App />))
