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

export const summaryRow = (o: ConversationObjectSummary): DiscoveryRow => ({
  address: o.address, exact: o.exact, post: o.post, number: o.number,
  replyTo: o.reply_to_number, kind: o.kind, title: o.title ?? o.kind,
})

export const objectRow = (o: PostObjectEntry, number: number | null, replyTo: number | null): DiscoveryRow => ({
  address: o.address.live, exact: o.address.exact, post: o.post, number,
  replyTo, kind: o.is?.chip ?? o.is?.word ?? o.type ?? o.kind,
  title: o.title ?? o.name ?? o.type,
})
