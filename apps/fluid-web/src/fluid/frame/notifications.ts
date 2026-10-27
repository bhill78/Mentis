/* RESULTS AND REQUESTS FOR YOU, FROM SOMEWHERE YOU ARE NOT LOOKING (D2).
 *
 * Classic's toasts (surfaces/Toasts.tsx), ported -- not mounted -- into
 * Fluid's frame. The owner's answer there (#140) holds here: exactly two
 * kinds and nothing else.
 *
 *   result   an agent returned a result or delivered what was owed:
 *            `result-returned` or `expectation-met`, from `/api/operational`
 *   ask      something now asks you for a decision or a response: from
 *            `/api/owed`, the list the Asks counter and Needs you draw
 *
 * Progress raises nothing. THE FIRST READ IS THE BASELINE and is never
 * announced, so a reload is quiet. Nothing in the conversation on screen is
 * announced: it is already in front of you. A burst in one place is one
 * toast that counts the rest; at most three are shown; each stays 6 s unless
 * the pointer or the keyboard is on it (Toasts.tsx in this folder).
 *
 * THE HISTORY THE BELL READS is what was actually offered, kept on this
 * device under the same key and in the same shape Classic keeps it
 * (surfaces/notifications.ts: `mentis:notifications:<corpus>`), so one
 * history is one history whichever face showed it. Showing, pausing and
 * dismissing a toast records no act and writes nothing to the record.
 *
 * Read on the pulse (identity/activity.ts `hearPulse`): when the record
 * moves, and at most every 30 s otherwise; only while the frame listens. */

