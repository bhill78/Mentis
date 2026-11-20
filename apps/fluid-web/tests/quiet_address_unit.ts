/* QUIET CHAT'S ADDRESSES AND ITS ENTRIES IN THE BROWSER'S HISTORY, checked
 * without a browser (src/quiet2/address.ts, centreHistory.ts): what an address
 * asks for, what the page opens on, the address of every place, that reading
 * and writing agree, that nothing written is ever one of Fluid's addresses,
 * and the two history decisions added with them (a conversation is entered
 * anew; something closed goes back only where one Back reaches it). */
import assert from 'node:assert/strict'
import { NO_FILE_SOURCE, NO_SOURCE_NAMED, NO_SUCH_AT, NO_SUCH_FILE, NO_SUCH_RECORD, PLACE_NAMES, addressOf, askedOf, centreFor, isEntryId, placeOf, readAddress, type CentreAt, type Place } from '../src/quiet2/address'
import { isBehind, plan } from '../src/quiet2/centreHistory'
import { entryFor } from '../src/entry'
import { graphIntent, inspectIntent } from '../src/quiet2/space/history'
import type { SpaceBrainKey, SpaceSessionId } from '../src/quiet2/space/contract'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const record = (entry: string): CentreAt => ({ brain: { stack: [{ page: 'record', entry }], origin: { from: 'link' } } })
const source = (col: string): CentreAt => ({ source: { view: { page: 'source', col }, reading: null } })
const NONE = { c: null, at: null }

/* -- what an address asks for ------------------------------------------------ */
{
  eq(readAddress(''), { c: null, at: null, asked: { what: 'conversation' } }, 'nothing named: the conversation')
  eq(readAddress('?c=ent-aaaaaa'), { c: 'ent-aaaaaa', at: null, asked: { what: 'conversation' } }, 'a conversation link, as before')
  eq(readAddress('?c=ent-aaaaaa&at=12'), { c: 'ent-aaaaaa', at: '12', asked: { what: 'conversation' } }, 'read around a post, as before')
  eq(readAddress('?record=ent-bbbbbb').asked, { what: 'record', entry: 'ent-bbbbbb' }, 'what Copy link copies')
  eq(readAddress('?c=ent-aaaaaa&record=ent-bbbbbb'), { c: 'ent-aaaaaa', at: null, asked: { what: 'record', entry: 'ent-bbbbbb' } }, 'a record over its conversation')
  eq(readAddress('?record=nonsense').asked, { what: 'nothing', words: NO_SUCH_RECORD }, 'not an id: said, never opened')
  eq(readAddress('?record=').asked, { what: 'nothing', words: NO_SUCH_RECORD }, 'an empty record is not the conversation in silence')
  eq(readAddress('?sources=all').asked, { what: 'sources' }, 'Manage Sources')
  eq(readAddress('?sources=').asked, { what: 'sources' }, 'and with nothing after it')
  eq(readAddress('?sources=ent-cccccc').asked, { what: 'source', col: 'ent-cccccc', file: null }, 'one source')
  eq(readAddress('?sources=add').asked, { what: 'add-source', connector: null }, 'Add a source')
  eq(readAddress('?sources=add%2Fgit').asked, { what: 'add-source', connector: 'git' }, 'Add a source, a kind chosen')
  eq(readAddress('?sources=ent-cccccc&file=ent-cccccc%2Fo%2Fnotes%2Fa.md').asked,
    { what: 'source', col: 'ent-cccccc', file: { at: 'object', col: 'ent-cccccc', key: 'notes/a.md' } }, 'a held file read in place over its source')
  ok(isEntryId('ent-0e43bf39866b') && !isEntryId('ent-') && !isEntryId('../x'), 'an entry id is an entry id')
}

