/* EXPERIMENTAL: a LIVE VIEW over Mentis Problem records. Not a task list.

   The declaration names WHICH Problems to watch and HOW to show them. It never
   holds their state: every row is read from the record (/api/governed for
   the Kind, /api/entries/<id> for each one) and re-read whenever the shell's
   existing /api/pulse says the record or the live runs moved -- the same
   mechanism every other surface in Mentis uses. Nothing here is written.

   WHAT THE RECORD CAN AND CANNOT SAY, found by reading it (see
   experiments/renderable_problems/README.md):
   - A Problem is a Kind with one field, `text`. It has no status field and
     its `standing_apt` is deliberately absent, so "unknown" stays unknown.
   - There is NO act meaning "resolved". supersede (replaced by better
     material), delete (its line ended), dispute (challenged) each mean
     something else, so this surface shows those facts under their own names
     and offers no resolve/close control at all.
   - Nothing records an assignee for a Problem. The only honest "who is on it"
     is an OBSERVATION: a live run whose requesting Turn names the Problem,
     or a recorded act whose `about` names it.
   - A Problem belongs to a Conversation only if a `scoped-to` link places it
     there or the act that produced it happened there. The generic entry door
     writes neither, so such Problems cannot be placed, and are counted, not
     guessed. */
import { useEffect, useRef, useState } from 'react'
import { GOV_HOME, readAddress, writeAddress } from '../../address'
import { useApi } from '../../api'
import type { TypeDef } from '../api'
import './problems.css'
import { problemsSpec, type Decl, type Show } from '../spec/problems'

/** SURFACE-OWNED state only: which Conversation a scope=conversation view was
    bound to where it was first drawn, so pinning it and moving on does not
    silently change what it watches. Never anything about a Problem. */
interface Held { bound?: string }

interface GovRow {
  entry: string
  summary: string | null
  author_alias: string | null
  at: number | null
  placed_at: { conversation: string; name: string | null }[]
  proposed_by: { act: string; actor_alias: string | null; conversation: string | null; conversation_name: string | null; turn: string | null }[]
  superseded_by: string[]
  disputed_by: string[]
}
interface Governed { groups: Record<string, GovRow[]>; totals: Record<string, number> }
interface EntryRead {
  id: string
  missing?: boolean
  kind?: string | null
  body?: Record<string, unknown>
  author_alias?: string | null
  at?: number | null
  superseded_by?: string[]
  deleted?: unknown
  versions?: { current?: { id: string } | string | null }
}
interface Act { id: string; act: string; actor: string; at: number; about: string[]; conversation: string | null; because: string | null }
interface Live { name: string; instance: string; runtime: string; conversation: string | null; turn: string | null; actor: string | null; liveness: string }

/* The last read of each surface, for the send-back payload only. Labelled as
   a read at a time, never as the Problems' state. */
const lastRead = new Map<string, { at: number; rows: unknown[] }>()

