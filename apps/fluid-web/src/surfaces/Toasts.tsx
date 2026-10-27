import { useCallback, useEffect, useRef, useState } from 'react'
import { read, said, useApi, type ConversationList, type Id, type OperationalList, type OwedList, type Turn } from '../api'
import { useMe } from '../identity'
import { type Nav } from '../nav'
import { openNotification } from './notifications'
import './Toasts.css'

/* ------------------------------------------------------------------------ *
 * TOASTS: WHAT CAME BACK, OR WHAT ASKS YOU, SOMEWHERE YOU ARE NOT LOOKING.
 *
 * The owner's answer (#140): "Results and requests for you". So exactly two
 * kinds, and nothing else:
 *
 *   result   an agent returned a result or delivered what was owed —
 *            `result-returned` or `expectation-met`, read from the same
 *            operational acts every other surface reads.
 *   ask      something now asks the owner for a decision or a response —
 *            read from `/api/owed`, the very list the Asks counter in the app
 *            bar draws. There is no second computation of "awaiting you" here.
 *
 * Progress (started, resumed, delegated, discovered, …) raises nothing.
 *
 * THE VISIBLE STACK IS TRANSIENT. Its offered snapshots are kept separately
 * in the notification history; dismissing here leaves that history intact.
 * A toast is interface state: showing, pausing and
 * dismissing one records no act and writes nothing. The first read after the
 * page loads is the baseline and is never announced, so a reload is quiet.
 *
 * NOT WHERE YOU ARE. An event in the Conversation on screen raises nothing —
 * unless a Topic is focused there and the Turn is not filed under it, because
 * then it is somewhere else you are not looking.
 * ------------------------------------------------------------------------ */

type Kind = 'result' | 'ask'

export interface Toast {
  key: string
  kind: Kind
  conversation: Id
  turn: Id | null
  /** "@Mason returned a result" */
  headline: string
  /** "Mentis UI/UX · #UI polish 1" */
  where: string
  /** "Mentis UI/UX": what a collapsed burst is counted in */
  convName: string
  /** the first words of the Turn, with every reference id taken out */
  excerpt: string
  /** a burst in the same place, collapsed into this toast */
  more: number
}

/** How long a toast stays when nobody is looking at it. */
const LIFE_MS = 6000
/** How many are on screen at once; the oldest makes way. */
const STACK = 3
/** Acts are read newest first, this many at a time. */
const WINDOW = 40
/** One run returning a result usually also records `expectation-met`: one
 *  piece of work finishing is one toast, not two. */
const SAME_RUN_S = 30

const RESULT_ACTS = new Set(['result-returned', 'expectation-met'])

/* ---- what else is on screen ------------------------------------------------
 * Compare holds its right half in its own state, out of the shell's sight. It
 * names it here -- the Conversation AND the Topic that half is focused on --
 * so that half is "on screen" by the same rule as the shell's own: all of
 * the Conversation when no Topic is focused, only what is filed under the
 * Topic when one is (review 2, R5; it used to count the whole Conversation). */
interface Half {
  /** null at Brain scope: then no Conversation is on screen there */
  conversation: Id | null
  topic: Id | null
}
const also = new Set<Half>()
const alsoListeners = new Set<() => void>()
export function useAlsoOnScreen(id: Id | null, topic: Id | null = null) {
  useEffect(() => {
    if (!id) return
    const half: Half = { conversation: id, topic }
    also.add(half)
    alsoListeners.forEach((f) => f())
    return () => {
      also.delete(half)
      alsoListeners.forEach((f) => f())
    }
  }, [id, topic])
}

/** Words only. A Turn's text carries structured references as
 *  `#Name[topic:ent-…]`; the name stays, the id never reaches the toast. */