import { useEffect, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { hearPulse } from '../identity/activity'
import { at as atName, personOf } from '../identity/people'
import { brainIdentity, type Id } from '../store'

export type Kind = 'result' | 'ask'

export interface Notice {
  key: string
  kind: Kind
  conversation: Id
  turn: Id | null
  /** "@Mason returned a result" */
  headline: string
  /** "Mentis UI/UX · #UI polish 1" */
  where: string
  /** what a collapsed burst is counted in */
  convName: string
  /** the first words of the post, every reference id taken out */
  excerpt: string
  /** a burst in the same place, collapsed into this one */
  more: number
  /** who it is from, to draw them (Fluid's own; Classic ignores it) */
  actor?: Id | null
  actorAlias?: string | null
}
export interface Kept extends Notice { at: number; unseen: boolean }

/** How many are on screen at once; the oldest makes way. */
export const STACK = 3
/** Acts are read newest first, this many at a time. */
const WINDOW = 40
/** One run returning a result usually also records `expectation-met`. */
const SAME_RUN_S = 30
const KEEP = 50
const SPACING = 1000
const STALE = 30000
const RESULT_ACTS: Record<string, string> = {
  'result-returned': 'returned a result',
  'expectation-met': 'delivered what was owed',
}

const asksFor = (expects: string) => (expects === 'decision' ? 'asks you to decide' : 'asks you for a response')

/** Words only: a post's references keep their names and lose their ids. */
export function plain(text: string, max = 140): string {
  const s = text
    .replace(/\[(?:topic|turn|conversation|participant|entry|artifact)[^\]]*\]/gi, '')
    .replace(/\b(?:ent|opr|adm|art)-[0-9a-f]{6,}\b/gi, '')
    .replace(/\[\s*\]|\(\s*\)/g, '')   // what held only an id holds nothing now
    .replace(/\*+|`+/g, '')
    .replace(/(^|\n)\s*(?:#{1,6}|>+)\s+/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
  return s.length > max ? s.slice(0, max - 1).trimEnd() + '…' : s
}

const json = async <T,>(path: string): Promise<T> => {
  const res = await fetch(path, { headers: { ...CLIENT_HEADERS } })
  const body = await res.json().catch(() => null)
  if (!res.ok || !body || body.error) throw new Error(body?.error ?? res.statusText)
  return body as T
}

interface Act { id: Id; act: string; at: number; actor: Id | null; conversation: Id | null; turn: Id | null; execution?: Id | null }
interface Ask { expectation: Id; at: number; conversation: Id | null; conversation_name?: string | null; turn: Id | null; expects: string; asked_by?: Id | null; asked_by_alias?: string | null; because?: string | null }
interface Candidate { key: string; kind: Kind; conversation: Id; conversationName: string | null; turn: Id | null; actor: Id | null; alias: string | null; headline: string; fallback: string }
interface TurnRead { parts?: { type: string; text?: string }[]; topics?: Id[]; deleted?: unknown }
interface Place { name: string; topics?: { id: Id; name: string }[] }

/* -- the state: toasts on screen, the history kept --------------------------- */

let toasts: Notice[] = []
let kept: Kept[] = []
let storageKey: string | null = null
let opened = false
const heard = new Set<() => void>()
const tell = () => heard.forEach((fn) => fn())
const subscribe = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }

export const useToasts = () => useSyncExternalStore(subscribe, () => toasts)
export const useKept = () => useSyncExternalStore(subscribe, () => kept)

export function dismissNotice(key: string) {
  const next = toasts.filter((t) => t.key !== key)
  if (next.length !== toasts.length) { toasts = next; tell() }
}

const valid = (n: any): n is Kept => n && typeof n.key === 'string' && (n.kind === 'result' || n.kind === 'ask')
  && typeof n.conversation === 'string' && (n.turn === null || typeof n.turn === 'string') && typeof n.headline === 'string'
  && typeof n.where === 'string' && typeof n.excerpt === 'string' && typeof n.convName === 'string'
  && typeof n.more === 'number' && typeof n.at === 'number' && typeof n.unseen === 'boolean'

/** What this device holds now: Classic, in another tab, may have added to it. */
function load(): Kept[] {
  if (!storageKey) return kept
  try {
    const v: unknown = JSON.parse(localStorage.getItem(storageKey) ?? '[]')
    return Array.isArray(v) ? v.filter(valid).slice(0, KEEP) : []
  } catch { return kept }
}

function save(next: Kept[]) {
  kept = next
  if (storageKey) {
    try { localStorage.setItem(storageKey, JSON.stringify(next)) } catch { /* a convenience on this device, not a record */ }
  }
  tell()
}

/** Keep what was offered: a growing burst replaces its earlier snapshot. */
function record(t: Notice) {
  const root = t.key.replace(/\++$/, '')
  save([{ ...t, at: Date.now(), unseen: !opened }, ...load().filter((n) => n.key.replace(/\++$/, '') !== root)].slice(0, KEEP))
}

/** The bell's sheet is open (true) or closed: what it shows is seen. */
export function bellOpen(open: boolean) {
  opened = open
  if (open) {
    const all = load()
    if (all.some((n) => n.unseen) || all !== kept) save(all.map((n) => (n.unseen ? { ...n, unseen: false } : n)))
  }
}

/* -- reading ------------------------------------------------------------------ */

let me: Id | null = null
let here: Id | null = null
let seenActs: Set<Id> | null = null
let seenAsks: Set<Id> | null = null
let loadedAt = Date.now() / 1000
const runs = new Map<string, number>()
let lastRead = 0
let readTimer: number | null = null
let reading = false
const places = new Map<Id, Place>()

function offerNow(n: Notice) {
  const same = toasts.find((t) => t.kind === n.kind && t.conversation === n.conversation)
  /* A BURST IS ONE TOAST: the first stays the headline, the rest are counted,
     and it starts its life again (a new key remounts it). */
  const next = same ? { ...same, key: same.key + '+', more: same.more + 1 } : n
  toasts = same ? [...toasts.filter((t) => t !== same), next] : [...toasts, next].slice(-STACK)
  record(next)
  tell()
}

async function offer(cs: Candidate[]) {
  for (const c of cs) {
    let turn: TurnRead | null = null
    if (c.turn) turn = await json<TurnRead>(`/api/turns/${encodeURIComponent(c.turn)}`).catch(() => null)
    /* NOT WHERE YOU ARE: the conversation on screen is already in front of you. */
    if (c.conversation === here) continue
    let place = places.get(c.conversation)
    if (!place) {
      place = await json<Place>(`/api/conversations/${encodeURIComponent(c.conversation)}?batch=0`).catch(() => undefined)
      if (place) places.set(c.conversation, place)
    }
    if (c.conversation === here) continue
    const convName = place?.name ?? c.conversationName ?? 'another conversation'
    const topic = (turn?.topics ?? []).map((t) => place?.topics?.find((x) => x.id === t)?.name).find(Boolean)
    const words = turn && !turn.deleted ? plain((turn.parts ?? []).filter((p) => p.type === 'text').map((p) => p.text ?? '').join(' ')) : ''
    offerNow({
      key: c.key, kind: c.kind, conversation: c.conversation, turn: c.turn, headline: c.headline,
      where: topic ? `${convName} · #${topic}` : convName, convName, excerpt: words || c.fallback, more: 0,
      actor: c.actor, actorAlias: c.alias,
    })
  }
}

