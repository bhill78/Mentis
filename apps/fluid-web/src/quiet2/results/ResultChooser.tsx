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
  checkedWords, isRefresh, pageWords, rowsOf, withMoreItems, withOlderGroups, type ResultRow,
} from './words'
import './results.css'

/** How a row is keyed, so React keeps the same row across a paging read. */
const keyOf = (r: ResultRow, i: number): string =>
  r.row === 'group' ? `g:${r.group.id}`
  : r.row === 'item' ? `i:${r.group.id}:${r.item.ref}:${i}`
  : r.row === 'more-items' ? `mi:${r.group.id}`
  : r.row === 'more-groups' ? 'mg'
  : `b:${i}`

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
    setBusy(key)
    setFailed(null)
    try {
      add(await read())
    } catch (e) {
      if (isRefresh(e)) { setStale(true); setShown(page) }
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
      {rows.map((r, i) => {
        const key = keyOf(r, i)
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
            <button key={key} role="menuitem" type="button"
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