export function plain(text: string, max = 140): string {
  const s = text
    .replace(/\[(?:topic|turn|conversation|participant|entry|artifact)[^\]]*\]/gi, '')
    .replace(/\b(?:ent|opr|adm|art)-[0-9a-f]{6,}\b/gi, '')
    // markdown's marks are not words: emphasis, code ticks, heading and quote
    // markers go; a `#Topic` name stays
    .replace(/\*+|`+/g, '')
    .replace(/(^|\n)\s*(?:#{1,6}|>+)\s+/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
  return s.length > max ? s.slice(0, max - 1).trimEnd() + '…' : s
}

const firstWords = (t: Turn | null) =>
  t && !t.deleted ? plain((t.parts ?? []).filter((p) => p.type === 'text').map((p) => p.text ?? '').join(' ')) : ''

const asksFor = (expects: string) =>
  expects === 'decision' ? 'asks you to decide' : 'asks you for a response'

const noun = (kind: Kind, n: number) =>
  kind === 'result' ? (n === 1 ? 'result' : 'results') : n === 1 ? 'request' : 'requests'

/** All a toast needs of a Conversation: its name and its Topics' names. */
interface Place {
  name: string
  topics: { id: Id; name: string }[]
}

interface Candidate {
  key: string
  kind: Kind
  conversation: Id
  conversationName: string | null
  turn: Id | null
  headline: string
  fallback: string
}

export default function Toasts({
  nav,
  conversations,
  onNotification,
}: {
  nav: Nav
  conversations: ConversationList | null
  onNotification: (t: Toast) => void
}) {
  const { me, person } = useMe()
  const [toasts, setToasts] = useState<Toast[]>([])

  const recorded = useRef(new Set<string>())
  useEffect(() => {
    for (const t of toasts) {
      if (recorded.current.has(t.key)) continue
      recorded.current.add(t.key)
      onNotification(t)
    }
  }, [toasts, onNotification])

  const acts = useApi<OperationalList>(`/api/operational?newest=1&limit=${WINDOW}`)
  // The same read the Asks counter makes, and so the same answer.
  const owed = useApi<OwedList>(me ? '/api/owed?participant=' + encodeURIComponent(me) + '&limit=50' : null)

  /* ---- the baseline: anything present at the first read is already seen -- */
  const loadedAt = useRef(Date.now() / 1000)
  const seenActs = useRef<Set<Id> | null>(null)
  const seenAsks = useRef<Set<Id> | null>(null)
  const runs = useRef(new Map<string, number>())

  // Read at decision time, not at render time: the reader may have moved.
  const where = useRef({ at: nav.at, conversations })
  where.current = { at: nav.at, conversations }
  const [, bump] = useState(0)
  useEffect(() => {
    const f = () => bump((n) => n + 1)
    alsoListeners.add(f)
    return () => {
      alsoListeners.delete(f)
    }
  }, [])

  const offer = useCallback(async (cs: Candidate[]) => {
    for (const c of cs) {
      let turn: Turn | null = null
      if (c.turn) {
        try {
          turn = await read<Turn>(`/api/turns/${c.turn}`)
        } catch {
          turn = null
        }
      }
      const { at, conversations: list } = where.current
      const topics = turn?.topics ?? []
      /* ON SCREEN IN ANY HALF: its Conversation is shown there, and either
         no Topic is focused there or the Turn is filed under that Topic. */
      const halves: Half[] = [{ conversation: at.conversation ?? null, topic: at.topic ?? null }, ...also]
      const onScreen = halves.some(
        (h) => h.conversation === c.conversation && (!h.topic || topics.includes(h.topic)),
      )
      if (onScreen) continue

      // A Conversation made since the rail last read is not in its list yet:
      // read it once, so the toast still names where, not "somewhere".
      let conv: Place | undefined = list?.conversations.find((x) => x.id === c.conversation)
      if (!conv) {
        try {
          conv = await read<Place>(`/api/conversations/${c.conversation}`)
        } catch {
          conv = undefined
        }
      }
      const convName = conv?.name ?? c.conversationName ?? 'another conversation'
      const topicName = topics.map((t) => conv?.topics.find((x) => x.id === t)?.name).find(Boolean)
      const place = topicName ? `${convName} · #${topicName}` : convName

      setToasts((was) => {
        const same = was.find((t) => t.kind === c.kind && t.conversation === c.conversation)
        if (same) {
          // A BURST IS ONE TOAST. The first stays the headline; the rest are
          // counted, and the toast starts its life again.
          return [
            ...was.filter((t) => t !== same),
            { ...same, key: same.key + '+', more: same.more + 1 },
          ]
        }
        const next: Toast = {
          key: c.key,
          kind: c.kind,
          conversation: c.conversation,
          turn: c.turn,
          headline: c.headline,
          where: place,
          convName,
          excerpt: firstWords(turn) || c.fallback,
          more: 0,
        }
        return [...was, next].slice(-STACK)
      })
    }
  }, [])

  /* ---- results, from the operational acts -------------------------------- */
  useEffect(() => {
    const list = acts.data?.operational
    if (!list) return
    if (!seenActs.current) {
      seenActs.current = new Set(list.map((a) => a.id))
      return
    }
    const fresh: Candidate[] = []
    for (const a of [...list].reverse()) {
      if (seenActs.current.has(a.id)) continue
      seenActs.current.add(a.id)
      if (!RESULT_ACTS.has(a.act) || !a.conversation) continue
      if (a.at < loadedAt.current) continue
      if (me && a.actor === me) continue // the owner finishing something is not news to the owner
      if (a.execution) {
        const last = runs.current.get(a.execution)
        runs.current.set(a.execution, a.at)
        if (last !== undefined && Math.abs(a.at - last) < SAME_RUN_S) continue
      }
      const who = person(a.actor)?.alias ?? 'Somebody'
      fresh.push({
        key: a.id,
        kind: 'result',
        conversation: a.conversation,
        conversationName: null,
        turn: a.turn,
        headline: `${who} ${said(a.act)}`,
        fallback: '',
      })
    }
    if (fresh.length) void offer(fresh)
  }, [acts.data, me, person, offer])

  /* ---- asks, from what the owner owes ------------------------------------ */
  useEffect(() => {
    const list = owed.data?.owed
    if (!list) return
    if (!seenAsks.current) {
      seenAsks.current = new Set(list.map((o) => o.expectation))
      return
    }
    const fresh: Candidate[] = []
    for (const o of [...list].reverse()) {
      if (seenAsks.current.has(o.expectation)) continue
      seenAsks.current.add(o.expectation)
      if (!o.conversation || o.at < loadedAt.current) continue
      const who = o.asked_by_alias ?? person(o.asked_by)?.alias ?? 'Somebody'
      fresh.push({
        key: o.expectation,
        kind: 'ask',
        conversation: o.conversation,
        conversationName: o.conversation_name ?? null,
        turn: o.turn,
        headline: `${who} ${asksFor(o.expects)}`,
        fallback: o.because ? plain(o.because) : '',
      })
    }
    if (fresh.length) void offer(fresh)
  }, [owed.data, person, offer])

  const dismiss = useCallback((key: string) => setToasts((was) => was.filter((t) => t.key !== key)), [])

  /* GOING THERE IS THE ORDINARY MOVE: the same place Brain home's rows take
     you, the Turn selected and announced so a folded group opens for it. */
  const open = (t: Toast) => {
    openNotification(nav, t)
    dismiss(t.key)
  }

  return (
    <section className="toasts" aria-label="Notifications">
      <ol className="toast-stack" aria-live="polite" aria-relevant="additions text">
        {toasts.map((t) => (
          <ToastCard key={t.key} t={t} onOpen={open} onDismiss={dismiss} />
        ))}
      </ol>
    </section>
  )
}

