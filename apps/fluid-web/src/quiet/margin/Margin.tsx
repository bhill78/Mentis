/* TRACK C owns this module: WHAT THE POSTS CARRY, PRESENTED BESIDE THEM.

   THE MOCKUP'S MARGINS (`quiet-chat-concept.html`, and its README: "what each
   turn carries goes beside it: media and the timeline, chart, git graph and
   flow chart on the right; documents, the table and the form on the left").
   Each one is a SMALL WINDOW: a head that says what it is and which post it
   came from, and the two things a reader does with it -- go back to the post
   it belongs to, and put it away. A picture and a film open in the viewer
   from here as they do from the post (that is the mockup's "pop out"); a
   block is the SAME block as the one in the post, keyed identically
   (`carried.ts`), so ticking a checklist here ticks it there.

   IT ADAPTS TO ITS OWN WIDTH, NOT THE WINDOW'S. `.qc-margin` is a container
   (rail.css), so every box asks how wide the MARGIN is -- which is a third
   of the shell's grid at 1440 and the whole column below 900 -- and nothing
   here reads the viewport. Anything that cannot shrink (a wide table, a long
   diagram) scrolls INSIDE its own box; the page never scrolls sideways.

   NOT A FLOATING WINDOW. Fluid's floats, magnets and Pages are outside this
   work: a box is an element in the margin's flow that LOOKS like a small
   window, and there is no dragging, no stacking and no z-order here. */
import { useEffect, useRef } from 'react'
import { RenderableBlock } from '../../experimental/renderable'
import { lead, tallyWords } from '../../fluid/conversation/annotated'
import { openViewer } from '../media/MediaLayer'
import { kindWords } from '../media/view'
import { goToPost, postNumber, putAway, useCarried, useOpened, type Carried } from './carried'
import './margin.css'

function BoxBody({ c }: { c: Carried }) {
  if (c.kind === 'block')
    return <RenderableBlock block={c.block} blockKey={c.blockKey} where={c.where} names={c.names} size="compact" />
  if (c.kind === 'media') {
    const { item } = c
    if (item.kind === 'image')
      return <button type="button" className="qc-box-image" aria-label={`Open ${item.name}`}
        onClick={(e) => openViewer([item], 0, e.currentTarget)}>
        <img src={item.url} alt={item.alt} />
      </button>
    return <button type="button" className="qc-box-open" aria-label={`Open ${item.name}`}
      onClick={(e) => openViewer([item], 0, e.currentTarget)}>
      Open · {kindWords[item.kind]}
    </button>
  }
  const { n } = lead(c.anchor)
  return <>
    {c.excerpt && <blockquote className="qc-box-passage">{c.excerpt}</blockquote>}
    <p className="qc-box-tally">{tallyWords(c.anchor)}</p>
    <p className="qc-muted">{n === 1 ? 'one thing is attached here' : `${n} things are attached here`}</p>
  </>
}

function Box({ c, marked }: { c: Carried; marked: boolean }) {
  const box = useRef<HTMLElement>(null)
  const number = postNumber(c.post)
  const from = number != null ? `post #${number}` : 'its post'
  useEffect(() => { if (marked) box.current?.scrollIntoView({ block: 'nearest' }) }, [marked])
  return (
    <section className="qc-box" ref={box} data-kind={c.kind} data-side={c.side}
      data-marked={marked || undefined} aria-label={`${c.title}, carried by ${from}`}>
      <div className="qc-box-head">
        <h3 className="qc-box-title">{c.title}</h3>
        <button type="button" className="qc-box-where" onClick={() => goToPost(c.post)}
          aria-label={`Go to ${from}`} title={`Go to ${from}`}>{number != null ? `#${number}` : '↑'}</button>
        <button type="button" className="qc-box-away" onClick={() => putAway(c.id)}
          aria-label={`Put away ${c.title}`} title="Put away">×</button>
      </div>
      <div className="qc-box-body"><BoxBody c={c} /></div>
    </section>
  )
}

export default function Margin() {
  const carried = useCarried()
  const opened = useOpened()
  if (!carried.length)
    return <p className="qc-carried-none">Nothing is carried beside these posts yet. A post's
      chart, table, checklist, timeline, diagram, file or annotation is presented here.</p>
  return <div className="qc-carried">
    {carried.map((c) => <Box key={c.id} c={c} marked={c.id === opened} />)}
  </div>
}
