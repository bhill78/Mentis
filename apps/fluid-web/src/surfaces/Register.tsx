import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ago,
  useApi,
  when,
  type AppliesRead,
  type ConditionsRead,
  type DisputeRead,
  type Id,
  type ItemHistoryRead,
  type ProposedRead,
  type SinceRead,
} from '../api'
import ActDialog, { type ActItem, type ActOutcome } from './governance/ActDialogs'
import { readProposal } from './standing'
import type { GovFilters } from '../address'
import { reachLabel, type AppliesRow } from './governance/InUseContext'
import { successorReach } from './governance/successorReach'
import { placedHere } from './governance/r2Model'
import '../register.css'

/* ------------------------------------------------------------------------ *
 * THE GOVERNED CORPUS, AS A LIST YOU CAN INTERROGATE.
 *
 * ONE REGISTER, TWO LENSES. Standing reads what the record SAYS about the
 * material — whether it stands, on whose authority, whether it is contested.
 * In use reads what the same material DOES, computed from what stands. They
 * are not two lists: they are this one list, faceted differently and given a
 * different column, which is what "one corpus at two lenses" has to mean in
 * code if it is to mean anything at all.
 *
 * AND ONE CORPUS AT TWO SCOPES. A Conversation narrows which material is in
 * scope; it does not narrow WHICH REGISTER. So the scope is a filter over the
 * same read, and changing it leaves the search, the facets and the paging
 * exactly where they were.
 *
 * IT IS A LIST AND A DOOR. Every row opens the one shared inspector; Establish,
 * Dispute and Supersede live there and in the act dialogs, never here. No
 * queue, no count tiles, no bulk establishment, no priority or confidence.
 *
 * NO KIND IS NAMED IN THIS FILE. What counts as governed is each Kind's own
 * `standing_apt`, answered by the server; the Kind facet is populated from
 * `/api/kinds`; and how something applies is read from the composer's own
 * scope vocabulary through `/api/governance/applies`.
 *
 * FOUR STANDING WORDS, EXCLUSIVE, AND A DISPUTE ON ITS OWN AXIS. Stands /
 * Proposed · reaches nobody / Ended / Replaced before establishment. A dispute
 * is a second chip that never contradicts the first, because only something
 * that stands can still stand.
 *
 * A PROPOSAL IS NOT AN OBLIGATION. Nothing in this file reads what anybody was
 * asked, so nothing in this file may say anybody owes anything.
 * ------------------------------------------------------------------------ */

/** One row of `/api/governed`, mirrored.
 *
 *  EXPORTED because the Standing lens arranges the same rows into the groups
 *  the approved surface reads down -- asked of you, stands here, proposed
 *  here -- and two renderings of one row would eventually disagree about what
 *  the record says. There is one row, arranged two ways. */
export interface Row {
  /** Intended predecessor context; never an actual placement or delivery. */
  proposed_reach?: Id[]
  entry: Id
  kind: string
  standing_apt: boolean | null
  /** null for a Kind whose standing is UNKNOWN: no standing answer is computed */
  state: 'candidate' | 'stands' | 'ended' | 'replaced' | null
  group: GroupName
  summary: string
  secondary: string
  attributed_to: Id | null
  author_alias: string | null
  at: number | null
  established_by: Id[]
  superseded_by: Id[]
  disputed_by: Id[]
  /** The objections of the challenges still open: not set aside, not withdrawn. */
  open_disputes?: Id[]
  /** `whole_brain` marks the one placement that applies in every
   *  Conversation and at Brain scope; it is never inferred from absence. */
  placed_at: { conversation: Id; name: string | null; whole_brain?: boolean }[]
  proposed_by: {
    act: Id
    actor: Id | null
    actor_alias: string | null
    conversation: Id | null
    conversation_name: string | null
    turn: Id | null
  }[]
  /** what is merely PROPOSED to replace this row, and what this row proposes
   *  to replace. NEVER `superseded_by`: nothing in here has ended anything,
   *  and a row with four proposals against it is a row that still stands.
   *  Null where the record declares no such relation. */
  proposed?: ProposedRead | null
}

type GroupName = 'proposed' | 'recorded' | 'standing' | 'history' | 'unknown'

interface Governed {
  error?: string
  groups: Record<GroupName, Row[]>
  totals: Record<GroupName, number>
  omitted: Record<GroupName, number>
  matched: number
  walked: number
  kinds: {
    listed: string[]
    standing_not_meaningful: string[]
    standing_apt_unknown: { kind: string; entries: number }[]
  }
  why_not: string | null
  not_an_ask?: string
}

interface KindDef {
  kind: string
  standing_apt: boolean | null
}

