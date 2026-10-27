/* THE TOAST: one at a time, bottom right, gone after 4.2s (spec section 7);
 * one that offers an action (Undo) stays 10s, the time Classic's Undo toast
 * gives (App.tsx), so there is time to act on it.
 * `nav.toast` hands its toasts here; the frame draws the current one. */

const SAYS_MS = 4200
const ACTION_MS = 10000

import { useSyncExternalStore } from 'react'
import type { Toast } from '../nav'

export interface Shown extends Toast { seq: number }

let current: Shown | null = null
let seq = 0
let timer: ReturnType<typeof setTimeout> | null = null
const listeners = new Set<() => void>()
const emit = () => { for (const fn of [...listeners]) fn() }

export function showToast(t: Toast) {
  seq += 1
  current = { ...t, seq }
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { current = null; emit() }, t.action ? ACTION_MS : SAYS_MS)
  emit()
}

export function dismissToast() {
  if (timer) clearTimeout(timer)
  current = null
  emit()
}

const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }
export const useToast = () => useSyncExternalStore(subscribe, () => current)
