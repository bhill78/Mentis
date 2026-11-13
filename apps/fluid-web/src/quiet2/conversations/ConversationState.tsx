/* AN ARCHIVED OR TRASHED CONVERSATION, OPENED: a small state chip under its
 * title with the way back (Unarchive, Restore), and -- in Trash -- the
 * composer's place taken by "In Trash · restore it to post here [Restore]".
 * Both read the Conversation's own row (`store.conversations`, kept current
 * by the change feed and by every change made here). */
import './conversations.css'
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { newOp, store, type Conversation, type ConversationChange, type Id } from '../../fluid/store'
import { READ_ONLY } from '../live'
import { repairText } from '../text'
import { changedWords, dayWord, stateOf } from './manage'

/** The Conversation's row as the store holds it, read once if it is not. */
export function useConversationRow(id: Id | null): Conversation | null {
  const sub = useCallback((fn: () => void) => (id ? store.subscribe('conv:' + id, fn) : () => {}), [id])
  const row = useSyncExternalStore(sub, () => (id ? store.conversations.get(id) ?? null : null))
  useEffect(() => { if (id && !store.conversations.has(id)) void store.loadConversations([id]).catch(() => {}) }, [id])
  return row
}

const ICON = {
  archived: <><rect x="2" y="3" width="12" height="3" rx=".6" /><path d="M3 6v7h10V6M6.5 8.5h3" /></>,
  trashed: <path d="M2.5 4.5h11M6 4.5V3h4v1.5M4 4.5l.7 9h6.6l.7-9M6.8 7v4.5M9.2 7v4.5" />,
}
const StateIcon = ({ state }: { state: 'archived' | 'trashed' }) => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICON[state]}</svg>
)

/** Unarchive or Restore, by the reader, with what the page says after. */
export function useChange(row: Conversation | null, say: (w: string) => void) {
  const [busy, setBusy] = useState(false)
  const change = async (what: ConversationChange) => {
    if (!row || busy) return
    setBusy(true)
    try {
      const author = store.me ?? await store.loadMe()
      await store.changeConversationState(row.id, author, what, newOp())
      say(changedWords(what, repairText(row.name) || 'Unnamed conversation'))
    } catch (e: unknown) {
      say(e instanceof Error ? e.message : String(e))
    } finally { setBusy(false) }
  }
  return { busy, change }
}

/** The chip under the title; nothing while the Conversation is active. */
export default function ConversationState({ row, say }: { row: Conversation | null; say: (w: string) => void }) {
  const st = stateOf(row)
  const { busy, change } = useChange(row, say)
  if (!row || st === 'active') return null
  return (
    <p className="q2-conv-state" role="status">
      <span className="q2-state-chip"><StateIcon state={st} />{st === 'archived' ? `Archived ${dayWord(row.state_at)}` : `In Trash since ${dayWord(row.state_at)}`}</span>
      {!READ_ONLY && (
        <button type="button" className="q2-quiet-btn" disabled={busy} onClick={() => void change(st === 'archived' ? 'unarchive' : 'restore')}>
          {st === 'archived' ? 'Unarchive' : 'Restore'}
        </button>
      )}
    </p>
  )
}

/** In Trash, the composer's place: restore it to post here. */
export function TrashedComposer({ row, say }: { row: Conversation; say: (w: string) => void }) {
  const { busy, change } = useChange(row, say)
  return (
    <div className="q2-dock-closed">
      <span><span className="q2-state-chip"><StateIcon state="trashed" />In Trash</span> · restore it to post here</span>
      {!READ_ONLY && <button type="button" className="q2-quiet-btn" disabled={busy} onClick={() => void change('restore')}>Restore</button>}
    </div>
  )
}
