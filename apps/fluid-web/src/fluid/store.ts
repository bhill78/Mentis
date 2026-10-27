/* THE FLUID CLIENT STORE (stages F0-F2; it reads, and the composer writes
 * through /fluid/api/posts, never through the store).
 *
 * ONE STORE FOR EVERY ZONE, keyed by entity id. Three things are kept apart:
 *
 *   entities     a post or a conversation as it now reads, by id
 *   collections  where things appear: ordered placements (id, via, number,
 *                reply-to, home) under a key -- `conversation:<id>`,
 *                `thread:<root>`, `conversations` -- never a body
 *   cursor       the change cursor the store has caught up to
 *
 * A placement is not part of a post: the same post appears in several
 * conversations with a different `via` and no number where it is included,
 * and storing that on the post would let one zone overwrite another's.
 *
 * WHO RE-RENDERS. Each entity and collection has its own listeners; a change
 * notifies only the keys it replaced. A zone subscribes to what it shows, so
 * a post edited in one conversation re-renders that post's card and nothing
 * else. The change loop (`follow`) asks `/fluid/api/changes` on the pulse's
 * cadence and fetches ONLY the changed ids this store already holds.
 *
 * OBJECTS (F1) ARE ENTITIES TOO, keyed by their LIVE ADDRESS
 * (`live:<root>:<key>`): what a post holds, as the server addresses it. Which
 * objects a post has is kept apart, under its root, with the version it was
 * read at; a change naming that post at another version, or naming
 * `objects:<root>` (what a run returned with it changed), reads them again. The
 * kept zone holds live addresses only, so a kept object follows its post's
 * edits, and says so when an edit removed it. Without the server's engine the
 * keys come from the same function the server runs (`objectsOfPost`). */

import { CLIENT_HEADERS } from '../api'
import { fluidFetch, newReadPeriod, readsInFlight, sharedJson } from './http'
import { hearPulse, hearPulseBeat } from './identity/activity'
import { objectsOfPost, type PostInput } from '../experimental/postobjects'
import type { RBlock } from '../experimental/spec/core'
import type { ObjectIs } from '../experimental/objectkinds'
import type { NeedsItems } from '../needsItems'

export type Id = string

export interface Part {
  type: string
  text?: string
  ref?: string
  [k: string]: unknown
}

export interface Membership {
  conversation: Id
  via: 'home' | 'linked'
  name?: string
  link?: Id
  by?: Id
  at?: number
}

export interface AgentWork {
  kind: 'brief' | 'result' | 'finding' | 'follow-up'
  why: string
  to: Id | null
  to_name: string | null
}

export interface Post {
  id: Id
  version: Id
  versions: number
  author: Id
  author_name: string
  at: number
  edited_at: number | null
  deleted: { record: Id; at: number; by: Id; because: string | null } | null
  parts: Part[]
  addressed_to: Id[]
  home: Id | null
  home_name: string | null
  number: number | null
  reply_to: Id | null
  reply_to_home: Id | null
  reply_to_home_name: string | null
  reply_to_number: number | null
  memberships: Membership[]
  expectations: Id[]
  /** the decision forms it carries (P7): asked `on` it, or put on it as a
   *  run's answer post; drawn under it from `decisions?post=` (P9) */
  decision_forms?: Id[]
  replies: { count: number; by_home: Record<Id, number> }
  /** AGENT WORK (`conversation.agent_work`): agent-to-agent chatter the
   *  column folds away by default, and why; null for what the owner reads */
  agent_work?: AgentWork | null
  /** the WHOLE thread (F6, `posts?thread=1`): every reply under it at any
   *  depth, where they live, and what This post shows for it, by kind */
  thread?: ThreadSummary
}

export interface ThreadSummary {
  replies: number
  by_home: Record<Id, number>
  kinds: [string, number][]
  /** false: the server could not extract some of them (no engine) */
  extracted: boolean
}

/** Where the posts under one Topic of a conversation are held (A8). */
export const topicKey = (conversation: Id, topic: Id) => `topic:${conversation}:${topic}`

/** A post's whole-thread reply count: what its chip, its replies sheet and
 *  its details all say. */
export const repliesOf = (p: Post): number => p.thread?.replies ?? p.replies.count

/** Which posts This post shows objects of for a root (`objects?thread=`). */
export interface ThreadObjects {
  root: Id
  /** the root first, then its replies in stream order */
  posts: Id[]
  replies: number
  omitted: number
}

export interface Conversation {
  id: Id
  name: string
  about?: string
  created: number
  posts: number
  included: number
  participants: number
  last_activity: number | null
  working: number
  provisional?: boolean
  needs_you?: number | null
  topics?: { id: Id; name: string; turns: number }[]
}

export interface SelectionItem {
  id: Id
  home: Id | null
  known: boolean
}

export interface SelectionCollection {
  key: 'selection'
  items: SelectionItem[]
  cursor?: string
}

export interface StreamItem {
  id: Id
  home: Id | null
  at: number
}

export interface StreamCollection {
  key: 'stream'
  items: StreamItem[]
  before: string | null
  after: string | null
  cursor?: string
  limit?: number
}

export const newOp = () => `fluid-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`

export interface GroupIncludedItem {
  post: Id
  link: Id
  home: Id
}

export interface MemberAddedItem {
  post: Id
  link: Id
  already: boolean
}

export interface MemberEndedItem {
  post: Id
  link: Id
  deletion?: unknown
  unfiled?: number
}

export interface MemberRefusedItem {
  post: Id
  asked: 'add' | 'end'
  error?: string
  [key: string]: unknown
}

export interface Placement {
  id: Id
  via?: 'home' | 'linked'
  number?: number | null
  reply_to?: Id | null
  home?: Id | null
  parent?: Id | null
  depth?: number
  link?: Id | null
}

export interface Collection {
  key: string
  items: Placement[]
  total: number
  older: number
  newer: number
  before: string | null
  after: string | null
  cursor?: string
  root_home?: Id | null
  by_home?: Record<Id, number>
}

export interface Changes {
  cursor: string
  start?: boolean
  reread?: boolean
  posts?: { id: Id; version: Id | null; conversations: Id[] }[]
  conversations?: Id[]
  collections?: string[]
  entities?: string[]
  work?: (Id | { id: Id })[]
  runs?: (Id | { id: Id })[]
  /** posts whose whole thread may read differently (`threads=1`, F6) */
  threads?: Id[]
}

/** One alternative a decision was asked with, as the asker stated it. */
export interface AskOption { label: string; consequence?: string; per_finding?: boolean; findings?: { ref: Id; label: string }[] }
/** A request as What needs you reads it (#576, `needs-you?post=` / `?ids=`). */
export interface Ask {
  id: Id
  error?: string
  expects: string | null
  options: AskOption[] | null
  because: string | null
  asked_by: Id
  asked_by_name: string
  carrier: Id | null
  carrier_name: string | null
  /** Home's Needs you rule itself (`home.asking_owner`): it needs the owner now */
  open: boolean
  /** what the record says became of it (`home._ask_rows`): open; withdrawn by
   *  the owner; answered by the owner; elsewhere -- somebody else carries it
   *  now; closed -- none of these, it asks the owner nothing now */
  state: 'open' | 'withdrawn' | 'answered' | 'elsewhere' | 'closed'
  answered: boolean
  withdrawn: boolean
  post: Id | null
  post_number: number | null
  post_author: Id | null
  post_topics: Id[]
  conversation: Id | null
  conversation_name: string | null
  at: number | null
  /** a question of a decision form (P7): the form, drawn whole (P9) */
  form?: Id
  /** an input (`request_input`): the block it waits on (P11) */
  block?: { set: Id; block: string; part: number; type: string | null } | null
}
/** What on one post, or the thread under it, needs the owner. */
export interface NeedsYouOn { key: string; post: Id; items: Id[]; owner: Id | null; unknown?: boolean; why?: string; cursor: string }

export interface WorkItem {
  id: Id
  what: string
  state: string
  carrier: Id | null
  carrier_name: string | null
  conversation: Id
  conversation_name: string
  post: Id
  post_number: number | null
  runs: Id[]
  updated_at: number
}

export interface RunItem {
  id: Id
  runtime: string
  model: string
  participant: string
  participant_name?: string
  conversation: Id
  post: Id
  state: string
  started_at: number
  ended_at: number | null
}

export interface BriefingItem {
  post: Id
  conversation: Id
  line: string
}

export interface BriefingData {
  period: 'morning' | 'lunch' | 'evening'
  items: BriefingItem[]
  cursor: string
}

export interface HomeWorkData {
  items: Id[]
  before: string | null
  counts: Record<string, number>
  cursor: string
}

