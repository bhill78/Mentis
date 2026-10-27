/* WHAT IS FILLED IN A POSTED BLOCK, KEPT BY MENTIS (forms build P5a-P5c).
 *
 * A form, checklist, editable table or pad in a posted Turn that has a
 * usable, unique `name=` is saved through the response-set routes
 * (mentis/fluid/commands.py, P3 and P4) instead of the tab-only
 * `store.held`. Its answers then last across reloads and devices, and each
 * carries the name of whoever gave it. The fields are the block's fill
 * fields (spec/fill.ts): a form's named fields, a checklist's items by
 * their text, a table's editable cells by row key and column, a pad's text.
 *
 *   KEY      A posted named block is keyed `Turn <id>[ part <i>]/@<name>:<type>`
 *            (objects.ts, keyOf). That key is all this needs: it names the
 *            post, the text part and the block, so every copy of the block
 *            -- the post, This post, a pin -- shares one entry here.
 *   DRAFTS   What is typed stays in the tab until the field is finished (a
 *            blur, or a choice made). Then it is saved, once.
 *   OP KEYS  Every write carries an operation key made when the write is
 *            first tried. A retried save sends the same key, so the server
 *            records it once however often it arrives.
 *   REPLACES An answer names the answers to that field it was made against
 *            (the heads this tab last read). Two tabs that answer the same
 *            field from the same reading make a CONFLICT, which the server
 *            keeps; a new answer replacing both settles it.
 *   READS    The post's sets are read when a form first draws, after every
 *            write, when the window regains focus, and every few seconds
 *            while it is shown, so a second tab or device catches up.
 *   OWN WORDS Every set takes the person's own words (P5c, F1), saved as
 *            written when the box is left; a new version names the one it
 *            replaces. An agent's reading of them -- an interpretation -- is
 *            shown unconfirmed until the person confirms, changes or
 *            declines it; confirming a field value names the field's
 *            answers the person saw (`replaces`), as the server requires.
 *
 * A form that cannot save -- no name=, a name another block also says, the
 * server refusing it -- says why and keeps today's tab-only behaviour.
 *
 * Nothing here decides what a value means: the block's fill rules
 * (spec/fill.ts) and the server's response model do.
 * ------------------------------------------------------------------------ */
import { useEffect, useSyncExternalStore } from 'react'
import type { Val } from './spec/form'

const API = '/fluid/api/response-sets'
const HEADERS = { 'X-Mentis-Client': '1', 'Content-Type': 'application/json' }
/** How often a form on screen rereads its post's answers. */
export const REREAD_MS = 5000

/** One answer as the server reads it (`responses._row`). */
export interface Head {
  answer: string
  field: string
  value: Val
  by: string
  by_alias: string | null
  at: number
  version?: string
  earlier_version?: boolean
  check?: { checked: boolean; problems?: string[] } | null
}

/** One version of somebody's own words (`responses._words_row`). */
export interface Words { words: string; text: string; replaces: string[]; by: string; by_alias: string | null; at: number }

/** What an interpretation proposes (`responses._proposal`). */
export type Proposes =
  | { type: 'set-field'; field: string; value: Val }
  | { type: 'add-row'; row: Record<string, string> }
  | { type: 'add-field'; field: { id: string; kind: string; label?: string } }

/** One interpretation as it stands (`responses.interpretation_view`). */
export interface Proposal {
  interpretation: string
  by: string
  by_alias: string | null
  at: number
  words: string
  for: string | null
  passage: { start: number; end: number; unit: 'codepoint' }
  excerpt: string
  proposes: Proposes
  status: 'pending' | 'confirmed' | 'changed' | 'declined'
  state: 'pending' | 'out of date' | 'confirmed' | 'changed' | 'declined'
  out_of_date: boolean | null
  why_out_of_date: string | null
  reply: { reply: string; by: string; at: number; answer: string | null; changed_to: Proposes | null; reason: string | null } | null
}