/* ---------------------------------------------------------------- standing --- */

/** THE FOUR EXCLUSIVE WORDS. `null` is a Kind that never declared whether
 *  standing is meaningful for its entries, which is UNKNOWN and is not one of
 *  the four — it gets its own word and is never folded into them. */
const STATE_SAID: Record<NonNullable<Row['state']>, string> = {
  stands: 'Stands',
  candidate: 'Proposed · reaches nobody',
  ended: 'Ended',
  replaced: 'Replaced before establishment',
}

/** The dispute chip, on its own axis. Dispute and standing are separate
 *  dimensions: only something that stands can "still stand", and a disputed
 *  proposal is still only proposed. Neither sentence contradicts the other. */
function disputeChip(r: Row): string | null {
  if (r.disputed_by.length === 0) return null
  if (r.state === 'stands') return 'Disputed · still stands'
  if (r.state === 'candidate') return 'Disputed · still only proposed'
  /* Disputed, and neither standing nor proposed any more. The dispute is a
     fact about the record and is not dropped because the item moved on. */
  return 'Disputed'
}

/** ON WHOSE AUTHORITY. Written and established are two acts and the record
 *  keeps them apart, so this says which of them happened rather than merging
 *  them into "by @X".
 *
 *  WHO ESTABLISHED IT IS ONE READ AWAY AND IS NOT GUESSED HERE. This read
 *  carries the establishing LINKS but not their actors, and filling the name
 *  in from the author would be exactly the merge this distinction exists to
 *  prevent. The inspector asks `/api/governance/history`, which carries it. */
function authority(r: Row): string {
  const by = r.author_alias ? '@' + r.author_alias.replace(/^@/, '') : null
  if (r.established_by.length === 0)
    return by ? `Not established · written by ${by}` : 'Not established'
  return by ? `Established · written by ${by}` : 'Established'
}

/* ------------------------------------------------------ why it is in scope --- */

/** WHY THIS IS IN SCOPE HERE, in one phrase.
 *
 *  Placement is a recorded link. Being selected as a Persona and being named
 *  for an execution are DELIVERY facts and come from delivery records only, so
 *  where no record names it the phrase says so rather than "0 times" — a zero
 *  would claim the looking had been done. */
function whyShort(
  r: Row,
  scope: Id | null,
  conditions: ConditionsRead | null,
  applies: AppliesRow | undefined,
): string {
  const here = scope ? r.placed_at.filter((p) => placedHere(p, scope)) : r.placed_at
  const by = r.author_alias ? ' by @' + r.author_alias.replace(/^@/, '') : ''
  const at = r.at ? ' · ' + ago(r.at) : ''
  if (here.some((p) => p.whole_brain)) {
    const local = here.filter((p) => !p.whole_brain).length
    return `Placed on the Whole Brain${local ? (scope ? ' and in this Conversation' : ` and in ${local} Conversation${local === 1 ? '' : 's'}`) : ''}${at}${by}`
  }
  if (here.length === 1) return `Placed in ${scope ? 'this Conversation' : (here[0].name ?? here[0].conversation)}${at}${by}`
  if (here.length > 1) return `Placed in ${here.length} Conversations${at}${by}`
  const c = conditions?.rows.find((x) => x.entry === r.entry)
  if (c && !c.uncounted) {
    if (c.selected_as_persona_in > 0)
      return `Selected as the Persona in ${c.selected_as_persona_in} delivery ${
        c.selected_as_persona_in === 1 ? 'record' : 'records'
      }`
    if (c.named_in > 0)
      return `Named for ${c.executions} of ${conditions?.executions_with_records} executions that have a record`
  }
  const asked = r.proposed_by.find((p) => !scope || p.conversation === scope)
  if (asked)
    return `Proposed ${scope ? 'here' : 'in ' + (asked.conversation_name ?? 'a Conversation')}${
      asked.actor_alias ? ' by @' + asked.actor_alias.replace(/^@/, '') : ''
    }`
  if (c?.uncounted && applies?.applies === 'when_named')
    return 'Nothing places it; no delivery record names it either'
  /* NO PATH IS AN ANSWER. Nothing places it, nothing selected it, nothing
     named it — said out loud rather than left as an empty cell. */
  return 'no path here'
}

/* ------------------------------------------------------------ the one row --- */

/** THE COLUMN HEADINGS, WHEREVER THE ROWS ARE.
 *
 *  They live with the rows rather than with the full Register, because a
 *  `reg-row` is five columns of unlabelled values anywhere it is rendered and
 *  the Standing lens renders its own bare `<ul className="reg-list">` lists
 *  for "Stands here", "Proposed here" and the Brain-scope group. Those had no
 *  heads at all: five columns, no names. The headings ARE the row's grid, so
 *  they are told which of the two it is -- one template for both put "Why it
 *  is here" over the wrong column in the In use lens.
 *
 *  `aria-hidden`, because a screen reader gets the row's own words and this
 *  is a visual alignment device, not a table. */
