import { useEffect, useMemo, useState } from 'react'
import { read, useApi, type Expectation, type Id, type OwedList } from '../../api'
import { governanceAsksIn } from './owedHere'

/* ------------------------------------------------------------------------ *
 * WHICH GOVERNED ITEMS AN OPEN ASK ALREADY COVERS.
 *
 * WHY ANYTHING NEEDS TO KNOW. An act offered beside an ask about the same
 * material makes two obligations out of one: the owner answers the ask, and
 * then the item still carries a control saying the same decision is waiting.
 * The Turn already suppresses its in-situ set-aside for exactly this reason;
 * the item inspector is reached from everywhere and has no Turn to ask, so it
 * asks the record instead.
 *
 * WHY IT TAKES TWO READS. `/api/owed` answers the obligation — who is asked,
 * by whom, in which Conversation — and deliberately does not answer what the
 * ask is ABOUT, because owing is not a fact about material. What an ask names
 * is recorded on the expectation, which the Turn it was made in carries. So
 * this reads the owner's open asks, then the Turns those asks hang on, and
 * collects the material their expectations name. Open asks are few by
 * construction, and the alternative would be a route pretending that owing and
 * material are one fact.
 *
 * ABSENT IS NOT EMPTY. Until both reads have answered, `known` is false and the
 * set is empty — which means "not yet known", never "no ask covers anything".
 * A caller must not read an empty set as permission; it must read `known`.
 * ------------------------------------------------------------------------ */

/** Only what this needs of a Turn: which expectations it carries, what each of
 *  them names, and — for `useAskAbout` below — the prose that IS the question.
 *  The expectation's id is `id`, which is what the route sends and what
 *  `Expectation` declares. */
interface TurnExpectations {
  expectations?: Expectation[]
  parts?: { type: string; text?: string }[]
}

/** The prose of a Turn, which is where an ask's question actually lives. The
 *  expectation's `because` is the asker's REASON and is not the question. */
function proseOf(t: TurnExpectations | null): string {
  return (t?.parts ?? [])
    .filter((p) => p.type === 'text' && p.text)
    .map((p) => p.text as string)
    .join('\n\n')
    .trim()
}

export interface AskCoverage {
  /** every governed item named by an expectation still owed by this person */
  named: Set<Id>
  /** both reads have answered. False means UNKNOWN, not "nothing covers it". */
  known: boolean
}

export function useAskCoverage(me: Id | null): AskCoverage {
  const owed = useApi<OwedList>(
    me ? '/api/owed?participant=' + encodeURIComponent(me) + '&limit=50' : null,
  )
  const rows = owed.data?.owed ?? null
  /* KEYED ON WHAT THE FIRST READ SAID, not on the array it said it in. `useApi`
     rereads on every advance and hands back a fresh array each time; following
     that identity would re-read every Turn whenever anything anywhere moved. */
  const key = useMemo(
    () => (rows ? rows.map((r) => r.expectation + '@' + (r.turn ?? '')).join(',') : null),
    [rows],
  )
  const [named, setNamed] = useState<Set<Id> | null>(null)

  useEffect(() => {
    if (key === null || rows === null) {
      setNamed(null)
      return
    }
    const open = new Set(rows.map((r) => r.expectation))
    const turns = [...new Set(rows.map((r) => r.turn).filter(Boolean))] as Id[]
    if (turns.length === 0) {
      /* Asks the record does not tie to a Turn name no material, so there is
         nothing they could cover. A known answer, and an empty one. */
      setNamed(new Set())
      return
    }
    let alive = true
    void Promise.all(
      /* A TURN THAT CANNOT BE READ IS NOT AN ANSWER ABOUT IT. It contributes
         nothing to the set rather than failing the whole question, and the
         worst it can cost is an act offered beside an ask. */
      turns.map((t) => read<TurnExpectations>('/api/turns/' + encodeURIComponent(t)).catch(() => null)),
    ).then((got) => {
      if (!alive) return
      const out = new Set<Id>()
      for (const turn of got)
        for (const e of turn?.expectations ?? [])
          if (open.has(e.id)) for (const m of e.material ?? []) out.add(m)
      setNamed(out)
    })
    return () => {
      alive = false
    }
    /* `rows` is followed through `key`, which is what changes when the asks
       themselves change rather than when the array holding them is rebuilt. */
  }, [key])

  return { named: named ?? new Set<Id>(), known: named !== null }
}

/* ------------------------------------------------------------------------ *
 * AND WHICH OPEN ASK DROVE THIS PARTICULAR LOOK.
 *
 * Compare is reached from an ask, from an overlap condition, from a row, from
 * the inspector and from a Turn. Only the first of those has somebody waiting
 * on an answer, and the surface says which it is out loud — "Nobody is asking.
 * Doing nothing is a legitimate answer." is a CLAIM, and it may only be made
 * once the record has actually been asked. So this answers three ways, never
 * two: an ask, no ask, or not yet known.
 *
 * ALL OF THEM, NOT ANY OF THEM. An ask drives a comparison when its own
 * expectation names every item being compared; one that names only one of the
 * two is an ask about that item and answering it from here would close
 * somebody else's question.
 * ------------------------------------------------------------------------ */

/** The open ask behind a look at some material, as a surface has to speak
 *  about it. Every field is the record's. */
