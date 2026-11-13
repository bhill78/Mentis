/* CONVERSATION MANAGEMENT: the words and rules the list, its menus and the
 * Danger Zone share, kept apart from the components so they can be checked
 * without a browser (tests/quiet2_convmgmt_unit.ts).
 *
 * A Conversation is listed Active, Archived or in Trash. Each change is one
 * act on it (`store.changeConversationState`); its id, posts, replies, files
 * and work are untouched, so every change is undone exactly. Archive stops
 * nothing. Trash is refused while work is in flight -- by the server, and
 * said here before it is asked. Permanent deletion is offered only when the
 * server says it is available (`store.conversationDeletion`); today it is
 * not, and the item says why. */
import type { Conversation, ConversationChange, ConversationState, DeletionCapability } from '../../fluid/store'

export const TABS: { id: ConversationState; label: string }[] = [
  { id: 'active', label: 'Active' }, { id: 'archived', label: 'Archived' }, { id: 'trashed', label: 'Trash' },
]

export const stateOf = (c: Pick<Conversation, 'state'> | null | undefined): ConversationState => c?.state ?? 'active'

/** The title filter: every word typed, anywhere in the title, any case. */
export function titleMatches(name: string | null | undefined, filter: string): boolean {
  const words = filter.toLowerCase().split(/\s+/).filter(Boolean)
  const title = (name ?? '').toLowerCase()
  return words.every((w) => title.includes(w))
}

