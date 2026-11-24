import { page } from '../../brainBinding'
import { MAGNET_SEARCH_TYPES, MAGNET_TABS } from './contract'
import type { MagnetContext, MagnetOverlay, MagnetPlace, MagnetPlaceKey, MagnetRoute, MagnetSearchTarget, MagnetSearchType, MagnetSnapshot, MagnetTab } from './contract'
import { emptyPlace, emptyPlaces, isMagnetTab, isPlaceKey } from './places'

// Device working state only. Retained content and messages belong to the Brain.
export function workingKey(brainKey: string): string | null {
  const bound = page.bound()
  return bound && !page.moved() && bound.split('@')[0] === brainKey.split('|').at(-1)
    ? `mentis.magnet.working.v1:${brainKey}:${bound}` : null
}

/** The key is deliberately NOT bumped: the loader reads both the v1 shape and
 *  the hybrid shape and always writes the hybrid one. Unknown keys were already
 *  ignored, so the old payload is safe to read; rolling back to the previous
 *  release reads the new shape and loses working state only. */
const obj = (v: unknown): Record<string, unknown> | null => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : null
const num = (v: unknown): number | null => typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null
const text = (v: unknown, max: number): string | null => typeof v === 'string' && v.length <= max ? v : null
const ref = (v: unknown): string | null => typeof v === 'string' && v.length > 0 && v.length < 300 ? v : null
const flag = (v: unknown): boolean | null => typeof v === 'boolean' ? v : null

/** v1 named the first tab `Overview`; the approved design names it `All`. */
const tabOf = (v: unknown): MagnetTab | null => v === 'Overview' ? 'All' : isMagnetTab(v) ? v : null
const overlayOf = (v: unknown): MagnetOverlay => v === 'search' || v === 'settings' ? v : null
const searchTypeOf = (v: unknown): MagnetSearchType => typeof v === 'string' && (MAGNET_SEARCH_TYPES as readonly string[]).includes(v) ? v as MagnetSearchType : 'All'
const kinds = ['Summary', 'Posts', 'Files', 'Perspectives', 'Conversation', 'Settings', 'Batches']
const targetOf = (v: unknown): MagnetSearchTarget | null => {
  const o = obj(v)
  if (!o || typeof o.kind !== 'string' || !kinds.includes(o.kind)) return null
  return { kind: o.kind as MagnetSearchTarget['kind'],
    ...(ref(o.entry) ? { entry: ref(o.entry)! } : {}),
    ...(ref(o.item) ? { item: ref(o.item)! } : {}),
    ...(ref(o.lens) ? { lens: ref(o.lens)! } : {}),
    ...(ref(o.message) ? { message: ref(o.message)! } : {}) }
}
const contextKinds = ['post', 'file', 'image', 'attachment', 'perspective', 'batch']
const contextOf = (v: unknown): MagnetContext | null => {
  const o = obj(v)
  if (!o || !ref(o.ref) || typeof o.kind !== 'string' || !contextKinds.includes(o.kind)) return null
  // Only the reference and its label are kept; captured text never enters storage.
  return { ref: ref(o.ref)!, kind: o.kind as MagnetContext['kind'], label: text(o.label, 200) ?? 'Discussion reference' }
}
const placeOf = (v: unknown): MagnetPlace | null => {
  const o = obj(v)
  if (!o) return null
  return { scroll: num(o.scroll) ?? 0, inspected: ref(o.inspected), inspectScroll: num(o.inspectScroll) ?? 0,
    inspectOrigin: ref(o.inspectOrigin), provenance: o.provenance === true, history: o.history === true }
}
const routeOf = (v: unknown): MagnetRoute | null => {
  const o = obj(v)
  if (!o) return null
  const tab = tabOf(o.tab), key = isPlaceKey(o.placeKey) ? o.placeKey : null, snapshot = placeOf(o.placeSnapshot)
  if (!tab || !key || !snapshot) return null
  return { tab, overlay: overlayOf(o.overlay), searchTarget: targetOf(o.searchTarget), lens: ref(o.lens),
    query: text(o.query, 1000) ?? '', searchType: searchTypeOf(o.searchType), searchListScroll: num(o.searchListScroll) ?? 0,
    placeKey: key, placeSnapshot: snapshot }
}