export function RegisterHeads({ lens }: { lens: 'standing' | 'use' }) {
  return (
    <li className="reg-heads" data-lens={lens} aria-hidden="true">
      <span>Governed material</span>
      <span>Kind</span>
      <span>{lens === 'standing' ? 'Standing' : 'How it applies'}</span>
      {lens === 'standing' && <span>Authority</span>}
      <span>Why it is here</span>
    </li>
  )
}

export function RegisterRow({
  r,
  lens,
  scope,
  isNew,
  conditions,
  applies,
  appliesRead,
  names,
  onOpen,
  onCompare,
  me,
  onChanged,
  inspected = false,
}: {
  r: Row
  lens: 'standing' | 'use'
  scope: Id | null
  isNew: boolean
  conditions: ConditionsRead | null
  applies: AppliesRow | undefined
  /** WHERE THE SEPARATE `applies` READ IS. `applies` being undefined is three
   *  different facts and they were collapsed into one verdict: the read has
   *  not come back, the read failed, or it came back and says nothing about
   *  this row. Only the last of those is a fact about the row. */
  appliesRead: 'pending' | 'failed' | 'answered'
  names: Record<string, string>
  onOpen: (id: Id) => void
  onCompare?: (left: Id, right: Id) => void
  /** who an act from a condition card would be attributed to. Absent, the
   *  card still states what the record says and offers no act — an act with
   *  nobody to attribute it to is not offered. */
  me?: Id | null
  /** the record moved because of an act taken here. */
  onChanged?: () => void
  /** this row is the item the inspector holds (I-138) */
  inspected?: boolean
}) {
  const dis = disputeChip(r)
  /* THE ITEM YOU LANDED ON IS THE ROW YOU CAN SEE. "Inspect in Governance"
     opens the inspector on it; the row it is read beside is marked and
     brought into view, so the register does not look like it is about
     something else. Nearest, so a row already on screen does not jump. NOT
     where the inspector is stacked under the register (a narrow workspace):
     there the inspector is what is brought into view, and the row is marked
     for when the reader scrolls back up to it. */
  const at = useRef<HTMLLIElement | null>(null)
  useEffect(() => {
    const el = at.current
    if (!inspected || !el) return
    const body = el.closest('.ws-gov-body')
    if (body && getComputedStyle(body).flexDirection === 'column') return
    el.scrollIntoView({ block: 'nearest' })
  }, [inspected])
  return (
    <li ref={at} className={'reg-item' + (inspected ? ' reg-inspected' : '')}>
      <button
        className="reg-row"
        aria-current={inspected ? 'true' : undefined}
        data-state={r.state ?? 'unknown'}
        data-lens={lens}
        onClick={() => onOpen(r.entry)}
      >
        <span className="reg-said">
          {r.summary || <span className="reg-faint">nothing written in its fields</span>}
          {r.secondary && <span className="reg-second"> — {r.secondary}</span>}
          {/* ACTED ON SINCE THIS PERSON'S LAST ARRIVAL. Not "unread": nothing
              anywhere records that anybody read anything. */}
          {isNew && (
            <span
              className="reg-new"
              title="acted on since your last arrival here. Nothing records that anybody read it."
            >
              new
            </span>
          )}
        </span>
        <span className="reg-kind">{r.kind}</span>
        {lens === 'standing' ? (
          <>
            <span className="reg-standing">
              {r.state ? (
                <span className="reg-state">{STATE_SAID[r.state]}</span>
              ) : (
                <span
                  className="reg-unknown"
                  title="its Kind's definition does not say whether standing applies to its entries"
                >
                  standing: UNKNOWN
                </span>
              )}
              {dis && (
                <span className="reg-disputed" title="a dispute revokes nothing until you act on it">
                  {dis}
                </span>
              )}
            </span>
            <span className="reg-authority">{authority(r)}</span>
          </>
        ) : (
          <span className="reg-applies">
            {/* THREE ANSWERS, KEPT APART. This lens asks the register for
                `state=standing` only, so every row on it stands by
                construction — "not standing" was false for every row it was
                ever shown beside, and on a failed read it was permanent. */}
            {applies ? (
              reachLabel(applies, names)
            ) : appliesRead === 'pending' ? (
              <span className="reg-faint">reading how it applies…</span>
            ) : appliesRead === 'failed' ? (
              <span className="reg-faint">how it applies could not be read</span>
            ) : (
              <span className="reg-faint">the read does not say how this one applies</span>
            )}
          </span>
        )}
        <span className="reg-why">{whyShort(r, scope, conditions, applies)}</span>
      </button>
      {/* CONDITIONS SIT UNDER THE ITEM THEY CONCERN, because that is what they
          are about. None of them is owed, and each says so in its own words. */}
      {r.disputed_by.length > 0 && <DisputeCondition r={r} onOpen={onOpen} />}
      {/* PROPOSED IS NOT REPLACED, AND THE TWO CARDS SAY DIFFERENT THINGS.
          This one fires while the row STILL STANDS and nothing has ended;
          the one below fires once something has. They are never both the
          same fact told twice. */}
      {(r.proposed?.successors.items.length ?? 0) > 0 &&
        r.superseded_by.length === 0 && (
          <ProposedReplacementCondition
            r={r}
            onOpen={onOpen}
            onCompare={onCompare}
            me={me}
            onChanged={onChanged}
          />
        )}
      {r.superseded_by.length > 0 && (
        <ReplacementCondition r={r} onOpen={onOpen} onCompare={onCompare} />
      )}
    </li>
  )
}

