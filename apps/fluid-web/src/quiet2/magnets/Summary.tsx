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
 *  explored outside the collection is rendered as a different thing.
 *
 *  **PRESENTED BY WHAT IT REPRESENTS** (owner #1017 `ent-599e68de0893`, plan
 *  Part 5). Three things this view used to get wrong, all of them about
 *  presentation and none about what is claimed:
 *
 *  1. The server records every answer as `lines: [{text, cites:[row ids]}]`
 *     (`mentis/magnet/perspectives_work.py`) and this view read only
 *     `data.text` and split it on newlines, so the citation each statement
 *     carries -- the one thing that makes a statement checkable -- was thrown
 *     away before the reader saw it. It is read now, and every statement is
 *     pressable to the captured records it was written from (`answerLines`,
 *     `citedRows`, `Briefing`) -- a written briefing included: where the
 *     server recorded `lines`, each is drawn as its own prose block with its
 *     own citations, rather than the whole document read straight into
 *     `Prose` and its citations dropped.
 *  2. A recorded answer that is a written document rather than one statement
 *     per line is rendered as prose by the Fluid renderer that already exists
 *     (`Prose`, `src/prose.tsx`): headings, paragraphs, lists and pipe tables,
 *     and in a browser the marked `timeline`/`chart` blocks of the existing
 *     registry. Nothing new is written and no renderer is edited.
 *  3. The lead before any answer exists was a record count ("This Magnet holds
 *     72 collected files, collected …"). It is what the material NAMES now
 *     (`materialLead`), read out of the rows' own captured words; every
 *     measurement -- the counts, the span, the word total, the counted words,
 *     and the synthesis's own trailing record-count line (`answerRecordCount`)
 *     -- is behind the one facts disclosure it always had.
 *
 *  And where the collected material records when it was published, that dated
 *  shape is drawn as a table rather than described (`datedMaterial`,
 *  `datedTable`): a set of dated published articles is a table, whatever the
 *  bytes it is stored as.
 *
 *  **THE REASONED BRIEFING IS ASKED FOR, NOT WAITED FOR** (owner #1017, plan
 *  Part 3). No model is called on the synthesis path, so the counted answer is
 *  the best that path can write; a briefing is written by a run reasoning over
 *  the collected records, through the mechanism the Perspectives surface
 *  already has. This view adds one press (`askForBriefing`), which freezes the
 *  standing question with this collection as its evidence and hands it to the
 *  Conversation for the owner to send, and the reading of the answer that comes
 *  back (`readFrozenAnswer`, `withWords`) -- which the record keeps as a frozen
 *  package rather than as words on the event. Nothing dispatches itself, and a
 *  briefing standing as the answer is never written over on its own. */
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { Prose, blocksAt, blocksOf, isStructured, isTableDivider, isTableRow, rowCells, type Block } from '../../prose'
import type { MagnetResource, MagnetSnapshot, SavedMagnet, SearchEntry, SearchSource } from './contract'
import type { MagnetSource } from '../../fluid/surface/magnet/types'
import Inspection, { artifactOf, capturedText, plainEvidenceOrigin, retainedFiles, sourceLabel } from './Inspection'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import { goTab, inspect, openOverlay, place, setOpen } from './places'
import { resultTitle } from './EvidenceViews'
import {
  AnswerStatement, Citations, Linked, SourceLink, SourceNotes, citedInline, citedRefs,
  linkHost, rowBody, rowHeader, rowLink, type CitationIndex, type SourceNote,
} from './links'
import { collectionRows } from './collectionRows'
import { supportsManualCollection } from './configuration'
import { focusMiniComposer, miniComposerDraft, saveMiniComposer } from './conversation'
import { setQuestionDraft, panelAt } from './panelDrafts'
import {
  answerDiff, answerText, changeWords, grounding, perspectivesOf, provenanceOf,
  restampAttachedQuestion, showPerspectiveContext, statements,
  NOTHING_NEW_CODE, STANDING_QUESTION,
  type AnswerChange, type InquiryEvent, type Perspective, type PerspectiveStore,
  type PreparedInquiry, type StandingSummary,
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
/** THE DISCLOSURE THE ANSWER'S APPARATUS LIVES BEHIND (owner
 *  `ent-15a36a065eb8`: secondary actions and provenance through progressive
 *  disclosure, not permanently on screen and not hidden). What it holds is
 *  every sentence the record requires to be readable about how this answer
 *  came to stand -- its grounding, what was checked before a run's reply was
 *  frozen as it, that it is a kept question's answer, and what the presses
 *  under it do. What it does NOT hold is anything that qualifies the answer's
 *  own words: an answer written from an earlier collection says so above, in
 *  the open. */
export const HOW_THIS_WAS_MADE = 'How this answer was made'

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
  // THE COUNTED WORDS ARE A FACT ABOUT THE TEXT, so they are stated where the
  // facts are. They were a sentence of the written overview -- the thing a
  // reader met before anything the material says -- which is the "collection
  // statistics ... presented as the primary content" the owner asked to be
  // demoted (#1017). Nothing is deleted and nothing is re-worded: the same
  // counted line, in the disclosure the other measurements are in.
  const frequent = frequentWords(s.results)
  if (frequent.length) lines.push(`Most used words, counted: ${frequent.map((w) => `${w.word} (${w.count})`).join(', ')}.`)
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

/** The range of the collected rows' own recorded `at`, read as when each row
 *  entered this collection -- not when the batch as a whole was collected,
 *  which `s.activation.at` already says, and not when an acquired row's
 *  material was itself written: for a held or acquired row, `at` is when this
 *  Magnet fetched it (see `rowPublication`, which reads the row's own
 *  recorded `Published:` line for that fact where one exists). */
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
    ? `The collected material was all collected on ${day(span.first)}.`
    : `The collected material was collected between ${day(span.first)} and ${day(span.last)}.`)
  if (words) lines.push(`Its collected text runs to about ${words.toLocaleString()} ${words === 1 ? 'word' : 'words'}.`)
  // The counted words moved to `summaryFacts`: see the note there. Every line
  // left here is still a measurement, and the view keeps all of them behind the
  // facts disclosure rather than leading with one.
  if (s.status && s.status !== 'ok') lines.push(`Not every source reported its whole scope, so this is what was collected, not everything that exists${s.reason ? `: ${s.reason}` : '.'}`)
  const sources = saved.config?.sources ?? []
  const uncaptured = sources.filter((source) => { const key = configuredKey(source); return !key || !counts.get(key) })
  if (uncaptured.length) lines.push(`${uncaptured.length} configured ${uncaptured.length === 1 ? 'source' : 'sources'} contributed nothing to this collection.`)
  return lines
}

/* ---------------------------------------------------------------------------
   WHAT THE MATERIAL NAMES -- the lead before any answer is recorded.

   The lead used to be the first two lines of `collectionOverview`: "This
   Magnet holds 72 collected files, collected 26 November 2026. They came from
   72 held files." Both sentences are true and both are counts, so the first
   thing a reader met was bookkeeping -- exactly the "collection statistics
   ... presented as the primary content" the owner asked to be demoted (#1017
   `ent-599e68de0893`). Every one of those lines is still written, and still
   available, behind the facts disclosure.

   What leads instead is read out of the rows' own captured words. */

/** Leading words stripped off a capitalised run before it is read as a name:
 *  a sentence-initial "The" or a question word is grammar, not a subject. The
 *  same list as `mentis/magnet/perspectives_work.py::_LEADING_STOP`. */
const LEADING_STOP = new Set(('the a an this that these those is are was were it its new from for with on at to in of as by '
  + 'what how why when where who which and or but not here there').split(' '))

/** THE SUBJECTS THE COLLECTED MATERIAL ITSELF NAMES: runs of two or more
 *  consecutive capitalised words ("Roman Space Telescope", "Artemis
 *  Programme"), ranked by how many rows name each.
 *
 *  This is content read, not a word counted -- a collection whose rows name
 *  nothing beyond ordinary sentences yields nothing at all, which is the honest
 *  outcome for it rather than a frequency table dressed up as a theme. The
 *  server makes the same reading over the same bytes
 *  (`perspectives_work.py::_subject_candidates`, `_subjects`) and the two agree
 *  on purpose: what this surface offers to ask about should be what an answer
 *  written from these rows leads with. */
export function namedSubjects(results: RouteResult[], limit = 3): string[] {
  const counts = new Map<string, number>(), order: string[] = []
  for (const r of results) {
    const said = new Set<string>()
    // The row's own words, READ AS SEPARATE PASSAGES -- never its provenance
    // trailer, which restates the configured search itself and would name the
    // same "subject" in every row. The headline and the material are read
    // apart because a run must not span the join between them: a feed title
    // ending in its byline, read straight into a body that opens with a name,
    // gave "NASA The Roman Space Telescope", a phrase neither passage says.
    const header = rowHeader(r)
    for (const passage of header ? [header.headline ?? '', header.body] : [resultTitle(r), capturedText(r)]) {
      let run: string[] = []
      const close = () => {
        let phrase = run
        while (phrase.length && LEADING_STOP.has(phrase[0].toLowerCase())) phrase = phrase.slice(1)
        if (phrase.length >= 2) said.add(phrase.join(' '))
        run = []
      }
      // A sentence end closes a run too: "… ships to the launch site. Its
      // coronagraph …" is two sentences, not one name.
      for (const raw of String(passage).split(/\s+/)) {
        const token = raw.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '')
        if (token && /^\p{Lu}/u.test(token)) {
          run.push(token)
          if (/[.!?:;]$/.test(raw)) close()
          continue
        }
        close()
      }
      close()
    }
    for (const phrase of said) {
      if (!counts.has(phrase)) order.push(phrase)
      counts.set(phrase, (counts.get(phrase) ?? 0) + 1)
    }
  }
  return order.sort((a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0) || order.indexOf(a) - order.indexOf(b))
    .slice(0, limit)
}

/** Said where the material names no subject of its own. Honest rather than
 *  silent, and it does not fall back to a count. */
export const NAMES_NOTHING_YET = 'The collected material names no subject that stands out of it yet. What it holds is quoted below in its own words.'

/** WHAT THE COLLECTION'S MATERIAL IS ABOUT, in one sentence, from its own
 *  words. The lead before an answer is recorded against the standing question
 *  -- and not a measurement of the collection, which is what it was. */
export function materialLead(s: MagnetSnapshot): string {
  if (s.activation === undefined || !s.activation) return ''
  const subjects = namedSubjects(s.results, 3)
  if (!subjects.length) return NAMES_NOTHING_YET
  const named = subjects.length > 1
    ? `${subjects.slice(0, -1).join(', ')} and ${subjects[subjects.length - 1]}`
    : subjects[0]
  return `The collected material names ${named}.`
}

/* ---------------------------------------------------------------------------
   DATED PUBLISHED MATERIAL IS A TABLE (owner #1017: "present information
   according to what it represents, not its internal storage type ... prose,
   images, tables, charts or timelines where appropriate").

   A set of articles that each record when they were published and who
   published them has a shape, and that shape is a table -- whatever the bytes
   it happens to be stored as (a held file, in this Magnet's case, which is why
   it was being drawn as a stack of quoted text). The columns are read out of
   each row's OWN recorded trailer, the one `mentis/sources/feeds.py::
   _entry_body` writes and `perspectives_work.py::_published`/`_publisher`
   read server-side: nothing is derived, inferred or fetched, and a row that
   recorded no publication date contributes no row to the table.

   It is drawn by the renderer that already draws tables -- `Prose`'s pipe
   tables (`src/prose.tsx`) -- so nothing here is a new renderer or a new
   presentation layer. */

/** When a collected row says IT was published, and by whom, from its own
 *  recorded `Published:`/`Publisher:` lines. Never `r.at`, which is when this
 *  Magnet fetched it -- a different fact, and the one the Summary used to
 *  report as when the material was written. */
export function rowPublication(r: RouteResult): { published: string | null; publisher: string | null } {
  const text = capturedText(r) || (typeof object(r.value).text === 'string' ? object(r.value).text : '')
  let published: string | null = null, publisher: string | null = null
  for (const raw of String(text).split('\n')) {
    const line = raw.trim()
    if (!published && line.startsWith('Published:')) {
      const said = line.slice('Published:'.length).trim()
      const at = Date.parse(said)
      published = Number.isFinite(at) ? new Date(at).toISOString().slice(0, 10) : null
    }
    if (!publisher && line.startsWith('Publisher:')) publisher = line.slice('Publisher:'.length).trim() || null
  }
  return { published, publisher }
}

export interface DatedRow { id: string; title: string; published: string; publisher: string }
/** The collected rows that record their own publication date, newest first. */
export function datedMaterial(results: RouteResult[], most = 10): DatedRow[] {
  const out: DatedRow[] = []
  for (const r of results) {
    const { published, publisher } = rowPublication(r)
    if (!published) continue
    out.push({ id: r.id, title: resultTitle(r), published, publisher: publisher ?? '—' })
  }
  return out.sort((a, b) => b.published.localeCompare(a.published) || a.title.localeCompare(b.title)).slice(0, most)
}