/* -- WHAT CANNOT BE TAKEN AS WRITTEN IS SAID, AND THE ADDRESS IS PUT RIGHT
      (independent review, 2026-11-20): a name the page cannot read never stays
      in the address while something else is shown ---------------------------- */
{
  /** what the page shows for `search`, the address it then has, and what it says */
  const lands = (search: string, pathname = '/') => {
    const a = readAddress(search)
    return { address: addressOf({ pathname, search, hash: '' }, { c: a.c, at: centreFor(a.asked) }, a, a.asked.what === 'space'), note: a.note ?? (a.asked.what === 'nothing' ? a.asked.words : null) }
  }
  const src = 'ent-cccccc'
  for (const file of ['garbage', '', 'ent-dddddd', 'add', 'ent-dddddd%2Ffiles', 'v', 'ent-dddddd%2Fo%2Fa.md'])
    eq(lands(`?c=ent-aaaaaa&sources=${src}&file=${file}`), { address: `/?c=ent-aaaaaa&sources=${src}`, note: NO_SUCH_FILE }, `a file that is not a file of this source: "${file}"`)
  eq(readAddress(`?sources=${src}&file=garbage`).asked, { what: 'source', col: src, file: null }, 'the source itself is still shown')
  eq(lands('?sources=v%2Fadm-1'), { address: '/?sources=all', note: NO_SOURCE_NAMED }, 'an observation with no source: Manage Sources, said, and the address says Manage Sources')
  eq(lands('?sources=v%2Fadm-1%2Fcompare%2Fadm-2', '/quiet2'), { address: '/quiet2?sources=all', note: NO_SOURCE_NAMED }, 'and two compared, the same')
  eq(lands('?sources='), { address: '/?sources=all', note: null }, 'Manage Sources with nothing after it is written whole')
  eq(lands(`?sources=${src}%2Ffiles`), { address: `/?sources=${src}`, note: null }, 'a tab of a source is its page')
  eq(lands(`?sources=${src}%2Fo%2Fa.md`), { address: `/?sources=${src}&file=${src}%2Fo%2Fa.md`, note: null }, 'a file written the short way is written the long way')
  eq(lands('?c=ent-aaaaaa&record=nonsense'), { address: '/?c=ent-aaaaaa', note: NO_SUCH_RECORD }, 'a record that is not an id')
  eq(lands('?space=yes'), { address: '/?space=1', note: null }, 'the 3D Brain is written one way')
  eq(lands('?c=ent-aaaaaa&record=ent-bbbbbb&sources=all&space=1'), { address: '/?c=ent-aaaaaa&record=ent-bbbbbb', note: null }, 'one place, and only its names')
  /* A FILE THAT BELONGS TO NOTHING SHOWN is said, never dropped in silence (re-review) */
  eq(lands('?c=ent-aaaaaa&file=ent-cccccc%2Fo%2Fa.md'), { address: '/?c=ent-aaaaaa', note: NO_FILE_SOURCE }, 'a file on its own')
  eq(lands('?file='), { address: '/', note: NO_FILE_SOURCE }, 'even an empty one')
  eq(lands('?sources=all&file=x'), { address: '/?sources=all', note: NO_FILE_SOURCE }, 'a file with Manage Sources')
  eq(lands('?sources=add&file=x'), { address: '/?sources=add', note: NO_FILE_SOURCE }, 'a file with Add a source')
  eq(lands('?sources=add%2Fgit&file=x'), { address: '/?sources=add%2Fgit', note: NO_FILE_SOURCE }, 'and with a kind chosen')
  eq(lands('?record=ent-bbbbbb&file=x'), { address: '/?record=ent-bbbbbb', note: NO_FILE_SOURCE }, 'a file with a record')
  eq(lands('?space=1&file=x'), { address: '/?space=1', note: NO_FILE_SOURCE }, 'a file with the 3D Brain')
  eq(lands('?sources=v%2Fadm-1&file=x').note, NO_SOURCE_NAMED, 'one thing is said: the larger')
  eq(lands('?record=nonsense&file=x').note, NO_SUCH_RECORD, 'and here')
  /* `at` that is not a number, over something other than the conversation: the words are true of any surface */
  eq(lands('?c=ent-aaaaaa&at=abc&record=ent-bbbbbb'), { address: '/?c=ent-aaaaaa&record=ent-bbbbbb', note: NO_SUCH_AT }, 'over a record')
  eq(lands(`?c=ent-aaaaaa&at=0&sources=${src}`), { address: `/?c=ent-aaaaaa&sources=${src}`, note: NO_SUCH_AT }, 'over a source')
  ok(!/latest posts|is shown/.test(NO_SUCH_AT), 'it does not say what is shown, because it does not know')
  /* `at` is a post number or it is nothing */
  for (const at of ['abc', '0', '-3', '1.5', '', '12abc', ' 4', '1e3'])
    eq(lands(`?c=ent-aaaaaa&at=${encodeURIComponent(at)}`), { address: '/?c=ent-aaaaaa', note: NO_SUCH_AT }, `not a post number: "${at}"`)
  eq(readAddress('?c=ent-aaaaaa&at=abc').at, null, 'and it is not read as one')
  eq(lands('?c=ent-aaaaaa&at=12'), { address: '/?c=ent-aaaaaa&at=12', note: null }, 'a post number is kept')
  eq(lands('?at=12'), { address: '/', note: null }, 'a post number with no conversation names nothing')
  eq(lands('?c=ent-aaaaaa&at=abc&record=nonsense').note, NO_SUCH_RECORD, 'one thing is said, the larger one')
  eq(lands(`?c=ent-aaaaaa&at=abc&sources=${src}&file=garbage`), { address: `/?c=ent-aaaaaa&sources=${src}`, note: NO_SUCH_FILE }, 'and both are taken off')
  /* the 3D Brain asked for by address is still named while it is opening */
  eq(addressOf({ pathname: '/', search: '?space=1', hash: '' }, { c: 'ent-aaaaaa', at: null }, NONE, true), '/?c=ent-aaaaaa&space=1', 'owed, and the conversation settled on meanwhile')
  eq(addressOf({ pathname: '/', search: '?c=ent-aaaaaa&space=1', hash: '' }, { c: 'ent-aaaaaa', at: record('ent-bbbbbb') }, NONE, true), '/?c=ent-aaaaaa&record=ent-bbbbbb', 'but never over something else the reader opened')
  eq(readAddress('?space=1').asked, { what: 'space' }, 'the 3D Brain')
  eq(readAddress('?space=0').asked, { what: 'conversation' }, 'and not when it says no')
  eq(readAddress('?record=ent-bbbbbb&sources=all&space=1').asked, { what: 'record', entry: 'ent-bbbbbb' }, 'one thing only: the record first')
  eq(readAddress('?sources=all&space=1').asked, { what: 'sources' }, 'then Sources')
  ok(isEntryId('ent-0e43bf39866b') && !isEntryId('ent-') && !isEntryId('../x'), 'an entry id is an entry id')
}

