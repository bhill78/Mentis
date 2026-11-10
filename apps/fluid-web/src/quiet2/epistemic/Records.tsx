/* A POST'S EPISTEMIC RECORDS, AS MARK 2 SHOWS THEM (Track A).
 *
 * ONE MARK PER POST, NEVER ONE PER RECORD: a small count in the right
 * margin, level with the byline, in the same measured stack as the post's
 * annotation marks (annotate/Margin.tsx draws it and keeps the two apart).
 * It says how many records the record states for this post (read.ts says
 * which, and how) and opens nothing until it is pressed.
 *
 * PRESSED, A COMPACT CARD: the records grouped by their own Kind, each group
 * with its count, opening on its own; a long group shows its first few and
 * says how many more. Each record says what it is in Mentis's words and no
 * other: its Kind, its words, its status as the Ladder gives it
 * (`formatStatusLabel`), how it is this post's (recorded in the work on it,
 * extracted or derived from it, an outcome of it), who recorded it and when,
 * its open challenges, an outcome's result, a hypothesis's falsifier and any
 * limits where recorded. Nothing is scored, ranked or summed into a verdict:
 * a requested adoption is a request, an outcome is what happened once.
 *
 * INSPECTED IN PLACE: a record opens to what Governance's item view reads of
 * it (`/api/ladder/items/<id>`, GovItem): its lineage one step each way, its
 * challenges with how each was answered, what superseded or was proposed to
 * supersede it, its adoption requests and declines, its outcomes, and how
 * often later work cited it or was given it. Read-only: acting on a record
 * is Governance's.
 *
 * THE WHOLE COLLECTION OPENS IN A WORKING SURFACE (`RecordsView`), every
 * group open, through the page's existing `onBeside`. */
import { useState, type ReactNode } from 'react'
import { ago } from '../../api'
import {
  attemptedLabel,
  basisVerb,
  challengeResolvedLine,
  citeView,
  formatStatusLabel,
  splitChallenges,
  whoOf,
  type LadderItem,
  type LineageNode,
} from '../../fluid/governance/ladderTypes'
import type { Id } from '../../fluid/store'
import { usePage } from '../Post'
import { postOf } from '../real'
import { repairText } from '../text'
import { useDetail, usePostRecords, type Held, type Relation } from './read'
import './records.css'

/** What a working surface holds when it holds a post's records. Surface.tsx
 *  draws it with `RecordsView`; Post.tsx's `SurfaceView` names it. */
export interface RecordsSurfaceView { kind: 'records'; post: Id; conversation: Id | null }

/* -- words ------------------------------------------------------------------ */

/** The order the owner reads Kinds in; every other Kind follows, the larger
 *  group first. A Kind the Brain does not define simply never appears. */
const FIRST = ['hypothesis', 'lesson', 'experience', 'note']

/** A Kind's name as a group heading: "hypotheses", "lessons",
 *  "conversation instructions". */
export function kindPlural(kind: string, n: number): string {
  const w = kind.replace(/[-_]/g, ' ')
  if (n === 1) return w
  if (/is$/.test(w)) return w.replace(/is$/, 'es')
  if (/[^aeiou]y$/.test(w)) return w.replace(/y$/, 'ies')
  if (/(s|x|ch|sh)$/.test(w)) return w + 'es'
  return w + 's'
}

/** How the record is this post's, in plain words. */
export function relationWords(rel: Relation): string {
  return rel === 'recorded' ? 'recorded in the work on this post' : `${basisVerb(rel)} this post`
}

/** The records in groups by Kind, in reading order. */
export function groupsOf(held: Held[]): [string, Held[]][] {
  const by = new Map<string, Held[]>()
  for (const h of held) by.set(h.item.kind, [...(by.get(h.item.kind) ?? []), h])
  for (const list of by.values()) list.sort((a, b) => (b.item.recorded_at ?? 0) - (a.item.recorded_at ?? 0))
  const rank = (k: string) => { const i = FIRST.indexOf(k); return i < 0 ? FIRST.length : i }
  return [...by].sort(([a, x], [b, y]) => rank(a) - rank(b) || y.length - x.length || a.localeCompare(b))
}

/** "18 records: 12 notes, 6 outcomes"; "2 problems"; "1 outcome" */
export function countWords(held: Held[]): string {
  const g = groupsOf(held)
  if (g.length === 1) return `${held.length} ${kindPlural(g[0][0], held.length)}`
  return `${held.length} records: ` + g.map(([k, l]) => `${l.length} ${kindPlural(k, l.length)}`).join(', ')
}

/** A record's own words: its `text`, else the first field that says
 *  something besides its name (a Persona's behaviour, a Workflow's text). */
const wordsOf = (item: LadderItem) => {
  const raw = item.text || Object.entries(item.fields ?? {}).find(([k, v]) => k !== 'name' && typeof v === 'string' && v.trim())?.[1] as string | undefined || ''
  return repairText(raw.trim())
}

/** A recorded field as words, only where the record holds it as words. */
const fieldOf = (item: LadderItem, name: string): string | null => {
  const v = (item.fields ?? {})[name]
  return typeof v === 'string' && v.trim() ? repairText(v.trim()) : null
}

