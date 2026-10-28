import type { ConversationObjectSummary, Id, PostObjectEntry } from '../store'

export interface DiscoveryRow {
  address: string
  exact?: string
  post: Id
  number: number | null
  replyTo: number | null
  kind: string
  title: string
}

export function navigatorIndex(at: number, key: string, length: number): number | null {
  if (!length) return null
  const d = key === 'ArrowLeft' || key === 'ArrowUp' ? -1
    : key === 'ArrowRight' || key === 'ArrowDown' ? 1 : 0
  return d ? (at + d + length) % length : null
}

/** Group only posts that actually carry objects: no empty reply filler rows. */
export function groupDiscovery<T extends DiscoveryRow>(items: T[], posts: Id[]): { post: Id; items: T[] }[] {
  const by = new Map<Id, T[]>()
  for (const item of items) by.set(item.post, [...(by.get(item.post) ?? []), item])
  const order = [...posts, ...items.map((x) => x.post).filter((id) => !posts.includes(id))]
  return [...new Set(order)].flatMap((post) => {
    const found = by.get(post)
    return found?.length ? [{ post, items: found }] : []
  })
}

/** The selected post and every reply below it, at any depth. The
 * conversation-wide Contents read has already loaded these posts, so changing
 * what is read only narrows that index; it does not start another object read. */
export function postSubtree(root: Id | null, posts: Id[], parentOf: (post: Id) => Id | null | undefined): Set<Id> {
  if (!root) return new Set()
  const found = new Set<Id>([root])
  let changed = true
  while (changed) {
    changed = false
    for (const post of posts) {
      if (found.has(post) || !found.has(parentOf(post) ?? '')) continue
      found.add(post)
      changed = true
    }
  }
  return found
}

export type ContentsScope = 'conversation' | 'post'

/** Saved arrangements from before post scope have no option and continue to
 * mean the whole conversation; a saved `post` option is retained verbatim. */
export const readContentsScope = (value: unknown): ContentsScope => value === 'post' ? 'post' : 'conversation'

export const summaryRow = (o: ConversationObjectSummary): DiscoveryRow => ({
  address: o.address, exact: o.exact, post: o.post, number: o.number,
  replyTo: o.reply_to_number, kind: o.kind, title: o.title ?? o.kind,
})

export const objectRow = (o: PostObjectEntry, number: number | null, replyTo: number | null): DiscoveryRow => ({
  address: o.address.live, exact: o.address.exact, post: o.post, number,
  replyTo, kind: o.is?.chip ?? o.is?.word ?? o.type ?? o.kind,
  title: o.title ?? o.name ?? o.type,
})
