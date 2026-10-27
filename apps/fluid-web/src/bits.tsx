import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { initial, whoColour } from './api'
import { Ref } from './refs'
import { useMe } from './identity'
import { RUNTIME_LABEL, RuntimeMark, hasMark } from './runtimeMarks'

/** Presentational primitives shared by surfaces. No domain logic. */

/** Every identifier this interface prints goes through here, so every one of
 *  them is inspectable in place. */
export function IdTag({ id, n = 10 }: { id: string | null | undefined; n?: number }) {
  return <Ref id={id} n={n} />
}

/** How a Participant is drawn. In order: the picture somebody chose for it;
 *  else the mark of the runtime that carried it; else its initial on its
 *  colour, as before. Every avatar in the interface comes through here, so
 *  the choice is read once, from the people list, and no caller passes it.
 *
 *  `runtime` is for a surface showing ONE piece of work -- a Turn -- and
 *  names the runtime that did that work, or null where none did (a person's
 *  Turn). Left out, it is where the Participant last ran. A chosen picture
 *  still wins, and then the runtime rides on it as a small badge, so a Turn
 *  never stops saying what wrote it. */
export function Avatar({
  id,
  alias,
  size = 32,
  runtime,
}: {
  id: string | null | undefined
  alias: string | null | undefined
  size?: number
  runtime?: string | null
}) {
  const { person } = useMe()
  const p = person(id)
  const rt = runtime !== undefined ? runtime : (p?.runtime ?? null)
  const picture = p?.avatar ?? null
  // A picture whose bytes will not load falls back rather than showing a
  // broken image. Asked again whenever the picture changes.
  const [broken, setBroken] = useState<string | null>(null)
  const shown = picture && broken !== picture ? picture : null
  const mark = hasMark(rt) ? rt : null
  return (
    <span
      className={'avatar' + (shown || mark ? ' avatar-drawn' : '')}
      aria-hidden="true"
      title={[alias, mark ? RUNTIME_LABEL[mark] : null].filter(Boolean).join(' · ') || undefined}
      style={{
        background: shown || mark ? undefined : whoColour(id),
        width: size,
        height: size,
        fontSize: Math.round(size * 0.44),
      }}
    >
      {shown ? (
        <img src={`/api/artifacts/${shown}`} alt="" onError={() => setBroken(shown)} />
      ) : mark ? (
        <RuntimeMark runtime={mark} size={size} />
      ) : (
        initial(alias)
      )}
      {shown && mark && size >= 22 && (
        <span className="avatar-badge">
          <RuntimeMark runtime={mark} size={Math.max(10, Math.round(size * 0.42))} />
        </span>
      )}
    </span>
  )
}

/* ------------------------------------------------------------------------ *
 * SURFACE CHROME.
 *
 * One drawn language for the controls that act on a surface rather than on
 * its content — minimise, close, step back. They were bare text glyphs
 * (`–`, `×`, `‹`) and read as prototype debris. Each is now a drawn mark of
 * the same weight as the pane's size presets, and every caller passes both a
 * `title` and an `aria-label`, so no capability is removed and the word is
 * still there for anyone who needs it.
 * ------------------------------------------------------------------------ */
/* THE AUTHORING MARKS ARE ORDINARY MEMBERS OF THIS SET, not a second icon
   system living in the composer. Two sets drift within one release --
   different weights, different optical sizes, different ideas of what a 14px
   mark is -- and they drift most visibly where both appear at once, which is
   exactly the composer's own row. Drawn here, on this grid, at this stroke.

   `B` and `I` are letterforms because that is what they are: there is no
   drawing of "bold" a reader recognises faster than a bold B. They are set in
   the same box, so every mark still occupies identical space. */
export type GlyphName =
  | 'minimise'
  | 'close'
  | 'back'
  | 'bold'
  | 'italic'
  | 'code'
  | 'link'
  | 'bullets'
  | 'numbers'
  | 'quote'
  | 'preview'
  | 'format'
  | 'copy'
  | 'reply'
  | 'focus'
  | 'more'
  | 'plus'
  | 'recent'
  | 'clock'
  | 'info'
  | 'edit'
  | 'trash'
  | 'dive'

