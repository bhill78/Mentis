/* Quiet Chat's run Permission (item 5.7): the four modes in the owner's wording with help for
 * each; the never-wait label no longer carries its explanation; how a change reaches the run is
 * a compact badge with a glyph (not colour alone) and the server's words; the explanatory
 * prose is help, not standing text; Execution stays a separate, fixed row. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { CHANGE_HELP, EXECUTION_HELP, PERMISSION_OPTIONS, effectBadge } from '../src/quiet2/activity/permission'

const src = (p: string) => readFileSync(new URL('../src/' + p, import.meta.url), 'utf8')

assert.deepEqual(PERMISSION_OPTIONS.map((o) => o.mode), ['ask', 'task', 'deny', 'all'])
assert.deepEqual(PERMISSION_OPTIONS.map((o) => o.words), ['Ask for permission', 'Allow routine operations', 'Never wait for me', 'Allow all operations'])
for (const o of PERMISSION_OPTIONS) assert.ok(o.help.length > 20, o.mode)
assert.match(PERMISSION_OPTIONS[2].help, /refused at once/)
assert.match(CHANGE_HELP, /waiting for you is decided again/)
assert.match(EXECUTION_HELP, /separate from Permission Mode/)

/* the badge: the server's state, a glyph, a few words, the server's full words */
const words = 'In force now: the run\'s next permission request is decided by it.'
assert.deepEqual(effectBadge({ state: 'applied', at: 'next-request', words }),
  { state: 'applied', glyph: '●', short: 'Applied · next request', words })
assert.equal(effectBadge({ state: 'applied', at: 'next-request', words, answered_now: [{ answer: 'allowed', by: 'task' }] })!.short,
  'Applied · next request · waiting request allowed')
assert.equal(effectBadge({ state: 'applied', at: 'next-request', words, answered_now: [{ answer: 'refused', by: 'deny' }] })!.short,
  'Applied · next request · waiting request refused')
assert.equal(effectBadge({ state: 'pending', at: 'next-run', words: 'w' })!.short, 'Pending · from its next run')
assert.equal(effectBadge({ state: 'pending', at: 'restart', words: 'w' })!.short, 'Pending · restarting fresh')
assert.equal(effectBadge({ state: 'pending', at: 'session-open', words: 'w' })!.short, 'Pending · when its session opens')
assert.deepEqual([effectBadge({ state: 'unsupported', at: null, words: 'w' })!.glyph, effectBadge({ state: 'unsupported', at: null, words: 'w' })!.short],
  ['⊘', 'Not enforced by this runtime'])
assert.equal(effectBadge({ state: 'unknown', at: null, words: 'w' })!.short, 'Not known here')
assert.equal(effectBadge(null), null)
assert.equal(effectBadge(undefined), null)

/* the pane: no standing prose, help by hover AND focus, Execution apart and fixed */
const rc = src('quiet2/activity/RunControls.tsx')
assert.ok(!/CHANGE_WORDS|EXECUTION_FIXED/.test(rc), 'the permanent explanations are gone')
assert.match(rc, /aria-pressed=\{on\}/)
assert.match(rc, /aria-describedby=\{tip\}/)
assert.match(rc, /role="tooltip"/)
assert.match(rc, /className="q2-perm-row q2-perm-exec"/)
const css = src('quiet2/dock.css')
assert.match(css, /\.q2-perm-item:hover > \.q2-tip, \.q2-perm-item:focus-within > \.q2-tip \{ display: block; \}/)
assert.match(css, /\.q2-perm-opt\[aria-pressed="true"\] \{ font-weight: 700;/)
console.log('quiet2 permission ok')