/* -- what the page opens on, and that it is the same thing written back ------- */
{
  eq(centreFor({ what: 'conversation' }), null, 'the conversation holds nothing over it')
  eq(centreFor({ what: 'record', entry: 'ent-bbbbbb' }), record('ent-bbbbbb'), 'a record, as a link opens one')
  eq(centreFor({ what: 'sources' }), { sources: 'all' }, 'the Sources browser is a place')
  eq(centreFor({ what: 'space' }), null, 'a graph is a session: the page opens it once the Brain is known')
  eq(centreFor({ what: 'nothing', words: 'x' }), null, 'what cannot be opened opens nothing')
  for (const search of ['?c=ent-aaaaaa', '?c=ent-aaaaaa&record=ent-bbbbbb', '?c=ent-aaaaaa&sources=all', '?c=ent-aaaaaa&sources=ent-cccccc',
    '?c=ent-aaaaaa&sources=ent-cccccc&file=ent-cccccc%2Fo%2Fnotes%252Fa.md', '?c=ent-aaaaaa&sources=add', '?c=ent-aaaaaa&sources=add%2Fgit']) {
    const a = readAddress(search)
    const back = addressOf({ pathname: '/quiet2', search, hash: '' }, { c: a.c, at: centreFor(a.asked) }, a)
    eq(back, '/quiet2' + search, `read then written is the same address: ${search}`)
    eq(askedOf(centreFor(a.asked)), a.asked, `and asks for the same thing: ${search}`)
  }
}

