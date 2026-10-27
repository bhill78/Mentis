import { useEffect, useMemo, useState } from 'react'
import { CLIENT_HEADERS, useApi, when, type Id } from '../../api'
import { fluidFetch } from '../../fluid/http'
import { useMe } from '../../identity'
import './execution-sheet.css'

/* ------------------------------------------------------------------------ *
 * ONE EXECUTION, AND WHAT IT ACTUALLY RECEIVED.
 *
 * THIS IS ABOUT AN EVENT, NOT ABOUT A THING. The item inspector answers
 * "what is this and does it hold"; this answers "what crossed to that run,
 * once, and how did it get there". Merging them is how "applies" becomes
 * "delivered", so they stay separate surfaces and neither borrows the
 * other's words.
 *
 * THREE ANSWERS, KEPT APART, exactly as the read keeps them apart:
 *   absent   no delivery record names this execution. Nothing was kept, so
 *            nothing may be concluded, and it is NOT "nothing received".
 *   empty    there is a record and it lists no behavioural material. That is
 *            a real answer, read from the record.
 *   unknown  the record cannot say. The payload as rendered is not kept and
 *            no record carries a model. Unknown is never turned into "none".
 *
 * COMPARISON IS ON REQUEST ONLY. Putting what would compose now beside what
 * was delivered then invites reading one as the other, so it is never shown
 * by default, the two are separate cards that are never merged, and each
 * carries its own stamp: AS DELIVERED, or COMPUTED · NOT A RECORD.
 *
 * NO KIND IS NAMED IN THIS FILE. How something reached the execution is read
 * from the scope the composition recorded — never from what the material is.
 * ------------------------------------------------------------------------ */

/* ------------------------------ what the reads return ------------------------------ */
/* Declared here rather than in `api.ts` because these shapes belong to this
   surface and nothing else reads them yet. */

type GroupName =
  | 'persona_selected'
  | 'named'
  | 'placed'
  | 'supplied'
  | 'orientation'
  | 'request'
  | 'other'

/** The GROUPS, in the read's own order. Each is an answer to "how did this
 *  reach me?", which is a different question from "what is it?". */
const GROUPS: GroupName[] = [
  'persona_selected',
  'named',
  'placed',
  'supplied',
  'orientation',
  'request',
  'other',
]

const GROUP_TITLE: Record<GroupName, string> = {
  persona_selected: 'Persona selected for this execution',
  named: 'Named for this execution',
  placed: 'Placed in the Conversation or on the Whole Brain',
  supplied: 'Supplied for this execution only',
  orientation: 'Orientation, computed at the time',
  request: 'The request',
  // The read carries an `other` group for a scope it does not classify. It is
  // not one of the approved six because the approved UI never had one; each
  // line says in the read's own words what scope it was recorded with.
  other: 'Recorded with a scope this does not classify',
}

/** The computed column asks the same question of a different moment, so one
 *  heading changes tense and the rest do not. */
const COMPUTED_TITLE: Partial<Record<GroupName, string>> = {
  orientation: 'Orientation, computed now',
}

interface SourceLine {
  source_kind: string | null
  source_id: Id | null
  scope: string | null
  how: GroupName
  why: string
  /** false for invocation-scoped material: it had no durable identity, and
   *  there is nothing to open and nothing to quote. */
  durable: boolean
  /** Other placements that would have carried the same material; it was
   *  delivered once, under `scope`. Absent where there was one reason. */
  also?: string[]
}

interface PersonaAnswer {
  /** from_the_record | lists_none | no_record — three answers, never merged */
  answer: 'from_the_record' | 'lists_none' | 'no_record'
  persona?: Id
  why?: string
}

interface Sheet {
  execution: Id
  record: 'absent' | 'empty' | 'present'
  records?: Id[]
  participant?: Id | null
  runtime?: string | null
  conversation?: Id | null
  mechanism?: string | null
  at?: number | null
  groups: Record<GroupName, SourceLine[]>
  sources: number
  why?: string | null
  persona: PersonaAnswer
  rendered_payload: { known: boolean; why: string }
  model: { known: boolean; why: string }
}

interface Component {
  source_kind: string | null
  source_id: Id | null
  scope: string | null
  text: string
  why: string
  about: string | null
  also?: string[]
}

