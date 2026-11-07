/* THE WORKING AREA: FLUID'S OWN ZONES, BOUNDED. Round 5, package W2.
 *
 * The stage is Fluid's Workspace (`fluid/workspace/Workspace.tsx`) over the
 * ORIGIN conversation's Holder, drawn inside a bounded root beside the Quiet
 * reading. Nothing is copied: the pages, the zone tree, the splitting and
 * merging, the Keep chooser, the link drop host, the detail column and the
 * narrow floats are the ones Fluid has, and `placeKey`/`placeKind` are W1's
 * seam for saying WHICH place owns the arrangement while another conversation
 * is read beside it.
 *
 * WHY IT WAITS FOR THE RUNTIME (`place.ts:969`). A second `enter` for the same
 * place returns immediately, so the first entrance decides what is drawn. The
 * runtime's entrance carries the browser copy (F9); Workspace's own
 * `usePlace` effect carries nothing, and a child's effect runs BEFORE its
 * parent's. So the stage does not mount Workspace for this place until the
 * Holder already holds it -- and then Workspace's own entrance is the no-op
 * the guard makes it, under the same kind, which is why the kind is supplied
 * rather than worked out twice.
 *
 * THE CONVERSATION ZONE IS A STAND-IN (F1). Quiet never mounts Fluid's
 * ConversationColumn and never lets a ConvLeaf claim the conversation's host:
 * there is ONE Quiet reader and ONE composer and they stay in the reading
 * slot. A zone that would show the conversation says so, in those words, with
 * a working Return to conversation -- and keeps its section frame, so the
 * stored zone, its splits, its merges and their Undo are all exactly what they
 * were.
 *
 * WHAT IS NOT HERE YET IS SAID SO. The floating windows, the Magnet discs and
 * the object/Peek viewer are package O's hosts, mounted into the measured area
 * through `ObjectHosts`; until they land, a Peek is refused in words and a
 * float on the page is reported rather than drawn invisibly. Tidy is package
 * T's, at the one controls point below.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { closeInspect, useMediaOpen } from '../../fluid/present'
import { useArr, workspace } from '../../fluid/workspace/place'
import { useNarrow } from '../../fluid/frame/narrow'
import { pageView } from '../../fluid/focus/page'
import { SectionChrome } from '../../fluid/surface/SurfaceChrome'
import * as nav from '../../fluid/nav'
import type { ConversationZone } from '../../fluid/workspace/Workspace'
import Workspace from '../../fluid/workspace/Workspace'
import type { WorkingAreaView } from '../contract'
import ObjectHosts from './ObjectHosts'
/* `Tidy.tsx` and `tidy.ts` differ only in case, so an extensionless import of
   either is ambiguous on a case-insensitive filesystem and tsc refuses it
   (TS1261). The extension is explicit until S renames one of the pair; the
   manifest's two paths are unchanged. */
import Tidy from './Tidy.tsx'
import WorkingProviders from './providers'
import { hostWorkingNavigation, placeKindOf } from './runtime'
import './working.css'

/** Where the Quiet reading is, for the focus a Return to conversation gives
 *  back (`QuietChat.tsx`'s own ids; the stream is what reads, the region is
 *  what always exists). */
function focusTheReading(): void {
  const el = document.getElementById('qc-stream') ?? document.getElementById('qc-reading')
  el?.focus({ preventScroll: true })
}

/** Has the Holder entered this place? The entrance is the runtime's, and this
 *  is the Holder's own answer to it rather than a second copy of the
 *  question. */
function useHolds(key: string): boolean {
  const [holds, setHolds] = useState(() => workspace.key === key)
  useEffect(() => {
    const look = () => setHolds(workspace.key === key)
    look()
    return workspace.subscribe(look)
  }, [key])
  return holds
}

