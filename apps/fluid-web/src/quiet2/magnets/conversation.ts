/* The Magnet's own persistent Conversation, isolated from the main store.
 * Ordinary grounded questions use the request routing door and attach the exact
 * retained Admission to the asking Turn. Explicit notes use the posting door.
 * Creation is an owner action under the backend's stable Magnet key. No timers,
 * automatic retries or inferred completion. Refresh reads actual history/work.
 * Drafts and frozen uncertain requests persist under origin, proxy, corpus,
 * restore instance and stable Magnet id; another Brain never hydrates them. */

import { CLIENT_HEADERS } from '../../api'
import type { Conversation, Expectation, Turn } from '../../api'
import { BRAIN_HEADER, brainNow, page, refusedAsOtherBrain, type Binding } from '../../brainBinding'
import { guardReload } from '../reloadGuard'
import type { MagnetResource } from './contract'
import { agentsOf, groundedRequest, retainedCollection, type MiniAgent, type RetainedCollection } from './evidence'

/* -- what this seam can truthfully show ------------------------------------ */

const ENTRY = /^ent-[a-zA-Z0-9]{6,40}$/
const entryId = (v: unknown): v is string => typeof v === 'string' && ENTRY.test(v)
const object = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : null

export const NO_OWN_CONVERSATION = 'This Magnet has no Conversation of its own in its saved definition. '
  + 'Create its Conversation here, or collect first.'
export const OWN_IS_A_SOURCE = 'This Magnet’s saved Conversation is one of the sources it collects from, '
  + 'so it is not a Conversation of its own. Nothing here creates, repairs or substitutes one.'
export const UNREADABLE_DEFINITION = 'This Magnet’s saved definition could not be read, so its own Conversation is unavailable.'

/** Every Conversation named by a source, whatever kind of source names it. */
export function sourceConversations(config: unknown): string[] {
  const c = object(config)
  if (!c || !Array.isArray(c.sources)) return []
  const found: string[] = []
  for (const s of c.sources) {
    const source = object(s)
    if (!source) continue
    for (const v of Object.values(source)) if (entryId(v) && !found.includes(v)) found.push(v)
  }
  return found
}

/** THE MAGNET'S OWN CONVERSATION, or why there is none to show. It must be a
 *  saved entry reference and it must differ from EVERY source: a Magnet
 *  pointed at one of its own sources has no Conversation of its own, and
 *  showing the source there would be this card inventing one. */
export function ownConversation(resource: MagnetResource): { conversation: string } | { unavailable: string } {
  const config = object(resource.saved.config)
  if (!config) return { unavailable: UNREADABLE_DEFINITION }
  const own = config.conversation
  if (own == null || own === '') return { unavailable: NO_OWN_CONVERSATION }
  if (!entryId(own)) return { unavailable: NO_OWN_CONVERSATION }
  if (sourceConversations(config).includes(own)) return { unavailable: OWN_IS_A_SOURCE }
  return { conversation: own }
}

/* -- which Brain ----------------------------------------------------------- */

/** The corpus a space registry key names (`<origin>|<proxy>|<corpusId>`). */
export function corpusOfSpaceKey(key: string): string {
  const at = key.lastIndexOf('|')
  return at < 0 ? '' : key.slice(at + 1).trim()
}

/** The corpus a page binding names (`<corpus_id>@<instance>`). */
export function corpusOfBoundBrain(bound: string): string {
  const at = bound.lastIndexOf('@')
  return at <= 0 ? '' : bound.slice(0, at).trim()
}

export const UNCONFIRMED_BRAIN = 'Nothing was sent: this page could not confirm which Brain the server serves.'
export const OTHER_BRAIN = 'Nothing was sent: this page is open on a Magnet of another Brain than the server now serves. '
  + 'Reload for the Brain it serves; your words are kept here.'

export type BrainCheck = { ok: true; brain: string } | { ok: false; why: string }

/** WHICH BRAIN A WRITE FROM THIS CARD NAMES, asked for now. The page's whole
 *  binding -- corpus and instance -- is what the write carries, and the
 *  resource's own corpus must be that binding's corpus: two keys in different
 *  shapes are compared on what they both say, never as strings. */
export async function confirmedBrain(
  resource: MagnetResource,
  binding: Binding = page,
  now: (b: Binding) => Promise<string | null> = (b) => brainNow(b),
): Promise<BrainCheck> {
  const bound = await now(binding)
  if (bound === null) return { ok: false, why: UNCONFIRMED_BRAIN }
  const mine = corpusOfSpaceKey(resource.brainKey)
  const serving = corpusOfBoundBrain(bound)
  if (!mine || !serving || mine !== serving) return { ok: false, why: OTHER_BRAIN }
  return { ok: true, brain: bound }
}

/* -- the isolated Magnet composer ----------------------------------------- */

/** HOW AN ATTEMPT ENDED, as far as this card can truthfully say.
 *  `in-flight` and `uncertain` and `malformed` are all UNRESOLVED: the post
 *  may be recorded, so the key must be reused. `refused` is resolved -- the
 *  server answered and recorded nothing -- and the key is kept only so a
 *  deliberate retry of the same words is still at most one post. */
export type AttemptState = 'in-flight' | 'uncertain' | 'malformed' | 'refused'

export const UNRESOLVED: ReadonlySet<AttemptState> = new Set<AttemptState>(['in-flight', 'uncertain', 'malformed'])

/** ONE SEND ATTEMPT AND WHAT IT CARRIED. The key and the identity are one
 *  thing: the key may only ever be reused for exactly this post. */
