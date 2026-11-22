/* THE RESULT CHOOSER (result navigation, part N-B).
 *
 * What a piece of Work actually produced, close to where the Work is talked
 * about: grouped by the post that produced it, each result named as the
 * record names it, with where it came from and what makes it this Work's.
 *
 * COMPACT FIRST, COMPLETE ON ASKING. The server's overview read is bounded
 * (8 groups, 4 items each) and the detail read pages (20 x 20): what is not
 * on this page is counted and offered, so the oldest return stays reachable
 * however much review activity came after it. Nothing is hidden quietly.
 *
 * IT CHOOSES NOTHING FOR THE READER. No result is the primary, the newest is
 * not promoted, and a file's type or name buys it no prominence. Opening is
 * the shared target opener's work (part N-C) through the host; the chooser
 * hands over the exact item it was given.
 *
 * A RESULT THAT CANNOT BE OPENED STAYS ON THE LIST with its reason -- purged,
 * missing, corrupt, not held here, merely named by a claim -- because a
 * reader looking for a deliverable needs to know it is gone, not to find a
 * shorter list. A failed read of more results says so too. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { Id } from '../../api'
import type { ResultGroup, ResultPage } from '../../work/contract'
import type { ResultsHost } from './host'
import {
  checkedWords, isRefresh, pageWords, rowsOf, withMoreItems, withOlderGroups,
} from './words'
import './results.css'

/** The keyboard is on nothing: where a browser leaves it when the element
 *  that held it is removed from the document. A real control here instead
 *  means the reader put it there, and it is not ours to move. */
const onNothing = (e: Element | null): boolean =>
  !e || e === document.body || e === document.documentElement

