/* Saved references only. This module has no Fluid workspace, reader, legacy
 * adapter or persistent browser state. The caller supplies this page's GET. */
import type { MagnetConfig } from '../../fluid/surface/magnet/types'
import type { MagnetGet, SavedMagnet } from './contract'
export { createMagnetResource } from './state'

const object = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : null
const magnetId = (v: unknown): v is `mag-${string}` => typeof v === 'string' && /^mag-[a-zA-Z0-9_-]{1,60}$/.test(v)
const entryId = (v: unknown): v is string => typeof v === 'string' && /^ent-[a-zA-Z0-9]{6,40}$/.test(v)
const types = new Set(['post', 'file', 'image', 'attachment'])
const dateValue = (v: unknown): v is string => {
  if (typeof v !== 'string' || !Number.isFinite(Date.parse(v))) return false
  const day = /^(\d{4}-\d{2}-\d{2})(?:$|T)/.exec(v)?.[1]
  if (!day) return false
  const at = Date.parse(day + 'T00:00:00Z')
  return Number.isFinite(at) && new Date(at).toISOString().slice(0, 10) === day
}

/** What this first candidate can truthfully inspect. Missing own Conversation
 * is deliberately NOT a read failure: the card explains its unavailable leg. */
export function unsupportedMagnet(config: unknown, id: string): string | undefined {
  const c = object(config)
  if (!c || c.id !== id) return 'The saved Magnet definition is missing or does not match its reference.'
  if (c.schema_version != null && c.schema_version !== 1) return 'This Magnet uses an unsupported definition schema.'
  // No configured source is a Magnet with nothing collected yet, not a broken
  // one: it opens, converses and is configured afterwards (`schema.py`
  // `_sources`). Nothing here substitutes a source for an empty list.
  if (!Array.isArray(c.sources) || c.sources.length > 20) return 'A Magnet has up to 20 configured sources.'
  for (const value of c.sources) {
    const source = object(value)
    if (!source || (source.kind === 'conversation' ? !entryId(source.conversation)
      : source.kind === 'file' ? typeof source.collection !== 'string' || !source.collection || (source.path != null && typeof source.path !== 'string') : true))
      return 'This candidate collects from Conversations and from plain text files. Other kinds of source are not available yet.'
  }
  const selection = object(c.selection)
  if (!selection) return 'The saved selection cannot be read.'
  if (selection.informationTypes != null && (!Array.isArray(selection.informationTypes) || selection.informationTypes.some((t) => !types.has(t))))
    return 'This preview supports Posts, Files, Images and Attachments; this selection asks for other information.'
  if (selection.dates != null) {
    const dates = object(selection.dates)
    if (!dates || Object.keys(dates).some((k) => k !== 'after' && k !== 'before')) return 'The saved date selection cannot be read.'
    for (const v of [dates.after, dates.before]) if (v != null && !dateValue(v)) return 'The saved date selection cannot be read.'
    if (typeof dates.after === 'string' && typeof dates.before === 'string' && Date.parse(dates.after) > Date.parse(dates.before)) return 'The saved date selection has its end before its start.'
  }
  return undefined
}

/** The one explicit discovery read. Saved zones may be on any saved page or
 * in its set-aside/focus placements, but never another Conversation/workspace.
 * A repeated placement is the same Magnet, so it is offered once. */
export async function discoverMagnets(conversation: string, get: MagnetGet, signal?: AbortSignal): Promise<SavedMagnet[]> {
  if (!entryId(conversation)) throw new Error('Open a conversation before choosing an existing Magnet.')
  const got = await get(`/fluid/api/arrangements/${encodeURIComponent(conversation)}`, signal)
  if (signal?.aborted) throw new DOMException('Discovery was abandoned.', 'AbortError')
  if (got.status !== 200) throw new Error(`The saved arrangement could not be read (${got.status}). Nothing was substituted.`)
  const answer = object(got.body)
  if (!answer) throw new Error('The saved arrangement answer cannot be read.')
  if (answer.layout == null) return []
  const layout = object(answer.layout)
  if (!layout || layout.format !== 'mentis.fluid-arrangement' || ![1, 2, 3].includes(Number(layout.version)))
    throw new Error('The saved arrangement format is unavailable in this preview.')
  const configs = object(layout.magnets) ?? {}
  const unreadable = object(answer.magnets_unreadable) ?? {}
  const found = new Map<string, string>()
  const zone = (v: unknown) => {
    const z = object(v)
    if (!z || z.type !== 'zone' || z.show !== 'magnet') return
    const options = object(z.options)
    const id = options?.magnet ?? z.id
    if (!magnetId(id)) return
    if (!found.has(id)) found.set(id, typeof z.name === 'string' && z.name.trim() ? z.name : 'Saved Magnet')
  }
  const tree = (v: unknown, depth = 0) => {
    if (depth > 30) throw new Error('The saved arrangement tree is too deep to read safely.')
    const n = object(v)
    if (n?.type === 'zone') zone(n)
    else if (n?.type === 'split' && Array.isArray(n.kids)) n.kids.forEach((kid) => tree(kid, depth + 1))
  }
  const view = (v: Record<string, unknown>) => {
    tree(v.tree)
    if (Array.isArray(v.setAside)) v.setAside.forEach(zone)
    const focus = object(v.focus)
    if (focus) {
      zone(focus.column)
      if (Array.isArray(focus.floats)) focus.floats.forEach((f) => zone(object(f)?.zone))
    }
  }
  view(layout)
  if (Array.isArray(layout.pages)) layout.pages.forEach((p) => { const page = object(p); if (page) view(page) })
  return [...found].map(([id, name]) => {
    const config = object(configs[id])
    const reason = typeof unreadable[id] === 'string' ? String(unreadable[id]) : unsupportedMagnet(config, id)
    return { id: id as `mag-${string}`, name, ...(config ? { config: config as unknown as MagnetConfig } : {}), ...(reason ? { reason } : {}) }
  })
}
