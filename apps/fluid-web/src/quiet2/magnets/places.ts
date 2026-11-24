/** The view-state spine. Every view is a "place" that keeps its own reading
 *  position, inspection and disclosure state, and every navigation goes through
 *  here so that returning is exact.
 *
 *  Deep copying is the contract, not an implementation detail: `route()` copies
 *  the search target and the place, and `restore()` writes copies back, which is
 *  what makes a return survive an intervening search. No helper here mutates a
 *  MagnetPlace in place; each one replaces it. */
import { MAGNET_PLACE_KEYS, MAGNET_TABS } from './contract'
import type { MagnetOverlay, MagnetPlace, MagnetPlaceKey, MagnetResource, MagnetRoute, MagnetSnapshot, MagnetTab } from './contract'

export const emptyPlace = (): MagnetPlace => ({ scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false, history: false })
export const emptyPlaces = (): Record<MagnetPlaceKey, MagnetPlace> =>
  Object.fromEntries(MAGNET_PLACE_KEYS.map((k) => [k, emptyPlace()])) as Record<MagnetPlaceKey, MagnetPlace>

export const isMagnetTab = (v: unknown): v is MagnetTab => typeof v === 'string' && (MAGNET_TABS as readonly string[]).includes(v)
export const isPlaceKey = (v: unknown): v is MagnetPlaceKey => typeof v === 'string' && (MAGNET_PLACE_KEYS as readonly string[]).includes(v)

/** THE NAVIGATION MODEL (owner request ent-3191baeb33d2 §1).
 *
 *  "The underlying information model does not need to dictate the navigation
 *  model." `MAGNET_TABS` stays the state and persistence spine -- every place
 *  keeps its own reading position, inspection and disclosure, and the host still
 *  supplies one view per place key -- while what the card offers is:
 *
 *    Summary · Perspectives · Conversation    the three primary places
 *    Collection [Everything|Posts|Files]      one secondary place, type-filtered
 *
 *  A collection filter IS the underlying lens place. That is deliberate: each
 *  type keeps the reading position it always had, a future source type adds a
 *  filter and not a primary tab, nothing in the persisted shape changes, and no
 *  tab is removed from the state the other parts' views are keyed by. */
export const MAGNET_PRIMARY_TABS = ['Summary', 'Perspectives', 'Conversation'] as const
export type MagnetPrimaryTab = typeof MAGNET_PRIMARY_TABS[number]
export const MAGNET_COLLECTION_TABS = ['All', 'Posts', 'Files'] as const
export type MagnetCollectionTab = typeof MAGNET_COLLECTION_TABS[number]
/** The collection's type filters, in order. `All` is the unified collection. */
export const MAGNET_COLLECTION_FILTERS: readonly { tab: MagnetCollectionTab; label: string }[] = [
  { tab: 'All', label: 'Everything' }, { tab: 'Posts', label: 'Posts' }, { tab: 'Files', label: 'Files' },
]
export const isCollectionTab = (v: unknown): v is MagnetCollectionTab =>
  typeof v === 'string' && (MAGNET_COLLECTION_TABS as readonly string[]).includes(v)
/** Which type filter the collection is showing, or would open on. */
export const collectionTabOf = (s: MagnetSnapshot): MagnetCollectionTab => isCollectionTab(s.tab) ? s.tab : 'All'
/** Whether the card is in the collection now (an overlay covers it). */
export const inCollection = (s: MagnetSnapshot): boolean => !s.overlay && isCollectionTab(s.tab)

/** Which place the card is showing: the overlay when one is open, else the tab. */
export const placeKeyOf = (s: MagnetSnapshot): MagnetPlaceKey => s.overlay ?? s.tab
export const place = (s: MagnetSnapshot): MagnetPlace => ({ ...emptyPlace(), ...s.places?.[placeKeyOf(s)] })
export const placeAt = (s: MagnetSnapshot, key: MagnetPlaceKey): MagnetPlace => ({ ...emptyPlace(), ...s.places?.[key] })

/** The frame registers how to read the live scroll of its one scroll container,
 *  so any part can call `remember(resource)` without reaching into the DOM. */
const readers = new WeakMap<MagnetResource, () => number>()
export function registerViewScroll(resource: MagnetResource, read: () => number): () => void {
  readers.set(resource, read)
  return () => { if (readers.get(resource) === read) readers.delete(resource) }
}

export function writePlace(resource: MagnetResource, key: MagnetPlaceKey, change: Partial<MagnetPlace>) {
  const s = resource.snapshot()
  resource.update({ places: { ...s.places, [key]: { ...placeAt(s, key), ...change } } })
}