/** The hybrid shape's own `places` map, when the payload already has one. */
function placesOf(v: unknown): Record<MagnetPlaceKey, MagnetPlace> | null {
  const o = obj(v)
  if (!o) return null
  const places = emptyPlaces()
  let found = false
  for (const [key, value] of Object.entries(o)) {
    if (!isPlaceKey(key)) continue
    const p = placeOf(value)
    if (p) { places[key] = p; found = true }
  }
  return found ? places : null
}

/** v1 → hybrid, key by key. All fourteen v1 keys are accounted for:
 *  x, y → x, y · tab (Overview→All) → tab · expanded, pinned → open, wide
 *  inspection → places[tab].inspected · inspectionScroll → places[tab].inspectScroll
 *  inspectionReturn → returnRoute (the one-level return is kept, not dropped)
 *  query → query · scroll → places[tab].scroll when `scrolls` has no entry
 *  scrolls → places[*].scroll (Overview→All, Compact dropped)
 *  agentId, assistanceMode, batchSelection → unchanged. */
function fromV1(v: Record<string, unknown>): Partial<MagnetSnapshot> {
  const tab = tabOf(v.tab) ?? 'Summary'
  const places = emptyPlaces()
  const named = new Set<MagnetPlaceKey>()
  for (const [key, value] of Object.entries(obj(v.scrolls) ?? {})) {
    const to = tabOf(key)                       // 'Compact' has no hybrid home: dropped
    const top = num(value)
    if (to && top !== null) { places[to] = { ...places[to], scroll: top }; named.add(to) }
  }
  const scroll = num(v.scroll)
  if (scroll !== null && !named.has(tab)) places[tab] = { ...places[tab], scroll }
  const inspected = text(v.inspection, 299)
  if (inspected) places[tab] = { ...places[tab], inspected, inspectScroll: num(v.inspectionScroll) ?? 0, inspectOrigin: null }
  const returning = obj(v.inspectionReturn)
  const returningTab = returning ? tabOf(returning.tab) : null
  return {
    ...(num(v.x) !== null && num(v.y) !== null ? { x: v.x as number, y: v.y as number } : {}),
    tab,
    open: v.expanded === true || v.pinned === true,
    wide: false,                                // v1 `expanded` meant "details shown", never a width
    overlay: null,
    places,
    ...(text(v.query, 1000) !== null ? { query: v.query as string } : {}),
    searchType: 'All', searchTarget: null, searchListScroll: 0, lens: null,
    returnRoute: returningTab
      ? { tab: returningTab, overlay: null, searchTarget: null, lens: null, query: text(v.query, 1000) ?? '',
          searchType: 'All', searchListScroll: 0, placeKey: returningTab,
          placeSnapshot: { ...emptyPlace(), scroll: places[returningTab].scroll } }
      : null,
    settingsReturn: null, context: null, contextSuppressed: false,
    ...(typeof v.agentId === 'string' && /^ent-[a-zA-Z0-9]{6,40}$/.test(v.agentId) ? { agentId: v.agentId } : {}),
    ...(['ordinary', 'retained'].includes(v.assistanceMode as string) ? { assistanceMode: v.assistanceMode as 'ordinary' | 'retained' } : {}),
    ...(batchOf(v.batchSelection) ? { batchSelection: batchOf(v.batchSelection)! } : {}),
  }
}
const batchOf = (v: unknown): { ref: string; digest: string } | null => {
  const o = obj(v)
  return o && typeof o.ref === 'string' && /^adm-[a-zA-Z0-9]{6,40}$/.test(o.ref) && typeof o.digest === 'string' && /^[0-9a-f]{64}$/.test(o.digest)
    ? { ref: o.ref, digest: o.digest } : null
}

