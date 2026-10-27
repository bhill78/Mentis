/* ONE INSPECTOR (render/inspect.ts): the same keys for every object, and
   the arrows stepping only through the opened thing's own family in its
   post. Pure: no DOM, no store. */
import assert from 'node:assert/strict'
import { inspectKey, inspectScope, stepIn, type InspectAt } from '../src/fluid/render/inspect'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const at = (over: Partial<InspectAt> = {}): InspectAt => ({ full: false, picture: false, typing: false, inObject: false, ...over })

/* -- keys ------------------------------------------------------------------ */

/* Esc: full screen first, then return -- for a picture and a table alike. */
for (const picture of [true, false]) {
  eq(inspectKey({ key: 'Escape' }, at({ picture })), 'close', `Esc returns (picture=${picture})`)
  eq(inspectKey({ key: 'Escape' }, at({ picture, full: true })), 'leave-full', `Esc leaves full screen first (picture=${picture})`)
  eq(inspectKey({ key: 'f' }, at({ picture })), 'full', `F goes full screen (picture=${picture})`)
  eq(inspectKey({ key: 'f' }, at({ picture, full: true })), 'leave-full', `F leaves full screen (picture=${picture})`)
  eq(inspectKey({ key: 'ArrowRight' }, at({ picture })), 'next', `→ steps on (picture=${picture})`)
  eq(inspectKey({ key: 'ArrowLeft' }, at({ picture })), 'prev', `← steps back (picture=${picture})`)
  eq(inspectKey({ key: 'ArrowLeft', altKey: true }, at({ picture })), 'close', `Alt+← returns, as Back does (picture=${picture})`)
}

/* Zoom is a picture's only. */
eq(inspectKey({ key: '+' }, at({ picture: true })), 'zoom-in', '+ zooms a picture in')
eq(inspectKey({ key: '=' }, at({ picture: true })), 'zoom-in', '= zooms a picture in')
eq(inspectKey({ key: '-' }, at({ picture: true })), 'zoom-out', '- zooms a picture out')
eq(inspectKey({ key: '0' }, at({ picture: true })), 'fit', '0 fits a picture')
for (const key of ['+', '-', '0']) eq(inspectKey({ key }, at()), null, `${key} is not the inspector's on a table`)

/* A field keeps every key typed into it, Esc too. */
for (const key of ['Escape', 'ArrowLeft', 'f', '+']) eq(inspectKey({ key }, at({ typing: true, picture: true })), null, `${key} typed into a field is the field's`)

/* Inside the drawn object, only Esc is the inspector's: a chart's or a
   timeline's own arrows and letters stay the object's. */
eq(inspectKey({ key: 'Escape' }, at({ inObject: true })), 'close', 'Esc inside the object returns')
for (const key of ['ArrowLeft', 'ArrowRight', 'f']) eq(inspectKey({ key }, at({ inObject: true })), null, `${key} inside the object is the object's`)

/* The browser's own shortcuts pass through. */
eq(inspectKey({ key: 'f', ctrlKey: true }, at()), null, 'Ctrl+F is the browser find')
eq(inspectKey({ key: '+', ctrlKey: true }, at({ picture: true })), null, 'Ctrl+ is the browser zoom')
eq(inspectKey({ key: 'ArrowRight', metaKey: true }, at()), null, 'Cmd+→ passes')
eq(inspectKey({ key: 'ArrowRight', altKey: true }, at()), null, 'Alt+→ passes')
eq(inspectKey({ key: 'x' }, at({ picture: true })), null, 'any other key passes')

/* -- scope ----------------------------------------------------------------- */

const listed = [
  { address: 'p/pic1', viewable: true, inspectable: true },
  { address: 'p/table', viewable: false, inspectable: true },
  { address: 'p/words', viewable: false, inspectable: false }, // a span of its words
  { address: 'p/film', viewable: true, inspectable: true },
  { address: 'p/table/cell', viewable: false, inspectable: false }, // not top-level
  { address: 'p/chart', viewable: false, inspectable: true },
]
eq(inspectScope(listed, true), ['p/pic1', 'p/film'], 'a picture steps through the post\'s pictures, films and sound, in order')
eq(inspectScope(listed, false), ['p/table', 'p/chart'], 'a table steps through the post\'s other top-level objects')
eq(inspectScope([], false), [], 'nothing listed, nothing to step through')

/* -- stepping -------------------------------------------------------------- */

const scope = ['a', 'b', 'c']
eq(stepIn(scope, 'a', 1), 'b', 'next')
eq(stepIn(scope, 'c', 1), 'a', 'next wraps round')
eq(stepIn(scope, 'a', -1), 'c', 'previous wraps round')
eq(stepIn(scope, 'b', -1), 'a', 'previous')
eq(stepIn(scope, 'zz', 1), 'a', 'one not in scope steps to its first')
eq(stepIn(['a'], 'a', 1), null, 'one alone: nothing to step to')
eq(stepIn([], 'a', 1), null, 'none: nothing to step to')

console.log(`inspect: ${checks} checks passed`)
