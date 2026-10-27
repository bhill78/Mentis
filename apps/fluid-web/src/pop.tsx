import { useLayoutEffect, useRef, type HTMLAttributes, type RefObject } from 'react'

/* ------------------------------------------------------------------------ *
 * A POPOVER THAT PLACES ITSELF BY THE ROOM IT HAS (UI polish 1 · review F1,
 * F2, F4).
 *
 * `.pop` hangs under its button, right edge to right edge. Which way it
 * opened used to be decided by where the button sat in the markup -- a
 * `:first-child` rule sent it rightward -- and the markup does not know
 * where the button is drawn. On a 390px phone the Turn's bar wraps and More
 * starts the second row at the left edge, so a right-anchored menu opened
 * 147px off the screen; in Compare the rightward rule sent a deleted Turn's
 * menu off the right edge, or across the divider into the other half.
 *
 * So it is MEASURED, every time it opens and whenever what it holds changes:
 * the room is the window, and every box around it that clips sideways (the
 * list of Turns scrolls, so it clips), and in Compare the half it belongs to
 * (`.pane`) -- each less a margin. It keeps its usual place -- under the button, right-aligned
 * -- when that fits, slides along the row just far enough when it does not,
 * and is never wider than the room. It stays `absolute` under its button, so
 * it scrolls with the Turn and none of the containing-block traps `anchored`
 * warns about apply. A popover some rule has made `fixed` (the phone's
 * Move to Topic… sheet) is placed by that rule and left alone here.
 *
 * UP OR DOWN is measured the same way. The edge that clips it is the nearest
 * scrolling ancestor -- the list of Turns -- not the window: a menu that fits
 * the window can still run under the composer and out of the list, which hid
 * a phone's Edit and Delete below the fold. It opens upward when it does not
 * fit below and there is more room above; a popover that scrolls its own
 * content (Move to Topic…) is also never made taller than that room.
 * ------------------------------------------------------------------------ */

const MARGIN = 8
/** The least height a popover that scrolls its own content is opened at,
 *  when it has that much to show and the list has that much room. */
const USABLE = 360

export function placeAcross(pop: HTMLElement) {
  const s = pop.style
  s.left = ''
  s.right = ''
  s.width = ''
  if (getComputedStyle(pop).position === 'fixed') return
  const anchor = pop.offsetParent?.getBoundingClientRect()
  if (!anchor) return
  const vw = document.documentElement.clientWidth
  let lo = MARGIN
  let hi = vw - MARGIN
  const within = (el: Element, r = el.getBoundingClientRect()) => {
    lo = Math.max(lo, r.left + el.clientLeft + MARGIN)
    hi = Math.min(hi, r.left + el.clientLeft + (el.clientWidth || r.width) - MARGIN)
  }
  // Compare's half, which does not clip but is where this menu belongs
  const pane = pop.closest('.pane')
  if (pane) within(pane)
  // and every box that does clip it sideways: the list of Turns scrolls, so
  // it clips, and so does a centre column drawn beside the rail's spine
  for (let el = pop.parentElement; el && el !== document.body; el = el.parentElement)
    if (getComputedStyle(el).overflowX !== 'visible') within(el)
  const natural = pop.getBoundingClientRect()
  const w = Math.min(natural.width, Math.max(0, hi - lo))
  // where it would be anyway, then slid only as far as the room demands
  const x = Math.max(lo, Math.min(anchor.right - w, hi - w))
  if (Math.abs(x - natural.left) < 0.5 && w === natural.width) return
  s.right = 'auto'
  s.left = `${x - anchor.left}px`
  s.width = `${w}px`
}

/* WHEN THE SCROLL CANNOT SHOW IT. The bar is sticky at the top of the list,
   so scrolling the list does not move a menu hanging from it: with a drawer
   open over most of a short window (1280x800), the scroll that should have
   brought the menu's foot into view moved the post instead, and the menu
   was cut off at the list's foot. Then, and only then, it is fitted to the
   room it has and scrolls what it holds -- never below a height it can be
   used at. */
const FITTED = 120

function fitBelow(pop: HTMLElement, clip: HTMLElement | null) {
  const foot = Math.min(clip ? clip.getBoundingClientRect().bottom : Infinity, window.innerHeight)
  const r = pop.getBoundingClientRect()
  const room = Math.floor(foot - r.top - MARGIN)
  if (r.bottom <= foot || room < FITTED) return
  pop.style.maxHeight = `${room}px`
  pop.style.overflowY = 'auto'
  pop.dataset.fitted = ''
}

