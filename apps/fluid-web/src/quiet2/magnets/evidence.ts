/* The retained batch is attached to the OWNER'S asking Turn. A dispatch's
 * references alone do not give its execution read_artifact reach. */
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
    throw new Error('The retained collection could not be verified. Collect before asking about it.')
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
  replyTo: string | null, op: string, agent: MiniAgent, collection: RetainedCollection) {
  const file = collection.artifact
  const work = `Answer only the owner's question below using the supplied retained Magnet collection ${file.ref} `
    + `(collection post ${collection.post}, digest ${file.digest}). Read it with read_artifact before answering. `
    + 'Examine the captured post body parts/text and file values, respecting the capture bounds and omissions. '
    + 'Cite the actual ent- post/version and adm- artifact references from that data. '
    + 'If the supplied data cannot be read or does not support an answer, state that limitation. '
    + 'Do not fabricate answers, substitute live source content, collect more, change configuration, or start broader work. '
    + `Return the answer in this Magnet Conversation.\n\nOwner's question:\n${question}`
  return {
    from: { magnet }, author, op, text: question,
    parts: [{ type: 'text', text: question },
      { type: 'file', ref: file.ref, media_type: file.media_type, alt: 'Retained Magnet collection' }],
    addressed_to: [agent.id], action: 'ask-participant', topics: [], because: null,
    ...(replyTo ? { replies_to: replyTo } : {}),
    dispatch: [{ participant: agent.id, runtime: agent.runtime, model: null, effort: null,
      persona: null, coordinate: false, new_instance: false, reach: 'work',
      requires: ['call_mentis_tools'], work }],
  }
}

export const evidencePieces = (text: string): string[] => text.split(/(\b(?:ent|adm)-[a-zA-Z0-9]{6,40}\b)/g)
export const isEvidence = (text: string): boolean => /^(?:ent|adm)-[a-zA-Z0-9]{6,40}$/.test(text)
