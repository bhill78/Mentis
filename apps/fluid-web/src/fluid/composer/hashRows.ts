/* WHAT THE `#` PALETTE OFFERS, AND WHEN ENTER MAY TAKE IT (Stage 1a).
 *
 * Two answers, asked at once and drawn as each arrives. The TOPIC answer
 * (`/fluid/api/topics?q=`) is a name lookup and comes back in milliseconds;
 * it alone decides the Topic rows and "Create topic". The FULL answer
 * (`/api/references`, production's exhaustive resolver) reads Turns and
 * acquired text and may take seconds; its posts, conversations and files are
 * added below the Topics when it comes. Neither waits for the other, and
 * Enter waits only for the answer that decides the first row: the topic
 * answer for a word, the full one for a bare number (a post's coordinate,
 * which only the full answer resolves).
 *
 * Pure: no React, so the rule is tested as it is. */

import { score } from '../../composer/trigger'
import type { Id } from '../store'

export type Pick =
  | { kind: 'person'; participant: Id; alias: string; dispatch: boolean; runtime?: string; model?: string; joining?: boolean }
  | { kind: 'summon'; alias: string; dispatch: boolean; runtime?: string; model?: string }
  | { kind: 'topic'; id: Id; name: string }
  | { kind: 'ref'; refKind: 'turn' | 'conversation' | 'acquired'; id: Id; label: string }
  | { kind: 'create'; name: string }

/** One row of `/api/references`. */
export interface Found {
  what: 'topic' | 'conversation' | 'turn' | 'participant' | 'acquired'
  ref: Id; name?: string; said?: string; number?: number; conversation_name?: string; exact?: string; key?: string
}

/** One row of `/fluid/api/topics`. */
export interface TopicHit { ref: Id; name: string; conversation?: Id; conversation_name?: string | null }

export interface HashRow { key: string; label: string; note?: string; group?: string; pick: Pick }

export const bare = (s: string) => s.replace(/^[@#]/, '')
export const titleOf = (q: string) => { const t = bare(q).trim().replace(/\s+/g, ' '); return t ? t[0].toUpperCase() + t.slice(1) : '' }
export const ranked = <T,>(xs: T[], label: (x: T) => string, q: string) =>
  xs.map((x, i) => ({ x, i, s: score(label(x), q) })).filter((r) => r.s !== null)
    .sort((a, b) => (a.s! - b.s!) || (a.i - b.i)).map((r) => r.x)

const numeric = (typed: string) => /^\d+$/.test(typed)

/** Whether the record is asked at all for these words. */
export const hashAsks = (typed: string) => typed.length >= 2 || numeric(typed)
/** Whether the topic lookup is asked: a bare number names a post, never a Topic. */
export const topicAsks = (typed: string) => hashAsks(typed) && !numeric(typed)

/** Enter and Tab wait only while the answer that decides the first row is
 *  still out. `null` is an answer not yet come. */
export function hashWaits(typed: string, topicHits: TopicHit[] | null, found: Found[] | null): boolean {
  if (!hashAsks(typed)) return false
  return numeric(typed) ? found === null : topicHits === null
}

const TOPIC_NOTE = 'topic: files this post under it'

export function hashRows({ q, topics, topicHits, found, conversation, canCreate, creating }: {
  q: string
  /** this conversation's Topics */
  topics: { id: Id; name: string }[]
  /** the topic answer for `q`; null while it is out */
  topicHits: TopicHit[] | null
  /** the full answer for `q`; null while it is out */
  found: Found[] | null
  conversation: Id | null
  canCreate: boolean
  creating: boolean
}): HashRow[] {
  const rows: HashRow[] = []
  const typed = q.trim()
  const here = (q ? ranked(topics, (x) => x.name, q) : topics).slice(0, 8)
  for (const x of here) rows.push({ key: x.id, label: '#' + x.name, note: TOPIC_NOTE, group: 'Topics here', pick: { kind: 'topic', id: x.id, name: x.name } })
  const shown = new Set(here.map((x) => x.id))
  const names = topics.map((x) => x.name)
  const topic = (ref: Id, name: string, where?: string | null) => {
    if (shown.has(ref)) return
    shown.add(ref)
    names.push(name)
    rows.push({ key: ref, label: '#' + name, note: where ? `${TOPIC_NOTE} · in ${where}` : TOPIC_NOTE, group: 'Topics', pick: { kind: 'topic', id: ref, name } })
  }
  for (const t of topicHits ?? []) topic(t.ref, t.name, t.conversation && t.conversation !== conversation ? t.conversation_name : null)
  for (const f of found ?? []) if (f.what === 'topic') topic(f.ref, f.name ?? f.ref, f.conversation_name)
  for (const f of found ?? []) {
    if (f.what === 'participant' || f.what === 'topic' || shown.has(f.ref)) continue
    const label = f.what === 'turn'
      ? `#${f.number ?? ''}${f.conversation_name ? ' · ' + f.conversation_name : ''}`
      : f.what === 'conversation' ? '#' + (f.name ?? f.ref) : '#' + (f.name ?? f.key ?? f.ref)
    const note = f.what === 'turn' ? (f.said ?? '').replace(/[#*`>_]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 60)
      : f.what === 'conversation' ? 'conversation: referred to' : 'acquired material'
    const said = f.what === 'turn' ? `#${f.number ?? ''}` : '#' + (f.name ?? f.key ?? f.ref)
    rows.push({ key: f.ref, label, note, group: 'Found', pick: { kind: 'ref', refKind: f.what, id: f.ref, label: said } })
  }
  /* A bare number is a post's coordinate, never a new Topic's name; and
     "Create" is offered once the topic answer says no Topic has the name. */
  if (canCreate && typed && !numeric(typed) && topicHits !== null
      && !names.some((x) => x.toLowerCase() === typed.toLowerCase()))
    rows.push({ key: 'create', label: creating ? `Creating topic "${titleOf(q)}"…` : `Create topic "${titleOf(q)}"`, note: conversation ? 'opens it in this conversation and files this post under it' : 'opened with your first post, which is filed under it', group: 'New', pick: { kind: 'create', name: titleOf(q) } })
  return rows
}