export function loadWorking(brainKey: string, id: string): Partial<MagnetSnapshot> {
  try {
    const key = workingKey(brainKey)
    if (!key) return {}
    const v = obj(JSON.parse(localStorage.getItem(`${key}:${id}`) ?? '{}'))
    if (!v) return {}
    const places = placesOf(v.places)
    // The hybrid shape is recognised by its own keys; anything else is v1.
    if (!places && flag(v.open) === null && flag(v.wide) === null) return Object.keys(v).length ? fromV1(v) : {}
    return {
      ...(num(v.x) !== null && num(v.y) !== null ? { x: v.x as number, y: v.y as number } : {}),
      ...(tabOf(v.tab) ? { tab: tabOf(v.tab)! } : {}),
      ...(flag(v.open) !== null ? { open: v.open as boolean } : {}),
      ...(flag(v.wide) !== null ? { wide: v.wide as boolean } : {}),
      overlay: overlayOf(v.overlay),
      ...(places ? { places } : {}),
      ...(text(v.query, 1000) !== null ? { query: v.query as string } : {}),
      searchType: searchTypeOf(v.searchType),
      searchTarget: targetOf(v.searchTarget),
      searchListScroll: num(v.searchListScroll) ?? 0,
      lens: ref(v.lens),
      returnRoute: routeOf(v.returnRoute),
      settingsReturn: routeOf(v.settingsReturn),
      context: contextOf(v.context),
      contextSuppressed: v.contextSuppressed === true,
      ...(typeof v.agentId === 'string' && /^ent-[a-zA-Z0-9]{6,40}$/.test(v.agentId) ? { agentId: v.agentId } : {}),
      ...(['ordinary', 'retained'].includes(v.assistanceMode as string) ? { assistanceMode: v.assistanceMode as 'ordinary' | 'retained' } : {}),
      ...(batchOf(v.batchSelection) ? { batchSelection: batchOf(v.batchSelection)! } : {}),
    }
  } catch { return {} }
}

export function saveWorking(brainKey: string, id: string, s: MagnetSnapshot) {
  try {
    const key = workingKey(brainKey)
    if (!key) return
    localStorage.setItem(`${key}:${id}`, JSON.stringify({
      x: s.x, y: s.y, open: s.open, wide: s.wide, tab: s.tab, overlay: s.overlay, places: s.places,
      query: s.query, searchType: s.searchType, searchTarget: s.searchTarget, searchListScroll: s.searchListScroll,
      lens: s.lens, returnRoute: s.returnRoute, settingsReturn: s.settingsReturn,
      context: s.context ? { ref: s.context.ref, kind: s.context.kind, label: s.context.label } : null,
      contextSuppressed: s.contextSuppressed,
      agentId: s.agentId, assistanceMode: s.assistanceMode, batchSelection: s.batchSelection,
    }))
  } catch { /* The Brain still retains collection and Conversation if storage is unavailable. */ }
}
export function openedMagnets(brainKey: string): string[] {
  try {
    const key = workingKey(brainKey), rows = key && JSON.parse(localStorage.getItem(`${key}:open`) ?? '[]')
    return Array.isArray(rows) ? rows.filter((id): id is string => typeof id === 'string' && /^mag-[a-zA-Z0-9_-]{1,60}$/.test(id)).slice(0, 20) : []
  } catch { return [] }
}
export function saveOpenedMagnets(brainKey: string, ids: string[]) {
  try { const key = workingKey(brainKey); if (key) localStorage.setItem(`${key}:open`, JSON.stringify(ids.slice(0, 20))) } catch { /* Device storage can be disabled. */ }
}
export const MAGNET_TAB_NAMES: readonly string[] = MAGNET_TABS
