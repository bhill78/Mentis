/* ------------------------------------------------------------------------ *
 * WHETHER THE READER'S HAND IS ON THE PAGE (opr-103be6dc3642, item 3).
 *
 * A finger down, a mouse button held (a scrollbar being dragged), a wheel
 * turning, or a scroll still gliding after the finger lifted: while any of
 * those is true the reader is moving the page, and nothing else may write a
 * scroll position. A write then fights the gesture -- the page snaps, or the
 * finger that was scrolling lands on whatever was put under it.
 *
 * One listener set for the whole document, installed on first use. It only
 * observes; it never cancels an event.
 * ------------------------------------------------------------------------ */

/** a scroll event this soon after the last input or the last scroll in the
 *  same glide is still the reader's own motion: momentum after a flick */
const GLIDE_MS = 140
/** a wheel is "turning" for this long after its last tick */
const WHEEL_MS = 180

let installed = false
let fingers = 0
let pressed = false
let lastWheel = -1e9
let lastInput = -1e9
/** the end of the reader's own scrolling, extended while it keeps going */
let gliding = -1e9
const waiting = new Set<() => void>()
let timer = 0

const now = () => performance.now()

function install() {
  if (installed || typeof document === 'undefined') return
  installed = true
  const opt = { capture: true, passive: true } as const
  document.addEventListener('touchstart', (e) => {
    fingers = e.touches.length
    lastInput = now()
  }, opt)
  const lift = (e: TouchEvent) => {
    fingers = e.touches.length
    lastInput = now()
    gliding = now() + GLIDE_MS
    settleSoon()
  }
  document.addEventListener('touchend', lift, opt)
  document.addEventListener('touchcancel', lift, opt)
  document.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse') pressed = true
    lastInput = now()
    noteDown(e)
  }, opt)
  /* Not passive: a tap that would land on something it was not aimed at is
     stopped here, before anything on the page hears it. */
  document.addEventListener('click', guardTap, { capture: true })
  const release = () => {
    if (!pressed) return
    pressed = false
    gliding = now() + GLIDE_MS
    settleSoon()
  }
  document.addEventListener('pointerup', release, opt)
  document.addEventListener('pointercancel', release, opt)
  window.addEventListener('blur', () => {
    pressed = false
    fingers = 0
    settleSoon()
  })
  document.addEventListener('wheel', () => {
    lastWheel = now()
    lastInput = lastWheel
    settleSoon()
  }, opt)
  /* Scroll does not bubble but it does capture. A scroll that follows the
     reader's input closely, or follows another such scroll closely, is the
     same glide; one that comes out of nowhere is somebody's code. */
  document.addEventListener('scroll', () => {
    const t = now()
    if (fingers > 0 || pressed || t - lastInput < GLIDE_MS || t < gliding) {
      gliding = t + GLIDE_MS
      settleSoon()
    }
  }, opt)
}

/* ------------------------------------------------------------------------ *
 * A TAP OPENS EXACTLY WHAT THE FINGER WENT DOWN ON (opr-4e2b70580f84).
 *
 * A browser decides what a tap clicked by looking at what is under the
 * finger when it LIFTS. If the page moved in between -- a new Turn at the
 * newest, a row above changing size -- that is the neighbour: the owner put
 * a finger on one thread and the next one opened. So for a finger or a pen,
 * a click goes through only when the control it lands on is the very
 * element the finger went down on, still on the page, and still where it
 * was. Otherwise it is dropped -- never handed to what is under it now.
 * A mouse is left alone: a browser already sends a press that went down on
 * one thing and up on another to neither of them.
 * ------------------------------------------------------------------------ */

const CONTROL =
  'button, a[href], input, select, textarea, label, summary, [role="button"], [role="radio"], [role="tab"], [role="option"], [role="menuitem"], [tabindex]'

let down: { ctl: Element | null; x: number; y: number; touch: boolean } | null = null

const controlOf = (t: EventTarget | null): Element | null =>
  t instanceof Element ? t.closest(CONTROL) : null

function noteDown(e: PointerEvent) {
  const ctl = controlOf(e.target)
  const r = ctl?.getBoundingClientRect()
  down = { ctl, x: r?.left ?? 0, y: r?.top ?? 0, touch: e.pointerType !== 'mouse' }
}

function guardTap(e: MouseEvent) {
  const d = down
  down = null
  if (!e.isTrusted || e.detail === 0 || !d || !d.touch) return
  const ctl = controlOf(e.target)
  if (!ctl && !d.ctl) return
  let ok = ctl === d.ctl && !!ctl && ctl.isConnected
  if (ok && ctl) {
    const r = ctl.getBoundingClientRect()
    ok = Math.abs(r.left - d.x) <= 2 && Math.abs(r.top - d.y) <= 2
  }
  if (ok) return
  e.preventDefault()
  e.stopImmediatePropagation()
}

/** True while the reader is moving the page by hand. */
export function handsOn(): boolean {
  install()
  const t = now()
  return fingers > 0 || pressed || t - lastWheel < WHEEL_MS || t < gliding
}

function settleSoon() {
  if (!waiting.size || timer) return
  timer = window.setTimeout(flush, 60)
}

function flush() {
  timer = 0
  if (!waiting.size) return
  if (handsOn()) {
    timer = window.setTimeout(flush, 60)
    return
  }
  const run = [...waiting]
  waiting.clear()
  for (const f of run) f()
}

/** Run `f` now if the reader's hand is off the page, or once it comes off.
 *  Each distinct function is queued once; the returned function unqueues it. */
export function whenHandsOff(f: () => void): () => void {
  install()
  if (!handsOn()) {
    f()
    return () => {}
  }
  waiting.add(f)
  settleSoon()
  return () => waiting.delete(f)
}

/** Start listening now, so the first touch on a freshly opened page is seen. */
export function watchHands(): void {
  install()
}
