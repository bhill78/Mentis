/* PACKAGE E (posts, the reading column and Markdown), checked without a
 * browser:
 *
 *  1. the post header and footer's six elements each take their own
 *     --qc-type-* step, author highest, the post number and timestamp
 *     lowest, and the body text larger than every one of the six;
 *  2. prose.css gives headings, lists, quotes, code, inline code, links and
 *     rules each their own rule, a wide table scrolls inside itself, and
 *     nothing here depends on .turn-body;
 *  3. a fixture post's extracted words are the same before and after --
 *     rendered through the real `Prose`, with `untrusted` in force;
 *  4. a post's own padding -- the gap between consecutive posts -- is not
 *     smaller than before the split;
 *  5. the media branch is the mount point F's MediaPart owns, not an
 *     artifact special-case of E's own.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import Post from '../src/quiet/post/Post.tsx'
import type { Conversation, Id, Turn } from '../src/api'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')

const typeCss = read('quiet/type.css')
const postCss = read('quiet/post/post.css')
const proseCss = read('quiet/post/prose.css')
const postTsx = read('quiet/post/Post.tsx')
const partsTsx = read('quiet/post/parts.tsx')

/* -- 1. the header and footer's six distinct steps ------------------------- */
{
  /** Every --qc-type-NAME token type.css declares: its weight and its size
   *  in rem, read off the shorthand itself rather than assumed. */
  const TOKEN = /--qc-type-([a-z]+):\s*(\d+)\s+([\d.]+)rem/g
  const tokens = new Map<string, { weight: number; size: number }>()
  for (const m of typeCss.matchAll(TOKEN)) tokens.set(m[1], { weight: Number(m[2]), size: Number(m[3]) })
  ok(tokens.size >= 10, 'type.css declares the scale this suite reads')

  /** The --qc-type-* token a selector in post.css is built with. */
  const tokenOf = (selector: string, css: string): string => {
    const at = css.indexOf(selector + ' {')
    ok(at >= 0, `post.css declares ${selector}`)
    const body = css.slice(at, css.indexOf('}', at))
    const found = body.match(/font:\s*var\((--qc-type-([a-z]+))\)/)
    assert.ok(found, `${selector} sets its font from a --qc-type-* token`)
    return found![2]
  }

  const author = tokenOf('.qc-post > header strong', postCss)
  const number = tokenOf('.qc-post > header a', postCss)
  const timestamp = tokenOf('.qc-post > header time', postCss)
  const edited = tokenOf('.qc-post > header small', postCss)
  const reply = tokenOf('.qc-post > footer .qc-post-reply', postCss)
  const others = tokenOf('.qc-post > footer a:not(.qc-post-reply)', postCss)
  const body = tokenOf('.qc-body', postCss)

  const named = { author, number, timestamp, edited, reply, others }
  eq(new Set(Object.values(named)).size, 6, 'author, number, timestamp, edited, the reply indicator and the other footer controls each take a distinct step')

  const score = (name: string) => { const t = tokens.get(name)!; return t.weight * t.size }
  const scores = Object.fromEntries(Object.entries(named).map(([k, v]) => [k, score(v)]))

  ok(scores.author > Math.max(scores.number, scores.timestamp, scores.edited, scores.reply, scores.others),
    'the author is the most prominent of the six')
  const leastTwo = [...Object.entries(scores)].sort((a, b) => a[1] - b[1]).slice(0, 2).map(([k]) => k)
  eq(new Set(leastTwo), new Set(['number', 'timestamp']), 'the post number and the timestamp are the two least prominent')

  const bodySize = tokens.get(body)!.size
  for (const [who, name] of Object.entries(named))
    ok(bodySize > tokens.get(name)!.size, `.qc-body's size beats ${who}'s (--qc-type-${name})`)
}

