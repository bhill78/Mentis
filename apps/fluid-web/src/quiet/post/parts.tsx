/* WHAT ONE PART OF A POST'S BODY BECOMES. Anything that is a file or an
   image is F's, through MediaPart -- so this module never decides how media
   looks and F never touches the post's own markup.

   WHAT ROUND 4 CHANGES (Track C owns this module now).

   1. THE RENDERER'S ARTIFACTS RENDER. This passed `untrusted` to `Prose`,
      which switches off the renderable blocks, the html preview and placed
      figures (prose.tsx): a checklist, a chart, a table, a timeline, a
      diagram, a pad, a ref, a panel or a timer an agent wrote arrived in
      Quiet as its own fenced source. `untrusted` is for text NOBODY IN THIS
      BRAIN WROTE -- a stored note, a file read off disk -- and a posted Turn
      is not that. So a Turn's words are now rendered the way Fluid renders
      the same content (`fluid/render/post.tsx` `Words`): `Prose` with the
      Turn part's own scope (`turnPartScope`) and its own name table
      (`namesFor`). The scope matters: a posted block's state is keyed by the
      Turn it was WRITTEN in and the index of its text part, so the SAME
      block drawn twice -- in the post and in the margin -- is one block with
      one set of answers, and two posts never share one.

      Quiet draws no grips (`BlockGripContext` is Fluid's drag-out-of-a-post),
      so none is provided and `RenderableBlock` draws none; everything else
      about the drawing is the shared renderers', unchanged.

   2. WHAT EACH POST CARRIES IS REGISTERED FOR THE MARGIN. Every marked block
      and every attachment is announced to `margin/carried.ts` under the
      part's own key, so the margin can present it beside the stream without
      this module knowing the margin exists. A registration is withdrawn when
      the part is no longer drawn.

   3. ANNOTATIONS ARE MOUNTED HERE, not in Post.tsx: one layer per post, at
      its first part, which puts an icon in the post's gutter level with each
      annotated passage. Every part also SAYS WHAT IT DRAWS
      (`annotations/words.ts`), because a passage is a place in the post's
      joined words and no part can see its siblings: that is how an anchor on
      a later text part is placed level with its own passage, rather than at
      the top of the body. */
import { useEffect, useMemo } from 'react'
import { Prose } from '../../prose'
import { analyse, markedIn, turnPartScope, type RBlock } from '../../experimental/renderable'
import { namesFor } from '../../experimental/objects'
import type { Part } from '../../api'
import Annotations from '../annotations/Annotations'
import { sayPart, type Drawn } from '../annotations/words'
import MediaPart from '../media/MediaPart'
import { itemOf } from '../media/view'
import { register, sideOf, type Carried } from '../margin/carried'

/** Quiet's own part scope (`<turn>:part:<n>`, built by Post.tsx) read back as
 *  the Turn and the part index a posted block is keyed by. Post.tsx is not
 *  this package's to change, so the two forms are reconciled here rather
 *  than by widening the seam. */
export function partAt(scope: string): { turn: string; index: number } {
  const cut = scope.lastIndexOf(':part:')
  if (cut < 0) return { turn: scope, index: 0 }
  const n = Number(scope.slice(cut + ':part:'.length))
  return { turn: scope.slice(0, cut), index: Number.isFinite(n) ? n : 0 }
}

/** The part types whose text `annotated.ts` counts as part of the post's
 *  words. Their rendering stands for exactly that stored text, so the
 *  passage walk (`surfaces/passage.ts`) consumes it as one span; anything
 *  else in the body is chrome the walk must skip, or an anchor would be
 *  drawn over words that are not in the stored text at all. */
const REFERENCE = new Set(['turn', 'topic', 'conversation', 'acquired', 'object'])

/** What a box carrying this block is called. */
function titleOf(block: RBlock): string {
  const a = analyse(block)
  return a.attrs.title || a.shared.label || block.type
}