/** Whether a table is worth drawing: two or more dated rows, over more than
 *  one date. One date is not a time axis, and a single row is not a table. */
export function worthTabulating(rows: DatedRow[]): boolean {
  return rows.length >= 2 && new Set(rows.map((d) => d.published)).size > 1
}

/** A table cell's text, safe to put between pipes. A headline holding a `|`
 *  would otherwise open a column the author did not write. */
const cell = (words: string, most = 80): string => {
  const said = String(words).replace(/\s+/g, ' ').replace(/\|/g, '\\|').trim()
  return said.length > most ? `${said.slice(0, most - 1)}…` : said || '—'
}

/** Those rows as the Markdown pipe table `Prose` already draws. */
export function datedTable(rows: DatedRow[]): string {
  return ['| Published | What it is | Publisher |', '|---|---|---|',
    ...rows.map((d) => `| ${cell(d.published, 12)} | ${cell(d.title)} | ${cell(d.publisher, 40)} |`)].join('\n')
}
export const DATED_WHY = 'Published dates and publishers as the records themselves recorded them — not when this Magnet collected them.'

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
  // A SUBJECT THE MATERIAL NAMES, where it names one. "What do the collected
  // records say about Roman Space Telescope?" is a question about the material;
  // "… about launches?" -- a word that happened to recur -- is a question about
  // a word count. Where the rows name nothing, the counted word is still the
  // honest thing to offer, so that is the fallback and not a silence.
  const subjects = namedSubjects(s.results, 2)
  for (const subject of subjects) out.push(`What do the collected records say about ${subject}?`)
  if (!subjects.length) for (const w of frequentWords(s.results, 2)) out.push(`What do the collected records say about ${w.word}?`)
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

/* ---------------------------------------------------------------------------
   THE REASONED BRIEFING (owner #1017 `ent-599e68de0893`, plan Part 3).

   The owner asked for a Summary that reads like an intelligent research
   briefing -- themes, noteworthy discoveries, developments, implications,
   avenues worth exploring -- rather than the counts the Python synthesis
   writes. No model is called on the synthesis path (`perspectives_work.py`
   `_state_of`), so no instruction of its can produce one: a briefing is
   written by a run that reasons over the collected records.

   NOTHING NEW IS BUILT FOR IT. The mechanism is the one the Perspectives
   surface already uses for an agent-written answer: the question is frozen
   with this Magnet's own collection as its immutable evidence package
   (`store.prepare`), the frozen ask travels through the Conversation's own
   composer (`ComposerBar`'s `beforeRequest`), and the reply the record shows
   answered it is frozen as this Perspective's answer at the recorded
   agent-reply boundary (`finalizeReply`, `MiniConversation`). What this
   surface adds is the one press that starts it for the STANDING question --
   the one whose answer is this Summary's lead -- and the reading of the answer
   that comes back.

   IT IS THE OWNER'S PRESS, AND ONLY THE OWNER'S. The press dispatches
   nothing: it freezes the question and carries it into this Magnet's
   Conversation, where the owner chooses who answers it and presses Send,
   exactly as "Ask an agent about this" does on the Perspectives surface. A
   Magnet opening spends no run, nothing wakes to write a briefing, and the
   written synthesis stays as the no-agent floor until a reply is frozen in
   its place (AGENTS.md: nothing wakes on its own; `activation.py` refuses a
   synthesis mode that is not `manual`).

   The hand-off is written here rather than imported from `InquiryPanel`'s own
   `askAnAgent`, which does the same three steps for the question being viewed:
   that module imports this one (`offeredQuestions`), so importing it back
   would be a cycle. The steps, their order and their refusals are the same;
   where the shared hand-off belongs is noted as a seam for the owner of those
   files. */

/** Answer instructions travel in the asking Turn, separately from the saved
 *  question. Refreshing an answer must preserve that question's exact bytes. */
export const BRIEFING_INSTRUCTIONS = 'Write the answer as a research briefing: the meaningful themes running through the collected records, the noteworthy discoveries and developments they report, what those imply, and the interesting avenues they leave worth exploring. Write publication prose with Markdown headings and lists where the content warrants them. Begin with the substantive answer; omit first-person process narration and closing work reports. Ground every statement in the attached collected records and cite the exact ones each statement is written from, using the attached evidence citation tokens that the reader renders as numbered inline markers with accessible provenance. Counts and collection statistics are secondary; put them last or leave them out.'
export const BRIEFING_ASK = `${STANDING_QUESTION}\n\n${BRIEFING_INSTRUCTIONS}`
export const WRITE_THE_BRIEFING = 'Ask an agent for a briefing'
const briefingRequest = (question: string) => question.endsWith(BRIEFING_INSTRUCTIONS)
  ? question : `${question}\n\n${BRIEFING_INSTRUCTIONS}`
/** Said beside the press, because a press that looks like it spends a run must
 *  say what it actually does -- AND NO MORE THAN IT DOES. It used to promise
 *  this collection as "the only evidence" for the briefing, which the act does
 *  not establish: `store.prepare` freezes the collection in hand together with
 *  whatever this question already carries -- records the owner selected,
 *  records they declared, earlier answers named as prior interpretation, and
 *  the Conversation when continuation is on (review `ent-5acd177f3aa8` F3).
 *  What actually went in is said after the press, counted, by
 *  `briefingFrozenWords`. */
export const BRIEFING_IS_YOURS_TO_SEND = 'Asking for a briefing sends nothing by itself: it freezes the briefing question with this Magnet’s collected records as its evidence — together with anything you have selected, declared or carried over for this question — and carries it into this Magnet’s Conversation, where you choose who answers it and press Send. The answer standing above is unchanged until a reply is frozen in its place.'
/** Said where a briefing written by a run is shown, about what the record
 *  checked before it accepted it. Deliberately not a grounding claim: what an
 *  answer was allowed to reach is `Grounded`'s to state, from the provenance
 *  the answer itself records.
 *
 *  IT SAYS THE CHECKS THAT WERE MADE, AND THEIR LIMITS. It used to say the
 *  record had checked that what the run could reach was EXACTLY the frozen
 *  package and nothing else. Reconciliation compares the enumeration of what
 *  Mentis OFFERED the run (`artifacts.available`), not every read it made and
 *  not its runtime's own tools; and the boundary admits this Magnet's own
 *  Conversation posts and its own held packages besides
 *  (`mentis/magnet/scope.py`). A disposable-Brain probe appended an own-
 *  Conversation post and an own-Magnet record after freezing, served both
 *  through the worker door, and reconciliation still qualified -- so the old
 *  sentence was false as written (review `ent-5acd177f3aa8` F5). Nor does
 *  finalization read a single statement against its records. */
export const BRIEFING_BY_RUN = 'Written by a run this Magnet handed its frozen collection to. Before the reply was frozen as this answer, the record checked that it came from the run this question was actually sent to, that every record in the frozen package was offered to that run, and that nothing beyond that package and what you declared with it was offered to it. That is an accounting of what this Magnet offered, not of everything the run read: within the boundary a run may also read this Magnet’s own Conversation and the packages this Magnet holds, and whatever its own tools reached is recorded where it says so rather than checked. Nothing checked the answer statement by statement — what each was written from is said beside it, and “Grounding not recorded” means it recorded none.'
/** Said when the frozen words of such an answer cannot be read. Nothing is
 *  shown in their place. */
export const BRIEFING_UNREAD = 'The answer standing against this Magnet’s kept question was written by a run, and its frozen words could not be read, so none of them are shown here. It is unchanged under this Magnet’s kept question.'
/** Said where the record will not qualify a frozen answer for reading NOW.
 *  The published contract is explicit that an immutable answer version is not
 *  perpetual qualification and that a fresh display receipt is obtained before
 *  it is shown (`docs/magnets/part-b-perspectives-api.md`), so a reader that
 *  shows the bytes on the strength of their digest alone has checked integrity
 *  and not qualification (review `ent-5acd177f3aa8` F4). */
export const BRIEFING_NOT_QUALIFIED = 'The record read this answer’s evidence again and does not qualify it for reading now, so none of its words are shown.'
/** Said where the written floor was NOT written over a briefing. */
export const BRIEFING_STANDS = 'A briefing written by a run stands as this Magnet’s answer. Nothing was written over it: ask for a written answer or another briefing when you want one.'
/** Said where the owner's own words arrived while the question was being
 *  frozen. They are kept exactly as typed and nothing is sent. */
export const BRIEFING_OWN_WORDS_KEPT = 'Words of your own were written while the briefing question was being frozen, so they were left exactly as they are and nothing was written over them. The briefing question is frozen and kept: keep or clear your own words, then ask again to carry it into the Conversation.'
/** Said where an earlier briefing question of the owner's was never answered,
 *  so `prepare` returns that original intent rather than freezing a second
 *  one. Keeping it is right; presenting it as a fresh freeze of the collection
 *  shown is not (review F3). */
export const BRIEFING_RESUMED = 'An earlier briefing question of yours has never been answered, so that original request — not a new one — is what was carried into the Conversation, with the evidence it was frozen with. Nothing was frozen a second time.'
/** Said beside an answer whose own collection is not the one on the surface --
 *  a briefing read out of its frozen manifest, or a written one out of what
 *  the record put on it. The answer is preserved either way
 *  (`needsWrittenAnswer`); what must not happen is the surface claiming it was
 *  written from what is shown beside it (review F6). */
export const BRIEFING_FROM_EARLIER = 'This answer was written from an earlier collection of this Magnet, not the one shown here. Nothing collected since has been written into it: ask again from the collection shown when you want an answer that has read it.'
/** Said where this surface cannot tell which collection a briefing was written
 *  from -- so it claims neither. */
export const BRIEFING_COLLECTION_UNKNOWN = 'Which collection this briefing was written from has not been read here, so it is not claimed to be the one shown.'

/** WHAT WAS ACTUALLY FROZEN AND HANDED OVER, so the surface can say it rather
 *  than repeat what the press intended. `collection` is the collection on the
 *  surface where the frozen package really holds it, and null where it does
 *  not -- a resumed intent holds the one it was frozen with. */
export interface BriefingFrozen {
  intent: string
  question: string
  revision: string
  manifest: string
  records: number
  collection: string | null
  resumed: boolean
  inherited: { priors: number; declared: number; selected: number; continuation: boolean }
}

/** WHAT WENT INTO THE FROZEN REQUEST, counted from the request itself. Said
 *  after the press instead of a promise made before it: the evidence a
 *  Perspective question carries is the collection AND whatever that question
 *  already carried, and a reader cannot see the difference unless it is
 *  stated (review `ent-5acd177f3aa8` F3). */
