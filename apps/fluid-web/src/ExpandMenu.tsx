import { Fragment, useContext, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import Pop from './pop'
import { ExpandContext, type Expander, type ExpandTarget } from './expandHook'

/* ------------------------------------------------------------------------ *
 * THE EXPAND MENU, THE SAME WHEREVER SOMETHING POSTED CAN BE EXPANDED.
 *
 * A block's ⋯ carries it as its Expand group; a file, a picture and a post's
 * own words carry it behind a small ▾ beside their ↗. In every one:
 *
 *   On this page      the page showing -- or, while Replies & details shows,
 *                     the page you were last on (it says which)
 *   To page ▸         every page, each with its zones when it has more
 *                     than one
 *   On a new page     a page of your own, keeping it whatever is selected
 *
 * Nothing is offered where the surface around the Turn offers nothing.
 * ------------------------------------------------------------------------ */

export function ExpandItems({ ex, target, dismiss }: { ex: Expander; target: ExpandTarget; dismiss: () => void }) {
  const [open, setOpen] = useState(false)
  const pages = open ? ex.pages() : []
  const go = (f: () => void) => (e: React.MouseEvent) => { e.stopPropagation(); dismiss(); f() }
  return (
    <div className="rb-tools-group" role="group" aria-label="Expand">
      <div className="rb-tools-lbl" aria-hidden="true">Expand</div>
      <button tabIndex={-1} role="menuitem" className="btn quiet rb-tools-item" onClick={go(() => ex.toPage(target))}>
        <span>{ex.here()}</span>
      </button>
      <button tabIndex={-1} role="menuitem" className="btn quiet rb-tools-item" aria-expanded={open}
        onClick={(e) => { e.stopPropagation(); setOpen(!open) }}>
        <span>To page {open ? '▾' : '▸'}</span>
      </button>
      {pages.map((p) => (
        <Fragment key={p.id}>
          <button tabIndex={-1} role="menuitem" className="btn quiet rb-tools-item rb-tools-sub" data-to-page={p.id}
            title={p.zones.length > 1 ? `To “${p.label}”: the zone that already shows it, else its first` : `To “${p.label}”`}
            onClick={go(() => ex.toZone(target, null, p.id))}>
            <span>{p.label}</span>{p.current ? <span className="rb-tools-here"> · showing</span> : null}
          </button>
          {p.zones.length > 1 ? p.zones.map((z) => (
            <button key={z.id} tabIndex={-1} role="menuitem" className="btn quiet rb-tools-item rb-tools-sub rb-tools-zone"
              data-to-page={p.id} data-to-zone={z.id} aria-label={`${p.label}, ${z.label}`}
              onClick={go(() => ex.toZone(target, z.id, p.id))}>
              <span>{z.label}</span>
            </button>
          )) : null}
        </Fragment>
      ))}
      <button tabIndex={-1} role="menuitem" className="btn quiet rb-tools-item" onClick={go(() => ex.toNewPage(target))}>
        <span>On a new page</span>
      </button>
    </div>
  )
}

/** Arrow keys, Home and End move through a menu's items; Escape closes it. */
export function menuKeys(e: KeyboardEvent<HTMLElement>, close: () => void) {
  if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
    e.preventDefault()
    e.stopPropagation()
    const items = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('[role^="menuitem"]'))
    const i = items.indexOf(document.activeElement as HTMLButtonElement)
    const next = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1
      : (i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
    items[next]?.focus()
  }
  if (e.key === 'Tab') close()
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close() }
}

/** ▾ beside a ↗: the whole Expand menu, for what has no ⋯ of its own. */
export function ExpandMore({ target, label, className = '' }: { target: ExpandTarget; label: string; className?: string }) {
  const ex = useContext(ExpandContext)
  const [open, setOpen] = useState(false)
  const btn = useRef<HTMLButtonElement>(null)
  const wrap = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (open) wrap.current?.querySelector<HTMLButtonElement>('[role^="menuitem"]')?.focus()
  }, [open])
  if (!ex) return null
  const close = () => { setOpen(false); btn.current?.focus() }
  return (
    <span ref={wrap} className={'popwrap rb-up-wrap ' + className}>
      <button ref={btn} type="button" className="lab-up-more" aria-haspopup="menu" aria-expanded={open}
        aria-label={`More ways to expand ${label}`} title="Expand: on this page, to another page, or on a new page"
        onClick={(e) => { e.stopPropagation(); if (open) close(); else setOpen(true) }}>▾</button>
      {open ? (
        <>
          <div className="scrim" onClick={(e) => { e.stopPropagation(); close() }} />
          <Pop role="menu" aria-label={`Expand ${label}`} className="rb-tools-menu" onKeyDown={(e) => menuKeys(e, close)}>
            <ExpandItems ex={ex} target={target} dismiss={close} />
          </Pop>
        </>
      ) : null}
    </span>
  )
}
