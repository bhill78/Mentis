import { useMemo, useState } from 'react'
import { clock, dayOf, useApi, when, type Id } from '../../api'
import './HistoryQuestions.css'

/* ------------------------------------------------------------------------ *
 * HISTORY IS A QUESTION SOMEBODY ASKS, NEVER A MODE THE PAGE IS IN.
 *
 * There is no "as at" switch here and there never was one in the approved
 * design: a page-wide time mode makes every surface answer a question nobody
 * asked, and leaves a reader unable to tell a historical answer from the
 * present one. Instead there are four questions, asked one at a time. Each
 * answer is MARKED as History and carries a Back that names the lens it was
 * asked from, so the way out is the way in.
 *
 * AN EMPTY ANSWER IS AN ANSWER. Every one of the four says, in its own words,
 * that the record has nothing to report for this scope — "No governance acts
 * in this period. An empty answer." — rather than rendering an empty table and
 * letting the reader decide whether that meant nothing happened or nothing
 * was looked at.
 *
 * ABSENT, EMPTY AND UNKNOWN ARE THREE DIFFERENT ANSWERS and are never merged.
 * An execution with no delivery record is ABSENT — not zero sources. A record
 * listing no behavioural material is EMPTY, read from the record. And a
 * participant who has never opened Governance has no last look for anything to
 * be since, which is absent too, and is said as such.
 *
 * COUNTS ARE RECORDS, NOT SCORES. Everything counted here is a count of
 * delivery records. It says how often something was named, never how good it
 * is, never that anybody read it — and where no record names something, it is
 * UNCOUNTED rather than counted as zero.
 * ------------------------------------------------------------------------ */

export type Question = 'changed' | 'received' | 'used' | 'ended'

/** The four, as they are asked. The title is the question, because the
 *  question is what the reader chose and what the answer is of. */
export const QUESTIONS: { q: Question; title: string }[] = [
  { q: 'changed', title: 'What changed since I last looked?' },
  { q: 'received', title: 'What did executions here actually receive?' },
  { q: 'used', title: 'Which Personas and named material were actually used here?' },
  { q: 'ended', title: 'What has ended here, and what replaced it?' },
]

/* ------------------------------------------------------------------ types -- */

interface ChangedAct {
  act: Id
  at: number
  what: string
  actor: Id | null
  conversation: Id | null
  about: Id[] | null
  because: string | null
  /** what the act itself recorded beyond the entries it names. The feed has
   *  always carried it; this shape left it out, so an act whose two sides
   *  live here and NOT in `about` could not be said correctly. */
  detail: Record<string, unknown> | null
}

interface Changed {
  error?: string
  acts?: ChangedAct[]
  total?: number
  empty?: string | null
}

/** A catch-up is a PAIR of arrivals and the acts between them, so `bounded`
 *  is the fact that matters: unbounded with no arrivals is ABSENT, and
 *  unbounded with one arrival bounds nothing. Neither is "nothing changed". */
interface Since {
  error?: string
  arrivals?: number
  bounded?: boolean
  window?: { from: number; to: number } | null
  changed?: Changed | null
  why?: string
}

interface ReceivedRow {
  execution: Id
  answer: 'absent' | 'empty' | 'received'
  sources?: number
  participant?: Id | null
  runtime?: string | null
  conversation?: Id | null
  at?: number | null
}

interface Received {
  error?: string
  executions?: ReceivedRow[]
  total?: number
  empty?: string | null
}

interface UsedRow {
  entry: Id
  records: number
}

interface Used {
  error?: string
  personas?: UsedRow[]
  named_material?: UsedRow[]
  records?: number
  records_naming_no_persona?: number
  empty?: string | null
}

interface EndedRow {
  entry: Id
  kind: string | null
  state: string
  never_held: boolean
  replaced_by: Id[]
  acts: { reason: string | null; at: number }[]
}

interface Ended {
  error?: string
  ended?: EndedRow[]
  total?: number
  empty?: string | null
}

interface GovernedRow {
  entry: Id
  kind: string
  state: string | null
  summary: string
}

interface Governed {
  groups?: Record<string, GovernedRow[]>
}

interface Participants {
  participants?: { participant: Id; alias: string }[]
}

interface ConversationsList {
  conversations?: { id: Id; name: string }[]
}

/* ---------------------------------------------------------------- words --- */

/** The governance acts, said the way a person says them. These are ACT names
 *  from the record's own vocabulary, not Kinds, and nothing here branches on
 *  what the material is. */
