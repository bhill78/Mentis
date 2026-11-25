/** The Summary view: the first tab and the default.
 *
 *  **Retained collection only** (plan §5-H3-1, B5). Every line here is derived
 *  from `resource.snapshot()` -- the immutable batch `state.ts` has already read
 *  and `collectionRows` has already verified -- and from the saved definition.
 *  This view issues no request of its own while it renders, and in particular
 *  never calls `GET /fluid/api/magnets/<id>/read` in any mode: that route reads
 *  the Magnet's sources *live*, which this surface exists not to do
 *  (`state.ts:1`). Two things it does ask for, and only when the owner presses
 *  for them: the recorded questions of this Magnet, and one earlier **retained**
 *  batch to compare against. Neither is a live source; neither happens on its
 *  own.
 *
 *  **Nothing here is synthesis.** The written overview is counted and measured
 *  facts about the collection; the excerpts are the collected records' own words,
 *  word for word, each one linked to the record it came from; the offered
 *  questions are questions, marked as questions. No sentence characterises what
 *  the material means. The four kinds are kept apart on the screen and are
 *  labelled: collection facts, the records' own words, questions and
 *  hypotheses, and interpretations somebody recorded. Evidence-grounded
 *  answering stays refused server-side and its affordance is rendered disabled,
 *  carrying the refusal's own reason. */