export function placeUpDown(pop: HTMLElement) {
  if (getComputedStyle(pop).position === 'fixed') return
  if (pop.dataset.fitted !== undefined) {
    pop.style.maxHeight = ''
    pop.style.overflowY = ''
    delete pop.dataset.fitted
  }
  const anchor = pop.offsetParent?.getBoundingClientRect()
  if (!anchor) return
  let clip: HTMLElement | null = pop.parentElement
  while (clip && !/(auto|scroll)/.test(getComputedStyle(clip).overflowY)) clip = clip.parentElement
  const lim = clip ? clip.getBoundingClientRect() : { top: 0, bottom: window.innerHeight }
  const top = Math.max(lim.top, 0)
  const bottom = Math.min(lim.bottom, window.innerHeight)
  const below = bottom - anchor.bottom - 12
  const above = anchor.top - top - 12
  const want = pop.scrollHeight
  if (/(auto|scroll)/.test(getComputedStyle(pop).overflowY)) {
    /* It scrolls what it holds, so it can be cut to the larger room -- but
       not below a height it can be USED at (review 2, R3: at 1024x768 the
       Move to Topic… box was cut to 230px, its field sliced and its Link
       section out of sight with no cue). That height is all of it up to
       USABLE, and never more than the list itself can show. When neither
       side has it, it opens downward at that height and the list is
       scrolled just far enough to show it, as a plain menu's is. */
    const need = Math.min(want, USABLE, bottom - top - 24)
    if (Math.max(above, below) >= need) {
      const up = want > below && above > below
      pop.classList.toggle('opens-up', up)
      pop.style.maxHeight = `${Math.max(160, Math.min(560, up ? above : below))}px`
    } else {
      pop.classList.remove('opens-up')
      pop.style.maxHeight = `${Math.max(160, need)}px`
      pop.scrollIntoView({ block: 'nearest', inline: 'nearest' })
      fitBelow(pop, clip)
    }
    return
  }
  /* A plain menu cannot be cut short. Upward only if it fits there; otherwise
     downward, and the list scrolled just far enough to show all of it -- a
     menu hanging below a Turn lengthens the list, so that scroll always
     exists, where one hanging above the first Turn would have none. */
  const up = want > below && want <= above
  pop.classList.toggle('opens-up', up)
  if (!up && want > below) {
    pop.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    fitBelow(pop, clip)
  }
}

/* ------------------------------------------------------------------------ *
 * A FLOATING PANEL PLACED BY THE ROOM IT HAS (UI polish 2, #1).
 *
 * `anchored` (bits.tsx) decides up or down from a fixed guess -- down
 * whenever 190px are free below the control -- before the panel exists. The
 * composer's participant panel is taller than that as soon as a runtime has
 * models, so on a phone it opened down from a chip over the pinned composer
 * and its options ran off the bottom of the page, where nothing could reach
 * them.
 *
 * This measures the panel as drawn: below when all of it fits below,
 * otherwise on whichever side has more room, and never taller than that
 * room -- the panel scrolls what it holds. The room is the VISUAL viewport,
 * so a phone's keyboard counts as taken. Across, it starts at the control
 * and slides left only as far as the window demands. The panel must be
 * `position: fixed` and rendered through `Floating`, so these are the
 * window's coordinates and no ancestor can clip it.
 * ------------------------------------------------------------------------ */
export function placeFloating(pop: HTMLElement, at: HTMLElement | null, width: number, most = 460) {
  const s = pop.style
  if (!at) {
    s.visibility = 'hidden'
    return
  }
  const vv = window.visualViewport
  const vh = vv ? vv.height + vv.offsetTop : window.innerHeight
  const vw = document.documentElement.clientWidth
  const r = at.getBoundingClientRect()
  const w = Math.min(width, vw - 2 * MARGIN)
  s.position = 'fixed'
  s.visibility = ''
  s.width = `${w}px`
  s.maxWidth = `${w}px`
  s.left = `${Math.max(MARGIN, Math.min(r.left, vw - w - MARGIN))}px`
  const below = vh - r.bottom - 6 - MARGIN
  const above = r.top - 6 - MARGIN
  s.maxHeight = ''
  const want = Math.min(pop.scrollHeight, most)
  const down = want <= below || below >= above
  const room = Math.max(120, Math.min(most, down ? below : above))
  s.maxHeight = `${room}px`
  if (down) {
    s.top = `${r.bottom + 6}px`
    s.bottom = 'auto'
  } else {
    s.top = 'auto'
    s.bottom = `${window.innerHeight - r.top + 6}px`
  }
  pop.dataset.opens = down ? 'down' : 'up'
}

/** Keep a floating panel placed while it is open: when it opens, when what it
 *  holds changes (a runtime's models arrive late), and when the window or the
 *  visual viewport (a phone keyboard) changes. */
export function useFloatingPlacement(
  pop: RefObject<HTMLElement | null>,
  at: HTMLElement | null,
  width: number,
  most?: number,
) {
  useLayoutEffect(() => {
    const el = pop.current
    if (!el) return
    let busy = false
    const place = () => {
      if (busy) return
      busy = true
      placeFloating(el, at, width, most)
      busy = false
    }
    place()
    const seen = new MutationObserver(place)
    seen.observe(el, { childList: true, subtree: true, characterData: true })
    window.addEventListener('resize', place)
    window.visualViewport?.addEventListener('resize', place)
    return () => {
      seen.disconnect()
      window.removeEventListener('resize', place)
      window.visualViewport?.removeEventListener('resize', place)
    }
  }, [pop, at, width, most])
}

export default function Pop({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  const self = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const pop = self.current
    if (!pop) return
    const place = () => {
      placeAcross(pop)
      placeUpDown(pop)
    }
    place()
    // What it holds can arrive late (MoveBox reads the record) and change its
    // width; watch the content, not the box, so placing it is not a change.
    const seen = new MutationObserver(place)
    seen.observe(pop, { childList: true, subtree: true, characterData: true })
    window.addEventListener('resize', place)
    return () => {
      seen.disconnect()
      window.removeEventListener('resize', place)
    }
  }, [])
  return <div ref={self} className={'pop' + (className ? ` ${className}` : '')} {...rest} />
}