interface Context {
  scope: string
  components: Component[]
  conflicts: { about: string | null; components: string[] }[]
  withheld: { source_kind: string | null; source_id: Id | null; why: string }[]
}

interface EntryRead {
  id: Id
  kind: string | null
  family?: string | null
  body: Record<string, unknown>
  fields: string[]
  missing?: boolean
}

interface Act {
  id: Id
  at: number
  actor: Id
  act: string
  execution: Id | null
  runtime: string | null
}

/* --------------------------------- small helpers --------------------------------- */

/** A one-off read for the handful of per-item questions a comparison asks.
 *  `useApi` is one path per hook and these are a list of paths decided at
 *  request time, so they are fetched here — same shape, same refusal. */
async function read<T>(path: string): Promise<T> {
  const res = await fluidFetch(path, { headers: CLIENT_HEADERS })
  const text = await res.text()
  const body: unknown = text ? JSON.parse(text) : null
  if (!res.ok || (body && typeof body === 'object' && 'error' in (body as object)))
    throw new Error((body as { error?: string })?.error ?? res.statusText)
  return body as T
}

/** Material placed across multiple routes is delivered once; the record keeps
 *  the additional reasons in `also`, and so does this line. */
function alsoWords(also?: string[]): string {
  if (!also?.length) return ''
  const hasWholeBrain = also.includes('whole-brain')
  const hasConv = also.some((s) => s.startsWith('conversation:') || s === 'conversation')
  if (hasWholeBrain && hasConv) {
    return ' · also placed in the Conversation and on the Whole Brain, delivered once'
  }
  if (hasWholeBrain) {
    return ' · also placed on the Whole Brain, delivered once'
  }
  if (hasConv) {
    return ' · also placed in the Conversation, delivered once'
  }
  return ` · also ${also.join(', ')}`
}

/** How a component reached an execution, from the SCOPE the composition
 *  recorded — mirrored here only because `/api/context` returns components
 *  ungrouped. It reads scope strings and the composition's own source words;
 *  it never reads what the material is. */
function howOf(c: Component): GroupName {
  const scope = c.scope ?? ''
  const kind = c.source_kind ?? ''
  if (scope === 'invocation:persona') return 'persona_selected'
  if (scope === 'invocation:named') return 'named'
  if (scope === 'brain' || kind.endsWith('orientation')) return 'orientation'
  if (kind === 'request') return 'request'
  if (scope.startsWith('conversation:') || scope === 'whole-brain') return 'placed'
  if (scope === 'invocation') return 'supplied'
  return 'other'
}

/** The first declared field carrying words. The Kind declares its own fields
 *  and their order; nothing here knows what any of them are called. */
function saidBy(e: EntryRead | null | undefined): string | null {
  if (!e || e.missing) return null
  const order = e.fields.length ? e.fields : Object.keys(e.body)
  for (const f of order) {
    const v = e.body[f]
    if (typeof v === 'string' && v.trim()) return v
  }
  return null
}

const stamp = (s: string) => <span className="xs-stamp">{s}</span>

/* ------------------------------------ props ------------------------------------ */

export interface ExecutionSheetProps {
  /** the execution this sheet is about */
  execution: Id
  /** what the reader came from, NAMED — the approved Back never says just
   *  "Back". Defaults to the delivery question the sheet is opened under. */
  backLabel?: string
  onBack?: () => void
  onClose?: () => void
  /** open the governed item behind a record line, in the one inspector */
  onOpenEntry?: (entry: Id) => void
  /** "Trace why this reached it" — the applicability investigation */
  onTrace?: (execution: Id) => void
  /** from the absent page: preview what would compose now instead. The seed
   *  is what operational history could say about this execution, so the
   *  preview opens on the same Participant and place rather than blank. */
  onPreview?: (seed: { participant: Id | null; conversation: Id | null }) => void
}

/* ------------------------------------ the sheet ------------------------------------ */