/* ---------------------------------------------------- condition: dispute --- */

/** A dispute, inline on the row it is about (I-29).
 *
 *  IT REVOKES NOTHING. The disputer, the date and the challenge in their own
 *  words, then the standing, unchanged, and the plain statement that nobody
 *  asked for anything. Read per row and only for rows the register already
 *  knows are disputed, so an undisputed corpus costs nothing. */
function DisputeCondition({ r, onOpen }: { r: Row; onOpen: (id: Id) => void }) {
  const got = useApi<{ disputes: DisputeRead[]; error?: string }>(
    '/api/governance/disputes?entry=' + encodeURIComponent(r.entry),
  )
  if (got.error)
    return <p className="reg-cond reg-cond-err">the challenges could not be read: {got.error}</p>
  if (!got.data) return null
  const all = got.data.disputes ?? []
  const open = all.filter((x) => x.open)
  if (open.length === 0) {
    if (all.length === 0) return null
    /* SET ASIDE IS NOT DELETED. The challenge was made, it was answered, and
       both facts stay in the record. */
    return (
      <div className="reg-cond">
        <p className="reg-cond-head">
          {all.length === 1 ? 'A challenge was' : `${all.length} challenges were`} set aside · the
          challenge and its text stay in the record, and standing did not change
        </p>
      </div>
    )
  }
  return (
    <>
      {open.map((x) => (
        <div className="reg-cond" key={x.link}>
          <p className="reg-cond-head">
            @{(x.by_alias ?? x.by ?? 'somebody').replace(/^@/, '')} disputes this ·{' '}
            <span title={when(x.at)}>{ago(x.at)}</span>
          </p>
          {x.reason && <blockquote className="reg-cond-said">{x.reason}</blockquote>}
          <p className="reg-cond-why">
            {r.state === 'stands'
              ? 'It still stands: a dispute revokes nothing until you act, and nobody has asked you to.'
              : 'A dispute revokes nothing. Nobody has asked you to act on it.'}
          </p>
          <p className="reg-cond-acts">
            <button className="reg-link" onClick={() => onOpen(x.disputed_by)}>
              Inspect challenge
            </button>
            {' · '}
            <button className="reg-link" onClick={() => onOpen(r.entry)}>
              Open the item to set it aside or supersede it
            </button>
          </p>
        </div>
      ))}
    </>
  )
}

/* -------------------------------------- condition: a PROPOSED replacement --- */

/** A proposed replacement, inline on the row it is about (I-30).
 *
 *  IT HAS REPLACED NOTHING AND IT REACHES NOBODY. The row still stands, its
 *  standing word is untouched, and this card is beside that word rather than
 *  over it — a proposal is not a lesser kind of supersession, it is a
 *  different fact on a different relation. SEVERAL MAY BE PROPOSED AT ONCE
 *  and each one gets its own card, because four candidates for one post are
 *  four candidates and not a queue.
 *
 *  NOBODY IS OWED ANYTHING BY IT, and that is said. The acts are offered
 *  because the owner is here, not because anything is being asked. */
