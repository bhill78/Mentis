/* SUGGESTED PAGES (adm-c93a 5.1): a post that marks objects `page=Evidence`
 * offers "+ Evidence" beside its pages; choosing it makes that page, keeping
 * every object so marked. Choosing it again shows the same page. The tabs
 * are the frame's (frame/TopBar.tsx); what they offer and do is here. */

import { useCallback, useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { store } from '../store'
import { keepSlot, zone } from './tree'
import { workspace } from './place'

/** The page labels the post being read (and its thread) marks, in order. */
function labels(): string {
  const s = nav.snapshot()
  const root = s.reading
  if (!root) return ''
  const posts = store.threadObjects.get(root)?.posts ?? [root]
  const out: string[] = []
  for (const id of posts)
    for (const a of store.postObjects.get(id)?.addresses ?? []) {
      const st = store.objects.get(a)
      const p = st && 'object' in st ? st.object.page : null
      if (p && !out.includes(p)) out.push(p)
    }
  return out.join('\u0000')
}

export function useSuggested(): string[] {
  const reading = useSyncExternalStore(nav.subscribe, () => nav.snapshot().reading)
  const sub = useCallback((fn: () => void) => {
    const offs = [nav.subscribe(fn)]
    if (reading) offs.push(store.subscribe('objects:' + reading, fn), store.subscribe('tobjects:' + reading, fn))
    return () => offs.forEach((off) => off())
  }, [reading])
  const got = useSyncExternalStore(sub, labels)
  return got ? got.split('\u0000') : []
}

/** Make (or show) the post's page `label`: the post read, or -- from an
 *  object that names the page (`post`, a reply's or its root's) -- that
 *  object's thread. */
export function openSuggested(label: string, post?: string) {
  const had = workspace.arr.pages.find((p) => p.title === label && !p.object)
  if (had) { nav.showPage(had.id); return }
  let root = post ?? nav.snapshot().reading
  for (let up = store.posts.get(store.posts.get(root ?? '')?.reply_to ?? ''); up; up = store.posts.get(up.reply_to ?? '')) root = up.id
  const posts = root ? store.threadObjects.get(root)?.posts ?? [root] : []
  const items = posts.flatMap((id) => (store.postObjects.get(id)?.addresses ?? []).filter((a) => {
    const st = store.objects.get(a)
    return st && 'object' in st && st.object.page === label && st.object.parent === null
  }))
  const id = nav.addPage(label)
  workspace.quiet((a) => ({ ...a, pages: a.pages.map((p) => (p.id === id ? { ...p, tree: zone(null, keepSlot(items)) } : p)) }))
}