export default function ExecutionSheet({
  execution,
  backLabel = 'What executions received',
  onBack,
  onClose,
  onOpenEntry,
  onTrace,
  onPreview,
}: ExecutionSheetProps) {
  const sheet = useApi<Sheet>(`/api/governance/execution?execution=${encodeURIComponent(execution)}`)
  // NEVER BY DEFAULT. The reader asks for the comparison, every time — and
  // until they do, nothing about now is even fetched.
  const [comparing, setComparing] = useState(false)
  const d = sheet.data
  const ctx = useApi<Context>(comparing && d ? contextPath(d) : null)

  // A new execution is a new question. Anything asked of the last one is not
  // carried over, or "compare" would follow the reader around.
  useEffect(() => setComparing(false), [execution])

  return (
    <div className="xs">
      <div className="xs-head">
        <div className="xs-eyebrow">Execution</div>
        <h2 className="mono">{execution}</h2>
        <div className="xs-actions">
          {onBack && (
            <button onClick={onBack}>← Back to {backLabel}</button>
          )}
          {onTrace && <button onClick={() => onTrace(execution)}>Trace why this reached it →</button>}
          {d && d.record !== 'absent' && (
            <button onClick={() => setComparing(!comparing)}>
              {comparing ? 'Hide comparison' : 'Compare with what would compose now'}
            </button>
          )}
          {onClose && <button onClick={onClose}>Close</button>}
        </div>
      </div>

      {sheet.error && <p className="xs-error">API error: {sheet.error}</p>}
      {sheet.loading && !d && <p className="xs-aside">loading…</p>}

      {d && d.record === 'absent' && (
        <AbsentPage execution={execution} onPreview={onPreview} />
      )}

      {d && d.record !== 'absent' && (
        <>
          <IdentityRow d={d} />
          <div className="xs-cards">
            <RecordCard d={d} onOpenEntry={onOpenEntry} />
            {comparing && <ComputedCard d={d} ctx={ctx} />}
          </div>
          {comparing && <Comparison d={d} ctx={ctx.data} />}
        </>
      )}
    </div>
  )
}

/* --------------------------------- identity row --------------------------------- */

/** The five identity cells. Each says what it is, what the record says, and
 *  WHICH QUESTION IT ANSWERS — the sub-label is not decoration: "carrier only"
 *  is the whole reason a runtime is on this row at all. */
function IdentityRow({ d }: { d: Sheet }) {
  /* NAMED WHERE THE RECORD NAMES THEM, AND NOT OTHERWISE. These two cells are
     read by somebody asking who ran this and as what, and both printed the
     bare identifier although the alias and the Persona's name are what the
     record already answers everywhere else in this workspace. An id nobody
     named stays an id — that is a true name, and a placeholder would not be —
     and naming one never changes WHICH of the three Persona answers is being
     given. */
  const { person } = useMe()
  const personas = useApi<{ personas: { persona: Id; name: string }[] }>('/api/personas')
  const nameOfPersona = (id: Id) =>
    personas.data?.personas.find((p) => p.persona === id)?.name ?? id

  const persona =
    d.persona.answer === 'from_the_record'
      ? {
          value: d.persona.persona ? nameOfPersona(d.persona.persona) : '',
          sub: 'from the record',
        }
      : d.persona.answer === 'lists_none'
        ? { value: 'UNKNOWN', sub: 'record lists none: none selected, or withheld' }
        : { value: 'UNKNOWN', sub: 'no record to say' }
  const cells = [
    {
      label: 'Participant',
      value: d.participant ? (person(d.participant)?.alias ?? d.participant) : '—',
      sub: 'durable identity',
    },
    { label: 'Persona', value: persona.value, sub: persona.sub },
    { label: 'Runtime', value: d.runtime ?? '—', sub: 'carrier only' },
    {
      label: 'Where',
      value: d.conversation ?? 'Brain scope',
      sub: d.conversation ? 'Conversation' : 'no Conversation',
    },
    { label: 'When', value: d.at ? when(d.at) : '—', sub: 'operational history' },
  ]
  return (
    <div className="xs-ids">
      {cells.map((c) => (
        <div key={c.label}>
          <div className="xs-id-label">{c.label}</div>
          <div className="xs-id-value">{c.value}</div>
          <div className="xs-id-sub">{c.sub}</div>
        </div>
      ))}
    </div>
  )
}

/* ------------------------------ the record, as delivered ------------------------------ */

