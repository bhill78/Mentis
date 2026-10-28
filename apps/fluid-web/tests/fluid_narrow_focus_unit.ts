import assert from 'node:assert/strict'
import { makePrimary, floatObject, floatOut, swapBack, primaryOf } from '../src/fluid/focus/model'
import { convPlace, narrowFloats, previousPrimary, seenAt, standIn } from '../src/fluid/focus/narrowView'
import type { Arr } from '../src/fluid/workspace/place'
import { onPage, pageView } from '../src/fluid/focus/page'
import { keepSlot, type Node, type Zone } from '../src/fluid/workspace/tree'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const z = (id: string, name = id): Zone => ({ type: 'zone', id, show: 'objects', name, slot: keepSlot() })
const arr = (tree: Node, focus?: Arr['focus']): Arr => ({ tree, pages: [], ...(focus ? { focus } : {}) })
const frozen = (a: Arr) => JSON.stringify(a)

/* Nothing swapped: the column is the conversation's, no stand-in, no stub. */
const plain = arr({ type: 'split', dir: 'row', sizes: [.5, .5], kids: [z('stage', 'Stage'), z('notes')] })
eq(convPlace(plain), null, 'the conversation has no other place')
eq(standIn(plain), null, 'nothing stands in')
eq(seenAt(plain, 'conv'), { in: 'column' }, 'the conversation is seen in the column')
eq(seenAt(plain, 'stage'), { in: 'leaf', zone: 'stage' }, 'a section is seen where it is')
eq(seenAt(plain, 'nope'), null, 'unknown content is nowhere')

/* Stage made primary: the conversation went to Stage's leaf, Stage to the
   column. Narrow, the column shows the conversation and the leaf shows Stage. */
const swapped = makePrimary(plain, 'stage')
const before = frozen(swapped)
eq(swapped.focus?.column?.id, 'stage', 'the desktop column holds Stage')
eq(convPlace(swapped), { place: 'leaf', zone: 'conv' }, 'the conversation sits in a leaf')
eq(standIn(swapped)?.id, 'stage', 'that leaf shows Stage when narrow')
eq(seenAt(swapped, 'conv'), { in: 'column' }, 'narrow, the conversation is in the column')
eq(seenAt(swapped, 'stage'), { in: 'leaf', zone: 'conv' }, 'narrow, Stage is seen in the conversation\'s leaf')
eq(seenAt(swapped, 'notes'), { in: 'leaf', zone: 'notes' }, 'other sections stay where they are')
eq(previousPrimary(swapped), 'conv', 'Esc would bring back the conversation')
eq(previousPrimary(swapBack(swapped)), null, 'after swapping back there is nothing before')
eq(previousPrimary(plain), null, 'nothing before an untouched arrangement')
eq(frozen(swapped), before, 'reading the narrow view never changes the arrangement')

/* A float made primary: the conversation floats where the object was. */
const floated = floatObject(plain, 'live:p:k', 'Survey', { x: 10, y: 20, w: 300, h: 200 }, undefined, 'Tidewater · #12')
const objId = floated.focus!.floats![0].zone.id
const floatPrimary = makePrimary(floated, objId)
const convFloat = floatPrimary.focus!.floats![0]
eq(convFloat.zone.show, 'conversation', 'the conversation floats')
eq(convPlace(floatPrimary), { place: 'float', float: convFloat.id }, 'its place is the float')
eq(standIn(floatPrimary)?.id, objId, 'the float shows the object when narrow')
eq(seenAt(floatPrimary, objId), { in: 'float', float: convFloat.id }, 'the object is seen in that float\'s panel')
eq(primaryOf(floatPrimary), objId, 'primary as the desktop has it')

/* Floats listed front first; travelling object floats among them; rectangles kept. */
const two = floatOut(floated, 'notes', { x: 5, y: 6, w: 280, h: 190 })
const listed = narrowFloats(two)
eq(listed.map((f) => f.zone.id), ['notes', objId], 'the front float first')
eq(listed.map((f) => [f.x, f.y, f.w, f.h]), [[5, 6, 280, 190], [10, 20, 300, 200]], 'rectangles are untouched')
eq(two.focus!.floats!.map((f) => f.zone.id), [objId, 'notes'], 'listing does not reorder the arrangement')
eq(seenAt(two, objId), { in: 'float', float: two.focus!.floats![0].id }, 'an object float is seen in its panel')
eq(narrowFloats(plain), [], 'no floats, no list')

/* A column holding something while the conversation is nowhere else: no stand-in. */
const lost = arr(z('a'), { column: z('x') })
eq(standIn(lost), null, 'nothing stands in when the conversation has no other place')
eq(seenAt(lost, 'x'), { in: 'column' }, 'and the column is where it would be')

/* On a page of the place's own (focus/page.ts), the narrow screen reads that
   page's view: where its content is seen, its stand-in, its Esc and floats. */
const withPage: Arr = { ...plain, pages: [{ id: 'p2', title: 'Two', tree: { type: 'split', dir: 'row', sizes: [.5, .5], kids: [z('plan', 'Plan'), z('log')] } }] }
const pageSwapped = onPage((v) => makePrimary(v, 'plan'), 'p2')(withPage)
const pv = pageView(pageSwapped, 'p2')
eq(seenAt(pv, 'plan'), { in: 'leaf', zone: 'conv' }, "page 2: Plan is seen in the conversation's leaf")
eq(seenAt(pv, 'log'), { in: 'leaf', zone: 'log' }, 'page 2: its other section where it is')
eq(seenAt(pv, 'conv'), { in: 'column' }, 'page 2: the conversation is in the column')
eq(seenAt(pageSwapped, 'plan'), null, "This post does not see page 2's content")
eq(standIn(pv)?.id, 'plan', "page 2: the conversation's leaf shows Plan when narrow")
eq(standIn(pageSwapped), null, 'This post has nothing standing in')
eq(previousPrimary(pv), 'conv', 'page 2: Esc would bring back the conversation')
eq(previousPrimary(pageSwapped), null, "This post has no Esc of page 2's")
const pageFloat = onPage((v) => floatOut(v, 'log', { x: 1, y: 2, w: 300, h: 200 }), 'p2')(withPage)
eq(narrowFloats(pageView(pageFloat, 'p2')).map((f) => f.zone.id), ['log'], 'page 2 lists its own floats')
eq(narrowFloats(pageFloat), [], 'This post lists none of them')
eq(seenAt(pageView(pageFloat, 'p2'), 'log'), { in: 'float', float: pageFloat.pages[0].focus!.floats![0].id }, 'page 2: a float is seen in its panel')

console.log(`fluid_narrow_focus_unit: ${checks} checks ok`)
