/* THE FRAME: Focus keeps the working panel in the focused column, and the
 * bar says each status once (fix-frame).
 *
 * - In Focus the posts and the composer keep to an 880 px column; the run
 *   panel and who-is-working line under it, and the tools strip above it,
 *   keep to the same column instead of spanning the whole window.
 * - The bar names the post read once (the This post tab, its author on
 *   hover): no Reading box repeating its number beside it.
 * - The count of other conversations says "elsewhere" in words. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { elsewhereWords, thisPostTitle } from '../src/fluid/frame/barWords'

const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (p: string) => readFileSync(src + p, 'utf8').replace(/\r\n/g, '\n')

/* -- Focus: everything at the column's edges keeps to the focused column ---- */
const conv = read('fluid/conversation/conversation.css').replace(/\/\*[\s\S]*?\*\//g, '')
const rules = (sel: string) => [...conv.matchAll(/([^{}]+)\{([^}]*)\}/g)]
  .filter((m) => m[1].split(',').some((s) => s.trim() === sel)).map((m) => m[2])
const COLUMN = /max\(\s*(\d+)px,\s*calc\(\(100% - 880px\) \/ 2 \+ \1px\)\)/
for (const [sel, prop] of [
  ['.fx-main.fx-focus > .fq-col .fx-conv .fr-panel', 'margin-left'],
  ['.fx-main.fx-focus > .fq-col .fx-conv .fr-panel', 'margin-right'],
  ['.fx-main.fx-focus > .fq-col .fx-conv .fx-working', 'margin-left'],
  ['.fx-main.fx-focus > .fq-col .fx-conv .fx-working', 'margin-right'],
  ['.fx-main.fx-focus > .fq-col .fx-conv .fx-conv-tools', 'padding-left'],
  ['.fx-main.fx-focus > .fq-col .fx-conv .fx-conv-tools', 'padding-right'],
] as const) {
  const decl = rules(sel).join(';').split(';').find((d) => d.trim().startsWith(prop + ':'))
  assert.ok(decl, `${sel} sets ${prop} in Focus`)
  assert.match(decl!, COLUMN, `${sel} ${prop} keeps to the 880 px column`)
}
// the composer's own column, which the rules above follow
assert.ok(rules('.fx-main.fx-focus > .fq-col .fx-conv .fx-composer-slot').some((r) => /max-width:\s*880px/.test(r)))
// the posts are centred where the composer is: the scrollbar's gutter on both sides
assert.ok(rules('.fx-main.fx-focus > .fq-col .fx-conv .fx-conv-scroll').some((r) => /scrollbar-gutter:\s*stable both-edges/.test(r)))

/* -- the bar: each status said once ---------------------------------------- */
const bar = read('fluid/frame/TopBar.tsx')
assert.ok(!/ReadingBox|readingBox|fx-readbox/.test(bar), 'no Reading box repeating the This post tab')
assert.ok(!/●\{n\}/.test(bar), 'the elsewhere count is not a bare dot')

assert.equal(thisPostTitle(49, '@brian'), 'Reading #49 by @brian')
assert.equal(thisPostTitle(49, 'brian'), 'Reading #49 by @brian')
assert.equal(thisPostTitle(7, null), 'Reading #7')
assert.match(thisPostTitle(null, '@brian'), /^This post/)

assert.deepEqual(elsewhereWords(2), { short: '2', word: 'elsewhere', title: '2 other conversations are working or waiting on you' })
assert.equal(elsewhereWords(1).title, '1 other conversation is working or waiting on you')

console.log('fluid_frame_unit: ok')
