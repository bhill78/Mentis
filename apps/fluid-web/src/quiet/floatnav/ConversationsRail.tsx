/* Track B: the Conversations rail collapses in place -- closing it narrows
 * its own grid column (layout.css's --qc-nav, released here through a
 * `:has()` rule in floatnav.css) rather than overlaying the page, so the
 * reading column gets the freed width back. It stays the SAME grid cell
 * QuietChat.tsx always mounted navigation in; this module only adds the
 * disclosure around what it already held. */
import { useRef, useState, type ReactNode } from 'react'
import './floatnav.css'

export default function ConversationsRail({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(() => typeof window === 'undefined' || window.innerWidth > 900)
  const toggle = useRef<HTMLButtonElement>(null)
  return <div className="qc-conversations-rail" data-open={open}>
    <button ref={toggle} type="button" className="qc-conversations-toggle"
      aria-expanded={open} aria-controls="qc-conversations-content"
      aria-label={open ? 'Hide conversations' : 'Show conversations'}
      onClick={() => setOpen((value) => !value)}>{open ? 'Conversations' : '☰'}</button>
    <div id="qc-conversations-content" className="qc-conversations-content" hidden={!open}
      onKeyDown={(e) => {
        if (e.key !== 'Escape' || e.defaultPrevented) return
        e.preventDefault()
        setOpen(false)
        toggle.current?.focus()
      }}>{children}</div>
  </div>
}
