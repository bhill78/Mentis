/* What Home's section bodies share: the store hook, the not-read-yet mark
 * and the row of filter words. */

import { useCallback, useSyncExternalStore } from 'react'
import { store } from '../store'

export function useKey<T>(key: string, read: () => T): T {
  const sub = useCallback((fn: () => void) => store.subscribe(key, fn), [key])
  return useSyncExternalStore(sub, read)
}

/** Not read yet: nothing is said, rather than "nothing here" before it is known. */
export const READING = <div className="fw-reading" aria-busy="true" />

export function Filters<K extends string>({ label, className, value, items, onPick }: {
  label: string; className: string; value: K
  items: { key: K; label: string; count?: number }[]; onPick: (k: K) => void
}) {
  return (
    <div className={'fw-filters ' + className} role="tablist" aria-label={label}>
      {items.map((s) => (
        <button key={s.key} className={'fw-tab' + (value === s.key ? ' on' : '')} role="tab" aria-selected={value === s.key} onClick={() => onPick(s.key)}>
          {s.label}
          {s.count !== undefined && <span className="fw-tab-count"> ({s.count})</span>}
        </button>
      ))}
    </div>
  )
}
