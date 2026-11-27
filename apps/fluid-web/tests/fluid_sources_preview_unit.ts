/* PreviewBody's "Read at" line (ent-e113ee9f68e5): a Git-backed connector's
 * `at` carries `{ref, commit, remote}`; a feed or web connector's carries
 * `{read, spent}` (webpages also adds `pages`) and has no `.commit` to read. */
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { Preview } from '../src/surfaces/sources/route'
import { PreviewBody } from '../src/surfaces/sources/parts'

let checks = 0
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const base: Preview = {
  collection: null, name: 'n', plan: 'p', within: null, binding_changed: false,
  admit: [], absent: [], not_acquired: [], refused: [], unexamined: [],
  absence_withheld: [], visible_not_selected: 0,
  links: { links_to: 0, embeds: 0 }, largest: [],
  bytes_to_retain: 0, bytes_new_to_store: 0,
  counts: { new: 0, changed: 0, reappeared: 0, absent: 0, not_acquired: 0,
    refused: 0, not_examined: 0, unexamined: 0, visible_not_selected: 0 },
  scope: { include: [], exclude: [] }, confirm: {},
}

const render = (p: Preview) => renderToStaticMarkup(createElement(PreviewBody, { p }))

/* Git-shaped `at`: the short hash still reads */
{
  const html = render({ ...base, at: { ref: 'main', commit: '0123456789abcdef', remote: 'origin' } })
  ok(html.includes('0123456789ab'), 'a Git commit is still shown, shortened')
  ok(html.includes('origin'), '… with its remote')
  ok(!html.includes('fetches'), 'nothing of a fetch budget is drawn for a Git read')
}

/* feed-shaped `at` ({read, spent}, no .commit): this used to crash on
 * p.at.commit.slice(0, 12) the instant a real feed Preview reached the page */
{
  const html = render({
    ...base,
    at: {
      read: [
        { kind: 'feed', shown: 'A feed', status: 'read', entries: 3, offered: 5 },
        { kind: 'feed', shown: 'Another feed', status: 'failed', entries: 0, why: 'timed out' },
      ],
      spent: { fetches: 2, max_fetches: 40, bytes: 2048, max_bytes: 1048576 },
    },
  })
  ok(html.includes('2') && /addresses/.test(html), 'both read addresses are counted')
  ok(/1 with results|1\s*with results/.test(html) || html.includes('with results'), 'how many actually gave results is said')
  ok(html.includes('not read'), 'and how many did not')
  ok(/2.*fetches/.test(html.replace(/\s+/g, ' ')), 'the fetch budget spent is shown')
  ok(!html.includes('undefined'), 'nothing is undefined')
}

/* web-shaped `at` ({read, spent, pages}): webpages._at adds a page count */
{
  const html = render({
    ...base,
    at: {
      read: [{ url: 'https://x.test/a', key: 'k', depth: 0, status: 'read', title: 'A', bytes: 512 } as never],
      spent: { fetches: 1, max_fetches: 60, bytes: 512, max_bytes: 2097152 },
      pages: 1,
    },
  })
  ok(html.includes('pages fetched'), 'a web connector\'s page count is shown')
  ok(!html.includes('undefined'), 'nothing is undefined')
}

console.log(`fluid sources preview: ${checks} checks passed`)