export function briefingFrozenWords(got: BriefingFrozen): string {
  const n = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`
  const carried = [
    got.inherited.selected ? n(got.inherited.selected, 'collected record you had selected', 'collected records you had selected') : '',
    got.inherited.declared ? n(got.inherited.declared, 'record you declared for this question', 'records you declared for this question') : '',
    got.inherited.priors ? n(got.inherited.priors, 'earlier answer to read as an interpretation', 'earlier answers to read as interpretations') : '',
    got.inherited.continuation ? 'what has been said about this question in this Magnet’s Conversation' : '',
  ].filter(Boolean)
  return [`Frozen and waiting in this Magnet’s Conversation: ${n(got.records, 'record', 'records')} in all,`,
    got.collection ? 'written from the collection shown here.' : 'written from the collection it was frozen with, which is not the one shown here.',
    carried.length ? `Carried with it: ${carried.join('; ')}.` : 'Nothing else is carried with it.',
    'Choose who answers it and press Send.'].join(' ')
}

/** ASK AN AGENT FOR THE BRIEFING. Three durable writes, in this order, each of
 *  them the owner's press: the standing question is made the active one (so the
 *  chip the composer checks is that question), its words are frozen as this
 *  wording of it, and the immutable input package is prepared from the
 *  collection in hand. Then the frozen ask is carried into the Conversation.
 *  Nothing is dispatched.
 *
 *  THE OWNER'S OWN UNSENT WORDS SURVIVE IT. Checked twice, and the second
 *  check is the one that matters: words typed during the waits above were read
 *  before them and replaced after, so the first check alone lost them (review
 *  `ent-5acd177f3aa8` F1). The composer is read again at the moment its text
 *  would be replaced, and different words refuse there -- with the frozen
 *  request kept, so asking again after keeping or clearing them resumes that
 *  same request rather than freezing a second one.
 *
 *  AND WHAT IT HANDS OVER CAN ACTUALLY BE SENT. The chip beside the words
 *  stands for this question at the wording that was actually frozen
 *  (`restampAttachedQuestion`), which is what the send compares against a
 *  fresh durable read; the record's own wording has to agree with the frozen
 *  one, or the frozen request cannot be sent as it stands and that is said
 *  instead of handed over (review F2). */
export async function askForBriefing(resource: MagnetResource, store: PerspectiveStore): Promise<BriefingFrozen> {
  const batch = resource.snapshot().activation?.artifact.ref
  if (!batch)
    throw new Error('Collect something first. A briefing is written from this Magnet’s collected records, and there are none.')
  const held = miniComposerDraft(resource)
  const earlier = store.snapshot().active
  if (held.text.trim() && held.text !== BRIEFING_ASK
    && (!earlier?.requestInstructions || held.text !== briefingRequest(earlier.text)))
    throw new Error('The Conversation Composer already holds different words of yours. Keep or clear them before asking for a briefing.')
  const topic = await store.ensureStanding()
  if (store.snapshot().selected !== topic) await store.select(topic)
  /* WHAT THIS QUESTION ALREADY CARRIES, counted before it is frozen with it:
     `prepare` sends the store's selections, declarations, priors and
     continuation whatever else is in hand, and this press neither clears them
     nor may claim they are not there. */
  const before = store.snapshot()
  const inherited = {
    priors: before.priors.length,
    declared: before.declared.length,
    selected: resource.snapshot().results.filter((r) => before.selections[r.id]).length,
    continuation: before.continuation === true,
  }
  const saved = await store.ordinaryContext()
  if (!saved || saved.perspective !== topic)
    throw new Error('The active question changed before the briefing was frozen. Nothing was sent.')
  const prepared = { ...await store.prepare(saved.question, `magnet-briefing:${resource.saved.id}:${crypto.randomUUID()}`),
    requestInstructions: saved.question.endsWith(BRIEFING_INSTRUCTIONS) ? '' : BRIEFING_INSTRUCTIONS }
  store.update({ active: prepared })
  const resumed = store.snapshot().resumed === true
  // The record's own current wording, read fresh: the sent Turn has to begin
  // with the question as the record holds it (`perspectives_work.bind`), and
  // the chip the send checks has to stand for that same wording.
  const context = await store.ordinaryContext()
  if (!context || context.perspective !== topic)
    throw new Error('The active question changed while the briefing was being frozen. The frozen request is kept; nothing was sent.')
  if (!prepared.question?.ref || context.revision !== prepared.question.ref)
    throw new Error('This Magnet’s kept question is not at the wording the briefing request was frozen with, so that request cannot be sent as it stands. It is kept, and nothing was sent.')
  const now = miniComposerDraft(resource)
  if (now.text !== held.text && now.text.trim() && now.text !== briefingRequest(prepared.text))
    throw new Error(BRIEFING_OWN_WORDS_KEPT)
  /* THE CHIP IS THIS QUESTION, AT THE WORDING FROZEN. The press promises to
     carry the frozen ask into the Conversation, and the send only carries it
     while the chip names this question (`ComposerBar.beforeRequest`), so the
     chip is attached here as the explicit choice this press is -- then made to
     stand for the frozen wording rather than whichever one it stood for
     before. */
  showPerspectiveContext(resource, topic, context.name)
  restampAttachedQuestion(resource, topic, prepared.question)
  saveMiniComposer(resource, { ...now, text: briefingRequest(prepared.text) })
  focusMiniComposer()
  goTab(resource, 'Conversation')
  setOpen(resource, true)
  /* WHICH COLLECTION THE PACKAGE REALLY HOLDS. A question frozen here was
     frozen with the collection this press passed to `prepare`, so that one is
     certain. A RESUMED intent was frozen with whatever was in hand then, and
     is only the collection shown if the package itself names it. */
  const sameCollection = !resumed || prepared.artifacts.some((a) => a.ref === batch)
  return { intent: prepared.intent, question: prepared.text, revision: prepared.question.ref,
    manifest: prepared.manifest.ref,
    records: prepared.closure?.count ?? prepared.artifacts.length,
    collection: sameCollection ? batch : null,
    resumed, inherited }
}

/** WHETHER A RECORDED ANSWER WAS WRITTEN BY A RUN rather than by the Python
 *  synthesis, decided from the two fields only `finalize` records: the reply
 *  Turn it was frozen from and the execution that produced it
 *  (`perspectives_work.finalize`). The synthesis records neither. */
export function agentWritten(e?: InquiryEvent | null): boolean {
  const d = object(e?.data)
  return typeof d.answer_post === 'string' && !!d.answer_post && typeof d.execution === 'string' && !!d.execution
}

/** The held package an answer event stands for, where it names one exactly. */
export function heldAnswer(e?: InquiryEvent | null): { ref: string; digest: string; size: number } | null {
  const held = object(object(e?.data).answer)
  return typeof held.ref === 'string' && /^[0-9a-f]{64}$/.test(held.digest ?? '') && Number.isInteger(held.size)
    ? { ref: held.ref, digest: held.digest, size: held.size } : null
}

/** The words a frozen answer package holds: its reply's own text parts, in the
 *  order they were frozen. Nothing is characterised, shortened or joined with
 *  anything else -- a briefing is read as the document it was written as. */
export function frozenWords(pkg: unknown): string {
  return joinedWords(object(pkg).parts)
}

/** The text of a reply's parts, in the order they were frozen. */
function joinedWords(parts: unknown): string {
  return (Array.isArray(parts) ? parts : [])
    .filter((p) => object(p).type === 'text' && typeof object(p).text === 'string')
    .map((p) => String(object(p).text).replace(/\s+$/, ''))
    .filter((t) => !!t.trim()).join('\n\n')
}

/* ---------------------------------------------------------------------------
   WHICH CHARACTERS OF THE FROZEN REPLY MENTIS ADDED, AS THE RECORD SAYS.

   Where a run makes an outcome claim, Mentis renders it onto the reply text
   itself ("Claim by @X: met — … (the agent's claim; …)"). It is execution
   bookkeeping, not the answer, and until the reply boundary existed nothing
   said where it began -- so this file recognised it by its WORDING
   (`CLAIM_TRAILER`), which is a guess about how Mentis phrases itself.

   It is now MEASURED, by the boundary that writes the reply
   (`mentis/web/dispatch.py`), recorded on the reply's `turn-said` act and
   carried into the frozen answer package by `perspectives_work.finalize`:
   `said_span` is the run's own words, `appended` the spans Mentis added. Read
   here, both of them, so the cut is by offset and not by phrase.

   NOT TRUSTED BLINDLY. The package verifies by size and digest, which says
   the bytes are the frozen ones and nothing about whether an offset addresses
   them; a span that does not fit the parts in hand is ignored, never clamped.
   And where the record carries no boundary -- every answer frozen before this
   -- the wording recogniser is still used, so an older answer reads exactly
   as it did. ------------------------------------------------------------- */

/** One recorded span of a frozen reply: a part, and characters of its text. */
interface Span { part: number; start: number; end: number }

/** `v` as a span of `parts`, or `null` where it does not address their
 *  characters. */
function spanOf(v: unknown, parts: unknown[]): Span | null {
  const s = object(v)
  const [part, start, end] = [s.part, s.start, s.end]
  if (![part, start, end].every((n) => Number.isInteger(n))) return null
  if (part < 0 || part >= parts.length) return null
  const held = object(parts[part])
  if (held.type !== 'text' || typeof held.text !== 'string') return null
  return start >= 0 && start <= end && end <= held.text.length
    ? { part, start, end } : null
}

/** THE RUN'S OWN WORDS OF A FROZEN ANSWER, and whether the record measured
 *  them.
 *
 *  `bounded` is the whole point: it says the cut below was made by recorded
 *  offsets, so nothing downstream has to recognise Mentis's wording. It is
 *  `false` for an answer frozen before the boundary was recorded, and false
 *  where cutting by the boundary would leave no words at all -- an answer that
 *  is nothing but Mentis's trailer is shown as what it is, the same way an
 *  answer that is nothing but narration is, rather than as an empty card. */
export function frozenAnswerWords(pkg: unknown): { words: string; bounded: boolean } {
  const held = object(pkg)
  const parts = Array.isArray(held.parts) ? (held.parts as unknown[]) : []
  const whole = joinedWords(parts)
  const said = spanOf(held.said_span, parts)
  const appended = (Array.isArray(held.appended) ? held.appended : [])
    .map((a) => spanOf(a, parts)).filter((a): a is Span => !!a)
  if (!said && !appended.length) return { words: whole, bounded: false }
  /* Both constraints, on the characters they each name: the part `said_span`
     names is narrowed to it, and every span Mentis appended is taken out of
     its own part. For a fallback reply the two say the same thing from either
     end; applying both never reads a character neither side claims. */
  const kept = parts.map((p, i) => {
    const o = object(p)
    if (o.type !== 'text' || typeof o.text !== 'string') return p
    let text: string = o.text
    let from = 0
    if (said && said.part === i) { from = said.start; text = text.slice(said.start, said.end) }
    for (const cut of appended.filter((a) => a.part === i).sort((a, b) => b.start - a.start)) {
      const [s, e] = [cut.start - from, cut.end - from]
      if (e <= 0 || s >= text.length) continue
      text = text.slice(0, Math.max(s, 0)) + text.slice(Math.min(e, text.length))
    }
    return { ...o, text }
  })
  const words = joinedWords(kept)
  return words.trim() ? { words, bounded: true } : { words: whole, bounded: false }
}

/* ---------------------------------------------------------------------------
   AN ANSWER IS THE ANSWER, NOT THE WORK OF WRITING IT (owner
   `ent-bce57ba67f38`: "Summary and Perspectives should present substantive,
   readable synthesized information, not agent narration, collection history,
   execution details or internal instructions ... display the final answer, not
   intermediate agent commentary").

   WHAT WAS WRONG. A run's reply is frozen verbatim
   (`perspectives_work.finalize`), and a model's reply commonly opens by saying
   what it is about to do. The owner's own Magnet opened its briefing with
   "I'll read the frozen question, collection records, manifest, and evidence,
   then trace the briefing's claims…" -- a sentence about the agent's work,
   standing where the answer's first sentence belongs, in the lead type.

   WHAT IS DONE ABOUT IT, AND WHERE. Nothing is edited in the record: the
   frozen package is what it is, it still verifies byte for byte, and "View the
   recorded answer" still opens exactly what was frozen. This is a READING
   rule, applied where the words are read for display, and it is deliberately
   the narrowest one that fixes what the owner read:

     - only LEADING runs of prose, before the answer's own content;
     - only a sentence that OPENS as narration of the agent's own work -- "I'll
       …", "Let me …", "I will …", "My plan …", optionally after a filler such
       as "Okay," or "First,";
     - a paragraph that is not plain prose (a heading, a list, a table, a
       fence, a quotation) ENDS the scan, whatever it says;
     - and if the strip would leave nothing at all, nothing is stripped: an
       answer that is only narration is shown as the answer it is, so the
       reader sees the problem rather than an empty card.

   SEAM. The clean fix is server-side -- `finalize` could freeze the answer
   without the preamble, or record where the answer begins. That is
   `mentis/magnet/perspectives_work.py`, which this part does not own, so this
   is the client-side strip the hand-off asked for as the stopgap.

   AND THE SENTENCES THAT MEET WITH NO CHARACTER BETWEEN THEM. Read back off
   TEST's own running candidate, the reply Turn this answer was frozen from
   holds ONE text part of 5155 characters in which the agent's blocks are
   already fused: "...the exact retained sources.The collection combines...",
   "...not present in the frozen rows.The collection's strongest theme...".
   `finalize` freezes `turns[0]["body"]["parts"]` verbatim, so it is faithful;
   the fusion is older than Mentis's Turn, in whatever assembled the reply's
   blocks into one part. That is a SEAM for whoever owns the reply path, and
   it is reported as one -- but the owner is reading the result now, so the
   missing character is restored for DISPLAY (`unfused`), and only ever the
   one space that is missing. ---------------------------------------------- */

/** TWO SENTENCES WITH NOTHING BETWEEN THEM, and the narrowest repair there is:
 *  the space that is missing. Not a paragraph break -- a break inside a list
 *  item or a table row would take apart a construct the author wrote, where a
 *  space cannot.
 *
 *  BOUNDED SO THAT ONLY A DEFECT MATCHES. A terminal mark with at least two
 *  lower-case letters in front of it and a capital followed by a lower-case
 *  letter behind it, and no whitespace at all: `sources.The`. A version, a
 *  decimal, an abbreviation (`U.S.`), a dotted word in capitals (`x.ORG`) and
 *  an address (`example.com/path`) all fail one of those. A dotted identifier
 *  written as prose rather than as code (`data.Text`) would match, which is
 *  why source is exempt below: it is the one place such a token belongs. */
const FUSED = /(?<=\p{Ll}\p{Ll})([.!?])(?=\p{Lu}\p{Ll})/gu

/** A line of fenced or indented source, which is shown as the characters it
 *  is and never repaired. */
const FENCE_LINE = /^ {0,3}(`{3,}|~{3,})/

/** Running prose outside any code, with the missing space restored. Inline
 *  code spans, fenced blocks and indented blocks are left exactly as written;
 *  headings, lists and tables keep their own shape, because nothing but a
 *  space is ever inserted. */
