/* WHICH INTERFACE AN ADDRESS OPENS (src/entry.ts). Quiet Chat is the default;
 * Fluid is the explicit legacy route; no saved link loses where it pointed. */
import assert from 'node:assert/strict'
import { entryFor, namesAFluidPlace } from '../src/entry'
import { PLACE_NAMES } from '../src/quiet2/address'

const at = (url: string) => { const u = new URL(url, 'http://h'); return { pathname: u.pathname, search: u.search, hash: u.hash } }
const opens = (url: string) => entryFor(at(url))

// THE ROOT IS QUIET CHAT -- mounted there, not sent somewhere else.
assert.deepEqual(opens('/'), { mount: 'quiet2' })
// ...with everything Quiet Chat itself reads in an address.
assert.deepEqual(opens('/?c=ent-1'), { mount: 'quiet2' })
assert.deepEqual(opens('/?c=ent-1&at=12'), { mount: 'quiet2' })
assert.deepEqual(opens('/?record=ent-9'), { mount: 'quiet2' })
assert.deepEqual(opens('/?c=ent-1#ent-post'), { mount: 'quiet2' })       // a post's own anchor, no slash
assert.deepEqual(opens('/?receded=1'), { mount: 'quiet2' })
// ...and with every name Quiet Chat WRITES for a place (quiet2/address.ts): a
// record, Manage Sources, a source and a file of it, Add a source, the 3D
// Brain. None of them is one of Fluid's, at the root or at /quiet2.
for (const q of ['?c=ent-1&record=ent-9', '?c=ent-1&sources=all', '?sources=ent-5', '?c=ent-1&sources=ent-5&file=ent-5%2Fo%2Fa.md',
  '?sources=add', '?sources=add%2Fgit', '?c=ent-1&space=1', '?space=1', '?c=ent-1&at=3&record=ent-9#ent-post']) {
  assert.deepEqual(opens('/' + q), { mount: 'quiet2' }, q)
  assert.deepEqual(opens('/quiet2' + q), { mount: 'quiet2' }, q)
}
for (const name of PLACE_NAMES) assert.equal(namesAFluidPlace(`?${name}=x`, ''), false, name)

// EXISTING QUIET LINKS ARE UNTOUCHED.
for (const u of ['/quiet2', '/quiet2/', '/quiet2?c=ent-1&at=3', '/quiet2?record=ent-9', '/quiet2?gov=1', '/quiet2#/brain/space'])
  assert.deepEqual(opens(u), { mount: 'quiet2' }, u)
for (const u of ['/quiet', '/quiet/', '/quiet#/c/ent-1']) assert.deepEqual(opens(u), { mount: 'quiet' }, u)

// FLUID AT ITS OWN ROUTE, whatever it is asked for, and it never moves.
for (const u of ['/fluid', '/fluid/', '/fluid?c=ent-1', '/fluid?c=ent-1&t=ent-2', '/fluid?gov=1&s=rules', '/fluid?home=1', '/fluid?stream=1&from=ent-1', '/fluid#/brain/sources/a%2Fb', '/fluid#/brain/space'])
  assert.deepEqual(opens(u), { mount: 'fluid' }, u)

// A FLUID LINK WRITTEN AT THE ROOT KEEPS ITS DESTINATION: handed to /fluid, query and hash untouched.
const kept: [string, string][] = [
  ['/?c=ent-1&t=ent-2', '/fluid?c=ent-1&t=ent-2'],
  ['/?gov=1', '/fluid?gov=1'],
  ['/?gov=1&s=rules', '/fluid?gov=1&s=rules'],
  ['/?view=governance', '/fluid?view=governance'],
  ['/?home=1', '/fluid?home=1'],
  ['/?stream=1&from=ent-1', '/fluid?stream=1&from=ent-1'],
  ['/?w=ws-1', '/fluid?w=ws-1'],
  ['/?lab', '/fluid?lab'],
  ['/#/brain/sources/a%2Fb/c', '/fluid#/brain/sources/a%2Fb/c'],
  ['/#/brain/space', '/fluid#/brain/space'],
  ['/#/c/ent-1/t/ent-2', '/fluid#/c/ent-1/t/ent-2'],
  ['/?c=ent%201&t=a%26b#/brain', '/fluid?c=ent%201&t=a%26b#/brain'],
]
for (const [from, to] of kept) assert.deepEqual(opens(from), { to }, from)

// NO LOOPS: wherever an address is sent, that address stays put.
for (const [from] of kept) {
  const first = opens(from)
  assert.ok('to' in first)
  assert.deepEqual(opens(first.to), { mount: 'fluid' }, from)
}

// AN UNKNOWN ADDRESS IS NOT SENT TO QUIET CHAT: it opens what it opened before.
for (const u of ['/nonsense', '/lab', '/lab/', '/index.html', '/quiet2/extra', '/quiet3', '/fluid/c/x', '/Quiet2'])
  assert.deepEqual(opens(u), { mount: 'fluid' }, u)

// What counts as Fluid's: only its own parameters and its `#/` places.
assert.equal(namesAFluidPlace('', ''), false)
assert.equal(namesAFluidPlace('?c=x', ''), false)
assert.equal(namesAFluidPlace('?c=x&at=4', '#ent-1'), false)
assert.equal(namesAFluidPlace('?record=t', ''), false)                    // a value is not a name
assert.equal(namesAFluidPlace('?c=gov', ''), false)
assert.equal(namesAFluidPlace('?t=', ''), true)
assert.equal(namesAFluidPlace('', '#/'), true)
console.log('entry_unit: ok')