export interface HomeCollectionData {
  items: Id[]
  before?: string | null
  cursor: string
}

/** One object of a post, as listed (`GET /fluid/api/objects?post=`). */
export interface PostObjectEntry {
  key: string
  part: number | null
  kind: 'block' | 'figure' | 'post-text' | 'media' | 'link'
  type: string
  title: string | null
  name: string | null
  /** a link object's (Objects B6): experimental/postobjects.ts; `is`: what it is (experimental/objectkinds.ts) */
  link?: { url: string; label: string | null; domain: string; video: string | null }
  is?: ObjectIs
  identity: 'declared' | 'reference' | 'positional'
  stable: boolean
  declared: boolean
  parent: string | null
  page: string | null
  line: number | null
  end: number | null
  formats?: string[]
  address: { exact: string; live: string }
  block?: RBlock
  ref?: string | null
  media_type?: string | null
  artifact?: { ref: string; url: string; state?: string }
  /** the post (root) and the version it was read from */
  post: Id
  version: Id
}

/** One post's listing, as `objects?post=` (and each post of `objects?posts=`) gives it. */
interface Listing {
  version: Id | null; deleted?: boolean; extracted: boolean | null; why_not?: string; input?: PostInput
  objects: Omit<PostObjectEntry, 'post' | 'version'>[]
}

/** An address held in the store: its object, or why it does not resolve. */
export type ObjectState =
  | { address: string; object: PostObjectEntry; derived?: boolean }
  | { address: string; unresolved: string }

export interface PostObjectsState {
  post: Id
  version: Id | null
  /** live addresses, in the post's order */
  addresses: string[]
  /** false: the server has no engine and the keys were derived here */
  extracted: boolean
  why_not?: string
  deleted?: boolean
}

export const liveRoot = (address: string) => (address.startsWith('live:') ? address.split(':', 3)[1] : null)

/** The keys the server's bundle would have given, from the input it handed
 *  back when it could not run it: the same function, in the client. */
function derived(input: PostInput, version: Id): PostObjectEntry[] {
  return objectsOfPost(input).map((o) => ({
    ...o, declared: o.identity === 'declared', post: input.id, version,
    address: { exact: `exact:${version}:${o.part ?? '-'}:${o.key}`, live: `live:${input.id}:${o.key}` },
    ...(o.ref ? { artifact: { ref: o.ref, url: `/api/artifacts/${o.ref}` } } : {}),
  }))
}

const KEPT = 'mentis.fluid.kept'
const readKept = (): string[] => {
  try {
    const got = JSON.parse(localStorage.getItem(KEPT) ?? '[]')
    return Array.isArray(got) ? got.filter((x) => typeof x === 'string' && x.startsWith('live:')) : []
  } catch {
    return []
  }
}

const SELECTION_KEY = 'mentis.fluid.selection'
const readSelection = (): string[] => {
  try {
    if (typeof sessionStorage === 'undefined') return []
    const got = JSON.parse(sessionStorage.getItem(SELECTION_KEY) ?? '[]')
    return Array.isArray(got) ? got.filter((x) => typeof x === 'string') : []
  } catch {
    return []
  }
}
const writeSelection = (ids: string[]) => {
  try {
    if (typeof sessionStorage === 'undefined') return
    sessionStorage.setItem(SELECTION_KEY, JSON.stringify(ids))
  } catch {}
}

/* AN UNNAMED CONVERSATION READS AS WHEN IT WAS STARTED (#190: "Unnamed ·
   started 1:40 PM"; opr-005ddf2f48f8). The record keeps the name it stands
   under as the domain writes it, "Unnamed 2026-10-20T04:06:34Z" (UTC, as
   Classic shows it too); Fluid shows it in the reader's own time: the time
   alone today, with the day otherwise.

   ONLY A NAME, AND ONLY A PROVISIONAL ONE (opr-7fb501067641): what is read so
   is a Conversation's name while the API says it is still `provisional`, and
   the same name where a post or a work item names that conversation (its home,
   its parent's home, where it is included). A post's text, an object's title,
   or a name somebody chose that happens to read the same are never touched.
   The seconds are shown (opr-835dfb8981a8 item 5): two conversations started
   in the same minute read apart in the switcher. Save names it as before. */
const PROVISIONAL = /^Unnamed (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)$/
export function readableName(name: string): string {
  const m = PROVISIONAL.exec(name)
  if (!m) return name
  const at = new Date(m[1])
  if (Number.isNaN(at.getTime())) return name
  const now = new Date()
  const time = at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' })
  const sameDay = at.toDateString() === now.toDateString()
  const day = at.toLocaleDateString([], { month: 'short', day: 'numeric', ...(at.getFullYear() !== now.getFullYear() ? { year: 'numeric' } : {}) })
  return `Unnamed · started ${sameDay ? time : `${day}, ${time}`}`
}
const shownConversation = <C extends Conversation>(c: C): C => (c.provisional === true ? { ...c, name: readableName(c.name) } : c)

/* ONE READ IN FLIGHT PER QUESTION (the owner's slowdown, 2026-10-25). Home's
   zones mount twice as the page opens (the layout before its arrangement is
   read, then the arrangement), and two zones can draw one collection, so the
   page asked `home/work` three times and `home/briefing`, `home/needs-you`,
   `home/for-you`, `home/activity` and `participants?limit=1` twice or more,
   all at once, each competing for the server's one interpreter. A read asked
   while the same read is on its way now waits for that one.

   NEVER ACROSS A WRITE: any write this page makes (any non-GET fetch) moves
   `epoch` when it starts and again when it ends, and a read is shared only
   with one started in the same epoch -- so a read asked after a write began
   is always a new read, never one that may have been answered before it.

   NOR ACROSS ANYBODY ELSE'S: a write made elsewhere (an agent, another tab)
   reaches this page only as movement in the change feed, and the feed's
   re-reads are asked to see it. So a change step that reports movement
   starts a new sharing period (`newReadPeriod`) before it reads anything
   again: none of its re-reads can join a read begun before the feed said
   the record moved. */
export { newReadPeriod, readEpoch } from './http'

/* WHAT NOBODY IS LOOKING AT WAITS FOR WHAT SOMEBODY IS. A read the page
   does not draw on opening (the bar's capacity ring, which is minutes-old
   rate-limit files) is asked once the page's own reads have been quiet for
   `QUIET_MS`, or `STARTUP_MAX_MS` after the page began, whichever is first:
   asked at once it competed with the zones being drawn for the server's one
   interpreter. Nothing is skipped -- it is asked later. */
const QUIET_MS = 800
const STARTUP_MAX_MS = 10000
let startupDone: Promise<void> | null = null
export function afterStartup(): Promise<void> {
  if (!startupDone) {
    startupDone = new Promise<void>((resolve) => {
      const began = typeof performance !== 'undefined' ? performance.now() : Date.now()
      let quietSince: number | null = null
      const look = () => {
        const now = typeof performance !== 'undefined' ? performance.now() : Date.now()
        if (readsInFlight()) quietSince = null
        else if (quietSince === null) quietSince = now
        if ((quietSince !== null && now - quietSince >= QUIET_MS) || now - began >= STARTUP_MAX_MS) resolve()
        else window.setTimeout(look, 100)
      }
      window.setTimeout(look, 100)
    })
  }
  return startupDone
}

/* AND WHAT DECORATES A CONVERSATION WAITS FOR ITS POSTS. Opening one asks
   its collection, then its posts -- the reading itself -- and, at the same
   moment, its work status pills (`/api/work?conversation=`, ~1.5 s of the
   server's time) and its participants and topics (`?batch=0`, ~0.4 s). All
   at once, the cheap reads the page is waiting for finished when the
   expensive ones did (measured: a 0.02 s collection read took 5-9 s).
   `whenQuiet` resolves once this store's own reads have been quiet for
   `ms` (at most `most` ms), so a decoration is asked just after the posts
   are drawn rather than in competition with them. */
export function whenQuiet(ms = 150, most = 6000): Promise<void> {
  return new Promise<void>((resolve) => {
    if (typeof window === 'undefined') { resolve(); return }
    const began = Date.now()
    let quietSince: number | null = null
    const look = () => {
      const now = Date.now()
      if (readsInFlight()) quietSince = null
      else if (quietSince === null) quietSince = now
      if ((quietSince !== null && now - quietSince >= ms) || now - began >= most) resolve()
      else window.setTimeout(look, 30)
    }
    /* After this turn: the reads a click starts are asked in its effects. */
    window.setTimeout(look, 30)
  })
}

/** Which Brain this is (`/api/brain?identity=1`): its name, role, path and
 *  id -- what the frame names and notifications are keyed by. Read once per
 *  page; it does not change while the page is open. */