export interface DrivingAsk {
  expectation: Id
  /** the Turn it was made in. A reply answers the Turn that asked. */
  turn: Id | null
  conversation: Id | null
  conversation_name: string | null
  asked_by: Id | null
  asked_by_alias: string | null
  /** the question in the asker's own words: the Turn's prose, or the recorded
   *  reason where the Turn holds no words. */
  question: string
  at: number
  /** what it expects; `input` closes only on Done at its block */
  expects?: string
  /** a question of a decision form (P7), which closes only at its form */
  form?: string | null
}

export interface AskAbout {
  /** the ask, or null for "the record holds none". Meaningless until `known`. */
  ask: DrivingAsk | null
  /** both reads have answered. False is UNKNOWN and is never "nobody asked". */
  known: boolean
}

export function useAskAbout(me: Id | null, ids: Id[]): AskAbout {
  const owed = useApi<OwedList>(
    me ? '/api/owed?participant=' + encodeURIComponent(me) + '&limit=50' : null,
  )
  const rows = owed.data?.owed ?? null
  const key = useMemo(
    () => (rows ? rows.map((r) => r.expectation + '@' + (r.turn ?? '')).join(',') : null),
    [rows],
  )
  /** what is being asked ABOUT, as a stable string, so that re-rendering with
   *  a fresh array of the same two ids does not re-read every Turn. */
  const want = useMemo(() => ids.filter(Boolean).join('|'), [ids])
  const [found, setFound] = useState<{ for: string; ask: DrivingAsk | null } | null>(null)

  useEffect(() => {
    if (key === null || rows === null || !want) {
      setFound(null)
      return
    }
    const wanted = want.split('|')
    const turns = [...new Set(rows.map((r) => r.turn).filter(Boolean))] as Id[]
    if (turns.length === 0) {
      /* Asks the record does not tie to a Turn name no material, so none of
         them can be about these two. A known answer, and an empty one. */
      setFound({ for: want, ask: null })
      return
    }
    let alive = true
    void Promise.all(
      turns.map((t) =>
        read<TurnExpectations>('/api/turns/' + encodeURIComponent(t))
          .then((d) => [t, d] as const)
          /* A Turn that cannot be read is not an answer about it. It costs at
             most an ask this surface does not know it could answer. */
          .catch(() => [t, null] as const),
      ),
    ).then((got) => {
      if (!alive) return
      const prose = new Map(got.map(([t, d]) => [t, d]))
      for (const r of rows) {
        const turn = r.turn ? prose.get(r.turn) : null
        const e = turn?.expectations?.find((x) => x.id === r.expectation)
        const material = e?.material ?? []
        if (!wanted.every((w) => material.includes(w))) continue
        setFound({
          for: want,
          ask: {
            expectation: r.expectation,
            turn: r.turn,
            conversation: r.conversation,
            conversation_name: r.conversation_name ?? null,
            asked_by: r.asked_by,
            asked_by_alias: r.asked_by_alias,
            question: (r.form ? r.question : null) || proseOf(turn ?? null) || r.because || r.expects,
            at: r.at,
            expects: r.expects,
            form: r.form ?? null,
          },
        })
        return
      }
      setFound({ for: want, ask: null })
    })
    return () => {
      alive = false
    }
    /* `rows` is followed through `key`, as above. */
  }, [key, want])

  /* THE ANSWER IS ONLY AN ANSWER ABOUT WHAT WAS ASKED. Holding the subject it
     was computed for is what stops a stale yes being read as a yes about the
     pair now on screen. */
  return { ask: found?.for === want ? found.ask : null, known: found?.for === want }
}

/* ------------------------------------------------------------------------ *
 * AND HOW MANY OF THEM ARE OWED IN ONE CONVERSATION (I-3, the chip's dot).
 *
 * ONLY ASKS. The `governs N +k` chip already says what has been proposed, and
 * a proposal asks nothing of anybody; the dot says that somebody is waiting on
 * this person for a governance decision here. So it counts the owed asks made
 * in this Conversation whose expectation names material -- the same
 * expectation field `useAskCoverage` reads -- and never reads a candidate. The
 * counting itself is `governanceAsksIn`, which is pure and tested.
 *
 * NULL IS UNKNOWN, as above, and the chip draws no dot for it rather than a
 * claim either way.
 * ------------------------------------------------------------------------ */
export function useGovernanceAsksIn(me: Id | null, conversation: Id | null): number | null {
  const owed = useApi<OwedList>(
    me && conversation ? '/api/owed?participant=' + encodeURIComponent(me) + '&limit=50' : null,
  )
  const rows = useMemo(
    () => (owed.data?.owed ?? null)?.filter((r) => r.conversation === conversation) ?? null,
    [owed.data, conversation],
  )
  const key = useMemo(
    () => (rows ? rows.map((r) => r.expectation + '@' + (r.turn ?? '')).join(',') : null),
    [rows],
  )
  const [found, setFound] = useState<{ for: string; n: number } | null>(null)

  useEffect(() => {
    if (key === null || rows === null) return
    const turns = [...new Set(rows.map((r) => r.turn).filter(Boolean))] as Id[]
    if (turns.length === 0 || conversation === null) {
      setFound({ for: key, n: 0 })
      return
    }
    let alive = true
    void Promise.all(
      turns.map((t) => read<TurnExpectations>('/api/turns/' + encodeURIComponent(t)).catch(() => null)),
    ).then((got) => {
      if (!alive) return
      setFound({ for: key, n: governanceAsksIn(rows, got, conversation) })
    })
    return () => {
      alive = false
    }
    /* `rows` is followed through `key`, as above. */
  }, [key])

  return key !== null && found?.for === key ? found.n : null
}
