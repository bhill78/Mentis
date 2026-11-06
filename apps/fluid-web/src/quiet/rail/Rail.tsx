/* PACKAGE B owns this module: the contextual margin and the controls that
   choose which reading it shows. At P0 both render what Quiet rendered before
   the split, in the same places -- the controls beside the title, the margin
   in the work row's third cell.

   THE RAIL'S STATE LIVES HERE, in `useRail`, rather than in the shell: B is
   what decides which readings there are. The shell calls the hook and hands
   the two halves what they need, because the controls and the margin sit in
   different rows and a module-level store would also outlive the conversation
   they belong to.

   WHAT B CHANGES. §3 of the concept asks for text-free topic lines whose
   weight comes from `topics[].turns`, the rail's top edge aligned to the
   header's lower edge, and the controls inside the rail region. The first two
   are this file's markup and rail.css; the third is where `RailTools` is
   mounted, which is the shell's one line and already outside the global
   header. */
import { useState } from 'react'
import type { Conversation, Id } from '../../api'
import type { RailName } from '../contract'
import { href } from '../model'
import ActivityPanel from '../activity/ActivityPanel'
import Decisions from '../activity/Decisions'
import './rail.css'

const READINGS = ['topics', 'brief', 'activity'] as const
const titled = (rail: RailName) => rail[0].toUpperCase() + rail.slice(1)

/** Which reading the margin shows. Starts on Topics, as it always has. */
export function useRail() {
  const [rail, setRail] = useState<RailName | null>('topics')
  return { rail, setRail }
}

export function RailTools({ rail, choose }: {
  rail: RailName | null; choose: (rail: RailName | null) => void
}) {
  return <nav aria-label="Conversation tools">{READINGS.map((item) =>
    <button key={item} aria-expanded={rail === item} aria-controls="qc-margin"
      onClick={() => choose(rail === item ? null : item)}>{titled(item)}</button>)}</nav>
}

export default function Rail({ rail, close, conversation, topic, facts }: {
  rail: RailName; close: () => void; conversation: Id; topic: Id | null; facts: Conversation | null
}) {
  return <aside id="qc-margin" className="qc-margin" aria-label={rail}>
    <div className="qc-nav-heading"><h2>{titled(rail)}</h2>
      <button aria-label="Close margin" onClick={close}>×</button></div>
    {rail === 'topics' && <nav aria-label="Topics">
      <a href={href(conversation)} aria-current={!topic ? 'page' : undefined}><strong>All posts</strong><span>{facts?.turns_total ?? '…'} posts in this conversation</span></a>
      {facts?.topics.map((t) => <a key={t.id} href={href(conversation, t.id)} aria-current={t.id === topic ? 'page' : undefined}>
        <strong># {t.name}</strong><span>{t.about || `${t.turns} posts filed here`}</span></a>)}
      {facts && !facts.topics.length && <p>No topics in this conversation yet.</p>}
    </nav>}
    {rail === 'brief' && <><p>{facts?.about || 'This conversation has no description.'}</p>
      <h3>People here</h3><p>{facts?.participants.map((p) => p.alias).join(', ')}</p></>}
    {rail === 'activity' && <>
      <ActivityPanel conversation={conversation} topic={topic} />
      <Decisions conversation={conversation} topic={topic} />
    </>}
  </aside>
}
