/* THE RECORD MOVED: a counter that goes up when Mentis says its record
 * advanced (the same beat `useApi` readers hear), at most once in a while so
 * a busy Brain does not re-read a list on every act. */
import { useEffect, useState } from 'react'
import { hearAdvance } from '../../api'

export function useBeat(spacingMs = 1500): number {
  const [beat, setBeat] = useState(0)
  useEffect(() => {
    let timer: number | null = null
    const stop = hearAdvance((moved) => {
      if (moved !== 'durable' || timer !== null) return
      timer = window.setTimeout(() => { timer = null; setBeat((n) => n + 1) }, spacingMs)
    })
    return () => { stop(); if (timer !== null) clearTimeout(timer) }
  }, [spacingMs])
  return beat
}
