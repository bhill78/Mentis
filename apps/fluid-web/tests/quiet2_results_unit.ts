/* THE RESULT CHOOSER (part N-B), checked without a server or a browser.
 *
 * What it must get right, and what the navigation review said breaks it:
 *
 *  1. NO PRIMARY IS GUESSED. Groups and results keep the server's order; no
 *     media type, name, size or return position promotes anything.
 *  2. THE OLDEST RETURN STAYS REACHABLE. With the compact cap filled by
 *     later review rounds, #88's three files are still reached through the
 *     older-groups page, and a thirteen-file return gives up all thirteen.
 *  3. WHAT IS MISSING IS SAID. Purged, corrupt, not-held, deleted and merely
 *     claimed results stay on the list with their reason; omitted groups and
 *     items are counted, so zero never stands for "nobody looked".
 *  4. PROVENANCE STAYS APART. Returned by a run, attached to a post and named
 *     by a claim are three different sentences, and a claim never makes its
 *     claimant the producer or earns an artifact action.
 *  5. OPENING FOLLOWS THE SERVER'S ANSWER. Held bytes open; `state: 'ok'`
 *     with nothing to open does not; an exact Admission reference is required.
 *  6. A POST CARRIES A CHOOSER ONLY WHERE THE RECORD MAPS IT, and the shared
 *     prose link `[words](adm-…)` resolves only at exact twelve hex digits.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ResultChooser from '../src/quiet2/results/ResultChooser'
import ResultsEntry from '../src/quiet2/results/ResultsEntry'
import { postResultsOf, type MoreResults, type PostResults, type ResultsHost } from '../src/quiet2/results/host'
import {
  associationWords, basisWords, checkedWords, entryWords, groupHeading, isRefresh, itemLabel, itemWhat, itemWords,
  openable, pageWords, provenanceWords, rowsOf, sizeWords, sourceWords, stateWords, totalsOf, withMoreItems,
  withOlderGroups,
} from '../src/quiet2/results/words'
import { resultEntriesOf } from '../src/quiet2/latest'
import { mayOpen } from '../src/surfaces/sources/artifactOpener'
import { isAdmissionRef } from '../src/refid'
import { inline } from '../src/prose'
import {
  GEN3, WORK, claimedOnly, corrupt, crowdedFirstPage, deletedPost, emptyPage, group88Rest,
  olderPage, openlessRecord, overview, postRef, purged, REFRESH, returned, turn, twiceObserved, wideRest,
} from './fixtures/magnetResults'
import type { ResultPage, WorkItem } from '../src/work/contract'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const has = (h: string, needle: string, what: string) => { assert.ok(h.includes(needle), `${what} (looking for ${JSON.stringify(needle)})`); checks++ }
const lacks = (h: string, needle: string, what: string) => { assert.ok(!h.includes(needle), `${what} (found ${JSON.stringify(needle)})`); checks++ }

const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (f: string) => readFileSync(src + f, 'utf8').replace(/\r\n/g, '\n')

/* -- 1. one result, in words ---------------------------------------------- */
{
  const T88 = turn(88)
  const file = returned(GEN3[0], 'g3a-yellow-puck.png', T88)
  eq(itemLabel(file), 'g3a-yellow-puck.png', 'a held file is called what the record named it')
  eq(itemLabel({ ...file, artifact: { ...file.artifact!, name: null } }), GEN3[0], 'with no name it is its own exact reference, never a guess')
  eq(itemLabel(postRef('ent-p88compare01', T88, 88)), 'the comparison post #88', 'a reference is called what the inspection says')
  eq(itemWhat(file), 'a held file', 'what it is, in words')
  eq(itemWhat(postRef('ent-p88compare01', T88, 88)), 'a post', 'a post says so')
  eq(itemWhat(openlessRecord('ent-exe91review01', T88)), 'a record', 'a record says so')
  eq([sizeWords(512), sizeWords(182_244), sizeWords(639_715), sizeWords(null)], ['512 B', '178 KB', '625 KB', null], 'bytes in words; unknown stays silent')

  /* THE THREE PROVENANCE FACTS ARE THREE DIFFERENT SENTENCES */
  eq(basisWords({ kind: 'returned-by-run', act: 'a', work: null, turn: null }), 'returned by this run', 'returned by a run')
  eq(basisWords({ kind: 'returned-by-run', act: 'a', work: null, turn: null, observation: 'result-recovered' }), 'recovered as returned by this run', 'a recovery is said as a recovery')
  eq(basisWords({ kind: 'attached-to-turn', act: 'a', work: null, turn: null }), 'attached to this post', 'attached to a post, without claiming its author made it')
  eq(basisWords({ kind: 'authored-result-ref', act: 'a', work: null, turn: null }), 'referenced by this claim', 'a claim is a claim')
  eq(provenanceWords(twiceObserved('adm-61aa11bb22cc', 'gen1-puck.png', turn(61))),
    ['returned by this run', 'recovered as returned by this run'],
    'one result observed twice keeps both facts and stays one result')
  eq(provenanceWords({ ...file, basis: [file.basis[0], { ...file.basis[0], act: 'opr-other' }] }), ['returned by this run'],
    'the same fact twice is said once')

  eq(associationWords(claimedOnly('adm-ff0011223344', turn(92))), 'referenced here; not verified as produced by this work',
    'a claim-only reference says exactly that')
  eq(associationWords({ ...file, association: 'unverified' }), 'the records disagree: this association is not verified', 'disagreement is said')
  eq(associationWords(file), null, 'a verified association needs no caveat')

  eq(sourceWords(T88), 'from #88 in Yellow Quiet Magnet', 'where it actually came from')
  eq(sourceWords(null), null, 'no source, no sentence')
}

