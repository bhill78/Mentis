import { CLIENT_HEADERS } from '../../api'
import { BRAIN_HEADER, confirmBrain, page, refusedAsOtherBrain } from '../../brainBinding'
import { fluidFetch } from '../../fluid/http'
import { conversationSeed } from '../../fluid/surface/magnet/choices'
import type { SavedMagnet } from './contract'
import { unsupportedMagnet } from './read'

export const entryId = (v: unknown): v is string => typeof v === 'string' && /^ent-[a-zA-Z0-9]{6,40}$/.test(v)
export const resourceCorpus = (key: string) => key.split('|').at(-1) ?? ''
export function matchesBinding(key: string) {
  return !!key && !page.moved() && page.bound()?.split('@')[0] === resourceCorpus(key)
}
export interface ConversationChoice { id: string; name: string }
export async function conversationChoices(q: string, cursor: string | null, signal: AbortSignal): Promise<{ rows: ConversationChoice[]; next: string | null }> {
  const params = new URLSearchParams({ activity: '1', limit: '40', state: 'active' })
  if (q.trim()) params.set('q', q.trim())
  if (cursor) params.set('cursor', cursor)
  const r = await fetch('/fluid/api/conversations?' + params, { headers: CLIENT_HEADERS, signal, cache: 'no-store' })
  const v = await r.json()
  if (!r.ok || !Array.isArray(v?.conversations)) throw new Error(v?.error ?? 'Conversations unavailable.')
  return { rows: v.conversations.filter((c: ConversationChoice) => entryId(c.id) && typeof c.name === 'string').map((c: ConversationChoice) => ({ id: c.id, name: c.name })), next: typeof v.next === 'string' ? v.next : null }
}
/** Existing atomic create-and-place door. No whole arrangement save or own-C creation. */
export async function makeMagnet(at: { key: string; arrangement: string; source: string; name: string; op: string }): Promise<SavedMagnet> {
  if (!entryId(at.arrangement) || !entryId(at.source) || !at.name.trim() || at.name.length > 200) throw new Error('Choose a source Conversation and a name of at most 200 characters.')
  if (await confirmBrain() !== true || !matchesBinding(at.key)) throw new Error('Creation unavailable: this page cannot confirm its Brain. Your choices are kept.')
  const r = await fluidFetch(`/fluid/api/arrangements/${encodeURIComponent(at.arrangement)}/magnets`, {
    method: 'POST', headers: { ...CLIENT_HEADERS, [BRAIN_HEADER]: page.bound()!, 'Content-Type': 'application/json' },
    body: JSON.stringify({ seed: conversationSeed(at.source), op: at.op, wideFallback: 'launcher', attach: {
      zone: { type: 'zone', show: 'magnet', name: at.name.trim() },
      base: { format: 'mentis.fluid-arrangement', version: 2, tree: { type: 'zone', id: 'quiet-objects', show: 'objects' } },
    } }),
  })
  const v = await r.json().catch(() => null)
  if (refusedAsOtherBrain(r.status, v)) page.move()
  if (!r.ok || !v?.magnet || v.error) throw new Error(v?.error ?? `Creation outcome unavailable (${r.status}). Refresh the list before trying again.`)
  const config = v.magnet
  if (typeof config.id !== 'string' || !/^mag-[a-zA-Z0-9_-]{1,60}$/.test(config.id)) throw new Error('Creation answered without a usable Magnet identity. Refresh the list before trying again.')
  if (!matchesBinding(at.key) || config.sources?.length !== 1 || config.sources[0]?.kind !== 'conversation' || config.sources[0]?.conversation !== at.source) throw new Error('Creation answered for a different Brain or source. Refresh the list to check the result; nothing was opened.')
  return { id: config.id, name: at.name.trim(), config, reason: unsupportedMagnet(config, config.id) }
}