export interface MiniAttempt {
  /** the operation key this attempt went out under */
  op: string
  /** the words sent, trimmed, exactly as the body carried them */
  text: string
  /** the post it answered, or null for the Conversation itself */
  replyTo: string | null
  /** the owner it was written as, as the server named them */
  author: string
  /** the whole page binding the write carried */
  brain: string
  state: AttemptState
  /** what the owner is told about it, restored when the card comes back */
  why: string
  /** Frozen request: an uncertain retry must use the same evidence, recipient
   * and operation, even after a newer collection has been retained. */
  request?: { path: string; body: Record<string, unknown> }
}

/** The post an explicit Reply is aimed at, kept with the words it belongs to. */
export interface MiniTarget { id: string; number: number | null; alias: string }

/** EVERYTHING ONE MAGNET'S COMPOSER HOLDS BETWEEN MOUNTS. The card is
 *  remounted by collapse, by a tab change and by the parent; none of this is
 *  the card's to lose, and none of it is written anywhere but here. */
interface Held { text: string; target: MiniTarget | null; attempt: MiniAttempt | null; revision: number }

const held = new Map<string, Held>()
const bindings = new WeakMap<MagnetResource, Binding>()
const composers = new Map<string, Set<() => void>>()
let draftRevision = 0
const notifyComposer = (key: string) => composers.get(key)?.forEach((fn) => fn())
let unguard: (() => void) | null = null

/** One held composer per Magnet resource: the same card collapsed, re-tabbed
 *  or remounted finds its own words, its own reply target and its own
 *  unresolved attempt, and another Magnet never sees them. */
export const miniDraftKey = (resource: MagnetResource): string => {
  const b = bindings.get(resource) ?? page
  return `${resource.brainKey}::${b.bound() ?? 'unbound'}::${resource.saved.id}`
}

const storageKey = (key: string) => `mentis-mini-v2:${key}`
const persistent = (key: string) => !key.includes('::unbound::')
const holdOf = (key: string): Held => {
  const memory = held.get(key)
  if (memory) return memory
  try {
    const raw = persistent(key) ? globalThis.localStorage?.getItem(storageKey(key)) : null
    const h = raw ? JSON.parse(raw) as Held : null
    if (h && typeof h.text === 'string' && Number.isSafeInteger(h.revision)
      && (!h.target || entryId(h.target.id))
      && (!h.attempt || (typeof h.attempt.op === 'string' && typeof h.attempt.text === 'string'
        && typeof h.attempt.author === 'string' && typeof h.attempt.brain === 'string'
        && ['in-flight', 'uncertain', 'malformed', 'refused'].includes(h.attempt.state)))) {
      held.set(key, h)
      draftRevision = Math.max(draftRevision, h.revision)
      return h
    }
  } catch { /* Storage unavailable: the in-page composer still works. */ }
  return { text: '', target: null, attempt: null, revision: 0 }
}

/** Nothing typed, nothing aimed at, nothing unresolved: hold nothing. */
function put(key: string, h: Held): void {
  if (!h.text && !h.target && !h.attempt) held.delete(key)
  else held.set(key, h)
  try {
    if (persistent(key)) {
      if (!h.text && !h.target && !h.attempt) globalThis.localStorage?.removeItem(storageKey(key))
      else globalThis.localStorage?.setItem(storageKey(key), JSON.stringify(h))
    }
  } catch { /* The reload guard still protects an in-memory draft. */ }
  guard()
  notifyComposer(key)
}

export const miniDraft = (resource: MagnetResource): string => holdOf(miniDraftKey(resource)).text

/** The reply target this Magnet's composer is aimed at, across mounts. */
export const miniReplyTarget = (resource: MagnetResource): MiniTarget | null =>
  holdOf(miniDraftKey(resource)).target

/** THE ATTEMPT THIS MAGNET HAS NOT RESOLVED, or the last refused one. Read
 *  fresh at every press: a send still in flight from an earlier mount writes
 *  its outcome here when it lands. */
export const miniAttempt = (resource: MagnetResource): MiniAttempt | null =>
  holdOf(miniDraftKey(resource)).attempt

/** Anything typed into any mini composer and not yet sent. */
export const anyMiniDraft = (): boolean => [...held.values()].some((h) => h.text.trim() !== '')

/** WHAT CLOSE PROTECTION ASKS. True: this Magnet holds words that closing it
 *  would lose. The parent asks this before it closes a card or discards one. */
export const hasMiniDraft = (resource: MagnetResource): boolean => miniDraft(resource).trim() !== ''

function guard() {
  if (typeof window === 'undefined') return
  if (anyMiniDraft() && !unguard) unguard = guardReload(anyMiniDraft)
  else if (!anyMiniDraft() && unguard) { unguard(); unguard = null }
}

export function setMiniDraft(resource: MagnetResource, text: string): void {
  const key = miniDraftKey(resource)
  const h = holdOf(key)
  put(key, { ...h, text, revision: h.text === text ? h.revision : ++draftRevision })
}

export function setMiniReplyTarget(resource: MagnetResource, target: MiniTarget | null): void {
  const key = miniDraftKey(resource)
  const h = holdOf(key)
  put(key, { ...h, target, revision: h.target?.id === target?.id ? h.revision : ++draftRevision })
}

/** Written as the attempt goes out and again as it lands, WHETHER OR NOT the
 *  card that sent it is still mounted: an unmounted in-flight send still
 *  resolves its own key, so a remount cannot mint a second one for it. */
