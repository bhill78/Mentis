/* REAL CONTENT, READ FROM THE BRAIN SERVING THIS PAGE.
 *
 * ONE STORE OF POSTS (round 2). A post or a reply is held once, by its id,
 * whichever presentation asked for it: the conversation's flow, a thread
 * expanded under its post, a thread entered in the reading column, or a
 * working surface. Each presentation reads the same entry; none copies it.
 * Replies are not a separate model: a reply is a post that answers another
 * (`replyTo`), and a thread is a post and the posts under it.
 *
 * Read only, except through Mentis's own posting and editing commands
 * (Fluid's `Composer`, `editPost`), which re-read what they changed.
 *
 * The adaptation is deliberately plain: a post's words are one Markdown
 * block, its pictures follow (two or more break out as a gallery), its other
 * files are its attachments, and a long post is drawn as an article. Its
 * anchors (annotations) are not part of the adaptation: the margin layer
 * (annotate/Margin.tsx) reads them live and places each one by alignment
 * against `sourceOfPost`, the post's stored words as its body draws them. */
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS, type Conversation, type Turn } from '../api'
import { formatSize, itemOf, returnedItemOf } from '../quiet/media/view'
import { hearPulse, type Moved, type Where } from '../fluid/identity/activity'
import { sourceOf, type Source } from '../fluid/conversation/annotated'
import { blocksOf, placedRef } from '../blocks'
import { POSTS, type Block, type Id, type Post } from './sample'
import { repairText } from './text'
import { factsOf, seedStatus } from './status/status'

/* -- the store ------------------------------------------------------------ */

const posts = new Map<Id, Post>()
let version = 0
const heard = new Set<() => void>()
const changed = () => { version++; heard.forEach((fn) => fn()) }

export function putPosts(ps: Post[]) { for (const p of ps) posts.set(p.id, p); changed() }
export const postOf = (id: Id) => posts.get(id)
/** Every post held from one conversation (latest.ts weighs them). */
export const heldIn = (conversation: Id): Post[] => [...posts.values()].filter((p) => p.real && p.conversation === conversation)
/** Re-renders the caller whenever any post is added or changed. */
const subscribe = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }
const snapshot = () => version
/* The third argument is the same snapshot: this store is the page's own and
   has no separate server state, and without it a view that reads posts cannot
   be rendered outside a browser at all (React requires a server snapshot). */
export const usePosts = () => useSyncExternalStore(subscribe, snapshot, snapshot)

/* The sample is held the same way, so its replies are threads like any. */
putPosts(POSTS)

const order = (a: Post, b: Post) => (a.number ?? 0) - (b.number ?? 0)

/** The posts that answer `id` directly, oldest first, as far as they are held. */
export function childrenOf(id: Id): Post[] {
  const p = posts.get(id)
  if (p?.replyIds) return p.replyIds.map((r) => posts.get(r)).filter((x): x is Post => !!x).sort(order)
  return [...posts.values()].filter((x) => x.replyTo === id)
}

/** How many posts are under `id`, whole: the record's count where it says,
 *  else those held. */
export function threadSize(id: Id): number {
  const p = posts.get(id)
  if (p?.threadCount !== undefined) return p.threadCount
  const walk = (x: Id): number => childrenOf(x).reduce((n, c) => n + 1 + walk(c.id), 0)
  return walk(id)
}

/* -- reading -------------------------------------------------------------- */

const ARTICLE_AT = 1200
const REFERENCE_PARTS = new Set(['topic', 'turn', 'conversation', 'acquired', 'object'])