/* -- the address of a place --------------------------------------------------- */
{
  const at = (search: string, hash = '', pathname = '/') => ({ pathname, search, hash })
  const conv = (c: string | null, over: CentreAt = null): Place => ({ c, at: over })
  eq(addressOf(at(''), conv('ent-aaaaaa'), NONE), '/?c=ent-aaaaaa', 'the conversation settled on is named')
  eq(addressOf(at('', '', '/quiet2'), conv('ent-aaaaaa'), NONE), '/quiet2?c=ent-aaaaaa', 'on whichever path the page is on')
  eq(addressOf(at('?c=ent-aaaaaa'), conv('ent-eeeeee'), { c: 'ent-aaaaaa', at: null }), '/?c=ent-eeeeee', 'another conversation')
  eq(addressOf(at(''), conv(null), NONE), '/', 'no conversation, no query')
  eq(addressOf(at('?c=ent-aaaaaa'), conv('ent-aaaaaa', record('ent-bbbbbb')), NONE), '/?c=ent-aaaaaa&record=ent-bbbbbb', 'a record open')
  eq(addressOf(at('?c=ent-aaaaaa&record=ent-bbbbbb'), conv('ent-aaaaaa'), NONE), '/?c=ent-aaaaaa', 'and left')
  eq(addressOf(at('?c=ent-aaaaaa'), conv('ent-aaaaaa', { sources: 'all' }), NONE), '/?c=ent-aaaaaa&sources=all', 'Manage Sources')
  eq(addressOf(at('?c=ent-aaaaaa'), conv('ent-aaaaaa', source('ent-cccccc')), NONE), '/?c=ent-aaaaaa&sources=ent-cccccc', 'a source')
  /* the top of the stack is what is read */
  const deep: CentreAt = { brain: { stack: [{ page: 'record', entry: 'ent-bbbbbb' }, { page: 'record', entry: 'ent-ffffff' }], origin: { from: 'browser', label: 'All' } } }
  eq(addressOf(at(''), conv('ent-aaaaaa', deep), NONE), '/?c=ent-aaaaaa&record=ent-ffffff', 'a record reached from a record is the one named')
  /* what has no address of its own is addressed as the conversation it is over */
  eq(addressOf(at(''), conv('ent-aaaaaa', { brain: { stack: [{ page: 'import' }], origin: { from: 'link' } } }), NONE), '/?c=ent-aaaaaa', 'Import')
  /* the 3D Brain, and what is read from it */
  const bk = 'brain-1' as SpaceBrainKey, sid = 'session-1' as SpaceSessionId
  eq(addressOf(at(''), conv('ent-aaaaaa', graphIntent(bk, sid)), NONE), '/?c=ent-aaaaaa&space=1', 'the 3D Brain')
  eq(addressOf(at(''), conv('ent-aaaaaa', inspectIntent(bk, sid, { kind: 'record', entry: 'ent-bbbbbb' })), NONE), '/?c=ent-aaaaaa&record=ent-bbbbbb',
    'a record read from the graph is the record: a refresh can show that, and cannot show the graph it was read from')
  eq(addressOf(at(''), conv('ent-aaaaaa', inspectIntent(bk, sid, { kind: 'post', conversation: 'ent-aaaaaa', post: 'ent-999999' })), NONE), '/?c=ent-aaaaaa',
    'a Turn read from the graph is its conversation')
  ok(!addressOf(at(''), conv('ent-aaaaaa', graphIntent(bk, sid)), NONE).includes(sid), 'a session is never in an address')
  /* `at` belongs to the conversation the page was opened on */
  const loaded = { c: 'ent-aaaaaa', at: '12' }
  eq(addressOf(at('?c=ent-aaaaaa&at=12'), conv('ent-aaaaaa', record('ent-bbbbbb')), loaded), '/?c=ent-aaaaaa&at=12&record=ent-bbbbbb', 'kept while that conversation is under what is open')
  eq(addressOf(at('?c=ent-aaaaaa&at=12'), conv('ent-eeeeee'), loaded), '/?c=ent-eeeeee', 'not carried to another conversation')
  eq(addressOf(at('?c=ent-eeeeee'), conv('ent-aaaaaa'), loaded), '/?c=ent-aaaaaa&at=12', 'and there again when the reader returns to it')
  /* a post's anchor stays only while its conversation does; Fluid's `#/` is never written */
  eq(addressOf(at('?c=ent-aaaaaa', '#ent-post'), conv('ent-aaaaaa', record('ent-bbbbbb')), NONE), '/?c=ent-aaaaaa&record=ent-bbbbbb#ent-post', 'the anchor, same conversation')
  eq(addressOf(at('?c=ent-aaaaaa', '#ent-post'), conv('ent-eeeeee'), NONE), '/?c=ent-eeeeee', 'the anchor is not carried to another')
  eq(addressOf(at('', '#/brain/space', '/quiet2'), conv('ent-aaaaaa'), NONE), '/quiet2?c=ent-aaaaaa', 'a `#/` hash is never written')
  /* what the address carried besides is left as it was */
  eq(addressOf(at('?content=long&c=ent-aaaaaa&arr=two'), conv('ent-eeeeee', { sources: 'all' }), NONE), '/?c=ent-eeeeee&sources=all&content=long&arr=two', 'a layout or content override stays')
}

