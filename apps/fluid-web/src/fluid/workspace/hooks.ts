/* The workspace's subscriptions: each card hears only what it shows (the
 * store's keys, as the shell's own hooks do), and the navigation state. */

import { useCallback, useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { store, type Id, type PostObjectEntry } from '../store'
import type { Show } from './tree'
import { KINDS, kindOf as isOf } from '../../experimental/objectkinds'

function useKey<T>(key: string, read: () => T): T {
  const sub = useCallback((fn: () => void) => store.subscribe(key, fn), [key])
  return useSyncExternalStore(sub, read)
}
export const usePost = (id: Id) => useKey('post:' + id, () => store.posts.get(id))
export const useCollection = (key: string) => useKey('coll:' + key, () => store.collections.get(key))
export const usePostObjects = (root: Id) => useKey('objects:' + root, () => store.postObjects.get(root))
export const useThreadObjects = (root: Id) => useKey('tobjects:' + root, () => store.threadObjects.get(root))
export const useObject = (address: string) => useKey('obj:' + address, () => store.objects.get(address))
export const useKept = () => useKey('kept', () => store.kept)
export const useIsKept = (address: string) => useKey('keep:' + address, () => store.isKept(address))
export const useSelection = () => useKey('selection', () => store.selected)
export const useNav = () => useSyncExternalStore(nav.subscribe, nav.snapshot)

/** A card's title: the block's own, else what it is. */
export function titleOf(o: PostObjectEntry): string {
  if (o.title && o.title !== o.type) return o.title
  if (o.kind === 'post-text') return 'Post text'
  if (o.kind === 'media') return o.type === 'returned' ? 'Returned file' : 'Attachment'
  return o.type.charAt(0).toUpperCase() + o.type.slice(1)
}

/** The page title Open as page gives a tab: the demo truncates past 22.
 *  A title that begins with its conversation's name ("Local LLM Prelim:
 *  context sizes") loses that name first, which every tab would otherwise
 *  share, so tabs read apart (F6 final fix round). */
export function tabTitle(t: string, names: (string | null | undefined)[] = []): string {
  for (const name of names) {
    if (!name) continue
    const esc = name.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const rest = t.replace(new RegExp(`^\\s*${esc}\\s*[:\\-–—·|]\\s*`, 'i'), '')
    if (rest !== t && rest.trim()) { t = rest; break }
  }
  return t.length > 22 ? t.slice(0, 20) + '…' : t
}

/** Which objects a zone shows (the zone sheet's SHOW, #188), as the kind
 *  registry (experimental/objectkinds.ts) answers what each object is:
 *  everything, the post's own words too; its objects; its sections (blocks
 *  its author wrote); media (pictures, film, sound, video links); files;
 *  forms; what can be filled in (forms, checklists, tables with editable
 *  columns or rows to choose, pads); or only some kinds. */
export type { Show } from './tree'
export { KINDS }
/** The "Only some kinds" choice an object answers to. */
export const kindOf = (o: PostObjectEntry): string => isOf(o).filter
/** Does `show` take this object, on its own? Where it sits is `shownOf`'s. */
export function shows(o: PostObjectEntry, show: Show, kinds?: string[]): boolean {
  const is = isOf(o)
  if (show === 'everything') return true
  if (show === 'needs-you') return false
  if (show === 'media') return is.family === 'media'
  if (show === 'files') return is.family === 'file'
  if (show === 'sections') return is.family === 'section'
  if (show === 'forms') return is.filter === 'form'
  if (show === 'fillable') return !!is.fillable
  if (show === 'kinds') return !!kinds?.includes(is.filter)
  return is.family !== 'text'
}

/** What a zone held on a post shows (P10b), in words: a post and its
 *  replies, or -- held on a reply, which is read on its own -- that reply. */
export const heldOn = (number: number | null, reply: boolean, none = 'this post'): string =>
  `${number != null ? `#${number}` : none}${reply ? '' : ' and its replies'}`

/** What a zone shows of one post's objects, in order. A block inside
 *  another (a form in a panel) is drawn by the block holding it, so it is
 *  shown on its own only where no block holding it is drawn in the zone:
 *  a panel's form is there under Forms, and not twice under Its objects,
 *  nor beside the panel where the zone keeps that panel (`drawn`: the
 *  addresses the zone draws already, exact or live). */
export function shownOf(list: PostObjectEntry[], show: Show, kinds?: string[], drawn?: ReadonlySet<string>): PostObjectEntry[] {
  const byKey = new Map(list.map((o) => [o.key, o]))
  const took = new Map(list.map((o) => [o.key, shows(o, show, kinds)]))
  const taken = (o: PostObjectEntry) => !!took.get(o.key)
    || (!!drawn && (drawn.has(o.address.live) || drawn.has(o.address.exact)))
  const held = (o: PostObjectEntry): boolean => {
    const seen = new Set<string>()
    for (let p = o.parent; p !== null && !seen.has(p); ) {
      seen.add(p)
      const up = byKey.get(p)
      if (!up) return false
      if (taken(up)) return true
      p = up.parent
    }
    return false
  }
  return list.filter((o) => !!took.get(o.key) && !held(o))
}