const when = (at: number) => {
  const d = new Date(at * 1000)
  const today = new Date()
  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  return d.toDateString() === today.toDateString() ? `Today, ${time}` : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${time}`
}

/* -- the words a post's body draws, as a place in the stored text ----------
   An anchor's passage is an offset into one stored text part. The body draws
   the parts joined (text and inline references, as `raw` below), Markdown
   rendered, mis-decoded runs repaired and an opening heading lifted out as
   the title. Fluid's alignment (`surfaces/passage.ts`) walks the rendered
   words against a source string, so it is given the joined parts
   (`sourceOf`, with each text part's span) with what the body does not draw
   blanked to spaces, character for character: every offset stays the stored
   text's, and a blank is markup to the walk.
     - a repaired run: its repaired character, then spaces for the rest;
     - the lifted heading: all spaces.
   The margin (annotate/Margin.tsx) places marks with it; a selection is said
   as a passage with it (`passageOf(range, body, sourceOfPost(id))`). */
const sources = new Map<Id, Source>()

/** The post's stored words as its `.q2-body` draws them, for `drawnRange`
 *  and `passageOf`; null for a post not read from a Brain. */
export const sourceOfPost = (id: Id): Source | null => sources.get(id) ?? null

/** Each run of non-ASCII characters repaired in place, padded to its length. */
const repairInPlace = (s: string) => s.replace(/[^\u0000-\u007f]+/g, (run) => { // eslint-disable-line no-control-regex
  const fixed = repairText(run)
  return fixed.length < run.length ? fixed + ' '.repeat(run.length - fixed.length) : run
})

function bodySource(t: Turn, lifted: boolean): Source {
  const src = sourceOf({ parts: t.parts } as never)
  /* the body draws the text as written (renderable fences too), not the
     blanked form Fluid's card draws */
  let drawn = repairInPlace(src.text)
  if (lifted) {
    const lead = drawn.length - drawn.trimStart().length
    const m = /^#{1,2} +(.+)\n/.exec(drawn.slice(lead) + '\n')
    if (m) {
      const end = Math.min(drawn.length, lead + m[0].length)
      drawn = drawn.slice(0, lead) + ' '.repeat(end - lead) + drawn.slice(end)
    }
  }
  return { ...src, drawn }
}

/** A Turn, as Quiet draws a post. */
export function adapt(t: Turn, conversation: Id, topicName: (id: Id) => string | undefined): Post {
  /* WHAT THE AUTHOR TYPED, as the server's edit box reads it (versions.py
     `flow_text`): text parts and the characters of inline references, in
     order, joined as they stand. Kept as written for editing; the repair of
     mis-decoded characters is applied only to what is drawn. */
  /* A READ THAT IS MISSING AN OPTIONAL LIST IS STILL A READ. The server's own
     Turn view always carries `parts` and `topics`, but drawing a post is now
     done in more than one place (the reading column, a surface, a Magnet's
     card), and a thin or partial read must leave the post empty rather than
     throw -- a throw here takes down whatever the post is drawn inside. */
  const parts = Array.isArray(t.parts) ? t.parts : []
  const raw = parts.filter((p) => p.type === 'text' || REFERENCE_PARTS.has(p.type)).map((p) => p.text ?? '').join('')
  const text = repairText(raw).trim()
  const items = parts.filter((p) => p.type !== 'text').map((p) => itemOf(p)).filter((x) => x !== null)
  /* a post that opens with a heading has its title already */
  const head = /^#{1,2} +(.+)\n/.exec(text + '\n')
  const body = head ? text.slice(head[0].length).trim() : text
  /* AN ARTIFACT A RUN RETURNED (return_artifact), NOT WRITTEN INTO THE TURN
     as a part -- `returned_with`, read off the act that recorded the reply
     (mentis/web `__init__.py`), drawn in the same picture strip or file
     list a person's own attachments get. One already placed inline, on its
     own line as `![alt](adm-…)` or the bare id (blocks.ts `placedRef`), is
     not drawn twice: it already has its figure in the body. */
  const placedInline = new Set(
    blocksOf(body).flatMap((b) => (b.kind === 'para' ? [placedRef(b.text)?.id] : [])).filter((x): x is string => !!x))
  const returned = (t.returned_with ?? [])
    .map(returnedItemOf).filter((x): x is NonNullable<typeof x> => x !== null && !placedInline.has(x.ref))
  const allItems = [...items, ...returned]
  const pictures = allItems.filter((i) => i.kind === 'image').map((i) => ({ src: i.url, alt: i.alt, caption: i.name, item: i }))
  const files = allItems.filter((i) => i.kind !== 'image')
  const blocks: Block[] = []
  if (body) blocks.push({ kind: 'text', md: body })
  /* the words as the body draws them, for placing passages in them */
  sources.set(t.id, bodySource({ ...t, parts }, !!head))
  seedStatus(t.id, factsOf(t))
  if (pictures.length === 1) blocks.push({ kind: 'figure', image: pictures[0] })
  else if (pictures.length > 1) blocks.push({ kind: 'wide', images: pictures })
  return {
    id: t.id,
    /* an agent's post is written by a run (`<runtime>/<run>`); a person's is
       not, even when the request it answered named a runtime */
    by: { id: t.author, name: t.author_alias, agent: !!t.written_by && t.written_by.includes('/') },
    at: when(t.at),
    atTime: t.at,
    weight: text.length > ARTICLE_AT ? 'article' : 'brief',
    title: head?.[1],
    topics: (Array.isArray(t.topics) ? t.topics : []).map(topicName).filter((n): n is string => !!n),
    blocks,
    attachments: files.map((f) => ({ name: f.name, type: f.mediaType.split('/').pop()?.toUpperCase() || 'File', size: formatSize(f.size) ?? '', url: f.url, item: f })),
    replyTo: t.answering ?? undefined,
    replyNumber: t.answering_number ?? undefined,
    anchor: (parts.find((p) => p.type === 'anchor') as { ref?: string } | undefined)?.ref,
    /* who it addressed and what it asked, as read (status/status.ts
       composes its status from them, and reads them again as they move) */
    status: factsOf(t),
    number: t.number,
    conversation,
    replyIds: t.replies,
    root: t.root,
    threadCount: t.thread_replies,
    text: raw,
    real: true,
  }
}

/** Participants' names as the Brain gives them, from every conversation read. */
const names = new Map<Id, string>()
/** Topics' names by id, from every conversation read. */
const topicNames = new Map<Id, string>()

/** A participant's name as the Brain gives it (with its @), where read. */
export const nameOf = (id: Id): string | null => {
  const n = names.get(id)
  return n ? (n.startsWith('@') ? n : '@' + n) : null
}

const read = (url: string) => fetch(url, { headers: CLIENT_HEADERS })
  .then((r) => r.ok ? r.json() : Promise.reject(new Error(`${r.status} ${r.statusText}`)))
  /* a read the server refuses by name answers 200 with its reason: an error here */
  .then((j: unknown) => j && typeof j === 'object' && typeof (j as { error?: unknown }).error === 'string' ? Promise.reject(new Error((j as { error: string }).error)) : j)

/** The thread a post belongs to: the server names a reply's root when asked
 *  for the reply's thread. */
export async function threadRootOf(conversation: Id, post: Id): Promise<Id> {
  const r = await fetch(`/api/conversations/${encodeURIComponent(conversation)}/thread/${encodeURIComponent(post)}`, { headers: CLIENT_HEADERS })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  const j = await r.json().catch(() => null) as { root?: string; turn?: unknown; error?: string } | null
  /* a reply: the server names its root; a root: its own thread is answered */
  if (j?.root) return j.root
  if (j?.turn) return post
  throw new Error(j?.error ?? 'the thread could not be read')
}

interface FlowPart {
  name: string; total: number; top: Id[]; all: Id[]; topics: { id: Id; key: string; name: string; count: number }[]; participants: Conversation['participants']
  /** how many units (threads, or a topic's posts) the read stands in */
  units: number | null
  /** threads older than this batch, and where it begins (its first post's number) */
  older: number; first: number | null
}

/** The flow of a conversation: its latest threads (or those around one
 *  number), each post held in the store. */
export async function readFlow(conversation: Id, around?: number, topic?: Id): Promise<FlowPart> {
  /* a topic in force: the server's own read of that topic's posts */
  const c = await read(`/api/conversations/${encodeURIComponent(conversation)}?batch=${around ? 6 : 30}${around ? `&around=${around}` : ''}${topic ? `&topic=${encodeURIComponent(topic)}` : ''}`) as Conversation
  return flowOf(c, conversation)
}

/** The batch before post number `before`: older threads of the same flow. */
export async function readEarlier(conversation: Id, before: number, topic?: Id): Promise<FlowPart> {
  const c = await read(`/api/conversations/${encodeURIComponent(conversation)}?batch=30&before=${before}${topic ? `&topic=${encodeURIComponent(topic)}` : ''}`) as Conversation
  return flowOf(c, conversation)
}

function flowOf(c: Conversation, conversation: Id): FlowPart {
  for (const p of c.participants ?? []) names.set(p.participant, p.alias)
  for (const x of c.topics ?? []) topicNames.set(x.id, x.name)
  const adapted = (c.turns ?? []).filter(Boolean).map((t) => adapt(t, conversation, (id) => topicNames.get(id)))
  putPosts(adapted)
  const held = new Set(adapted.map((p) => p.id))
  /* a reply whose thread is in the flow belongs under it, not beside it */
  const top = (c.turns ?? []).filter(Boolean).filter((t) => !t.answering || !(t.root && t.root !== t.id && held.has(t.root))).map((t) => t.id)
  return {
    name: repairText(c.name), total: c.turns_total, top, all: adapted.map((p) => p.id),
    topics: (c.topics ?? []).map((x) => ({ id: x.id, key: x.name, name: x.name, count: x.turns })),
    participants: c.participants ?? [],
    units: c.batch?.units_total ?? null,
    older: c.batch?.older ?? 0,
    first: c.batch?.first ?? null,
  }
}

interface ThreadRead { conversation: Id; root: Id; turn: Turn; replies_total: number; replies: Turn[] }

/** A whole thread, every post in it held in the store. */
export async function readThread(conversation: Id, root: Id): Promise<void> {
  const t = await read(`/api/conversations/${encodeURIComponent(conversation)}/thread/${encodeURIComponent(root)}`) as ThreadRead
  putPosts([t.turn, ...(t.replies ?? [])].filter(Boolean).map((x) => adapt(x, conversation, (id) => topicNames.get(id))).map((p) => {
    /* the flow's read knows the topics' names; keep them where it had them */
    const had = posts.get(p.id)
    return had?.topics?.length && !p.topics?.length ? { ...p, topics: had.topics } : p
  }))
}

/* -- THE THREAD BEING READ FOLLOWS THE RECORD TOO -------------------------
   A thread entered in the reading column (or opened in a fold) is read by
   `readThread`, by its root, and was read exactly once: when its root
   changed. The flow's reread (below) carries every post of the LATEST batch
   of threads with it, so a reply inside a recent thread arrives with the
   flow -- but a thread whose root is older than that batch is in no batch
   the flow reads, and an agent's reply inside it was not drawn until the
   reader left the thread and came back (ent-4964f2340ef8).

   So the thread hears the same beat, on the same terms as the flow: the one
   pulse the page already runs (`hearPulse`), `flowMoved` for whether the
   move can have touched this conversation at all, and `FLOW_SPACING`
   between reads of it -- trailing, at most one read per thread on screen per
   window, nothing for a move that names other conversations or for live
   execution alone. No new poll and nothing that wakes on its own.

   The read is the same read, by root, so an older root is covered exactly as
   a recent one is, and the store holds each post once, by its id: a reply
   already read is not drawn twice and the thread's own composer and draft
   (Quiet2.tsx `Dock`) are untouched. */

/** WHETHER A READ IS A REREAD of the thread already shown, rather than the
 *  first read of this root: the pulse asked for it (`advance` moved) and the
 *  root has not changed. A first read says it is reading and owns its
 *  failure; a reread leaves what is already read standing -- nothing
 *  flickers out and back, and a reread that fails does not take the thread
 *  off the page. */
export const readingAgain = (was: { root: Id; advance: number } | null, root: Id, advance: number): boolean =>
  !!was && was.root === root && was.advance !== advance

/** Reads `root`'s thread once it is wanted (real posts only), and again when
 *  the pulse says this conversation's material moved. */
export function useThread(root: Id | null): { loading: boolean; error: string | null } {
  const [state, setState] = useState<{ loading: boolean; error: string | null }>({ loading: false, error: null })
  const p = root ? posts.get(root) : undefined
  const conversation = p?.real ? p.conversation : undefined
  /* THE RECORD MOVED HERE: one more read of this same thread. Counted, so a
     move while a read is in flight is not swallowed by it. */
  const [advance, setAdvance] = useState(0)
  /** when the last read of this thread began, for `FLOW_SPACING` */
  const began = useRef(0)
  /** what was last read here, so a reread is told from arriving */
  const was = useRef<{ root: Id; advance: number } | null>(null)
  useEffect(() => {
    if (!conversation || !root) return
    let owed: number | null = null
    const stop = hearPulse((m, where) => {
      if (!flowMoved(m, where, conversation) || owed !== null) return
      owed = window.setTimeout(() => { owed = null; setAdvance((n) => n + 1) }, spacedAfter(began.current))
    })
    /* the thread closed, another root entered, or the page left: the beat is
       let go and an owed read never runs */
    return () => { stop(); if (owed !== null) clearTimeout(owed) }
  }, [conversation, root])
  useEffect(() => {
    if (!conversation || !root) { was.current = null; return }
    let live = true
    const again = readingAgain(was.current, root, advance)
    was.current = { root, advance }
    if (!again) setState({ loading: true, error: null })
    began.current = Date.now()
    readThread(conversation, root).then(() => { if (live) setState({ loading: false, error: null }) })
      /* a reread that fails changes nothing: what was read is still true */
      .catch((e: unknown) => { if (live && !again) setState({ loading: false, error: String(e) }) })
    return () => { live = false }
  }, [conversation, root, advance])
  return state
}

/* -- what a page shows ---------------------------------------------------- */

export interface FlowRead {
  name: string
  total: number
  /** the top-level posts, in order; their replies are reached through them */
  top: Id[]
  topics: { id?: Id; key: string; name: string; count: number }[]
  participants: { id: Id; name: string }[]
  /** a topic's read: how many posts it has in all */
  units: number | null
  /** the topic this read is focused on, if any */
  topic: Id | null
  /** the conversation a composer writes to, where there is one */
  conversation: Id | null
  /** threads older than those read, and the number to read before */
  older: number
  first: number | null
}

/* THE LONG-FORM REEL: real posts chosen from the dev Brain for what they hold
   (found by scanning it, 2026-11-09). Each is read in place (`around` its
   number) with its neighbours, so its replies come with it. */
export const LONG_REEL: { conversation: string; number: number; why: string }[] = [
  { conversation: 'ent-cd0ddc9713a5', number: 702, why: 'a long technical post with ten substantial, nested agent replies' },
  { conversation: 'ent-98c0a097dbd9', number: 5, why: 'headings and fenced code' },
  { conversation: 'ent-cd0ddc9713a5', number: 916, why: 'a wide table' },
  { conversation: 'ent-cd0ddc9713a5', number: 792, why: 'twelve short replies' },
  { conversation: 'ent-aae5fb2dd737', number: 15, why: 'annotations' },
  { conversation: 'ent-0a1a163beb3a', number: 569, why: 'a table and fourteen pictures' },
  { conversation: 'ent-dca5ea664adf', number: 102, why: 'text the record holds mis-encoded' },
]

/* -- THE FLOW FOLLOWS THE RECORD ------------------------------------------
   An agent finishes a run and posts, and the conversation being read showed
   nothing of it until something else made the page read again -- another
   post by the reader, a rename, a switch, a reload (owner, 2026-11-17).
   The flow was read when it was opened and on `reread` alone; every other
   reader in the interface hears the record move on the pulse and reads its
   own path again.

   So it hears the same pulse, through the one beat Fluid already runs
   (identity/activity.ts `hearPulse`, `/api/pulse` every 1.2 s while
   something listens, nothing while the tab is hidden). No new poll, no
   stream, no second model of the record: the flow reads exactly what it
   always read, when the pulse says this conversation's material moved.

   WHAT IS NOT DONE HERE. Nothing wakes to look for work (AGENTS.md): the
   beat is the one the page already has, it runs only while a flow is on
   screen, and a move that names other conversations is not read at all. */

/** NO SOONER THAN THIS after the last read of this flow began. The pulse's
 *  durable half moves on every act of a working agent, and a conversation's
 *  read is not cheap; moves inside the window become exactly one read at its
 *  end -- trailing, so nothing is dropped. (`status.ts` spaces its own post
 *  reads the same way, and `api.ts`'s `rereadPlan` is the same decision for
 *  `useApi`'s readers.) */
export const FLOW_SPACING = 1500

/** WHEN A READ THE PULSE ASKED FOR RUNS: no sooner than `FLOW_SPACING` after
 *  the last read of that same path began, and at once where that is already
 *  past. The flow and the thread being read space themselves this way, each
 *  for its own path. */
export const spacedAfter = (began: number, now: number = Date.now()): number => Math.max(0, began + FLOW_SPACING - now)

/** WHETHER A PULSE MOVE CAN HAVE CHANGED THIS FLOW.
 *
 *  Only the record moving writes a post: the live half moving is execution
 *  the record has not heard about yet, and a run that merely ended wrote
 *  nothing here -- its final post is a durable move of its own, which is the
 *  owner's case ("after an agent finishes a run and posts").
 *
 *  Where the record moved only ever narrows what is certain (`mentis/web/
 *  moved.py`): no answer, or a `loose` one, is a yes, exactly as before. */
export function flowMoved(moved: Moved, where: Where | null, conversation: Id | null): boolean {
  if (moved !== 'durable' || !conversation) return false
  if (!where || where.loose) return true
  return where.conversations.includes(conversation)
}

/** WHAT A REREAD SHOWS: the batch just read, with whatever was already on
 *  screen above it kept in front.
 *
 *  A flow is the conversation's LATEST batch of threads. Reading it again
 *  answers the latest batch again -- which, once a post has been added, is
 *  not the same batch: its oldest thread has dropped off the end, and every
 *  expansion the reader asked for with Earlier posts is gone from it.
 *  Replacing what is shown with that would take words away from above where
 *  somebody is reading and move the page under them. So the ids already
 *  shown that the new batch does not name are kept, in their order, ahead of
 *  it -- being absent from the latest batch, they are older than it -- and
 *  how much is still older (`older`, `first`) stays as the earlier read left
 *  it. A kept post that has since become a reply under a root in the new
 *  batch goes under it rather than beside it, as reading earlier posts does. */
export function keepingEarlier(shown: FlowRead | null, got: FlowRead, held: (id: Id) => Post | undefined = postOf): FlowRead {
  if (!shown || shown.conversation !== got.conversation || shown.topic !== got.topic) return got
  const now = new Set(got.top)
  const front = shown.top.filter((x) => !now.has(x))
  const back = shown.first !== null && got.first !== null && shown.first < got.first
  if (!front.length) {
    return back ? { ...got, older: shown.older, first: shown.first } : got
  }
  const top = [...front, ...got.top]
  const tops = new Set(top)
  const under = (x: Id) => { const p = held(x); return !!(p?.replyTo && p.root && p.root !== x && tops.has(p.root)) }
  return {
    ...got,
    top: top.filter((x) => !under(x)),
    older: back ? shown.older : got.older,
    first: back ? shown.first : got.first,
    participants: [...new Map([...shown.participants, ...got.participants].map((p) => [p.id, p])).values()],
  }
}

/** A real conversation's latest posts (`conversation`), or the reel. A new
 *  `reread` reads it again (after a post), keeping what is shown meanwhile;
 *  it also reads again, by itself, when the pulse says this conversation's
 *  material moved (`flowMoved`), which is how an agent's post arrives. */
export function useRealFlow(mode: 'real' | 'long' | null, conversation: Id | null, reread = 0, around?: number, topic?: Id): { read: FlowRead | null; error: string | null; earlier: (() => Promise<void>) | null } {
  const [got, setGot] = useState<FlowRead | null>(null)
  /* a new conversation starts blank; a topic in force or lifted keeps the
     conversation shown while its read comes */
  const was = useRef<Id | null>(null)
  const [more, setMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /* THE RECORD MOVED HERE: one more read of this same flow. Counted, so a
     move while a read is in flight is not swallowed by it -- the read in
     flight is let go (`live`) and the flow is read again. */
  const [advance, setAdvance] = useState(0)
  /** when the last read of this flow began, for `FLOW_SPACING` */
  const began = useRef(0)
  /** what the flow shown was read as: a merge is only ever within one */
  const shape = useRef<string | null>(null)
  const asRead = `${mode ?? ''}|${conversation ?? ''}|${topic ?? ''}|${around ?? ''}`
  useEffect(() => {
    if (mode !== 'real' || !conversation) return
    let owed: number | null = null
    const stop = hearPulse((m, where) => {
      if (!flowMoved(m, where, conversation) || owed !== null) return
      owed = window.setTimeout(() => { owed = null; setAdvance((n) => n + 1) }, spacedAfter(began.current))
    })
    return () => { stop(); if (owed !== null) clearTimeout(owed) }
  }, [mode, conversation])
  useEffect(() => {
    if (!mode || (mode === 'real' && !conversation)) return
    let live = true
    if (was.current !== conversation) setGot(null)
    was.current = conversation
    began.current = Date.now()
    /* a read of the same conversation, topic and place keeps what is above it
       (`keepingEarlier`); any other read is its own flow and replaces it */
    const keep = mode === 'real' && shape.current === asRead
    shape.current = asRead
    setError(null)
    const people = (ps: Conversation['participants']) => ps.map((p) => ({ id: p.participant, name: p.alias }))
    const job: Promise<FlowRead> = mode === 'real'
      ? readFlow(conversation!, topic ? undefined : around, topic).then((f) => ({ ...f, participants: people(f.participants), conversation, topic: topic ?? null }))
      /* one entry that cannot be read leaves the others standing */
      : Promise.allSettled(LONG_REEL.map((r) => readFlow(r.conversation, r.number).then((f) => {
          /* found among everything read, not only the top: a reel entry may itself be a reply */
          const id = f.all.find((x) => postOf(x)?.number === r.number) ?? null
          if (id) putPosts([{ ...postOf(id)!, topics: [f.name] }])
          return { id, f }
        }))).then((settled) => settled.flatMap((x) => x.status === 'fulfilled' ? [x.value] : [])).then((all) => ({
          name: 'Long-form reel', total: all.filter((x) => x.id).length,
          top: all.map((x) => x.id).filter((x): x is Id => !!x),
          topics: [],
          participants: [...new Map(all.flatMap((x) => people(x.f.participants)).map((p) => [p.id, p])).values()],
          conversation: null, older: 0, first: null, units: null, topic: null,
        }))
    job.then((r) => { if (live) setGot((g) => (keep ? keepingEarlier(g, r) : r)) })
      .catch((e: unknown) => { if (live) setError(String(e)) })
    return () => { live = false }
  }, [mode, conversation, reread, around, topic, advance]) // eslint-disable-line react-hooks/exhaustive-deps
  /* EARLIER POSTS: the batch before the first read, put ahead of it */
  const earlier = mode === 'real' && conversation && got && got.topic === (topic ?? null) && got.older > 0 && got.first !== null && !more
    ? async () => {
        setMore(true)
        try {
          const f = await readEarlier(conversation, got.first!, got.topic ?? undefined)
          const known = new Set(got.top)
          setGot((g) => {
            if (!g || g.conversation !== conversation || g.topic !== got.topic) return g
            /* a reply shown alone (its root not read yet) goes under its root once that arrives */
            const top = [...f.top.filter((x) => !known.has(x)), ...g.top]
            const tops = new Set(top)
            const under = (x: Id) => { const p = postOf(x); return !!(p?.replyTo && p.root && p.root !== x && tops.has(p.root)) }
            return {
            ...g, top: top.filter((x) => !under(x)), older: f.older, first: f.first,
            participants: [...new Map([...g.participants, ...f.participants.map((p) => ({ id: p.participant, name: p.alias }))].map((p) => [p.id, p])).values()],
          } })
        } catch (e) { setError(`Could not read earlier posts: ${String(e)}`) } finally { setMore(false) }
      }
    : null
  return { read: got, error, earlier }
}
