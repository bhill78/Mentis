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
  return composerRequest({ text: question, parts: [{ type: 'text', text: question }],
    addressed_to: [agent.id], action: 'ask-participant', topics: [], because: null,
    dispatch: [{ participant: agent.id, runtime: agent.runtime, model: null, effort: null,
      persona: null, coordinate: false, new_instance: false }] }, magnet, author, replyTo, op, collection)
}

/** Add routing and bounded grounding to bodyOf's result. Every participant and
 * Work permission stays as the Composer built it; no second reading of them. */
export function composerRequest(post: Record<string, unknown>, magnet: string, author: string,
  replyTo: string | null, op: string, collection: RetainedCollection | null): Record<string, unknown> {
  const { _magnetPerspective, ...payload } = post
  const routed = { ...payload, from: { magnet }, author, op,
    ...(replyTo ? { replies_to: replyTo } : {}) }
  if (post.action === 'record-only') return routed
  if (_magnetPerspective) return routed
  if (!collection) throw new Error('Collect information first, then ask about the retained collection.')
  const question = typeof post.text === 'string' ? post.text : ''
  const file = collection.artifact
  const work = `Answer only the owner's question below using the supplied retained Magnet collection ${file.ref} `
    + `(collection post ${collection.post}, digest ${file.digest}). Read it with read_artifact before answering. `
    + 'Examine the captured post body parts/text and file values, respecting the capture bounds and omissions. '
    + 'Cite the actual ent- post/version and adm- artifact references from that data. '
    + 'If the supplied data cannot be read or does not support an answer, state that limitation. '
    + 'Do not fabricate answers, substitute live source content, collect more, change configuration, or start broader work. '
    + `Return the answer in this Magnet Conversation.\n\nOwner's question:\n${question}`
  return {
    ...routed,
    parts: [...(Array.isArray(post.parts) ? post.parts : []),
      ...(post.action === 'ask-mentis' ? [{ type: 'text', text: `\n\n${work}` }] : []),
      { type: 'file', ref: file.ref, media_type: file.media_type, alt: 'Retained Magnet collection' }],
    dispatch: (Array.isArray(post.dispatch) ? post.dispatch : []).map((spec: Record<string, unknown>) => ({
      ...spec, reach: 'work', requires: [...new Set([...(Array.isArray(spec.requires) ? spec.requires : []), 'call_mentis_tools'])], work,
    })),
  }
}

export const evidencePieces = (text: string): string[] => text.split(/(\b(?:ent|adm)-[a-zA-Z0-9]{6,40}\b)/g)
export const isEvidence = (text: string): boolean => /^(?:ent|adm)-[a-zA-Z0-9]{6,40}$/.test(text)
