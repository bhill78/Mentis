/* THE FRAME'S LAYER: where choice sheets are drawn, above everything and
 * outside every panel (a panel's backdrop blur, or the workspace's container
 * query, would otherwise become their containing block).
 *
 * Not a React portal. A portal is react-dom's, and /fluid importing react-dom
 * asks production's shared chunk for one more export than it did before F6,
 * which renames production's exports and changes its built JS (F6 final fix
 * round, item 6). A sheet hands what it draws to this layer instead, and the
 * shell draws the layer once, at its root. */

import { Fragment, useId, useLayoutEffect, useSyncExternalStore, type ReactNode } from 'react'

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
  return <>{all.map(([k, n]) => <Fragment key={k}>{n}</Fragment>)}</>
}