function RecordCard({ d, onOpenEntry }: { d: Sheet; onOpenEntry?: (e: Id) => void }) {
  return (
    <section className="xs-card">
      <div className="xs-card-head">
        <h3>What it received</h3>
        {stamp('AS DELIVERED')}
      </div>
      <div className="xs-card-meta">
        {(d.records ?? []).join(' · ')}
        {d.at ? ` · ${when(d.at)}` : ''}
        {d.mechanism ? ` · mechanism: ${d.mechanism}` : ''}
      </div>
      {/* UNKNOWN, AND SAID SO. No delivery record carries a model, which is a
          different answer from a model of "none". */}
      <div className="xs-card-meta" title={d.model.why}>
        model: not recorded
      </div>

      {d.record === 'empty' && (
        <p className="xs-note">
          The record lists <strong>no behavioural material</strong>. That is an empty list, read
          from the record, not an unknown.
        </p>
      )}

      {d.record === 'present' &&
        GROUPS.map((g) => (
          <RecordGroup key={g} group={g} lines={d.groups[g] ?? []} persona={d.persona} onOpenEntry={onOpenEntry} />
        ))}
    </section>
  )
}

function RecordGroup({
  group,
  lines,
  persona,
  onOpenEntry,
}: {
  group: GroupName
  lines: SourceLine[]
  persona: PersonaAnswer
  onOpenEntry?: (e: Id) => void
}) {
  // A RECORD THAT LISTS NO PERSONA IS NOT A RECORD OF "NO PERSONA". The group
  // stays, and says which question is open rather than disappearing.
  const missingPersona = group === 'persona_selected' && lines.length === 0
  if (lines.length === 0 && !missingPersona) return null
  return (
    <div className="xs-group">
      <div className="xs-group-title">{GROUP_TITLE[group]}</div>
      {missingPersona ? (
        <p className="xs-note" title={persona.why}>
          The record lists no Persona. Whether none was selected or one was withheld:{' '}
          <strong>UNKNOWN</strong>.
        </p>
      ) : (
        <ul className="xs-list">
          {lines.map((l, i) => (
            <RecordLine key={`${l.source_id ?? l.scope}-${i}`} line={l} onOpenEntry={onOpenEntry} />
          ))}
        </ul>
      )}
    </div>
  )
}

/** One line of the record, and what expanding it can honestly say.
 *
 *  THE TEXT AND THE PAYLOAD ARE TWO DIFFERENT ANSWERS. Entries are immutable,
 *  so the source's own words can be shown exactly; how they were assembled
 *  into what actually went out is not kept, and that is Unknown. Showing the
 *  first and letting it read as the second is the mistake this dl exists to
 *  prevent. */
function RecordLine({ line, onOpenEntry }: { line: SourceLine; onOpenEntry?: (e: Id) => void }) {
  const [open, setOpen] = useState(false)
  const entry = useApi<EntryRead>(open && line.source_id ? `/api/entries/${line.source_id}` : null)
  const text = saidBy(entry.data)
  return (
    <li className="xs-line">
      <button className="xs-line-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="xs-caret">{open ? '▾' : '▸'}</span>
        <span className="xs-line-what">{line.source_id ?? line.source_kind ?? line.scope}</span>
        <span className="xs-tag">{line.why}{alsoWords(line.also)}</span>
      </button>
      {open && (
        <dl className="xs-dl">
          <dt>Source identity</dt>
          <dd>
            {line.source_id ? (
              <>
                {onOpenEntry ? (
                  <button className="xs-link" onClick={() => onOpenEntry(line.source_id as Id)}>
                    {line.source_id}
                  </button>
                ) : (
                  <span className="mono">{line.source_id}</span>
                )}
                {entry.data?.kind ? ` · ${entry.data.kind}` : ''}
              </>
            ) : (
              <em>none: this component has no durable identity</em>
            )}
          </dd>

          <dt>Scope</dt>
          <dd className="mono">{line.scope ?? '—'}{line.also?.length ? ` (also ${line.also.join(', ')})` : ''}</dd>

          {line.durable ? (
            <>
              <dt>Text of this source</dt>
              <dd>
                {entry.loading && 'reading the record…'}
                {text !== null && <span className="xs-quote">{text}</span>}
                {!entry.loading && text === null && <em>the record holds no words in its declared fields</em>}
                <p className="xs-aside">
                  Entries are immutable, so this is exactly the source's text. It is not necessarily
                  the text as rendered.
                </p>
              </dd>
            </>
          ) : (
            <>
              <dt>Its text</dt>
              <dd>
                <strong>Unknown</strong>. It existed only for this execution and ended with it.
              </dd>
            </>
          )}

          <dt>As rendered into the payload</dt>
          <dd>
            <strong>Unknown</strong>. The record names sources; it does not keep the assembled text.
          </dd>
        </dl>
      )}
    </li>
  )
}