function ProposedReplacementCondition({
  r,
  onOpen,
  onCompare,
  me,
  onChanged,
}: {
  r: Row
  onOpen: (id: Id) => void
  onCompare?: (left: Id, right: Id) => void
  me?: Id | null
  onChanged?: () => void
}) {
  const [acting, setActing] = useState<
    { act: 'establish' | 'dispute'; on: ActItem; ends: ActItem[] } | null
  >(null)
  const [landed, setLanded] = useState<string | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  /* WHAT APPROVING IT WOULD END, ASKED OF THE RECORD BEFORE THE DIALOG OPENS.
     This row is only one of the predecessors a proposal may name, and a dialog
     that said otherwise would be describing the act falsely. */
  const approve = async (successor: Id) => {
    setFailed(null)
    try {
      const got = await readProposal(successor)
      setActing({ act: 'establish', on: got.successor, ends: got.ends })
    } catch (e) {
      setFailed((e as Error).message)
    }
  }
  const said = r.summary
    ? `“${r.summary.length > 60 ? r.summary.slice(0, 59) + '…' : r.summary}”`
    : 'this'
  return (
    <>
      {(r.proposed?.successors.items ?? []).map((x) => {
        const theirs: ActItem = {
          entry: x.entry,
          kind: x.kind,
          text: x.summary ?? 'nothing written in its fields',
          stands: x.stands,
          standing: x.state,
        }
        return (
          <div className="reg-cond" key={x.link}>
            <p className="reg-cond-head">
              @{(x.by_alias ?? x.attributed_to ?? 'somebody').replace(/^@/, '')} proposed a
              replacement for {said} · <span title={when(x.at)}>{ago(x.at)}</span>
            </p>
            {x.reason && <blockquote className="reg-cond-said">{x.reason}</blockquote>}
            {/* WHAT THIS CANDIDATE REACHES, ASKED OF THE SAME FIELD THE
                ACTS BELOW ARE OFFERED FROM. The sentence used to be a
                constant while the buttons under it branched on `x.state`:
                after approval the card went on saying the successor that had
                just ended this row reached nobody, and a candidate
                established on its own — with the predecessor still standing —
                was described as reaching nobody while the read said it
                stands. One fact, one answer, wherever it is said. */}
            <p className="reg-cond-why">
              {successorReach(x.state, said, r.state === null ? null : r.state === 'stands')} Nobody
              asked you.
            </p>
            <p className="reg-cond-acts">
              {onCompare && (
                <>
                  <button className="reg-link" onClick={() => onCompare(r.entry, x.entry)}>
                    Compare
                  </button>
                  {' · '}
                </>
              )}
              {me && x.state === 'candidate' && (
                <>
                  <button className="reg-link" onClick={() => void approve(x.entry)}>
                    Establish replacement…
                  </button>
                  {' · '}
                  <button
                    className="reg-link"
                    onClick={() => setActing({ act: 'dispute', on: theirs, ends: [] })}
                  >
                    Dispute…
                  </button>
                  {' · '}
                </>
              )}
              <button className="reg-link" onClick={() => onOpen(x.entry)}>
                Open the proposal
              </button>
            </p>
          </div>
        )
      })}
      {/* THE READ IS BOUNDED AND SAYS SO. `omitted` is how many further
          proposals name this item that the read did not carry; a row with six
          competing candidates showed five and read as a row with five. A
          number nobody is told about is a number that silently disagrees with
          the record. */}
      {(r.proposed?.successors.omitted ?? 0) > 0 && (
        <p className="reg-cond-why">
          and {r.proposed!.successors.omitted} more proposed to replace {said}, not listed here —{' '}
          {r.proposed!.successors.total} in all.{' '}
          <button className="reg-link" onClick={() => onOpen(r.entry)}>
            Open the item to read them
          </button>
        </p>
      )}
      {failed && (
        <p className="reg-cond-landed" role="alert">
          the proposal could not be read: {failed}
        </p>
      )}
      {landed && (
        <p className="reg-cond-landed" role="status">
          {landed}
        </p>
      )}
      {acting && (
        <ActDialog
          act={acting.act}
          item={acting.on}
          /* ONE ACT, STATED BEFORE THE CLICK. `ends` is what makes the
             establish dialog say it ends this item and perform both together;
             the dispute path is given none, because disputing ends nothing. */
          ends={acting.act === 'establish' ? acting.ends : undefined}
          me={me ?? null}
          onCancel={() => setActing(null)}
          onDone={(outcome: ActOutcome) => {
            setActing(null)
            setLanded(outcome.said)
            onChanged?.()
          }}
        />
      )}
    </>
  )
}

/* ------------------------------------------ condition: replacement/ending --- */

/** What replaced it, or was proposed to (I-30).
 *
 *  MARK IV RECORDS SUPERSESSION AS ONE ACT: a `supersedes` link ends its
 *  target the moment it exists, whether or not the successor was ever
 *  established. So the state the approved artifact describes — a replacement
 *  that reaches nobody while the old one keeps standing — is read here from
 *  what the record actually holds, and the successor's OWN standing is stated
 *  rather than assumed. "Replaced by something that reaches nobody" is a
 *  different fact from "replaced", and both are producible. */
