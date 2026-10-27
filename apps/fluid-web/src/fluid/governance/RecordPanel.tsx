/* THE RECORD PANEL, always beside the item's text (Codex's addition, accepted
 * with Claude's layout): Standing, Reach, From, Produced by, Established by,
 * Replaces, Proposed successors and Cited by.
 *
 * EVERY FIELD SAYS HOW ITS OWN LOOKUP WENT. The fields come from four reads --
 * the entry, its reach (`/api/governance/applies`), its history
 * (`/api/governance/history`) and each predecessor's own entry -- and one read
 * failing, or not answering, is said in the field it feeds, with Retry, while
 * every other field shows what its read returned. Nothing waits on everything:
 * Classic's panel stayed on "loading…" when one read would not settle.
 *
 * Read-only. The acts are the record's own (useRecordActs), drawn beside it. */

import { useEffect, useState, type ReactNode } from 'react'
import { ago, useApi, when, type Id, type ItemHistoryRead, type ProposedRead } from '../../api'
import { CITED_BY } from '../../surfaces/governance/R2Record'
import { standingOf, standingUndeclared } from '../../surfaces/standing'
import { store } from '../store'

/** What the entry read carries that the panel speaks from. */
export interface EntryFull {
  id: Id
  missing?: boolean
  kind: string | null
  stands: boolean
  standing_apt?: boolean | null
  established_by: Id[]
  superseded_by: Id[]
  incoming?: Record<string, Id[]>
  proposed?: ProposedRead | null
  deleted?: { at: number } | null
  author_alias?: string | null
  at?: number | null
  provenance?: {
    produced_by?: {
      act: Id; act_type?: string; actor_alias?: string; at?: number; runtime?: string | null
      conversation?: Id | null; turn?: Id | null; turn_number?: number | null
    }[]
    why_not?: string
  }
}

interface Lookup { loading: boolean; error: string | null; reload: () => void }

/** A lookup that has not answered after this long is said to be waiting. */
const SLOW_MS = 12000

/** One field, and how its lookup went. */
function Field({ label, read, children, name }: { label: string; read?: Lookup; children?: ReactNode; name: string }) {
  const [slow, setSlow] = useState(false)
  const pending = !!read?.loading
  useEffect(() => {
    setSlow(false)
    if (!pending) return
    const t = setTimeout(() => setSlow(true), SLOW_MS)
    return () => clearTimeout(t)
  }, [pending])
  return (
    <div className="fg-field" data-field={name}>
      <dt>{label}</dt>
      <dd>
        {read?.error ? (
          <span className="fg-field-error" role="alert">
            Couldn’t read this: {read.error}{' '}
            <button className="fg-link" onClick={read.reload}>Retry</button>
          </span>
        ) : pending && children == null ? (
          <span className="fg-faint">{slow ? 'Still waiting for the record to answer… ' : 'Reading…'}
            {slow && <button className="fg-link" onClick={read!.reload}>Retry</button>}</span>
        ) : (
          children
        )}
      </dd>
    </div>
  )
}

/** Where it stands, as Classic's register says it, and the pill's class: ONE
 *  ANSWER for the item's header and the panel's Standing field, so the two
 *  cannot disagree. Undeclared standing says no standing word (`standingUndeclared`). */
export function standingSaid(d: EntryFull): { tone: string; words: string } {
  if (d.deleted) return { tone: 'ended', words: 'Ended or deleted' }
  if (standingUndeclared(d)) return { tone: 'undeclared', words: 'Standing undeclared' }
  const s = standingOf(d)
  return s === 'stands' ? { tone: 'stands', words: 'In force' }
    : s === 'candidate' ? { tone: 'candidate', words: 'Proposed · reaches nobody' }
      : s === 'ended' ? { tone: 'ended', words: 'Ended: superseded' }
        : { tone: 'ended', words: 'Replaced before establishment' }
}

/** A predecessor the record links this one to, read on its own so its failure
 *  is its own, and openable: it is governed material in its own right. */
function EntryRef({ id, onOpen }: { id: Id; onOpen: (id: Id) => void }) {
  const got = useApi<{ kind: string | null; fields: string[]; body: Record<string, unknown>; missing?: boolean }>(
    '/api/entries/' + encodeURIComponent(id))
  const text = got.data && !got.data.missing
    ? String(got.data.fields.map((f) => got.data!.body[f]).find((v) => typeof v === 'string' && v) ?? '') : ''
  return (
    <li>
      <button className="fg-link fg-mono" onClick={() => onOpen(id)}>{id}</button>
      {got.error ? <span className="fg-field-error" role="alert"> · couldn’t read it: {got.error}{' '}
        <button className="fg-link" onClick={got.reload}>Retry</button></span>
        : got.data?.missing ? <span className="fg-faint"> · not held in this Brain</span>
          : text ? <span className="fg-faint"> · {got.data?.kind} · {text.length > 60 ? text.slice(0, 59) + '…' : text}</span> : null}
    </li>
  )
}