/* -- 2. whether it opens, and why not ------------------------------------- */
{
  const T88 = turn(88), T92 = turn(92)
  const held = returned(GEN3[0], 'g3a-yellow-puck.png', T88)
  eq(openable(held), { can: true, why: null }, 'held bytes the work returned can be opened')
  ok(!openable(purged('adm-37bb22cc33dd', 'early-sketch.png', T88)).can, 'purged bytes cannot')
  has(openable(purged('adm-37bb22cc33dd', 'early-sketch.png', T88)).why!, 'purged', 'and the reason says purged')
  ok(!openable(corrupt('adm-80bb22cc33dd', 'gen2-notes.md', T88)).can, 'bytes that do not match cannot be opened')
  has(openable(corrupt('adm-80bb22cc33dd', 'gen2-notes.md', T88)).why!, 'do not match', 'and say so')
  ok(!openable(claimedOnly('adm-ff0011223344', T92)).can, 'an artifact a claim merely named is not actionable')
  has(openable(claimedOnly('adm-ff0011223344', T92)).why!, 'not verified as produced', 'and says why')
  eq(openable(postRef('ent-p88compare01', T88, 88)), { can: true, why: null }, 'an available post with somewhere to open, opens')
  /* `state: 'ok'` IS NOT ENOUGH: an execution activity resolves and has no opener */
  ok(!openable(openlessRecord('ent-exe91review01', T88)).can, 'available and ok but nothing to open: not openable')
  has(openable(openlessRecord('ent-exe91review01', T88)).why!, 'no opener', 'and the inspection\'s own reason is kept')
  ok(!openable(deletedPost('ent-p0goneaway01', T92)).can, 'a deleted post does not open')
  ok(!openable({ ...held, ref: 'adm-667a23eb' }).can, 'an inexact Admission reference earns no file action')
  ok(!openable({ ...held, artifact: undefined }).can, 'no current answer about the bytes: no action')

  eq(stateWords('held'), 'held', 'held is held')
  eq(stateWords('held-but-missing'), 'held by the record, its bytes are gone', 'a missing blob is said plainly')
  eq(stateWords('something-new'), 'its state is "something-new"', 'an unknown state is said as itself, never as available')
  eq([mayOpen(null, 'held'), mayOpen({ open: () => {} }, 'held'), mayOpen({ open: () => {} }, 'purged')], [false, true, false],
    'a host may offer to open only held bytes, and only when it has an opener')

  const words = itemWords(purged('adm-37bb22cc33dd', 'early-sketch.png', T88))
  has(words, 'a held file', 'the line says what it is')
  has(words, 'from #88 in Yellow Quiet Magnet', 'and where it came from')
  has(words, 'returned by this run', 'and what makes it this work\'s')
  has(words, 'cannot be opened here', 'and that it cannot be opened')
}

