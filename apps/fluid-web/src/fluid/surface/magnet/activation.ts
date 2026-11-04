/* A PRESS OF ACTIVATE (docs/magnets/M1-contract.md, "Manual activation"),
 * browser-free, its door injected so tests count every call (client.ts binds
 * the real one).
 *
 * One press is one operation key, and nothing here presses for anybody: there
 * is no retry, timer or queue. The key is kept from before it is sent until an
 * answer says what came of it, so a lost answer, even across a reload, is asked
 * again only under the key it was lost under, and a new key can't record a
 * second activation. What the server answers is said in its own words.
 *
 *   201, 200                 recorded, or an earlier press's record replayed
 *   503 Busy                 nothing was recorded: a later press has a new key,
 *                            unless this one was asking about a lost answer
 *   503 OutcomeUnknown, any  nobody knows: the key stays for the next press
 *   other failure of the
 *   server's, anything not
 *   understood
 *   every other refusal      said; the key goes */

import type { MagnetId } from './types'

export type ActivationPhase = 'idle' | 'running' | 'complete' | 'partial' | 'busy' | 'refused' | 'unknown'

export interface ActivationResult {
  magnet: string
  state: 'complete' | 'partial'
  conversation: string
  conversation_created: boolean
  post: string
  page: { sources: number; results: number; statuses: Record<string, number>; kept: Array<{ facet: string; reason: string }> }
  replayed: boolean
}

export interface ActivationNow {
  phase: ActivationPhase
  /** what the server said, or how this client lost its answer */
  words?: string
  result?: ActivationResult
  /** the next press asks again under the key whose answer was lost */
  sameKey?: boolean
}

export interface ActivationKey { author: string; op: string }

export interface ActivationDoor {
  /** The one POST. Rejects when no whole answer came. */
  post(magnet: MagnetId, key: ActivationKey): Promise<{ status: number; body: unknown }>
  me(): Promise<string>
  newKey(): string
  /** where a key waits for its answer: past this page, so a reload doesn't lose it */
  keptKey(magnet: MagnetId): ActivationKey | null
  keepKey(magnet: MagnetId, key: ActivationKey | null): void
}

const IDLE: ActivationNow = { phase: 'idle' }
const LOST = 'The answer to this press was lost, so it may or may not have been recorded. Pressing again asks under the same key.'
const WAS_LOST = 'An earlier press was never answered here, so it may or may not have been recorded. Pressing again asks under the same key.'

const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`

/** What a recorded activation came to: partial says what it held back, in the server's words. */
export function resultWords(r: ActivationResult): string {
  const page = `${plural(r.page.results, 'result')} from ${plural(r.page.sources, 'source')}`
  const held = Object.entries(r.page.statuses).filter(([s, n]) => s !== 'ok' && n > 0).map(([s, n]) => `${n} ${s}`)
  const kept = r.page.kept.map((k) => `${k.facet}: ${k.reason}`)
  const partly = r.state === 'partial' ? ` Partial: ${[...held, ...kept].join('; ') || 'not every source answered in full'}.` : ''
  return `${r.replayed ? 'Already recorded under this key, and nothing was written again: ' : 'Recorded in its own Conversation: '}${page}.${partly}`
}

const isResult = (b: unknown): b is ActivationResult => {
  const r = b as Partial<ActivationResult> | null
  return !!r && (r.state === 'complete' || r.state === 'partial') && typeof r.conversation === 'string' && typeof r.post === 'string'
}
const saidIn = (b: unknown): string | undefined => {
  const r = b as { reason?: { message?: unknown }; error?: unknown } | null
  const said = r?.reason?.message ?? r?.error
  return typeof said === 'string' && said ? said : undefined
}

/** What an answer says of the press it answers. `asking`: it asked about a lost answer, and only a
 *  result, or a refusal from past the key's look-up (400 and 422 are the body's and the key's, 404
 *  and 409 the definition's, and all come from Python), says what became of that. */
export function readAnswer(status: number, body: unknown, asking: boolean): { now: ActivationNow; keepsKey: boolean } {
  const kind = (body as { kind?: unknown } | null)?.kind
  if ((status === 200 || status === 201) && isResult(body)) return { now: { phase: body.state, result: body, words: resultWords(body) }, keepsKey: false }
  const said = saidIn(body)
  /* these say nothing was written; any other failure of the server's doesn't */
  const nothingWritten = kind === 'Busy' || kind === 'ProcessorUnavailable' || kind === 'InternalProtocolError'
  if (status < 400 || !said || (status >= 500 && !nothingWritten))
    return { now: { phase: 'unknown', words: said ?? LOST, sameKey: true }, keepsKey: true }
  const looked = status === 400 || status === 404 || status === 409 || status === 422
  if (asking && !looked) return { now: { phase: kind === 'Busy' ? 'busy' : 'refused', words: `${said} ${LOST}`, sameKey: true }, keepsKey: true }
  return { now: { phase: kind === 'Busy' ? 'busy' : 'refused', words: said }, keepsKey: false }
}

export interface Activations {
  now(magnet: MagnetId): ActivationNow
  /** one press; while one is running here, that one. Never rejects: how it went is `now`. */
  press(magnet: MagnetId): Promise<ActivationNow>
  subscribe(fn: () => void): () => void
}

export function createActivations(door: ActivationDoor): Activations {
  const said = new Map<MagnetId, ActivationNow>()
  const running = new Map<MagnetId, Promise<ActivationNow>>()
  const heard = new Set<() => void>()
  const set = (magnet: MagnetId, now: ActivationNow) => {
    said.set(magnet, now)
    heard.forEach((fn) => fn())
    return now
  }
  const now = (magnet: MagnetId): ActivationNow => {
    const known = said.get(magnet)
    if (known) return known
    /* first asked of this Magnet on this page: a key still kept is an answer lost before it */
    const kept = door.keptKey(magnet) ? { phase: 'unknown' as const, words: WAS_LOST, sameKey: true } : IDLE
    said.set(magnet, kept)
    return kept
  }
  const press = async (magnet: MagnetId): Promise<ActivationNow> => {
    const kept = door.keptKey(magnet)
    let key: ActivationKey
    try {
      key = kept ?? { author: await door.me(), op: door.newKey() }
    } catch (e) {
      return set(magnet, { phase: 'refused', words: (e as Error).message })
    }
    set(magnet, { phase: 'running', words: kept ? 'Asking again under the same key…' : 'Running…' })
    door.keepKey(magnet, key)
    try {
      const got = await door.post(magnet, key)
      const { now: answered, keepsKey } = readAnswer(got.status, got.body, !!kept)
      if (!keepsKey) door.keepKey(magnet, null)
      return set(magnet, answered)
    } catch {
      return set(magnet, { phase: 'unknown', words: LOST, sameKey: true })
    }
  }
  return {
    now,
    press(magnet) {
      const already = running.get(magnet)
      if (already) return already
      const one = press(magnet).finally(() => running.delete(magnet))
      running.set(magnet, one)
      return one
    },
    subscribe(fn) { heard.add(fn); return () => { heard.delete(fn) } },
  }
}