function ReplacementCondition({
  r,
  onOpen,
  onCompare,
}: {
  r: Row
  onOpen: (id: Id) => void
  onCompare?: (left: Id, right: Id) => void
}) {
  const got = useApi<ItemHistoryRead>(
    '/api/governance/history?entry=' + encodeURIComponent(r.entry),
  )
  const step = got.data?.timeline?.find((t) => t.entry === r.entry)
  const link = step?.superseded_by?.[0]
  if (!link) return null
  const successor = link.from
  const theirs = got.data?.timeline?.find((t) => t.entry === successor)
  const stood = theirs?.state === 'stands'
  return (
    <div className="reg-cond">
      <p className="reg-cond-head">
        @{(link.by_alias ?? link.by ?? 'somebody').replace(/^@/, '')} replaced this ·{' '}
        <span title={when(link.at)}>{ago(link.at)}</span>
      </p>
      {link.reason && <blockquote className="reg-cond-said">{link.reason}</blockquote>}
      <p className="reg-cond-why">
        {stood
          ? 'The replacement stands. Past delivery records that name this one stay exactly as they are.'
          : 'The replacement does not stand, so it reaches nobody. Nobody asked you.'}
      </p>
      <p className="reg-cond-acts">
        {onCompare && (
          <>
            <button className="reg-link" onClick={() => onCompare(r.entry, successor)}>
              Compare
            </button>
            {' · '}
          </>
        )}
        <button className="reg-link" onClick={() => onOpen(successor)}>
          Open the replacement
        </button>
      </p>
    </div>
  )
}

/* ------------------------------------------------------------ the facets --- */

const STANDING_FACET: { value: string; label: string; title: string }[] = [
  { value: '', label: 'All', title: 'every answer about standing' },
  { value: 'standing', label: 'Stands', title: 'established, and nothing has superseded it' },
  { value: 'proposed', label: 'Proposed', title: 'written, and reaching nobody' },
  {
    value: 'disputed',
    label: 'Disputed',
    title: 'an open challenge AND it still stands. A disputed proposal is under Proposed.',
  },
]

const APPLIES_FACET: { value: string; label: string; title: string }[] = [
  {
    value: '',
    label: 'Any way',
    title: 'every standing item, however it could reach an execution',
  },
  {
    value: 'placed',
    label: 'Placed',
    title: 'placed at a Conversation, so it reaches everybody acting there',
  },
  {
    value: 'by_persona',
    label: 'By Persona',
    title: 'reaches an execution that was started as it, and no other',
  },
  {
    value: 'when_named',
    label: 'When named',
    title: 'nothing carries it; it reaches an execution only when named for that invocation',
  },
  {
    value: 'truth_apt',
    label: 'Truth-apt, when named',
    title: 'its Kind says it can be right or wrong, and it reaches work only if named',
  },
]

