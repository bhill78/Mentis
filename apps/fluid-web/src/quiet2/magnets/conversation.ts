/* THE MAGNET'S OWN CONVERSATION, READ AND WRITTEN AS ITSELF.
 *
 * A Magnet may have ONE Conversation of its own (`MagnetConfig.conversation`),
 * distinct from every source it collects from. This is the mini presentation's
 * HTTP and state seam for that Conversation, and nothing else:
 *
 *   - IT READS WHAT IS THERE. The Conversation's own latest page
 *     (`GET /api/conversations/<C>`), its earlier pages (`&before=`) and one
 *     thread at a time (`/thread/<root>`), through the API Quiet already uses
 *     and with `CLIENT_HEADERS`. Nothing is substituted for a read that fails:
 *     the refusal is said.
 *   - IT NEVER MAKES ONE. A Magnet with no own Conversation, or one whose
 *     saved Conversation is a source it collects from, is UNAVAILABLE here and
 *     says so. Creation, repair and activation belong to nothing in this file.
 *   - IT HAS NO PART IN THE MAIN STORE. Quiet's conversation flow
 *     (`quiet2/real.ts`) and its navigation are untouched: this holds its own
 *     posts, for this card, for as long as the card is mounted.
 *   - IT WRITES ONLY WHAT THE OWNER PRESSES SEND ON. One ordinary
 *     `record-only` post through the existing posting door
 *     (`POST /fluid/api/posts`), naming the Brain the page is bound to
 *     (`X-Mentis-Brain`) and the Participant the server itself names as the
 *     owner (`me` of the participants read). There is no fallback to
 *     `participants[0]`: a record with no owner is a refusal, not a guess.
 *     Nothing is dispatched, nothing is activated, nothing is created.
 *
 * WHICH BRAIN. A Magnet resource is keyed by the space registry's key
 * (`<origin>|<proxy>|<corpusId>`, space/registry.ts) and the page is bound by
 * `brainBinding` to `<corpus_id>@<instance>`. Those two strings are never
 * equal, so they are compared on the corpus they both name, and the write
 * carries the page's whole binding -- corpus AND instance -- which the server
 * checks (409 `BrainChanged`). A page that cannot say which Brain it is on
 * writes nothing at all.
 *
 * AN UNCERTAIN SEND IS NEVER RESENT BLINDLY. A send whose answer never
 * arrived may have been recorded. The draft, and the operation key it was sent
 * under, are both kept: the owner is told the outcome is unknown, and sending
 * again reuses that same key, which the posting door answers from what it
 * already recorded (`posting.post`, `op`) rather than writing a second post.
 *
 * NO UNSENT TEXT LEAVES THE PAGE. Drafts are held in this module for the
 * life of the page -- never in storage, never in the address, never in the
 * record -- so collapsing the card, changing tab or unmounting keeps them, and
 * leaving the page itself asks first (`reloadGuard.guardReload`). */

import { CLIENT_HEADERS } from '../../api'
import type { Conversation, Expectation, Turn } from '../../api'
import { BRAIN_HEADER, brainNow, page, refusedAsOtherBrain, type Binding } from '../../brainBinding'
import { guardReload } from '../reloadGuard'
import type { MagnetResource } from './contract'

/* -- what this seam can truthfully show ------------------------------------ */

const ENTRY = /^ent-[a-zA-Z0-9]{6,40}$/
const entryId = (v: unknown): v is string => typeof v === 'string' && ENTRY.test(v)
const object = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : null

export const NO_OWN_CONVERSATION = 'This Magnet has no Conversation of its own in its saved definition. '
  + 'Nothing here creates or repairs one.'
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

/* -- the drafts, held for the page and nowhere else ------------------------- */

const drafts = new Map<string, string>()
let unguard: (() => void) | null = null

/** One draft per Magnet resource: the same card collapsed, re-tabbed or
 *  remounted finds its own words, and another Magnet never sees them. */
export const miniDraftKey = (resource: MagnetResource): string => `${resource.brainKey}::${resource.id}`

export const miniDraft = (resource: MagnetResource): string => drafts.get(miniDraftKey(resource)) ?? ''

/** Anything typed into any mini composer and not yet sent. */
export const anyMiniDraft = (): boolean => [...drafts.values()].some((t) => t.trim() !== '')

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
  if (text) drafts.set(key, text)
  else drafts.delete(key)
  guard()
}