/* -- 3. the page: bounds counted, nothing quietly dropped ----------------- */
{
  const t = totalsOf(overview)
  eq([t.groups, t.shownGroups, t.omittedGroups], [11, 8, 3], 'the groups the server counted, shown and left over')
  eq(t.shownItems, overview.groups.reduce((n, g) => n + g.items.length, 0), 'every item drawn is counted')
  eq(t.unseenItems, 10, 'one omitted tail plus the nine items of the groups not shown')
  eq(t.items, t.shownItems + 10, 'and the total is structural, before availability')
  has(pageWords(overview), '8 of 11 result groups', 'the summary says how much of the whole is shown')
  has(pageWords(overview), '10 more not listed here', 'and how many results are not listed')
  eq(pageWords(emptyPage), 'No results are recorded for this work yet', 'nothing recorded is said as nothing recorded')
  /* A GROUP NOBODY PAGED TO IS NOT AN EMPTY GROUP */
  const unexamined: ResultPage = { ...emptyPage, total_groups: 4, omitted_groups: 4, omitted_group_items: 12 }
  has(pageWords(unexamined), '12 more not listed here', 'the items of unexamined groups are counted, not zero')
  has(entryWords(overview), '+ results', 'the entry control admits there is more than it shows')
  eq(entryWords(emptyPage), 'No results recorded', 'and says plainly when there is nothing')
  eq(checkedWords(overview), 'Availability checked 2026-11-21T21:40:00Z', 'availability belongs to this read, not to the cursor')
  eq(checkedWords({ ...overview, availability_checked_at: '' }), null, 'unknown stays unsaid')
  eq(groupHeading(overview.groups[2]), '#88 in Yellow Quiet Magnet', 'a group is headed by the post that produced it')
  eq(groupHeading(overview.groups[6]), 'A return with no post of its own', 'an unplaced return is said so; no post is invented')
}

/* -- 4. the rows: the server's order, and nothing promoted ---------------- */
{
  const rows = rowsOf(overview, true)
  const order = rows.filter((r) => r.row === 'group').map((r) => (r as { group: { id: string } }).group.id)
  eq(order, overview.groups.map((g) => g.id), 'groups are drawn in the server\'s order, never re-sorted')
  const in88 = rows.filter((r) => r.row === 'item' && (r as { group: { id: string } }).group.id === 'grp-88')
    .map((r) => (r as { item: { ref: string } }).item.ref)
  eq(in88, [...GEN3, 'ent-p88compare01'], 'items keep recorded order: the biggest file and the HTML win nothing')
  const all = JSON.stringify(rows)
  lacks(all, 'primary', 'no row calls anything the primary')
  lacks(all, 'latest result', 'and nothing is promoted for being newest')

  /* paging rows are offered when the host can read more */
  ok(rows.some((r) => r.row === 'more-items' && r.group.id === 'grp-88'), '#88\'s remaining item is offered')
  const more = rows.find((r) => r.row === 'more-groups')
  ok(more, 'and so are the older groups')
  has((more as { words: string }).words, '3 older groups', 'with their count')
  has((more as { words: string }).words, '9 more results', 'and the results inside them')

  /* WITHOUT A CONTINUATION READ THE BOUND IS STILL STATED */
  const bounded = rowsOf(overview, false)
  ok(!bounded.some((r) => r.row === 'more-items' || r.row === 'more-groups'), 'no paging is offered that the host cannot do')
  const notes = bounded.filter((r) => r.row === 'bounded').map((r) => (r as { words: string }).words)
  ok(notes.some((w) => w.includes('1 more results in this group')), 'the group\'s own remainder is still declared')
  ok(notes.some((w) => w.includes('3 older result groups')), 'and so are the groups not listed')
}