export function unfused(words: unknown): string {
  const src = typeof words === 'string' ? words : ''
  const out: string[] = []
  let fence: string | null = null
  for (const line of src.split('\n')) {
    const f = FENCE_LINE.exec(line)
    if (fence !== null) {
      out.push(line)
      if (f && line.trim().startsWith(fence)) fence = null
      continue
    }
    if (f) { fence = f[1]; out.push(line); continue }
    if (/^ {4,}/.test(line)) { out.push(line); continue }
    out.push(line.split(/(`[^`]*`)/).map((p, i) => i % 2 ? p : p.replace(FUSED, '$1 ')).join(''))
  }
  return out.join('\n')
}

/** A paragraph that is running prose, and so can carry a narrated sentence. A
 *  heading, a quotation, a list item, a numbered item, a table row and a fence
 *  are none of those, and stop the scan rather than being read for narration. */
const NOT_PLAIN_PROSE = /^(?:#{1,6}\s|>|[-*+]\s|\d+[.)]\s|\||`{3,}|~{3,}|\s{4})/

/** HOW AN AGENT OPENS A SENTENCE ABOUT ITS OWN WORK. First person and a verb
 *  of intention or of procedure -- never merely first person, because an
 *  answer may legitimately say "I found no record of it". Optional fillers in
 *  front, which is how the same sentence arrives with "Okay," or "First," on
 *  it. */
const NARRATES = new RegExp(
  '^(?:(?:ok(?:ay)?|alright|right|sure|certainly|first(?:ly)?|next|then|now|finally)\\b[\\s,.:;—–-]*)*' +
  '(?:i\\s?[\'’]\\s?(?:ll|ve|m|d)\\b' +
  '|i\\s+(?:will|am|have|shall|plan|intend|need|should|plan)\\b' +
  '|let\\s+me\\b|let\\s?[\'’]\\s?s\\b' +
  '|my\\s+(?:plan|approach)\\b' +
  '|here\\s?[\'’]\\s?s\\s+(?:my|the)\\s+(?:plan|approach)\\b)', 'i')

/** Where the first sentence of a run of prose ends. A terminal mark (or an
 *  ellipsis), the marks that close around it, then whitespace -- or the end of
 *  the run, in which case the whole run is that one sentence. */
const SENTENCE_END = /[.!?…]["'”’)\]]*\s/

/** `para` with its leading narrated sentences taken off; `''` where the whole
 *  paragraph is narration. Nothing else is touched: the sentence that opens
 *  the answer comes back with its own characters. */
function withoutNarratedSentences(para: string): string {
  let rest = para.trim()
  while (rest && NARRATES.test(rest)) {
    const m = SENTENCE_END.exec(rest)
    if (!m) return ''
    rest = rest.slice((m.index ?? 0) + m[0].length).trimStart()
  }
  return rest
}

/** THE OUTCOME TRAILER MENTIS APPENDS TO A RUN'S REPLY, recognised by the
 *  parenthetical it always closes with. It is the run's recorded claim and its
 *  evidence references -- execution detail about the work, not the answer to
 *  the question -- and the owner named exactly that among what should not be
 *  on these surfaces. It is the last paragraph of the frozen reply, it is
 *  still in the record, and "View the recorded answer" still opens the whole
 *  of what was frozen. */
const CLAIM_TRAILER = /\n[ \t]*\n[^\n]*\(the agent's claim; what Mentis recorded is shown with the work\)[ \t]*$/

/** `src` with its leading narration taken off, or `src` where there is none or
 *  where taking it off would leave nothing. */
function withoutLeadingNarration(src: string): string {
  let rest = src.replace(/^\s+/, '')
  for (;;) {
    const cut = rest.search(/\n[ \t]*\n/)
    const para = cut < 0 ? rest : rest.slice(0, cut)
    const after = cut < 0 ? '' : rest.slice(cut).replace(/^\s+/, '')
    if (NOT_PLAIN_PROSE.test(para)) break
    const kept = withoutNarratedSentences(para)
    if (kept === para.trim()) break
    /* The paragraph's remainder is the answer's own opening: stop there. */
    if (kept) { rest = after ? `${kept}\n\n${after}` : kept; break }
    if (!after.trim()) return src
    rest = after
  }
  return rest.trim() || src
}

/* ---------------------------------------------------------------------------
   AND THE SAME AT THE CLOSE (owner `ent-bce57ba67f38`, read again on the
   narration strip's own screenshots: "not agent narration, collection
   history, execution details or internal instructions").

   WHAT IS STILL WRONG. A reply that opens by saying what it is about to do
   also commonly closes by saying what it did -- and on the owner's own Magnet
   that closing paragraph is addressed to whoever evaluates the run, not to
   the owner reading the Magnet: "The frozen question for Topic
   `ent-85f547319077` is answered here and in the returned briefing,
   `adm-3cfefbd3d5ad`. The cited versions and byte ranges identify the
   retained collection text. All configured sources in the extract returned
   successfully ... Nothing is required from the owner." It exposes bare
   reference ids as reading matter and is bookkeeping about the work, which is
   exactly what the owner named.

   SO THE SAME READING RULE, FROM THE OTHER END, and as narrow:

     - only TRAILING runs of prose, after the answer's own content (the claim
       trailer is taken off first, so this paragraph is then the last one);
     - only a paragraph that is RECOGNISABLY this pattern: plain prose that
       both names a bare reference id AND is written in the bookkeeping
       phrases below. Either alone is not enough -- an answer's own paragraph
       cites records by reference, and prose may legitimately mention a source
       or the owner;
     - inside such a paragraph, only its trailing bookkeeping sentences;
     - a paragraph that is not plain prose ENDS the scan, whatever it says;
     - and if the strip would leave nothing at all, nothing is stripped.

   SEAM, the same one: the clean fix is that the reply's answer and its
   closing report to the evaluator are not one frozen run of prose, in
   `mentis/magnet/perspectives_work.py`, which this part does not own. ----- */

/** A BARE RECORD REFERENCE WRITTEN AS PROSE -- this record's own id shapes,
 *  optionally in backticks. Not reading matter for the owner, and the first
 *  half of the pattern recognised below. */
const BARE_REFERENCE = /\b(?:ent|adm|opr|def)-[0-9a-f]{12}\b/

/** HOW A RUN WRITES ITS CLOSING BOOKKEEPING, by the phrases it is actually
 *  written in: whether the frozen question is answered, which briefing was
 *  returned, whether the configured sources returned, what the citations
 *  identify, and whether anything is wanted from the owner. Named phrases,
 *  never a guess at the subject, so that an answer which merely talks about
 *  sources or about the owner is left exactly as it was written. */
const BOOKKEEPS = new RegExp([
  'frozen question', 'returned briefing', 'frozen evidence',
  'return(?:ed|s|ing)\\s+successfully', 'byte ranges?',
  'nothing (?:is|was) (?:required|needed|asked)',
  '(?:required|needed|asked) (?:from|of) the owner',
].join('|'), 'i')

/** The sentences of a run of prose, in order, each keeping the characters and
 *  the spacing it was written with, so that joining a prefix of them back
 *  together returns the author's own text. */
function sentencesOf(para: string): string[] {
  const out: string[] = []
  let rest = para
  for (;;) {
    const m = SENTENCE_END.exec(rest)
    if (!m) { if (rest.trim()) out.push(rest); return out }
    const at = (m.index ?? 0) + m[0].length
    out.push(rest.slice(0, at))
    rest = rest.slice(at)
  }
}

/** A sentence of an already-recognised bookkeeping paragraph that is part of
 *  that bookkeeping: written in one of its phrases, or there to name a bare
 *  reference id. */
const bookkeeps = (sentence: string) => BOOKKEEPS.test(sentence) || BARE_REFERENCE.test(sentence)

/** `para` with its trailing bookkeeping sentences taken off; `''` where the
 *  whole paragraph is bookkeeping. */
function withoutBookkeepingSentences(para: string): string {
  const parts = sentencesOf(para)
  let end = parts.length
  while (end > 0 && bookkeeps(parts[end - 1])) end -= 1
  return parts.slice(0, end).join('').trim()
}

/** `src` with a trailing run of closing bookkeeping taken off, or `src` where
 *  there is none or where taking it off would leave nothing. */
function withoutClosingBookkeeping(src: string): string {
  let rest = src.replace(/\s+$/, '')
  for (;;) {
    let at = -1
    let len = 0
    for (const m of rest.matchAll(/\n[ \t]*\n\s*/g)) { at = m.index ?? 0; len = m[0].length }
    const para = at < 0 ? rest : rest.slice(at + len)
    const before = at < 0 ? '' : rest.slice(0, at)
    if (NOT_PLAIN_PROSE.test(para)) break
    /* RECOGNISABLY THE PATTERN, or this paragraph is the answer's own close. */
    if (!(BARE_REFERENCE.test(para) && BOOKKEEPS.test(para))) break
    const kept = withoutBookkeepingSentences(para)
    if (kept === para.trim()) break
    /* What is left of the paragraph is the answer's own ending: stop there. */
    if (kept) { rest = before ? `${before}\n\n${kept}` : kept; break }
    if (!before.trim()) return src
    rest = before.replace(/\s+$/, '')
  }
  return rest.trim() || src
}

/** A RECORDED ANSWER'S OWN WORDS, with a leading narration of the agent's
 *  work, a trailing claim trailer and a trailing run of closing bookkeeping
 *  left out of what is drawn. Returns the input unchanged where there is none
 *  of those, and where taking one out would leave nothing.
 *
 *  The fused sentences are separated first (`unfused`): on TEST's own answer
 *  the narrated sentence and the answer's first sentence are ONE run of
 *  characters with no space between them, so until the space is there the end
 *  of the narration cannot be found at all.
 *
 *  `measured.appended` says Mentis's own appended characters were already cut
 *  by the offsets the record holds (`frozenAnswerWords`). Then the wording
 *  recogniser is not consulted at all: a trailer the agent happened to quote
 *  in its own answer is the agent's words and stays, and a rendering Mentis
 *  rephrases later still goes. Without it the wording is the only thing there
 *  is, and is used exactly as before. */
export function withoutNarration(words: unknown, measured?: { appended?: boolean }): string {
  const whole = unfused(words)
  const cut = measured?.appended ? whole : whole.replace(CLAIM_TRAILER, '')
  const src = cut.trim() ? cut : whole
  if (!src.trim()) return src
  const opened = withoutLeadingNarration(src)
  const closed = withoutClosingBookkeeping(opened)
  return closed.trim() ? closed : opened
}

/** READ THE FROZEN WORDS OF AN ANSWER A RUN WROTE.
 *
 *  `finalize` records the reply as an immutable package and the reply Turn it
 *  came from; it does not record the words on the event the way the synthesis
 *  does (`data.text`), so a briefing has nothing to show until the package
 *  itself is read. It is read through the one artifact door this card already
 *  reads a frozen manifest through, and verified the same way -- exact size,
 *  exact digest -- so what is shown is the frozen answer and never a
 *  substitute. Where the event does record `text` (an answer written by the
 *  synthesis, or by a later build that records it), that is used and nothing is
 *  fetched.
 *
 *  THE WORDS READ ARE THE ANSWER'S, not the account of writing it: a leading
 *  narration is left out of what is drawn (`withoutNarration`), on both paths,
 *  because this is the one door both surfaces read an agent-written answer
 *  through. The frozen bytes are still verified whole before anything of them
 *  is read, and the recorded package is unchanged.
 *
 *  AND MENTIS'S OWN APPENDED CHARACTERS GO BY THE OFFSETS THE RECORD HOLDS
 *  where the package carries them (`frozenAnswerWords`), rather than by
 *  recognising how Mentis phrases its claim rendering. An answer frozen before
 *  the boundary was recorded carries none, and reads exactly as it did. */
export async function readFrozenAnswer(e: InquiryEvent): Promise<string> {
  const recorded = answerText(e)
  if (recorded) return withoutNarration(recorded)
  const held = heldAnswer(e)
  if (!held) throw new Error('This answer names no frozen record of its own words.')
  const r = await fetch(`/api/artifacts/${encodeURIComponent(held.ref)}`, { headers: CLIENT_HEADERS, cache: 'no-store' })
  if (!r.ok) throw new Error('The frozen answer is unavailable. Nothing was substituted for it.')
  const raw = new Uint8Array(await r.arrayBuffer())
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))].map((n) => n.toString(16).padStart(2, '0')).join('')
  if (raw.byteLength !== held.size || digest !== held.digest)
    throw new Error('The frozen answer did not verify against the record. Nothing of it is shown.')
  const read = frozenAnswerWords(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw)))
  if (!read.words) throw new Error('The frozen answer holds no words to read.')
  return withoutNarration(read.words, { appended: read.bounded })
}

/** THE BRIEFING AS THIS VIEW MAY ACTUALLY SHOW IT: its words, and the
 *  collection it was really written from. */
export interface StandingBriefing { post: string; words: string; collection: string[] }