export function setMiniAttempt(resource: MagnetResource, attempt: MiniAttempt): void {
  const key = miniDraftKey(resource)
  put(key, { ...holdOf(key), attempt })
}

/** THE OUTCOME IS KNOWN, so the key is let go: a post the answer named, a
 *  Brain that refused it outright, or a post the owner has changed away from. */
export function clearMiniAttempt(resource: MagnetResource): void {
  const key = miniDraftKey(resource)
  put(key, { ...holdOf(key), attempt: null })
}

/** The owner's own explicit discard, and what a RECORDED post leaves behind:
 *  the words, the reply target and the attempt go together, because none of
 *  them means anything without the others. */
export function discardMiniDraft(resource: MagnetResource): void {
  const key = miniDraftKey(resource)
  put(key, { text: '', target: null, attempt: null, revision: ++draftRevision })
}

/** Only for a check: a page with nothing typed anywhere. */
export function forgetMiniDrafts(): void {
  held.clear()
  composers.forEach((_, key) => notifyComposer(key))
  if (unguard) { unguard(); unguard = null }
}

/** WHETHER AN ATTEMPT'S KEY STILL COVERS WHAT THE COMPOSER NOW HOLDS. Words
 *  and reply target only: those are what the owner changes. The owner and the
 *  Brain are checked at the press, where they are known. */
export const attemptCovers = (a: MiniAttempt | null, text: string, replyTo: string | null): boolean =>
  !!a && a.text === text && a.replyTo === replyTo

/* -- what a post reads as here --------------------------------------------- */

/** How the record stands on one request recorded on a post. Nothing is
 *  inferred from the shape of the ask: each state is a field the read states,
 *  and a reply existing is a CLAIM, not an answer. */
export type WorkState = 'withdrawn' | 'lapsed' | 'answered' | 'claimed' | 'open'

export interface MiniWork {
  expectation: string
  expects: string
  state: WorkState
  /** who carries it, or null BECAUSE NOBODY DOES */
  ofAlias: string | null
  unassigned: boolean
  byAlias: string
  liveExecution: boolean
}

export interface MiniPost {
  id: string
  number: number | null
  authorAlias: string
  /** written by a run (`<runtime>/<run>`), which a person's post is not */
  agent: boolean
  at: number
  text: string
  replyTo: string | null
  replyNumber: number | null
  root: string | null
  replies: number
  work: MiniWork[]
  /** this post's line ends in a deletion record: its words are not shown here */
  deleted: boolean
}

const REFERENCE_PARTS = new Set(['topic', 'turn', 'conversation', 'acquired', 'object'])

/** The author's words as one plain string. It is drawn as TEXT and never as
 *  markup: nothing in this feature renders a post's words as HTML. */
export function textOfTurn(t: Turn): string {
  if (!Array.isArray(t.parts)) return ''
  return t.parts
    .filter((p) => p && (p.type === 'text' || REFERENCE_PARTS.has(p.type)))
    .map((p) => typeof p.text === 'string' ? p.text : '')
    .join('')
    .trim()
}

export function workOf(e: Expectation): MiniWork {
  const state: WorkState = e.withdrawn ? 'withdrawn'
    : e.lapsed ? 'lapsed'
    : e.answered_by ? 'answered'
    : e.satisfied_by?.length ? 'claimed'
    : 'open'
  return {
    expectation: e.id,
    expects: typeof e.expects === 'string' ? e.expects : '',
    state,
    ofAlias: e.of_alias ?? null,
    unassigned: !!e.unassigned || e.of === null,
    byAlias: e.by_alias ?? '',
    liveExecution: !!e.live_execution,
  }
}

export const WORK_WORDS: Record<WorkState, string> = {
  withdrawn: 'withdrawn',
  lapsed: 'closed without an answer',
  answered: 'answered',
  claimed: 'claimed answered',
  open: 'open',
}

export function adaptTurn(t: Turn): MiniPost {
  return {
    id: t.id,
    number: typeof t.number === 'number' ? t.number : null,
    authorAlias: typeof t.author_alias === 'string' && t.author_alias ? t.author_alias : t.author,
    agent: !!t.written_by && t.written_by.includes('/'),
    at: typeof t.at === 'number' ? t.at : 0,
    text: t.deleted ? '' : textOfTurn(t),
    replyTo: t.answering ?? null,
    replyNumber: t.answering_number ?? null,
    root: t.root ?? null,
    replies: typeof t.thread_replies === 'number' ? t.thread_replies : (t.replies?.length ?? 0),
    work: Array.isArray(t.expectations) ? t.expectations.map(workOf) : [],
    deleted: !!t.deleted,
  }
}

/* -- the HTTP seam --------------------------------------------------------- */

export interface MiniAnswer { status: number; body: unknown }
export type MiniGet = (path: string, signal?: AbortSignal) => Promise<MiniAnswer>
export type MiniSend = (path: string, body: unknown, headers: Record<string, string>) => Promise<MiniAnswer>

export const liveGet: MiniGet = async (path, signal) => {
  const r = await fetch(path, { headers: { ...CLIENT_HEADERS }, cache: 'no-store', ...(signal ? { signal } : {}) })
  return { status: r.status, body: await r.json().catch(() => null) }
}

export const livePost: MiniSend = async (path, body, headers) => {
  const r = await fetch(path, {
    method: 'POST',
    headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  })
  return { status: r.status, body: await r.json().catch(() => null) }
}