/** AN ESTABLISHMENT, SAID AS CLASSIC SAYS IT (WorkspaceItemLegs, the Versions
 *  timeline): who, when and why, as text. It is a link, not governed material,
 *  so it is never opened as an item -- that drew it with a Standing, a Reach,
 *  Dispute and More, and invited disputing who established the rule. The
 *  record names no Turn an establishment came from, so there is nothing to
 *  point an arrow at. */
function Establishment({ by, at, reason }: { by: string | null | undefined; at: number | null | undefined; reason: string | null | undefined }) {
  return (
    <>
      <span className="fg-established">{by ?? 'Somebody the record does not name'}{at ? ` · ${when(at)}` : ''}</span>
      {reason && <small className="fg-faint fg-why">{reason}</small>}
    </>
  )
}

/** The fallback, where the history has no step for the item: the entry read
 *  names only the establishing links, so each is read for the same words. */
function EstablishmentRef({ link }: { link: Id }) {
  const got = useApi<{ author_alias?: string | null; at?: number | null; body?: Record<string, unknown>; missing?: boolean }>(
    '/api/entries/' + encodeURIComponent(link))
  const reason = got.data?.body?.reason
  return (
    <li>
      {got.error ? <span className="fg-field-error" role="alert">Couldn’t read this establishment: {got.error}{' '}
        <button className="fg-link" onClick={got.reload}>Retry</button></span>
        : !got.data ? <span className="fg-faint">Reading…</span>
          : got.data.missing ? <span className="fg-faint">An establishment this Brain does not hold.</span>
            : <Establishment by={got.data.author_alias} at={got.data.at} reason={typeof reason === 'string' ? reason : null} />}
    </li>
  )
}