/** One set as it stands (`responses.state`), plus what the list adds. */
export interface SetState {
  set: string
  post: string
  part: number
  block: string
  mode: string
  started_from?: string | null
  fields: Record<string, { value: Val | null; answer: string | null; heads: Head[]; conflict: boolean }>
  conflicts: string[]
  answers: number
  ready: boolean
  changed_since_ready: boolean
  marked_ready: { entry: string; by: string; at: number; answers: string[] } | null
  source_deleted: { record: string; at: number; by: string } | null
  version?: string
  awaited?: boolean
  own_words?: Words[]
  proposals?: Proposal[]
  pending?: number
}

/** The accounting of one person's words (`responses.accounting`). */
export interface Accounting { words: (Words & { not_cited: { start: number; end: number; excerpt: string }[] })[] }

interface PostRead { post: string; you: string | null; author: string | null; author_alias: string | null; sets: SetState[] }

/** A write the server has not confirmed: its key, kept for a retry. */
interface Pending { op: string; value: Val; replaces: string[]; error?: string; refused?: boolean }

export interface Entry {
  post: string
  part: number
  block: string
  /** read: the post's sets have been read at least once */
  read: boolean
  /** why this block's answers cannot be saved; then it is tab-only */
  cannot?: string
  /** why the last read failed (kept answers are still shown) */
  readError?: string
  set?: SetState
  you: string | null
  author: string | null
  authorAlias: string | null
  /** typed in this tab, not saved yet */
  drafts: Record<string, Val>
  /** sent and not yet confirmed */
  saving: Record<string, Pending>
  /** sent and failed: kept, with its key, to try again */
  failed: Record<string, Pending>
  /** the last Done or Send back said this */
  said?: { ok: boolean; text: string }
  busy?: 'ready' | 'send-back' | 'move'
  /** a move that needs confirming first */
  movePlan?: { field: string; matches: boolean }[]
  /** the op key of a Done/Send back/move/reply being tried, kept for its retry */
  ops: Record<string, string>
  /** own words typed here and not saved yet; their save in flight; a save that failed */
  wordsDraft?: string
  wordsSaving?: { op: string; text: string; replaces: string[] }
  wordsFailed?: { op: string; text: string; replaces: string[]; error: string }
  /** an interpretation being replied to, and what the last reply to one said when it was refused */
  replying?: string
  replyError?: Record<string, string>
}

/* -------------------------------------------------------------- the store */

const entries = new Map<string, Entry>()
const listeners = new Set<() => void>()
let v = 0
const tell = () => { v++; listeners.forEach((f) => f()) }
const subscribe = (f: () => void) => { listeners.add(f); return () => { listeners.delete(f) } }

/** A posted named fillable block's key, read back into what it names; null otherwise. */
export function durableAddress(key: string): { post: string; part: number; block: string; type: string } | null {
  const m = /^Turn (\S+?)(?: part (\d+))?\/@(.+):(form|checklist|table|pad)$/.exec(key)
  if (!m) return null
  return { post: m[1], part: m[2] ? Number(m[2]) : 0, block: m[3], type: m[4] }
}

/** Whether a block's key is under a posted Turn (so it would be saved if it could). */
export const isPosted = (where: string) => /^Turn \S+/.test(where)

