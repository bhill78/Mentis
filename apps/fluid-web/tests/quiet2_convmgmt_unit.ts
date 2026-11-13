/* QUIET CHAT CONVERSATION MANAGEMENT (owner-approved design, 2026-11-12),
 * checked without a browser: the list's words and rules, each row's menu,
 * the title filter, the Danger Zone with a deletion's real impact, refusals,
 * tombstones and the physical cleanup status (owner decision 2026-11-13). */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { Conversation, DeletionCapability, DeletionImpact } from '../src/fluid/store'
import {
  ARCHIVE_NOTE, DANGER_HEADLINE, STATE_CHANGING, DELETION_UNAVAILABLE, TABS, canConfirm, changedWords, dangerFirstFocus,
  dangerStart, dangerStep, emptyLine, menuFor, rowLabel, rowTime, titleMatches, trashRefusal,
  impactGroups, deletionRefusal, cleanupOf, cleanupWords, cleanupOffered, cleanupMeaning, deletedWords, isDeleted, stateOf, tombstoneLabel, relationWords,
} from '../src/quiet2/conversations/manage'
import DangerZone from '../src/quiet2/conversations/DangerZone'

const src = (p: string) => readFileSync(new URL('../src/' + p, import.meta.url), 'utf8')
const NOW = Date.UTC(2026, 10, 12, 20, 0, 0)
const conv = (over: Partial<Conversation> = {}): Conversation => ({
  id: 'ent-1', name: 'Release 0.9: planning the rollout', created: NOW / 1000 - 86400, posts: 3, included: 0,
  participants: 1, last_activity: NOW / 1000 - 120 * 60, working: 0, needs_you: 0, state: 'active', ...over,
})
const UNAVAILABLE: DeletionCapability = { available: false, why: DELETION_UNAVAILABLE }
const items = (c: Conversation, d: DeletionCapability | null = UNAVAILABLE) =>
  menuFor(c, d).map((e) => (e.kind === 'item' ? `${e.label}${e.disabled ? ' (disabled)' : ''}` : '— Danger Zone —'))

/* tabs: text, in order, no counts */
assert.deepEqual(TABS.map((t) => t.label), ['Active', 'Archived', 'Trash'])

/* the title filter: every word, any case, titles only */
assert.ok(titleMatches('Release 0.9: planning the rollout', 'PLAN roll'))
assert.ok(!titleMatches('Release 0.9: planning the rollout', 'deploy'))
assert.ok(titleMatches('anything', '   '))
assert.equal(emptyLine('archived', 'rev'), 'No archived conversation titled “rev”.')
assert.equal(emptyLine('trashed', 'rev'), 'No conversation in Trash titled “rev”.')
assert.equal(emptyLine('trashed', ''), 'Trash is empty.')

/* rows: one line, a faint time; put-away rows say when; work says it works */
assert.equal(rowTime(conv(), NOW).words, '2 h')
assert.deepEqual(rowTime(conv({ working: 2, last_activity: NOW / 1000 - 5 * 60 }), NOW), { words: 'working · 5 min', busy: true })
assert.equal(rowTime(conv({ state: 'archived', state_at: Date.UTC(2026, 10, 3, 12) / 1000 }), NOW).words, 'archived 3 Nov')
assert.equal(rowTime(conv({ state: 'trashed', state_at: Date.UTC(2026, 10, 10, 12) / 1000 }), NOW).words, 'in Trash · 10 Nov')
assert.match(rowLabel(conv({ working: 2, needs_you: 1 }), NOW), /2 runs working, 1 waiting for you$/)

