/* Fluid zones, P10a and P10b: what a zone's Show takes, held in Node against
   the UI source (no server, no browser, no build).

     * a form is its own kind (Forms), and forms, checklists, pads and tables
       with editable columns or rows to choose are fillable; other blocks,
       and tables only to read, are not;
     * an `is` an older bundle carried (no `fillable`) is asked again, so a
       form it called 'other' is a form;
     * a block inside another is shown on its own only where the block
       holding it is not: a panel's form under Forms, never twice under Its
       objects;
     * a block inside one the zone keeps is drawn by it, not followed in
       again as a card of its own (P10b review, finding 1);
     * a refused table is never fillable (finding 3);
     * on a rail, the read post's words go to a following zone not held on
       a post, or the first held one where all are (finding 2);
     * Stay on #N promises replies only where it shows them (finding 4);
     * a slot held on a post (`pin`) is a well-formed tree; a pin the server
       would refuse is not (finding 5).
   Run by tests/test_fluid_zone_filters.py. */
import assert from 'node:assert/strict'
import { fillableOf, kindOf } from '../src/experimental/objectkinds'
import { objectsOfPost } from '../src/experimental/postobjects'
import { heldOn, shownOf } from '../src/fluid/workspace/hooks'
import { valid, wordsZone } from '../src/fluid/workspace/tree'
import type { PostObjectEntry } from '../src/fluid/store'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }

/* -- what is fillable ------------------------------------------------------ */

eq(fillableOf('form'), true, 'a form is fillable')
eq(fillableOf('checklist'), true, 'a checklist is fillable')
eq(fillableOf('pad'), true, 'a pad is fillable')
const ROWS = 'id,note\na,x'
const tbl = (info: string, body = ROWS) => fillableOf('table', { info, body, closed: true })
eq(tbl('table version=1'), false, 'a table only to read is not')
eq(tbl('table version=1 key=id editable=note'), true, 'a table with an editable column is')
eq(tbl('table version=1 key=id editable=""'), false, 'an empty editable= names no column')
eq(tbl('table version=1 key=id select=one'), true, 'a table whose rows are chosen is')
eq(tbl('table version=1 key=id select=many'), true, 'many rows too')
eq(tbl('table version=1 select=none'), false, 'select=none chooses nothing')
eq(fillableOf('chart', { info: 'chart version=1 form=bar' }), false, 'a chart is not')
/* A table the table rules refuse is drawn as source: never fillable (finding 3). */
eq(tbl('table version=1 key=id editable=nosuch'), false, 'an editable column the table lacks is refused, so not fillable')
eq(tbl('table version=1 key=id editable=id'), false, 'the key made editable is refused, so not fillable')
eq(tbl('table version=1 key=id select=several'), false, 'a select= that is no choice is refused')
eq(tbl('table version=1 key=id editable=note', 'id,note\na,x\na,y'), false, 'keys that repeat are refused')
eq(fillableOf('table', { info: 'table version=1 key=id editable=note', body: ROWS, closed: false }), false, 'a table never closed is refused')
eq(fillableOf('table', { info: 'table version=1 key=id editable=note' }), false, 'a table with no rows to read is not fillable')
eq(fillableOf('panel'), false, 'a panel is not: what it holds may be')

const block = (type: string, info = `${type} version=1`, body = 'k,v\na,1') =>
  kindOf({ kind: 'block', type, parent: null, block: { info, body, closed: true } })
eq([block('form').filter, block('form').fillable], ['form', true], 'a form answers to Forms, not Other blocks')
eq([block('table', 'table version=1 editable=v key=k').filter, block('table', 'table version=1 editable=v key=k').fillable],
  ['table', true], 'an editable table stays a table, and is fillable')
eq(block('diagram').fillable, false, 'a diagram is not fillable')
eq(kindOf({ kind: 'link', type: 'link', parent: null }).fillable, undefined, 'only blocks carry fillable')

