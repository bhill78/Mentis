/* THE CLASS AND THE INPUT THE CHROME DRAWS FOR (part P4).
 *
 * §3.1 gives `usePresentationClass`, `inputMode` and `useInputMode` to P5
 * (frame/narrow.ts). Until P5 lands, the chrome reads them here, by the same
 * rules: the class from the viewport width (narrow.ts presentationClass),
 * coarse input where the pointer is coarse or nothing hovers. P5 points these
 * at its hooks and this file goes. */

import { useSyncExternalStore } from 'react'
import { presentationClass } from '../frame/narrow'
import type { InputMode, PresentationClass } from './types'

const COARSE = '(pointer: coarse), (hover: none)'
const coarseQuery = typeof matchMedia !== 'undefined' ? matchMedia(COARSE) : null

export const inputMode = (): InputMode => (coarseQuery?.matches ? 'coarse' : 'fine')
export const classNow = (): PresentationClass => presentationClass(typeof window === 'undefined' ? 1280 : window.innerWidth)

const fns = new Set<() => void>()
const emit = () => fns.forEach((fn) => fn())
coarseQuery?.addEventListener('change', emit)
if (typeof window !== 'undefined') window.addEventListener('resize', () => emit())
const subscribe = (fn: () => void) => { fns.add(fn); return () => { fns.delete(fn) } }

export const useInputMode = () => useSyncExternalStore(subscribe, inputMode)
export const useClassNow = () => useSyncExternalStore(subscribe, classNow)
