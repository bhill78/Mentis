/* KEEP AS SECTION (workspace/feedSection.ts), held in Node against the
   arrangement itself (no server, no browser):

     * a view kept as a section brings it in as its feed and places nothing:
       `{ follow: false, show: 'objects', items: [], present: 'list',
       feed: { source } }`, under the view's name;
     * it goes beside the conversation's primary on the page named -- split
       off the primary's leaf, or at the tree's edge nearest the column when
       the primary is the column -- and no other page changes;
     * the same view kept twice is one section: the second time nothing is
       added and the section already there is named;
     * it is one pure step from the arrangement before (what Undo restores).

   Run by tests/run.mjs. */
import assert from 'node:assert/strict'
import { feedSectionOn, feedSlot, withFeedSection } from '../src/fluid/workspace/feedSection'
import type { Arr } from '../src/fluid/workspace/place'
import { findZone, followSlot, zones, type Node, type Split, type Zone } from '../src/fluid/workspace/tree'
import { conversationZone } from '../src/fluid/focus/model'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const same = (a: unknown, b: unknown, what: string) => { assert.equal(a, b, what); checks++ }
const ok = (v: unknown, what: string) => { assert.ok(v, what); checks++ }
const z = (id: string): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot: followSlot() })

/* This post: the conversation is in the column (the usual place), one
   following zone in the tree. Page "p1": the conversation docked as a leaf
   beside a zone, and it is the page's primary. */
const p1Tree: Node = { type: 'split', dir: 'row', sizes: [0.5, 0.5], kids: [z('a'), conversationZone()] }
const start: Arr = {
  tree: z('post'),
  pages: [{ id: 'p1', title: 'One', tree: p1Tree, focus: { primary: 'conv', column: z('col') } }],
}
const snapshot = structuredClone(start)

/* -- the slot ----------------------------------------------------------------- */

eq(feedSlot('actions'), { follow: false, show: 'objects', items: [], present: 'list', feed: { source: 'actions' } },
  'a feed section follows nothing, places nothing, and brings in its feed')

/* -- on This post: beside the column, at the tree's nearest edge --------------- */

const one = withFeedSection(start, 'actions', 'this-post', 'Actions')
same(one.added, true, 'kept once, a section is added')
const t1 = one.arr.tree as Split
same(t1.type, 'split', 'the page tree is split')
same(t1.dir, 'row', 'side by side')
same((t1.kids[0] as Zone).id, one.zone, 'the new section is at the edge nearest the column (the primary)')
eq(t1.kids[1], start.tree, 'what was there keeps its tree')
ok(t1.sizes[0] < t1.sizes[1], 'and most of the room')
const made = findZone(one.arr.tree, one.zone)!
eq(made.slot, feedSlot('actions'), 'the section brings in Actions')
same(made.name, 'Actions', "named for the view")
same(one.arr.pages, start.pages, 'no other page changes')
eq(start, snapshot, 'the arrangement before is untouched (Undo restores it)')

/* -- idempotent ---------------------------------------------------------------- */

const two = withFeedSection(one.arr, 'actions', 'this-post', 'Actions')
same(two.added, false, 'kept again, nothing is added')
same(two.arr, one.arr, 'the arrangement is the same one: no step is made of nothing')
same(two.zone, one.zone, 'and the section already there is named, to be lit')
same(feedSectionOn(one.arr, 'this-post', { source: 'actions' }), one.zone, 'found by its feed')
same(feedSectionOn(one.arr, 'this-post', { source: 'actions', options: { owed: 'me' } }), undefined,
  'a feed with other options is another feed')
same(feedSectionOn(one.arr, 'p1', { source: 'actions' }), undefined, 'and only on its own page')

const media = withFeedSection(one.arr, 'media', 'this-post', 'Media')
same(media.added, true, 'another view is another section')
same(zones(media.arr.tree).length, 3, 'beside the first')

/* -- on another page: beside the primary leaf ---------------------------------- */

const p = withFeedSection(start, 'brief', 'p1', 'Brief')
same(p.added, true, 'kept on page One')
same(p.arr.tree, start.tree, "This post's tree is untouched")
const pt = p.arr.pages[0].tree as Split
eq(zones(pt).map((x) => x.id), ['a', 'conv', p.zone], 'split off the conversation, its primary, on its far side')
ok(pt.sizes[2] < pt.sizes[1], 'the primary keeps the most of its leaf')
eq(p.arr.pages[0].focus, start.pages[0].focus, "the page's focus is untouched")
same(withFeedSection(p.arr, 'brief', 'p1').added, false, 'kept again on that page, nothing is added')

/* A section in a float or the column counts as there. */
const floated: Arr = { ...start, focus: { floats: [{ id: 'f', zone: { ...z('fz'), slot: feedSlot('guidance') }, x: 0, y: 0, w: 300, h: 200 }] } }
same(withFeedSection(floated, 'guidance', 'this-post').zone, 'fz', 'a floating section bringing it in is the one lit')

/* A page that is gone: This post, as everything that names a page does. */
same(withFeedSection(start, 'brief', 'gone').arr.pages, start.pages, 'a closed page falls back to This post')

console.log(`fluid feed section: ${checks} checks passed`)