const VERB: Record<string, string> = {
  'material-proposed': 'proposed',
  /* PUT FORWARD TO REPLACE SOMETHING, which is not the same as proposed and
     not the same as superseded: nothing has ended. The change feed carried
     the act and this map had no word for it, so the row said the raw act
     name or nothing at all. */
  'supersession-proposed': 'proposed as a replacement for',
  'material-established': 'established',
  'material-superseded': 'superseded',
  'material-disputed': 'disputed',
  'dispute-set-aside': 'set aside',
  'material-revised': 'revised',
  /* uiux/edit: append-only Edit and Delete */
  'material-edited': 'edited (new version)',
  'material-deleted': 'deleted',
}

/** The two sides of a supersession proposal, from the act's own detail, or
 *  null where the record does not carry them. Nothing is inferred from
 *  `about`: it holds both sides in one list and cannot say which is which. */
function proposalOf(
  detail: Record<string, unknown> | null,
): { replacement: Id; predecessors: Id[] } | null {
  const rep = detail?.replacement
  const preds = detail?.predecessors
  if (typeof rep !== 'string' || !Array.isArray(preds) || preds.length === 0) return null
  return { replacement: rep as Id, predecessors: preds as Id[] }
}

function clip(s: string, n = 72): string {
  const t = (s || '').replace(/\s+/g, ' ').trim()
  return t.length <= n ? t : t.slice(0, n - 1) + '…'
}

/** A list said the way a person says one. */
function andList(xs: string[]): string {
  if (xs.length === 0) return ''
  if (xs.length === 1) return xs[0]
  return xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]
}

/** Said in words, never by a hue alone, and taken from the server's own
 *  classification so that two surfaces cannot disagree about what a word
 *  means. `ended` used to hold; `replaced` never did. */
const STATE_SAID: Record<string, string> = {
  candidate: 'proposed',
  stands: 'stands',
  ended: 'ended',
  replaced: 'replaced before establishment',
}

/** Everything the register holds, flattened, so an id in an act can be said as
 *  the material it names. An id nobody has a row for stays an id: a guess
 *  would be worse than an identifier, and a standing word nobody computed
 *  stays absent rather than becoming "does not stand". */
function useNames(): {
  name: (id: Id) => string
  kindOf: (id: Id) => string | null
  standing: (id: Id) => string | null
} {
  const reg = useApi<Governed>('/api/governed?limit=500')
  const rows = useMemo(
    () => Object.values(reg.data?.groups ?? {}).flat() as GovernedRow[],
    [reg.data],
  )
  const by = useMemo(() => new Map(rows.map((r) => [r.entry, r])), [rows])
  return {
    name: (id) => {
      const r = by.get(id)
      return r ? `“${clip(r.summary)}”` : id
    },
    kindOf: (id) => by.get(id)?.kind ?? null,
    standing: (id) => {
      const st = by.get(id)?.state
      return st ? (STATE_SAID[st] ?? null) : null
    },
  }
}

/* ----------------------------------------------------------------- menu --- */

export interface HistoryMenuProps {
  /** what the reader is looking at now, so the question can be asked OF it
   *  and the answer can name the way back. */
  lens: string
  onAsk: (q: Question) => void
}

