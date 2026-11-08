import { useRef, useState, type ReactNode } from 'react'
import './navigation.css'

/** Fixed reading navigation, deliberately outside the working margins. */
export default function NavigationRail({ side, title, children }: {
  side: 'left' | 'right'; title: string; children: ReactNode
}) {
  const [open, setOpen] = useState(() => typeof window === 'undefined' || window.innerWidth > 1100)
  const toggle = useRef<HTMLButtonElement>(null)
  const id = `qc-navigation-${side}`
  return <aside className="qc-navigation-rail" data-side={side} data-open={open}
    aria-label={`${title} rail`} onKeyDown={(e) => {
      // A filter consumes its first Escape; the next dismisses the rail.
      if (e.key === 'Escape' && !e.defaultPrevented) {
        e.preventDefault()
        setOpen(false)
        toggle.current?.focus()
      }
    }}>
    <button ref={toggle} type="button" className="qc-navigation-toggle"
      aria-expanded={open} aria-controls={id}
      aria-label={`${open ? 'Hide' : 'Show'} ${title.toLowerCase()}`}
      onClick={() => setOpen((value) => !value)}>{title}</button>
    <div id={id} className="qc-navigation-content" hidden={!open}>{children}</div>
  </aside>
}

/** Both navigators use the same disclosure, query and Escape/focus behavior. */
export function NavigationFilter({ id, label, query, change }: {
  id: string; label: string; query: string; change: (query: string) => void
}) {
  const [open, setOpen] = useState(false)
  const toggle = useRef<HTMLButtonElement>(null)
  return <div className="qc-navigation-filter">
    <button ref={toggle} type="button" aria-label={label} aria-expanded={open}
      aria-controls={id} onClick={() => { setOpen(!open); change('') }}>Filter</button>
    {open && <input id={id} type="search" aria-label={label} placeholder="Filter…"
      autoFocus value={query} onChange={(e) => change(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.preventDefault()
          change('')
          setOpen(false)
          toggle.current?.focus()
        }
      }} />}
  </div>
}
