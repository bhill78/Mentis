/* THE 3D BRAIN'S OWN FULL-SCREEN PRESENTATION (owner, revision of 2026-11-18,
 * ent-46aecf919fe8: "It should work with the full screen and use the same
 * canvas background the user is on, not the document vewer like overlay").
 *
 * WHAT WAS WRONG. The graph was drawn inside the generic viewer frame a PDF
 * and a picture gallery are drawn in (viewer/Viewer.tsx), inside the maximised
 * layer that frosts the page away behind a rounded, shadowed, bordered sheet.
 * A document viewer is right for a document: it is a page of something, held
 * in a frame, with a header saying where it came from. The 3D Brain is not a
 * document. It is a field, and it is the place you are standing in -- so it
 * reads as a thing laid ON the page, which is what the owner rejected.
 *
 * WHAT THIS IS INSTEAD. The same canvas the rest of Quiet Chat is drawn on
 * (`var(--canvas)`, no frosting, no sheet, no border, no shadow), filled by the
 * field, with ONE control over it: the way out. The graph's own header, tools,
 * legends and timeline are the renderer's and already float over the field
 * (`space.css` `.space-head`, `.space-tools`); nothing of them is duplicated
 * here, and nothing of the renderer, the camera or the session is reimplemented
 * -- this is a host, exactly as SpaceHost.tsx is (see its own note).
 *
 * IT IS STILL MODAL in the accessibility sense: the work row behind it is
 * `inert` while it is up (Quiet2.tsx), so focus belongs in here, Escape leaves,
 * and what opened it is focused again when it goes. That is behaviour, not
 * chrome: the owner's objection is to the document-viewer LOOK. */
import { Suspense, lazy, useEffect, useRef } from 'react'
import './space-stage.css'

/* the canvas and the graph module: loaded when the 3D Brain is first opened */
const SpaceHost = lazy(() => import('./SpaceHost'))

const CLOSE = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
)

export default function SpaceStage({ sessionId, onClose, openedBy }: {
  sessionId: string
  /** the one release path (Quiet2's `closeSpace`): never a generic close */
  onClose: () => void
  /** what opened it, focused again when it goes */
  openedBy: HTMLElement | null
}) {
  const box = useRef<HTMLDivElement>(null)
  /* what opened it, as it was when it opened: a later open elsewhere does not
     change where this one hands focus back to */
  const from = useRef(openedBy)
  useEffect(() => {
    const opener = from.current
    box.current?.querySelector<HTMLElement>('.q2-space-close')?.focus()
    /* after the row behind is no longer inert: the next frame */
    return () => { requestAnimationFrame(() => { if (opener?.isConnected) opener.focus() }) }
  }, [])
  return (
    <div className="q2-space-stage" ref={box} role="dialog" aria-modal="true" aria-label="3D Brain"
      onKeyDown={(e) => { if (e.key === 'Escape' && !e.defaultPrevented) { e.preventDefault(); onClose() } }}>
      <Suspense fallback={<p className="q2-space-wait" role="status">Loading the 3D Brain…</p>}>
        <SpaceHost sessionId={sessionId} placement="max" />
      </Suspense>
      <button type="button" className="q2-space-close" onClick={onClose}
        title="Close the 3D Brain and return to the conversation" aria-label="Close the 3D Brain">{CLOSE}</button>
    </div>
  )
}
