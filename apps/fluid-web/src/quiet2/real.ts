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
 * files are its attachments, its anchors (annotations) sit in the margin
 * beside the passage they quote, and a long post is drawn as an article. */
import { useEffect, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS, type Conversation, type Turn } from '../api'
import { formatSize, itemOf } from '../quiet/media/view'
import { PEOPLE, POSTS, type Aside, type Block, type Id, type Post } from './sample'
import { repairText } from './text'

/* -- the store ------------------------------------------------------------ */

const posts = new Map<Id, Post>()
let version = 0
const heard = new Set<() => void>()
const changed = () => { version++; heard.forEach((fn) => fn()) }

export function putPosts(ps: Post[]) { for (const p of ps) posts.set(p.id, p); changed() }
export const postOf = (id: Id) => posts.get(id)
/** Re-renders the caller whenever any post is added or changed. */
const subscribe = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }
const snapshot = () => version
export const usePosts = () => useSyncExternalStore(subscribe, snapshot)

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

const firstLine = (s: string, n = 72) => { const l = s.split('\n').find((x) => x.trim()) ?? ''; return l.length > n ? l.slice(0, n - 1) + '…' : l }

/** A Turn, as Quiet draws a post. */
export function adapt(t: Turn, conversation: Id, topicName: (id: Id) => string | undefined): Post {
  /* WHAT THE AUTHOR TYPED, as the server's edit box reads it (versions.py
     `flow_text`): text parts and the characters of inline references, in
     order, joined as they stand. Kept as written for editing; the repair of
     mis-decoded characters is applied only to what is drawn. */
  const raw = t.parts.filter((p) => p.type === 'text' || REFERENCE_PARTS.has(p.type)).map((p) => p.text ?? '').join('')
  const text = repairText(raw).trim()
  const items = t.parts.filter((p) => p.type !== 'text').map((p) => itemOf(p)).filter((x) => x !== null)
  const pictures = items.filter((i) => i.kind === 'image').map((i) => ({ src: i.url, alt: i.alt, caption: i.name, item: i }))
  const files = items.filter((i) => i.kind !== 'image')
  /* a post that opens with a heading has its title already */
  const head = /^#{1,2} +(.+)\n/.exec(text + '\n')
  const body = head ? text.slice(head[0].length).trim() : text
  const blocks: Block[] = []
  if (body) blocks.push({ kind: 'text', md: body })
  /* ANNOTATIONS sit beside the paragraph they quote: the body is split at
     paragraph breaks so each anchor can find its own passage */
  const anchors = (t.anchors ?? []).filter((a) => !a.deleted)
  if (anchors.length && body) {
    blocks.length = 0
    let open: string[] = []
    const placed = new Set<string>()
    const flush = (asides?: Aside[]) => { if (open.length) blocks.push({ kind: 'text', md: open.join('\n\n'), ...(asides?.length ? { asides } : {}) }); open = [] }
    for (const para of body.split(/\n{2,}/)) {
      open.push(para)
      const here = anchors.filter((a) => !placed.has(a.anchor) && a.excerpt && para.includes(repairText(a.excerpt).slice(0, 40)))
      /* fenced code is never split: keep reading until its fence closes */
      const fences = (open.join('\n\n').match(/^\s*```/gm) ?? []).length
      if (here.length && fences % 2 === 0) { here.forEach((a) => placed.add(a.anchor)); flush(here.map(annotationOf)) }
    }
    flush()
    /* an anchor whose passage cannot be found still sits beside the post */
    const lost = anchors.filter((a) => !placed.has(a.anchor)).map(annotationOf)
    if (lost.length && blocks[0]?.kind === 'text') blocks[0] = { ...blocks[0], asides: [...(blocks[0].asides ?? []), ...lost] }
  }
  if (pictures.length === 1) blocks.push({ kind: 'figure', image: pictures[0] })
  else if (pictures.length > 1) blocks.push({ kind: 'wide', images: pictures })
  return {
    id: t.id,
    /* an agent's post is written by a run (`<runtime>/<run>`); a person's is
       not, even when the request it answered named a runtime */
    by: { id: t.author, name: t.author_alias, agent: !!t.written_by && t.written_by.includes('/') },
    at: when(t.at),
    weight: text.length > ARTICLE_AT ? 'article' : 'brief',
    title: head?.[1],
    topics: t.topics.map(topicName).filter((n): n is string => !!n),
    blocks,
    attachments: files.map((f) => ({ name: f.name, type: f.mediaType.split('/').pop()?.toUpperCase() || 'File', size: formatSize(f.size) ?? '', url: f.url, item: f })),
    replyTo: t.answering ?? undefined,
    replyNumber: t.answering_number ?? undefined,
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

function annotationOf(a: NonNullable<Turn['anchors']>[number]): Aside {
  const said = [
    a.replies.length ? `${a.replies.length} comment${a.replies.length === 1 ? '' : 's'}` : null,
    a.reactions.length ? a.reactions.map((r) => `${r.token} ${r.count}`).join(' ') : null,
    a.deep_dives.length ? `${a.deep_dives.length} deep dive${a.deep_dives.length === 1 ? '' : 's'}` : null,
  ].filter(Boolean).join(' · ')
  const sample = Object.values(PEOPLE).find((p) => p.id === a.by)
  const alias = names.get(a.by)
  return {
    kind: 'annotation',
    by: sample ?? { id: a.by, name: alias ? (alias.startsWith('@') ? alias : '@' + alias) : '@someone', agent: false },
    at: when(a.at),
    text: `“${firstLine(repairText(a.excerpt ?? ''), 90)}”${said ? ` — ${said}` : ''}`,
  }
}

const read = (url: string) => fetch(url, { headers: CLIENT_HEADERS })
  .then((r) => r.ok ? r.json() : Promise.reject(new Error(`${r.status} ${r.statusText}`)))

interface FlowPart {
  name: string; total: number; top: Id[]; all: Id[]; topics: { key: string; name: string; count: number }[]; participants: Conversation['participants']
  /** threads older than this batch, and where it begins (its first post's number) */
  older: number; first: number | null
}

/** The flow of a conversation: its latest threads (or those around one
 *  number), each post held in the store. */
export async function readFlow(conversation: Id, around?: number): Promise<FlowPart> {
  const c = await read(`/api/conversations/${encodeURIComponent(conversation)}?batch=${around ? 6 : 30}${around ? `&around=${around}` : ''}`) as Conversation
  return flowOf(c, conversation)
}

/** The batch before post number `before`: older threads of the same flow. */
export async function readEarlier(conversation: Id, before: number): Promise<FlowPart> {
  const c = await read(`/api/conversations/${encodeURIComponent(conversation)}?batch=30&before=${before}`) as Conversation
  return flowOf(c, conversation)
}

function flowOf(c: Conversation, conversation: Id): FlowPart {
  for (const p of c.participants) names.set(p.participant, p.alias)
  const topicNames = new Map(c.topics.map((x) => [x.id, x.name]))
  const adapted = c.turns.map((t) => adapt(t, conversation, (id) => topicNames.get(id)))
  putPosts(adapted)
  const held = new Set(adapted.map((p) => p.id))
  /* a reply whose thread is in the flow belongs under it, not beside it */
  const top = c.turns.filter((t) => !t.answering || !(t.root && t.root !== t.id && held.has(t.root))).map((t) => t.id)
  return {
    name: repairText(c.name), total: c.turns_total, top, all: adapted.map((p) => p.id),
    topics: c.topics.map((x) => ({ key: x.name, name: x.name, count: x.turns })),
    participants: c.participants,
    older: c.batch?.older ?? 0,
    first: c.batch?.first ?? null,
  }
}

interface ThreadRead { conversation: Id; root: Id; turn: Turn; replies_total: number; replies: Turn[] }

/** A whole thread, every post in it held in the store. */
export async function readThread(conversation: Id, root: Id): Promise<void> {
  const t = await read(`/api/conversations/${encodeURIComponent(conversation)}/thread/${encodeURIComponent(root)}`) as ThreadRead
  putPosts([t.turn, ...t.replies].map((x) => adapt(x, conversation, () => undefined)).map((p) => {
    /* the flow's read knows the topics' names; keep them where it had them */
    const had = posts.get(p.id)
    return had?.topics?.length && !p.topics?.length ? { ...p, topics: had.topics } : p
  }))
}

/** Reads `root`'s thread once it is wanted (real posts only). */
export function useThread(root: Id | null): { loading: boolean; error: string | null } {
  const [state, setState] = useState<{ loading: boolean; error: string | null }>({ loading: false, error: null })
  const p = root ? posts.get(root) : undefined
  const conversation = p?.real ? p.conversation : undefined
  useEffect(() => {
    if (!conversation || !root) return
    let live = true
    setState({ loading: true, error: null })
    readThread(conversation, root).then(() => { if (live) setState({ loading: false, error: null }) })
      .catch((e: unknown) => { if (live) setState({ loading: false, error: String(e) }) })
    return () => { live = false }
  }, [conversation, root])
  return state
}

/* -- what a page shows ---------------------------------------------------- */

export interface FlowRead {
  name: string
  total: number
  /** the top-level posts, in order; their replies are reached through them */
  top: Id[]
  topics: { key: string; name: string; count: number }[]
  participants: { id: Id; name: string }[]
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

/** A real conversation's latest posts (`conversation`), or the reel. A new
 *  `reread` reads it again (after a post), keeping what is shown meanwhile. */
export function useRealFlow(mode: 'real' | 'long' | null, conversation: Id | null, reread = 0, around?: number): { read: FlowRead | null; error: string | null; earlier: (() => Promise<void>) | null } {
  const [got, setGot] = useState<FlowRead | null>(null)
  const [more, setMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!mode || (mode === 'real' && !conversation)) return
    let live = true
    if (!reread) setGot(null)
    setError(null)
    const people = (ps: Conversation['participants']) => ps.map((p) => ({ id: p.participant, name: p.alias }))
    const job: Promise<FlowRead> = mode === 'real'
      ? readFlow(conversation!, around).then((f) => ({ ...f, participants: people(f.participants), conversation }))
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
          conversation: null, older: 0, first: null,
        }))
    job.then((r) => { if (live) setGot(r) }).catch((e: unknown) => { if (live) setError(String(e)) })
    return () => { live = false }
  }, [mode, conversation, reread, around])
  /* EARLIER POSTS: the batch before the first read, put ahead of it */
  const earlier = mode === 'real' && conversation && got && got.older > 0 && got.first !== null && !more
    ? async () => {
        setMore(true)
        try {
          const f = await readEarlier(conversation, got.first!)
          const known = new Set(got.top)
          setGot((g) => g && g.conversation === conversation ? {
            ...g, top: [...f.top.filter((x) => !known.has(x)), ...g.top], older: f.older, first: f.first,
            participants: [...new Map([...g.participants, ...f.participants.map((p) => ({ id: p.participant, name: p.alias }))].map((p) => [p.id, p])).values()],
          } : g)
        } catch (e) { setError(`Could not read earlier posts: ${String(e)}`) } finally { setMore(false) }
      }
    : null
  return { read: got, error, earlier }
}