/* -- 5. the oldest return stays reachable (F2) ---------------------------- */
{
  /* the compact page is filled by later review rounds: #88 is not on it */
  ok(!crowdedFirstPage.groups.some((g) => g.id === 'grp-88'), 'the fixture\'s first page really is without #88')
  const withOlder = withOlderGroups(crowdedFirstPage, olderPage)
  const got = withOlder.groups.find((g) => g.id === 'grp-88')
  ok(got, 'the older-groups page reaches #88')
  eq(got!.items.slice(0, 3).map((i) => i.ref), [...GEN3], 'with its three exact files')
  eq(withOlder.groups.map((g) => g.id).slice(0, 8), crowdedFirstPage.groups.map((g) => g.id), 'the newer page keeps its place and order')
  eq(withOlder.next_results_before, olderPage.next_results_before, 'and paging continues from the older read')
  eq(withOlderGroups(withOlder, olderPage).groups.length, withOlder.groups.length, 'the same older page twice adds nothing twice')

  /* a thirteen-file return gives up all thirteen, once each */
  const wide = withMoreItems(olderPage, 'grp-80-wide', wideRest)
  const g = wide.groups.find((x) => x.id === 'grp-80-wide')!
  eq(g.items.length, 13, 'every file of the return is reachable')
  eq(new Set(g.items.map((i) => i.ref)).size, 13, 'each exactly once')
  eq([g.omitted_items, g.next_items_after], [0, null], 'and the group says there is no more')
  eq(withMoreItems(wide, 'grp-80-wide', wideRest).groups.find((x) => x.id === 'grp-80-wide')!.items.length, 13,
    'reading the same continuation twice does not duplicate anything')
  eq(withMoreItems(olderPage, 'grp-88', wideRest).groups.find((x) => x.id === 'grp-88')!.items.length, 4,
    'a page about another group changes nothing here')

  /* the last item of #88 is a purged file: still listed, still explained */
  const rest = withMoreItems(olderPage, 'grp-88', group88Rest).groups.find((x) => x.id === 'grp-88')!
  eq(rest.items.length, 5, '#88\'s fifth result arrives')
  ok(!openable(rest.items[4]).can, 'and it is honestly not openable')
  has(itemWords(rest.items[4]), 'purged', 'with its reason on the row')
}

/* -- 6. a refused continuation is not an empty list ----------------------- */
{
  eq(isRefresh(REFRESH), true, 'the server\'s refresh condition is recognised')
  eq(isRefresh({ status: 409, body: REFRESH }), true, 'however the client wrapped it')
  eq(isRefresh(new Error('ResultsRefreshRequired: cursors moved')), true, 'including as a thrown message')
  eq(isRefresh(new Error('network down')), false, 'an ordinary failure is not a refresh')
  eq(isRefresh(null), false, 'and neither is nothing')
}

/* -- 7. which post carries a chooser (A7) --------------------------------- */
{
  const page = overview
  const mapped: PostResults[] = [
    { work: WORK, title: 'Yellow Quiet Magnet', mapping: 'request', page },
    { work: WORK, title: 'Yellow Quiet Magnet', mapping: 'update', page },
  ]
  const host = { of: (post: string) => (post === 'ent-t20' ? [mapped[0]] : post === 'ent-t92' ? [mapped[1]] : []) }
  eq(postResultsOf(host, { id: 'ent-t20', real: true }).map((r) => r.mapping), ['request'], 'the request post carries the work\'s results')
  eq(postResultsOf(host, { id: 'ent-t92', real: true }).map((r) => r.mapping), ['update'], 'so does a post the record maps as an update')
  eq(postResultsOf(host, { id: 'ent-t90', real: true }), [], 'a carrier\'s ordinary post, which the record does not map, carries none')
  eq(postResultsOf(host, { id: 'ent-t99', real: true }), [], 'and neither does the newest post for being newest')
  eq(postResultsOf(null, { id: 'ent-t20', real: true }), [], 'with no host nothing is drawn at all')
  eq(postResultsOf(host, { id: 'ent-t20', real: false }), [], 'and nothing is drawn on a post that is not in the record')
  eq(postResultsOf({ of: () => [mapped[0], mapped[0]] }, { id: 'ent-t20', real: true }).length, 1, 'the same mapping twice is one chooser')
  eq(postResultsOf({ of: () => mapped }, { id: 'ent-t20', real: true }).length, 2, 'a post that is both request and update says both')
}

