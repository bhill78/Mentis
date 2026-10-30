/* THE FLUID WORKSPACE, beside the conversation: the #184 demo's workspace
 * over the Fluid store, SHAPED BY THE READER (Fluid completion, stream A).
 *
 * Pages slide on a track: This post first, then the place's own pages (+,
 * Open as page, Keep on a new page). Every page is a tree of zones the
 * reader splits, merges, closes and resizes (TreeView.tsx); each zone follows
 * what is read, keeps what was put in it, or both (Zones.tsx). The
 * arrangement is the place's (place.ts): this tab's until saved in the
 * Brain. An object's detail opens OVER the arrangement, growing out of its
 * card; the detail column (the "beside" preference) and the Selection
 * column split off beside This post.
 *
 * Everything it shows comes from the store; where it is, what is read and
 * what is open come from the navigation contract (../nav). It writes
 * nothing to the record. */

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { isBrainRef } from '../brain/address'
import { isAsk } from '../present/NeedsYou'
import { store } from '../store'
import { DetailColumn, Overlay } from './Detail'
import { useNav } from './hooks'
import { KeepChooser } from './keep'
import { LinkDropHost } from '../conversation/linkDrop'
import { treeOf, useArr, withTree, workspace, type PlaceKind } from './place'
import Tree from './TreeView'
import { minSize, wordsZone } from './tree'
import { Side, WorkspaceZone } from './Zones'
import GovItem from '../governance/GovItem'
import { useGovNav } from '../governance/context'
import { govEntry, isGovObject } from '../governance/model'
import ConvLeaf from '../focus/ConvLeaf'
import { CONVERSATION_SHOW } from '../focus/types'
import NarrowFloats from '../focus/NarrowFloats'
import { useNarrow, usePresentationClass } from '../frame/narrow'
import { pageIn, pageView } from '../focus/page'
import { derive } from '../focus/narrowView'
import { useClosedHere } from '../surface/ClosedHere'
import { useTravelOnPage } from '../focus/travel'
import './workspace.css'

/** Which place the conversation shown is, and what kind. */
function usePlace() {
  const n = useNav()
  const c = n.conversation
  const provisional = c ? !!store.conversations.get(c)?.provisional : false
  useEffect(() => {
    if (!c) return
    const kind: PlaceKind = c === 'stream' ? 'stream' : provisional ? 'unnamed' : 'conversation'
    workspace.enter(c, kind)
  }, [c, provisional])
}

/** Mounted by the frame (frame/WorkspaceSlot.tsx), which drives ../nav. */
export default function Workspace() {
  const n = useNav()
  usePlace()
  /* the owner's travelling floats are over the page shown (focus/travel.ts) */
  useTravelOnPage()
  const arr = useArr()
  const g = useGovNav()
  const narrow = useNarrow()
  /** the governed-item pages that have been shown, and so stay mounted */
  const shownGov = useRef(new Set<string>())
  const ws = useRef<HTMLElement | null>(null)
  const [dim, setDim] = useState(false)
  const onDim = useCallback((on: boolean) => setDim(on), [])
  const i = Math.max(0, n.pages.findIndex((p) => p.id === n.page))
  /* the page whose Fluid Focus is shown (focus/page.ts) */
  const focusPage = pageIn(arr, n.page)
  /* WHAT THIS DEVICE SHOWS (P5): what is closed here is left out of every
     page's tree (a zone's id is the place's own); in compact the shown
     page's zones stack in the class's order (derive). */
  const closed = useClosedHere()
  const cls = usePresentationClass()
  const devices = useSyncExternalStore(workspace.subscribe, () => workspace.devices)
  const stackOrder = useMemo(() => (cls === 'compact' ? derive(pageView(arr, focusPage), 'compact', devices.compact).order : undefined),
    [cls, arr, focusPage, devices])
  /* The least room the page shown needs, so a boundary dragged beside the
     workspace stops before its zones have to stack (Boundary.tsx). */
  const shown = treeOf(arr, n.pages[i]?.id ?? 'this-post')
  const least = shown ? minSize(shown, 'w') : 300
  /* A page shows its objects whether or not their post is being read. A
     request kept from What needs you is no object: its card reads it (#576);
     nor is a 3D Brain object (read by BrainKept), nor a governed item's
     page (Governance), which GovItem reads. */
  useEffect(() => {
    for (const a of store.held) if (!isAsk(a) && !isGovObject(a) && !isBrainRef(a) && !store.objects.has(a)) void store.loadObject(a).catch(() => {})
  }, [arr])
  return (
    <section ref={ws} className={'wk' + (dim ? ' wk-dim' : '') + (n.detail?.kind === 'object' ? ' wk-detail-open' : '')} aria-label="workspace" data-width={n.width} data-min={least}>
      <div className="wk-track" style={{ transform: `translateX(calc(${-i * 100}% - ${i * 12}px))` }}>
        {n.pages.map((p, k) => {
          const tree = treeOf(arr, p.id)
          const first = tree ? wordsZone(tree) : undefined
          return (
            <div key={p.id} className="wk-page" data-page={p.id} aria-hidden={k !== i} inert={k !== i}>
              {'object' in p && p.object && isGovObject(p.object) ? (
                /* A governed item opened beside its conversation (Governance),
                   drawn in place of the page's zones. Drawn the first time its
                   tab is shown, then kept mounted while another page is, so an
                   act half-written in it survives a look at This post -- and
                   tabs a reload restored read nothing until somebody opens them. */
                <section className="wk-panel fg-page">
                  {(k === i || shownGov.current.has(p.id)) && (shownGov.current.add(p.id),
                    <GovItem key={`${p.object}:${g.editNonce}`} entry={govEntry(p.object)} onBack={() => g.openGov()}
                      onClose={() => g.closeItem(p.id)} />)}
                </section>
              ) : tree && (
                <Tree tree={tree} label={'title' in p ? p.title : 'This post'} page={p.id}
                  closed={closed} order={p.id === focusPage ? stackOrder : undefined}
                  onEdit={(f, words) => workspace.edit((a) => withTree(a, p.id, f(treeOf(a, p.id)!)), words)}
                  onLive={(t, done) => workspace.live(withTree(workspace.arr, p.id, t), done ? { from: withTree(workspace.arr, p.id, done.from) } : undefined)}
                  canCloseLast={false}
                  renderZone={(z, r, ctl) => z.show === CONVERSATION_SHOW
                    ? <ConvLeaf z={z} ctl={ctl} page={p.id} />
                    : <WorkspaceZone z={z} r={r} ctl={ctl} page={p.id} first={z.id === first} />} />
              )}
              {/* Narrow, the floats have nothing to float over: listed here,
                  after the shown page's tree (focus/NarrowFloats.tsx). */}
              {narrow && p.id === focusPage && n.conversation !== 'stream' && <NarrowFloats />}
              {p.id === 'this-post' && (
                <>
                  <DetailColumn />
                  <Side />
                </>
              )}
            </div>
          )
        })}
      </div>
      <Overlay ws={ws} onDim={onDim} />
      <KeepChooser />
      {/* what a drop on a post or a conversation would link, and its confirmation (W4) */}
      <LinkDropHost />
    </section>
  )
}
