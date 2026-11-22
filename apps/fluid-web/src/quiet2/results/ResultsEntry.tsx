/* THE WAY IN TO A WORK'S RESULTS (result navigation, part N-B).
 *
 * One small control, drawn wherever a Work is already being talked about: on
 * the post that asked for the work, on a post the record maps as that work's
 * own update, and on a Latest row. It says how many results there are and
 * opens the chooser; it never claims one of them is the result.
 *
 * WHY A POST HAS ONE AT ALL is the server's fact, passed in by the host (the
 * Work's `origin` Turn, or one of its exact `update_turns`). Nothing here
 * decides it from an author, a nearest reply, a post's expectations or
 * proximity, so a carrier's ordinary remark never acquires a chooser.
 *
 * It comes BEFORE the routine activity beside it -- the status line, the
 * chronological rows -- because what the work produced is what a person came
 * looking for; the activity stays exactly as it was, under it. */
import { useEffect, useRef, useState } from 'react'
import type { PostResults, ResultsHost } from './host'
import { entryWords, totalsOf } from './words'
import ResultChooser from './ResultChooser'
import './results.css'

/** Why these results are offered here, said plainly on the control. */
const WHY: Record<PostResults['mapping'], string> = {
  request: 'this post asked for the work',
  update: 'the record maps this post as an update of the work',
  work: 'the results recorded under this work',
}

export default function ResultsEntry({ results, host, inline = false }: {
  results: PostResults
  host: ResultsHost | null
  /** drawn inside a menu (the Latest list): the control is that menu's own
   *  row, so it takes `role="menuitem"` and the chooser opens under it */
  inline?: boolean
}) {
  const [open, setOpen] = useState(false)
  const button = useRef<HTMLButtonElement>(null)
  const wrap = useRef<HTMLDivElement>(null)
  const t = totalsOf(results.page)

  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', away)
    return () => document.removeEventListener('pointerdown', away)
  }, [open])

  /* Closed from inside the chooser (Escape, or a result was opened): focus
     comes back to the control that opened it, which is still here. */
  const close = () => { setOpen(false); requestAnimationFrame(() => button.current?.focus()) }

  const words = entryWords(results.page)
  const said = `${words} · ${WHY[results.mapping]}`
  return (
    <div ref={wrap} className={'q2r-entry-wrap' + (inline ? ' q2r-inline' : '')} data-work={results.work}>
      <button ref={button} type="button" className="q2r-entry" role={inline ? 'menuitem' : undefined}
        aria-haspopup="menu" aria-expanded={open}
        aria-label={`Results of ${results.title ?? 'this work'}: ${said}`} title={said}
        disabled={!t.items}
        onClick={() => setOpen(!open)}>
        <span className="q2r-entry-what">Results</span>
        <span className="q2r-entry-count">{words}</span>
      </button>
      {open && (
        <ResultChooser work={results.work} title={results.title} page={results.page} host={host} onClose={close} />
      )}
    </div>
  )
}