export const problems: TypeDef<Decl, Held> = {
  ...problemsSpec,
  Rich({ data: d, state, set, help }) {
    const here = readAddress().conversation
    const conv = d.mode === 'conversation' ? d.conversation ?? state?.bound ?? here : null
    // Bind once, where first drawn. Surface-owned, shown, resettable.
    useEffect(() => {
      if (d.mode === 'conversation' && !d.conversation && !state?.bound && here) set({ bound: here })
    }, [d.mode, d.conversation, state?.bound, here, set])

    const gov = useApi<Governed>('/api/governed?kind=problem&limit=1000')
    const act = d.show.includes('activity')
    // Live movement rereads this at most every 4s: the resolution `useWorking`
    // chose for the same route, enough to watch a run begin and end.
    const working = useApi<{ live: Live[]; why_not?: string }>(act ? '/api/working' : null, { runs: true, runsSpacing: 4000 })
    const ops = useApi<{ operational: Act[] }>(act ? '/api/operational?newest=1&limit=400' : null)
    const convName = useApi<{ name?: string; body?: { name?: string } }>(conv ? `/api/entries/${conv}` : null)

    /* WHAT CAUSED THE LAST READ, measured rather than asserted: every time
       the data objects change identity a read completed. */
    const [reads, setReads] = useState<{ n: number; at: number | null }>({ n: 0, at: null })
    const seen = useRef<unknown[]>([])
    useEffect(() => {
      const now = [gov.data, working.data, ops.data]
      if (now.some((x, i) => x && x !== seen.current[i])) setReads((r) => ({ n: r.n + 1, at: Date.now() }))
      seen.current = now
    }, [gov.data, working.data, ops.data])

    const all = Object.values(gov.data?.groups ?? {}).flat()
    const byId = new Map(all.map((r) => [r.entry, r]))
    let ids: string[]
    let unplaced = 0
    if (d.mode === 'refs') ids = d.refs
    else if (d.mode === 'brain') ids = all.map((r) => r.entry)
    else {
      const inConv = (r: GovRow) =>
        r.placed_at.some((p) => p.conversation === conv) || r.proposed_by.some((p) => p.conversation === conv)
      ids = all.filter(inConv).map((r) => r.entry)
      unplaced = all.filter((r) => !r.placed_at.length && !r.proposed_by.some((p) => p.conversation)).length
    }
    const ended = (id: string) => (byId.get(id)?.superseded_by.length ?? 0) > 0
    const hidden = d.include === 'current' ? ids.filter(ended) : []
    ids = ids.filter((id) => !hidden.includes(id))
    if (d.order !== 'listed')
      ids = [...ids].sort((x, y) => ((byId.get(x)?.at ?? 0) - (byId.get(y)?.at ?? 0)) * (d.order === 'newest' ? -1 : 1))

    const live = working.data?.live ?? []
    useEffect(() => {
      lastRead.set(help.key, { at: reads.at ?? Date.now(), rows: ids.map((id) => ({ id, ...(byId.get(id) ?? { unread: true }) })) })
    })

    const scopeLine =
      d.mode === 'refs' ? `the ${d.refs.length} Problem${d.refs.length === 1 ? '' : 's'} named in refs`
        : d.mode === 'brain' ? 'every Problem in this Brain'
          : conv ? `Problems placed in, or raised in, Conversation “${convName.data?.body?.name ?? conv}”`
            : 'Problems of a Conversation — but no Conversation is open here, so there is nothing to scope to'

    return (
      <div className="rb-pr">
        <div className="rb-pr-scope">
          <b>Watching:</b> {scopeLine}
          {d.mode === 'conversation' && conv && !d.conversation && (
            <span className="rb-pr-own" title="Owned by this surface, not by Mentis"> bound by this surface where it was first drawn</span>
          )}
          {' · '}include={d.include}{hidden.length ? ` (${hidden.length} replaced or deleted not shown)` : ''} · order={d.order}
        </div>
        {gov.error && <p className="rb-bad">Could not read Problems from Mentis: {gov.error}. Nothing is shown in their place.</p>}
        {!gov.data && !gov.error && <p className="rb-muted">Reading Problems from Mentis…</p>}
        {gov.data && ids.length === 0 && (
          <p className="rb-muted">
            {d.mode === 'brain' || all.length === 0
              ? `This Brain holds ${all.length} Problem record${all.length === 1 ? '' : 's'}${hidden.length ? ` (${hidden.length} replaced or deleted)` : ''}.`
              : 'No Problem is placed in, or was raised in, this Conversation.'}
          </p>
        )}
        {ids.length > 0 && (
          <ul className="rb-pr-list">
            {ids.map((id) => <Row key={id} id={id} row={byId.get(id)} d={d} live={live} ops={act ? ops.data?.operational ?? null : null} />)}
          </ul>
        )}
        {d.mode === 'conversation' && gov.data && unplaced > 0 && (
          <p className="rb-pr-unk">
            Unknown: {unplaced} Problem{unplaced === 1 ? '' : 's'} in this Brain {unplaced === 1 ? 'has' : 'have'} no recorded Conversation
            (written through the generic entry door, which records none), so this view cannot say whether {unplaced === 1 ? 'it belongs' : 'they belong'} here.
          </p>
        )}
        <div className="rb-pr-foot">
          <span className="rb-pr-rec">record</span> read from the Problem records ·{' '}
          <span className="rb-pr-obs">observed</span> runtime observation ·{' '}
          <span className="rb-pr-own">surface</span> owned by this surface ·{' '}
          <span className="rb-pr-unk">unknown</span> Mentis cannot say
          <br />
          Last read {reads.at ? new Date(reads.at).toLocaleTimeString() : '—'} (read #{reads.n}). It re-reads whenever the shell's
          existing <code>/api/pulse</code> says the record or a live run moved (asked every 1.2 s while this tab is visible), or when you press{' '}
          <button className="btn quiet" onClick={() => { gov.reload(); working.reload(); ops.reload() }}>Refresh now</button>.
          <br />
          No resolve or close control: Mentis has no act that means “resolved”. Open a Problem in Mentis for what can be done to it
          (edit, delete, dispute, supersede), each of which means what it says.
        </div>
      </div>
    )
  },

  readable(d, a, s) {
    const out = [
      'A live view over Mentis Problem records. Their current state is read from Mentis when shown and is NOT copied here.',
    ]
    if (d.mode === 'refs') out.push(`watches: ${d.refs.join(', ')} (open each in Mentis to see it)`)
    else if (d.mode === 'brain') out.push('watches: every Problem in the Brain it is read in')
    else
      out.push(
        `watches: Problems placed in, or raised in, ${d.conversation ? `Conversation ${d.conversation}` : s?.bound ? `Conversation ${s.bound} (bound by the surface where first drawn)` : 'the Conversation it is read in (not yet bound)'}`,
      )
    out.push(`include: ${d.include === 'current' ? 'current (not replaced, not deleted)' : 'all'}; order: ${d.order}; shows: ${d.show.join(', ')}`)
    if (a.title) out.unshift(`title: ${JSON.stringify(a.title)}`)
    return out.join('\n')
  },

  handoff(d, _a, s, help) {
    const r = lastRead.get(help.key)
    return {
      view: { ...d, bound_conversation: s?.bound ?? null },
      as_last_read: r
        ? { read_at: new Date(r.at).toISOString(), note: 'a read of the records at that time, not their state now', rows: r.rows }
        : null,
    }
  },
}

function when(t: number | null | undefined) {
  return t ? new Date(t * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : 'unknown time'
}

function openInMentis(id: string) {
  const a = readAddress()
  // Close the gallery (if open) so the inspector is visible; the pin dock stays.
  window.dispatchEvent(new CustomEvent('mentis:experimental-close-gallery'))
  window.location.hash = writeAddress({ ...a, gov: { ...GOV_HOME, filters: { ...GOV_HOME.filters }, open: [], item: id } })
}

function Row({ id, row, d, live, ops }: { id: string; row: GovRow | undefined; d: Decl; live: Live[]; ops: Act[] | null }) {
  const e = useApi<EntryRead>(`/api/entries/${id}`)
  const show = (s: Show) => d.show.includes(s)
  const x = e.data
  if (!row && x && (x.missing || x.kind !== 'problem'))
    return (
      <li className="rb-pr-row rb-pr-bad">
        <code>{id}</code>{' '}
        <span className="rb-pr-rec">
          {x.missing ? 'the record holds no such entry' : `this is not a Problem: it is a ${x.kind ?? 'record of no Kind'}`}
        </span>
      </li>
    )
  const text = row?.summary ?? (typeof x?.body?.text === 'string' ? (x.body.text as string) : null)
  const deleted = !!x?.deleted
  const replaced = (row?.superseded_by ?? x?.superseded_by ?? []).length > 0
  const disputed = row?.disputed_by ?? []
  const glyph = deleted ? '✕' : replaced ? '⤳' : disputed.length ? '⚑' : '●'
  const cur = x?.versions?.current
  const currentId = typeof cur === 'string' ? cur : cur?.id
  // Observations. A live run counts only if the Turn that asked for it names this Problem.
  const naming = (ops ?? []).filter((a) => a.about?.includes(id))
  return (
    <li className="rb-pr-row">
      <div className="rb-pr-line">
        <span className="rb-pr-glyph" title="a record fact, not a status">{glyph}</span>
        {show('text') && <span className="rb-pr-text">{text ?? (e.loading ? '…' : '(no text)')}</span>}
        <span className="rb-grow" />
        <button className="btn quiet" onClick={() => openInMentis(id)} title="Open this Problem in the Mentis inspector">Open in Mentis</button>
      </div>
      <div className="rb-pr-facts">
        <code>{id}</code>
        {show('author') && <span className="rb-pr-rec">by {row?.author_alias ?? x?.author_alias ?? 'unknown'}</span>}
        {show('recorded') && <span className="rb-pr-rec">recorded {when(row?.at ?? x?.at)}</span>}
        {show('record') && (
          <span className="rb-pr-rec">
            {deleted ? 'deleted (its line was ended; the record keeps it)'
              : replaced ? `replaced by ${(row?.superseded_by ?? x?.superseded_by ?? []).join(', ')}`
                : 'recorded; not replaced, not deleted'}
            {disputed.length > 0 && ` · disputed by ${disputed.join(', ')} (a challenge; it still stands)`}
            {currentId && currentId !== id && ` · a newer version exists: ${currentId}`}
          </span>
        )}
        {show('record') && <span className="rb-pr-unk">resolved: Mentis records no such fact</span>}
        {show('place') && (
          row?.proposed_by.some((p) => p.conversation) || row?.placed_at.length
            ? <span className="rb-pr-rec">
                {row.placed_at.map((p) => `placed in “${p.name ?? p.conversation}”`).join('; ')}
                {row.proposed_by.filter((p) => p.conversation).map((p) => `raised by ${p.actor_alias ?? 'somebody'} in “${p.conversation_name ?? p.conversation}”`).join('; ')}
              </span>
            : <span className="rb-pr-unk">Conversation: none recorded</span>
        )}
      </div>
      {show('activity') && <Activity id={id} live={live} naming={naming} opsRead={ops !== null} />}
    </li>
  )
}

function Activity({ id, live, naming, opsRead }: { id: string; live: Live[]; naming: Act[]; opsRead: boolean }) {
  return (
    <div className="rb-pr-facts">
      <span className="rb-pr-unk">assigned to: Mentis records no assignee for a Problem</span>
      {live.map((r) => <LiveRun key={r.instance} run={r} id={id} />)}
      {!opsRead ? (
        <span className="rb-pr-unk">recorded activity: not read yet</span>
      ) : naming.length ? (
        <span className="rb-pr-obs">
          last act naming it: {naming[0].act} at {when(naming[0].at)}
          {naming.length > 1 ? ` (${naming.length} in the last 400 acts)` : ''}
        </span>
      ) : (
        <span className="rb-pr-unk">activity: no act in the last 400 names it — unknown, not “idle”</span>
      )}
    </div>
  )
}

/** A live run is shown against this Problem ONLY if the Turn that started it names it. */
function LiveRun({ run, id }: { run: Live; id: string }) {
  const t = useApi<EntryRead>(run.turn ? `/api/entries/${run.turn}` : null)
  if (!t.data || !JSON.stringify(t.data.body ?? {}).includes(id)) return null
  return (
    <span className="rb-pr-obs">
      working now: {run.name} ({run.runtime}, {run.liveness}) on a request that names this Problem
    </span>
  )
}
