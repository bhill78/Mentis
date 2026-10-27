/* THE FRAME'S LAYER: where choice sheets are drawn, above everything and
 * outside every panel (a panel's backdrop blur, or the workspace's container
 * query, would otherwise become their containing block).
 *
 * Drawn with React portal (createPortal) from react-dom. */

import { Fragment, useId, useLayoutEffect, useState, useSyncExternalStore, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

let drawn: [string, ReactNode][] = []
const heard = new Set<() => void>()
const subscribe = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }
function put(id: string, node: ReactNode | null) {
  const at = drawn.findIndex(([k]) => k === id)
  if (node === null && at < 0) return
  drawn = node === null ? drawn.filter(([k]) => k !== id)
    : at < 0 ? [...drawn, [id, node]] : drawn.map((e, i) => (i === at ? [id, node] : e))
  for (const fn of [...heard]) fn()
}

/** Draw `node` in the layer while this component is mounted (null: nothing). */
export function useLayer(node: ReactNode | null) {
  const id = useId()
  useLayoutEffect(() => { put(id, node) })
  useLayoutEffect(() => () => put(id, null), [id])
}

export function Layer() {
  const all = useSyncExternalStore(subscribe, () => drawn)
  const [target, setTarget] = useState<HTMLElement | null>(null)

  useLayoutEffect(() => {
    setTarget(document.getElementById('fx-layer') ?? document.body)
  }, [])

  if (!target) return null
  return createPortal(
    <>{all.map(([k, n]) => <Fragment key={k}>{n}</Fragment>)}</>,
    target,
  )
}
