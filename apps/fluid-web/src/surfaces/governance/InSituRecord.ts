import { useEffect, useRef, useState } from 'react'
import { useApi, type ApiState, type Id, type ProposedRead } from '../../api'

/* ------------------------------------------------------------------------ *
 * WHAT A TURN REFERS TO, READ ONCE FOR THE WHOLE CONVERSATION.
 *
 * A TURN CARRIES A REFERENCE AND NOTHING ELSE. There is no Conversation-local
 * copy of governance state anywhere in here: a Turn knows only WHICH item the
 * work made, and every word drawn about that item is read from the item's own
 * current state. Two Turns that name the same item show the same thing,
 * because they are reading the same row.
 *
 * AND THE REFERENCE IS NOT A NEW FACT EITHER. `proposed_by[].turn` on the
 * register row is the `produced` Relation walked back to the act that made
 * the material, and that act already carries the Turn and the Conversation.
 * Nothing here writes a link, and nothing here is stored.
 *
 * WHY ONE READ AND NOT ONE PER TURN. Eleven Turns asking the register eleven
 * times is eleven identical answers, and the same again on every advance. So
 * the read is shared: the first Turn to want it does it, and the rest read
 * what it got. The share is a cache of a READ, never of a decision — when the
 * record advances, the reader rereads and everybody sees the new answer.
 * ------------------------------------------------------------------------ */

/** One row of the Brain-wide register, as `/api/governed` returns it. */
export interface RegisterRow {
  entry: Id
  kind: string
  /** the CURRENT Kind definition's answer, where it has one. null is UNKNOWN. */
  standing_apt: boolean | null
  summary: string
  secondary: string
  attributed_to: Id | null
  author_alias: string | null
  at: number | null
  placed_at: { conversation: Id; name: string | null; whole_brain?: boolean }[]
  /** the acts that produced it, each naming the Turn and Conversation it
   *  happened in. Empty for material that predates the provenance link. */
  proposed_by: {
    act: Id
    act_type: string
    actor: Id
    actor_alias: string | null
    conversation: Id | null
    conversation_name: string | null
    turn: Id | null
  }[]
  established_by: Id[]
  superseded_by: Id[]
  disputed_by: Id[]
  /** the four exclusive words, or null where standing does not apply */
  state: 'stands' | 'ended' | 'replaced' | 'candidate' | null
  group: 'proposed' | 'standing' | 'history' | 'unknown'
  /** what this row is merely PROPOSED to replace, and what is proposed to
   *  replace it. It has ended nothing either way: a row with a proposal
   *  against it keeps exactly the `state` above. */
  proposed?: ProposedRead | null
}

interface Register {
  groups: Record<string, RegisterRow[]>
  totals: Record<string, number>
  omitted: Record<string, number>
}

/** One operational act, as `/api/operational` returns it. Only the fields a
 *  Turn's execution footer needs are named; the rest ride along unread. */
export interface Act {
  id: Id
  at: number
  actor: Id
  act: string
  conversation: Id | null
  turn: Id | null
  /** the execution this act was recorded under, or null because none was */
  execution: string | null
  runtime: string | null
}

/** What ONE execution received, as `/api/governance/execution` returns it.
 *
 *  `record` IS THE ANSWER, and it is one of three. `absent`: no delivery
 *  record names this execution, so nothing is held and nothing may be
 *  concluded. `empty`: a record exists and lists no behavioural material,
 *  which is a real answer read from the record. `present`: it lists some. */
export interface ExecutionSheet {
  execution: string
  record: 'absent' | 'empty' | 'present'
  participant?: Id | null
  runtime?: string | null
  conversation?: Id | null
  at?: number | null
  sources: number
  why: string | null
  /** THREE ANSWERS ABOUT THE PERSONA, never collapsed into "none". */
  persona:
    | { answer: 'from_the_record'; persona: Id | null }
    | { answer: 'lists_none'; why: string }
    | { answer: 'no_record'; why: string }
}

/** The supersession chain through one item, as `/api/governance/history`
 *  returns it — the item's own current state, and what happened to it. */
export interface ItemTimeline {
  entry: Id
  kind: string | null
  body: Record<string, unknown>
  at: number | null
  attributed_to: Id | null
  written_by: string | null
  state: 'stands' | 'ended' | 'replaced' | 'candidate'
  established: { link: Id; by: Id | null; reason: string | null; at: number }[]
  placed_at: { link: Id; to: Id; name?: string | null; reason: string | null }[]
  superseded_by: { link: Id; from: Id; by: Id | null; reason: string | null; at: number }[]
  supersedes: { link: Id; to: Id; by: Id | null; reason: string | null; at: number }[]
  disputes: {
    link: Id
    objection: Id
    by: Id | null
    by_alias?: string | null
    reason: string | null
    at: number
    /** the `supports` link that answered it, or null while it is open */
    set_aside: Id | null
  }[]
  /** proposed, which is not done. Never `superseded_by`. */
  proposed?: ProposedRead | null
  missing?: boolean
}

export interface ItemHistory {
  entry: Id
  chain: Id[]
  timeline: ItemTimeline[]
}

/* ---------------------------- the shared read ----------------------------- *
 *
 * ONE READER PER PATH, ELECTED, NOT CONFIGURED. Every Turn asks for the same
 * path; the first one to ask claims it and is the one that actually reads,
 * through the ordinary `useApi` so that it rereads on an advance exactly like
 * every other reader in this interface. The others subscribe and are told.
 *
 * WHY NOT A PROVIDER. A Provider would have to be mounted above the Turns, in
 * a surface this package does not own. Claiming is local, needs nobody to
 * wire it, and behaves identically whether one Turn is on screen or fifty.
 */

