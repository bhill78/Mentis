/* WHAT TAKES THE CENTRE COLUMN, IN THE BROWSER'S OWN HISTORY.
 *
 * THE DEFECT THIS ANSWERS (owner, 2026-11-16): opening a source, then a file,
 * and pressing Back went to a different Mentis server. Quiet Chat recorded
 * nothing in the browser's history, so the browser's Back (the button, a
 * mouse's back key, Alt+Left, a swipe) did not go back inside Quiet Chat at
 * all: it left the page for whatever the tab had shown before it, which for
 * somebody moving between TEST and DAY-TO-DAY is the other server.
 *
 * Now each thing that takes the centre column -- a source, a file read in
 * place, Add a source, a Brain record and the records reached from it -- is an
 * entry of the browser's history, on the page's own address. Nothing here
 * names a server or builds a URL: an entry is pushed with no address, so it
 * can only ever be this page, on this origin.
 *
 * ONE WAY BACK, NOT TWO. The page's own Back controls do not set state
 * beside the history: `go` looks for the place asked for among the entries
 * behind this one and, finding it, asks the BROWSER to go back to it; the
 * state is then set where the browser reports it (`popstate`), exactly as it
 * is when the reader presses the browser's Back themselves. Only a place that
 * is not behind is pushed. So the in-page Back and the browser's Back walk
 * the same entries and can never disagree.
 *
 * The entries carry the place as plain data (`history.state.q2c`) and their
 * position (`q2i`). What was behind a reload is not known to this page, so
 * after one a place asked for is pushed rather than searched for; that is
 * only ever a longer history, never a wrong one.
 *
 * `plan` is the decision, apart from the browser, so it is checkable
 * (`tests/quiet_sources_unit.ts`). */
import { useEffect, useRef } from 'react'

export type How = 'push' | 'pop' | 'replace'

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)

/** Where `to` is to be found: how many entries back (a negative number), 0
 *  when it is already the place shown, or null when it must be pushed. The
 *  search stops at the first entry this page does not know (before a reload). */
export function plan<T>(trail: (T | null | undefined)[], at: number, to: T | null): number | null {
  if (same(trail[at], to)) return 0
  for (let j = at - 1; j >= 0; j--) {
    if (trail[j] === undefined) return null
    if (same(trail[j], to)) return j - at
  }
  return null
}

interface Held { q2c?: unknown; q2i?: number }

/** `apply(to, from, how, asked)` sets the page to `to`. `asked` is false only
 *  when the browser moved on its own (its Back or Forward), so the page can
 *  do there what its own Back would have done. */
export function useCentreHistory<T>(apply: (to: T | null, from: T | null, how: How, asked: boolean) => void) {
  const trail = useRef<(T | null | undefined)[]>([null])
  const at = useRef(0)
  const then = useRef<(() => void) | null | undefined>(undefined)
  const now = useRef(apply)
  now.current = apply

  useEffect(() => {
    /* this page's first entry: the conversation, wherever in the tab's history it is */
    const held = (history.state ?? {}) as Held
    const i = typeof held.q2i === 'number' ? held.q2i : 0
    const first: (T | null | undefined)[] = []
    first[i] = null
    trail.current = first
    at.current = i
    history.replaceState({ ...held, q2c: null, q2i: i }, '')
    const pop = (e: PopStateEvent) => {
      const s = (e.state ?? null) as Held | null
      const ours = !!s && typeof s.q2i === 'number'
      const from = trail.current[at.current] ?? null
      const to = ours ? ((s!.q2c ?? null) as T | null) : null
      if (ours) { at.current = s!.q2i!; trail.current[at.current] = to }
      const after = then.current
      then.current = undefined
      now.current(to, from, 'pop', after !== undefined)
      after?.()
    }
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [])

  /** to this place: back to it where it is behind, else forward to it */
  const go = (to: T | null, after?: () => void) => {
    const step = plan(trail.current, at.current, to)
    if (step === 0) { after?.(); return }
    if (step !== null) { then.current = after ?? null; history.go(step); return }
    const from = trail.current[at.current] ?? null
    trail.current.length = at.current + 1
    trail.current.push(to)
    at.current += 1
    history.pushState({ ...((history.state ?? {}) as Held), q2c: to, q2i: at.current }, '')
    now.current(to, from, 'push', true)
    after?.()
  }
  /** the place shown becomes this one, with no new entry (a record just made;
   *  a choice inside one page) */
  const replace = (to: T | null) => {
    const from = trail.current[at.current] ?? null
    trail.current[at.current] = to
    history.replaceState({ ...((history.state ?? {}) as Held), q2c: to, q2i: at.current }, '')
    now.current(to, from, 'replace', true)
  }
  return { go, replace }
}
