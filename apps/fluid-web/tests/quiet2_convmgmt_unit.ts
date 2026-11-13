/* QUIET CHAT CONVERSATION MANAGEMENT (owner-approved design, 2026-11-12),
 * checked without a browser: the list's words and rules, each row's menu,
 * the title filter, and the Danger Zone -- which the browser cannot reach,
 * because the server says permanent deletion is not available. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { Conversation, DeletionCapability } from '../src/fluid/store'
import {
  ARCHIVE_NOTE, DANGER_HEADLINE, DELETION_EFFECTS, DELETION_UNAVAILABLE, TABS, canConfirm, changedWords, dangerFirstFocus,
  dangerStart, dangerStep, emptyLine, menuFor, rowLabel, rowTime, titleMatches, trashRefusal,
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
assert.deepEqual(items(conv({ state: 'trashed' }), { available: true, why: '' }), ['Restore', '— Danger Zone —', 'Permanently delete…'])

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

const html = renderToStaticMarkup(createElement(DangerZone, { name: 'Scratch: PDF viewer tests', files: { removed: 3, shared: 1 }, onBack: () => {}, onConfirm: () => {} }))
assert.ok(html.includes(DANGER_HEADLINE), 'the exact headline')
assert.equal(DANGER_HEADLINE, 'This conversation will be permanently deleted. This cannot be undone.')
assert.ok(html.includes('Permanently delete “Scratch: PDF viewer tests”'), 'the conversation is named')
for (const g of DELETION_EFFECTS) { assert.ok(html.includes(`<h3>${g.heading}</h3>`)); for (const l of g.lines) assert.ok(html.includes(l), l) }
assert.deepEqual(DELETION_EFFECTS.map((g) => g.heading), ['Removed', 'Kept', 'Not reached'])
assert.ok(html.includes('3 files will be removed · 1 shared file stays'))
assert.match(html, /role="alertdialog" aria-modal="true"/)
assert.match(html, /<button[^>]*class="q2-danger-delete"[^>]*disabled=""/, 'delete is disabled at first')
assert.ok(html.indexOf('q2-danger-cancel') < html.indexOf('q2-danger-delete'))
const dz = src('quiet2/conversations/DangerZone.tsx')
assert.match(dz, /useEffect\(\(\) => \{ cancel\.current\?\.focus\(\) \}, \[\]\)/, 'Cancel takes focus when it opens')
assert.match(dz, /e\.key === 'Escape'[^\n]*send\(\{ type: 'escape' \}\)/, 'Esc goes back')

/* gated: the page opens it only from an enabled menu item, and no deletion
   code exists to call */
const q2 = src('quiet2/Quiet2.tsx')
assert.match(q2, /onConfirm=\{\(\) => \{ setDanger\(null\); setNotice\('Permanent deletion is not available on this server\.'\) \}\}/)
const store = src('fluid/store.ts')
assert.ok(!/conversations\/\$\{[^}]+\}\/(delete|erase|purge)/.test(store), 'no deletion route is called')
const list = src('quiet2/conversations/ConversationList.tsx')
assert.match(list, /if \(!it\.disabled\) void act\(menuRow, it\.act\)/, 'a disabled item does nothing')

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