export interface BrainIdentity {
  corpus_id?: string; corpus_path?: string | null
  corpus_name?: string | null; corpus_role?: string | null; corpus_name_why_not?: string | null
}
let brainRead: Promise<BrainIdentity | null> | null = null
export function brainIdentity(): Promise<BrainIdentity | null> {
  if (!brainRead) {
    brainRead = fluidFetch('/api/brain?identity=1', { headers: { ...CLIENT_HEADERS } })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((b) => { if (!b) brainRead = null; return b })
  }
  return brainRead
}

/** Whether a change answer names anything at all as moved. */
function moved(ch: object): boolean {
  return Object.entries(ch).some(([k, v]) => k !== 'cursor' && k !== 'start' && (Array.isArray(v) ? v.length > 0 : false))
}

function get<T>(path: string): Promise<T> {
  return sharedJson<T>('/fluid/api/' + path, { ...CLIENT_HEADERS })
}

const BATCH = 64
/** How long the switcher trusts a list read at the change cursor it holds. */
const LIST_FRESH_MS = 30000
const PAGE = 30
/** Members read before a post the conversation is read around. */
const AROUND = 10
/** The server's most per page (`read.PAGE_MAX`): what a reread asks for. */
const PAGE_MAX = 200
/** Thread listings kept while not shown (`dropThreads`). */
const IDLE_THREADS = 8
const chunks = <T,>(xs: T[], n: number) =>
  Array.from({ length: Math.ceil(xs.length / n) }, (_, i) => xs.slice(i * n, i * n + n))

type Listener = () => void

class Store {
  posts = new Map<Id, Post>()
  conversations = new Map<Id, Conversation>()
  list: Conversation[] | null = null
  listTotal = 0
  listNext: string | null = null
  collections = new Map<string, Collection>()
  /** objects, by live address */
  objects = new Map<string, ObjectState>()
  /** which objects each post has, by root */
  postObjects = new Map<Id, PostObjectsState>()
  /** which posts This post shows objects of, by the root read */
  threadObjects = new Map<Id, ThreadObjects>()
  /** the kept zone: live addresses, kept across posts and reloads */
  kept: string[] = readKept()
  /** selection across conversations (lasts for session only) */
  selected: Set<Id> = new Set(readSelection())
  work = new Map<Id, WorkItem>()
  runs = new Map<Id, RunItem>()
  briefing: BriefingData | null = null
  homeWork = new Map<string, HomeWorkData>()
  homeNeedsYou: HomeCollectionData | null = null
  /** What needs you on a post (#576), by post, and each request by id */
  needsYouOn = new Map<Id, NeedsYouOn>()
  asks = new Map<Id, Ask>()
  /** What needs you, one item per form (P11): the bell's list and count */
  needsItems: NeedsItems | null = null
  homeForYou: HomeCollectionData | null = null
  homeActivity: { items: Id[]; cursor: string } | null = null
  arrangements = new Map<string, any>()
  cursor: string | null = null
  commandError: string | null = null
  feedError: string | null = null
  pickedBriefingPeriod: 'morning' | 'lunch' | 'evening' | null = null
  private listeners = new Map<string, Set<Listener>>()

  get error(): string | null {
    return this.commandError ?? this.feedError
  }

  set error(val: string | null) {
    this.commandError = val
  }

  subscribe = (key: string, fn: Listener) => {
    let set = this.listeners.get(key)
    if (!set) this.listeners.set(key, (set = new Set()))
    set.add(fn)
    return () => {
      set!.delete(fn)
    }
  }

  notify(key: string) {
    this.listeners.get(key)?.forEach((fn) => fn())
  }

  hasListener(key: string): boolean {
    const set = this.listeners.get(key)
    return !!(set && set.size > 0)
  }

  /** Let go of the Home answers no zone shows, so the change loop does not
   *  read them again for nobody; a zone reads its own when it mounts. */
  private dropUnshownHome() {
    const anyWork = this.hasListener('coll:home:work')
    for (const st of [...this.homeWork.keys()]) {
      if (!anyWork && !this.hasListener('coll:home:work:' + st)) this.homeWork.delete(st)
    }
    if (!this.hasListener('coll:home:needs-you')) this.homeNeedsYou = null
    if (!this.hasListener('coll:home:activity')) this.homeActivity = null
    if (!this.hasListener('coll:home:briefing')) this.briefing = null
    if (!this.hasListener('coll:home:for-you')) this.homeForYou = null
  }

  setError(err: string | null) {
    this.commandError = err
    if (err === null) this.feedError = null
    this.notify('error')
  }

  /* -- entities --------------------------------------------------------- */

  /** A conversation's name where something names it (`readableName`):
   *  readable only while the store holds that conversation as provisional. */
  private nameShown<T extends string | null | undefined>(id: Id | null | undefined, raw: T): T {
    if (!raw || !id || this.conversations.get(id)?.provisional !== true) return raw
    return readableName(raw) as T
  }

  private postShown(p: Post): Post {
    return {
      ...p,
      home_name: this.nameShown(p.home, p.home_name),
      reply_to_home_name: this.nameShown(p.reply_to_home, p.reply_to_home_name),
      memberships: (p.memberships ?? []).map((m) => (m.name ? { ...m, name: this.nameShown(m.conversation, m.name) } : m)),
    }
  }

  /** Conversations as the API gave them, held under the names they show.
   *  One newly known as provisional is shown so wherever a held post or work
   *  item names it, too: the list can arrive after the posts. */
  private putConversations(cs: Conversation[]): Conversation[] {
    const newly = new Set<Id>()
    const shown = cs.map((c) => {
      if (c.provisional === true && this.conversations.get(c.id)?.provisional !== true) newly.add(c.id)
      const s = shownConversation(c)
      this.conversations.set(c.id, s)
      return s
    })
    if (newly.size) {
      for (const p of this.posts.values()) {
        if (![p.home, p.reply_to_home, ...(p.memberships ?? []).map((m) => m.conversation)].some((x) => x && newly.has(x))) continue
        this.posts.set(p.id, this.postShown(p))
        this.notify('post:' + p.id)
      }
      for (const w of this.work.values()) {
        if (!newly.has(w.conversation)) continue
        this.work.set(w.id, { ...w, conversation_name: this.nameShown(w.conversation, w.conversation_name) })
        this.notify('work:' + w.id)
      }
    }
    for (const c of shown) this.notify('conv:' + c.id)
    return shown
  }

  async loadPosts(ids: Id[], force = false) {
    const want = [...new Set(ids)].filter((i) => force || !this.posts.has(i))
    for (const part of chunks(want, BATCH)) {
      /* `thread=1`: each post's whole thread with it, for its chip and counts (F6). */
      const got = await get<{ posts: (Post & { error?: string })[] }>('posts?ids=' + part.map(encodeURIComponent).join(',') + '&thread=1')
      for (const raw of got.posts) {
        if (raw.error) continue
        const p = this.postShown(raw)
        const had = this.posts.get(p.id)
        if (had && JSON.stringify(had) === JSON.stringify(p)) continue
        this.posts.set(p.id, p)
        this.notify('post:' + p.id)
      }
    }
  }

  async loadConversations(ids: Id[]) {
    for (const part of chunks([...new Set(ids)], BATCH)) {
      const got = await get<{ conversations: (Conversation & { error?: string })[] }>('conversations?ids=' + part.map(encodeURIComponent).join(','))
      this.putConversations(got.conversations.filter((c) => !c.error))
    }
  }

  async loadList() {
    const at = { cursor: this.cursor, t: Date.now() }
    const got = await get<{ conversations: Conversation[]; total: number; next: string | null }>('conversations?activity=1&limit=40')
    this.list = this.putConversations(got.conversations)
    this.listTotal = got.total
    this.listNext = got.next
    this.listAt = at
    this.notify('coll:conversations')
  }

  /** The next switcher page. A search has its own page and does not replace
   * the canonical recent list held by the shell. */
  async conversationPage(cursor: string | null, q = ''): Promise<{ conversations: Conversation[]; total: number; next: string | null }> {
    const params = new URLSearchParams({ activity: '1', limit: '40' })
    if (cursor) params.set('cursor', cursor)
    if (q) params.set('q', q)
    const got = await get<{ conversations: Conversation[]; total: number; next: string | null }>('conversations?' + params.toString())
    return { ...got, conversations: this.putConversations(got.conversations) }
  }

  async loadMoreList(): Promise<void> {
    if (!this.listNext) return
    const got = await this.conversationPage(this.listNext)
    const seen = new Set((this.list ?? []).map((c) => c.id))
    this.list = [...(this.list ?? []), ...got.conversations.filter((c) => !seen.has(c.id))]
    this.listTotal = got.total
    this.listNext = got.next
    this.notify('coll:conversations')
  }