import { useEffect, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import type { MagnetResource, MagnetSnapshot, SavedMagnet, SearchEntry, SearchSource } from './contract'
import type { MagnetSource } from '../../fluid/surface/magnet/types'
import Inspection, { capturedText, evidenceOrigin, retainedFiles, sourceLabel } from './Inspection'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import { goTab, inspect, place } from './places'
import { resultTitle } from './EvidenceViews'
import { collectionRows } from './collectionRows'
import { miniComposerDraft, saveMiniComposer } from './conversation'
import { setQuestionDraft, panelAt } from './panelDrafts'
import { perspectivesOf, PERSPECTIVE_BLOCK_REASON, type InquiryEvent, type Perspective } from './perspectives'
import './summary.css'

/** The reason comes from the gate itself, not from a sentence written here:
 *  `PERSPECTIVE_BLOCK_REASON` is the client's statement of the server's
 *  `grounded_answers: false` refusal (`perspectives.py` GROUNDED_ANSWERS_ENABLED,
 *  DISCLOSURE). See the Turn's discrepancy note: the server's own
 *  `grounded_answers`/`disclosure` fields are not kept in H5's `InquirySnapshot`,
 *  and Summary may not make a request to read them. */
export const GROUNDED_UNAVAILABLE = `Unavailable · ${PERSPECTIVE_BLOCK_REASON}`

/** What the written overview says about itself, so no reader has to guess
 *  whether an agent wrote it. */
export const EXTRACTIVE_LABEL = 'Counted from the collected records and quoted from them word for word. No agent read or summarised this collection.'
/** Per-record support and contradiction belong to grounded Perspective work,
 *  which is refused: say so rather than show an empty frame as if it worked. */
export const SUPPORT_UNRECORDED = 'No records are recorded as supporting or contradicting any of these: marking evidence for or against a question is part of grounded Perspective answering, which is unavailable.'
export const NO_COMPARISON = 'No comparison with an earlier collection. Nothing here claims anything changed.'
/** ANSWERING FROM THE COLLECTED RECORDS IS NOT OFFERED HERE, by any control.
 *  Supplying the retained batch to an agent to answer from is the retained-content
 *  path, which the revised boundary contract (adm-c5c73679ac1e §2) requires to
 *  refuse everywhere until configured-source read enforcement and session
 *  exposure are independently verified. So this view offers no press that
 *  attaches the collection or asks for an answer from it -- not for one record
 *  and not for the collection as a whole -- and says so where such an offer
 *  would otherwise sit. What stays is what is already true: counted and quoted
 *  facts above, and ordinary conversation that reads no collected material. */
export const COLLECTION_NOT_ANSWERABLE = 'Answering from the collected records is unavailable: configured-source access has to be enforced first. Ordinary conversation about this Magnet, its sources and your questions works now.'

const when = (at?: number | null) => typeof at === 'number' && Number.isFinite(at) ? new Date(at * 1000).toLocaleString() : null
const day = (at?: number | null) => typeof at === 'number' && Number.isFinite(at) ? new Date(at * 1000).toLocaleDateString() : null
const object = (v: unknown): Record<string, any> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, any> : {}

/** How many retained items in the batch shown were captured from each key. */
export function capturedCounts(s: MagnetSnapshot): Map<string, number> {
  const counts = new Map<string, number>()
  for (const r of s.results) {
    const key = (r as RouteResult & { capturedSourceKey?: string }).capturedSourceKey
    if (typeof key === 'string' && key) counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return counts
}

/** A configured source's captured key, in `collectionRows`'s own vocabulary.
 *  Only Conversation and held-file sources can be captured by this candidate
 *  (`read.ts unsupportedMagnet`), so any other kind has no key and no items. */
export function configuredKey(source: MagnetSource): string | null {
  if (source.kind === 'conversation') return `conversation:${source.conversation}`
  if (source.kind === 'file') return `file:${source.collection}:${source.path ?? ''}`
  return null
}

/** The factual lines, in the order §5-H3-1 names them. Returned as sentences so
 *  that `summarySource` searches exactly what the reader can see. These are the
 *  collection's facts and nothing else; what the records say is `collectedText`
 *  and `collectedExcerpts`, and what changed is `compareCollections`. */
export function summaryFacts(saved: SavedMagnet, s: MagnetSnapshot): string[] {
  const posts = s.results.filter((r) => r.kind === 'post').length
  const files = retainedFiles(s.results).length
  const sources = saved.config?.sources ?? []
  const selection = saved.config?.selection
  const counts = capturedCounts(s)
  const read = s.activation !== undefined
  const lines: string[] = []
  if (!read) lines.push('This collection has not been read yet. Opening never collects and never reads a live source.')
  else if (!s.activation) lines.push('Nothing collected yet. Press Collect now; opening never collects automatically.')
  else lines.push(`${posts} collected posts and ${files} collected files in the collection shown.`)
  lines.push(`${sources.length} configured ${sources.length === 1 ? 'source' : 'sources'}: ${sources.map((source) => {
    const key = configuredKey(source)
    if (!key) return `a ${source.kind} source, which this candidate does not capture`
    const got = counts.get(key)
    return `${sourceLabel(key)} (${got ? `${got} collected ${got === 1 ? 'item' : 'items'}` : 'nothing collected from it here'})`
  }).join('; ') || 'none readable'}.`)
  for (const key of counts.keys()) {
    if (!sources.some((source) => configuredKey(source) === key))
      lines.push(`This collection also holds ${counts.get(key)} items captured from ${sourceLabel(key)}, which the current configuration no longer names. The captured copy is unchanged.`)
  }
  const collected = when(s.activation?.at)
  if (collected) lines.push(`Collected ${collected} · recorded state ${s.activation?.state ?? 'unstated'}.`)
  if (s.status) lines.push(s.status === 'ok' ? 'Every captured source reported its whole selected scope.'
    : `This collection is ${s.status}${s.reason ? `. Stated by its captured sources: ${s.reason}` : '. No reason was stated.'}`)
  if (s.error) lines.push(s.error)
  lines.push(`Showing ${s.batchSelection ? 'an earlier collection you chose' : 'the latest collection'}.`)
  lines.push(`Selected Conversation types: ${(selection?.informationTypes?.length ? selection.informationTypes : ['post', 'file', 'image']).join(', ')}.`)
  if (selection?.dates) lines.push(`Selected dates: ${selection.dates.after || 'any start'} to ${selection.dates.before || 'any end'}.`)
  if (saved.config && ['criteria', 'phrases', 'topics', 'filters'].some((k) => !!saved.config?.selection[k as keyof typeof saved.config.selection]))
    lines.push('Criteria, phrases, topics and filters are kept with the Magnet; this source does not apply them.')
  lines.push(s.previousOpen ? 'Activity is compared with this tab’s last-open time only; there is no shared read state.' : 'No last-open baseline in this tab yet.')
  return lines
}

/* ---------------------------------------------------------------------------
   WHAT THE COLLECTION ACTUALLY HOLDS, written out.

   Everything below is either counted (words, items, dates) or quoted (the
   records' own characters). Nothing is characterised: there is no sentence of
   the form "this collection is about X", because deciding that is reading, and
   no agent has read this material. */

/** Every captured word of the batch, joined. Held-file text and post text both,
 *  so a count over it is a count over what was actually retained. */
export function collectedText(results: RouteResult[]): string {
  return results.map((r) => {
    const v = object(r.value)
    return typeof v.text === 'string' && (r as RouteResult & { via?: string }).via === 'held-source' ? v.text : capturedText(r)
  }).filter(Boolean).join('\n\n')
}

/** Words that carry no subject on their own; counting them says nothing. */
const COMMON = new Set(('the and that this with have from were was for are not but all any can has had had its into than then '
  + 'they them their there these those which while would should could when what where who whom why how about above after again '
  + 'against because been before being below between both during each few more most other over same some such only own too very '
  + 'will just dont should now also upon under here your yours ours mine theirs does done each either neither within without '
  + 'through across among per via etc said says say like make made take taken give given well back much many one two three').split(' '))

export interface CountedWord { word: string; count: number }
/** The words used most in the collected text, **counted**. A count is a fact
 *  about the text; it is not a theme, and the view says so where it shows it. */
export function frequentWords(results: RouteResult[], limit = 6): CountedWord[] {
  const counts = new Map<string, number>()
  for (const raw of collectedText(results).toLowerCase().split(/[^\p{L}\p{N}'’-]+/u)) {
    const word = raw.replace(/^['’-]+|['’-]+$/g, '')
    if (word.length < 4 || COMMON.has(word) || /^\d/.test(word)) continue
    if (/^(ent|adm|mag|opr|def)-/.test(word)) continue       // references are identity, not subject
    counts.set(word, (counts.get(word) ?? 0) + 1)
  }
  return [...counts.entries()].filter(([, n]) => n > 1).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit).map(([word, count]) => ({ word, count }))
}

/** When the collected material itself was written, from what was captured with
 *  it -- not when the batch was collected, which is a different fact. */
export function collectedSpan(results: RouteResult[]): { first: number; last: number } | null {
  const times = results.map((r) => r.at).filter((at): at is number => typeof at === 'number' && Number.isFinite(at))
  return times.length ? { first: Math.min(...times), last: Math.max(...times) } : null
}

export interface Excerpt { id: string; title: string; origin: string; text: string }
/** The records' own opening words, quoted. The one honest kind of "summary" a
 *  surface that has read nothing can offer: it shows the material instead of
 *  describing it, and every excerpt opens the record it came from. */
export function collectedExcerpts(results: RouteResult[], limit = 4, length = 220): Excerpt[] {
  return results.map((r) => ({ id: r.id, title: resultTitle(r), origin: evidenceOrigin(r),
    text: (capturedText(r) || (typeof object(r.value).text === 'string' ? object(r.value).text : '')).replace(/\s+/g, ' ').trim().slice(0, length) }))
    .filter((e) => !!e.text).slice(0, limit)
}

/** THE WRITTEN OVERVIEW. Sentences, not a counts table -- and every one of them
 *  is a measurement of the collection or of its captured text. */
export function collectionOverview(saved: SavedMagnet, s: MagnetSnapshot): string[] {
  if (s.activation === undefined || !s.activation) return []
  const posts = s.results.filter((r) => r.kind === 'post').length
  const files = retainedFiles(s.results).length
  const text = collectedText(s.results)
  const words = text.split(/\s+/).filter(Boolean).length
  const span = collectedSpan(s.results)
  const counts = capturedCounts(s)
  const named = [...counts.entries()].map(([key, n]) => `${sourceLabel(key)} (${n})`)
  const lines: string[] = []
  const held = [posts ? `${posts} collected ${posts === 1 ? 'post' : 'posts'}` : '', files ? `${files} collected ${files === 1 ? 'file' : 'files'}` : '']
    .filter(Boolean).join(' and ') || 'nothing'
  lines.push(`This Magnet holds ${held}, collected ${when(s.activation.at)}.`)
  if (named.length) lines.push(`They came from ${named.join(', ')}.`)
  if (span) lines.push(day(span.first) === day(span.last)
    ? `The collected material is all from ${day(span.first)}.`
    : `The collected material was written between ${day(span.first)} and ${day(span.last)}.`)
  if (words) lines.push(`Its collected text runs to about ${words.toLocaleString()} ${words === 1 ? 'word' : 'words'}.`)
  const frequent = frequentWords(s.results)
  if (frequent.length) lines.push(`Most used words, counted: ${frequent.map((w) => `${w.word} (${w.count})`).join(', ')}.`)
  if (s.status && s.status !== 'ok') lines.push(`Not every source reported its whole scope, so this is what was collected, not everything that exists${s.reason ? `: ${s.reason}` : '.'}`)
  const sources = saved.config?.sources ?? []
  const uncaptured = sources.filter((source) => { const key = configuredKey(source); return !key || !counts.get(key) })
  if (uncaptured.length) lines.push(`${uncaptured.length} configured ${uncaptured.length === 1 ? 'source' : 'sources'} contributed nothing to this collection.`)
  return lines
}

/** QUESTIONS THE COLLECTION MAKES ASKABLE. Each is a question built out of
 *  facts already on this screen -- a source that was collected, a word that was
 *  counted, two batches that exist. None of them is an answer, a finding or a
 *  claim about the material, and the view labels them as questions. */
export function offeredQuestions(s: MagnetSnapshot, earlier = false): string[] {
  const out: string[] = []
  if (s.activation === undefined || !s.activation) {
    out.push('How do I configure this Magnet?')
    out.push('What can this Magnet collect at the moment?')
    out.push('What should I collect first for this idea?')
    return out
  }
  const counts = capturedCounts(s)
  const [first] = [...counts.keys()]
  for (const w of frequentWords(s.results, 2)) out.push(`What do the collected records say about ${w.word}?`)
  if (first) out.push(`What is in the material collected from ${sourceLabel(first)}?`)
  if (earlier) out.push('What is in this collection that was not in the previous one?')
  if (counts.size > 1) out.push('Where do the collected sources disagree with each other?')
  out.push('What is missing from this collection that I would need?')
  return out.slice(0, 5)
}

/* ---------------------------------------------------------------------------
   CHANGE, ONLY BETWEEN TWO COMPARABLE RETAINED BATCHES.

   Two batches are comparable when they captured the same sources. Two batches
   of different source sets differ because the Magnet was reconfigured, and
   calling that a change in the material would be a false statement about the
   collection -- so it is refused by name instead. */

/** One retained item's identity across batches, and the version of it that was
 *  captured. A post keeps its id and changes version; a held file's range is
 *  identified by its source and compared by digest and length, because
 *  recollecting a changed file produces a new Admission reference. */
export function itemIdentity(r: RouteResult): { id: string; version: string } {
  const v = object(r.value)
  if ((r as RouteResult & { via?: string }).via === 'held-source')
    return { id: `file:${v.collection}:${v.path ?? ''}`, version: `${v.digest}:${v.end}` }
  return { id: `post:${r.id}`, version: String(r.version ?? r.id) }
}

export const capturedKeys = (results: RouteResult[]): string[] =>
  [...new Set(results.map((r) => (r as RouteResult & { capturedSourceKey?: string }).capturedSourceKey ?? ''))].filter(Boolean).sort()

export interface Comparison {
  comparable: boolean
  reason?: string
  added: Excerpt[]
  gone: number
  changed: number
  unchanged: number
}

/** What is actually different between the batch shown and an earlier retained
 *  one. Pure: it reads two decoded result lists and nothing else. */
export function compareCollections(current: RouteResult[], previous: RouteResult[]): Comparison {
  const empty = { added: [], gone: 0, changed: 0, unchanged: 0 }
  const here = capturedKeys(current), there = capturedKeys(previous)
  if (here.join('|') !== there.join('|'))
    return { comparable: false, ...empty,
      reason: 'These two collections captured different sources, so they are not comparable. Nothing is claimed about what changed.' }
  const before = new Map(previous.map((r) => { const i = itemIdentity(r); return [i.id, i.version] }))
  const now = new Map(current.map((r) => { const i = itemIdentity(r); return [i.id, i.version] }))
  let changed = 0, unchanged = 0
  const added: RouteResult[] = []
  for (const r of current) {
    const i = itemIdentity(r)
    if (!before.has(i.id)) { added.push(r); continue }
    if (before.get(i.id) === i.version) unchanged++
    else changed++
  }
  const gone = [...before.keys()].filter((id) => !now.has(id)).length
  return { comparable: true, added: collectedExcerpts(added, 3), gone, changed, unchanged }
}

/** The one sentence a comparison is worth, in plain words. */
export function comparisonWords(c: Comparison): string {
  if (!c.comparable) return c.reason ?? NO_COMPARISON
  const bits = [
    c.added.length ? `${c.added.length} new ${c.added.length === 1 ? 'record' : 'records'}` : '',
    c.changed ? `${c.changed} changed since then` : '',
    c.gone ? `${c.gone} no longer collected` : '',
  ].filter(Boolean)
  return bits.length
    ? `Compared with the previous collection: ${bits.join(', ')}; ${c.unchanged} unchanged.`
    : `Nothing changed between the previous collection and this one: all ${c.unchanged} records are the same captured versions.`
}

/** The earlier retained batch to compare against, and its decoded contents.
 *  A retained read of an immutable, already-recorded batch -- never a source
 *  read -- and it happens only because the owner pressed for it. */
export async function readEarlierBatch(resource: MagnetResource, shown: string, signal?: AbortSignal):
  Promise<{ at: number; results: RouteResult[] } | { bound: string }> {
  const id = encodeURIComponent(resource.saved.id)
  const ask = async (path: string) => {
    const r = await fetch(path, { headers: CLIENT_HEADERS, signal, cache: 'no-store' })
    const v = await r.json().catch(() => null)
    if (!r.ok || !v || v.error) throw new Error(v?.error ?? `This Magnet’s collection history is unavailable (${r.status}).`)
    if (v.magnet !== resource.saved.id) throw new Error('That answer was for another Magnet. Nothing was compared.')
    return v
  }
  const list = await ask(`/fluid/api/magnets/${id}/collection/history?limit=20`)
  if (!Array.isArray(list.batches)) throw new Error('The collection history could not be read.')
  const at = list.batches.findIndex((b: any) => object(b.artifact).ref === shown)
  const earlier = at < 0 ? null : list.batches[at + 1]
  if (!earlier) return { bound: 'No earlier collection to compare with: this is the first one.' }
  const ref = object(earlier.artifact).ref, digest = object(earlier.artifact).digest
  if (typeof ref !== 'string' || typeof digest !== 'string') throw new Error('An earlier collection lacks its recorded reference.')
  const body = await ask(`/fluid/api/magnets/${id}/collection?${new URLSearchParams({ batch: ref, digest })}`)
  if (object(object(body.activation).artifact).ref !== ref || object(object(body.activation).artifact).digest !== digest)
    throw new Error('That read did not return the collection that was asked for. Nothing was substituted.')
  return { at: object(body.activation).at, results: collectionRows(body.page).results }
}

/** The Summary's own facts, written overview and quoted words, as one searchable
 *  entry. Already complete: all of it is derived from the batch in hand, so this
 *  source owes no `complete()` (§4). */
export function summarySource(resource: MagnetResource): SearchSource {
  return {
    entries(): SearchEntry[] {
      const s = resource.snapshot()
      return [{ key: 'summary', kind: 'Summary', title: 'Collection overview',
        text: [...collectionOverview(resource.saved, s), ...collectedExcerpts(s.results, 8).map((e) => `${e.title}: ${e.text}`),
          ...summaryFacts(resource.saved, s)].join(' '),
        open: () => goTab(resource, 'Summary') }]
    },
  }
}

/** The recorded questions and interpretations this Magnet holds, told apart.
 *  `created`, `question` and `branch` events are wordings of a question;
 *  `challenged` is somebody's recorded contradiction of one. Nothing here is
 *  promoted to a finding, and the attribution is the event's own. */
export function recordedChallenges(events: InquiryEvent[]): InquiryEvent[] {
  return events.filter((e) => e.event === 'challenged' || e.event === 'challenge')
}

/* ---------------------------------------------------------------------------
   THE FOUR THINGS A PRESS HERE DOES, as functions, so each can be driven and
   checked without a browser. The view holds only which of them is in flight. */

/** An offered question becomes a Perspective's draft question, where one press
 *  creates it with its name taken from the question. Nothing is written to the
 *  record here, and no other draft slot is touched (`panelDrafts.ts`). */
export function exploreQuestion(resource: MagnetResource, question: string): void {
  setQuestionDraft(panelAt(resource), question)
  goTab(resource, 'Perspectives')
}

/** With nothing collected, a starter question is an ordinary message. The
 *  owner's own unsent words are never overwritten: that is what it returns. */
export function askOrdinaryQuestion(resource: MagnetResource, question: string): string {
  const draft = miniComposerDraft(resource)
  if (draft.text.trim()) return 'The Composer already holds words of yours. Keep or clear them first.'
  saveMiniComposer(resource, { ...draft, text: question })
  goTab(resource, 'Conversation')
  return ''
}

export interface ComparisonResult { words: string; added: Excerpt[]; at?: number; comparable: boolean }
/** The whole comparison act: find the batch before the one shown, read it, and
 *  compare. Refuses by name rather than guessing when there is nothing
 *  comparable to compare with. */
export async function compareWithPrevious(resource: MagnetResource, signal?: AbortSignal):
  Promise<ComparisonResult | { bound: string }> {
  const s = resource.snapshot()
  const batch = s.activation?.artifact.ref
  if (!batch) return { bound: NO_COMPARISON }
  const got = await readEarlierBatch(resource, batch, signal)
  if ('bound' in got) return got
  const c = compareCollections(s.results, got.results)
  return { words: comparisonWords(c), added: c.added, at: got.at, comparable: c.comparable }
}

function Questions({ resource, rows, events, loading, error, onLoad, read }: {
  resource: MagnetResource; rows: Perspective[]; events: InquiryEvent[]
  loading: boolean; error?: string; onLoad(): void; read: boolean
}) {
  const challenges = recordedChallenges(events)
  return <section className="q2-magnet-understanding" aria-label="Recorded questions and interpretations">
    <h4>Questions and interpretations already recorded</h4>
    {!read
      ? <><p className="q2-magnet-muted">Not read yet. Nothing is read from the record until you ask for it.</p>
        <button type="button" className="q2-magnet-link" disabled={loading} onClick={onLoad}>Show recorded questions</button></>
      : rows.length
        ? <ul className="q2-magnet-items">{rows.map((p) => <li key={p.perspective}>
          <strong>{p.name}</strong>{p.retired ? <small className="q2-magnet-muted"> · retired</small> : null}
          {p.current_question && <p className="q2-magnet-quote">“{p.current_question.text}”</p>}
          <small className="q2-magnet-muted">Question · {p.perspective}{p.current_question ? ` · revision ${p.current_question.revision}` : ''}</small>
        </li>)}</ul>
        : <p className="q2-magnet-muted">No questions recorded for this Magnet yet.</p>}
    {read && !!challenges.length && <>
      <h5>Recorded challenges</h5>
      <ul className="q2-magnet-items">{challenges.map((e) => <li key={e.post}>
        <p className="q2-magnet-quote">“{typeof e.data?.text === 'string' ? e.data.text : 'A challenge was recorded with no wording.'}”</p>
        <small className="q2-magnet-muted">Recorded challenge · {e.post}</small>
      </li>)}</ul>
    </>}
    {read && <p className="q2-magnet-muted">{SUPPORT_UNRECORDED}</p>}
    {error && <p className="q2-magnet-muted" role="status">{error}</p>}
    <button type="button" className="q2-magnet-link" onClick={() => goTab(resource, 'Perspectives')}>Work on questions</button>
  </section>
}

export default function Summary({ resource, onPost }: { resource: MagnetResource; onPost(result: RouteResult): void }) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const inquiries = perspectivesOf(resource)
  const lens = useSyncExternalStore(inquiries.subscribe, inquiries.snapshot, inquiries.snapshot)
  const here = place(s)
  const posts = s.results.filter((r) => r.kind === 'post')
  const files = retainedFiles(s.results)
  const read = s.activation !== undefined
  const items = [...posts, ...files]
  const batch = s.activation?.artifact.ref
  const [comparison, setComparison] = useState<ComparisonResult | null>(null)
  const [comparing, setComparing] = useState(false)
  const [message, setMessage] = useState('')
  const [loadingQuestions, setLoadingQuestions] = useState(false)
  /** Whether the recorded questions have been read at all. Rows that arrived
   *  because the Perspectives view read them count; so does this view asking. */
  const [askedForQuestions, setAskedForQuestions] = useState(false)
  /** A batch change invalidates a comparison taken against the previous one. */
  useEffect(() => { setComparison(null); setMessage('') }, [batch])

  const overview = collectionOverview(resource.saved, s)
  const excerpts = collectedExcerpts(s.results)
  const questions = offeredQuestions(s, !!comparison)
  // Real retained items, offered as the Summary's supports.
  const supports = items.slice(0, 6)

  const askOrdinary = (question: string) => setMessage(askOrdinaryQuestion(resource, question))
  const compare = () => {
    if (!batch || comparing) return
    const ctl = new AbortController()
    setComparing(true); setMessage('')
    void compareWithPrevious(resource, ctl.signal).then((got) => {
      if ('bound' in got) { setMessage(got.bound); return }
      setComparison(got)
      if (!got.comparable) setMessage(got.words)
    }).catch((e: Error) => setMessage(`No comparison was made: ${e.message}`)).finally(() => setComparing(false))
  }
  const loadQuestions = () => {
    if (loadingQuestions) return
    setLoadingQuestions(true); setAskedForQuestions(true)
    void inquiries.read().finally(() => setLoadingQuestions(false))
  }

  return <section className="q2-magnet-summary" id="q2-magnet-summary">
    <div className="q2-magnet-section-title">
      <h3 id="summary-title" tabIndex={-1}>Summary</h3>
      <span className="q2-magnet-count">{read ? `${posts.length} posts · ${files.length} files` : 'not read yet'}</span>
    </div>
    {s.loading && <p className="q2-magnet-muted" role="status">Reading this collection…</p>}
    {read && !s.activation
      ? <div className="q2-magnet-collection-empty">
          <p>No collected information yet. Conversation is still available.</p>
          <p className="q2-magnet-muted">Choose sources in settings, or press Collect now. Opening never collects.</p>
          <h4>A place to start</h4>
          <ul className="q2-magnet-questions">{questions.map((q) => <li key={q}>
            <button type="button" className="q2-magnet-question" onClick={() => askOrdinary(q)}>{q}</button>
          </li>)}</ul>
          <p className="q2-magnet-muted">These go to the Composer as ordinary questions. Ordinary help works before anything is collected.</p>
        </div>
      : <>
        {/* Before the one retained read answers there is nothing to say about
            the collection, so nothing below is claimed: the facts line says it
            has not been read, and that is the whole of it. */}
        {!!s.activation && <>
        <div className="q2-magnet-written">
          {overview.map((line, i) => <p key={i}>{line}</p>)}
          {!!overview.length && <p className="q2-magnet-muted">{EXTRACTIVE_LABEL}</p>}
        </div>

        {!!excerpts.length && <section className="q2-magnet-understanding" aria-label="In the collected records’ own words">
          <h4>In the records’ own words</h4>
          <ul className="q2-magnet-items">{excerpts.map((e) => <li key={e.id}>
            <button type="button" className="q2-magnet-quote-row" id={`excerpt-${e.id}`} aria-expanded={here.inspected === e.id}
              onClick={() => inspect(resource, e.id, `excerpt-${e.id}`)}>
              <span className="q2-magnet-quote">“{e.text}{e.text.length >= 220 ? '…' : ''}”</span>
              <small className="q2-magnet-muted">{e.title} · {e.origin}</small>
            </button>
          </li>)}</ul>
          <p className="q2-magnet-muted">Quoted exactly as collected, each one opening the record it came from.</p>
        </section>}

        <section className="q2-magnet-understanding" aria-label="Changes since the previous collection">
          <h4>What changed</h4>
          {comparison
            ? <><p>{comparison.words}</p>
              {!!comparison.added.length && <ul className="q2-magnet-items">{comparison.added.map((e) => <li key={e.id}>
                <button type="button" className="q2-magnet-link" onClick={() => inspect(resource, e.id, `excerpt-${e.id}`)}>{e.title}</button>
                <p className="q2-magnet-quote">“{e.text}”</p>
              </li>)}</ul>}
              <p className="q2-magnet-muted">Compared against the collection from {when(comparison.at) ?? 'earlier'}. Both are captured copies; neither source was read again.</p></>
            : <><p className="q2-magnet-muted">{NO_COMPARISON}</p>
              <button type="button" className="q2-magnet-link" disabled={comparing || !batch} onClick={compare}>
                {comparing ? 'Reading the previous collection…' : 'Compare with the previous collection'}</button></>}
        </section>

        <section className="q2-magnet-understanding" aria-label="Questions to explore">
          <h4>Questions you could explore</h4>
          <p className="q2-magnet-muted">Questions, not findings: each one is built from what was counted above and nothing has answered any of them.</p>
          <ul className="q2-magnet-questions">{questions.map((q) => <li key={q}>
            <button type="button" className="q2-magnet-question" onClick={() => exploreQuestion(resource, q)}>{q}</button>
          </li>)}</ul>
        </section>

        <Questions resource={resource} rows={lens.rows} events={lens.events} loading={loadingQuestions || lens.loading}
          error={lens.error} onLoad={loadQuestions} read={askedForQuestions || !!lens.rows.length} />

        {/* Where the whole-collection discussion offer used to be. It is a
            statement, not a control: there is nothing to press that would
            supply the collection to an agent. */}
        {batch && <p className="q2-magnet-muted">{COLLECTION_NOT_ANSWERABLE}</p>}
        </>}

        <details className="q2-magnet-provenance" open={here.history}>
          <summary><span className="q2-magnet-eyebrow">Collection overview · facts only</span></summary>
          <div className="q2-magnet-facts">{summaryFacts(resource.saved, s).map((line, i) => <p key={i}>{line}</p>)}</div>
          {(items.length > 0 || batch) && <div className="q2-magnet-support">
            {batch && <button type="button" className="q2-magnet-link" id={`support-${batch}`} aria-expanded={here.inspected === batch}
              onClick={() => inspect(resource, batch, `support-${batch}`)}>View collection record ↗</button>}
            {supports.map((r) => <button type="button" key={`${r.kind}:${r.id}`} className="q2-magnet-link" id={`support-${r.id}`} aria-expanded={here.inspected === r.id}
              onClick={() => inspect(resource, r.id, `support-${r.id}`)}>View {resultTitle(r)} ↗</button>)}
            {items.length > supports.length && <span className="q2-magnet-muted">{items.length - supports.length} more collected records are in the collection.</span>}
          </div>}
        </details>
      </>}
    {message && <p className="q2-magnet-muted" role="status">{message}</p>}
    {/* Inline, inside the Summary section: never a separate screen. */}
    {here.inspected && <Inspection resource={resource} refId={here.inspected} source={onPost} />}
    <p className="q2-magnet-dependency">Sample records · not agent analysis or synthesis.</p>
    <div className="q2-magnet-grounding">
      <button type="button" className="q2-magnet-secondary" disabled aria-describedby="grounded-status">Synthesize from evidence</button>
      <span id="grounded-status" className="q2-magnet-muted">{GROUNDED_UNAVAILABLE}</span>
    </div>
  </section>
}
