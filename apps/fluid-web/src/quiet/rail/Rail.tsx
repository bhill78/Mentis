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
import { href } from '../model'
import ActivityPanel from '../activity/ActivityPanel'
import Decisions from '../activity/Decisions'
import Margin from '../margin/Margin'
import { useAsked } from '../margin/carried'
import { markMetrics } from './marks'
import { NavigationFilter } from '../navigation/NavigationRail'
import './rail.css'

const READINGS = ['brief', 'activity', 'carried'] as const
const titled = (rail: RailName) => rail[0].toUpperCase() + rail.slice(1)

/** Working material starts put away for reading; an annotation opens Carried.
 * Topics has its own independent navigation rail in Track A. */
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

export function TopicsNav({ conversation, topic, facts }: {
  conversation: Id; topic: Id | null; facts: Conversation | null
}) {
  const topics = facts?.topics ?? []
  const [query, setQuery] = useState('')
  const filtered = topics.filter((t) => (t.name + ' ' + t.about).toLowerCase().includes(query.trim().toLowerCase()))
  const busiest = Math.max(0, ...topics.map((t) => t.turns))
  return <nav className="qc-topics" aria-label="Topics">
      <NavigationFilter id="qc-topic-query" label="Find a topic" query={query} change={setQuery} />
      <div className="qc-topic-tools">
        <a className="qc-topic-all" href={href(conversation)} aria-current={!topic ? 'page' : undefined}><span>All posts</span></a>
      </div>
      {/* Keep the existing topic identities, counts and selection semantics.
          Track A's stylesheet makes their labels continuously readable. */}
      {!!topics.length && <ul className="qc-topic-marks">
        {filtered.map((t) => {
          const metrics = markMetrics(t.turns, busiest, t.id === topic)
          return <li key={t.id}>
            <a className="qc-topic-mark" href={href(conversation, t.id)}
              aria-current={t.id === topic ? 'page' : undefined}
              aria-label={t.about ? `${t.name} — ${t.about}` : t.name}
              title={`${t.name} · ${t.turns} posts${t.about ? ` — ${t.about}` : ''}`}
              style={{ '--qc-mark-thickness': `${metrics.thickness}px`, '--qc-mark-length': `${metrics.length}px` } as React.CSSProperties}>
              <span className="qc-topic-bar" aria-hidden="true" />
              <span className="qc-topic-label">{t.name}</span>
            </a>
          </li>
        })}
      </ul>}
      {facts && !topics.length && <p>No topics in this conversation yet.</p>}
      {!!topics.length && !filtered.length && <p>No matching topics.</p>}
    </nav>
}

export default function Rail({ rail, close, conversation, topic, facts }: {
  rail: RailName; close: () => void; conversation: Id; topic: Id | null; facts: Conversation | null
}) {
  return <aside id="qc-margin" className="qc-margin" aria-label={rail}>
    <div className="qc-rail-heading"><h2>{titled(rail)}</h2>
      <button aria-label="Close margin" onClick={close}>×</button></div>
    {rail === 'topics' && <TopicsNav {...{ conversation, topic, facts }} />}
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
      <Margin side="right" />
      <Decisions conversation={conversation} topic={topic} />
    </>}
  </aside>
}
