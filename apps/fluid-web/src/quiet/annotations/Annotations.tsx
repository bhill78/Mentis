/* TRACK C owns this module: ANNOTATIONS ON A QUIET POST -- an icon in the
   post's gutter level with the annotated passage, and the annotation itself
   as a box in the margin.

   WHAT IS REUSED, AND WHY NOT MORE. The record's side of this is already
   written and is not written again here: `fluid/actions.ts` reads a post's
   anchors (`readAnchorsOf`, and `anchorsKey`, the change feed's name for
   them) and `fluid/conversation/annotated.ts` holds them in one batch
   (`useAnchors`), says where a passage is drawn in the rendered words
   (`drawnRange`, over `surfaces/passage.ts`'s alignment) and says briefly
   what an anchor carries (`carries`, `lead`, `tallyWords`). Quiet's own part
   is the PRESENTATION: where the mark sits, what activating it does, and the
   margin box. Fluid's own `Annotations.tsx` is not reused -- it draws
   Fluid's sheets, its selection bar and its commands, which belong to
   Fluid's frame and its store, and none of which Quiet mounts.

   NOTHING IS WRITTEN FROM HERE. This slice SHOWS what is attached. Reacting,
   commenting and opening a deep dive from Quiet are not in it.

   WHERE A MARK GOES. The layer is the post body's first child, laid out at
   its top with no height of its own, so each mark's `top` is measured as the
   distance from the layer to the passage's own first line -- and the marks
   are stacked apart from each other so two passages a line apart do not draw
   one mark over the other, as Fluid's gutter does it. The words the passages
   are placed in are the WHOLE post's, assembled from what every part says it
   draws (`words.ts`), so a passage in the second or the tenth text part is
   placed level with itself, not at the top. A mark whose passage cannot be
   found at all (an anchor on a version that is no longer current) sits level
   with the top of the body rather than being hidden: the annotation is still
   real and still reachable.

   THE LAYER IS NOT THE POST'S WORDS. It carries `data-src-skip`, so the
   alignment walk never tries to place its glyphs in the stored text. */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { highlightFor } from '../../surfaces/passage'
import type { PostAnchor } from '../../fluid/actions'
import { carries, drawnRange, inTextOrder, lead, tallyWords, useAnchors } from '../../fluid/conversation/annotated'
import { store } from '../../fluid/store'
import { present, register, type Carried } from '../margin/carried'
import { usePostSource } from './words'
import './annotations.css'

/** The height a mark takes in the gutter, for stacking two that would
 *  otherwise overlap. */
const MARK = 18

export const boxIdOf = (anchor: string) => 'anchor:' + anchor

/** A GUTTER IS A MEASUREMENT, AND THERE IS NOTHING TO MEASURE IN A STRING.
 *  Every mark's place is read off the rendered words with
 *  `getClientRects`, so this layer exists only where there is a layout to
 *  ask. Rendered to a string (`quiet_post_unit`'s `renderToStaticMarkup`, and
 *  any future server render) it draws nothing rather than drawing marks
 *  stacked at zero -- and the anchors read, which is `useSyncExternalStore`
 *  over the change feed and has no server snapshot to give, is not started
 *  there either. The branch is on the environment, which does not change
 *  within a process, so no hook is ever called conditionally. */
export default function Annotations(props: { post: string }) {
  if (typeof document === 'undefined') return null
  return <Layer {...props} />
}