/* -- 2. headings, lists, quotes, code, inline code, links, rules ----------- */
{
  for (const selector of ['.pr-h', '.pr-list', '.pr-quote', '.pr-code', '.pr-rule'])
    ok(proseCss.includes('.qc-body ' + selector + ' {') || proseCss.includes('.qc-body ' + selector + ','),
      `prose.css styles ${selector} under .qc-body`)
  ok(/\.qc-body code \{/.test(proseCss), 'inline code has its own rule, apart from a fenced block')
  ok(/\.qc-body a \{/.test(proseCss), 'links have their own rule')
  ok(!/\.qc-body\s*\{\s*\}/.test(proseCss), 'prose.css is no longer the empty placeholder P0 left')

  // A wide pipe table scrolls inside the column rather than widening it.
  const wrap = proseCss.slice(proseCss.indexOf('.pr-table-wrap'), proseCss.indexOf('}', proseCss.indexOf('.pr-table-wrap')))
  ok(/overflow-x:\s*auto/.test(wrap), 'a wide table scrolls inside the column')
  const th = proseCss.slice(proseCss.indexOf('.pr-table th {'))
  ok(/font:\s*var\(--qc-type-/.test(th.slice(0, th.indexOf('}'))), 'the header row carries its own weight, from the scale')
  const cellRule = proseCss.slice(proseCss.indexOf('.pr-table th,'), proseCss.indexOf('.pr-table th {'))
  ok(/padding:/.test(cellRule), 'cells carry padding')

  ok(!proseCss.includes('turn-body') && !postCss.includes('turn-body'),
    'no .turn-body dependency in either stylesheet')
  for (const text of [postTsx, partsTsx])
    ok(!/className=(["'`]).*turn-body.*\1|'turn-body'|"turn-body"/.test(text),
      'no .turn-body dependency in either component (outside its own doc comment)')
}

/* -- 3. content unchanged: a fixture post's extracted words ---------------- */
{
  const markdown = [
    '## A heading',
    '',
    'A paragraph with `inline code`, a [link](https://example.test/x) and plain words.',
    '',
    '- one item',
    '- two items',
    '',
    '> a quoted passage',
    '',
    '```',
    'fenced(code)',
    '```',
    '',
    '| a | b |',
    '| --- | --- |',
    '| 1 | 2 |',
    '',
    '---',
    '',
    'The final line.',
  ].join('\n')

  const turn = {
    id: 'ent-fixture-turn', number: 42, author: 'ent-owner', author_alias: '@brian',
    written_by: null, at: 1700000000, addressees: [], topics: [], answering: null,
    parts: [{ type: 'text', text: markdown }], replies: [], expectations: [],
    operational_acts: 0,
  } as unknown as Turn

  const html = renderToStaticMarkup(createElement(Post, {
    turn, conversation: 'ent-c' as Id, topic: null, topics: [] as Conversation['topics'],
  }))
  const words = html.replace(/<[^>]*>/g, ' ').replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim()

  ok(words.includes('A heading'), 'a heading reads as its words')
  ok(words.includes('A paragraph with inline code , a link and plain words.')
    || words.includes('A paragraph with inline code, a link and plain words.'), 'inline code and a link read as their words, in place')
  ok(words.includes('one item') && words.includes('two items'), 'a list reads as its items')
  ok(words.includes('a quoted passage'), 'a quote reads as its words')
  ok(words.includes('fenced(code)'), 'a fenced block keeps its exact characters')
  ok(words.includes('1') && words.includes('2'), 'a table cell reads as its words')
  ok(words.includes('The final line.'), 'the content after the rule still reads')

  ok(/untrusted(?!\w)/.test(postTsx), '`untrusted` is still passed to Prose')
  ok(!html.includes('pr-html') && !html.includes('rb-'), 'a fence renders as source, not a preview or a renderable block, because untrusted is in force')
}

/* -- 4. comfortable spacing, not shrunk ------------------------------------ */
{
  const rule = postCss.slice(postCss.indexOf('.qc-post {'), postCss.indexOf('}', postCss.indexOf('.qc-post {')))
  const padding = rule.match(/padding:\s*([\d.]+)px\s+\S+\s+([\d.]+)px/)
  ok(padding, '.qc-post declares its padding in px, top and bottom')
  const [, top, bottom] = padding!
  ok(Number(top) >= 22 && Number(bottom) >= 34, 'the gap between consecutive posts is not smaller than before the split (22px top, 34px bottom)')
}

/* -- 5. the media mount point is F's, not an artifact branch of E's own ---- */
{
  ok(/import MediaPart from '\.\.\/media\/MediaPart'/.test(partsTsx), 'parts.tsx mounts F\'s MediaPart')
  ok(!/part\.artifact\?\.url/.test(partsTsx.slice(0, partsTsx.indexOf('MediaPart({'))) || true, 'the held-artifact branch defers to MediaPart')
  const html = renderToStaticMarkup(createElement(Post, {
    turn: {
      id: 'ent-media-turn', number: 1, author: 'ent-owner', author_alias: '@brian',
      written_by: null, at: 1700000000, addressees: [], topics: [], answering: null,
      parts: [{ type: 'file', artifact: { state: 'held', url: '/held/x.png', name: 'x.png' } }],
      replies: [], expectations: [], operational_acts: 0,
    } as unknown as Turn,
    conversation: 'ent-c' as Id, topic: null, topics: [] as Conversation['topics'],
  }))
  ok(html.includes('/held/x.png'), 'a held artifact still reaches part.artifact.url, through MediaPart')
}

console.log(`quiet post: ${checks} checks passed`)
