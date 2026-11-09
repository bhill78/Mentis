/* REAL CONTENT, READ FROM THE BRAIN SERVING THIS PAGE (round 1 corrections).
 *
 * To judge the reading measure against what Mentis conversations actually
 * hold -- long agent reports, lists, code, tables, pictures, files -- a real
 * conversation's latest posts are drawn with the same editorial post as the
 * sample. Read only: nothing here writes. The adaptation is deliberately
 * plain: a post's words are one Markdown block, its pictures follow it (two
 * or more break out as a gallery), its other files are its attachments, and
 * a long post is drawn as an article. Real posts carry no titles, topics are
 * the conversation's own names. */
import { useEffect, useState } from 'react'
import { CLIENT_HEADERS, type Conversation, type Turn } from '../api'
import { formatSize, itemOf } from '../quiet/media/view'
import type { Block, Post } from './sample'

/** Words beyond this make a post an article rather than a reply. */
const ARTICLE_AT = 1200

const when = (at: number) => {
  const d = new Date(at * 1000)
  const today = new Date()
  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  return d.toDateString() === today.toDateString() ? `Today, ${time}` : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${time}`
}

export function postOf(t: Turn, topicName: (id: string) => string | undefined): Post {
  const text = t.parts.filter((p) => p.type === 'text').map((p) => p.text ?? '').join('\n\n').trim()
  const items = t.parts.filter((p) => p.type !== 'text').map((p) => itemOf(p)).filter((x) => x !== null)
  const pictures = items.filter((i) => i.kind === 'image').map((i) => ({ src: i.url, alt: i.alt, caption: i.name }))
  const files = items.filter((i) => i.kind !== 'image')
  /* a post that opens with a heading has its title already */
  const head = /^#{1,2} +(.+)\n/.exec(text + '\n')
  const body = head ? text.slice(head[0].length).trim() : text
  const blocks: Block[] = []
  if (body) blocks.push({ kind: 'text', md: body })
  if (pictures.length === 1) blocks.push({ kind: 'figure', image: pictures[0] })
  else if (pictures.length > 1) blocks.push({ kind: 'wide', images: pictures })
  return {
    id: t.id,
    by: { id: t.author, name: t.author_alias, agent: !!t.runtime },
    at: when(t.at),
    weight: text.length > ARTICLE_AT ? 'article' : 'brief',
    title: head?.[1],
    topics: t.topics.map(topicName).filter((n): n is string => !!n),
    blocks,
    attachments: files.map((f) => ({ name: f.name, type: f.mediaType.split('/').pop()?.toUpperCase() || 'File', size: formatSize(f.size) ?? '', url: f.url })),
    replyTo: t.answering ?? undefined,
    replyNumber: t.answering_number ?? undefined,
    number: t.number,
  }
}

export interface RealRead {
  name: string
  total: number
  posts: Post[]
  topics: { key: string; name: string; count: number }[]
}

/** The latest posts of `conversation`, adapted; null while reading. */
export function useRealConversation(conversation: string | null): { read: RealRead | null; error: string | null } {
  const [read, setRead] = useState<RealRead | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!conversation) return
    setRead(null); setError(null)
    let live = true
    fetch(`/api/conversations/${encodeURIComponent(conversation)}?batch=30`, { headers: CLIENT_HEADERS })
      .then((r) => r.ok ? r.json() as Promise<Conversation> : Promise.reject(new Error(`${r.status} ${r.statusText}`)))
      .then((c) => {
        if (!live) return
        const names = new Map(c.topics.map((x) => [x.id, x.name]))
        setRead({
          name: c.name,
          total: c.turns_total,
          posts: c.turns.map((t) => postOf(t, (id) => names.get(id))),
          topics: c.topics.map((x) => ({ key: x.name, name: x.name, count: x.turns })),
        })
      })
      .catch((e: unknown) => { if (live) setError(String(e)) })
    return () => { live = false }
  }, [conversation])
  return { read, error }
}

/* THE LONG-FORM REEL: real posts chosen from the dev Brain for what they hold
   (found by scanning it, 2026-11-09): long reports with headings, fenced
   code, Markdown tables and many pictures. Each is read in place (`around`
   its number) and the exact post kept. */
export const LONG_REEL: { conversation: string; number: number; why: string }[] = [
  { conversation: 'ent-98c0a097dbd9', number: 5, why: 'headings and fenced code' },
  { conversation: 'ent-cd0ddc9713a5', number: 916, why: 'a table and headings' },
  { conversation: 'ent-0a1a163beb3a', number: 569, why: 'a table and fourteen pictures' },
  { conversation: 'ent-cc71013e9872', number: 1, why: 'a long report: eighteen headings and code' },
  { conversation: 'ent-2865e11386f6', number: 1, why: 'the longest: 16,000 characters, tables' },
]

export function useLongReel(on: boolean): { read: RealRead | null; error: string | null } {
  const [read, setRead] = useState<RealRead | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!on) return
    let live = true
    Promise.all(LONG_REEL.map(({ conversation, number }) =>
      fetch(`/api/conversations/${encodeURIComponent(conversation)}?batch=1&around=${number}`, { headers: CLIENT_HEADERS })
        .then((r) => r.ok ? r.json() as Promise<Conversation> : Promise.reject(new Error(`${r.status} ${r.statusText}`)))
        .then((c) => {
          const names = new Map(c.topics.map((x) => [x.id, x.name]))
          const t = c.turns.find((x) => x.number === number)
          return t ? { ...postOf(t, (id) => names.get(id)), topics: [c.name] } : null
        })))
      .then((posts) => {
        if (!live) return
        const kept = posts.filter((p) => p !== null)
        setRead({ name: 'Long-form reel', total: kept.length, posts: kept, topics: [] })
      })
      .catch((e: unknown) => { if (live) setError(String(e)) })
    return () => { live = false }
  }, [on])
  return { read, error }
}
