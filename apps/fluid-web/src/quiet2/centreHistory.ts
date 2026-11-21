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
 * entry of the browser's history. Nothing here names a server: an entry is
 * pushed either with no address at all or with the one the page gives for it
 * (`Addressing.address`), which is the page's own path and a query
 * (address.ts), so it can only ever be this page, on this origin.
 *
 * AN ENTRY HAS AN ADDRESS (owner, 2026-11-20). Entries were pushed with no
 * address, so every place in Quiet Chat shared the address the page was
 * opened on: a refresh, or the address copied from the bar, went somewhere
 * else. The page now says what each entry's address is, and what the FIRST
 * entry is (read from the address it was opened with, where it used to be
 * the conversation whatever the address said). The walk through the entries
 * is exactly what it was.
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

/** Whether `to` is the entry DIRECTLY behind: the one a single Back reaches.
 *  Something that is closed (rather than left for somewhere else) goes back
 *  to it when it is, and otherwise gives up its own entry -- so closing never
 *  adds an entry whose only use would be to bring the closed thing back. */
export function isBehind<T>(trail: (T | null | undefined)[], at: number, to: T | null): boolean {
  return at > 0 && trail[at - 1] !== undefined && same(trail[at - 1], to)
}

/** Whether a move the browser has just made is one to ask about first: only
 *  the reader's own Back or Forward (a move this page asked for was guarded
 *  by whoever asked for it, and is never questioned twice), only among this
 *  page's own entries, and only where it actually changes what the centre
 *  holds -- a `popstate` that lands on the same place loses nothing. */
export function askFirst<T>(asked: boolean, ours: boolean, from: T | null, to: T | null): boolean {
  return !asked && ours && !same(from, to)
}

/** Whether a question already open is no longer worth asking: the browser has
 *  come back to the very entry the reader was on (their own Forward undoing
 *  the Back they were asked about), so nothing is being left after all. The
 *  question goes, and the page is left exactly as it was -- the answer would
 *  otherwise be about a move that is no longer happening, and would walk the
 *  browser somewhere the page is not (review ent-d960d458078c, H1). */
export function unasked(open: boolean, ours: boolean, where: number | null, was: number): boolean {
  return open && ours && where === was
}

interface Held { q2c?: unknown; q2i?: number }

/** Asked before the browser's own Back or Forward is allowed to change what
 *  the centre holds, where the page being left has unfinished work. It
 *  answers later: `go` lets the move happen, `stay` walks the browser back to
 *  the entry the reader was on. It returns false where there is nothing to
 *  ask, and then the move happens at once, exactly as it did before.
 *
 *  Asked AGAIN while a question of its own is still open, it replaces that
 *  question: the browser has moved on, and the answer must answer for where
 *  it is now, not where it was. */
export type AskFirst = (go: () => void, stay: () => void, to?: unknown, from?: unknown) => boolean

/** What a question that is no longer worth asking does: it is taken away. A
 *  reader whose own Forward undid the Back they were asked about has answered
 *  it themselves, and is left exactly where they were. */
export type Unask = () => void

/** What the page says of its entries' addresses. Both are optional: without
 *  them every entry is on the address the page has, and the first is `null`. */
export interface Addressing<T> {
  /** what the page was opened on, read from its address (the first entry) */
  first?: T | null
  /** the address of an entry: a path and query on this page, never an origin.
   *  Null leaves the address as it is. */
  address?: (to: T | null) => string | null
}

/** `apply(to, from, how, asked)` sets the page to `to`. `asked` is false only
 *  when the browser moved on its own (its Back or Forward), so the page can
 *  do there what its own Back would have done.
 *
 *  NOTHING UNSAVED IS LOST WITHOUT A QUESTION, the browser's own Back
 *  included (owner, ent-406244084c3e). The page's own controls can ask before
 *  they move; the browser's cannot, because by the time `popstate` arrives it
 *  has already moved. So `ask` is put here instead: the move is held, nothing
 *  is applied, and the reader's answer either lets it through or walks the
 *  browser back to where they were. Only the browser's own Back and Forward
 *  go through it -- a move this page asked for was guarded by whoever asked
 *  for it, and is never questioned twice. */
