/* Collection metadata is for viewing. Ordinary messages never attach the pool. */
import { validateExplicitSelector } from './contract'
export interface RetainedCollection {
  post: string
  artifact: { ref: string; digest: string; size: number; media_type: string }
  at: number
}
export interface MiniAgent { id: string; alias: string; runtime: string | null }
const obj = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : null
const entry = (v: unknown): v is string => typeof v === 'string' && /^ent-[a-zA-Z0-9]{6,40}$/.test(v)

export function retainedCollection(body: unknown, magnet: string): RetainedCollection | null {
  const b = obj(body)
  if (!b || b.magnet !== magnet || !obj(b.config)) throw new Error('The collection read did not answer for this Magnet.')
  if (b.activation === null && b.page === null) return null
  const a = obj(b.activation), file = obj(a?.artifact), page = obj(b.page)
  if (!a || !entry(a.post) || !file || typeof file.ref !== 'string'
    || !/^adm-[a-zA-Z0-9]{6,40}$/.test(file.ref)
    || typeof file.digest !== 'string' || !file.digest
    || typeof file.size !== 'number' || !Number.isSafeInteger(file.size) || file.size < 0
    || typeof file.media_type !== 'string' || !file.media_type
    || typeof a.at !== 'number' || !Number.isFinite(a.at)
    || !page || !Array.isArray(page.sources)) {
    throw new Error('The collection could not be verified. Collect before asking about it.')
  }
  return { post: a.post, artifact: file as unknown as RetainedCollection['artifact'], at: a.at }
}

/** Participants are possible agent recipients, including those with no runtime
 * default. The owner chooses who should act as an agent; a null runtime uses
 * core automatic selection. Only the server's valid `me` identifies the owner. */
export function agentsOf(body: unknown): MiniAgent[] {
  const b = obj(body)
  if (!b || !Array.isArray(b.participants)) throw new Error('Agent participants could not be read.')
  if (!entry(b.me)) throw new Error('Agent participants did not identify the owner. Refresh before choosing a recipient.')
  return b.participants.flatMap((v) => {
    const p = obj(v)
    if (!p || !entry(p.id) || p.id === b.me || typeof p.alias !== 'string') return []
    const runtime = typeof p.default_runtime === 'string' && p.default_runtime ? p.default_runtime : null
    if (!runtime && p.runtime_mode !== 'auto' && p.runtime_mode !== 'undeclared') return []
    return [{ id: p.id, alias: p.alias, runtime }]
  })
}

export function groundedRequest(magnet: string, author: string, question: string,
  replyTo: string | null, op: string, agent: MiniAgent, collection: RetainedCollection | null) {
  return composerRequest({ text: question, parts: [{ type: 'text', text: question }],
    addressed_to: [agent.id], action: 'ask-participant', topics: [], because: null,
    dispatch: [{ participant: agent.id, runtime: agent.runtime, model: null, effort: null,
      persona: null, coordinate: false, new_instance: false }] }, magnet, author, replyTo, op, collection)
}

/** Route the exact Composer message. Context selectors travel separately from
 * authored parts. Retained collections are never attached by this adapter. */
export function composerRequest(post: Record<string, unknown>, magnet: string, author: string,
  replyTo: string | null, op: string, _collection: RetainedCollection | null): Record<string, unknown> {
  if (Object.keys(post).some((key) => key.startsWith('_magnet')))
    throw new Error('This old Magnet send format is unavailable. Keep your words and prepare a new ordinary request.')
  if (post.magnet_context !== null && post.magnet_context !== undefined) {
    const checked = validateExplicitSelector(post.magnet_context)
    if (!checked.ok) throw new Error(checked.error)
  }
  return { ...post, from: { magnet }, author, op,
    ...(post.action === 'ask-mentis' ? { ask_mentis: { ...(obj(post.ask_mentis) ?? {}), reach: 'work' } } : {}),
    dispatch: (Array.isArray(post.dispatch) ? post.dispatch : []).map((spec) => ({ ...spec, reach: 'work' })),
    ...(replyTo ? { replies_to: replyTo } : {}) }
}

export const evidencePieces = (text: string): string[] => text.split(/(\b(?:ent|adm)-[a-zA-Z0-9]{6,40}\b)/g)
export const isEvidence = (text: string): boolean => /^(?:ent|adm)-[a-zA-Z0-9]{6,40}$/.test(text)