/* An older bundle's `is`: a form was 'other', with no `fillable`. It is asked again. */
const stale = { word: 'form', chip: 'form', family: 'section' as const, filter: 'other', doc: null, source: 'block' as const }
eq(kindOf({ kind: 'block', type: 'form', parent: null, is: stale }).filter, 'form', 'an older bundle\'s form is a form')
const carried = { ...stale, filter: 'form', fillable: true }
assert.equal(kindOf({ kind: 'block', type: 'form', parent: null, is: carried }), carried); checks++

/* -- what a zone shows of a post with nested blocks -------------------------- */

const POST = [
  'Words first.',
  '',
  '````panel version=1 name=section title="A section"',
  '```form version=1 name=ask title="Ask"',
  'field: name',
  '```',
  '',
  '```table version=1 key=id editable=note',
  'id,note',
  'a,x',
  '```',
  '````',
  '',
  '```chart version=1 form=bar x=item y=value x_label="Item" y_label="Value"',
  'item,value',
  'A,1',
  '```',
  '',
  '```pad version=1 name=notes',
  'Draft',
  '```',
  '',
  '```table version=1',
  'a,b',
  '1,2',
  '```',
].join('\n')

const objs: PostObjectEntry[] = objectsOfPost({ id: 'p1', parts: [{ type: 'text', text: POST }] })
  .map((o) => ({ ...o, declared: o.identity === 'declared', post: 'p1', version: 'p1',
    address: { exact: `exact:p1:${o.key}`, live: `live:p1:${o.key}` } }) as PostObjectEntry)
const typesOf = (show: Parameters<typeof shownOf>[1], kinds?: string[]) => shownOf(objs, show, kinds).map((o) => o.type)

const panel = objs.find((o) => o.type === 'panel')!
const form = objs.find((o) => o.type === 'form')!
eq(form.parent, panel.key, 'the form is inside the panel (the fixture is what it says)')

eq(typesOf('objects'), ['panel', 'chart', 'pad', 'table'], 'Its objects: the panel draws its form, so the form is not there twice')
eq(typesOf('sections'), ['panel', 'chart', 'pad', 'table'], 'Its blocks (`sections`) likewise')
eq(typesOf('everything'), ['text', 'panel', 'chart', 'pad', 'table'], 'Everything: the words, then each top-level object')
eq(typesOf('forms'), ['form'], 'Forms: the form inside the panel is shown')
eq(typesOf('fillable'), ['form', 'table', 'pad'], 'Things to fill in: the nested form and editable table, and the pad; not the table only to read')
eq(typesOf('kinds', ['form']), ['form'], 'Only some kinds: Forms finds the nested form')
eq(typesOf('kinds', ['table']), ['table', 'table'], 'Only some kinds: Tables finds the nested table and the top-level one')
eq(typesOf('kinds', ['other']), ['panel', 'pad'], 'Only some kinds: Other blocks no longer holds forms')
eq(typesOf('needs-you'), [], 'What needs you draws its own cards')

/* deeper: a form in a panel in a panel, and a holder missing from the listing */
const DEEP = ['`````panel version=1 name=outer', '````panel version=1 name=inner', '```form version=1 name=deep', 'field: x', '```', '````', '`````'].join('\n')
const deep = objectsOfPost({ id: 'p2', parts: [{ type: 'text', text: DEEP }] })
  .map((o) => ({ ...o, post: 'p2', version: 'p2', declared: false, address: { exact: o.key, live: o.key } }) as PostObjectEntry)
eq(shownOf(deep, 'sections').map((o) => o.name), ['outer'], 'only the outermost holder, however deep')
eq(shownOf(deep, 'forms').map((o) => o.name), ['deep'], 'the deepest form under Forms')
eq(shownOf(deep.filter((o) => o.name !== 'outer'), 'sections').map((o) => o.name), ['inner'],
  'a block whose holder is not listed is shown, not lost')

/* A zone that keeps the panel draws its form inside it: Forms and Things to
   fill in do not draw it again as a card of its own (finding 1). */