export default function ResultChooser({ work, title, page, host, onClose, autoFocus = true }: {
  /** the Work whose results these are (its trunk expectation) */
  work: Id
  /** the Work's own title, where the read knew it */
  title: string | null
  /** the server's bounded page, exactly as it was read */
  page: ResultPage
  /** what the host lends: opening, source navigation, more pages */
  host: ResultsHost | null
  /** the chooser was closed (Escape, or a result was opened) */
  onClose?: (() => void) | null
  /** put focus on the first row when it is drawn */
  autoFocus?: boolean
}) {
  /* THE PAGE AS IT IS BEING READ: the host's page, with older groups and
     remaining items added as they are asked for. The host's own page is the
     truth it was last read as; when it changes, paging starts again from it. */
  const [shown, setShown] = useState<ResultPage>(page)
  const [busy, setBusy] = useState<string | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  useEffect(() => { setShown(page); setStale(false); setFailed(null) }, [page])

  const box = useRef<HTMLDivElement>(null)
  const items = () => [...(box.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])]
  useLayoutEffect(() => { if (autoFocus) (items()[0] ?? box.current)?.focus() }, [autoFocus])

  /* WHERE THE KEYBOARD IS LEFT WHEN A PAGING ROW ANSWERS (independent mounted
     re-review adm-31ceb17555cf, R2). A successful page is also the end of the
     row that asked for it: once a group has given up its last items, or the
     last older group has arrived, "Show the other N results here" and "All
     results" have nothing left to offer and are not drawn again. The element
     holding focus was therefore removed and focus fell to the document body,
     so Home, End and the arrows reached nothing and the reader had to find
     their way back into the menu with the pointer.
     The row that answered is replaced, in its own place in the one flat walk,
     by the results it brought: the menu item now AT THAT INDEX is the first
     of them, which is both a surviving control and the thing the reader
     asked for. Where the row is still offered (a group with more pages left)
     it keeps its own focus and nothing moves.
     ONLY THE PLACE THIS ANSWER TOOK AWAY (independent mounted re-review
     ent-fc5160b6de70, R3). An answer can arrive long after it was asked for,
     and the menu stays open while it is in flight: the reader may Tab out of
     it and be on the post's own Reply button, or anywhere else, by the time
     it lands. That place is theirs, and an Enter meant for it must not reach
     a result instead. So the row that asked is kept, not just its index, and
     the place is recovered only where this answer is what took it away: the
     row is gone from the document and the keyboard was left on nothing.
     THE READER'S OWN ROW, NOT THE ONE THAT ASKED (independent mounted
     re-review ent-11d361574f9a, R4). Waiting for a page, a reader walks on
     to another result and leaves the keyboard there. The row that asked is
     then not the place this answer owes anything to: that row's index is a
     fallback for when the reader's own row is gone with it. Each row now
     keeps its identity as the page grows (`words.ts`, rowsOf), so an added
     page leaves the chosen control exactly where it was and this recovery is
     not reached at all. Where something does take that control out of the
     document while its own result is still offered, the keyboard goes back
     to that result -- the same file, by its own reference -- and never to a
     different one, because the next Enter is meant for the file the reader
     chose. */
  const landing = useRef<
    { at: number; row: HTMLElement; held: HTMLElement | null; identity: string | null } | null
  >(null)
  useLayoutEffect(() => {
    const asked = landing.current
    if (!asked) return
    landing.current = null
    const all = items()
    if (!all.length) return
    if (box.current?.contains(document.activeElement)) return   // the row answered and is still there
    if (!onNothing(document.activeElement)) return              // the reader moved on; leave them there
    /* the exact result the reader was on, if this answer took its control
       away and the same result is still offered (drawn twice under one post,
       the first of them is still that result and not another file) */
    const own = asked.identity && asked.held && !asked.held.isConnected
      ? all.find((e) => e.getAttribute('data-control') === asked.identity) ?? null
      : null
    if (own) { own.focus(); return }
    if (asked.row.isConnected) return                           // the row survived: it was not taken away
    all[Math.min(asked.at, all.length - 1)].focus()
  }, [shown])

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onClose?.(); return }
    const all = items()
    const at = all.indexOf(document.activeElement as HTMLElement)
    const to = e.key === 'ArrowDown' ? at + 1 : e.key === 'ArrowUp' ? at - 1
      : e.key === 'Home' ? 0 : e.key === 'End' ? all.length - 1 : null
    if (to === null || !all.length) return
    e.preventDefault()
    /* drawn inside another menu (the Latest list), this walk is the one that
       applies: the list outside must not move the focus a second time */
    e.stopPropagation()
    all[(to + all.length) % all.length].focus()
  }

  /* MORE RESULTS, AND WHAT A REFUSED PAGE MEANS. A cursor the server will
     not take (it moved, or belongs to another Brain) is not an empty result
     list and not a page to append: the stale cursors are dropped and the
     first page is offered again, said in words. */
  const ask = async (key: string, read: () => Promise<ResultPage>, add: (got: ResultPage) => void) => {
    if (busy) return
    /* the row this was asked from and its place in the walk, so the answer
       can be left there (R2) and only where that row's own removal is what
       emptied the keyboard (R3); null is a press with no place to keep */
    const all = items()
    const from = all.indexOf(document.activeElement as HTMLElement)
    const asked = from >= 0 ? { at: from, row: all[from] } : null
    /* and where the keyboard actually is when the answer lands, which is not
       where it was asked from if the reader walked on while it was in flight
       (R4): the element itself, and the result it is the control for */
    const keeping = () => {
      if (!asked) return null
      const now = document.activeElement as HTMLElement | null
      const held = now && box.current?.contains(now) ? now : null
      return { ...asked, held, identity: held?.getAttribute('data-control') ?? null }
    }
    setBusy(key)
    setFailed(null)
    try {
      const got = await read()
      landing.current = keeping()
      add(got)
    } catch (e) {
      /* a refusal drops the older pages, so the row that asked may go too:
         the keyboard is left in the menu for that answer as well (R2) */
      if (isRefresh(e)) { landing.current = keeping(); setStale(true); setShown(page) }
      else setFailed(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }
  const moreItems = (group: ResultGroup, cursor: string) =>
    void ask(`mi:${group.id}`, () => host!.more!.itemsAfter(work, group.id, cursor),
      (got) => setShown((p) => withMoreItems(p, group.id, got)))
  const moreGroups = (cursor: string) =>
    void ask('mg', () => host!.more!.groupsBefore(work, cursor),
      (got) => setShown((p) => withOlderGroups(p, got)))

  const rows = rowsOf(shown, !!host?.more)
  const checked = checkedWords(shown)
  const head = `Results of ${title ?? 'this work'}`

  return (
    <div ref={box} className="q2r-chooser" role="menu" aria-label={head} tabIndex={-1} onKeyDown={onKey}>
      <p className="q2r-head" aria-hidden="true">
        <span className="q2r-head-what">{head}</span>
        <span className="q2r-head-count">{pageWords(shown)}</span>
      </p>
      {!host && (
        <p className="q2r-note">
          These results are listed here; opening them needs the conversation view.
        </p>
      )}
      {stale && (
        <p className="q2r-note q2r-stale" role="alert">
          These results moved while this was open, so the older pages were dropped. The newest page is shown.
        </p>
      )}
      {failed && (
        <p className="q2r-note q2r-failed" role="alert">Could not read more results: {failed}</p>
      )}
      {!rows.length && <p className="q2r-note">Nothing has been returned under this work yet.</p>}
      {rows.map((r) => {
        /* the row's own identity (`words.ts`, rowsOf): a result a reader has
           chosen keeps its drawn control, and its keyboard place with it,
           while earlier groups give up the rest of their files */
        const key = r.key
        if (r.row === 'group')
          return (
            <div key={key} className="q2r-group">
              {r.source && host?.openSource ? (
                <button role="menuitem" type="button" className="q2r-group-head q2r-go"
                  aria-label={`Go to ${r.heading}, the post these results came from`}
                  onClick={() => { host.openSource!({ work, group: r.group }); onClose?.() }}>
                  <span className="q2r-group-where">{r.heading}</span>
                  <span className="q2r-group-count">{r.words}</span>
                </button>
              ) : (
                <p className="q2r-group-head">
                  <span className="q2r-group-where">{r.heading}</span>
                  <span className="q2r-group-count">{r.words}</span>
                </p>
              )}
            </div>
          )
        if (r.row === 'item')
          return (
            /* ITS OWN STABLE IDENTITY (independent rendered review
               adm-d4c77f502b8c, F5). The launch a press makes names this row
               as the control to return focus to (`result:<group>:<ref>`), and
               nothing drew that name: a close whose chooser is still open had
               no way to find the row it came from. Drawn here, the identity
               the launch carries and the identity in the document are the
               same fact. */
            <button key={key} role="menuitem" type="button"
              data-control={`result:${r.group.id}:${r.item.ref}`}
              className={'q2r-item' + (r.can ? '' : ' q2r-shut')}
              aria-disabled={r.can && host ? undefined : 'true'}
              aria-label={`${r.label}. ${r.words}`}
              title={r.words}
              onClick={r.can && host ? () => { host.open({ work, group: r.group, item: r.item }); onClose?.() } : undefined}>
              <span className="q2r-item-name">{r.label}</span>
              <span className="q2r-item-words">{r.words}</span>
            </button>
          )
        if (r.row === 'more-items')
          return (
            <button key={key} role="menuitem" type="button" className="q2r-more"
              aria-label={`${r.words}, in ${r.group.id}`}
              onClick={() => moreItems(r.group, r.cursor)}>
              {busy === `mi:${r.group.id}` ? 'Reading…' : r.words}
            </button>
          )
        if (r.row === 'more-groups')
          return (
            <button key={key} role="menuitem" type="button" className="q2r-more q2r-all"
              onClick={() => moreGroups(r.cursor)}>
              {busy === 'mg' ? 'Reading…' : r.words}
            </button>
          )
        return <p key={key} className="q2r-note q2r-bounded">{r.words}</p>
      })}
      {checked && <p className="q2r-checked">{checked}</p>}
    </div>
  )
}