/** A Turn's words, rendered as Fluid renders the same content, and the blocks
 *  in them offered to the margin. */
function Words({ text, turn, index }: { text: string; turn: string; index: number }) {
  const scope = turnPartScope(turn, index)
  const names = useMemo(() => namesFor(text, scope), [text, scope])
  useEffect(() => {
    const group = 'blocks:' + scope
    register(group, markedIn(text, scope, names).map(({ block, key }): Carried => ({
      kind: 'block', id: 'block:' + key, post: turn, title: titleOf(block),
      side: sideOf(block.type), type: block.type, block, blockKey: key, where: scope, names,
    })))
    return () => register(group, [])
  }, [text, scope, names, turn])
  return <Prose src={text} scope={scope} names={names} />
}

/** An attachment, drawn by F and offered to the margin. */
function Media({ part, scope, turn }: { part: Part; scope: string; turn: string }) {
  const item = useMemo(() => itemOf(part), [part])
  useEffect(() => {
    const group = 'media:' + scope
    register(group, item ? [{ kind: 'media', id: 'media:' + scope, post: turn, title: item.name, side: 'right', item }] : [])
    return () => register(group, [])
  }, [scope, turn, item])
  return <MediaPart part={part} scope={scope} />
}

/** WHAT THIS PART PUTS IN THE POST'S JOINED WORDS -- said beside `Body`,
 *  which decides it, and read by the annotation layer (`annotations/words.ts`)
 *  to place a passage in any part of the post. A text part contributes its own
 *  text; a reference the body stands for contributes its stored text
 *  (`data-src-text`); anything drawn as chrome (`data-src-skip`) contributes
 *  none -- an attachment included, because MediaPart draws what the file is,
 *  not words the post stored. The part keeps its index either way. */
function drawnAs(part: Part): Drawn {
  if (part.type === 'text') return { type: 'text', text: part.text ?? '' }
  /* as `Body` branches: a topic reference and a held attachment are chrome */
  if (part.type === 'topic_ref' || (part.artifact?.state === 'held' && part.artifact.url))
    return { type: part.type, text: '' }
  return { type: part.type, text: (REFERENCE.has(part.type) ? part.text : undefined) ?? '' }
}

function Body({ part, scope, turn, index }: { part: Part; scope: string; turn: string; index: number }) {
  if (part.type === 'text') return <Words text={part.text ?? ''} turn={turn} index={index} />
  if (part.type === 'topic_ref' && part.text) return <span data-src-skip="">{part.text}</span>
  if (part.artifact?.state === 'held' && part.artifact.url) return <Media part={part} scope={scope} turn={turn} />
  /* Retain authored non-text references without importing Fluid's object
     surfaces. A reference the stored words include stands for its own text;
     anything else is not in them and is skipped by the passage walk. */
  const said = REFERENCE.has(part.type) ? part.text : undefined
  return <p className="qc-context" {...(said ? { 'data-src-text': said } : { 'data-src-skip': '' })}>
    {part.text || part.alt || part.ref || part.type}</p>
}

export default function PostPart({ part, scope }: { part: Part; scope: string }) {
  const { turn, index } = partAt(scope)
  /* EVERY PART SAYS WHAT IT DRAWS. Post.tsx hands each part over on its own,
     so no part sees its siblings; the post's joined words are assembled from
     what each one says, and the layer below reads them whole. */
  const drawn = useMemo(() => drawnAs(part), [part])
  useEffect(() => sayPart(turn, index, drawn), [turn, index, drawn])
  return <>
    {/* ONE LAYER PER POST, at its first part -- one gutter, measured once --
        and it places a passage in ANY of the post's parts, because the words
        it reads are the whole post's (`annotations/words.ts`). */}
    {index === 0 && <Annotations post={turn} />}
    <Body part={part} scope={scope} turn={turn} index={index} />
  </>
}