/** "Ask a historical question" — four questions, and no page mode. */
export function HistoryMenu({ lens, onAsk }: HistoryMenuProps) {
  const [open, setOpen] = useState(false)
  return (
    <div className="hq-menu">
      <button
        className={'hq-menu-btn' + (open ? ' on' : '')}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        title={`Ask a historical question of ${lens}. Asking records nothing.`}
      >
        Ask a historical question
      </button>
      {open && (
        <ul className="hq-menu-list">
          {QUESTIONS.map((x) => (
            <li key={x.q}>
              <button
                className="hq-menu-item"
                onClick={() => {
                  setOpen(false)
                  onAsk(x.q)
                }}
              >
                {x.title}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/* --------------------------------------------------------------- answer --- */

export interface HistoryAnswerProps {
  question: Question
  /** the Conversation the question is asked of, or null for the whole Brain.
   *  The lede says which, because "here" means different things. */
  conversation: Id | null
  /** who is asking. Only "what changed since I last looked" needs it — a last
   *  look is a person's arrival, and without a person there is none. */
  me: Id | null
  /** what the reader was looking at, named on the way back. */
  lens: string
  onBack: () => void
  /** open one execution's record. Navigation belongs to whoever owns the
   *  address, so this asks rather than routing. */
  onOpenExecution?: (execution: Id) => void
  onInspect?: (entry: Id) => void
}

export default function HistoryAnswer(props: HistoryAnswerProps) {
  const { question, lens, onBack } = props
  const title = QUESTIONS.find((x) => x.q === question)?.title ?? question
  return (
    <section className="hq" aria-label={`History · ${title}`}>
      {/* MARKED AS HISTORY, AND THE WAY BACK NAMES WHERE IT CAME FROM. A
          historical answer that looks like the present is the whole failure
          this marking exists to prevent. */}
      <p className="hq-marker">
        <span className="hq-tag">History</span> · {title}
      </p>
      <button className="hq-back" onClick={onBack}>
        ‹ Back to {lens}
      </button>
      {question === 'changed' && <Changed {...props} />}
      {question === 'received' && <ReceivedAnswer {...props} />}
      {question === 'used' && <UsedAnswer {...props} />}
      {question === 'ended' && <EndedAnswer {...props} />}
    </section>
  )
}

/* ------------------------------------------------- A8a · what changed --- */

function Changed({ conversation, me, onInspect }: HistoryAnswerProps) {
  const [scope, setScope] = useState<'since' | 'all'>('since')
  const here = conversation ? 'here' : 'in this Brain'
  const names = useNames()
  const people = useApi<Participants>('/api/participants')
  const aliasOf = (id: Id | null) =>
    (id && people.data?.participants?.find((p) => p.participant === id)?.alias) || id || 'somebody'

  const q = conversation ? '&conversation=' + encodeURIComponent(conversation) : ''
  /* ASKING RECORDS NOTHING. `/api/governance/since` is a read: the only
     last-looked fact is an arrival, and an arrival is recorded when somebody
     opens Governance, not when they ask what changed. */
  const since = useApi<Since>(
    me ? '/api/governance/since?participant=' + encodeURIComponent(me) + q : null,
  )
  const all = useApi<Changed>('/api/governance/questions?question=changed' + q)

  const sinceActs = since.data?.changed?.acts ?? []
  const allActs = all.data?.acts ?? []
  const bounded = since.data?.bounded === true
  const acts = scope === 'since' && bounded ? sinceActs : allActs

  const days = useMemo(() => {
    const out: { day: string; rows: ChangedAct[] }[] = []
    for (const a of [...acts].sort((x, y) => y.at - x.at)) {
      const d = dayOf(a.at)
      const last = out[out.length - 1]
      if (last && last.day === d) last.rows.push(a)
      else out.push({ day: d, rows: [a] })
    }
    return out
  }, [acts])

  return (
    <>
      <p className="hq-lede">
        Governance acts on material that matters {here}: proposed, established, superseded,
        disputed, set aside, asked and answered. Not a Conversation timeline.
      </p>

      <div className="hq-filter" role="group" aria-label="which period">
        <button
          className={'hq-chip' + (scope === 'since' ? ' on' : '')}
          disabled={!bounded}
          onClick={() => setScope('since')}
        >
          {bounded && since.data?.window
            ? `Since you last looked (${when(since.data.window.from)})`
            : 'Since you last looked'}
          {bounded ? ` · ${sinceActs.length}` : ''}
        </button>
        <button
          className={'hq-chip' + (scope === 'all' || !bounded ? ' on' : '')}
          onClick={() => setScope('all')}
        >
          All · {allActs.length}
        </button>
      </div>

      {/* THE TWO UNBOUNDED ANSWERS, SAID IN THE RECORD'S OWN WORDS. Never
          arrived is ABSENT, not zero; one arrival bounds nothing. Neither is
          allowed to render as "nothing changed since you last looked". */}
      {!me && (
        <p className="hq-absent">
          A last look is somebody&rsquo;s arrival. Without a participant there is no last
          look for anything to be since: absent, not zero.
        </p>
      )}
      {me && since.data && !bounded && since.data.why && (
        <p className="hq-absent">{since.data.why}</p>
      )}

      {days.length === 0 ? (
        <p className="hq-empty">No governance acts in this period. An empty answer.</p>
      ) : (
        days.map((d) => (
          <div key={d.day} className="hq-day">
            <h3 className="hq-day-head">{d.day}</h3>
            <ul className="hq-list">
              {d.rows.map((a) => {
                const about = a.about ?? []
                const kind = about.map(names.kindOf).find(Boolean) ?? null
                /* A supersession names every predecessor it ended, because
                   one successor may end several and saying only the first
                   would leave the others ended by nothing nameable. */
                /* AND A PROPOSAL NAMES THE TWO SIDES APART. Its `about` is
                   every predecessor AND the replacement, so listing it flat
                   would name the replacement as one of the things it
                   replaces. The act's own detail keeps them apart. */
                const prop =
                  a.what === 'supersession-proposed' ? proposalOf(a.detail) : null
                const said = prop
                  ? `${VERB[a.what]} ${andList(prop.predecessors.map(names.name))}: ${names.name(prop.replacement)}`
                  : a.what === 'material-superseded' && about.length > 1
                    ? `superseded ${andList(about.map(names.name))}`
                    : `${VERB[a.what] ?? a.what} ${andList(about.map(names.name))}`
                return (
                  <li key={a.act} className="hq-act">
                    <span className="hq-time">{clock(a.at)}</span>
                    {kind && <span className="hq-kind">{kind}</span>}
                    <span className="hq-said">
                      <span className="hq-who">{aliasOf(a.actor)}</span> {said}
                    </span>
                    {/* THE REASON IN THE WORDS IT WAS GIVEN IN, quoted rather
                        than paraphrased. Absent where none was given. */}
                    {a.because && <q className="hq-because">{a.because}</q>}
                    {onInspect && about[0] && (
                      <button className="hq-open" onClick={() => onInspect(about[0])}>
                        Inspect
                      </button>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        ))
      )}
    </>
  )
}

/* -------------------------------------- A8b · what executions received --- */

function ReceivedAnswer({ conversation, onOpenExecution }: HistoryAnswerProps) {
  const [who, setWho] = useState<Id | null>(null)
  const [show, setShow] = useState(40)
  const here = conversation ? ' here' : ''
  const people = useApi<Participants>('/api/participants')
  const places = useApi<ConversationsList>('/api/conversations')

  const q =
    (conversation ? '&conversation=' + encodeURIComponent(conversation) : '') +
    (who ? '&participant=' + encodeURIComponent(who) : '')
  const answer = useApi<Received>('/api/governance/questions?question=received' + q)

  const aliasOf = (id: Id | null | undefined) =>
    (id && people.data?.participants?.find((p) => p.participant === id)?.alias) || null
  const placeOf = (id: Id | null | undefined) =>
    (id && places.data?.conversations?.find((c) => c.id === id)?.name) || null

  /* Newest first, which is how somebody reads a record of what happened. The
     engine returns them oldest first. */
  const rows = useMemo(
    () => [...(answer.data?.executions ?? [])].sort((a, b) => (b.at ?? 0) - (a.at ?? 0)),
    [answer.data],
  )
  const total = answer.data?.total ?? rows.length

  return (
    <>
      <p className="hq-lede">
        What actually crossed to each execution{here}, from delivery records. Open one to
        set it beside what would compose now. A record says what crossed, never that it
        was read or followed.
      </p>

      <div className="hq-filter" role="group" aria-label="whose executions">
        <button className={'hq-chip' + (who === null ? ' on' : '')} onClick={() => setWho(null)}>
          All
        </button>
        {(people.data?.participants ?? []).map((p) => (
          <button
            key={p.participant}
            className={'hq-chip' + (who === p.participant ? ' on' : '')}
            onClick={() => setWho(p.participant)}
          >
            {p.alias}
          </button>
        ))}
      </div>

      {rows.length === 0 ? (
        <p className="hq-empty">
          No delivery record answers for this scope. An empty answer from the records.
        </p>
      ) : (
        <>
          <div className="hq-scroll">
            <table className="hq-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Participant</th>
                  <th>Runtime</th>
                  <th>Where</th>
                  <th>What crossed</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, show).map((r) => (
                  <tr key={r.execution}>
                    <td>{r.at ? when(r.at) : <span className="hq-unknown">unknown</span>}</td>
                    <td>{aliasOf(r.participant) ?? <span className="hq-unknown">unknown</span>}</td>
                    {/* The runtime is the carrier. Not an identity, not a Persona. */}
                    <td title="Runtime: the carrier. Not an identity, not a Persona.">
                      {r.runtime ?? <span className="hq-unknown">not in record</span>}
                    </td>
                    <td>{placeOf(r.conversation) ?? <span className="hq-unknown">unknown</span>}</td>
                    <td>
                      {/* THE THREE ANSWERS, NEVER MERGED. */}
                      {r.answer === 'absent' ? (
                        <span className="hq-absent-cell">no delivery record: absent</span>
                      ) : r.answer === 'empty' ? (
                        <span className="hq-empty-cell">record lists none: empty</span>
                      ) : (
                        <span>{r.sources} governed sources</span>
                      )}
                      {onOpenExecution && (
                        <button
                          className="hq-open"
                          onClick={() => onOpenExecution(r.execution)}
                        >
                          Open
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hq-foot">
            {Math.min(show, rows.length)} of {total} executions, newest first.
          </p>
          {show < rows.length && (
            <button className="hq-more" onClick={() => setShow(show + 40)}>
              Show 40 more
            </button>
          )}
          {/* WHAT THIS ANSWER DOES NOT CARRY, said rather than left as a blank
              column. Which Persona an execution was started as is a fact of
              that execution's own record, and it is read there. */}
          <p className="hq-limit">
            Which Persona each execution was started as is not in this answer. It is a fact
            of the execution&rsquo;s own record, and is read by opening one.
          </p>
        </>
      )}
    </>
  )
}

/* ------------------------------------------------------- A8c · what was used --- */

function UsedAnswer({ conversation, onInspect }: HistoryAnswerProps) {
  const here = conversation ? ' here' : ''
  const names = useNames()
  const q = conversation ? '&conversation=' + encodeURIComponent(conversation) : ''
  const answer = useApi<Used>('/api/governance/questions?question=used' + q)

  const group = (title: string, rows: UsedRow[]) => (
    <div className="hq-group">
      <h3 className="hq-group-head">{title}</h3>
      {rows.length === 0 ? (
        <p className="hq-empty">None recorded. An empty answer from the records.</p>
      ) : (
        <div className="hq-scroll">
          <table className="hq-table">
            <thead>
              <tr>
                <th>Governed material</th>
                <th>Standing now</th>
                <th>Delivery records{here}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.entry}>
                  <td>
                    {onInspect ? (
                      <button className="hq-link" onClick={() => onInspect(r.entry)}>
                        {names.name(r.entry)}
                      </button>
                    ) : (
                      names.name(r.entry)
                    )}
                  </td>
                  <td>
                    {names.standing(r.entry) ?? (
                      <span className="hq-unknown">not said</span>
                    )}
                  </td>
                  <td>{r.records}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )

  return (
    <>
      <p className="hq-lede">
        From delivery records only: what was actually selected or named for executions
        {here}. Counts are records, not scores. A record says what crossed, never that it
        was read or followed.
      </p>
      {group('Personas executions were started as', answer.data?.personas ?? [])}
      {group('Material named for executions', answer.data?.named_material ?? [])}
      {/* A RECORD THAT NAMES NO PERSONA IS COUNTED UNDER NOTHING, and is
          reported separately rather than folded into a group it does not
          belong to. */}
      {(answer.data?.records_naming_no_persona ?? 0) > 0 && (
        <p className="hq-limit">
          {answer.data?.records_naming_no_persona} delivery records name no Persona at all.
          They are counted under nothing above.
        </p>
      )}
      <p className="hq-foot">
        Executions with no delivery record are not counted, because what they received is
        absent from the record.
      </p>
    </>
  )
}

/* ------------------------------------------------------- A8d · what ended --- */

function EndedAnswer({ conversation, onInspect }: HistoryAnswerProps) {
  const names = useNames()
  const q = conversation ? '&conversation=' + encodeURIComponent(conversation) : ''
  const answer = useApi<Ended>('/api/governance/questions?question=ended' + q)
  const rows = answer.data?.ended ?? []

  return (
    <>
      <p className="hq-lede">
        Ended material{conversation ? ' that concerned this Conversation' : ''}. Nothing is
        deleted: each item stays readable, and past delivery records keep naming it.
      </p>
      {rows.length === 0 ? (
        <p className="hq-empty">Nothing has ended here. An empty answer.</p>
      ) : (
        <div className="hq-scroll">
          <table className="hq-table">
            <thead>
              <tr>
                <th>Governed material</th>
                <th>Ended</th>
                <th>Replaced by</th>
                <th>Reason given</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const at = Math.max(...r.acts.map((a) => a.at), 0)
                const reason = r.acts.map((a) => a.reason).find(Boolean) ?? null
                return (
                  <tr key={r.entry}>
                    <td>
                      {onInspect ? (
                        <button className="hq-link" onClick={() => onInspect(r.entry)}>
                          {names.name(r.entry)}
                        </button>
                      ) : (
                        names.name(r.entry)
                      )}
                      {/* REPLACED IS NOT ENDED, and the difference is said in
                          words: this one never held at all. */}
                      {r.never_held && (
                        <span className="hq-note"> replaced before establishment</span>
                      )}
                    </td>
                    <td>{at ? when(at) : <span className="hq-unknown">unknown</span>}</td>
                    <td>
                      {r.replaced_by.length === 0
                        ? '—'
                        : andList(r.replaced_by.map(names.name))}
                    </td>
                    <td>{reason ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
