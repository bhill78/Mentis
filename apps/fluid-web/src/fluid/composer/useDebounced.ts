import { useEffect, useState } from 'react'

/** How long typing pauses before a search goes out: the `#` palette's own
 *  250 ms (Palette.tsx), so every composer search waits alike. */
export const PAUSE_MS = 250

/** `value` once it has held still for `ms`: a read keyed on it is asked at
 *  most once per typing pause, never per keystroke. */
export function useDebounced<T>(value: T, ms = PAUSE_MS): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const t = window.setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return settled
}