/* -- the mark --------------------------------------------------------------- */

export const RECORDS_GLYPH = (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 3 3 7.5 12 12l9-4.5L12 3Z" /><path d="m3 12 9 4.5 9-4.5" /><path d="m3 16.5 9 4.5 9-4.5" />
  </svg>
)

/** What the mark says to a reader who cannot see it. */
export const markLabel = (held: Held[]) => `Epistemic records from this post: ${countWords(held)}`

/* -- the card's body -------------------------------------------------------- */

/** How many records a group shows before saying how many more. */
const FEW = 5

export function RecordsPanel({ post, conversation, held, onClose }: {
  post: Id; conversation: Id | null; held: Held[]; onClose: () => void
}) {
  const page = usePage()
  const beside = page.onBeside
  const { truncated } = usePostRecords(post, conversation)
  return (
    <>
      <div className="q2m-head">
        <span className="q2m-what">Records from this post</span>
        {beside && (
          <button type="button" className="q2e-beside" title="Open every record in a working surface"
            onClick={() => { onClose(); beside({ kind: 'records', post, conversation }) }}>Open beside</button>
        )}
        <button type="button" className="q2m-x" aria-label="Close" title="Close (Esc)" onClick={onClose}>×</button>
      </div>
      <p className="q2m-meta">{truncated && 'At least '}{countWords(held)}</p>
      <Groups held={held} open={held.length <= FEW} />
    </>
  )
}

/** The groups, each opening on its own. */
function Groups({ held, open, all }: { held: Held[]; open: boolean; all?: boolean }) {
  const groups = groupsOf(held)
  return (
    <div className="q2e-groups">
      {groups.map(([kind, list]) => <Group key={kind} kind={kind} list={list} open={open || groups.length === 1} all={all} />)}
    </div>
  )
}

function Group({ kind, list, open: first, all }: { kind: string; list: Held[]; open: boolean; all?: boolean }) {
  const [open, setOpen] = useState(first)
  const [more, setMore] = useState(false)
  const shown = all || more ? list : list.slice(0, FEW)
  const id = `q2e-g-${kind}-${list[0]?.item.id ?? ''}`
  return (
    <section className={'q2e-group' + (open ? ' on' : '')}>
      <button type="button" className="q2e-group-head" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <span className="q2e-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
        <span className="q2e-kind">{kindPlural(kind, list.length)}</span>
        <span className="q2e-count">{list.length}</span>
      </button>
      {open && (
        <ol className="q2e-list" id={id}>
          {shown.map((h) => <Record key={h.item.id} h={h} />)}
          {shown.length < list.length && (
            <li className="q2e-more"><button type="button" className="q2e-link" onClick={() => setMore(true)}>Show {list.length - shown.length} more {kindPlural(kind, list.length - shown.length)}</button></li>
          )}
        </ol>
      )}
    </section>
  )
}

/** One record: identity, words, standing, how it is this post's. */
function Record({ h }: { h: Held }) {
  const { item, relations } = h
  const [inspect, setInspect] = useState(false)
  const status = formatStatusLabel(item.status)
  const words = wordsOf(item)
  const name = fieldOf(item, 'name')
  const falsifier = fieldOf(item, 'falsifier')
  const result = item.kind === 'outcome' ? fieldOf(item, 'result') : null
  const attempted = item.kind === 'outcome' ? (item.fields ?? {}).attempted as boolean | null | undefined : undefined
  const by = item.recorded_by?.alias ? whoOf({ by_alias: item.recorded_by.alias }) : null
  return (
    <li className="q2e-record">
      <p className="q2e-words">{name && <b>{name}{words ? ': ' : ''}</b>}{words || (!name && <i>No words recorded</i>)}</p>
      <p className="q2e-facts">
        <span className={'q2e-status q2e-status-' + item.status}>{status.label}</span>
        {result && <span>{result}{attemptedLabel(attempted)}</span>}
        {item.challenged > 0 && <span className="q2e-challenged">{item.challenged} open {item.challenged === 1 ? 'challenge' : 'challenges'}</span>}
        {item.governs && (item.status === 'recorded' || item.status === 'adoption_requested') && <span>not adopted</span>}
      </p>
      {falsifier && <p className="q2e-field"><span>Falsifier:</span> {falsifier}</p>}
      {item.limits && <p className="q2e-field"><span>Limits:</span> {repairText(item.limits)}</p>}
      <p className="q2e-how">
        {relations.map(relationWords).join(' · ')}
        {by && <> · {by}</>}
        {item.recorded_at ? <> · <time title={new Date(item.recorded_at * 1000).toLocaleString()}>{ago(item.recorded_at)}</time></> : null}
      </p>
      <p className="q2e-id">
        <code title="This record's identity in Mentis">{item.id}</code>
        <button type="button" className="q2e-link" aria-expanded={inspect} onClick={() => setInspect(!inspect)}>{inspect ? 'Less' : 'Inspect'}</button>
      </p>
      {inspect && <Detail id={item.id} />}
    </li>
  )
}