function Facet({
  label,
  options,
  value,
  onChoose,
}: {
  label: string
  options: { value: string; label: string; title: string }[]
  value: string
  onChoose: (v: string) => void
}) {
  return (
    <div className="reg-facet" role="group" aria-label={label}>
      <span className="reg-facet-label">{label}</span>
      {options.map((o) => (
        <button
          key={o.value}
          className={'reg-facet-btn' + (value === o.value ? ' on' : '')}
          aria-pressed={value === o.value}
          title={o.title}
          onClick={() => onChoose(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ props --- */

const PAGE = 40

export interface RegisterProps {
  /** which question is being asked of the same corpus */
  lens: 'standing' | 'use'
  /** the Conversation this register is read through, or null for the Brain */
  conversation: Id | null
  /** the facets, held by whoever owns the address so a link can carry them */
  filters: GovFilters
  onFilters: (next: GovFilters) => void
  onOpenEntry: (id: Id) => void
  onCompare?: (left: Id, right: Id) => void
  /** who is looking, for the `new` marker. Without one there is no last look
   *  and so no marker, which is absent and not "nothing is new". */
  me?: Id | null
  /** names for Conversations, so a placement can be said and not idented */
  names?: Record<string, string>
  /** the item the inspector holds, marked where its row is shown */
  inspected?: Id | null
}

export default function Register({
  lens,
  conversation,
  filters,
  onFilters,
  onOpenEntry,
  onCompare,
  me,
  names = {},
  inspected = null,
}: RegisterProps) {
  const [typed, setTyped] = useState(filters.q)
  const [limit, setLimit] = useState(PAGE)
  /* THE ADDRESS IS THE SOURCE OF TRUTH FOR THE QUERY, so a link that carries a
     search puts it in the box. Typing goes the other way, debounced. */
  useEffect(() => setTyped(filters.q), [filters.q])
  const onF = onFilters
  const current = filters
  useEffect(() => {
    const t = setTimeout(() => {
      if (typed.trim() !== current.q) onF({ ...current, q: typed.trim() })
    }, 250)
    return () => clearTimeout(t)
  }, [typed, current, onF])
  // A new question starts from the first page again.
  useEffect(() => setLimit(PAGE), [filters.q, filters.kind, filters.state, filters.applies, lens])

  const kinds = useApi<{ kinds: KindDef[] }>('/api/kinds')

  /* THE `Disputed` FACET IS NOT A GROUP THE SERVER KEEPS. It means an open
     dispute AND it still stands, so the read asks for what stands and the
     second half is applied here — which is also why it cannot be sent as a
     `state` the route would rightly refuse.

     AND IN USE ONLY READS WHAT STANDS, because only standing material acts on
     work. Said in the footer rather than left for anybody to infer. */
  const wanted =
    lens === 'use' ? 'standing' : filters.state === 'disputed' ? 'standing' : filters.state
  const params = new URLSearchParams()
  if (filters.q) params.set('q', filters.q)
  if (filters.kind) params.set('kind', filters.kind)
  if (wanted) params.set('state', wanted)
  params.set('limit', String(Math.max(PAGE, limit) + PAGE))
  const got = useApi<Governed>('/api/governed?' + params)
  const d = got.data

  const applies = useApi<AppliesRead>(lens === 'use' ? '/api/governance/applies' : null)
  const appliesBy = useMemo(() => {
    const out: Record<string, AppliesRow> = {}
    for (const row of applies.data?.rows ?? []) out[row.entry] = row as AppliesRow
    return out
  }, [applies.data])
  /* AND WHETHER THAT READ HAS ANSWERED AT ALL. It is a second request beside
     the register's own, so a missing row means one of three things and the
     row must not report the third when it is the first or second. */
  const appliesRead: 'pending' | 'failed' | 'answered' =
    applies.error ? 'failed' : applies.data ? 'answered' : 'pending'

  /* WHAT CHANGED SINCE THIS PERSON'S LAST ARRIVAL. A catch-up is a PAIR of
     arrivals: never having arrived is absent, one arrival bounds nothing, and
     both of those mean there is no marker rather than that nothing is new. */
  const since = useApi<SinceRead>(
    me
      ? '/api/governance/since?participant=' +
        encodeURIComponent(me) +
        (conversation ? '&conversation=' + encodeURIComponent(conversation) : '')
      : null,
  )
  const fresh = useMemo(() => {
    const acts = since.data?.bounded ? (since.data.changed?.acts ?? []) : []
    const out = new Set<string>()
    for (const a of acts) for (const e of a.about ?? []) out.add(e)
    return out
  }, [since.data])

  const rows = useMemo<Row[]>(() => {
    if (!d || d.error) return []
    let out = [
      ...(d.groups.standing ?? []),
      ...(d.groups.proposed ?? []),
      ...(d.groups.history ?? []),
      ...(d.groups.unknown ?? []),
    ]
    /* A CONVERSATION IS A LENS, so this narrows what is in scope rather than
       asking a different question: material placed here, or proposed here. */
    if (conversation)
      out = out.filter(
        (r) =>
          r.placed_at.some((p) => placedHere(p, conversation)) ||
          r.proposed_by.some((p) => p.conversation === conversation),
      )
    if (lens === 'standing' && filters.state === 'disputed')
      out = out.filter((r) => r.disputed_by.length > 0 && r.state === 'stands')
    if (lens === 'use' && filters.applies)
      out = out.filter((r) => {
        const a = appliesBy[r.entry]
        if (!a) return false
        if (filters.applies === 'truth_apt') return a.truth_apt === true
        return a.applies === filters.applies
      })
    /* ALPHABETICAL, as the approved register is: somebody looking for material
       they can half-remember the words of is not helped by recency. */
    return [...out].sort((a, b) =>
      (a.summary || a.entry).localeCompare(b.summary || b.entry, undefined, {
        sensitivity: 'base',
      }),
    )
  }, [d, conversation, filters.state, filters.applies, lens, appliesBy])

  /* PER-ROW DELIVERY CONDITIONS, for the rows actually on screen. Counted from
     delivery records and nothing else, so a row nothing names is UNCOUNTED and
     never a zero. */
  const shown = rows.slice(0, limit)
  const askFor = shown.map((r) => r.entry)
  const conditions = useApi<ConditionsRead>(
    askFor.length
      ? '/api/governance/conditions?' +
        askFor.map((e) => 'entry=' + encodeURIComponent(e)).join('&')
      : null,
  )

  const taking = (kinds.data?.kinds ?? []).filter((k) => k.standing_apt === true)
  const unsaid = (kinds.data?.kinds ?? []).filter((k) => k.standing_apt == null)
  const kindOptions = [
    { value: '', label: 'Any', title: 'every Kind this record declares governed' },
    ...taking.map((k) => ({ value: k.kind, label: k.kind, title: `only ${k.kind}` })),
    ...unsaid.map((k) => ({
      value: k.kind,
      label: k.kind,
      title: `${k.kind} — its definition does not say whether standing applies (UNKNOWN)`,
    })),
  ]
  const narrowed = Boolean(filters.q || filters.kind || filters.state || filters.applies)

  return (
    <section className="register" aria-label={`governed material · ${lens}`}>
      <div className="reg-controls">
        <label className="reg-search">
          <span className="reg-sr">find governed material</span>
          <input
            type="search"
            placeholder="Find governed material…"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
          />
        </label>
        {/* THE FACET THAT BELONGS TO THIS LENS, and only that one. Standing
            asks what the record says; In use asks how it reaches work. Asking
            one of them the other's question would be a category error wearing
            a filter's clothes. */}
        {lens === 'standing' ? (
          <Facet
            label="Standing"
            options={STANDING_FACET}
            value={filters.state}
            onChoose={(state) => onFilters({ ...filters, state })}
          />
        ) : (
          <Facet
            label="Applies"
            options={APPLIES_FACET}
            value={filters.applies}
            onChoose={(a) => onFilters({ ...filters, applies: a })}
          />
        )}
        <Facet
          label="Kind"
          options={kindOptions}
          value={filters.kind}
          onChoose={(kind) => onFilters({ ...filters, kind })}
        />
      </div>

      {/* COULD NOT READ IS NOT EMPTY. */}
      {got.error && (
        <p className="reg-error" role="alert">
          could not read governed material: {got.error}
        </p>
      )}
      {!d && !got.error && <p className="reg-empty">reading the record…</p>}
      {d?.error && <p className="reg-error">{d.error}</p>}
      {d?.why_not && <p className="reg-note">{d.why_not}</p>}

      {d && !d.error && (
        <>
          {rows.length === 0 ? (
            <p className="reg-empty">
              {narrowed
                ? 'Nothing matches that. An empty answer, not an empty record.'
                : conversation
                  ? 'Nothing that concerns this Conversation is here. An empty answer.'
                  : 'The record holds no governed material. An empty answer.'}
            </p>
          ) : (
            /* THE LIST OWNS THE COLUMNS, so the lens is told to the list:
               In use has four and Standing five, and every row and the
               headings take whichever it is through `subgrid`. */
            <ul className="reg-list" data-lens={lens}>
              <RegisterHeads lens={lens} />
              {shown.map((r) => (
                <RegisterRow
                  key={r.entry}
                  r={r}
                  lens={lens}
                  scope={conversation}
                  isNew={fresh.has(r.entry)}
                  conditions={conditions.data ?? null}
                  applies={appliesBy[r.entry]}
                  appliesRead={appliesRead}
                  names={names}
                  onOpen={onOpenEntry}
                  onCompare={onCompare}
                  me={me}
                  onChanged={() => got.reload()}
                  inspected={r.entry === inspected}
                />
              ))}
            </ul>
          )}

          <p className="reg-foot">
            {shown.length} of {rows.length} · alphabetical.{' '}
            {lens === 'standing'
              ? 'Ended material is history.'
              : 'Only standing material acts on work.'}
            {rows.length > shown.length && (
              <>
                {' '}
                <button className="reg-more" onClick={() => setLimit((n) => n + PAGE)}>
                  Show {PAGE} more
                </button>
              </>
            )}
          </p>

          {/* NOT WALKED IS NOT FORGOTTEN. */}
          {!filters.kind && (d.kinds.standing_apt_unknown ?? []).some((k) => k.entries > 0) && (
            <p className="reg-note reg-unlisted">
              Not listed: entries of Kinds whose definition doesn't say whether standing applies —{' '}
              {d.kinds.standing_apt_unknown
                .filter((k) => k.entries > 0)
                .map((k, i) => (
                  <span key={k.kind}>
                    {i > 0 && ', '}
                    <button
                      className="reg-link"
                      onClick={() => onFilters({ ...filters, kind: k.kind })}
                    >
                      {k.kind}
                    </button>{' '}
                    ({k.entries})
                  </span>
                ))}
              .
            </p>
          )}
        </>
      )}
    </section>
  )
}