/* ------------------------------- the absent answer ------------------------------- */

/** NO RECORD IS NOT AN EMPTY RECORD.
 *
 *  Operational history can still say the execution happened, and it is read
 *  for exactly that and nothing more: who, on what, and when. What crossed is
 *  absent, and the page refuses to reconstruct it from what stands now —
 *  which would answer a question about the past with a fact about the
 *  present. */
function AbsentPage({
  execution,
  onPreview,
}: {
  execution: Id
  onPreview?: (seed: { participant: Id | null; conversation: Id | null }) => void
}) {
  // Read only on this page, because only this page has a question operational
  // history can answer. No route selects acts by execution, so the acts are
  // read and the ones naming this execution are kept.
  const ops = useApi<{ operational: Act[] }>('/api/operational?limit=400&newest=1')
  const happened = (ops.data?.operational ?? []).filter((a) => a.execution === execution)
  const first = happened[happened.length - 1] ?? null
  return (
    <section className="xs-card">
      <p className="xs-lede">No delivery record exists for this execution.</p>
      <p className="xs-note">
        {first ? (
          <>
            Operational history shows that it happened: {first.actor} on {first.runtime ?? 'an unnamed runtime'} at{' '}
            {when(first.at)}.{' '}
          </>
        ) : ops.loading ? (
          'reading operational history… '
        ) : (
          'Operational history does not name it either. '
        )}
        Nothing records what crossed to it. What it received is{' '}
        <strong>absent from the record</strong>. It is not "nothing", and it will not be
        reconstructed from what stands.
      </p>
      {onPreview && (
        <div className="xs-actions">
          <button onClick={() => onPreview({ participant: first?.actor ?? null, conversation: null })}>
            Preview what would compose now instead
          </button>
        </div>
      )}
    </section>
  )
}

/* ---------------------------- the computed side, on request ---------------------------- */

/** What `/api/context` answers for the same Participant and place.
 *
 *  THE PERSONA IS ONLY PASSED WHEN THE RECORD NAMES ONE. A record that lists
 *  none cannot say whether none was selected or one was withheld, so
 *  composing "without a Persona" here would quietly turn UNKNOWN into
 *  "none" — the one substitution the whole surface exists to refuse. */
function contextPath(d: Sheet): string {
  const p = new URLSearchParams()
  if (d.participant) p.set('participant', d.participant)
  if (d.conversation) p.set('conversation', d.conversation)
  if (d.persona.answer === 'from_the_record' && d.persona.persona) p.set('persona', d.persona.persona)
  return `/api/context?${p.toString()}`
}

interface ContextState {
  data: Context | null
  error: string | null
  loading: boolean
}