/** The owner's own explicit discard, and what a sent post leaves behind. */
export function discardMiniDraft(resource: MagnetResource): void {
  drafts.delete(miniDraftKey(resource))
  guard()
}

/** Only for a check: a page with nothing typed anywhere. */
export function forgetMiniDrafts(): void {
  drafts.clear()
  if (unguard) { unguard(); unguard = null }
}

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
  replyTo: { id: string; number: number | null; alias: string } | null
  draft: string
  sending: boolean
  sendError?: string
  /** the last send's answer never arrived: it MAY have been recorded */
  uncertain: boolean
  sent?: { post: string; number: number | null; replayed: boolean }
  /** the page has moved to another Brain, or cannot say which it serves */
  identity?: string
}

export interface MiniConversation {
  conversation: string | null
  snapshot(): MiniSnapshot
  subscribe(fn: () => void): () => void
  read(): Promise<void>
  earlier(): Promise<void>
  openThread(root: string): Promise<void>
  closeThread(): void
  replyTo(post: MiniPost | null): void
  draft(text: string): void
  send(): Promise<void>
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
export const MOVED_SEND = 'Nothing was recorded: this server now serves another Brain than this card was opened on. '
  + 'Reload for the Brain it serves; your words are still here.'

const newOp = () => `mini-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`

/** ONE MAGNET'S MINI CONVERSATION. Its reads are abandonable, its state is its
 *  own, and everything it holds dies with the card. */
export function createMiniConversation(at: MiniAt): MiniConversation {
  const get = at.get ?? liveGet
  const sendTo = at.post ?? livePost
  const binding = at.binding ?? page
  const now = at.now ?? ((b: Binding) => brainNow(b, undefined, true))
  const op = at.op ?? newOp
  const found = ownConversation(at.resource)
  const conversation = 'conversation' in found ? found.conversation : null

  let current: MiniSnapshot = {
    ...('unavailable' in found ? { unavailable: found.unavailable } : {}),
    conversation, name: '', loading: false, posts: [], total: null, older: 0, first: null,
    loadingEarlier: false, owed: null, thread: null, replyTo: null,
    draft: miniDraft(at.resource), sending: false, uncertain: false,
  }
  const heard = new Set<() => void>()
  let disposed = false
  let generation = 0
  /* A SEND'S OWN LIFETIME, counted apart from the reads': a send re-reads the
     Conversation when it lands, and that read must not make the send that
     asked for it look abandoned. Only cancel and disposal end a send. */
  let sends = 0
  let control: AbortController | null = null
  let reading: Promise<void> | null = null
  /* THE KEY THE LAST ATTEMPT WENT OUT UNDER, kept only while its outcome is
     unknown: sending again reuses it, so the door answers from what it already
     recorded rather than writing a second post. */
  let heldOp: { op: string; text: string; replyTo: string | null } | null = null

  const emit = (change: Partial<MiniSnapshot>) => {
    if (disposed) return
    current = { ...current, ...change }
    heard.forEach((fn) => fn())
  }
  const mineStill = (mine: number, signal?: AbortSignal) => !disposed && generation === mine && !signal?.aborted
  const sendStill = (mine: number) => !disposed && sends === mine
  const said = (e: unknown) => e instanceof Error ? e.message : 'This Conversation could not be read.'

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
    const abort = new AbortController()
    control = abort
    emit({ loading: true, error: undefined })
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
    if (current.loadingEarlier || current.older <= 0 || from === null) return
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
    emit({ thread: { root, loading: true, replies: [] } })
    try {
      const got = await get(threadPath(conversation, root))
      if (!mineStill(mine)) return
      if (got.status !== 200) throw new Error(`This thread could not be read (${got.status}). Nothing was substituted.`)
      const body = object(got.body)
      const refused = errorOf(got.body)
      if (refused) throw new Error(refused)
      if (!body || !Array.isArray(body.replies)) throw new Error('This thread’s read could not be understood.')
      const replies = (body.replies as Turn[]).map(adaptTurn).sort((a, b) => (a.number ?? 0) - (b.number ?? 0))
      if (current.thread?.root !== root) return
      emit({ thread: { root, loading: false, replies } })
    } catch (e) {
      if (!mineStill(mine) || current.thread?.root !== root) return
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

  const send = async (): Promise<void> => {
    if (disposed || !conversation || current.sending) return
    if (!at.canWrite) { emit({ sendError: CANNOT_WRITE }); return }
    const text = current.draft.trim()
    if (!text) { emit({ sendError: 'Write something to send.' }); return }
    const replyTo = current.replyTo?.id ?? null
    const mine = ++sends
    emit({ sending: true, sendError: undefined, sent: undefined })
    try {
      const brain = await confirmedBrain(at.resource, binding, now)
      if (!sendStill(mine)) return
      if (!brain.ok) { emit({ sendError: brain.why, identity: brain.why }); return }
      const me = await owner()
      if (!sendStill(mine)) return
      if (!me) { emit({ sendError: NO_OWNER }); return }
      /* THE SAME WORDS AFTER AN UNCERTAIN SEND GO UNDER THE SAME KEY. Anything
         else -- different words, a different reply target -- is a new post and
         gets a new one. */
      const same = heldOp && heldOp.text === text && heldOp.replyTo === replyTo
      const key = same ? heldOp!.op : op()
      heldOp = { op: key, text, replyTo }
      const body = {
        conversation,
        author: me,
        parts: [{ type: 'text', text }],
        text,
        addressed_to: [],
        topics: [],
        because: null,
        action: 'record-only',
        dispatch: [],
        op: key,
        ...(replyTo ? { replies_to: replyTo } : {}),
      }
      let answer: MiniAnswer
      try {
        answer = await sendTo(POSTS_PATH, body, { [BRAIN_HEADER]: brain.brain })
      } catch {
        /* NOTHING CAME BACK. The post may be recorded: the words and the key
           are both kept, and nothing is sent again by itself. */
        if (!sendStill(mine)) return
        emit({ uncertain: true, sendError: UNCERTAIN_SEND })
        return
      }
      if (!sendStill(mine)) return
      if (refusedAsOtherBrain(answer.status, answer.body)) {
        binding.move()
        heldOp = null
        emit({ sendError: errorOf(answer.body) ?? MOVED_SEND, identity: MOVED_SEND })
        return
      }
      const refusal = errorOf(answer.body)
      if (answer.status !== 200 || refusal) {
        /* ANSWERED AND REFUSED: nothing was recorded, and the key stays with
           these words so a deliberate retry is still the same one post. */
        emit({ sendError: refusal ?? `This post was not recorded (${answer.status}).` })
        return
      }
      const out = object(answer.body)
      const posted = typeof out?.post === 'string' ? out.post : null
      heldOp = null
      /* WHAT WAS TYPED SINCE IS NOT THROWN AWAY: only the words that were sent
         are cleared, and anything added while the send was in flight stays. */
      if (current.draft.trim() === text) {
        discardMiniDraft(at.resource)
        emit({ draft: '', replyTo: null })
      }
      emit({
        uncertain: false,
        sent: posted ? { post: posted, number: typeof out?.number === 'number' ? out.number : null, replayed: !!out?.replayed } : undefined,
      })
      await read()
      if (sendStill(mine) && current.thread && replyTo) await openThread(current.thread.root)
    } finally {
      if (sendStill(mine)) emit({ sending: false })
    }
  }

  return {
    conversation,
    snapshot: () => current,
    subscribe(fn) { if (!disposed) heard.add(fn); return () => { heard.delete(fn) } },
    read,
    earlier,
    openThread,
    closeThread() { emit({ thread: null }) },
    replyTo(post) {
      emit({ replyTo: post ? { id: post.id, number: post.number, alias: post.authorAlias } : null })
    },
    draft(text) {
      setMiniDraft(at.resource, text)
      /* DIFFERENT WORDS ARE A DIFFERENT POST: the uncertain attempt's key no
         longer covers them, and saying the outcome is unknown would be about
         words that were never sent. The attempt itself stays unresolved and
         the earlier words' key is let go with them. */
      const covered = !!heldOp && heldOp.text === text.trim() && heldOp.replyTo === (current.replyTo?.id ?? null)
      emit({ draft: text, ...(current.uncertain && !covered ? { uncertain: false, sendError: undefined } : {}) })
      if (!covered) heldOp = null
    },
    send,
    cancel,
    dispose() {
      if (disposed) return
      disposed = true
      generation++
      sends++
      control?.abort()
      control = null
      reading = null
      /* The DRAFT outlives this store on purpose: the card is remounted by
         collapse, by a tab change and by the parent, and the words are the
         owner's until they send or discard them. */
      heard.forEach((fn) => fn())
      heard.clear()
    },
  }
}