eq(typesOf('forms'), ['form'], "nothing kept: the panel's form is under Forms")
eq(shownOf(objs, 'forms', undefined, new Set([panel.address.live])).map((o) => o.type), [],
  'the panel kept here: its form is not shown again under Forms')
eq(shownOf(objs, 'fillable', undefined, new Set([panel.address.live])).map((o) => o.type), ['pad'],
  'the panel kept here: under Things to fill in its form and table are not shown again; the pad is')
eq(shownOf(objs, 'forms', undefined, new Set([panel.address.exact])).map((o) => o.type), [],
  'kept by its exact address, likewise')
eq(shownOf(deep, 'forms', undefined, new Set([deep.find((o) => o.name === 'outer')!.address.live])).map((o) => o.name), [],
  'any holder kept, however far up')
eq(shownOf(objs, 'forms', undefined, new Set([form.address.live])).map((o) => o.type), ['form'],
  "kept itself is the zone's to leave out (Zones.tsx), not a holder")

/* -- a zone held on one post (P10b) ---------------------------------------- */

const zoneWith = (slot: Record<string, unknown>) => ({ type: 'zone', id: 'z1', show: 'objects', slot: { follow: true, show: 'objects', items: [], present: 'cards', ...slot } })
eq(valid(zoneWith({ pin: 'ent-0123456789ab' })), true, 'a slot held on a post is well formed')
eq(valid(zoneWith({ show: 'forms' })), true, 'Forms is a Show')
eq(valid(zoneWith({ show: 'fillable' })), true, 'Things to fill in is a Show')
eq(valid(zoneWith({ pin: 7 })), false, 'a pin that is not an id is refused')
eq(valid(zoneWith({ pin: '' })), false, 'an empty pin is refused')
/* As the server takes a pin (lab_workspaces._TURN, arrangements._slot): finding 5. */
eq(valid(zoneWith({ pin: 'ent-0123 456789ab' })), false, 'a pin with a space is refused')
eq(valid(zoneWith({ pin: 'ent-0123/456789ab' })), false, 'a pin with a slash is refused')
eq(valid(zoneWith({ pin: 'x'.repeat(81) })), false, 'a pin longer than the server takes is refused')
eq(valid(zoneWith({ pin: 'ent-0123456789ab', follow: false })), false, 'only a zone that follows is held on a post')
/* pin: null is no pin, as the server takes it (arrangements._slot): on any zone. */
eq(valid(zoneWith({ pin: null })), true, 'a following zone with pin null is well formed')
eq(valid(zoneWith({ pin: null, follow: false })), true, 'a keeping zone with pin null is well formed')

/* Stay on #N says what it shows (finding 4): a reply is read on its own. */
eq(heldOn(5, false), '#5 and its replies', 'a post: it and its replies')
eq(heldOn(6, true), '#6', 'a reply: only itself')
eq(heldOn(null, false), 'this post and its replies', 'no number yet')

/* On a rail, whose zone carries the read post's words (finding 2). */
const z = (id: string, slot?: Record<string, unknown>) =>
  ({ type: 'zone', id, show: 'objects', ...(slot ? { slot: { follow: true, show: 'objects', items: [], present: 'cards', ...slot } } : {}) })
const split = (...kids: unknown[]) => ({ type: 'split', dir: 'row', kids, sizes: kids.map(() => 1 / kids.length) }) as never
eq(wordsZone(split(z('a', { pin: 'ent-0123456789ab' }), z('b', {}))), 'b', 'a held zone first: the next following zone carries the words')
eq(wordsZone(split(z('a', { follow: false }), z('b', {}), z('c', {}))), 'b', 'a keeping zone is passed over, as before')
eq(wordsZone(split(z('a', { pin: 'ent-0123456789ab' }), z('b', { pin: 'ent-0123456789ac' }))), 'a',
  "every following zone held: the first carries them (it draws the read post's words)")
eq(wordsZone(split(z('a', { follow: false }))), undefined, 'none follows: none carries them')
eq(valid(zoneWith({ show: 'forms-ish' })), false, 'an unknown Show is still refused')

console.log(`fluid zone filters: ${checks} checks passed`)
