/* EXPERIMENTAL: the reading half of problems (drawn in ../types/problems.tsx). */
import type { TypeSpec } from './api'
import { listOf } from '../util'

export type Show = 'text' | 'author' | 'recorded' | 'record' | 'place' | 'activity'

export const SHOWS: Show[] = ['text', 'author', 'recorded', 'record', 'place', 'activity']

export interface Decl {
  mode: 'refs' | 'conversation' | 'brain'
  refs: string[]
  conversation: string | null
  include: 'current' | 'all'
  order: 'newest' | 'oldest' | 'listed'
  show: Show[]
}

export const ID = /^ent-[0-9a-f]{6,}$/

export const problemsSpec: TypeSpec<Decl> = {
  type: 'problems',
  summary: 'A live view over existing Mentis Problem records. Shows what the record says; owns none of it.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    refs: { req: 'optional', says: 'comma list of Problem ids to watch (explicit mode)' },
    scope: { req: 'optional', choices: ['conversation', 'brain'], says: 'watch Problems of a scope instead of named ones' },
    conversation: { req: 'optional', says: 'with scope=conversation: which one (default: where the block is read)' },
    include: { req: 'optional', choices: ['current', 'all'], says: 'current = not replaced and not deleted (default); all' },
    order: { req: 'optional', choices: ['newest', 'oldest', 'listed'], says: 'row order; listed = as in refs' },
    show: { req: 'optional', says: `comma list of: ${SHOWS.join(', ')} (default all)` },
  },
  body: 'nothing: the Problems are read live from Mentis, never written into the block',
  parse(body, a, c) {
    const refs = listOf(a.refs)
    if (!!a.refs === !!a.scope)
      c.err(a.refs ? 'scope' : 'refs', 'Say either refs=… (the Problems to watch) or scope=conversation|brain, not both and not neither.')
    for (const r of refs) if (!ID.test(r)) c.err('refs', `“${r}” is not an entry id (they look like ent-3f2a…).`)
    if (a.conversation && a.scope !== 'conversation') c.err('conversation', 'conversation=… only means something with scope=conversation.')
    if (a.conversation && !ID.test(a.conversation)) c.err('conversation', `“${a.conversation}” is not a Conversation id.`)
    if (a.order === 'listed' && !a.refs) c.err('order', 'order=listed keeps the order of refs, so it needs refs.')
    const show = (a.show ? listOf(a.show) : SHOWS) as Show[]
    for (const s of show) if (!SHOWS.includes(s)) c.err('show', `“${s}” is not something this view can show. Choose from: ${SHOWS.join(', ')}.`)
    if (body.trim()) c.warn('body', 'The body is not used. Problem state is read live from Mentis and is never copied into the block.')
    return {
      mode: a.refs ? 'refs' : a.scope === 'brain' ? 'brain' : 'conversation',
      refs,
      conversation: a.conversation ?? null,
      include: (a.include as Decl['include']) ?? 'current',
      order: (a.order as Decl['order']) ?? (a.refs ? 'listed' : 'newest'),
      show,
    }
  },

}
