/* WHAT A RECORD'S FIELD HOLDS, DRAWN AS WHAT IT IS (re-review finding F2-R1;
 * src/surfaces/entryValue.tsx).
 *
 * A declared field may hold a structured value, and the record inspector drew
 * every field through `String(value)`: for anything but a string, a number or
 * a boolean that is the word `[object Object]`. That inspector is the ONLY way
 * Fluid's exact-source opener lets the owner read a supported non-post record
 * before approving it, so the words a decision is about were in the entry read
 * and nowhere on the screen.
 *
 * What this holds the rendering to:
 *   - CONTENT IS PRESERVED. Every leaf the value holds is drawn, under the name
 *     the record gave it; nothing is summarised, counted or truncated.
 *   - `[object Object]` NEVER APPEARS, for any shape.
 *   - A SINGLE STRING IS EXACTLY WHAT IT WAS: prose, drawn by `Prose`.
 *   - NOTHING IS SUBSTITUTED, and an empty list or record is said to be empty.
 *   - NO KIND AND NO FIELD IS NAMED: the shape decides, so a Kind defined after
 *     this was written reads correctly too. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { EMPTY_LIST, EMPTY_RECORD, FieldValue, valueWords } from '../src/surfaces/entryValue'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

/** The field as the inspector draws it, as text, with the markup taken out. */
const drawn = (value: unknown): string =>
  renderToStaticMarkup(createElement(FieldValue, { value, scope: 'entry:ent-one:design' }))
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

const PURPOSE = 'Build this isolated widget only.'
const RESTRICTION = 'Deployment is forbidden.'

/* -- THE SHAPE THE FINDING WAS FOUND WITH ----------------------------------
   A dynamic Kind with one declared field holding a structured design. The
   corpus accepts it; the inspector showed `[object Object]`. */
{
  const design = { purpose: PURPOSE, restriction: RESTRICTION }
  const said = drawn(design)
  ok(!said.includes('[object Object]'), 'a structured field is never drawn as [object Object]')
  ok(said.includes(PURPOSE), 'every part the record holds is on the screen')
  ok(said.includes(RESTRICTION), 'all of them, not the first')
  ok(said.indexOf('purpose') < said.indexOf('restriction'),
    'under the names the record gave them, in the order the record holds them')
  ok(said.indexOf(PURPOSE) < said.indexOf(RESTRICTION), 'and each name leads its own value')
  ok(valueWords(design).includes(PURPOSE) && valueWords(design).includes(RESTRICTION),
    'and the plain-text reading an act must state keeps both as well')
  ok(!valueWords(design).includes('[object Object]'), 'with no [object Object] in it either')
}

/* -- A LIST OF CONTENT PARTS, which is what a contribution's `parts` is -----
   The exact-source opener falls back to this inspector where the post read
   FAILED, so a post's own words have to be readable here too. */
{
  const parts = [{ type: 'text', text: 'Exact candidate owl. Build only; no deployment.' },
    { type: 'text', text: 'A second part, equally recorded.' }]
  const said = drawn(parts)
  ok(!said.includes('[object Object]'), 'a list of structured parts is not [object Object] either')
  ok(said.includes('Exact candidate owl. Build only; no deployment.'), 'the words of the first part are drawn')
  ok(said.includes('A second part, equally recorded.'), 'and of the second: nothing is dropped as a summary')
  ok(said.indexOf('Exact candidate owl') < said.indexOf('A second part'), 'in the order the record holds them')
}

/* -- NESTED AS DEEPLY AS THE RECORD NESTS IT -------------------------------- */
{
  const said = drawn({ outer: { inner: ['one', { deepest: 'kept' }] } })
  for (const word of ['outer', 'inner', 'one', 'deepest', 'kept']) {
    ok(said.includes(word), `a nested leaf is still drawn (${word})`)
  }
  ok(!said.includes('[object Object]'), 'however deep it goes')
}

/* -- A STRING IS EXACTLY WHAT IT ALWAYS WAS -------------------------------- */
{
  const one = 'Candidate design: build only; no deployment.'
  eq(drawn(one), one, 'a single-string field reads as the prose it is, unchanged')
  eq(valueWords(one), one, 'and its plain-text reading is the string itself')
  eq(valueWords(7), '7', 'a number is its own value')
  eq(valueWords(false), 'false', 'and so is a boolean')
  eq(drawn(7), '7', 'drawn the same way')
}

/* -- NOTHING IS SUBSTITUTED, AND EMPTY IS SAID TO BE EMPTY ----------------- */
{
  eq(drawn([]), EMPTY_LIST, 'a declared field holding an empty list says so')
  eq(drawn({}), EMPTY_RECORD, 'and one holding no parts says that')
  eq(drawn(null), '', 'nothing recorded is drawn as nothing, not as a word')
  eq(drawn(undefined), '', 'and neither is an absent field')
  for (const empty of [EMPTY_LIST, EMPTY_RECORD]) {
    ok(!/\b(deleted|missing|erased)\b/.test(empty), `and says nothing about the record (${empty})`)
  }
}

/* -- NO KIND AND NO FIELD IS NAMED IN THE RENDERING ------------------------ */
{
  const text = readFileSync(fileURLToPath(new URL('../src/surfaces/entryValue.tsx', import.meta.url)), 'utf8')
  for (const named of ["'contribution'", "'parts'", "'review-design'", "'design'"]) {
    ok(!text.includes(named), `the shape decides how a field is drawn, not its Kind or name (${named})`)
  }
}

console.log(`entry value: ${checks} checks ok`)