  /** The cursor and time the list was last read at (`loadListIfMoved`). */
  private listAt: { cursor: string | null; t: number } | null = null

  /** THE SWITCHER'S READ OF THE LIST, ONLY IF IT MAY HAVE MOVED (the owner's
   *  slowdown, 2026-10-25): every opening of the sheet read the whole list
   *  again (~0.4-0.9 s of the server's time) while the pick it was opened for
   *  read its conversation. The change feed already reads the list again when
   *  a conversation moves (`stepOnce`); here it is read again only once the
   *  record has moved since, or `LIST_FRESH_MS` has gone by -- what is
   *  working now is observed, not recorded. */
  loadListIfMoved(): Promise<void> {
    const at = this.listAt
    if (this.list && at && at.cursor === this.cursor && Date.now() - at.t < LIST_FRESH_MS) return Promise.resolve()
    return this.loadList()
  }

  /* -- collections ------------------------------------------------------ */

  private setCollection(c: Collection) {
    this.collections.set(c.key, c)
    this.notify('coll:' + c.key)
  }

  /** One collection's reads, one at a time: a refresh and an older page
   *  never write over each other's answer. */
  private pending = new Map<string, Promise<unknown>>()
  private serial<T>(key: string, fn: () => Promise<T>): Promise<T> {
    const next = (this.pending.get(key) ?? Promise.resolve()).catch(() => {}).then(fn)
    this.pending.set(key, next)
    next.finally(() => { if (this.pending.get(key) === next) this.pending.delete(key) }).catch(() => {})
    return next
  }

  /** WHAT IS HELD, READ AGAIN: every member from the oldest position held
   *  (`from`, inclusive; `start` when nothing older is held) to the newest,
   *  page by page. New members come in and ended ones go out wherever they
   *  are, and the older pages a reader loaded stay loaded. */
  private async rereadHeld(path: string, held: Collection, also: Id[] = []) {
    const pages: Collection[] = []
    /* A WINDOW AROUND AN OLDER POST (`conversationAround`) is read again as
       far as it reaches, never on to the newest: what lies beyond stays
       `newer`, to scroll to. ITS END IS A POSITION, NOT A MEMBER
       (opr-4a5a62c8ae1c): the newest member held may since have been removed,
       and looking for it then read on to the newest. The window ends where its
       `after` cursor stands, which pages whether or not a member is still
       there; the page after it says how many members are at or before it
       (its `older`), so the members from where the window starts to there are
       exactly that many less those before the start. */
    const end = held.newer > 0 && held.items.length && held.after ? held.after : null
    let upto: number | null = null, total = 0
    if (end) {
      const beyond = await get<Collection>(`${path}&limit=1&after=${encodeURIComponent(end)}`)
      upto = beyond.older
      total = beyond.total
    }
    let at = `${path}&limit=${PAGE_MAX}&from=${encodeURIComponent(held.before ?? 'start')}`
    for (;;) {
      const got = await get<Collection>(at)
      pages.push(got)
      if (upto !== null && pages[0].older + pages.reduce((n, p) => n + p.items.length, 0) >= upto) break
      if (!got.newer || !got.after) break
      at = `${path}&limit=${PAGE_MAX}&after=${encodeURIComponent(got.after)}`
    }
    let items = pages.flatMap((p) => p.items)
    const first = pages[0], last = pages[pages.length - 1]
    let tail = { newer: last.newer, after: last.after }
    if (upto !== null) {
      items = items.slice(0, Math.max(0, upto - first.older))
      const beyond = Math.max(0, total - upto)
      tail = { newer: beyond, after: beyond ? end : null }
    }
    await this.loadPosts([...also, ...items.map((i) => i.id)])
    this.setCollection({ ...last, ...tail, items, older: first.older, before: first.before, cursor: first.cursor })
  }

  /** The newest page of a conversation, or -- `keepWidth` -- what is held of
   *  it read again (`rereadHeld`). */
  loadConversation(id: Id, keepWidth = false) {
    const key = 'conversation:' + id
    const path = `collections/conversation?id=${encodeURIComponent(id)}`
    return this.serial(key, async () => {
      const held = this.collections.get(key)
      if (keepWidth && held) return this.rereadHeld(path, held)
      const got = await get<Collection>(`${path}&limit=${PAGE}`)
      const items = got.items
      await this.loadPosts(items.map((i) => i.id))
      this.setCollection({ ...got, items })
    })
  }

  olderOfConversation(id: Id) {
    const key = 'conversation:' + id
    return this.serial(key, async () => {
      const held = this.collections.get(key)
      if (!held?.before) return
      const got = await get<Collection>(`collections/conversation?id=${encodeURIComponent(id)}&limit=${PAGE}&before=${encodeURIComponent(held.before)}`)
      await this.loadPosts(got.items.map((i) => i.id))
      this.setCollection({ ...held, items: [...got.items, ...held.items], older: got.older, before: got.before })
    })
  }

  /** A POST READ FAR BACK IS READ IN ITS PLACE (opr-49f1f943b6a9): the
   *  conversation is held around `post` -- a few members before it and a page
   *  from it, by the API's bounded paging from a member's id -- not as its
   *  newest page, which may not reach it. Older and newer pages follow
   *  (`olderOfConversation`, `newerOfConversation`). */
  conversationAround(id: Id, post: Id) {
    const key = 'conversation:' + id
    const path = `collections/conversation?id=${encodeURIComponent(id)}`
    return this.serial(key, async () => {
      const at = encodeURIComponent(post)
      const [b, f] = await Promise.all([
        get<Collection>(`${path}&limit=${AROUND}&before=${at}`),
        get<Collection>(`${path}&limit=${PAGE}&from=${at}`),
      ])
      const items = [...b.items, ...f.items]
      await this.loadPosts(items.map((i) => i.id))
      this.setCollection({ ...f, items, older: b.items.length ? b.older : f.older, before: b.items.length ? b.before : f.before })
    })
  }

  newerOfConversation(id: Id) {
    const key = 'conversation:' + id
    return this.serial(key, async () => {
      const held = this.collections.get(key)
      if (!held?.after || !held.newer) return
      const got = await get<Collection>(`collections/conversation?id=${encodeURIComponent(id)}&limit=${PAGE}&after=${encodeURIComponent(held.after)}`)
      await this.loadPosts(got.items.map((i) => i.id))
      const have = new Set(held.items.map((i) => i.id))
      this.setCollection({ ...held, items: [...held.items, ...got.items.filter((i) => !have.has(i.id))], newer: got.newer, after: got.after })
    })
  }

  loadThread(root: Id, keepWidth = false) {
    const key = 'thread:' + root
    const path = `collections/thread?root=${encodeURIComponent(root)}`
    return this.serial(key, async () => {
      const held = this.collections.get(key)
      if (keepWidth && held) return this.rereadHeld(path, held, [root])
      const got = await get<Collection>(`${path}&limit=${PAGE}`)
      await this.loadPosts([root, ...got.items.map((i) => i.id)])
      this.setCollection(got)
    })
  }

  olderOfThread(root: Id) {
    const key = 'thread:' + root
    return this.serial(key, async () => {
      const held = this.collections.get(key)
      if (!held?.before) return
      const got = await get<Collection>(`collections/thread?root=${encodeURIComponent(root)}&limit=${PAGE}&before=${encodeURIComponent(held.before)}`)
      await this.loadPosts(got.items.map((i) => i.id))
      this.setCollection({ ...held, items: [...got.items, ...held.items], older: got.older, before: got.before })
    })
  }

  /* -- stream (F5 C1) --------------------------------------------------- */

  streamDropped = false
  private streamToken = 0

  /** The newest page of the global stream across all conversations. */
  loadStream(keepWidth = false) {
    const key = 'stream'
    const path = 'collections/stream'
    if (!keepWidth) {
      this.streamDropped = false
    } else if (this.streamDropped) {
      return Promise.resolve()
    }
    const token = !keepWidth ? ++this.streamToken : this.streamToken
    return this.serial(key, async () => {
      if (this.streamDropped || this.streamToken !== token) return
      const held = this.collections.get(key)
      if (keepWidth && held) {
        const count = Math.min(Math.max(held.items.length, PAGE), PAGE_MAX)
        const got = await get<Collection>(`${path}?limit=${count}`)
        if (this.streamDropped || this.streamToken !== token) return
        const items = got.items
        await this.loadPosts(items.map((i) => i.id))
        if (this.streamDropped || this.streamToken !== token) return
        this.setCollection({ ...got, items, before: got.before ?? held.before })
        return
      }
      const got = await get<Collection>(`${path}?limit=${PAGE}`)
      if (this.streamDropped || this.streamToken !== token) return
      const items = got.items
      await this.loadPosts(items.map((i) => i.id))
      if (this.streamDropped || this.streamToken !== token) return
      this.setCollection({ ...got, items })
    })
  }

