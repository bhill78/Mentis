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
import { EMPTY_LIST, EMPTY_RECORD, FieldValue, fieldScope, itemScope, partScope, valueWords } from '../src/surfaces/entryValue'

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

/* ONE STATE KEY NAMES EXACTLY ONE FIELD PATH (re-review finding F2-R1 and the
 * rule behind it): a marked block's state is kept under its scope, so no two
 * different places in a record may share one. Checked for every leaf of
 * records built to collide under the old dotted keys, not only the reported
 * example. */
{
  /** Every leaf's scope, walked exactly as `FieldValue` builds them. */
  const leaves = (entry: string, body: Record<string, unknown>) => {
    const out: string[] = []
    const walk = (v: unknown, scope: string) => {
      if (Array.isArray(v)) v.forEach((x, i) => walk(x, itemScope(scope, i)))
      else if (v && typeof v === 'object') Object.entries(v).forEach(([k, x]) => walk(x, partScope(scope, k)))
      else out.push(scope)
    }
    for (const [f, v] of Object.entries(body)) walk(v, fieldScope(entry, f))
    return out
  }
  const records: Record<string, unknown>[] = [
    { 'a.b': 'x', a: { b: 'y' } },                             // the reported case
    { a: ['p', 'q'], 'a.1': 'r', b: { '1': 's' }, c: [['t']], 'c.0': ['u'] },
    { 'a[0]': 'x', a: ['y'], 'a["k"]': 'z', 'a[\"k\"]': 'w', k: { '"k"': 'v' } },
    { 'x:y': 'p', x: { y: 'q' }, '': 'empty name', ' ': 'space', 'é.ü': { 'é': 'r' } },
  ]
  for (const r of records) {
    const got = leaves('ent-one', r)
    eq(new Set(got).size, got.length, `every leaf has its own state key: ${JSON.stringify(r)} -> ${got.join(' | ')}`)
  }
  // across fields of one record and between records of different entries
  // an entry id containing ':' cannot pass for part of a field (found by review:
  // under the old raw form ent-a + "b:c" and ent-a:b + "c" were one key)
  ok(fieldScope('ent-a', 'b:c') !== fieldScope('ent-a:b', 'c'), 'an entry id cannot pass for a field')
  // a numeric part name against a list position, and their old dotted collision
  ok(partScope('s', '1') !== itemScope('s', 1), 'part "1" and item [1] are different places')
  // EVERY VIEW OF ONE FIELD SHARES ITS STATE: the governance item and the record
  // inspector build the same key for the same field (found by review)
  const gov = readFileSync(fileURLToPath(new URL('../src/fluid/governance/GovItem.tsx', import.meta.url)), 'utf8')
  ok(!/scope=\{`entry:\$\{/.test(gov), 'the governance item builds field scopes only through fieldScope')
  ok(/fieldScope\(entry, x\.field\)/.test(gov) && /fieldScope\(id, f\)/.test(readFileSync(fileURLToPath(new URL('../src/surfaces/EntryInspect.tsx', import.meta.url)), 'utf8')),
     'both views key a field by fieldScope(entry, field)')
  // the renderer itself builds no dotted path any more
  const src = readFileSync(fileURLToPath(new URL('../src/surfaces/entryValue.tsx', import.meta.url)), 'utf8')
  ok(!/\$\{scope\}\.\$\{/.test(src), 'no scope is built by joining names with a dot')
  const insp = readFileSync(fileURLToPath(new URL('../src/surfaces/EntryInspect.tsx', import.meta.url)), 'utf8')
  ok(!/scope=\{`entry:\$\{id\}:\$\{/.test(insp), 'the inspector builds field scopes only through fieldScope')
}

console.log(`entry value: ${checks} checks ok`)
