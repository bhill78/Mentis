import { useState, type ReactNode } from 'react'

/** Presentation paging over a read already held; never claims a server total. */
export default function Bounded<T>({ items, label, listClass, children }: {
  items: T[]; label: string; listClass?: string; children: (item: T, index: number) => ReactNode
}) {
  const [page, setPage] = useState(0)
  const start = Math.min(page * 5, Math.max(0, Math.ceil(items.length / 5) - 1) * 5)
  if (!items.length) return null
  return <div className="ei-bounded">
    <p className="ei-aside ei-faint">{label}: {items.length} in this read · showing {start + 1}–{Math.min(start + 5, items.length)}</p>
    {listClass ? <ol className={listClass}>{items.slice(start, start + 5).map((item, index) => children(item, start + index))}</ol> : items.slice(start, start + 5).map((item, index) => children(item, start + index))}
    {items.length > 5 && <p className="ei-acts">
      <button className="ei-link" disabled={!start} onClick={() => setPage(start / 5 - 1)}>Previous</button>{' · '}
      <button className="ei-link" disabled={start + 5 >= items.length} onClick={() => setPage(start / 5 + 1)}>Next 5 {label.toLowerCase()}</button>
    </p>}
  </div>
}