/** The quiet line under an empty tab. */
export function emptyLine(tab: ConversationState, filter: string): string {
  const f = filter.trim()
  if (f) return `No ${tab === 'trashed' ? 'conversation in Trash' : `${tab} conversation`} titled “${f}”.`
  return tab === 'active' ? 'No active conversations.' : tab === 'archived' ? 'Nothing archived.' : 'Trash is empty.'
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
/** "3 Nov", "today" */
export function dayWord(at: number | null | undefined, now = Date.now()): string {
  if (!at) return ''
  const d = new Date(at * 1000), n = new Date(now)
  if (d.toDateString() === n.toDateString()) return 'today'
  return `${d.getDate()} ${MONTHS[d.getMonth()]}${d.getFullYear() !== n.getFullYear() ? ` ${d.getFullYear()}` : ''}`
}

/** "5 min", "3 h", "2 d": minutes since */
export const shortAgo = (m: number) => (m < 60 ? `${m} min` : m < 60 * 24 ? `${Math.round(m / 60)} h` : `${Math.round(m / 60 / 24)} d`)
export const minutesSince = (at: number | null | undefined, now = Date.now()) => (at ? Math.max(1, Math.round((now / 1000 - at) / 60)) : null)

/** What is in flight there, as the row says it. */
export function inFlight(c: Pick<Conversation, 'working' | 'needs_you'>): { running: number; waiting: number } {
  return { running: c.working ?? 0, waiting: c.needs_you ?? 0 }
}

/** The faint time on a row: when it last moved, or when it was put away. */
export function rowTime(c: Conversation, now = Date.now()): { words: string; busy: boolean } {
  const st = stateOf(c)
  if (st === 'archived') return { words: `archived ${dayWord(c.state_at, now)}`.trim(), busy: false }
  if (st === 'trashed') return { words: `in Trash · ${dayWord(c.state_at, now)}`, busy: false }
  const idle = minutesSince(c.last_activity ?? c.created, now)
  const busy = (c.working ?? 0) > 0
  return { words: [busy ? 'working' : null, idle ? shortAgo(idle) : null].filter(Boolean).join(' · '), busy }
}

/** A row's accessible name: its title, state and work in words. */
export function rowLabel(c: Conversation, now = Date.now()): string {
  const st = stateOf(c)
  const { running, waiting } = inFlight(c)
  const idle = minutesSince(c.last_activity ?? c.created, now)
  return [c.name || 'Unnamed conversation',
    st === 'archived' ? `archived ${dayWord(c.state_at, now)}` : st === 'trashed' ? `in Trash since ${dayWord(c.state_at, now)}` : idle ? `active ${shortAgo(idle)} ago` : null,
    running ? `${running} ${running === 1 ? 'run' : 'runs'} working` : null,
    waiting ? `${waiting} waiting for you` : null].filter(Boolean).join(', ')
}

/** Why Trash is refused while work is in flight: the server's own words
 *  (`conversation.trash_refusal_words`). */
export function trashRefusal(running: number, waiting: number): string | null {
  if (!running && !waiting) return null
  const parts = [running ? `${running} ${running === 1 ? 'run' : 'runs'} still working` : null, waiting ? `${waiting} waiting for you` : null].filter(Boolean)
  return parts.join(' and ') + '. Stop or finish them first.'
}

export const ARCHIVE_NOTE = 'Work is still running here. It continues while archived.'
export const DELETION_UNAVAILABLE = 'Not available yet. Mentis keeps every post in a permanent record; erasing it needs your decision.'

export type MenuAct = ConversationChange | 'rename' | 'delete'
export type MenuEntry =
  | { kind: 'item'; act: MenuAct; label: string; sub?: string; note?: boolean; disabled?: boolean; danger?: boolean }
  | { kind: 'danger-head' }

export const STATE_CHANGING = 'A change to this conversation is still being made.'

/** The menu for one row. Rename is not offered in Trash (restore it first).
 *  While a state change of this row is on its way (`changing`), no other is
 *  offered: changes are made one at a time. */
export function menuFor(c: Conversation, deletion: DeletionCapability | null, changing = false): MenuEntry[] {
  const entries = menuEntries(c, deletion)
  if (!changing) return entries
  return entries.map((e) => (e.kind === 'item' && e.act !== 'rename' && e.act !== 'delete'
    ? { ...e, disabled: true, sub: STATE_CHANGING, note: false } : e))
}

function menuEntries(c: Conversation, deletion: DeletionCapability | null): MenuEntry[] {
  const st = stateOf(c)
  const { running, waiting } = inFlight(c)
  const refusal = trashRefusal(running, waiting)
  const trash: MenuEntry = { kind: 'item', act: 'trash', label: 'Move to Trash', sub: refusal ?? undefined, disabled: !!refusal }
  if (st === 'active') return [
    { kind: 'item', act: 'rename', label: 'Rename' },
    { kind: 'item', act: 'archive', label: 'Archive', sub: running ? ARCHIVE_NOTE : undefined, note: !!running },
    trash,
  ]
  if (st === 'archived') return [
    { kind: 'item', act: 'rename', label: 'Rename' },
    { kind: 'item', act: 'unarchive', label: 'Unarchive' },
    trash,
  ]
  const available = !!deletion?.available
  return [
    { kind: 'item', act: 'restore', label: 'Restore' },
    { kind: 'danger-head' },
    available
      ? { kind: 'item', act: 'delete', label: 'Permanently delete…', danger: true }
      : { kind: 'item', act: 'delete', label: 'Permanently delete', sub: deletion?.why || DELETION_UNAVAILABLE, disabled: true, danger: true },
  ]
}

/** What the page says once a change is made. */
export function changedWords(change: ConversationChange, name: string, running = 0): string {
  if (change === 'archive') return `Archived “${name}”${running ? '. Its work continues.' : '.'}`
  if (change === 'unarchive') return `“${name}” is active again.`
  if (change === 'trash') return `Moved “${name}” to Trash.`
  return `Restored “${name}”.`
}

/* -- THE DANGER ZONE ---------------------------------------------------------
   A full-screen confirmation, reachable only when permanent deletion is
   available (it is not: see `menuFor`). Cancel has focus first; the delete
   button stays disabled until `delete` is typed, so no ordinary keypress
   sequence can delete; Esc and Cancel go back to the list. */
export const DANGER_HEADLINE = 'This conversation will be permanently deleted. This cannot be undone.'
export const DANGER_CONFIRM_WORD = 'delete'
export const DELETION_EFFECTS: { heading: string; lines: string[] }[] = [
  { heading: 'Removed', lines: [
    'The text of every post and reply.',
    'Files only this conversation holds (uploads and files agents returned).',
    'What agents were sent here.',
  ] },
  { heading: 'Kept', lines: [
    'A record that the conversation existed and was deleted: when, and by whom.',
    'Who did what and when, without the content.',
    'Files also held by another conversation or source.',
    'Rules, lessons, decisions and outcomes made from it. They stay, but their link back points to deleted text.',
  ] },
  { heading: 'Not reached', lines: ['Backups, Git repositories and agent runtime logs outside Mentis.'] },
]

export interface DangerState { typed: string; done: 'open' | 'back' | 'confirmed' }
export type DangerEvent = { type: 'type'; text: string } | { type: 'cancel' } | { type: 'escape' } | { type: 'confirm' }
export const dangerStart = (): DangerState => ({ typed: '', done: 'open' })
export const dangerFirstFocus = 'cancel' as const
export const canConfirm = (typed: string) => typed.trim().toLowerCase() === DANGER_CONFIRM_WORD
/** The overlay's whole behaviour: typing, Cancel, Esc and Confirm. Confirm
 *  does nothing until the word is typed. */
export function dangerStep(s: DangerState, e: DangerEvent): DangerState {
  if (s.done !== 'open') return s
  if (e.type === 'type') return { ...s, typed: e.text }
  if (e.type === 'cancel' || e.type === 'escape') return { ...s, done: 'back' }
  return canConfirm(s.typed) ? { ...s, done: 'confirmed' } : s
}