export const newOp = () => 'ui-' + (globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`)

/** The entry for a durable key, made on first use. */
export function entryOf(key: string): Entry | null {
  const hit = entries.get(key)
  if (hit) return hit
  const at = durableAddress(key)
  if (!at) return null
  const e: Entry = { post: at.post, part: at.part, block: at.block, read: false, you: null, author: null, authorAlias: null, drafts: {}, saving: {}, failed: {}, ops: {} }
  entries.set(key, e)
  return e
}

/** Is this key's block saved by Mentis (as far as is known now)? */
export const isDurable = (key: string) => { const e = entryOf(key); return !!e && !e.cannot }

/* -------------------------------------------------------------- talking */

interface Got<T> { status: number; body: T & { error?: string; refused?: boolean } }

async function call<T>(path: string, body?: unknown): Promise<Got<T>> {
  const res = await fetch(path, body === undefined ? { headers: HEADERS } : { method: 'POST', headers: HEADERS, body: JSON.stringify(body) })
  const text = await res.text()
  let parsed: unknown = {}
  try { parsed = text ? JSON.parse(text) : {} } catch { parsed = { error: `${res.status}: ${text.slice(0, 200)}` } }
  return { status: res.status, body: parsed as Got<T>['body'] }
}

/** Is this a refusal (the server said no, with its reasons) rather than a failure to reach it? */
const refusedStatus = (s: number) => s === 400 || s === 403 || s === 404 || s === 405 || s === 409 || s === 422

const inFlight = new Map<string, Promise<void>>()

/** Read one post's sets into every entry of that post. */
export function readPost(post: string): Promise<void> {
  const going = inFlight.get(post)
  if (going) return going
  const p = (async () => {
    try {
      const got = await call<PostRead>(`${API}?post=${encodeURIComponent(post)}`)
      const mine = [...entries.values()].filter((e) => e.post === post)
      if (got.status !== 200) {
        for (const e of mine) { e.readError = got.body.error ?? `the answers could not be read (${got.status})`; e.read = true }
        return
      }
      for (const e of mine) {
        e.read = true
        e.readError = undefined
        e.you = got.body.you
        e.author = got.body.author
        e.authorAlias = got.body.author_alias
        e.set = got.body.sets.find((s) => s.part === e.part && s.block === e.block && s.mode === 'shared' && !s.started_from)
        /* A draft the server now holds is no longer a draft. */
        for (const [f, d] of Object.entries(e.drafts)) {
          const now = e.set?.fields[f]
          if (now && !now.conflict && JSON.stringify(now.value) === JSON.stringify(d)) delete e.drafts[f]
        }
      }
    } catch (err) {
      for (const e of entries.values()) if (e.post === post) { e.readError = `the answers could not be read: ${(err as Error).message}`; e.read = true }
    } finally {
      inFlight.delete(post)
      tell()
    }
  })()
  inFlight.set(post, p)
  return p
}

/** Open the block's set if it has none yet. Returns its id, or null (and `cannot` says why). */
async function setOf(e: Entry): Promise<string | null> {
  if (e.set) return e.set.set
  const op = (e.ops.open ??= newOp())
  const got = await call<{ set: string }>(API, { post: e.post, block: e.block, part: e.part, op })
  if (got.status === 200) {
    delete e.ops.open
    await readPost(e.post)
    /* readPost has set `e.set` (TypeScript cannot see it through the await). */
    return (e.set as SetState | undefined)?.set ?? got.body.set
  }
  if (refusedStatus(got.status)) {
    delete e.ops.open
    e.cannot = got.body.error ?? 'Mentis refused to keep answers for this form'
    tell()
    return null
  }
  throw new Error(got.body.error ?? `could not reach Mentis (${got.status})`)
}

/* -------------------------------------------------------------- writing */

/** The value a field shows: a draft, else the one saved answer, else the form's own. */
export function shownValue(e: Entry, field: string, init: Val): Val {
  if (field in e.drafts) return e.drafts[field]
  if (field in e.saving) return e.saving[field].value
  if (field in e.failed) return e.failed[field].value
  const f = e.set?.fields[field]
  if (f && !f.conflict && f.value !== null) return f.value as Val
  return init
}

/** What is saved for a field now (null when nothing, or a conflict). */
const savedValue = (e: Entry, field: string): Val | null => {
  const f = e.set?.fields[field]
  return f && !f.conflict ? (f.value as Val) : null
}

/** Keep what is typed, in the tab. Nothing is sent. */
export function draft(key: string, field: string, value: Val) {
  const e = entryOf(key)
  if (!e) return
  e.drafts[field] = value
  tell()
}

/** The field is finished: save its draft, if it differs from what is saved. */
export async function finish(key: string, field: string, init: Val): Promise<void> {
  const e = entryOf(key)
  if (!e || e.cannot || !(field in e.drafts)) return
  const value = e.drafts[field]
  const f = e.set?.fields[field]
  const saved = savedValue(e, field)
  /* Nothing to say: it reads as it already does (saved, or the form's own and never answered). */
  if (!f?.conflict && (saved !== null ? JSON.stringify(saved) === JSON.stringify(value) : JSON.stringify(value) === JSON.stringify(init))) {
    delete e.drafts[field]
    tell()
    return
  }
  delete e.drafts[field]
  /* A new answer takes the place of one that failed. */
  delete e.failed[field]
  const pending: Pending = { op: newOp(), value, replaces: (f?.heads ?? []).map((h) => h.answer) }
  return send(e, field, pending)
}

/** Try a failed save again, with the same operation key. */
export function retry(key: string, field: string) {
  const e = entryOf(key)
  const p = e?.failed[field]
  if (!e || !p) return
  delete e.failed[field]
  return send(e, field, { ...p, error: undefined, refused: undefined })
}

/** Drop a failed save, keeping what is saved. */
export function discard(key: string, field: string) {
  const e = entryOf(key)
  if (!e) return
  delete e.failed[field]
  delete e.drafts[field]
  tell()
}

async function send(e: Entry, field: string, p: Pending): Promise<void> {
  e.saving[field] = p
  /* What Done or Send back last said is about the answers before this one. */
  e.said = undefined
  tell()
  try {
    const sid = await setOf(e)
    if (!sid) { delete e.saving[field]; e.drafts[field] = p.value; tell(); return }
    const got = await call<{ answer: string }>(`${API}/${encodeURIComponent(sid)}/answers`, { field, value: p.value, replaces: p.replaces, op: p.op })
    delete e.saving[field]
    if (got.status !== 200) {
      e.failed[field] = { ...p, error: got.body.error ?? `not saved (${got.status})`, refused: refusedStatus(got.status) }
      /* The block itself cannot be saved (e.g. its name is now shared). */
      if (refusedStatus(got.status) && /cannot be saved|no block in this post/.test(got.body.error ?? '')) e.cannot = got.body.error
    }
    await readPost(e.post)
  } catch (err) {
    delete e.saving[field]
    e.failed[field] = { ...p, error: `not saved: ${(err as Error).message || 'Mentis could not be reached'}` }
    tell()
  }
}

/** Save every draft now (before Done). True when nothing is left unsaved. */
export async function flush(key: string, inits: Record<string, Val>): Promise<boolean> {
  const e = entryOf(key)
  if (!e) return false
  await Promise.all(Object.keys(e.drafts).map((f) => finish(key, f, inits[f])))
  return !Object.keys(e.drafts).length && !Object.keys(e.failed).length && !Object.keys(e.saving).length
}

/** The answers a person sees for one field now: the ids a confirmation names as replaced. */
export const headsOf = (e: Entry, field: string) => (e.set?.fields[field]?.heads ?? []).map((h) => h.answer)

/** The answer ids a person is looking at: every field's one current answer. */
const seenOf = (s: SetState) => Object.values(s.fields).flatMap((f) => (f.conflict ? [] : f.answer ? [f.answer] : []))

async function act(key: string, which: 'ready' | 'send-back', body: (s: SetState) => Record<string, unknown>,
  ok: (b: Record<string, unknown>, e: Entry) => string | null) {
  const e = entryOf(key)
  if (!e || e.busy) return
  e.busy = which
  e.said = undefined
  tell()
  try {
    const sid = await setOf(e)
    if (!sid || !e.set) { e.said = { ok: false, text: e.cannot ?? 'Nothing has been answered yet.' }; return }
    const op = (e.ops[which] ??= newOp())
    const got = await call<Record<string, unknown>>(`${API}/${encodeURIComponent(sid)}/${which}`, { ...body(e.set), op })
    if (got.status === 200) {
      delete e.ops[which]
      const text = ok(got.body, e)
      e.said = text === null ? undefined : { ok: true, text }
    } else {
      if (refusedStatus(got.status)) delete e.ops[which]
      e.said = { ok: false, text: got.body.error ?? `not done (${got.status})` }
    }
    await readPost(e.post)
  } catch (err) {
    e.said = { ok: false, text: `not done: ${(err as Error).message || 'Mentis could not be reached'}` }
  } finally {
    e.busy = undefined
    tell()
  }
}

/** Done: mark the answers ready, as they are on screen. What it then says
 *  is read back from the record (`statusOf`): "Ready", or "Ready, handed to"
 *  the agent whose work declared it waits for these answers. */
export const markReady = (key: string) => act(key, 'ready', (s) => ({ seen: seenOf(s) }), () => null)

/** Send back: hand the answers as they stand to the post's author, to act on now. */
export const sendBack = (key: string) => act(key, 'send-back', () => ({}),
  (_b, e) => `Sent back to ${e.authorAlias ?? 'the agent'}`)

/** Move the answers to the form's current version: at once when nothing changed shape, otherwise after a preview. */
export async function move(key: string, confirm = false) {
  const e = entryOf(key)
  if (!e?.set || e.busy) return
  e.busy = 'move'
  tell()
  try {
    const op = (e.ops[confirm ? 'move-confirm' : 'move'] ??= newOp())
    const got = await call<{ moved: boolean; plan: { field: string; matches: boolean }[] }>(`${API}/${encodeURIComponent(e.set.set)}/move`, { confirm, op })
    delete e.ops[confirm ? 'move-confirm' : 'move']
    if (got.status !== 200) e.said = { ok: false, text: got.body.error ?? `not moved (${got.status})` }
    else e.movePlan = got.body.moved ? undefined : got.body.plan
    await readPost(e.post)
  } catch (err) {
    e.said = { ok: false, text: `not moved: ${(err as Error).message}` }
  } finally {
    e.busy = undefined
    tell()
  }
}

/** Every answer ever given to each of these fields, oldest first. */
export async function historyOf(key: string, fields: string[]): Promise<Record<string, Head[]>> {
  const e = entryOf(key)
  if (!e?.set) return {}
  const out: Record<string, Head[]> = {}
  await Promise.all(fields.map(async (f) => {
    const got = await call<{ history: Head[] }>(`${API}/${encodeURIComponent(e.set!.set)}/history?field=${encodeURIComponent(f)}`)
    out[f] = got.status === 200 ? got.body.history : []
  }))
  return out
}

/* -------------------------------------------------------------- own words (P5c) */

/** The words of `you` that no later version of theirs replaces: what the box edits. */
export const mineOf = (e: Entry): Words | undefined => e.set?.own_words?.filter((w) => w.by === e.you).at(-1)

/** Keep what is typed in the own-words box, in the tab. Nothing is sent. */
export function draftWords(key: string, text: string) {
  const e = entryOf(key)
  if (!e) return
  e.wordsDraft = text
  tell()
}

/** The box is left: save the words as written, as a new version of the
 *  person's own, if they differ from what is saved. */
export async function finishWords(key: string): Promise<void> {
  const e = entryOf(key)
  if (!e || e.cannot || e.wordsDraft === undefined) return
  const text = e.wordsDraft
  const mine = mineOf(e)
  delete e.wordsDraft
  if (text === (mine?.text ?? '') || (!mine && !text.trim())) { tell(); return }
  if (!text.trim()) {
    /* Own words are kept, never emptied: an empty box keeps the last version. */
    e.wordsFailed = { op: newOp(), text, replaces: mine ? [mine.words] : [], error: 'Own words are never emptied: the last version is kept. Write something, or leave it as it was.' }
    tell()
    return
  }
  e.wordsFailed = undefined
  return sendWords(e, { op: newOp(), text, replaces: mine ? [mine.words] : [] })
}

/** Try a failed save of the own words again, with the same operation key. */
export function retryWords(key: string) {
  const e = entryOf(key)
  const p = e?.wordsFailed
  if (!e || !p || !p.text.trim()) return
  e.wordsFailed = undefined
  return sendWords(e, { op: p.op, text: p.text, replaces: p.replaces })
}

/** Drop own words that failed to save, keeping what is saved. */
export function discardWords(key: string) {
  const e = entryOf(key)
  if (!e) return
  e.wordsFailed = undefined
  delete e.wordsDraft
  tell()
}

async function sendWords(e: Entry, p: { op: string; text: string; replaces: string[] }) {
  e.wordsSaving = p
  e.said = undefined
  tell()
  try {
    const sid = await setOf(e)
    if (!sid) { e.wordsSaving = undefined; e.wordsDraft = p.text; tell(); return }
    const got = await call<{ words: string }>(`${API}/${encodeURIComponent(sid)}/own-words`, { text: p.text, replaces: p.replaces, op: p.op })
    e.wordsSaving = undefined
    if (got.status !== 200) e.wordsFailed = { ...p, error: got.body.error ?? `not saved (${got.status})` }
    await readPost(e.post)
  } catch (err) {
    e.wordsSaving = undefined
    e.wordsFailed = { ...p, error: `not saved: ${(err as Error).message || 'Mentis could not be reached'}` }
    tell()
  }
}

/** Every version of the own words in the set, oldest first. */
export async function wordsHistory(key: string): Promise<Words[]> {
  const e = entryOf(key)
  if (!e?.set) return []
  const got = await call<{ words: Words[] }>(`${API}/${encodeURIComponent(e.set.set)}/history?words=1`)
  return got.status === 200 ? got.body.words : []
}

/** What no interpretation has quoted yet, per person's words. */
export async function accountingOf(key: string): Promise<Accounting | null> {
  const e = entryOf(key)
  if (!e?.set) return null
  const got = await call<Accounting>(`${API}/${encodeURIComponent(e.set.set)}/accounting`)
  return got.status === 200 ? got.body : null
}

/** Confirm, change or decline an interpretation, as the person whose words
 *  it read. A field value confirmed or changed names the field's answers
 *  shown now (`replaces`); the server refuses it, writing nothing, when they
 *  are no longer what it holds, and the set is read again. */
export async function reply(key: string, p: Proposal, outcome: 'confirm' | 'change' | 'decline',
  extra: { value?: Val; changed_to?: Record<string, unknown>; reason?: string } = {}) {
  const e = entryOf(key)
  if (!e || e.replying) return
  e.replying = p.interpretation
  const errors = (e.replyError ??= {})
  delete errors[p.interpretation]
  tell()
  const opKey = `reply:${p.interpretation}:${outcome}`
  try {
    const body: Record<string, unknown> = { ...extra, op: (e.ops[opKey] ??= newOp()) }
    if (p.proposes.type === 'set-field' && outcome !== 'decline') body.replaces = headsOf(e, p.proposes.field)
    const got = await call<Record<string, unknown>>(`/fluid/api/interpretations/${encodeURIComponent(p.interpretation)}/${outcome}`, body)
    if (got.status === 200 || refusedStatus(got.status)) delete e.ops[opKey]
    if (got.status !== 200) errors[p.interpretation] = got.body.error ?? `not done (${got.status})`
    await readPost(e.post)
  } catch (err) {
    errors[p.interpretation] = `not done: ${(err as Error).message || 'Mentis could not be reached'}`
  } finally {
    e.replying = undefined
    tell()
  }
}

/* -------------------------------------------------------------- reading */

const mounted = new Map<string, number>()
let timer: ReturnType<typeof setInterval> | null = null
const rereadAll = () => { if (document.visibilityState === 'visible') for (const post of new Set([...mounted.keys()])) void readPost(post) }

function watch(post: string) {
  mounted.set(post, (mounted.get(post) ?? 0) + 1)
  if (!timer) {
    timer = setInterval(rereadAll, REREAD_MS)
    window.addEventListener('focus', rereadAll)
    document.addEventListener('visibilitychange', rereadAll)
    window.addEventListener('beforeunload', warnUnsaved)
  }
  return () => {
    const n = (mounted.get(post) ?? 1) - 1
    if (n > 0) mounted.set(post, n); else mounted.delete(post)
    if (!mounted.size && timer) {
      clearInterval(timer)
      timer = null
      window.removeEventListener('focus', rereadAll)
      document.removeEventListener('visibilitychange', rereadAll)
      window.removeEventListener('beforeunload', warnUnsaved)
    }
  }
}

/** Leaving with something typed and not saved asks first. */
function warnUnsaved(ev: BeforeUnloadEvent) {
  for (const e of entries.values()) {
    if (Object.keys(e.drafts).length || Object.keys(e.failed).length || Object.keys(e.saving).length
      || e.wordsDraft !== undefined || e.wordsFailed || e.wordsSaving) {
      ev.preventDefault()
      ev.returnValue = ''
      return
    }
  }
}

/** The entry for a posted named fillable block, kept up to date while it is drawn; null for any other block. */
export function useAnswers(key: string): Entry | null {
  useSyncExternalStore(subscribe, () => v)
  const e = entryOf(key)
  const post = e?.post
  useEffect(() => {
    if (!post) return
    const stop = watch(post)
    const hit = entries.get(key)
    if (hit && !hit.read) void readPost(post)
    return stop
  }, [key, post])
  return e
}

/** For tests and the readable text: the entry as it is, without subscribing. */
export const peek = (key: string) => entries.get(key) ?? null

/* -------------------------------------------------------------- saying it */

/** "just now", "5 min ago", or the date. */
export function ago(ts: number): string {
  const s = Date.now() / 1000 - ts
  if (s < 90) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return new Date(ts * 1000).toLocaleDateString()
}

export const aliasOf = (h: Head) => h.by_alias ?? h.by
/** The initial drawn beside a value somebody else set. */
export const initialOf = (h: Head) => (aliasOf(h).replace(/^@/, '')[0] ?? '?').toUpperCase()

/** The one quiet status line: what the answers are now. Empty when nothing is answered. */
export function statusOf(e: Entry): string {
  if (e.busy === 'ready') return 'Marking ready…'
  if (e.busy === 'send-back') return 'Sending back…'
  if (Object.keys(e.saving).length || e.wordsSaving) return 'Saving…'
  if (e.said?.ok) return e.said.text
  const s = e.set
  if (!s) return ''
  if (s.ready) return s.awaited ? `Ready, handed to ${e.authorAlias ?? 'the agent'}` : 'Ready'
  if (s.changed_since_ready) return 'Changed since ready'
  return s.answers || s.own_words?.length ? 'Saved' : ''
}

/** What the readable text says beyond the values: who set each, what disagrees, what is not saved. */
export interface Durable {
  status: string
  by: Record<string, string>
  conflicts: Record<string, { value: Val; by: string }[]>
  unsaved: string[]
  failed: string[]
  sourceDeleted: boolean
  /** every person's own words as they now read */
  words: { by: string; text: string }[]
  /** what has been read into them, and what became of it */
  proposals: { by: string; excerpt: string; proposes: Proposes; state: Proposal['state'] }[]
}

/** A posted block's values as Mentis holds them (with this tab's drafts), in
 *  the shape its readable text and handoff read (`values` by fill field id);
 *  undefined when the block is not saved by Mentis. */
export function durableState(key: string): { values: Record<string, Val>; durable: Durable } | undefined {
  const e = entries.get(key)
  if (!e || e.cannot) return undefined
  const values: Record<string, Val> = {}
  const by: Record<string, string> = {}
  const conflicts: Durable['conflicts'] = {}
  for (const [f, x] of Object.entries(e.set?.fields ?? {})) {
    if (x.conflict) conflicts[f] = x.heads.map((h) => ({ value: h.value, by: aliasOf(h) }))
    else if (x.value !== null) { values[f] = x.value as Val; by[f] = aliasOf(x.heads[0]) }
  }
  for (const src of [e.failed, e.saving]) for (const [f, p] of Object.entries(src)) values[f] = p.value
  Object.assign(values, e.drafts)
  return { values, durable: { status: statusOf(e), by, conflicts, unsaved: Object.keys(e.drafts),
    failed: Object.keys(e.failed), sourceDeleted: !!e.set?.source_deleted,
    words: (e.set?.own_words ?? []).map((w) => ({ by: w.by_alias ?? w.by, text: w.text })),
    proposals: (e.set?.proposals ?? []).map((x) => ({ by: x.by_alias ?? x.by, excerpt: x.excerpt, proposes: x.proposes, state: x.state })) } }
}