export const POSTS_PATH = '/fluid/api/posts'
export const PARTICIPANTS_PATH = '/fluid/api/participants?limit=1'
export const AGENTS_PATH = '/fluid/api/participants?limit=500&runtimes=1'
export const REQUESTS_PATH = '/fluid/api/requests'
export const collectionPath = (resource: MagnetResource) => `/fluid/api/magnets/${encodeURIComponent(resource.saved.id)}/collection`
export const PAGE_SIZE = 30

export const conversationPath = (c: string, before?: number): string =>
  `/api/conversations/${encodeURIComponent(c)}?batch=${PAGE_SIZE}${before != null ? `&before=${before}` : ''}`
export const threadPath = (c: string, root: string): string =>
  `/api/conversations/${encodeURIComponent(c)}/thread/${encodeURIComponent(root)}`

const errorOf = (body: unknown): string | null => {
  const b = object(body)
  return b && typeof b.error === 'string' ? b.error : null
}

/** A read the server refuses by name answers 200 with its reason (`real.ts`),
 *  so a refusal is an error here and never an empty Conversation. */
function conversationOf(got: MiniAnswer, conversation: string): Conversation {
  if (got.status !== 200) throw new Error(`This Conversation could not be read (${got.status}). Nothing was substituted.`)
  const said = errorOf(got.body)
  if (said) throw new Error(said)
  const body = object(got.body)
  if (!body || !Array.isArray(body.turns)) throw new Error('This Conversation’s read could not be understood.')
  if (body.id !== conversation) throw new Error('The answer was for another Conversation. Nothing was shown.')
  return body as unknown as Conversation
}

export interface MiniPage {
  name: string
  posts: MiniPost[]
  total: number | null
  /** threads older than this read, and the post number to read before them */
  older: number
  first: number | null
  /** the obligations this Conversation carries now, as the read states them */
  owed: number | null
}

export function pageOf(c: Conversation): MiniPage {
  const posts = c.turns.map(adaptTurn)
  const held = new Set(posts.map((p) => p.id))
  const top = posts.filter((p) => !p.replyTo || !(p.root && p.root !== p.id && held.has(p.root)))
  return {
    name: typeof c.name === 'string' ? c.name : '',
    posts: top.sort((a, b) => (a.number ?? 0) - (b.number ?? 0)),
    total: typeof c.turns_total === 'number' ? c.turns_total : null,
    older: c.batch?.older ?? 0,
    first: c.batch?.first ?? null,
    owed: Array.isArray(c.owed) ? c.owed.length : null,
  }
}

/* -- the store ------------------------------------------------------------- */

export interface MiniThread {
  root: string
  loading: boolean
  error?: string
  replies: MiniPost[]
}

export interface MiniSnapshot {
  /** why this Magnet has no Conversation of its own; set means nothing below applies */
  unavailable?: string
  conversation: string | null
  name: string
  loading: boolean
  error?: string
  posts: MiniPost[]
  total: number | null
  older: number
  first: number | null
  loadingEarlier: boolean
  earlierError?: string
  owed: number | null
  thread: MiniThread | null
  /** the post an explicit Reply is aimed at */
  replyTo: MiniTarget | null
  draft: string
  sending: boolean
  sendError?: string
  /** an attempt this Magnet has not resolved: it MAY have been recorded, so
   *  the words and its key are both still held and a retry reuses that key */
  uncertain: boolean
  /** the unresolved attempt's own key, for the owner and for a check */
  uncertainOp?: string
  sent?: { post: string; number: number | null; replayed: boolean }
  /** the page has moved to another Brain, or cannot say which it serves */
  identity?: string
  agents: MiniAgent[]
  agent: string
  collection: RetainedCollection | null
  contextLoading: boolean
  contextError?: string
  creating: boolean
  dispatchStatus?: string
}

export interface MiniConversation {
  conversation: string | null
  snapshot(): MiniSnapshot
  subscribe(fn: () => void): () => void
  read(): Promise<void>
  /** THE OWNER ASKING FOR WHAT HAS ARRIVED SINCE: this Conversation's latest
   *  page again, and the open thread with it. Nothing calls it on a timer. */
  refresh(): Promise<void>
  earlier(): Promise<void>
  openThread(root: string): Promise<void>
  closeThread(): void
  replyTo(post: MiniPost | null): void
  draft(text: string): void
  send(): Promise<void>
  ask(): Promise<void>
  prepare(): Promise<void>
  chooseAgent(id: string): void
  createOwn(): Promise<void>
  cancel(): void
  dispose(): void
}

export interface MiniAt {
  resource: MagnetResource
  canWrite: boolean
  get?: MiniGet
  post?: MiniSend
  binding?: Binding
  now?: (b: Binding) => Promise<string | null>
  op?: () => string
}

export const CANNOT_WRITE = 'Sending is unavailable for this Magnet here.'
export const NO_OWNER = 'Nothing was sent: this record names no owner, and this card writes only as the owner. '
  + 'Your words are kept here.'
export const UNCERTAIN_SEND = 'Nothing came back from the server, so whether this was recorded is unknown. '
  + 'Read the Conversation before sending again — sending again reuses the same key, so it cannot record a second post.'
/** A SEND LEFT IN FLIGHT BY AN UNMOUNT, found again when the card comes back. */
export const IN_FLIGHT_SEND = 'A send from this card was still on its way when the card was put away, so whether it was recorded is unknown. '
  + 'Refresh the Conversation before sending again — sending again reuses the same key, so it cannot record a second post.'
/** 200 WITHOUT A POST IS NOT A RECORD. The door answered, but what it answered
 *  names nothing that was recorded, so nothing here may be called sent. */