  olderOfStream() {
    const key = 'stream'
    if (this.streamDropped) return Promise.resolve()
    const token = this.streamToken
    return this.serial(key, async () => {
      if (this.streamDropped || this.streamToken !== token) return
      const held = this.collections.get(key)
      if (!held?.before) return
      const got = await get<Collection>(`collections/stream?limit=${PAGE}&before=${encodeURIComponent(held.before)}`)
      if (this.streamDropped || this.streamToken !== token) return
      await this.loadPosts(got.items.map((i) => i.id))
      if (this.streamDropped || this.streamToken !== token) return
      this.setCollection({
        ...held,
        items: [...held.items, ...got.items],
        older: got.older,
        before: got.before,
        after: got.after ?? held.after,
      })
    })
  }

  /** Drops the stream collection when the view is no longer showing it. */
  dropStream() {
    this.streamDropped = true
    this.streamToken++
    this.collections.delete('stream')
    this.notify('coll:stream')
  }


  /* -- selection (F5 C2) ------------------------------------------------ */

  async loadSelection(ids?: Id[]): Promise<SelectionCollection> {
    const targetIds = ids ?? Array.from(this.selected)
    if (!targetIds.length) {
      const empty: SelectionCollection = { key: 'selection', items: [] }
      this.collections.set('selection', empty as any)
      this.notify('coll:selection')
      return empty
    }
    const allItems: SelectionItem[] = []
    let cursor: string | undefined
    for (const chunk of chunks(targetIds, BATCH)) {
      const got = await get<SelectionCollection>(`collections/selection?ids=${chunk.map(encodeURIComponent).join(',')}`)
      if (got.items) allItems.push(...got.items)
      if (got.cursor) cursor = got.cursor
    }
    const knownIds = allItems.filter((i) => i.known).map((i) => i.id)
    if (knownIds.length) {
      await this.loadPosts(knownIds)
    }
    const result: SelectionCollection = { key: 'selection', items: allItems, ...(cursor ? { cursor } : {}) }
    this.collections.set('selection', result as any)
    this.notify('coll:selection')
    return result
  }

  toggleSelect(id: Id) {
    const next = new Set(this.selected)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    this.selected = next
    writeSelection([...this.selected])
    this.notify('selection')
    void this.loadSelection().catch(() => {})
  }

  setSelection(ids: Id[]) {
    this.selected = new Set(ids)
    writeSelection([...this.selected])
    this.notify('selection')
    void this.loadSelection().catch(() => {})
  }

  clearSelection() {
    this.selected = new Set()
    writeSelection([])
    this.notify('selection')
    void this.loadSelection().catch(() => {})
  }

  isSelected(id: Id): boolean {
    return this.selected.has(id)
  }

  /* -- objects (F1) ----------------------------------------------------- */

  private putObject(st: ObjectState) {
    const had = this.objects.get(st.address)
    if (had && JSON.stringify(had) === JSON.stringify(st)) return
    this.objects.set(st.address, st)
    this.notify('obj:' + st.address)
  }

  /** A post's objects at its current version. */
  async loadObjects(root: Id, force = false) {
    if (!force && this.postObjects.has(root)) return
    this.putListing(root, await get<Listing>('objects?post=' + encodeURIComponent(root)))
  }

  /** Many posts' objects in one read per BATCH (`objects?posts=`, F6). */
  async loadObjectsMany(roots: Id[], force = false) {
    const want = [...new Set(roots)].filter((r) => force || !this.postObjects.has(r))
    for (const part of chunks(want, BATCH)) {
      const got = await get<{ posts: (Listing & { post: Id; error?: string })[] }>('objects?posts=' + part.map(encodeURIComponent).join(','))
      for (const l of got.posts) if (!l.error) this.putListing(l.post, l)
    }
  }

  /** What This post shows for a root: its objects and every reply's under it,
   *  in ONE read (`objects?thread=`, F6), and those posts, in one more. */
  async loadThreadObjects(root: Id, force = false) {
    if (!force && this.threadObjects.has(root)) return
    const got = await get<{ root: Id; replies: number; omitted: number; posts: (Listing & { post: Id; error?: string })[] }>(
      'objects?thread=' + encodeURIComponent(root))
    for (const l of got.posts) if (!l.error) this.putListing(l.post, l)
    const posts = got.posts.filter((l) => !l.error).map((l) => l.post)
    /* Each card's "from #N . @who" reads its post: all of them, batched, not one each. */
    await this.loadPosts(posts).catch(() => {})
    this.threadObjects.delete(root)
    this.threadObjects.set(root, { root, posts, replies: got.replies, omitted: got.omitted })
    this.notify('tobjects:' + root)
    this.dropThreads()
  }

  /** THREAD LISTINGS NOBODY SHOWS ARE LET GO (F6 final fix round): one This
   *  post shows is kept; of the rest, the IDLE_THREADS read last stay (Back
   *  to a post is instant), and older ones are dropped and read again only
   *  if shown again. */
  private dropThreads() {
    const idle = [...this.threadObjects.keys()].filter((r) => !this.hasListener('tobjects:' + r))
    for (const r of idle.slice(0, Math.max(0, idle.length - IDLE_THREADS))) this.threadObjects.delete(r)
  }

  private putListing(root: Id, got: Listing) {
    const version = got.version
    const list: PostObjectEntry[] = got.extracted === false && got.input && version
      ? derived(got.input, version)
      : (got.objects ?? []).map((o) => ({ ...o, post: root, version: version! }))
    for (const o of list) this.putObject({ address: o.address.live, object: o, ...(got.extracted === false ? { derived: true } : {}) })
    const before = this.postObjects.get(root)
    /* An object the new version no longer has: a keeper is told, never shown the old one. */
    for (const a of before?.addresses ?? [])
      if (!list.some((o) => o.address.live === a)) this.putObject({ address: a, unresolved: 'no longer in this post' })
    this.postObjects.set(root, {
      post: root, version, addresses: list.map((o) => o.address.live), extracted: got.extracted !== false,
      ...(got.why_not ? { why_not: got.why_not } : {}), ...(got.deleted ? { deleted: true } : {}),
    })
    this.notify('objects:' + root)
  }

  /** One object by its live address (a kept one whose post is not followed). */
  async loadObject(address: string) {
    const res = await fluidFetch('/fluid/api/objects/' + encodeURIComponent(address) + '?format=json', { headers: { ...CLIENT_HEADERS } })
    const body = await res.json().catch(() => null)
    if (res.status === 404 && body?.resolves === false) return this.putObject({ address, unresolved: String(body.why) })
    if (!res.ok || !body || body.error) throw new Error(body?.error ?? res.statusText)
    if (body.extracted === false) {
      const key = address.split(':').slice(2).join(':')
      const o = derived(body.input as PostInput, body.version).find((x) => x.key === key)
      return this.putObject(o ? { address, object: o, derived: true } : { address, unresolved: 'no longer resolves (derived without the server engine)' })
    }
    this.putObject({ address, object: { ...body.object, post: body.post, version: body.version } })
  }

  isKept = (address: string) => this.kept.includes(address)

  /** What the places' zones keep, wherever the reader put it (stream A):
   *  read again when its post changes, as the kept zone's were. Each place
   *  that keeps -- the conversation's workspace, Home (D1) -- says what it
   *  holds under its own name, and neither clears the other's. */
  held: string[] = []
  private heldBy = new Map<string, string[]>()
  setHeld(addresses: string[], by = 'workspace') {
    this.heldBy.set(by, addresses)
    this.held = [...new Set([...this.heldBy.values()].flat())]
  }

  keep(address: string, on = true) {
    const has = this.kept.includes(address)
    if (on === has) return
    this.kept = on ? [...this.kept, address] : this.kept.filter((a) => a !== address)
    try {
      localStorage.setItem(KEPT, JSON.stringify(this.kept))
    } catch {
      /* private mode: kept for this page only */
    }
    this.notify('kept')
    this.notify('keep:' + address)
  }

