import { useCallback, useEffect, useRef, useState } from 'react'
import type { Toast } from './Toasts'
import { announceGoTo, type Nav } from '../nav'

export interface Notification extends Toast { at: number; unseen: boolean }
export function openNotification(nav: Nav, t: Toast) {
  nav.go({ conversation: t.conversation, topic: null, turn: t.turn, act: null,
    thread: null, depth: [], gov: null, compare: false, aux: null, from: 'shell' })
  if (t.turn) window.setTimeout(() => announceGoTo(t.turn!), 0)
}

/** Open the post an open item was asked on, at its form (P11). */
export function openItemAt(nav: Nav, conversation: string | null, turn: string) {
  nav.go({ conversation, topic: null, turn, act: null,
    thread: null, depth: [], gov: null, compare: false, aux: null, from: 'shell' })
  window.setTimeout(() => announceGoTo(turn), 0)
}

/** Only toasts actually offered are kept; the first feed read remains quiet. */
export function useNotificationHistory(corpus: string | undefined) {
  const key = corpus ? `mentis:notifications:${corpus}` : null
  const [items, setItems] = useState<Notification[]>([])
  const current = useRef<Notification[]>([])
  const opened = useRef(false)
  const storageKey = useRef<string | null>(null)
  const pending = useRef<Toast[]>([])
  const [storageError, setStorageError] = useState<string | null>(null)
  const save = useCallback((next: Notification[]) => {
    current.current = next
    setItems(next)
    if (!storageKey.current) return
    try {
      localStorage.setItem(storageKey.current, JSON.stringify(next))
      setStorageError(null)
    } catch { setStorageError('Recent notifications could not be saved on this device.') }
  }, [])
  const record = useCallback((t: Toast) => {
    if (!storageKey.current) { pending.current.push(t); return }
    // A growing burst replaces its earlier snapshot, as it does on screen.
    const root = t.key.replace(/\++$/, '')
    save([{ ...t, at: Date.now(), unseen: !opened.current },
      ...current.current.filter(n => n.key.replace(/\++$/, '') !== root)].slice(0, 50))
  }, [save])
  useEffect(() => {
    if (!key || key === storageKey.current) return
    storageKey.current = key
    let loaded: Notification[] = []
    try {
      const value: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
      if (Array.isArray(value)) loaded = value.filter(n => n && typeof n.key === 'string'
        && ['result', 'ask'].includes(n.kind) && typeof n.conversation === 'string'
        && (n.turn === null || typeof n.turn === 'string') && typeof n.headline === 'string'
        && typeof n.where === 'string' && typeof n.excerpt === 'string'
        && typeof n.convName === 'string' && typeof n.more === 'number'
        && typeof n.at === 'number' && typeof n.unseen === 'boolean').slice(0, 50)
    } catch { setStorageError('Saved notifications could not be read on this device.') }
    current.current = opened.current ? loaded.map(n => ({ ...n, unseen: false })) : loaded
    if (opened.current) save(current.current)
    else setItems(current.current)
    const waiting = pending.current.splice(0)
    waiting.forEach(record)
  }, [key, record, save])
  const onPanel = useCallback((open: boolean) => {
    opened.current = open
    if (open) save(current.current.map(n => ({ ...n, unseen: false })))
  }, [save])
  return { items, record, onPanel, storageError, unseen: items.filter(n => n.unseen).length }
}