export const MALFORMED_SEND = 'The server answered without naming a recorded post, so whether this was recorded is unknown. '
  + 'Refresh the Conversation before sending again — sending again reuses the same key, so it cannot record a second post.'
/** The same words under a key that went out as somebody else, or on another
 *  Brain. Reusing it would mean the door answering for a DIFFERENT post. */
export const OTHER_IDENTITY = 'Nothing was sent: the unresolved attempt with these words was made as another owner or on another Brain, '
  + 'so its key cannot answer for this one. Refresh the Conversation and see what is recorded before sending these words again.'
export const MOVED_SEND = 'Nothing was recorded: this server now serves another Brain than this card was opened on. '
  + 'Reload for the Brain it serves; your words are still here.'

const newOp = () => `mini-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`

/** ONE MAGNET'S MINI CONVERSATION. Its reads are abandonable, its state is its
 *  own; the shared composer survives the card. */
export function createMiniConversation(at: MiniAt): MiniConversation {
  const resource = at.resource
  const get = at.get ?? liveGet
  const sendTo = at.post ?? livePost
  const binding = at.binding ?? page
  // Resource keys omit the restore instance. Mini drafts never do.
  bindings.set(resource, binding)
  const now = at.now ?? ((b: Binding) => brainNow(b, undefined, true))
  const op = at.op ?? newOp
  const found = ownConversation(resource)
  const conversation = 'conversation' in found ? found.conversation : null

  /* AN UNRESOLVED ATTEMPT THE COMPOSER STILL HOLDS THE POST FOR. The owner is
     told "the same key" only where that is actually true: an attempt whose
     words or reply target are no longer what is in the composer cannot answer
     for what Send would now write. */
  const offered = (text: string, replyTo: string | null): MiniAttempt | null => {
    const a = miniAttempt(resource)
    return a && UNRESOLVED.has(a.state) && attemptCovers(a, text.trim(), replyTo) ? a : null
  }
  const saying = (a: MiniAttempt): Partial<MiniSnapshot> =>
    ({ uncertain: true, uncertainOp: a.op, sendError: a.state === 'in-flight' ? IN_FLIGHT_SEND : a.why })

  /* WHAT THIS MAGNET WAS ALREADY HOLDING. A remount is not a fresh composer:
     the words, the post they answer and an attempt whose outcome is unknown
     all come back, so the owner's retry is the same post under the same key
     and not a second one. */
  const resumedDraft = miniDraft(resource)
  const resumedTarget = miniReplyTarget(resource)
  const resumed = offered(resumedDraft, resumedTarget?.id ?? null)

  let current: MiniSnapshot = {
    ...('unavailable' in found ? { unavailable: found.unavailable } : {}),
    conversation, name: '', loading: false, posts: [], total: null, older: 0, first: null,
    loadingEarlier: false, owed: null, thread: null,
    replyTo: resumedTarget,
    draft: resumedDraft, sending: false,
    agents: [], agent: '', collection: null, contextLoading: false, creating: false,
    uncertain: !!resumed,
    ...(resumed ? saying(resumed) : {}),
  }
  const heard = new Set<() => void>()
  let disposed = false
  let generation = 0
  let threadRequest = 0
  /* A SEND'S OWN LIFETIME, counted apart from the reads': a send re-reads the
     Conversation when it lands, and that read must not make the send that
     asked for it look abandoned. Only cancel and disposal end a send. */
  let sends = 0
  let control: AbortController | null = null
  let reading: Promise<void> | null = null
  let preparation = 0

  const emit = (change: Partial<MiniSnapshot>) => {
    if (disposed) return
    current = { ...current, ...change }
    heard.forEach((fn) => fn())
  }
  /* Every mounted view of this resource follows the same held composer.
     A completion from a disposed store must update the new visible view too. */
  const composerKey = miniDraftKey(resource)
  const syncComposer = () => {
    const h = holdOf(composerKey)
    const a = offered(h.text, h.target?.id ?? null)
    emit({ draft: h.text, replyTo: h.target,
      ...(a ? saying(a) : { uncertain: false, uncertainOp: undefined, sendError: undefined }) })
  }
  const listeners = composers.get(composerKey) ?? new Set<() => void>()
  composers.set(composerKey, listeners)
  listeners.add(syncComposer)
  const mineStill = (mine: number, signal?: AbortSignal) => !disposed && generation === mine && !signal?.aborted
  const sendStill = (mine: number) => !disposed && sends === mine
  const said = (e: unknown) => e instanceof Error ? e.message : 'This Conversation could not be read.'

  /* HOW AN ATTEMPT ENDS, written where the next mount will read it and NOT
     gated on this card still being mounted -- but only while it is still the
     attempt this Magnet holds. A later press, or the owner moving on, may
     already have resolved or replaced it, and a late answer must not revive
     a key that no longer stands for anything. */
  const settle = (a: MiniAttempt, state: AttemptState, why: string): void => {
    if (miniAttempt(resource)?.op === a.op) setMiniAttempt(resource, { ...a, state, why })
  }
  const letGo = (a: MiniAttempt): void => {
    if (miniAttempt(resource)?.op === a.op) clearMiniAttempt(resource)
  }

  const cancel = () => {
    generation++
    sends++
    control?.abort()
    control = null
    reading = null
    emit({ loading: false, loadingEarlier: false })
  }

  const read = (): Promise<void> => {
    if (disposed || !conversation) return Promise.resolve()
    if (reading) return reading
    const mine = ++generation
    threadRequest++
    const abort = new AbortController()
    control = abort
    emit({ loading: true, error: undefined, loadingEarlier: false, earlierError: undefined,
      ...(current.thread ? { thread: { ...current.thread, loading: false } } : {}) })
    const run = async () => {
      try {
        const c = conversationOf(await get(conversationPath(conversation), abort.signal), conversation)
        if (!mineStill(mine, abort.signal)) return
        const got = pageOf(c)
        emit({ name: got.name, posts: got.posts, total: got.total, older: got.older, first: got.first, owed: got.owed, error: undefined })
      } catch (e) {
        if (!mineStill(mine, abort.signal)) return
        emit({ error: said(e) })
      } finally {
        if (!disposed && generation === mine) { control = null; reading = null; emit({ loading: false }) }
      }
    }
    reading = run()
    return reading
  }

  /** ONE PAGE OLDER, put ahead of what is shown. Never a wider read: the
   *  batch before the first post read, by its number, and nothing else. */
  const earlier = async (): Promise<void> => {
    if (disposed || !conversation) return
    const from = current.first
    if (current.loading || current.loadingEarlier || current.older <= 0 || from === null) return
    const mine = generation
    emit({ loadingEarlier: true, earlierError: undefined })
    try {
      const c = conversationOf(await get(conversationPath(conversation, from)), conversation)
      if (!mineStill(mine)) return
      const got = pageOf(c)
      const known = new Set(current.posts.map((p) => p.id))
      emit({ posts: [...got.posts.filter((p) => !known.has(p.id)), ...current.posts], older: got.older, first: got.first })
    } catch (e) {
      if (!mineStill(mine)) return
      emit({ earlierError: said(e) })
    } finally {
      if (!disposed && generation === mine) emit({ loadingEarlier: false })
    }
  }

  /** ONE THREAD, read whole by its root, as the server answers it. */
  const openThread = async (root: string): Promise<void> => {
    if (disposed || !conversation || !entryId(root)) return
    const mine = generation
    const request = ++threadRequest
    const threadStill = () => mineStill(mine) && threadRequest === request && current.thread?.root === root
    emit({ thread: { root, loading: true, replies: [] } })
    try {
      const got = await get(threadPath(conversation, root))
      if (!threadStill()) return
      if (got.status !== 200) throw new Error(`This thread could not be read (${got.status}). Nothing was substituted.`)
      const body = object(got.body)
      const refused = errorOf(got.body)
      if (refused) throw new Error(refused)
      if (!body || !Array.isArray(body.replies)) throw new Error('This thread’s read could not be understood.')
      const replies = (body.replies as Turn[]).map(adaptTurn).sort((a, b) => (a.number ?? 0) - (b.number ?? 0))
      if (!threadStill()) return
      emit({ thread: { root, loading: false, replies } })
    } catch (e) {
      if (!threadStill()) return
      emit({ thread: { root, loading: false, replies: [], error: said(e) } })
    }
  }

  /** THE OWNER THIS CARD WRITES AS, as the server names it. Null is a refusal
   *  and never `participants[0]`. */
  const owner = async (): Promise<string | null> => {
    const got = await get(PARTICIPANTS_PATH)
    if (got.status !== 200) return null
    const body = object(got.body)
    const me = body?.me
    return typeof me === 'string' && me.trim() ? me : null
  }

  const prepare = async (): Promise<void> => {
    if (disposed || current.unavailable === OWN_IS_A_SOURCE) return
    const n = ++preparation
    const still = () => !disposed && n === preparation
    emit({ contextLoading: true, contextError: undefined })
    try {
      const brain = await confirmedBrain(resource, binding, now)
      if (!brain.ok) throw new Error(brain.why)
      const [batch, people] = await Promise.all([get(collectionPath(resource)), get(AGENTS_PATH)])
      const after = await confirmedBrain(resource, binding, now)
      if (!still()) return
      if (!after.ok || after.brain !== brain.brain) throw new Error(OTHER_BRAIN)
      if (batch.status !== 200 || errorOf(batch.body)) throw new Error(errorOf(batch.body) ?? `Collection unavailable (${batch.status}).`)
      const collection = retainedCollection(batch.body, resource.saved.id)
      const config = object(object(batch.body)?.config)
      if (!config) throw new Error(UNREADABLE_DEFINITION)
      // Never install a purported own Conversation that is a source.
      const own = config.conversation
      if (own && (!entryId(own) || sourceConversations(config).includes(own))) throw new Error(OWN_IS_A_SOURCE)
      if (people.status !== 200 || errorOf(people.body)) throw new Error('Agent participants could not be read.')
      const agents = agentsOf(people.body)
      const previous = current.agent || resource.snapshot().agentId || ''
      const preferred = agents.filter((a) => a.runtime === 'codex')
      // Undeclared recipients always need an explicit choice, even if only one
      // is listed. A runtime declaration may still supply a unique preference.
      const agent = agents.some((a) => a.id === previous) ? previous
        : preferred.length === 1 ? preferred[0].id
        : agents.length === 1 && agents[0].runtime ? agents[0].id : ''
      emit({ agents, agent, collection })
      const changedOwn = resource.saved.config?.conversation !== config.conversation
      resource.saved.config = config as unknown as NonNullable<typeof resource.saved.config>
      if (changedOwn) resource.update({})
    } catch (e) {
      if (still()) emit({ collection: null, contextError: said(e) })
    } finally {
      if (still()) emit({ contextLoading: false })
    }
  }

  const createOwn = async (): Promise<void> => {
    if (disposed || current.creating || conversation || current.unavailable !== NO_OWN_CONVERSATION) return
    if (!at.canWrite) { emit({ sendError: CANNOT_WRITE }); return }
    emit({ creating: true, sendError: undefined })
    try {
      const brain = await confirmedBrain(resource, binding, now)
      if (!brain.ok) throw new Error(brain.why)
      const author = await owner()
      if (!author) throw new Error(NO_OWNER)
      const answer = await sendTo(`/fluid/api/magnets/${encodeURIComponent(resource.saved.id)}/conversation`,
        { author, op: `magnet-conversation:${resource.saved.id}` }, { [BRAIN_HEADER]: brain.brain })
      if (refusedAsOtherBrain(answer.status, answer.body)) { binding.move(); throw new Error(MOVED_SEND) }
      const own = object(answer.body)?.conversation
      if (answer.status < 200 || answer.status >= 300 || errorOf(answer.body) || !entryId(own)
        || sourceConversations(resource.saved.config).includes(own)) {
        throw new Error(errorOf(answer.body) ?? 'The server did not confirm an own Conversation. Retry Create under the same stable key.')
      }
      resource.saved.config = { ...resource.saved.config!, conversation: own }
      resource.update({})
    } catch (e) {
      emit({ sendError: said(e) })
    } finally { emit({ creating: false }) }
  }

  const send = async (ask = false): Promise<void> => {
    if (disposed || !conversation || current.sending) return
    if (!at.canWrite) { emit({ sendError: CANNOT_WRITE }); return }
    const text = current.draft.trim()
    if (!text) { emit({ sendError: 'Write something to send.' }); return }
    const replyTo = current.replyTo?.id ?? null
    const revision = holdOf(composerKey).revision
    const mine = ++sends
    emit({ sending: true, sendError: undefined, sent: undefined })
    try {
      const brain = await confirmedBrain(resource, binding, now)
      if (!sendStill(mine)) return
      if (!brain.ok) { emit({ sendError: brain.why, identity: brain.why }); return }
      const me = await owner()
      if (!sendStill(mine)) return
      if (!me) { emit({ sendError: NO_OWNER }); return }
      /* A previous mount can resolve this post while preflight is waiting.
         Do not resurrect the retired intent under a freshly minted key. */
      if (holdOf(composerKey).revision !== revision) return
      /* THE SAME POST AFTER AN UNRESOLVED SEND GOES UNDER THE SAME KEY, read
         from what this Magnet holds and not from this mount: the attempt may
         have been made by an earlier mount, or be in flight from one still.
         Anything else -- different words, a different reply target -- is a
         different post and gets a new key.
         The identity is checked whole. The same words under a key that went
         out as another owner or on another Brain would have the door answer
         for a post that is not this one, so that is refused outright rather
         than resolved by guessing which of the two the owner meant. */
      const open = miniAttempt(resource)
      const covered = attemptCovers(open, text, replyTo)
      if (covered && (open!.author !== me || open!.brain !== brain.brain)) {
        emit({ uncertain: true, uncertainOp: open!.op, sendError: OTHER_IDENTITY })
        return
      }
      const key = covered ? open!.op : op()
      if (covered && !!open!.request !== ask) {
        emit({ sendError: 'This unresolved send used the other mode. Resolve it in that mode or edit the question before starting a different send.' })
        return
      }
      let request = covered ? open!.request : undefined
      if (ask && !request) {
        // Fresh collection and participants from the real API at the press.
        await prepare()
        if (!sendStill(mine) || holdOf(composerKey).revision !== revision) return
        const agent = current.agents.find((a) => a.id === current.agent)
        if (!current.collection) { emit({ sendError: current.contextError ?? 'Collect information first, then ask about the retained collection.' }); return }
        if (!agent) { emit({ sendError: 'Choose an agent participant before asking.' }); return }
        request = { path: REQUESTS_PATH, body: groundedRequest(resource.saved.id, me, text, replyTo, key, agent, current.collection) }
      }
      const attempt: MiniAttempt = {
        op: key, text, replyTo, author: me, brain: brain.brain, state: 'in-flight', why: IN_FLIGHT_SEND,
        ...(request ? { request } : {}),
      }
      /* RECORDED BEFORE IT GOES, and updated when it lands whether or not this
         card is still mounted: an unmount mid-flight must not leave a key that
         nothing knows was used. */
      setMiniAttempt(resource, attempt)
      const body = request?.body ?? {
        conversation,
        author: me,
        text,
        action: 'record-only',
        op: key,
        ...(replyTo ? { replies_to: replyTo } : {}),
      }
      let answer: MiniAnswer
      try {
        answer = await sendTo(request?.path ?? POSTS_PATH, body, { [BRAIN_HEADER]: brain.brain })
      } catch {
        /* NOTHING CAME BACK. The post may be recorded: the words and the key
           are both kept, and nothing is sent again by itself. */
        settle(attempt, 'uncertain', UNCERTAIN_SEND)
        if (!sendStill(mine)) return
        emit({ uncertain: true, uncertainOp: key, sendError: UNCERTAIN_SEND })
        return
      }
      if (refusedAsOtherBrain(answer.status, answer.body)) {
        /* THIS BRAIN NEVER SAW IT: the write was refused on its binding, so
           the outcome is known and the key is let go with it. */
        letGo(attempt)
        binding.move()
        if (!sendStill(mine)) return
        emit({ uncertain: false, uncertainOp: undefined, sendError: errorOf(answer.body) ?? MOVED_SEND, identity: MOVED_SEND })
        return
      }
      const refusal = errorOf(answer.body)
      if (answer.status !== 200 || refusal) {
        /* ANSWERED AND REFUSED: nothing was recorded, and the key stays with
           these words so a deliberate retry is still the same one post. */
        const why = refusal ?? `This post was not recorded (${answer.status}).`
        settle(attempt, 'refused', why)
        if (!sendStill(mine)) return
        emit({ uncertain: false, uncertainOp: undefined, sendError: why })
        return
      }
      /* A RECORDED POST IS ONE THE ANSWER NAMES. 200 with no `post`, or with
         something that is not an entry reference, says nothing about what was
         recorded: it fails closed exactly as an answer that never came, and
         the words and the key stay until the record itself is read. */
      const out = object(answer.body)
      const named = out?.post
      const posted = entryId(named) ? named : null
      if (!posted) {
        settle(attempt, 'malformed', MALFORMED_SEND)
        if (!sendStill(mine)) return
        emit({ uncertain: true, uncertainOp: key, sendError: MALFORMED_SEND, sent: undefined })
        await read()
        return
      }
      /* Settle the held attempt and the matching draft atomically. Text alone
         cannot identify intent: retargeting or editing away and back creates
         a newer revision, including when it happens in another mount. */
      const h = holdOf(composerKey)
      if (h.attempt?.op === attempt.op) {
        const sameIntent = h.revision === revision && h.text.trim() === text
          && (h.target?.id ?? null) === replyTo
        put(composerKey, sameIntent
          ? { text: '', target: null, attempt: null, revision: ++draftRevision }
          : { ...h, attempt: null })
      }
      if (!sendStill(mine)) return
      emit({
        uncertain: false, uncertainOp: undefined,
        sent: { post: posted, number: typeof out?.number === 'number' ? out.number : null, replayed: !!out?.replayed },
        ...(ask ? { dispatchStatus: 'Request recorded for the selected agent. Refresh to read its actual work status and any reply.' } : {}),
      })
      await read()
      if (sendStill(mine) && current.thread && replyTo) await openThread(current.thread.root)
    } finally {
      if (sendStill(mine)) emit({ sending: false })
    }
  }

  /** THE OWNER ASKING WHAT HAS ARRIVED. The latest page again, and the thread
   *  that is open with it, so replies and Work recorded since the card was
   *  mounted are read without collapsing and reopening it. Nothing calls this
   *  but a press: there is no timer and nothing polls. */
  const refresh = async (): Promise<void> => {
    if (disposed || !conversation) return
    const open = current.thread?.root ?? null
    const pending = read()
    const request = threadRequest
    await pending
    if (disposed) return
    if (open && threadRequest === request && current.thread?.root === open) await openThread(open)
  }

  /* WHAT THE OWNER CHANGING THE POST DOES TO THE KEY. Different words or a
     different reply target are a different post: the attempt's key does not
     cover them, saying its outcome would be about words that were never sent,
     and the key is let go with the post it belonged to.
     EXCEPT ONE THAT IS ALREADY ON ITS WAY. Typing does not recall a request
     the server may already have recorded, so an in-flight attempt is held
     until it settles however the composer changes under it -- it simply stops
     being what the next Send would write, and stops being offered as such. */
  const changed = (text: string, replyTo: string | null): Partial<MiniSnapshot> => {
    const a = miniAttempt(resource)
    const covers = attemptCovers(a, text.trim(), replyTo)
    if (!covers && a && a.state !== 'in-flight') clearMiniAttempt(resource)
    const still = covers && a && UNRESOLVED.has(a.state) ? a : null
    if (!!still === current.uncertain) return {}
    return still ? saying(still) : { uncertain: false, uncertainOp: undefined, sendError: undefined }
  }

  return {
    conversation,
    snapshot: () => current,
    subscribe(fn) { if (!disposed) heard.add(fn); return () => { heard.delete(fn) } },
    read,
    refresh,
    earlier,
    openThread,
    closeThread() { threadRequest++; emit({ thread: null }) },
    replyTo(post) {
      const target: MiniTarget | null = post ? { id: post.id, number: post.number, alias: post.authorAlias } : null
      /* THE REPLY TARGET IS THE MAGNET'S, NOT THE MOUNT'S: a card collapsed
         while it is aimed at a post comes back aimed at the same post. */
      setMiniReplyTarget(resource, target)
      emit({ replyTo: target, ...changed(current.draft, target?.id ?? null) })
    },
    draft(text) {
      setMiniDraft(resource, text)
      emit({ draft: text, ...changed(text, current.replyTo?.id ?? null) })
    },
    send: () => send(false),
    ask: () => send(true),
    prepare,
    createOwn,
    chooseAgent(id) { if (!current.sending) { const agent = current.agents.some((a) => a.id === id) ? id : ''; resource.update({ agentId: agent }); emit({ agent }) } },
    cancel,
    dispose() {
      if (disposed) return
      disposed = true
      listeners.delete(syncComposer)
      if (!listeners.size) composers.delete(composerKey)
      generation++
      sends++
      control?.abort()
      control = null
      reading = null
      /* WHAT THIS MAGNET HOLDS OUTLIVES THIS STORE ON PURPOSE: the card is
         remounted by collapse, by a tab change and by the parent, and the
         words, the post they answer and any attempt whose outcome is not yet
         known are the Magnet's until the owner sends or discards them. A send
         still in flight here writes its own outcome where the next mount
         reads it, so it cannot be resent under a second key. */
      heard.forEach((fn) => fn())
      heard.clear()
    },
  }
}