/* -- 8. the Latest list's own entries ------------------------------------- */
{
  const item = (expectation: string, title: string, result_summary?: ResultPage) =>
    ({ expectation, title, result_summary } as unknown as WorkItem)
  const items = [item('opr-a', 'Magnet', overview), item('opr-b', 'No read', undefined), item('opr-c', 'Empty', emptyPage), item('opr-a', 'Magnet again', overview)]
  const entries = resultEntriesOf(items)
  eq(entries.map((e) => e.work), ['opr-a', 'opr-c'], 'only the works whose read carries results, each once, in the read\'s order')
  eq(entries[0].title, 'Magnet', 'with the work\'s own title')
  eq(resultEntriesOf(null), [], 'no read, no entries')
  /* a work whose read did not ask for results is left out, not drawn as having none */
  ok(!entries.some((e) => e.work === 'opr-b'), 'a work with no result read is not claimed to have no results')
}

/* -- 9. what is actually drawn -------------------------------------------- */
const opened: unknown[] = []
const sources: unknown[] = []
const more: MoreResults = { groupsBefore: async () => olderPage, itemsAfter: async () => group88Rest }
const host: ResultsHost = { open: (c) => opened.push(c), openSource: (c) => sources.push(c), more }

{
  const html = renderToStaticMarkup(createElement(ResultChooser, {
    work: WORK, title: 'Yellow Quiet Magnet', page: overview, host, autoFocus: false,
  }))
  for (const ref of GEN3) void ref
  has(html, 'g3a-yellow-puck.png', '#88\'s first file is on the list')
  has(html, 'g3b-yellow-puck.png', 'and its second')
  has(html, 'gen3-comparison.html', 'and the comparison')
  has(html, '#88 in Yellow Quiet Magnet', 'under the post that produced them')
  has(html, 'A return with no post of its own', 'an unplaced return is headed honestly')
  has(html, 'early-sketch.png', 'the purged file keeps its place on the list')
  has(html, 'cannot be opened here: its bytes were purged', 'with its reason in the row\'s own words, not only a tooltip')
  has(html, 'referenced here; not verified as produced by this work', 'a claim-only reference is labelled as one')
  has(html, 'this post was deleted', 'and a deleted post says so')
  has(html, 'All results: 3 older groups', 'the older groups are offered')
  has(html, 'Show the other 1 results here', 'and so is the remainder of #88')
  has(html, 'Availability checked', 'the read says when it checked')
  eq((html.match(/role="menu"/g) ?? []).length, 1, 'one menu')
  const items = (html.match(/role="menuitem"/g) ?? []).length
  const rows = rowsOf(overview, true)
  const expected = rows.filter((r) => (r.row === 'group' && r.source) || r.row === 'item' || r.row === 'more-items' || r.row === 'more-groups').length
  eq(items, expected, 'every row a reader can act on is a menu item: results, source posts and the paging offers')
  has(html, 'aria-disabled="true"', 'a result that cannot be opened is marked so for a screen reader')
  /* the source post is its own act, apart from the items */
  has(html, 'the post these results came from', 'a group offers its source post separately from its results')
}

{
  /* NO HOST: still a full, honest list; nothing pretends to open */
  const html = renderToStaticMarkup(createElement(ResultChooser, {
    work: WORK, title: null, page: overview, host: null, autoFocus: false,
  }))
  has(html, 'Results of this work', 'it still says whose results these are')
  has(html, 'opening them needs the conversation view', 'and that it cannot open them here')
  has(html, 'g3a-yellow-puck.png', 'the results are all still listed')
  has(html, '3 older result groups are not listed here', 'and the bound is still declared')
  lacks(html, 'All results:', 'no paging is offered that it cannot perform')
  eq((html.match(/aria-disabled="true"/g) ?? []).length, rowsOf(overview, false).filter((r) => r.row === 'item').length,
    'with no host every result is marked as not openable here')
}