  /** What a change to these posts means for the objects held: a post read at
   *  another version, or one the feed names `objects:<root>` for (what a run
   *  returned with it changed, at the same version), is read again -- its
   *  listing if a zone follows it, and every kept address under it. */
  private async objectsChanged(changed: Map<Id, Id | null>, named: Set<Id>, all: boolean, threads: Set<Id>) {
    const jobs: Promise<unknown>[] = []
    /* A thread This post shows, whose count or objects moved (the feed's
       `threads`, F6): its listing is read again whole, in one read. */
    const reread = new Set<Id>()
    for (const [root, t] of [...this.threadObjects]) {
      if (all || threads.has(root)) {
        /* Only a thread still on screen is read again; one that is not is
           dropped, and read afresh if it is shown again. */
        if (!this.hasListener('tobjects:' + root)) { this.threadObjects.delete(root); continue }
        jobs.push(this.loadThreadObjects(root, true))
        for (const p of t.posts) reread.add(p)
      }
    }
    const stale: Id[] = []
    for (const [root, held] of this.postObjects) {
      if (reread.has(root)) continue
      if (all || named.has(root) || (changed.has(root) && changed.get(root) !== held.version)) stale.push(root)
    }
    /* One post read as it always was; several, in one batched read. */
    if (stale.length === 1) jobs.push(this.loadObjects(stale[0], true))
    else if (stale.length) jobs.push(this.loadObjectsMany(stale, true))
    for (const a of new Set([...this.kept, ...this.held])) {
      const root = liveRoot(a)
      if (!root || this.postObjects.has(root)) continue
      const st = this.objects.get(a)
      const at = st && 'object' in st ? st.object.version : null
      if (all || named.has(root) || (changed.has(root) && changed.get(root) !== at)) jobs.push(this.loadObject(a))
    }
    const settled = await Promise.allSettled(jobs)
    const failed = settled.find((r) => r.status === 'rejected')
    if (failed) throw (failed as PromiseRejectedResult).reason
  }

  /* -- following the record --------------------------------------------- */

  /* ONE STEP AT A TIME. The loop and a post's catch-up (`posted`) both step,
     and two steps racing would each move the cursor past the other's read. */
  private stepping: Promise<void> = Promise.resolve()

  /** One step of the change loop, after any step already running. */
  step(): Promise<void> {
    const run = this.stepping.then(() => this.stepOnce())
    this.stepping = run.catch(() => {})
    return run
  }

  /** WHAT THIS PAGE JUST POSTED (F2), caught up at once rather than on the
   *  next beat: the change feed brings the post into every collection it
   *  belongs to, exactly as it would bring anybody else's. A reply's parent is
   *  read again too, for its count of replies. Nothing is reloaded. */
  async posted(post: Id, conversation: Id, replyTo: Id | null) {
    await this.step()
    const jobs: Promise<unknown>[] = []
    if (replyTo && this.posts.has(replyTo)) jobs.push(this.loadPosts([replyTo], true))
    if (!this.posts.has(post)) jobs.push(this.loadPosts([post]))
    if (this.conversations.has(conversation)) jobs.push(this.loadConversations([conversation]))
    await Promise.all(jobs)
  }

  /** One step of the change loop: what moved since the cursor, and only the
   *  changed things this store holds are read again.
   *
   *  THE CURSOR MOVES ONLY WHEN EVERY READ THE CHANGE CALLED FOR HAS
   *  SUCCEEDED. If any fails the step throws with the cursor where it was,
   *  so the next step is told the same change and reads it again; each read
   *  replaces what it reads, so reading it twice is the same as once. */
  private async stepOnce() {
    /* `threads=1`: which posts' whole threads moved, for their chips and counts (F6). */
    const ch = await get<Changes>('changes' + (this.cursor ? '?since=' + encodeURIComponent(this.cursor) + '&threads=1' : ''))
    if (this.cursor === null || ch.start) {
      this.cursor = ch.cursor
      return
    }
    const rereadAll = !!ch.reread
    /* MOVED ELSEWHERE: every read below is asked to see it, so none may join
       a read begun before this answer came (`newReadPeriod`). */
    if (rereadAll || ch.cursor !== this.cursor || moved(ch)) newReadPeriod()
    const namedConvs = (ch.collections ?? [])
      .filter((k) => k.startsWith('conversation:'))
      .map((k) => k.slice('conversation:'.length))
    const chConvs = [...new Set([...(ch.conversations ?? []), ...namedConvs])]
    /* A post whose whole thread moved -- a reply anywhere under it, or a
       reply's objects -- is read again for its summary, though it did not change. */
    const threads = new Set([...(ch.threads ?? []),
      ...(ch.collections ?? []).filter((k) => k.startsWith('thread:')).map((k) => k.slice('thread:'.length))])
    const posts = rereadAll ? [...this.posts.keys()]
      : [...new Set([...(ch.posts ?? []).map((p) => p.id), ...threads])].filter((id) => this.posts.has(id))
    const convs = rereadAll ? [...this.conversations.keys()] : chConvs.filter((id) => this.conversations.has(id))
    const keys = rereadAll ? [...this.collections.keys()] : (ch.collections ?? []).filter((k) => this.collections.has(k))

    const workIdsFromEntities = (ch.entities ?? [])
      .filter((k) => k.startsWith('work:'))
      .map((k) => k.slice('work:'.length))
    const workIdsFromCollections = (ch.collections ?? [])
      .filter((k) => k.startsWith('work:'))
      .map((k) => k.slice('work:'.length))
    const workIdsFromFeed = ((ch as any).work ?? []).map((w: any) => (typeof w === 'string' ? w : w.id))
    const allWorkIds = [...new Set([...workIdsFromEntities, ...workIdsFromCollections, ...workIdsFromFeed])]

    const runIdsFromEntities = (ch.entities ?? [])
      .filter((k) => k.startsWith('run:'))
      .map((k) => k.slice('run:'.length))
    const runIdsFromCollections = (ch.collections ?? [])
      .filter((k) => k.startsWith('run:'))
      .map((k) => k.slice('run:'.length))
    const runIdsFromFeed = ((ch as any).runs ?? []).map((r: any) => (typeof r === 'string' ? r : r.id))
    const allRunIds = [...new Set([...runIdsFromEntities, ...runIdsFromCollections, ...runIdsFromFeed])]

    const changedWork = rereadAll ? [...this.work.keys()] : allWorkIds.filter((id) => this.work.has(id))
    const changedRuns = rereadAll ? [...this.runs.keys()] : allRunIds.filter((id) => this.runs.has(id))

    const collSet = new Set(ch.collections ?? [])
    const jobs: Promise<unknown>[] = []
    if (posts.length) jobs.push(this.loadPosts(posts, true))
    if (convs.length) jobs.push(this.loadConversations(convs))
    if ((this.list !== null || this.hasListener('coll:conversations')) && (convs.length || rereadAll || collSet.has('conversations'))) jobs.push(this.loadList())
    /* A Topic's posts (A8) move with its conversation: read again whenever
       the conversation is named, or everything is. */
    for (const k of this.collections.keys()) {
      if (!k.startsWith('topic:')) continue
      const [, c, t] = k.split(':')
      if (rereadAll || chConvs.includes(c)) jobs.push(this.loadTopic(c, t, true))
    }
    for (const k of keys) {
      if (k.startsWith('conversation:')) jobs.push(this.loadConversation(k.slice('conversation:'.length), true))
      else if (k.startsWith('thread:')) jobs.push(this.loadThread(k.slice('thread:'.length), true))
      else if (k === 'stream') jobs.push(this.loadStream(true))
      else if (k === 'selection') jobs.push(this.loadSelection())
    }
    if ((this.collections.has('stream') || this.hasListener('coll:stream')) && (rereadAll || collSet.has('stream')) && !keys.includes('stream')) {
      jobs.push(this.loadStream(true))
    }
    if ((this.collections.has('selection') || this.hasListener('coll:selection')) && (rereadAll || (posts.length > 0 && [...this.selected].some((id) => posts.includes(id)))) && !keys.includes('selection')) {
      jobs.push(this.loadSelection())
    }
    if (changedWork.length) jobs.push(this.loadWork(changedWork, true))
    if (changedRuns.length) jobs.push(this.loadRuns(changedRuns, true))

    /* HOME IS READ AGAIN ONLY WHILE A ZONE SHOWS IT. Holding a Home answer
       used to be enough: once Home had been opened, every change naming
       `home:work` re-read every state ever shown, in every tab, for the rest
       of the session -- 3.3 s of server work per read on the live Brain
       (2026-10-27: 1,919 requests projected each time), on every record move
       while agents worked, with nobody looking. Each zone reads its own
       collection when it mounts (Home.tsx), so what nothing shows is let go
       rather than kept stale. */
    this.dropUnshownHome()
    if (rereadAll || collSet.has('home:needs-you')) {
      if (this.hasListener('coll:home:needs-you')) {
        jobs.push(this.loadHomeNeedsYou())
      }
    }
    /* What needs you on a post moves exactly when Home's Needs you may (#576). */
    if (rereadAll || collSet.has('home:needs-you')) jobs.push(this.needsYouChanged())
    /* The bell's items move exactly when Needs you may (P11). */
    if ((rereadAll || collSet.has('home:needs-you')) && (this.needsItems !== null || this.hasListener('needs-items'))) {
      jobs.push(this.loadNeedsItems())
    }
    if (rereadAll || collSet.has('home:work')) {
      const states = [...this.homeWork.keys()]
      if (!states.length && this.hasListener('coll:home:work')) states.push('all')
      for (const st of states) {
        jobs.push(this.loadHomeWork(st as any))
      }
    }
    if (rereadAll || collSet.has('home:activity')) {
      if (this.hasListener('coll:home:activity')) {
        jobs.push(this.loadHomeActivity())
      }
    }
    if (rereadAll || collSet.has('home:briefing')) {
      if (this.hasListener('coll:home:briefing')) {
        jobs.push(this.loadHomeBriefing(this.pickedBriefingPeriod ?? undefined))
      }
    }
    if (rereadAll || collSet.has('home:for-you')) {
      if (this.hasListener('coll:home:for-you')) {
        jobs.push(this.loadHomeForYou())
      }
    }
    const versions = new Map<Id, Id | null>((ch.posts ?? []).map((p) => [p.id, p.version]))
    const named = new Set((ch.collections ?? []).filter((k) => k.startsWith('objects:')).map((k) => k.slice('objects:'.length)))
    jobs.push(this.objectsChanged(versions, named, rereadAll, threads))
    // Every read settles before the step does, so none outlives it into the next.
    const failed = (await Promise.allSettled(jobs)).find((r) => r.status === 'rejected')
    if (failed) throw (failed as PromiseRejectedResult).reason
    /* A post's annotations (`anchors:<post>`) are held by whoever reads them
       (conversation/annotated.ts): told, never read here. */
    const anchorKeys = rereadAll ? [...this.listeners.keys()].filter((k) => k.startsWith('anchors:'))
      : (ch.collections ?? []).filter((k) => k.startsWith('anchors:'))
    for (const k of anchorKeys) this.notify(k)
    this.cursor = ch.cursor
  }