function Layer({ post }: { post: string }) {
  const anchors = useAnchors(post)
  const list = useMemo(() => inTextOrder(anchors.filter(carries)), [anchors])
  /* The post's words as the alignment walk reads them: the WHOLE post's,
     assembled from what each part says it draws (`words.ts`), because a
     passage may be in any text part and Quiet's parts are mounted one at a
     time. The walk below reads the whole body, which holds them all. */
  const src = usePostSource(post)
  const layer = useRef<HTMLDivElement>(null)
  const [tops, setTops] = useState<Record<string, number>>({})
  const [open, setOpen] = useState<string | null>(null)

  const bodyOf = () => layer.current?.closest<HTMLElement>('.qc-body') ?? null

  /* WHAT THE MARGIN IS OFFERED: one box per annotation that carries
     something, withdrawn when this post is no longer drawn. */
  useEffect(() => {
    const group = 'anchors:' + post
    register(group, list.map((a): Carried => ({
      kind: 'annotation', id: boxIdOf(a.anchor), post, side: 'right',
      title: a.selector.type === 'version' ? 'Annotation · the whole post' : 'Annotation',
      anchor: a, excerpt: a.excerpt ?? null,
    })))
    return () => register(group, [])
  }, [list, post])

  /* WHAT THE BOX WILL SHOW IS READ WITH THE ANCHORS. The margin is where an
     annotation is read, and a comment on a passage is its own Turn: it is
     asked for here, in one batch for the whole post, as soon as the anchors
     say there is one -- not when the reader opens the box, which would make
     every annotation open on a loading line first. `loadPosts` asks only for
     what the store does not already hold. */
  useEffect(() => {
    const comments = list.flatMap((a) => a.replies)
    if (comments.length) void store.loadPosts(comments).catch(() => {})
  }, [list])

  /* Where each mark goes, measured after layout and again whenever the post
     changes shape (a wrapped line moves every passage below it). */
  const live = useRef({ list, src })
  live.current = { list, src }
  useLayoutEffect(() => {
    const el = layer.current
    if (!el || !list.length) return
    const measure = () => {
      const origin = el.getBoundingClientRect().top
      const body = bodyOf()
      const ys = live.current.list.map((a) => {
        const line = drawnRange(a, body, live.current.src)?.getClientRects()[0]
        return [a.anchor, line ? Math.max(0, line.top + line.height / 2 - origin - MARK / 2) : 0] as const
      }).sort((x, y) => x[1] - y[1])
      const out: Record<string, number> = {}
      let floor = -Infinity
      for (const [id, y] of ys) { out[id] = Math.max(y, floor); floor = out[id] + MARK + 2 }
      setTops((was) => (JSON.stringify(was) === JSON.stringify(out) ? was : out))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el.closest('.qc-post') ?? el)
    return () => ro.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list, src])

  /* A faint lasting wash on every annotated passage, and a plainer one on
     the passage whose mark was activated. A browser without the custom
     highlight registry simply draws neither (`highlight`). */
  useEffect(() => {
    const body = bodyOf()
    highlightFor('qc-anno-on', post, list.map((a) => drawnRange(a, body, src)).filter((r): r is Range => !!r))
    return () => highlightFor('qc-anno-on', post, [])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list, src, tops, post])
  useEffect(() => {
    const a = open ? list.find((x) => x.anchor === open) : null
    const r = a ? drawnRange(a, bodyOf(), src) : null
    highlightFor('qc-anno-here', post, r ? [r] : [])
    return () => highlightFor('qc-anno-here', post, [])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, list, src, post])

  if (!list.length) return <div ref={layer} className="qc-anno" data-src-skip="" aria-hidden="true" />

  /** Activating a mark marks its passage and collects the annotation into
   *  the margin, which is where it is read. */
  const activate = (a: PostAnchor) => {
    const next = open === a.anchor ? null : a.anchor
    setOpen(next)
    present(next ? boxIdOf(a.anchor) : null)
  }

  return (
    <div ref={layer} className="qc-anno" data-src-skip="">
      <div className="qc-anno-marks" role="group" aria-label="Annotations on this post">
        {list.map((a) => {
          const { glyph, n } = lead(a)
          const on = a.selector.type === 'version' ? 'the whole post' : `“${a.excerpt ?? ''}”`
          return (
            <button key={a.anchor} type="button" className="qc-anno-mark" data-anno={a.anchor}
              style={{ top: (tops[a.anchor] ?? 0) + 'px' }} aria-expanded={open === a.anchor}
              aria-label={`Annotation on ${on}: ${tallyWords(a)}`} title={`${tallyWords(a)} · on ${on}`}
              onClick={() => activate(a)}>
              <span className="qc-anno-glyph" aria-hidden="true">{glyph}</span>
              {n > 1 && <span className="qc-anno-n" aria-hidden="true">{n}</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