{
  const entry = (mapping: PostResults['mapping'], page: ResultPage) => renderToStaticMarkup(createElement(ResultsEntry, {
    results: { work: WORK, title: 'Yellow Quiet Magnet', mapping, page }, host,
  }))
  const update = entry('update', overview)
  has(update, 'the record maps this post as an update of the work', 'the control says why this post has results')
  has(update, 'aria-expanded="false"', 'and starts closed')
  has(update, 'results', 'with a count')
  has(entry('request', overview), 'this post asked for the work', 'a request post says that instead')
  has(entry('work', overview), 'the results recorded under this work', 'and a Latest row claims no post mapping at all')
  has(entry('request', emptyPage), 'disabled', 'nothing recorded: there is nothing to open')
  has(entry('request', emptyPage), 'No results recorded', 'and it says so')
}

/* -- 10. the shared prose link (NB1, L1) ---------------------------------- */
{
  eq([isAdmissionRef('adm-667a23eb07a8'), isAdmissionRef('adm-667a23eb'), isAdmissionRef('adm-667A23EB07A8'),
    isAdmissionRef('adm-667a23eb07a8.png'), isAdmissionRef('C:/x/adm-667a23eb07a8')],
    [true, false, false, false, false], 'an Admission is named exactly or not at all')

  const drawn = (md: string) => renderToStaticMarkup(createElement('div', null, ...inline(md)))
  const exact = drawn('See [the Gen 3 comparison](adm-667a23eb07a8) for the shapes.')
  has(exact, 'the Gen 3 comparison', 'an exact Admission link keeps the author\'s words')
  lacks(exact, 'pr-link-refused', 'and is a reference now, not refused text')
  has(exact, 'ref-wrap', 'drawn as the chip the record explains')

  const malformed = drawn('See [the shapes](adm-667a23eb) please.')
  has(malformed, 'pr-link-refused', 'a malformed token stays what the author wrote')
  has(malformed, 'adm-667a23eb', 'with its destination visible')

  const path = drawn('See [the shapes](C:/Work/out/adm-667a23eb07a8.png).')
  has(path, 'pr-link-refused', 'a local path is not a reference')
  lacks(path, 'ref-wrap', 'and gets no artifact action')

  const image = drawn('![a yellow puck](adm-a43714dc1b5b)')
  has(image, 'ref-wrap', 'an image reference is unchanged')

  const web = drawn('See [the page](https://example.com/x?a=1).')
  has(web, 'href="https://example.com/x?a=1"', 'an ordinary link still goes where it says')
  has(web, 'rel="noreferrer noopener"', 'with safeHref\'s own rules untouched')
  has(drawn('See [nowhere](javascript:alert(1)).'), 'pr-link-refused', 'and an unsafe scheme is still refused')
}

/* -- 11. where it sits: results before the routine activity --------------- */
{
  const post = read('quiet2/Post.tsx')
  const attachments = post.indexOf('<Attachments post={post} files={post.attachments} />')
  const results = post.indexOf('<PostResults post={post} />')
  const status = post.indexOf('<StatusLine s={status} />')
  ok(attachments > 0 && results > attachments, 'the chooser is drawn after the post\'s own attachments')
  ok(status > results, 'and before the status line and toolbar under it')
  has(post, 'postResultsOf(page.results, post)', 'and only from the host\'s exact mapping')

  const latest = read('quiet2/JumpToLatest.tsx')
  const section = latest.indexOf('q2-jump-results')
  const chains = latest.indexOf('Jump to latest <span>where work last ended')
  ok(section > 0 && chains > section, 'in Latest, results come before the chronological rows')
  has(latest, 'results?.entries.length', 'and only when the host lent them')
  /* THE CHRONOLOGICAL LIST ITSELF IS UNTOUCHED */
  has(latest, 'chainsOf(recent, Date.now() / 1000)', 'the chains are still read exactly as before')
  has(latest, 'the last {CHAIN_WINDOW / 60} minutes', 'and still described as before')
}

console.log(`quiet2 results: ${checks} checks`)