function results(list: Act[]): Candidate[] {
  if (!seenActs) { seenActs = new Set(list.map((a) => a.id)); return [] }
  const fresh: Candidate[] = []
  for (const a of [...list].reverse()) {
    if (seenActs.has(a.id)) continue
    seenActs.add(a.id)
    const said = RESULT_ACTS[a.act]
    if (!said || !a.conversation || a.at < loadedAt) continue
    if (me && a.actor === me) continue   // the owner finishing something is not news to the owner
    if (a.execution) {
      const last = runs.get(a.execution)
      runs.set(a.execution, a.at)
      if (last !== undefined && Math.abs(a.at - last) < SAME_RUN_S) continue
    }
    const alias = personOf(a.actor)?.alias ?? null
    fresh.push({ key: a.id, kind: 'result', conversation: a.conversation, conversationName: null, turn: a.turn,
      actor: a.actor, alias, headline: `${alias ? atName(alias) : 'Somebody'} ${said}`, fallback: '' })
  }
  return fresh
}

function asks(list: Ask[]): Candidate[] {
  if (!seenAsks) { seenAsks = new Set(list.map((o) => o.expectation)); return [] }
  const fresh: Candidate[] = []
  for (const o of [...list].reverse()) {
    if (seenAsks.has(o.expectation)) continue
    seenAsks.add(o.expectation)
    if (!o.conversation || o.at < loadedAt) continue
    const alias = o.asked_by_alias ?? personOf(o.asked_by)?.alias ?? null
    fresh.push({ key: o.expectation, kind: 'ask', conversation: o.conversation, conversationName: o.conversation_name ?? null,
      turn: o.turn, actor: o.asked_by ?? null, alias, headline: `${alias ? atName(alias) : 'Somebody'} ${asksFor(o.expects)}`,
      fallback: o.because ? plain(o.because) : '' })
  }
  return fresh
}

async function read() {
  if (reading) return
  reading = true
  lastRead = Date.now()
  try {
    const [ops, owed] = await Promise.all([
      json<{ operational: Act[] }>(`/api/operational?newest=1&limit=${WINDOW}`).catch(() => null),
      me ? json<{ owed: Ask[] | null }>(`/api/owed?participant=${encodeURIComponent(me)}&limit=50`).catch(() => null) : Promise.resolve(null),
    ])
    const fresh = [...(ops?.operational ? results(ops.operational) : []), ...(owed?.owed ? asks(owed.owed) : [])]
    if (fresh.length) await offer(fresh)
  } finally {
    reading = false
  }
}

function soon() {
  if (readTimer !== null) return
  readTimer = window.setTimeout(() => { readTimer = null; void read() }, Math.max(0, lastRead + SPACING - Date.now()))
}

/** Follow results and asks while the frame is mounted. `who` is the reader
 *  (asks are theirs; their own results are not news); `shown` the
 *  conversation on screen. */
export function useNotifications(who: Id | null, shown: Id | null) {
  useEffect(() => { here = shown }, [shown])
  useEffect(() => {
    if (!who) return
    me = who
    loadedAt = Date.now() / 1000
    seenActs = null
    seenAsks = null
    let live = true
    void brainIdentity().then((b) => {
      if (!live || !b?.corpus_id) return
      storageKey = `mentis:notifications:${b.corpus_id}`
      kept = load()
      tell()
    }).catch(() => {})
    void read()
    const stop = hearPulse((m) => { if (m === 'durable') soon() })
    const t = window.setInterval(() => { if (Date.now() - lastRead > STALE) soon() }, 5000)
    return () => { live = false; stop(); clearInterval(t) }
  }, [who])
}
