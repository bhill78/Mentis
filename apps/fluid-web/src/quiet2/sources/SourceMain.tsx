/* SOURCES, IN THE MAIN READING AREA (Manage Sources in Quiet Chat).
 *
 * The same arrangement as the Brain's (brain/BrainPages.tsx): opened from
 * the Sources browser, a source takes the centre reading column; Back
 * returns to the browser as it was left; "Back to the conversation" returns
 * to the conversation where it was being read (Quiet2.tsx keeps that place).
 * No rail, no dashboard, no second column of its own.
 *
 * WHAT IS HELD IS READ BESIDE THE SOURCE where a working column is free
 * (Quiet2's own `openBeside`), and otherwise IN PLACE, here, with Back to
 * the source: a phone and a full workspace get the same thing in the room
 * they have. While something is read in place the source's page stays
 * mounted underneath, so its open sections, its search and its place are
 * exactly as they were on return. */
import { useLayoutEffect, useRef } from 'react'
import { shortId, useApi, type Id, type ParticipantsList } from '../../api'
import type { SourcesAnswer, SourcesRoute } from '../../surfaces/sources/route'
import { nameOf as knownName } from '../real'
import AddSourcePage from './AddSourcePage'
import SourceContent, { contentWords } from './SourceContent'
import SourcePage from './SourcePage'
import '../brain/brainRecord.css'
import '../../surfaces/sources/sources.css'
import './sources.css'

export type SourceMainView = { page: 'source'; col: Id } | { page: 'add'; connector: string | null }
export interface SourceMainState { view: SourceMainView; reading: SourcesRoute | null }

/** A participant, as a person reads them; never an id where a name is known. */
export const personWords = (id: Id | null | undefined): string => (id ? (knownName(id) ?? shortId(id, 10)).replace(/^@/, '') : 'someone')

export default function SourceMain({ state, data, why, me, canWrite, onState, onBack, onLeave, onCancel, onBeside, onChanged }: {
  state: SourceMainState
  data: SourcesAnswer | null
  why?: string | null
  me: Id | null
  canWrite: boolean
  onState: (s: SourceMainState) => void
  /** out to the Sources browser, as it was left */
  onBack: () => void
  /** straight back to the conversation */
  onLeave: () => void
  /** THE FORM'S OWN CANCEL. It leaves for the same place as Back, and --
   *  like Back, "Back to the conversation" and the browser's Back -- it is
   *  asked about first where something has been filled in (the same
   *  question, `leaving.ts`); with nothing filled in it leaves at once. It
   *  was once never asked about (review ent-d960d458078c read a Cancel press
   *  as "throw this away"), and a draft went with one press and no word. It
   *  stays its own callback so the two presses can still be told apart. */
  onCancel: () => void
  /** open held content beside the conversation; false where no column is free */
  onBeside: ((r: SourcesRoute, source: string | null) => boolean) | null
  onChanged: () => void
}) {
  const { view, reading } = state
  /* `data` is null until the one read of `/api/sources` Quiet2 keeps has
     answered. Add a source is told that, because `[]` descriptors before the
     answer and `[]` after it mean opposite things to a reader. */
  const descriptors = data?.descriptors ?? []
  const source = view.page === 'source' ? data?.collections.find((c) => c.collection === view.col) ?? null : null
  const box = useRef<HTMLDivElement>(null)
  /* who declared and refreshed it, by name: the Brain's own list of participants */
  const people = useApi<ParticipantsList>('/api/participants', { live: false })
  const person = (id: Id | null | undefined): string => {
    const alias = id ? people.data?.participants.find((x) => x.participant === id)?.alias : null
    return alias ? alias.replace(/^@/, '') : personWords(id)
  }

  /* read in place: from its top, and the source's page where it was on return */
  const left = useRef<number | null>(null)
  const readingKey = reading ? JSON.stringify(reading) : null
  useLayoutEffect(() => {
    const pane = box.current?.closest<HTMLElement>('.q2-pane')
    if (!pane) return
    if (readingKey) { pane.scrollTop = 0; return }
    if (left.current !== null) { pane.scrollTop = left.current; left.current = null }
  }, [readingKey])

  const read = (r: SourcesRoute) => {
    if (onBeside && onBeside(r, source?.name ?? null)) return
    if (!reading) left.current = box.current?.closest<HTMLElement>('.q2-pane')?.scrollTop ?? 0
    onState({ view, reading: r })
  }
  const openSource = (col: Id) => onState({ view: { page: 'source', col }, reading: null })

  return (
    <div ref={box} className="q2-stream q2-brain-main q2-src" data-source-page={reading ? 'content' : view.page}>
      <div className="q2-back-bar rv-backbar">
        {reading
          ? <button type="button" className="q2-back-btn" data-source-back onClick={() => onState({ view, reading: null })}>‹ {source?.name ?? 'The source'}</button>
          : <button type="button" className="q2-back-btn" data-source-back onClick={onBack}>‹ Sources</button>}
        <span className="q2-back-where">{reading ? contentWords(reading) : view.page === 'add' ? 'New source' : 'Source'}</span>
        <button type="button" className="q2-link-quiet" onClick={onLeave}>Back to the conversation</button>
      </div>
      {view.page === 'source' && (
        <div hidden={!!reading}>
          <SourcePage key={view.col} col={view.col} descriptors={descriptors} picker={data?.picker} me={me} nameOf={person} canWrite={canWrite}
            onOpenContent={read} onChanged={onChanged}
            onAddKind={(connector) => onState({ view: { page: 'add', connector }, reading: null })} />
        </div>
      )}
      {view.page === 'source' && reading && (
        <div className="rv rv-full q2-src-reading">
          <SourceContent route={reading} onRoute={(r) => onState({ view, reading: r })} onSource={openSource} />
        </div>
      )}
      {view.page === 'add' && (canWrite
        ? <AddSourcePage descriptors={descriptors} read={data !== null} why={why} picker={data?.picker} me={me} connector={view.connector}
            onConnector={(connector) => onState({ view: { page: 'add', connector }, reading: null })}
            onOpenSource={openSource} onChanged={onChanged} onCancel={onCancel} />
        : <div className="rv rv-full"><p className="q2m-faint" role="alert">This page is read-only: a source cannot be added here.</p></div>)}
    </div>
  )
}