/* -- one record, inspected ---------------------------------------------------- */

/** A lineage node as one line: what it is, its first words, an outcome's result. */
const nodeWords = (n: LineageNode) => {
  const c = citeView(n)
  const what = n.kind === 'contribution' ? 'a post' : (n.kind ?? 'source').replace(/[-_]/g, ' ')
  const said = repairText(c.quote ? `“${c.quote}”` : c.link)
  return `${what}: ${said.length > 110 ? said.slice(0, 109).trimEnd() + '…' : said}` + (n.result ? ` (${n.result}${attemptedLabel(n.attempted)})` : '')
}

function Detail({ id }: { id: Id }) {
  const { d, error } = useDetail(id, true)
  if (error) return <p className="q2m-faint" role="alert">Could not read it: {error}</p>
  if (!d) return <p className="q2m-faint" role="status">Reading…</p>
  const up = (d.lineage?.up ?? []).filter((n) => (n.depth ?? 1) === 1)
  const down = (d.lineage?.down ?? []).filter((n) => (n.depth ?? 1) === 1)
  const { open, resolved } = splitChallenges(d.challenges)
  const outcomes = Array.isArray(d.outcomes) ? d.outcomes : d.outcomes?.all ?? d.outcomes?.latest ?? []
  const cited = typeof d.cited_by === 'number' ? d.cited_by : d.usage?.cited ?? d.cited_by.length
  const delivered = d.usage?.delivered ?? d.delivered?.length ?? 0
  const reqs = d.adoption?.requests ?? []
  const declines = d.adoption?.declines ?? []
  const rows: [string, ReactNode][] = []
  if (up.length) rows.push(['Rests on', <ul>{up.map((n) => <li key={n.id}>{basisVerb(n.relation)} {nodeWords(n)}</li>)}</ul>])
  if (down.length) rows.push(['Came after it', <ul>{down.map((n) => <li key={n.id}>{basisVerb(n.relation)}: {nodeWords(n)}</li>)}</ul>])
  if (open.length || resolved.length) rows.push(['Challenges', <ul>
    {open.map((c) => <li key={c.link}><b>open</b> · {whoOf(c)}: {repairText(c.because)}</li>)}
    {resolved.map((c) => <li key={c.link} className="q2m-faint">{whoOf(c)}: {repairText(c.because)} · {challengeResolvedLine(c)}</li>)}
  </ul>])
  if (reqs.length || declines.length || d.adoption?.adopted) rows.push(['Adoption', <ul>
    {reqs.map((r) => <li key={r.request}>requested by {whoOf(r)}{r.at ? ` ${ago(r.at)}` : ''}{r.closed_by ? ` · ${r.closed_by}` : r.closed ? ' · answered' : ' · open'}{r.because ? `: ${repairText(r.because)}` : ''}</li>)}
    {declines.map((x, i) => <li key={'d' + i}>declined by {whoOf(x)}{x.at ? ` ${ago(x.at)}` : ''}{x.because ? `: ${repairText(x.because)}` : ''}</li>)}
    {d.adoption?.adopted && <li>adopted{d.adoption.adopted.at ? ` ${ago(d.adoption.adopted.at)}` : ''}</li>}
  </ul>])
  if (outcomes.length) rows.push(['Outcomes', <ul>{outcomes.slice(0, 5).map((o) => <li key={o.id}>{o.result ?? 'outcome'}{attemptedLabel(o.attempted)}{o.text ? `: ${repairText(o.text)}` : ''}</li>)}
    {outcomes.length > 5 && <li className="q2m-faint">and {outcomes.length - 5} more</li>}</ul>])
  rows.push(['Used since', <>{cited} later {cited === 1 ? 'record cites' : 'records cite'} it · given to {delivered} {delivered === 1 ? 'run' : 'runs'}</>])
  return (
    <dl className="q2e-detail">
      {rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
    </dl>
  )
}

/* -- the whole collection, in a working surface ------------------------------ */

/** Every record of one post, every group open, for a working surface. */
export function RecordsView({ view }: { view: RecordsSurfaceView }) {
  const page = usePage()
  const { held, error, truncated } = usePostRecords(view.post, view.conversation)
  const p = postOf(view.post)
  return (
    <div className="q2e-view">
      <p className="q2e-view-from">
        {held ? (truncated ? 'At least ' : '') + countWords(held) : error ? `Could not read the records: ${error}` : 'Reading the records…'}
        {p && <> · <button type="button" className="q2e-link" onClick={() => page.onBeside?.({ kind: 'post', id: view.post })}>Show the post they are from</button></>}
      </p>
      {held && (held.length ? <Groups held={held} open all /> : <p className="q2m-faint">The record states no records for this post now.</p>)}
    </div>
  )
}

/** A working surface's header for a post's records: [what in it, kind]. */
export function recordsIdentity(view: RecordsSurfaceView): { what: string; kind: string } {
  const p = postOf(view.post)
  const who = p ? p.by.name.replace(/^@/, '') : ''
  return { what: [p?.number ? `from #${p.number}` : 'from a post', who && `by ${who}`].filter(Boolean).join(' '), kind: 'Records' }
}
