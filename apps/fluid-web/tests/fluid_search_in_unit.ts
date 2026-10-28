/* Focus Search (src/fluid/search-in/), held in Node against the code itself
   (no server, no browser, no build):

     * compile/findIn (match.ts): a query is literal by default -- every
       regex metacharacter means itself; a pattern only when asked, and one
       that does not compile is an answer, never a throw; case is the
       reader's choice; a zero-length match is skipped, and no text yields
       more than 2000 matches;
     * planBlocks (highlight.ts): the current match's block and its
       neighbours are near (kept at full strength); every other match block
       is a hit.

   Run by tests/run.mjs. */
import assert from 'node:assert/strict'
import { compile, findIn, MAX_MATCHES, type Matcher } from '../src/fluid/search-in/match'
import { planBlocks } from '../src/fluid/search-in/highlight'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (v: unknown, what: string) => { assert.ok(v, what); checks++ }
const at = (text: string, m: Matcher) => findIn(text, m).map(({ start, end }) => text.slice(start, end))
const asMatcher = (r: Matcher | { error: string }): Matcher => {
  assert.ok(!('error' in r), `expected a matcher, got the error ${(r as { error: string }).error}`)
  return r as Matcher
}

/* -- literal by default: metacharacters mean themselves ---------------------- */

const LIT = '.*+?()[]'
{
  const m = asMatcher(compile(LIT))
  eq(at(`before ${LIT} after`, m), [LIT], 'a literal query finds itself, metacharacters and all')
  eq(at('.*+?()[]X .*+?()[]', m), [LIT, LIT], 'every occurrence is found, in order')
  eq(at('ax+?()[]', m), [], 'no character of it acts as a pattern')
}
{
  const m = asMatcher(compile('v1.2 (draft)'))
  eq(at('see v1.2 (draft) now', m), ['v1.2 (draft)'], 'dots and parentheses are what was typed')
  eq(at('see v1x2 (draft) now', m), [], 'a dot is not "any character"')
}
{
  const m = asMatcher(compile('a+b'))
  eq(at('aaab a+b', m), ['a+b'], '+ is escaped, so only the literal is found')
}

/* -- regex only when asked ---------------------------------------------------- */

{
  const m = asMatcher(compile('a.c', { regex: true }))
  eq(at('abc a.c axc', m), ['abc', 'a.c', 'axc'], 'a real pattern matches as a pattern')
  const lit = asMatcher(compile('a.c'))
  eq(at('abc a.c axc', lit), ['a.c'], 'the same characters are literal without the option')
}
{
  const m = asMatcher(compile('\\b\\d{4}\\b', { regex: true }))
  eq(at('in 2025, not 25 or 20255', m), ['2025'], 'classes and boundaries work')
}

/* -- an invalid regex is an answer, never a throw ------------------------------ */

{
  const r = compile('(', { regex: true })
  ok('error' in r, 'an unclosed group is an error answer')
  ok(typeof (r as { error: string }).error === 'string' && (r as { error: string }).error.length > 0, 'and it says why')
}
{
  const r = compile('[', { regex: true })
  ok('error' in r, 'an unclosed class is an error answer')
}
{
  const m = asMatcher(compile('('))
  eq(at('a ( b', m), ['('], 'the same characters are fine as a literal')
}

/* -- case is the reader's choice ----------------------------------------------- */

{
  const m = asMatcher(compile('Tide'))
  eq(at('tide TIDE Tide', m), ['tide', 'TIDE', 'Tide'], 'case is ignored unless asked')
  const exact = asMatcher(compile('Tide', { caseSensitive: true }))
  eq(at('tide TIDE Tide', exact), ['Tide'], 'and exact when asked')
}
{
  const m = asMatcher(compile('t.de', { regex: true, caseSensitive: true }))
  eq(at('TIDE tide', m), ['tide'], 'the option reaches patterns too')
}

/* -- offsets, zero-length matches, reuse, the cap ------------------------------- */

{
  const m = asMatcher(compile('bb'))
  eq(findIn('abb bbc', m), [{ start: 1, end: 3 }, { start: 4, end: 6 }], 'offsets are into the text given')
}
{
  const m = asMatcher(compile('a*', { regex: true }))
  eq(findIn('bbb', m), [], 'a pattern that matches empty is skipped, not spun on')
  eq(findIn('baa', m), [{ start: 1, end: 3 }], 'and its real matches still found (greedy, one run)')
}
{
  const m = asMatcher(compile('a'))
  eq(findIn('a a', m).length, 2, 'one matcher runs over a text')
  eq(findIn('a a a', m).length, 3, 'and again over another (its cursor rewound)')
}
{
  const m = asMatcher(compile('a'))
  eq(findIn('a'.repeat(MAX_MATCHES + 1000), m).length, MAX_MATCHES, `no text yields more than ${MAX_MATCHES}`)
}

/* -- planBlocks: near the current match, hit otherwise -------------------------- */

{
  const blocks = ['A', 'B', 'C', 'D']
  const sibs = (b: string) => {
    const i = blocks.indexOf(b)
    return [i > 0 ? blocks[i - 1] : null, i < blocks.length - 1 ? blocks[i + 1] : null]
  }
  eq(planBlocks(blocks, 'B', sibs), { near: ['B', 'A', 'C'], hit: ['D'] },
    "the current block and its two neighbours are near; the rest are hits")
  eq(planBlocks(blocks, null, sibs), { near: [], hit: blocks }, 'no current: every match block is a hit')
  eq(planBlocks(['A', 'B'], 'A', sibs), { near: ['A', 'B'], hit: [] }, 'a neighbour that is itself a match block is near, not both')
  eq(planBlocks(['A'], 'not-there', sibs), { near: [], hit: ['A'] }, 'a current the hits do not hold changes nothing')
}

console.log(`fluid search-in: ${checks} checks passed`)