export function Glyph({ name }: { name: GlyphName }) {
  const letter = name === 'bold' || name === 'italic'
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      aria-hidden="true"
      focusable="false"
      fill={letter ? 'currentColor' : 'none'}
      stroke={letter ? 'none' : 'currentColor'}
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {name === 'minimise' && <path d="M3 10.5h8" />}
      {name === 'close' && <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" />}
      {name === 'back' && <path d="M8.5 3L4.5 7l4 4" />}
      {/* start something new here */}
      {name === 'plus' && <path d="M7 2.5v9M2.5 7h9" />}
      {/* a clock turned back: what was asked before */}
      {name === 'recent' && <path d="M2.4 7a4.6 4.6 0 1 0 1.35-3.25M2.2 2.2v2.4h2.4M7 4.6V7l1.7 1.1" />}
      {/* a plain clock: how long something is kept */}
      {name === 'clock' && (
        <>
          <circle cx="7" cy="7" r="5" />
          <path d="M7 4.2V7l2 1.3" />
        </>
      )}

      {letter && (
        <text
          x="7"
          y="11"
          textAnchor="middle"
          fontSize="12"
          fontWeight={name === 'bold' ? 700 : 400}
          fontStyle={name === 'italic' ? 'italic' : 'normal'}
          fontFamily="Georgia, 'Times New Roman', serif"
        >
          {name === 'bold' ? 'B' : 'I'}
        </text>
      )}

      {/* chevrons: the one mark every writer already reads as code */}
      {name === 'code' && <path d="M5 4L2 7l3 3M9 4l3 3-3 3" />}
      {/* two halves of a chain, parted at the middle */}
      {name === 'link' && (
        <path d="M6.6 4.6 8 3.2a2.7 2.7 0 0 1 3.8 3.8l-1.4 1.4M7.4 9.4 6 10.8a2.7 2.7 0 0 1-3.8-3.8l1.4-1.4M5.6 8.4l2.8-2.8" />
      )}
      {name === 'bullets' && (
        <>
          <path d="M6 4h6M6 7h6M6 10h6" />
          <circle cx="2.8" cy="4" r="0.9" fill="currentColor" stroke="none" />
          <circle cx="2.8" cy="7" r="0.9" fill="currentColor" stroke="none" />
          <circle cx="2.8" cy="10" r="0.9" fill="currentColor" stroke="none" />
        </>
      )}
      {name === 'numbers' && (
        <>
          <path d="M6 4h6M6 7h6M6 10h6" />
          <text
            x="0.6"
            y="11.4"
            fontSize="6.4"
            fill="currentColor"
            stroke="none"
            fontFamily="ui-monospace, monospace"
          >
            123
          </text>
        </>
      )}
      {/* the margin bar a quotation is set against */}
      {name === 'quote' && <path d="M2.6 3.4v7.2M6 4.4h6M6 7h6M6 9.6h3.5" />}
      {/* an open eye: what this will look like once it is said */}
      {name === 'preview' && (
        <>
          <path d="M1.6 7S3.7 3.6 7 3.6 12.4 7 12.4 7 10.3 10.4 7 10.4 1.6 7 1.6 7Z" />
          <circle cx="7" cy="7" r="1.5" />
        </>
      )}
      {/* lines and a nib: the authoring door */}
      {name === 'format' && (
        <path d="M2.5 3.5h9M2.5 7h5.5M2.5 10.5h4M9.2 11.4l3.3-3.3-1.4-1.4-3.3 3.3-.4 1.8z" />
      )}
      {/* THE TURN'S OWN VERBS (uiux/turn item 1). Drawn as the marks a reader
          already knows from every mail and chat client, never as a private
          vocabulary; each control that uses one still carries its words. */}
      {/* two sheets, one behind the other */}
      {name === 'copy' && (
        <>
          <rect x="4.6" y="4.6" width="7" height="7" rx="1.3" />
          <path d="M9.4 2.6H3.9a1.3 1.3 0 0 0-1.3 1.3v5.5" />
        </>
      )}
      {/* the answering arrow */}
      {name === 'reply' && <path d="M5.5 3.5 2.5 6.5l3 3M2.8 6.5h5.4a3.3 3.3 0 0 1 3.3 3.3v.7" />}
      {/* four corners pulled outward: open this larger */}
      {name === 'focus' && (
        <path d="M8.6 2.4h3v3M5.4 11.6h-3v-3M11.6 2.4 8 6M2.4 11.6 6 8" />
      )}
      {/* THE MORE MENU'S VERBS, drawn on the same grid as the bar's. */}
      {/* a ringed i: what is behind it */}
      {name === 'info' && (
        <>
          <circle cx="7" cy="7" r="5" />
          <path d="M7 6.4v3.4" />
          <circle cx="7" cy="4.4" r="0.8" fill="currentColor" stroke="none" />
        </>
      )}
      {/* a pencil: write it again */}
      {name === 'edit' && <path d="M2.6 11.4l.6-2.6 6.3-6.3 2 2-6.3 6.3zM8.3 3.7l2 2" />}
      {/* a bin with its lid */}
      {name === 'trash' && <path d="M2.6 4h8.8M5.6 4V2.6h2.8V4M3.8 4l.6 7.4h5.2l.6-7.4" />}
      {/* out of here, and on into somewhere new */}
      {name === 'dive' && <path d="M5 3h6v6M11 3 3 11" />}
      {name === 'more' && (
        <>
          <circle cx="3" cy="7" r="1" fill="currentColor" stroke="none" />
          <circle cx="7" cy="7" r="1" fill="currentColor" stroke="none" />
          <circle cx="11" cy="7" r="1" fill="currentColor" stroke="none" />
        </>
      )}
    </svg>
  )
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="sec">
      <div className="label">{title}</div>
      {children}
    </section>
  )
}

