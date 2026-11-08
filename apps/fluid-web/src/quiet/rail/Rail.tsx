/* Track 2: bounded topic navigation; public rail props stay unchanged.
 *
 * ROUND 4 (Track C) adds a FOURTH READING: what the posts carry. The margin
 * already held the conversation's topics, its brief, and the runs with the
 * decisions accordion under them; beside those it now presents each post's
 * rendered blocks, its media and its annotations as small windows
 * (`margin/Margin.tsx`), which is what the concept's margins are for.
 *
 * HOW THAT READING IS CHOSEN. By its own control, like the other three -- and
 * by anything that asks to be read there. An annotation's icon in a post's
 * gutter collects the annotation into the margin (`margin/carried.ts`
 * `present`), which means switching the reading; `useRail` is the one place
 * that can, so it watches the store's ask rather than the margin reaching
 * for the shell's state. */
import { useEffect, useState } from 'react'
import type { Conversation, Id } from '../../api'
import type { RailName } from '../contract'
import ActivityPanel from '../activity/ActivityPanel'
import Decisions from '../activity/Decisions'
import Margin from '../margin/Margin'
import { useAsked } from '../margin/carried'
import './rail.css'

/* Track B: Topics moved out to its own floating presentation
 * (floatnav/TopicsFloat.tsx) -- it is no longer one of the readings this
 * margin switches between, so the working margin (what each post carries)
 * keeps exactly the readings it had before Topics is extracted. */
const READINGS = ['brief', 'activity', 'carried'] as const
const titled = (rail: RailName) => rail[0].toUpperCase() + rail.slice(1)

/** Which reading the margin shows. Starts closed -- Topics no longer opens
 *  it by default, now that Topics floats on its own -- and moves to Carried
 *  when something in a post asks to be read there. */
export function useRail() {
  const [rail, setRail] = useState<RailName | null>(null)
  const asked = useAsked()
  useEffect(() => { if (asked) setRail('carried') }, [asked])
  return { rail, setRail }
}

export function RailTools({ rail, choose }: {
  rail: RailName | null; choose: (rail: RailName | null) => void
}) {
  return <nav className="qc-rail-tools" aria-label="Conversation tools">{READINGS.map((item) =>
    <button key={item} aria-expanded={rail === item} aria-controls="qc-margin"
      onClick={() => choose(rail === item ? null : item)}>{titled(item)}</button>)}</nav>
}

export default function Rail({ rail, close, conversation, topic, facts }: {
  rail: RailName; close: () => void; conversation: Id; topic: Id | null; facts: Conversation | null
}) {
  return <aside id="qc-margin" className="qc-margin" aria-label={rail}>
    <div className="qc-rail-heading"><h2>{titled(rail)}</h2>
      <button aria-label="Close margin" onClick={close}>×</button></div>
    {rail === 'brief' && <><p>{facts?.about || 'This conversation has no description.'}</p>
      <h3>People here</h3><p>{facts?.participants.map((p) => p.alias).join(', ')}</p></>}
    {rail === 'activity' && <>
      <ActivityPanel conversation={conversation} topic={topic} />
      <Decisions conversation={conversation} topic={topic} />
    </>}
    {/* ALONGSIDE THE DECISION ACCORDIONS, as the request asks: what the posts
        carry is presented BESIDE the margin's existing controls, not instead
        of them. An outstanding decision is the one thing in the margin that
        is owed rather than offered, so it stays reachable in this reading
        too -- under the boxes, where Activity also puts it. */}
    {rail === 'carried' && <>
      <Margin />
      <Decisions conversation={conversation} topic={topic} />
    </>}
  </aside>
}
