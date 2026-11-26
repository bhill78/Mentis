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
 *  **THE LEAD IS AN ANSWER NOW** (plan §3 Part F). What this view opens with is
 *  the current answer of this Magnet's standing Perspective -- "What is the
 *  state of what this Magnet has gathered?" -- written by Mentis from the
 *  collected rows and recorded against that question, with "what changed" being
 *  the difference between it and the answer it superseded. It is one mechanism
 *  with Perspectives, not a second one: the same `answered` events, the same
 *  history, the same provenance.
 *
 *  The counted and measured facts STAY, as the owner asked, as secondary
 *  detail behind the disclosure that already carried them: they are honest and
 *  the counts remain available. The excerpts are still the records' own words.
 *  What went is the claim that answering from the collected records is
 *  unavailable, and the permanently disabled press that said so: the server's
 *  gate is open (Part A, `GROUNDED_ANSWERS_ENABLED`), so a Summary that still
 *  said it was shut would be the interface claiming something untrue. Every
 *  answer shown here states what it was grounded in, and an answer that
 *  explored outside the collection is rendered as a different thing. */
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import type { MagnetResource, MagnetSnapshot, SavedMagnet, SearchEntry, SearchSource } from './contract'
import type { MagnetSource } from '../../fluid/surface/magnet/types'
import Inspection, { capturedText, plainEvidenceOrigin, retainedFiles, sourceLabel } from './Inspection'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import { goTab, inspect, openOverlay, place } from './places'
import { resultTitle } from './EvidenceViews'
import { AnswerStatement, Linked, SourceLink, linkHost, rowBody, rowLink } from './links'
import { collectionRows } from './collectionRows'
import { supportsManualCollection } from './configuration'
import { focusMiniComposer, miniComposerDraft, saveMiniComposer } from './conversation'
import { setQuestionDraft, panelAt } from './panelDrafts'
import {
  answerDiff, answerText, changeWords, grounding, perspectivesOf, provenanceOf, statements,
  NOTHING_NEW_CODE,
  type AnswerChange, type InquiryEvent, type Perspective, type StandingSummary,
} from './perspectives'
import './summary.css'

/** What the counted lines say about themselves, where they are shown as the
 *  secondary detail they now are. */
export const EXTRACTIVE_LABEL = 'Counts and quotations from this collection.'
export const NO_COMPARISON = 'No comparison with an earlier collection. Nothing here claims anything changed.'
/** Said where the lead would be before any answer has been written: the
 *  counted facts are shown instead, and the view says which of the two it is
 *  showing rather than letting a measurement read as an answer. */
export const NOT_ANSWERED_YET = 'No answer is recorded for this collection yet. What follows is counted, not answered.'
/** Said beside the one press that writes the evolving summary. */
export const ANSWER_THIS_COLLECTION = 'Answer from this collection'
export const SUMMARY_IS_A_QUESTION = 'This is the answer standing against one kept question — “What is the state of what this Magnet has gathered?” — and its earlier answers are kept under it in Perspectives.'

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

export interface Excerpt {
  id: string; title: string; origin: string; text: string
  /** The address this record recorded for itself, where it has one, so an
   *  excerpt of a collected article can be followed to the article (owner
   *  ent-0b4f3f69b836). It is Part W's recorded permalink, read out of the
   *  row's own verified bytes (`links.tsx`), never built from a key. */
  link?: string
}
/** The records' own opening words, quoted. The one honest kind of "summary" a
 *  surface that has read nothing can offer: it shows the material instead of
 *  describing it, and every excerpt opens the record it came from.
 *
 *  Its `origin` is the clean one (`plainEvidenceOrigin`): the excerpts are the
 *  Summary's own resting content, so they say what kind of record each came
 *  from, never the recorded Conversation or collection id. The exact captured
 *  key stays one press away, in the inspection's provenance disclosure. */