export function useCentreHistory<T>(apply: (to: T | null, from: T | null, how: How, asked: boolean) => void, ask?: AskFirst, unask?: Unask, addressing?: Addressing<T>) {
  const trail = useRef<(T | null | undefined)[]>([addressing?.first ?? null])
  const naming = useRef(addressing?.address)
  naming.current = addressing?.address
  /** the address of an entry, or undefined where the page gives none: the
   *  browser then keeps the address it has, as it always did */
  const named = (to: T | null) => naming.current?.(to) ?? undefined
  const at = useRef(0)
  const then = useRef<(() => void) | null | undefined>(undefined)
  const now = useRef(apply)
  now.current = apply
  const asking = useRef(ask)
  asking.current = ask
  const unasking = useRef(unask)
  unasking.current = unask
  /* THE WAY BACK FROM A MOVE THE READER TOOK BACK: `stay` asks the browser to
     return to the entry they were on, and the `popstate` that answers is this
     page's own doing, not a move to apply. It is the ENTRY it is going to,
     not a flag: a `history.go` that cannot move answers with no popstate at
     all, and a flag only ever cleared by one would swallow the reader's next
     Back for ever (independent review ent-d960d458078c, H1). */
  const returning = useRef<number | null>(null)
  /* WHERE THE BROWSER ACTUALLY IS, which while a question is open is not
     where this page is: the reader can press Back and Forward as often as
     they like before answering, and `stay` must walk back from the last of
     those presses, not from the first. */
  const browserAt = useRef<number | null>(null)
  /* A QUESTION OF OURS IS OPEN, about a move the browser has already made */
  const open = useRef(false)
  /* which walk back is the current one */
  const walk = useRef(0)
  /* THE BROWSER IS ON ITS WAY BACK: `history.go` answers later, in
     `popstate`, and until it does this page's position is not yet where it
     will be. A second Back pressed in that moment would be planned from the
     old position and go one entry too far -- out of Quiet Chat. So nothing
     else moves until the browser has said where it landed. */
  const moving = useRef(false)
  const started = useRef(false)

  useEffect(() => {
    /* this page's first entry: the conversation, wherever in the tab's
       history it is. ONCE: an effect run again (a development build runs
       each twice) must not wipe an entry made in between. */
    if (!started.current) {
      started.current = true
      const held = (history.state ?? {}) as Held
      const i = typeof held.q2i === 'number' ? held.q2i : 0
      /* THE FIRST ENTRY IS WHAT THE ADDRESS ASKED FOR, in place: nothing is
         pushed for it, so opening a link adds no entry of its own and Back
         leaves as it would from any page just opened. ITS ADDRESS IS PUT AS
         THE PAGE WRITES IT (independent review, 2026-11-20): an address
         given with a name that could not be read (a file that is not one, a
         post number that is not a number) would otherwise go on naming, for
         every refresh and bookmark, a place that is not the one shown. */
      const opened = addressing?.first ?? null
      const first: (T | null | undefined)[] = []
      first[i] = opened
      trail.current = first
      at.current = i
      browserAt.current = i
      history.replaceState({ ...held, q2c: opened, q2i: i }, '', named(opened))
    }
    const pop = (e: PopStateEvent) => {
      moving.current = false
      const s = (e.state ?? null) as Held | null
      const ours = !!s && typeof s.q2i === 'number'
      const where = ours ? s!.q2i! : null
      const from = trail.current[at.current] ?? null
      const to = ours ? ((s!.q2c ?? null) as T | null) : null
      browserAt.current = where
      /* the browser answering `stay`: it is back where the reader was, and
         the page never left, so there is nothing to apply */
      if (returning.current !== null) {
        const back = returning.current
        returning.current = null
        if (where === back) { at.current = back; return }
        /* it landed somewhere else: the walk back is over and this move is
           the reader's own, so it is treated as one */
      }
      const after = then.current
      then.current = undefined
      const asked = after !== undefined
      /* A QUESTION OF OURS IS ANSWERED, or is no longer worth asking: either
         way it is taken away before anything else happens. */
      const close = () => { if (open.current) { open.current = false; unasking.current?.() } }
      const land = () => {
        if (open.current) { open.current = false }
        if (ours) { at.current = where!; trail.current[at.current] = to }
        now.current(to, from, 'pop', asked)
        after?.()
      }
      /* THE READER'S OWN FORWARD, UNDOING THE BACK THEY WERE ASKED ABOUT.
         They are back on the entry they were on, holding the same unfinished
         work: there is nothing to leave and nothing left to ask, so the
         question goes and the page stays exactly as it was. Without this the
         answer would be about a move that is no longer happening, and the
         browser and the page would stop agreeing (review ent-d960d458078c). */
      if (unasked(open.current, ours, where, at.current)) { close(); return }
      /* THE READER'S OWN BACK OR FORWARD, off a page holding unfinished work.
         The browser has moved; this page has not, and it does not until the
         question is answered. `at.current` is left where the reader was, so
         the step back is right however many times they press. */
      if (asking.current && askFirst(asked, ours, from, to)) {
        const held = asking.current(land, () => {
          open.current = false
          /* FROM WHERE THE BROWSER IS NOW, not from where it was when the
             question was asked: it can have moved again since. */
          const back = at.current - (browserAt.current ?? at.current)
          if (!back) return
          returning.current = at.current
          /* nothing else moves until the browser says it is back, exactly as
             for this page's own Back; a browser that never answers (it should
             not happen) does not lock the page, and does not leave the next
             Back to be swallowed by a walk that never happened. The walk is
             counted, so a later one is never given up on by an earlier
             one's timeout. */
          const mine = walk.current += 1
          moving.current = true
          window.setTimeout(() => {
            moving.current = false
            if (walk.current === mine) returning.current = null
          }, 1500)
          history.go(back)
        }, to, from)
        if (held) { open.current = true; return }
      }
      /* not worth asking about after all: any question of ours goes with it */
      close()
      land()
    }
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [])

  /** to this place: back to it where it is behind, else forward to it */
  const go = (to: T | null, after?: () => void) => {
    if (moving.current) return
    const step = plan(trail.current, at.current, to)
    if (step === 0) { after?.(); return }
    if (step !== null) {
      then.current = after ?? null
      moving.current = true
      /* a browser that never answers (it should not happen) does not lock the page */
      window.setTimeout(() => { moving.current = false }, 1500)
      history.go(step)
      return
    }
    add(to, after)
  }
  /** a new entry, whatever is behind */
  const add = (to: T | null, after?: () => void) => {
    const from = trail.current[at.current] ?? null
    trail.current.length = at.current + 1
    trail.current.push(to)
    at.current += 1
    browserAt.current = at.current
    history.pushState({ ...((history.state ?? {}) as Held), q2c: to, q2i: at.current }, '', named(to))
    now.current(to, from, 'push', true)
    after?.()
  }
  /** FORWARD TO THIS PLACE, never back to it: a place the reader goes to anew
   *  each time they choose it (another conversation), so that Back returns to
   *  where they chose it FROM. `go` would find an earlier visit behind and
   *  walk back to that, and Back would then skip everything since. The place
   *  already shown still adds nothing. */
  const push = (to: T | null, after?: () => void) => {
    if (moving.current) return
    if (same(trail.current[at.current], to)) { after?.(); return }
    add(to, after)
  }
  /** OUT OF SOMETHING THAT IS CLOSED: back to `to` where one Back reaches it,
   *  else this entry becomes it (`isBehind`). */
  const back = (to: T | null, after?: () => void) => {
    if (moving.current) return
    if (isBehind(trail.current, at.current, to)) { go(to, after); return }
    replace(to)
    after?.()
  }
  /** the place shown becomes this one, with no new entry (a record just made;
   *  a choice inside one page) */
  const replace = (to: T | null) => {
    if (moving.current) return
    const from = trail.current[at.current] ?? null
    trail.current[at.current] = to
    history.replaceState({ ...((history.state ?? {}) as Held), q2c: to, q2i: at.current }, '', named(to))
    now.current(to, from, 'replace', true)
  }
  return { go, replace, push, back }
}