/* menus, by state */
assert.deepEqual(items(conv()), ['Rename', 'Archive', 'Move to Trash'])
assert.deepEqual(items(conv({ state: 'archived' })), ['Rename', 'Unarchive', 'Move to Trash'])
assert.deepEqual(items(conv({ state: 'trashed' })), ['Restore', '— Danger Zone —', 'Permanently delete (disabled)'])
const del = menuFor(conv({ state: 'trashed' }), UNAVAILABLE).at(-1)!
assert.ok(del.kind === 'item' && del.disabled && del.sub === DELETION_UNAVAILABLE, 'deletion is disabled with the reason')
/* not read, or unreadable: still disabled */
assert.deepEqual(items(conv({ state: 'trashed' }), null), ['Restore', '— Danger Zone —', 'Permanently delete (disabled)'])
/* only a server saying it is available would enable it */
const AVAILABLE: DeletionCapability = { available: true, why: '' }
assert.deepEqual(items(conv({ state: 'trashed' }), AVAILABLE), ['Restore', '— Danger Zone —', 'Permanently delete…'])
/* ... and only once Trash's work check passes: work in flight says why */
assert.deepEqual(items(conv({ state: 'trashed', working: 1 }), AVAILABLE), ['Restore', '— Danger Zone —', 'Permanently delete (disabled)'])
const held = menuFor(conv({ state: 'trashed', needs_you: 2 }), AVAILABLE).at(-1)!
assert.ok(held.kind === 'item' && held.disabled && held.sub === '2 waiting for you. Stop or finish them first.')
/* a deleted conversation is in no tab */
assert.ok(isDeleted(conv({ state: 'deleted' })) && stateOf(conv({ state: 'deleted' })) === 'active' && !isDeleted(conv({ state: 'trashed' })))
assert.match(src('quiet2/conversations/ConversationList.tsx'), /!isDeleted\(c\) && stateOf\(c\) === tab/)

/* one state change at a time: while one is on its way, no other is offered */
const pending = menuFor(conv(), UNAVAILABLE, true)
assert.deepEqual(pending.map((e) => (e.kind === 'item' ? [e.label, !!e.disabled] : null)),
  [['Rename', false], ['Archive', true], ['Move to Trash', true]])
assert.ok(pending.every((e) => e.kind !== 'item' || e.act === 'rename' || e.sub === STATE_CHANGING))
assert.match(src('quiet2/conversations/ConversationList.tsx'), /menuFor\(menuRow, cap, store\.changingState\(menuRow\.id\)\)/)

/* active work: Archive with a note, Trash refused with the reason */
const busy = conv({ working: 2, needs_you: 1 })
assert.deepEqual(items(busy), ['Rename', 'Archive', 'Move to Trash (disabled)'])
const [, archive, trash] = menuFor(busy, UNAVAILABLE)
assert.ok(archive.kind === 'item' && archive.sub === ARCHIVE_NOTE && !archive.disabled)
assert.ok(trash.kind === 'item' && trash.sub === '2 runs still working and 1 waiting for you. Stop or finish them first.')
assert.equal(trashRefusal(1, 0), '1 run still working. Stop or finish them first.')
assert.equal(trashRefusal(0, 0), null)
assert.deepEqual(items(conv({ state: 'archived', needs_you: 1 })), ['Rename', 'Unarchive', 'Move to Trash (disabled)'])
assert.equal(changedWords('archive', 'A', 2), 'Archived “A”. Its work continues.')

/* THE DANGER ZONE: Cancel first, delete only once typed, Cancel/Esc go back */
assert.equal(dangerFirstFocus, 'cancel')
let s = dangerStart()
assert.equal(s.done, 'open')
s = dangerStep(s, { type: 'confirm' })
assert.equal(s.done, 'open', 'confirm does nothing before the word is typed')
s = dangerStep(s, { type: 'type', text: 'delet' })
assert.equal(dangerStep(s, { type: 'confirm' }).done, 'open')
assert.ok(!canConfirm('Delete it'))
s = dangerStep(s, { type: 'type', text: ' Delete ' })
assert.equal(dangerStep(s, { type: 'confirm' }).done, 'confirmed')
assert.equal(dangerStep(dangerStart(), { type: 'cancel' }).done, 'back')
assert.equal(dangerStep(dangerStart(), { type: 'escape' }).done, 'back')
assert.equal(dangerStep({ typed: 'delete', done: 'back' }, { type: 'confirm' }).done, 'back', 'nothing after going back')

assert.equal(dangerStep({ typed: 'delete', done: 'confirmed' }, { type: 'cancel' }).done, 'confirmed', 'nothing is taken while deleting')
/* a refusal opens it again; a changed impact clears the word */
assert.deepEqual(dangerStep({ typed: 'delete', done: 'confirmed' }, { type: 'refused', again: true }), { typed: '', done: 'open' })
assert.deepEqual(dangerStep({ typed: 'delete', done: 'confirmed' }, { type: 'refused', again: false }), { typed: 'delete', done: 'open' })
assert.deepEqual(dangerStep({ typed: 'x', done: 'open' }, { type: 'refused', again: true }), { typed: 'x', done: 'open' })

