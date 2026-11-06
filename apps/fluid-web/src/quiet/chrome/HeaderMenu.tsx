/* The global header's one remaining secondary option (Open Fluid) lives
 * behind this disclosure, at the header's top left -- mirroring
 * BackgroundControl's Settings disclosure at the top right, which this
 * does not touch. The panel is always mounted and toggled with `hidden`,
 * not conditionally rendered, so its contents stay reachable to anything
 * that queries them structurally rather than only after a click. */
import { useEffect, useRef, useState } from 'react'

export default function HeaderMenu() {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); trigger.current?.focus() }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [open])
  return <div ref={root} className="qc-header-menu">
    <button ref={trigger} type="button" className="qc-menu-button" aria-label="Menu" title="Menu"
      aria-expanded={open} aria-controls="qc-menu-panel" onClick={() => setOpen(!open)}>
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
        <path d="M4 7h16M4 12h16M4 17h16" />
      </svg>
    </button>
    <nav id="qc-menu-panel" className="qc-menu-panel" aria-label="Quiet Chat menu" hidden={!open}>
      <a className="qc-fluid" href="/fluid" onClick={() => setOpen(false)}>Open Fluid ↗</a>
    </nav>
  </div>
}