function ToastCard({
  t,
  onOpen,
  onDismiss,
}: {
  t: Toast
  onOpen: (t: Toast) => void
  onDismiss: (key: string) => void
}) {
  /* SIX SECONDS, UNLESS SOMEBODY IS LOOKING. Hover or focus stops the clock;
     leaving starts what was left of it. */
  const [held, setHeld] = useState({ hover: false, focus: false })
  const left = useRef(LIFE_MS)
  useEffect(() => {
    if (held.hover || held.focus) return
    const from = Date.now()
    const timer = window.setTimeout(() => onDismiss(t.key), left.current)
    return () => {
      window.clearTimeout(timer)
      left.current = Math.max(1500, left.current - (Date.now() - from))
    }
  }, [held.hover, held.focus, t.key, onDismiss])

  const burst = t.more > 0 ? `${t.more} more ${noun(t.kind, t.more)} in ${t.convName}` : null
  return (
    <li
      className={'toast toast-' + t.kind}
      onMouseEnter={() => setHeld((h) => ({ ...h, hover: true }))}
      onMouseLeave={() => setHeld((h) => ({ ...h, hover: false }))}
      onFocus={() => setHeld((h) => ({ ...h, focus: true }))}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setHeld((h) => ({ ...h, focus: false }))
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation()
          onDismiss(t.key)
        }
      }}
    >
      <button className="toast-go" onClick={() => onOpen(t)} title="Go to it">
        <span className="toast-kind">{t.kind === 'result' ? 'Result' : 'For you'}</span>
        <span className="toast-head">{t.headline}</span>
        <span className="toast-where">in {t.where}</span>
        {t.excerpt && <span className="toast-said">{t.excerpt}</span>}
        {burst && <span className="toast-more">{burst}</span>}
      </button>
      <button className="toast-x" aria-label={`Dismiss: ${t.headline}`} title="Dismiss" onClick={() => onDismiss(t.key)}>
        ×
      </button>
    </li>
  )
}