/** READ THE BRIEFING STANDING NOW -- QUALIFIED FIRST, AND KNOWING ITS OWN
 *  COLLECTION.
 *
 *  Three things in this order, because each is a condition of the next:
 *
 *  1. A FRESH DISPLAY RECEIPT for this answer's own frozen question and the
 *     run that produced it (`store.displayReceipt`). The contract says an
 *     immutable answer version is not perpetual qualification and that a
 *     receipt is appended before a display; a size-and-digest check is
 *     integrity, not current qualification, so reading the bytes on its
 *     strength alone showed a historically frozen reply as the standing answer
 *     even where a fresh check would not qualify it (review F4). Anything but
 *     `qualified` shows nothing of the answer's words.
 *  2. WHICH COLLECTION IT WAS WRITTEN FROM, out of its own frozen manifest --
 *     `finalize` records no collection on the answer event, which is why this
 *     view could show a briefing written from an earlier collection beside the
 *     facts and excerpts of the one on screen without saying so (review F6).
 *     The manifest is read and verified through the store's own door.
 *  3. THE FROZEN WORDS, as before.
 *
 *  All three are reads of named records, started by the answer standing now
 *  being one whose words its event does not carry. The receipt is the one
 *  durable append, and it is the append the contract asks for. */
export async function readStandingBriefing(store: PerspectiveStore, e: InquiryEvent): Promise<StandingBriefing> {
  const d = object(e.data)
  const topic = e.perspective
  const intent = typeof d.intent === 'string' ? d.intent : ''
  const execution = typeof d.execution === 'string' ? d.execution : ''
  if (!topic || !intent || !execution)
    throw new Error('This answer does not name the frozen question and the run it was accepted for, so the record cannot be asked whether it qualifies now.')
  const receipt = await store.displayReceipt(topic, intent, execution)
  const status = typeof object(receipt).status === 'string' ? String(object(receipt).status) : 'unknown'
  if (status !== 'qualified') throw new Error(`${BRIEFING_NOT_QUALIFIED} The record says: ${status}.`)
  const held = await store.get(`/${topic}/intents/${encodeURIComponent(intent)}`)
  const prepared = object(held).prepared as PreparedInquiry | undefined
  if (!prepared || prepared.intent !== intent)
    throw new Error('The frozen question this answer was written for could not be read, so the collection it was written from is unknown.')
  const manifest = object(await store.manifest(prepared))
  const collection = (Array.isArray(manifest.batches) ? manifest.batches : [])
    .map((b: unknown) => object(b).ref)
    .filter((ref: unknown): ref is string => typeof ref === 'string' && !!ref)
  return { post: e.post, words: await readFrozenAnswer(e), collection }
}

/** WHETHER THE BRIEFING STANDING NOW WAS WRITTEN FROM THE COLLECTION SHOWN.
 *  `null` where this view has not read which collection it was written from,
 *  so that neither statement is made (review F6). */
export function writtenFromShown(got: StandingBriefing | null, post: string | undefined,
                                 batch: string | undefined): boolean | null {
  if (!got || !post || got.post !== post || !batch) return null
  return got.collection.includes(batch)
}

/** WHETHER THE WRITTEN FLOOR IS STILL OWED FOR THE COLLECTION IN HAND.
 *
 *  It is owed where the record holds no answer written from this collection --
 *  which is what the one write per observed collection answers. It is NOT owed
 *  where a run's briefing stands: `finalize` records no collection on its
 *  answer (`basis` is the synthesis's field alone), so "not for this
 *  collection" would be read of every briefing there is, and the counted
 *  answer would be written over the reasoned one on the next open. A briefing
 *  is superseded only by a press. */
export function needsWrittenAnswer(got: StandingSummary | null | undefined, batch: string): boolean {
  return !(got?.batch === batch || agentWritten(got?.current))
}

/** The answer to render: the recorded event, with the frozen words of a
 *  run-written answer put where every other part of this view already reads an
 *  answer's words (`answerText`). The recorded characters are the frozen ones;
 *  nothing else of the event is changed, so what it was grounded in, what it
 *  cites and what changed are still read from the record itself. */
