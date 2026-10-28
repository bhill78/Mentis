/* ONE ESC, ONE THING (owner's final consolidation brief; objects/CONTRACT.md).
 *
 * Every part of Fluid that Esc can unwind registers here instead of adding a
 * window listener of its own. On Esc the handlers are asked in order of
 * priority, highest first; the first that returns true has done the one
 * thing, and nobody else is asked. Before this, Shell.tsx and TreeView.tsx
 * each listened, so one Esc both closed an open object and swapped the
 * primary back.
 *
 * The order (ESC below):
 *   sheet -> Peek / an open object -> Focus steps back -> the previous primary.
 *
 * A key typed into a field is the field's. `escapeOnce` is the pure part, for
 * the unit tests; the listener is installed once, on first registration. */

export const ESC = {
  /** a menu or chooser (frame/Sheet) */
  sheet: 500,
  /** Peek (present/viewer.tsx): leaves full screen first, then closes */
  peek: 400,
  /** an object or post detail opened over the workspace */
  detail: 300,
  /** at a narrow width, the one sheet over the column */
  pane: 250,
  /** the Focus lens: one step back through this Page's Focus history,
   *  then out of Focus to the original arrangement */
  lens: 200,
  /** the conversation's own reading focus (Column.tsx) */
  reading: 150,
  /** Make primary, swapped back (focus/bring.ts) */
  primary: 100,
} as const

export type EscHandler = (e: KeyboardEvent) => boolean

interface Entry { priority: number; handler: EscHandler; n: number }
const entries: Entry[] = []
let serial = 0
let installed = false

/** The handlers in the order Esc asks them: highest priority first; of equal
 *  priority, the one registered last first (the most recently opened). */
export function escOrder<T extends { priority: number; n: number }>(xs: readonly T[]): T[] {
  return [...xs].sort((a, b) => b.priority - a.priority || b.n - a.n)
}

/** Ask `handlers` in order until one does something. True when one did. */
export function escapeOnce(handlers: readonly { priority: number; n: number; handler: EscHandler }[], e: KeyboardEvent): boolean {
  for (const x of escOrder(handlers)) {
    if (x.handler(e)) return true
  }
  return false
}

const typing = (t: EventTarget | null) => {
  const el = t as HTMLElement | null
  return !!el && (!!el.matches?.('input, textarea, select') || !!el.isContentEditable)
}

function install() {
  if (installed || typeof window === 'undefined') return
  installed = true
  /* Bubbling, on the window: what is nearest the key keeps its own Esc (an
     open Sheet's and the selection bar's captured listeners, a composer's,
     a notice's) and stops it there; whatever reaches here is asked once. */
  window.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || e.defaultPrevented || typing(e.target)) return
    if (escapeOnce(entries, e)) e.preventDefault()
  })
}

/** Register what Esc does at `priority` (ESC): return true when it did
 *  something. Returns the unregister. */
export function onEscape(priority: number, handler: EscHandler): () => void {
  install()
  const entry: Entry = { priority, handler, n: ++serial }
  entries.push(entry)
  return () => {
    const i = entries.indexOf(entry)
    if (i >= 0) entries.splice(i, 1)
  }
}
