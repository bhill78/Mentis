/* TRACK D: in-content search, behaving like Fluid's own search-in (⌕ /
 * Ctrl+F opens a slide-out field that searches #qc-stream, reusing
 * fluid/search-in whole -- match.ts, highlight.ts, kept.ts and FocusSearch's
 * own `useFocusSearch` hook for its open state, hotkey and bar). The only
 * thing owned here is where the field sits: a slide-out aligned with the
 * reading column (#qc-reading), not the header's own cell, so it reads over
 * what it searches rather than off at the strip's corner. */
import { useEffect, useState, type CSSProperties } from 'react'
import { useFocusSearch } from '../../fluid/search-in/FocusSearch'
import './search.css'

function useReadingColumnRect(enabled: boolean) {
  const [rect, setRect] = useState<{ left: number; width: number } | null>(null)
  useEffect(() => {
    if (!enabled) return
    const measure = () => {
      const el = document.getElementById('qc-reading')
      setRect(el ? { left: el.getBoundingClientRect().left, width: el.getBoundingClientRect().width } : null)
    }
    measure()
    const el = document.getElementById('qc-reading')
    const ro = el ? new ResizeObserver(measure) : null
    ro?.observe(el!)
    window.addEventListener('resize', measure)
    return () => { ro?.disconnect(); window.removeEventListener('resize', measure) }
  }, [enabled])
  return rect
}

export default function QuietSearch() {
  const { open, setOpen, bar } = useFocusSearch(
    () => document.getElementById('qc-stream'),
    () => document.body,
    'qc-stream',
  )
  const rect = useReadingColumnRect(open)
  const style = rect ? { left: rect.left, width: rect.width } as CSSProperties : undefined
  return <div className="qc-search">
    <button type="button" className="qc-tool-button" aria-label="Search in this conversation"
      aria-expanded={open} title="Search in this conversation (Ctrl+F)"
      onClick={() => setOpen(!open)}>⌕</button>
    {open && bar && <div className="qc-search-slide" style={style}>{bar}</div>}
  </div>
}
