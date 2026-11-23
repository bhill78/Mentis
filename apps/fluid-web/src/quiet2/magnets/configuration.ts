import { CLIENT_HEADERS } from '../../api'
import { BRAIN_HEADER, confirmBrain, page, refusedAsOtherBrain } from '../../brainBinding'
import { fluidFetch } from '../../fluid/http'
import type { MagnetConfig, MagnetSource } from '../../fluid/surface/magnet/types'
import { matchesBinding } from './managementApi'

export const sourceIdentity = (s: MagnetSource) => s.kind === 'conversation' ? `conversation:${s.conversation}`
  : s.kind === 'file' ? `file:${s.collection}:${s.path ?? ''}` : JSON.stringify(s)
export function exactFileIssue(collection: string, path: string): string | null {
  if (!/^[A-Za-z0-9_.:-]{1,80}$/.test(collection)) return 'This collection name cannot be saved by this Magnet schema (80 characters maximum).'
  if (!path.trim()) return 'Choose one held file; collection-wide file reads are unavailable.'
  if (Array.from(path).length > 300) return 'This held file path exceeds the Magnet limit of 300 characters.'
  if (/^[\\/]|^[A-Za-z]:|[?*\u0000]/.test(path) || /[\\/]$/.test(path) || path.split(/[\\/]/).some((p) => !p || p === '.' || p === '..'))
    return 'Choose an exact held file path, without a directory, wildcard or traversal.'
  return null
}
export function collectionChange(config: MagnetConfig, sources: MagnetSource[], types: string[], after: string, before: string) {
  if (!sources.length || sources.length > 20 || !sources.some((s) => s.kind === 'conversation')) throw new Error('Choose at least one Conversation and at most 20 sources in total.')
  if (new Set(sources.map(sourceIdentity)).size !== sources.length) throw new Error('Each source can be selected once.')
  for (const s of sources) {
    if (s.kind === 'conversation') { if (!/^ent-[a-zA-Z0-9]{6,40}$/.test(s.conversation)) throw new Error('Choose an existing Conversation.') }
    else if (s.kind === 'file') { const issue = exactFileIssue(s.collection, s.path ?? ''); if (issue) throw new Error(issue) }
    else throw new Error(`${s.kind} collection is unavailable in this milestone.`)
  }
  if (!types.length || types.some((t) => !['post', 'file', 'image', 'attachment'].includes(t))) throw new Error('Choose supported Conversation information types.')
  for (const date of [after, before]) if (date && (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(Date.parse(date)) || new Date(date).toISOString().slice(0, 10) !== date)) throw new Error('Choose a valid date.')
  if (after && before && after > before) throw new Error('The end date is before the start date.')
  return { sources, selection: { ...config.selection, informationTypes: types as NonNullable<MagnetConfig['selection']['informationTypes']>, dates: { ...(after ? { after } : {}), ...(before ? { before } : {}) } } }
}
export async function configurationRead(path: string, signal?: AbortSignal): Promise<any> {
  const r = await fetch(path, { headers: CLIENT_HEADERS, signal, cache: 'no-store' })
  const v = await r.json().catch(() => null)
  if (!r.ok || !v || v.error) throw new Error(v?.error ?? `Configuration information unavailable (${r.status}).`)
  return v
}
export async function holdingArrangement(arrangement: string, magnet: string, signal?: AbortSignal) {
  const v = await configurationRead(`/fluid/api/arrangements/${encodeURIComponent(arrangement)}`, signal)
  if (!v.layout?.magnets?.[magnet]) throw new Error('This arrangement does not hold the Magnet. Choose an existing holding arrangement; attach the Magnet first if none holds it.')
  return v
}
export async function saveCollection(at: { brainKey: string; arrangement: string; magnet: string; change: ReturnType<typeof collectionChange>; op: string }) {
  if (await confirmBrain() !== true || !matchesBinding(at.brainKey)) throw new Error('This page cannot confirm its Brain. The configuration has not been sent.')
  await holdingArrangement(at.arrangement, at.magnet)
  if (!matchesBinding(at.brainKey)) throw new Error('The Brain changed before saving. Reload to continue.')
  const r = await fluidFetch(`/fluid/api/arrangements/${encodeURIComponent(at.arrangement)}/magnets/${encodeURIComponent(at.magnet)}/reconfigure`, {
    method: 'POST', headers: { ...CLIENT_HEADERS, [BRAIN_HEADER]: page.bound()!, 'Content-Type': 'application/json' }, body: JSON.stringify({ change: at.change, op: at.op }),
  })
  const v = await r.json().catch(() => null)
  if (refusedAsOtherBrain(r.status, v)) page.move()
  if (!r.ok || !v?.magnet || v.magnet.id !== at.magnet) {
    const error = new Error(v?.error ?? `Save outcome is unknown (${r.status}). Retry the unchanged save.`)
    Object.assign(error, { refused: r.status >= 400 && r.status < 500 && !!v?.refused })
    throw error
  }
  if (!matchesBinding(at.brainKey)) throw new Error('The Brain changed while saving. No response was applied to this page.')
  return v.magnet as MagnetConfig
}