export function Loading({ state }: { state: { loading: boolean; error: string | null } }) {
  if (state.error) return <div className="empty">API error: {state.error}</div>
  if (state.loading) return <div className="empty">loading…</div>
  return null
}

/** SOMETHING ASKED FOR IS ON ITS WAY, said in the commit that asked. The same
 *  look as opening a Conversation (`.conv-switching` in ConversationSurface):
 *  a moving bar, a line saying what is being read, and placeholder rows where
 *  it will land. `rows={0}` for the bar and words alone, where what is
 *  already in hand stays on screen beneath it; no `words`, the bar alone.
 *  Reduced motion stills the bar. */
export function LoadingIndicator({ words, rows = 3 }: { words: string; rows?: number }) {
  return (
    <div className="loading-ind" role="status" aria-live="polite" aria-busy="true">
      <span className="loading-ind-bar" aria-hidden="true" />
      {words && <span className="loading-ind-words">{words}</span>}
      {rows > 0 && (
        <div className="loading-ind-ghosts" aria-hidden="true">
          {Array.from({ length: rows }, (_, i) => <i key={i} />)}
        </div>
      )}
    </div>
  )
}

/** A closed-by-default disclosure. Depth lives behind one of these. */
export function Disclosure({
  label,
  hint,
  opened,
  children,
}: {
  label: string
  hint?: string
  /** opens it when this becomes true — somebody went to what is inside.
   *  Never closes it: that is the reader's. */
  opened?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(!!opened)
  useEffect(() => {
    if (opened) setOpen(true)
  }, [opened])
  return (
    <div className={'disclose' + (open ? ' open' : '')}>
      <button className="disclose-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="caret">{open ? '▾' : '▸'}</span>
        <span>{label}</span>
        {hint && <span className="faint">{hint}</span>}
      </button>
      {open && <div className="disclose-body">{children}</div>}
    </div>
  )
}

/** The act names, said the way a person says them. Lives with the API
 *  types so that a reference preview can use it without a cycle. */
export { said } from './api'

/** A popover anchored to a control but positioned in the viewport, so a
 *  scrolling pane never clips the explanation. Layout only.
 *
 *  THE COORDINATES ARE THE VIEWPORT'S, SO THE BOX MUST BE TOO. `fixed` is
 *  only relative to the viewport when no ancestor establishes a containing
 *  block of its own, and several do: the contextual layer's
 *  `backdrop-filter` (even `blur(0px)`), the centre's `container-type`, the
 *  composer's blur. Inside one of those these numbers are read from the
 *  wrong origin -- a reply's status hover in the Thread landed a whole
 *  column to the right, off the screen -- and the ancestor's overflow clips
 *  what it holds, which cut the presence panel off at the Conversation's
 *  edge. Render the box through `Floating` and neither can happen. */
export function Floating({ children }: { children: React.ReactNode }) {
  return createPortal(children, document.body)
}

export function anchored(el: HTMLElement | null, width = 330): React.CSSProperties {
  if (!el) return { visibility: 'hidden' }
  const r = el.getBoundingClientRect()
  const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 12))
  return window.innerHeight - r.bottom > 190
    ? { position: 'fixed', top: r.bottom + 6, left, maxWidth: width }
    : /* `top: auto`, or `.pop`'s own `top` still applies and, with both set,
         the pop is pushed below the window -- Recent Scratch opened off-screen */
      { position: 'fixed', top: 'auto', bottom: window.innerHeight - r.top + 6, left, maxWidth: width }
}

/** A small stack of who took part. Identity, never a count that means more. */
export function Faces({ of }: { of: { id: string; alias: string }[] }) {
  return (
    <span className="faces">
      {of.map((p) => (
        <Avatar key={p.id} id={p.id} alias={p.alias} size={18} />
      ))}
    </span>
  )
}

/* ------------------------------------------------------------------------ *
 * THE CANVAS BED — where the atmosphere's backdrop is painted.
 *
 * IT EXISTS TO CLIP. The backdrop is OVERSCANNED past the workspace when an
 * atmosphere drifts, and an absolutely positioned box that extends past its
 * containing block contributes scrollable overflow to it — which wrapped the
 * whole application in a 64px scrollbar. The workspace cannot simply clip
 * that away, because it legitimately scrolls horizontally on desktop when
 * panes are widened past the window, and CSS will not let one axis clip
 * while the other scrolls: `overflow-y: clip` beside `overflow-x: auto`
 * computes to `hidden`, which keeps the bar off but leaves the shell
 * programmatically scrollable — one `scrollIntoView` from shifting.
 *
 * So the backdrop gets its own bed, inset to the workspace and clipping on
 * both axes. Its overscan cannot reach anything, and the shell is not a
 * scroll container at all. Only the surfaces inside it scroll.
 * ------------------------------------------------------------------------ */
export const CanvasBed = () => <div className="canvas-bed" aria-hidden="true" />
