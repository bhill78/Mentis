/* The workspace's motion, in the demo's one language (spec 1.7): a
 * translucent clone that flies from where a thing was to where it went, and
 * the ring that flashes on the card a detail returns into. */

const reduced = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches

/** A clone from `from` to `to`: the target is at least 60 wide and 30..140
 *  tall, it ends at .2 opacity and is gone at 470ms. */
export function fly(from: Element | null, to: Element | null) {
  if (!from || !to || reduced()) return
  const a = from.getBoundingClientRect(), b = to.getBoundingClientRect()
  const f = document.createElement('div')
  f.className = 'wk-fly'
  Object.assign(f.style, { left: a.left + 'px', top: a.top + 'px', width: a.width + 'px', height: a.height + 'px' })
  document.body.appendChild(f)
  void f.offsetWidth
  Object.assign(f.style, {
    left: b.left + 'px', top: b.top + 'px', width: Math.max(60, b.width) + 'px',
    height: Math.max(30, Math.min(b.height, 140)) + 'px', opacity: '.2',
  })
  setTimeout(() => f.remove(), 470)
}

/** The return flash: a 2px accent ring that fades over 900ms. */
export function flash(el: Element | null) {
  if (!el || !(el as HTMLElement).animate) return
  ;(el as HTMLElement).animate(
    [{ boxShadow: '0 0 0 2px var(--wk-accent)' }, { boxShadow: '0 0 0 0 transparent' }],
    { duration: reduced() ? 10 : 900 },
  )
}

/** Where a page's tab is drawn, for the clone to fly to. The frame draws the
 *  tabs; `data-tab` is the demo's hook and the stub's. */
export const tabFor = (id: string) => document.querySelector(`[data-tab="${CSS.escape(id)}"]`)
