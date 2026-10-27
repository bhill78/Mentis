/* Subscriptions: each component hears only what it shows. */

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { store, whenQuiet, type Id } from '../store'

export function useKey<T>(key: string, read: () => T): T {
  const sub = useCallback((fn: () => void) => store.subscribe(key, fn), [key])
  return useSyncExternalStore(sub, read)
}
export const usePost = (id: Id) => useKey('post:' + id, () => store.posts.get(id))
export const useCollection = (key: string) => useKey('coll:' + key, () => store.collections.get(key))
export const useConversation = (id: Id | null) => useKey('conv:' + id, () => (id ? store.conversations.get(id) : undefined))
export const useList = () => useKey('coll:conversations', () => store.list)
export const useError = () => useKey('error', () => store.error)
export const usePostObjects = (root: Id) => useKey('objects:' + root, () => store.postObjects.get(root))
export const useObject = (address: string) => useKey('obj:' + address, () => store.objects.get(address))
export const useKept = () => useKey('kept', () => store.kept)
export const useIsKept = (address: string) => useKey('keep:' + address, () => store.isKept(address))
export const useSelection = () => useKey('selection', () => store.selected)

export const useNav = () => useSyncExternalStore(nav.subscribe, nav.snapshot)

/** `id` once the store's own reads have gone quiet after it was given
 *  (`store.whenQuiet`), null until then: what a decoration of a conversation
 *  is read for, so it is asked after the conversation's posts, not with them. */
export function useAfterReads<T>(id: T | null): T | null {
  const [ready, setReady] = useState<T | null>(null)
  useEffect(() => {
    if (id === null) { setReady(null); return }
    let live = true
    void whenQuiet().then(() => { if (live) setReady(id) })
    return () => { live = false }
  }, [id])
  return ready === id ? ready : null
}