  /* -- commands (F3) ---------------------------------------------------- */

  me: Id | null = null
  /** this Brain's owner, as the server names it (`me` of the participants
   *  read is `owner_of`); null where it names none -- never the fallback
   *  participant `me` falls back to */
  owner: Id | null = null

  async loadMe(): Promise<Id> {
    if (this.me) return this.me
    const got = await get<{ participants: { id: Id }[]; me: Id | null }>('participants?limit=1')
    this.owner = got.me ?? null
    const found = got.me ?? got.participants[0]?.id ?? null
    if (!found) throw new Error('No current participant found')
    this.me = found
    return this.me
  }

  async createConversation(author: Id, op?: string, name?: string): Promise<{ conversation: Id; name: string; provisional: boolean; projection: Conversation | null; cursor: string }> {
    const body: { author: Id; name?: string; op: string } = { author, op: op ?? newOp() }
    if (name !== undefined) body.name = name
    const res = await fluidFetch('/fluid/api/conversations', {
      method: 'POST',
      headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const got = await res.json().catch(() => null)
    if (!res.ok || !got || got.error) {
      const err = new Error(got?.error ?? res.statusText) as any
      if (got) Object.assign(err, got)
      err.status = res.status
      err.serverAnswer = true
      throw err
    }
    if (got.projection) this.putConversations([got.projection])
    if (this.list) void this.loadList()
    return got
  }

  async renameConversation(conversation: Id, author: Id, name: string, op?: string): Promise<{ conversation: Id; name: string; provisional: boolean; cursor: string }> {
    const body = { author, name, op: op ?? newOp() }
    const res = await fluidFetch(`/fluid/api/conversations/${encodeURIComponent(conversation)}/name`, {
      method: 'POST',
      headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const got = await res.json().catch(() => null)
    if (!res.ok || !got || got.error) {
      const err = new Error(got?.error ?? res.statusText) as any
      if (got) Object.assign(err, got)
      err.status = res.status
      err.serverAnswer = true
      throw err
    }
    if (got.projection) this.putConversations([got.projection])
    if (this.list) void this.loadList()
    return got
  }

  async groupConversations(author: Id, posts: Id[], name?: string, op?: string): Promise<{ conversation: Id; name: string; provisional: boolean; projection: Conversation | null; included: GroupIncludedItem[]; cursor: string }> {
    const body: { author: Id; posts: Id[]; name?: string; op: string } = { author, posts, op: op ?? newOp() }
    if (name !== undefined) body.name = name
    const res = await fluidFetch('/fluid/api/conversations/group', {
      method: 'POST',
      headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const got = await res.json().catch(() => null)
    if (!res.ok || !got || got.error) {
      const err = new Error(got?.error ?? res.statusText) as any
      if (got) Object.assign(err, got)
      err.status = res.status
      err.serverAnswer = true
      throw err
    }
    if (got.projection) this.putConversations([got.projection])
    if (this.list) void this.loadList()
    return got
  }

  async modifyMembers(
    conversation: Id,
    author: Id,
    add?: Id[],
    end?: Id[],
    op?: string,
  ): Promise<{ conversation: Id; added: MemberAddedItem[]; ended: MemberEndedItem[]; refused: MemberRefusedItem[]; cursor: string }> {
    const body: { author: Id; add?: Id[]; end?: Id[]; op: string } = { author, op: op ?? newOp() }
    if (add && add.length) body.add = add
    if (end && end.length) body.end = end
    const res = await fluidFetch(`/fluid/api/conversations/${encodeURIComponent(conversation)}/members`, {
      method: 'POST',
      headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const got = await res.json().catch(() => null)
    if (!res.ok || !got || got.error) {
      const err = new Error(got?.error ?? res.statusText) as any
      if (got) Object.assign(err, got)
      err.status = res.status
      err.serverAnswer = true
      throw err
    }
    if (got.projection) this.putConversations([got.projection])
    for (const raw of got.posts ?? []) {
      if (raw.error) continue
      const post = this.postShown(raw)
      const had = this.posts.get(post.id)
      if (had && JSON.stringify(had) === JSON.stringify(post)) continue
      this.posts.set(post.id, post)
      this.notify('post:' + post.id)
    }
    const reread = async () => {
      await Promise.all([
        this.loadConversation(conversation, true),
        this.loadConversations([conversation]),
      ])
      if (this.list) void this.loadList()
    }
    try {
      await reread()
    } catch {
      // opr-5307744bbd68: after a 200, a failed reread must not show Failed to fetch nor keep the op key:
      // report the action done and retry the reread.
      setTimeout(() => {
        void reread().catch(() => {})
      }, 500)
    }
    return got
  }

  /** ADDRESS A POST ALREADY WRITTEN (A5a), through Fluid's existing command
   *  (`POST /fluid/api/posts/<id>/address`, the shared operation production's
   *  TurnActions uses): `participant` is asked to respond to it, `because` is
   *  the sender's note. One operation key per request, so a retry after a
   *  lost answer is answered with what was done. The post is read again for
   *  the request it now carries. */
  async addressPost(post: Id, participant: Id, by: Id, because: string | null, op: string): Promise<{ dispatched: number; expectation?: Id }> {
    const res = await fluidFetch(`/fluid/api/posts/${encodeURIComponent(post)}/address`, {
      method: 'POST',
      headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
      body: JSON.stringify({ participant, by, because, action: 'ask-participant', op }),
    })
    const got = await res.json().catch(() => null)
    if (!res.ok || !got || got.error) {
      const err = new Error(got?.error ?? res.statusText) as any
      if (got) Object.assign(err, got)
      err.status = res.status
      err.serverAnswer = true
      throw err
    }
    await this.loadPosts([post], true).catch(() => {})
    return got
  }

  /* -- a conversation's Topic (A8) ----------------------------------------
     The posts filed under one Topic of a conversation, by the conversation
     collection's additive `topic` parameter: its own collection, held under
     `topic:<conversation>:<topic>` beside the conversation's, so the two
     never write over each other. Read again whenever the conversation is. */

  loadTopic(conversation: Id, topic: Id, keepWidth = false) {
    const key = topicKey(conversation, topic)
    const path = `collections/conversation?id=${encodeURIComponent(conversation)}&topic=${encodeURIComponent(topic)}`
    return this.serial(key, async () => {
      const held = this.collections.get(key)
      if (keepWidth && held) return this.rereadHeld(path, held)
      const got = await get<Collection>(`${path}&limit=${PAGE}`)
      await this.loadPosts(got.items.map((i) => i.id))
      this.setCollection({ ...got, key })
    })
  }

  olderOfTopic(conversation: Id, topic: Id) {
    const key = topicKey(conversation, topic)
    return this.serial(key, async () => {
      const held = this.collections.get(key)
      if (!held?.before) return
      const got = await get<Collection>(`collections/conversation?id=${encodeURIComponent(conversation)}&topic=${encodeURIComponent(topic)}&limit=${PAGE}&before=${encodeURIComponent(held.before)}`)
      await this.loadPosts(got.items.map((i) => i.id))
      this.setCollection({ ...held, items: [...got.items, ...held.items], older: got.older, before: got.before })
    })
  }

  /* -- home, work, and arrangements (F4) -------------------------------- */

  async loadWork(ids: Id[], force = false): Promise<WorkItem[]> {
    if (!ids.length) return []
    const want = force ? ids : ids.filter((id) => !this.work.has(id))
    for (const chunk of chunks(want, BATCH)) {
      const got = await get<{ work: WorkItem[] }>('work?ids=' + chunk.map(encodeURIComponent).join(','))
      for (const w of got.work ?? []) {
        this.work.set(w.id, { ...w, conversation_name: this.nameShown(w.conversation, w.conversation_name) })
        this.notify('work:' + w.id)
      }
    }
    return ids.map((id) => this.work.get(id)!).filter(Boolean)
  }

  async loadRuns(ids: Id[], force = false): Promise<RunItem[]> {
    if (!ids.length) return []
    const want = force ? ids : ids.filter((id) => !this.runs.has(id))
    for (const chunk of chunks(want, BATCH)) {
      const got = await get<{ runs: RunItem[] }>('runs?ids=' + chunk.map(encodeURIComponent).join(','))
      for (const r of got.runs ?? []) {
        this.runs.set(r.id, r)
        this.notify('run:' + r.id)
      }
    }
    return ids.map((id) => this.runs.get(id)!).filter(Boolean)
  }

  async loadHomeNeedsYou(before?: string, limit?: number): Promise<HomeCollectionData> {
    const q = new URLSearchParams()
    if (before) q.set('before', before)
    if (limit) q.set('limit', String(limit))
    const qs = q.toString()
    const got = await get<HomeCollectionData>('home/needs-you' + (qs ? '?' + qs : ''))
    this.homeNeedsYou = got
    if (got.items && got.items.length) {
      await this.loadWork(got.items)
    }
    this.notify('coll:home:needs-you')
    return got
  }

  /* -- what needs you on a post (#576) ------------------------------------ */

  private putAsks(rows: Ask[]) {
    for (const a of rows) {
      if (a.error) continue
      this.asks.set(a.id, { ...a, conversation_name: this.nameShown(a.conversation, a.conversation_name) })
      this.notify('ask:' + a.id)
    }
  }

  async loadNeedsYouOn(post: Id): Promise<NeedsYouOn> {
    const got = await get<NeedsYouOn & { asks: Ask[] }>('needs-you?post=' + encodeURIComponent(post))
    this.putAsks(got.asks ?? [])
    const { asks: _rows, ...on } = got
    this.needsYouOn.set(post, on)
    this.notify('needs-you:' + post)
    return on
  }

  /** What needs you, one item per form (P11, `needs-you/items`). */
  async loadNeedsItems(): Promise<NeedsItems> {
    const got = await get<NeedsItems>('needs-you/items')
    this.needsItems = got
    this.notify('needs-items')
    return got
  }

  async loadAsks(ids: Id[]): Promise<void> {
    for (const chunk of chunks(ids, BATCH)) {
      const got = await get<{ asks: Ask[] }>('needs-you?ids=' + chunk.map(encodeURIComponent).join(','))
      this.putAsks(got.asks ?? [])
    }
  }

  /** Read again what a zone shows of it; what nothing shows is dropped. */
  private async needsYouChanged() {
    /* WHAT IS SHOWN IS READ FIRST, then what each post asks: a zone keeps a
       card that left a post's list only once its request reads closed, so
       a request read closed after its post's list was read again would
       already be gone from the zone, with nothing to say what became of it
       (P11: Done in the zone, which reads nothing back itself). */
    const kept = [...this.asks.keys()].filter((id) => this.hasListener('ask:' + id))
    if (kept.length) await this.loadAsks(kept)
    const jobs: Promise<unknown>[] = []
    for (const post of [...this.needsYouOn.keys()]) {
      if (this.hasListener('needs-you:' + post)) jobs.push(this.loadNeedsYouOn(post))
      else this.needsYouOn.delete(post)
    }
    await Promise.all(jobs)
  }

  async loadHomeWork(
    state: 'all' | 'needs-you' | 'in-flight' | 'completed' | 'ended' = 'all',
    before?: string,
    limit?: number,
  ): Promise<HomeWorkData> {
    const q = new URLSearchParams()
    if (state) q.set('state', state)
    if (before) q.set('before', before)
    if (limit) q.set('limit', String(limit))
    const qs = q.toString()
    const got = await get<HomeWorkData>('home/work' + (qs ? '?' + qs : ''))
    this.homeWork.set(state, got)
    if (got.items && got.items.length) {
      await this.loadWork(got.items)
    }
    this.notify('coll:home:work')
    this.notify('coll:home:work:' + state)
    return got
  }

  async loadHomeActivity(): Promise<{ items: Id[]; cursor: string }> {
    const got = await get<{ items: Id[]; cursor: string }>('home/activity')
    this.homeActivity = got
    if (got.items && got.items.length) {
      await this.loadRuns(got.items)
    }
    this.notify('coll:home:activity')
    return got
  }

  async loadHomeBriefing(
    period?: 'morning' | 'lunch' | 'evening',
    date?: string,
  ): Promise<BriefingData> {
    const q = new URLSearchParams()
    if (period) {
      q.set('period', period)
      this.pickedBriefingPeriod = period
    } else {
      this.pickedBriefingPeriod = null
    }
    if (date) q.set('date', date)
    const qs = q.toString()
    const got = await get<BriefingData>('home/briefing' + (qs ? '?' + qs : ''))
    this.briefing = got
    this.notify('coll:home:briefing')
    return got
  }

  async loadHomeForYou(before?: string, limit?: number): Promise<HomeCollectionData> {
    const q = new URLSearchParams()
    if (before) q.set('before', before)
    if (limit) q.set('limit', String(limit))
    const qs = q.toString()
    const got = await get<HomeCollectionData>('home/for-you' + (qs ? '?' + qs : ''))
    this.homeForYou = got
    if (got.items && got.items.length) {
      await this.loadPosts(got.items)
    }
    this.notify('coll:home:for-you')
    return got
  }

  async loadArrangement(key: string): Promise<any> {
    const got = await get<{ layout: any }>(`arrangements/${encodeURIComponent(key)}`).catch(() => null)
    const layout = got ? got.layout : null
    this.arrangements.set(key, layout)
    this.notify('arrangement:' + key)
    return layout
  }

  async saveArrangement(key: string, layout: any, op?: string): Promise<any> {
    const body = { layout, op: op ?? newOp() }
    const res = await fluidFetch(`/fluid/api/arrangements/${encodeURIComponent(key)}`, {
      method: 'POST',
      headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const got = await res.json().catch(() => null)
    if (!res.ok || !got || got.error) {
      const err = new Error(got?.error ?? res.statusText) as any
      if (got) Object.assign(err, got)
      err.status = res.status
      err.serverAnswer = true
      throw err
    }
    this.arrangements.set(key, layout)
    this.notify('arrangement:' + key)
    return got
  }

  private stopFollowing: (() => void) | null = null

  /** Follow durable movement reported by Fluid's one pulse loop. A successful
   * pulse also provides the stale fallback, so `/changes` is not polled on a
   * second 1.2-second clock. */
  follow(_everyMs = 1200) {
    if (this.stopFollowing !== null) return
    let busy = false
    let again = false
    let lastStep = 0
    const staleMs = 30000
    const tick = async () => {
      if (document.hidden) return
      if (busy) { again = true; return }
      busy = true
      try {
        await this.step()
        lastStep = Date.now()
        if (this.feedError) {
          this.feedError = null
          this.notify('error')
        }
      } catch (e) {
        this.feedError = String((e as Error).message ?? e)
        this.notify('error')
      } finally {
        busy = false
        if (again) { again = false; void tick() }
      }
    }
    const stopMove = hearPulse((m) => { if (m === 'durable') void tick() })
    const stopBeat = hearPulseBeat(() => {
      if (!lastStep || Date.now() - lastStep >= staleMs) void tick()
    })
    this.stopFollowing = () => { stopMove(); stopBeat(); this.stopFollowing = null }
  }
}

export const store = new Store()