/** Write the live scroll position into the current place, before any navigation.
 *
 *  While an inspection is visible the live offset belongs to the inspection, so
 *  it is written to `inspectScroll`. The list position the reader came from --
 *  the one `inspect()` saved and `closeInspect()` returns to -- is never
 *  overwritten by closing the card, changing size, searching, opening settings
 *  or inspecting something nested. This is the same split the frame's `onScroll`
 *  makes, so remembering and scrolling can never disagree. */
export function remember(resource: MagnetResource, scrollTop?: number) {
  const s = resource.snapshot()
  const now = place(s)
  const live = scrollTop ?? readers.get(resource)?.()
  const kept = now.inspected ? now.inspectScroll : now.scroll
  const top = typeof live === 'number' && Number.isFinite(live) && live >= 0 ? Math.round(live) : kept
  writePlace(resource, placeKeyOf(s), now.inspected ? { inspectScroll: top } : { scroll: top })
}

export function route(s: MagnetSnapshot): MagnetRoute {
  return {
    tab: s.tab, overlay: s.overlay,
    searchTarget: s.searchTarget ? { ...s.searchTarget } : null,
    lens: s.lens ?? null, query: s.query ?? '', searchType: s.searchType ?? 'All',
    searchListScroll: s.searchListScroll ?? 0,
    placeKey: placeKeyOf(s), placeSnapshot: place(s),
  }
}

export function restore(resource: MagnetResource, r: MagnetRoute) {
  remember(resource)
  const s = resource.snapshot()
  resource.update({
    tab: r.tab, overlay: r.overlay,
    searchTarget: r.searchTarget ? { ...r.searchTarget } : null,
    lens: r.lens, query: r.query, searchType: r.searchType, searchListScroll: r.searchListScroll,
    places: { ...s.places, [r.placeKey]: { ...r.placeSnapshot } },
  })
}

export function goTab(resource: MagnetResource, tab: MagnetTab) {
  remember(resource)
  resource.update({ tab, overlay: null, searchTarget: null })
}

export function openOverlay(resource: MagnetResource, overlay: Exclude<MagnetOverlay, null>) {
  remember(resource)
  if (overlay === 'settings') {
    const s = resource.snapshot()
    if (s.overlay !== 'settings') resource.update({ settingsReturn: route(s) })
    resource.update({ overlay: 'settings' })
    return
  }
  resource.update({ overlay })
}

/** Leaving settings returns exactly where the gear was pressed from. */
export function leaveSettings(resource: MagnetResource) {
  const s = resource.snapshot()
  const back = s.settingsReturn
  resource.update({ settingsReturn: null })
  if (back) { restore(resource, back); return }
  remember(resource)
  resource.update({ overlay: null })
}

export function closeOverlay(resource: MagnetResource) {
  const s = resource.snapshot()
  if (s.overlay === 'settings') { leaveSettings(resource); return }
  remember(resource)
  resource.update({ overlay: null, searchTarget: null })
}

/** Open an evidence reference inside the current place, remembering where the
 *  reader came back to. This is v1's one-level inspection return, kept. */
export function inspect(resource: MagnetResource, ref: string, origin?: string | null) {
  remember(resource)
  const s = resource.snapshot()
  const key = placeKeyOf(s), now = place(s)
  resource.update({
    open: true,
    places: {
      ...s.places,
      [key]: now.inspected
        ? { ...now, inspected: ref, inspectScroll: 0, provenance: false }
        : { ...now, inspected: ref, inspectScroll: 0, inspectOrigin: origin ?? null, provenance: false },
    },
  })
}

/** Leaving an inspection keeps `scroll` exactly as `inspect()` remembered it: the
 *  list position the reader came from. The inspection's own position is dropped. */
export function closeInspect(resource: MagnetResource) {
  const s = resource.snapshot()
  const key = placeKeyOf(s), now = place(s)
  resource.update({ places: { ...s.places, [key]: { ...now, inspected: null, provenance: false, inspectScroll: 0, inspectOrigin: null } } })
}

export const clearInspections = (places: Record<MagnetPlaceKey, MagnetPlace>): Record<MagnetPlaceKey, MagnetPlace> =>
  Object.fromEntries(MAGNET_PLACE_KEYS.map((k) => [k, { ...emptyPlace(), ...places?.[k], inspected: null, inspectOrigin: null, inspectScroll: 0, provenance: false }])) as Record<MagnetPlaceKey, MagnetPlace>

/** The one place the open transition's activity baseline is written. The card
 *  is opened by the puck, by the header close only to shut it, and by the host's
 *  Magnet phase -- never by a pointer entering or by focus. */
export function setOpen(resource: MagnetResource, open: boolean) {
  const s = resource.snapshot()
  if (s.open === open) return
  resource.update(open ? { open: true, previousOpen: s.openedAt, openedAt: Date.now() } : { open: false })
}
