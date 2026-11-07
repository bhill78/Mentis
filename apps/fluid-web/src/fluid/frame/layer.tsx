/* THE FRAME'S LAYER: where choice sheets are drawn, above everything and
 * outside every panel (a panel's backdrop blur, or the workspace's container
 * query, would otherwise become their containing block).
 *
 * Drawn with React portal (createPortal) from react-dom. */

import { Fragment, useEffect, useId, useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
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

/** WHAT IS DRAWN IS ONE LIST, SO ONE LAYER DRAWS IT (Quiet round 5, W2).
 *  Every mounted Layer renders the same module-level `drawn`, so a second one
 *  would draw every sheet, menu and palette twice. Fluid's Shell mounts
 *  exactly one and is unaffected; Quiet has two hosts that each need the layer
 *  when the other is not drawn -- the composer's dock and the working stage --
 *  so the FIRST to mount draws, and the next in line takes over when it goes.
 *  Which host it is makes no difference to what is drawn: the list and the
 *  portal target are the same for all of them. */
const hosts: object[] = []
const hostFns = new Set<() => void>()
const tellHosts = () => { for (const fn of [...hostFns]) fn() }
function useFirstHost(): boolean {
  const me = useRef<object>({})
  const [, bump] = useState(0)
  useEffect(() => {
    const fn = () => bump((n) => n + 1)
    hostFns.add(fn)
    return () => { hostFns.delete(fn) }
  }, [])
  useLayoutEffect(() => {
    const mine = me.current
    hosts.push(mine)
    tellHosts()
    return () => {
      const at = hosts.indexOf(mine)
      if (at >= 0) hosts.splice(at, 1)
      tellHosts()
    }
  }, [])
  return hosts[0] === me.current
}

export function Layer() {
  const all = useSyncExternalStore(subscribe, () => drawn)
  const [target, setTarget] = useState<HTMLElement | null>(null)
  const draws = useFirstHost()

  /* #fx-layer CAN BE HIDDEN WITHOUT BEING UNMOUNTED: Quiet's working stage
     keeps its host mounted but under `hidden` while its room is collapsed
     (round 5, package L), and that is also the page's only `#fx-layer`. A
     sheet drawn into a hidden ancestor is invisible to everyone using this
     layer, not only to the host that is hidden -- so the check is of
     visibility, not existence, re-read whenever there is something new to
     place. */
  useLayoutEffect(() => {
    const el = document.getElementById('fx-layer')
    setTarget(el && el.offsetParent !== null ? el : document.body)
  }, [all, draws])

  if (!target || !draws) return null
  return createPortal(
    <>{all.map(([k, n]) => <Fragment key={k}>{n}</Fragment>)}</>,
    target,
  )
}