const IDLE: ApiState<never> = { data: null, error: null, loading: false, reload: () => {} }
const WAITING: ApiState<never> = { data: null, error: null, loading: true, reload: () => {} }

interface Share<T> {
  /** whoever is currently doing the reading, or nobody yet */
  owner: object | null
  state: ApiState<T>
  listeners: Set<() => void>
}

const shares = new Map<string, Share<unknown>>()

function shareOf<T>(path: string): Share<T> {
  let s = shares.get(path)
  if (!s) {
    s = { owner: null, state: WAITING, listeners: new Set() }
    shares.set(path, s)
  }
  return s as Share<T>
}

/** One read of `path`, however many callers want it.
 *
 *  THE READER IS ELECTED IN AN EFFECT, not during render, because a render may
 *  happen twice and be thrown away and a claim taken there would be kept by a
 *  component that never mounted. Whoever is first to mount reads; everybody
 *  else is told what it got. When the reader goes, the rest are told and the
 *  next one takes it over, so the read follows the Turns that are on screen. */
function useShared<T>(path: string | null): ApiState<T> {
  const [, bump] = useState(0)
  const self = useRef({})
  const share = path ? shareOf<T>(path) : null
  const [mine, setMine] = useState(false)

  useEffect(() => {
    if (!share) {
      setMine(false)
      return
    }
    const me = self.current
    const claim = () => {
      if (share.owner === null) share.owner = me
      setMine(share.owner === me)
    }
    const tell = () => {
      claim()
      bump((n) => n + 1)
    }
    share.listeners.add(tell)
    claim()
    return () => {
      share.listeners.delete(tell)
      if (share.owner === me) {
        share.owner = null
        share.state = WAITING
        for (const l of [...share.listeners]) l()
      }
    }
  }, [share])

  /* THE ORDINARY READER, so that this rereads on an advance exactly like every
     other reader here. `null` for everybody who is not the elected one. */
  const read = useApi<T>(mine && path ? path : null)

  useEffect(() => {
    if (!share || !mine) return
    share.state = read
    for (const l of [...share.listeners]) l()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [share, mine, read.data, read.error, read.loading])

  if (!share) return IDLE as ApiState<T>
  return mine ? read : (share.state as ApiState<T>)
}

/* ------------------------------ the indexes ------------------------------- */

export interface TurnGovernance {
  /** the governed items this Turn's work brought into being, by reference */
  items: Id[]
}

const NOTHING: TurnGovernance = { items: [] }

/* WHICH RUN POSTED A TURN IS NOT READ HERE. It comes with the Turn itself
   (`Turn.execution`, `Turn.runtime`), from that Turn's own acts. It used to be
   read here off `/api/operational?limit=1000`, which is the Conversation's
   OLDEST thousand acts: the newest Turns, the ones being read, had no footer. */

export interface InSituIndex {
  byTurn: (turn: Id) => TurnGovernance
  /** the register rows this Conversation's Turns refer to, by entry */
  row: (entry: Id) => RegisterRow | null
  /** why a read could not be made, said rather than drawn as an absence */
  error: string | null
  loading: boolean
}

/** Everything the in-situ cards in ONE Conversation need in order to know
 *  WHICH Turns carry a reference and to what. One shared read, whatever the
 *  number of Turns on screen. */
export function useInSituIndex(_conversation: Id | null): InSituIndex {
  const reg = useShared<Register>('/api/governed?limit=1000')

  const rows: RegisterRow[] = reg.data
    ? Object.values(reg.data.groups).flat()
    : []
  const byEntry = new Map<Id, RegisterRow>(rows.map((r) => [r.entry, r]))

  const byTurn = new Map<Id, TurnGovernance>()
  const at = (turn: Id) => {
    let g = byTurn.get(turn)
    if (!g) {
      g = { items: [] }
      byTurn.set(turn, g)
    }
    return g
  }
  for (const r of rows)
    for (const p of r.proposed_by)
      if (p.turn && !at(p.turn).items.includes(r.entry)) at(p.turn).items.push(r.entry)

  return {
    byTurn: (turn) => byTurn.get(turn) ?? NOTHING,
    row: (entry) => byEntry.get(entry) ?? null,
    error: reg.error,
    loading: reg.loading,
  }
}

/** One item's own current state, read from the item and from nothing else.
 *
 *  THE SAME READ GOVERNANCE MAKES. `/api/governance/history` answers what was
 *  written, whether anybody established it, where it is placed, what ended it,
 *  what it ended, and which challenges are open — which is every word an
 *  in-situ card says. The card holds no copy of any of it. */
export function useItem(entry: Id | null): { item: ItemTimeline | null; error: string | null; loading: boolean } {
  const got = useShared<ItemHistory>(entry ? `/api/governance/history?entry=${entry}` : null)
  const mine = got.data?.timeline.find((t) => t.entry === entry) ?? null
  return { item: mine, error: got.error, loading: got.loading }
}

/** What one execution received — or the statement that no record says. */
export function useExecutionSheet(execution: string | null): {
  sheet: ExecutionSheet | null
  error: string | null
} {
  const got = useShared<ExecutionSheet>(
    execution ? `/api/governance/execution?execution=${encodeURIComponent(execution)}` : null,
  )
  return { sheet: got.data, error: got.error }
}