function ComputedCard({ d, ctx }: { d: Sheet; ctx: ContextState }) {
  const personaUnknown = d.persona.answer !== 'from_the_record'
  const byGroup = useMemo(() => {
    const out: Record<GroupName, Component[]> = {
      persona_selected: [], named: [], placed: [], supplied: [], orientation: [], request: [], other: [],
    }
    for (const c of ctx.data?.components ?? []) out[howOf(c)].push(c)
    return out
  }, [ctx.data])

  return (
    <section className="xs-card">
      <div className="xs-card-head">
        <h3>If it were composed now</h3>
        {stamp('COMPUTED · NOT A RECORD')}
      </div>
      <div className="xs-card-meta">from what stands at {when(Date.now() / 1000)}</div>
      {ctx.error && <p className="xs-error">API error: {ctx.error}</p>}
      {ctx.loading && !ctx.data && <p className="xs-aside">computing…</p>}

      {GROUPS.map((g) => {
        const lines = byGroup[g]
        const unknownHere = g === 'persona_selected' && personaUnknown
        if (!lines.length && !unknownHere) return null
        return (
          <div className="xs-group" key={g}>
            <div className="xs-group-title">{COMPUTED_TITLE[g] ?? GROUP_TITLE[g]}</div>
            {unknownHere ? (
              <p className="xs-note">
                <strong>UNKNOWN</strong> · not computed, because the historical selection is not
                known
              </p>
            ) : (
              <ul className="xs-list">
                {lines.map((c, i) => (
                  <li className="xs-line" key={`${c.source_id ?? c.scope}-${i}`}>
                    <div className="xs-line-head">
                      <span className="xs-line-what">{c.source_id ?? c.source_kind}</span>
                      <span className="xs-tag">{c.why}{alsoWords(c.also)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}

      {/* WHAT WOULD NOT REACH IT, AND THE MACHINE'S OWN REASON. Withholding
          something silently is how a composition stops being answerable. */}
      {(ctx.data?.withheld ?? []).length > 0 && (
        <div className="xs-group">
          <div className="xs-group-title">Would be withheld</div>
          <ul className="xs-list">
            {(ctx.data?.withheld ?? []).map((w, i) => (
              <li className="xs-line" key={`${w.source_id ?? w.source_kind}-${i}`}>
                <div className="xs-line-head">
                  <span className="xs-line-what">{w.source_id ?? w.source_kind}</span>
                  <span className="xs-tag">{w.why}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(ctx.data?.conflicts ?? []).map((k, i) => (
        <p className="xs-note" key={i}>
          {k.components.length} components speak to “{k.about}”. Surfaced, not resolved.
        </p>
      ))}
    </section>
  )
}

/* --------------------------------- the diff summary --------------------------------- */

interface ThenNow {
  then: string
  now: string
  /** when it was established, where the timeline records an establishing act */
  established_at: number | null
  /** when it was superseded, where it was */
  superseded_at: number | null
}

/** THEN AND NOW ARE TWO ANSWERS AND ARE ASKED FOR SEPARATELY.
 *
 *  `stands(as_at=)` says what the record said at the moment of delivery;
 *  `item_history` supplies the dates the tags quote. Neither is derived from
 *  the other and neither is guessed: an item the reads cannot speak for is
 *  left without a tag rather than given the likeliest one. */
function useThenNow(entries: Id[], asAt: number | null): Map<Id, ThenNow> {
  const key = entries.join(',')
  const [out, setOut] = useState<Map<Id, ThenNow>>(new Map())
  useEffect(() => {
    if (!asAt || !key) {
      setOut(new Map())
      return
    }
    let alive = true
    const ids = key.split(',')
    Promise.all(
      ids.map(async (id) => {
        const [st, hist] = await Promise.all([
          read<{ then: { state: string }; now: { state: string } }>(
            `/api/governance/standing?entry=${encodeURIComponent(id)}&as_at=${asAt}`,
          ),
          read<{ timeline: { entry: Id; established: { at: number }[]; superseded_by: { at: number }[] }[] }>(
            `/api/governance/history?entry=${encodeURIComponent(id)}`,
          ),
        ])
        const row = hist.timeline.find((r) => r.entry === id)
        return [
          id,
          {
            then: st.then.state,
            now: st.now.state,
            established_at: row?.established?.[0]?.at ?? null,
            superseded_at: row?.superseded_by?.[0]?.at ?? null,
          },
        ] as const
      }),
    )
      .then((pairs) => alive && setOut(new Map(pairs)))
      .catch(() => alive && setOut(new Map()))
    return () => {
      alive = false
    }
  }, [key, asAt])
  return out
}

/** The comparison's own account of itself.
 *
 *  IT NEVER REPORTS "0 DIFFERENCES" AGAINST AN UNKNOWN PERSONA. Where the
 *  record lists no Persona, the Persona is dropped from BOTH sides, the count
 *  is worded as being over the known dimensions, and which those are is
 *  named. Treating UNKNOWN as "none" and then finding no difference would be
 *  a comparison that agreed with itself about something nobody recorded. */
function Comparison({ d, ctx }: { d: Sheet; ctx: Context | null }) {
  const personaUnknown = d.persona.answer !== 'from_the_record'

  // The compared dimensions, and only those: the Persona (when it is known),
  // what was placed, and what was named. Orientation and the request are
  // recomputed by their nature and are not differences anybody chose.
  const compared: GroupName[] = personaUnknown
    ? ['named', 'placed']
    : ['persona_selected', 'named', 'placed']

  const delivered = compared.flatMap((g) => (d.groups[g] ?? []).filter((l) => l.source_id))
  const deliveredIds = delivered.map((l) => l.source_id as Id)
  const computed = (ctx?.components ?? []).filter(
    (c) => c.source_id && compared.includes(howOf(c)),
  )
  const computedIds = new Set(computed.map((c) => c.source_id as Id))
  const deliveredSet = new Set(deliveredIds)

  // `useThenNow` keys on the ids themselves, so a fresh array each render
  // costs nothing and there is no memo to keep honest.
  const facts = useThenNow([...new Set([...deliveredIds, ...computedIds])], d.at ?? null)

  const goneFromNow = deliveredIds.filter((id) => !computedIds.has(id))
  const newSinceThen = [...computedIds].filter((id) => !deliveredSet.has(id))
  const ended = goneFromNow.filter((id) => facts.get(id)?.now === 'ended')
  const differences = goneFromNow.length + newSinceThen.length
  const dimensions = personaUnknown ? 'placed and named material' : 'Persona, placed and named material'
  const hasInvocationOnly = Object.values(d.groups).some((ls) => ls.some((l) => !l.durable))
  const namedMaterial = (d.groups.named ?? []).length > 0

  return (
    <section>
      <p className="xs-section-title">The comparison</p>

      {personaUnknown && (
        <p className="xs-banner">
          <strong>Not an exact comparison.</strong> The record lists no Persona and cannot say
          whether none was selected or one was withheld, so the historical Persona is{' '}
          <strong>UNKNOWN</strong>. It is left out of both sides and is not treated as “none”.
        </p>
      )}

      <p className="xs-note">
        <strong>
          {differences === 0
            ? 'No difference found in the known dimensions'
            : `${differences} difference${differences === 1 ? '' : 's'} in the known dimensions`}
        </strong>{' '}
        ({dimensions})
      </p>

      <p className="xs-note">
        {goneFromNow.length} received then {goneFromNow.length === 1 ? 'has' : 'have'} since ended
        {ended.length > 0 && ` (${ended.join(', ')})`}. {newSinceThen.length} standing now{' '}
        {newSinceThen.length === 1 ? 'was' : 'were'} not received then.
      </p>

      {personaUnknown && (
        <p className="xs-note">
          Whether the Persona differs: <strong>UNKNOWN</strong>.
        </p>
      )}

      {hasInvocationOnly && (
        <p className="xs-note">
          The record also lists invocation material with no durable identity. Its text is{' '}
          <strong>UNKNOWN</strong> and is not recomposed.
        </p>
      )}

      <p className="xs-note">
        The right-hand column is computed for the same Participant and Conversation
        {personaUnknown ? '' : ' and the same Persona'}
        {namedMaterial
          ? '. Material named for this execution only is not recomposed: no read accepts it'
          : ' and named material'}
        . It is not a record.
      </p>

      {/* THE PER-LINE TAGS, which is where then and now are actually told
          apart. They hang off the comparison rather than off the record card,
          because the record says nothing about now and must not appear to. */}
      <div className="xs-cards">
        <div className="xs-card">
          <div className="xs-card-head">
            <h3>What it received</h3>
            {stamp('AS DELIVERED')}
          </div>
          <ul className="xs-list">
            {delivered.map((l) => {
              const f = facts.get(l.source_id as Id)
              const tag = !f
                ? null
                : f.now === 'ended'
                  ? `ended ${f.superseded_at ? when(f.superseded_at) : ''}`.trim()
                  : computedIds.has(l.source_id as Id)
                    ? 'still stands'
                    : 'not delivered now'
              return (
                <li className="xs-line" key={l.source_id}>
                  <div className="xs-line-head">
                    <span className="xs-line-what">{l.source_id}</span>
                    {tag && <span className="xs-tag">{tag}</span>}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>

        <div className="xs-card">
          <div className="xs-card-head">
            <h3>If it were composed now</h3>
            {stamp('COMPUTED · NOT A RECORD')}
          </div>
          <ul className="xs-list">
            {computed.map((c) => {
              const id = c.source_id as Id
              const f = facts.get(id)
              const tag = deliveredSet.has(id)
                ? 'received then too'
                : !f
                  ? 'not received then'
                  : f.then === 'stands'
                    ? 'stood then; not in this record'
                    : `not received then${f.established_at ? ` · did not stand until ${when(f.established_at)}` : ''}`
              return (
                <li className="xs-line" key={id}>
                  <div className="xs-line-head">
                    <span className="xs-line-what">{id}</span>
                    <span className="xs-tag">{tag}</span>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      </div>
    </section>
  )
}
