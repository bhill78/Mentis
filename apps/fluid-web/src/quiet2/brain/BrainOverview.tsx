/* ABOUT THIS BRAIN: a few lines inside the Brain card, with the detail folded.
 *
 *   ‹ Records      About this Brain                 ×
 *   TEST · development
 *   WHAT IT HOLDS · counts
 *     111 conversations · 11,218 posts
 *     285 knowledge records · 73 governing records, 31 in effect
 *     7,908 files · 5 connected sources
 *   ROOM ON THIS COMPUTER · sizes
 *     Database 398 MB · Files 3.26 GB
 *   TO MOVE IT
 *     About 3.7 GB as a portable backup. Includes … Leaves out …
 *   ▸ Knowledge by kind   ▸ Governing records by standing   ▸ Files by origin
 *   ▸ On disk, part by part   ▸ Not in a portable backup
 *
 * It is the Brain card's own second face, not a page and not a dashboard:
 * the card it is in stays as it was left, and "Records" goes back to it.
 * Every number is the server's (`overview.ts`); nothing is computed here. */
import { useEffect, useRef, useState } from 'react'
import {
  brainName, diskLine, diskRows, fetchBrainOverview, holdsLines, kindRows, leftOutRows, measuredWords, originRows, portableWords, standingRows,
  type BrainOverviewData, type Row,
} from './overview'
import './overview.css'

function Rows({ rows, empty }: { rows: Row[]; empty: string }) {
  if (!rows.length) return <p className="q2-bo-none">{empty}</p>
  return (
    <ul className="q2-bo-rows">
      {rows.map((r, i) => (
        <li key={i}>
          <span className="q2-bo-l">{r.label}{r.note && <span className="q2-bo-n">{r.note}</span>}</span>
          <span className="q2-bo-v">{r.value}</span>
        </li>
      ))}
    </ul>
  )
}

export default function BrainOverview({ open, onBack, onClose }: { open: boolean; onBack: () => void; onClose: () => void }) {
  const [data, setData] = useState<BrainOverviewData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [measuring, setMeasuring] = useState(false)
  const back = useRef<HTMLButtonElement>(null)
  const live = useRef<AbortController | null>(null)

  const load = (measure: boolean) => {
    live.current?.abort()
    const ctl = new AbortController()
    live.current = ctl
    setError(null)
    if (measure) setMeasuring(true)
    fetchBrainOverview(measure, ctl.signal).then(
      (got) => { if (!ctl.signal.aborted) setData(got) },
      (e: unknown) => { if (!ctl.signal.aborted) setError(e instanceof Error ? e.message : String(e)) },
    ).finally(() => { if (live.current === ctl) { live.current = null; setMeasuring(false) } })
  }

  /* read when it is opened, every time: what it says is what the Brain holds now */
  useEffect(() => {
    if (!open) return
    load(false)
    requestAnimationFrame(() => back.current?.focus({ preventScroll: true }))
    return () => { live.current?.abort(); live.current = null }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null
  const portable = data ? portableWords(data) : null
  return (
    <section className="q2-bo" aria-labelledby="q2-bo-title" data-brain-overview>
      <header className="q2-cl-head">
        <button ref={back} type="button" className="q2-bo-back" onClick={onBack} aria-label="Back to the records">‹ Records</button>
        <h2 id="q2-bo-title">About this Brain</h2>
        <button type="button" className="q2-cl-close" aria-label="Close" title="Close" onClick={onClose}>×</button>
      </header>
      <div className="q2-bo-body" aria-busy={!data && !error ? true : undefined}>
        {!data && !error && <p className="q2-bo-none" role="status">Reading the Brain…</p>}
        {error && <p className="q2-bo-none" role="alert">Could not read the Brain: {error} <button type="button" className="q2-link" onClick={() => load(false)}>Try again</button></p>}
        {data && portable && <>
          <p className="q2-bo-name" data-bo="name">{brainName(data)}</p>

          <h3>What it holds <span>counts of things</span></h3>
          <ul className="q2-bo-lines" data-bo="holds">{holdsLines(data).map((l, i) => <li key={i}>{l}</li>)}</ul>

          <h3>Room on this computer <span>sizes on disk</span></h3>
          <ul className="q2-bo-lines" data-bo="disk"><li>{diskLine(data)}</li></ul>

          <h3>To move it <span>an estimate</span></h3>
          <div className="q2-bo-move" data-bo="portable">
            <p className="q2-bo-total">{portable.total}</p>
            <p>{portable.includes}</p>
            <p>{portable.excludes}</p>
          </div>

          <div className="q2-bo-more">
            <details data-bo-detail="knowledge">
              <summary>Knowledge by kind</summary>
              <Rows rows={kindRows(data.counts.knowledge)} empty="No knowledge records yet." />
            </details>
            <details data-bo-detail="governing">
              <summary>Governing records by standing</summary>
              <Rows rows={standingRows(data.counts.governing)} empty="No governing records yet." />
              {data.counts.governing.kinds.length > 0 && <>
                <p className="q2-bo-sub">By kind</p>
                <Rows rows={kindRows(data.counts.governing)} empty="" />
              </>}
            </details>
            <details data-bo-detail="files">
              <summary>Files, by how they arrived</summary>
              <Rows rows={originRows(data)} empty="No files are held." />
              {data.counts.files.origins.length > 1 && <p className="q2-bo-hint">The same file arriving two ways is listed under each, and stored once.</p>}
              {data.counts.files.unsized > 0 && <p className="q2-bo-hint">{data.counts.files.unsized} {data.counts.files.unsized === 1 ? 'file was' : 'files were'} recorded without a size and {data.counts.files.unsized === 1 ? 'is' : 'are'} not in these sizes.</p>}
            </details>
            <details data-bo-detail="disk">
              <summary>On disk, part by part</summary>
              <Rows rows={diskRows(data)} empty="" />
            </details>
            <details data-bo-detail="left-out">
              <summary>Not in a portable backup</summary>
              <Rows rows={leftOutRows(data)} empty="Nothing of this Brain is left out." />
              <p className="q2-bo-hint">A portable backup is made with <code>{data.portable.as}</code>. The size above is an estimate: it adds up file sizes and does not check each file, and the backup’s own list of contents is not counted.</p>
            </details>
          </div>

          <p className="q2-bo-foot" data-bo="measured">
            {measuredWords(data)}{' '}
            <button type="button" className="q2-link" disabled={measuring} data-bo-measure onClick={() => load(true)}>{measuring ? 'Measuring…' : 'Measure again'}</button>
          </p>
        </>}
      </div>
    </section>
  )
}