export function withWords(e: InquiryEvent | null | undefined, read: { post: string; words: string } | null): InquiryEvent | null {
  if (!e) return null
  if (!read || read.post !== e.post || answerText(e)) return e
  return { ...e, data: { ...e.data, text: read.words } }
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

/* ---------------------------------------------------------------------------
   THE RECORDED ANSWER, WITH THE STRUCTURE IT WAS RECORDED WITH.

   The server writes every answer as `lines: [{text, cites:[row ids]}]` and
   records that structure on the answered event beside the joined `text`
   (`mentis/magnet/perspectives_work.py::answer`, `data["lines"]`). This view
   read only `data.text` and split it on newlines, so `cites` -- the records
   each statement was actually written from, which `_selections` has already
   validated against the retained batch -- was read NOWHERE in this directory.
   A statement whose support cannot be opened is a statement the reader has to
   take on trust, which is the opposite of what grounding it was for.

   Nothing here changes a recorded character, and nothing here invents a
   citation: a cited id that is not in the batch shown is dropped rather than
   drawn as an opening that would not open. */

export interface AnswerLine {
  /** The statement, exactly as recorded. */
  text: string
  /** The collected rows it was written from, by their recorded ids. */
  cites: string[]
}

/** An answer's statements with their citations. Falls back to the joined text
 *  split per line for an answer recorded before `lines` was written, so an
 *  older answer still renders -- with no citations, because it recorded
 *  none, and never with guessed ones. */
export function answerLines(e?: InquiryEvent | null): AnswerLine[] {
  const recorded = e?.data?.lines
  if (Array.isArray(recorded)) {
    const out: AnswerLine[] = []
    for (const line of recorded) {
      const said = object(line)
      if (typeof said.text !== 'string' || !said.text.trim()) continue
      out.push({ text: said.text.trim(),
        cites: (Array.isArray(said.cites) ? said.cites : []).filter((c: unknown): c is string => typeof c === 'string' && !!c) })
    }
    if (out.length) return out
  }
  return statements(answerText(e)).map((text) => ({ text, cites: [] }))
}

/** The one line a statement-per-line synthesis closes with, counting what it
 *  read (`mentis/magnet/perspectives_work.py::_state_of`'s fixed closing
 *  sentence, "This Magnet has gathered N records from M sources…") --
 *  recognised by its fixed lead-in, not derived from its position, so the
 *  main answer never shows it above the fold (plan Part 5) while nothing it
 *  says is lost: it is kept, among the collection's other measurements, in
 *  the facts disclosure (`answerRecordCount`, used beside `measured`). */
const RECORD_COUNT_LINE = /^This Magnet has gathered \d+ records? from /

/** `lines`, with a trailing record-count line pulled out rather than shown. */
function withoutRecordCount(lines: AnswerLine[]): AnswerLine[] {
  if (!lines.length || !RECORD_COUNT_LINE.test(lines[lines.length - 1].text)) return lines
  return lines.slice(0, -1)
}

/** The demoted record-count line's own words, for the facts disclosure --
 *  `null` where the answer is a written briefing (it does not close with
 *  one) or recorded none. */
export function answerRecordCount(e?: InquiryEvent | null): string | null {
  if (!e || isWrittenBriefing(answerText(e))) return null
  const lines = answerLines(e)
  const last = lines[lines.length - 1]
  return last && RECORD_COUNT_LINE.test(last.text) ? last.text : null
}

export interface Cited { id: string; title: string }
/** The rows a statement cites, named by their own words and in the order the
 *  statement names them. A row the batch shown does not hold is dropped: this
 *  surface opens captured copies, and nothing is substituted for one it has
 *  not got. */
export function citedRows(cites: string[], results: RouteResult[]): Cited[] {
  const by = new Map(results.map((r) => [r.id, r]))
  const out: Cited[] = [], seen = new Set<string>()
  for (const id of cites) {
    const r = by.get(id)
    if (!r || seen.has(id)) continue
    seen.add(id)
    out.push({ id, title: resultTitle(r) })
  }
  return out
}

/* ---------------------------------------------------------------------------
   THE SOURCES AN ANSWER CITES IN ITS OWN CHARACTERS, NUMBERED.

   `cites` is the structure the server records per statement, and `citedRows`
   has named those rows by their own words since Part 5. A citation the agent
   wrote INTO its sentence is the same thing said the other way round -- a held
   reference, its source digest and the captured byte range -- and it had no
   reader at all, so it arrived as 38 characters of token in the running text.

   It is read here, through the id→title mapping that already exists: the
   reference is matched to a collected row the three ways the inspection
   matches one, and what the reader is told is the row's own title and the
   clean origin and capture time the resting surfaces already use
   (`resultTitle`, `plainEvidenceOrigin`) -- no key, no digest, no bounds. The
   exact reference, digest and range stay on the element that replaced the
   token (`data-cite`) and in the record the number opens, where Inspection's
   provenance disclosure already holds Origin, Version, Captured and Bounds.
   No new data plumbing: every field drawn here was already drawn somewhere on
   this card. ----------------------------------------------------------------- */

/** Said where an answer cites a record this collection does not hold. The
 *  number is still drawn -- the sentence cited something -- and nothing is
 *  substituted for a record that is not here. */
export const CITED_NOT_HELD = 'Not in the collection shown'

/** The collected row a citation's held reference names, or null. The same
 *  three ways `Inspection` finds one, so a number that is a press opens what
 *  the press promises. */
export function citedRow(ref: string, rows: RouteResult[]): RouteResult | null {
  return rows.find((r) => r.id === ref || r.version === ref || artifactOf(r) === ref) ?? null
}

/** THE NUMBERED SOURCES OF ONE ANSWER, in the order a reader meets them across
 *  the whole of it, each named by what it is. */
export function answerSources(texts: string[], results: RouteResult[],
                              open: (id: string, from?: string) => void,
                              recorded?: unknown): SourceNote[] {
  const rows = [...results, ...retainedFiles(results)]
  const sources: { n: number; ref: string }[] = []
  const numbers = new Set<number>(), refs = new Set<string>()
  for (const value of Array.isArray(recorded) ? recorded : []) {
    const c = object(value)
    if (!Number.isSafeInteger(c.n) || c.n < 1 || typeof c.item !== 'string' || !c.item
      || numbers.has(c.n) || refs.has(c.item)) continue
    sources.push({ n: c.n, ref: c.item })
    numbers.add(c.n); refs.add(c.item)
  }
  let next = Math.max(0, ...numbers) + 1
  for (const ref of citedRefs(texts)) if (!refs.has(ref)) {
    sources.push({ n: next++, ref }); refs.add(ref)
  }
  return sources.map(({ n, ref }) => {
    const r = citedRow(ref, rows)
    if (!r) return { n, ref, title: CITED_NOT_HELD,
      detail: 'No live source was opened to show it.', open: null }
    const at = when(r.at)
    /* The site a reader recognises where the row recorded an address, and the
       clean origin otherwise -- the same choice the inspection's own heading
       line makes, and for the same reason: `plainEvidenceOrigin` carries the
       held-file key, which is exactly what the owner asked to stop reading. */
    const from = linkHost(rowLink(r)) ?? plainEvidenceOrigin(r)
    return { n, ref, title: resultTitle(r),
      detail: [from, at ? `captured ${at}` : ''].filter(Boolean).join(' · '),
      open: () => open(r.id, `cite-source-${n}`) }
  })
}

/** What the prose renderer is given for a run of citations: the numbers and
 *  names of the notes already built, and the press each number is. */
export function citationIndexOf(notes: SourceNote[], recordedNumbers = false): CitationIndex {
  const by = new Map(notes.map((s) => [s.ref, s]))
  const numbered = new Map(notes.map((s) => [s.n, s.ref]))
  return {
    refOf: (n) => recordedNumbers ? numbered.get(n) ?? null : null,
    numberOf: (ref) => by.get(ref)?.n ?? null,
    nameOf: (ref) => { const s = by.get(ref); return s && s.title !== CITED_NOT_HELD ? s.title : null },
    open: (ref) => by.get(ref)?.open?.(),
  }
}

/** WHETHER A RECORDED ANSWER IS A WRITTEN DOCUMENT rather than one statement
 *  per line, decided from the characters themselves.
 *
 *  The Python synthesis writes consecutive single-line statements, which read
 *  as one paragraph, so `isStructured` is false for it and it keeps its
 *  statement-and-quotation layout -- the layout that makes its citations
 *  pressable. A briefing written as Markdown (headings, paragraphs, lists,
 *  pipe tables) is structured, and is rendered as the document it is by the
 *  renderer Fluid already has. */
export const isWrittenBriefing = (words: string): boolean => isStructured(words)

export const WRITTEN_FROM = 'Written from'
/** What a change to a WRITTEN answer is worth saying. Its lines are not its
 *  statements, so they are not listed as if each were a thing it now says. */
export const BRIEFING_REWRITTEN = 'This answer is written as a document, and was rewritten from the collection shown. It is read whole above; the answer it superseded is kept under this Magnet’s standing question.'

/** The collected records one statement was written from, each a press that
 *  opens the captured copy inside this card -- and, where this entry is one of
 *  several that were merged into a single Markdown construct, WHICH PART of
 *  that construct the records were recorded against (`part`).
 *
 *  Without the part, a table assembled from three recorded entries shows three
 *  "Written from" lines under the whole table and nothing says which row each
 *  supports: review `ent-c0f9cca287b7` moved a citation from one entry to
 *  another and got byte-for-byte identical HTML, which makes the recorded
 *  attribution unrecoverable from the rendered surface. The part is the entry's
 *  own recorded words, shortened (`citedPart`) -- never a guess at what a
 *  source supports -- so what a reader can map is exactly what the server
 *  recorded, and a citation that moves to another entry moves its label with
 *  it. A group of one entry needs no part: its citations sit under the one
 *  thing they were recorded against. */
function Cites({ resource, cites, part }: { resource: MagnetResource; cites: string[]; part?: string }) {
  const rows = citedRows(cites, resource.snapshot().results)
  if (!rows.length) return null
  return <p className="mgd-subtle">{part ? `${part} — ` : ''}{WRITTEN_FROM}{' '}
    {rows.map((c, i) => <span key={c.id}>{i ? ' · ' : ''}
      <button type="button" className="mgd-link mgd-small" id={`cite-${c.id}`}
        onClick={() => inspect(resource, c.id, `cite-${c.id}`)}>{c.title}</button></span>)}</p>
}

/* WHICH PART OF A MERGED CONSTRUCT ONE ENTRY IS, in its own recorded words AND
   at a stated occurrence. `Row`/`Rows` for the pipe table rows an entry holds,
   `Item`/`Items` for the list items it holds, and the quoted words themselves
   for a statement or a clause of one -- the same characters the construct above
   shows, so a reader finds the row, item or phrase a citation line names by
   reading it.

   WORDS ALONE DO NOT IDENTIFY AN OCCURRENCE, which is what review
   `ent-7ca49dfd8393` showed with seven reproductions: two table rows whose
   recorded first cell is the same 66 characters label identically once cut at
   `PART_AT_MOST`, `1. Calibration completed.` and `2. Calibration completed.`
   label identically because the item's number is the list's and not the item's
   words, and a phrase a briefing repeats labels identically wherever it is
   repeated. In each, moving the group's only citation from one entry to the
   next produced byte-for-byte identical HTML, so what the server recorded could
   not be read off the surface at all.

   So every citation line in a group of more than one entry states WHICH
   RECORDED PART of that group it is -- `Part 2`, counted in the order the
   entries were recorded, which is the order their citation lines are drawn --
   and, where the reader of the assembled body can determine it, which drawn row
   or item that part produced (`Part 2, Row 3`). The part number is what makes
   every label distinct, including where an entry cites nothing and emits no
   line at all; the row or item number is what maps the label to something
   visible. Where the mapping cannot be determined the number is simply left
   out: nothing is guessed, and no label claims a position the body's own reader
   did not give.

   AND A PART NUMBER IS NOT AN OCCURRENCE, which re-review `ent-a4a90e65e3d5`
   showed with an A/B counterexample: one repeated phrase drawn three times in
   one paragraph, assembled once from three recorded entries and once from two
   (the first holding two of the occurrences), with the only citation recorded
   against `Part 2` both times -- the second occurrence in one, the third in the
   other, and byte-for-byte identical output. The part number counts RECORDED
   ENTRIES, and a recorded entry can hold more than one occurrence of its own
   words; so where the body gave no row or item to point at, the label SAYS in
   plain words that it cannot show where in the passage those words are
   (`CITED_PLACE_UNSHOWN`) rather than leaving a number to be read as a place.
   Nothing finer is inferred: the record carries the entry, not the occurrence. */
export const CITED_ROW = 'Row', CITED_ROWS = 'Rows'
export const CITED_ITEM = 'Item', CITED_ITEMS = 'Items'
export const CITED_PART = 'Part'

/** WHAT A LABEL SAYS INSTEAD OF A POSITION the assembled body did not give --
 *  a statement merged into a paragraph, or an entry whose words crossed more
 *  than one block. It states the limit of what is known, in the reader's own
 *  language, so `Part 2` is read as the recorded part it is and not as the
 *  second of anything drawn. */
export const CITED_PLACE_UNSHOWN = 'its place in the passage above is not shown'

/** How much of an entry's words a label carries before it is cut at a word
 *  boundary. Long enough to identify the part among its neighbours, short
 *  enough to stay one quiet line under the construct. */
const PART_AT_MOST = 56

/** One entry's recorded words as a label: whitespace collapsed, the emphasis
 *  markers the drawn construct already shows as emphasis dropped, and a cut at
 *  a word boundary. Nothing is added, reworded or reordered. */
function shortened(words: string): string {
  const one = words.replace(/\*\*|__|`/g, '').replace(/\s+/g, ' ').trim()
  if (one.length <= PART_AT_MOST) return one
  const cut = one.slice(0, PART_AT_MOST)
  const space = cut.lastIndexOf(' ')
  return `${(space > PART_AT_MOST / 2 ? cut.slice(0, space) : cut).replace(/[\s,;:.]+$/, '')}…`
}

const quoted = (words: string): string => `“${shortened(words)}”`

/** The table rows one entry holds, each named by its own cells in the order
 *  the drawn table shows them. A header row is named only where the entry
 *  holds nothing else: where the entry carries data rows under its divider,
 *  those rows are what it is, and the header is the table's first line rather
 *  than anything a citation was recorded against. */
function rowWords(text: string): string[] {
  const lines = text.split('\n').filter((l) => l.trim())
  const rows = lines.filter((l) => isTableRow(l) && !isTableDivider(l))
  if (!rows.length) return []
  const divider = lines.findIndex((l) => isTableDivider(l))
  const data = divider < 0 ? rows : lines.slice(divider + 1).filter((l) => isTableRow(l) && !isTableDivider(l))
  return (data.length ? data : rows).map((l) => rowCells(l).filter(Boolean).join(' · '))
}

/** WHERE IN THE DRAWN GROUP one recorded entry's words are. `part` is which
 *  recorded part of the group the entry is, counted from 1 -- always known,
 *  because the group is the entries it was built from. `rows` and `items` are
 *  the first and last ordinal, counted from 1, of the drawn table rows or list
 *  items that entry's words produced, read out of the assembled body by the
 *  renderer's own reader (`placeIn`); absent where it could not be determined. */
export interface CitedPlace { part: number; rows?: [number, number]; items?: [number, number] }

const span = ([from, to]: [number, number]): string => (from === to ? `${from}` : `${from}–${to}`)

/** WHAT ONE RECORDED ENTRY IS, named by its own recorded characters and -- given
 *  its place in the group (`CitedPlace`) -- at a stated occurrence.
 *
 *  The words are the entry's rows, its items, or the statement itself; the
 *  position is the one the group's own assembled body gave them, and is left
 *  out where there was none to read. A statement merged into a paragraph has no
 *  numbered part to name, and the recorded part number is NOT a stand-in for
 *  one -- two entries of the same repeated phrase are two recorded parts
 *  whatever occurrences they produced -- so such a label states that the place
 *  is not shown (`CITED_PLACE_UNSHOWN`) beside the part it is. */
export function citedPart(text: string, place?: CitedPlace): string {
  const rows = rowWords(text)
  const read = blocksOf(text)
  const only = read.length === 1 ? read[0] : null
  const items = only?.kind === 'list' ? only.items : []
  /* An entry whose own text is neither rows nor one list can still have landed
     in a list: a continuation that finished the item above it. */
  const of = rows.length ? 'row' : items.length || place?.items ? 'item' : ''
  const where = of === 'row' ? place?.rows : of === 'item' ? place?.items : undefined
  const words = (rows.length ? rows : items.length ? items : [text]).map(quoted)
  const many = words.length > 1 || (!!where && where[1] > where[0])
  const noun = of === 'row' ? (many ? CITED_ROWS : CITED_ROW) : of === 'item' ? (many ? CITED_ITEMS : CITED_ITEM) : ''
  /* A PART WITH NO POSITION BEHIND IT says so: a bare `Row`/`Item` with no
     number, or a part number alone, is nothing a reader can map, and a number
     beside repeated words reads as an occurrence it was never counted as. The
     label carries the limit instead -- only where the entry is one part of a
     group, since a group of one is labelled with nothing at all. */
  const unshown = !!place && !where
  const position = [place ? `${CITED_PART} ${place.part}` : '', where ? `${noun} ${span(where)}` : unshown ? '' : noun]
  const stated = position.filter(Boolean).join(', ')
  return [unshown ? `${stated} (${CITED_PLACE_UNSHOWN})`.trim() : stated, words.join(', ')]
    .filter(Boolean).join(' ')
}

/** What a recorded entry's own text, read alone, leaves open for the entry
 *  right after it to continue: the kind of thing its last block is, and --
 *  for a paragraph -- whether that block's last line stops at a sentence's
 *  end or is cut off mid-construct. An entry whose own text holds more than
 *  one block (a heading followed by a paragraph) can still leave its last
 *  block open; a heading, quote, code or rule can't be continued into, so it
 *  closes whatever follows. */
type Tail =
  | { kind: 'table' }
  | { kind: 'list'; ordered: boolean; open: boolean }
  | { kind: 'para'; open: boolean }
  | null

/** Whether words stop at the end of a sentence. The terminal mark may be
 *  followed by the marks that close around it -- a quote, a bracket, or the
 *  emphasis opened before it: `**Roman is ready.**` ends its sentence, and
 *  review `ent-c0f9cca287b7` found it read as open (so it swallowed the next
 *  statement) while the identical unemphasised sentence read as closed. */
const ENDS_A_SENTENCE = /[.!?:;][*_`'"’”)\]]*$/
const endsASentence = (words: string): boolean => ENDS_A_SENTENCE.test(words.trim())

function tailOf(text: string): Tail {
  const read = blocksOf(text)
  const last = read[read.length - 1]
  if (!last) return null
  if (last.kind === 'table') return { kind: 'table' }
  if (last.kind === 'list')
    return { kind: 'list', ordered: last.ordered, open: !endsASentence(last.items[last.items.length - 1] ?? '.') }
  if (last.kind === 'para') return { kind: 'para', open: !endsASentence(last.text) }
  return null
}

/** Whether an entry is nothing but ORPHAN TABLE ROWS: every line of it is a
 *  pipe row and none is a header's divider, so `blocksOf` reads the lot as one
 *  paragraph that happens to be shaped like rows. One such line is how a
 *  table's row arrives recorded on its own; SEVERAL of them is how two rows
 *  recorded in one entry arrive, which review `ent-c0f9cca287b7` found
 *  rendering as literal pipes outside the table because a newline disqualified
 *  the fragment. An entry carrying its own divider is a table of its own, not a
 *  fragment of the one before it -- merging that one turns its header and
 *  divider into data rows. */
function isOrphanRows(text: string): boolean {
  const lines = text.split('\n').filter((l) => l.trim())
  return !!lines.length && lines.every((l) => isTableRow(l) && !isTableDivider(l))
}

/** WHAT ONE ENTRY ADDS TO THE GROUP BEFORE IT, or `null` where it adds nothing
 *  -- where it is a statement of its own rather than a fragment completing what
 *  that group left open: orphan rows under a table, a list item of the same
 *  ordering, prose continuing a sentence that was cut off.
 *
 *  AN ENTRY THAT BEGINS AS A CONTINUATION AND THEN CARRIES MORE. What decides
 *  this is the entry's FIRST block, not the whole entry: review
 *  `ent-7ca49dfd8393` recorded three real splits in which the continuing
 *  fragment arrives with another block behind it -- two orphan rows and then a
 *  concluding paragraph, a cut-off list item's rest and then the next item, half
 *  a sentence and then the next heading -- and rejecting all of them (the old
 *  `read.length !== 1`) left rows as literal pipes outside the table, restarted
 *  an ordered list at 1, and split one sentence across two paragraphs. The first
 *  block is joined the way its construct is written and THE REST OF THE ENTRY IS
 *  KEPT VERBATIM after it, its own blank lines included, so what follows is read
 *  as the blocks it was recorded as.
 *
 *  A list item continued by plain prose is the one case that needs more than a
 *  newline. `blocksOf` reads a plain line as continuing the item above it only
 *  where that line is INDENTED, and `answerLines` trims every recorded entry,
 *  so the indentation the writer used is already gone by here: review
 *  `ent-c0f9cca287b7` found such a continuation closing the list and starting a
 *  second one, numbered from 1 again. The group restores the indentation (two
 *  spaces) when it joins the fragment, which is the construct's own shape and
 *  not a recorded character altered -- the words are the recorded words. Only
 *  the continuing block is indented; a later line of the same entry is the line
 *  it was recorded as. */
function continues(tail: Tail, text: string): string | null {
  if (!tail) return null
  const read = blocksAt(text)
  const first = read[0]
  if (!first) return null
  const lines = text.split('\n')
  const head = lines.slice(0, first.end), rest = lines.slice(first.end)
  const headText = head.join('\n')
  /* The first thing after the continuing block, if the entry carries one. */
  const next = rest.find((l) => l.trim()) ?? ''
  const joined = (fragment: string[]) => `\n${[...fragment, ...rest].join('\n')}`
  if (tail.kind === 'table')
    /* A row line right after the rows would be read as this table's row too --
       including a divider, which would be drawn as data. An entry whose later
       block is a table of its own is left to be its own body. */
    return first.kind === 'para' && isOrphanRows(headText) && !isTableRow(next) ? joined(head) : null
  if (tail.kind === 'list') {
    if (first.kind === 'list') return first.ordered === tail.ordered ? joined(head) : null
    if (first.kind === 'para' && tail.open && !isOrphanRows(headText))
      return joined(head.map((l) => (l.trim() ? `  ${l.trim()}` : l)))
    return null
  }
  return tail.open && first.kind === 'para' ? joined(head) : null
}

/** WHETHER THE JOIN DID WHAT IT MEANT TO, asked of the renderer's own reader
 *  rather than of a rule about the characters: the blocks the group already had
 *  are still those blocks, none of them was swallowed, and the one at the end --
 *  the construct being continued -- is still that construct and has grown. A
 *  join the reader does not confirm is not taken, and the entry becomes its own
 *  body: the surface then shows two blocks where the writer wrote one, which is
 *  a visible shortcoming and not a corrupted table or a renumbered list. */
function absorbs(src: string, more: string): boolean {
  const was = blocksOf(src), now = blocksOf(src + more)
  if (now.length < was.length) return false
  const last = was.length - 1
  for (let i = 0; i < last; i++) if (JSON.stringify(was[i]) !== JSON.stringify(now[i])) return false
  const before = was[last], after = now[last]
  if (!before || !after || before.kind !== after.kind) return false
  if (before.kind === 'table' && after.kind === 'table')
    return after.head.join('|') === before.head.join('|')
      && after.rows.length >= before.rows.length
      && before.rows.every((row, i) => row.join('|') === after.rows[i]?.join('|'))
  if (before.kind === 'list' && after.kind === 'list')
    return after.ordered === before.ordered && after.items.length >= before.items.length
      && before.items.every((item, i) => (i === before.items.length - 1
        ? (after.items[i] ?? '').startsWith(item) : after.items[i] === item))
  if (before.kind === 'para' && after.kind === 'para') return after.text.startsWith(before.text)
  return false
}

/** WHERE ONE ENTRY'S WORDS LANDED IN THE ASSEMBLED BODY, read by comparing what
 *  the renderer's reader made of the group before this entry with what it makes
 *  of it after -- never by counting the characters of the entry itself. The
 *  rows or items the entry added are the ones the construct gained; a
 *  continuation that finished the item already there is that item. Anything the
 *  comparison does not settle leaves the entry named by its recorded part, with
 *  the label saying that the place is not shown (`CITED_PLACE_UNSHOWN`), which
 *  is honest about what is known. */
function placeIn(part: number, before: Block[], after: Block[]): CitedPlace {
  const i = Math.max(0, before.length - 1)
  const was = before[i], now = after[i]
  if (now?.kind === 'table') {
    const from = was?.kind === 'table' ? was.rows.length + 1 : 1
    return now.rows.length >= from ? { part, rows: [from, now.rows.length] } : { part }
  }
  if (now?.kind === 'list') {
    const had = was?.kind === 'list' ? was.items.length : 0
    /* An entry that FINISHED the item already there begins at that item, whether
       or not it went on to start the next one: its first words are in it. */
    const finished = had > 0 && (now.items[had - 1] ?? '').length > ((was as typeof now).items[had - 1] ?? '').length
    const from = finished ? had : had + 1
    return now.items.length >= from ? { part, items: [from, now.items.length] } : { part }
  }
  return { part }
}

/** A GROUP OF RECORDED ENTRIES THAT ARE ONE MARKDOWN CONSTRUCT.
 *
 *  `blocks.ts`'s reader takes one body at a time, so a pipe table, an ordered
 *  list or a paragraph that the server split across separate recorded entries
 *  -- each with its own citations -- loses its adjacency when each entry is
 *  handed to `Prose` on its own (review `ent-19c3c55af28c`). This groups
 *  consecutive entries only where one is nothing but a fragment continuing
 *  the one before it (an orphan table row, a list item of the same order, an
 *  unfinished sentence), and joins each fragment the way that construct is
 *  written (`continues`), so the group read as one body is the one block it
 *  was written as. Two complete statements -- the ordinary case, each ending
 *  its own sentence -- are never merged into one paragraph: nothing here
 *  implies a citation supports a statement it was not recorded against. Each
 *  entry keeps its own citations, listed in order and, in a group of more than
 *  one, naming the part of the construct they were recorded against
 *  (`citedPart`); they are never pooled into one set.
 *
 *  Every group also carries, per entry and in the same order, WHERE that
 *  entry's words landed in the body it assembled (`places`), so a citation line
 *  can state the occurrence it was recorded against and not only its wording. A
 *  proposed join is taken only where the reader confirms it (`absorbs`). */
export interface BriefingGroup { lines: AnswerLine[]; src: string; places: CitedPlace[] }
export function briefingGroups(lines: AnswerLine[]): BriefingGroup[] {
  const groups: BriefingGroup[] = []
  let tail: Tail = null
  for (const line of lines) {
    const group = groups[groups.length - 1]
    const more = group ? continues(tail, line.text) : null
    if (group && more !== null && absorbs(group.src, more)) {
      const before = blocksOf(group.src)
      group.lines.push(line)
      group.src += more
      group.places.push(placeIn(group.places.length + 1, before, blocksOf(group.src)))
    } else {
      groups.push({ lines: [line], src: line.text, places: [placeIn(1, [], blocksOf(line.text))] })
    }
    tail = tailOf(groups[groups.length - 1].src)
  }
  return groups
}

/** THE ANSWER, PRESENTED AS WHAT IT IS.
 *
 *  A written briefing is prose: `Prose` draws its headings, paragraphs, lists
 *  and pipe tables, and in a browser the marked `timeline`/`chart` blocks of
 *  the registry it already reads. Where the server recorded it as `lines`
 *  (0e's structured contract), each recorded line is drawn as its own prose
 *  block with the records it was written from as presses beneath it --
 *  `Prose` still draws the Markdown each block holds, and a block spanning a
 *  multi-line construct (a pipe table, a list) keeps its own lines together
 *  when the server recorded it as one line of the contract, or when it was
 *  split across several (`briefingGroups`): either way those lines are
 *  grouped and read as one body before `Prose` sees them, and each
 *  contributing entry still shows the records it was written from beneath the
 *  group, never blended into one set -- naming, where the group holds more
 *  than one entry, the row, item or statement those records were recorded
 *  against, so which source supports which part of the construct is readable
 *  from the surface itself and not only from the record. An answer with no
 *  recorded `lines`
 *  (written before the contract existed) still reads whole, the one case
 *  nothing can be cited against. A statement-per-line synthesis keeps the
 *  layout that suits it -- the statement, the record's own words under it
 *  (`AnswerStatement`, `links.tsx`), and the records it was written from as
 *  presses -- with its trailing record-count line held back for the facts
 *  disclosure instead of shown here (plan Part 5, `answerRecordCount`).
 *  Either way the recorded characters are the recorded ones.
 *
 *  AND THE CITATIONS THE ANSWER WROTE INTO ITS OWN SENTENCES ARE NUMBERS
 *  (owner `ent-bce57ba67f38`). Every direct citation in the answer is numbered
 *  once, across the whole of it, and drawn as `[1]`; what each number is comes
 *  under the answer as a Sources list naming the record, where it came from and
 *  when it was captured, and pressing either the number or the entry opens the
 *  captured record with its exact reference, digest and bounds already
 *  disclosed there. The renderer is the one that was already here: `Prose`
 *  reads the document, with citations drawn inside its running text by
 *  `citedInline` -- nothing of the Markdown reader is edited or replaced. */
export function Briefing({ resource, answer }: { resource: MagnetResource; answer: InquiryEvent | null }) {
  /* READ, not merely fetched. `readFrozenAnswer` already reads an answer whose
     words come out of its frozen package; an answer that recorded its words on
     the event reaches this surface without passing through it, so the same
     reading is applied here. Both are idempotent, so an answer that came the
     other way is unchanged by it. */
  const words = withoutNarration(answerText(answer))
  if (!words) return null
  const lines = answerLines(answer)
  /* THE WHOLE ANSWER IS NUMBERED ONCE, so a record cited in the first
     paragraph and again in the fourth carries the same number in both. The
     joined text leads, which is the order a reader meets them in; the recorded
     statements follow, for an answer whose joined text and lines differ. */
  const notes = answerSources([words, ...lines.map((l) => l.text)], resource.snapshot().results,
    (id, from) => inspect(resource, id, from), answer?.data?.citations)
  const numbered = Array.isArray(answer?.data?.citations) && !!answer.data.citations.length
  const index = citationIndexOf(notes, numbered)
  const body = numbered
    ? <div className="q2-prose"><Prose src={words} inlineOf={citedInline(index)}
      scope={`magnet-answer:${answer?.post ?? resource.saved.id}`} /></div>
    : isWrittenBriefing(words)
    ? !Array.isArray(answer?.data?.lines) || !answer.data.lines.length
      ? <div className="q2-prose"><Prose src={words} inlineOf={citedInline(index)}
        scope={`magnet-answer:${answer?.post ?? resource.saved.id}`} /></div>
      : <>{briefingGroups(lines).map((group, i) => <div key={`answer-${i}`} className="q2-prose">
        <Prose src={group.src} inlineOf={citedInline(index)}
          scope={`magnet-answer:${answer?.post ?? resource.saved.id}-${i}`} />
        {group.lines.map((line, j) => <Cites key={j} resource={resource} cites={line.cites}
          part={group.lines.length > 1 ? citedPart(line.text, group.places[j]) : undefined} />)}
      </div>)}</>
    : <>{withoutRecordCount(lines).map((line, i) => <div key={`answer-${i}`}>
      <AnswerStatement line={line.text} lead={!i} />
      <Cites resource={resource} cites={line.cites} />
    </div>)}</>
  return <Citations.Provider value={index}>{body}<SourceNotes notes={notes} /></Citations.Provider>
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

/** THE HEADLINE AND ITS EXCERPT (approved mockup round 4,
 *  `01-summary-rest.png` / `02-summary-focus.png`). A real title, not the bare
 *  "SUMMARY" label standing alone over undifferentiated prose: the answer's
 *  own leading sentence, drawn at the weight a reader meets a title at, with
 *  the next one to three sentences beneath it at the quieter body size as the
 *  excerpt. Nothing is generated here that the recorded answer does not
 *  already say -- no second model call, no fabricated subject line -- this
 *  only draws the synthesis's own first sentence as what it already is: the
 *  thing a reader needs to know without opening the card. */
export function summaryHeadline(words: string): { title: string; excerpt: string } | null {
  const body = withoutNarration(words).trim()
  if (!body) return null
  const sentences = body.replace(/\s+/g, ' ').match(/[^.!?]+[.!?]+(?=\s|$)|[^.!?]+$/g) ?? [body]
  const title = sentences[0].trim()
  const excerpt = sentences.slice(1, 4).join(' ').trim()
  return title ? { title, excerpt } : null
}

/** The moment a collection was last captured, said the way the approved
 *  metadata row says a moment: "today, 10:42 AM" or "Nov 18" -- never the raw
 *  recorded number. A local copy of `CollectionConfiguration.lastCollected`
 *  rather than an import of it: that module is substituted by a stub in its
 *  own authority test, and this surface has no other reason to depend on it. */
function lastCollectedWhen(at?: number | null): string {
  if (typeof at !== 'number' || !Number.isFinite(at)) return 'Not collected yet'
  const d = new Date(at * 1000)
  return d.toDateString() === new Date().toDateString()
    ? `Last collected today, ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
    : `Last collected ${d.toLocaleDateString([], { month: 'short', day: 'numeric' })}`
}

/** Taking the answer to the Conversation, the way every other "Discuss" press
 *  in this build does (`TAKE_TO_CONVERSATION`, `discussEvidence`): the one
 *  explicit act, never a navigation that reads as leaving the Magnet. */
export function discussSummary(resource: MagnetResource): void {
  goTab(resource, 'Conversation')
  focusMiniComposer()
}

/** THE METADATA ROW ITSELF (plan Part A/round 4): update time and two
 *  small icon-only buttons below a hairline divider, in place of the
 *  prominent "Where it came from" / "Discuss" text links the owner asked to
 *  be rid of (`ent-b328aed7a160`). Each carries a `title` and matching
 *  `aria-label`, the same convention `q2-magnet-icon` already uses everywhere
 *  else in this build, rather than a new icon system. */
function SummaryHeadline({ resource, headline, at }: { resource: MagnetResource; headline: { title: string; excerpt: string }; at?: number | null }) {
  {/* NO "Summary" KICKER HERE: the card's own tab already reads Summary a
      hand's width above (owner `ent-15a36a065eb8`, "the place name is said
      once"), so this opens directly on the real title the owner asked for
      instead of repeating the tab over it. */}
  return <section className="q2-magnet-headline" aria-label="Summary">
    <h3 className="q2-magnet-headline-title">{headline.title}</h3>
    {!!headline.excerpt && <p className="q2-magnet-headline-excerpt">{headline.excerpt}</p>}
    <div className="mgd-divider q2-magnet-headline-divider" />
    <div className="mgd-row mgd-spread q2-magnet-headline-meta">
      <span className="mgd-subtle">{lastCollectedWhen(at)}</span>
      <span className="mgd-row">
        <button type="button" className="q2-magnet-icon" aria-label="View sources" title="View sources" onClick={() => browseCollection(resource)}><span aria-hidden="true">👁</span></button>
        <button type="button" className="q2-magnet-icon" aria-label="Discuss in Conversation" title="Discuss in Conversation" onClick={() => discussSummary(resource)}><span aria-hidden="true">💬</span></button>
      </span>
    </div>
  </section>
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
      /* AND A BRIEFING A RUN WROTE IS NEVER WRITTEN OVER ON ITS OWN (plan Part
         3). The written synthesis is the floor shown where no run has answered;
         it is not an improvement on a briefing, and `finalize` records no
         collection on its answer, so "the answer is not for this collection"
         cannot be read as "there is no answer". With a briefing standing, this
         view writes nothing: the owner's two presses -- a written answer, or
         another briefing -- are what record the next one. */
      .then((got) => needsWrittenAnswer(got, batch) ? inquiries.summarise(batch) : got)
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
  /* A BRIEFING A RUN WROTE, QUALIFIED AND THEN READ, once per answer. A fresh
     display receipt for the answer's own frozen question and run, the
     collection it was written from out of its own manifest, and then its
     frozen words -- all of them reads of named records, started only by the
     answer standing now being one whose words the event does not carry: no
     timer, no poll, and nothing is read again while that same answer stands.
     Where the record will not qualify it now, nothing of its words is shown. */
  const [frozen, setFrozen] = useState<StandingBriefing | null>(null)
  const standingAnswer = summary?.current ?? null
  useEffect(() => {
    if (!standingAnswer || !agentWritten(standingAnswer) || answerText(standingAnswer)) return
    let live = true
    void readStandingBriefing(inquiries, standingAnswer)
      .then((got) => { if (live) setFrozen(got) })
      .catch((e: Error) => { if (live) setMessage(`${BRIEFING_UNREAD} ${e.message}`) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [standingAnswer])
  const [asking, setAsking] = useState(false)
  /** What the last press actually froze and handed over, said in its own words
   *  rather than promised beforehand. */
  const [frozenAsk, setFrozenAsk] = useState<BriefingFrozen | null>(null)
  const askBriefing = () => {
    if (asking) return
    setAsking(true); setMessage(''); setFrozenAsk(null)
    void askForBriefing(resource, inquiries)
      .then((got) => setFrozenAsk(got))
      .catch((e: Error) => setMessage(e.message))
      .finally(() => setAsking(false))
  }
  /** The answer as it is read here: the recorded event, with a run-written
   *  answer's frozen words where this view reads any answer's words. */
  const current = withWords(standingAnswer, frozen)
  const byRun = agentWritten(current)
  /** WHETHER THE ANSWER SHOWN WAS WRITTEN FROM THE COLLECTION SHOWN. For a
   *  briefing, out of its own frozen manifest; for the written synthesis, the
   *  collection the record puts on its answer. `null` means unread, and then
   *  neither is claimed. */
  const fromShown: boolean | null = byRun
    ? writtenFromShown(frozen, current?.post, batch)
    : summary?.batch == null || !batch ? null : summary.batch === batch
  const answered = answerText(current)
  /** THE HEADLINE DRAWN FROM THIS ANSWER (plan Part A/round 4), `null` where
   *  there is no answer to draw one from -- the counted-lead branch below
   *  keeps its own wording exactly as it was. */
  const headline = answered ? summaryHeadline(answered) : null
  const writtenBriefing = !!answered && isWrittenBriefing(answered)
  const change: AnswerChange | null = answerDiff(current, summary?.superseded[0])

  const lead = materialLead(s)
  const measured = collectionOverview(resource.saved, s)
  const recordCount = answerRecordCount(current)
  const excerpts = collectedExcerpts(s.results)
  const dated = datedMaterial(s.results)
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
    {/* THE PLACE NAME IS SAID ONCE (owner `ent-15a36a065eb8`: redundant
        headings out). The card's own tab bar reads `Summary` a hand's width
        above this, so the eyebrow printed the word twice with nothing between
        them. What this line says that the tab does not -- what is held, and
        how much of it -- is kept, as the standfirst it is. */}
    <div className="mgd-row mgd-spread q2-magnet-place-head">
      <div className="mgd-grow">
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
              {/* THE ANSWER AS WHAT IT IS (plan Part 5). A written briefing is
                  drawn as prose by `Prose`; a statement-per-line synthesis
                  keeps statement, quotation and air (owner ent-0b4f3f69b836),
                  and each statement now carries the collected records it was
                  written from as presses -- the `cites` the server has always
                  recorded and this view used to discard. The recorded
                  characters are unchanged either way. What was grounded in what
                  is said by `Grounded`, below, exactly as before. */}
              {!!headline && <SummaryHeadline resource={resource} headline={headline} at={s.activation?.at} />}
              <Briefing resource={resource} answer={current} />
              {/* WHICH COLLECTION THIS ANSWER WAS WRITTEN FROM, where it is not
                  the one shown beside it. The answer is preserved either way --
                  burying a briefing under the counted floor is what
                  `needsWrittenAnswer` prevents -- but the records, facts and
                  excerpts below belong to the collection on screen, and an
                  answer written from an earlier one must say so rather than
                  stand silently among them (review F6). */}
              {fromShown === false && <p className="mgd-subtle">{BRIEFING_FROM_EARLIER}</p>}
              {byRun && fromShown === null && <p className="mgd-subtle">{BRIEFING_COLLECTION_UNKNOWN}</p>}
              {/* HOW THE ANSWER WAS MADE, ONE PRESS AWAY (owner
                  `ent-15a36a065eb8`: "Keep secondary actions and provenance
                  available through progressive disclosure").
                  What stood here was four paragraphs of apparatus between the
                  answer and the records it was written from: what it was
                  grounded in, what the record checked before it froze a run's
                  reply, that this is a kept question's answer, and what the
                  presses under it would do. Every word of it is still written,
                  in full, in the order it was in. None of it is what a reader
                  came to read, and all of it was printed over the fold.

                  WHAT STAYS ABOVE IT is what qualifies the answer itself: that
                  it was written from an earlier collection than the one on
                  screen, or that which collection is unread. Those change what
                  the words above mean, so they are not disclosure material. */}
              <details className="q2-magnet-provenance q2-magnet-disclosure q2-magnet-how">
                <summary><span className="mgd-link mgd-small">{HOW_THIS_WAS_MADE} ▾</span></summary>
                <div aria-label="How this answer was made, and what the presses under it do">
                  <Grounded answer={current} />
                  {/* WHAT THE RECORD CHECKED BEFORE IT FROZE A RUN'S REPLY as
                      this answer. Said only of an answer a run wrote, and said
                      as what it is -- a statement about the reach the record
                      qualified, not a second grounding claim: what an answer
                      was allowed to reach is `Grounded`'s, from the answer's
                      own provenance. */}
                  {byRun && <p className="mgd-subtle">{BRIEFING_BY_RUN}</p>}
                  {/* Who wrote it is said ONCE, by the grounding statement
                      above ("Written from this Magnet's collected records and
                      nothing else"). What this adds is the one thing that
                      statement does not: that it is a kept question's answer,
                      with its earlier answers under it. The answer package's
                      own `written_by` sentence is on the recorded answer, one
                      press away. */}
                  <p className="mgd-subtle">{SUMMARY_IS_A_QUESTION}</p>
                  {/* And what the two presses in the row below actually do.
                      It was a paragraph under them; it is the same paragraph,
                      beside the rest of what is true about this answer. */}
                  <p className="mgd-subtle">{byRun ? BRIEFING_STANDS : BRIEFING_IS_YOURS_TO_SEND}</p>
                </div>
              </details>
            </section>
          : <>{/* THE LEAD WITHOUT AN ANSWER IS WHAT THE MATERIAL NAMES, not a
                   count of it: `materialLead` reads the subjects out of the
                   rows' own captured words. Every measurement the counted lead
                   used to open with is written still, in the facts disclosure
                   below. */}
              <p className="mgd-p mgd-muted q2-magnet-lead">{lead}</p>
              <p className="mgd-subtle">{answering ? 'Writing an answer from this collection…' : NOT_ANSWERED_YET}</p></>}
        {/* The design's own action row (`03-sources.png`'s "Collect manually"):
            what is true on the left, the press at the far edge. */}
        <div className="mgd-row mgd-spread q2-magnet-lead-action">
          <span className="mgd-subtle mgd-grow">{starting.note}</span>
          <button type="button" className="mgd-button mgd-secondary" disabled={answering || !batch} onClick={answerNow}>
            {answering ? 'Answering…' : answered ? 'Answer again from this collection' : ANSWER_THIS_COLLECTION}</button>
          {/* THE BRIEFING THE OWNER ASKED FOR, as the one press that asks for
              it (plan Part 3). The written answer beside it is the floor that
              needs no run; this is the reasoned one, and it is started only
              here, by hand. */}
          <button type="button" className="mgd-button mgd-secondary" disabled={asking || !batch} onClick={askBriefing}>
            {asking ? 'Preparing the briefing question…' : WRITE_THE_BRIEFING}</button>
          <button type="button" className="mgd-button" onClick={() => chooseSources(resource)}>{starting.label}</button>
        </div>
        {/* With no answer yet there is nothing to disclose it behind, and this
            page is nearly empty: what asking for a briefing actually does is
            the guidance the reader needs, so it stays on the surface. With an
            answer it is behind `How this answer was made ▾`, above. */}
        {!answered && <p className="mgd-subtle">{BRIEFING_IS_YOURS_TO_SEND}</p>}
        {/* WHAT THE PRESS ACTUALLY FROZE, counted from the frozen request
            itself: which collection its evidence is, what this question
            carried into it besides, and whether an earlier unanswered request
            was resumed instead of a new one frozen (review F3). */}
        {!!frozenAsk && <p className="mgd-subtle" role="status">
          {frozenAsk.resumed ? `${BRIEFING_RESUMED} ${briefingFrozenWords(frozenAsk)}` : briefingFrozenWords(frozenAsk)}</p>}
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

        {/* PRESENTED AS WHAT IT REPRESENTS (owner #1017). Where the collected
            records record their own publication dates, what they are is a set
            of dated published things -- so they are drawn as a table, by the
            renderer that already draws tables, rather than described in a
            sentence or quoted in a column. A collection whose rows record no
            such date gets no table: the shape has to be in the material. */}
        {worthTabulating(dated) && <section aria-label="What this Magnet holds, by date">
          <h3 className="mgd-h3">What it holds, by date</h3>
          <div className="q2-prose"><Prose src={datedTable(dated)} scope={`magnet-dated:${resource.saved.id}`} /></div>
          <p className="mgd-subtle">{DATED_WHY}</p>
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
            {!!current && <>
              {/* A DOCUMENT'S LINES ARE NOT ITS STATEMENTS. `answerDiff` splits
                  the recorded text on newlines, which is exactly right for the
                  synthesis -- it writes one statement per line -- and wrong for
                  a written briefing, where it listed `|---|---|`, a `**bold**`
                  fragment and half a sentence as sixteen things the answer "now
                  says". A written answer is rewritten whole and read whole
                  above; only a statement-per-line answer lists its statements
                  here. Nothing is hidden either way: both answers are kept
                  under this Magnet's standing question. */}
              {writtenBriefing
                /* AND IT IS ONLY "REWRITTEN FROM THE COLLECTION SHOWN" WHERE
                   IT WAS. This sentence is now said of frozen briefings too,
                   and a briefing stands over later collections, so saying it
                   unconditionally told the owner a preserved older answer had
                   been rewritten from what is on screen (review F6). */
                ? <p className="mgd-p">{fromShown === true ? BRIEFING_REWRITTEN
                  : fromShown === false ? BRIEFING_FROM_EARLIER : BRIEFING_COLLECTION_UNKNOWN}</p>
                : <>
                  <p className="mgd-p">{changeWords(change)}</p>
                  {change?.added.map((line) => <p className="mgd-item" key={`added-${line}`}><span className="mgd-subtle">Now says · </span><Linked text={line} /></p>)}
                  {change?.gone.map((line) => <p className="mgd-item" key={`gone-${line}`}><span className="mgd-subtle">No longer says · </span><Linked text={line} /></p>)}
                </>}
              {!summary?.superseded.length && <p className="mgd-subtle">This is the first answer recorded against this Magnet's standing question, so there is nothing before it to differ from.</p>}
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
            {/* EVERY MEASUREMENT, INCLUDING THE TWO THAT USED TO LEAD. The
                counted overview is written whole here now -- what was
                collected, from how many sources, when, over what span, how
                much text -- so demoting the counted lead took nothing away
                from the reader; it moved it to where the owner kept the rest
                of the measurements. */}
            {measured.map((line, i) => <p key={`measured-${i}`}>{line}</p>)}
            {/* THE ANSWER'S OWN RECORD-COUNT LINE, demoted the same way as the
                counted lead above: the synthesis still counts what it read,
                last, and the count is kept here rather than shown above the
                fold in the answer itself (plan Part 5). */}
            {recordCount && <p>{recordCount}</p>}
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