/* THE IMPACT, as the server reads it (the shape of `deletion-impact`) */
const IMPACT: DeletionImpact = {
  conversation: 'ent-d',
  counts: { posts: 3, replies: 2, versions: 1, topics: 0, entries: 6, links_with_words_erased: 10, acts: 17, acts_kept: 0, runs_material: 1 },
  files_removed: [{ label: 'only-here.txt', size: 40 }],
  files_kept: [{ label: 'shared.txt', why: 'referenced by something that is kept' }],
  surviving_records: [{ id: 'ent-o', kind: 'outcome', title: 'It worked', relation: 'outcome-of' }],
  relationships: { other_conversations: ['ent-k'], work_across: 0, surviving_records: 1 },
  cannot_erase: [{ what: 'earlier backups, snapshots and exports', why: 'copies made before deletion are outside this Brain' }],
  token: 'tok-1',
}
const groups = impactGroups(IMPACT)
assert.deepEqual(groups.map((g) => g.heading), ['Removed', 'Kept', 'Not reached'])
const flat = JSON.stringify(groups)
for (const w of ['The text of 3 posts and 2 replies, with 1 earlier version.', '1 file only this conversation holds:', 'only-here.txt · 40 B',
  'What agents were sent here (1 run record).', 'Who did what and when (17 activity records), without the content.', '1 shared file stays:',
  'shared.txt · referenced by something that is kept', 'outcome “It worked” · an outcome of one of its posts', '1 other conversation connected to it',
  'Earlier backups, snapshots and exports.']) assert.ok(flat.includes(w), w)
/* the bytes are never said to be gone at once */
assert.ok(flat.includes('Removing the old bytes from disk is a cleanup that follows'))
assert.equal(relationWords('extracted-from'), 'extracted from one of its posts')

const html = renderToStaticMarkup(createElement(DangerZone, { conversation: conv({ id: 'ent-d', state: 'trashed' }), name: 'Scratch: PDF viewer tests', initial: IMPACT, onBack: () => {}, onDeleted: () => {} }))
assert.ok(html.includes(DANGER_HEADLINE), 'the exact headline')
assert.equal(DANGER_HEADLINE, 'This conversation will be permanently deleted. This cannot be undone.')
assert.ok(html.includes('Permanently delete “Scratch: PDF viewer tests”'), 'the conversation is named')
for (const g of groups) assert.ok(html.includes(`<h3>${g.heading}</h3>`))
assert.ok(html.includes('data-impact="tok-1"') && html.includes('only-here.txt · 40 B'), 'the real impact is shown')
assert.match(html, /role="alertdialog" aria-modal="true"/)
assert.match(html, /<button[^>]*class="q2-danger-delete"[^>]*disabled=""/, 'delete is disabled at first')
assert.ok(html.indexOf('q2-danger-cancel') < html.indexOf('q2-danger-delete'))
/* not read yet: reading, and still disabled */
const reading = renderToStaticMarkup(createElement(DangerZone, { conversation: conv({ id: 'ent-d', state: 'trashed' }), name: 'X', onBack: () => {}, onDeleted: () => {} }))
assert.ok(reading.includes('Reading what would be deleted') && /class="q2-danger-delete"[^>]*disabled=""/.test(reading))
const dz = src('quiet2/conversations/DangerZone.tsx')
assert.match(dz, /useEffect\(\(\) => \{ cancel\.current\?\.focus\(\) \}, \[\]\)/, 'Cancel takes focus when it opens')
assert.match(dz, /e\.key === 'Escape'[^\n]*send\(\{ type: 'escape' \}\)/, 'Esc goes back')
assert.match(dz, /const ok = canConfirm\(s\.typed\) && !!impact && !deleting/, 'delete needs the word and the impact')
assert.match(dz, /store\.deleteConversation\(conversation\.id, author, impact\.token\)/, 'the deletion presents the token shown')

/* refusals, in plain words */
assert.equal(deletionRefusal({ code: 'impact-changed', error: 'x' }).again, true)
assert.match(deletionRefusal({ code: 'impact-changed' }).words, /changed since it was shown/)
assert.match(deletionRefusal({ code: 'work-in-flight', error: '1 run still working. Stop or finish them first.' }).words, /^Work is still in flight here, so nothing was deleted: 1 run still working/)
assert.match(deletionRefusal({ code: 'owner-only' }).words, /Only the owner/)
assert.match(deletionRefusal(new Error('boom')).words, /^Nothing was deleted: boom$/)