const WorkingArea: WorkingAreaView = ({
  originConversation,
  effectiveConversation,
  page,
  readingPost,
  onNavigate,
}) => {
  const holds = useHolds(originConversation)
  const kind = useMemo(() => placeKindOf(originConversation), [originConversation])
  const arr = useArr()

  /* THE ONE WAY OUT, LENT TO THE NAV ADAPTER. `fluid/nav.ts` reports a
     cross-conversation read or detail and applies none of it; the runtime
     needs this very function to route it, and the shell gives it to the area
     rather than to the hook. */
  useEffect(() => hostWorkingNavigation(onNavigate), [onNavigate])

  /* THE MEASURED STAGE, for O's hosts and T's Tidy: the element itself, once
     it is in the document, so a float is scoped to this area and cannot cover
     the Quiet composer or toolbar. */
  const stage = useRef<HTMLDivElement | null>(null)
  const [area, setArea] = useState<HTMLElement | null>(null)
  useLayoutEffect(() => {
    setArea(stage.current)
  }, [holds])

  /* WHETHER O'S HOSTS ARE THERE, asked of what `ObjectHosts` actually drew:
     the bootstrap draws nothing, and O's body draws its layers. No package
     has to tell the other. */
  const hostsRoot = useRef<HTMLDivElement | null>(null)
  const [hosts, setHosts] = useState(false)
  useLayoutEffect(() => {
    setHosts(!!hostsRoot.current && hostsRoot.current.childElementCount > 0)
  })

  /* A PEEK WITH NOWHERE TO BE DRAWN IS REFUSED IN WORDS. `inspect` is the
     existing viewer's (`present/viewer.tsx`) and its host is O's; without it
     the press would look like it worked and show nothing. */
  const inspecting = useMediaOpen()
  useEffect(() => {
    if (!inspecting || hosts) return
    closeInspect()
    nav.toast({ text: 'Looking closer at an object in the working area is not available yet.' })
  }, [inspecting, hosts])

  /* A FLOAT ON THIS PAGE WITH NO HOST IS REPORTED, NOT DRAWN INVISIBLY. The
     arrangement keeps it either way -- it is the reader's -- so this says
     where it has gone rather than throwing it away. */
  const narrow = useNarrow()
  const floating = useMemo(() => (pageView(arr, page).focus?.floats ?? []).length, [arr, page])
  /* Narrow, Workspace lists them itself (`focus/NarrowFloats.tsx`), so there
     is nothing missing to report. */
  const unhosted = !narrow && !hosts ? floating : 0

  const returnToConversation = useCallback(() => {
    onNavigate({ conversation: effectiveConversation, turn: readingPost })
    focusTheReading()
  }, [onNavigate, effectiveConversation, readingPost])

  /* THE CONVERSATION ZONE'S STAND-IN (F1), with ConvLeaf's own arguments so
     the same zone is drawn on the same page with the same section controls --
     split, merge, close, drag and their Undo all unchanged. */
  const renderConversation = useCallback<ConversationZone>(
    ({ z, ctl, page: on }) => {
      const name = z.name ?? 'Conversation'
      return (
        <section
          className="wk-zone wk-panel qw-conv-stand"
          aria-label={`${name} section`}
          data-zone="conversation"
          data-zone-name={name}
          data-page={on}
        >
          <SectionChrome
            id={z.id}
            name={name}
            ctl={ctl}
            kind="conversation"
            title={<span className="wk-what">{name}</span>}
            body={
              <div className="wk-zbody qw-conv-body">
                <p className="qw-stand-says" role="note">
                  Conversation is in the reading area.
                </p>
                <button type="button" className="qw-stand-go" onClick={returnToConversation}>
                  Return to conversation
                </button>
              </div>
            }
          />
        </section>
      )
    },
    [returnToConversation],
  )

  return (
    <WorkingProviders
      originConversation={originConversation}
      effectiveConversation={effectiveConversation}
      page={page}
      onNavigate={onNavigate}
    >
    <div className="qw-area" role="group" aria-label="Working area">
      <div className="qw-stage" ref={stage}>
        {holds ? (
          <Workspace
            placeKey={originConversation}
            placeKind={kind}
            renderConversation={renderConversation}
          />
        ) : (
          <p className="qw-area-empty">Opening this working area…</p>
        )}
        {/* O's hosts, inside the measured stage; the controls point is T's. */}
        <div className="qw-hosts" ref={hostsRoot}>
          <ObjectHosts
            areaElement={area}
            originConversation={originConversation}
            effectiveConversation={effectiveConversation}
            page={page}
            onNavigate={onNavigate}
          />
        </div>
      </div>
      <div className="qw-controls" data-slot="workspaceControls">
        <Tidy areaElement={area} originConversation={originConversation} page={page} />
      </div>
      {unhosted > 0 && (
        <p className="qw-unavailable" role="status">
          {unhosted === 1
            ? 'One floating window on this page is kept, and is not drawn here yet.'
            : `${unhosted} floating windows on this page are kept, and are not drawn here yet.`}
        </p>
      )}
    </div>
    </WorkingProviders>
  )
}

export default WorkingArea