/* -- NOTHING QUIET CHAT WRITES IS EVER ONE OF FLUID'S ADDRESSES (src/entry.ts) -- */
{
  const bk = 'brain-1' as SpaceBrainKey, sid = 'session-1' as SpaceSessionId
  const overs: CentreAt[] = [null, record('ent-bbbbbb'), { sources: 'all' }, source('ent-cccccc'),
    { source: { view: { page: 'source', col: 'ent-cccccc' }, reading: { at: 'object', col: 'ent-cccccc', key: 't/s/w.md' } } },
    { source: { view: { page: 'source', col: 'ent-cccccc' }, reading: { at: 'observation', ref: 'adm-1' } } },
    { source: { view: { page: 'add', connector: null }, reading: null } }, { source: { view: { page: 'add', connector: 'git' }, reading: null } },
    graphIntent(bk, sid)]
  for (const pathname of ['/', '/quiet2']) for (const over of overs) for (const c of [null, 'ent-aaaaaa']) {
    const address = addressOf({ pathname, search: '', hash: '' }, { c, at: over }, NONE)
    const u = new URL(address, 'http://h')
    eq(entryFor({ pathname: u.pathname, search: u.search, hash: u.hash }), { mount: 'quiet2' }, `mounts Quiet Chat: ${address}`)
    eq(u.pathname, pathname, 'on the path the page is on')
    for (const k of new URLSearchParams(u.search).keys()) ok((PLACE_NAMES as readonly string[]).includes(k), `only a place's own names: ${k}`)
    /* and it opens what it names */
    const a = readAddress(u.search)
    eq({ c: a.c, at: centreFor(a.asked) }, { c, at: over && 'space' in over ? null : over }, `reopens the same place: ${address}`)
  }
}

/* -- entries made before places carried their conversation -------------------- */
{
  eq(placeOf(null, 'ent-aaaaaa'), { c: 'ent-aaaaaa', at: null }, 'the conversation, as it was')
  eq(placeOf(record('ent-bbbbbb'), 'ent-aaaaaa'), { c: 'ent-aaaaaa', at: record('ent-bbbbbb') }, 'an older entry is the centre it was, over the conversation shown')
  eq(placeOf({ c: 'ent-eeeeee', at: null }, 'ent-aaaaaa'), { c: 'ent-eeeeee', at: null }, 'a place is itself')
  eq(placeOf({ c: 7, at: null }, 'ent-aaaaaa'), { c: null, at: null }, 'and nothing odd is taken for a conversation')
  eq(placeOf('junk', null), { c: null, at: null }, 'anything else is the conversation')
}

/* -- the history, with the conversation in each entry -------------------------- */
{
  const A: Place = { c: 'a', at: null }, B: Place = { c: 'b', at: null }
  const AR: Place = { c: 'a', at: record('ent-bbbbbb') }
  const AS: Place = { c: 'a', at: { sources: 'all' } }
  /* A CONVERSATION CHOSEN AGAIN IS ENTERED ANEW (the page pushes it; `plan`
     says why it cannot simply search): it IS behind, and going back to that
     would make Back skip everything visited since */
  eq(plan([A, B], 1, A), -1, 'the earlier visit is found behind')
  eq(plan([A, B], 1, B), 0, 'but the conversation already shown is never entered twice')
  /* a record over a conversation leaves for ITS conversation, one step back */
  eq(plan([A, B, A, AR], 3, A), -1, 'the nearest: the one it was opened over')
  eq(plan([B, AR], 1, A), null, 'opened by address over a conversation not behind: pushed')
  /* SOMETHING CLOSED goes back only where one Back reaches where it was opened from */
  ok(isBehind([A, AS], 1, A), 'the Sources browser opened over the conversation: closing is one step back')
  ok(!isBehind([A, AR, AS], 2, A), 'opened over a record: the conversation is not what is behind')
  ok(!isBehind([AS], 0, A), 'opened by address: nothing is behind, and nothing is added to go back to')
  ok(!isBehind([undefined, AS] as (Place | undefined)[], 1, A), 'after a reload what is behind is unknown: never guessed')
  ok(!isBehind([B, AS], 1, A), 'another conversation behind is not this one')
}

console.log(`quiet_address_unit: ${checks} checks ok`)
