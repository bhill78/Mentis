/* CONVERSATION MANAGEMENT: the words and rules the list, its menus and the
 * Danger Zone share, kept apart from the components so they can be checked
 * without a browser (tests/quiet2_convmgmt_unit.ts).
 *
 * A Conversation is listed Active, Archived or in Trash. Each change is one
 * act on it (`store.changeConversationState`); its id, posts, replies, files
 * and work are untouched, so every change is undone exactly. Archive stops
 * nothing. Trash is refused while work is in flight -- by the server, and
 * said here before it is asked. Permanent deletion (from Trash only) is
 * offered only when the server says it is available
 * (`store.conversationDeletion`) and Trash's work check passes; otherwise
 * the item says why. */
import type { CleanupState, Conversation, ConversationChange, ConversationState, DeletionCapability, DeletionImpact, PhysicalCleanup, SurvivingRecord, Tombstone } from '../../fluid/store'

export const TABS: { id: ConversationState; label: string }[] = [
  { id: 'active', label: 'Active' }, { id: 'archived', label: 'Archived' }, { id: 'trashed', label: 'Trash' },
]

export const stateOf = (c: Pick<Conversation, 'state'> | null | undefined): ConversationState => {
  const s = c?.state
  return s === 'archived' || s === 'trashed' ? s : 'active'
}
/** Permanently deleted: in no list; only its tombstone opens. */
export const isDeleted = (c: Pick<Conversation, 'state'> | null | undefined): boolean => c?.state === 'deleted'

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
  /* THE TRASH WORK CHECK: work still in flight here refuses deletion as it
     refuses Trash (and the server asks again when it is confirmed) */
  return [
    { kind: 'item', act: 'restore', label: 'Restore' },
    { kind: 'danger-head' },
    !available
      ? { kind: 'item', act: 'delete', label: 'Permanently delete', sub: deletion?.why || DELETION_UNAVAILABLE, disabled: true, danger: true }
      : refusal
        ? { kind: 'item', act: 'delete', label: 'Permanently delete', sub: refusal, disabled: true, danger: true }
        : { kind: 'item', act: 'delete', label: 'Permanently delete…', danger: true },
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
   available (`menuFor`). It shows the deletion's actual impact, read from the
   server. Cancel has focus first; the delete button stays disabled until
   `delete` is typed and the impact is read, so no ordinary keypress sequence
   can delete; Esc and Cancel go back to the list. */
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
  /** the server refused the confirmed deletion: open again; `again` clears
   *  the typed word, so a changed impact is confirmed anew */
  | { type: 'refused'; again: boolean }
export const dangerStart = (): DangerState => ({ typed: '', done: 'open' })
export const dangerFirstFocus = 'cancel' as const
export const canConfirm = (typed: string) => typed.trim().toLowerCase() === DANGER_CONFIRM_WORD
/** The overlay's whole behaviour: typing, Cancel, Esc and Confirm. Confirm
 *  does nothing until the word is typed. While a confirmed deletion is on its
 *  way nothing else is taken; a refusal opens it again. */
export function dangerStep(s: DangerState, e: DangerEvent): DangerState {
  if (e.type === 'refused') return s.done === 'confirmed' ? { typed: e.again ? '' : s.typed, done: 'open' } : s
  if (s.done !== 'open') return s
  if (e.type === 'type') return { ...s, typed: e.text }
  if (e.type === 'cancel' || e.type === 'escape') return { ...s, done: 'back' }
  return canConfirm(s.typed) ? { ...s, done: 'confirmed' } : s
}

/* -- THE IMPACT, IN WORDS -----------------------------------------------------
   What the server says a deletion would do (`DeletionImpact`), shown under
   three headings. Every number is the server's; nothing is estimated here. */
const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`
export function sizeWords(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
/** How a surviving record is tied to what was deleted. */
export function relationWords(relation: string): string {
  switch (relation) {
    case 'extracted-from': return 'extracted from one of its posts'
    case 'derived-from': return 'derived from one of its posts'
    case 'outcome-of': return 'an outcome of one of its posts'
    case 'in-context': return 'recorded in its context'
    default: return relation.replace(/[-_]/g, ' ')
  }
}
export const recordWords = (r: SurvivingRecord) => `${r.kind.replace(/[-_]/g, ' ')} “${r.title}”`
/** At most this many files or records are named; the rest are counted. */
export const NAMED = 5
function named<T>(xs: T[], line: (x: T) => string): string[] {
  return [...xs.slice(0, NAMED).map(line), ...(xs.length > NAMED ? [`and ${xs.length - NAMED} more`] : [])]
}

export interface ImpactLine { text: string; sub?: string[] }
export interface ImpactGroup { heading: 'Removed' | 'Kept' | 'Not reached'; lines: ImpactLine[] }
export function impactGroups(i: DeletionImpact): ImpactGroup[] {
  const c = i.counts
  const removed: ImpactLine[] = []
  const words = [c.posts ? plural(c.posts, 'post') : null, c.replies ? plural(c.replies, 'reply', 'replies') : null].filter(Boolean).join(' and ')
  removed.push({ text: words
    ? `The text of ${words}${c.versions ? `, with ${plural(c.versions, 'earlier version')}` : ''}.`
    : 'It has no posts: its name and description.' })
  if (c.topics) removed.push({ text: `${plural(c.topics, 'topic')} only it has.` })
  if (i.files_removed.length) removed.push({
    text: `${plural(i.files_removed.length, 'file')} only this conversation holds:`,
    sub: named(i.files_removed, (f) => [f.label, sizeWords(f.size)].filter(Boolean).join(' · ')),
  })
  else removed.push({ text: 'No files: none is held only here.' })
  if (c.runs_material) removed.push({ text: `What agents were sent here (${plural(c.runs_material, 'run record')}).` })
  removed.push({ text: 'All of it stops being readable through Mentis at once. Removing the old bytes from disk is a cleanup that follows; its status is shown after, and called complete only once verified.' })
  const kept: ImpactLine[] = [
    { text: 'A record that the conversation existed and was deleted: when, and by whom.' },
    { text: c.acts ? `Who did what and when (${plural(c.acts, 'activity record')}), without the content.` : 'Who did what and when, without the content.' },
  ]
  if (i.files_kept.length) kept.push({
    text: `${plural(i.files_kept.length, 'shared file')} ${i.files_kept.length === 1 ? 'stays' : 'stay'}:`,
    sub: named(i.files_kept, (f) => `${f.label} · ${f.why}`),
  })
  const n = i.surviving_records.length
  if (n) kept.push({
    text: `${plural(n, 'record')} made from it ${n === 1 ? 'stays' : 'stay'}; ${n === 1 ? 'its' : 'their'} link back will read “Deleted post”:`,
    sub: named(i.surviving_records, (r) => `${recordWords(r)} · ${relationWords(r.relation)}`),
  })
  const others = i.relationships.other_conversations.length
  if (others) kept.push({ text: `${plural(others, 'other conversation')} connected to it ${others === 1 ? 'keeps its' : 'keep their'} own posts; links here will read “Deleted conversation”.` })
  const work = i.relationships.work_across
  if (work) kept.push({ text: `${plural(work, 'piece')} of work elsewhere ${work === 1 ? 'keeps its' : 'keep their'} record.` })
  if (c.acts_kept) kept.push({ text: `${plural(c.acts_kept, 'governance record')} made here ${c.acts_kept === 1 ? 'keeps its' : 'keep their'} words.` })
  const reach: ImpactLine[] = i.cannot_erase.length
    ? i.cannot_erase.map((x) => ({ text: x.what.charAt(0).toUpperCase() + x.what.slice(1) + '.', sub: [x.why] }))
    : [{ text: 'Backups, Git repositories and agent runtime logs outside Mentis.' }]
  return [{ heading: 'Removed', lines: removed }, { heading: 'Kept', lines: kept }, { heading: 'Not reached', lines: reach }]
}

/** A refused deletion, in plain words; whether the word must be typed again
 *  (`again`: what is shown is no longer what was confirmed) and whether the
 *  impact is read again (`reread`). */
export function deletionRefusal(e: unknown): { words: string; again: boolean; reread: boolean } {
  const x = (e ?? {}) as { code?: string; error?: string; message?: string }
  const said = (x.error || x.message || String(e)).trim()
  switch (x.code) {
    case 'impact-changed': return { words: 'What would be deleted changed since it was shown. It has been read again: check it, then type delete again.', again: true, reread: true }
    case 'work-in-flight': return { words: `Work is still in flight here, so nothing was deleted: ${said}`, again: false, reread: true }
    case 'not-in-trash': return { words: 'It is no longer in Trash, so it cannot be permanently deleted from here. Nothing was deleted.', again: true, reread: false }
    case 'conversation-deleted': return { words: 'It was already permanently deleted.', again: true, reread: false }
    case 'owner-only': return { words: 'Only the owner can permanently delete a conversation. Nothing was deleted.', again: false, reread: false }
    case 'record-moved': return { words: 'The record kept changing while the deletion was checked. Nothing was deleted; try again.', again: false, reread: true }
    default: return { words: `Nothing was deleted: ${said}`, again: false, reread: true }
  }
}

/** A tombstone's row in "Deleted conversations": no name, no words of it. */
export function tombstoneLabel(t: Pick<Tombstone, 'created' | 'deleted_at' | 'counts'>, by: string | null, now = Date.now()): string {
  const removed = (t.counts?.posts ?? 0) + (t.counts?.replies ?? 0)
  return ['Deleted conversation', t.created ? `created ${dayWord(t.created, now)}` : null,
    `deleted ${dayWord(t.deleted_at, now)}${by ? ` by ${by}` : ''}`,
    `${plural(removed, 'post')} removed`].filter(Boolean).join(', ')
}

/* -- PHYSICAL CLEANUP, said apart from the deletion ----------------------------
   The deletion is done once it commits: nothing of it is read through Mentis
   again. Whether the database's old pages and the files' bytes are gone is a
   separate status the server VERIFIES: pending, completed or failed. Nothing
   here says the bytes are gone before the server says `completed`. */
export interface Cleanup { status: CleanupState | 'unknown'; reason: string | null }
/** The status as the server reported it (an object, or the bare word);
 *  absent or unreadable: unknown, never assumed complete. */
export function cleanupOf(x: PhysicalCleanup | CleanupState | null | undefined): Cleanup {
  const raw = typeof x === 'string' ? { status: x } : x ?? null
  const st = raw?.status
  const reason = raw && typeof (raw as PhysicalCleanup).reason === 'string' && (raw as PhysicalCleanup).reason ? String((raw as PhysicalCleanup).reason) : null
  if (st === 'pending' || st === 'completed' || st === 'failed') return { status: st, reason }
  return { status: 'unknown', reason }
}
/** "Cleanup pending", "Cleanup complete", "Cleanup failed: <reason>". */
export function cleanupWords(c: Cleanup): string {
  if (c.status === 'completed') return 'Cleanup complete'
  if (c.status === 'failed') return `Cleanup failed${c.reason ? `: ${c.reason}` : ''}`
  if (c.status === 'pending') return 'Cleanup pending'
  return 'Cleanup status not reported'
}
/** What that status means, in a sentence, without claiming more. */
export function cleanupMeaning(c: Cleanup): string {
  if (c.status === 'completed') return 'The database was checkpointed and the files only it held were removed from disk; both were verified.'
  if (c.status === 'failed') return 'Its content cannot be read through Mentis, but old database pages or file bytes may still be on disk until cleanup is finished.'
  return 'Its content cannot be read through Mentis. Old database pages and file bytes are removed from disk by the cleanup, which is not verified yet.'
}
/** Whether "Finish cleanup" is offered. */
export const cleanupOffered = (c: Cleanup) => c.status === 'pending' || c.status === 'failed'

/** What the page says once a deletion is done: the deletion, then the
 *  cleanup apart from it. */
export const deletedWords = (name: string, cleanup?: Cleanup) =>
  `Permanently deleted “${name}”.` + (cleanup ? ` ${cleanupWords(cleanup)}.` : '')