export function collectedExcerpts(results: RouteResult[], limit = 4, length = 220): Excerpt[] {
  return results.map((r) => {
    // For a collected web row the quoted words are the material under the
    // recorded header: its headline is already `resultTitle` and its address is
    // already the link, so an excerpt that restated both read "Juno - NASA
    // Science (.gov) https://news.google.com/rss/articles/CBMiT0FV…".
    const body = rowBody(r), link = rowLink(r)
    // And its origin is the site, not the object key the collection stores it
    // under: this line was reading "Held file ·
    // space-missions-and-astronomy-what-launch/a733ec1ec5e51a4b" under a
    // headline the reader had just read. Every other record keeps
    // `plainEvidenceOrigin` exactly, and neither says a recorded identity.
    return { id: r.id, title: resultTitle(r), origin: linkHost(link) ?? plainEvidenceOrigin(r),
      text: (body ?? (capturedText(r) || (typeof object(r.value).text === 'string' ? object(r.value).text : ''))).replace(/\s+/g, ' ').trim().slice(0, length),
      ...(link ? { link } : {}) }
  })
    // A record with an address but no retained words of its own is still a
    // record worth showing -- it is the one thing the reader can open.
    .filter((e) => !!e.text || !!e.link).slice(0, limit)
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
  const lines: string[] = []
  const held = [posts ? `${posts} collected ${posts === 1 ? 'post' : 'posts'}` : '', files ? `${files} collected ${files === 1 ? 'file' : 'files'}` : '']
    .filter(Boolean).join(' and ') || 'nothing'
  lines.push(`This Magnet holds ${held}, collected ${when(s.activation.at)}.`)
  // WHERE IT CAME FROM, WITHOUT NAMING AN IDENTITY. The written overview is the
  // Summary's own resting content, and it used to list every captured key here,
  // so the first thing a reader saw was "They came from Conversation
  // ent-a1d2c5e714ea (3), Held file col-5260ed8d10f2 / README.md (1)." -- the
  // raw identifiers the owner asked the redesign to be rid of
  // (ent-1e82a8786c37). It says which kinds of source, and how many of each.
  // Nothing is lost: the Collection's own Sources view names each source by the
  // name a reader recognises, and the per-source breakdown with what each gave
  // is still stated, one press away, in the facts disclosure below
  // (`summaryFacts`) -- which is where the owner kept provenance.
  const kinds = [...counts.keys()].reduce((acc, key) => {
    if (key.startsWith('conversation:')) acc.conversations += 1
    else if (key.startsWith('file:')) acc.files += 1
    else acc.other += 1
    return acc
  }, { conversations: 0, files: 0, other: 0 })
  const from = [
    kinds.conversations ? `${kinds.conversations} ${kinds.conversations === 1 ? 'Conversation' : 'Conversations'}` : '',
    kinds.files ? `${kinds.files} held ${kinds.files === 1 ? 'file' : 'files'}` : '',
    kinds.other ? `${kinds.other} other ${kinds.other === 1 ? 'source' : 'sources'}` : '',
  ].filter(Boolean)
  if (from.length) lines.push(`They came from ${from.length > 1
    ? `${from.slice(0, -1).join(', ')} and ${from[from.length - 1]}` : from[0]}.`)
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

/** WHAT IS TRUE NOW, as one statement: what has been collected, when, and from
 *  how many sources. That is what the approved design puts under the heading of
 *  a surface -- one line in the mockups' own `muted` paragraph, not a stack of
 *  measurements (`04-browse.png`: "24 items from 2 sources · collected today").
 *
 *  The rest of `collectionOverview` -- the span the material was written over,
 *  how much text it runs to, which words recur, which configured sources gave
 *  nothing -- is measured detail ABOUT the collection rather than what it
 *  currently is, so it moves behind the one disclosure with the facts. Nothing
 *  is deleted and nothing is re-worded: this reads the same lines, and takes the
 *  first two of them. */
export function collectionLead(saved: SavedMagnet, s: MagnetSnapshot): string {
  return collectionOverview(saved, s).slice(0, 2).join(' ')
}

/** The measured lines that are not the lead, which the disclosure carries. */
export function collectionDetail(saved: SavedMagnet, s: MagnetSnapshot): string[] {
  return collectionOverview(saved, s).slice(2)
}

/** WHAT HAS BEEN COLLECTED, beside the heading, in the design's own place for a
 *  count (`04-browse.png`'s `<h2>Collected items <span class="subtle">24</span>`).
 *  It is the one place the Summary says how much there is, and before the single
 *  retained read answers it says exactly that and claims nothing. */
export function heldWords(s: MagnetSnapshot, posts: number, files: number): string {
  if (s.activation === undefined) return 'not read yet'
  if (!s.activation) return 'nothing collected yet'
  return `${posts} ${posts === 1 ? 'post' : 'posts'} · ${files} ${files === 1 ? 'file' : 'files'}`
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
  for (const w of frequentWords(s.results, 2)) out.push(`What do the collected records say about ${w.word}?`)
  // A collected source is still something to ask about, asked without its
  // recorded key: an offered question a reader presses is not the place for an
  // identity (owner request ent-1e82a8786c37), and one that carried it read
  // "What is in the material collected from Conversation ent-a1d2c5e714ea?".
  if (counts.size) out.push(counts.size === 1
    ? 'What is in the material this source collected?'
    : 'What is in the material collected from each source?')
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

/** THE EMPTY COLLECTION'S ONE OBVIOUS STARTING ACTION (owner request
 *  ent-068c167fa7e6 §2, §4). With nothing collected the useful move is to say
 *  where to look, so the empty state carries one press that opens Settings on
 *  the sources -- not a wall of explanation, and not a second Collect control
 *  whose authority this view does not hold. What the press says depends on
 *  whether anything is configured yet, which is a fact of the saved definition
 *  and needs no request. */
export function startingAction(saved: SavedMagnet): { label: string; note: string } {
  const sources = saved.config?.sources ?? []
  if (!sources.length) return { label: 'Choose a source', note: 'Nothing is read until you choose where to look.' }
  const named = `${sources.length} configured ${sources.length === 1 ? 'source' : 'sources'}.`
  // Collection runs when the owner presses for it, and only where the saved
  // modes support that. Nothing here says it happens on its own (§5).
  return { label: 'Review sources', note: saved.config && supportsManualCollection(saved.config)
    ? `${named} Collect when you are ready.`
    : `${named} Collecting by hand is not configured yet; choose manual collection in Settings.` }
}

/** Opening Settings from the empty state. Kept as a function so the starting
 *  action can be driven without a browser, like every other press here. */
export function chooseSources(resource: MagnetResource): void {
  openOverlay(resource, 'settings')
}

/** Going to the collected records themselves: the Collection, unfiltered. The
 *  collected records are the working content, so every route into them from
 *  here is this one place rather than a type-specific list. */
export function browseCollection(resource: MagnetResource): void {
  goTab(resource, 'All')
}

/** With nothing collected, a starter question is an ordinary message. The
 *  owner's own unsent words are never overwritten: that is what it returns. */
export function askOrdinaryQuestion(resource: MagnetResource, question: string): string {
  const draft = miniComposerDraft(resource)
  if (draft.text.trim()) return 'The Composer already holds words of yours. Keep or clear them first.'
  saveMiniComposer(resource, { ...draft, text: question })
  focusMiniComposer()
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

/** WHAT AN ANSWER WAS GROUNDED IN, beside the answer itself.
 *
 *  Three distinct statements, never a blend (Part A's contract, its field names
 *  unchanged): grounded in this collection, allowed to look outside and did
 *  not, and explored outside -- which is rendered as a visibly different thing,
 *  with what it reached named. An answer whose provenance was not recorded says
 *  that, and is not shown as grounded. */
export function Grounded({ answer }: { answer: InquiryEvent | null }) {
  const g = grounding(provenanceOf(answer))
  if (!answer) return null
  return <div className={`q2-magnet-grounding${g.outside ? ' q2-magnet-outside' : ''}`}>
    <span className={g.outside ? 'mgd-future' : 'mgd-today'}>{g.label.toUpperCase()}</span>
    <span className="mgd-subtle">{g.detail}</span>
    {!!g.reached.length && <ul className="q2-magnet-items" aria-label="What this answer reached outside the collection">
      {g.reached.map((what) => <li key={what}>{what}</li>)}</ul>}
  </div>
}

/** A ROW THE READER PRESSES, in the approved design's own shape: the ruled
 *  record row of `04-browse.png` (`mgd-item`) with the whole row as the control.
 *  The rule, the title weight, the quoted paragraph and the byline are the
 *  design's; what this adds is that pressing the row opens the record inside the
 *  card, which is why the pressable element is a button and its words are
 *  phrasing content rather than a `<p>`. */
function RecordRow({ excerpt, expanded, onOpen }: { excerpt: Excerpt; expanded: boolean; onOpen(): void }) {
  return <div className="mgd-item">
    <button type="button" className="q2-magnet-quote-row" id={`excerpt-${excerpt.id}`} aria-expanded={expanded} onClick={onOpen}>
      <b>{excerpt.title}</b>
      {!!excerpt.text && <span className="q2-magnet-quote">“{excerpt.text}{excerpt.text.length >= 220 ? '…' : ''}”</span>}
      <small className="mgd-subtle">{excerpt.origin}</small>
    </button>
    {/* Outside the press, for the same reason the Collection's rows put it
        there: this row already opens the captured copy inside the card. */}
    {!!excerpt.link && <SourceLink url={excerpt.link} />}
  </div>
}

/** AN OFFERED QUESTION, as the mockups offer one: the `mgd-example` block with
 *  its gold left rule and the `↗` that takes it up (`02-compact-current.png`'s
 *  "TRY ASKING"). The whole row is the press, as the rows above are. */
function QuestionRow({ question, onTake }: { question: string; onTake(): void }) {
  return <div className="mgd-example">
    <button type="button" className="q2-magnet-question" onClick={onTake}>
      <span className="q2-magnet-question-words">{question}</span>
      <span className="mgd-link" aria-hidden="true">↗</span>
    </button>
  </div>
}

/** THE RECORDED QUESTIONS AND INTERPRETATIONS THIS MAGNET HOLDS, behind the
 *  design's own disclosure for them (`Past questions ▾`, `08-history.png`).
 *  Nothing is removed: the recorded question, its own wording, its revision and
 *  the recorded challenges are all still here, attributed and versioned, and
 *  still read only when the owner asks. What changed is that the Summary's
 *  resting surface no longer opens on a heading about the record's bookkeeping.
 *  The disclosure's own words are its accessible name, so the heading that said
 *  the same thing twice is the label rather than a line under it. */
function Questions({ resource, rows, events, loading, error, onLoad, read }: {
  resource: MagnetResource; rows: Perspective[]; events: InquiryEvent[]
  loading: boolean; error?: string; onLoad(): void; read: boolean
}) {
  const challenges = recordedChallenges(events)
  return <details className="q2-magnet-provenance q2-magnet-disclosure">
    <summary><span className="mgd-link mgd-small">Past questions ▾</span></summary>
    <div aria-label="Questions and interpretations already recorded">
      {!read
        ? <><p className="mgd-subtle">Not read yet. Nothing is read from the record until you ask for it.</p>
          <button type="button" className="mgd-link mgd-small" disabled={loading} onClick={onLoad}>Show recorded questions</button></>
        : rows.length
          ? rows.map((p) => <div className="mgd-item" key={p.perspective}>
            <b>{p.name}</b>{p.retired ? <small className="mgd-subtle"> · retired</small> : null}
            {p.current_question && <p className="q2-magnet-quote">“{p.current_question.text}”</p>}
            <small className="mgd-subtle">Question · {p.perspective}{p.current_question ? ` · revision ${p.current_question.revision}` : ''}</small>
          </div>)
          : <p className="mgd-subtle">No questions recorded for this Magnet yet.</p>}
      {read && !!challenges.length && <>
        <div className="mgd-eyebrow">Recorded challenges</div>
        {challenges.map((e) => <div className="mgd-item" key={e.post}>
          <p className="q2-magnet-quote">“{typeof e.data?.text === 'string' ? e.data.text : 'A challenge was recorded with no wording.'}”</p>
          <small className="mgd-subtle">Recorded challenge · {e.post}</small>
        </div>)}
      </>}
      {error && <p className="mgd-subtle" role="status">{error}</p>}
      <button type="button" className="mgd-link mgd-small" onClick={() => goTab(resource, 'Perspectives')}>Work on questions</button>
    </div>
  </details>
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
  const [answering, setAnswering] = useState(false)
  /** A batch change invalidates a comparison taken against the previous one. */
  useEffect(() => { setComparison(null); setMessage('') }, [batch])

  /* THE EVOLVING SUMMARY, READ AND -- ONCE PER COLLECTION -- WRITTEN.
     The lead is the current answer of this Magnet's standing Perspective. This
     view reads it, and where the record holds no answer for the collection in
     hand it asks for one: ONE write per observed collection, keyed by that
     batch, so a replay or a second surface records nothing further. There is no
     timer, no poll and no retry -- a refusal is said in words and never tried
     again -- and the server decides whether there is anything new to answer
     from Part E's own new-item count, refusing `nothing-new` when there is
     not. Collecting is still only ever the owner's press. */
  const summary: StandingSummary | null | undefined = lens.summary
  const asked = useRef<string | null>(null)
  useEffect(() => {
    if (!batch || asked.current === batch) return
    asked.current = batch
    setAnswering(true)
    void inquiries.readSummary()
      .then((got) => got?.batch === batch ? got : inquiries.summarise(batch))
      .catch((e: Error) => { if ((e as { details?: { code?: string } }).details?.code !== NOTHING_NEW_CODE) setMessage(`No answer was written from this collection: ${e.message}`) })
      .finally(() => setAnswering(false))
    // Only the collected batch may start this: nothing else here is new evidence.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batch])
  const answerNow = () => {
    if (!batch || answering) return
    setAnswering(true); setMessage('')
    void inquiries.summarise(batch)
      .catch((e: Error) => setMessage(e.message))
      .finally(() => setAnswering(false))
  }
  const answered = answerText(summary?.current)
  const change: AnswerChange | null = answerDiff(summary?.current, summary?.superseded[0])

  const lead = collectionLead(resource.saved, s)
  const detail = collectionDetail(resource.saved, s)
  const excerpts = collectedExcerpts(s.results)
  const starting = startingAction(resource.saved)
  const questions = offeredQuestions(s, !!comparison)

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
    {/* THE HEADING BLOCK EVERY SURFACE HAS (plan seam 4): the place's name as
        the eyebrow, what is being shown as the 25px heading with its count
        beside it, and the one most useful counterpart link at the far edge of
        that row. The pattern and the numbers are the approved design's
        (`04-browse.png`), and it replaces the floating link row that was
        there. */}
    <div className="mgd-row mgd-spread q2-magnet-place-head">
      <div className="mgd-grow">
        <div className="mgd-eyebrow">Summary</div>
        <h2 id="summary-title" className="mgd-h2" tabIndex={-1}>What this Magnet holds{' '}
          <span className="mgd-subtle">{heldWords(s, posts.length, files.length)}</span></h2>
      </div>
      {!!s.activation && !!items.length && <button type="button" className="mgd-link mgd-small q2-magnet-place-link"
        onClick={() => browseCollection(resource)}>Collected items →</button>}
    </div>
    {s.loading && <p className="mgd-subtle" role="status">Reading this collection…</p>}
    {read && !s.activation
      ? <>
          {/* WHAT IS TRUE NOW, then the useful action AS A BUTTON. The sentence
              that used to describe the action ("Choose sources in Settings,
              then collect.") is the button and its own note: the owner asked
              for useful actions presented prominently rather than explained
              (ent-a24ec84c8176). */}
          <p className="mgd-p">No collected information yet.</p>
          <div className="mgd-row mgd-spread q2-magnet-lead-action">
            <span className="mgd-subtle mgd-grow">{starting.note}</span>
            <button type="button" className="mgd-button" onClick={() => chooseSources(resource)}>{starting.label}</button>
            <button type="button" className="mgd-button mgd-secondary" disabled={!resource.collect || !resource.saved.config || !supportsManualCollection(resource.saved.config) || s.collecting} onClick={() => void resource.collect?.()}>Collect now</button>
          </div>
          <div className="mgd-divider" />
          <div className="mgd-eyebrow">Start a conversation</div>
          {questions.map((q) => <QuestionRow key={q} question={q} onTake={() => askOrdinary(q)} />)}
        </>
      : <>
        {/* Before the one retained read answers there is nothing to say about
            the collection, so nothing below is claimed: the facts line says it
            has not been read, and that is the whole of it. */}
        {!!s.activation && <>
        {/* THE LEAD IS THE ANSWER. The current answer of this Magnet's standing
            Perspective, statement by statement as it was recorded, with what it
            was grounded in stated beside it. Before any answer exists the
            counted lead is shown instead, saying which of the two it is. */}
        {answered
          ? <section className="q2-magnet-answer" aria-label="What this Magnet has gathered">
              {/* STATEMENT, THEN WHAT IT QUOTED, THEN AIR (owner
                  ent-0b4f3f69b836). The recorded characters are unchanged:
                  `AnswerStatement` lays one statement out and makes the
                  addresses in it followable. What was grounded in what is said
                  by `Grounded`, below, exactly as before. */}
              {statements(answered).map((line, i) =>
                <AnswerStatement key={`answer-${i}`} line={line} lead={!i} />)}
              <Grounded answer={summary?.current ?? null} />
              {/* Who wrote it is said ONCE, by the grounding statement above
                  ("Written from this Magnet's collected records and nothing
                  else"). What this adds is the one thing that statement does
                  not: that it is a kept question's answer, with its earlier
                  answers under it. The answer package's own `written_by`
                  sentence is on the recorded answer, one press away. */}
              <p className="mgd-subtle">{SUMMARY_IS_A_QUESTION}</p>
            </section>
          : <><p className="mgd-p mgd-muted q2-magnet-lead">{lead}</p>
              <p className="mgd-subtle">{answering ? 'Writing an answer from this collection…' : NOT_ANSWERED_YET}</p></>}
        {/* The design's own action row (`03-sources.png`'s "Collect manually"):
            what is true on the left, the press at the far edge. */}
        <div className="mgd-row mgd-spread q2-magnet-lead-action">
          <span className="mgd-subtle mgd-grow">{starting.note}</span>
          <button type="button" className="mgd-button mgd-secondary" disabled={answering || !batch} onClick={answerNow}>
            {answering ? 'Answering…' : answered ? 'Answer again from this collection' : ANSWER_THIS_COLLECTION}</button>
          <button type="button" className="mgd-button" onClick={() => chooseSources(resource)}>{starting.label}</button>
        </div>
        <div className="mgd-divider" />

        {/* THE COLLECTED RECORDS COME FIRST (owner request ent-068c167fa7e6 §2:
            "Make collected information the primary working content"). What was
            collected is read before anything measured about it, and every row
            opens the record it quotes. */}
        {!!excerpts.length && <section aria-label="In the collected records’ own words">
          <div className="mgd-row mgd-spread">
            <h3 className="mgd-h3 mgd-grow">In the records’ own words</h3>
            {items.length > excerpts.length && <button type="button" className="mgd-link mgd-small" onClick={() => browseCollection(resource)}>
              All {items.length} collected items →</button>}
          </div>
          {excerpts.map((e) => <RecordRow key={e.id} excerpt={e} expanded={here.inspected === e.id}
            onOpen={() => inspect(resource, e.id, `excerpt-${e.id}`)} />)}
        </section>}

        <div className="mgd-space" />
        {/* AN OFFERED QUESTION NOW LEADS TO AN ANSWER. With a collection in
            hand, pressing one carries it into Perspectives, where asking it
            records a real answer grounded in these rows. The ordinary
            source-free route stays exactly where it was useful -- the empty
            state below, which has nothing to answer from. */}
        <section aria-label="Questions to explore">
          <div className="mgd-eyebrow">Questions to explore</div>
          {questions.map((q) => <QuestionRow key={q} question={q} onTake={() => exploreQuestion(resource, q)} />)}
        </section>

        <div className="mgd-divider" />
        {/* EVERYTHING THAT IS MECHANISM IS BEHIND ONE OF THESE, in the design's
            own idiom (`Limits and dates ▾`, `Past questions ▾`). Comparing two
            collections opens itself once a comparison has been made, because
            then it has something to say. */}
        <details className="q2-magnet-provenance q2-magnet-disclosure" open={!!comparison || !!change?.added.length}>
          <summary><span className="mgd-link mgd-small">What changed ▾</span></summary>
          <div aria-label="Changes since the previous collection">
            {/* WHAT CHANGED IS THE DIFFERENCE BETWEEN TWO ANSWERS. The answer
                standing now against the answer it superseded: that is what the
                evolving summary changing means. The batch comparison stays
                below it, as the measured detail it is. */}
            {!!summary?.current && <>
              <p className="mgd-p">{changeWords(change)}</p>
              {change?.added.map((line) => <p className="mgd-item" key={`added-${line}`}><span className="mgd-subtle">Now says · </span><Linked text={line} /></p>)}
              {change?.gone.map((line) => <p className="mgd-item" key={`gone-${line}`}><span className="mgd-subtle">No longer says · </span><Linked text={line} /></p>)}
              {!summary.superseded.length && <p className="mgd-subtle">This is the first answer recorded against this Magnet's standing question, so there is nothing before it to differ from.</p>}
              <div className="mgd-divider" />
            </>}
            {comparison
              ? <><p className="mgd-p">{comparison.words}</p>
                {comparison.added.map((e) => <div className="mgd-item" key={e.id}>
                  <button type="button" className="mgd-link" onClick={() => inspect(resource, e.id, `excerpt-${e.id}`)}>{e.title}</button>
                  {!!e.link && <SourceLink url={e.link} />}
                  {!!e.text && <p className="q2-magnet-quote">“{e.text}”</p>}
                </div>)}
                <p className="mgd-subtle">Compared against the collection from {when(comparison.at) ?? 'earlier'}. Both are captured copies; neither source was read again.</p></>
              : <><p className="mgd-subtle">{NO_COMPARISON}</p>
                <button type="button" className="mgd-link mgd-small" disabled={comparing || !batch} onClick={compare}>
                  {comparing ? 'Reading the previous collection…' : 'Compare with the previous collection'}</button></>}
          </div>
        </details>

        <Questions resource={resource} rows={lens.rows} events={lens.events} loading={loadingQuestions || lens.loading}
          error={lens.error} onLoad={loadQuestions} read={askedForQuestions || !!lens.rows.length} />

        </>}

        {/* THE ONE DISCLOSURE FOR THE COLLECTION'S OWN MECHANISM, named as the
            other surfaces name theirs. It carries the counted detail and the
            facts: the configured sources and what each gave, the recorded
            state, the selected types, the selected dates, the limits, and the
            comparison baseline. Nothing is deleted -- it stops being the first
            thing read (owner ent-a24ec84c8176). */}
        <details className="q2-magnet-provenance q2-magnet-disclosure" open={here.history}>
          <summary><span className="mgd-link mgd-small">Limits and dates ▾</span></summary>
          <div className="q2-magnet-facts">
            {detail.map((line, i) => <p key={`measured-${i}`}>{line}</p>)}
            {summaryFacts(resource.saved, s).map((line, i) => <p key={i}>{line}</p>)}
          </div>
        </details>
      </>}
    {message && <p className="mgd-subtle" role="status">{message}</p>}
    {/* Inline, inside the Summary section: never a separate screen. */}
    {here.inspected && <Inspection resource={resource} refId={here.inspected} source={onPost} />}
    {/* THE PERMANENTLY DISABLED "Draft an answer from selected records" PRESS
        IS GONE, with the sentence that said answering was unavailable until
        configured-source access was enforced. It is enforced (Part A,
        `mentis/magnet/scope.py`), the gate is open, and the press that writes
        an answer from this collection is in the action row above, beside what
        it answers. Nothing here claims a grounding it does not have: every
        answer states what it was grounded in. */}
  </section>
}