export default function RecordPanel({ entry, d, entryRead, rev, onOpenItem, onReadTurn, ladderStatus }: {
  entry: Id
  d: EntryFull | null
  entryRead: Lookup
  /** bumped after an act, so every read here is taken again */
  rev: number
  onOpenItem: (id: Id) => void
  onReadTurn: (conversation: Id, turn: Id) => void
  /** LADDER MATERIAL IS SAID IN THE LADDER'S WORDS: its status, in place of
   *  the pre-ladder Standing line. Null while it is not yet known whether
   *  this is Ladder material; absent for material that stands and governs. */
  ladderStatus?: { label: string; challenged: number } | null
}) {
  const applies = useApi<{ rows: { entry: Id; applies: string; why: string; placed_at: Id[]; whole_brain?: boolean; carried_by?: Id[] }[] }>(
    '/api/governance/applies?entry=' + encodeURIComponent(entry))
  const hist = useApi<ItemHistoryRead>('/api/governance/history?entry=' + encodeURIComponent(entry))
  useEffect(() => { if (rev) { applies.reload(); hist.reload() } }, [rev]) // eslint-disable-line react-hooks/exhaustive-deps

  const made = d?.provenance?.produced_by ?? []
  const from = made.find((p) => p.conversation && p.turn) ?? null
  /* The conversation's name, from Fluid's own store. */
  const [, setNames] = useState(0)
  useEffect(() => {
    if (from?.conversation && !store.conversations.has(from.conversation))
      void store.loadConversations([from.conversation]).then(() => setNames((n) => n + 1)).catch(() => {})
  }, [from?.conversation])
  const fromName = from?.conversation ? store.conversations.get(from.conversation)?.name ?? null : null

  const reach = applies.data?.rows.find((r) => r.entry === entry) ?? null
  const step = hist.data?.timeline?.find((t) => t.entry === entry) ?? null
  const established = step?.established ?? []
  const replaces = (step?.supersedes ?? []).map((l) => l.to)
  const successors = d?.proposed?.successors

  const entryField = (label: string, name: string, body: () => ReactNode) => (
    <Field label={label} name={name} read={entryRead}>{d && !d.missing ? body() : d?.missing ? <span className="fg-faint">This Brain does not hold this entry.</span> : null}</Field>
  )

  return (
    <aside className="fg-record" aria-label="Record">
      <h3 className="fg-record-title">Record</h3>
      <dl>
        {ladderStatus !== undefined ? (
          <Field label="Status" name="status">
            {ladderStatus ? (
              <>{ladderStatus.label}{ladderStatus.challenged > 0 && <span className="fg-flag"> · Challenged{ladderStatus.challenged > 1 ? ` ${ladderStatus.challenged} times` : ''}</span>}</>
            ) : <span className="fg-faint">Reading…</span>}
          </Field>
        ) : entryField('Standing', 'standing', () => {
          const n = d!.incoming?.disputes?.length ?? 0
          return <>{standingSaid(d!).words}{n > 0 && <span className="fg-flag"> · Disputed{n > 1 ? ` ${n} times` : ''}{d!.stands ? ' · still stands' : ''}</span>}</>
        })}
        <Field label="Reach" name="reach" read={applies}>
          {applies.data && (reach ? (
            <span title={reach.why}>
              {reach.applies === 'placed'
                ? reach.whole_brain ? 'Whole Brain' : `Placed in ${reach.placed_at.length} conversation${reach.placed_at.length === 1 ? '' : 's'}`
                : reach.applies === 'by_persona' ? 'When selected as a persona'
                  : reach.applies === 'when_named' ? 'Only when named' : reach.applies}
              <small className="fg-faint fg-why">{reach.why}</small>
            </span>
          ) : <span className="fg-faint">It reaches nobody as it stands now.</span>)}
        </Field>
        {entryField('From', 'from', () => from ? (
          <>
            <button className="fg-link" onClick={() => onReadTurn(from.conversation!, from.turn!)}>
              {fromName ?? 'its conversation'} · Turn{from.turn_number != null ? ` #${from.turn_number}` : ''} ↗
            </button>
            {from.actor_alias && <small className="fg-faint fg-why">{from.actor_alias}{from.at ? ` · ${when(from.at)}` : ''}</small>}
          </>
        ) : <span className="fg-faint">{d!.provenance?.why_not ?? 'The record names no Turn this came from.'}</span>)}
        {entryField('Produced by', 'produced', () => made.length ? (
          <ul className="fg-list">
            {made.slice(0, 3).map((p) => (
              <li key={p.act}>{p.actor_alias ?? 'unattributed'} · {p.act_type ?? 'act'}
                <small className="fg-faint fg-why">{[p.runtime, p.at ? when(p.at) : null].filter(Boolean).join(' · ')}</small></li>
            ))}
            {made.length > 3 && <li className="fg-faint">and {made.length - 3} more acts</li>}
          </ul>
        ) : <span className="fg-faint">{d!.provenance?.why_not ?? 'No act claims to have produced it.'}</span>)}
        {/* FROM THE HISTORY WHERE IT HAS A STEP FOR THIS ITEM; otherwise from
            the entry read, and "nobody" only once that read has said so. */}
        <Field label="Established by" name="established" read={hist.error || !hist.data || step ? hist : entryRead}>
          {hist.data && (step ? (established.length ? (
            <ul className="fg-list">
              {established.map((l) => (
                <li key={l.link}><Establishment by={l.by_alias} at={l.at} reason={l.reason} /></li>
              ))}
            </ul>
          ) : <span className="fg-faint">Nobody has established it.</span>)
            : d && !d.missing ? (d.established_by.length
              ? <ul className="fg-list">{d.established_by.map((x) => <EstablishmentRef key={x} link={x} />)}</ul>
              : <span className="fg-faint">Nobody has established it.</span>)
              : d?.missing ? <span className="fg-faint">This Brain does not hold this entry.</span> : null)}
        </Field>
        <Field label="Replaces" name="replaces" read={hist}>
          {hist.data && (replaces.length
            ? <ul className="fg-list">{replaces.map((id) => <EntryRef key={id} id={id} onOpen={onOpenItem} />)}</ul>
            : <span className="fg-faint">Nothing: it replaced no earlier record.</span>)}
        </Field>
        {entryField('Proposed successors', 'successors', () => d!.proposed == null
          ? <span className="fg-faint">This record declares no relation for proposing a replacement, so none can be read.</span>
          : (
            <details className="fg-fold">
              <summary>{successors?.total ?? successors?.items.length ?? 0} proposed</summary>
              {successors && successors.items.length > 0 ? (
                <ul className="fg-list">
                  {successors.items.map((x) => (
                    <li key={x.link}>
                      <button className="fg-link" onClick={() => onOpenItem(x.entry)}>{x.summary ? (x.summary.length > 70 ? x.summary.slice(0, 69) + '…' : x.summary) : x.entry}</button>
                      <small className="fg-faint fg-why">{x.by_alias ?? 'somebody'} · {x.state === 'candidate' ? 'proposed · reaches nobody' : x.state}{x.at ? ` · ${ago(x.at)}` : ''}</small>
                    </li>
                  ))}
                  {successors.omitted > 0 && <li className="fg-faint">{successors.omitted} more were not returned by this read.</li>}
                </ul>
              ) : <p className="fg-faint">None proposed.</p>}
            </details>
          ))}
        <Field label="Cited by" name="cited">
          <details className="fg-fold"><summary>Where it is cited</summary><p className="fg-faint">{CITED_BY}</p></details>
        </Field>
      </dl>
    </aside>
  )
}