/* PHYSICAL CLEANUP: said apart, never claimed before it is verified */
assert.equal(cleanupWords(cleanupOf({ status: 'pending' })), 'Cleanup pending')
assert.equal(cleanupWords(cleanupOf('completed')), 'Cleanup complete')
assert.equal(cleanupWords(cleanupOf({ status: 'failed', reason: 'a reader held the WAL' })), 'Cleanup failed: a reader held the WAL')
assert.equal(cleanupOf(undefined).status, 'unknown')
assert.equal(cleanupOf({ status: 'done?' as never }).status, 'unknown', 'an unknown word is never read as complete')
assert.ok(cleanupOffered(cleanupOf('pending')) && cleanupOffered(cleanupOf('failed')) && !cleanupOffered(cleanupOf('completed')) && !cleanupOffered(cleanupOf(undefined)))
assert.ok(cleanupMeaning(cleanupOf('pending')).includes('not verified yet'))
assert.equal(deletedWords('A', cleanupOf('pending')), 'Permanently deleted “A”. Cleanup pending.')
assert.match(tombstoneLabel({ created: NOW / 1000 - 86400, deleted_at: NOW / 1000, counts: { posts: 3, replies: 2 } }, '@brian', NOW), /^Deleted conversation, created 11 Nov, deleted today by @brian, 5 posts removed$/)

/* wired: the page draws it from an enabled menu item, and after a deletion
   says so with the cleanup apart, back at the list */
const q2 = src('quiet2/Quiet2.tsx')
assert.match(q2, /onDeleted=\{\(done\) => \{ setNotice\(deletedWords\([^\n]*cleanupOf\(done\.physical_cleanup\)\)\); setDanger\(null\); setListSignal\(\(n\) => n \+ 1\) \}\}/)
assert.match(q2, /deleted && conversationId \? \(\s*<div className="q2-stream"><TombstoneView id=\{conversationId\} \/><\/div>/)
const store = src('fluid/store.ts')
assert.match(store, /\/fluid\/api\/conversations\/\$\{encodeURIComponent\(conversation\)\}\/delete/)
const list = src('quiet2/conversations/ConversationList.tsx')
assert.match(list, /if \(!it\.disabled\) void act\(menuRow, it\.act\)/, 'a disabled item does nothing')
assert.match(list, /tab === 'trashed' && \(\s*<button[^\n]*className="q2-link-quiet q2-cl-foot"[^\n]*>Deleted conversations<\/button>/)
const tomb = src('quiet2/conversations/Tombstone.tsx')
assert.match(tomb, /cleanupOffered\(cleanup\) && !READ_ONLY && \(/, 'Finish cleanup only while pending or failed')
/* in Trash or deleted, posts offer no Reply or Edit and words no selection acts */
assert.match(src('quiet2/Post.tsx'), /const closed = row\?\.state === 'trashed' \|\| row\?\.state === 'deleted'/)
assert.match(src('quiet2/annotate/Selection.tsx'), /home\?\.state === 'trashed' \|\| home\?\.state === 'deleted'\) return null/)

/* the list has no post search and does not open the global Search */
assert.ok(!/useSearch|references|GlobalDock/.test(list))
assert.match(list, /aria-label="Filter these conversations by title"/)
/* the global Search panel is unchanged by this work */
assert.ok(!/conversation_state|In posts/.test(src('quiet2/GlobalDock.tsx')))

/* the rail's page is read as Active (not filtered after an unfiltered page) */
assert.match(q2, /store\.listState = 'active'\s*\n\s*store\.loadList\(\)/)
/* every Dock refuses to post into a conversation in Trash: the reading
   column and every working surface use it */
const dock = src('quiet2/Dock.tsx')
assert.match(dock, /row && row\.state === 'trashed' \? <TrashedComposer/)
assert.match(dock, /: blocked\s*\n\s*\? blocked/)
assert.ok((src('quiet2/Surface.tsx').match(/<Dock /g) ?? []).length >= 2)
/* a failed Restore from a surface's guard is shown there, not dropped */
const cstate = src('quiet2/conversations/ConversationState.tsx')
assert.match(dock, /<TrashedComposer row=\{row\} \/>/)
assert.equal((cstate.match(/\{failed && <span className="q2-state-failed" role="alert">\{failed\}<\/span>\}/g) ?? []).length, 2)

console.log('quiet2 conversation management: ok')
